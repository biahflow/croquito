"""Código SCO é fatiado com formato fechado e recusa estruturada."""

from __future__ import annotations

import pytest

from croquito_valuation.errors import ValuationValidationError
from croquito_valuation.sco import (
    is_contract_code,
    is_family_row_code,
    is_sco_code,
    is_subgroup_row_code,
    parse_family_header,
    parse_intermediate_header,
    parse_sco_code,
    parse_subgroup_header,
)


def test_parses_the_reference_sample() -> None:
    parts = parse_sco_code("AD04050050(/)")

    assert parts.family == "AD"
    assert parts.subgroup == "04"
    assert parts.group == "05"
    assert parts.item == "0050"
    assert parts.variant == "/"
    assert parts.code == "AD04050050(/)"
    assert parts.subgroup_row_code == "AD0405"


def test_parses_letter_variants() -> None:
    assert parse_sco_code("XX99999999(B)").variant == "B"
    assert parse_sco_code("CE02100015(A)").variant == "A"


@pytest.mark.parametrize(
    "code",
    [
        "AD0405005(/)",
        "AD040500500(/)",
        "ad04050050(/)",
        "AD04050050",
        "AD04050050()",
        "AD04050050(a)",
        "AD04050050(1)",
        "AD04050050(//)",
        "",
    ],
)
def test_rejects_malformed_codes_with_a_stable_code(code: str) -> None:
    with pytest.raises(ValuationValidationError) as raised:
        parse_sco_code(code)

    assert raised.value.code == "SCO_CODE_UNPARSEABLE"
    assert raised.value.details["code"] == code
    assert is_sco_code(code) is False


def test_recognizes_family_and_subgroup_header_codes() -> None:
    assert is_family_row_code("AD") is True
    assert is_family_row_code("AD0405") is False
    assert is_subgroup_row_code("AD0405") is True
    assert is_subgroup_row_code("AD") is False
    assert is_subgroup_row_code("AD04050050(/)") is False


def test_parses_the_family_header_written_with_the_name() -> None:
    assert parse_family_header("AD PAVIMENTACAO SINTETICA") == ("AD", "PAVIMENTACAO SINTETICA")
    assert parse_family_header("CE  SERVICOS PRELIMINARES ") == (
        "CE",
        "SERVICOS PRELIMINARES",
    )


def test_parses_the_intermediate_header_between_family_and_subgroup() -> None:
    assert parse_intermediate_header("AD 04 SERVICOS DE PAVIMENTACAO") == (
        "AD04",
        "SERVICOS DE PAVIMENTACAO",
    )
    assert parse_intermediate_header("AD04 SERVICOS DE PAVIMENTACAO") == (
        "AD04",
        "SERVICOS DE PAVIMENTACAO",
    )


def test_parses_subgroup_headers_written_with_and_without_separators() -> None:
    assert parse_subgroup_header("AD 04.05 PISO INTERTRAVADO") == ("AD0405", "PISO INTERTRAVADO")
    assert parse_subgroup_header("AD 04 05 PISO INTERTRAVADO") == ("AD0405", "PISO INTERTRAVADO")
    assert parse_subgroup_header("AD0410MEIOFIODEGRANITO") == ("AD0410", "MEIOFIODEGRANITO")


@pytest.mark.parametrize(
    "text",
    [
        "PCRJ  SCO-Sistema de Custos de Obras",
        "CATALOGO SINTETICO DE PRECOS",
        "AD",
        "",
    ],
)
def test_hierarchy_headers_reject_sheet_titles(text: str) -> None:
    assert parse_family_header(text) is None
    assert parse_intermediate_header(text) is None
    assert parse_subgroup_header(text) is None


def test_subgroup_header_does_not_swallow_a_complete_item_code() -> None:
    assert parse_subgroup_header("AD04050050(/)") is None
    assert parse_subgroup_header("AD0405005(/)") is None
    assert parse_intermediate_header("AD04050050(/)") is None


def test_subgroup_and_intermediate_headers_do_not_overlap() -> None:
    assert parse_intermediate_header("AD 04.05 PISO INTERTRAVADO") is None
    assert parse_subgroup_header("AD 04 SERVICOS DE PAVIMENTACAO") is None


def test_is_contract_code_accepts_the_full_sco_code() -> None:
    assert is_contract_code("AD04050050(/)") is True
    assert is_contract_code("XX99999999(B)") is True


def test_is_contract_code_accepts_the_bare_form_without_a_variant() -> None:
    """Forma nua de item contratado fora da tabela SCO (ex.: `IE00040849`)."""
    assert is_contract_code("IE00040849") is True


@pytest.mark.parametrize(
    "value",
    [
        "IE0004084",
        "IE000408490",
        "ie00040849",
        "IE 00040849",
        "IE00040849(/)a",
        "",
    ],
)
def test_is_contract_code_rejects_text_without_the_structure(value: str) -> None:
    assert is_contract_code(value) is False
