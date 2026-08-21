"""Envelope dos eventos de domínio: o que pode viajar e o que é recusado (F-031 T2)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from croquito_core.errors import DomainValidationError
from croquito_core.events import (
    DOMAIN_EVENT_TYPES,
    EVENT_AI_CALL_EXECUTED,
    EVENT_JOB_CREATED,
    build_domain_event,
)


def test_envelope_carrega_exatamente_os_campos_do_contrato() -> None:
    moment = datetime(2026, 8, 21, 12, 30, 45, tzinfo=UTC)

    envelope = build_domain_event(
        event_type=EVENT_JOB_CREATED,
        tenant_id="tenant-a",
        job_id="job-1",
        occurred_at=moment,
        payload={"project_id": "project-1", "stage": "VALIDATING", "status": "UPLOADED"},
    )

    assert set(envelope) == {
        "event_id",
        "event_type",
        "tenant_id",
        "occurred_at",
        "job_id",
        "payload",
    }
    assert envelope["event_type"] == "croquito.job.created.v1"
    assert envelope["occurred_at"] == "2026-08-21T12:30:45+00:00"
    assert envelope["job_id"] == "job-1"


def test_event_id_dado_e_reusado_para_que_a_reentrega_seja_deduplicavel() -> None:
    """O relay reconstrói o envelope da linha já gravada; o id precisa ser o MESMO.

    Entrega é at-least-once e o consumidor deduplica por `event_id`. Um id novo a cada
    reentrega faria a mesma mensagem contar duas vezes no portal — que é exatamente a
    métrica que a F-031 existe para não mentir.
    """
    moment = datetime.now(UTC)
    payload = {"provider": "anthropic", "model_id": "claude-x", "latency_ms": 12}

    primeiro = build_domain_event(
        event_id="evt-1",
        event_type=EVENT_AI_CALL_EXECUTED,
        tenant_id="tenant-a",
        occurred_at=moment,
        payload=payload,
    )
    segundo = build_domain_event(
        event_id="evt-1",
        event_type=EVENT_AI_CALL_EXECUTED,
        tenant_id="tenant-a",
        occurred_at=moment,
        payload=payload,
    )

    assert primeiro == segundo
    assert primeiro["event_id"] == "evt-1"


def test_event_id_ausente_nasce_novo_a_cada_evento() -> None:
    moment = datetime.now(UTC)
    payload = {"project_id": "project-1", "stage": "VALIDATING", "status": "UPLOADED"}

    primeiro = build_domain_event(
        event_type=EVENT_JOB_CREATED, tenant_id="t", occurred_at=moment, payload=payload
    )
    segundo = build_domain_event(
        event_type=EVENT_JOB_CREATED, tenant_id="t", occurred_at=moment, payload=payload
    )

    assert primeiro["event_id"] != segundo["event_id"]


@pytest.mark.parametrize(
    "proibido",
    [
        {"evidence": {"bbox": {"left": 1}}},
        {"readings": ["rd_1", "rd_2"]},
        {"preview": b"\x89PNG"},
    ],
)
def test_payload_aninhado_e_recusado_porque_e_a_forma_que_conteudo_tem(
    proibido: dict[str, object],
) -> None:
    """A conferência é de FORMA, não de lista de nomes proibidos.

    Recorte de imagem, texto de cota e resposta bruta chegam aninhados — um `dict`, uma
    lista, `bytes`. Bloquear a forma pega o vazamento antes de ele ter nome; uma lista de
    chaves proibidas só pegaria os nomes que alguém já imaginou.
    """
    with pytest.raises(DomainValidationError) as error:
        build_domain_event(
            event_type=EVENT_JOB_CREATED,
            tenant_id="tenant-a",
            occurred_at=datetime.now(UTC),
            payload=proibido,
        )

    assert "escalares" in str(error.value)


def test_tipo_fora_do_catalogo_e_recusado() -> None:
    with pytest.raises(DomainValidationError) as error:
        build_domain_event(
            event_type="croquito.job.inventado.v1",
            tenant_id="tenant-a",
            occurred_at=datetime.now(UTC),
            payload={},
        )

    assert "catálogo" in str(error.value)


def test_occurred_at_naive_e_recusado() -> None:
    """RFC 3339 UTC é o contrato; um instante sem fuso publicaria hora sem significado."""
    with pytest.raises(DomainValidationError) as error:
        build_domain_event(
            event_type=EVENT_JOB_CREATED,
            tenant_id="tenant-a",
            occurred_at=datetime(2026, 8, 21, 12, 0, 0),
            payload={},
        )

    assert "tz-aware" in str(error.value)


def test_catalogo_v1_tem_exatamente_os_treze_tipos_do_contrato() -> None:
    """`events-contract.md` é o que o portal implementa; a constante não pode divergir.

    Acrescentar tipo aqui sem acrescentá-lo ao documento publicaria mensagem que nenhum
    consumidor sabe ler; o inverso deixaria o documento prometendo o que não sai.
    """
    assert {
        "croquito.job.created.v1",
        "croquito.job.stage_changed.v1",
        "croquito.review.decisions_recorded.v1",
        "croquito.review.rectifications_recorded.v1",
        "croquito.review.proposals_decided.v1",
        "croquito.review.calibration_set.v1",
        "croquito.review.chains_declared.v1",
        "croquito.scene.approved.v1",
        "croquito.export.completed.v1",
        "croquito.export.failed.v1",
        "croquito.ai.call_executed.v1",
        "croquito.valuation.action_recorded.v1",
        "croquito.estimate.action_recorded.v1",
    } == DOMAIN_EVENT_TYPES
