"""acervo de catálogos de referência da plataforma.

Revision ID: 0014
Revises: 0013
Create Date: 2026-08-22

Cria `reference_catalogs` (F-037 T1, ADR-0047), aditiva e nova: nenhuma tabela existente
muda e nenhuma linha é migrada. O caminho de upload por rodada continua idêntico ao que
está no ar — esta tabela acrescenta ONDE guardar centralmente, não substitui nada.

**Esta é a primeira tabela do schema sem `tenant_id`**, e a ausência é a decisão 1 do
ADR-0047, não descuido: catálogo público de preços não tem dono, não é dado de cliente e
não revela nada sobre nenhum tenant. A condição que sustenta a ausência — nada aqui deriva
de conteúdo de cliente — está escrita na docstring de `ReferenceCatalogRecord` e é
verificada por teste. Tabela global nova exige ADR próprio.

`uq_reference_catalog_object` sobre `object_sha256` é o que torna cada publicação imutável
e endereçada por conteúdo (decisão 3): republicar o mesmo arquivo é recusado pela rota com
código estável, e a constraint é a rede embaixo dela — data-base nova tem digest novo, logo
entrada nova, e a anterior continua existindo porque uma rodada antiga ainda a referencia.

Sem índice além do único: o acervo cresce por publicação manual de data-base (ordem de
dezenas de linhas), e a listagem lê a tabela inteira. Índice que ninguém usa é custo de
escrita e de manutenção sem contrapartida.

Rollback: forward-only (ADR-0029, D2) — reverter é apontar a revisão anterior da imagem.
Recuperação manual, se um dia exigida com aprovação humana explícita, seria
`DROP TABLE reference_catalogs`: nenhuma outra tabela depende dela, e ela não depende de
nenhuma. O objeto publicado no store não é tocado por DDL nenhuma.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0014"
down_revision: str | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "reference_catalogs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("display_name", sa.String(length=200), nullable=False),
        sa.Column("origin", sa.String(length=16), nullable=False),
        sa.Column("reference_month", sa.String(length=7), nullable=False),
        sa.Column("object_sha256", sa.String(length=64), nullable=False),
        sa.Column("source_sha256", sa.String(length=64), nullable=False),
        sa.Column("entry_count", sa.Integer(), nullable=False),
        sa.Column("object_key", sa.String(length=512), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("published_by", sa.String(length=128), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("withdrawn_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("object_sha256", name="uq_reference_catalog_object"),
    )


def downgrade() -> None:
    # Forward-only por decisão (ADR-0029, D2): reverter é apontar a revisão anterior da
    # imagem, não desfazer DDL num banco hospedado.
    raise NotImplementedError(
        "Migrations são forward-only (ADR-0029): reverta apontando a revisão anterior da imagem."
    )
