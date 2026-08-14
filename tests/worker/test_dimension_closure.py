import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from croquitodxf_core.models import IssueSeverity
from croquitodxf_worker.dimension_closure import (
    ChainVerificationError,
    is_plan_dimension,
    suggest_chains,
    verify_chain,
)
from croquitodxf_worker.review import (
    DimensionReading,
    EvidenceRegion,
    HumanDecision,
    PixelBox,
    ReadingStatus,
    ReviewPacket,
)

DIGEST = "a" * 64

GOLDEN = Path("output/pdf/golden-guaxindiba-v1/review-input.json")


def _reading(
    index: int,
    raw_text: str,
    value: str,
    *,
    kind: str = "length",
    decimals: int = 2,
    confirmed: bool = True,
) -> DimensionReading:
    return DimensionReading(
        id=f"rd_{index:016x}",
        evidence=EvidenceRegion(
            dataset_id="fixture-v1",
            page_number=1,
            image_sha256=DIGEST,
            bbox=PixelBox(left=index * 20, top=5, right=index * 20 + 20, bottom=15),
        ),
        raw_text=raw_text,
        value_si=Decimal(value),
        unit="m",
        kind=kind,
        written_decimals=decimals,
        target_hint="trecho",
        extractor="local-fixture",
        extractor_version="v1",
        status=ReadingStatus.CONFIRMED if confirmed else ReadingStatus.PROPOSED,
        decision=(
            HumanDecision(
                decision_id=f"hd_{index:016x}",
                action="confirm",
                reviewer_id="reviewer",
                reviewer_role="engineer",
                decided_at=datetime.now(UTC),
            )
            if confirmed
            else None
        ),
    )


def _packet(*readings: DimensionReading) -> ReviewPacket:
    return ReviewPacket(
        dataset_id="fixture-v1",
        page_number=1,
        image_sha256=DIGEST,
        readings=list(readings),
        safety_notes=["Fixture local.", "Revisão humana obrigatória."],
    )


PARTS = ("12,49", "9,55", "3,86")


def _guaxindiba_packet() -> ReviewPacket:
    """A cadeia real do croqui: três trechos partilham a largura do campo."""
    return _packet(
        _reading(1, "25,90", "25.90"),
        _reading(2, PARTS[0], "12.49"),
        _reading(3, PARTS[1], "9.55"),
        _reading(4, PARTS[2], "3.86"),
    )


def test_a_declared_chain_that_closes_reports_no_issue() -> None:
    packet = _guaxindiba_packet()

    chain = verify_chain(
        packet,
        total_id="rd_0000000000000001",
        part_ids=[
            "rd_0000000000000002",
            "rd_0000000000000003",
            "rd_0000000000000004",
        ],
    )

    assert chain.parts_sum_m == Decimal("25.90")
    assert chain.residual_m == Decimal("0.00")
    assert chain.closes is True
    assert chain.issue() is None


def test_a_declared_chain_that_misses_becomes_a_warning_never_a_blocker() -> None:
    """O croqui pode estar certo com a cota faltando; travar o export seria veto indevido."""
    packet = _packet(
        _reading(1, "19,75", "19.75"),
        _reading(2, "21,75", "21.75"),
        _reading(3, "0,90", "0.90"),
    )

    chain = verify_chain(
        packet,
        total_id="rd_0000000000000001",
        part_ids=["rd_0000000000000002", "rd_0000000000000003"],
    )

    assert chain.closes is False
    assert chain.residual_m == Decimal("2.90")
    issue = chain.issue()
    assert issue is not None
    assert issue.severity is IssueSeverity.WARNING
    assert issue.code == "DIMENSION_CHAIN_MISMATCH"
    assert "2.90" in issue.message


