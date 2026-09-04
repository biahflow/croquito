"""Associação determinística entre recortes de cotas e propostas CV em pixels."""

from __future__ import annotations

import json
import math
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from croquito_worker.association_confidence import association_confidence as _score_association
from croquito_worker.element_identity_matching import hint_matches_label
from croquito_worker.io_utils import atomic_write_text
from croquito_worker.review import DimensionReading, PixelBox, ReviewPacket
from croquito_worker.vision import (
    PixelCircle,
    PixelLine,
    PixelPoint,
    PixelPolyline,
    VisionProposal,
    VisionProposalSet,
)

ASSOCIATOR_VERSION = "pixel-proximity-associator-v1"

ELEMENT_IDENTITY_RELATION: Final = "element_identity"
"""A relação da candidata que nasce de identidade declarada, não de distância (ADR-0063 D3).

A procedência mora na CANDIDATA, e é por isso que `AssociationSet.associator_version`
continua sendo `pixel-proximity-associator-v1` mesmo num conjunto que carrega candidatas
por identidade: o associador de proximidade é o mesmo de sempre, e continua produzindo
exatamente o que sempre produziu. Trocar a versão do conjunto diria que o funil mudou —
ele não mudou; o que existe agora é uma segunda origem de candidata, declarada nela mesma.
"""


class AssociationModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, str_strip_whitespace=True)


class AssociationCandidate(AssociationModel):
    reading_id: str = Field(pattern=r"^rd_[a-f0-9]{16}$")
    proposal_id: str = Field(pattern=r"^vp_[a-f0-9]{16}$")
    proposal_kind: Literal["line", "circle", "contour"]
    # `element_identity` é aditivo (F-051 T4): conjunto persistido antes dela continua
    # validando sem tocar em nada. A candidata por identidade nasce do ato humano de
    # declaração, e não da distância — mas os campos observacionais abaixo continuam
    # preenchidos com FATOS medidos (a distância real em pixels é um fato; ela só deixou
    # de ser o critério de elegibilidade).
    relation: Literal["nearest_geometry", "inside_or_near_circle", "element_identity"]
    pixel_distance: float = Field(ge=0)
    proximity_score: float = Field(ge=0, le=1)
    visual_quality_score: float = Field(ge=0, le=1)
    # Alinhamento entre o eixo dominante do bbox da evidência da leitura e a direção do
    # segmento candidato (derivada de `PixelLine.start`/`end`). `None` quando o candidato
    # não tem direção própria (círculo, contorno) — sinal ausente, nunca sinal ruim.
    orientation_alignment: float | None = Field(default=None, ge=0, le=1)
    # Confiança determinística de associação (F-029 T1): "sei a qual segmento esta cota
    # pertence?". Distinta de `reading_confidence` ("li certo?") — nunca se fundem. Default
    # 0.0 é só o valor de um candidato construído fora de `associate_readings` (ex.:
    # fixtures de teste existentes) — o pipeline real sempre recalcula o valor real.
    association_confidence: float = Field(default=0.0, ge=0, le=1)
    precision: Literal["unresolved"] = "unresolved"
    export: Literal[False] = False


