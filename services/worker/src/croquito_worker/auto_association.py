"""Decisão de ator-máquina sobre leitura de cota, atrás de dupla chave local (ADR-0041).

O invariante do pipeline continua fail-closed: leitura sem decisão completa não vira
geometria. O que este módulo acrescenta é *quem* pode ter autoria de uma decisão — e só
quando duas chaves explícitas estão presentes ao mesmo tempo:

1. `CROQUITO_AUTO_ASSOCIATION_ENABLED=true` — leitura estrita, e **ausente é desligado**.
   É o oposto deliberado do braço OpenAI (`CROQUITO_OPENAI_ARM_ENABLED`, ligado quando
   ausente): lá desligar tira uma testemunha da revisão humana, aqui ligar tira a pessoa
   do circuito. Ligar precisa ser ato declarado.
2. `CROQUITO_AUTO_ASSOCIATION_THRESHOLD` — o corte, **sem default no código**. O número
   de corte é escolhido por uma pessoa a partir do relatório de calibração (F-029, gate
   humano 3); flag ligada sem threshold é erro de configuração que impede o modo, nunca
   um valor inventado.

Um corte só, e **dois tiers separados pelo custo do erro** (ADR-0041 D5, revisto pelo
ADR-0044 D1):

- **`cota`** — o tier de dupla testemunha: `reading_confidence` E
  `association_confidence` do candidato escolhido superam o corte. Nenhuma das duas
  sozinha basta, porque associar errado põe a cota certa no segmento errado e nada a
  jusante percebe.
- **`anotacao`** — leitura SEM papel de geometria de planta (elevação `h=…`, ou o sinal
  `note` do provider da F-021): entra confirmada **sem elemento associado**, espelhando o
  ato humano de "anotação da folha" (ADR-0044, D1a). Nenhum eixo do corte é exigido:
  testemunha única basta porque, sem vínculo, o erro não alcança geometria nenhuma.

O tier de anotação NÃO grava associação, e é isso que o torna barato. Associação
explícita é restrição métrica no traçado — `height` puxa o eixo Y —, e a regra humana
recusa associação em anotação com 422. O candidato mais provável viaja como
**observação** (na `note` e na auditoria), para instruir a fixação do texto no aceite do
traçado; nunca como vínculo. Leitura sem candidato nenhum entra do mesmo jeito: o texto
vale sem elemento até o aceite.

Cota de planta nunca entra pelo tier de anotação, com qualquer confiança (ADR-0044, D2),
e o tier não reclassifica nada: `kind`, valor, unidade e texto entram como o extrator
leu. O que muda entre os tiers é o critério de elegibilidade, nunca o conteúdo.

O sistema só confirma, nunca rejeita, nunca retifica e nunca redecide: auto-decisão só
nasce sobre leitura sem decisão alguma (ADR-0041, D3 e D4). Corrigir uma auto-decisão é
o mesmo ato humano de sempre, pelo caminho de retificação do ADR-0022.
"""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Final, Literal

from croquito_core.models import MeasurementKind
from croquito_worker.association import AssociationCandidate, AssociationSet
from croquito_worker.association_confidence import (
    CONFIDENCE_SCORE_VERSION,
    ConfidenceThreshold,
    confidence_chains,
    reading_confidence,
    shadow_decisions,
)
from croquito_worker.review import DimensionReading, HumanDecision, ReadingStatus, ReviewPacket

AUTO_ASSOCIATION_ENABLED_ENV: Final = "CROQUITO_AUTO_ASSOCIATION_ENABLED"
AUTO_ASSOCIATION_THRESHOLD_ENV: Final = "CROQUITO_AUTO_ASSOCIATION_THRESHOLD"

AUTO_DECISION_CREATED_BY: Final = "auto-association"
"""Rótulo do ato na proveniência de escrita; a identidade versionada vai na decisão."""

AutoDecisionTier = Literal["cota", "anotacao"]
"""Por qual regra a máquina decidiu — dupla testemunha, ou custo do erro (ADR-0044)."""

PLAN_DIMENSION_KINDS: Final = frozenset(
    {
        MeasurementKind.LENGTH,
        MeasurementKind.WIDTH,
        MeasurementKind.RADIUS,
        MeasurementKind.DIAMETER,
        MeasurementKind.ANGLE,
        MeasurementKind.AREA,
    }
)
"""Kinds que descrevem geometria de PLANTA e nunca entram pelo tier de anotação.

Lista literal do ADR-0044 (D2), que é o complemento exato de `height` no enum de hoje.
Escrita por extenso, e não como "tudo menos height", para que um `MeasurementKind` novo
nasça FORA do tier de anotação até alguém decidir o contrário — o default seguro é o
que exige duas testemunhas.
"""


