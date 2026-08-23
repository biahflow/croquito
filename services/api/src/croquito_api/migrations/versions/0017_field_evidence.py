"""evidência de campo vinculada ao job, fotos avulsas e observações versionadas.

Revision ID: 0017
Revises: 0016
Create Date: 2026-08-23

Revisão aditiva e forward-only da F-030. Cria o vínculo muitos-para-muitos job ↔ survey,
metadados de fotos avulsas e confirmações humanas de valores lidos. Os blobs e resultados
de análise permanecem no object storage; o banco guarda somente digests, chaves opacas,
estado e autoria. Duas colunas JSON entram em ``review_revisions`` com defaults de servidor
para que writers da imagem anterior atravessem o deploy rolante sem falhar.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0017"
down_revision: str | None = "0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "job_survey_links",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=128), nullable=False),
        sa.Column("job_id", sa.String(length=36), nullable=False),
        sa.Column("survey_id", sa.String(length=36), nullable=False),
        sa.Column("linked_by", sa.String(length=128), nullable=False),
        sa.Column("linked_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"]),
        sa.ForeignKeyConstraint(
            ["tenant_id", "survey_id"],
            ["survey_records.tenant_id", "survey_records.id"],
            name="fk_job_survey_links_survey",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "job_id", "survey_id", name="uq_job_survey_link"),
    )
    op.create_index(op.f("ix_job_survey_links_tenant_id"), "job_survey_links", ["tenant_id"])
    op.create_index(op.f("ix_job_survey_links_job_id"), "job_survey_links", ["job_id"])
    op.create_index(op.f("ix_job_survey_links_survey_id"), "job_survey_links", ["survey_id"])

    op.create_table(
        "job_field_photo_records",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=128), nullable=False),
        sa.Column("job_id", sa.String(length=36), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("mime_type", sa.String(length=100), nullable=False),
        sa.Column("byte_size", sa.Integer(), nullable=False),
        sa.Column("object_key", sa.String(length=512), nullable=False),
        sa.Column("anchor_text", sa.String(length=500), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("created_by", sa.String(length=128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("object_key"),
        sa.UniqueConstraint("tenant_id", "job_id", "sha256", name="uq_job_field_photo_digest"),
    )
    op.create_index(
        op.f("ix_job_field_photo_records_tenant_id"),
        "job_field_photo_records",
        ["tenant_id"],
    )
    op.create_index(
        op.f("ix_job_field_photo_records_job_id"), "job_field_photo_records", ["job_id"]
    )

    op.create_table(
        "field_evidence_analyses",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=128), nullable=False),
        sa.Column("job_id", sa.String(length=36), nullable=False),
        sa.Column("origin", sa.String(length=16), nullable=False),
        sa.Column("evidence_id", sa.String(length=36), nullable=False),
        sa.Column("task", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("artifact_key", sa.String(length=512), nullable=True),
        sa.Column("failure_code", sa.String(length=80), nullable=True),
        sa.Column("requested_by", sa.String(length=128), nullable=False),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "job_id",
            "origin",
            "evidence_id",
            "task",
            name="uq_field_evidence_analysis_target",
        ),
    )
    op.create_index(
        op.f("ix_field_evidence_analyses_tenant_id"),
        "field_evidence_analyses",
        ["tenant_id"],
    )
    op.create_index(
        op.f("ix_field_evidence_analyses_job_id"),
        "field_evidence_analyses",
        ["job_id"],
    )
    op.create_index(
        op.f("ix_field_evidence_analyses_evidence_id"),
        "field_evidence_analyses",
        ["evidence_id"],
    )

    op.create_table(
        "field_photo_value_confirmations",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=128), nullable=False),
        sa.Column("job_id", sa.String(length=36), nullable=False),
        sa.Column("photo_id", sa.String(length=36), nullable=False),
        sa.Column("source_reading_id", sa.String(length=128), nullable=False),
        sa.Column("value_mm", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("raw_text", sa.Text(), nullable=False),
        sa.Column("supersedes_confirmation_id", sa.String(length=36), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("confirmed_by", sa.String(length=128), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"]),
        sa.ForeignKeyConstraint(["photo_id"], ["job_field_photo_records.id"]),
        sa.ForeignKeyConstraint(
            ["supersedes_confirmation_id"], ["field_photo_value_confirmations.id"]
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_field_photo_value_confirmations_tenant_id"),
        "field_photo_value_confirmations",
        ["tenant_id"],
    )
    op.create_index(
        op.f("ix_field_photo_value_confirmations_job_id"),
        "field_photo_value_confirmations",
        ["job_id"],
    )
    op.create_index(
        op.f("ix_field_photo_value_confirmations_photo_id"),
        "field_photo_value_confirmations",
        ["photo_id"],
    )

    op.add_column(
        "review_revisions",
        sa.Column(
            "field_witnesses_json",
            sa.JSON(),
            server_default=sa.text("'[]'"),
            nullable=False,
        ),
    )
    op.add_column(
        "review_revisions",
        sa.Column(
            "field_observations_json",
            sa.JSON(),
            server_default=sa.text("'[]'"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    raise NotImplementedError(
        "Migrations são forward-only (ADR-0029): reverta apontando a revisão anterior da imagem."
    )
