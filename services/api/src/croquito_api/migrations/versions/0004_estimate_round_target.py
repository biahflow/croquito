"""orcamento: teto de verba da rodada (ADR-0040).

Revision ID: 0004
Revises: 0003
Create Date: 2026-08-20

Acrescenta duas colunas NULLABLE a `estimate_rounds`: `target_amount` (o teto declarado,
`Decimal` exato como TEXTO — a mesma disciplina do BDI e da quantidade do takeoff) e
`target_label` (o rótulo livre da origem da verba, ex.: a demanda da Relação de Praças).
As duas nascem opcionais: rodada sem teto não preenche nenhuma, e "sem teto" é ausência
(`NULL`), nunca `0.00` — a validação de aplicação recusa zero e negativo antes de a linha
chegar ao banco (ADR-0040, decisão 1). Nenhuma tabela do `Estimate` muda: o teto é dado da
RODADA, não do artefato.

Primeira migração INCREMENTAL do repositório: `0001`-`0003` cada uma cria tabela nova, e
esta é a primeira a alterar uma tabela existente. Escrita à MÃO, e não por
`make db-revision`, porque o gerador de revisão precisa de um PostgreSQL vivo para o
autogenerate comparar contra (`services/api/AGENTS.md`); esta árvore de trabalho não tem
um. O gate do ADR-0029 (`tests/api/test_migrations.py`, que exige
`CROQUITO_TEST_POSTGRES_URL` e roda no CI) confere que esta migration produz exatamente o
schema que `Base.metadata` declara — divergência reprova o CI, não esta revisão.

Nenhuma linha existente é tocada: `ADD COLUMN` NULLABLE não exige backfill nem
`server_default`, no mesmo precedente de `catalog_cascade_json` da `0003` — o default é do
modelo (`None`), e declará-lo aqui também faria o gate de drift acusar divergência entre a
migration e `Base.metadata` na primeira comparação com `compare_server_default` ligado.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "estimate_rounds", sa.Column("target_amount", sa.String(length=32), nullable=True)
    )
    op.add_column(
        "estimate_rounds", sa.Column("target_label", sa.String(length=120), nullable=True)
    )


def downgrade() -> None:
    # Forward-only por decisão (ADR-0029, D2): reverter é apontar a revisão anterior da
    # imagem, não desfazer DDL num banco hospedado.
    raise NotImplementedError(
        "Migrations são forward-only (ADR-0029): reverta apontando a revisão anterior da imagem."
    )
