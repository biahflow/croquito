"""Confianças determinísticas de leitura e associação — nenhuma decisão, nenhum efeito colateral.

Duas perguntas diferentes, duas confianças nomeadas, nunca fundidas num número só:

- `reading_confidence` — "li 7,35 corretamente?" — soma sinais sobre a leitura em si
  (corroboração de OCR, participação em cadeia que fecha, presença de valor numérico).
- `association_confidence` — "sei a qual segmento 7,35 pertence?" — soma sinais sobre o
  candidato de associação (proximidade, qualidade visual, orientação, ambiguidade frente
  ao segundo candidato e, quando existir, o resíduo do solver).

Ambas são somas ponderadas de sinais tipados em [0, 1], com pesos como constantes
nomeadas. Um sinal ausente nunca é tratado como reprovação: contribui de forma neutra
(0.5 do próprio peso), nunca como requisito. Nada aqui decide, persiste ou associa —
`shadow_decisions` só relata o que UM CORTE hipotético teria auto-decidido, para
calibração futura.

A grade de cortes e a montagem do registro gravável (`confidence_shadow_json`) moram
aqui, ao lado do score, e não no serviço que grava: os dois caminhos de escrita de
revisão — o da API e o do worker, que faz nascer a revisão 1 — precisam produzir
exatamente o mesmo registro, e duas cópias da mesma grade divergiriam em silêncio,
corrompendo a calibração sem nenhum erro visível. Decidir de fato com estas confianças é
assunto de `auto_association`, nunca deste módulo.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Final

from croquito_worker.dimension_closure import (
    ChainVerificationError,
    DimensionChain,
    suggest_chains,
    verify_chain,
)
from croquito_worker.rectangle_solver import SolverResidual
from croquito_worker.review import DimensionReading, ReviewPacket

if TYPE_CHECKING:
    # Somente para tipagem: `association.py` importa este módulo em tempo de execução
    # para pontuar candidatos recém-construídos, então o import inverso aqui precisa
    # ficar restrito ao type checking para não fechar um ciclo de import.
    from croquito_worker.association import AssociationCandidate, AssociationSet

CONFIDENCE_SCORE_VERSION: Final = "1.0.0"
"""Versão dos pesos e dos sinais deste módulo — carimbada em todo shadow gravado.

