"""Cadeia completa da medição de obra, ponta a ponta, pela API `/v1` autenticada (F-003 T13).

Contraponto de `tests/e2e/test_valuation_full_chain.py`: aquele arquivo prova que a cadeia
de medição fecha pelos comandos do CLI, lendo e gravando artefato em disco. Este arquivo
prova a MESMA cadeia de negócio — mesma fixture sintética, mesmas decisões do orçamentista
sintético (`croquito_worker.valuation.synthetic`) — pela superfície nova: upload assinado,
rotas HTTP autenticadas de `/v1/valuation-rounds` e o worker consumindo a fila no mesmo
processo (`LocalQueueWorker.dispatch`). Nenhum dos dois arquivos é alterado pelo outro; a
prova aqui é que a SUPERFÍCIE mudou e o produto não.

Nenhuma chamada paga acontece: a extração da legenda entra pelo mesmo seam de fixture que
`tests/worker/test_valuation_extraction_worker.py` usa (`valuation_extraction_adapter`
injetado no `LocalQueueWorker`), com `legend_fixture_adapter` construído sobre a MESMA
prancha sintética (`croquito_worker.valuation.plate.render_synthetic_plate`) que alimenta o
worker. O portão de ambiente da rota (`CROQUITO_AI_MAX_ESTIMATED_COST_USD` +
`CROQUITO_ANTHROPIC_API_KEY`) precisa estar declarado para a rota aceitar o pedido de
extração — é um freio de config, não uma chamada de rede — e é isso, e só isso, que o
`monkeypatch` do teste declara.

Toda mutação manda `Idempotency-Key` e o `base_version` corrente, como um cliente real
faria: a concorrência otimista da rodada nunca é driblada lendo a versão do banco. O único
acesso ao banco neste arquivo é de CONFERÊNCIA (nenhuma etapa avança por escrita direta).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any, Final, cast

import pytest
from fastapi.testclient import TestClient

from croquito_api.config import ApiSettings
from croquito_api.database import Database
from croquito_api.main import create_app
from croquito_valuation.models import PriceCatalog, PriceCatalogEntry, Valuation
from croquito_valuation.rounding import money_trunc
from croquito_valuation.takeoff import TakeoffPacket
from croquito_worker.local_queue import LocalQueueWorker, LocalWorkerSettings
from croquito_worker.valuation.legend_fixtures import legend_fixture_adapter
from croquito_worker.valuation.plate import SYNTHETIC_LEGEND_ROWS, render_synthetic_plate
from croquito_worker.valuation.round_extraction import AI_BUDGET_ENV
from croquito_worker.valuation.synthetic import (
    DEMO_EXPECTED_CODE_BY_LABEL,
    build_demo_code_assignments,
    build_demo_takeoff_decisions,
    item_for_label,
)
from tests.fakes import FakeObjectStore, FakeQueue

TENANT: Final = "tenant-medicao-v1-e2e"
QUEUE_URL: Final = "http://localstack/queue"
SUBJECT: Final = "orcamentista-v1-e2e"
ROLE: Final = "orcamentista"
_ANTHROPIC_KEY_ENV: Final = "CROQUITO_ANTHROPIC_API_KEY"

WORKSITE_KEY: Final = "praca-v1-e2e-norte"
WORKSITE_NAME: Final = "PRACA V1 E2E NORTE"
REFERENCE_LABEL: Final = "MEDICAO V1 E2E 01/2026"
PERIOD_NUMBER: Final = 1
ADDRESS: Final = "RUA SINTETICA V1, S/N"
CONTRACT_LABEL: Final = "CONTRATO SINTETICO V1 E2E 01/2026"

_LAWN_REJECTION_NOTE = "sem cotação aplicável no contrato sintético"
"""Mesma justificativa que `build_demo_code_assignments` grava na rejeição do gramado —
citada aqui só para a asserção final do dossiê, nunca reconstruída à mão."""

_LABELS = SYNTHETIC_LEGEND_ROWS
_PAVEMENT_LABEL = _LABELS[0].label
_LAWN_LABEL = _LABELS[1].label
_FENCE_LABEL = _LABELS[2].label
_BENCH_LABEL = _LABELS[3].label
_LAMP_LABEL = _LABELS[4].label
_RUBBER_LABEL = _LABELS[6].label

_CATALOG_UNIT_PRICE: dict[str, tuple[str, Decimal]] = {
    DEMO_EXPECTED_CODE_BY_LABEL[_PAVEMENT_LABEL]: ("M2", Decimal("100.00")),
    DEMO_EXPECTED_CODE_BY_LABEL[_FENCE_LABEL]: ("M2", Decimal("50.00")),
    DEMO_EXPECTED_CODE_BY_LABEL[_BENCH_LABEL]: ("UN", Decimal("500.00")),
    DEMO_EXPECTED_CODE_BY_LABEL[_LAMP_LABEL]: ("UN", Decimal("1000.00")),
    DEMO_EXPECTED_CODE_BY_LABEL[_RUBBER_LABEL]: ("M2", Decimal("200.00")),
}
"""Catálogo sintético do teste: só os 5 códigos que `build_demo_code_assignments` confirma,
com a unidade que casa com o item (nenhuma nota de incompatibilidade é necessária) e um
preço arbitrário — este teste não reusa o MAPÃO sintético do M2, é um catálogo próprio."""

_LABEL_BY_CODE = {code: label for label, code in DEMO_EXPECTED_CODE_BY_LABEL.items()}


def _headers(key: str | None = None, *, tenant: str = TENANT, roles: str = ROLE) -> dict[str, str]:
    headers = {"Authorization": f"Bearer test:{tenant}:{SUBJECT}:{roles}"}
    if key is not None:
        headers["Idempotency-Key"] = key
    return headers


def _catalog_bytes() -> bytes:
    catalog = PriceCatalog(
        source_label="CATALOGO SINTETICO V1 E2E",
        reference_month="2026-01",
        source_sha256="c" * 64,
        entries=[
            PriceCatalogEntry(
                code=code,
                description=f"{_LABEL_BY_CODE[code]} V1 E2E",
                unit=unit,
                unit_price=price,
                family_code=code[:2],
                family_name="FAMILIA SINTETICA V1 E2E",
                subgroup_code=code[:6],
                subgroup_name="SUBGRUPO SINTETICO V1 E2E",
            )
            for code, (unit, price) in _CATALOG_UNIT_PRICE.items()
        ],
    )
    return catalog.model_dump_json().encode("utf-8")


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
    """Consome toda a fila corrente; comandos de overlay superados pelo pacote são
    descartados em silêncio pelo próprio worker (ADR-0030), não por este helper."""
    processed = 0
    while worker.run_once():
        processed += 1
    return processed


@pytest.fixture
def stack(
    tmp_path: Path,
) -> tuple[TestClient, FakeObjectStore, FakeQueue, str]:
    """API sobre SQLite em arquivo + storage/fila em memória compartilhados com o worker.

    O worker não nasce aqui: ele só pode ser construído depois que a prancha sintética foi
    renderizada, porque o adapter fixture da extração é amarrado ao gabarito daquela
    prancha (`legend_fixture_adapter`).
    """
    database_url = f"sqlite+pysqlite:///{tmp_path / 'valuation-v1-chain.db'}"
    database = Database(database_url)
    database.create_schema()
    settings = ApiSettings(
        database_url=database_url,
        artifact_bucket="croquito-v1-e2e",
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


@dataclass(frozen=True, slots=True)
class _ChainThroughCalc:
    """Estado da rodada logo depois do boletim construído e servido (fim do step 9).

    Devolvido por `_build_round_through_calc` para as duas continuações que partem do
    MESMO boletim construído pela MESMA cadeia real: o final feliz original (dossiê +
    estado final) e a aprovação/exportação da F-028 (T3).
    """

    client: TestClient
    storage: FakeObjectStore
    round_id: str
    version: int
    final_packet: TakeoffPacket
    final_takeoff: dict[str, Any]


def _build_round_through_calc(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    stack: tuple[TestClient, FakeObjectStore, FakeQueue, str],
) -> _ChainThroughCalc:
    """Cadeia real até o boletim construído e servido pela rota (steps 0-9 do e2e).

    Extraído de `test_valuation_round_full_chain_through_v1_api` (F-028 T3) para ser
    reusado pela aprovação/exportação nominal: as duas cenas partem do MESMO boletim
    construído pela MESMA cadeia real — presign, extração via worker, decisões de
    takeoff e de código, `/calc` — e nenhuma delas escreve o artefato direto no banco.
    """
    client, storage, queue, database_url = stack

    # 0. Prancha sintética gerada agora, e o adapter fixture amarrado a ela: nenhuma
    # chamada externa acontece, mas a extração ainda precisa do freio de ambiente
    # declarado (teto de gasto + credencial) para a ROTA aceitar o pedido (F-003 achado
    # do próprio ADR-0028): é config, não rede.
    plate = render_synthetic_plate(tmp_path / "plate-source")
    monkeypatch.setenv(AI_BUDGET_ENV, "1.50")
    monkeypatch.setenv(_ANTHROPIC_KEY_ENV, "chave-de-teste-nunca-usada")
    worker = LocalQueueWorker(
        LocalWorkerSettings(
            database_url=database_url,
            queue_url=QUEUE_URL,
            aws_region="sa-east-1",
            aws_endpoint_url="http://localhost:4566",
            artifact_bucket="croquito-v1-e2e",
        ),
        valuation_extraction_adapter=legend_fixture_adapter(plate),
    )
    worker.client = queue
    worker.s3_client = storage

    # 1. Presign + PUT do catálogo sintético, e a rodada nasce com ele instalado.
    catalog_payload = _catalog_bytes()
    catalog_upload = _presign_and_put(
        client,
        storage,
        filename="catalogo.json",
        content_type="application/json",
        payload=catalog_payload,
        key="presign-catalogo",
    )
    created = client.post(
        "/v1/valuation-rounds",
        headers=_headers("rodada-v1-e2e"),
        json={
            "worksite_key": WORKSITE_KEY,
            "worksite_name": WORKSITE_NAME,
            "catalog_upload_id": catalog_upload["upload_id"],
            "reference_label": REFERENCE_LABEL,
            "period_number": PERIOD_NUMBER,
            "address": ADDRESS,
            "contract_label": CONTRACT_LABEL,
        },
    )
    assert created.status_code == 201, created.text
    round_id = created.json()["round_id"]
    assert created.json()["version"] == 1
    version = 1

    # 2. Presign + PUT da prancha sintética, e a associação à rodada.
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
        f"/v1/valuation-rounds/{round_id}/plate",
        headers=_headers("prancha-associada"),
        json={"upload_id": plate_upload["upload_id"], "base_version": version},
    )
    assert associated.status_code == 200, associated.text
    version = associated.json()["version"]
    assert version == 2

    # 3. A extração paga cai na fila; o worker a consome no MESMO teste, com o adapter
    # fixture — nenhum provider real é chamado.
    extraction = client.post(
        f"/v1/valuation-rounds/{round_id}/plate/extractions",
        headers=_headers("extracao-v1-e2e"),
        json={"base_version": version},
    )
    assert extraction.status_code == 202, extraction.text
    assert extraction.json()["status"] == "queued"
    version = extraction.json()["version"]
    assert version == 3
    assert queue.commands() == []  # nada consumido ainda: só publicado

    assert _drain(worker) == 1
    assert queue.commands() == ["extract_valuation_plate"]

    round_after_extraction = client.get(
        f"/v1/valuation-rounds/{round_id}", headers=_headers()
    ).json()
    assert round_after_extraction["extraction"]["status"] == "done"
    version = round_after_extraction["version"]
    assert version == 4

    # 4. `GET .../takeoff` e `GET .../takeoff/overlay`: URL assinada, e o overlay
    # recém-publicado não está vencido.
    takeoff = client.get(f"/v1/valuation-rounds/{round_id}/takeoff", headers=_headers()).json()
    assert takeoff["version"] == version
    assert takeoff["items"] == len(SYNTHETIC_LEGEND_ROWS)
    assert takeoff["review_status"] == "review_required"
    packet = _packet_from_takeoff_response(takeoff)

    overlay = client.get(
        f"/v1/valuation-rounds/{round_id}/takeoff/overlay", headers=_headers()
    ).json()
    assert overlay["stale"] is False
    assert overlay["packet_sha256"] == takeoff["packet_sha256"]

    # 5. Uma decisão de takeoff por item, até a revisão ficar completa. Cada POST é o ato
    # humano que avança a rodada, e o overlay fica vencido até o worker redesenhá-lo
    # (ADR-0030) — a última decisão é a que o teste confere isso.
    takeoff_decisions = build_demo_takeoff_decisions(packet).decisions
    last_decision_response: dict[str, Any] | None = None
    for index, decision in enumerate(takeoff_decisions):
        response = client.post(
            f"/v1/valuation-rounds/{round_id}/takeoff/decisions",
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
    # O overlay é consequência da decisão, não parte dela: ele ainda declara o pacote
    # anterior até o worker consumir o comando de re-render.
    assert last_decision_response["overlay"]["stale"] is True

    assert _drain(worker) == len(takeoff_decisions)
    assert queue.commands().count("rerender_takeoff_overlay") == len(takeoff_decisions)

    overlay_after_decisions = client.get(
        f"/v1/valuation-rounds/{round_id}/takeoff/overlay", headers=_headers()
    ).json()
    assert overlay_after_decisions["stale"] is False
    assert overlay_after_decisions["packet_sha256"] == last_decision_response["packet_sha256"]

    final_takeoff = client.get(
        f"/v1/valuation-rounds/{round_id}/takeoff", headers=_headers()
    ).json()
    assert final_takeoff["confirmed"] == len(SYNTHETIC_LEGEND_ROWS) - 1  # a intervenção rejeita
    assert final_takeoff["rejected"] == 1
    final_packet = _packet_from_takeoff_response(final_takeoff)

    # 6. `GET .../code-suggestions`: shortlist calculada e persistida, sem avançar a
    # versão da rodada — o `GET` não é ato humano.
    suggestions = client.get(
        f"/v1/valuation-rounds/{round_id}/code-suggestions", headers=_headers()
    ).json()
    assert suggestions["computed"] is True
    assert suggestions["version"] == version
    round_after_suggestions = client.get(
        f"/v1/valuation-rounds/{round_id}", headers=_headers()
    ).json()
    assert round_after_suggestions["version"] == version

    # 7. Busca léxica no catálogo instalado.
    search = client.get(
        f"/v1/valuation-rounds/{round_id}/catalog/search?q=alambrado&limit=5",
        headers=_headers(),
    )
    assert search.status_code == 200, search.text
    search_body = search.json()
    assert search_body["matching"] == "lexical"
    assert DEMO_EXPECTED_CODE_BY_LABEL[_FENCE_LABEL] in [
        result["code"] for result in search_body["results"]
    ]

    # 8. Decisão de código por item confirmado, até nenhum ficar pendente — com pelo
    # menos uma rejeição justificada (o gramado, sem cotação aplicável).
    code_decisions = build_demo_code_assignments(packet).assignments
    lawn_note: str | None = None
    for index, assignment in enumerate(code_decisions):
        response = client.post(
            f"/v1/valuation-rounds/{round_id}/code-assignments/decisions",
            headers=_headers(f"decisao-codigo-{index}"),
            json={
                "base_version": version,
                "item_id": assignment.item_id,
                "action": assignment.action,
                "code": assignment.code,
                "note": assignment.note,
            },
        )
        assert response.status_code == 200, response.text
        version = response.json()["version"]
        if assignment.code is None:
            lawn_note = assignment.note
    assert lawn_note == _LAWN_REJECTION_NOTE

    assignments_state = client.get(
        f"/v1/valuation-rounds/{round_id}/code-assignments", headers=_headers()
    ).json()
    assert assignments_state["pending_items"] == []
    assert assignments_state["confirmed"] == len(_CATALOG_UNIT_PRICE)
    assert assignments_state["rejected"] == 1

    # Quantidades e unidades FINAIS lidas da API — nunca supostas — para calcular o
    # boletim esperado sem repetir a lógica do domínio.
    expected_line_totals: dict[str, Decimal] = {}
    for code, (_unit, price) in _CATALOG_UNIT_PRICE.items():
        item = item_for_label(final_packet, _LABEL_BY_CODE[code])
        assert item.quantity is not None
        expected_line_totals[code] = money_trunc(item.quantity * price)
    expected_total = sum(expected_line_totals.values(), Decimal("0.00"))

    # 9. `POST .../calc` → `GET .../bulletin`: totais recomputados na leitura batem com
    # o que foi construído.
    calc = client.post(
        f"/v1/valuation-rounds/{round_id}/calc",
        headers=_headers("boletim-v1-e2e"),
        json={"base_version": version},
    )
    assert calc.status_code == 200, calc.text
    calc_body = calc.json()
    version = calc_body["version"]
    assert calc_body["total_amount"] == str(expected_total)
    lines_by_code = {line["code"]: line for line in calc_body["valuation"]["bulletins"][0]["lines"]}
    assert set(lines_by_code) == set(expected_line_totals)
    for code, expected_amount in expected_line_totals.items():
        assert Decimal(lines_by_code[code]["total"]) == expected_amount

    bulletin = client.get(f"/v1/valuation-rounds/{round_id}/bulletin", headers=_headers()).json()
    assert bulletin["total_amount"] == calc_body["total_amount"]
    assert bulletin["valuation_sha256"] == calc_body["valuation_sha256"]

    return _ChainThroughCalc(
        client=client,
        storage=storage,
        round_id=round_id,
        version=version,
        final_packet=final_packet,
        final_takeoff=final_takeoff,
    )


def test_valuation_round_full_chain_through_v1_api(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    stack: tuple[TestClient, FakeObjectStore, FakeQueue, str],
) -> None:
    chain = _build_round_through_calc(tmp_path, monkeypatch, stack)
    client = chain.client
    round_id = chain.round_id
    version = chain.version
    final_packet = chain.final_packet
    final_takeoff = chain.final_takeoff

    # 10. `POST .../amendment-dossier` → `GET .../amendment-dossier`: o item rejeitado
    # aparece, sem nenhum campo de preço.
    dossier = client.post(
        f"/v1/valuation-rounds/{round_id}/amendment-dossier",
        headers=_headers("dossie-v1-e2e"),
        json={"base_version": version},
    )
    assert dossier.status_code == 200, dossier.text
    dossier_body = dossier.json()
    version = dossier_body["version"]
    assert dossier_body["item_count"] == 1
    lawn_item = item_for_label(final_packet, _LAWN_LABEL)
    dossier_item = dossier_body["dossier"]["items"][0]
    assert dossier_item["item_id"] == lawn_item.id
    assert dossier_item["decision"]["action"] == "reject"
    assert dossier_item["justification"] == _LAWN_REJECTION_NOTE
    assert "price" not in json.dumps(dossier_body["dossier"])

    dossier_read = client.get(
        f"/v1/valuation-rounds/{round_id}/amendment-dossier", headers=_headers()
    ).json()
    assert dossier_read["dossier"] == dossier_body["dossier"]
    assert dossier_read["dossier_sha256"] == dossier_body["dossier_sha256"]

    # 11. Estado final da rodada: todas as etapas presentes, e o digest do pacote que a
    # rota `/takeoff` serviu é o mesmo que o estado da rodada publica.
    final_state = client.get(f"/v1/valuation-rounds/{round_id}", headers=_headers()).json()
    assert final_state["version"] == version
    assert final_state["plate"]["present"] is True
    assert final_state["extraction"]["status"] == "done"
    assert final_state["takeoff"]["present"] is True
    assert final_state["takeoff"]["review_status"] == "complete"
    assert final_state["codes"]["assignments_present"] is True
    assert final_state["codes"]["confirmed"] == len(_CATALOG_UNIT_PRICE)
    assert final_state["codes"]["rejected"] == 1
    assert final_state["codes"]["pending"] == 0
    assert final_state["bulletin"]["present"] is True
    assert final_state["dossier"]["present"] is True
    assert final_state["artifacts"]["takeoff_packet_json"] == final_takeoff["packet_sha256"]

    listing = client.get("/v1/valuation-rounds", headers=_headers()).json()
    summary = next(item for item in listing["items"] if item["round_id"] == round_id)
    assert summary["stage"] == "amendment_dossier"
    assert summary["extraction_status"] == "done"


# --- F-028 T3: aprovação nominal + export do boletim pelas rotas /v1, sem CLI -------------


def _assert_route_workbook_matches_cli(
    route_workbook: bytes,
    *,
    valuation: Valuation,
    catalog: PriceCatalog,
    tmp_path: Path,
) -> None:
    """Reabre o `.xlsx` publicado pela rota e o compara, por CANONICALIZAÇÃO, com o que o
    caminho de exportação do CLI produziria para a MESMA `Valuation` aprovada e o MESMO
    catálogo (critério 6 da F-028: a rota fecha a cadeia sem o CLI, e o boletim que ela
    publica não é um produto paralelo).

    Import das funções do worker/domínio **só aqui dentro**, porque só este teste de
    paridade precisa do caminho de exportação alternativo — o resto da cadeia não passa
    pelo CLI.

    `croquito_worker.valuation.cli.run_export_valuation` (a função que a rota do CLI usa)
    foi lida como referência do desenho fail-closed (grava em nome pendente, audita,
    só então publica), mas sua assinatura exige um `ContractWorkbook` **não opcional** —
    e a rota publica o boletim de `/v1` com `contract=None`, porque a rodada não importa
    consolidado contratual (`bulletin_export_contract`, `valuation_rounds.py`). Passar
    QUALQUER `ContractWorkbook` — mesmo vazio — faria `plan_workbook` acrescentar a aba
    PLANILHA GERAL (e a de RE-RA, se houver aditivo), e os dois `.xlsx` deixariam de ser
    logicamente idênticos por um motivo estrutural, não um detalhe de valor.

    A comparação, então, chama diretamente as DUAS funções que `run_export_valuation`
    embrulha — `write_valuation_workbook` e `audit_workbook` — com `contract=None`: são
    as MESMAS funções de produção que tanto o comando `export-valuation` do CLI quanto
    `render_valuation_workbook` da rota (F-028 T1) chamam por baixo, então a paridade
    provada aqui é a paridade real da produção, não uma reimplementação do teste.
    """
    from croquito_valuation.canonical import audit_workbook, canonicalize_workbook
    from croquito_valuation.template import default_template
    from croquito_valuation.workbook_writer import write_valuation_workbook

    template = default_template()

    route_path = tmp_path / "rota-boletim.xlsx"
    route_path.write_bytes(route_workbook)

    cli_path = tmp_path / "cli-boletim.xlsx"
    write_valuation_workbook(valuation, catalog, template, cli_path, None)
    cli_audit = audit_workbook(cli_path, valuation, catalog, template, None)
    assert cli_audit.status == "ok", cli_audit.findings

    assert canonicalize_workbook(route_path, template) == canonicalize_workbook(cli_path, template)


def test_aprovacao_e_exportacao_do_boletim_fecham_por_v1_sem_cli(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    stack: tuple[TestClient, FakeObjectStore, FakeQueue, str],
) -> None:
    """Critérios 5 e 6 da F-028: aprovação nominal + export do boletim fecham pela rota
    `/v1`, sem CLI, e o `.xlsx` publicado é logicamente idêntico ao que a MESMA medição
    aprovada produziria pelo caminho de exportação do CLI (F-028 T3).

    Parte do MESMO boletim de `test_valuation_round_full_chain_through_v1_api`
    (`_build_round_through_calc`); esta cena prova só o que aquele teste não cobre:

    1. exportar antes de aprovar é recusado pelo PORTÃO DO DOMÍNIO
       (`VALUATION_EXPORT_BLOCKED`/`VALUATION_NOT_APPROVED`), e nada é publicado;
    2. `POST .../approve` carimba a identidade do subject do token e amarra o ato ao
       digest do conteúdo — o `GET` da rodada expõe `approved`/`approved_by`/`stale`;
    3. `POST .../bulletin/export` publica um `.xlsx` auditado, reabrível, e logicamente
       idêntico ao que o caminho de exportação do CLI produziria (paridade, ver
       `_assert_route_workbook_matches_cli`);
    4. recalcular (`/calc` de novo) deixa a aprovação anterior CADUCA — o `GET` expõe
       `stale: true` mesmo sem nenhuma decisão nova, porque `Valuation.id` é gerado de
       novo a cada `/calc` — e a exportação recusa com `APPROVAL_CONTENT_MISMATCH` até um
       ato de aprovação novo, que destrava a exportação de novo.
    """
    chain = _build_round_through_calc(tmp_path, monkeypatch, stack)
    client = chain.client
    storage = chain.storage
    round_id = chain.round_id
    version = chain.version

    # 1. Exportar ANTES de aprovar: recusa do portão do domínio, e nada é publicado.
    objects_before = set(storage.objects)
    blocked = client.post(
        f"/v1/valuation-rounds/{round_id}/bulletin/export",
        headers=_headers("exportar-sem-aprovar"),
        json={"base_version": version},
    )
    assert blocked.status_code == 422, blocked.text
    blocked_detail = blocked.json()["detail"]
    assert blocked_detail["code"] == "DOMAIN_VALIDATION_FAILED"
    assert blocked_detail["details"]["code"] == "VALUATION_EXPORT_BLOCKED"
    assert "VALUATION_NOT_APPROVED" in blocked_detail["details"]["errors"]
    assert set(storage.objects) == objects_before

    # 2. `POST .../approve`: aprovação embutida, identidade do JWT, digest amarrado ao
    # conteúdo aprovado — o GET da rodada expõe o bloco de aprovação.
    approved = client.post(
        f"/v1/valuation-rounds/{round_id}/approve",
        headers=_headers("aprovar-v1-e2e"),
        json={"base_version": version},
    )
    assert approved.status_code == 200, approved.text
    version = approved.json()["version"]

    round_after_approval = client.get(f"/v1/valuation-rounds/{round_id}", headers=_headers()).json()
    approval_after_approval = round_after_approval["bulletin"]["approval"]
    assert approval_after_approval["approved"] is True
    assert approval_after_approval["approved_by"] == SUBJECT
    assert approval_after_approval["stale"] is False

    # 3. `POST .../bulletin/export`: publicado; reabre o `.xlsx` do fake store e compara
    # com o caminho do CLI sobre a MESMA `Valuation`/catálogo/template.
    exported = client.post(
        f"/v1/valuation-rounds/{round_id}/bulletin/export",
        headers=_headers("exportar-v1-e2e"),
        json={"base_version": version},
    )
    assert exported.status_code == 200, exported.text
    version = exported.json()["version"]
    valuation_sha256 = exported.json()["valuation_sha256"]

    bulletin_after_export = client.get(
        f"/v1/valuation-rounds/{round_id}/bulletin", headers=_headers()
    ).json()
    assert bulletin_after_export["workbook_url"] is not None

    route_workbook_key = (
        f"tenants/{TENANT}/valuation-rounds/{round_id}/bulletin/{valuation_sha256}.xlsx"
    )
    _assert_route_workbook_matches_cli(
        storage.body(route_workbook_key),
        valuation=Valuation.model_validate(bulletin_after_export["valuation"]),
        catalog=PriceCatalog.model_validate_json(_catalog_bytes()),
        tmp_path=tmp_path,
    )

    # 4. Recalcular deixa a aprovação caduca: o GET expõe `stale: true`, a exportação
    # recusa com `APPROVAL_CONTENT_MISMATCH`, e aprovar de novo destrava a exportação.
    recalculated = client.post(
        f"/v1/valuation-rounds/{round_id}/calc",
        headers=_headers("recalcular-v1-e2e"),
        json={"base_version": version},
    )
    assert recalculated.status_code == 200, recalculated.text
    version = recalculated.json()["version"]

    round_after_recalc = client.get(f"/v1/valuation-rounds/{round_id}", headers=_headers()).json()
    assert round_after_recalc["bulletin"]["approval"]["stale"] is True

    refused = client.post(
        f"/v1/valuation-rounds/{round_id}/bulletin/export",
        headers=_headers("exportar-caduca-v1-e2e"),
        json={"base_version": version},
    )
    assert refused.status_code == 422, refused.text
    refused_detail = refused.json()["detail"]
    assert refused_detail["code"] == "DOMAIN_VALIDATION_FAILED"
    assert refused_detail["details"]["code"] == "VALUATION_EXPORT_BLOCKED"
    assert "APPROVAL_CONTENT_MISMATCH" in refused_detail["details"]["errors"]

    reapproved = client.post(
        f"/v1/valuation-rounds/{round_id}/approve",
        headers=_headers("aprovar-de-novo-v1-e2e"),
        json={"base_version": version},
    )
    assert reapproved.status_code == 200, reapproved.text
    version = reapproved.json()["version"]

    exported_again = client.post(
        f"/v1/valuation-rounds/{round_id}/bulletin/export",
        headers=_headers("exportar-liberada-v1-e2e"),
        json={"base_version": version},
    )
    assert exported_again.status_code == 200, exported_again.text
    assert exported_again.json()["workbook_present"] is True
