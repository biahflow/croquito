"""A planilha gerada é reaberta, recomputada e conferida centavo a centavo."""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

import pytest
from openpyxl import load_workbook

from croquitodxf_valuation.canonical import audit_workbook, canonicalize_workbook
from croquitodxf_valuation.contract import ContractWorkbook
from croquitodxf_valuation.errors import ValuationValidationError
from croquitodxf_valuation.models import BulletinLine, PriceCatalog, Valuation
from croquitodxf_valuation.template import WorkbookTemplate, default_template
from croquitodxf_valuation.workbook_reader import read_contract_workbook
from croquitodxf_valuation.workbook_writer import (
    PlannedCell,
    plan_workbook,
    write_valuation_workbook,
)
from tests.valuation.builders import (
    PREVIOUS_MAPAO_CONTRACT_LABEL,
    PREVIOUS_MAPAO_SOURCE_LABEL,
    MeasuredItem,
    MeasuredWorksite,
    ValuationFixture,
    bake_formula_values,
    build_approval,
    build_catalog_for_contract,
    build_fixture,
    build_multi_worksite_valuation,
    build_previous_mapao_workbook,
    build_valuation_from_catalog,
    tamper_cell,
    template_without_amended_column,
    write_fixture_workbook,
)


def _cells(canonical: dict[str, object], sheet_name: str) -> dict[str, dict[str, object]]:
    sheets = canonical["sheets"]
    assert isinstance(sheets, list)
    for sheet in sheets:
        assert isinstance(sheet, dict)
        if sheet["name"] == sheet_name:
            cells = sheet["cells"]
            assert isinstance(cells, list)
            return {str(cell["ref"]): cell for cell in cells}
    raise AssertionError(f"aba ausente no canônico: {sheet_name}")


def _all_cells(canonical: dict[str, object]) -> list[dict[str, object]]:
    sheets = canonical["sheets"]
    assert isinstance(sheets, list)
    cells: list[dict[str, object]] = []
    for sheet in sheets:
        assert isinstance(sheet, dict)
        sheet_cells = sheet["cells"]
        assert isinstance(sheet_cells, list)
        cells.extend(sheet_cells)
    return cells


def _write(fixture: ValuationFixture, tmp_path: Path) -> Path:
    workbook_path = tmp_path / "medicao.xlsx"
    write_fixture_workbook(fixture, workbook_path)
    return workbook_path


def test_roundtrip_matches_the_valuation_cent_by_cent(tmp_path: Path) -> None:
    fixture = build_fixture(tmp_path)
    workbook_path = _write(fixture, tmp_path)

    report = audit_workbook(workbook_path, fixture.valuation, fixture.catalog, fixture.template)

    assert report.status == "ok"
    assert report.findings == []
    assert report.total_amount == fixture.valuation.total_amount

    canonical = canonicalize_workbook(workbook_path, fixture.template)
    bulletin_cells = _cells(canonical, report.worksites[0].bulletin_sheet)
    totals = [
        cell["value"]
        for ref, cell in bulletin_cells.items()
        if ref.startswith("G") and cell["kind"] in {"number", "formula"}
    ]
    for line in fixture.valuation.bulletins[0].lines:
        assert str(line.total) in totals
    assert str(fixture.valuation.total_amount) in totals
    assert "11.84" in totals, "o par 1,15 x 10,30 prova que dinheiro trunca"


def test_emitted_formulas_stay_inside_the_closed_grammar(tmp_path: Path) -> None:
    fixture = build_fixture(tmp_path)
    workbook_path = _write(fixture, tmp_path)

    canonical = canonicalize_workbook(workbook_path, fixture.template)
    formulas = [str(cell["formula"]) for cell in _all_cells(canonical) if cell["kind"] == "formula"]

    assert any(formula.startswith("=TRUNC(") for formula in formulas)
    assert any(formula.startswith("=SUM(") for formula in formulas)
    assert any(formula.startswith("=ROUND(PRODUCT(") for formula in formulas)
    assert any("),2)-" in formula for formula in formulas)
    for formula in formulas:
        assert formula.startswith(("=TRUNC(", "=SUM(", "=ROUND(PRODUCT("))


