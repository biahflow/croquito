"""Cadeia completa do orçamento-base, ponta a ponta, pela API `/v1` autenticada (F-020 T5).

Contraponto de `tests/e2e/test_valuation_full_chain.py` (`estimate_chain`, linhas 785-908):
aquele arquivo prova que a cadeia SCO -> EMOP -> composição fecha pelos comandos do CLI,
sobre a MESMA obra sintética da medição (`chain.reviewed_packet`). Este arquivo prova a
MESMA jornada de negócio — mesmas decisões do orçamentista sintético
(`croquito_worker.valuation.estimate_fixture`), mais a fonte SINAPI (F-026/T3) — pela
superfície nova: upload assinado e rotas HTTP autenticadas de `/v1/estimate-rounds`, com o
worker consumindo a fila no mesmo processo (`LocalQueueWorker.dispatch`,
ESTIMATE_ROUND_CHAIN, F-020 T6).

Nenhum passo importa `croquito_worker.valuation.cli`: os quatro catálogos da cascata
nascem das mesmas funções de domínio que os comandos `import-emop`/`import-sinapi`/
`import-compositions` chamam por baixo (`croquito_valuation.catalog.read_price_catalog`,
`croquito_valuation.emop.read_emop_catalog_with_report`,
`croquito_valuation.sinapi.read_sinapi_catalog`,
`croquito_valuation.composition.compile_compositions`), nunca do CLI que os embrulha — é
essa ausência de import que prova que a jornada não depende dele. A quarta fonte (SINAPI)
não tem decisão própria na fixture do orçamentista (`estimate_fixture.py`, fora de escopo
desta task): este teste substitui, só localmente, a decisão do mobiliário (banco de
concreto) para citar a SINAPI em vez da EMOP — mesmo item, mesma quantidade, fonte
diferente — e é essa substituição que prova a cascata de quatro fontes ponta a ponta sem
alterar nenhuma contagem existente.

A extração da legenda entra pelo mesmo seam de fixture que `tests/e2e/test_valuation_v1_chain.py`
usa (`legend_fixture_adapter` sobre a MESMA prancha sintética). O portão de ambiente da
rota (`CROQUITO_AI_MAX_ESTIMATED_COST_USD` + `CROQUITO_ANTHROPIC_API_KEY`) é freio de
config, não chamada de rede, e é isso — e só isso — que o `monkeypatch` do teste declara.

Toda mutação manda `Idempotency-Key` e o `base_version` corrente. O único acesso direto ao
object store neste arquivo é para reler a planilha PUBLICADA (a URL assinada da fixture não
é buscável por HTTP) e conferir seu digest contra o que a API declarou.
"""

from __future__ import annotations

import hashlib
from decimal import Decimal
from pathlib import Path
from typing import Any, Final, cast

import pytest
from fastapi.testclient import TestClient

from croquito_api.config import ApiSettings
from croquito_api.database import Database
from croquito_api.estimate_rounds import estimate_workbook_key
from croquito_api.main import create_app
from croquito_valuation.canonical import canonicalize_workbook
from croquito_valuation.catalog import read_price_catalog
from croquito_valuation.composition import compile_compositions
from croquito_valuation.emop import read_emop_catalog_with_report
from croquito_valuation.estimate import Estimate
from croquito_valuation.estimate_workbook import audit_estimate_workbook
from croquito_valuation.models import PriceCatalog, PriceOrigin
from croquito_valuation.sinapi import read_sinapi_catalog
from croquito_valuation.takeoff import TakeoffPacket
from croquito_valuation.template import default_template
from croquito_worker.local_queue import LocalQueueWorker, LocalWorkerSettings
from croquito_worker.valuation.emop_fixture import emop_fixture_layout, write_emop_dbf
from croquito_worker.valuation.estimate_fixture import (
    SYNTHETIC_ESTIMATE_WORKSITE_KEY,
    SYNTHETIC_ESTIMATE_WORKSITE_NAME,
    build_demo_estimate_assignments,
    build_synthetic_composition_set,
)
from croquito_worker.valuation.legend_fixtures import legend_fixture_adapter
from croquito_worker.valuation.plate import SYNTHETIC_LEGEND_ROWS, render_synthetic_plate
from croquito_worker.valuation.round_extraction import AI_BUDGET_ENV
from croquito_worker.valuation.sinapi_fixture import sinapi_fixture_layout, write_sinapi_xlsx
from croquito_worker.valuation.synthetic import (
    SYNTHETIC_CONTRACT_SOURCE_LABEL,
    SYNTHETIC_REFERENCE_MONTH,
    build_demo_takeoff_decisions,
    build_synthetic_previous_mapao,
    item_for_label,
)
from tests.fakes import FakeObjectStore, FakeQueue

