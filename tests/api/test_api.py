import base64
import hashlib
import json
import math
import re
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, cast, get_args
from uuid import UUID

import pytest
from botocore.exceptions import BotoCoreError
from fastapi.testclient import TestClient
from sqlalchemy import select

from croquito_api.config import ApiSettings
from croquito_api.database import (
    AiProcessingAuthorizationRecord,
    ApprovalRecord,
    AuditRecord,
    ChatSessionRecord,
    ChatTurnRecord,
    Database,
    ExportArtifactRecord,
    IdempotencyRecord,
    JobRecord,
    ProjectRecord,
    ProposalDecisionRecord,
    ReviewDecisionRecord,
    ReviewRevisionRecord,
    RevisionRecord,
    TraceSolveRecord,
    UploadRecord,
)
from croquito_api.main import UPLOAD_CONTENT_TYPES, PresignUploadRequest, create_app
from croquito_core.ids import new_uuid7
from croquito_core.models import (
    Entity,
    EntityKind,
    LayerName,
    LineGeometry,
    Measurement,
    MeasurementKind,
    Point2D,
    Precision,
    Provenance,
    SceneRevision,
    UnitCode,
)
from croquito_worker.association import AssociationSet
from croquito_worker.association_confidence import CONFIDENCE_SCORE_VERSION
from croquito_worker.auto_association import AutoAssociationMode, apply_auto_association
from croquito_worker.criteria import FALLBACK_CRITERION_MESSAGE
from croquito_worker.review import (
    DimensionReading,
    EvidenceRegion,
    HumanDecision,
    PixelBox,
    ReadingStatus,
    ReviewPacket,
)
from croquito_worker.vision import (
    PixelCircle,
    PixelLine,
    PixelPoint,
    PixelPolyline,
    VisionProposal,
    VisionProposalSet,
)
from tests.fakes import FakeObjectStore, FakeQueue, synthetic_pdf

CRITERION_TEXT = "Perímetro, linha central, círculo, áreas e gols são entidades CAD limpas."


def _client(tmp_path: Path) -> TestClient:
    database = Database(f"sqlite+pysqlite:///{tmp_path / 'api.db'}")
    database.create_schema()
    settings = ApiSettings(
        database_url=f"sqlite+pysqlite:///{tmp_path / 'api.db'}",
        artifact_bucket="croquito-test-artifacts",
        aws_region="sa-east-1",
        aws_endpoint_url="http://localhost:4566",
        queue_url=None,
        oidc_issuer=None,
        oidc_audience=None,
        web_origin="http://localhost:5173",
        allow_test_tokens=True,
    )
    app = create_app(settings=settings, database=database)
    app.state.artifact_store = FakeObjectStore()
    return TestClient(app)


def _presign_and_put(
    client: TestClient,
    *,
    tenant: str = "tenant-a",
    filename: str = "levantamento.pdf",
    idempotency_key: str = "test-request-001",
    stored_body: bytes | None = None,
) -> dict[str, Any]:
    """Presigns declaring the real digest, then stores the bytes the browser would PUT."""
    pdf = synthetic_pdf()
    presign = client.post(
        "/v1/uploads/presign",
        headers={**_headers(tenant), "Idempotency-Key": idempotency_key},
        json={
            "filename": filename,
            "content_type": "application/pdf",
            "size_bytes": len(pdf),
            "sha256": hashlib.sha256(pdf).hexdigest(),
        },
    )
    assert presign.status_code == 200
    store = cast(FakeObjectStore, cast(Any, client.app).state.artifact_store)
    store.put_direct(
        object_key=presign.json()["object_key"],
        body=pdf if stored_body is None else stored_body,
    )
    return cast(dict[str, Any], presign.json())


def _headers(tenant_id: str, roles: str = "engineer") -> dict[str, str]:
    return {
        "Authorization": f"Bearer test:{tenant_id}:reviewer:{roles}",
        "Idempotency-Key": "test-request-001",
    }


def test_health_and_metadata() -> None:
    client = TestClient(create_app())

    health = client.get("/healthz")
    metadata = client.get("/v1/meta")

    assert health.status_code == 200
    assert health.json() == {"status": "ok"}
    assert metadata.status_code == 200
    assert metadata.json()["scene_schema_version"] == "1.0.0"


def test_real_provider_job_requires_and_persists_contractual_entitlement(tmp_path: Path) -> None:
    database = Database(f"sqlite+pysqlite:///{tmp_path / 'consent.db'}")
    database.create_schema()
    settings = ApiSettings(
        database_url=f"sqlite+pysqlite:///{tmp_path / 'consent.db'}",
        artifact_bucket="test",
        aws_region="sa-east-1",
        aws_endpoint_url="http://localhost:4566",
        queue_url=None,
        oidc_issuer=None,
        oidc_audience=None,
        web_origin="http://localhost:5173",
        allow_test_tokens=True,
        real_providers_enabled=True,
    )
    app = create_app(settings=settings, database=database)
    app.state.artifact_store = FakeObjectStore()
    client = TestClient(app)
    upload = _presign_and_put(client, filename="consent.pdf")
    payload = {"upload_id": upload["upload_id"], "project_name": "Contrato"}

    blocked = client.post("/v1/jobs", headers=_headers("tenant-a"), json=payload)
    assert blocked.status_code == 403
    assert blocked.json()["detail"]["code"] == "AI_PROCESSING_NOT_AUTHORIZED"

    forbidden = client.put(
        "/v1/platform/tenants/tenant-a/ai-processing-entitlement",
        headers={**_headers("tenant-a"), "Idempotency-Key": "tenant-entitlement-forbidden"},
        json={"enabled": True, "agreement_reference": "ctr-tenant-a-v1"},
    )
    assert forbidden.status_code == 403

    entitlement = client.put(
        "/v1/platform/tenants/tenant-a/ai-processing-entitlement",
        headers={
            **_headers("platform", "platform_operator"),
            "Idempotency-Key": "tenant-entitlement-enabled",
        },
        json={"enabled": True, "agreement_reference": "ctr-tenant-a-v1"},
    )
    assert entitlement.status_code == 200
    assert entitlement.json()["enabled"] is True

    accepted = client.post(
        "/v1/jobs",
        headers={**_headers("tenant-a"), "Idempotency-Key": "contract-accepted"},
        json=payload,
    )
    assert accepted.status_code == 201
    with database.sessions() as session:
        authorization = session.query(AiProcessingAuthorizationRecord).one()
        assert authorization.job_id == accepted.json()["job_id"]
        assert authorization.authorization_source == "contract"
        assert authorization.agreement_reference == "ctr-tenant-a-v1"
        assert authorization.providers_json == ["openai", "anthropic"]

    revoked = client.put(
        "/v1/platform/tenants/tenant-a/ai-processing-entitlement",
        headers={
            **_headers("platform", "platform_operator"),
            "Idempotency-Key": "tenant-entitlement-revoked",
        },
        json={"enabled": False},
    )
    assert revoked.status_code == 200
    assert revoked.json()["enabled"] is False

    second_upload = _presign_and_put(
        client,
        filename="contrato-revogado.pdf",
        idempotency_key="contract-revoked-upload",
    )
    revoked_job = client.post(
        "/v1/jobs",
        headers={**_headers("tenant-a"), "Idempotency-Key": "contract-revoked-job"},
        json={"upload_id": second_upload["upload_id"], "project_name": "Revogado"},
    )
    assert revoked_job.status_code == 403
    assert revoked_job.json()["detail"]["code"] == "AI_PROCESSING_NOT_AUTHORIZED"


def test_scene_schema_is_exposed() -> None:
    client = TestClient(create_app())

    response = client.get("/v1/schemas/scene")

    assert response.status_code == 200
    assert response.json()["title"] == "SceneRevision"
    assert "entities" in response.json()["properties"]


def test_me_returns_subject_tenant_and_sorted_roles_without_requiring_a_role(
    tmp_path: Path,
) -> None:
    client = _client(tmp_path)

    plain = client.get("/v1/me", headers=_headers("tenant-a"))
    operator = client.get("/v1/me", headers=_headers("platform", "platform_operator,tenant_admin"))

    assert plain.status_code == 200
    assert plain.json() == {"subject": "reviewer", "tenant_id": "tenant-a", "roles": ["engineer"]}
    assert operator.status_code == 200
    assert operator.json() == {
        "subject": "reviewer",
        "tenant_id": "platform",
        "roles": ["platform_operator", "tenant_admin"],
    }
    # Nunca claims brutos nem token: só o que o Principal expõe.
    assert "token" not in plain.json()
    assert "claims" not in plain.json()


def test_me_requires_authentication() -> None:
    client = TestClient(create_app())

    response = client.get("/v1/me")

    assert response.status_code == 401


def test_platform_tenant_reads_require_platform_operator_role(tmp_path: Path) -> None:
    client = _client(tmp_path)

    listing = client.get("/v1/platform/tenants", headers=_headers("tenant-a"))
    single = client.get(
        "/v1/platform/tenants/tenant-a/ai-processing-entitlement",
        headers=_headers("tenant-a"),
    )

    assert listing.status_code == 403
    assert single.status_code == 403


def test_platform_tenant_entitlement_get_is_never_404_and_reflects_the_put_lifecycle(
    tmp_path: Path,
) -> None:
    client = _client(tmp_path)
    operator_headers = _headers("platform", "platform_operator")
    endpoint = "/v1/platform/tenants/tenant-a/ai-processing-entitlement"

    never_activated = client.get(endpoint, headers=operator_headers)
    assert never_activated.status_code == 200
    assert never_activated.json() == {
        "tenant_id": "tenant-a",
        "enabled": False,
        "agreement_reference": None,
        "authorized_at": None,
        "revoked_at": None,
    }

    activated = client.put(
        endpoint,
        headers={**operator_headers, "Idempotency-Key": "activate-tenant-a"},
        json={"enabled": True, "agreement_reference": "ctr-tenant-a-v1"},
    )
    assert activated.status_code == 200

    after_activation = client.get(endpoint, headers=operator_headers)
    assert after_activation.status_code == 200
    body = after_activation.json()
    assert body["enabled"] is True
    assert body["agreement_reference"] == "ctr-tenant-a-v1"
    assert body["authorized_at"] is not None
    assert body["revoked_at"] is None

    revoked = client.put(
        endpoint,
        headers={**operator_headers, "Idempotency-Key": "revoke-tenant-a"},
        json={"enabled": False},
    )
    assert revoked.status_code == 200

    after_revocation = client.get(endpoint, headers=operator_headers)
    assert after_revocation.status_code == 200
    revoked_body = after_revocation.json()
    assert revoked_body["enabled"] is False
    assert revoked_body["agreement_reference"] == "ctr-tenant-a-v1"
    assert revoked_body["revoked_at"] is not None


def test_platform_tenant_listing_unions_uploads_projects_and_entitlements(
    tmp_path: Path,
) -> None:
    client = _client(tmp_path)
    operator_headers = _headers("platform", "platform_operator")

    # Tenant que só tem upload.
    _presign_and_put(client, tenant="tenant-upload-only", filename="upload-only.pdf")

    # Tenant que só tem project — inserido direto porque a API não cria project sem
    # upload junto (POST /v1/jobs sempre exige upload_id); a listagem precisa incluir
    # esse tenant mesmo assim, pela tabela projects isolada.
    database = cast(Database, cast(Any, client.app).state.database)
    with database.sessions() as session:
        session.add(
            ProjectRecord(
                id=str(new_uuid7()),
                tenant_id="tenant-project-only",
                name="Projeto isolado",
                default_unit="m",
                status="ACTIVE",
                created_by="reviewer",
                expires_at=datetime.now(UTC),
            )
        )
        session.commit()

    # Tenant que só tem entitlement (nunca fez upload nem project).
    entitlement_response = client.put(
        "/v1/platform/tenants/tenant-entitlement-only/ai-processing-entitlement",
        headers={**operator_headers, "Idempotency-Key": "entitlement-only"},
        json={"enabled": True, "agreement_reference": "ctr-entitlement-only"},
    )
    assert entitlement_response.status_code == 200

    listing = client.get("/v1/platform/tenants", headers=operator_headers)

    assert listing.status_code == 200
    tenants = {entry["tenant_id"]: entry for entry in listing.json()["tenants"]}
    assert "tenant-upload-only" in tenants
    assert tenants["tenant-upload-only"]["enabled"] is False
    assert "tenant-project-only" in tenants
    assert tenants["tenant-project-only"]["enabled"] is False
    assert "tenant-entitlement-only" in tenants
    assert tenants["tenant-entitlement-only"]["enabled"] is True
    assert tenants["tenant-entitlement-only"]["agreement_reference"] == "ctr-entitlement-only"
    # Ordenação determinística por tenant_id, para SQLite (testes) e PostgreSQL concordarem.
    tenant_ids = [entry["tenant_id"] for entry in listing.json()["tenants"]]
    assert tenant_ids == sorted(tenant_ids)


def test_upload_and_job_are_tenant_scoped(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "local")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "local")
    client = _client(tmp_path)
    pdf = synthetic_pdf()
    payload = {
        "filename": "levantamento.pdf",
        "content_type": "application/pdf",
        "size_bytes": len(pdf),
        "sha256": hashlib.sha256(pdf).hexdigest(),
    }

    presign = client.post("/v1/uploads/presign", headers=_headers("tenant-a"), json=payload)

    assert presign.status_code == 200
    assert presign.json()["object_key"].startswith("tenants/tenant-a/uploads/")
    assert presign.json()["headers"]["Content-Type"] == "application/pdf"
    assert presign.json()["headers"]["x-amz-checksum-sha256"] == base64.b64encode(
        hashlib.sha256(pdf).digest()
    ).decode("ascii")
    retry_presign = client.post("/v1/uploads/presign", headers=_headers("tenant-a"), json=payload)
    assert retry_presign.json()["upload_id"] == presign.json()["upload_id"]
    cast(FakeObjectStore, cast(Any, client.app).state.artifact_store).put_direct(
        object_key=presign.json()["object_key"], body=pdf
    )

    create = client.post(
        "/v1/jobs",
        headers=_headers("tenant-a"),
        json={
            "upload_id": presign.json()["upload_id"],
            "project_name": "Guaxindiba",
            "default_unit": "m",
        },
    )

    assert create.status_code == 201
    job_id = create.json()["job_id"]
    assert client.get(f"/v1/jobs/{job_id}", headers=_headers("tenant-a")).status_code == 200
    assert client.get(f"/v1/jobs/{job_id}", headers=_headers("tenant-b")).status_code == 404
    assert create.headers["X-Request-ID"]


def test_presign_assina_o_catalogo_json_da_rodada_de_medicao(tmp_path: Path) -> None:
    """O catálogo de preços da rodada sobe pelo mesmo presign, como objeto JSON.

    O ADR-0028 D6 escreveu "presign sem alteração" pensando na prancha e deixou o catálogo
    (`catalog_upload_id`) sem porta de entrada nenhuma; o tipo declarado é o que fecha a
    lacuna sem criar um segundo caminho de ingestão.
    """
    client = _client(tmp_path)
    catalog = b'{"source_label": "SCO"}'

    presign = client.post(
        "/v1/uploads/presign",
        headers=_headers("tenant-a"),
        json={
            "filename": "catalogo SCO 2026-01.json",
            "content_type": "application/json",
            "size_bytes": len(catalog),
            "sha256": hashlib.sha256(catalog).hexdigest(),
        },
    )

    assert presign.status_code == 200
    assert presign.json()["object_key"].endswith("/catalogo-SCO-2026-01.json")
    assert presign.json()["headers"]["Content-Type"] == "application/json"


@pytest.mark.parametrize(
    ("filename", "content_type"),
    [
        ("catalogo.pdf", "application/json"),
        ("levantamento.json", "application/pdf"),
        ("levantamento.txt", "application/pdf"),
    ],
)
def test_presign_recusa_extensao_que_nao_casa_com_o_tipo(
    tmp_path: Path, filename: str, content_type: str
) -> None:
    client = _client(tmp_path)

    response = client.post(
        "/v1/uploads/presign",
        headers=_headers("tenant-a"),
        json={
            "filename": filename,
            "content_type": content_type,
            "size_bytes": 1024,
            "sha256": "a" * 64,
        },
    )

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "INVALID_UPLOAD"


def test_presign_recusa_tipo_fora_da_lista(tmp_path: Path) -> None:
    client = _client(tmp_path)

    response = client.post(
        "/v1/uploads/presign",
        headers=_headers("tenant-a"),
        json={
            "filename": "planilha.xlsx",
            "content_type": "application/vnd.ms-excel",
            "size_bytes": 1024,
            "sha256": "a" * 64,
        },
    )

    assert response.status_code == 422


def test_o_tipo_declarado_no_contrato_e_o_mesmo_que_a_rota_conhece() -> None:
    """Um tipo novo entra nos dois lugares ou em nenhum: extensão sem tipo é buraco."""
    assert set(get_args(PresignUploadRequest.model_fields["content_type"].annotation)) == set(
        UPLOAD_CONTENT_TYPES
    )


def test_job_recusa_upload_que_nao_e_pdf(tmp_path: Path) -> None:
    """O presign passou a assinar JSON; o caminho do croqui continua exigindo PDF."""
    client = _client(tmp_path)
    catalog = b'{"source_label": "SCO"}'
    presign = client.post(
        "/v1/uploads/presign",
        headers=_headers("tenant-a"),
        json={
            "filename": "catalogo.json",
            "content_type": "application/json",
            "size_bytes": len(catalog),
            "sha256": hashlib.sha256(catalog).hexdigest(),
        },
    )
    assert presign.status_code == 200
    cast(FakeObjectStore, cast(Any, client.app).state.artifact_store).put_direct(
        object_key=presign.json()["object_key"],
        body=catalog,
        content_type="application/json",
    )

    response = client.post(
        "/v1/jobs",
        headers=_headers("tenant-a"),
        json={
            "upload_id": presign.json()["upload_id"],
            "project_name": "Guaxindiba",
            "default_unit": "m",
        },
    )

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "INVALID_UPLOAD"
    assert client.get("/v1/projects", headers=_headers("tenant-a")).json() == []


def test_mutation_requires_jwt_and_idempotency_key(tmp_path: Path) -> None:
    client = _client(tmp_path)
    payload = {
        "filename": "levantamento.pdf",
        "content_type": "application/pdf",
        "size_bytes": 1024,
        "sha256": "a" * 64,
    }

    assert client.post("/v1/uploads/presign", json=payload).status_code == 401
    assert (
        client.post(
            "/v1/uploads/presign",
            headers={"Authorization": "Bearer test:tenant-a:reviewer:engineer"},
            json=payload,
        ).status_code
        == 400
    )


def test_job_is_not_created_when_remote_checksum_diverges(tmp_path: Path) -> None:
    client = _client(tmp_path)
    # The browser stored bytes that do not match the digest declared at presign time.
    presign = _presign_and_put(client, stored_body=b"%PDF-1.7 conteudo divergente")

    response = client.post(
        "/v1/jobs",
        headers=_headers("tenant-a"),
        json={
            "upload_id": presign["upload_id"],
            "project_name": "Teste",
            "default_unit": "m",
        },
    )

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "INVALID_UPLOAD"
    assert client.get("/v1/projects", headers=_headers("tenant-a")).json() == []


