from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from croquito_core.models import MeasurementKind, UnitCode
from croquito_worker.association import AssociationCandidate, AssociationSet
from croquito_worker.association_confidence import (
    ConfidenceThreshold,
    ShadowChoice,
    association_confidence,
    reading_confidence,
    shadow_decisions,
)
from croquito_worker.dimension_closure import ChainTerm, DimensionChain
from croquito_worker.review import (
    DimensionReading,
    EvidenceRegion,
    HumanDecision,
    PixelBox,
    ReadingStatus,
    ReviewPacket,
)

DIGEST = "a" * 64


def _reading(
    index: int,
    *,
    value: str | None = "10.00",
    ocr_corroborated: bool | None = None,
) -> DimensionReading:
    confirmed = value is not None
    return DimensionReading(
        id=f"rd_{index:016x}",
        evidence=EvidenceRegion(
            dataset_id="fixture-v1",
            page_number=1,
            image_sha256=DIGEST,
            bbox=PixelBox(left=index * 20, top=5, right=index * 20 + 20, bottom=15),
        ),
        raw_text=f"{value or '?'} m",
        value_si=Decimal(value) if value is not None else None,
        unit=UnitCode.METRE,
        kind=MeasurementKind.WIDTH,
        written_decimals=2,
        target_hint="trecho",
        extractor="fixture",
        extractor_version="v1",
        ocr_corroborated=ocr_corroborated,
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


def _chain(
    *, total: DimensionReading, parts: list[DimensionReading], closes: bool
) -> DimensionChain:
    assert total.value_si is not None
    total_term = ChainTerm(reading_id=total.id, value_m=total.value_si, raw_text=total.raw_text)
    part_terms = tuple(
        ChainTerm(reading_id=part.id, value_m=part.value_si, raw_text=part.raw_text)
        for part in parts
        if part.value_si is not None
    )
    return DimensionChain(
        total=total_term,
        parts=part_terms,
        residual_m=Decimal("0.00") if closes else Decimal("5.00"),
        tolerance_m=Decimal("0.01"),
    )


def _candidate(**overrides: object) -> AssociationCandidate:
    defaults: dict[str, object] = {
        "reading_id": "rd_1111111111111111",
        "proposal_id": "vp_1111111111111111",
        "proposal_kind": "line",
        "relation": "nearest_geometry",
        "pixel_distance": 1.0,
        "proximity_score": 0.5,
        "visual_quality_score": 0.5,
        "orientation_alignment": 0.5,
    }
    defaults.update(overrides)
    return AssociationCandidate(**defaults)


# --- reading_confidence -------------------------------------------------------------


def test_reading_confidence_is_monotonic_in_ocr_corroboration() -> None:
    reading_true = _reading(1, ocr_corroborated=True)
    reading_none = _reading(2, ocr_corroborated=None)
    reading_false = _reading(3, ocr_corroborated=False)

    score_true = reading_confidence(reading_true, [])
    score_none = reading_confidence(reading_none, [])
    score_false = reading_confidence(reading_false, [])

    assert score_true > score_none > score_false


def test_reading_confidence_without_chains_is_neutral_not_penalized() -> None:
    reading = _reading(1, ocr_corroborated=True)

    score = reading_confidence(reading, [])

    # ocr=True (0.4) + cadeia ausente neutra (0.3 * 0.5) + valor presente (0.3):
    assert score == 0.85


def test_reading_confidence_rewards_a_chain_that_closes_over_one_that_does_not() -> None:
    total = _reading(1, value="25.90")
    part_a = _reading(2, value="12.49")
    part_b = _reading(3, value="13.41")

    closing_chain = _chain(total=total, parts=[part_a, part_b], closes=True)
    broken_chain = _chain(total=total, parts=[part_a, part_b], closes=False)

    score_with_closing_chain = reading_confidence(total, [closing_chain])
    score_with_broken_chain = reading_confidence(total, [broken_chain])

    assert score_with_closing_chain > score_with_broken_chain


def test_reading_confidence_penalizes_missing_value() -> None:
    reading_with_value = _reading(1, value="10.00", ocr_corroborated=None)
    reading_without_value = _reading(2, value=None, ocr_corroborated=None)

    score_with_value = reading_confidence(reading_with_value, [])
    score_without_value = reading_confidence(reading_without_value, [])
    assert score_with_value > score_without_value


def test_reading_confidence_is_deterministic() -> None:
    reading = _reading(1, ocr_corroborated=True)

    assert reading_confidence(reading, []) == reading_confidence(reading, [])


# --- association_confidence ----------------------------------------------------------


def test_association_confidence_is_monotonic_in_proximity() -> None:
    reading = _reading(1)
    low = _candidate(proximity_score=0.2)
    high = _candidate(proximity_score=0.8)

    assert association_confidence(high, reading) > association_confidence(low, reading)


def test_association_confidence_is_monotonic_in_visual_quality() -> None:
    reading = _reading(1)
    low = _candidate(visual_quality_score=0.2)
    high = _candidate(visual_quality_score=0.8)

    assert association_confidence(high, reading) > association_confidence(low, reading)


def test_association_confidence_is_monotonic_in_orientation_alignment() -> None:
    reading = _reading(1)
    low = _candidate(orientation_alignment=0.0)
    high = _candidate(orientation_alignment=1.0)

    assert association_confidence(high, reading) > association_confidence(low, reading)


def test_circle_without_orientation_is_neutral_not_penalized() -> None:
    """Círculo (sem direção própria) não deve ser tratado pior que uma linha mal alinhada."""
    reading = _reading(1)
    misaligned_line = _candidate(orientation_alignment=0.0)
    circle_without_direction = _candidate(
        proposal_kind="circle",
        relation="inside_or_near_circle",
        orientation_alignment=None,
    )

    assert association_confidence(circle_without_direction, reading) > association_confidence(
        misaligned_line, reading
    )


def test_ambiguous_candidate_is_downgraded_by_margin_over_second_candidate() -> None:
    reading = _reading(1)
    clear_winner = _candidate(proximity_score=0.8)
    clear_winner_sibling = _candidate(proposal_id="vp_2222222222222222", proximity_score=0.2)

    tied_candidate = _candidate(proximity_score=0.8)
    tied_sibling = _candidate(proposal_id="vp_2222222222222222", proximity_score=0.79)

    score_clear = association_confidence(
        clear_winner, reading, other_candidates=[clear_winner, clear_winner_sibling]
    )
    score_ambiguous = association_confidence(
        tied_candidate, reading, other_candidates=[tied_candidate, tied_sibling]
    )

    assert score_clear > score_ambiguous


def test_association_confidence_is_deterministic() -> None:
    reading = _reading(1)
    candidate = _candidate()

    first = association_confidence(candidate, reading)
    second = association_confidence(candidate, reading)

    assert first == second


# --- shadow_decisions ------------------------------------------------------------------


def _packet(*readings: DimensionReading) -> ReviewPacket:
    return ReviewPacket(
        dataset_id="fixture-v1",
        page_number=1,
        image_sha256=DIGEST,
        readings=list(readings),
        safety_notes=["fixture", "revisão humana obrigatória"],
    )


def _associations(*candidates: AssociationCandidate) -> AssociationSet:
    return AssociationSet(
        dataset_id="fixture-v1",
        page_number=1,
        image_sha256=DIGEST,
        candidates=list(candidates),
        unassociated_reading_ids=[],
        safety_notes=["fixture", "não confirma", "não exporta"],
    )


def test_shadow_decisions_is_pure_and_never_mixes_reading_and_association_confidence() -> None:
    strong_reading = _reading(1, ocr_corroborated=True, value="10.00")
    weak_reading = _reading(2, ocr_corroborated=False, value="10.00")

    strong_candidate = _candidate(
        reading_id=strong_reading.id,
        proposal_id="vp_1111111111111111",
        proximity_score=0.95,
        visual_quality_score=0.95,
        orientation_alignment=0.95,
        association_confidence=0.95,
    )
    weak_candidate = _candidate(
        reading_id=weak_reading.id,
        proposal_id="vp_2222222222222222",
        proximity_score=0.1,
        visual_quality_score=0.1,
        orientation_alignment=0.1,
        association_confidence=0.1,
    )

    packet = _packet(strong_reading, weak_reading)
    associations = _associations(strong_candidate, weak_candidate)
    thresholds = [
        ConfidenceThreshold(reading_threshold=0.6, association_threshold=0.6),
        ConfidenceThreshold(reading_threshold=0.95, association_threshold=0.95),
    ]

    readings_before = [reading.model_dump() for reading in packet.readings]
    candidates_before = [candidate.model_dump() for candidate in associations.candidates]

    decisions = shadow_decisions(packet, associations, [], thresholds)

    lenient, strict = decisions
    lenient_ids = tuple(choice.reading_id for choice in lenient.auto_choices)
    assert lenient_ids == (strong_reading.id,)
    assert weak_reading.id not in lenient_ids
    assert lenient.auto_choices[0].proposal_id == strong_candidate.proposal_id
    assert lenient.auto_choices[0].association_confidence == strong_candidate.association_confidence
    assert lenient.auto_choices[0].reading_confidence == reading_confidence(strong_reading, [])

    # Nenhum efeito colateral: entradas continuam idênticas depois da chamada.
    assert [reading.model_dump() for reading in packet.readings] == readings_before
    assert [candidate.model_dump() for candidate in associations.candidates] == candidates_before

    # Determinismo/pureza: mesma entrada produz a mesma saída, sem mutar nada.
    repeated = shadow_decisions(packet, associations, [], thresholds)
    assert decisions == repeated
    assert strict.reading_threshold == 0.95


def test_shadow_decisions_requires_both_reading_and_association_above_threshold() -> None:
    """Leitura ótima mas associação ambígua não deve entrar — o erro perigoso é associar errado."""
    reading = _reading(1, ocr_corroborated=True, value="10.00")
    weak_association_candidate = _candidate(
        reading_id=reading.id,
        proposal_id="vp_1111111111111111",
        proximity_score=0.1,
        visual_quality_score=0.1,
        orientation_alignment=0.1,
        association_confidence=0.1,
    )

    packet = _packet(reading)
    associations = _associations(weak_association_candidate)
    thresholds = [ConfidenceThreshold(reading_threshold=0.5, association_threshold=0.5)]

    decisions = shadow_decisions(packet, associations, [], thresholds)

    assert decisions[0].auto_choices == ()


def test_shadow_decisions_excludes_unassociated_readings() -> None:
    reading = _reading(1, ocr_corroborated=True, value="10.00")
    packet = _packet(reading)
    associations = _associations()  # nenhum candidato: leitura sem associação
    thresholds = [ConfidenceThreshold(reading_threshold=0.0, association_threshold=0.0)]

    decisions = shadow_decisions(packet, associations, [], thresholds)

    assert decisions[0].auto_choices == ()


def test_shadow_decisions_breaks_ties_by_proposal_id_deterministically() -> None:
    """Dois candidatos com a mesma `association_confidence`: vence o menor `proposal_id`,
    de forma determinística em chamadas repetidas — nunca a ordem de inserção da lista."""
    reading = _reading(1, ocr_corroborated=True, value="10.00")
    higher_id_candidate = _candidate(
        reading_id=reading.id,
        proposal_id="vp_ffffffffffffffff",
        association_confidence=0.9,
    )
    lower_id_candidate = _candidate(
        reading_id=reading.id,
        proposal_id="vp_1111111111111111",
        association_confidence=0.9,
    )

    packet = _packet(reading)
    # Ordem de inserção propositalmente favorece o candidato de maior id, para provar que
    # o desempate não depende de posição na lista.
    associations = _associations(higher_id_candidate, lower_id_candidate)
    thresholds = [ConfidenceThreshold(reading_threshold=0.0, association_threshold=0.0)]

    decisions = shadow_decisions(packet, associations, [], thresholds)
    repeated = shadow_decisions(packet, associations, [], thresholds)

    assert decisions[0].auto_choices == (
        ShadowChoice(
            reading_id=reading.id,
            proposal_id="vp_1111111111111111",
            reading_confidence=reading_confidence(reading, []),
            association_confidence=0.9,
        ),
    )
    assert decisions == repeated
