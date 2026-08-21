"""Ponto único de sugestão de código SCO do worker: shortlist lexical e refino pago.

O módulo é fino de propósito. Ele existe para que exista **um** lugar por onde a sugestão
de código passa, e é esse lugar que o M5 estende: o provider pago de texto entra aqui para
**refinar a shortlist lexical** — reordenar, anotar, explicar —, nunca para substituí-la e
nunca para confirmar código. Confirmação continua sendo ato humano
(`apply_code_assignments`).

Uma shortlist determinística é o fallback permanente do produto, não um estágio
transitório: sem entitlement contratual, sem crédito ou com o provider fora do ar, o
orçamentista continua recebendo shortlist — basta não pedir o refino.
`refine_code_suggestions` **não** tem fallback silencioso: falha de provider sobe para o
chamador, que decide o que fazer, porque publicar a determinística anunciando refino
mentiria sobre o que foi feito.

Qual determinística, mudou em 2026-08-21: quem monta a shortlist da degradação passou a ser
`sco_matching.build_hybrid_code_suggestions` com `index=None` (braço léxico por cobertura
ponderada por IDF), medidamente melhor no catálogo real — ver
`SCO_LEXICAL_IDF_SUGGESTER_VERSION`. `build_code_suggestions` (Dice) permanece porque a
CASCATA do orçamento-base ainda é montada por ela e porque `lexical_similarity` continua
sendo o `lexical_score` publicado em cada candidato das duas vias.

O que sai daqui para o domínio é forma pura: a ordem pedida, as anotações e o lineage da
chamada. Quem valida que a ordem é permutação do que foi transmitido é `apply_refinement`.

O refino deixou de ser UMA chamada em 2026-08-21: a shortlist publicada tem 15 candidatos
por item e o que cabe numa chamada é bem menos, então o estágio manda uma janela de
candidatos por item (`TRANSMITTED_CANDIDATE_WINDOW`) e fatia os itens em lotes que caibam
no `text_payload`. Ver `_refinement_batches` para o custo declarado disso.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Final

from croquito_valuation.assignment import (
    CodeSuggestion,
    CodeSuggestionSet,
    SuggestionConfig,
    SuggestionRefinement,
    apply_refinement,
    suggest_codes,
    suggest_codes_over_cascade,
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
para caber no limite do provider (`ProviderRequest.text_payload`, 20000 caracteres), sem
mudar o que o resultado pode ser. A descrição do catálogo real chega a 1356 caracteres e a
shortlist inteira de um item estouraria o payload sem o corte; ele é marcado com `…` no
texto enviado, e a shortlist — a única coisa que o refino pode reordenar — continua
íntegra.

O teto de itens por chamada de refino DIMINUIU quando `max_candidates_per_item` subiu de 3
para 15 (2026-08-21): com descrição no corte máximo, cada candidato ocupa ~510 caracteres,
então a shortlist inteira de uma prancha real de 15 itens estourava o teto — medido, 113%
com k=5 e 335% com k=15. Os dois números que estavam colapsados num só (quantos candidatos
a orçamentista vê, quantos o modelo reordena) foram separados no mesmo dia:
`TRANSMITTED_CANDIDATE_WINDOW` diz quantos viajam por item, e `_refinement_batches` diz
quantos itens cabem em cada chamada.
"""

TRANSMITTED_CANDIDATE_WINDOW: Final = 10
"""Quantos candidatos de cada item viajam para o refino — a cauda da shortlist não vai.

Dez é o `max_length` de `ScoItemRefinementOutput.ranked_codes` (contrato de saída do
prompt `sco-refinement`, em `croquito_worker.providers`): mais do que isso o provider não
tem como devolver, então mandar mais seria pedir uma resposta que o próprio contrato
recusa. **Se um dia o contrato subir, é lá que se olha** — este número acompanha aquele
`max_length`, não o contrário, e a paridade entre os dois é verificada em teste. Mudar o
contrato exige eval e passa pelo `PROMPT_CHANGE_PROTOCOL`; mudar só este número, não.

Consequência declarada: a shortlist publica 15 candidatos e o modelo opina sobre os 10
primeiros. Os 5 restantes continuam publicados, na ordem que a via léxica deu, e nenhum
deles pode subir por refino. É a troca aceita para o refino voltar a rodar sem tocar no
contrato de prompt.
"""

