"""`TakeoffPacket` espelha `ReviewPacket`: proposed/ambiguous só vira confirmed/rejected
por decisão rastreável do orçamentista, e a aplicação nunca muta o pacote de entrada."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Literal

import pytest
from pydantic import ValidationError

from croquitodxf_valuation.errors import ValuationValidationError, valuation_error_codes
from croquitodxf_valuation.models import ReviewerDecision
from croquitodxf_valuation.takeoff import (
    PlateBox,
    PlateEvidence,
    TakeoffDecisionBatch,
    TakeoffDecisionInput,
    TakeoffItem,
    TakeoffItemStatus,
    TakeoffPacket,
    apply_takeoff_decisions,
)

_PLATE_ID = "praca-sintetica-norte-prancha-01"
_DIGEST = "a" * 64
_PDF_DIGEST = "b" * 64
_ITEM_1 = "ti_0000000000000001"
_ITEM_2 = "ti_0000000000000002"


def _evidence(
    *, plate_id: str = _PLATE_ID, page_number: int = 1, image_sha256: str = _DIGEST
) -> PlateEvidence:
    return PlateEvidence(
        plate_id=plate_id,
        page_number=page_number,
        image_sha256=image_sha256,
        bbox=PlateBox(left=10, top=10, right=110, bottom=60),
    )


def _item(
    *,
    item_id: str = _ITEM_1,
    status: TakeoffItemStatus = TakeoffItemStatus.PROPOSED,
    quantity: Decimal | None = Decimal("105.00"),
    decision: ReviewerDecision | None = None,
    evidence: PlateEvidence | None = None,
) -> TakeoffItem:
    return TakeoffItem(
        id=item_id,
        evidence=evidence or _evidence(),
        raw_text="PISO INTERTRAVADO 105,00 M2",
        label="PISO INTERTRAVADO",
        quantity=quantity,
        unit="m2",
        source="legend_extraction",
        extractor="legend-extractor-sintetico",
        extractor_version="1.0.0",
        status=status,
        decision=decision,
    )


def _decision(action: Literal["confirm", "reject"] = "confirm") -> ReviewerDecision:
    return ReviewerDecision(
        decision_id="vd_0123456789abcdef",
        action=action,
        reviewer_id="orcamentista-sintetico",
        reviewer_role="orcamentista",
        decided_at=datetime(2026, 2, 1, 12, 0, tzinfo=UTC),
    )


def _packet(
    items: list[TakeoffItem] | None = None,
    *,
    plate_id: str = _PLATE_ID,
    page_number: int = 1,
    image_sha256: str = _DIGEST,
) -> TakeoffPacket:
    return TakeoffPacket(
        plate_id=plate_id,
        page_number=page_number,
        image_sha256=image_sha256,
        source_pdf_sha256=_PDF_DIGEST,
        items=items
        if items is not None
        else [
            _item(),
            _item(item_id=_ITEM_2, status=TakeoffItemStatus.AMBIGUOUS, quantity=None),
        ],
        safety_notes=[
            "Extração automática da legenda; quantidade não confirmada.",
            "Decisão do orçamentista obrigatória antes de qualquer boletim.",
        ],
    )


def _decision_input(
    *,
    item_id: str = _ITEM_1,
    action: Literal["confirm", "reject"] = "confirm",
    decided_at: datetime = datetime(2026, 2, 1, 12, 0, tzinfo=UTC),
    **overrides: object,
) -> TakeoffDecisionInput:
    return TakeoffDecisionInput(
        item_id=item_id,
        action=action,
        reviewer_id="orcamentista-sintetico",
        reviewer_role="orcamentista",
        decided_at=decided_at,
        **overrides,
    )


def test_packet_with_proposed_and_ambiguous_items_builds() -> None:
    packet = _packet()

    assert {item.id for item in packet.pending_items()} == {_ITEM_1, _ITEM_2}
    assert packet.confirmed_items() == []


def test_duplicate_item_ids_are_refused() -> None:
    with pytest.raises(ValidationError) as raised:
        _packet(items=[_item(), _item()])

    assert valuation_error_codes(raised.value) == ["TAKEOFF_DUPLICATE_ITEM_ID"]


@pytest.mark.parametrize(
    "evidence_kwargs",
    [
        {"plate_id": "outra-prancha"},
        {"page_number": 2},
        {"image_sha256": "c" * 64},
    ],
)
def test_evidence_diverging_from_packet_is_refused(evidence_kwargs: dict[str, object]) -> None:
    mismatched_item = _item(evidence=_evidence(**evidence_kwargs))  # type: ignore[arg-type]

    with pytest.raises(ValidationError) as raised:
        _packet(items=[mismatched_item])

    assert valuation_error_codes(raised.value) == ["TAKEOFF_EVIDENCE_MISMATCH"]


def test_confirmed_item_requires_quantity_and_decision() -> None:
    with pytest.raises(ValidationError) as raised:
        _item(status=TakeoffItemStatus.CONFIRMED, quantity=None, decision=None)

    assert valuation_error_codes(raised.value) == ["TAKEOFF_ITEM_CONFIRMED_INCOMPLETE"]


def test_rejected_item_requires_a_reject_decision() -> None:
    with pytest.raises(ValidationError) as raised:
        _item(status=TakeoffItemStatus.REJECTED, decision=None)

    assert valuation_error_codes(raised.value) == ["TAKEOFF_ITEM_REJECTED_WITHOUT_DECISION"]


def test_proposed_item_cannot_carry_a_decision() -> None:
    with pytest.raises(ValidationError) as raised:
        _item(status=TakeoffItemStatus.PROPOSED, decision=_decision())

    assert valuation_error_codes(raised.value) == ["TAKEOFF_ITEM_UNREVIEWED_WITH_DECISION"]


def test_ambiguous_item_cannot_carry_a_quantity() -> None:
    with pytest.raises(ValidationError) as raised:
        _item(status=TakeoffItemStatus.AMBIGUOUS, quantity=Decimal("10.00"))

    assert valuation_error_codes(raised.value) == ["TAKEOFF_ITEM_AMBIGUOUS_WITH_QUANTITY"]


def test_batch_refuses_two_decisions_for_the_same_item() -> None:
    decision = _decision_input()

    with pytest.raises(ValidationError) as raised:
        TakeoffDecisionBatch(decisions=[decision, decision])

    assert valuation_error_codes(raised.value) == ["TAKEOFF_DECISION_DUPLICATE_ITEM"]


def test_decision_without_timezone_is_refused() -> None:
    with pytest.raises(ValidationError) as raised:
        TakeoffDecisionInput(
            item_id=_ITEM_1,
            action="confirm",
            reviewer_id="orcamentista-sintetico",
            reviewer_role="orcamentista",
            decided_at=datetime(2026, 2, 1, 12, 0),
        )

    assert valuation_error_codes(raised.value) == ["TAKEOFF_DECISION_TIMESTAMP_NAIVE"]


def test_apply_confirms_a_proposed_item_keeping_its_proposed_quantity() -> None:
    packet = _packet()
    batch = TakeoffDecisionBatch(decisions=[_decision_input()])

    updated = apply_takeoff_decisions(packet, batch)

    confirmed = next(item for item in updated.items if item.id == _ITEM_1)
    assert confirmed.status is TakeoffItemStatus.CONFIRMED
    assert confirmed.quantity == Decimal("105.00")
    assert confirmed.decision is not None
    assert confirmed.decision.action == "confirm"


def test_apply_confirms_with_quantity_unit_and_label_overrides() -> None:
    packet = _packet()
    batch = TakeoffDecisionBatch(
        decisions=[
            _decision_input(
                quantity=Decimal("98.50"),
                unit="m2",
                label="PISO INTERTRAVADO CORRIGIDO",
            )
        ]
    )

    updated = apply_takeoff_decisions(packet, batch)

    confirmed = next(item for item in updated.items if item.id == _ITEM_1)
    assert confirmed.quantity == Decimal("98.50")
    assert confirmed.unit == "m2"
    assert confirmed.label == "PISO INTERTRAVADO CORRIGIDO"


def test_apply_confirms_an_ambiguous_item_when_quantity_is_supplied() -> None:
    packet = _packet()
    batch = TakeoffDecisionBatch(
        decisions=[_decision_input(item_id=_ITEM_2, quantity=Decimal("12.30"))]
    )

    updated = apply_takeoff_decisions(packet, batch)

    confirmed = next(item for item in updated.items if item.id == _ITEM_2)
    assert confirmed.status is TakeoffItemStatus.CONFIRMED
    assert confirmed.quantity == Decimal("12.30")


def test_apply_confirming_an_ambiguous_item_without_quantity_raises_the_model_error() -> None:
    packet = _packet()
    batch = TakeoffDecisionBatch(decisions=[_decision_input(item_id=_ITEM_2)])

    with pytest.raises(ValidationError) as raised:
        apply_takeoff_decisions(packet, batch)

    assert valuation_error_codes(raised.value) == ["TAKEOFF_ITEM_CONFIRMED_INCOMPLETE"]


def test_apply_rejects_an_item() -> None:
    packet = _packet()
    batch = TakeoffDecisionBatch(decisions=[_decision_input(action="reject")])

    updated = apply_takeoff_decisions(packet, batch)

    rejected = next(item for item in updated.items if item.id == _ITEM_1)
    assert rejected.status is TakeoffItemStatus.REJECTED
    assert rejected.decision is not None
    assert rejected.decision.action == "reject"


def test_apply_refuses_decision_for_unknown_item() -> None:
    packet = _packet()
    batch = TakeoffDecisionBatch(decisions=[_decision_input(item_id="ti_ffffffffffffffff")])

    with pytest.raises(ValuationValidationError) as raised:
        apply_takeoff_decisions(packet, batch)

    assert raised.value.code == "TAKEOFF_DECISION_UNKNOWN_ITEM"


def test_apply_refuses_re_deciding_an_already_reviewed_item() -> None:
    packet = _packet()
    first_pass = apply_takeoff_decisions(
        packet, TakeoffDecisionBatch(decisions=[_decision_input()])
    )

    with pytest.raises(ValuationValidationError) as raised:
        apply_takeoff_decisions(
            first_pass,
            TakeoffDecisionBatch(
                decisions=[_decision_input(decided_at=datetime(2026, 2, 2, 9, 0, tzinfo=UTC))]
            ),
        )

    assert raised.value.code == "TAKEOFF_ITEM_ALREADY_REVIEWED"


def test_apply_never_mutates_the_input_packet() -> None:
    packet = _packet()
    before = packet.model_dump()

    apply_takeoff_decisions(packet, TakeoffDecisionBatch(decisions=[_decision_input()]))

    assert packet.model_dump() == before


def test_decision_id_is_deterministic_for_the_same_input() -> None:
    packet = _packet()
    decision = _decision_input()

    first = apply_takeoff_decisions(packet, TakeoffDecisionBatch(decisions=[decision]))
    second = apply_takeoff_decisions(packet, TakeoffDecisionBatch(decisions=[decision]))

    first_decision = next(item for item in first.items if item.id == _ITEM_1).decision
    second_decision = next(item for item in second.items if item.id == _ITEM_1).decision
    assert first_decision is not None
    assert second_decision is not None
    assert first_decision.decision_id == second_decision.decision_id


def test_apply_appends_a_safety_note_without_losing_the_originals() -> None:
    packet = _packet()

    updated = apply_takeoff_decisions(packet, TakeoffDecisionBatch(decisions=[_decision_input()]))

    assert updated.safety_notes[: len(packet.safety_notes)] == packet.safety_notes
    assert updated.safety_notes[-1] == (
        "Decisões do orçamentista aplicadas; propostas originais permanecem "
        "no histórico de entrada."
    )