Os pesos abaixo VÃO mudar: recalibrá-los é o propósito das fatias 2 e 3 da F-029. Sem
este carimbo, shadows de versões diferentes conviveriam no banco indistinguíveis, e o
relatório de calibração somaria maçã com laranja sem nenhum aviso. Quem alterar peso,
sinal ou fórmula deste módulo sobe esta versão no mesmo trabalho.
"""

READING_OCR_WEIGHT = 0.4
"""Corroboração de OCR é o sinal mais forte sobre a leitura: dois braços leram o mesmo texto."""

READING_CHAIN_WEIGHT = 0.3
"""Participar de uma cadeia que fecha (`dimension_closure`) corrobora o valor lido."""

READING_VALUE_WEIGHT = 0.3
"""Ter valor numérico coerente extraído é pré-condição para qualquer confiança de leitura."""

ASSOCIATION_PROXIMITY_WEIGHT = 0.3
"""Proximidade em pixels ao segmento candidato, já calculada por `associate_readings`."""

ASSOCIATION_VISUAL_QUALITY_WEIGHT = 0.2
"""Qualidade visual do traço CV (`VisionProposal.quality_score`)."""

ASSOCIATION_ORIENTATION_WEIGHT = 0.2
"""Alinhamento entre o eixo dominante do texto da cota e a direção do segmento."""

ASSOCIATION_MARGIN_WEIGHT = 0.2
"""Margem sobre o segundo candidato: quanto mais ambíguo, menor a confiança."""

ASSOCIATION_SOLVER_WEIGHT = 0.1
"""Resíduo do solver para a leitura, quando um diagnóstico de solve já existir."""


def _clamp01(value: float) -> float:
    return min(1.0, max(0.0, value))


def _ocr_component(ocr_corroborated: bool | None) -> float:
    if ocr_corroborated is None:
        # Braço de OCR ausente ou que falhou: sem informação, nunca reprovação.
        return 0.5
    return 1.0 if ocr_corroborated else 0.0


def _reading_participates(reading_id: str, chain: DimensionChain) -> bool:
    if chain.total.reading_id == reading_id:
        return True
    return any(term.reading_id == reading_id for term in chain.parts)


def _chain_component(reading_id: str, chains: Sequence[DimensionChain]) -> float:
    participating = [chain for chain in chains if _reading_participates(reading_id, chain)]
    if not participating:
        # A leitura não aparece em nenhuma cadeia observada: neutro, não é reprovação.
        return 0.5
    return 1.0 if any(chain.closes for chain in participating) else 0.0


def _value_component(reading: DimensionReading) -> float:
    return 1.0 if reading.value_si is not None else 0.0


def reading_confidence(reading: DimensionReading, chains: Sequence[DimensionChain]) -> float:
    """ "Li certo?" — 0 a 1, determinístico, nunca fundido com `association_confidence`."""
    score = (
        _ocr_component(reading.ocr_corroborated) * READING_OCR_WEIGHT
        + _chain_component(reading.id, chains) * READING_CHAIN_WEIGHT
        + _value_component(reading) * READING_VALUE_WEIGHT
    )
    return round(_clamp01(score), 4)


def _orientation_component(orientation_alignment: float | None) -> float:
    if orientation_alignment is None:
        # Candidato sem direção própria (círculo, contorno): sinal ausente, não ruim.
        return 0.5
    return orientation_alignment


def _margin_component(own_proximity: float, other_proximities: Sequence[float]) -> float:
    if not other_proximities:
        # Único candidato elegível para a leitura: nenhuma disputa, sem ambiguidade.
        return 1.0
    margin_raw = own_proximity - max(other_proximities)
    return _clamp01((margin_raw + 1.0) / 2.0)


def _solver_component(solver_residual: SolverResidual | None) -> float:
    if solver_residual is None:
        # Sem diagnóstico de solve para esta revisão ainda: neutro, nunca requisito.
        return 0.5
    return 1.0 if solver_residual.passed else 0.0


def association_confidence(
    candidate: AssociationCandidate,
    reading: DimensionReading,
    *,
    other_candidates: Sequence[AssociationCandidate] = (),
    solver_residual: SolverResidual | None = None,
) -> float:
    """ "Sei onde encaixa?" — 0 a 1, determinístico, nunca fundido com `reading_confidence`.

    `reading` é aceito pela assinatura para sinais futuros que dependam da leitura em si
    (por exemplo `kind` vs. `proposal_kind`); nenhum sinal atual depende dele.
    """
    del reading
    other_proximities = [
        other.proximity_score
        for other in other_candidates
        if other.reading_id == candidate.reading_id and other.proposal_id != candidate.proposal_id
    ]
    orientation_component = _orientation_component(candidate.orientation_alignment)
    margin_component = _margin_component(candidate.proximity_score, other_proximities)
    score = (
        candidate.proximity_score * ASSOCIATION_PROXIMITY_WEIGHT
        + candidate.visual_quality_score * ASSOCIATION_VISUAL_QUALITY_WEIGHT
        + orientation_component * ASSOCIATION_ORIENTATION_WEIGHT
        + margin_component * ASSOCIATION_MARGIN_WEIGHT
        + _solver_component(solver_residual) * ASSOCIATION_SOLVER_WEIGHT
    )
    return round(_clamp01(score), 4)


@dataclass(frozen=True)
class ConfidenceThreshold:
    """Um ponto da grade: acima de qual confiança de leitura e de associação, ambas."""

    reading_threshold: float
    association_threshold: float


@dataclass(frozen=True)
class ShadowChoice:
    """O candidato que o corte hipotético TERIA escolhido para uma leitura.

    Registra o `proposal_id` explicitamente — não só que a leitura passaria no corte —
    porque a calibração (fatia 2/3) compara essa escolha com a associação humana real, e
    recomputar o argmax fora deste registro reabriria o desempate a uma ordem de lista
    que nunca foi um contrato.
    """

    reading_id: str
    proposal_id: str
    reading_confidence: float
    association_confidence: float


@dataclass(frozen=True)
class ShadowDecision:
    """O que TERIA sido auto-decidido neste ponto da grade — nunca uma decisão real."""

    reading_threshold: float
    association_threshold: float
    auto_choices: tuple[ShadowChoice, ...]


def _best_candidate(candidates: Sequence[AssociationCandidate]) -> AssociationCandidate:
    """O candidato de maior `association_confidence` para uma leitura.

    Empate desfeito por `proposal_id` em ordem lexicográfica crescente — desempate
    determinístico e explícito, nunca a ordem de inserção da lista de candidatos.
    """

    def _sort_key(candidate: AssociationCandidate) -> tuple[float, str]:
        return (-candidate.association_confidence, candidate.proposal_id)

    return min(candidates, key=_sort_key)


def shadow_decisions(
    packet: ReviewPacket,
    associations: AssociationSet,
    chains: Sequence[DimensionChain],
    thresholds: Sequence[ConfidenceThreshold],
) -> tuple[ShadowDecision, ...]:
    """Função pura: para cada threshold da grade, quais leituras estariam acima e por qual escolha.

    Uma leitura só entra se leitura E associação (a confiança do seu candidato escolhido)
    estiverem acima do corte — o erro perigoso é associar errado, então nenhuma das duas
    confianças sozinha basta. Sem efeito colateral: não decide, não persiste, não associa
    nada de verdade.
    """
    candidates_by_reading: dict[str, list[AssociationCandidate]] = {}
    for candidate in associations.candidates:
        candidates_by_reading.setdefault(candidate.reading_id, []).append(candidate)

    reading_scores = {
        reading.id: reading_confidence(reading, chains) for reading in packet.readings
    }
    best_by_reading = {
        reading_id: _best_candidate(group) for reading_id, group in candidates_by_reading.items()
    }

    decisions: list[ShadowDecision] = []
    for threshold in thresholds:
        auto_choices = tuple(
            ShadowChoice(
                reading_id=reading_id,
                proposal_id=best.proposal_id,
                reading_confidence=reading_scores[reading_id],
                association_confidence=best.association_confidence,
            )
            for reading_id, best in best_by_reading.items()
            # Leitura sem NENHUM candidato (fora de `best_by_reading`) nunca é
            # auto-decidável, mesmo num corte 0.0 — não há segmento nenhum para associar.
            if reading_scores[reading_id] >= threshold.reading_threshold
            and best.association_confidence >= threshold.association_threshold
        )
        decisions.append(
            ShadowDecision(
                reading_threshold=threshold.reading_threshold,
                association_threshold=threshold.association_threshold,
                auto_choices=auto_choices,
            )
        )
    return tuple(decisions)


CONFIDENCE_THRESHOLD_CUTS: Final[tuple[float, ...]] = (0.5, 0.6, 0.7, 0.8, 0.9, 0.95)
"""Cortes da grade de shadow, aplicados aos DOIS eixos: o da leitura e o da associação.

