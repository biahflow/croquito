import json
import zipfile
from datetime import UTC, datetime, timedelta
from io import BytesIO
from pathlib import Path
from typing import Any

import pytest

from croquito_api.database import (
    ApprovalRecord,
    Database,
    ExportArtifactRecord,
    JobRecord,
    ProjectRecord,
    RevisionRecord,
    UploadRecord,
)
from croquito_core.models import SceneRevision
from croquito_worker.local_queue import LocalQueueWorker, LocalWorkerSettings
from croquito_worker.synthetic import build_synthetic_scene
from tests.fakes import FakeObjectStore, FakeQueue

JOB_ID = "00000000-0000-7000-8000-000000000801"
EXPORT_ID = "00000000-0000-7000-8000-000000000802"
TENANT_ID = "tenant-export"


def _seed(tmp_path: Path, *, approved: bool) -> tuple[Database, str]:
    database_url = f"sqlite+pysqlite:///{tmp_path / 'export.db'}"
    database = Database(database_url)
    database.create_schema()
    scene = build_synthetic_scene()
    if not approved:
        scene = SceneRevision.model_validate({**scene.model_dump(mode="json"), "approved": False})
    expires_at = datetime.now(UTC) + timedelta(days=7)
    with database.sessions.begin() as session:
        session.add(
            ProjectRecord(
                id="project-export",
                tenant_id=TENANT_ID,
                name="Export",
                default_unit="m",
                created_by="reviewer",
                expires_at=expires_at,
            )
        )
        session.add(
            UploadRecord(
                id="upload-export",
                tenant_id=TENANT_ID,
                object_key=f"tenants/{TENANT_ID}/uploads/upload-export/entrada.pdf",
                filename="entrada.pdf",
                content_type="application/pdf",
                size_bytes=1024,
                sha256="e" * 64,
            )
        )
        session.flush()
        session.add(
            JobRecord(
                id=JOB_ID,
                tenant_id=TENANT_ID,
                project_id="project-export",
                upload_id="upload-export",
                status="EXPORTING",
                stage="EXPORTING",
                expires_at=expires_at,
            )
        )
        session.flush()
        session.add(
            RevisionRecord(
                id=str(scene.id),
                tenant_id=TENANT_ID,
                job_id=JOB_ID,
                version=scene.version,
                scene=scene.model_dump(mode="json"),
                created_by="reviewer",
            )
        )
        session.flush()
        session.add(
            ApprovalRecord(
                id="approval-export",
                tenant_id=TENANT_ID,
                job_id=JOB_ID,
                source_revision_id=str(scene.id),
                approved_revision_id=str(scene.id),
                reviewer_id="reviewer",
                reviewer_roles=["engineer"],
                acknowledgement="Cena revisada e limitações reconhecidas.",
                approval_json={
                    "source_scene_id": str(scene.id),
                    "approval_id": "ap_" + "a" * 16,
                    "action": "approve",
                    "reviewer_id": "reviewer",
                    "reviewer_role": "engineer",
                    "decided_at": datetime.now(UTC).isoformat(),
                    "source_evidence_checked": True,
                    "geometry_checked": True,
                    "limitations_acknowledged": True,
                    "statement": "Cena cobre apenas o campo principal revisado.",
                    "acknowledged_criteria": ["ACC_GUA_001"],
                },
            )
        )
        session.flush()
        session.add(
            ExportArtifactRecord(
                id=EXPORT_ID,
                tenant_id=TENANT_ID,
                job_id=JOB_ID,
                scene_revision_id=str(scene.id),
                approval_id="approval-export",
                format="dxf",
                status="QUEUED",
                requested_by="reviewer",
            )
        )
    return database, database_url


def _worker(database_url: str, body: dict[str, Any]) -> tuple[LocalQueueWorker, FakeObjectStore]:
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
    storage = FakeObjectStore()
    worker.s3_client = storage
    return worker, storage


