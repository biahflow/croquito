"""outbox transacional dos eventos de domínio publicados para fora.

Revision ID: 0012
Revises: 0011
Create Date: 2026-08-21

Cria `domain_events` (F-031 T2, ADR-0042), aditiva e nova: nenhuma tabela existente muda
e nenhuma linha é migrada. A tabela é a outbox que a API e o worker gravam na MESMA
transação do fato, e que o relay `croquito-demo publish-events` drena marcando
`published_at`.

`down_revision = "0008"` encadeia na revisão da T1 desta mesma branch. A numeração final
é assunto do rebase de integração (a `0007` está reservada pela F-029, ver o cabeçalho da
`0008`); o encadeamento relativo T1 → T2 é que precisa sobreviver a ele.

Índices: `tenant_id`, `event_type` e `job_id` servem à leitura por entidade; o de
`published_at` serve à varredura do relay (`WHERE published_at IS NULL`), que é o acesso
quente da tabela. Sem poda/retenção nesta fatia — consequência declarada no ADR-0042.

Rollback: forward-only (ADR-0029, D2) — reverter é apontar a revisão anterior da imagem.
Recuperação manual, se um dia exigida com aprovação humana explícita, seria
`DROP TABLE domain_events`: nenhuma outra tabela depende dela, e ela não depende de
nenhuma (`job_id` é coluna solta, sem chave estrangeira, porque o fato publicado não é
filho do job — ver a docstring de `DomainEventRecord`).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "domain_events",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=128), nullable=False),
        sa.Column("event_type", sa.String(length=80), nullable=False),
        sa.Column("job_id", sa.String(length=36), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload_json", sa.JSON(), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_domain_events_tenant_id"), "domain_events", ["tenant_id"])
    op.create_index(op.f("ix_domain_events_event_type"), "domain_events", ["event_type"])
    op.create_index(op.f("ix_domain_events_job_id"), "domain_events", ["job_id"])
    op.create_index(op.f("ix_domain_events_published_at"), "domain_events", ["published_at"])


def downgrade() -> None:
    # Forward-only por decisão (ADR-0029, D2): reverter é apontar a revisão anterior da
    # imagem, não desfazer DDL num banco hospedado.
    raise NotImplementedError(
        "Migrations são forward-only (ADR-0029): reverta apontando a revisão anterior da imagem."
    )