TENANT: Final = "tenant-estimate-v1-e2e"
QUEUE_URL: Final = "http://localstack/queue"
SUBJECT: Final = "orcamentista-estimate-v1-e2e"
ROLE: Final = "orcamentista"
_ANTHROPIC_KEY_ENV: Final = "CROQUITO_ANTHROPIC_API_KEY"

REFERENCE_LABEL: Final = "ORCAMENTO V1 E2E 01/2026"
ADDRESS: Final = "RUA SINTETICA ORCAMENTO V1, S/N"
BDI_PERCENT: Final = "25.00"


def _headers(key: str | None = None, *, tenant: str = TENANT, roles: str = ROLE) -> dict[str, str]:
    headers = {"Authorization": f"Bearer test:{tenant}:{SUBJECT}:{roles}"}
    if key is not None:
        headers["Idempotency-Key"] = key
    return headers


def _presign_and_put(
    client: TestClient,
    storage: FakeObjectStore,
    *,
    filename: str,
    content_type: str,
    payload: bytes,
    key: str,
) -> dict[str, Any]:
    presign = client.post(
        "/v1/uploads/presign",
        headers=_headers(key),
        json={
            "filename": filename,
            "content_type": content_type,
            "size_bytes": len(payload),
            "sha256": hashlib.sha256(payload).hexdigest(),
        },
    )
    assert presign.status_code == 200, presign.text
    storage.put_direct(
        object_key=presign.json()["object_key"], body=payload, content_type=content_type
    )
    return cast(dict[str, Any], presign.json())


def _catalog_upload_bytes(catalog: PriceCatalog) -> bytes:
    return catalog.model_dump_json().encode("utf-8")


def _packet_from_takeoff_response(body: dict[str, Any]) -> TakeoffPacket:
    """`GET .../takeoff` junta uma âncora por item (`anchored_packet`); o domínio não a
    conhece (`extra="forbid"`), então ela sai antes de revalidar o pacote."""
    document = dict(body["packet"])
    items = []
    for item in document["items"]:
        item = dict(item)
        item.pop("anchor", None)
        items.append(item)
    return TakeoffPacket.model_validate({**document, "items": items})


def _drain(worker: LocalQueueWorker) -> int:
    """Consome toda a fila corrente."""
    processed = 0
    while worker.run_once():
        processed += 1
    return processed


def _canonical_cells(canonical: dict[str, object], sheet_name: str) -> dict[str, dict[str, object]]:
    sheets = canonical["sheets"]
    assert isinstance(sheets, list)
    for sheet in sheets:
        assert isinstance(sheet, dict)
        if sheet["name"] == sheet_name:
            cells = sheet["cells"]
            assert isinstance(cells, list)
            return {str(cell["ref"]): cell for cell in cells if isinstance(cell, dict)}
    raise AssertionError(f"aba ausente no canônico: {sheet_name}")


@pytest.fixture
def stack(
    tmp_path: Path,
) -> tuple[TestClient, FakeObjectStore, FakeQueue, str]:
    """API sobre SQLite em arquivo + storage/fila em memória compartilhados com o worker."""
    database_url = f"sqlite+pysqlite:///{tmp_path / 'estimate-v1-chain.db'}"
    database = Database(database_url)
    database.create_schema()
    settings = ApiSettings(
        database_url=database_url,
        artifact_bucket="croquito-estimate-v1-e2e",
        aws_region="sa-east-1",
        aws_endpoint_url="http://localhost:4566",
        queue_url=QUEUE_URL,
        oidc_issuer=None,
        oidc_audience=None,
        web_origin="http://localhost:5173",
        allow_test_tokens=True,
    )
    app = create_app(settings=settings, database=database)
    storage = FakeObjectStore()
    queue = FakeQueue()
    app.state.artifact_store = storage
    app.state.queue.client = queue
    return TestClient(app), storage, queue, database_url


