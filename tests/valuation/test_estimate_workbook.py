"""A planilha do orçamento-base (ADR-0038) é reaberta, recomputada e conferida centavo a
centavo — o mesmo portão da medição, com um auditor próprio.

O caso feliz usa duas linhas com o MESMO preço unitário e o mesmo BDI (10%) de propósito:
a soma dos totais truncados linha a linha (110,10) diverge de `TRUNC(soma sem BDI x 1,10),
2)` (110,11, um centavo a mais). Se o valor do BDI impresso fosse o percentual aplicado ao
total geral — a alternativa que o ADR-0038 (decisão 4) rejeita —, a planilha discordaria
dela mesma no centavo. É essa divergência que o teste do bloco de totais prova.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from croquito_valuation.canonical import canonicalize_workbook
from croquito_valuation.errors import ValuationValidationError
from croquito_valuation.estimate import CatalogSource, Estimate, EstimateLine
from croquito_valuation.estimate_workbook import (
    EstimateAuditFinding,
    EstimateAuditReport,
    audit_estimate_workbook,
    write_estimate_workbook,
)
from croquito_valuation.models import CalcBlock, CalcOperand, CalcRecipe, CalcSheet, PriceOrigin
from croquito_valuation.template import WorkbookTemplate, default_template
from croquito_worker.valuation import cli
from croquito_worker.valuation.synthetic import build_synthetic_estimate_approval
from tests.valuation.builders import tamper_cell

_WORKSITE_KEY = "praca-sintetica-orcamento-t2"
_WORKSITE_NAME = "PRACA SINTETICA T2"
_ADDRESS = "RUA SINTETICA T2, 100"
_PLATE_ID = "praca-sintetica-t2-prancha-01"
_DIGEST = "a" * 64
_PDF_DIGEST = "b" * 64
_SCO_DIGEST = "c" * 64
_EMOP_DIGEST = "d" * 64
_BDI_PERCENT = Decimal("10.00")
_UNPRICED_ITEM_ID = "ti_00000000000000ff"


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


def _build_estimate() -> Estimate:
    """Duas linhas, três decisões deliberadas: BDI (10%) aplicado por linha e truncado
    antes de somar, uma fonte por origem (SCO e EMOP) e um item sem preço declarado."""
    sco_source = CatalogSource(
        origin=PriceOrigin.SCO,
        source_sha256=_SCO_DIGEST,
        reference_month="2026-04",
        source_label="SCO SINTETICO T2",
    )
    emop_source = CatalogSource(
        origin=PriceOrigin.EMOP,
        source_sha256=_EMOP_DIGEST,
        reference_month="2026-07",
        source_label="EMOP SINTETICO T2",
    )
    line_a = EstimateLine(
        item_number="1",
        code="AD04050060(/)",
        description="ALAMBRADO SINTETICO T2",
        unit="m",
        unit_price=Decimal("10.01"),
        unit_price_with_bdi=Decimal("11.01"),
        quantity=Decimal("3.00"),
        total=Decimal("33.03"),
        price_origin=PriceOrigin.SCO,
        catalog_sha256=_SCO_DIGEST,
        reference_month="2026-04",
        source_label="SCO SINTETICO T2",
    )
    line_b = EstimateLine(
        item_number="2",
        code="EMOP.CE.002",
        description="PISO EMBORRACHADO SINTETICO T2",
        unit="m2",
        unit_price=Decimal("10.01"),
        unit_price_with_bdi=Decimal("11.01"),
        quantity=Decimal("7.00"),
        total=Decimal("77.07"),
        price_origin=PriceOrigin.EMOP,
        catalog_sha256=_EMOP_DIGEST,
        reference_month="2026-07",
        source_label="EMOP SINTETICO T2",
    )
    return Estimate(
        worksite_key=_WORKSITE_KEY,
        worksite_name=_WORKSITE_NAME,
        address=_ADDRESS,
        plate_id=_PLATE_ID,
        page_number=1,
        image_sha256=_DIGEST,
        source_pdf_sha256=_PDF_DIGEST,
        bdi_percent=_BDI_PERCENT,
        cascade=[sco_source, emop_source],
        lines=[line_a, line_b],
        unpriced_item_ids=[_UNPRICED_ITEM_ID],
        calc_sheets=[_calc_sheet("1", Decimal("3.00")), _calc_sheet("2", Decimal("7.00"))],
        total_amount_without_bdi=Decimal("100.10"),
        total_amount=Decimal("110.10"),
        safety_notes=[
            "Orçamento-base sintético de teste (T2): não é medição, não tem contrato.",
            "Cada linha declara a origem do preço; conferir a data-base antes de usar.",
        ],
    )


def _cells(canonical: dict[str, object], sheet_name: str) -> dict[str, dict[str, object]]:
    sheets = canonical["sheets"]
    assert isinstance(sheets, list)
    for sheet in sheets:
        assert isinstance(sheet, dict)
        if sheet["name"] == sheet_name:
            cells = sheet["cells"]
            assert isinstance(cells, list)
            result: dict[str, dict[str, object]] = {}
            for cell in cells:
                assert isinstance(cell, dict)
                result[str(cell["ref"])] = cell
            return result
    raise AssertionError(f"aba ausente no canônico: {sheet_name}")


def _write(tmp_path: Path, estimate: Estimate, template: WorkbookTemplate) -> Path:
    output = tmp_path / "orcamento.xlsx"
    write_estimate_workbook(estimate, template, output)
    return output


def test_the_seven_bulletin_columns_plus_source_and_bdi_price_are_printed_per_line(
    tmp_path: Path,
) -> None:
    estimate = _build_estimate()
    template = default_template()
    layout = template.estimate
    assert layout is not None
    workbook_path = _write(tmp_path, estimate, template)

    canonical = canonicalize_workbook(workbook_path, template)
    cells = _cells(canonical, layout.sheet_name)
    columns = layout.columns

    assert cells[f"{columns.item.letter}{layout.header_row}"]["value"] == "ITEM"
    assert cells[f"{columns.code.letter}{layout.header_row}"]["value"] == "COD."
    assert cells[f"{columns.source.letter}{layout.header_row}"]["value"] == "FONTE"
    assert cells[f"{columns.description.letter}{layout.header_row}"]["value"] == "DESCRIÇÃO"
    assert cells[f"{columns.unit.letter}{layout.header_row}"]["value"] == "UN"
    assert cells[f"{columns.unit_price.letter}{layout.header_row}"]["value"] == "VALOR UNIT"
    assert (
        cells[f"{columns.unit_price_with_bdi.letter}{layout.header_row}"]["value"]
        == "VALOR UNIT. C/ BDI"
    )
    assert cells[f"{columns.quantity.letter}{layout.header_row}"]["value"] == "QUANT"
    assert cells[f"{columns.total.letter}{layout.header_row}"]["value"] == "TOTAL"

    first_line_row = layout.header_row + 1
    # FONTE combina origem e data-base numa célula só (ADR-0038, decisão 5).
    assert cells[f"{columns.source.letter}{first_line_row}"]["value"] == "SCO 2026-04"
    assert cells[f"{columns.unit_price.letter}{first_line_row}"]["value"] == "10.01"
    assert cells[f"{columns.unit_price_with_bdi.letter}{first_line_row}"]["value"] == "11.01"
    second_line_row = first_line_row + 1
    assert cells[f"{columns.source.letter}{second_line_row}"]["value"] == "EMOP 2026-07"


def test_bdi_amount_is_the_difference_of_the_truncated_totals(tmp_path: Path) -> None:
    """O ponto do ADR-0038 (decisão 4): 10,00 (soma dos truncados), não 10,01 — o que
    `TRUNC(100,10 x 1,10, 2)` daria se o BDI fosse aplicado ao total geral."""
    estimate = _build_estimate()
    template = default_template()
    layout = template.estimate
    assert layout is not None
    workbook_path = _write(tmp_path, estimate, template)

    canonical = canonicalize_workbook(workbook_path, template)
    cells = _cells(canonical, layout.sheet_name)
    total_col = layout.columns.total.letter

    # duas linhas: header_row=6 -> linhas em 7 e 8; bloco de totais em 10/11/12.
    assert cells[f"{total_col}10"]["value"] == "100.10"
    assert cells[f"{layout.columns.description.letter}10"]["value"] == "TOTAL SEM BDI"
    assert cells[f"{total_col}11"]["value"] == "10.00"
    assert cells[f"{total_col}11"]["formula"] == f"={total_col}12-{total_col}10"
    assert cells[f"{layout.columns.description.letter}11"]["value"] == "BDI (10.00%)"
    assert cells[f"{total_col}12"]["value"] == "110.10"
    assert cells[f"{total_col}12"]["formula"] == f"=SUM({total_col}7:{total_col}8)"
    assert cells[f"{layout.columns.description.letter}12"]["value"] == "TOTAL GERAL"
    assert estimate.total_amount - estimate.total_amount_without_bdi == Decimal("10.00")


def test_unpriced_item_gets_its_own_block_and_no_price(tmp_path: Path) -> None:
    estimate = _build_estimate()
    template = default_template()
    layout = template.estimate
    assert layout is not None
    workbook_path = _write(tmp_path, estimate, template)

    canonical = canonicalize_workbook(workbook_path, template)
    cells = _cells(canonical, layout.sheet_name)
    item_col = layout.columns.item.letter

    assert cells[f"{item_col}14"]["value"] == layout.unpriced_section_label
    assert cells[f"{item_col}15"]["value"] == _UNPRICED_ITEM_ID
    # Nenhuma linha de preço nasce para o item sem preço: sem célula na coluna de preço.
    assert f"{layout.columns.unit_price_with_bdi.letter}15" not in cells
    assert f"{layout.columns.total.letter}15" not in cells


def test_the_happy_path_audits_clean(tmp_path: Path) -> None:
    estimate = _build_estimate()
    template = default_template()
    workbook_path = _write(tmp_path, estimate, template)

    report = audit_estimate_workbook(workbook_path, estimate, template)

    assert report.status == "ok"
    assert report.findings == []
    assert report.total_amount == estimate.total_amount == Decimal("110.10")


def test_a_tampered_cell_makes_the_audit_divergent(tmp_path: Path) -> None:
    """Adulterar o preço com BDI da primeira linha derruba a própria célula e o total que
    a referencia — a auditoria pega a cascata, e nada disso seria publicado."""
    estimate = _build_estimate()
    template = default_template()
    layout = template.estimate
    assert layout is not None
    workbook_path = _write(tmp_path, estimate, template)
    price_ref = f"{layout.columns.unit_price_with_bdi.letter}7"
    total_ref = f"{layout.columns.total.letter}7"

    tamper_cell(workbook_path, layout.sheet_name, price_ref, Decimal("999.00"))

    report = audit_estimate_workbook(workbook_path, estimate, template)

    assert report.status == "divergent"
    divergent_refs = {finding.ref for finding in report.findings}
    assert {price_ref, total_ref} <= divergent_refs
    assert {finding.code for finding in report.findings} == {"CELL_VALUE_MISMATCH"}


def test_export_gate_does_not_publish_when_the_audit_is_divergent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """O mesmo desenho de `run_export_valuation`: auditoria divergente não publica nada,
    e o pendente não sobra no diretório.

    O orçamento entra assinado porque desde o ADR-0046 o portão do domínio corre antes da
    escrita; o que este teste isola é o OUTRO lado do risco, o do auditor.
    """
    estimate = build_synthetic_estimate_approval(_build_estimate())
    template = default_template()
    layout = template.estimate
    assert layout is not None
    output_dir = tmp_path / "orcamento-demo"

    def _fake_divergent_audit(
        workbook_path: Path, estimate: Estimate, template: WorkbookTemplate
    ) -> EstimateAuditReport:
        return EstimateAuditReport(
            status="divergent",
            workbook_sha256="0" * 64,
            sheet_name=layout.sheet_name,
            checked_cells=1,
            formula_cells=0,
            total_amount=estimate.total_amount,
            findings=[
                EstimateAuditFinding(code="CELL_VALUE_MISMATCH", sheet=layout.sheet_name, ref="I7")
            ],
        )

    monkeypatch.setattr(cli, "audit_estimate_workbook", _fake_divergent_audit)

    workbook_path, audit = cli.run_export_estimate_workbook(estimate, template, output_dir)

    assert workbook_path is None
    assert audit.status == "divergent"
    assert not (output_dir / cli.ESTIMATE_WORKBOOK_FILENAME).exists()
    assert not (output_dir / cli._PENDING_ESTIMATE_WORKBOOK_FILENAME).exists()


def test_the_export_refuses_an_unsigned_estimate_before_writing_anything(tmp_path: Path) -> None:
    """O portão do domínio corre antes de qualquer escrita: nem o pendente nasce.

    O CLI obedece à mesma regra que a API porque a regra é do `Estimate`, não da rota
    (ADR-0046, decisão 3).
    """
    output_dir = tmp_path / "orcamento-sem-assinatura"

    with pytest.raises(ValuationValidationError) as raised:
        cli.run_export_estimate_workbook(_build_estimate(), default_template(), output_dir)

    assert raised.value.code == "ESTIMATE_EXPORT_BLOCKED"
    assert raised.value.details["errors"] == ["ESTIMATE_NOT_APPROVED"]
    assert not output_dir.exists()
