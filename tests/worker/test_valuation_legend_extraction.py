"""Mapeamento observação→takeoff da extração paga de legenda, e os gates que a cercam.

O que estes testes protegem é a peça que decide o que vira número: `takeoff_packet_from_legend`
é pura, roda sem provider e sem rede, e a regra dela é uma só — na dúvida, item ambíguo e
**sem** quantidade. Quantidade fora da gramática pt-BR, unidade que o catálogo não conhece,
rótulo ausente ou linha declarada ilegível nunca viram um número plausível.
"""

from __future__ import annotations

import hashlib
import json
from decimal import Decimal
from pathlib import Path

import pytest
from PIL import Image
from pydantic import ValidationError

from croquito_valuation.errors import ValuationValidationError, valuation_error_codes
from croquito_valuation.takeoff import TakeoffItemStatus
from croquito_worker.extraction_eval import ExtractionNotAllowlistedError
from croquito_worker.providers import (
    FixtureProviderAdapter,
    LegendExtractionOutput,
    LegendRowOutput,
    NormalizedBox,
    PromptTask,
    ProviderName,
)
from croquito_worker.valuation.legend_extraction import (
    extractor_label,
    legend_item_id,
    normalized_legend_unit,
    parse_legend_quantity,
    run_legend_extraction,
    takeoff_packet_from_legend,
)

ALLOWLIST = "CROQUITO_AI_EXTRACTION_ALLOWED_DIGESTS"

_PLATE_ID = "prancha-de-teste-01"
_IMAGE_DIGEST = "a" * 64
_PDF_DIGEST = "b" * 64
_IMAGE_WIDTH = 400
_IMAGE_HEIGHT = 200
_EXTRACTOR = "anthropic:fixture-legend-v1"
_EXTRACTOR_VERSION = "legend-extraction@1.0.0"


def _row(
    *,
    raw_text: str = "PISO INTERTRAVADO 61,20 M2",
    label: str | None = "PISO INTERTRAVADO",
    quantity_text: str | None = "61,20",
    unit_text: str | None = "M2",
    legibility: str = "clear",
    bbox: NormalizedBox | None = None,
) -> LegendRowOutput:
    return LegendRowOutput.model_validate(
        {
            "raw_text": raw_text,
            "label": label,
            "quantity_text": quantity_text,
            "unit_text": unit_text,
            "legibility": legibility,
            "bbox": (bbox or NormalizedBox(left=0.1, top=0.2, right=0.9, bottom=0.4)).model_dump(),
        }
    )


def _packet_from(*rows: LegendRowOutput):  # type: ignore[no-untyped-def]
    return takeoff_packet_from_legend(
        LegendExtractionOutput(rows=list(rows)),
        plate_id=_PLATE_ID,
        page_number=1,
        image_sha256=_IMAGE_DIGEST,
        source_pdf_sha256=_PDF_DIGEST,
        image_width=_IMAGE_WIDTH,
        image_height=_IMAGE_HEIGHT,
        extractor=_EXTRACTOR,
        extractor_version=_EXTRACTOR_VERSION,
    )


# --------------------------------------------------------------------------------------
# Gramática pt-BR da quantidade
# --------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("61,20", Decimal("61.20")),
        ("1.234,50", Decimal("1234.50")),
        ("2.345,67", Decimal("2345.67")),
        ("4", Decimal("4")),
        ("1.234", Decimal("1234")),
        ("  7  ", Decimal("7")),
    ],
)
def test_quantity_written_in_portuguese_is_parsed_exactly(text: str, expected: Decimal) -> None:
    assert parse_legend_quantity(text) == expected


@pytest.mark.parametrize(
    "text",
    [
        None,
        "",
        "---",
        "1.5",
        "1,234.50",
        "61,20 m2",
        "aprox. 60",
        "0",
        "-4",
    ],
)
def test_quantity_outside_the_grammar_is_a_doubt_not_a_number(text: str | None) -> None:
    """`1.5` é o caso que importa: em pt-BR pode ser 1,5 ou 15 — e adivinhar é proibido."""
    assert parse_legend_quantity(text) is None


