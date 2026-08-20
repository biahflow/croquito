"""O aceite em lote do traçado é resolvido pelo worker, uma vez por comando.

Cada teste cobre um desfecho do contrato: cena nova quando o aceite fecha, blockers sem
revisão quando falta ato humano, conflito consultável quando a revisão andou e replay
sem efeito quando a mensagem volta.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from croquito_api.database import (
    Database,
    JobRecord,
    ProjectRecord,
    ReviewRevisionRecord,
    RevisionRecord,
    TraceSolveRecord,
    UploadRecord,
)
from croquito_core.models import SceneRevision
from croquito_worker.local_queue import LocalQueueWorker, LocalWorkerSettings
from croquito_worker.tracing import TraceAcceptance
from tests.bundles import (
    CIRCLE_PROPOSAL_ID,
    CIRCLE_READING_ID,
    HEIGHT_PROPOSAL_ID,
    HEIGHT_READING_ID,
    WIDTH_PROPOSAL_ID,
    WIDTH_READING_ID,
    build_associations,
    build_packet,
    build_proposals,
)
from tests.fakes import FakeObjectStore, FakeQueue

JOB_ID = "00000000-0000-7000-8000-000000000901"
REVIEW_ID = "00000000-0000-7000-8000-000000000902"
TRACE_SOLVE_ID = "00000000-0000-7000-8000-000000000903"
TENANT_ID = "tenant-trace"
DATASET_ID = "synthetic-trace-v1"
DIGEST = "c" * 64


def _acceptance() -> TraceAcceptance:
    return TraceAcceptance(
        acceptance_id="ta_" + "1" * 16,
        reviewer_id="eng-trace",
        reviewer_role="engineer",
        decided_at=datetime(2026, 8, 12, 12, 0, tzinfo=UTC),
        note="Traçado conferido contra a evidência protegida.",
        proposal_ids=[WIDTH_PROPOSAL_ID, HEIGHT_PROPOSAL_ID, CIRCLE_PROPOSAL_ID],
        unlabelled_proposal_ids=[CIRCLE_PROPOSAL_ID],
    )


def _seed(
    tmp_path: Path,
    *,
    confirmed: bool = True,
    required_criteria: list[str] | None = None,
    criteria_texts: dict[str, str] | None = None,
) -> tuple[Database, str]:
    database_url = f"sqlite+pysqlite:///{tmp_path / 'trace.db'}"
    database = Database(database_url)
    database.create_schema()
    packet = build_packet(dataset_id=DATASET_ID, digest=DIGEST, decided=confirmed)
    associations = build_associations(dataset_id=DATASET_ID, digest=DIGEST)
    proposals = build_proposals(dataset_id=DATASET_ID, digest=DIGEST)
    expires_at = datetime.now(UTC) + timedelta(days=7)
    with database.sessions.begin() as session:
        session.add(
            ProjectRecord(
                id="project-trace",
                tenant_id=TENANT_ID,
                name="Traçado",
                default_unit="m",
                created_by="reviewer",
                expires_at=expires_at,
            )
        )
        session.add(
            UploadRecord(
                id="upload-trace",
                tenant_id=TENANT_ID,
                object_key=f"tenants/{TENANT_ID}/uploads/upload-trace/entrada.pdf",
                filename="entrada.pdf",
                content_type="application/pdf",
                size_bytes=1024,
                sha256="d" * 64,
            )
        )
        session.flush()
        session.add(
            JobRecord(
                id=JOB_ID,
                tenant_id=TENANT_ID,
                project_id="project-trace",
                upload_id="upload-trace",
                status="REVIEW_REQUIRED",
                stage="PREVIEWING",
                expires_at=expires_at,
            )
        )
        session.flush()
        session.add(
            ReviewRevisionRecord(
                id=REVIEW_ID,
                tenant_id=TENANT_ID,
                job_id=JOB_ID,
                version=1,
                packet_json=packet.model_dump(mode="json"),
                associations_json=associations.model_dump(mode="json"),
                proposals_json=proposals.model_dump(mode="json"),
                selected_associations_json={
                    WIDTH_READING_ID: WIDTH_PROPOSAL_ID,
                    HEIGHT_READING_ID: HEIGHT_PROPOSAL_ID,
                },
                evidence_refs_json={"source_image_key": f"tenants/{TENANT_ID}/review/source.png"},
                required_blocker_codes_json=required_criteria or [],
                required_criteria_texts_json=criteria_texts,
                created_by="local-worker",
            )
        )
        session.flush()
        session.add(
            TraceSolveRecord(
                id=TRACE_SOLVE_ID,
                tenant_id=TENANT_ID,
                job_id=JOB_ID,
                base_review_revision_id=REVIEW_ID,
                base_scene_revision_id=None,
                status="QUEUED",
                acceptance_id=_acceptance().acceptance_id,
                acceptance_json=_acceptance().model_dump(mode="json"),
                associations_json={
                    WIDTH_READING_ID: WIDTH_PROPOSAL_ID,
                    HEIGHT_READING_ID: HEIGHT_PROPOSAL_ID,
                },
                title="TRACADO SINTETICO",
                feature_id="tracado",
                requested_by="eng-trace",
            )
        )
    return database, database_url


def _worker(database_url: str, body: dict[str, Any]) -> tuple[LocalQueueWorker, FakeQueue]:
    worker = LocalQueueWorker(
        LocalWorkerSettings(
            database_url=database_url,
            queue_url="http://localstack/queue",
            aws_region="sa-east-1",
            aws_endpoint_url="http://localstack",
        )
    )
    queue = FakeQueue()
    queue.send_message(MessageBody=json.dumps(body))
    worker.client = queue
    worker.s3_client = FakeObjectStore()
    return worker, queue


def _message(**overrides: Any) -> dict[str, Any]:
    return {
        "command": "solve_trace_scene",
        "trace_solve_id": TRACE_SOLVE_ID,
        "job_id": JOB_ID,
        "tenant_id": TENANT_ID,
        **overrides,
    }


def test_trace_solve_creates_the_scene_and_records_the_acceptance(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "local")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "local")
    database, database_url = _seed(tmp_path)
    declared_chains = [
        {
            "chain_id": "ch_0123456789abcdef",
            "total_id": WIDTH_READING_ID,
            "part_ids": [HEIGHT_READING_ID, CIRCLE_READING_ID],
            "declared_by": "eng-trace",
            "declared_role": "engineer",
            "declared_at": "2026-08-20T12:00:00+00:00",
        }
    ]
    with database.sessions.begin() as session:
        base = session.get(ReviewRevisionRecord, REVIEW_ID)
        assert base is not None
        base.declared_chains_json = declared_chains
    worker, queue = _worker(database_url, _message())

    assert worker.run_once() == 1

    with database.sessions() as session:
        record = session.get(TraceSolveRecord, TRACE_SOLVE_ID)
        assert record is not None
        assert record.status == "COMPLETED"
        assert record.solve_status == "solved_unapproved"
        assert record.blockers_json == []
        assert record.failure_code is None
        assert record.exact_entity_count == 2
        assert record.approximate_entity_count == 1
        assert record.scale_m_per_px is not None and record.scale_m_per_px > 0
        assert record.residual_summary_json is not None
        assert record.residual_summary_json["count"] == 2
        assert record.residual_summary_json["failed_count"] == 0

        scene_record = session.get(RevisionRecord, record.result_scene_revision_id)
        assert scene_record is not None
        # A primeira cena métrica do job nasce do traçado, não aprovada.
        assert scene_record.version == 1
        assert scene_record.job_id == JOB_ID
        assert scene_record.scene["approved"] is False
        assert scene_record.parent_revision_id is None

        review_record = session.get(ReviewRevisionRecord, record.result_review_revision_id)
        assert review_record is not None
        assert review_record.version == 2
        assert review_record.parent_review_id == REVIEW_ID
        assert review_record.scene_revision_id == scene_record.id
        assert review_record.trace_acceptance_json is not None
        acceptance = review_record.trace_acceptance_json["acceptance"]
        assert acceptance["acceptance_id"] == _acceptance().acceptance_id
        assert acceptance["reviewer_id"] == "eng-trace"
        assert review_record.trace_acceptance_json["scene_revision_id"] == scene_record.id
        # A cadeia declarada é ato humano sobre cotas: o traçado não decide cota nenhuma
        # e não pode fazê-la evaporar na revisão que ele cria.
        assert review_record.declared_chains_json == declared_chains
        base_record = session.get(ReviewRevisionRecord, REVIEW_ID)
        assert base_record is not None
        # O snapshot da revisão continua íntegro: o traçado não reescreve evidência.
        assert review_record.packet_json == base_record.packet_json
        assert review_record.proposals_json == base_record.proposals_json
    assert queue.deleted == ["receipt-1"]


def test_trace_solve_materialises_the_scope_criterion_of_the_review(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Paridade com o solver retangular: a cena traçada carrega o critério do caso."""
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "local")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "local")
    criterion_text = "Muros, portões e patamares usam layers distintos."
    database, database_url = _seed(
        tmp_path,
        required_criteria=["ACC_GUA_002"],
        criteria_texts={"ACC_GUA_002": criterion_text},
    )
    worker, _queue = _worker(database_url, _message())

    assert worker.run_once() == 1

    with database.sessions() as session:
        record = session.get(TraceSolveRecord, TRACE_SOLVE_ID)
        assert record is not None
        assert record.solve_status == "solved_unapproved"
        scene_record = session.get(RevisionRecord, record.result_scene_revision_id)
        assert scene_record is not None
        criterion = next(
            issue for issue in scene_record.scene["issues"] if issue["code"] == "ACC_GUA_002"
        )
        assert criterion["severity"] == "critical"
        assert criterion["status"] == "open"
        assert criterion["message"] == criterion_text
        # A cena traçada não é exportável enquanto o critério não for declarado.
        assert SceneRevision.model_validate(scene_record.scene).export_errors() == [
            "SCENE_NOT_APPROVED",
            "OPEN_CRITICAL_ISSUE:ACC_GUA_002",
        ]
        review_record = session.get(ReviewRevisionRecord, record.result_review_revision_id)
        assert review_record is not None
        # A revisão criada pelo traçado propaga código e texto sem reescrevê-los.
        assert review_record.required_blocker_codes_json == ["ACC_GUA_002"]
        assert review_record.required_criteria_texts_json == {"ACC_GUA_002": criterion_text}


