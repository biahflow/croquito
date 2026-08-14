"""Confere cotas confirmadas umas contra as outras.

Uma cota isolada não tem como estar errada — é só um número. O erro aparece quando os
números precisam conviver: se três trechos partilham a largura total, a soma tem que bater.
Um projetista faz essa conta antes de desenhar, e é ela que separa "o croqui fecha" de
"faltam 2,90 m e alguém descobre isso em obra".

Aritmética sobre leituras confirmadas, não geometria: roda antes de existir cena e não
depende de pixel nenhum.

## Por que verificar e não descobrir

A tentação é procurar sozinho quais somas fecham. Medido no croqui Guaxindiba, com teto de
quatro parcelas, isso produz **4 fechamentos e 213 quase-fechamentos** entre 12 cotas — e
sem restringir a números puros, 636 e 26.622, porque a busca soma alegremente vão de portão
com altura de muro. Dos 4 fechamentos, 3 são coincidência aritmética.

Duzentos avisos treinam o revisor a ignorar avisos. Então:

- `verify_chain` é a API principal: alguém **declara** que estas parcelas partilham este
  total, e a função confere. Zero falso positivo, porque não adivinha nada.
- `suggest_chains` só devolve o que fecha **dentro da tolerância**, ordenado e limitado, e
  o resultado é sugestão para uma pessoa olhar — nunca `Constraint` gravada sozinha.

Achar automaticamente o metro perdido exige saber quais cotas caem na mesma reta, e isso é
topologia, não soma. Enquanto essa informação não existir, esta camada verifica em vez de
palpitar.
"""

from __future__ import annotations

import re
from decimal import Decimal
from itertools import combinations

from pydantic import BaseModel, ConfigDict, Field

from croquitodxf_core.models import Issue, IssueSeverity, UnitCode

from .review import DimensionReading, ReadingStatus, ReviewPacket

MAX_CHAIN_TERMS = 4
"""Teto de parcelas por cadeia: com parcelas suficientes qualquer total é alcançável."""

MAX_SUGGESTIONS = 12
"""Teto de sugestões. Lista que não cabe na tela não é revisada, é rolada."""

PLAN_DIMENSION = re.compile(r"^\d+(?:[.,]\d+)?\s*m?$")
"""Cota de planta é número puro na folha.

`kind` não serve para separar: no croqui real `21,75` está marcado `height` e é a largura
do campo, enquanto `h=3,80` é altura de muro. O que distingue de verdade é a escrita —
anotação carrega palavra ou símbolo (`h=`, `Portão 1,0 x 2,05`), cota de planta não.
"""


class ClosureModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ChainTerm(ClosureModel):
    reading_id: str
    value_m: Decimal
    raw_text: str


class DimensionChain(ClosureModel):
    """Uma soma de trechos comparada com um total, ambos lidos da folha."""

    total: ChainTerm
    parts: tuple[ChainTerm, ...] = Field(min_length=2)
    residual_m: Decimal
    tolerance_m: Decimal

    @property
    def closes(self) -> bool:
        return abs(self.residual_m) <= self.tolerance_m

    @property
    def parts_sum_m(self) -> Decimal:
        return sum((term.value_m for term in self.parts), Decimal(0))

    def describe(self) -> str:
        soma = " + ".join(str(term.value_m) for term in self.parts)
        return f"{soma} = {self.parts_sum_m} contra {self.total.value_m}"

    def issue(self) -> Issue | None:
        """Divergência como `warning`: o revisor decide, o export não trava.

        Travar seria transformar conta de plausibilidade em veto técnico — e o croqui pode
        estar certo com a cota faltando, que é justamente o que se quer mostrar.
        """
        if self.closes:
            return None
        return Issue(
            code="DIMENSION_CHAIN_MISMATCH",
            severity=IssueSeverity.WARNING,
            message=(
                f"As cotas declaradas não fecham: {self.describe()} "
                f"(diferença de {abs(self.residual_m)} m). "
                "Confira se falta um trecho no croqui ou se alguma medida está incompleta."
            ),
        )


class ChainVerificationError(ValueError):
    """As leituras indicadas não permitem montar a cadeia."""


def _tolerance_m(reading: DimensionReading) -> Decimal:
    """Meia casa do que foi escrito: `14,50` promete centímetro, `14,5` não."""
    tolerance = Decimal(10) ** -reading.written_decimals / 2
    if reading.unit is UnitCode.MILLIMETRE:
        tolerance *= Decimal("0.001")
    return tolerance


