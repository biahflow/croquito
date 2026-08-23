"""Leitura explícita de foto vinculada ao job (F-030, T2)."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, cast

from croquito_api.database import (
    AiProcessingAuthorizationRecord,
    Database,
    FieldEvidenceAnalysisRecord,
    JobFieldPhotoRecord,
    JobRecord,
    ProjectRecord,
    TenantAiProcessingEntitlementRecord,
    UploadRecord,
)
from croquito_worker.local_queue import LocalQueueWorker, LocalWorkerSettings
from croquito_worker.providers import (
    FieldPhotoClassificationOutput,
    ProviderExecution,
    ProviderName,
    ProviderRequest,
    ProviderSuite,
    ProviderUsage,
)
from tests.fakes import FakeObjectStore, FakeQueue
from tests.worker.test_survey_photo_analysis import CountingAdapter, sharp_photo

TENANT = "tenant-field-worker"
JOB_ID = "00000000-0000-7000-8000-000000000911"
PHOTO_ID = "00000000-0000-7000-8000-000000000912"
ANALYSIS_ID = "00000000-0000-7000-8000-000000000913"


def _seed(
    tmp_path: Path, *, authorized: bool = False, task: str = "reading"
) -> tuple[str, FakeObjectStore, str]:
    image = sharp_photo()
    digest = hashlib.sha256(image).hexdigest()
    media_key = f"tenants/{TENANT}/jobs/{JOB_ID}/field-evidence/media/{digest}"
    artifact_key = (
        f"tenants/{TENANT}/jobs/{JOB_ID}/field-evidence/analysis/standalone/{PHOTO_ID}/{task}.json"
    )
    database_url = f"sqlite+pysqlite:///{tmp_path / 'field-worker.db'}"
    database = Database(database_url)
    database.create_schema()
    now = datetime.now(UTC)
    with database.sessions.begin() as session:
        session.add(
            ProjectRecord(
                id="project-field-worker",
                tenant_id=TENANT,
                name="Projeto",
                default_unit="m",
                created_by="seed",
                expires_at=now,
            )
        )
        session.add(
            UploadRecord(
                id="upload-field-worker",
                tenant_id=TENANT,
                object_key=f"tenants/{TENANT}/uploads/source.pdf",
                filename="source.pdf",
                content_type="application/pdf",
                size_bytes=1,
                sha256="a" * 64,
            )
        )
        session.flush()
        session.add(
            JobRecord(
                id=JOB_ID,
                tenant_id=TENANT,
                project_id="project-field-worker",
                upload_id="upload-field-worker",
                status="REVIEW_REQUIRED",
                stage="PREVIEWING",
                expires_at=now,
            )
        )
        session.flush()
        session.add(
            JobFieldPhotoRecord(
                id=PHOTO_ID,
                tenant_id=TENANT,
                job_id=JOB_ID,
                sha256=digest,
                mime_type="image/png",
                byte_size=len(image),
                object_key=media_key,
                anchor_text="Muro dos fundos",
                status="CONFIRMED",
                created_by="reviewer",
            )
        )
        session.add(
            FieldEvidenceAnalysisRecord(
                id=ANALYSIS_ID,
                tenant_id=TENANT,
                job_id=JOB_ID,
                origin="standalone",
                evidence_id=PHOTO_ID,
                task=task,
                status="QUEUED",
                artifact_key=artifact_key,
                requested_by="reviewer",
            )
        )
        if authorized:
            session.add(
                TenantAiProcessingEntitlementRecord(
                    id="entitlement-field-worker",
                    tenant_id=TENANT,
                    status="ACTIVE",
                    agreement_reference="contract-field-worker",
                    authorized_by="operator",
                    authorized_at=now,
                )
            )
            session.flush()
            session.add(
                AiProcessingAuthorizationRecord(
                    id="authorization-field-worker",
                    tenant_id=TENANT,
                    job_id=JOB_ID,
                    accepted_by="operator",
                    notice_version="contractual-entitlement-v1",
                    providers_json=["anthropic"],
                    global_processing=True,
                    retention_days=7,
                    authorization_source="contract",
                    entitlement_id="entitlement-field-worker",
                    agreement_reference="contract-field-worker",
                )
            )
    store = FakeObjectStore()
    store.put_direct(object_key=media_key, body=image, content_type="image/png")
    return database_url, store, artifact_key


def _worker(
    database_url: str,
    store: FakeObjectStore,
    *,
    primary: CountingAdapter | ClassificationAdapter | None = None,
) -> LocalQueueWorker:
    worker = LocalQueueWorker(
        LocalWorkerSettings(
            database_url=database_url,
            queue_url="http://localstack/queue",
            aws_region="sa-east-1",
            aws_endpoint_url="http://localstack",
        ),
        provider_suite=(ProviderSuite(anthropic=primary) if primary is not None else None),
    )
    worker.client = FakeQueue()
    worker.s3_client = store
    return worker


class ClassificationAdapter:
    """Provider sintético estrito; nenhum teste desta suíte acessa a rede."""

    def __init__(self) -> None:
        self.calls: list[ProviderRequest] = []

    def execute(self, request: ProviderRequest) -> ProviderExecution:
        self.calls.append(request)
        return ProviderExecution(
            provider=ProviderName.ANTHROPIC,
            model_id="claude-opus-5",
            prompt=request.prompt,
            input_digest=request.image_sha256,
            latency_ms=3,
            usage=ProviderUsage(estimated_cost_usd=Decimal("0.75")),
            output=FieldPhotoClassificationOutput(
                category="MURO",
                description="Muro de alvenaria visível.",
                topology_notes=["Portão junto ao muro."],
                confidence="high",
            ),
        )


def _message(**overrides: Any) -> dict[str, Any]:
    return {
        "command": "analyze_field_evidence",
        "analysis_id": ANALYSIS_ID,
        "job_id": JOB_ID,
        "tenant_id": TENANT,
        **overrides,
    }


def test_leitura_explicitamente_pedida_faz_passe_offline_sem_provider(tmp_path: Path) -> None:
    database_url, store, artifact_key = _seed(tmp_path)
    worker = _worker(database_url, store)

    assert worker.dispatch(_message()) == 1

    document = cast(dict[str, Any], json.loads(store.body(artifact_key)))
    assert document["schema"] == "field-evidence-reading/1"
    assert document["provider_pass"] == "skipped_disabled"
    assert document["quality"]["width_px"] == 1024
    assert document["readings"] == []
    assert not {"measurement", "geometry", "entity", "precision", "blocker"} & set(document)
    database = Database(database_url)
    with database.sessions() as session:
        state = session.get(FieldEvidenceAnalysisRecord, ANALYSIS_ID)
        assert state is not None and state.status == "PROCESSED"


def test_worker_deduplica_estado_processado_sem_repetir_provider(tmp_path: Path) -> None:
    database_url, store, artifact_key = _seed(tmp_path, authorized=True)
    primary = CountingAdapter()
    worker = _worker(database_url, store, primary=primary)

    assert worker.dispatch(_message()) == 1
    first = store.body(artifact_key)
    assert worker.dispatch(_message()) == 0

    assert len(primary.calls) == 1
    assert store.body(artifact_key) == first
    document = cast(dict[str, Any], json.loads(first))
    assert len(document["readings"]) == 1
    reading = document["readings"][0]
    assert reading["id"].startswith("fpr_")
    assert not {"bbox", "x", "y", "confirmed", "status"} & set(reading)


def test_sem_snapshot_do_job_adapter_injetado_nao_recebe_foto(tmp_path: Path) -> None:
    database_url, store, artifact_key = _seed(tmp_path, authorized=False)
    primary = CountingAdapter()
    worker = _worker(database_url, store, primary=primary)

    assert worker.dispatch(_message()) == 1

    document = cast(dict[str, Any], json.loads(store.body(artifact_key)))
    assert document["provider_pass"] == "skipped_no_entitlement"
    assert primary.calls == []


def test_classificacao_nasce_rascunho_sem_medida_geometria_ou_fallback(tmp_path: Path) -> None:
    database_url, store, artifact_key = _seed(tmp_path, authorized=True, task="classification")
    primary = ClassificationAdapter()
    worker = _worker(database_url, store, primary=primary)

    assert worker.dispatch(_message()) == 1

    document = cast(dict[str, Any], json.loads(store.body(artifact_key)))
    assert document["schema"] == "field-evidence-classification/1"
    assert document["classification"] == {
        "category": "MURO",
        "description": "Muro de alvenaria visível.",
        "topology_notes": ["Portão junto ao muro."],
        "confidence": "high",
    }
    assert document["lineage"]["model_id"] == "claude-opus-5"
    assert len(primary.calls) == 1
    assert not {
        "measurement",
        "measurements",
        "geometry",
        "entity",
        "entities",
        "precision",
        "blocker",
        "blockers",
    } & set(document)
    database = Database(database_url)
    with database.sessions() as session:
        state = session.get(FieldEvidenceAnalysisRecord, ANALYSIS_ID)
        assert state is not None and state.status == "DRAFT"

    # Estado terminal: reentrega não escolhe resultado melhor nem custa outra chamada.
    assert worker.dispatch(_message()) == 0
    assert len(primary.calls) == 1