def test_review_operation_creates_a_new_unresolved_revision(tmp_path: Path) -> None:
    database = Database(f"sqlite+pysqlite:///{tmp_path / 'review.db'}")
    database.create_schema()
    settings = ApiSettings(
        database_url=f"sqlite+pysqlite:///{tmp_path / 'review.db'}",
        artifact_bucket="test",
        aws_region="sa-east-1",
        aws_endpoint_url=None,
        queue_url=None,
        oidc_issuer=None,
        oidc_audience=None,
        web_origin="http://localhost:5173",
        allow_test_tokens=True,
    )
    job_id = UUID("00000000-0000-7000-8000-000000000201")
    scene = SceneRevision(job_id=job_id, version=1, entities=[])
    with database.sessions.begin() as session:
        session.add(
            ProjectRecord(
                id="project",
                tenant_id="tenant-a",
                name="Teste",
                default_unit="m",
                created_by="reviewer",
                expires_at=scene.created_at,
            )
        )
        session.add(
            UploadRecord(
                id="upload",
                tenant_id="tenant-a",
                object_key="key",
                filename="x.pdf",
                content_type="application/pdf",
                size_bytes=1,
                sha256="a" * 64,
            )
        )
        session.flush()
        session.add(
            JobRecord(
                id=str(job_id),
                tenant_id="tenant-a",
                project_id="project",
                upload_id="upload",
                status="REVIEW_REQUIRED",
                stage="PREVIEWING",
                expires_at=scene.created_at,
            )
        )
        session.flush()
        session.add(
            RevisionRecord(
                id=str(scene.id),
                tenant_id="tenant-a",
                job_id=str(job_id),
                version=1,
                scene=scene.model_dump(mode="json"),
                created_by="worker",
            )
        )
    client = TestClient(create_app(settings=settings, database=database))
    response = client.post(
        f"/v1/jobs/{job_id}/revisions",
        headers=_headers("tenant-a"),
        json={
            "base_version": 1,
            "reason": "Desenho manual",
            "operations": [
                {
                    "op": "add_entity",
                    "entity": {
                        "id": "00000000-0000-7000-8000-000000000202",
                        "kind": "line",
                        "layer": "REVISAO",
                        "precision": "unresolved",
                        "export": False,
                        "geometry": {
                            "type": "line",
                            "start": {"x": 0, "y": 0},
                            "end": {"x": 1, "y": 0},
                        },
                    },
                }
            ],
        },
    )
    assert response.status_code == 200
    assert response.json()["version"] == 2
    assert response.json()["entities"][0]["precision"] == "unresolved"


def _extra_reading(digest: str) -> DimensionReading:
    """A reading outside the rectangle request, used to re-run the solver after a decision."""
    return DimensionReading(
        id="rd_4444444444444444",
        evidence=EvidenceRegion(
            dataset_id="synthetic-guaxindiba-contract-v1",
            page_number=1,
            image_sha256=digest,
            bbox=PixelBox(left=10, top=120, right=80, bottom=150),
        ),
        raw_text="detalhe sintético",
        value_si=Decimal("3.00"),
        unit=UnitCode.METRE,
        kind=MeasurementKind.LENGTH,
        written_decimals=2,
        target_hint="detalhe lateral",
        extractor="contract-fixture",
        extractor_version="v1",
        status=ReadingStatus.PROPOSED,
    )


def _chain_readings(digest: str) -> list[DimensionReading]:
    """Quatro cotas de planta cujo texto é número puro, para a conferência de cadeias.

    `suggest_chains` só olha cota de planta (número puro na folha), e nenhuma leitura da
    fixture base é: `"largura sintética"` descreve o que a cota mede, não o que está
    escrito nela. Estas quatro fecham exatamente uma soma — 12,00 + 13,90 = 25,90 — e a
    quarta (3,00) existe para declarar uma cadeia que NÃO fecha.

    Nenhuma delas entra em `associations`: são confirmadas como anotação da folha, o que
    as mantém fora do solver e deixa a conferência de cadeia isolada do traçado.
    """
    values = (
        ("rd_5555555555555555", "25,90", "25.90", 10),
        ("rd_6666666666666666", "12,00", "12.00", 80),
        ("rd_7777777777777777", "13,90", "13.90", 150),
        ("rd_8888888888888888", "3,00", "3.00", 220),
    )
    return [
        DimensionReading(
            id=reading_id,
            evidence=EvidenceRegion(
                dataset_id="synthetic-guaxindiba-contract-v1",
                page_number=1,
                image_sha256=digest,
                bbox=PixelBox(left=left, top=60, right=left + 60, bottom=90),
            ),
            raw_text=raw_text,
            value_si=Decimal(value_si),
            unit=UnitCode.METRE,
            kind=MeasurementKind.LENGTH,
            written_decimals=2,
            target_hint="cadeia sintética",
            extractor="contract-fixture",
            extractor_version="v1",
            status=ReadingStatus.PROPOSED,
        )
        for reading_id, raw_text, value_si, left in values
    ]


def _seed_review_session(
    client: TestClient, *, extra_reading: bool = False, chain_readings: bool = False
) -> UUID:
    database = cast(Database, cast(Any, client.app).state.database)
    job_id = UUID("00000000-0000-7000-8000-000000000301")
    digest = "b" * 64
    packet = ReviewPacket(
        dataset_id="synthetic-guaxindiba-contract-v1",
        page_number=1,
        image_sha256=digest,
        readings=[
            DimensionReading(
                id="rd_1111111111111111",
                evidence=EvidenceRegion(
                    dataset_id="synthetic-guaxindiba-contract-v1",
                    page_number=1,
                    image_sha256=digest,
                    bbox=PixelBox(left=10, top=20, right=80, bottom=50),
                ),
                raw_text="largura sintética",
                value_si=Decimal("25.90"),
                unit=UnitCode.METRE,
                kind=MeasurementKind.WIDTH,
                written_decimals=2,
                target_hint="campo principal",
                extractor="contract-fixture",
                extractor_version="v1",
                status=ReadingStatus.PROPOSED,
            ),
            DimensionReading(
                id="rd_2222222222222222",
                evidence=EvidenceRegion(
                    dataset_id="synthetic-guaxindiba-contract-v1",
                    page_number=1,
                    image_sha256=digest,
                    bbox=PixelBox(left=90, top=20, right=160, bottom=50),
                ),
                raw_text="altura sintética",
                value_si=Decimal("21.75"),
                unit=UnitCode.METRE,
                kind=MeasurementKind.HEIGHT,
                written_decimals=2,
                target_hint="campo principal",
                extractor="contract-fixture",
                extractor_version="v1",
                status=ReadingStatus.PROPOSED,
            ),
            DimensionReading(
                id="rd_3333333333333333",
                evidence=EvidenceRegion(
                    dataset_id="synthetic-guaxindiba-contract-v1",
                    page_number=1,
                    image_sha256=digest,
                    bbox=PixelBox(left=170, top=20, right=240, bottom=50),
                ),
                raw_text="círculo sintético",
                value_si=Decimal("6.00"),
                unit=UnitCode.METRE,
                kind=MeasurementKind.DIAMETER,
                written_decimals=2,
                target_hint="círculo central",
                extractor="contract-fixture",
                extractor_version="v1",
                status=ReadingStatus.PROPOSED,
            ),
            *([_extra_reading(digest)] if extra_reading else []),
            *(_chain_readings(digest) if chain_readings else []),
        ],
        safety_notes=["Fixture sintética.", "Revisão humana obrigatória."],
    )
    associations = AssociationSet.model_validate(
        {
            "dataset_id": packet.dataset_id,
            "page_number": 1,
            "image_sha256": digest,
            # `association_confidence` explícito e DIFERENTE por candidato: a fixture não
            # passa por `associate_readings`, e sem valor cada candidato ficaria no default
            # 0.0 — o shadow log responderia lista vazia em todo ponto da grade e os testes
            # de threshold passariam por vacuidade. Os três valores separam os cortes da
            # grade (0,92 acima de 0,9; 0,78 entre 0,7 e 0,8; 0,55 acima só de 0,5).
            "candidates": [
                {
                    "reading_id": "rd_1111111111111111",
                    "proposal_id": "vp_1111111111111111",
                    "proposal_kind": "line",
                    "relation": "nearest_geometry",
                    "pixel_distance": 1,
                    "proximity_score": 0.9,
                    "visual_quality_score": 0.8,
                    "association_confidence": 0.92,
                },
                {
                    "reading_id": "rd_2222222222222222",
                    "proposal_id": "vp_2222222222222222",
                    "proposal_kind": "line",
                    "relation": "nearest_geometry",
                    "pixel_distance": 1,
                    "proximity_score": 0.9,
                    "visual_quality_score": 0.8,
                    "association_confidence": 0.78,
                },
                {
                    "reading_id": "rd_3333333333333333",
                    "proposal_id": "vp_3333333333333333",
                    "proposal_kind": "circle",
                    "relation": "inside_or_near_circle",
                    "pixel_distance": 1,
                    "proximity_score": 0.9,
                    "visual_quality_score": 0.8,
                    "association_confidence": 0.55,
                },
                *(
                    [
                        {
                            "reading_id": "rd_4444444444444444",
                            "proposal_id": "vp_4444444444444444",
                            "proposal_kind": "contour",
                            "relation": "nearest_geometry",
                            "pixel_distance": 2,
                            "proximity_score": 0.7,
                            "visual_quality_score": 0.7,
                        }
                    ]
                    if extra_reading
                    else []
                ),
            ],
            "unassociated_reading_ids": [],
            "safety_notes": ["pixels", "não confirma", "não exporta"],
        }
    )
    proposals = VisionProposalSet(
        dataset_id=packet.dataset_id,
        page_number=1,
        image_sha256=digest,
        image_width_px=300,
        image_height_px=200,
        configured_limits={"line": 80, "circle": 16, "contour": 16},
        limit_reached=[],
        proposals=[
            VisionProposal(
                id="vp_1111111111111111",
                kind="line",
                geometry=PixelLine(start=PixelPoint(x=0, y=0), end=PixelPoint(x=100, y=0)),
                algorithm="fixture",
                quality_score=0.9,
            ),
            VisionProposal(
                id="vp_2222222222222222",
                kind="line",
                geometry=PixelLine(start=PixelPoint(x=0, y=0), end=PixelPoint(x=0, y=100)),
                algorithm="fixture",
                quality_score=0.9,
            ),
            VisionProposal(
                id="vp_3333333333333333",
                kind="circle",
                geometry=PixelCircle(center=PixelPoint(x=50, y=50), radius=12),
                algorithm="fixture",
                quality_score=0.9,
            ),
            VisionProposal(
                id="vp_4444444444444444",
                kind="contour",
                geometry=PixelPolyline(
                    points=[PixelPoint(x=10, y=10), PixelPoint(x=30, y=10), PixelPoint(x=20, y=30)]
                ),
                algorithm="fixture",
                quality_score=0.9,
            ),
        ],
        safety_notes=["fixture", "pixels", "não exportável"],
    )
    scene = SceneRevision(
        job_id=job_id,
        version=1,
        entities=[
            Entity(
                id=UUID("00000000-0000-7000-8000-000000000401"),
                kind=EntityKind.LINE,
                layer=LayerName.CAMPO,
                precision=Precision.EXACT,
                geometry=LineGeometry(start=Point2D(x=0, y=0), end=Point2D(x=25.9, y=0)),
                provenance=Provenance(
                    source_type="solver", source_ids=["rd_width"], summary_code="SOLVER"
                ),
            ),
            Entity(
                id=UUID("00000000-0000-7000-8000-000000000402"),
                kind=EntityKind.LINE,
                layer=LayerName.CAMPO,
                precision=Precision.EXACT,
                geometry=LineGeometry(start=Point2D(x=0, y=0), end=Point2D(x=0, y=21.75)),
                provenance=Provenance(
                    source_type="solver", source_ids=["rd_height"], summary_code="SOLVER"
                ),
            ),
        ],
    )
    now = datetime.now(UTC)
    with database.sessions.begin() as session:
        session.add(
            ProjectRecord(
                id="project-review",
                tenant_id="tenant-a",
                name="Revisão sintética",
                default_unit="m",
                created_by="worker",
                expires_at=now,
            )
        )
        session.add(
            UploadRecord(
                id="upload-review",
                tenant_id="tenant-a",
                object_key="protected/synthetic.pdf",
                filename="synthetic.pdf",
                content_type="application/pdf",
                size_bytes=1,
                sha256="a" * 64,
            )
        )
        session.flush()
        session.add(
            JobRecord(
                id=str(job_id),
                tenant_id="tenant-a",
                project_id="project-review",
                upload_id="upload-review",
                status="REVIEW_REQUIRED",
                stage="PREVIEWING",
                expires_at=now,
            )
        )
        session.flush()
        session.add(
            RevisionRecord(
                id=str(scene.id),
                tenant_id="tenant-a",
                job_id=str(job_id),
                version=scene.version,
                scene=scene.model_dump(mode="json"),
                created_by="rectangle-solver-v1",
            )
        )
        session.flush()
        session.add(
            ReviewRevisionRecord(
                id="00000000-0000-7000-8000-000000000302",
                tenant_id="tenant-a",
                job_id=str(job_id),
                version=1,
                packet_json=packet.model_dump(mode="json"),
                associations_json=associations.model_dump(mode="json"),
                proposals_json=proposals.model_dump(mode="json"),
                evidence_refs_json={"source_image_key": "tenants/tenant-a/review/source.png"},
                solver_request_json={
                    "feature_id": "campo-principal",
                    "width_reading_id": "rd_1111111111111111",
                    "height_reading_id": "rd_2222222222222222",
                    "centre_circle_reading_id": "rd_3333333333333333",
                },
                required_blocker_codes_json=["ACC_GUA_001"],
                required_criteria_texts_json={"ACC_GUA_001": CRITERION_TEXT},
                created_by="local-worker",
            )
        )
    return job_id


def test_professional_calibrates_and_accepts_approximate_proposal(tmp_path: Path) -> None:
    client = _client(tmp_path)
    job_id = _seed_review_session(client)
    calibration = client.post(
        f"/v1/jobs/{job_id}/review/calibration",
        headers={**_headers("tenant-a"), "Idempotency-Key": "proposal-calibration"},
        json={
            "base_review_version": 1,
            "base_scene_version": 1,
            "anchors": [
                {
                    "proposal_id": "vp_1111111111111111",
                    "entity_id": "00000000-0000-7000-8000-000000000401",
                },
                {
                    "proposal_id": "vp_2222222222222222",
                    "entity_id": "00000000-0000-7000-8000-000000000402",
                },
            ],
        },
    )

    assert calibration.status_code == 200
    calibration_json = calibration.json()["calibration"]
    assert calibration_json["scale_m_per_px"] > 0
    # A fixture tem 100 px valendo 25,90 m num eixo e 21,75 m no outro: o croqui não
    # está em esquadro e a calibração afim precisa registrar uma escala por eixo.
    assert calibration_json["mode"] == "affine"
    assert calibration_json["scale_x_m_per_px"] == pytest.approx(0.259)
    assert calibration_json["scale_y_m_per_px"] == pytest.approx(0.2175)
    assert calibration_json["anisotropy"] == pytest.approx(0.259 / 0.2175)
    accepted = client.post(
        f"/v1/jobs/{job_id}/review/proposals",
        headers={**_headers("tenant-a"), "Idempotency-Key": "proposal-accept"},
        json={
            "base_review_version": 2,
            "base_scene_version": 1,
            "proposal_id": "vp_3333333333333333",
            "action": "accept",
            "justification": "Círculo revisado como hipótese visual.",
            "calibration_id": calibration_json["calibration_id"],
        },
    )

    assert accepted.status_code == 200
    response = accepted.json()
    assert response["version"] == 3
    assert response["proposal_decisions"][-1]["action"] == "accept"
    assert response["scene"]["version"] == 2
    entity = response["scene"]["entities"][-1]
    # Escalas de eixo diferentes tornam o círculo uma elipse. O scene graph não tem
    # elipse, então ele é amostrado como polilinha em vez de ganhar um raio médio que
    # não corresponderia a nenhum dos dois eixos.
    assert entity["kind"] == "polyline"
    assert entity["precision"] == "approximate"
    assert entity["layer"] == "APROXIMADO"
    assert entity["export"] is True
    out_of_scale = next(
        issue for issue in response["scene"]["issues"] if issue["code"] == "SKETCH_OUT_OF_SCALE"
    )
    assert out_of_scale["severity"] == "warning"
    assert "19.1%" in out_of_scale["message"]
    assert accepted.json()["scene"]["approved"] is False
    retry = client.post(
        f"/v1/jobs/{job_id}/review/proposals",
        headers={**_headers("tenant-a"), "Idempotency-Key": "proposal-accept"},
        json={
            "base_review_version": 2,
            "base_scene_version": 1,
            "proposal_id": "vp_3333333333333333",
            "action": "accept",
            "justification": "Círculo revisado como hipótese visual.",
            "calibration_id": calibration_json["calibration_id"],
        },
    )
    assert retry.status_code == 200
    assert retry.json()["review_id"] == response["review_id"]


def _line_entity_id(
    scene: dict[str, Any], start: tuple[float, float], end: tuple[float, float]
) -> str:
    for entity in scene["entities"]:
        geometry = entity["geometry"]
        if geometry["type"] != "line":
            continue
        current = (
            (geometry["start"]["x"], geometry["start"]["y"]),
            (geometry["end"]["x"], geometry["end"]["y"]),
        )
        if current == (start, end):
            return str(entity["id"])
    raise AssertionError(f"Entidade de linha {start}->{end} não encontrada na cena.")


def _confirm_solver_readings(client: TestClient, job_id: UUID, *, base_version: int) -> Any:
    return client.post(
        f"/v1/jobs/{job_id}/review/decisions",
        headers={**_headers("tenant-a"), "Idempotency-Key": f"solver-readings-{base_version}"},
        json={
            "base_version": base_version,
            "decisions": [
                {
                    "reading_id": "rd_1111111111111111",
                    "action": "confirm",
                    "justification": "Evidência sintética revisada.",
                    "association_proposal_id": "vp_1111111111111111",
                },
                {
                    "reading_id": "rd_2222222222222222",
                    "action": "confirm",
                    "justification": "Evidência sintética revisada.",
                    "association_proposal_id": "vp_2222222222222222",
                },
                {
                    "reading_id": "rd_3333333333333333",
                    "action": "confirm",
                    "justification": "Evidência sintética revisada.",
                    "association_proposal_id": "vp_3333333333333333",
                },
            ],
        },
    )


