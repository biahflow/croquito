"""O documento da prefeitura: gabarito de ordem fixa e memória de cálculo ao lado (F-043).

O que estes testes fixam é o que distingue o gabarito do escritor de hoje:

- a ordem é a do GABARITO, nunca a de `estimate.lines` — a fixture sintética espalha os
  códigos do orçamento pelo gabarito de propósito, então um escritor que voltasse ao
  cursor sequencial reprovaria já na primeira asserção;
- TODA linha do gabarito é impressa: a que o orçamento não preenche sai zerada, nunca
  ausente, porque as 390 linhas de zero do documento real fazem parte da entrega;
- código do orçamento que o gabarito não declara é RECUSA nomeando o código, com o disco
  intocado — linha inventada no fim do arquivo é justamente o que o documento não admite;
- a memória reusa `workbook_writer.plan_calc_block`, o único render de bloco do
  repositório, e a medição continua idêntica ao golden dela depois dessa promoção.
"""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pytest

from croquito_valuation.canonical import GRAMMAR_PATTERNS, canonicalize_workbook
from croquito_valuation.errors import ValuationValidationError
from croquito_valuation.estimate import CatalogSource, Estimate, EstimateLine
from croquito_valuation.estimate_workbook import (
    audit_estimate_grid_workbook,
    plan_estimate_grid_workbook,
    write_estimate_grid_workbook,
)
from croquito_valuation.models import CalcBlock, CalcOperand, CalcRecipe, CalcSheet, PriceOrigin
from croquito_valuation.template import EstimateTemplateRow, WorkbookTemplate, default_template
from croquito_worker.valuation import cli
from croquito_worker.valuation.synthetic import build_synthetic_estimate_approval
from tests.valuation.builders import (
    ESTIMATE_GRID_MEMORY_SHEET_NAME,
    ESTIMATE_GRID_REVISION_LABEL,
    ESTIMATE_GRID_SHEET_NAME,
    build_fixture,
    estimate_grid_rows,
    estimate_grid_template,
    tamper_cell,
    write_fixture_workbook,
)

GOLDEN_MEASUREMENT_PATH = Path(__file__).parent / "golden" / "valuation-demo.canonical.json"
GOLDEN_GRID_PATH = Path(__file__).parent / "golden" / "estimate-grid-workbook.canonical.json"

_WORKSITE_KEY = "praca-sintetica-gabarito"
_WORKSITE_NAME = "PRACA SINTETICA GABARITO"
_ADDRESS = "RUA SINTETICA DO GABARITO, 43"
_PLATE_ID = "praca-sintetica-gabarito-prancha-01"
_DIGEST = "a" * 64
_PDF_DIGEST = "b" * 64
_SCO_DIGEST = "c" * 64
_EMOP_DIGEST = "d" * 64
_UNPRICED_ITEM_ID = "ti_00000000000000ff"

_SCO_CODE = "AD04050060(/)"
"""Código que o gabarito sintético imprime na linha 02.3 — a SEXTA linha dele."""

_EMOP_CODE = "EMOP.CE.001"
"""Código que o gabarito sintético imprime na linha 04.3 — a NONA linha dele."""


def _calc_sheet_with_named_operands(item_number: str, quantity: Decimal) -> CalcSheet:
    """Um bloco de dois operandos nomeados e uma dedução: 2,00 x 2,00 - dedução."""
    deduction = Decimal("4.00") - quantity
    return CalcSheet(
        worksite_key=_WORKSITE_KEY,
        item_number=item_number,
        blocks=[
            CalcBlock(
                label=f"AREA MEDIDA {item_number}",
                recipe=CalcRecipe.LENGTH_TIMES_WIDTH,
                operands=[
                    CalcOperand(name="COMPRIMENTO", value=Decimal("2.00")),
                    CalcOperand(name="LARGURA", value=Decimal("2.00")),
                ],
                deductions=[CalcOperand(name="DESC. VÃOS", value=deduction)],
                subtotal=quantity,
            )
        ],
        total_quantity=quantity,
    )


