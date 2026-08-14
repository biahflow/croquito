"""Eval determinística do takeoff: recall da fixture e contrato do fluxo de revisão.

O gate roda inteiramente sobre a prancha sintética; ver a nota de honestidade em
`croquitodxf_worker.valuation.takeoff_eval`.
"""

from __future__ import annotations

from pathlib import Path

from croquitodxf_worker.valuation.plate import (
    PLATE_IMAGE_FILENAME,
    PLATE_PDF_FILENAME,
    SYNTHETIC_LEGEND_ROWS,
)
from croquitodxf_worker.valuation.takeoff_eval import TakeoffEvalReport, run_takeoff_eval

_EXPECTED_CHECKS = {
    "no_item_born_confirmed",
    "ambiguous_without_quantity",
    "evidence_bound_to_render",
    "re_decision_refused",
    "ambiguous_needs_informed_quantity",
    "review_completes_with_decisions",
    "tampered_render_refused",
}


def test_run_takeoff_eval_passes_with_full_recall_and_every_check(tmp_path: Path) -> None:
    report, report_path = run_takeoff_eval(tmp_path)

    assert report.passed is True
    assert report.legend_recall == 1.0
    assert report.thresholds == {"legend_recall": 1.0}
    assert set(report.checks) == _EXPECTED_CHECKS
    assert all(report.checks.values())
    assert report.item_count == len(SYNTHETIC_LEGEND_ROWS)
    assert report_path.is_file()


def test_report_locks_the_exact_set_of_checks(tmp_path: Path) -> None:
    report, _ = run_takeoff_eval(tmp_path)

    assert set(report.checks.keys()) == _EXPECTED_CHECKS


def test_report_is_reloadable_from_the_published_json(tmp_path: Path) -> None:
    report, report_path = run_takeoff_eval(tmp_path)

    reloaded = TakeoffEvalReport.model_validate_json(report_path.read_text(encoding="utf-8"))

    assert reloaded == report


def test_plate_artifacts_exist_alongside_the_report(tmp_path: Path) -> None:
    run_takeoff_eval(tmp_path)

    assert (tmp_path / PLATE_PDF_FILENAME).is_file()
    assert (tmp_path / PLATE_IMAGE_FILENAME).is_file()
