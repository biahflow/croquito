"""Associação determinística entre recortes de cotas e propostas CV em pixels."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from croquito_worker.association_confidence import association_confidence as _score_association
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


class AssociationModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, str_strip_whitespace=True)


class AssociationCandidate(AssociationModel):
    reading_id: str = Field(pattern=r"^rd_[a-f0-9]{16}$")
    proposal_id: str = Field(pattern=r"^vp_[a-f0-9]{16}$")
    proposal_kind: Literal["line", "circle", "contour"]
    relation: Literal["nearest_geometry", "inside_or_near_circle"]
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
    max_distance = math.hypot(proposals.image_width_px, proposals.image_height_px) * (
        effective_config.max_distance_diagonal_ratio
    )
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
