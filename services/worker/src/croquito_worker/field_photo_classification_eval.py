"""Gate offline e rodada real, única, da classificação visual de campo (F-030 T6)."""

from __future__ import annotations

import hashlib
import json
import os
import re
from decimal import Decimal
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from croquito_worker.extraction_eval import prepare_transmission
from croquito_worker.io_utils import atomic_write_text
from croquito_worker.providers import (
    PROMPT_SPECS,
    AnthropicProviderAdapter,
    BudgetedProviderAdapter,
    CostBudget,
    FieldPhotoCategory,
    FieldPhotoClassificationOutput,
    PromptTask,
    ProviderExecutionError,
    build_request,
)

LIVE_CASE_COUNT = 6
LIVE_MODEL = "claude-opus-5"
CALL_RESERVE_USD = Decimal("0.75")
ABSOLUTE_BUDGET_USD = Decimal("5.00")
_FORBIDDEN_VISUAL_INFERENCE = re.compile(
    r"(?:\d|\b(?:mm|cm|metro|metros|altura|largura|distância|area|área|coordenad|"
    r"ângulo|geometri|precisão|blocker)\w*)",
    re.IGNORECASE,
)


class ClassificationCorpusCase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: str = Field(min_length=1, max_length=80)
    image: str = Field(min_length=1, max_length=500)
    expected_category: FieldPhotoCategory