def test_accepted_approximation_survives_a_later_reading_decision(tmp_path: Path) -> None:
    client = _client(tmp_path)
    job_id = _seed_review_session(client, extra_reading=True)
    solved = _confirm_solver_readings(client, job_id, base_version=1)
    assert solved.status_code == 200
    solver_scene = solved.json()["scene"]
    assert solver_scene["version"] == 2
    # Anchors are the solver's own edges, so re-solving reproduces them deterministically.
    bottom_id = _line_entity_id(solver_scene, (25.9, 0.0), (0.0, 0.0))
    left_id = _line_entity_id(solver_scene, (0.0, 0.0), (0.0, 21.75))

    calibration = client.post(
        f"/v1/jobs/{job_id}/review/calibration",
        headers={**_headers("tenant-a"), "Idempotency-Key": "survive-calibration"},
        json={
            "base_review_version": 2,
            "base_scene_version": 2,
            "anchors": [
                {"proposal_id": "vp_1111111111111111", "entity_id": bottom_id, "reversed": True},
                {"proposal_id": "vp_2222222222222222", "entity_id": left_id},
            ],
        },
    )
    assert calibration.status_code == 200
    calibration_id = calibration.json()["calibration"]["calibration_id"]

    accepted = client.post(
        f"/v1/jobs/{job_id}/review/proposals",
        headers={**_headers("tenant-a"), "Idempotency-Key": "survive-accept"},
        json={
            "base_review_version": 3,
            "base_scene_version": 2,
            "proposal_id": "vp_3333333333333333",
            "action": "accept",
            "justification": "Círculo aceito como hipótese visual.",
            "calibration_id": calibration_id,
        },
    )
    assert accepted.status_code == 200
    approximate_id = accepted.json()["proposal_decisions"][-1]["entity_id"]
    assert accepted.json()["scene"]["version"] == 3

    later = client.post(
        f"/v1/jobs/{job_id}/review/decisions",
        headers={**_headers("tenant-a"), "Idempotency-Key": "survive-extra-reading"},
        json={
            "base_version": 4,
            "decisions": [
                {
                    "reading_id": "rd_4444444444444444",
                    "action": "confirm",
                    "justification": "Detalhe lateral revisado na evidência.",
                    "association_proposal_id": "vp_4444444444444444",
                }
            ],
        },
    )

    assert later.status_code == 200
    body = later.json()
    resolved_scene = body["scene"]
    assert resolved_scene["version"] == 4
    surviving = [entity for entity in resolved_scene["entities"] if entity["id"] == approximate_id]
    assert len(surviving) == 1
    assert surviving[0]["precision"] == "approximate"
    assert body["calibration"] is not None
    assert body["calibration"]["scene_version"] == 4
    assert "CALIBRATION_SUPERSEDED" not in [issue["code"] for issue in resolved_scene["issues"]]


def test_superseded_calibration_freezes_accepted_geometry_instead_of_dropping_it(
    tmp_path: Path,
) -> None:
    client = _client(tmp_path)
    job_id = _seed_review_session(client)
    calibration = client.post(
        f"/v1/jobs/{job_id}/review/calibration",
        headers={**_headers("tenant-a"), "Idempotency-Key": "drift-calibration"},
        json={
            "base_review_version": 1,
            "base_scene_version": 1,
            "anchors": [
                {
                    "proposal_id": "vp_1111111111111111",
                    "entity_id": "00000000-0000-7000-8000-000000000401",
                },
                {
                    "proposal_id": "vp_2222222222222222",
                    "entity_id": "00000000-0000-7000-8000-000000000402",
                },
            ],
        },
    )
    assert calibration.status_code == 200
    accepted = client.post(
        f"/v1/jobs/{job_id}/review/proposals",
        headers={**_headers("tenant-a"), "Idempotency-Key": "drift-accept"},
        json={
            "base_review_version": 2,
            "base_scene_version": 1,
            "proposal_id": "vp_3333333333333333",
            "action": "accept",
            "justification": "Círculo aceito como hipótese visual.",
            "calibration_id": calibration.json()["calibration"]["calibration_id"],
        },
    )
    assert accepted.status_code == 200
    approximate_id = accepted.json()["proposal_decisions"][-1]["entity_id"]

    # The solver replaces the anchor entities, so the stored transform no longer holds.
    solved = _confirm_solver_readings(client, job_id, base_version=3)

    assert solved.status_code == 200
    body = solved.json()
    resolved_scene = body["scene"]
    assert [entity["id"] for entity in resolved_scene["entities"]].count(approximate_id) == 1
    assert body["calibration"] is None
    assert "CALIBRATION_SUPERSEDED" in [issue["code"] for issue in resolved_scene["issues"]]
    superseded = next(
        issue for issue in resolved_scene["issues"] if issue["code"] == "CALIBRATION_SUPERSEDED"
    )
    assert superseded["severity"] == "critical"
    assert approximate_id in superseded["entity_ids"]


def test_proposal_decision_requires_professional_and_calibration(tmp_path: Path) -> None:
    client = _client(tmp_path)
    job_id = _seed_review_session(client)
    payload = {
        "base_review_version": 1,
        "base_scene_version": 1,
        "proposal_id": "vp_3333333333333333",
        "action": "accept",
        "justification": "Hipótese visual revisada.",
    }
    forbidden = client.post(
        f"/v1/jobs/{job_id}/review/proposals",
        headers={**_headers("tenant-a", "cad_operator"), "Idempotency-Key": "proposal-role"},
        json=payload,
    )
    assert forbidden.status_code == 403
    missing = client.post(
        f"/v1/jobs/{job_id}/review/proposals",
        headers={**_headers("tenant-a"), "Idempotency-Key": "proposal-missing-calibration"},
        json=payload,
    )
    assert missing.status_code == 422
    assert missing.json()["detail"]["code"] == "CALIBRATION_REQUIRED"


def test_authenticated_review_decisions_are_tenant_scoped_and_idempotent(tmp_path: Path) -> None:
    client = _client(tmp_path)
    job_id = _seed_review_session(client)
    endpoint = f"/v1/jobs/{job_id}/review"
    assert client.get(endpoint, headers=_headers("tenant-a")).status_code == 200
    assert client.get(endpoint, headers=_headers("tenant-b")).status_code == 404

    payload = {
        "base_version": 1,
        "decisions": [
            {
                "reading_id": "rd_1111111111111111",
                "action": "confirm",
                "justification": "Conferido no material protegido.",
                "association_proposal_id": "vp_1111111111111111",
            }
        ],
    }
    response = client.post(f"{endpoint}/decisions", headers=_headers("tenant-a"), json=payload)

    assert response.status_code == 200
    assert response.json()["version"] == 2
    assert response.json()["packet"]["readings"][0]["status"] == "confirmed"
    assert response.json()["packet"]["readings"][0]["decision"]["reviewer_id"] == "reviewer"
    assert response.json()["preview_urls"]["source_image_url"].startswith(
        "https://storage.invalid/"
    )
    retry = client.post(f"{endpoint}/decisions", headers=_headers("tenant-a"), json=payload)
    assert retry.status_code == 200
    assert retry.json()["review_id"] == response.json()["review_id"]

    stale = client.post(
        f"{endpoint}/decisions",
        headers={**_headers("tenant-a"), "Idempotency-Key": "review-stale"},
        json=payload,
    )
    assert stale.status_code == 409
    assert stale.json()["detail"]["code"] == "REVISION_CONFLICT"


def test_annotation_reading_confirms_without_association(tmp_path: Path) -> None:
    """Anotação da folha (tela aérea) é declaração explícita: confirma sem elemento
    associado e nunca entra no mapa de associações; anotação COM associação é
    contradição e recusa."""
    client = _client(tmp_path)
    job_id = _seed_review_session(client)
    endpoint = f"/v1/jobs/{job_id}/review/decisions"

    contradictory = client.post(
        endpoint,
        headers={**_headers("tenant-a"), "Idempotency-Key": "annotation-conflict"},
        json={
            "base_version": 1,
            "decisions": [
                {
                    "reading_id": "rd_1111111111111111",
                    "action": "confirm",
                    "justification": "Anotação que veio com associação por engano.",
                    "association_proposal_id": "vp_1111111111111111",
                    "annotation": True,
                }
            ],
        },
    )
    assert contradictory.status_code == 422
    assert "não leva associação" in contradictory.json()["detail"]["detail"]

    annotated = client.post(
        endpoint,
        headers={**_headers("tenant-a"), "Idempotency-Key": "annotation-ok"},
        json={
            "base_version": 1,
            "decisions": [
                {
                    "reading_id": "rd_1111111111111111",
                    "action": "confirm",
                    "justification": "Anotação de cobertura da folha, não mede elemento.",
                    "annotation": True,
                }
            ],
        },
    )
    assert annotated.status_code == 200
    body = annotated.json()
    assert body["packet"]["readings"][0]["status"] == "confirmed"
    assert "rd_1111111111111111" not in body["selected_associations"]

    plain_missing = client.post(
        endpoint,
        headers={**_headers("tenant-a"), "Idempotency-Key": "still-required"},
        json={
            "base_version": 2,
            "decisions": [
                {
                    "reading_id": "rd_2222222222222222",
                    "action": "confirm",
                    "justification": "Cota de verdade sem associação continua barrada.",
                }
            ],
        },
    )
    assert plain_missing.status_code == 422
    assert "declaração de anotação" in plain_missing.json()["detail"]["detail"]


def test_review_rejects_ineligible_role_and_decided_reading(tmp_path: Path) -> None:
    client = _client(tmp_path)
    job_id = _seed_review_session(client)
    endpoint = f"/v1/jobs/{job_id}/review/decisions"
    payload = {
        "base_version": 1,
        "decisions": [
            {
                "reading_id": "rd_1111111111111111",
                "action": "confirm",
                "justification": "Conferido no material protegido.",
                "association_proposal_id": "vp_1111111111111111",
            }
        ],
    }
    ineligible = client.post(endpoint, headers=_headers("tenant-a", "cad_operator"), json=payload)
    assert ineligible.status_code == 403
    assert client.post(endpoint, headers=_headers("tenant-a"), json=payload).status_code == 200
    decided = client.post(
        endpoint,
        headers={**_headers("tenant-a"), "Idempotency-Key": "review-decided"},
        json={**payload, "base_version": 2},
    )
    assert decided.status_code == 422
    # A recusa aponta o caminho: decisão registrada se corrige, não se sobrescreve.
    assert decided.json()["detail"]["code"] == "READING_ALREADY_DECIDED"
    assert "correção declarada" in decided.json()["detail"]["detail"]


def _current_decision_id(client: TestClient, job_id: UUID, reading_id: str) -> str:
    review = client.get(f"/v1/jobs/{job_id}/review", headers=_headers("tenant-a")).json()
    reading = next(item for item in review["packet"]["readings"] if item["id"] == reading_id)
    return str(reading["decision"]["decision_id"])


def _rectification_payload(base_version: int, **overrides: Any) -> dict[str, Any]:
    return {
        "base_version": base_version,
        "rectifications": [
            {
                "reading_id": "rd_1111111111111111",
                "action": "confirm",
                "justification": "A cota foi transcrita errada; conferida de novo na folha.",
                "association_proposal_id": "vp_1111111111111111",
                **overrides,
            }
        ],
    }


def _confirm_width_with_the_wrong_reading(client: TestClient, job_id: UUID) -> Any:
    """Confirma a largura com valor e tipo errados — o erro real do Guaxindiba v1."""
    return client.post(
        f"/v1/jobs/{job_id}/review/decisions",
        headers={**_headers("tenant-a"), "Idempotency-Key": "wrong-width"},
        json={
            "base_version": 1,
            "decisions": [
                {
                    "reading_id": "rd_1111111111111111",
                    "action": "confirm",
                    "justification": "Confirmada como estava escrita na proposta.",
                    "association_proposal_id": "vp_1111111111111111",
                    "raw_text": "12,00",
                    "value_si": "12.00",
                    "unit": "m",
                    "kind": "length",
                },
                {
                    "reading_id": "rd_2222222222222222",
                    "action": "confirm",
                    "justification": "Evidência sintética revisada.",
                    "association_proposal_id": "vp_2222222222222222",
                },
                {
                    "reading_id": "rd_3333333333333333",
                    "action": "confirm",
                    "justification": "Evidência sintética revisada.",
                    "association_proposal_id": "vp_3333333333333333",
                },
            ],
        },
    )


def test_rectification_records_a_new_decision_and_re_solves_the_scene(tmp_path: Path) -> None:
    client = _client(tmp_path)
    job_id = _seed_review_session(client)
    solved = _confirm_width_with_the_wrong_reading(client, job_id)
    assert solved.status_code == 200
    assert solved.json()["scene"]["version"] == 2
    previous_decision_id = _current_decision_id(client, job_id, "rd_1111111111111111")

    rectified = client.post(
        f"/v1/jobs/{job_id}/review/rectifications",
        headers={**_headers("tenant-a"), "Idempotency-Key": "rectify-width"},
        json=_rectification_payload(
            2,
            rectifies_decision_id=previous_decision_id,
            raw_text="25,90",
            value_si="25.90",
            unit="m",
            kind="width",
        ),
    )

    assert rectified.status_code == 200
    body = rectified.json()
    assert body["version"] == 3
    reading = next(
        item for item in body["packet"]["readings"] if item["id"] == "rd_1111111111111111"
    )
    assert reading["status"] == "confirmed"
    assert reading["value_si"] == "25.90"
    assert reading["decision"]["rectifies_decision_id"] == previous_decision_id
    new_decision_id = reading["decision"]["decision_id"]
    assert new_decision_id != previous_decision_id
    # O re-solve aconteceu: a cena nova é recomputada a partir do pacote corrigido, e a
    # provenance das entidades já cita a decisão nova — nada ficou preso à anterior.
    scene = body["scene"]
    assert scene["version"] == 3
    assert scene["approved"] is False
    source_ids = {
        source
        for entity in scene["entities"]
        if entity["provenance"]
        for source in entity["provenance"]["source_ids"]
    }
    assert new_decision_id in source_ids
    assert previous_decision_id not in source_ids
    assert "READING_DECISION_SUPERSEDED" not in [issue["code"] for issue in scene["issues"]]
    width_measurement = next(
        measurement for measurement in scene["measurements"] if measurement["kind"] == "width"
    )
    assert width_measurement["value_si"] == "25.90"

    database = cast(Database, cast(Any, client.app).state.database)
    with database.sessions() as session:
        record = session.scalars(
            select(ReviewDecisionRecord).where(
                ReviewDecisionRecord.action == "rectify_confirm",
            )
        ).one()
        assert record.reading_id == "rd_1111111111111111"
        assert record.decision_id == new_decision_id
        assert record.rectifies_decision_id == previous_decision_id
        assert record.association_proposal_id == "vp_1111111111111111"
        audit = session.scalars(
            select(AuditRecord).where(AuditRecord.action == "REVIEW_DECISIONS_RECTIFIED")
        ).one()
        assert audit.resource_type == "review_revision"
        assert audit.resource_id == body["review_id"]


def test_rectification_to_a_rejection_drops_the_association_and_blocks_the_solver(
    tmp_path: Path,
) -> None:
    client = _client(tmp_path)
    job_id = _seed_review_session(client)
    assert _confirm_solver_readings(client, job_id, base_version=1).status_code == 200
    previous_decision_id = _current_decision_id(client, job_id, "rd_1111111111111111")

    rejected = client.post(
        f"/v1/jobs/{job_id}/review/rectifications",
        headers={**_headers("tenant-a"), "Idempotency-Key": "rectify-reject"},
        json=_rectification_payload(
            2,
            action="reject",
            rectifies_decision_id=previous_decision_id,
            association_proposal_id=None,
            justification="A cota não existe na folha; a leitura foi um artefato.",
        ),
    )

    assert rejected.status_code == 200
    body = rejected.json()
    assert "rd_1111111111111111" not in body["selected_associations"]
    assert any("WIDTH_HUMAN_CONFIRMATION_REQUIRED" in blocker for blocker in body["blockers"])
    # Sem re-solve possível, o que já foi desenhado sobre a decisão antiga fica travado
    # atrás da issue crítica — nunca apagado, nunca reprojetado.
    assert "READING_DECISION_SUPERSEDED" in body["blockers"]
    scene = body["scene"]
    assert scene["version"] == 3
    assert scene["approved"] is False
    superseded = next(
        issue for issue in scene["issues"] if issue["code"] == "READING_DECISION_SUPERSEDED"
    )
    assert superseded["severity"] == "critical"
    assert superseded["entity_ids"]
    assert (
        "OPEN_CRITICAL_ISSUE:READING_DECISION_SUPERSEDED"
        in SceneRevision.model_validate(scene).export_errors()
    )


def test_rectification_refuses_every_declared_failure(tmp_path: Path) -> None:
    client = _client(tmp_path)
    job_id = _seed_review_session(client)
    endpoint = f"/v1/jobs/{job_id}/review/rectifications"

    undecided = client.post(
        endpoint,
        headers={**_headers("tenant-a"), "Idempotency-Key": "rectify-undecided"},
        json=_rectification_payload(1, rectifies_decision_id="hd_" + "a" * 16),
    )
    assert undecided.status_code == 422
    assert undecided.json()["detail"]["code"] == "READING_NOT_DECIDED"

    assert _confirm_solver_readings(client, job_id, base_version=1).status_code == 200
    previous_decision_id = _current_decision_id(client, job_id, "rd_1111111111111111")

    stale_version = client.post(
        endpoint,
        headers={**_headers("tenant-a"), "Idempotency-Key": "rectify-stale-version"},
        json=_rectification_payload(1, rectifies_decision_id=previous_decision_id, kind="height"),
    )
    assert stale_version.status_code == 409
    assert stale_version.json()["detail"]["code"] == "REVISION_CONFLICT"

    stale_target = client.post(
        endpoint,
        headers={**_headers("tenant-a"), "Idempotency-Key": "rectify-stale-target"},
        json=_rectification_payload(2, rectifies_decision_id="hd_" + "0" * 16, kind="height"),
    )
    assert stale_target.status_code == 409
    assert stale_target.json()["detail"]["code"] == "RECTIFICATION_TARGET_STALE"

    unchanged = client.post(
        endpoint,
        headers={**_headers("tenant-a"), "Idempotency-Key": "rectify-noop"},
        json=_rectification_payload(2, rectifies_decision_id=previous_decision_id),
    )
    assert unchanged.status_code == 422
    assert unchanged.json()["detail"]["code"] == "RECTIFICATION_ALREADY_APPLIED"

    ineligible = client.post(
        endpoint,
        headers={**_headers("tenant-a", "cad_operator"), "Idempotency-Key": "rectify-role"},
        json=_rectification_payload(2, rectifies_decision_id=previous_decision_id, kind="height"),
    )
    assert ineligible.status_code == 403

    other_tenant = client.post(
        endpoint,
        headers={**_headers("tenant-b"), "Idempotency-Key": "rectify-tenant"},
        json=_rectification_payload(2, rectifies_decision_id=previous_decision_id, kind="height"),
    )
    assert other_tenant.status_code == 404


def test_rectification_replays_the_same_revision_for_the_same_key(tmp_path: Path) -> None:
    client = _client(tmp_path)
    job_id = _seed_review_session(client)
    assert _confirm_solver_readings(client, job_id, base_version=1).status_code == 200
    previous_decision_id = _current_decision_id(client, job_id, "rd_1111111111111111")
    endpoint = f"/v1/jobs/{job_id}/review/rectifications"
    payload = _rectification_payload(
        2, rectifies_decision_id=previous_decision_id, raw_text="25,90 conferido"
    )

    first = client.post(
        endpoint,
        headers={**_headers("tenant-a"), "Idempotency-Key": "rectify-replay"},
        json=payload,
    )
    assert first.status_code == 200
    replay = client.post(
        endpoint,
        headers={**_headers("tenant-a"), "Idempotency-Key": "rectify-replay"},
        json=payload,
    )

    assert replay.status_code == 200
    assert replay.json()["review_id"] == first.json()["review_id"]
    database = cast(Database, cast(Any, client.app).state.database)
    with database.sessions() as session:
        versions = session.scalars(
            select(ReviewRevisionRecord.version).where(
                ReviewRevisionRecord.job_id == str(job_id),
            )
        ).all()
        assert sorted(versions) == [1, 2, 3]

    reused = client.post(
        endpoint,
        headers={**_headers("tenant-a"), "Idempotency-Key": "rectify-replay"},
        json=_rectification_payload(
            2, rectifies_decision_id=previous_decision_id, raw_text="outro texto"
        ),
    )
    assert reused.status_code == 409
    assert reused.json()["detail"]["code"] == "IDEMPOTENCY_KEY_REUSED"


