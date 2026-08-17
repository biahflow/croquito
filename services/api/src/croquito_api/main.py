"""API de lifecycle: autentica, persiste e orquestra; não processa PDFs no request."""

from __future__ import annotations

import base64
import hashlib
import json
import math
import re
from collections.abc import Generator, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Annotated, Any, Final, Literal, cast
from uuid import UUID

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError
from fastapi import Depends, FastAPI, Header, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from starlette.exceptions import HTTPException as StarletteHTTPException

from croquito_api.auth import OidcAuthenticator, Principal, require_principal
from croquito_api.config import ApiSettings
from croquito_api.database import (
    AiProcessingAuthorizationRecord,
    ApprovalRecord,
    AuditRecord,
    ChatSessionRecord,
    ChatTurnRecord,
    Database,
    ExportArtifactRecord,
    IdempotencyRecord,
    JobRecord,
    ProjectRecord,
    ProposalDecisionRecord,
    ReviewDecisionRecord,
    ReviewRevisionRecord,
    RevisionRecord,
    TenantAiProcessingEntitlementRecord,
    TraceSolveRecord,
    UploadRecord,
)
from croquito_api.pubsub_queue import PubSubProcessingQueue, QueuePublishError
from croquito_api.storage import ArtifactStore
from croquito_core.errors import DomainValidationError
from croquito_core.ids import new_uuid7
from croquito_core.models import (
    SCENE_SCHEMA_VERSION,
    Entity,
    EntityKind,
    Issue,
    IssueSeverity,
    IssueStatus,
    LayerName,
    Measurement,
    MeasurementKind,
    Precision,
    SceneRevision,
    UnitCode,
)
from croquito_worker.association import AssociationSet
from croquito_worker.criteria import (
    FALLBACK_CRITERION_MESSAGE,
    apply_criteria_declarations,
    criterion_message,
    scope_criteria_issues,
)
from croquito_worker.dimension_annotation import (
    DimensionAnnotationError,
    annotate_note,
    annotate_traced_line,
)
from croquito_worker.proposal_calibration import (
    HUMAN_ACCEPTED_PROPOSAL_SOURCE_TYPE,
    ISOTROPY_TOLERANCE,
    AffineTransform,
    CalibrationAnchor,
    CalibrationError,
    CalibrationTransform,
    approximate_entity_from_proposal,
    matrix_of,
    resolve_calibration,
    revalidate_calibration,
    transform_from_calibration_json,
)
from croquito_worker.providers import ReviewChatOutput
from croquito_worker.rectangle_solver import RectangleSolveRequest, solve_rectangle
from croquito_worker.review import (
    DimensionReading,
    ReadingDecisionBatch,
    ReadingDecisionInput,
    ReadingRectificationBatch,
    ReadingRectificationInput,
    ReadingStatus,
    ReviewPacket,
    SceneApproval,
    apply_reading_decisions,
    rectify_reading_decisions,
)
from croquito_worker.tracing import (
    GENERAL_NOTE_TARGET,
    LEGEND_NOTE_PREFIX,
    DerivedDimensionRequest,
    KeepApartPair,
    TraceAcceptance,
    TraceDetailGroup,
    keep_apart_proposal_ids,
)
from croquito_worker.vision import VisionProposalSet


class ApiModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class HealthResponse(ApiModel):
    status: str


class MetaResponse(ApiModel):
    service: str
    api_version: str
    scene_schema_version: str


#: Tipos que o presign assina, com a extensão que cada um exige no nome do arquivo.
#: O PDF é a prancha e o croqui; o JSON é o catálogo de preços que a rodada de medição
#: instala na criação (ADR-0028 D6 tratou só da prancha e deixou o catálogo sem porta).
#: Um tipo novo aqui é decisão de contrato, não conveniência de rota.
UPLOAD_CONTENT_TYPES: Final[Mapping[str, str]] = {
    "application/pdf": ".pdf",
    "application/json": ".json",
}

PDF_CONTENT_TYPE: Final = "application/pdf"


class PresignUploadRequest(ApiModel):
    filename: str = Field(min_length=1, max_length=255)
    content_type: Literal["application/pdf", "application/json"]
    size_bytes: int = Field(gt=0, le=100_000_000)
    sha256: str = Field(pattern=r"^[a-fA-F0-9]{64}$")


class PresignUploadResponse(ApiModel):
    upload_id: UUID
    object_key: str
    url: str
    headers: dict[str, str]
    expires_at: datetime


class CreateJobRequest(ApiModel):
    upload_id: UUID
    project_name: str = Field(min_length=1, max_length=160)
    default_unit: UnitCode = UnitCode.METRE
    external_ai_consent: bool | None = Field(default=None, deprecated=True)


class SetAiProcessingEntitlementRequest(ApiModel):
    enabled: bool
    agreement_reference: str | None = Field(default=None, min_length=3, max_length=128)


class AiProcessingEntitlementResponse(ApiModel):
    tenant_id: str
    enabled: bool
    agreement_reference: str
    authorized_at: datetime
    revoked_at: datetime | None = None


class JobResponse(ApiModel):
    job_id: UUID
    project_id: UUID
    status: str
    stage: str
    expires_at: datetime
    page_count: int | None = None
    failure_code: str | None = None
    created_at: datetime
    updated_at: datetime


class LatestJobResponse(ApiModel):
    job_id: UUID
    status: str
    stage: str


class ProjectResponse(ApiModel):
    project_id: UUID
    name: str
    default_unit: UnitCode
    status: str
    expires_at: datetime
    latest_job: LatestJobResponse | None = None


class ApproveRequest(ApiModel):
    """Mirrors the SceneApproval contract: every verification is stated, never inferred."""

    revision_id: UUID
    accepted_approximations: set[UUID] = Field(default_factory=set)
    # Dois atos distintos sobre o critério de escopo (ADR-0017): coberto pela cena que se
    # aprova, ou assumido pendente. Nenhum dos dois alcança blocker de geometria.
    covered_criteria: set[str] = Field(default_factory=set)
    acknowledged_criteria: set[str] = Field(default_factory=set)
    source_evidence_checked: Literal[True]
    geometry_checked: Literal[True]
    limitations_acknowledged: Literal[True]
    statement: str = Field(min_length=20, max_length=500)


class AddEntityOperation(ApiModel):
    op: Literal["add_entity"]
    entity: Entity


class AddMeasurementOperation(ApiModel):
    op: Literal["add_measurement"]
    measurement: Measurement


ReviewOperation = Annotated[AddEntityOperation | AddMeasurementOperation, Field(discriminator="op")]


class CreateRevisionRequest(ApiModel):
    base_version: int = Field(ge=1)
    operations: list[ReviewOperation] = Field(min_length=1, max_length=50)
    reason: str = Field(min_length=3, max_length=500)


class ReviewDecisionCommand(ApiModel):
    reading_id: str = Field(pattern=r"^rd_[a-f0-9]{16}$")
    action: Literal["confirm", "correct", "reject"]
    justification: str = Field(min_length=3, max_length=500)
    association_proposal_id: str | None = Field(default=None, pattern=r"^vp_[a-f0-9]{16}$")
    # Declaração explícita de "anotação da folha, não mede elemento" (a tela aérea do
    # Guaxindiba): dispensa a associação SEM afrouxar a regra para cota de verdade.
    annotation: bool = False
    raw_text: str | None = Field(default=None, min_length=1, max_length=200)
    value_si: str | None = Field(default=None, pattern=r"^\d+(?:\.\d+)?$")
    unit: UnitCode | None = None
    kind: MeasurementKind | None = None
    written_decimals: int | None = Field(default=None, ge=0, le=8)
    target_hint: str | None = Field(default=None, min_length=1, max_length=120)


class SubmitReviewDecisionsRequest(ApiModel):
    base_version: int = Field(ge=1)
    decisions: list[ReviewDecisionCommand] = Field(min_length=1, max_length=50)


class RectifyReadingCommand(ApiModel):
    """Correção declarada de uma decisão já registrada.

    Não existe ação `correct` aqui: o desfecho da leitura é `confirm` ou `reject`, e o
    que muda em relação ao registro anterior viaja nos mesmos campos da decisão. O alvo
    é citado nominalmente e a justificativa é obrigatória — quem corrige o registro de
    um profissional escreve por quê.
    """

    reading_id: str = Field(pattern=r"^rd_[a-f0-9]{16}$")
    action: Literal["confirm", "reject"]
    rectifies_decision_id: str = Field(pattern=r"^hd_[a-f0-9]{16}$")
    justification: str = Field(min_length=3, max_length=500)
    # A associação é sempre redeclarada: a tela pré-preenche a vigente, mas o envio é
    # explícito. Nada é herdado em silêncio de uma decisão que está sendo corrigida.
    association_proposal_id: str | None = Field(default=None, pattern=r"^vp_[a-f0-9]{16}$")
    annotation: bool = False
    raw_text: str | None = Field(default=None, min_length=1, max_length=200)
    value_si: str | None = Field(default=None, pattern=r"^\d+(?:\.\d+)?$")
    unit: UnitCode | None = None
    kind: MeasurementKind | None = None
    written_decimals: int | None = Field(default=None, ge=0, le=8)
    target_hint: str | None = Field(default=None, min_length=1, max_length=120)


class RectifyReviewDecisionsRequest(ApiModel):
    base_version: int = Field(ge=1)
    rectifications: list[RectifyReadingCommand] = Field(min_length=1, max_length=50)


class ProposalCalibrationAnchorRequest(ApiModel):
    proposal_id: str = Field(pattern=r"^vp_[a-f0-9]{16}$")
    # Opcional: sem isto o ajuste escolhe a aresta métrica, porque as quatro arestas de
    # um retângulo são indistinguíveis para quem seleciona numa lista.
    entity_id: UUID | None = None
    reversed: bool = False


class CreateProposalCalibrationRequest(ApiModel):
    base_review_version: int = Field(ge=1)
    base_scene_version: int = Field(ge=1)
    anchors: list[ProposalCalibrationAnchorRequest] = Field(min_length=2, max_length=2)
    # Afim por padrão: croqui à mão raramente tem a mesma escala nos dois eixos, e a
    # similaridade simplesmente não tem solução quando as âncoras discordam.
    mode: Literal["similarity", "affine"] = "affine"


class ProposalCalibrationResponse(ApiModel):
    calibration_id: UUID
    scene_revision_id: UUID
    scene_version: int
    anchors: list[ProposalCalibrationAnchorRequest]
    scale_m_per_px: float = Field(gt=0)
    rotation_radians: float
    translation_m: tuple[float, float]
    rmse_m: float = Field(ge=0)
    mode: Literal["similarity", "affine"] = "similarity"
    # Representação canônica: (m11, m12, m21, m22, tx, ty). Ausente em calibrações
    # gravadas antes da escala por eixo, que eram sempre similaridade.
    matrix: tuple[float, float, float, float, float, float] | None = None
    scale_x_m_per_px: float | None = Field(default=None, gt=0)
    scale_y_m_per_px: float | None = Field(default=None, gt=0)
    anisotropy: float | None = Field(default=None, ge=1)


class ProposalDecisionResponse(ApiModel):
    proposal_id: str
    action: Literal["accept", "reject"]
    entity_id: UUID | None = None
    calibration_id: UUID | None = None


class DecideProposalRequest(ApiModel):
    base_review_version: int = Field(ge=1)
    base_scene_version: int = Field(ge=1)
    proposal_id: str = Field(pattern=r"^vp_[a-f0-9]{16}$")
    action: Literal["accept", "reject"]
    justification: str = Field(min_length=3, max_length=500)
    calibration_id: UUID | None = None


class DecideProposalBatchRequest(ApiModel):
    """Uma decisão para muitas propostas: traçar um croqui inteiro uma a uma é inviável.

    O lote inteiro vira uma revisão e uma cena, então ou entra tudo ou não entra nada.
    A justificativa é única por lote e vale para cada proposta nele.
    """

    base_review_version: int = Field(ge=1)
    base_scene_version: int = Field(ge=1)
    proposal_ids: list[Annotated[str, Field(pattern=r"^vp_[a-f0-9]{16}$")]] = Field(
        min_length=1, max_length=500
    )
    action: Literal["accept", "reject"]
    justification: str = Field(min_length=3, max_length=500)
    calibration_id: UUID | None = None


class AnnotateDimensionRequest(ApiModel):
    """Amarra uma cota confirmada a uma linha traçada; a cota passa a valer sobre o pixel."""

    base_review_version: int = Field(ge=1)
    base_scene_version: int = Field(ge=1)
    reading_id: str = Field(pattern=r"^rd_[a-f0-9]{16}$")
    entity_id: UUID
    justification: str = Field(min_length=3, max_length=500)


class AnnotateNoteRequest(ApiModel):
    """Prende uma leitura confirmada ao elemento como texto, sem inventar geometria."""

    base_review_version: int = Field(ge=1)
    base_scene_version: int = Field(ge=1)
    reading_id: str = Field(pattern=r"^rd_[a-f0-9]{16}$")
    entity_id: UUID
    layer: Literal["MURO", "ALAMBRADO", "PORTAO", "PATAMAR", "EQUIPAMENTOS", "TEXTOS"] = "TEXTOS"
    justification: str = Field(min_length=3, max_length=500)


class RequiredCriterion(ApiModel):
    """Critério de escopo do caso com o texto que o revisor precisa ler, não só o código."""

    code: str
    text: str


class ReviewResponse(ApiModel):
    job_id: UUID
    review_id: UUID
    version: int
    packet: ReviewPacket
    associations: AssociationSet
    proposals: VisionProposalSet | None = None
    selected_associations: dict[str, str]
    calibration: ProposalCalibrationResponse | None = None
    proposal_decisions: list[ProposalDecisionResponse] = Field(default_factory=list)
    issues: list[Issue]
    blockers: list[str]
    required_criteria: list[RequiredCriterion] = Field(default_factory=list)
    scene: SceneRevision | None = None
    preview_urls: dict[str, str] = Field(default_factory=dict)

    @field_validator("required_criteria", mode="before")
    @classmethod
    def accept_code_only_criteria(cls, value: Any) -> Any:
        """Resposta gravada antes de o texto viajar: replay idempotente não pode quebrar."""
        if not isinstance(value, list):
            return value
        return [
            {"code": item, "text": FALLBACK_CRITERION_MESSAGE} if isinstance(item, str) else item
            for item in value
        ]


class CreateExportRequest(ApiModel):
    revision_id: UUID
    format: Literal["dxf"] = "dxf"


class ExportArtifactResponse(ApiModel):
    export_id: UUID
    job_id: UUID
    scene_revision_id: UUID
    format: Literal["dxf"]
    status: Literal["QUEUED", "RUNNING", "COMPLETED", "FAILED"]
    audit_status: str | None = None
    dxf_sha256: str | None = None
    failure_code: str | None = None
    audit_errors: list[str] = Field(default_factory=list)
    package_url: str | None = None


class TraceDeclaredSpan(ApiModel):
    """Vão declarado entre duas arestas do mesmo elemento, por pares de âncoras em pixel."""

    proposal_id: str = Field(min_length=1, max_length=64)
    spans_px: list[tuple[tuple[float, float], tuple[float, float]]] = Field(
        min_length=1, max_length=32
    )


TraceAssociationTarget = str | list[str] | TraceDeclaredSpan
"""Os três formatos do traçado: um elemento, um par de elementos ou âncoras declaradas."""


class CreateTraceSolveRequest(ApiModel):
    """Aceite em lote do traçado: o ato humano completo, sem identidade nem relógio.

    Revisor, papel, `decided_at` e `acceptance_id` são derivados do JWT e do servidor;
    o cliente declara apenas o que aceitou e como as cotas se ligam ao desenho.
    """

    base_review_version: int = Field(ge=1)
    # Ausente quando o job ainda não tem cena: o traçado é a primeira geometria métrica.
    base_scene_version: int | None = Field(default=None, ge=1)
    proposal_ids: list[str] = Field(min_length=1, max_length=500)
    hatch_proposal_ids: list[str] = Field(default_factory=list, max_length=500)
    # `["vp_a", "vp_b"]` separa nos dois eixos; a forma objeto declara o eixo do problema.
    keep_apart_pairs: list[tuple[str, str] | KeepApartPair] = Field(
        default_factory=list, max_length=500
    )
    unlabelled_proposal_ids: list[str] = Field(default_factory=list, max_length=500)
    freeform_proposal_ids: list[str] = Field(default_factory=list, max_length=500)
    detail_groups: list[TraceDetailGroup] = Field(default_factory=list, max_length=32)
    associations: dict[str, TraceAssociationTarget] = Field(default_factory=dict)
    note_associations: dict[str, str] = Field(default_factory=dict)
    derived_dimensions: list[DerivedDimensionRequest] = Field(default_factory=list, max_length=200)
    dimension_texts: dict[str, str] = Field(default_factory=dict)
    note: str | None = Field(default=None, max_length=500)
    title: str | None = Field(default=None, min_length=1, max_length=120)
    feature_id: str = Field(default="tracado", pattern=r"^[a-z0-9][a-z0-9_-]{0,63}$")


class TraceResidualSummary(ApiModel):
    """Resumo dos resíduos; a lista completa fica na cena resolvida, não no registro."""

    count: int = Field(ge=0)
    failed_count: int = Field(ge=0)
    worst_code: str | None = None
    worst_absolute_error_m: float | None = None
    worst_tolerance_m: float | None = None


class TraceSolveResponse(ApiModel):
    trace_solve_id: UUID
    job_id: UUID
    status: Literal["QUEUED", "RUNNING", "COMPLETED", "FAILED"]
    acceptance_id: str
    base_review_version: int
    base_scene_version: int | None = None
    solve_status: Literal["solved_unapproved", "review_required", "conflict"] | None = None
    blockers: list[str] = Field(default_factory=list)
    unapplied_reading_ids: list[str] = Field(default_factory=list)
    residual_summary: TraceResidualSummary | None = None
    exact_entity_count: int | None = None
    approximate_entity_count: int | None = None
    note_count: int | None = None
    scale_m_per_px: float | None = None
    detail_group_scales: dict[str, float] = Field(default_factory=dict)
    result_scene_revision_id: UUID | None = None
    result_scene_version: int | None = None
    result_review_version: int | None = None
    failure_code: str | None = None


