"""Importação do catálogo: normalização, unicidade, digest e recusa por linha."""

from __future__ import annotations

import hashlib
from decimal import Decimal
from pathlib import Path

import pytest

from croquitodxf_valuation.catalog import normalize_unit, read_price_catalog
from croquitodxf_valuation.errors import ValuationValidationError
from croquitodxf_valuation.models import PriceCatalog
from croquitodxf_valuation.template import default_template
from tests.valuation.builders import (
    ColumnarCatalogRow,
    build_fixture,
    columnar_catalog_expectations,
    columnar_catalog_template,
    write_catalog_workbook,
    write_columnar_catalog_workbook,
    write_columnar_rows_workbook,
)

_VALID_ROWS = (
    ("AD", "PAVIMENTACAO SINTETICA", "", ""),
    ("AD0405", "PISO INTERTRAVADO SINTETICO", "", ""),
    ("AD04050050(/)", "PISO INTERTRAVADO SINTETICO 6CM", "M2", "89,30"),
)

_COLUMNAR_HIERARCHY: tuple[ColumnarCatalogRow, ...] = (
    ("AD PAVIMENTACAO SINTETICA", "...2", "...3", "...4", "...5", "...6"),
    ("", "AD 04 SERVICOS DE PAVIMENTACAO", "", "", "", "NA"),
    ("", "", "AD 04.05 PISO INTERTRAVADO SINTETICO", "", "", "NA"),
)


_NOTE_TEXT = "Nota: As marcas indicadas servem apenas para definir o padrao de qualidade."


def _read_columnar(path: Path) -> PriceCatalog:
    return read_price_catalog(
        path, columnar_catalog_template(), source_label="teste", reference_month="2026-01"
    )


def _read_declared(path: Path) -> PriceCatalog:
    """Lê com a nota editorial e o marcador de item sem cotação declarados no template."""
    template = columnar_catalog_template(note_prefixes=["Nota:"], unpriced_markers=["sem cotação"])
    return read_price_catalog(path, template, source_label="teste", reference_month="2026-01")


def test_imports_the_synthetic_catalog_from_a_hidden_sheet(tmp_path: Path) -> None:
    fixture = build_fixture(tmp_path)

    codes = [entry.code for entry in fixture.catalog.entries]
    assert len(codes) == len(set(codes))
    assert len(codes) == 32
    assert fixture.catalog.reference_month == "2026-01"

    piso = fixture.catalog.entry_for("AD04050050(/)")
    assert piso.unit_price == Decimal("89.30")
    assert piso.family_code == "AD"
    assert piso.family_name == "PAVIMENTACAO SINTETICA"
    assert piso.subgroup_code == "AD0405"
    assert piso.subgroup_name == "PISO INTERTRAVADO SINTETICO"


def test_variants_of_the_same_base_code_coexist_with_different_prices(tmp_path: Path) -> None:
    fixture = build_fixture(tmp_path)

    variant_a = fixture.catalog.entry_for("CE02100015(A)")
    variant_b = fixture.catalog.entry_for("CE02100015(B)")

    assert variant_a.unit_price == Decimal("142.75")
    assert variant_b.unit_price == Decimal("168.90")
    assert variant_a.unit_price != variant_b.unit_price


def test_units_and_prices_are_normalized_at_the_reading_boundary(tmp_path: Path) -> None:
    fixture = build_fixture(tmp_path)

    assert fixture.catalog.entry_for("AD04050050(/)").unit == "m2"
    assert fixture.catalog.entry_for("AD04050055(B)").unit == "m2"
    assert fixture.catalog.entry_for("MB01100020(/)").unit == "un"
    assert fixture.catalog.entry_for("SP01050015(A)").unit == "m3"
    assert fixture.catalog.entry_for("SP02100015(/)").unit == "mes"
    assert fixture.catalog.entry_for("CE02100020(/)").unit_price == Decimal("1580.00")


def test_source_digest_and_id_come_from_the_file_content(tmp_path: Path) -> None:
    fixture = build_fixture(tmp_path)
    expected = hashlib.sha256(fixture.catalog_path.read_bytes()).hexdigest()

    assert fixture.catalog.source_sha256 == expected

    reimported = read_price_catalog(
        fixture.catalog_path,
        fixture.template,
        source_label="reimportado",
        reference_month="2026-01",
    )
    assert reimported.id == fixture.catalog.id