@pytest.mark.parametrize(
    ("text", "expected"),
    [("M2", ("m2", True)), ("m²", ("m2", True)), ("UNID.", ("un", True)), ("ML", ("m", True))],
)
def test_known_units_are_normalised(text: str, expected: tuple[str, bool]) -> None:
    assert normalized_legend_unit(text) == expected


def test_unknown_unit_is_preserved_literally_and_absent_unit_becomes_unknown() -> None:
    assert normalized_legend_unit("VB") == ("VB", False)
    assert normalized_legend_unit(None) == ("unknown", False)
    assert normalized_legend_unit("   ") == ("unknown", False)


# --------------------------------------------------------------------------------------
# takeoff_packet_from_legend
# --------------------------------------------------------------------------------------


def test_a_clear_row_becomes_a_proposed_item_with_quantity_and_normalised_unit() -> None:
    packet = _packet_from(_row())

    item = packet.items[0]
    assert item.status is TakeoffItemStatus.PROPOSED
    assert item.quantity == Decimal("61.20")
    assert item.unit == "m2"
    assert item.label == "PISO INTERTRAVADO"
    assert item.raw_text == "PISO INTERTRAVADO 61,20 M2"
    assert item.source == "legend_extraction"
    assert item.extractor == _EXTRACTOR
    assert item.extractor_version == _EXTRACTOR_VERSION
    assert item.decision is None


@pytest.mark.parametrize(
    "overrides",
    [
        {"legibility": "illegible"},
        {"legibility": "ambiguous"},
        {"quantity_text": None},
        {"quantity_text": "---"},
        {"quantity_text": "1.5"},
        {"unit_text": "VB"},
        {"unit_text": None},
        {"label": None},
    ],
)
def test_any_doubt_in_the_row_produces_an_ambiguous_item_without_quantity(
    overrides: dict[str, object],
) -> None:
    packet = _packet_from(_row(**overrides))  # type: ignore[arg-type]

    item = packet.items[0]
    assert item.status is TakeoffItemStatus.AMBIGUOUS
    assert item.quantity is None


def test_a_row_without_a_label_falls_back_to_the_line_as_written() -> None:
    packet = _packet_from(_row(label=None, raw_text="LINHA SEM ROTULO 12,00 M2"))

    assert packet.items[0].label == "LINHA SEM ROTULO 12,00 M2"


def test_an_unmappable_unit_keeps_the_literal_written_on_the_plate() -> None:
    packet = _packet_from(_row(unit_text="VB"))

    assert packet.items[0].unit == "VB"


def test_a_row_without_a_unit_declares_it_unknown_instead_of_guessing() -> None:
    packet = _packet_from(_row(unit_text=None))

    assert packet.items[0].unit == "unknown"


def test_no_item_is_ever_born_confirmed() -> None:
    packet = _packet_from(_row(), _row(legibility="illegible", raw_text="OUTRA LINHA"))

    assert all(
        item.status in {TakeoffItemStatus.PROPOSED, TakeoffItemStatus.AMBIGUOUS}
        for item in packet.items
    )
    assert packet.confirmed_items() == []
    assert len(packet.pending_items()) == 2


def test_the_bbox_is_scaled_to_the_original_pixels_and_clamped_to_the_page() -> None:
    packet = _packet_from(
        _row(bbox=NormalizedBox(left=0.0, top=0.25, right=1.0, bottom=0.5)),
        _row(
            raw_text="LINHA COM RUIDO 4 UN",
            bbox=NormalizedBox(left=0.5, top=0.5, right=1.0, bottom=1.0),
        ),
    )

    first = packet.items[0].evidence.bbox
    assert (first.left, first.top, first.right, first.bottom) == (0, 50, 400, 100)
    second = packet.items[1].evidence.bbox
    assert (second.left, second.top, second.right, second.bottom) == (200, 100, 400, 200)


def test_a_bbox_that_collapses_after_rounding_is_refused_by_the_domain() -> None:
    """Âncora de evidência sem área não mostra onde o número foi lido: recusa, não conserto."""
    with pytest.raises(ValidationError) as raised:
        _packet_from(_row(bbox=NormalizedBox(left=0.5, top=0.2, right=0.5001, bottom=0.4)))

    assert "TAKEOFF_BBOX_INVALID" in valuation_error_codes(raised.value)


