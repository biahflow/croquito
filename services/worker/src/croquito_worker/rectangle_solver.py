"""Solver determinístico para a primeira família controlada: campo retangular."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Literal
from uuid import NAMESPACE_URL, UUID, uuid5

from pydantic import BaseModel, ConfigDict, Field

from croquito_core.models import (
    CircleGeometry,
    Constraint,
    DimensionGeometry,
    Entity,
    EntityKind,
    Issue,
    IssueSeverity,
    LayerName,
    LineGeometry,
    Measurement,
    MeasurementKind,
    Point2D,
    Precision,
    Provenance,
    SceneRevision,
)
from croquito_worker.io_utils import atomic_write_text
from croquito_worker.review import (
    DimensionReading,
    ReadingStatus,
    ReviewPacket,
    SceneApproval,
)

SOLVER_VERSION = "rectangle-solver-v1"


class SolverModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, str_strip_whitespace=True)


class RectangleSolveRequest(SolverModel):
    feature_id: str = Field(min_length=1, max_length=80)
    width_reading_id: str = Field(pattern=r"^rd_[a-f0-9]{16}$")
    height_reading_id: str = Field(pattern=r"^rd_[a-f0-9]{16}$")
    centre_circle_reading_id: str | None = Field(
        default=None,
        pattern=r"^rd_[a-f0-9]{16}$",
    )
    require_centre_circle: bool = True
    include_centre_line: bool = True
    layer: LayerName = LayerName.CAMPO


class SolverResidual(SolverModel):
    code: str = Field(pattern=r"^[A-Z0-9_]{3,64}$")
    expected_m: Decimal
    actual_m: Decimal
    absolute_error_m: Decimal = Field(ge=0)
    tolerance_m: Decimal = Field(ge=0)
    passed: bool


class RectangleSolveResult(SolverModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    solver_version: Literal["rectangle-solver-v1"] = "rectangle-solver-v1"
    status: Literal["solved_unapproved", "review_required", "conflict"]
    dataset_id: str
    feature_id: str
    blockers: list[str]
    residuals: list[SolverResidual]
    scene: SceneRevision | None = None
    safety_notes: list[str] = Field(min_length=2)


class ApprovedRectangleRevision(SolverModel):
    approval: SceneApproval
    source_scene_id: UUID
    scene: SceneRevision


def _uuid(dataset_id: str, feature_id: str, suffix: str) -> UUID:
    return uuid5(NAMESPACE_URL, f"croquito:{dataset_id}:{feature_id}:{suffix}")


def _reading_map(packet: ReviewPacket) -> dict[str, DimensionReading]:
    return {reading.id: reading for reading in packet.readings}


def _resolve_reading(
    readings: dict[str, DimensionReading],
    reading_id: str,
    expected_kinds: set[MeasurementKind],
    blocker_prefix: str,
) -> tuple[DimensionReading | None, list[str]]:
    reading = readings.get(reading_id)
    if reading is None:
        return None, [f"{blocker_prefix}_READING_NOT_FOUND:{reading_id}"]
    if reading.kind not in expected_kinds:
        return None, [f"{blocker_prefix}_KIND_MISMATCH:{reading_id}"]
    if reading.status is not ReadingStatus.CONFIRMED:
        return None, [f"{blocker_prefix}_HUMAN_CONFIRMATION_REQUIRED:{reading_id}"]
    if reading.value_si is None or reading.decision is None:
        return None, [f"{blocker_prefix}_INCOMPLETE_CONFIRMATION:{reading_id}"]
    return reading, []


def _provenance(reading: DimensionReading, association_proposal_id: str) -> Provenance:
    assert reading.decision is not None
    return Provenance(
        source_type="human_confirmed_reading+explicit_association",
        source_ids=[reading.id, reading.decision.decision_id, association_proposal_id],
        summary_code="HUMAN_CONFIRMED_READING_ASSOCIATION",
    )


def _derived_provenance(
    readings: tuple[DimensionReading, ...],
    confirmed_associations: dict[str, str],
) -> Provenance:
    source_ids = [
        item for reading in readings for item in (reading.id, confirmed_associations[reading.id])
    ]
    return Provenance(
        source_type=SOLVER_VERSION,
        source_ids=source_ids,
        summary_code="DERIVED_RECTANGLE_CONSTRAINT",
    )


def _residual(
    code: str,
    expected: Decimal,
    actual: Decimal,
    written_decimals: int,
    unit_scale_to_si: Decimal,
) -> SolverResidual:
    tolerance = max(
        Decimal("0.000001"),
        Decimal(1).scaleb(-written_decimals) / 2 * unit_scale_to_si,
    )
    error = abs(expected - actual)
    return SolverResidual(
        code=code,
        expected_m=expected,
        actual_m=actual,
        absolute_error_m=error,
        tolerance_m=tolerance,
        passed=error <= tolerance,
    )


def solve_rectangle(
    packet: ReviewPacket,
    request: RectangleSolveRequest,
    *,
    confirmed_associations: dict[str, str] | None = None,
) -> RectangleSolveResult:
    readings = _reading_map(packet)
    width, width_blockers = _resolve_reading(
        readings,
        request.width_reading_id,
        {MeasurementKind.WIDTH, MeasurementKind.LENGTH},
        "WIDTH",
    )
    height, height_blockers = _resolve_reading(
        readings,
        request.height_reading_id,
        {MeasurementKind.HEIGHT, MeasurementKind.LENGTH},
        "HEIGHT",
    )
    blockers = [*width_blockers, *height_blockers]
    circle: DimensionReading | None = None
    if request.centre_circle_reading_id is not None:
        circle, circle_blockers = _resolve_reading(
            readings,
            request.centre_circle_reading_id,
            {MeasurementKind.RADIUS, MeasurementKind.DIAMETER},
            "CENTRE_CIRCLE",
        )
        blockers.extend(circle_blockers)
    elif request.require_centre_circle:
        blockers.append("CENTRE_CIRCLE_READING_REQUIRED")

    required_readings = [request.width_reading_id, request.height_reading_id]
    if request.centre_circle_reading_id is not None:
        required_readings.append(request.centre_circle_reading_id)
    associations = confirmed_associations or {}
    blockers.extend(
        f"EXPLICIT_ASSOCIATION_REQUIRED:{reading_id}"
        for reading_id in required_readings
        if not associations.get(reading_id)
    )

    safety_notes = [
        "Pixels e proporções visuais não definem escala nem medida.",
        "O resultado solucionado permanece não aprovado até revisão profissional da cena.",
    ]
    if blockers:
        return RectangleSolveResult(
            status="review_required",
            dataset_id=packet.dataset_id,
            feature_id=request.feature_id,
            blockers=blockers,
            residuals=[],
            safety_notes=safety_notes,
        )

    assert width is not None and width.value_si is not None
    assert height is not None and height.value_si is not None
    width_m = width.value_si
    height_m = height.value_si
    width_float = float(width_m)
    height_float = float(height_m)
    source_width = _provenance(width, associations[width.id])
    source_height = _provenance(height, associations[height.id])
    derived = _derived_provenance((width, height), associations)

    top_id = _uuid(packet.dataset_id, request.feature_id, "top")
    right_id = _uuid(packet.dataset_id, request.feature_id, "right")
    bottom_id = _uuid(packet.dataset_id, request.feature_id, "bottom")
    left_id = _uuid(packet.dataset_id, request.feature_id, "left")
    entities = [
        Entity(
            id=top_id,
            kind=EntityKind.LINE,
            layer=request.layer,
            precision=Precision.EXACT,
            geometry=LineGeometry(
                start=Point2D(x=0, y=height_float),
                end=Point2D(x=width_float, y=height_float),
            ),
            provenance=source_width,
        ),
        Entity(
            id=right_id,
            kind=EntityKind.LINE,
            layer=request.layer,
            precision=Precision.EXACT,
            geometry=LineGeometry(
                start=Point2D(x=width_float, y=height_float),
                end=Point2D(x=width_float, y=0),
            ),
            provenance=source_height,
        ),
        Entity(
            id=bottom_id,
            kind=EntityKind.LINE,
            layer=request.layer,
            precision=Precision.EXACT,
            geometry=LineGeometry(
                start=Point2D(x=width_float, y=0),
                end=Point2D(x=0, y=0),
            ),
            provenance=source_width,
        ),
        Entity(
            id=left_id,
            kind=EntityKind.LINE,
            layer=request.layer,
            precision=Precision.EXACT,
            geometry=LineGeometry(
                start=Point2D(x=0, y=0),
                end=Point2D(x=0, y=height_float),
            ),
            provenance=source_height,
        ),
    ]
    if request.include_centre_line:
        entities.append(
            Entity(
                id=_uuid(packet.dataset_id, request.feature_id, "centre-line"),
                kind=EntityKind.LINE,
                layer=LayerName.DETALHES,
                precision=Precision.DERIVED,
                geometry=LineGeometry(
                    start=Point2D(x=width_float / 2, y=0),
                    end=Point2D(x=width_float / 2, y=height_float),
                ),
                provenance=derived,
            )
        )

    measurements = [
        Measurement(
            id=_uuid(packet.dataset_id, request.feature_id, "measurement-width"),
            entity_id=top_id,
            kind=MeasurementKind.WIDTH,
            raw_text=width.raw_text,
            value_si=width_m,
            unit=width.unit,
            written_decimals=width.written_decimals,
            confirmed=True,
            provenance=source_width,
        ),
        Measurement(
            id=_uuid(packet.dataset_id, request.feature_id, "measurement-height"),
            entity_id=left_id,
            kind=MeasurementKind.HEIGHT,
            raw_text=height.raw_text,
            value_si=height_m,
            unit=height.unit,
            written_decimals=height.written_decimals,
            confirmed=True,
            provenance=source_height,
        ),
    ]
    entities.extend(
        [
            Entity(
                id=_uuid(packet.dataset_id, request.feature_id, "dimension-width"),
                kind=EntityKind.DIMENSION,
                layer=LayerName.COTAS,
                precision=Precision.EXACT,
                geometry=DimensionGeometry(
                    first=Point2D(x=0, y=height_float),
                    second=Point2D(x=width_float, y=height_float),
                    base=Point2D(x=0, y=height_float + max(1.0, height_float * 0.06)),
                    text_override=f"{width_m} m",
                ),
                provenance=source_width,
            ),
            Entity(
                id=_uuid(packet.dataset_id, request.feature_id, "dimension-height"),
                kind=EntityKind.DIMENSION,
                layer=LayerName.COTAS,
                precision=Precision.EXACT,
                geometry=DimensionGeometry(
                    first=Point2D(x=0, y=0),
                    second=Point2D(x=0, y=height_float),
                    base=Point2D(x=-max(1.0, width_float * 0.06), y=0),
                    text_override=f"{height_m} m",
                ),
                provenance=source_height,
            ),
        ]
    )

    if circle is not None:
        assert circle.value_si is not None
        assert circle.decision is not None
        radius_m = (
            circle.value_si / 2 if circle.kind is MeasurementKind.DIAMETER else circle.value_si
        )
        if radius_m * 2 >= min(width_m, height_m):
            blockers.append("CENTRE_CIRCLE_EXCEEDS_FIELD")
        else:
            circle_id = _uuid(packet.dataset_id, request.feature_id, "centre-circle")
            circle_provenance = Provenance(
                source_type="human_confirmed_reading+rectangle-solver-v1",
                source_ids=[circle.id, circle.decision.decision_id, width.id, height.id],
                summary_code="CONFIRMED_RADIUS_DERIVED_CENTER",
            )
            entities.append(
                Entity(
                    id=circle_id,
                    kind=EntityKind.CIRCLE,
                    layer=LayerName.DETALHES,
                    precision=Precision.EXACT,
                    geometry=CircleGeometry(
                        center=Point2D(x=width_float / 2, y=height_float / 2),
                        radius=float(radius_m),
                    ),
                    provenance=circle_provenance,
                )
            )
            measurements.append(
                Measurement(
                    id=_uuid(packet.dataset_id, request.feature_id, "measurement-circle"),
                    entity_id=circle_id,
                    kind=circle.kind,
                    raw_text=circle.raw_text,
                    value_si=circle.value_si,
                    unit=circle.unit,
                    written_decimals=circle.written_decimals,
                    confirmed=True,
                    provenance=_provenance(circle, associations[circle.id]),
                )
            )

    residuals = [
        _residual(
            "WIDTH_RESIDUAL",
            width_m,
            Decimal(str(width_float)),
            width.written_decimals,
            Decimal("0.001") if width.unit.value == "mm" else Decimal(1),
        ),
        _residual(
            "HEIGHT_RESIDUAL",
            height_m,
            Decimal(str(height_float)),
            height.written_decimals,
            Decimal("0.001") if height.unit.value == "mm" else Decimal(1),
        ),
    ]
    if any(not residual.passed for residual in residuals):
        blockers.append("NUMERIC_RESIDUAL_EXCEEDS_TOLERANCE")

    issues = [
        Issue(
            code=blocker.split(":", maxsplit=1)[0],
            severity=IssueSeverity.CRITICAL,
            message=blocker,
        )
        for blocker in blockers
    ]
    scene = SceneRevision(
        id=_uuid(packet.dataset_id, request.feature_id, "scene-draft"),
        job_id=_uuid(packet.dataset_id, request.feature_id, "job"),
        version=1,
        created_at=datetime.now(UTC),
        approved=False,
        entities=entities,
        measurements=measurements,
        constraints=[
            Constraint(
                id=_uuid(packet.dataset_id, request.feature_id, "constraint-rectangle"),
                kind="orthogonal_rectangle",
                entity_ids=[top_id, right_id, bottom_id, left_id],
                tolerance=1e-9,
                hard=True,
                satisfied=True,
            )
        ],
        issues=issues,
    )
    status: Literal["solved_unapproved", "conflict"] = (
        "conflict" if blockers else "solved_unapproved"
    )
    return RectangleSolveResult(
        status=status,
        dataset_id=packet.dataset_id,
        feature_id=request.feature_id,
        blockers=blockers,
        residuals=residuals,
        scene=scene,
        safety_notes=safety_notes,
    )


def write_solve_result(result: RectangleSolveResult, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    result_path = output_dir / "solve-result.json"
    serialized = json.dumps(
        result.model_dump(mode="json"),
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    )
    atomic_write_text(result_path, f"{serialized}\n")
    return result_path


def approve_rectangle(
    result: RectangleSolveResult,
    approval: SceneApproval,
) -> ApprovedRectangleRevision:
    if result.status != "solved_unapproved" or result.scene is None:
        raise ValueError("somente solução sem blockers pode ser aprovada")
    if approval.source_scene_id != result.scene.id:
        raise ValueError("aprovação aponta para outra revisão")
    preapproval_errors = [
        error for error in result.scene.export_errors() if error != "SCENE_NOT_APPROVED"
    ]
    if preapproval_errors:
        raise ValueError(f"revisão contém blockers de exportação: {preapproval_errors}")
    approved_scene = result.scene.model_copy(
        deep=True,
        update={
            "id": uuid5(
                NAMESPACE_URL,
                f"croquito:{result.scene.id}:{approval.approval_id}:approved",
            ),
            "version": result.scene.version + 1,
            "created_at": approval.decided_at,
            "approved": True,
        },
    )
    approved_scene.ensure_exportable()
    return ApprovedRectangleRevision(
        approval=approval,
        source_scene_id=result.scene.id,
        scene=approved_scene,
    )


def write_approved_revision(
    approved: ApprovedRectangleRevision,
    output_dir: Path,
) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    scene_path = output_dir / "scene-approved.json"
    approval_path = output_dir / "aprovacao.json"
    scene_json = json.dumps(
        approved.scene.model_dump(mode="json"),
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    )
    approval_json = json.dumps(
        {
            "source_scene_id": str(approved.source_scene_id),
            **approved.approval.model_dump(mode="json"),
        },
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    )
    atomic_write_text(scene_path, f"{scene_json}\n")
    atomic_write_text(approval_path, f"{approval_json}\n")
    return scene_path, approval_path
