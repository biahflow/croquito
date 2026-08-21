"""Retrieval híbrido de código SCO: braço léxico, braço semântico e fusão de ranking.

Este módulo existe por causa de um limite MEDIDO, não de uma intuição. A Fase 1 do M7
melhorou o matcher léxico (radical + sinônimo) e mediu o teto dele contra o catálogo real:
8 dos 12 rótulos reais da Toca com código correto ficaram fora do top-20, em ranks de 26 a
853 (`tests/valuation/golden/matcher-golden-v1.json`). A causa é sistemática — o Dice
penaliza a descrição longa, e vários códigos SCO têm descrição de um parágrafo inteiro —,
então mais léxico não fecha o vão. O que fecha é um segundo braço que compare SENTIDO em
vez de palavra, e uma fusão que não deixe nenhum dos dois mandar sozinho.

As três peças, todas determinísticas dado o índice:

- **braço léxico**: `weighted_query_coverage_score` (que fração da consulta a descrição
  cobre, cada palavra pesada pelo IDF dela no catálogo), com `lexical_similarity`
  desempatando. Cobertura não tem denominador do lado da descrição, então o parágrafo
  deixa de ser punido; o IDF impede que cobrir "piso" valha o mesmo que cobrir
  "intertravado".
- **braço semântico**: kNN por cosseno sobre um índice de embeddings do catálogo,
  construído UMA vez por catálogo (`index-catalog`) e amarrado ao digest dele.
- **fusão**: Reciprocal Rank Fusion (`RRF_K = 60`), que combina POSIÇÕES e não scores —
  é o que permite fundir uma medida em [0, 1] com um cosseno sem calibrar escala.

Limites declarados:

- O índice é dado local, derivado do catálogo do cliente; ele não é versionado.
- Índice de outro catálogo é recusado na carga (`INDEX_CATALOG_MISMATCH`), nunca usado
  "porque estava lá": vetor de outro catálogo devolveria código que não existe no vigente.
- Embutir consulta nova é chamada PAGA. Ela só acontece com teto de gasto e credencial
  declarados no ambiente; sem isso o produto inteiro degrada para o braço léxico, com o
  motivo visível — nunca em silêncio.
- O cache de consulta é por rodada e amarrado ao modelo; cache de outro modelo recusa em
  vez de misturar espaços vetoriais incomparáveis.
"""

from __future__ import annotations

import base64
import hashlib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Final, Literal

import numpy as np
import numpy.typing as npt
from pydantic import BaseModel, ConfigDict, Field, model_validator

from croquito_valuation.assignment import (
    SCO_HYBRID_SUGGESTER_VERSION,
    SCO_LEXICAL_IDF_SUGGESTER_VERSION,
    CodeCandidate,
    CodeSuggestion,
    CodeSuggestionSet,
    SuggestionConfig,
    SuggestionSemantics,
)
from croquito_valuation.catalog import (
    DomainSynonyms,
    LegendNoiseList,
    StemIdfTable,
    build_stem_idf_table,
    lexical_similarity,
    normalize_unit,
    weighted_query_coverage_score,
)
from croquito_valuation.contract import ContractWorkbook
from croquito_valuation.errors import ValuationValidationError
from croquito_valuation.models import SHA256_PATTERN, PriceCatalog, PriceCatalogEntry
from croquito_valuation.takeoff import TakeoffPacket
from croquito_worker.io_utils import atomic_write_text
from croquito_worker.providers import (
    EMBEDDINGS_MAX_BATCH,
    EmbeddingsAdapter,
    EmbeddingsExecution,
    ProviderName,
    build_embeddings_adapter,
)

CATALOG_INDEX_FILENAME: Final = "catalog-embeddings.json"
"""Índice de embeddings do catálogo, gravado ao lado do `catalog.json` que o originou."""

QUERY_CACHE_FILENAME: Final = "query-embeddings.json"
"""Cache de vetores de consulta da rodada: um rótulo embutido uma vez, reusado sempre."""

INDEX_SCHEMA_VERSION: Final = "catalog-embeddings-v1"
QUERY_CACHE_SCHEMA_VERSION: Final = "query-embeddings-v1"

RRF_K: Final = 60
"""Constante do Reciprocal Rank Fusion, no valor clássico da literatura (Cormack 2009).

Ela controla o quanto o topo de uma lista domina: com 60, a diferença entre o 1º e o 2º
lugar de um braço (1/61 contra 1/62) é pequena perto do ganho de aparecer nos DOIS braços
(2/70 para dois décimos lugares). É exatamente o comportamento desejado aqui — corroboração
entre braços vale mais do que primeiro lugar num braço só."""

HYBRID_DEFAULT_K: Final = 20
"""Profundidade padrão da lista fundida: o mesmo k do gate de recall do golden."""

