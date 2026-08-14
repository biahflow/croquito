from __future__ import annotations

from decimal import Decimal

import pytest

from croquito_core.models import MeasurementKind, UnitCode
from croquito_worker.association import associate_readings
from croquito_worker.review import (
    DimensionReading,
    EvidenceRegion,
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

IMAGE_DIGEST = "a" * 64


def _packet() -> ReviewPacket:
    return ReviewPacket(
        dataset_id="association-fixture-v1",
        page_number=1,
        image_sha256=IMAGE_DIGEST,
        readings=[
            DimensionReading(
                id="rd_1111111111111111",
                evidence=EvidenceRegion(
                    dataset_id="association-fixture-v1",
                    page_number=1,
                    image_sha256=IMAGE_DIGEST,
                    bbox=PixelBox(left=45, top=10, right=55, bottom=20),
                ),
                raw_text="10,00 m",
                value_si=Decimal("10.00"),
                unit=UnitCode.METRE,
                kind=MeasurementKind.WIDTH,
                written_decimals=2,
                target_hint="linha superior",
                extractor="fixture",
                extractor_version="v1",
                status=ReadingStatus.PROPOSED,
            )
        ],
        safety_notes=["fixture", "revisão humana obrigatória"],
    )


def _proposals(*, image_digest: str = IMAGE_DIGEST) -> VisionProposalSet:
    return VisionProposalSet(
        dataset_id="association-fixture-v1",
        page_number=1,
        image_sha256=image_digest,
        image_width_px=100,
        image_height_px=100,
        configured_limits={"line": 10, "circle": 10, "contour": 10},
        limit_reached=[],
        proposals=[
            VisionProposal(
                id="vp_1111111111111111",
                kind="line",
                geometry=PixelLine(
                    start=PixelPoint(x=0, y=15),
                    end=PixelPoint(x=100, y=15),
                ),
                algorithm="fixture",
                quality_score=0.9,
            ),
            VisionProposal(
                id="vp_2222222222222222",
                kind="circle",
                geometry=PixelCircle(center=PixelPoint(x=80, y=80), radius=10),
                algorithm="fixture",
                quality_score=0.99,
            ),
        ],
        safety_notes=["fixture", "unresolved", "non-exportable"],
    )


def test_association_ranks_nearby_line_without_confirming_it() -> None:
    associations = associate_readings(_packet(), _proposals())

    assert associations.unassociated_reading_ids == []
    assert len(associations.candidates) == 1
    candidate = associations.candidates[0]
    assert candidate.reading_id == "rd_1111111111111111"
    assert candidate.proposal_id == "vp_1111111111111111"
    assert candidate.relation == "nearest_geometry"
    assert candidate.pixel_distance == 0
    assert candidate.precision == "unresolved"
    assert candidate.export is False


def test_association_refuses_mismatched_evidence_digest() -> None:
    with pytest.raises(ValueError, match="digest"):
        associate_readings(_packet(), _proposals(image_digest="b" * 64))