def _build_estimate() -> Estimate:
    """Duas linhas, com os códigos ESPALHADOS pelo gabarito (posições 5 e 8, de zero).

    Os números repetem os do teste da planilha sem gabarito de propósito: o BDI impresso
    (10,00) é a diferença entre os totais truncados, e não `TRUNC(100,10 x 1,10, 2)`.
    """
    sco_source = CatalogSource(
        origin=PriceOrigin.SCO,
        source_sha256=_SCO_DIGEST,
        reference_month="2026-04",
        source_label="SCO SINTETICO F043",
    )
    emop_source = CatalogSource(
        origin=PriceOrigin.EMOP,
        source_sha256=_EMOP_DIGEST,
        reference_month="2026-07",
        source_label="EMOP SINTETICO F043",
    )
    line_a = EstimateLine(
        item_number="1",
        code=_SCO_CODE,
        description="PISO INTERTRAVADO DO ORCAMENTO",
        unit="m2",
        unit_price=Decimal("10.01"),
        unit_price_with_bdi=Decimal("11.01"),
        quantity=Decimal("3.00"),
        total=Decimal("33.03"),
        price_origin=PriceOrigin.SCO,
        catalog_sha256=_SCO_DIGEST,
        reference_month="2026-04",
        source_label="SCO SINTETICO F043",
    )
    line_b = EstimateLine(
        item_number="2",
        code=_EMOP_CODE,
        description="MOBILIARIO DO ORCAMENTO",
        unit="UN",
        unit_price=Decimal("10.01"),
        unit_price_with_bdi=Decimal("11.01"),
        quantity=Decimal("3.50"),
        total=Decimal("38.53"),
        price_origin=PriceOrigin.EMOP,
        catalog_sha256=_EMOP_DIGEST,
        reference_month="2026-07",
        source_label="EMOP SINTETICO F043",
    )
    return Estimate(
        worksite_key=_WORKSITE_KEY,
        worksite_name=_WORKSITE_NAME,
        address=_ADDRESS,
        plate_id=_PLATE_ID,
        page_number=1,
        image_sha256=_DIGEST,
        source_pdf_sha256=_PDF_DIGEST,
        bdi_percent=Decimal("10.00"),
        cascade=[sco_source, emop_source],
        lines=[line_a, line_b],
        unpriced_item_ids=[_UNPRICED_ITEM_ID],
        calc_sheets=[
            _calc_sheet_with_named_operands("1", Decimal("3.00")),
            _calc_sheet_with_named_operands("2", Decimal("3.50")),
        ],
        total_amount_without_bdi=Decimal("65.06"),
        total_amount=Decimal("71.56"),
        safety_notes=[
            "Orçamento-base sintético de teste (F-043): não é medição, não tem contrato.",
            "Cada linha declara a origem do preço; conferir a data-base antes de usar.",
        ],
    )


def _cells(canonical: dict[str, object], sheet_name: str) -> dict[str, dict[str, object]]:
    sheets = canonical["sheets"]
    assert isinstance(sheets, list)
    for sheet in sheets:
        assert isinstance(sheet, dict)
        if sheet["name"] == sheet_name:
            raw_cells = sheet["cells"]
            assert isinstance(raw_cells, list)
            indexed: dict[str, dict[str, object]] = {}
            for cell in raw_cells:
                assert isinstance(cell, dict)
                indexed[str(cell["ref"])] = cell
            return indexed
    raise AssertionError(f"aba ausente no canônico: {sheet_name}")


def _write(tmp_path: Path, estimate: Estimate, template: WorkbookTemplate) -> Path:
    output = tmp_path / "orcamento-gabarito.xlsx"
    write_estimate_grid_workbook(estimate, template, output)
    return output


def test_the_printed_order_and_numbering_are_the_grid_s_not_the_estimate_s(
    tmp_path: Path,
) -> None:
    """A linha da planilha é `header_row + 1 + índice no gabarito`, e a numeração `GG.N`
    e as lacunas de grupo saem como o gabarito as declarou."""
    template = estimate_grid_template()
    grid = template.estimate_grid
    assert grid is not None
    workbook_path = _write(tmp_path, _build_estimate(), template)

    cells = _cells(canonicalize_workbook(workbook_path, template), ESTIMATE_GRID_SHEET_NAME)
    columns = grid.columns
    first_line_row = grid.header_row + 1

    printed = [
        (
            str(cells[f"{columns.group.letter}{first_line_row + index}"]["value"]),
            str(cells[f"{columns.item.letter}{first_line_row + index}"]["value"]),
            str(cells[f"{columns.code.letter}{first_line_row + index}"]["value"]),
        )
        for index in range(len(grid.rows))
    ]

    assert printed == [(row.group, row.item, row.code) for row in estimate_grid_rows()]
    # A lacuna de grupo é o próprio gabarito não declarar linha do grupo 03.
    assert sorted({group for group, _, _ in printed}) == ["01", "02", "04"]
    # O orçamento tem duas linhas e elas caem nas posições do gabarito, não em 8 e 9.
    assert cells[f"{columns.code.letter}13"]["value"] == _SCO_CODE
    assert cells[f"{columns.code.letter}16"]["value"] == _EMOP_CODE


