"""A cadeia completa da medição, percorrida uma vez pela demonstração determinística.

O que este arquivo prova é o encaixe entre os elos que os testes de domínio já cobrem
separadamente: a prancha vira takeoff, o takeoff revisado vira código confirmado, o
código confirmado vira boletim e memória, e a obra que nasceu disso entra na medição
consolidada como qualquer outra — atravessando o portão de exportação e a auditoria.

A demonstração roda **uma vez** por módulo: ela gera prancha, planilha e auditoria, e
pagar isso por teste não compraria nada. Ordem interna de candidatos de sugestão não é
asserida aqui (é comportamento do domínio, coberto em `test_assignment.py`) e digest de
arquivo também não — os bytes do PDF e do xlsx variam entre execuções de propósito.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from croquito_valuation.assignment import CodeSuggestionSet
from croquito_valuation.models import CalcRecipe
from croquito_worker.valuation.cli import (
    CALC_PLAN_FILENAME,
    CODE_ASSIGNMENT_DECISIONS_FILENAME,
    CODE_ASSIGNMENTS_FILENAME,
    CODE_SUGGESTIONS_FILENAME,
    ValuationDemoResult,
    run_valuation_demo,
)
from croquito_worker.valuation.plate import SYNTHETIC_PLATE_ID
from croquito_worker.valuation.synthetic import SYNTHETIC_TAKEOFF_WORKSITE_KEY
from croquito_worker.valuation.takeoff_fixture import takeoff_item_id

_LAWN_ITEM_ID = takeoff_item_id(SYNTHETIC_PLATE_ID, "GRAMADO SINTETICO")
_FENCE_ITEM_NUMBER = "2"
_RUBBER_ITEM_NUMBER = "5"


@pytest.fixture(scope="module")
def demo(tmp_path_factory: pytest.TempPathFactory) -> ValuationDemoResult:
    return run_valuation_demo(tmp_path_factory.mktemp("chain") / "demo")


def test_the_plate_worksite_closes_the_chain_as_the_fourth_worksite(
    demo: ValuationDemoResult,
) -> None:
    keys = [bulletin.worksite_key for bulletin in demo.valuation.bulletins]

    assert keys == [
        "praca-sintetica-norte",
        "praca-sintetica-sul",
        "praca-sintetica-leste",
        SYNTHETIC_TAKEOFF_WORKSITE_KEY,
    ]
    bulletin = demo.valuation.bulletins[-1]
    # O gramado ficou de fora: código rejeitado não vira linha de boletim.
    assert [line.code for line in bulletin.lines] == [
        "AD04050060(/)",
        "CE02100010(/)",
        "MB01100010(/)",
        "MB01300010(/)",
        "AD04150010(/)",
    ]


def test_the_rejected_code_is_the_only_item_left_out_of_the_bulletin(
    demo: ValuationDemoResult,
) -> None:
    assert demo.takeoff_build.excluded_item_ids == (_LAWN_ITEM_ID,)


def test_the_fence_carries_the_review_conversion_into_the_calc_sheet(
    demo: ValuationDemoResult,
) -> None:
    """O projetista entrega metro linear com altura anotada; o orçamentista mede em m².

    A memória imprime a conversão (48,75 x 1,20) em vez de esconder o número convertido:
    é o plano de cálculo explicando a quantidade que o revisor confirmou.
    """
    bulletin = demo.valuation.bulletins[-1]
    line = next(line for line in bulletin.lines if line.item_number == _FENCE_ITEM_NUMBER)
    sheet = demo.valuation.calc_sheet_for(SYNTHETIC_TAKEOFF_WORKSITE_KEY, _FENCE_ITEM_NUMBER)

    assert line.quantity == Decimal("58.50")
    assert [block.recipe for block in sheet.blocks] == [CalcRecipe.PERIMETER_TIMES_HEIGHT]
    assert [operand.value for operand in sheet.blocks[0].operands] == [
        Decimal("48.75"),
        Decimal("1.20"),
    ]


def test_the_illegible_line_carries_the_quantity_the_reviewer_informed(
    demo: ValuationDemoResult,
) -> None:
    """18,40 não foi lido da prancha: a linha é ilegível e quem informou foi o revisor."""
    bulletin = demo.valuation.bulletins[-1]
    line = next(line for line in bulletin.lines if line.item_number == _RUBBER_ITEM_NUMBER)

    assert line.code == "AD04150010(/)"
    assert line.quantity == Decimal("18.40")


def test_the_chain_publishes_every_intermediate_artifact(demo: ValuationDemoResult) -> None:
    assert demo.audit.status == "ok"
    assert demo.takeoff_packet_path.is_file()
    assert demo.takeoff_decisions_path.is_file()
    for path in (
        demo.suggestions_path,
        demo.assignment_decisions_path,
        demo.assignments_path,
        demo.calc_plan_path,
    ):
        assert path.is_file()
    assert [path.name for path in (demo.suggestions_path, demo.calc_plan_path)] == [
        CODE_SUGGESTIONS_FILENAME,
        CALC_PLAN_FILENAME,
    ]
    assert demo.assignment_decisions_path.name == CODE_ASSIGNMENT_DECISIONS_FILENAME
    assert demo.assignments_path.name == CODE_ASSIGNMENTS_FILENAME


def test_every_confirmed_item_is_answered_by_the_suggestion_set(
    demo: ValuationDemoResult,
) -> None:
    """Sugestão não some com item: ele recebe candidatos ou é declarado sem candidato."""
    suggestions = CodeSuggestionSet.model_validate_json(
        demo.suggestions_path.read_text(encoding="utf-8")
    )
    answered = {suggestion.item_id for suggestion in suggestions.suggestions} | set(
        suggestions.unmatched_item_ids
    )

    assert {item.id for item in demo.takeoff_packet.confirmed_items()} <= answered


def test_the_consolidated_valuation_passes_the_export_gate(demo: ValuationDemoResult) -> None:
    """Aprovada, no período seguinte e dentro do saldo de cada código do contrato."""
    assert demo.valuation.export_errors(demo.contract) == []
