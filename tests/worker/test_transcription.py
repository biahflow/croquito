"""Testes de `transcribe-readings` e `readings-to-packet`, sempre com adapter fake.

Nenhum teste aqui depende de credencial de provider: `authorize_page` já bloqueia a
chamada antes de qualquer adapter ser tocado, e os adapters usados são
`FixtureProviderAdapter`/dublês locais determinísticos.
"""

from __future__ import annotations

import hashlib
import json
from decimal import Decimal
from pathlib import Path

import pytest
from PIL import Image

from croquito_worker.extraction_eval import ExtractionCandidate, ExtractionNotAllowlistedError
from croquito_worker.providers import (
    FixtureProviderAdapter,
    MeasurementExtractionOutput,
    MeasurementReadingOutput,
    NormalizedBox,
    PromptTask,
    ProviderExecution,
    ProviderName,
    ProviderRequest,
    TargetHint,
)
from croquito_worker.review import (
    DimensionReading,
    EvidenceRegion,
    PixelBox,
    ReadingStatus,
    ReviewPacket,
)
from croquito_worker.synthetic import render_synthetic_input
from croquito_worker.transcription import (
    CollisionResolutionNote,
    TranscriptionArtifact,
    TranscriptionMergeError,
    merge_readings_into_packet,
    run_transcription,
    write_merge_artifacts,
)
from tests.bundles import (
    CIRCLE_READING_ID,
    HEIGHT_READING_ID,
    WIDTH_M,
    WIDTH_READING_ID,
    build_manifest,
    build_packet,
)

ALLOWLIST = "CROQUITO_AI_EXTRACTION_ALLOWED_DIGESTS"


class _NeverCalledAdapter:
    """Prova de que `authorize_page` recusa antes de qualquer chamada externa."""

    def execute(self, request: ProviderRequest) -> ProviderExecution:  # pragma: no cover
        raise AssertionError("o adapter não deveria ser tocado sem digest na allowlist")


def _measurement_adapter(*readings: MeasurementReadingOutput) -> FixtureProviderAdapter:
    output = MeasurementExtractionOutput(readings=list(readings))
    return FixtureProviderAdapter(
        provider=ProviderName.BEDROCK_ANTHROPIC,
        model_id="anthropic.claude-sonnet-5",
        outputs={PromptTask.MEASUREMENT_EXTRACTION: output},
    )


def _manifest(tmp_path: Path, source: Path, *, document_digest: str) -> Path:
    path = tmp_path / "manifest.json"
    path.write_text(
        json.dumps(
            {
                "source_sha256": document_digest,
                "pages": [{"image_sha256": hashlib.sha256(source.read_bytes()).hexdigest()}],
            }
        )
    )
    return path


def _prepare(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path]:
    source = tmp_path / "entrada.png"
    render_synthetic_input(source)
    document_digest = "d" * 64
    monkeypatch.setenv(ALLOWLIST, document_digest)
    return source, _manifest(tmp_path, source, document_digest=document_digest)


def _reading(
    *,
    raw_text: str,
    kind: str,
    value: str | None,
    unit: str,
    bbox: NormalizedBox,
    legibility: str = "clear",
    entity_label: str = "campo",
    feature: str = "largura",
    written_precision: int = 2,
    alternatives: list[str] | None = None,
) -> MeasurementReadingOutput:
    return MeasurementReadingOutput(
        raw_text=raw_text,
        kind=kind,
        normalized_value=Decimal(value) if value is not None else None,
        unit=unit,
        written_precision=written_precision,
        bbox=bbox,
        target_hint=TargetHint(entity_label=entity_label, feature=feature),
        legibility=legibility,
        alternatives=alternatives or [],
    )


# --------------------------------------------------------------------------------------
# transcribe-readings
# --------------------------------------------------------------------------------------


