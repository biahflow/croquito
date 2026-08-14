"""O portão de exportação falha fechado: sem aprovação válida e dentro do saldo, nada sai."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

import pytest
from pydantic import ValidationError

from croquitodxf_valuation.contract import ContractLine, ContractWorkbook
from croquitodxf_valuation.errors import ValuationValidationError, valuation_error_codes
from croquitodxf_valuation.models import (
    BulletinLine,
    CalcBlock,
    CalcOperand,
    CalcRecipe,
    CalcSheet,
    ReviewerDecision,
    Valuation,
    ValuationApproval,
    WorksiteBulletin,
)
from croquitodxf_valuation.rounding import money_trunc

_CODE = "AD04050050(/)"
_OTHER_CODE = "SP01050010(/)"
_UNIT = "m2"
_UNIT_PRICE = Decimal("10.00")
_VALUATION_ID = UUID("0195f3a0-0000-7000-8000-000000000001")
_ALFA = "praca-alfa"
_BETA = "praca-beta"
_DEFAULT_QUANTITIES: dict[str, str] = {_ALFA: "5.00", _BETA: "4.00"}


def _bulletin(
    worksite_key: str, quantity: str, *, unit: str, unit_price: Decimal
) -> WorksiteBulletin:
    total = money_trunc(Decimal(quantity) * unit_price)
    line = BulletinLine(
        item_number="1",
        code=_CODE,
        description="PISO INTERTRAVADO SINTETICO 6CM",
        unit=unit,
        unit_price=unit_price,
        quantity=Decimal(quantity),
        total=total,
    )
    return WorksiteBulletin(
        worksite_key=worksite_key,
        worksite_name=worksite_key.upper().replace("-", " "),
        lines=[line],
        total_amount=total,
    )


def _calc_sheet(worksite_key: str, quantity: str) -> CalcSheet:
    block = CalcBlock(
        label="AREA MEDIDA",
        recipe=CalcRecipe.DIRECT_QUANTITY,
        operands=[CalcOperand(name="AREA", value=Decimal(quantity), unit=_UNIT)],
        subtotal=Decimal(quantity),
    )
    return CalcSheet(
        worksite_key=worksite_key,
        item_number="1",
        blocks=[block],
        total_quantity=Decimal(quantity),
    )


def _valuation(
    *,
    quantities: dict[str, str] | None = None,
    period_number: int = 1,
    unit: str = _UNIT,
    unit_price: Decimal = _UNIT_PRICE,
) -> Valuation:
    measured = _DEFAULT_QUANTITIES if quantities is None else quantities
    return Valuation(
        id=_VALUATION_ID,
        period_number=period_number,
        reference_label="JANEIRO/2026",
        bulletins=[
            _bulletin(worksite_key, quantity, unit=unit, unit_price=unit_price)
            for worksite_key, quantity in measured.items()
        ],
        calc_sheets=[
            _calc_sheet(worksite_key, quantity) for worksite_key, quantity in measured.items()
        ],
    )


def _decision(action: Literal["confirm", "reject"] = "confirm") -> ReviewerDecision:
    return ReviewerDecision(
        decision_id="vd_0123456789abcdef",
        action=action,
        reviewer_id="orcamentista-sintetico",
        reviewer_role="orcamentista",
        decided_at=datetime(2026, 2, 1, 12, 0, tzinfo=UTC),
        note="conferido contra o consolidado",
    )


def _with_approval(valuation: Valuation, approval: ValuationApproval) -> Valuation:
    """Anexa a aprovação sem alterar o conteúdo digerido (o digest exclui `approval`)."""
    payload = valuation.model_dump()
    payload["approval"] = approval.model_dump()
    return Valuation.model_validate(payload)


def _approved(
    valuation: Valuation,
    *,
    action: Literal["confirm", "reject"] = "confirm",
    digest: str | None = None,
) -> Valuation:
    approval = ValuationApproval(
        decision=_decision(action),
        valuation_digest=valuation.content_digest() if digest is None else digest,
    )
    return _with_approval(valuation, approval)


def _contract_line(
    *,
    code: str = _CODE,
    item_number: str = "1",
    group_label: str = "PAVIMENTACAO",
    unit: str = _UNIT,
    unit_price: Decimal = _UNIT_PRICE,
    quantity: str = "20.00",
) -> ContractLine:
    return ContractLine(
        group_label=group_label,
        item_number=item_number,
        code=code,
        description="PISO INTERTRAVADO SINTETICO 6CM",
        unit=unit,
        unit_price=unit_price,
        contract_quantity=Decimal(quantity),
        amended_quantity=Decimal(quantity),
        periods=[],
        accumulated_quantity=Decimal("0.00"),
        accumulated_amount=Decimal("0.00"),
        balance_quantity=Decimal(quantity),
    )


def _contract(
    *, lines: list[ContractLine] | None = None, period_numbers: list[int] | None = None
) -> ContractWorkbook:
    return ContractWorkbook(
        source_label="MAPÃO SINTÉTICO (fixture)",
        source_sha256="c" * 64,
        period_numbers=[] if period_numbers is None else period_numbers,
        lines=[_contract_line()] if lines is None else lines,
    )


def test_approved_valuation_inside_the_balance_has_no_export_errors() -> None:
    valuation = _approved(_valuation())

    assert valuation.export_errors(_contract()) == []
    valuation.ensure_exportable(_contract())


def test_valuation_without_approval_is_blocked() -> None:
    assert _valuation().export_errors(_contract()) == ["VALUATION_NOT_APPROVED"]


def test_rejected_decision_is_blocked() -> None:
    valuation = _approved(_valuation(), action="reject")

    assert valuation.export_errors(_contract()) == ["VALUATION_APPROVAL_REJECTED"]


def test_approval_of_a_previous_content_is_blocked() -> None:
    approved = _approved(_valuation())
    stale_digest = approved.content_digest()
    edited = _approved(_valuation(quantities={_ALFA: "6.00", _BETA: "4.00"}), digest=stale_digest)

    assert edited.export_errors(_contract()) == ["APPROVAL_CONTENT_MISMATCH"]


def test_period_out_of_sequence_is_blocked() -> None:
    valuation = _approved(_valuation(period_number=3))

    assert valuation.export_errors(_contract()) == ["PERIOD_NOT_SEQUENTIAL:1:3"]


def test_the_expected_period_follows_the_last_measurement_number_not_the_count() -> None:
    """O contrato real pula uma medição: depois de 1, 2 e 4 a próxima é a 5ª, não a 4ª."""
    contract = _contract(period_numbers=[1, 2, 4])

    assert _approved(_valuation(period_number=4)).export_errors(contract) == [
        "PERIOD_NOT_SEQUENTIAL:5:4"
    ]
    assert _approved(_valuation(period_number=5)).export_errors(contract) == []


def test_a_code_that_the_contract_repeats_in_two_groups_is_blocked_per_worksite() -> None:
    contract = _contract(
        lines=[_contract_line(), _contract_line(group_label="PAVIMENTACAO DA QUADRA")]
    )
    valuation = _approved(_valuation())

    assert valuation.export_errors(contract) == [
        f"CODE_AMBIGUOUS_IN_CONTRACT:{_ALFA}:1:{_CODE}",
        f"CODE_AMBIGUOUS_IN_CONTRACT:{_BETA}:1:{_CODE}",
    ]


def test_code_outside_the_contract_is_blocked_per_worksite() -> None:
    contract = _contract(lines=[_contract_line(code=_OTHER_CODE, unit="m3")])
    valuation = _approved(_valuation())

    assert valuation.export_errors(contract) == [
        f"CODE_NOT_IN_CONTRACT:{_ALFA}:1:{_CODE}",
        f"CODE_NOT_IN_CONTRACT:{_BETA}:1:{_CODE}",
    ]


def test_price_divergent_from_the_contract_is_blocked() -> None:
    contract = _contract(lines=[_contract_line(unit_price=Decimal("11.00"))])
    valuation = _approved(_valuation())

    assert valuation.export_errors(contract) == [
        f"LINE_PRICE_NOT_IN_CONTRACT:{_CODE}",
        f"LINE_PRICE_NOT_IN_CONTRACT:{_CODE}",
    ]


def test_unit_divergent_from_the_contract_is_blocked() -> None:
    contract = _contract(lines=[_contract_line(unit="m3")])
    valuation = _approved(_valuation())

    assert valuation.export_errors(contract) == [
        f"LINE_UNIT_NOT_IN_CONTRACT:{_CODE}",
        f"LINE_UNIT_NOT_IN_CONTRACT:{_CODE}",
    ]


def test_balance_is_checked_across_every_worksite_of_the_valuation() -> None:
    contract = _contract(lines=[_contract_line(quantity="8.00")])

    alone = _approved(_valuation(quantities={_ALFA: "5.00"}))
    assert alone.export_errors(contract) == []

    together = _approved(_valuation())
    assert together.export_errors(contract) == [f"BALANCE_EXCEEDED:{_CODE}"]


_EXTRA_CODE = "IE00040849"
"""Código nu fora da tabela SCO: o portão confere preço/unidade/saldo por igualdade
de string, então ele passa como qualquer outro código, sem tratamento especial."""


def test_a_bare_code_passes_the_price_unit_and_balance_gate_like_any_code() -> None:
    contract = _contract(lines=[_contract_line(code=_EXTRA_CODE)])
    total = money_trunc(Decimal("5.00") * _UNIT_PRICE)
    line = BulletinLine(
        item_number="1",
        code=_EXTRA_CODE,
        description="SERVICO CONTRATADO FORA DA TABELA SCO",
        unit=_UNIT,
        unit_price=_UNIT_PRICE,
        quantity=Decimal("5.00"),
        total=total,
    )
    bulletin = WorksiteBulletin(
        worksite_key=_ALFA,
        worksite_name=_ALFA.upper().replace("-", " "),
        lines=[line],
        total_amount=total,
    )
    valuation = _approved(
        Valuation(
            id=_VALUATION_ID,
            period_number=1,
            reference_label="JANEIRO/2026",
            bulletins=[bulletin],
            calc_sheets=[_calc_sheet(_ALFA, "5.00")],
        )
    )

    assert valuation.export_errors(contract) == []


def test_ensure_exportable_raises_with_the_whole_list() -> None:
    contract = _contract(lines=[_contract_line(quantity="8.00")], period_numbers=[1, 2, 3, 4])

    with pytest.raises(ValuationValidationError) as raised:
        _valuation().ensure_exportable(contract)

    assert raised.value.code == "VALUATION_EXPORT_BLOCKED"
    assert raised.value.details["errors"] == [
        "VALUATION_NOT_APPROVED",
        "PERIOD_NOT_SEQUENTIAL:5:1",
        f"BALANCE_EXCEEDED:{_CODE}",
    ]


def test_content_digest_ignores_the_approval_it_authorizes() -> None:
    valuation = _valuation()
    approved = _approved(valuation)

    assert approved.approval is not None
    assert approved.content_digest() == valuation.content_digest()
    assert approved.approval.valuation_digest == valuation.content_digest()


def test_decision_without_timezone_is_refused() -> None:
    with pytest.raises(ValidationError) as raised:
        ReviewerDecision(
            decision_id="vd_0123456789abcdef",
            action="confirm",
            reviewer_id="orcamentista-sintetico",
            reviewer_role="orcamentista",
            decided_at=datetime(2026, 2, 1, 12, 0),
        )

    assert valuation_error_codes(raised.value) == ["DECISION_TIMESTAMP_NAIVE"]
