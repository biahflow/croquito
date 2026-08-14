"""O template é dado: os layouts novos recusam configuração ambígua com código estável."""

from __future__ import annotations

from decimal import Decimal

import pytest
from pydantic import ValidationError

from croquito_valuation.errors import valuation_error_codes
from croquito_valuation.template import (
    AmendmentColumns,
    AmendmentLayout,
    CatalogLayout,
    GeneralLayout,
    WorkbookTemplate,
    default_template,
)


def _general(
    *,
    sheet_name: str = "PLANILHA GERAL",
    unit_price_column: str = "G",
    period_label_pattern: str = "{n}ª MEDIÇÃO",
    pair_sublabel_row: int | None = 4,
    data_first_row: int = 5,
    amended_quantity_column: str | None = "H",
    quantity_decimal_scale: int = 2,
) -> GeneralLayout:
    return GeneralLayout(
        sheet_name=sheet_name,
        title="PLANILHA GERAL DO CONTRATO",
        header_row=3,
        pair_sublabel_row=pair_sublabel_row,
        data_first_row=data_first_row,
        group_column="A",
        item_column="B",
        code_column="C",
        description_column="D",
        unit_column="E",
        contract_quantity_column="F",
        unit_price_column=unit_price_column,
        amended_quantity_column=amended_quantity_column,
        first_period_column="I",
        period_label_pattern=period_label_pattern,
        quantity_decimal_scale=quantity_decimal_scale,
    )


def test_default_template_declares_the_general_and_amendment_layouts() -> None:
    template = default_template()

    assert template.general.sheet_name == "PLANILHA GERAL"
    assert template.general.first_period_column == "I"
    assert template.general.pair_sublabel_row == 6
    assert template.general.data_first_row == 7
    assert template.amendment is not None
    assert template.amendment.data_first_row == 5
    assert [block.label for block in template.amendment.blocks] == ["1ª RE-RA"]
    assert template.amendment.section_rows_carry_group_subtotal is False


def _catalog(
    *,
    code_column: str = "C",
    family_column: str | None = "A",
    subgroup_intermediate_column: str | None = "B",
    note_prefixes: list[str] | None = None,
    unpriced_markers: list[str] | None = None,
) -> CatalogLayout:
    return CatalogLayout(
        sheet_name="FGV06",
        first_row=4,
        code_column=code_column,
        description_column="D",
        unit_column="E",
        price_column="F",
        family_column=family_column,
        subgroup_intermediate_column=subgroup_intermediate_column,
        note_prefixes=[] if note_prefixes is None else note_prefixes,
        unpriced_markers=[] if unpriced_markers is None else unpriced_markers,
    )


def test_default_template_keeps_the_hierarchy_in_the_code_column() -> None:
    layout = default_template().catalog

    assert layout.family_column is None
    assert layout.subgroup_intermediate_column is None
    assert layout.hierarchy_columns is None
    assert layout.declared_columns == ("A", "B", "C", "D")


def test_catalog_layout_accepts_the_full_column_hierarchy() -> None:
    layout = _catalog()

    assert layout.hierarchy_columns == ("A", "B")
    assert layout.declared_columns == ("A", "B", "C", "D", "E", "F")
    assert layout.note_prefixes == []
    assert layout.is_unpriced("sem cotação") is False


def test_catalog_layout_recognizes_only_the_declared_unpriced_marker() -> None:
    layout = _catalog(unpriced_markers=["sem cotação"])

    assert layout.is_unpriced("  Sem  Cotação ") is True
    assert layout.is_unpriced("a combinar") is False
    assert layout.is_unpriced(Decimal("10.00")) is False


@pytest.mark.parametrize(
    ("note_prefixes", "unpriced_markers"),
    [(["N"], []), ([], [" a "])],
)
def test_catalog_layout_refuses_a_declared_text_that_matches_almost_anything(
    note_prefixes: list[str], unpriced_markers: list[str]
) -> None:
    with pytest.raises(ValidationError) as raised:
        _catalog(note_prefixes=note_prefixes, unpriced_markers=unpriced_markers)

    assert valuation_error_codes(raised.value) == ["TEMPLATE_CATALOG_TEXT_INVALID"]


