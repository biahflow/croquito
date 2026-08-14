"""Índice de embeddings FABRICADO, determinístico e offline — para teste e eval, só.

Espelho de `legend_fixtures` para o braço semântico: ele existe para que a fusão, o
contrato do índice e a degradação sejam exercitados no CI sem rede, sem credencial e sem
custo. O que ele **não** faz é medir qualidade semântica: os vetores não vêm de modelo
nenhum, vêm de um saco de radicais projetado por hash.

Consequência a declarar em todo relatório que usar este índice: dois textos que
compartilham radicais ficam próximos, e dois textos que dizem a mesma coisa com palavras
diferentes ficam distantes — exatamente o que um embedding real resolveria. Portanto uma
métrica alta aqui prova que a fusão funciona, nunca que a busca semântica é boa. A medida
real é o golden contra o catálogo do cliente, com o índice pago
(`tests/valuation/test_matcher_golden.py`).
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from typing import Final

import numpy as np
import numpy.typing as npt

from croquitodxf_valuation.catalog import lexical_stems
from croquitodxf_valuation.models import PriceCatalog
from croquitodxf_worker.valuation.sco_matching import (
    CatalogEmbeddingIndex,
    SemanticIndex,
    bind_index_to_catalog,
    catalog_index_text,
    encode_vectors,
    index_document,
    normalize_rows,
)

FIXTURE_EMBEDDINGS_MODEL: Final = "fixture-hashed-stems-v1"
"""Nome que declara a natureza fabricada do vetor em todo artefato que o carrega."""

FIXTURE_EMBEDDINGS_PROVIDER: Final = "fixture"
FIXTURE_EMBEDDINGS_DIMS: Final = 64
"""Pequeno de propósito: cabe no golden de teste e o kNN roda em microssegundos."""


def fixture_vector(text: str, *, dims: int = FIXTURE_EMBEDDINGS_DIMS) -> tuple[float, ...]:
    """Saco de radicais projetado por hash estável (o "hashing trick"), sem rede.

    Cada radical do texto recebe uma posição e um sinal derivados do sha256 dele — estável
    entre processos e máquinas, ao contrário do `hash()` do Python. O vetor resultante é
    normalizado, então o produto interno entre dois textos é aproximadamente a fração de
    radicais em comum: uma "semântica" puramente lexical, suficiente para exercitar a
    fusão e nada além disso.
    """
    vector = np.zeros(dims, dtype=np.float32)
    for stem in lexical_stems(text):
        digest = hashlib.sha256(stem.encode("utf-8")).digest()
        position = int.from_bytes(digest[:4], "big") % dims
        sign = 1.0 if digest[4] % 2 == 0 else -1.0
        vector[position] += np.float32(sign)
    norm = float(np.linalg.norm(vector))
    if norm > 0:
        vector = (vector / norm).astype(np.float32)
    return tuple(float(value) for value in vector)


def fixture_catalog_index(
    catalog: PriceCatalog, *, dims: int = FIXTURE_EMBEDDINGS_DIMS
) -> CatalogEmbeddingIndex:
    """Documento de índice para um catálogo, no MESMO contrato do índice pago."""
    rows: npt.NDArray[np.float32] = np.asarray(
        [fixture_vector(catalog_index_text(entry), dims=dims) for entry in catalog.entries],
        dtype=np.float32,
    )
    return CatalogEmbeddingIndex(
        provider=FIXTURE_EMBEDDINGS_PROVIDER,
        model_id=FIXTURE_EMBEDDINGS_MODEL,
        catalog_sha256=catalog.source_sha256,
        dims=dims,
        codes=[entry.code for entry in catalog.entries],
        vectors_base64=encode_vectors(normalize_rows(rows)),
        batch_digests=[hashlib.sha256(b"fixture-index").hexdigest()],
        built_at=datetime(2026, 1, 1, tzinfo=UTC).isoformat(),
    )


def fixture_semantic_index(
    catalog: PriceCatalog, *, dims: int = FIXTURE_EMBEDDINGS_DIMS
) -> SemanticIndex:
    """Índice fixture já carregado e amarrado ao catálogo, pronto para a fusão."""
    document = fixture_catalog_index(catalog, dims=dims)
    digest = hashlib.sha256(index_document(document).encode("utf-8")).hexdigest()
    return bind_index_to_catalog(document, digest, catalog)
