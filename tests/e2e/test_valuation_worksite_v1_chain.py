"""A praça de DUAS folhas fechando ponta a ponta pela `/v1` (F-046 T4d, ADR-0057).

Contraponto de `tests/e2e/test_valuation_v1_chain.py`, que prova a mesma cadeia com UMA
folha: aqui a rodada nasce com duas folhas promovidas em lote, as duas são extraídas pelo
worker, as duas são revisadas e codificadas, uma leitura repetida é declarada como o mesmo
elemento físico, e só então o boletim da praça é construído e servido.

É o teste que a T4d existe para poder escrever. Antes dela a `/v1` guardava um conjunto de
códigos só — o da primeira folha —, e esta cadeia parava em `CALC_ASSIGNMENT_MISSING`,
nomeando os itens da folha 2 e nunca fechando.

Nenhuma chamada paga acontece: a extração entra pelo mesmo seam de fixture da cadeia de uma
folha (`legend_fixture_adapter` injetado no `LocalQueueWorker`), construído sobre a MESMA
prancha sintética. O PDF de duas páginas é a prancha sintética com a página duplicada — as
duas folhas leem a mesma legenda, que é o caso mais exigente para o consolidado: sem vínculo
declarado, tudo conta duas vezes, e é isso que a fusão precisa saber desfazer.

Toda mutação manda `Idempotency-Key` e o `base_version` corrente. O único acesso ao banco é
de CONFERÊNCIA: nenhuma etapa avança por escrita direta.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from typing import Final, cast

import pymupdf
import pytest
from fastapi.testclient import TestClient

from croquito_api.config import ApiSettings
from croquito_api.database import Database
from croquito_api.main import create_app
from croquito_valuation.models import Valuation
from croquito_valuation.rounding import money_trunc
from croquito_valuation.takeoff import TakeoffPacket
from croquito_worker.local_queue import LocalQueueWorker, LocalWorkerSettings
from croquito_worker.valuation.legend_fixtures import legend_fixture_adapter
from croquito_worker.valuation.plate import (
    SYNTHETIC_LEGEND_ROWS,
    PlateArtifacts,
    render_synthetic_plate,
)
from croquito_worker.valuation.round_extraction import AI_BUDGET_ENV
from croquito_worker.valuation.synthetic import (
    DEMO_EXPECTED_CODE_BY_LABEL,
    build_demo_code_assignments,
    build_demo_takeoff_decisions,
    item_for_label,
)
from tests.e2e.test_valuation_v1_chain import (
    _ANTHROPIC_KEY_ENV,
    _CATALOG_UNIT_PRICE,
    _LABEL_BY_CODE,
    _PAVEMENT_LABEL,
    QUEUE_URL,
    TENANT,
    _catalog_bytes,
    _drain,
    _headers,
    _packet_from_takeoff_response,
    _presign_and_put,
)
from tests.fakes import FakeObjectStore, FakeQueue

WORKSITE_KEY: Final = "praca-t4d-e2e"
"""Curta de propósito: o boletim de cada folha deriva `{chave}-p{posição}`, e a chave
derivada tem de continuar casando com o formato de chave de obra."""

WORKSITE_NAME: Final = "PRACA T4D E2E"
REFERENCE_LABEL: Final = "MEDICAO PRACA T4D 01/2026"
PERIOD_NUMBER: Final = 1
ADDRESS: Final = "RUA SINTETICA T4D, S/N"
CONTRACT_LABEL: Final = "CONTRATO SINTETICO T4D 01/2026"


def _two_page_plate_pdf(plate: PlateArtifacts, destination: Path) -> bytes:
    """A prancha sintética com a página DUPLICADA: um documento, duas folhas de praça.

    Duplicar é o que torna o teste exigente em vez de conveniente: as duas folhas leem a
    mesma legenda, então sem vínculo declarado a praça soma tudo duas vezes — e é exatamente
    essa soma que a declaração de identidade precisa saber desfazer, uma parcela de cada vez.

    Duas folhas do MESMO documento também são o caso real: planta geral e detalhe saem do
    mesmo PDF, e é por isso que o lote de promoção recebe um `upload_id` e várias páginas.
    """
    origem = pymupdf.open(plate.pdf_path)
    destino = pymupdf.open()
    try:
        destino.insert_pdf(origem)
        destino.insert_pdf(origem)
        assert destino.page_count == 2
        destino.save(destination)
    finally:
        destino.close()
        origem.close()
    return destination.read_bytes()


@pytest.fixture
def stack(tmp_path: Path) -> tuple[TestClient, FakeObjectStore, FakeQueue, str]:
    """API sobre SQLite em arquivo + storage/fila em memória compartilhados com o worker."""
    database_url = f"sqlite+pysqlite:///{tmp_path / 'praca-t4d.db'}"
    database = Database(database_url)
    database.create_schema()
    settings = ApiSettings(
        database_url=database_url,
        artifact_bucket="croquito-t4d-e2e",
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


def test_a_praca_de_duas_folhas_fecha_o_boletim_ponta_a_ponta(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    stack: tuple[TestClient, FakeObjectStore, FakeQueue, str],
) -> None:
    """Promover → extrair → decidir itens → confirmar códigos → fechar pacote → calc → boletim.

    Cada passo é a rota que a tela chama, na ordem em que a orçamentista os faz, e as duas
    folhas passam por todos eles. O que a T4d acrescenta à cadeia é o `plate_id` da etapa de
    código: sem ele, a folha 2 chegaria ao boletim sem conjunto nenhum.
    """
    client, storage, queue, database_url = stack

    # 0. Prancha sintética e o adapter fixture amarrado a ela. O freio de ambiente da extração
    # (teto de gasto + credencial) é config, não rede: a rota exige que ele esteja declarado.
    plate = render_synthetic_plate(tmp_path / "plate-source")
    monkeypatch.setenv(AI_BUDGET_ENV, "1.50")
    monkeypatch.setenv(_ANTHROPIC_KEY_ENV, "chave-de-teste-nunca-usada")
    worker = LocalQueueWorker(
        LocalWorkerSettings(
            database_url=database_url,
            queue_url=QUEUE_URL,
            aws_region="sa-east-1",
            aws_endpoint_url="http://localhost:4566",
            artifact_bucket="croquito-t4d-e2e",
        ),
        valuation_extraction_adapter=legend_fixture_adapter(plate),
    )
    worker.client = queue
    worker.s3_client = storage

    # 1. Catálogo instalado e rodada criada com ele.
    catalog_upload = _presign_and_put(
        client,
        storage,
        filename="catalogo.json",
        content_type="application/json",
        payload=_catalog_bytes(),
        key="presign-catalogo-t4d",
    )
    created = client.post(
        "/v1/valuation-rounds",
        headers=_headers("rodada-t4d"),
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
    version = created.json()["version"]

    # 2. Um documento de duas páginas, e as DUAS promovidas em lote: a seleção é o ato, e ela
    # é explícita — nada vem marcado por padrão.
    plate_payload = _two_page_plate_pdf(plate, tmp_path / "prancha-duas-folhas.pdf")
    plate_upload = _presign_and_put(
        client,
        storage,
        filename="prancha.pdf",
        content_type="application/pdf",
        payload=plate_payload,
        key="presign-prancha-t4d",
    )
    promoted = client.post(
        f"/v1/valuation-rounds/{round_id}/plates",
        headers=_headers("folhas-t4d"),
        json={
            "upload_id": plate_upload["upload_id"],
            "base_version": version,
            "page_numbers": [1, 2],
        },
    )
    assert promoted.status_code == 200, promoted.text
    version = promoted.json()["version"]
    assert promoted.json()["plate_count"] == 2
    folhas = [folha["plate_id"] for folha in promoted.json()["appended"]]
    assert folhas == [f"rodada-{round_id}", f"rodada-{round_id}-f2"]

    # 3. Uma extração paga por folha, num ato só, com as folhas nomeadas: o custo por folha é
    # escrito ANTES de o worker gastar o primeiro centavo.
    extraction = client.post(
        f"/v1/valuation-rounds/{round_id}/plates/extractions",
        headers=_headers("extracao-t4d"),
        json={"base_version": version, "plate_ids": folhas},
    )
    assert extraction.status_code == 202, extraction.text
    assert extraction.json()["plate_count"] == 2
    version = extraction.json()["version"]
    assert _drain(worker) == 2
    assert queue.commands() == ["extract_valuation_plate", "extract_valuation_plate"]

    praca = client.get(f"/v1/valuation-rounds/{round_id}/worksite", headers=_headers()).json()
    assert [folha["extraction_status"] for folha in praca["plates"]] == ["done", "done"]
    assert [folha["takeoff_present"] for folha in praca["plates"]] == [True, True]
    version = praca["version"]

    # 4. Revisão do takeoff, uma folha de cada vez: o lote é a legenda de UMA prancha.
    pacotes: dict[str, TakeoffPacket] = {}
    for indice, folha in enumerate(folhas):
        takeoff = client.get(
            f"/v1/valuation-rounds/{round_id}/takeoff",
            headers=_headers(),
            params={"plate_id": folha},
        ).json()
        assert takeoff["packet"]["plate_id"] == folha
        assert takeoff["review_status"] == "review_required"
        pacote = _packet_from_takeoff_response(takeoff)
        decisoes = build_demo_takeoff_decisions(pacote).decisions
        revisado = client.post(
            f"/v1/valuation-rounds/{round_id}/takeoff/decisions",
            headers=_headers(f"revisao-folha-{indice}"),
            json={
                "base_version": version,
                "plate_id": folha,
                "decisions": [
                    {
                        "item_id": decisao.item_id,
                        "action": decisao.action,
                        "quantity": None if decisao.quantity is None else str(decisao.quantity),
                        "unit": decisao.unit,
                        "note": decisao.note,
                    }
                    for decisao in decisoes
                ],
            },
        )
        assert revisado.status_code == 200, revisado.text
        assert revisado.json()["review_status"] == "complete"
        version = revisado.json()["version"]
        pacotes[folha] = _packet_from_takeoff_response(
            client.get(
                f"/v1/valuation-rounds/{round_id}/takeoff",
                headers=_headers(),
                params={"plate_id": folha},
            ).json()
        )
    _drain(worker)

    # 5. Etapa de código, também por folha — é o que a T4d entrega. A shortlist é a daquela
    # prancha, e o conjunto acumulado é gravado no lugar dela.
    for indice, folha in enumerate(folhas):
        shortlist = client.get(
            f"/v1/valuation-rounds/{round_id}/code-suggestions",
            headers=_headers(),
            params={"plate_id": folha},
        ).json()
        assert shortlist["suggestions"]["plate_id"] == folha
        # A shortlist é derivada e não é ato humano: o token de concorrência não anda.
        assert shortlist["version"] == version

        decisoes_de_codigo = build_demo_code_assignments(pacotes[folha]).assignments
        for posicao, atribuicao in enumerate(decisoes_de_codigo):
            resposta = client.post(
                f"/v1/valuation-rounds/{round_id}/code-assignments/decisions",
                headers=_headers(f"codigo-{indice}-{posicao}"),
                json={
                    "base_version": version,
                    "plate_id": folha,
                    "item_id": atribuicao.item_id,
                    "action": atribuicao.action,
                    "code": atribuicao.code,
                    "note": atribuicao.note,
                },
            )
            assert resposta.status_code == 200, resposta.text
            version = resposta.json()["version"]
        for posicao, atribuicao in enumerate(decisoes_de_codigo):
            if atribuicao.action != "confirm":
                continue  # a rejeição fecha o item sozinha
            resposta = client.post(
                f"/v1/valuation-rounds/{round_id}/code-assignments/closures",
                headers=_headers(f"fechamento-{indice}-{posicao}"),
                json={"base_version": version, "plate_id": folha, "item_id": atribuicao.item_id},
            )
            assert resposta.status_code == 200, resposta.text
            version = resposta.json()["version"]

        etapa = client.get(
            f"/v1/valuation-rounds/{round_id}/code-assignments",
            headers=_headers(),
            params={"plate_id": folha},
        ).json()
        assert etapa["plate_id"] == folha
        assert etapa["pending_items"] == []
        assert etapa["confirmed"] == len(_CATALOG_UNIT_PRICE)

    # 6. O mesmo piso desenhado nas duas folhas é declarado como UM elemento físico.
    piso_a = item_for_label(pacotes[folhas[0]], _PAVEMENT_LABEL)
    piso_b = item_for_label(pacotes[folhas[1]], _PAVEMENT_LABEL)
    previa = client.post(
        f"/v1/valuation-rounds/{round_id}/worksite/identity-links/preview",
        headers={"Authorization": f"Bearer test:{TENANT}:orcamentista-v1-e2e:orcamentista"},
        json={
            "kept": {"plate_id": folhas[0], "item_id": piso_a.id},
            "discarded": {"plate_id": folhas[1], "item_id": piso_b.id},
        },
    ).json()
    assert previa["unit_mismatch"] is False
    # A prévia é a conta do SERVIDOR: a tela de medição não soma.
    assert Decimal(previa["total_before"]) == cast(Decimal, piso_a.quantity) + cast(
        Decimal, piso_b.quantity
    )
    assert Decimal(previa["total_after"]) == piso_a.quantity

    vinculo = client.post(
        f"/v1/valuation-rounds/{round_id}/worksite/identity-links",
        headers=_headers("vinculo-t4d"),
        json={
            "base_version": version,
            "kept": {"plate_id": folhas[0], "item_id": piso_a.id},
            "discarded": {"plate_id": folhas[1], "item_id": piso_b.id},
            "note": "o mesmo piso aparece nas duas folhas do documento",
        },
    )
    assert vinculo.status_code == 200, vinculo.text
    version = vinculo.json()["version"]

    # 7. O boletim da praça FECHA — o desfecho que a T4d destravou.
    calc = client.post(
        f"/v1/valuation-rounds/{round_id}/calc",
        headers=_headers("boletim-t4d"),
        json={"base_version": version},
    )
    assert calc.status_code == 200, calc.text
    corpo = calc.json()
    version = corpo["version"]
    medicao = Valuation.model_validate(corpo["valuation"])

    # Um boletim por folha, com a folha de origem preservada em cada memória.
    assert [boletim.worksite_key for boletim in medicao.bulletins] == [
        f"{WORKSITE_KEY}-p1",
        f"{WORKSITE_KEY}-p2",
    ]
    assert {sheet.worksite_key for sheet in medicao.calc_sheets} == {
        f"{WORKSITE_KEY}-p1",
        f"{WORKSITE_KEY}-p2",
    }

    # O total esperado é montado das quantidades FINAIS lidas da API, nunca supostas: cada
    # código conta nas duas folhas, menos o piso, que a declaração fundiu numa parcela só.
    esperado = Decimal("0.00")
    for codigo, (_unidade, preco) in _CATALOG_UNIT_PRICE.items():
        rotulo = _LABEL_BY_CODE[codigo]
        for indice, folha in enumerate(folhas):
            if indice == 1 and rotulo == _PAVEMENT_LABEL:
                continue  # a leitura absorvida não conta no total da praça
            item = item_for_label(pacotes[folha], rotulo)
            assert item.quantity is not None
            esperado += money_trunc(item.quantity * preco)
    assert Decimal(corpo["total_amount"]) == esperado

    # A leitura absorvida continua IMPRESSA na folha onde foi lida, com contribuição zero:
    # fundir é visível, não é apagar.
    linhas_da_folha_2 = {linha.code: linha for linha in medicao.bulletins[1].lines}
    codigo_do_piso = DEMO_EXPECTED_CODE_BY_LABEL[_PAVEMENT_LABEL]
    assert linhas_da_folha_2[codigo_do_piso].quantity == Decimal("0.00")
    assert linhas_da_folha_2[codigo_do_piso].total == Decimal("0.00")

    # 8. `GET .../bulletin` recomputa os totais na leitura e serve o mesmo documento.
    boletim = client.get(f"/v1/valuation-rounds/{round_id}/bulletin", headers=_headers()).json()
    assert boletim["total_amount"] == corpo["total_amount"]
    assert boletim["valuation_sha256"] == corpo["valuation_sha256"]

    # 9. Estado final: a praça inteira presente, as duas folhas extraídas e o boletim no ar.
    final = client.get(f"/v1/valuation-rounds/{round_id}", headers=_headers()).json()
    assert final["version"] == version
    assert final["worksite"]["plate_count"] == 2
    assert final["worksite"]["identity_link_count"] == 1
    assert final["bulletin"]["present"] is True
    praca_final = client.get(f"/v1/valuation-rounds/{round_id}/worksite", headers=_headers()).json()
    assert praca_final["consolidated"]["present"] is True
    assert praca_final["consolidated"]["pending_plate_ids"] == []
    assert [folha["review_status"] for folha in praca_final["plates"]] == [
        "complete",
        "complete",
    ]
    assert len(SYNTHETIC_LEGEND_ROWS) == praca_final["plates"][0]["item_count"]