TEXT_PAYLOAD_MAX_LENGTH: Final = 20000
"""Espelho do `max_length` de `ProviderRequest.text_payload`; paridade verificada em teste.

O valor é declarado aqui, e não lido do modelo, porque ele é usado como PREDICADO de
fatiamento (cabe mais um item nesta chamada?), não como validação — a validação continua
sendo do próprio `ProviderRequest`, que recusa fechado se este número um dia divergir.
"""

_ELLIPSIS: Final = "…"


@dataclass(frozen=True, slots=True)
class RefinementResult:
    """Shortlist refinada e o lineage completo das chamadas pagas que a produziram.

    `executions` é plural desde que o estágio passou a fatiar os itens em lotes: uma
    entrada por chamada, na ordem em que saíram. Quem lê precisa do custo TOTAL, não do
    custo da primeira — por isso não existe atalho `execution` aqui: um chamador que
    lesse só `[0]` publicaria um gasto menor do que o que aconteceu, e o compilador não
    teria como avisar.
    """

    suggestions: CodeSuggestionSet
    executions: tuple[ProviderExecution, ...]

    @property
    def call_count(self) -> int:
        """Quantas chamadas pagas o refino desta prancha custou."""
        return len(self.executions)

    @property
    def estimated_cost_usd(self) -> Decimal | None:
        """Soma do custo estimado das chamadas; `None` quando nenhuma delas o declarou."""
        known = [
            execution.usage.estimated_cost_usd
            for execution in self.executions
            if execution.usage.estimated_cost_usd is not None
        ]
        return sum(known, Decimal(0)) if known else None


def build_code_suggestions(
    packet: TakeoffPacket,
    catalog: PriceCatalog,
    contract: ContractWorkbook | None = None,
    *,
    config: SuggestionConfig | None = None,
    synonyms: DomainSynonyms | None = None,
) -> CodeSuggestionSet:
    """Sugere códigos do catálogo para os itens confirmados do takeoff, pela via Dice.

    Observação determinística: nenhum item recebe código aqui, e item sem candidato
    elegível sai em `unmatched_item_ids` em vez de receber um candidato forçado.

    **Não** é mais a shortlist que a rodada publica quando o braço semântico não pode
    rodar: essa passou a ser a da fusão sem perna semântica
    (`sco_matching.build_hybrid_code_suggestions` com `index=None`). Esta continua sendo o
    tijolo de `build_cascade_code_suggestions` e a via que a demo e o eval exercitam.

    Ponto único de sugestão do worker (ver docstring do módulo): quem carrega sinônimos por
    rodada — `synonyms.json` do diretório da rodada, com o seed empacotado como fallback —
    é o chamador (CLI/`local_server`), via `croquito_worker.valuation.cli.load_round_synonyms`.
    """
    return suggest_codes(packet, catalog, contract, config=config, synonyms=synonyms)


def build_cascade_code_suggestions(
    packet: TakeoffPacket,
    cascade: Sequence[PriceCatalog],
    *,
    config: SuggestionConfig | None = None,
    synonyms: DomainSynonyms | None = None,
) -> CodeSuggestionSet:
    """Shortlist lexical do ORÇAMENTO-BASE: mesma via determinística, várias fontes.

    Ponto único de sugestão do worker também para a cascata (ver docstring do módulo).
    Nenhum provider entra aqui: o refino pago e o braço semântico continuam sendo do
    caminho de um catálogo só, e o comando declara essa degradação em vez de inventar uma
    chamada paga sobre catálogo não-SCO.
    """
    return suggest_codes_over_cascade(packet, cascade, config=config, synonyms=synonyms)


def _transmitted_description(description: str) -> str:
    if len(description) <= TRANSMITTED_DESCRIPTION_MAX_LENGTH:
        return description
    return description[: TRANSMITTED_DESCRIPTION_MAX_LENGTH - 1] + _ELLIPSIS


