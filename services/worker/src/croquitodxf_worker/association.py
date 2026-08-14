"""Associação determinística entre recortes de cotas e propostas CV em pixels."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from croquitodxf_worker.io_utils import atomic_write_text
from croquitodxf_worker.review import DimensionReading, ReviewPacket
from croquitodxf_worker.vision import (
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
                )
            )
        if not eligible:
            unassociated_reading_ids.append(reading.id)
            continue
        candidates.extend(
            sorted(
                eligible,
                key=lambda candidate: (
                    candidate.pixel_distance,
                    -candidate.visual_quality_score,
                    candidate.proposal_id,
                ),
            )[: effective_config.max_candidates_per_reading]
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