HYBRID_ARM_DEPTH: Final = 50
"""Quantos candidatos cada braço propõe antes da fusão, quando o chamador não escolhe.

Calibrado contra o catálogo real (4.964 itens) e os 12 casos reais do golden, não escolhido
por gosto — recall@20 da fusão na configuração vigente (cobertura ponderada por IDF,
oráculo de família, `text-embedding-3-small`), medido em 2026-08-13:

| profundidade de braço | 20 | 30 | 50 | 80 | 120 | 200 |
|---|---|---|---|---|---|---|
| recall@20 | 9/12 | 10/12 | **11/12** | 10/12 | 10/12 | 10/12 |

O formato da curva tem explicação, e é ela que justifica o número: braço raso demais perde
o candidato que só um dos lados enxerga (com 20 ficam de fora PISO EM SAIBRO e FORRAÇÃO EM
GRAMA); braço fundo demais deixa entrar pares corroborados em posições ruins, que empurram
para fora da página o candidato que um braço só colocou no topo (com 80 cai o PISO
INTERTRAVADO, com 120 e 200 cai a GOLA QUADRADA). O ótimo em 50 se manteve nas duas
configurações medidas — antes e depois do IDF —, o que é evidência de que ele descreve a
fusão e não um ajuste a um conjunto de casos."""

_FLOAT32: Final = "<f4"
"""float32 little-endian explícito: o índice é lido por outra máquina que não a que gravou."""

SEMANTIC_INDEX_MISSING: Final = (
    "rodada sem índice de embeddings do catálogo; rode `index-catalog` para criá-lo"
)
SEMANTIC_UNAVAILABLE_PREFIX: Final = "via de embeddings indisponível"

SEMANTIC_DEGRADABLE_CODES: Final[frozenset[str]] = frozenset(
    {
        "SEMANTIC_QUERY_NOT_CACHED",
        "QUERY_CACHE_MODEL_MISMATCH",
        "SEMANTIC_QUERY_DIMS_MISMATCH",
    }
)
"""Recusas que significam "o braço semântico não pode responder ESTA consulta".

Só elas autorizam degradar para o léxico; qualquer outra recusa de domínio sobe, porque
degradar em cima de um erro que não é do braço semântico esconderia o defeito real."""


def embeddings_adapter_or_reason() -> tuple[EmbeddingsAdapter | None, str | None]:
    """Adapter de embeddings do processo, ou o motivo declarado de ele não existir.

    A recusa da fábrica (sem teto de gasto, sem credencial) é motivo, não exceção: quem
    consulta sem poder pagar recebe o braço léxico com o porquê ao lado, em vez de um erro.
    """
    try:
        return build_embeddings_adapter(), None
    except ValueError as error:
        return None, f"{SEMANTIC_UNAVAILABLE_PREFIX}: {error}"


INDEX_TEXT_RECIPE: Final = "code-description-unit-v1"
"""Qual texto de cada item foi embutido no índice — parte da identidade dele.

Trocar a receita muda os vetores tanto quanto trocar de modelo, e um índice de receita
antiga misturado com uma consulta de hoje degradaria a busca em silêncio. Por isso ela é
gravada no documento e conferida na carga (`INDEX_TEXT_RECIPE_MISMATCH`), e por isso o
`index-catalog` reconstrói em vez de reusar quando a receita mudou.

- `code-description-unit-v1`: `"{código} {descrição} ({unidade})"` — a receita EM USO;
- `description-unit-v2`: `"{descrição} ({unidade})"` — construída e medida na rodada 2.1 e
  **descartada**. A hipótese era razoável (o código SCO é etiqueta opaca, não linguagem) e
  a medição a derrubou; ver `INDEX_TEXT_RECIPE_MEASUREMENT`.
"""

INDEX_TEXT_RECIPE_MEASUREMENT: Final = """Rodada 2.1 (2026-08-13), golden real, 12 casos
com código, cobertura ponderada por IDF, profundidade de braço 50, `text-embedding-3-small`
e oráculo de CÓDIGO ÚNICO (a comparação foi feita antes do oráculo de família, e as duas
receitas foram medidas na mesma régua); um índice pago construído por receita:

| receita | recall@20 | top-1 | top-3 |
|---|---|---|---|
| `code-description-unit-v1` | **9/12** | 2 | 2 |
| `description-unit-v2` | 8/12 | 2 | 3 |

A v2 melhora o braço semântico de vários casos (GRAMADO 8 -> 3, PISO INTERTRAVADO 113 ->
73, ALAMBRADO DO CAMPO 100 -> 78) e piora o de outros (PISO EM SAIBRO 28 -> 43, GOLA
QUADRADA 285 -> 341, FORRAÇÃO EM GRAMA 37 -> 56). É essa última que decide: a FORRAÇÃO cai
do rank 9 para o 54 na lista fundida e sai do top-20, custando um caso de recall. A leitura
provável — não verificada, e por isso registrada como hipótese — é que o prefixo de família
do código (`PJ04`, `PJ24`) funciona como um sinal fraco de agrupamento no espaço vetorial.
Fica o registro para que ninguém refaça o experimento achando que é ganho óbvio."""


def catalog_index_text(entry: PriceCatalogEntry) -> str:
    """Texto embutido de um item do catálogo: código, descrição e unidade.

    É a receita `code-description-unit-v1` (`INDEX_TEXT_RECIPE`). A unidade entra porque
    "fornecimento de banco (un)" e "assentamento de banco (m)" são serviços diferentes que a
    descrição nem sempre distingue. O código entra porque **medimos** que tirá-lo custa um
    caso de recall no golden real, contra a intuição de que etiqueta opaca é só ruído
    (`INDEX_TEXT_RECIPE_MEASUREMENT`). Preço não entra: preço não é sentido.
    """
    return f"{entry.code} {entry.description} ({entry.unit})"


