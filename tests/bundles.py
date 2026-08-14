"""Construção de um pacote de revisão sintético válido para `seed-review`.

Os quatro digests de imagem e o digest do documento são amarrados ao que é realmente
gravado em disco, porque é exatamente essa cadeia que o comando verifica.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from PIL import Image
from pydantic import BaseModel

from croquito_worker.association import AssociationSet
from croquito_worker.ingest import PageManifest, PdfManifest
from croquito_worker.rectangle_solver import RectangleSolveRequest
from croquito_worker.review import (
    DimensionReading,
    EvidenceRegion,
    HumanDecision,
    PixelBox,
    ReadingStatus,
    ReviewPacket,
)
from croquito_worker.vision import (
    PixelCircle,
    PixelLine,
    PixelPoint,
    VisionProposal,
    VisionProposalSet,
)

WIDTH_READING_ID = "rd_1111111111111111"
HEIGHT_READING_ID = "rd_2222222222222222"
CIRCLE_READING_ID = "rd_3333333333333333"
WIDTH_PROPOSAL_ID = "vp_1111111111111111"
HEIGHT_PROPOSAL_ID = "vp_2222222222222222"
CIRCLE_PROPOSAL_ID = "vp_3333333333333333"

WIDTH_M = "25.90"
HEIGHT_M = "21.75"
CIRCLE_DIAMETER_M = "6.00"


def _write_json(path: Path, payload: BaseModel) -> Path:
    path.write_text(
        json.dumps(payload.model_dump(mode="json"), ensure_ascii=False), encoding="utf-8"
    )
    return path


def _reading(
    identifier: str,
    *,
    dataset_id: str,
    digest: str,
    value: str,
    kind: str,
    hint: str,
    left: int,
    decided: bool,
) -> DimensionReading:
    decision = (
        HumanDecision(
            decision_id="hd_" + "a" * 16,
            action="confirm",
            reviewer_id="reviewer",
            reviewer_role="engineer",
            decided_at=datetime.now(UTC),
            note="Decisão fabricada que o seed precisa recusar.",
        )
        if decided
        else None
    )
    return DimensionReading(
        id=identifier,
        evidence=EvidenceRegion(
            dataset_id=dataset_id,
            page_number=1,
            image_sha256=digest,
            bbox=PixelBox(left=left, top=5, right=left + 20, bottom=15),
        ),
        raw_text=f"{value} m",
        value_si=Decimal(value),
        unit="m",
        kind=kind,
        written_decimals=2,
        target_hint=hint,
        extractor="local-fixture",
        extractor_version="v1",
        status=ReadingStatus.CONFIRMED if decided else ReadingStatus.PROPOSED,
        decision=decision,
    )


def build_packet(*, dataset_id: str, digest: str, decided: bool = False) -> ReviewPacket:
    return ReviewPacket(
        dataset_id=dataset_id,
        page_number=1,
        image_sha256=digest,
        readings=[
            _reading(
                WIDTH_READING_ID,
                dataset_id=dataset_id,
                digest=digest,
                value=WIDTH_M,
                kind="width",
                hint="campo principal",
                left=0,
                decided=decided,
            ),
            _reading(
                HEIGHT_READING_ID,
                dataset_id=dataset_id,
                digest=digest,
                value=HEIGHT_M,
                kind="height",
                hint="campo principal",
                left=20,
                decided=decided,
            ),
            _reading(
                CIRCLE_READING_ID,
                dataset_id=dataset_id,
                digest=digest,
                value=CIRCLE_DIAMETER_M,
                kind="diameter",
                hint="círculo central",
                left=40,
                decided=decided,
            ),
        ],
        safety_notes=["Fixture local.", "Revisão humana obrigatória."],
    )


def build_associations(
    *, dataset_id: str, digest: str, drop_circle: bool = False
) -> AssociationSet:
    candidates: list[dict[str, Any]] = [
        {
            "reading_id": WIDTH_READING_ID,
            "proposal_id": WIDTH_PROPOSAL_ID,
            "proposal_kind": "line",
            "relation": "nearest_geometry",
            "pixel_distance": 1,
            "proximity_score": 0.9,
            "visual_quality_score": 0.8,
        },
        {
            "reading_id": HEIGHT_READING_ID,
            "proposal_id": HEIGHT_PROPOSAL_ID,
            "proposal_kind": "line",
            "relation": "nearest_geometry",
            "pixel_distance": 1,
            "proximity_score": 0.9,
            "visual_quality_score": 0.8,
        },
        {
            "reading_id": CIRCLE_READING_ID,
            "proposal_id": CIRCLE_PROPOSAL_ID,
            "proposal_kind": "circle",
            "relation": "inside_or_near_circle",
            "pixel_distance": 1,
            "proximity_score": 0.9,
            "visual_quality_score": 0.8,
        },
    ]
    if drop_circle:
        candidates = candidates[:2]
    return AssociationSet.model_validate(
        {
            "dataset_id": dataset_id,
            "page_number": 1,
            "image_sha256": digest,
            "candidates": candidates,
            "unassociated_reading_ids": [CIRCLE_READING_ID] if drop_circle else [],
            "safety_notes": ["pixels", "não confirma", "não exporta"],
        }
    )


def build_proposals(*, dataset_id: str, digest: str) -> VisionProposalSet:
    return VisionProposalSet(
        dataset_id=dataset_id,
        page_number=1,
        image_sha256=digest,
        image_width_px=40,
        image_height_px=30,
        configured_limits={"line": 80, "circle": 16, "contour": 16},
        limit_reached=[],
        proposals=[
            VisionProposal(
                id=WIDTH_PROPOSAL_ID,
                kind="line",
                geometry=PixelLine(start=PixelPoint(x=0, y=0), end=PixelPoint(x=30, y=0)),
                algorithm="fixture",
                quality_score=0.9,
            ),
            VisionProposal(
                id=HEIGHT_PROPOSAL_ID,
                kind="line",
                geometry=PixelLine(start=PixelPoint(x=0, y=0), end=PixelPoint(x=0, y=20)),
                algorithm="fixture",
                quality_score=0.9,
            ),
            VisionProposal(
                id=CIRCLE_PROPOSAL_ID,
                kind="circle",
                geometry=PixelCircle(center=PixelPoint(x=15, y=10), radius=4),
                algorithm="fixture",
                quality_score=0.9,
            ),
        ],
        safety_notes=["fixture", "pixels", "não exportável"],
    )


def build_manifest(*, dataset_id: str, digest: str, source_sha256: str) -> PdfManifest:
    return PdfManifest(
        dataset_id=dataset_id,
        role="golden",
        source_basename="levantamento.pdf",
        source_sha256=source_sha256,
        source_size_bytes=1024,
        page_count=1,
        encrypted=False,
        rendered_at=datetime.now(UTC),
        renderer="pymupdf",
        retention_notice="Retenção local de sete dias.",
        pages=[
            PageManifest(
                number=1,
                width_points=595.0,
                height_points=842.0,
                rotation_degrees=0,
                rendered_width_px=40,
                rendered_height_px=30,
                ink_coverage=0.1,
                text_character_count=10,
                vector_drawing_count=2,
                blank_candidate=False,
                image_sha256=digest,
                render_file="page-001.png",
            )
        ],
    )


def build_request(*, with_centre_circle: bool = True) -> RectangleSolveRequest:
    return RectangleSolveRequest(
        feature_id="campo-principal",
        width_reading_id=WIDTH_READING_ID,
        height_reading_id=HEIGHT_READING_ID,
        centre_circle_reading_id=CIRCLE_READING_ID if with_centre_circle else None,
        require_centre_circle=with_centre_circle,
    )


def write_seed_bundle(
    directory: Path,
    *,
    source_sha256: str,
    dataset_id: str = "golden-local-v1",
    decided: bool = False,
    drop_circle_candidate: bool = False,
    manifest_source_sha256: str | None = None,
) -> dict[str, Path]:
    """Writes the six files `seed-review` requires, with every digest bound to disk."""
    directory.mkdir(parents=True, exist_ok=True)
    image_path = directory / "page-001.png"
    Image.new("RGB", (40, 30), "white").save(image_path)
    digest = hashlib.sha256(image_path.read_bytes()).hexdigest()

    return {
        "image": image_path,
        "packet": _write_json(
            directory / "review-packet.json",
            build_packet(dataset_id=dataset_id, digest=digest, decided=decided),
        ),
        "associations": _write_json(
            directory / "association-candidates.json",
            build_associations(
                dataset_id=dataset_id, digest=digest, drop_circle=drop_circle_candidate
            ),
        ),
        "proposals": _write_json(
            directory / "vision-proposals.json",
            build_proposals(dataset_id=dataset_id, digest=digest),
        ),
        "manifest": _write_json(
            directory / "manifest.json",
            build_manifest(
                dataset_id=dataset_id,
                digest=digest,
                source_sha256=manifest_source_sha256 or source_sha256,
            ),
        ),
        "rectangle_request": _write_json(directory / "rectangle-request.json", build_request()),
    }
