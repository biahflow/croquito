import hashlib
import json
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import cast

import pytest

from croquito_api.database import (
    AiProcessingAuthorizationRecord,
    Database,
    JobRecord,
    ProjectRecord,
    ReviewRevisionRecord,
    TenantAiProcessingEntitlementRecord,
    UploadRecord,
)
from croquito_worker.local_queue import (
    LocalQueueWorker,
    LocalWorkerSettings,
    S3ProtectedRawResponseStore,
)
from croquito_worker.providers import (
    FixtureProviderAdapter,
    PromptTask,
    ProviderExecution,
    ProviderFailureCode,
    ProviderName,
    ProviderRequest,
    ProviderSuite,
    build_synthetic_provider_suite,
)
from tests.fakes import FakeObjectStore, FakeQueue, synthetic_pdf

UPLOAD_KEY_A = "tenants/tenant-a/uploads/upload-a/entrada.pdf"
UPLOAD_KEY_FIXTURE = "tenants/tenant-fixture/uploads/fixture.pdf"
UPLOAD_KEY_CONSENT = "tenants/tenant-consent/uploads/consent.pdf"


def _queue(body: dict[str, str]) -> FakeQueue:
    queue = FakeQueue()
    queue.send_message(MessageBody=json.dumps(body))
    return queue


def _storage(*, object_key: str, pdf: bytes) -> FakeObjectStore:
    storage = FakeObjectStore()
    storage.put_direct(object_key=object_key, body=pdf)
    return storage


def test_local_queue_worker_advances_only_the_queued_tenant(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "local")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "local")
    database_url = f"sqlite+pysqlite:///{tmp_path / 'worker.db'}"
    database = Database(database_url)
    database.create_schema()
    pdf = synthetic_pdf()
    expires_at = datetime.now(UTC) + timedelta(days=7)
    with database.sessions.begin() as session:
        session.add(
            ProjectRecord(
                id="project-a",
                tenant_id="tenant-a",
                name="Projeto",
                default_unit="m",
                created_by="reviewer",
                expires_at=expires_at,
            )
        )
        session.add(
            UploadRecord(
                id="upload-a",
                tenant_id="tenant-a",
                object_key=UPLOAD_KEY_A,
                filename="entrada.pdf",
                content_type="application/pdf",
                size_bytes=10,
                sha256=hashlib.sha256(pdf).hexdigest(),
            )
        )
        session.flush()
        session.add(
            JobRecord(
                id="00000000-0000-7000-8000-000000000001",
                tenant_id="tenant-a",
                project_id="project-a",
                upload_id="upload-a",
                status="UPLOADED",
                stage="VALIDATING",
                expires_at=expires_at,
            )
        )
    worker = LocalQueueWorker(
        LocalWorkerSettings(
            database_url=database_url,
            queue_url="http://localstack/queue",
            aws_region="sa-east-1",
            aws_endpoint_url="http://localstack",
        )
    )
    fake_client = _queue(
        {
            "job_id": "00000000-0000-7000-8000-000000000001",
            "tenant_id": "tenant-a",
            "stage": "VALIDATING",
        }
    )
    worker.client = fake_client
    worker.s3_client = _storage(object_key=UPLOAD_KEY_A, pdf=pdf)

    assert worker.run_once() == 1
    with database.sessions() as session:
        job = session.get(JobRecord, "00000000-0000-7000-8000-000000000001")
        assert job is not None
        assert job.status == "REVIEW_REQUIRED"
        assert job.stage == "PREVIEWING"
        assert job.page_count == 1
    assert fake_client.deleted == ["receipt-1"]
    assert worker.s3_client.puts == []


