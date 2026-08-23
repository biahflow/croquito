"""Gates sem rede da rodada real de classificação da F-030."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from croquito_worker.field_photo_classification_eval import (
    ClassificationCorpus,
    run_live_classification_eval,
    run_offline_classification_eval,
)


def test_eval_offline_fecha_schema_lineage_categorias_e_ausencia_de_geometria(
    tmp_path: Path,
) -> None:
    report, path = run_offline_classification_eval(tmp_path)

    assert report.passed is True
    assert report.schema_lineage_valid_count == 7
    assert report.non_geometric_count == 7
    assert report.correct_count == 7
    assert report.high_confidence_error_count == 0
    assert report.estimated_cost_usd == 0
    assert json.loads(path.read_text())["mode"] == "offline"


def test_corpus_real_exige_exatamente_seis_casos_distintos() -> None:
    with pytest.raises(ValueError):
        ClassificationCorpus.model_validate(
            {
                "schema": "field-photo-classification-corpus/1",
                "cases": [{"case_id": "um", "image": "um.jpg", "expected_category": "MURO"}],
            }
        )


def test_live_recusa_antes_da_rede_sem_openai_explicitamente_desligado(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manifest = tmp_path / "corpus.json"
    manifest.write_text(
        json.dumps(
            {
                "schema": "field-photo-classification-corpus/1",
                "cases": [
                    {
                        "case_id": f"case-{index}",
                        "image": f"{index}.jpg",
                        "expected_category": "UNKNOWN",
                    }
                    for index in range(6)
                ],
            }
        )
    )
    monkeypatch.delenv("CROQUITO_OPENAI_ARM_ENABLED", raising=False)
    monkeypatch.setenv("CROQUITO_ANTHROPIC_API_KEY", "nao-deve-sair")
    monkeypatch.setenv("CROQUITO_AI_MAX_ESTIMATED_COST_USD", "5.00")

    with pytest.raises(ValueError, match="OPENAI_ARM_ENABLED=false"):
        run_live_classification_eval(manifest, tmp_path / "output")
