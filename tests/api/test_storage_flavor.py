"""Storage flavor: o que a AWS assina e o GCS recusa, decidido por configuração."""

import base64
import hashlib
from dataclasses import replace
from pathlib import Path
from typing import Any, cast

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from croquito_api.config import ApiSettings
from croquito_api.database import AuditRecord, Database
from croquito_api.main import create_app
from croquito_api.storage import ArtifactStore, UploadedObject
from croquito_core.errors import DomainValidationError
from tests.fakes import FakeObjectStore, synthetic_pdf


class RecordingS3Client:
    """Registra os parâmetros que o `ArtifactStore` monta, sem falar com nuvem nenhuma."""

    def __init__(self) -> None:
        self.presign_params: list[dict[str, Any]] = []
        self.head_params: list[dict[str, Any]] = []
        self.head_response: dict[str, Any] = {
            "ContentLength": 1024,
            "ContentType": "application/pdf",
            "ChecksumSHA256": "Zm9v",
        }

    def generate_presigned_url(self, operation: str, **kwargs: Any) -> str:
        self.presign_params.append(dict(kwargs["Params"]))
        return f"https://storage.invalid/{operation}"

    def head_object(self, **kwargs: Any) -> dict[str, Any]:
        self.head_params.append(dict(kwargs))
        return self.head_response


class GcsObjectStore(FakeObjectStore):
    """Dublê do storage GCS: guarda os bytes, mas não devolve checksum próprio."""

    def head_upload(self, *, object_key: str) -> UploadedObject | None:
        stored = super().head_upload(object_key=object_key)
        if stored is None:
            return None
        return UploadedObject(
            content_length=stored.content_length,
            content_type=stored.content_type,
            checksum_sha256=None,
        )


def _settings(tmp_path: Path, *, flavor: str = "s3") -> ApiSettings:
    return ApiSettings(
        database_url=f"sqlite+pysqlite:///{tmp_path / 'api.db'}",
        artifact_bucket="croquito-test-artifacts",
        aws_region="sa-east-1",
        aws_endpoint_url="http://localhost:4566",
        queue_url=None,
        oidc_issuer=None,
        oidc_audience=None,
        web_origin="http://localhost:5173",
        allow_test_tokens=True,
        storage_flavor=cast(Any, flavor),
    )


def _headers(idempotency_key: str) -> dict[str, str]:
    return {
        "Authorization": "Bearer test:tenant-a:reviewer:engineer",
        "Idempotency-Key": idempotency_key,
    }


def test_invalid_storage_flavor_is_refused_with_a_domain_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CROQUITO_STORAGE_FLAVOR", "azure")

    with pytest.raises(DomainValidationError):
        ApiSettings.from_environment()

    monkeypatch.delenv("CROQUITO_STORAGE_FLAVOR")
    assert ApiSettings.from_environment().storage_flavor == "s3"


def test_s3_flavor_signs_the_checksum_and_reads_it_back(tmp_path: Path) -> None:
    store = ArtifactStore(_settings(tmp_path))
    assert store.client.meta.config.signature_version == "s3v4"
    assert store.client.meta.config.s3 is None
    client = RecordingS3Client()
    store.client = client

    store.presign_pdf_upload(object_key="tenants/a/uploads/x.pdf", checksum_sha256="Zm9v")
    uploaded = store.head_upload(object_key="tenants/a/uploads/x.pdf")

    assert client.presign_params[0]["ChecksumSHA256"] == "Zm9v"
    assert client.head_params[0]["ChecksumMode"] == "ENABLED"
    assert uploaded is not None
    assert uploaded.checksum_sha256 == "Zm9v"


def test_gcs_flavor_omits_checksum_and_signs_path_style(tmp_path: Path) -> None:
    """A interoperabilidade XML do GCS recusa o header de checksum e o virtual-host."""
    store = ArtifactStore(_settings(tmp_path, flavor="gcs"))
    assert store.client.meta.config.signature_version == "s3v4"
    assert store.client.meta.config.s3 == {"addressing_style": "path"}
    client = RecordingS3Client()
    store.client = client

    store.presign_pdf_upload(object_key="tenants/a/uploads/x.pdf", checksum_sha256="Zm9v")
    uploaded = store.head_upload(object_key="tenants/a/uploads/x.pdf")

    assert "ChecksumSHA256" not in client.presign_params[0]
    assert client.presign_params[0]["ContentType"] == "application/pdf"
    assert "ChecksumMode" not in client.head_params[0]
    assert uploaded is not None
    assert uploaded.content_length == 1024
    # O storage até respondeu um checksum, mas ele não é o do protocolo assinado aqui.
    assert uploaded.checksum_sha256 is None