def test_pinned_cell_is_written_as_a_literal_and_listed_in_the_audit(tmp_path: Path) -> None:
    fixture = build_fixture(tmp_path)
    workbook_path = tmp_path / "medicao.xlsx"
    write_report = write_fixture_workbook(fixture, workbook_path)

    assert write_report.pinned_cells, "a fixture precisa exercitar o ramo de célula fixada"
    report = audit_workbook(workbook_path, fixture.valuation, fixture.catalog, fixture.template)
    assert [pinned.ref for pinned in report.pinned_cells] == [
        pinned.ref for pinned in write_report.pinned_cells
    ]

    canonical = canonicalize_workbook(workbook_path, fixture.template)
    for pinned in write_report.pinned_cells:
        cell = _cells(canonical, pinned.sheet)[pinned.ref]
        assert cell["kind"] == "number"
        assert cell["value"] == str(pinned.value)
        assert pinned.reason == "TRUNC_DOUBLE_DIVERGENCE"


@pytest.mark.parametrize(
    "formula",
    [
        "=IF(F8>0,F8*E8,0)",
        "='BM X'!G12",
        "=H9-J9-K9",
        # `SUM` de argumento único fica fora da forma 5: a lista começa em duas refs.
        "=SUM(H9)",
    ],
)
def test_formula_outside_the_grammar_is_refused(tmp_path: Path, formula: str) -> None:
    fixture = build_fixture(tmp_path)
    workbook_path = _write(fixture, tmp_path)

    workbook = load_workbook(workbook_path)
    worksheet = workbook[fixture.template.bulletin_sheet_name("PRACA SINTETICA NORTE")]
    worksheet["G8"] = formula
    workbook.save(workbook_path)

    with pytest.raises(ValuationValidationError) as raised:
        canonicalize_workbook(workbook_path, fixture.template)

    assert raised.value.code == "FORMULA_UNSUPPORTED"
    assert raised.value.details["ref"] == "G8"


def test_audit_detects_a_tampered_quantity(tmp_path: Path) -> None:
    fixture = build_fixture(tmp_path)
    workbook_path = _write(fixture, tmp_path)

    workbook = load_workbook(workbook_path)
    worksheet = workbook[fixture.template.bulletin_sheet_name("PRACA SINTETICA NORTE")]
    worksheet["F8"] = Decimal("999.00")
    workbook.save(workbook_path)

    report = audit_workbook(workbook_path, fixture.valuation, fixture.catalog, fixture.template)

    assert report.status == "divergent"
    codes = {finding.code for finding in report.findings}
    assert "CELL_VALUE_MISMATCH" in codes
    assert {finding.ref for finding in report.findings} >= {"F8", "G8", "G16"}


def test_writer_refuses_a_price_that_is_not_in_the_catalog(tmp_path: Path) -> None:
    fixture = build_fixture(tmp_path)
    lines = list(fixture.valuation.bulletins[0].lines)
    tampered = BulletinLine(
        item_number=lines[0].item_number,
        code=lines[0].code,
        description=lines[0].description,
        unit=lines[0].unit,
        unit_price=Decimal("99.99"),
        quantity=lines[0].quantity,
        total=Decimal("12598.74"),
    )
    payload = fixture.valuation.model_dump()
    payload["bulletins"][0]["lines"][0] = tampered.model_dump()
    payload["bulletins"][0]["total_amount"] = sum(
        (line["total"] for line in payload["bulletins"][0]["lines"]), Decimal("0.00")
    )
    valuation = Valuation.model_validate(payload)

    with pytest.raises(ValuationValidationError) as raised:
        write_fixture_workbook(
            ValuationFixture(
                catalog_path=fixture.catalog_path,
                template=fixture.template,
                catalog=fixture.catalog,
                valuation=valuation,
            ),
            tmp_path / "divergente.xlsx",
        )

    assert raised.value.code == "LINE_PRICE_NOT_IN_CATALOG"


@dataclass(frozen=True, slots=True)
class _MultiWorksiteFixture:
    """Consolidado importado, catálogo do contrato e a medição de três obras."""

    template: WorkbookTemplate
    contract: ContractWorkbook
    catalog: PriceCatalog
    valuation: Valuation


