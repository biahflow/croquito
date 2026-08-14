"""Dinheiro trunca, quantidade arredonda, e a fronteira do double é declarada."""

from __future__ import annotations

from decimal import Decimal

from croquitodxf_valuation.rounding import (
    money_trunc,
    quantity_round,
    spreadsheet_double_trunc,
    trunc_divergence,
)


def test_money_trunc_never_rounds_up() -> None:
    product = Decimal("1.15") * Decimal("10.30")

    assert product == Decimal("11.8450")
    assert money_trunc(product) == Decimal("11.84")
    assert quantity_round(product) == Decimal("11.85")


def test_money_trunc_truncates_toward_zero_on_negatives() -> None:
    assert money_trunc(Decimal("-11.845")) == Decimal("-11.84")
    assert money_trunc(Decimal("-0.019")) == Decimal("-0.01")


def test_quantity_round_is_half_away_from_zero() -> None:
    assert quantity_round(Decimal("2.005")) == Decimal("2.01")
    assert quantity_round(Decimal("-2.005")) == Decimal("-2.01")
    assert quantity_round(Decimal("2.004")) == Decimal("2.00")


def test_money_trunc_keeps_two_decimal_scale() -> None:
    assert str(money_trunc(Decimal("12"))) == "12.00"
    assert str(quantity_round(Decimal("12.5"))) == "12.50"


def test_trunc_divergence_is_false_when_the_live_formula_reproduces_the_exact_value() -> None:
    # Pares documentados da fixture: a fórmula viva pode ficar na célula.
    assert trunc_divergence(Decimal("1.15"), Decimal("10.30")) is False
    assert trunc_divergence(Decimal("4.35"), Decimal("13.30")) is False
    assert trunc_divergence(Decimal("126.00"), Decimal("89.30")) is False


def test_trunc_divergence_is_true_when_the_double_product_falls_below() -> None:
    # 18,40 x 236,55 vale 4352,52 exato; em ponto flutuante o produto cai para 4352,51.
    assert money_trunc(Decimal("18.40") * Decimal("236.55")) == Decimal("4352.52")
    assert spreadsheet_double_trunc(Decimal("18.40"), Decimal("236.55")) == Decimal("4352.51")
    assert trunc_divergence(Decimal("18.40"), Decimal("236.55")) is True

    assert money_trunc(Decimal("12.00") * Decimal("612.40")) == Decimal("7348.80")
    assert spreadsheet_double_trunc(Decimal("12.00"), Decimal("612.40")) == Decimal("7348.79")
    assert trunc_divergence(Decimal("12.00"), Decimal("612.40")) is True


def test_boundary_pairs_exist_in_a_small_search() -> None:
    divergent = [
        (quantity, price)
        for quantity in (Decimal("0.50"), Decimal("1.00"), Decimal("3.00"))
        for price in (Decimal("2.30"), Decimal("20.15"), Decimal("32.30"))
        if trunc_divergence(quantity, price)
    ]

    assert divergent, "a busca de fronteira precisa achar ao menos um par divergente"
    for quantity, price in divergent:
        assert spreadsheet_double_trunc(quantity, price) < money_trunc(quantity * price)
