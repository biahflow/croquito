"""Logging estruturado em JSON (stdlib puro), uma linha por registro.

Todo log do processo (API e worker) vai para **stderr**: vários subcomandos do CLI do
worker imprimem o resultado em stdout, e log ali corromperia essa saída. `extra`
passado ao logger é promovido a chaves de topo; uma exceção anexada ao registro vira
somente `error.kind`/`error.message` — nunca o traceback com valores de variáveis
locais, que poderiam carregar conteúdo de cliente.
"""

from __future__ import annotations

import json
import logging
import logging.config
import os
from datetime import UTC, datetime
from typing import Any, Final

_RESERVED_RECORD_ATTRS: Final[frozenset[str]] = frozenset(
    logging.LogRecord(
        name="", level=0, pathname="", lineno=0, msg="", args=(), exc_info=None
    ).__dict__
)
"""Atributos que todo `LogRecord` já carrega — o resto de `record.__dict__` é `extra`."""

_CONFIGURED_ATTR: Final = "_croquito_json_logging_configured"


class JsonLogFormatter(logging.Formatter):
    """Formata cada registro como uma linha JSON: timestamp, level, logger, message
    e os campos de `extra` promovidos a chaves de topo."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key, value in record.__dict__.items():
            if key in _RESERVED_RECORD_ATTRS or key in payload:
                continue
            payload[key] = value
        if record.exc_info is not None:
            exc_type, exc_value, _traceback = record.exc_info
            payload["error"] = {
                "kind": exc_type.__name__ if exc_type is not None else "UnknownError",
                "message": str(exc_value) if exc_value is not None else "",
            }
        return json.dumps(payload, default=str, ensure_ascii=False)


def configure_logging(level: str = "INFO") -> None:
    """Configura o root logger para emitir uma linha JSON por registro em stderr.

    Idempotente: chamadas repetidas no mesmo processo (a suíte de testes instancia
    vários apps) não duplicam handler — a segunda chamada só ajusta o nível. Respeita
    `CROQUITO_LOG_LEVEL` quando setado, mesmo por cima do `level` recebido.
    """
    root = logging.getLogger()
    resolved_level = os.environ.get("CROQUITO_LOG_LEVEL", level).upper()
    if getattr(root, _CONFIGURED_ATTR, False):
        root.setLevel(resolved_level)
        return
    logging.config.dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {"json": {"()": JsonLogFormatter}},
            "handlers": {
                "croquito_stderr": {
                    "class": "logging.StreamHandler",
                    "formatter": "json",
                    "stream": "ext://sys.stderr",
                }
            },
            "root": {"level": resolved_level, "handlers": ["croquito_stderr"]},
        }
    )
    setattr(root, _CONFIGURED_ATTR, True)