def test_transcribe_readings_writes_deterministic_artifacts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source, manifest = _prepare(tmp_path, monkeypatch)
    adapter = _measurement_adapter(
        _reading(
            raw_text="25,90 m",
            kind="length",
            value="25.90",
            unit="m",
            bbox=NormalizedBox(left=0.08, top=0.12, right=0.20, bottom=0.18),
            legibility="clear",
        ),
        _reading(
            raw_text="Ø 6,00 m",
            kind="diameter",
            value="6.00",
            unit="m",
            bbox=NormalizedBox(left=0.40, top=0.12, right=0.54, bottom=0.18),
            legibility="ambiguous",
        ),
    )
    candidate = ExtractionCandidate(name="sonnet", adapter=adapter)

    artifact, report, readings_path, report_path = run_transcription(
        source, candidate, tmp_path / "out", manifest_path=manifest
    )

    assert readings_path == tmp_path / "out" / "sonnet-readings.json"
    assert report_path == tmp_path / "out" / "transcription-report.json"
    assert readings_path.is_file()
    assert report_path.is_file()

    assert artifact.arm == "sonnet"
    assert artifact.provider == "bedrock_anthropic"
    assert artifact.model_id == "anthropic.claude-sonnet-5"
    assert artifact.prompt_id == "measurement-extraction"
    assert len(artifact.output.readings) == 2

    roundtrip = TranscriptionArtifact.model_validate_json(readings_path.read_text())
    assert roundtrip == artifact

    assert report.reading_count == 2
    assert report.counts_by_kind == {"length": 1, "diameter": 1}
    assert report.counts_by_legibility == {"clear": 1, "ambiguous": 1}
    assert report.arm == "sonnet"
    assert report.provider == "bedrock_anthropic"

    # O report é o artefato "seguro": nenhum texto de cota deve vazar nele.
    report_text = report_path.read_text(encoding="utf-8")
    assert "25,90" not in report_text
    assert "6,00" not in report_text
    # As leituras cruas ficam só no artefato dedicado a isso.
    assert "25,90" in readings_path.read_text(encoding="utf-8")


def test_transcribe_readings_refuses_without_allowlisted_digest_and_never_touches_the_adapter(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "entrada.png"
    render_synthetic_input(source)
    manifest = _manifest(tmp_path, source, document_digest="d" * 64)
    monkeypatch.setenv(ALLOWLIST, "")

    candidate = ExtractionCandidate(name="sonnet", adapter=_NeverCalledAdapter())

    with pytest.raises(ExtractionNotAllowlistedError, match="allowlist"):
        run_transcription(source, candidate, tmp_path / "out", manifest_path=manifest)


# --------------------------------------------------------------------------------------
# readings-to-packet
# --------------------------------------------------------------------------------------


def _seed_bundle(tmp_path: Path, *, dataset_id: str = "golden-local-v1") -> tuple[Path, Path, str]:
    image_path = tmp_path / "page-001.png"
    Image.new("RGB", (40, 30), "white").save(image_path)
    digest = hashlib.sha256(image_path.read_bytes()).hexdigest()
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            build_manifest(dataset_id=dataset_id, digest=digest, source_sha256="e" * 64).model_dump(
                mode="json"
            )
        )
    )
    return image_path, manifest_path, digest


def _artifact(*readings: MeasurementReadingOutput) -> TranscriptionArtifact:
    return TranscriptionArtifact(
        arm="sonnet",
        provider="bedrock_anthropic",
        model_id="anthropic.claude-sonnet-5",
        prompt_id="measurement-extraction",
        prompt_version="measurement-extraction@1.1.0",
        prompt_hash="a" * 64,
        schema_version="1.0.0",
        input_digest="b" * 64,
        latency_ms=12,
        raw_response_ref=None,
        output=MeasurementExtractionOutput(readings=list(readings)),
    )


