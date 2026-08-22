"""Porta de publicação e relay idempotente da outbox de eventos (F-031 T2, ADR-0042)."""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import create_engine, text

from croquito_api.database import Database, DomainEventRecord
from croquito_core.events import EVENT_AI_CALL_EXECUTED, EVENT_JOB_CREATED
from croquito_worker.domain_event_publisher import (
    DomainEventPublishError,
    FileDomainEventPublisher,
    PubSubDomainEventPublisher,
    drain_domain_events,
)


class _RecordingPublisher:
    """Sink em memória que pode ser mandado falhar no N-ésimo evento."""

    def __init__(self, *, fail_at: int | None = None) -> None:
        self.published: list[dict[str, Any]] = []
        self.fail_at = fail_at

    def publish(self, envelope: Mapping[str, Any]) -> None:
        if self.fail_at is not None and len(self.published) == self.fail_at:
            raise DomainEventPublishError("sink indisponível (simulado)")
        self.published.append(dict(envelope))


def _seeded_database(tmp_path: Path, *, events: int = 3) -> tuple[Database, str]:
    database_url = f"sqlite+pysqlite:///{tmp_path / 'outbox.db'}"
    database = Database(database_url)
    database.create_schema()
    base = datetime(2026, 8, 21, 10, 0, 0, tzinfo=UTC)
    with database.sessions.begin() as session:
        for position in range(events):
            session.add(
                DomainEventRecord(
                    id=f"evt-{position}",
                    tenant_id="tenant-a",
                    event_type=EVENT_JOB_CREATED,
                    job_id=f"job-{position}",
                    occurred_at=base,
                    payload_json={
                        "project_id": f"project-{position}",
                        "stage": "VALIDATING",
                        "status": "UPLOADED",
                    },
                    created_at=base,
                )
            )
    return database, database_url


def test_relay_publica_pendentes_marca_e_a_reexecucao_publica_zero(tmp_path: Path) -> None:
    database, database_url = _seeded_database(tmp_path)
    engine = create_engine(database_url)
    publisher = _RecordingPublisher()

    first = drain_domain_events(engine, publisher)
    second = drain_domain_events(engine, publisher)

    assert (first.published, first.remaining) == (3, 0)
    # Reexecução não republica: `published_at` já marcado é o que a varredura ignora.
    assert (second.published, second.remaining) == (0, 0)
    assert len(publisher.published) == 3
    assert [envelope["event_id"] for envelope in publisher.published] == [
        "evt-0",
        "evt-1",
        "evt-2",
    ]
    with database.sessions() as session:
        assert all(
            event.published_at is not None for event in session.query(DomainEventRecord).all()
        )
    engine.dispose()


def test_falha_no_meio_do_lote_deixa_marcados_so_os_ja_publicados(tmp_path: Path) -> None:
    """A marca vem DEPOIS da publicação, um a um — é a única garantia real desta fatia.

    Marcar antes perderia o evento na falha do sink; marcar o lote inteiro no fim
    republicaria tudo o que já saiu na próxima execução. Este teste prova o meio-termo:
    o que saiu fica marcado, o que falhou e os seguintes continuam pendentes, e a
    continuação retoma exatamente dali.
    """
    database, database_url = _seeded_database(tmp_path)
    engine = create_engine(database_url)
    falhando = _RecordingPublisher(fail_at=2)

    with pytest.raises(DomainEventPublishError):
        drain_domain_events(engine, falhando)

    with database.sessions() as session:
        marcados = {
            event.id
            for event in session.query(DomainEventRecord).all()
            if event.published_at is not None
        }
    assert marcados == {"evt-0", "evt-1"}

    retomada = _RecordingPublisher()
    result = drain_domain_events(engine, retomada)

    assert (result.published, result.remaining) == (1, 0)
    assert [envelope["event_id"] for envelope in retomada.published] == ["evt-2"]
    engine.dispose()


def test_limite_por_execucao_deixa_o_resto_pendente(tmp_path: Path) -> None:
    _database, database_url = _seeded_database(tmp_path)
    engine = create_engine(database_url)
    publisher = _RecordingPublisher()

    result = drain_domain_events(engine, publisher, limit=2)

    assert (result.published, result.remaining) == (2, 1)
    engine.dispose()


