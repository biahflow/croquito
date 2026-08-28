"""Índice de embeddings publicado pela plataforma: o irmão do acervo de catálogos.

Camada de aplicação sem FastAPI, como `reference_catalogs.py`: nada aqui recebe `Request`,
monta `Response` nem conhece código de status. O que mora aqui é o pouco que precisa de UMA
fonte — o prefixo do objeto, a função que monta a chave, o teto de leitura, a busca da
publicação vigente e o cache de leitura do processo.

O desenho é o do ADR-0054, e ele espelha de perto o do ADR-0047 porque a pergunta é a
mesma: onde mora um objeto público, sem dono, endereçado por digest. Três propriedades
atravessam o módulo:

- **O objeto fica FORA de `tenants/`** (D1), pelo mesmo motivo do catálogo: índice de
  catálogo público não tem dono. A consequência prática também é a mesma — as guardas de
  prefixo do repositório (`signed_artifact_url`, `_preview_urls`, `_export_response`)
  recusam uma chave daqui por construção, e recusar é o comportamento CORRETO: o índice é
  lido pelo servidor, nunca baixado pelo cliente.
- **O índice é encontrado por DIGEST, não por proveniência** (D3): a busca é por
  `catalog_source_sha256` + `text_recipe` + `AVAILABLE`. É a mesma chave que
  `bind_index_to_catalog` já confere fechado, e é por isso que o resolvedor não a
  reimplementa.
- **O servidor LÊ o índice; nunca o constrói** (D4). A construção continua no comando pago
  `index-catalog` do CLI, onde um humano aperta o botão. Aqui só entra desserialização
  validada por Pydantic, com o teto aplicado ANTES dela.
"""

from __future__ import annotations

import hashlib
import re
import threading
from collections import OrderedDict
from typing import Final, Protocol

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from croquito_api.database import ReferenceCatalogEmbeddingRecord

# Reexport explícito dos estados de circulação, e não um par novo de literais: retirar um
# índice e retirar um catálogo são o MESMO fato — a publicação deixa de ser oferecida e
# continua existindo, porque quem já a citou continua podendo relê-la. Duas cópias dos
# literais seriam dois vocabulários livres para divergir num `AVAILABLE` escrito diferente.
from croquito_api.reference_catalogs import STATUS_AVAILABLE as STATUS_AVAILABLE
from croquito_api.reference_catalogs import STATUS_WITHDRAWN as STATUS_WITHDRAWN
from croquito_valuation.errors import ValuationValidationError, valuation_errors
from croquito_valuation.models import PriceCatalog
from croquito_worker.valuation.sco_matching import (
    INDEX_TEXT_RECIPE,
    CatalogEmbeddingIndex,
    SemanticIndex,
    bind_index_to_catalog,
)

#: Prefixo do índice no object store. O primeiro segmento NÃO é `tenants/` de propósito,
#: pelo mesmo motivo do acervo: é o que mantém o objeto público fora de todo caminho que
#: assina URL por prefixo de tenant, sem que nenhuma daquelas guardas precise ser afrouxada.
REFERENCE_CATALOG_INDEX_PREFIX: Final = "platform/reference-catalog-indexes/"

CATALOG_INDEX_MAX_BYTES: Final = 64 * 1024 * 1024
"""Teto de leitura do índice de embeddings publicado — constante PRÓPRIA, deliberadamente.

Não é `CATALOG_MAX_BYTES` afrouxado (`valuation_rounds.py`, 32 MiB): são artefatos
diferentes, com tamanhos e riscos diferentes. O catálogo real do SCO tem 2,4 MB de JSON; o
índice do MESMO catálogo, construído em 2026-08-25, tem **40,7 MB** — 4.964 itens x 1.536
dimensões em float32 base64 (ADR-0054, consequências). O número não é precaução: com o teto
do catálogo, o índice real simplesmente **não passa**.

64 MiB é o dobro do teto do catálogo e ~57% de folga sobre a medição: cabe um catálogo
bem maior que o SCO inteiro sem que o teto vire o portão de recusa, e continua distante do
que faria um objeto arbitrário caber na memória do processo. Afrouxar isto não é ajuste de
constante: é rever quanto de plataforma cabe num processo da API, e o lugar disso é o ADR.
"""

