"""Consumidor local SQS com providers externos explicitamente autorizados por job.

O despacho (`LocalQueueWorker.dispatch`) é independente do transporte: o consumidor SQS o
chama depois do `receive_message` e o receptor push (`push_server`) depois de decodificar
o envelope. Retorno normal significa ack; exceção significa reentrega.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from collections.abc import Mapping, Sequence
from contextlib import closing, suppress
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final, cast

import boto3
import fitz
from botocore.config import Config as BotoConfig
from botocore.exceptions import BotoCoreError, ClientError
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Connection, RowMapping
from sqlalchemy.exc import IntegrityError

from croquito_core.errors import DomainValidationError
from croquito_core.ids import new_uuid7
from croquito_core.models import SceneRevision
from croquito_valuation.errors import ValuationValidationError
from croquito_worker.artifact_store import WorkerArtifactStore
from croquito_worker.chat import build_chat_text_payload, chat_unknown_references
from croquito_worker.criteria import ScopeCriterion
from croquito_worker.dxf import export_scene_package
from croquito_worker.provider_review import (
    ProviderReviewSnapshot,
    build_provider_review_snapshot,
)
from croquito_worker.providers import (
    PromptTask,
    ProtectedRawResponseStore,
    ProviderAdapter,
    ProviderExecution,
    ProviderExecutionError,
    ProviderFailureCode,
    ProviderName,
    ProviderSuite,
    ReviewChatOutput,
    build_image_text_request,
    build_real_provider_suite,
)
from croquito_worker.rectangle_solver import SolverResidual
from croquito_worker.review import ReviewPacket
from croquito_worker.review_store import (
    ReviewAlreadyExistsError,
    insert_review_revision_v1,
    json_expression,
)
from croquito_worker.tracing import (
    TRACER_VERSION,
    DerivedDimensionRequest,
    TraceAcceptance,
    solve_trace,
)
from croquito_worker.valuation.round_extraction import (
    MAX_PLATE_PDF_BYTES,
    PLATE_IMAGE_DIGEST,
    PLATE_IMAGE_REF,
    PLATE_PAGE_NUMBER,
    PLATE_PDF_FILENAME,
    TAKEOFF_OVERLAY_DIGEST,
    TAKEOFF_OVERLAY_REF,
    build_extraction_adapter,
    execution_payload,
    extract_legend_from_upload,
    extraction_arm_spec,
    extraction_failure_code,
    extraction_unavailable,
    ingest_plate_upload,
    plate_image_object_key,
    registration_payload,
    takeoff_overlay_object_key,
    upload_invalid,
)
from croquito_worker.valuation.takeoff_overlay import render_takeoff_overlay, save_takeoff_overlay
from croquito_worker.vision import VisionProposalSet


@dataclass(frozen=True, slots=True)
class LocalWorkerSettings:
    database_url: str
    queue_url: str
    aws_region: str
    aws_endpoint_url: str
    artifact_bucket: str = "croquito-local-artifacts"
    # SSE-S3 explícita em todo put. O storage do GCP criptografa em repouso por padrão e
    # recusa o header pela interoperabilidade; lá a flag desliga sem perder criptografia.
    storage_sse_enabled: bool = True
    real_providers_enabled: bool = False
    # Digests sha256 de upload liberados para extração paga. Vazio significa nenhum:
    # ligar a flag de providers não deve, sozinho, mandar documento de cliente para fora.
    ai_extraction_allowed_digests: frozenset[str] = frozenset()

    @classmethod
    def from_environment(cls, *, require_queue: bool = True) -> LocalWorkerSettings:
        """Reads local configuration; commands that never consume the queue may skip its URL."""
        required = {
            "database_url": os.getenv("CROQUITO_DATABASE_URL"),
            "aws_endpoint_url": os.getenv("CROQUITO_AWS_ENDPOINT_URL"),
        }
        if require_queue:
            required["queue_url"] = os.getenv("CROQUITO_PROCESSING_QUEUE_URL")
        missing = [name for name, value in required.items() if not value]
        if missing:
            raise ValueError(f"Configuração local ausente: {', '.join(missing)}")
        return cls(
            database_url=str(required["database_url"]),
            queue_url=str(required.get("queue_url") or ""),
            aws_region=os.getenv("AWS_REGION", "sa-east-1"),
            aws_endpoint_url=str(required["aws_endpoint_url"]),
            artifact_bucket=os.getenv("CROQUITO_ARTIFACT_BUCKET", "croquito-local-artifacts"),
            storage_sse_enabled=os.getenv("CROQUITO_STORAGE_SSE", "true").lower()
            in {"1", "true", "yes"},
            real_providers_enabled=os.getenv("CROQUITO_REAL_PROVIDERS_ENABLED", "").lower()
            in {"1", "true", "yes"},
            ai_extraction_allowed_digests=frozenset(
                digest.strip().lower()
                for digest in os.getenv("CROQUITO_AI_EXTRACTION_ALLOWED_DIGESTS", "").split(",")
                if digest.strip()
            ),
        )


#: Status de job que só existem depois da ingestão ter concluído. `FAILED` fica de fora
#: de propósito: a recusa por autorização ou por PDF inválido é recuperável, e reenfileirar
#: o mesmo comando depois de corrigir a causa continua sendo o caminho de retomada.
INGESTED_JOB_STATUSES = frozenset({"REVIEW_REQUIRED", "APPROVED", "EXPORTING", "COMPLETED"})

VALUATION_EXTRACTION_VERSION: Final = "valuation-extraction-v1"
"""Autor da revisão que a extração publica e versão declarada no lineage.

O par prompt+modelo já viaja no `execution` do lineage; isto identifica o CAMINHO que
publicou o artefato — o comando de fila, e não a thread do servidor de homologação."""


def _json_column(value: Any) -> Any:
    """Raw SQL returns JSON as text on SQLite and as a structure on PostgreSQL."""
    return json.loads(value) if isinstance(value, str) else value


def _json_parameter(parameters: dict[str, Any], dialect: str, name: str, value: Any) -> str:
    """Binds one JSON column, emitting the literal NULL when there is nothing to store."""
    if value is None:
        return "NULL"
    parameters[name] = json.dumps(value, ensure_ascii=False)
    return json_expression(dialect, name)


def _residual_summary(residuals: Sequence[SolverResidual]) -> dict[str, Any]:
    """Counts plus the worst residual: the full list already travels inside the scene."""
    worst = max(residuals, key=lambda residual: residual.absolute_error_m, default=None)
    return {
        "count": len(residuals),
        "failed_count": sum(1 for residual in residuals if not residual.passed),
        "worst_code": worst.code if worst is not None else None,
        "worst_absolute_error_m": float(worst.absolute_error_m) if worst is not None else None,
        "worst_tolerance_m": float(worst.tolerance_m) if worst is not None else None,
    }


class InvalidUploadError(ValueError):
    """Untrusted input failed a deterministic pre-processing guardrail."""


class UnroutableMessageError(ValueError):
    """A mensagem não descreve um comando conhecido deste worker.

    É defeito do publicador ou payload estranho à fila, nunca falha transitória: reentregar
    produz exatamente o mesmo resultado. Continua sendo `ValueError` para preservar a
    semântica do consumidor SQS, que não apaga a mensagem quando o despacho levanta.
    """


@dataclass(frozen=True, slots=True)
class ValidatedUpload:
    page_count: int
    first_page_preview: bytes | None = None


@dataclass(frozen=True, slots=True)
class S3ProtectedRawResponseStore(ProtectedRawResponseStore):
    """Stores raw provider payloads under the job's private seven-day lifecycle prefix."""

    client: Any
    bucket: str
    tenant_id: str
    job_id: str
    #: Ver `WorkerArtifactStore.sse`: SSE-S3 explícita, desligável só onde o storage recusa.
    sse: bool = True

    def persist(self, *, provider: ProviderName, input_digest: str, payload: bytes) -> str:
        payload_digest = hashlib.sha256(payload).hexdigest()
        key = (
            f"tenants/{self.tenant_id}/jobs/{self.job_id}/providers/"
            f"{provider.value}/{input_digest}/{payload_digest}.json"
        )
        self.client.put_object(
            Bucket=self.bucket,
            Key=key,
            Body=payload,
            ContentType="application/json",
            **({"ServerSideEncryption": "AES256"} if self.sse else {}),
        )
        return key