def test_trace_solve_without_human_confirmation_records_blockers_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "local")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "local")
    database, database_url = _seed(tmp_path, confirmed=False)
    worker, _queue = _worker(database_url, _message())

    assert worker.run_once() == 1

    with database.sessions() as session:
        record = session.get(TraceSolveRecord, TRACE_SOLVE_ID)
        assert record is not None
        assert record.status == "COMPLETED"
        assert record.solve_status == "review_required"
        assert any(
            blocker.startswith("TRACE_HUMAN_CONFIRMATION_REQUIRED")
            for blocker in record.blockers_json
        )
        assert record.result_scene_revision_id is None
        assert record.result_review_revision_id is None
        # Nenhuma cena e nenhuma revisão nova: leitura sem decisão não vira geometria.
        assert session.query(RevisionRecord).count() == 0
        assert session.query(ReviewRevisionRecord).count() == 1


def test_trace_solve_records_conflict_when_the_review_moved(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "local")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "local")
    database, database_url = _seed(tmp_path)
    with database.sessions.begin() as session:
        base = session.get(ReviewRevisionRecord, REVIEW_ID)
        assert base is not None
        session.add(
            ReviewRevisionRecord(
                id="00000000-0000-7000-8000-000000000904",
                tenant_id=TENANT_ID,
                job_id=JOB_ID,
                version=2,
                parent_review_id=REVIEW_ID,
                packet_json=base.packet_json,
                associations_json=base.associations_json,
                proposals_json=base.proposals_json,
                selected_associations_json=base.selected_associations_json,
                evidence_refs_json=base.evidence_refs_json,
                required_blocker_codes_json=[],
                created_by="outra-decisao",
            )
        )
    worker, queue = _worker(database_url, _message())

    assert worker.run_once() == 1

    with database.sessions() as session:
        record = session.get(TraceSolveRecord, TRACE_SOLVE_ID)
        assert record is not None
        # Conflito é resultado consultável, não exceção nem 500.
        assert record.status == "COMPLETED"
        assert record.solve_status == "conflict"
        assert record.failure_code == "REVISION_MOVED"
        assert record.result_scene_revision_id is None
        assert session.query(RevisionRecord).count() == 0
    assert queue.deleted == ["receipt-1"]