Grade deliberadamente curta. O shadow é gravado em cada revisão de leitura e viaja em
cada resposta de revisão, e o produto cartesiano cresce com o quadrado dos cortes sem
trazer informação nova: cada escolha de um ponto da grade é derivável das duas
confianças da leitura, que ficam gravadas ao lado (`reading_confidences` e a
`association_confidence` de cada candidato, dentro de `associations`). Um passo de 0,05
entre 0,5 e 0,95 multiplicaria por cem as mesmas N triplas por revisão — e o relatório
de calibração (F-029, fatia 2) recompõe qualquer corte a partir do que está gravado,
com a resolução que ele quiser. Abaixo de 0,5 nada é grade: é ruído para qualquer
leitura de auto-decisão.
"""

CONFIDENCE_THRESHOLD_GRID: Final[tuple[ConfidenceThreshold, ...]] = tuple(
    ConfidenceThreshold(reading_threshold=reading_cut, association_threshold=association_cut)
    for reading_cut in CONFIDENCE_THRESHOLD_CUTS
    for association_cut in CONFIDENCE_THRESHOLD_CUTS
)
"""Grade fixa: os dois eixos são independentes porque os dois erros são diferentes.

Ler errado produz uma cota errada, que a conferência de cadeia e o solver ainda podem
denunciar; associar errado põe a cota certa no segmento errado, e nada a jusante
percebe. Fundir os dois num corte só apagaria essa diferença.
"""

CONFIDENCE_REFERENCE_THRESHOLD: Final[ConfidenceThreshold] = CONFIDENCE_THRESHOLD_GRID[-1]
"""Ponto da grade usado para publicar as taxas observacionais — o MAIS conservador.

