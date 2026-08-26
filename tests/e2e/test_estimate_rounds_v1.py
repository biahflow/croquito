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

Desde a F-035 (ADR-0046) a planilha NÃO nasce da montagem, e a cadeia tem três atos:
`POST .../estimate` monta, `POST .../estimate/approve` assina com o papel `aprovador` e
`POST .../estimate/export` despacha com o `orcamentista`. É por isso que este arquivo tem
DOIS subjects e não um: quem montou não assina, e a recusa compara IDENTIDADE — acumular os
dois papéis no mesmo token não contorna.

Toda mutação manda `Idempotency-Key` e o `base_version` corrente. O único acesso direto ao
object store neste arquivo é para reler a planilha PUBLICADA (a URL assinada da fixture não
é buscável por HTTP) e conferir seu digest contra o que a API declarou — e, no teste do
portão de despacho, para provar que uma recusa não escreveu nada.
"""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from decimal import Decimal
from pathlib import Path
from typing import Any, Final, Literal, cast

import pytest
from fastapi.testclient import TestClient
from httpx import Response

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

APPROVER_SUBJECT: Final = "aprovadora-estimate-v1-e2e"
"""Quem ASSINA, e deliberadamente outra pessoa que não a que monta.

A recusa de auto-aprovação compara identidade contra quem montou (ADR-0046, decisão 6), e
uma fixture de subject único não teria como exercer "outra pessoa assina" — provaria a
cadeia com o único token que ela nunca pode aceitar."""

APPROVER_ROLE: Final = "aprovador"
_ANTHROPIC_KEY_ENV: Final = "CROQUITO_ANTHROPIC_API_KEY"

REFERENCE_LABEL: Final = "ORCAMENTO V1 E2E 01/2026"
ADDRESS: Final = "RUA SINTETICA ORCAMENTO V1, S/N"
BDI_PERCENT: Final = "25.00"


def _headers(
    key: str | None = None,
    *,
    tenant: str = TENANT,
    roles: str = ROLE,
    subject: str = SUBJECT,
) -> dict[str, str]:
    """Token sintético de quem MONTA, salvo quando o teste pede outro subject ou papel."""
    headers = {"Authorization": f"Bearer test:{tenant}:{subject}:{roles}"}
    if key is not None:
        headers["Idempotency-Key"] = key
    return headers


def _approve_estimate(
    client: TestClient,
    round_id: str,
    *,
    base_version: int,
    key: str,
    subject: str = APPROVER_SUBJECT,
    roles: str = APPROVER_ROLE,
) -> Response:
    """Assina o orçamento da cabeça: o corpo é SÓ `base_version`, a identidade é do JWT."""
    return cast(
        Response,
        client.post(
            f"/v1/estimate-rounds/{round_id}/estimate/approve",
            headers=_headers(key, roles=roles, subject=subject),
            json={"base_version": base_version},
        ),
    )


def _export_estimate(
    client: TestClient,
    round_id: str,
    *,
    base_version: int,
    key: str,
    subject: str = SUBJECT,
    roles: str = ROLE,
) -> Response:
    """Despacha a planilha: ato do `orcamentista`, atrás do portão de aprovação."""
    return cast(
        Response,
        client.post(
            f"/v1/estimate-rounds/{round_id}/estimate/export",
            headers=_headers(key, roles=roles, subject=subject),
            json={"base_version": base_version},
        ),
    )


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


def _close_packages(
    client: TestClient,
    round_id: str,
    item_ids: Sequence[str],
    *,
    version: int,
    prefix: str,
) -> int:
    """Declara completo o pacote de serviços de cada elemento precificado.

    Confirmar um código deixou de terminar o elemento (ADR-0053): ele pode disparar outros
    serviços, e só o fechamento afirma que não dispara. Sem o ato o orçamento recusaria em
    `ESTIMATE_PACKAGE_NOT_CLOSED`. A rejeição fecha o item sozinha e não passa por aqui.

    Devolve a `base_version` corrente, porque cada fechamento grava a sua revisão.
    """
    for index, item_id in enumerate(item_ids):
        response = client.post(
            f"/v1/estimate-rounds/{round_id}/code-assignments/closures",
            headers=_headers(f"{prefix}-{index}"),
            json={"base_version": version, "item_id": item_id},
        )
        assert response.status_code == 200, response.text
        version = response.json()["version"]
    return version


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

    aberto = client.get(
        f"/v1/estimate-rounds/{round_id}/code-assignments", headers=_headers()
    ).json()
    assert len(aberto["pending_items"]) == len(code_decisions) - 1, (
        "elemento com código confirmado e pacote aberto continua pendente"
    )
    version = _close_packages(
        client,
        round_id,
        [item.item_id for item in code_decisions if item.action == "confirm"],
        version=version,
        prefix="fechamento-pacote",
    )

    assignments_state = client.get(
        f"/v1/estimate-rounds/{round_id}/code-assignments", headers=_headers()
    ).json()
    assert assignments_state["pending_items"] == []
    assert assignments_state["rejected"] == 1  # a luminária: nenhuma fonte a precifica
    assert assignments_state["confirmed"] == len(code_decisions) - 1
    assert assignments_state["closed"] == len(code_decisions)

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

    # 7. `POST .../estimate` com o `base_version` correto: monta — e **só** monta. Desde a
    # F-035 (ADR-0046) a planilha não nasce daqui, e é esse instante — orçamento pronto e
    # ainda sem circular — que a assinatura nominal existe para ocupar.
    built = client.post(
        f"/v1/estimate-rounds/{round_id}/estimate",
        headers=_headers("orcamento-v1-e2e"),
        json={"base_version": version, "bdi_percent": BDI_PERCENT},
    )
    assert built.status_code == 200, built.text
    built_body = built.json()
    version = built_body["version"]
    assert built_body["bdi_percent"] == BDI_PERCENT
    assert built_body["workbook_present"] is False
    assert built_body["approval"]["approved"] is False
    assert built_body["approval"]["stale"] is False
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

    # 7b. Assinar e despachar, os dois atos que a F-035 pôs entre o orçamento montado e a
    # planilha publicada. Quem assina é OUTRA pessoa, com o papel `aprovador`; quem despacha
    # é o orçamentista que montou.
    approved = _approve_estimate(client, round_id, base_version=version, key="assinatura-v1-e2e")
    assert approved.status_code == 200, approved.text
    approved_body = approved.json()
    version = approved_body["version"]
    approval = approved_body["approval"]
    assert approval["approved"] is True
    assert approval["approved_by"] == APPROVER_SUBJECT
    assert approval["stale"] is False
    assert approval["approved_digest"] == approval["current_digest"]
    # Assinar não muda o que foi assinado: o digest do CONTEÚDO é o mesmo da montagem.
    assert approval["current_digest"] == built_body["approval"]["current_digest"]
    assert approved_body["workbook_present"] is False

    exported = _export_estimate(client, round_id, base_version=version, key="despacho-v1-e2e")
    assert exported.status_code == 200, exported.text
    exported_body = exported.json()
    version = exported_body["version"]
    assert exported_body["workbook_present"] is True
    # Despachar não altera o orçamento: o documento gravado é o mesmo que a assinatura
    # produziu, e só a referência do arquivo entra na revisão nova.
    assert exported_body["estimate_sha256"] == approved_body["estimate_sha256"]

    # 8. `GET .../estimate`: auditoria ok, planilha publicada — a URL assinada da fixture
    # não é buscável por HTTP, então a conferência lê o BLOB diretamente do object store,
    # pela mesma chave que a API deriva do digest do CONTEÚDO do orçamento (que exclui a
    # aprovação, e por isso não mudou desde a montagem).
    read = client.get(f"/v1/estimate-rounds/{round_id}/estimate", headers=_headers()).json()
    assert read["estimate_sha256"] == exported_body["estimate_sha256"]
    # A assinatura entra no DOCUMENTO e muda o digest dele; o do conteúdo segue intacto.
    assert read["estimate_sha256"] != built_body["estimate_sha256"]
    assert read["approval"]["current_digest"] == built_body["approval"]["current_digest"]
    assert read["approval"]["stale"] is False
    assert read["workbook_present"] is True
    assert read["workbook_url"] is not None
    for absent_key in ("target", "consumed", "remaining", "over"):
        assert absent_key not in read

    object_key = estimate_workbook_key(
        tenant_id=TENANT,
        round_id=str(round_id),
        estimate_sha256=read["approval"]["current_digest"],
    )
    workbook_bytes = storage.body(object_key)
    assert hashlib.sha256(workbook_bytes).hexdigest() == read["workbook_sha256"]

    workbook_path = tmp_path / "orcamento-publicado.xlsx"
    workbook_path.write_bytes(workbook_bytes)

    # A auditoria compara a planilha com o orçamento MONTADO, e não com o assinado, porque a
    # igualdade dos dois digests de conteúdo acima já provou que são o mesmo conteúdo.
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

    version = _close_packages(
        client,
        round_id,
        [item.item_id for item in code_decisions if item.action == "confirm"],
        version=version,
        prefix="fechamento-pacote-teto",
    )

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


def test_estimate_round_contracted_demand_regime_through_v1_api(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    stack: tuple[TestClient, FakeObjectStore, FakeQueue, str],
) -> None:
    """Regime "demanda sob contrato" (F-033, ADR-0045) pela cadeia REAL `/v1`, critério 5.

    Réplica enxuta de `test_estimate_round_full_chain_through_v1_api` até a planilha
    publicada — mesma prancha sintética, mesmos helpers —, desta vez com
    `pricing_regime=contracted_demand` declarado na CRIAÇÃO da rodada (no molde do
    `target_amount` de `test_estimate_round_target_over_and_exact_limit_through_v1_api`).
    Prova, pela cadeia inteira e não só pela rota isolada (já coberta por
    `tests/api/test_estimate_round_routes.py`): a cascata só aceita `sco`; `emop` recusa na
    INSTALAÇÃO com `409 ESTIMATE_CASCADE_ORIGIN_FORBIDDEN` sem mudar a cascata nem a
    versão da rodada; e a planilha publicada chega com TODA linha de preço citando `sco`
    na coluna FONTE.

    Sob o regime só o catálogo SCO instala, e a MAPÃO sintética
    (`build_synthetic_previous_mapao`) precifica pavimento, alambrado, banco, luminária e
    piso emborrachado — os mesmos cinco códigos do demo de medição, catálogo único
    (`croquito_worker.valuation.synthetic._DEMO_CODE_ASSIGNMENTS`) — mas não o gramado, que
    no orçamento de cascata livre (`estimate_fixture.py`) vem da EMOP ou de composição
    manual. Aqui o gramado fica REJEITADO: candidato a aditivo (ADR-0045, decisão 5), não
    falha de precificação — e é esse rejeitado que prova `amendment_candidates` no bloco do
    regime.
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

    # A única fonte que a rodada sob contrato aceita, e uma fonte proibida (EMOP) para
    # provar a recusa na instalação — nunca chega a entrar na cascata.
    template = default_template()
    previous_mapao_path = build_synthetic_previous_mapao(tmp_path / "previous-mapao-regime.xlsx")
    sco_catalog = read_price_catalog(
        previous_mapao_path,
        template,
        source_label=SYNTHETIC_CONTRACT_SOURCE_LABEL,
        reference_month=SYNTHETIC_REFERENCE_MONTH,
    )
    dbf_path = write_emop_dbf(tmp_path / "emop-sintetico-regime.dbf")
    emop_catalog, _emop_notes = read_emop_catalog_with_report(dbf_path, emop_fixture_layout())

    # 1. `POST /v1/estimate-rounds` JÁ com `pricing_regime=contracted_demand` (ADR-0045)
    # declarado na CRIAÇÃO — no molde do `target_amount` do teste de teto.
    created = client.post(
        "/v1/estimate-rounds",
        headers=_headers("rodada-regime-e2e"),
        json={
            "worksite_key": "praca-sintetica-regime-e2e",
            "worksite_name": SYNTHETIC_ESTIMATE_WORKSITE_NAME,
            "reference_label": "ORCAMENTO V1 REGIME E2E 01/2026",
            "address": ADDRESS,
            "pricing_regime": "contracted_demand",
        },
    )
    assert created.status_code == 201, created.text
    round_id = created.json()["round_id"]
    version = created.json()["version"]

    # 2. O bloco do regime já aparece no estado da rodada, cascata ainda vazia: só `sco` é
    # aceito (ADR-0045, decisão 3), e nenhum candidato a aditivo existe ainda.
    state_after_creation = client.get(f"/v1/estimate-rounds/{round_id}", headers=_headers()).json()
    assert state_after_creation["regime"] == {
        "value": "contracted_demand",
        "allowed_cascade_origins": ["sco"],
        "amendment_candidates": 0,
    }

    # 3. `sco` instala normalmente.
    sco_upload = _presign_and_put(
        client,
        storage,
        filename="catalogo-regime-sco.json",
        content_type="application/json",
        payload=_catalog_upload_bytes(sco_catalog),
        key="presign-catalogo-regime-sco",
    )
    installed = client.post(
        f"/v1/estimate-rounds/{round_id}/catalogs",
        headers=_headers("instala-catalogo-regime-sco"),
        json={"upload_id": sco_upload["upload_id"], "base_version": version},
    )
    assert installed.status_code == 201, installed.text
    version = installed.json()["version"]
    assert [entry["origin"] for entry in installed.json()["cascade"]] == ["sco"]

    # 4. `emop` recusa NA INSTALAÇÃO com `409 ESTIMATE_CASCADE_ORIGIN_FORBIDDEN` (critério 3
    # da feature): a cascata segue com uma fonte só e a versão da rodada não muda.
    emop_upload = _presign_and_put(
        client,
        storage,
        filename="catalogo-regime-emop.json",
        content_type="application/json",
        payload=_catalog_upload_bytes(emop_catalog),
        key="presign-catalogo-regime-emop",
    )
    forbidden = client.post(
        f"/v1/estimate-rounds/{round_id}/catalogs",
        headers=_headers("instala-catalogo-regime-emop"),
        json={"upload_id": emop_upload["upload_id"], "base_version": version},
    )
    assert forbidden.status_code == 409, forbidden.text
    assert forbidden.json()["detail"]["code"] == "ESTIMATE_CASCADE_ORIGIN_FORBIDDEN"
    assert forbidden.json()["detail"]["details"] == {"origin": "emop", "allowed_origins": ["sco"]}

    unchanged = client.get(f"/v1/estimate-rounds/{round_id}", headers=_headers()).json()
    assert unchanged["version"] == version
    assert [entry["origin"] for entry in unchanged["cascade"]] == ["sco"]

    # 5. Segue a cadeia como o teste-molde: prancha, extração paga (via fixture, offline),
    # takeoff e código — só a cascata muda de forma.
    plate_payload = plate.pdf_path.read_bytes()
    plate_upload = _presign_and_put(
        client,
        storage,
        filename="prancha-regime.pdf",
        content_type="application/pdf",
        payload=plate_payload,
        key="presign-prancha-regime",
    )
    associated = client.post(
        f"/v1/estimate-rounds/{round_id}/plate",
        headers=_headers("prancha-associada-regime"),
        json={"upload_id": plate_upload["upload_id"], "base_version": version},
    )
    assert associated.status_code == 200, associated.text
    version = associated.json()["version"]

    extraction = client.post(
        f"/v1/estimate-rounds/{round_id}/plate/extractions",
        headers=_headers("extracao-regime-e2e"),
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

    takeoff = client.get(f"/v1/estimate-rounds/{round_id}/takeoff", headers=_headers()).json()
    assert takeoff["version"] == version
    packet = _packet_from_takeoff_response(takeoff)

    takeoff_decisions = build_demo_takeoff_decisions(packet).decisions
    last_decision_response: dict[str, Any] | None = None
    for index, decision in enumerate(takeoff_decisions):
        response = client.post(
            f"/v1/estimate-rounds/{round_id}/takeoff/decisions",
            headers=_headers(f"decisao-takeoff-regime-{index}"),
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

    # 5b. Confirma código citando SEMPRE `sco` — é a única fonte instalada, e a única que o
    # regime aceitaria. A MAPÃO sintética precifica cinco dos seis itens confirmados no
    # takeoff (a área de intervenção já foi rejeitada NO takeoff, não chega aqui); o
    # gramado — que só a EMOP ou uma composição manual precificam no orçamento livre — fica
    # sem código nela e é REJEITADO: candidato a aditivo, não falha.
    _RegimeCodeDecision = tuple[str, Literal["confirm", "reject"], str | None]
    regime_code_decisions: Final[tuple[_RegimeCodeDecision, ...]] = (
        ("PISO INTERTRAVADO SINTETICO", "confirm", "AD04050060(/)"),
        ("GRAMADO SINTETICO", "reject", None),
        ("ALAMBRADO SINTETICO", "confirm", "CE02100010(/)"),
        ("BANCO DE CONCRETO SINTETICO", "confirm", "MB01100010(/)"),
        ("LUMINARIA DUPLA SINTETICA", "confirm", "MB01300010(/)"),
        ("PISO EMBORRACHADO SINTETICO", "confirm", "AD04150010(/)"),
    )
    lawn_item_id = item_for_label(final_packet, "GRAMADO SINTETICO").id
    for index, (label, action, code) in enumerate(regime_code_decisions):
        response = client.post(
            f"/v1/estimate-rounds/{round_id}/code-assignments/decisions",
            headers=_headers(f"decisao-codigo-regime-{index}"),
            json={
                "base_version": version,
                "item_id": item_for_label(final_packet, label).id,
                "action": action,
                "code": code,
                "catalog_sha256": None if code is None else sco_catalog.source_sha256,
                "note": (
                    "sem código na tabela contratual; candidato a aditivo sob o regime "
                    "(ADR-0045, decisão 5)"
                    if code is None
                    else "precificado pela tabela contratual (SCO)"
                ),
            },
        )
        assert response.status_code == 200, response.text
        version = response.json()["version"]

    version = _close_packages(
        client,
        round_id,
        [
            item_for_label(final_packet, label).id
            for label, action, _ in regime_code_decisions
            if action == "confirm"
        ],
        version=version,
        prefix="fechamento-pacote-regime",
    )

    assignments_state = client.get(
        f"/v1/estimate-rounds/{round_id}/code-assignments", headers=_headers()
    ).json()
    assert assignments_state["pending_items"] == []
    assert assignments_state["rejected"] == 1  # o gramado: candidato a aditivo
    assert assignments_state["confirmed"] == len(regime_code_decisions) - 1

    # O bloco do regime lê o mesmo rejeitado como candidato a aditivo (ADR-0045, decisão 5).
    round_after_codes = client.get(f"/v1/estimate-rounds/{round_id}", headers=_headers()).json()
    assert round_after_codes["regime"]["amendment_candidates"] == 1

    # 6. `POST .../estimate`: BDI declarado RECUSA sob o regime (F-036, ADR-0048 decisão 3).
    # O preço da tabela contratual já embute o BDI, e aplicá-lo de novo é o erro de domínio
    # que o ADR-0038 nomeou ao manter o BDI fora da medição. Até a F-036 este e2e montava com
    # 25% sobre preço que já os continha, e o total saía inflado.
    recusado = client.post(
        f"/v1/estimate-rounds/{round_id}/estimate",
        headers=_headers("orcamento-regime-bdi-e2e"),
        json={"base_version": version, "bdi_percent": BDI_PERCENT},
    )
    assert recusado.status_code == 422, recusado.text
    assert recusado.json()["code"] == "ESTIMATE_BDI_FORBIDDEN_UNDER_REGIME"

    # Omitindo o BDI a cadeia segue igual, e é o caminho normal sob o regime: as cinco linhas
    # de preço vêm todas do SCO, e o gramado sai como único item sem preço (critério central
    # desta feature). A planilha ainda não existe: desde a F-035 ela só nasce do despacho,
    # depois da assinatura.
    built = client.post(
        f"/v1/estimate-rounds/{round_id}/estimate",
        headers=_headers("orcamento-regime-e2e"),
        json={"base_version": version},
    )
    assert built.status_code == 200, built.text
    built_body = built.json()
    version = built_body["version"]
    assert built_body["workbook_present"] is False
    assert built_body["approval"]["approved"] is False

    estimate = Estimate.model_validate(built_body["estimate"])
    assert len(estimate.lines) == len(regime_code_decisions) - 1
    assert all(line.price_origin == PriceOrigin.SCO for line in estimate.lines)
    assert estimate.unpriced_item_ids == [lawn_item_id]

    # 6b. Assina com o papel `aprovador` (outra pessoa) e despacha com o `orcamentista`: o
    # regime não muda a cadeia de aprovação, e a cadeia de aprovação não muda o regime.
    approved = _approve_estimate(
        client, round_id, base_version=version, key="assinatura-regime-e2e"
    )
    assert approved.status_code == 200, approved.text
    approved_body = approved.json()
    version = approved_body["version"]
    assert approved_body["approval"]["approved_by"] == APPROVER_SUBJECT
    assert approved_body["approval"]["stale"] is False

    exported = _export_estimate(client, round_id, base_version=version, key="despacho-regime-e2e")
    assert exported.status_code == 200, exported.text
    exported_body = exported.json()
    version = exported_body["version"]
    assert exported_body["workbook_present"] is True

    # 7. `GET .../estimate`: lê o BLOB publicado do object store (a URL assinada da fixture
    # não é buscável por HTTP) e confere a planilha canônica — TODA linha de preço cita
    # `sco` na coluna FONTE (critério 5 da feature: a cadeia inteira sob o regime chega à
    # planilha citando só a tabela contratual).
    read = client.get(f"/v1/estimate-rounds/{round_id}/estimate", headers=_headers()).json()
    assert read["estimate_sha256"] == exported_body["estimate_sha256"]
    assert read["approval"]["current_digest"] == built_body["approval"]["current_digest"]

    object_key = estimate_workbook_key(
        tenant_id=TENANT,
        round_id=str(round_id),
        estimate_sha256=read["approval"]["current_digest"],
    )
    workbook_bytes = storage.body(object_key)
    assert hashlib.sha256(workbook_bytes).hexdigest() == read["workbook_sha256"]

    workbook_path = tmp_path / "orcamento-regime-publicado.xlsx"
    workbook_path.write_bytes(workbook_bytes)

    audit = audit_estimate_workbook(workbook_path, estimate, template)
    assert audit.status == "ok"
    assert audit.findings == []

    # 8. F-036: a medição nasce do orçamento ASSINADO, e é aqui que a cadeia inteira fecha —
    # o documento que desce para a empresa passa a ser o contratado contra o qual a obra é
    # medida. Obra e endereço vêm do conteúdo assinado; declará-los aqui recusa.
    medicao = client.post(
        "/v1/valuation-rounds",
        headers=_headers("medicao-do-orcamento-e2e"),
        json={
            "estimate_round_id": str(round_id),
            "reference_label": "Medição 1 — e2e",
            "period_number": 1,
        },
    )
    assert medicao.status_code == 201, medicao.text

    estado = client.get(
        f"/v1/valuation-rounds/{medicao.json()['round_id']}",
        headers=_headers("estado-medicao-e2e"),
    )
    assert estado.status_code == 200, estado.text
    contratado = estado.json()["contracted"]
    assert contratado["origin"] == "signed_estimate"
    assert contratado["estimate_round_id"] == str(round_id)
    # O digest é o do conteúdo assinado, e é ele que responde "medi contra o quê".
    assert contratado["estimate_digest"] == read["approval"]["current_digest"]
    assert contratado["code_count"] == len(estimate.lines)

    layout = template.estimate
    assert layout is not None
    columns = layout.columns
    canonical = canonicalize_workbook(workbook_path, template)
    cells = _canonical_cells(canonical, layout.sheet_name)

    header_row = layout.header_row
    for offset in range(len(estimate.lines)):
        row = header_row + 1 + offset
        source_cell = cells[f"{columns.source.letter}{row}"]["value"]
        assert isinstance(source_cell, str), row
        assert "SCO" in source_cell, row


def test_estimate_dispatch_gate_through_v1_api(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    stack: tuple[TestClient, FakeObjectStore, FakeQueue, str],
) -> None:
    """O portão do despacho pela cadeia REAL `/v1` (F-035, ADR-0046), com DOIS tokens.

    Réplica enxuta de `test_estimate_round_full_chain_through_v1_api` até o orçamento
    montado — sem repetir as asserções de cascata e de planilha que aquele teste já faz —,
    desta vez para provar o que só a cadeia inteira prova, e a rota isolada em
    `tests/api/test_estimate_round_routes.py` não vê:

    1. despachar sem assinatura recusa e **nada é escrito** — conferido no object store, não
       no código de status: um portão que recusa depois de gravar já publicou;
    2. assinar e despachar são atos de papéis diferentes, exercidos aqui com tokens
       diferentes na MESMA cadeia — e nem acumular os dois papéis deixa quem montou assinar,
       porque a comparação é de identidade;
    3. remontar depois de assinado leva a assinatura adiante CADUCA, e o despacho recusa com
       `APPROVAL_CONTENT_MISMATCH` até um ato novo de aprovação.

    Como o teste-molde, a extração paga entra pelo `legend_fixture_adapter` sobre a mesma
    prancha sintética: nada aqui sai do processo.
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
    previous_mapao_path = build_synthetic_previous_mapao(tmp_path / "previous-mapao-portao.xlsx")
    sco_catalog = read_price_catalog(
        previous_mapao_path,
        template,
        source_label=SYNTHETIC_CONTRACT_SOURCE_LABEL,
        reference_month=SYNTHETIC_REFERENCE_MONTH,
    )
    dbf_path = write_emop_dbf(tmp_path / "emop-sintetico-portao.dbf")
    emop_catalog, _emop_notes = read_emop_catalog_with_report(dbf_path, emop_fixture_layout())
    composition_set = build_synthetic_composition_set()
    composition_catalog = compile_compositions(
        composition_set,
        source_sha256=hashlib.sha256(composition_set.model_dump_json().encode("utf-8")).hexdigest(),
    )
    cascade = (sco_catalog, emop_catalog, composition_catalog)

    # 1. Rodada, cascata de três fontes, prancha e extração — o trecho da cadeia que este
    # teste precisa ter percorrido para chegar ao orçamento montado.
    created = client.post(
        "/v1/estimate-rounds",
        headers=_headers("rodada-portao-e2e"),
        json={
            "worksite_key": "praca-sintetica-portao-e2e",
            "worksite_name": SYNTHETIC_ESTIMATE_WORKSITE_NAME,
            "reference_label": "ORCAMENTO V1 PORTAO E2E 01/2026",
            "address": ADDRESS,
        },
    )
    assert created.status_code == 201, created.text
    round_id = created.json()["round_id"]
    version = created.json()["version"]

    for index, catalog in enumerate(cascade):
        upload = _presign_and_put(
            client,
            storage,
            filename=f"catalogo-portao-{catalog.origin.value}.json",
            content_type="application/json",
            payload=_catalog_upload_bytes(catalog),
            key=f"presign-catalogo-portao-{index}",
        )
        installed = client.post(
            f"/v1/estimate-rounds/{round_id}/catalogs",
            headers=_headers(f"instala-catalogo-portao-{index}"),
            json={"upload_id": upload["upload_id"], "base_version": version},
        )
        assert installed.status_code == 201, installed.text
        version = installed.json()["version"]

    plate_upload = _presign_and_put(
        client,
        storage,
        filename="prancha-portao.pdf",
        content_type="application/pdf",
        payload=plate.pdf_path.read_bytes(),
        key="presign-prancha-portao",
    )
    associated = client.post(
        f"/v1/estimate-rounds/{round_id}/plate",
        headers=_headers("prancha-associada-portao"),
        json={"upload_id": plate_upload["upload_id"], "base_version": version},
    )
    assert associated.status_code == 200, associated.text
    version = associated.json()["version"]

    extraction = client.post(
        f"/v1/estimate-rounds/{round_id}/plate/extractions",
        headers=_headers("extracao-portao-e2e"),
        json={"base_version": version},
    )
    assert extraction.status_code == 202, extraction.text

    assert _drain(worker) == 1

    round_after_extraction = client.get(
        f"/v1/estimate-rounds/{round_id}", headers=_headers()
    ).json()
    assert round_after_extraction["extraction"]["status"] == "done"
    version = round_after_extraction["version"]
    # Sem orçamento na cabeça, o bloco de aprovação nem aparece: ausência não é um valor.
    assert "approval" not in round_after_extraction

    # 2. Takeoff revisado e código decidido, pelos mesmos helpers do teste-molde.
    takeoff = client.get(f"/v1/estimate-rounds/{round_id}/takeoff", headers=_headers()).json()
    packet = _packet_from_takeoff_response(takeoff)

    takeoff_decisions = build_demo_takeoff_decisions(packet).decisions
    for index, decision in enumerate(takeoff_decisions):
        response = client.post(
            f"/v1/estimate-rounds/{round_id}/takeoff/decisions",
            headers=_headers(f"decisao-takeoff-portao-{index}"),
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
        version = response.json()["version"]

    assert _drain(worker) == len(takeoff_decisions)

    final_takeoff = client.get(f"/v1/estimate-rounds/{round_id}/takeoff", headers=_headers()).json()
    final_packet = _packet_from_takeoff_response(final_takeoff)

    gate_decisions = build_demo_estimate_assignments(final_packet, list(cascade)).assignments
    for index, assignment in enumerate(gate_decisions):
        response = client.post(
            f"/v1/estimate-rounds/{round_id}/code-assignments/decisions",
            headers=_headers(f"decisao-codigo-portao-{index}"),
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

    version = _close_packages(
        client,
        round_id,
        [item.item_id for item in gate_decisions if item.action == "confirm"],
        version=version,
        prefix="fechamento-pacote-portao",
    )

    # 3. Monta. A partir daqui o teste é só sobre o portão, e o object store é a testemunha:
    # tudo o que for recusado tem de deixá-lo exatamente como está agora.
    built = client.post(
        f"/v1/estimate-rounds/{round_id}/estimate",
        headers=_headers("orcamento-portao-e2e"),
        json={"base_version": version, "bdi_percent": BDI_PERCENT},
    )
    assert built.status_code == 200, built.text
    version = built.json()["version"]
    assert built.json()["workbook_present"] is False
    objects_after_build = set(storage.objects)

    # 4. Despachar sem assinatura recusa pelo portão do DOMÍNIO — e nada é escrito.
    unsigned = _export_estimate(
        client, round_id, base_version=version, key="despacho-sem-assinatura"
    )
    assert unsigned.status_code == 422, unsigned.text
    detail = unsigned.json()["detail"]
    assert detail["code"] == "DOMAIN_VALIDATION_FAILED"
    assert detail["details"]["code"] == "ESTIMATE_EXPORT_BLOCKED"
    assert detail["details"]["errors"] == ["ESTIMATE_NOT_APPROVED"]
    assert set(storage.objects) == objects_after_build
    after_refusal = client.get(f"/v1/estimate-rounds/{round_id}", headers=_headers()).json()
    assert after_refusal["version"] == version
    assert after_refusal["approval"]["approved"] is False
    assert after_refusal["estimate"]["workbook_present"] is False

    # 5. Assinar é do papel `aprovador`, e é de OUTRA pessoa. O token que montou recusa duas
    # vezes, por dois motivos diferentes: sem o papel, é `403 FORBIDDEN`; com os dois papéis,
    # é a segregação por identidade que recusa (ADR-0046, decisão 6).
    without_role = _approve_estimate(
        client,
        round_id,
        base_version=version,
        key="assinatura-sem-papel",
        subject=SUBJECT,
        roles=ROLE,
    )
    assert without_role.status_code == 403, without_role.text
    assert without_role.json()["detail"]["code"] == "FORBIDDEN"

    self_approval = _approve_estimate(
        client,
        round_id,
        base_version=version,
        key="auto-aprovacao",
        subject=SUBJECT,
        roles=f"{ROLE},{APPROVER_ROLE}",
    )
    assert self_approval.status_code == 403, self_approval.text
    assert self_approval.json()["detail"]["code"] == "ESTIMATE_SELF_APPROVAL_FORBIDDEN"
    # A recusa não devolve quem montou: seria um diretório de usuários do tenant.
    assert SUBJECT not in self_approval.text

    approved = _approve_estimate(client, round_id, base_version=version, key="assinatura-portao")
    assert approved.status_code == 200, approved.text
    version = approved.json()["version"]
    approval = approved.json()["approval"]
    assert approval["approved"] is True
    assert approval["approved_by"] == APPROVER_SUBJECT
    assert approval["stale"] is False
    assert set(storage.objects) == objects_after_build  # assinar também não publica nada

    # 6. Despachar é do `orcamentista`: o token que assinou não despacha.
    wrong_dispatcher = _export_estimate(
        client,
        round_id,
        base_version=version,
        key="despacho-do-aprovador",
        subject=APPROVER_SUBJECT,
        roles=APPROVER_ROLE,
    )
    assert wrong_dispatcher.status_code == 403, wrong_dispatcher.text
    assert wrong_dispatcher.json()["detail"]["code"] == "FORBIDDEN"
    assert set(storage.objects) == objects_after_build

    dispatched = _export_estimate(client, round_id, base_version=version, key="despacho-portao")
    assert dispatched.status_code == 200, dispatched.text
    version = dispatched.json()["version"]
    assert dispatched.json()["workbook_present"] is True

    published_key = estimate_workbook_key(
        tenant_id=TENANT, round_id=str(round_id), estimate_sha256=approval["current_digest"]
    )
    assert set(storage.objects) - objects_after_build == {published_key}
    assert (
        hashlib.sha256(storage.body(published_key)).hexdigest()
        == dispatched.json()["workbook_sha256"]
    )

    # 7. A caducidade pela cadeia: remontar com outro BDI leva a assinatura adiante, agora
    # apontando para o conteúdo antigo — e o despacho recusa até um ato novo. Preservar não é
    # aprovar: é o que mantém visível que alguém assinou algo que mudou depois.
    objects_after_dispatch = set(storage.objects)
    rebuilt = client.post(
        f"/v1/estimate-rounds/{round_id}/estimate",
        headers=_headers("remontagem-portao"),
        json={"base_version": version, "bdi_percent": "30.00"},
    )
    assert rebuilt.status_code == 200, rebuilt.text
    version = rebuilt.json()["version"]
    stale_approval = rebuilt.json()["approval"]
    assert stale_approval["approved"] is True
    assert stale_approval["stale"] is True
    assert stale_approval["approved_by"] == APPROVER_SUBJECT
    assert stale_approval["approved_digest"] == approval["approved_digest"]
    assert stale_approval["current_digest"] != approval["current_digest"]

    stale_dispatch = _export_estimate(client, round_id, base_version=version, key="despacho-caduco")
    assert stale_dispatch.status_code == 422, stale_dispatch.text
    assert stale_dispatch.json()["detail"]["details"]["errors"] == ["APPROVAL_CONTENT_MISMATCH"]
    assert set(storage.objects) == objects_after_dispatch

    state_while_stale = client.get(f"/v1/estimate-rounds/{round_id}", headers=_headers()).json()
    assert state_while_stale["approval"]["stale"] is True
    assert state_while_stale["version"] == version

    # 8. O ato novo destrava, e a planilha nova mora noutro endereço: cada revisão continua
    # apontando para o arquivo do conteúdo que ela publicou.
    approved_again = _approve_estimate(
        client, round_id, base_version=version, key="assinatura-portao-2"
    )
    assert approved_again.status_code == 200, approved_again.text
    version = approved_again.json()["version"]
    assert approved_again.json()["approval"]["stale"] is False

    dispatched_again = _export_estimate(
        client, round_id, base_version=version, key="despacho-portao-2"
    )
    assert dispatched_again.status_code == 200, dispatched_again.text
    assert dispatched_again.json()["workbook_present"] is True

    republished_key = estimate_workbook_key(
        tenant_id=TENANT,
        round_id=str(round_id),
        estimate_sha256=stale_approval["current_digest"],
    )
    assert set(storage.objects) - objects_after_dispatch == {republished_key}
    assert republished_key != published_key

    final_read = client.get(f"/v1/estimate-rounds/{round_id}/estimate", headers=_headers()).json()
    assert final_read["approval"]["stale"] is False
    assert final_read["workbook_url"] is not None