def test_unknown_unit_passes_through_lowercased() -> None:
    assert normalize_unit(" CJ ") == "cj"
    assert normalize_unit("M²") == "m2"
    assert normalize_unit("unid.") == "un"


def test_row_with_unparseable_code_fails_with_sheet_and_row(tmp_path: Path) -> None:
    path = write_catalog_workbook(
        tmp_path / "quebrado.xlsx",
        [*_VALID_ROWS, ("AD0405005(/)", "ITEM QUEBRADO", "M2", "10,00")],
    )

    with pytest.raises(ValuationValidationError) as raised:
        read_price_catalog(
            path, default_template(), source_label="teste", reference_month="2026-01"
        )

    assert raised.value.code == "ROW_UNPARSEABLE"
    assert raised.value.details["sheet"] == "CATALOGO"
    assert raised.value.details["row"] == 5


def test_row_with_unreadable_price_fails(tmp_path: Path) -> None:
    path = write_catalog_workbook(
        tmp_path / "preco.xlsx",
        [*_VALID_ROWS, ("AD04050055(A)", "ITEM SEM PRECO LEGIVEL", "M2", "sob consulta")],
    )

    with pytest.raises(ValuationValidationError) as raised:
        read_price_catalog(
            path, default_template(), source_label="teste", reference_month="2026-01"
        )

    assert raised.value.code == "ROW_UNPARSEABLE"
    assert raised.value.details["reason"] == "preço ilegível"


def test_item_before_family_header_fails(tmp_path: Path) -> None:
    path = write_catalog_workbook(
        tmp_path / "sem-familia.xlsx",
        [("AD04050050(/)", "ITEM ORFAO", "M2", "10,00")],
    )

    with pytest.raises(ValuationValidationError) as raised:
        read_price_catalog(
            path, default_template(), source_label="teste", reference_month="2026-01"
        )

    assert raised.value.code == "ROW_UNPARSEABLE"
    assert raised.value.details["reason"] == "item antes de família ou subgrupo"


def test_missing_catalog_sheet_fails(tmp_path: Path) -> None:
    path = write_catalog_workbook(tmp_path / "outra-aba.xlsx", _VALID_ROWS, sheet_name="PRECOS")

    with pytest.raises(ValuationValidationError) as raised:
        read_price_catalog(
            path, default_template(), source_label="teste", reference_month="2026-01"
        )

    assert raised.value.code == "CATALOG_SHEET_MISSING"


def test_in_column_hierarchy_remains_the_default_mode(tmp_path: Path) -> None:
    path = write_catalog_workbook(tmp_path / "na-coluna.xlsx", _VALID_ROWS)

    catalog = read_price_catalog(
        path, default_template(), source_label="teste", reference_month="2026-01"
    )

    assert default_template().catalog.hierarchy_columns is None
    entry = catalog.entry_for("AD04050050(/)")
    assert entry.family_code == "AD"
    assert entry.family_name == "PAVIMENTACAO SINTETICA"
    assert entry.subgroup_code == "AD0405"
    assert entry.subgroup_name == "PISO INTERTRAVADO SINTETICO"
    assert entry.unit_price == Decimal("89.30")


def test_imports_the_catalog_with_the_hierarchy_in_its_own_columns(tmp_path: Path) -> None:
    path = write_columnar_catalog_workbook(tmp_path / "fgv06.xlsx")

    catalog = _read_columnar(path)

    assert [entry.code for entry in catalog.entries] == [
        expected.code for expected in columnar_catalog_expectations()
    ]
    for entry, expected in zip(catalog.entries, columnar_catalog_expectations(), strict=True):
        assert entry.description == expected.description
        assert entry.unit == expected.unit
        assert entry.unit_price == expected.unit_price
        assert entry.family_code == expected.family_code
        assert entry.family_name == expected.family_name
        assert entry.subgroup_code == expected.subgroup_code
        assert entry.subgroup_name == expected.subgroup_name


def test_columnar_catalog_reads_prices_written_as_ptbr_text(tmp_path: Path) -> None:
    path = write_columnar_catalog_workbook(tmp_path / "precos.xlsx")

    catalog = _read_columnar(path)

    assert catalog.entry_for("AD04050050(/)").unit_price == Decimal("217.69")
    assert catalog.entry_for("AD04050055(B)").unit_price == Decimal("1625.02")
    assert catalog.entry_for("CE02100020(/)").unit_price == Decimal("1580.00")
    assert catalog.entry_for("AD04100015(/)").unit == "m"