@pytest.mark.parametrize(
    ("family_column", "subgroup_intermediate_column"),
    [("A", None), (None, "B")],
)
def test_catalog_layout_refuses_half_of_the_column_hierarchy(
    family_column: str | None, subgroup_intermediate_column: str | None
) -> None:
    with pytest.raises(ValidationError) as raised:
        _catalog(
            family_column=family_column,
            subgroup_intermediate_column=subgroup_intermediate_column,
        )

    assert valuation_error_codes(raised.value) == ["TEMPLATE_CATALOG_HIERARCHY_INCOMPLETE"]


def test_catalog_layout_refuses_two_columns_on_the_same_letter() -> None:
    with pytest.raises(ValidationError) as raised:
        _catalog(code_column="B")

    assert valuation_error_codes(raised.value) == ["TEMPLATE_DUPLICATE_COLUMN"]


def test_general_layout_names_each_period_from_the_declared_pattern() -> None:
    layout = _general()

    assert layout.period_label(1) == "1ª MEDIÇÃO"
    assert layout.period_label(19) == "19ª MEDIÇÃO"


@pytest.mark.parametrize(
    ("pattern", "text", "expected"),
    [
        ("{n}ª MEDIÇÃO", "1ª MEDIÇÃO", 1),
        # O arquivo do cliente escreve sufixo livre e nem sempre fecha o parêntese.
        ("{n}ª MEDIÇÃO", "11ª MEDIÇÃO - COMPLEMENTAR", 11),
        ("{n}ª MEDIÇÃO", "13ª MEDIÇÃO (COMPLEMENTAR", 13),
        ("{n}ª MEDIÇÃO", "15ª MEDIÇÃO - 11ª ETAPA", 15),
        ("MEDIÇÃO {n}", "MEDIÇÃO 7 COMPLEMENTAR", 7),
        ("{n}ª MEDIÇÃO", "ACUMULADO", None),
        ("{n}ª MEDIÇÃO", "SALDO", None),
        ("{n}ª MEDIÇÃO", "MEDIÇÃO", None),
        ("{n}ª MEDIÇÃO", "", None),
    ],
)
def test_general_layout_reads_the_measurement_number_from_the_written_label(
    pattern: str, text: str, expected: int | None
) -> None:
    assert _general(period_label_pattern=pattern).parse_period_label(text) == expected


def test_general_layout_accepts_a_sheet_without_the_amended_quantity_column() -> None:
    layout = _general(amended_quantity_column=None)

    assert layout.amended_quantity_column is None
    assert layout.fixed_columns == ("A", "B", "C", "D", "E", "F", "G", "I")
    assert default_template().general.amended_quantity_column == "H"


def test_general_layout_declares_the_decimal_scale_of_the_quantities() -> None:
    assert _general().quantity_decimal_scale == 2
    assert _general(quantity_decimal_scale=4).quantity_decimal_scale == 4


@pytest.mark.parametrize("scale", [1, 7])
def test_general_layout_refuses_a_quantity_scale_outside_the_limits(scale: int) -> None:
    with pytest.raises(ValidationError) as raised:
        _general(quantity_decimal_scale=scale)

    assert [error["loc"] for error in raised.value.errors()] == [("quantity_decimal_scale",)]


def test_general_layout_refuses_data_before_the_header() -> None:
    with pytest.raises(ValidationError) as raised:
        _general(pair_sublabel_row=None, data_first_row=3)

    assert valuation_error_codes(raised.value) == ["TEMPLATE_ROW_ORDER_INVALID"]


def test_general_layout_refuses_data_before_the_pair_sublabels() -> None:
    with pytest.raises(ValidationError) as raised:
        _general(pair_sublabel_row=6, data_first_row=5)

    assert valuation_error_codes(raised.value) == ["TEMPLATE_ROW_ORDER_INVALID"]


