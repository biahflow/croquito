"""Saídas de provider fabricadas para a eval offline da extração de legenda.

Este módulo é fixture, e vive longe do caminho de produção de propósito: nada aqui é
importado por `legend_extraction.py`, por `sco_suggestion.py` ou pelos comandos pagos —
`extract-legend-real` e `suggest-codes --refine-arm` recusam explicitamente o provider
`fixture` para que observação fabricada nunca vire artefato publicado.

O que ele constrói sai das MESMAS constantes que desenham a prancha sintética
(`SYNTHETIC_LEGEND_ROWS`) e do MESMO gabarito de código do demo
(`DEMO_EXPECTED_CODE_BY_LABEL`): a fixture não pode "acertar" um número que a prancha não
imprime, porque ela não tem outra fonte de onde tirá-lo.

Honestidade: um braço fixture mede **mecanismo e contrato** — que o mapeamento observação→
takeoff, os gates e o refino se comportam como prometido —, nunca precisão de leitura de
uma prancha real. Precisão é o que a rodada paga da Fase D vai medir.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Final

from croquitodxf_valuation.assignment import CodeSuggestionSet
from croquitodxf_valuation.takeoff import PlateBox
from croquitodxf_worker.providers import (
    FixtureProviderAdapter,
    LegendExtractionOutput,
    LegendRowOutput,
    NormalizedBox,
    PromptTask,
    ProviderName,
    ProviderOutput,
    ScoItemRefinementOutput,
    ScoRefinementOutput,
)
from croquitodxf_worker.valuation.plate import PlateArtifacts

FIXTURE_ARM_NAME: Final = "fixture"
FIXTURE_PROVIDER: Final = ProviderName.ANTHROPIC
FIXTURE_LEGEND_MODEL_ID: Final = "fixture-legend-extractor-v1"
FIXTURE_REFINEMENT_MODEL_ID: Final = "fixture-sco-rerank-v1"

FIXTURE_PAGE_NOTE: Final = "Prancha sintética; nenhuma prancha de cliente foi lida."

_PERFECT_RATIONALE: Final = (
    "fixture determinística: código do gabarito sintético em primeiro, resto na ordem lexical"
)
_NO_CODE_RATIONALE: Final = (
    "fixture determinística: nenhum candidato aplicável ao item; ordem lexical preservada"
)
_MOVED_FLAG: Final = "lexical-top1-divergente"
_NO_CODE_FLAG: Final = "sem-codigo-no-gabarito"

OUT_OF_SHORTLIST_CODE: Final = "ZZ99999999(/)"
"""Código que nenhum catálogo sintético publica: é o que a eval usa para provar que o
refino recusa substituir a shortlist em vez de aceitar código vindo do nada."""


def _normalized_box(bbox: PlateBox, *, image_width: int, image_height: int) -> NormalizedBox:
    return NormalizedBox(
        left=bbox.left / image_width,
        top=bbox.top / image_height,
        right=bbox.right / image_width,
        bottom=bbox.bottom / image_height,
    )


def build_legend_extraction_output(plate: PlateArtifacts) -> LegendExtractionOutput:
    """Transcrição perfeita da legenda que a prancha sintética acabou de imprimir.

    Cada linha vem do gabarito que o próprio render devolveu — texto, quantidade escrita,
    unidade e recorte —, então o braço fixture é o teto do que a eval pode medir: recall 1
    significa que o mapeamento não perdeu nada, não que um modelo real leria assim. A linha
    deliberadamente ilegível da prancha continua ilegível aqui: ela é a que tem de virar
    item ambíguo sem quantidade.
    """
    return LegendExtractionOutput(
        rows=[
            LegendRowOutput(
                raw_text=entry.row.as_written(),
                label=entry.row.label,
                quantity_text=entry.row.raw_quantity_text,
                unit_text=entry.row.unit,
                bbox=_normalized_box(
                    entry.bbox,
                    image_width=plate.image_width,
                    image_height=plate.image_height,
                ),
                legibility="clear" if entry.row.quantity is not None else "illegible",
            )
            for entry in plate.rows
        ],
        page_notes=[FIXTURE_PAGE_NOTE],
    )


def build_sco_refinement_output(
    suggestions: CodeSuggestionSet,
    labels_by_item: Mapping[str, str],
    expected_code_by_label: Mapping[str, str],
) -> ScoRefinementOutput:
    """Refino que põe o código do gabarito em primeiro, permutando **só** a shortlist.

    Item cujo gabarito não tem código (o gramado, rejeitado no demo) mantém a ordem lexical
    e recebe flag: a fixture não inventa preferência onde o gabarito não tem opinião. Item
    cuja ordem lexical já estava certa também mantém a ordem — e é isso que faz a métrica
    do refino ser comparável com a da baseline no mesmo relatório.
    """
    items: list[ScoItemRefinementOutput] = []
    for suggestion in suggestions.suggestions:
        shortlist = [candidate.code for candidate in suggestion.candidates]
        expected = expected_code_by_label.get(labels_by_item.get(suggestion.item_id, ""))
        if expected is None or expected not in shortlist:
            items.append(
                ScoItemRefinementOutput(
                    item_id=suggestion.item_id,
                    ranked_codes=shortlist,
                    rationale=_NO_CODE_RATIONALE,
                    flags=[_NO_CODE_FLAG],
                )
            )
            continue
        ranked = [expected, *[code for code in shortlist if code != expected]]
        items.append(
            ScoItemRefinementOutput(
                item_id=suggestion.item_id,
                ranked_codes=ranked,
                rationale=_PERFECT_RATIONALE,
                flags=[] if ranked == shortlist else [_MOVED_FLAG],
            )
        )
    return ScoRefinementOutput(items=items)


def build_out_of_shortlist_refinement_output(
    suggestions: CodeSuggestionSet,
) -> ScoRefinementOutput:
    """Refino deliberadamente inválido: um código que não estava na shortlist do item."""
    first = suggestions.suggestions[0]
    return ScoRefinementOutput(
        items=[
            ScoItemRefinementOutput(
                item_id=first.item_id,
                ranked_codes=[OUT_OF_SHORTLIST_CODE, *[c.code for c in first.candidates]],
                rationale="fixture inválida de propósito: código fora da shortlist lexical",
            )
        ]
    )


def _fixture_adapter(model_id: str, output: ProviderOutput) -> FixtureProviderAdapter:
    task = PromptTask(output.task)
    return FixtureProviderAdapter(
        provider=FIXTURE_PROVIDER,
        model_id=model_id,
        outputs={task: output},
    )


def legend_fixture_adapter(plate: PlateArtifacts) -> FixtureProviderAdapter:
    """Adapter offline que devolve a transcrição perfeita da prancha recém-gerada."""
    return _fixture_adapter(FIXTURE_LEGEND_MODEL_ID, build_legend_extraction_output(plate))


def refinement_fixture_adapter(
    suggestions: CodeSuggestionSet,
    labels_by_item: Mapping[str, str],
    expected_code_by_label: Mapping[str, str],
) -> FixtureProviderAdapter:
    """Adapter offline de refino, construído **depois** da shortlist que ele reordena.

    A dependência é real e explícita: só dá para permutar uma shortlist que já existe, e é
    por isso que o braço fixture entrega uma fábrica de adapter em vez de um adapter
    pronto.
    """
    return _fixture_adapter(
        FIXTURE_REFINEMENT_MODEL_ID,
        build_sco_refinement_output(suggestions, labels_by_item, expected_code_by_label),
    )


def invalid_refinement_fixture_adapter(
    suggestions: CodeSuggestionSet,
) -> FixtureProviderAdapter:
    """Adapter offline que tenta injetar código fora da shortlist; existe para ser recusado."""
    return _fixture_adapter(
        FIXTURE_REFINEMENT_MODEL_ID,
        build_out_of_shortlist_refinement_output(suggestions),
    )
