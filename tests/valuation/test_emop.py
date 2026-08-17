"""Importador EMOP offline: leitor .DBF mínimo, sempre `origin=emop`, e o CLI que o expõe.

O catálogo digital EMOP real é pago e o arquivo real não existe neste repositório — tudo
aqui é sintético (`tests.valuation.emop_fixture`). O que importa nas recusas não é a
mensagem, é que nenhum artefato pela metade sobra no diretório de saída.
"""

from __future__ import annotations

import json
from dataclasses import replace
from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import ValidationError

from croquito_valuation.catalog import file_sha256
from croquito_valuation.emop import (
    EmopCatalogLayout,
    read_emop_catalog,
    read_emop_catalog_with_report,
)
from croquito_valuation.errors import ValuationValidationError, valuation_error_codes
from croquito_valuation.models import PriceCatalog, PriceOrigin
from croquito_worker.valuation.cli import CATALOG_FILENAME, EMOP_IMPORT_REPORT_FILENAME, main
from tests.valuation.emop_fixture import (
    EMOP_FIXTURE_ROWS,
    EMOP_REFERENCE_MONTH,
    EMOP_SOURCE_LABEL,
    FIELD_DESCRIPTION,
    FIELD_PRICE,
    corrupt_dbf_version,
    corrupt_field_bytes,
    emop_fixture_layout,
    expected_emop_entries,
    truncate_dbf_file,
    write_emop_dbf,
)

# --------------------------------------------------------------------------------------
# caminho feliz: entradas, origin, reference_month, digest
# --------------------------------------------------------------------------------------


def test_read_emop_catalog_matches_the_synthetic_fixture(tmp_path: Path) -> None:
    dbf_path = write_emop_dbf(tmp_path / "emop-sintetico.dbf")
    layout = emop_fixture_layout()

    catalog = read_emop_catalog(dbf_path, layout)

    assert catalog.origin == PriceOrigin.EMOP
    assert catalog.source_label == EMOP_SOURCE_LABEL
    assert catalog.reference_month == EMOP_REFERENCE_MONTH
    assert catalog.source_sha256 == file_sha256(dbf_path)
    assert catalog.entries == expected_emop_entries()
    assert all(entry.origin == PriceOrigin.EMOP for entry in catalog.entries)


def test_deleted_records_are_skipped_counted_and_never_imported(tmp_path: Path) -> None:
    dbf_path = write_emop_dbf(tmp_path / "emop-sintetico.dbf")
    layout = emop_fixture_layout()

    catalog, notes = read_emop_catalog_with_report(dbf_path, layout)

    deleted_codes = {row.code for row in EMOP_FIXTURE_ROWS if row.deleted}
    assert deleted_codes, "a fixture precisa declarar ao menos uma linha deletada"
    assert {entry.code for entry in catalog.entries}.isdisjoint(deleted_codes)
    assert notes.deleted_count == len(deleted_codes)
    assert set(notes.deleted_rows) == {
        index + 1 for index, row in enumerate(EMOP_FIXTURE_ROWS) if row.deleted
    }


def test_reimporting_the_same_bytes_yields_the_same_catalog_id(tmp_path: Path) -> None:
    first_path = write_emop_dbf(tmp_path / "primeiro.dbf")
    second_path = write_emop_dbf(tmp_path / "segundo.dbf")
    layout = emop_fixture_layout()

    first = read_emop_catalog(first_path, layout)
    second = read_emop_catalog(second_path, layout)

    assert first.id == second.id


# --------------------------------------------------------------------------------------
# recusas estruturais do .DBF
# --------------------------------------------------------------------------------------


def test_a_dbf_with_an_unsupported_version_is_refused(tmp_path: Path) -> None:
    dbf_path = write_emop_dbf(tmp_path / "emop.dbf")
    corrupt_dbf_version(dbf_path)

    with pytest.raises(ValuationValidationError) as raised:
        read_emop_catalog(dbf_path, emop_fixture_layout())

    assert raised.value.code == "EMOP_DBF_UNSUPPORTED"


def test_a_truncated_dbf_file_is_refused(tmp_path: Path) -> None:
    dbf_path = write_emop_dbf(tmp_path / "emop.dbf")
    truncate_dbf_file(dbf_path, keep_bytes=10)

    with pytest.raises(ValuationValidationError) as raised:
        read_emop_catalog(dbf_path, emop_fixture_layout())

    assert raised.value.code == "EMOP_DBF_UNSUPPORTED"


