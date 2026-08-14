"""Ponto único de sugestão de código SCO do worker: shortlist lexical e refino pago.

O módulo é fino de propósito. Ele existe para que exista **um** lugar por onde a sugestão
de código passa, e é esse lugar que o M5 estende: o provider pago de texto entra aqui para
**refinar a shortlist lexical** — reordenar, anotar, explicar —, nunca para substituí-la e
nunca para confirmar código. Confirmação continua sendo ato humano
(`apply_code_assignments`).

A via lexical (`build_code_suggestions`) é o fallback permanente do produto, não um
estágio transitório: sem entitlement contratual, sem crédito ou com o provider fora do ar,
o orçamentista continua recebendo a mesma shortlist determinística — basta não pedir o
refino. `refine_code_suggestions` **não** tem fallback silencioso: falha de provider sobe
para o chamador, que decide o que fazer, porque publicar a lexical anunciando refino
mentiria sobre o que foi feito.

O que sai daqui para o domínio é forma pura: a ordem pedida, as anotações e o lineage da
chamada. Quem valida que a ordem é permutação da shortlist é `apply_refinement`.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final

from croquito_valuation.assignment import (
    CodeSuggestion,
    CodeSuggestionSet,
    SuggestionConfig,
    SuggestionRefinement,
    apply_refinement,
    suggest_codes,
)
from croquito_valuation.catalog import DomainSynonyms
from croquito_valuation.contract import ContractWorkbook
from croquito_valuation.errors import ValuationValidationError
from croquito_valuation.models import PriceCatalog
from croquito_valuation.takeoff import TakeoffItem, TakeoffPacket
from croquito_worker.providers import (
    PromptTask,
    ProviderAdapter,
    ProviderExecution,
    ProviderExecutionError,
    ProviderFailureCode,
    ScoRefinementOutput,
    build_text_request,
)

TRANSMITTED_DESCRIPTION_MAX_LENGTH: Final = 400
"""Corte da descrição do candidato no payload enviado ao provider.