def _has_plan_geometry_role(reading: DimensionReading) -> bool:
    """A leitura manda na geometria de planta quando confirmada?

    O sinal `note` do provider (F-021) responde primeiro, e não por conveniência: quando
    o modelo lê a linha como recado completo da folha, `provider_review` grava
    `annotation_suggested=True` **e neutraliza o `kind` para `length`** de propósito
    (`provider_review.py`, "kind='note' completo é recado da folha, não cota"). Ler a
    lista de kinds antes do sinal transformaria a segunda metade do ADR-0044 D1 ("ou
    sinal note do provider") em código morto: toda anotação chega marcada como `length`.

    Sem o sinal, quem responde é o `kind` como o extrator o classificou.
    """
    if reading.annotation_suggested:
        return False
    return reading.kind in PLAN_DIMENSION_KINDS


def system_reviewer_id() -> str:
    """Identidade do ator-máquina, carimbada com a versão do score que a produziu."""
    return f"system:auto-association@{CONFIDENCE_SCORE_VERSION}"


class AutoAssociationConfigError(RuntimeError):
    """A configuração do modo automático está incompleta ou inválida; nada foi decidido."""


@dataclass(frozen=True, slots=True)
class AutoAssociationMode:
    """O modo automático ligado, com o corte que uma pessoa escolheu."""

    threshold: float

    @property
    def confidence_threshold(self) -> ConfidenceThreshold:
        """O mesmo corte nos dois eixos — a grade do shadow fala essa língua."""
        return ConfidenceThreshold(
            reading_threshold=self.threshold, association_threshold=self.threshold
        )


OBSERVATION_CUT: Final = ConfidenceThreshold(reading_threshold=0.0, association_threshold=0.0)
"""Corte que não decide nada: serve só para colher o candidato mais provável de cada leitura.

Não é um segundo threshold — **o corte operacional continua sendo um só** (ADR-0041, D5).
Zerado nos dois eixos, ele devolve, para toda leitura que tenha ao menos um candidato, a
MESMA escolha que o shadow log registraria: mesmo argmax, mesmo desempate por
`proposal_id`. É assim que o "elemento provável" citado numa anotação automática é o
mesmo que a calibração vê, sem uma segunda implementação de ranking para divergir.
"""


def _flag_enabled(raw: str | None) -> bool:
    """Leitura estrita do interruptor: só `true`/`false`, e ausente é desligado.

    Um `"0"`, um `"no"` ou um vazio interpretado por conta própria decidiria em silêncio
    se a revisão terá ou não toque humano. Valor estranho é erro, não é um modo.
    """
    if raw is None:
        return False
    normalized = raw.strip().lower()
    if normalized == "true":
        return True
    if normalized == "false":
        return False
    raise AutoAssociationConfigError(
        f"{AUTO_ASSOCIATION_ENABLED_ENV} aceita apenas 'true' ou 'false': {raw!r}"
    )


def _threshold(raw: str | None) -> float:
    if raw is None or not raw.strip():
        raise AutoAssociationConfigError(
            f"{AUTO_ASSOCIATION_ENABLED_ENV}=true exige {AUTO_ASSOCIATION_THRESHOLD_ENV} "
            "explícito entre 0 e 1; o corte é escolhido por uma pessoa a partir do "
            "relatório de calibração, nunca por um default do código."
        )
    try:
        value = float(raw.strip())
    except ValueError as error:
        raise AutoAssociationConfigError(
            f"{AUTO_ASSOCIATION_THRESHOLD_ENV} não é um número entre 0 e 1: {raw!r}"
        ) from error
    if not 0.0 <= value <= 1.0:
        raise AutoAssociationConfigError(
            f"{AUTO_ASSOCIATION_THRESHOLD_ENV} precisa estar entre 0 e 1: {raw!r}"
        )
    return value


