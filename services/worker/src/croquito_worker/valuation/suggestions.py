"""Cálculo da shortlist de códigos SCO da rodada: híbrida quando dá, lexical sempre.

O que mora aqui é a DECISÃO de qual shortlist computar e o que dizer quando o braço pago
não pôde participar. Quem lê os artefatos da rodada, publica o resultado e calcula digest
é o adaptador — este módulo recebe pacote, catálogo, contrato e sinônimos já carregados e
devolve o conjunto calculado mais as notas que a tela mostra.

Duas regras atravessam o cálculo:

- **Revisão do takeoff completa é precondição.** Computar sobre um pacote meio revisado
  congelaria uma shortlist sem os itens que ainda vão ser confirmados.
- **O braço pago nunca quebra a shortlist.** Falta de índice, de teto de gasto ou de
  credencial — e falha do provider — degradam para a shortlist lexical com o motivo
  declarado em `notes`, nunca em erro e nunca em silêncio.
"""

from __future__ import annotations

from pathlib import Path

from croquito_valuation.assignment import CodeSuggestionSet
from croquito_valuation.catalog import DomainSynonyms, default_legend_noise
from croquito_valuation.contract import ContractWorkbook
from croquito_valuation.errors import ValuationValidationError
from croquito_valuation.models import PriceCatalog
from croquito_valuation.takeoff import TakeoffPacket
from croquito_worker.providers import ProviderExecutionError
from croquito_worker.valuation.catalog_search import (
    SEMANTIC_UNAVAILABLE_MESSAGE,
    SemanticArm,
)
from croquito_worker.valuation.sco_matching import (
    SEMANTIC_DEGRADABLE_CODES,
    build_hybrid_code_suggestions,
    resolve_query_vectors,
)
from croquito_worker.valuation.sco_suggestion import build_code_suggestions


def require_reviewed_takeoff(packet: TakeoffPacket) -> None:
    """Recusa a shortlist enquanto sobrar item pendente de revisão no takeoff.

    Guarda declarada à parte porque o adaptador a chama ANTES de carregar catálogo,
    contrato e sinônimos: revisão incompleta é a recusa mais próxima do ato do
    orçamentista, e ela não deve ficar atrás de um `LOCAL_ARTIFACT_MISSING` de outro
    artefato. Ela continua valendo aqui dentro, para que o cálculo seja fail-closed
    sozinho.
    """
    pending = packet.pending_items()
    if pending:
        raise ValuationValidationError(
            "LOCAL_TAKEOFF_REVIEW_INCOMPLETE",
            "sugestão de código exige a revisão do takeoff concluída",
            {"pending_item_ids": [item.id for item in pending]},
        )


def compute_suggestions(
    packet: TakeoffPacket,
    catalog: PriceCatalog,
    contract: ContractWorkbook | None,
    synonyms: DomainSynonyms,
    *,
    semantic: SemanticArm,
    query_cache_path: Path,
) -> tuple[CodeSuggestionSet, list[str]]:
    """Recomputa a shortlist do zero e devolve o conjunto e as notas do braço semântico.

    Com índice, teto de gasto e credencial, a shortlist é a **híbrida** — fusão do braço
    léxico com a vizinhança semântica, amortecendo palavras de ESTADO da legenda
    (`default_legend_noise()`, rodada 2.2) — e embutir os rótulos custa uma chamada paga
    pequena, cacheada em `query_cache_path` (rodada). Faltando qualquer um dos três, a
    shortlist é a lexical e o motivo viaja nas notas.

    Nada é gravado aqui: publicar o conjunto e calcular o digest é do adaptador. O único
    arquivo tocado é o cache de vetores da rodada, que é insumo da chamada paga e não
    artefato de decisão.
    """
    require_reviewed_takeoff(packet)
    computed: CodeSuggestionSet | None = None
    notes: list[str] = []
    if semantic.index is None:
        notes.append(semantic.message)
    else:
        try:
            resolved = resolve_query_vectors(
                [item.label for item in packet.confirmed_items()],
                index=semantic.index,
                cache_path=query_cache_path,
                adapter=semantic.adapter,
            )
            computed = build_hybrid_code_suggestions(
                packet,
                catalog,
                contract,
                index=semantic.index,
                query_vectors=resolved.by_query,
                synonyms=synonyms,
                noise=default_legend_noise(),
            )
        except ValuationValidationError as error:
            if error.code not in SEMANTIC_DEGRADABLE_CODES:
                raise
            notes.append(f"{SEMANTIC_UNAVAILABLE_MESSAGE}: {error.code}")
        except ProviderExecutionError as error:
            notes.append(f"{SEMANTIC_UNAVAILABLE_MESSAGE}: provider {error.code.value}")
    if computed is None:
        computed = build_code_suggestions(packet, catalog, contract, synonyms=synonyms)
    return computed, notes
