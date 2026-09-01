"""o gabarito da prefeitura vira artefato de plataforma, publicável e versionado.

Revision ID: 0029
Revises: 0028
Create Date: 2026-09-01

Cria `estimate_templates` (F-043 T2), aditiva e nova: nenhuma tabela existente muda e
nenhuma linha é migrada. Até aqui o gabarito de ordem fixa da prefeitura só existia como
arquivo JSON lido por caminho no CLI do worker — a API não conhecia `WorkbookTemplate` —,
e por isso a jornada web não tinha como oferecê-lo. O dono decidiu em 2026-08-28 que ele
vive como artefato de plataforma, no molde do acervo de catálogos da F-037.

`tenant_id` é ANULÁVEL e hoje sempre nulo: o gabarito é da prefeitura e vale para todos os
tenants, como em `site_setup_kits`. A coluna existe porque o gabarito de uma segunda
prefeitura, autorado por um tenant, é extensão previsível, e acrescentá-la depois custaria
uma migração com dado dentro.

`uq_estimate_template_identity` sobre `(tenant_id, name, template_version)` é a rede embaixo
da recusa de republicação — não a recusa em si. `NULL` não colide com `NULL` em PostgreSQL
nem em SQLite, e o gabarito de plataforma tem `tenant_id` nulo: quem recusa de verdade é a
rota, com `409 ESTIMATE_TEMPLATE_ALREADY_PUBLISHED`.

`template_version` é `String(120)` porque é o `max_length` de
`EstimateTemplateLayout.revision_label`. Apertá-la abaixo disso passaria em SQLite e daria
`500` em PostgreSQL — que foi exatamente como o defeito da chave de idempotência atravessou
a suíte inteira até a captura de navegador o encontrar.

Um índice, pelo caminho de leitura real: `tenant_id`, que toda consulta filtra.

Rollback: forward-only (ADR-0029, D2) — reverter é apontar a revisão anterior da imagem.
Recuperação manual, se um dia exigida com aprovação humana explícita, seria
`DROP TABLE estimate_templates`: nenhuma outra tabela depende dela. O que se perderia são os
gabaritos publicados, que são dado declarado e republicável pela mesma rota.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0029"
down_revision: str | None = "0028"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "estimate_templates",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=128), nullable=True),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("template_version", sa.String(length=120), nullable=False),
        sa.Column("source_label", sa.String(length=200), nullable=False),
        sa.Column("document_json", sa.JSON(), nullable=False),
        sa.Column("document_sha256", sa.String(length=64), nullable=False),
        sa.Column("withdrawn_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.String(length=128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id", "name", "template_version", name="uq_estimate_template_identity"
        ),
    )
    op.create_index(
        op.f("ix_estimate_templates_tenant_id"), "estimate_templates", ["tenant_id"], unique=False
    )


def downgrade() -> None:
    # Forward-only por decisão (ADR-0029, D2): reverter é apontar a revisão anterior da
    # imagem, não desfazer DDL num banco hospedado.
    raise NotImplementedError(
        "Migrations são forward-only (ADR-0029): reverta apontando a revisão anterior da imagem."
    )