class ClassificationCorpus(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    schema_version: Literal["field-photo-classification-corpus/1"] = Field(
        alias="schema", serialization_alias="schema"
    )
    cases: list[ClassificationCorpusCase] = Field(
        min_length=LIVE_CASE_COUNT, max_length=LIVE_CASE_COUNT
    )


class ClassificationEvalCase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: str
    expected_category: FieldPhotoCategory
    actual_category: FieldPhotoCategory | None = None
    confidence: Literal["high", "medium", "low"] | None = None
    schema_valid: bool
    lineage_valid: bool
    non_geometric: bool
    correct: bool
    failure_code: str | None = None
    input_sha256: str | None = None


class ClassificationEvalReport(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    schema_version: Literal["field-photo-classification-eval/1"] = Field(
        default="field-photo-classification-eval/1",
        alias="schema",
        serialization_alias="schema",
    )
    mode: Literal["offline", "live"]
    candidate: str
    prompt_version: str
    prompt_template_hash: str
    cases: list[ClassificationEvalCase]
    schema_lineage_valid_count: int = Field(ge=0)
    non_geometric_count: int = Field(ge=0)
    correct_count: int = Field(ge=0)
    high_confidence_error_count: int = Field(ge=0)
    estimated_cost_usd: Decimal = Field(ge=0)
    passed: bool


def _non_geometric(output: FieldPhotoClassificationOutput) -> bool:
    text = " ".join([output.description, *output.topology_notes])
    return _FORBIDDEN_VISUAL_INFERENCE.search(text) is None


def _report(
    *,
    mode: Literal["offline", "live"],
    candidate: str,
    cases: list[ClassificationEvalCase],
    estimated_cost_usd: Decimal,
) -> ClassificationEvalReport:
    valid = sum(case.schema_valid and case.lineage_valid for case in cases)
    non_geometric = sum(case.non_geometric for case in cases)
    correct = sum(case.correct for case in cases)
    high_errors = sum(case.confidence == "high" and not case.correct for case in cases)
    required = len(cases)
    return ClassificationEvalReport(
        mode=mode,
        candidate=candidate,
        prompt_version=PROMPT_SPECS[PromptTask.FIELD_PHOTO_CLASSIFICATION].prompt_version,
        prompt_template_hash=PROMPT_SPECS[PromptTask.FIELD_PHOTO_CLASSIFICATION].template_hash,
        cases=cases,
        schema_lineage_valid_count=valid,
        non_geometric_count=non_geometric,
        correct_count=correct,
        high_confidence_error_count=high_errors,
        estimated_cost_usd=estimated_cost_usd,
        passed=(
            valid == required
            and non_geometric == required
            and correct >= (5 if mode == "live" else required)
            and high_errors == 0
            and estimated_cost_usd <= ABSOLUTE_BUDGET_USD
        ),
    )


def _write_report(report: ClassificationEvalReport, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "field-photo-classification-eval.json"
    atomic_write_text(
        path,
        json.dumps(
            report.model_dump(mode="json", by_alias=True),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
    )
    return path


def run_offline_classification_eval(
    output_dir: Path,
) -> tuple[ClassificationEvalReport, Path]:
    """Exercita schema fechado, categorias e proibições sem chave, rede ou foto real."""
    cases: list[ClassificationEvalCase] = []
    categories: tuple[FieldPhotoCategory, ...] = (
        "MURO",
        "ALAMBRADO",
        "PORTAO",
        "PATAMAR",
        "EQUIPAMENTOS",
        "DETALHES",
        "UNKNOWN",
    )
    for index, category in enumerate(categories, start=1):
        output = FieldPhotoClassificationOutput(
            category=category,
            description=f"Assunto sintético {category.lower()} visível.",
            topology_notes=["Elemento junto ao limite registrado."],
            confidence="medium",
        )
        cases.append(
            ClassificationEvalCase(
                case_id=f"offline-{index}",
                expected_category=category,
                actual_category=output.category,
                confidence=output.confidence,
                schema_valid=True,
                lineage_valid=(
                    PROMPT_SPECS[PromptTask.FIELD_PHOTO_CLASSIFICATION].schema_version == "1.0.0"
                ),
                non_geometric=_non_geometric(output),
                correct=output.category == category,
            )
        )
    # As três formas perigosas são recusadas pelo contrato, e portanto fazem parte do gate.
    for payload in (
        {"category": "ARVORE", "description": "Árvore", "confidence": "medium"},
        {"category": "MURO", "description": "Muro", "confidence": 0.92},
        {
            "category": "MURO",
            "description": "Muro",
            "confidence": "high",
            "measurement": "2 m",
        },
    ):
        try:
            FieldPhotoClassificationOutput.model_validate(payload)
        except ValidationError:
            continue
        raise AssertionError("schema aceitou categoria, probabilidade ou medida proibida")
    report = _report(
        mode="offline", candidate="fixture-contract-v1", cases=cases, estimated_cost_usd=Decimal(0)
    )
    return report, _write_report(report, output_dir)


def _live_environment() -> tuple[str, CostBudget]:
    if os.getenv("CROQUITO_OPENAI_ARM_ENABLED", "").strip().lower() != "false":
        raise ValueError("CROQUITO_OPENAI_ARM_ENABLED=false é obrigatório nesta rodada")
    api_key = os.getenv("CROQUITO_ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        raise ValueError("CROQUITO_ANTHROPIC_API_KEY ausente")
    try:
        limit = Decimal(os.environ["CROQUITO_AI_MAX_ESTIMATED_COST_USD"])
        reserve = Decimal(
            os.getenv("CROQUITO_AI_ESTIMATED_COST_PER_LLM_CALL_USD", str(CALL_RESERVE_USD))
        )
    except (KeyError, ArithmeticError) as error:
        raise ValueError("teto e reserva explícitos são obrigatórios") from error
    if limit != ABSOLUTE_BUDGET_USD or reserve != CALL_RESERVE_USD:
        raise ValueError("a rodada exige teto 5.00 e reserva 0.75 por chamada")
    return api_key, CostBudget(limit)


def run_live_classification_eval(
    corpus_path: Path, output_dir: Path
) -> tuple[ClassificationEvalReport, Path]:
    """Executa seis fotos uma vez cada no mesmo Opus; não há retry nem fallback."""
    corpus = ClassificationCorpus.model_validate_json(corpus_path.read_text())
    if len({case.case_id for case in corpus.cases}) != LIVE_CASE_COUNT:
        raise ValueError("os seis case_id precisam ser distintos")
    api_key, budget = _live_environment()
    adapter = BudgetedProviderAdapter(
        AnthropicProviderAdapter(api_key=api_key, model_id=LIVE_MODEL),
        budget=budget,
        estimated_cost_usd=CALL_RESERVE_USD,
    )
    cases: list[ClassificationEvalCase] = []
    for case in corpus.cases:
        source = (corpus_path.parent / case.image).resolve()
        image_bytes, width, height = prepare_transmission(source)
        digest = hashlib.sha256(image_bytes).hexdigest()
        request = build_request(
            PromptTask.FIELD_PHOTO_CLASSIFICATION,
            image_bytes=image_bytes,
            image_sha256=digest,
            image_width_px=width,
            image_height_px=height,
        )
        try:
            execution = adapter.execute(request)
        except ProviderExecutionError as error:
            cases.append(
                ClassificationEvalCase(
                    case_id=case.case_id,
                    expected_category=case.expected_category,
                    schema_valid=False,
                    lineage_valid=False,
                    non_geometric=False,
                    correct=False,
                    failure_code=error.code.value,
                    input_sha256=digest,
                )
            )
            continue
        output = execution.output
        if not isinstance(output, FieldPhotoClassificationOutput):
            raise AssertionError("adapter aceitou saída de outra tarefa")
        lineage_valid = (
            execution.model_id == LIVE_MODEL
            and execution.provider.value == "anthropic"
            and execution.prompt == PROMPT_SPECS[PromptTask.FIELD_PHOTO_CLASSIFICATION]
            and execution.input_digest == digest
        )
        cases.append(
            ClassificationEvalCase(
                case_id=case.case_id,
                expected_category=case.expected_category,
                actual_category=output.category,
                confidence=output.confidence,
                schema_valid=True,
                lineage_valid=lineage_valid,
                non_geometric=_non_geometric(output),
                correct=output.category == case.expected_category,
                input_sha256=digest,
            )
        )
    report = _report(
        mode="live", candidate=LIVE_MODEL, cases=cases, estimated_cost_usd=budget.spent_usd
    )
    return report, _write_report(report, output_dir)


__all__ = [
    "ClassificationCorpus",
    "ClassificationEvalReport",
    "run_live_classification_eval",
    "run_offline_classification_eval",
]