TRACED_DECISION_ID = "hd_aaaaaaaaaaaaaaaa"
TRACED_ENTITY_ID = UUID("00000000-0000-7000-8000-000000000501")


def _seed_traced_session(client: TestClient) -> UUID:
    """Cena já traçada a partir de uma cota confirmada, sem pedido de solver retangular.

    É o estado real depois do traçado em lote: a geometria existe, se apoia na decisão
    humana pela provenance, e nenhum re-solve automático a recompõe.
    """
    database = cast(Database, cast(Any, client.app).state.database)
    job_id = UUID("00000000-0000-7000-8000-000000000601")
    digest = "c" * 64
    dataset_id = "synthetic-traced-contract-v1"
    packet = ReviewPacket(
        dataset_id=dataset_id,
        page_number=1,
        image_sha256=digest,
        readings=[
            DimensionReading(
                id="rd_1111111111111111",
                evidence=EvidenceRegion(
                    dataset_id=dataset_id,
                    page_number=1,
                    image_sha256=digest,
                    bbox=PixelBox(left=10, top=20, right=80, bottom=50),
                ),
                raw_text="19,75",
                value_si=Decimal("19.75"),
                unit=UnitCode.METRE,
                kind=MeasurementKind.WIDTH,
                written_decimals=2,
                target_hint="muro do fundo",
                extractor="contract-fixture",
                extractor_version="v1",
                status=ReadingStatus.CONFIRMED,
                decision=HumanDecision(
                    decision_id=TRACED_DECISION_ID,
                    action="confirm",
                    reviewer_id="reviewer",
                    reviewer_role="engineer",
                    decided_at=datetime.now(UTC),
                    note="Cota conferida na evidência protegida.",
                ),
            )
        ],
        safety_notes=["Fixture sintética.", "Revisão humana obrigatória."],
    )
    associations = AssociationSet.model_validate(
        {
            "dataset_id": dataset_id,
            "page_number": 1,
            "image_sha256": digest,
            "candidates": [
                {
                    "reading_id": "rd_1111111111111111",
                    "proposal_id": "vp_1111111111111111",
                    "proposal_kind": "line",
                    "relation": "nearest_geometry",
                    "pixel_distance": 1,
                    "proximity_score": 0.9,
                    "visual_quality_score": 0.8,
                }
            ],
            "unassociated_reading_ids": [],
            "safety_notes": ["pixels", "não confirma", "não exporta"],
        }
    )
    provenance = Provenance(
        source_type="human_confirmed_reading+traced_span",
        source_ids=["rd_1111111111111111", TRACED_DECISION_ID, "vp_1111111111111111"],
        summary_code="CONFIRMED_READING_OVER_TRACED_SPAN",
    )
    scene = SceneRevision(
        job_id=job_id,
        version=1,
        entities=[
            Entity(
                id=TRACED_ENTITY_ID,
                kind=EntityKind.LINE,
                layer=LayerName.MURO,
                precision=Precision.EXACT,
                geometry=LineGeometry(start=Point2D(x=0, y=0), end=Point2D(x=19.75, y=0)),
                provenance=provenance,
            )
        ],
        measurements=[
            Measurement(
                entity_id=TRACED_ENTITY_ID,
                kind=MeasurementKind.WIDTH,
                raw_text="19,75",
                value_si=Decimal("19.75"),
                unit=UnitCode.METRE,
                written_decimals=2,
                confirmed=True,
                provenance=provenance,
            )
        ],
    )
    now = datetime.now(UTC)
    with database.sessions.begin() as session:
        session.add(
            ProjectRecord(
                id="project-traced",
                tenant_id="tenant-a",
                name="Traçado sintético",
                default_unit="m",
                created_by="worker",
                expires_at=now,
            )
        )
        session.add(
            UploadRecord(
                id="upload-traced",
                tenant_id="tenant-a",
                object_key="protected/traced.pdf",
                filename="traced.pdf",
                content_type="application/pdf",
                size_bytes=1,
                sha256="d" * 64,
            )
        )
        session.flush()
        session.add(
            JobRecord(
                id=str(job_id),
                tenant_id="tenant-a",
                project_id="project-traced",
                upload_id="upload-traced",
                status="REVIEW_REQUIRED",
                stage="PREVIEWING",
                expires_at=now,
            )
        )
        session.flush()
        session.add(
            RevisionRecord(
                id=str(scene.id),
                tenant_id="tenant-a",
                job_id=str(job_id),
                version=scene.version,
                scene=scene.model_dump(mode="json"),
                created_by="trace-solver",
            )
        )
        session.flush()
        session.add(
            ReviewRevisionRecord(
                id="00000000-0000-7000-8000-000000000602",
                tenant_id="tenant-a",
                job_id=str(job_id),
                version=1,
                packet_json=packet.model_dump(mode="json"),
                associations_json=associations.model_dump(mode="json"),
                selected_associations_json={"rd_1111111111111111": "vp_1111111111111111"},
                trace_acceptance_json={"acceptance_id": "ta_1111111111111111"},
                evidence_refs_json={"source_image_key": "tenants/tenant-a/review/source.png"},
                scene_revision_id=str(scene.id),
                created_by="local-worker",
            )
        )
    return job_id


def test_rectification_supersedes_traced_geometry_without_touching_it(tmp_path: Path) -> None:
    client = _client(tmp_path)
    job_id = _seed_traced_session(client)

    rectified = client.post(
        f"/v1/jobs/{job_id}/review/rectifications",
        headers={**_headers("tenant-a"), "Idempotency-Key": "rectify-traced"},
        json=_rectification_payload(
            1,
            rectifies_decision_id=TRACED_DECISION_ID,
            raw_text="19,25",
            value_si="19.25",
            unit="m",
            kind="width",
        ),
    )

    assert rectified.status_code == 200
    body = rectified.json()
    assert body["version"] == 2
    scene = body["scene"]
    # Cena NOVA, não aprovada: a traçada continua no banco exatamente como estava.
    assert scene["version"] == 2
    assert scene["approved"] is False
    superseded = next(
        issue for issue in scene["issues"] if issue["code"] == "READING_DECISION_SUPERSEDED"
    )
    assert superseded["severity"] == "critical"
    assert superseded["entity_ids"] == [str(TRACED_ENTITY_ID)]
    assert "READING_DECISION_SUPERSEDED" in body["blockers"]
    assert (
        "OPEN_CRITICAL_ISSUE:READING_DECISION_SUPERSEDED"
        in SceneRevision.model_validate(scene).export_errors()
    )
    # O aceite de traçado viaja verbatim: ele é o registro de um ato que aconteceu.
    database = cast(Database, cast(Any, client.app).state.database)
    with database.sessions() as session:
        revisions = session.scalars(
            select(ReviewRevisionRecord)
            .where(ReviewRevisionRecord.job_id == str(job_id))
            .order_by(ReviewRevisionRecord.version)
        ).all()
        assert [item.version for item in revisions] == [1, 2]
        assert revisions[1].trace_acceptance_json == revisions[0].trace_acceptance_json
        # A revisão anterior mantém a decisão original intacta.
        previous_reading = revisions[0].packet_json["readings"][0]
        assert previous_reading["decision"]["decision_id"] == TRACED_DECISION_ID
        assert previous_reading["value_si"] == "19.75"
        scenes = session.scalars(
            select(RevisionRecord)
            .where(RevisionRecord.job_id == str(job_id))
            .order_by(RevisionRecord.version)
        ).all()
        assert [item.version for item in scenes] == [1, 2]
        assert scenes[0].scene["entities"] == scenes[1].scene["entities"]
        traced_scene_id = scenes[0].id

    stale_approval = client.post(
        f"/v1/jobs/{job_id}/approve",
        headers={**_headers("tenant-a"), "Idempotency-Key": "approve-stale-scene"},
        json=_approval_payload(traced_scene_id),
    )
    assert stale_approval.status_code == 409
    assert stale_approval.json()["detail"]["code"] == "REVISION_CONFLICT"


def test_rectification_after_approval_leaves_the_approved_package_untouched(
    tmp_path: Path,
) -> None:
    client = _client(tmp_path)
    job_id = _seed_traced_session(client)
    database = cast(Database, cast(Any, client.app).state.database)
    with database.sessions() as session:
        draft_id = session.scalars(
            select(RevisionRecord.id).where(RevisionRecord.job_id == str(job_id))
        ).one()

    approved = client.post(
        f"/v1/jobs/{job_id}/approve",
        headers={**_headers("tenant-a"), "Idempotency-Key": "approve-before-rectify"},
        json=_approval_payload(draft_id),
    )
    assert approved.status_code == 200
    approved_id = approved.json()["id"]
    export = client.post(
        f"/v1/jobs/{job_id}/exports",
        headers={**_headers("tenant-a"), "Idempotency-Key": "export-before-rectify"},
        json={"revision_id": approved_id},
    )
    assert export.status_code == 202
    export_id = export.json()["export_id"]

    rectified = client.post(
        f"/v1/jobs/{job_id}/review/rectifications",
        headers={**_headers("tenant-a"), "Idempotency-Key": "rectify-after-approval"},
        json=_rectification_payload(
            1,
            rectifies_decision_id=TRACED_DECISION_ID,
            raw_text="19,25",
            value_si="19.25",
            unit="m",
            kind="width",
        ),
    )

    assert rectified.status_code == 200
    assert rectified.json()["scene"]["approved"] is False
    assert rectified.json()["scene"]["version"] == 3
    with database.sessions() as session:
        still_approved = session.get(RevisionRecord, approved_id)
        assert still_approved is not None
        assert still_approved.approved_at is not None
        assert still_approved.scene["approved"] is True
        approval = session.scalars(select(ApprovalRecord)).one()
        assert approval.approved_revision_id == approved_id
        artifact = session.get(ExportArtifactRecord, export_id)
        assert artifact is not None
        assert artifact.scene_revision_id == approved_id
        assert artifact.status == "QUEUED"


def test_rectification_of_an_annotation_keeps_the_association_rules(tmp_path: Path) -> None:
    client = _client(tmp_path)
    job_id = _seed_review_session(client)
    assert _confirm_solver_readings(client, job_id, base_version=1).status_code == 200
    previous_decision_id = _current_decision_id(client, job_id, "rd_1111111111111111")
    endpoint = f"/v1/jobs/{job_id}/review/rectifications"

    contradictory = client.post(
        endpoint,
        headers={**_headers("tenant-a"), "Idempotency-Key": "rectify-annotation-conflict"},
        json=_rectification_payload(2, rectifies_decision_id=previous_decision_id, annotation=True),
    )
    assert contradictory.status_code == 422
    assert "não leva associação" in contradictory.json()["detail"]["detail"]

    missing_association = client.post(
        endpoint,
        headers={**_headers("tenant-a"), "Idempotency-Key": "rectify-no-association"},
        json=_rectification_payload(
            2, rectifies_decision_id=previous_decision_id, association_proposal_id=None
        ),
    )
    assert missing_association.status_code == 422
    assert "declaração de anotação" in missing_association.json()["detail"]["detail"]

    annotated = client.post(
        endpoint,
        headers={**_headers("tenant-a"), "Idempotency-Key": "rectify-annotation"},
        json=_rectification_payload(
            2,
            rectifies_decision_id=previous_decision_id,
            association_proposal_id=None,
            annotation=True,
            justification="É anotação da folha, não mede elemento.",
        ),
    )
    assert annotated.status_code == 200
    assert "rd_1111111111111111" not in annotated.json()["selected_associations"]


def _confirm_chain_readings(client: TestClient, job_id: UUID, *, base_version: int = 1) -> Any:
    """Confirma as quatro cotas de planta como anotação: sem associação e fora do solver."""
    return client.post(
        f"/v1/jobs/{job_id}/review/decisions",
        headers={**_headers("tenant-a"), "Idempotency-Key": f"chain-readings-{base_version}"},
        json={
            "base_version": base_version,
            "decisions": [
                {
                    "reading_id": reading_id,
                    "action": "confirm",
                    "justification": "Cota de planta conferida na folha.",
                    "annotation": True,
                }
                for reading_id in (
                    "rd_5555555555555555",
                    "rd_6666666666666666",
                    "rd_7777777777777777",
                    "rd_8888888888888888",
                )
            ],
        },
    )


def _declare_chain(
    client: TestClient,
    job_id: UUID,
    *,
    base_version: int,
    key: str,
    total_id: str = "rd_5555555555555555",
    part_ids: tuple[str, ...] = ("rd_6666666666666666", "rd_7777777777777777"),
) -> Any:
    return client.post(
        f"/v1/jobs/{job_id}/review/chains",
        headers={**_headers("tenant-a"), "Idempotency-Key": key},
        json={
            "base_version": base_version,
            "action": "declare",
            "total_id": total_id,
            "part_ids": list(part_ids),
        },
    )


def test_suggested_chains_only_appear_after_the_readings_are_confirmed(tmp_path: Path) -> None:
    """A sugestão é aritmética sobre leitura CONFIRMADA: sem decisão humana não há soma."""
    client = _client(tmp_path)
    job_id = _seed_review_session(client, chain_readings=True)

    before = client.get(f"/v1/jobs/{job_id}/review", headers=_headers("tenant-a")).json()
    assert before["suggested_chains"] == []
    assert before["declared_chains"] == []

    confirmed = _confirm_chain_readings(client, job_id)
    assert confirmed.status_code == 200
    suggested = confirmed.json()["suggested_chains"]

    assert len(suggested) == 1
    assert suggested[0]["total"]["reading_id"] == "rd_5555555555555555"
    assert {part["reading_id"] for part in suggested[0]["parts"]} == {
        "rd_6666666666666666",
        "rd_7777777777777777",
    }
    # Decimal viaja como string: o valor escrito na cota não pode passar por float.
    assert suggested[0]["residual_m"] == "0.00"
    assert isinstance(suggested[0]["tolerance_m"], str)


def test_declared_chain_that_closes_is_recorded_without_touching_the_blockers(
    tmp_path: Path,
) -> None:
    client = _client(tmp_path)
    job_id = _seed_review_session(client, chain_readings=True)
    confirmed = _confirm_chain_readings(client, job_id)
    assert confirmed.status_code == 200
    blockers_before = confirmed.json()["blockers"]

    declared = _declare_chain(client, job_id, base_version=2, key="chain-declare")

    assert declared.status_code == 200
    assert declared.json()["version"] == 3
    chains = declared.json()["declared_chains"]
    assert len(chains) == 1
    assert chains[0]["status"] == "closes"
    assert chains[0]["issue"] is None
    assert chains[0]["declared_by"] == "reviewer"
    assert chains[0]["chain"]["total"]["reading_id"] == "rd_5555555555555555"
    # Conferência de cota não é veto de exportação: a lista de blockers é a mesma.
    assert declared.json()["blockers"] == blockers_before


def test_declared_chain_that_does_not_close_is_a_warning_and_never_a_blocker(
    tmp_path: Path,
) -> None:
    """Declarar cadeia que NÃO fecha é o caso desejado: é ela que denuncia o trecho faltando."""
    client = _client(tmp_path)
    job_id = _seed_review_session(client, chain_readings=True)
    confirmed = _confirm_chain_readings(client, job_id)
    assert confirmed.status_code == 200
    blockers_before = confirmed.json()["blockers"]

    declared = _declare_chain(
        client,
        job_id,
        base_version=2,
        key="chain-mismatch",
        part_ids=("rd_6666666666666666", "rd_8888888888888888"),
    )

    assert declared.status_code == 200
    chains = declared.json()["declared_chains"]
    assert chains[0]["status"] == "mismatch"
    assert chains[0]["issue"]["code"] == "DIMENSION_CHAIN_MISMATCH"
    assert chains[0]["issue"]["severity"] == "warning"
    assert chains[0]["chain"]["residual_m"] == "-10.90"
    assert declared.json()["blockers"] == blockers_before
    assert "DIMENSION_CHAIN_MISMATCH" not in declared.json()["blockers"]


def test_chain_refuses_what_cannot_be_assembled_and_a_stale_base_version(
    tmp_path: Path,
) -> None:
    client = _client(tmp_path)
    job_id = _seed_review_session(client, chain_readings=True)
    assert _confirm_chain_readings(client, job_id).status_code == 200
    endpoint = f"/v1/jobs/{job_id}/review/chains"

    unconfirmed = _declare_chain(
        client,
        job_id,
        base_version=2,
        key="chain-unconfirmed",
        part_ids=("rd_6666666666666666", "rd_1111111111111111"),
    )
    assert unconfirmed.status_code == 422
    assert unconfirmed.json()["detail"]["code"] == "CHAIN_INVALID"
    assert "rd_1111111111111111" in unconfirmed.json()["detail"]["detail"]

    single_part = _declare_chain(
        client,
        job_id,
        base_version=2,
        key="chain-single-part",
        part_ids=("rd_6666666666666666",),
    )
    assert single_part.status_code == 422
    assert single_part.json()["detail"]["code"] == "CHAIN_INVALID"

    without_total = client.post(
        endpoint,
        headers={**_headers("tenant-a"), "Idempotency-Key": "chain-no-total"},
        json={
            "base_version": 2,
            "action": "declare",
            "part_ids": ["rd_6666666666666666", "rd_7777777777777777"],
        },
    )
    assert without_total.status_code == 422
    assert without_total.json()["detail"]["code"] == "CHAIN_INVALID"

    stale = _declare_chain(client, job_id, base_version=1, key="chain-stale")
    assert stale.status_code == 409
    assert stale.json()["detail"]["code"] == "REVISION_CONFLICT"

    other_tenant = client.post(
        endpoint,
        headers={**_headers("tenant-b"), "Idempotency-Key": "chain-other-tenant"},
        json={
            "base_version": 2,
            "action": "declare",
            "total_id": "rd_5555555555555555",
            "part_ids": ["rd_6666666666666666", "rd_7777777777777777"],
        },
    )
    assert other_tenant.status_code == 404


def test_retracting_a_chain_removes_it_and_an_unknown_id_is_not_found(tmp_path: Path) -> None:
    client = _client(tmp_path)
    job_id = _seed_review_session(client, chain_readings=True)
    assert _confirm_chain_readings(client, job_id).status_code == 200
    declared = _declare_chain(client, job_id, base_version=2, key="chain-to-retract")
    assert declared.status_code == 200
    chain_id = declared.json()["declared_chains"][0]["chain_id"]
    assert chain_id.startswith("ch_")
    endpoint = f"/v1/jobs/{job_id}/review/chains"

    unknown = client.post(
        endpoint,
        headers={**_headers("tenant-a"), "Idempotency-Key": "chain-retract-unknown"},
        json={"base_version": 3, "action": "retract", "chain_id": "ch_0000000000000000"},
    )
    assert unknown.status_code == 404
    assert unknown.json()["detail"]["code"] == "CHAIN_NOT_FOUND"

    retracted = client.post(
        endpoint,
        headers={**_headers("tenant-a"), "Idempotency-Key": "chain-retract"},
        json={"base_version": 3, "action": "retract", "chain_id": chain_id},
    )
    assert retracted.status_code == 200
    assert retracted.json()["declared_chains"] == []
    assert retracted.json()["version"] == 4