def test_amendment_layout_refuses_data_before_the_header() -> None:
    with pytest.raises(ValidationError) as raised:
        AmendmentLayout(
            sheet_name="MAPÃO - PREFEITURA",
            header_row=4,
            data_first_row=4,
            code_column="C",
            blocks=[AmendmentColumns(label="1ª RE-RA", added_column="J")],
        )

    assert valuation_error_codes(raised.value) == ["TEMPLATE_ROW_ORDER_INVALID"]


def test_general_layout_refuses_two_columns_on_the_same_letter() -> None:
    with pytest.raises(ValidationError) as raised:
        _general(unit_price_column="F")

    assert valuation_error_codes(raised.value) == ["TEMPLATE_DUPLICATE_COLUMN"]


def test_general_layout_refuses_a_period_label_without_the_placeholder() -> None:
    with pytest.raises(ValidationError) as raised:
        _general(period_label_pattern="MEDIÇÃO")

    assert valuation_error_codes(raised.value) == ["TEMPLATE_PERIOD_PATTERN_INVALID"]


def test_general_layout_refuses_a_sheet_name_the_workbook_cannot_hold() -> None:
    with pytest.raises(ValidationError) as raised:
        _general(sheet_name="PLANILHA GERAL/CONSOLIDADA")

    assert valuation_error_codes(raised.value) == ["SHEET_NAME_INVALID_CHARS"]


def test_amendment_block_needs_at_least_one_column() -> None:
    with pytest.raises(ValidationError) as raised:
        AmendmentColumns(label="1ª RE-RA")

    assert valuation_error_codes(raised.value) == ["TEMPLATE_AMENDMENT_BLOCK_EMPTY"]


def _with_extra_code_patterns(patterns: list[str]) -> WorkbookTemplate:
    template = default_template()
    payload = template.model_dump()
    payload["extra_code_patterns"] = patterns
    return WorkbookTemplate.model_validate(payload)


def test_template_accepts_a_declared_extra_code_pattern() -> None:
    template = _with_extra_code_patterns([r"^IE\d{8}$"])

    assert template.matches_extra_code("IE00040849") is True
    assert template.matches_extra_code("AD04050050(/)") is False
    assert template.matches_extra_code("LAZER / PAISAGISMO") is False


def test_template_without_extra_patterns_matches_nothing() -> None:
    assert default_template().matches_extra_code("IE00040849") is False


def test_template_refuses_an_extra_pattern_that_does_not_compile() -> None:
    with pytest.raises(ValidationError) as raised:
        _with_extra_code_patterns(["(unclosed"])

    assert valuation_error_codes(raised.value) == ["TEMPLATE_EXTRA_CODE_PATTERN_INVALID"]


def test_template_refuses_an_extra_pattern_that_matches_the_empty_string() -> None:
    with pytest.raises(ValidationError) as raised:
        _with_extra_code_patterns([r"^IE\d{8}$|^$"])

    assert valuation_error_codes(raised.value) == ["TEMPLATE_EXTRA_CODE_PATTERN_INVALID"]


def test_template_refuses_an_extra_pattern_that_matches_a_section_title() -> None:
    """Padrão frouxo demais (`.+`) casaria `LAZER / PAISAGISMO`: o validador recusa."""
    with pytest.raises(ValidationError) as raised:
        _with_extra_code_patterns([r".+"])

    assert valuation_error_codes(raised.value) == ["TEMPLATE_EXTRA_CODE_PATTERN_INVALID"]


def test_template_refuses_two_sheets_with_the_same_name() -> None:
    template = default_template()
    conflicting = AmendmentLayout(
        sheet_name=template.general.sheet_name,
        header_row=3,
        data_first_row=4,
        code_column="C",
        blocks=[AmendmentColumns(label="1ª RE-RA", added_column="J")],
    )

    with pytest.raises(ValidationError) as raised:
        WorkbookTemplate.model_validate(
            {**template.model_dump(), "amendment": conflicting.model_dump()}
        )

    assert valuation_error_codes(raised.value) == ["TEMPLATE_SHEET_NAME_CONFLICT"]
