"""O transporte Pub/Sub publica exatamente o que o transporte SQS publica."""

import hashlib
import json
from pathlib import Path
from typing import Any, cast

import pytest
from fastapi.testclient import TestClient
from google.api_core.exceptions import ServiceUnavailable

from croquito_api.config import ApiSettings
from croquito_api.database import Database
from croquito_api.main import ProcessingQueue, create_app
from croquito_api.pubsub_queue import PubSubProcessingQueue, QueuePublishError
from croquito_core.errors import DomainValidationError
from tests.fakes import FakeObjectStore, FakePublisher, FakeQueue, synthetic_pdf

TOPIC = "projects/croquito-hml/topics/processing"

# Um comando de cada tipo, com os mesmos argumentos nos dois adaptadores.
COMMANDS: list[tuple[str, dict[str, str]]] = [
    ("enqueue", {"job_id": "job-1", "tenant_id": "tenant-a"}),
    (
        "enqueue_export",
        {
            "export_id": "export-1",
            "job_id": "job-1",
            "tenant_id": "tenant-a",
            "scene_revision_id": "scene-1",
        },
    ),
    (
        "enqueue_trace_solve",
        {"trace_solve_id": "trace-1", "job_id": "job-1", "tenant_id": "tenant-a"},
    ),
    ("enqueue_chat_turn", {"chat_turn_id": "turn-1", "job_id": "job-1", "tenant_id": "tenant-a"}),
    (
        # A medição não tem `job_id` e nunca terá (ADR-0016); o envelope precisa ser
        # idêntico nos dois transportes justamente porque ele é diferente dos outros.
        "enqueue_valuation_plate_extraction",
        {"round_id": "round-1", "extraction_id": "extraction-1", "tenant_id": "tenant-a"},
    ),
]


def _settings(tmp_path: Path, *, pubsub_topic: str | None = None) -> ApiSettings:
    return ApiSettings(
        database_url=f"sqlite+pysqlite:///{tmp_path / 'api.db'}",
        artifact_bucket="croquito-test-artifacts",
        aws_region="sa-east-1",
        aws_endpoint_url="http://localhost:4566",
        queue_url=None,
        oidc_issuer=None,
        oidc_audience=None,
        web_origin="http://localhost:5173",
        allow_test_tokens=True,
        pubsub_topic=pubsub_topic,
    )


def test_pubsub_publishes_the_same_bodies_as_sqs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """O worker lê um único contrato de mensagem; a nuvem não pode mudar um byte dele."""
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "local")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "local")
    sqs_queue = ProcessingQueue(_settings(tmp_path))
    sqs_queue.queue_url = "http://localstack/queue"
    transport = FakeQueue()
    sqs_queue.client = transport
    publisher = FakePublisher()
    pubsub_queue = PubSubProcessingQueue(
        _settings(tmp_path, pubsub_topic=TOPIC), publisher=publisher
    )

    for method, arguments in COMMANDS:
        getattr(sqs_queue, method)(**arguments)
        getattr(pubsub_queue, method)(**arguments)

    published = [message["Body"].encode("utf-8") for message in transport.messages]
    assert published == publisher.bodies()
    assert [json.loads(body)["command"] for body in publisher.bodies()] == [
        "process_upload",
        "export_scene_package",
        "solve_trace_scene",
        "answer_chat_turn",
        "extract_valuation_plate",
    ]
    assert {topic for topic, _data in publisher.published} == {TOPIC}


def test_publisher_failures_become_queue_publish_error(tmp_path: Path) -> None:
    settings = _settings(tmp_path, pubsub_topic=TOPIC)
    on_publish = PubSubProcessingQueue(
        settings, publisher=FakePublisher(publish_failure=ServiceUnavailable("indisponível"))
    )
    on_result = PubSubProcessingQueue(
        settings, publisher=FakePublisher(result_failure=ServiceUnavailable("indisponível"))
    )
    on_timeout = PubSubProcessingQueue(
        settings, publisher=FakePublisher(result_failure=TimeoutError())
    )

    with pytest.raises(QueuePublishError):
        on_publish.enqueue(job_id="job-1", tenant_id="tenant-a")
    with pytest.raises(QueuePublishError):
        on_result.enqueue_export(
            export_id="export-1",
            job_id="job-1",
            tenant_id="tenant-a",
            scene_revision_id="scene-1",
        )
    with pytest.raises(QueuePublishError):
        on_timeout.enqueue_chat_turn(chat_turn_id="turn-1", job_id="job-1", tenant_id="tenant-a")


def test_pubsub_backend_requires_a_topic(tmp_path: Path) -> None:
    with pytest.raises(DomainValidationError):
        PubSubProcessingQueue(_settings(tmp_path))


def test_settings_derive_the_backend_from_the_topic(tmp_path: Path) -> None:
    assert _settings(tmp_path).queue_backend == "sqs"
    assert _settings(tmp_path, pubsub_topic=TOPIC).queue_backend == "pubsub"


def test_create_app_mounts_the_pubsub_adapter(tmp_path: Path) -> None:
    database = Database(f"sqlite+pysqlite:///{tmp_path / 'api.db'}")
    database.create_schema()

    application = create_app(settings=_settings(tmp_path, pubsub_topic=TOPIC), database=database)

    assert isinstance(application.state.queue, PubSubProcessingQueue)


def test_broken_pubsub_queue_answers_the_same_problem_as_sqs(tmp_path: Path) -> None:
    """A rota não conhece o transporte: fila fora do ar é sempre o mesmo problem+json."""
    database = Database(f"sqlite+pysqlite:///{tmp_path / 'api.db'}")
    database.create_schema()
    settings = _settings(tmp_path, pubsub_topic=TOPIC)
    application = create_app(settings=settings, database=database)
    application.state.artifact_store = FakeObjectStore()
    application.state.queue = PubSubProcessingQueue(
        settings, publisher=FakePublisher(result_failure=ServiceUnavailable("indisponível"))
    )
    client = TestClient(application)
    headers = {
        "Authorization": "Bearer test:tenant-a:reviewer:engineer",
        "Idempotency-Key": "pubsub-down",
    }
    pdf = synthetic_pdf()
    presign = client.post(
        "/v1/uploads/presign",
        headers=headers,
        json={
            "filename": "levantamento.pdf",
            "content_type": "application/pdf",
            "size_bytes": len(pdf),
            "sha256": hashlib.sha256(pdf).hexdigest(),
        },
    )
    assert presign.status_code == 200
    cast(FakeObjectStore, cast(Any, client.app).state.artifact_store).put_direct(
        object_key=presign.json()["object_key"], body=pdf
    )

    response = client.post(
        "/v1/jobs",
        headers={**headers, "Idempotency-Key": "pubsub-down-job"},
        json={"upload_id": presign.json()["upload_id"], "project_name": "Guaxindiba"},
    )

    assert response.status_code == 503
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["code"] == "PROCESSING_UNAVAILABLE"