def test_rectified_reading_makes_the_chain_stale_and_a_later_decision_keeps_it(
    tmp_path: Path,
) -> None:
    """A cadeia declarada não some quando o chão sai de baixo dela — ela avisa.

    E nenhuma decisão posterior a apaga: sem o carry-forward de `declared_chains_json`,
    a declaração evaporaria na revisão seguinte sem ninguém retratá-la.
    """
    client = _client(tmp_path)
    job_id = _seed_review_session(client, chain_readings=True)
    assert _confirm_chain_readings(client, job_id).status_code == 200
    declared = _declare_chain(client, job_id, base_version=2, key="chain-before-rect")
    assert declared.status_code == 200

    # Uma decisão sobre outra leitura NÃO pode apagar a cadeia declarada.
    decided = client.post(
        f"/v1/jobs/{job_id}/review/decisions",
        headers={**_headers("tenant-a"), "Idempotency-Key": "chain-carry-forward"},
        json={
            "base_version": 3,
            "decisions": [
                {
                    "reading_id": "rd_1111111111111111",
                    "action": "confirm",
                    "justification": "Evidência sintética revisada.",
                    "association_proposal_id": "vp_1111111111111111",
                }
            ],
        },
    )
    assert decided.status_code == 200
    assert len(decided.json()["declared_chains"]) == 1
    assert decided.json()["declared_chains"][0]["status"] == "closes"

    previous_decision_id = _current_decision_id(client, job_id, "rd_6666666666666666")
    rectified = client.post(
        f"/v1/jobs/{job_id}/review/rectifications",
        headers={**_headers("tenant-a"), "Idempotency-Key": "chain-rectify"},
        json={
            "base_version": 4,
            "rectifications": [
                {
                    "reading_id": "rd_6666666666666666",
                    "action": "reject",
                    "rectifies_decision_id": previous_decision_id,
                    "justification": "O 12,00 é de outra folha; não vale para este croqui.",
                }
            ],
        },
    )

    assert rectified.status_code == 200
    chains = rectified.json()["declared_chains"]
    assert len(chains) == 1
    assert chains[0]["status"] == "stale"
    assert chains[0]["chain"] is None
    assert chains[0]["issue"]["code"] == "CHAIN_READING_SUPERSEDED"
    assert chains[0]["issue"]["severity"] == "warning"
    assert "CHAIN_READING_SUPERSEDED" not in rectified.json()["blockers"]

    # Cadeia vencida continua retratável: é o único jeito de tirá-la da tela.
    retracted = client.post(
        f"/v1/jobs/{job_id}/review/chains",
        headers={**_headers("tenant-a"), "Idempotency-Key": "chain-retract-stale"},
        json={
            "base_version": 5,
            "action": "retract",
            "chain_id": chains[0]["chain_id"],
        },
    )
    assert retracted.status_code == 200
    assert retracted.json()["declared_chains"] == []


def test_idempotent_replay_of_a_response_stored_before_the_chain_fields(tmp_path: Path) -> None:
    """Resposta gravada antes dos campos existirem é revalidada no replay — e não pode quebrar."""
    client = _client(tmp_path)
    job_id = _seed_review_session(client, chain_readings=True)
    payload = {
        "base_version": 1,
        "decisions": [
            {
                "reading_id": "rd_1111111111111111",
                "action": "confirm",
                "justification": "Conferido no material protegido.",
                "association_proposal_id": "vp_1111111111111111",
            }
        ],
    }
    headers = {**_headers("tenant-a"), "Idempotency-Key": "chain-legacy-replay"}
    first = client.post(f"/v1/jobs/{job_id}/review/decisions", headers=headers, json=payload)
    assert first.status_code == 200

    database = cast(Database, cast(Any, client.app).state.database)
    with database.sessions.begin() as session:
        record = session.query(IdempotencyRecord).filter_by(key="chain-legacy-replay").one()
        legacy = dict(record.response_json)
        legacy.pop("suggested_chains")
        legacy.pop("declared_chains")
        record.response_json = legacy

    replayed = client.post(f"/v1/jobs/{job_id}/review/decisions", headers=headers, json=payload)

    assert replayed.status_code == 200
    assert replayed.json()["suggested_chains"] == []
    assert replayed.json()["declared_chains"] == []


CONFIDENCE_FIELDS = (
    "reading_confidences",
    "confidence_shadow",
    "auto_association_rate",
    "review_rate",
)


def _shadow_point(response: dict[str, Any], reading_cut: float, association_cut: float) -> Any:
    """Um ponto nomeado da grade de shadow, para o teste não depender da ordem dela."""
    return next(
        point
        for point in response["confidence_shadow"]
        if point["reading_threshold"] == reading_cut
        and point["association_threshold"] == association_cut
    )


def _reading_confidences(response: dict[str, Any]) -> dict[str, float]:
    return {
        item["reading_id"]: item["reading_confidence"] for item in response["reading_confidences"]
    }


def test_review_publishes_the_confidence_shadow_gravado_na_revisao(tmp_path: Path) -> None:
    """O shadow é observação gravada por revisão: o que CADA corte teria auto-decidido.

    A revisão desta fixture é montada direto no banco, sem passar por nenhum dos dois
    caminhos de escrita — como uma linha gravada antes de a coluna existir. Ela responde
    com os campos vazios, nunca com erro: ausência de registro, jamais zero medido. Da
    primeira revisão escrita pela API em diante o registro existe.
    """
    client = _client(tmp_path)
    job_id = _seed_review_session(client, chain_readings=True)

    seeded = client.get(f"/v1/jobs/{job_id}/review", headers=_headers("tenant-a")).json()
    assert seeded["reading_confidences"] == []
    assert seeded["confidence_shadow"] == []
    assert seeded["auto_association_rate"] is None
    assert seeded["review_rate"] is None

    confirmed = _confirm_chain_readings(client, job_id)
    assert confirmed.status_code == 200
    body = confirmed.json()

    confidences = _reading_confidences(body)
    assert len(confidences) == 7
    # Participar de uma cadeia que fecha corrobora a leitura; a cota que não entra em
    # cadeia nenhuma fica no valor neutro do sinal, não abaixo dele.
    assert confidences["rd_5555555555555555"] == 0.8
    assert confidences["rd_6666666666666666"] == 0.8
    assert confidences["rd_8888888888888888"] == 0.65
    assert confidences["rd_1111111111111111"] == 0.65

    assert len(body["confidence_shadow"]) == 36
    generous = _shadow_point(body, 0.6, 0.7)
    assert [
        (choice["reading_id"], choice["proposal_id"]) for choice in generous["auto_choices"]
    ] == [
        ("rd_1111111111111111", "vp_1111111111111111"),
        ("rd_2222222222222222", "vp_2222222222222222"),
    ]
    assert generous["auto_choices"][0]["reading_confidence"] == 0.65
    assert generous["auto_choices"][0]["association_confidence"] == 0.92

    # Cota confirmada e corroborada por cadeia, mas sem candidato de associação nenhum,
    # não é auto-decidível em corte algum: não há segmento a que associá-la.
    assert _shadow_point(body, 0.7, 0.5)["auto_choices"] == []
    # Ponto de referência das taxas é o mais conservador da grade.
    assert _shadow_point(body, 0.95, 0.95)["auto_choices"] == []
    # 0 de 3 cotas com candidato seriam auto-associadas; as 7 seguem exigindo revisão.
    assert body["auto_association_rate"] == 0.0
    assert body["review_rate"] == 1.0


def test_o_shadow_gravado_carimba_a_versao_do_score(tmp_path: Path) -> None:
    """Sem o carimbo, shadows de pesos diferentes conviveriam indistinguíveis no banco.

    Os pesos vão ser recalibrados; o relatório de calibração precisa poder separar o que
    saiu de qual versão em vez de somar tudo em silêncio.
    """
    client = _client(tmp_path)
    job_id = _seed_review_session(client, chain_readings=True)
    assert _confirm_chain_readings(client, job_id).status_code == 200

    database = cast(Database, cast(Any, client.app).state.database)
    with database.sessions() as session:
        stored = (
            session.query(ReviewRevisionRecord)
            .filter_by(job_id=str(job_id), version=2)
            .one()
            .confidence_shadow_json
        )

    assert stored["score_version"] == CONFIDENCE_SCORE_VERSION
    assert stored["readings_total"] == 7
    assert stored["readings_with_candidate"] == 3


def test_uma_cadeia_declarada_que_nao_fecha_baixa_a_confianca_de_quem_so_esta_nela(
    tmp_path: Path,
) -> None:
    """Declaração humana contradita pela aritmética é evidência CONTRA a participante.

    Declarar é afirmar que estas parcelas, e só estas, compõem este total; quando a conta
    não bate, alguma das leituras está errada. Quem participa só dessa cadeia cai; quem
    também participa de uma cadeia que fecha continua sustentada por ela — `any(closes)`
    vence, e é a T1 que decide isso, não a API.
    """
    client = _client(tmp_path)
    job_id = _seed_review_session(client, chain_readings=True)
    confirmed = _confirm_chain_readings(client, job_id)
    assert confirmed.status_code == 200
    before = _reading_confidences(confirmed.json())
    # A cadeia sugerida que fecha (25,90 = 12,00 + 13,90) sustenta três leituras; a quarta
    # não entra em cadeia nenhuma e fica no valor neutro do sinal.
    assert before["rd_6666666666666666"] == 0.8
    assert before["rd_8888888888888888"] == 0.65

    declared = _declare_chain(
        client,
        job_id,
        base_version=2,
        key="confidence-chain-mismatch",
        part_ids=("rd_6666666666666666", "rd_8888888888888888"),
    )

    assert declared.status_code == 200
    assert declared.json()["declared_chains"][0]["status"] == "mismatch"
    after = _reading_confidences(declared.json())
    # Só a cadeia contradita explica esta leitura: a confiança cai.
    assert after["rd_8888888888888888"] == 0.5
    # Esta participa das duas, e a que fecha continua valendo.
    assert after["rd_6666666666666666"] == 0.8
    # A cota fora da declaração não é afetada por ela.
    assert after["rd_7777777777777777"] == before["rd_7777777777777777"]


def test_uma_cadeia_declarada_que_vence_deixa_de_pesar_no_sinal(tmp_path: Path) -> None:
    """`stale` é conferência impossível, não conferência reprovada: sai do sinal.

    A cadeia perdeu uma participante (retificada depois de declarada) e deixou de ser
    verificável. Mantê-la penalizando seria acusar a leitura com base numa conta que
    ninguém consegue mais fazer.
    """
    client = _client(tmp_path)
    job_id = _seed_review_session(client, chain_readings=True)
    assert _confirm_chain_readings(client, job_id).status_code == 200
    declared = _declare_chain(
        client,
        job_id,
        base_version=2,
        key="confidence-chain-stale",
        part_ids=("rd_6666666666666666", "rd_8888888888888888"),
    )
    assert declared.status_code == 200
    assert _reading_confidences(declared.json())["rd_8888888888888888"] == 0.5

    previous_decision_id = _current_decision_id(client, job_id, "rd_6666666666666666")
    rectified = client.post(
        f"/v1/jobs/{job_id}/review/rectifications",
        headers={**_headers("tenant-a"), "Idempotency-Key": "confidence-chain-rectify"},
        json={
            "base_version": 3,
            "rectifications": [
                {
                    "reading_id": "rd_6666666666666666",
                    "action": "reject",
                    "rectifies_decision_id": previous_decision_id,
                    "justification": "O 12,00 é de outra folha; não vale para este croqui.",
                }
            ],
        },
    )

    assert rectified.status_code == 200
    assert rectified.json()["declared_chains"][0]["status"] == "stale"
    # Sem a cadeia vencida e sem a sugerida (que também perdeu o 12,00), a leitura volta
    # ao valor neutro do sinal de cadeia em vez de continuar penalizada.
    assert _reading_confidences(rectified.json())["rd_8888888888888888"] == 0.65


def test_o_shadow_nunca_decide_associa_ou_bloqueia(tmp_path: Path) -> None:
    """O registro diz o que TERIA feito; a revisão continua exigindo o ato humano."""
    client = _client(tmp_path)
    job_id = _seed_review_session(client)

    decided = client.post(
        f"/v1/jobs/{job_id}/review/decisions",
        headers={**_headers("tenant-a"), "Idempotency-Key": "shadow-decides-nothing"},
        json={
            "base_version": 1,
            "decisions": [
                {
                    "reading_id": "rd_1111111111111111",
                    "action": "confirm",
                    "justification": "Evidência sintética revisada.",
                    "association_proposal_id": "vp_1111111111111111",
                }
            ],
        },
    )

    assert decided.status_code == 200
    body = decided.json()
    auto = {choice["reading_id"] for choice in _shadow_point(body, 0.6, 0.7)["auto_choices"]}
    # O corte generoso diria que esta cota também seria auto-associável...
    assert "rd_2222222222222222" in auto
    untouched = next(
        reading for reading in body["packet"]["readings"] if reading["id"] == "rd_2222222222222222"
    )
    # ...e ela continua proposta, sem decisão e sem associação explícita.
    assert untouched["status"] == "proposed"
    assert untouched["decision"] is None
    assert body["selected_associations"] == {"rd_1111111111111111": "vp_1111111111111111"}
    # Confiança não vira pendência de exportação nem issue: o solver continua cobrando
    # confirmação humana justamente da cota que o corte teria resolvido sozinho.
    assert "HEIGHT_HUMAN_CONFIRMATION_REQUIRED:rd_2222222222222222" in body["blockers"]
    assert "ACC_GUA_001" in body["blockers"]
    assert not [code for code in body["blockers"] if "CONFIDENCE" in code or "SHADOW" in code]
    # Uma confiança alta também não abre issue: com uma única cota confirmada não há cena
    # métrica ainda, e o shadow não acrescenta nada a essa lista.
    assert body["issues"] == []


def test_os_campos_de_confianca_sao_identicos_em_duas_leituras_da_mesma_revisao(
    tmp_path: Path,
) -> None:
    """Determinismo fim a fim: a resposta do comando e a leitura seguinte não divergem."""
    client = _client(tmp_path)
    job_id = _seed_review_session(client, chain_readings=True)
    written = _confirm_chain_readings(client, job_id)
    assert written.status_code == 200

    first = client.get(f"/v1/jobs/{job_id}/review", headers=_headers("tenant-a")).json()
    second = client.get(f"/v1/jobs/{job_id}/review", headers=_headers("tenant-a")).json()

    for field in CONFIDENCE_FIELDS:
        assert first[field] == written.json()[field], field
        assert second[field] == first[field], field


def test_idempotent_replay_of_a_response_stored_before_the_confidence_fields(
    tmp_path: Path,
) -> None:
    """Resposta gravada antes dos campos existirem é revalidada no replay — e não quebra."""
    client = _client(tmp_path)
    job_id = _seed_review_session(client)
    payload = {
        "base_version": 1,
        "decisions": [
            {
                "reading_id": "rd_1111111111111111",
                "action": "confirm",
                "justification": "Conferido no material protegido.",
                "association_proposal_id": "vp_1111111111111111",
            }
        ],
    }
    headers = {**_headers("tenant-a"), "Idempotency-Key": "confidence-legacy-replay"}
    first = client.post(f"/v1/jobs/{job_id}/review/decisions", headers=headers, json=payload)
    assert first.status_code == 200

    database = cast(Database, cast(Any, client.app).state.database)
    with database.sessions.begin() as session:
        record = session.query(IdempotencyRecord).filter_by(key="confidence-legacy-replay").one()
        legacy = dict(record.response_json)
        for field in CONFIDENCE_FIELDS:
            legacy.pop(field)
        record.response_json = legacy

    replayed = client.post(f"/v1/jobs/{job_id}/review/decisions", headers=headers, json=payload)

    assert replayed.status_code == 200
    assert replayed.json()["reading_confidences"] == []
    assert replayed.json()["confidence_shadow"] == []
    assert replayed.json()["auto_association_rate"] is None
    assert replayed.json()["review_rate"] is None


def _seed_auto_decided_review(
    client: TestClient, job_id: UUID, *, threshold: float = 0.6
) -> dict[str, str]:
    """Reescreve a revisão 1 como o worker a gravaria com o modo automático ligado.

    A API nunca cria decisão de ator-máquina — ela vem do worker, nunca de request —, e é
    por isso que a fixture usa o próprio código do ato em vez de fabricar a decisão à mão:
    o que a rota precisa aguentar é exatamente o que aquele caminho grava.
    """
    database = cast(Database, cast(Any, client.app).state.database)
    with database.sessions.begin() as session:
        record = session.query(ReviewRevisionRecord).filter_by(job_id=str(job_id), version=1).one()
        outcome = apply_auto_association(
            ReviewPacket.model_validate(record.packet_json),
            AssociationSet.model_validate(record.associations_json),
            mode=AutoAssociationMode(threshold=threshold),
        )
        record.packet_json = outcome.packet.model_dump(mode="json")
        record.selected_associations_json = outcome.selected_associations
    return {decision.reading_id: decision.decision_id for decision in outcome.decisions}


def test_a_revisao_exibe_o_ator_de_cada_decisao(tmp_path: Path) -> None:
    """Proveniência atravessa até a resposta: quem lê a revisão vê quem decidiu."""
    client = _client(tmp_path)
    job_id = _seed_review_session(client)
    auto = _seed_auto_decided_review(client, job_id)
    # A cota de círculo tem associação ambígua na fixture (0,55) e fica de fora do corte.
    assert set(auto) == {"rd_1111111111111111", "rd_2222222222222222"}

    body = client.get(f"/v1/jobs/{job_id}/review", headers=_headers("tenant-a")).json()

    readings = {reading["id"]: reading for reading in body["packet"]["readings"]}
    automatic = readings["rd_1111111111111111"]["decision"]
    assert automatic["actor"] == "system"
    assert automatic["reviewer_role"] is None
    assert automatic["reviewer_id"].startswith("system:auto-association@")
    # Por qual regra a máquina decidiu viaja estruturado, não escondido na justificativa.
    assert automatic["auto_tier"] == "cota"
    assert body["selected_associations"]["rd_1111111111111111"] == "vp_1111111111111111"
    assert readings["rd_3333333333333333"]["decision"] is None

    decided = client.post(
        f"/v1/jobs/{job_id}/review/decisions",
        headers={**_headers("tenant-a"), "Idempotency-Key": "actor-human-decision"},
        json={
            "base_version": 1,
            "decisions": [
                {
                    "reading_id": "rd_3333333333333333",
                    "action": "confirm",
                    "justification": "Exceção conferida na evidência protegida.",
                    "association_proposal_id": "vp_3333333333333333",
                }
            ],
        },
    )

    assert decided.status_code == 200
    human = next(
        reading["decision"]
        for reading in decided.json()["packet"]["readings"]
        if reading["id"] == "rd_3333333333333333"
    )
    assert human["actor"] == "human"
    assert human["reviewer_role"] == "engineer"
    # Pessoa decide por julgamento, não por tier: o campo não existe na decisão dela.
    assert human["auto_tier"] is None
    # A associação da máquina viaja para a revisão seguinte junto com a da pessoa.
    assert decided.json()["selected_associations"] == {
        "rd_1111111111111111": "vp_1111111111111111",
        "rd_2222222222222222": "vp_2222222222222222",
        "rd_3333333333333333": "vp_3333333333333333",
    }


