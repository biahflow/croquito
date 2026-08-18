"""medicao: tabelas da rodada de medição de obra.

Revision ID: 0002
Revises: 0001
Create Date: 2026-08-17

Primeira revisão depois da baseline, e o primeiro uso real do runner do ADR-0029.
Cria as duas tabelas decididas no ADR-0028 D2 — `valuation_rounds`
(identidade, obra, catálogo instalado e o contador único de versão do D3) e
`valuation_round_revisions` (append-only, uma coluna JSON por artefato da cadeia).

Nenhuma tabela existente é alterada e nenhuma linha é migrada: a decisão humana de
2026-08-17 é que as rodadas do bucket de homologação **não** são importadas.

`BASELINE_TABLES` em `croquito_api.bootstrap` deliberadamente NÃO recebe estas tabelas:
ela descreve a revisão `0001`, e um banco anterior ao runner não pode tê-las. É este
`upgrade`, aplicado logo depois do carimbo, que as cria.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "valuation_rounds",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=128), nullable=False),
        sa.Column("worksite_key", sa.String(length=64), nullable=False),
        sa.Column("worksite_name", sa.String(length=120), nullable=False),
        sa.Column("reference_label", sa.String(length=120), nullable=False),
        sa.Column("period_number", sa.Integer(), nullable=False),
        sa.Column("address", sa.String(length=200), nullable=True),
        sa.Column("contract_label", sa.String(length=120), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("catalog_upload_id", sa.String(length=36), nullable=False),
        sa.Column("catalog_object_key", sa.String(length=512), nullable=False),
        sa.Column("catalog_source_sha256", sa.String(length=64), nullable=False),
        sa.Column("catalog_summary_json", sa.JSON(), nullable=False),
        sa.Column("plate_upload_id", sa.String(length=36), nullable=True),
        sa.Column("plate_object_key", sa.String(length=512), nullable=True),
        sa.Column("plate_source_sha256", sa.String(length=64), nullable=True),
        sa.Column("plate_page_count", sa.Integer(), nullable=True),
        sa.Column("extraction_id", sa.String(length=36), nullable=True),
        sa.Column("extraction_status", sa.String(length=16), nullable=False),
        sa.Column("extraction_failure_code", sa.String(length=80), nullable=True),
        sa.Column("extraction_requested_by", sa.String(length=128), nullable=True),
        sa.Column("extraction_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.String(length=128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        # Sem chave estrangeira para `projects`: a fronteira do ADR-0016 vale também no
        # modelo relacional (ADR-0028 D8).
        sa.ForeignKeyConstraint(
            ["catalog_upload_id"],
            ["uploads.id"],
        ),
        sa.ForeignKeyConstraint(
            ["plate_upload_id"],
            ["uploads.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    # Índice composto da listagem com cursor opaco; declarado também em `__table_args__`,
    # e o gate de drift reprova se existir só de um dos dois lados.
    op.create_index(
        "ix_valuation_rounds_tenant_created",
        "valuation_rounds",
        ["tenant_id", "created_at", "id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_valuation_rounds_tenant_id"), "valuation_rounds", ["tenant_id"], unique=False
    )
    op.create_table(
        "valuation_round_revisions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=128), nullable=False),
        sa.Column("round_id", sa.String(length=36), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("parent_revision_id", sa.String(length=36), nullable=True),
        sa.Column("takeoff_packet_json", sa.JSON(), nullable=True),
        sa.Column("takeoff_registration_json", sa.JSON(), nullable=True),
        sa.Column("code_suggestions_json", sa.JSON(), nullable=True),
        sa.Column("code_assignments_json", sa.JSON(), nullable=True),
        sa.Column("valuation_json", sa.JSON(), nullable=True),
        sa.Column("amendment_dossier_json", sa.JSON(), nullable=True),
        sa.Column("extraction_lineage_json", sa.JSON(), nullable=True),
        sa.Column("artifact_refs_json", sa.JSON(), nullable=False),
        sa.Column("artifact_digests_json", sa.JSON(), nullable=False),
        sa.Column("created_by", sa.String(length=128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["round_id"],
            ["valuation_rounds.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("round_id", "version", name="uq_valuation_round_version"),
    )
    op.create_index(
        op.f("ix_valuation_round_revisions_round_id"),
        "valuation_round_revisions",
        ["round_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_valuation_round_revisions_tenant_id"),
        "valuation_round_revisions",
        ["tenant_id"],
        unique=False,
    )


def downgrade() -> None:
    # Forward-only por decisão (ADR-0029, D2): reverter é apontar a revisão anterior da
    # imagem, não desfazer DDL num banco hospedado.
    raise NotImplementedError(
        "Migrations são forward-only (ADR-0029): reverta apontando a revisão anterior da imagem."
    )
