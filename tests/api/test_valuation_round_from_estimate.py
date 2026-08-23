"""Abrir a medição a partir de um orçamento assinado (F-036 T2, ADR-0048).

A rodada de orçamento é semeada direto no banco, com o `estimate_json` assinado e a cascata
apontando para um catálogo no store falso. A cadeia que PRODUZ esse orçamento já é coberta
por `test_estimate_round_routes.py`, e repeti-la aqui só tornaria estes testes lentos sem
dizer nada novo sobre a abertura da medição, que é o que eles medem.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, cast

from fastapi.testclient import TestClient

from croquito_api.database import (
    Database,
    EstimateRoundRecord,
    EstimateRoundRevisionRecord,
    ValuationRoundRecord,
)
from croquito_core.ids import new_uuid7
from croquito_valuation.estimate import (
    CatalogSource,
    Estimate,
    EstimateApproval,
    EstimateApproverDecision,
    EstimateLine,
)
from croquito_valuation.models import (
    CalcBlock,
    CalcOperand,
    CalcRecipe,
    CalcSheet,
    PriceCatalog,
    PriceCatalogEntry,
    PriceOrigin,
)
from croquito_valuation.rounding import money_trunc
from tests.api.test_valuation_round_routes import (
    _TENANT,
    _client,
    _database,
    _headers,
    _store,
)

_CODE = "CE04100010(/)"
_WORKSITE_KEY = "praca-orcada-sintetica"
_UNIT_PRICE = Decimal("50.00")
_OBJECT_KEY = f"tenants/{_TENANT}/reference-catalogs/sco-sintetico.json"


def _catalog_bytes() -> bytes:
    catalog = PriceCatalog(
        source_label="SCO CONTRATUAL SINTETICO",
        reference_month="2026-01",
        source_sha256="c" * 64,
        origin=PriceOrigin.SCO,
        entries=[
            PriceCatalogEntry(
                code=_CODE,
                description="ALAMBRADO GALVANIZADO",
                unit="m",
                unit_price=_UNIT_PRICE,
                family_code="CE",
                family_name="SERVICOS SINTETICOS",
                subgroup_code="CE0410",
                subgroup_name="ITENS SINTETICOS",
                origin=PriceOrigin.SCO,
            )
        ],
    )
    return catalog.model_dump_json().encode("utf-8")


def _calc_sheet(item_number: str, quantity: Decimal) -> CalcSheet:
    return CalcSheet(
        worksite_key=_WORKSITE_KEY,
        item_number=item_number,
        blocks=[
            CalcBlock(
                label="MEDIDA DIRETA",
                recipe=CalcRecipe.DIRECT_QUANTITY,
                operands=[CalcOperand(name="QUANTIDADE", value=quantity)],
                subtotal=quantity,
            )
        ],
        total_quantity=quantity,
    )


def _estimate(*, quantities: tuple[str, ...] = ("12.00",)) -> Estimate:
    """Orçamento sob o regime: BDI zero, porque a tabela contratual já o embute."""
    lines = [
        EstimateLine(
            item_number=str(index),
            code=_CODE,
            description="ALAMBRADO GALVANIZADO",
            unit="m",
            unit_price=_UNIT_PRICE,
            unit_price_with_bdi=_UNIT_PRICE,
            quantity=Decimal(quantity),
            total=money_trunc(Decimal(quantity) * _UNIT_PRICE),
            price_origin=PriceOrigin.SCO,
            catalog_sha256="c" * 64,
            reference_month="2026-01",
            source_label="SCO CONTRATUAL SINTETICO",
        )
        for index, quantity in enumerate(quantities, start=1)
    ]
    return Estimate(
        worksite_key=_WORKSITE_KEY,
        worksite_name="PRACA ORCADA SINTETICA",
        address="RUA SINTETICA, 100",
        plate_id="praca-orcada-prancha-01",
        page_number=1,
        image_sha256="a" * 64,
        source_pdf_sha256="b" * 64,
        bdi_percent=Decimal("0"),
        cascade=[
            CatalogSource(
                origin=PriceOrigin.SCO,
                source_sha256="c" * 64,
                reference_month="2026-01",
                source_label="SCO CONTRATUAL SINTETICO",
            )
        ],
        lines=lines,
        calc_sheets=[_calc_sheet(line.item_number, line.quantity) for line in lines],
        total_amount_without_bdi=sum((line.total for line in lines), Decimal("0.00")),
        total_amount=sum((line.total for line in lines), Decimal("0.00")),
        safety_notes=[
            "Orçamento sintético de teste sob demanda contratada.",
            "Cada linha declara a origem do preço; conferir a data-base antes de usar.",
        ],
    )


def _signed(estimate: Estimate, *, action: str = "confirm") -> dict[str, Any]:
    approval = EstimateApproval(
        decision=EstimateApproverDecision(
            decision_id="ed_0123456789abcdef",
            action=cast(Any, action),
            approver_id="aprovador-sintetico",
            approver_role="aprovador",
            decided_at=datetime(2026, 8, 22, 12, 0, tzinfo=UTC),
        ),
        estimate_digest=estimate.content_digest(),
    )
    payload = estimate.model_dump(mode="json")
    payload["approval"] = approval.model_dump(mode="json")
    return payload


def _seed_estimate_round(
    client: TestClient,
    *,
    document: dict[str, Any] | None,
    regime: str | None = "contracted_demand",
    tenant: str = _TENANT,
) -> str:
    """Rodada de orçamento com a cascata instalada e, opcionalmente, um orçamento na cabeça."""
    payload = _catalog_bytes()
    _store(client).put_direct(object_key=_OBJECT_KEY, body=payload, content_type="application/json")
    digest = hashlib.sha256(payload).hexdigest()
    database: Database = _database(client)
    round_id = str(new_uuid7())
    now = datetime.now(UTC)
    with database.sessions() as session:
        session.add(
            EstimateRoundRecord(
                id=round_id,
                tenant_id=tenant,
                worksite_key=_WORKSITE_KEY,
                worksite_name="PRACA ORCADA SINTETICA",
                reference_label="DEMANDA 2026/014",
                address="RUA SINTETICA, 100",
                pricing_regime=regime,
                status="OPEN",
                version=1,
                catalog_cascade_json=[
                    {
                        "provenance": "reference_catalog",
                        "upload_id": None,
                        "reference_catalog_id": str(new_uuid7()),
                        "object_key": _OBJECT_KEY,
                        "object_sha256": digest,
                        "source_sha256": "c" * 64,
                        "origin": PriceOrigin.SCO.value,
                        "reference_month": "2026-01",
                        "source_label": "SCO CONTRATUAL SINTETICO",
                        "summary": {},
                    }
                ],
                extraction_status="idle",
                created_by="orcamentista-sintetica",
                created_at=now,
                updated_at=now,
            )
        )
        session.add(
            EstimateRoundRevisionRecord(
                id=str(new_uuid7()),
                tenant_id=tenant,
                round_id=round_id,
                version=1,
                estimate_json=document,
                created_by="orcamentista-sintetica",
                created_at=now,
            )
        )
        session.commit()
    return round_id


def _refusal_errors(body: Any) -> list[str]:
    """As violações que a recusa carrega, onde quer que o envelope do problema as ponha.

    A busca é recursiva de propósito: o teste mede QUE a causa viaja até o cliente, não em
    qual chave o `problem+json` a aninhou — amarrar no caminho faria o teste quebrar numa
    mudança de envelope que não muda o que o orçamentista lê.
    """
    if isinstance(body, dict):
        found = body.get("errors")
        if isinstance(found, list):
            return [str(item) for item in found]
        for value in body.values():
            nested = _refusal_errors(value)
            if nested:
                return nested
    return []


def _open_from(
    client: TestClient, estimate_round_id: str, *, key: str = "abrir-do-orcamento", **extra: Any
) -> Any:
    body: dict[str, Any] = {
        "estimate_round_id": estimate_round_id,
        "reference_label": "Medição 1 — agosto/2026",
        "period_number": 1,
    }
    body.update(extra)
    return client.post("/v1/valuation-rounds", headers=_headers(key=key), json=body)


def test_a_medicao_nasce_com_o_contratado_do_orcamento_assinado(tmp_path: Path) -> None:
    client = _client(tmp_path)
    estimate_round_id = _seed_estimate_round(client, document=_signed(_estimate()))

    response = _open_from(client, estimate_round_id)

    assert response.status_code == 201, response.text
    round_id = response.json()["round_id"]
    with _database(client).sessions() as session:
        record = session.get(ValuationRoundRecord, round_id)
        assert record is not None
        # Obra e endereço vêm do conteúdo assinado, não do corpo do pedido.
        assert record.worksite_key == _WORKSITE_KEY
        assert record.address == "RUA SINTETICA, 100"
        assert record.estimate_round_id == estimate_round_id
        contract = record.contract_workbook_json
        assert contract is not None
        assert record.estimate_digest == contract["source_sha256"]
        assert [line["code"] for line in contract["lines"]] == [_CODE]
        # Preço de FONTE: o mesmo que o catálogo instalado traz, e que o boletim imprimirá.
        assert contract["lines"][0]["unit_price"] == "50.00"
        assert contract["lines"][0]["balance_quantity"] == "12.00"


def test_o_mesmo_codigo_em_dois_itens_vira_uma_linha_do_contratado(tmp_path: Path) -> None:
    client = _client(tmp_path)
    estimate_round_id = _seed_estimate_round(
        client, document=_signed(_estimate(quantities=("12.00", "7.50")))
    )

    response = _open_from(client, estimate_round_id)

    assert response.status_code == 201, response.text
    with _database(client).sessions() as session:
        record = session.get(ValuationRoundRecord, response.json()["round_id"])
        assert record is not None and record.contract_workbook_json is not None
        lines = record.contract_workbook_json["lines"]
        assert len(lines) == 1
        assert lines[0]["contract_quantity"] == "19.50"


def test_a_leitura_da_rodada_declara_contra_o_que_ela_confere(tmp_path: Path) -> None:
    """Decisão 9 do ADR-0048: as duas rodadas não podem parecer iguais."""
    client = _client(tmp_path)
    estimate_round_id = _seed_estimate_round(client, document=_signed(_estimate()))
    created = _open_from(client, estimate_round_id)
    assert created.status_code == 201, created.text

    leitura = client.get(
        f"/v1/valuation-rounds/{created.json()['round_id']}",
        headers=_headers(key="estado-com-vinculo"),
    )

    assert leitura.status_code == 200, leitura.text
    contracted = leitura.json()["contracted"]
    assert contracted["origin"] == "signed_estimate"
    assert contracted["estimate_round_id"] == estimate_round_id
    assert contracted["code_count"] == 1


def test_orcamento_sem_o_regime_nao_abre_medicao(tmp_path: Path) -> None:
    """Fora da demanda contratada existem a licitação e o deságio entre os dois preços."""
    client = _client(tmp_path)
    estimate_round_id = _seed_estimate_round(client, document=_signed(_estimate()), regime=None)

    response = _open_from(client, estimate_round_id)

    assert response.status_code == 409, response.text
    assert response.json()["code"] == "ESTIMATE_ORIGIN_REGIME_REQUIRED"


def test_orcamento_sem_assinatura_nao_abre_medicao(tmp_path: Path) -> None:
    client = _client(tmp_path)
    estimate_round_id = _seed_estimate_round(client, document=_estimate().model_dump(mode="json"))

    response = _open_from(client, estimate_round_id)

    assert response.status_code == 409, response.text
    body = response.json()
    assert body["code"] == "ESTIMATE_ORIGIN_NOT_SIGNED"
    assert "ESTIMATE_NOT_APPROVED" in _refusal_errors(body)


def test_assinatura_rejeitada_nao_abre_medicao(tmp_path: Path) -> None:
    client = _client(tmp_path)
    estimate_round_id = _seed_estimate_round(client, document=_signed(_estimate(), action="reject"))

    response = _open_from(client, estimate_round_id)

    assert response.status_code == 409, response.text
    assert "ESTIMATE_APPROVAL_REJECTED" in _refusal_errors(response.json())


def test_rodada_de_orcamento_sem_montagem_recusa(tmp_path: Path) -> None:
    client = _client(tmp_path)
    estimate_round_id = _seed_estimate_round(client, document=None)

    response = _open_from(client, estimate_round_id)

    assert response.status_code in (409, 422), response.text


def test_orcamento_de_outro_tenant_e_indistinguivel_de_ausente(tmp_path: Path) -> None:
    client = _client(tmp_path)
    estimate_round_id = _seed_estimate_round(
        client, document=_signed(_estimate()), tenant="outro-tenant"
    )

    response = _open_from(client, estimate_round_id)

    assert response.status_code == 404, response.text


def test_declarar_a_obra_junto_do_orcamento_recusa(tmp_path: Path) -> None:
    """Aceitar a obra aqui abriria a porta para medir uma praça diferente da que foi orçada."""
    client = _client(tmp_path)
    estimate_round_id = _seed_estimate_round(client, document=_signed(_estimate()))

    response = _open_from(client, estimate_round_id, worksite_key="outra-praca")

    assert response.status_code == 422, response.text


def test_sem_origem_nenhuma_recusa(tmp_path: Path) -> None:
    response = _client(tmp_path).post(
        "/v1/valuation-rounds",
        headers=_headers(key="sem-origem"),
        json={"reference_label": "Medição 1", "period_number": 1},
    )

    assert response.status_code == 422, response.text