def _payload_item(suggestion: CodeSuggestion, item: TakeoffItem) -> dict[str, object]:
    """Um item da shortlist como o provider o recebe: só o que a decisão de ordem exige.

    Só a JANELA de candidatos viaja (`TRANSMITTED_CANDIDATE_WINDOW`); a cauda fica de fora
    porque o contrato de saída do prompt não teria como devolvê-la.
    """
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
            for candidate in suggestion.candidates[:TRANSMITTED_CANDIDATE_WINDOW]
        ],
    }


def _payload_entries(
    packet: TakeoffPacket, suggestions: CodeSuggestionSet
) -> list[dict[str, object]]:
    """Um dicionário por item da shortlist, na ordem do conjunto, já com a janela aplicada."""
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
    return [
        _payload_item(suggestion, items_by_id[suggestion.item_id])
        for suggestion in suggestions.suggestions
    ]


def _payload_text(entries: Sequence[dict[str, object]]) -> str:
    return json.dumps(
        {"items": list(entries)}, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )


def build_refinement_payload(packet: TakeoffPacket, suggestions: CodeSuggestionSet) -> str:
    """Monta o texto determinístico do refino INTEIRO — todos os itens, janela aplicada.

    Determinístico (`sort_keys=True`) porque o digest desse texto é o `input_digest` do
    lineage: o mesmo pacote com a mesma shortlist tem de produzir o mesmo digest. Vai só o
    que a decisão de ordem exige — item, texto lido, quantidade, unidade e os candidatos
    que a via lexical já elegeu. Preço não vai: ordem de shortlist não se decide por preço.

    Este texto é o que IDENTIFICA a entrada do estágio, e nem sempre é o que sai numa
    chamada: quando os itens não cabem num `text_payload` só, `_refinement_batches` corta
    este mesmo conteúdo em vários. Com um lote só, os dois coincidem exatamente.
    """
    return _payload_text(_payload_entries(packet, suggestions))


