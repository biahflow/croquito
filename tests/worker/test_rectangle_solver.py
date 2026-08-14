from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from PIL import Image
from pydantic import ValidationError

from croquitodxf_core.errors import DomainValidationError
from croquitodxf_core.models import MeasurementKind, UnitCode
from croquitodxf_worker.dxf import export_scene_package
from croquitodxf_worker.rectangle_solver import RectangleSolveRequest, solve_rectangle
from croquitodxf_worker.review import (
    DimensionReading,
    EvidenceRegion,
    HumanDecision,
    PixelBox,
    ReadingDecisionBatch,
    ReadingDecisionInput,
    ReadingStatus,
    ReviewPacket,
    apply_reading_decisions,
    file_sha256,
    write_review_artifacts,
)
from croquitodxf_worker.solver_eval import run_solver_eval


def _digest() -> str:
    return hashlib.sha256(b"fixture-image").hexdigest()


def _hex_suffix(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()[:16]


def _decision(suffix: str, action: str = "confirm") -> HumanDecision:
    return HumanDecision(
        decision_id=f"hd_{_hex_suffix(suffix)}",
        action=action,
        reviewer_id="reviewer-fixture",
        reviewer_role="engineer",
        decided_at=datetime(2026, 8, 10, tzinfo=UTC),
        note="fixture sintética",
    )


def _reading(
    identifier: str,
    kind: MeasurementKind,
    value: str,
    *,
    confirmed: bool,
) -> DimensionReading:
    return DimensionReading(
        id=f"rd_{_hex_suffix(identifier)}",
        evidence=EvidenceRegion(
            dataset_id="rectangle-fixture-v1",
            page_number=1,
            image_sha256=_digest(),
            bbox=PixelBox(left=20, top=30, right=240, bottom=90),
        ),
        raw_text=value.replace(".", ","),
        value_si=Decimal(value),
        unit=UnitCode.METRE,
        kind=kind,
        written_decimals=2,
        target_hint=kind.value,
        extractor="synthetic_fixture",
        extractor_version="v1",
        status=ReadingStatus.CONFIRMED if confirmed else ReadingStatus.PROPOSED,
        decision=_decision(identifier) if confirmed else None,
    )


def _packet(*, confirmed: bool, circle_value: str = "6.00") -> ReviewPacket:
    return ReviewPacket(
        dataset_id="rectangle-fixture-v1",
        page_number=1,
        image_sha256=_digest(),
        readings=[
            _reading("width", MeasurementKind.WIDTH, "31.95", confirmed=confirmed),
            _reading("height", MeasurementKind.HEIGHT, "25.90", confirmed=confirmed),
            _reading("circle", MeasurementKind.DIAMETER, circle_value, confirmed=confirmed),
        ],
        safety_notes=[
            "Fixture sintética.",
            "Confirmação humana obrigatória fora de fixtures.",
        ],
    )


def _request() -> RectangleSolveRequest:
    return RectangleSolveRequest(
        feature_id="campo-principal",
        width_reading_id=f"rd_{_hex_suffix('width')}",
        height_reading_id=f"rd_{_hex_suffix('height')}",
        centre_circle_reading_id=f"rd_{_hex_suffix('circle')}",
    )


def _associations() -> dict[str, str]:
    return {
        f"rd_{_hex_suffix('width')}": "vp_1111111111111111",
        f"rd_{_hex_suffix('height')}": "vp_2222222222222222",
        f"rd_{_hex_suffix('circle')}": "vp_3333333333333333",
    }


def test_unreviewed_readings_never_create_metric_scene() -> None:
    result = solve_rectangle(
        _packet(confirmed=False), _request(), confirmed_associations=_associations()
    )

    assert result.status == "review_required"
    assert result.scene is None
    assert len(result.blockers) == 3
    assert all("HUMAN_CONFIRMATION_REQUIRED" in blocker for blocker in result.blockers)


def test_confirmed_reading_requires_human_decision() -> None:
    data = _reading("width", MeasurementKind.WIDTH, "31.95", confirmed=False).model_dump()
    data["status"] = ReadingStatus.CONFIRMED

    with pytest.raises(ValidationError, match="decisão humana"):
        DimensionReading.model_validate(data)


def test_confirmed_rectangle_solves_but_remains_unapproved(tmp_path: Path) -> None:
    result = solve_rectangle(
        _packet(confirmed=True), _request(), confirmed_associations=_associations()
    )

    assert result.status == "solved_unapproved"
    assert result.blockers == []
    assert result.scene is not None
    assert result.scene.approved is False
    assert all(residual.passed for residual in result.residuals)
    assert len(result.scene.entities) == 8
    assert len(result.scene.measurements) == 3
    assert result.scene.export_errors() == ["SCENE_NOT_APPROVED"]
    with pytest.raises(DomainValidationError, match="SCENE_NOT_APPROVED"):
        export_scene_package(result.scene, tmp_path)


def test_confirmed_readings_without_explicit_associations_do_not_create_scene() -> None:
    result = solve_rectangle(_packet(confirmed=True), _request())

    assert result.status == "review_required"
    assert result.scene is None
    assert all("EXPLICIT_ASSOCIATION_REQUIRED" in blocker for blocker in result.blockers)


def test_impossible_centre_circle_creates_critical_conflict() -> None:
    result = solve_rectangle(
        _packet(confirmed=True, circle_value="30.00"),
        _request(),
        confirmed_associations=_associations(),
    )

    assert result.status == "conflict"
    assert result.scene is not None
    assert result.blockers == ["CENTRE_CIRCLE_EXCEEDS_FIELD"]
    assert result.scene.issues[0].severity.value == "critical"


def test_review_artifacts_bind_overlay_to_exact_image(tmp_path: Path) -> None:
    image_path = tmp_path / "fixture.png"
    Image.new("RGB", (400, 300), "white").save(image_path)
    packet = _packet(confirmed=False).model_copy(
        update={
            "image_sha256": file_sha256(image_path),
            "readings": [
                reading.model_copy(
                    update={
                        "evidence": reading.evidence.model_copy(
                            update={"image_sha256": file_sha256(image_path)}
                        )
                    }
                )
                for reading in _packet(confirmed=False).readings
            ],
        }
    )

    packet_path, overlay_path = write_review_artifacts(packet, image_path, tmp_path / "review")

    assert packet_path.is_file()
    assert overlay_path.is_file()
    assert Image.open(overlay_path).size == (400, 300)


def test_human_decision_creates_new_packet_and_preserves_original() -> None:
    original = _packet(confirmed=False)
    batch = ReadingDecisionBatch(
        decisions=[
            ReadingDecisionInput(
                reading_id=original.readings[0].id,
                action="confirm",
                reviewer_id="domain-reviewer",
                reviewer_role="architect",
                decided_at=datetime(2026, 8, 10, tzinfo=UTC),
                raw_text="32,00 m",
                value_si=Decimal("32.00"),
                unit=UnitCode.METRE,
                kind=MeasurementKind.WIDTH,
                written_decimals=2,
                target_hint="largura revisada",
            )
        ]
    )

    reviewed = apply_reading_decisions(original, batch)

    assert original.readings[0].status is ReadingStatus.PROPOSED
    assert reviewed.readings[0].status is ReadingStatus.CONFIRMED
    assert reviewed.readings[0].value_si == Decimal("32.00")
    assert reviewed.readings[0].decision is not None
    assert reviewed.readings[1].status is ReadingStatus.PROPOSED


def test_human_decision_rejects_unknown_reading() -> None:
    batch = ReadingDecisionBatch(
        decisions=[
            ReadingDecisionInput(
                reading_id="rd_0000000000000000",
                action="reject",
                reviewer_id="domain-reviewer",
                reviewer_role="engineer",
                decided_at=datetime(2026, 8, 10, tzinfo=UTC),
            )
        ]
    )

    with pytest.raises(ValueError, match="desconhecidas"):
        apply_reading_decisions(_packet(confirmed=False), batch)


def test_human_decision_does_not_overwrite_confirmed_reading() -> None:
    packet = _packet(confirmed=True)
    batch = ReadingDecisionBatch(
        decisions=[
            ReadingDecisionInput(
                reading_id=packet.readings[0].id,
                action="confirm",
                reviewer_id="another-reviewer",
                reviewer_role="engineer",
                decided_at=datetime(2026, 8, 10, tzinfo=UTC),
            )
        ]
    )

    with pytest.raises(ValueError, match="já revisada"):
        apply_reading_decisions(packet, batch)


def test_solver_eval_requires_approval_and_publishes_audited_dxf(tmp_path: Path) -> None:
    report, report_path = run_solver_eval(tmp_path)

    assert report.passed is True
    assert all(report.checks.values())
    assert report.width_error_m == 0
    assert report.height_error_m == 0
    assert report.circle_radius_error_m == 0
    assert report.audit_status == "approved"
    assert report_path.is_file()