def normalize_query_text(text: str) -> str:
    """Chave do cache de consulta, que é também o texto exatamente embutido.

    Só caixa e espaço em branco são normalizados; acento é preservado de propósito — ele
    carrega sentido em português e o modelo de embedding o usa. A chave ser o próprio texto
    embutido é o que impede o cache de devolver o vetor de um texto diferente do pedido.
    """
    return " ".join(text.split()).casefold()


# --------------------------------------------------------------------------------------
# Índice do catálogo
# --------------------------------------------------------------------------------------


class CatalogEmbeddingIndex(BaseModel):
    """Documento do índice em disco: vetores em base64 de float32, um código por linha.

    Base64 e não lista JSON por tamanho: o catálogo real tem 4.965 itens e o modelo padrão
    devolve 1.536 dimensões, o que dá 7,6 milhões de floats. Em lista JSON isso passa de
    100 MB e leva dezenas de segundos para carregar; em float32 base64 são ~30 MB de texto
    (~23 MB de bytes) lidos de uma vez por `numpy.frombuffer`. A precisão de float32 é
    folgada para um cosseno cujo uso é ordenar.

    `catalog_sha256` amarra o índice ao catálogo que o originou e `text_recipe` diz QUAL
    texto de cada item foi embutido — as duas coisas precisam bater para o índice servir.
    `batch_digests` é o lineage da via de embeddings, que não tem prompt:
    `{model_id, input_count, input_digest}` por lote enviado.
    """

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["catalog-embeddings-v1"] = INDEX_SCHEMA_VERSION
    text_recipe: Literal["code-description-unit-v1", "description-unit-v2"] = (
        "code-description-unit-v1"
    )
    provider: str = Field(min_length=1, max_length=40)
    model_id: str = Field(min_length=1, max_length=160)
    catalog_sha256: str = Field(pattern=SHA256_PATTERN)
    dims: int = Field(ge=1, le=8192)
    codes: list[str] = Field(min_length=1)
    vectors_base64: str = Field(min_length=1)
    batch_digests: list[str] = Field(min_length=1)
    built_at: str = Field(min_length=1, max_length=40)

    @model_validator(mode="after")
    def validate_payload_size(self) -> CatalogEmbeddingIndex:
        expected = len(self.codes) * self.dims * 4
        try:
            payload = base64.b64decode(self.vectors_base64, validate=True)
        except ValueError as error:
            raise ValuationValidationError(
                "INDEX_PAYLOAD_INVALID",
                "vetores do índice não são base64 válido",
                {"codes": len(self.codes)},
            ) from error
        if len(payload) != expected:
            raise ValuationValidationError(
                "INDEX_PAYLOAD_INVALID",
                "tamanho dos vetores do índice não corresponde a códigos vezes dimensões",
                {"expected_bytes": expected, "actual_bytes": len(payload)},
            )
        return self


@dataclass(frozen=True, slots=True)
class SemanticIndex:
    """Índice já carregado e conferido contra o catálogo, pronto para o kNN.

    `matrix` tem uma linha por código, **L2-normalizada na construção**: com isso o cosseno
    é um produto interno e a busca inteira é uma multiplicação matriz-vetor.
    """

    provider: str
    model_id: str
    dims: int
    catalog_sha256: str
    index_sha256: str
    codes: tuple[str, ...]
    matrix: npt.NDArray[np.float32]


@dataclass(frozen=True, slots=True)
class CatalogIndexBuild:
    """Índice construído mais o que a construção custou."""

    index: CatalogEmbeddingIndex
    item_count: int
    batch_count: int
    input_tokens: int | None
    estimated_cost_usd: str | None
    latency_ms: int


def normalize_rows(matrix: npt.NDArray[np.float32]) -> npt.NDArray[np.float32]:
    """Normaliza cada linha em L2; linha nula continua nula (cosseno 0, nunca NaN)."""
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    safe = np.where(norms == 0, np.float32(1.0), norms)
    return (matrix / safe).astype(np.float32)


def encode_vectors(matrix: npt.NDArray[np.float32]) -> str:
    return base64.b64encode(matrix.astype(_FLOAT32).tobytes()).decode("ascii")


def decode_vectors(payload: str, *, rows: int, dims: int) -> npt.NDArray[np.float32]:
    raw = base64.b64decode(payload, validate=True)
    flat = np.frombuffer(raw, dtype=np.dtype(_FLOAT32))
    return np.asarray(flat, dtype=np.float32).reshape(rows, dims)