def test_a_row_the_estimate_does_not_fill_is_printed_zeroed_instead_of_absent(
    tmp_path: Path,
) -> None:
    """Quantidade e total zerados e PRESENTES; com preço declarado no gabarito, ele sai."""
    template = estimate_grid_template()
    grid = template.estimate_grid
    assert grid is not None
    workbook_path = _write(tmp_path, _build_estimate(), template)

    cells = _cells(canonicalize_workbook(workbook_path, template), ESTIMATE_GRID_SHEET_NAME)
    columns = grid.columns

    # 01.1 (linha 8) não está no orçamento e tem preço declarado no gabarito.
    assert cells[f"{columns.quantity.letter}8"]["value"] == "0.00"
    assert cells[f"{columns.unit_price.letter}8"]["value"] == "612.50"
    assert cells[f"{columns.total.letter}8"]["value"] == "0.00"
    # 01.3 (linha 10) não está no orçamento e o gabarito não declara preço: a célula de
    # preço não nasce, e o total é literal — fórmula sobre célula vazia derrubaria a
    # auditoria inteira (`FORMULA_REFERENCE_EMPTY`) em vez de imprimir zero.
    assert f"{columns.unit_price.letter}10" not in cells
    assert cells[f"{columns.quantity.letter}10"]["value"] == "0.00"
    assert cells[f"{columns.total.letter}10"]["kind"] == "number"
    assert cells[f"{columns.total.letter}10"]["value"] == "0.00"
    # Nenhuma linha do gabarito falta.
    for index in range(len(grid.rows)):
        assert f"{columns.total.letter}{grid.header_row + 1 + index}" in cells


def test_the_estimate_price_wins_over_the_price_declared_in_the_grid(tmp_path: Path) -> None:
    """Preço do orçamento manda; divergência com o do gabarito NÃO recusa nada."""
    rows = list(estimate_grid_rows())
    rows[5] = EstimateTemplateRow.model_validate(
        {**rows[5].model_dump(), "unit_price": Decimal("999.99")}
    )
    template = estimate_grid_template(rows=rows)
    grid = template.estimate_grid
    assert grid is not None
    workbook_path = _write(tmp_path, _build_estimate(), template)

    cells = _cells(canonicalize_workbook(workbook_path, template), ESTIMATE_GRID_SHEET_NAME)

    assert cells[f"{grid.columns.code.letter}13"]["value"] == _SCO_CODE
    assert cells[f"{grid.columns.unit_price.letter}13"]["value"] == "11.01"
    assert audit_estimate_grid_workbook(workbook_path, _build_estimate(), template).status == "ok"


def test_the_grid_revision_is_printed_so_the_file_says_which_one_it_used(
    tmp_path: Path,
) -> None:
    template = estimate_grid_template()
    grid = template.estimate_grid
    assert grid is not None
    workbook_path = _write(tmp_path, _build_estimate(), template)

    cells = _cells(canonicalize_workbook(workbook_path, template), ESTIMATE_GRID_SHEET_NAME)

    assert cells[f"{grid.label_column}5"]["value"] == grid.revision_row_label
    assert cells[f"{grid.value_column}5"]["value"] == ESTIMATE_GRID_REVISION_LABEL


