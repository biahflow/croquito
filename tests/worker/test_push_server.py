"""Receptor push: o transporte muda, o despacho e a semântica de reentrega não."""

import base64
import hashlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast

import pytest
from fastapi.testclient import TestClient

from croquito_api.database import Database, JobRecord, ProjectRecord, UploadRecord
from croquito_worker.local_queue import LocalQueueWorker, LocalWorkerSettings
from croquito_worker.push_server import create_push_app
from tests.fakes import FakeObjectStore, synthetic_pdf

JOB_ID = "00000000-0000-7000-8000-000000000021"
OBJECT_KEY = "tenants/tenant-push/uploads/push.pdf"


def _seed(tmp_path: Path, *, pdf: bytes) -> tuple[Database, str]:
    database_url = f"sqlite+pysqlite:///{tmp_path / 'push.db'}"
    database = Database(database_url)
    database.create_schema()
    expires_at = datetime.now(UTC) + timedelta(days=7)
    with database.sessions.begin() as session:
        session.add(
            ProjectRecord(
                id="project-push",
                tenant_id="tenant-push",
                name="Push",
                default_unit="m",
                created_by="reviewer",
                expires_at=expires_at,
            )
        )
        session.add(
            UploadRecord(
                id="upload-push",
                tenant_id="tenant-push",
                object_key=OBJECT_KEY,
                filename="push.pdf",
                content_type="application/pdf",
                size_bytes=len(pdf),
                sha256=hashlib.sha256(pdf).hexdigest(),
            )
        )
        session.flush()
        session.add(
            JobRecord(
                id=JOB_ID,
                tenant_id="tenant-push",
                project_id="project-push",
                upload_id="upload-push",
                status="UPLOADED",
                stage="VALIDATING",
                expires_at=expires_at,
            )
        )
    return database, database_url


def _client(database_url: str, *, storage: FakeObjectStore) -> TestClient:
    application = create_push_app(
        LocalWorkerSettings(
            database_url=database_url,
            queue_url="",
            aws_region="sa-east-1",
            aws_endpoint_url="http://localstack",
        )
    )
    worker = cast(LocalQueueWorker, application.state.worker)
    worker.s3_client = storage
    # `raise_server_exceptions=False` deixa a falha virar 500 observável, como no Cloud Run.
    return TestClient(application, raise_server_exceptions=False)


def _envelope(body: Any, *, raw: str | None = None) -> dict[str, Any]:
    data = (
        raw
        if raw is not None
        else base64.b64encode(json.dumps(body).encode("utf-8")).decode("ascii")
    )
    return {
        "message": {
            "data": data,
            "messageId": "12345",
            "publishTime": "2026-08-14T12:00:00Z",
        },
        "subscription": "projects/croquito-hml/subscriptions/processing-push",
    }


def test_valid_envelope_dispatches_and_acks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "local")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "local")
    pdf = synthetic_pdf()
    database, database_url = _seed(tmp_path, pdf=pdf)
    storage = FakeObjectStore()
    storage.put_direct(object_key=OBJECT_KEY, body=pdf)
    client = _client(database_url, storage=storage)

    response = client.post(
        "/pubsub",
        json=_envelope({"command": "process_upload", "job_id": JOB_ID, "tenant_id": "tenant-push"}),
    )

    assert response.status_code == 204
    with database.sessions() as session:
        job = session.get(JobRecord, JOB_ID)
        assert job is not None
        assert job.status == "REVIEW_REQUIRED"


def test_poison_payloads_are_acked_without_effect(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Reentregar um payload que nunca vai executar é um ciclo caro; ele é descartado."""
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "local")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "local")
    pdf = synthetic_pdf()
    database, database_url = _seed(tmp_path, pdf=pdf)
    storage = FakeObjectStore()
    storage.put_direct(object_key=OBJECT_KEY, body=pdf)
    client = _client(database_url, storage=storage)

    responses = [
        client.post("/pubsub", json=_envelope(None, raw="isto-não-é-base64!!")),
        client.post(
            "/pubsub",
            json=_envelope(None, raw=base64.b64encode(b"{nao e json").decode("ascii")),
        ),
        client.post("/pubsub", json=_envelope([1, 2, 3])),
        client.post(
            "/pubsub",
            json=_envelope(
                {"command": "delete_everything", "job_id": JOB_ID, "tenant_id": "tenant-push"}
            ),
        ),
        client.post(
            "/pubsub",
            json=_envelope({"command": "process_upload", "tenant_id": "tenant-push"}),
        ),
        client.post("/pubsub", json={"subscription": "sem-mensagem"}),
    ]

    assert [response.status_code for response in responses] == [200] * 6
    with database.sessions() as session:
        job = session.get(JobRecord, JOB_ID)
        assert job is not None
        assert job.status == "UPLOADED"


def test_infrastructure_failure_returns_500_so_pubsub_redelivers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "local")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "local")
    pdf = synthetic_pdf()
    database, database_url = _seed(tmp_path, pdf=pdf)
    # Storage sem o objeto: o worker levanta a falha transitória do object store.
    client = _client(database_url, storage=FakeObjectStore())

    response = client.post(
        "/pubsub",
        json=_envelope({"command": "process_upload", "job_id": JOB_ID, "tenant_id": "tenant-push"}),
    )

    assert response.status_code == 500
    with database.sessions() as session:
        job = session.get(JobRecord, JOB_ID)
        assert job is not None
        assert job.status == "UPLOADED"