def test_columnar_catalog_accepts_a_subgroup_header_without_separators(tmp_path: Path) -> None:
    path = write_columnar_catalog_workbook(tmp_path / "colado.xlsx")

    entry = _read_columnar(path).entry_for("AD04100015(/)")

    assert entry.subgroup_code == "AD0410"
    assert entry.subgroup_name == "MEIOFIODEGRANITOSINTETICO"


def test_columnar_catalog_resets_the_hierarchy_on_the_next_family(tmp_path: Path) -> None:
    path = write_columnar_catalog_workbook(tmp_path / "duas-familias.xlsx")

    entry = _read_columnar(path).entry_for("CE02100015(A)")

    assert entry.family_code == "CE"
    assert entry.family_name == "SERVICOS PRELIMINARES E MOBILIARIO"
    assert entry.subgroup_code == "CE0210"
    assert entry.subgroup_name == "BANCOS E LIXEIRAS"


def test_columnar_item_before_the_hierarchy_fails(tmp_path: Path) -> None:
    path = write_columnar_rows_workbook(
        tmp_path / "orfao.xlsx",
        [("", "", "AD04050050(/)", "ITEM ORFAO", "M2", "10,00")],
    )

    with pytest.raises(ValuationValidationError) as raised:
        _read_columnar(path)

    assert raised.value.code == "ROW_UNPARSEABLE"
    assert raised.value.details["reason"] == "item antes de família ou subgrupo"
    assert raised.value.details["row"] == 4


def test_columnar_item_outside_the_current_subgroup_fails(tmp_path: Path) -> None:
    path = write_columnar_rows_workbook(
        tmp_path / "fora-do-subgrupo.xlsx",
        [*_COLUMNAR_HIERARCHY, ("", "", "AD04100015(/)", "MEIO FIO", "ML", "10,00")],
    )

    with pytest.raises(ValuationValidationError) as raised:
        _read_columnar(path)

    assert raised.value.code == "ROW_UNPARSEABLE"
    assert raised.value.details["reason"] == "item fora do subgrupo corrente"
    assert raised.value.details["subgroup"] == "AD0405"


def test_columnar_intermediate_outside_the_current_family_fails(tmp_path: Path) -> None:
    path = write_columnar_rows_workbook(
        tmp_path / "fora-da-familia.xlsx",
        [
            ("AD PAVIMENTACAO SINTETICA", "...2", "...3", "...4", "...5", "...6"),
            ("", "CE 02 MOBILIARIO URBANO", "", "", "", "NA"),
        ],
    )

    with pytest.raises(ValuationValidationError) as raised:
        _read_columnar(path)

    assert raised.value.code == "ROW_UNPARSEABLE"
    assert raised.value.details["reason"] == "subgrupo intermediário fora da família corrente"
    assert raised.value.details["family"] == "AD"


def test_columnar_subgroup_outside_the_current_intermediate_fails(tmp_path: Path) -> None:
    path = write_columnar_rows_workbook(
        tmp_path / "subgrupo-fora.xlsx",
        [*_COLUMNAR_HIERARCHY[:2], ("", "", "AD 07.05 OUTRO SUBGRUPO", "", "", "NA")],
    )

    with pytest.raises(ValuationValidationError) as raised:
        _read_columnar(path)

    assert raised.value.code == "ROW_UNPARSEABLE"
    assert raised.value.details["reason"] == "cabeçalho de subgrupo fora da hierarquia corrente"
    assert raised.value.details["intermediate"] == "AD04"


def test_columnar_family_header_that_is_a_sheet_title_fails(tmp_path: Path) -> None:
    path = write_columnar_rows_workbook(
        tmp_path / "titulo.xlsx",
        [("PCRJ  SCO-Sistema de Custos de Obras", "", "", "", "", "")],
    )

    with pytest.raises(ValuationValidationError) as raised:
        _read_columnar(path)

    assert raised.value.code == "ROW_UNPARSEABLE"
    assert raised.value.details["reason"] == "cabeçalho de família ilegível"
    assert raised.value.details["value"] == "PCRJ  SCO-Sistema de Custos de Obras"


