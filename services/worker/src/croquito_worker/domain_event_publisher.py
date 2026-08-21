"""Porta de publicação dos eventos de domínio e o relay que drena a outbox (ADR-0042).

A separação é a mesma que `ProcessingQueue`/`PubSubProcessingQueue` já usa para os
comandos internos: quem produz o evento não conhece o broker, e trocar de broker é
escrever outro adapter atrás desta porta — sem tocar em nenhum produtor.

Nada aqui é chamado do request path. A API e o worker só GRAVAM na outbox, na mesma
transação do fato; publicar é trabalho deste relay, executado fora da transação e fora
da resposta ao cliente.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

from sqlalchemy import DateTime, bindparam, text
from sqlalchemy.engine import Engine

from croquito_core.events import build_domain_event

#: Publicação síncrona: o relay só marca `published_at` depois que o broker confirmou.
PUBLISH_TIMEOUT_SECONDS = 10.0

#: Teto padrão de eventos por execução do relay; a próxima execução continua de onde parou.
DEFAULT_RELAY_LIMIT = 500


class DomainEventPublishError(RuntimeError):
    """O sink recusou o evento; ele continua pendente na outbox e será reentregue."""


class DomainEventPublisher(Protocol):
    """Superfície mínima de um sink de eventos: recebe o envelope pronto e o entrega."""

    def publish(self, envelope: Mapping[str, Any]) -> None: ...


class FileDomainEventPublisher:
    """Sink JSONL local, para demo e teste — nenhum byte sai da máquina.

    Abre e fecha o arquivo a cada evento de propósito: assim uma falha no meio do lote
    deixa em disco, já persistidas, exatamente as linhas dos eventos que o relay marcou
    como publicados. Um handle aberto com buffer poderia perder a última linha e fazer o
    arquivo discordar da coluna `published_at`.
    """

    def __init__(self, path: Path) -> None:
        self.path = path

    def publish(self, envelope: Mapping[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(envelope, ensure_ascii=False, sort_keys=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")


class PubSubPublishFuture(Protocol):
    """Futuro devolvido pelo publisher; só o resultado com timeout é usado aqui."""

    def result(self, timeout: float | None = ...) -> Any: ...


class PubSubClient(Protocol):
    """Superfície mínima do `PublisherClient`, para que o teste injete um dublê."""

    def publish(self, topic: str, data: bytes) -> PubSubPublishFuture: ...


class PubSubDomainEventPublisher:
    """Sink Pub/Sub no tópico dedicado dos eventos de domínio (`CROQUITO_DOMAIN_EVENTS_TOPIC`).

    O SDK do Google é importado DENTRO dos métodos, nunca no topo: o worker roda o
    pipeline inteiro sem Pub/Sub, e um import de módulo faria todo comando do
    `croquito-demo` pagar mais de um segundo de import a frio por um adapter que a maioria
    deles não usa. Construir o objeto também não abre conexão — o cliente nasce na
    primeira publicação, e um teste que injeta um dublê nunca toca a rede.
    """

    def __init__(self, topic: str, *, publisher: PubSubClient | None = None) -> None:
        if not topic:
            raise ValueError("CROQUITO_DOMAIN_EVENTS_TOPIC é obrigatório para o sink pubsub.")
        self.topic = topic
        self._publisher = publisher

    def _client(self) -> PubSubClient:
        if self._publisher is None:
            from google.cloud import pubsub_v1

            client: PubSubClient = pubsub_v1.PublisherClient()
            self._publisher = client
        return self._publisher

    def publish(self, envelope: Mapping[str, Any]) -> None:
        from google.api_core.exceptions import GoogleAPIError

        data = json.dumps(envelope, ensure_ascii=False, sort_keys=True).encode("utf-8")
        try:
            future = self._client().publish(self.topic, data)
            future.result(timeout=PUBLISH_TIMEOUT_SECONDS)
        except (GoogleAPIError, TimeoutError) as error:
            raise DomainEventPublishError("Tópico de eventos indisponível.") from error


@dataclass(frozen=True, slots=True)
class RelayResult:
    published: int
    remaining: int


def _as_utc(value: datetime) -> datetime:
    """Reancora em UTC o instante que o SQLite devolve naive.

    O `bind_processor` do `DATETIME` do SQLite descarta o offset na gravação, então o
    valor volta sem tzinfo mesmo tendo sido gravado em UTC pelos dois escritores (API por
    ORM, worker por SQL cru). No PostgreSQL a coluna é `timestamptz` e já volta aware.
    """
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


#: `.columns(nome=tipo)` casa por NOME. A forma posicional casaria a única coluna
#: declarada com a PRIMEIRA do `SELECT` (`id`), e o `result_processor` de data tentaria
#: converter o identificador em `datetime` — falha barulhenta que já aconteceu aqui.
#: Sem declaração nenhuma, o SQLite devolveria `occurred_at` como a string gravada.
_PENDING_QUERY = text(
    "SELECT id, tenant_id, event_type, job_id, occurred_at, payload_json "
    "FROM domain_events WHERE published_at IS NULL ORDER BY created_at, id LIMIT :limit"
).columns(occurred_at=DateTime(timezone=True))

_MARK_PUBLISHED = text(
    "UPDATE domain_events SET published_at = :published_at WHERE id = :id AND published_at IS NULL"
).bindparams(bindparam("published_at", type_=DateTime(timezone=True)))

_PENDING_COUNT = text("SELECT COUNT(*) FROM domain_events WHERE published_at IS NULL")


def pending_domain_events(engine: Engine, *, limit: int) -> Sequence[dict[str, Any]]:
    """Os envelopes ainda não publicados, em ordem de gravação.

    O envelope é RECONSTRUÍDO a partir das colunas, e o `event_id` reusa o `id` da linha:
    reentrega precisa repetir o mesmo identificador, senão o consumidor não tem como
    deduplicar o que a entrega at-least-once vai repetir.
    """
    with engine.connect() as connection:
        rows = connection.execute(_PENDING_QUERY, {"limit": limit}).mappings().all()
    envelopes: list[dict[str, Any]] = []
    for row in rows:
        payload = row["payload_json"]
        envelopes.append(
            build_domain_event(
                event_id=row["id"],
                event_type=row["event_type"],
                tenant_id=row["tenant_id"],
                job_id=row["job_id"],
                occurred_at=_as_utc(row["occurred_at"]),
                # SQL cru devolve JSON como texto no SQLite e como estrutura no PostgreSQL.
                payload=json.loads(payload) if isinstance(payload, str) else payload,
            )
        )
    return envelopes


def drain_domain_events(
    engine: Engine,
    publisher: DomainEventPublisher,
    *,
    limit: int = DEFAULT_RELAY_LIMIT,
) -> RelayResult:
    """Publica os eventos pendentes e marca cada um DEPOIS de publicá-lo.

    A ordem importa e é a única garantia real desta fatia: marcar antes perderia o evento
    numa falha do sink, e marcar o lote inteiro no fim republicaria tudo o que já saiu. Um
    a um, uma falha no meio deixa os anteriores marcados, o que falhou e os seguintes
    pendentes, e a próxima execução continua exatamente dali.

    Sem retry próprio de propósito (fatia 1): a exceção do adapter interrompe o relay, e a
    reentrega natural — rodar o comando de novo — é o mecanismo de recuperação. Duplicata
    é o modo de falha aceito (at-least-once); o consumidor deduplica por `event_id`.
    """
    published = 0
    for envelope in pending_domain_events(engine, limit=limit):
        publisher.publish(envelope)
        with engine.begin() as connection:
            connection.execute(
                _MARK_PUBLISHED,
                {"id": envelope["event_id"], "published_at": datetime.now(UTC)},
            )
        published += 1
    with engine.connect() as connection:
        remaining = int(connection.execute(_PENDING_COUNT).scalar_one())
    return RelayResult(published=published, remaining=remaining)