def build_catalog_index(
    catalog: PriceCatalog, adapter: EmbeddingsAdapter, *, provider: str = ProviderName.OPENAI.value
) -> CatalogIndexBuild:
    """Embute o catálogo inteiro em lotes e devolve o índice normalizado.

    O lote é o teto do provider (`EMBEDDINGS_MAX_BATCH`); cada lote é uma chamada paga com
    reserva própria no `CostBudget`. Dimensão que muda entre lotes recusa o índice inteiro:
    misturar dimensões produziria um kNN sem sentido.
    """
    texts = [catalog_index_text(entry) for entry in catalog.entries]
    codes = [entry.code for entry in catalog.entries]
    executions: list[EmbeddingsExecution] = []
    rows: list[tuple[float, ...]] = []
    for start in range(0, len(texts), EMBEDDINGS_MAX_BATCH):
        execution = adapter.embed(texts[start : start + EMBEDDINGS_MAX_BATCH])
        executions.append(execution)
        rows.extend(execution.vectors)
    dims = executions[0].dims
    if any(execution.dims != dims for execution in executions):
        raise ValuationValidationError(
            "INDEX_DIMS_INCONSISTENT",
            "lotes de embeddings devolveram dimensões diferentes; índice não publicado",
            {"dims": sorted({execution.dims for execution in executions})},
        )
    matrix = normalize_rows(np.asarray(rows, dtype=np.float32))
    tokens = [
        execution.usage.input_tokens
        for execution in executions
        if execution.usage.input_tokens is not None
    ]
    costs = [
        execution.usage.estimated_cost_usd
        for execution in executions
        if execution.usage.estimated_cost_usd is not None
    ]
    index = CatalogEmbeddingIndex(
        text_recipe=INDEX_TEXT_RECIPE,
        provider=provider,
        model_id=executions[0].model_id,
        catalog_sha256=catalog.source_sha256,
        dims=dims,
        codes=codes,
        vectors_base64=encode_vectors(matrix),
        batch_digests=[execution.input_digest for execution in executions],
        built_at=datetime.now(UTC).isoformat(),
    )
    return CatalogIndexBuild(
        index=index,
        item_count=len(codes),
        batch_count=len(executions),
        input_tokens=sum(tokens) if tokens else None,
        estimated_cost_usd=str(sum(costs)) if costs else None,
        latency_ms=sum(execution.latency_ms for execution in executions),
    )


def index_document(index: CatalogEmbeddingIndex) -> str:
    """Serialização canônica do índice; o digest dela é o `index_sha256` do lineage."""
    return index.model_dump_json(indent=2) + "\n"


def read_catalog_index(path: Path) -> tuple[CatalogEmbeddingIndex, str]:
    """Lê o documento do índice e devolve o digest dos BYTES lidos, não do reserializado."""
    data = path.read_bytes()
    return (
        CatalogEmbeddingIndex.model_validate_json(data.decode("utf-8")),
        hashlib.sha256(data).hexdigest(),
    )


def bind_index_to_catalog(
    index: CatalogEmbeddingIndex, index_sha256: str, catalog: PriceCatalog
) -> SemanticIndex:
    """Confere o índice contra o catálogo vigente e o prepara para o kNN.

    Recusa fechada em vez de degradação silenciosa: um índice de outro catálogo devolveria
    códigos que o catálogo carregado nem tem, e o orçamentista veria sugestão de um
    contrato que não é o dele.
    """
    if index.catalog_sha256 != catalog.source_sha256:
        raise ValuationValidationError(
            "INDEX_CATALOG_MISMATCH",
            "índice de embeddings pertence a outro catálogo de preços",
            {
                "index_catalog_sha256": index.catalog_sha256,
                "catalog_sha256": catalog.source_sha256,
            },
        )
    if len(index.codes) != len(catalog.entries):
        raise ValuationValidationError(
            "INDEX_CATALOG_MISMATCH",
            "índice de embeddings tem contagem de itens diferente da do catálogo",
            {"index_codes": len(index.codes), "catalog_entries": len(catalog.entries)},
        )
    if index.text_recipe != INDEX_TEXT_RECIPE:
        raise ValuationValidationError(
            "INDEX_TEXT_RECIPE_MISMATCH",
            "índice foi construído com outro texto por item; reconstrua com `index-catalog`",
            {"index_text_recipe": index.text_recipe, "current_text_recipe": INDEX_TEXT_RECIPE},
        )
    return SemanticIndex(
        provider=index.provider,
        model_id=index.model_id,
        dims=index.dims,
        catalog_sha256=index.catalog_sha256,
        index_sha256=index_sha256,
        codes=tuple(index.codes),
        matrix=decode_vectors(index.vectors_base64, rows=len(index.codes), dims=index.dims),
    )


def load_semantic_index(path: Path, catalog: PriceCatalog) -> SemanticIndex:
    """Carrega o índice do disco já amarrado ao catálogo informado."""
    index, digest = read_catalog_index(path)
    return bind_index_to_catalog(index, digest, catalog)


def semantic_topk(
    query_vec: Sequence[float], index: SemanticIndex, k: int
) -> list[tuple[str, float]]:
    """Os `k` códigos mais próximos da consulta por cosseno, do mais próximo ao mais distante.

    Força bruta em numpy: 5 mil por 1.536 é uma multiplicação de milissegundos, e um índice
    aproximado (HNSW e afins) traria dependência, não-determinismo e um novo parâmetro de
    recall para justificar. Empate de cosseno desempata por código, para que a ordem seja
    total e reprodutível.
    """
    if k < 1:
        raise ValueError("k do kNN semântico deve ser positivo")
    vector = np.asarray(query_vec, dtype=np.float32)
    if vector.shape != (index.dims,):
        raise ValuationValidationError(
            "SEMANTIC_QUERY_DIMS_MISMATCH",
            "vetor da consulta não tem a dimensão do índice",
            {"query_dims": int(vector.size), "index_dims": index.dims},
        )
    norm = float(np.linalg.norm(vector))
    if norm > 0:
        vector = (vector / norm).astype(np.float32)
    similarities = index.matrix @ vector
    ranked = sorted(
        zip(index.codes, (float(value) for value in similarities), strict=True),
        key=lambda found: (-found[1], found[0]),
    )
    return ranked[:k]


