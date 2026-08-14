"""Paridade entre fórmula e valor em cache, sobre uma pasta que o sistema não gerou.

O `openpyxl` escreve a fórmula e **não** escreve o valor calculado dela — quem calcula é o
Excel. Para exercitar a ferramenta é preciso um arquivo que tenha os dois, então o helper
daqui injeta o `<v>` dentro dos `<c>` que já têm `<f>`, direto no XML da aba. É a única
forma de reproduzir, sem Excel, a pasta que chega do cliente: fórmula de um lado, último
valor calculado do outro, e a possibilidade de os dois discordarem.

Nada aqui é dado de cliente: as fórmulas e os números são inventados no próprio teste.
"""

from __future__ import annotations

import json
import xml.etree.ElementTree as ElementTree
import zipfile
from decimal import Decimal
from pathlib import Path

import pytest
from openpyxl import Workbook

from croquito_worker.valuation.cli import PARITY_REPORT_FILENAME, main

SHEET = "TESTE"
_SPREADSHEET_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
_CELL = f"{{{_SPREADSHEET_NS}}}c"
_FORMULA = f"{{{_SPREADSHEET_NS}}}f"
_VALUE = f"{{{_SPREADSHEET_NS}}}v"


def _inject_cached_values(path: Path, cached: dict[str, str]) -> None:
    """Grava o valor calculado das fórmulas indicadas, como o Excel faria ao salvar.

    O XML da aba usa o namespace padrão do SpreadsheetML; ele é registrado sem prefixo
    para que o arquivo regravado continue sendo o mesmo formato, e não um com `ns0:`.
    """
    ElementTree.register_namespace("", _SPREADSHEET_NS)
    with zipfile.ZipFile(path) as archive:
        entries = {name: archive.read(name) for name in archive.namelist()}
    for name, payload in list(entries.items()):
        if not (name.startswith("xl/worksheets/sheet") and name.endswith(".xml")):
            continue
        root = ElementTree.fromstring(payload.decode("utf-8"))
        touched = False
        for cell in root.iter(_CELL):
            ref = cell.get("r")
            if cell.find(_FORMULA) is None or ref is None or ref not in cached:
                continue
            # O `openpyxl` já grava um `<v />` vazio depois do `<f>`; preencher esse é o
            # que reproduz o arquivo salvo pelo Excel. Criar um segundo seria ignorado.
            value = cell.find(_VALUE)
            if value is None:
                value = ElementTree.SubElement(cell, _VALUE)
            value.text = cached[ref]
            touched = True
        if touched:
            entries[name] = ElementTree.tostring(root, encoding="utf-8", xml_declaration=True)
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, payload in entries.items():
            archive.writestr(name, payload)


def _build_workbook(path: Path, cells: dict[str, object], cached: dict[str, str]) -> Path:
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = SHEET
    for ref, value in cells.items():
        worksheet[ref] = value
    path.parent.mkdir(parents=True, exist_ok=True)
    workbook.save(path)
    _inject_cached_values(path, cached)
    return path


_LIVE_CELLS: dict[str, object] = {
    "A1": Decimal("2.00"),
    "B1": Decimal("3.00"),
    "C1": "=TRUNC(A1*B1,2)",
    "A2": Decimal("4.00"),
    "B2": Decimal("2.50"),
    "C2": "=TRUNC(A2*B2,2)",
    "C3": "=SUM(C1:C2)",
}
_LIVE_CACHE = {"C1": "6", "C2": "10", "C3": "16"}


def _run_parity(path: Path, output_dir: Path) -> int:
    return main(["parity", "--previous", str(path), "--output", str(output_dir)])


def _report(output_dir: Path) -> dict[str, object]:
    return dict(json.loads((output_dir / PARITY_REPORT_FILENAME).read_text(encoding="utf-8")))


def _findings(output_dir: Path) -> list[dict[str, object]]:
    findings = _report(output_dir)["findings"]
    assert isinstance(findings, list)
    return [dict(finding) for finding in findings]