class ChatAnchors(ApiModel):
    """O que o profissional apontou ao perguntar; nada é inferido por proximidade."""

    reading_ids: list[Annotated[str, Field(pattern=r"^rd_[a-f0-9]{16}$")]] = Field(
        default_factory=list, max_length=20
    )
    proposal_ids: list[Annotated[str, Field(pattern=r"^vp_[a-f0-9]{16}$")]] = Field(
        default_factory=list, max_length=20
    )


class CreateChatSessionRequest(ApiModel):
    """Corpo vazio (`{}`): a revisão-base é fixada pelo servidor, não escolhida pelo cliente."""


class CreateChatTurnRequest(ApiModel):
    question: str = Field(min_length=3, max_length=500)
    anchors: ChatAnchors = Field(default_factory=ChatAnchors)


class ChatTurnResponse(ApiModel):
    chat_turn_id: UUID
    chat_session_id: UUID
    job_id: UUID
    sequence: int = Field(ge=1)
    status: Literal["QUEUED", "RUNNING", "COMPLETED", "FAILED"]
    question: str
    anchors: ChatAnchors
    # Observação validada contra o contrato do provider, nunca resposta bruta. Os
    # `proposed_acts` são rascunhos dos payloads que os endpoints existentes já aceitam.
    answer: ReviewChatOutput | None = None
    failure_code: str | None = None
    created_at: datetime
    updated_at: datetime


class ChatSessionResponse(ApiModel):
    chat_session_id: UUID
    job_id: UUID
    status: Literal["OPEN", "CLOSED"]
    base_review_revision_id: UUID
    base_review_version: int
    created_at: datetime
    turns: list[ChatTurnResponse] = Field(default_factory=list)


class ChatSessionSummaryResponse(ApiModel):
    """Lista magra: quem abriu a tela precisa escolher uma conversa, não relê-las."""

    chat_session_id: UUID
    status: Literal["OPEN", "CLOSED"]
    created_at: datetime
    turn_count: int = Field(ge=0)


class ProcessingQueue:
    """Adaptador pequeno para SQS; sem fila configurada, falha fechado."""

    def __init__(self, settings: ApiSettings) -> None:
        self.queue_url = settings.queue_url
        self.client = boto3.client(
            "sqs",
            region_name=settings.aws_region,
            endpoint_url=settings.aws_endpoint_url,
            config=Config(retries={"max_attempts": 3, "mode": "standard"}),
        )

    def enqueue(self, *, job_id: str, tenant_id: str) -> None:
        if self.queue_url is None:
            return
        self.client.send_message(
            QueueUrl=self.queue_url,
            MessageBody=json.dumps(
                {
                    "command": "process_upload",
                    "job_id": job_id,
                    "tenant_id": tenant_id,
                    "stage": "VALIDATING",
                }
            ),
        )

    def enqueue_export(
        self, *, export_id: str, job_id: str, tenant_id: str, scene_revision_id: str
    ) -> None:
        """Publishes the export intent; the CAD package is always built outside the request."""
        if self.queue_url is None:
            return
        self.client.send_message(
            QueueUrl=self.queue_url,
            MessageBody=json.dumps(
                {
                    "command": "export_scene_package",
                    "export_id": export_id,
                    "job_id": job_id,
                    "tenant_id": tenant_id,
                    "scene_revision_id": scene_revision_id,
                }
            ),
        )

    def enqueue_trace_solve(self, *, trace_solve_id: str, job_id: str, tenant_id: str) -> None:
        """Publishes the trace intent; the geometry solver never runs in the request path."""
        if self.queue_url is None:
            return
        self.client.send_message(
            QueueUrl=self.queue_url,
            MessageBody=json.dumps(
                {
                    "command": "solve_trace_scene",
                    "trace_solve_id": trace_solve_id,
                    "job_id": job_id,
                    "tenant_id": tenant_id,
                }
            ),
        )

    def enqueue_chat_turn(self, *, chat_turn_id: str, job_id: str, tenant_id: str) -> None:
        """Publishes the chat turn; no model is ever called from the request path."""
        if self.queue_url is None:
            return
        self.client.send_message(
            QueueUrl=self.queue_url,
            MessageBody=json.dumps(
                {
                    "command": "answer_chat_turn",
                    "chat_turn_id": chat_turn_id,
                    "job_id": job_id,
                    "tenant_id": tenant_id,
                }
            ),
        )


#: Os dois transportes publicam os mesmos comandos com o mesmo corpo; a rota não sabe
#: qual está montado.
QueueAdapter = ProcessingQueue | PubSubProcessingQueue

#: Falhas de transporte que a rota traduz em 503 repetível, seja qual for a nuvem.
QUEUE_TRANSPORT_ERRORS = (BotoCoreError, ClientError, QueuePublishError)


def _problem(code: str, http_status: int, detail: str) -> HTTPException:
    return HTTPException(status_code=http_status, detail={"code": code, "detail": detail})


def _safe_filename(filename: str, content_type: str) -> str:
    """Nome normalizado cuja extensão CASA com o tipo declarado no presign.

    A extensão é conferida contra o tipo, e não contra uma lista fixa, porque os dois
    viajam no mesmo corpo: `.pdf` com tipo de JSON e `.json` com tipo de PDF são a mesma
    incoerência, e aceitar qualquer uma delas deixaria o objeto gravado com um tipo que
    contradiz o nome — e é pelo tipo que a criação do job e a instalação do catálogo
    decidem o que aquele upload é.
    """
    extension = UPLOAD_CONTENT_TYPES.get(content_type)
    if extension is None:  # pragma: no cover - o contrato do request já restringe o tipo
        raise _problem(
            "INVALID_UPLOAD",
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "Tipo de conteúdo não aceito para upload.",
        )
    normalized = re.sub(r"[^A-Za-z0-9._-]+", "-", filename).strip(".-")
    if not normalized.lower().endswith(extension):
        raise _problem(
            "INVALID_UPLOAD",
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"Arquivo precisa ter extensão {extension.removeprefix('.').upper()} "
            f"para o tipo {content_type}.",
        )
    return normalized or f"documento{extension}"


