"""quem montou o orçamento da revisão.

Revision ID: 0015
Revises: 0014
Create Date: 2026-08-22

Acrescenta `estimate_round_revisions.estimate_built_by` (F-035 T2, ADR-0046, decisão 6):
o subject de quem MONTOU o orçamento da cabeça, contra o qual a rota de aprovação compara o
`sub` do JWT para recusar auto-aprovação. `created_by` não serve para isso — ele é de quem
fez o ÚLTIMO ato, e depois de uma aprovação já não é quem montou.

Aditiva e `NULL`-able: nenhuma linha é migrada e nada é reescrito. `NULL` é "a rodada ainda
não tem orçamento montado" e também toda revisão anterior a esta coluna, cuja montagem não
registrou autor. Preencher retroativamente com `created_by` seria inventar um fato — a
revisão pode ter sido criada por um ato posterior à montagem —, e o efeito prático de
deixar `NULL` é honesto: uma rodada montada antes do deploy precisa ser remontada para
poder ser aprovada, que é ato normal da jornada.

Expand/contract: a coluna entra antes de qualquer código exigi-la, e o código anterior
convive com ela porque ela é opcional (services/api/AGENTS.md).

Rollback: forward-only (ADR-0029, D2) — reverter é apontar a revisão anterior da imagem, e
o código anterior continua funcionando com a coluna presente. Recuperação manual, se um dia
exigida com aprovação humana explícita, seria
`ALTER TABLE estimate_round_revisions DROP COLUMN estimate_built_by`.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0015"
down_revision: str | None = "0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "estimate_round_revisions",
        sa.Column("estimate_built_by", sa.String(length=128), nullable=True),
    )


def downgrade() -> None:
    # Forward-only por decisão (ADR-0029, D2): reverter é apontar a revisão anterior da
    # imagem, não desfazer DDL num banco hospedado.
    raise NotImplementedError(
        "Migrations são forward-only (ADR-0029): reverta apontando a revisão anterior da imagem."
    )
