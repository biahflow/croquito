"""acervo de parcelas de canteiro com duas origens.

Revision ID: 0021
Revises: 0020
Create Date: 2026-08-28

Cria `site_setup_kits` (F-042 T2, ADR-0060), aditiva e nova: nenhuma tabela existente muda e
nenhuma linha é migrada. Depois desta revisão a jornada do orçamento continua exatamente como
antes até que alguém publique ou autore um acervo — o que ela acrescenta é ONDE o acervo passa
a poder existir.

`tenant_id` é ANULÁVEL, e é a decisão do ADR-0060, não descuido: o acervo tem duas origens —
plataforma (`NULL`, publicado por `platform_operator`, no molde da F-037) e tenant
(preenchido, autorado pela orçamentista a partir de uma rodada dela). Esta **não** é uma
terceira tabela sem `tenant_id`: a coluna existe, e toda leitura filtra
`tenant_id IS NULL OR tenant_id = :tenant`. A condição está escrita na docstring de
`SiteSetupKitRecord` e é verificada por teste com DOIS tenants.

`uq_site_setup_kit_identity` sobre `(tenant_id, name, kit_version)` é o que torna cada
publicação imutável: republicar a mesma versão é recusa, e versão nova é linha nova, como no
acervo de catálogos (ADR-0047 D3). A constraint **não** cobre sozinha o acervo de plataforma,
porque `NULL` não colide com `NULL` nem em PostgreSQL nem em SQLite; por isso a rota confere a
duplicidade antes de gravar, com código estável, e a constraint é a rede embaixo dela para o
acervo do tenant. Escrever aqui um índice único parcial sobre `(name, kit_version)` com
`tenant_id IS NULL` fecharia essa metade no banco, mas seria DDL específica de PostgreSQL num
schema que os testes também criam em SQLite — a divergência entre os dois ambientes custaria
mais do que a conferência explícita que a rota já faz.

O documento do acervo mora na coluna `document_json`, e não no object store como o
`catalog.json` da F-037: um acervo é receita curta, lida inteira em todo preview e em todo
apply, e não há bytes de arquivo de terceiro a preservar — só o `SiteSetupKit` que a própria
API validou antes de gravar. `document_sha256` deixa conferível, depois, que o acervo aplicado
numa rodada é byte a byte o que está aqui.

Índice em `tenant_id` porque é por ele que a listagem da rodada filtra, e ela roda em toda
abertura da etapa de códigos.

Rollback: forward-only (ADR-0029, D2) — reverter é apontar a revisão anterior da imagem.
Recuperação manual, se um dia exigida com aprovação humana explícita, seria
`DROP TABLE site_setup_kits`: nenhuma outra tabela depende dela, e a matriz de cálculo que
citou um acervo continua legível sem ela (a proveniência viaja DENTRO da `calc_matrix_json`,
não por chave estrangeira).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0021"
down_revision: str | None = "0020"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "site_setup_kits",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=128), nullable=True),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("kit_version", sa.String(length=40), nullable=False),
        sa.Column("source_label", sa.String(length=200), nullable=False),
        sa.Column("document_json", sa.JSON(), nullable=False),
        sa.Column("document_sha256", sa.String(length=64), nullable=False),
        sa.Column("withdrawn_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.String(length=128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "name", "kit_version", name="uq_site_setup_kit_identity"),
    )
    op.create_index(
        op.f("ix_site_setup_kits_tenant_id"), "site_setup_kits", ["tenant_id"], unique=False
    )


def downgrade() -> None:
    # Forward-only por decisão (ADR-0029, D2): reverter é apontar a revisão anterior da
    # imagem, não desfazer DDL num banco hospedado.
    raise NotImplementedError(
        "Migrations são forward-only (ADR-0029): reverta apontando a revisão anterior da imagem."
    )
