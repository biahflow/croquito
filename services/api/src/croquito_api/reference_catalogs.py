"""Acervo de catálogos de referência da plataforma: o que a rota decide antes de existir HTTP.

Camada de aplicação sem FastAPI, como `estimate_rounds.py` e `valuation_rounds.py`: nada
aqui recebe `Request`, monta `Response` nem conhece código de status. O que mora aqui é o
pouco que precisa de UMA fonte — o prefixo do objeto, a função que monta a chave, os
estados de circulação e as origens que a plataforma pode distribuir.

Duas propriedades atravessam o módulo (ADR-0047):

- **O objeto do acervo fica FORA de `tenants/`** (decisão 1): catálogo público não tem
  dono. A consequência prática é que as três guardas de prefixo do repositório —
  `signed_artifact_url` (`valuation_rounds.py`), `_preview_urls` e `_export_response`
  (`main.py`) — recusam uma chave do acervo por construção, e recusar é o comportamento
  CORRETO: o cliente escolhe a tabela, ele não a baixa (decisão 6). Nenhuma rota assina
  URL de objeto daqui.
- **A chave é endereçada pelo CONTEÚDO** (decisão 3), como `estimate_workbook_key` faz
  para a planilha do orçamento. Publicação nova nunca sobrescreve publicação antiga: uma
  rodada montada sobre a data-base anterior continua lendo exatamente o arquivo que ela
  citou.
"""

from __future__ import annotations

import re
from typing import Final

from croquito_valuation.models import PriceOrigin

#: Prefixo do acervo no object store. O primeiro segmento NÃO é `tenants/` de propósito:
#: é o que mantém o objeto público fora de todo caminho que assina URL por prefixo de
#: tenant, sem que nenhuma daquelas guardas precise ser afrouxada.
REFERENCE_CATALOG_PREFIX: Final = "platform/reference-catalogs/"

#: Estados de circulação de uma publicação. Retirar NÃO apaga (ADR-0047 decisão 3): a linha
#: e o objeto continuam existindo porque uma rodada antiga ainda os referencia; o que muda é
#: só o catálogo deixar de ser oferecido em escolha nova.
STATUS_AVAILABLE: Final = "AVAILABLE"
STATUS_WITHDRAWN: Final = "WITHDRAWN"

#: Origens que a PLATAFORMA pode distribuir para todos os tenants (ADR-0047 decisão 8).
#: `emop` é tabela paga e fica fora — quem tem a licença é o cliente, e ela continua
#: entrando pelo upload dele; `composition` é do cliente por natureza. A restrição vive
#: aqui, e não na leitura do catálogo, porque ela é sobre DISTRIBUIÇÃO: os dois formatos
#: continuam sendo lidos e instalados normalmente pelo caminho de upload.
PUBLISHABLE_ORIGINS: Final[frozenset[PriceOrigin]] = frozenset(
    {PriceOrigin.SCO, PriceOrigin.SINAPI, PriceOrigin.SICRO}
)

_OBJECT_SHA256_PATTERN: Final = re.compile(r"^[a-f0-9]{64}$")


def reference_catalog_key(*, object_sha256: str) -> str:
    """Chave do `catalog.json` publicado, endereçada pelo digest dos BYTES do arquivo.

    Uma função dedicada, e não interpolação espalhada: a chave do acervo é a única do
    projeto que não começa por `tenants/`, e o lugar onde essa exceção é escrita precisa ser
    um só — quem for procurar por que um objeto está fora do prefixo do tenant chega aqui.

    O digest é conferido contra a forma hexadecimal minúscula antes de virar caminho: ele
    vem do registro do upload já validado, mas montar caminho a partir de texto que ninguém
    olhou é como um `..` entra numa chave de object store.
    """
    if _OBJECT_SHA256_PATTERN.fullmatch(object_sha256) is None:
        raise ValueError("o digest do catálogo publicado precisa ser sha256 hexadecimal")
    return f"{REFERENCE_CATALOG_PREFIX}{object_sha256}.json"
