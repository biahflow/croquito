"""Avaliação sintética ponta a ponta de leitura revisada, solver e DXF."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Literal
from zipfile import ZipFile

from pydantic import BaseModel, ConfigDict

from croquitodxf_core.models import MeasurementKind, UnitCode
from croquitodxf_worker.dxf import export_scene_package
from croquitodxf_worker.io_utils import atomic_write_text
from croquitodxf_worker.rectangle_solver import (
    RectangleSolveRequest,
    approve_rectangle,
    solve_rectangle,
    write_approved_revision,
    write_solve_result,
)
from croquitodxf_worker.review import (
    DimensionReading,
    EvidenceRegion,
    HumanDecision,
    PixelBox,
    ReadingStatus,
    ReviewPacket,
    SceneApproval,
    file_sha256,
    write_review_artifacts,
)
from croquitodxf_worker.synthetic import (
    CENTRE_CIRCLE_RADIUS,
    FIELD_HEIGHT,
    FIELD_WIDTH,
    render_synthetic_input,
)


class SolverEvalReport(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    schema_version: Literal["1.0.0"] = "1.0.0"
    passed: bool
    checks: dict[str, bool]
    width_error_m: Decimal
    height_error_m: Decimal
    circle_radius_error_m: Decimal
    draft_scene_id: str
    approved_scene_id: str
    audit_status: str
    package_file: str


def _suffix(label: str) -> str:
    return hashlib.sha256(label.encode()).hexdigest()[:16]


def _decision(label: str) -> HumanDecision:
    return HumanDecision(
        decision_id=f"hd_{_suffix(label)}",
        action="confirm",
        reviewer_id="synthetic-fixture-reviewer",
        reviewer_role="domain_reviewer",
        decided_at=datetime(2026, 1, 1, tzinfo=UTC),
        note="Decisão exclusiva da fixture sintética versionada.",
    )


def _reading(
    image_digest: str,
    *,
    label: str,
    kind: MeasurementKind,
    value: Decimal,
    bbox: PixelBox,
) -> DimensionReading:
    return DimensionReading(
        id=f"rd_{_suffix(label)}",
        evidence=EvidenceRegion(
            dataset_id="rectangle-solver-fixture-v1",
            page_number=1,
            image_sha256=image_digest,
            bbox=bbox,
        ),
        raw_text=str(value).replace(".", ","),
        value_si=value,
        unit=UnitCode.METRE,
        kind=kind,
        written_decimals=2,
        target_hint=label,
        extractor="synthetic_fixture",
        extractor_version="v1",
        status=ReadingStatus.CONFIRMED,
        decision=_decision(label),
    )


def run_solver_eval(output_dir: Path) -> tuple[SolverEvalReport, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    input_path = output_dir / "entrada-sintetica.png"
    render_synthetic_input(input_path)
    digest = file_sha256(input_path)
    readings = [
        _reading(
            digest,
            label="width",
            kind=MeasurementKind.WIDTH,
            value=Decimal(str(FIELD_WIDTH)),
            bbox=PixelBox(left=560, top=60, right=760, bottom=130),
        ),
        _reading(
            digest,
            label="height",
            kind=MeasurementKind.HEIGHT,
            value=Decimal(str(FIELD_HEIGHT)),
            bbox=PixelBox(left=5, top=400, right=160, bottom=650),
        ),
        _reading(
            digest,
            label="circle",
            kind=MeasurementKind.RADIUS,
            value=Decimal(str(CENTRE_CIRCLE_RADIUS)),
            bbox=PixelBox(left=600, top=420, right=800, bottom=650),
        ),
    ]
    packet = ReviewPacket(
        dataset_id="rectangle-solver-fixture-v1",
        page_number=1,
        image_sha256=digest,
        readings=readings,
        safety_notes=[
            "Somente dados sintéticos; não mede desempenho em documentos reais.",
            "As decisões humanas deste pacote pertencem apenas à fixture.",
        ],
    )
    write_review_artifacts(packet, input_path, output_dir)
    request = RectangleSolveRequest(
        feature_id="campo-sintetico",
        width_reading_id=readings[0].id,
        height_reading_id=readings[1].id,
        centre_circle_reading_id=readings[2].id,
    )
    result = solve_rectangle(
        packet,
        request,
        confirmed_associations={
            packet.readings[0].id: "vp_1111111111111111",
            packet.readings[1].id: "vp_2222222222222222",
            packet.readings[2].id: "vp_3333333333333333",
        },
    )
    write_solve_result(result, output_dir)
    if result.scene is None:
        raise RuntimeError(f"fixture não solucionada: {result.blockers}")
    blocked_before_approval = result.scene.export_errors() == ["SCENE_NOT_APPROVED"]
    approval = SceneApproval(
        approval_id=f"ap_{_suffix('scene-approval')}",
        source_scene_id=result.scene.id,
        reviewer_id="synthetic-fixture-reviewer",
        reviewer_role="domain_reviewer",
        decided_at=datetime(2026, 1, 1, tzinfo=UTC),
        source_evidence_checked=True,
        geometry_checked=True,
        limitations_acknowledged=True,
        statement="Aprovação exclusiva da fixture sintética, sem validade profissional externa.",
    )
    approved = approve_rectangle(result, approval)
    _, approval_path = write_approved_revision(approved, output_dir)
    export = export_scene_package(
        approved.scene,
        output_dir,
        package_stem="solver-sintetico",
        extra_package_files=[approval_path],
    )

    residual_by_code = {residual.code: residual for residual in result.residuals}
    width_error = residual_by_code["WIDTH_RESIDUAL"].absolute_error_m
    height_error = residual_by_code["HEIGHT_RESIDUAL"].absolute_error_m
    circle_measurement = next(
        measurement
        for measurement in approved.scene.measurements
        if measurement.kind is MeasurementKind.RADIUS
    )
    assert circle_measurement.value_si is not None
    circle_error = abs(circle_measurement.value_si - Decimal(str(CENTRE_CIRCLE_RADIUS)))
    checks = {
        "solver_solved": result.status == "solved_unapproved",
        "draft_blocked_before_approval": blocked_before_approval,
        "human_approval_bound_to_draft": approved.source_scene_id == result.scene.id,
        "approved_revision_is_new": approved.scene.id != result.scene.id,
        "all_residuals_pass": all(residual.passed for residual in result.residuals),
        "dxf_audit_approved": export.audit.status == "approved",
        "approval_in_package": False,
    }
    with ZipFile(export.package_path) as archive:
        checks["approval_in_package"] = approval_path.name in archive.namelist()
    report = SolverEvalReport(
        passed=all(checks.values()),
        checks=checks,
        width_error_m=width_error,
        height_error_m=height_error,
        circle_radius_error_m=circle_error,
        draft_scene_id=str(result.scene.id),
        approved_scene_id=str(approved.scene.id),
        audit_status=export.audit.status,
        package_file=export.package_path.name,
    )
    report_path = output_dir / "solver-eval.json"
    serialized = json.dumps(
        report.model_dump(mode="json"),
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    )
    atomic_write_text(report_path, f"{serialized}\n")
    return report, report_path
