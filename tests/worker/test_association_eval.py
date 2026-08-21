"""Gate de associação (F-029 T3) e relatório local de calibração.

Dois assuntos, um arquivo, no formato pedido pelo Task Contract: o gate determinístico
sobre a fixture sintética (`association-eval`, molde `vision_eval.py`) e o replay local
sobre revisões conhecidas (`calibration-report`, família `valuation-parity` — nunca CI).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest

from croquito_api.database import (
    Database,
    JobRecord,
    ProjectRecord,
    ReviewRevisionRecord,
    UploadRecord,
)
from croquito_worker import cli
from croquito_worker.association import associate_readings
from croquito_worker.association_confidence import CONFIDENCE_SCORE_VERSION
from croquito_worker.association_eval import (
    ASSOCIATION_EVAL_GATE_THRESHOLD,
    EVAL_CONFIG,
    build_association_eval_fixture,
    evaluate_association_set,
    run_synthetic_association_eval,
)
from croquito_worker.calibration_report import CalibrationReportError, run_calibration_report

TENANT_ID = "tenant-calibration"
JOB_ID = UUID("00000000-0000-7000-8000-000000002001")


def _run_main(monkeypatch: pytest.MonkeyPatch, argv: list[str]) -> int:
    monkeypatch.setattr("sys.argv", ["croquito-demo", *argv])
    return cli.main()


# --- association-eval: gate determinístico -----------------------------------------------


def test_association_eval_gate_passes_on_synthetic_fixture(tmp_path: Path) -> None:
    report, report_path = run_synthetic_association_eval(tmp_path)

    assert report.passed is True
    assert report.errors_above_gate == 0
    assert report.recall_top1 == 1.0
    assert report.eligible_count == 4
    assert report.reading_count == 5
    assert report.unassociated_as_expected is True
    assert report_path.exists()


def test_association_eval_is_deterministic(tmp_path: Path) -> None:
    first, _ = run_synthetic_association_eval(tmp_path / "first")
    second, _ = run_synthetic_association_eval(tmp_path / "second")

    assert first.model_dump(mode="json") == second.model_dump(mode="json")


def test_association_eval_cli_exits_zero_on_pass(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    exit_code = _run_main(monkeypatch, ["association-eval", "--output", str(tmp_path)])
    assert exit_code == 0
    assert (tmp_path / "association-eval.json").exists()


def test_association_eval_gate_fails_when_wrong_association_planted_above_cutoff() -> None:
    """Sabotagem: planta uma associação errada com confiança acima do corte do gate."""
    packet, proposals, ground_truth = build_association_eval_fixture()
    associations = associate_readings(packet, proposals, config=EVAL_CONFIG)

    prox_reading_id = next(
        reading_id for reading_id, proposal_id in ground_truth.items() if proposal_id is not None
    )
    # Descobre a leitura ambígua por proximidade (rd_prox) e planta a associação ERRADA
    # (a segunda linha, não o gabarito) com confiança acima do corte do gate.
    wrong_candidates = [
        candidate
        for candidate in associations.candidates
        if candidate.reading_id in ground_truth
        and ground_truth[candidate.reading_id] is not None
        and candidate.proposal_id != ground_truth[candidate.reading_id]
    ]
    assert wrong_candidates, "fixture deveria ter ao menos um candidato concorrente errado"
    sabotaged = wrong_candidates[0].model_copy(
        update={"association_confidence": ASSOCIATION_EVAL_GATE_THRESHOLD + 0.05}
    )
    poisoned_candidates = [
        sabotaged if candidate is wrong_candidates[0] else candidate
        for candidate in associations.candidates
    ]
    poisoned = associations.model_copy(update={"candidates": poisoned_candidates})

    report = evaluate_association_set(ground_truth, poisoned)

    assert report.passed is False
    assert report.errors_above_gate >= 1
    del prox_reading_id  # só usado para deixar a intenção do teste legível acima


# --- calibration-report: replay local ------------------------------------------------------


def _seed_database(tmp_path: Path) -> str:
    database_url = f"sqlite+pysqlite:///{tmp_path / 'calibration.db'}"
    database = Database(database_url)
    database.create_schema()
    expires_at = datetime.now(UTC) + timedelta(days=7)
    with database.sessions.begin() as session:
        session.add(
            ProjectRecord(
                id="project-calibration",
                tenant_id=TENANT_ID,
                name="Calibração",
                default_unit="m",
                created_by="reviewer",
                expires_at=expires_at,
            )
        )
        session.add(
            UploadRecord(
                id="upload-calibration",
                tenant_id=TENANT_ID,
                object_key=f"tenants/{TENANT_ID}/uploads/upload-calibration/entrada.pdf",
                filename="entrada.pdf",
                content_type="application/pdf",
                size_bytes=1024,
                sha256="a" * 64,
            )
        )
        session.flush()
        session.add(
            JobRecord(
                id=str(JOB_ID),
                tenant_id=TENANT_ID,
                project_id="project-calibration",
                upload_id="upload-calibration",
                status="REVIEW_REQUIRED",
                stage="REVIEWING",
                expires_at=expires_at,
            )
        )
    return database_url


def _reading_json(
    reading_id: str, *, action: str | None, decision_id: str | None, rectifies: str | None = None
) -> dict[str, Any]:
    reading: dict[str, Any] = {
        "id": reading_id,
        "evidence": {
            "dataset_id": "calibration-fixture",
            "page_number": 1,
            "image_sha256": "a" * 64,
            "coordinate_space": "source_image_pixels",
            "bbox": {"left": 0, "top": 0, "right": 10, "bottom": 10},
        },
        "raw_text": "1,00 m",
        "value_si": "1.00" if action is not None else None,
        "unit": "m",
        "kind": "length",
        "written_decimals": 2,
        "extractor": "fixture",
        "extractor_version": "v1",
        "status": "proposed"
        if action is None
        else ("confirmed" if action == "confirm" else "rejected"),
        "decision": None,
    }
    if action is not None:
        reading["decision"] = {
            "decision_id": decision_id,
            "action": action,
            "actor": "human",
            "reviewer_id": "reviewer-01",
            "reviewer_role": "domain_reviewer",
            "decided_at": "2026-01-01T00:00:00+00:00",
            "note": "correção declarada" if rectifies else None,
            "rectifies_decision_id": rectifies,
        }
    return reading


def _association_set_json(candidates: dict[str, str]) -> dict[str, Any]:
    return {
        "schema_version": "1.0.0",
        "dataset_id": "calibration-fixture",
        "page_number": 1,
        "image_sha256": "a" * 64,
        "coordinate_space": "source_image_pixels",
        "associator_version": "pixel-proximity-associator-v1",
        "candidates": [
            {
                "reading_id": reading_id,
                "proposal_id": proposal_id,
                "proposal_kind": "line",
                "relation": "nearest_geometry",
                "pixel_distance": 5.0,
                "proximity_score": 0.9,
                "visual_quality_score": 0.9,
                "orientation_alignment": None,
                "association_confidence": 0.9,
            }
            for reading_id, proposal_id in candidates.items()
        ],
        "unassociated_reading_ids": [],
        "safety_notes": ["fixture local", "sem conteúdo de cliente", "não exportável"],
    }


_POINT_LOW: dict[str, Any] = {"reading_threshold": 0.5, "association_threshold": 0.5}
_POINT_HIGH: dict[str, Any] = {"reading_threshold": 0.9, "association_threshold": 0.9}


def _shadow_json(
    *, auto_choices_low: list[dict[str, Any]], auto_choices_high: list[dict[str, Any]]
) -> dict[str, Any]:
    return {
        "score_version": CONFIDENCE_SCORE_VERSION,
        "reading_confidences": [],
        "decisions": [
            {**_POINT_LOW, "auto_choices": auto_choices_low},
            {**_POINT_HIGH, "auto_choices": auto_choices_high},
        ],
        "readings_total": 3,
        "readings_with_candidate": 3,
    }


def _choice(
    reading_id: str, proposal_id: str, *, reading_confidence: float, association_confidence: float
) -> dict[str, Any]:
    return {
        "reading_id": reading_id,
        "proposal_id": proposal_id,
        "reading_confidence": reading_confidence,
        "association_confidence": association_confidence,
    }


RD_0 = "rd_" + "0" * 16  # nasce JÁ decidida na v1 (caso "não deveria acontecer") — inelegível
RD_1 = "rd_" + "1" * 16  # confirmada em v2, depois RETIFICADA para rejeitada em v3
RD_2 = "rd_" + "2" * 16  # confirmada com associação DIFERENTE da que o auto teria escolhido
RD_3 = "rd_" + "3" * 16  # rejeitada desde a primeira decisão (v2)
RD_4 = "rd_" + "4" * 16  # regressão do viés de look-ahead: só "auto-decidível" DEPOIS do ato
VP_A = "vp_" + "a" * 16
VP_B = "vp_" + "b" * 16
VP_C = "vp_" + "c" * 16
VP_D = "vp_" + "d" * 16
VP_ZERO = "vp_" + "0" * 16


def _seed_known_revisions(tmp_path: Path) -> str:
    """Três revisões de um job: 4 leituras com verdade humana (+ 1 caso-limite inelegível).

    v1: todas as leituras ainda PROPOSED, exceto `rd_0` — que já nasce decidida na
    primeira revisão do job, o caso "não deveria acontecer" que `_birth_entries` recusa
    por falta de um estado anterior (fica de fora de `readings_with_truth`).

    v2: primeira decisão humana de `rd_1` (confirm, vp_a — igual ao que o corte permissivo
    escolheria), `rd_2` (confirm vp_b — o corte permissivo escolheria vp_a: erro de
    ASSOCIAÇÃO plantado de propósito), `rd_3` (reject — erro de LEITURA) e `rd_4` (confirm
    vp_d). A verdade das quatro é medida contra o shadow de v1 (a revisão ANTERIOR), nunca
    contra o de v2: `rd_4` é o caso que prova isso — seu shadow em v1 (pré-decisão) NÃO a
    lista como auto-decidível no corte permissivo, mas seu shadow em v2 (pós-decisão, como
    se a própria confirmação tivesse fechado uma cadeia que corroborou a leitura) já a
    listaria. Se o relatório usasse o shadow de nascimento (o bug do finding), `rd_4`
    entraria erradamente no `auto_decidable_count`.

    v3: retifica `rd_1` para rejeitada. A verdade vigente de `rd_1` passa a viver em v3,
    medida contra o shadow de v2 (a revisão imediatamente anterior a v3) — não o de v1.
    """
    database_url = _seed_database(tmp_path)
    database = Database(database_url)

    rd0_reading = _reading_json(RD_0, action="confirm", decision_id="hd_" + "0" * 16)
    packet_v1: dict[str, Any] = {
        "schema_version": "1.1.0",
        "dataset_id": "calibration-fixture",
        "page_number": 1,
        "image_sha256": "a" * 64,
        "region_candidates": [],
        "readings": [
            rd0_reading,
            _reading_json(RD_1, action=None, decision_id=None),
            _reading_json(RD_2, action=None, decision_id=None),
            _reading_json(RD_3, action=None, decision_id=None),
            _reading_json(RD_4, action=None, decision_id=None),
        ],
        "safety_status": "human_review_required",
        "safety_notes": ["fixture local", "sem conteúdo de cliente"],
    }
    rd1_confirmed = _reading_json(RD_1, action="confirm", decision_id="hd_" + "1" * 16)
    rd2_confirmed = _reading_json(RD_2, action="confirm", decision_id="hd_" + "2" * 16)
    rd3_rejected = _reading_json(RD_3, action="reject", decision_id="hd_" + "3" * 16)
    rd4_confirmed = _reading_json(RD_4, action="confirm", decision_id="hd_" + "5" * 16)
    packet_v2: dict[str, Any] = {
        **packet_v1,
        "readings": [rd0_reading, rd1_confirmed, rd2_confirmed, rd3_rejected, rd4_confirmed],
    }
    rd1_rectified = _reading_json(
        RD_1, action="reject", decision_id="hd_" + "4" * 16, rectifies="hd_" + "1" * 16
    )
    packet_v3: dict[str, Any] = {
        **packet_v1,
        "readings": [rd0_reading, rd1_rectified, rd2_confirmed, rd3_rejected, rd4_confirmed],
    }
    associations_json = _association_set_json(
        {RD_0: VP_ZERO, RD_1: VP_A, RD_2: VP_A, RD_3: VP_C, RD_4: VP_D}
    )
    shadow_v1 = _shadow_json(
        auto_choices_low=[
            _choice(RD_1, VP_A, reading_confidence=0.9, association_confidence=0.85),
            _choice(RD_2, VP_A, reading_confidence=0.7, association_confidence=0.6),
            _choice(RD_3, VP_C, reading_confidence=0.65, association_confidence=0.55),
            # rd_4 AUSENTE de propósito: pré-decisão, o corte permissivo ainda não a
            # auto-decidiria — é o estado honesto que o relatório deve enxergar.
        ],
        auto_choices_high=[
            _choice(RD_1, VP_A, reading_confidence=0.95, association_confidence=0.92),
        ],
    )
    shadow_v2 = _shadow_json(
        auto_choices_low=[
            _choice(RD_1, VP_A, reading_confidence=0.9, association_confidence=0.85),
            _choice(RD_2, VP_A, reading_confidence=0.7, association_confidence=0.6),
            _choice(RD_3, VP_C, reading_confidence=0.65, association_confidence=0.55),
            # rd_4 presente aqui, PÓS a própria confirmação (ex.: cadeia que só fechou
            # porque a leitura foi confirmada) — é o shadow "contaminado" que o relatório
            # NÃO deve usar para julgar a decisão nascida em v2. É usado, sim, como
            # estado ANTERIOR da retificação de rd_1 nascida em v3.
            _choice(RD_4, VP_D, reading_confidence=0.85, association_confidence=0.8),
        ],
        auto_choices_high=[
            _choice(RD_1, VP_A, reading_confidence=0.95, association_confidence=0.92),
        ],
    )
    with database.sessions.begin() as session:
        session.add(
            ReviewRevisionRecord(
                id="review-v1",
                tenant_id=TENANT_ID,
                job_id=str(JOB_ID),
                version=1,
                parent_review_id=None,
                packet_json=packet_v1,
                associations_json=associations_json,
                selected_associations_json={RD_0: VP_ZERO},
                confidence_shadow_json=shadow_v1,
                created_by="reviewer-01",
            )
        )
        session.add(
            ReviewRevisionRecord(
                id="review-v2",
                tenant_id=TENANT_ID,
                job_id=str(JOB_ID),
                version=2,
                parent_review_id="review-v1",
                packet_json=packet_v2,
                associations_json=associations_json,
                selected_associations_json={
                    RD_0: VP_ZERO,
                    RD_1: VP_A,
                    RD_2: VP_B,
                    RD_4: VP_D,
                },
                confidence_shadow_json=shadow_v2,
                created_by="reviewer-01",
            )
        )
        session.add(
            ReviewRevisionRecord(
                id="review-v3",
                tenant_id=TENANT_ID,
                job_id=str(JOB_ID),
                version=3,
                parent_review_id="review-v2",
                packet_json=packet_v3,
                associations_json=associations_json,
                selected_associations_json={RD_0: VP_ZERO, RD_2: VP_B, RD_4: VP_D},
                confidence_shadow_json=shadow_v2,  # nunca lida (não há v4); só preenche o schema
                created_by="reviewer-01",
            )
        )
    return database_url


def test_calibration_report_produces_expected_rates(tmp_path: Path) -> None:
    database_url = _seed_known_revisions(tmp_path)

    report, report_path, table_path = run_calibration_report(database_url, tmp_path / "out")

    assert report.jobs_considered == 1
    assert report.revisions_considered == 3
    # rd_0 (nascida na v1, sem revisão anterior) fica de fora: 4, não 5.
    assert report.readings_with_truth == 4
    assert report_path.exists()
    assert table_path.exists()

    assert [version.score_version for version in report.score_versions] == [
        CONFIDENCE_SCORE_VERSION
    ]
    version_report = report.score_versions[0]
    assert version_report.eligible_reading_count == 4

    rows_by_threshold = {
        (row.reading_threshold, row.association_threshold): row for row in version_report.rows
    }
    low = rows_by_threshold[(0.5, 0.5)]
    # rd_1 (via shadow de v2, sua revisão ANTERIOR), rd_2 (confirm errado, via shadow de
    # v1) e rd_3 (reject, via shadow de v1) auto-decidíveis no corte permissivo; rd_4 NÃO
    # — prova de que o relatório usou o shadow PRÉ-decisão (v1), não o de nascimento (v2),
    # onde rd_4 apareceria.
    assert low.auto_decidable_count == 3
    assert low.auto_rate == pytest.approx(0.75)
    assert low.review_rate == pytest.approx(0.25)
    assert low.confirm_auto_decidable_count == 1
    assert low.association_error_count == 1
    assert low.association_error_rate == pytest.approx(1.0)
    assert low.reading_error_count == 2
    assert low.reading_error_rate == pytest.approx(round(2 / 3, 4))

    high = rows_by_threshold[(0.9, 0.9)]
    # Só rd_1 (via shadow de v2) segue auto-decidível no corte exigente.
    assert high.auto_decidable_count == 1
    assert high.auto_rate == pytest.approx(0.25)
    assert high.review_rate == pytest.approx(0.75)
    assert high.confirm_auto_decidable_count == 0
    assert high.association_error_count == 0
    assert high.association_error_rate is None
    assert high.reading_error_count == 1
    assert high.reading_error_rate == pytest.approx(1.0)


def test_calibration_report_raises_without_eligible_data(tmp_path: Path) -> None:
    database_url = _seed_database(tmp_path)

    with pytest.raises(CalibrationReportError) as excinfo:
        run_calibration_report(database_url, tmp_path / "out")
    assert excinfo.value.code == "NO_ELIGIBLE_DATA"


def test_calibration_report_cli_exits_two_without_eligible_data(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database_url = _seed_database(tmp_path)
    monkeypatch.setenv("CROQUITO_DATABASE_URL", database_url)

    exit_code = _run_main(monkeypatch, ["calibration-report", "--output", str(tmp_path / "out")])
    assert exit_code == 2


def test_calibration_report_cli_exits_two_without_database_url(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("CROQUITO_DATABASE_URL", raising=False)

    exit_code = _run_main(monkeypatch, ["calibration-report", "--output", str(tmp_path / "out")])
    assert exit_code == 2
