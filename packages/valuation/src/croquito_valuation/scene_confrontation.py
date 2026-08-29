"""O confronto do pacote inteiro com a cena aprovada (F-047 T4b).

A T4 abriu a travessia de UM item (`QuantitySource.feed`) e a T5, o confronto de UM item
(`QuantitySource.record_divergence`). Falta o ato que a jornada executa de verdade: passar
o `quantitativos.csv` da cena aprovada pelo pacote de takeoff **inteiro**, item a item, e
dizer o que aconteceu com cada um.

Este módulo é só isso — o laço e o relatório. Ele não decide tolerância, não lê CSV, não
sabe o que é `element_ref`: quem faz as três coisas é o `quantity_source.py`, e trocar
qualquer regra dele muda este laço sem que uma linha aqui precise ser reescrita. É também
a razão de o módulo ser PURO: a rota que o chama já terá lido o pacote do banco e o CSV do
object store, e o que sobra — decidir por item entre alimentar, divergir e não fazer nada —
tem de ser exercitável sem subir aplicação nenhuma.

Duas regras atravessam o laço:

- **Nada é palpite, nem a omissão.** Todo item volta no relatório, inclusive o que não
  mudou, com o motivo nomeado de não ter mudado. "Não apareceu na resposta" nunca é como o
  produto diz que a cena não tinha aquele número.
- **O confronto é repetível.** Rodá-lo de novo sobre o mesmo estado não duplica divergência
  (item que já tem uma é pulado, respeitando a recusa `QUANTITY_DIVERGENCE_ALREADY_RECORDED`
  da T5), não realimenta o que já veio da cena e não devolve pacote novo quando nada mudou:
  `changed` é `False` e quem chama não grava revisão nenhuma.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import Field, model_validator

from croquito_core.models import ELEMENT_REF_PATTERN, Precision
from croquito_valuation.errors import ValuationValidationError
from croquito_valuation.models import (
    TAKEOFF_ITEM_ID_PATTERN,
    ExactDecimal,
    ValuationContractModel,
)
from croquito_valuation.quantity_source import QuantitySource, QuantityUnresolvedReason
from croquito_valuation.takeoff import TakeoffItem, TakeoffItemStatus, TakeoffPacket


class SceneConfrontationOutcome(StrEnum):
    """O que o confronto fez com um item de takeoff. Três desfechos, e só três."""

    FED = "fed"
    """O item não tinha quantidade e recebeu a da cena, com a precisão declarada lá."""

    DIVERGENCE_RECORDED = "divergence_recorded"
    """O item já trazia a quantidade da legenda e os dois números discordam além da
    tolerância: a divergência foi gravada e ninguém escolheu por ninguém."""

    UNCHANGED = "unchanged"
    """Nada mudou neste item, e `reason` diz por quê — sempre."""


class SceneConfrontationSkipReason(StrEnum):
    """Por que o item ficou intacto, quando a cena até tinha quantidade para ele.

    Complementa `QuantityUnresolvedReason`, que nomeia o outro conjunto de motivos — os da
    cena não ter número para o item. Os valores dos dois enums são disjuntos de propósito:
    eles viajam no mesmo campo do relatório, e um valor ambíguo faria a tela mostrar o
    motivo errado.
    """

    ITEM_REJECTED = "item_rejected"
    """Linha que o orçamentista rejeitou. Ela não vira boletim, então confrontá-la
    produziria uma divergência que nada destrava e ninguém precisa resolver."""

    ALREADY_FED_FROM_SCENE = "already_fed_from_scene"
    """A quantidade do item JÁ nasceu da cena: não há legenda para confrontar, e realimentar
    seria reescrever o mesmo número por cima de si mesmo."""

    DIVERGENCE_ALREADY_RECORDED = "divergence_already_recorded"
    """O item já tem divergência gravada, aberta ou resolvida. Regravar apagaria o número
    que alguém está olhando na tela, ou a decisão que já foi tomada sobre ele (T5)."""

    WITHIN_TOLERANCE = "within_tolerance"
    """Os dois números existem e concordam dentro da tolerância nomeada. Concordar não é
    evento: nada é gravado, e o relatório registra que o confronto aconteceu."""


class SceneItemOutcome(ValuationContractModel):
    """O que o confronto fez com um item, e por quê. Uma linha por item do pacote."""

    item_id: str = Field(pattern=TAKEOFF_ITEM_ID_PATTERN)
    element_ref: str | None = Field(default=None, pattern=ELEMENT_REF_PATTERN)
    outcome: SceneConfrontationOutcome
    reason: SceneConfrontationSkipReason | QuantityUnresolvedReason | None = None
    scene_quantity: ExactDecimal | None = Field(default=None, gt=0)
    """A quantidade que a cena ofereceu, presente sempre que ela existiu — inclusive quando
    o desfecho foi não usá-la (`WITHIN_TOLERANCE`), que é justamente onde ver o número da
    cena ao lado do da legenda explica a decisão do sistema."""
    scene_precision: Precision | None = None

    @model_validator(mode="after")
    def validate_outcome(self) -> SceneItemOutcome:
        """Desfecho e motivo se excluem: mudou não tem motivo, não mudou sempre tem."""
        if self.outcome is SceneConfrontationOutcome.UNCHANGED:
            if self.reason is None:
                raise ValuationValidationError(
                    "SCENE_OUTCOME_WITHOUT_REASON",
                    "item que não mudou exige o motivo nomeado",
                    {"item_id": self.item_id},
                )
            return self
        if self.reason is not None:
            raise ValuationValidationError(
                "SCENE_OUTCOME_INCONSISTENT",
                "item alimentado ou divergido não carrega motivo de recusa",
                {"item_id": self.item_id},
            )
        if self.scene_quantity is None or self.scene_precision is None or self.element_ref is None:
            raise ValuationValidationError(
                "SCENE_OUTCOME_INCOMPLETE",
                "item alimentado ou divergido exige identidade, quantidade e precisão da cena",
                {"item_id": self.item_id},
            )
        return self


class SceneConfrontation(ValuationContractModel):
    """O pacote depois do confronto e o relatório item a item.

    `packet` é o pacote NOVO quando algo mudou e o mesmo de entrada quando nada mudou —
    `changed` discrimina, e é por ele que a rota decide se grava revisão. Devolver sempre um
    pacote reconstruído faria toda releitura do CSV avançar a cadeia da rodada sem que ato
    nenhum tivesse acontecido.
    """

    packet: TakeoffPacket
    outcomes: list[SceneItemOutcome] = Field(min_length=1)

    @property
    def changed(self) -> bool:
        """`True` quando ao menos um item foi alimentado ou ganhou divergência."""
        return any(
            outcome.outcome is not SceneConfrontationOutcome.UNCHANGED for outcome in self.outcomes
        )

    def count_of(self, outcome: SceneConfrontationOutcome) -> int:
        """Quantos itens tiveram aquele desfecho."""
        return sum(1 for entry in self.outcomes if entry.outcome is outcome)


def confront_scene_quantities(packet: TakeoffPacket, source: QuantitySource) -> SceneConfrontation:
    """Passa a cena aprovada pelo pacote inteiro e devolve o pacote resultante e o relatório.

    A ordem das perguntas por item é a ordem em que elas de fato impedem o confronto:

    1. **divergência já gravada** — a T5 recusa regravar, e aqui a recusa vira "pulei", não
       exceção: um item já confrontado não pode impedir que os outros o sejam;
    2. **item rejeitado** — linha descartada não vira boletim nem trava nada;
    3. **a cena resolve?** — `QuantitySource.resolve` responde com a quantidade ou com o
       motivo nomeado (sem identidade num dos lados, precisão `approximate`/`unresolved`,
       unidade que a cena não produz, grandeza ausente);
    4. **o item já tem número?** — não tem, alimenta; tem e veio da cena, não há o que
       confrontar; tem e veio da legenda, compara com a tolerância nomeada.

    Nunca levanta por regra de negócio deste laço: recusa é linha do relatório. O que ainda
    pode levantar é a invariante do domínio (alimentar item já revisado, por exemplo), e ela
    levanta de propósito — é o `quantity_source` quem manda, e o desfecho é fechado.
    """
    outcomes: list[SceneItemOutcome] = []
    items: list[TakeoffItem] = []
    for item in packet.items:
        updated, outcome = _confront_item(item, source)
        items.append(updated)
        outcomes.append(outcome)

    changed = any(
        outcome.outcome is not SceneConfrontationOutcome.UNCHANGED for outcome in outcomes
    )
    return SceneConfrontation(
        packet=(
            TakeoffPacket.model_validate({**packet.model_dump(), "items": items})
            if changed
            else packet
        ),
        outcomes=outcomes,
    )


def _confront_item(
    item: TakeoffItem, source: QuantitySource
) -> tuple[TakeoffItem, SceneItemOutcome]:
    """O item depois do confronto (o mesmo, quando nada mudou) e a linha do relatório."""

    def unchanged(
        reason: SceneConfrontationSkipReason | QuantityUnresolvedReason,
        *,
        scene_quantity: ExactDecimal | None = None,
        scene_precision: Precision | None = None,
    ) -> tuple[TakeoffItem, SceneItemOutcome]:
        return item, SceneItemOutcome(
            item_id=item.id,
            element_ref=item.element_ref,
            outcome=SceneConfrontationOutcome.UNCHANGED,
            reason=reason,
            scene_quantity=scene_quantity,
            scene_precision=scene_precision,
        )

    if item.scene_divergence is not None:
        return unchanged(SceneConfrontationSkipReason.DIVERGENCE_ALREADY_RECORDED)
    if item.status is TakeoffItemStatus.REJECTED:
        return unchanged(SceneConfrontationSkipReason.ITEM_REJECTED)

    resolution = source.resolve(item)
    if not resolution.resolved:
        # `validate_outcome` do `QuantityResolution` garante o motivo presente aqui.
        assert resolution.reason is not None
        return unchanged(resolution.reason)
    assert resolution.quantity is not None
    assert resolution.precision is not None

    def changed(
        updated: TakeoffItem, outcome: SceneConfrontationOutcome
    ) -> tuple[TakeoffItem, SceneItemOutcome]:
        return updated, SceneItemOutcome(
            item_id=item.id,
            element_ref=item.element_ref,
            outcome=outcome,
            scene_quantity=resolution.quantity,
            scene_precision=resolution.precision,
        )

    if item.quantity is None:
        return changed(source.feed(item), SceneConfrontationOutcome.FED)
    if item.source == "scene_graph":
        return unchanged(
            SceneConfrontationSkipReason.ALREADY_FED_FROM_SCENE,
            scene_quantity=resolution.quantity,
            scene_precision=resolution.precision,
        )
    divergent = source.record_divergence(item)
    if divergent.scene_divergence is None:
        return unchanged(
            SceneConfrontationSkipReason.WITHIN_TOLERANCE,
            scene_quantity=resolution.quantity,
            scene_precision=resolution.precision,
        )
    return changed(divergent, SceneConfrontationOutcome.DIVERGENCE_RECORDED)