def _multi_worksite(tmp_path: Path) -> _MultiWorksiteFixture:
    template = default_template()
    previous = build_previous_mapao_workbook(tmp_path / "mapao-anterior.xlsx")
    contract = read_contract_workbook(
        previous.workbook_path,
        template,
        source_label=PREVIOUS_MAPAO_SOURCE_LABEL,
        contract_label=PREVIOUS_MAPAO_CONTRACT_LABEL,
    )
    catalog = build_catalog_for_contract(tmp_path / "catalogo-contrato.xlsx", contract)
    return _MultiWorksiteFixture(
        template=template,
        contract=contract,
        catalog=catalog,
        valuation=build_multi_worksite_valuation(contract),
    )


def _write_multi(fixture: _MultiWorksiteFixture, tmp_path: Path) -> Path:
    output = tmp_path / "medicao-consolidada.xlsx"
    write_valuation_workbook(
        fixture.valuation,
        fixture.catalog,
        fixture.template,
        output,
        contract=fixture.contract,
    )
    return output


def _planned_cell(
    fixture: _MultiWorksiteFixture, role: str, item_number: str | None = None
) -> PlannedCell:
    plan = plan_workbook(fixture.valuation, fixture.catalog, fixture.template, fixture.contract)
    for sheet in plan.sheets:
        if sheet.name != fixture.template.general.sheet_name:
            continue
        for cell in sheet.cells:
            if cell.role == role and (item_number is None or cell.item_number == item_number):
                return cell
    raise AssertionError(f"célula ausente do plano da geral: {role}/{item_number}")


# Código: (vigente, acumulado depois desta medição, saldo depois desta medição).
_AFTER_MEASUREMENT: dict[str, tuple[str, str, str]] = {
    "AD04050050(/)": ("16.00", "10.00", "6.00"),
    "AD04050055(A)": ("10.00", "9.99", "0.01"),
    "AD04050055(B)": ("6.00", "3.00", "3.00"),
    "SP01050010(/)": ("8.00", "3.75", "4.25"),
    "SP01050015(A)": ("0.00", "0.00", "0.00"),
    "MB01100010(/)": ("6.00", "4.00", "2.00"),
}


def test_multi_worksite_workbook_carries_general_amendments_and_every_pair(
    tmp_path: Path,
) -> None:
    fixture = _multi_worksite(tmp_path)
    output = _write_multi(fixture, tmp_path)

    report = audit_workbook(
        output,
        fixture.valuation,
        fixture.catalog,
        fixture.template,
        fixture.contract,
    )

    assert report.status == "ok"
    assert report.findings == []
    assert report.total_amount == fixture.valuation.total_amount == Decimal("117.50")
    assert report.general_sheet == fixture.template.general.sheet_name
    assert fixture.template.amendment is not None
    assert report.amendment_sheet == fixture.template.amendment.sheet_name
    assert [worksite.worksite_key for worksite in report.worksites] == [
        bulletin.worksite_key for bulletin in fixture.valuation.bulletins
    ]

    workbook = load_workbook(output)
    try:
        names = list(workbook.sheetnames)
    finally:
        workbook.close()
    assert names[0] == fixture.template.general.sheet_name
    assert names[1] == fixture.template.amendment.sheet_name
    for worksite in report.worksites:
        assert worksite.bulletin_sheet in names
        assert worksite.memory_sheet in names

    # O portão de exportação vê a mesma medição fechar contra o consolidado.
    assert build_approval(fixture.valuation).export_errors(fixture.contract) == []


def test_the_six_accepted_forms_show_up_in_the_consolidated_workbook(tmp_path: Path) -> None:
    fixture = _multi_worksite(tmp_path)
    output = _write_multi(fixture, tmp_path)

    canonical = canonicalize_workbook(output, fixture.template)
    formulas = [str(cell["formula"]) for cell in _all_cells(canonical) if cell["kind"] == "formula"]

    ref = r"[A-Z]+\d+"
    shapes = (
        rf"=TRUNC\({ref}\*{ref},2\)",
        rf"=ROUND\(PRODUCT\({ref}:{ref}\),2\)",
        rf"=ROUND\(PRODUCT\({ref}:{ref}\),2\)-{ref}",
        rf"=SUM\({ref}:{ref}\)",
        rf"=SUM\({ref}(,{ref})+\)",
        rf"={ref}-{ref}",
    )
    for shape in shapes:
        assert any(re.fullmatch(shape, formula) for formula in formulas), shape
    for formula in formulas:
        assert any(re.fullmatch(shape, formula) for shape in shapes), formula


