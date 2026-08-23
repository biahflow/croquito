"""Tradução do orçamento assinado em consolidado contratual (F-036 T1, ADR-0048).

O que estes testes protegem é o número que vai virar oráculo dos outros: um consolidado torto
transforma seis guardrails da medição em seis carimbos, e carimbo ninguém confere depois.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Literal

import pytest

from croquito_valuation.contract import ContractWorkbook
from croquito_valuation.contract_from_estimate import build_contract_from_estimate
from croquito_valuation.errors import ValuationValidationError
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
    PriceOrigin,
)
from croquito_valuation.rounding import money_trunc

_WORKSITE_KEY = "praca-sintetica-portao"
_CODE = "AD04050050(/)"
_OTHER_CODE = "AD04050051(/)"
_CATALOG_DIGEST = "c" * 64
_REFERENCE_MONTH = "2026-04"
_SOURCE_LABEL = "SCO SINTETICO (fixture)"
_UNIT_PRICE = Decimal("10.00")
_BDI_PERCENT = Decimal("20.00")

_GROUP = "DEMANDA 2026/014"
_ORIGIN_LABEL = "orçamento assinado: DEMANDA 2026/014"


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


def _line(
    *,
    item_number: str,
    code: str = _CODE,
    quantity: str,
    unit: str = "m2",
    unit_price: Decimal = _UNIT_PRICE,
    bdi_percent: Decimal = _BDI_PERCENT,
) -> EstimateLine:
    amount = Decimal(quantity)
    unit_price_with_bdi = money_trunc(unit_price * (1 + bdi_percent / 100))
    return EstimateLine(
        item_number=item_number,
        code=code,
        description="PISO INTERTRAVADO SINTETICO 6CM",
        unit=unit,
        unit_price=unit_price,
        unit_price_with_bdi=unit_price_with_bdi,
        quantity=amount,
        total=money_trunc(amount * unit_price_with_bdi),
        price_origin=PriceOrigin.SCO,
        catalog_sha256=_CATALOG_DIGEST,
        reference_month=_REFERENCE_MONTH,
        source_label=_SOURCE_LABEL,
    )


def _estimate(lines: list[EstimateLine], *, bdi_percent: Decimal = _BDI_PERCENT) -> Estimate:
    return Estimate(
        worksite_key=_WORKSITE_KEY,
        worksite_name="PRACA SINTETICA PORTAO",
        plate_id="praca-sintetica-portao-prancha-01",
        page_number=1,
        image_sha256="a" * 64,
        source_pdf_sha256="b" * 64,
        bdi_percent=bdi_percent,
        cascade=[
            CatalogSource(
                origin=PriceOrigin.SCO,
                source_sha256=_CATALOG_DIGEST,
                reference_month=_REFERENCE_MONTH,
                source_label=_SOURCE_LABEL,
            )
        ],
        lines=lines,
        calc_sheets=[_calc_sheet(line.item_number, line.quantity) for line in lines],
        total_amount_without_bdi=sum(
            (money_trunc(line.quantity * line.unit_price) for line in lines), Decimal("0.00")
        ),
        total_amount=sum((line.total for line in lines), Decimal("0.00")),
        safety_notes=[
            "Orçamento-base sintético de teste: não é medição e não tem contrato.",
            "Cada linha declara a origem do preço; conferir a data-base antes de usar.",
        ],
    )


def _approved(
    estimate: Estimate,
    *,
    action: Literal["confirm", "reject"] = "confirm",
    digest: str | None = None,
) -> Estimate:
    approval = EstimateApproval(
        decision=EstimateApproverDecision(
            decision_id="ed_0123456789abcdef",
            action=action,
            approver_id="aprovador-sintetico",
            approver_role="aprovador",
            decided_at=datetime(2026, 4, 30, 12, 0, tzinfo=UTC),
        ),
        estimate_digest=estimate.content_digest() if digest is None else digest,
    )
    payload = estimate.model_dump()
    payload["approval"] = approval.model_dump()
    return Estimate.model_validate(payload)


def _build(estimate: Estimate) -> ContractWorkbook:
    return build_contract_from_estimate(estimate, group_label=_GROUP, source_label=_ORIGIN_LABEL)


def _blocked_codes(error: ValuationValidationError) -> list[str]:
    """`details` é `dict[str, object]`; a lista de violações sai daqui já tipada."""
    errors = error.details["errors"]
    assert isinstance(errors, list)
    return [str(item) for item in errors]


def test_o_consolidado_nasce_com_saldo_igual_ao_contratado() -> None:
    """Primeira medição: nada foi lançado, então o saldo é o contrato inteiro."""
    contract = _build(_approved(_estimate([_line(item_number="1", quantity="5.00")])))

    assert contract.period_numbers == []
    assert len(contract.lines) == 1
    line = contract.lines[0]
    assert line.contract_quantity == Decimal("5.00")
    assert line.amended_quantity == Decimal("5.00")
    assert line.balance_quantity == Decimal("5.00")
    assert line.accumulated_quantity == Decimal("0.00")
    assert line.accumulated_amount == Decimal("0.00")
    assert line.periods == []
    assert line.group_label == _GROUP
    assert line.item_number == "1"


def test_o_preco_e_o_de_fonte_e_nunca_o_com_bdi() -> None:
    """A decisão mais consequente do ADR-0048.

    Com BDI de 20%, `unit_price_with_bdi` é 12,00 e `unit_price` é 10,00. Se a tradução
    trocasse os campos, TODA linha do boletim dispararia `LINE_PRICE_NOT_IN_CONTRACT` no
    primeiro uso, porque o boletim precifica pelo catálogo `sco`, que traz 10,00.
    """
    estimate = _approved(_estimate([_line(item_number="1", quantity="5.00")]))
    assert estimate.lines[0].unit_price_with_bdi == Decimal("12.00")

    contract = _build(estimate)

    assert contract.lines[0].unit_price == Decimal("10.00")


def test_o_mesmo_codigo_em_dois_trechos_vira_uma_linha_somada() -> None:
    """O caso comum, não a exceção: o mesmo serviço itemizado em dois trechos da prancha.

    `Estimate.validate_lines` recusa `item_number` repetido e NÃO recusa código repetido; o
    consolidado tem chave única grupo+código. Copiar linha a linha quebraria aqui.
    """
    estimate = _approved(
        _estimate(
            [
                _line(item_number="1", quantity="5.00"),
                _line(item_number="2", quantity="3.50"),
            ]
        )
    )

    contract = _build(estimate)

    assert len(contract.lines) == 1
    assert contract.lines[0].contract_quantity == Decimal("8.50")
    assert contract.lines[0].balance_quantity == Decimal("8.50")


def test_codigos_diferentes_viram_linhas_diferentes_na_ordem_do_orcamento() -> None:
    estimate = _approved(
        _estimate(
            [
                _line(item_number="1", code=_OTHER_CODE, quantity="2.00"),
                _line(item_number="2", code=_CODE, quantity="5.00"),
            ]
        )
    )

    contract = _build(estimate)

    assert [line.code for line in contract.lines] == [_OTHER_CODE, _CODE]
    assert [line.item_number for line in contract.lines] == ["1", "2"]


def test_preco_divergente_no_mesmo_codigo_recusa_em_vez_de_escolher() -> None:
    """Somar quantidades de preços diferentes seria fabricar um número."""
    estimate = _approved(
        _estimate(
            [
                _line(item_number="1", quantity="5.00"),
                _line(item_number="2", quantity="3.00", unit_price=Decimal("11.00")),
            ]
        )
    )

    with pytest.raises(ValuationValidationError) as error:
        _build(estimate)

    assert error.value.code == "ESTIMATE_CODE_PRICE_CONFLICT"
    assert error.value.details["code"] == _CODE
    assert error.value.details["unit_price"] == "10.00"
    assert error.value.details["conflicting_unit_price"] == "11.00"


def test_unidade_divergente_no_mesmo_codigo_recusa() -> None:
    estimate = _approved(
        _estimate(
            [
                _line(item_number="1", quantity="5.00"),
                _line(item_number="2", quantity="3.00", unit="m"),
            ]
        )
    )

    with pytest.raises(ValuationValidationError) as error:
        _build(estimate)

    assert error.value.code == "ESTIMATE_CODE_PRICE_CONFLICT"
    assert error.value.details["conflicting_unit"] == "m"


def test_orcamento_sem_assinatura_nao_produz_consolidado() -> None:
    with pytest.raises(ValuationValidationError) as error:
        _build(_estimate([_line(item_number="1", quantity="5.00")]))

    assert error.value.code == "ESTIMATE_EXPORT_BLOCKED"
    assert "ESTIMATE_NOT_APPROVED" in _blocked_codes(error.value)


def test_assinatura_rejeitada_nao_produz_consolidado() -> None:
    estimate = _approved(_estimate([_line(item_number="1", quantity="5.00")]), action="reject")

    with pytest.raises(ValuationValidationError) as error:
        _build(estimate)

    assert "ESTIMATE_APPROVAL_REJECTED" in _blocked_codes(error.value)


def test_assinatura_caduca_por_remontagem_nao_produz_consolidado() -> None:
    """Remontar depois de assinar não apaga a assinatura: torna-a caduca."""
    estimate = _approved(_estimate([_line(item_number="1", quantity="5.00")]), digest="d" * 64)

    with pytest.raises(ValuationValidationError) as error:
        _build(estimate)

    assert "APPROVAL_CONTENT_MISMATCH" in _blocked_codes(error.value)


def test_a_origem_do_consolidado_e_o_digest_assinado() -> None:
    """Não o digest da medição, que é o que a fabricação de hoje usa."""
    estimate = _approved(_estimate([_line(item_number="1", quantity="5.00")]))

    contract = _build(estimate)

    assert contract.source_sha256 == estimate.content_digest()
    assert contract.source_label == _ORIGIN_LABEL


def test_o_consolidado_nao_afirma_qual_contrato_e() -> None:
    """Lacuna 4 do ADR-0045: restringir a origem não confere a identidade do contrato.

    Preencher `contract_label` com o rótulo da rodada afirmaria uma identidade que ninguém
    conferiu — e é justamente a lacuna que esta feature declara não fechar.
    """
    contract = _build(_approved(_estimate([_line(item_number="1", quantity="5.00")])))

    assert contract.contract_label is None


def test_o_consolidado_produzido_sobrevive_a_revalidacao() -> None:
    """A prova real: os `model_validator` do consolidado passam sobre o que foi traduzido."""
    contract = _build(
        _approved(
            _estimate(
                [
                    _line(item_number="1", quantity="5.00"),
                    _line(item_number="2", code=_OTHER_CODE, quantity="2.25"),
                ]
            )
        )
    )

    revalidated = ContractWorkbook.model_validate(contract.model_dump(mode="json"))

    assert [line.code for line in revalidated.lines] == [_CODE, _OTHER_CODE]
    assert revalidated.next_period_number == 1
