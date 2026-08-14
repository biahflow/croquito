"""Conversa da revisão, fatia offline: da pergunta ao ato humano registrado.

O teste percorre API e worker sobre o mesmo banco, a mesma fila e o mesmo storage. O que
ele prova é o contorno da fatia 1: o agente responde com **rascunhos** e o registro só
existe quando o profissional envia o comando de decisão que já existia — o agente,
estruturalmente, não submete nada.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from croquito_api.config import ApiSettings
from croquito_api.database import Database
from croquito_api.main import create_app
from croquito_worker.local_queue import LocalQueueWorker, LocalWorkerSettings
from croquito_worker.providers import build_synthetic_provider_suite
from croquito_worker.review_seed import SeedInputs, seed_review
from tests.bundles import WIDTH_PROPOSAL_ID, WIDTH_READING_ID, write_seed_bundle
from tests.fakes import FakeObjectStore, FakeQueue, synthetic_pdf

TENANT = "tenant-chat-e2e"
QUEUE_URL = "http://localstack/queue"


def _headers(key: str, *, tenant: str = TENANT) -> dict[str, str]:
    return {
        "Authorization": f"Bearer test:{tenant}:eng-chat:engineer",
        "Idempotency-Key": key,
    }


@pytest.fixture
def stack(tmp_path: Path) -> tuple[TestClient, Path, FakeObjectStore, FakeQueue]:
    database_url = f"sqlite+pysqlite:///{tmp_path / 'chat-e2e.db'}"
    database = Database(database_url)
    database.create_schema()
    app = create_app(
        settings=ApiSettings(
            database_url=database_url,
            artifact_bucket="croquito-chat-e2e",
            aws_region="sa-east-1",
            aws_endpoint_url="http://localhost:4566",
            queue_url=QUEUE_URL,
            oidc_issuer=None,
            oidc_audience=None,
            web_origin="http://localhost:5173",
            allow_test_tokens=True,
        ),
        database=database,
    )
    storage = FakeObjectStore()
    queue = FakeQueue()
    app.state.artifact_store = storage
    # A `ProcessingQueue` real é mantida: o envelope publicado é o de produção.
    app.state.queue.client = queue
    return TestClient(app), tmp_path, storage, queue


def _worker(
    tmp_path: Path, storage: FakeObjectStore, queue: FakeQueue, *, fixtures: bool
) -> LocalQueueWorker:
    """O consumidor local; a suíte sintética entra por injeção explícita, como no Makefile."""
    worker = LocalQueueWorker(
        LocalWorkerSettings(
            database_url=f"sqlite+pysqlite:///{tmp_path / 'chat-e2e.db'}",
            queue_url=QUEUE_URL,
            aws_region="sa-east-1",
            aws_endpoint_url="http://localhost:4566",
            artifact_bucket="croquito-chat-e2e",
        ),
        provider_suite=build_synthetic_provider_suite() if fixtures else None,
    )
    worker.client = queue
    worker.s3_client = storage
    return worker


def test_chat_draft_becomes_a_decision_only_through_the_human_command(
    stack: tuple[TestClient, Path, FakeObjectStore, FakeQueue],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "local")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "local")
    client, tmp_path, storage, queue = stack
    pdf = synthetic_pdf()
    source_sha256 = hashlib.sha256(pdf).hexdigest()

    presign = client.post(
        "/v1/uploads/presign",
        headers=_headers("chat-presign"),
        json={
            "filename": "levantamento.pdf",
            "content_type": "application/pdf",
            "size_bytes": len(pdf),
            "sha256": source_sha256,
        },
    )
    assert presign.status_code == 200
    storage.put_direct(object_key=presign.json()["object_key"], body=pdf)
    job_id = client.post(
        "/v1/jobs",
        headers=_headers("chat-job"),
        json={
            "upload_id": presign.json()["upload_id"],
            "project_name": "Caso sintético da conversa",
            "default_unit": "m",
        },
    ).json()["job_id"]
    # Upload processado SEM suíte: nenhum provider participa da ingestão.
    assert _worker(tmp_path, storage, queue, fixtures=False).run_once() == 1

    bundle = write_seed_bundle(tmp_path / "bundle", source_sha256=source_sha256)
    seeded = seed_review(
        SeedInputs(
            job_id=UUID(job_id),
            tenant_id=TENANT,
            packet_path=bundle["packet"],
            associations_path=bundle["associations"],
            proposals_path=bundle["proposals"],
            rectangle_request_path=bundle["rectangle_request"],
            manifest_path=bundle["manifest"],
            image_path=bundle["image"],
            required_criteria=(),
            operator_id="tenant-admin-chat",
        ),
        LocalWorkerSettings(
            database_url=f"sqlite+pysqlite:///{tmp_path / 'chat-e2e.db'}",
            queue_url="",
            aws_region="sa-east-1",
            aws_endpoint_url="http://localhost:4566",
            artifact_bucket="croquito-chat-e2e",
        ),
        s3_client=storage,
    )
    assert seeded.review_version == 1

    # 1. Conversa aberta sobre a revisão corrente.
    session_id = client.post(
        f"/v1/jobs/{job_id}/chat-sessions",
        headers=_headers("chat-open"),
        json={},
    ).json()["chat_session_id"]

    # 2. Pergunta ancorada na leitura e no elemento que o profissional apontou.
    turn = client.post(
        f"/v1/jobs/{job_id}/chat-sessions/{session_id}/turns",
        headers=_headers("chat-turn"),
        json={
            "question": "Essa cota de largura mede a aresta de baixo do campo?",
            "anchors": {
                "reading_ids": [WIDTH_READING_ID],
                "proposal_ids": [WIDTH_PROPOSAL_ID],
            },
        },
    )
    assert turn.status_code == 202
    assert turn.json()["status"] == "QUEUED"
    assert queue.commands() == ["process_upload"]

    # 3. Worker com a suíte sintética injetada; nenhuma chamada externa acontece.
    assert _worker(tmp_path, storage, queue, fixtures=True).run_once() == 1
    assert queue.commands() == ["process_upload", "answer_chat_turn"]

    # 4. Polling devolve a resposta com o rascunho tipado.
    answered = client.get(
        f"/v1/jobs/{job_id}/chat-sessions/{session_id}", headers=_headers("chat-poll")
    )
    assert answered.status_code == 200
    answered_turn = answered.json()["turns"][0]
    assert answered_turn["status"] == "COMPLETED"
    assert answered_turn["failure_code"] is None
    answer = answered_turn["answer"]
    assert answer["answer_kind"] == "answer"
    draft = answer["proposed_acts"][0]
    assert draft["act"] == "reading_decision"

    # A conversa não decidiu nada: a leitura continua proposta.
    review = client.get(f"/v1/jobs/{job_id}/review", headers=_headers("chat-review"))
    reading = next(
        item for item in review.json()["packet"]["readings"] if item["id"] == WIDTH_READING_ID
    )
    assert reading["status"] == "proposed"
    assert reading["decision"] is None

    # 5. O ato humano é o comando que já existia, com o conteúdo do rascunho.
    decided = client.post(
        f"/v1/jobs/{job_id}/review/decisions",
        headers=_headers("chat-decision"),
        json={
            "base_version": review.json()["version"],
            "decisions": [
                {
                    "reading_id": draft["reading_id"],
                    "action": draft["action"],
                    "justification": draft["justification_draft"],
                    "association_proposal_id": draft["association_proposal_id"],
                }
            ],
        },
    )
    assert decided.status_code == 200
    confirmed = next(
        item for item in decided.json()["packet"]["readings"] if item["id"] == WIDTH_READING_ID
    )
    assert confirmed["status"] == "confirmed"
    # Quem assina é o profissional do JWT, nunca o agente.
    assert confirmed["decision"]["reviewer_id"] == "eng-chat"
    assert confirmed["decision"]["reviewer_role"] == "engineer"
    assert decided.json()["selected_associations"][WIDTH_READING_ID] == WIDTH_PROPOSAL_ID

    # 6. A conversa continua presa à revisão em que foi aberta, que não é mais a corrente.
    after = client.get(
        f"/v1/jobs/{job_id}/chat-sessions/{session_id}", headers=_headers("chat-poll-2")
    )
    assert after.json()["base_review_version"] == 1
    assert decided.json()["version"] == 2