def _refinement_batches(
    packet: TakeoffPacket, suggestions: CodeSuggestionSet
) -> list[tuple[tuple[str, ...], str]]:
    """Fatia os itens em lotes que cabem no `text_payload`; devolve (ids do lote, texto).

    **Isto é aumento de custo declarado**: cada lote é uma chamada paga. Medido no pior
    caso (janela de 10 candidatos, toda descrição no corte de 400), um item ocupa ~5.360
    caracteres e cabem **3 itens por chamada**: uma prancha de 15 itens passa a custar
    **5 chamadas** onde antes fazia 1. Com descrições reais, mais curtas que o corte,
    cabem mais itens e o número cai — o teto é o payload, não uma contagem fixa. A
    alternativa seria enviar menos candidatos ainda, e aí o refino opinaria sobre menos da
    shortlist do que o contrato de prompt permite.

    Fatiar não pode mudar o resultado: a ordem dos itens é a do conjunto, cada item vai
    inteiro em um único lote, e a reordenação só é aplicada no fim, de uma vez
    (`apply_refinement`). Item que sozinho não cabe recusa fechado com
    `REFINEMENT_ITEM_TOO_LARGE` em vez de ser cortado pela metade.

    Conjunto sem nenhum item continua produzindo UM lote vazio: o estágio pagou a chamada e
    o artefato tem de declarar que passou pelo refino, como sempre declarou.
    """
    entries = _payload_entries(packet, suggestions)
    if not entries:
        return [((), _payload_text([]))]

    batches: list[list[dict[str, object]]] = []
    current: list[dict[str, object]] = []
    for entry in entries:
        if len(_payload_text([entry])) > TEXT_PAYLOAD_MAX_LENGTH:
            raise ValuationValidationError(
                "REFINEMENT_ITEM_TOO_LARGE",
                "um único item da shortlist não cabe no payload do provider de refino",
                {
                    "item_id": entry["item_id"],
                    "length": len(_payload_text([entry])),
                    "max_length": TEXT_PAYLOAD_MAX_LENGTH,
                },
            )
        if current and len(_payload_text([*current, entry])) > TEXT_PAYLOAD_MAX_LENGTH:
            batches.append(current)
            current = []
        current.append(entry)
    batches.append(current)
    return [
        (tuple(str(entry["item_id"]) for entry in batch), _payload_text(batch)) for batch in batches
    ]


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
    quem recusa código fora da janela transmitida, item desconhecido e nota longa demais.
    Aqui só se recusa o que a conversão não consegue representar: duas respostas para o
    mesmo item, e resposta sobre item que aquele lote não perguntou.

    **Uma chamada paga por lote** (`_refinement_batches`), não mais uma por prancha. A
    reordenação continua sendo aplicada UMA vez, no fim, sobre o conjunto inteiro: fatiar é
    detalhe de transporte e não pode mudar a shortlist publicada.
    """
    batches = _refinement_batches(packet, suggestions)
    executions: list[ProviderExecution] = []
    ranked_codes_by_item: dict[str, Sequence[str]] = {}
    notes_by_item: dict[str, str] = {}
    flags_by_item: dict[str, Sequence[str]] = {}

    for batch_item_ids, text_payload in batches:
        request = build_text_request(PromptTask.SCO_REFINEMENT, text_payload=text_payload)
        execution = adapter.execute(request)
        executions.append(execution)
        output = execution.output
        if not isinstance(output, ScoRefinementOutput):  # pragma: no cover - contrato do adapter
            raise ProviderExecutionError(ProviderFailureCode.INVALID_SCHEMA)

        item_ids = [item.item_id for item in output.items]
        duplicated = sorted(
            {item_id for item_id in item_ids if item_ids.count(item_id) > 1}
            | (set(item_ids) & set(ranked_codes_by_item))
        )
        if duplicated:
            raise ValuationValidationError(
                "REFINEMENT_DUPLICATE_ITEM",
                "refino devolveu mais de uma ordem para o mesmo item",
                {"item_ids": duplicated},
            )
        outside = sorted(set(item_ids) - set(batch_item_ids))
        if outside:
            raise ValuationValidationError(
                "REFINEMENT_UNKNOWN_ITEM",
                "refino devolveu item que não estava no lote enviado",
                {"unknown_ids": outside},
            )

        ranked_codes_by_item.update({item.item_id: item.ranked_codes for item in output.items})
        notes_by_item.update({item.item_id: item.rationale for item in output.items})
        flags_by_item.update({item.item_id: item.flags for item in output.items if item.flags})

    refined = apply_refinement(
        suggestions,
        ranked_codes_by_item,
        notes_by_item,
        flags_by_item,
        _refinement_lineage(packet, suggestions, executions[0]),
        transmitted_window=TRANSMITTED_CANDIDATE_WINDOW,
    )
    return RefinementResult(suggestions=refined, executions=tuple(executions))


def _refinement_lineage(
    packet: TakeoffPacket, suggestions: CodeSuggestionSet, first: ProviderExecution
) -> SuggestionRefinement:
    """O lineage do ESTÁGIO de refino, não o de uma das chamadas que o compuseram.

    Desenho declarado, porque com fatiamento há várias execuções pagas e `SuggestionRefinement`
    guarda uma só:

    - `provider`, `model_id` e `prompt_version` são idênticos em todos os lotes por
      construção — um único adapter, uma única `PromptTask`, montada uma vez —, então
      tomá-los da primeira execução não perde informação;
    - `input_digest` passa a ser o digest do payload INTEIRO
      (`build_refinement_payload`), não o do primeiro lote. É reproduzível a partir do
      pacote e da shortlist, é estável se o tamanho do lote mudar, e não mente: gravar o
      digest do lote 1 afirmaria que a ordem publicada saiu daquele payload, quando três
      quartos dela vieram de outros. Com um lote só, os dois coincidem exatamente e o
      lineage é bit a bit o de antes.

    O que o modelo de domínio não guarda — custo total e número de chamadas — não some: ele
    viaja em `RefinementResult.executions`, que é o que o comando e a eval publicam.
    """
    payload = build_refinement_payload(packet, suggestions).strip()
    return SuggestionRefinement(
        provider=first.provider.value,
        model_id=first.model_id,
        prompt_version=first.prompt.prompt_version,
        input_digest=hashlib.sha256(payload.encode("utf-8")).hexdigest(),
    )
