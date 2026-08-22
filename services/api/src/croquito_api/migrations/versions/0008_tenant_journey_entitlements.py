"""disponibilidade de jornada: entitlement por tenant e jornada (F-034).

Revision ID: 0008
Revises: 0007
Create Date: 2026-08-22

Cria `tenant_journey_entitlements`, no molde exato de `tenant_ai_processing_entitlements`
da `0001`: mesmo conjunto de colunas, mesma disciplina de auditoria (`authorized_by`,
`authorized_at`, `revoked_at`) e mesmo `status` textual. A única diferença é a coluna
`journey`, que transforma a unicidade em par (`tenant_id`, `journey`) — um tenant pode ter
o piloto de uma jornada e não o de outra.

Copiar a forma é deliberado: é o mesmo tipo de fato — decisão comercial duradoura, com
registro nominal de quem autorizou — e a tela que vai administrá-lo (fatia 2 da F-034) é a
mesma tela da autorização de IA. Uma tabela com forma diferente para o mesmo fato obrigaria
duas leituras de auditoria.

Nenhuma tabela existente é alterada e nenhuma linha é migrada. A tabela nasce vazia, e vazia
ela não muda comportamento nenhum: ela só é consultada quando o ambiente declara a jornada
`pilot`, e o padrão das três jornadas é `enabled`.

`BASELINE_TABLES` em `croquito_api.bootstrap` deliberadamente NÃO recebe esta tabela, pelo
mesmo motivo da `0002` e da `0003`: aquela lista descreve a revisão `0001`, e um banco
anterior ao runner não pode tê-la. É este `upgrade`, aplicado depois do carimbo, que a cria.

Rollback: forward-only (ADR-0029, D2) — reverter é apontar a revisão anterior da imagem.
Recuperação manual, se um dia for exigida com aprovação humana explícita, seria
`DROP TABLE tenant_journey_entitlements`, que descarta apenas as autorizações de piloto:
nenhuma outra tabela referencia esta, e uma jornada `enabled` continua aberta sem ela.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "tenant_journey_entitlements",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=128), nullable=False),
        sa.Column("journey", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("agreement_reference", sa.String(length=128), nullable=False),
        sa.Column("authorized_by", sa.String(length=128), nullable=False),
        sa.Column("authorized_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "journey", name="uq_journey_entitlement_tenant_journey"),
    )
    op.create_index(
        op.f("ix_tenant_journey_entitlements_tenant_id"),
        "tenant_journey_entitlements",
        ["tenant_id"],
        unique=False,
    )


def downgrade() -> None:
    # Forward-only por decisão (ADR-0029, D2): reverter é apontar a revisão anterior da
    # imagem, não desfazer DDL num banco hospedado.
    raise NotImplementedError(
        "Migrations são forward-only (ADR-0029): reverta apontando a revisão anterior da imagem."
    )
