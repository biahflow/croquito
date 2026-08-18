"""Transporte Pub/Sub dos mesmos comandos de processamento publicados no SQS.

O corpo publicado é byte-idêntico ao do adaptador SQS: o worker lê um único contrato de
mensagem, qualquer que seja a nuvem. Este é o único módulo que importa o SDK do Google.
"""

from __future__ import annotations

import json
from typing import Any, Protocol

from google.api_core.exceptions import GoogleAPIError

from croquito_api.config import ApiSettings
from croquito_core.errors import DomainValidationError

#: Publicação é síncrona: a rota só responde depois que o comando está durável na fila.
PUBLISH_TIMEOUT_SECONDS = 10.0


class QueuePublishError(Exception):
    """A fila não aceitou o comando; a intenção já está persistida e pode ser repetida."""

    def __init__(self, message: str = "Fila de processamento indisponível.") -> None:
        super().__init__(message)


class PublishFuture(Protocol):
    """Futuro devolvido pelo publisher; só o resultado com timeout é usado aqui."""

    def result(self, timeout: float | None = ...) -> Any: ...


class Publisher(Protocol):
    """Superfície mínima do `PublisherClient`, para que o teste injete um dublê."""

    def publish(self, topic: str, data: bytes) -> PublishFuture: ...


def _build_publisher() -> Publisher:
    """Cria o cliente real.

    O import mora aqui dentro de propósito: o SDK do Pub/Sub custa mais de um segundo de
    import a frio, e o deploy SQS não deve pagá-lo. Nenhum outro módulo importa
    `google.cloud`.
    """
    from google.cloud import pubsub_v1

    publisher: Publisher = pubsub_v1.PublisherClient()
    return publisher


class PubSubProcessingQueue:
    """Adaptador Pub/Sub com os mesmos comandos do `ProcessingQueue`; falha fechado."""

    def __init__(self, settings: ApiSettings, *, publisher: Publisher | None = None) -> None:
        if not settings.pubsub_topic:
            raise DomainValidationError(
                ["CROQUITO_PUBSUB_TOPIC é obrigatório quando a fila é Pub/Sub."]
            )
        self.topic = settings.pubsub_topic
        self._publisher = publisher

    def _client(self) -> Publisher:
        """Constrói o cliente só na primeira publicação; subir a app não depende da fila."""
        if self._publisher is None:
            self._publisher = _build_publisher()
        return self._publisher

    def _publish(self, body: dict[str, Any]) -> None:
        # `json.dumps` com os separadores padrão: mesmo corpo, byte a byte, do SQS.
        data = json.dumps(body).encode("utf-8")
        try:
            future = self._client().publish(self.topic, data)
            future.result(timeout=PUBLISH_TIMEOUT_SECONDS)
        except (GoogleAPIError, TimeoutError) as error:
            raise QueuePublishError() from error

    def enqueue(self, *, job_id: str, tenant_id: str) -> None:
        self._publish(
            {
                "command": "process_upload",
                "job_id": job_id,
                "tenant_id": tenant_id,
                "stage": "VALIDATING",
            }
        )

    def enqueue_export(
        self, *, export_id: str, job_id: str, tenant_id: str, scene_revision_id: str
    ) -> None:
        """Publishes the export intent; the CAD package is always built outside the request."""
        self._publish(
            {
                "command": "export_scene_package",
                "export_id": export_id,
                "job_id": job_id,
                "tenant_id": tenant_id,
                "scene_revision_id": scene_revision_id,
            }
        )

    def enqueue_trace_solve(self, *, trace_solve_id: str, job_id: str, tenant_id: str) -> None:
        """Publishes the trace intent; the geometry solver never runs in the request path."""
        self._publish(
            {
                "command": "solve_trace_scene",
                "trace_solve_id": trace_solve_id,
                "job_id": job_id,
                "tenant_id": tenant_id,
            }
        )

    def enqueue_valuation_plate_extraction(
        self, *, round_id: str, extraction_id: str, tenant_id: str
    ) -> None:
        """Publica a extração paga da legenda; o corpo é o mesmo do SQS, byte a byte."""
        self._publish(
            {
                "command": "extract_valuation_plate",
                "round_id": round_id,
                "extraction_id": extraction_id,
                "tenant_id": tenant_id,
            }
        )

    def enqueue_takeoff_overlay_rerender(
        self, *, round_id: str, tenant_id: str, packet_sha256: str
    ) -> None:
        """Publica o re-render do overlay do takeoff; o corpo é o mesmo do SQS, byte a byte."""
        self._publish(
            {
                "command": "rerender_takeoff_overlay",
                "round_id": round_id,
                "tenant_id": tenant_id,
                "packet_sha256": packet_sha256,
            }
        )

    def enqueue_chat_turn(self, *, chat_turn_id: str, job_id: str, tenant_id: str) -> None:
        """Publishes the chat turn; no model is ever called from the request path."""
        self._publish(
            {
                "command": "answer_chat_turn",
                "chat_turn_id": chat_turn_id,
                "job_id": job_id,
                "tenant_id": tenant_id,
            }
        )