def test_a_revisao_exibe_o_tier_de_cada_decisao_automatica(tmp_path: Path) -> None:
    """Com o corte em 0,7 nenhuma leitura passa nos dois eixos; a elevação passa no dela.

    A fixture não tem braço de OCR, então toda leitura fica em 0,65 de confiança de
    leitura. A cota de planta de associação altíssima (0,92) continua exceção — é o que a
    dupla testemunha cobra —, e a altura de associação 0,78 entra pelo tier de anotação.
    """
    client = _client(tmp_path)
    job_id = _seed_review_session(client)
    auto = _seed_auto_decided_review(client, job_id, threshold=0.7)

    assert set(auto) == {"rd_2222222222222222"}

    body = client.get(f"/v1/jobs/{job_id}/review", headers=_headers("tenant-a")).json()

    readings = {reading["id"]: reading for reading in body["packet"]["readings"]}
    annotation = readings["rd_2222222222222222"]["decision"]
    assert annotation["actor"] == "system"
    assert annotation["auto_tier"] == "anotacao"
    assert annotation["note"].startswith("Anotação automática")
    # Cota de planta com associação melhor ainda assim NÃO entrou: o não-vazamento do
    # ADR-0044 (D2) atravessa até a resposta que o revisor lê.
    assert readings["rd_1111111111111111"]["decision"] is None


def test_a_anotacao_automatica_tem_a_mesma_forma_da_anotacao_declarada_por_gente(
    tmp_path: Path,
) -> None:
    """Mesmo mecanismo, autoria diferente (ADR-0044, D1a).

    A anotação da folha é, neste contrato, a única confirmação SEM elemento associado —
    a regra recusa com 422 quem tenta associar uma. A anotação automática nasce com essa
    mesma forma: confirmada e ausente do mapa de associações. O que a distingue do ato
    humano é o ator e o tier, nunca o mecanismo — e é por isso que ela não vira restrição
    de geometria em caminho nenhum.
    """
    client = _client(tmp_path)
    job_id = _seed_review_session(client)
    auto = _seed_auto_decided_review(client, job_id, threshold=0.7)
    assert set(auto) == {"rd_2222222222222222"}

    declared = client.post(
        f"/v1/jobs/{job_id}/review/decisions",
        headers={**_headers("tenant-a"), "Idempotency-Key": "anotacao-humana"},
        json={
            "base_version": 1,
            "decisions": [
                {
                    "reading_id": "rd_3333333333333333",
                    "action": "confirm",
                    "justification": "Recado da folha: não mede elemento nenhum.",
                    "annotation": True,
                }
            ],
        },
    )

    assert declared.status_code == 200
    body = declared.json()
    readings = {reading["id"]: reading for reading in body["packet"]["readings"]}
    automatic = readings["rd_2222222222222222"]
    human = readings["rd_3333333333333333"]
    # Mesma forma: confirmada, e fora do mapa de associações.
    assert automatic["status"] == human["status"] == "confirmed"
    assert "rd_2222222222222222" not in body["selected_associations"]
    assert "rd_3333333333333333" not in body["selected_associations"]
    assert body["selected_associations"] == {}
    # Autoria diferente, e só ela.
    assert automatic["decision"]["actor"] == "system"
    assert automatic["decision"]["auto_tier"] == "anotacao"
    assert human["decision"]["actor"] == "human"
    assert human["decision"]["auto_tier"] is None


def test_a_tela_de_correcao_trata_a_anotacao_automatica_como_a_humana(
    tmp_path: Path,
) -> None:
    """Sem associação vigente, a correção não tem associação a pré-preencher.

    A tela lê `selected_associations` para montar a correção declarada; para uma anotação
    — de máquina ou de pessoa — não há entrada, e o formulário nasce na opção "anotação
    da folha". Aqui isso é conferido pelo dado que a resposta entrega, que é o que a tela
    consome.
    """
    client = _client(tmp_path)
    job_id = _seed_review_session(client)
    auto = _seed_auto_decided_review(client, job_id, threshold=0.7)

    body = client.get(f"/v1/jobs/{job_id}/review", headers=_headers("tenant-a")).json()

    assert body["selected_associations"].get("rd_2222222222222222") is None
    # E ela continua corrigível: o alvo da correção é a decisão, não a associação.
    rectified = client.post(
        f"/v1/jobs/{job_id}/review/rectifications",
        headers={**_headers("tenant-a"), "Idempotency-Key": "anotacao-auto-rectify"},
        json={
            "base_version": 1,
            "rectifications": [
                {
                    "reading_id": "rd_2222222222222222",
                    "action": "confirm",
                    "rectifies_decision_id": auto["rd_2222222222222222"],
                    "justification": "A altura é 3,90; a automática leu 21,75 da cota ao lado.",
                    "annotation": True,
                    "raw_text": "h=3,90",
                    "value_si": "3.90",
                    "unit": "m",
                }
            ],
        },
    )

    assert rectified.status_code == 200
    corrected = next(
        reading
        for reading in rectified.json()["packet"]["readings"]
        if reading["id"] == "rd_2222222222222222"
    )
    assert corrected["value_si"] == "3.90"
    assert corrected["decision"]["actor"] == "human"
    assert corrected["decision"]["auto_tier"] is None
    # Corrigida como anotação, continua sem vínculo — e sem virar geometria.
    assert "rd_2222222222222222" not in rectified.json()["selected_associations"]


def test_auto_decisao_nao_e_sobrescrita_e_e_retificavel_pelo_caminho_humano(
    tmp_path: Path,
) -> None:
    """A recíproca do ADR-0041: gente corrige a máquina pelo caminho do ADR-0022."""
    client = _client(tmp_path)
    job_id = _seed_review_session(client)
    auto = _seed_auto_decided_review(client, job_id)

    overwritten = client.post(
        f"/v1/jobs/{job_id}/review/decisions",
        headers={**_headers("tenant-a"), "Idempotency-Key": "auto-overwrite"},
        json={
            "base_version": 1,
            "decisions": [
                {
                    "reading_id": "rd_1111111111111111",
                    "action": "confirm",
                    "justification": "Tentativa de decidir de novo o que a máquina decidiu.",
                    "association_proposal_id": "vp_1111111111111111",
                }
            ],
        },
    )

    assert overwritten.status_code == 422
    assert overwritten.json()["detail"]["code"] == "READING_ALREADY_DECIDED"

    rectified = client.post(
        f"/v1/jobs/{job_id}/review/rectifications",
        headers={**_headers("tenant-a"), "Idempotency-Key": "auto-rectify"},
        json={
            "base_version": 1,
            "rectifications": [
                {
                    "reading_id": "rd_1111111111111111",
                    "action": "confirm",
                    "rectifies_decision_id": auto["rd_1111111111111111"],
                    "justification": "A automática leu a cota da folha ao lado; a largura é 26,10.",
                    "association_proposal_id": "vp_1111111111111111",
                    "raw_text": "26,10",
                    "value_si": "26.10",
                    "unit": "m",
                }
            ],
        },
    )

    assert rectified.status_code == 200
    corrected = next(
        reading
        for reading in rectified.json()["packet"]["readings"]
        if reading["id"] == "rd_1111111111111111"
    )
    assert corrected["value_si"] == "26.10"
    assert corrected["decision"]["actor"] == "human"
    assert corrected["decision"]["reviewer_role"] == "engineer"
    assert corrected["decision"]["rectifies_decision_id"] == auto["rd_1111111111111111"]
    assert corrected["decision"]["decision_id"] != auto["rd_1111111111111111"]


def test_confirmed_associations_create_only_a_blocked_draft_scene(tmp_path: Path) -> None:
    client = _client(tmp_path)
    job_id = _seed_review_session(client)
    response = client.post(
        f"/v1/jobs/{job_id}/review/decisions",
        headers=_headers("tenant-a"),
        json={
            "base_version": 1,
            "decisions": [
                {
                    "reading_id": "rd_1111111111111111",
                    "action": "confirm",
                    "justification": "Evidência sintética revisada.",
                    "association_proposal_id": "vp_1111111111111111",
                },
                {
                    "reading_id": "rd_2222222222222222",
                    "action": "confirm",
                    "justification": "Evidência sintética revisada.",
                    "association_proposal_id": "vp_2222222222222222",
                },
                {
                    "reading_id": "rd_3333333333333333",
                    "action": "confirm",
                    "justification": "Evidência sintética revisada.",
                    "association_proposal_id": "vp_3333333333333333",
                },
            ],
        },
    )

    assert response.status_code == 200
    assert response.json()["scene"]["approved"] is False
    assert "ACC_GUA_001" in response.json()["blockers"]
    criterion = next(issue for issue in response.json()["issues"] if issue["code"] == "ACC_GUA_001")
    assert criterion["severity"] == "critical"
    # A issue carrega o texto do critério do caso, não uma frase genérica.
    assert criterion["message"] == CRITERION_TEXT
    assert response.json()["required_criteria"] == [{"code": "ACC_GUA_001", "text": CRITERION_TEXT}]


def _job_status(client: TestClient, job_id: UUID) -> str:
    database = cast(Database, cast(Any, client.app).state.database)
    with database.sessions() as session:
        job = session.get(JobRecord, str(job_id))
        assert job is not None
        return job.status


def _approval_payload(revision_id: str, **overrides: Any) -> dict[str, Any]:
    return {
        "revision_id": revision_id,
        "source_evidence_checked": True,
        "geometry_checked": True,
        "limitations_acknowledged": True,
        "statement": "Geometria conferida contra a evidência protegida do levantamento.",
        **overrides,
    }


def test_approve_requires_engineer_and_every_explicit_verification(tmp_path: Path) -> None:
    client = _client(tmp_path)
    job_id = _seed_review_session(client)
    revision_id = client.get(f"/v1/jobs/{job_id}/review", headers=_headers("tenant-a")).json()[
        "scene"
    ]["id"]

    forbidden = client.post(
        f"/v1/jobs/{job_id}/approve",
        headers={**_headers("tenant-a", "cad_operator"), "Idempotency-Key": "approve-role"},
        json=_approval_payload(revision_id),
    )
    assert forbidden.status_code == 403

    for omitted in ("source_evidence_checked", "geometry_checked", "limitations_acknowledged"):
        payload = _approval_payload(revision_id)
        payload[omitted] = False
        refused = client.post(
            f"/v1/jobs/{job_id}/approve",
            headers={**_headers("tenant-a"), "Idempotency-Key": f"approve-{omitted}"},
            json=payload,
        )
        assert refused.status_code == 422

    short = client.post(
        f"/v1/jobs/{job_id}/approve",
        headers={**_headers("tenant-a"), "Idempotency-Key": "approve-short"},
        json=_approval_payload(revision_id, statement="curto demais"),
    )
    assert short.status_code == 422
    assert _job_status(client, job_id) != "APPROVED"


def test_approve_refuses_unknown_approximation_with_a_domain_error(tmp_path: Path) -> None:
    client = _client(tmp_path)
    job_id = _seed_review_session(client)
    revision_id = client.get(f"/v1/jobs/{job_id}/review", headers=_headers("tenant-a")).json()[
        "scene"
    ]["id"]

    response = client.post(
        f"/v1/jobs/{job_id}/approve",
        headers={**_headers("tenant-a"), "Idempotency-Key": "approve-unknown-approximation"},
        json=_approval_payload(
            revision_id,
            accepted_approximations=["00000000-0000-7000-8000-000000000999"],
        ),
    )

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "DOMAIN_VALIDATION_FAILED"


def test_approve_acknowledges_scope_criteria_and_stays_idempotent(tmp_path: Path) -> None:
    client = _client(tmp_path)
    job_id = _seed_review_session(client)
    solved = _confirm_solver_readings(client, job_id, base_version=1)
    assert "ACC_GUA_001" in solved.json()["blockers"]
    revision_id = solved.json()["scene"]["id"]

    unacknowledged = client.post(
        f"/v1/jobs/{job_id}/approve",
        headers={**_headers("tenant-a"), "Idempotency-Key": "approve-open-criterion"},
        json=_approval_payload(revision_id),
    )
    assert unacknowledged.status_code == 422
    assert "OPEN_CRITICAL_ISSUE:ACC_GUA_001" in unacknowledged.json()["errors"]

    foreign = client.post(
        f"/v1/jobs/{job_id}/approve",
        headers={**_headers("tenant-a"), "Idempotency-Key": "approve-foreign-criterion"},
        json=_approval_payload(revision_id, acknowledged_criteria=["NUMERIC_RESIDUAL"]),
    )
    assert foreign.status_code == 422
    assert foreign.json()["detail"]["code"] == "CRITERION_NOT_ACKNOWLEDGEABLE"

    payload = _approval_payload(revision_id, acknowledged_criteria=["ACC_GUA_001"])
    approved = client.post(
        f"/v1/jobs/{job_id}/approve",
        headers={**_headers("tenant-a"), "Idempotency-Key": "approve-acknowledged"},
        json=payload,
    )

    assert approved.status_code == 200
    body = approved.json()
    assert body["approved"] is True
    assert (
        next(issue for issue in body["issues"] if issue["code"] == "ACC_GUA_001")["status"]
        == "accepted"
    )
    retry = client.post(
        f"/v1/jobs/{job_id}/approve",
        headers={**_headers("tenant-a"), "Idempotency-Key": "approve-acknowledged"},
        json=payload,
    )
    assert retry.status_code == 200
    assert retry.json()["id"] == body["id"]
    assert _job_status(client, job_id) == "APPROVED"

    reapprove = client.post(
        f"/v1/jobs/{job_id}/approve",
        headers={**_headers("tenant-a"), "Idempotency-Key": "approve-again"},
        json=_approval_payload(body["id"], acknowledged_criteria=["ACC_GUA_001"]),
    )
    assert reapprove.status_code == 409


def test_approve_declares_a_criterion_covered_by_the_scene(tmp_path: Path) -> None:
    """Coberto pela cena é ato distinto de reconhecer pendência: a issue fecha `resolved`."""
    client = _client(tmp_path)
    job_id = _seed_review_session(client)
    solved = _confirm_solver_readings(client, job_id, base_version=1)
    revision_id = solved.json()["scene"]["id"]

    payload = _approval_payload(revision_id, covered_criteria=["ACC_GUA_001"])
    approved = client.post(
        f"/v1/jobs/{job_id}/approve",
        headers={**_headers("tenant-a"), "Idempotency-Key": "approve-covered"},
        json=payload,
    )

    assert approved.status_code == 200
    body = approved.json()
    assert (
        next(issue for issue in body["issues"] if issue["code"] == "ACC_GUA_001")["status"]
        == "resolved"
    )
    # Critério declarado deixa de ser bloqueio na revisão devolvida ao revisor.
    review = client.get(f"/v1/jobs/{job_id}/review", headers=_headers("tenant-a"))
    assert "ACC_GUA_001" not in review.json()["blockers"]

    replay = client.post(
        f"/v1/jobs/{job_id}/approve",
        headers={**_headers("tenant-a"), "Idempotency-Key": "approve-covered"},
        json=payload,
    )
    assert replay.status_code == 200
    assert replay.json()["id"] == body["id"]

    database = cast(Database, cast(Any, client.app).state.database)
    with database.sessions() as session:
        record = session.query(ApprovalRecord).filter_by(job_id=str(job_id)).one()
        assert record.approval_json is not None
        # Os dois conjuntos viajam separados no registro que vira o `aprovacao.json`.
        assert record.approval_json["covered_criteria"] == ["ACC_GUA_001"]
        assert record.approval_json["acknowledged_criteria"] == []


def test_approve_refuses_a_criterion_declared_covered_and_pending(tmp_path: Path) -> None:
    client = _client(tmp_path)
    job_id = _seed_review_session(client)
    solved = _confirm_solver_readings(client, job_id, base_version=1)
    revision_id = solved.json()["scene"]["id"]

    conflicting = client.post(
        f"/v1/jobs/{job_id}/approve",
        headers={**_headers("tenant-a"), "Idempotency-Key": "approve-conflict"},
        json=_approval_payload(
            revision_id,
            covered_criteria=["ACC_GUA_001"],
            acknowledged_criteria=["ACC_GUA_001"],
        ),
    )

    assert conflicting.status_code == 422
    assert conflicting.json()["detail"]["code"] == "CRITERION_DECLARATION_CONFLICT"

    foreign = client.post(
        f"/v1/jobs/{job_id}/approve",
        headers={**_headers("tenant-a"), "Idempotency-Key": "approve-covered-foreign"},
        json=_approval_payload(revision_id, covered_criteria=["MEASUREMENT_MISMATCH"]),
    )
    assert foreign.status_code == 422
    assert foreign.json()["detail"]["code"] == "CRITERION_NOT_ACKNOWLEDGEABLE"
    assert _job_status(client, job_id) != "APPROVED"


def test_review_of_a_legacy_row_without_criteria_texts_falls_back(tmp_path: Path) -> None:
    """Linha semeada antes da coluna de textos: a resposta e a issue caem na frase padrão."""
    client = _client(tmp_path)
    job_id = _seed_review_session(client)
    database = cast(Database, cast(Any, client.app).state.database)
    with database.sessions.begin() as session:
        review = session.query(ReviewRevisionRecord).filter_by(job_id=str(job_id)).one()
        review.required_criteria_texts_json = None

    review_response = client.get(f"/v1/jobs/{job_id}/review", headers=_headers("tenant-a"))
    assert review_response.status_code == 200
    assert review_response.json()["required_criteria"] == [
        {"code": "ACC_GUA_001", "text": FALLBACK_CRITERION_MESSAGE}
    ]

    solved = _confirm_solver_readings(client, job_id, base_version=1)
    assert solved.status_code == 200
    criterion = next(issue for issue in solved.json()["issues"] if issue["code"] == "ACC_GUA_001")
    assert criterion["message"] == FALLBACK_CRITERION_MESSAGE


def test_export_requires_an_approved_scene_and_returns_one_artifact(tmp_path: Path) -> None:
    client = _client(tmp_path)
    job_id = _seed_review_session(client)
    draft_id = client.get(f"/v1/jobs/{job_id}/review", headers=_headers("tenant-a")).json()[
        "scene"
    ]["id"]

    blocked = client.post(
        f"/v1/jobs/{job_id}/exports",
        headers={**_headers("tenant-a"), "Idempotency-Key": "export-not-approved"},
        json={"revision_id": draft_id},
    )
    assert blocked.status_code == 422
    assert blocked.json()["detail"]["code"] == "SCENE_NOT_APPROVED"

    approved = client.post(
        f"/v1/jobs/{job_id}/approve",
        headers={**_headers("tenant-a"), "Idempotency-Key": "export-approve"},
        json=_approval_payload(draft_id),
    )
    assert approved.status_code == 200
    approved_id = approved.json()["id"]

    first = client.post(
        f"/v1/jobs/{job_id}/exports",
        headers={**_headers("tenant-a"), "Idempotency-Key": "export-first"},
        json={"revision_id": approved_id},
    )
    second = client.post(
        f"/v1/jobs/{job_id}/exports",
        headers={**_headers("tenant-a"), "Idempotency-Key": "export-second"},
        json={"revision_id": approved_id},
    )

    assert first.status_code == 202
    assert second.status_code == 202
    assert first.json()["export_id"] == second.json()["export_id"]
    assert first.json()["status"] == "QUEUED"
    assert first.json()["package_url"] is None

    export_id = first.json()["export_id"]
    fetched = client.get(f"/v1/jobs/{job_id}/exports/{export_id}", headers=_headers("tenant-a"))
    assert fetched.status_code == 200
    assert fetched.json()["package_url"] is None
    assert (
        client.get(
            f"/v1/jobs/{job_id}/exports/{export_id}", headers=_headers("tenant-b")
        ).status_code
        == 404
    )