CATALOG_INDEX_CACHE_MAX_ENTRIES: Final = 2
"""Quantos índices decodificados o processo guarda ao mesmo tempo.

O número é escolhido pelo TAMANHO, não por simetria com o `CatalogCache` (4 entradas): um
catálogo decodificado tem alguns MB, um índice tem ~40 MB, e copiar aquele número aqui
custaria ~160 MB de matriz por processo, multiplicados por worker — mais do que a API
inteira usa hoje para servir tudo o mais.

Duas entradas, e não uma, porque a unidade de leitura é a FONTE, não a rodada: o braço
semântico roda por fonte da cascata (ADR-0054 D5) e nesta fase só as fontes da plataforma
têm índice (SCO/SINAPI/SICRO; catálogo de upload do cliente segue sem — aceite humano item
4). Uma entrada só faria uma cascata de duas fontes de plataforma expulsar e reler ~40 MB a
cada alternância, que é justamente o custo que o cache existe para não pagar. ~80 MB é o
teto que este processo aceita; crescer daqui exige medir a memória do serviço, não editar
o número.
"""

_OBJECT_SHA256_PATTERN: Final = re.compile(r"^[a-f0-9]{64}$")

INDEX_OBJECT_UNREADABLE: Final = "INDEX_OBJECT_UNREADABLE"
"""Código de domínio da leitura que não produziu o documento publicado.

Objeto ausente, maior que o teto ou com digest divergente do registrado: os três dizem que
o AMBIENTE não devolveu o que a publicação validou, e não que a publicação estava errada.
Fica ao lado dos códigos de `sco_matching` (`INDEX_CATALOG_MISMATCH`,
`INDEX_TEXT_RECIPE_MISMATCH`, `INDEX_PAYLOAD_INVALID`) porque quem lê a nota de degradação
lê os quatro na mesma lista.
"""


def reference_catalog_index_key(*, object_sha256: str) -> str:
    """Chave do `catalog-embeddings.json` publicado, endereçada pelo digest dos BYTES.

    Mesma forma e mesma razão de `reference_catalog_key`: uma função dedicada, e não
    interpolação espalhada, porque as chaves fora de `tenants/` são a exceção do projeto e
    precisam estar num lugar só.

    O digest é conferido contra a forma hexadecimal minúscula antes de virar caminho: ele
    vem do registro do upload já validado, mas montar caminho a partir de texto que ninguém
    olhou é como um `..` entra numa chave de object store.
    """
    if _OBJECT_SHA256_PATTERN.fullmatch(object_sha256) is None:
        raise ValueError("o digest do índice publicado precisa ser sha256 hexadecimal")
    return f"{REFERENCE_CATALOG_INDEX_PREFIX}{object_sha256}.json"


class CatalogIndexStore(Protocol):
    """A fatia do object store que a leitura do índice usa; o vendor não entra aqui."""

    def read_object(self, *, object_key: str, max_bytes: int) -> bytes | None: ...


