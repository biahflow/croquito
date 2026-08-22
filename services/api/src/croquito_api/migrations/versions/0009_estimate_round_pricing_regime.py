"""orcamento: regime de preço da rodada (ADR-0045).

Revision ID: 0009
Revises: 0008
Create Date: 2026-08-22

Acrescenta uma coluna NULLABLE a `estimate_rounds`: `pricing_regime`, o regime de preço
declarado para a rodada. `NULL` é o comportamento de antes desta decisão — pré-licitação,
cascata livre — e é AUSÊNCIA, não valor: "pré-licitação" nunca é gravado, porque
escrevê-lo faria a falta de uma declaração humana parecer uma (ADR-0045, decisão 2). O
único valor gravável é `contracted_demand`, e a partir dele a cascata só aceita `sco`, com
a recusa acontecendo na INSTALAÇÃO da fonte (decisão 3).

Nenhuma tabela do `Estimate` muda: o regime é dado da RODADA, não do artefato, exatamente
como o teto da `0004` — cujo molde esta revisão segue, inclusive na escrita à MÃO em vez
de `make db-revision`, porque o autogenerate precisa de um PostgreSQL vivo para comparar
contra (`services/api/AGENTS.md`) e esta árvore de trabalho não tem um. O gate do ADR-0029
(`tests/api/test_migrations.py`, que exige `CROQUITO_TEST_POSTGRES_URL` e roda no CI)
confere que esta migration produz exatamente o schema que `Base.metadata` declara.

Nenhuma linha existente é tocada: `ADD COLUMN` NULLABLE não exige backfill nem
`server_default` — o default é do modelo (`None`), e declará-lo aqui faria o gate de drift
acusar divergência entre a migration e `Base.metadata`. Rodada aberta antes desta revisão
continua sem regime, que é o estado correto: ninguém declarou nada por ela.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "estimate_rounds", sa.Column("pricing_regime", sa.String(length=32), nullable=True)
    )


def downgrade() -> None:
    # Forward-only por decisão (ADR-0029, D2): reverter é apontar a revisão anterior da
    # imagem, não desfazer DDL num banco hospedado.
    raise NotImplementedError(
        "Migrations são forward-only (ADR-0029): reverta apontando a revisão anterior da imagem."
    )
