"""recusa de proposta assistida de agrupamento de elemento.

Revision ID: 0027
Revises: 0026
Create Date: 2026-08-28

Cria `element_proposal_rejections` (F-047 T6, ADR-0058 decisão 2), aditiva e nova: nenhuma
tabela existente muda e nenhuma linha é migrada. A proposta de agrupamento em si NUNCA é
persistida — ela é recomputada a cada leitura por
`croquito_core.element_proposals.propose_element_groups`, puro e determinístico sobre a
cena corrente. O que precisa de memória é só a RECUSA humana: sem ela, a mesma proposta
errada voltaria a ser oferecida a cada `GET /v1/jobs/{job_id}/elements/proposals`.

`tenant_id` é NOT NULL e sempre filtrado: é dado de revisão de um job de um tenant, a
mesma fronteira de `scene_revisions`.

`uq_element_proposal_rejection` sobre `(tenant_id, job_id, proposal_id)` faz recusar a
mesma proposta duas vezes o MESMO ato, não dois; é também o que o endpoint consulta para
responder `404 ELEMENT_PROPOSAL_NOT_FOUND` a uma segunda tentativa com outra
`Idempotency-Key`.

Dois índices, um por caminho de leitura real: `tenant_id` (toda leitura filtra por ele) e
`job_id` (é por ele que `GET .../elements/proposals` e o `POST .../rejections` consultam
quais propostas já foram recusadas neste job).

Rollback: forward-only (ADR-0029, D2) — reverter é apontar a revisão anterior da imagem.
Recuperação manual, se um dia exigida com aprovação humana explícita, seria
`DROP TABLE element_proposal_rejections`: nenhuma outra tabela depende dela, e nenhuma
identidade de elemento gravada em `scene_revisions.scene` se perde — o índice de recusa é
só memória do ato de dizer não a uma sugestão, não fonte de verdade de identidade nenhuma.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0027"
down_revision: str | None = "0026"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "element_proposal_rejections",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=128), nullable=False),
        sa.Column("job_id", sa.String(length=36), nullable=False),
        sa.Column("proposal_id", sa.String(length=32), nullable=False),
        sa.Column("entity_ids_json", sa.JSON(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("rejected_by", sa.String(length=128), nullable=False),
        sa.Column("rejected_by_role", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["job_id"],
            ["jobs.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id", "job_id", "proposal_id", name="uq_element_proposal_rejection"
        ),
    )
    op.create_index(
        op.f("ix_element_proposal_rejections_tenant_id"),
        "element_proposal_rejections",
        ["tenant_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_element_proposal_rejections_job_id"),
        "element_proposal_rejections",
        ["job_id"],
        unique=False,
    )


def downgrade() -> None:
    # Forward-only por decisão (ADR-0029, D2): reverter é apontar a revisão anterior da
    # imagem, não desfazer DDL num banco hospedado.
    raise NotImplementedError(
        "Migrations são forward-only (ADR-0029): reverta apontando a revisão anterior da imagem."
    )
