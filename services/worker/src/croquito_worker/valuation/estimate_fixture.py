"""Fixture sintética do orçamento-base: a composição manual e as decisões da cascata.

Complemento de `synthetic.py` (medição licitada) para a outra margem da fronteira do
`ADR-0027`. A prancha, a legenda e as decisões de takeoff são as mesmas — é a mesma obra
sintética —; o que muda é o ato seguinte: em vez de confirmar código contra um catálogo só,
o orçamentista escolhe, item a item, **de qual fonte** da cascata vem o preço.

As decisões contam a história que o M8 existe para representar:

- os itens que a tabela pública precifica ficam no SCO;
- o mobiliário e o piso emborrachado vão para a EMOP (o SCO sintético até tem preço para
  eles, mas a escolha da fonte é do orçamentista, e o orçamento-base admite a EMOP);
- o gramado, que nenhuma tabela publicada precifica, recebe uma **composição manual**;
- a luminária é rejeitada em toda a cascata e sai declarada em `unpriced_item_ids`, que é
  a lista de candidatos a composição nova — nunca preço de item parecido.

Nada aqui é dado de cliente: preços, coeficientes e códigos são inventados, e o rótulo de
cada composição diz "SINTETICA".
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Final, Literal

from croquito_valuation.assignment import CodeAssignmentBatch, CodeAssignmentInput
from croquito_valuation.composition import CompositionLine, CompositionSet, CostComposition
from croquito_valuation.errors import ValuationValidationError
from croquito_valuation.models import PriceCatalog, PriceOrigin
from croquito_valuation.rounding import money_trunc
from croquito_valuation.takeoff import TakeoffPacket
from croquito_worker.valuation.synthetic import (
    SYNTHETIC_TAKEOFF_REVIEWER,
    item_for_label,
)

SYNTHETIC_COMPOSITION_SOURCE_LABEL: Final = "COMPOSICOES SINTETICAS DO ORCAMENTISTA (fixture)"
SYNTHETIC_COMPOSITION_REFERENCE_MONTH: Final = "2026-07"
SYNTHETIC_COMPOSITION_CODE: Final = "COMP.GRAMADO.001"
SYNTHETIC_ESTIMATE_DECIDED_AT: Final = datetime(2026, 4, 15, 12, 0, tzinfo=UTC)

SYNTHETIC_ESTIMATE_WORKSITE_KEY: Final = "praca-sintetica-oeste-orcamento"
SYNTHETIC_ESTIMATE_WORKSITE_NAME: Final = "PRACA SINTETICA OESTE (ORCAMENTO-BASE)"
SYNTHETIC_ESTIMATE_WORKSITE_ADDRESS: Final = "RUA SINTETICA 400 — BAIRRO SINTETICO"

_PAVEMENT_LABEL: Final = "PISO INTERTRAVADO SINTETICO"
_LAWN_LABEL: Final = "GRAMADO SINTETICO"
_FENCE_LABEL: Final = "ALAMBRADO SINTETICO"
_BENCH_LABEL: Final = "BANCO DE CONCRETO SINTETICO"
_LAMP_LABEL: Final = "LUMINARIA DUPLA SINTETICA"
_RUBBER_LABEL: Final = "PISO EMBORRACHADO SINTETICO"

_LAWN_COMPOSITION_LINES: Final[tuple[CompositionLine, ...]] = (
    CompositionLine(
        kind="material",
        description="GRAMA SINTETICA EM PLACAS, POSTA EM OBRA",
        unit="m2",
        coefficient=Decimal("1.05"),
        unit_price=Decimal("18.40"),
        reference="cotacao sintetica de fornecedor 2026-07",
    ),
    CompositionLine(
        kind="labor",
        description="JARDINEIRO SINTETICO COM ENCARGOS",
        unit="h",
        coefficient=Decimal("0.35"),
        unit_price=Decimal("22.50"),
        reference="EMOP.CE.001 (referencia declarada da fixture)",
    ),
    CompositionLine(
        kind="equipment",
        description="COMPACTADOR SINTETICO DE PLACA VIBRATORIA",
        unit="h",
        coefficient=Decimal("0.05"),
        unit_price=Decimal("31.20"),
        reference="cotacao sintetica de locacao 2026-07",
    ),
)
"""1,05 m² de placa por m² assentado, 0,35 h de jardineiro e 0,05 h de compactador.

