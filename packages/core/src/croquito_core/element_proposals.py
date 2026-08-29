"""Propostas assistidas de agrupamento de elemento (F-047 T6, ADR-0058 decisão 2).

O sistema pode PROPOR o agrupamento de entidades num elemento, do mesmo jeito que já
propõe candidatos de visão: a proposta nasce `unresolved` e nunca escreve `element_ref` em
lugar nenhum — só o ato humano em `POST /v1/jobs/{job_id}/elements`
(`croquito_api.main.declare_element`, F-047 T2) cunha identidade. Este módulo é
deliberadamente puro — só lê uma `SceneRevision`, sem I/O, sem provider pago, sem estado —
para que a mesma cena produza sempre as mesmas propostas, na mesma ordem (critério de
aceite 1 da T6).

Dois sinais, cada um sobre o subconjunto de entidades que a T2 ainda não identificou
(`entity.element_ref is None`) e que não é anotação. `TEXT`, `DIMENSION` e
`DIAMETER_DIMENSION` nunca são "o elemento" — são o rótulo ou a cota que o documentam —,
o mesmo recorte que `services/worker/src/croquito_worker/dxf.py` (`_write_quantities`) já
aplica ao decidir o que é quantidade física:

1. **`provenance`**: entidades da MESMA camada com a MESMA procedência (`summary_code` e os
   mesmos `source_ids`) — o mesmo lote de detecção descreveu mais de um traço do mesmo
   elemento. É o sinal mais forte, mas é só um SINAL, não identidade: duas paredes
   distintas detectadas no mesmo lote (mesmo `summary_code`) também caem aqui, e é
   exatamente esse tipo de proposta errada que o humano tem de poder recusar (critério de
   aceite 4 da T6).
2. **`label_proximity`**: entidades da MESMA camada, sem grupo de procedência, cujo
   centróide está mais perto do MESMO rótulo (`TEXT`) do que de qualquer outro, dentro de
   `LABEL_PROXIMITY_THRESHOLD_M`. É a alternativa "camada + rótulo estruturado" que o
   ADR-0058 rejeita como identidade AUTOMÁTICA e aceita nomeadamente como proposta (seção
   "Alternativas" do ADR).

Nenhum dos dois sinais decide sozinho: os dois produzem só candidatos human-in-the-loop.
Confirmar é o MESMO ato da T2 (o chamador reenvia `entity_ids` para
`POST /v1/jobs/{job_id}/elements`); este módulo não escreve nada e não abre um segundo
caminho de identidade.
"""

from __future__ import annotations

import hashlib
import math
from typing import Final, Literal, NamedTuple
from uuid import UUID

from croquito_core.models import (
    ArcGeometry,
    CircleGeometry,
    Entity,
    EntityKind,
    LayerName,
    LineGeometry,
    PolylineGeometry,
    SceneRevision,
    SplineGeometry,
    TextGeometry,
)

#: Nunca são "o elemento": `TEXT` é o rótulo, `DIMENSION`/`DIAMETER_DIMENSION` são a cota.
_ANNOTATION_KINDS: Final[frozenset[EntityKind]] = frozenset(
    {EntityKind.TEXT, EntityKind.DIMENSION, EntityKind.DIAMETER_DIMENSION}
)

#: Distância máxima, em metros (convenção do repo: metros e radianos internamente), entre
#: o centróide de uma entidade e o rótulo mais próximo para o sinal `label_proximity`.
#: Acima disso o rótulo já não descreve aquele traço — descreve a vizinhança dele.
LABEL_PROXIMITY_THRESHOLD_M: Final = 3.0

_PROPOSAL_PREFIX: Final = "elp_"

#: Sinais que o produtor conhece, na ordem em que são aplicados: procedência primeiro
#: (mais forte), depois proximidade de rótulo. `list_element_proposals`
#: (`croquito_api.main`) preserva esta ordem na resposta.
ElementProposalSignal = Literal["provenance", "label_proximity"]


class ElementGroupProposal(NamedTuple):
    """Um candidato de agrupamento: nunca escrito na cena, só oferecido para decisão humana."""

    proposal_id: str
    layer: LayerName
    entity_ids: tuple[UUID, ...]
    signal: ElementProposalSignal
    label: str | None = None


def _proposal_id(scene: SceneRevision, entity_ids: tuple[UUID, ...]) -> str:
    """Determinístico: a mesma cena e o mesmo conjunto de entidades cunham sempre o mesmo id.

    É o que faz uma proposta recusada (F-047 T6, critério de aceite 6) ser reconhecível na
    próxima leitura: a persistência de recusa guarda este id, e o produtor roda de novo a
    cada chamada — nunca é o produtor que "lembra" a recusa, é o id que é estável.
    """
    seed = f"{scene.job_id}:" + ",".join(sorted(str(item) for item in entity_ids))
    return f"{_PROPOSAL_PREFIX}{hashlib.sha256(seed.encode()).hexdigest()[:16]}"


