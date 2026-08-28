"""O braço semântico do caminho hospedado: quando ele roda, e o que se diz quando não roda.

Camada de aplicação sem FastAPI, como `reference_catalogs.py` e `reference_catalog_indexes.py`:
nada aqui recebe `Request`, monta `Response` nem conhece código de status. O que mora aqui é
a montagem do `SemanticArm` de cada fonte a partir do índice PUBLICADO da plataforma
(ADR-0054) e o vocabulário das notas de degradação.

Três regras atravessam o módulo, e as três são do ADR-0054:

- **Nada aqui recusa um ato** (D8). Toda ausência — providers desligados, entitlement
  inativo, teto de gasto ou credencial ausentes, índice ausente, índice recusado na
  amarração — vira `SemanticArm(index=None, …)` com o motivo escrito. A shortlist sai
  léxica; o recompute não é perdido. `_require_active_ai_entitlement` levanta `403` e por
  isso **não** é usado aqui: um tenant sem entitlement perderia inclusive o braço léxico,
  que não custa nada.
- **A nota diz QUAL fonte ficou sem** (D6). Cobertura parcial é estado normal da cascata, e
  uma frase única ("o braço está indisponível") esconderia que o SCO rodou híbrido e só a
  EMOP ficou de fora. A fonte é nomeada por posição e origem — dado da rodada, nunca
  conteúdo do cliente.
- **A ausência de índice e a RECUSA de um índice são fatos diferentes.**
  `resolve_semantic_index` devolve `None` para o primeiro e levanta exceção de domínio para
  o segundo; achatar os dois numa nota só apagaria a informação de que existe um índice
  publicado e ele foi rejeitado — que é o desfecho de um deploy fora de ordem quando a
  receita de texto muda, e o único sinal de que alguém precisa republicar.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Final

from sqlalchemy.orm import Session

from croquito_api.reference_catalog_indexes import (
    CatalogIndexStore,
    SemanticIndexCache,
    resolve_semantic_index,
)
from croquito_valuation.errors import ValuationValidationError
from croquito_valuation.models import PriceCatalog
from croquito_worker.providers import EmbeddingsAdapter
from croquito_worker.valuation.catalog_search import (
    SEMANTIC_AVAILABLE_MESSAGE,
    SEMANTIC_UNAVAILABLE_MESSAGE,
    SemanticArm,
)

PROVIDERS_DISABLED_REASON: Final = (
    f"{SEMANTIC_UNAVAILABLE_MESSAGE}: providers reais desligados neste ambiente"
)
"""`CROQUITO_REAL_PROVIDERS_ENABLED=false`: nenhuma chamada externa é possível.

