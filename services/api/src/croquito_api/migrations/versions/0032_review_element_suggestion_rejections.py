"""recusa de sugestão assistida de identidade na revisão, sobre o rótulo do modelo.

Revision ID: 0032
Revises: 0031
Create Date: 2026-09-04

Cria `review_element_suggestion_rejections` (F-051 T3, ADR-0063 decisão 1), aditiva e
nova: nenhuma tabela existente muda e nenhuma linha é migrada. O gêmeo, uma etapa antes,
de `element_proposal_rejections` (migration `0027`): a sugestão em si NUNCA é persistida —
ela é recomputada a cada leitura por
`croquito_worker.review_element_suggestions.suggest_review_elements`, puro e determinístico
sobre o `VisionProposalSet` corrente da revisão. O que precisa de memória é só a RECUSA
humana: sem ela, a mesma sugestão de rótulo errado voltaria a ser oferecida a cada
`GET /v1/jobs/{job_id}/review/elements/suggestions`.

`tenant_id` é NOT NULL e sempre filtrado: é dado de revisão de um job de um tenant, a
mesma fronteira de `review_revisions`.

`uq_review_element_suggestion_rejection` sobre `(tenant_id, job_id, suggestion_id)` faz
recusar a mesma sugestão duas vezes o MESMO ato, não dois; é também o que o endpoint
consulta para responder `404 REVIEW_ELEMENT_SUGGESTION_NOT_FOUND` a uma segunda tentativa
com outra `Idempotency-Key`.

Dois índices, um por caminho de leitura real: `tenant_id` (toda leitura filtra por ele) e
`job_id` (é por ele que `GET .../elements/suggestions` e o `POST .../rejections` consultam
quais sugestões já foram recusadas neste job).

Rollback: forward-only (ADR-0029, D2) — reverter é apontar a revisão anterior da imagem.
Recuperação manual, se um dia exigida com aprovação humana explícita, seria
`DROP TABLE review_element_suggestion_rejections`: nenhuma outra tabela depende dela, e
nenhuma identidade de elemento gravada em `review_revisions.element_declarations_json` se
perde — o índice de recusa é só memória do ato de dizer não a uma sugestão, não fonte de
verdade de identidade nenhuma.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0032"
down_revision: str | None = "0031"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "review_element_suggestion_rejections",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=128), nullable=False),
        sa.Column("job_id", sa.String(length=36), nullable=False),
        sa.Column("suggestion_id", sa.String(length=32), nullable=False),
        sa.Column("proposal_ids_json", sa.JSON(), nullable=False),
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
            "tenant_id",
            "job_id",
            "suggestion_id",
            name="uq_review_element_suggestion_rejection",
        ),
    )
    op.create_index(
        op.f("ix_review_element_suggestion_rejections_tenant_id"),
        "review_element_suggestion_rejections",
        ["tenant_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_review_element_suggestion_rejections_job_id"),
        "review_element_suggestion_rejections",
        ["job_id"],
        unique=False,
    )


def downgrade() -> None:
    # Forward-only por decisão (ADR-0029, D2): reverter é apontar a revisão anterior da
    # imagem, não desfazer DDL num banco hospedado.
    raise NotImplementedError(
        "Migrations são forward-only (ADR-0029): reverta apontando a revisão anterior da imagem."
    )
