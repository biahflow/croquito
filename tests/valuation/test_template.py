"""O template é dado: os layouts novos recusam configuração ambígua com código estável."""

from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal

import pytest
from pydantic import ValidationError

from croquito_valuation.errors import ValuationValidationError, valuation_error_codes
from croquito_valuation.template import (
    AmendmentColumns,
    AmendmentLayout,
    CatalogLayout,
    EstimateTemplateColumns,
    EstimateTemplateLayout,
    EstimateTemplateRow,
    GeneralLayout,
    SheetColumn,
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


def _grid_rows(
    *, codes: Sequence[str] = ("SIN.A.001", "SIN.B.001"), items: Sequence[str] = ("01.1", "01.2")
) -> list[EstimateTemplateRow]:
    return [
        EstimateTemplateRow(
            group=item.split(".")[0],
            item=item,
            code=code,
            description=f"LINHA SINTETICA {item}",
            unit="m2",
        )
        for code, item in zip(codes, items, strict=True)
    ]


def _grid_layout(**overrides: object) -> EstimateTemplateLayout:
    payload: dict[str, object] = {
        "sheet_name": "PLANILHA ORÇAMENTÁRIA",
        "title": "PLANILHA ORÇAMENTÁRIA",
        "revision_label": "REV. 0",
        "memory_sheet_name": "MEMÓRIA ORÇAMENTO",
        "header_row": 7,
        "columns": EstimateTemplateColumns(
            group=SheetColumn(letter="A", label="GRUPO"),
            item=SheetColumn(letter="B", label="ITEM"),
            code=SheetColumn(letter="C", label="CÓDIGO"),
            description=SheetColumn(letter="D", label="ESPECIFICAÇÃO"),
            unit=SheetColumn(letter="E", label="UN"),
            quantity=SheetColumn(letter="F", label="QUANT"),
            unit_price=SheetColumn(letter="G", label="VALOR UNIT"),
            total=SheetColumn(letter="H", label="TOTAL"),
        ),
        "rows": _grid_rows(),
    }
    payload.update(overrides)
    return EstimateTemplateLayout.model_validate(payload)


def test_estimate_grid_keeps_group_and_item_as_written_text() -> None:
    """Zero à esquerda e a forma `GG.N` são o documento; o modelo não os recomputa."""
    layout = _grid_layout(rows=_grid_rows(items=("01.1", "04.10")))

    assert [row.item for row in layout.rows] == ["01.1", "04.10"]
    assert [row.group for row in layout.rows] == ["01", "04"]
    assert layout.row_index_by_code == {"SIN.A.001": 0, "SIN.B.001": 1}


def test_estimate_grid_refuses_a_code_that_is_not_a_catalog_code() -> None:
    with pytest.raises(ValidationError) as raised:
        EstimateTemplateRow(
            group="01",
            item="01.1",
            code="codigo com espaco",
            description="LINHA INVALIDA",
            unit="m",
        )

    assert valuation_error_codes(raised.value) == ["TEMPLATE_ESTIMATE_GRID_CODE_INVALID"]


def test_estimate_grid_refuses_the_same_code_on_two_rows() -> None:
    """O índice código→linha exige unicidade: repetido, a quantidade cairia à sorte."""
    with pytest.raises(ValidationError) as raised:
        _grid_layout(rows=_grid_rows(codes=("SIN.A.001", "SIN.A.001")))

    assert valuation_error_codes(raised.value) == ["TEMPLATE_ESTIMATE_GRID_DUPLICATE_CODE"]


def test_estimate_grid_refuses_the_same_item_number_on_two_rows() -> None:
    with pytest.raises(ValidationError) as raised:
        _grid_layout(rows=_grid_rows(items=("01.1", "01.1")))

    assert valuation_error_codes(raised.value) == ["TEMPLATE_ESTIMATE_GRID_DUPLICATE_ITEM"]


def test_estimate_grid_refuses_the_memory_sheet_with_the_name_of_the_grid() -> None:
    with pytest.raises(ValidationError) as raised:
        _grid_layout(memory_sheet_name="PLANILHA ORÇAMENTÁRIA")

    assert valuation_error_codes(raised.value) == ["TEMPLATE_SHEET_NAME_CONFLICT"]


def test_estimate_grid_refuses_two_columns_on_the_same_letter() -> None:
    with pytest.raises(ValidationError) as raised:
        EstimateTemplateColumns(
            group=SheetColumn(letter="A", label="GRUPO"),
            item=SheetColumn(letter="A", label="ITEM"),
            code=SheetColumn(letter="C", label="CÓDIGO"),
            description=SheetColumn(letter="D", label="ESPECIFICAÇÃO"),
            unit=SheetColumn(letter="E", label="UN"),
            quantity=SheetColumn(letter="F", label="QUANT"),
            unit_price=SheetColumn(letter="G", label="VALOR UNIT"),
            total=SheetColumn(letter="H", label="TOTAL"),
        )

    assert valuation_error_codes(raised.value) == ["TEMPLATE_DUPLICATE_COLUMN"]


def test_template_refuses_a_grid_sheet_that_collides_with_another_declared_sheet() -> None:
    """A aba do gabarito entra no mesmo cheque de conflito das demais abas do template."""
    template = default_template()

    with pytest.raises(ValidationError) as raised:
        WorkbookTemplate.model_validate(
            {
                **template.model_dump(),
                "estimate_grid": _grid_layout(sheet_name=template.general.sheet_name).model_dump(),
            }
        )

    assert valuation_error_codes(raised.value) == ["TEMPLATE_SHEET_NAME_CONFLICT"]


def test_the_default_template_declares_no_grid() -> None:
    """Sem gabarito declarado nada muda: é o que mantém a rodada de hoje intacta."""
    assert default_template().estimate_grid is None


# --------------------------------------------------------------------------------------
# o nome de praça real dentro do teto de 31 caracteres da aba
# --------------------------------------------------------------------------------------

# As praças deste produto, como elas se chamam. "Campo do Morro da Bandeira" tem 26
# caracteres e `MEMÓRIA ` come 8: sem forma curta, praça de nome real não exporta.
_PRACAS_REAIS: Sequence[str] = (
    "Campo do Guaxindiba",
    "Praça Noel de Carvalho",
    "Praça Raul Campelo",
    "Campo do Morro da Bandeira",
    "Praça das Casinhas",
    "Campo da Toca",
)


def test_the_worksite_budget_is_the_smallest_of_the_two_sheets() -> None:
    """BM e MEMÓRIA da mesma obra se chamam igual, então quem manda é a aba mais apertada."""
    template = default_template()

    assert template.worksite_sheet_budget == 23  # 31 - len("MEMÓRIA ")


@pytest.mark.parametrize("worksite_name", _PRACAS_REAIS)
@pytest.mark.parametrize("suffix", ["", " P1", " P2", " P9", " P10"])
def test_every_real_worksite_name_fits_the_sheet_with_one_or_many_plates(
    worksite_name: str, suffix: str
) -> None:
    """Critério 2: nenhuma praça deste produto quebra a pasta, com uma folha ou com dez."""
    template = default_template()
    derived = f"{worksite_name}{suffix}"

    bulletin = template.bulletin_sheet_name(derived)
    memory = template.memory_sheet_name(derived)

    assert len(bulletin) <= 31
    assert len(memory) <= 31
    # BM e MEMÓRIA da mesma folha carregam o MESMO rótulo; quem confere abre as duas juntas.
    assert bulletin.removeprefix("BM ") == memory.removeprefix("MEMÓRIA ")


@pytest.mark.parametrize(
    ("worksite_name", "expected"),
    [
        # Degrau 1: cabe inteiro, e a aba é a de hoje caractere a caractere.
        ("PRACA SINTETICA NORTE", "MEMÓRIA PRACA SINTETICA NORTE"),
        ("Campo da Toca P2", "MEMÓRIA Campo da Toca P2"),
        # Degrau 2: caem as partículas de ligação, nenhuma palavra que nomeia se perde.
        ("Campo do Morro da Bandeira", "MEMÓRIA Campo Morro Bandeira"),
        ("Praça Noel de Carvalho P2", "MEMÓRIA Praça Noel Carvalho P2"),
        # Degrau 3: a palavra do MEIO é abreviada; o tipo e a folha ficam inteiros.
        ("PRACA SINTETICA NORTE P1", "MEMÓRIA PRACA SINT. NORTE P1"),
        ("Campo do Morro da Bandeira P10", "MEMÓRIA Campo Morro Band. P10"),
    ],
)
def test_the_sheet_label_shortens_in_declared_steps(worksite_name: str, expected: str) -> None:
    """Cada degrau é uma decisão escrita, não um truncamento: o teste fixa qual é qual."""
    assert default_template().memory_sheet_name(worksite_name) == expected


def test_a_name_that_already_fits_is_never_touched() -> None:
    """Não-regressão: a pasta que a prefeitura já recebe não muda de nome de aba."""
    template = default_template()

    assert template.bulletin_sheet_name("PRACA SINTETICA NORTE") == "BM PRACA SINTETICA NORTE"
    assert template.memory_sheet_name("PRACA SINTETICA NORTE") == "MEMÓRIA PRACA SINTETICA NORTE"


def test_a_name_that_does_not_fit_even_shortened_is_refused_with_the_limit() -> None:
    """Nome impossível recusa dizendo o teto e o que fazer, em vez de virar aba truncada."""
    template = default_template()

    with pytest.raises(ValuationValidationError) as raised:
        template.memory_sheet_name("Complexo Poliesportivo Municipal")

    assert raised.value.code == "WORKSITE_NAME_DOES_NOT_FIT_SHEET"
    assert raised.value.details["limit"] == 23
    assert "23 caracteres" in raised.value.message


def test_a_pattern_with_two_placeholders_is_refused() -> None:
    """O orçamento da aba desconta o padrão uma vez; dois marcadores mentiriam a conta."""
    template = default_template()

    with pytest.raises(ValidationError) as raised:
        WorkbookTemplate.model_validate(
            {**template.model_dump(), "memory_sheet_pattern": "M {worksite} {worksite}"}
        )

    assert valuation_error_codes(raised.value) == ["TEMPLATE_SHEET_PATTERN_INVALID"]