def test_completed_export_signs_only_the_tenant_package(tmp_path: Path) -> None:
    client = _client(tmp_path)
    job_id = _seed_review_session(client)
    draft_id = client.get(f"/v1/jobs/{job_id}/review", headers=_headers("tenant-a")).json()[
        "scene"
    ]["id"]
    approved_id = client.post(
        f"/v1/jobs/{job_id}/approve",
        headers={**_headers("tenant-a"), "Idempotency-Key": "signed-approve"},
        json=_approval_payload(draft_id),
    ).json()["id"]
    export_id = client.post(
        f"/v1/jobs/{job_id}/exports",
        headers={**_headers("tenant-a"), "Idempotency-Key": "signed-export"},
        json={"revision_id": approved_id},
    ).json()["export_id"]

    database = cast(Database, cast(Any, client.app).state.database)
    with database.sessions.begin() as session:
        artifact = session.get(ExportArtifactRecord, export_id)
        assert artifact is not None
        artifact.status = "COMPLETED"
        artifact.audit_status = "approved"
        artifact.dxf_sha256 = "f" * 64
        artifact.package_object_key = (
            f"tenants/tenant-a/jobs/{job_id}/exports/{export_id}/croquito.zip"
        )

    completed = client.get(f"/v1/jobs/{job_id}/exports/{export_id}", headers=_headers("tenant-a"))

    assert completed.status_code == 200
    assert completed.json()["status"] == "COMPLETED"
    assert completed.json()["package_url"].startswith("https://storage.invalid/tenants/tenant-a/")
    assert completed.json()["dxf_sha256"] == "f" * 64


def _confirmed_calibration(client: TestClient, job_id: UUID) -> dict[str, Any]:
    response = client.post(
        f"/v1/jobs/{job_id}/review/calibration",
        headers={**_headers("tenant-a"), "Idempotency-Key": f"calibration-{job_id}"},
        json={
            "base_review_version": 1,
            "base_scene_version": 1,
            "anchors": [
                {
                    "proposal_id": "vp_1111111111111111",
                    "entity_id": "00000000-0000-7000-8000-000000000401",
                },
                {
                    "proposal_id": "vp_2222222222222222",
                    "entity_id": "00000000-0000-7000-8000-000000000402",
                },
            ],
        },
    )
    assert response.status_code == 200
    return cast(dict[str, Any], response.json()["calibration"])


def test_batch_accept_traces_every_proposal_in_one_revision(tmp_path: Path) -> None:
    client = _client(tmp_path)
    job_id = _seed_review_session(client)
    before = client.get(f"/v1/jobs/{job_id}/review", headers=_headers("tenant-a")).json()
    calibration = _confirmed_calibration(client, job_id)

    accepted = client.post(
        f"/v1/jobs/{job_id}/review/proposals/batch",
        headers={**_headers("tenant-a"), "Idempotency-Key": "proposal-batch"},
        json={
            "base_review_version": 2,
            "base_scene_version": 1,
            "proposal_ids": ["vp_3333333333333333", "vp_4444444444444444"],
            "action": "accept",
            "justification": "Traçado do croqui aceito como geometria aproximada.",
            "calibration_id": calibration["calibration_id"],
        },
    )

    assert accepted.status_code == 200
    body = accepted.json()
    # Um lote, uma cena: duas entidades novas com um único incremento de versão.
    assert body["scene"]["version"] == before["scene"]["version"] + 1
    assert len(body["scene"]["entities"]) == len(before["scene"]["entities"]) + 2
    assert {decision["proposal_id"] for decision in body["proposal_decisions"]} == {
        "vp_3333333333333333",
        "vp_4444444444444444",
    }
    assert all(decision["entity_id"] for decision in body["proposal_decisions"])
    assert all(
        decision["calibration_id"] == calibration["calibration_id"]
        for decision in body["proposal_decisions"]
    )
    traced = body["scene"]["entities"][-2:]
    assert {entity["layer"] for entity in traced} == {"APROXIMADO"}
    assert {entity["precision"] for entity in traced} == {"approximate"}


def test_batch_refuses_when_one_proposal_was_already_decided(tmp_path: Path) -> None:
    client = _client(tmp_path)
    job_id = _seed_review_session(client)
    client.post(
        f"/v1/jobs/{job_id}/review/proposals",
        headers={**_headers("tenant-a"), "Idempotency-Key": "single-reject"},
        json={
            "base_review_version": 1,
            "base_scene_version": 1,
            "proposal_id": "vp_4444444444444444",
            "action": "reject",
            "justification": "Contorno é anotação.",
        },
    )

    refused = client.post(
        f"/v1/jobs/{job_id}/review/proposals/batch",
        headers={**_headers("tenant-a"), "Idempotency-Key": "batch-overlap"},
        json={
            "base_review_version": 2,
            "base_scene_version": 1,
            "proposal_ids": ["vp_3333333333333333", "vp_4444444444444444"],
            "action": "reject",
            "justification": "Traçado descartado.",
        },
    )

    # O lote inteiro é recusado: nenhuma decisão registrada pode ser sobrescrita.
    assert refused.status_code == 422
    assert refused.json()["detail"]["code"] == "PROPOSAL_ALREADY_DECIDED"
    review = client.get(f"/v1/jobs/{job_id}/review", headers=_headers("tenant-a")).json()
    assert len(review["proposal_decisions"]) == 1


def test_batch_accept_requires_the_current_calibration(tmp_path: Path) -> None:
    client = _client(tmp_path)
    job_id = _seed_review_session(client)

    refused = client.post(
        f"/v1/jobs/{job_id}/review/proposals/batch",
        headers={**_headers("tenant-a"), "Idempotency-Key": "batch-uncalibrated"},
        json={
            "base_review_version": 1,
            "base_scene_version": 1,
            "proposal_ids": ["vp_3333333333333333"],
            "action": "accept",
            "justification": "Sem calibração confirmada.",
        },
    )

    assert refused.status_code == 422
    assert refused.json()["detail"]["code"] == "CALIBRATION_REQUIRED"


def test_dimension_annotation_makes_the_written_value_win_over_pixels(tmp_path: Path) -> None:
    client = _client(tmp_path)
    job_id = _seed_review_session(client)
    confirmed = client.post(
        f"/v1/jobs/{job_id}/review/decisions",
        headers={**_headers("tenant-a"), "Idempotency-Key": "confirm-for-dimension"},
        json={
            "base_version": 1,
            "decisions": [
                {
                    "reading_id": "rd_1111111111111111",
                    "action": "confirm",
                    "justification": "Cota conferida na evidência.",
                    "association_proposal_id": "vp_1111111111111111",
                }
            ],
        },
    )
    assert confirmed.status_code == 200
    calibration_response = client.post(
        f"/v1/jobs/{job_id}/review/calibration",
        headers={**_headers("tenant-a"), "Idempotency-Key": "calibration-for-dimension"},
        json={
            "base_review_version": confirmed.json()["version"],
            "base_scene_version": confirmed.json()["scene"]["version"],
            "anchors": [
                {"proposal_id": "vp_1111111111111111"},
                {"proposal_id": "vp_2222222222222222"},
            ],
        },
    )
    assert calibration_response.status_code == 200
    calibrated = calibration_response.json()
    calibration = calibrated["calibration"]
    traced = client.post(
        f"/v1/jobs/{job_id}/review/proposals/batch",
        headers={**_headers("tenant-a"), "Idempotency-Key": "batch-for-dimension"},
        json={
            "base_review_version": calibrated["version"],
            "base_scene_version": calibrated["scene"]["version"],
            "proposal_ids": ["vp_1111111111111111"],
            "action": "accept",
            "justification": "Linha do muro traçada.",
            "calibration_id": calibration["calibration_id"],
        },
    )
    assert traced.status_code == 200
    body = traced.json()
    traced_entity = body["scene"]["entities"][-1]
    assert traced_entity["layer"] == "APROXIMADO"

    annotated = client.post(
        f"/v1/jobs/{job_id}/review/dimensions",
        headers={**_headers("tenant-a"), "Idempotency-Key": "dimension-1"},
        json={
            "base_review_version": body["version"],
            "base_scene_version": body["scene"]["version"],
            "reading_id": "rd_1111111111111111",
            "entity_id": traced_entity["id"],
            "justification": "A linha traçada é a cota de largura confirmada.",
        },
    )

    assert annotated.status_code == 200
    scene = annotated.json()["scene"]
    adjusted = next(item for item in scene["entities"] if item["id"] == traced_entity["id"])
    length = math.hypot(
        adjusted["geometry"]["end"]["x"] - adjusted["geometry"]["start"]["x"],
        adjusted["geometry"]["end"]["y"] - adjusted["geometry"]["start"]["y"],
    )
    # A cota escrita prevalece sobre o comprimento vindo de pixels.
    assert length == pytest.approx(25.9)
    dimension = next(item for item in scene["entities"] if item["kind"] == "dimension")
    assert dimension["layer"] == "COTAS"
    assert scene["measurements"][-1]["confirmed"] is True

    # Uma leitura que já virou cota no desenho não pode ser amarrada de novo — o guard
    # cobre DIMENSION, DIAMETER_DIMENSION e TEXT pela provenance da entidade.
    repeated = client.post(
        f"/v1/jobs/{job_id}/review/dimensions",
        headers={**_headers("tenant-a"), "Idempotency-Key": "dimension-2"},
        json={
            "base_review_version": annotated.json()["version"],
            "base_scene_version": scene["version"],
            "reading_id": "rd_1111111111111111",
            "entity_id": traced_entity["id"],
            "justification": "Tentativa repetida da mesma amarração.",
        },
    )
    assert repeated.status_code == 422
    assert "já está no desenho" in repeated.json()["detail"]["detail"]


def test_dimension_annotation_refuses_an_unconfirmed_reading(tmp_path: Path) -> None:
    client = _client(tmp_path)
    job_id = _seed_review_session(client)
    review = client.get(f"/v1/jobs/{job_id}/review", headers=_headers("tenant-a")).json()
    pending = next(item for item in review["packet"]["readings"] if item["status"] != "confirmed")

    refused = client.post(
        f"/v1/jobs/{job_id}/review/dimensions",
        headers={**_headers("tenant-a"), "Idempotency-Key": "dimension-unconfirmed"},
        json={
            "base_review_version": review["version"],
            "base_scene_version": review["scene"]["version"],
            "reading_id": pending["id"],
            "entity_id": review["scene"]["entities"][0]["id"],
            "justification": "Tentativa sem confirmação.",
        },
    )

    assert refused.status_code == 422
    assert refused.json()["detail"]["code"] == "DOMAIN_VALIDATION_FAILED"


def test_rejected_proposal_is_recorded_without_touching_the_scene(tmp_path: Path) -> None:
    client = _client(tmp_path)
    job_id = _seed_review_session(client)
    before = client.get(f"/v1/jobs/{job_id}/review", headers=_headers("tenant-a")).json()

    rejected = client.post(
        f"/v1/jobs/{job_id}/review/proposals",
        headers={**_headers("tenant-a"), "Idempotency-Key": "proposal-reject"},
        json={
            "base_review_version": 1,
            "base_scene_version": 1,
            "proposal_id": "vp_4444444444444444",
            "action": "reject",
            "justification": "Contorno é anotação, não geometria do campo.",
        },
    )

    assert rejected.status_code == 200
    body = rejected.json()
    decision = body["proposal_decisions"][-1]
    assert decision["action"] == "reject"
    assert decision["entity_id"] is None
    assert "justification" not in decision
    assert body["scene"]["version"] == before["scene"]["version"]
    assert len(body["scene"]["entities"]) == len(before["scene"]["entities"])

    database = cast(Database, cast(Any, client.app).state.database)
    with database.sessions() as session:
        record = (
            session.query(ProposalDecisionRecord).filter_by(proposal_id="vp_4444444444444444").one()
        )
        assert record.action == "reject"
        assert record.scene_revision_id is None


def _observed_queue(client: TestClient) -> FakeQueue:
    """Substitui apenas o transporte: o envelope publicado continua sendo o de produção."""
    queue = FakeQueue()
    processing_queue = cast(Any, client.app).state.queue
    processing_queue.queue_url = "http://localstack/queue"
    processing_queue.client = queue
    return queue


def _published_commands(queue: FakeQueue) -> list[str]:
    """Comandos publicados e ainda não consumidos; aqui não há worker para entregá-los."""
    return [str(json.loads(message["Body"])["command"]) for message in queue.messages]


def _trace_payload(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "base_review_version": 1,
        "base_scene_version": 1,
        "proposal_ids": ["vp_1111111111111111", "vp_2222222222222222", "vp_3333333333333333"],
        "unlabelled_proposal_ids": ["vp_3333333333333333"],
        "associations": {
            "rd_1111111111111111": "vp_1111111111111111",
            "rd_2222222222222222": "vp_2222222222222222",
        },
        "note": "Traçado conferido contra a evidência protegida.",
        "title": "CAMPO SINTETICO",
    }
    payload.update(overrides)
    return payload


def test_trace_solve_is_queued_with_the_identity_taken_from_the_jwt(tmp_path: Path) -> None:
    client = _client(tmp_path)
    job_id = _seed_review_session(client)
    queue = _observed_queue(client)

    requested = client.post(
        f"/v1/jobs/{job_id}/trace-solves",
        headers={**_headers("tenant-a"), "Idempotency-Key": "trace-first"},
        json=_trace_payload(),
    )

    assert requested.status_code == 202
    body = requested.json()
    assert body["status"] == "QUEUED"
    assert body["solve_status"] is None
    assert re.fullmatch(r"ta_[a-f0-9]{16}", body["acceptance_id"])
    assert body["base_review_version"] == 1
    assert body["base_scene_version"] == 1
    # A API só enfileira: a geometria nunca é resolvida no request path.
    assert _published_commands(queue) == ["solve_trace_scene"]
    envelope = json.loads(queue.messages[0]["Body"])
    assert envelope["trace_solve_id"] == body["trace_solve_id"]
    assert envelope["tenant_id"] == "tenant-a"

    database = cast(Database, cast(Any, client.app).state.database)
    with database.sessions() as session:
        record = session.get(TraceSolveRecord, body["trace_solve_id"])
        assert record is not None
        assert record.status == "QUEUED"
        assert record.tenant_id == "tenant-a"
        # Identidade, papel e horário vêm do JWT e do relógio do servidor.
        assert record.acceptance_json["reviewer_id"] == "reviewer"
        assert record.acceptance_json["reviewer_role"] == "engineer"
        assert record.acceptance_json["decided_at"] is not None
        assert record.requested_by == "reviewer"


def test_trace_solve_inherits_the_confirmed_associations_and_lets_the_body_win(
    tmp_path: Path,
) -> None:
    client = _client(tmp_path)
    job_id = _seed_review_session(client)
    _observed_queue(client)
    confirmed = _confirm_solver_readings(client, job_id, base_version=1)
    assert confirmed.status_code == 200

    requested = client.post(
        f"/v1/jobs/{job_id}/trace-solves",
        headers={**_headers("tenant-a"), "Idempotency-Key": "trace-overlay"},
        json=_trace_payload(
            base_review_version=confirmed.json()["version"],
            base_scene_version=confirmed.json()["scene"]["version"],
            proposal_ids=[
                "vp_1111111111111111",
                "vp_2222222222222222",
                "vp_3333333333333333",
                "vp_4444444444444444",
            ],
            associations={"rd_1111111111111111": "vp_4444444444444444"},
        ),
    )

    assert requested.status_code == 202
    database = cast(Database, cast(Any, client.app).state.database)
    with database.sessions() as session:
        record = session.get(TraceSolveRecord, requested.json()["trace_solve_id"])
        assert record is not None
        # O corpo vence por leitura; as demais associações confirmadas continuam valendo.
        assert record.associations_json["rd_1111111111111111"] == "vp_4444444444444444"
        assert record.associations_json["rd_2222222222222222"] == "vp_2222222222222222"
        assert record.associations_json["rd_3333333333333333"] == "vp_3333333333333333"


def test_trace_solve_keeps_the_three_association_formats(tmp_path: Path) -> None:
    client = _client(tmp_path)
    job_id = _seed_review_session(client)
    _observed_queue(client)

    requested = client.post(
        f"/v1/jobs/{job_id}/trace-solves",
        headers={**_headers("tenant-a"), "Idempotency-Key": "trace-formats"},
        json=_trace_payload(
            proposal_ids=[
                "vp_1111111111111111",
                "vp_2222222222222222",
                "vp_3333333333333333",
                "vp_4444444444444444",
            ],
            associations={
                "rd_1111111111111111": "vp_1111111111111111",
                "rd_2222222222222222": ["vp_1111111111111111", "vp_2222222222222222"],
                "rd_3333333333333333": {
                    "proposal_id": "vp_4444444444444444",
                    "spans_px": [[[10, 10], [30, 10]]],
                },
            },
        ),
    )

    assert requested.status_code == 202
    database = cast(Database, cast(Any, client.app).state.database)
    with database.sessions() as session:
        record = session.get(TraceSolveRecord, requested.json()["trace_solve_id"])
        assert record is not None
        stored = record.associations_json
        # O solver só reconhece o formato objeto com exatamente estas duas chaves.
        assert stored["rd_1111111111111111"] == "vp_1111111111111111"
        assert stored["rd_2222222222222222"] == ["vp_1111111111111111", "vp_2222222222222222"]
        assert stored["rd_3333333333333333"] == {
            "proposal_id": "vp_4444444444444444",
            "spans_px": [[[10.0, 10.0], [30.0, 10.0]]],
        }


def test_trace_solve_keeps_both_keep_apart_formats(tmp_path: Path) -> None:
    """O par simples e o par com eixo chegam ao aceite como foram declarados.

    O eixo é do revisor, não da API: quem separa mureta e patamar só na horizontal precisa
    que o `x` sobreviva ao request path, e as duas formas citam propostas do snapshot.
    """
    client = _client(tmp_path)
    job_id = _seed_review_session(client)
    _observed_queue(client)

    requested = client.post(
        f"/v1/jobs/{job_id}/trace-solves",
        headers={**_headers("tenant-a"), "Idempotency-Key": "trace-keep-apart"},
        json=_trace_payload(
            keep_apart_pairs=[
                ["vp_1111111111111111", "vp_2222222222222222"],
                {
                    "first": "vp_1111111111111111",
                    "second": "vp_3333333333333333",
                    "axis": "x",
                },
            ]
        ),
    )

    assert requested.status_code == 202
    database = cast(Database, cast(Any, client.app).state.database)
    with database.sessions() as session:
        record = session.get(TraceSolveRecord, requested.json()["trace_solve_id"])
        assert record is not None
        assert record.acceptance_json["keep_apart_pairs"] == [
            ["vp_1111111111111111", "vp_2222222222222222"],
            {"first": "vp_1111111111111111", "second": "vp_3333333333333333", "axis": "x"},
        ]