def test_the_bdi_amount_is_still_the_difference_of_the_truncated_totals(
    tmp_path: Path,
) -> None:
    """ADR-0038, decisão 4, intacto no gabarito: 6,50, não o percentual sobre o total."""
    estimate = _build_estimate()
    template = estimate_grid_template()
    grid = template.estimate_grid
    assert grid is not None
    workbook_path = _write(tmp_path, estimate, template)

    cells = _cells(canonicalize_workbook(workbook_path, template), ESTIMATE_GRID_SHEET_NAME)
    total_col = grid.columns.total.letter

    # dez linhas de gabarito: header_row=7 -> linhas 8..17; bloco de totais em 19/20/21.
    assert cells[f"{total_col}19"]["value"] == "65.06"
    assert cells[f"{total_col}20"]["formula"] == f"={total_col}21-{total_col}19"
    assert cells[f"{total_col}20"]["value"] == "6.50"
    assert cells[f"{total_col}21"]["formula"] == f"=SUM({total_col}8:{total_col}17)"
    assert cells[f"{total_col}21"]["value"] == "71.56"
    assert estimate.total_amount - estimate.total_amount_without_bdi == Decimal("6.50")


def test_a_code_outside_the_grid_is_refused_by_name_with_the_disk_untouched(
    tmp_path: Path,
) -> None:
    """A recusa acontece no planejamento, antes de qualquer escrita: o arquivo não nasce."""
    rows = [row for row in estimate_grid_rows() if row.code != _EMOP_CODE]
    template = estimate_grid_template(rows=rows)
    output = tmp_path / "orcamento-gabarito.xlsx"

    with pytest.raises(ValuationValidationError) as raised:
        write_estimate_grid_workbook(_build_estimate(), template, output)

    assert raised.value.code == "ESTIMATE_GRID_CODE_ABSENT"
    assert raised.value.details["codes"] == [_EMOP_CODE]
    assert not output.exists()
    assert list(tmp_path.iterdir()) == []


def test_two_estimate_lines_on_the_same_code_are_refused_instead_of_one_winning(
    tmp_path: Path,
) -> None:
    """O gabarito tem UMA linha por código: escolher qual das duas quantidades imprimir
    seria a máquina decidindo em silêncio — exatamente o erro de mapeamento que o
    documento de 433 linhas esconde bem."""
    estimate = _build_estimate()
    payload = estimate.model_dump()
    payload["lines"][1]["code"] = _SCO_CODE
    payload["lines"][1]["price_origin"] = PriceOrigin.SCO.value
    payload["lines"][1]["catalog_sha256"] = _SCO_DIGEST
    payload["lines"][1]["reference_month"] = "2026-04"
    payload["lines"][1]["source_label"] = "SCO SINTETICO F043"
    duplicated = Estimate.model_validate(payload)
    output = tmp_path / "orcamento-gabarito.xlsx"

    with pytest.raises(ValuationValidationError) as raised:
        write_estimate_grid_workbook(duplicated, estimate_grid_template(), output)

    assert raised.value.code == "ESTIMATE_GRID_CODE_DUPLICATE"
    assert raised.value.details["codes"] == [_SCO_CODE]
    assert not output.exists()


def test_the_memory_prints_one_block_per_code_with_named_operands(tmp_path: Path) -> None:
    """Bloco por código, com rótulo, operandos nomeados, dedução e subtotal — o render é o
    de `plan_calc_block`, e a ordem é a do gabarito, como na aba ao lado."""
    template = estimate_grid_template()
    memory = template.memory
    workbook_path = _write(tmp_path, _build_estimate(), template)

    cells = _cells(canonicalize_workbook(workbook_path, template), ESTIMATE_GRID_MEMORY_SHEET_NAME)

    first_summary_row = memory.header_row + 1
    # Cada item ocupa seis linhas: resumo, os três do bloco, o total e uma em branco.
    second_summary_row = first_summary_row + 6
    # A ordem da memória é a do gabarito: o código da linha 02.3 vem antes do da 04.3,
    # ainda que no orçamento eles sejam a primeira e a segunda linha, nessa ordem.
    assert cells[f"{memory.columns.code.letter}{first_summary_row}"]["value"] == _SCO_CODE
    assert cells[f"{memory.columns.code.letter}{second_summary_row}"]["value"] == _EMOP_CODE
    assert cells[f"{memory.columns.quantity.letter}{first_summary_row}"]["value"] == "3.00"
    # bloco: rótulo, operandos nomeados, dedução e subtotal recomputado
    block_label_row = first_summary_row + 1
    header_row = block_label_row + 1
    value_row = block_label_row + 2
    assert cells[f"{memory.block_label_column}{block_label_row}"]["value"] == "AREA MEDIDA 1"
    operand_columns = memory.operand_columns
    assert cells[f"{operand_columns[0]}{header_row}"]["value"] == "COMPRIMENTO"
    assert cells[f"{operand_columns[1]}{header_row}"]["value"] == "LARGURA"
    assert cells[f"{operand_columns[2]}{header_row}"]["value"] == memory.deduction_label
    assert cells[f"{operand_columns[0]}{value_row}"]["value"] == "2.00"
    subtotal = cells[f"{memory.subtotal_column}{value_row}"]
    assert subtotal["formula"] == (
        f"=ROUND(PRODUCT({operand_columns[0]}{value_row}:{operand_columns[1]}{value_row}),2)"
        f"-{operand_columns[2]}{value_row}"
    )
    assert subtotal["value"] == "3.00"
    assert cells[f"{memory.subtotal_column}{value_row + 1}"]["value"] == "3.00"


