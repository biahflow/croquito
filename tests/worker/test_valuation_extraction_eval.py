"""Eval da extração paga: correspondência item↔gabarito e o percurso completo de um braço.

O defeito que este módulo existe para não deixar voltar apareceu só na primeira rodada paga:
o modelo transcreveu o rótulo **como impresso** na prancha — `ALAMBRADO SINTETICO (h=1,20m)`,
rótulo e nota colados — e a eval, que casava por rótulo exato do gabarito, recusou a revisão
sintética com `SYNTHETIC_LABEL_UNKNOWN`. O braço fixture não alcança esse caso por
construção: ele transcreve o rótulo puro. Por isso o teste de regressão é um braço fixture
**variante**, que escreve o rótulo impresso e percorre o mesmo caminho de código do braço
real, sem rede.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

import pytest

from croquitodxf_valuation.catalog import read_price_catalog
from croquitodxf_valuation.contract import ContractWorkbook
from croquitodxf_valuation.models import PriceCatalog
from croquitodxf_valuation.takeoff import (
    PlateBox,
    PlateEvidence,
    TakeoffItem,
    TakeoffItemStatus,
)
from croquitodxf_valuation.template import default_template
from croquitodxf_valuation.workbook_reader import read_contract_workbook
from croquitodxf_worker.providers import (
    FixtureProviderAdapter,
    LegendExtractionOutput,
    LegendRowOutput,
    PromptTask,
    ProviderName,
)
from croquitodxf_worker.valuation.extraction_eval import (
    ExtractionArm,
    _run_arm,
    gabarito_row_for,
)
from croquitodxf_worker.valuation.legend_fixtures import (
    FIXTURE_LEGEND_MODEL_ID,
    build_legend_extraction_output,
    refinement_fixture_adapter,
)
from croquitodxf_worker.valuation.plate import (
    SYNTHETIC_LEGEND_ROWS,
    PlateArtifacts,
    render_synthetic_plate,
)
from croquitodxf_worker.valuation.synthetic import (
    DEMO_EXPECTED_CODE_BY_LABEL,
    SYNTHETIC_CONTRACT_LABEL,
    SYNTHETIC_CONTRACT_SOURCE_LABEL,
    SYNTHETIC_REFERENCE_MONTH,
    build_synthetic_previous_mapao,
)

_FENCE_ROW = SYNTHETIC_LEGEND_ROWS[2]
"""A linha do alambrado: a única do gabarito cujo rótulo impresso difere do puro."""

_INTERVENTION_LABEL = "AREA DE INTERVENCAO SINTETICA"


@dataclass(frozen=True, slots=True)
class EvalWorkspace:
    """Prancha, catálogo e consolidado sintéticos, montados uma vez por módulo."""

    plate: PlateArtifacts
    catalog: PriceCatalog
    contract: ContractWorkbook
    output_dir: Path


@pytest.fixture(scope="module")
def workspace(tmp_path_factory: pytest.TempPathFactory) -> EvalWorkspace:
    root = tmp_path_factory.mktemp("valuation-extraction-eval")
    template = default_template()
    previous_path = build_synthetic_previous_mapao(root / "previous-mapao.xlsx")
    return EvalWorkspace(
        plate=render_synthetic_plate(root),
        catalog=read_price_catalog(
            previous_path,
            template,
            source_label=SYNTHETIC_CONTRACT_SOURCE_LABEL,
            reference_month=SYNTHETIC_REFERENCE_MONTH,
        ),
        contract=read_contract_workbook(
            previous_path,
            template,
            source_label=SYNTHETIC_CONTRACT_SOURCE_LABEL,
            contract_label=SYNTHETIC_CONTRACT_LABEL,
        ),
        output_dir=root,
    )


def _item(label: str) -> TakeoffItem:
    """Item de takeoff mínimo, só com o que a correspondência por rótulo consulta."""
    return TakeoffItem(
        id="ti_0123456789abcdef",
        evidence=PlateEvidence(
            plate_id="prancha",
            page_number=1,
            image_sha256="a" * 64,
            bbox=PlateBox(left=1, top=1, right=10, bottom=10),
        ),
        raw_text=f"{label} 1,00 M2",
        label=label,
        quantity=Decimal("1.00"),
        unit="m2",
        source="legend_extraction",
        extractor="anthropic:modelo-de-teste",
        extractor_version="legend-extraction@1.0.0",
        status=TakeoffItemStatus.PROPOSED,
    )


def _printed_label_output(plate: PlateArtifacts) -> LegendExtractionOutput:
    """A transcrição perfeita, mas com o rótulo **como impresso** (rótulo + nota colados).

    É o que o Sonnet devolveu na primeira rodada paga: leitura fiel ao papel.
    """
    perfect = build_legend_extraction_output(plate)
    rows = [
        LegendRowOutput.model_validate(
            {**row.model_dump(), "label": entry.row.plate_label},
        )
        for row, entry in zip(perfect.rows, plate.rows, strict=True)
    ]
    return LegendExtractionOutput(rows=rows, page_notes=list(perfect.page_notes))


def _printed_label_arm(plate: PlateArtifacts) -> ExtractionArm:
    return ExtractionArm(
        name="rotulo-impresso",
        legend_adapter=FixtureProviderAdapter(
            provider=ProviderName.ANTHROPIC,
            model_id=FIXTURE_LEGEND_MODEL_ID,
            outputs={PromptTask.LEGEND_EXTRACTION: _printed_label_output(plate)},
        ),
        refinement_adapter=lambda suggestions, labels: refinement_fixture_adapter(
            suggestions, labels, DEMO_EXPECTED_CODE_BY_LABEL
        ),
    )


# --------------------------------------------------------------------------------------
# gabarito_row_for
# --------------------------------------------------------------------------------------


def test_the_plain_label_matches_its_gabarito_row() -> None:
    assert gabarito_row_for(_item(_FENCE_ROW.label)) is _FENCE_ROW


def test_the_printed_label_with_the_note_glued_matches_the_same_row() -> None:
    """`ALAMBRADO SINTETICO (h=1,20m)` é o mesmo alambrado; transcrever o papel não é erro."""
    assert _FENCE_ROW.plate_label != _FENCE_ROW.label
    assert gabarito_row_for(_item(_FENCE_ROW.plate_label)) is _FENCE_ROW


def test_surrounding_whitespace_does_not_break_the_match() -> None:
    assert gabarito_row_for(_item(f"  {_FENCE_ROW.plate_label}  ")) is _FENCE_ROW


def test_a_label_that_describes_no_row_does_not_match_by_approximation() -> None:
    assert gabarito_row_for(_item("ALAMBRADO")) is None
    assert gabarito_row_for(_item("MURETA DE CONCRETO SINTETICA")) is None


# --------------------------------------------------------------------------------------
# Percurso completo do braço com rótulo impresso (regressão da primeira rodada paga)
# --------------------------------------------------------------------------------------


def test_an_arm_that_transcribes_the_printed_label_scores_full_recall(
    workspace: EvalWorkspace, tmp_path: Path
) -> None:
    outcome = _run_arm(
        _printed_label_arm(workspace.plate),
        workspace.plate,
        workspace.catalog,
        workspace.contract,
        tmp_path,
    )

    assert outcome.report.legend_recall == 1.0
    assert outcome.report.quantity_accuracy == 1.0
    assert outcome.unmatched_item_ids == ()


def test_the_synthetic_review_closes_over_printed_labels(
    workspace: EvalWorkspace, tmp_path: Path
) -> None:
    """O que quebrava antes: a revisão recusava com SYNTHETIC_LABEL_UNKNOWN."""
    outcome = _run_arm(
        _printed_label_arm(workspace.plate),
        workspace.plate,
        workspace.catalog,
        workspace.contract,
        tmp_path,
    )

    reviewed = outcome.reviewed
    assert reviewed.pending_items() == []
    assert len(reviewed.confirmed_items()) == len(SYNTHETIC_LEGEND_ROWS) - 1
    rejected_rows = [
        gabarito_row_for(item)
        for item in reviewed.items
        if item.status is TakeoffItemStatus.REJECTED
    ]
    assert [row.label for row in rejected_rows if row is not None] == [_INTERVENTION_LABEL]
    # A linha ilegível fecha com a quantidade do gabarito informada pelo revisor sintético,
    # nunca com um número derivado da imagem.
    illegible_row = next(row for row in SYNTHETIC_LEGEND_ROWS if row.quantity is None)
    supplied = next(item for item in reviewed.items if gabarito_row_for(item) is illegible_row)
    assert supplied.status is TakeoffItemStatus.CONFIRMED
    assert supplied.quantity is not None
    assert supplied.decision is not None
    assert supplied.decision.note is not None


def test_the_sco_oracle_still_measures_under_printed_labels(
    workspace: EvalWorkspace, tmp_path: Path
) -> None:
    """O hit-rate é indexado pelo rótulo do GABARITO; com o impresso a chave erraria e daria 0.

    O braço com rótulo impresso pontua igual ao braço de rótulo puro — e isso depende de a
    revisão sintética continuar sendo a **do demo**: é a decisão do alambrado que converte
    metro linear em m², e sem essa conversão a unidade do item derruba o código certo para
    fora da shortlist lexical (medido: top-1 cai de 1,0 para 0,8). A correspondência por
    gabarito conserta o endereçamento da decisão, não a política dela.
    """
    outcome = _run_arm(
        _printed_label_arm(workspace.plate),
        workspace.plate,
        workspace.catalog,
        workspace.contract,
        tmp_path,
    )

    assert outcome.lexical.suggestions
    assert outcome.report.sco_top1 == 1.0
    assert outcome.report.sco_top3 == 1.0
    # O refino continua ganhando da baseline lexical, como no braço de rótulo puro.
    assert outcome.report.lexical_sco_top1 == 0.8
    assert outcome.report.sco_top1 > outcome.report.lexical_sco_top1


def test_an_unmatched_item_is_reported_instead_of_breaking_the_run(
    workspace: EvalWorkspace, tmp_path: Path
) -> None:
    """Rótulo que o gabarito não descreve não é revisado nem medido — é declarado."""
    plate = workspace.plate
    output = _printed_label_output(plate)
    intruder = LegendRowOutput.model_validate(
        {
            **output.rows[0].model_dump(),
            "raw_text": "MURETA DE CONCRETO SINTETICA 3,00 M",
            "label": "MURETA DE CONCRETO SINTETICA",
            "quantity_text": "3,00",
            "unit_text": "M",
        }
    )
    arm = ExtractionArm(
        name="com-intruso",
        legend_adapter=FixtureProviderAdapter(
            provider=ProviderName.ANTHROPIC,
            model_id=FIXTURE_LEGEND_MODEL_ID,
            outputs={
                PromptTask.LEGEND_EXTRACTION: LegendExtractionOutput(
                    rows=[*output.rows, intruder], page_notes=list(output.page_notes)
                )
            },
        ),
        refinement_adapter=lambda suggestions, labels: refinement_fixture_adapter(
            suggestions, labels, DEMO_EXPECTED_CODE_BY_LABEL
        ),
    )

    outcome = _run_arm(arm, plate, workspace.catalog, workspace.contract, tmp_path)

    assert len(outcome.unmatched_item_ids) == 1
    # O intruso não é revisado: ele continua pendente e fora do boletim.
    pending = outcome.reviewed.pending_items()
    assert [item.label for item in pending] == ["MURETA DE CONCRETO SINTETICA"]
    # E o recall das linhas do gabarito não é afetado pelo item a mais.
    assert outcome.report.legend_recall == 1.0