# --------------------------------------------------------------------------------------
# Fusão de ranking
# --------------------------------------------------------------------------------------

Origin = Literal["lexical", "semantic", "both"]


@dataclass(frozen=True, slots=True)
class FusedEntry:
    """Um código depois da fusão, com a evidência de qual braço o trouxe."""

    code: str
    origin: Origin
    semantic_score: float | None
    fused_score: float
    fused_rank: int


def fuse_arms(
    lexical_codes: Sequence[str],
    semantic_scored: Sequence[tuple[str, float]],
    *,
    k: int,
    rrf_k: int = RRF_K,
) -> list[FusedEntry]:
    """Reciprocal Rank Fusion entre a lista léxica e a semântica, ambas já ordenadas.

    `score(c) = Σ 1/(rrf_k + posição de c no braço)`, somando só os braços em que o código
    aparece — a formulação clássica, sobre listas TRUNCADAS. Truncar importa: se cada braço
    ranqueasse o catálogo inteiro, um código péssimo no léxico carregaria essa penalidade
    para dentro da fusão e o braço semântico nunca conseguiria resgatá-lo, que é justamente
    o caso dos oito gaps medidos na Fase 1.

    Empate de score desempata por código: a saída é totalmente determinística dado o par de
    listas. `fused_rank` é a posição na lista devolvida, com 0 no topo — a mesma convenção
    de rank do golden set.
    """
    scores: dict[str, float] = {}
    in_lexical = set(lexical_codes)
    semantic_by_code = {code: score for code, score in semantic_scored}
    for position, code in enumerate(lexical_codes, start=1):
        scores[code] = scores.get(code, 0.0) + 1.0 / (rrf_k + position)
    for position, (code, _score) in enumerate(semantic_scored, start=1):
        scores[code] = scores.get(code, 0.0) + 1.0 / (rrf_k + position)
    ordered = sorted(scores.items(), key=lambda found: (-found[1], found[0]))[:k]
    fused: list[FusedEntry] = []
    for rank, (code, score) in enumerate(ordered):
        lexical = code in in_lexical
        semantic = code in semantic_by_code
        origin: Origin = "both" if lexical and semantic else ("lexical" if lexical else "semantic")
        fused.append(
            FusedEntry(
                code=code,
                origin=origin,
                semantic_score=round(semantic_by_code[code], 6) if semantic else None,
                fused_score=round(score, 8),
                fused_rank=rank,
            )
        )
    return fused


@dataclass(frozen=True, slots=True)
class HybridCandidate:
    """Um código candidato depois da fusão, com o score de cada braço.

    `lexical_score` aqui é a COBERTURA da consulta (`query_coverage_score`), que é o que
    ordena o braço léxico da fusão — não a `lexical_similarity` que o domínio publica em
    `CodeCandidate.lexical_score`. Os dois convivem de propósito: a cobertura ordena o
    braço, a similaridade desempata dentro dele e continua sendo o score de compatibilidade
    que o orçamentista vê no artefato.
    """

    code: str
    origin: Origin
    lexical_score: float
    semantic_score: float | None
    fused_score: float
    fused_rank: int


_IDF_CACHE: dict[str, StemIdfTable] = {}
_IDF_CACHE_MAX_ENTRIES: Final = 2
"""Tabela de IDF por catálogo, memoizada no processo.

Construí-la varre as 4.964 descrições do catálogo real (~4 s); refazê-la a cada consulta
tornaria a busca inutilizável na tela. A chave amarra catálogo E tabela de sinônimos: as
duas entram no cálculo do peso, e trocar qualquer uma muda os pesos. O teto de duas
entradas existe porque um processo serve uma rodada — mais que isso é vazamento, não
cache."""


def catalog_idf_table(
    catalog: PriceCatalog, synonyms: DomainSynonyms | None = None
) -> StemIdfTable:
    """Pesos de discriminação do vocabulário deste catálogo, construídos uma vez por processo."""
    fingerprint = (
        "sem-sinonimos"
        if synonyms is None
        else hashlib.sha256(synonyms.model_dump_json().encode("utf-8")).hexdigest()
    )
    key = f"{catalog.source_sha256}:{fingerprint}"
    cached = _IDF_CACHE.get(key)
    if cached is not None:
        return cached
    table = build_stem_idf_table(
        [entry.description for entry in catalog.entries], synonyms=synonyms
    )
    if len(_IDF_CACHE) >= _IDF_CACHE_MAX_ENTRIES:
        _IDF_CACHE.pop(next(iter(_IDF_CACHE)))
    _IDF_CACHE[key] = table
    return table