def test_estimate_round_full_chain_through_v1_api(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    stack: tuple[TestClient, FakeObjectStore, FakeQueue, str],
) -> None:
    client, storage, queue, database_url = stack

    # 0. Prancha sintética gerada agora, e o adapter fixture amarrado a ela: nenhuma chamada
    # externa acontece, mas a extração ainda precisa do freio de ambiente declarado (teto de
    # gasto + credencial) para a ROTA aceitar o pedido — é config, não rede.
    plate = render_synthetic_plate(tmp_path / "plate-source")
    monkeypatch.setenv(AI_BUDGET_ENV, "1.50")
    monkeypatch.setenv(_ANTHROPIC_KEY_ENV, "chave-de-teste-nunca-usada")
    worker = LocalQueueWorker(
        LocalWorkerSettings(
            database_url=database_url,
            queue_url=QUEUE_URL,
            aws_region="sa-east-1",
            aws_endpoint_url="http://localhost:4566",
            artifact_bucket="croquito-estimate-v1-e2e",
        ),
        valuation_extraction_adapter=legend_fixture_adapter(plate),
    )
    worker.client = queue
    worker.s3_client = storage

    # 0b. As três fontes de preço da cascata, construídas pelas MESMAS funções de domínio
    # que os comandos `import-emop`/`import-compositions` chamam por baixo — nunca o CLI.
    template = default_template()
    previous_mapao_path = build_synthetic_previous_mapao(tmp_path / "previous-mapao.xlsx")
    sco_catalog = read_price_catalog(
        previous_mapao_path,
        template,
        source_label=SYNTHETIC_CONTRACT_SOURCE_LABEL,
        reference_month=SYNTHETIC_REFERENCE_MONTH,
    )
    dbf_path = write_emop_dbf(tmp_path / "emop-sintetico.dbf")
    emop_catalog, _emop_notes = read_emop_catalog_with_report(dbf_path, emop_fixture_layout())
    composition_set = build_synthetic_composition_set()
    composition_source_sha256 = hashlib.sha256(
        composition_set.model_dump_json().encode("utf-8")
    ).hexdigest()
    composition_catalog = compile_compositions(
        composition_set, source_sha256=composition_source_sha256
    )
    sinapi_path = write_sinapi_xlsx(tmp_path / "sinapi-sintetico.xlsx")
    sinapi_catalog = read_sinapi_catalog(sinapi_path, sinapi_fixture_layout())
    cascade = (sco_catalog, emop_catalog, composition_catalog, sinapi_catalog)

    # 1. `POST /v1/estimate-rounds`: abre a rodada, ainda sem fonte de preço.
    created = client.post(
        "/v1/estimate-rounds",
        headers=_headers("rodada-estimate-v1-e2e"),
        json={
            "worksite_key": SYNTHETIC_ESTIMATE_WORKSITE_KEY,
            "worksite_name": SYNTHETIC_ESTIMATE_WORKSITE_NAME,
            "reference_label": REFERENCE_LABEL,
            "address": ADDRESS,
        },
    )
    assert created.status_code == 201, created.text
    round_id = created.json()["round_id"]
    assert created.json()["version"] == 1
    version = 1

    # 2. Instala as três fontes na cascata, na ordem declarada (SCO, EMOP, COMPOSIÇÃO).
    for index, catalog in enumerate(cascade):
        upload = _presign_and_put(
            client,
            storage,
            filename=f"catalogo-{catalog.origin.value}.json",
            content_type="application/json",
            payload=_catalog_upload_bytes(catalog),
            key=f"presign-catalogo-{index}",
        )
        installed = client.post(
            f"/v1/estimate-rounds/{round_id}/catalogs",
            headers=_headers(f"instala-catalogo-{index}"),
            json={"upload_id": upload["upload_id"], "base_version": version},
        )
        assert installed.status_code == 201, installed.text
        version = installed.json()["version"]
        assert [entry["origin"] for entry in installed.json()["cascade"]] == [
            source.origin.value for source in cascade[: index + 1]
        ]

    # A recusa de origem repetida: reinstalar o catálogo SCO (mesmo conteúdo de origem, novo
    # upload) recusa com `409 ESTIMATE_CASCADE_ORIGIN_DUPLICATE` e não avança a rodada.
    duplicate_upload = _presign_and_put(
        client,
        storage,
        filename="catalogo-sco-duplicado.json",
        content_type="application/json",
        payload=_catalog_upload_bytes(sco_catalog),
        key="presign-catalogo-duplicado",
    )
    duplicate = client.post(
        f"/v1/estimate-rounds/{round_id}/catalogs",
        headers=_headers("instala-catalogo-duplicado"),
        json={"upload_id": duplicate_upload["upload_id"], "base_version": version},
    )
    assert duplicate.status_code == 409, duplicate.text
    assert duplicate.json()["detail"]["code"] == "ESTIMATE_CASCADE_ORIGIN_DUPLICATE"

    unchanged = client.get(f"/v1/estimate-rounds/{round_id}", headers=_headers()).json()
    assert unchanged["version"] == version

    # 3. Presign + PUT da prancha sintética, e a associação à rodada; e a extração paga cai
    # na fila, consumida pelo worker no MESMO teste com o adapter fixture (caminho offline).
    plate_payload = plate.pdf_path.read_bytes()
    plate_upload = _presign_and_put(
        client,
        storage,
        filename="prancha.pdf",
        content_type="application/pdf",
        payload=plate_payload,
        key="presign-prancha",
    )
    associated = client.post(
        f"/v1/estimate-rounds/{round_id}/plate",
        headers=_headers("prancha-associada"),
        json={"upload_id": plate_upload["upload_id"], "base_version": version},
    )
    assert associated.status_code == 200, associated.text
    version = associated.json()["version"]

    extraction = client.post(
        f"/v1/estimate-rounds/{round_id}/plate/extractions",
        headers=_headers("extracao-estimate-v1-e2e"),
        json={"base_version": version},
    )
    assert extraction.status_code == 202, extraction.text
    assert extraction.json()["status"] == "queued"
    version = extraction.json()["version"]
    assert queue.commands() == []  # nada consumido ainda: só publicado

    assert _drain(worker) == 1
    assert queue.commands() == ["extract_estimate_plate"]

    round_after_extraction = client.get(
        f"/v1/estimate-rounds/{round_id}", headers=_headers()
    ).json()
    assert round_after_extraction["extraction"]["status"] == "done"
    version = round_after_extraction["version"]

    # 4. Decide takeoff item a item, até a revisão ficar completa.
    takeoff = client.get(f"/v1/estimate-rounds/{round_id}/takeoff", headers=_headers()).json()
    assert takeoff["version"] == version
    assert takeoff["items"] == len(SYNTHETIC_LEGEND_ROWS)
    assert takeoff["review_status"] == "review_required"
    packet = _packet_from_takeoff_response(takeoff)

    takeoff_decisions = build_demo_takeoff_decisions(packet).decisions
    last_decision_response: dict[str, Any] | None = None
    for index, decision in enumerate(takeoff_decisions):
        response = client.post(
            f"/v1/estimate-rounds/{round_id}/takeoff/decisions",
            headers=_headers(f"decisao-takeoff-{index}"),
            json={
                "base_version": version,
                "item_id": decision.item_id,
                "action": decision.action,
                "quantity": None if decision.quantity is None else str(decision.quantity),
                "unit": decision.unit,
                "note": decision.note,
            },
        )
        assert response.status_code == 200, response.text
        body = response.json()
        version = body["version"]
        last_decision_response = body
    assert last_decision_response is not None
    assert last_decision_response["review_status"] == "complete"
    assert last_decision_response["pending"] == 0
    assert last_decision_response["overlay"]["stale"] is True

    assert _drain(worker) == len(takeoff_decisions)
    assert queue.commands().count("rerender_estimate_takeoff_overlay") == len(takeoff_decisions)

    overlay_after_decisions = client.get(
        f"/v1/estimate-rounds/{round_id}/takeoff/overlay", headers=_headers()
    ).json()
    assert overlay_after_decisions["stale"] is False

    final_takeoff = client.get(f"/v1/estimate-rounds/{round_id}/takeoff", headers=_headers()).json()
    assert final_takeoff["confirmed"] == len(SYNTHETIC_LEGEND_ROWS) - 1  # a intervenção rejeita
    assert final_takeoff["rejected"] == 1
    final_packet = _packet_from_takeoff_response(final_takeoff)

    # 5. Confirma (ou rejeita) o código de cada item, CITANDO a fonte da cascata.
    #
    # A fixture do orçamentista (`estimate_fixture.py`, fora de escopo desta task) decide o
    # banco de concreto pela EMOP; aqui, só neste teste, a mesma decisão é reescrita para
    # citar a SINAPI (código "0009012", "MOBILIARIO SINTETICO SINAPI", unidade "UN" — bate a
    # unidade "UN" do item, `SINAPI_FIXTURE_ROWS[2]` em `sinapi_fixture.py`) — prova que a
    # cascata de quatro fontes fecha com pelo menos um item decidido pela origem nova, sem
    # mudar quantas decisões existem nem a contagem de confirmados/rejeitados.
    bench_item_id = item_for_label(final_packet, "BANCO DE CONCRETO SINTETICO").id
    code_decisions = [
        assignment.model_copy(
            update={
                "code": "0009012",
                "catalog_sha256": sinapi_catalog.source_sha256,
                "note": "mobiliario cotado pela SINAPI nesta pre-licitacao",
            }
        )
        if assignment.item_id == bench_item_id
        else assignment
        for assignment in build_demo_estimate_assignments(final_packet, list(cascade)).assignments
    ]
    for index, assignment in enumerate(code_decisions):
        response = client.post(
            f"/v1/estimate-rounds/{round_id}/code-assignments/decisions",
            headers=_headers(f"decisao-codigo-{index}"),
            json={
                "base_version": version,
                "item_id": assignment.item_id,
                "action": assignment.action,
                "code": assignment.code,
                "catalog_sha256": assignment.catalog_sha256,
                "note": assignment.note,
            },
        )
        assert response.status_code == 200, response.text
        version = response.json()["version"]

    assignments_state = client.get(
        f"/v1/estimate-rounds/{round_id}/code-assignments", headers=_headers()
    ).json()
    assert assignments_state["pending_items"] == []
    assert assignments_state["rejected"] == 1  # a luminária: nenhuma fonte a precifica
    assert assignments_state["confirmed"] == len(code_decisions) - 1

    # 6. `base_version` velho recusa a montagem com `409 REVISION_CONFLICT`, sem publicar
    # orçamento nem planilha nenhuma.
    stale = client.post(
        f"/v1/estimate-rounds/{round_id}/estimate",
        headers=_headers("orcamento-versao-velha"),
        json={"base_version": version - 1, "bdi_percent": BDI_PERCENT},
    )
    assert stale.status_code == 409, stale.text
    assert stale.json()["detail"]["code"] == "REVISION_CONFLICT"

    unchanged_after_stale = client.get(f"/v1/estimate-rounds/{round_id}", headers=_headers()).json()
    assert unchanged_after_stale["version"] == version
    assert unchanged_after_stale["estimate"]["present"] is False

    # 7. `POST .../estimate` com o `base_version` correto: monta, audita e publica.
    built = client.post(
        f"/v1/estimate-rounds/{round_id}/estimate",
        headers=_headers("orcamento-v1-e2e"),
        json={"base_version": version, "bdi_percent": BDI_PERCENT},
    )
    assert built.status_code == 200, built.text
    built_body = built.json()
    version = built_body["version"]
    assert built_body["bdi_percent"] == BDI_PERCENT
    assert built_body["workbook_present"] is True
    # Retrocompatibilidade (F-027 T3): rodada sem teto declarado não ganha o bloco
    # derivado do teto de verba (ADR-0040) — nem `target`, nem `consumed`/`remaining`/`over`.
    for absent_key in ("target", "consumed", "remaining", "over"):
        assert absent_key not in built_body

    # `estimate_json` da revisão valida com `Estimate.model_validate` (schema v2), e os dois
    # totais batem com o que a rota publicou como texto.
    estimate = Estimate.model_validate(built_body["estimate"])
    assert str(estimate.total_amount) == built_body["total_amount"]
    assert str(estimate.total_amount_without_bdi) == built_body["total_amount_without_bdi"]
    printed_bdi_amount = estimate.total_amount - estimate.total_amount_without_bdi
    assert estimate.unpriced_item_ids == [
        item_for_label(final_packet, "LUMINARIA DUPLA SINTETICA").id
    ]

    # A cascata tem quatro fontes: a linha do banco de concreto (item redecidido no passo 5)
    # cita a origem nova e o código do catálogo SINAPI.
    sinapi_line_index, sinapi_line = next(
        (index, line)
        for index, line in enumerate(estimate.lines)
        if line.price_origin.value == "sinapi"
    )
    assert sinapi_line.price_origin == PriceOrigin.SINAPI
    assert sinapi_line.code == "0009012"
    assert sinapi_line.catalog_sha256 == sinapi_catalog.source_sha256

    # 8. `GET .../estimate`: auditoria ok, planilha publicada — a URL assinada da fixture
    # não é buscável por HTTP, então a conferência lê o BLOB diretamente do object store,
    # pela mesma chave que a API deriva do digest do orçamento.
    read = client.get(f"/v1/estimate-rounds/{round_id}/estimate", headers=_headers()).json()
    assert read["estimate_sha256"] == built_body["estimate_sha256"]
    assert read["workbook_present"] is True
    assert read["workbook_url"] is not None
    for absent_key in ("target", "consumed", "remaining", "over"):
        assert absent_key not in read

    object_key = estimate_workbook_key(
        tenant_id=TENANT, round_id=str(round_id), estimate_sha256=read["estimate_sha256"]
    )
    workbook_bytes = storage.body(object_key)
    assert hashlib.sha256(workbook_bytes).hexdigest() == read["workbook_sha256"]

    workbook_path = tmp_path / "orcamento-publicado.xlsx"
    workbook_path.write_bytes(workbook_bytes)

    audit = audit_estimate_workbook(workbook_path, estimate, template)
    assert audit.status == "ok"
    assert audit.findings == []

    layout = template.estimate
    assert layout is not None
    columns = layout.columns
    canonical = canonicalize_workbook(workbook_path, template)
    cells = _canonical_cells(canonical, layout.sheet_name)

    # A planilha publicada, reaberta com openpyxl (por dentro de `canonicalize_workbook`),
    # tem as colunas FONTE e VALOR UNIT. C/ BDI.
    header_row = layout.header_row
    assert cells[f"{columns.source.letter}{header_row}"]["value"] == "FONTE"
    bdi_price_header = cells[f"{columns.unit_price_with_bdi.letter}{header_row}"]["value"]
    assert bdi_price_header == "VALOR UNIT. C/ BDI"

    # A linha do banco de concreto (fonte SINAPI) reabre com "SINAPI" na célula FONTE.
    sinapi_row = header_row + sinapi_line_index + 1
    sinapi_source_cell = cells[f"{columns.source.letter}{sinapi_row}"]["value"]
    assert isinstance(sinapi_source_cell, str)
    assert "SINAPI" in sinapi_source_cell

    # `total_amount - total_amount_without_bdi` bate com o BDI impresso na planilha.
    n_lines = len(estimate.lines)
    last_line_row = header_row + n_lines
    total_without_bdi_row = last_line_row + 2
    bdi_amount_row = total_without_bdi_row + 1
    total_row = bdi_amount_row + 1
    total_col = columns.total.letter
    assert Decimal(str(cells[f"{total_col}{bdi_amount_row}"]["value"])) == printed_bdi_amount
    assert Decimal(str(cells[f"{total_col}{total_row}"]["value"])) == estimate.total_amount

    # O bloco de itens sem preço: a luminária, sem nenhum campo de preço junto.
    unpriced_header_row = total_row + 2
    assert (
        cells[f"{columns.item.letter}{unpriced_header_row}"]["value"]
        == layout.unpriced_section_label
    )
    printed_unpriced_ids = [
        cells[f"{columns.item.letter}{unpriced_header_row + 1 + offset}"]["value"]
        for offset in range(len(estimate.unpriced_item_ids))
    ]
    assert printed_unpriced_ids == estimate.unpriced_item_ids


