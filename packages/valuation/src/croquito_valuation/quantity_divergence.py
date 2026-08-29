"""A divergência entre a quantidade da CENA e a lida na LEGENDA (F-047 T5, ADR-0058 D6).

Quando o mesmo elemento tem quantidade dos dois lados da fronteira, o produto mostra as
duas e **recusa fechar**. Nenhuma origem apaga a outra: a cena não sobrescreve a legenda, a
legenda não sobrescreve a cena, e quem revisa vê os dois números, a origem de cada um e a
diferença antes de decidir. Divergência é o *valor* da feature — é onde a redigitação
escondia o erro —, então conciliá-la em silêncio anularia o motivo de ela existir.

Três regras atravessam o módulo:

- **A tolerância é constante NOMEADA**, `maior(1% do valor da legenda, 0,01 na unidade do
  item)` — o piso existe porque 1% de uma quantidade pequena é menor que a menor diferença
  que a planilha sabe escrever, e sem ele todo item miúdo viraria divergência.
- **A comparação é `>`, nunca `>=`**: diferença exatamente igual à tolerância NÃO abre
  divergência (ato humano de 2026-08-28). A tolerância é o que ainda se aceita, não o
  primeiro valor recusado.
- **Resolver é decisão humana registrada**, com autor e instante, e só entre os dois
  números que existem: "nenhuma das duas" não é oferecida, porque digitar uma terceira
  quantidade aqui seria exatamente a redigitação que a feature existe para eliminar.

O módulo é a metade PURA da divergência: modelos, tolerância e invariantes. Ele não conhece
`TakeoffItem` (é `takeoff.py` quem o carrega, e por isso não pode importar de lá) nem o
`quantitativos.csv` (é `quantity_source.py` quem o lê e detecta a divergência).
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Final, Literal, NamedTuple

from pydantic import Field, field_validator, model_validator

from croquito_core.models import ELEMENT_REF_PATTERN, Precision
from croquito_valuation.errors import ValuationValidationError
from croquito_valuation.models import (
    SCENE_ELIGIBLE_PRECISIONS,
    ExactDecimal,
    ValuationContractModel,
)
from croquito_valuation.rounding import quantity_round

QUANTITY_DIVERGENCE_RELATIVE_TOLERANCE: Final = Decimal("0.01")
"""1% da quantidade LIDA NA LEGENDA — e não da média nem da quantidade da cena.

