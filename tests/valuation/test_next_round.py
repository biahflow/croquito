"""A medição seguinte: o consolidado n+1 nasce da rodada anterior (F-040, ADR-0056 dec. 4)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from croquito_valuation.contract import (
    Amendment,
    AmendmentLine,
    ContractLine,
    ContractWorkbook,
    PriceAdjustment,
    apply_declared_amendment,
    build_next_round_contract,
)
from croquito_valuation.errors import ValuationValidationError

_CODE = "AD04050050(/)"
_SOURCE_SHA256 = "a" * 64
_BRT = timezone(timedelta(hours=-3))


def _line(*, contract_quantity: str = "20.00", unit_price: str = "10.00") -> ContractLine:
    return ContractLine(
        group_label="PAVIMENTACAO",
        item_number="1",
        code=_CODE,
        description="PISO INTERTRAVADO SINTETICO 6CM",
        unit="m2",
        unit_price=Decimal(unit_price),
        contract_quantity=Decimal(contract_quantity),
        periods=[],
        accumulated_quantity=Decimal("0.00"),
        accumulated_amount=Decimal("0.00"),
    )


def _workbook(
    *,
    lines: list[ContractLine] | None = None,
    period_numbers: list[int] | None = None,
    adjustments: list[PriceAdjustment] | None = None,
) -> ContractWorkbook:
    return ContractWorkbook(
        source_label="MAPÃO SINTÉTICO (fixture)",
        source_sha256=_SOURCE_SHA256,
        period_numbers=[] if period_numbers is None else period_numbers,
        lines=[_line()] if lines is None else lines,
        adjustments=adjustments or [],
    )


def test_a_medicao_seguinte_lanca_o_periodo_e_soma_o_acumulado() -> None:
    previous = _workbook()

    nxt = build_next_round_contract(previous, measured={_CODE: Decimal("5.00")}, period_number=1)

    assert nxt.period_numbers == [1]
    line = nxt.line_for_code(_CODE)
    assert [p.period_number for p in line.periods] == [1]
    assert line.periods[0].quantity == Decimal("5.00")
    assert line.periods[0].amount == Decimal("50.00")
    # Sem reajuste, o período não carrega preço próprio: foi medido pelo contratado.
    assert line.periods[0].unit_price is None
    assert line.accumulated_quantity == Decimal("5.00")
    # Saldo derivado: 20 vigentes - 5 medidos = 15.
    assert nxt.current_balance_quantity(line) == Decimal("15.00")


def test_a_medicao_seguinte_exige_o_periodo_sequente() -> None:
    previous = _workbook(period_numbers=[])

    with pytest.raises(ValuationValidationError) as raised:
        build_next_round_contract(previous, measured={_CODE: Decimal("5.00")}, period_number=2)

    assert raised.value.code == "NEXT_ROUND_PERIOD_NOT_SEQUENTIAL"


def test_a_medicao_seguinte_preserva_a_re_ra_da_rodada_anterior() -> None:
    declared = Amendment(
        label="1ª RE-RA",
        lines=[AmendmentLine(code=_CODE, quantity_delta=Decimal("-4.00"))],
        declared_by="Ana",
        declared_at=datetime(2026, 8, 27, 10, 0, tzinfo=_BRT),
        reference_period="Processo 123/2026",
    )
    previous = apply_declared_amendment(_workbook(), declared)

    nxt = build_next_round_contract(previous, measured={_CODE: Decimal("5.00")}, period_number=1)

    line = nxt.line_for_code(_CODE)
    assert nxt.amendments[-1].has_provenance is True
    # Vigente re-ratificado (16), preservado: 16 - 5 = 11 de saldo.
    assert nxt.current_quantity(line) == Decimal("16.00")
    assert nxt.current_balance_quantity(line) == Decimal("11.00")


def test_a_medicao_seguinte_lanca_o_preco_reajustado_no_periodo() -> None:
    adjustment = PriceAdjustment(
        kind="index_factor",
        declared_by="Ana",
        declared_at=datetime(2026, 8, 27, 10, 0, tzinfo=_BRT),
        reference_period="08/2025 a 07/2026",
        index_label="INCC",
        factor=Decimal("1.10"),
    )
    previous = _workbook(adjustments=[adjustment])

    nxt = build_next_round_contract(previous, measured={_CODE: Decimal("5.00")}, period_number=1)

    period = nxt.line_for_code(_CODE).periods[0]
    # Preço vigente reajustado: 10,00 x 1,10 = 11,00; o período carrega o preço próprio.
    assert period.unit_price == Decimal("11.00")
    assert period.amount == Decimal("55.00")
