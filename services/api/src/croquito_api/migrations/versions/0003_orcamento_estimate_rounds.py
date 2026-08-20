"""orcamento: tabelas da rodada de orçamento-base.

Revision ID: 0003
Revises: 0002
Create Date: 2026-08-20

Cria as duas tabelas do orçamento-base de PRÉ-licitação (F-020, ADR-0038):
`estimate_rounds` (identidade da obra, cascata ORDENADA de fontes de preço,
prancha, extração e o contador único de versão) e `estimate_round_revisions`
(append-only, uma coluna JSON por artefato da cadeia).

Nenhuma tabela existente é alterada e nenhuma linha é migrada: as tabelas da
medição (`valuation_rounds`, `valuation_round_revisions`) ficam intactas, e o
orçamento-base não reaproveita rodada nenhuma delas — a fronteira do ADR-0027
vale também no modelo relacional.

Duas diferenças em relação a `0002` merecem nome, porque são as que fazem esta
revisão não ser uma cópia:

- não existem `period_number` nem `contract_label`: período e contrato são
  conceitos de obra licitada, e uma coluna que só poderia ser preenchida com
  mentira é pior do que uma coluna ausente;
- no lugar das quatro colunas de catálogo único entra `catalog_cascade_json`,
  cuja ORDEM é a regra de precificação declarada pelo orçamentista (ADR-0027).
  Ela nasce vazia porque a rodada de orçamento abre antes de ter fonte, ao
  contrário da de medição, que nasce com catálogo por construção.

`BASELINE_TABLES` em `croquito_api.bootstrap` deliberadamente NÃO recebe estas
tabelas, pelo mesmo motivo da `0002`: ela descreve a revisão `0001`, e um banco
anterior ao runner não pode tê-las. É este `upgrade`, aplicado depois do
carimbo, que as cria.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "estimate_rounds",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=128), nullable=False),
        sa.Column("worksite_key", sa.String(length=64), nullable=False),
        sa.Column("worksite_name", sa.String(length=120), nullable=False),
        sa.Column("reference_label", sa.String(length=120), nullable=False),
        sa.Column("address", sa.String(length=200), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        # `NOT NULL` sem `server_default`, no precedente de `catalog_summary_json` da
        # `0002`: o default de lista vazia é do modelo (`default=list`), e declará-lo
        # também no servidor faria o gate de drift do ADR-0029 acusar divergência entre a
        # migration e `Base.metadata` na primeira vez que alguém rodasse com
        # `compare_server_default` ligado.
        sa.Column("catalog_cascade_json", sa.JSON(), nullable=False),
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
        # Sem chave estrangeira para `projects`, como na medição: a fronteira do ADR-0016
        # vale também no modelo relacional.
        sa.ForeignKeyConstraint(
            ["plate_upload_id"],
            ["uploads.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    # Índice composto da listagem com cursor opaco; declarado também em `__table_args__`,
    # e o gate de drift reprova se existir só de um dos dois lados.
    op.create_index(
        "ix_estimate_rounds_tenant_created",
        "estimate_rounds",
        ["tenant_id", "created_at", "id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_estimate_rounds_tenant_id"), "estimate_rounds", ["tenant_id"], unique=False
    )
    op.create_table(
        "estimate_round_revisions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=128), nullable=False),
        sa.Column("round_id", sa.String(length=36), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("parent_revision_id", sa.String(length=36), nullable=True),
        sa.Column("takeoff_packet_json", sa.JSON(), nullable=True),
        sa.Column("takeoff_registration_json", sa.JSON(), nullable=True),
        sa.Column("code_suggestions_json", sa.JSON(), nullable=True),
        sa.Column("code_assignments_json", sa.JSON(), nullable=True),
        sa.Column("estimate_json", sa.JSON(), nullable=True),
        sa.Column("extraction_lineage_json", sa.JSON(), nullable=True),
        sa.Column("artifact_refs_json", sa.JSON(), nullable=False),
        sa.Column("artifact_digests_json", sa.JSON(), nullable=False),
        sa.Column("created_by", sa.String(length=128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["round_id"],
            ["estimate_rounds.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("round_id", "version", name="uq_estimate_round_version"),
    )
    op.create_index(
        op.f("ix_estimate_round_revisions_round_id"),
        "estimate_round_revisions",
        ["round_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_estimate_round_revisions_tenant_id"),
        "estimate_round_revisions",
        ["tenant_id"],
        unique=False,
    )


def downgrade() -> None:
    # Forward-only por decisão (ADR-0029, D2): reverter é apontar a revisão anterior da
    # imagem, não desfazer DDL num banco hospedado.
    raise NotImplementedError(
        "Migrations são forward-only (ADR-0029): reverta apontando a revisão anterior da imagem."
    )