def _seed_authorized_job(
    database: Database, *, job_id: str, tenant_id: str, object_key: str, pdf: bytes
) -> None:
    expires_at = datetime.now(UTC) + timedelta(days=7)
    with database.sessions.begin() as session:
        session.add(
            ProjectRecord(
                id=f"project-{tenant_id}",
                tenant_id=tenant_id,
                name="Autorizado",
                default_unit="m",
                created_by="reviewer",
                expires_at=expires_at,
            )
        )
        session.add(
            UploadRecord(
                id=f"upload-{tenant_id}",
                tenant_id=tenant_id,
                object_key=object_key,
                filename="autorizado.pdf",
                content_type="application/pdf",
                size_bytes=len(pdf),
                sha256=hashlib.sha256(pdf).hexdigest(),
            )
        )
        session.flush()
        session.add(
            JobRecord(
                id=job_id,
                tenant_id=tenant_id,
                project_id=f"project-{tenant_id}",
                upload_id=f"upload-{tenant_id}",
                status="UPLOADED",
                stage="VALIDATING",
                expires_at=expires_at,
            )
        )
        session.add(
            TenantAiProcessingEntitlementRecord(
                id=f"entitlement-{tenant_id}",
                tenant_id=tenant_id,
                status="ACTIVE",
                agreement_reference="ctr-v1",
                authorized_by="platform-operator",
                authorized_at=expires_at,
            )
        )
        session.flush()
        session.add(
            AiProcessingAuthorizationRecord(
                id=f"authorization-{tenant_id}",
                tenant_id=tenant_id,
                job_id=job_id,
                accepted_by="platform-operator",
                notice_version="contractual-entitlement-v1",
                providers_json=["openai", "bedrock_anthropic", "textract"],
                global_processing=True,
                retention_days=7,
                authorization_source="contract",
                entitlement_id=f"entitlement-{tenant_id}",
                agreement_reference="ctr-v1",
            )
        )


def test_budget_exceeded_fails_the_job_instead_of_burning_the_ceiling_again(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Reentrega depois de estourar o teto chamaria o provider de novo e gastaria mais."""
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "local")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "local")
    database_url = f"sqlite+pysqlite:///{tmp_path / 'budget-worker.db'}"
    database = Database(database_url)
    database.create_schema()
    pdf = synthetic_pdf()
    job_id = "00000000-0000-7000-8000-000000000009"
    object_key = "tenants/tenant-budget/uploads/budget.pdf"
    _seed_authorized_job(
        database, job_id=job_id, tenant_id="tenant-budget", object_key=object_key, pdf=pdf
    )
    suite = build_synthetic_provider_suite()
    exhausted = replace(
        suite,
        openai=replace(
            cast(FixtureProviderAdapter, suite.openai),
            failures={PromptTask.PAGE_SURVEY: ProviderFailureCode.BUDGET_EXCEEDED},
        ),
    )
    worker = LocalQueueWorker(
        LocalWorkerSettings(
            database_url=database_url,
            queue_url="http://localstack/queue",
            aws_region="sa-east-1",
            aws_endpoint_url="http://localstack",
            real_providers_enabled=True,
        ),
        provider_suite=exhausted,
    )
    queue = _queue({"job_id": job_id, "tenant_id": "tenant-budget"})
    worker.client = queue
    worker.s3_client = _storage(object_key=object_key, pdf=pdf)

    assert worker.run_once() == 1
    with database.sessions() as session:
        job = session.get(JobRecord, job_id)
        assert job is not None
        assert job.status == "FAILED"
        assert job.failure_code == "AI_BUDGET_EXCEEDED"
        assert session.query(ReviewRevisionRecord).filter_by(job_id=job_id).count() == 0
    # Mensagem drenada: sem isso a fila reentregaria e o teto seria gasto outra vez.
    assert queue.deleted == ["receipt-1"]


def test_extraction_refuses_a_document_outside_the_allowlist(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Entitlement libera o tenant a pagar; a allowlist libera o documento a sair."""
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "local")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "local")
    database_url = f"sqlite+pysqlite:///{tmp_path / 'allowlist-worker.db'}"
    database = Database(database_url)
    database.create_schema()
    pdf = synthetic_pdf()
    job_id = "00000000-0000-7000-8000-000000000010"
    object_key = "tenants/tenant-allowlist/uploads/nao-autorizado.pdf"
    _seed_authorized_job(
        database, job_id=job_id, tenant_id="tenant-allowlist", object_key=object_key, pdf=pdf
    )
    worker = LocalQueueWorker(
        LocalWorkerSettings(
            database_url=database_url,
            queue_url="http://localstack/queue",
            aws_region="sa-east-1",
            aws_endpoint_url="http://localstack",
            real_providers_enabled=True,
            ai_extraction_allowed_digests=frozenset({"b" * 64}),
        )
    )
    queue = _queue({"job_id": job_id, "tenant_id": "tenant-allowlist"})
    worker.client = queue
    worker.s3_client = _storage(object_key=object_key, pdf=pdf)

    assert worker.run_once() == 1
    with database.sessions() as session:
        job = session.get(JobRecord, job_id)
        assert job is not None
        assert job.status == "FAILED"
        assert job.failure_code == "AI_EXTRACTION_NOT_ALLOWLISTED"
    # Recusado antes de montar a suite real: nenhuma credencial é lida, nada sai.
    assert queue.deleted == ["receipt-1"]
    assert worker.s3_client.puts == []


