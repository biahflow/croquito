"""O extrator fixture produz observação, nunca quantitativo.

Todo item sai `proposed` ou `ambiguous`, amarrado por digest à prancha que acabou de ser
gerada. A fixture não aceita prancha que ela não desenhou, e um arquivo alterado entre
gerar e extrair recusa em vez de virar item.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from croquitodxf_valuation.errors import ValuationValidationError
from croquitodxf_valuation.takeoff import TakeoffItemStatus, TakeoffPacket
from croquitodxf_worker.valuation.plate import (
    PLATE_EXTRACTOR_VERSION,
    SYNTHETIC_LEGEND_ROWS,
    SYNTHETIC_PLATE_ID,
    render_synthetic_plate,
)
from croquitodxf_worker.valuation.takeoff_fixture import (
    FIXTURE_EXTRACTOR,
    extract_takeoff_fixture,
    takeoff_item_id,
)

_AMBIGUOUS_LABEL = "PISO EMBORRACHADO SINTETICO"


def _extract(directory: Path) -> TakeoffPacket:
    return extract_takeoff_fixture(render_synthetic_plate(directory))


def test_packet_has_one_item_per_legend_row(tmp_path: Path) -> None:
    packet = _extract(tmp_path / "plate")

    assert packet.plate_id == SYNTHETIC_PLATE_ID
    assert packet.page_number == 1
    assert len(packet.items) == len(SYNTHETIC_LEGEND_ROWS)
    assert [item.label for item in packet.items] == [row.label for row in SYNTHETIC_LEGEND_ROWS]
    assert [item.raw_text for item in packet.items] == [
        row.as_written() for row in SYNTHETIC_LEGEND_ROWS
    ]


def test_no_item_is_born_confirmed(tmp_path: Path) -> None:
    packet = _extract(tmp_path / "plate")

    assert {item.status for item in packet.items} == {
        TakeoffItemStatus.PROPOSED,
        TakeoffItemStatus.AMBIGUOUS,
    }
    assert packet.confirmed_items() == []
    assert len(packet.pending_items()) == len(packet.items)
    assert all(item.decision is None for item in packet.items)


def test_the_illegible_row_becomes_the_only_ambiguous_item(tmp_path: Path) -> None:
    packet = _extract(tmp_path / "plate")

    ambiguous = [item for item in packet.items if item.status is TakeoffItemStatus.AMBIGUOUS]
    assert [item.label for item in ambiguous] == [_AMBIGUOUS_LABEL]
    assert ambiguous[0].quantity is None
    assert all(
        item.quantity is not None
        for item in packet.items
        if item.status is TakeoffItemStatus.PROPOSED
    )


def test_units_are_normalized_from_what_the_plate_writes(tmp_path: Path) -> None:
    packet = _extract(tmp_path / "plate")

    assert {row.unit for row in SYNTHETIC_LEGEND_ROWS} == {"M2", "M", "UN"}
    assert [item.unit for item in packet.items] == ["m2", "m2", "m", "un", "un", "m2", "m2"]


def test_lineage_records_the_fixture_extractor(tmp_path: Path) -> None:
    packet = _extract(tmp_path / "plate")

    assert {item.extractor for item in packet.items} == {FIXTURE_EXTRACTOR}
    assert {item.extractor_version for item in packet.items} == {PLATE_EXTRACTOR_VERSION}
    assert {item.source for item in packet.items} == {"legend_extraction"}
    assert packet.safety_status == "human_review_required"
    assert packet.safety_notes == [
        "Extração fixture sintética; nenhuma prancha de cliente foi lida.",
        "Decisão do orçamentista obrigatória antes de qualquer quantitativo.",
    ]


def test_evidence_is_bound_to_the_plate_that_was_generated(tmp_path: Path) -> None:
    artifacts = render_synthetic_plate(tmp_path / "plate")

    packet = extract_takeoff_fixture(artifacts)

    assert packet.image_sha256 == artifacts.image_sha256
    assert packet.source_pdf_sha256 == artifacts.pdf_sha256
    assert [item.evidence.bbox for item in packet.items] == [entry.bbox for entry in artifacts.rows]
    assert {item.evidence.image_sha256 for item in packet.items} == {artifacts.image_sha256}


def test_item_ids_are_deterministic_between_two_extractions(tmp_path: Path) -> None:
    """O id é função da prancha e do rótulo: duas gerações da mesma legenda coincidem."""
    first = _extract(tmp_path / "first")
    second = _extract(tmp_path / "second")

    assert [item.id for item in first.items] == [item.id for item in second.items]
    assert [item.id for item in first.items] == [
        takeoff_item_id(SYNTHETIC_PLATE_ID, row.label) for row in SYNTHETIC_LEGEND_ROWS
    ]


def test_an_artifact_changed_after_generation_is_refused(tmp_path: Path) -> None:
    artifacts = render_synthetic_plate(tmp_path / "plate")
    artifacts.image_path.write_bytes(b"outra imagem")

    with pytest.raises(ValuationValidationError) as raised:
        extract_takeoff_fixture(artifacts)

    assert raised.value.code == "TAKEOFF_FIXTURE_ARTIFACT_MISMATCH"


def test_packet_round_trips_through_the_canonical_json(tmp_path: Path) -> None:
    packet = _extract(tmp_path / "plate")

    assert TakeoffPacket.model_validate_json(packet.model_dump_json()) == packet
