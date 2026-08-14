"""Persistência transacional tenant-scoped para o primeiro fluxo SaaS."""

from __future__ import annotations

from collections.abc import Generator
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    create_engine,
    event,
    inspect,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker
from sqlalchemy.pool import StaticPool


class Base(DeclarativeBase):
    pass


class ProjectRecord(Base):
    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(128), index=True)
    name: Mapped[str] = mapped_column(String(160))
    default_unit: Mapped[str] = mapped_column(String(8))
    status: Mapped[str] = mapped_column(String(32), default="ACTIVE")
    created_by: Mapped[str] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class UploadRecord(Base):
    __tablename__ = "uploads"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(128), index=True)
    object_key: Mapped[str] = mapped_column(String(512), unique=True)
    filename: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(128))
    size_bytes: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(32), default="PRESIGNED")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )


class JobRecord(Base):
    __tablename__ = "jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(128), index=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    upload_id: Mapped[str] = mapped_column(ForeignKey("uploads.id"), unique=True)
    status: Mapped[str] = mapped_column(String(32), default="UPLOADED")
    stage: Mapped[str] = mapped_column(String(32), default="VALIDATING")
    page_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    failure_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )


class TenantAiProcessingEntitlementRecord(Base):
    """Contractual authorization managed by the platform for one tenant."""

    __tablename__ = "tenant_ai_processing_entitlements"
    __table_args__ = (UniqueConstraint("tenant_id", name="uq_ai_entitlement_tenant"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(128), index=True)
    status: Mapped[str] = mapped_column(String(16), default="ACTIVE")
    agreement_reference: Mapped[str] = mapped_column(String(128))
    authorized_by: Mapped[str] = mapped_column(String(128))
    authorized_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )


class AiProcessingAuthorizationRecord(Base):
    """Immutable per-job snapshot of the contractual AI-processing authorization."""

    __tablename__ = "ai_processing_consents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(128), index=True)
    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.id"), unique=True, index=True)
    accepted_by: Mapped[str] = mapped_column(String(128))
    notice_version: Mapped[str] = mapped_column(String(32))
    providers_json: Mapped[list[str]] = mapped_column(JSON)
    global_processing: Mapped[bool] = mapped_column()
    retention_days: Mapped[int] = mapped_column(Integer)
    authorization_source: Mapped[str | None] = mapped_column(String(32), nullable=True)
    entitlement_id: Mapped[str | None] = mapped_column(
        ForeignKey("tenant_ai_processing_entitlements.id"), nullable=True
    )
    agreement_reference: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )


