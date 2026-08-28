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

import hashlib
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from croquito_valuation.assignment import CodeSuggestionSet, suggest_codes_over_cascade
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
    CascadeSemanticSource,
    build_hybrid_code_suggestions,
    build_hybrid_code_suggestions_over_cascade,
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

    @classmethod
    def from_executions(
        cls,
        *,
        model_id: str,
        executions: Sequence[EmbeddingsExecution],
        sources_with_index: int,
        sources_total: int,
        reason: str | None = None,
    ) -> SemanticArmTelemetry:
        """A mesma telemetria de N fontes da cascata: um gasto por fonte, somado.

        Tokens e custo são SOMA porque a grandeza que se quer observar é o que o ato inteiro
        custou — o recompute é um clique só, ainda que a cascata tenha três tabelas. Cada
        fonte pode ter respondido pelo cache (nenhuma execução) ou ter pago, e por isso a
        soma ignora as ausentes em vez de zerar tudo: `None` continua significando "nada foi
        pago", e não "custou zero".

        `reason` acompanha um braço que RODOU com cobertura parcial (ADR-0054 D6): ele diz
        por que alguma fonte ficou de fora, e `sources_with_index < sources_total` diz
        quantas. Sem ele, o evento de uma cascata meio indexada seria indistinguível do de
        uma cascata inteiramente indexada.
        """
        usages = [execution.usage for execution in executions]
        tokens = [usage.input_tokens for usage in usages if usage.input_tokens is not None]
        costs = [
            usage.estimated_cost_usd for usage in usages if usage.estimated_cost_usd is not None
        ]
        return cls(
            arm_ran=True,
            reason=reason,
            model_id=model_id,
            input_tokens=sum(tokens) if tokens else None,
            estimated_cost_usd=str(sum(costs)) if costs else None,
            sources_with_index=sources_with_index,
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


def query_cache_path_for_model(directory: Path, model_id: str) -> Path:
    """Onde os vetores de consulta de UM modelo ficam dentro do diretório do ato.

    Um arquivo por modelo, e não um por fonte: duas fontes da cascata indexadas pelo MESMO
    modelo compartilham o espaço vetorial e devem compartilhar o cache — resolver os mesmos
    rótulos duas vezes pagaria duas vezes pelo mesmo vetor. Modelos diferentes ficam
    separados porque `load_query_cache` recusa (com razão) um cache gravado por outro
    modelo, e um arquivo único faria a segunda fonte derrubar o braço da primeira.

    O nome é o digest do `model_id`, e não o `model_id`: ele vem do documento publicado e
    seria caminho de arquivo montado a partir de texto que ninguém conferiu.
    """
    digest = hashlib.sha256(model_id.encode("utf-8")).hexdigest()[:16]
    return directory / f"query-embeddings-{digest}.json"


def compute_cascade_suggestions(
    packet: TakeoffPacket,
    cascade: Sequence[PriceCatalog],
    synonyms: DomainSynonyms,
    *,
    arms: Sequence[SemanticArm],
    query_cache_dir: Path,
) -> tuple[CodeSuggestionSet, list[str], SemanticArmTelemetry]:
    """A irmã de `compute_suggestions` para a CASCATA: um braço semântico por fonte.

    Mesma disciplina do caminho de um catálogo só, aplicada fonte a fonte (ADR-0054 D5/D6):
    a fonte com índice e adapter tem os rótulos embutidos e entra na fusão pelos dois braços;
    a fonte sem índice — ou cuja resolução de vetores recusou — entra com o braço léxico e o
    motivo vai para as notas, nomeando **qual** fonte ficou sem. Nenhum desses casos é erro:
    cobertura parcial é estado normal, e a shortlist sai igual em forma, com uma perna a
    menos naquele bloco.

    A falha de UMA fonte não contamina as demais de propósito. Degradar a cascata inteira
    porque o índice da EMOP foi recusado tiraria do orçamentista a vizinhança semântica do
    SCO, que estava disponível e já foi paga.

    Com NENHUMA fonte respondendo pelo braço semântico, a shortlist é a lexical de sempre
    (`suggest_codes_over_cascade`) — **o algoritmo não muda por causa de uma perna que não
    existe**. É a diferença entre acrescentar um braço e trocar de via: enquanto nenhum
    índice estiver publicado, o recálculo devolve exatamente a shortlist que o `GET` já
    devolvia, e a única coisa nova são as notas dizendo por quê. Trocar para a via de
    cobertura ponderada nesse caso seria uma mudança de comportamento medida noutro contexto
    (um catálogo só, `SCO_LEXICAL_IDF_SUGGESTER_VERSION`) e nunca medida na cascata.

    `query_cache_dir` é o diretório do ATO, e a chamada é a única coisa cara aqui: quem o
    cria e o descarta é o chamador (ver o recompute da API), porque a decisão de não
    persistir vetor de consulta é de fronteira de dado, não deste cálculo.
    """
    require_reviewed_takeoff(packet)
    if len(arms) != len(cascade):
        raise ValuationValidationError(
            "SEMANTIC_CASCADE_SOURCES_MISMATCH",
            "cada fonte da cascata precisa de exatamente um braço semântico declarado",
            {"cascade": len(cascade), "arms": len(arms)},
        )
    labels = [item.label for item in packet.confirmed_items()]
    notes: list[str] = []
    executions: list[EmbeddingsExecution] = []
    sources: list[CascadeSemanticSource] = []
    model_ids: list[str] = []
    for arm in arms:
        if arm.index is None:
            notes.append(arm.message)
            sources.append(CascadeSemanticSource(None))
            continue
        try:
            resolved = resolve_query_vectors(
                labels,
                index=arm.index,
                cache_path=query_cache_path_for_model(query_cache_dir, arm.index.model_id),
                adapter=arm.adapter,
            )
        except ValuationValidationError as error:
            if error.code not in SEMANTIC_DEGRADABLE_CODES:
                raise
            notes.append(f"{SEMANTIC_UNAVAILABLE_MESSAGE}: {error.code}")
            sources.append(CascadeSemanticSource(None))
            continue
        except ProviderExecutionError as error:
            notes.append(f"{SEMANTIC_UNAVAILABLE_MESSAGE}: provider {error.code.value}")
            sources.append(CascadeSemanticSource(None))
            continue
        if resolved.execution is not None:
            executions.append(resolved.execution)
        model_ids.append(arm.index.model_id)
        sources.append(CascadeSemanticSource(arm.index, resolved.by_query))
    # Notas repetidas viram uma: quando o que faltou é do ATO (entitlement, ambiente,
    # credencial), todas as fontes carregam a MESMA frase, e repeti-la uma vez por tabela
    # daria à tela três avisos idênticos sobre um problema só.
    notes = list(dict.fromkeys(notes))
    if not model_ids:
        return (
            suggest_codes_over_cascade(packet, cascade, synonyms=synonyms),
            notes,
            SemanticArmTelemetry.lexical_only(
                notes[0] if notes else SEMANTIC_UNAVAILABLE_MESSAGE, sources_total=len(cascade)
            ),
        )
    computed = build_hybrid_code_suggestions_over_cascade(
        packet,
        cascade,
        sources,
        synonyms=synonyms,
        noise=default_legend_noise(),
    )
    telemetry = SemanticArmTelemetry.from_executions(
        # O modelo da PRIMEIRA fonte que rodou, e não uma lista: o campo é singular no
        # contrato da telemetria e a cascata usa o mesmo modelo em todas as fontes na
        # prática (o índice de todas é publicado pela mesma via). Cascata com modelos
        # diferentes continua declarando as contagens certas; qual fonte usou qual modelo é
        # o que o `semantic` do próprio artefato guarda, com o digest do índice.
        model_id=model_ids[0],
        executions=executions,
        sources_with_index=len(model_ids),
        sources_total=len(cascade),
        reason=notes[0] if notes else None,
    )
    return computed, notes, telemetry