def _validate_pdf_stream(
    body: Any,
    *,
    expected_sha256: str,
    capture_first_page_preview: bool = False,
) -> ValidatedUpload:
    digest = hashlib.sha256()
    total_size = 0
    with tempfile.NamedTemporaryFile(suffix=".pdf") as temporary_file:
        while chunk := body.read(1024 * 1024):
            if not isinstance(chunk, bytes):
                raise InvalidUploadError("Corpo de upload inválido.")
            total_size += len(chunk)
            if total_size > 100_000_000:
                raise InvalidUploadError("PDF excede o limite de tamanho.")
            digest.update(chunk)
            temporary_file.write(chunk)
        temporary_file.flush()
        temporary_file.seek(0)
        if temporary_file.read(5) != b"%PDF-":
            raise InvalidUploadError("Assinatura PDF ausente.")
        if digest.hexdigest() != expected_sha256:
            raise InvalidUploadError("Digest do PDF diverge do upload solicitado.")
        try:
            document = fitz.open(temporary_file.name)
        except (fitz.FileDataError, RuntimeError) as error:
            raise InvalidUploadError("Estrutura PDF inválida.") from error
        with document:
            if document.page_count < 1 or document.page_count > 50:
                raise InvalidUploadError("Quantidade de páginas fora do limite.")
            for page in document:
                rect = page.rect
                pixel_width = rect.width * 200 / 72
                pixel_height = rect.height * 200 / 72
                if pixel_width * pixel_height > 100_000_000:
                    raise InvalidUploadError("Página excede o limite de resolução.")
            preview = None
            if capture_first_page_preview:
                pixmap = document[0].get_pixmap(matrix=fitz.Matrix(200 / 72, 200 / 72), alpha=False)
                preview = pixmap.tobytes("png")
            return ValidatedUpload(page_count=int(document.page_count), first_page_preview=preview)