def test_the_happy_path_audits_clean_on_both_sheets(tmp_path: Path) -> None:
    estimate = _build_estimate()
    template = estimate_grid_template()
    workbook_path = _write(tmp_path, estimate, template)

    report = audit_estimate_grid_workbook(workbook_path, estimate, template)

    assert report.status == "ok"
    assert report.findings == []
    assert report.sheet_name == ESTIMATE_GRID_SHEET_NAME
    assert report.memory_sheet_name == ESTIMATE_GRID_MEMORY_SHEET_NAME
    assert report.total_amount == estimate.total_amount
    plan = plan_estimate_grid_workbook(estimate, template)
    assert report.checked_cells == plan.planned_cells
    assert {sheet.name for sheet in plan.sheets} == {
        ESTIMATE_GRID_SHEET_NAME,
        ESTIMATE_GRID_MEMORY_SHEET_NAME,
    }


@pytest.mark.parametrize(
    ("sheet_name", "ref"),
    [(ESTIMATE_GRID_SHEET_NAME, "G13"), (ESTIMATE_GRID_MEMORY_SHEET_NAME, "C7")],
)
def test_a_tampered_cell_makes_the_audit_divergent(
    tmp_path: Path, sheet_name: str, ref: str
) -> None:
    """Adulterar o preço no gabarito ou um operando na memória reprova — a conferência é
    célula a célula nas DUAS abas, não só de totais."""
    estimate = _build_estimate()
    template = estimate_grid_template()
    workbook_path = _write(tmp_path, estimate, template)

    tamper_cell(workbook_path, sheet_name, ref, Decimal("999.00"))

    report = audit_estimate_grid_workbook(workbook_path, estimate, template)

    assert report.status == "divergent"
    assert ref in {finding.ref for finding in report.findings}
    assert {finding.sheet for finding in report.findings} == {sheet_name}


def test_every_emitted_formula_stays_inside_the_closed_grammar(tmp_path: Path) -> None:
    """Nenhuma forma nova de fórmula: estender a gramática exigiria mexer também no
    mini-avaliador, e o gabarito não faz isso."""
    template = estimate_grid_template()
    plan = plan_estimate_grid_workbook(_build_estimate(), template)

    formulas = [
        cell.formula for sheet in plan.sheets for cell in sheet.cells if cell.kind == "formula"
    ]

    assert formulas
    for formula in formulas:
        assert formula is not None
        assert any(pattern.fullmatch(formula) for _, pattern in GRAMMAR_PATTERNS), formula


def test_the_measurement_golden_survives_the_promotion_of_the_block_render(
    tmp_path: Path,
) -> None:
    """`_plan_block` virou `plan_calc_block` para que a memória do orçamento o reuse; a
    promoção é refatoração pura, e o golden da medição é o oráculo disso."""
    fixture = build_fixture(tmp_path / "medicao")
    workbook_path = tmp_path / "medicao" / "medicao.xlsx"
    write_fixture_workbook(fixture, workbook_path)

    canonical = canonicalize_workbook(workbook_path, fixture.template)

    assert canonical == json.loads(GOLDEN_MEASUREMENT_PATH.read_text(encoding="utf-8"))


