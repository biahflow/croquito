"""elo declarado entre a rodada de medição e o croqui aprovado.

Revision ID: 0028
Revises: 0027
Create Date: 2026-08-29

Acrescenta `valuation_round_revisions.scene_link_json` (F-047 T4b, ADR-0058 decisões 5 e
7), aditiva e `NULL`: nenhuma linha existente muda e nenhuma leitura anterior
passa a responder diferente. Rodada sem elo declarado continua respondendo exatamente como
antes desta coluna existir.

A coluna guarda o ATO de declarar qual croqui aprovado alimenta a rodada — job, revisão da
cena, export citado, digest do DXF auditado, autor e instante. Ela entra na cadeia
append-only da rodada, e não numa coluna da raiz, porque trocar o elo é OUTRO ato: cada
declaração grava revisão nova e a anterior continua legível onde foi feita. Numa coluna da
raiz, um `UPDATE` apagaria de qual croqui a medição anterior tinha vindo.

Sem índice novo: a coluna é lida sempre pela cabeça da rodada, que já é alcançada pelo
índice de `(round_id, version)` que `uq_valuation_round_version` sustenta. Nenhuma consulta
filtra por dentro do JSON.

Rollback: forward-only (ADR-0029, D2) — reverter é apontar a revisão anterior da imagem.
Recuperação manual, se um dia exigida com aprovação humana explícita, seria
`ALTER TABLE valuation_round_revisions DROP COLUMN scene_link_json`, e ela apagaria o
registro de qual croqui alimentou cada medição — por isso é ato humano, não automação.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0028"
down_revision: str | None = "0027"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "valuation_round_revisions",
        sa.Column("scene_link_json", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    # Forward-only por decisão (ADR-0029, D2): reverter é apontar a revisão anterior da
    # imagem, não desfazer DDL num banco hospedado.
    raise NotImplementedError(
        "Migrations são forward-only (ADR-0029): reverta apontando a revisão anterior da imagem."
    )
