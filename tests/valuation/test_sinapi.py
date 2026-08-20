"""Importador SINAPI offline: leitor .xlsx mínimo, sempre `origin=sinapi`, e o CLI.

A tabela SINAPI real é de distribuição pública, mas o arquivo real não existe neste
repositório — tudo aqui é sintético (`croquito_worker.valuation.sinapi_fixture`). Espelho
da estrutura de `tests/valuation/test_emop.py` (o molde desta task, F-026/T2): o que
importa nas recusas não é a mensagem, é que nenhum artefato pela metade sobra no
diretório de saída.
"""

from __future__ import annotations

import json
from dataclasses import replace
from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import ValidationError

from croquito_valuation.catalog import file_sha256
from croquito_valuation.errors import ValuationValidationError, valuation_error_codes
from croquito_valuation.models import PriceCatalog, PriceOrigin
from croquito_valuation.sinapi import (
    SinapiCatalogLayout,
    read_sinapi_catalog,
    read_sinapi_catalog_with_report,
)
from croquito_worker.valuation.cli import CATALOG_FILENAME, SINAPI_IMPORT_REPORT_FILENAME, main
from croquito_worker.valuation.sinapi_fixture import (
    SINAPI_FIXTURE_ROWS,
    SINAPI_REFERENCE_MONTH,
    SINAPI_SOURCE_LABEL,
    expected_sinapi_entries,
    sinapi_fixture_layout,
    write_sinapi_xlsx,
)

# --------------------------------------------------------------------------------------
# caminho feliz: entradas, origin, reference_month, digest
# --------------------------------------------------------------------------------------


def test_read_sinapi_catalog_matches_the_synthetic_fixture(tmp_path: Path) -> None:
    xlsx_path = write_sinapi_xlsx(tmp_path / "sinapi-sintetico.xlsx")
    layout = sinapi_fixture_layout()

    catalog = read_sinapi_catalog(xlsx_path, layout)

    assert catalog.origin == PriceOrigin.SINAPI
    assert catalog.source_label == SINAPI_SOURCE_LABEL
    assert catalog.reference_month == SINAPI_REFERENCE_MONTH
    assert catalog.source_sha256 == file_sha256(xlsx_path)
    assert catalog.entries == expected_sinapi_entries()
    assert all(entry.origin == PriceOrigin.SINAPI for entry in catalog.entries)


def test_blank_rows_are_skipped_counted_and_never_imported(tmp_path: Path) -> None:
    xlsx_path = write_sinapi_xlsx(tmp_path / "sinapi-sintetico.xlsx")
    layout = sinapi_fixture_layout()

    catalog, notes = read_sinapi_catalog_with_report(xlsx_path, layout)

    blank_rows = [row for row in SINAPI_FIXTURE_ROWS if row.blank]
    assert blank_rows, "a fixture precisa declarar ao menos uma linha em branco"
    assert len(catalog.entries) == len(SINAPI_FIXTURE_ROWS) - len(blank_rows)
    assert notes.blank_row_count == len(blank_rows)
    assert notes.blank_rows == (4,)


def test_reimporting_the_same_bytes_yields_the_same_catalog_id(tmp_path: Path) -> None:
    first_path = write_sinapi_xlsx(tmp_path / "primeiro.xlsx")
    second_path = write_sinapi_xlsx(tmp_path / "segundo.xlsx")
    layout = sinapi_fixture_layout()

    first = read_sinapi_catalog(first_path, layout)
    second = read_sinapi_catalog(second_path, layout)

    assert first.id == second.id


# --------------------------------------------------------------------------------------
# recusas estruturais do .xlsx
# --------------------------------------------------------------------------------------


def test_a_broken_xlsx_file_is_refused(tmp_path: Path) -> None:
    xlsx_path = tmp_path / "sinapi.xlsx"
    xlsx_path.write_bytes(b"isto nao e um arquivo xlsx valido")

    with pytest.raises(ValuationValidationError) as raised:
        read_sinapi_catalog(xlsx_path, sinapi_fixture_layout())

    assert raised.value.code == "SINAPI_XLSX_UNSUPPORTED"


def test_a_sheet_declared_in_the_layout_but_missing_from_the_xlsx_is_refused(
    tmp_path: Path,
) -> None:
    xlsx_path = write_sinapi_xlsx(tmp_path / "sinapi.xlsx")
    layout = SinapiCatalogLayout.model_validate(
        {**sinapi_fixture_layout().model_dump(), "sheet_name": "OUTRA_ABA"}
    )

    with pytest.raises(ValuationValidationError) as raised:
        read_sinapi_catalog(xlsx_path, layout)

    assert raised.value.code == "SINAPI_SHEET_MISSING"


# --------------------------------------------------------------------------------------
# coluna declarada no layout ausente da tabela
# --------------------------------------------------------------------------------------