Não é threshold operacional e não é recomendação: o corte de operação é escolhido por
uma pessoa a partir do relatório de calibração (F-029, gate humano 3), nunca por um
default do código. Publicar a taxa no ponto mais exigente da grade garante que o número
exposto jamais superestime o que um modo automático faria.
"""


def verified_declared_chain(
    packet: ReviewPacket, declared: Mapping[str, Any]
) -> DimensionChain | None:
    """Reconfere UMA cadeia declarada contra o pacote corrente; `None` quando ela venceu.

    A declaração é histórica e imutável; o veredito não é. Uma participante retificada ou
    rejeitada depois da declaração deixa a cadeia sem pé (`stale` na resposta da API), e
    aqui isso é `None`: conferência impossível, nunca conferência reprovada.
    """
    try:
        return verify_chain(
            packet,
            total_id=str(declared["total_id"]),
            part_ids=[str(part_id) for part_id in declared["part_ids"]],
        )
    except ChainVerificationError:
        return None


def confidence_chains(
    packet: ReviewPacket, declared_chains: Sequence[Mapping[str, Any]]
) -> list[DimensionChain]:
    """Cadeias que pesam na confiança de leitura: as sugeridas que fecham e as DECLARADAS.

    As duas origens entram por critérios diferentes de propósito, porque afirmam coisas
    diferentes:

    - **Sugerida** é descoberta automática e incompleta — `suggest_chains` varre somas e
      já devolve só o que fecha dentro da tolerância. Uma soma que não fecha aí não é
      evidência de nada: pode ser simplesmente uma cota que o croqui não traz (raciocínio
      da F-023). Por isso a sugestão só corrobora, nunca acusa.
    - **Declarada** é ato humano afirmando que estas parcelas, e só estas, compõem este
      total. Quando a aritmética contradiz a afirmação (`mismatch`), essa é a evidência
      humana mais forte contra uma das participantes — e num experimento de auto-decisão o
      conservador é BAIXAR a confiança de quem foi contradito, não ignorar a contradição
      (espírito do ADR-0041). Por isso a declarada entra fechando ou não, e é
      `_chain_component` da T1 que decide o peso: `any(closes)` vence, e a participante de
      cadeia declarada que nenhuma outra cadeia sustenta cai para o componente 0.

    `stale` fica de fora nos dois casos: perdeu uma participante e não é verificável —
    ausência de conferência não é conferência reprovada.

    Uma cadeia repetida nas duas origens é inofensiva: o sinal pergunta se ALGUMA cadeia
    da leitura fecha, não quantas.
    """
    chains = list(suggest_chains(packet))
    chains.extend(
        chain
        for chain in (verified_declared_chain(packet, declared) for declared in declared_chains)
        if chain is not None
    )
    return chains


def confidence_shadow_json(
    packet: ReviewPacket,
    associations: AssociationSet,
    declared_chains: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """O shadow desta revisão, pronto para gravar: computado e nunca aplicado.

    Função pura sobre o que a própria revisão guarda (pacote, candidatos e cadeias
    declaradas). Não decide leitura, não seleciona associação, não cria issue e não
    entra em `blockers`; o registro existe para comparar, depois, o que um corte teria
    escolhido com o que a pessoa de fato escolheu.

    Os denominadores viajam gravados junto porque o relatório de calibração (F-029,
    fatia 2) lê linhas de `review_revisions` e não deveria reabrir cada pacote só para
    saber sobre quantas leituras a taxa foi calculada.

    `score_version` carimba de qual versão de pesos e sinais aquele shadow saiu. Os pesos
    vão ser recalibrados — é o propósito das fatias seguintes —, e sem o carimbo dois
    shadows de versões diferentes conviveriam no banco indistinguíveis, corrompendo o
    relatório de calibração em silêncio.
    """
    chains = confidence_chains(packet, declared_chains)
    readings_with_candidate = {candidate.reading_id for candidate in associations.candidates}
    return {
        "score_version": CONFIDENCE_SCORE_VERSION,
        "reading_confidences": [
            {
                "reading_id": reading.id,
                "reading_confidence": reading_confidence(reading, chains),
            }
            for reading in packet.readings
        ],
        "decisions": [
            {
                "reading_threshold": decision.reading_threshold,
                "association_threshold": decision.association_threshold,
                "auto_choices": [
                    {
                        "reading_id": choice.reading_id,
                        "proposal_id": choice.proposal_id,
                        "reading_confidence": choice.reading_confidence,
                        "association_confidence": choice.association_confidence,
                    }
                    for choice in decision.auto_choices
                ],
            }
            for decision in shadow_decisions(
                packet, associations, chains, CONFIDENCE_THRESHOLD_GRID
            )
        ],
        "readings_total": len(packet.readings),
        "readings_with_candidate": len(readings_with_candidate),
    }