def _representative_points(entity: Entity) -> list[tuple[float, float]]:
    geometry = entity.geometry
    if isinstance(geometry, LineGeometry):
        return [(geometry.start.x, geometry.start.y), (geometry.end.x, geometry.end.y)]
    if isinstance(geometry, PolylineGeometry):
        return [(point.x, point.y) for point in geometry.points]
    if isinstance(geometry, CircleGeometry):
        return [(geometry.center.x, geometry.center.y)]
    if isinstance(geometry, ArcGeometry):
        return [(geometry.center.x, geometry.center.y)]
    if isinstance(geometry, SplineGeometry):
        return [(point.x, point.y) for point in geometry.fit_points]
    return []


def _centroid(entity: Entity) -> tuple[float, float] | None:
    points = _representative_points(entity)
    if not points:
        return None
    return (
        sum(x for x, _y in points) / len(points),
        sum(y for _x, y in points) / len(points),
    )


def _candidates(scene: SceneRevision) -> list[Entity]:
    """Entidades ainda sem identidade e que não são anotação, na ordem da cena."""
    return [
        entity
        for entity in scene.entities
        if entity.element_ref is None and entity.kind not in _ANNOTATION_KINDS
    ]


def _provenance_groups(candidates: list[Entity]) -> list[tuple[LayerName, tuple[UUID, ...]]]:
    """Sinal 1: mesma camada, mesma procedência (`summary_code` + `source_ids`)."""
    order: list[tuple[LayerName, str, tuple[str, ...]]] = []
    buckets: dict[tuple[LayerName, str, tuple[str, ...]], list[UUID]] = {}
    for entity in candidates:
        if entity.provenance is None:
            continue
        key = (
            entity.layer,
            entity.provenance.summary_code,
            tuple(sorted(entity.provenance.source_ids)),
        )
        if key not in buckets:
            buckets[key] = []
            order.append(key)
        buckets[key].append(entity.id)
    return [(key[0], tuple(buckets[key])) for key in order if len(buckets[key]) >= 2]


def _label_proximity_groups(
    scene: SceneRevision, remaining: list[Entity]
) -> list[tuple[LayerName, tuple[UUID, ...], str]]:
    """Sinal 2: mesma camada, mais perto do MESMO rótulo do que de qualquer outro."""
    labels = [
        (entity.id, entity.geometry.insertion, entity.geometry.text)
        for entity in scene.entities
        if isinstance(entity.geometry, TextGeometry)
    ]
    if not labels:
        return []
    label_text_by_id = {label_id: text for label_id, _point, text in labels}
    order: list[tuple[LayerName, UUID]] = []
    buckets: dict[tuple[LayerName, UUID], list[UUID]] = {}
    for entity in remaining:
        centroid = _centroid(entity)
        if centroid is None:
            continue
        eligible = sorted(
            (
                (math.hypot(point.x - centroid[0], point.y - centroid[1]), str(label_id))
                for label_id, point, _text in labels
            ),
            key=lambda item: item[0],
        )
        if not eligible or eligible[0][0] > LABEL_PROXIMITY_THRESHOLD_M:
            continue
        nearest_id = UUID(eligible[0][1])
        key = (entity.layer, nearest_id)
        if key not in buckets:
            buckets[key] = []
            order.append(key)
        buckets[key].append(entity.id)
    return [
        (key[0], tuple(buckets[key]), label_text_by_id[key[1]])
        for key in order
        if len(buckets[key]) >= 2
    ]


def propose_element_groups(scene: SceneRevision) -> list[ElementGroupProposal]:
    """Propostas determinísticas para a cena corrente: nunca escreve, só sugere.

    Ordem estável: sinal `provenance` primeiro, depois `label_proximity`; dentro de cada
    sinal, a ordem em que os grupos aparecem na cena. Sem entidade candidata ou sem sinal
    algum, devolve lista vazia — a revisão responde exatamente como antes desta feature
    (critério de aceite 7).
    """
    candidates = _candidates(scene)
    provenance_groups = _provenance_groups(candidates)
    grouped_ids = {entity_id for _layer, ids in provenance_groups for entity_id in ids}
    remaining = [entity for entity in candidates if entity.id not in grouped_ids]
    label_groups = _label_proximity_groups(scene, remaining)

    proposals = [
        ElementGroupProposal(
            proposal_id=_proposal_id(scene, ids),
            layer=layer,
            entity_ids=ids,
            signal="provenance",
        )
        for layer, ids in provenance_groups
    ]
    proposals.extend(
        ElementGroupProposal(
            proposal_id=_proposal_id(scene, ids),
            layer=layer,
            entity_ids=ids,
            signal="label_proximity",
            label=label,
        )
        for layer, ids, label in label_groups
    )
    return proposals