def test_explicit_provider_fixture_persists_non_exportable_review_snapshot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "local")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "local")
    database_url = f"sqlite+pysqlite:///{tmp_path / 'fixture-worker.db'}"
    database = Database(database_url)
    database.create_schema()
    pdf = synthetic_pdf()
    expires_at = datetime.now(UTC) + timedelta(days=7)
    job_id = "00000000-0000-7000-8000-000000000002"
    with database.sessions.begin() as session:
        session.add(
            ProjectRecord(
                id="project-fixture",
                tenant_id="tenant-fixture",
                name="Fixture",
                default_unit="m",
                created_by="reviewer",
                expires_at=expires_at,
            )
        )
        session.add(
            UploadRecord(
                id="upload-fixture",
                tenant_id="tenant-fixture",
                object_key=UPLOAD_KEY_FIXTURE,
                filename="fixture.pdf",
                content_type="application/pdf",
                size_bytes=len(pdf),
                sha256=hashlib.sha256(pdf).hexdigest(),
            )
        )
        session.flush()
        session.add(
            JobRecord(
                id=job_id,
                tenant_id="tenant-fixture",
                project_id="project-fixture",
                upload_id="upload-fixture",
                status="UPLOADED",
                stage="VALIDATING",
                expires_at=expires_at,
            )
        )
        session.add(
            TenantAiProcessingEntitlementRecord(
                id="entitlement-fixture",
                tenant_id="tenant-fixture",
                status="ACTIVE",
                agreement_reference="ctr-fixture-v1",
                authorized_by="platform-operator",
                authorized_at=expires_at,
            )
        )
        session.flush()
        session.add(
            AiProcessingAuthorizationRecord(
                id="authorization-fixture",
                tenant_id="tenant-fixture",
                job_id=job_id,
                accepted_by="platform-operator",
                notice_version="contractual-entitlement-v1",
                providers_json=["openai", "bedrock_anthropic", "textract"],
                global_processing=True,
                retention_days=7,
                authorization_source="contract",
                entitlement_id="entitlement-fixture",
                agreement_reference="ctr-fixture-v1",
            )
        )

    worker = LocalQueueWorker(
        LocalWorkerSettings(
            database_url=database_url,
            queue_url="http://localstack/queue",
            aws_region="sa-east-1",
            aws_endpoint_url="http://localstack",
            real_providers_enabled=True,
        ),
        provider_suite=build_synthetic_provider_suite(),
    )
    queue = _queue({"job_id": job_id, "tenant_id": "tenant-fixture"})
    storage = _storage(object_key=UPLOAD_KEY_FIXTURE, pdf=pdf)
    worker.client = queue
    worker.s3_client = storage

    assert worker.run_once() == 1
    with database.sessions() as session:
        review = session.query(ReviewRevisionRecord).filter_by(job_id=job_id).one()
        assert review.packet_json["safety_status"] == "human_review_required"
        assert review.packet_json["readings"][0]["provider_lineage"][0]["provider"] == "openai"
        assert review.associations_json["candidates"]
        assert review.evidence_refs_json == {
            "source_image_key": f"tenants/tenant-fixture/jobs/{job_id}/review/source.png"
        }
    assert len(storage.puts) == 1
    assert storage.puts[0]["ContentType"] == "image/png"