def _canonical_of_grid_workbook(output_dir: Path) -> dict[str, object]:
    result = cli.run_estimate_demo(output_dir)
    template = estimate_grid_template()
    workbook_path = output_dir / "orcamento-gabarito.xlsx"
    write_estimate_grid_workbook(result.estimate, template, workbook_path)
    audit = audit_estimate_grid_workbook(workbook_path, result.estimate, template)
    assert audit.status == "ok", audit.findings
    return canonicalize_workbook(workbook_path, template)


def test_grid_canonical_matches_the_versioned_golden(tmp_path: Path) -> None:
    canonical = _canonical_of_grid_workbook(tmp_path / "estimate-demo")

    assert canonical == json.loads(GOLDEN_GRID_PATH.read_text(encoding="utf-8"))


def test_the_export_publishes_the_grid_when_the_template_declares_one(tmp_path: Path) -> None:
    """O caminho de uso fora dos testes: com gabarito declarado, quem grava e audita é o
    par do gabarito — e o portão fail-closed continua sendo o mesmo."""
    estimate = build_synthetic_estimate_approval(_build_estimate())
    output_dir = tmp_path / "orcamento"

    workbook_path, audit = cli.run_export_estimate_workbook(
        estimate, estimate_grid_template(), output_dir
    )

    assert workbook_path is not None, audit.findings
    assert audit.status == "ok"
    assert audit.sheet_name == ESTIMATE_GRID_SHEET_NAME
    assert audit.memory_sheet_name == ESTIMATE_GRID_MEMORY_SHEET_NAME
    assert not (output_dir / cli._PENDING_ESTIMATE_WORKBOOK_FILENAME).exists()


def test_the_export_without_a_grid_keeps_publishing_the_sheet_of_today(tmp_path: Path) -> None:
    """Nenhuma mudança de comportamento para quem não declara gabarito."""
    estimate = build_synthetic_estimate_approval(_build_estimate())
    output_dir = tmp_path / "orcamento-sem-gabarito"

    workbook_path, audit = cli.run_export_estimate_workbook(
        estimate, default_template(), output_dir
    )

    assert workbook_path is not None, audit.findings
    assert audit.sheet_name == "ORÇAMENTO"
    assert audit.memory_sheet_name is None


def test_the_command_refuses_a_code_the_grid_does_not_declare(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A recusa chega ao operador pelo mesmo formato estável dos demais comandos."""
    estimate = build_synthetic_estimate_approval(_build_estimate())
    estimate_path = tmp_path / "estimate.json"
    estimate_path.write_text(estimate.model_dump_json(), encoding="utf-8")
    rows = [row for row in estimate_grid_rows() if row.code != _EMOP_CODE]
    template_path = tmp_path / "template.json"
    template_path.write_text(estimate_grid_template(rows=rows).model_dump_json(), encoding="utf-8")
    output_dir = tmp_path / "saida"

    code = cli.main(
        [
            "export-estimate",
            "--estimate",
            str(estimate_path),
            "--template",
            str(template_path),
            "--output",
            str(output_dir),
        ]
    )

    assert code == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["refused"] == "ESTIMATE_GRID_CODE_ABSENT"
    assert payload["details"]["codes"] == [_EMOP_CODE]
    assert not (output_dir / cli.ESTIMATE_WORKBOOK_FILENAME).exists()


def test_the_command_publishes_the_two_sheets_and_the_audit(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    estimate = build_synthetic_estimate_approval(_build_estimate())
    estimate_path = tmp_path / "estimate.json"
    estimate_path.write_text(estimate.model_dump_json(), encoding="utf-8")
    template_path = tmp_path / "template.json"
    template_path.write_text(estimate_grid_template().model_dump_json(), encoding="utf-8")
    output_dir = tmp_path / "saida"

    code = cli.main(
        [
            "export-estimate",
            "--estimate",
            str(estimate_path),
            "--template",
            str(template_path),
            "--output",
            str(output_dir),
        ]
    )

    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "ok"
    assert payload["sheet"] == ESTIMATE_GRID_SHEET_NAME
    assert payload["memory_sheet"] == ESTIMATE_GRID_MEMORY_SHEET_NAME
    assert (output_dir / cli.ESTIMATE_WORKBOOK_FILENAME).is_file()
    assert (output_dir / cli.ESTIMATE_WORKBOOK_AUDIT_FILENAME).is_file()
