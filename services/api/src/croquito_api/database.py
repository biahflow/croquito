"""Persistência transacional tenant-scoped para o primeiro fluxo SaaS.

Toda tabela de DADO DE CLIENTE tem `tenant_id`, e o isolamento é conferido no mesmo `where`
do `id`. A única exceção é `ReferenceCatalogRecord`, o acervo de catálogos públicos da
plataforma: ela não guarda dado de cliente, e a razão está escrita na docstring dela
(ADR-0047, decisão 1). Tabela global nova exige ADR próprio — a ausência de `tenant_id`
nunca é detalhe de implementação.
"""

from __future__ import annotations

from collections.abc import Generator
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    DateTime,
    Float,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    PrimaryKeyConstraint,
    String,
    Text,
    UniqueConstraint,
    create_engine,
    event,
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


class JobStageEventRecord(Base):
    """Append-only history of every `jobs.stage`/`status` transition (F-031 T1).

    `jobs.stage`/`status` são sobrescritos por `UPDATE`, e sem esta tabela o cycle time
    por etapa é irreconstruível: uma vez sobrescrito, o valor anterior desaparece. Cada
    linha aqui é gravada na MESMA transação do `UPDATE`/`INSERT` que muda o job —
    `from_stage`/`from_status` vêm de uma leitura do job feita antes da mudança, na mesma
    conexão, nunca de suposição; ver `services/worker/src/croquito_worker/local_queue.py`.

    `source` distingue o evento inicial gravado pela API na criação do job (`"api"`,
    `from_stage`/`from_status` sempre `None`) das transições que o worker grava a cada
    `UPDATE jobs SET status/stage` (`"worker"`).
    """

    __tablename__ = "job_stage_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(128), index=True)
    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.id"), index=True)
    from_stage: Mapped[str | None] = mapped_column(String(32), nullable=True)
    to_stage: Mapped[str] = mapped_column(String(32))
    from_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    to_status: Mapped[str] = mapped_column(String(32))
    source: Mapped[str] = mapped_column(String(16))
    failure_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )


class DomainEventRecord(Base):
    """Outbox transacional dos eventos de domínio publicados para fora (F-031 T2, ADR-0042).

    Cada linha é gravada na MESMA transação do fato que a produziu — o ato humano na API,
    o `UPDATE` de stage no worker, a chamada de provider concluída. É essa co-transação
    que faz a garantia dos dois lados: nada é publicado sem ter acontecido (transação
    abortada leva o evento junto) e nada acontece sem ficar publicável (o commit do fato
    já deixou o evento durável). Publicar direto do request path perderia as duas.

    `published_at IS NULL` é a fila de trabalho do relay
    (`croquito-demo publish-events`), e o índice existe por causa dessa varredura. A marca
    é gravada DEPOIS da publicação: reentrega é o modo de falha aceito (at-least-once, o
    consumidor deduplica por `event_id`), perda não é.

    `job_id` é `String(36)` SEM chave estrangeira, de propósito e diferente de
    `JobStageEventRecord`: o outbox é registro de um fato já ocorrido, e não filho do job.
    Eventos de medição e de orçamento nascem sem job nenhum, e uma FK faria a retenção do
    job decidir se um fato publicado pode continuar existindo — o histórico externo já
    consumido não pode depender do ciclo de vida da entidade que o originou.

    `id` É o `event_id` do envelope: um só identificador para a linha e para a mensagem,
    porque duplicar isso abriria a possibilidade de eles divergirem numa reentrega.
    """

    __tablename__ = "domain_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(128), index=True)
    event_type: Mapped[str] = mapped_column(String(80), index=True)
    job_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    payload_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    """Só escalares e `None`, conferidos por `croquito_core.events.build_domain_event`.

    Nunca imagem, texto de cota, conteúdo de documento, token ou URL assinada: a mesma
    política dos logs vale aqui, e a conferência é de FORMA (nada aninhado atravessa)."""
    published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
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