def test_item_ids_are_deterministic_and_survive_a_repeated_label() -> None:
    """Prancha real repete rótulo; o índice desambigua sem inventar identidade."""
    rows = (
        _row(raw_text="PISO INTERTRAVADO 61,20 M2"),
        _row(raw_text="PISO INTERTRAVADO 12,00 M2", quantity_text="12,00"),
    )

    first = _packet_from(*rows)
    second = _packet_from(*rows)

    assert [item.id for item in first.items] == [item.id for item in second.items]
    assert first.items[0].id != first.items[1].id
    assert first.items[0].id == legend_item_id(_PLATE_ID, 0, "PISO INTERTRAVADO 61,20 M2")


def test_an_extraction_without_rows_refuses_instead_of_publishing_an_empty_packet() -> None:
    with pytest.raises(ValuationValidationError) as raised:
        _packet_from()

    assert raised.value.code == "LEGEND_EXTRACTION_EMPTY"


def test_the_extractor_label_stays_inside_the_domain_limit() -> None:
    label = extractor_label("bedrock_anthropic", "x" * 200)

    assert len(label) == 80
    assert label.startswith("bedrock_anthropic:")


# --------------------------------------------------------------------------------------
# run_legend_extraction — gate primeiro, rede depois
# --------------------------------------------------------------------------------------


def _png(path: Path) -> Path:
    Image.new("RGB", (_IMAGE_WIDTH, _IMAGE_HEIGHT), "white").save(path, format="PNG")
    return path


def _manifest(path: Path, *, source_digest: str, page_digest: str) -> Path:
    path.write_text(
        json.dumps({"source_sha256": source_digest, "pages": [{"image_sha256": page_digest}]}),
        encoding="utf-8",
    )
    return path


def _adapter() -> FixtureProviderAdapter:
    return FixtureProviderAdapter(
        provider=ProviderName.ANTHROPIC,
        model_id="fixture-legend-v1",
        outputs={
            PromptTask.LEGEND_EXTRACTION: LegendExtractionOutput(
                rows=[_row(), _row(raw_text="LINHA ILEGIVEL", legibility="illegible")]
            )
        },
    )


def _run(image: Path, manifest: Path):  # type: ignore[no-untyped-def]
    return run_legend_extraction(image, manifest, _adapter(), plate_id=_PLATE_ID, page_number=1)


def test_the_extraction_binds_the_packet_to_the_page_and_to_the_authorised_document(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    image = _png(tmp_path / "prancha.png")
    image_digest = hashlib.sha256(image.read_bytes()).hexdigest()
    document_digest = "d" * 64
    manifest = _manifest(
        tmp_path / "manifest.json", source_digest=document_digest, page_digest=image_digest
    )
    monkeypatch.setenv(ALLOWLIST, document_digest)

    result = _run(image, manifest)

    assert result.source_sha256 == document_digest
    assert result.packet.image_sha256 == image_digest
    assert result.packet.source_pdf_sha256 == document_digest
    assert result.packet.confirmed_items() == []
    assert [item.status for item in result.packet.items] == [
        TakeoffItemStatus.PROPOSED,
        TakeoffItemStatus.AMBIGUOUS,
    ]
    assert result.execution.prompt.prompt_id == PromptTask.LEGEND_EXTRACTION.value
    assert result.packet.items[0].extractor == "anthropic:fixture-legend-v1"


def test_a_page_outside_the_manifest_is_refused_before_the_provider_is_called(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    image = _png(tmp_path / "prancha.png")
    manifest = _manifest(tmp_path / "manifest.json", source_digest="d" * 64, page_digest="e" * 64)
    monkeypatch.setenv(ALLOWLIST, "d" * 64)

    with pytest.raises(ExtractionNotAllowlistedError, match="não pertence ao manifest"):
        _run(image, manifest)


def test_a_document_outside_the_allowlist_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    image = _png(tmp_path / "prancha.png")
    image_digest = hashlib.sha256(image.read_bytes()).hexdigest()
    manifest = _manifest(
        tmp_path / "manifest.json", source_digest="d" * 64, page_digest=image_digest
    )
    monkeypatch.setenv(ALLOWLIST, "")

    with pytest.raises(ExtractionNotAllowlistedError, match="allowlist"):
        _run(image, manifest)
