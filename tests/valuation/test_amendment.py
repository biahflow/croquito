"""RE-RA declarada: procedência, guard de declaração, item novo e vigente derivado (F-040)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from pydantic import ValidationError

from croquito_valuation.contract import (
    Amendment,
    AmendmentLine,
    ContractLine,
    ContractWorkbook,
    apply_declared_amendment,
)
from croquito_valuation.errors import ValuationValidationError, valuation_error_codes

_CODE = "AD04050050(/)"
_CODE_NEW = "MB01100010(/)"
_SOURCE_SHA256 = "a" * 64
_BRT = timezone(timedelta(hours=-3))


def _line(
    *,
    code: str = _CODE,
    item_number: str = "1",
    contract_quantity: str = "20.00",
    amended_quantity: str | None = None,
    balance_quantity: str | None = None,
) -> ContractLine:
    return ContractLine(
        group_label="PAVIMENTACAO",
        item_number=item_number,
        code=code,
        description="PISO INTERTRAVADO SINTETICO 6CM",
        unit="m2",
        unit_price=Decimal("10.00"),
        contract_quantity=Decimal(contract_quantity),
        amended_quantity=None if amended_quantity is None else Decimal(amended_quantity),
        periods=[],
        accumulated_quantity=Decimal("0.00"),
        accumulated_amount=Decimal("0.00"),
        balance_quantity=None if balance_quantity is None else Decimal(balance_quantity),
    )


def _workbook(*, lines: list[ContractLine], amendments: list[Amendment] | None = None) -> ContractWorkbook:
    return ContractWorkbook(
        source_label="MAPÃO SINTÉTICO (fixture)",
        source_sha256=_SOURCE_SHA256,
        period_numbers=[],
        lines=lines,
        amendments=amendments or [],
    )


def _declared(lines: list[AmendmentLine], *, label: str = "1ª RE-RA") -> Amendment:
    return Amendment(
        label=label,
        lines=lines,
        declared_by="Ana Medição",
        declared_at=datetime(2026, 8, 27, 10, 0, tzinfo=_BRT),
        reference_period="Processo 123/2026",
    )


def test_amendment_lida_do_mapao_nao_exige_procedencia() -> None:
    """A RE-RA sem procedência continua válida no modelo: é a leitura do MAPÃO histórico."""
    amendment = Amendment(label="RE-RA do MAPÃO", lines=[AmendmentLine(code=_CODE, quantity_delta=Decimal("-4.00"))])
    assert amendment.has_provenance is False


def test_declaracao_sem_procedencia_recusa_no_ato() -> None:
    amendment = Amendment(label="RE-RA", lines=[AmendmentLine(code=_CODE, quantity_delta=Decimal("-4.00"))])
    with pytest.raises(ValuationValidationError) as raised:
        amendment.ensure_declared()

    assert raised.value.code == "AMENDMENT_PROVENANCE_MISSING"
    assert set(raised.value.details["missing"]) == {"declared_by", "declared_at", "reference_period"}


def test_declaracao_com_instante_ingenuo_recusa() -> None:
    with pytest.raises(ValidationError) as raised:
        Amendment(
            label="RE-RA",
            lines=[AmendmentLine(code=_CODE, quantity_delta=Decimal("-4.00"))],
            declared_by="Ana",
            declared_at=datetime(2026, 8, 27, 10, 0),  # noqa: DTZ001 — o ponto do teste
            reference_period="Processo 123/2026",
        )

    assert valuation_error_codes(raised.value) == ["AMENDMENT_TIMESTAMP_NAIVE"]


def test_declaracao_completa_passa_no_guard() -> None:
    _declared([AmendmentLine(code=_CODE, quantity_delta=Decimal("-4.00"))]).ensure_declared()


def test_item_existente_nao_materializa_uma_segunda_fonte() -> None:
    with pytest.raises(ValidationError) as raised:
        AmendmentLine(
            code=_CODE,
            quantity_delta=Decimal("-4.00"),
            unit_price=Decimal("10.00"),
        )

    assert valuation_error_codes(raised.value) == ["AMENDMENT_MATERIALIZATION_UNEXPECTED"]


def test_vigente_derivado_reflete_a_re_ra_aplicada() -> None:
    workbook = _workbook(lines=[_line(contract_quantity="20.00")])
    declared = _declared([AmendmentLine(code=_CODE, quantity_delta=Decimal("-4.00"))])

    applied = apply_declared_amendment(workbook, declared)

    line = applied.line_for_code(_CODE)
    assert applied.current_quantity(line) == Decimal("16.00")
    assert applied.current_balance_quantity(line) == Decimal("16.00")
    assert applied.amendments[-1].has_provenance is True


def test_item_novo_nasce_materializado_do_catalogo() -> None:
    workbook = _workbook(lines=[_line(contract_quantity="20.00")])
    declared = _declared(
        [
            AmendmentLine(
                code=_CODE_NEW,
                quantity_delta=Decimal("6.00"),
                is_new_item=True,
                description="BANCO SINTETICO DE CONCRETO",
                unit="un",
                unit_price=Decimal("5.00"),
            )
        ]
    )

    applied = apply_declared_amendment(workbook, declared)

    created = applied.line_for_code(_CODE_NEW)
    assert created.contract_quantity == Decimal("0.00")
    assert created.description == "BANCO SINTETICO DE CONCRETO"
    assert created.unit == "un"
    assert created.unit_price == Decimal("5.00")
    # Contratual zero, vigente igual ao delta (ADR-0056, decisão 7).
    assert applied.current_quantity(created) == Decimal("6.00")


def test_item_novo_sem_materializacao_recusa() -> None:
    workbook = _workbook(lines=[_line(contract_quantity="20.00")])
    declared = _declared(
        [AmendmentLine(code=_CODE_NEW, quantity_delta=Decimal("6.00"), is_new_item=True)]
    )

    with pytest.raises(ValuationValidationError) as raised:
        apply_declared_amendment(workbook, declared)

    assert raised.value.code == "AMENDMENT_NEW_ITEM_INVALID"


def test_item_novo_em_consolidado_multigrupo_e_ambiguo() -> None:
    workbook = _workbook(
        lines=[
            _line(contract_quantity="20.00"),
            ContractLine(
                group_label="SERVICOS PRELIMINARES",
                item_number="1",
                code="SP01050010(/)",
                description="ESCAVACAO",
                unit="m3",
                unit_price=Decimal("20.00"),
                contract_quantity=Decimal("8.00"),
                periods=[],
                accumulated_quantity=Decimal("0.00"),
                accumulated_amount=Decimal("0.00"),
            ),
        ]
    )
    declared = _declared(
        [
            AmendmentLine(
                code=_CODE_NEW,
                quantity_delta=Decimal("6.00"),
                is_new_item=True,
                description="BANCO",
                unit="un",
                unit_price=Decimal("5.00"),
            )
        ]
    )

    with pytest.raises(ValuationValidationError) as raised:
        apply_declared_amendment(workbook, declared)

    assert raised.value.code == "AMENDMENT_NEW_ITEM_GROUP_AMBIGUOUS"


@pytest.mark.parametrize("schema_version", ["2.0.0", "3.0.0"])
def test_consolidado_gravado_antes_da_feature_continua_validando(schema_version: str) -> None:
    """Schema `2.0.0`/`3.0.0` com `amended_quantity` gravado responde com o vigente que trazia."""
    workbook = ContractWorkbook(
        schema_version=schema_version,
        source_label="MAPÃO SINTÉTICO (fixture)",
        source_sha256=_SOURCE_SHA256,
        period_numbers=[],
        lines=[_line(contract_quantity="20.00", amended_quantity="20.00", balance_quantity="20.00")],
    )

    line = workbook.line_for_code(_CODE)
    assert workbook.current_quantity(line) == Decimal("20.00")
    assert workbook.current_balance_quantity(line) == Decimal("20.00")
