"""Contrato de vínculo e leitura da evidência de campo da F-030 (T1)."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast
from uuid import UUID

from fastapi.testclient import TestClient
from sqlalchemy import select

from croquito_api.config import ApiSettings
from croquito_api.database import (
    AiProcessingAuthorizationRecord,
    AuditRecord,
    Database,
    FieldEvidenceAnalysisRecord,
    FieldPhotoValueConfirmationRecord,
    IdempotencyRecord,
    JobFieldPhotoRecord,
    JobRecord,
    JobSurveyLinkRecord,
    ProjectRecord,
    SurveyMediaRecord,
    SurveyRecord,
    TenantAiProcessingEntitlementRecord,
    UploadRecord,
)
from croquito_api.main import create_app
from tests.fakes import FakeObjectStore, FakeQueue

TENANT = "tenant-field-evidence"
OTHER_TENANT = "tenant-other"
JOB_ID = UUID("00000000-0000-7000-8000-000000000901")
OTHER_JOB_ID = UUID("00000000-0000-7000-8000-000000000902")
SURVEY_ID = "survey-completed-a"
OTHER_SURVEY_ID = "survey-completed-b"
PHOTO = b"field evidence synthetic jpeg"
PHOTO_SHA256 = hashlib.sha256(PHOTO).hexdigest()
NOW = datetime(2026, 8, 23, 12, 0, tzinfo=UTC)


def _headers(
    *, tenant: str = TENANT, roles: str = "engineer", key: str = "field-evidence-1"
) -> dict[str, str]:
    return {
        "Authorization": f"Bearer test:{tenant}:reviewer:{roles}",
        "Idempotency-Key": key,
    }


def _packet(survey_id: str, *, with_photo: bool = False) -> dict[str, Any]:
    return {
        "survey_id": survey_id,
        "name": f"Levantamento {survey_id}",
        "order_id": f"order-{survey_id}",
        "device_id": "device-field",
        "created_at": NOW.isoformat(),
        "updated_at": NOW.isoformat(),
        "points": [
            {"id": "p1", "x_mm": 0, "y_mm": 0, "created_at": NOW.isoformat()},
            {"id": "p2", "x_mm": 2450, "y_mm": 0, "created_at": NOW.isoformat()},
        ],
        "segments": [],
        "measurements": [
            {
                "id": "measurement-confirmed",
                "value_mm": 2450,
                "kind": "length",
                "from_point_id": "p1",
                "to_point_id": "p2",
                "second_from_point_id": None,
                "second_to_point_id": None,
                "element_id": None,
                "instrument": "trena laser",
                "status": "confirmed",
                "justification": None,
                "created_at": NOW.isoformat(),
            },
            {
                "id": "measurement-draft",
                "value_mm": 2400,
                "kind": "length",
                "from_point_id": "p1",
                "to_point_id": "p2",
                "second_from_point_id": None,
                "second_to_point_id": None,
                "element_id": None,
                "instrument": "trena manual",
                "status": "draft",
                "justification": None,
                "created_at": NOW.isoformat(),
            },
        ],
        "media_anchors": (
            [
                {
                    "id": "anchor-photo",
                    "media_ref": {
                        "sha256": PHOTO_SHA256,
                        "mime_type": "image/jpeg",
                        "byte_size": len(PHOTO),
                    },
                    "point_id": "p1",
                    "element_id": None,
                    "note_id": None,
                    "created_at": NOW.isoformat(),
                }
            ]
            if with_photo
            else []
        ),
        "elements": [],
        "observations": [],
        "gps_fixes": [],
        "arrival_context": None,
        "status": "concluded",
        "waivers": [],
        "operations": [],
    }


def _seed(database: Database, store: FakeObjectStore) -> None:
    with database.sessions.begin() as session:
        for tenant, suffix, job_id in (
            (TENANT, "a", JOB_ID),
            (OTHER_TENANT, "b", OTHER_JOB_ID),
        ):
            session.add(
                ProjectRecord(
                    id=f"project-{suffix}",
                    tenant_id=tenant,
                    name=f"Projeto {suffix}",
                    default_unit="m",
                    created_by="seed",
                    expires_at=NOW,
                )
            )
            session.add(
                UploadRecord(
                    id=f"upload-{suffix}",
                    tenant_id=tenant,
                    object_key=f"tenants/{tenant}/uploads/source-{suffix}.pdf",
                    filename="source.pdf",
                    content_type="application/pdf",
                    size_bytes=1,
                    sha256=suffix * 64,
                )
            )
            session.flush()
            session.add(
                JobRecord(
                    id=str(job_id),
                    tenant_id=tenant,
                    project_id=f"project-{suffix}",
                    upload_id=f"upload-{suffix}",
                    status="REVIEW_REQUIRED",
                    stage="PREVIEWING",
                    expires_at=NOW,
                )
            )
        session.add_all(
            [
                SurveyRecord(
                    id=SURVEY_ID,
                    tenant_id=TENANT,
                    name="Praça principal",
                    order_ref="OS-030",
                    status="COMPLETED",
                    version=4,
                    snapshot_json=_packet(SURVEY_ID, with_photo=True),
                    created_at=NOW,
                    updated_at=NOW,
                ),
                SurveyRecord(
                    id=OTHER_SURVEY_ID,
                    tenant_id=OTHER_TENANT,
                    name="Praça alheia",
                    order_ref="OS-OTHER",
                    status="COMPLETED",
                    version=2,
                    snapshot_json=_packet(OTHER_SURVEY_ID),
                    created_at=NOW,
                    updated_at=NOW,
                ),
            ]
        )
        session.flush()
        media_key = f"tenants/{TENANT}/surveys/{SURVEY_ID}/media/{PHOTO_SHA256}"
        session.add(
            SurveyMediaRecord(
                id="00000000-0000-7000-8000-000000000903",
                tenant_id=TENANT,
                survey_id=SURVEY_ID,
                sha256=PHOTO_SHA256,
                mime_type="image/jpeg",
                byte_size=len(PHOTO),
                object_key=media_key,
                status="CONFIRMED",
                created_at=NOW,
            )
        )
    store.put_direct(object_key=media_key, body=PHOTO, content_type="image/jpeg")
    store.put_direct(
        object_key=f"tenants/{TENANT}/surveys/{SURVEY_ID}/analysis/{PHOTO_SHA256}.json",
        body=json.dumps(
            {
                "tenant_id": TENANT,
                "survey_id": SURVEY_ID,
                "provider_pass": "skipped",
                "readings": [],
                "notes": ["sem cota legível"],
                "lineage": {"task": "FIELD_PHOTO_READING"},
            }
        ).encode(),
        content_type="application/json",
    )


def _client(
    tmp_path: Path, *, real_providers_enabled: bool = False, authorized: bool = False
) -> TestClient:
    tmp_path.mkdir(parents=True, exist_ok=True)
    database = Database(f"sqlite+pysqlite:///{tmp_path / 'field-evidence.db'}")
    database.create_schema()
    settings = ApiSettings(
        database_url=f"sqlite+pysqlite:///{tmp_path / 'field-evidence.db'}",
        artifact_bucket="croquito-test-artifacts",
        aws_region="sa-east-1",
        aws_endpoint_url="http://localhost:4566",
        queue_url=None,
        oidc_issuer=None,
        oidc_audience=None,
        web_origin="http://localhost:5173",
        allow_test_tokens=True,
        real_providers_enabled=real_providers_enabled,
    )
    application = create_app(settings=settings, database=database)
    store = FakeObjectStore()
    application.state.artifact_store = store
    _seed(database, store)
    if authorized:
        with database.sessions.begin() as session:
            session.add(
                TenantAiProcessingEntitlementRecord(
                    id=f"entitlement-{tmp_path.name}",
                    tenant_id=TENANT,
                    status="ACTIVE",
                    agreement_reference="contract-f030",
                    authorized_by="operator",
                    authorized_at=NOW,
                )
            )
            session.flush()
            session.add(
                AiProcessingAuthorizationRecord(
                    id=f"authorization-{tmp_path.name}",
                    tenant_id=TENANT,
                    job_id=str(JOB_ID),
                    accepted_by="operator",
                    notice_version="contractual-entitlement-v1",
                    providers_json=["anthropic"],
                    global_processing=True,
                    retention_days=7,
                    authorization_source="contract",
                    entitlement_id=f"entitlement-{tmp_path.name}",
                    agreement_reference="contract-f030",
                )
            )
    return TestClient(application)


def _database(client: TestClient) -> Database:
    return cast(Database, cast(Any, client.app).state.database)


def _store(client: TestClient) -> FakeObjectStore:
    return cast(FakeObjectStore, cast(Any, client.app).state.artifact_store)


def _queue(client: TestClient) -> FakeQueue:
    queue = FakeQueue()
    processing_queue = cast(Any, client.app).state.queue
    processing_queue.queue_url = "http://localstack/queue"
    processing_queue.client = queue
    return queue


def _presign_standalone(
    client: TestClient,
    *,
    body: bytes = PHOTO,
    mime_type: str = "image/jpeg",
    base_version: int = 1,
    key: str = "standalone-presign",
) -> Any:
    return client.post(
        f"/v1/jobs/{JOB_ID}/field-evidence/photos/presign",
        headers=_headers(key=key),
        json={
            "base_version": base_version,
            "sha256": hashlib.sha256(body).hexdigest(),
            "mime_type": mime_type,
            "byte_size": len(body),
            "anchor_text": "Muro dos fundos, junto ao portão",
        },
    )


def test_lista_somente_levantamentos_concluidos_do_tenant(tmp_path: Path) -> None:
    client = _client(tmp_path)

    response = client.get("/v1/surveys", headers=_headers())

    assert response.status_code == 200
    body = response.json()
    assert body["next_cursor"] is None
    assert len(body["items"]) == 1
    assert body["items"][0] | {"completed_at": "ignored"} == {
        "survey_id": SURVEY_ID,
        "name": "Praça principal",
        "order_ref": "OS-030",
        "version": 4,
        "photo_count": 1,
        "confirmed_measurement_count": 1,
        "completed_at": "ignored",
    }


def test_vinculo_e_desvinculo_sao_idempotentes_e_versionados(tmp_path: Path) -> None:
    client = _client(tmp_path)
    path = f"/v1/jobs/{JOB_ID}/field-evidence/surveys/{SURVEY_ID}"

    linked = client.post(path, headers=_headers(key="link-1"), json={"base_version": 1})
    replay = client.post(path, headers=_headers(key="link-1"), json={"base_version": 1})
    natural_replay = client.post(path, headers=_headers(key="link-2"), json={"base_version": 1})

    assert linked.status_code == replay.status_code == natural_replay.status_code == 200
    assert linked.json() == replay.json() == natural_replay.json()
    assert linked.json()["version"] == 2
    with _database(client).sessions() as session:
        assert len(list(session.scalars(select(JobSurveyLinkRecord)))) == 1
        assert set(session.scalars(select(AuditRecord.action))) == {"JOB_SURVEY_LINKED"}

    unlinked = client.post(
        f"{path}/unlink", headers=_headers(key="unlink-1"), json={"base_version": 2}
    )
    assert unlinked.status_code == 200
    assert unlinked.json()["linked"] is False
    assert unlinked.json()["version"] == 3
    with _database(client).sessions() as session:
        assert list(session.scalars(select(JobSurveyLinkRecord))) == []


def test_vinculo_recusa_versao_concorrente_e_evidencia_de_outro_tenant(tmp_path: Path) -> None:
    client = _client(tmp_path)

    conflict = client.post(
        f"/v1/jobs/{JOB_ID}/field-evidence/surveys/{SURVEY_ID}",
        headers=_headers(key="wrong-version"),
        json={"base_version": 8},
    )
    foreign_survey = client.post(
        f"/v1/jobs/{JOB_ID}/field-evidence/surveys/{OTHER_SURVEY_ID}",
        headers=_headers(key="foreign-survey"),
        json={"base_version": 1},
    )
    foreign_job = client.get(f"/v1/jobs/{OTHER_JOB_ID}/field-evidence", headers=_headers())

    assert conflict.status_code == 409
    assert conflict.json()["code"] == "REVISION_CONFLICT"
    assert foreign_survey.status_code == 404
    assert foreign_job.status_code == 404


def test_leitura_retorna_ancora_medida_confirmada_e_url_temporaria(tmp_path: Path) -> None:
    client = _client(tmp_path)
    path = f"/v1/jobs/{JOB_ID}/field-evidence/surveys/{SURVEY_ID}"
    assert (
        client.post(path, headers=_headers(key="link-read"), json={"base_version": 1}).status_code
        == 200
    )

    response = client.get(f"/v1/jobs/{JOB_ID}/field-evidence", headers=_headers())

    assert response.status_code == 200
    body = response.json()
    assert body["version"] == 2
    assert [item["source_id"] for item in body["surveys"][0]["measurements"]] == [
        "measurement-confirmed"
    ]
    photo = body["photos"][0]
    assert photo["origin"] == "survey"
    assert photo["anchors"] == [{"kind": "point", "ref_id": "p1"}]
    assert photo["url"].endswith("?temporary=true")
    assert photo["reading_status"] == "PROCESSED"
    assert photo["classification_status"] == "NOT_REQUESTED"
    assert photo["classification"] is None
    assert photo["analysis"]["notes"] == ["sem cota legível"]
    assert "tenant_id" not in photo["analysis"]
    assert "survey_id" not in photo["analysis"]


def test_papel_incorreto_e_recusado_antes_do_lookup(tmp_path: Path) -> None:
    client = _client(tmp_path)

    response = client.get(
        f"/v1/jobs/{OTHER_JOB_ID}/field-evidence",
        headers=_headers(roles="field_technician"),
    )

    assert response.status_code == 403
    assert response.json()["code"] == "FORBIDDEN"


def test_foto_avulsa_exige_mime_fechado_e_nao_persiste_url_assinada(tmp_path: Path) -> None:
    client = _client(tmp_path)

    invalid = _presign_standalone(client, mime_type="application/pdf", key="bad-mime")
    created = _presign_standalone(client)
    replay = _presign_standalone(client)

    assert invalid.status_code == 422
    assert created.status_code == replay.status_code == 200
    assert created.json()["photo_id"] == replay.json()["photo_id"]
    assert created.json()["version"] == 2
    assert created.json()["url"].endswith(
        "?checksum=" + created.json()["headers"]["x-amz-checksum-sha256"]
    )
    with _database(client).sessions() as session:
        photo = session.get(JobFieldPhotoRecord, created.json()["photo_id"])
        assert photo is not None and photo.status == "PRESIGNED"
        intent = session.scalar(
            select(IdempotencyRecord).where(IdempotencyRecord.key == "standalone-presign")
        )
        assert intent is not None
        serialized = json.dumps(intent.response_json)
        assert "url" not in serialized
        assert "storage.invalid" not in serialized


def test_confirmacao_confere_digest_e_nao_dispara_analise(tmp_path: Path) -> None:
    client = _client(tmp_path)
    queue = _queue(client)
    presign = _presign_standalone(client)
    photo_id = presign.json()["photo_id"]
    with _database(client).sessions() as session:
        photo = session.get(JobFieldPhotoRecord, photo_id)
        assert photo is not None
        object_key = photo.object_key
    _store(client).put_direct(object_key=object_key, body=PHOTO, content_type="image/jpeg")

    confirmed = client.post(
        f"/v1/jobs/{JOB_ID}/field-evidence/photos/{photo_id}/confirm",
        headers=_headers(key="standalone-confirm"),
        json={"base_version": 2},
    )

    assert confirmed.status_code == 200
    assert confirmed.json() == {"photo_id": photo_id, "status": "CONFIRMED", "version": 3}
    assert len(queue.messages) == 0
    evidence = client.get(f"/v1/jobs/{JOB_ID}/field-evidence", headers=_headers())
    assert evidence.status_code == 200
    assert evidence.json()["photos"][0]["anchor_text"] == "Muro dos fundos, junto ao portão"
    assert evidence.json()["photos"][0]["reading_status"] == "NOT_REQUESTED"


def test_digest_divergente_nao_confirma_foto_avulsa(tmp_path: Path) -> None:
    client = _client(tmp_path)
    presign = _presign_standalone(client)
    photo_id = presign.json()["photo_id"]
    with _database(client).sessions() as session:
        photo = session.get(JobFieldPhotoRecord, photo_id)
        assert photo is not None
        object_key = photo.object_key
    corrupted = b"field evidence synthetic jpeh"
    assert len(corrupted) == len(PHOTO)
    _store(client).put_direct(object_key=object_key, body=corrupted, content_type="image/jpeg")

    response = client.post(
        f"/v1/jobs/{JOB_ID}/field-evidence/photos/{photo_id}/confirm",
        headers=_headers(key="digest-mismatch"),
        json={"base_version": 2},
    )

    assert response.status_code == 409
    assert response.json()["code"] == "FIELD_PHOTO_DIGEST_MISMATCH"


def test_leitura_so_e_enfileirada_por_pedido_explicito(tmp_path: Path) -> None:
    client = _client(tmp_path)
    queue = _queue(client)
    presign = _presign_standalone(client)
    photo_id = presign.json()["photo_id"]
    with _database(client).sessions() as session:
        photo = session.get(JobFieldPhotoRecord, photo_id)
        assert photo is not None
        object_key = photo.object_key
    _store(client).put_direct(object_key=object_key, body=PHOTO, content_type="image/jpeg")
    assert (
        client.post(
            f"/v1/jobs/{JOB_ID}/field-evidence/photos/{photo_id}/confirm",
            headers=_headers(key="confirm-before-reading"),
            json={"base_version": 2},
        ).status_code
        == 200
    )
    assert len(queue.messages) == 0

    requested = client.post(
        f"/v1/jobs/{JOB_ID}/field-evidence/photos/standalone/{photo_id}/reading",
        headers=_headers(key="reading-1"),
        json={"base_version": 3},
    )
    replay = client.post(
        f"/v1/jobs/{JOB_ID}/field-evidence/photos/standalone/{photo_id}/reading",
        headers=_headers(key="reading-1"),
        json={"base_version": 3},
    )

    assert requested.status_code == replay.status_code == 202
    assert requested.json()["version"] == 4
    assert len(queue.messages) == 2  # at-least-once; o worker deduplica pela linha de estado
    assert {json.loads(message["Body"])["command"] for message in queue.messages} == {
        "analyze_field_evidence"
    }


def test_classificacao_exige_provider_e_entitlement_antes_de_enfileirar(tmp_path: Path) -> None:
    disabled = _client(tmp_path / "disabled")
    assert (
        disabled.post(
            f"/v1/jobs/{JOB_ID}/field-evidence/surveys/{SURVEY_ID}",
            headers=_headers(key="link-class-disabled"),
            json={"base_version": 1},
        ).status_code
        == 200
    )
    path = (
        f"/v1/jobs/{JOB_ID}/field-evidence/photos/survey/"
        "00000000-0000-7000-8000-000000000903/classification"
    )
    unavailable = disabled.post(
        path,
        headers=_headers(key="classification-disabled"),
        json={"base_version": 2},
    )
    assert unavailable.status_code == 503
    assert unavailable.json()["code"] == "PROVIDER_UNAVAILABLE"

    enabled = _client(tmp_path / "enabled", real_providers_enabled=True)
    assert (
        enabled.post(
            f"/v1/jobs/{JOB_ID}/field-evidence/surveys/{SURVEY_ID}",
            headers=_headers(key="link-class-enabled"),
            json={"base_version": 1},
        ).status_code
        == 200
    )
    forbidden = enabled.post(
        path,
        headers=_headers(key="classification-no-entitlement"),
        json={"base_version": 2},
    )
    assert forbidden.status_code == 403
    assert forbidden.json()["code"] == "AI_PROCESSING_NOT_AUTHORIZED"
    assert len(_queue(enabled).messages) == 0

    authorized = _client(tmp_path / "authorized", real_providers_enabled=True, authorized=True)
    queue = _queue(authorized)
    assert (
        authorized.post(
            f"/v1/jobs/{JOB_ID}/field-evidence/surveys/{SURVEY_ID}",
            headers=_headers(key="link-class-authorized"),
            json={"base_version": 1},
        ).status_code
        == 200
    )
    accepted = authorized.post(
        path,
        headers=_headers(key="classification-authorized"),
        json={"base_version": 2},
    )
    replay = authorized.post(
        path,
        headers=_headers(key="classification-authorized"),
        json={"base_version": 2},
    )
    assert accepted.status_code == replay.status_code == 202
    assert accepted.json()["task"] == "classification"
    assert accepted.json()["status"] == "QUEUED"
    assert accepted.json()["version"] == 3
    assert len(queue.messages) == 2
    with _database(authorized).sessions() as session:
        state = session.scalar(
            select(FieldEvidenceAnalysisRecord).where(
                FieldEvidenceAnalysisRecord.task == "classification"
            )
        )
        assert state is not None
        assert state.artifact_key is not None
        assert state.artifact_key.endswith("/classification.json")


def test_valor_so_pode_ser_confirmado_depois_da_leitura_e_correcao_e_append_only(
    tmp_path: Path,
) -> None:
    client = _client(tmp_path)
    presign = _presign_standalone(client)
    photo_id = presign.json()["photo_id"]
    with _database(client).sessions() as session:
        photo = session.get(JobFieldPhotoRecord, photo_id)
        assert photo is not None
        object_key = photo.object_key
    _store(client).put_direct(object_key=object_key, body=PHOTO, content_type="image/jpeg")
    assert (
        client.post(
            f"/v1/jobs/{JOB_ID}/field-evidence/photos/{photo_id}/confirm",
            headers=_headers(key="confirm-for-value"),
            json={"base_version": 2},
        ).status_code
        == 200
    )
    value_path = f"/v1/jobs/{JOB_ID}/field-evidence/photos/standalone/{photo_id}/values"
    too_early = client.post(
        value_path,
        headers=_headers(key="value-too-early"),
        json={
            "base_version": 3,
            "source_reading_id": "fpr_reading",
            "value_mm": 2450,
            "kind": "length",
            "raw_text": "2,45 m",
        },
    )
    assert too_early.status_code == 409
    with _database(client).sessions.begin() as session:
        job = session.get(JobRecord, str(JOB_ID))
        assert job is not None
        state = FieldEvidenceAnalysisRecord(
            id="00000000-0000-7000-8000-000000000904",
            tenant_id=TENANT,
            job_id=str(JOB_ID),
            origin="standalone",
            evidence_id=photo_id,
            task="reading",
            status="PROCESSED",
            artifact_key=(
                f"tenants/{TENANT}/jobs/{JOB_ID}/field-evidence/analysis/"
                f"standalone/{photo_id}/reading.json"
            ),
            requested_by="reviewer",
        )
        session.add(state)
    assert state.artifact_key is not None
    _store(client).put_direct(
        object_key=state.artifact_key,
        body=json.dumps(
            {"schema": "field-evidence-reading/1", "readings": [{"id": "fpr_reading"}]}
        ).encode(),
        content_type="application/json",
    )
    first = client.post(
        value_path,
        headers=_headers(key="value-first"),
        json={
            "base_version": 3,
            "source_reading_id": "fpr_reading",
            "value_mm": 2450,
            "kind": "length",
            "raw_text": "2,45 m",
        },
    )
    correction = client.post(
        value_path,
        headers=_headers(key="value-correction"),
        json={
            "base_version": 4,
            "source_reading_id": "fpr_reading",
            "value_mm": 2470,
            "kind": "length",
            "raw_text": "2,47 m",
        },
    )

    assert first.status_code == correction.status_code == 200
    assert correction.json()["version"] == 5
    with _database(client).sessions() as session:
        rows = list(
            session.scalars(
                select(FieldPhotoValueConfirmationRecord).order_by(
                    FieldPhotoValueConfirmationRecord.confirmed_at
                )
            )
        )
        assert [row.status for row in rows] == ["SUPERSEDED", "ACTIVE"]
        assert rows[1].supersedes_confirmation_id == rows[0].id
    evidence = client.get(f"/v1/jobs/{JOB_ID}/field-evidence", headers=_headers())
    confirmed = evidence.json()["photos"][0]["confirmed_values"]
    assert len(confirmed) == 1
    assert confirmed[0]["value_mm"] == 2470