def test_a_dbf_truncated_in_the_middle_of_the_records_is_refused(tmp_path: Path) -> None:
    dbf_path = write_emop_dbf(tmp_path / "emop.dbf")
    full_size = dbf_path.stat().st_size
    truncate_dbf_file(dbf_path, keep_bytes=full_size - 5)

    with pytest.raises(ValuationValidationError) as raised:
        read_emop_catalog(dbf_path, emop_fixture_layout())

    assert raised.value.code == "EMOP_DBF_UNSUPPORTED"


# --------------------------------------------------------------------------------------
# campo declarado no layout ausente da tabela
# --------------------------------------------------------------------------------------


def test_a_field_declared_in_the_layout_but_missing_from_the_dbf_is_refused(
    tmp_path: Path,
) -> None:
    dbf_path = write_emop_dbf(tmp_path / "emop.dbf")
    layout = EmopCatalogLayout.model_validate(
        {**emop_fixture_layout().model_dump(), "price_field": "AUSENTE"}
    )

    with pytest.raises(ValuationValidationError) as raised:
        read_emop_catalog(dbf_path, layout)

    assert raised.value.code == "EMOP_FIELD_MISSING"
    assert raised.value.details["fields"] == ["AUSENTE"]


# --------------------------------------------------------------------------------------
# linha ilegível: código fora do padrão, preço não numérico, descrição vazia
# --------------------------------------------------------------------------------------


def test_a_row_whose_code_does_not_match_the_layout_pattern_is_refused(tmp_path: Path) -> None:
    rows = (replace(EMOP_FIXTURE_ROWS[0], code="BADCODE"), *EMOP_FIXTURE_ROWS[1:])
    dbf_path = write_emop_dbf(tmp_path / "emop.dbf", rows)

    with pytest.raises(ValuationValidationError) as raised:
        read_emop_catalog(dbf_path, emop_fixture_layout())

    assert raised.value.code == "EMOP_ROW_UNPARSEABLE"
    assert raised.value.details["row"] == 1


def test_a_dbf_tampered_after_generation_with_a_non_numeric_price_is_refused(
    tmp_path: Path,
) -> None:
    """Adultera os bytes depois de gerar: o mesmo arquivo, um campo alterado por fora do
    leitor. A recusa é estrutural — nada aqui vira `float` nem entra no catálogo."""
    dbf_path = write_emop_dbf(tmp_path / "emop.dbf")
    before = file_sha256(dbf_path)
    corrupt_field_bytes(dbf_path, row_index=0, field_name=FIELD_PRICE, raw_text="XYZ")
    assert file_sha256(dbf_path) != before, "a adulteração precisa mudar os bytes do arquivo"

    with pytest.raises(ValuationValidationError) as raised:
        read_emop_catalog(dbf_path, emop_fixture_layout())

    assert raised.value.code == "EMOP_ROW_UNPARSEABLE"
    assert raised.value.details["row"] == 1


def test_a_dbf_tampered_after_generation_with_an_empty_description_is_refused(
    tmp_path: Path,
) -> None:
    dbf_path = write_emop_dbf(tmp_path / "emop.dbf")
    corrupt_field_bytes(dbf_path, row_index=1, field_name=FIELD_DESCRIPTION, raw_text="")

    with pytest.raises(ValuationValidationError) as raised:
        read_emop_catalog(dbf_path, emop_fixture_layout())

    assert raised.value.code == "EMOP_ROW_UNPARSEABLE"
    assert raised.value.details["row"] == 2


# --------------------------------------------------------------------------------------
# catálogo vazio
# --------------------------------------------------------------------------------------


def test_a_dbf_with_every_row_deleted_is_refused_as_empty(tmp_path: Path) -> None:
    rows = tuple(replace(row, deleted=True) for row in EMOP_FIXTURE_ROWS)
    dbf_path = write_emop_dbf(tmp_path / "emop.dbf", rows)

    with pytest.raises(ValuationValidationError) as raised:
        read_emop_catalog(dbf_path, emop_fixture_layout())

    assert raised.value.code == "EMOP_EMPTY"


# --------------------------------------------------------------------------------------
# layout: código de padrão inválido ou frouxo demais (cinto e suspensório)
# --------------------------------------------------------------------------------------


def _layout_with_pattern(pattern: str) -> dict[str, object]:
    return {**emop_fixture_layout().model_dump(), "code_pattern": pattern}


