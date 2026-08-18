"""Busca no catálogo de preços: braço léxico determinístico, braço semântico opcional.

O que mora aqui é a consulta em si — normalização, casamento por palavra, ranking e fusão
com o kNN semântico —, sem saber de onde vieram o catálogo e o vetor da consulta. Quem lê
o catálogo do diretório da rodada, resolve o vetor no cache e decide a situação do braço
semântico é o adaptador (o servidor de homologação hoje, a API `/v1` depois): este módulo
recebe tudo pronto e devolve o payload da resposta.

`SemanticArm` é a situação do braço semântico resolvida pelo adaptador e passada adiante.
Ela vive aqui, e não no servidor, porque é vocabulário da BUSCA: o mesmo objeto alimenta a
shortlist de códigos (`suggestions.py`) e a resposta desta busca.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final, Literal

from croquito_valuation.catalog import (
    DomainSynonyms,
    LegendNoiseList,
    expand_terms,
    lexical_similarity,
    lexical_stems,
    lexical_tokens,
    weighted_query_coverage_score,
)
from croquito_valuation.errors import ValuationValidationError
from croquito_valuation.models import PriceCatalog, PriceCatalogEntry
from croquito_worker.providers import EmbeddingsAdapter
from croquito_worker.valuation.sco_matching import (
    SemanticIndex,
    catalog_idf_table,
    fuse_arms,
    semantic_topk,
)

CATALOG_SEARCH_DEFAULT_LIMIT: Final = 20
CATALOG_SEARCH_MAX_LIMIT: Final = 50

CATALOG_SEARCH_MIN_PREFIX: Final = 4
"""Comprimento mínimo do lado que serve de prefixo no casamento da busca.

Abaixo disso, prefixo vira coincidência: `pis` traria `piscina` para quem procura piso.
Igualdade de palavra continua valendo em qualquer comprimento."""

SEMANTIC_AVAILABLE_MESSAGE: Final = "busca semântica disponível"
SEMANTIC_LIMITED_MESSAGE: Final = "busca semântica limitada às consultas já embutidas"
SEMANTIC_UNAVAILABLE_MESSAGE: Final = "busca semântica indisponível"
"""Prefixos das três situações do braço semântico, sempre com o motivo colado.

