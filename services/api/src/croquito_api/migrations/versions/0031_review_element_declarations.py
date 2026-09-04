"""identidade de elemento declarada na revisão, sobre propostas.

Revision ID: 0031
Revises: 0030
Create Date: 2026-09-04

Revisão aditiva e forward-only da F-051 (T2). Uma coluna JSON entra em ``review_revisions``
com default de servidor, no mesmo padrão das colunas da F-030 (migration ``0017``), para que
writers da imagem anterior — que listam as colunas uma a uma — atravessem o deploy rolante
sem falhar, e para que toda revisão já gravada leia a coluna nova como lista vazia.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0031"
down_revision: str | None = "0030"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "review_revisions",
        sa.Column(
            "element_declarations_json",
            sa.JSON(),
            server_default=sa.text("'[]'"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    raise NotImplementedError(
        "Migrations são forward-only (ADR-0029): reverta apontando a revisão anterior da imagem."
    )