def _sheet(output_dir: Path) -> dict[str, object]:
    sheets = _report(output_dir)["sheets"]
    assert isinstance(sheets, list)
    return dict(sheets[0])


def test_a_workbook_whose_caches_match_its_formulas_has_no_finding(tmp_path: Path) -> None:
    path = _build_workbook(tmp_path / "cliente.xlsx", _LIVE_CELLS, _LIVE_CACHE)
    output_dir = tmp_path / "parity"

    exit_code = _run_parity(path, output_dir)

    assert exit_code == 0
    assert _sheet(output_dir) == {
        "name": SHEET,
        "formulas": 3,
        "verified": 3,
        "divergent": 0,
        "foreign": 0,
        "cache_missing": 0,
    }
    assert _findings(output_dir) == []


def test_a_tampered_cache_is_reported_on_its_own_cell(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = _build_workbook(tmp_path / "cliente.xlsx", _LIVE_CELLS, {**_LIVE_CACHE, "C3": "99.99"})
    output_dir = tmp_path / "parity"

    exit_code = _run_parity(path, output_dir)

    assert exit_code == 1
    summary = json.loads(capsys.readouterr().out)
    assert summary["divergent"] == 1
    assert _findings(output_dir) == [
        {
            "code": "PARITY_VALUE_DIVERGENT",
            "sheet": SHEET,
            "ref": "C3",
            "formula": "=SUM(C1:C2)",
            "cached": "99.99",
            "recomputed": "16.00",
            "missing_refs": [],
            "category": None,
        }
    ]


def test_a_vlookup_is_classified_instead_of_guessed(tmp_path: Path) -> None:
    cells = {**_LIVE_CELLS, "D1": "=VLOOKUP(A1,Z1:AA9,2,FALSE)"}
    path = _build_workbook(tmp_path / "cliente.xlsx", cells, {**_LIVE_CACHE, "D1": "42"})
    output_dir = tmp_path / "parity"

    exit_code = _run_parity(path, output_dir)

    # Fórmula fora da gramática é achado classificado, não motivo para reprovar o arquivo.
    assert exit_code == 0
    assert _sheet(output_dir)["foreign"] == 1
    assert _findings(output_dir) == [
        {
            "code": "PARITY_FORMULA_FOREIGN",
            "sheet": SHEET,
            "ref": "D1",
            "formula": "=VLOOKUP(A1,Z1:AA9,2,FALSE)",
            "cached": None,
            "recomputed": None,
            "missing_refs": [],
            "category": "vlookup",
        }
    ]


def test_an_operand_without_cache_is_reported_instead_of_recomputed_from_nothing(
    tmp_path: Path,
) -> None:
    cells = {**_LIVE_CELLS, "C4": "=TRUNC(A9*B9,2)"}
    path = _build_workbook(tmp_path / "cliente.xlsx", cells, {**_LIVE_CACHE, "C4": "0"})
    output_dir = tmp_path / "parity"

    exit_code = _run_parity(path, output_dir)

    assert exit_code == 0
    assert _sheet(output_dir)["cache_missing"] == 1
    assert _findings(output_dir) == [
        {
            "code": "PARITY_CACHE_MISSING",
            "sheet": SHEET,
            "ref": "C4",
            "formula": "=TRUNC(A9*B9,2)",
            "cached": None,
            "recomputed": None,
            "missing_refs": ["A9", "B9"],
            "category": None,
        }
    ]


def test_an_unreadable_file_is_a_closed_refusal(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tmp_path / "cliente.xlsx"
    path.write_bytes(b"isto nao e uma planilha")

    exit_code = _run_parity(path, tmp_path / "parity")

    assert exit_code == 2
    assert json.loads(capsys.readouterr().out)["refused"] == "PARITY_WORKBOOK_UNREADABLE"
    assert not (tmp_path / "parity" / PARITY_REPORT_FILENAME).exists()