def test_layout_refuses_a_code_pattern_that_does_not_compile() -> None:
    with pytest.raises(ValidationError) as raised:
        EmopCatalogLayout.model_validate(_layout_with_pattern("("))

    assert valuation_error_codes(raised.value) == ["EMOP_LAYOUT_CODE_PATTERN_INVALID"]


def test_layout_refuses_a_code_pattern_that_matches_the_empty_string() -> None:
    with pytest.raises(ValidationError) as raised:
        EmopCatalogLayout.model_validate(_layout_with_pattern(".*"))

    assert valuation_error_codes(raised.value) == ["EMOP_LAYOUT_CODE_PATTERN_INVALID"]


# --------------------------------------------------------------------------------------
# CLI: import-emop feliz e recusa fechada
# --------------------------------------------------------------------------------------


def _stdout(capsys: pytest.CaptureFixture[str]) -> dict[str, object]:
    lines = [line for line in capsys.readouterr().out.splitlines() if line.strip()]
    return dict(json.loads(lines[-1]))


def _layout_path(tmp_path: Path) -> Path:
    layout_path = tmp_path / "emop-layout.json"
    layout_path.write_text(emop_fixture_layout().model_dump_json(indent=2), encoding="utf-8")
    return layout_path


def test_cli_import_emop_publishes_only_the_catalog_and_its_own_report(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    dbf_path = write_emop_dbf(tmp_path / "emop.dbf")
    layout_path = _layout_path(tmp_path)
    output_dir = tmp_path / "import-emop"

    exit_code = main(
        [
            "import-emop",
            "--input",
            str(dbf_path),
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
    active_rows = [row for row in EMOP_FIXTURE_ROWS if not row.deleted]
    deleted_rows = [row for row in EMOP_FIXTURE_ROWS if row.deleted]
    assert payload["catalog_entries"] == len(active_rows)
    deleted_records = payload["deleted_records"]
    assert isinstance(deleted_records, dict)
    assert deleted_records["count"] == len(deleted_rows)

    assert (output_dir / CATALOG_FILENAME).is_file()
    assert (output_dir / EMOP_IMPORT_REPORT_FILENAME).is_file()

    catalog = PriceCatalog.model_validate_json(
        (output_dir / CATALOG_FILENAME).read_text(encoding="utf-8")
    )
    assert catalog.origin == PriceOrigin.EMOP
    assert catalog.source_sha256 == file_sha256(dbf_path)

    report = json.loads((output_dir / EMOP_IMPORT_REPORT_FILENAME).read_text(encoding="utf-8"))
    for key, value in report.items():
        assert payload[key] == value


def test_cli_import_emop_refuses_a_broken_dbf_without_publishing_anything(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    dbf_path = write_emop_dbf(tmp_path / "emop.dbf")
    corrupt_dbf_version(dbf_path)
    layout_path = _layout_path(tmp_path)
    output_dir = tmp_path / "import-emop"

    exit_code = main(
        [
            "import-emop",
            "--input",
            str(dbf_path),
            "--layout",
            str(layout_path),
            "--output",
            str(output_dir),
        ]
    )

    assert exit_code == 2
    assert _stdout(capsys)["refused"] == "EMOP_DBF_UNSUPPORTED"
    assert not output_dir.exists() or list(output_dir.iterdir()) == []


def test_cli_import_emop_refuses_an_invalid_layout_without_publishing_anything(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    dbf_path = write_emop_dbf(tmp_path / "emop.dbf")
    layout_path = tmp_path / "emop-layout.json"
    layout_path.write_text(
        json.dumps({**emop_fixture_layout().model_dump(), "code_pattern": ".*"}),
        encoding="utf-8",
    )
    output_dir = tmp_path / "import-emop"

    exit_code = main(
        [
            "import-emop",
            "--input",
            str(dbf_path),
            "--layout",
            str(layout_path),
            "--output",
            str(output_dir),
        ]
    )

    assert exit_code == 2
    assert _stdout(capsys)["refused"] == "EMOP_LAYOUT_CODE_PATTERN_INVALID"
    assert not output_dir.exists() or list(output_dir.iterdir()) == []


def test_decimal_price_never_goes_through_float(tmp_path: Path) -> None:
    """Cinto extra: o preço lido é sempre `Decimal` construído de texto, nunca `float`."""
    dbf_path = write_emop_dbf(tmp_path / "emop.dbf")

    catalog = read_emop_catalog(dbf_path, emop_fixture_layout())

    for entry, row in zip(catalog.entries, expected_emop_entries(), strict=True):
        assert isinstance(entry.unit_price, Decimal)
        assert entry.unit_price == row.unit_price