def _request_hash(payload: BaseModel) -> str:
    encoded = json.dumps(payload.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _approval_id(*, scene_id: UUID, reviewer_id: str, decided_at: datetime, statement: str) -> str:
    """Deterministic approval id, mirroring the review contract's decision identifiers."""
    canonical = json.dumps(
        {
            "source_scene_id": str(scene_id),
            "reviewer_id": reviewer_id,
            "decided_at": decided_at.isoformat(),
            "statement": statement,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return f"ap_{hashlib.sha256(canonical.encode('utf-8')).hexdigest()[:16]}"


def _domain_messages(error: ValidationError) -> str:
    """Domain messages from a contract validator; never the rejected values themselves."""
    messages = [str(item["msg"]).removeprefix("Value error, ") for item in error.errors()]
    return "; ".join(dict.fromkeys(messages)) or "Aceite de traçado inconsistente."


def _trace_acceptance_id(
    *, job_id: UUID, reviewer_id: str, decided_at: datetime, proposal_ids: list[str]
) -> str:
    """Deterministic acceptance id, mirroring the review contract's decision identifiers."""
    canonical = json.dumps(
        {
            "job_id": str(job_id),
            "reviewer_id": reviewer_id,
            "decided_at": decided_at.isoformat(),
            "proposal_ids": proposal_ids,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return f"ta_{hashlib.sha256(canonical.encode('utf-8')).hexdigest()[:16]}"


def _note_target_proposal_ids(target: str) -> list[str]:
    """Resolves a note target to the proposals it anchors on; the title block anchors none."""
    if target == GENERAL_NOTE_TARGET:
        return []
    if target.startswith(LEGEND_NOTE_PREFIX):
        return [target[len(LEGEND_NOTE_PREFIX) :]]
    # Sufixo "#v"/"#h" é dica de orientação da aresta âncora, não parte do id.
    return [target.partition("#")[0]]


def _association_proposal_ids(target: TraceAssociationTarget) -> list[str]:
    if isinstance(target, str):
        return [target]
    if isinstance(target, TraceDeclaredSpan):
        return [target.proposal_id]
    return list(target)


def _idempotent_response(
    session: Session,
    *,
    principal: Principal,
    operation: str,
    key: str,
    request_hash: str,
) -> dict[str, Any] | None:
    record = session.scalar(
        select(IdempotencyRecord).where(
            IdempotencyRecord.tenant_id == principal.tenant_id,
            IdempotencyRecord.operation == operation,
            IdempotencyRecord.key == key,
        )
    )
    if record is None:
        return None
    if record.request_hash != request_hash:
        raise _problem(
            "IDEMPOTENCY_KEY_REUSED",
            status.HTTP_409_CONFLICT,
            "Idempotency-Key já foi usado com outro comando.",
        )
    return record.response_json


def _store_idempotent_response(
    session: Session,
    *,
    principal: Principal,
    operation: str,
    key: str,
    request_hash: str,
    response: BaseModel,
) -> None:
    session.add(
        IdempotencyRecord(
            id=str(new_uuid7()),
            tenant_id=principal.tenant_id,
            operation=operation,
            key=key,
            request_hash=request_hash,
            response_json=response.model_dump(mode="json"),
        )
    )


def _record_audit(
    session: Session,
    *,
    principal: Principal,
    action: str,
    resource_type: str,
    resource_id: str,
    request_id: str,
    tenant_id: str | None = None,
) -> None:
    session.add(
        AuditRecord(
            id=str(new_uuid7()),
            tenant_id=tenant_id or principal.tenant_id,
            actor_id=principal.subject,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            metadata_json={"request_id": request_id},
        )
    )


def _reviewer_role(principal: Principal) -> str:
    """Maps only signed roles to the review contract's professional role vocabulary."""
    for role in ("engineer", "architect", "domain_reviewer"):
        if principal.has_role(role):
            return role
    raise _problem(
        "FORBIDDEN",
        status.HTTP_403_FORBIDDEN,
        "Papel profissional elegível é obrigatório para decidir leituras.",
    )


def _require_active_ai_entitlement(
    session: Session, principal: Principal, *, real_providers_enabled: bool
) -> TenantAiProcessingEntitlementRecord | None:
    """Autorização contratual ativa do tenant, exigida só onde providers reais estão ligados.

    Com o ambiente desligado (`real_providers_enabled=false`) nenhuma chamada externa é
    possível, e exigir contrato para um caminho 100% local seria proibir o que já não sai
    da máquina. O portão é o mesmo do job desde o ADR-0012; esta função existe para que
    ele seja um só, e não uma cópia por endpoint.
    """
    if not real_providers_enabled:
        return None
    entitlement = session.scalar(
        select(TenantAiProcessingEntitlementRecord).where(
            TenantAiProcessingEntitlementRecord.tenant_id == principal.tenant_id,
            TenantAiProcessingEntitlementRecord.status == "ACTIVE",
        )
    )
    if entitlement is None:
        raise _problem(
            "AI_PROCESSING_NOT_AUTHORIZED",
            status.HTTP_403_FORBIDDEN,
            "O tenant não possui autorização contratual ativa para processamento externo.",
        )
    return entitlement


def _require_platform_operator(principal: Principal) -> None:
    if not principal.has_role("platform_operator"):
        raise _problem(
            "FORBIDDEN",
            status.HTTP_403_FORBIDDEN,
            "Papel platform_operator é obrigatório para administrar autorização contratual.",
        )


def _latest_review(
    session: Session, *, job_id: UUID, tenant_id: str
) -> ReviewRevisionRecord | None:
    return session.scalar(
        select(ReviewRevisionRecord)
        .where(
            ReviewRevisionRecord.job_id == str(job_id),
            ReviewRevisionRecord.tenant_id == tenant_id,
        )
        .order_by(ReviewRevisionRecord.version.desc())
    )


def _latest_scene(session: Session, *, job_id: UUID, tenant_id: str) -> RevisionRecord | None:
    return session.scalar(
        select(RevisionRecord)
        .where(
            RevisionRecord.job_id == str(job_id),
            RevisionRecord.tenant_id == tenant_id,
        )
        .order_by(RevisionRecord.version.desc())
    )


def _calibration_response(value: dict[str, Any] | None) -> ProposalCalibrationResponse | None:
    return ProposalCalibrationResponse.model_validate(value) if value is not None else None


def _human_accepted_entities(scene: SceneRevision) -> list[Entity]:
    """Entities a professional accepted from a pixel proposal; never regenerated by a solver."""
    return [
        entity
        for entity in scene.entities
        if entity.provenance is not None
        and entity.provenance.source_type == HUMAN_ACCEPTED_PROPOSAL_SOURCE_TYPE
    ]


# `_revalidate_calibration` and `_matrix_of` used to duplicate
# `croquito_worker.proposal_calibration.revalidate_calibration`/`matrix_of`; the CLI's
# `refresh-proposals` needs the exact same drift rule, so the logic now lives once in the
# worker package (already an API dependency) and is reused here by reference.
_revalidate_calibration = revalidate_calibration
_matrix_of = matrix_of


def _calibration_payload(
    *,
    calibration_id: UUID,
    scene_revision_id: UUID,
    scene_version: int,
    anchors: list[ProposalCalibrationAnchorRequest],
    transform: CalibrationTransform,
) -> ProposalCalibrationResponse:
    matrix = _matrix_of(transform)
    if isinstance(transform, AffineTransform):
        mode: Literal["similarity", "affine"] = "affine"
        rotation = math.atan2(transform.m21, transform.m11)
    else:
        mode = "similarity"
        rotation = math.atan2(transform.b, transform.a)
    return ProposalCalibrationResponse(
        calibration_id=calibration_id,
        scene_revision_id=scene_revision_id,
        scene_version=scene_version,
        anchors=anchors,
        # Campo herdado: para afim descreve apenas o eixo x, por isso a escala por eixo
        # viaja separada e a matriz é a fonte de verdade.
        scale_m_per_px=transform.scale_x_m_per_px,
        rotation_radians=rotation,
        translation_m=(transform.tx, transform.ty),
        rmse_m=transform.rmse_m,
        mode=mode,
        matrix=matrix,
        scale_x_m_per_px=transform.scale_x_m_per_px,
        scale_y_m_per_px=transform.scale_y_m_per_px,
        anisotropy=transform.anisotropy,
    )


def _annotation_target(
    session: Session,
    *,
    job_id: UUID,
    tenant_id: str,
    base_review_version: int,
    base_scene_version: int,
    reading_id: str,
) -> tuple[ReviewRevisionRecord, RevisionRecord, SceneRevision, DimensionReading]:
    """Revisão, cena e leitura confirmada prontas para virar cota ou anotação."""
    current = _latest_review(session, job_id=job_id, tenant_id=tenant_id)
    if current is None:
        raise _problem(
            "JOB_NOT_READY",
            status.HTTP_409_CONFLICT,
            "Pacote de revisão ainda não está disponível.",
        )
    if current.version != base_review_version:
        raise _problem(
            "REVISION_CONFLICT", status.HTTP_409_CONFLICT, "Existe uma revisão mais recente."
        )
    scene_record = _latest_scene(session, job_id=job_id, tenant_id=tenant_id)
    if scene_record is None or scene_record.version != base_scene_version:
        raise _problem(
            "REVISION_CONFLICT",
            status.HTTP_409_CONFLICT,
            "Existe uma cena mais recente para a anotação.",
        )
    packet = ReviewPacket.model_validate(current.packet_json)
    reading = next((item for item in packet.readings if item.id == reading_id), None)
    if reading is None:
        raise _problem(
            "DOMAIN_VALIDATION_FAILED",
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "A leitura não pertence ao pacote desta revisão.",
        )
    if reading.status is not ReadingStatus.CONFIRMED or reading.decision is None:
        raise _problem(
            "DOMAIN_VALIDATION_FAILED",
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "Só uma leitura confirmada chega ao desenho.",
        )
    scene = SceneRevision.model_validate(scene_record.scene)
    if any(
        entity.provenance is not None and reading_id in entity.provenance.source_ids
        for entity in scene.entities
        if entity.kind in {EntityKind.DIMENSION, EntityKind.DIAMETER_DIMENSION, EntityKind.TEXT}
    ):
        raise _problem(
            "DOMAIN_VALIDATION_FAILED",
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "Esta leitura já está no desenho.",
        )
    return current, scene_record, scene, reading


OUT_OF_SCALE_CODE = "SKETCH_OUT_OF_SCALE"


def _out_of_scale_issue(
    scene: SceneRevision, transform: CalibrationTransform
) -> list[dict[str, Any]]:
    """Registra, uma única vez, que os eixos do croqui não estão na mesma escala.

    É `warning`, não `critical`: a distorção não impede exportar, mas precisa constar
    no `hipoteses.json` para quem abrir o DXF saber que ângulos fora dos eixos das
    âncoras não foram preservados.
    """
    if transform.anisotropy <= ISOTROPY_TOLERANCE:
        return []
    if any(issue.code == OUT_OF_SCALE_CODE for issue in scene.issues):
        return []
    percentage = (transform.anisotropy - 1) * 100
    return [
        Issue(
            code=OUT_OF_SCALE_CODE,
            severity=IssueSeverity.WARNING,
            status=IssueStatus.OPEN,
            message=(
                "Os eixos do croqui divergem "
                f"{percentage:.1f}% em escala. A geometria aproximada foi ajustada por "
                "eixo; ângulos fora das âncoras não são preservados."
            ),
        ).model_dump(mode="json")
    ]


def _transform_from_calibration(
    calibration: ProposalCalibrationResponse,
) -> CalibrationTransform:
    """Reconstrói a transformação gravada, delegando ao parser comum do worker."""
    return transform_from_calibration_json(calibration.model_dump(mode="json"))


def _preview_urls(
    application: FastAPI, *, tenant_id: str, evidence_refs: dict[str, str]
) -> dict[str, str]:
    """Presign only opaque private keys; URLs are never persisted or audited."""
    store: ArtifactStore = application.state.artifact_store
    urls: dict[str, str] = {}
    tenant_prefix = f"tenants/{tenant_id}/"
    for label, object_key in evidence_refs.items():
        if label.endswith("_key") and object_key.startswith(tenant_prefix):
            urls[label.removesuffix("_key") + "_url"] = store.presign_private_read(
                object_key=object_key
            )
    return urls


def _export_response(application: FastAPI, record: ExportArtifactRecord) -> ExportArtifactResponse:
    """Signs the package only once it exists and only under the caller's tenant prefix."""
    package_url: str | None = None
    tenant_prefix = f"tenants/{record.tenant_id}/"
    if (
        record.status == "COMPLETED"
        and record.package_object_key is not None
        and record.package_object_key.startswith(tenant_prefix)
    ):
        store: ArtifactStore = application.state.artifact_store
        package_url = store.presign_private_read(object_key=record.package_object_key)
    audit = record.audit_json or {}
    errors = audit.get("errors", [])
    return ExportArtifactResponse.model_validate(
        {
            "export_id": UUID(record.id),
            "job_id": UUID(record.job_id),
            "scene_revision_id": UUID(record.scene_revision_id),
            "format": record.format,
            "status": record.status,
            "audit_status": record.audit_status,
            "dxf_sha256": record.dxf_sha256,
            "failure_code": record.failure_code,
            "audit_errors": errors if isinstance(errors, list) else [],
            "package_url": package_url,
        }
    )


def _revision_version(session: Session, revision_id: str | None) -> int | None:
    if revision_id is None:
        return None
    record = session.scalar(select(RevisionRecord).where(RevisionRecord.id == revision_id))
    return record.version if record is not None else None


def _review_version(session: Session, review_id: str | None) -> int | None:
    if review_id is None:
        return None
    record = session.scalar(
        select(ReviewRevisionRecord).where(ReviewRevisionRecord.id == review_id)
    )
    return record.version if record is not None else None


def _trace_solve_response(session: Session, record: TraceSolveRecord) -> TraceSolveResponse:
    """Polling view of one trace solve; blockers are stable domain codes, never raw output."""
    summary = record.residual_summary_json
    return TraceSolveResponse.model_validate(
        {
            "trace_solve_id": UUID(record.id),
            "job_id": UUID(record.job_id),
            "status": record.status,
            "acceptance_id": record.acceptance_id,
            "base_review_version": _review_version(session, record.base_review_revision_id),
            "base_scene_version": _revision_version(session, record.base_scene_revision_id),
            "solve_status": record.solve_status,
            "blockers": list(record.blockers_json or []),
            "unapplied_reading_ids": list(record.unapplied_reading_ids_json or []),
            "residual_summary": summary,
            "exact_entity_count": record.exact_entity_count,
            "approximate_entity_count": record.approximate_entity_count,
            "note_count": record.note_count,
            "scale_m_per_px": record.scale_m_per_px,
            "detail_group_scales": dict(record.detail_group_scales_json or {}),
            "result_scene_revision_id": record.result_scene_revision_id,
            "result_scene_version": _revision_version(session, record.result_scene_revision_id),
            "result_review_version": _review_version(session, record.result_review_revision_id),
            "failure_code": record.failure_code,
        }
    )


def _chat_turn_response(record: ChatTurnRecord) -> ChatTurnResponse:
    """Vista de polling de um turno; a resposta volta revalidada contra o contrato."""
    return ChatTurnResponse(
        chat_turn_id=UUID(record.id),
        chat_session_id=UUID(record.session_id),
        job_id=UUID(record.job_id),
        sequence=record.sequence,
        status=cast(Literal["QUEUED", "RUNNING", "COMPLETED", "FAILED"], record.status),
        question=record.question_text,
        anchors=ChatAnchors.model_validate(record.anchor_refs_json or {}),
        # Revalidar em vez de repassar: um `answer_json` que tivesse escapado do contrato
        # chegaria ao cliente como se fosse contrato.
        answer=(
            ReviewChatOutput.model_validate(record.answer_json)
            if record.answer_json is not None
            else None
        ),
        failure_code=record.failure_code,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def _chat_session_response(
    record: ChatSessionRecord, *, base_review_version: int, turns: Sequence[ChatTurnRecord]
) -> ChatSessionResponse:
    return ChatSessionResponse(
        chat_session_id=UUID(record.id),
        job_id=UUID(record.job_id),
        status=cast(Literal["OPEN", "CLOSED"], record.status),
        base_review_revision_id=UUID(record.base_review_revision_id),
        base_review_version=base_review_version,
        created_at=record.created_at,
        turns=[_chat_turn_response(turn) for turn in turns],
    )


def _review_response(
    application: FastAPI, session: Session, record: ReviewRevisionRecord
) -> ReviewResponse:
    packet = ReviewPacket.model_validate(record.packet_json)
    associations = AssociationSet.model_validate(record.associations_json)
    proposals = (
        VisionProposalSet.model_validate(record.proposals_json)
        if record.proposals_json is not None
        else None
    )
    scene_record = (
        session.scalar(select(RevisionRecord).where(RevisionRecord.id == record.scene_revision_id))
        if record.scene_revision_id is not None
        else None
    )
    latest_scene = _latest_scene(session, job_id=UUID(record.job_id), tenant_id=record.tenant_id)
    # A aprovação cria uma cena nova sem criar review revision. Sem isto a revisão
    # continuaria devolvendo o rascunho e a tela pediria uma aprovação já assinada.
    if latest_scene is not None and (
        scene_record is None or latest_scene.version > scene_record.version
    ):
        scene_record = latest_scene
    scene = SceneRevision.model_validate(scene_record.scene) if scene_record is not None else None
    issues = scene.issues if scene is not None else []
    declared_codes = {
        issue.code
        for issue in issues
        if issue.status in {IssueStatus.ACCEPTED, IssueStatus.RESOLVED}
    }
    blockers = [
        *record.solver_blockers_json,
        # Critério já declarado na aprovação — coberto ou reconhecido — deixa de ser
        # bloqueio; mantê-lo na lista ensina o revisor a ignorar aviso vermelho.
        *[code for code in record.required_blocker_codes_json if code not in declared_codes],
    ]
    if scene is not None:
        blockers.extend(
            issue.code
            for issue in scene.issues
            if issue.severity is IssueSeverity.CRITICAL and issue.status is IssueStatus.OPEN
        )
    return ReviewResponse(
        job_id=UUID(record.job_id),
        review_id=UUID(record.id),
        version=record.version,
        packet=packet,
        associations=associations,
        proposals=proposals,
        selected_associations=record.selected_associations_json,
        calibration=_calibration_response(record.calibration_json),
        proposal_decisions=[
            ProposalDecisionResponse.model_validate(
                {key: item for key, item in value.items() if key != "justification"}
            )
            for value in (record.proposal_decisions_json or [])
        ],
        issues=issues,
        blockers=list(dict.fromkeys(blockers)),
        required_criteria=[
            RequiredCriterion(
                code=code,
                text=criterion_message(code, record.required_criteria_texts_json or {}),
            )
            for code in record.required_blocker_codes_json
        ],
        scene=scene,
        preview_urls=_preview_urls(
            application,
            tenant_id=record.tenant_id,
            evidence_refs=record.evidence_refs_json,
        ),
    )


CALIBRATION_SUPERSEDED_MESSAGE = (
    "A calibração não é mais válida para a cena atual; recalibre antes de exportar."
)
READING_DECISION_SUPERSEDED_CODE = "READING_DECISION_SUPERSEDED"
READING_DECISION_SUPERSEDED_MESSAGE = (
    "Uma medida foi corrigida depois que esta parte do desenho foi feita; "
    "refaça o traçado dela antes de exportar."
)


@dataclass(frozen=True, slots=True)
class ResolvedSceneChange:
    """O que uma mudança de revisão de leitura produziu na cena, antes de persistir."""

    blockers: list[str]
    scene: SceneRevision | None
    calibration_json: dict[str, Any] | None
    parent_scene_id: str | None


def _apply_association_rules(
    *,
    reading_id: str,
    confirming: bool,
    annotation: bool,
    association_proposal_id: str | None,
    candidate_pairs: set[tuple[str, str]],
    selected_associations: dict[str, str],
) -> None:
    """Regra única de associação para decidir e para corrigir decisão registrada.

    A associação é sempre declarada pelo comando — nunca herdada em silêncio de uma
    decisão anterior — e a anotação da folha continua sendo a única confirmação sem
    elemento associado.
    """
    if not confirming:
        selected_associations.pop(reading_id, None)
        return
    if annotation:
        if association_proposal_id is not None:
            raise _problem(
                "DOMAIN_VALIDATION_FAILED",
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "Anotação da folha não leva associação de elemento.",
            )
        # Anotação confirmada não entra no mapa de associações: sem
        # restrição de geometria, ela segue como leitura não aplicada.
        selected_associations.pop(reading_id, None)
        return
    if association_proposal_id is None:
        raise _problem(
            "DOMAIN_VALIDATION_FAILED",
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "Confirmação exige uma associação explícita — ou a declaração de anotação.",
        )
    if (reading_id, association_proposal_id) not in candidate_pairs:
        raise _problem(
            "DOMAIN_VALIDATION_FAILED",
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "A associação selecionada não pertence à leitura.",
        )
    selected_associations[reading_id] = association_proposal_id


def _rectification_changes_nothing(
    reading: DimensionReading,
    command: RectifyReadingCommand,
    *,
    previous_association: str | None,
    next_association: str | None,
) -> bool:
    """Correção que reescreveria o registro vigente idêntico a ele mesmo.

    Ela não é registrada: uma revisão nova e uma cascata de invalidação sem nenhuma
    mudança material transformariam auditoria em ruído.
    """
    if previous_association != next_association:
        return False
    expected_status = (
        ReadingStatus.CONFIRMED if command.action == "confirm" else ReadingStatus.REJECTED
    )
    if reading.status is not expected_status:
        return False
    if command.raw_text is not None and command.raw_text != reading.raw_text:
        return False
    if command.value_si is not None and Decimal(command.value_si) != reading.value_si:
        return False
    if command.unit is not None and command.unit != reading.unit:
        return False
    if command.kind is not None and command.kind != reading.kind:
        return False
    written_decimals = command.written_decimals
    if written_decimals is not None and written_decimals != reading.written_decimals:
        return False
    return command.target_hint is None or command.target_hint == reading.target_hint


def _resolve_scene_after_review_change(
    session: Session,
    *,
    job_id: UUID,
    tenant_id: str,
    current: ReviewRevisionRecord,
    reviewed_packet: ReviewPacket,
    selected_associations: dict[str, str],
) -> ResolvedSceneChange:
    """Re-resolve a cena retangular depois de um ato humano sobre as leituras.

    Vale igual para a decisão e para a correção declarada de decisão: duas cópias desta
    regra divergiriam em silêncio, e é aqui que mora a garantia de que a geometria aceita
    por um profissional nunca é reprojetada nem descartada.
    """
    if current.solver_request_json is None:
        return ResolvedSceneChange(
            blockers=[],
            scene=None,
            calibration_json=current.calibration_json,
            parent_scene_id=None,
        )
    solver_result = solve_rectangle(
        reviewed_packet,
        RectangleSolveRequest.model_validate(current.solver_request_json),
        confirmed_associations=selected_associations,
    )
    if solver_result.scene is None:
        return ResolvedSceneChange(
            blockers=solver_result.blockers,
            scene=None,
            calibration_json=current.calibration_json,
            parent_scene_id=None,
        )
    previous_scene_record = _latest_scene(session, job_id=job_id, tenant_id=tenant_id)
    preserved: list[Entity] = []
    parent_scene_id: str | None = None
    if previous_scene_record is not None:
        parent_scene_id = previous_scene_record.id
        preserved = _human_accepted_entities(
            SceneRevision.model_validate(previous_scene_record.scene)
        )
    blocker_issues = scope_criteria_issues(
        current.required_blocker_codes_json,
        current.required_criteria_texts_json or {},
    )
    scene = SceneRevision.model_validate(
        {
            **solver_result.scene.model_dump(mode="json"),
            "id": str(new_uuid7()),
            "job_id": str(job_id),
            "version": (previous_scene_record.version if previous_scene_record else 0) + 1,
            "entities": [
                *[entity.model_dump(mode="json") for entity in solver_result.scene.entities],
                *[entity.model_dump(mode="json") for entity in preserved],
            ],
            "issues": [
                *[issue.model_dump(mode="json") for issue in solver_result.scene.issues],
                *[issue.model_dump(mode="json") for issue in blocker_issues],
            ],
        }
    )
    next_calibration_json = _revalidate_calibration(
        current.calibration_json,
        proposals_json=current.proposals_json,
        scene=scene,
        scene_record_id=str(scene.id),
    )
    if preserved and next_calibration_json is None:
        # The accepted geometry is never re-projected or dropped: it is frozen
        # behind a critical issue until a professional recalibrates and re-decides.
        scene = _with_critical_issue(
            scene,
            code="CALIBRATION_SUPERSEDED",
            message=CALIBRATION_SUPERSEDED_MESSAGE,
            entity_ids=[entity.id for entity in preserved],
        )
    return ResolvedSceneChange(
        blockers=solver_result.blockers,
        scene=scene,
        calibration_json=next_calibration_json,
        parent_scene_id=parent_scene_id,
    )


def _with_critical_issue(
    scene: SceneRevision, *, code: str, message: str, entity_ids: list[UUID]
) -> SceneRevision:
    """Cena nova com mais uma issue crítica; a cena recebida permanece intacta."""
    return SceneRevision.model_validate(
        {
            **scene.model_dump(mode="json"),
            "issues": [
                *[issue.model_dump(mode="json") for issue in scene.issues],
                Issue(
                    code=code,
                    severity=IssueSeverity.CRITICAL,
                    message=message,
                    entity_ids=entity_ids,
                ).model_dump(mode="json"),
            ],
        }
    )


def _entities_holding_decisions(scene: SceneRevision, decision_ids: set[str]) -> list[UUID]:
    """Entidades cuja geometria (ou cuja medida) ainda se apoia nas decisões citadas.

    `Measurement.provenance` carrega o `decision_id` tanto no solver retangular quanto no
    traçado, então uma cota confirmada sobrevivente é encontrada aqui pela entidade que
    ela mede — sem isso uma correção poderia deixar uma medida órfã no desenho.
    """
    held: list[UUID] = []
    for entity in scene.entities:
        if entity.provenance is not None and decision_ids.intersection(
            entity.provenance.source_ids
        ):
            held.append(entity.id)
    for measurement in scene.measurements:
        if measurement.provenance is not None and decision_ids.intersection(
            measurement.provenance.source_ids
        ):
            held.append(measurement.entity_id)
    return list(dict.fromkeys(held))


def _get_database(request: Request) -> Generator[Session, None, None]:
    database: Database = request.app.state.database
    yield from database.session()


DatabaseSession = Annotated[Session, Depends(_get_database)]
AuthenticatedPrincipal = Annotated[Principal, Depends(require_principal)]


def _require_idempotency(
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> str:
    if idempotency_key is None or len(idempotency_key) > 255:
        raise _problem(
            "IDEMPOTENCY_KEY_REQUIRED",
            status.HTTP_400_BAD_REQUEST,
            "Idempotency-Key é obrigatório.",
        )
    return idempotency_key


def create_app(settings: ApiSettings | None = None, database: Database | None = None) -> FastAPI:
    runtime_settings = settings or ApiSettings.from_environment()
    runtime_database = database or Database(runtime_settings.database_url)
    application = FastAPI(
        title="Croquito API",
        version="0.2.0",
        description="API de controle; processamento pesado ocorre fora do request HTTP.",
    )
    application.add_middleware(
        CORSMiddleware,
        allow_origins=runtime_settings.web_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "DELETE"],
        allow_headers=["Authorization", "Content-Type", "Idempotency-Key", "X-Request-ID"],
    )
    application.state.database = runtime_database
    application.state.authenticator = OidcAuthenticator(
        issuer=runtime_settings.oidc_issuer,
        audience=runtime_settings.oidc_audience,
        allow_test_tokens=runtime_settings.allow_test_tokens,
    )
    queue_adapter: QueueAdapter = (
        PubSubProcessingQueue(runtime_settings)
        if runtime_settings.queue_backend == "pubsub"
        else ProcessingQueue(runtime_settings)
    )
    application.state.queue = queue_adapter
    application.state.artifact_store = ArtifactStore(runtime_settings)
    application.state.settings = runtime_settings

    @application.middleware("http")
    async def request_correlation(request: Request, call_next: Any) -> Any:
        request_id = request.headers.get("X-Request-ID") or str(new_uuid7())
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response

    @application.exception_handler(StarletteHTTPException)
    async def problem_handler(request: Request, exception: StarletteHTTPException) -> JSONResponse:
        """Emits application/problem+json while keeping the detail body clients already read."""
        # Routes carry a structured detail; Starlette itself still raises plain strings.
        detail: Any = exception.detail
        raw_code = detail.get("code") if isinstance(detail, dict) else None
        code = raw_code if isinstance(raw_code, str) else None
        return JSONResponse(
            status_code=exception.status_code,
            media_type="application/problem+json",
            headers=getattr(exception, "headers", None),
            content={
                "type": f"https://errors.croquito.local/{(code or 'http-error').lower()}",
                "title": code or "Erro de requisição",
                "status": exception.status_code,
                "code": code or "HTTP_ERROR",
                "request_id": getattr(request.state, "request_id", None),
                "detail": detail,
            },
        )

    @application.exception_handler(DomainValidationError)
    async def domain_error_handler(
        _request: Request,
        exception: DomainValidationError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            media_type="application/problem+json",
            content={
                "type": "https://errors.croquito.local/domain-validation",
                "title": "Cena inválida",
                "status": 422,
                "code": "DOMAIN_VALIDATION_FAILED",
                "errors": exception.errors,
            },
        )

    @application.get("/healthz", response_model=HealthResponse, include_in_schema=False)
    async def health() -> HealthResponse:
        return HealthResponse(status="ok")

    @application.get("/v1/meta", response_model=MetaResponse, tags=["meta"])
    async def metadata() -> MetaResponse:
        return MetaResponse(
            service="croquito-api",
            api_version="v1",
            scene_schema_version=SCENE_SCHEMA_VERSION,
        )

    @application.get("/v1/schemas/scene", response_model=dict[str, Any], tags=["meta"])
    async def scene_schema() -> dict[str, Any]:
        return SceneRevision.model_json_schema()

    @application.put(
        "/v1/platform/tenants/{tenant_id}/ai-processing-entitlement",
        response_model=AiProcessingEntitlementResponse,
        tags=["platform"],
    )
    async def set_ai_processing_entitlement(
        tenant_id: str,
        payload: SetAiProcessingEntitlementRequest,
        request: Request,
        principal: AuthenticatedPrincipal,
        session: DatabaseSession,
        idempotency_key: Annotated[str, Depends(_require_idempotency)],
    ) -> AiProcessingEntitlementResponse:
        _require_platform_operator(principal)
        if payload.enabled and payload.agreement_reference is None:
            raise _problem(
                "AGREEMENT_REFERENCE_REQUIRED",
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "Ativar processamento por IA exige a referência lógica do contrato.",
            )
        operation = f"platform.ai-processing-entitlement:{tenant_id}"
        request_hash = _request_hash(payload)
        existing_response = _idempotent_response(
            session,
            principal=principal,
            operation=operation,
            key=idempotency_key,
            request_hash=request_hash,
        )
        if existing_response is not None:
            return AiProcessingEntitlementResponse.model_validate(existing_response)

        now = datetime.now(UTC)
        entitlement = session.scalar(
            select(TenantAiProcessingEntitlementRecord).where(
                TenantAiProcessingEntitlementRecord.tenant_id == tenant_id
            )
        )
        if entitlement is None:
            if not payload.enabled:
                raise _problem(
                    "NOT_FOUND",
                    status.HTTP_404_NOT_FOUND,
                    "Autorização contratual não encontrada para o tenant.",
                )
            entitlement = TenantAiProcessingEntitlementRecord(
                id=str(new_uuid7()),
                tenant_id=tenant_id,
                status="ACTIVE",
                agreement_reference=payload.agreement_reference or "",
                authorized_by=principal.subject,
                authorized_at=now,
                revoked_at=None,
            )
            session.add(entitlement)
        elif payload.enabled:
            entitlement.status = "ACTIVE"
            entitlement.agreement_reference = payload.agreement_reference or ""
            entitlement.authorized_by = principal.subject
            entitlement.authorized_at = now
            entitlement.revoked_at = None
        else:
            entitlement.status = "REVOKED"
            entitlement.revoked_at = now

        response = AiProcessingEntitlementResponse(
            tenant_id=tenant_id,
            enabled=entitlement.status == "ACTIVE",
            agreement_reference=entitlement.agreement_reference,
            authorized_at=entitlement.authorized_at,
            revoked_at=entitlement.revoked_at,
        )
        _store_idempotent_response(
            session,
            principal=principal,
            operation=operation,
            key=idempotency_key,
            request_hash=request_hash,
            response=response,
        )
        _record_audit(
            session,
            principal=principal,
            action=(
                "AI_PROCESSING_ENTITLEMENT_ENABLED"
                if payload.enabled
                else "AI_PROCESSING_ENTITLEMENT_REVOKED"
            ),
            resource_type="tenant_ai_processing_entitlement",
            resource_id=entitlement.id,
            request_id=request.state.request_id,
            tenant_id=tenant_id,
        )
        session.commit()
        return response

    @application.post("/v1/uploads/presign", response_model=PresignUploadResponse, tags=["uploads"])
    async def presign_upload(
        payload: PresignUploadRequest,
        request: Request,
        principal: AuthenticatedPrincipal,
        session: DatabaseSession,
        idempotency_key: Annotated[str, Depends(_require_idempotency)],
    ) -> PresignUploadResponse:
        request_hash = _request_hash(payload)
        existing = _idempotent_response(
            session,
            principal=principal,
            operation="uploads.presign",
            key=idempotency_key,
            request_hash=request_hash,
        )
        if existing is not None:
            return PresignUploadResponse.model_validate(existing)
        upload_id = new_uuid7()
        safe_filename = _safe_filename(payload.filename, payload.content_type)
        object_key = f"tenants/{principal.tenant_id}/uploads/{upload_id}/{safe_filename}"
        expires_at = datetime.now(UTC) + timedelta(minutes=15)
        record = UploadRecord(
            id=str(upload_id),
            tenant_id=principal.tenant_id,
            object_key=object_key,
            filename=safe_filename,
            content_type=payload.content_type,
            size_bytes=payload.size_bytes,
            sha256=payload.sha256.lower(),
        )
        checksum_sha256 = base64.b64encode(bytes.fromhex(payload.sha256)).decode("ascii")
        artifact_store: ArtifactStore = application.state.artifact_store
        url = artifact_store.presign_upload(
            object_key=object_key,
            checksum_sha256=checksum_sha256,
            content_type=payload.content_type,
        )
        headers: dict[str, str] = {"Content-Type": payload.content_type}
        if runtime_settings.storage_flavor == "s3":
            # O header entra na assinatura só no S3; enviá-lo ao GCS faria o PUT falhar.
            headers["x-amz-checksum-sha256"] = checksum_sha256
        response = PresignUploadResponse(
            upload_id=upload_id,
            object_key=object_key,
            url=url,
            headers=headers,
            expires_at=expires_at,
        )
        session.add(record)
        _store_idempotent_response(
            session,
            principal=principal,
            operation="uploads.presign",
            key=idempotency_key,
            request_hash=request_hash,
            response=response,
        )
        _record_audit(
            session,
            principal=principal,
            action="UPLOAD_PRESIGNED",
            resource_type="upload",
            resource_id=str(upload_id),
            request_id=request.state.request_id,
        )
        session.commit()
        return response

    @application.post(
        "/v1/jobs", response_model=JobResponse, status_code=status.HTTP_201_CREATED, tags=["jobs"]
    )
    async def create_job(
        payload: CreateJobRequest,
        request: Request,
        principal: AuthenticatedPrincipal,
        session: DatabaseSession,
        idempotency_key: Annotated[str, Depends(_require_idempotency)],
    ) -> JobResponse:
        request_hash = _request_hash(payload)
        existing = _idempotent_response(
            session,
            principal=principal,
            operation="jobs.create",
            key=idempotency_key,
            request_hash=request_hash,
        )
        if existing is not None:
            response = JobResponse.model_validate(existing)
            try:
                application.state.queue.enqueue(
                    job_id=str(response.job_id), tenant_id=principal.tenant_id
                )
            except QUEUE_TRANSPORT_ERRORS as error:
                raise _problem(
                    "PROCESSING_UNAVAILABLE",
                    status.HTTP_503_SERVICE_UNAVAILABLE,
                    "Não foi possível iniciar o processamento; repita o mesmo comando.",
                ) from error
            return response
        upload = session.scalar(
            select(UploadRecord).where(
                UploadRecord.id == str(payload.upload_id),
                UploadRecord.tenant_id == principal.tenant_id,
            )
        )
        if upload is None:
            raise _problem("NOT_FOUND", status.HTTP_404_NOT_FOUND, "Upload não encontrado.")
        if upload.status != "PRESIGNED":
            raise _problem(
                "INVALID_UPLOAD", status.HTTP_422_UNPROCESSABLE_ENTITY, "Upload indisponível."
            )
        if upload.content_type != PDF_CONTENT_TYPE:
            # O presign passou a assinar mais de um tipo (o catálogo da medição é JSON), e
            # a conferência de tipo abaixo só compara o objeto com o que foi declarado —
            # ela não sabe o que ESTA rota aceita. O croqui continua sendo PDF e só.
            raise _problem(
                "INVALID_UPLOAD",
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "Upload precisa ser um PDF.",
            )

        expected_checksum = base64.b64encode(bytes.fromhex(upload.sha256)).decode("ascii")
        uploaded_object = application.state.artifact_store.head_upload(object_key=upload.object_key)
        # O checksum remoto não existe na interoperabilidade GCS. Tamanho e tipo continuam
        # conferidos aqui, e o digest é verificado pelo worker, que relê os bytes gravados
        # antes de qualquer processamento — a integridade não é dispensada, é adiada.
        checksum_deferred = runtime_settings.storage_flavor == "gcs"
        if (
            uploaded_object is None
            or uploaded_object.content_length != upload.size_bytes
            or uploaded_object.content_type.lower() != upload.content_type
            or (not checksum_deferred and uploaded_object.checksum_sha256 != expected_checksum)
        ):
            raise _problem(
                "INVALID_UPLOAD",
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "Upload ausente, incompleto ou com integridade divergente.",
            )

        now = datetime.now(UTC)
        expires_at = now + timedelta(days=7)
        project_id = new_uuid7()
        job_id = new_uuid7()
        project = ProjectRecord(
            id=str(project_id),
            tenant_id=principal.tenant_id,
            name=payload.project_name,
            default_unit=payload.default_unit.value,
            created_by=principal.subject,
            expires_at=expires_at,
        )
        job = JobRecord(
            id=str(job_id),
            tenant_id=principal.tenant_id,
            project_id=str(project_id),
            upload_id=str(payload.upload_id),
            status="UPLOADED",
            stage="VALIDATING",
            expires_at=expires_at,
            created_at=now,
            updated_at=now,
        )
        entitlement = _require_active_ai_entitlement(
            session,
            principal,
            real_providers_enabled=runtime_settings.real_providers_enabled,
        )
        upload.status = "VERIFIED"
        response = JobResponse(
            job_id=job_id,
            project_id=project_id,
            status=job.status,
            stage=job.stage,
            expires_at=expires_at,
            created_at=job.created_at,
            updated_at=job.updated_at,
        )
        # The parent row must exist before the child insert: without relationships the ORM
        # does not order these two mappers, and PostgreSQL enforces the foreign key.
        session.add(project)
        session.flush()
        session.add(job)
        session.flush()
        if entitlement is not None:
            session.add(
                AiProcessingAuthorizationRecord(
                    id=str(new_uuid7()),
                    tenant_id=principal.tenant_id,
                    job_id=str(job_id),
                    accepted_by=entitlement.authorized_by,
                    notice_version="contractual-entitlement-v1",
                    providers_json=["openai", "bedrock_anthropic", "textract"],
                    global_processing=True,
                    retention_days=7,
                    authorization_source="contract",
                    entitlement_id=entitlement.id,
                    agreement_reference=entitlement.agreement_reference,
                )
            )
        _store_idempotent_response(
            session,
            principal=principal,
            operation="jobs.create",
            key=idempotency_key,
            request_hash=request_hash,
            response=response,
        )
        _record_audit(
            session,
            principal=principal,
            action="JOB_CREATED",
            resource_type="job",
            resource_id=str(job_id),
            request_id=request.state.request_id,
        )
        if checksum_deferred:
            _record_audit(
                session,
                principal=principal,
                action="UPLOAD_CHECKSUM_DEFERRED_TO_WORKER",
                resource_type="upload",
                resource_id=str(payload.upload_id),
                request_id=request.state.request_id,
            )
        session.commit()
        queue: QueueAdapter = application.state.queue
        try:
            queue.enqueue(job_id=str(job_id), tenant_id=principal.tenant_id)
        except QUEUE_TRANSPORT_ERRORS as error:
            raise _problem(
                "PROCESSING_UNAVAILABLE",
                status.HTTP_503_SERVICE_UNAVAILABLE,
                "Job persistido; repita o mesmo comando para reenfileirar com segurança.",
            ) from error
        return response

    @application.get("/v1/jobs/{job_id}", response_model=JobResponse, tags=["jobs"])
    async def get_job(
        job_id: UUID,
        principal: AuthenticatedPrincipal,
        session: DatabaseSession,
    ) -> JobResponse:
        job = session.scalar(
            select(JobRecord).where(
                JobRecord.id == str(job_id), JobRecord.tenant_id == principal.tenant_id
            )
        )
        if job is None:
            raise _problem("NOT_FOUND", status.HTTP_404_NOT_FOUND, "Job não encontrado.")
        return JobResponse(
            job_id=UUID(job.id),
            project_id=UUID(job.project_id),
            status=job.status,
            stage=job.stage,
            expires_at=job.expires_at,
            page_count=job.page_count,
            failure_code=job.failure_code,
            created_at=job.created_at,
            updated_at=job.updated_at,
        )

    @application.get("/v1/jobs/{job_id}/review", response_model=ReviewResponse, tags=["review"])
    async def get_review(
        job_id: UUID,
        principal: AuthenticatedPrincipal,
        session: DatabaseSession,
    ) -> ReviewResponse:
        job = session.scalar(
            select(JobRecord).where(
                JobRecord.id == str(job_id), JobRecord.tenant_id == principal.tenant_id
            )
        )
        if job is None:
            raise _problem("NOT_FOUND", status.HTTP_404_NOT_FOUND, "Job não encontrado.")
        review = _latest_review(session, job_id=job_id, tenant_id=principal.tenant_id)
        if review is None:
            raise _problem(
                "JOB_NOT_READY",
                status.HTTP_409_CONFLICT,
                "Pacote de revisão ainda não está disponível.",
            )
        return _review_response(application, session, review)

    @application.post(
        "/v1/jobs/{job_id}/review/decisions", response_model=ReviewResponse, tags=["review"]
    )
    async def submit_review_decisions(
        job_id: UUID,
        payload: SubmitReviewDecisionsRequest,
        request: Request,
        principal: AuthenticatedPrincipal,
        session: DatabaseSession,
        idempotency_key: Annotated[str, Depends(_require_idempotency)],
    ) -> ReviewResponse:
        reviewer_role = _reviewer_role(principal)
        job = session.scalar(
            select(JobRecord).where(
                JobRecord.id == str(job_id), JobRecord.tenant_id == principal.tenant_id
            )
        )
        if job is None:
            raise _problem("NOT_FOUND", status.HTTP_404_NOT_FOUND, "Job não encontrado.")
        request_hash = _request_hash(payload)
        operation = f"review.decisions:{job_id}"
        existing = _idempotent_response(
            session,
            principal=principal,
            operation=operation,
            key=idempotency_key,
            request_hash=request_hash,
        )
        if existing is not None:
            return ReviewResponse.model_validate(existing)

        current = _latest_review(session, job_id=job_id, tenant_id=principal.tenant_id)
        if current is None:
            raise _problem(
                "JOB_NOT_READY",
                status.HTTP_409_CONFLICT,
                "Pacote de revisão ainda não está disponível.",
            )
        if current.version != payload.base_version:
            raise _problem(
                "REVISION_CONFLICT",
                status.HTTP_409_CONFLICT,
                "Existe uma revisão de leitura mais recente.",
            )

        packet = ReviewPacket.model_validate(current.packet_json)
        associations = AssociationSet.model_validate(current.associations_json)
        candidate_pairs = {
            (candidate.reading_id, candidate.proposal_id) for candidate in associations.candidates
        }
        selected_associations = dict(current.selected_associations_json)
        readings_by_id = {reading.id: reading for reading in packet.readings}
        # Decisão é ato único; corrigir o que já foi decidido tem comando próprio, que
        # sucede a decisão anterior em vez de sobrescrevê-la.
        if any(
            readings_by_id[command.reading_id].status
            in {ReadingStatus.CONFIRMED, ReadingStatus.REJECTED}
            for command in payload.decisions
            if command.reading_id in readings_by_id
        ):
            raise _problem(
                "READING_ALREADY_DECIDED",
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "A leitura já foi decidida. Para corrigir, use a correção declarada.",
            )
        batch_items: list[ReadingDecisionInput] = []
        for command in payload.decisions:
            _apply_association_rules(
                reading_id=command.reading_id,
                confirming=command.action in {"confirm", "correct"},
                annotation=command.annotation,
                association_proposal_id=command.association_proposal_id,
                candidate_pairs=candidate_pairs,
                selected_associations=selected_associations,
            )
            batch_items.append(
                ReadingDecisionInput(
                    reading_id=command.reading_id,
                    action="confirm" if command.action in {"confirm", "correct"} else "reject",
                    reviewer_id=principal.subject,
                    reviewer_role=reviewer_role,
                    decided_at=datetime.now(UTC),
                    note=command.justification,
                    raw_text=command.raw_text,
                    value_si=command.value_si,
                    unit=command.unit,
                    kind=command.kind,
                    written_decimals=command.written_decimals,
                    target_hint=command.target_hint,
                )
            )
        try:
            reviewed_packet = apply_reading_decisions(
                packet, ReadingDecisionBatch(decisions=batch_items)
            )
        except ValueError as error:
            raise _problem(
                "DOMAIN_VALIDATION_FAILED",
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "A leitura não pode receber outra decisão.",
            ) from error

        resolved = _resolve_scene_after_review_change(
            session,
            job_id=job_id,
            tenant_id=principal.tenant_id,
            current=current,
            reviewed_packet=reviewed_packet,
            selected_associations=selected_associations,
        )
        scene = resolved.scene
        parent_scene_id = resolved.parent_scene_id

        next_review = ReviewRevisionRecord(
            id=str(new_uuid7()),
            tenant_id=principal.tenant_id,
            job_id=str(job_id),
            version=current.version + 1,
            parent_review_id=current.id,
            packet_json=reviewed_packet.model_dump(mode="json"),
            associations_json=associations.model_dump(mode="json"),
            proposals_json=current.proposals_json,
            selected_associations_json=selected_associations,
            calibration_json=resolved.calibration_json,
            proposal_decisions_json=current.proposal_decisions_json,
            evidence_refs_json=current.evidence_refs_json,
            solver_request_json=current.solver_request_json,
            solver_blockers_json=resolved.blockers,
            required_blocker_codes_json=current.required_blocker_codes_json,
            required_criteria_texts_json=current.required_criteria_texts_json,
            created_by=principal.subject,
        )
        if scene is not None:
            session.add(
                RevisionRecord(
                    id=str(scene.id),
                    tenant_id=principal.tenant_id,
                    job_id=str(job_id),
                    version=scene.version,
                    parent_revision_id=parent_scene_id,
                    scene=scene.model_dump(mode="json"),
                    created_by="rectangle-solver-v1",
                )
            )
            next_review.scene_revision_id = str(scene.id)
            session.flush()
        session.add(next_review)
        session.flush()
        decided_readings = {reading.id: reading for reading in reviewed_packet.readings}
        for command in payload.decisions:
            recorded = decided_readings[command.reading_id].decision
            session.add(
                ReviewDecisionRecord(
                    id=str(new_uuid7()),
                    tenant_id=principal.tenant_id,
                    job_id=str(job_id),
                    review_revision_id=next_review.id,
                    reading_id=command.reading_id,
                    action=command.action,
                    reviewer_id=principal.subject,
                    reviewer_role=reviewer_role,
                    association_proposal_id=command.association_proposal_id,
                    # O índice de auditoria passa a citar a decisão gravada no pacote;
                    # sem o id, uma correção declarada não teria alvo verificável.
                    decision_id=recorded.decision_id if recorded is not None else None,
                )
            )
        try:
            session.flush()
        except IntegrityError as error:
            session.rollback()
            raise _problem(
                "REVISION_CONFLICT",
                status.HTTP_409_CONFLICT,
                "Uma decisão concorrente criou uma revisão mais recente.",
            ) from error
        response = _review_response(application, session, next_review)
        _store_idempotent_response(
            session,
            principal=principal,
            operation=operation,
            key=idempotency_key,
            request_hash=request_hash,
            response=response,
        )
        _record_audit(
            session,
            principal=principal,
            action="REVIEW_DECISIONS_RECORDED",
            resource_type="review_revision",
            resource_id=next_review.id,
            request_id=request.state.request_id,
        )
        session.commit()
        return response

    @application.post(
        "/v1/jobs/{job_id}/review/rectifications", response_model=ReviewResponse, tags=["review"]
    )
    async def rectify_review_decisions(
        job_id: UUID,
        payload: RectifyReviewDecisionsRequest,
        request: Request,
        principal: AuthenticatedPrincipal,
        session: DatabaseSession,
        idempotency_key: Annotated[str, Depends(_require_idempotency)],
    ) -> ReviewResponse:
        """Corrige decisões já registradas criando uma revisão nova, nunca editando.

        A decisão anterior continua no `packet_json` da revisão parental e no índice
        append-only. O que já foi desenhado sobre ela não é apagado nem reprojetado: a
        cena mais recente ganha a issue crítica `READING_DECISION_SUPERSEDED` e o export
        fica bloqueado até o profissional refazer o traçado daquela parte. Aprovação e
        pacote já publicados não são tocados.
        """
        reviewer_role = _reviewer_role(principal)
        job = session.scalar(
            select(JobRecord).where(
                JobRecord.id == str(job_id), JobRecord.tenant_id == principal.tenant_id
            )
        )
        if job is None:
            raise _problem("NOT_FOUND", status.HTTP_404_NOT_FOUND, "Job não encontrado.")
        request_hash = _request_hash(payload)
        operation = f"review.rectifications:{job_id}"
        existing = _idempotent_response(
            session,
            principal=principal,
            operation=operation,
            key=idempotency_key,
            request_hash=request_hash,
        )
        if existing is not None:
            return ReviewResponse.model_validate(existing)

        current = _latest_review(session, job_id=job_id, tenant_id=principal.tenant_id)
        if current is None:
            raise _problem(
                "JOB_NOT_READY",
                status.HTTP_409_CONFLICT,
                "Pacote de revisão ainda não está disponível.",
            )
        if current.version != payload.base_version:
            raise _problem(
                "REVISION_CONFLICT",
                status.HTTP_409_CONFLICT,
                "Existe uma revisão de leitura mais recente.",
            )

        packet = ReviewPacket.model_validate(current.packet_json)
        associations = AssociationSet.model_validate(current.associations_json)
        candidate_pairs = {
            (candidate.reading_id, candidate.proposal_id) for candidate in associations.candidates
        }
        selected_associations = dict(current.selected_associations_json)
        readings_by_id = {reading.id: reading for reading in packet.readings}
        batch_items: list[ReadingRectificationInput] = []
        for command in payload.rectifications:
            reading = readings_by_id.get(command.reading_id)
            if reading is None:
                raise _problem(
                    "DOMAIN_VALIDATION_FAILED",
                    status.HTTP_422_UNPROCESSABLE_ENTITY,
                    "A leitura não pertence ao pacote desta revisão.",
                )
            if reading.decision is None or reading.status not in {
                ReadingStatus.CONFIRMED,
                ReadingStatus.REJECTED,
            }:
                raise _problem(
                    "READING_NOT_DECIDED",
                    status.HTTP_422_UNPROCESSABLE_ENTITY,
                    "Esta leitura ainda não foi decidida; use a decisão normal.",
                )
            if command.rectifies_decision_id != reading.decision.decision_id:
                raise _problem(
                    "RECTIFICATION_TARGET_STALE",
                    status.HTTP_409_CONFLICT,
                    "A decisão corrigida não é a vigente desta leitura; recarregue a revisão.",
                )
            previous_association = selected_associations.get(command.reading_id)
            _apply_association_rules(
                reading_id=command.reading_id,
                confirming=command.action == "confirm",
                annotation=command.annotation,
                association_proposal_id=command.association_proposal_id,
                candidate_pairs=candidate_pairs,
                selected_associations=selected_associations,
            )
            if _rectification_changes_nothing(
                reading,
                command,
                previous_association=previous_association,
                next_association=selected_associations.get(command.reading_id),
            ):
                raise _problem(
                    "RECTIFICATION_ALREADY_APPLIED",
                    status.HTTP_422_UNPROCESSABLE_ENTITY,
                    "A correção não muda nada no registro vigente desta leitura.",
                )
            batch_items.append(
                ReadingRectificationInput(
                    reading_id=command.reading_id,
                    action=command.action,
                    rectifies_decision_id=command.rectifies_decision_id,
                    reviewer_id=principal.subject,
                    reviewer_role=reviewer_role,
                    decided_at=datetime.now(UTC),
                    note=command.justification,
                    raw_text=command.raw_text,
                    value_si=command.value_si,
                    unit=command.unit,
                    kind=command.kind,
                    written_decimals=command.written_decimals,
                    target_hint=command.target_hint,
                )
            )
        try:
            rectified_packet = rectify_reading_decisions(
                packet, ReadingRectificationBatch(rectifications=batch_items)
            )
        except ValueError as error:
            raise _problem(
                "DOMAIN_VALIDATION_FAILED",
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "A correção não pôde ser registrada sobre esta leitura.",
            ) from error

        resolved = _resolve_scene_after_review_change(
            session,
            job_id=job_id,
            tenant_id=principal.tenant_id,
            current=current,
            reviewed_packet=rectified_packet,
            selected_associations=selected_associations,
        )
        scene = resolved.scene
        parent_scene_id = resolved.parent_scene_id
        rectified_decision_ids = {
            command.rectifies_decision_id for command in payload.rectifications
        }
        if scene is not None:
            # Uma única cena nova por request: se a calibração também caiu, as duas
            # issues críticas convivem nela.
            held = _entities_holding_decisions(scene, rectified_decision_ids)
            if held:
                scene = _with_critical_issue(
                    scene,
                    code=READING_DECISION_SUPERSEDED_CODE,
                    message=READING_DECISION_SUPERSEDED_MESSAGE,
                    entity_ids=held,
                )
        else:
            latest_scene_record = _latest_scene(
                session, job_id=job_id, tenant_id=principal.tenant_id
            )
            if latest_scene_record is not None:
                latest_scene = SceneRevision.model_validate(latest_scene_record.scene)
                held = _entities_holding_decisions(latest_scene, rectified_decision_ids)
                if held:
                    # A cena existente nunca é editada — nem para receber a issue. A
                    # geometria viaja intacta para a revisão nova, que nasce não aprovada.
                    scene = _with_critical_issue(
                        SceneRevision.model_validate(
                            {
                                **latest_scene.model_dump(mode="json"),
                                "id": str(new_uuid7()),
                                "version": latest_scene.version + 1,
                                "approved": False,
                            }
                        ),
                        code=READING_DECISION_SUPERSEDED_CODE,
                        message=READING_DECISION_SUPERSEDED_MESSAGE,
                        entity_ids=held,
                    )
                    parent_scene_id = latest_scene_record.id

        next_review = ReviewRevisionRecord(
            id=str(new_uuid7()),
            tenant_id=principal.tenant_id,
            job_id=str(job_id),
            version=current.version + 1,
            parent_review_id=current.id,
            packet_json=rectified_packet.model_dump(mode="json"),
            associations_json=associations.model_dump(mode="json"),
            proposals_json=current.proposals_json,
            selected_associations_json=selected_associations,
            calibration_json=resolved.calibration_json,
            proposal_decisions_json=current.proposal_decisions_json,
            # O aceite de traçado é ato histórico da revisão em que aconteceu: viaja
            # verbatim, nunca "atualizado" pela correção.
            trace_acceptance_json=current.trace_acceptance_json,
            evidence_refs_json=current.evidence_refs_json,
            solver_request_json=current.solver_request_json,
            solver_blockers_json=resolved.blockers,
            required_blocker_codes_json=current.required_blocker_codes_json,
            required_criteria_texts_json=current.required_criteria_texts_json,
            created_by=principal.subject,
        )
        if scene is not None:
            session.add(
                RevisionRecord(
                    id=str(scene.id),
                    tenant_id=principal.tenant_id,
                    job_id=str(job_id),
                    version=scene.version,
                    parent_revision_id=parent_scene_id,
                    scene=scene.model_dump(mode="json"),
                    created_by=principal.subject,
                )
            )
            next_review.scene_revision_id = str(scene.id)
            session.flush()
        else:
            next_review.scene_revision_id = current.scene_revision_id
        session.add(next_review)
        session.flush()
        rectified_readings = {reading.id: reading for reading in rectified_packet.readings}
        for command in payload.rectifications:
            recorded = rectified_readings[command.reading_id].decision
            session.add(
                ReviewDecisionRecord(
                    id=str(new_uuid7()),
                    tenant_id=principal.tenant_id,
                    job_id=str(job_id),
                    review_revision_id=next_review.id,
                    reading_id=command.reading_id,
                    action=f"rectify_{command.action}",
                    reviewer_id=principal.subject,
                    reviewer_role=reviewer_role,
                    association_proposal_id=command.association_proposal_id,
                    decision_id=recorded.decision_id if recorded is not None else None,
                    rectifies_decision_id=command.rectifies_decision_id,
                )
            )
        try:
            session.flush()
        except IntegrityError as error:
            session.rollback()
            raise _problem(
                "REVISION_CONFLICT",
                status.HTTP_409_CONFLICT,
                "Uma decisão concorrente criou uma revisão mais recente.",
            ) from error
        response = _review_response(application, session, next_review)
        _store_idempotent_response(
            session,
            principal=principal,
            operation=operation,
            key=idempotency_key,
            request_hash=request_hash,
            response=response,
        )
        _record_audit(
            session,
            principal=principal,
            action="REVIEW_DECISIONS_RECTIFIED",
            resource_type="review_revision",
            resource_id=next_review.id,
            request_id=request.state.request_id,
        )
        session.commit()
        return response

    @application.post(
        "/v1/jobs/{job_id}/review/calibration",
        response_model=ReviewResponse,
        tags=["review"],
    )
    async def create_proposal_calibration(
        job_id: UUID,
        payload: CreateProposalCalibrationRequest,
        request: Request,
        principal: AuthenticatedPrincipal,
        session: DatabaseSession,
        idempotency_key: Annotated[str, Depends(_require_idempotency)],
    ) -> ReviewResponse:
        _reviewer_role(principal)
        job = session.scalar(
            select(JobRecord).where(
                JobRecord.id == str(job_id), JobRecord.tenant_id == principal.tenant_id
            )
        )
        if job is None:
            raise _problem("NOT_FOUND", status.HTTP_404_NOT_FOUND, "Job não encontrado.")
        operation = f"review.proposal-calibration:{job_id}"
        request_hash = _request_hash(payload)
        existing = _idempotent_response(
            session,
            principal=principal,
            operation=operation,
            key=idempotency_key,
            request_hash=request_hash,
        )
        if existing is not None:
            return ReviewResponse.model_validate(existing)
        current = _latest_review(session, job_id=job_id, tenant_id=principal.tenant_id)
        if current is None or current.proposals_json is None:
            raise _problem(
                "PROPOSALS_NOT_READY",
                status.HTTP_409_CONFLICT,
                "Snapshot de propostas ainda não está disponível.",
            )
        if current.version != payload.base_review_version:
            raise _problem(
                "REVISION_CONFLICT",
                status.HTTP_409_CONFLICT,
                "Existe uma revisão de propostas mais recente.",
            )
        scene_record = _latest_scene(session, job_id=job_id, tenant_id=principal.tenant_id)
        if scene_record is None:
            raise _problem(
                "JOB_NOT_READY", status.HTTP_409_CONFLICT, "Cena ainda não está disponível."
            )
        if scene_record.version != payload.base_scene_version:
            raise _problem(
                "REVISION_CONFLICT",
                status.HTTP_409_CONFLICT,
                "Existe uma cena mais recente para calibração.",
            )
        proposals = VisionProposalSet.model_validate(current.proposals_json)
        scene = SceneRevision.model_validate(scene_record.scene)
        anchors = [
            CalibrationAnchor(
                proposal_id=anchor.proposal_id,
                entity_id=anchor.entity_id,
                reversed=anchor.reversed,
            )
            for anchor in payload.anchors
        ]
        try:
            transform, resolved = resolve_calibration(proposals, scene, anchors, mode=payload.mode)
        except CalibrationError as error:
            raise _problem(
                "CALIBRATION_INVALID",
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                str(error),
            ) from error
        calibration_id = new_uuid7()
        calibration = _calibration_payload(
            calibration_id=calibration_id,
            scene_revision_id=UUID(scene_record.id),
            scene_version=scene_record.version,
            # O sentido gravado é o que o ajuste escolheu, não o que veio no request:
            # é ele que a revalidação de deriva precisa reproduzir.
            anchors=[
                ProposalCalibrationAnchorRequest(
                    proposal_id=anchor.proposal_id,
                    entity_id=anchor.entity_id,
                    reversed=anchor.reversed,
                )
                for anchor in resolved
            ],
            transform=transform,
        )
        next_review = ReviewRevisionRecord(
            id=str(new_uuid7()),
            tenant_id=principal.tenant_id,
            job_id=str(job_id),
            version=current.version + 1,
            parent_review_id=current.id,
            packet_json=current.packet_json,
            associations_json=current.associations_json,
            proposals_json=current.proposals_json,
            selected_associations_json=current.selected_associations_json,
            calibration_json=calibration.model_dump(mode="json"),
            proposal_decisions_json=current.proposal_decisions_json,
            evidence_refs_json=current.evidence_refs_json,
            solver_request_json=current.solver_request_json,
            solver_blockers_json=current.solver_blockers_json,
            required_blocker_codes_json=current.required_blocker_codes_json,
            required_criteria_texts_json=current.required_criteria_texts_json,
            scene_revision_id=scene_record.id,
            created_by=principal.subject,
        )
        session.add(next_review)
        try:
            session.flush()
        except IntegrityError as error:
            session.rollback()
            raise _problem(
                "REVISION_CONFLICT",
                status.HTTP_409_CONFLICT,
                "Uma atualização concorrente criou nova revisão.",
            ) from error
        response = _review_response(application, session, next_review)
        _store_idempotent_response(
            session,
            principal=principal,
            operation=operation,
            key=idempotency_key,
            request_hash=request_hash,
            response=response,
        )
        _record_audit(
            session,
            principal=principal,
            action="PROPOSAL_CALIBRATION_RECORDED",
            resource_type="review_revision",
            resource_id=next_review.id,
            request_id=request.state.request_id,
        )
        session.commit()
        return response

    @application.post(
        "/v1/jobs/{job_id}/review/proposals",
        response_model=ReviewResponse,
        tags=["review"],
    )
    async def decide_proposal(
        job_id: UUID,
        payload: DecideProposalRequest,
        request: Request,
        principal: AuthenticatedPrincipal,
        session: DatabaseSession,
        idempotency_key: Annotated[str, Depends(_require_idempotency)],
    ) -> ReviewResponse:
        reviewer_role = _reviewer_role(principal)
        job = session.scalar(
            select(JobRecord).where(
                JobRecord.id == str(job_id), JobRecord.tenant_id == principal.tenant_id
            )
        )
        if job is None:
            raise _problem("NOT_FOUND", status.HTTP_404_NOT_FOUND, "Job não encontrado.")
        operation = f"review.proposal-decision:{job_id}"
        request_hash = _request_hash(payload)
        existing = _idempotent_response(
            session,
            principal=principal,
            operation=operation,
            key=idempotency_key,
            request_hash=request_hash,
        )
        if existing is not None:
            return ReviewResponse.model_validate(existing)
        current = _latest_review(session, job_id=job_id, tenant_id=principal.tenant_id)
        if current is None or current.proposals_json is None:
            raise _problem(
                "PROPOSALS_NOT_READY",
                status.HTTP_409_CONFLICT,
                "Snapshot de propostas ainda não está disponível.",
            )
        if current.version != payload.base_review_version:
            raise _problem(
                "REVISION_CONFLICT",
                status.HTTP_409_CONFLICT,
                "Existe uma revisão de propostas mais recente.",
            )
        scene_record = _latest_scene(session, job_id=job_id, tenant_id=principal.tenant_id)
        if scene_record is None or scene_record.version != payload.base_scene_version:
            raise _problem(
                "REVISION_CONFLICT",
                status.HTTP_409_CONFLICT,
                "Existe uma cena mais recente para a decisão.",
            )
        proposals = VisionProposalSet.model_validate(current.proposals_json)
        proposal = next(
            (item for item in proposals.proposals if item.id == payload.proposal_id), None
        )
        if proposal is None:
            raise _problem(
                "DOMAIN_VALIDATION_FAILED",
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "A proposta não pertence ao snapshot da revisão.",
            )
        decisions = list(current.proposal_decisions_json or [])
        if any(decision.get("proposal_id") == payload.proposal_id for decision in decisions):
            raise _problem(
                "PROPOSAL_ALREADY_DECIDED",
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "A proposta já recebeu decisão e permanece no histórico.",
            )

        current_scene = SceneRevision.model_validate(scene_record.scene)
        next_scene: SceneRevision | None = None
        calibration_id: UUID | None = None
        if payload.action == "accept":
            calibration = _calibration_response(current.calibration_json)
            if calibration is None or payload.calibration_id != calibration.calibration_id:
                raise _problem(
                    "CALIBRATION_REQUIRED",
                    status.HTTP_422_UNPROCESSABLE_ENTITY,
                    "Aceitar proposta exige a calibração confirmada da revisão atual.",
                )
            if calibration.scene_revision_id != UUID(scene_record.id):
                anchor_ids = {anchor.entity_id for anchor in calibration.anchors}
                current_ids = {entity.id for entity in current_scene.entities}
                if not anchor_ids <= current_ids:
                    raise _problem(
                        "CALIBRATION_STALE",
                        status.HTTP_409_CONFLICT,
                        "Os anchors da calibração não existem na cena atual.",
                    )
            transform = _transform_from_calibration(calibration)
            next_review_id = new_uuid7()
            try:
                entity = approximate_entity_from_proposal(
                    proposal,
                    transform,
                    calibration_id=calibration.calibration_id,
                    review_id=next_review_id,
                )
            except CalibrationError as error:
                raise _problem(
                    "CALIBRATION_INVALID", status.HTTP_422_UNPROCESSABLE_ENTITY, str(error)
                ) from error
            next_scene = SceneRevision.model_validate(
                {
                    **current_scene.model_dump(mode="json"),
                    "id": str(new_uuid7()),
                    "version": current_scene.version + 1,
                    "entities": [
                        *[item.model_dump(mode="json") for item in current_scene.entities],
                        entity.model_dump(mode="json"),
                    ],
                    "issues": [
                        *[item.model_dump(mode="json") for item in current_scene.issues],
                        *_out_of_scale_issue(current_scene, transform),
                    ],
                }
            )
            review_id = next_review_id
            calibration_id = calibration.calibration_id
            decision = ProposalDecisionResponse(
                proposal_id=payload.proposal_id,
                action="accept",
                entity_id=entity.id,
                calibration_id=calibration_id,
            )
        else:
            if payload.calibration_id is not None:
                raise _problem(
                    "DOMAIN_VALIDATION_FAILED",
                    status.HTTP_422_UNPROCESSABLE_ENTITY,
                    "Rejeição não aceita uma calibração.",
                )
            review_id = new_uuid7()
            decision = ProposalDecisionResponse(proposal_id=payload.proposal_id, action="reject")
        decisions.append(
            {**decision.model_dump(mode="json"), "justification": payload.justification}
        )
        next_review = ReviewRevisionRecord(
            id=str(review_id),
            tenant_id=principal.tenant_id,
            job_id=str(job_id),
            version=current.version + 1,
            parent_review_id=current.id,
            packet_json=current.packet_json,
            associations_json=current.associations_json,
            proposals_json=current.proposals_json,
            selected_associations_json=current.selected_associations_json,
            calibration_json=current.calibration_json,
            proposal_decisions_json=decisions,
            evidence_refs_json=current.evidence_refs_json,
            solver_request_json=current.solver_request_json,
            solver_blockers_json=current.solver_blockers_json,
            required_blocker_codes_json=current.required_blocker_codes_json,
            required_criteria_texts_json=current.required_criteria_texts_json,
            scene_revision_id=str(next_scene.id) if next_scene is not None else scene_record.id,
            created_by=principal.subject,
        )
        if next_scene is not None:
            session.add(
                RevisionRecord(
                    id=str(next_scene.id),
                    tenant_id=principal.tenant_id,
                    job_id=str(job_id),
                    version=next_scene.version,
                    parent_revision_id=scene_record.id,
                    scene=next_scene.model_dump(mode="json"),
                    created_by=principal.subject,
                )
            )
            session.flush()
        session.add(next_review)
        session.flush()
        session.add(
            ProposalDecisionRecord(
                id=str(new_uuid7()),
                tenant_id=principal.tenant_id,
                job_id=str(job_id),
                review_revision_id=next_review.id,
                proposal_id=payload.proposal_id,
                action=payload.action,
                reviewer_id=principal.subject,
                reviewer_role=reviewer_role,
                scene_revision_id=str(next_scene.id) if next_scene is not None else None,
            )
        )
        try:
            session.flush()
        except IntegrityError as error:
            session.rollback()
            raise _problem(
                "REVISION_CONFLICT",
                status.HTTP_409_CONFLICT,
                "Uma atualização concorrente criou nova revisão.",
            ) from error
        response = _review_response(application, session, next_review)
        _store_idempotent_response(
            session,
            principal=principal,
            operation=operation,
            key=idempotency_key,
            request_hash=request_hash,
            response=response,
        )
        _record_audit(
            session,
            principal=principal,
            action="PROPOSAL_DECISION_RECORDED",
            resource_type="review_revision",
            resource_id=next_review.id,
            request_id=request.state.request_id,
        )
        session.commit()
        return response

    @application.post(
        "/v1/jobs/{job_id}/review/proposals/batch",
        response_model=ReviewResponse,
        tags=["review"],
    )
    async def decide_proposal_batch(
        job_id: UUID,
        payload: DecideProposalBatchRequest,
        request: Request,
        principal: AuthenticatedPrincipal,
        session: DatabaseSession,
        idempotency_key: Annotated[str, Depends(_require_idempotency)],
    ) -> ReviewResponse:
        reviewer_role = _reviewer_role(principal)
        job = session.scalar(
            select(JobRecord).where(
                JobRecord.id == str(job_id), JobRecord.tenant_id == principal.tenant_id
            )
        )
        if job is None:
            raise _problem("NOT_FOUND", status.HTTP_404_NOT_FOUND, "Job não encontrado.")
        operation = f"review.proposal-batch:{job_id}"
        request_hash = _request_hash(payload)
        existing = _idempotent_response(
            session,
            principal=principal,
            operation=operation,
            key=idempotency_key,
            request_hash=request_hash,
        )
        if existing is not None:
            return ReviewResponse.model_validate(existing)
        current = _latest_review(session, job_id=job_id, tenant_id=principal.tenant_id)
        if current is None or current.proposals_json is None:
            raise _problem(
                "PROPOSALS_NOT_READY",
                status.HTTP_409_CONFLICT,
                "Snapshot de propostas ainda não está disponível.",
            )
        if current.version != payload.base_review_version:
            raise _problem(
                "REVISION_CONFLICT",
                status.HTTP_409_CONFLICT,
                "Existe uma revisão de propostas mais recente.",
            )
        scene_record = _latest_scene(session, job_id=job_id, tenant_id=principal.tenant_id)
        if scene_record is None or scene_record.version != payload.base_scene_version:
            raise _problem(
                "REVISION_CONFLICT",
                status.HTTP_409_CONFLICT,
                "Existe uma cena mais recente para a decisão.",
            )
        requested = payload.proposal_ids
        if len(set(requested)) != len(requested):
            raise _problem(
                "DOMAIN_VALIDATION_FAILED",
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "O lote repete a mesma proposta.",
            )
        proposals = VisionProposalSet.model_validate(current.proposals_json)
        by_id = {item.id: item for item in proposals.proposals}
        unknown = [item for item in requested if item not in by_id]
        if unknown:
            raise _problem(
                "DOMAIN_VALIDATION_FAILED",
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                f"{len(unknown)} propostas não pertencem ao snapshot da revisão.",
            )
        decisions = list(current.proposal_decisions_json or [])
        already = {decision.get("proposal_id") for decision in decisions}
        repeated = [item for item in requested if item in already]
        if repeated:
            raise _problem(
                "PROPOSAL_ALREADY_DECIDED",
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                f"{len(repeated)} propostas do lote já receberam decisão.",
            )

        current_scene = SceneRevision.model_validate(scene_record.scene)
        next_scene: SceneRevision | None = None
        review_id = new_uuid7()
        batch: list[ProposalDecisionResponse] = []
        if payload.action == "accept":
            calibration = _calibration_response(current.calibration_json)
            if calibration is None or payload.calibration_id != calibration.calibration_id:
                raise _problem(
                    "CALIBRATION_REQUIRED",
                    status.HTTP_422_UNPROCESSABLE_ENTITY,
                    "Aceitar proposta exige a calibração confirmada da revisão atual.",
                )
            if calibration.scene_revision_id != UUID(scene_record.id):
                anchor_ids = {anchor.entity_id for anchor in calibration.anchors}
                if not anchor_ids <= {entity.id for entity in current_scene.entities}:
                    raise _problem(
                        "CALIBRATION_STALE",
                        status.HTTP_409_CONFLICT,
                        "Os anchors da calibração não existem na cena atual.",
                    )
            transform = _transform_from_calibration(calibration)
            entities = []
            for proposal_id in requested:
                try:
                    entity = approximate_entity_from_proposal(
                        by_id[proposal_id],
                        transform,
                        calibration_id=calibration.calibration_id,
                        review_id=review_id,
                    )
                except CalibrationError as error:
                    # Falha em qualquer proposta invalida o lote inteiro: meia cena
                    # traçada seria pior do que nenhuma.
                    raise _problem(
                        "CALIBRATION_INVALID",
                        status.HTTP_422_UNPROCESSABLE_ENTITY,
                        f"{proposal_id}: {error}",
                    ) from error
                entities.append(entity)
                batch.append(
                    ProposalDecisionResponse(
                        proposal_id=proposal_id,
                        action="accept",
                        entity_id=entity.id,
                        calibration_id=calibration.calibration_id,
                    )
                )
            next_scene = SceneRevision.model_validate(
                {
                    **current_scene.model_dump(mode="json"),
                    "id": str(new_uuid7()),
                    "version": current_scene.version + 1,
                    "entities": [
                        *[item.model_dump(mode="json") for item in current_scene.entities],
                        *[item.model_dump(mode="json") for item in entities],
                    ],
                    "issues": [
                        *[item.model_dump(mode="json") for item in current_scene.issues],
                        *_out_of_scale_issue(current_scene, transform),
                    ],
                }
            )
        else:
            if payload.calibration_id is not None:
                raise _problem(
                    "DOMAIN_VALIDATION_FAILED",
                    status.HTTP_422_UNPROCESSABLE_ENTITY,
                    "Rejeição não aceita uma calibração.",
                )
            batch = [
                ProposalDecisionResponse(proposal_id=proposal_id, action="reject")
                for proposal_id in requested
            ]
        decisions.extend(
            {**decision.model_dump(mode="json"), "justification": payload.justification}
            for decision in batch
        )
        next_review = ReviewRevisionRecord(
            id=str(review_id),
            tenant_id=principal.tenant_id,
            job_id=str(job_id),
            version=current.version + 1,
            parent_review_id=current.id,
            packet_json=current.packet_json,
            associations_json=current.associations_json,
            proposals_json=current.proposals_json,
            selected_associations_json=current.selected_associations_json,
            calibration_json=current.calibration_json,
            proposal_decisions_json=decisions,
            evidence_refs_json=current.evidence_refs_json,
            solver_request_json=current.solver_request_json,
            solver_blockers_json=current.solver_blockers_json,
            required_blocker_codes_json=current.required_blocker_codes_json,
            required_criteria_texts_json=current.required_criteria_texts_json,
            scene_revision_id=str(next_scene.id) if next_scene is not None else scene_record.id,
            created_by=principal.subject,
        )
        if next_scene is not None:
            session.add(
                RevisionRecord(
                    id=str(next_scene.id),
                    tenant_id=principal.tenant_id,
                    job_id=str(job_id),
                    version=next_scene.version,
                    parent_revision_id=scene_record.id,
                    scene=next_scene.model_dump(mode="json"),
                    created_by=principal.subject,
                )
            )
            session.flush()
        session.add(next_review)
        session.flush()
        for decision in batch:
            session.add(
                ProposalDecisionRecord(
                    id=str(new_uuid7()),
                    tenant_id=principal.tenant_id,
                    job_id=str(job_id),
                    review_revision_id=next_review.id,
                    proposal_id=decision.proposal_id,
                    action=payload.action,
                    reviewer_id=principal.subject,
                    reviewer_role=reviewer_role,
                    scene_revision_id=str(next_scene.id) if next_scene is not None else None,
                )
            )
        try:
            session.flush()
        except IntegrityError as error:
            session.rollback()
            raise _problem(
                "REVISION_CONFLICT",
                status.HTTP_409_CONFLICT,
                "Uma atualização concorrente criou nova revisão.",
            ) from error
        response = _review_response(application, session, next_review)
        _store_idempotent_response(
            session,
            principal=principal,
            operation=operation,
            key=idempotency_key,
            request_hash=request_hash,
            response=response,
        )
        _record_audit(
            session,
            principal=principal,
            action="PROPOSAL_BATCH_DECISION_RECORDED",
            resource_type="review_revision",
            resource_id=next_review.id,
            request_id=request.state.request_id,
        )
        session.commit()
        return response

    @application.post(
        "/v1/jobs/{job_id}/review/dimensions",
        response_model=ReviewResponse,
        tags=["review"],
    )
    async def annotate_dimension(
        job_id: UUID,
        payload: AnnotateDimensionRequest,
        request: Request,
        principal: AuthenticatedPrincipal,
        session: DatabaseSession,
        idempotency_key: Annotated[str, Depends(_require_idempotency)],
    ) -> ReviewResponse:
        _reviewer_role(principal)
        job = session.scalar(
            select(JobRecord).where(
                JobRecord.id == str(job_id), JobRecord.tenant_id == principal.tenant_id
            )
        )
        if job is None:
            raise _problem("NOT_FOUND", status.HTTP_404_NOT_FOUND, "Job não encontrado.")
        operation = f"review.dimension:{job_id}"
        request_hash = _request_hash(payload)
        existing = _idempotent_response(
            session,
            principal=principal,
            operation=operation,
            key=idempotency_key,
            request_hash=request_hash,
        )
        if existing is not None:
            return ReviewResponse.model_validate(existing)
        current, scene_record, current_scene, reading = _annotation_target(
            session,
            job_id=job_id,
            tenant_id=principal.tenant_id,
            base_review_version=payload.base_review_version,
            base_scene_version=payload.base_scene_version,
            reading_id=payload.reading_id,
        )
        if reading.value_si is None or reading.decision is None:
            raise _problem(
                "DOMAIN_VALIDATION_FAILED",
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "A cota precisa de um valor confirmado.",
            )
        try:
            adjusted, dimension, measurement = annotate_traced_line(
                current_scene,
                entity_id=payload.entity_id,
                reading_id=reading.id,
                decision_id=reading.decision.decision_id,
                value_si=reading.value_si,
                written_decimals=reading.written_decimals,
                kind=reading.kind,
            )
        except DimensionAnnotationError as error:
            raise _problem(
                "DOMAIN_VALIDATION_FAILED", status.HTTP_422_UNPROCESSABLE_ENTITY, str(error)
            ) from error
        next_scene = SceneRevision.model_validate(
            {
                **current_scene.model_dump(mode="json"),
                "id": str(new_uuid7()),
                "version": current_scene.version + 1,
                "entities": [
                    *[
                        (adjusted if item.id == adjusted.id else item).model_dump(mode="json")
                        for item in current_scene.entities
                    ],
                    dimension.model_dump(mode="json"),
                ],
                "measurements": [
                    *[item.model_dump(mode="json") for item in current_scene.measurements],
                    measurement.model_dump(mode="json"),
                ],
            }
        )
        next_review = ReviewRevisionRecord(
            id=str(new_uuid7()),
            tenant_id=principal.tenant_id,
            job_id=str(job_id),
            version=current.version + 1,
            parent_review_id=current.id,
            packet_json=current.packet_json,
            associations_json=current.associations_json,
            proposals_json=current.proposals_json,
            selected_associations_json=current.selected_associations_json,
            calibration_json=current.calibration_json,
            proposal_decisions_json=current.proposal_decisions_json,
            evidence_refs_json=current.evidence_refs_json,
            solver_request_json=current.solver_request_json,
            solver_blockers_json=current.solver_blockers_json,
            required_blocker_codes_json=current.required_blocker_codes_json,
            required_criteria_texts_json=current.required_criteria_texts_json,
            scene_revision_id=str(next_scene.id),
            created_by=principal.subject,
        )
        session.add(
            RevisionRecord(
                id=str(next_scene.id),
                tenant_id=principal.tenant_id,
                job_id=str(job_id),
                version=next_scene.version,
                parent_revision_id=scene_record.id,
                scene=next_scene.model_dump(mode="json"),
                created_by=principal.subject,
            )
        )
        session.flush()
        session.add(next_review)
        try:
            session.flush()
        except IntegrityError as error:
            session.rollback()
            raise _problem(
                "REVISION_CONFLICT",
                status.HTTP_409_CONFLICT,
                "Uma atualização concorrente criou nova revisão.",
            ) from error
        response = _review_response(application, session, next_review)
        _store_idempotent_response(
            session,
            principal=principal,
            operation=operation,
            key=idempotency_key,
            request_hash=request_hash,
            response=response,
        )
        _record_audit(
            session,
            principal=principal,
            action="DIMENSION_ANNOTATED",
            resource_type="scene_revision",
            resource_id=str(next_scene.id),
            request_id=request.state.request_id,
        )
        session.commit()
        return response

    @application.post(
        "/v1/jobs/{job_id}/review/notes",
        response_model=ReviewResponse,
        tags=["review"],
    )
    async def annotate_note_endpoint(
        job_id: UUID,
        payload: AnnotateNoteRequest,
        request: Request,
        principal: AuthenticatedPrincipal,
        session: DatabaseSession,
        idempotency_key: Annotated[str, Depends(_require_idempotency)],
    ) -> ReviewResponse:
        _reviewer_role(principal)
        job = session.scalar(
            select(JobRecord).where(
                JobRecord.id == str(job_id), JobRecord.tenant_id == principal.tenant_id
            )
        )
        if job is None:
            raise _problem("NOT_FOUND", status.HTTP_404_NOT_FOUND, "Job não encontrado.")
        operation = f"review.note:{job_id}"
        request_hash = _request_hash(payload)
        existing = _idempotent_response(
            session,
            principal=principal,
            operation=operation,
            key=idempotency_key,
            request_hash=request_hash,
        )
        if existing is not None:
            return ReviewResponse.model_validate(existing)
        current, scene_record, current_scene, reading = _annotation_target(
            session,
            job_id=job_id,
            tenant_id=principal.tenant_id,
            base_review_version=payload.base_review_version,
            base_scene_version=payload.base_scene_version,
            reading_id=payload.reading_id,
        )
        assert reading.decision is not None
        try:
            note = annotate_note(
                current_scene,
                entity_id=payload.entity_id,
                layer=LayerName(payload.layer),
                text=reading.raw_text,
                reading_id=reading.id,
                decision_id=reading.decision.decision_id,
            )
        except DimensionAnnotationError as error:
            raise _problem(
                "DOMAIN_VALIDATION_FAILED", status.HTTP_422_UNPROCESSABLE_ENTITY, str(error)
            ) from error
        next_scene = SceneRevision.model_validate(
            {
                **current_scene.model_dump(mode="json"),
                "id": str(new_uuid7()),
                "version": current_scene.version + 1,
                "entities": [
                    *[item.model_dump(mode="json") for item in current_scene.entities],
                    note.model_dump(mode="json"),
                ],
            }
        )
        next_review = ReviewRevisionRecord(
            id=str(new_uuid7()),
            tenant_id=principal.tenant_id,
            job_id=str(job_id),
            version=current.version + 1,
            parent_review_id=current.id,
            packet_json=current.packet_json,
            associations_json=current.associations_json,
            proposals_json=current.proposals_json,
            selected_associations_json=current.selected_associations_json,
            calibration_json=current.calibration_json,
            proposal_decisions_json=current.proposal_decisions_json,
            evidence_refs_json=current.evidence_refs_json,
            solver_request_json=current.solver_request_json,
            solver_blockers_json=current.solver_blockers_json,
            required_blocker_codes_json=current.required_blocker_codes_json,
            required_criteria_texts_json=current.required_criteria_texts_json,
            scene_revision_id=str(next_scene.id),
            created_by=principal.subject,
        )
        session.add(
            RevisionRecord(
                id=str(next_scene.id),
                tenant_id=principal.tenant_id,
                job_id=str(job_id),
                version=next_scene.version,
                parent_revision_id=scene_record.id,
                scene=next_scene.model_dump(mode="json"),
                created_by=principal.subject,
            )
        )
        session.flush()
        session.add(next_review)
        try:
            session.flush()
        except IntegrityError as error:
            session.rollback()
            raise _problem(
                "REVISION_CONFLICT",
                status.HTTP_409_CONFLICT,
                "Uma atualização concorrente criou nova revisão.",
            ) from error
        response = _review_response(application, session, next_review)
        _store_idempotent_response(
            session,
            principal=principal,
            operation=operation,
            key=idempotency_key,
            request_hash=request_hash,
            response=response,
        )
        _record_audit(
            session,
            principal=principal,
            action="NOTE_ANNOTATED",
            resource_type="scene_revision",
            resource_id=str(next_scene.id),
            request_id=request.state.request_id,
        )
        session.commit()
        return response

    @application.get("/v1/projects", response_model=list[ProjectResponse], tags=["projects"])
    async def list_projects(
        principal: AuthenticatedPrincipal, session: DatabaseSession
    ) -> list[ProjectResponse]:
        projects = session.scalars(
            select(ProjectRecord)
            .where(ProjectRecord.tenant_id == principal.tenant_id)
            .order_by(ProjectRecord.created_at.desc())
        ).all()
        response: list[ProjectResponse] = []
        for project in projects:
            latest_job = session.scalar(
                select(JobRecord)
                .where(
                    JobRecord.project_id == project.id,
                    JobRecord.tenant_id == principal.tenant_id,
                )
                .order_by(JobRecord.created_at.desc())
            )
            response.append(
                ProjectResponse(
                    project_id=UUID(project.id),
                    name=project.name,
                    default_unit=UnitCode(project.default_unit),
                    status=project.status,
                    expires_at=project.expires_at,
                    latest_job=(
                        LatestJobResponse(
                            job_id=UUID(latest_job.id),
                            status=latest_job.status,
                            stage=latest_job.stage,
                        )
                        if latest_job is not None
                        else None
                    ),
                )
            )
        return response

    @application.get("/v1/jobs/{job_id}/scene", response_model=SceneRevision, tags=["scene"])
    async def get_scene(
        job_id: UUID,
        principal: AuthenticatedPrincipal,
        session: DatabaseSession,
    ) -> SceneRevision:
        revision = session.scalar(
            select(RevisionRecord)
            .where(
                RevisionRecord.job_id == str(job_id),
                RevisionRecord.tenant_id == principal.tenant_id,
            )
            .order_by(RevisionRecord.version.desc())
        )
        if revision is None:
            raise _problem(
                "JOB_NOT_READY", status.HTTP_409_CONFLICT, "Cena ainda não está disponível."
            )
        return SceneRevision.model_validate(revision.scene)

    @application.post("/v1/jobs/{job_id}/revisions", response_model=SceneRevision, tags=["scene"])
    async def create_revision(
        job_id: UUID,
        payload: CreateRevisionRequest,
        principal: AuthenticatedPrincipal,
        session: DatabaseSession,
        idempotency_key: Annotated[str, Depends(_require_idempotency)],
    ) -> SceneRevision:
        revision_operation = f"scene.revision:{job_id}"
        request_hash = _request_hash(payload)
        replayed = _idempotent_response(
            session,
            principal=principal,
            operation=revision_operation,
            key=idempotency_key,
            request_hash=request_hash,
        )
        if replayed is not None:
            return SceneRevision.model_validate(replayed)
        current = session.scalar(
            select(RevisionRecord)
            .where(
                RevisionRecord.job_id == str(job_id),
                RevisionRecord.tenant_id == principal.tenant_id,
            )
            .order_by(RevisionRecord.version.desc())
        )
        if current is None:
            raise _problem(
                "JOB_NOT_READY", status.HTTP_409_CONFLICT, "Cena ainda não está disponível."
            )
        current_scene = SceneRevision.model_validate(current.scene)
        if current_scene.version != payload.base_version:
            raise _problem(
                "REVISION_CONFLICT", status.HTTP_409_CONFLICT, "Existe uma revisão mais recente."
            )
        if current_scene.approved:
            raise _problem(
                "REVISION_CONFLICT", status.HTTP_409_CONFLICT, "Revisão aprovada é imutável."
            )

        entities = list(current_scene.entities)
        measurements = list(current_scene.measurements)
        known_entity_ids = {entity.id for entity in entities}
        for operation in payload.operations:
            if isinstance(operation, AddEntityOperation):
                if operation.entity.id in known_entity_ids:
                    raise _problem(
                        "DOMAIN_VALIDATION_FAILED", 422, "Entidade já existe na revisão."
                    )
                if operation.entity.precision is Precision.EXACT:
                    raise _problem(
                        "UNRESOLVED_GEOMETRY",
                        422,
                        "O navegador não pode criar geometria exact sem solver e evidência.",
                    )
                entities.append(operation.entity)
                known_entity_ids.add(operation.entity.id)
            elif operation.measurement.entity_id not in known_entity_ids:
                raise _problem(
                    "DOMAIN_VALIDATION_FAILED", 422, "Medida aponta para entidade inexistente."
                )
            elif operation.measurement.confirmed:
                raise _problem(
                    "DOMAIN_VALIDATION_FAILED",
                    422,
                    "Confirmação de medida requer fluxo profissional específico.",
                )
            else:
                measurements.append(operation.measurement)

        next_scene = SceneRevision.model_validate(
            {
                **current_scene.model_dump(mode="json"),
                "id": str(new_uuid7()),
                "version": current_scene.version + 1,
                "entities": [entity.model_dump(mode="json") for entity in entities],
                "measurements": [
                    measurement.model_dump(mode="json") for measurement in measurements
                ],
            }
        )
        session.add(
            RevisionRecord(
                id=str(next_scene.id),
                tenant_id=principal.tenant_id,
                job_id=str(job_id),
                version=next_scene.version,
                parent_revision_id=str(current_scene.id),
                scene=next_scene.model_dump(mode="json"),
                created_by=principal.subject,
            )
        )
        _store_idempotent_response(
            session,
            principal=principal,
            operation=revision_operation,
            key=idempotency_key,
            request_hash=request_hash,
            response=next_scene,
        )
        session.commit()
        return next_scene

    @application.post("/v1/jobs/{job_id}/approve", response_model=SceneRevision, tags=["scene"])
    async def approve_scene(
        job_id: UUID,
        payload: ApproveRequest,
        request: Request,
        principal: AuthenticatedPrincipal,
        session: DatabaseSession,
        idempotency_key: Annotated[str, Depends(_require_idempotency)],
    ) -> SceneRevision:
        if not principal.has_role("engineer"):
            raise _problem("FORBIDDEN", status.HTTP_403_FORBIDDEN, "Papel engineer é obrigatório.")
        reviewer_role = _reviewer_role(principal)
        operation = f"scene.approve:{job_id}"
        request_hash = _request_hash(payload)
        existing = _idempotent_response(
            session,
            principal=principal,
            operation=operation,
            key=idempotency_key,
            request_hash=request_hash,
        )
        if existing is not None:
            return SceneRevision.model_validate(existing)
        revision = session.scalar(
            select(RevisionRecord).where(
                RevisionRecord.id == str(payload.revision_id),
                RevisionRecord.job_id == str(job_id),
                RevisionRecord.tenant_id == principal.tenant_id,
            )
        )
        if revision is None:
            raise _problem("NOT_FOUND", status.HTTP_404_NOT_FOUND, "Revisão não encontrada.")
        source_scene = SceneRevision.model_validate(revision.scene)
        if source_scene.approved:
            raise _problem(
                "REVISION_CONFLICT",
                status.HTTP_409_CONFLICT,
                "Uma revisão aprovada é imutável.",
            )
        latest = _latest_scene(session, job_id=job_id, tenant_id=principal.tenant_id)
        if latest is not None and latest.version > source_scene.version:
            raise _problem(
                "REVISION_CONFLICT",
                status.HTTP_409_CONFLICT,
                "Existe uma revisão de cena mais recente.",
            )
        if not source_scene.entities:
            raise _problem(
                "UNRESOLVED_GEOMETRY",
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "Cena vazia não pode receber aprovação técnica.",
            )
        # Pre-checked here so an unknown id fails as a domain error instead of a 500.
        approximate_ids = {
            entity.id
            for entity in source_scene.entities
            if entity.precision is Precision.APPROXIMATE
        }
        if not payload.accepted_approximations <= approximate_ids:
            raise _problem(
                "DOMAIN_VALIDATION_FAILED",
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "Só é possível aceitar aproximações existentes na revisão.",
            )
        review = _latest_review(session, job_id=job_id, tenant_id=principal.tenant_id)
        declarable = set(review.required_blocker_codes_json) if review is not None else set()
        if not (payload.covered_criteria | payload.acknowledged_criteria) <= declarable:
            raise _problem(
                "CRITERION_NOT_ACKNOWLEDGEABLE",
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "Somente critérios de escopo declarados no caso podem ser reconhecidos.",
            )
        if payload.covered_criteria & payload.acknowledged_criteria:
            raise _problem(
                "CRITERION_DECLARATION_CONFLICT",
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "Um critério não pode ser declarado coberto e pendente ao mesmo tempo.",
            )
        approved_at = datetime.now(UTC)
        approval = SceneApproval(
            approval_id=_approval_id(
                scene_id=source_scene.id,
                reviewer_id=principal.subject,
                decided_at=approved_at,
                statement=payload.statement,
            ),
            source_scene_id=source_scene.id,
            reviewer_id=principal.subject,
            reviewer_role=reviewer_role,
            decided_at=approved_at,
            source_evidence_checked=payload.source_evidence_checked,
            geometry_checked=payload.geometry_checked,
            limitations_acknowledged=payload.limitations_acknowledged,
            covered_criteria=sorted(payload.covered_criteria),
            acknowledged_criteria=sorted(payload.acknowledged_criteria),
            statement=payload.statement,
        )
        declared_issues = apply_criteria_declarations(
            source_scene.issues,
            covered=payload.covered_criteria,
            acknowledged=payload.acknowledged_criteria,
        )
        approved_scene = SceneRevision.model_validate(
            {
                **source_scene.model_dump(mode="json"),
                "id": str(new_uuid7()),
                "version": source_scene.version + 1,
                "approved": True,
                "accepted_approximation_ids": [
                    str(item) for item in payload.accepted_approximations
                ],
                "issues": [issue.model_dump(mode="json") for issue in declared_issues],
            }
        )
        approved_scene.ensure_exportable()
        session.add(
            RevisionRecord(
                id=str(approved_scene.id),
                tenant_id=principal.tenant_id,
                job_id=str(job_id),
                version=approved_scene.version,
                parent_revision_id=str(source_scene.id),
                scene=approved_scene.model_dump(mode="json"),
                created_by=principal.subject,
                approved_at=approved_at,
                approved_by=principal.subject,
            )
        )
        session.flush()
        session.add(
            ApprovalRecord(
                id=str(new_uuid7()),
                tenant_id=principal.tenant_id,
                job_id=str(job_id),
                source_revision_id=str(source_scene.id),
                approved_revision_id=str(approved_scene.id),
                reviewer_id=principal.subject,
                reviewer_roles=sorted(principal.roles),
                acknowledgement=payload.statement,
                # Os dois conjuntos são campos do contrato `SceneApproval`; nada é colado
                # por fora do modelo ao montar o registro que vira o `aprovacao.json`.
                approval_json={
                    "source_scene_id": str(source_scene.id),
                    **approval.model_dump(mode="json"),
                },
            )
        )
        job = session.get(JobRecord, str(job_id))
        if job is not None:
            job.status = "APPROVED"
            job.updated_at = approved_at
        try:
            session.flush()
        except IntegrityError as error:
            session.rollback()
            raise _problem(
                "REVISION_CONFLICT",
                status.HTTP_409_CONFLICT,
                "Uma aprovação concorrente criou outra revisão.",
            ) from error
        _store_idempotent_response(
            session,
            principal=principal,
            operation=operation,
            key=idempotency_key,
            request_hash=request_hash,
            response=approved_scene,
        )
        _record_audit(
            session,
            principal=principal,
            action="SCENE_APPROVED",
            resource_type="scene_revision",
            resource_id=str(approved_scene.id),
            request_id=request.state.request_id,
        )
        session.commit()
        return approved_scene

    @application.post(
        "/v1/jobs/{job_id}/exports",
        response_model=ExportArtifactResponse,
        status_code=status.HTTP_202_ACCEPTED,
        tags=["exports"],
    )
    async def create_export(
        job_id: UUID,
        payload: CreateExportRequest,
        request: Request,
        principal: AuthenticatedPrincipal,
        session: DatabaseSession,
        _idempotency_key: Annotated[str, Depends(_require_idempotency)],
    ) -> ExportArtifactResponse:
        """Validates and queues the export; the CAD package is never built in the request path."""
        _reviewer_role(principal)
        job = session.scalar(
            select(JobRecord).where(
                JobRecord.id == str(job_id), JobRecord.tenant_id == principal.tenant_id
            )
        )
        if job is None:
            raise _problem("NOT_FOUND", status.HTTP_404_NOT_FOUND, "Job não encontrado.")
        revision = session.scalar(
            select(RevisionRecord).where(
                RevisionRecord.id == str(payload.revision_id),
                RevisionRecord.job_id == str(job_id),
                RevisionRecord.tenant_id == principal.tenant_id,
            )
        )
        if revision is None:
            raise _problem("NOT_FOUND", status.HTTP_404_NOT_FOUND, "Revisão não encontrada.")
        approval = session.scalar(
            select(ApprovalRecord).where(
                ApprovalRecord.approved_revision_id == revision.id,
                ApprovalRecord.tenant_id == principal.tenant_id,
            )
        )
        scene = SceneRevision.model_validate(revision.scene)
        if not scene.approved or approval is None:
            raise _problem(
                "SCENE_NOT_APPROVED",
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "Somente uma revisão aprovada pode ser exportada.",
            )
        # Server-side revalidation: approval alone never authorises a broken scene.
        errors = scene.export_errors()
        if errors:
            raise DomainValidationError(errors)

        artifact = session.scalar(
            select(ExportArtifactRecord).where(
                ExportArtifactRecord.job_id == str(job_id),
                ExportArtifactRecord.tenant_id == principal.tenant_id,
                ExportArtifactRecord.scene_revision_id == revision.id,
                ExportArtifactRecord.format == payload.format,
            )
        )
        if artifact is not None and artifact.status == "COMPLETED":
            return _export_response(application, artifact)
        if artifact is None:
            artifact = ExportArtifactRecord(
                id=str(new_uuid7()),
                tenant_id=principal.tenant_id,
                job_id=str(job_id),
                scene_revision_id=revision.id,
                approval_id=approval.id,
                format=payload.format,
                status="QUEUED",
                requested_by=principal.subject,
            )
            session.add(artifact)
        else:
            artifact.status = "QUEUED"
            artifact.failure_code = None
            artifact.updated_at = datetime.now(UTC)
        job.status = "EXPORTING"
        job.updated_at = datetime.now(UTC)
        _record_audit(
            session,
            principal=principal,
            action="EXPORT_REQUESTED",
            resource_type="export_artifact",
            resource_id=artifact.id,
            request_id=request.state.request_id,
        )
        # The intent is durable before the queue call, and no transaction spans it.
        session.commit()
        queue: QueueAdapter = application.state.queue
        try:
            queue.enqueue_export(
                export_id=artifact.id,
                job_id=str(job_id),
                tenant_id=principal.tenant_id,
                scene_revision_id=revision.id,
            )
        except QUEUE_TRANSPORT_ERRORS as error:
            raise _problem(
                "PROCESSING_UNAVAILABLE",
                status.HTTP_503_SERVICE_UNAVAILABLE,
                "A fila de processamento não aceitou o comando; tente novamente.",
            ) from error
        return _export_response(application, artifact)

    @application.get(
        "/v1/jobs/{job_id}/exports/{export_id}",
        response_model=ExportArtifactResponse,
        tags=["exports"],
    )
    async def get_export(
        job_id: UUID,
        export_id: UUID,
        principal: AuthenticatedPrincipal,
        session: DatabaseSession,
    ) -> ExportArtifactResponse:
        artifact = session.scalar(
            select(ExportArtifactRecord).where(
                ExportArtifactRecord.id == str(export_id),
                ExportArtifactRecord.job_id == str(job_id),
                ExportArtifactRecord.tenant_id == principal.tenant_id,
            )
        )
        if artifact is None:
            raise _problem("NOT_FOUND", status.HTTP_404_NOT_FOUND, "Exportação não encontrada.")
        return _export_response(application, artifact)

    @application.post(
        "/v1/jobs/{job_id}/trace-solves",
        response_model=TraceSolveResponse,
        status_code=status.HTTP_202_ACCEPTED,
        tags=["trace"],
    )
    async def create_trace_solve(
        job_id: UUID,
        payload: CreateTraceSolveRequest,
        request: Request,
        principal: AuthenticatedPrincipal,
        session: DatabaseSession,
        idempotency_key: Annotated[str, Depends(_require_idempotency)],
    ) -> TraceSolveResponse:
        """Validates and queues the batch trace; the geometry is always solved in the worker."""
        reviewer_role = _reviewer_role(principal)
        job = session.scalar(
            select(JobRecord).where(
                JobRecord.id == str(job_id), JobRecord.tenant_id == principal.tenant_id
            )
        )
        if job is None:
            raise _problem("NOT_FOUND", status.HTTP_404_NOT_FOUND, "Job não encontrado.")
        operation = f"trace.solve:{job_id}"
        request_hash = _request_hash(payload)
        existing = _idempotent_response(
            session,
            principal=principal,
            operation=operation,
            key=idempotency_key,
            request_hash=request_hash,
        )
        if existing is not None:
            return TraceSolveResponse.model_validate(existing)

        current = _latest_review(session, job_id=job_id, tenant_id=principal.tenant_id)
        if current is None:
            raise _problem(
                "JOB_NOT_READY",
                status.HTTP_409_CONFLICT,
                "Pacote de revisão ainda não está disponível.",
            )
        if current.proposals_json is None:
            raise _problem(
                "PROPOSALS_NOT_READY",
                status.HTTP_409_CONFLICT,
                "Snapshot de propostas ainda não está disponível.",
            )
        if current.version != payload.base_review_version:
            raise _problem(
                "REVISION_CONFLICT",
                status.HTTP_409_CONFLICT,
                "Existe uma revisão de leitura mais recente.",
            )
        scene_record = _latest_scene(session, job_id=job_id, tenant_id=principal.tenant_id)
        current_scene_version = scene_record.version if scene_record is not None else None
        if current_scene_version != payload.base_scene_version:
            raise _problem(
                "REVISION_CONFLICT",
                status.HTTP_409_CONFLICT,
                "Existe uma cena mais recente para o traçado.",
            )

        # A revisão corrente já carrega as associações confirmadas por leitura; o corpo
        # sobrepõe por `reading_id` sem apagar as demais.
        associations: dict[str, Any] = dict(current.selected_associations_json)
        for reading_id, target in payload.associations.items():
            associations[reading_id] = (
                target.model_dump(mode="json") if isinstance(target, TraceDeclaredSpan) else target
            )

        known = {
            proposal.id
            for proposal in VisionProposalSet.model_validate(current.proposals_json).proposals
        }
        referenced = [
            *payload.proposal_ids,
            *payload.hatch_proposal_ids,
            *payload.unlabelled_proposal_ids,
            *payload.freeform_proposal_ids,
            *[item for pair in payload.keep_apart_pairs for item in keep_apart_proposal_ids(pair)],
            *[item for group in payload.detail_groups for item in group.proposal_ids],
            *[item.proposal_id for item in payload.derived_dimensions],
            *[
                proposal_id
                for target in payload.associations.values()
                for proposal_id in _association_proposal_ids(target)
            ],
            *current.selected_associations_json.values(),
            *[
                proposal_id
                for target in payload.note_associations.values()
                for proposal_id in _note_target_proposal_ids(target)
            ],
        ]
        unknown = sorted({item for item in referenced if item not in known})
        if unknown:
            raise _problem(
                "TRACE_PROPOSAL_UNKNOWN",
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                f"{len(unknown)} propostas não pertencem ao snapshot da revisão.",
            )

        decided_at = datetime.now(UTC)
        try:
            # A consistência interna do aceite é a do próprio contrato do traçado:
            # construí-lo aqui reprova o lote antes de ocupar a fila.
            acceptance = TraceAcceptance.model_validate(
                {
                    "acceptance_id": _trace_acceptance_id(
                        job_id=job_id,
                        reviewer_id=principal.subject,
                        decided_at=decided_at,
                        proposal_ids=payload.proposal_ids,
                    ),
                    "reviewer_id": principal.subject,
                    "reviewer_role": reviewer_role,
                    "decided_at": decided_at,
                    "note": payload.note,
                    "proposal_ids": payload.proposal_ids,
                    "hatch_proposal_ids": payload.hatch_proposal_ids,
                    "keep_apart_pairs": [
                        pair.model_dump(mode="json") if isinstance(pair, KeepApartPair) else pair
                        for pair in payload.keep_apart_pairs
                    ],
                    "unlabelled_proposal_ids": payload.unlabelled_proposal_ids,
                    "freeform_proposal_ids": payload.freeform_proposal_ids,
                    "detail_groups": [
                        group.model_dump(mode="json") for group in payload.detail_groups
                    ],
                }
            )
        except ValidationError as error:
            raise _problem(
                "TRACE_ACCEPTANCE_INVALID",
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                _domain_messages(error),
            ) from error

        record = TraceSolveRecord(
            id=str(new_uuid7()),
            tenant_id=principal.tenant_id,
            job_id=str(job_id),
            base_review_revision_id=current.id,
            base_scene_revision_id=scene_record.id if scene_record is not None else None,
            status="QUEUED",
            acceptance_id=acceptance.acceptance_id,
            acceptance_json=acceptance.model_dump(mode="json"),
            associations_json=associations,
            note_associations_json=dict(payload.note_associations),
            derived_dimensions_json=[
                item.model_dump(mode="json") for item in payload.derived_dimensions
            ],
            dimension_texts_json=dict(payload.dimension_texts),
            title=payload.title,
            feature_id=payload.feature_id,
            requested_by=principal.subject,
        )
        session.add(record)
        session.flush()
        response = _trace_solve_response(session, record)
        _store_idempotent_response(
            session,
            principal=principal,
            operation=operation,
            key=idempotency_key,
            request_hash=request_hash,
            response=response,
        )
        _record_audit(
            session,
            principal=principal,
            action="TRACE_SOLVE_REQUESTED",
            resource_type="trace_solve",
            resource_id=record.id,
            request_id=request.state.request_id,
        )
        # The intent is durable before the queue call, and no transaction spans it.
        session.commit()
        queue: QueueAdapter = application.state.queue
        try:
            queue.enqueue_trace_solve(
                trace_solve_id=record.id,
                job_id=str(job_id),
                tenant_id=principal.tenant_id,
            )
        except QUEUE_TRANSPORT_ERRORS as error:
            raise _problem(
                "PROCESSING_UNAVAILABLE",
                status.HTTP_503_SERVICE_UNAVAILABLE,
                "A fila de processamento não aceitou o comando; tente novamente.",
            ) from error
        return response

    @application.get(
        "/v1/jobs/{job_id}/trace-solves/{trace_solve_id}",
        response_model=TraceSolveResponse,
        tags=["trace"],
    )
    async def get_trace_solve(
        job_id: UUID,
        trace_solve_id: UUID,
        principal: AuthenticatedPrincipal,
        session: DatabaseSession,
    ) -> TraceSolveResponse:
        record = session.scalar(
            select(TraceSolveRecord).where(
                TraceSolveRecord.id == str(trace_solve_id),
                TraceSolveRecord.job_id == str(job_id),
                TraceSolveRecord.tenant_id == principal.tenant_id,
            )
        )
        if record is None:
            raise _problem("NOT_FOUND", status.HTTP_404_NOT_FOUND, "Traçado não encontrado.")
        return _trace_solve_response(session, record)

    def _chat_session_of(
        session: Session, *, job_id: UUID, session_id: UUID, tenant_id: str
    ) -> ChatSessionRecord:
        record = session.scalar(
            select(ChatSessionRecord).where(
                ChatSessionRecord.id == str(session_id),
                ChatSessionRecord.job_id == str(job_id),
                ChatSessionRecord.tenant_id == tenant_id,
            )
        )
        if record is None:
            raise _problem("NOT_FOUND", status.HTTP_404_NOT_FOUND, "Conversa não encontrada.")
        return record

    def _chat_turns_of(session: Session, chat_session: ChatSessionRecord) -> list[ChatTurnRecord]:
        return list(
            session.scalars(
                select(ChatTurnRecord)
                .where(
                    ChatTurnRecord.session_id == chat_session.id,
                    ChatTurnRecord.tenant_id == chat_session.tenant_id,
                )
                .order_by(ChatTurnRecord.sequence)
            )
        )

    def _base_review_of(session: Session, chat_session: ChatSessionRecord) -> ReviewRevisionRecord:
        """A revisão que a conversa fixou; ela não segue a revisão corrente do job."""
        record = session.scalar(
            select(ReviewRevisionRecord).where(
                ReviewRevisionRecord.id == chat_session.base_review_revision_id,
                ReviewRevisionRecord.tenant_id == chat_session.tenant_id,
            )
        )
        if record is None:
            raise _problem(
                "JOB_NOT_READY",
                status.HTTP_409_CONFLICT,
                "A revisão-base desta conversa não está mais disponível.",
            )
        return record

    @application.post(
        "/v1/jobs/{job_id}/chat-sessions",
        response_model=ChatSessionResponse,
        status_code=status.HTTP_201_CREATED,
        tags=["chat"],
    )
    async def create_chat_session(
        job_id: UUID,
        payload: CreateChatSessionRequest,
        request: Request,
        principal: AuthenticatedPrincipal,
        session: DatabaseSession,
        idempotency_key: Annotated[str, Depends(_require_idempotency)],
    ) -> ChatSessionResponse:
        """Abre uma conversa presa à revisão de leitura corrente; nenhum modelo roda aqui."""
        _reviewer_role(principal)
        job = session.scalar(
            select(JobRecord).where(
                JobRecord.id == str(job_id), JobRecord.tenant_id == principal.tenant_id
            )
        )
        if job is None:
            raise _problem("NOT_FOUND", status.HTTP_404_NOT_FOUND, "Job não encontrado.")
        _require_active_ai_entitlement(
            session,
            principal,
            real_providers_enabled=runtime_settings.real_providers_enabled,
        )
        operation = f"chat.session:{job_id}"
        request_hash = _request_hash(payload)
        existing = _idempotent_response(
            session,
            principal=principal,
            operation=operation,
            key=idempotency_key,
            request_hash=request_hash,
        )
        if existing is not None:
            return ChatSessionResponse.model_validate(existing)

        current = _latest_review(session, job_id=job_id, tenant_id=principal.tenant_id)
        if current is None:
            raise _problem(
                "JOB_NOT_READY",
                status.HTTP_409_CONFLICT,
                "Pacote de revisão ainda não está disponível.",
            )
        record = ChatSessionRecord(
            id=str(new_uuid7()),
            tenant_id=principal.tenant_id,
            job_id=str(job_id),
            base_review_revision_id=current.id,
            status="OPEN",
            created_by=principal.subject,
        )
        session.add(record)
        session.flush()
        response = _chat_session_response(record, base_review_version=current.version, turns=[])
        _store_idempotent_response(
            session,
            principal=principal,
            operation=operation,
            key=idempotency_key,
            request_hash=request_hash,
            response=response,
        )
        # Só ids: nem a pergunta nem a resposta chegam perto da auditoria.
        _record_audit(
            session,
            principal=principal,
            action="CHAT_SESSION_OPENED",
            resource_type="chat_session",
            resource_id=record.id,
            request_id=request.state.request_id,
        )
        session.commit()
        return response

    @application.post(
        "/v1/jobs/{job_id}/chat-sessions/{session_id}/turns",
        response_model=ChatTurnResponse,
        status_code=status.HTTP_202_ACCEPTED,
        tags=["chat"],
    )
    async def create_chat_turn(
        job_id: UUID,
        session_id: UUID,
        payload: CreateChatTurnRequest,
        request: Request,
        principal: AuthenticatedPrincipal,
        session: DatabaseSession,
        idempotency_key: Annotated[str, Depends(_require_idempotency)],
    ) -> ChatTurnResponse:
        """Persiste a pergunta, commita e só então enfileira; o modelo roda no worker."""
        _reviewer_role(principal)
        chat_session = _chat_session_of(
            session, job_id=job_id, session_id=session_id, tenant_id=principal.tenant_id
        )
        if chat_session.status != "OPEN":
            raise _problem(
                "CHAT_SESSION_CLOSED",
                status.HTTP_409_CONFLICT,
                "Esta conversa está encerrada; abra outra.",
            )
        operation = f"chat.turn:{session_id}"
        request_hash = _request_hash(payload)
        existing = _idempotent_response(
            session,
            principal=principal,
            operation=operation,
            key=idempotency_key,
            request_hash=request_hash,
        )
        if existing is not None:
            return ChatTurnResponse.model_validate(existing)

        turns = _chat_turns_of(session, chat_session)
        # Um turno em voo por conversa: duas perguntas simultâneas sobre a mesma folha
        # produziriam duas respostas sem ordem entre si, e a conversa deixaria de ser uma.
        if any(turn.status in {"QUEUED", "RUNNING"} for turn in turns):
            raise _problem(
                "CHAT_TURN_PENDING",
                status.HTTP_409_CONFLICT,
                "A pergunta anterior ainda está sendo respondida.",
            )
        base_review = _base_review_of(session, chat_session)
        packet = ReviewPacket.model_validate(base_review.packet_json)
        known_readings = {reading.id for reading in packet.readings}
        known_proposals = (
            {
                proposal.id
                for proposal in VisionProposalSet.model_validate(
                    base_review.proposals_json
                ).proposals
            }
            if base_review.proposals_json is not None
            else set[str]()
        )
        unknown = sorted(
            {item for item in payload.anchors.reading_ids if item not in known_readings}
            | {item for item in payload.anchors.proposal_ids if item not in known_proposals}
        )
        if unknown:
            raise _problem(
                "CHAT_ANCHOR_UNKNOWN",
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                f"{len(unknown)} âncoras não pertencem à revisão-base desta conversa.",
            )

        record = ChatTurnRecord(
            id=str(new_uuid7()),
            tenant_id=principal.tenant_id,
            job_id=str(job_id),
            session_id=chat_session.id,
            sequence=max((turn.sequence for turn in turns), default=0) + 1,
            status="QUEUED",
            question_text=payload.question,
            anchor_refs_json=payload.anchors.model_dump(mode="json"),
            requested_by=principal.subject,
        )
        session.add(record)
        session.flush()
        response = _chat_turn_response(record)
        _store_idempotent_response(
            session,
            principal=principal,
            operation=operation,
            key=idempotency_key,
            request_hash=request_hash,
            response=response,
        )
        _record_audit(
            session,
            principal=principal,
            action="CHAT_TURN_REQUESTED",
            resource_type="chat_turn",
            resource_id=record.id,
            request_id=request.state.request_id,
        )
        # The intent is durable before the queue call, and no transaction spans it.
        session.commit()
        queue: QueueAdapter = application.state.queue
        try:
            queue.enqueue_chat_turn(
                chat_turn_id=record.id,
                job_id=str(job_id),
                tenant_id=principal.tenant_id,
            )
        except QUEUE_TRANSPORT_ERRORS as error:
            raise _problem(
                "PROCESSING_UNAVAILABLE",
                status.HTTP_503_SERVICE_UNAVAILABLE,
                "A fila de processamento não aceitou o comando; tente novamente.",
            ) from error
        return response

    @application.get(
        "/v1/jobs/{job_id}/chat-sessions",
        response_model=list[ChatSessionSummaryResponse],
        tags=["chat"],
    )
    async def list_chat_sessions(
        job_id: UUID,
        principal: AuthenticatedPrincipal,
        session: DatabaseSession,
    ) -> list[ChatSessionSummaryResponse]:
        job = session.scalar(
            select(JobRecord).where(
                JobRecord.id == str(job_id), JobRecord.tenant_id == principal.tenant_id
            )
        )
        if job is None:
            raise _problem("NOT_FOUND", status.HTTP_404_NOT_FOUND, "Job não encontrado.")
        records = session.scalars(
            select(ChatSessionRecord)
            .where(
                ChatSessionRecord.job_id == str(job_id),
                ChatSessionRecord.tenant_id == principal.tenant_id,
            )
            .order_by(ChatSessionRecord.created_at)
        )
        return [
            ChatSessionSummaryResponse(
                chat_session_id=UUID(record.id),
                status=cast(Literal["OPEN", "CLOSED"], record.status),
                created_at=record.created_at,
                # Contagem por consulta: carregar cada turno — com pergunta e resposta —
                # só para contá-los seria caro e desnecessário numa lista magra.
                turn_count=session.scalar(
                    select(func.count())
                    .select_from(ChatTurnRecord)
                    .where(
                        ChatTurnRecord.session_id == record.id,
                        ChatTurnRecord.tenant_id == principal.tenant_id,
                    )
                )
                or 0,
            )
            for record in records
        ]

    @application.get(
        "/v1/jobs/{job_id}/chat-sessions/{session_id}",
        response_model=ChatSessionResponse,
        tags=["chat"],
    )
    async def get_chat_session(
        job_id: UUID,
        session_id: UUID,
        principal: AuthenticatedPrincipal,
        session: DatabaseSession,
    ) -> ChatSessionResponse:
        chat_session = _chat_session_of(
            session, job_id=job_id, session_id=session_id, tenant_id=principal.tenant_id
        )
        base_review = _base_review_of(session, chat_session)
        return _chat_session_response(
            chat_session,
            base_review_version=base_review.version,
            turns=_chat_turns_of(session, chat_session),
        )

    return application


app = create_app()
