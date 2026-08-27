"""O consolidado contratual recomputa acumulado, saldo e o efeito das RE-RA."""

from __future__ import annotations

from decimal import Decimal

import pytest
from pydantic import ValidationError

from croquito_valuation.contract import (
    Amendment,
    AmendmentLine,
    ContractLine,
    ContractWorkbook,
    PeriodProgress,
    contract_workbook_id_for,
)
from croquito_valuation.errors import (
    ValuationValidationError,
    valuation_error_codes,
    valuation_errors,
)

_CODE_A = "AD04050050(/)"
_CODE_B = "SP01050010(/)"
_CODE_NEW = "MB01100010(/)"
_CODE_ABSENT = "CE02100010(/)"
_OTHER_GROUP = "PAVIMENTACAO DA QUADRA"
_SOURCE_SHA256 = "a" * 64


def _period(number: int, quantity: str, amount: str) -> PeriodProgress:
    return PeriodProgress(period_number=number, quantity=Decimal(quantity), amount=Decimal(amount))


def _first_line(
    *,
    item_number: str = "1",
    code: str = _CODE_A,
    group_label: str = "PAVIMENTACAO",
    amended_quantity: str = "16.00",
    periods: list[PeriodProgress] | None = None,
    accumulated_quantity: str = "5.00",
    accumulated_amount: str = "50.00",
    balance_quantity: str = "11.00",
) -> ContractLine:
    """Linha reduzida por RE-RA: 20,00 contratados, 16,00 vigentes, 5,00 medidos."""
    return ContractLine(
        group_label=group_label,
        item_number=item_number,
        code=code,
        description="PISO INTERTRAVADO SINTETICO 6CM",
        unit="m2",
        unit_price=Decimal("10.00"),
        contract_quantity=Decimal("20.00"),
        amended_quantity=Decimal(amended_quantity),
        periods=[_period(1, "3.00", "30.00"), _period(2, "2.00", "20.00")]
        if periods is None
        else periods,
        accumulated_quantity=Decimal(accumulated_quantity),
        accumulated_amount=Decimal(accumulated_amount),
        balance_quantity=Decimal(balance_quantity),
    )


def _second_line() -> ContractLine:
    """Linha sem RE-RA: 8,00 contratados e vigentes, 2,50 medidos."""
    return ContractLine(
        group_label="SERVICOS PRELIMINARES",
        item_number="2",
        code=_CODE_B,
        description="ESCAVACAO SINTETICA MANUAL EM SOLO",
        unit="m3",
        unit_price=Decimal("20.00"),
        contract_quantity=Decimal("8.00"),
        amended_quantity=Decimal("8.00"),
        periods=[_period(1, "1.00", "20.00"), _period(2, "1.50", "30.00")],
        accumulated_quantity=Decimal("2.50"),
        accumulated_amount=Decimal("50.00"),
        balance_quantity=Decimal("5.50"),
    )


def _new_item_line() -> ContractLine:
    """Item criado por RE-RA: contratual zero, vigente 6,00, nada medido ainda."""
    return ContractLine(
        group_label="MOBILIARIO URBANO",
        item_number="3",
        code=_CODE_NEW,
        description="BANCO SINTETICO DE CONCRETO PRE-MOLDADO",
        unit="un",
        unit_price=Decimal("5.00"),
        contract_quantity=Decimal("0.00"),
        amended_quantity=Decimal("6.00"),
        periods=[],
        accumulated_quantity=Decimal("0.00"),
        accumulated_amount=Decimal("0.00"),
        balance_quantity=Decimal("6.00"),
    )


def _amendment(lines: list[AmendmentLine] | None = None) -> Amendment:
    return Amendment(
        label="1ª RE-RA",
        lines=[
            AmendmentLine(code=_CODE_A, quantity_delta=Decimal("-4.00"), note="redução de escopo"),
            AmendmentLine(code=_CODE_NEW, quantity_delta=Decimal("6.00"), is_new_item=True),
        ]
        if lines is None
        else lines,
    )