def test_merge_converts_one_full_reading_field_by_field(tmp_path: Path) -> None:
    image_path, manifest_path, digest = _seed_bundle(tmp_path)
    base_packet = build_packet(dataset_id="golden-local-v1", digest=digest)
    artifact = _artifact(
        _reading(
            raw_text="1,20 m",
            kind="radius",
            value="1.20",
            unit="m",
            bbox=NormalizedBox(left=0.5, top=0.5, right=0.75, bottom=0.875),
            legibility="clear",
            entity_label="poste",
            feature="raio",
            written_precision=2,
        )
    )

    merged, report = merge_readings_into_packet(
        artifact, base_packet, manifest_path=manifest_path, image_path=image_path
    )

    assert report.accepted_count == 1
    assert report.discarded_count == 0
    assert report.base_reading_count == 3
    assert report.total_reading_count == 4

    new_reading = next(
        reading
        for reading in merged.readings
        if reading.id
        not in {
            WIDTH_READING_ID,
            HEIGHT_READING_ID,
            CIRCLE_READING_ID,
        }
    )
    expected_id = f"rd_{hashlib.sha256(f'{digest}:1'.encode()).hexdigest()[:16]}"
    assert new_reading.id == expected_id
    assert new_reading.evidence == EvidenceRegion(
        dataset_id="golden-local-v1",
        page_number=1,
        image_sha256=digest,
        bbox=PixelBox(left=20, top=15, right=30, bottom=26),
    )
    assert new_reading.raw_text == "1,20 m"
    assert new_reading.value_si == Decimal("1.20")
    assert new_reading.unit == "m"
    assert new_reading.kind == "radius"
    assert new_reading.written_decimals == 2
    assert new_reading.target_hint == "poste: raio"
    assert new_reading.extractor == "bedrock_anthropic"
    assert new_reading.extractor_version == "anthropic.claude-sonnet-5+measurement-extraction@1.1.0"
    assert len(new_reading.provider_lineage) == 1
    assert new_reading.provider_lineage[0].provider == "bedrock_anthropic"
    assert new_reading.status == ReadingStatus.PROPOSED
    assert new_reading.decision is None

    # Leituras do pacote base permanecem intocadas.
    base_by_id = {reading.id: reading for reading in base_packet.readings}
    for reading in merged.readings:
        if reading.id in base_by_id:
            assert reading == base_by_id[reading.id]

    # O pacote resultante passa pela validação integral (validate_references incluso).
    ReviewPacket.model_validate(merged.model_dump(mode="json"))


def test_merge_discards_readings_with_a_reason_and_no_dimension_content(tmp_path: Path) -> None:
    image_path, manifest_path, digest = _seed_bundle(tmp_path)
    base_packet = build_packet(dataset_id="golden-local-v1", digest=digest)
    artifact = _artifact(
        _reading(
            raw_text="30 cm",
            kind="length",
            value="30",
            unit="cm",
            bbox=NormalizedBox(left=0.0, top=0.0, right=0.1, bottom=0.1),
        ),
        _reading(
            raw_text="3 postes",
            kind="count",
            value="3",
            unit="m",
            bbox=NormalizedBox(left=0.0, top=0.0, right=0.1, bottom=0.1),
        ),
        _reading(
            raw_text="0,90 m",
            kind="length",
            value="0.90",
            unit="m",
            bbox=NormalizedBox(left=0.50, top=0.1, right=0.505, bottom=0.9),
        ),
    )

    _merged, report = merge_readings_into_packet(
        artifact, base_packet, manifest_path=manifest_path, image_path=image_path
    )

    assert report.accepted_count == 0
    assert report.discarded_count == 3
    assert report.discarded_by_reason == {
        "unsupported_unit": 1,
        "unsupported_kind": 1,
        "degenerate_bbox": 1,
    }
    reasons_by_index = {note.index: note.reason for note in report.discarded}
    assert reasons_by_index == {1: "unsupported_unit", 2: "unsupported_kind", 3: "degenerate_bbox"}
    # Nenhuma nota de descarte carrega o raw_text original da cota (só código de unidade
    # e tipo, que já são vocabulário controlado do contrato, não conteúdo do croqui).
    for note in report.discarded:
        assert "30" not in note.detail
        assert "postes" not in note.detail
        assert "0,90" not in note.detail


def test_merge_discards_a_new_reading_that_duplicates_a_base_reading(tmp_path: Path) -> None:
    image_path, manifest_path, digest = _seed_bundle(tmp_path)
    base_packet = build_packet(dataset_id="golden-local-v1", digest=digest)
    artifact = _artifact(
        _reading(
            raw_text="25,90 m",
            kind="width",
            value=WIDTH_M,
            unit="m",
            bbox=NormalizedBox(left=0.0, top=0.2, right=0.3, bottom=0.4),
        )
    )

    _merged, report = merge_readings_into_packet(
        artifact, base_packet, manifest_path=manifest_path, image_path=image_path
    )

    assert report.accepted_count == 0
    assert report.duplicate_count == 1
    assert report.discarded_by_reason == {"duplicate": 1}
    assert report.discarded[0].reason == "duplicate"
    assert WIDTH_READING_ID in report.discarded[0].detail


