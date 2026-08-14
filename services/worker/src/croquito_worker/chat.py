"""Contexto determinístico de um turno de conversa da revisão.

O que o modelo recebe é montado aqui, por função pura: a pergunta do profissional e os
fatos da revisão-base que ele apontou. Nada de identidade — tenant, revisor, job, URL
assinada — entra no payload: o que sai daqui é evidência da folha, não do cliente.

O que volta do modelo é observação, como qualquer outra saída de provider. Os rascunhos de
ato citam ids; conferir que cada id existe no snapshot da revisão-base é responsabilidade
do chamador (`chat_unknown_references`), e um id inventado recusa o turno inteiro em vez de
virar meia resposta aplicável.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Sequence
from typing import Final

from croquito_worker.providers import (
    ChatKeepApartDraft,
    ChatNoteAssociationDraft,
    ChatReadingDecisionDraft,
    ChatTraceAssociationDraft,
    ReviewChatOutput,
)
from croquito_worker.review import DimensionReading
from croquito_worker.tracing import GENERAL_NOTE_TARGET, LEGEND_NOTE_PREFIX
from croquito_worker.vision import VisionProposal

CHAT_CONTEXT_VERSION: Final = "review-chat-context-v1"
"""Versão da forma do payload de contexto; viaja com ele e entra no digest de lineage."""


def _unique(values: Iterable[str]) -> list[str]:
    return list(dict.fromkeys(values))


def build_chat_text_payload(
    *,
    question: str,
    readings: Sequence[DimensionReading],
    proposals: Sequence[VisionProposal],
) -> str:
    """Payload de texto de um turno: a pergunta mais os fatos das âncoras declaradas.

    A ordem das âncoras é a que o profissional declarou — ela carrega a ênfase dele ("essa
    cota contra aquele elemento") e reordenar seria reescrever a pergunta. Duplicata é
    removida preservando a primeira ocorrência, então o mesmo turno produz sempre o mesmo
    texto e, por consequência, o mesmo digest de lineage.

    `raw_text` viaja **literal**: é ele que o profissional vê na folha, e normalizá-lo aqui
    faria o modelo conversar sobre um número que ninguém escreveu.
    """
    unique_readings = {reading.id: reading for reading in readings}
    unique_proposals = {proposal.id: proposal for proposal in proposals}
    payload = {
        "context_version": CHAT_CONTEXT_VERSION,
        "question": question,
        "readings": [
            {
                "id": reading.id,
                "raw_text": reading.raw_text,
                "kind": reading.kind.value,
                "status": reading.status.value,
                "unit": reading.unit.value,
            }
            for reading in unique_readings.values()
        ],
        "proposals": [
            {"id": proposal.id, "kind": proposal.kind, "label": proposal.label}
            for proposal in unique_proposals.values()
        ],
    }
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def note_target_proposal_id(target: str) -> str | None:
    """Proposta que um alvo de nota do traçado ancora; o carimbo não ancora nenhuma."""
    if target == GENERAL_NOTE_TARGET:
        return None
    # Sufixo "#v"/"#h" é dica de orientação da aresta âncora, não parte do id.
    return target.removeprefix(LEGEND_NOTE_PREFIX).partition("#")[0]


def chat_unknown_references(
    answer: ReviewChatOutput,
    *,
    reading_ids: set[str],
    proposal_ids: set[str],
) -> list[str]:
    """Ids citados pelos rascunhos que não existem no snapshot da revisão-base.

    O chamador recusa o turno inteiro quando esta lista não é vazia: uma resposta que
    inventa um id não é uma resposta parcialmente boa, é uma resposta sobre outra folha.
    """
    cited_readings: list[str] = []
    cited_proposals: list[str] = []
    for act in answer.proposed_acts:
        if isinstance(act, ChatReadingDecisionDraft):
            cited_readings.append(act.reading_id)
            if act.association_proposal_id is not None:
                cited_proposals.append(act.association_proposal_id)
        elif isinstance(act, ChatTraceAssociationDraft):
            cited_readings.append(act.reading_id)
            cited_proposals.extend(
                [act.target] if isinstance(act.target, str) else list(act.target)
            )
        elif isinstance(act, ChatKeepApartDraft):
            cited_proposals.extend([act.first, act.second])
        elif isinstance(act, ChatNoteAssociationDraft):
            cited_readings.append(act.reading_id)
            anchored = note_target_proposal_id(act.target)
            if anchored is not None:
                cited_proposals.append(anchored)
    unknown = {item for item in _unique(cited_readings) if item not in reading_ids}
    unknown |= {item for item in _unique(cited_proposals) if item not in proposal_ids}
    return sorted(unknown)
