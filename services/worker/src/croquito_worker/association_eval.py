"""Eval determinística de associação (F-029 T3) — gate sobre fixture sintética programática.

Molde de `vision_eval.py`: a fixture nasce em código (nenhuma pasta de fixture estática),
o gabarito é conhecido de antemão e o relatório é um JSON auditável com `passed` como AND
de critérios nomeados. A diferença é o que se mede: aqui não é recall geométrico do OpenCV,
é se `associate_readings` (T-anterior) mais o score de confiança de `association_confidence`
(F-029 T1) escolhem o candidato certo — e, quando escolhem errado, se o erro fica ACIMA do
corte do gate, que é o caso perigoso: uma pessoa confiaria numa auto-associação errada.

O gabarito cobre de propósito os casos que uma eval de recall geométrico não distingue:

- um caso claro (candidato isolado, sem disputa);
- um par ambíguo por PROXIMIDADE (duas linhas quase equidistantes — a margem decide);
- um par ambíguo por ORIENTAÇÃO (mesma distância exata — o alinhamento do texto decide);
- um círculo (sem direção própria — `orientation_alignment` neutro);
- uma leitura sem candidato nenhum (fora do raio de busca — nunca é auto-associável).

Nada aqui desenha ou lê pixel de imagem: `associate_readings` e `association_confidence`
operam só sobre os contratos tipados (`ReviewPacket`, `VisionProposalSet`), e a fixture não
precisa de PNG nenhum para exercitar exatamente esse caminho.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from decimal import Decimal
from pathlib import Path
from typing import Final

from pydantic import BaseModel, ConfigDict, Field

from croquito_core.models import MeasurementKind, UnitCode
from croquito_worker.association import (
    AssociationCandidate,
    AssociationConfig,
    AssociationSet,
    associate_readings,
)
from croquito_worker.association_confidence import (
    CONFIDENCE_SCORE_VERSION,
    # Import deliberado do símbolo privado: o propósito deste eval é ESPELHAR a escolha de
    # produção (a mesma regra de desempate que decide qual candidato o modo automático
    # usaria), nunca uma cópia independente — se a regra mudar em `association_confidence`,
    # este eval precisa mudar junto, não divergir em silêncio. Mesmo pacote, mesma regra.
    _best_candidate,
)
from croquito_worker.io_utils import atomic_write_text
from croquito_worker.review import (
    DimensionReading,
    EvidenceRegion,
    PixelBox,
    ReadingStatus,
    ReviewPacket,
)
from croquito_worker.vision import (
    PixelCircle,
    PixelLine,
    PixelPoint,
    VisionProposal,
    VisionProposalSet,
)

DATASET_ID: Final = "association-eval-fixture-v1"
IMAGE_SHA256: Final = hashlib.sha256(b"association-eval-fixture-v1").hexdigest()
IMAGE_WIDTH_PX: Final = 1600
IMAGE_HEIGHT_PX: Final = 1200

# Ratio menor que o padrão de produção (`AssociationConfig.max_distance_diagonal_ratio` =
# 0.18): a fixture usa geometria compacta de propósito (gabarito fácil de auditar a olho),
# e o raio de busca padrão a essa escala alcançaria proposta de outro caso de teste,
# poluindo o gabarito com candidato que ninguém pediu para disputar.
EVAL_CONFIG: Final = AssociationConfig(max_distance_diagonal_ratio=0.08)

ASSOCIATION_EVAL_GATE_THRESHOLD: Final = 0.8
"""Corte do gate: acima disto, uma associação errada é o erro perigoso e reprova sozinha."""

ASSOCIATION_EVAL_MIN_RECALL: Final = 1.0
"""Recall mínimo do top-1 sobre as leituras com gabarito conhecido (fixture pequena e fechada)."""


def _suffix(label: str) -> str:
    return hashlib.sha256(f"association-eval:{label}".encode()).hexdigest()[:16]


def _reading_id(label: str) -> str:
    return f"rd_{_suffix(label)}"


def _proposal_id(label: str) -> str:
    return f"vp_{_suffix(label)}"


def _line_proposal(
    label: str, *, start: tuple[float, float], end: tuple[float, float], quality: float
) -> VisionProposal:
    return VisionProposal(
        id=_proposal_id(label),
        kind="line",
        geometry=PixelLine(
            start=PixelPoint(x=start[0], y=start[1]),
            end=PixelPoint(x=end[0], y=end[1]),
        ),
        algorithm="association-eval-fixture",
        quality_score=quality,
    )


def _circle_proposal(
    label: str, *, center: tuple[float, float], radius: float, quality: float
) -> VisionProposal:
    return VisionProposal(
        id=_proposal_id(label),
        kind="circle",
        geometry=PixelCircle(center=PixelPoint(x=center[0], y=center[1]), radius=radius),
        algorithm="association-eval-fixture",
        quality_score=quality,
    )


def _reading(
    label: str,
    *,
    bbox: PixelBox,
    kind: MeasurementKind = MeasurementKind.LENGTH,
    value: str = "1.00",
) -> DimensionReading:
    return DimensionReading(
        id=_reading_id(label),
        evidence=EvidenceRegion(
            dataset_id=DATASET_ID,
            page_number=1,
            image_sha256=IMAGE_SHA256,
            bbox=bbox,
        ),
        raw_text=value.replace(".", ","),
        value_si=Decimal(value),
        unit=UnitCode.METRE,
        kind=kind,
        written_decimals=2,
        target_hint=label,
        extractor="association-eval-fixture",
        extractor_version="v1",
        status=ReadingStatus.PROPOSED,
    )


# --- geometria do gabarito, coordenadas escolhidas para que cada caso isole exatamente os
# candidatos que o comentário descreve (conferido por distância ponto-segmento, não por
# inspeção visual) -------------------------------------------------------------------------

LINE_A = _line_proposal("line-a", start=(150, 50), end=(150, 750), quality=0.9)
"""Caso claro: única leitura próxima é `rd_clear`, por larga margem sobre qualquer outra."""

LINE_B1 = _line_proposal("line-b1", start=(300, 450), end=(600, 450), quality=0.85)
LINE_B2 = _line_proposal("line-b2", start=(300, 470), end=(600, 470), quality=0.80)
"""Par ambíguo por PROXIMIDADE: 20 px de afastamento entre si; `rd_prox` fica 8/12 px de
cada uma — o gabarito é B1, mais perto E de melhor qualidade, mas a margem é estreita."""

LINE_C1 = _line_proposal("line-c1", start=(350, 650), end=(650, 650), quality=0.75)
LINE_C2 = _line_proposal("line-c2", start=(650, 550), end=(650, 700), quality=0.75)
"""Par ambíguo por ORIENTAÇÃO: `rd_orient` fica EXATAMENTE a 15 px das duas (mesma
qualidade visual) — só o alinhamento do eixo do texto com a direção do segmento decide,
e o gabarito (C1, horizontal) é o alinhado com o bbox horizontal da leitura."""

CIRCLE = _circle_proposal("circle", center=(500, 150), radius=60, quality=0.9)
"""Candidato sem direção própria: `orientation_alignment` neutro (`None`)."""


def build_association_eval_fixture() -> tuple[
    ReviewPacket, VisionProposalSet, dict[str, str | None]
]:
    """Pacote de revisão, propostas CV e gabarito de associação — tudo em código, sem PNG.

    O gabarito mapeia `reading_id -> proposal_id` esperado, ou `None` quando a leitura não
    deve encontrar candidato nenhum (`rd_none`, fora do raio de busca de todo mundo).
    """
    readings = [
        _reading("clear", bbox=PixelBox(left=160, top=390, right=190, bottom=410)),
        _reading("prox", bbox=PixelBox(left=430, top=448, right=470, bottom=468)),
        _reading("orient", bbox=PixelBox(left=605, top=625, right=665, bottom=645)),
        _reading(
            "circle",
            bbox=PixelBox(left=485, top=205, right=515, bottom=225),
            kind=MeasurementKind.RADIUS,
        ),
        _reading("none", bbox=PixelBox(left=880, top=880, right=920, bottom=920)),
    ]
    packet = ReviewPacket(
        dataset_id=DATASET_ID,
        page_number=1,
        image_sha256=IMAGE_SHA256,
        readings=readings,
        safety_notes=[
            "Fixture sintética do gate de associação (F-029 T3); sem conteúdo de cliente.",
            "Nenhuma decisão humana está presente; todo candidato segue unresolved.",
        ],
    )
    proposals = VisionProposalSet(
        dataset_id=DATASET_ID,
        page_number=1,
        image_sha256=IMAGE_SHA256,
        image_width_px=IMAGE_WIDTH_PX,
        image_height_px=IMAGE_HEIGHT_PX,
        configured_limits={},
        limit_reached=[],
        proposals=[LINE_A, LINE_B1, LINE_B2, LINE_C1, LINE_C2, CIRCLE],
        safety_notes=[
            "Fixture sintética do gate de associação (F-029 T3); sem conteúdo de cliente.",
            "Geometria construída em código; nenhuma detecção OpenCV real foi executada.",
            "Toda proposta permanece unresolved e não exportável.",
        ],
    )
    ground_truth: dict[str, str | None] = {
        _reading_id("clear"): LINE_A.id,
        _reading_id("prox"): LINE_B1.id,
        _reading_id("orient"): LINE_C1.id,
        _reading_id("circle"): CIRCLE.id,
        _reading_id("none"): None,
    }
    return packet, proposals, ground_truth


class AssociationEvalReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dataset_id: str
    associator_version: str
    score_version: str
    reading_count: int = Field(ge=0)
    eligible_count: int = Field(ge=0)
    correct_top1_count: int = Field(ge=0)
    recall_top1: float = Field(ge=0, le=1)
    errors_above_gate: int = Field(ge=0)
    unassociated_as_expected: bool
    passed: bool
    thresholds: dict[str, float]


def evaluate_association_set(
    ground_truth: Mapping[str, str | None],
    associations: AssociationSet,
) -> AssociationEvalReport:
    """Função pura: mede recall do top-1 e erro acima do corte do gate contra um gabarito.

    Separada de `run_synthetic_association_eval` para que um teste possa sabotar o
    `AssociationSet` já calculado (plantar uma associação errada com confiança acima do
    corte) sem precisar reconstruir a fixture inteira.
    """
    candidates_by_reading: dict[str, list[AssociationCandidate]] = {}
    for candidate in associations.candidates:
        candidates_by_reading.setdefault(candidate.reading_id, []).append(candidate)

    eligible = {
        reading_id: proposal_id
        for reading_id, proposal_id in ground_truth.items()
        if proposal_id is not None
    }
    correct = 0
    errors_above_gate = 0
    for reading_id, expected_proposal_id in eligible.items():
        candidates = candidates_by_reading.get(reading_id, [])
        if not candidates:
            # Gabarito esperava candidato e não há nenhum: a fixture está quebrada, não é
            # um erro de score — conta como recall perdido, nunca como erro acima do corte.
            continue
        top = _best_candidate(candidates)
        if top.proposal_id == expected_proposal_id:
            correct += 1
        elif top.association_confidence >= ASSOCIATION_EVAL_GATE_THRESHOLD:
            errors_above_gate += 1

    unassociated_expected = {
        reading_id for reading_id, proposal_id in ground_truth.items() if proposal_id is None
    }
    unassociated_as_expected = unassociated_expected <= set(associations.unassociated_reading_ids)

    recall = correct / len(eligible) if eligible else 1.0
    thresholds = {
        "gate_threshold": ASSOCIATION_EVAL_GATE_THRESHOLD,
        "min_recall": ASSOCIATION_EVAL_MIN_RECALL,
    }
    passed = (
        errors_above_gate == 0
        and recall >= ASSOCIATION_EVAL_MIN_RECALL
        and unassociated_as_expected
    )
    return AssociationEvalReport(
        dataset_id=associations.dataset_id,
        associator_version=associations.associator_version,
        score_version=CONFIDENCE_SCORE_VERSION,
        reading_count=len(ground_truth),
        eligible_count=len(eligible),
        correct_top1_count=correct,
        recall_top1=round(recall, 4),
        errors_above_gate=errors_above_gate,
        unassociated_as_expected=unassociated_as_expected,
        passed=passed,
        thresholds=thresholds,
    )


def run_synthetic_association_eval(output_dir: Path) -> tuple[AssociationEvalReport, Path]:
    packet, proposals, ground_truth = build_association_eval_fixture()
    associations = associate_readings(packet, proposals, config=EVAL_CONFIG)
    report = evaluate_association_set(ground_truth, associations)
    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / "association-eval.json"
    serialized = json.dumps(
        report.model_dump(mode="json"),
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    )
    atomic_write_text(report_path, f"{serialized}\n")
    return report, report_path