Distinta da nota de entitlement de propósito. As duas param o mesmo braço, mas quem as
resolve é gente diferente: esta é do operador da plataforma (variável de ambiente do
serviço), a outra é comercial (contrato do tenant). Uma frase só faria a orçamentista abrir
chamado no lugar errado."""

ENTITLEMENT_INACTIVE_REASON: Final = (
    f"{SEMANTIC_UNAVAILABLE_MESSAGE}: tenant sem autorização contratual ativa para "
    "processamento externo"
)
"""ADR-0012/0036 sem `ACTIVE`: o braço pago não roda, e o recompute continua acontecendo."""


def source_label(*, position: int, catalog: PriceCatalog, total: int) -> str:
    """Como uma fonte é nomeada na nota: posição instalada e origem de preço.

    As duas juntas, e não uma delas: a posição é o que o orçamentista vê na tela (a ordem
    que ele mesmo instalou) e a origem é o que ele chama a tabela pelo nome. Nem o rótulo do
    arquivo nem o nome da obra entram aqui — nota de degradação é texto de tela e não é
    lugar de conteúdo.

    Com uma fonte só a posição some: a medição de obra licitada tem um catálogo e nada mais
    (ADR-0027), e "fonte 1" seria numeração de uma lista que não existe na tela dela.
    """
    if total == 1:
        return f"o catálogo da rodada ({catalog.origin.value})"
    return f"fonte {position} ({catalog.origin.value})"


def index_absent_reason(label: str) -> str:
    """Estado NORMAL (D6): esta fonte não tem índice publicado, e a shortlist sai léxica."""
    return f"{SEMANTIC_UNAVAILABLE_MESSAGE}: {label} sem índice de embeddings publicado"


def index_refused_reason(label: str, code: str) -> str:
    """Há índice e ele foi RECUSADO na amarração; o código de domínio viaja na nota.

    É o desfecho declarado de publicar o índice depois de subir o código que mudou a receita
    de texto (ADR-0054, riscos aceitos): `bind_index_to_catalog` recusa receita divergente,
    a shortlist degrada para léxica e o motivo diz o que republicar. Nada disso derruba o
    recompute.
    """
    return f"{SEMANTIC_UNAVAILABLE_MESSAGE}: índice de {label} recusado ({code})"


def index_available_message(label: str, model_id: str) -> str:
    """A declaração da PRÓPRIA fonte que tem índice; ela não vira nota na resposta.

    `SemanticArm.message` é obrigatório e existe para o arm dizer o que ele é. Quem monta
    `semantic_notes` (`compute_suggestions`/`compute_cascade_suggestions`) só publica as
    mensagens de quem NÃO rodou — a mesma regra que o caminho de um catálogo só já praticava
    desde o M7: nota é o que explica a falta, e o que rodou aparece no artefato, em
    `semantic` e no `suggester_version`, que é onde a auditoria procura.

    Ela continua sendo escrita porque é o motivo que a telemetria usa quando o braço é
    montado e ainda assim não resolve a consulta — aí a fonte que "estava disponível" precisa
    dizer com qual modelo ela estava.
    """
    return f"{SEMANTIC_AVAILABLE_MESSAGE} em {label}: {model_id}"


def resolve_cascade_arms(
    session: Session,
    store: CatalogIndexStore,
    *,
    cascade: Sequence[PriceCatalog],
    cache: SemanticIndexCache,
    adapter: EmbeddingsAdapter | None,
    unavailable_reason: str | None,
) -> list[SemanticArm]:
    """Um `SemanticArm` por fonte da cascata, na ordem instalada, com o motivo de cada uma.

    `unavailable_reason` é o portão do ATO — providers desligados, entitlement inativo, teto
    de gasto ou credencial ausentes. Quando ele existe, nenhuma fonte é consultada: sem
    adapter o braço não conseguiria embutir rótulo nenhum, e ir ao banco procurar índice que
    não seria usado gastaria consulta para produzir a mesma nota. A nota é a do portão, e não
    "sem índice" — dizer que falta índice quando o que falta é credencial mandaria a pessoa
    procurar o problema no lugar errado.

    Sem portão, cada fonte é resolvida por conta própria e o resultado de uma **não** afeta
    o das outras (D6): a EMOP sem índice não tira do SCO a vizinhança semântica que ele tem.
    """
    if unavailable_reason is not None or adapter is None:
        reason = unavailable_reason or PROVIDERS_DISABLED_REASON
        return [SemanticArm(None, None, "unavailable", reason) for _ in cascade]
    arms: list[SemanticArm] = []
    for position, catalog in enumerate(cascade, start=1):
        label = source_label(position=position, catalog=catalog, total=len(cascade))
        try:
            index = resolve_semantic_index(session, store, catalog=catalog, cache=cache)
        except ValuationValidationError as error:
            arms.append(
                SemanticArm(None, None, "unavailable", index_refused_reason(label, error.code))
            )
            continue
        if index is None:
            arms.append(SemanticArm(None, None, "unavailable", index_absent_reason(label)))
            continue
        arms.append(
            SemanticArm(index, adapter, "available", index_available_message(label, index.model_id))
        )
    return arms
