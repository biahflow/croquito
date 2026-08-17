"""Os validadores recomputam cada total e recusam com código estável."""

from __future__ import annotations

from decimal import Decimal

import pytest
from pydantic import ValidationError

from croquito_valuation.errors import valuation_error_codes
from croquito_valuation.models import (
    BulletinLine,
    CalcBlock,
    CalcOperand,
    CalcRecipe,
    CalcSheet,
    PriceCatalog,
    PriceCatalogEntry,
    PriceOrigin,
    Valuation,
    WorksiteBulletin,
)

_WORKSITE_KEY = "praca-sintetica-norte"


def _area_block(subtotal: str = "105.00") -> CalcBlock:
    return CalcBlock(
        label="PASSEIO NORTE",
        recipe=CalcRecipe.LENGTH_TIMES_WIDTH,
        operands=[
            CalcOperand(name="COMPRIMENTO", value=Decimal("12.50"), unit="m"),
            CalcOperand(name="LARGURA", value=Decimal("8.40"), unit="m"),
        ],
        subtotal=Decimal(subtotal),
    )


def _small_area_block() -> CalcBlock:
    return CalcBlock(
        label="PASSEIO LESTE",
        recipe=CalcRecipe.LENGTH_TIMES_WIDTH,
        operands=[
            CalcOperand(name="COMPRIMENTO", value=Decimal("6.00"), unit="m"),
            CalcOperand(name="LARGURA", value=Decimal("3.50"), unit="m"),
        ],
        subtotal=Decimal("21.00"),
    )


def _line(quantity: str = "126.00", total: str = "11251.80") -> BulletinLine:
    return BulletinLine(
        item_number="1",
        code="AD04050050(/)",
        description="PISO INTERTRAVADO SINTETICO 6CM",
        unit="m2",
        unit_price=Decimal("89.30"),
        quantity=Decimal(quantity),
        total=Decimal(total),
    )


def _catalog_entry(code: str = "AD04050050(/)", price: str = "89.30") -> PriceCatalogEntry:
    return PriceCatalogEntry(
        code=code,
        description="PISO INTERTRAVADO SINTETICO 6CM",
        unit="m2",
        unit_price=Decimal(price),
        family_code="AD",
        family_name="PAVIMENTACAO SINTETICA",
        subgroup_code="AD0405",
        subgroup_name="PISO INTERTRAVADO SINTETICO",
    )


def test_valid_block_and_sheet_pass() -> None:
    sheet = CalcSheet(
        worksite_key=_WORKSITE_KEY,
        item_number="1",
        blocks=[_area_block(), _small_area_block()],
        total_quantity=Decimal("126.00"),
    )

    assert sheet.expected_total_quantity == Decimal("126.00")


def test_block_subtotal_mismatch_is_reported_with_its_code() -> None:
    with pytest.raises(ValidationError) as raised:
        _area_block("104.99")

    assert valuation_error_codes(raised.value) == ["CALC_SUBTOTAL_MISMATCH"]


def test_block_with_deduction_subtracts_before_rounding() -> None:
    block = CalcBlock(
        label="ALAMBRADO DO CAMPO",
        recipe=CalcRecipe.PERIM_HEIGHT_MINUS_OPENINGS,
        operands=[
            CalcOperand(name="PERÍMETRO", value=Decimal("45.60"), unit="m"),
            CalcOperand(name="ALTURA", value=Decimal("2.00"), unit="m"),
        ],
        deductions=[CalcOperand(name="VÃOS", value=Decimal("6.00"), unit="m2")],
        subtotal=Decimal("85.20"),
    )

    assert block.expected_subtotal == Decimal("85.20")


def test_calc_sheet_total_mismatch_is_reported() -> None:
    with pytest.raises(ValidationError) as raised:
        CalcSheet(
            worksite_key=_WORKSITE_KEY,
            item_number="1",
            blocks=[_area_block()],
            total_quantity=Decimal("105.01"),
        )

    assert valuation_error_codes(raised.value) == ["CALC_TOTAL_MISMATCH"]


def test_line_total_must_be_truncated_not_rounded() -> None:
    line = BulletinLine(
        item_number="6",
        code="SP01050010(/)",
        description="ESCAVACAO SINTETICA MANUAL",
        unit="m3",
        unit_price=Decimal("10.30"),
        quantity=Decimal("1.15"),
        total=Decimal("11.84"),
    )
    assert line.expected_total == Decimal("11.84")

    with pytest.raises(ValidationError) as raised:
        BulletinLine(
            item_number="6",
            code="SP01050010(/)",
            description="ESCAVACAO SINTETICA MANUAL",
            unit="m3",
            unit_price=Decimal("10.30"),
            quantity=Decimal("1.15"),
            total=Decimal("11.85"),
        )

    assert valuation_error_codes(raised.value) == ["LINE_TOTAL_MISMATCH"]


