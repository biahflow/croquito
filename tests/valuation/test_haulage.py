"""A tabela de derivação de transporte é dado curado, e o cálculo confere com a planilha.

O capítulo de transporte, carga e bota-fora não é medido na prancha: ele é função do resto
do orçamento. O gate deste arquivo são os sete casos reais do Campo do Toca — se o número
que sai daqui divergir do que a prefeitura imprimiu, a tabela deixou de descrever a fonte.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from pydantic import ValidationError

from croquito_valuation.errors import valuation_error_codes
from croquito_valuation.haulage import (
    HAULAGE_SEED_VERSION,
    HaulageFactor,
    HaulageTable,
    ServiceHaulage,
    default_haulage_table,
    derive_haulage_quantity,
    haulage_operands,
)

_HAULING = "TC04100050(/)"


def _derivation(
    *,
    target_code: str = _HAULING,
    origin_code: str = "BP09100050(B)",
    label: str = "PAVIMENTO RÍGIDO",
    factors: list[HaulageFactor] | None = None,
) -> ServiceHaulage:
    return ServiceHaulage(
        target_code=target_code,
        origin_code=origin_code,
        label=label,
        factors=factors
        if factors is not None
        else [
            HaulageFactor(name="P.ESP", value=Decimal("2.5")),
            HaulageFactor(name="ESP", value=Decimal("0.1"), unit="m"),
            HaulageFactor(name="DAM", value=Decimal("3.5"), unit="dam"),
        ],
    )


# --------------------------------------------------------------------------------------
# o seed empacotado
# --------------------------------------------------------------------------------------


def test_the_packaged_seed_loads_and_declares_its_version() -> None:
    table = default_haulage_table()

    assert table.version == HAULAGE_SEED_VERSION
    assert len(table.derivations) == 111
    assert "Campo do Toca" in table.source_label


def test_the_seed_declares_what_it_could_not_map() -> None:
    """Materiais que a fonte cobre e que não têm código não somem: ficam declarados.

    São linhas de um template mais amplo que o contrato desta obra — silenciá-las faria a
    tabela parecer completa quando ela não é.
    """
    table = default_haulage_table()

    assert "TELHA (TRAPEZOIDAL)" in table.unmapped_labels
    assert len(table.unmapped_labels) == 6


def test_the_seed_keeps_the_formula_shape_of_each_destination() -> None:
    """A forma muda com o destino, e a tabela guarda a que a memória declarou."""
    table = default_haulage_table()
    shapes = {
        tuple(factor.name for factor in derivation.factors) for derivation in table.derivations
    }

    assert ("P.ESP", "ESP", "DAM") in shapes  # transporte horizontal de item medido em área
    assert ("P.ESP", "DAM") in shapes  # ...de item já medido em volume
    assert ("P.ESP", "ESP") in shapes  # carga e descarga: sem distância
    assert ("EMP",) in shapes  # retirada de entulho: empolamento


def test_the_hauling_service_is_fed_by_the_whole_budget() -> None:
    table = default_haulage_table()

    assert len(table.derivations_for(_HAULING)) == 106
    assert table.derivations_for("BP09100050(B)") == []


# --------------------------------------------------------------------------------------
# o gate: os sete casos reais
# --------------------------------------------------------------------------------------

#: `(código de origem, quantidade do orçamento, quantidade impressa na memória)`.
_TOCA_CASES = [
    ("BP09100050(B)", "418.12", "365.86"),
    ("MT14150050(A)", "478.74", "754.02"),
    ("BP04050350(/)", "478.74", "251.34"),
    ("PJ14100500(/)", "783.86", "20.58"),
    ("ET39050109(/)", "418.12", "10.98"),
    ("PJ14150203(A)", "783.86", "10.97"),
    ("BP09200353(/)", "59.34", "29.91"),
]


@pytest.mark.parametrize(("origin_code", "quantity", "expected"), _TOCA_CASES)
def test_the_derived_quantity_matches_the_printed_memory(
    origin_code: str, quantity: str, expected: str
) -> None:
    table = default_haulage_table()
    derivation = next(
        item for item in table.derivations_for(_HAULING) if item.origin_code == origin_code
    )

    assert derive_haulage_quantity(Decimal(quantity), derivation) == Decimal(expected)


def test_a_factor_can_be_overridden_per_worksite() -> None:
    """A distância do carrinho de mão pode ser do canteiro, não do contrato.

    Enquanto ninguém decide, vale a da fonte; quando decidirem, troca-se sem tocar na
    tabela.
    """
    derivation = _derivation()

    doubled = derive_haulage_quantity(
        Decimal("418.12"), derivation, overrides={"DAM": Decimal("7.0")}
    )

    assert doubled == Decimal("731.71")
    assert derive_haulage_quantity(Decimal("418.12"), derivation) == Decimal("365.86")


# --------------------------------------------------------------------------------------
# operandos para a memória
# --------------------------------------------------------------------------------------


def test_the_operands_carry_the_origin_quantity_as_a_literal() -> None:
    """A memória publicada não tem referência cruzada: quem confere lê o número usado."""
    operands = haulage_operands(Decimal("418.12"), _derivation(), origin_unit="m2")

    assert [operand.name for operand in operands] == [
        "QUANTIDADE BP09100050(B)",
        "P.ESP",
        "ESP",
        "DAM",
    ]
    assert operands[0].value == Decimal("418.12")
    assert operands[0].unit == "m2"
    assert operands[3].unit == "dam"


def test_the_operands_reflect_the_override() -> None:
    operands = haulage_operands(Decimal("418.12"), _derivation(), overrides={"DAM": Decimal("7.0")})

    assert operands[3].value == Decimal("7.0")


# --------------------------------------------------------------------------------------
# recusas
# --------------------------------------------------------------------------------------


def test_a_service_cannot_derive_its_own_quantity() -> None:
    with pytest.raises(ValidationError) as raised:
        _derivation(origin_code=_HAULING)

    assert valuation_error_codes(raised.value) == ["HAULAGE_SELF_DERIVATION"]


def test_a_code_outside_any_catalog_shape_is_refused() -> None:
    with pytest.raises(ValidationError) as raised:
        _derivation(origin_code="codigo minusculo")

    assert valuation_error_codes(raised.value) == ["HAULAGE_CODE_INVALID"]


def test_the_item_no_table_priced_can_still_be_hauled() -> None:
    """O contrato real traz códigos `IE...` fora do SCO; o entulho deles conta igual."""
    derivation = _derivation(origin_code="IE00040849", label="TIJOLO REFRATÁRIO")

    assert derivation.origin_code == "IE00040849"


def test_the_same_pair_cannot_be_derived_twice() -> None:
    with pytest.raises(ValidationError) as raised:
        HaulageTable(
            version=HAULAGE_SEED_VERSION,
            source_label="fixture",
            derivations=[_derivation(), _derivation()],
        )

    assert valuation_error_codes(raised.value) == ["HAULAGE_DUPLICATE_PAIR"]


def test_a_factor_of_zero_is_refused() -> None:
    """Fator zero zeraria a linha em silêncio; ausência de fator se declara não declarando."""
    with pytest.raises(ValidationError):
        HaulageFactor(name="P.ESP", value=Decimal("0"))
