"""Wiring da CLI para `transcribe-readings` e `readings-to-packet`.

Cobre exit codes e erros de uso (padrão dos comandos vizinhos) e um caminho feliz por
comando, com `build_extraction_arm` trocado por um adapter fake — nenhum teste aqui toca
rede ou exige variável de ambiente de credencial.
"""

from __future__ import annotations

import hashlib
import json
from decimal import Decimal
from pathlib import Path

import pytest
from PIL import Image

from croquitodxf_worker import cli
from croquitodxf_worker.providers import (
    FixtureProviderAdapter,
    MeasurementExtractionOutput,
    MeasurementReadingOutput,
    NormalizedBox,
    PromptTask,
    ProviderAdapter,
    ProviderName,
    TargetHint,
)
from croquitodxf_worker.synthetic import render_synthetic_input
from croquitodxf_worker.transcription import TranscriptionArtifact
from tests.bundles import build_manifest, build_packet

ALLOWLIST = "CROQUITODXF_AI_EXTRACTION_ALLOWED_DIGESTS"


def _run_main(monkeypatch: pytest.MonkeyPatch, argv: list[str]) -> int:
    monkeypatch.setattr("sys.argv", ["croquitodxf-demo", *argv])
    return cli.main()


def test_transcribe_readings_rejects_zero_arms(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with pytest.raises(SystemExit) as excinfo:
        _run_main(
            monkeypatch,
            [
                "transcribe-readings",
                "--image",
                str(tmp_path / "entrada.png"),
                "--manifest",
                str(tmp_path / "manifest.json"),
                "--output",
                str(tmp_path / "out"),
            ],
        )
    assert excinfo.value.code == 2


def test_transcribe_readings_rejects_more_than_one_arm(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with pytest.raises(SystemExit) as excinfo:
        _run_main(
            monkeypatch,
            [
                "transcribe-readings",
                "--image",
                str(tmp_path / "entrada.png"),
                "--manifest",
                str(tmp_path / "manifest.json"),
                "--output",
                str(tmp_path / "out"),
                "--arm",
                "sonnet=bedrock:anthropic.claude-sonnet-5",
                "--arm",
                "opus=bedrock:anthropic.claude-opus-5",
            ],
        )
    assert excinfo.value.code == 2


def test_transcribe_readings_cli_happy_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    source = tmp_path / "entrada.png"
    render_synthetic_input(source)
    document_digest = "d" * 64
    monkeypatch.setenv(ALLOWLIST, document_digest)
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "source_sha256": document_digest,
                "pages": [{"image_sha256": hashlib.sha256(source.read_bytes()).hexdigest()}],
            }
        )
    )

    def _fake_build_extraction_arm(*, provider: str, model_id: str) -> ProviderAdapter:
        assert provider == "bedrock"
        assert model_id == "anthropic.claude-sonnet-5"
        return FixtureProviderAdapter(
            provider=ProviderName.BEDROCK_ANTHROPIC,
            model_id=model_id,
            outputs={
                PromptTask.MEASUREMENT_EXTRACTION: MeasurementExtractionOutput(
                    readings=[
                        MeasurementReadingOutput(
                            raw_text="25,90 m",
                            kind="width",
                            normalized_value=Decimal("25.90"),
                            unit="m",
                            written_precision=2,
                            bbox=NormalizedBox(left=0.08, top=0.12, right=0.20, bottom=0.18),
                            target_hint=TargetHint(entity_label="campo", feature="largura"),
                            legibility="clear",
                        )
                    ]
                )
            },
        )

    monkeypatch.setattr(
        "croquitodxf_worker.providers.build_extraction_arm", _fake_build_extraction_arm
    )

    exit_code = _run_main(
        monkeypatch,
        [
            "transcribe-readings",
            "--image",
            str(source),
            "--manifest",
            str(manifest_path),
            "--output",
            str(tmp_path / "out"),
            "--arm",
            "sonnet=bedrock:anthropic.claude-sonnet-5",
        ],
    )

    assert exit_code == 0
    stdout = json.loads(capsys.readouterr().out)
    assert stdout["arm"] == "sonnet"
    assert stdout["provider"] == "bedrock_anthropic"
    assert stdout["readings"] == 1
    assert (tmp_path / "out" / "sonnet-readings.json").is_file()
    assert (tmp_path / "out" / "transcription-report.json").is_file()


def test_readings_to_packet_cli_happy_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    image_path = tmp_path / "page-001.png"
    Image.new("RGB", (40, 30), "white").save(image_path)
    digest = hashlib.sha256(image_path.read_bytes()).hexdigest()
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            build_manifest(
                dataset_id="golden-local-v1", digest=digest, source_sha256="e" * 64
            ).model_dump(mode="json")
        )
    )
    base_packet_path = tmp_path / "review-packet.json"
    base_packet_path.write_text(
        json.dumps(
            build_packet(dataset_id="golden-local-v1", digest=digest).model_dump(mode="json")
        )
    )
    readings_path = tmp_path / "sonnet-readings.json"
    readings_path.write_text(
        TranscriptionArtifact(
            arm="sonnet",
            provider="bedrock_anthropic",
            model_id="anthropic.claude-sonnet-5",
            prompt_id="measurement-extraction",
            prompt_version="measurement-extraction@1.1.0",
            prompt_hash="a" * 64,
            schema_version="1.0.0",
            input_digest="b" * 64,
            latency_ms=10,
            raw_response_ref=None,
            output=MeasurementExtractionOutput(
                readings=[
                    MeasurementReadingOutput(
                        raw_text="1,20 m",
                        kind="radius",
                        normalized_value=Decimal("1.20"),
                        unit="m",
                        written_precision=2,
                        bbox=NormalizedBox(left=0.5, top=0.5, right=0.75, bottom=0.875),
                        target_hint=TargetHint(entity_label="poste", feature="raio"),
                        legibility="clear",
                    )
                ]
            ),
        ).model_dump_json()
    )

    exit_code = _run_main(
        monkeypatch,
        [
            "readings-to-packet",
            "--readings",
            str(readings_path),
            "--base-packet",
            str(base_packet_path),
            "--manifest",
            str(manifest_path),
            "--image",
            str(image_path),
            "--output",
            str(tmp_path / "out"),
        ],
    )

    assert exit_code == 0
    stdout = json.loads(capsys.readouterr().out)
    assert stdout["base_readings"] == 3
    assert stdout["accepted"] == 1
    assert stdout["duplicates"] == 0
    assert stdout["discarded"] == 0
    assert stdout["total_readings"] == 4
    assert (tmp_path / "out" / "review-packet-merged.json").is_file()
    assert (tmp_path / "out" / "merge-report.json").is_file()
