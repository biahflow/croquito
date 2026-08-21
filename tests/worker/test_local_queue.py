import hashlib
import json
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from io import BytesIO
from pathlib import Path
from typing import cast

import fitz
import pytest
from PIL import Image

from croquito_api.database import (
    AiProcessingAuthorizationRecord,
    Database,
    JobRecord,
    ProjectRecord,
    ReviewRevisionRecord,
    TenantAiProcessingEntitlementRecord,
    UploadRecord,
)
from croquito_worker.auto_association import AutoAssociationConfigError
from croquito_worker.local_queue import (
    PREVIEW_BASE_DPI,
    PROVIDER_IMAGE_MAX_BYTES,
    PROVIDER_IMAGE_MAX_SIDE_PX,
    LocalQueueWorker,
    LocalWorkerSettings,
    S3ProtectedRawResponseStore,
    ValidatedUpload,
    _validate_pdf_stream,
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


def test_o_worker_recusa_subir_com_o_modo_automatico_mal_configurado(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Flag ligada sem corte é erro de configuração e para antes da primeira mensagem.

    Se a recusa só acontecesse na gravação da revisão, o consumidor entraria em ciclo de
    reentrega por um erro que não é do dado — e cada volta pagaria de novo a ingestão.
    """
    monkeypatch.setenv("CROQUITO_AUTO_ASSOCIATION_ENABLED", "true")
    monkeypatch.delenv("CROQUITO_AUTO_ASSOCIATION_THRESHOLD", raising=False)

    with pytest.raises(AutoAssociationConfigError):
        LocalQueueWorker(
            LocalWorkerSettings(
                database_url=f"sqlite+pysqlite:///{tmp_path / 'worker.db'}",
                queue_url="http://localstack/queue",
                aws_region="sa-east-1",
                aws_endpoint_url="http://localstack",
            )
        )


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
                providers_json=["openai", "anthropic"],
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
    # O teto estoura no braço primário do survey (Anthropic). Ali o fallback não entra:
    # a segunda chamada consumiria o mesmo teto, então o job precisa falhar inteiro.
    exhausted = replace(
        suite,
        anthropic=replace(
            cast(FixtureProviderAdapter, suite.anthropic),
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


def test_hosted_suite_labels_the_revision_as_paid_extraction(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Suite construída pelo worker chamou provider real; a proveniência tem de dizer isso.

    A fixture entra por `build_real_provider_suite` monkeypatchado — nada sai da máquina —,
    exatamente pelo caminho em que `provider_suite` é `None`.
    """
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "local")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "local")
    database_url = f"sqlite+pysqlite:///{tmp_path / 'hosted-worker.db'}"
    database = Database(database_url)
    database.create_schema()
    pdf = synthetic_pdf()
    job_id = "00000000-0000-7000-8000-000000000011"
    object_key = "tenants/tenant-hosted/uploads/autorizado.pdf"
    _seed_authorized_job(
        database, job_id=job_id, tenant_id="tenant-hosted", object_key=object_key, pdf=pdf
    )
    monkeypatch.setattr(
        "croquito_worker.local_queue.build_real_provider_suite",
        lambda **_kwargs: build_synthetic_provider_suite(),
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
    worker.client = _queue({"job_id": job_id, "tenant_id": "tenant-hosted"})
    worker.s3_client = _storage(object_key=object_key, pdf=pdf)

    assert worker.run_once() == 1
    with database.sessions() as session:
        review = session.query(ReviewRevisionRecord).filter_by(job_id=job_id).one()
        assert review.created_by == "hosted-provider-extraction-v1"
        assert review.packet_json["dataset_id"] == f"job-{job_id}"


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
                providers_json=["openai", "anthropic"],
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
        # Anthropic é a âncora da extração dupla; OpenAI entra como contraparte.
        assert review.packet_json["readings"][0]["provider_lineage"][0]["provider"] == "anthropic"
        # Rótulos honestos: o dataset identifica o documento do job, e a proveniência
        # diz que esta revisão nasceu de fixture offline, não de chamada paga.
        assert review.packet_json["dataset_id"] == f"job-{job_id}"
        assert review.associations_json["dataset_id"] == f"job-{job_id}"
        assert review.proposals_json is not None
        assert review.proposals_json["dataset_id"] == f"job-{job_id}"
        assert review.created_by == "offline-provider-contract-fixture"
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
        provider_suite=ProviderSuite(openai=refusing, anthropic=refusing),
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


def _line_art_pdf(*, width: float, height: float, spacing: int) -> bytes:
    """Página sintética com traço denso o bastante para o PNG não comprimir a nada.

    Prancha em branco vira PNG de alguns KB e não exercita limite nenhum; o que interessa
    aqui é a página grande e cheia de linha fina, como a do cliente.
    """
    document = fitz.open()
    page = document.new_page(width=width, height=height)
    for index in range(0, int(width), spacing):
        page.draw_line(fitz.Point(index, 0), fitz.Point(width - index, height), width=0.4)
    for index in range(0, int(height), spacing):
        page.draw_line(fitz.Point(0, index), fitz.Point(width, height - index), width=0.4)
    content = cast(bytes, document.tobytes())
    document.close()
    return content


def _validated(pdf: bytes) -> ValidatedUpload:
    return _validate_pdf_stream(
        BytesIO(pdf),
        expected_sha256=hashlib.sha256(pdf).hexdigest(),
        capture_first_page_preview=True,
    )


def test_provider_preview_fits_the_provider_image_limits() -> None:
    """A prancha real do cliente rendia 4875x6718 px e PNG de 22 MB a 200 DPI.

    Os dois braços recusavam o payload com 4xx e o job ficava preso em PROCESSING. O
    preview agora nasce dentro dos tetos; o DPI efetivo é a evidência de quanto caiu.
    """
    # Mesma geometria da prancha real: 1755x2418 pt = 4875x6717 px a 200 DPI.
    validated = _validated(_line_art_pdf(width=1755, height=2418, spacing=18))

    assert validated.first_page_preview is not None
    assert validated.preview_dpi is not None
    assert len(validated.first_page_preview) <= PROVIDER_IMAGE_MAX_BYTES
    with Image.open(BytesIO(validated.first_page_preview)) as image:
        width, height = image.size
    assert max(width, height) <= PROVIDER_IMAGE_MAX_SIDE_PX
    # Reduziu de verdade, e o DPI declarado bate com o pixmap entregue.
    assert validated.preview_dpi < PREVIEW_BASE_DPI
    assert width == pytest.approx(1755 * validated.preview_dpi / 72, abs=2)
    assert height == pytest.approx(2418 * validated.preview_dpi / 72, abs=2)


def test_provider_preview_respects_the_side_limit_alone() -> None:
    """Página larga e leve: o PNG cabe em bytes, só o lado maior estoura."""
    # 3000x400 pt = 8333x1111 px a 200 DPI — acima dos 7500 px, longe do teto de bytes.
    validated = _validated(_line_art_pdf(width=3000, height=400, spacing=120))

    assert validated.first_page_preview is not None
    assert len(validated.first_page_preview) <= PROVIDER_IMAGE_MAX_BYTES
    with Image.open(BytesIO(validated.first_page_preview)) as image:
        assert max(image.size) <= PROVIDER_IMAGE_MAX_SIDE_PX


def test_provider_preview_keeps_full_dpi_when_the_page_already_fits() -> None:
    """Sem estouro não há redução: documento pequeno continua saindo a 200 DPI."""
    validated = _validated(synthetic_pdf())

    assert validated.preview_dpi == PREVIEW_BASE_DPI


def test_object_client_only_sends_checksums_where_the_api_requires_them(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """O checksum implícito do botocore quebrou o primeiro PUT em HML (GCS interop).

    O GCS recusa `x-amz-checksum-*` e a assinatura cai em SignatureDoesNotMatch; cada
    reentrega pagava uma chamada de provider e falhava de novo na gravação.
    """
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "local")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "local")
    worker = LocalQueueWorker(
        LocalWorkerSettings(
            database_url=f"sqlite+pysqlite:///{tmp_path / 'client.db'}",
            queue_url="http://localstack/queue",
            aws_region="sa-east-1",
            aws_endpoint_url="http://localstack",
        )
    )

    config = worker.s3_client.meta.config

    assert config.request_checksum_calculation == "when_required"
    assert config.response_checksum_validation == "when_required"
    # A correção do checksum não pode desfazer o que já fazia o GCS funcionar no GET.
    assert config.signature_version == "s3v4"
    assert config.s3["addressing_style"] == "path"


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


