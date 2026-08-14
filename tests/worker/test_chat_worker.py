"""O turno de conversa é respondido pelo worker, uma vez por comando.

Cada teste cobre um desfecho do contrato: resposta gravada com lineage quando a fixture
responde, recusa do turno inteiro quando a resposta cita um id que não existe na
revisão-base, falha sem vazar mensagem quando o estágio quebra e recusa antes de qualquer
chamada quando não há suíte injetada — nesta fatia nenhum provider real é construído.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from croquito_api.database import (
    ChatSessionRecord,
    ChatTurnRecord,
    Database,
    JobRecord,
    ProjectRecord,
    ReviewRevisionRecord,
    UploadRecord,
)
from croquito_worker.local_queue import LocalQueueWorker, LocalWorkerSettings
from croquito_worker.providers import (
    ProviderName,
    ProviderSuite,
    build_synthetic_provider_suite,
)
from tests.bundles import (
    WIDTH_PROPOSAL_ID,
    WIDTH_READING_ID,
    build_associations,
    build_packet,
    build_proposals,
)
from tests.fakes import FakeObjectStore, FakeQueue

JOB_ID = "00000000-0000-7000-8000-000000000a01"
REVIEW_ID = "00000000-0000-7000-8000-000000000a02"
SESSION_ID = "00000000-0000-7000-8000-000000000a03"
TURN_ID = "00000000-0000-7000-8000-000000000a04"
TENANT_ID = "tenant-chat"
DATASET_ID = "synthetic-chat-v1"
DIGEST = "c" * 64
SOURCE_IMAGE_KEY = f"tenants/{TENANT_ID}/jobs/{JOB_ID}/review/source.png"


def _seed(
    tmp_path: Path, *, with_source_image: bool = True
) -> tuple[Database, str, FakeObjectStore]:
    database_url = f"sqlite+pysqlite:///{tmp_path / 'chat.db'}"
    database = Database(database_url)
    database.create_schema()
    expires_at = datetime.now(UTC) + timedelta(days=7)
    with database.sessions.begin() as session:
        session.add(
            ProjectRecord(
                id="project-chat",
                tenant_id=TENANT_ID,
                name="Conversa",
                default_unit="m",
                created_by="reviewer",
                expires_at=expires_at,
            )
        )
        session.add(
            UploadRecord(
                id="upload-chat",
                tenant_id=TENANT_ID,
                object_key=f"tenants/{TENANT_ID}/uploads/upload-chat/entrada.pdf",
                filename="entrada.pdf",
                content_type="application/pdf",
                size_bytes=1024,
                sha256="d" * 64,
            )
        )
        session.flush()
        session.add(
            JobRecord(
                id=JOB_ID,
                tenant_id=TENANT_ID,
                project_id="project-chat",
                upload_id="upload-chat",
                status="REVIEW_REQUIRED",
                stage="PREVIEWING",
                expires_at=expires_at,
            )
        )
        session.flush()
        session.add(
            ReviewRevisionRecord(
                id=REVIEW_ID,
                tenant_id=TENANT_ID,
                job_id=JOB_ID,
                version=1,
                packet_json=build_packet(dataset_id=DATASET_ID, digest=DIGEST).model_dump(
                    mode="json"
                ),
                associations_json=build_associations(
                    dataset_id=DATASET_ID, digest=DIGEST
                ).model_dump(mode="json"),
                proposals_json=build_proposals(dataset_id=DATASET_ID, digest=DIGEST).model_dump(
                    mode="json"
                ),
                evidence_refs_json=(
                    {"source_image_key": SOURCE_IMAGE_KEY} if with_source_image else {}
                ),
                required_blocker_codes_json=[],
                created_by="local-worker",
            )
        )
        session.flush()
        session.add(
            ChatSessionRecord(
                id=SESSION_ID,
                tenant_id=TENANT_ID,
                job_id=JOB_ID,
                base_review_revision_id=REVIEW_ID,
                status="OPEN",
                created_by="eng-chat",
            )
        )
        session.flush()
        session.add(
            ChatTurnRecord(
                id=TURN_ID,
                tenant_id=TENANT_ID,
                job_id=JOB_ID,
                session_id=SESSION_ID,
                sequence=1,
                status="QUEUED",
                question_text="Essa cota mede a borda do campo?",
                anchor_refs_json={
                    "reading_ids": [WIDTH_READING_ID],
                    "proposal_ids": [WIDTH_PROPOSAL_ID],
                },
                requested_by="eng-chat",
            )
        )
    store = FakeObjectStore()
    if with_source_image:
        store.put_direct(
            object_key=SOURCE_IMAGE_KEY, body=b"\x89PNG folha sintetica", content_type="image/png"
        )
    return database, database_url, store


def _worker(
    database_url: str,
    store: FakeObjectStore,
    body: dict[str, Any],
    *,
    suite: ProviderSuite | None,
) -> tuple[LocalQueueWorker, FakeQueue]:
    worker = LocalQueueWorker(
        LocalWorkerSettings(
            database_url=database_url,
            queue_url="http://localstack/queue",
            aws_region="sa-east-1",
            aws_endpoint_url="http://localstack",
            # A flag de providers reais ligada não muda nada: sem suíte injetada o turno
            # falha em vez de construir provider.
            real_providers_enabled=True,
        ),
        provider_suite=suite,
    )
    queue = FakeQueue()
    queue.send_message(MessageBody=json.dumps(body))
    worker.client = queue
    worker.s3_client = store
    return worker, queue


def _message(**overrides: Any) -> dict[str, Any]:
    return {
        "command": "answer_chat_turn",
        "chat_turn_id": TURN_ID,
        "job_id": JOB_ID,
        "tenant_id": TENANT_ID,
        **overrides,
    }


@pytest.fixture(autouse=True)
def _local_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "local")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "local")


def test_chat_turn_records_the_answer_with_the_call_lineage(tmp_path: Path) -> None:
    database, database_url, store = _seed(tmp_path)
    worker, queue = _worker(database_url, store, _message(), suite=build_synthetic_provider_suite())

    assert worker.run_once() == 1

    with database.sessions() as session:
        record = session.get(ChatTurnRecord, TURN_ID)
        assert record is not None
        assert record.status == "COMPLETED"
        assert record.failure_code is None
        assert record.answer_json is not None
        assert record.answer_json["answer_kind"] == "answer"
        acts = record.answer_json["proposed_acts"]
        # A resposta carrega rascunhos tipados dos payloads que os endpoints já aceitam.
        assert [act["act"] for act in acts] == ["reading_decision", "trace_association"]
        assert acts[0]["reading_id"] == WIDTH_READING_ID
        assert acts[0]["association_proposal_id"] == WIDTH_PROPOSAL_ID
        assert record.provider == ProviderName.BEDROCK_ANTHROPIC.value
        assert record.prompt_version == "review-chat@1.0.1"
        # O digest do lineage é o do envelope imagem+texto da chamada.
        assert record.input_digest is not None and len(record.input_digest) == 64
    assert queue.deleted == ["receipt-1"]


def test_chat_turn_replay_does_not_answer_twice(tmp_path: Path) -> None:
    database, database_url, store = _seed(tmp_path)
    suite = build_synthetic_provider_suite()
    worker, _queue = _worker(database_url, store, _message(), suite=suite)
    assert worker.run_once() == 1
    with database.sessions.begin() as session:
        first = session.get(ChatTurnRecord, TURN_ID)
        assert first is not None and first.answer_json is not None
        # Marca de sabotagem: se o replay respondesse de novo, ela seria sobrescrita.
        first.answer_json = {**first.answer_json, "answer_text": "resposta original"}

    replay, replay_queue = _worker(database_url, store, _message(), suite=suite)
    assert replay.run_once() == 1

    with database.sessions() as session:
        record = session.get(ChatTurnRecord, TURN_ID)
        assert record is not None
        assert record.status == "COMPLETED"
        assert record.answer_json is not None
        assert record.answer_json["answer_text"] == "resposta original"
    assert replay_queue.deleted == ["receipt-1"]


def test_chat_turn_claims_only_a_queued_or_failed_turn(tmp_path: Path) -> None:
    database, database_url, store = _seed(tmp_path)
    with database.sessions.begin() as session:
        running = session.get(ChatTurnRecord, TURN_ID)
        assert running is not None
        running.status = "RUNNING"
    worker, queue = _worker(database_url, store, _message(), suite=build_synthetic_provider_suite())

    assert worker.run_once() == 1

    with database.sessions() as session:
        record = session.get(ChatTurnRecord, TURN_ID)
        assert record is not None
        # Outro consumidor já tomou o turno; este drena a mensagem sem tocar nele.
        assert record.status == "RUNNING"
        assert record.answer_json is None
    assert queue.deleted == ["receipt-1"]


def test_chat_turn_refuses_the_whole_answer_when_a_draft_cites_an_unknown_id(
    tmp_path: Path,
) -> None:
    database, database_url, store = _seed(tmp_path)
    # Rascunho amarrado a outra revisão: cada id é válido na forma e inexistente aqui.
    suite = build_synthetic_provider_suite(
        chat_reading_id="rd_9999999999999999", chat_proposal_id="vp_9999999999999999"
    )
    worker, queue = _worker(database_url, store, _message(), suite=suite)

    assert worker.run_once() == 1

    with database.sessions() as session:
        record = session.get(ChatTurnRecord, TURN_ID)
        assert record is not None
        assert record.status == "FAILED"
        assert record.failure_code == "CHAT_ACT_UNKNOWN_REFERENCE"
        # Nem meia resposta é gravada: o turno inteiro é recusado.
        assert record.answer_json is None
        # O lineage da recusa fica: é ele que permite corrigir o contrato depois.
        assert record.provider == ProviderName.BEDROCK_ANTHROPIC.value
    assert queue.deleted == ["receipt-1"]


def test_chat_turn_without_an_injected_suite_never_builds_a_provider(tmp_path: Path) -> None:
    database, database_url, store = _seed(tmp_path)
    worker, queue = _worker(database_url, store, _message(), suite=None)

    assert worker.run_once() == 1

    with database.sessions() as session:
        record = session.get(ChatTurnRecord, TURN_ID)
        assert record is not None
        assert record.status == "FAILED"
        assert record.failure_code == "CHAT_PROVIDER_UNAVAILABLE"
        assert record.answer_json is None
        assert record.provider is None
    assert queue.deleted == ["receipt-1"]


def test_chat_turn_failure_never_leaks_the_exception_message(tmp_path: Path) -> None:
    """Sem imagem de página o estágio quebra; só o código estável é persistido."""
    database, database_url, store = _seed(tmp_path, with_source_image=False)
    worker, queue = _worker(database_url, store, _message(), suite=build_synthetic_provider_suite())

    assert worker.run_once() == 1

    with database.sessions() as session:
        record = session.get(ChatTurnRecord, TURN_ID)
        assert record is not None
        assert record.status == "FAILED"
        assert record.failure_code == "CHAT_ANSWER_FAILED"
        assert record.answer_json is None
    assert queue.deleted == ["receipt-1"]


def test_chat_turn_refuses_a_message_from_another_tenant(tmp_path: Path) -> None:
    database, database_url, store = _seed(tmp_path)
    worker, _queue = _worker(
        database_url,
        store,
        _message(tenant_id="tenant-other"),
        suite=build_synthetic_provider_suite(),
    )

    with pytest.raises(ValueError):
        worker.run_once()

    with database.sessions() as session:
        record = session.get(ChatTurnRecord, TURN_ID)
        assert record is not None
        assert record.status == "QUEUED"


def test_chat_turn_id_is_required_for_the_chat_command(tmp_path: Path) -> None:
    _database, database_url, store = _seed(tmp_path)
    body = _message()
    del body["chat_turn_id"]
    worker, _queue = _worker(database_url, store, body, suite=build_synthetic_provider_suite())

    with pytest.raises(ValueError):
        worker.run_once()