Mesma natureza do `prepare_transmission` da extração de geometria: reduzir o que trafega
para caber no limite do provider (`ProviderRequest.text_payload`), sem mudar o que o
resultado pode ser. A descrição do catálogo real chega a 1356 caracteres e três candidatos
por item estourariam o payload; o corte é marcado com `…` no texto enviado, e a shortlist
— a única coisa que o refino pode reordenar — continua íntegra.
"""

_ELLIPSIS: Final = "…"


@dataclass(frozen=True, slots=True)
class RefinementResult:
    """Shortlist refinada e o lineage completo da chamada que a produziu."""

    suggestions: CodeSuggestionSet
    execution: ProviderExecution


def build_code_suggestions(
    packet: TakeoffPacket,
    catalog: PriceCatalog,
    contract: ContractWorkbook | None = None,
    *,
    config: SuggestionConfig | None = None,
    synonyms: DomainSynonyms | None = None,
) -> CodeSuggestionSet:
    """Sugere códigos do catálogo para os itens confirmados do takeoff.

    Observação determinística: nenhum item recebe código aqui, e item sem candidato
    elegível sai em `unmatched_item_ids` em vez de receber um candidato forçado.

    Ponto único de sugestão do worker (ver docstring do módulo): quem carrega sinônimos por
    rodada — `synonyms.json` do diretório da rodada, com o seed empacotado como fallback —
    é o chamador (CLI/`local_server`), via `croquito_worker.valuation.cli.load_round_synonyms`.
    """
    return suggest_codes(packet, catalog, contract, config=config, synonyms=synonyms)


def _transmitted_description(description: str) -> str:
    if len(description) <= TRANSMITTED_DESCRIPTION_MAX_LENGTH:
        return description
    return description[: TRANSMITTED_DESCRIPTION_MAX_LENGTH - 1] + _ELLIPSIS


def _payload_item(suggestion: CodeSuggestion, item: TakeoffItem) -> dict[str, object]:
    """Um item da shortlist como o provider o recebe: só o que a decisão de ordem exige."""
    return {
        "item_id": suggestion.item_id,
        "label": item.label,
        "raw_text": item.raw_text,
        "quantity": None if item.quantity is None else str(item.quantity),
        "unit": item.unit,
        "candidates": [
            {
                "code": candidate.code,
                "description": _transmitted_description(candidate.description),
                "unit": candidate.unit,
                "unit_compatible": candidate.unit_compatible,
                "in_contract": candidate.in_contract,
                "lexical_score": candidate.lexical_score,
            }
            for candidate in suggestion.candidates
        ],
    }


def build_refinement_payload(packet: TakeoffPacket, suggestions: CodeSuggestionSet) -> str:
    """Monta o texto determinístico enviado ao provider de refino.

    Determinístico (`sort_keys=True`) porque o digest desse texto é o `input_digest` do
    lineage: o mesmo pacote com a mesma shortlist tem de produzir o mesmo digest. Vai só o
    que a decisão de ordem exige — item, texto lido, quantidade, unidade e os candidatos
    que a via lexical já elegeu. Preço não vai: ordem de shortlist não se decide por preço.
    """
    items_by_id = {item.id: item for item in packet.items}
    missing = sorted(
        suggestion.item_id
        for suggestion in suggestions.suggestions
        if suggestion.item_id not in items_by_id
    )
    if missing:
        raise ValuationValidationError(
            "REFINEMENT_PACKET_MISMATCH",
            "shortlist cita item que o pacote de takeoff informado não contém",
            {"item_ids": missing},
        )
    payload = {
        "items": [
            _payload_item(suggestion, items_by_id[suggestion.item_id])
            for suggestion in suggestions.suggestions
        ]
    }
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def refine_code_suggestions(
    packet: TakeoffPacket,
    suggestions: CodeSuggestionSet,
    adapter: ProviderAdapter,
) -> RefinementResult:
    """Refina a shortlist lexical com uma chamada paga de texto; nunca a substitui.

    O adapter chega pronto do chamador — já embrulhado em retry e budget pela fábrica —,
    então o teto de gasto e a política de retentativa não são decididos aqui. Falha de
    provider (`ProviderExecutionError`) sobe: quem sabe se cabe recusar ou seguir com a
    lexical é o comando, e um fallback escondido neste nível publicaria uma ordem sem
    dizer de onde ela veio.

    A saída do provider é convertida em forma pura e entregue a `apply_refinement`, que é
    quem recusa código fora da shortlist, item desconhecido e nota longa demais. Aqui só se
    recusa o que a conversão não consegue representar: duas respostas para o mesmo item.
    """
    request = build_text_request(
        PromptTask.SCO_REFINEMENT,
        text_payload=build_refinement_payload(packet, suggestions),
    )
    execution = adapter.execute(request)
    output = execution.output
    if not isinstance(output, ScoRefinementOutput):  # pragma: no cover - contrato do adapter
        raise ProviderExecutionError(ProviderFailureCode.INVALID_SCHEMA)

    item_ids = [item.item_id for item in output.items]
    duplicated = sorted({item_id for item_id in item_ids if item_ids.count(item_id) > 1})
    if duplicated:
        raise ValuationValidationError(
            "REFINEMENT_DUPLICATE_ITEM",
            "refino devolveu mais de uma ordem para o mesmo item",
            {"item_ids": duplicated},
        )

    ranked_codes_by_item: dict[str, Sequence[str]] = {
        item.item_id: item.ranked_codes for item in output.items
    }
    notes_by_item = {item.item_id: item.rationale for item in output.items}
    flags_by_item: dict[str, Sequence[str]] = {
        item.item_id: item.flags for item in output.items if item.flags
    }
    refined = apply_refinement(
        suggestions,
        ranked_codes_by_item,
        notes_by_item,
        flags_by_item,
        SuggestionRefinement(
            provider=execution.provider.value,
            model_id=execution.model_id,
            prompt_version=execution.prompt.prompt_version,
            input_digest=execution.input_digest,
        ),
    )
    return RefinementResult(suggestions=refined, execution=execution)