def test_raw_response_store_keeps_the_accepted_key_and_marks_the_rejected_one() -> None:
    """A chave de sucesso não se move; a recusada ganha o segmento que o `ls` mostra.

    O operador que lista o prefixo do job precisa distinguir raw aceito de raw recusado sem
    abrir arquivo nenhum — e nenhum objeto de sucesso pode mudar de lugar por causa disso.
    """
    storage = FakeObjectStore()
    store = S3ProtectedRawResponseStore(
        client=storage, bucket="bucket", tenant_id="tenant-a", job_id="job-a"
    )
    payload = b"{}"
    payload_digest = hashlib.sha256(payload).hexdigest()
    input_digest = "a" * 64

    accepted = store.persist(
        provider=ProviderName.OPENAI, input_digest=input_digest, payload=payload
    )
    rejected = store.persist(
        provider=ProviderName.OPENAI,
        input_digest=input_digest,
        payload=payload,
        rejected_stage="invalid_json",
    )

    assert accepted == (
        f"tenants/tenant-a/jobs/job-a/providers/openai/{input_digest}/{payload_digest}.json"
    )
    assert rejected == (
        "tenants/tenant-a/jobs/job-a/providers/openai/rejected/invalid_json/"
        f"{input_digest}/{payload_digest}.json"
    )
    assert [str(put["Key"]) for put in storage.puts] == [accepted, rejected]