def test_estimate_round_target_over_and_exact_limit_through_v1_api(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    stack: tuple[TestClient, FakeObjectStore, FakeQueue, str],
) -> None:
    """Teto declarado na criação, consumido pela cadeia real `/v1` (F-027 T3, ADR-0040).

    Réplica enxuta de `test_estimate_round_full_chain_through_v1_api` até o orçamento
    montado — sem repetir as asserções de cascata/planilha que aquele teste já cobre —
    desta vez com `target_amount` declarado na CRIAÇÃO da rodada (critério 2 da feature),
    para provar o bloco derivado com valores exatos pela cadeia inteira: estouro na
    montagem (critério 3), limite exato editado depois NÃO é estouro (critério 4),
    conflito de versão e teto inválido na rota `.../target`.

    O total conhecido deste cenário (`legend_fixture_adapter` + as três fontes da
    cascata + `build_demo_estimate_assignments`) é `71516.83` com BDI 25% — medido
    empiricamente a partir da MESMA cadeia (não é o `1125.00` do cenário menor usado
    pelos testes de rota de T1 em `tests/api/test_estimate_round_routes.py`, que usa uma
    fixture sintética diferente e mais simples).
    """
    client, storage, queue, database_url = stack

    plate = render_synthetic_plate(tmp_path / "plate-source")
    monkeypatch.setenv(AI_BUDGET_ENV, "1.50")
    monkeypatch.setenv(_ANTHROPIC_KEY_ENV, "chave-de-teste-nunca-usada")
    worker = LocalQueueWorker(
        LocalWorkerSettings(
            database_url=database_url,
            queue_url=QUEUE_URL,
            aws_region="sa-east-1",
            aws_endpoint_url="http://localhost:4566",
            artifact_bucket="croquito-estimate-v1-e2e",
        ),
        valuation_extraction_adapter=legend_fixture_adapter(plate),
    )
    worker.client = queue
    worker.s3_client = storage

    template = default_template()
    previous_mapao_path = build_synthetic_previous_mapao(tmp_path / "previous-mapao-teto.xlsx")
    sco_catalog = read_price_catalog(
        previous_mapao_path,
        template,
        source_label=SYNTHETIC_CONTRACT_SOURCE_LABEL,
        reference_month=SYNTHETIC_REFERENCE_MONTH,
    )
    dbf_path = write_emop_dbf(tmp_path / "emop-sintetico-teto.dbf")
    emop_catalog, _emop_notes = read_emop_catalog_with_report(dbf_path, emop_fixture_layout())
    composition_set = build_synthetic_composition_set()
    composition_source_sha256 = hashlib.sha256(
        composition_set.model_dump_json().encode("utf-8")
    ).hexdigest()
    composition_catalog = compile_compositions(
        composition_set, source_sha256=composition_source_sha256
    )
    cascade = (sco_catalog, emop_catalog, composition_catalog)

    # 1. `POST /v1/estimate-rounds` JÁ com teto declarado (critério 2 da feature) — menor
    # que o total conhecido do cenário, para estourar assim que a montagem publicar.
    created = client.post(
        "/v1/estimate-rounds",
        headers=_headers("rodada-teto-e2e"),
        json={
            "worksite_key": "praca-sintetica-teto-e2e",
            "worksite_name": SYNTHETIC_ESTIMATE_WORKSITE_NAME,
            "reference_label": "ORCAMENTO V1 TETO E2E 01/2026",
            "address": ADDRESS,
            "target_amount": "70000.00",
            "target_label": "Relação de Praças 2026 · demanda de teste",
        },
    )
    assert created.status_code == 201, created.text
    round_id = created.json()["round_id"]
    version = created.json()["version"]

    for index, catalog in enumerate(cascade):
        upload = _presign_and_put(
            client,
            storage,
            filename=f"catalogo-teto-{catalog.origin.value}.json",
            content_type="application/json",
            payload=_catalog_upload_bytes(catalog),
            key=f"presign-catalogo-teto-{index}",
        )
        installed = client.post(
            f"/v1/estimate-rounds/{round_id}/catalogs",
            headers=_headers(f"instala-catalogo-teto-{index}"),
            json={"upload_id": upload["upload_id"], "base_version": version},
        )
        assert installed.status_code == 201, installed.text
        version = installed.json()["version"]

    plate_payload = plate.pdf_path.read_bytes()
    plate_upload = _presign_and_put(
        client,
        storage,
        filename="prancha-teto.pdf",
        content_type="application/pdf",
        payload=plate_payload,
        key="presign-prancha-teto",
    )
    associated = client.post(
        f"/v1/estimate-rounds/{round_id}/plate",
        headers=_headers("prancha-associada-teto"),
        json={"upload_id": plate_upload["upload_id"], "base_version": version},
    )
    assert associated.status_code == 200, associated.text
    version = associated.json()["version"]

    extraction = client.post(
        f"/v1/estimate-rounds/{round_id}/plate/extractions",
        headers=_headers("extracao-teto-e2e"),
        json={"base_version": version},
    )
    assert extraction.status_code == 202, extraction.text
    version = extraction.json()["version"]

    assert _drain(worker) == 1

    round_after_extraction = client.get(
        f"/v1/estimate-rounds/{round_id}", headers=_headers()
    ).json()
    assert round_after_extraction["extraction"]["status"] == "done"
    version = round_after_extraction["version"]
    # O teto sobrevive intacto ao resto da cadeia: sem orçamento montado, o bloco
    # derivado só tem `target` — o consumo depende do `total_amount` que ainda não existe.
    assert round_after_extraction["target"] == {
        "amount": "70000.00",
        "label": "Relação de Praças 2026 · demanda de teste",
    }
    assert "consumed" not in round_after_extraction

    takeoff = client.get(f"/v1/estimate-rounds/{round_id}/takeoff", headers=_headers()).json()
    assert takeoff["version"] == version
    packet = _packet_from_takeoff_response(takeoff)

    takeoff_decisions = build_demo_takeoff_decisions(packet).decisions
    last_decision_response: dict[str, Any] | None = None
    for index, decision in enumerate(takeoff_decisions):
        response = client.post(
            f"/v1/estimate-rounds/{round_id}/takeoff/decisions",
            headers=_headers(f"decisao-takeoff-teto-{index}"),
            json={
                "base_version": version,
                "item_id": decision.item_id,
                "action": decision.action,
                "quantity": None if decision.quantity is None else str(decision.quantity),
                "unit": decision.unit,
                "note": decision.note,
            },
        )
        assert response.status_code == 200, response.text
        body = response.json()
        version = body["version"]
        last_decision_response = body
    assert last_decision_response is not None
    assert last_decision_response["review_status"] == "complete"

    assert _drain(worker) == len(takeoff_decisions)

    final_takeoff = client.get(f"/v1/estimate-rounds/{round_id}/takeoff", headers=_headers()).json()
    final_packet = _packet_from_takeoff_response(final_takeoff)

    code_decisions = build_demo_estimate_assignments(final_packet, list(cascade)).assignments
    for index, assignment in enumerate(code_decisions):
        response = client.post(
            f"/v1/estimate-rounds/{round_id}/code-assignments/decisions",
            headers=_headers(f"decisao-codigo-teto-{index}"),
            json={
                "base_version": version,
                "item_id": assignment.item_id,
                "action": assignment.action,
                "code": assignment.code,
                "catalog_sha256": assignment.catalog_sha256,
                "note": assignment.note,
            },
        )
        assert response.status_code == 200, response.text
        version = response.json()["version"]

    # 2. `POST .../estimate`: monta, audita e publica — teto (70000.00) menor que o total
    # conhecido do cenário (71516.83 com BDI 25%) estoura já na PRÓPRIA montagem
    # (critério 3 da feature).
    built = client.post(
        f"/v1/estimate-rounds/{round_id}/estimate",
        headers=_headers("orcamento-teto-e2e"),
        json={"base_version": version, "bdi_percent": BDI_PERCENT},
    )
    assert built.status_code == 200, built.text
    built_body = built.json()
    version = built_body["version"]
    total_amount = built_body["total_amount"]
    assert total_amount == "71516.83"
    assert built_body["target"] == {
        "amount": "70000.00",
        "label": "Relação de Praças 2026 · demanda de teste",
    }
    assert built_body["consumed"] == total_amount
    assert built_body["remaining"] == "-1516.83"
    assert built_body["over"] is True

    read_after_build = client.get(
        f"/v1/estimate-rounds/{round_id}/estimate", headers=_headers()
    ).json()
    assert read_after_build["consumed"] == total_amount
    assert read_after_build["remaining"] == "-1516.83"
    assert read_after_build["over"] is True

    # 3. `POST .../target` editando o teto para EXATAMENTE o total conhecido: o limite
    # exato NÃO é estouro (critério 4 da feature) — `over: false`, `remaining == "0.00"`.
    exact = client.post(
        f"/v1/estimate-rounds/{round_id}/target",
        headers=_headers("teto-limite-exato-e2e"),
        json={"base_version": version, "target_amount": total_amount},
    )
    assert exact.status_code == 200, exact.text
    exact_body = exact.json()
    version = exact_body["version"]
    # Editar sem repetir `target_label` limpa o rótulo — a rota não faz merge parcial.
    assert exact_body["target"] == {"amount": total_amount, "label": None}
    assert exact_body["consumed"] == total_amount
    assert exact_body["remaining"] == "0.00"
    assert exact_body["over"] is False

    # 4. `base_version` velho recusa com `409 REVISION_CONFLICT`, sem gravar nada.
    stale = client.post(
        f"/v1/estimate-rounds/{round_id}/target",
        headers=_headers("teto-velho-e2e"),
        json={"base_version": version - 1, "target_amount": "1.00"},
    )
    assert stale.status_code == 409, stale.text
    assert stale.json()["detail"]["code"] == "REVISION_CONFLICT"

    unchanged = client.get(f"/v1/estimate-rounds/{round_id}", headers=_headers()).json()
    assert unchanged["version"] == version
    assert unchanged["target"] == {"amount": total_amount, "label": None}

    # 5. `0,00` recusa com `422 ESTIMATE_TARGET_INVALID`, sem avançar a versão nem tocar
    # o teto gravado.
    invalid = client.post(
        f"/v1/estimate-rounds/{round_id}/target",
        headers=_headers("teto-invalido-e2e"),
        json={"base_version": version, "target_amount": "0.00"},
    )
    assert invalid.status_code == 422, invalid.text
    assert invalid.json()["detail"]["code"] == "ESTIMATE_TARGET_INVALID"

    unchanged_after_invalid = client.get(
        f"/v1/estimate-rounds/{round_id}", headers=_headers()
    ).json()
    assert unchanged_after_invalid["version"] == version
    assert unchanged_after_invalid["target"]["amount"] == total_amount