def test_merge_resolves_an_id_collision_with_a_deterministic_suffix(tmp_path: Path) -> None:
    image_path = tmp_path / "page.png"
    Image.new("RGB", (40, 30), "white").save(image_path)
    digest = hashlib.sha256(image_path.read_bytes()).hexdigest()
    colliding_id = f"rd_{hashlib.sha256(f'{digest}:1'.encode()).hexdigest()[:16]}"

    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "dataset_id": "colisao-v1",
                "pages": [
                    {
                        "image_sha256": digest,
                        "number": 1,
                        "rendered_width_px": 40,
                        "rendered_height_px": 30,
                    }
                ],
            }
        )
    )
    base_packet = ReviewPacket(
        dataset_id="colisao-v1",
        page_number=1,
        image_sha256=digest,
        readings=[
            DimensionReading(
                id=colliding_id,
                evidence=EvidenceRegion(
                    dataset_id="colisao-v1",
                    page_number=1,
                    image_sha256=digest,
                    bbox=PixelBox(left=0, top=0, right=5, bottom=5),
                ),
                raw_text="1,00 m",
                value_si=Decimal("1.00"),
                unit="m",
                kind="length",
                written_decimals=2,
                target_hint="leitura já existente",
                extractor="local",
                extractor_version="v0",
                status=ReadingStatus.PROPOSED,
            )
        ],
        safety_notes=["Fixture local.", "Revisão humana obrigatória."],
    )
    artifact = _artifact(
        _reading(
            raw_text="2,00 m",
            kind="length",
            value="2.00",
            unit="m",
            bbox=NormalizedBox(left=0.5, top=0.5, right=0.75, bottom=0.9),
            entity_label="poste",
            feature="altura",
        )
    )

    merged, report = merge_readings_into_packet(
        artifact, base_packet, manifest_path=manifest_path, image_path=image_path
    )

    expected_resolved_id = f"rd_{hashlib.sha256(f'{digest}:1:1'.encode()).hexdigest()[:16]}"
    assert report.id_collisions == [
        CollisionResolutionNote(
            index=1,
            original_id=colliding_id,
            resolved_id=expected_resolved_id,
            attempts=1,
        )
    ]
    new_ids = {reading.id for reading in merged.readings} - {colliding_id}
    assert new_ids == {expected_resolved_id}
    assert report.total_reading_count == 2


def test_merge_refuses_when_the_image_does_not_belong_to_the_manifest(tmp_path: Path) -> None:
    image_path, _manifest_path, digest = _seed_bundle(tmp_path)
    base_packet = build_packet(dataset_id="golden-local-v1", digest=digest)
    artifact = _artifact()
    other_manifest = tmp_path / "outro-manifest.json"
    other_manifest.write_text(json.dumps({"dataset_id": "golden-local-v1", "pages": []}))

    with pytest.raises(TranscriptionMergeError, match="não pertence ao manifest"):
        merge_readings_into_packet(
            artifact, base_packet, manifest_path=other_manifest, image_path=image_path
        )


def test_write_merge_artifacts_creates_both_files(tmp_path: Path) -> None:
    image_path, manifest_path, digest = _seed_bundle(tmp_path)
    base_packet = build_packet(dataset_id="golden-local-v1", digest=digest)
    artifact = _artifact()

    merged, report = merge_readings_into_packet(
        artifact, base_packet, manifest_path=manifest_path, image_path=image_path
    )
    packet_path, report_path = write_merge_artifacts(merged, report, tmp_path / "out")

    assert packet_path == tmp_path / "out" / "review-packet-merged.json"
    assert report_path == tmp_path / "out" / "merge-report.json"
    assert ReviewPacket.model_validate_json(packet_path.read_text()) == merged
