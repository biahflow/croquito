"""Correção declarada de decisão de leitura: sucessão registrada, nunca sobrescrita."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from pydantic import ValidationError

from croquito_worker.review import (
    RECTIFICATION_SAFETY_NOTE,
    HumanDecision,
    ReadingDecisionBatch,
    ReadingDecisionInput,
    ReadingRectificationBatch,
    ReadingRectificationInput,
    ReadingStatus,
    ReviewPacket,
    apply_reading_decisions,
    rectify_reading_decisions,
)
from tests.bundles import HEIGHT_READING_ID, WIDTH_READING_ID, build_packet

DATASET = "golden-local-v1"
DIGEST = "b" * 64
DECIDED_AT = datetime(2026, 8, 13, 12, 0, tzinfo=UTC)


def _proposed_packet() -> ReviewPacket:
    return build_packet(dataset_id=DATASET, digest=DIGEST)


def _decision(reading_id: str, **overrides: object) -> ReadingDecisionInput:
    payload: dict[str, object] = {
        "reading_id": reading_id,
        "action": "confirm",
        "reviewer_id": "reviewer",
        "reviewer_role": "engineer",
        "decided_at": DECIDED_AT,
        "note": "Conferido na evidência protegida.",
    }
    payload.update(overrides)
    return ReadingDecisionInput.model_validate(payload)


def _confirmed_packet(**overrides: object) -> ReviewPacket:
    """Pacote com a largura confirmada — o estado real antes de qualquer correção."""
    return apply_reading_decisions(
        _proposed_packet(),
        ReadingDecisionBatch(decisions=[_decision(WIDTH_READING_ID, **overrides)]),
    )


def _rectification(
    reading_id: str, *, target: str, **overrides: object
) -> ReadingRectificationInput:
    payload: dict[str, object] = {
        "reading_id": reading_id,
        "action": "confirm",
        "rectifies_decision_id": target,
        "reviewer_id": "reviewer",
        "reviewer_role": "engineer",
        "decided_at": datetime(2026, 8, 13, 15, 30, tzinfo=UTC),
        "note": "Eixo trocado na leitura original; corrigido contra a folha.",
    }
    payload.update(overrides)
    return ReadingRectificationInput.model_validate(payload)


def test_rectified_reading_keeps_the_previous_decision_as_the_declared_target() -> None:
    """Caso Guaxindiba: a cota foi confirmada como largura e mede a altura."""
    confirmed = _confirmed_packet()
    before = next(item for item in confirmed.readings if item.id == WIDTH_READING_ID)
    assert before.decision is not None
    previous_id = before.decision.decision_id

    rectified = rectify_reading_decisions(
        confirmed,
        ReadingRectificationBatch(
            rectifications=[_rectification(WIDTH_READING_ID, target=previous_id, kind="height")]
        ),
    )

    after = next(item for item in rectified.readings if item.id == WIDTH_READING_ID)
    assert after.decision is not None
    assert after.status is ReadingStatus.CONFIRMED
    assert after.kind.value == "height"
    assert after.decision.decision_id != previous_id
    assert after.decision.rectifies_decision_id == previous_id
    assert after.decision.note is not None
    # O pacote continua válido e a nota de sucessão entra uma vez só.
    assert ReviewPacket.model_validate(rectified.model_dump()) == rectified
    assert rectified.safety_notes.count(RECTIFICATION_SAFETY_NOTE) == 1
    twice = rectify_reading_decisions(
        rectified,
        ReadingRectificationBatch(
            rectifications=[
                _rectification(
                    WIDTH_READING_ID,
                    target=after.decision.decision_id,
                    kind="width",
                    note="Segunda correção do mesmo trecho, conferida na folha.",
                )
            ]
        ),
    )
    assert twice.safety_notes.count(RECTIFICATION_SAFETY_NOTE) == 1
    # A decisão anterior segue intacta no pacote de origem; nada é editado in place.
    assert before.decision.decision_id == previous_id
    assert before.decision.rectifies_decision_id is None


def test_rectification_can_turn_a_confirmation_into_a_rejection() -> None:
    confirmed = _confirmed_packet()
    before = next(item for item in confirmed.readings if item.id == WIDTH_READING_ID)
    assert before.decision is not None

    rectified = rectify_reading_decisions(
        confirmed,
        ReadingRectificationBatch(
            rectifications=[
                _rectification(
                    WIDTH_READING_ID,
                    target=before.decision.decision_id,
                    action="reject",
                    note="A cota não existe na folha; leitura rejeitada.",
                )
            ]
        ),
    )

    after = next(item for item in rectified.readings if item.id == WIDTH_READING_ID)
    assert after.status is ReadingStatus.REJECTED
    assert after.decision is not None
    assert after.decision.action == "reject"
    assert after.decision.rectifies_decision_id == before.decision.decision_id


def test_a_reading_without_a_decision_is_not_rectifiable() -> None:
    packet = _proposed_packet()

    with pytest.raises(ValueError, match="sem decisão"):
        rectify_reading_decisions(
            packet,
            ReadingRectificationBatch(
                rectifications=[_rectification(WIDTH_READING_ID, target="hd_" + "a" * 16)]
            ),
        )


def test_rectification_of_a_stale_target_is_refused() -> None:
    confirmed = _confirmed_packet()

    with pytest.raises(ValueError, match="não é a vigente"):
        rectify_reading_decisions(
            confirmed,
            ReadingRectificationBatch(
                rectifications=[_rectification(WIDTH_READING_ID, target="hd_" + "0" * 16)]
            ),
        )


def test_rectification_of_an_unknown_reading_is_refused() -> None:
    confirmed = _confirmed_packet()

    with pytest.raises(ValueError, match="desconhecidas"):
        rectify_reading_decisions(
            confirmed,
            ReadingRectificationBatch(
                rectifications=[_rectification("rd_" + "9" * 16, target="hd_" + "a" * 16)]
            ),
        )


def test_a_rectifying_decision_requires_a_written_justification() -> None:
    with pytest.raises(ValidationError, match="justificativa"):
        HumanDecision(
            decision_id="hd_" + "a" * 16,
            action="confirm",
            reviewer_id="reviewer",
            reviewer_role="engineer",
            decided_at=DECIDED_AT,
            note=None,
            rectifies_decision_id="hd_" + "b" * 16,
        )


def test_the_identifier_of_a_first_decision_is_unchanged_byte_for_byte() -> None:
    """Regressão: o id é identidade histórica e não pode mudar com o campo novo."""
    confirmed = _confirmed_packet()
    decided = next(item for item in confirmed.readings if item.id == WIDTH_READING_ID)

    assert decided.decision is not None
    # Valor recomputado com a fórmula anterior à sucessão declarada (sha256 do JSON
    # canônico sem a chave nova): a chave só entra quando há alvo a citar.
    assert decided.decision.decision_id == "hd_ae9391c59b8adac1"


def test_rectifications_of_distinct_targets_never_share_an_identifier() -> None:
    """Mesmo conteúdo, alvos distintos: a sucessão faz parte da identidade."""
    packet = apply_reading_decisions(
        _proposed_packet(),
        ReadingDecisionBatch(
            decisions=[
                _decision(WIDTH_READING_ID),
                _decision(HEIGHT_READING_ID, note="Outra conferência na evidência."),
            ]
        ),
    )
    width = next(item for item in packet.readings if item.id == WIDTH_READING_ID)
    height = next(item for item in packet.readings if item.id == HEIGHT_READING_ID)
    assert width.decision is not None and height.decision is not None
    assert width.decision.decision_id != height.decision.decision_id

    rectified = rectify_reading_decisions(
        packet,
        ReadingRectificationBatch(
            rectifications=[
                _rectification(WIDTH_READING_ID, target=width.decision.decision_id, kind="height"),
                _rectification(HEIGHT_READING_ID, target=height.decision.decision_id, kind="width"),
            ]
        ),
    )
    ids = {
        item.id: item.decision.decision_id
        for item in rectified.readings
        if item.decision is not None
    }
    assert ids[WIDTH_READING_ID] != ids[HEIGHT_READING_ID]
    assert len(set(ids.values())) == len(ids)


def test_the_normal_decision_still_refuses_a_reading_that_was_already_decided() -> None:
    confirmed = _confirmed_packet()

    with pytest.raises(ValueError, match="já revisada"):
        apply_reading_decisions(
            confirmed,
            ReadingDecisionBatch(decisions=[_decision(WIDTH_READING_ID, action="reject")]),
        )


def test_a_packet_written_before_the_rectification_field_still_loads() -> None:
    legacy = _confirmed_packet().model_dump(mode="json")
    for reading in legacy["readings"]:
        if reading["decision"] is not None:
            reading["decision"].pop("rectifies_decision_id")

    reloaded = ReviewPacket.model_validate(legacy)

    decided = next(item for item in reloaded.readings if item.id == WIDTH_READING_ID)
    assert decided.decision is not None
    assert decided.decision.rectifies_decision_id is None
    # E continua retificável: o alvo é o id que já estava gravado.
    rectified = rectify_reading_decisions(
        reloaded,
        ReadingRectificationBatch(
            rectifications=[
                _rectification(
                    WIDTH_READING_ID,
                    target=decided.decision.decision_id,
                    value_si=Decimal("21.75"),
                )
            ]
        ),
    )
    after = next(item for item in rectified.readings if item.id == WIDTH_READING_ID)
    assert after.value_si == Decimal("21.75")