def _message(**overrides: Any) -> dict[str, Any]:
    return {
        "command": "export_scene_package",
        "export_id": EXPORT_ID,
        "job_id": JOB_ID,
        "tenant_id": TENANT_ID,
        **overrides,
    }


def test_export_publishes_audited_package_with_the_approval(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "local")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "local")
    database, database_url = _seed(tmp_path, approved=True)
    worker, storage = _worker(database_url, _message())

    assert worker.run_once() == 1

    with database.sessions() as session:
        artifact = session.get(ExportArtifactRecord, EXPORT_ID)
        assert artifact is not None
        assert artifact.status == "COMPLETED"
        assert artifact.audit_status == "approved"
        assert artifact.dxf_sha256 is not None
        assert artifact.package_object_key == (
            f"tenants/{TENANT_ID}/jobs/{JOB_ID}/exports/{EXPORT_ID}/croquito.zip"
        )
        job = session.get(JobRecord, JOB_ID)
        assert job is not None
        assert job.status == "COMPLETED"
    assert len(storage.puts) == 1
    assert storage.puts[0]["ContentType"] == "application/zip"
    assert storage.puts[0]["ServerSideEncryption"] == "AES256"
    with zipfile.ZipFile(BytesIO(storage.puts[0]["Body"])) as package:
        assert sorted(package.namelist()) == [
            "aprovacao.json",
            "auditoria.json",
            "desenho.dxf",
            "hipoteses.json",
            "preview.png",
            "quantitativos.csv",
        ]
        approval = json.loads(package.read("aprovacao.json"))
        assert approval["limitations_acknowledged"] is True
        assert approval["acknowledged_criteria"] == ["ACC_GUA_001"]


def test_export_replay_does_not_republish_a_completed_package(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "local")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "local")
    database, database_url = _seed(tmp_path, approved=True)
    worker, storage = _worker(database_url, _message())
    assert worker.run_once() == 1

    replay, replay_storage = _worker(database_url, _message())
    assert replay.run_once() == 1

    assert replay_storage.puts == []
    with database.sessions() as session:
        artifact = session.get(ExportArtifactRecord, EXPORT_ID)
        assert artifact is not None
        assert artifact.status == "COMPLETED"
    assert len(storage.puts) == 1


def test_export_of_unapproved_scene_fails_closed_without_publishing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "local")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "local")
    database, database_url = _seed(tmp_path, approved=False)
    worker, storage = _worker(database_url, _message())

    assert worker.run_once() == 1

    assert storage.puts == []
    with database.sessions() as session:
        artifact = session.get(ExportArtifactRecord, EXPORT_ID)
        assert artifact is not None
        assert artifact.status == "FAILED"
        assert artifact.failure_code == "EXPORT_AUDIT_FAILED"
        assert artifact.package_object_key is None
        assert artifact.audit_json is not None
        assert "SCENE_NOT_APPROVED" in artifact.audit_json["errors"]
        job = session.get(JobRecord, JOB_ID)
        assert job is not None
        assert job.status == "FAILED"


def test_export_refuses_a_message_from_another_tenant(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "local")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "local")
    _database, database_url = _seed(tmp_path, approved=True)
    worker, storage = _worker(database_url, _message(tenant_id="tenant-other"))

    with pytest.raises(ValueError):
        worker.run_once()

    assert storage.puts == []


def test_unknown_command_is_refused(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "local")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "local")
    _database, database_url = _seed(tmp_path, approved=True)
    worker, _storage = _worker(database_url, _message(command="delete_everything"))

    with pytest.raises(ValueError):
        worker.run_once()


def test_export_id_is_required_for_the_export_command(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "local")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "local")
    _database, database_url = _seed(tmp_path, approved=True)
    body = _message()
    del body["export_id"]
    worker, _storage = _worker(database_url, body)

    with pytest.raises(ValueError):
        worker.run_once()
