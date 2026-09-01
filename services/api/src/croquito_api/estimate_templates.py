"""Gabarito da prefeitura na fronteira da API: o que a rota decide antes de HTTP.

Camada de aplicação sem FastAPI, no molde de `site_setup_kits.py` e `reference_catalogs.py`:
nada aqui recebe `Request`, monta `Response` nem conhece código de status por si só. O motor
é `croquito_valuation.template.EstimateTemplateLayout`, entregue pela F-043 T1, e não é
reimplementado aqui — quem valida ordem, unicidade de código e formato de código é ele.

O que mora neste módulo é o pouco que precisa de UMA fonte deste lado da fronteira (F-043 T2):

- **a cláusula de tenant** (`visible_templates`), escrita uma vez. O gabarito publicado hoje é
  sempre de plataforma (`tenant_id IS NULL`), mas quem lê pela rodada de um tenant precisa da
  cláusula inteira, e repeti-la em cada rota é como ela divergiria;
- **a recusa de republicação** (`already_published`), que é o que torna o gabarito imutável;
- o payload que a tela lê, com a revisão do gabarito à vista.

O gabarito NÃO carrega as 433 linhas para a listagem: `template_record_payload` devolve
identidade, revisão e contagem. Quem precisa do documento inteiro é a publicação da planilha,
e ela o lê da linha pelo id.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final

from sqlalchemy import or_
from sqlalchemy.sql.elements import ColumnElement

from croquito_api.database import EstimateTemplateRecord
from croquito_api.valuation_rounds import RoundRefusal, document_digest
from croquito_valuation.template import EstimateTemplateLayout

ESTIMATE_TEMPLATE_ALREADY_PUBLISHED: Final = "ESTIMATE_TEMPLATE_ALREADY_PUBLISHED"
ESTIMATE_TEMPLATE_WITHDRAWN: Final = "ESTIMATE_TEMPLATE_WITHDRAWN"

ORIGIN_PLATFORM: Final = "platform"
"""Gabarito publicado pela plataforma, válido para todos os tenants (`tenant_id IS NULL`)."""

ORIGIN_TENANT: Final = "tenant"
"""Gabarito autorado por um tenant. Nenhuma rota o escreve ainda; a coluna o antecipa."""


# --- fronteira de tenant ------------------------------------------------------------------


def visible_templates(tenant_id: str) -> ColumnElement[bool]:
    """`tenant_id IS NULL OR tenant_id = :tenant`, a cláusula de toda leitura POR RODADA.

    Escrita uma vez de propósito, pela mesma razão de `site_setup_kits.visible_kits`: a metade
    esquecida não quebra teste nenhum — ela só mostra ao tenant errado, ou esconde do dono.

    As rotas de PLATAFORMA não usam esta cláusula: elas filtram `tenant_id IS NULL`, porque
    listar ali o gabarito autorado por um tenant daria a um operador a lista dos artefatos de
    todos os clientes.
    """
    return or_(
        EstimateTemplateRecord.tenant_id.is_(None),
        EstimateTemplateRecord.tenant_id == tenant_id,
    )


def template_origin(record: EstimateTemplateRecord) -> str:
    """De onde o gabarito veio, para a tela dizê-lo sem reinterpretar `tenant_id`."""
    return ORIGIN_PLATFORM if record.tenant_id is None else ORIGIN_TENANT


# --- documento ----------------------------------------------------------------------------


def load_template(record: EstimateTemplateRecord) -> EstimateTemplateLayout:
    """O gabarito gravado, revalidado na leitura.

    Espelha `site_setup_kits.load_kit`: o artefato passa pelo validador do domínio de novo
    toda vez que sai do banco, e não só quando entrou.
    """
    return EstimateTemplateLayout.model_validate(record.document_json)


def template_document_digest(document: Mapping[str, Any]) -> str:
    """Digest canônico do documento do gabarito, o mesmo de toda coluna JSON de revisão."""
    return document_digest(document)


def already_published(name: str, template_version: str) -> RoundRefusal:
    """Mesma `(name, template_version)`: recusa, nunca sobrescrita.

    Gabarito é imutável pela mesma razão do catálogo de referência (ADR-0047 D3): a planilha
    publicada IMPRIME a revisão do gabarito que a gerou, e reescrever o conteúdo por baixo
    faria aquele arquivo dizer uma revisão e descrever outra — exatamente o silêncio que o
    `revision_label` existe para desfazer. Revisão nova é linha nova.

    Esta recusa é conferida na ROTA, e não deixada para a `UniqueConstraint`: o gabarito de
    plataforma tem `tenant_id` nulo, e `NULL` não colide com `NULL` nem em PostgreSQL nem em
    SQLite. A constraint é a rede embaixo, para o dia em que houver gabarito com dono.
    """
    return RoundRefusal(
        409,
        ESTIMATE_TEMPLATE_ALREADY_PUBLISHED,
        "já existe gabarito com este nome e revisão; gabarito é imutável e revisão nova é "
        "entrada nova",
        {"name": name, "template_version": template_version},
    )


def template_withdrawn(estimate_template_id: str) -> RoundRefusal:
    """Gabarito fora de circulação não é oferecido; a linha continua existindo."""
    return RoundRefusal(
        409,
        ESTIMATE_TEMPLATE_WITHDRAWN,
        "este gabarito saiu de circulação e não é mais oferecido para publicação nova",
        {"estimate_template_id": estimate_template_id},
    )


# --- payloads -----------------------------------------------------------------------------


def template_record_payload(
    record: EstimateTemplateRecord, template: EstimateTemplateLayout
) -> dict[str, Any]:
    """O que a rota devolve sobre um gabarito publicado.

    Sem as linhas: são 433 no gabarito real, e nem a listagem nem a confirmação de publicação
    têm o que fazer com elas. O que decide escolha é identidade, revisão e tamanho — e é o
    tamanho que denuncia, à vista, um gabarito truncado.
    """
    return {
        "estimate_template_id": record.id,
        "name": record.name,
        "template_version": record.template_version,
        "origin": template_origin(record),
        "source_label": record.source_label,
        "sheet_name": template.sheet_name,
        "memory_sheet_name": template.memory_sheet_name,
        "row_count": len(template.rows),
        "document_sha256": record.document_sha256,
        "available": record.withdrawn_at is None,
        "created_by": record.created_by,
        "created_at": record.created_at,
        "withdrawn_at": record.withdrawn_at,
    }


def template_option_payload(
    record: EstimateTemplateRecord, template: EstimateTemplateLayout
) -> dict[str, Any]:
    """O gabarito como a RODADA o oferece: o que decide a escolha, e nada além.

    Difere de `template_record_payload` no que a orçamentista precisa saber para escolher, e
    que a administração não precisa: quantas linhas já vêm com preço no gabarito. É esse par
    — total e com preço — que o carimbo "433 linhas · 43 com quantidade · 390 zeradas" da tela
    aproxima antes de o orçamento existir.

    Não sai daqui: `created_by`, `withdrawn_at` e as linhas. Quem lista pela rodada só vê
    gabarito em circulação, então `available` seria sempre `true`.
    """
    return {
        "estimate_template_id": record.id,
        "name": record.name,
        "template_version": record.template_version,
        "origin": template_origin(record),
        "source_label": record.source_label,
        "sheet_name": template.sheet_name,
        "memory_sheet_name": template.memory_sheet_name,
        "row_count": len(template.rows),
        "priced_row_count": sum(1 for row in template.rows if row.unit_price is not None),
        "document_sha256": record.document_sha256,
    }