class LocalQueueWorker:
    def __init__(
        self,
        settings: LocalWorkerSettings,
        *,
        provider_suite: ProviderSuite | None = None,
        valuation_extraction_adapter: ProviderAdapter | None = None,
    ) -> None:
        self.settings = settings
        # No environment switch exists for fixtures: only a caller can explicitly inject one.
        self.provider_suite = provider_suite
        # Mesma regra para o braço pago da extração de legenda: nenhuma variável de ambiente
        # troca o adapter real por uma fixture — só quem constrói o worker pode injetá-la.
        self.valuation_extraction_adapter = valuation_extraction_adapter
        self._queue_client: Any | None = None
        self._object_client: Any | None = None
        self.engine = create_engine(settings.database_url)

    @property
    def client(self) -> Any:
        """SQS client built on first use: the push transport never consumes a queue."""
        if self._queue_client is None:
            self._queue_client = boto3.client(
                "sqs",
                region_name=self.settings.aws_region,
                endpoint_url=self.settings.aws_endpoint_url,
            )
        return self._queue_client

    @client.setter
    def client(self, value: Any) -> None:
        self._queue_client = value

    @property
    def s3_client(self) -> Any:
        if self._object_client is None:
            # Path-style e SigV4 explícitos, como no ArtifactStore da API: o interop
            # S3 do GCS exige os dois; LocalStack e AWS aceitam ambos.
            self._object_client = boto3.client(
                "s3",
                region_name=self.settings.aws_region,
                endpoint_url=self.settings.aws_endpoint_url,
                config=BotoConfig(signature_version="s3v4", s3={"addressing_style": "path"}),
            )
        return self._object_client

    @s3_client.setter
    def s3_client(self, value: Any) -> None:
        self._object_client = value

    def _mark_failed(self, *, job_id: str, tenant_id: str, failure_code: str) -> None:
        with self.engine.begin() as connection:
            result = connection.execute(
                text(
                    "UPDATE jobs SET status = 'FAILED', stage = 'VALIDATING', "
                    "failure_code = :failure_code, updated_at = CURRENT_TIMESTAMP "
                    "WHERE id = :job_id AND tenant_id = :tenant_id"
                ),
                {"job_id": job_id, "tenant_id": tenant_id, "failure_code": failure_code},
            )
        if result.rowcount != 1:
            raise ValueError("Job não encontrado ou tenant divergente")

    def _mark_invalid_upload(self, *, job_id: str, tenant_id: str) -> None:
        self._mark_failed(job_id=job_id, tenant_id=tenant_id, failure_code="INVALID_UPLOAD")

    def _delete_message(self, message: dict[str, Any]) -> None:
        self.client.delete_message(
            QueueUrl=self.settings.queue_url,
            ReceiptHandle=message["ReceiptHandle"],
        )

    def run_once(self) -> int:
        response = self.client.receive_message(
            QueueUrl=self.settings.queue_url,
            MaxNumberOfMessages=1,
            WaitTimeSeconds=1,
        )
        messages = response.get("Messages", [])
        if not messages:
            return 0
        message = messages[0]
        processed = self.dispatch(json.loads(message["Body"]))
        # Retorno normal do despacho é o ack; exceção deixa a mensagem para reentrega.
        self._delete_message(message)
        return processed

    def dispatch(self, body: Mapping[str, Any]) -> int:
        """Executa um comando já decodificado, independente do transporte que o trouxe.

        Contrato com o chamador: retorno normal significa ack (o transporte pode
        descartar a mensagem); exceção significa reentrega. Nenhum handler apaga
        mensagem — a semântica do transporte mora aqui e em `run_once`.
        """
        # Messages published before the command field are always ingestion work.
        command = body.get("command", "process_upload")
        tenant_id = body.get("tenant_id")
        if not isinstance(tenant_id, str):
            raise UnroutableMessageError("Mensagem de processamento inválida")
        if command == "extract_valuation_plate":
            # A rodada de medição não tem `job_id` e nunca terá: `Job` é vocabulário proibido
            # neste contexto delimitado (ADR-0016). Por isso o roteamento por comando vem
            # ANTES da guarda de `job_id`, que continua valendo para os quatro comandos do
            # croqui — exigi-la primeiro rejeitaria este envelope antes de alguém o ler.
            round_id = body.get("round_id")
            extraction_id = body.get("extraction_id")
            if not isinstance(round_id, str) or not isinstance(extraction_id, str):
                raise UnroutableMessageError("Mensagem de extração de medição inválida")
            return self._handle_valuation_extraction(
                round_id=round_id, extraction_id=extraction_id, tenant_id=tenant_id
            )
        job_id = body.get("job_id")
        if not isinstance(job_id, str):
            raise UnroutableMessageError("Mensagem de processamento inválida")
        if command == "export_scene_package":
            export_id = body.get("export_id")
            if not isinstance(export_id, str):
                raise UnroutableMessageError("Mensagem de exportação inválida")
            return self._handle_export(export_id=export_id, job_id=job_id, tenant_id=tenant_id)
        if command == "solve_trace_scene":
            trace_solve_id = body.get("trace_solve_id")
            if not isinstance(trace_solve_id, str):
                raise UnroutableMessageError("Mensagem de traçado inválida")
            return self._handle_trace_solve(
                trace_solve_id=trace_solve_id, job_id=job_id, tenant_id=tenant_id
            )
        if command == "answer_chat_turn":
            chat_turn_id = body.get("chat_turn_id")
            if not isinstance(chat_turn_id, str):
                raise UnroutableMessageError("Mensagem de conversa inválida")
            return self._handle_chat_turn(
                chat_turn_id=chat_turn_id, job_id=job_id, tenant_id=tenant_id
            )
        if command != "process_upload":
            raise UnroutableMessageError("Comando de processamento desconhecido")
        return self._handle_upload(job_id=job_id, tenant_id=tenant_id)

    def _handle_upload(self, *, job_id: str, tenant_id: str) -> int:
        with self.engine.connect() as connection:
            ingested = connection.execute(
                text("SELECT status FROM jobs WHERE id = :job_id AND tenant_id = :tenant_id"),
                {"job_id": job_id, "tenant_id": tenant_id},
            ).scalar_one_or_none()
            if ingested in INGESTED_JOB_STATUSES:
                # Reentrega de um job que já passou da ingestão: reprocessar baixaria o
                # documento de novo e, com providers ligados, pagaria a chamada outra vez.
                return 1
            upload = (
                connection.execute(
                    text(
                        "SELECT uploads.object_key, uploads.sha256 FROM uploads "
                        "JOIN jobs ON jobs.upload_id = uploads.id "
                        "WHERE jobs.id = :job_id AND jobs.tenant_id = :tenant_id "
                        "AND uploads.tenant_id = :tenant_id"
                    ),
                    {"job_id": job_id, "tenant_id": tenant_id},
                )
                .mappings()
                .one_or_none()
            )
            authorization = connection.execute(
                text(
                    # "authorization" is a reserved word in PostgreSQL; SQLite accepts it.
                    "SELECT consent.id FROM ai_processing_consents AS consent "
                    "JOIN tenant_ai_processing_entitlements AS entitlement "
                    "ON entitlement.id = consent.entitlement_id "
                    "WHERE consent.job_id = :job_id "
                    "AND consent.tenant_id = :tenant_id "
                    "AND consent.authorization_source = 'contract' "
                    "AND entitlement.tenant_id = :tenant_id "
                    "AND entitlement.status = 'ACTIVE'"
                ),
                {"job_id": job_id, "tenant_id": tenant_id},
            ).scalar_one_or_none()
        if upload is None:
            raise ValueError("Upload não encontrado ou tenant divergente")
        if self.settings.real_providers_enabled and authorization is None:
            self._mark_failed(
                job_id=job_id,
                tenant_id=tenant_id,
                failure_code="AI_PROCESSING_NOT_AUTHORIZED",
            )
            return 1
        try:
            uploaded_object = self.s3_client.get_object(
                Bucket=self.settings.artifact_bucket,
                Key=upload["object_key"],
            )
            uses_provider = self.provider_suite is not None or self.settings.real_providers_enabled
            validated_upload = _validate_pdf_stream(
                uploaded_object["Body"],
                expected_sha256=upload["sha256"],
                capture_first_page_preview=uses_provider,
            )
        except InvalidUploadError:
            self._mark_invalid_upload(job_id=job_id, tenant_id=tenant_id)
            return 1
        except (BotoCoreError, ClientError):
            # Redelivery owns the bounded retry policy for transient object-store failures.
            raise
        review_snapshot = None
        suite = self.provider_suite
        if (
            self.settings.real_providers_enabled
            # Suite injetada é fixture em teste ou demo: nada sai da máquina, então a
            # allowlist, que existe para controlar envio externo, não se aplica.
            and suite is None
            and upload["sha256"].lower() not in self.settings.ai_extraction_allowed_digests
        ):
            # Entitlement diz que o tenant pode pagar; a allowlist diz qual documento
            # foi autorizado a sair. São coisas diferentes e ambas precisam valer.
            self._mark_failed(
                job_id=job_id,
                tenant_id=tenant_id,
                failure_code="AI_EXTRACTION_NOT_ALLOWLISTED",
            )
            return 1
        if suite is None and self.settings.real_providers_enabled:
            suite = build_real_provider_suite(
                raw_store=S3ProtectedRawResponseStore(
                    client=self.s3_client,
                    bucket=self.settings.artifact_bucket,
                    tenant_id=tenant_id,
                    job_id=job_id,
                    sse=self.settings.storage_sse_enabled,
                )
            )
        if suite is not None:
            preview = validated_upload.first_page_preview
            if preview is None:
                raise ValueError("Preview de fixture não foi renderizado")
            with tempfile.NamedTemporaryFile(suffix=".png") as preview_file:
                preview_file.write(preview)
                preview_file.flush()
                try:
                    review_snapshot = build_provider_review_snapshot(
                        Path(preview_file.name),
                        dataset_id="synthetic-provider-contract-v1",
                        suite=suite,
                    )
                except ProviderExecutionError as error:
                    if error.code is not ProviderFailureCode.BUDGET_EXCEEDED:
                        raise
                    # Estouro de budget não é falha transitória. Sem o ack, a reentrega
                    # chamaria o provider de novo e gastaria mais — o oposto do que o
                    # teto existe para impedir.
                    self._mark_failed(
                        job_id=job_id,
                        tenant_id=tenant_id,
                        failure_code="AI_BUDGET_EXCEEDED",
                    )
                    return 1
            if validated_upload.page_count > 1:
                review_snapshot = ProviderReviewSnapshot(
                    packet=review_snapshot.packet.model_copy(
                        update={
                            "safety_notes": [
                                *review_snapshot.packet.safety_notes,
                                "PAGE_PROCESSING_LIMITED_TO_FIRST_PAGE",
                            ]
                        }
                    ),
                    associations=review_snapshot.associations,
                    proposals=review_snapshot.proposals,
                    source_image_bytes=review_snapshot.source_image_bytes,
                )
            source_image_key = f"tenants/{tenant_id}/jobs/{job_id}/review/source.png"
            self.s3_client.put_object(
                Bucket=self.settings.artifact_bucket,
                Key=source_image_key,
                Body=review_snapshot.source_image_bytes,
                ContentType="image/png",
            )

        with self.engine.begin() as connection:
            if review_snapshot is not None:
                # Redelivery of an already ingested job never replaces recorded evidence.
                with suppress(ReviewAlreadyExistsError):
                    insert_review_revision_v1(
                        connection,
                        tenant_id=tenant_id,
                        job_id=job_id,
                        packet=review_snapshot.packet,
                        associations=review_snapshot.associations,
                        proposals=review_snapshot.proposals,
                        evidence_refs={"source_image_key": source_image_key},
                        # The provider fixture carries no rectangle request: no solver runs here.
                        solver_request=None,
                        solver_blockers=[],
                        required_blocker_codes=[],
                        required_criteria_texts={},
                        created_by="offline-provider-contract-fixture",
                    )
            result = connection.execute(
                text(
                    "UPDATE jobs SET status = 'REVIEW_REQUIRED', stage = 'PREVIEWING', "
                    "page_count = :page_count, failure_code = NULL, updated_at = CURRENT_TIMESTAMP "
                    "WHERE id = :job_id AND tenant_id = :tenant_id"
                ),
                {
                    "job_id": job_id,
                    "tenant_id": tenant_id,
                    "page_count": validated_upload.page_count,
                },
            )
        if result.rowcount != 1:
            raise ValueError("Job não encontrado ou tenant divergente")
        return 1

    def _finish_export(
        self,
        *,
        export_id: str,
        tenant_id: str,
        job_id: str,
        status: str,
        job_status: str,
        package_object_key: str | None = None,
        dxf_sha256: str | None = None,
        audit_status: str | None = None,
        audit_json: dict[str, Any] | None = None,
        failure_code: str | None = None,
    ) -> None:
        audit_expression = (
            "CAST(:audit AS JSONB)" if self.engine.dialect.name == "postgresql" else "json(:audit)"
        )
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    "UPDATE export_artifacts SET status = :status, "
                    "package_object_key = :package_object_key, dxf_sha256 = :dxf_sha256, "
                    "audit_status = :audit_status, failure_code = :failure_code, "
                    f"audit_json = {audit_expression if audit_json is not None else 'NULL'}, "
                    "updated_at = CURRENT_TIMESTAMP "
                    "WHERE id = :export_id AND tenant_id = :tenant_id"
                ),
                {
                    "export_id": export_id,
                    "tenant_id": tenant_id,
                    "status": status,
                    "package_object_key": package_object_key,
                    "dxf_sha256": dxf_sha256,
                    "audit_status": audit_status,
                    "failure_code": failure_code,
                    **({"audit": json.dumps(audit_json)} if audit_json is not None else {}),
                },
            )
            connection.execute(
                text(
                    "UPDATE jobs SET status = :job_status, updated_at = CURRENT_TIMESTAMP "
                    "WHERE id = :job_id AND tenant_id = :tenant_id"
                ),
                {"job_id": job_id, "tenant_id": tenant_id, "job_status": job_status},
            )

    def _handle_export(self, *, export_id: str, job_id: str, tenant_id: str) -> int:
        """Builds, audits and publishes the CAD package exactly once per approved revision."""
        with self.engine.connect() as connection:
            artifact = (
                connection.execute(
                    text(
                        "SELECT export_artifacts.status, export_artifacts.scene_revision_id, "
                        "scene_revisions.scene AS scene, approvals.approval_json AS approval "
                        "FROM export_artifacts "
                        "JOIN scene_revisions ON scene_revisions.id = "
                        "export_artifacts.scene_revision_id "
                        "JOIN approvals ON approvals.id = export_artifacts.approval_id "
                        "WHERE export_artifacts.id = :export_id "
                        "AND export_artifacts.tenant_id = :tenant_id "
                        "AND export_artifacts.job_id = :job_id"
                    ),
                    {"export_id": export_id, "tenant_id": tenant_id, "job_id": job_id},
                )
                .mappings()
                .one_or_none()
            )
        if artifact is None:
            raise ValueError("Exportação não encontrada ou tenant divergente")
        if artifact["status"] == "COMPLETED":
            # Replay of a published package never rebuilds or re-uploads it.
            return 1

        with self.engine.begin() as connection:
            claimed = connection.execute(
                text(
                    "UPDATE export_artifacts SET status = 'RUNNING', "
                    "updated_at = CURRENT_TIMESTAMP WHERE id = :export_id "
                    "AND tenant_id = :tenant_id AND status IN ('QUEUED', 'FAILED')"
                ),
                {"export_id": export_id, "tenant_id": tenant_id},
            )
        if claimed.rowcount != 1:
            return 1

        scene_json = artifact["scene"]
        approval_json = artifact["approval"]
        if isinstance(scene_json, str):
            scene_json = json.loads(scene_json)
        if isinstance(approval_json, str):
            approval_json = json.loads(approval_json)
        try:
            scene = SceneRevision.model_validate(scene_json)
            with tempfile.TemporaryDirectory() as workspace:
                output_dir = Path(workspace)
                extra_files = []
                if approval_json is not None:
                    approval_path = output_dir / "aprovacao.json"
                    approval_path.write_text(
                        json.dumps(approval_json, ensure_ascii=False, indent=2, sort_keys=True),
                        encoding="utf-8",
                    )
                    extra_files.append(approval_path)
                export = export_scene_package(
                    scene, output_dir, extra_package_files=extra_files or None
                )
                package_key = WorkerArtifactStore(
                    client=self.s3_client,
                    bucket=self.settings.artifact_bucket,
                    sse=self.settings.storage_sse_enabled,
                ).put_export_package(
                    tenant_id=tenant_id,
                    job_id=job_id,
                    export_id=export_id,
                    path=export.package_path,
                )
        except DomainValidationError as error:
            self._finish_export(
                export_id=export_id,
                tenant_id=tenant_id,
                job_id=job_id,
                status="FAILED",
                job_status="FAILED",
                failure_code="EXPORT_AUDIT_FAILED",
                audit_json={"errors": list(error.errors)},
            )
            return 1
        except (BotoCoreError, ClientError):
            # Redelivery owns the bounded retry policy for transient object-store failures.
            raise

        self._finish_export(
            export_id=export_id,
            tenant_id=tenant_id,
            job_id=job_id,
            status="COMPLETED",
            job_status="COMPLETED",
            package_object_key=package_key,
            dxf_sha256=export.audit.dxf_sha256,
            audit_status=export.audit.status,
            audit_json={"checks": export.audit.checks, "errors": list(export.audit.errors)},
        )
        return 1

    def _write_trace_solve_result(
        self,
        *,
        trace_solve_id: str,
        tenant_id: str,
        status: str,
        solve_status: str | None = None,
        blockers: Sequence[str] = (),
        unapplied_reading_ids: Sequence[str] = (),
        residual_summary: dict[str, Any] | None = None,
        exact_entity_count: int | None = None,
        approximate_entity_count: int | None = None,
        note_count: int | None = None,
        scale_m_per_px: float | None = None,
        detail_group_scales: Mapping[str, float] | None = None,
        result_scene_revision_id: str | None = None,
        result_review_revision_id: str | None = None,
        failure_code: str | None = None,
        connection: Connection | None = None,
    ) -> None:
        """Records the outcome; the caller may share its transaction with the new revisions."""
        dialect = self.engine.dialect.name
        parameters: dict[str, Any] = {
            "trace_solve_id": trace_solve_id,
            "tenant_id": tenant_id,
            "status": status,
            "solve_status": solve_status,
            "exact_entity_count": exact_entity_count,
            "approximate_entity_count": approximate_entity_count,
            "note_count": note_count,
            "scale_m_per_px": scale_m_per_px,
            "result_scene_revision_id": result_scene_revision_id,
            "result_review_revision_id": result_review_revision_id,
            "failure_code": failure_code,
        }
        blockers_expression = _json_parameter(parameters, dialect, "blockers", list(blockers))
        unapplied_expression = _json_parameter(
            parameters, dialect, "unapplied", list(unapplied_reading_ids)
        )
        residual_expression = _json_parameter(parameters, dialect, "residuals", residual_summary)
        scales_expression = _json_parameter(
            parameters, dialect, "scales", dict(detail_group_scales or {})
        )
        statement = text(
            "UPDATE trace_solves SET status = :status, solve_status = :solve_status, "
            f"blockers_json = {blockers_expression}, "
            f"unapplied_reading_ids_json = {unapplied_expression}, "
            f"residual_summary_json = {residual_expression}, "
            f"detail_group_scales_json = {scales_expression}, "
            "exact_entity_count = :exact_entity_count, "
            "approximate_entity_count = :approximate_entity_count, "
            "note_count = :note_count, scale_m_per_px = :scale_m_per_px, "
            "result_scene_revision_id = :result_scene_revision_id, "
            "result_review_revision_id = :result_review_revision_id, "
            "failure_code = :failure_code, updated_at = CURRENT_TIMESTAMP "
            "WHERE id = :trace_solve_id AND tenant_id = :tenant_id"
        )
        if connection is not None:
            connection.execute(statement, parameters)
            return
        with self.engine.begin() as owned_connection:
            owned_connection.execute(statement, parameters)

    def _insert_traced_revisions(
        self,
        *,
        connection: Connection,
        job_id: str,
        tenant_id: str,
        base_review: RowMapping,
        scene_id: str,
        scene_payload: dict[str, Any],
        parent_scene_id: str | None,
        review_id: str,
        trace_acceptance: dict[str, Any],
    ) -> None:
        """Writes the traced scene and the review revision that records the human acceptance."""
        dialect = self.engine.dialect.name
        scene_parameters: dict[str, Any] = {
            "id": scene_id,
            "tenant_id": tenant_id,
            "job_id": job_id,
            "version": scene_payload["version"],
            "parent_revision_id": parent_scene_id,
            "created_by": TRACER_VERSION,
        }
        scene_expression = _json_parameter(scene_parameters, dialect, "scene", scene_payload)
        connection.execute(
            text(
                "INSERT INTO scene_revisions "
                "(id, tenant_id, job_id, version, parent_revision_id, scene, created_by, "
                "created_at) VALUES (:id, :tenant_id, :job_id, :version, :parent_revision_id, "
                f"{scene_expression}, :created_by, CURRENT_TIMESTAMP)"
            ),
            scene_parameters,
        )
        review_parameters: dict[str, Any] = {
            "id": review_id,
            "tenant_id": tenant_id,
            "job_id": job_id,
            "version": int(base_review["version"]) + 1,
            "parent_review_id": base_review["id"],
            "scene_revision_id": scene_id,
            "created_by": TRACER_VERSION,
        }
        columns = {
            "packet_json": _json_column(base_review["packet_json"]),
            "associations_json": _json_column(base_review["associations_json"]),
            "proposals_json": _json_column(base_review["proposals_json"]),
            "selected_associations_json": _json_column(base_review["selected_associations_json"]),
            "calibration_json": _json_column(base_review["calibration_json"]),
            "proposal_decisions_json": _json_column(base_review["proposal_decisions_json"]),
            "trace_acceptance_json": trace_acceptance,
            "evidence_refs_json": _json_column(base_review["evidence_refs_json"]),
            "solver_request_json": _json_column(base_review["solver_request_json"]),
            # Blockers do solver retangular não são resolvidos pelo traçado: mantê-los
            # evita anunciar como resolvido o que ninguém resolveu.
            "solver_blockers_json": _json_column(base_review["solver_blockers_json"]),
            "required_blocker_codes_json": _json_column(base_review["required_blocker_codes_json"]),
            "required_criteria_texts_json": _json_column(
                base_review["required_criteria_texts_json"]
            ),
        }
        expressions = {
            name: _json_parameter(review_parameters, dialect, name, value)
            for name, value in columns.items()
        }
        connection.execute(
            text(
                "INSERT INTO review_revisions "
                "(id, tenant_id, job_id, version, parent_review_id, packet_json, "
                "associations_json, proposals_json, selected_associations_json, "
                "calibration_json, proposal_decisions_json, trace_acceptance_json, "
                "evidence_refs_json, solver_request_json, solver_blockers_json, "
                "required_blocker_codes_json, required_criteria_texts_json, "
                "scene_revision_id, created_by, created_at) "
                "VALUES (:id, :tenant_id, :job_id, :version, :parent_review_id, "
                f"{expressions['packet_json']}, {expressions['associations_json']}, "
                f"{expressions['proposals_json']}, "
                f"{expressions['selected_associations_json']}, "
                f"{expressions['calibration_json']}, "
                f"{expressions['proposal_decisions_json']}, "
                f"{expressions['trace_acceptance_json']}, "
                f"{expressions['evidence_refs_json']}, "
                f"{expressions['solver_request_json']}, "
                f"{expressions['solver_blockers_json']}, "
                f"{expressions['required_blocker_codes_json']}, "
                f"{expressions['required_criteria_texts_json']}, "
                ":scene_revision_id, :created_by, CURRENT_TIMESTAMP)"
            ),
            review_parameters,
        )

    def _handle_trace_solve(self, *, trace_solve_id: str, job_id: str, tenant_id: str) -> int:
        """Solves one accepted batch trace exactly once, recording conflict as a result."""
        with self.engine.connect() as connection:
            record = (
                connection.execute(
                    text(
                        "SELECT status, base_review_revision_id, base_scene_revision_id, "
                        "acceptance_json, associations_json, note_associations_json, "
                        "derived_dimensions_json, dimension_texts_json, title, feature_id "
                        "FROM trace_solves WHERE id = :trace_solve_id "
                        "AND tenant_id = :tenant_id AND job_id = :job_id"
                    ),
                    {
                        "trace_solve_id": trace_solve_id,
                        "tenant_id": tenant_id,
                        "job_id": job_id,
                    },
                )
                .mappings()
                .one_or_none()
            )
        if record is None:
            raise ValueError("Traçado não encontrado ou tenant divergente")
        if record["status"] == "COMPLETED":
            # Replay of a recorded outcome never re-solves nor creates another revision.
            return 1

        with self.engine.begin() as connection:
            claimed = connection.execute(
                text(
                    "UPDATE trace_solves SET status = 'RUNNING', "
                    "updated_at = CURRENT_TIMESTAMP WHERE id = :trace_solve_id "
                    "AND tenant_id = :tenant_id AND status IN ('QUEUED', 'FAILED')"
                ),
                {"trace_solve_id": trace_solve_id, "tenant_id": tenant_id},
            )
        if claimed.rowcount != 1:
            return 1

        with self.engine.connect() as connection:
            base_review = (
                connection.execute(
                    text(
                        "SELECT id, version, packet_json, associations_json, proposals_json, "
                        "selected_associations_json, calibration_json, proposal_decisions_json, "
                        "evidence_refs_json, solver_request_json, solver_blockers_json, "
                        "required_blocker_codes_json, required_criteria_texts_json "
                        "FROM review_revisions "
                        "WHERE id = :review_id AND tenant_id = :tenant_id AND job_id = :job_id"
                    ),
                    {
                        "review_id": record["base_review_revision_id"],
                        "tenant_id": tenant_id,
                        "job_id": job_id,
                    },
                )
                .mappings()
                .one_or_none()
            )
            latest_review_version = connection.execute(
                text(
                    "SELECT MAX(version) FROM review_revisions "
                    "WHERE job_id = :job_id AND tenant_id = :tenant_id"
                ),
                {"job_id": job_id, "tenant_id": tenant_id},
            ).scalar_one_or_none()
            latest_scene = (
                connection.execute(
                    text(
                        "SELECT id, version FROM scene_revisions "
                        "WHERE job_id = :job_id AND tenant_id = :tenant_id "
                        "ORDER BY version DESC LIMIT 1"
                    ),
                    {"job_id": job_id, "tenant_id": tenant_id},
                )
                .mappings()
                .one_or_none()
            )
        if base_review is None or base_review["proposals_json"] is None:
            self._write_trace_solve_result(
                trace_solve_id=trace_solve_id,
                tenant_id=tenant_id,
                status="FAILED",
                failure_code="TRACE_BASE_REVISION_MISSING",
            )
            return 1
        base_scene_id = record["base_scene_revision_id"]
        current_scene_id = latest_scene["id"] if latest_scene is not None else None
        if latest_review_version != base_review["version"] or current_scene_id != base_scene_id:
            # Conflito de versão é resultado consultável, não exceção: outra decisão
            # entrou entre o aceite e a fila, e o traçado precisa ser refeito sobre ela.
            self._write_trace_solve_result(
                trace_solve_id=trace_solve_id,
                tenant_id=tenant_id,
                status="COMPLETED",
                solve_status="conflict",
                failure_code="REVISION_MOVED",
            )
            return 1

        try:
            packet = ReviewPacket.model_validate(_json_column(base_review["packet_json"]))
            proposal_set = VisionProposalSet.model_validate(
                _json_column(base_review["proposals_json"])
            )
            acceptance = TraceAcceptance.model_validate(_json_column(record["acceptance_json"]))
            derived_requests = [
                DerivedDimensionRequest.model_validate(item)
                for item in _json_column(record["derived_dimensions_json"]) or []
            ]
            # O critério exigido da revisão de leitura vira issue crítica na cena traçada,
            # exatamente como no fluxo retangular: sem isto o portão de export não o vê.
            criteria_texts = _json_column(base_review["required_criteria_texts_json"]) or {}
            required_criteria = [
                ScopeCriterion(code=code, text=criteria_texts.get(code))
                for code in _json_column(base_review["required_blocker_codes_json"]) or []
            ]
            result = solve_trace(
                packet,
                proposal_set.proposals,
                acceptance,
                required_criteria=required_criteria,
                confirmed_associations=_json_column(record["associations_json"]) or {},
                note_associations=_json_column(record["note_associations_json"]) or {},
                derived_dimension_requests=derived_requests,
                dimension_texts=_json_column(record["dimension_texts_json"]) or {},
                image_width=proposal_set.image_width_px,
                image_height=proposal_set.image_height_px,
                feature_id=str(record["feature_id"]),
                title=record["title"],
            )
        except (BotoCoreError, ClientError):
            raise
        except Exception:
            # A mensagem da exceção pode carregar evidência do cliente; só o código sai.
            self._write_trace_solve_result(
                trace_solve_id=trace_solve_id,
                tenant_id=tenant_id,
                status="FAILED",
                failure_code="TRACE_SOLVE_FAILED",
            )
            return 1

        outcome: dict[str, Any] = {
            "solve_status": result.status,
            "blockers": result.blockers,
            "unapplied_reading_ids": result.unapplied_reading_ids,
            "residual_summary": _residual_summary(result.residuals),
            "exact_entity_count": result.exact_entity_count,
            "approximate_entity_count": result.approximate_entity_count,
            "note_count": result.note_count,
            "scale_m_per_px": result.scale_m_per_px,
            "detail_group_scales": result.detail_group_scales,
        }
        if result.status != "solved_unapproved" or result.scene is None:
            self._write_trace_solve_result(
                trace_solve_id=trace_solve_id,
                tenant_id=tenant_id,
                status="COMPLETED",
                **outcome,
            )
            return 1

        scene_id = str(new_uuid7())
        review_id = str(new_uuid7())
        scene_payload = SceneRevision.model_validate(
            {
                **result.scene.model_dump(mode="json"),
                "id": scene_id,
                "job_id": job_id,
                "version": (latest_scene["version"] if latest_scene is not None else 0) + 1,
                "approved": False,
            }
        ).model_dump(mode="json")
        trace_acceptance = {
            "trace_solve_id": trace_solve_id,
            "acceptance": _json_column(record["acceptance_json"]),
            "associations": _json_column(record["associations_json"]) or {},
            "note_associations": _json_column(record["note_associations_json"]) or {},
            "derived_dimensions": _json_column(record["derived_dimensions_json"]) or [],
            "dimension_texts": _json_column(record["dimension_texts_json"]) or {},
            "solve_status": result.status,
            "scene_revision_id": scene_id,
        }
        try:
            with self.engine.begin() as connection:
                self._insert_traced_revisions(
                    connection=connection,
                    job_id=job_id,
                    tenant_id=tenant_id,
                    base_review=base_review,
                    scene_id=scene_id,
                    scene_payload=scene_payload,
                    parent_scene_id=base_scene_id,
                    review_id=review_id,
                    trace_acceptance=trace_acceptance,
                )
                self._write_trace_solve_result(
                    connection=connection,
                    trace_solve_id=trace_solve_id,
                    tenant_id=tenant_id,
                    status="COMPLETED",
                    result_scene_revision_id=scene_id,
                    result_review_revision_id=review_id,
                    **outcome,
                )
        except IntegrityError:
            # Corrida na versão: outra revisão ganhou a chave única e o traçado não vale mais.
            self._write_trace_solve_result(
                trace_solve_id=trace_solve_id,
                tenant_id=tenant_id,
                status="COMPLETED",
                solve_status="conflict",
                failure_code="REVISION_MOVED",
                blockers=result.blockers,
                unapplied_reading_ids=result.unapplied_reading_ids,
            )
        return 1

    def _write_chat_turn_result(
        self,
        *,
        chat_turn_id: str,
        tenant_id: str,
        status: str,
        answer: dict[str, Any] | None = None,
        execution: ProviderExecution | None = None,
        failure_code: str | None = None,
    ) -> None:
        """Grava o desfecho do turno com o lineage da chamada, quando houve uma.

        O lineage acompanha também a recusa: saber qual prompt e qual modelo produziram um
        rascunho recusado é exatamente o que permite corrigir o contrato depois.
        """
        dialect = self.engine.dialect.name
        usage = execution.usage if execution is not None else None
        cost = usage.estimated_cost_usd if usage is not None else None
        parameters: dict[str, Any] = {
            "chat_turn_id": chat_turn_id,
            "tenant_id": tenant_id,
            "status": status,
            "provider": execution.provider.value if execution is not None else None,
            "model_id": execution.model_id if execution is not None else None,
            "prompt_version": execution.prompt.prompt_version if execution is not None else None,
            "input_digest": execution.input_digest if execution is not None else None,
            "latency_ms": execution.latency_ms if execution is not None else None,
            "input_tokens": usage.input_tokens if usage is not None else None,
            "output_tokens": usage.output_tokens if usage is not None else None,
            "estimated_cost_usd": str(cost) if cost is not None else None,
            "raw_response_ref": execution.raw_response_ref if execution is not None else None,
            "failure_code": failure_code,
        }
        answer_expression = _json_parameter(parameters, dialect, "answer", answer)
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    "UPDATE chat_turns SET status = :status, "
                    f"answer_json = {answer_expression}, "
                    "provider = :provider, model_id = :model_id, "
                    "prompt_version = :prompt_version, input_digest = :input_digest, "
                    "latency_ms = :latency_ms, input_tokens = :input_tokens, "
                    "output_tokens = :output_tokens, "
                    "estimated_cost_usd = :estimated_cost_usd, "
                    "raw_response_ref = :raw_response_ref, failure_code = :failure_code, "
                    "updated_at = CURRENT_TIMESTAMP "
                    "WHERE id = :chat_turn_id AND tenant_id = :tenant_id"
                ),
                parameters,
            )

    def _handle_chat_turn(self, *, chat_turn_id: str, job_id: str, tenant_id: str) -> int:
        """Responde um turno de conversa exatamente uma vez, sobre a revisão-base da sessão.

        O contexto é imutável: a folha e as leituras são as da revisão que a conversa fixou
        na abertura, não as da revisão corrente. A resposta é observação com rascunhos
        tipados — nenhum ato é submetido aqui, por construção.
        """
        with self.engine.connect() as connection:
            record = (
                connection.execute(
                    text(
                        "SELECT chat_turns.status AS turn_status, chat_turns.question_text, "
                        "chat_turns.anchor_refs_json, "
                        "chat_sessions.base_review_revision_id AS base_review_revision_id "
                        "FROM chat_turns "
                        "JOIN chat_sessions ON chat_sessions.id = chat_turns.session_id "
                        "WHERE chat_turns.id = :chat_turn_id "
                        "AND chat_turns.tenant_id = :tenant_id "
                        "AND chat_turns.job_id = :job_id"
                    ),
                    {"chat_turn_id": chat_turn_id, "tenant_id": tenant_id, "job_id": job_id},
                )
                .mappings()
                .one_or_none()
            )
        if record is None:
            raise ValueError("Turno de conversa não encontrado ou tenant divergente")
        if record["turn_status"] == "COMPLETED":
            # Replay de um turno já respondido não chama provider nem reescreve a resposta.
            return 1

        with self.engine.begin() as connection:
            claimed = connection.execute(
                text(
                    "UPDATE chat_turns SET status = 'RUNNING', "
                    "updated_at = CURRENT_TIMESTAMP WHERE id = :chat_turn_id "
                    "AND tenant_id = :tenant_id AND status IN ('QUEUED', 'FAILED')"
                ),
                {"chat_turn_id": chat_turn_id, "tenant_id": tenant_id},
            )
        if claimed.rowcount != 1:
            return 1

        suite = self.provider_suite
        if suite is None:
            # Fatia 1 é 100% offline: sem suíte injetada nenhum provider é construído,
            # nem com `real_providers_enabled` ligado. Nada sai da máquina por omissão.
            self._write_chat_turn_result(
                chat_turn_id=chat_turn_id,
                tenant_id=tenant_id,
                status="FAILED",
                failure_code="CHAT_PROVIDER_UNAVAILABLE",
            )
            return 1

        try:
            with self.engine.connect() as connection:
                base_review = (
                    connection.execute(
                        text(
                            "SELECT packet_json, proposals_json, evidence_refs_json "
                            "FROM review_revisions WHERE id = :review_id "
                            "AND tenant_id = :tenant_id AND job_id = :job_id"
                        ),
                        {
                            "review_id": record["base_review_revision_id"],
                            "tenant_id": tenant_id,
                            "job_id": job_id,
                        },
                    )
                    .mappings()
                    .one_or_none()
                )
            if base_review is None:
                raise ValueError("revisão-base da conversa indisponível")
            packet = ReviewPacket.model_validate(_json_column(base_review["packet_json"]))
            proposal_set = (
                VisionProposalSet.model_validate(_json_column(base_review["proposals_json"]))
                if base_review["proposals_json"] is not None
                else None
            )
            anchors = _json_column(record["anchor_refs_json"]) or {}
            anchored_reading_ids = list(anchors.get("reading_ids", []))
            anchored_proposal_ids = list(anchors.get("proposal_ids", []))
            readings_by_id = {reading.id: reading for reading in packet.readings}
            proposals_by_id = (
                {proposal.id: proposal for proposal in proposal_set.proposals}
                if proposal_set is not None
                else {}
            )
            text_payload = build_chat_text_payload(
                question=str(record["question_text"]),
                readings=[
                    readings_by_id[reading_id]
                    for reading_id in anchored_reading_ids
                    if reading_id in readings_by_id
                ],
                proposals=[
                    proposals_by_id[proposal_id]
                    for proposal_id in anchored_proposal_ids
                    if proposal_id in proposals_by_id
                ],
            )
            evidence_refs = _json_column(base_review["evidence_refs_json"]) or {}
            source_image_key = evidence_refs.get("source_image_key")
            if not isinstance(source_image_key, str):
                raise ValueError("revisão-base sem imagem de página")
            image_bytes = self.s3_client.get_object(
                Bucket=self.settings.artifact_bucket, Key=source_image_key
            )["Body"].read()
            execution = suite.bedrock_anthropic.execute(
                build_image_text_request(
                    PromptTask.REVIEW_CHAT,
                    image_bytes=image_bytes,
                    text_payload=text_payload,
                    image_width_px=(
                        proposal_set.image_width_px if proposal_set is not None else None
                    ),
                    image_height_px=(
                        proposal_set.image_height_px if proposal_set is not None else None
                    ),
                )
            )
            answer = execution.output
            if not isinstance(answer, ReviewChatOutput):
                raise ValueError("saída fora do contrato de conversa")
            unknown = chat_unknown_references(
                answer,
                reading_ids=set(readings_by_id),
                proposal_ids=set(proposals_by_id),
            )
        except (BotoCoreError, ClientError):
            # Redelivery owns the bounded retry policy for transient object-store failures.
            raise
        except Exception:
            # A mensagem da exceção pode carregar evidência do cliente; só o código sai.
            self._write_chat_turn_result(
                chat_turn_id=chat_turn_id,
                tenant_id=tenant_id,
                status="FAILED",
                failure_code="CHAT_ANSWER_FAILED",
            )
            return 1

        if unknown:
            # Id inventado recusa o turno INTEIRO: uma resposta que cita o que não existe
            # não é meia resposta aproveitável, é resposta sobre outra folha.
            self._write_chat_turn_result(
                chat_turn_id=chat_turn_id,
                tenant_id=tenant_id,
                status="FAILED",
                execution=execution,
                failure_code="CHAT_ACT_UNKNOWN_REFERENCE",
            )
            return 1

        self._write_chat_turn_result(
            chat_turn_id=chat_turn_id,
            tenant_id=tenant_id,
            status="COMPLETED",
            answer=answer.model_dump(mode="json"),
            execution=execution,
        )
        return 1

    # -- Medição de obra: extração paga da legenda (ADR-0028 D7) ------------------------

    def _valuation_extraction_adapter(self, arm_spec: str) -> ProviderAdapter:
        """Braço pago da extração, ou a recusa declarada de por que ele não existe.

        O adapter injetado é fixture de teste ou demo — nada sai da máquina —, e por isso
        dispensa o gate de teto de gasto e credencial, exatamente como a `ProviderSuite`
        injetada dispensa a allowlist na ingestão. Sem injeção, a pré-checagem de ambiente
        vale integralmente: sem teto de gasto declarado, nenhuma chamada é tentada.
        """
        if self.valuation_extraction_adapter is not None:
            return self.valuation_extraction_adapter
        unavailable = extraction_unavailable(arm_spec)
        if unavailable is not None:
            raise unavailable
        _name, _model_id, adapter = build_extraction_adapter(arm_spec)
        return adapter

    def _put_round_png(self, *, object_key: str, payload: bytes) -> None:
        self.s3_client.put_object(
            Bucket=self.settings.artifact_bucket,
            Key=object_key,
            Body=payload,
            ContentType="image/png",
            **({"ServerSideEncryption": "AES256"} if self.settings.storage_sse_enabled else {}),
        )

    def _settle_valuation_extraction(
        self, *, round_id: str, extraction_id: str, tenant_id: str, failure_code: str
    ) -> None:
        """Fecha a extração como `failed`: nenhuma revisão, versão da rodada intacta.

        O `WHERE` repete o par extração+estado do claim: um desfecho tardio nunca sobrescreve
        uma extração posterior que já tomou a rodada para si. Falha em não casar linha
        nenhuma é justamente o caso em que não há nada a fechar.
        """
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    "UPDATE valuation_rounds SET extraction_status = 'failed', "
                    "extraction_failure_code = :failure_code, "
                    "extraction_updated_at = CURRENT_TIMESTAMP, "
                    "updated_at = CURRENT_TIMESTAMP "
                    "WHERE id = :round_id AND tenant_id = :tenant_id "
                    "AND extraction_id = :extraction_id AND extraction_status = 'running'"
                ),
                {
                    "round_id": round_id,
                    "tenant_id": tenant_id,
                    "extraction_id": extraction_id,
                    "failure_code": failure_code,
                },
            )

    def _publish_valuation_extraction(
        self,
        *,
        round_id: str,
        extraction_id: str,
        tenant_id: str,
        packet: dict[str, Any],
        registration: dict[str, Any],
        lineage: dict[str, Any],
        refs: dict[str, str],
        digests: dict[str, str],
        page_count: int,
    ) -> None:
        """Grava a revisão e fecha a extração na MESMA transação.

        Pacote publicado com a rodada ainda `running`, ou rodada `done` sem revisão, seriam
        estados que a tela não sabe ler — e nenhum dos dois é recuperável por retentativa.
        A revisão copia da cabeça o que a extração não produziu, porque revisão é
        append-only e o que o ato não mudou viaja idêntico (ADR-0028 D2).
        """
        dialect = self.engine.dialect.name
        with self.engine.begin() as connection:
            head = (
                connection.execute(
                    text(
                        "SELECT id, version, code_suggestions_json, code_assignments_json, "
                        "valuation_json, amendment_dossier_json, artifact_refs_json, "
                        "artifact_digests_json FROM valuation_round_revisions "
                        "WHERE round_id = :round_id AND tenant_id = :tenant_id "
                        "ORDER BY version DESC LIMIT 1"
                    ),
                    {"round_id": round_id, "tenant_id": tenant_id},
                )
                .mappings()
                .one_or_none()
            )
            carried_refs = dict(_json_column(head["artifact_refs_json"]) or {}) if head else {}
            carried_digests = (
                dict(_json_column(head["artifact_digests_json"]) or {}) if head else {}
            )
            carried_refs.update(refs)
            carried_digests.update(digests)
            parameters: dict[str, Any] = {
                "id": str(new_uuid7()),
                "tenant_id": tenant_id,
                "round_id": round_id,
                "version": 1 if head is None else int(head["version"]) + 1,
                "parent_revision_id": None if head is None else head["id"],
                "created_by": VALUATION_EXTRACTION_VERSION,
            }
            columns = {
                "takeoff_packet_json": packet,
                "takeoff_registration_json": registration,
                "code_suggestions_json": _json_column(head["code_suggestions_json"])
                if head
                else None,
                "code_assignments_json": _json_column(head["code_assignments_json"])
                if head
                else None,
                "valuation_json": _json_column(head["valuation_json"]) if head else None,
                "amendment_dossier_json": _json_column(head["amendment_dossier_json"])
                if head
                else None,
                "extraction_lineage_json": lineage,
                "artifact_refs_json": carried_refs,
                "artifact_digests_json": carried_digests,
            }
            expressions = {
                name: _json_parameter(parameters, dialect, name, value)
                for name, value in columns.items()
            }
            connection.execute(
                text(
                    "INSERT INTO valuation_round_revisions "
                    "(id, tenant_id, round_id, version, parent_revision_id, takeoff_packet_json, "
                    "takeoff_registration_json, code_suggestions_json, code_assignments_json, "
                    "valuation_json, amendment_dossier_json, extraction_lineage_json, "
                    "artifact_refs_json, artifact_digests_json, created_by, created_at) "
                    "VALUES (:id, :tenant_id, :round_id, :version, :parent_revision_id, "
                    f"{expressions['takeoff_packet_json']}, "
                    f"{expressions['takeoff_registration_json']}, "
                    f"{expressions['code_suggestions_json']}, "
                    f"{expressions['code_assignments_json']}, "
                    f"{expressions['valuation_json']}, "
                    f"{expressions['amendment_dossier_json']}, "
                    f"{expressions['extraction_lineage_json']}, "
                    f"{expressions['artifact_refs_json']}, "
                    f"{expressions['artifact_digests_json']}, "
                    ":created_by, CURRENT_TIMESTAMP)"
                ),
                parameters,
            )
            published = connection.execute(
                text(
                    "UPDATE valuation_rounds SET extraction_status = 'done', "
                    "extraction_failure_code = NULL, plate_page_count = :page_count, "
                    "version = version + 1, extraction_updated_at = CURRENT_TIMESTAMP, "
                    "updated_at = CURRENT_TIMESTAMP "
                    "WHERE id = :round_id AND tenant_id = :tenant_id "
                    "AND extraction_id = :extraction_id AND extraction_status = 'running'"
                ),
                {
                    "round_id": round_id,
                    "tenant_id": tenant_id,
                    "extraction_id": extraction_id,
                    "page_count": page_count,
                },
            )
            if published.rowcount != 1:
                # Dentro da transação de propósito: levantar aqui desfaz a revisão recém
                # inserida, em vez de deixar um pacote publicado numa rodada que outra
                # extração já tomou.
                raise ValueError("Rodada de medição saiu do estado de extração em curso")

    def _extract_valuation_plate(
        self, *, round_id: str, extraction_id: str, tenant_id: str
    ) -> None:
        """Ingere a página da prancha, extrai a legenda e publica o pacote da rodada.

        Toda a escrita de disco acontece num diretório temporário desta tarefa; o que
        sobrevive são dois PNGs sob o prefixo do tenant no object store e uma revisão nova.
        """
        with self.engine.connect() as connection:
            record = (
                connection.execute(
                    text(
                        "SELECT plate_object_key, plate_source_sha256 FROM valuation_rounds "
                        "WHERE id = :round_id AND tenant_id = :tenant_id"
                    ),
                    {"round_id": round_id, "tenant_id": tenant_id},
                )
                .mappings()
                .one_or_none()
            )
        if record is None or not record["plate_object_key"]:
            raise ValuationValidationError(
                "ROUND_STAGE_NOT_READY",
                "a rodada não tem prancha associada para extrair",
                {"round_id": round_id},
            )
        arm_spec = extraction_arm_spec()
        adapter = self._valuation_extraction_adapter(arm_spec)

        with tempfile.TemporaryDirectory() as workspace:
            # O nome do diretório vira `plate_id` do pacote (`round_extraction.dataset_id`),
            # então ele identifica a RODADA — nunca um temporário aleatório do sistema.
            workdir = Path(workspace) / f"rodada-{round_id}"
            workdir.mkdir()
            body = self.s3_client.get_object(
                Bucket=self.settings.artifact_bucket, Key=str(record["plate_object_key"])
            )["Body"]
            with closing(body):
                payload = cast(bytes, body.read(MAX_PLATE_PDF_BYTES + 1))
            if len(payload) > MAX_PLATE_PDF_BYTES:
                raise upload_invalid(
                    "a prancha armazenada excede o limite de ingestão",
                    {"max_bytes": MAX_PLATE_PDF_BYTES},
                )
            manifest = ingest_plate_upload(workdir, filename=PLATE_PDF_FILENAME, payload=payload)
            if manifest.source_sha256 != str(record["plate_source_sha256"]):
                # O digest declarado no presign é o que o orçamentista consentiu; um objeto
                # que não o reproduz não é a prancha dele.
                raise upload_invalid(
                    "a prancha armazenada diverge do digest declarado no upload",
                    {"round_id": round_id},
                )
            result = extract_legend_from_upload(workdir, manifest, adapter)
            image_path = workdir / manifest.pages[PLATE_PAGE_NUMBER - 1].render_file
            # Overlay renderizado ANTES de qualquer publicação, como em `cli._publish_takeoff`:
            # pacote sem overlay não é meio caminho aceitável — é o overlay que mostra ao
            # orçamentista de onde cada número foi lido.
            overlay_path = workdir / "takeoff-overlay.png"
            save_takeoff_overlay(render_takeoff_overlay(image_path, result.packet), overlay_path)
            image_bytes = image_path.read_bytes()
            overlay_bytes = overlay_path.read_bytes()

        plate_key = plate_image_object_key(tenant_id=tenant_id, round_id=round_id)
        overlay_key = takeoff_overlay_object_key(tenant_id=tenant_id, round_id=round_id)
        self._put_round_png(object_key=plate_key, payload=image_bytes)
        self._put_round_png(object_key=overlay_key, payload=overlay_bytes)

        lineage: dict[str, Any] = {
            "worker_version": VALUATION_EXTRACTION_VERSION,
            "arm": arm_spec,
            "plate_id": result.packet.plate_id,
            "page_number": result.packet.page_number,
            "image_sha256": result.packet.image_sha256,
            "consented_source_sha256": result.source_sha256,
            "consent": "upload da prancha pelo orçamentista na sessão autenticada da API /v1",
            "extracted_at": datetime.now(UTC).isoformat(),
            "execution": execution_payload(result.execution),
        }
        self._publish_valuation_extraction(
            round_id=round_id,
            extraction_id=extraction_id,
            tenant_id=tenant_id,
            packet=result.packet.model_dump(mode="json"),
            registration=dict(registration_payload(result.registration)),
            lineage=lineage,
            refs={PLATE_IMAGE_REF: plate_key, TAKEOFF_OVERLAY_REF: overlay_key},
            digests={
                PLATE_IMAGE_DIGEST: result.packet.image_sha256,
                TAKEOFF_OVERLAY_DIGEST: hashlib.sha256(overlay_bytes).hexdigest(),
            },
            page_count=manifest.page_count,
        )

    def _handle_valuation_extraction(
        self, *, round_id: str, extraction_id: str, tenant_id: str
    ) -> int:
        """Executa a extração paga da legenda no máximo UMA vez por comando enfileirado.

        O claim é um `UPDATE` condicional, e não um `SELECT` seguido de escrita: duas
        entregas simultâneas do mesmo envelope passariam pela leitura, e o provider seria
        pago duas vezes. `rowcount != 1` significa que outra entrega já levou o trabalho —
        ou que a extração não está mais em fila — e o retorno normal é o ack sem trabalho.

        Nenhuma falha reenfileira: depois do claim a rodada está `running`, e uma reentrega
        encontraria o claim fechado e não faria nada. Por isso todo desfecho é declarado —
        `done` com o pacote, ou `failed` com o código —, e a retomada é um ato explícito do
        orçamentista, que é também o único que pode decidir pagar de novo.
        """
        with self.engine.begin() as connection:
            claimed = connection.execute(
                text(
                    "UPDATE valuation_rounds SET extraction_status = 'running', "
                    "extraction_updated_at = CURRENT_TIMESTAMP, "
                    "updated_at = CURRENT_TIMESTAMP "
                    "WHERE id = :round_id AND tenant_id = :tenant_id "
                    "AND extraction_id = :extraction_id AND extraction_status = 'queued'"
                ),
                {"round_id": round_id, "tenant_id": tenant_id, "extraction_id": extraction_id},
            )
        if claimed.rowcount != 1:
            return 1

        try:
            self._extract_valuation_plate(
                round_id=round_id, extraction_id=extraction_id, tenant_id=tenant_id
            )
        except Exception as error:
            # A mensagem da exceção pode carregar evidência da prancha; só o código sai.
            self._settle_valuation_extraction(
                round_id=round_id,
                extraction_id=extraction_id,
                tenant_id=tenant_id,
                failure_code=extraction_failure_code(error),
            )
        return 1


def run_local_worker_once(*, provider_suite: ProviderSuite | None = None) -> int:
    """Consome uma mensagem local; a suíte só existe quando o chamador a injeta."""
    return LocalQueueWorker(
        LocalWorkerSettings.from_environment(), provider_suite=provider_suite
    ).run_once()
