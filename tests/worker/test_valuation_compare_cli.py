"""Wiring do `compare-bulletin`: caminho feliz, divergência publicada e recusa fechada.

In-process, como os demais comandos: `main()` da CLI de medição, sem subprocesso. O lado
gerado é o `valuation.json` da fixture sintética do M1 (`tests.valuation.builders`); o
lado real é um xlsx pequeno escrito com `openpyxl` no próprio teste, no layout do
`default_template()`.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from decimal import Decimal
from pathlib import Path

from openpyxl import Workbook

from croquito_valuation.models import BulletinLine, Valuation
from croquito_valuation.template import WorkbookTemplate
from croquito_worker.valuation.cli import BULLETIN_COMPARE_REPORT_FILENAME, main
from tests.valuation.builders import build_fixture

SHEET_NAME = "BM PRACA SINTETICA NORTE"


def _write_reference_bm(
    path: Path,
    template: WorkbookTemplate,
    lines: Sequence[BulletinLine],
    total: Decimal,
    *,
    sheet_name: str = SHEET_NAME,
) -> Path:
    """Grava um BM real a partir das próprias linhas do boletim gerado (ou de uma cópia
    alterada delas), no layout do template — sem depender de nenhum documento de cliente.
    """
    layout = template.bulletin
    columns = layout.columns
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = sheet_name
    worksheet[f"{layout.label_column}1"] = layout.title
    row = layout.header_row + 1
    for line in lines:
        worksheet[f"{columns.code.letter}{row}"] = line.code
        worksheet[f"{columns.description.letter}{row}"] = line.description
        worksheet[f"{columns.unit.letter}{row}"] = line.unit
        worksheet[f"{columns.quantity.letter}{row}"] = line.quantity
        worksheet[f"{columns.unit_price.letter}{row}"] = line.unit_price
        worksheet[f"{columns.total.letter}{row}"] = line.total
        row += 1
    worksheet[f"{layout.label_column}{row}"] = layout.total_label
    worksheet[f"{columns.total.letter}{row}"] = total
    path.parent.mkdir(parents=True, exist_ok=True)
    workbook.save(path)
    return path


def _write_valuation(valuation: Valuation, path: Path) -> Path:
    path.write_text(valuation.model_dump_json(indent=2), encoding="utf-8")
    return path


def _run_compare(
    valuation_path: Path, worksite_key: str, reference_path: Path, output_dir: Path
) -> int:
    return main(
        [
            "compare-bulletin",
            "--valuation",
            str(valuation_path),
            "--worksite",
            worksite_key,
            "--reference",
            str(reference_path),
            "--sheet",
            SHEET_NAME,
            "--output",
            str(output_dir),
        ]
    )


def _report(output_dir: Path) -> dict[str, object]:
    return dict(
        json.loads((output_dir / BULLETIN_COMPARE_REPORT_FILENAME).read_text(encoding="utf-8"))
    )


def test_matching_reference_exits_zero_and_publishes_report(tmp_path: Path) -> None:
    fixture = build_fixture(tmp_path)
    bulletin = fixture.valuation.bulletins[0]
    valuation_path = _write_valuation(fixture.valuation, tmp_path / "valuation.json")
    reference_path = _write_reference_bm(
        tmp_path / "bm-real.xlsx", fixture.template, bulletin.lines, bulletin.total_amount
    )
    output_dir = tmp_path / "compare"

    exit_code = _run_compare(valuation_path, bulletin.worksite_key, reference_path, output_dir)

    assert exit_code == 0
    report = _report(output_dir)
    assert report["zero_cent"] is True
    assert report["missing_in_reference"] == []
    assert report["missing_in_generated"] == []
    assert report["line_total_diffs"] == []


def test_divergent_reference_exits_one_and_publishes_report(tmp_path: Path) -> None:
    fixture = build_fixture(tmp_path)
    bulletin = fixture.valuation.bulletins[0]
    tampered_code = bulletin.lines[0].code
    valuation_path = _write_valuation(fixture.valuation, tmp_path / "valuation.json")
    # A referência escrita traz 1 centavo a mais no total da linha adulterada.
    reference_path = tmp_path / "bm-real.xlsx"
    layout = fixture.template.bulletin
    columns = layout.columns
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = SHEET_NAME
    row = layout.header_row + 1
    for line in bulletin.lines:
        total = line.total + Decimal("0.01") if line.code == tampered_code else line.total
        worksheet[f"{columns.code.letter}{row}"] = line.code
        worksheet[f"{columns.description.letter}{row}"] = line.description
        worksheet[f"{columns.unit.letter}{row}"] = line.unit
        worksheet[f"{columns.quantity.letter}{row}"] = line.quantity
        worksheet[f"{columns.unit_price.letter}{row}"] = line.unit_price
        worksheet[f"{columns.total.letter}{row}"] = total
        row += 1
    worksheet[f"{layout.label_column}{row}"] = layout.total_label
    worksheet[f"{columns.total.letter}{row}"] = bulletin.total_amount
    workbook.save(reference_path)
    output_dir = tmp_path / "compare"

    exit_code = _run_compare(valuation_path, bulletin.worksite_key, reference_path, output_dir)

    assert exit_code == 1
    report = _report(output_dir)
    assert report["zero_cent"] is False
    line_total_diffs = report["line_total_diffs"]
    assert isinstance(line_total_diffs, list)
    assert [diff["code"] for diff in line_total_diffs] == [tampered_code]


def test_missing_sheet_refuses_with_exit_two_and_no_artifact(tmp_path: Path) -> None:
    fixture = build_fixture(tmp_path)
    bulletin = fixture.valuation.bulletins[0]
    valuation_path = _write_valuation(fixture.valuation, tmp_path / "valuation.json")
    reference_path = _write_reference_bm(
        tmp_path / "bm-real.xlsx", fixture.template, bulletin.lines, bulletin.total_amount
    )
    output_dir = tmp_path / "compare"

    exit_code = main(
        [
            "compare-bulletin",
            "--valuation",
            str(valuation_path),
            "--worksite",
            bulletin.worksite_key,
            "--reference",
            str(reference_path),
            "--sheet",
            "ABA QUE NAO EXISTE",
            "--output",
            str(output_dir),
        ]
    )

    assert exit_code == 2
    assert not (output_dir / BULLETIN_COMPARE_REPORT_FILENAME).exists()
