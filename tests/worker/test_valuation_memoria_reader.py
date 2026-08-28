"""Leitura de uma aba de memória de cálculo real (`.xlsx`) — entrada C do
`precedent-eval` (F-044 T1, escopo ampliado).

A planilha é escrita pelo próprio teste, com `openpyxl`: nada aqui é dado de cliente. O
formato (colunas 1-indexadas B=item, C=código, D=descrição/rótulo) é o mesmo que
`croquito_valuation.precedent.scan_memoria_rows` interpreta — este arquivo testa só a
ponta de I/O (abrir o `.xlsx`, achar a aba, entregar as linhas em cache).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from openpyxl import Workbook

from croquito_valuation.errors import ValuationValidationError
from croquito_worker.valuation.memoria_reader import read_memoria_sheet


def _write_memoria_workbook(path: Path, sheet_name: str, rows: list[list[object]]) -> None:
    workbook = Workbook()
    worksheet = workbook.active
    assert worksheet is not None
    worksheet.title = sheet_name
    for row in rows:
        worksheet.append(row)
    workbook.save(path)


def test_read_memoria_sheet_finds_blocks_and_labels(tmp_path: Path) -> None:
    path = tmp_path / "memoria.xlsx"
    _write_memoria_workbook(
        path,
        "MEMÓRIA DE CÁLCULO",
        [
            [None, "01.10", "AD39050218(A)", "descrição do código"],
            [None, None, None, "VIGIA"],
            [None, "01.11", "ET04600200(/)", "descrição do código 2"],
            [None, None, None, "ALAMBRADO CAMPO E QUADRA"],
        ],
    )

    scan = read_memoria_sheet(path, "MEMÓRIA DE CÁLCULO")

    assert len(scan.blocks) == 2
    assert scan.blocks[0].label == "VIGIA"
    assert scan.blocks[0].code == "AD39050218(A)"
    assert scan.blocks[1].label == "ALAMBRADO CAMPO E QUADRA"


def test_read_memoria_sheet_refuses_a_missing_sheet(tmp_path: Path) -> None:
    path = tmp_path / "memoria.xlsx"
    _write_memoria_workbook(path, "ABA REAL", [[None, "01.10", "AD39050218(A)", "descrição"]])

    with pytest.raises(ValuationValidationError) as excinfo:
        read_memoria_sheet(path, "ABA QUE NAO EXISTE")

    assert excinfo.value.code == "PRECEDENT_MEMORIA_SHEET_NOT_FOUND"
    assert excinfo.value.details["available"] == ["ABA REAL"]


def test_read_memoria_sheet_refuses_an_unreadable_file(tmp_path: Path) -> None:
    path = tmp_path / "not-a-workbook.xlsx"
    path.write_text("isto não é uma planilha", encoding="utf-8")

    with pytest.raises(ValuationValidationError) as excinfo:
        read_memoria_sheet(path, "QUALQUER ABA")

    assert excinfo.value.code == "PRECEDENT_MEMORIA_WORKBOOK_UNREADABLE"