def test_a_column_declared_in_the_layout_but_outside_the_table_is_refused(
    tmp_path: Path,
) -> None:
    xlsx_path = write_sinapi_xlsx(tmp_path / "sinapi.xlsx")
    layout = SinapiCatalogLayout.model_validate(
        {**sinapi_fixture_layout().model_dump(), "price_column": "Z"}
    )

    with pytest.raises(ValuationValidationError) as raised:
        read_sinapi_catalog(xlsx_path, layout)

    assert raised.value.code == "SINAPI_FIELD_MISSING"
    assert raised.value.details["columns"] == ["Z"]


# --------------------------------------------------------------------------------------
# linha ilegível: código fora do padrão, preço não numérico/negativo/float, descrição vazia
# --------------------------------------------------------------------------------------


def test_a_row_whose_code_does_not_match_the_layout_pattern_is_refused(tmp_path: Path) -> None:
    rows = (replace(SINAPI_FIXTURE_ROWS[0], code="BADCODE"), *SINAPI_FIXTURE_ROWS[1:])
    xlsx_path = write_sinapi_xlsx(tmp_path / "sinapi.xlsx", rows)

    with pytest.raises(ValuationValidationError) as raised:
        read_sinapi_catalog(xlsx_path, sinapi_fixture_layout())

    assert raised.value.code == "SINAPI_ROW_UNPARSEABLE"
    assert raised.value.details["row"] == 2


def test_a_row_with_a_non_numeric_price_text_is_refused(tmp_path: Path) -> None:
    rows = (replace(SINAPI_FIXTURE_ROWS[0], price="XYZ"), *SINAPI_FIXTURE_ROWS[1:])
    xlsx_path = write_sinapi_xlsx(tmp_path / "sinapi.xlsx", rows)

    with pytest.raises(ValuationValidationError) as raised:
        read_sinapi_catalog(xlsx_path, sinapi_fixture_layout())

    assert raised.value.code == "SINAPI_ROW_UNPARSEABLE"
    assert raised.value.details["row"] == 2


def test_a_row_with_a_negative_price_is_refused(tmp_path: Path) -> None:
    rows = (replace(SINAPI_FIXTURE_ROWS[0], price=Decimal("-5.00")), *SINAPI_FIXTURE_ROWS[1:])
    xlsx_path = write_sinapi_xlsx(tmp_path / "sinapi.xlsx", rows)

    with pytest.raises(ValuationValidationError) as raised:
        read_sinapi_catalog(xlsx_path, sinapi_fixture_layout())

    assert raised.value.code == "SINAPI_ROW_UNPARSEABLE"
    assert raised.value.details["row"] == 2


def test_a_price_cell_written_as_a_binary_float_is_refused_instead_of_converted(
    tmp_path: Path,
) -> None:
    """A célula de preço nasce número binário do openpyxl (não texto): a linha recusa em
    vez de converter — é a garantia central deste importador (`ExactDecimal`)."""
    xlsx_path = write_sinapi_xlsx(tmp_path / "sinapi.xlsx", price_as_float=True)

    with pytest.raises(ValuationValidationError) as raised:
        read_sinapi_catalog(xlsx_path, sinapi_fixture_layout())

    assert raised.value.code == "SINAPI_ROW_UNPARSEABLE"
    assert raised.value.details["row"] == 2


def test_a_row_with_an_empty_description_is_refused(tmp_path: Path) -> None:
    rows = (
        SINAPI_FIXTURE_ROWS[0],
        replace(SINAPI_FIXTURE_ROWS[1], description=""),
        *SINAPI_FIXTURE_ROWS[2:],
    )
    xlsx_path = write_sinapi_xlsx(tmp_path / "sinapi.xlsx", rows)

    with pytest.raises(ValuationValidationError) as raised:
        read_sinapi_catalog(xlsx_path, sinapi_fixture_layout())

    assert raised.value.code == "SINAPI_ROW_UNPARSEABLE"
    assert raised.value.details["row"] == 3


# --------------------------------------------------------------------------------------
# catálogo vazio
# --------------------------------------------------------------------------------------


def test_a_table_with_every_row_blank_is_refused_as_empty(tmp_path: Path) -> None:
    rows = tuple(replace(row, blank=True) for row in SINAPI_FIXTURE_ROWS)
    xlsx_path = write_sinapi_xlsx(tmp_path / "sinapi.xlsx", rows)

    with pytest.raises(ValuationValidationError) as raised:
        read_sinapi_catalog(xlsx_path, sinapi_fixture_layout())

    assert raised.value.code == "SINAPI_EMPTY"


# --------------------------------------------------------------------------------------
# layout: código de padrão inválido ou frouxo demais (cinto e suspensório)
# --------------------------------------------------------------------------------------


def _layout_with_pattern(pattern: str) -> dict[str, object]:
    return {**sinapi_fixture_layout().model_dump(), "code_pattern": pattern}


def test_layout_refuses_a_code_pattern_that_does_not_compile() -> None:
    with pytest.raises(ValidationError) as raised:
        SinapiCatalogLayout.model_validate(_layout_with_pattern("("))

    assert valuation_error_codes(raised.value) == ["SINAPI_LAYOUT_CODE_PATTERN_INVALID"]