def test_trace_solve_replay_does_not_create_a_second_scene(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "local")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "local")
    database, database_url = _seed(tmp_path)
    worker, _queue = _worker(database_url, _message())
    assert worker.run_once() == 1

    replay, replay_queue = _worker(database_url, _message())
    assert replay.run_once() == 1

    with database.sessions() as session:
        assert session.query(RevisionRecord).count() == 1
        assert session.query(ReviewRevisionRecord).count() == 2
        record = session.get(TraceSolveRecord, TRACE_SOLVE_ID)
        assert record is not None
        assert record.status == "COMPLETED"
    assert replay_queue.deleted == ["receipt-1"]


def test_trace_solve_refuses_a_message_from_another_tenant(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "local")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "local")
    database, database_url = _seed(tmp_path)
    worker, _queue = _worker(database_url, _message(tenant_id="tenant-other"))

    with pytest.raises(ValueError):
        worker.run_once()

    with database.sessions() as session:
        assert session.query(RevisionRecord).count() == 0


def test_trace_solve_id_is_required_for_the_trace_command(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "local")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "local")
    _database, database_url = _seed(tmp_path)
    body = _message()
    del body["trace_solve_id"]
    worker, _queue = _worker(database_url, body)

    with pytest.raises(ValueError):
        worker.run_once()