def lexical_arm(
    query: str,
    catalog: PriceCatalog,
    *,
    synonyms: DomainSynonyms | None = None,
    noise: LegendNoiseList | None = None,
    depth: int,
    idf: StemIdfTable | None = None,
) -> list[tuple[str, float]]:
    """Braço léxico da fusão: códigos por cobertura PONDERADA, com similaridade desempatando.

    A ponderação por IDF (`weighted_query_coverage_score`) é o que impede a palavra comum
    de valer o mesmo que a rara: sem ela, cobrir "piso" empata com cobrir "intertravado" e
    o alvo de "PISO INTERTRAVADO" fica no rank 127 do braço; com ela, no rank 3. A
    contrapartida medida está na docstring da função do domínio. `noise` amortece (nunca
    remove) o peso das palavras de ESTADO da legenda ("existente", "a ser recuperar") na
    mesma função — ver `LEGEND_NOISE_DAMP_FACTOR`.

    Só entram itens com cobertura maior que zero — ou seja, que compartilham ao menos um
    radical (ou sinônimo dele) com a consulta. É um piso natural, mais informativo que o
    piso de ruído de `SuggestionConfig.min_lexical_score`, e evita calcular
    `lexical_similarity` (que é o custo real, por causa do `SequenceMatcher`) sobre o
    catálogo inteiro.
    """
    weights = idf if idf is not None else catalog_idf_table(catalog, synonyms)
    scored: list[tuple[float, float, str]] = []
    for entry in catalog.entries:
        coverage = weighted_query_coverage_score(
            query, entry.description, idf=weights, synonyms=synonyms, noise=noise
        )
        if coverage <= 0:
            continue
        similarity = lexical_similarity(query, entry.description, synonyms=synonyms)
        scored.append((coverage, similarity, entry.code))
    scored.sort(key=lambda found: (-found[0], -found[1], found[2]))
    return [(code, coverage) for coverage, _similarity, code in scored[:depth]]


def hybrid_candidates(
    query: str,
    catalog: PriceCatalog,
    *,
    index: SemanticIndex | None = None,
    query_vec: Sequence[float] | None = None,
    synonyms: DomainSynonyms | None = None,
    noise: LegendNoiseList | None = None,
    k: int = HYBRID_DEFAULT_K,
    arm_depth: int | None = None,
) -> list[HybridCandidate]:
    """Fusão dos dois braços para uma consulta; determinística dado o índice.

    Sem índice ou sem vetor da consulta, o braço semântico simplesmente não existe e a
    saída é o braço léxico por cobertura — que já é melhor do que a ordem por Dice puro,
    e é o que o produto serve quando não há teto de gasto ou credencial.

    `arm_depth` é a profundidade de CADA braço antes da fusão; o padrão é
    `HYBRID_ARM_DEPTH`, nunca menor que `k`. Ele é separado de `k` porque são coisas
    diferentes: `k` é quanto se publica, `arm_depth` é quanto cada braço tem direito de
    propor — e a curva medida que fixa o padrão está na docstring da constante.
    """
    if k < 1:
        raise ValueError("k da fusão híbrida deve ser positivo")
    depth = arm_depth if arm_depth is not None else max(k, HYBRID_ARM_DEPTH)
    weights = catalog_idf_table(catalog, synonyms)
    lexical = lexical_arm(query, catalog, synonyms=synonyms, noise=noise, depth=depth, idf=weights)
    coverage_by_code = dict(lexical)
    semantic: list[tuple[str, float]] = []
    if index is not None and query_vec is not None:
        semantic = semantic_topk(query_vec, index, depth)
    fused = fuse_arms([code for code, _coverage in lexical], semantic, k=k)
    # Candidato que veio só do braço semântico não tem cobertura calculada ainda, e devolver
    # 0.0 seria mentira: ele pode ter cobertura real e ter ficado fora da profundidade do
    # braço léxico. São no máximo `k` descrições, então medir aqui não muda o custo.
    entries_by_code = {entry.code: entry for entry in catalog.entries}
    for entry in fused:
        if entry.code not in coverage_by_code and entry.code in entries_by_code:
            coverage_by_code[entry.code] = weighted_query_coverage_score(
                query,
                entries_by_code[entry.code].description,
                idf=weights,
                synonyms=synonyms,
                noise=noise,
            )
    return [
        HybridCandidate(
            code=entry.code,
            origin=entry.origin,
            lexical_score=coverage_by_code.get(entry.code, 0.0),
            semantic_score=entry.semantic_score,
            fused_score=entry.fused_score,
            fused_rank=entry.fused_rank,
        )
        for entry in fused
    ]


# --------------------------------------------------------------------------------------
# Cache de vetores de consulta
# --------------------------------------------------------------------------------------


class QueryEmbeddingCache(BaseModel):
    """Vetores de consulta já pagos nesta rodada, indexados pelo texto normalizado.

    Lista de floats e não base64 aqui de propósito: são dezenas de rótulos, não milhares de
    itens, e um cache legível é conferível a olho na homologação.
    """

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["query-embeddings-v1"] = QUERY_CACHE_SCHEMA_VERSION
    model_id: str = Field(min_length=1, max_length=160)
    dims: int = Field(ge=1, le=8192)
    vectors: dict[str, list[float]] = Field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class QueryVectors:
    """Vetores resolvidos para um conjunto de consultas, e o que a resolução custou."""

    by_query: dict[str, tuple[float, ...]]
    execution: EmbeddingsExecution | None
    embedded_count: int