A referência é a legenda porque é ela que o orçamentista escreveu e é contra ela que a
divergência é lida na tela ("a cena diz 2% a mais do que eu li"). Ancorar no outro lado
faria a mesma dupla de números abrir ou não abrir conforme a ordem da comparação.
"""

QUANTITY_DIVERGENCE_ABSOLUTE_FLOOR: Final = Decimal("0.01")
"""Piso absoluto na unidade do item: abaixo dele, 1% é menor que a menor diferença que a
planilha consegue escrever (a quantidade é arredondada em duas casas antes de virar linha).
Sem o piso, um alambrado de `0,80 m` abriria divergência com `0,81 m` — ruído puro."""


class ToleranceBound(StrEnum):
    """Qual das duas parcelas GOVERNOU a tolerância nomeada: a relativa (1% da legenda) ou
    o piso absoluto. Existe para a tela não precisar comparar `relative_tolerance` com
    `absolute_floor` — o servidor já decidiu e nomeia."""

    RELATIVE = "relative"
    ABSOLUTE_FLOOR = "absolute_floor"


class ToleranceBreakdown(NamedTuple):
    """As duas parcelas da tolerância nomeada e qual delas venceu — a MESMA conta que
    `quantity_divergence_tolerance` faz, nunca uma segunda derivação: só esta função
    calcula, e o resto do módulo lê os campos daqui."""

    relative_tolerance: Decimal
    absolute_floor: Decimal
    tolerance: Decimal
    tolerance_bound: ToleranceBound


def quantity_divergence_tolerance_breakdown(legend_quantity: Decimal) -> ToleranceBreakdown:
    """As duas parcelas de `maior(1% da legenda, 0,01)`, e qual delas governou.

    Empate (a borda em que 1% é exatamente 0,01) é lido como a relativa vencendo — é o
    caso comum, e o piso é a EXCEÇÃO que só governa quando é estritamente maior. Mesma
    semântica de `max(relative, floor)` que o código já tinha: o piso só desempata se for
    maior, nunca em igualdade.
    """
    relative_tolerance = legend_quantity * QUANTITY_DIVERGENCE_RELATIVE_TOLERANCE
    absolute_floor = QUANTITY_DIVERGENCE_ABSOLUTE_FLOOR
    if absolute_floor > relative_tolerance:
        return ToleranceBreakdown(
            relative_tolerance=relative_tolerance,
            absolute_floor=absolute_floor,
            tolerance=absolute_floor,
            tolerance_bound=ToleranceBound.ABSOLUTE_FLOOR,
        )
    return ToleranceBreakdown(
        relative_tolerance=relative_tolerance,
        absolute_floor=absolute_floor,
        tolerance=relative_tolerance,
        tolerance_bound=ToleranceBound.RELATIVE,
    )


def quantity_divergence_ratio(*, difference: Decimal, legend_quantity: Decimal) -> Decimal | None:
    """Razão entre a diferença e a legenda, em PERCENTUAL pronto para a tela — nunca fração.

    `None` quando `legend_quantity` é zero: a razão não existe, e dividir por zero não é o
    jeito de dizer isso. `LegendQuantityOrigin.quantity` já exige `gt=0` e por isso o
    modelo nunca chama esta função com zero — mas ela é pura e não deve depender de uma
    constraint que vive em outro model para não quebrar.

    Arredondada como QUANTIDADE (`croquito_valuation.rounding.quantity_round`:
    `ROUND_HALF_UP`, duas casas) — a mesma regra da planilha (dinheiro trunca, quantidade
    arredonda) — para que a tela só troque pontuação e junte "%", sem contar nada.
    """
    if legend_quantity == 0:
        return None
    return quantity_round((difference / legend_quantity) * 100)


def quantity_divergence_tolerance(legend_quantity: Decimal) -> Decimal:
    """`maior(1% da quantidade da legenda, 0,01)`. Constante nomeada, nunca número solto.

    Aritmética exata de `Decimal` de ponta a ponta: nada aqui arredonda, porque arredondar a
    tolerância deslocaria a borda que o aceite humano fixou. Lê `.tolerance` do breakdown —
    a mesma conta, nunca uma segunda derivação.
    """
    return quantity_divergence_tolerance_breakdown(legend_quantity).tolerance


def quantities_diverge(*, scene_quantity: Decimal, legend_quantity: Decimal) -> bool:
    """`True` quando os dois números se afastam MAIS que a tolerância.

    `>` e não `>=`: a diferença exatamente igual à tolerância é o último caso aceito.
    """
    difference = abs(scene_quantity - legend_quantity)
    return difference > quantity_divergence_tolerance(legend_quantity)


class SceneQuantityOrigin(ValuationContractModel):
    """De onde veio o número da CENA: identidade do elemento, precisão declarada e revisão.

    A precisão é a que a entidade declarou e nunca sobe, como em toda a travessia
    (ADR-0058 decisão 4): só `exact` e `derived` chegam até aqui, porque `approximate` não
    alimenta quantidade e portanto também não tem com o que divergir.
    """

    quantity: ExactDecimal = Field(gt=0)
    element_ref: str = Field(pattern=ELEMENT_REF_PATTERN)
    precision: Precision
    # O UUID da revisão aprovada que publicou o `quantitativos.csv`. É opcional porque o CSV
    # não o carrega: quem lê o pacote declara a revisão de onde ele saiu. Ausente, a issue
    # diz que a revisão não foi declarada — estado legível, e não uma revisão inventada.
    scene_revision_id: str | None = Field(default=None, min_length=1, max_length=64)

    @model_validator(mode="after")
    def validate_precision(self) -> SceneQuantityOrigin:
        if self.precision not in SCENE_ELIGIBLE_PRECISIONS:
            raise ValuationValidationError(
                "QUANTITY_DIVERGENCE_PRECISION_NOT_ELIGIBLE",
                "só entidade exact ou derived atravessa a fronteira; approximate não diverge",
                {"element_ref": self.element_ref, "precision": self.precision.value},
            )
        return self


class LegendQuantityOrigin(ValuationContractModel):
    """De onde veio o número da LEGENDA: quem leu, com que versão, e quando foi decidido.

    `read_by`/`read_at` só existem depois da decisão do orçamentista sobre o item: antes
    dela quem "leu" é o extrator, e carimbar um instante humano que ninguém praticou seria
    inventar a metade mais auditada da origem.
    """

    quantity: ExactDecimal = Field(gt=0)
    source: Literal["legend_extraction", "manual"]
    extractor: str = Field(min_length=1, max_length=80)
    extractor_version: str = Field(min_length=1, max_length=80)
    read_by: str | None = Field(default=None, min_length=1, max_length=120)
    read_at: datetime | None = None

    @field_validator("read_at")
    @classmethod
    def validate_timezone(cls, value: datetime | None) -> datetime | None:
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise ValuationValidationError(
                "QUANTITY_DIVERGENCE_TIMESTAMP_NAIVE",
                "origem da legenda exige data e hora com fuso horário",
                {"read_at": value.isoformat()},
            )
        return value


class DivergenceChoice(StrEnum):
    """Qual dos DOIS números passa a valer. Não há um terceiro valor, de propósito.

    "Nenhuma das duas" não é oferecida (ADR-0058, aceite de 2026-08-28): digitar uma
    terceira quantidade na resolução seria a redigitação que a feature existe para
    eliminar. Quem quiser um número que não é nem o da cena nem o da legenda corrige a
    origem — a legenda, pela decisão de takeoff; a cena, pelo traçado — e volta aqui.
    """

    SCENE = "scene"
    LEGEND = "legend"


class QuantityDivergenceResolution(ValuationContractModel):
    """O ato humano que escolhe um dos dois números, com autor e instante.

    Espelha `ReviewerDecision` na forma, não no significado: aqui não se confirma nem se
    rejeita um item — declara-se qual origem prevalece numa divergência já aberta.
    """

    choice: DivergenceChoice
    reviewer_id: str = Field(min_length=1, max_length=120)
    reviewer_role: Literal["orcamentista"]
    resolved_at: datetime
    note: str | None = Field(default=None, min_length=1, max_length=500)

    @field_validator("resolved_at")
    @classmethod
    def validate_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValuationValidationError(
                "QUANTITY_DIVERGENCE_TIMESTAMP_NAIVE",
                "resolução de divergência exige data e hora com fuso horário",
                {"resolved_at": value.isoformat()},
            )
        return value


class QuantityDivergence(ValuationContractModel):
    """A issue: os dois números, as duas origens, a diferença e a tolerância que ela furou.

    O modelo se recusa a existir dentro da tolerância (`QUANTITY_DIVERGENCE_WITHIN_TOLERANCE`)
    e a carregar uma diferença ou uma tolerância que não sejam as recomputadas dos próprios
    números. Assim a issue nunca é um rótulo colado por fora: ela é o resultado da conta,
    conferido na construção e a cada releitura do JSON gravado.

    `relative_tolerance`, `absolute_floor`, `tolerance_bound` e `legend_ratio` (F-047 T5b)
    são a mesma conta por extenso que a tela precisa mostrar (pacote de design aprovado,
    estado 06) — nascem OPCIONAIS e conferidos do mesmo jeito quando presentes, porque uma
    divergência gravada antes desta mudança precisa continuar legível sem eles.
    """

    scene: SceneQuantityOrigin
    legend: LegendQuantityOrigin
    difference: ExactDecimal = Field(gt=0)
    tolerance: ExactDecimal = Field(gt=0)
    relative_tolerance: ExactDecimal | None = Field(default=None, gt=0)
    absolute_floor: ExactDecimal | None = Field(default=None, gt=0)
    tolerance_bound: ToleranceBound | None = None
    legend_ratio: ExactDecimal | None = Field(default=None, gt=0)
    resolution: QuantityDivergenceResolution | None = None

    @model_validator(mode="after")
    def validate_arithmetic(self) -> QuantityDivergence:
        expected_difference = abs(self.scene.quantity - self.legend.quantity)
        if self.difference != expected_difference:
            raise ValuationValidationError(
                "QUANTITY_DIVERGENCE_DIFFERENCE_MISMATCH",
                "a diferença declarada não é a diferença entre os dois números",
                {"declared": str(self.difference), "recomputed": str(expected_difference)},
            )
        breakdown = quantity_divergence_tolerance_breakdown(self.legend.quantity)
        if self.tolerance != breakdown.tolerance:
            raise ValuationValidationError(
                "QUANTITY_DIVERGENCE_TOLERANCE_MISMATCH",
                "a tolerância declarada não é a tolerância nomeada da divergência",
                {"declared": str(self.tolerance), "recomputed": str(breakdown.tolerance)},
            )
        if self.difference <= self.tolerance:
            raise ValuationValidationError(
                "QUANTITY_DIVERGENCE_WITHIN_TOLERANCE",
                "diferença dentro da tolerância não é divergência; a issue não existe",
                {"difference": str(self.difference), "tolerance": str(self.tolerance)},
            )
        if (
            self.relative_tolerance is not None
            and self.relative_tolerance != breakdown.relative_tolerance
        ):
            raise ValuationValidationError(
                "QUANTITY_DIVERGENCE_RELATIVE_MISMATCH",
                "a parcela de 1% declarada não é a recomputada da legenda",
                {
                    "declared": str(self.relative_tolerance),
                    "recomputed": str(breakdown.relative_tolerance),
                },
            )
        if self.absolute_floor is not None and self.absolute_floor != breakdown.absolute_floor:
            raise ValuationValidationError(
                "QUANTITY_DIVERGENCE_FLOOR_MISMATCH",
                "o piso de unidade declarado não é o piso nomeado da divergência",
                {
                    "declared": str(self.absolute_floor),
                    "recomputed": str(breakdown.absolute_floor),
                },
            )
        if self.tolerance_bound is not None and self.tolerance_bound != breakdown.tolerance_bound:
            raise ValuationValidationError(
                "QUANTITY_DIVERGENCE_BOUND_MISMATCH",
                "a parcela que governou a tolerância declarada não é a recomputada",
                {
                    "declared": self.tolerance_bound.value,
                    "recomputed": breakdown.tolerance_bound.value,
                },
            )
        if self.legend_ratio is not None:
            expected_ratio = quantity_divergence_ratio(
                difference=self.difference, legend_quantity=self.legend.quantity
            )
            if self.legend_ratio != expected_ratio:
                raise ValuationValidationError(
                    "QUANTITY_DIVERGENCE_RATIO_MISMATCH",
                    "a razão declarada não é a recomputada entre a diferença e a legenda",
                    {"declared": str(self.legend_ratio), "recomputed": str(expected_ratio)},
                )
        return self

    @property
    def is_open(self) -> bool:
        """`True` enquanto ninguém escolheu. É o estado que trava o fechamento do pacote."""
        return self.resolution is None

    @property
    def chosen_quantity(self) -> Decimal | None:
        """A quantidade que passou a valer, ou `None` enquanto a divergência está aberta."""
        if self.resolution is None:
            return None
        if self.resolution.choice is DivergenceChoice.SCENE:
            return self.scene.quantity
        return self.legend.quantity

    @property
    def superseded_quantity(self) -> Decimal | None:
        """O número PRETERIDO, que continua gravado e recuperável (ADR-0058 decisão 6).

        Ele não é apagado na resolução: quem auditar a medição meses depois precisa ver o
        que foi descartado tanto quanto o que valeu.
        """
        if self.resolution is None:
            return None
        if self.resolution.choice is DivergenceChoice.SCENE:
            return self.legend.quantity
        return self.scene.quantity