Nenhuma delas é erro: a tela continua funcionando com o braço léxico. O que não pode
acontecer é a busca piorar sem ninguém saber por quê — daí o motivo viajar no `/state`, na
resposta da busca e no banner do `serve`."""

SemanticStatus = Literal["available", "limited", "unavailable"]


@dataclass(frozen=True, slots=True)
class SemanticArm:
    """Situação do braço semântico da rodada, resolvida a cada requisição.

    `index` presente e `adapter` ausente é o estado `limited`: consulta já embutida no
    cache continua respondendo pelo híbrido, consulta nova cai no léxico com aviso. É o
    estado de um servidor sem teto de gasto rodando sobre uma rodada que já foi indexada —
    útil de verdade, e por isso não é tratado como indisponível.
    """

    index: SemanticIndex | None
    adapter: EmbeddingsAdapter | None
    status: SemanticStatus
    message: str

    def payload(self) -> dict[str, object]:
        return {
            "status": self.status,
            "message": self.message,
            "index_present": self.index is not None,
            "model_id": None if self.index is None else self.index.model_id,
        }


def term_matches_description(term: str, tokens: frozenset[str]) -> bool:
    """Um termo da busca casa com a descrição por PALAVRA, nunca por pedaço de palavra.

    Igualdade sempre vale. Prefixo vale nos dois sentidos — "grama" acha "gramado" e
    "gramado" acha "grama" — a partir de `CATALOG_SEARCH_MIN_PREFIX` caracteres do lado
    que serve de prefixo, que é o que separa flexão de palavra de coincidência de letras.

    O piso existe por causa do defeito real da homologação: "gramado" trazia
    "**pro**gramado**r** de computador", porque a busca casava substring sem fronteira de
    palavra. Substring deixou de ser critério — "gramado" não é token de "programador",
    e nenhum dos dois é prefixo do outro.
    """
    if term in tokens:
        return True
    if len(term) < CATALOG_SEARCH_MIN_PREFIX:
        return False
    return any(
        token.startswith(term)
        or (len(token) >= CATALOG_SEARCH_MIN_PREFIX and term.startswith(token))
        for token in tokens
    )


def require_query_terms(query: str) -> tuple[str, ...]:
    """Palavras utilizáveis da busca; consulta sem nenhuma recusa ANTES de qualquer gasto.

    A ordem importa: a rota valida a consulta antes de pedir vetor, senão um `-` digitado
    por engano viraria chamada paga só para ser recusado logo depois.
    """
    terms = lexical_tokens(query)
    if not terms:
        raise ValuationValidationError(
            "LOCAL_SEARCH_QUERY_EMPTY",
            "busca exige ao menos uma palavra com dois caracteres ou mais",
            {"query": query},
        )
    return terms


def result_payload(
    entry: PriceCatalogEntry,
    *,
    origin: str,
    coverage: float,
    semantic_score: float | None,
) -> dict[str, object]:
    """Um resultado da busca com a evidência de por que ele está ali.

    A descrição volta **inteira**: é ela que diz se o código é de execução ou de mero
    fornecimento, e cortá-la esconderia justamente a diferença que o orçamentista precisa
    ver.
    """
    return {
        "code": entry.code,
        "unit": entry.unit,
        "unit_price": str(entry.unit_price),
        "description": entry.description,
        "origin": origin,
        "lexical_score": coverage,
        "semantic_score": semantic_score,
    }


def search_catalog(
    catalog: PriceCatalog,
    query: str,
    limit: int,
    synonyms: DomainSynonyms | None = None,
    *,
    noise: LegendNoiseList | None = None,
    semantic: SemanticArm | None = None,
    query_vec: Sequence[float] | None = None,
    semantic_warning: str | None = None,
) -> dict[str, object]:
    """Busca determinística por palavra-chave sobre o catálogo, ordenada por relevância.

    Normalização é a mesma da sugestão lexical (`lexical_tokens`: NFKD sem acento,
    `casefold`, tokens de dois caracteres ou mais), então a tela e o ranking enxergam o
    texto do mesmo jeito. Um item casa quando **todas** as palavras da busca casam com
    palavras da descrição (`term_matches_description`) — ou quando o código começa por
    uma delas, que é como se procura `AD0405` direto. Com `synonyms`, cada palavra da busca
    ganha um GRUPO de equivalentes (`expand_terms`): o casamento por palavra passa a valer
    se QUALQUER termo do grupo casar, então uma busca por "refletor" também encontra
    catálogo escrito só com "projetor" — mas continua exigindo uma correspondência por
    palavra ORIGINAL da busca (nenhum termo expandido relaxa a exigência das demais).

    A ordem do braço léxico é por COBERTURA PONDERADA da consulta
    (`weighted_query_coverage_score`, o mesmo scorer do braço léxico da shortlist), com
    `lexical_similarity` desempatando e o código fechando o desempate. A cobertura entrou
    no lugar do Dice puro por causa do achado medido na Fase 1 do M7: o Dice pune a
    descrição longa, e no catálogo real isso empurrava o código certo para o rank 346
    porque a descrição dele é um parágrafo. O peso por IDF veio depois, na 2.1, porque
    cobrir a palavra comum não pode valer o mesmo que cobrir a rara. Devolver na ordem do
    catálogo, como antes de tudo isso, escondia o item certo atrás de homônimos: a página é
    cortada em `limit` **depois** do ranking. `total_matches` continua contando o conjunto
    casado por palavra. Com `noise` (rodada 2.2), o peso de um radical de ESTADO da legenda
    ("existente", "a ser recuperar") é amortecido na cobertura ponderada — não muda quem
    entra na página, mas limpa a COMPOSIÇÃO dela: "REFLETOR EXISTENTE" caiu de 10/20 para
    0/20 itens cujo único mérito era conter "existente" (ver
    `tests/valuation/golden/matcher-golden-v1.json`, `note_phase_2_2`).

    Com `query_vec` (a rodada tem índice, teto de gasto e credencial), a lista casada por
    palavra vira UM braço e o kNN semântico vira o outro, fundidos por RRF: a resposta sai
    com `matching: "hybrid"`, cada resultado declara de qual braço veio (`origin`) e um
    código que nenhuma palavra da busca casa pode aparecer, que é o ponto do braço
    semântico. Sem vetor, `matching: "lexical"` e o motivo vai em `semantic_notes` — a
    busca nunca quebra por causa do braço pago.

    `expanded_terms` só aparece na resposta quando a expansão acrescentou algum termo — é
    o que deixa visível, por exemplo, que "refletor" virou também "projetor".
    """
    terms = require_query_terms(query)
    # `expand_terms` casa GRUPOS de sinônimo por radical (`lexical_stems`), não pela grafia
    # crua — "alambrado" só bate o grupo porque o radical dele é "alambra". Por isso a
    # expansão é feita PALAVRA A PALAVRA (nunca com a frase inteira de uma vez): assim a
    # origem de cada termo expandido fica sem ambiguidade — é sempre a palavra da busca que
    # acabou de ser expandida, nunca uma mistura das várias palavras digitadas.
    term_groups: dict[str, tuple[str, ...]] = {}
    combined_origins: dict[str, set[str]] = {}
    for term in terms:
        term_stem = lexical_stems(term)
        term_expansion = expand_terms(term_stem, synonyms)
        extras = [candidate for candidate in term_expansion.terms if candidate not in term_stem]
        term_groups[term] = (term, *extras)
        for extra_term, sources in term_expansion.origins.items():
            combined_origins.setdefault(extra_term, set()).update(sources)

    matches: list[tuple[float, float, str]] = []
    coverage_by_code: dict[str, float] = {}
    entries_by_code = {entry.code: entry for entry in catalog.entries}
    idf = catalog_idf_table(catalog, synonyms)
    for entry in catalog.entries:
        tokens = frozenset(lexical_tokens(entry.description))
        code = "".join(lexical_tokens(entry.code))
        by_description = all(
            any(term_matches_description(candidate, tokens) for candidate in term_groups[term])
            for term in terms
        )
        by_code = any(code.startswith(term) for term in terms)
        if not (by_description or by_code):
            continue
        coverage = weighted_query_coverage_score(
            query, entry.description, idf=idf, synonyms=synonyms, noise=noise
        )
        coverage_by_code[entry.code] = coverage
        matches.append(
            (
                coverage,
                lexical_similarity(query, entry.description, synonyms=synonyms),
                entry.code,
            )
        )
    matches.sort(key=lambda found: (-found[0], -found[1], found[2]))
    lexical_codes = [code for _coverage, _similarity, code in matches[:limit]]

    notes = [] if semantic_warning is None else [semantic_warning]
    results: list[dict[str, object]]
    semantic_scored: list[tuple[str, float]] = []
    if semantic is not None and semantic.index is not None and query_vec is not None:
        semantic_scored = semantic_topk(query_vec, semantic.index, limit)
        matching = "hybrid"
        results = []
        for fused in fuse_arms(lexical_codes, semantic_scored, k=limit):
            found = entries_by_code.get(fused.code)
            if found is None:  # pragma: no cover - índice amarrado ao catálogo por digest
                continue
            # O resultado que veio só do braço semântico não passou pelo filtro por palavra,
            # então a cobertura dele ainda não foi medida; devolver 0.0 sem medir seria dizer
            # que ele não tem nenhuma palavra da busca, o que nem sempre é verdade.
            if fused.code not in coverage_by_code:
                coverage_by_code[fused.code] = weighted_query_coverage_score(
                    query, found.description, idf=idf, synonyms=synonyms, noise=noise
                )
            results.append(
                result_payload(
                    found,
                    origin=fused.origin,
                    coverage=coverage_by_code[fused.code],
                    semantic_score=fused.semantic_score,
                )
            )
    else:
        matching = "lexical"
        results = [
            result_payload(
                entries_by_code[code],
                origin="lexical",
                coverage=coverage_by_code.get(code, 0.0),
                semantic_score=None,
            )
            for code in lexical_codes
        ]

    result: dict[str, object] = {
        "query": query,
        "terms": list(terms),
        "limit": limit,
        "matching": matching,
        "total_matches": len(matches),
        "semantic_matches": len(semantic_scored),
        "semantic_notes": notes,
        "results": results,
    }
    if combined_origins:
        result["expanded_terms"] = {
            term: sorted(sources) for term, sources in combined_origins.items()
        }
    return result