def test_columnar_code_outside_the_sco_format_fails(tmp_path: Path) -> None:
    path = write_columnar_rows_workbook(
        tmp_path / "codigo-quebrado.xlsx",
        [*_COLUMNAR_HIERARCHY, ("", "", "AD0405005(/)", "ITEM QUEBRADO", "M2", "10,00")],
    )

    with pytest.raises(ValuationValidationError) as raised:
        _read_columnar(path)

    assert raised.value.code == "ROW_UNPARSEABLE"
    assert raised.value.details["reason"] == "código fora do formato SCO"
    assert raised.value.details["code"] == "AD0405005(/)"


def test_columnar_blank_separator_row_is_skipped_without_shifting_the_row_number(
    tmp_path: Path,
) -> None:
    path = write_columnar_rows_workbook(
        tmp_path / "separadora.xlsx",
        [
            *_COLUMNAR_HIERARCHY,
            ("", "", "", "", "", ""),
            ("", "", "AD0405005(/)", "ITEM QUEBRADO", "M2", "10,00"),
        ],
    )

    with pytest.raises(ValuationValidationError) as raised:
        _read_columnar(path)

    assert raised.value.details["row"] == 8


def test_columnar_catalog_without_any_item_fails(tmp_path: Path) -> None:
    path = write_columnar_rows_workbook(tmp_path / "vazio.xlsx", _COLUMNAR_HIERARCHY)

    with pytest.raises(ValuationValidationError) as raised:
        _read_columnar(path)

    assert raised.value.code == "CATALOG_EMPTY"


def test_a_note_row_declared_in_the_template_is_skipped(tmp_path: Path) -> None:
    """O catálogo publicado intercala nota editorial entre os cabeçalhos."""
    rows: tuple[ColumnarCatalogRow, ...] = (
        _COLUMNAR_HIERARCHY[0],
        (_NOTE_TEXT, "", "", "", "", "NA"),
        *_COLUMNAR_HIERARCHY[1:],
        ("", "", "AD04050050(/)", "PISO INTERTRAVADO SINTETICO 6CM", "M2", "89,30"),
    )
    path = write_columnar_rows_workbook(tmp_path / "com-nota.xlsx", rows)

    catalog = _read_declared(path)

    assert [entry.code for entry in catalog.entries] == ["AD04050050(/)"]
    assert catalog.entry_for("AD04050050(/)").family_name == "PAVIMENTACAO SINTETICA"


def test_a_note_row_that_the_template_does_not_declare_still_fails(tmp_path: Path) -> None:
    path = write_columnar_rows_workbook(
        tmp_path / "nota-nao-declarada.xlsx", [(_NOTE_TEXT, "", "", "", "", "NA")]
    )

    with pytest.raises(ValuationValidationError) as raised:
        _read_columnar(path)

    assert raised.value.code == "ROW_UNPARSEABLE"
    assert raised.value.details["reason"] == "cabeçalho de família ilegível"


def test_an_item_without_a_published_price_stays_out_of_the_catalog(tmp_path: Path) -> None:
    """`sem cotação` não é preço ilegível: é ausência de preço, e ausência não vira zero."""
    rows: tuple[ColumnarCatalogRow, ...] = (
        *_COLUMNAR_HIERARCHY,
        ("", "", "AD04050050(/)", "PISO INTERTRAVADO SINTETICO 6CM", "M2", "89,30"),
        ("", "", "AD04050055(B)", "PISO INTERTRAVADO SINTETICO 8CM", "M2", "  Sem Cotação "),
    )
    path = write_columnar_rows_workbook(tmp_path / "sem-cotacao.xlsx", rows)

    catalog = _read_declared(path)

    assert [entry.code for entry in catalog.entries] == ["AD04050050(/)"]
    assert not catalog.has_code("AD04050055(B)")


def test_an_unpriced_marker_that_the_template_does_not_declare_still_fails(tmp_path: Path) -> None:
    path = write_columnar_rows_workbook(
        tmp_path / "sem-cotacao-nao-declarada.xlsx",
        [
            *_COLUMNAR_HIERARCHY,
            ("", "", "AD04050050(/)", "PISO INTERTRAVADO SINTETICO 6CM", "M2", "sem cotação"),
        ],
    )

    with pytest.raises(ValuationValidationError) as raised:
        _read_columnar(path)

    assert raised.value.code == "ROW_UNPARSEABLE"
    assert raised.value.details["reason"] == "preço ilegível"
