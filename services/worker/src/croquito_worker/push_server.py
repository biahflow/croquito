"""Transporte HTTP push do Pub/Sub para o mesmo despacho do consumidor SQS.

O worker não muda de comportamento por causa do transporte: a rota decodifica o envelope,
entrega o corpo a `LocalQueueWorker.dispatch` e traduz o desfecho em código HTTP. Toda a
lógica de idempotência, claim e recusa continua nos handlers.

Autenticação: **não** há verificação de token aqui de propósito. A assinatura do push é
verificada pela IAM do Cloud Run (`roles/run.invoker` na conta de serviço da subscription),
antes de a requisição chegar ao processo; validar o mesmo token de novo aqui seria uma
segunda fonte de verdade sobre quem pode chamar. O serviço nunca deve ser publicado com
invocação anônima.

Códigos de retorno, e por quê:

- `204` — comando executado, o Pub/Sub pode dar ack.
- `200` — envelope, base64, JSON ou comando inválidos. Reentregar não muda o resultado, e
  um payload-veneno reentregue para sempre é um ciclo caro; o descarte fica no log, com id
  opaco e código de motivo, nunca o conteúdo.
- `500` — falha ao executar um comando legítimo (banco, storage, provider). O Pub/Sub
  reentrega, que é exatamente a política que o consumidor SQS já tinha ao não apagar a
  mensagem.
"""

from __future__ import annotations

import base64
import json
import logging
import os
from typing import Any

import uvicorn
from fastapi import FastAPI, Request, Response, status
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, Field

from croquito_worker.local_queue import (
    LocalQueueWorker,
    LocalWorkerSettings,
    UnroutableMessageError,
)
from croquito_worker.providers import ProviderSuite

logger = logging.getLogger("croquito_worker.push")


class PushMessage(BaseModel):
    """Mensagem do envelope push. Campos extras do Pub/Sub são ignorados de propósito."""

    data: str
    # Só observabilidade: um envelope sem id ainda carrega um comando válido, e derrubá-lo
    # perderia trabalho de verdade por causa de um campo de log.
    message_id: str = Field(default="", alias="messageId")


class PushEnvelope(BaseModel):
    message: PushMessage
    subscription: str = ""


def _drop(*, reason: str, message_id: str, subscription: str) -> Response:
    """Descarta a entrega e registra o motivo.

    Só saem o código do motivo e identificadores opacos — nunca o corpo da mensagem. Os
    dois identificadores vêm do corpo da requisição e são formatados com `%r` para que
    quebra de linha não possa forjar uma linha de log; os mesmos campos vão em `extra`
    para quem coleta log estruturado.
    """
    logger.warning(
        "push_message_dropped reason=%s message_id=%r subscription=%r",
        reason,
        message_id,
        subscription,
        extra={
            "reason": reason,
            "message_id": message_id,
            "subscription": subscription,
        },
    )
    return Response(status_code=status.HTTP_200_OK)


def create_push_app(
    settings: LocalWorkerSettings | None = None,
    *,
    provider_suite: ProviderSuite | None = None,
) -> FastAPI:
    """Monta o receptor push sobre um `LocalQueueWorker` compartilhado pelo processo."""
    runtime_settings = settings or LocalWorkerSettings.from_environment(require_queue=False)
    # Um worker por processo: o engine tem pool próprio e os clients são criados sob
    # demanda. A rota é síncrona, então o Starlette a executa no threadpool e o
    # healthcheck continua respondendo enquanto um comando longo roda.
    worker = LocalQueueWorker(runtime_settings, provider_suite=provider_suite)
    application = FastAPI(
        title="Croquito worker push",
        version="0.1.0",
        description="Recebe comandos do Pub/Sub e os despacha para o worker.",
    )
    application.state.worker = worker

    @application.exception_handler(RequestValidationError)
    async def invalid_envelope(_request: Request, _error: RequestValidationError) -> Response:
        return _drop(reason="INVALID_ENVELOPE", message_id="", subscription="")

    @application.get("/healthz", include_in_schema=False)
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @application.post("/pubsub", include_in_schema=False)
    def receive_push(envelope: PushEnvelope) -> Response:
        try:
            payload = base64.b64decode(envelope.message.data, validate=True)
            # `binascii.Error` do base64 também é `ValueError`, como o erro do JSON.
            body: Any = json.loads(payload)
        except ValueError:
            return _drop(
                reason="INVALID_PAYLOAD",
                message_id=envelope.message.message_id,
                subscription=envelope.subscription,
            )
        if not isinstance(body, dict):
            return _drop(
                reason="INVALID_PAYLOAD",
                message_id=envelope.message.message_id,
                subscription=envelope.subscription,
            )
        try:
            worker.dispatch(body)
        except UnroutableMessageError:
            return _drop(
                reason="UNROUTABLE_COMMAND",
                message_id=envelope.message.message_id,
                subscription=envelope.subscription,
            )
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    return application


def main() -> None:
    """Sobe o receptor na porta que o Cloud Run injeta."""
    uvicorn.run(
        create_push_app(),
        # O container só é alcançável pelo proxy do Cloud Run; o bind aberto é exigência
        # da plataforma, não exposição do processo.
        host="0.0.0.0",
        port=int(os.environ.get("PORT", "8080")),
        log_level="info",
    )