def test_layout_refuses_a_code_pattern_that_matches_the_empty_string() -> None:
    with pytest.raises(ValidationError) as raised:
        SinapiCatalogLayout.model_validate(_layout_with_pattern(".*"))

    assert valuation_error_codes(raised.value) == ["SINAPI_LAYOUT_CODE_PATTERN_INVALID"]


# --------------------------------------------------------------------------------------
# CLI: import-sinapi feliz e recusa fechada
# --------------------------------------------------------------------------------------


def _stdout(capsys: pytest.CaptureFixture[str]) -> dict[str, object]:
    lines = [line for line in capsys.readouterr().out.splitlines() if line.strip()]
    return dict(json.loads(lines[-1]))


def _layout_path(tmp_path: Path) -> Path:
    layout_path = tmp_path / "sinapi-layout.json"
    layout_path.write_text(sinapi_fixture_layout().model_dump_json(indent=2), encoding="utf-8")
    return layout_path


def test_cli_import_sinapi_publishes_only_the_catalog_and_its_own_report(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    xlsx_path = write_sinapi_xlsx(tmp_path / "sinapi.xlsx")
    layout_path = _layout_path(tmp_path)
    output_dir = tmp_path / "import-sinapi"

    exit_code = main(
        [
            "import-sinapi",
            "--input",
            str(xlsx_path),
            "--layout",
            str(layout_path),
            "--output",
            str(output_dir),
        ]
    )

    assert exit_code == 0
    payload = _stdout(capsys)
    assert payload["consolidado"] == "not_imported"
    note = payload["note"]
    assert isinstance(note, str)
    assert "BULLETIN_PRICE_ORIGIN_FORBIDDEN" in note
    active_rows = [row for row in SINAPI_FIXTURE_ROWS if not row.blank]
    blank_rows = [row for row in SINAPI_FIXTURE_ROWS if row.blank]
    assert payload["catalog_entries"] == len(active_rows)
    blank_row_payload = payload["blank_rows"]
    assert isinstance(blank_row_payload, dict)
    assert blank_row_payload["count"] == len(blank_rows)

    assert (output_dir / CATALOG_FILENAME).is_file()
    assert (output_dir / SINAPI_IMPORT_REPORT_FILENAME).is_file()

    catalog = PriceCatalog.model_validate_json(
        (output_dir / CATALOG_FILENAME).read_text(encoding="utf-8")
    )
    assert catalog.origin == PriceOrigin.SINAPI
    assert catalog.source_sha256 == file_sha256(xlsx_path)

    report = json.loads((output_dir / SINAPI_IMPORT_REPORT_FILENAME).read_text(encoding="utf-8"))
    for key, value in report.items():
        assert payload[key] == value


def test_cli_import_sinapi_refuses_a_broken_xlsx_without_publishing_anything(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    xlsx_path = tmp_path / "sinapi.xlsx"
    xlsx_path.write_bytes(b"nao e um xlsx valido")
    layout_path = _layout_path(tmp_path)
    output_dir = tmp_path / "import-sinapi"

    exit_code = main(
        [
            "import-sinapi",
            "--input",
            str(xlsx_path),
            "--layout",
            str(layout_path),
            "--output",
            str(output_dir),
        ]
    )

    assert exit_code == 2
    assert _stdout(capsys)["refused"] == "SINAPI_XLSX_UNSUPPORTED"
    assert not output_dir.exists() or list(output_dir.iterdir()) == []


def test_cli_import_sinapi_refuses_an_invalid_layout_without_publishing_anything(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    xlsx_path = write_sinapi_xlsx(tmp_path / "sinapi.xlsx")
    layout_path = tmp_path / "sinapi-layout.json"
    layout_path.write_text(
        json.dumps({**sinapi_fixture_layout().model_dump(), "code_pattern": ".*"}),
        encoding="utf-8",
    )
    output_dir = tmp_path / "import-sinapi"

    exit_code = main(
        [
            "import-sinapi",
            "--input",
            str(xlsx_path),
            "--layout",
            str(layout_path),
            "--output",
            str(output_dir),
        ]
    )

    assert exit_code == 2
    assert _stdout(capsys)["refused"] == "SINAPI_LAYOUT_CODE_PATTERN_INVALID"
    assert not output_dir.exists() or list(output_dir.iterdir()) == []


def test_decimal_price_never_goes_through_float(tmp_path: Path) -> None:
    """Cinto extra: o preço lido é sempre `Decimal` construído de texto, nunca `float`."""
    xlsx_path = write_sinapi_xlsx(tmp_path / "sinapi.xlsx")

    catalog = read_sinapi_catalog(xlsx_path, sinapi_fixture_layout())

    for entry, row in zip(catalog.entries, expected_sinapi_entries(), strict=True):
        assert isinstance(entry.unit_price, Decimal)
        assert entry.unit_price == row.unit_price