def test_bulletin_line_accepts_a_bare_code_outside_the_sco_table() -> None:
    """`IE00040849` não é SCO, mas tem a estrutura que o contrato real usa fora da tabela."""
    line = BulletinLine(
        item_number="1",
        code="IE00040849",
        description="SERVICO CONTRATADO FORA DA TABELA SCO",
        unit="un",
        unit_price=Decimal("5.00"),
        quantity=Decimal("2.00"),
        total=Decimal("10.00"),
    )

    assert line.code == "IE00040849"


@pytest.mark.parametrize("code", ["LAZER / PAISAGISMO", "IE123"])
def test_bulletin_line_refuses_text_without_the_contract_code_structure(code: str) -> None:
    with pytest.raises(ValidationError) as raised:
        BulletinLine(
            item_number="1",
            code=code,
            description="SERVICO CONTRATADO FORA DA TABELA SCO",
            unit="un",
            unit_price=Decimal("5.00"),
            quantity=Decimal("2.00"),
            total=Decimal("10.00"),
        )

    assert [error["loc"] for error in raised.value.errors()] == [("code",)]


def test_decimal_field_refuses_float_input() -> None:
    with pytest.raises(ValidationError) as raised:
        BulletinLine(
            item_number="1",
            code="AD04050050(/)",
            description="PISO",
            unit="m2",
            unit_price=89.30,
            quantity=Decimal("126.00"),
            total=Decimal("11251.80"),
        )

    assert "DECIMAL_FROM_FLOAT" in valuation_error_codes(raised.value)


def test_bulletin_total_is_the_sum_of_already_truncated_totals() -> None:
    bulletin = WorksiteBulletin(
        worksite_key="praca-sintetica-norte",
        worksite_name="PRACA SINTETICA NORTE",
        lines=[_line()],
        total_amount=Decimal("11251.80"),
    )
    assert bulletin.expected_total_amount == Decimal("11251.80")

    with pytest.raises(ValidationError) as raised:
        WorksiteBulletin(
            worksite_key="praca-sintetica-norte",
            worksite_name="PRACA SINTETICA NORTE",
            lines=[_line()],
            total_amount=Decimal("11251.79"),
        )

    assert valuation_error_codes(raised.value) == ["BULLETIN_TOTAL_MISMATCH"]


def test_bulletin_refuses_duplicated_item_number() -> None:
    with pytest.raises(ValidationError) as raised:
        WorksiteBulletin(
            worksite_key="praca-sintetica-norte",
            worksite_name="PRACA SINTETICA NORTE",
            lines=[_line(), _line()],
            total_amount=Decimal("22503.60"),
        )

    assert valuation_error_codes(raised.value) == ["BULLETIN_DUPLICATE_ITEM"]


def test_catalog_refuses_duplicated_code() -> None:
    with pytest.raises(ValidationError) as raised:
        PriceCatalog(
            source_label="teste",
            reference_month="2026-01",
            source_sha256="0" * 64,
            entries=[_catalog_entry(), _catalog_entry(price="99.00")],
        )

    assert valuation_error_codes(raised.value) == ["CATALOG_DUPLICATE_CODE"]


# --------------------------------------------------------------------------------------
# origem de preço (M8): default sco ao reler artefato antigo, validação do código por
# origem e coerência de origem dentro de um catálogo
# --------------------------------------------------------------------------------------

_CATALOG_ENTRY_JSON_WITHOUT_ORIGIN: dict[str, object] = {
    "code": "AD04050050(/)",
    "description": "PISO INTERTRAVADO SINTETICO 6CM",
    "unit": "m2",
    "unit_price": "89.30",
    "family_code": "AD",
    "family_name": "PAVIMENTACAO SINTETICA",
    "subgroup_code": "AD0405",
    "subgroup_name": "PISO INTERTRAVADO SINTETICO",
}


def test_catalog_entry_defaults_to_sco_origin_when_rereading_json_without_the_field() -> None:
    """Todo artefato M1-M7 relido sem `origin` continua válido, sempre como `sco`."""
    entry = PriceCatalogEntry.model_validate(_CATALOG_ENTRY_JSON_WITHOUT_ORIGIN)

    assert entry.origin == PriceOrigin.SCO


def test_catalog_defaults_to_sco_origin_when_rereading_json_without_the_field() -> None:
    payload = {
        "source_label": "teste",
        "reference_month": "2026-01",
        "source_sha256": "0" * 64,
        "entries": [_CATALOG_ENTRY_JSON_WITHOUT_ORIGIN],
    }

    catalog = PriceCatalog.model_validate(payload)

    assert catalog.origin == PriceOrigin.SCO
    assert catalog.entries[0].origin == PriceOrigin.SCO


def test_an_sco_shaped_code_with_emop_origin_passes_the_structural_check() -> None:
    """Origem `emop`/`composition` usa o superset estrutural: um código SCO cabe nele."""
    entry = PriceCatalogEntry.model_validate({**_catalog_entry().model_dump(), "origin": "emop"})

    assert entry.origin == PriceOrigin.EMOP
    assert entry.code == "AD04050050(/)"


