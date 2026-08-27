"""Testes de `scripts/bootstrap_local_aws.py`: guarda de endpoint e redrive da fila.

O módulo é carregado por caminho (não é um pacote importável), como em
`test_check_docs.py`, para não mexer em `sys.path` globalmente.

O que é coberto aqui é o que dói se estiver errado: provisionar contra um endpoint que
não é o emulador da máquina, e uma fila de processamento sem DLQ ligada. O resto do
script é chamada direta de API do emulador, exercida por `make db-init`.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_MODULE_PATH = _REPO_ROOT / "scripts" / "bootstrap_local_aws.py"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("bootstrap_local_aws", _MODULE_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


bootstrap = _load()


@pytest.mark.parametrize(
    "endpoint",
    [
        "http://127.0.0.1:4566",
        "http://localhost:4566",
        "http://host.docker.internal:4566",
    ],
)
def test_endpoint_local_e_aceito(endpoint: str) -> None:
    bootstrap._require_local_endpoint(endpoint)


@pytest.mark.parametrize(
    "endpoint",
    [
        "https://storage.googleapis.com",
        "https://s3.sa-east-1.amazonaws.com",
        "http://croquito-hml.biahflow.ai",
    ],
)
def test_endpoint_remoto_e_recusado(endpoint: str) -> None:
    """Storage de verdade nunca é provisionado por este script, nem por descuido de env."""
    with pytest.raises(bootstrap.NotLocalEndpointError):
        bootstrap._require_local_endpoint(endpoint)


def test_main_recusa_endpoint_remoto_sem_abrir_cliente(monkeypatch: pytest.MonkeyPatch) -> None:
    """A recusa vem ANTES do primeiro cliente: falhar depois já teria tocado o endpoint."""
    monkeypatch.setattr(bootstrap, "ENDPOINT", "https://storage.googleapis.com")

    def _proibido(service: str) -> Any:  # pragma: no cover - o teste falha se for chamado
        raise AssertionError(f"cliente {service} não deveria ser criado")

    monkeypatch.setattr(bootstrap, "_client", _proibido)
    assert bootstrap.main() == 2


class _SqsFake:
    """Emulador mínimo de SQS: só o que `_ensure_queues` usa."""

    def __init__(self, existentes: tuple[str, ...]) -> None:
        self.filas: dict[str, str] = {
            nome: f"http://local/000000000000/{nome}" for nome in existentes
        }
        self.atributos_definidos: dict[str, dict[str, str]] = {}
        self.criadas: list[tuple[str, dict[str, str]]] = []

    def get_queue_url(self, QueueName: str) -> dict[str, str]:
        if QueueName not in self.filas:
            from botocore.exceptions import ClientError

            raise ClientError(
                {"Error": {"Code": "AWS.SimpleQueueService.NonExistentQueue"}}, "GetQueueUrl"
            )
        return {"QueueUrl": self.filas[QueueName]}

    def create_queue(
        self, QueueName: str, Attributes: dict[str, str] | None = None
    ) -> dict[str, str]:
        self.filas[QueueName] = f"http://local/000000000000/{QueueName}"
        self.criadas.append((QueueName, Attributes or {}))
        return {"QueueUrl": self.filas[QueueName]}

    def get_queue_attributes(
        self, QueueUrl: str, AttributeNames: list[str]
    ) -> dict[str, dict[str, str]]:
        nome = QueueUrl.rsplit("/", 1)[-1]
        return {"Attributes": {"QueueArn": f"arn:aws:sqs:sa-east-1:000000000000:{nome}"}}

    def set_queue_attributes(self, QueueUrl: str, Attributes: dict[str, str]) -> None:
        self.atributos_definidos[QueueUrl.rsplit("/", 1)[-1]] = Attributes


def test_fila_nova_nasce_com_redrive_para_a_dlq() -> None:
    sqs = _SqsFake(existentes=())
    bootstrap._ensure_queues(sqs)
    criadas = dict(sqs.criadas)
    assert bootstrap.DLQ_QUEUE in criadas
    politica = json.loads(criadas[bootstrap.PROCESSING_QUEUE]["RedrivePolicy"])
    assert politica["deadLetterTargetArn"].endswith(bootstrap.DLQ_QUEUE)
    assert politica["maxReceiveCount"] == "5"


def test_fila_existente_tem_o_redrive_reafirmado() -> None:
    """Fila criada à mão sem DLQ reentregaria mensagem venenosa para sempre, em silêncio."""
    sqs = _SqsFake(existentes=(bootstrap.PROCESSING_QUEUE, bootstrap.DLQ_QUEUE))
    bootstrap._ensure_queues(sqs)
    assert sqs.criadas == []
    politica = json.loads(sqs.atributos_definidos[bootstrap.PROCESSING_QUEUE]["RedrivePolicy"])
    assert politica["deadLetterTargetArn"].endswith(bootstrap.DLQ_QUEUE)