def auto_association_mode(
    environment: dict[str, str] | None = None,
) -> AutoAssociationMode | None:
    """Lê a dupla chave; `None` quando o modo está desligado, erro quando está incoerente.

    Recusar é o comportamento correto para flag ligada sem corte: o modo não ativa, e o
    chamador não recebe um número inventado. Desligado não levanta nada — é o padrão.
    """
    source = os.environ if environment is None else environment
    if not _flag_enabled(source.get(AUTO_ASSOCIATION_ENABLED_ENV)):
        return None
    return AutoAssociationMode(threshold=_threshold(source.get(AUTO_ASSOCIATION_THRESHOLD_ENV)))


@dataclass(frozen=True, slots=True)
class AutoDecision:
    """Uma leitura que entrou sem toque humano, com tudo que a auditoria precisa citar.

    `reading_confidence` é gravada nos DOIS tiers, inclusive onde ela não decidiu nada:
    no tier de anotação ela é observação — o dado que a próxima calibração precisa para
    responder "quanto teria custado exigir a segunda testemunha aqui?".
    """

    reading_id: str
    decision_id: str
    reading_confidence: float
    threshold: float
    score_version: str
    # O vínculo GRAVADO em `selected_associations`. `None` no tier de anotação, que
    # confirma sem elemento associado — e é a ausência desse vínculo que faz a anotação
    # não virar restrição em solve nenhum.
    proposal_id: str | None
    # OBSERVAÇÃO do tier de anotação: o candidato que teria vencido, para instruir a
    # fixação do texto no aceite do traçado. Nunca é vínculo, e `None` quando a leitura
    # não tem candidato nenhum — ela entra assim mesmo.
    probable_proposal_id: str | None = None
    # Confiança do candidato citado acima, seja ele vínculo (tier de cota) ou provável
    # (tier de anotação). `None` só quando não há candidato algum.
    association_confidence: float | None = None
    # Aditivo (ADR-0044): registro gravado antes deste campo é do tier `cota`, o único
    # que existia. Quem lê um shadow antigo assume esse default explicitamente.
    tier: AutoDecisionTier = "cota"

    def as_json(self) -> dict[str, Any]:
        return {
            "reading_id": self.reading_id,
            "proposal_id": self.proposal_id,
            "probable_proposal_id": self.probable_proposal_id,
            "decision_id": self.decision_id,
            "reading_confidence": self.reading_confidence,
            "association_confidence": self.association_confidence,
            "threshold": self.threshold,
            "score_version": self.score_version,
            "tier": self.tier,
        }


@dataclass(frozen=True, slots=True)
class AutoAssociationOutcome:
    """O pacote e as associações depois do ato da máquina — entrada nunca é mutada."""

    packet: ReviewPacket
    selected_associations: dict[str, str]
    decisions: tuple[AutoDecision, ...]


AUTO_DECISION_SAFETY_NOTE: Final = (
    "Cotas auto-decididas por confiança calibrada, com proveniência de ator-máquina; "
    "cada uma delas é retificável pelo caminho humano de correção declarada."
)
"""Nota do pacote. Cobre os dois tiers e não é reescrita pelo tier de anotação: ela já
está gravada em revisões reais, e o que separa os tiers viaja por decisão (`auto_tier`),
não por uma frase no pacote."""