class TenantJourneyEntitlementRecord(Base):
    """Contractual authorization for one tenant to open one journey (F-034).

    Deliberately the same shape as `TenantAiProcessingEntitlementRecord`: this is the same
    kind of fact — a durable commercial decision, with who authorized it and when — and the
    platform screen that will administer it (fatia 2) is the same screen. The only
    difference is the `journey` discriminator, which makes the uniqueness a pair.

    Only read while the environment declares that journey `pilot`; `enabled` and `disabled`
    never reach this table.
    """

    __tablename__ = "tenant_journey_entitlements"
    __table_args__ = (
        UniqueConstraint("tenant_id", "journey", name="uq_journey_entitlement_tenant_journey"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(128), index=True)
    journey: Mapped[str] = mapped_column(String(16))
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


class ReferenceCatalogRecord(Base):
    """Catálogo público de referência publicado pela plataforma — **sem `tenant_id`**.

    A ausência é a decisão 1 do ADR-0047, não esquecimento: esta é a primeira e, por
    enquanto, a única tabela do projeto sem coluna de tenant. Uma tabela pública de preços
    **não tem dono** — SINAPI, SICRO e o catálogo do SCO são documentos publicados, iguais
    byte a byte para todo cliente. Replicá-los por tenant guardaria N cópias idênticas de um
    documento público para satisfazer um invariante que existe para proteger dado PRIVADO.

    A condição que sustenta a ausência está escrita, e é ela que qualquer mudança futura
    tem de reler: **nenhuma coluna aqui deriva de conteúdo de cliente**. Tudo o que entra
    vem de um arquivo que o operador da plataforma publicou — `origin`, `reference_month`,
    `source_sha256` e `entry_count` são lidos de DENTRO do `catalog.json`, e o único texto
    escrito à mão é o nome de exibição, digitado pelo operador. Nada aqui é derivado de
    prancha, levantamento, orçamento ou rodada de cliente algum. O teste que verifica essa
    condição é parte da feature (`tests/api/test_reference_catalogs.py`); acrescentar coluna
    que a viole é decisão de arquitetura, e exige ADR próprio.

    Cada publicação é imutável e endereçada pelo digest do arquivo (`object_sha256`), que é
    único: republicar o mesmo conteúdo é recusado, e data-base nova é entrada NOVA. Nunca há
    atualização no lugar — sobrescrever mudaria preço para todos os tenants ao mesmo tempo,
    inclusive em rodadas já montadas (ADR-0047 decisão 3, ADR-0027 decisão 4).

    Retirar de circulação carimba `status` e `withdrawn_at`; a linha e o objeto continuam
    existindo, porque uma rodada antiga ainda os referencia.
    """

    __tablename__ = "reference_catalogs"
    __table_args__ = (UniqueConstraint("object_sha256", name="uq_reference_catalog_object"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    display_name: Mapped[str] = mapped_column(String(200))
    """Único valor DIGITADO: o nome que a escolha exibe. Origem, data-base e contagem vêm do
    arquivo justamente para que o rótulo não possa discordar do conteúdo."""
    origin: Mapped[str] = mapped_column(String(16))
    reference_month: Mapped[str] = mapped_column(String(7))
    object_sha256: Mapped[str] = mapped_column(String(64))
    """Digest dos BYTES do `catalog.json` publicado; é ele que endereça o objeto no store."""
    source_sha256: Mapped[str] = mapped_column(String(64))
    """Digest do arquivo de ORIGEM (`.xlsx`, `.DBF`) que o importador leu, carimbado por ele
    dentro do catálogo. Não é o mesmo que `object_sha256`, e a distinção é a mesma que a
    `CascadeEntry` já faz: um confere a integridade do objeto lido, o outro é a identidade
    da fonte que a decisão de código cita."""
    entry_count: Mapped[int] = mapped_column(Integer)
    object_key: Mapped[str] = mapped_column(String(512))
    """Chave do objeto sob o prefixo do acervo, FORA de `tenants/` (ADR-0047 decisão 6).
    Nenhuma rota assina URL dela: o cliente escolhe a tabela, o servidor é quem a lê."""
    status: Mapped[str] = mapped_column(String(16), default="AVAILABLE")
    """``AVAILABLE`` | ``WITHDRAWN``. Retirar não apaga."""
    published_by: Mapped[str] = mapped_column(String(128))
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    withdrawn_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


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
    declared_chains_json: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    """Cadeias de cotas que uma pessoa DECLAROU partilharem o mesmo total.

    Guarda só a declaração (`chain_id`, `total_id`, `part_ids`, autoria e instante); o
    resultado da conferência é recomputado contra o pacote corrente a cada leitura, para
    que a correção de uma leitura participante apareça como cadeia vencida em vez de
    continuar afirmando um fechamento que já não existe.
    """
    confidence_shadow_json: Mapped[dict[str, Any]] = mapped_column(
        JSON, default=dict, server_default=text("'{}'")
    )
    """O que TERIA sido auto-decidido em cada threshold da grade — nunca uma decisão.

    Ao contrário de `declared_chains_json`, aqui o RESULTADO é gravado: um shadow vale
    por ser o que o pipeline teria feito NAQUELE instante, com aquele pacote e aqueles
    candidatos. Recomputá-lo depois compararia a decisão humana de ontem com o score de
    hoje, e é justamente essa comparação que a calibração não pode fazer.

    `server_default` (migração `0007`) porque o caminho de escrita do worker lista as
    colunas uma a uma: sem ele, um INSERT que não conhece esta coluna quebraria.
    """
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
    interaction_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    """Touch time AUTORRELATADO pela tela que produziu esta revisão (F-031 T4).

    Telemetria observacional, nunca dado de negócio: `NULL` quer dizer "não medido" —
    cliente antigo, aba fechada antes do envio, valor absurdo descartado no payload — e
    jamais "zero". Nada de geometria, decisão ou aprovação depende deste número, e ele
    não entra em nenhum portão; some da conta e a conta continua declarada.
    """
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
    unapplied_readings_json: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    """Cada leitura não aplicada com a CAUSA declarada no ponto do descarte (F-025).

    Fica ao lado de ``unapplied_reading_ids_json``, que continua sendo a lista de ids na
    mesma ordem: o campo antigo é contrato publicado e não muda de forma."""
    contested_spans_json: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    """Vãos disputados por duas ou mais leituras confirmadas; diagnóstico, nunca portão."""
    applied_spans_json: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    """Âncoras em metros de cada cota aplicada, no frame CAD da prancha."""
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


class ValuationRoundRecord(Base):
    """Raiz da rodada de medição de obra (ADR-0028 D1), escopada por tenant.

    Deliberadamente **sem** chave estrangeira para ``projects``: a fronteira do contexto
    delimitado da medição (ADR-0016) vale também no modelo relacional, e a obra permanece
    atributo da rodada (``worksite_key``/``worksite_name``), não entidade própria (D8).

    Catálogo e prancha entram por referência ao object store, nunca por conteúdo: o
    catálogo real tem megabytes e o índice de embeddings dezenas deles, e a regra de blobs
    do D2 manda o binário para o store com digest e metadado no banco.
    """

    __tablename__ = "valuation_rounds"
    __table_args__ = (
        # Índice da listagem com cursor opaco (`GET /v1/valuation-rounds`): o desempate por
        # `id` faz parte da chave porque duas rodadas podem nascer no mesmo instante.
        Index("ix_valuation_rounds_tenant_created", "tenant_id", "created_at", "id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(128), index=True)
    worksite_key: Mapped[str] = mapped_column(String(64))
    worksite_name: Mapped[str] = mapped_column(String(120))
    reference_label: Mapped[str] = mapped_column(String(120))
    period_number: Mapped[int] = mapped_column(Integer)
    """O número da medição; atributo da rodada, e não da rota que constrói o cálculo."""
    address: Mapped[str | None] = mapped_column(String(200), nullable=True)
    contract_label: Mapped[str | None] = mapped_column(String(120), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="OPEN")
    version: Mapped[int] = mapped_column(Integer, default=1)
    """Contador ÚNICO de toda a cadeia da rodada (D3): takeoff, códigos, boletim e dossiê
    pertencem à mesma cadeia causal, e só ato humano o incrementa. Artefato derivado
    persistido sem decisão humana não avança esta versão."""
    catalog_upload_id: Mapped[str | None] = mapped_column(ForeignKey("uploads.id"), nullable=True)
    """Upload do cliente que trouxe o catálogo, quando houve um.

    `NULL` desde a F-036: a rodada aberta a partir de um orçamento assinado instala o
    catálogo que o orçamento usou, e esse arquivo pode ter vindo do **acervo da plataforma**
    (F-037), onde não existe upload do cliente para citar. É proveniência, não conteúdo — o
    que a rodada precisa para LER o catálogo são as duas colunas abaixo, que seguem
    obrigatórias."""
    catalog_object_key: Mapped[str] = mapped_column(String(512))
    catalog_source_sha256: Mapped[str] = mapped_column(String(64))
    """O catálogo é instalado na CRIAÇÃO e é imutável na rodada, por isso estas duas colunas
    são obrigatórias: trocar de catálogo é abrir rodada nova (API Contract, "Medição de
    obra").  Isso NÃO torna morto o código `CATALOG_REQUIRED` do ADR-0028 D4 — ele nomeia a
    precondição de o catálogo INSTALADO não estar utilizável agora (objeto fora do store,
    digest divergente), que é falha de configuração e não de cadeia.  Rodada sem a coluna
    preenchida não existe por construção, e afrouxar isto depois seria `ALTER` numa linha
    forward-only: se um dia a rodada precisar nascer sem catálogo, é decisão de contrato."""

    catalog_summary_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    """Resumo pequeno do catálogo instalado (contagem de entradas, referência); o catálogo
    inteiro fica no object store e nunca nesta coluna."""

    estimate_round_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    """Rodada de ORÇAMENTO de origem (F-036, ADR-0048). Sem chave estrangeira, pelo mesmo
    motivo que esta tabela não tem FK para ``projects``: a fronteira do contexto delimitado
    (ADR-0016) vale também no modelo relacional."""
    estimate_digest: Mapped[str | None] = mapped_column(String(64), nullable=True)
    """Digest do conteúdo **assinado** contra o qual esta obra é medida. É ele, e não o id da
    rodada, que responde "medi contra o quê": remontar o orçamento depois torna a assinatura
    caduca e não alcança medição já aberta (ADR-0048, decisão 6)."""
    contract_workbook_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    """Consolidado contratual derivado do orçamento assinado, gravado na abertura e imutável
    na rodada — como o catálogo instalado (ADR-0048, decisão 7).

    ``None`` nas três colunas é o estado de sempre: rodada aberta sem orçamento de origem, que
    continua conferindo o boletim contra o consolidado FABRICADO por
    ``bulletin_export_contract``, com os seis guardrails inertes que aquele docstring declara.
    A distinção entre os dois regimes de conferência é visível na leitura da rodada, e é
    exigência da decisão 9 do ADR-0048 — as duas não podem parecer iguais."""

    plate_upload_id: Mapped[str | None] = mapped_column(ForeignKey("uploads.id"), nullable=True)
    plate_object_key: Mapped[str | None] = mapped_column(String(512), nullable=True)
    plate_source_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    plate_page_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    extraction_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    extraction_status: Mapped[str] = mapped_column(String(16), default="idle")
    """`idle` | `queued` | `running` | `done` | `failed`. O comando de fila da extração paga
    (D7) é estado da raiz, no precedente de `ExportArtifactRecord.status`, e não tabela
    própria: há no máximo uma extração em voo por rodada."""
    extraction_failure_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    extraction_requested_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    extraction_updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_by: Mapped[str] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )


class ValuationRoundRevisionRecord(Base):
    """Estado imutável da cadeia de medição numa versão da rodada (ADR-0028 D2).

    Append-only: mutação cria linha nova e nenhuma coluna JSON é atualizada no lugar. O
    conteúdo dessas colunas é artefato de trabalho do cliente — quantitativo, código,
    preço, memória de cálculo — e **nunca** é copiado para log de aplicação; o que pode ser
    registrado é id opaco, etapa, digest e contagem.
    """

    __tablename__ = "valuation_round_revisions"
    __table_args__ = (UniqueConstraint("round_id", "version", name="uq_valuation_round_version"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(128), index=True)
    round_id: Mapped[str] = mapped_column(ForeignKey("valuation_rounds.id"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    parent_revision_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    takeoff_packet_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    takeoff_registration_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    """Relatório do registro fino de bbox: é ele que separa âncora `registered` de `raw`."""
    code_suggestions_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    code_assignments_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    valuation_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    amendment_dossier_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    extraction_lineage_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    artifact_refs_json: Mapped[dict[str, str]] = mapped_column(JSON, default=dict)
    """Chaves de objeto sob o prefixo do tenant (prancha, overlay); nunca URL assinada."""
    artifact_digests_json: Mapped[dict[str, str]] = mapped_column(JSON, default=dict)
    created_by: Mapped[str] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )


class EstimateRoundRecord(Base):
    """Raiz da rodada de ORÇAMENTO-BASE (pré-licitação, ADR-0038), escopada por tenant.

    Espelho de ``ValuationRoundRecord`` com a diferença que define a fronteira do ADR-0027:
    aqui não há contrato, não há período e não há saldo, porque nenhum deles existe antes
    da licitação. As duas colunas que a medição usa para nomeá-los (``period_number`` e
    ``contract_label``) ficam de fora por isso — carregá-las obrigaria a rodada a declarar
    um número de medição e um contrato que ela não tem, e uma coluna que só pode ser
    preenchida com mentira é pior do que uma coluna ausente.

    No lugar do catálogo ÚNICO da medição entra ``catalog_cascade_json``: a cascata de
    fontes de preço, ORDENADA, com a ordem sendo o dado que decide a precificação
    (ADR-0027). Cada entrada referencia o objeto no store por digest — catálogo é blob e
    blob nunca entra em coluna de banco (ADR-0028 D2).
    """

    __tablename__ = "estimate_rounds"
    __table_args__ = (
        # Espelho de `ix_valuation_rounds_tenant_created`: índice da listagem com cursor
        # opaco, com `id` na chave porque duas rodadas podem nascer no mesmo instante.
        Index("ix_estimate_rounds_tenant_created", "tenant_id", "created_at", "id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(128), index=True)
    worksite_key: Mapped[str] = mapped_column(String(64))
    worksite_name: Mapped[str] = mapped_column(String(120))
    reference_label: Mapped[str] = mapped_column(String(120))
    """Rótulo livre da rodada, o que a listagem mostra. Não é período nem contrato."""
    address: Mapped[str | None] = mapped_column(String(200), nullable=True)
    target_amount: Mapped[str | None] = mapped_column(String(32), nullable=True)
    """Teto de verba da rodada, `Decimal` exato como TEXTO — a mesma disciplina do BDI e da
    quantidade do takeoff (ADR-0038, ADR-0040 decisão 1). Ausência é "sem teto"; zero e
    negativo são recusados na validação de aplicação (`parse_target_amount`) e nunca
    chegam a esta coluna. O `Estimate` montado não ganha campo novo por causa dele: o
    orçamento continua puro e recomputável, e o teto é o contexto de trabalho da rodada
    (ADR-0040 decisão 1)."""
    target_label: Mapped[str | None] = mapped_column(String(120), nullable=True)
    """Rótulo livre da origem da verba (ex.: a demanda da Relação de Praças). Opcional
    mesmo quando há teto declarado."""
    pricing_regime: Mapped[str | None] = mapped_column(String(32), nullable=True)
    """Regime de preço declarado para a rodada (ADR-0045). `NULL` é o estado de sempre —
    pré-licitação, cascata livre —, e é AUSÊNCIA, não valor: "pré-licitação" nunca é
    gravado aqui, porque escrevê-lo faria a falta de uma declaração humana parecer uma.

    O único valor gravável é `contracted_demand`: a demanda orçada dentro de um contrato
    guarda-chuva já licitado, que tem a FORMA do orçamento-base e a REGRA da obra licitada
    — só a tabela contratual vale. Declarado, restringe a cascata a `sco` na INSTALAÇÃO
    (`ensure_source_installable`), e é mão única: não há caminho de volta, porque desfazer
    o regime devolveria à rodada a permissão de instalar a fonte que ela já foi impedida
    de instalar. É dado da RODADA, como o teto e o BDI; o `Estimate` não ganha campo por
    causa dele."""
    status: Mapped[str] = mapped_column(String(32), default="OPEN")
    version: Mapped[int] = mapped_column(Integer, default=1)
    """Contador ÚNICO de toda a cadeia da rodada, como o da medição (ADR-0028 D3): só ato
    humano o incrementa, e artefato derivado persistido sem decisão humana não o move."""
    catalog_cascade_json: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    """Cascata ORDENADA de fontes de preço; a posição é a precedência declarada.

    Cada entrada é ``{upload_id, object_key, source_sha256, origin, reference_month,
    source_label, summary}``. A lista nasce vazia — a rodada de orçamento abre antes de
    ter fonte, ao contrário da rodada de medição, que nasce com catálogo por construção —
    e cresce por ato humano (``POST .../catalogs``). Uma origem só pode aparecer uma vez:
    duas fontes da mesma origem fariam "o preço veio da EMOP" deixar de identificar de
    qual arquivo ele veio (``ESTIMATE_CASCADE_ORIGIN_DUPLICATE``)."""
    plate_upload_id: Mapped[str | None] = mapped_column(ForeignKey("uploads.id"), nullable=True)
    plate_object_key: Mapped[str | None] = mapped_column(String(512), nullable=True)
    plate_source_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    plate_page_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    extraction_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    extraction_status: Mapped[str] = mapped_column(String(16), default="idle")
    """`idle` | `queued` | `running` | `done` | `failed`, como na medição: há no máximo uma
    extração em voo por rodada, e ela é estado da raiz e não tabela própria."""
    extraction_failure_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    extraction_requested_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    extraction_updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_by: Mapped[str] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )


class EstimateRoundRevisionRecord(Base):
    """Estado imutável da cadeia do orçamento-base numa versão da rodada.

    Espelho append-only de ``ValuationRoundRevisionRecord``: mutação cria linha nova e
    nenhuma coluna JSON é atualizada no lugar. Sem ``valuation_json`` nem
    ``amendment_dossier_json`` — boletim e dossiê de aditivo são artefatos da obra
    LICITADA e não existem deste lado da fronteira (ADR-0027).

    O conteúdo dessas colunas é artefato de trabalho do cliente — quantitativo, código,
    preço, memória de cálculo — e **nunca** é copiado para log de aplicação.
    """

    __tablename__ = "estimate_round_revisions"
    __table_args__ = (UniqueConstraint("round_id", "version", name="uq_estimate_round_version"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(128), index=True)
    round_id: Mapped[str] = mapped_column(ForeignKey("estimate_rounds.id"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    parent_revision_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    takeoff_packet_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    takeoff_registration_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    """Relatório do registro fino de bbox: é ele que separa âncora `registered` de `raw`."""
    code_suggestions_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    code_assignments_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    estimate_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    """O `Estimate` montado: linhas com proveniência, BDI declarado e memória de cálculo."""
    estimate_built_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    """Subject de quem MONTOU o orçamento da cabeça, carregado adiante pelos atos seguintes.

    Não é ``created_by``, e a diferença é a razão de a coluna existir (ADR-0046, decisão 6):
    ``created_by`` é de quem fez o ÚLTIMO ato, então depois de uma aprovação ele já não é
    quem montou — e é exatamente contra quem montou que a rota de aprovação compara o
    ``sub`` do JWT para recusar auto-aprovação. Descobrir o autor comparando a revisão com a
    pai seria arqueologia numa cadeia append-only, que a mesma decisão recusou.

    ``NULL`` é "a rodada ainda não tem orçamento montado" — e também toda revisão anterior a
    esta coluna, cuja montagem não registrou autor. Aprovar essas exige remontar; nada aqui
    inventa um autor que ninguém gravou.
    """
    extraction_lineage_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    artifact_refs_json: Mapped[dict[str, str]] = mapped_column(JSON, default=dict)
    """Chaves de objeto sob o prefixo do tenant (prancha, overlay, planilha publicada);
    nunca URL assinada."""
    artifact_digests_json: Mapped[dict[str, str]] = mapped_column(JSON, default=dict)
    created_by: Mapped[str] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )


class SurveyRecord(Base):
    """Levantamento de campo sincronizado pela PWA do técnico (F-032, ADR-0043).

    A raiz guarda o ÚLTIMO pacote consolidado (``snapshot_json``) e o contador que o
    aplicativo usa como guarda otimista; o histórico do outbox vive em
    ``survey_operation_records``, e nenhuma linha dele é editada ou apagada — resolver
    conflito é operação nova, não sobrescrita.

    ``snapshot_json`` é o ``SurveyPacket`` (``croquito_core.field``) SEM ``operations``:
    o histórico já tem tabela própria e duplicá-lo aqui faria duas fontes divergirem na
    primeira retransmissão. O conteúdo é trabalho de campo do cliente — coordenadas,
    medidas, notas — e **nunca** é copiado para log de aplicação.

    A chave primária é ``(tenant_id, id)``, e não ``id`` sozinho, porque ``id`` é gerado
    NO APARELHO: uma chave global faria o identificador de um tenant recusar o de outro, e
    o app já persistiu id que não é UUID (``survey-local``, do scaffold da fatia 0), onde a
    colisão entre tenants deixa de ser hipótese remota. Isolamento de tenant é invariante
    do banco, não consequência de sorte no gerador de id.
    """

    __tablename__ = "survey_records"
    __table_args__ = (PrimaryKeyConstraint("tenant_id", "id", name="pk_survey_records"),)

    id: Mapped[str] = mapped_column(String(36))
    """Id gerado pelo aparelho (``crypto.randomUUID``), não pelo servidor: o levantamento
    nasce offline e precisa de identidade antes de existir rede."""
    tenant_id: Mapped[str] = mapped_column(String(128))
    """Sem ``index=True``: a chave primária já começa por ele, e um índice extra na mesma
    coluna líder custaria escrita sem servir a nenhuma leitura que a PK não sirva."""
    name: Mapped[str] = mapped_column(String(200))
    order_ref: Mapped[str | None] = mapped_column(String(200), nullable=True)
    """Ordem de levantamento que originou o survey; ausente no dado legado do app."""
    status: Mapped[str] = mapped_column(String(16), default="OPEN")
    """``OPEN`` | ``COMPLETED``. Concluído não aceita operação nova (conflito 6b)."""
    version: Mapped[int] = mapped_column(Integer, default=1)
    """Só lote válido de operações o incrementa; é a ``base_version`` da conclusão."""
    snapshot_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )


class SurveyOperationRecord(Base):
    """Uma operação do outbox do aparelho, gravada uma única vez.

    A chave primária é ``(tenant_id, operation_id)``: reenvio do mesmo lote é fato normal
    numa rede de campo, e a unicidade natural do ``operation_id`` é o que torna o
    reconhecimento idempotente sem inventar uma chave de deduplicação paralela — mas ele
    também nasce no aparelho, então a unicidade vale DENTRO do tenant, que é como o ack já
    é consultado.

    ``(tenant_id, survey_id, device_id, seq)`` é único porque a ordem por aparelho é o
    contrato de sincronização: dois lotes concorrentes disputam a mesma posição e o
    perdedor recebe conflito, nunca uma gravação fora de ordem. O ``tenant_id`` entra na
    chave pela mesma razão que entra na PK — sem ele, dois tenants com o mesmo
    ``survey_id`` disputariam a mesma posição de sequência.
    """

    __tablename__ = "survey_operation_records"
    __table_args__ = (
        PrimaryKeyConstraint("tenant_id", "id", name="pk_survey_operation_records"),
        ForeignKeyConstraint(
            ["tenant_id", "survey_id"],
            ["survey_records.tenant_id", "survey_records.id"],
            name="fk_survey_operation_records_survey",
        ),
        UniqueConstraint(
            "tenant_id", "survey_id", "device_id", "seq", name="uq_survey_operation_seq"
        ),
    )

    id: Mapped[str] = mapped_column(String(64))
    tenant_id: Mapped[str] = mapped_column(String(128))
    """Sem ``index=True``: a PK já começa por ele (ver ``SurveyRecord.tenant_id``)."""
    survey_id: Mapped[str] = mapped_column(String(36), index=True)
    device_id: Mapped[str] = mapped_column(String(128))
    seq: Mapped[int] = mapped_column(Integer)
    type: Mapped[str] = mapped_column(String(100))
    payload_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )


class SurveyMediaRecord(Base):
    """Uma foto ou áudio do levantamento: metadado e digest aqui, bytes no object store.

    A regra da prancha 6a — metadado antes da mídia — vive na rota: o digest precisa
    estar referenciado no pacote consolidado antes de ganhar URL assinada. ``object_key``
    é derivado de tenant, survey e digest, e por isso é único; ``(tenant_id, survey_id,
    sha256)`` também, porque a mesma mídia ancorada duas vezes é um arquivo só.

    Aqui o ``id`` continua SIMPLES: ele é gerado pelo servidor (UUIDv7), não pelo
    aparelho, e por isso não carrega o problema de colisão que fez a raiz e as operações
    ganharem chave composta.
    """

    __tablename__ = "survey_media_records"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "survey_id"],
            ["survey_records.tenant_id", "survey_records.id"],
            name="fk_survey_media_records_survey",
        ),
        UniqueConstraint("tenant_id", "survey_id", "sha256", name="uq_survey_media_digest"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(128), index=True)
    survey_id: Mapped[str] = mapped_column(String(36), index=True)
    sha256: Mapped[str] = mapped_column(String(64))
    mime_type: Mapped[str] = mapped_column(String(100))
    byte_size: Mapped[int] = mapped_column(Integer)
    object_key: Mapped[str] = mapped_column(String(512), unique=True)
    status: Mapped[str] = mapped_column(String(16), default="PRESIGNED")
    """``PRESIGNED`` | ``CONFIRMED``. A transição é o que publica o comando de análise."""
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )


class Database:
    def __init__(self, database_url: str) -> None:
        connect_args: dict[str, Any] = {}
        # `pool_pre_ping` custa um SELECT 1 na conexão reciclada e evita o erro que o
        # Postgres gerenciado produz quando o compute suspende por ociosidade: a conexão
        # no pool continua parecendo viva e só falha na primeira query real, já dentro do
        # request. Descartar de graça é mais barato que traduzir esse erro em toda rota.
        engine_kwargs: dict[str, Any] = {"future": True, "pool_pre_ping": True}
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
        """Cria o schema do zero: serve a suíte de testes e banco novo, nada além disso.

        Evoluir banco que já existe é trabalho do runner de migrations
        (`croquito_api.bootstrap`, ADR-0029). Este método não altera tabela existente: em
        banco desatualizado ele não faz nada, e é o runner que detecta e recusa esse caso.
        """
        Base.metadata.create_all(self.engine)

    def session(self) -> Generator[Session, None, None]:
        database_session = self.sessions()
        try:
            yield database_session
        finally:
            database_session.close()
