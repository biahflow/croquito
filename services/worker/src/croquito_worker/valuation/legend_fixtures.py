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

import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Final

from croquito_valuation.assignment import CodeSuggestionSet
from croquito_valuation.takeoff import PlateBox
from croquito_worker.providers import (
    FixtureProviderAdapter,
    LegendExtractionOutput,
    LegendRowOutput,
    NormalizedBox,
    PromptTask,
    ProviderAdapter,
    ProviderExecution,
    ProviderName,
    ProviderOutput,
    ProviderRequest,
    ScoItemRefinementOutput,
    ScoRefinementOutput,
)
from croquito_worker.valuation.plate import PlateArtifacts
from croquito_worker.valuation.sco_suggestion import TRANSMITTED_CANDIDATE_WINDOW

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
    """Refino que põe o código do gabarito em primeiro, permutando **só a janela enviada**.

    A janela é `TRANSMITTED_CANDIDATE_WINDOW`, a mesma que o estágio real transmite: um
    provider de verdade também não conseguiria devolver mais que isso, porque o contrato de
    saída do prompt limita `ranked_codes`. A fixture que ranqueasse a shortlist inteira
    estaria medindo um comportamento impossível.

    Consequência honesta: gabarito que caiu FORA da janela não pode ser promovido — a
    fixture mantém a ordem lexical e marca a flag, exatamente como faz quando o código do
    gabarito não está na shortlist. Item cujo gabarito não tem código (o gramado, rejeitado
    no demo) segue no mesmo caso: a fixture não inventa preferência onde o gabarito não tem
    opinião. Item cuja ordem lexical já estava certa também mantém a ordem — e é isso que
    faz a métrica do refino ser comparável com a da baseline no mesmo relatório.
    """
    items: list[ScoItemRefinementOutput] = []
    for suggestion in suggestions.suggestions:
        window = [
            candidate.code for candidate in suggestion.candidates[:TRANSMITTED_CANDIDATE_WINDOW]
        ]
        expected = expected_code_by_label.get(labels_by_item.get(suggestion.item_id, ""))
        if expected is None or expected not in window:
            items.append(
                ScoItemRefinementOutput(
                    item_id=suggestion.item_id,
                    ranked_codes=window,
                    rationale=_NO_CODE_RATIONALE,
                    flags=[_NO_CODE_FLAG],
                )
            )
            continue
        ranked = [expected, *[code for code in window if code != expected]]
        items.append(
            ScoItemRefinementOutput(
                item_id=suggestion.item_id,
                ranked_codes=ranked,
                rationale=_PERFECT_RATIONALE,
                flags=[] if ranked == window else [_MOVED_FLAG],
            )
        )
    return ScoRefinementOutput(items=items)


def build_out_of_shortlist_refinement_output(
    suggestions: CodeSuggestionSet,
) -> ScoRefinementOutput:
    """Refino deliberadamente inválido: um código que não estava na shortlist do item.

    O intruso ENTRA no lugar do último candidato da janela em vez de somar-se a ela: a
    resposta continua cabendo no contrato de saída do prompt (`ranked_codes`, no máximo
    `TRANSMITTED_CANDIDATE_WINDOW`), e a recusa que a eval mede passa a ser a do domínio —
    código vindo do nada —, não a do schema por tamanho de lista.
    """
    first = suggestions.suggestions[0]
    window = [c.code for c in first.candidates[:TRANSMITTED_CANDIDATE_WINDOW]]
    return ScoRefinementOutput(
        items=[
            ScoItemRefinementOutput(
                item_id=first.item_id,
                ranked_codes=[OUT_OF_SHORTLIST_CODE, *window[:-1]],
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


@dataclass(frozen=True, slots=True)
class _BatchedRefinementAdapter:
    """Adapter de refino que responde só sobre os itens do lote que recebeu.

    `FixtureProviderAdapter` devolve a mesma saída para qualquer requisição, e isso deixou
    de servir para o refino quando ele passou a fatiar os itens em vários `text_payload`:
    responder sobre a prancha inteira em cada lote seria um provider inventando resposta
    para pergunta que não recebeu — coisa que `refine_code_suggestions` recusa, e com razão.
    Aqui a fixture lê do próprio payload quais itens foram perguntados, como um provider
    real faria, e devolve exatamente aqueles.
    """

    model_id: str
    items_by_id: Mapping[str, ScoItemRefinementOutput]

    def execute(self, request: ProviderRequest) -> ProviderExecution:
        payload = json.loads(request.text_payload or '{"items":[]}')
        asked = [str(entry["item_id"]) for entry in payload["items"]]
        output = ScoRefinementOutput(
            items=[self.items_by_id[item_id] for item_id in asked if item_id in self.items_by_id]
        )
        return _fixture_adapter(self.model_id, output).execute(request)


def legend_fixture_adapter(plate: PlateArtifacts) -> FixtureProviderAdapter:
    """Adapter offline que devolve a transcrição perfeita da prancha recém-gerada."""
    return _fixture_adapter(FIXTURE_LEGEND_MODEL_ID, build_legend_extraction_output(plate))


def refinement_fixture_adapter(
    suggestions: CodeSuggestionSet,
    labels_by_item: Mapping[str, str],
    expected_code_by_label: Mapping[str, str],
) -> ProviderAdapter:
    """Adapter offline de refino, construído **depois** da shortlist que ele reordena.

    A dependência é real e explícita: só dá para permutar uma shortlist que já existe, e é
    por isso que o braço fixture entrega uma fábrica de adapter em vez de um adapter
    pronto.
    """
    output = build_sco_refinement_output(suggestions, labels_by_item, expected_code_by_label)
    return _BatchedRefinementAdapter(
        model_id=FIXTURE_REFINEMENT_MODEL_ID,
        items_by_id={item.item_id: item for item in output.items},
    )


def invalid_refinement_fixture_adapter(
    suggestions: CodeSuggestionSet,
) -> ProviderAdapter:
    """Adapter offline que tenta injetar código fora da shortlist; existe para ser recusado."""
    output = build_out_of_shortlist_refinement_output(suggestions)
    return _BatchedRefinementAdapter(
        model_id=FIXTURE_REFINEMENT_MODEL_ID,
        items_by_id={item.item_id: item for item in output.items},
    )
