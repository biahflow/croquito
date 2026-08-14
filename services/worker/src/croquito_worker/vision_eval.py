"""Eval determinística de propostas geométricas usando apenas fixture sintética."""

from __future__ import annotations

import json
import math
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from croquito_worker.io_utils import atomic_write_text
from croquito_worker.synthetic import (
    CENTRE_CIRCLE_RADIUS,
    FIELD_HEIGHT,
    FIELD_WIDTH,
    render_synthetic_input,
)
from croquito_worker.vision import PixelCircle, PixelLine, write_proposal_artifacts


class VisionEvalReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dataset_id: str
    detector_version: str
    line_recall: float = Field(ge=0, le=1)
    circle_recall: float = Field(ge=0, le=1)
    circle_candidate_precision: float = Field(ge=0, le=1)
    unresolved_rate: float = Field(ge=0, le=1)
    non_exportable_rate: float = Field(ge=0, le=1)
    proposal_count: int = Field(ge=0)
    passed: bool
    thresholds: dict[str, float]


def _line_matches(
    line: PixelLine,
    *,
    orientation: str,
    position: float,
    interval_start: float,
    interval_end: float,
) -> bool:
    delta_x = line.end.x - line.start.x
    delta_y = line.end.y - line.start.y
    length = math.hypot(delta_x, delta_y)
    if length == 0:
        return False
    if orientation == "horizontal":
        if abs(delta_y) / length > math.sin(math.radians(6)):
            return False
        candidate_position = (line.start.y + line.end.y) / 2
        candidate_start, candidate_end = sorted([line.start.x, line.end.x])
    else:
        if abs(delta_x) / length > math.sin(math.radians(6)):
            return False
        candidate_position = (line.start.x + line.end.x) / 2
        candidate_start, candidate_end = sorted([line.start.y, line.end.y])
    overlap = max(
        0.0,
        min(candidate_end, interval_end) - max(candidate_start, interval_start),
    )
    expected_length = interval_end - interval_start
    return abs(candidate_position - position) <= 12 and overlap / expected_length >= 0.72


def run_synthetic_vision_eval(output_dir: Path) -> tuple[VisionEvalReport, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    input_path = output_dir / "vision-fixture.png"
    render_synthetic_input(input_path)
    proposal_set, _proposals_path, _overlay_path = write_proposal_artifacts(
        input_path,
        output_dir,
        dataset_id="synthetic-vision-v1",
        page_number=1,
    )
    left, top = 170.0, 150.0
    right = left + int(FIELD_WIDTH * 30)
    bottom = top + int(FIELD_HEIGHT * 30)
    expected_lines = [
        ("horizontal", top, left, right),
        ("horizontal", bottom, left, right),
        ("vertical", left, top, bottom),
        ("vertical", right, top, bottom),
    ]
    lines = [
        proposal.geometry
        for proposal in proposal_set.proposals
        if isinstance(proposal.geometry, PixelLine)
    ]
    matched_lines = sum(
        any(
            _line_matches(
                line,
                orientation=orientation,
                position=position,
                interval_start=interval_start,
                interval_end=interval_end,
            )
            for line in lines
        )
        for orientation, position, interval_start, interval_end in expected_lines
    )
    expected_center = ((left + right) / 2, (top + bottom) / 2)
    expected_radius = CENTRE_CIRCLE_RADIUS * 30
    circles = [
        proposal.geometry
        for proposal in proposal_set.proposals
        if isinstance(proposal.geometry, PixelCircle)
    ]
    circle_match = any(
        math.hypot(
            circle.center.x - expected_center[0],
            circle.center.y - expected_center[1],
        )
        <= 15
        and abs(circle.radius - expected_radius) <= 15
        for circle in circles
    )
    proposal_count = len(proposal_set.proposals)
    unresolved_rate = (
        sum(proposal.precision == "unresolved" for proposal in proposal_set.proposals)
        / proposal_count
        if proposal_count
        else 1.0
    )
    non_exportable_rate = (
        sum(not proposal.export for proposal in proposal_set.proposals) / proposal_count
        if proposal_count
        else 1.0
    )
    line_recall = matched_lines / len(expected_lines)
    circle_recall = float(circle_match)
    circle_candidate_precision = 1 / len(circles) if circle_match and circles else 0.0
    thresholds = {
        "line_recall": 0.75,
        "circle_recall": 1.0,
        "circle_candidate_precision": 1.0,
        "unresolved_rate": 1.0,
        "non_exportable_rate": 1.0,
    }
    report = VisionEvalReport(
        dataset_id=proposal_set.dataset_id,
        detector_version=proposal_set.detector_version,
        line_recall=line_recall,
        circle_recall=circle_recall,
        circle_candidate_precision=circle_candidate_precision,
        unresolved_rate=unresolved_rate,
        non_exportable_rate=non_exportable_rate,
        proposal_count=proposal_count,
        passed=(
            line_recall >= thresholds["line_recall"]
            and circle_recall >= thresholds["circle_recall"]
            and circle_candidate_precision >= thresholds["circle_candidate_precision"]
            and unresolved_rate == thresholds["unresolved_rate"]
            and non_exportable_rate == thresholds["non_exportable_rate"]
        ),
        thresholds=thresholds,
    )
    report_path = output_dir / "vision-eval.json"
    serialized_report = json.dumps(
        report.model_dump(mode="json"),
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    )
    atomic_write_text(report_path, f"{serialized_report}\n")
    return report, report_path