def test_trace_solve_refuses_a_keep_apart_proposal_outside_the_snapshot(tmp_path: Path) -> None:
    """A forma objeto passa pela mesma checagem de proposta conhecida que o par simples."""
    client = _client(tmp_path)
    job_id = _seed_review_session(client)

    refused = client.post(
        f"/v1/jobs/{job_id}/trace-solves",
        headers={**_headers("tenant-a"), "Idempotency-Key": "trace-keep-apart-unknown"},
        json=_trace_payload(
            keep_apart_pairs=[{"first": "vp_1111111111111111", "second": "vp_9999999999999999"}]
        ),
    )

    assert refused.status_code == 422
    assert refused.json()["detail"]["code"] == "TRACE_PROPOSAL_UNKNOWN"


def test_trace_solve_refuses_a_stale_base_version(tmp_path: Path) -> None:
    client = _client(tmp_path)
    job_id = _seed_review_session(client)

    refused = client.post(
        f"/v1/jobs/{job_id}/trace-solves",
        headers={**_headers("tenant-a"), "Idempotency-Key": "trace-stale"},
        json=_trace_payload(base_review_version=2),
    )

    assert refused.status_code == 409
    assert refused.json()["detail"]["code"] == "REVISION_CONFLICT"


def test_trace_solve_refuses_a_proposal_outside_the_snapshot(tmp_path: Path) -> None:
    client = _client(tmp_path)
    job_id = _seed_review_session(client)

    refused = client.post(
        f"/v1/jobs/{job_id}/trace-solves",
        headers={**_headers("tenant-a"), "Idempotency-Key": "trace-unknown"},
        json=_trace_payload(proposal_ids=["vp_1111111111111111", "vp_9999999999999999"]),
    )

    assert refused.status_code == 422
    assert refused.json()["detail"]["code"] == "TRACE_PROPOSAL_UNKNOWN"


def test_trace_solve_refuses_an_inconsistent_acceptance(tmp_path: Path) -> None:
    client = _client(tmp_path)
    job_id = _seed_review_session(client)

    refused = client.post(
        f"/v1/jobs/{job_id}/trace-solves",
        headers={**_headers("tenant-a"), "Idempotency-Key": "trace-inconsistent"},
        json=_trace_payload(
            proposal_ids=["vp_1111111111111111"],
            unlabelled_proposal_ids=[],
            associations={},
            detail_groups=[
                {
                    "detail_id": "A",
                    "title": "Painel de alambrado",
                    "proposal_ids": ["vp_2222222222222222"],
                }
            ],
        ),
    )

    assert refused.status_code == 422
    problem = refused.json()
    assert problem["detail"]["code"] == "TRACE_ACCEPTANCE_INVALID"
    # A mensagem de domínio do contrato do traçado chega ao cliente sem os valores.
    assert problem["detail"]["detail"] == "grupo de detalhe só pode conter proposta aceita"


def test_trace_solve_polling_exposes_the_result_and_isolates_the_tenant(tmp_path: Path) -> None:
    client = _client(tmp_path)
    job_id = _seed_review_session(client)
    _observed_queue(client)
    trace_solve_id = client.post(
        f"/v1/jobs/{job_id}/trace-solves",
        headers={**_headers("tenant-a"), "Idempotency-Key": "trace-poll"},
        json=_trace_payload(),
    ).json()["trace_solve_id"]

    queued = client.get(
        f"/v1/jobs/{job_id}/trace-solves/{trace_solve_id}", headers=_headers("tenant-a")
    )
    assert queued.status_code == 200
    assert queued.json()["status"] == "QUEUED"
    assert queued.json()["blockers"] == []

    database = cast(Database, cast(Any, client.app).state.database)
    with database.sessions.begin() as session:
        record = session.get(TraceSolveRecord, trace_solve_id)
        assert record is not None
        record.status = "COMPLETED"
        record.solve_status = "review_required"
        record.blockers_json = ["TRACE_HUMAN_CONFIRMATION_REQUIRED:rd_1111111111111111"]
        record.unapplied_reading_ids_json = ["rd_3333333333333333"]
        record.unapplied_readings_json = [
            {
                "reading_id": "rd_3333333333333333",
                "cause": "TRACE_SPAN_AXIS_UNDECLARED",
                "target_proposal_ids": ["vp_1111111111111111"],
            }
        ]
        record.contested_spans_json = [
            {
                "axis": "x",
                "reading_ids": ["rd_1111111111111111", "rd_2222222222222222"],
                "values_m": [5.0, 8.0],
                "proposal_ids": ["vp_1111111111111111"],
            }
        ]
        record.applied_spans_json = [
            {
                "reading_id": "rd_1111111111111111",
                "axis": "x",
                "value_m": 5.0,
                "start_m": 0.0,
                "end_m": 5.0,
                "proposal_id": "vp_1111111111111111",
                "second_proposal_id": None,
                "gap": False,
            }
        ]
        record.residual_summary_json = {
            "count": 2,
            "failed_count": 1,
            "worst_code": "NUMERIC_RESIDUAL",
            "worst_absolute_error_m": 0.4,
            "worst_tolerance_m": 0.05,
        }

    completed = client.get(
        f"/v1/jobs/{job_id}/trace-solves/{trace_solve_id}", headers=_headers("tenant-a")
    )
    assert completed.status_code == 200
    body = completed.json()
    assert body["solve_status"] == "review_required"
    # Blockers do domínio chegam ao cliente como códigos estáveis.
    assert body["blockers"] == ["TRACE_HUMAN_CONFIRMATION_REQUIRED:rd_1111111111111111"]
    assert body["unapplied_reading_ids"] == ["rd_3333333333333333"]
    # O diagnóstico é aditivo: a lista de ids acima continua igual, e ao lado dela vem a
    # causa por leitura, o vão em disputa e a âncora da cota aplicada.
    assert body["unapplied_readings"] == [
        {
            "reading_id": "rd_3333333333333333",
            "cause": "TRACE_SPAN_AXIS_UNDECLARED",
            "target_proposal_ids": ["vp_1111111111111111"],
        }
    ]
    assert body["contested_spans"][0]["reading_ids"] == [
        "rd_1111111111111111",
        "rd_2222222222222222",
    ]
    assert body["contested_spans"][0]["values_m"] == [5.0, 8.0]
    assert body["applied_spans"][0]["end_m"] == 5.0
    assert body["residual_summary"]["failed_count"] == 1

    assert (
        client.get(
            f"/v1/jobs/{job_id}/trace-solves/{trace_solve_id}", headers=_headers("tenant-b")
        ).status_code
        == 404
    )


def test_trace_solve_repeats_the_idempotent_response(tmp_path: Path) -> None:
    client = _client(tmp_path)
    job_id = _seed_review_session(client)
    queue = _observed_queue(client)
    headers = {**_headers("tenant-a"), "Idempotency-Key": "trace-repeat"}

    first = client.post(f"/v1/jobs/{job_id}/trace-solves", headers=headers, json=_trace_payload())
    second = client.post(f"/v1/jobs/{job_id}/trace-solves", headers=headers, json=_trace_payload())

    assert first.status_code == 202
    assert second.status_code == 202
    assert first.json()["trace_solve_id"] == second.json()["trace_solve_id"]
    assert _published_commands(queue) == ["solve_trace_scene"]
    database = cast(Database, cast(Any, client.app).state.database)
    with database.sessions() as session:
        assert session.query(TraceSolveRecord).count() == 1


def _open_chat_session(client: TestClient, job_id: UUID, *, key: str = "chat-open") -> str:
    response = client.post(
        f"/v1/jobs/{job_id}/chat-sessions",
        headers={**_headers("tenant-a"), "Idempotency-Key": key},
        json={},
    )
    assert response.status_code == 201, response.text
    return cast(str, response.json()["chat_session_id"])


def _turn_payload(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "question": "Essa cota mede a borda do campo ou a mureta?",
        "anchors": {
            "reading_ids": ["rd_1111111111111111"],
            "proposal_ids": ["vp_1111111111111111"],
        },
    }
    payload.update(overrides)
    return payload


def test_chat_session_pins_the_current_review_and_audits_only_ids(tmp_path: Path) -> None:
    client = _client(tmp_path)
    job_id = _seed_review_session(client)

    response = client.post(
        f"/v1/jobs/{job_id}/chat-sessions",
        headers={**_headers("tenant-a"), "Idempotency-Key": "chat-open"},
        json={},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "OPEN"
    assert body["base_review_version"] == 1
    assert body["turns"] == []
    database = cast(Database, cast(Any, client.app).state.database)
    with database.sessions() as session:
        record = session.get(ChatSessionRecord, body["chat_session_id"])
        assert record is not None
        assert record.tenant_id == "tenant-a"
        assert record.base_review_revision_id == "00000000-0000-7000-8000-000000000302"
        assert record.created_by == "reviewer"
        audit = session.scalar(
            select(AuditRecord).where(AuditRecord.action == "CHAT_SESSION_OPENED")
        )
        assert audit is not None
        # Auditoria só com ids: nem pergunta nem resposta chegam perto dela.
        assert audit.metadata_json.keys() == {"request_id"}


def test_chat_session_requires_a_professional_role_and_isolates_the_tenant(
    tmp_path: Path,
) -> None:
    client = _client(tmp_path)
    job_id = _seed_review_session(client)

    forbidden = client.post(
        f"/v1/jobs/{job_id}/chat-sessions",
        headers={
            **_headers("tenant-a", roles="viewer"),
            "Idempotency-Key": "chat-role",
        },
        json={},
    )
    other_tenant = client.post(
        f"/v1/jobs/{job_id}/chat-sessions",
        headers={**_headers("tenant-b"), "Idempotency-Key": "chat-tenant"},
        json={},
    )

    assert forbidden.status_code == 403
    assert forbidden.json()["detail"]["code"] == "FORBIDDEN"
    assert other_tenant.status_code == 404


def test_chat_session_without_a_review_is_not_ready(tmp_path: Path) -> None:
    client = _client(tmp_path)
    upload = _presign_and_put(client)
    job_id = client.post(
        "/v1/jobs",
        headers={**_headers("tenant-a"), "Idempotency-Key": "chat-job"},
        json={"upload_id": upload["upload_id"], "project_name": "Sem revisão"},
    ).json()["job_id"]

    response = client.post(
        f"/v1/jobs/{job_id}/chat-sessions",
        headers={**_headers("tenant-a"), "Idempotency-Key": "chat-not-ready"},
        json={},
    )

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "JOB_NOT_READY"


def test_chat_session_repeats_the_idempotent_response(tmp_path: Path) -> None:
    client = _client(tmp_path)
    job_id = _seed_review_session(client)
    headers = {**_headers("tenant-a"), "Idempotency-Key": "chat-repeat"}

    first = client.post(f"/v1/jobs/{job_id}/chat-sessions", headers=headers, json={})
    second = client.post(f"/v1/jobs/{job_id}/chat-sessions", headers=headers, json={})

    assert first.status_code == 201
    assert first.json()["chat_session_id"] == second.json()["chat_session_id"]
    database = cast(Database, cast(Any, client.app).state.database)
    with database.sessions() as session:
        assert session.query(ChatSessionRecord).count() == 1


def test_chat_turn_is_queued_and_never_calls_a_model_in_the_request(tmp_path: Path) -> None:
    client = _client(tmp_path)
    job_id = _seed_review_session(client)
    session_id = _open_chat_session(client, job_id)
    queue = _observed_queue(client)

    response = client.post(
        f"/v1/jobs/{job_id}/chat-sessions/{session_id}/turns",
        headers={**_headers("tenant-a"), "Idempotency-Key": "chat-turn-1"},
        json=_turn_payload(),
    )

    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "QUEUED"
    assert body["sequence"] == 1
    assert body["answer"] is None
    assert _published_commands(queue) == ["answer_chat_turn"]
    envelope = json.loads(queue.messages[0]["Body"])
    assert envelope["chat_turn_id"] == body["chat_turn_id"]
    assert envelope["job_id"] == str(job_id)
    assert envelope["tenant_id"] == "tenant-a"
    # A pergunta fica no banco e não viaja na fila.
    assert "question" not in envelope
    database = cast(Database, cast(Any, client.app).state.database)
    with database.sessions() as session:
        record = session.get(ChatTurnRecord, body["chat_turn_id"])
        assert record is not None
        assert record.status == "QUEUED"
        assert record.question_text == _turn_payload()["question"]
        assert record.requested_by == "reviewer"
        audit = session.scalar(
            select(AuditRecord).where(AuditRecord.action == "CHAT_TURN_REQUESTED")
        )
        assert audit is not None
        assert audit.metadata_json.keys() == {"request_id"}


def test_chat_turn_allows_only_one_pending_question_per_session(tmp_path: Path) -> None:
    client = _client(tmp_path)
    job_id = _seed_review_session(client)
    session_id = _open_chat_session(client, job_id)
    _observed_queue(client)
    first = client.post(
        f"/v1/jobs/{job_id}/chat-sessions/{session_id}/turns",
        headers={**_headers("tenant-a"), "Idempotency-Key": "chat-turn-1"},
        json=_turn_payload(),
    )
    assert first.status_code == 202

    second = client.post(
        f"/v1/jobs/{job_id}/chat-sessions/{session_id}/turns",
        headers={**_headers("tenant-a"), "Idempotency-Key": "chat-turn-2"},
        json=_turn_payload(question="E a mureta, tem cota?"),
    )

    assert second.status_code == 409
    assert second.json()["detail"]["code"] == "CHAT_TURN_PENDING"

    database = cast(Database, cast(Any, client.app).state.database)
    with database.sessions.begin() as session:
        record = session.get(ChatTurnRecord, first.json()["chat_turn_id"])
        assert record is not None
        record.status = "COMPLETED"
    # Respondida a anterior, a próxima pergunta entra com a sequência seguinte.
    third = client.post(
        f"/v1/jobs/{job_id}/chat-sessions/{session_id}/turns",
        headers={**_headers("tenant-a"), "Idempotency-Key": "chat-turn-3"},
        json=_turn_payload(question="E a mureta, tem cota?"),
    )
    assert third.status_code == 202
    assert third.json()["sequence"] == 2


def test_chat_turn_refuses_an_anchor_outside_the_base_revision(tmp_path: Path) -> None:
    client = _client(tmp_path)
    job_id = _seed_review_session(client)
    session_id = _open_chat_session(client, job_id)
    _observed_queue(client)

    response = client.post(
        f"/v1/jobs/{job_id}/chat-sessions/{session_id}/turns",
        headers={**_headers("tenant-a"), "Idempotency-Key": "chat-anchor"},
        json=_turn_payload(
            anchors={
                "reading_ids": ["rd_9999999999999999"],
                "proposal_ids": ["vp_1111111111111111"],
            }
        ),
    )

    assert response.status_code == 422
    problem = response.json()
    assert problem["detail"]["code"] == "CHAT_ANCHOR_UNKNOWN"
    database = cast(Database, cast(Any, client.app).state.database)
    with database.sessions() as session:
        assert session.query(ChatTurnRecord).count() == 0


def test_chat_turn_refuses_a_closed_session_and_another_tenant(tmp_path: Path) -> None:
    client = _client(tmp_path)
    job_id = _seed_review_session(client)
    session_id = _open_chat_session(client, job_id)
    _observed_queue(client)
    database = cast(Database, cast(Any, client.app).state.database)
    with database.sessions.begin() as session:
        record = session.get(ChatSessionRecord, session_id)
        assert record is not None
        record.status = "CLOSED"

    closed = client.post(
        f"/v1/jobs/{job_id}/chat-sessions/{session_id}/turns",
        headers={**_headers("tenant-a"), "Idempotency-Key": "chat-closed"},
        json=_turn_payload(),
    )
    other_tenant = client.post(
        f"/v1/jobs/{job_id}/chat-sessions/{session_id}/turns",
        headers={**_headers("tenant-b"), "Idempotency-Key": "chat-closed-b"},
        json=_turn_payload(),
    )

    assert closed.status_code == 409
    assert closed.json()["detail"]["code"] == "CHAT_SESSION_CLOSED"
    assert other_tenant.status_code == 404


def test_chat_turn_keeps_the_row_queued_when_the_queue_refuses(tmp_path: Path) -> None:
    client = _client(tmp_path)
    job_id = _seed_review_session(client)
    session_id = _open_chat_session(client, job_id)

    class RefusingQueue:
        def send_message(self, **_kwargs: Any) -> None:
            raise BotoCoreError()

    processing_queue = cast(Any, client.app).state.queue
    processing_queue.queue_url = "http://localstack/queue"
    processing_queue.client = RefusingQueue()

    response = client.post(
        f"/v1/jobs/{job_id}/chat-sessions/{session_id}/turns",
        headers={**_headers("tenant-a"), "Idempotency-Key": "chat-queue-down"},
        json=_turn_payload(),
    )

    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "PROCESSING_UNAVAILABLE"
    database = cast(Database, cast(Any, client.app).state.database)
    with database.sessions() as session:
        record = session.scalar(select(ChatTurnRecord))
        # A intenção é durável antes da fila: uma nova chamada reenfileira.
        assert record is not None
        assert record.status == "QUEUED"


def test_chat_polling_returns_the_answer_and_the_list_stays_lean(tmp_path: Path) -> None:
    client = _client(tmp_path)
    job_id = _seed_review_session(client)
    session_id = _open_chat_session(client, job_id)
    _observed_queue(client)
    turn_id = client.post(
        f"/v1/jobs/{job_id}/chat-sessions/{session_id}/turns",
        headers={**_headers("tenant-a"), "Idempotency-Key": "chat-poll"},
        json=_turn_payload(),
    ).json()["chat_turn_id"]

    queued = client.get(
        f"/v1/jobs/{job_id}/chat-sessions/{session_id}", headers=_headers("tenant-a")
    )
    assert queued.status_code == 200
    assert queued.json()["turns"][0]["status"] == "QUEUED"

    database = cast(Database, cast(Any, client.app).state.database)
    with database.sessions.begin() as session:
        record = session.get(ChatTurnRecord, turn_id)
        assert record is not None
        record.status = "COMPLETED"
        record.answer_json = {
            "task": "review-chat",
            "answer_kind": "answer",
            "answer_text": "A cota está escrita ao lado do elemento apontado.",
            "evidence_notes": [],
            "open_question": None,
            "proposed_acts": [
                {
                    "act": "reading_decision",
                    "reading_id": "rd_1111111111111111",
                    "action": "confirm",
                    "association_proposal_id": "vp_1111111111111111",
                    "annotation": False,
                    "justification_draft": "Cota conferida contra o recorte da evidência.",
                }
            ],
        }

    completed = client.get(
        f"/v1/jobs/{job_id}/chat-sessions/{session_id}", headers=_headers("tenant-a")
    )
    assert completed.status_code == 200
    turn = completed.json()["turns"][0]
    assert turn["status"] == "COMPLETED"
    assert turn["answer"]["proposed_acts"][0]["reading_id"] == "rd_1111111111111111"

    listed = client.get(f"/v1/jobs/{job_id}/chat-sessions", headers=_headers("tenant-a"))
    assert listed.status_code == 200
    assert listed.json() == [
        {
            "chat_session_id": session_id,
            "status": "OPEN",
            "created_at": completed.json()["created_at"],
            "turn_count": 1,
        }
    ]
    # Conversa de outro tenant não existe para quem pergunta.
    assert (
        client.get(
            f"/v1/jobs/{job_id}/chat-sessions/{session_id}", headers=_headers("tenant-b")
        ).status_code
        == 404
    )
    assert (
        client.get(f"/v1/jobs/{job_id}/chat-sessions", headers=_headers("tenant-b")).status_code
        == 404
    )