def load_query_cache(path: Path, index: SemanticIndex) -> QueryEmbeddingCache:
    """Cache da rodada, conferido contra o modelo do índice.

    Cache de outro modelo recusa em vez de ser apagado ou reaproveitado: vetores de dois
    modelos não vivem no mesmo espaço, e misturá-los daria vizinhança sem sentido. Quem
    resolve é o operador, apagando o arquivo — não o código, decidindo por ele.
    """
    if not path.is_file():
        return QueryEmbeddingCache(model_id=index.model_id, dims=index.dims)
    cache = QueryEmbeddingCache.model_validate_json(path.read_text(encoding="utf-8"))
    if cache.model_id != index.model_id or cache.dims != index.dims:
        raise ValuationValidationError(
            "QUERY_CACHE_MODEL_MISMATCH",
            "cache de consultas foi gravado por outro modelo de embedding",
            {
                "cache_model_id": cache.model_id,
                "index_model_id": index.model_id,
                "cache_dims": cache.dims,
                "index_dims": index.dims,
            },
        )
    return cache


def resolve_query_vectors(
    queries: Sequence[str],
    *,
    index: SemanticIndex,
    cache_path: Path,
    adapter: EmbeddingsAdapter | None,
) -> QueryVectors:
    """Vetores das consultas pedidas, reusando o cache e pagando só pelo que falta.

    Uma consulta nova é uma chamada paga pequena; consulta repetida não custa nada. Sem
    adapter (o modo do golden e de qualquer rodada sem teto de gasto), consulta ausente do
    cache recusa com `SEMANTIC_QUERY_NOT_CACHED` — nunca é embutida às escondidas.

    O cache só é regravado quando algo novo entrou, e sempre por escrita atômica: uma
    interrupção no meio não deixa cache pela metade.
    """
    cache = load_query_cache(cache_path, index)
    wanted = list(dict.fromkeys(normalize_query_text(query) for query in queries))
    missing = [key for key in wanted if key not in cache.vectors]
    execution: EmbeddingsExecution | None = None
    if missing:
        if adapter is None:
            raise ValuationValidationError(
                "SEMANTIC_QUERY_NOT_CACHED",
                "consulta sem vetor no cache e nenhuma via de embeddings disponível",
                {"queries": missing[:10], "missing": len(missing)},
            )
        execution = adapter.embed(missing)
        if execution.dims != index.dims:
            raise ValuationValidationError(
                "SEMANTIC_QUERY_DIMS_MISMATCH",
                "vetor de consulta não tem a dimensão do índice",
                {"query_dims": execution.dims, "index_dims": index.dims},
            )
        updated = dict(cache.vectors)
        for key, vector in zip(missing, execution.vectors, strict=True):
            updated[key] = list(vector)
        cache = cache.model_copy(update={"vectors": updated})
        atomic_write_text(cache_path, cache.model_dump_json(indent=2) + "\n")
    return QueryVectors(
        by_query={key: tuple(cache.vectors[key]) for key in wanted},
        execution=execution,
        embedded_count=len(missing),
    )


# --------------------------------------------------------------------------------------
# Shortlist híbrida de código
# --------------------------------------------------------------------------------------

_SHARED_SAFETY_NOTES: Final = (
    "Compatibilidade de unidade e presença no contrato não substituem a decisão do orçamentista.",
    "Item sem candidato exige busca manual no catálogo antes da confirmação.",
)

_HYBRID_SAFETY_NOTES: Final = (
    "Shortlist híbrida é observação determinística; nenhum código foi confirmado.",
    *_SHARED_SAFETY_NOTES,
    "A ordem vem da fusão entre cobertura léxica e vizinhança semântica; ela não mede preço.",
)

_LEXICAL_IDF_SAFETY_NOTES: Final = (
    "Shortlist léxica é observação determinística; nenhum código foi confirmado.",
    *_SHARED_SAFETY_NOTES,
    "A ordem vem da cobertura léxica ponderada por IDF, sem braço semântico; ela não mede preço.",
)