class AssociationSet(AssociationModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    dataset_id: str
    page_number: int = Field(ge=1)
    image_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    coordinate_space: Literal["source_image_pixels"] = "source_image_pixels"
    associator_version: Literal["pixel-proximity-associator-v1"] = "pixel-proximity-associator-v1"
    candidates: list[AssociationCandidate]
    unassociated_reading_ids: list[str]
    safety_notes: list[str] = Field(min_length=3)

    @model_validator(mode="after")
    def validate_candidates(self) -> AssociationSet:
        candidate_ids = {candidate.reading_id for candidate in self.candidates}
        if candidate_ids & set(self.unassociated_reading_ids):
            raise ValueError("leitura não pode ser associada e não associada ao mesmo tempo")
        return self


@dataclass(frozen=True)
class AssociationConfig:
    max_candidates_per_reading: int = 3
    max_distance_diagonal_ratio: float = 0.18


def _point_to_segment_distance(point: PixelPoint, start: PixelPoint, end: PixelPoint) -> float:
    delta_x = end.x - start.x
    delta_y = end.y - start.y
    segment_length_squared = delta_x * delta_x + delta_y * delta_y
    if segment_length_squared == 0:
        return math.hypot(point.x - start.x, point.y - start.y)
    progress = (
        (point.x - start.x) * delta_x + (point.y - start.y) * delta_y
    ) / segment_length_squared
    progress = min(1.0, max(0.0, progress))
    closest_x = start.x + progress * delta_x
    closest_y = start.y + progress * delta_y
    return math.hypot(point.x - closest_x, point.y - closest_y)


def _distance_to_polyline(point: PixelPoint, geometry: PixelPolyline) -> float:
    points = geometry.points
    segments = list(zip(points, [*points[1:], points[0]], strict=True))
    return min(_point_to_segment_distance(point, start, end) for start, end in segments)


def _distance_to_proposal(
    point: PixelPoint,
    proposal: VisionProposal,
) -> tuple[float, Literal["nearest_geometry", "inside_or_near_circle"]]:
    geometry = proposal.geometry
    if isinstance(geometry, PixelLine):
        return _point_to_segment_distance(point, geometry.start, geometry.end), "nearest_geometry"
    if isinstance(geometry, PixelCircle):
        center_distance = math.hypot(point.x - geometry.center.x, point.y - geometry.center.y)
        return max(0.0, center_distance - geometry.radius), "inside_or_near_circle"
    if isinstance(geometry, PixelPolyline):
        return _distance_to_polyline(point, geometry), "nearest_geometry"
    raise TypeError(f"geometria CV não suportada: {type(geometry).__name__}")


def _evidence_center(reading: DimensionReading) -> PixelPoint:
    bbox = reading.evidence.bbox
    return PixelPoint(x=(bbox.left + bbox.right) / 2, y=(bbox.top + bbox.bottom) / 2)


def _bbox_dominant_axis_vector(bbox: PixelBox) -> PixelPoint:
    """Vetor unitário do eixo dominante do bbox: o lado mais comprido dá a direção do texto."""
    width = bbox.right - bbox.left
    height = bbox.bottom - bbox.top
    if width >= height:
        return PixelPoint(x=1.0, y=0.0)
    return PixelPoint(x=0.0, y=1.0)


def _orientation_alignment(reading: DimensionReading, proposal: VisionProposal) -> float | None:
    """Alinhamento entre o eixo dominante do texto e a direção do segmento candidato.

    Só linhas têm direção própria derivável de `start`/`end`; círculo e contorno voltam
    `None` — sinal ausente, tratado como neutro por `association_confidence`.
    """
    geometry = proposal.geometry
    if not isinstance(geometry, PixelLine):
        return None
    delta_x = geometry.end.x - geometry.start.x
    delta_y = geometry.end.y - geometry.start.y
    length = math.hypot(delta_x, delta_y)
    if length == 0:
        return None
    axis = _bbox_dominant_axis_vector(reading.evidence.bbox)
    # Valor absoluto: orientação não distingue sentido, só direção (0° e 180° são iguais).
    cosine = abs((delta_x / length) * axis.x + (delta_y / length) * axis.y)
    return round(min(1.0, max(0.0, cosine)), 4)


def _max_candidate_distance(proposals: VisionProposalSet, config: AssociationConfig) -> float:
    """O alcance do funil de proximidade, em pixels: fração da diagonal da imagem."""
    return math.hypot(proposals.image_width_px, proposals.image_height_px) * (
        config.max_distance_diagonal_ratio
    )


def associate_readings(
    packet: ReviewPacket,
    proposals: VisionProposalSet,
    *,
    config: AssociationConfig | None = None,
) -> AssociationSet:
    effective_config = config or AssociationConfig()
    if packet.dataset_id != proposals.dataset_id:
        raise ValueError("dataset do review packet diverge das propostas CV")
    if packet.page_number != proposals.page_number:
        raise ValueError("página do review packet diverge das propostas CV")
    if packet.image_sha256 != proposals.image_sha256:
        raise ValueError("digest do review packet diverge das propostas CV")
    if effective_config.max_candidates_per_reading < 1:
        raise ValueError("max_candidates_per_reading deve ser positivo")
    max_distance = _max_candidate_distance(proposals, effective_config)
    candidates: list[AssociationCandidate] = []
    unassociated_reading_ids: list[str] = []
    for reading in packet.readings:
        center = _evidence_center(reading)
        eligible: list[AssociationCandidate] = []
        for proposal in proposals.proposals:
            distance, relation = _distance_to_proposal(center, proposal)
            if distance > max_distance:
                continue
            proximity = max(0.0, 1 - distance / max_distance)
            eligible.append(
                AssociationCandidate(
                    reading_id=reading.id,
                    proposal_id=proposal.id,
                    proposal_kind=proposal.kind,
                    relation=relation,
                    pixel_distance=round(distance, 4),
                    proximity_score=round(proximity, 4),
                    visual_quality_score=proposal.quality_score,
                    orientation_alignment=_orientation_alignment(reading, proposal),
                    # Provisório: recalculado abaixo depois do ranking final, quando os
                    # demais candidatos da mesma leitura (para a margem) já são conhecidos.
                    association_confidence=0.0,
                )
            )
        if not eligible:
            unassociated_reading_ids.append(reading.id)
            continue
        ranked = sorted(
            eligible,
            key=lambda candidate: (
                candidate.pixel_distance,
                -candidate.visual_quality_score,
                candidate.proposal_id,
            ),
        )[: effective_config.max_candidates_per_reading]
        candidates.extend(
            candidate.model_copy(
                update={
                    "association_confidence": _score_association(
                        candidate,
                        reading,
                        other_candidates=ranked,
                    )
                }
            )
            for candidate in ranked
        )

    return AssociationSet(
        dataset_id=packet.dataset_id,
        page_number=packet.page_number,
        image_sha256=packet.image_sha256,
        candidates=candidates,
        unassociated_reading_ids=unassociated_reading_ids,
        safety_notes=[
            "Associação é calculada somente em pixels da imagem fonte.",
            "Proximidade e quality score não confirmam cota, unidade, alvo ou geometria.",
            "Todo candidato permanece unresolved e não exportável até revisão humana.",
        ],
    )


@dataclass(frozen=True, slots=True)
class ElementIdentity:
    """Uma identidade ATIVA e NOMEADA da revisão, na forma que o casamento consome."""

    element_ref: str
    label: str
    proposal_ids: tuple[str, ...]


def active_element_identities(rows: Iterable[Mapping[str, Any]]) -> list[ElementIdentity]:
    """As identidades da revisão que podem receber cota-balão, na ordem em que foram declaradas.

    Duas entradas ficam de fora, cada uma por um motivo próprio:

    - **revogada** (`status="revoked"`): alguém desfez o ato. A entrada continua no
      histórico e o `element_ref` continua fora do estoque de cunhagem, mas o elemento não
      existe mais — cunhar candidata para ele devolveria em silêncio o que uma pessoa
      desfez;
    - **sem rótulo**: é pelo NOME que o hint procura o referente, e um elemento sem nome não
      tem por onde ser procurado. Declarar sem rótulo continua sendo válido (a identidade
      serve ao transporte no traçado); ela só não participa deste casamento.
    """
    identities: list[ElementIdentity] = []
    for row in rows:
        if row.get("status", "active") != "active":
            continue
        label = row.get("label")
        if not isinstance(label, str) or not label.strip():
            continue
        identities.append(
            ElementIdentity(
                element_ref=str(row["element_ref"]),
                label=label,
                proposal_ids=tuple(row.get("proposal_ids") or ()),
            )
        )
    return identities


def rederive_element_identity_candidates(
    *,
    packet: ReviewPacket,
    proposals: VisionProposalSet,
    associations: AssociationSet,
    identities: Sequence[ElementIdentity],
    confirmed_associations: Mapping[str, str] | None = None,
    config: AssociationConfig | None = None,
) -> AssociationSet:
    """As candidatas por identidade deste conjunto, RECONSTRUÍDAS do zero (F-051 T4).

    Reconstrução, e não acréscimo: toda candidata `element_identity` sai, e as que valem
    voltam a nascer das declarações CORRENTES. É o que faz uma operação só servir aos quatro
    atos que mudam o casamento — declarar, revogar, renomear e corrigir o hint da leitura —
    e é o que garante que aplicar a mesma entrada duas vezes dê o mesmo conjunto. Uma versão
    incremental precisaria saber o que mudou, e erraria em silêncio no dia em que dois atos
    chegassem juntos.

    Uma exceção, e ela é o aceite do Design Approval Package da feature: candidata por
    identidade que SUSTENTA uma associação confirmada (`confirmed_associations`) não é
    removida. Revogar o elemento não desfaz o que uma pessoa já confirmou, e um
    `selected_associations` apontando para um par que não está mais na lista de candidatas
    seria exatamente esse desfazer, adiado — a próxima retificação daquela leitura bateria
    no portão e a associação humana morreria sem ninguém ter decidido nada.

    O que esta função NUNCA faz: tocar candidata de proximidade (nem a pontuação delas),
    tocar `selected_associations`, confirmar o que quer que seja. A candidata nasce
    `unresolved`/`export=false` como todas as outras, e o portão único da API
    (`_apply_association_rules`) continua sendo o caminho de confirmação.

    Quando nada muda, o conjunto de ENTRADA volta — o mesmo objeto, não uma cópia igual.
    Quem chama usa essa identidade para gravar o JSON persistido verbatim, e é assim que um
    job sem declaração nenhuma continua respondendo byte a byte como antes da feature.
    """
    confirmed = dict(confirmed_associations or {})
    effective_config = config or AssociationConfig()
    kept: list[AssociationCandidate] = []
    dropped_reading_ids: set[str] = set()
    for candidate in associations.candidates:
        if candidate.relation != ELEMENT_IDENTITY_RELATION:
            kept.append(candidate)
            continue
        if confirmed.get(candidate.reading_id) == candidate.proposal_id:
            kept.append(candidate)
            continue
        dropped_reading_ids.add(candidate.reading_id)

    proposals_by_id = {proposal.id: proposal for proposal in proposals.proposals}
    max_distance = _max_candidate_distance(proposals, effective_config)
    # O par já presente NÃO ganha duplicata: a leitura cuja candidata mais próxima é
    # justamente uma proposta do elemento declarado continua com uma linha só, a de
    # proximidade, com a pontuação que ela já tinha.
    existing_pairs = {(candidate.reading_id, candidate.proposal_id) for candidate in kept}
    minted: list[AssociationCandidate] = []
    for reading in packet.readings:
        hint = reading.target_entity_label
        if not hint:
            continue
        centre = _evidence_center(reading)
        for identity in identities:
            if not hint_matches_label(hint, identity.label):
                continue
            for proposal_id in identity.proposal_ids:
                proposal = proposals_by_id.get(proposal_id)
                if proposal is None:
                    # Proposta fora do snapshot corrente: não há geometria para medir, e
                    # inventar distância seria a única alternativa. A declaração continua
                    # inteira no histórico da revisão.
                    continue
                pair = (reading.id, proposal.id)
                if pair in existing_pairs:
                    continue
                existing_pairs.add(pair)
                distance, _ = _distance_to_proposal(centre, proposal)
                minted.append(
                    AssociationCandidate(
                        reading_id=reading.id,
                        proposal_id=proposal.id,
                        proposal_kind=proposal.kind,
                        relation=ELEMENT_IDENTITY_RELATION,
                        # Fatos medidos, não critério: a cota-balão está a milhares de
                        # pixels do referente, e é isso que estes números dizem. Quem
                        # revisa merece ver a distância real ao lado da candidata que
                        # chegou por outro caminho.
                        pixel_distance=round(distance, 4),
                        proximity_score=(
                            round(max(0.0, 1 - distance / max_distance), 4)
                            if max_distance > 0
                            else 0.0
                        ),
                        # Forma corrigida por pessoa não tem pontuação de detector
                        # (ADR-0050, decisão 2). O 0.0 aqui é ausência de medição, e o
                        # campo do candidato é obrigatório desde a primeira versão do
                        # contrato; nenhum ranking depende dele nesta relação.
                        visual_quality_score=(
                            proposal.quality_score if proposal.quality_score is not None else 0.0
                        ),
                        orientation_alignment=_orientation_alignment(reading, proposal),
                        # `association_confidence` fica no 0.0 de propósito: o score da
                        # F-029 mede proximidade e margem entre vizinhos, e não sabe nada
                        # sobre identidade declarada. Pontuá-la por proximidade daria
                        # sempre ~0 com aparência de medição; deixá-la neutra mantém a
                        # candidata por identidade FORA de qualquer corte automático —
                        # ela ranqueia para o humano, e só ele a confirma.
                        association_confidence=0.0,
                    )
                )

    candidates = [*kept, *minted]
    reading_ids_with_candidate = {candidate.reading_id for candidate in candidates}
    unassociated = [
        reading_id
        for reading_id in associations.unassociated_reading_ids
        if reading_id not in reading_ids_with_candidate
    ]
    # A leitura que só tinha candidata por identidade e a perdeu volta para a lista de não
    # associadas, em ordem de pacote: o modelo proíbe estar nas duas listas, e sumir das
    # duas esconderia da revisão que aquela cota ficou sem referente nenhum.
    already_listed = set(unassociated)
    unassociated.extend(
        reading.id
        for reading in packet.readings
        if reading.id in dropped_reading_ids
        and reading.id not in reading_ids_with_candidate
        and reading.id not in already_listed
    )
    if (
        candidates == associations.candidates
        and unassociated == associations.unassociated_reading_ids
    ):
        # Reconstrução que chegou ao conjunto de entrada: o objeto de origem volta, e quem
        # grava a revisão nova copia o JSON persistido em vez de reserializá-lo. É o que
        # faz a segunda chamada do MESMO ato (e todo ato de uma revisão sem declaração)
        # sair byte a byte igual ao que já estava no banco.
        return associations
    return AssociationSet.model_validate(
        {
            **associations.model_dump(mode="json"),
            "candidates": [candidate.model_dump(mode="json") for candidate in candidates],
            "unassociated_reading_ids": unassociated,
        }
    )


def load_proposal_set(path: Path) -> VisionProposalSet:
    return VisionProposalSet.model_validate_json(path.read_text(encoding="utf-8"))


def write_association_set(associations: AssociationSet, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "association-candidates.json"
    serialized = json.dumps(
        associations.model_dump(mode="json"),
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    )
    atomic_write_text(path, f"{serialized}\n")
    return path