class SemanticIndexCache:
    """Índices decodificados por (digest do índice, digest do catálogo), no processo.

    Existe por custo medido, como o `_IndexCache` do servidor de medição
    (`croquito_worker.valuation.local_server`): decodificar 4.964 x 1.536 float32 e
    normalizar as linhas a cada recompute tornaria a leitura de um artefato imutável a
    etapa mais cara do ato.

    A chave é o par que o ADR-0054 D4 nomeia, e cada metade dela faz um trabalho: o digest
    do OBJETO garante que índice trocado é entrada nova, e o digest do CATÁLOGO garante que
    um vínculo só é reusado com o mesmo catálogo que o `bind_index_to_catalog` conferiu.
    Sem a segunda metade, um catálogo trocado receberia de volta um `SemanticIndex`
    amarrado ao anterior — exatamente a degradação silenciosa que a amarração existe para
    recusar.

    É cache de LEITURA de artefato público e imutável — não de decisão, não de autorização
    e não de nada que dependa de tenant: dois tenants com o mesmo índice compartilham a
    mesma matriz de propósito, porque o conteúdo é idêntico byte a byte por construção.
    """

    def __init__(self, max_entries: int = CATALOG_INDEX_CACHE_MAX_ENTRIES) -> None:
        self._lock = threading.Lock()
        self._entries: OrderedDict[tuple[str, str], SemanticIndex] = OrderedDict()
        self._max_entries = max_entries

    def get(self, key: tuple[str, str]) -> SemanticIndex | None:
        with self._lock:
            index = self._entries.get(key)
            if index is not None:
                self._entries.move_to_end(key)
            return index

    def put(self, key: tuple[str, str], index: SemanticIndex) -> None:
        with self._lock:
            self._entries[key] = index
            self._entries.move_to_end(key)
            while len(self._entries) > self._max_entries:
                self._entries.popitem(last=False)


def published_index_for_catalog(
    session: Session,
    *,
    catalog_source_sha256: str,
    text_recipe: str = INDEX_TEXT_RECIPE,
) -> ReferenceCatalogEmbeddingRecord | None:
    """A publicação vigente para um catálogo e uma receita, ou `None` quando não há uma.

    A busca é por DIGEST da fonte (ADR-0054 D3), e não pelo `reference_catalog_id`: assim o
    índice serve qualquer entrada do acervo cujos bytes de origem sejam os mesmos, que é a
    identidade que a decisão de código cita. `text_recipe` entra na chave porque trocar a
    receita muda os vetores tanto quanto trocar de modelo.

    Ausência é estado NORMAL, não erro (D6): fonte sem índice contribui só com o braço
    léxico. Por isso `None`, e não exceção.

    Ordenação em Python e não no banco, como nas demais listagens de plataforma: SQLite
    (testes) e PostgreSQL (hospedado) não ordenam texto do mesmo jeito. O `id` é UUIDv7,
    então a última publicação disponível é a mais recente — republicar a mesma receita com
    modelo novo passa a valer sem que ninguém precise retirar a anterior.
    """
    records = session.scalars(
        select(ReferenceCatalogEmbeddingRecord).where(
            ReferenceCatalogEmbeddingRecord.catalog_source_sha256 == catalog_source_sha256,
            ReferenceCatalogEmbeddingRecord.text_recipe == text_recipe,
            ReferenceCatalogEmbeddingRecord.status == STATUS_AVAILABLE,
        )
    ).all()
    if not records:
        return None
    return sorted(records, key=lambda record: record.id)[-1]


def read_semantic_index(
    store: CatalogIndexStore,
    *,
    record: ReferenceCatalogEmbeddingRecord,
    catalog: PriceCatalog,
    cache: SemanticIndexCache,
) -> SemanticIndex:
    """Lê o objeto publicado, valida o documento e o AMARRA ao catálogo informado.

    A amarração é `bind_index_to_catalog` (`sco_matching`), e ela não é reimplementada aqui:
    aquela função já recusa fechado índice de outro catálogo, de outra receita ou com
    contagem de itens divergente, e é a MESMA usada pelo CLI e pelo servidor de medição —
    duas conferências escritas em lados opostos passariam nos testes de cada um e
    divergiriam em silêncio.

    Recusa por exceção de domínio, nunca por degradação silenciosa: `INDEX_CATALOG_MISMATCH`
    e `INDEX_TEXT_RECIPE_MISMATCH` vêm da amarração, `INDEX_PAYLOAD_INVALID` do contrato do
    documento e `INDEX_OBJECT_UNREADABLE` do ambiente. Quem chama decide se isso vira nota
    de degradação (é o que a cascata fará) ou recusa do ato.
    """
    key = (record.object_sha256, catalog.source_sha256)
    cached = cache.get(key)
    if cached is not None:
        return cached
    payload = read_index_document(store, object_key=record.object_key)
    if hashlib.sha256(payload).hexdigest() != record.object_sha256.lower():
        raise ValuationValidationError(
            INDEX_OBJECT_UNREADABLE,
            "índice de embeddings com integridade divergente do digest registrado",
            {"reference_catalog_index_id": record.id},
        )
    index = bind_index_to_catalog(parse_index_document(payload), record.object_sha256, catalog)
    cache.put(key, index)
    return index


