"""Observações humanas sobre a classificação por IA da F-030 (T7).

A observação é versionada com a revisão, FORA da SceneRevision: registrar, corrigir ou
descartar nunca toca cena, digest, blockers ou exportação. A `source` é copiada do artefato
de classificação pelo servidor, nunca aceita do cliente.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from sqlalchemy import func, select

from croquito_api.database import (
    AuditRecord,
    Database,
    FieldEvidenceAnalysisRecord,
    JobFieldPhotoRecord,
    ReviewRevisionRecord,
    RevisionRecord,
)
from tests.api.test_api import _client, _headers, _seed_review_session
from tests.fakes import FakeObjectStore

TENANT = "tenant-a"
EVIDENCE_ID = "00000000-0000-7000-8000-000000000931"
ANALYSIS_ID = "00000000-0000-7000-8000-000000000932"


def _database(client: Any) -> Database:
    return cast(Database, cast(Any, client.app).state.database)


def _store(client: Any) -> FakeObjectStore:
    return cast(FakeObjectStore, cast(Any, client.app).state.artifact_store)


def _seed_photo(client: Any, job_id: Any) -> None:
    """Semeia a foto avulsa confirmada, sem análise ainda."""
    with _database(client).sessions.begin() as session:
        session.add(
            JobFieldPhotoRecord(
                id=EVIDENCE_ID,
                tenant_id=TENANT,
                job_id=str(job_id),
                sha256="c" * 64,
                mime_type="image/jpeg",
                byte_size=1234,
                object_key=f"tenants/{TENANT}/jobs/{job_id}/field-evidence/photos/{EVIDENCE_ID}.jpg",
                anchor_text="Alambrado do fundo",
                status="CONFIRMED",
                created_by="reviewer",
                created_at=datetime.now(UTC),
            )
        )


def _seed_classification(client: Any, job_id: Any, *, status: str = "DRAFT") -> None:
    """Acrescenta o rascunho de classificação e grava o artefato com lineage."""
    artifact_key = (
        f"tenants/{TENANT}/jobs/{job_id}/field-evidence/analysis/"
        f"standalone/{EVIDENCE_ID}/classification.json"
    )
    with _database(client).sessions.begin() as session:
        session.add(
            FieldEvidenceAnalysisRecord(
                id=ANALYSIS_ID,
                tenant_id=TENANT,
                job_id=str(job_id),
                origin="standalone",
                evidence_id=EVIDENCE_ID,
                task="classification",
                status=status,
                artifact_key=artifact_key,
                requested_by="reviewer",
            )
        )
    _store(client).put_direct(
        object_key=artifact_key,
        body=json.dumps(
            {
                "schema": "field-evidence-classification/1",
                "classification": {
                    "category": "ALAMBRADO",
                    "description": "Tela de alambrado sobre mureta baixa.",
                    "topology_notes": ["fecha à direita"],
                    "confidence": "high",
                },
                "lineage": {
                    "provider": "anthropic",
                    "model_id": "claude-opus-5",
                    "prompt": {
                        "prompt_id": "field-photo-classification",
                        "prompt_version": "field-photo-classification@1.0.0",
                        "template_hash": "d" * 64,
                        "schema_version": "1.0.0",
                    },
                },
            }
        ).encode(),
        content_type="application/json",
    )


def _seed_draft(client: Any, job_id: Any, *, status: str = "DRAFT") -> None:
    """Semeia foto avulsa confirmada + rascunho de classificação DRAFT com artefato."""
    _seed_photo(client, job_id)
    _seed_classification(client, job_id, status=status)


def _observe(client: Any, job_id: Any, *, body: dict[str, Any], key: str) -> Any:
    return client.post(
        f"/v1/jobs/{job_id}/review/field-observations",
        headers={**_headers(TENANT), "Idempotency-Key": key},
        json=body,
    )


def _record_body(**overrides: Any) -> dict[str, Any]:
    body = {
        "base_version": 1,
        "action": "record",
        "origin": "standalone",
        "evidence_id": EVIDENCE_ID,
        "category": "ALAMBRADO",
        "description": "Concordo: é alambrado, não muro.",
    }
    body.update(overrides)
    return body


def _latest_review(client: Any, job_id: Any) -> ReviewRevisionRecord:
    with _database(client).sessions() as session:
        record = session.scalar(
            select(ReviewRevisionRecord)
            .where(ReviewRevisionRecord.job_id == str(job_id))
            .order_by(ReviewRevisionRecord.version.desc())
        )
        assert record is not None
        return record


def test_registrar_cria_observacao_com_fonte_e_nao_toca_cena_nem_exportacao(
    tmp_path: Path,
) -> None:
    client = _client(tmp_path)
    job_id = _seed_review_session(client)
    _seed_draft(client, job_id)
    before = client.get(f"/v1/jobs/{job_id}/review", headers=_headers(TENANT)).json()
    with _database(client).sessions() as session:
        scene_count_before = session.scalar(select(func.count(RevisionRecord.id)))
        scene_id_before = _latest_review_id(session, job_id)

    recorded = _observe(client, job_id, body=_record_body(), key="record-1")

    assert recorded.status_code == 200
    payload = recorded.json()
    observations = payload["field_observations"]
    assert len(observations) == 1
    entry = observations[0]
    assert entry["status"] == "ACTIVE"
    assert entry["category"] == "ALAMBRADO"
    assert entry["description"] == "Concordo: é alambrado, não muro."
    # A fonte é copiada do artefato pelo servidor: categoria proposta e lineage.
    assert entry["source"]["category"] == "ALAMBRADO"
    assert entry["source"]["model_id"] == "claude-opus-5"
    assert entry["source"]["prompt_version"] == "field-photo-classification@1.0.0"
    assert entry["recorded_by"] == "reviewer"
    # Cena, blockers, pacote e exportação permanecem verbatim; nenhuma cena nova.
    for key in ("scene", "blockers", "issues", "packet", "selected_associations"):
        assert payload[key] == before[key]
    with _database(client).sessions() as session:
        assert session.scalar(select(func.count(RevisionRecord.id))) == scene_count_before
        assert _latest_review(client, job_id).scene_revision_id == scene_id_before


def _latest_review_id(session: Any, job_id: Any) -> Any:
    record = session.scalar(
        select(ReviewRevisionRecord)
        .where(ReviewRevisionRecord.job_id == str(job_id))
        .order_by(ReviewRevisionRecord.version.desc())
    )
    assert record is not None
    return record.scene_revision_id


def test_corrigir_e_append_only_e_preserva_a_proposta_da_ia(tmp_path: Path) -> None:
    client = _client(tmp_path)
    job_id = _seed_review_session(client)
    _seed_draft(client, job_id)
    recorded = _observe(client, job_id, body=_record_body(), key="record-1")
    observation_id = recorded.json()["field_observations"][0]["observation_id"]

    corrected = _observe(
        client,
        job_id,
        body=_record_body(
            base_version=2,
            category="MURO",
            description="Revendo: é muro com tela por cima.",
            corrects_observation_id=observation_id,
        ),
        key="correct-1",
    )

    assert corrected.status_code == 200
    entries = corrected.json()["field_observations"]
    by_status = {entry["status"]: entry for entry in entries}
    assert by_status["SUPERSEDED"]["observation_id"] == observation_id
    active = by_status["ACTIVE"]
    assert active["category"] == "MURO"
    assert active["supersedes_observation_id"] == observation_id
    # A proposta da IA fica preservada na fonte, mesmo com a categoria corrigida.
    assert active["source"]["category"] == "ALAMBRADO"


def test_descartar_registra_ato_sem_observacao_ativa_e_preserva_classificacao(
    tmp_path: Path,
) -> None:
    client = _client(tmp_path)
    job_id = _seed_review_session(client)
    _seed_draft(client, job_id)

    dismissed = _observe(
        client,
        job_id,
        body={
            "base_version": 1,
            "action": "dismiss",
            "origin": "standalone",
            "evidence_id": EVIDENCE_ID,
        },
        key="dismiss-1",
    )

    assert dismissed.status_code == 200
    entries = dismissed.json()["field_observations"]
    assert len(entries) == 1
    assert entries[0]["status"] == "DISMISSED"
    assert entries[0]["category"] is None
    assert entries[0]["description"] is None
    # O artefato de classificação continua intacto e em DRAFT.
    with _database(client).sessions() as session:
        analysis = session.get(FieldEvidenceAnalysisRecord, ANALYSIS_ID)
        assert analysis is not None and analysis.status == "DRAFT"
        dismiss_events = session.scalar(
            select(func.count(AuditRecord.id)).where(
                AuditRecord.action == "FIELD_OBSERVATION_DISMISSED"
            )
        )
        assert dismiss_events == 1


def test_replay_idempotente_nao_duplica_e_conflito_de_versao_e_409(tmp_path: Path) -> None:
    client = _client(tmp_path)
    job_id = _seed_review_session(client)
    _seed_draft(client, job_id)

    first = _observe(client, job_id, body=_record_body(), key="once")
    replay = _observe(client, job_id, body=_record_body(), key="once")
    stale = _observe(client, job_id, body=_record_body(base_version=1), key="stale")

    assert first.json() == replay.json()
    assert len(first.json()["field_observations"]) == 1
    assert stale.status_code == 409
    assert stale.json()["code"] == "REVISION_CONFLICT"


def test_papel_e_tenant_falham_fechados(tmp_path: Path) -> None:
    client = _client(tmp_path)
    job_id = _seed_review_session(client)
    _seed_draft(client, job_id)

    wrong_role = client.post(
        f"/v1/jobs/{job_id}/review/field-observations",
        headers={
            "Authorization": f"Bearer test:{TENANT}:reviewer:viewer",
            "Idempotency-Key": "wrong-role",
        },
        json=_record_body(),
    )
    other_tenant = client.post(
        f"/v1/jobs/{job_id}/review/field-observations",
        headers={**_headers("tenant-b"), "Idempotency-Key": "other-tenant"},
        json=_record_body(),
    )

    assert wrong_role.status_code == 403
    assert other_tenant.status_code == 404
    # Nada foi gravado: a revisão continua na versão 1.
    assert _latest_review(client, job_id).version == 1


def test_erros_nomeados_de_rascunho_e_correcao(tmp_path: Path) -> None:
    client = _client(tmp_path)
    job_id = _seed_review_session(client)

    # Foto inexistente é 404 (a foto é resolvida antes do rascunho).
    missing_photo = _observe(
        client,
        job_id,
        body=_record_body(evidence_id="00000000-0000-7000-8000-0000000009ff"),
        key="missing-photo",
    )
    assert missing_photo.status_code == 404

    # Foto presente, mas sem rascunho DRAFT: registrar falha fechado.
    _seed_photo(client, job_id)
    sem_rascunho = _observe(client, job_id, body=_record_body(), key="no-draft")
    assert sem_rascunho.status_code == 409
    assert sem_rascunho.json()["code"] == "FIELD_OBSERVATION_DRAFT_NOT_FOUND"

    _seed_classification(client, job_id)
    first = _observe(client, job_id, body=_record_body(), key="first")
    assert first.status_code == 200

    # Segunda observação sem corrects: a foto já tem ativa.
    duplicate = _observe(client, job_id, body=_record_body(base_version=2), key="dup")
    assert duplicate.status_code == 409
    assert duplicate.json()["code"] == "FIELD_OBSERVATION_ALREADY_RECORDED"

    # Corrigir uma observação inexistente é 404.
    bad_correct = _observe(
        client,
        job_id,
        body=_record_body(
            base_version=2,
            corrects_observation_id="00000000-0000-7000-8000-0000000009ee",
        ),
        key="bad-correct",
    )
    assert bad_correct.status_code == 404
    assert bad_correct.json()["code"] == "FIELD_OBSERVATION_NOT_FOUND"

    # Descartar com categoria é recusado pelo validador (422).
    dismiss_with_category = _observe(
        client,
        job_id,
        body={
            "base_version": 2,
            "action": "dismiss",
            "origin": "standalone",
            "evidence_id": EVIDENCE_ID,
            "category": "MURO",
        },
        key="dismiss-bad",
    )
    assert dismiss_with_category.status_code == 422