class RevisionRecord(Base):
    __tablename__ = "scene_revisions"
    __table_args__ = (UniqueConstraint("job_id", "version", name="uq_scene_version"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(128), index=True)
    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.id"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    parent_revision_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    scene: Mapped[dict[str, Any]] = mapped_column(JSON)
    created_by: Mapped[str] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    approved_by: Mapped[str | None] = mapped_column(String(128), nullable=True)


class ReviewRevisionRecord(Base):
    """Immutable, tenant-scoped snapshot of a human measurement review.

    Evidence content lives in the protected artifact store.  The JSON columns keep
    only the review contract and object references required to reproduce a decision;
    they must never be copied to application logs.
    """

    __tablename__ = "review_revisions"
    __table_args__ = (UniqueConstraint("job_id", "version", name="uq_review_version"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(128), index=True)
    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.id"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    parent_review_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    packet_json: Mapped[dict[str, Any]] = mapped_column(JSON)
    associations_json: Mapped[dict[str, Any]] = mapped_column(JSON)
    proposals_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    selected_associations_json: Mapped[dict[str, str]] = mapped_column(JSON, default=dict)
    calibration_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    proposal_decisions_json: Mapped[list[dict[str, Any]] | None] = mapped_column(
        JSON, nullable=True
    )
    trace_acceptance_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    """The batch trace acceptance that produced this revision, recorded as a human act."""
    evidence_refs_json: Mapped[dict[str, str]] = mapped_column(JSON, default=dict)
    solver_request_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    solver_blockers_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    required_blocker_codes_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    required_criteria_texts_json: Mapped[dict[str, str] | None] = mapped_column(JSON, nullable=True)
    """Texto do critério por código, quando o caso o declarou; linha antiga fica NULL."""
    scene_revision_id: Mapped[str | None] = mapped_column(
        ForeignKey("scene_revisions.id"), nullable=True
    )
    created_by: Mapped[str] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )


class ReviewDecisionRecord(Base):
    """Append-only audit index for a decision whose full evidence remains in review JSON.

    A correção declarada de uma decisão (`action` ``rectify_confirm``/``rectify_reject``)
    é uma linha NOVA que cita a anterior em ``rectifies_decision_id``; nenhuma linha é
    editada ou removida.  O índice único é por revisão de leitura, e não por leitura: a
    mesma leitura pode aparecer em revisões diferentes, uma vez em cada ato humano.
    """

    __tablename__ = "review_decisions"
    __table_args__ = (
        UniqueConstraint("review_revision_id", "reading_id", name="uq_review_decision_reading"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(128), index=True)
    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.id"), index=True)
    review_revision_id: Mapped[str] = mapped_column(ForeignKey("review_revisions.id"))
    reading_id: Mapped[str] = mapped_column(String(32))
    action: Mapped[str] = mapped_column(String(16))
    reviewer_id: Mapped[str] = mapped_column(String(128))
    reviewer_role: Mapped[str] = mapped_column(String(32))
    association_proposal_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    decision_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    """Id da `HumanDecision` gravada nesta linha; NULL nas linhas anteriores à coluna."""
    rectifies_decision_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    """Decisão que esta corrige, quando o ato foi uma correção declarada."""
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )


class ProposalDecisionRecord(Base):
    """Append-only audit index; proposal geometry stays in the protected review snapshot."""

    __tablename__ = "proposal_decisions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(128), index=True)
    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.id"), index=True)
    review_revision_id: Mapped[str] = mapped_column(ForeignKey("review_revisions.id"))
    proposal_id: Mapped[str] = mapped_column(String(32))
    action: Mapped[str] = mapped_column(String(16))
    reviewer_id: Mapped[str] = mapped_column(String(128))
    reviewer_role: Mapped[str] = mapped_column(String(32))
    scene_revision_id: Mapped[str | None] = mapped_column(
        ForeignKey("scene_revisions.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )


class ApprovalRecord(Base):
    __tablename__ = "approvals"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(128), index=True)
    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.id"), index=True)
    source_revision_id: Mapped[str] = mapped_column(ForeignKey("scene_revisions.id"))
    approved_revision_id: Mapped[str] = mapped_column(ForeignKey("scene_revisions.id"))
    reviewer_id: Mapped[str] = mapped_column(String(128))
    reviewer_roles: Mapped[list[str]] = mapped_column(JSON)
    acknowledgement: Mapped[str] = mapped_column(Text)
    approval_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    """The SceneApproval contract, serialised exactly as the export package's aprovacao.json."""
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )


class ExportArtifactRecord(Base):
    """One published CAD package per approved revision; the ZIP itself lives in the store."""

    __tablename__ = "export_artifacts"
    __table_args__ = (
        UniqueConstraint("job_id", "scene_revision_id", "format", name="uq_export_target"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(128), index=True)
    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.id"), index=True)
    scene_revision_id: Mapped[str] = mapped_column(ForeignKey("scene_revisions.id"))
    approval_id: Mapped[str] = mapped_column(ForeignKey("approvals.id"))
    format: Mapped[str] = mapped_column(String(8), default="dxf")
    status: Mapped[str] = mapped_column(String(16), default="QUEUED")
    package_object_key: Mapped[str | None] = mapped_column(String(512), nullable=True)
    dxf_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    audit_status: Mapped[str | None] = mapped_column(String(16), nullable=True)
    audit_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    failure_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    requested_by: Mapped[str] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )


class TraceSolveRecord(Base):
    """One batch trace acceptance resolved outside the request path.

    The row is the durable intent (what the professional accepted and against which
    revisions) plus the solver outcome.  A version race is recorded here as
    ``solve_status='conflict'``, never raised: the caller polls a result, not a crash.
    """

    __tablename__ = "trace_solves"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(128), index=True)
    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.id"), index=True)
    base_review_revision_id: Mapped[str] = mapped_column(ForeignKey("review_revisions.id"))
    base_scene_revision_id: Mapped[str | None] = mapped_column(
        ForeignKey("scene_revisions.id"), nullable=True
    )
    status: Mapped[str] = mapped_column(String(16), default="QUEUED")
    acceptance_id: Mapped[str] = mapped_column(String(32))
    acceptance_json: Mapped[dict[str, Any]] = mapped_column(JSON)
    associations_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    note_associations_json: Mapped[dict[str, str]] = mapped_column(JSON, default=dict)
    derived_dimensions_json: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    dimension_texts_json: Mapped[dict[str, str]] = mapped_column(JSON, default=dict)
    title: Mapped[str | None] = mapped_column(String(120), nullable=True)
    feature_id: Mapped[str] = mapped_column(String(64), default="tracado")
    solve_status: Mapped[str | None] = mapped_column(String(24), nullable=True)
    blockers_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    unapplied_reading_ids_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    residual_summary_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    """Counts plus the worst residual; the full list stays in the solved scene."""
    exact_entity_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    approximate_entity_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    note_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    scale_m_per_px: Mapped[float | None] = mapped_column(Float, nullable=True)
    detail_group_scales_json: Mapped[dict[str, float]] = mapped_column(JSON, default=dict)
    result_scene_revision_id: Mapped[str | None] = mapped_column(
        ForeignKey("scene_revisions.id"), nullable=True
    )
    result_review_revision_id: Mapped[str | None] = mapped_column(
        ForeignKey("review_revisions.id"), nullable=True
    )
    failure_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    requested_by: Mapped[str] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )


class ChatSessionRecord(Base):
    """Uma conversa do profissional sobre a folha, presa à revisão de leitura que ele via.

    A revisão-base é fixada na abertura e nunca muda: uma conversa que seguisse a revisão
    corrente responderia sobre uma folha diferente da que gerou a pergunta.
    """

    __tablename__ = "chat_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(128), index=True)
    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.id"), index=True)
    base_review_revision_id: Mapped[str] = mapped_column(ForeignKey("review_revisions.id"))
    status: Mapped[str] = mapped_column(String(16), default="OPEN")
    created_by: Mapped[str] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )


class ChatTurnRecord(Base):
    """Uma pergunta e a resposta observacional que o worker gravou para ela.

    Pergunta e resposta ficam no banco, nunca em log: é o mesmo tratamento do
    ``packet_json.raw_text``.  A resposta é observação com rascunhos tipados; nenhum ato
    dela vale sem o comando humano correspondente.
    """

    __tablename__ = "chat_turns"
    __table_args__ = (UniqueConstraint("session_id", "sequence", name="uq_chat_turn_sequence"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(128), index=True)
    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.id"), index=True)
    session_id: Mapped[str] = mapped_column(ForeignKey("chat_sessions.id"), index=True)
    sequence: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(16), default="QUEUED")
    question_text: Mapped[str] = mapped_column(Text)
    anchor_refs_json: Mapped[dict[str, list[str]]] = mapped_column(JSON, default=dict)
    """`{"reading_ids": [...], "proposal_ids": [...]}` — o que o profissional apontou."""
    answer_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    provider: Mapped[str | None] = mapped_column(String(40), nullable=True)
    model_id: Mapped[str | None] = mapped_column(String(160), nullable=True)
    prompt_version: Mapped[str | None] = mapped_column(String(80), nullable=True)
    input_digest: Mapped[str | None] = mapped_column(String(64), nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    estimated_cost_usd: Mapped[str | None] = mapped_column(String(24), nullable=True)
    """Texto decimal canônico: `Decimal` não tem bind nativo em SQLite e float perde centavo."""
    raw_response_ref: Mapped[str | None] = mapped_column(String(512), nullable=True)
    failure_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    requested_by: Mapped[str] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )


class AuditRecord(Base):
    __tablename__ = "audit_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(128), index=True)
    actor_id: Mapped[str] = mapped_column(String(128))
    action: Mapped[str] = mapped_column(String(64))
    resource_type: Mapped[str] = mapped_column(String(64))
    resource_id: Mapped[str] = mapped_column(String(36))
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )


