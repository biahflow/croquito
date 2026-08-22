"""jobs: histórico append-only de transição de estágio/status.

Revision ID: 0011
Revises: 0010
Create Date: 2026-08-21

`down_revision = "0006"` é DELIBERADO: a `0007` está reservada pela F-029, que segue em
execução em outra branch a partir do mesmo checkout original, e ainda não existe neste
worktree (`feat/f-031-value-events`). Encadear direto na `0006` evita que esta branch
invente uma `0007` própria que colidiria na integração. O rebase de integração desta
branch (gate humano, ver `docs/features/F-031-value-events/feature.md`) é quem resolve a
numeração final — provavelmente reapontando esta revisão para a `0007` real.

Cria `job_stage_events` (F-031 T1), aditiva e nova: nenhuma tabela existente muda e
nenhuma linha é migrada. `jobs.stage`/`status` são sobrescritos por `UPDATE` desde a
baseline, e sem esta tabela o cycle time por etapa não é reconstruível — o valor anterior
simplesmente desaparece no `UPDATE`. Cada transição real (API na criação do job, worker em
cada `UPDATE jobs SET status/stage`) grava aqui, na mesma transação, com `from_stage`/
`from_status` lidos do job antes da mudança.

Rollback: forward-only (ADR-0029, D2) — reverter é apontar a revisão anterior da imagem.
Recuperação manual, se um dia exigida com aprovação humana explícita, seria
`DROP TABLE job_stage_events`: nenhuma outra tabela depende dela.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "job_stage_events",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=128), nullable=False),
        sa.Column("job_id", sa.String(length=36), nullable=False),
        sa.Column("from_stage", sa.String(length=32), nullable=True),
        sa.Column("to_stage", sa.String(length=32), nullable=False),
        sa.Column("from_status", sa.String(length=32), nullable=True),
        sa.Column("to_status", sa.String(length=32), nullable=False),
        sa.Column("source", sa.String(length=16), nullable=False),
        sa.Column("failure_code", sa.String(length=80), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["job_id"],
            ["jobs.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_job_stage_events_tenant_id"), "job_stage_events", ["tenant_id"], unique=False
    )
    op.create_index(
        op.f("ix_job_stage_events_job_id"), "job_stage_events", ["job_id"], unique=False
    )


def downgrade() -> None:
    # Forward-only por decisão (ADR-0029, D2): reverter é apontar a revisão anterior da
    # imagem, não desfazer DDL num banco hospedado.
    raise NotImplementedError(
        "Migrations são forward-only (ADR-0029): reverta apontando a revisão anterior da imagem."
    )
