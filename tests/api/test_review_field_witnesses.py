"""Testemunhas explícitas e neutras da F-030 (T4)."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from sqlalchemy import func, select

from croquito_api.database import (
    Database,
    FieldPhotoValueConfirmationRecord,
    JobSurveyLinkRecord,
    ReviewRevisionRecord,
    RevisionRecord,
    SurveyRecord,
)
from tests.api.test_api import _client, _headers, _seed_review_session
from tests.api.test_field_evidence import _packet

TENANT = "tenant-a"
SURVEY_ID = "survey-witness"


def _database(client: Any) -> Database:
    return cast(Database, cast(Any, client.app).state.database)


def _confirm_target_reading(client: Any, job_id: Any) -> dict[str, Any]:
    response = client.post(
        f"/v1/jobs/{job_id}/review/decisions",
        headers={**_headers(TENANT), "Idempotency-Key": "confirm-witness-target"},
        json={
            "base_version": 1,
            "decisions": [
                {
                    "reading_id": "rd_1111111111111111",
                    "action": "confirm",
                    "justification": "Cota conferida antes de associar observações.",
                    "association_proposal_id": "vp_1111111111111111",
                }
            ],
        },
    )
    assert response.status_code == 200
    return cast(dict[str, Any], response.json())


def _seed_sources(client: Any, job_id: Any) -> str:
    packet = _packet(SURVEY_ID)
    packet["measurements"][0]["id"] = "field-confirmed"
    packet["measurements"][0]["value_mm"] = 26000
    packet["measurements"][1]["id"] = "field-draft"
    packet["measurements"][1]["value_mm"] = 25900
    confirmation_id = "00000000-0000-7000-8000-000000000921"
    now = datetime.now(UTC)
    with _database(client).sessions.begin() as session:
        session.add(
            SurveyRecord(
                id=SURVEY_ID,
                tenant_id=TENANT,
                name="Levantamento com testemunhas",
                order_ref="OS-WITNESS",
                status="COMPLETED",
                version=2,
                snapshot_json=packet,
            )
        )
        session.flush()
        session.add(
            JobSurveyLinkRecord(
                id="00000000-0000-7000-8000-000000000922",
                tenant_id=TENANT,
                job_id=str(job_id),
                survey_id=SURVEY_ID,
                linked_by="reviewer",
            )
        )
        session.add(
            FieldPhotoValueConfirmationRecord(
                id=confirmation_id,
                tenant_id=TENANT,
                job_id=str(job_id),
                origin="standalone",
                evidence_id="00000000-0000-7000-8000-000000000923",
                source_reading_id="fpr_field",
                value_mm=25850,
                kind="length",
                raw_text="25,85 m",
                status="ACTIVE",
                confirmed_by="reviewer",
                confirmed_at=now,
            )
        )
    return confirmation_id


def _associate(
    client: Any,
    job_id: Any,
    *,
    base_version: int,
    source: dict[str, Any],
    key: str,
) -> Any:
    return client.post(
        f"/v1/jobs/{job_id}/review/witnesses",
        headers={**_headers(TENANT), "Idempotency-Key": key},
        json={
            "base_version": base_version,
            "action": "associate",
            "reading_id": "rd_1111111111111111",
            "source": source,
        },
    )


def test_multiplas_testemunhas_sao_empilhadas_com_diferenca_neutra(tmp_path: Path) -> None:
    client = _client(tmp_path)
    job_id = _seed_review_session(client)
    before = _confirm_target_reading(client, job_id)
    confirmation_id = _seed_sources(client, job_id)
    with _database(client).sessions() as session:
        scene_count_before = session.scalar(select(func.count(RevisionRecord.id)))

    field = _associate(
        client,
        job_id,
        base_version=2,
        source={
            "type": "survey_measurement",
            "source_id": "field-confirmed",
            "survey_id": SURVEY_ID,
        },
        key="associate-field",
    )
    photo = _associate(
        client,
        job_id,
        base_version=3,
        source={"type": "photo_reading", "source_id": confirmation_id},
        key="associate-photo",
    )

    assert field.status_code == photo.status_code == 200
    assert field.json()["field_witnesses"][0]["difference_mm"] == "100.00"
    witnesses = photo.json()["field_witnesses"]
    assert len(witnesses) == 2
    assert [item["difference_mm"] for item in witnesses] == ["100.00", "-50.00"]
    assert all("status" not in item and "agrees" not in item for item in witnesses)
    # A observação lateral não refaz nada da cadeia geométrica.
    for key in ("scene", "blockers", "issues", "packet", "selected_associations"):
        assert photo.json()[key] == before[key]
    with _database(client).sessions() as session:
        assert session.scalar(select(func.count(RevisionRecord.id))) == scene_count_before


def test_valor_do_cliente_e_inaceitavel_e_medida_draft_nao_vira_testemunha(
    tmp_path: Path,
) -> None:
    client = _client(tmp_path)
    job_id = _seed_review_session(client)
    _confirm_target_reading(client, job_id)
    _seed_sources(client, job_id)
    path = f"/v1/jobs/{job_id}/review/witnesses"

    invented = client.post(
        path,
        headers={**_headers(TENANT), "Idempotency-Key": "invented-value"},
        json={
            "base_version": 2,
            "action": "associate",
            "reading_id": "rd_1111111111111111",
            "source": {
                "type": "survey_measurement",
                "source_id": "field-confirmed",
                "survey_id": SURVEY_ID,
                "value_mm": 1,
            },
        },
    )
    draft = _associate(
        client,
        job_id,
        base_version=2,
        source={
            "type": "survey_measurement",
            "source_id": "field-draft",
            "survey_id": SURVEY_ID,
        },
        key="draft-source",
    )

    assert invented.status_code == 422
    assert draft.status_code == 409
    assert draft.json()["code"] == "FIELD_WITNESS_SOURCE_NOT_CONFIRMED"
    with _database(client).sessions() as session:
        latest = session.scalar(
            select(ReviewRevisionRecord)
            .where(ReviewRevisionRecord.job_id == str(job_id))
            .order_by(ReviewRevisionRecord.version.desc())
        )
        assert latest is not None and latest.version == 2


def test_testemunha_pode_ser_retratada_individualmente_e_replay_nao_duplica(
    tmp_path: Path,
) -> None:
    client = _client(tmp_path)
    job_id = _seed_review_session(client)
    _confirm_target_reading(client, job_id)
    confirmation_id = _seed_sources(client, job_id)
    associated = _associate(
        client,
        job_id,
        base_version=2,
        source={"type": "photo_reading", "source_id": confirmation_id},
        key="photo-once",
    )
    replay = _associate(
        client,
        job_id,
        base_version=2,
        source={"type": "photo_reading", "source_id": confirmation_id},
        key="photo-once",
    )
    witness_id = associated.json()["field_witnesses"][0]["witness_id"]
    retracted = client.post(
        f"/v1/jobs/{job_id}/review/witnesses",
        headers={**_headers(TENANT), "Idempotency-Key": "retract-photo"},
        json={"base_version": 3, "action": "retract", "witness_id": witness_id},
    )

    assert associated.json() == replay.json()
    assert len(associated.json()["field_witnesses"]) == 1
    assert retracted.status_code == 200
    assert retracted.json()["version"] == 4
    assert retracted.json()["field_witnesses"] == []