class IdempotencyRecord(Base):
    __tablename__ = "idempotency_records"
    __table_args__ = (
        UniqueConstraint("tenant_id", "operation", "key", name="uq_idempotency_scope"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(128), index=True)
    operation: Mapped[str] = mapped_column(String(80))
    key: Mapped[str] = mapped_column(String(255))
    request_hash: Mapped[str] = mapped_column(String(64))
    response_json: Mapped[dict[str, Any]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )


class Database:
    def __init__(self, database_url: str) -> None:
        connect_args: dict[str, Any] = {}
        engine_kwargs: dict[str, Any] = {"future": True}
        if database_url.startswith("sqlite"):
            connect_args["check_same_thread"] = False
            if database_url.endswith(":memory:"):
                engine_kwargs["poolclass"] = StaticPool
        self.engine = create_engine(database_url, connect_args=connect_args, **engine_kwargs)
        if database_url.startswith("sqlite"):
            # SQLite ignores foreign keys unless asked, which would let an insert ordering
            # bug pass locally and fail only against PostgreSQL.
            @event.listens_for(self.engine, "connect")
            def _enforce_foreign_keys(connection: Any, _record: Any) -> None:
                cursor = connection.cursor()
                cursor.execute("PRAGMA foreign_keys=ON")
                cursor.close()

        self.sessions = sessionmaker(self.engine, expire_on_commit=False)

    def create_schema(self) -> None:
        # `create_all` já é aditivo para TABELA nova (`chat_sessions`/`chat_turns` entram
        # por aqui, sem DDL própria); os blocos abaixo existem para COLUNA nova em tabela
        # que um volume local antigo já tem.
        Base.metadata.create_all(self.engine)
        # The local scaffold predates a migration runner. Keep this additive
        # upgrade explicit so existing local Docker volumes can adopt the new
        # job metadata without reset or destructive DDL.
        existing_columns = {column["name"] for column in inspect(self.engine).get_columns("jobs")}
        missing_columns = {
            "page_count": "INTEGER",
            "failure_code": "VARCHAR(80)",
        }
        with self.engine.begin() as connection:
            for name, definition in missing_columns.items():
                if name not in existing_columns:
                    connection.execute(text(f"ALTER TABLE jobs ADD COLUMN {name} {definition}"))
        review_columns = {
            column["name"] for column in inspect(self.engine).get_columns("review_revisions")
        }
        review_additions = {
            "proposals_json": "JSON",
            "calibration_json": "JSON",
            "proposal_decisions_json": "JSON",
            "trace_acceptance_json": "JSON",
            "required_criteria_texts_json": "JSON",
        }
        with self.engine.begin() as connection:
            for name, definition in review_additions.items():
                if name not in review_columns:
                    connection.execute(
                        text(f"ALTER TABLE review_revisions ADD COLUMN {name} {definition}")
                    )
        approval_columns = {
            column["name"] for column in inspect(self.engine).get_columns("approvals")
        }
        with self.engine.begin() as connection:
            if "approval_json" not in approval_columns:
                connection.execute(text("ALTER TABLE approvals ADD COLUMN approval_json JSON"))
            # A local volume created before the constraint may hold duplicate versions; the
            # index creation fails loudly instead of hiding a scene-versioning conflict.
            connection.execute(
                text(
                    "CREATE UNIQUE INDEX IF NOT EXISTS uq_scene_version "
                    "ON scene_revisions (job_id, version)"
                )
            )
        decision_columns = {
            column["name"] for column in inspect(self.engine).get_columns("review_decisions")
        }
        decision_additions = {
            "decision_id": "VARCHAR(32)",
            "rectifies_decision_id": "VARCHAR(32)",
        }
        with self.engine.begin() as connection:
            for name, definition in decision_additions.items():
                if name not in decision_columns:
                    connection.execute(
                        text(f"ALTER TABLE review_decisions ADD COLUMN {name} {definition}")
                    )
            # Uma revisão de leitura registra um ato por leitura; duplicata num volume
            # local antigo falha alto aqui em vez de esconder decisão concorrente.
            connection.execute(
                text(
                    "CREATE UNIQUE INDEX IF NOT EXISTS uq_review_decision_reading "
                    "ON review_decisions (review_revision_id, reading_id)"
                )
            )
        authorization_columns = {
            column["name"] for column in inspect(self.engine).get_columns("ai_processing_consents")
        }
        authorization_additions = {
            "authorization_source": "VARCHAR(32)",
            "entitlement_id": "VARCHAR(36)",
            "agreement_reference": "VARCHAR(128)",
        }
        with self.engine.begin() as connection:
            for name, definition in authorization_additions.items():
                if name not in authorization_columns:
                    connection.execute(
                        text(f"ALTER TABLE ai_processing_consents ADD COLUMN {name} {definition}")
                    )

    def session(self) -> Generator[Session, None, None]:
        database_session = self.sessions()
        try:
            yield database_session
        finally:
            database_session.close()
