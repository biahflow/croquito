"""Regras de arredondamento da medição: dinheiro trunca, quantidade arredonda.

A planilha MAPÃO trunca dinheiro em duas casas (`TRUNC`) e arredonda quantidade
(`ROUND`). As duas operações são diferentes e a diferença aparece em centavos: uma
quantidade 1,15 a R$ 10,30 vale R$ 11,84 truncada e R$ 11,85 arredondada. Todo cálculo
monetário do módulo passa por estas funções, sempre em `Decimal`.
"""

from __future__ import annotations

import math
from decimal import ROUND_DOWN, ROUND_HALF_UP, Decimal
from typing import Final

MONEY_QUANTUM: Final = Decimal("0.01")
QUANTITY_QUANTUM: Final = Decimal("0.01")


def money_trunc(value: Decimal) -> Decimal:
    """`TRUNC(x, 2)` da planilha: trunca em direção a zero e nunca arredonda."""
    return value.quantize(MONEY_QUANTUM, rounding=ROUND_DOWN)


def quantity_round(value: Decimal) -> Decimal:
    """`ROUND(x, 2)` da planilha: meia distância para longe do zero."""
    return value.quantize(QUANTITY_QUANTUM, rounding=ROUND_HALF_UP)


def spreadsheet_double_trunc(quantity: Decimal, unit_price: Decimal) -> Decimal:
    """Replica o truncamento que uma fórmula viva faria sobre o produto em ponto flutuante.

    Fronteira explícita: `float(...)` só existe aqui, para modelar o motor da planilha,
    e o resultado volta a `Decimal` por `Decimal(str(...))`. O modelo é conservador —
    Excel e LibreOffice aplicam correções de último bit que podem devolver o valor
    exato mesmo quando esta réplica não devolve. Quando a réplica diverge do cálculo
    exato, o módulo prefere gravar o valor literal a confiar na fórmula.
    """
    product = float(quantity) * float(unit_price)
    return Decimal(str(math.trunc(product * 100) / 100))


def trunc_divergence(quantity: Decimal, unit_price: Decimal) -> bool:
    """`True` quando a fórmula viva pode não reproduzir o valor exato em `Decimal`."""
    return spreadsheet_double_trunc(quantity, unit_price) != money_trunc(quantity * unit_price)