def test_the_generated_general_can_be_imported_back_as_the_next_consolidation(
    tmp_path: Path,
) -> None:
    fixture = _multi_worksite(tmp_path)
    output = _write_multi(fixture, tmp_path)
    recalculated = bake_formula_values(
        output, tmp_path / "medicao-recalculada.xlsx", fixture.template
    )

    reimported = read_contract_workbook(
        recalculated,
        fixture.template,
        source_label="MAPÃO GERADO PELA MEDIÇÃO",
        contract_label=PREVIOUS_MAPAO_CONTRACT_LABEL,
    )

    assert reimported.period_numbers == [*fixture.contract.period_numbers, 3]
    assert [line.code for line in reimported.lines] == [
        line.code for line in fixture.contract.lines
    ]
    for line in reimported.lines:
        amended, accumulated, balance = _AFTER_MEASUREMENT[line.code]
        assert line.amended_quantity == Decimal(amended), line.code
        assert line.accumulated_quantity == Decimal(accumulated), line.code
        assert line.balance_quantity == Decimal(balance), line.code
        assert len(line.periods) == reimported.period_count
    assert reimported.amendments == fixture.contract.amendments


def test_a_tampered_general_quantity_is_caught_with_its_cascade(tmp_path: Path) -> None:
    fixture = _multi_worksite(tmp_path)
    output = _write_multi(fixture, tmp_path)
    quantity = _planned_cell(fixture, "general_current_quantity", "1")

    tamper_cell(output, fixture.template.general.sheet_name, quantity.ref, Decimal("999.00"))

    report = audit_workbook(
        output,
        fixture.valuation,
        fixture.catalog,
        fixture.template,
        fixture.contract,
    )

    assert report.status == "divergent"
    assert {finding.code for finding in report.findings} == {"CELL_VALUE_MISMATCH"}
    divergent = {finding.ref for finding in report.findings}
    cascade = {
        quantity.ref,
        _planned_cell(fixture, "general_current_amount", "1").ref,
        _planned_cell(fixture, "general_accumulated_quantity", "1").ref,
        _planned_cell(fixture, "general_accumulated_amount", "1").ref,
        _planned_cell(fixture, "general_balance", "1").ref,
        _planned_cell(fixture, "general_total").ref,
    }
    assert cascade <= divergent


def test_consolidation_drift_of_one_cent_refuses_the_workbook(tmp_path: Path) -> None:
    fixture = _multi_worksite(tmp_path)
    # 1,15 e 2,15 a 12,50: 14,37 + 26,87 = 41,24 linha a linha e 41,25 consolidado.
    drifting = build_valuation_from_catalog(
        fixture.catalog,
        fixture.contract.next_period_number,
        [
            MeasuredWorksite(
                worksite_key="praca-sintetica-norte",
                worksite_name="PRACA SINTETICA NORTE",
                items=(MeasuredItem(code="AD04050055(A)", quantity=Decimal("1.15")),),
            ),
            MeasuredWorksite(
                worksite_key="praca-sintetica-sul",
                worksite_name="PRACA SINTETICA SUL",
                items=(MeasuredItem(code="AD04050055(A)", quantity=Decimal("2.15")),),
            ),
        ],
    )

    with pytest.raises(ValuationValidationError) as raised:
        plan_workbook(drifting, fixture.catalog, fixture.template, fixture.contract)

    assert raised.value.code == "GENERAL_CONSOLIDATION_MISMATCH"
    assert raised.value.details["reason"] == "TRUNC_CONSOLIDATION_DRIFT"
    assert raised.value.details["general_total"] == "41.25"
    assert raised.value.details["valuation_total"] == "41.24"