def test_sink_de_arquivo_grava_um_envelope_por_linha(tmp_path: Path) -> None:
    _database, database_url = _seeded_database(tmp_path, events=2)
    engine = create_engine(database_url)
    destino = tmp_path / "eventos" / "out.jsonl"

    result = drain_domain_events(engine, FileDomainEventPublisher(destino))

    assert result.published == 2
    linhas = destino.read_text(encoding="utf-8").splitlines()
    assert len(linhas) == 2
    primeiro = json.loads(linhas[0])
    assert primeiro["event_id"] == "evt-0"
    assert primeiro["event_type"] == "croquito.job.created.v1"
    assert primeiro["payload"]["project_id"] == "project-0"
    engine.dispose()


def test_envelope_reconstruido_preserva_o_instante_gravado(tmp_path: Path) -> None:
    """`occurred_at` sai RFC 3339 UTC mesmo vindo naive do SQLite.

    O `bind_processor` do dialeto descarta o offset ao gravar; publicar o valor cru faria
    o consumidor receber hora sem fuso e datar o fato onde quisesse.
    """
    _database, database_url = _seeded_database(tmp_path, events=1)
    engine = create_engine(database_url)
    publisher = _RecordingPublisher()

    drain_domain_events(engine, publisher)

    assert publisher.published[0]["occurred_at"] == "2026-08-21T10:00:00+00:00"
    engine.dispose()


def test_payload_com_chave_proibida_nao_e_publicado(tmp_path: Path) -> None:
    """Linha com conteúdo aninhado na outbox não vira mensagem: o relay recusa antes.

    A gravação já é conferida na origem, mas o relay é a última fronteira antes do
    barramento — e é a única que ainda existe se alguém, um dia, inserir na tabela por
    fora dos produtores.
    """
    database_url = f"sqlite+pysqlite:///{tmp_path / 'sujo.db'}"
    database = Database(database_url)
    database.create_schema()
    with database.sessions.begin() as session:
        session.add(
            DomainEventRecord(
                id="evt-sujo",
                tenant_id="tenant-a",
                event_type=EVENT_AI_CALL_EXECUTED,
                job_id="job-1",
                occurred_at=datetime.now(UTC),
                payload_json={"provider": "anthropic", "evidence": {"raw_text": "25,90"}},
            )
        )
    engine = create_engine(database_url)

    with pytest.raises(Exception, match="escalares"):
        drain_domain_events(engine, _RecordingPublisher())

    with engine.connect() as connection:
        pendentes = connection.execute(
            text("SELECT COUNT(*) FROM domain_events WHERE published_at IS NULL")
        ).scalar_one()
    assert pendentes == 1
    engine.dispose()


class _FakeFuture:
    def result(self, timeout: float | None = None) -> None:
        return None


class _FakePubSubClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, bytes]] = []

    def publish(self, topic: str, data: bytes) -> _FakeFuture:
        self.calls.append((topic, data))
        return _FakeFuture()


def test_adapter_pubsub_publica_o_envelope_sem_tocar_a_rede() -> None:
    """Cliente injetado: nenhum teste desta suíte fala com o GCP."""
    client = _FakePubSubClient()
    publisher = PubSubDomainEventPublisher("projects/p/topics/eventos", publisher=client)

    publisher.publish({"event_id": "evt-1", "event_type": "croquito.job.created.v1"})

    topic, data = client.calls[0]
    assert topic == "projects/p/topics/eventos"
    assert json.loads(data.decode("utf-8"))["event_id"] == "evt-1"


def test_adapter_pubsub_sem_topico_recusa_na_construcao() -> None:
    with pytest.raises(ValueError, match="CROQUITO_DOMAIN_EVENTS_TOPIC"):
        PubSubDomainEventPublisher("")


def test_falha_do_broker_vira_erro_de_publicacao_e_nao_vaza_o_sdk() -> None:
    """O relay lida com UM erro; deixar o erro do SDK subir acoplaria o CLI ao Google."""
    from google.api_core.exceptions import ServiceUnavailable

    class _BrokenClient:
        def publish(self, topic: str, data: bytes) -> _FakeFuture:
            raise ServiceUnavailable("tópico fora do ar")

    publisher = PubSubDomainEventPublisher("projects/p/topics/eventos", publisher=_BrokenClient())

    with pytest.raises(DomainEventPublishError):
        publisher.publish({"event_id": "evt-1"})