def _workbook(
    *,
    lines: list[ContractLine] | None = None,
    amendments: list[Amendment] | None = None,
    period_numbers: list[int] | None = None,
) -> ContractWorkbook:
    return ContractWorkbook(
        source_label="MAPÃO SINTÉTICO 19ª MEDIÇÃO (fixture)",
        source_sha256=_SOURCE_SHA256,
        contract_label="CONTRATO SINTETICO 001/2026",
        period_numbers=[1, 2] if period_numbers is None else period_numbers,
        lines=[_first_line(), _second_line(), _new_item_line()] if lines is None else lines,
        amendments=[_amendment()] if amendments is None else amendments,
    )


def test_consolidated_workbook_closes_periods_amendments_and_balance() -> None:
    workbook = _workbook()

    # O consolidado subiu de schema com a F-039 (reajuste), aditivamente: `2.0.0` continua
    # validando e responde sem reajuste, que é a verdade sobre um consolidado escrito antes.
    assert workbook.schema_version == "3.0.0"
    assert workbook.adjustments == []
    assert workbook.is_adjusted is False
    reduced = workbook.line_for_code(_CODE_A)
    assert reduced.expected_accumulated_quantity == Decimal("5.00")
    assert reduced.expected_accumulated_amount == Decimal("50.00")
    assert reduced.expected_balance_quantity == Decimal("11.00")
    assert workbook.line_for_code(_CODE_NEW).contract_quantity == Decimal("0.00")
    assert workbook.line_for_code(_CODE_B).balance_quantity == Decimal("5.50")


def test_contract_workbook_id_is_derived_from_the_source_digest() -> None:
    assert contract_workbook_id_for(_SOURCE_SHA256) == contract_workbook_id_for(_SOURCE_SHA256)
    assert contract_workbook_id_for(_SOURCE_SHA256) != contract_workbook_id_for("b" * 64)


def test_line_for_code_refuses_a_code_outside_the_contract() -> None:
    with pytest.raises(ValuationValidationError) as raised:
        _workbook().line_for_code(_CODE_ABSENT)

    assert raised.value.code == "CODE_NOT_IN_CONTRACT"
    assert raised.value.details["code"] == _CODE_ABSENT


def test_periods_must_be_strictly_increasing() -> None:
    with pytest.raises(ValidationError) as raised:
        _first_line(periods=[_period(2, "3.00", "30.00"), _period(2, "2.00", "20.00")])

    assert valuation_error_codes(raised.value) == ["PERIOD_SEQUENCE_BROKEN"]


def test_a_line_may_skip_a_measurement_number_the_contract_also_skips() -> None:
    """O contrato real pula uma medição: a linha declara 1 e 4, e isso fecha."""
    skipped = _first_line(periods=[_period(1, "3.00", "30.00"), _period(4, "2.00", "20.00")])

    workbook = _workbook(lines=[skipped, _new_item_line()], period_numbers=[1, 4])

    assert [period.period_number for period in workbook.lines[0].periods] == [1, 4]
    assert workbook.period_count == 2
    assert workbook.next_period_number == 5


def test_the_first_measurement_of_a_contract_is_the_number_one() -> None:
    workbook = _workbook(
        lines=[_new_item_line()],
        amendments=[
            _amendment(
                lines=[
                    AmendmentLine(code=_CODE_NEW, quantity_delta=Decimal("6.00"), is_new_item=True)
                ]
            )
        ],
        period_numbers=[],
    )

    assert workbook.period_count == 0
    assert workbook.next_period_number == 1


@pytest.mark.parametrize("period_numbers", [[2, 1], [1, 1], [0, 1]])
def test_workbook_refuses_measurement_numbers_that_do_not_grow(period_numbers: list[int]) -> None:
    with pytest.raises(ValidationError) as raised:
        _workbook(lines=[_new_item_line()], amendments=[], period_numbers=period_numbers)

    assert valuation_error_codes(raised.value) == ["PERIOD_SEQUENCE_BROKEN"]


def test_period_amount_must_be_quantity_times_price_truncated() -> None:
    with pytest.raises(ValidationError) as raised:
        _first_line(periods=[_period(1, "3.00", "30.01"), _period(2, "2.00", "20.00")])

    assert valuation_error_codes(raised.value) == ["PERIOD_AMOUNT_MISMATCH"]
    assert valuation_errors(raised.value)[0].details["period_number"] == 1