def _decision_id(
    *,
    reading_id: str,
    decided_at: datetime,
    proposal_id: str | None,
    reading_confidence: float,
    association_confidence: float | None,
    threshold: float,
) -> str:
    """Identidade da decisão derivada do ato inteiro, como no caminho humano.

    `proposal_id` nulo é o que a anotação automática de fato produziu — confirmação sem
    elemento associado —, e não um campo faltando. Para o tier de cota o conteúdo
    canônico segue idêntico ao da T4, byte a byte.
    """
    canonical = json.dumps(
        {
            "actor": "system",
            "reading_id": reading_id,
            "reviewer_id": system_reviewer_id(),
            "decided_at": decided_at.isoformat(),
            "proposal_id": proposal_id,
            "reading_confidence": reading_confidence,
            "association_confidence": association_confidence,
            "threshold": threshold,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return f"hd_{hashlib.sha256(canonical.encode()).hexdigest()[:16]}"


def _probable_element(decision: AutoDecision) -> str:
    """A dica de elemento que o revisor lê na justificativa — observação, nunca vínculo."""
    if decision.probable_proposal_id is None:
        return (
            "Sem candidato de elemento: o texto vale sozinho até alguém prendê-lo no "
            "aceite do traçado."
        )
    confidence = decision.association_confidence
    measured = "" if confidence is None else f", confiança de associação {confidence:g}"
    return (
        f"Elemento provável: {decision.probable_proposal_id}{measured} — observação para "
        "o traçado, nenhum vínculo foi gravado."
    )


def _note(decision: AutoDecision) -> str:
    """A justificativa registra o tier, o corte vigente e o que foi (ou não) exigido.

    O texto do tier `cota` é o mesmo desde a T4, palavra por palavra: ele já está gravado
    em revisões reais, e reescrevê-lo faria a mesma decisão parecer outra na comparação
    entre rodadas. O tier viaja estruturado em `auto_tier`; a `note` do tier de anotação
    nasce agora e diz o que ele NÃO fez — nem exigiu o corte, nem prendeu elemento.
    """
    if decision.tier == "anotacao":
        return (
            f"Anotação automática (corte vigente {decision.threshold:g}, "
            f"score {decision.score_version}): leitura sem papel de geometria de planta, "
            "confirmada SEM elemento associado, como a anotação da folha declarada por "
            f"uma pessoa. Confiança de leitura {decision.reading_confidence:g} "
            f"registrada e não exigida. {_probable_element(decision)}"
        )
    return (
        f"Decisão automática de associação (corte {decision.threshold:g}, "
        f"score {decision.score_version}): confiança de leitura "
        f"{decision.reading_confidence:g} e de associação "
        f"{decision.association_confidence:g}, ambas acima do corte."
    )


def _decidable(packet: ReviewPacket) -> set[str]:
    """Leituras elegíveis: sem decisão alguma e com valor numérico.

    Sem valor não há o que confirmar — `DimensionReading` recusa leitura confirmada sem
    medida —, e inventar um é exatamente o que o pipeline existe para impedir.
    """
    return {
        reading.id
        for reading in packet.readings
        if reading.decision is None
        and reading.status not in {ReadingStatus.CONFIRMED, ReadingStatus.REJECTED}
        and reading.value_si is not None
    }


def apply_auto_association(
    packet: ReviewPacket,
    associations: AssociationSet,
    *,
    mode: AutoAssociationMode,
    declared_chains: Sequence[dict[str, Any]] = (),
    plan_geometry_reading_ids: frozenset[str] = frozenset(),
    decided_at: datetime | None = None,
) -> AutoAssociationOutcome:
    """Confirma, com autoria de máquina, o que cada tier permite — nesta ordem.

    Primeiro o tier `cota`, de dupla testemunha (ADR-0041): a leitura precisa dos dois
    eixos acima do corte e recebe a associação explícita que o solver exige. Depois o tier
    `anotacao` (ADR-0044, D1a), só sobre o que sobrou e só para leitura sem papel de
    geometria de planta: ali nenhum eixo do corte é exigido e NENHUMA associação é
    gravada — a leitura entra confirmada e sem elemento, que é exatamente a forma do ato
    humano de "anotação da folha". A ordem importa e é deliberada: quem passa nos dois
    eixos entra pela regra mais forte, e o tier registrado diz por qual regra ela entrou.

    O candidato mais provável do tier de anotação vem do mesmo `shadow_decisions` que
    registra o tier 1 (`OBSERVATION_CUT`): mesmo argmax, mesmo desempate por
    `proposal_id`. Ele viaja como observação na `note` e na auditoria, e leitura sem
    candidato nenhum entra do mesmo jeito — o texto vale sem elemento até o aceite.

    `plan_geometry_reading_ids` são leituras que a própria revisão declara como geometria
    de planta por outro caminho que não o `kind` — hoje, as citadas pelo pedido do solver
    retangular como lado ou círculo do elemento. Elas ficam fora do tier de anotação seja
    qual for o `kind` (ADR-0044, D1a e D2).

    Leitura já decidida — por gente ou por uma execução anterior — nunca é tocada:
    `READING_ALREADY_DECIDED` cobre o sistema como cobre pessoa (ADR-0041, D4). O carimbo
    de tempo é do servidor.
    """
    decidable = _decidable(packet)
    if not decidable:
        return AutoAssociationOutcome(packet=packet, selected_associations={}, decisions=())

    chains = confidence_chains(packet, declared_chains)
    dimension_cut, observation_cut = shadow_decisions(
        packet,
        associations,
        chains,
        (mode.confidence_threshold, OBSERVATION_CUT),
    )
    candidates_by_pair: dict[tuple[str, str], AssociationCandidate] = {
        (candidate.reading_id, candidate.proposal_id): candidate
        for candidate in associations.candidates
    }
    probable_by_reading = {choice.reading_id: choice for choice in observation_cut.auto_choices}
    stamped_at = decided_at or datetime.now(UTC)

    decisions: list[AutoDecision] = []
    selected_associations: dict[str, str] = {}
    updated_readings: list[dict[str, Any]] = []
    decided_by_reading: dict[str, HumanDecision] = {}

    def _register(decision: AutoDecision) -> None:
        decided_by_reading[decision.reading_id] = HumanDecision(
            decision_id=decision.decision_id,
            action="confirm",
            actor="system",
            auto_tier=decision.tier,
            reviewer_id=system_reviewer_id(),
            decided_at=stamped_at,
            note=_note(decision),
        )
        decisions.append(decision)

    # Tier `cota`: dupla testemunha, com o vínculo que o solver exige.
    for choice in dimension_cut.auto_choices:
        if choice.reading_id not in decidable:
            continue
        if (choice.reading_id, choice.proposal_id) not in candidates_by_pair:
            continue
        _register(
            AutoDecision(
                reading_id=choice.reading_id,
                proposal_id=choice.proposal_id,
                decision_id=_decision_id(
                    reading_id=choice.reading_id,
                    decided_at=stamped_at,
                    proposal_id=choice.proposal_id,
                    reading_confidence=choice.reading_confidence,
                    association_confidence=choice.association_confidence,
                    threshold=mode.threshold,
                ),
                reading_confidence=choice.reading_confidence,
                association_confidence=choice.association_confidence,
                threshold=mode.threshold,
                score_version=CONFIDENCE_SCORE_VERSION,
                tier="cota",
            )
        )
        selected_associations[choice.reading_id] = choice.proposal_id

    # Tier `anotacao`: sem corte e sem vínculo. Percorre as LEITURAS, não os candidatos,
    # porque a anotação sem candidato nenhum também entra.
    for reading in packet.readings:
        if reading.id not in decidable or reading.id in decided_by_reading:
            continue
        if reading.id in plan_geometry_reading_ids or _has_plan_geometry_role(reading):
            continue
        probable = probable_by_reading.get(reading.id)
        # A leitura sem candidato nenhum não aparece no corte de observação, e é por isso
        # que a confiança de leitura é calculada aqui: ela existe para toda leitura, com
        # ou sem elemento provável, e é o dado que a próxima calibração vai querer.
        confidence = reading_confidence(reading, chains)
        probable_confidence = None if probable is None else probable.association_confidence
        _register(
            AutoDecision(
                reading_id=reading.id,
                proposal_id=None,
                probable_proposal_id=None if probable is None else probable.proposal_id,
                decision_id=_decision_id(
                    reading_id=reading.id,
                    decided_at=stamped_at,
                    # A identidade cita o que o ato produziu: nenhum vínculo.
                    proposal_id=None,
                    reading_confidence=confidence,
                    association_confidence=probable_confidence,
                    threshold=mode.threshold,
                ),
                reading_confidence=confidence,
                association_confidence=probable_confidence,
                threshold=mode.threshold,
                score_version=CONFIDENCE_SCORE_VERSION,
                tier="anotacao",
            )
        )

    if not decisions:
        return AutoAssociationOutcome(packet=packet, selected_associations={}, decisions=())

    for reading in packet.readings:
        decision_for_reading = decided_by_reading.get(reading.id)
        if decision_for_reading is None:
            updated_readings.append(reading.model_dump())
            continue
        # Só o estado da revisão muda: valor, unidade, tipo e alvo são o que o extrator
        # leu. Máquina confirma o que está escrito; corrigir o escrito é ato humano.
        updated_readings.append(
            {
                **reading.model_dump(),
                "status": ReadingStatus.CONFIRMED,
                "decision": decision_for_reading.model_dump(),
            }
        )

    safety_notes = list(packet.safety_notes)
    if AUTO_DECISION_SAFETY_NOTE not in safety_notes:
        safety_notes.append(AUTO_DECISION_SAFETY_NOTE)
    decided_packet = ReviewPacket.model_validate(
        {**packet.model_dump(), "readings": updated_readings, "safety_notes": safety_notes}
    )
    return AutoAssociationOutcome(
        packet=decided_packet,
        selected_associations=selected_associations,
        decisions=tuple(decisions),
    )
