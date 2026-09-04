"""Sugestões assistidas de identidade de elemento na REVISÃO (F-051 T3, ADR-0063 decisão 1).

O rótulo que o modelo deu a uma proposta de geometria (`VisionProposal.label`,
`vision.py:114`) vira **sugestão**: nasce `unresolved`, não gera candidata nenhuma no
solver e não vale nada até um humano confirmar — reenviando os mesmos `proposal_ids`
para `POST /v1/jobs/{job_id}/review/elements` (F-051 T2), nunca por um segundo caminho de
escrita. Este módulo só sugere; ele nunca escreve `element_ref` em lugar nenhum.

É o gêmeo, uma etapa antes, de `croquito_core.element_proposals` (F-047 T6, ADR-0058
decisão 2) — mesmo espírito (puro, determinístico, sem provider pago, sem I/O), produtor
NOVO porque a entrada é diferente: `propose_element_groups` opera sobre `SceneRevision`
(pós-solve); aqui a entrada é o `VisionProposalSet` da revisão (pré-solve), que só existe
em `croquito_worker` — e é por isso que este módulo mora aqui, não em `packages/core`
(`packages/core` nunca depende de `croquito_worker`; a direção é a oposta).

O sinal é UM só: propostas com o MESMO `label`, casamento EXATO. Rótulos do modelo variam
de forma ("B" vs. "grade B" vs. "alambrado B") — este produtor não decide normalização
sozinho: a comparação vive em `_label_group_key`, função nomeada para a T4 trocar num lugar
só quando a normalização mínima for decidida (Unknown 1 do contrato da feature, resolvido
na T4 contra o dado do job de referência real).

Proposta sem rótulo (`label is None` ou vazio) nunca é sugerida — não há o que agrupar.
Proposta já coberta por uma declaração ATIVA (`declared_proposal_ids`) também não: ela já
tem identidade, oferecer sugestão de novo seria ruído. Um grupo de UMA única proposta é
sugestão válida: ao contrário dos sinais fracos de `element_proposals` (procedência,
proximidade — que exigem >=2 para não superinterpretar coincidência), o rótulo aqui é um
sinal que o modelo já declarou explicitamente sobre aquela proposta.
"""

from __future__ import annotations

import hashlib
from collections.abc import Collection
from typing import Final, NamedTuple
from uuid import UUID

from croquito_worker.vision import VisionProposalSet

_SUGGESTION_PREFIX: Final = "els_"


class ReviewElementSuggestion(NamedTuple):
    """Um candidato de identidade: nunca escrito na revisão, só oferecido para decisão humana."""

    suggestion_id: str
    label: str
    proposal_ids: tuple[str, ...]


def _suggestion_id(job_id: UUID, proposal_ids: tuple[str, ...]) -> str:
    """Determinístico: o mesmo job e o mesmo conjunto de propostas cunham sempre o mesmo id.

    Molde do hash de `croquito_core.element_proposals._proposal_id`: é o que faz uma
    sugestão recusada (critério de aceite 3 da T3) ser reconhecível na próxima leitura — a
    persistência de recusa guarda este id, e o produtor roda de novo a cada chamada, nunca
    "lembrando" a recusa por conta própria. `job_id` entra no hash porque, diferente das
    entidades da cena (UUIDv7, globalmente únicas), `VisionProposal.id` é só único DENTRO
    do conjunto de um job: dois jobs distintos podem ter propostas com o mesmo id (as
    fixtures de teste do repositório fazem isso de propósito).
    """
    seed = f"{job_id}:" + ",".join(sorted(proposal_ids))
    return f"{_SUGGESTION_PREFIX}{hashlib.sha256(seed.encode()).hexdigest()[:16]}"


def _label_group_key(label: str) -> str:
    """A chave de agrupamento do rótulo — casamento EXATO por enquanto.

    Comparação idêntica à de `croquito_api.main._review_element_label_owner`: a
    normalização mínima ("B" casa com "grade B") é decisão declarada da T4 da F-051, com o
    dado do job de referência real; aproximar aqui, antes dela, seria o casamento difuso em
    silêncio que a feature recusa (ADR-0063). Quando a T4 decidir a constante, esta é a
    ÚNICA função que muda.
    """
    return label


def suggest_review_elements(
    proposals: VisionProposalSet,
    *,
    job_id: UUID,
    declared_proposal_ids: Collection[str] = (),
) -> list[ReviewElementSuggestion]:
    """Sugestões determinísticas para o conjunto de propostas corrente: nunca escreve, só sugere.

    Ordem estável: a ordem em que cada rótulo aparece pela primeira vez em
    `proposals.proposals`. Sem proposta rotulada nenhuma, ou com toda proposta rotulada já
    coberta por declaração ativa, devolve lista vazia — a revisão responde exatamente como
    antes desta feature (critério de aceite 5 do contrato da T3).
    """
    excluded = set(declared_proposal_ids)
    order: list[str] = []
    buckets: dict[str, list[str]] = {}
    labels_by_key: dict[str, str] = {}
    for proposal in proposals.proposals:
        label = proposal.label
        if not label or proposal.id in excluded:
            continue
        key = _label_group_key(label)
        if key not in buckets:
            buckets[key] = []
            order.append(key)
            labels_by_key[key] = label
        buckets[key].append(proposal.id)
    return [
        ReviewElementSuggestion(
            suggestion_id=_suggestion_id(job_id, tuple(buckets[key])),
            label=labels_by_key[key],
            proposal_ids=tuple(buckets[key]),
        )
        for key in order
    ]