def build_hybrid_code_suggestions(
    packet: TakeoffPacket,
    catalog: PriceCatalog,
    contract: ContractWorkbook | None,
    *,
    index: SemanticIndex | None = None,
    query_vectors: Mapping[str, tuple[float, ...]] | None = None,
    config: SuggestionConfig | None = None,
    synonyms: DomainSynonyms | None = None,
    noise: LegendNoiseList | None = None,
) -> CodeSuggestionSet:
    """Shortlist de código montada por `hybrid_candidates`, no mesmo contrato de `suggest_codes`.

    Duas diferenças declaradas em relação à via Dice (`suggest_codes`), e só elas:

    1. **Quem entra** é decidido pela fusão, não pelo piso de ruído lexical. É essa a
       entrega do M7 Fase 2: um código que a via Dice deixava no rank 346 entra pelo
       braço semântico. `min_lexical_score` continua existindo, mas é conceito daquela via
       e não filtra nada aqui.
    2. **A ordem** usa a posição fundida no lugar do score lexical, mantendo intacta a
       dominância que o domínio já pratica: unidade compatível manda, depois presença no
       contrato, e só então a relevância.

    Tudo o mais é idêntico: `lexical_score` de cada candidato continua sendo
    `lexical_similarity` (o mesmo número de sempre, com o mesmo significado), nenhum item
    recebe código, e item sem candidato sai em `unmatched_item_ids`.

    **Sem índice** (`index=None`) a função é o caminho da DEGRADAÇÃO, não um erro: a fusão
    roda com um braço só, o léxico por cobertura ponderada, e o conjunto sai declarado como
    `SCO_LEXICAL_IDF_SUGGESTER_VERSION`, sem bloco `semantic` — nenhum embedding
    participou. É por isso que a assinatura aceita ausência de índice em vez de exigir um:
    até 2026-08-21 o produto desviava a degradação para a via Dice, que é medidamente pior
    (3/8 contra 8/8 em k=5 no catálogo real), enquanto `hybrid_candidates(index=None)` —
    que já degradava sozinho — ficava sem chamador. `--no-semantic` passa a significar
    "esta via sem a perna semântica", não "outro algoritmo".

    **Com índice**, item cuja consulta não tem vetor recusa a rodada inteira em vez de
    virar item lexical escondido dentro de um conjunto que se declara híbrido.
    """
    effective_config = config or SuggestionConfig()
    if effective_config.max_candidates_per_item < 1:
        raise ValuationValidationError(
            "SUGGESTION_CONFIG_INVALID",
            "configuração de sugestão de código inválida",
            {"max_candidates_per_item": effective_config.max_candidates_per_item},
        )
    confirmed_items = packet.confirmed_items()
    if not confirmed_items:
        raise ValuationValidationError(
            "SUGGESTION_NO_CONFIRMED_ITEMS",
            "pacote de takeoff não possui item confirmado; revise o takeoff antes de sugerir",
            {"plate_id": packet.plate_id},
        )
    entries_by_code = {entry.code: entry for entry in catalog.entries}
    contract_codes = {line.code for line in contract.lines} if contract is not None else frozenset()

    vectors = query_vectors or {}

    suggestions: list[CodeSuggestion] = []
    unmatched_item_ids: list[str] = []
    for item in confirmed_items:
        vector: tuple[float, ...] | None = None
        if index is not None:
            key = normalize_query_text(item.label)
            vector = vectors.get(key)
            if vector is None:
                raise ValuationValidationError(
                    "SEMANTIC_QUERY_NOT_CACHED",
                    "item de takeoff sem vetor de consulta na shortlist híbrida",
                    {"item_id": item.id, "query": key},
                )
        fused = hybrid_candidates(
            item.label,
            catalog,
            index=index,
            query_vec=vector,
            synonyms=synonyms,
            noise=noise,
            k=effective_config.max_candidates_per_item,
        )
        candidates: list[tuple[bool, bool, int, CodeCandidate]] = []
        for candidate in fused:
            entry = entries_by_code.get(candidate.code)
            if entry is None:  # pragma: no cover - índice amarrado ao catálogo por digest
                continue
            unit_compatible = normalize_unit(item.unit) == normalize_unit(entry.unit)
            in_contract = entry.code in contract_codes
            candidates.append(
                (
                    not unit_compatible,
                    not in_contract,
                    candidate.fused_rank,
                    CodeCandidate(
                        code=entry.code,
                        description=entry.description,
                        unit=entry.unit,
                        unit_price=entry.unit_price,
                        unit_compatible=unit_compatible,
                        in_contract=in_contract,
                        lexical_score=lexical_similarity(
                            item.label, entry.description, synonyms=synonyms
                        ),
                        # Mesma proveniência que `suggest_codes` carimba: com um catálogo
                        # só, o digest continua no cabeçalho e a origem é a dele. Sem isto,
                        # um catálogo não-SCO servido por esta via recusaria o próprio
                        # candidato em `validate_code_for_origin`.
                        catalog_origin=catalog.origin,
                    ),
                )
            )
        if not candidates:
            unmatched_item_ids.append(item.id)
            continue
        candidates.sort(key=lambda found: (found[0], found[1], found[2]))
        suggestions.append(
            CodeSuggestion(item_id=item.id, candidates=[entry for *_keys, entry in candidates])
        )

    return CodeSuggestionSet(
        plate_id=packet.plate_id,
        page_number=packet.page_number,
        image_sha256=packet.image_sha256,
        catalog_sha256=catalog.source_sha256,
        contract_sha256=contract.source_sha256 if contract else None,
        suggester_version=(
            SCO_HYBRID_SUGGESTER_VERSION if index is not None else SCO_LEXICAL_IDF_SUGGESTER_VERSION
        ),
        semantic=(
            None
            if index is None
            else SuggestionSemantics(
                provider=index.provider,
                model_id=index.model_id,
                dims=index.dims,
                index_sha256=index.index_sha256,
            )
        ),
        suggestions=suggestions,
        unmatched_item_ids=unmatched_item_ids,
        safety_notes=list(_HYBRID_SAFETY_NOTES if index is not None else _LEXICAL_IDF_SAFETY_NOTES),
    )