def resolve_semantic_index(
    session: Session,
    store: CatalogIndexStore,
    *,
    catalog: PriceCatalog,
    cache: SemanticIndexCache,
    text_recipe: str = INDEX_TEXT_RECIPE,
) -> SemanticIndex | None:
    """O índice publicado para um catálogo já carregado, ou `None` quando não há um.

    É o caminho inteiro da leitura num lugar só: achar a publicação por digest, ler o
    objeto, validar o documento e amarrá-lo ao catálogo. `None` diz "esta fonte não tem
    índice" (estado normal); exceção de domínio diz "há um índice e ele foi RECUSADO", que
    é fato diferente e a nota de degradação precisa distinguir (ADR-0054 D6).
    """
    record = published_index_for_catalog(
        session, catalog_source_sha256=catalog.source_sha256, text_recipe=text_recipe
    )
    if record is None:
        return None
    return read_semantic_index(store, record=record, catalog=catalog, cache=cache)


def read_index_document(store: CatalogIndexStore, *, object_key: str) -> bytes:
    """Os bytes do índice, limitados por `CATALOG_INDEX_MAX_BYTES`, ou recusa.

    A leitura pede um byte a mais que o teto (contrato de `ArtifactStore.read_object`): é
    assim que "objeto do tamanho esperado" se distingue de "objeto maior que o limite" sem
    carregar o excesso. Passar do teto é recusa POR EXTENSO — o documento truncado
    desserializaria como JSON inválido e a causa verdadeira (o tamanho) sumiria numa recusa
    de contrato.
    """
    payload = store.read_object(object_key=object_key, max_bytes=CATALOG_INDEX_MAX_BYTES)
    if payload is None:
        raise ValuationValidationError(
            INDEX_OBJECT_UNREADABLE,
            "índice de embeddings ausente no armazenamento",
            {"max_bytes": CATALOG_INDEX_MAX_BYTES},
        )
    if len(payload) > CATALOG_INDEX_MAX_BYTES:
        raise ValuationValidationError(
            INDEX_OBJECT_UNREADABLE,
            "índice de embeddings excede o limite de leitura da API",
            {"max_bytes": CATALOG_INDEX_MAX_BYTES},
        )
    return payload


def parse_index_document(payload: bytes) -> CatalogEmbeddingIndex:
    """Desserializa o documento do índice; nada aqui o constrói (ADR-0054 D4).

    Um JSON de vetores validado por Pydantic **não** é o parser de planilha que a decisão 9
    do ADR-0047 proíbe no servidor: não há formato binário de terceiro, não há derivação
    paga e não há dado de cliente — é leitura de um documento de contrato fechado
    (`extra="forbid"`) que o próprio operador publicou.

    A recusa sai sempre como erro de DOMÍNIO, nunca como `ValidationError` do pydantic. O
    invariante do próprio documento (vetores que não batem com códigos vezes dimensões) já
    levanta `INDEX_PAYLOAD_INVALID` de dentro do validador, e o pydantic o encapsula:
    `valuation_errors` o recupera para que o código verdadeiro chegue a quem chama, em vez
    de virar um genérico. A recusa de forma (campo faltando, tipo errado, extra proibido)
    não tem código próprio e cai no mesmo `INDEX_PAYLOAD_INVALID`.

    Nada da mensagem do pydantic viaja: ela pode conter valores do arquivo, e resposta de
    erro não é lugar de conteúdo de artefato.
    """
    try:
        return CatalogEmbeddingIndex.model_validate_json(payload)
    except ValidationError as error:
        embedded = valuation_errors(error)
        if embedded:
            raise embedded[0] from error
        raise ValuationValidationError(
            "INDEX_PAYLOAD_INVALID",
            "o índice de embeddings enviado não pôde ser lido",
        ) from error