def test_real_providers_require_contractual_authorization_before_reading_upload(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "local")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "local")
    database_url = f"sqlite+pysqlite:///{tmp_path / 'consent-worker.db'}"
    database = Database(database_url)
    database.create_schema()
    job_id = "00000000-0000-7000-8000-000000000003"
    now = datetime.now(UTC) + timedelta(days=7)
    with database.sessions.begin() as session:
        session.add(
            ProjectRecord(
                id="project-consent",
                tenant_id="tenant-consent",
                name="Consentimento",
                default_unit="m",
                created_by="reviewer",
                expires_at=now,
            )
        )
        session.add(
            UploadRecord(
                id="upload-consent",
                tenant_id="tenant-consent",
                object_key=UPLOAD_KEY_CONSENT,
                filename="consent.pdf",
                content_type="application/pdf",
                size_bytes=1,
                sha256="a" * 64,
            )
        )
        session.flush()
        session.add(
            JobRecord(
                id=job_id,
                tenant_id="tenant-consent",
                project_id="project-consent",
                upload_id="upload-consent",
                status="UPLOADED",
                stage="VALIDATING",
                expires_at=now,
            )
        )
    worker = LocalQueueWorker(
        LocalWorkerSettings(
            database_url=database_url,
            queue_url="http://localstack/queue",
            aws_region="sa-east-1",
            aws_endpoint_url="http://localstack",
            real_providers_enabled=True,
        )
    )
    queue = _queue({"job_id": job_id, "tenant_id": "tenant-consent"})
    worker.client = queue
    worker.s3_client = FakeObjectStore()

    assert worker.run_once() == 1
    with database.sessions() as session:
        job = session.get(JobRecord, job_id)
        assert job is not None
        assert job.failure_code == "AI_PROCESSING_NOT_AUTHORIZED"
    assert queue.deleted == ["receipt-1"]


@dataclass(frozen=True)
class _RefusingAdapter:
    """Qualquer chamada aqui é o defeito que o teste procura."""

    def execute(self, request: ProviderRequest) -> ProviderExecution:
        raise AssertionError("provider chamado numa reentrega de job já ingerido")


def test_redelivery_of_an_ingested_job_neither_reprocesses_nor_calls_the_provider(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Sem a guarda, a reentrega rebaixaria o documento e pagaria a chamada de novo."""
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "local")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "local")
    database_url = f"sqlite+pysqlite:///{tmp_path / 'redelivery.db'}"
    database = Database(database_url)
    database.create_schema()
    pdf = synthetic_pdf()
    job_id = "00000000-0000-7000-8000-000000000011"
    object_key = "tenants/tenant-redelivery/uploads/reentrega.pdf"
    _seed_authorized_job(
        database, job_id=job_id, tenant_id="tenant-redelivery", object_key=object_key, pdf=pdf
    )
    settings = LocalWorkerSettings(
        database_url=database_url,
        queue_url="http://localstack/queue",
        aws_region="sa-east-1",
        aws_endpoint_url="http://localstack",
        real_providers_enabled=True,
    )
    body = {"command": "process_upload", "job_id": job_id, "tenant_id": "tenant-redelivery"}
    first = LocalQueueWorker(settings, provider_suite=build_synthetic_provider_suite())
    first.client = _queue(body)
    first.s3_client = _storage(object_key=object_key, pdf=pdf)
    assert first.run_once() == 1

    refusing = _RefusingAdapter()
    second = LocalQueueWorker(
        settings,
        provider_suite=ProviderSuite(
            openai=refusing, bedrock_anthropic=refusing, textract=refusing
        ),
    )
    second.client = _queue(body)
    # Storage vazio: qualquer releitura do documento levantaria em vez de passar batido.
    second.s3_client = FakeObjectStore()

    assert second.run_once() == 1
    with database.sessions() as session:
        job = session.get(JobRecord, job_id)
        assert job is not None
        assert job.status == "REVIEW_REQUIRED"
        assert session.query(ReviewRevisionRecord).filter_by(job_id=job_id).count() == 1
    assert second.s3_client.puts == []
    # A reentrega é reconhecida e drenada; ela não volta para a fila.
    assert second.client.deleted == ["receipt-1"]


def test_raw_response_store_honours_the_encryption_flag() -> None:
    storage = FakeObjectStore()
    encrypted = S3ProtectedRawResponseStore(
        client=storage, bucket="bucket", tenant_id="tenant-a", job_id="job-a"
    )
    plain = S3ProtectedRawResponseStore(
        client=storage, bucket="bucket", tenant_id="tenant-a", job_id="job-a", sse=False
    )

    encrypted.persist(provider=ProviderName.OPENAI, input_digest="a" * 64, payload=b"{}")
    plain.persist(provider=ProviderName.OPENAI, input_digest="b" * 64, payload=b"{}")

    assert storage.puts[0]["ServerSideEncryption"] == "AES256"
    assert "ServerSideEncryption" not in storage.puts[1]