def test_a_code_outside_the_consolidation_refuses_the_workbook(tmp_path: Path) -> None:
    template = default_template()
    previous = build_previous_mapao_workbook(tmp_path / "mapao-anterior.xlsx")
    contract = read_contract_workbook(
        previous.workbook_path,
        template,
        source_label=PREVIOUS_MAPAO_SOURCE_LABEL,
        contract_label=PREVIOUS_MAPAO_CONTRACT_LABEL,
    )
    outside = "CE02100010(/)"
    catalog = build_catalog_for_contract(
        tmp_path / "catalogo-contrato.xlsx",
        contract,
        extra_rows=(
            ("CE", "CERCAMENTO SINTETICO", "", ""),
            ("CE0210", "ALAMBRADO SINTETICO", "", ""),
            (outside, "ALAMBRADO SINTETICO TELA GALVANIZADA", "m2", "128.35"),
        ),
    )
    valuation = build_valuation_from_catalog(
        catalog,
        contract.next_period_number,
        [
            MeasuredWorksite(
                worksite_key="praca-sintetica-norte",
                worksite_name="PRACA SINTETICA NORTE",
                items=(MeasuredItem(code=outside, quantity=Decimal("1.00")),),
            )
        ],
    )

    with pytest.raises(ValuationValidationError) as raised:
        plan_workbook(valuation, catalog, template, contract)

    assert raised.value.code == "GENERAL_CONSOLIDATION_MISMATCH"
    assert raised.value.details["reason"] == "CODE_NOT_IN_CONTRACT"
    assert raised.value.details["codes"] == [outside]


def test_a_template_without_the_amended_column_refuses_to_plan_the_general(
    tmp_path: Path,
) -> None:
    """A GERAL gerada declara o vigente; sem coluna para ele, o escritor recusa fechado."""
    fixture = _multi_worksite(tmp_path)
    template = template_without_amended_column()

    with pytest.raises(ValuationValidationError) as raised:
        plan_workbook(fixture.valuation, fixture.catalog, template, fixture.contract)

    assert raised.value.code == "PLAN_GENERAL_NOT_REPRESENTABLE"
    assert raised.value.details["reason"] == "AMENDED_QUANTITY_COLUMN_MISSING"


def test_two_sheets_with_the_same_name_refuse_the_plan(tmp_path: Path) -> None:
    fixture = _multi_worksite(tmp_path)
    collided = fixture.template.bulletin_sheet_name("PRACA SINTETICA NORTE")
    payload = fixture.template.model_dump()
    payload["general"]["sheet_name"] = collided
    template = WorkbookTemplate.model_validate(payload)

    with pytest.raises(ValuationValidationError) as raised:
        plan_workbook(fixture.valuation, fixture.catalog, template, fixture.contract)

    assert raised.value.code == "PLAN_SHEET_NAME_COLLISION"
    assert raised.value.details["names"] == [collided]


def test_the_first_measurement_of_a_contract_accumulates_a_single_pair(tmp_path: Path) -> None:
    fixture = _multi_worksite(tmp_path)
    payload = fixture.contract.model_dump()
    payload["period_numbers"] = []
    for line in payload["lines"]:
        line["periods"] = []
        line["accumulated_quantity"] = Decimal("0.00")
        line["accumulated_amount"] = Decimal("0.00")
        line["balance_quantity"] = line["amended_quantity"]
    contract = ContractWorkbook.model_validate(payload)
    valuation = build_multi_worksite_valuation(contract)
    output = tmp_path / "primeira-medicao.xlsx"

    write_valuation_workbook(
        valuation, fixture.catalog, fixture.template, output, contract=contract
    )
    report = audit_workbook(output, valuation, fixture.catalog, fixture.template, contract)

    assert valuation.period_number == 1
    assert report.status == "ok"
    assert report.findings == []
    plan = plan_workbook(valuation, fixture.catalog, fixture.template, contract)
    general = next(
        sheet for sheet in plan.sheets if sheet.name == fixture.template.general.sheet_name
    )
    accumulated = [
        cell.formula for cell in general.cells if cell.role == "general_accumulated_quantity"
    ]
    # Sem histórico existe um par só: a lista de uma ref sairia da gramática.
    assert accumulated == ["=SUM(I8:I8)", "=SUM(I9:I9)", "=SUM(I10:I10)"] + [
        f"=SUM(I{row}:I{row})" for row in (12, 13, 14)
    ]