def test_accumulated_quantity_must_match_the_sum_of_the_periods() -> None:
    with pytest.raises(ValidationError) as raised:
        _first_line(accumulated_quantity="5.50", balance_quantity="10.50")

    assert valuation_error_codes(raised.value) == ["CONTRACT_ACCUMULATED_MISMATCH"]
    assert valuation_errors(raised.value)[0].details["field"] == "accumulated_quantity"


def test_accumulated_amount_must_match_the_sum_of_the_periods() -> None:
    with pytest.raises(ValidationError) as raised:
        _first_line(accumulated_amount="50.01")

    assert valuation_error_codes(raised.value) == ["CONTRACT_ACCUMULATED_MISMATCH"]
    assert valuation_errors(raised.value)[0].details["field"] == "accumulated_amount"


def test_accumulated_above_the_amended_quantity_is_refused() -> None:
    with pytest.raises(ValidationError) as raised:
        _first_line(amended_quantity="4.00", balance_quantity="0.00")

    assert valuation_error_codes(raised.value) == ["CONTRACT_BALANCE_NEGATIVE"]


def test_declared_balance_must_be_amended_minus_accumulated() -> None:
    with pytest.raises(ValidationError) as raised:
        _first_line(balance_quantity="10.00")

    assert valuation_error_codes(raised.value) == ["CONTRACT_BALANCE_MISMATCH"]


def test_workbook_refuses_a_repeated_item_number_in_the_same_group() -> None:
    with pytest.raises(ValidationError) as raised:
        _workbook(lines=[_first_line(), _first_line(code=_CODE_B)])

    assert valuation_error_codes(raised.value) == ["CONTRACT_DUPLICATE_ITEM"]


def test_workbook_refuses_a_repeated_code_in_the_same_group() -> None:
    with pytest.raises(ValidationError) as raised:
        _workbook(lines=[_first_line(), _first_line(item_number="2")])

    assert valuation_error_codes(raised.value) == ["CONTRACT_DUPLICATE_CODE"]


def _repeated_code_workbook() -> ContractWorkbook:
    """Duas linhas do mesmo código em grupos diferentes, nenhuma alterada por RE-RA."""
    return _workbook(
        lines=[
            _first_line(amended_quantity="20.00", balance_quantity="15.00"),
            _first_line(
                group_label=_OTHER_GROUP, amended_quantity="20.00", balance_quantity="15.00"
            ),
        ],
        amendments=[],
    )


def test_workbook_accepts_the_same_code_and_item_number_in_another_group() -> None:
    """O MAPÃO real repete código e reinicia a numeração de item a cada grupo."""
    workbook = _repeated_code_workbook()

    assert [line.group_label for line in workbook.lines_for_code(_CODE_A)] == [
        "PAVIMENTACAO",
        _OTHER_GROUP,
    ]
    assert [line.item_number for line in workbook.lines_for_code(_CODE_A)] == ["1", "1"]


def test_line_for_code_needs_the_group_when_the_code_repeats() -> None:
    workbook = _repeated_code_workbook()

    with pytest.raises(ValuationValidationError) as raised:
        workbook.line_for_code(_CODE_A)

    assert raised.value.code == "CODE_AMBIGUOUS_IN_CONTRACT"
    assert raised.value.details["groups"] == ["PAVIMENTACAO", _OTHER_GROUP]
    assert workbook.line_for_code(_CODE_A, group_label=_OTHER_GROUP).group_label == _OTHER_GROUP


def test_an_amendment_over_a_repeated_code_is_refused() -> None:
    with pytest.raises(ValidationError) as raised:
        _workbook(
            lines=[
                _first_line(),
                _first_line(group_label=_OTHER_GROUP),
            ],
            amendments=[
                _amendment(lines=[AmendmentLine(code=_CODE_A, quantity_delta=Decimal("-4.00"))])
            ],
        )

    assert valuation_error_codes(raised.value) == ["CODE_AMBIGUOUS_IN_CONTRACT"]
    assert valuation_errors(raised.value)[0].details["groups"] == ["PAVIMENTACAO", _OTHER_GROUP]


