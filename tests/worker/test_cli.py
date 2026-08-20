"""Wiring da CLI para `transcribe-readings` e `readings-to-packet`.

Cobre exit codes e erros de uso (padrão dos comandos vizinhos) e um caminho feliz por
comando, com `build_extraction_arm` trocado por um adapter fake — nenhum teste aqui toca
rede ou exige variável de ambiente de credencial.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from PIL import Image

from croquito_worker import cli
from croquito_worker.providers import (
    FixtureProviderAdapter,
    MeasurementExtractionOutput,
    MeasurementReadingOutput,
    NormalizedBox,
    PromptTask,
    ProviderAdapter,
    ProviderName,
    TargetHint,
)
from croquito_worker.synthetic import render_synthetic_input
from croquito_worker.transcription import TranscriptionArtifact
from tests.bundles import build_manifest, build_packet

ALLOWLIST = "CROQUITO_AI_EXTRACTION_ALLOWED_DIGESTS"


def _run_main(monkeypatch: pytest.MonkeyPatch, argv: list[str]) -> int:
    monkeypatch.setattr("sys.argv", ["croquito-demo", *argv])
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
        "croquito_worker.providers.build_extraction_arm", _fake_build_extraction_arm
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


CHAIN_TOTAL_ID = "rd_5555555555555555"
CHAIN_PART_IDS = ("rd_6666666666666666", "rd_7777777777777777")
CHAIN_ODD_ID = "rd_8888888888888888"


def _chain_packet(tmp_path: Path) -> Path:
    """Pacote com quatro cotas de planta confirmadas: 12,00 + 13,90 fecham os 25,90."""
    from croquito_worker.review import (
        DimensionReading,
        EvidenceRegion,
        HumanDecision,
        PixelBox,
        ReadingStatus,
        ReviewPacket,
    )

    digest = "c" * 64
    values = (
        (CHAIN_TOTAL_ID, "25,90", "25.90", 0),
        (CHAIN_PART_IDS[0], "12,00", "12.00", 30),
        (CHAIN_PART_IDS[1], "13,90", "13.90", 60),
        (CHAIN_ODD_ID, "3,00", "3.00", 90),
    )
    packet = ReviewPacket(
        dataset_id="chain-fixture",
        page_number=1,
        image_sha256=digest,
        readings=[
            DimensionReading(
                id=reading_id,
                evidence=EvidenceRegion(
                    dataset_id="chain-fixture",
                    page_number=1,
                    image_sha256=digest,
                    bbox=PixelBox(left=left, top=5, right=left + 20, bottom=15),
                ),
                raw_text=raw_text,
                value_si=Decimal(value_si),
                unit="m",
                kind="length",
                written_decimals=2,
                target_hint="cadeia sintética",
                extractor="local-fixture",
                extractor_version="v1",
                status=ReadingStatus.CONFIRMED,
                decision=HumanDecision(
                    decision_id=f"hd_{index}{'a' * 15}",
                    action="confirm",
                    reviewer_id="reviewer",
                    reviewer_role="engineer",
                    decided_at=datetime.now(UTC),
                    note="Cota de planta conferida na folha.",
                ),
            )
            for index, (reading_id, raw_text, value_si, left) in enumerate(values)
        ],
        safety_notes=["Fixture local.", "Revisão humana obrigatória."],
    )
    path = tmp_path / "reviewed-packet.json"
    path.write_text(
        json.dumps(packet.model_dump(mode="json"), ensure_ascii=False), encoding="utf-8"
    )
    return path


def test_check_chains_suggests_and_writes_the_same_json(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    packet_path = _chain_packet(tmp_path)
    output = tmp_path / "cadeias" / "sugestoes.json"

    code = _run_main(
        monkeypatch,
        ["check-chains", "--packet", str(packet_path), "--output", str(output)],
    )

    assert code == 0
    payload = json.loads(capsys.readouterr().out.strip())
    assert payload["suggestions"] == 1
    assert payload["safety_status"] == "observational_only"
    assert payload["chains"][0]["total"]["reading_id"] == CHAIN_TOTAL_ID
    assert {part["reading_id"] for part in payload["chains"][0]["parts"]} == set(CHAIN_PART_IDS)
    assert json.loads(output.read_text(encoding="utf-8")) == payload


def test_check_chains_verifies_a_declared_chain_that_closes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    packet_path = _chain_packet(tmp_path)

    code = _run_main(
        monkeypatch,
        [
            "check-chains",
            "--packet",
            str(packet_path),
            "--total",
            CHAIN_TOTAL_ID,
            "--part",
            CHAIN_PART_IDS[0],
            "--part",
            CHAIN_PART_IDS[1],
        ],
    )

    assert code == 0
    payload = json.loads(capsys.readouterr().out.strip())
    assert payload == {
        "closes": True,
        "residual_m": "0.00",
        "tolerance_m": "0.015",
        "issue": None,
    }


def test_check_chains_reports_a_mismatch_without_failing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Divergência sai com 0: o comando não é mais duro que o produto, onde ela é aviso."""
    packet_path = _chain_packet(tmp_path)

    code = _run_main(
        monkeypatch,
        [
            "check-chains",
            "--packet",
            str(packet_path),
            "--total",
            CHAIN_TOTAL_ID,
            "--part",
            CHAIN_PART_IDS[0],
            "--part",
            CHAIN_ODD_ID,
        ],
    )

    assert code == 0
    payload = json.loads(capsys.readouterr().out.strip())
    assert payload["closes"] is False
    assert payload["residual_m"] == "-10.90"
    assert payload["issue"]["code"] == "DIMENSION_CHAIN_MISMATCH"
    assert payload["issue"]["severity"] == "warning"


def test_check_chains_fails_on_a_chain_that_cannot_be_assembled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    packet_path = _chain_packet(tmp_path)

    code = _run_main(
        monkeypatch,
        [
            "check-chains",
            "--packet",
            str(packet_path),
            "--total",
            CHAIN_TOTAL_ID,
            "--part",
            CHAIN_PART_IDS[0],
        ],
    )

    assert code == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "pelo menos duas parcelas" in captured.err


def test_check_chains_refuses_parts_without_a_total(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    packet_path = _chain_packet(tmp_path)

    with pytest.raises(SystemExit) as excinfo:
        _run_main(
            monkeypatch,
            ["check-chains", "--packet", str(packet_path), "--part", CHAIN_PART_IDS[0]],
        )

    assert excinfo.value.code == 2