def _value_m(reading: DimensionReading) -> Decimal | None:
    if reading.value_si is None:
        return None
    if reading.unit is UnitCode.MILLIMETRE:
        return reading.value_si * Decimal("0.001")
    return reading.value_si


def _term(reading: DimensionReading) -> tuple[ChainTerm, Decimal]:
    value = _value_m(reading)
    if value is None:
        raise ChainVerificationError(f"A leitura {reading.id} não tem valor numérico.")
    return (
        ChainTerm(reading_id=reading.id, value_m=value, raw_text=reading.raw_text),
        _tolerance_m(reading),
    )


def _confirmed(packet: ReviewPacket) -> dict[str, DimensionReading]:
    return {
        reading.id: reading
        for reading in packet.readings
        if reading.status is ReadingStatus.CONFIRMED
    }


def is_plan_dimension(reading: DimensionReading) -> bool:
    return bool(PLAN_DIMENSION.match(reading.raw_text.strip()))


def verify_chain(packet: ReviewPacket, *, total_id: str, part_ids: list[str]) -> DimensionChain:
    """Confere uma cadeia declarada: estas parcelas partilham este total?

    A tolerância da cadeia é a soma das tolerâncias envolvidas. Exigir de uma soma de
    quatro a precisão de uma cota isolada reprovaria cadeias corretas por arredondamento.
    """
    if len(part_ids) < 2:
        raise ChainVerificationError("Uma cadeia precisa de pelo menos duas parcelas.")
    if total_id in part_ids:
        raise ChainVerificationError("O total não pode ser também parcela de si mesmo.")
    if len(set(part_ids)) != len(part_ids):
        raise ChainVerificationError("A mesma leitura não pode entrar duas vezes na cadeia.")

    confirmed = _confirmed(packet)
    missing = [item for item in [total_id, *part_ids] if item not in confirmed]
    if missing:
        raise ChainVerificationError(
            f"Cadeia exige leitura confirmada; ainda não confirmadas: {', '.join(missing)}"
        )

    total_term, total_tolerance = _term(confirmed[total_id])
    parts: list[ChainTerm] = []
    tolerance = total_tolerance
    for part_id in part_ids:
        term, part_tolerance = _term(confirmed[part_id])
        parts.append(term)
        tolerance += part_tolerance

    parts_sum = sum((term.value_m for term in parts), Decimal(0))
    return DimensionChain(
        total=total_term,
        parts=tuple(parts),
        residual_m=parts_sum - total_term.value_m,
        tolerance_m=tolerance,
    )


def suggest_chains(
    packet: ReviewPacket,
    *,
    max_terms: int = MAX_CHAIN_TERMS,
    limit: int = MAX_SUGGESTIONS,
) -> list[DimensionChain]:
    """Somas que fecham exatamente, como sugestão para uma pessoa confirmar.

    Só entram cotas de planta, e só cadeias dentro da tolerância. Mesmo assim há
    coincidência: no croqui real, 3 das 4 sugestões são acaso aritmético. Por isso o
    retorno é sugestão, e a `Constraint` só nasce de `verify_chain`.
    """
    usable: list[tuple[DimensionReading, Decimal, Decimal]] = []
    for reading in _confirmed(packet).values():
        value = _value_m(reading)
        if value is None or value <= 0 or not is_plan_dimension(reading):
            continue
        usable.append((reading, value, _tolerance_m(reading)))

    found: list[DimensionChain] = []
    for total_reading, total_value, total_tolerance in usable:
        others = [item for item in usable if item[0].id != total_reading.id]
        for size in range(2, min(max_terms, len(others)) + 1):
            for subset in combinations(others, size):
                parts_sum = sum((value for _r, value, _t in subset), Decimal(0))
                tolerance = total_tolerance + sum((tol for _r, _v, tol in subset), Decimal(0))
                residual = parts_sum - total_value
                if abs(residual) > tolerance:
                    continue
                found.append(
                    DimensionChain(
                        total=ChainTerm(
                            reading_id=total_reading.id,
                            value_m=total_value,
                            raw_text=total_reading.raw_text,
                        ),
                        parts=tuple(
                            ChainTerm(reading_id=item.id, value_m=value, raw_text=item.raw_text)
                            for item, value, _tol in subset
                        ),
                        residual_m=residual,
                        tolerance_m=tolerance,
                    )
                )

    # Cadeia curta e exata primeiro: entre duas explicações do mesmo total, a de menos
    # partes é a que o revisor consegue conferir olhando a folha.
    found.sort(key=lambda item: (len(item.parts), abs(item.residual_m)))
    return found[:limit]