def test_line_must_declare_the_same_measurement_numbers_as_the_contract() -> None:
    incomplete = _first_line(
        periods=[_period(1, "5.00", "50.00")],
        accumulated_quantity="5.00",
        accumulated_amount="50.00",
    )

    with pytest.raises(ValidationError) as raised:
        _workbook(lines=[incomplete, _second_line(), _new_item_line()])

    assert valuation_error_codes(raised.value) == ["CONTRACT_PERIOD_NUMBERS_MISMATCH"]
    assert valuation_errors(raised.value)[0].details["expected"] == [1, 2]
    assert valuation_errors(raised.value)[0].details["declared"] == [1]


def test_amendment_refuses_the_same_code_twice() -> None:
    with pytest.raises(ValidationError) as raised:
        Amendment(
            label="1ª RE-RA",
            lines=[
                AmendmentLine(code=_CODE_A, quantity_delta=Decimal("-2.00")),
                AmendmentLine(code=_CODE_A, quantity_delta=Decimal("-2.00")),
            ],
        )

    assert valuation_error_codes(raised.value) == ["AMENDMENT_DUPLICATE_CODE"]


def test_amended_quantity_must_be_contract_plus_the_amendments() -> None:
    with pytest.raises(ValidationError) as raised:
        _workbook(
            lines=[
                _first_line(amended_quantity="17.00", balance_quantity="12.00"),
                _second_line(),
                _new_item_line(),
            ]
        )

    assert valuation_error_codes(raised.value) == ["AMENDMENT_APPLICATION_MISMATCH"]


def test_amendment_cannot_push_a_code_below_zero() -> None:
    negative = _amendment(
        lines=[
            AmendmentLine(code=_CODE_A, quantity_delta=Decimal("-25.00")),
            AmendmentLine(code=_CODE_NEW, quantity_delta=Decimal("6.00"), is_new_item=True),
        ]
    )

    with pytest.raises(ValidationError) as raised:
        _workbook(amendments=[negative])

    assert valuation_error_codes(raised.value) == ["AMENDMENT_NEGATIVE_RESULT"]


def test_contract_line_accepts_a_bare_code_outside_the_sco_table() -> None:
    """`IE00040849` não é SCO, mas tem a estrutura que o contrato real usa fora da tabela."""
    line = _first_line(code="IE00040849")

    assert line.code == "IE00040849"


@pytest.mark.parametrize("code", ["LAZER / PAISAGISMO", "IE123"])
def test_contract_line_refuses_text_without_the_contract_code_structure(code: str) -> None:
    with pytest.raises(ValidationError) as raised:
        _first_line(code=code)

    assert [error["loc"] for error in raised.value.errors()] == [("code",)]


def test_amendment_line_accepts_a_bare_code_outside_the_sco_table() -> None:
    line = AmendmentLine(code="IE00040849", quantity_delta=Decimal("1.00"))

    assert line.code == "IE00040849"


@pytest.mark.parametrize("code", ["LAZER / PAISAGISMO", "IE123"])
def test_amendment_line_refuses_text_without_the_contract_code_structure(code: str) -> None:
    with pytest.raises(ValidationError) as raised:
        AmendmentLine(code=code, quantity_delta=Decimal("1.00"))

    assert [error["loc"] for error in raised.value.errors()] == [("code",)]


def test_amendment_target_must_exist_in_the_contract() -> None:
    unknown = _amendment(
        lines=[
            AmendmentLine(code=_CODE_A, quantity_delta=Decimal("-4.00")),
            AmendmentLine(code=_CODE_NEW, quantity_delta=Decimal("6.00"), is_new_item=True),
            AmendmentLine(code=_CODE_ABSENT, quantity_delta=Decimal("-1.00")),
        ]
    )

    with pytest.raises(ValidationError) as raised:
        _workbook(amendments=[unknown])

    assert valuation_error_codes(raised.value) == ["AMENDMENT_TARGET_UNKNOWN"]


def test_new_item_of_an_amendment_must_start_from_zero() -> None:
    invalid = _amendment(
        lines=[
            AmendmentLine(code=_CODE_A, quantity_delta=Decimal("-4.00"), is_new_item=True),
            AmendmentLine(code=_CODE_NEW, quantity_delta=Decimal("6.00"), is_new_item=True),
        ]
    )

    with pytest.raises(ValidationError) as raised:
        _workbook(amendments=[invalid])

    assert valuation_error_codes(raised.value) == ["AMENDMENT_NEW_ITEM_INVALID"]