@pytest.mark.parametrize("origin", ["sco", "emop", "composition"])
def test_a_code_with_space_or_lowercase_is_refused_regardless_of_origin(origin: str) -> None:
    payload = {**_catalog_entry().model_dump(), "code": "ad 0405", "origin": origin}

    with pytest.raises(ValidationError) as raised:
        PriceCatalogEntry.model_validate(payload)

    assert valuation_error_codes(raised.value) == ["CATALOG_CODE_INVALID_FOR_ORIGIN"]


def test_a_non_sco_code_with_sco_origin_is_refused() -> None:
    payload = {**_catalog_entry().model_dump(), "code": "EMOP.AD.001"}

    with pytest.raises(ValidationError) as raised:
        PriceCatalogEntry.model_validate(payload)

    assert valuation_error_codes(raised.value) == ["CATALOG_CODE_INVALID_FOR_ORIGIN"]


def test_catalog_refuses_entries_whose_origin_does_not_match_the_catalog() -> None:
    """Um catálogo é uma fonte só; mistura de origem acontece na cascata (fase futura)."""
    sco_entry = _catalog_entry(code="AD04050050(/)")
    emop_entry = PriceCatalogEntry.model_validate(
        {**_catalog_entry().model_dump(), "code": "EMOP.AD.001", "origin": "emop"}
    )

    with pytest.raises(ValidationError) as raised:
        PriceCatalog(
            source_label="teste",
            reference_month="2026-01",
            source_sha256="0" * 64,
            entries=[sco_entry, emop_entry],
        )

    assert valuation_error_codes(raised.value) == ["CATALOG_ORIGIN_MIXED"]


def _bulletin(worksite_key: str = _WORKSITE_KEY) -> WorksiteBulletin:
    return WorksiteBulletin(
        worksite_key=worksite_key,
        worksite_name="PRACA SINTETICA NORTE",
        lines=[_line()],
        total_amount=Decimal("11251.80"),
    )


def _full_sheet(worksite_key: str = _WORKSITE_KEY) -> CalcSheet:
    return CalcSheet(
        worksite_key=worksite_key,
        item_number="1",
        blocks=[_area_block(), _small_area_block()],
        total_quantity=Decimal("126.00"),
    )


def test_valuation_requires_one_calc_sheet_per_line() -> None:
    with pytest.raises(ValidationError) as raised:
        Valuation(
            period_number=1,
            reference_label="JANEIRO/2026",
            bulletins=[_bulletin()],
            calc_sheets=[
                CalcSheet(
                    worksite_key=_WORKSITE_KEY,
                    item_number="2",
                    blocks=[_area_block()],
                    total_quantity=Decimal("105.00"),
                )
            ],
        )

    assert valuation_error_codes(raised.value) == ["VALUATION_CALC_SHEET_MISMATCH"]


def test_valuation_requires_matching_quantity() -> None:
    with pytest.raises(ValidationError) as raised:
        Valuation(
            period_number=1,
            reference_label="JANEIRO/2026",
            bulletins=[_bulletin()],
            calc_sheets=[
                CalcSheet(
                    worksite_key=_WORKSITE_KEY,
                    item_number="1",
                    blocks=[_area_block()],
                    total_quantity=Decimal("105.00"),
                )
            ],
        )

    assert valuation_error_codes(raised.value) == ["VALUATION_QUANTITY_MISMATCH"]


def test_valuation_accepts_the_consistent_case() -> None:
    valuation = Valuation(
        period_number=1,
        reference_label="JANEIRO/2026",
        bulletins=[_bulletin()],
        calc_sheets=[_full_sheet()],
    )

    assert valuation.schema_version == "2.0.0"
    assert valuation.calc_sheet_for(_WORKSITE_KEY, "1").total_quantity == Decimal("126.00")
    assert valuation.total_amount == Decimal("11251.80")


def test_valuation_refuses_two_bulletins_for_the_same_worksite() -> None:
    with pytest.raises(ValidationError) as raised:
        Valuation(
            period_number=1,
            reference_label="JANEIRO/2026",
            bulletins=[_bulletin(), _bulletin()],
            calc_sheets=[_full_sheet()],
        )

    assert valuation_error_codes(raised.value) == ["VALUATION_DUPLICATE_WORKSITE"]


def test_valuation_matches_calc_sheets_by_worksite_and_item() -> None:
    other_key = "praca-sintetica-sul"
    valuation = Valuation(
        period_number=1,
        reference_label="JANEIRO/2026",
        bulletins=[_bulletin(), _bulletin(other_key)],
        calc_sheets=[_full_sheet(), _full_sheet(other_key)],
    )

    assert valuation.calc_sheet_for(other_key, "1").worksite_key == other_key
    assert valuation.total_amount == Decimal("22503.60")

    with pytest.raises(ValidationError) as raised:
        Valuation(
            period_number=1,
            reference_label="JANEIRO/2026",
            bulletins=[_bulletin(), _bulletin("praca-sintetica-sul")],
            calc_sheets=[_full_sheet(), _full_sheet()],
        )

    assert valuation_error_codes(raised.value) == ["VALUATION_DUPLICATE_CALC_SHEET"]
