"""Envelope e catálogo dos eventos de domínio publicados para fora (F-031, ADR-0042).

Este módulo é o único lugar onde o formato do envelope existe em código. Ele NÃO faz I/O
e não conhece banco, fila nem HTTP: quem grava a outbox é a API/o worker, quem publica é
o relay. Aqui mora só a montagem e a conferência do que pode viajar.

A regra dura é a política de logs do repositório aplicada ao payload: ele carrega apenas
IDs opacos, stage, durações, status, códigos de erro estáveis, model ID, tokens, custo e
contagens. Nunca imagem, texto de cota, conteúdo de documento, token de autenticação ou
URL assinada. `build_domain_event` recusa qualquer valor que não seja escalar ou `None`
justamente porque conteúdo quase sempre chega aninhado (um `dict` de recorte, uma lista
de leituras) — bloquear a FORMA é o que impede o vazamento antes de ele ter nome.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Any, Final

from croquito_core.errors import DomainValidationError
from croquito_core.ids import new_uuid7

EVENT_JOB_CREATED: Final = "croquito.job.created.v1"
EVENT_JOB_STAGE_CHANGED: Final = "croquito.job.stage_changed.v1"
EVENT_REVIEW_DECISIONS_RECORDED: Final = "croquito.review.decisions_recorded.v1"
EVENT_REVIEW_RECTIFICATIONS_RECORDED: Final = "croquito.review.rectifications_recorded.v1"
EVENT_REVIEW_PROPOSALS_DECIDED: Final = "croquito.review.proposals_decided.v1"
EVENT_REVIEW_CALIBRATION_SET: Final = "croquito.review.calibration_set.v1"
EVENT_REVIEW_CHAINS_DECLARED: Final = "croquito.review.chains_declared.v1"
EVENT_SCENE_APPROVED: Final = "croquito.scene.approved.v1"
EVENT_EXPORT_COMPLETED: Final = "croquito.export.completed.v1"
EVENT_EXPORT_FAILED: Final = "croquito.export.failed.v1"
EVENT_AI_CALL_EXECUTED: Final = "croquito.ai.call_executed.v1"
EVENT_VALUATION_ACTION_RECORDED: Final = "croquito.valuation.action_recorded.v1"
EVENT_ESTIMATE_ACTION_RECORDED: Final = "croquito.estimate.action_recorded.v1"

DOMAIN_EVENT_TYPES: Final[frozenset[str]] = frozenset(
    {
        EVENT_JOB_CREATED,
        EVENT_JOB_STAGE_CHANGED,
        EVENT_REVIEW_DECISIONS_RECORDED,
        EVENT_REVIEW_RECTIFICATIONS_RECORDED,
        EVENT_REVIEW_PROPOSALS_DECIDED,
        EVENT_REVIEW_CALIBRATION_SET,
        EVENT_REVIEW_CHAINS_DECLARED,
        EVENT_SCENE_APPROVED,
        EVENT_EXPORT_COMPLETED,
        EVENT_EXPORT_FAILED,
        EVENT_AI_CALL_EXECUTED,
        EVENT_VALUATION_ACTION_RECORDED,
        EVENT_ESTIMATE_ACTION_RECORDED,
    }
)
"""Catálogo v1 fechado, espelho de `docs/features/F-031-value-events/events-contract.md`.

Fechado de propósito: um tipo novo é mudança de contrato de consumo para o portal, e
inventá-lo no sítio de emissão publicaria uma mensagem que nenhum consumidor sabe ler.
"""

#: Chave do payload aceita: identificador curto, minúsculo, sem espaço.
_MAX_KEY_LENGTH: Final = 64

#: Valor escalar aceito no payload. `bool` é subclasse de `int` e entra por ele.
PayloadValue = str | int | float | bool | None


def _reject(errors: list[str]) -> None:
    if errors:
        raise DomainValidationError(errors)


def validate_payload(payload: Mapping[str, Any]) -> dict[str, PayloadValue]:
    """Devolve o payload conferido, ou levanta com TODOS os problemas de uma vez.

    A conferência é de forma, não de semântica: nenhuma lista de chaves proibidas seria
    completa, e caçar nome de chave daria falsa segurança. O que se prova aqui é que nada
    aninhado (`dict`, `list`, `bytes`) atravessa — é essa a forma que conteúdo tem.
    """
    errors: list[str] = []
    checked: dict[str, PayloadValue] = {}
    for key, value in payload.items():
        if not isinstance(key, str) or not key or len(key) > _MAX_KEY_LENGTH:
            errors.append(f"chave de payload inválida: {key!r}")
            continue
        if value is None or isinstance(value, str | int | float | bool):
            checked[key] = value
            continue
        errors.append(
            f"payload de evento aceita só escalares ou None; {key!r} veio como "
            f"{type(value).__name__}"
        )
    _reject(errors)
    return checked


def build_domain_event(
    *,
    event_type: str,
    tenant_id: str,
    occurred_at: datetime,
    payload: Mapping[str, Any],
    job_id: str | None = None,
    event_id: str | None = None,
) -> dict[str, Any]:
    """Monta o envelope v1 do contrato de consumo, conferindo o que pode viajar.

    `event_id` é aceito para que o relay reconstrua o MESMO envelope a partir da linha já
    gravada na outbox: reentrega precisa repetir o id, senão o consumidor não deduplica.
    Ausente, nasce um UUIDv7 novo — a ordem temporal do id acompanha a da gravação.
    """
    errors: list[str] = []
    if event_type not in DOMAIN_EVENT_TYPES:
        errors.append(f"event_type fora do catálogo v1: {event_type!r}")
    if not tenant_id:
        errors.append("tenant_id é obrigatório no envelope")
    if occurred_at.tzinfo is None:
        errors.append("occurred_at precisa ser tz-aware; o contrato publica RFC 3339 UTC")
    _reject(errors)
    return {
        "event_id": event_id or str(new_uuid7()),
        "event_type": event_type,
        "tenant_id": tenant_id,
        "occurred_at": occurred_at.isoformat(),
        "job_id": job_id,
        "payload": validate_payload(payload),
    }
