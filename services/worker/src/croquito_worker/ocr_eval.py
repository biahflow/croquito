"""Eval determinística da corroboração de OCR usando a prancha e a fixture sintéticas."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from typing import cast

from pydantic import BaseModel, ConfigDict, Field

from croquito_worker.io_utils import atomic_write_text
from croquito_worker.provider_review import build_provider_review_snapshot
from croquito_worker.providers import (
    FixtureProviderAdapter,
    NormalizedBox,
    OcrLineOutput,
    OcrOutput,
    PromptTask,
    ProviderSuite,
    build_synthetic_provider_suite,
)
from croquito_worker.synthetic import render_synthetic_input

DATASET_ID: str = "synthetic-ocr-eval-v1"
"""Dataset da eval; separado do `provider-contract-demo` para não colidir digest/artefatos."""


class OcrEvalReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dataset_id: str
    reading_count: int = Field(ge=0)
    confirmed_count: int = Field(ge=0)
    confirmation_recall: float = Field(ge=0, le=1)
    false_confirmed_count: int = Field(ge=0)
    passed: bool
    thresholds: dict[str, float]


def _decoy_ocr_suite() -> ProviderSuite:
    """A mesma suite sintética, mas com a cota "25,90 m" só reaparecendo longe do lugar
    certo — o falso-confirmado por texto repetido é exatamente o risco conhecido da T3.

    A linha de OCR verdadeira da leitura 1 é removida da fixture; uma decoy com o mesmo
    texto normalizado é inserida numa bbox que não intersecta a bbox de nenhuma leitura.
    Se a corroboração confirmasse por texto sozinho, a leitura 1 sairia confirmada mesmo
    sem evidência espacial real — é isso que este cenário nega.
    """
    base = build_synthetic_provider_suite()
    ocr_adapter = cast(FixtureProviderAdapter, base.ocr)
    original_output = cast(OcrOutput, ocr_adapter.outputs[PromptTask.OCR])
    kept_lines = [line for line in original_output.lines if line.raw_text != "25,90 m"]
    decoy_line = OcrLineOutput(
        raw_text="25,90 m",
        bbox=NormalizedBox(left=0.60, top=0.80, right=0.74, bottom=0.86),
        text_type="printed",
    )
    decoy_output = OcrOutput(lines=[decoy_line, *kept_lines])
    decoy_ocr = replace(ocr_adapter, outputs={PromptTask.OCR: decoy_output})
    return replace(base, ocr=decoy_ocr)


def run_ocr_corroboration_eval(output_dir: Path) -> tuple[OcrEvalReport, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    input_path = output_dir / "ocr-eval-fixture.png"
    render_synthetic_input(input_path)

    # Caso positivo: fixture padrão do contrato, onde o OCR confirma as três leituras.
    positive_snapshot = build_provider_review_snapshot(
        input_path, dataset_id=DATASET_ID, suite=build_synthetic_provider_suite()
    )
    reading_count = len(positive_snapshot.packet.readings)
    confirmed_count = sum(
        1 for note in positive_snapshot.packet.safety_notes if note.endswith("_OCR_CONFIRMED")
    )
    confirmation_recall = confirmed_count / reading_count if reading_count else 0.0

    # Caso negativo: decoy espacial da leitura 1 — nega o falso-confirmado por texto.
    negative_snapshot = build_provider_review_snapshot(
        input_path, dataset_id=DATASET_ID, suite=_decoy_ocr_suite()
    )
    false_confirmed_count = sum(
        1 for note in negative_snapshot.packet.safety_notes if note == "READING_1_OCR_CONFIRMED"
    )

    thresholds = {"confirmation_recall": 1.0, "false_confirmed_count": 0.0}
    report = OcrEvalReport(
        dataset_id=DATASET_ID,
        reading_count=reading_count,
        confirmed_count=confirmed_count,
        confirmation_recall=confirmation_recall,
        false_confirmed_count=false_confirmed_count,
        passed=(
            confirmation_recall >= thresholds["confirmation_recall"]
            and false_confirmed_count <= thresholds["false_confirmed_count"]
        ),
        thresholds=thresholds,
    )
    report_path = output_dir / "ocr-eval.json"
    serialized_report = json.dumps(
        report.model_dump(mode="json"),
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    )
    atomic_write_text(report_path, f"{serialized_report}\n")
    return report, report_path
