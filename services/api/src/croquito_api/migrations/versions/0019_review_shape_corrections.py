"""revisão de leitura: correções humanas de forma, em conjunto próprio.

Revision ID: 0019
Revises: 0018
Create Date: 2026-08-27

Acrescenta a `review_revisions` a coluna `shape_corrections_json` (F-018), ADITIVA e
NULLABLE: é o `VisionProposalSet` de proveniência `human-correction-v1`
([ADR-0050](../../../../../docs/adr/0050-correcao-humana-de-forma-como-proposta-derivada.md),
decisão 1), separado de `proposals_json` porque um conjunto declara UM `detector_version`
— e misturar observação de máquina com correção humana no mesmo conjunto apagaria
exatamente a distinção que a feature existe para preservar.

`NULL` é a verdade sobre toda revisão anterior: ninguém corrigiu forma nenhuma nela.
Sem `server_default`, pelo mesmo motivo da `0013`: a coluna é nullable, o caminho de
escrita do worker lista colunas uma a uma, e uma instância antiga que insira
`review_revisions` sem citá-la durante o deploy rolante (ADR-0029, e a regra de
expand/contract do `services/api/AGENTS.md`) segue válida gravando `NULL`.

O dado NÃO afrouxa portão nenhum: as propostas dentro dele continuam `unresolved` e
`export=false` por `Literal` do modelo (ADR-0050, decisão 5), e nada aqui promove
precisão nem entra em `ensure_exportable()`.

Rollback: forward-only (ADR-0029, D2) — reverter é apontar a revisão anterior da imagem.
Recuperação manual, se um dia for exigida com aprovação humana explícita, seria
`ALTER TABLE review_revisions DROP COLUMN shape_corrections_json`, que descarta as
correções humanas gravadas e nada mais: as observações originais vivem em
`proposals_json` e não dependem desta coluna.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0019"
down_revision: str | None = "0018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "review_revisions",
        sa.Column("shape_corrections_json", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    # Forward-only por decisão (ADR-0029, D2): reverter é apontar a revisão anterior da
    # imagem, não desfazer DDL num banco hospedado.
    raise NotImplementedError(
        "Migrations são forward-only (ADR-0029): reverta apontando a revisão anterior da imagem."
    )