def test_presign_response_carries_the_checksum_header_only_on_s3(tmp_path: Path) -> None:
    pdf = synthetic_pdf()
    payload = {
        "filename": "levantamento.pdf",
        "content_type": "application/pdf",
        "size_bytes": len(pdf),
        "sha256": hashlib.sha256(pdf).hexdigest(),
    }
    expected = base64.b64encode(hashlib.sha256(pdf).digest()).decode("ascii")

    for flavor, store in (("s3", FakeObjectStore()), ("gcs", GcsObjectStore())):
        database_url = f"sqlite+pysqlite:///{tmp_path / f'{flavor}.db'}"
        database = Database(database_url)
        database.create_schema()
        settings = replace(_settings(tmp_path, flavor=flavor), database_url=database_url)
        application = create_app(settings=settings, database=database)
        application.state.artifact_store = store
        client = TestClient(application)

        response = client.post("/v1/uploads/presign", headers=_headers("presign"), json=payload)

        assert response.status_code == 200
        headers = response.json()["headers"]
        assert headers["Content-Type"] == "application/pdf"
        if flavor == "s3":
            assert headers["x-amz-checksum-sha256"] == expected
        else:
            assert "x-amz-checksum-sha256" not in headers


def test_gcs_job_creation_records_that_the_checksum_moved_to_the_worker(tmp_path: Path) -> None:
    """Tamanho e tipo continuam conferidos aqui; o digest é o worker que refaz."""
    database = Database(f"sqlite+pysqlite:///{tmp_path / 'api.db'}")
    database.create_schema()
    application = create_app(settings=_settings(tmp_path, flavor="gcs"), database=database)
    store = GcsObjectStore()
    application.state.artifact_store = store
    client = TestClient(application)
    pdf = synthetic_pdf()
    presign = client.post(
        "/v1/uploads/presign",
        headers=_headers("gcs-presign"),
        json={
            "filename": "levantamento.pdf",
            "content_type": "application/pdf",
            "size_bytes": len(pdf),
            "sha256": hashlib.sha256(pdf).hexdigest(),
        },
    )
    assert presign.status_code == 200
    store.put_direct(object_key=presign.json()["object_key"], body=pdf)

    created = client.post(
        "/v1/jobs",
        headers=_headers("gcs-job"),
        json={"upload_id": presign.json()["upload_id"], "project_name": "Guaxindiba"},
    )

    assert created.status_code == 201
    with database.sessions() as session:
        actions = [
            record.action
            for record in session.scalars(select(AuditRecord).order_by(AuditRecord.id)).all()
        ]
    assert "UPLOAD_CHECKSUM_DEFERRED_TO_WORKER" in actions


def test_gcs_job_creation_still_refuses_a_truncated_upload(tmp_path: Path) -> None:
    database = Database(f"sqlite+pysqlite:///{tmp_path / 'api.db'}")
    database.create_schema()
    application = create_app(settings=_settings(tmp_path, flavor="gcs"), database=database)
    store = GcsObjectStore()
    application.state.artifact_store = store
    client = TestClient(application)
    pdf = synthetic_pdf()
    presign = client.post(
        "/v1/uploads/presign",
        headers=_headers("gcs-presign"),
        json={
            "filename": "levantamento.pdf",
            "content_type": "application/pdf",
            "size_bytes": len(pdf),
            "sha256": hashlib.sha256(pdf).hexdigest(),
        },
    )
    assert presign.status_code == 200
    store.put_direct(object_key=presign.json()["object_key"], body=pdf[: len(pdf) // 2])

    created = client.post(
        "/v1/jobs",
        headers=_headers("gcs-job"),
        json={"upload_id": presign.json()["upload_id"], "project_name": "Guaxindiba"},
    )

    assert created.status_code == 422
    assert created.json()["detail"]["code"] == "INVALID_UPLOAD"


def test_s3_job_creation_still_refuses_a_storage_without_checksum(tmp_path: Path) -> None:
    """No flavor s3 a comparação continua obrigatória — a mudança não afrouxou nada."""
    database = Database(f"sqlite+pysqlite:///{tmp_path / 'api.db'}")
    database.create_schema()
    application = create_app(settings=_settings(tmp_path), database=database)
    store = GcsObjectStore()
    application.state.artifact_store = store
    client = TestClient(application)
    pdf = synthetic_pdf()
    presign = client.post(
        "/v1/uploads/presign",
        headers=_headers("s3-presign"),
        json={
            "filename": "levantamento.pdf",
            "content_type": "application/pdf",
            "size_bytes": len(pdf),
            "sha256": hashlib.sha256(pdf).hexdigest(),
        },
    )
    assert presign.status_code == 200
    store.put_direct(object_key=presign.json()["object_key"], body=pdf)

    created = client.post(
        "/v1/jobs",
        headers=_headers("s3-job"),
        json={"upload_id": presign.json()["upload_id"], "project_name": "Guaxindiba"},
    )

    assert created.status_code == 422
    assert created.json()["detail"]["code"] == "INVALID_UPLOAD"
