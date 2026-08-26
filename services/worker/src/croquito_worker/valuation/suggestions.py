"""Cálculo da shortlist de códigos SCO da rodada: híbrida quando dá, léxica sempre.

O que mora aqui é a DECISÃO de qual shortlist computar e o que dizer quando o braço pago
não pôde participar. Quem lê os artefatos da rodada, publica o resultado e calcula digest
é o adaptador — este módulo recebe pacote, catálogo, contrato e sinônimos já carregados e
devolve o conjunto calculado mais as notas que a tela mostra.

Duas regras atravessam o cálculo:

- **Revisão do takeoff completa é precondição.** Computar sobre um pacote meio revisado
  congelaria uma shortlist sem os itens que ainda vão ser confirmados.
- **O braço pago nunca quebra a shortlist.** Falta de índice, de teto de gasto ou de
  credencial — e falha do provider — degradam para a MESMA via com um braço a menos (o
  léxico por cobertura ponderada), com o motivo declarado em `notes`, nunca em erro e
  nunca em silêncio. Degradar é perder a perna semântica, não trocar de algoritmo: até
  2026-08-21 este módulo desviava para a via Dice (`build_code_suggestions`), medidamente
  pior no catálogo real — ver `SCO_LEXICAL_IDF_SUGGESTER_VERSION`.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from croquito_valuation.assignment import CodeSuggestionSet
from croquito_valuation.catalog import DomainSynonyms, default_legend_noise
from croquito_valuation.contract import ContractWorkbook
from croquito_valuation.errors import ValuationValidationError
from croquito_valuation.models import PriceCatalog
from croquito_valuation.takeoff import TakeoffPacket
from croquito_worker.providers import EmbeddingsExecution, ProviderExecutionError
from croquito_worker.valuation.catalog_search import (
    SEMANTIC_UNAVAILABLE_MESSAGE,
    SemanticArm,
)
from croquito_worker.valuation.sco_matching import (
    SEMANTIC_DEGRADABLE_CODES,
    build_hybrid_code_suggestions,
    resolve_query_vectors,
)


@dataclass(frozen=True, slots=True)
class SemanticArmTelemetry:
    """O que a via paga de embeddings gastou ao (re)computar uma shortlist de código.

    Observabilidade, nunca freio: o teto de gasto continua no adapter
    (`BudgetedProviderAdapter` + `CROQUITO_AI_MAX_ESTIMATED_COST_USD`). Os campos são só o que
    o `CLAUDE.md` autoriza a registrar de uma chamada paga — se o braço rodou, model id,
    tokens de entrada, custo estimado e a contagem de fontes com índice —, jamais o CONTEÚDO
    (rótulos, descrições) que foi embutido.

    `arm_ran=False` é registro POSITIVO, não ausência: uma recomputação só léxica declara que
    a vizinhança semântica não participou, com o motivo já declarado ao lado (`reason`, o mesmo
    texto que viaja em `semantic_notes`). `input_tokens`/`estimated_cost_usd` nulos com
    `arm_ran=True` é o caso legítimo do cache de consulta: o braço respondeu sem chamada paga
    nova. `estimated_cost_usd` viaja como TEXTO pela mesma disciplina de
    `chat_turns.estimated_cost_usd`, para não devolver o `Decimal` do custo como float de JSON.
    """

    arm_ran: bool
    reason: str | None
    model_id: str | None
    input_tokens: int | None
    estimated_cost_usd: str | None
    sources_with_index: int
    sources_total: int

    @classmethod
    def lexical_only(cls, reason: str, *, sources_total: int = 1) -> SemanticArmTelemetry:
        """Braço semântico ausente: nenhuma fonte com índice, custo nulo, motivo declarado."""
        return cls(
            arm_ran=False,
            reason=reason,
            model_id=None,
            input_tokens=None,
            estimated_cost_usd=None,
            sources_with_index=0,
            sources_total=sources_total,
        )

    @classmethod
    def from_execution(
        cls,
        *,
        model_id: str,
        execution: EmbeddingsExecution | None,
        sources_total: int = 1,
    ) -> SemanticArmTelemetry:
        """Braço que rodou: tokens e custo vêm da execução paga, nulos quando foi só cache."""
        usage = None if execution is None else execution.usage
        return cls(
            arm_ran=True,
            reason=None,
            model_id=model_id,
            input_tokens=None if usage is None else usage.input_tokens,
            estimated_cost_usd=(
                None
                if usage is None or usage.estimated_cost_usd is None
                else str(usage.estimated_cost_usd)
            ),
            sources_with_index=1,
            sources_total=sources_total,
        )

    def event_payload(self) -> dict[str, Any]:
        """Bloco a fundir no evento de rodada e no log; só grandezas, nunca conteúdo."""
        return {
            "semantic_arm_ran": self.arm_ran,
            "semantic_reason": self.reason,
            "model_id": self.model_id,
            "input_tokens": self.input_tokens,
            "estimated_cost_usd": self.estimated_cost_usd,
            "sources_with_index": self.sources_with_index,
            "sources_total": self.sources_total,
        }


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
) -> tuple[CodeSuggestionSet, list[str], SemanticArmTelemetry]:
    """Recomputa a shortlist do zero e devolve o conjunto, as notas e a telemetria do braço.

    Com índice, teto de gasto e credencial, a shortlist é a **híbrida** — fusão do braço
    léxico com a vizinhança semântica, amortecendo palavras de ESTADO da legenda
    (`default_legend_noise()`, rodada 2.2) — e embutir os rótulos custa uma chamada paga
    pequena, cacheada em `query_cache_path` (rodada). Faltando qualquer um dos três, a
    mesma função monta a shortlist sem o braço semântico (`index=None`) e o motivo viaja
    nas notas: o que a degradação tira é a perna paga, não o algoritmo.

    Nada é gravado aqui: publicar o conjunto e calcular o digest é do adaptador. O único
    arquivo tocado é o cache de vetores da rodada, que é insumo da chamada paga e não
    artefato de decisão.

    A terceira saída é a `SemanticArmTelemetry` do gasto: ela nasce aqui porque este é o
    único ponto que sabe se a chamada paga aconteceu e o que ela custou (via
    `resolve_query_vectors`, cujo `execution` era descartado). Quem só quer a shortlist
    ignora o terceiro elemento; o recompute da API o registra no evento e no log.
    """
    require_reviewed_takeoff(packet)
    computed: CodeSuggestionSet | None = None
    notes: list[str] = []
    execution: EmbeddingsExecution | None = None
    arm_ran = False
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
            execution = resolved.execution
            arm_ran = True
        except ValuationValidationError as error:
            if error.code not in SEMANTIC_DEGRADABLE_CODES:
                raise
            notes.append(f"{SEMANTIC_UNAVAILABLE_MESSAGE}: {error.code}")
        except ProviderExecutionError as error:
            notes.append(f"{SEMANTIC_UNAVAILABLE_MESSAGE}: provider {error.code.value}")
    if computed is None:
        computed = build_hybrid_code_suggestions(
            packet,
            catalog,
            contract,
            synonyms=synonyms,
            noise=default_legend_noise(),
        )
    if arm_ran and semantic.index is not None:
        telemetry = SemanticArmTelemetry.from_execution(
            model_id=semantic.index.model_id, execution=execution
        )
    else:
        telemetry = SemanticArmTelemetry.lexical_only(notes[-1] if notes else semantic.message)
    return computed, notes, telemetry
