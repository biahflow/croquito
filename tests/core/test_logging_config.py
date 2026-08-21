"""Logging estruturado (F-031 T5): uma linha JSON por registro, extra promovido,
exceção sem stack de variáveis e configuração idempotente."""

from __future__ import annotations

import io
import json
import logging

import pytest

from croquito_core.logging_config import JsonLogFormatter, configure_logging


def _handler_with_formatter(stream: io.StringIO) -> logging.StreamHandler[io.StringIO]:
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonLogFormatter())
    return handler


def test_formatter_emits_valid_json_with_extra_promoted_to_top_level_keys() -> None:
    stream = io.StringIO()
    logger = logging.getLogger("croquito.tests.formatter.extra")
    logger.setLevel(logging.INFO)
    logger.propagate = False
    logger.addHandler(_handler_with_formatter(stream))

    logger.info("request_completed", extra={"request_id": "req-1", "duration_ms": 12.5})

    line = stream.getvalue().strip()
    payload = json.loads(line)
    assert payload["message"] == "request_completed"
    assert payload["logger"] == "croquito.tests.formatter.extra"
    assert payload["level"] == "INFO"
    assert "timestamp" in payload
    assert payload["request_id"] == "req-1"
    assert payload["duration_ms"] == 12.5


def test_formatter_on_exception_carries_error_kind_and_message_without_local_variables() -> None:
    stream = io.StringIO()
    logger = logging.getLogger("croquito.tests.formatter.exception")
    logger.setLevel(logging.ERROR)
    logger.propagate = False
    logger.addHandler(_handler_with_formatter(stream))

    sensitive_local_value = "cota-confidencial-42m"
    try:
        raise ValueError("job inválido")
    except ValueError:
        logger.exception("job_failed", extra={"job_id": "job-1"})

    line = stream.getvalue().strip()
    payload = json.loads(line)
    assert payload["error"] == {"kind": "ValueError", "message": "job inválido"}
    assert payload["job_id"] == "job-1"
    # A linha inteira nunca carrega o valor de uma variável local do frame que falhou —
    # só tipo e mensagem da exceção, nunca o stack formatado.
    assert sensitive_local_value not in line
    assert "Traceback" not in line


def test_configure_logging_called_twice_does_not_duplicate_handlers_or_lines(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("CROQUITO_LOG_LEVEL", raising=False)
    configure_logging()
    root = logging.getLogger()
    handlers_after_first_call = list(root.handlers)

    configure_logging()

    assert root.handlers == handlers_after_first_call
    # Conta só o nosso handler pelo formatter — pytest também injeta um StreamHandler
    # próprio (`LogCaptureHandler`) durante a execução do teste, e não é ele que a
    # idempotência precisa vigiar.
    json_handlers = [h for h in root.handlers if isinstance(h.formatter, JsonLogFormatter)]
    assert len(json_handlers) == 1