A mão de obra fecha em 7,875 e trunca para 7,87 na própria linha: é o caso que mostra, na
fixture, que o preço unitário soma parcelas já truncadas — a regra conservadora declarada
em `composition.py`."""


def build_synthetic_composition_set() -> CompositionSet:
    """Composições manuais sintéticas do orçamentista; hoje só a do gramado.

    O preço unitário não é digitado: ele é a soma truncada das linhas, calculada pela mesma
    função que o modelo usa para recomputá-lo — declarar um número à mão aqui deixaria a
    fixture livre para divergir da regra que ela deveria demonstrar.
    """
    lines = list(_LAWN_COMPOSITION_LINES)
    return CompositionSet(
        source_label=SYNTHETIC_COMPOSITION_SOURCE_LABEL,
        reference_month=SYNTHETIC_COMPOSITION_REFERENCE_MONTH,
        compositions=[
            CostComposition(
                code=SYNTHETIC_COMPOSITION_CODE,
                description="EXECUCAO DE GRAMADO SINTETICO EM PLACAS, INCLUSIVE PREPARO",
                unit="m2",
                family_code="COMP",
                family_name="COMPOSICOES SINTETICAS DO ORCAMENTISTA",
                subgroup_code="COMP.01",
                subgroup_name="PAISAGISMO SINTETICO",
                lines=lines,
                unit_price=money_trunc(sum((line.amount for line in lines), Decimal("0.00"))),
            )
        ],
    )


@dataclass(frozen=True, slots=True)
class _DemoEstimateDecision:
    """Decisão de código do orçamentista sintético citando a ORIGEM da fonte escolhida.

    A fixture cita a origem, não o digest: o digest é do arquivo que a rodada importou e
    entra em `build_demo_estimate_assignments` a partir da cascata real — fixar um digest
    aqui seria inventar uma amarração que a rodada não fez.
    """

    label: str
    action: Literal["confirm", "reject"]
    origin: PriceOrigin | None = None
    code: str | None = None
    note: str | None = None


_DEMO_ESTIMATE_DECISIONS: Final[tuple[_DemoEstimateDecision, ...]] = (
    _DemoEstimateDecision(
        label=_PAVEMENT_LABEL,
        action="confirm",
        origin=PriceOrigin.SCO,
        code="AD04050060(/)",
    ),
    _DemoEstimateDecision(
        label=_LAWN_LABEL,
        action="confirm",
        origin=PriceOrigin.COMPOSITION,
        code=SYNTHETIC_COMPOSITION_CODE,
        note="sem cotacao publicada; preco de composicao manual do orcamentista",
    ),
    _DemoEstimateDecision(
        label=_FENCE_LABEL,
        action="confirm",
        origin=PriceOrigin.SCO,
        code="CE02100010(/)",
    ),
    _DemoEstimateDecision(
        label=_BENCH_LABEL,
        action="confirm",
        origin=PriceOrigin.EMOP,
        code="EMOP.CE.001",
        note="mobiliario cotado pela EMOP nesta pre-licitacao",
    ),
    _DemoEstimateDecision(
        label=_LAMP_LABEL,
        action="reject",
        note="sem cotacao em nenhuma fonte da cascata; exige composicao nova",
    ),
    _DemoEstimateDecision(
        label=_RUBBER_LABEL,
        action="confirm",
        origin=PriceOrigin.EMOP,
        code="EMOP.AD.001",
        note="piso emborrachado cotado pela EMOP nesta pre-licitacao",
    ),
)


def _catalog_for_origin(cascade: Sequence[PriceCatalog], origin: PriceOrigin) -> PriceCatalog:
    """Catálogo da cascata com a origem citada pela fixture; ausência falha alto."""
    for catalog in cascade:
        if catalog.origin == origin:
            return catalog
    raise ValuationValidationError(
        "SYNTHETIC_CASCADE_ORIGIN_MISSING",
        "a fixture do orçamento-base cita uma origem que não está na cascata da rodada",
        {"origin": origin.value, "cascade": [entry.origin.value for entry in cascade]},
    )


def build_demo_estimate_assignments(
    packet: TakeoffPacket, cascade: Sequence[PriceCatalog]
) -> CodeAssignmentBatch:
    """Decisões de código do orçamentista sintético sobre a CASCATA de fontes.

    Cada confirmação cita o digest do catálogo da origem escolhida, lido da cascata que a
    rodada montou. A luminária é rejeitada: nenhuma fonte a precifica, e é ela que
    demonstra `unpriced_item_ids` no orçamento publicado.
    """
    return CodeAssignmentBatch(
        assignments=[
            CodeAssignmentInput(
                item_id=item_for_label(packet, decision.label).id,
                action=decision.action,
                code=decision.code,
                catalog_sha256=(
                    None
                    if decision.origin is None
                    else _catalog_for_origin(cascade, decision.origin).source_sha256
                ),
                reviewer_id=SYNTHETIC_TAKEOFF_REVIEWER,
                reviewer_role="orcamentista",
                decided_at=SYNTHETIC_ESTIMATE_DECIDED_AT,
                note=decision.note,
            )
            for decision in _DEMO_ESTIMATE_DECISIONS
        ]
    )