def test_chain_tolerance_accumulates_over_the_terms() -> None:
    """Cobrar de uma soma de três a precisão de uma cota isolada reprovaria cadeia boa."""
    packet = _packet(
        _reading(1, "10,0", "10.0", decimals=1),
        _reading(2, "5,0", "5.04", decimals=1),
        _reading(3, "5,0", "5.0", decimals=1),
    )

    chain = verify_chain(
        packet,
        total_id="rd_0000000000000001",
        part_ids=["rd_0000000000000002", "rd_0000000000000003"],
    )

    assert chain.tolerance_m == Decimal("0.15")  # três termos a 0,05
    assert chain.closes is True


def test_unconfirmed_reading_cannot_enter_a_chain() -> None:
    packet = _packet(
        _reading(1, "25,90", "25.90"),
        _reading(2, "12,49", "12.49"),
        _reading(3, "13,41", "13.41", confirmed=False),
    )

    with pytest.raises(ChainVerificationError, match="não confirmadas"):
        verify_chain(
            packet,
            total_id="rd_0000000000000001",
            part_ids=["rd_0000000000000002", "rd_0000000000000003"],
        )


def test_a_reading_cannot_be_its_own_part_or_appear_twice() -> None:
    packet = _guaxindiba_packet()

    with pytest.raises(ChainVerificationError, match="parcela de si"):
        verify_chain(
            packet,
            total_id="rd_0000000000000001",
            part_ids=["rd_0000000000000001", "rd_0000000000000002"],
        )
    with pytest.raises(ChainVerificationError, match="duas vezes"):
        verify_chain(
            packet,
            total_id="rd_0000000000000001",
            part_ids=["rd_0000000000000002", "rd_0000000000000002"],
        )


def test_annotation_is_not_a_plan_dimension() -> None:
    """`kind` não separa: no croqui real 21,75 vem marcado `height` e é largura em planta."""
    assert is_plan_dimension(_reading(1, "21,75", "21.75", kind="height")) is True
    assert is_plan_dimension(_reading(2, "14,50 m", "14.50")) is True
    assert is_plan_dimension(_reading(3, "muro vizinho h=3,80", "3.80", kind="height")) is False
    assert is_plan_dimension(_reading(4, "Portão 1,0 x 2,05", "1.0")) is False
    assert is_plan_dimension(_reading(5, "2 Traves 4'' h=2,20 c=3,90", "3.90")) is False


def test_suggestions_ignore_annotations_so_a_gate_never_sums_with_a_wall_height() -> None:
    packet = _packet(
        _reading(1, "12,49", "12.49"),
        _reading(2, "8,60", "8.60"),
        _reading(3, "Portão 3,60 x 3,90", "3.89"),
    )

    assert suggest_chains(packet) == []


def test_suggestions_are_capped_and_shortest_first() -> None:
    packet = _guaxindiba_packet()

    found = suggest_chains(packet, limit=3)

    assert len(found) <= 3
    assert all(chain.closes for chain in found)
    assert [len(chain.parts) for chain in found] == sorted(len(c.parts) for c in found)


@pytest.mark.skipif(not GOLDEN.is_file(), reason="golden local, não versionado")
def test_the_real_chain_is_found_among_the_suggestions_on_the_golden_sketch() -> None:
    """Guardrail medido: entre 12 cotas de planta saem 4 sugestões, 3 delas coincidência."""
    raw = json.loads(GOLDEN.read_text())
    for index, reading in enumerate(raw["readings"]):
        if reading["value_si"] is not None:
            reading["status"] = "confirmed"
            reading["decision"] = {
                "decision_id": f"hd_{index:016x}",
                "action": "confirm",
                "reviewer_id": "tester",
                "reviewer_role": "engineer",
                "decided_at": datetime.now(UTC).isoformat(),
            }
    packet = ReviewPacket.model_validate(raw)

    found = suggest_chains(packet)

    assert len(found) <= 6, "explosão combinatória vira ruído para o revisor"
    real = {
        frozenset(term.raw_text for term in chain.parts): chain
        for chain in found
        if chain.total.raw_text == "25,90"
    }
    assert frozenset(PARTS) in real
