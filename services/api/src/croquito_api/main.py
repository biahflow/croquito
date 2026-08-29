"""API de lifecycle: autentica, persiste e orquestra; não processa PDFs no request."""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import math
import re
import time
from collections.abc import Collection, Generator, Mapping, Sequence
from contextlib import suppress
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Annotated, Any, Final, Literal, cast
from uuid import UUID

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError
from fastapi import Depends, FastAPI, Header, HTTPException, Path, Query, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    RootModel,
    ValidationError,
    field_validator,
    model_validator,
)
from sqlalchemy import and_, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from starlette.exceptions import HTTPException as StarletteHTTPException

from croquito_api import estimate_rounds, precedents, site_setup_kits
from croquito_api.auth import (
    OidcAuthenticator,
    Principal,
    optional_principal,
    require_principal,
)
from croquito_api.config import ApiSettings
from croquito_api.database import (
    AiProcessingAuthorizationRecord,
    ApprovalRecord,
    AuditRecord,
    ChatSessionRecord,
    ChatTurnRecord,
    Database,
    DomainEventRecord,
    EstimateRoundRecord,
    EstimateRoundRevisionRecord,
    ExportArtifactRecord,
    FieldEvidenceAnalysisRecord,
    FieldPhotoValueConfirmationRecord,
    IdempotencyRecord,
    JobFieldPhotoRecord,
    JobRecord,
    JobStageEventRecord,
    JobSurveyLinkRecord,
    ProjectRecord,
    ProposalDecisionRecord,
    ReferenceCatalogEmbeddingRecord,
    ReferenceCatalogRecord,
    ReviewDecisionRecord,
    ReviewRevisionRecord,
    RevisionRecord,
    SiteSetupKitRecord,
    SurveyMediaRecord,
    SurveyOperationRecord,
    SurveyRecord,
    TenantAiProcessingEntitlementRecord,
    TenantJourneyEntitlementRecord,
    TraceSolveRecord,
    UploadRecord,
    ValuationRoundPlateRecord,
    ValuationRoundRecord,
    ValuationRoundRevisionRecord,
)
from croquito_api.journeys import (
    CROQUI_REVIEWER_ROLES,
    ESTIMATE_APPROVER_ROLE,
    JOURNEYS,
    Journey,
    JourneyAvailability,
    journey_of_path,
    journey_reachable,
    pilot_journeys,
    resolve_journeys,
)
from croquito_api.metrics import (
    MetricsPeriodError,
    compute_job_metrics,
    compute_tenant_summary,
    parse_period_bound,
)
from croquito_api.pubsub_queue import PubSubProcessingQueue, QueuePublishError
from croquito_api.reference_catalog_indexes import (
    CATALOG_INDEX_MAX_BYTES,
    SemanticIndexCache,
    parse_index_document,
    read_index_document,
    reference_catalog_index_key,
)
from croquito_api.reference_catalogs import (
    PUBLISHABLE_ORIGINS,
    STATUS_AVAILABLE,
    STATUS_WITHDRAWN,
    reference_catalog_key,
)
from croquito_api.semantic_arm import (
    ENTITLEMENT_INACTIVE_REASON,
    PROVIDERS_DISABLED_REASON,
    resolve_cascade_arms,
)
from croquito_api.storage import ArtifactStore
from croquito_api.valuation_rounds import (
    BULLETIN_SOURCES_DIGEST,
    BULLETIN_WORKBOOK_CONTENT_TYPE,
    BULLETIN_WORKBOOK_DIGEST,
    BULLETIN_WORKBOOK_REF,
    CATALOG_MAX_BYTES,
    STAGE_BULLETIN,
    STAGE_DOSSIER,
    STAGE_TAKEOFF,
    WORKSITE_PLATE_LIMIT,
    CatalogCache,
    RoundRefusal,
    append_revision,
    append_round_plate,
    append_round_plates,
    approval_state,
    approve_valuation,
    assignments_document_for_plate,
    assignments_for_plate,
    bulletin_export_contract,
    bulletin_sources_digest,
    bulletin_sources_state,
    bulletin_workbook_key,
    bulletin_workbook_ref,
    carry_approval_forward,
    compute_round_suggestions,
    current_stage,
    declared_identity_link,
    document_digest,
    extracted_plate_ids,
    head_revision,
    identity_link_preview,
    identity_links_of,
    load_catalog,
    load_round,
    plate_artifact_name,
    plate_assignments_changes,
    plate_packet_changes,
    plate_packet_document,
    plate_registration,
    plate_suggestions_changes,
    queue_plate_extractions,
    readable_valuation,
    render_valuation_workbook,
    require_assignments,
    require_base_version,
    require_document,
    require_plate,
    require_plate_packet,
    require_reviewed_packet,
    require_takeoff_overlay,
    require_takeoff_packet,
    require_unrefined_suggestions,
    require_worksite_takeoff,
    resolve_plate,
    round_plates,
    round_state_payload,
    search_round_catalog,
    signed_artifact_url,
    stage_not_ready,
    suggestions_document_for_plate,
    suggestions_of,
    takeoff_overlay_state,
    worksite_packets,
    worksite_plate_inputs,
    worksite_state,
)
from croquito_core.errors import DomainValidationError
from croquito_core.events import (
    EVENT_ESTIMATE_ACTION_RECORDED,
    EVENT_JOB_CREATED,
    EVENT_REVIEW_CALIBRATION_SET,
    EVENT_REVIEW_CHAINS_DECLARED,
    EVENT_REVIEW_DECISIONS_RECORDED,
    EVENT_REVIEW_PROPOSALS_DECIDED,
    EVENT_REVIEW_RECTIFICATIONS_RECORDED,
    EVENT_SCENE_APPROVED,
    EVENT_VALUATION_ACTION_RECORDED,
    build_domain_event,
)
from croquito_core.field import MeasurementStatus as FieldMeasurementStatus
from croquito_core.field import SurveyOperation, SurveyPacket, SurveyStatus
from croquito_core.ids import new_uuid7
from croquito_core.logging_config import configure_logging
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
from croquito_valuation.amendment_dossier import AmendmentDossier, build_amendment_dossier
from croquito_valuation.assignment import (
    CodeAssignmentBatch,
    CodeAssignmentInput,
    CodeAssignmentRevocationInput,
    CodeAssignmentSet,
    CodeSuggestionSet,
    ItemPackageClosureInput,
    apply_code_assignments,
    apply_code_assignments_over_cascade,
    apply_code_revocation,
)
from croquito_valuation.calc_matrix import CalcMatrix
from croquito_valuation.contract import (
    Amendment,
    AmendmentLine,
    ContractWorkbook,
    PriceAdjustment,
    apply_declared_amendment,
    build_next_round_contract,
)
from croquito_valuation.contract_from_estimate import build_contract_from_estimate
from croquito_valuation.errors import ValuationValidationError, valuation_errors
from croquito_valuation.estimate import Estimate, build_worksite_estimate
from croquito_valuation.models import (
    WORKSITE_KEY_PATTERN,
    PriceCatalog,
    PriceOrigin,
    Valuation,
)
from croquito_valuation.precedent import PRICE_SOURCE_UNDECLARED, PrecedentSeedPacket
from croquito_valuation.site_setup import (
    SiteSetupKit,
    apply_site_setup_kit,
    preview_site_setup_kit,
)
from croquito_valuation.takeoff import (
    TakeoffDecisionBatch,
    TakeoffDecisionInput,
    TakeoffPacket,
    apply_takeoff_decisions,
)
from croquito_valuation.template import default_template
from croquito_valuation.workbook_writer import consolidate_by_code
from croquito_valuation.worksite_calc import build_worksite_takeoff_valuation
from croquito_worker.association import AssociationSet
from croquito_worker.association_confidence import (
    CONFIDENCE_REFERENCE_THRESHOLD,
    confidence_shadow_json,
    verified_declared_chain,
)
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
from croquito_worker.dimension_closure import (
    ChainVerificationError,
    DimensionChain,
    suggest_chains,
    verify_chain,
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
from croquito_worker.valuation.catalog_search import (
    CATALOG_SEARCH_DEFAULT_LIMIT,
    CATALOG_SEARCH_MAX_LIMIT,
    SemanticArm,
)
from croquito_worker.valuation.round_extraction import (
    PLATE_IMAGE_REF,
    extraction_arm_spec,
    extraction_unavailable,
)
from croquito_worker.valuation.round_view import (
    REVIEWER_ROLE as VALUATION_REVIEWER_ROLE,
)
from croquito_worker.valuation.round_view import (
    anchor_counts,
    anchored_packet,
    count_closed,
    count_status,
    item_payload,
    matching_of,
    parse_quantity,
    pending_code_items,
    registered_item_ids,
    review_status,
    takeoff_counts,
)
from croquito_worker.valuation.sco_matching import embeddings_adapter_or_reason
from croquito_worker.valuation.suggestions import SemanticArmTelemetry
from croquito_worker.vision import (
    PixelGeometryValue,
    PixelLine,
    PixelPoint,
    PixelPolyline,
    VisionProposal,
    VisionProposalSet,
)


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


class MeResponse(ApiModel):
    subject: str
    tenant_id: str
    roles: list[str]
    #: Jornadas que este principal pode abrir, já resolvidas pelas três perguntas da F-034
    #: (ambiente, tenant e papel). A SPA renderiza esta lista; ela não recalcula papel.
    journeys: list[Journey]


class PlatformTenantResponse(ApiModel):
    """Estado legível do entitlement de um tenant, mesmo quando nunca foi ativado.

    Diferente de `AiProcessingEntitlementResponse` (o PUT, que só existe depois de
    ativar ao menos uma vez): aqui `agreement_reference`, `authorized_at` e
    `revoked_at` são opcionais porque um tenant que nunca teve entitlement criado
    ainda é um resultado válido — 200 com `enabled=false` e nulos, não 404.
    """

    tenant_id: str
    enabled: bool
    agreement_reference: str | None = None
    authorized_at: datetime | None = None
    revoked_at: datetime | None = None


class PlatformTenantListResponse(ApiModel):
    tenants: list[PlatformTenantResponse]


class SetJourneyEntitlementRequest(ApiModel):
    """Conceder (`enabled=true`) ou revogar (`enabled=false`) uma jornada para um tenant.

    Mesma forma de `SetAiProcessingEntitlementRequest` de propósito: é o mesmo tipo de
    fato — decisão comercial durável, com quem autorizou e quando — e o mesmo papel a
    administra. O par (tenant, jornada) vem da rota; o corpo carrega só o ato.
    """

    enabled: bool
    agreement_reference: str | None = Field(default=None, min_length=3, max_length=128)


class JourneyEntitlementResponse(ApiModel):
    """Uma autorização de (tenant, jornada), com o registro do ato que a criou.

    `authorized_by` sai daqui porque o ato é NOMINAL: a tela de plataforma mostra quem
    autorizou e quando. Uma autorização revogada continua sendo devolvida, com
    `revoked_at` carimbado — sumir com a linha apagaria a trilha do que houve antes.
    """

    tenant_id: str
    journey: Journey
    enabled: bool
    agreement_reference: str
    authorized_by: str
    authorized_at: datetime
    revoked_at: datetime | None = None


class JourneyAvailabilityResponse(ApiModel):
    """Estado declarado de uma jornada neste ambiente — leitura, nunca escrita.

    Mudar o estado é alterar configuração de ambiente e publicar, e por isso não existe
    rota para escrevê-lo: a tela mostra o estado para ninguém procurar um interruptor
    que não existe.
    """

    journey: Journey
    state: JourneyAvailability


class PlatformJourneyListResponse(ApiModel):
    journeys: list[JourneyAvailabilityResponse]
    entitlements: list[JourneyEntitlementResponse]


class PresignReferenceCatalogRequest(ApiModel):
    """Presign do `catalog.json` que vai ao acervo — sem `content_type`, e é deliberado.

    A rota existe porque publicar não pode depender da jornada do croqui (F-037 escopo 7):
    `POST /v1/uploads/presign` cai no prefixo `/v1/uploads`, que é do croqui, e num ambiente
    com essa jornada desligada o operador da plataforma receberia `403 JOURNEY_UNAVAILABLE`
    e o acervo ficaria sem como ser alimentado.

    O tipo não entra no corpo porque o acervo publica catálogo normalizado e nada mais:
    recebê-lo seria oferecer uma escolha que a rota recusaria em seguida. `ApiModel` recusa
    campo desconhecido, então um corpo que tente declarar `content_type` — de PDF ou até de
    JSON — é recusado no contrato. A extensão de `filename` continua sendo conferida contra
    o tipo por `_safe_filename`, que devolve `422 INVALID_UPLOAD` para nome que não seja
    `.json`.
    """

    filename: str = Field(min_length=1, max_length=255)
    size_bytes: int = Field(gt=0, le=100_000_000)
    sha256: str = Field(pattern=r"^[a-fA-F0-9]{64}$")


class PublishReferenceCatalogRequest(ApiModel):
    """Publica no acervo o `catalog.json` JÁ NORMALIZADO que subiu pelo presign.

    O corpo tem DOIS campos, e é deliberado que não tenha mais: `origin`,
    `reference_month`, `source_sha256` e a contagem de entradas são lidos de dentro do
    arquivo, nunca informados aqui. Rótulo que se digita ao lado do conteúdo é rótulo que
    pode discordar dele — e um catálogo publicado com a data-base errada mudaria o preço de
    todos os tenants que o escolhessem. `ApiModel` recusa campo desconhecido, então um corpo
    que tente declará-los é recusado no contrato, antes de qualquer leitura.

    O que se escreve é só o nome de exibição: é ele que distingue, na escolha, duas linhas
    que sem ele seriam ambas "SCO".
    """

    upload_id: UUID
    display_name: str = Field(min_length=3, max_length=200)


class ReferenceCatalogResponse(ApiModel):
    """Uma publicação do acervo como a administração da plataforma a lê.

    `object_key` NÃO sai daqui, pelo mesmo motivo que a `CascadeEntry` não publica a dela: a
    chave é referência interna do store. E aqui a razão é mais forte — o objeto do acervo
    fica fora de `tenants/` e nenhuma rota o assina (ADR-0047 decisão 6), então publicar o
    endereço só ofereceria um caminho que não existe.
    """

    reference_catalog_id: UUID
    display_name: str
    origin: str
    reference_month: str
    entry_count: int
    object_sha256: str
    source_sha256: str
    available: bool
    published_by: str
    published_at: datetime
    withdrawn_at: datetime | None = None


class ReferenceCatalogListResponse(ApiModel):
    catalogs: list[ReferenceCatalogResponse]


#: Nome de um parâmetro de obra na fronteira `/v1`. O teto é o de `SiteSetupOperand.parameter`
#: (`site_setup.py`): um nome que o domínio recusaria não chega a ser procurado no acervo.
SiteSetupParameterName = Annotated[str, Field(min_length=1, max_length=60)]

#: Valor declarado de um parâmetro, sempre TEXTO. Decimal exato não viaja como número de JSON
#: (ADR-0038, decisão 2): ele já teria passado por binário antes de chegar aqui.
SiteSetupParameterValue = Annotated[str, Field(min_length=1, max_length=40)]

#: Id de parcela do acervo citado numa exclusão. Sem `pattern` de propósito: id malformado é,
#: por definição, id que este acervo não tem, e o domínio já o recusa por extenso
#: (`SITE_SETUP_UNKNOWN_PARCEL`). Recusá-lo no esquema faria a mesma causa sair como erro do
#: FastAPI numa rota e como `problem+json` na outra.
SiteSetupParcelId = Annotated[str, Field(min_length=1, max_length=40)]


class PublishSiteSetupKitRequest(ApiModel):
    """Publica no acervo da PLATAFORMA um acervo de parcelas de canteiro (F-042, ADR-0060).

    O corpo tem dois campos, e é deliberado que não tenha mais: `version` e `source_label` são
    lidos de DENTRO do documento, nunca informados ao lado. Rótulo que se digita ao lado do
    conteúdo é rótulo que pode discordar dele — e um acervo publicado com a versão errada
    passaria a ser confundido, na matriz, com as parcelas de outra aplicação (o merge do apply
    é por `kit_version`).

    `document` chega como objeto CRU, e não como `SiteSetupKit` tipado, pelo mesmo motivo de
    `BuildEstimateRequest.calc_matrix`: um modelo do domínio embutido faria o Pydantic recusar
    durante o parsing do corpo, e a invariante sairia como erro de esquema do FastAPI em vez do
    `application/problem+json` com o código estável do domínio.
    """

    name: str = Field(min_length=3, max_length=200)
    document: dict[str, Any]


class PrecedentSeedResponse(ApiModel):
    """O que a semeadura do índice de precedentes fez, em contagens.

    Nenhum rótulo volta pelo fio: quem semeou tem o pacote em mãos, e devolvê-lo mastigado
    só faria texto de cliente atravessar a fronteira mais uma vez sem necessidade.

    `observations_skipped` é a metade que prova a idempotência: reingerir a mesma praça
    devolve `observations_ingested: 0`, e a contagem de praças do índice não se move.
    """

    worksite_key: str
    observations_ingested: int
    observations_skipped: int
    labels: int


class SiteSetupKitResponse(ApiModel):
    """Um acervo de parcelas de canteiro como a administração o lê.

    O documento inteiro NÃO sai daqui: são dezenas de parcelas com rótulo e operando por linha
    de listagem, e quem precisa delas é a pré-visualização, que as lê do banco. O que sai é o
    que distingue duas linhas — nome, versão, de onde foi autorado e quantas parcelas tem.
    """

    kit_id: UUID
    name: str
    kit_version: str
    origin: Literal["platform", "tenant"]
    """Derivado de `tenant_id` na leitura, nunca uma terceira coluna que possa discordar."""
    source_label: str
    parcel_count: int
    document_sha256: str
    available: bool
    created_by: str
    created_at: datetime
    withdrawn_at: datetime | None = None


class SiteSetupKitListResponse(ApiModel):
    kits: list[SiteSetupKitResponse]


class PresignReferenceCatalogIndexRequest(ApiModel):
    """Presign do `catalog-embeddings.json` que vai ao acervo de índices.

    Idêntico em forma ao presign do catálogo, e pela mesma razão: o tipo é fixo em
    `application/json` porque o que se publica aqui é o documento do índice e nada mais, e
    publicar não pode depender da jornada do croqui (o portão de disponibilidade da F-034 é
    dependência do router, e `/v1/uploads` é do croqui).

    `size_bytes` continua com o teto do presign — 100 MB —, e não com
    `CATALOG_INDEX_MAX_BYTES`: são coisas diferentes. O presign diz quanto o storage aceita
    receber; o teto de leitura diz quanto a API aceita carregar na memória do processo, e é
    ele que recusa a publicação, por extenso e com a causa nomeada. Conferir o tamanho duas
    vezes em lugares que significam coisas diferentes esconderia qual dos dois recusou.
    """

    filename: str = Field(min_length=1, max_length=255)
    size_bytes: int = Field(gt=0, le=100_000_000)
    sha256: str = Field(pattern=r"^[a-fA-F0-9]{64}$")


class PublishReferenceCatalogIndexRequest(ApiModel):
    """Publica o índice de embeddings de UM catálogo já publicado no acervo.

    Dois campos, e é deliberado que não tenha mais: `provider`, `model_id`, `dims`,
    `text_recipe`, a contagem de códigos e o digest do catálogo indexado são lidos de dentro
    do documento, nunca informados aqui. Rótulo que se digita ao lado do conteúdo é rótulo
    que pode discordar dele — e um índice publicado com a receita errada degradaria a busca
    em silêncio para todo tenant que o usasse.

    `reference_catalog_id` é o único vínculo declarado, e ele existe para ser CONFERIDO: o
    `catalog_sha256` de dentro do documento tem de bater com o `source_sha256` daquela
    entrada do acervo. Não é por ele que o índice será encontrado depois — a busca é por
    digest da fonte (ADR-0054 D3) —, é por ele que a publicação prova que sabe o que está
    publicando.
    """

    upload_id: UUID
    reference_catalog_id: UUID


class ReferenceCatalogIndexResponse(ApiModel):
    """Uma publicação de índice como a administração da plataforma a lê.

    `object_key` NÃO sai daqui, pelo mesmo motivo do acervo — e aqui a razão é mais forte
    ainda: o objeto fica fora de `tenants/`, nenhuma rota o assina e ele nunca é baixado
    pelo cliente. Os vetores também não saem, obviamente: o que a tela precisa é da
    identidade do índice (quem, com qual modelo, sobre qual catálogo, com qual receita).
    """

    reference_catalog_index_id: UUID
    reference_catalog_id: UUID
    catalog_source_sha256: str
    text_recipe: str
    provider: str
    model_id: str
    dims: int
    code_count: int
    object_sha256: str
    available: bool
    published_by: str
    published_at: datetime
    withdrawn_at: datetime | None = None


class ReferenceCatalogIndexListResponse(ApiModel):
    indexes: list[ReferenceCatalogIndexResponse]


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


class StageDurationResponse(ApiModel):
    """Uma etapa do job e quanto ela durou; `duration_ms` ausente = etapa ainda aberta."""

    stage: str
    status: str
    duration_ms: int | None = None


class CycleMetricsResponse(ApiModel):
    total_ms: int | None = None
    stages: list[StageDurationResponse]


class HumanMetricsResponse(ApiModel):
    review_revisions: int
    decisions_total: int
    confirmed: int
    corrected: int
    rejected: int
    #: `null` quando não houve decisão nenhuma. Não é `0.0`: "nada foi decidido" e "nada
    #: foi corrigido do que se decidiu" são estados diferentes.
    correction_rate: float | None = None
    rectifications: int
    #: Touch time real é a T4 desta feature; até lá, ausência declarada.
    interaction_ms_total: int | None = None


class AutomationMetricsResponse(ApiModel):
    """Campos reservados da F-029: enquanto ela não aterrissa, os dois são `null`."""

    auto_association_rate: float | None = None
    review_rate: float | None = None


class AiCostMetricsResponse(ApiModel):
    calls: int
    input_tokens: int
    output_tokens: int
    #: Decimal exato como TEXTO, a mesma disciplina de `chat_turns.estimated_cost_usd`:
    #: `float` de custo perde centavo em soma, e é somando que o portal calcula custo por
    #: transação.
    estimated_cost_usd: str


class JobMetricsResponse(ApiModel):
    job_id: UUID
    cycle: CycleMetricsResponse
    human: HumanMetricsResponse
    automation: AutomationMetricsResponse
    ai_cost: AiCostMetricsResponse


class MetricsPeriodResponse(ApiModel):
    """Eco do recorte aplicado, já normalizado em UTC; `null` significa "sem limite"."""

    from_: datetime | None = Field(default=None, alias="from")
    to: datetime | None = None

    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class MetricsSummaryResponse(ApiModel):
    period: MetricsPeriodResponse
    jobs_total: int
    jobs_completed: int
    jobs_failed: int
    #: Denominador de `avg_correction_rate`: sem ele a média não diz sobre quantos jobs foi.
    jobs_with_decisions: int
    avg_cycle_total_ms: int | None = None
    avg_correction_rate: float | None = None
    ai_cost: AiCostMetricsResponse
    valuation_rounds_total: int
    estimate_rounds_total: int
    #: Custo das extrações pagas das rodadas de medição e de orçamento do período.
    rounds_ai_cost: AiCostMetricsResponse


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


#: Teto do touch time aceito num envio: 24 horas em milissegundos. Acima disso não é
#: sessão de revisão nenhuma — é aba esquecida aberta, relógio do cliente saltando ou
#: soma de um cronômetro que ninguém zerou.
MAX_INTERACTION_MS: Final = 24 * 60 * 60 * 1000

#: Campos de TELEMETRIA do payload: descritos no contrato, fora da identidade do comando.
#: São excluídos do `_request_hash` por duas razões que apontam para o mesmo lado: um
#: replay legítimo (mesma `Idempotency-Key`, cronômetro necessariamente diferente) não
#: pode virar `IDEMPOTENCY_KEY_REUSED`, e o hash gravado ANTES deste campo existir
#: precisa continuar batendo com o de um envio idêntico feito depois.
TELEMETRY_PAYLOAD_FIELDS: Final[frozenset[str]] = frozenset({"interaction_ms"})


def _observational_interaction_ms(value: object) -> int | None:
    """Lê o touch time autorrelatado; o que não for plausível vira `None`, nunca 422.

    Isto é telemetria, não dado de negócio: o ato humano — a decisão, a correção — não
    pode ser recusado porque o cronômetro da tela veio negativo, veio como texto ou veio
    com um número que não descreve sessão de trabalho nenhuma. Recusar aqui inverteria a
    prioridade e faria a medição do processo atrapalhar o processo.

    `bool` cai fora de propósito, ainda que seja subclasse de `int`: um `true` no campo
    significaria "1 ms de revisão", que é uma medida inventada a partir de um engano.
    """
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        measured = value
    elif isinstance(value, float) and math.isfinite(value):
        measured = int(value)
    else:
        return None
    return measured if 0 <= measured <= MAX_INTERACTION_MS else None


#: Touch time do envio, em milissegundos, medido pela tela que o produziu.
InteractionMs = Annotated[int | None, BeforeValidator(_observational_interaction_ms)]


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
    # Observacional e opcional: ausente diz "não medido" (cliente antigo, aba fechada
    # antes do envio), nunca "zero". Ver `_observational_interaction_ms`.
    interaction_ms: InteractionMs = None


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
    interaction_ms: InteractionMs = None


class ReviewChainCommand(ApiModel):
    """Declara ou retrata uma cadeia de cotas: estas parcelas partilham este total.

    A declaração é do humano, não do motor: `suggest_chains` só oferece candidatos, e é
    aqui que alguém assume que a soma tem significado no desenho. Cadeia que NÃO fecha é
    declarável de propósito — o desencontro é justamente o que se quer registrar.
    """

    base_version: int = Field(ge=1)
    action: Literal["declare", "retract"]
    total_id: str | None = Field(default=None, pattern=r"^rd_[a-f0-9]{16}$")
    part_ids: list[Annotated[str, Field(pattern=r"^rd_[a-f0-9]{16}$")]] = Field(
        default_factory=list, max_length=16
    )
    # Sem `pattern`: id desconhecido é 404, e recusar antes pelo formato transformaria a
    # mesma pergunta ("existe esta cadeia?") em duas respostas diferentes.
    chain_id: str | None = Field(default=None, min_length=1, max_length=64)


class FieldWitnessSource(ApiModel):
    type: Literal["survey_measurement", "photo_reading"]
    source_id: str = Field(min_length=1, max_length=128)
    survey_id: str | None = Field(default=None, min_length=1, max_length=36)

    @model_validator(mode="after")
    def validate_source(self) -> FieldWitnessSource:
        if self.type == "survey_measurement" and self.survey_id is None:
            raise ValueError("medida do app exige survey_id")
        if self.type == "photo_reading" and self.survey_id is not None:
            raise ValueError("leitura de foto não aceita survey_id")
        return self


class ReviewWitnessCommand(ApiModel):
    base_version: int = Field(ge=1)
    action: Literal["associate", "retract"]
    reading_id: str | None = Field(default=None, pattern=r"^rd_[a-f0-9]{16}$")
    source: FieldWitnessSource | None = None
    witness_id: UUID | None = None

    @model_validator(mode="after")
    def validate_action(self) -> ReviewWitnessCommand:
        if self.action == "associate":
            if self.reading_id is None or self.source is None or self.witness_id is not None:
                raise ValueError("associação exige reading_id e source, sem witness_id")
        elif self.witness_id is None or self.reading_id is not None or self.source is not None:
            raise ValueError("retração exige somente witness_id")
        return self


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


class ShapeCorrectionVertexRequest(ApiModel):
    """Um vértice da forma corrigida, em PIXELS da imagem fonte — o espaço da proposta."""

    x: float = Field(ge=0)
    y: float = Field(ge=0)


class CorrectProposalShapeRequest(ApiModel):
    """Correção humana de forma: cria proposta NOVA, jamais altera a observada.

    A regra inteira é do ADR-0050 — `docs/adr/0050-correcao-humana-de-forma-como-`
    `proposta-derivada.md`. A forma corrigida nasce num `VisionProposalSet` de proveniência própria
    (`human-correction-v1`), declara em `derived_from` de quais propostas OBSERVADAS ela
    nasceu, e continua `unresolved`/`export=false` — a promoção de precisão segue sendo
    exclusiva da calibração, e `exact` só nasce de cota confirmada.

    `derived_from` obrigatório e não vazio é o que impede a feature de virar um editor de
    geometria dentro do navegador: sem forma de origem não há correção, há desenho.

    A justificativa é obrigatória como em `accept`/`reject` — corrigir a geometria que vai
    virar desenho é decisão de domínio, não ajuste de interface.
    """

    base_review_version: int = Field(ge=1)
    base_scene_version: int = Field(ge=1)
    derived_from: list[str] = Field(min_length=1, max_length=20)
    #: Dois vértices são uma linha; três ou mais, uma polilinha. O teto acompanha o do
    #: contrato de geometria (`PixelPolyline`), e não é escolha desta fronteira.
    vertices: list[ShapeCorrectionVertexRequest] = Field(min_length=2, max_length=200)
    closed: bool = False
    justification: str = Field(min_length=3, max_length=500)

    @field_validator("derived_from")
    @classmethod
    def validate_derived_from(cls, value: list[str]) -> list[str]:
        for proposal_id in value:
            if not re.fullmatch(r"vp_[a-f0-9]{16}", proposal_id):
                raise ValueError("derivação aponta para id de proposta inválido")
        if len(set(value)) != len(value):
            raise ValueError("derivação repete a mesma proposta")
        return value


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


class DeclaredChainResponse(ApiModel):
    """Uma cadeia declarada por uma pessoa, reconferida contra o pacote de hoje.

    O que fica gravado é a declaração; `chain`, `status` e `issue` são recomputados a
    cada leitura. Por isso existe `stale`: a cota participante pode ter sido retificada
    ou rejeitada depois, e nesse caso a cadeia não é apagada — ela passa a avisar que
    perdeu o pé, e cabe a uma pessoa retratá-la ou declará-la de novo.
    """

    chain_id: str
    declared_by: str
    declared_at: datetime
    chain: DimensionChain | None = None
    status: Literal["closes", "mismatch", "stale"]
    issue: Issue | None = None


class ReadingConfidence(ApiModel):
    """ "Li certo?" por leitura — observação, nunca decisão nem veto de exportação."""

    reading_id: str
    reading_confidence: float


class ShadowChoiceResponse(ApiModel):
    """A associação que um corte hipotético TERIA escolhido para uma leitura."""

    reading_id: str
    proposal_id: str
    reading_confidence: float
    association_confidence: float


class ShadowDecisionResponse(ApiModel):
    """Um ponto da grade e o que ele teria auto-decidido — nenhuma decisão real."""

    reading_threshold: float
    association_threshold: float
    auto_choices: list[ShadowChoiceResponse]


class FieldWitnessResponse(ApiModel):
    witness_id: UUID
    reading_id: str
    source_type: Literal["survey_measurement", "photo_reading"]
    source_id: str
    survey_id: str | None = None
    reading_value_mm: Decimal
    source_value_mm: Decimal
    difference_mm: Decimal
    associated_by: str
    associated_at: datetime


#: A lista fechada de categorias da classificação (ADR-0049 D9), duplicada aqui como as
#: demais camadas do arquivo: a API não importa o enum do worker.
FieldObservationCategory = Literal[
    "MURO", "ALAMBRADO", "PORTAO", "PATAMAR", "EQUIPAMENTOS", "DETALHES", "UNKNOWN"
]


class FieldObservationSource(ApiModel):
    """Resumo do rascunho da IA no instante do ato, copiado do artefato pelo servidor.

    Preserva o que a IA propôs mesmo depois de o revisor corrigir a categoria, e sobrevive à
    expiração do artefato. Nunca é aceito do cliente — mesma regra do valor da testemunha.
    """

    analysis_id: UUID
    category: FieldObservationCategory
    provider: str | None = None
    model_id: str | None = None
    prompt_version: str | None = None
    schema_version: str | None = None


class FieldObservationResponse(ApiModel):
    observation_id: UUID
    origin: Literal["survey", "standalone"]
    evidence_id: UUID
    status: Literal["ACTIVE", "SUPERSEDED", "DISMISSED"]
    #: Ausentes só em `DISMISSED`, que registra o ato de descartar, não uma observação.
    category: FieldObservationCategory | None = None
    description: str | None = None
    source: FieldObservationSource
    supersedes_observation_id: UUID | None = None
    recorded_by: str
    recorded_at: datetime


class FieldObservationCommand(ApiModel):
    base_version: int = Field(ge=1)
    action: Literal["record", "dismiss"]
    origin: Literal["survey", "standalone"]
    evidence_id: UUID
    category: FieldObservationCategory | None = None
    description: str | None = Field(default=None, min_length=1, max_length=500)
    corrects_observation_id: UUID | None = None

    @model_validator(mode="after")
    def validate_action(self) -> FieldObservationCommand:
        if self.action == "record":
            if self.category is None or self.description is None:
                raise ValueError("registrar exige category e description")
        elif (
            self.category is not None
            or self.description is not None
            or self.corrects_observation_id is not None
        ):
            raise ValueError("descartar não leva category, description nem correção")
        return self


class ReviewResponse(ApiModel):
    job_id: UUID
    review_id: UUID
    version: int
    packet: ReviewPacket
    associations: AssociationSet
    proposals: VisionProposalSet | None = None
    # Correções humanas de forma (F-018), num conjunto de proveniência própria
    # (`detector_version = "human-correction-v1"`, ADR-0050 decisão 1). Separado de
    # `proposals` para que a observação da máquina continue legível depois da correção —
    # é dela que sai a única medida objetiva de quanto o modelo erra.
    #
    # `None` quando ninguém corrigiu forma nesta revisão, que é o que a coluna diz. Mesmo
    # motivo de default dos demais: resposta idempotente gravada antes do campo é
    # revalidada no replay e não pode virar 500.
    shape_corrections: VisionProposalSet | None = None
    selected_associations: dict[str, str]
    calibration: ProposalCalibrationResponse | None = None
    proposal_decisions: list[ProposalDecisionResponse] = Field(default_factory=list)
    issues: list[Issue]
    blockers: list[str]
    required_criteria: list[RequiredCriterion] = Field(default_factory=list)
    # Conferência aritmética das cotas confirmadas: sugestão calculada na hora e
    # declaração humana persistida. Nenhuma das duas entra em `blockers` — divergência de
    # cadeia é aviso para o revisor, nunca veto de exportação.
    #
    # `default_factory=list` nas duas porque a resposta idempotente gravada ANTES destes
    # campos existirem é revalidada no replay; sem o default, um `Idempotency-Key` de
    # antes do deploy passaria a responder 500.
    suggested_chains: list[DimensionChain] = Field(default_factory=list)
    declared_chains: list[DeclaredChainResponse] = Field(default_factory=list)
    # Confiança determinística e shadow log (F-029): tudo OBSERVACIONAL. Nada aqui
    # decide leitura, associação, blocker, cena ou exportação; a associação que vale
    # continua sendo a explícita em `selected_associations`, e ela só nasce de ato
    # humano. As confianças por candidato viajam dentro de `associations`.
    #
    # Mesmo motivo de default da F-023: a resposta idempotente gravada ANTES destes
    # campos existirem é revalidada no replay, e sem default um `Idempotency-Key` de
    # antes do deploy passaria a responder 500. Revisão gravada antes da coluna
    # `confidence_shadow_json` responde igual: listas vazias e taxas nulas.
    reading_confidences: list[ReadingConfidence] = Field(default_factory=list)
    confidence_shadow: list[ShadowDecisionResponse] = Field(default_factory=list)
    auto_association_rate: float | None = None
    review_rate: float | None = None
    field_witnesses: list[FieldWitnessResponse] = Field(default_factory=list)
    # Observações humanas sobre a classificação por IA (F-030 T7): versionadas com a revisão,
    # FORA da SceneRevision. `default_factory=list` pelo mesmo motivo dos demais: a resposta
    # idempotente gravada antes do campo é revalidada no replay e não pode virar 500.
    field_observations: list[FieldObservationResponse] = Field(default_factory=list)
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


class UnappliedReadingOut(ApiModel):
    """Uma leitura confirmada que não virou vão, com o motivo declarado pelo traçado.

    `cause` é código estável do domínio (mesmo formato de `Issue.code`), nunca frase de
    solver: a frase que o profissional lê vive na `Issue` da cena.
    """

    reading_id: str
    cause: str
    target_proposal_ids: list[str] = Field(default_factory=list)


class ContestedSpanOut(ApiModel):
    """Duas ou mais leituras confirmadas prometendo distâncias diferentes para o mesmo vão.

    Diagnóstico: não é blocker e não muda `solve_status` — quem decide o desfecho continua
    sendo o resíduo.
    """

    axis: Literal["x", "y"]
    reading_ids: list[str] = Field(default_factory=list)
    # Float como no resumo de resíduos: a precisão escrita da cota vive na cena.
    values_m: list[float] = Field(default_factory=list)
    proposal_ids: list[str] = Field(default_factory=list)


class AppliedSpanOut(ApiModel):
    """Onde, em metros da prancha, cada cota aplicada ancorou (`start_m <= end_m`)."""

    reading_id: str
    axis: Literal["x", "y"]
    value_m: float
    start_m: float
    end_m: float
    proposal_id: str
    second_proposal_id: str | None = None
    gap: bool = False


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
    # Aditivos (F-025): a lista de ids acima continua sendo o contrato antigo, na mesma
    # ordem; estes dizem por que, quem disputa com quem e onde a cota aplicada ancorou.
    unapplied_readings: list[UnappliedReadingOut] = Field(default_factory=list)
    contested_spans: list[ContestedSpanOut] = Field(default_factory=list)
    applied_spans: list[AppliedSpanOut] = Field(default_factory=list)
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


CATALOG_CONTENT_TYPE: Final = "application/json"


class PriceAdjustmentRequest(ApiModel):
    """Declaração de reajuste na abertura da rodada (F-039, ADR-0055).

    O reajuste é do CONTRATO, e por isso só existe no caminho que tem contratado: rodada
    aberta por upload de catálogo não tem consolidado a reajustar. A declaração é gravada com
    o consolidado e é imutável na rodada, como ele (ADR-0048, decisão 7).

    O carimbo de identidade não entra por aqui: `declared_by` e `declared_at` vêm do
    `Principal` e do relógio do servidor, como em toda decisão da cadeia.

    `factor` viaja como TEXTO pelo mesmo motivo da quantidade do takeoff: fator é `Decimal`
    exato, e um `float` de JSON já teria perdido a escala escrita antes de chegar aqui.
    """

    kind: Literal["index_factor", "catalog_version"]
    reference_period: str = Field(min_length=1, max_length=60)
    note: str | None = Field(default=None, min_length=1, max_length=300)
    #: `index_factor`: o índice e o fator, obrigatórios juntos — fator sem índice não é
    #: conferível contra a publicação oficial.
    index_label: str | None = Field(default=None, min_length=1, max_length=60)
    factor: str | None = Field(default=None, min_length=1, max_length=20)
    #: `catalog_version`: o upload da versão nova. O servidor resolve o preço de cada código
    #: contratado a partir dela e materializa a tabela na declaração (ADR-0055, decisão 4) —
    #: o cliente não informa preço nenhum.
    catalog_upload_id: UUID | None = None

    @model_validator(mode="after")
    def validate_kind(self) -> PriceAdjustmentRequest:
        if self.kind == "index_factor":
            if self.factor is None or self.index_label is None:
                raise ValueError("reajuste por índice exige fator e index_label")
            if self.catalog_upload_id is not None:
                raise ValueError("reajuste por índice não cita catálogo")
            return self
        if self.catalog_upload_id is None:
            raise ValueError("reajuste por versão de tabela exige catalog_upload_id")
        if self.factor is not None or self.index_label is not None:
            raise ValueError("reajuste por versão de tabela não carrega fator de índice")
        return self


class AmendmentLineRequest(ApiModel):
    """Um código alterado por uma RE-RA: delta com sinal, ou item novo.

    `quantity_delta` viaja como TEXTO pelo mesmo motivo do fator do reajuste: é `Decimal`
    exato, e um `float` de JSON já teria perdido a escala escrita.

    O item novo **não** informa descrição, unidade nem preço: o servidor os materializa do
    catálogo contratual instalado na rodada (ADR-0056, decisão 7), como o `catalog_version`
    faz com o preço. Deixar o cliente informá-los aceitaria um número de contrato vindo de
    fora, que é o oposto do que este consolidado existe para garantir.
    """

    code: str = Field(min_length=1, max_length=30)
    quantity_delta: str = Field(min_length=1, max_length=20)
    is_new_item: bool = False
    note: str | None = Field(default=None, min_length=1, max_length=200)


class AmendmentRequest(ApiModel):
    """Declaração de RE-RA na abertura da rodada (F-040, ADR-0056).

    Espelho de `PriceAdjustmentRequest`: só existe no caminho que tem contratado, é gravada
    com o consolidado e imutável na rodada. O carimbo de identidade não entra por aqui —
    `declared_by` e `declared_at` vêm do `Principal` e do relógio do servidor.
    """

    label: str = Field(min_length=1, max_length=60)
    reference_period: str = Field(min_length=1, max_length=60)
    note: str | None = Field(default=None, min_length=1, max_length=300)
    lines: list[AmendmentLineRequest] = Field(min_length=1)


class CreateValuationRoundRequest(ApiModel):
    """Rodada nova: a obra, o catálogo instalado e os rótulos que o boletim exige.

    `period_number`, `address` e `contract_label` são atributos da RODADA (decisão humana de
    2026-08-17): nenhuma rota do contrato os recebia e sem eles o boletim não fecha. O
    carimbo de identidade não entra por aqui — `reviewer_id`, `reviewer_role`, `decided_at` e
    `decision_id` são recusados pelo `extra="forbid"` do `ApiModel`, não por lista negra.

    `worksite_key` repete o padrão que o domínio exige de `WorksiteBulletin`
    (`WORKSITE_KEY_PATTERN`) porque a chave é IMUTÁVEL na rodada: aceitá-la livre aqui faria
    uma rodada nascer válida com `PRAÇA X` e só quebrar no `POST /calc`, dezenas de decisões
    depois, quando já não há o que corrigir sem abrir rodada nova.

    **Duas origens, uma de cada vez (F-036, ADR-0048)**:

    - `catalog_upload_id` — o caminho de sempre. A obra e o catálogo são declarados aqui, e a
      rodada não terá contratado contra o que conferir;
    - `estimate_round_id` — a rodada nasce de um orçamento **assinado** sob o regime
      `contracted_demand`. Obra, catálogo e contratado vêm do conteúdo assinado, e por isso
      `worksite_key`, `worksite_name` e `address` são **recusados** neste caminho: aceitá-los
      abriria a porta para a rodada declarar uma obra diferente da que foi orçada, e nenhum
      número do consolidado é informado por humano.
    """

    worksite_key: str | None = Field(default=None, pattern=WORKSITE_KEY_PATTERN)
    worksite_name: str | None = Field(default=None, min_length=1, max_length=120)
    catalog_upload_id: UUID | None = None
    estimate_round_id: UUID | None = None
    #: A medição seguinte (F-040): abre a rodada `n+1` a partir da rodada anterior aprovada.
    #: Obra, catálogo e contratado vêm dela, e o consolidado soma os períodos já lançados.
    previous_round_id: UUID | None = None
    reference_label: str = Field(min_length=1, max_length=120)
    period_number: int = Field(ge=1, le=999)
    address: str | None = Field(default=None, min_length=1, max_length=200)
    contract_label: str | None = Field(default=None, min_length=1, max_length=120)
    #: Reajuste do contrato, opcional (F-039). Só no caminho do orçamento assinado: sem
    #: contratado não há preço contratual a reajustar.
    price_adjustment: PriceAdjustmentRequest | None = None
    #: RE-RA declarada na abertura, opcional (F-040). Como o reajuste, só no caminho do
    #: orçamento assinado: sem contratado não há quantidade contratual a re-ratificar.
    amendment: AmendmentRequest | None = None

    @model_validator(mode="after")
    def validate_origin(self) -> CreateValuationRoundRequest:
        """Exatamente uma origem, e os campos da obra só existem na origem que os define."""
        origins = {
            "catalog_upload_id": self.catalog_upload_id,
            "estimate_round_id": self.estimate_round_id,
            "previous_round_id": self.previous_round_id,
        }
        provided = [name for name, value in origins.items() if value is not None]
        if len(provided) != 1:
            raise ValueError(
                "informe exatamente uma origem: catalog_upload_id, estimate_round_id OU "
                "previous_round_id"
            )
        # As duas origens contratadas (orçamento assinado e medição seguinte) trazem obra,
        # catálogo e contratado de dentro do sistema; só o upload declara a obra aqui.
        from_contract = self.estimate_round_id is not None or self.previous_round_id is not None
        if from_contract:
            declared = [
                name
                for name, value in (
                    ("worksite_key", self.worksite_key),
                    ("worksite_name", self.worksite_name),
                    ("address", self.address),
                )
                if value is not None
            ]
            if declared:
                raise ValueError(
                    "obra e endereço vêm da origem contratada e não são declarados aqui: "
                    + ", ".join(declared)
                )
        elif self.worksite_key is None or self.worksite_name is None:
            raise ValueError("worksite_key e worksite_name são obrigatórios sem origem contratada")
        if self.price_adjustment is not None and not from_contract:
            raise ValueError(
                "reajuste exige origem contratada (orçamento assinado ou medição seguinte): "
                "sem contratado não há preço contratual a reajustar"
            )
        if self.amendment is not None and not from_contract:
            raise ValueError(
                "RE-RA exige origem contratada (orçamento assinado ou medição seguinte): "
                "sem contratado não há quantidade contratual a re-ratificar"
            )
        return self


class ValuationRoundResponse(ApiModel):
    round_id: UUID
    version: int
    status: str
    created_at: datetime


class ValuationRoundSummary(ApiModel):
    round_id: UUID
    worksite_key: str
    worksite_name: str
    reference_label: str
    period_number: int
    version: int
    status: str
    stage: str
    extraction_status: str
    created_at: datetime
    updated_at: datetime
    #: Se a medição da rodada foi aprovada e não caducou (F-040): é o que a tela mostra com o
    #: selo, e a base do saldo da medição seguinte.
    approved: bool = False
    #: Se esta rodada pode abrir a medição seguinte: aprovada E com consolidado gravado. Sem
    #: contratado de origem não há acumulado a somar (ADR-0056, decisão 4).
    can_open_next: bool = False


class ValuationRoundPage(ApiModel):
    items: list[ValuationRoundSummary]
    next_cursor: str | None = None


class ValuationOriginSummary(ApiModel):
    """Um orçamento que pode originar uma medição, com o estado da assinatura declarado.

    `signature` sai por extenso em vez de um booleano porque os três estados levam a atos
    diferentes: `signed` abre a medição, `stale` pede assinar a versão atual, e `unsigned`
    pede assinar. Um `approved: false` não distinguiria os dois últimos, e é justamente a
    distinção que o desenho aprovado mostra.

    `total_amount` e `code_count` são o que a lista precisa para a pessoa reconhecer o
    orçamento sem abri-lo. Vêm do conteúdo montado, e não de coluna: o orçamento é
    recomputado na leitura, e servir um total gravado faria um documento adulterado no banco
    passar por bom.
    """

    round_id: UUID
    worksite_name: str
    reference_label: str
    signature: Literal["signed", "stale", "unsigned"]
    approved_by: str | None = None
    approved_at: datetime | None = None
    #: Digest do conteúdo ASSINADO; é ele que a medição guarda como "medi contra o quê".
    estimate_digest: str | None = None
    code_count: int
    total_amount: str


class ValuationOriginsResponse(ApiModel):
    """Os orçamentos elegíveis, do mais recente para o mais antigo.

    Sem cursor, ao contrário da listagem de rodadas: a lista já nasce filtrada pelo regime e
    pela montagem, e paginar uma escolha que cabe na tela custaria mais do que resolve. Se um
    tenant chegar a ter mais orçamentos sob contrato do que cabe numa escolha, o problema é de
    desenho da tela, não de transporte.
    """

    items: list[ValuationOriginSummary]


PlateIdQuery = Annotated[
    str | None,
    Query(
        min_length=1,
        max_length=64,
        description=(
            "Folha da praça a ler. Ausente, a leitura é a da primeira folha — o "
            "comportamento de sempre (F-046)."
        ),
    ),
]
"""A folha escolhida numa leitura da praça, sempre OPCIONAL (F-046 T4c).

Um alias só, para que as três leituras por folha — prancha, takeoff e overlay — declarem o
mesmo parâmetro com o mesmo limite e a mesma descrição. Ele nunca tem valor padrão diferente
de `None`: a ausência é o que mantém toda tela que ainda não conhece a praça respondendo
exatamente como antes.

O limite de 64 caracteres é o de `plate_id` no domínio (`CodeAssignmentSet.plate_id`,
`TakeoffItemAddressRequest.plate_id`): um id maior que isso não é folha de praça nenhuma, e
recusá-lo na fronteira evita carregar a praça para procurar o que não pode existir."""


class AssociatePlateRequest(ApiModel):
    upload_id: UUID
    base_version: int = Field(ge=1)


class AppendPlatesRequest(ApiModel):
    """Ato em lote: quais páginas do documento enviado viram folhas da praça (F-046 T4).

    `page_numbers` é EXIGIDO e não tem valor padrão. Não é rigor decorativo: promover todas
    as páginas automaticamente encheria a praça de quadro de áreas e carimbo, e foi recusado
    nominalmente no pacote de design aprovado. A escolha é humana, explícita e em lote.

    O teto de 12 páginas por requisição é o teto da praça (`WORKSITE_PLATE_LIMIT`) repetido na
    fronteira: um corpo com mil páginas seria recusado de todo jeito, e recusá-lo antes de
    chegar ao domínio evita carregar a lista para nada.
    """

    upload_id: UUID
    base_version: int = Field(ge=1)
    # Página é 1-based; `ge=1` recusa o zero e o negativo na fronteira, em vez de deixá-los
    # virar uma folha que só a ingestão descobriria ser impossível.
    page_numbers: list[Annotated[int, Field(ge=1)]] = Field(
        min_length=1, max_length=WORKSITE_PLATE_LIMIT
    )


class ValuationPlateSummary(ApiModel):
    """Uma folha da praça como o lote a devolve: identidade, origem e página."""

    plate_id: str
    position: int
    page_number: int
    source_sha256: str


class ValuationPlatesResponse(ApiModel):
    """As folhas acrescentadas e o tamanho da praça depois do ato.

    `plate_count` e `plate_limit` viajam juntos porque é a distância entre os dois que diz à
    tela quantas folhas ainda cabem — e cada folha que cabe é uma extração paga a mais.
    """

    round_id: UUID
    version: int
    plate_count: int
    plate_limit: int
    appended: list[ValuationPlateSummary]


class ValuationPlateResponse(ApiModel):
    """Metadados da prancha; a imagem sai por URL assinada e nunca pelo request path (D5)."""

    round_id: UUID
    version: int
    upload_id: UUID
    source_sha256: str
    page_count: int | None = None
    image_url: str | None = None


class TakeoffItemAddressRequest(ApiModel):
    """Endereço de um item que atravessa a praça: o par `(plate_id, item_id)`.

    `item_id` só é único DENTRO do pacote de uma folha; sem a `plate_id` junto, duas folhas
    que cunharam o mesmo id seriam indistinguíveis (ADR-0057, decisão 5).
    """

    plate_id: str = Field(min_length=1, max_length=64)
    item_id: str = Field(min_length=1, max_length=32)


class DeclareIdentityLinkRequest(ApiModel):
    """Ato humano: duas leituras de folhas diferentes são o MESMO elemento físico.

    O corpo declara O QUE é o mesmo elemento e QUAL das duas leituras governa a quantidade
    (`kept`, "a parcela que fica"). Autor e instante NÃO viajam aqui: vêm do JWT e do relógio
    do servidor, como em toda decisão desta cadeia — um corpo que carimbasse quem declarou
    deixaria o cliente escolher a procedência do próprio ato.

    A nota é obrigatória porque o vínculo muda o total da praça: quem confere depois precisa
    ler por que duas leituras viraram uma.
    """

    base_version: int = Field(ge=1)
    kept: TakeoffItemAddressRequest
    discarded: TakeoffItemAddressRequest
    note: str = Field(min_length=1, max_length=300)


class PreviewIdentityLinkRequest(ApiModel):
    """O vínculo que a orçamentista está considerando, para ver o efeito ANTES de declarar.

    Espelho de `DeclareIdentityLinkRequest` sem o que só o ato tem: sem `base_version` — nada
    é gravado e a versão da rodada não anda, como no `GET` da shortlist e na pré-visualização
    do acervo de canteiro — e sem `note`, porque a justificativa é do ato, não da simulação.

    É `POST`, e não `GET`, pelo mesmo motivo da pré-visualização do acervo: o endereço das
    duas leituras viaja no corpo, e pô-lo em query string publicaria identificadores de
    conteúdo da prancha do cliente na URL, que é o que os logs de infraestrutura registram.
    """

    kept: TakeoffItemAddressRequest
    discarded: TakeoffItemAddressRequest


class CreatePlateExtractionRequest(ApiModel):
    base_version: int = Field(ge=1)


class CreatePlatesExtractionRequest(ApiModel):
    """Ato em lote: quais folhas da praça vão para a extração paga (F-046 T4).

    `plate_ids` é exigido e nada vem marcado por padrão, pelo mesmo motivo da promoção: cada
    folha é uma chamada paga, e o número delas é escolha declarada de quem paga.
    """

    base_version: int = Field(ge=1)
    plate_ids: list[Annotated[str, Field(min_length=1, max_length=64)]] = Field(
        min_length=1, max_length=WORKSITE_PLATE_LIMIT
    )


class ValuationExtractionResponse(ApiModel):
    round_id: UUID
    version: int
    extraction_id: UUID
    status: str


class ValuationPlatesExtractionResponse(ApiModel):
    """O lote aceito, com o número de folhas que serão extraídas declarado na resposta.

    `plate_count` existe para ser lido ANTES de a primeira chamada paga acontecer: o comando
    só sai enfileirado, o worker é quem paga, e esta é a última fronteira em que o número de
    extrações autorizadas pode ser confirmado por quem as autorizou.
    """

    round_id: UUID
    version: int
    extraction_id: UUID
    status: str
    plate_count: int
    plate_ids: list[str]


class ValuationTakeoffOverlayResponse(ApiModel):
    """Overlay das âncoras: URL assinada, digest do desenho e a idade dele (ADR-0030).

    `packet_sha256` é o pacote CORRENTE da rodada e `overlay_packet_sha256` é o pacote que
    originou o desenho; `stale` é a comparação dos dois, feita na leitura. Os três viajam
    juntos porque a marca sozinha não diz ao cliente o que mudou nem quando ele já pode
    parar de esperar pelo re-render.
    """

    round_id: UUID
    version: int
    image_url: str
    image_sha256: str | None = None
    packet_sha256: str
    overlay_packet_sha256: str | None = None
    stale: bool


class TakeoffItemDecision(ApiModel):
    """Uma decisão do orçamentista sobre um item do takeoff, dentro do lote.

    `quantity` viaja como TEXTO porque quantidade é `Decimal` exato neste contexto: um
    `float` de JSON já teria perdido a escala escrita na legenda antes de chegar aqui.

    O carimbo de identidade não entra por aqui — `reviewer_id`, `reviewer_role`,
    `decided_at` e `decision_id` são recusados pelo `extra="forbid"` do `ApiModel`, não por
    lista negra: a identidade vem do `Principal` e o instante, do servidor.

    O padrão de `item_id` repete o do domínio (`TakeoffDecisionInput`) de propósito: ele é
    o que faz um id malformado ser `422` de contrato na fronteira, em vez de estourar o
    validador do domínio no meio da rota.
    """

    item_id: str = Field(pattern=r"^ti_[a-f0-9]{16}$")
    action: Literal["confirm", "reject"]
    quantity: str | None = Field(default=None, min_length=1, max_length=40)
    unit: str | None = Field(default=None, min_length=1, max_length=20)
    note: str | None = Field(default=None, max_length=500)
    item_note: str | None = Field(default=None, max_length=300)


class TakeoffDecisionRequest(ApiModel):
    """O ato de revisão do takeoff é um LOTE, e só um lote.

    A revisão da legenda é lida item a item mas decidida de uma vez: quem confere quinze
    linhas contra a prancha termina com quinze decisões que valem juntas ou não valem. A
    forma singular anterior transformava esse ato único em quinze atos — quinze revisões
    na cadeia, quinze `base_version` em série (cada uma invalidando o formulário aberto),
    quinze overlays reenfileirados para um desenho que só interessa no fim. A rodada real
    do Guaxindiba acumulou 44 revisões para uma legenda de 15 itens; é esse rastro que a
    forma de lote não produz.

    O lote é ATÔMICO: uma revisão nova com todas as decisões, ou nenhuma. Aplicar metade
    deixaria a cadeia num estado que o revisor não pediu e não viu.

    Um item por lote — `TAKEOFF_DECISION_DUPLICATE_ITEM` é invariante do domínio
    (`TakeoffDecisionBatch`), não checagem desta fronteira: duas decisões para o mesmo item
    no mesmo ato não têm ordem definida, e escolher uma delas seria inventar a intenção.
    """

    base_version: int = Field(ge=1)
    #: A folha da praça que este lote revisa. **Opcional**, e a ausência é a primeira folha —
    #: o comportamento de sempre (F-046 T4c). Um lote é a legenda de UMA prancha por
    #: construção, então a folha entra no corpo do ato e não em cada decisão: decidir itens de
    #: duas folhas no mesmo lote seria outro ato, sobre outro pacote, com outra revisão.
    plate_id: str | None = Field(default=None, min_length=1, max_length=64)
    #: Teto de tamanho porque um lote é a legenda de uma prancha, não uma importação: o
    #: maior pacote real observado tem dezenas de itens, e um corpo de milhares seria
    #: outro caso de uso, com outro desenho.
    decisions: list[TakeoffItemDecision] = Field(min_length=1, max_length=200)


class RecomputeSuggestionsRequest(ApiModel):
    """Recompute explícito da shortlist de código: o corpo é só a guarda de concorrência.

    O recompute é ATO humano — ele descarta a shortlist anterior e a substitui pelo
    algoritmo corrente —, e por isso exige `base_version` e avança a versão da rodada. A
    leitura que calcula a shortlist pela primeira vez não é ato nenhum e não pede corpo.
    """

    base_version: int = Field(ge=1)


class ItemPackageClosureRequest(ApiModel):
    """Declaração de que o pacote de serviços de um elemento está completo.

    Serve às duas jornadas: fechar não cita fonte de preço nem código, então a diferença
    que obrigou `EstimateCodeAssignmentDecisionRequest` a existir não aparece aqui.

    A `note` é opcional de propósito. Fechar é o curso normal do trabalho — ao contrário da
    rejeição, que tira o item do boletim e por isso exige justificativa nesta API.
    """

    base_version: int = Field(ge=1)
    item_id: str = Field(pattern=r"^ti_[a-f0-9]{16}$")
    note: str | None = Field(default=None, min_length=1, max_length=500)


class CodeAssignmentRevocationRequest(ApiModel):
    """Retirada de um par `(elemento, código)` já confirmado (F-045).

    Serve às duas jornadas: desfazer não cita fonte de preço — a fonte é a que o par
    confirmado já carrega, e pedi-la de novo deixaria o cliente afirmar algo que o servidor
    sabe melhor.

    A `note` é **obrigatória**, ao contrário da do fechamento. Fechar é o curso normal do
    trabalho; desfazer é o ato que alguém vai auditar depois, e a frase escrita é o que
    separa o conserto do descuido.
    """

    base_version: int = Field(ge=1)
    item_id: str = Field(pattern=r"^ti_[a-f0-9]{16}$")
    code: str = Field(min_length=1, max_length=30)
    note: str = Field(min_length=1, max_length=500)


class CodeAssignmentDecisionRequest(ApiModel):
    """Uma decisão do orçamentista sobre o código SCO de um item confirmado no takeoff.

    O carimbo de identidade não entra por aqui — `reviewer_id`, `reviewer_role`,
    `decided_at` e `decision_id` são recusados pelo `extra="forbid"` do `ApiModel`: a
    identidade vem do `Principal` e o instante, do servidor.

    Duas regras são de CONTRATO e ficam aqui; nenhuma outra é. O `pattern` de `item_id`
    repete o do domínio para que um id malformado seja `422` de fronteira em vez de estourar
    no meio da rota, e a justificativa obrigatória na rejeição é exigência desta API (o
    domínio aceita nota vazia): rejeitar um código sem dizer por quê deixaria o item fora do
    boletim e fora do dossiê do aditivo sem nenhum motivo registrado. Código no catálogo,
    unidade compatível, item já decidido e item não confirmado no takeoff continuam sendo
    recusa do domínio, que esta rota não reimplementa.
    """

    base_version: int = Field(ge=1)
    #: A folha da praça em que este item foi lido. **Opcional**, e a ausência é a primeira
    #: folha — o comportamento de sempre (F-046 T4d). Ela entra no corpo, e não no `item_id`,
    #: porque `item_id` só é único DENTRO do pacote de uma folha (ADR-0057, decisão 5): sem a
    #: folha junto, duas pranchas que cunharam o mesmo id seriam indistinguíveis.
    plate_id: str | None = Field(default=None, min_length=1, max_length=64)
    item_id: str = Field(pattern=r"^ti_[a-f0-9]{16}$")
    action: Literal["confirm", "reject"]
    code: str | None = Field(default=None, min_length=1, max_length=30)
    note: str | None = Field(default=None, min_length=1, max_length=500)

    @model_validator(mode="after")
    def validate_rejection_note(self) -> CodeAssignmentDecisionRequest:
        if self.action == "reject" and self.note is None:
            # Mensagem fixa: nada do corpo recusado volta ao cliente pelo erro de contrato.
            raise ValueError("rejeição de código exige justificativa em `note`")
        return self


class ValuationItemPackageClosureRequest(ItemPackageClosureRequest):
    """Fechamento de pacote na medição, que desde a F-046 acontece POR FOLHA da praça.

    Modelo próprio, e não um campo a mais no compartilhado: `ItemPackageClosureRequest` serve
    às duas jornadas, e o orçamento-base não tem praça nenhuma. Acrescentar `plate_id` lá
    deixaria a rota do orçamento aceitar um campo que ela ignora em silêncio — que é
    exatamente o tipo de contrato que o `extra="forbid"` desta API existe para não ter.
    """

    #: A folha da praça cujo pacote este ato declara completo. **Opcional**, e a ausência é a
    #: primeira folha — o comportamento de sempre (F-046 T4d).
    plate_id: str | None = Field(default=None, min_length=1, max_length=64)


class ValuationCodeAssignmentRevocationRequest(CodeAssignmentRevocationRequest):
    """Retirada de um par `(elemento, código)` na medição, por folha da praça (F-046 T4d).

    Existe pelo mesmo motivo de `ValuationItemPackageClosureRequest`: a revogação é ato das
    duas jornadas, e só uma delas tem folhas.
    """

    #: A folha da praça em que o par foi confirmado. **Opcional**, e a ausência é a primeira
    #: folha — o comportamento de sempre.
    plate_id: str | None = Field(default=None, min_length=1, max_length=64)


class BuildValuationCalcRequest(ApiModel):
    """Construção do boletim e da memória de cálculo: o corpo é só a guarda de concorrência.

    A identidade da obra NÃO entra por aqui. No servidor de medição (`POST /calc/build`),
    `worksite_key`, `worksite_name`, `period_number`, `reference_label`, `address` e
    `contract_label` viajavam no payload; em `/v1` eles são atributos da RODADA (decisão
    humana de 2026-08-17, colunas de `ValuationRoundRecord`) e é de lá que o cálculo os lê.
    Aceitá-los aqui deixaria o cliente reescrever a identidade da obra no meio da cadeia —
    quem recusa é o `extra="forbid"` do `ApiModel`, não uma lista negra.

    `base_version` é MUDANÇA pretendida desta migração (F-003, achado 7): `/calc/build` não
    tem guarda de concorrência nenhuma e sempre reconstrói do estado corrente dos dois
    artefatos de origem. Em `/v1` a construção é ato humano da cadeia — ela avança a versão
    da rodada e pode devolver `409 REVISION_CONFLICT`.

    `calc_matrix` é a matriz elemento x serviço (ADR-0053, F-038 T8), opcional: quando vem, o
    boletim funde por código e resolve dependência; sem ela, o regime legado (código único
    por item) segue byte-idêntico. Ela chega como objeto cru e é validada como `CalcMatrix` no
    corpo da rota — invariante do domínio (ciclo, código duplicado) volta como
    `422 DOMAIN_VALIDATION_FAILED`, não como erro de esquema. É persistida na revisão nova
    (`calc_matrix_json`) para auditoria antes de alimentar o builder.
    """

    base_version: int = Field(ge=1)
    calc_matrix: dict[str, Any] | None = Field(default=None)


class BuildAmendmentDossierRequest(ApiModel):
    """Construção do dossiê do aditivo: espelho de `BuildValuationCalcRequest`.

    O dossiê nasce dos MESMOS dois artefatos-base do boletim (pacote de takeoff e conjunto
    de códigos) e não recebe nada além da guarda de concorrência: ele não precifica por
    construção (ADR-0027) e não tem rótulo próprio a receber.

    Como no boletim, `base_version` é mudança pretendida: `/dossier/build` reconstrói sem
    guarda, e em `/v1` a reconstrução é ato humano que avança a versão da rodada.
    """

    base_version: int = Field(ge=1)


class ApproveValuationRequest(ApiModel):
    """Aprovação nominal da medição: o corpo é SÓ a guarda de concorrência (F-028).

    Nenhum campo de identidade existe aqui, e a ausência é o desenho. `reviewer_id`,
    `reviewer_role`, `decided_at` e `decision_id` são carimbo do servidor — o nome que a
    medição publica é o do subject do JWT, e um campo de "nome do aprovador" no corpo faria
    do ato nominal um campo de texto. Quem recusa qualquer um deles é o `extra="forbid"` do
    `ApiModel`, não uma lista negra.

    A observação (`note` do `ReviewerDecision`) também não entra: o que ela significaria numa
    aprovação — ressalva? condição? — é decisão de produto que ninguém tomou, e um campo
    livre gravado junto de um ato nominal pareceria ter efeito jurídico sem tê-lo.
    """

    base_version: int = Field(ge=1)


class ExportBulletinRequest(ApiModel):
    """Exportação do boletim: espelho de `ApproveValuationRequest`.

    Não há nada a escolher na exportação — nem formato, nem layout, nem "exportar assim
    mesmo". A medição publicada é a da cabeça da rodada, o layout é o da prefeitura
    (`default_template()`) e a aprovação válida é precondição, não opção.
    """

    base_version: int = Field(ge=1)


SHA256_HEX_PATTERN: Final = r"^[a-f0-9]{64}$"


class CreateEstimateRoundRequest(ApiModel):
    """Rodada de orçamento-base nova: a obra e o rótulo, nada mais.

    Três diferenças de `CreateValuationRoundRequest` dão nome à fronteira do ADR-0027.
    Não há `catalog_upload_id`: a rodada abre SEM fonte e as fontes entram depois, uma a
    uma, em ordem declarada (`POST .../catalogs`) — instalar uma só na criação faria a
    primeira fonte parecer privilegiada. Não há `period_number` nem `contract_label`:
    período é da medição e contrato é da obra licitada, e antes da licitação não existe
    nenhum dos dois.

    `worksite_key` repete `WORKSITE_KEY_PATTERN`, que o domínio exige do `Estimate`, pelo
    mesmo motivo da medição: a chave é imutável na rodada, e aceitá-la livre aqui faria uma
    rodada nascer válida e só quebrar na montagem, dezenas de decisões depois.

    `target_amount`/`target_label` são o teto de verba (ADR-0040), OPCIONAIS: a tela de
    abertura da rodada é onde ele nasce, mas uma rodada sem verba prevista continua se
    abrindo exatamente como antes desta feature. `target_amount` viaja como TEXTO pelo
    mesmo motivo do BDI — é `Decimal` exato, e um número de JSON já teria passado por
    binário antes de chegar aqui.

    `pricing_regime` é o regime de preço da rodada (ADR-0045), OPCIONAL e declarável
    também depois (`POST .../regime`). Omitir é a pré-licitação de sempre, com cascata
    livre. `pre_bid` é aceito pelo schema só para ser recusado com código estável: ele
    nunca é gravado, porque a ausência já é ele e porque o regime é mão única.
    """

    worksite_key: str = Field(pattern=WORKSITE_KEY_PATTERN)
    worksite_name: str = Field(min_length=1, max_length=120)
    reference_label: str = Field(min_length=1, max_length=120)
    address: str | None = Field(default=None, min_length=1, max_length=200)
    target_amount: str | None = Field(default=None, min_length=1, max_length=32)
    target_label: str | None = Field(default=None, min_length=1, max_length=120)
    pricing_regime: Literal["pre_bid", "contracted_demand"] | None = None


class EstimateRoundResponse(ApiModel):
    round_id: UUID
    version: int
    status: str
    created_at: datetime


class EstimateRoundSummary(ApiModel):
    """Linha da listagem. `cascade_origins` sai na ORDEM da cascata, que é a precedência.

    `target_amount`/`target_label` são os dois textos CRUS da raiz da rodada (ADR-0040),
    sem `consumed`/`remaining`/`over`: a listagem não busca a cabeça de cada rodada, e
    aquele bloco só pode ser derivado contra o `total_amount` de um `estimate_json` que
    vive na revisão, não na raiz. Rodada sem teto devolve os dois `None`.
    """

    round_id: UUID
    worksite_key: str
    worksite_name: str
    reference_label: str
    version: int
    status: str
    stage: str
    extraction_status: str
    cascade_origins: list[str]
    target_amount: str | None = None
    target_label: str | None = None
    pricing_regime: Literal["pre_bid", "contracted_demand"] | None = None
    created_at: datetime
    updated_at: datetime


class EstimateRoundPage(ApiModel):
    items: list[EstimateRoundSummary]
    next_cursor: str | None = None


class InstallEstimateCatalogRequest(ApiModel):
    """Instala UMA fonte de preço no fim da cascata, por um de DOIS caminhos.

    `reference_catalog_id` cita uma tabela do acervo da plataforma — a orçamentista
    escolhe de uma lista e nenhum arquivo sobe. `upload_id` é a tabela PRÓPRIA do cliente,
    subida pelo presign de sempre: a EMOP que ele licenciou, o catálogo de um contrato
    específico. Os dois produzem a mesma entrada de cascata; o que muda é quem publicou o
    arquivo, e isso fica gravado (ADR-0047 decisão 7).

    Os dois são opcionais no contrato e **exatamente um** é obrigatório no ato: o corpo com
    ambos, ou com nenhum, recusa `422 ESTIMATE_CATALOG_SOURCE_INVALID`. Deixá-los mutuamente
    exclusivos por tipo não é expressável aqui sem partir a rota em duas, e duas rotas para
    instalar a mesma coisa dobrariam as regras da cascata.
    """

    upload_id: UUID | None = None
    reference_catalog_id: UUID | None = None
    base_version: int = Field(ge=1)


class ReorderEstimateCascadeRequest(ApiModel):
    """Reordena a cascata. O corpo é a lista COMPLETA dos digests, na ordem nova.

    Completa, e não um "mova esta fonte para a posição N", porque a ordem inteira é a regra
    de precificação: um corpo parcial obrigaria o servidor a decidir onde as fontes
    omitidas entram, e essa decisão é exatamente a que o ADR-0027 tira do código.
    """

    base_version: int = Field(ge=1)
    cascade: list[str] = Field(min_length=1, max_length=8)

    @field_validator("cascade")
    @classmethod
    def validate_digests(cls, value: list[str]) -> list[str]:
        if any(re.fullmatch(SHA256_HEX_PATTERN, digest) is None for digest in value):
            # Mensagem fixa: nada do corpo recusado volta ao cliente pelo erro de contrato.
            raise ValueError("cada item da cascata é o sha256 hexadecimal de uma fonte")
        return value


class RemoveEstimateCascadeSourceRequest(ApiModel):
    """Remove uma fonte da cascata instalada, citada pelo `source_sha256` dela.

    Espelho de `ReorderEstimateCascadeRequest`: um único digest, e não posição nem origem,
    pelo mesmo motivo que a reordenação cita digest — é o identificador estável da fonte,
    o mesmo que a confirmação de código cita.
    """

    base_version: int = Field(ge=1)
    source_sha256: str = Field(pattern=SHA256_HEX_PATTERN)


class EstimateCascadeResponse(ApiModel):
    """A cascata como a tela a lê. `object_key` e `upload_id` não saem daqui."""

    round_id: UUID
    version: int
    cascade: list[dict[str, Any]]


class EstimateReferenceCatalogOption(ApiModel):
    """Uma tabela do acervo como a ESCOLHA da rodada a oferece.

    É deliberadamente mais pobre que `ReferenceCatalogResponse`: `published_by` é a
    identidade do operador da plataforma, de outro tenant, e quem escolhe uma tabela não
    tem por que saber quem a publicou. O que sai é o que distingue duas linhas na lista —
    nome, origem, data-base e tamanho — mais o digest da fonte, que é a identidade que a
    cascata e a decisão de código já citam.
    """

    reference_catalog_id: UUID
    display_name: str
    origin: str
    reference_month: str
    entry_count: int
    source_sha256: str


class EstimateReferenceCatalogListResponse(ApiModel):
    """O que esta rodada pode instalar do acervo, já filtrado pelo servidor."""

    round_id: UUID
    catalogs: list[EstimateReferenceCatalogOption]


class EstimateSiteSetupKitParameter(ApiModel):
    """Um parâmetro de obra que o acervo cita, como a tela pede o campo.

    `unit` é a unidade do PRIMEIRO operando que cita o parâmetro, e `null` quando os operandos
    discordam entre si — escolher um faria o campo ser rotulado com uma unidade que metade das
    parcelas desmente. `cited_by` é quantas PARCELAS citam o parâmetro, que é o que a tela
    mostra ("citado por 6 parcelas") para que declarar um número tenha consequência visível.
    """

    name: str
    unit: str | None = None
    cited_by: int


class EstimateSiteSetupKitOption(ApiModel):
    """Um acervo como a ESCOLHA da rodada o oferece (F-042, ADR-0060).

    Mais pobre que `SiteSetupKitResponse` pelo mesmo motivo de `EstimateReferenceCatalogOption`:
    `created_by` de um acervo de plataforma é a identidade de um operador de outro tenant, e
    quem escolhe um acervo não tem por que saber quem o publicou.
    """

    kit_id: UUID
    name: str
    kit_version: str
    origin: Literal["platform", "tenant"]
    source_label: str
    parcel_count: int
    parameters: list[EstimateSiteSetupKitParameter]
    created_at: datetime


class EstimateSiteSetupKitListResponse(ApiModel):
    """O que ESTA rodada pode aplicar: acervo de plataforma em circulação mais o do tenant."""

    round_id: UUID
    version: int
    kits: list[EstimateSiteSetupKitOption]


class SiteSetupPreviewRequest(ApiModel):
    """Pré-visualização da aplicação do acervo: leitura, e por isso sem guarda de escrita.

    Não tem `base_version` nem aceita `Idempotency-Key` de propósito — ela não grava nada e não
    avança a versão da rodada, como o `GET` da shortlist (ADR-0054 D7). Pedir uma guarda de
    concorrência a um ato que não escreve faria a tela ter de recarregar para conferir uma
    conta.
    """

    kit_id: UUID
    parameters: dict[SiteSetupParameterName, SiteSetupParameterValue] = Field(default_factory=dict)
    excluded_parcel_ids: list[SiteSetupParcelId] = Field(default_factory=list)


class ApplySiteSetupKitRequest(ApiModel):
    """Aplicação do acervo na matriz: ato humano, com guarda de concorrência.

    Mesmo corpo da pré-visualização mais `base_version`, e a diferença é exatamente essa: aqui
    a matriz muda, a revisão nova nasce e o contador da rodada anda.
    """

    base_version: int = Field(ge=1)
    kit_id: UUID
    parameters: dict[SiteSetupParameterName, SiteSetupParameterValue] = Field(default_factory=dict)
    excluded_parcel_ids: list[SiteSetupParcelId] = Field(default_factory=list)


class AuthorSiteSetupKitRequest(ApiModel):
    """Autoria de acervo DO TENANT a partir das parcelas `STANDALONE` da rodada corrente.

    `parameter_bindings` mapeia `"<índice da parcela standalone>.<nome do operando>"` para o
    nome do parâmetro de obra, e é ele que diz QUAIS operandos viram parâmetro — todo operando
    não citado vira constante. O sistema **não** infere: `1 x 2` pode ser "uma unidade por dois
    meses de obra" ou "duas placas de um metro", e adivinhar produziria um acervo que nasce
    errado e só é descoberto na praça seguinte.

    O índice é a posição da parcela na lista de contribuições `STANDALONE` da matriz da revisão
    corrente, percorrida na ordem dos serviços e, dentro de cada serviço, na ordem gravada.
    """

    base_version: int = Field(ge=1)
    name: str = Field(min_length=3, max_length=200)
    kit_version: str = Field(min_length=1, max_length=40)
    parameter_bindings: dict[
        Annotated[str, Field(min_length=3, max_length=80)], SiteSetupParameterName
    ] = Field(default_factory=dict)


class EstimateCodeAssignmentDecisionRequest(ApiModel):
    """Decisão de código do orçamento-base: a confirmação CITA a fonte de preço.

    É a única diferença de contrato para `CodeAssignmentDecisionRequest` da medição, e é a
    razão de este modelo existir: com mais de uma tabela na rodada, resolver o código pela
    ordem da cascata seria a máquina escolhendo quem precifica o item. A citação é
    obrigatória na confirmação e proibida na rejeição — rejeitar é recusar TODAS as fontes,
    não uma delas.

    `codes` é o aceite do PACOTE (F-044): o precedente é do rótulo, e o rótulo dispara um
    conjunto de códigos, então aceitá-lo é um ato só e vira **uma revisão só**. Ele é
    mutuamente exclusivo com `code` — dois campos dizendo o que gravar deixariam o
    significado do corpo depender de qual o servidor lê primeiro —, vale só na confirmação,
    e todos os códigos citam a MESMA fonte, que é a que `catalog_sha256` declara.

    Aceitar o pacote **não o fecha**: o fechamento continua sendo o ato separado de
    `/closures` (ADR-0053, decisão 2; decisão 5 do pacote de design da F-044).
    """

    base_version: int = Field(ge=1)
    item_id: str = Field(pattern=r"^ti_[a-f0-9]{16}$")
    action: Literal["confirm", "reject"]
    code: str | None = Field(default=None, min_length=1, max_length=30)
    #: 50 é teto de corpo, não regra de domínio: o maior pacote real observado tem seis
    #: serviços por elemento, e um lote de dezenas já não é o aceite de um precedente.
    #: Lista vazia NÃO é recusada aqui — quem recusa lote sem decisão nenhuma é o domínio
    #: (`ASSIGNMENT_BATCH_EMPTY`), e reimplementar a regra na fronteira criaria duas.
    codes: list[Annotated[str, Field(min_length=1, max_length=30)]] | None = Field(
        default=None, max_length=50
    )
    catalog_sha256: str | None = Field(default=None, pattern=SHA256_HEX_PATTERN)
    note: str | None = Field(default=None, min_length=1, max_length=500)

    @model_validator(mode="after")
    def validate_decision(self) -> EstimateCodeAssignmentDecisionRequest:
        if self.action == "reject" and self.note is None:
            # Mensagem fixa: nada do corpo recusado volta ao cliente pelo erro de contrato.
            raise ValueError("rejeição de código exige justificativa em `note`")
        if self.action == "confirm" and self.catalog_sha256 is None:
            raise ValueError("confirmação de código exige a fonte de preço em `catalog_sha256`")
        if self.code is not None and self.codes is not None:
            raise ValueError("informe `code` ou `codes`, nunca os dois")
        if self.action == "confirm" and self.code is None and self.codes is None:
            raise ValueError("confirmação de código exige `code` ou o pacote em `codes`")
        if self.action == "reject" and self.codes is not None:
            raise ValueError("rejeição não aceita pacote de códigos; ela recusa todas as fontes")
        return self


class BuildEstimateRequest(ApiModel):
    """Montagem do orçamento-base: a guarda de concorrência e o BDI do orçamento.

    `bdi_percent` viaja como TEXTO porque é `ExactDecimal` no domínio (ADR-0038, decisão
    2), que recusa `float`: um número de JSON já teria passado por binário antes de chegar
    aqui. É percentual ÚNICO do orçamento inteiro — BDI por linha ou por grupo é decisão
    recusada no ADR, não campo omitido.

    A identidade da obra não entra por aqui: `worksite_key`, `worksite_name` e `address`
    são atributos da rodada, e o `extra="forbid"` do `ApiModel` recusa quem tentar
    reescrevê-los no meio da cadeia.
    """

    base_version: int = Field(ge=1)
    bdi_percent: str | None = Field(default=None, min_length=1, max_length=12)
    """Opcional **só** sob demanda contratada, onde a ausência vale zero (F-036).

    Sob o regime a tabela contratual já embute o BDI, então o único valor lícito é zero — e
    exigir que alguém digite um número que só pode ser zero é fricção sem informação. Fora do
    regime ele continua obrigatório: um orçamento de pré-licitação sem BDI declarado é
    orçamento incompleto, e assumir zero ali seria inventar a decisão mais consequente da
    planilha."""
    calc_matrix: dict[str, Any] | None = Field(default=None)
    """A matriz elemento x serviço (ADR-0053, F-038 T8), opcional e espelho da rota de calc.

    Quando vem, o orçamento funde por código e resolve dependência; sem ela, o regime legado
    (código único por item) segue byte-idêntico. Chega como objeto cru, é validada como
    `CalcMatrix` no corpo da rota — invariante do domínio volta como
    `422 DOMAIN_VALIDATION_FAILED` — e é persistida em `calc_matrix_json` antes do builder."""


class ApproveEstimateRequest(ApiModel):
    """Aprovação nominal do orçamento-base: o corpo é SÓ a guarda de concorrência (F-035).

    Nenhum campo de identidade existe aqui, e a ausência é o desenho. `approver_id`,
    `approver_role`, `decided_at` e `decision_id` são carimbo do servidor — o nome que o
    orçamento publica é o do subject do JWT, e um campo de "nome do aprovador" no corpo
    faria do ato nominal um campo de texto, assinável em nome de outra pessoa. Quem recusa
    qualquer um deles com `422` é o `extra="forbid"` do `ApiModel`, não uma lista negra.

    A observação (`note` do `EstimateApproverDecision`) também não entra, pelo mesmo motivo
    do irmão da medição: o que ela significaria numa aprovação — ressalva? condição? — é
    decisão de produto que ninguém tomou, e um campo livre gravado junto de um ato nominal
    pareceria ter efeito jurídico sem tê-lo.
    """

    base_version: int = Field(ge=1)


class ExportEstimateRequest(ApiModel):
    """Despacho da planilha do orçamento: espelho de `ApproveEstimateRequest`.

    Não há nada a escolher no despacho — nem formato, nem layout, nem "exportar assim
    mesmo". O orçamento publicado é o da cabeça da rodada, o layout é o da prefeitura
    (`default_template()`) e a aprovação válida é precondição, não opção.
    """

    base_version: int = Field(ge=1)


class SetEstimateTargetRequest(ApiModel):
    """Declara ou edita o teto de verba da rodada (ADR-0040): valor exato + rótulo opcional.

    `target_amount` viaja como TEXTO pelo mesmo motivo do BDI — `Decimal` exato, e um
    número de JSON já teria passado por binário. Zero e negativo recusam com
    `422 ESTIMATE_TARGET_INVALID`; "sem teto" é ausência do campo na criação da rodada, e
    esta rota não tem contraparte de remoção — o Design Approval Package não desenha
    apagar um teto já declarado (questão em aberto do pacote), e por isso esta rota só
    declara ou edita.
    """

    base_version: int = Field(ge=1)
    target_amount: str = Field(min_length=1, max_length=32)
    target_label: str | None = Field(default=None, min_length=1, max_length=120)


class SetEstimateRegimeRequest(ApiModel):
    """Declara que a rodada corre sob contrato licitado (ADR-0045): um valor, uma direção.

    O campo aceita `pre_bid` no schema de propósito, apesar de ele nunca poder ser gravado:
    recusar a volta com `409 ESTIMATE_REGIME_IRREVERSIBLE` diz por que ela não acontece,
    enquanto um `422` de schema diria apenas que o valor não existe — e a mão única é
    decisão de produto, não digitação errada. Corrigir um engano de declaração é abrir
    outra rodada.

    Não há campo de rótulo: o regime não descreve QUAL contrato, e um rótulo livre aqui
    daria ao orçamento a aparência de conhecer um contrato que ele não modela (ADR-0045,
    decisão 6).
    """

    base_version: int = Field(ge=1)
    pricing_regime: Literal["pre_bid", "contracted_demand"]


class ValuationDocumentResponse(RootModel[dict[str, Any]]):
    """Resposta de medição cuja FORMA vem do domínio, guardada para o `Idempotency-Key`.

    As contagens do takeoff nascem de `TakeoffItemStatus`, e recopiá-las como campos fixos
    aqui faria a API deixar de mostrar um status novo sem que nenhum teste reclamasse. Este
    envelope existe só para o registro de idempotência poder guardar a resposta inteira;
    a rota continua devolvendo o dicionário do domínio.
    """


#: Papel do técnico de campo: quem coleta é quem sincroniza. Toda mutação de `/v1/surveys`
#: o exige; o escritório LÊ o levantamento com os papéis de revisão que já existem.
FIELD_TECHNICIAN_ROLE: Final = "field_technician"

#: Papéis do escritório que podem ler um levantamento sincronizado. São os mesmos de
#: `_reviewer_role`, e por um motivo: quem revisa cota é quem consulta o que veio do campo.
SURVEY_OFFICE_ROLES: Final[tuple[str, ...]] = ("engineer", "architect", "domain_reviewer")

#: Tipos de mídia que o levantamento assina, e o comando de fila que a confirmação de cada
#: um publica. Um tipo novo aqui é decisão de contrato (e de custo de processamento), não
#: conveniência de rota — mesma disciplina de `UPLOAD_CONTENT_TYPES`.
SURVEY_MEDIA_COMMANDS: Final[Mapping[str, str]] = {
    "image/jpeg": "photo",
    "image/png": "photo",
    "image/webp": "photo",
    "audio/webm": "audio",
    "audio/mp4": "audio",
}

#: O id do levantamento é gerado pelo aparelho, offline, antes de existir rede; o limite
#: apenas casa com a coluna e recusa um id que não caberia nela.
SURVEY_ID_MAX_LENGTH: Final = 36
SURVEY_DEVICE_ID_MAX_LENGTH: Final = 128
SURVEY_OPERATION_ID_MAX_LENGTH: Final = 64
SURVEY_ORDER_REF_MAX_LENGTH: Final = 200

#: Teto de operações por lote. Não é regra de negócio: é a guarda contra um corpo sem
#: limite, e o app divide o outbox em lotes bem menores que isto.
SURVEY_OPERATIONS_BATCH_LIMIT: Final = 2000
FIELD_EVIDENCE_ANALYSIS_MAX_BYTES: Final = 2_000_000


class SubmitSurveyOperationsRequest(ApiModel):
    """Um lote do outbox do aparelho mais o pacote consolidado que ele produz.

    `survey` é validado pelo contrato canônico (`croquito_core.field.SurveyPacket`, T7) e
    não por um espelho escrito à mão aqui: a API não republica a forma do levantamento.
    O que ela guarda em `snapshot_json` é este pacote SEM `operations` — o histórico tem
    tabela própria, e mantê-lo nos dois lugares faria as duas fontes divergirem na
    primeira retransmissão.

    `device_id` viaja no topo, e não só dentro de cada operação, porque a contiguidade de
    `seq` é POR APARELHO: um lote precisa dizer de quem ele é antes de ser conferido.
    """

    device_id: str = Field(min_length=1, max_length=SURVEY_DEVICE_ID_MAX_LENGTH)
    survey: SurveyPacket
    operations: list[SurveyOperation] = Field(
        default_factory=list, max_length=SURVEY_OPERATIONS_BATCH_LIMIT
    )


class SurveyOperationsAckResponse(ApiModel):
    """O reconhecimento que o app usa para limpar o outbox e reavaliar o que falta enviar."""

    survey_id: str
    acked_operation_ids: list[str]
    version: int
    last_seq_by_device: dict[str, int]


class SurveyMediaState(ApiModel):
    """Estado de uma mídia do levantamento. Sem `object_key` e sem URL: a tela precisa
    saber se a foto chegou, não onde ela está guardada."""

    sha256: str
    mime_type: str
    status: str


class SurveyStateResponse(ApiModel):
    """O levantamento como o servidor o conhece — a mesma forma que a tela de conflito lê."""

    survey: SurveyPacket
    version: int
    status: str
    last_seq_by_device: dict[str, int]
    media: list[SurveyMediaState]


class PresignSurveyMediaRequest(ApiModel):
    """Pedido de URL assinada para uma foto ou áudio JÁ referenciado no pacote (prancha 6a).

    `mime_type` é fechado no contrato porque é ele que decide o processamento posterior:
    imagem vai para a análise visual, áudio para a transcrição. Um tipo fora da lista não
    é "mídia desconhecida", é comando que ninguém sabe cumprir.
    """

    sha256: str = Field(pattern=SHA256_HEX_PATTERN)
    mime_type: Literal["image/jpeg", "image/png", "image/webp", "audio/webm", "audio/mp4"]
    byte_size: int = Field(gt=0, le=100_000_000)


class PresignSurveyMediaResponse(ApiModel):
    media_id: UUID
    sha256: str
    object_key: str
    url: str
    headers: dict[str, str]
    expires_at: datetime


class CompleteSurveyRequest(ApiModel):
    """Conclusão do levantamento sob a mesma guarda otimista das revisões de leitura."""

    base_version: int = Field(ge=1)


class CompletedSurveySummary(ApiModel):
    survey_id: str
    name: str
    order_ref: str | None
    version: int
    photo_count: int
    confirmed_measurement_count: int
    completed_at: datetime


class CompletedSurveyPage(ApiModel):
    items: list[CompletedSurveySummary]
    next_cursor: str | None = None


class MutateJobSurveyLinkRequest(ApiModel):
    """Guarda otimista da evidência do job; identidade vem do JWT."""

    base_version: int = Field(ge=1)


class JobSurveyLinkResponse(ApiModel):
    job_id: UUID
    survey_id: str
    linked: bool
    version: int


class FieldEvidenceAnchor(ApiModel):
    kind: Literal["point", "element", "note"]
    ref_id: str


class FieldEvidenceMeasurement(ApiModel):
    source_id: str
    survey_id: str
    value_mm: int
    kind: str
    instrument: str
    from_point_id: str | None
    to_point_id: str | None
    second_from_point_id: str | None
    second_to_point_id: str | None
    element_id: str | None
    created_at: datetime


class FieldEvidenceConfirmedValue(ApiModel):
    confirmation_id: UUID
    source_reading_id: str
    value_mm: int
    kind: str
    raw_text: str
    confirmed_by: str
    confirmed_at: datetime


class FieldEvidencePhoto(ApiModel):
    evidence_id: str
    origin: Literal["survey", "standalone"]
    survey_id: str | None
    sha256: str
    mime_type: str
    anchors: list[FieldEvidenceAnchor]
    anchor_text: str | None
    captured_at: datetime
    url: str
    analysis: dict[str, Any] | None
    classification: dict[str, Any] | None
    reading_status: str
    classification_status: str
    confirmed_values: list[FieldEvidenceConfirmedValue]


class LinkedSurveyEvidence(ApiModel):
    survey_id: str
    name: str
    linked_by: str
    linked_at: datetime
    measurements: list[FieldEvidenceMeasurement]


class FieldEvidenceResponse(ApiModel):
    job_id: UUID
    version: int
    surveys: list[LinkedSurveyEvidence]
    photos: list[FieldEvidencePhoto]


class PresignJobFieldPhotoRequest(ApiModel):
    base_version: int = Field(ge=1)
    sha256: str = Field(pattern=SHA256_HEX_PATTERN)
    mime_type: Literal["image/jpeg", "image/png", "image/webp"]
    byte_size: int = Field(gt=0, le=25_000_000)
    anchor_text: str = Field(min_length=1, max_length=500)


class PresignJobFieldPhotoResponse(ApiModel):
    photo_id: UUID
    version: int
    sha256: str
    url: str
    headers: dict[str, str]
    expires_at: datetime


class _PresignJobFieldPhotoIntent(ApiModel):
    """Parte persistível da resposta; URL assinada é reconstruída a cada replay."""

    photo_id: UUID
    version: int


class ConfirmJobFieldPhotoRequest(ApiModel):
    base_version: int = Field(ge=1)


class JobFieldPhotoStateResponse(ApiModel):
    photo_id: UUID
    status: str
    version: int


class RequestFieldPhotoAnalysisRequest(ApiModel):
    base_version: int = Field(ge=1)


class FieldPhotoAnalysisStateResponse(ApiModel):
    analysis_id: UUID
    task: Literal["reading", "classification"]
    status: str
    version: int


class ConfirmFieldPhotoValueRequest(ApiModel):
    base_version: int = Field(ge=1)
    source_reading_id: str = Field(min_length=1, max_length=128)
    value_mm: int = Field(ge=0, le=1_000_000_000)
    kind: Literal["length", "diagonal", "width", "radius", "level", "drop", "height"]
    raw_text: str = Field(min_length=1, max_length=200)


class ConfirmFieldPhotoValueResponse(ApiModel):
    confirmation: FieldEvidenceConfirmedValue
    version: int


#: O id do levantamento não é `UUID` no caminho de propósito: ele nasce no aparelho e o
#: app já persistiu levantamento com id que não é UUID (dado legado do scaffold da fatia
#: 0). Recusá-lo aqui apagaria trabalho de campo que existe.
SurveyIdPath = Annotated[str, Path(min_length=1, max_length=SURVEY_ID_MAX_LENGTH)]

#: O digest é o identificador da mídia no caminho; a forma é conferida antes de virar chave
#: de objeto, para que nada vindo do cliente componha um `object_key`.
SurveyDigestPath = Annotated[str, Path(pattern=SHA256_HEX_PATTERN)]


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

    def enqueue_valuation_plate_extraction(
        self, *, round_id: str, extraction_id: str, tenant_id: str, plate_id: str | None = None
    ) -> None:
        """Publica a extração paga da legenda; nenhum provider é chamado no request path.

        O envelope não tem `job_id` de propósito: o ADR-0016 proíbe `Job` no vocabulário da
        medição, e é por isso que o despacho do worker roteia por comando ANTES de exigir
        aquele campo.

        `plate_id` diz QUAL folha da praça esta mensagem extrai (F-046). Um comando por folha,
        e não um por lote: é o que faz a folha que falha não derrubar as demais, e é o que dá
        a cada uma o seu claim atômico. Ausente significa a primeira folha — o envelope de
        antes desta feature, que continua válido enquanto estiver em voo na fila.
        """
        if self.queue_url is None:
            return
        body: dict[str, str] = {
            "command": "extract_valuation_plate",
            "round_id": round_id,
            "extraction_id": extraction_id,
            "tenant_id": tenant_id,
        }
        if plate_id is not None:
            body["plate_id"] = plate_id
        self.client.send_message(QueueUrl=self.queue_url, MessageBody=json.dumps(body))

    def enqueue_takeoff_overlay_rerender(
        self, *, round_id: str, tenant_id: str, packet_sha256: str
    ) -> None:
        """Publica o re-render do overlay do takeoff; o desenho nunca sai do request path.

        O digest do pacote viaja no envelope porque é ele que torna o comando seguro de
        repetir: o worker descarta em silêncio um comando cujo pacote já foi superado por
        uma decisão posterior (ADR-0030). Sem `job_id`, como todo comando de medição.
        """
        if self.queue_url is None:
            return
        self.client.send_message(
            QueueUrl=self.queue_url,
            MessageBody=json.dumps(
                {
                    "command": "rerender_takeoff_overlay",
                    "round_id": round_id,
                    "tenant_id": tenant_id,
                    "packet_sha256": packet_sha256,
                }
            ),
        )

    def enqueue_estimate_plate_extraction(
        self, *, round_id: str, extraction_id: str, tenant_id: str
    ) -> None:
        """Publica a extração paga da legenda da rodada de ORÇAMENTO-BASE.

        Comando próprio, e não o da medição com outro `round_id`: os dois lados leem
        tabelas diferentes, e um envelope ambíguo faria o worker procurar uma rodada de
        medição que não existe — ou, pior, encontrar uma de mesmo id em outra tabela.

        Quem consome este comando é o `dispatch` de `local_queue.py` no worker
        (`ESTIMATE_ROUND_CHAIN`, F-020 T6). A rota nunca depende dele para responder: a
        extração paga já é recusada antes daqui quando o ambiente não tem provider
        configurado.
        """
        if self.queue_url is None:
            return
        self.client.send_message(
            QueueUrl=self.queue_url,
            MessageBody=json.dumps(
                {
                    "command": "extract_estimate_plate",
                    "round_id": round_id,
                    "extraction_id": extraction_id,
                    "tenant_id": tenant_id,
                }
            ),
        )

    def enqueue_estimate_takeoff_overlay_rerender(
        self, *, round_id: str, tenant_id: str, packet_sha256: str
    ) -> None:
        """Re-render do overlay da rodada de orçamento; espelho do comando da medição."""
        if self.queue_url is None:
            return
        self.client.send_message(
            QueueUrl=self.queue_url,
            MessageBody=json.dumps(
                {
                    "command": "rerender_estimate_takeoff_overlay",
                    "round_id": round_id,
                    "tenant_id": tenant_id,
                    "packet_sha256": packet_sha256,
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

    def enqueue_survey_photo_analysis(
        self, *, survey_id: str, media_id: str, tenant_id: str
    ) -> None:
        """Publica a análise da foto de campo; nenhum modelo é chamado no request path.

        O envelope carrega o id opaco da linha de mídia, e não o digest nem a chave do
        objeto: quem consome resolve os dois pelo banco, e uma mensagem de fila não
        precisa saber nomear arquivo de cliente. Sem `job_id`, como todo comando que não
        pertence à cadeia do croqui.
        """
        if self.queue_url is None:
            return
        self.client.send_message(
            QueueUrl=self.queue_url,
            MessageBody=json.dumps(
                {
                    "command": "analyze_survey_photo",
                    "survey_id": survey_id,
                    "media_id": media_id,
                    "tenant_id": tenant_id,
                }
            ),
        )

    def enqueue_field_evidence_analysis(
        self, *, analysis_id: str, job_id: str, tenant_id: str
    ) -> None:
        """Publica uma análise pedida pelo revisor; o alvo é resolvido no worker."""
        if self.queue_url is None:
            return
        self.client.send_message(
            QueueUrl=self.queue_url,
            MessageBody=json.dumps(
                {
                    "command": "analyze_field_evidence",
                    "analysis_id": analysis_id,
                    "job_id": job_id,
                    "tenant_id": tenant_id,
                }
            ),
        )

    def enqueue_survey_transcription(
        self, *, survey_id: str, media_id: str, tenant_id: str
    ) -> None:
        """Publica a transcrição do áudio de campo; mesmo envelope da análise de foto."""
        if self.queue_url is None:
            return
        self.client.send_message(
            QueueUrl=self.queue_url,
            MessageBody=json.dumps(
                {
                    "command": "transcribe_survey_audio",
                    "survey_id": survey_id,
                    "media_id": media_id,
                    "tenant_id": tenant_id,
                }
            ),
        )

    def enqueue_survey_export(self, *, survey_id: str, tenant_id: str) -> None:
        """Publica a exportação do levantamento concluído; o pacote nasce fora do request."""
        if self.queue_url is None:
            return
        self.client.send_message(
            QueueUrl=self.queue_url,
            MessageBody=json.dumps(
                {
                    "command": "export_survey",
                    "survey_id": survey_id,
                    "tenant_id": tenant_id,
                }
            ),
        )


#: Os dois transportes publicam os mesmos comandos com o mesmo corpo; a rota não sabe
#: qual está montado.
QueueAdapter = ProcessingQueue | PubSubProcessingQueue

#: Falhas de transporte que a rota traduz em 503 repetível, seja qual for a nuvem.
QUEUE_TRANSPORT_ERRORS = (BotoCoreError, ClientError, QueuePublishError)


def _problem(
    code: str,
    http_status: int,
    detail: str,
    details: Mapping[str, object] | None = None,
) -> HTTPException:
    """Erro com código estável; `details` carrega o vocabulário de domínio, quando há um.

    O `details` existe para o `DOMAIN_VALIDATION_FAILED` da medição (ADR-0028 D4): o código
    de invariante de `packages/valuation` viaja DENTRO do erro, porque a API não republica o
    vocabulário do domínio na sua lista de códigos.
    """
    body: dict[str, Any] = {"code": code, "detail": detail}
    if details:
        body["details"] = dict(details)
    return HTTPException(status_code=http_status, detail=body)


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


def _presign_tenant_upload(
    application: FastAPI,
    *,
    principal: Principal,
    filename: str,
    content_type: str,
    size_bytes: int,
    sha256: str,
    storage_flavor: str,
) -> tuple[UploadRecord, PresignUploadResponse]:
    """URL de escrita para UM objeto sob o prefixo do tenant, e o registro que o descreve.

    Vive fora das rotas porque há dois presigns com exatamente esta sequência — o do croqui
    (`POST /v1/uploads/presign`) e o do acervo (`POST /v1/platform/reference-catalogs/presign`,
    F-037 escopo 7). Duas cópias divergiriam no detalhe que ninguém revisa: o header de
    checksum entra na assinatura só no S3, e mandá-lo ao GCS faz o PUT falhar.

    O objeto fica sob `tenants/{tenant_id}/uploads/` nos dois casos, inclusive no do acervo:
    a área de upload é de quem sobe enquanto o arquivo ainda não foi lido, e ele só vira
    objeto da plataforma depois que a publicação confere o digest e o grava sob o prefixo do
    acervo. Assinar direto para lá poria no acervo um arquivo que ninguém validou.

    O que NÃO mora aqui: idempotência, auditoria e `commit`. Cada rota tem operação própria
    e é ela quem decide o que gravou — a chamadora precisa `session.add` do registro
    devolvido.
    """
    upload_id = new_uuid7()
    safe_filename = _safe_filename(filename, content_type)
    object_key = f"tenants/{principal.tenant_id}/uploads/{upload_id}/{safe_filename}"
    expires_at = datetime.now(UTC) + timedelta(minutes=15)
    record = UploadRecord(
        id=str(upload_id),
        tenant_id=principal.tenant_id,
        object_key=object_key,
        filename=safe_filename,
        content_type=content_type,
        size_bytes=size_bytes,
        sha256=sha256.lower(),
    )
    checksum_sha256 = base64.b64encode(bytes.fromhex(sha256)).decode("ascii")
    artifact_store: ArtifactStore = application.state.artifact_store
    url = artifact_store.presign_upload(
        object_key=object_key,
        checksum_sha256=checksum_sha256,
        content_type=content_type,
    )
    headers: dict[str, str] = {"Content-Type": content_type}
    if storage_flavor == "s3":
        # O header entra na assinatura só no S3; enviá-lo ao GCS faria o PUT falhar.
        headers["x-amz-checksum-sha256"] = checksum_sha256
    response = PresignUploadResponse(
        upload_id=upload_id,
        object_key=object_key,
        url=url,
        headers=headers,
        expires_at=expires_at,
    )
    return record, response


def _request_hash(payload: BaseModel, *, exclude: frozenset[str] | None = None) -> str:
    """Impressão digital do COMANDO, para casar replay com a resposta já gravada.

    `exclude` existe para os campos de telemetria (`TELEMETRY_PAYLOAD_FIELDS`): o touch
    time descreve como o comando foi produzido, não o que ele manda fazer. Deixá-lo no
    hash faria um replay legítimo — a mesma `Idempotency-Key` com o cronômetro em outro
    valor — responder `IDEMPOTENCY_KEY_REUSED`, e faria o hash de um envio idêntico
    deixar de bater com o que foi gravado antes de o campo existir.
    """
    encoded = json.dumps(
        payload.model_dump(mode="json", exclude=set(exclude or frozenset())),
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


class _ParameterlessCommand(BaseModel):
    """Comando sem nenhum parâmetro: o ato é inteiramente identificado pela rota.

    Não é modelo de requisição — nenhuma rota o declara, e ele não aparece no OpenAPI. Ele
    existe só para dar a `_request_hash` um valor ESTÁVEL quando a mutação não tem corpo,
    para que o registro de idempotência daquela rota continue detectando reuso de chave pelo
    mesmo caminho de todas as outras.
    """


_PARAMETERLESS_COMMAND: Final = _ParameterlessCommand()


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


def _chain_id(
    *, total_id: str, part_ids: Sequence[str], declared_by: str, declared_at: datetime
) -> str:
    """Id determinístico da cadeia declarada, no mesmo molde dos `rd_…`/`ap_…` do repo.

    Deriva do conteúdo da declaração — quem declarou, quando, e quais leituras —, de modo
    que duas cadeias diferentes nunca colidem e a mesma declaração é sempre nomeada igual.
    """
    canonical = json.dumps(
        {
            "total_id": total_id,
            "part_ids": list(part_ids),
            "declared_by": declared_by,
            "declared_at": declared_at.isoformat(),
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return f"ch_{hashlib.sha256(canonical.encode('utf-8')).hexdigest()[:16]}"


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
    details: Mapping[str, str | int] | None = None,
) -> None:
    """Registra o ato no tenant ALVO, ou no de quem o praticou quando não há alvo.

    `details` existe para o ato de plataforma que não tem tenant alvo: publicar no acervo é
    feito por um operador, para todos, e o `tenant_id` gravado é o DELE — o fato verdadeiro
    é "esta pessoa, deste tenant, publicou" (ADR-0047 decisão 11). Sem o detalhe, a linha de
    auditoria diria o tenant errado sobre o alcance do ato. Só cabe aqui identificador
    opaco e rótulo público: conteúdo de cliente, chave de objeto e URL assinada nunca entram
    em auditoria (ADR-0028 D5).
    """
    session.add(
        AuditRecord(
            id=str(new_uuid7()),
            tenant_id=tenant_id or principal.tenant_id,
            actor_id=principal.subject,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            metadata_json={"request_id": request_id, **(details or {})},
        )
    )


def _optional_interaction_ms(interaction_ms: int | None) -> dict[str, int]:
    """Trecho de payload com o touch time, ou VAZIO quando ninguém mediu.

    O contrato de eventos marca `interaction_ms` como opcional, e opcional ali quer dizer
    ausente: publicar a chave com `null` diria ao consumidor que a medição existe e vale
    nada. Chave ausente é a única forma de dizer "não medido" sem inventar um número.
    """
    return {} if interaction_ms is None else {"interaction_ms": interaction_ms}


def _record_domain_event(
    session: Session,
    *,
    principal: Principal,
    event_type: str,
    payload: Mapping[str, Any],
    job_id: UUID | str | None = None,
) -> None:
    """Grava um evento de domínio na outbox, na MESMA sessão (e transação) do fato.

    Deliberadamente ao lado de `_record_audit` e nunca depois do `commit`: o `session.add`
    daqui entra na mesma unidade de trabalho do registro de negócio, então ou os dois
    commitam ou nenhum. Publicar do request path — direto na fila, depois de responder —
    publicaria fatos de transação abortada e perderia fatos em falha de broker; é o que o
    ADR-0042 rejeitou.

    Emitir só nos atos que o catálogo v1 cobre é regra, e não omissão: `build_domain_event`
    recusa `event_type` fora do catálogo, e um ato auditado sem tipo publicado continua
    auditado em `audit_events`. O payload passa pela conferência de FORMA do
    `croquito_core.events` — nada aninhado atravessa, que é como conteúdo viajaria.
    """
    occurred_at = datetime.now(UTC)
    resolved_job_id = str(job_id) if job_id is not None else None
    envelope = build_domain_event(
        event_type=event_type,
        tenant_id=principal.tenant_id,
        occurred_at=occurred_at,
        payload=payload,
        job_id=resolved_job_id,
    )
    session.add(
        DomainEventRecord(
            id=str(envelope["event_id"]),
            tenant_id=principal.tenant_id,
            event_type=event_type,
            job_id=resolved_job_id,
            occurred_at=occurred_at,
            payload_json=envelope["payload"],
        )
    )


def _record_round_event(
    session: Session,
    *,
    principal: Principal,
    event_type: str,
    action: str,
    record: ValuationRoundRecord | EstimateRoundRecord,
    extra_payload: Mapping[str, Any] | None = None,
) -> None:
    """Espelha em evento a ação já auditada de uma rodada de medição/orçamento.

    O catálogo v1 não granulariza essas ações em tipos próprios de propósito: `action`
    carrega o MESMO código estável que `audit_events` grava, e criar um tipo por ação é
    evolução `.v2+`, guiada pelo consumo real do portal — publicar treze tipos que
    ninguém lê é contrato que envelhece antes de ser usado.

    `version` é o contador ÚNICO da cadeia da rodada (ADR-0028 D3) DEPOIS do ato; é ele
    que dá ao consumidor a ordem causal dentro da rodada, que `occurred_at` sozinho não
    garante.

    `extra_payload` acrescenta grandezas de observabilidade a UMA ação específica sem mudar
    o formato das demais — hoje só o recompute da shortlist o usa, para declarar o gasto do
    braço de embeddings (rodou?, model id, tokens, custo, fontes com índice). São grandezas,
    nunca conteúdo: quem monta o bloco (`SemanticArmTelemetry.event_payload`) já o garante.
    """
    payload: dict[str, Any] = {
        "action": action,
        "round_id": record.id,
        "version": record.version,
    }
    if extra_payload is not None:
        payload.update(extra_payload)
    _record_domain_event(
        session,
        principal=principal,
        event_type=event_type,
        payload=payload,
    )


def _log_suggestions_recompute(
    record: ValuationRoundRecord | EstimateRoundRecord,
    telemetry: SemanticArmTelemetry,
) -> None:
    """Log estruturado do gasto do braço de embeddings no recompute da shortlist.

    É o par do evento de rodada para quem observa a plataforma pelos logs e não pela fila de
    eventos — foi lendo a saída do CLI, por falta deste registro, que o consumo do tenant
    teve de ser medido por fora na rodada de 2026-08-25. O `stage` distingue as duas jornadas
    sem carregar nome de obra, e `round_id` é id opaco; os demais campos são as grandezas que
    `event_payload` já isolou (nenhum conteúdo embutido). Hoje sai `semantic_arm_ran=false`:
    a rodada da API não publica índice, e declarar que a via paga não rodou é o oposto de
    degradar em silêncio.
    """
    stage = (
        "valuation.code-suggestions.recompute"
        if isinstance(record, ValuationRoundRecord)
        else "estimate.code-suggestions.recompute"
    )
    _VALUATION_LOGGER.info(
        "code_suggestions_recomputed",
        extra={"stage": stage, "round_id": record.id, **telemetry.event_payload()},
    )


def _reviewer_role(principal: Principal) -> str:
    """Maps only signed roles to the review contract's professional role vocabulary."""
    for role in CROQUI_REVIEWER_ROLES:
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


def _ai_entitlement_reason(
    session: Session, principal: Principal, *, real_providers_enabled: bool
) -> str | None:
    """O irmão de `_require_active_ai_entitlement` que DEVOLVE o motivo em vez de levantar.

    Mesma pergunta, desfecho oposto, e é essa a decisão 8 do ADR-0054: um `403` no recompute
    faria o tenant sem autorização contratual perder o ato inteiro — inclusive o braço
    léxico, que não chama provider nenhum e não custa nada. Aqui a falta vira nota, a
    shortlist sai léxica e o recompute acontece.

    Os dois convivem de propósito, e não são um o substituto do outro: onde a rota EXISTE
    para praticar a chamada paga (busca híbrida, chat, extração), recusar é o comportamento
    certo — devolver `200` com meio resultado esconderia que o pedido não foi atendido. Onde
    a chamada paga é um ENFEITE de um ato que se completa sem ela, recusar é que seria o
    erro. `_require_active_ai_entitlement` continua sendo o portão dos primeiros.

    Ambiente com providers desligados nem chega a consultar o banco: não há chamada externa
    possível, e o motivo é do operador da plataforma, não do contrato do tenant.
    """
    if not real_providers_enabled:
        return PROVIDERS_DISABLED_REASON
    entitlement = session.scalar(
        select(TenantAiProcessingEntitlementRecord).where(
            TenantAiProcessingEntitlementRecord.tenant_id == principal.tenant_id,
            TenantAiProcessingEntitlementRecord.status == "ACTIVE",
        )
    )
    return None if entitlement is not None else ENTITLEMENT_INACTIVE_REASON


def _require_job_ai_authorization(
    session: Session, *, job: JobRecord, real_providers_enabled: bool
) -> None:
    """O snapshot do job continua obrigatório quando uma foto pode sair da plataforma."""
    if not real_providers_enabled:
        return
    authorization = session.scalar(
        select(AiProcessingAuthorizationRecord.id).where(
            AiProcessingAuthorizationRecord.job_id == job.id,
            AiProcessingAuthorizationRecord.tenant_id == job.tenant_id,
        )
    )
    if authorization is None:
        raise _problem(
            "AI_PROCESSING_NOT_AUTHORIZED",
            status.HTTP_403_FORBIDDEN,
            "O job não possui autorização registrada para processamento externo.",
        )


def _entitled_journeys(
    database: Database, *, tenant_id: str, journeys: Collection[Journey]
) -> frozenset[Journey]:
    """Jornadas em `pilot` que este tenant tem autorizadas, lidas do entitlement (F-034).

    Sem jornada em `pilot` nenhuma sessão é aberta: em ambiente que não declara piloto — o
    padrão — este caminho não toca o banco, e nem o portão das rotas nem `GET /v1/me`
    passam a depender dele para responder.

    A sessão é própria e curta de propósito: o portão roda antes das dependências da rota, e
    `GET /v1/me` não tem sessão. `status == "ACTIVE"` é o mesmo critério do entitlement de
    IA, então revogar (que grava `REVOKED` e `revoked_at`) fecha a jornada pelo mesmo
    caminho de quem nunca teve autorização.
    """
    wanted = frozenset(journeys)
    if not wanted:
        return frozenset()
    with database.sessions() as session:
        granted = session.scalars(
            select(TenantJourneyEntitlementRecord.journey).where(
                TenantJourneyEntitlementRecord.tenant_id == tenant_id,
                TenantJourneyEntitlementRecord.journey.in_(sorted(wanted)),
                TenantJourneyEntitlementRecord.status == "ACTIVE",
            )
        ).all()
    return frozenset(cast(Journey, journey) for journey in granted) & wanted


def _journey_unavailable(journey: Journey) -> HTTPException:
    """Recusa única da jornada indisponível: `disabled` e piloto sem entitlement respondem
    exatamente isto, para que ninguém descubra pela diferença de mensagem que existe um
    piloto do qual não faz parte."""
    return _problem(
        "JOURNEY_UNAVAILABLE",
        status.HTTP_403_FORBIDDEN,
        f"A jornada {journey} não está disponível neste ambiente.",
    )


def _require_valuation_reviewer(principal: Principal) -> str:
    """Papel `orcamentista`, exigido em TODA rota de medição — inclusive de leitura (D8).

    É a primeira coisa que cada rota faz, antes de qualquer lookup: quem não tem o papel não
    descobre, pela diferença entre `403` e `404`, se uma rodada existe.
    """
    if not principal.has_role(VALUATION_REVIEWER_ROLE):
        raise _problem(
            "FORBIDDEN",
            status.HTTP_403_FORBIDDEN,
            f"Papel {VALUATION_REVIEWER_ROLE} é obrigatório nas rotas de medição.",
        )
    return VALUATION_REVIEWER_ROLE


def _require_estimate_approver(principal: Principal) -> None:
    """Papel `aprovador`, exigido só na rota que ASSINA o orçamento (ADR-0046, decisão 5).

    Ele não substitui `orcamentista` em lugar nenhum: a mutação da cadeia e o despacho
    continuam sendo do orçamentista, e este papel abre exatamente um ato. Como em
    `_require_valuation_reviewer`, a checagem vem antes de qualquer lookup — quem não tem o
    papel não descobre, pela diferença entre `403` e `404`, se uma rodada existe.
    """
    if not principal.has_role(ESTIMATE_APPROVER_ROLE):
        raise _problem(
            "FORBIDDEN",
            status.HTTP_403_FORBIDDEN,
            f"Papel {ESTIMATE_APPROVER_ROLE} é obrigatório para aprovar o orçamento.",
        )


def _require_estimate_reader(principal: Principal) -> None:
    """Leitura das rotas do orçamento: quem monta ou quem assina.

    O aprovador precisa ABRIR a jornada para ver o que assina (ADR-0046, decisão 5) — uma
    assinatura dada sobre um orçamento que a pessoa não pôde ler seria carimbo, não ato. Ler
    não é mutar: toda mutação da cadeia segue em `_require_valuation_reviewer`, e é o teste
    irmão de `test_sem_o_papel_toda_rota_recusa_antes_do_lookup` que impede uma delas de
    afrouxar por engano ao ganhar este papel.
    """
    if principal.has_role(VALUATION_REVIEWER_ROLE) or principal.has_role(ESTIMATE_APPROVER_ROLE):
        return
    raise _problem(
        "FORBIDDEN",
        status.HTTP_403_FORBIDDEN,
        f"Papel {VALUATION_REVIEWER_ROLE} ou {ESTIMATE_APPROVER_ROLE} é obrigatório "
        "nas rotas de orçamento.",
    )


def _require_field_technician(principal: Principal) -> None:
    """Papel `field_technician`, exigido em toda MUTAÇÃO de `/v1/surveys`.

    Coletar é ato de quem esteve no local: o escritório lê o levantamento (ver
    `_require_survey_reader`), mas não escreve nele. Como em `_require_valuation_reviewer`,
    a checagem vem antes de qualquer lookup — quem não tem o papel não descobre, pela
    diferença entre `403` e `404`, se um levantamento existe.
    """
    if not principal.has_role(FIELD_TECHNICIAN_ROLE):
        raise _problem(
            "FORBIDDEN",
            status.HTTP_403_FORBIDDEN,
            f"Papel {FIELD_TECHNICIAN_ROLE} é obrigatório para sincronizar levantamento.",
        )


def _require_survey_reader(principal: Principal) -> None:
    """Leitura do levantamento: o técnico que coletou ou o profissional que vai revisar."""
    if principal.has_role(FIELD_TECHNICIAN_ROLE):
        return
    if any(principal.has_role(role) for role in SURVEY_OFFICE_ROLES):
        return
    raise _problem(
        "FORBIDDEN",
        status.HTTP_403_FORBIDDEN,
        "Papel de campo ou de revisão é obrigatório para ler um levantamento.",
    )


def _load_survey(session: Session, *, survey_id: str, tenant_id: str) -> SurveyRecord:
    """O levantamento do tenant, ou `404`. De outro tenant é indistinguível de inexistente."""
    record = session.scalar(
        select(SurveyRecord).where(
            SurveyRecord.id == survey_id, SurveyRecord.tenant_id == tenant_id
        )
    )
    if record is None:
        raise _problem("NOT_FOUND", status.HTTP_404_NOT_FOUND, "Levantamento não encontrado.")
    return record


def _last_seq_by_device(session: Session, *, survey_id: str, tenant_id: str) -> dict[str, int]:
    """O último `seq` gravado por aparelho — a régua da contiguidade e o que o app compara.

    Sai ordenado por `device_id` para que duas respostas iguais sejam iguais também byte a
    byte: esta estrutura entra no registro de idempotência e no detalhe do conflito.
    """
    rows = session.execute(
        select(SurveyOperationRecord.device_id, func.max(SurveyOperationRecord.seq))
        .where(
            SurveyOperationRecord.survey_id == survey_id,
            SurveyOperationRecord.tenant_id == tenant_id,
        )
        .group_by(SurveyOperationRecord.device_id)
    ).all()
    return dict(sorted((str(device_id), int(last_seq)) for device_id, last_seq in rows))


def _survey_media_digests(packet: SurveyPacket) -> set[str]:
    """Todo `sha256` que o pacote consolidado referencia, em qualquer das três âncoras.

    São três porque o pacote tem três lugares onde mídia é citada: a âncora de foto/áudio
    (`media_anchors`), o áudio de uma observação (`observations[].audio_media_ref`) e a
    foto de acesso da chegada (`arrival_context.access_media_ref`, prancha 2). Deixar
    qualquer uma de fora faria a regra da prancha 6a recusar uma mídia legítima.
    """
    digests = {anchor.media_ref.sha256 for anchor in packet.media_anchors}
    digests.update(
        note.audio_media_ref.sha256 for note in packet.observations if note.audio_media_ref
    )
    if packet.arrival_context is not None and packet.arrival_context.access_media_ref is not None:
        digests.add(packet.arrival_context.access_media_ref.sha256)
    return digests


def _survey_media_rows(
    session: Session, *, survey_id: str, tenant_id: str
) -> list[SurveyMediaRecord]:
    return list(
        session.scalars(
            select(SurveyMediaRecord)
            .where(
                SurveyMediaRecord.survey_id == survey_id,
                SurveyMediaRecord.tenant_id == tenant_id,
            )
            .order_by(SurveyMediaRecord.sha256)
        )
    )


def _survey_state(session: Session, record: SurveyRecord) -> SurveyStateResponse:
    """O estado que a leitura, a confirmação de mídia e a conclusão devolvem, sempre igual."""
    return SurveyStateResponse(
        survey=SurveyPacket.model_validate(record.snapshot_json),
        version=record.version,
        status=record.status,
        last_seq_by_device=_last_seq_by_device(
            session, survey_id=record.id, tenant_id=record.tenant_id
        ),
        media=[
            SurveyMediaState(sha256=media.sha256, mime_type=media.mime_type, status=media.status)
            for media in _survey_media_rows(
                session, survey_id=record.id, tenant_id=record.tenant_id
            )
        ],
    )


def _survey_conflict(session: Session, *, record: SurveyRecord, detail: str) -> HTTPException:
    """O `409 SURVEY_CONFLICT` da prancha 6b, com o que a tela precisa para decidir.

    O detalhe carrega o estado do servidor inteiro de propósito: quem resolve o conflito é
    a pessoa, no aparelho, comparando o que ela tem com o que o servidor tem. O servidor
    não escolhe versão vencedora e não apaga nada — a resolução volta como operação normal
    do outbox (`type: "conflict_resolution"`), com justificativa no payload.
    """
    return _problem(
        "SURVEY_CONFLICT",
        status.HTTP_409_CONFLICT,
        detail,
        {
            "server_version": record.version,
            "last_seq_by_device": _last_seq_by_device(
                session, survey_id=record.id, tenant_id=record.tenant_id
            ),
            "server_snapshot": record.snapshot_json,
        },
    )


def _survey_race_conflict(session: Session) -> HTTPException:
    """Corrida de escrita entre dois lotes: a guarda relacional arbitra, e quem perde relê.

    Diferente do conflito de sequência, este não devolve o estado do servidor: a transação
    vencedora pode nem ter commitado ainda, e anexar um estado que já vai mudar seria pior
    do que mandar o app reler.
    """
    session.rollback()
    return _problem(
        "SURVEY_CONFLICT",
        status.HTTP_409_CONFLICT,
        "Uma sincronização concorrente ocupou esta posição da sequência; releia o estado.",
    )


def _validate_survey_batch(survey_id: str, payload: SubmitSurveyOperationsRequest) -> None:
    """Recusa lote incoerente ANTES de tocar o banco; a mensagem nunca ecoa o conteúdo.

    São recusas de forma, não de sequência: pacote de outro levantamento, operação de
    outro levantamento ou de outro aparelho, e identificadores maiores do que as colunas
    que os guardam. Gap e regressão de `seq` são outra coisa — são conflito (`409`), e não
    erro de contrato.
    """
    problems: list[str] = []
    if payload.survey.survey_id != survey_id:
        problems.append("o pacote não é deste levantamento")
    if payload.survey.order_id is not None and (
        len(payload.survey.order_id) > SURVEY_ORDER_REF_MAX_LENGTH
    ):
        problems.append("a ordem de origem excede o tamanho aceito")
    if any(operation.survey_id != survey_id for operation in payload.operations):
        problems.append("há operação de outro levantamento no lote")
    if any(operation.device_id != payload.device_id for operation in payload.operations):
        problems.append("há operação de outro aparelho no lote")
    if any(
        len(operation.operation_id) > SURVEY_OPERATION_ID_MAX_LENGTH
        for operation in payload.operations
    ):
        problems.append("há operação com identificador maior que o aceito")
    if problems:
        raise _problem(
            "SURVEY_PACKET_INVALID",
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "; ".join(problems) + ".",
        )


def _load_job(session: Session, *, job_id: UUID, tenant_id: str) -> JobRecord:
    """Job do tenant, ou `404`; ids alheios nunca revelam existência."""
    record = session.scalar(
        select(JobRecord).where(JobRecord.id == str(job_id), JobRecord.tenant_id == tenant_id)
    )
    if record is None:
        raise _problem("NOT_FOUND", status.HTTP_404_NOT_FOUND, "Job não encontrado.")
    return record


def _read_field_analysis(
    application: FastAPI, *, object_key: str, tenant_id: str
) -> dict[str, Any] | None:
    """Lê artefato pequeno sem aceitar chave fora do prefixo nem expor payload em log."""
    if not object_key.startswith(f"tenants/{tenant_id}/") or ".." in object_key.split("/"):
        return None
    raw = application.state.artifact_store.read_object(
        object_key=object_key, max_bytes=FIELD_EVIDENCE_ANALYSIS_MAX_BYTES
    )
    if raw is None or len(raw) > FIELD_EVIDENCE_ANALYSIS_MAX_BYTES:
        return None
    try:
        document = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    return cast(dict[str, Any], document) if isinstance(document, dict) else None


def _field_anchor_payload(
    packet: SurveyPacket, sha256: str
) -> tuple[list[FieldEvidenceAnchor], datetime | None]:
    anchors: list[FieldEvidenceAnchor] = []
    captured_at: datetime | None = None
    for anchor in packet.media_anchors:
        if anchor.media_ref.sha256 != sha256:
            continue
        captured_at = (
            anchor.created_at if captured_at is None else min(captured_at, anchor.created_at)
        )
        anchor_refs: tuple[tuple[Literal["point", "element", "note"], str | None], ...] = (
            ("point", anchor.point_id),
            ("element", anchor.element_id),
            ("note", anchor.note_id),
        )
        for kind, ref_id in anchor_refs:
            if ref_id is not None:
                anchors.append(FieldEvidenceAnchor(kind=kind, ref_id=ref_id))
    return anchors, captured_at


def _field_analysis_state(
    session: Session,
    *,
    tenant_id: str,
    job_id: str,
    origin: Literal["survey", "standalone"],
    evidence_id: str,
    task: Literal["reading", "classification"],
) -> FieldEvidenceAnalysisRecord | None:
    return session.scalar(
        select(FieldEvidenceAnalysisRecord).where(
            FieldEvidenceAnalysisRecord.tenant_id == tenant_id,
            FieldEvidenceAnalysisRecord.job_id == job_id,
            FieldEvidenceAnalysisRecord.origin == origin,
            FieldEvidenceAnalysisRecord.evidence_id == evidence_id,
            FieldEvidenceAnalysisRecord.task == task,
        )
    )


@dataclass(frozen=True, slots=True)
class _FieldPhotoTarget:
    origin: Literal["survey", "standalone"]
    evidence_id: str
    object_key: str
    sha256: str
    mime_type: str
    byte_size: int


def _load_field_photo_target(
    session: Session,
    *,
    job: JobRecord,
    origin: Literal["survey", "standalone"],
    evidence_id: UUID,
    require_confirmed: bool = True,
) -> _FieldPhotoTarget:
    """Resolve a foto escopada ao job; alvo alheio e inexistente são o mesmo `404`."""
    identifier = str(evidence_id)
    if origin == "standalone":
        photo = session.scalar(
            select(JobFieldPhotoRecord).where(
                JobFieldPhotoRecord.id == identifier,
                JobFieldPhotoRecord.job_id == job.id,
                JobFieldPhotoRecord.tenant_id == job.tenant_id,
            )
        )
        if photo is None or (require_confirmed and photo.status != "CONFIRMED"):
            raise _problem("NOT_FOUND", status.HTTP_404_NOT_FOUND, "Foto de campo não encontrada.")
        return _FieldPhotoTarget(
            origin=origin,
            evidence_id=photo.id,
            object_key=photo.object_key,
            sha256=photo.sha256,
            mime_type=photo.mime_type,
            byte_size=photo.byte_size,
        )

    media_query = select(SurveyMediaRecord).where(
        SurveyMediaRecord.id == identifier,
        SurveyMediaRecord.tenant_id == job.tenant_id,
        SurveyMediaRecord.mime_type.like("image/%"),
    )
    if require_confirmed:
        media_query = media_query.where(SurveyMediaRecord.status == "CONFIRMED")
    media = session.scalar(media_query)
    linked = (
        None
        if media is None
        else session.scalar(
            select(JobSurveyLinkRecord.id).where(
                JobSurveyLinkRecord.job_id == job.id,
                JobSurveyLinkRecord.tenant_id == job.tenant_id,
                JobSurveyLinkRecord.survey_id == media.survey_id,
            )
        )
    )
    if media is None or linked is None:
        raise _problem("NOT_FOUND", status.HTTP_404_NOT_FOUND, "Foto de campo não encontrada.")
    return _FieldPhotoTarget(
        origin=origin,
        evidence_id=media.id,
        object_key=media.object_key,
        sha256=media.sha256,
        mime_type=media.mime_type,
        byte_size=media.byte_size,
    )


def _field_analysis_object_key(*, job: JobRecord, origin: str, evidence_id: str, task: str) -> str:
    return (
        f"tenants/{job.tenant_id}/jobs/{job.id}/field-evidence/analysis/"
        f"{origin}/{evidence_id}/{task}.json"
    )


def _confirmed_field_values(
    session: Session, *, job: JobRecord, origin: str, evidence_id: str
) -> list[FieldEvidenceConfirmedValue]:
    records = session.scalars(
        select(FieldPhotoValueConfirmationRecord)
        .where(
            FieldPhotoValueConfirmationRecord.tenant_id == job.tenant_id,
            FieldPhotoValueConfirmationRecord.job_id == job.id,
            FieldPhotoValueConfirmationRecord.origin == origin,
            FieldPhotoValueConfirmationRecord.evidence_id == evidence_id,
            FieldPhotoValueConfirmationRecord.status == "ACTIVE",
        )
        .order_by(FieldPhotoValueConfirmationRecord.confirmed_at)
    )
    return [
        FieldEvidenceConfirmedValue(
            confirmation_id=UUID(record.id),
            source_reading_id=record.source_reading_id,
            value_mm=record.value_mm,
            kind=record.kind,
            raw_text=record.raw_text,
            confirmed_by=record.confirmed_by,
            confirmed_at=record.confirmed_at,
        )
        for record in records
    ]


def _public_field_analysis(document: dict[str, Any] | None) -> dict[str, Any] | None:
    """Expõe só o resultado profissional; ids internos e tenant ficam no artefato."""
    if document is None:
        return None
    allowed = {
        "quality",
        "provider_pass",
        "provider_failure_code",
        "provider_notes",
        "readings",
        "notes",
        "classification",
        "lineage",
        "schema",
    }
    return {key: value for key, value in document.items() if key in allowed}


def _field_evidence_response(
    application: FastAPI,
    session: Session,
    *,
    job: JobRecord,
) -> FieldEvidenceResponse:
    links = list(
        session.scalars(
            select(JobSurveyLinkRecord)
            .where(
                JobSurveyLinkRecord.job_id == job.id,
                JobSurveyLinkRecord.tenant_id == job.tenant_id,
            )
            .order_by(JobSurveyLinkRecord.linked_at, JobSurveyLinkRecord.survey_id)
        )
    )
    surveys: list[LinkedSurveyEvidence] = []
    photos: list[FieldEvidencePhoto] = []
    store: ArtifactStore = application.state.artifact_store
    for link in links:
        survey = session.scalar(
            select(SurveyRecord).where(
                SurveyRecord.id == link.survey_id,
                SurveyRecord.tenant_id == job.tenant_id,
            )
        )
        if survey is None:  # pragma: no cover - FK composta protege a linha
            continue
        packet = SurveyPacket.model_validate(survey.snapshot_json)
        measurements = [
            FieldEvidenceMeasurement(
                source_id=measurement.id,
                survey_id=survey.id,
                value_mm=measurement.value_mm,
                kind=measurement.kind.value,
                instrument=measurement.instrument,
                from_point_id=measurement.from_point_id,
                to_point_id=measurement.to_point_id,
                second_from_point_id=measurement.second_from_point_id,
                second_to_point_id=measurement.second_to_point_id,
                element_id=measurement.element_id,
                created_at=measurement.created_at,
            )
            for measurement in packet.measurements
            if measurement.status is FieldMeasurementStatus.CONFIRMED
        ]
        surveys.append(
            LinkedSurveyEvidence(
                survey_id=survey.id,
                name=survey.name,
                linked_by=link.linked_by,
                linked_at=link.linked_at,
                measurements=measurements,
            )
        )
        for media in _survey_media_rows(session, survey_id=survey.id, tenant_id=job.tenant_id):
            if media.status != "CONFIRMED" or not media.mime_type.startswith("image/"):
                continue
            url = signed_artifact_url(store, object_key=media.object_key, tenant_id=job.tenant_id)
            if url is None:
                continue
            anchors, captured_at = _field_anchor_payload(packet, media.sha256)
            analysis_key = (
                f"tenants/{job.tenant_id}/surveys/{survey.id}/analysis/{media.sha256}.json"
            )
            reading_state = _field_analysis_state(
                session,
                tenant_id=job.tenant_id,
                job_id=job.id,
                origin="survey",
                evidence_id=media.id,
                task="reading",
            )
            classification_state = _field_analysis_state(
                session,
                tenant_id=job.tenant_id,
                job_id=job.id,
                origin="survey",
                evidence_id=media.id,
                task="classification",
            )
            analysis = _public_field_analysis(
                _read_field_analysis(
                    application,
                    object_key=(
                        reading_state.artifact_key
                        if reading_state is not None and reading_state.artifact_key is not None
                        else analysis_key
                    ),
                    tenant_id=job.tenant_id,
                )
            )
            classification = _public_field_analysis(
                _read_field_analysis(
                    application,
                    object_key=classification_state.artifact_key,
                    tenant_id=job.tenant_id,
                )
                if classification_state is not None
                and classification_state.artifact_key is not None
                else None
            )
            photos.append(
                FieldEvidencePhoto(
                    evidence_id=media.id,
                    origin="survey",
                    survey_id=survey.id,
                    sha256=media.sha256,
                    mime_type=media.mime_type,
                    anchors=anchors,
                    anchor_text=None,
                    captured_at=captured_at or media.created_at,
                    url=url,
                    analysis=analysis,
                    classification=classification,
                    reading_status=(
                        reading_state.status
                        if reading_state is not None
                        else ("PROCESSED" if analysis is not None else "NOT_REQUESTED")
                    ),
                    classification_status=(
                        classification_state.status
                        if classification_state is not None
                        else "NOT_REQUESTED"
                    ),
                    confirmed_values=_confirmed_field_values(
                        session,
                        job=job,
                        origin="survey",
                        evidence_id=media.id,
                    ),
                )
            )

    standalone = list(
        session.scalars(
            select(JobFieldPhotoRecord)
            .where(
                JobFieldPhotoRecord.job_id == job.id,
                JobFieldPhotoRecord.tenant_id == job.tenant_id,
                JobFieldPhotoRecord.status == "CONFIRMED",
            )
            .order_by(JobFieldPhotoRecord.created_at, JobFieldPhotoRecord.id)
        )
    )
    for photo in standalone:
        url = signed_artifact_url(store, object_key=photo.object_key, tenant_id=job.tenant_id)
        if url is None:
            continue
        reading_state = _field_analysis_state(
            session,
            tenant_id=job.tenant_id,
            job_id=job.id,
            origin="standalone",
            evidence_id=photo.id,
            task="reading",
        )
        classification_state = _field_analysis_state(
            session,
            tenant_id=job.tenant_id,
            job_id=job.id,
            origin="standalone",
            evidence_id=photo.id,
            task="classification",
        )
        analysis = _public_field_analysis(
            _read_field_analysis(
                application,
                object_key=reading_state.artifact_key,
                tenant_id=job.tenant_id,
            )
            if reading_state is not None and reading_state.artifact_key is not None
            else None
        )
        classification = _public_field_analysis(
            _read_field_analysis(
                application,
                object_key=classification_state.artifact_key,
                tenant_id=job.tenant_id,
            )
            if classification_state is not None and classification_state.artifact_key is not None
            else None
        )
        photos.append(
            FieldEvidencePhoto(
                evidence_id=photo.id,
                origin="standalone",
                survey_id=None,
                sha256=photo.sha256,
                mime_type=photo.mime_type,
                anchors=[],
                anchor_text=photo.anchor_text,
                captured_at=photo.created_at,
                url=url,
                analysis=analysis,
                classification=classification,
                reading_status=(reading_state.status if reading_state else "NOT_REQUESTED"),
                classification_status=(
                    classification_state.status
                    if classification_state is not None
                    else "NOT_REQUESTED"
                ),
                confirmed_values=_confirmed_field_values(
                    session,
                    job=job,
                    origin="standalone",
                    evidence_id=photo.id,
                ),
            )
        )
    return FieldEvidenceResponse(
        job_id=UUID(job.id), version=job.version, surveys=surveys, photos=photos
    )


def _round_refusal_problem(refusal: RoundRefusal) -> HTTPException:
    """Traduz a precondição da rodada no problem+json de sempre, sem inventar formato."""
    return _problem(refusal.code, refusal.http_status, refusal.detail, refusal.details)


def _valuation_domain_problem(error: ValuationValidationError) -> HTTPException:
    """Invariante de `packages/valuation` como `422 DOMAIN_VALIDATION_FAILED` (ADR-0028 D4).

    `code` é escrito por ÚLTIMO de propósito: os detalhes das invariantes de código de
    catálogo carregam a chave `code` com o código SCO recusado (`ASSIGNMENT_CODE_INVALID`,
    `ASSIGNMENT_CODE_NOT_IN_CATALOG`, `ASSIGNMENT_UNIT_INCOMPATIBLE_WITHOUT_NOTE`), e com a
    ordem invertida era o código do catálogo que saía em `details.code` — o cliente lia
    `"CE04100010(/)"` onde o contrato promete o nome da invariante, e o nome não saía em
    lugar nenhum. Aqui `details.code` significa uma coisa só: a invariante que recusou.
    """
    return _problem(
        "DOMAIN_VALIDATION_FAILED",
        status.HTTP_422_UNPROCESSABLE_ENTITY,
        error.message,
        {**error.details, "code": error.code},
    )


def _valuation_model_problem(error: ValidationError) -> HTTPException:
    """Invariante de domínio embrulhada pelo Pydantic, sem devolver a mensagem do validador.

    `ValuationValidationError` é um `ValueError`, então uma invariante levantada dentro de
    um validador de modelo chega aqui encapsulada — é o caso de confirmar um item
    `ambiguous` sem quantidade, que é caminho real do orçamentista e não erro de programa.
    `valuation_errors` recupera a exceção original para que o código de domínio continue
    saindo em `details`; sem ela, só o código declarado sai, porque a mensagem do Pydantic
    pode ecoar o valor recusado — e valor recusado, aqui, é trecho de prancha de cliente.
    """
    domain = valuation_errors(error)
    if domain:
        return _valuation_domain_problem(domain[0])
    return _problem(
        "DOMAIN_VALIDATION_FAILED",
        status.HTTP_422_UNPROCESSABLE_ENTITY,
        "A decisão não corresponde ao contrato do modelo.",
        {"code": "MODEL_VALIDATION_FAILED"},
    )


def _validate_calc_matrix(raw: Mapping[str, Any] | None) -> CalcMatrix | None:
    """Valida a matriz de contribuições posta no build, ou `None` no regime legado.

    A matriz chega como objeto cru no corpo da rota (não como campo tipado) de propósito: um
    `CalcMatrix` embutido faria o Pydantic recusar durante o PARSING do corpo, e ali a
    invariante do domínio (ciclo, código duplicado) sairia como erro de esquema do FastAPI, e
    não no envelope `application/problem+json` das demais rotas. Validando aqui, a
    `ValuationValidationError` embrulhada volta por `_valuation_model_problem` como
    `422 DOMAIN_VALIDATION_FAILED` com o código estável do domínio — o mesmo caminho das
    decisões de código.
    """
    if raw is None:
        return None
    try:
        return CalcMatrix.model_validate(raw)
    except ValidationError as error:
        raise _valuation_model_problem(error) from error


def _validate_site_setup_kit(raw: Mapping[str, Any]) -> SiteSetupKit:
    """Valida o documento do acervo publicado, com a MESMA disciplina da matriz de cálculo.

    O documento chega como objeto cru no corpo (não como campo tipado) pelo mesmo motivo de
    `_validate_calc_matrix`: um `SiteSetupKit` embutido faria o Pydantic recusar durante o
    PARSING do corpo, e a invariante do domínio (operando que é constante e parâmetro ao mesmo
    tempo, código fora do formato de catálogo, parcela com id repetido) sairia como erro de
    esquema do FastAPI em vez do envelope `application/problem+json` das demais rotas.
    """
    try:
        return SiteSetupKit.model_validate(raw)
    except ValidationError as error:
        raise _valuation_model_problem(error) from error


def _commit_valuation_revision(session: Session) -> None:
    """Fecha a mutação da rodada; corrida na cadeia é conflito de versão, não erro 500.

    A guarda otimista de `base_version` é conferida em MEMÓRIA, antes da gravação: duas
    mutações que leram a mesma versão passam as duas por ela e vão disputar a mesma posição
    da cadeia append-only, onde `uq_valuation_round_version` arbitra. Quem perde recebeu, de
    fato, uma rodada que mudou depois da leitura dele — que é exatamente o que
    `REVISION_CONFLICT` diz. É o mesmo desfecho que as rotas de revisão do croqui já dão à
    corrida equivalente, e não um caso especial da medição.
    """
    try:
        session.commit()
    except IntegrityError as error:
        session.rollback()
        raise _problem(
            "REVISION_CONFLICT",
            status.HTTP_409_CONFLICT,
            "Uma decisão concorrente criou uma revisão mais recente.",
        ) from error


def _load_valuation_round(
    session: Session, *, round_id: UUID, tenant_id: str
) -> ValuationRoundRecord:
    """A rodada do tenant, ou `404`. Rodada de outro tenant é indistinguível de inexistente."""
    record = load_round(session, round_id=str(round_id), tenant_id=tenant_id)
    if record is None:
        raise _problem("NOT_FOUND", status.HTTP_404_NOT_FOUND, "Rodada de medição não encontrada.")
    return record


def _round_is_approved(revision: ValuationRoundRevisionRecord | None) -> bool:
    """Se a medição da rodada foi aprovada e não caducou (F-040).

    Espelha o portão: aprovação caduca não abre a medição seguinte, porque o acumulado seria
    apurado sobre conteúdo que mudou depois do ato humano.
    """
    state = approval_state(readable_valuation(revision))
    return bool(state["approved"]) and not bool(state["stale"])


def _valuation_round_plate_counts(
    session: Session, *, tenant_id: str, round_ids: Sequence[str]
) -> dict[str, int]:
    """Quantas folhas cada rodada da página tem, numa consulta só (F-046).

    Existe pelo mesmo motivo de `_valuation_round_heads`: desde que a folha virou tabela
    filha, a etapa da linha da listagem depende de "tem folha?", e perguntar isso por linha
    faria a primeira tela que o orçamentista abre custar N+1 idas ao banco.
    """
    if not round_ids:
        return {}
    rows = session.execute(
        select(
            ValuationRoundPlateRecord.round_id,
            func.count(ValuationRoundPlateRecord.id),
        )
        .where(
            ValuationRoundPlateRecord.tenant_id == tenant_id,
            ValuationRoundPlateRecord.round_id.in_(round_ids),
        )
        .group_by(ValuationRoundPlateRecord.round_id)
    ).all()
    return {str(round_id): int(total) for round_id, total in rows}


def _valuation_round_heads(
    session: Session, *, tenant_id: str, round_ids: Sequence[str]
) -> dict[str, ValuationRoundRevisionRecord]:
    """Cabeça de cada rodada da página, numa consulta só.

    Uma consulta por linha faria a listagem custar N+1 idas ao banco para preencher uma
    coluna de rótulo — e é justamente a listagem que a tela abre primeiro.
    """
    if not round_ids:
        return {}
    latest = (
        select(
            ValuationRoundRevisionRecord.round_id.label("round_id"),
            func.max(ValuationRoundRevisionRecord.version).label("version"),
        )
        .where(
            ValuationRoundRevisionRecord.tenant_id == tenant_id,
            ValuationRoundRevisionRecord.round_id.in_(round_ids),
        )
        .group_by(ValuationRoundRevisionRecord.round_id)
        .subquery()
    )
    records = session.scalars(
        select(ValuationRoundRevisionRecord)
        .join(
            latest,
            and_(
                ValuationRoundRevisionRecord.round_id == latest.c.round_id,
                ValuationRoundRevisionRecord.version == latest.c.version,
            ),
        )
        .where(ValuationRoundRevisionRecord.tenant_id == tenant_id)
    )
    return {record.round_id: record for record in records}


def _encode_round_cursor(
    record: ValuationRoundRecord | EstimateRoundRecord | SurveyRecord,
) -> str:
    """Cursor opaco sobre `(created_at, id)` — a mesma chave do índice da listagem.

    Serve as duas raízes de rodada porque o cursor depende só de `created_at` e `id`, que
    as duas têm com o mesmo significado e sob o mesmo índice composto. Duplicá-lo por
    tabela criaria duas codificações que ninguém garantiria idênticas.

    O carimbo sai do valor que o próprio banco devolveu, e não de um `datetime` montado
    aqui: é isso que faz a comparação da página seguinte usar exatamente a representação
    que aquele banco guarda, com ou sem fuso.
    """
    raw = f"{record.created_at.isoformat()}|{record.id}"
    return base64.urlsafe_b64encode(raw.encode("utf-8")).decode("ascii")


def _decode_round_cursor(cursor: str) -> tuple[datetime, str]:
    try:
        raw = base64.urlsafe_b64decode(cursor.encode("ascii")).decode("utf-8")
        stamp, separator, identifier = raw.partition("|")
        if not separator or not identifier:
            raise ValueError("cursor sem separador")
        return datetime.fromisoformat(stamp), identifier
    except (ValueError, UnicodeDecodeError) as error:
        raise _problem(
            "DOMAIN_VALIDATION_FAILED",
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "Cursor de paginação inválido.",
            {"code": "CURSOR_INVALID"},
        ) from error


def _require_valuation_upload(
    session: Session,
    application: FastAPI,
    *,
    upload_id: UUID,
    principal: Principal,
    content_type: str,
    storage_flavor: str,
) -> UploadRecord:
    """Upload do tenant, verificado contra o objeto realmente gravado.

    Mesma conferência da criação de job (tipo declarado, tamanho e checksum), com o tipo
    aceito vindo de quem chama: a rodada instala catálogo JSON e associa prancha PDF pelo
    mesmo presign, e cada uma delas aceita um tipo só.
    """
    upload = session.scalar(
        select(UploadRecord).where(
            UploadRecord.id == str(upload_id),
            UploadRecord.tenant_id == principal.tenant_id,
        )
    )
    if upload is None:
        raise _problem("NOT_FOUND", status.HTTP_404_NOT_FOUND, "Upload não encontrado.")
    if upload.status != "PRESIGNED":
        raise _problem(
            "INVALID_UPLOAD", status.HTTP_422_UNPROCESSABLE_ENTITY, "Upload indisponível."
        )
    if upload.content_type != content_type:
        raise _problem(
            "INVALID_UPLOAD",
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"Upload precisa ter o tipo {content_type}.",
        )
    expected_checksum = base64.b64encode(bytes.fromhex(upload.sha256)).decode("ascii")
    uploaded_object = application.state.artifact_store.head_upload(object_key=upload.object_key)
    # O checksum remoto não existe na interoperabilidade GCS; lá a integridade é conferida
    # sobre os bytes lidos (catálogo) ou pelo worker, que relê o documento (prancha).
    checksum_deferred = storage_flavor == "gcs"
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
    return upload


def _read_catalog_object(
    application: FastAPI,
    *,
    object_key: str,
    expected_sha256: str,
    unreadable_code: str,
) -> tuple[bytes, PriceCatalog]:
    """Bytes e catálogo validado de UM objeto JSON, conferido contra o digest esperado.

    O catálogo é o único artefato que a API lê do object store (ver `read_object`): ele é
    pequeno, é de aplicação e precisa ser validado ANTES de o ato existir — uma rodada nasce
    com catálogo por construção, e um catálogo que não valida aqui viraria uma rodada
    inutilizável em toda etapa seguinte.

    A entrada é **objeto + digest esperado**, e não o registro de upload, porque a fonte
    passou a ter dois caminhos (F-037): o upload do cliente e o acervo da plataforma. O que
    a leitura precisa saber é o mesmo nos dois — qual objeto ler e qual conteúdo ele tem de
    ter —, e o que muda é só o vocabulário da recusa, porque um objeto ausente do acervo
    não é problema do upload de ninguém.

    Os BYTES saem junto com o modelo porque a publicação no acervo grava o mesmo arquivo
    sob o prefixo do acervo, e reler o objeto só para copiá-lo seria uma segunda leitura do
    mesmo conteúdo — com a janela, entre uma e outra, de o objeto lido não ser o validado.
    """
    payload = application.state.artifact_store.read_object(
        object_key=object_key, max_bytes=CATALOG_MAX_BYTES
    )
    if payload is None:
        raise _problem(
            unreadable_code,
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "Catálogo ausente no armazenamento.",
        )
    if len(payload) > CATALOG_MAX_BYTES:
        raise _problem(
            "LIMIT_EXCEEDED",
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "Catálogo excede o limite de leitura da API.",
            {"max_bytes": CATALOG_MAX_BYTES},
        )
    if hashlib.sha256(payload).hexdigest() != expected_sha256.lower():
        raise _problem(
            unreadable_code,
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "Catálogo com integridade divergente do digest registrado.",
        )
    try:
        catalog = PriceCatalog.model_validate_json(payload)
    except ValidationError as error:
        # Recusa de contrato do modelo: a mensagem do pydantic pode conter valores do
        # arquivo, então só o código declarado sai.
        raise _problem(
            "DOMAIN_VALIDATION_FAILED",
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "O catálogo enviado não pôde ser lido.",
            {"code": "MODEL_VALIDATION_FAILED"},
        ) from error
    return payload, catalog


def _read_catalog(application: FastAPI, upload: UploadRecord) -> tuple[bytes, PriceCatalog]:
    """O catálogo de um upload do cliente; ilegível recusa o ato que o pediu."""
    return _read_catalog_object(
        application,
        object_key=upload.object_key,
        expected_sha256=upload.sha256,
        unreadable_code="INVALID_UPLOAD",
    )


def _install_catalog(
    application: FastAPI,
    *,
    object_key: str,
    object_sha256: str,
    unreadable_code: str,
) -> tuple[PriceCatalog, dict[str, Any]]:
    """Catálogo validado e o resumo que a entrada da cascata guarda ao lado dele."""
    _, catalog = _read_catalog_object(
        application,
        object_key=object_key,
        expected_sha256=object_sha256,
        unreadable_code=unreadable_code,
    )
    summary: dict[str, Any] = {
        "source_label": catalog.source_label,
        "reference_month": catalog.reference_month,
        "source_sha256": catalog.source_sha256,
        "entries": len(catalog.entries),
    }
    return catalog, summary


@dataclass(frozen=True, slots=True)
class _ValuationOrigin:
    """De onde a rodada de medição nasceu, já resolvido (F-036, ADR-0048).

    As duas origens produzem o MESMO objeto, e é isso que mantém a criação da rodada com um
    caminho só de gravação: o que muda é de onde a obra, o catálogo e o contratado vieram —
    não o que a rodada é depois de aberta.
    """

    worksite_key: str
    worksite_name: str
    address: str | None
    catalog_upload_id: str | None
    catalog_object_key: str
    catalog_source_sha256: str
    catalog_summary: dict[str, Any]
    estimate_round_id: str | None
    estimate_digest: str | None
    contract_workbook_json: dict[str, Any] | None
    upload: UploadRecord | None
    """O registro de upload a marcar `VERIFIED`, quando a origem foi um upload do cliente."""


def _price_adjustment_from_request(
    application: FastAPI,
    session: Session,
    *,
    payload: PriceAdjustmentRequest,
    contract: ContractWorkbook,
    principal: Principal,
    storage_flavor: str,
) -> PriceAdjustment:
    """A declaração do cliente vira o ato de domínio, com identidade e relógio do servidor.

    No tipo `catalog_version` é AQUI que o preço de cada código contratado é resolvido e
    materializado (ADR-0055, decisão 4): o cliente cita a versão nova, e o servidor lê. O
    cliente nunca informa preço — deixá-lo informar seria aceitar um número de contrato vindo
    de fora, que é o oposto do que este consolidado existe para garantir.
    """
    declared_at = datetime.now(UTC)
    if payload.kind == "index_factor":
        try:
            factor = parse_quantity(payload.factor)
        except DomainValidationError as error:
            raise _problem(
                "DOMAIN_VALIDATION_FAILED",
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "O fator do reajuste não é um decimal exato.",
            ) from error
        return PriceAdjustment(
            kind="index_factor",
            declared_by=principal.subject,
            declared_at=declared_at,
            reference_period=payload.reference_period,
            note=payload.note,
            index_label=payload.index_label,
            factor=factor,
        )

    assert payload.catalog_upload_id is not None  # garantido pelo contrato de entrada
    upload = _require_valuation_upload(
        session,
        application,
        upload_id=payload.catalog_upload_id,
        principal=principal,
        content_type=CATALOG_CONTENT_TYPE,
        storage_flavor=storage_flavor,
    )
    catalog, _summary = _install_catalog(
        application,
        object_key=upload.object_key,
        object_sha256=upload.sha256.lower(),
        unreadable_code="INVALID_UPLOAD",
    )
    precos = {entry.code: entry.unit_price for entry in catalog.entries}
    contratados = {line.code for line in contract.lines}
    faltando = sorted(contratados - set(precos))
    if faltando:
        # Recusa aqui, e não no modelo, para a mensagem citar o que falta: reprecificar
        # metade do contrato é pior do que não reprecificar.
        raise _problem(
            "PRICE_ADJUSTMENT_CODE_MISSING",
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "A versão nova da tabela não precifica todo código contratado.",
            {"missing": faltando[:20]},
        )
    return PriceAdjustment(
        kind="catalog_version",
        declared_by=principal.subject,
        declared_at=declared_at,
        reference_period=payload.reference_period,
        note=payload.note,
        catalog_label=catalog.source_label,
        catalog_sha256=catalog.source_sha256,
        prices_by_code={code: precos[code] for code in sorted(contratados)},
    )


def _origin_from_signed_estimate(
    session: Session,
    application: FastAPI,
    *,
    estimate_round_id: UUID,
    principal: Principal,
) -> _ValuationOrigin:
    """Obra, catálogo e contratado derivados de um orçamento **assinado** sob o regime.

    A ordem das recusas importa e é deliberada:

    1. a rodada existe e é do tenant — senão `404`, indistinguível de rodada alheia;
    2. o regime é `contracted_demand` — fora dele, chamar o orçamento de contratado seria
       mentira, porque entre ele e o contrato existiriam a licitação e o deságio
       (ADR-0048, decisão 1);
    3. há orçamento montado na cabeça;
    4. a assinatura é válida — quem recusa é `ensure_exportable()` dentro da tradução, que
       já sabe distinguir nunca assinado, rejeitado e caduco por remontagem.

    Inverter 2 e 3 faria uma rodada sem orçamento e sem regime recusar por motivo diferente
    conforme o que estivesse faltando primeiro.
    """
    record = estimate_rounds.load_round(
        session, round_id=str(estimate_round_id), tenant_id=principal.tenant_id
    )
    if record is None:
        raise _problem(
            "NOT_FOUND", status.HTTP_404_NOT_FOUND, "Rodada de orçamento não encontrada."
        )
    if record.pricing_regime != estimate_rounds.REGIME_CONTRACTED_DEMAND:
        raise _problem(
            "ESTIMATE_ORIGIN_REGIME_REQUIRED",
            status.HTTP_409_CONFLICT,
            "Só orçamento sob demanda contratada vira contratado da medição: fora desse "
            "regime existem a licitação e o deságio entre o orçamento e o contrato.",
        )
    revision = estimate_rounds.head_revision(
        session, round_id=record.id, tenant_id=principal.tenant_id
    )
    document = estimate_rounds.require_document(
        revision,
        "estimate_json",
        stage=estimate_rounds.STAGE_ESTIMATE,
        detail="a rodada de orçamento ainda não tem orçamento montado",
    )
    try:
        estimate = Estimate.model_validate(dict(document))
    except ValidationError as error:
        raise _valuation_model_problem(error) from error

    try:
        contract = build_contract_from_estimate(
            estimate,
            group_label=record.reference_label,
            source_label=f"orçamento assinado: {record.reference_label}",
        )
    except ValuationValidationError as error:
        # `ensure_exportable()` recusa com `ESTIMATE_EXPORT_BLOCKED` e a lista de violações;
        # aqui o código é próprio porque a condição é outra: não é "não posso despachar", é
        # "não posso abrir medição contra isto".
        raise _problem(
            "ESTIMATE_ORIGIN_NOT_SIGNED",
            status.HTTP_409_CONFLICT,
            "O orçamento não tem assinatura válida: sem conteúdo aprovado não há contratado "
            "de onde abrir a medição.",
            {"errors": error.details.get("errors", [error.code])},
        ) from error

    cascade = estimate_rounds.cascade_entries(record)
    installed = next((entry for entry in cascade if entry.origin == PriceOrigin.SCO.value), None)
    if installed is None:
        raise _problem(
            "CATALOG_REQUIRED",
            status.HTTP_409_CONFLICT,
            "A rodada de orçamento não tem a tabela contratual instalada.",
        )
    _catalog, summary = _install_catalog(
        application,
        object_key=installed.object_key,
        object_sha256=installed.object_sha256,
        unreadable_code="CATALOG_REQUIRED",
    )
    approval = estimate.approval
    # A tradução acima já recusou o caso `None`; a asserção é para o type checker.
    assert approval is not None
    return _ValuationOrigin(
        worksite_key=estimate.worksite_key,
        worksite_name=estimate.worksite_name,
        address=estimate.address,
        # O arquivo pode ter vindo do acervo da plataforma, onde não há upload do cliente a
        # citar; `catalog_object_key` e `catalog_source_sha256` é que dizem o que ler.
        catalog_upload_id=installed.upload_id,
        catalog_object_key=installed.object_key,
        catalog_source_sha256=installed.object_sha256,
        catalog_summary=summary,
        estimate_round_id=record.id,
        estimate_digest=approval.estimate_digest,
        contract_workbook_json=contract.model_dump(mode="json"),
        upload=None,
    )


def _export_contract_for(record: ValuationRoundRecord, valuation: Valuation) -> ContractWorkbook:
    """O consolidado que o portão recebe: o gravado, se a rodada tem origem assinada.

    Sem vínculo, cai no `bulletin_export_contract` de sempre — o consolidado FABRICADO a
    partir da própria medição, com os seis guardrails inertes que o docstring dele declara.
    Removê-lo quebraria toda rodada aberta sem orçamento de origem, e é por isso que os dois
    convivem (ADR-0048, decisão 9); o que não pode é as duas rodadas parecerem iguais, e é a
    leitura da rodada que as distingue.

    Consolidado gravado que não revalida é falha de ambiente, não do ato corrente: ele foi
    escrito pela abertura da rodada e é imutável desde então.
    """
    stored = record.contract_workbook_json
    if stored is None:
        return bulletin_export_contract(valuation)
    try:
        return ContractWorkbook.model_validate(dict(stored))
    except ValidationError as error:
        raise _valuation_model_problem(error) from error


def _amendment_from_request(
    application: FastAPI,
    *,
    payload: AmendmentRequest,
    origin: _ValuationOrigin,
    principal: Principal,
) -> Amendment:
    """A declaração de RE-RA do cliente vira o ato de domínio, com identidade e relógio do servidor.

    O item novo é materializado AQUI, do catálogo contratual instalado na rodada (ADR-0056,
    decisão 7): o cliente cita o código e o delta, e o servidor lê descrição, unidade e preço.
    Código de item novo ausente do catálogo recusa — não há de onde a linha nascer.
    """
    declared_at = datetime.now(UTC)
    needs_catalog = any(line.is_new_item for line in payload.lines)
    entries: dict[str, Any] = {}
    if needs_catalog:
        catalog, _summary = _install_catalog(
            application,
            object_key=origin.catalog_object_key,
            object_sha256=origin.catalog_source_sha256,
            unreadable_code="CATALOG_REQUIRED",
        )
        entries = {entry.code: entry for entry in catalog.entries}

    lines: list[AmendmentLine] = []
    for line in payload.lines:
        try:
            quantity_delta = parse_quantity(line.quantity_delta)
        except DomainValidationError as error:
            raise _problem(
                "DOMAIN_VALIDATION_FAILED",
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "O delta de quantidade da RE-RA não é um decimal exato.",
            ) from error
        if line.is_new_item:
            entry = entries.get(line.code)
            if entry is None:
                raise _problem(
                    "AMENDMENT_NEW_ITEM_CODE_MISSING",
                    status.HTTP_422_UNPROCESSABLE_ENTITY,
                    "O item novo da RE-RA cita um código que o catálogo contratual não traz: "
                    "não há de onde materializar descrição, unidade e preço.",
                    {"code": line.code},
                )
            lines.append(
                AmendmentLine(
                    code=line.code,
                    quantity_delta=quantity_delta,
                    is_new_item=True,
                    note=line.note,
                    description=entry.description,
                    unit=entry.unit,
                    unit_price=entry.unit_price,
                )
            )
        else:
            lines.append(
                AmendmentLine(code=line.code, quantity_delta=quantity_delta, note=line.note)
            )
    return Amendment(
        label=payload.label,
        lines=lines,
        declared_by=principal.subject,
        declared_at=declared_at,
        reference_period=payload.reference_period,
        note=payload.note,
    )


def _origin_from_previous_round(
    session: Session,
    application: FastAPI,
    *,
    previous_round_id: UUID,
    declared_period_number: int,
    principal: Principal,
) -> _ValuationOrigin:
    """A medição seguinte: obra, catálogo e contratado vêm da rodada anterior aprovada (F-040).

    A rodada `n+1` nasce do consolidado da rodada `n` mais o período aprovado nela (ADR-0056,
    decisão 4; ADR-0048, decisão 8). Reajustes e RE-RA já declarados na rodada anterior estão
    no consolidado dela e são preservados. Exige a rodada anterior **aprovada** (decisão 5):
    o acumulado é a base do saldo, e apurá-lo sobre período não aprovado afirma como medido o
    que ainda pode mudar.
    """
    record = load_round(session, round_id=str(previous_round_id), tenant_id=principal.tenant_id)
    if record is None:
        raise _problem("NOT_FOUND", status.HTTP_404_NOT_FOUND, "Rodada anterior não encontrada.")
    stored = record.contract_workbook_json
    if stored is None:
        raise _problem(
            "NEXT_ROUND_PREVIOUS_WITHOUT_CONTRACT",
            status.HTTP_409_CONFLICT,
            "A rodada anterior não tem consolidado contratual: só a medição sob contrato abre a "
            "medição seguinte.",
        )
    revision = head_revision(session, round_id=record.id, tenant_id=principal.tenant_id)
    valuation = readable_valuation(revision)
    state = approval_state(valuation)
    if valuation is None or not state["approved"] or state["stale"]:
        raise _problem(
            "NEXT_ROUND_PREVIOUS_NOT_APPROVED",
            status.HTTP_409_CONFLICT,
            "A medição seguinte exige a rodada anterior aprovada: o acumulado é a base do saldo, "
            "e apurá-lo sobre período não aprovado afirma como medido o que ainda pode mudar.",
        )
    expected_period = record.period_number + 1
    if declared_period_number != expected_period:
        raise _problem(
            "PERIOD_NOT_SEQUENTIAL",
            status.HTTP_409_CONFLICT,
            "A medição seguinte é o período imediatamente após o da rodada anterior.",
            {"expected": expected_period, "declared": declared_period_number},
        )
    measured: dict[str, Decimal] = {}
    for bulletin in valuation.bulletins:
        for line in bulletin.lines:
            measured[line.code] = measured.get(line.code, Decimal("0.00")) + line.quantity
    try:
        previous_contract = ContractWorkbook.model_validate(dict(stored))
        nxt = build_next_round_contract(
            previous_contract, measured=measured, period_number=record.period_number
        )
    except ValuationValidationError as error:
        raise _valuation_domain_problem(error) from error
    except ValidationError as error:
        raise _valuation_model_problem(error) from error
    return _ValuationOrigin(
        worksite_key=record.worksite_key,
        worksite_name=record.worksite_name,
        address=record.address,
        catalog_upload_id=record.catalog_upload_id,
        catalog_object_key=record.catalog_object_key,
        catalog_source_sha256=record.catalog_source_sha256,
        catalog_summary=record.catalog_summary_json,
        estimate_round_id=record.estimate_round_id,
        estimate_digest=record.estimate_digest,
        contract_workbook_json=nxt.model_dump(mode="json"),
        upload=None,
    )


def _resolve_valuation_origin(
    session: Session,
    application: FastAPI,
    *,
    payload: CreateValuationRoundRequest,
    principal: Principal,
    storage_flavor: str,
) -> _ValuationOrigin:
    """As três portas da criação da rodada; o contrato já garantiu que só uma foi usada."""
    if payload.estimate_round_id is not None or payload.previous_round_id is not None:
        if payload.estimate_round_id is not None:
            origin = _origin_from_signed_estimate(
                session,
                application,
                estimate_round_id=payload.estimate_round_id,
                principal=principal,
            )
        else:
            assert payload.previous_round_id is not None
            origin = _origin_from_previous_round(
                session,
                application,
                previous_round_id=payload.previous_round_id,
                declared_period_number=payload.period_number,
                principal=principal,
            )
        if payload.price_adjustment is None and payload.amendment is None:
            return origin
        # Reajuste e RE-RA entram no consolidado ANTES de ele ser gravado e compõem na ordem
        # declarada (ADR-0056, decisão 6): depois disso ele é imutável na rodada (ADR-0048,
        # decisão 7), e é essa imutabilidade que faz a declaração valer para o período inteiro.
        assert origin.contract_workbook_json is not None
        contract = ContractWorkbook.model_validate(dict(origin.contract_workbook_json))
        if payload.price_adjustment is not None:
            adjustment = _price_adjustment_from_request(
                application,
                session,
                payload=payload.price_adjustment,
                contract=contract,
                principal=principal,
                storage_flavor=storage_flavor,
            )
            try:
                reajustado = contract.model_copy(
                    update={"adjustments": [*contract.adjustments, adjustment]}
                )
                # `model_copy` não revalida: a releitura é o que faz a cobertura por código do
                # `catalog_version` ser conferida pelo domínio, e não só pela fronteira.
                contract = ContractWorkbook.model_validate(reajustado.model_dump(mode="json"))
            except ValidationError as error:
                raise _valuation_model_problem(error) from error
        if payload.amendment is not None:
            declared = _amendment_from_request(
                application, payload=payload.amendment, origin=origin, principal=principal
            )
            try:
                contract = apply_declared_amendment(contract, declared)
            except ValuationValidationError as error:
                raise _valuation_domain_problem(error) from error
            except ValidationError as error:
                raise _valuation_model_problem(error) from error
        return replace(origin, contract_workbook_json=contract.model_dump(mode="json"))

    # Caminho de sempre: obra declarada e catálogo por upload, sem contratado a conferir.
    assert payload.catalog_upload_id is not None
    assert payload.worksite_key is not None
    assert payload.worksite_name is not None
    upload = _require_valuation_upload(
        session,
        application,
        upload_id=payload.catalog_upload_id,
        principal=principal,
        content_type=CATALOG_CONTENT_TYPE,
        storage_flavor=storage_flavor,
    )
    _catalog, summary = _install_catalog(
        application,
        object_key=upload.object_key,
        object_sha256=upload.sha256.lower(),
        unreadable_code="INVALID_UPLOAD",
    )
    return _ValuationOrigin(
        worksite_key=payload.worksite_key,
        worksite_name=payload.worksite_name,
        address=payload.address,
        catalog_upload_id=str(payload.catalog_upload_id),
        catalog_object_key=upload.object_key,
        catalog_source_sha256=upload.sha256.lower(),
        catalog_summary=summary,
        estimate_round_id=None,
        estimate_digest=None,
        contract_workbook_json=None,
        upload=upload,
    )


def _catalog_source(payload: InstallEstimateCatalogRequest) -> tuple[str, UUID]:
    """A procedência do ato e o identificador que ela cita; nunca os dois, nunca nenhum.

    A recusa é de CONTRATO e vem antes de qualquer lookup: um corpo que cita as duas
    formas não é ambíguo só para o servidor — ele é ambíguo sobre qual arquivo o
    orçamentista quis instalar, e escolher uma delas em silêncio gravaria uma cascata que
    ninguém pediu. Sem gravar nada, nos dois casos.
    """
    if payload.upload_id is not None and payload.reference_catalog_id is None:
        return estimate_rounds.PROVENANCE_TENANT_UPLOAD, payload.upload_id
    if payload.reference_catalog_id is not None and payload.upload_id is None:
        return estimate_rounds.PROVENANCE_REFERENCE_CATALOG, payload.reference_catalog_id
    raise _problem(
        estimate_rounds.ESTIMATE_CATALOG_SOURCE_INVALID,
        status.HTTP_422_UNPROCESSABLE_ENTITY,
        (
            "Informe a tabela do acervo (reference_catalog_id) ou o arquivo próprio (upload_id)."
            if payload.upload_id is None
            else "Informe apenas uma fonte: a tabela do acervo ou o arquivo próprio."
        ),
    )


def _require_available_reference_catalog(
    session: Session, *, reference_catalog_id: UUID
) -> ReferenceCatalogRecord:
    """A tabela do acervo em circulação, ou a recusa. **Sem filtro de tenant**, e é a única.

    O acervo é dado da plataforma e ler dele é livre para quem opera o orçamento (ADR-0047
    decisões 1 e 5): não há tenant a comparar, porque a linha não tem dono. É a exceção
    autorizada, e ela vale só aqui — o upload do cliente continua filtrado por
    `tenant_id` em `_require_valuation_upload`.

    Catálogo fora de circulação recusa em vez de instalar: retirar é justamente parar de
    oferecê-lo em escolha nova, e a rodada que já o instalou continua intacta.
    """
    record = session.get(ReferenceCatalogRecord, str(reference_catalog_id))
    if record is None:
        raise _problem("NOT_FOUND", status.HTTP_404_NOT_FOUND, "Catálogo do acervo não encontrado.")
    if record.status != STATUS_AVAILABLE:
        raise _problem(
            "REFERENCE_CATALOG_WITHDRAWN",
            status.HTTP_409_CONFLICT,
            "Esta tabela saiu de circulação e não é mais oferecida para instalação nova.",
            {"reference_catalog_id": record.id},
        )
    return record


def _require_platform_operator(principal: Principal) -> None:
    if not principal.has_role("platform_operator"):
        raise _problem(
            "FORBIDDEN",
            status.HTTP_403_FORBIDDEN,
            "Papel platform_operator é obrigatório para administrar autorização contratual.",
        )


def _all_known_tenant_ids(session: Session) -> list[str]:
    """UNION real (distinct entre selects) sobre as três tabelas com pegada de tenant.

    `uploads` é a pegada mais precoce do ciclo de vida (existe antes de qualquer job ou
    project), então entra na união mesmo sem entitlement ou project associado. Ordenação
    por `tenant_id` em Python garante que SQLite (testes) e PostgreSQL (HML) concordem —
    não depender de ordenação implícita de UNION entre dialetos.
    """
    query = (
        select(TenantAiProcessingEntitlementRecord.tenant_id)
        .distinct()
        .union(
            select(ProjectRecord.tenant_id).distinct(),
            select(UploadRecord.tenant_id).distinct(),
        )
    )
    return sorted({row[0] for row in session.execute(query)})


def _platform_tenant_response(
    tenant_id: str, entitlement: TenantAiProcessingEntitlementRecord | None
) -> PlatformTenantResponse:
    if entitlement is None:
        return PlatformTenantResponse(
            tenant_id=tenant_id,
            enabled=False,
            agreement_reference=None,
            authorized_at=None,
            revoked_at=None,
        )
    return PlatformTenantResponse(
        tenant_id=tenant_id,
        enabled=entitlement.status == "ACTIVE",
        agreement_reference=entitlement.agreement_reference or None,
        authorized_at=entitlement.authorized_at,
        revoked_at=entitlement.revoked_at,
    )


def _journey_entitlement_response(
    record: TenantJourneyEntitlementRecord,
) -> JourneyEntitlementResponse:
    """Só as colunas do ato; nada de `id`, `updated_at` ou linha bruta de banco."""
    return JourneyEntitlementResponse(
        tenant_id=record.tenant_id,
        journey=cast(Journey, record.journey),
        enabled=record.status == "ACTIVE",
        agreement_reference=record.agreement_reference,
        authorized_by=record.authorized_by,
        authorized_at=record.authorized_at,
        revoked_at=record.revoked_at,
    )


def _reference_catalog_response(record: ReferenceCatalogRecord) -> ReferenceCatalogResponse:
    """Só o que descreve a publicação; a chave do objeto não sai daqui."""
    return ReferenceCatalogResponse(
        reference_catalog_id=UUID(record.id),
        display_name=record.display_name,
        origin=record.origin,
        reference_month=record.reference_month,
        entry_count=record.entry_count,
        object_sha256=record.object_sha256,
        source_sha256=record.source_sha256,
        available=record.status == STATUS_AVAILABLE,
        published_by=record.published_by,
        published_at=record.published_at,
        withdrawn_at=record.withdrawn_at,
    )


def _reference_catalog_index_response(
    record: ReferenceCatalogEmbeddingRecord,
) -> ReferenceCatalogIndexResponse:
    """Só o que descreve a publicação; nem a chave do objeto, nem um único vetor."""
    return ReferenceCatalogIndexResponse(
        reference_catalog_index_id=UUID(record.id),
        reference_catalog_id=UUID(record.reference_catalog_id),
        catalog_source_sha256=record.catalog_source_sha256,
        text_recipe=record.text_recipe,
        provider=record.provider,
        model_id=record.model_id,
        dims=record.dims,
        code_count=record.code_count,
        object_sha256=record.object_sha256,
        available=record.status == STATUS_AVAILABLE,
        published_by=record.published_by,
        published_at=record.published_at,
        withdrawn_at=record.withdrawn_at,
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


#: O `algorithm` da forma corrigida por pessoa. Nome, e não versão de detector: quem
#: produziu o conjunto já está dito em `detector_version` (ADR-0050, decisão 1).
HUMAN_SHAPE_CORRECTION_ALGORITHM: Final = "human-shape-correction-v1"


def _shape_correction_id(job_id: UUID, review_version: int, ordinal: int) -> str:
    """Id determinístico da correção, no formato que `VisionProposal` exige.

    Determinístico e não aleatório para que o replay idempotente da mesma requisição
    produza o mesmo id: `Idempotency-Key` repetida devolve a resposta gravada, e um id
    sorteado faria a segunda tentativa divergir da primeira se ela chegasse a executar.
    """
    semente = f"{job_id}:{review_version}:{ordinal}".encode()
    return f"vp_{hashlib.sha256(semente).hexdigest()[:16]}"


def _carried_review_context(record: ReviewRevisionRecord) -> dict[str, Any]:
    """Campos laterais que toda revisão sucessora preserva verbatim.

    Testemunhas e observações de campo (F-030) e as correções humanas de forma (F-018)
    não são recomputadas por ato nenhum da revisão: elas são registro histórico e viajam
    inteiras para a revisão seguinte. Ficam num lugar só justamente porque esquecer uma
    delas em um dos caminhos de escrita apagaria trabalho humano em silêncio.
    """
    return {
        "field_witnesses_json": list(record.field_witnesses_json),
        "field_observations_json": list(record.field_observations_json),
        "shape_corrections_json": record.shape_corrections_json,
    }


def _confirmed_reading_value_mm(reading: DimensionReading) -> Decimal:
    if reading.status is not ReadingStatus.CONFIRMED or reading.value_si is None:
        raise _problem(
            "FIELD_WITNESS_READING_NOT_CONFIRMED",
            status.HTTP_409_CONFLICT,
            "A leitura da prancha precisa estar confirmada antes de receber testemunha.",
        )
    return reading.value_si * Decimal(1000) if reading.unit is UnitCode.METRE else reading.value_si


def _resolve_field_witness_source(
    session: Session,
    *,
    job: JobRecord,
    source: FieldWitnessSource,
) -> tuple[Decimal, str | None]:
    """Resolve valor e procedência no servidor; nenhum número vem do comando."""
    if source.type == "photo_reading":
        try:
            confirmation_id = str(UUID(source.source_id))
        except ValueError as error:
            raise _problem(
                "FIELD_WITNESS_SOURCE_NOT_FOUND",
                status.HTTP_404_NOT_FOUND,
                "Leitura confirmada da foto não encontrada.",
            ) from error
        confirmation = session.scalar(
            select(FieldPhotoValueConfirmationRecord).where(
                FieldPhotoValueConfirmationRecord.id == confirmation_id,
                FieldPhotoValueConfirmationRecord.tenant_id == job.tenant_id,
                FieldPhotoValueConfirmationRecord.job_id == job.id,
                FieldPhotoValueConfirmationRecord.status == "ACTIVE",
            )
        )
        if confirmation is None:
            raise _problem(
                "FIELD_WITNESS_SOURCE_NOT_FOUND",
                status.HTTP_404_NOT_FOUND,
                "Leitura confirmada da foto não encontrada.",
            )
        return Decimal(confirmation.value_mm), None

    assert source.survey_id is not None
    linked = session.scalar(
        select(JobSurveyLinkRecord.id).where(
            JobSurveyLinkRecord.tenant_id == job.tenant_id,
            JobSurveyLinkRecord.job_id == job.id,
            JobSurveyLinkRecord.survey_id == source.survey_id,
        )
    )
    if linked is None:
        raise _problem(
            "FIELD_WITNESS_SOURCE_NOT_FOUND",
            status.HTTP_404_NOT_FOUND,
            "Medida confirmada do levantamento não encontrada.",
        )
    survey = _load_survey(session, survey_id=source.survey_id, tenant_id=job.tenant_id)
    packet = SurveyPacket.model_validate(survey.snapshot_json)
    measurement = next((item for item in packet.measurements if item.id == source.source_id), None)
    if measurement is None or measurement.status is not FieldMeasurementStatus.CONFIRMED:
        raise _problem(
            "FIELD_WITNESS_SOURCE_NOT_CONFIRMED",
            status.HTTP_409_CONFLICT,
            "A medida do levantamento precisa estar confirmada.",
        )
    return Decimal(measurement.value_mm), survey.id


def _field_observation_source(
    analysis: FieldEvidenceAnalysisRecord, document: dict[str, Any]
) -> FieldObservationSource:
    """Monta a fonte da observação a partir do artefato de classificação, no servidor."""
    classification = document.get("classification")
    category = classification.get("category") if isinstance(classification, dict) else None
    lineage = document.get("lineage")
    provider = model_id = prompt_version = schema_version = None
    if isinstance(lineage, dict):
        provider = lineage.get("provider")
        model_id = lineage.get("model_id")
        prompt = lineage.get("prompt")
        if isinstance(prompt, dict):
            prompt_version = prompt.get("prompt_version")
            schema_version = prompt.get("schema_version")
    return FieldObservationSource(
        analysis_id=UUID(analysis.id),
        category=category,
        provider=provider,
        model_id=model_id,
        prompt_version=prompt_version,
        schema_version=schema_version,
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
            "unapplied_readings": list(record.unapplied_readings_json or []),
            "contested_spans": list(record.contested_spans_json or []),
            "applied_spans": list(record.applied_spans_json or []),
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


CHAIN_READING_SUPERSEDED_CODE = "CHAIN_READING_SUPERSEDED"
CHAIN_READING_SUPERSEDED_MESSAGE = (
    "Uma das cotas desta cadeia deixou de estar confirmada depois que ela foi declarada; "
    "confira a cadeia e declare de novo, ou retrate-a."
)


def _declared_chain_responses(
    packet: ReviewPacket, declared: Sequence[Mapping[str, Any]]
) -> list[DeclaredChainResponse]:
    """Reconfere cada cadeia declarada contra o pacote corrente, sem tocar no gravado.

    A declaração é histórica e imutável; o veredito não é. Retificar uma leitura da
    cadeia não pode continuar afirmando um fechamento que já não existe, e também não
    pode fazer a cadeia sumir sem que ninguém veja — daí `stale`, que é aviso e pede um
    ato humano.
    """
    responses: list[DeclaredChainResponse] = []
    for item in declared:
        common = {
            "chain_id": item["chain_id"],
            "declared_by": item["declared_by"],
            "declared_at": item["declared_at"],
        }
        # A reconferência mora junto do score (`association_confidence`) porque os dois
        # caminhos de escrita de revisão — este e o do worker — precisam dar o mesmo
        # veredito sobre a mesma declaração.
        chain = verified_declared_chain(packet, item)
        if chain is None:
            responses.append(
                DeclaredChainResponse(
                    **common,
                    chain=None,
                    status="stale",
                    issue=Issue(
                        code=CHAIN_READING_SUPERSEDED_CODE,
                        severity=IssueSeverity.WARNING,
                        message=CHAIN_READING_SUPERSEDED_MESSAGE,
                    ),
                )
            )
            continue
        responses.append(
            DeclaredChainResponse(
                **common,
                chain=chain,
                status="closes" if chain.closes else "mismatch",
                issue=chain.issue(),
            )
        )
    return responses


def _carried_confidence_shadow(current: ReviewRevisionRecord) -> dict[str, Any]:
    """Shadow da revisão nova quando pacote, candidatos e cadeias viajam verbatim.

    Recomputa em vez de copiar `current.confidence_shadow_json`: a revisão parental pode
    ser anterior à coluna — copiar propagaria o vazio para sempre. Como o shadow é função
    pura desses três campos, e os três são idênticos aos da parental, recomputar devolve
    exatamente o que a parental devolveria.

    Uma diferença é deliberada: o registro do ATO de auto-decisão (`auto_decisions`, F-029)
    não é recomputável e fica só na revisão 1, a única em que ele pode ter acontecido.
    Repeti-lo nas revisões seguintes afirmaria um ato novo que ninguém praticou; o que
    viaja para elas é o efeito — a decisão de ator-máquina gravada no próprio pacote.
    """
    return confidence_shadow_json(
        ReviewPacket.model_validate(current.packet_json),
        AssociationSet.model_validate(current.associations_json),
        current.declared_chains_json,
    )


@dataclass(frozen=True, slots=True)
class ConfidenceView:
    """Os campos observacionais de confiança de uma revisão, prontos para a resposta."""

    reading_confidences: list[ReadingConfidence]
    confidence_shadow: list[ShadowDecisionResponse]
    auto_association_rate: float | None
    review_rate: float | None


def _confidence_view(shadow: Mapping[str, Any] | None) -> ConfidenceView:
    """Lê o shadow gravado e publica as taxas OBSERVACIONAIS da revisão corrente.

    As duas taxas são medidas do registro, não decisões, e dependem inteiramente da grade
    e do ponto de referência (`CONFIDENCE_REFERENCE_THRESHOLD`) — mudar a grade muda os
    números sem que nada no produto tenha mudado. Denominadores diferentes de propósito:

    - `auto_association_rate` = leituras auto-decidíveis no ponto de referência ÷ leituras
      que têm ao menos um candidato de associação. Pergunta "das cotas onde havia a quem
      associar, quantas o corte resolveria sozinho?"; leitura sem candidato nenhum não é
      falha do score e falsearia o numerador.
    - `review_rate` = complemento sobre o TOTAL de leituras da revisão. Pergunta "quanto
      da revisão ainda exige uma pessoa?", e aí a leitura sem candidato conta: ela também
      é trabalho humano.

    Revisão gravada antes da coluna, ou por um caminho que não a preenche, responde com
    listas vazias e taxas nulas — ausência de registro, nunca zero medido.

    O `score_version` gravado não é filtrado aqui porque só existe uma versão de pesos: o
    campo existe desde a primeira linha para que o dia da recalibração encontre o histórico
    já separável. Quem publicar taxa AGREGADA sobre várias revisões precisa agrupar por
    ele; esta função descreve uma revisão só, que tem uma versão só.
    """
    stored = shadow or {}
    reading_confidences = [
        ReadingConfidence.model_validate(item) for item in stored.get("reading_confidences", [])
    ]
    confidence_shadow = [
        ShadowDecisionResponse.model_validate(item) for item in stored.get("decisions", [])
    ]
    reference = next(
        (
            decision
            for decision in confidence_shadow
            if decision.reading_threshold == CONFIDENCE_REFERENCE_THRESHOLD.reading_threshold
            and decision.association_threshold
            == CONFIDENCE_REFERENCE_THRESHOLD.association_threshold
        ),
        None,
    )
    if reference is None:
        return ConfidenceView(
            reading_confidences=reading_confidences,
            confidence_shadow=confidence_shadow,
            auto_association_rate=None,
            review_rate=None,
        )
    auto_decidable = len(reference.auto_choices)
    total = int(stored.get("readings_total", 0))
    with_candidate = int(stored.get("readings_with_candidate", 0))
    return ConfidenceView(
        reading_confidences=reading_confidences,
        confidence_shadow=confidence_shadow,
        auto_association_rate=(
            round(auto_decidable / with_candidate, 4) if with_candidate else None
        ),
        review_rate=round((total - auto_decidable) / total, 4) if total else None,
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
    shape_corrections = (
        VisionProposalSet.model_validate(record.shape_corrections_json)
        if record.shape_corrections_json is not None
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
    # O shadow é LIDO do que a revisão gravou, nunca recomputado aqui: ele vale por ser o
    # que o pipeline teria feito no instante daquela revisão. Recompor agora compararia a
    # decisão humana de ontem com o score de hoje.
    confidence = _confidence_view(record.confidence_shadow_json)
    return ReviewResponse(
        job_id=UUID(record.job_id),
        review_id=UUID(record.id),
        version=record.version,
        packet=packet,
        associations=associations,
        proposals=proposals,
        shape_corrections=shape_corrections,
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
        suggested_chains=suggest_chains(packet),
        declared_chains=_declared_chain_responses(packet, record.declared_chains_json),
        reading_confidences=confidence.reading_confidences,
        confidence_shadow=confidence.confidence_shadow,
        auto_association_rate=confidence.auto_association_rate,
        review_rate=confidence.review_rate,
        field_witnesses=[
            FieldWitnessResponse.model_validate(value) for value in record.field_witnesses_json
        ],
        field_observations=[
            FieldObservationResponse.model_validate(value)
            for value in record.field_observations_json
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


_REQUEST_LOGGER = logging.getLogger("croquito_api.request")
_VALUATION_LOGGER = logging.getLogger("croquito_api.valuation")
"""Log estruturado das ações de rodada que gastam (ou poderiam gastar) via paga.

Só grandezas entram no `extra`, pelo mesmo contrato do `CLAUDE.md` que rege o
`request_completed`: id opaco de rodada, stage, `arm_ran`, model id, tokens, custo e
contagens — nunca rótulo, descrição ou qualquer conteúdo embutido."""


def create_app(settings: ApiSettings | None = None, database: Database | None = None) -> FastAPI:
    configure_logging()
    runtime_settings = settings or ApiSettings.from_environment()
    runtime_database = database or Database(runtime_settings.database_url)

    def journey_gate(request: Request) -> None:
        """Portão de disponibilidade de jornada, aplicado UMA vez para toda rota (F-034).

        Entra como dependência do router — não como cópia em cada uma das rotas — porque a
        checagem replicada rota a rota é exatamente o jeito de uma rota nova nascer sem
        portão. `tests/api/test_journeys.py` percorre as rotas publicadas e reprova o
        prefixo `/v1/` que ninguém classificou.

        Declara só `Request`: qualquer outro parâmetro (esquema de segurança, header, sessão
        de banco) viraria `security`/`parameters` no documento OpenAPI de TODAS as rotas,
        inclusive das públicas, e abriria sessão de banco até no `/healthz`.

        Responde só às duas primeiras perguntas — ambiente e tenant. O papel continua sendo
        exigido por cada rota, com o código que ela já usa: a disponibilidade ANTECEDE o
        portão de papel, não o substitui.
        """
        journey = journey_of_path(request.url.path)
        if journey is None:
            return
        state = runtime_settings.journeys.state_of(journey)
        if state == "enabled":
            # Caminho de todo ambiente que não declara nada: nem autentica de novo, nem
            # toca o banco. É o que faz esta feature não custar nada onde não foi ligada.
            return
        principal = optional_principal(request)
        if principal is None:
            # Sem principal não há tenant para perguntar, e o portão não fabrica recusa de
            # autenticação: a dependência da própria rota devolve o `401` de sempre.
            return
        if state == "disabled":
            # Nenhum entitlement muda esta resposta, então não se pergunta ao banco. Importa
            # porque `disabled` é justamente o estado que segue recebendo tráfego — link
            # antigo, aba aberta, bundle velho da SPA — e cada uma dessas requisições abriria
            # uma sessão para uma consulta cujo resultado já é irrelevante.
            raise _journey_unavailable(journey)
        entitled = _entitled_journeys(
            runtime_database, tenant_id=principal.tenant_id, journeys=(journey,)
        )
        if journey_reachable(state, entitled=journey in entitled):
            return
        raise _journey_unavailable(journey)

    application = FastAPI(
        title="Croquito API",
        version="0.2.0",
        description="API de controle; processamento pesado ocorre fora do request HTTP.",
        dependencies=[Depends(journey_gate)],
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
        jwks_url=runtime_settings.oidc_jwks_url,
    )
    queue_adapter: QueueAdapter = (
        PubSubProcessingQueue(runtime_settings)
        if runtime_settings.queue_backend == "pubsub"
        else ProcessingQueue(runtime_settings)
    )
    application.state.queue = queue_adapter
    application.state.artifact_store = ArtifactStore(runtime_settings)
    application.state.settings = runtime_settings
    # Catálogo decodificado por digest, com a vida da aplicação: a busca de código é
    # consultada a cada tecla e decodificar 2,4 MB de JSON por requisição tornaria a etapa
    # mais usada da tela a mais cara. Preso à aplicação, e não ao módulo, para que duas
    # aplicações do mesmo processo (a suíte inteira) não compartilhem catálogo decodificado.
    application.state.catalog_cache = CatalogCache()
    # Índice de embeddings decodificado por (digest do índice, digest do catálogo), também
    # com a vida da aplicação e pelo mesmo motivo — só que a conta é outra: ~40 MB de matriz
    # por entrada, não alguns MB de JSON. Preso à aplicação, e não ao módulo, para que duas
    # aplicações do mesmo processo (a suíte inteira) não compartilhem índice decodificado.
    application.state.semantic_index_cache = SemanticIndexCache()
    # A via de embeddings vive na APLICAÇÃO, e não é construída a cada recompute (ADR-0054,
    # aceite humano item 2). `build_embeddings_adapter()` cria um `CostBudget` novo a cada
    # chamada (`providers.py`), o que num CLI é certo — um comando, um teto — e num serviço
    # hospedado seria teto nenhum: cada requisição começaria o orçamento do zero e o limite
    # do processo nunca seria alcançado. Preso aqui, o `BudgetedEmbeddingsAdapter` acumula
    # de verdade.
    #
    # Construir só com providers reais LIGADOS não é otimização: com o ambiente desligado
    # não existe chamada externa possível, e ler credencial para guardar um objeto que
    # ninguém pode usar seria o contrário do que `CROQUITO_REAL_PROVIDERS_ENABLED=false`
    # promete. O motivo da ausência é guardado ao lado do adapter porque é ele que vira a
    # nota de degradação — nunca uma exceção.
    adapter, adapter_reason = (
        embeddings_adapter_or_reason()
        if runtime_settings.real_providers_enabled
        else (None, PROVIDERS_DISABLED_REASON)
    )
    application.state.embeddings_adapter = adapter
    application.state.embeddings_unavailable_reason = adapter_reason

    @application.middleware("http")
    async def request_correlation(request: Request, call_next: Any) -> Any:
        request_id = request.headers.get("X-Request-ID") or str(new_uuid7())
        request.state.request_id = request_id
        started_at = time.monotonic()
        response = await call_next(request)
        duration_ms = (time.monotonic() - started_at) * 1000
        response.headers["X-Request-ID"] = request_id
        # A rota é o TEMPLATE (`/v1/jobs/{job_id}/...`), nunca o path cru: o path resolvido
        # carrega UUID de job/tenant e viraria conteúdo em log. Sem rota casada (404 antes do
        # roteamento, ex. método inválido), não há `request.scope["route"]` — registramos um
        # rótulo fixo em vez do path.
        route = request.scope.get("route")
        route_path = route.path if route is not None else "unmatched"
        log_level = logging.WARNING if response.status_code >= 500 else logging.INFO
        _REQUEST_LOGGER.log(
            log_level,
            "request_completed",
            extra={
                "request_id": request_id,
                "method": request.method,
                "route": route_path,
                "status_code": response.status_code,
                "duration_ms": round(duration_ms, 3),
            },
        )
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

    @application.exception_handler(RoundRefusal)
    async def round_refusal_handler(request: Request, exception: RoundRefusal) -> JSONResponse:
        """Precondição da rodada de medição no MESMO envelope das demais rotas.

        O núcleo de `valuation_rounds` levanta sem falar HTTP; a tradução acontece aqui, num
        lugar só, delegando ao handler de erro que já existe — duas rotas não podem responder
        formatos diferentes para a mesma causa.
        """
        return await problem_handler(request, _round_refusal_problem(exception))

    @application.exception_handler(ValuationValidationError)
    async def valuation_domain_handler(
        request: Request, exception: ValuationValidationError
    ) -> JSONResponse:
        """Invariante de `packages/valuation` como `DOMAIN_VALIDATION_FAILED` (ADR-0028 D4)."""
        return await problem_handler(request, _valuation_domain_problem(exception))

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

    @application.get("/v1/me", response_model=MeResponse, tags=["meta"])
    async def me(principal: AuthenticatedPrincipal) -> MeResponse:
        """A SPA descobre quem é o principal autenticado. Exige só autenticação — nenhum
        papel — e nunca devolve claims brutos ou o token: só o que o `Principal` já
        expõe (subject, tenant, roles), a mesma superfície usada nas decisões de
        autorização.

        `journeys` sai daqui já resolvido pelas três perguntas da F-034 — ambiente, tenant
        e papel — porque decisão de disponibilidade não é tomada no navegador. A tela
        esconde o que não está na lista; quem autoriza continua sendo o servidor, e a URL
        direta segue recusada pelo portão das rotas.
        """
        availability = runtime_settings.journeys.as_mapping()
        entitled = _entitled_journeys(
            runtime_database,
            tenant_id=principal.tenant_id,
            journeys=pilot_journeys(availability),
        )
        return MeResponse(
            subject=principal.subject,
            tenant_id=principal.tenant_id,
            roles=sorted(principal.roles),
            journeys=list(
                resolve_journeys(
                    availability=availability, entitled=entitled, roles=principal.roles
                )
            ),
        )

    @application.get(
        "/v1/platform/tenants",
        response_model=PlatformTenantListResponse,
        tags=["platform"],
    )
    async def list_platform_tenants(
        principal: AuthenticatedPrincipal,
        session: DatabaseSession,
    ) -> PlatformTenantListResponse:
        _require_platform_operator(principal)
        tenant_ids = _all_known_tenant_ids(session)
        entitlements: dict[str, TenantAiProcessingEntitlementRecord] = {}
        if tenant_ids:
            entitlements = {
                record.tenant_id: record
                for record in session.scalars(
                    select(TenantAiProcessingEntitlementRecord).where(
                        TenantAiProcessingEntitlementRecord.tenant_id.in_(tenant_ids)
                    )
                )
            }
        return PlatformTenantListResponse(
            tenants=[
                _platform_tenant_response(tenant_id, entitlements.get(tenant_id))
                for tenant_id in tenant_ids
            ]
        )

    @application.get(
        "/v1/platform/tenants/{tenant_id}/ai-processing-entitlement",
        response_model=PlatformTenantResponse,
        tags=["platform"],
    )
    async def get_ai_processing_entitlement(
        tenant_id: str,
        principal: AuthenticatedPrincipal,
        session: DatabaseSession,
    ) -> PlatformTenantResponse:
        _require_platform_operator(principal)
        entitlement = session.scalar(
            select(TenantAiProcessingEntitlementRecord).where(
                TenantAiProcessingEntitlementRecord.tenant_id == tenant_id
            )
        )
        return _platform_tenant_response(tenant_id, entitlement)

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

    @application.get(
        "/v1/platform/journeys",
        response_model=PlatformJourneyListResponse,
        tags=["platform"],
    )
    async def list_platform_journeys(
        principal: AuthenticatedPrincipal,
        session: DatabaseSession,
    ) -> PlatformJourneyListResponse:
        """Estado de cada jornada neste ambiente e toda autorização já concedida (F-034).

        Duas leituras num lugar só porque a tela responde uma pergunta só: quais jornadas
        existem para cada cliente. O estado vem da configuração e é **somente leitura**; as
        autorizações vêm da tabela do entitlement.

        A listagem traz apenas os pares (tenant, jornada) que TÊM registro — inclusive os
        revogados, que continuam na lista com `revoked_at`. Listar todo tenant conhecido
        (como faz `/v1/platform/tenants`) é questão em aberto do pacote de design aprovado,
        e portanto não é decidida aqui em silêncio.
        """
        _require_platform_operator(principal)
        availability = runtime_settings.journeys.as_mapping()
        records = session.scalars(select(TenantJourneyEntitlementRecord)).all()
        # Ordenação em Python, como em `_all_known_tenant_ids`: SQLite (testes) e
        # PostgreSQL (hospedado) não ordenam texto do mesmo jeito, e a tela lê a ordem.
        ordered = sorted(records, key=lambda record: (record.tenant_id, record.journey))
        return PlatformJourneyListResponse(
            journeys=[
                JourneyAvailabilityResponse(journey=journey, state=availability[journey])
                for journey in JOURNEYS
            ],
            entitlements=[_journey_entitlement_response(record) for record in ordered],
        )

    @application.put(
        "/v1/platform/tenants/{tenant_id}/journey-entitlements/{journey}",
        response_model=JourneyEntitlementResponse,
        tags=["platform"],
    )
    async def set_journey_entitlement(
        tenant_id: str,
        journey: Journey,
        payload: SetJourneyEntitlementRequest,
        request: Request,
        principal: AuthenticatedPrincipal,
        session: DatabaseSession,
        idempotency_key: Annotated[str, Depends(_require_idempotency)],
    ) -> JourneyEntitlementResponse:
        """Concede ou revoga o acesso de um tenant a uma jornada, por ato nominal (F-034).

        O tenant ALVO vem da rota e só `platform_operator` chega aqui; o `tenant_id` do JWT
        de quem chama não decide nada nesta rota, exatamente como no entitlement de IA.
        """
        _require_platform_operator(principal)
        state = runtime_settings.journeys.state_of(journey)
        if payload.enabled and state != "pilot":
            # Recusa ANTES de qualquer escrita. Autorizar um cliente numa jornada que já
            # existe para todos, ou que não existe neste ambiente, não teria efeito nenhum
            # hoje — e o registro criado passaria a valer sozinho, sem ato novo, se o
            # estado virasse `pilot` depois.
            #
            # Revogar segue permitido em QUALQUER estado, de propósito: é o que permite
            # encerrar uma autorização criada durante o piloto depois que a jornada foi
            # liberada, em vez de deixá-la ativa esperando o próximo piloto.
            raise _problem(
                "JOURNEY_NOT_IN_PILOT",
                status.HTTP_409_CONFLICT,
                f"A jornada {journey} não está em piloto neste ambiente; autorizar um "
                "cliente nela não teria efeito.",
                {"journey": journey, "state": state},
            )
        if payload.enabled and payload.agreement_reference is None:
            raise _problem(
                "AGREEMENT_REFERENCE_REQUIRED",
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "Autorizar um cliente numa jornada em piloto exige a referência lógica "
                "do contrato.",
            )
        operation = f"platform.journey-entitlement:{tenant_id}:{journey}"
        request_hash = _request_hash(payload)
        existing_response = _idempotent_response(
            session,
            principal=principal,
            operation=operation,
            key=idempotency_key,
            request_hash=request_hash,
        )
        if existing_response is not None:
            return JourneyEntitlementResponse.model_validate(existing_response)

        now = datetime.now(UTC)
        entitlement = session.scalar(
            select(TenantJourneyEntitlementRecord).where(
                TenantJourneyEntitlementRecord.tenant_id == tenant_id,
                TenantJourneyEntitlementRecord.journey == journey,
            )
        )
        if entitlement is None:
            if not payload.enabled:
                raise _problem(
                    "NOT_FOUND",
                    status.HTTP_404_NOT_FOUND,
                    "Autorização de jornada não encontrada para o tenant.",
                )
            entitlement = TenantJourneyEntitlementRecord(
                id=str(new_uuid7()),
                tenant_id=tenant_id,
                journey=journey,
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
            # Revogar NÃO apaga: o registro fica, com o contrato e o autor do ato original,
            # e ganha a data da revogação. É a trilha que a tela mostra.
            entitlement.status = "REVOKED"
            entitlement.revoked_at = now

        response = _journey_entitlement_response(entitlement)
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
                "JOURNEY_ENTITLEMENT_GRANTED" if payload.enabled else "JOURNEY_ENTITLEMENT_REVOKED"
            ),
            resource_type="tenant_journey_entitlement",
            resource_id=entitlement.id,
            request_id=request.state.request_id,
            tenant_id=tenant_id,
        )
        session.commit()
        return response

    @application.post(
        "/v1/platform/reference-catalogs/presign",
        response_model=PresignUploadResponse,
        tags=["platform"],
    )
    async def presign_reference_catalog(
        payload: PresignReferenceCatalogRequest,
        request: Request,
        principal: AuthenticatedPrincipal,
        session: DatabaseSession,
        idempotency_key: Annotated[str, Depends(_require_idempotency)],
    ) -> PresignUploadResponse:
        """Presign do acervo, para publicar não depender da jornada do croqui (F-037 escopo 7).

        O portão de disponibilidade da F-034 é dependência do router e `/v1/uploads` é do
        croqui (`journeys.py`): com essa jornada em `disabled`, o operador que subisse o
        `catalog.json` pelo presign de lá receberia `403 JOURNEY_UNAVAILABLE`, e o acervo
        ficaria sem como ser alimentado — justo o módulo que a F-034 nasceu para poder
        desligar. `/v1/platform` já está declarado fora de jornada, então a mesma sequência
        sob este prefixo atravessa. Nada em `journeys.py` muda: tirar o presign do croqui do
        portão resolveria um caso de plataforma enfraquecendo o mecanismo inteiro.

        É `presign_upload` na íntegra — mesma idempotência, mesmo `UploadRecord` sob
        `tenants/{tenant_id}/uploads/`, mesmo checksum, mesmo header por perfil de storage e
        mesma auditoria (`UPLOAD_PRESIGNED`: o fato é que este principal assinou um upload; o
        ato de publicar é auditado à parte) — com duas diferenças, e só elas:

        - **papel antes de qualquer coisa**: `platform_operator`, como nas demais rotas de
          plataforma. Quem não o tem recebe `403` sem que nada seja consultado ou gravado;
        - **tipo fixo** em `application/json`: o acervo publica catálogo normalizado e nada
          mais, então o tipo não vem do corpo.
        """
        _require_platform_operator(principal)
        operation = "platform.reference-catalogs.presign"
        request_hash = _request_hash(payload)
        existing = _idempotent_response(
            session,
            principal=principal,
            operation=operation,
            key=idempotency_key,
            request_hash=request_hash,
        )
        if existing is not None:
            return PresignUploadResponse.model_validate(existing)
        record, response = _presign_tenant_upload(
            application,
            principal=principal,
            filename=payload.filename,
            content_type=CATALOG_CONTENT_TYPE,
            size_bytes=payload.size_bytes,
            sha256=payload.sha256,
            storage_flavor=runtime_settings.storage_flavor,
        )
        session.add(record)
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
            action="UPLOAD_PRESIGNED",
            resource_type="upload",
            resource_id=str(response.upload_id),
            request_id=request.state.request_id,
        )
        session.commit()
        return response

    @application.post(
        "/v1/platform/reference-catalogs",
        response_model=ReferenceCatalogResponse,
        status_code=status.HTTP_201_CREATED,
        tags=["platform"],
    )
    async def publish_reference_catalog(
        payload: PublishReferenceCatalogRequest,
        request: Request,
        principal: AuthenticatedPrincipal,
        session: DatabaseSession,
        idempotency_key: Annotated[str, Depends(_require_idempotency)],
    ) -> ReferenceCatalogResponse:
        """Publica uma tabela de referência para TODOS os tenants (F-037, ADR-0047).

        O que sobe é o `catalog.json` já normalizado pelo CLI (`import-catalog`,
        `import-sinapi`, `import-sicro`), por `POST /v1/platform/reference-catalogs/presign`.
        O servidor não importa `.xlsx` nem `.DBF` (decisão 9): trazer leitor de formato
        binário sobre arquivo externo para o request path seria superfície de ataque nova sem
        valor de produto correspondente.

        A publicação **não exige** que o upload tenha vindo daquele presign: qualquer upload
        JSON do tenant do operador serve. Exigir a procedência do presign seria uma trava a
        mais sem fronteira nova — quem sobe e quem publica são a mesma pessoa, com o mesmo
        papel, e `_require_valuation_upload` já recusa upload de outro tenant, tipo diferente
        de `application/json` e objeto que não casa com o que foi declarado. O que decide o
        que entra no acervo é o conteúdo lido do arquivo, não por qual porta ele subiu.

        Três recusas, todas ANTES de qualquer escrita — no store ou no banco:

        - **papel**, antes de qualquer lookup: quem não é `platform_operator` recebe `403` e
          não descobre o que existe no acervo;
        - **origem que a plataforma não pode distribuir** (`emop`, paga, e `composition`, do
          cliente): `422 REFERENCE_CATALOG_ORIGIN_NOT_PUBLISHABLE`. As duas continuam
          entrando pelo upload de quem tem a licença;
        - **conteúdo já publicado**: `409 REFERENCE_CATALOG_ALREADY_PUBLISHED`. Publicação é
          imutável e endereçada por digest (decisão 3) — data-base nova tem conteúdo novo,
          logo entrada nova, e a anterior continua existindo porque uma rodada antiga ainda
          a referencia.

        O objeto é gravado ANTES do `commit`: linha que aponta para objeto inexistente seria
        uma escolha oferecida na tela que falharia na instalação, enquanto objeto sem linha é
        um arquivo endereçado por conteúdo que ninguém referencia — o mesmo que a próxima
        publicação do mesmo digest reescreveria byte a byte.
        """
        _require_platform_operator(principal)
        operation = "platform.reference-catalogs"
        request_hash = _request_hash(payload)
        existing_response = _idempotent_response(
            session,
            principal=principal,
            operation=operation,
            key=idempotency_key,
            request_hash=request_hash,
        )
        if existing_response is not None:
            return ReferenceCatalogResponse.model_validate(existing_response)

        upload = _require_valuation_upload(
            session,
            application,
            upload_id=payload.upload_id,
            principal=principal,
            content_type=CATALOG_CONTENT_TYPE,
            storage_flavor=runtime_settings.storage_flavor,
        )
        body, catalog = _read_catalog(application, upload)
        if catalog.origin not in PUBLISHABLE_ORIGINS:
            raise _problem(
                "REFERENCE_CATALOG_ORIGIN_NOT_PUBLISHABLE",
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "A plataforma não distribui tabela desta origem; ela entra pelo upload de "
                "quem tem a licença dela.",
                {"origin": catalog.origin.value},
            )
        object_sha256 = upload.sha256.lower()
        published = session.scalar(
            select(ReferenceCatalogRecord).where(
                ReferenceCatalogRecord.object_sha256 == object_sha256
            )
        )
        if published is not None:
            raise _problem(
                "REFERENCE_CATALOG_ALREADY_PUBLISHED",
                status.HTTP_409_CONFLICT,
                "Este conteúdo já está no acervo; publicação é imutável e uma data-base "
                "nova é entrada nova.",
                {"reference_catalog_id": published.id},
            )

        object_key = reference_catalog_key(object_sha256=object_sha256)
        application.state.artifact_store.write_object(
            object_key=object_key, body=body, content_type=CATALOG_CONTENT_TYPE
        )
        record = ReferenceCatalogRecord(
            id=str(new_uuid7()),
            display_name=payload.display_name,
            # Origem, data-base, digest da fonte e contagem vêm de DENTRO do arquivo: o
            # rótulo não pode discordar do conteúdo, e um catálogo publicado com a data-base
            # errada mudaria o preço de todo tenant que o escolhesse.
            origin=catalog.origin.value,
            reference_month=catalog.reference_month,
            object_sha256=object_sha256,
            source_sha256=catalog.source_sha256,
            entry_count=len(catalog.entries),
            object_key=object_key,
            status=STATUS_AVAILABLE,
            published_by=principal.subject,
            published_at=datetime.now(UTC),
            withdrawn_at=None,
        )
        session.add(record)
        upload.status = "VERIFIED"
        response = _reference_catalog_response(record)
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
            action="REFERENCE_CATALOG_PUBLISHED",
            resource_type="reference_catalog",
            resource_id=record.id,
            request_id=request.state.request_id,
            # Sem tenant alvo: o ato vale para todos, e o `tenant_id` gravado é o do
            # OPERADOR (decisão 11). Os detalhes dizem QUAL documento passou a valer para
            # todos, que é o que a linha de auditoria precisaria de um join para saber.
            details={
                "reference_catalog_id": record.id,
                "origin": record.origin,
                "reference_month": record.reference_month,
            },
        )
        session.commit()
        return response

    @application.get(
        "/v1/platform/reference-catalogs",
        response_model=ReferenceCatalogListResponse,
        tags=["platform"],
    )
    async def list_reference_catalogs(
        principal: AuthenticatedPrincipal,
        session: DatabaseSession,
    ) -> ReferenceCatalogListResponse:
        """O acervo INTEIRO, inclusive o que está fora de circulação.

        Leitura sem `Idempotency-Key` e sem auditoria, como as demais listagens de
        plataforma. O que foi retirado continua na lista, com `withdrawn_at` carimbado:
        sumir com a linha apagaria a trilha do que houve — e a rodada que o referencia
        continua funcionando, então o registro precisa continuar legível.

        Ordenação em Python, como em `_all_known_tenant_ids`: SQLite (testes) e PostgreSQL
        (hospedado) não ordenam texto do mesmo jeito, e a tela lê a ordem. O `id` fecha o
        critério porque é UUIDv7 — duas publicações da mesma origem e data-base saem na
        ordem em que foram publicadas.
        """
        _require_platform_operator(principal)
        records = session.scalars(select(ReferenceCatalogRecord)).all()
        ordered = sorted(
            records, key=lambda record: (record.origin, record.reference_month, record.id)
        )
        return ReferenceCatalogListResponse(
            catalogs=[_reference_catalog_response(record) for record in ordered]
        )

    @application.post(
        "/v1/platform/reference-catalogs/{reference_catalog_id}/withdraw",
        response_model=ReferenceCatalogResponse,
        tags=["platform"],
    )
    async def withdraw_reference_catalog(
        reference_catalog_id: UUID,
        request: Request,
        principal: AuthenticatedPrincipal,
        session: DatabaseSession,
        idempotency_key: Annotated[str, Depends(_require_idempotency)],
    ) -> ReferenceCatalogResponse:
        """Tira o catálogo de circulação: ele deixa de ser oferecido e **não** é apagado.

        Apagar quebraria toda rodada que já o referencia — o preço de uma linha de orçamento
        cita o digest da fonte, e uma fonte que sumiu do store deixaria de poder ser relida.
        Por isso o ato carimba `status` e `withdrawn_at`, e nada mais: a linha continua na
        listagem, o objeto continua no store, e o que muda é só o catálogo sair das escolhas
        novas.

        Sem corpo: o ato é inteiramente identificado pela rota. Retirar o que já está fora de
        circulação devolve o registro como está, sem recarimbar a data nem auditar de novo —
        a data verdadeira é a da retirada, não a da última vez que alguém repetiu o pedido.
        """
        _require_platform_operator(principal)
        operation = f"platform.reference-catalogs.withdraw:{reference_catalog_id}"
        request_hash = _request_hash(_PARAMETERLESS_COMMAND)
        existing_response = _idempotent_response(
            session,
            principal=principal,
            operation=operation,
            key=idempotency_key,
            request_hash=request_hash,
        )
        if existing_response is not None:
            return ReferenceCatalogResponse.model_validate(existing_response)

        record = session.get(ReferenceCatalogRecord, str(reference_catalog_id))
        if record is None:
            raise _problem(
                "NOT_FOUND", status.HTTP_404_NOT_FOUND, "Catálogo do acervo não encontrado."
            )
        already_withdrawn = record.status == STATUS_WITHDRAWN
        if not already_withdrawn:
            record.status = STATUS_WITHDRAWN
            record.withdrawn_at = datetime.now(UTC)
        response = _reference_catalog_response(record)
        _store_idempotent_response(
            session,
            principal=principal,
            operation=operation,
            key=idempotency_key,
            request_hash=request_hash,
            response=response,
        )
        if not already_withdrawn:
            _record_audit(
                session,
                principal=principal,
                action="REFERENCE_CATALOG_WITHDRAWN",
                resource_type="reference_catalog",
                resource_id=record.id,
                request_id=request.state.request_id,
                details={
                    "reference_catalog_id": record.id,
                    "origin": record.origin,
                    "reference_month": record.reference_month,
                },
            )
        session.commit()
        return response

    @application.post(
        "/v1/platform/reference-catalog-indexes/presign",
        response_model=PresignUploadResponse,
        tags=["platform"],
    )
    async def presign_reference_catalog_index(
        payload: PresignReferenceCatalogIndexRequest,
        request: Request,
        principal: AuthenticatedPrincipal,
        session: DatabaseSession,
        idempotency_key: Annotated[str, Depends(_require_idempotency)],
    ) -> PresignUploadResponse:
        """Presign do índice, irmão do presign do acervo e pelo mesmo motivo.

        Publicar índice não pode depender da jornada do croqui: `/v1/uploads` é do croqui e
        cai no portão de disponibilidade da F-034, então num ambiente com essa jornada
        `disabled` o operador da plataforma não teria como alimentar nem o acervo nem os
        índices dele. `/v1/platform` está declarado fora de jornada.

        É `presign_upload` na íntegra — mesma idempotência, mesmo `UploadRecord` sob
        `tenants/{tenant_id}/uploads/` do OPERADOR, mesmo checksum, mesmo header por perfil
        de storage e mesma auditoria (`UPLOAD_PRESIGNED`; publicar é ato auditado à parte).
        O objeto só sai do prefixo do operador quando a publicação o lê e o confere: assinar
        direto para dentro do prefixo do índice poria lá um arquivo que ninguém validou.
        """
        _require_platform_operator(principal)
        operation = "platform.reference-catalog-indexes.presign"
        request_hash = _request_hash(payload)
        existing = _idempotent_response(
            session,
            principal=principal,
            operation=operation,
            key=idempotency_key,
            request_hash=request_hash,
        )
        if existing is not None:
            return PresignUploadResponse.model_validate(existing)
        record, response = _presign_tenant_upload(
            application,
            principal=principal,
            filename=payload.filename,
            content_type=CATALOG_CONTENT_TYPE,
            size_bytes=payload.size_bytes,
            sha256=payload.sha256,
            storage_flavor=runtime_settings.storage_flavor,
        )
        session.add(record)
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
            action="UPLOAD_PRESIGNED",
            resource_type="upload",
            resource_id=str(response.upload_id),
            request_id=request.state.request_id,
        )
        session.commit()
        return response

    @application.post(
        "/v1/platform/reference-catalog-indexes",
        response_model=ReferenceCatalogIndexResponse,
        status_code=status.HTTP_201_CREATED,
        tags=["platform"],
    )
    async def publish_reference_catalog_index(
        payload: PublishReferenceCatalogIndexRequest,
        request: Request,
        principal: AuthenticatedPrincipal,
        session: DatabaseSession,
        idempotency_key: Annotated[str, Depends(_require_idempotency)],
    ) -> ReferenceCatalogIndexResponse:
        """Publica o índice de embeddings de um catálogo do acervo (F-041, ADR-0054).

        O que sobe é o `catalog-embeddings.json` construído pelo comando pago
        `index-catalog` do CLI. **O servidor lê o índice; nunca o constrói** (ADR-0054 D4):
        a construção continua onde um humano aperta o botão e paga a chamada, e aqui só
        entra desserialização validada por Pydantic. Isso honra a RAZÃO da decisão 9 do
        ADR-0047 — derivação pesada e paga fora do request path —, e não apenas a sua letra,
        que proíbe parser de planilha; um JSON de vetores de contrato fechado não é um.

        Cinco recusas, todas ANTES de qualquer escrita — no store ou no banco:

        - **papel**, antes de qualquer lookup: quem não é `platform_operator` recebe `403` e
          não descobre o que existe;
        - **tamanho**, antes de desserializar: `422 REFERENCE_CATALOG_INDEX_TOO_LARGE`, por
          extenso e com a causa nomeada — documento truncado desserializaria como JSON
          inválido e a causa verdadeira sumiria numa recusa de contrato;
        - **documento ilegível**: `422 REFERENCE_CATALOG_INDEX_UNREADABLE`, com o código de
          domínio nos detalhes e nada do conteúdo do arquivo;
        - **índice de outro catálogo**: `422 REFERENCE_CATALOG_INDEX_CATALOG_MISMATCH`. O
          `catalog_sha256` de dentro do documento tem de bater com o `source_sha256` da
          entrada do acervo citada — publicar índice de outro catálogo devolveria códigos
          que aquele catálogo nem tem;
        - **conteúdo já publicado**: `409 REFERENCE_CATALOG_INDEX_ALREADY_PUBLISHED`.
          Publicação é imutável e endereçada por digest — receita ou modelo novos têm digest
          novo, logo entrada nova, e a anterior continua existindo.

        O objeto é gravado ANTES do `commit`, pela mesma razão do acervo: linha apontando
        para objeto inexistente degradaria a busca com um índice que falha na leitura,
        enquanto objeto sem linha é um arquivo endereçado por conteúdo que ninguém
        referencia — o mesmo que a próxima publicação do mesmo digest reescreveria byte a
        byte.
        """
        _require_platform_operator(principal)
        operation = "platform.reference-catalog-indexes"
        request_hash = _request_hash(payload)
        existing_response = _idempotent_response(
            session,
            principal=principal,
            operation=operation,
            key=idempotency_key,
            request_hash=request_hash,
        )
        if existing_response is not None:
            return ReferenceCatalogIndexResponse.model_validate(existing_response)

        upload = _require_valuation_upload(
            session,
            application,
            upload_id=payload.upload_id,
            principal=principal,
            content_type=CATALOG_CONTENT_TYPE,
            storage_flavor=runtime_settings.storage_flavor,
        )
        # O teto ANTES de desserializar, e sobre o tamanho DECLARADO — que
        # `_require_valuation_upload` acabou de conferir contra o objeto realmente gravado.
        # Ler primeiro para medir depois carregaria no processo justamente o excesso que o
        # teto existe para manter fora dele.
        if upload.size_bytes > CATALOG_INDEX_MAX_BYTES:
            raise _problem(
                "REFERENCE_CATALOG_INDEX_TOO_LARGE",
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "O índice excede o limite de leitura da API e é recusado por inteiro.",
                {"max_bytes": CATALOG_INDEX_MAX_BYTES, "size_bytes": upload.size_bytes},
            )
        store: ArtifactStore = application.state.artifact_store
        try:
            body = read_index_document(store, object_key=upload.object_key)
            index = parse_index_document(body)
        except ValuationValidationError as error:
            # Só o código de domínio sai: a mensagem do pydantic pode carregar valores do
            # arquivo, e resposta de erro não é lugar de conteúdo de artefato.
            raise _problem(
                "REFERENCE_CATALOG_INDEX_UNREADABLE",
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "O índice enviado não pôde ser lido.",
                {"code": error.code},
            ) from error
        if hashlib.sha256(body).hexdigest() != upload.sha256.lower():
            raise _problem(
                "INVALID_UPLOAD",
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "Índice com integridade divergente do digest registrado.",
            )

        catalog_record = session.get(ReferenceCatalogRecord, str(payload.reference_catalog_id))
        if catalog_record is None:
            raise _problem(
                "NOT_FOUND", status.HTTP_404_NOT_FOUND, "Catálogo do acervo não encontrado."
            )
        if index.catalog_sha256 != catalog_record.source_sha256:
            raise _problem(
                "REFERENCE_CATALOG_INDEX_CATALOG_MISMATCH",
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "O índice foi construído sobre outro catálogo; ele não serve o que foi citado.",
                {
                    "reference_catalog_id": catalog_record.id,
                    "index_catalog_sha256": index.catalog_sha256,
                    "catalog_source_sha256": catalog_record.source_sha256,
                },
            )
        object_sha256 = upload.sha256.lower()
        published = session.scalar(
            select(ReferenceCatalogEmbeddingRecord).where(
                ReferenceCatalogEmbeddingRecord.object_sha256 == object_sha256
            )
        )
        if published is not None:
            raise _problem(
                "REFERENCE_CATALOG_INDEX_ALREADY_PUBLISHED",
                status.HTTP_409_CONFLICT,
                "Este índice já está publicado; publicação é imutável e um índice "
                "reconstruído é entrada nova.",
                {"reference_catalog_index_id": published.id},
            )

        object_key = reference_catalog_index_key(object_sha256=object_sha256)
        store.write_object(object_key=object_key, body=body, content_type=CATALOG_CONTENT_TYPE)
        record = ReferenceCatalogEmbeddingRecord(
            id=str(new_uuid7()),
            reference_catalog_id=catalog_record.id,
            # Tudo abaixo vem de DENTRO do documento: nada é digitado, e por isso nada pode
            # discordar do conteúdo que a leitura vai encontrar.
            catalog_source_sha256=index.catalog_sha256,
            text_recipe=index.text_recipe,
            provider=index.provider,
            model_id=index.model_id,
            dims=index.dims,
            code_count=len(index.codes),
            object_key=object_key,
            object_sha256=object_sha256,
            status=STATUS_AVAILABLE,
            published_by=principal.subject,
            published_at=datetime.now(UTC),
            withdrawn_at=None,
        )
        session.add(record)
        upload.status = "VERIFIED"
        response = _reference_catalog_index_response(record)
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
            action="REFERENCE_CATALOG_INDEX_PUBLISHED",
            resource_type="reference_catalog_index",
            resource_id=record.id,
            request_id=request.state.request_id,
            # Sem tenant alvo: o ato vale para todos, e o `tenant_id` gravado é o do
            # OPERADOR. Os detalhes dizem QUAL índice passou a valer, com a receita e o
            # modelo — que é o que decide se ele será aceito na amarração.
            details={
                "reference_catalog_index_id": record.id,
                "reference_catalog_id": record.reference_catalog_id,
                "text_recipe": record.text_recipe,
                "model_id": record.model_id,
            },
        )
        session.commit()
        return response

    @application.get(
        "/v1/platform/reference-catalog-indexes",
        response_model=ReferenceCatalogIndexListResponse,
        tags=["platform"],
    )
    async def list_reference_catalog_indexes(
        principal: AuthenticatedPrincipal,
        session: DatabaseSession,
    ) -> ReferenceCatalogIndexListResponse:
        """Todos os índices, inclusive os que saíram de circulação.

        Leitura sem `Idempotency-Key` e sem auditoria, como as demais listagens de
        plataforma. O que foi retirado continua na lista, com `withdrawn_at` carimbado.

        Ordenação em Python, como no acervo: SQLite (testes) e PostgreSQL (hospedado) não
        ordenam texto do mesmo jeito, e a tela lê a ordem. O `id` fecha o critério porque é
        UUIDv7 — dois índices do mesmo catálogo e da mesma receita saem na ordem em que
        foram publicados, que é a ordem em que a busca os prefere.
        """
        _require_platform_operator(principal)
        records = session.scalars(select(ReferenceCatalogEmbeddingRecord)).all()
        ordered = sorted(
            records,
            key=lambda record: (record.catalog_source_sha256, record.text_recipe, record.id),
        )
        return ReferenceCatalogIndexListResponse(
            indexes=[_reference_catalog_index_response(record) for record in ordered]
        )

    @application.post(
        "/v1/platform/reference-catalog-indexes/{reference_catalog_index_id}/withdraw",
        response_model=ReferenceCatalogIndexResponse,
        tags=["platform"],
    )
    async def withdraw_reference_catalog_index(
        reference_catalog_index_id: UUID,
        request: Request,
        principal: AuthenticatedPrincipal,
        session: DatabaseSession,
        idempotency_key: Annotated[str, Depends(_require_idempotency)],
    ) -> ReferenceCatalogIndexResponse:
        """Tira o índice de circulação: ele deixa de ser resolvido e **não** é apagado.

        Apagar seria perder a trilha de qual índice serviu uma shortlist já gravada — e a
        shortlist cita o digest do índice que a produziu. Por isso o ato carimba `status` e
        `withdrawn_at`, e nada mais: a linha continua na listagem, o objeto continua no
        store, e o que muda é a resolução deixar de encontrá-lo. A fonte volta a contribuir
        só com o braço léxico, que é estado normal e não erro (ADR-0054 D6).

        Sem corpo: o ato é inteiramente identificado pela rota. Retirar o que já está fora
        de circulação devolve o registro como está, sem recarimbar a data nem auditar de
        novo — a data verdadeira é a da retirada, não a da última repetição do pedido.
        """
        _require_platform_operator(principal)
        operation = f"platform.reference-catalog-indexes.withdraw:{reference_catalog_index_id}"
        request_hash = _request_hash(_PARAMETERLESS_COMMAND)
        existing_response = _idempotent_response(
            session,
            principal=principal,
            operation=operation,
            key=idempotency_key,
            request_hash=request_hash,
        )
        if existing_response is not None:
            return ReferenceCatalogIndexResponse.model_validate(existing_response)

        record = session.get(ReferenceCatalogEmbeddingRecord, str(reference_catalog_index_id))
        if record is None:
            raise _problem(
                "NOT_FOUND", status.HTTP_404_NOT_FOUND, "Índice publicado não encontrado."
            )
        already_withdrawn = record.status == STATUS_WITHDRAWN
        if not already_withdrawn:
            record.status = STATUS_WITHDRAWN
            record.withdrawn_at = datetime.now(UTC)
        response = _reference_catalog_index_response(record)
        _store_idempotent_response(
            session,
            principal=principal,
            operation=operation,
            key=idempotency_key,
            request_hash=request_hash,
            response=response,
        )
        if not already_withdrawn:
            _record_audit(
                session,
                principal=principal,
                action="REFERENCE_CATALOG_INDEX_WITHDRAWN",
                resource_type="reference_catalog_index",
                resource_id=record.id,
                request_id=request.state.request_id,
                details={
                    "reference_catalog_index_id": record.id,
                    "reference_catalog_id": record.reference_catalog_id,
                    "text_recipe": record.text_recipe,
                },
            )
        session.commit()
        return response

    # --- acervo de parcelas de canteiro da plataforma (F-042, ADR-0060) -------------------
    #
    # Molde da F-037, com uma diferença que é a decisão do ADR-0060: aqui a tabela tem
    # `tenant_id`, e ele é ANULÁVEL. Estas três rotas administram a metade de PLATAFORMA do
    # acervo (`tenant_id IS NULL`); a metade do tenant nasce em
    # `POST /v1/estimate-rounds/{round_id}/site-setup/kits`, e é a rodada que a lê.

    def _load_platform_site_setup_kit(session: Session, *, kit_id: UUID) -> SiteSetupKitRecord:
        """O acervo DE PLATAFORMA com este id, ou `404`.

        A cláusula `tenant_id IS NULL` não é redundante com o id: sem ela, um operador de
        plataforma poderia retirar de circulação o acervo que a orçamentista de um tenant
        autorou — que é dado do cliente, e não coisa que a plataforma administra.
        """
        record = session.scalar(
            select(SiteSetupKitRecord).where(
                SiteSetupKitRecord.id == str(kit_id),
                SiteSetupKitRecord.tenant_id.is_(None),
            )
        )
        if record is None:
            raise _problem(
                "NOT_FOUND",
                status.HTTP_404_NOT_FOUND,
                "Acervo de parcelas de canteiro não encontrado.",
            )
        return record

    @application.post(
        "/v1/platform/site-setup-kits",
        response_model=SiteSetupKitResponse,
        status_code=status.HTTP_201_CREATED,
        tags=["platform"],
    )
    async def publish_site_setup_kit(
        payload: PublishSiteSetupKitRequest,
        request: Request,
        principal: AuthenticatedPrincipal,
        session: DatabaseSession,
        idempotency_key: Annotated[str, Depends(_require_idempotency)],
    ) -> SiteSetupKitResponse:
        """Publica um acervo de parcelas de canteiro para TODOS os tenants (F-042, ADR-0060).

        O que entra é um `SiteSetupKit` cru, validado pelo domínio ANTES de virar linha:
        operando que é constante e referência ao mesmo tempo, código fora do formato de
        catálogo e parcela com id repetido recusam com `422 DOMAIN_VALIDATION_FAILED` e o
        código estável do domínio, nunca como erro de esquema do FastAPI.

        Duas recusas, as duas ANTES de qualquer escrita:

        - **papel**, antes de qualquer lookup: quem não é `platform_operator` recebe `403` e
          não descobre o que existe no acervo;
        - **mesma `(name, kit_version)` já publicada**: `409 SITE_SETUP_KIT_ALREADY_PUBLISHED`.
          Acervo é imutável — uma rodada que aplicou a versão `1.0.0` cita essa versão nas
          parcelas que materializou, e reescrever o conteúdo por baixo mudaria em silêncio o
          que aquelas parcelas dizem ter nascido de.

        Não há upload nem objeto no store: o acervo é receita curta, lida inteira em todo
        preview e em todo apply, e não há bytes de arquivo de terceiro a preservar.
        """
        _require_platform_operator(principal)
        operation = "platform.site-setup-kits"
        request_hash = _request_hash(payload)
        existing_response = _idempotent_response(
            session,
            principal=principal,
            operation=operation,
            key=idempotency_key,
            request_hash=request_hash,
        )
        if existing_response is not None:
            return SiteSetupKitResponse.model_validate(existing_response)

        kit = _validate_site_setup_kit(payload.document)
        published = session.scalar(
            select(SiteSetupKitRecord).where(
                SiteSetupKitRecord.tenant_id.is_(None),
                SiteSetupKitRecord.name == payload.name,
                SiteSetupKitRecord.kit_version == kit.version,
            )
        )
        if published is not None:
            raise site_setup_kits.already_published(payload.name, kit.version)

        document = kit.model_dump(mode="json")
        record = SiteSetupKitRecord(
            id=str(new_uuid7()),
            # A ausência é a origem: acervo de plataforma não tem dono (ADR-0060).
            tenant_id=None,
            name=payload.name,
            # Versão e rótulo de origem vêm de DENTRO do documento: o que se digita ao lado
            # do conteúdo pode discordar dele, e a versão é a chave do merge do apply.
            kit_version=kit.version,
            source_label=kit.source_label,
            document_json=document,
            document_sha256=site_setup_kits.kit_document_digest(document),
            withdrawn_at=None,
            created_by=principal.subject,
            created_at=datetime.now(UTC),
        )
        session.add(record)
        response = SiteSetupKitResponse.model_validate(
            site_setup_kits.kit_record_payload(record, kit)
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
            action="SITE_SETUP_KIT_PUBLISHED",
            resource_type="site_setup_kit",
            resource_id=record.id,
            request_id=request.state.request_id,
            # Sem tenant alvo: o ato vale para todos, e o `tenant_id` gravado é o do OPERADOR
            # (ADR-0047 decisão 11). Só identificador e versão — o nome de exibição é rótulo
            # digitado, e rótulo não entra em auditoria.
            details={"site_setup_kit_id": record.id, "kit_version": record.kit_version},
        )
        session.commit()
        return response

    @application.get(
        "/v1/platform/site-setup-kits",
        response_model=SiteSetupKitListResponse,
        tags=["platform"],
    )
    async def list_site_setup_kits(
        principal: AuthenticatedPrincipal,
        session: DatabaseSession,
    ) -> SiteSetupKitListResponse:
        """O acervo DE PLATAFORMA inteiro, inclusive o que está fora de circulação.

        `tenant_id IS NULL` é filtro, não otimização: o acervo que a orçamentista de um tenant
        autorou é dado dele, e listá-lo aqui daria a um operador de plataforma a lista dos
        acervos de todos os clientes. Quem lê acervo de tenant é a rodada daquele tenant.

        Leitura sem `Idempotency-Key` e sem auditoria, como as demais listagens de plataforma.
        O que foi retirado continua na lista, com `withdrawn_at` carimbado.

        Ordenação em Python, como em `list_reference_catalogs`: SQLite (testes) e PostgreSQL
        (hospedado) não ordenam texto do mesmo jeito, e a tela lê a ordem.
        """
        _require_platform_operator(principal)
        records = session.scalars(
            select(SiteSetupKitRecord).where(SiteSetupKitRecord.tenant_id.is_(None))
        ).all()
        ordered = sorted(records, key=lambda record: (record.name, record.kit_version, record.id))
        return SiteSetupKitListResponse(
            kits=[
                SiteSetupKitResponse.model_validate(
                    site_setup_kits.kit_record_payload(record, site_setup_kits.load_kit(record))
                )
                for record in ordered
            ]
        )

    @application.post(
        "/v1/platform/site-setup-kits/{site_setup_kit_id}/withdraw",
        response_model=SiteSetupKitResponse,
        tags=["platform"],
    )
    async def withdraw_site_setup_kit(
        site_setup_kit_id: UUID,
        request: Request,
        principal: AuthenticatedPrincipal,
        session: DatabaseSession,
        idempotency_key: Annotated[str, Depends(_require_idempotency)],
    ) -> SiteSetupKitResponse:
        """Tira o acervo de circulação: ele deixa de ser oferecido e **não** é apagado.

        Apagar quebraria a leitura de toda rodada que já o aplicou — as parcelas materializadas
        citam a versão do acervo, e o registro é o que permite dizer de onde elas vieram. Por
        isso o ato carimba `withdrawn_at`, e nada mais.

        Sem corpo: o ato é inteiramente identificado pela rota. Retirar o que já está fora de
        circulação devolve o registro como está, sem recarimbar a data nem auditar de novo.
        """
        _require_platform_operator(principal)
        operation = f"platform.site-setup-kits.withdraw:{site_setup_kit_id}"
        request_hash = _request_hash(_PARAMETERLESS_COMMAND)
        existing_response = _idempotent_response(
            session,
            principal=principal,
            operation=operation,
            key=idempotency_key,
            request_hash=request_hash,
        )
        if existing_response is not None:
            return SiteSetupKitResponse.model_validate(existing_response)

        record = _load_platform_site_setup_kit(session, kit_id=site_setup_kit_id)
        already_withdrawn = record.withdrawn_at is not None
        if not already_withdrawn:
            record.withdrawn_at = datetime.now(UTC)
        response = SiteSetupKitResponse.model_validate(
            site_setup_kits.kit_record_payload(record, site_setup_kits.load_kit(record))
        )
        _store_idempotent_response(
            session,
            principal=principal,
            operation=operation,
            key=idempotency_key,
            request_hash=request_hash,
            response=response,
        )
        if not already_withdrawn:
            _record_audit(
                session,
                principal=principal,
                action="SITE_SETUP_KIT_WITHDRAWN",
                resource_type="site_setup_kit",
                resource_id=record.id,
                request_id=request.state.request_id,
                details={"site_setup_kit_id": record.id, "kit_version": record.kit_version},
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
        record, response = _presign_tenant_upload(
            application,
            principal=principal,
            filename=payload.filename,
            content_type=payload.content_type,
            size_bytes=payload.size_bytes,
            sha256=payload.sha256,
            storage_flavor=runtime_settings.storage_flavor,
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
            resource_id=str(response.upload_id),
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
        session.add(
            JobStageEventRecord(
                id=str(new_uuid7()),
                tenant_id=principal.tenant_id,
                job_id=str(job_id),
                from_stage=None,
                to_stage=job.stage,
                from_status=None,
                to_status=job.status,
                source="api",
                created_at=now,
            )
        )
        if entitlement is not None:
            session.add(
                AiProcessingAuthorizationRecord(
                    id=str(new_uuid7()),
                    tenant_id=principal.tenant_id,
                    job_id=str(job_id),
                    accepted_by=entitlement.authorized_by,
                    notice_version="contractual-entitlement-v1",
                    providers_json=["openai", "anthropic"],
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
        _record_domain_event(
            session,
            principal=principal,
            event_type=EVENT_JOB_CREATED,
            job_id=job_id,
            payload={"project_id": str(project_id), "stage": job.stage, "status": job.status},
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

    @application.get(
        "/v1/jobs/{job_id}/metrics", response_model=JobMetricsResponse, tags=["metrics"]
    )
    async def get_job_metrics(
        job_id: UUID,
        principal: AuthenticatedPrincipal,
        session: DatabaseSession,
    ) -> JobMetricsResponse:
        """Cycle time, ato humano e custo de IA do job, derivados do que já está gravado.

        Nada é calculado no worker nem persistido: é leitura sobre `job_stage_events`,
        `review_decisions`, `chat_turns` e o lineage do pacote de revisão corrente.

        O escopo de tenant é o mesmo das rotas vizinhas e mora no `where`: job de outro
        tenant não é "sem permissão", é inexistente (`404`), e responder `403` diria ao
        chamador que aquele id existe em algum lugar.
        """
        job = session.scalar(
            select(JobRecord).where(
                JobRecord.id == str(job_id), JobRecord.tenant_id == principal.tenant_id
            )
        )
        if job is None:
            raise _problem("NOT_FOUND", status.HTTP_404_NOT_FOUND, "Job não encontrado.")
        return JobMetricsResponse.model_validate(compute_job_metrics(session, job))

    @application.get("/v1/metrics/summary", response_model=MetricsSummaryResponse, tags=["metrics"])
    async def get_metrics_summary(
        principal: AuthenticatedPrincipal,
        session: DatabaseSession,
        period_from: Annotated[str | None, Query(alias="from")] = None,
        period_to: Annotated[str | None, Query(alias="to")] = None,
    ) -> MetricsSummaryResponse:
        """Agregado do tenant do JWT no período, recortado por `created_at`.

        Os limites chegam como TEXTO e são convertidos aqui, e não declarados como
        `datetime` no parâmetro, porque uma data malformada precisa sair como
        `application/problem+json` com código estável — a validação nativa do FastAPI
        responderia `422` no formato dela, fora do contrato de erro desta API.
        """
        try:
            period_start = parse_period_bound(period_from, field="from")
            period_end = parse_period_bound(period_to, field="to")
        except MetricsPeriodError as error:
            raise _problem(
                "INVALID_METRICS_PERIOD",
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "Período inválido: use instantes ISO 8601 (UTC quando sem fuso).",
            ) from error
        if period_start is not None and period_end is not None and period_start > period_end:
            raise _problem(
                "INVALID_METRICS_PERIOD",
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "Período inválido: `from` é posterior a `to`.",
            )
        return MetricsSummaryResponse.model_validate(
            compute_tenant_summary(
                session,
                tenant_id=principal.tenant_id,
                period_start=period_start,
                period_end=period_end,
            )
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
        request_hash = _request_hash(payload, exclude=TELEMETRY_PAYLOAD_FIELDS)
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
            declared_chains_json=current.declared_chains_json,
            **_carried_review_context(current),
            confidence_shadow_json=confidence_shadow_json(
                reviewed_packet, associations, current.declared_chains_json
            ),
            calibration_json=resolved.calibration_json,
            proposal_decisions_json=current.proposal_decisions_json,
            evidence_refs_json=current.evidence_refs_json,
            solver_request_json=current.solver_request_json,
            solver_blockers_json=resolved.blockers,
            required_blocker_codes_json=current.required_blocker_codes_json,
            required_criteria_texts_json=current.required_criteria_texts_json,
            # Touch time DESTE envio, e não o acumulado da folha: a revisão é a unidade
            # do ato, e somar o acumulado a cada lote contaria o mesmo tempo de novo.
            interaction_ms=payload.interaction_ms,
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
        # Contagens do LOTE desta request, e não do acumulado da revisão: o consumidor
        # soma os eventos para chegar ao acumulado, e reafirmar o total a cada lote o
        # faria contar duas vezes.
        _record_domain_event(
            session,
            principal=principal,
            event_type=EVENT_REVIEW_DECISIONS_RECORDED,
            job_id=job_id,
            payload={
                "review_version": next_review.version,
                "decisions_total": len(payload.decisions),
                "confirmed": sum(1 for item in payload.decisions if item.action == "confirm"),
                "corrected": sum(1 for item in payload.decisions if item.action == "correct"),
                "rejected": sum(1 for item in payload.decisions if item.action == "reject"),
                **_optional_interaction_ms(payload.interaction_ms),
            },
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
        request_hash = _request_hash(payload, exclude=TELEMETRY_PAYLOAD_FIELDS)
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
            declared_chains_json=current.declared_chains_json,
            **_carried_review_context(current),
            confidence_shadow_json=confidence_shadow_json(
                rectified_packet, associations, current.declared_chains_json
            ),
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
            # O touch time é do envio que criou ESTA revisão; o da revisão corrigida
            # ficou na revisão dela, e não é herdado nem somado aqui.
            interaction_ms=payload.interaction_ms,
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
        _record_domain_event(
            session,
            principal=principal,
            event_type=EVENT_REVIEW_RECTIFICATIONS_RECORDED,
            job_id=job_id,
            payload={
                "review_version": next_review.version,
                "rectifications_total": len(payload.rectifications),
                **_optional_interaction_ms(payload.interaction_ms),
            },
        )
        session.commit()
        return response

    @application.post(
        "/v1/jobs/{job_id}/review/chains",
        response_model=ReviewResponse,
        tags=["review"],
    )
    async def declare_review_chain(
        job_id: UUID,
        payload: ReviewChainCommand,
        request: Request,
        principal: AuthenticatedPrincipal,
        session: DatabaseSession,
        idempotency_key: Annotated[str, Depends(_require_idempotency)],
    ) -> ReviewResponse:
        """Declara (ou retrata) que estas parcelas partilham este total.

        O motor sugere; quem afirma é uma pessoa. Cadeia que NÃO fecha é declarável de
        propósito: o desencontro entre a soma e o total é exatamente o achado — falta um
        trecho na folha, ou uma das medidas está incompleta. Por isso nada aqui entra em
        `blockers`, e o export continua decidido pelo portão da cena.

        Como as vizinhas, cria uma revisão de leitura nova em vez de editar a corrente:
        declarar e retratar são atos humanos, e o histórico de cada um fica na revisão em
        que aconteceu.
        """
        reviewer_role = _reviewer_role(principal)
        job = session.scalar(
            select(JobRecord).where(
                JobRecord.id == str(job_id), JobRecord.tenant_id == principal.tenant_id
            )
        )
        if job is None:
            raise _problem("NOT_FOUND", status.HTTP_404_NOT_FOUND, "Job não encontrado.")
        operation = f"review.chains:{job_id}"
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
        declared_chains = [dict(item) for item in current.declared_chains_json]
        if payload.action == "declare":
            if payload.total_id is None:
                raise _problem(
                    "CHAIN_INVALID",
                    status.HTTP_422_UNPROCESSABLE_ENTITY,
                    "Declarar uma cadeia exige o total e pelo menos duas parcelas.",
                )
            try:
                # O resultado não é gravado: a cadeia é reconferida contra o pacote a cada
                # leitura. Aqui a conferência serve só para recusar cadeia que não existe.
                verify_chain(packet, total_id=payload.total_id, part_ids=list(payload.part_ids))
            except ChainVerificationError as error:
                raise _problem(
                    "CHAIN_INVALID", status.HTTP_422_UNPROCESSABLE_ENTITY, str(error)
                ) from error
            declared_at = datetime.now(UTC)
            declared_chains.append(
                {
                    "chain_id": _chain_id(
                        total_id=payload.total_id,
                        part_ids=payload.part_ids,
                        declared_by=principal.subject,
                        declared_at=declared_at,
                    ),
                    "total_id": payload.total_id,
                    "part_ids": list(payload.part_ids),
                    "declared_by": principal.subject,
                    "declared_role": reviewer_role,
                    "declared_at": declared_at.isoformat(),
                }
            )
            audit_action = "REVIEW_CHAIN_DECLARED"
        else:
            if payload.chain_id is None:
                raise _problem(
                    "CHAIN_INVALID",
                    status.HTTP_422_UNPROCESSABLE_ENTITY,
                    "Retratar uma cadeia exige o identificador dela.",
                )
            remaining = [item for item in declared_chains if item["chain_id"] != payload.chain_id]
            if len(remaining) == len(declared_chains):
                raise _problem(
                    "CHAIN_NOT_FOUND",
                    status.HTTP_404_NOT_FOUND,
                    "Cadeia declarada não encontrada nesta revisão.",
                )
            declared_chains = remaining
            audit_action = "REVIEW_CHAIN_RETRACTED"

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
            declared_chains_json=declared_chains,
            **_carried_review_context(current),
            # A cadeia declarada é sinal de confiança de leitura: declarar ou retratar
            # muda o shadow, então ele é recomputado sobre a lista NOVA.
            confidence_shadow_json=confidence_shadow_json(
                packet, AssociationSet.model_validate(current.associations_json), declared_chains
            ),
            calibration_json=current.calibration_json,
            proposal_decisions_json=current.proposal_decisions_json,
            # Declarar cadeia não decide leitura nem desenha nada: o aceite de traçado, a
            # cena e os blockers da revisão anterior seguem valendo, verbatim.
            trace_acceptance_json=current.trace_acceptance_json,
            evidence_refs_json=current.evidence_refs_json,
            solver_request_json=current.solver_request_json,
            solver_blockers_json=current.solver_blockers_json,
            required_blocker_codes_json=current.required_blocker_codes_json,
            required_criteria_texts_json=current.required_criteria_texts_json,
            scene_revision_id=current.scene_revision_id,
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
            action=audit_action,
            resource_type="review_revision",
            resource_id=next_review.id,
            request_id=request.state.request_id,
        )
        # `chains_total` é o total DECLARADO que sobrou depois do ato (a retração diminui),
        # e não quantas cadeias este ato mexeu: é o estado que o portal precisa refletir.
        _record_domain_event(
            session,
            principal=principal,
            event_type=EVENT_REVIEW_CHAINS_DECLARED,
            job_id=job_id,
            payload={
                "review_version": next_review.version,
                "action": payload.action,
                "chains_total": len(declared_chains),
            },
        )
        session.commit()
        return response

    @application.post(
        "/v1/jobs/{job_id}/review/witnesses",
        response_model=ReviewResponse,
        tags=["review"],
    )
    async def mutate_review_witnesses(
        job_id: UUID,
        payload: ReviewWitnessCommand,
        request: Request,
        principal: AuthenticatedPrincipal,
        session: DatabaseSession,
        idempotency_key: Annotated[str, Depends(_require_idempotency)],
    ) -> ReviewResponse:
        """Associa ou retrata observação de campo sem tocar cena, solver ou blockers."""
        _reviewer_role(principal)
        operation = f"review.field-witnesses:{job_id}"
        request_hash = _request_hash(payload)
        replay = _idempotent_response(
            session,
            principal=principal,
            operation=operation,
            key=idempotency_key,
            request_hash=request_hash,
        )
        if replay is not None:
            return ReviewResponse.model_validate(replay)
        job = _load_job(session, job_id=job_id, tenant_id=principal.tenant_id)
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
        witnesses = [dict(value) for value in current.field_witnesses_json]
        if payload.action == "associate":
            assert payload.reading_id is not None and payload.source is not None
            packet = ReviewPacket.model_validate(current.packet_json)
            reading = next(
                (item for item in packet.readings if item.id == payload.reading_id), None
            )
            if reading is None:
                raise _problem(
                    "FIELD_WITNESS_READING_NOT_FOUND",
                    status.HTTP_404_NOT_FOUND,
                    "Leitura da prancha não encontrada nesta revisão.",
                )
            reading_value_mm = _confirmed_reading_value_mm(reading)
            source_value_mm, survey_id = _resolve_field_witness_source(
                session, job=job, source=payload.source
            )
            if any(
                value.get("reading_id") == payload.reading_id
                and value.get("source_type") == payload.source.type
                and value.get("source_id") == payload.source.source_id
                and value.get("survey_id") == survey_id
                for value in witnesses
            ):
                raise _problem(
                    "FIELD_WITNESS_ALREADY_ASSOCIATED",
                    status.HTTP_409_CONFLICT,
                    "Esta testemunha já está associada à leitura.",
                )
            witness = FieldWitnessResponse(
                witness_id=new_uuid7(),
                reading_id=payload.reading_id,
                source_type=payload.source.type,
                source_id=payload.source.source_id,
                survey_id=survey_id,
                reading_value_mm=reading_value_mm,
                source_value_mm=source_value_mm,
                difference_mm=source_value_mm - reading_value_mm,
                associated_by=principal.subject,
                associated_at=datetime.now(UTC),
            )
            witnesses.append(witness.model_dump(mode="json"))
            audit_action = "FIELD_WITNESS_ASSOCIATED"
        else:
            assert payload.witness_id is not None
            remaining = [
                value for value in witnesses if value.get("witness_id") != str(payload.witness_id)
            ]
            if len(remaining) == len(witnesses):
                raise _problem(
                    "FIELD_WITNESS_NOT_FOUND",
                    status.HTTP_404_NOT_FOUND,
                    "Testemunha não encontrada nesta revisão.",
                )
            witnesses = remaining
            audit_action = "FIELD_WITNESS_RETRACTED"

        next_review = ReviewRevisionRecord(
            id=str(new_uuid7()),
            tenant_id=current.tenant_id,
            job_id=current.job_id,
            version=current.version + 1,
            parent_review_id=current.id,
            packet_json=current.packet_json,
            associations_json=current.associations_json,
            proposals_json=current.proposals_json,
            selected_associations_json=current.selected_associations_json,
            declared_chains_json=current.declared_chains_json,
            confidence_shadow_json=current.confidence_shadow_json,
            field_witnesses_json=witnesses,
            field_observations_json=current.field_observations_json,
            shape_corrections_json=current.shape_corrections_json,
            calibration_json=current.calibration_json,
            proposal_decisions_json=current.proposal_decisions_json,
            trace_acceptance_json=current.trace_acceptance_json,
            evidence_refs_json=current.evidence_refs_json,
            solver_request_json=current.solver_request_json,
            solver_blockers_json=current.solver_blockers_json,
            required_blocker_codes_json=current.required_blocker_codes_json,
            required_criteria_texts_json=current.required_criteria_texts_json,
            scene_revision_id=current.scene_revision_id,
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
            action=audit_action,
            resource_type="review_revision",
            resource_id=next_review.id,
            request_id=request.state.request_id,
        )
        session.commit()
        return response

    @application.post(
        "/v1/jobs/{job_id}/review/field-observations",
        response_model=ReviewResponse,
        tags=["review"],
    )
    async def mutate_review_field_observations(
        job_id: UUID,
        payload: FieldObservationCommand,
        request: Request,
        principal: AuthenticatedPrincipal,
        session: DatabaseSession,
        idempotency_key: Annotated[str, Depends(_require_idempotency)],
    ) -> ReviewResponse:
        """Registra ou descarta observação humana sobre a classificação, fora da cena."""
        _reviewer_role(principal)
        operation = f"review.field-observations:{job_id}:{payload.origin}:{payload.evidence_id}"
        request_hash = _request_hash(payload)
        replay = _idempotent_response(
            session,
            principal=principal,
            operation=operation,
            key=idempotency_key,
            request_hash=request_hash,
        )
        if replay is not None:
            return ReviewResponse.model_validate(replay)
        job = _load_job(session, job_id=job_id, tenant_id=principal.tenant_id)
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
        # Foto alvo escopada ao job; alheia ou inexistente é o mesmo 404.
        _load_field_photo_target(
            session, job=job, origin=payload.origin, evidence_id=payload.evidence_id
        )
        # A observação nasce de um rascunho de classificação: exige DRAFT com artefato.
        analysis = _field_analysis_state(
            session,
            tenant_id=job.tenant_id,
            job_id=job.id,
            origin=payload.origin,
            evidence_id=str(payload.evidence_id),
            task="classification",
        )
        document = (
            _read_field_analysis(
                application, object_key=analysis.artifact_key, tenant_id=job.tenant_id
            )
            if analysis is not None
            and analysis.status == "DRAFT"
            and analysis.artifact_key is not None
            else None
        )
        if analysis is None or analysis.status != "DRAFT" or document is None:
            raise _problem(
                "FIELD_OBSERVATION_DRAFT_NOT_FOUND",
                status.HTTP_409_CONFLICT,
                "Não há rascunho de classificação para esta foto.",
            )
        source = _field_observation_source(analysis, document)

        evidence_id = str(payload.evidence_id)
        observations = [dict(value) for value in current.field_observations_json]

        def _for_photo(entry: dict[str, Any]) -> bool:
            return entry.get("origin") == payload.origin and entry.get("evidence_id") == evidence_id

        now = datetime.now(UTC)
        if payload.action == "record":
            if payload.corrects_observation_id is None:
                if any(
                    entry.get("status") == "ACTIVE" and _for_photo(entry) for entry in observations
                ):
                    raise _problem(
                        "FIELD_OBSERVATION_ALREADY_RECORDED",
                        status.HTTP_409_CONFLICT,
                        "Esta foto já tem uma observação ativa.",
                    )
                audit_action = "FIELD_OBSERVATION_RECORDED"
            else:
                target = next(
                    (
                        entry
                        for entry in observations
                        if entry.get("observation_id") == str(payload.corrects_observation_id)
                        and entry.get("status") == "ACTIVE"
                        and _for_photo(entry)
                    ),
                    None,
                )
                if target is None:
                    raise _problem(
                        "FIELD_OBSERVATION_NOT_FOUND",
                        status.HTTP_404_NOT_FOUND,
                        "Observação a corrigir não encontrada nesta revisão.",
                    )
                target["status"] = "SUPERSEDED"
                audit_action = "FIELD_OBSERVATION_CORRECTED"
            observation = FieldObservationResponse(
                observation_id=new_uuid7(),
                origin=payload.origin,
                evidence_id=payload.evidence_id,
                status="ACTIVE",
                category=payload.category,
                description=payload.description,
                source=source,
                supersedes_observation_id=payload.corrects_observation_id,
                recorded_by=principal.subject,
                recorded_at=now,
            )
            observations.append(observation.model_dump(mode="json"))
        else:
            if any(
                entry.get("status") in {"ACTIVE", "DISMISSED"} and _for_photo(entry)
                for entry in observations
            ):
                raise _problem(
                    "FIELD_OBSERVATION_ALREADY_HANDLED",
                    status.HTTP_409_CONFLICT,
                    "O rascunho desta foto já foi registrado ou descartado.",
                )
            observation = FieldObservationResponse(
                observation_id=new_uuid7(),
                origin=payload.origin,
                evidence_id=payload.evidence_id,
                status="DISMISSED",
                category=None,
                description=None,
                source=source,
                supersedes_observation_id=None,
                recorded_by=principal.subject,
                recorded_at=now,
            )
            observations.append(observation.model_dump(mode="json"))
            audit_action = "FIELD_OBSERVATION_DISMISSED"

        next_review = ReviewRevisionRecord(
            id=str(new_uuid7()),
            tenant_id=current.tenant_id,
            job_id=current.job_id,
            version=current.version + 1,
            parent_review_id=current.id,
            packet_json=current.packet_json,
            associations_json=current.associations_json,
            proposals_json=current.proposals_json,
            selected_associations_json=current.selected_associations_json,
            declared_chains_json=current.declared_chains_json,
            confidence_shadow_json=current.confidence_shadow_json,
            field_witnesses_json=current.field_witnesses_json,
            field_observations_json=observations,
            shape_corrections_json=current.shape_corrections_json,
            calibration_json=current.calibration_json,
            proposal_decisions_json=current.proposal_decisions_json,
            trace_acceptance_json=current.trace_acceptance_json,
            evidence_refs_json=current.evidence_refs_json,
            solver_request_json=current.solver_request_json,
            solver_blockers_json=current.solver_blockers_json,
            required_blocker_codes_json=current.required_blocker_codes_json,
            required_criteria_texts_json=current.required_criteria_texts_json,
            scene_revision_id=current.scene_revision_id,
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
            action=audit_action,
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
            declared_chains_json=current.declared_chains_json,
            **_carried_review_context(current),
            confidence_shadow_json=_carried_confidence_shadow(current),
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
        # Só a versão: escala, rotação e âncoras descrevem o desenho do cliente e não têm
        # o que fazer num barramento externo.
        _record_domain_event(
            session,
            principal=principal,
            event_type=EVENT_REVIEW_CALIBRATION_SET,
            job_id=job_id,
            payload={"review_version": next_review.version},
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
            declared_chains_json=current.declared_chains_json,
            **_carried_review_context(current),
            confidence_shadow_json=_carried_confidence_shadow(current),
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
        _record_domain_event(
            session,
            principal=principal,
            event_type=EVENT_REVIEW_PROPOSALS_DECIDED,
            job_id=job_id,
            payload={
                "review_version": next_review.version,
                "proposals_total": 1,
                "accepted": 1 if payload.action == "accept" else 0,
                "rejected": 1 if payload.action == "reject" else 0,
            },
        )
        session.commit()
        return response

    @application.post(
        "/v1/jobs/{job_id}/review/proposals/corrections",
        response_model=ReviewResponse,
        tags=["review"],
    )
    async def correct_proposal_shape(
        job_id: UUID,
        payload: CorrectProposalShapeRequest,
        request: Request,
        principal: AuthenticatedPrincipal,
        session: DatabaseSession,
        idempotency_key: Annotated[str, Depends(_require_idempotency)],
    ) -> ReviewResponse:
        """Grava a correção humana de forma como proposta NOVA, derivada das observadas.

        A observação da máquina não é tocada: ela continua em `proposals_json`, com o
        `algorithm`, a pontuação e a proveniência dela. A correção vai para
        `shape_corrections_json`, num conjunto de `detector_version` próprio — é essa
        separação que preserva a comparação entre máquina e humano depois da correção
        (ADR-0050, decisões 1 e 4).

        Nada aqui promove precisão: a forma nasce `unresolved` e `export=false` por
        `Literal` do modelo, e o portão de exportação não é consultado nem alterado.
        """
        reviewer_role = _reviewer_role(principal)
        job = session.scalar(
            select(JobRecord).where(
                JobRecord.id == str(job_id), JobRecord.tenant_id == principal.tenant_id
            )
        )
        if job is None:
            raise _problem("NOT_FOUND", status.HTTP_404_NOT_FOUND, "Job não encontrado.")
        operation = f"review.shape-correction:{job_id}"
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
                "Existe uma cena mais recente para a correção.",
            )

        proposals = VisionProposalSet.model_validate(current.proposals_json)
        conhecidas = {proposal.id: proposal for proposal in proposals.proposals}
        desconhecidas = sorted(set(payload.derived_from) - set(conhecidas))
        if desconhecidas:
            raise _problem(
                "DOMAIN_VALIDATION_FAILED",
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "A correção deriva de proposta fora do snapshot da revisão.",
            )
        # Decisão registrada é imutável, e a tela já não oferece o ato sobre forma decidida.
        # A fronteira repete a regra porque quem chama a rota direto não passa pela tela.
        decididas = {
            str(decision.get("proposal_id")) for decision in (current.proposal_decisions_json or [])
        }
        if decididas & set(payload.derived_from):
            raise _problem(
                "PROPOSAL_ALREADY_DECIDED",
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "Proposta já decidida não recebe correção de forma.",
            )

        vertices = [PixelPoint(x=vertice.x, y=vertice.y) for vertice in payload.vertices]
        # Dois vértices são uma reta; três ou mais, uma polilinha. O tipo acompanha a
        # forma que a pessoa desenhou, e não o tipo da proposta de origem: unir dois
        # fragmentos retos é justamente o caso em que ele muda.
        geometry: PixelGeometryValue = (
            PixelLine(start=vertices[0], end=vertices[1])
            if len(vertices) == 2 and not payload.closed
            else PixelPolyline(points=vertices, closed=payload.closed)
        )
        correcoes = list((current.shape_corrections_json or {}).get("proposals", []))
        try:
            correcao = VisionProposal(
                id=_shape_correction_id(job_id, current.version, len(correcoes)),
                kind="line" if geometry.type == "line" else "contour",
                geometry=geometry,
                algorithm=HUMAN_SHAPE_CORRECTION_ALGORITHM,
                # Sem pontuação, e não `1.0`: para uma forma que uma pessoa desenhou não
                # existe número honesto de confiança de detector (ADR-0050, decisão 2).
                quality_score=None,
                derived_from=list(payload.derived_from),
            )
            conjunto = VisionProposalSet(
                dataset_id=proposals.dataset_id,
                page_number=proposals.page_number,
                image_sha256=proposals.image_sha256,
                image_width_px=proposals.image_width_px,
                image_height_px=proposals.image_height_px,
                detector_version="human-correction-v1",
                configured_limits={},
                limit_reached=[],
                proposals=[
                    *(VisionProposal.model_validate(item) for item in correcoes),
                    correcao,
                ],
                safety_notes=[
                    "Formas corrigidas por pessoa; as observações originais permanecem "
                    "no conjunto de propostas da revisão.",
                    "Correção humana não promove precisão: continua não resolvida e não "
                    "exportável até que uma calibração a torne aproximada.",
                    "Cada forma declara de quais propostas observadas ela derivou.",
                ],
            )
        except ValidationError as error:
            # O vocabulário do domínio viaja no corpo do erro; a fronteira não republica a
            # lista de invariantes de `VisionProposal` como código dela.
            raise _problem(
                "DOMAIN_VALIDATION_FAILED",
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "A forma corrigida não satisfaz o contrato de proposta.",
            ) from error

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
            declared_chains_json=current.declared_chains_json,
            **{
                **_carried_review_context(current),
                # O único campo que ESTE ato substitui.
                "shape_corrections_json": conjunto.model_dump(mode="json"),
            },
            confidence_shadow_json=_carried_confidence_shadow(current),
            calibration_json=current.calibration_json,
            proposal_decisions_json=current.proposal_decisions_json,
            trace_acceptance_json=current.trace_acceptance_json,
            evidence_refs_json=current.evidence_refs_json,
            solver_request_json=current.solver_request_json,
            solver_blockers_json=current.solver_blockers_json,
            required_blocker_codes_json=current.required_blocker_codes_json,
            required_criteria_texts_json=current.required_criteria_texts_json,
            scene_revision_id=current.scene_revision_id,
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
            action="PROPOSAL_SHAPE_CORRECTED",
            resource_type="review_revision",
            resource_id=next_review.id,
            request_id=request.state.request_id,
            details={
                "derived_from": len(payload.derived_from),
                "vertices": len(payload.vertices),
                "reviewer_role": reviewer_role,
            },
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
            declared_chains_json=current.declared_chains_json,
            **_carried_review_context(current),
            confidence_shadow_json=_carried_confidence_shadow(current),
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
        # `batch` é o que o lote REALMENTE decidiu (proposta já decidida antes não entra),
        # e não `payload.proposal_ids`: a contagem publicada precisa bater com as linhas de
        # `proposal_decisions` gravadas logo acima.
        _record_domain_event(
            session,
            principal=principal,
            event_type=EVENT_REVIEW_PROPOSALS_DECIDED,
            job_id=job_id,
            payload={
                "review_version": next_review.version,
                "proposals_total": len(batch),
                "accepted": len(batch) if payload.action == "accept" else 0,
                "rejected": len(batch) if payload.action == "reject" else 0,
            },
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
            declared_chains_json=current.declared_chains_json,
            **_carried_review_context(current),
            confidence_shadow_json=_carried_confidence_shadow(current),
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
            declared_chains_json=current.declared_chains_json,
            **_carried_review_context(current),
            confidence_shadow_json=_carried_confidence_shadow(current),
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
        # O PAPEL do aprovador, nunca o subject: quem aprovou é pessoa identificável, e o
        # barramento externo recebe a qualificação profissional do ato, não a identidade.
        _record_domain_event(
            session,
            principal=principal,
            event_type=EVENT_SCENE_APPROVED,
            job_id=job_id,
            payload={
                "scene_revision_id": str(approved_scene.id),
                "approved_by_role": reviewer_role,
            },
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

    # -- Medição de obra (ADR-0028) -----------------------------------------------------

    def _enqueue_plate_extraction(
        *, round_id: str, extraction_id: str, tenant_id: str, plate_ids: Sequence[str] = ()
    ) -> None:
        """Publica o comando com o intent já durável; falha de transporte é 503 repetível.

        Um comando POR folha (F-046): é o que dá a cada uma o seu claim atômico no worker e o
        que faz a folha que falha não levar as outras junto. `plate_ids` vazio publica o
        envelope de sempre, sem folha nomeada, que o worker resolve para a primeira — é o
        caminho da rota singular e da praça de uma folha.

        A recusa da fila continua sendo `503` repetível para o lote INTEIRO: com o intent já
        durável e o claim atômico do worker, repetir o mesmo comando reenfileira sem repagar
        nada — e uma folha publicada a mais é melhor do que uma folha que ninguém extrai.
        """
        queue: QueueAdapter = application.state.queue
        try:
            for plate_id in plate_ids or (None,):
                queue.enqueue_valuation_plate_extraction(
                    round_id=round_id,
                    extraction_id=extraction_id,
                    tenant_id=tenant_id,
                    plate_id=plate_id,
                )
        except QUEUE_TRANSPORT_ERRORS as error:
            raise _problem(
                "PROCESSING_UNAVAILABLE",
                status.HTTP_503_SERVICE_UNAVAILABLE,
                "Extração registrada; repita o mesmo comando para reenfileirar com segurança.",
            ) from error

    def _enqueue_takeoff_overlay_rerender(
        *, round_id: str, tenant_id: str, packet_sha256: str
    ) -> None:
        """Publica o re-render do overlay. Falha de transporte NÃO derruba a decisão.

        A diferença para `_enqueue_plate_extraction` é deliberada (ADR-0030): lá o
        enfileiramento É o ato, e sem fila não há extração nenhuma; aqui o ato é a decisão
        do orçamentista, que já está durável quando este comando é publicado. Traduzir a
        recusa da fila em `503` faria o cliente supor que a decisão não valeu e repeti-la —
        e a segunda tentativa recusaria o item como já revisado.

        O desfecho de uma publicação perdida é visível sem log: o overlay continua
        declarando o pacote antigo, ou seja, continua `stale` na rota que o serve.
        """
        queue: QueueAdapter = application.state.queue
        with suppress(*QUEUE_TRANSPORT_ERRORS):
            queue.enqueue_takeoff_overlay_rerender(
                round_id=round_id, tenant_id=tenant_id, packet_sha256=packet_sha256
            )

    def _takeoff_payload(
        record: ValuationRoundRecord,
        revision: ValuationRoundRevisionRecord | None,
        plate: ValuationRoundPlateRecord | None = None,
    ) -> dict[str, Any]:
        """Pacote de UMA folha da praça, com a âncora de cada item declarada, contagens e digest.

        Espelha o `/takeoff` do servidor de medição pelas MESMAS funções puras, com as
        chaves em inglês. O digest é o do documento guardado na revisão — não o desta
        resposta —, para que ele seja idêntico ao que o estado da rodada publica: é por
        esse valor que a tela sabe se o que ela tem na mão ainda é o pacote corrente.

        `plate=None` é a folha de sempre — a primeira —, e a resposta é a de sempre, campo por
        campo. Nenhuma chave nova entra aqui: quem precisa saber de qual folha o pacote é já
        lê `packet.plate_id`, que sempre esteve na resposta porque sempre esteve no pacote.
        """
        if plate is None:
            packet = require_takeoff_packet(revision)
            stored: Mapping[str, Any] = require_document(
                revision,
                "takeoff_packet_json",
                stage=STAGE_TAKEOFF,
                detail="a rodada ainda não tem pacote de takeoff publicado",
            )
            registration: Mapping[str, Any] | None = (
                None if revision is None else revision.takeoff_registration_json
            )
        else:
            packet = require_plate_packet(revision, plate)
            stored = plate_packet_document(revision, plate)
            registration = plate_registration(revision, plate)
        registered = registered_item_ids(registration)
        return {
            "round_id": record.id,
            "version": record.version,
            "packet": anchored_packet(packet, registered),
            "packet_sha256": document_digest(stored),
            "review_status": review_status(packet),
            **takeoff_counts(packet),
            **anchor_counts(packet, registered),
        }

    def _round_catalog(record: ValuationRoundRecord) -> PriceCatalog:
        """Catálogo instalado na rodada, decodificado uma vez por digest.

        O catálogo é imutável na rodada e o cache é chaveado pelo digest instalado, então
        duas rodadas com o mesmo catálogo compartilham a decodificação de propósito —
        conteúdo idêntico byte a byte por construção. Objeto sumido, divergente do digest ou
        ilegível recusa com `CATALOG_REQUIRED`: é falha de ambiente, não do ato.
        """
        return load_catalog(
            application.state.artifact_store, record, cache=application.state.catalog_cache
        )

    def _semantic_arms(
        session: Session, principal: Principal, cascade: Sequence[PriceCatalog]
    ) -> list[SemanticArm]:
        """Os braços semânticos do RECOMPUTE, um por fonte, com o motivo de cada ausência.

        Chamado **só** pelos dois recomputes (ADR-0054 D7). O `GET` da shortlist não passa
        por aqui, e é isso que preserva a invariante de que ler não paga: quem não monta
        braço não embute rótulo nenhum.

        A ordem das perguntas é a do custo crescente. Primeiro o que não sai do processo — o
        contrato do tenant e a existência da via de embeddings —, e só depois o banco e o
        object store, que é onde o índice publicado é procurado. Sem via de embeddings não
        adianta achar índice: o braço não conseguiria embutir os rótulos, e a consulta teria
        sido gasta para produzir a mesma nota.

        Nenhum desfecho daqui recusa o ato: todos viram nota, inclusive o entitlement
        ausente (D8).
        """
        reason = _ai_entitlement_reason(
            session,
            principal,
            real_providers_enabled=runtime_settings.real_providers_enabled,
        ) or cast(str | None, application.state.embeddings_unavailable_reason)
        return resolve_cascade_arms(
            session,
            application.state.artifact_store,
            cascade=cascade,
            cache=application.state.semantic_index_cache,
            adapter=application.state.embeddings_adapter,
            unavailable_reason=reason,
        )

    def _suggestions_payload(
        record: ValuationRoundRecord,
        *,
        document: Mapping[str, Any],
        suggestions: CodeSuggestionSet,
        computed: bool,
        notes: list[str],
    ) -> dict[str, Any]:
        """Shortlist como a tela a recebe, com o digest do que está GRAVADO na revisão.

        `computed` distingue a shortlist recém-calculada da que já estava lá, e `matching` é
        derivado do `suggester_version` do próprio conjunto (`matching_of`): assim a resposta
        continua verdadeira quando ela vem do artefato gravado por outra sessão — inclusive
        uma que tinha índice semântico e esta não tem.
        """
        return {
            "round_id": record.id,
            "version": record.version,
            "suggestions": suggestions.model_dump(mode="json"),
            "suggestions_sha256": document_digest(document),
            "computed": computed,
            "matching": matching_of(suggestions),
            "semantic_notes": notes,
        }

    def _resolve_code_plate(
        session: Session,
        record: ValuationRoundRecord,
        principal: AuthenticatedPrincipal,
        plate_id: str | None,
    ) -> ValuationRoundPlateRecord | None:
        """A folha da praça que a etapa de código deste ato toca, ou `None` para a primeira.

        `None` é o caminho de sempre, e ele nem carrega a praça: a rodada de uma folha não
        passa a fazer uma query a mais só porque a praça passou a existir (F-046 T4d). Folha
        nomeada que não é desta praça é `404 ROUND_PLATE_NOT_FOUND`, pela resolução única.
        """
        if plate_id is None:
            return None
        plates = round_plates(session, round_id=record.id, tenant_id=principal.tenant_id)
        return resolve_plate(plates, plate_id)

    def _packet_for_code_plate(
        revision: ValuationRoundRevisionRecord | None,
        plate: ValuationRoundPlateRecord | None,
    ) -> TakeoffPacket:
        """O pacote contra o qual a decisão de código é aplicada — recusa por recusa, o de sempre.

        Sem folha nomeada, a recusa é `require_takeoff_packet` ("a rodada ainda não tem pacote
        de takeoff publicado"); com folha, é a da folha. As duas são `ROUND_STAGE_NOT_READY` na
        etapa `takeoff`, e nenhuma delas passa a existir onde não existia.
        """
        if plate is None:
            return require_takeoff_packet(revision)
        return require_plate_packet(revision, plate)

    def _assignments_payload(
        record: ValuationRoundRecord,
        *,
        packet: TakeoffPacket,
        assignments: CodeAssignmentSet | None,
        document: Mapping[str, Any] | None,
    ) -> dict[str, Any]:
        """Decisões de código da rodada e o que ainda falta decidir.

        Conjunto inexistente **não** é erro: a rodada com takeoff revisado e nenhuma decisão
        de código é o estado normal de quem acabou de chegar nesta etapa, e é `pending_items`
        que diz o que ela tem pela frente. Zero é informação: as contagens sempre saem.

        `plate_id` sai do PACOTE, e não do conjunto: a folha continua declarada quando ainda
        não há decisão nenhuma nela, que é justamente o estado em que a tela mais precisa saber
        de qual prancha esta etapa está falando (F-046 T4d).
        """
        return {
            "round_id": record.id,
            "version": record.version,
            "plate_id": packet.plate_id,
            "assignments": None if assignments is None else assignments.model_dump(mode="json"),
            "assignments_sha256": None if document is None else document_digest(document),
            "confirmed": 0 if assignments is None else count_status(assignments, "confirmed"),
            "rejected": 0 if assignments is None else count_status(assignments, "rejected"),
            # `confirmed` conta PARES e `closed` conta ELEMENTOS: sob pacote os dois
            # divergem, e é `closed` que responde "quanto já ficou pronto".
            "closed": 0 if assignments is None else count_closed(assignments),
            "pending_items": [
                item_payload(item) for item in pending_code_items(packet, assignments)
            ],
        }

    def _bulletin_payload(
        record: ValuationRoundRecord,
        revision: ValuationRoundRevisionRecord | None,
        plates: Sequence[ValuationRoundPlateRecord],
        *,
        document: Mapping[str, Any],
        valuation: Valuation,
    ) -> dict[str, Any]:
        """Boletim como a tela o recebe, com o digest do que está GRAVADO na revisão.

        `total_amount` sai como TEXTO porque dinheiro é `Decimal` neste contexto
        (ADR-0016): serializá-lo como número de JSON devolveria ao cliente um binário
        aproximado do centavo que o `TRUNC(x,2)` do domínio acabou de fixar. O digest é o do
        documento guardado — não o desta resposta —, para ser idêntico ao que o estado da
        rodada publica.

        O bloco de aprovação é derivado da medição REVALIDADA que a rota já tem em mãos, e
        não relido da revisão: as duas leituras responderiam a mesma coisa no caminho feliz,
        e usar a que a rota acabou de validar é o que faz a resposta do ato de aprovar já
        sair com a aprovação que ele mesmo escreveu.

        A URL assinada da planilha **não** entra aqui, pelo mesmo motivo de
        `_estimate_payload`: esta forma é a que o registro de idempotência guarda no banco, e
        gravar URL assinada seria persistir credencial de leitura fora de um cofre. Ela sai
        só no `GET`, montada na hora.

        `consolidation` é a linha por CÓDIGO somando as folhas da praça (F-046 T4e) — o
        número que a PLANILHA GERAL entrega à prefeitura e que, até aqui, só existia dentro
        do `.xlsx`. A resposta trazia o total da praça e o total de cada folha; a praça de N
        folhas em que o mesmo código aparece em duas delas ficava sem o único total que a
        prefeitura lê. Quem deriva é `workbook_writer.consolidate_by_code`, a MESMA função
        que planeja a coluna corrente da GERAL: derivá-la aqui de novo seria uma segunda
        verdade, e a tela somar as folhas no navegador seria uma terceira.

        `consolidation_drifts` é a deriva declarada do ADR-0062 chegando a quem confere.
        Ela sai daqui, e não de `rendered.audit` da exportação, por dois motivos: a rodada
        de `/v1` grava a pasta com `contract=None` (não há PLANILHA GERAL a imprimir; ver
        `render_valuation_workbook`), então a lista da auditoria é sempre vazia neste
        caminho e transportá-la seria declarar que a deriva não existe; e a conferência
        acontece ANTES de exportar — a deriva precisa estar visível no boletim recém-montado,
        não só depois que o `.xlsx` foi publicado. É a mesma consolidação acima, filtrada,
        na forma que o plano, o relatório de gravação e a auditoria já publicam.

        Nada disso entra em `valuation_json`: a consolidação é DERIVADA da medição gravada,
        e persistir um número derivado ao lado do fato que o gera é criar dois donos para
        ele. Por isso `valuation_sha256` não muda ao servir estes campos.

        `stale` e os dois digests de fonte respondem, no próprio boletim, se ele ainda
        descreve a praça de agora — o mesmo par de perguntas que `approval` faz sobre a
        assinatura. As FOLHAS entram por parâmetro porque a praça é feita delas: acrescentar
        folha vence o boletim ainda que nenhum pacote novo tenha chegado.
        """
        digests = {} if revision is None else dict(revision.artifact_digests_json or {})
        consolidation = consolidate_by_code(valuation)
        return {
            "round_id": record.id,
            "version": record.version,
            "valuation": valuation.model_dump(mode="json"),
            "valuation_sha256": document_digest(document),
            "total_amount": str(valuation.total_amount),
            **bulletin_sources_state(record, revision, plates),
            "consolidation": [item.model_dump(mode="json") for item in consolidation],
            "consolidation_drifts": [
                item.as_drift().model_dump(mode="json") for item in consolidation if item.has_drift
            ],
            "workbook_present": bulletin_workbook_ref(revision) is not None,
            "workbook_sha256": digests.get(BULLETIN_WORKBOOK_DIGEST),
            "approval": approval_state(valuation),
        }

    def _dossier_payload(
        record: ValuationRoundRecord, *, document: Mapping[str, Any], dossier: AmendmentDossier
    ) -> dict[str, Any]:
        """Dossiê do aditivo como a tela o recebe; nenhum campo de preço existe nele.

        `item_count` zero é desfecho NORMAL e não erro: rodada em que todo item confirmado
        teve o código confirmado não tem aditivo nenhum a pedir.
        """
        return {
            "round_id": record.id,
            "version": record.version,
            "dossier": dossier.model_dump(mode="json"),
            "dossier_sha256": document_digest(document),
            "item_count": len(dossier.items),
        }

    def _revalidated_bulletin(document: Mapping[str, Any]) -> Valuation:
        """Boletim gravado, revalidado na leitura: quem recomputa os totais é o modelo.

        `WorksiteBulletin.validate_bulletin` refaz a soma dos totais já truncados de cada
        linha e recusa a divergência (`BULLETIN_TOTAL_MISMATCH`); `Valuation` refaz o 1:1
        entre linha do boletim e memória de cálculo. Servir o total como ele foi gravado
        faria uma medição adulterada no banco passar por boa — e a tela nunca renderiza
        medição inválida, então artefato que não revalida é `422`, não `200` com ressalva.
        """
        try:
            return Valuation.model_validate(dict(document))
        except ValidationError as error:
            raise _valuation_model_problem(error) from error

    def _revalidated_dossier(document: Mapping[str, Any]) -> AmendmentDossier:
        """Dossiê gravado, revalidado na leitura: espelho de `_revalidated_bulletin`.

        Aqui não há total a recomputar — o dossiê não precifica —, mas há invariantes que
        valem o mesmo: item duplicado e item cuja justificativa deixou de casar com a
        decisão de rejeição que o originou.
        """
        try:
            return AmendmentDossier.model_validate(dict(document))
        except ValidationError as error:
            raise _valuation_model_problem(error) from error

    def _plate_response(
        record: ValuationRoundRecord,
        revision: ValuationRoundRevisionRecord | None,
        plates: Sequence[ValuationRoundPlateRecord],
        *,
        tenant: str,
        plate_id: str | None = None,
    ) -> ValuationPlateResponse:
        """Metadados de UMA folha e, quando a página já foi promovida, a URL assinada.

        `image_url` nulo é estado honesto e não erro: a página só existe depois que o worker
        ingere o PDF. Chave gravada fora do prefixo do tenant, essa sim, é tratada como
        inexistente — e o presign nunca chega a ser chamado.

        Sem `plate_id` responde pela PRIMEIRA folha, e por isso a praça de uma folha lê
        exatamente o que lia antes; com `plate_id`, pela folha nomeada (T4c), cuja imagem está
        sob a chave sufixada que a ingestão escreveu (`plate_ref_key`). Quem quer o estado das
        N folhas de uma vez lê a rota da praça.
        """
        plate = require_plate(plates, plate_id)
        refs = {} if revision is None else dict(revision.artifact_refs_json or {})
        image_key = refs.get(plate_artifact_name(PLATE_IMAGE_REF, plate))
        image_url: str | None = None
        if image_key is not None:
            image_url = signed_artifact_url(
                application.state.artifact_store, object_key=image_key, tenant_id=tenant
            )
            if image_url is None:
                raise _problem(
                    "NOT_FOUND",
                    status.HTTP_404_NOT_FOUND,
                    "Imagem da prancha não encontrada.",
                )
        return ValuationPlateResponse(
            round_id=UUID(record.id),
            version=record.version,
            upload_id=UUID(plate.upload_id),
            source_sha256=plate.source_sha256,
            page_count=plate.page_count,
            image_url=image_url,
        )

    @application.post(
        "/v1/valuation-rounds",
        response_model=ValuationRoundResponse,
        status_code=status.HTTP_201_CREATED,
        tags=["valuation"],
    )
    async def create_valuation_round(
        payload: CreateValuationRoundRequest,
        request: Request,
        principal: AuthenticatedPrincipal,
        session: DatabaseSession,
        idempotency_key: Annotated[str, Depends(_require_idempotency)],
    ) -> ValuationRoundResponse:
        """Abre a rodada e instala o catálogo, que é imutável nela: trocar é abrir outra."""
        _require_valuation_reviewer(principal)
        request_hash = _request_hash(payload)
        existing = _idempotent_response(
            session,
            principal=principal,
            operation="valuation-rounds.create",
            key=idempotency_key,
            request_hash=request_hash,
        )
        if existing is not None:
            return ValuationRoundResponse.model_validate(existing)

        origin = _resolve_valuation_origin(
            session,
            application,
            payload=payload,
            principal=principal,
            storage_flavor=runtime_settings.storage_flavor,
        )
        # Chamada pelo EFEITO: o rótulo é do escritor da planilha, o que interessa aqui é a
        # recusa. `WORKSITE_NAME_DOES_NOT_FIT_SHEET` já existia, e o portão do domínio
        # continua onde estava — mas ele reprovava na MONTAGEM do boletim, depois de a
        # orçamentista ter revisado e codificado as N folhas da praça, quando o nome já não
        # é mais editável e só resta refazer a rodada. Aqui ele ainda é, e por isso a
        # recusa passa a acontecer aqui também, com a mesma mensagem e o mesmo teto.
        #
        # O nome do CORPO, e não o de `origin`: nas origens por orçamento assinado e por
        # medição seguinte o nome vem do conteúdo aprovado e o corpo o RECUSA — recusar ali
        # trocaria uma reprovação tardia com conserto (encurtar a praça na abertura da
        # rodada seguinte) por uma imediata sem conserto nenhum. Naquelas origens quem
        # recusa continua sendo a montagem do boletim.
        if payload.worksite_name is not None:
            default_template().sheet_worksite_label(payload.worksite_name)

        now = datetime.now(UTC)
        round_id = new_uuid7()
        record = ValuationRoundRecord(
            id=str(round_id),
            tenant_id=principal.tenant_id,
            worksite_key=origin.worksite_key,
            worksite_name=origin.worksite_name,
            reference_label=payload.reference_label,
            period_number=payload.period_number,
            address=origin.address,
            contract_label=payload.contract_label,
            status="OPEN",
            version=1,
            catalog_upload_id=origin.catalog_upload_id,
            catalog_object_key=origin.catalog_object_key,
            catalog_source_sha256=origin.catalog_source_sha256,
            catalog_summary_json=origin.catalog_summary,
            estimate_round_id=origin.estimate_round_id,
            estimate_digest=origin.estimate_digest,
            contract_workbook_json=origin.contract_workbook_json,
            extraction_status="idle",
            created_by=principal.subject,
            created_at=now,
            updated_at=now,
        )
        if origin.upload is not None:
            origin.upload.status = "VERIFIED"
        session.add(record)
        response = ValuationRoundResponse(
            round_id=round_id,
            version=record.version,
            status=record.status,
            created_at=now,
        )
        _store_idempotent_response(
            session,
            principal=principal,
            operation="valuation-rounds.create",
            key=idempotency_key,
            request_hash=request_hash,
            response=response,
        )
        _record_audit(
            session,
            principal=principal,
            action="VALUATION_ROUND_CREATED",
            resource_type="valuation_round",
            resource_id=str(round_id),
            request_id=request.state.request_id,
        )
        _record_round_event(
            session,
            principal=principal,
            event_type=EVENT_VALUATION_ACTION_RECORDED,
            action="VALUATION_ROUND_CREATED",
            record=record,
        )
        session.commit()
        return response

    @application.get(
        "/v1/valuation-rounds",
        response_model=ValuationRoundPage,
        tags=["valuation"],
    )
    async def list_valuation_rounds(
        principal: AuthenticatedPrincipal,
        session: DatabaseSession,
        limit: Annotated[int, Query(ge=1, le=100)] = 20,
        cursor: str | None = None,
    ) -> ValuationRoundPage:
        """Rodadas do tenant, da mais recente para a mais antiga, com cursor opaco."""
        _require_valuation_reviewer(principal)
        query = select(ValuationRoundRecord).where(
            ValuationRoundRecord.tenant_id == principal.tenant_id
        )
        if cursor is not None:
            created_at, identifier = _decode_round_cursor(cursor)
            # Forma explícita em vez de comparação de tupla: row values dependem da versão
            # do SQLite, e uma listagem não é lugar de descobrir isso em produção.
            query = query.where(
                or_(
                    ValuationRoundRecord.created_at < created_at,
                    and_(
                        ValuationRoundRecord.created_at == created_at,
                        ValuationRoundRecord.id < identifier,
                    ),
                )
            )
        records = list(
            session.scalars(
                query.order_by(
                    ValuationRoundRecord.created_at.desc(), ValuationRoundRecord.id.desc()
                ).limit(limit + 1)
            )
        )
        page = records[:limit]
        heads = _valuation_round_heads(
            session,
            tenant_id=principal.tenant_id,
            round_ids=[record.id for record in page],
        )
        plate_counts = _valuation_round_plate_counts(
            session,
            tenant_id=principal.tenant_id,
            round_ids=[record.id for record in page],
        )
        return ValuationRoundPage(
            items=[
                ValuationRoundSummary(
                    round_id=UUID(record.id),
                    worksite_key=record.worksite_key,
                    worksite_name=record.worksite_name,
                    reference_label=record.reference_label,
                    period_number=record.period_number,
                    version=record.version,
                    status=record.status,
                    stage=current_stage(
                        record,
                        heads.get(record.id),
                        has_plate=plate_counts.get(record.id, 0) > 0,
                    ),
                    extraction_status=record.extraction_status,
                    created_at=record.created_at,
                    updated_at=record.updated_at,
                    approved=_round_is_approved(heads.get(record.id)),
                    can_open_next=_round_is_approved(heads.get(record.id))
                    and record.contract_workbook_json is not None,
                )
                for record in page
            ],
            next_cursor=_encode_round_cursor(page[-1]) if len(records) > limit and page else None,
        )

    @application.get(
        "/v1/valuation-origins",
        response_model=ValuationOriginsResponse,
        tags=["valuation"],
    )
    async def list_valuation_origins(
        principal: AuthenticatedPrincipal,
        session: DatabaseSession,
    ) -> ValuationOriginsResponse:
        """Orçamentos que podem originar uma medição (F-036, ADR-0048).

        Mora sob a jornada da MEDIÇÃO, e não sob `/v1/estimate-rounds`, por duas razões que
        não são de gosto: a listagem do orçamento é paginada por cursor, e "mostre os
        assinados" viraria varrer páginas do lado do cliente; e prefixo é jornada — um tenant
        com o orçamento `disabled` e a medição `enabled` receberia `403 JOURNEY_UNAVAILABLE`
        numa tela de medição (F-034).

        A lista traz também as **não assinadas** sob o regime, com o estado por extenso. Não
        é ruído: quem procura um orçamento que sabe existir precisa encontrá-lo e ler o
        motivo de ele não servir ainda, em vez de concluir que ele sumiu.

        Leitura tolerante: orçamento que não revalida sai da lista em vez de derrubar a tela,
        a mesma regra que `round_state_payload` já segue. Quem recusa de verdade é a abertura
        da rodada, que revalida o conteúdo antes de gravar o consolidado.
        """
        _require_valuation_reviewer(principal)
        records = list(
            session.scalars(
                select(EstimateRoundRecord)
                .where(
                    EstimateRoundRecord.tenant_id == principal.tenant_id,
                    EstimateRoundRecord.pricing_regime == estimate_rounds.REGIME_CONTRACTED_DEMAND,
                )
                .order_by(EstimateRoundRecord.created_at.desc(), EstimateRoundRecord.id.desc())
            )
        )
        heads = _estimate_round_heads(
            session,
            tenant_id=principal.tenant_id,
            round_ids=[record.id for record in records],
        )
        items: list[ValuationOriginSummary] = []
        for record in records:
            estimate = estimate_rounds.readable_estimate(heads.get(record.id))
            if estimate is None:
                # Rodada sob o regime que ainda não tem orçamento montado: não há o que
                # assinar nem o que herdar, e listá-la ofereceria uma origem inexistente.
                continue
            approval = estimate_rounds.approval_payload(estimate)
            if not approval["approved"]:
                signature: Literal["signed", "stale", "unsigned"] = "unsigned"
            elif approval["stale"]:
                signature = "stale"
            else:
                signature = "signed"
            items.append(
                ValuationOriginSummary(
                    round_id=UUID(record.id),
                    worksite_name=record.worksite_name,
                    reference_label=record.reference_label,
                    signature=signature,
                    approved_by=approval["approved_by"],
                    approved_at=approval["approved_at"],
                    estimate_digest=approval["approved_digest"],
                    code_count=len(estimate.lines),
                    total_amount=str(estimate.total_amount),
                )
            )
        return ValuationOriginsResponse(items=items)

    @application.get(
        "/v1/valuation-rounds/{round_id}",
        response_model=dict[str, Any],
        tags=["valuation"],
    )
    async def get_valuation_round(
        round_id: UUID,
        principal: AuthenticatedPrincipal,
        session: DatabaseSession,
    ) -> dict[str, Any]:
        """Estado da rodada por etapa; é por aqui que a tela acompanha a extração paga."""
        _require_valuation_reviewer(principal)
        record = _load_valuation_round(session, round_id=round_id, tenant_id=principal.tenant_id)
        revision = head_revision(session, round_id=record.id, tenant_id=principal.tenant_id)
        plates = round_plates(session, round_id=record.id, tenant_id=principal.tenant_id)
        return round_state_payload(record, revision, plates)

    @application.post(
        "/v1/valuation-rounds/{round_id}/plate",
        response_model=ValuationPlateResponse,
        tags=["valuation"],
    )
    async def associate_valuation_plate(
        round_id: UUID,
        payload: AssociatePlateRequest,
        request: Request,
        principal: AuthenticatedPrincipal,
        session: DatabaseSession,
        idempotency_key: Annotated[str, Depends(_require_idempotency)],
    ) -> ValuationPlateResponse:
        """Acrescenta uma folha à praça; a API não renderiza nem lê a prancha.

        A ingestão da página — render a 200 DPI, manifest, digest da imagem — é trabalho do
        worker: aqui o PDF é só conferido contra o que o presign declarou.

        Desde a F-046 a rodada tem N folhas (ADR-0057): praça grande vem em planta geral,
        detalhes e cortes, e a legenda quantificada é da OBRA. A segunda folha deixou de ser
        recusa e passou a ser o caso normal; `ROUND_PLATE_ALREADY_PRESENT` recusa só a folha
        REPETIDA — mesma origem e mesma página. A resposta é da folha recém-acrescentada e
        tem a forma de sempre.
        """
        _require_valuation_reviewer(principal)
        operation = f"valuation-rounds.plate:{round_id}"
        request_hash = _request_hash(payload)
        existing = _idempotent_response(
            session,
            principal=principal,
            operation=operation,
            key=idempotency_key,
            request_hash=request_hash,
        )
        if existing is not None:
            return ValuationPlateResponse.model_validate(existing)

        record = _load_valuation_round(session, round_id=round_id, tenant_id=principal.tenant_id)
        require_base_version(record, payload.base_version)
        plates = round_plates(session, round_id=record.id, tenant_id=principal.tenant_id)
        upload = _require_valuation_upload(
            session,
            application,
            upload_id=payload.upload_id,
            principal=principal,
            content_type=PDF_CONTENT_TYPE,
            storage_flavor=runtime_settings.storage_flavor,
        )
        now = datetime.now(UTC)
        # A recusa da folha repetida é do núcleo e acontece ANTES de qualquer escrita: duas
        # rotas não podem discordar sobre o que é a mesma folha.
        plate = append_round_plate(
            session,
            round_record=record,
            plates=plates,
            upload_id=str(payload.upload_id),
            object_key=upload.object_key,
            source_sha256=upload.sha256,
            created_by=principal.subject,
        )
        # Acrescentar a folha é ato humano, e o contador da rodada é o token de concorrência
        # de toda a cadeia (D3): quem leu a rodada antes disso precisa reler antes de decidir.
        # Nenhuma revisão nasce aqui — a folha é linha própria, e revisão guarda artefato.
        record.version += 1
        record.updated_at = now
        upload.status = "VERIFIED"
        response = _plate_response(record, None, [plate], tenant=principal.tenant_id)
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
            action="VALUATION_PLATE_ASSOCIATED",
            resource_type="valuation_round",
            resource_id=record.id,
            request_id=request.state.request_id,
        )
        _record_round_event(
            session,
            principal=principal,
            event_type=EVENT_VALUATION_ACTION_RECORDED,
            action="VALUATION_PLATE_ASSOCIATED",
            record=record,
        )
        # Duas folhas acrescentadas da MESMA versão passam as duas pela guarda otimista em
        # memória e vão disputar a mesma posição da praça, onde `uq_valuation_round_plate`
        # arbitra. Quem perde recebeu, de fato, uma rodada que mudou depois da leitura dele —
        # que é o que `REVISION_CONFLICT` diz. Antes da F-046 a corrida só sobrescrevia as
        # colunas escalares em silêncio.
        _commit_valuation_revision(session)
        return response

    @application.post(
        "/v1/valuation-rounds/{round_id}/plates",
        response_model=ValuationPlatesResponse,
        tags=["valuation"],
    )
    async def append_valuation_plates(
        round_id: UUID,
        payload: AppendPlatesRequest,
        request: Request,
        principal: AuthenticatedPrincipal,
        session: DatabaseSession,
        idempotency_key: Annotated[str, Depends(_require_idempotency)],
    ) -> ValuationPlatesResponse:
        """Promove EM LOTE as páginas escolhidas de um documento a folhas da praça (F-046 T4).

        O ato é a seleção: a orçamentista marca quais páginas viram folha e confirma uma vez.
        Nada vem marcado por padrão e não há promoção automática de todas as páginas — as duas
        alternativas foram recusadas no pacote de design aprovado, e a segunda encheria a
        praça de quadro de áreas e carimbo.

        Tudo ou nada: o teto da praça e a página repetida são apurados sobre o lote inteiro
        antes da primeira folha. Meia promoção deixaria a orçamentista com folhas que ela não
        pediu e uma conta de extração que ela não escolheu.

        A API não abre o PDF (`services/api/AGENTS.md`): página que não existe no documento é
        descoberta pela ingestão, no worker, e o desfecho fica NA folha, sem derrubar as
        demais. Promover não extrai nada — extração é ato à parte, e é o que custa dinheiro.
        """
        _require_valuation_reviewer(principal)
        operation = f"valuation-rounds.plates:{round_id}"
        request_hash = _request_hash(payload)
        existing = _idempotent_response(
            session,
            principal=principal,
            operation=operation,
            key=idempotency_key,
            request_hash=request_hash,
        )
        if existing is not None:
            return ValuationPlatesResponse.model_validate(existing)

        record = _load_valuation_round(session, round_id=round_id, tenant_id=principal.tenant_id)
        require_base_version(record, payload.base_version)
        plates = round_plates(session, round_id=record.id, tenant_id=principal.tenant_id)
        upload = _require_valuation_upload(
            session,
            application,
            upload_id=payload.upload_id,
            principal=principal,
            content_type=PDF_CONTENT_TYPE,
            storage_flavor=runtime_settings.storage_flavor,
        )
        now = datetime.now(UTC)
        appended = append_round_plates(
            session,
            round_record=record,
            plates=plates,
            upload_id=str(payload.upload_id),
            object_key=upload.object_key,
            source_sha256=upload.sha256,
            created_by=principal.subject,
            page_numbers=payload.page_numbers,
        )
        # Um ato humano, um avanço do contador — mesmo que o lote traga N folhas: o token de
        # concorrência conta ATOS, e quem leu a rodada antes do lote precisa reler antes de
        # decidir qualquer coisa sobre ela.
        record.version += 1
        record.updated_at = now
        upload.status = "VERIFIED"
        response = ValuationPlatesResponse(
            round_id=UUID(record.id),
            version=record.version,
            plate_count=len(plates) + len(appended),
            plate_limit=WORKSITE_PLATE_LIMIT,
            appended=[
                ValuationPlateSummary(
                    plate_id=plate.plate_id,
                    position=plate.position,
                    page_number=plate.page_number,
                    source_sha256=plate.source_sha256,
                )
                for plate in appended
            ],
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
            action="VALUATION_PLATE_ASSOCIATED",
            resource_type="valuation_round",
            resource_id=record.id,
            request_id=request.state.request_id,
        )
        _record_round_event(
            session,
            principal=principal,
            event_type=EVENT_VALUATION_ACTION_RECORDED,
            action="VALUATION_PLATE_ASSOCIATED",
            record=record,
        )
        _commit_valuation_revision(session)
        return response

    @application.get(
        "/v1/valuation-rounds/{round_id}/plate",
        response_model=ValuationPlateResponse,
        tags=["valuation"],
    )
    async def get_valuation_plate(
        round_id: UUID,
        principal: AuthenticatedPrincipal,
        session: DatabaseSession,
        plate_id: PlateIdQuery = None,
    ) -> ValuationPlateResponse:
        """Metadados e URL assinada da página promovida; a URL não vai para log nem auditoria.

        `plate_id` é OPCIONAL e a ausência dele é a leitura de sempre — a primeira folha
        (F-046 T4c). É por ele que a tela da praça abre a folha 2 em diante sem precisar de
        rota nova.
        """
        _require_valuation_reviewer(principal)
        record = _load_valuation_round(session, round_id=round_id, tenant_id=principal.tenant_id)
        revision = head_revision(session, round_id=record.id, tenant_id=principal.tenant_id)
        plates = round_plates(session, round_id=record.id, tenant_id=principal.tenant_id)
        return _plate_response(
            record, revision, plates, tenant=principal.tenant_id, plate_id=plate_id
        )

    @application.post(
        "/v1/valuation-rounds/{round_id}/plate/extractions",
        response_model=ValuationExtractionResponse,
        status_code=status.HTTP_202_ACCEPTED,
        tags=["valuation"],
    )
    async def create_valuation_plate_extraction(
        round_id: UUID,
        payload: CreatePlateExtractionRequest,
        request: Request,
        principal: AuthenticatedPrincipal,
        session: DatabaseSession,
        idempotency_key: Annotated[str, Depends(_require_idempotency)],
    ) -> ValuationExtractionResponse:
        """Enfileira a extração paga da legenda; nenhum provider é chamado no request path.

        Rota da PRIMEIRA folha, que é a folha única da rodada de sempre: desde a F-046 ela
        delega ao mesmo núcleo do lote (`queue_plate_extractions`), com a folha nomeada, para
        que a praça de uma folha e a de N passem exatamente pelas mesmas recusas. Quem quer
        escolher quais folhas extrair usa a rota do lote.
        """
        _require_valuation_reviewer(principal)
        operation = f"valuation-rounds.extractions:{round_id}"
        request_hash = _request_hash(payload)
        existing = _idempotent_response(
            session,
            principal=principal,
            operation=operation,
            key=idempotency_key,
            request_hash=request_hash,
        )
        if existing is not None:
            replay = ValuationExtractionResponse.model_validate(existing)
            # Repetir o mesmo comando é o caminho de retomada quando a fila recusou: o
            # intent já está durável, e o claim atômico do worker garante que uma entrega
            # extra não repague o provider.
            _enqueue_plate_extraction(
                round_id=str(round_id),
                extraction_id=str(replay.extraction_id),
                tenant_id=principal.tenant_id,
            )
            return replay

        record = _load_valuation_round(session, round_id=round_id, tenant_id=principal.tenant_id)
        require_base_version(record, payload.base_version)
        plates = round_plates(session, round_id=record.id, tenant_id=principal.tenant_id)
        plate = require_plate(plates)
        revision = head_revision(session, round_id=record.id, tenant_id=principal.tenant_id)
        # Chamada paga de provider: entitlement contratual do tenant primeiro, e sem
        # enfileirar nada quando ele falta (ADR-0012).
        _require_active_ai_entitlement(
            session,
            principal,
            real_providers_enabled=runtime_settings.real_providers_enabled,
        )
        unavailable = extraction_unavailable(extraction_arm_spec())
        if unavailable is not None:
            # Só o código declarado sai: nome de variável de ambiente do servidor é detalhe
            # de infraestrutura e não pertence à resposta de um cliente.
            raise _problem(
                "PROVIDER_UNAVAILABLE",
                status.HTTP_503_SERVICE_UNAVAILABLE,
                "A extração automática não está disponível neste ambiente.",
                {"code": unavailable.code},
            )

        now = datetime.now(UTC)
        extraction_id = new_uuid7()
        queue_plate_extractions(
            record,
            plates,
            extracted_plate_ids(revision, plates),
            plate_ids=[plate.plate_id],
            extraction_id=str(extraction_id),
            requested_by=principal.subject,
            now=now,
        )
        record.version += 1
        record.updated_at = now
        response = ValuationExtractionResponse(
            round_id=round_id,
            version=record.version,
            extraction_id=extraction_id,
            status=record.extraction_status,
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
            action="VALUATION_EXTRACTION_REQUESTED",
            resource_type="valuation_round",
            resource_id=record.id,
            request_id=request.state.request_id,
        )
        _record_round_event(
            session,
            principal=principal,
            event_type=EVENT_VALUATION_ACTION_RECORDED,
            action="VALUATION_EXTRACTION_REQUESTED",
            record=record,
        )
        # O intent é durável ANTES da fila, e nenhuma transação atravessa a publicação.
        session.commit()
        _enqueue_plate_extraction(
            round_id=str(round_id),
            extraction_id=str(extraction_id),
            tenant_id=principal.tenant_id,
        )
        return response

    @application.post(
        "/v1/valuation-rounds/{round_id}/plates/extractions",
        response_model=ValuationPlatesExtractionResponse,
        status_code=status.HTTP_202_ACCEPTED,
        tags=["valuation"],
    )
    async def create_valuation_plates_extraction(
        round_id: UUID,
        payload: CreatePlatesExtractionRequest,
        request: Request,
        principal: AuthenticatedPrincipal,
        session: DatabaseSession,
        idempotency_key: Annotated[str, Depends(_require_idempotency)],
    ) -> ValuationPlatesExtractionResponse:
        """Enfileira a extração paga de VÁRIAS folhas da praça, num ato só (F-046 T4).

        Cada folha é uma chamada paga a mais, e por isso duas coisas são explícitas: quais
        folhas (`plate_ids`, sem nada marcado por padrão) e quantas (`plate_count` na
        resposta, escrito antes de o worker gastar o primeiro centavo). O custo por folha não
        pode aparecer só na fatura.

        Os freios de gasto que já existiam continuam todos: entitlement contratual do tenant
        (ADR-0012) e teto de gasto declarado no ambiente do servidor
        (`extraction_unavailable`), os dois antes de qualquer enfileiramento. O teto de folhas
        por rodada (`WORKSITE_PLATE_LIMIT`) já foi cobrado quando a folha entrou na praça.

        Tudo ou nada: folha inexistente, folha já extraída e folha com extração em voo
        recusam o LOTE inteiro. Uma autorização pela metade seria a pior das respostas — quem
        pagou por três folhas leria "aceito" e receberia duas.

        Um comando de fila por folha, com o mesmo `extraction_id` do lote: é o que dá a cada
        uma o seu claim atômico e o que faz a que falha não derrubar as demais.
        """
        _require_valuation_reviewer(principal)
        operation = f"valuation-rounds.plates-extractions:{round_id}"
        request_hash = _request_hash(payload)
        existing = _idempotent_response(
            session,
            principal=principal,
            operation=operation,
            key=idempotency_key,
            request_hash=request_hash,
        )
        if existing is not None:
            replay = ValuationPlatesExtractionResponse.model_validate(existing)
            # Repetir o mesmo comando é o caminho de retomada quando a fila recusou: o
            # intent já está durável, e o claim atômico do worker garante que uma entrega
            # extra não repague o provider.
            _enqueue_plate_extraction(
                round_id=str(round_id),
                extraction_id=str(replay.extraction_id),
                tenant_id=principal.tenant_id,
                plate_ids=replay.plate_ids,
            )
            return replay

        record = _load_valuation_round(session, round_id=round_id, tenant_id=principal.tenant_id)
        require_base_version(record, payload.base_version)
        plates = round_plates(session, round_id=record.id, tenant_id=principal.tenant_id)
        require_plate(plates)
        revision = head_revision(session, round_id=record.id, tenant_id=principal.tenant_id)
        _require_active_ai_entitlement(
            session,
            principal,
            real_providers_enabled=runtime_settings.real_providers_enabled,
        )
        unavailable = extraction_unavailable(extraction_arm_spec())
        if unavailable is not None:
            raise _problem(
                "PROVIDER_UNAVAILABLE",
                status.HTTP_503_SERVICE_UNAVAILABLE,
                "A extração automática não está disponível neste ambiente.",
                {"code": unavailable.code},
            )

        now = datetime.now(UTC)
        extraction_id = new_uuid7()
        queued = queue_plate_extractions(
            record,
            plates,
            extracted_plate_ids(revision, plates),
            plate_ids=payload.plate_ids,
            extraction_id=str(extraction_id),
            requested_by=principal.subject,
            now=now,
        )
        record.version += 1
        record.updated_at = now
        response = ValuationPlatesExtractionResponse(
            round_id=round_id,
            version=record.version,
            extraction_id=extraction_id,
            status="queued",
            plate_count=len(queued),
            plate_ids=[plate.plate_id for plate in queued],
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
            action="VALUATION_EXTRACTION_REQUESTED",
            resource_type="valuation_round",
            resource_id=record.id,
            request_id=request.state.request_id,
        )
        _record_round_event(
            session,
            principal=principal,
            event_type=EVENT_VALUATION_ACTION_RECORDED,
            action="VALUATION_EXTRACTION_REQUESTED",
            record=record,
        )
        # O intent é durável ANTES da fila, e nenhuma transação atravessa a publicação.
        session.commit()
        _enqueue_plate_extraction(
            round_id=str(round_id),
            extraction_id=str(extraction_id),
            tenant_id=principal.tenant_id,
            plate_ids=response.plate_ids,
        )
        return response

    @application.get(
        "/v1/valuation-rounds/{round_id}/takeoff",
        response_model=dict[str, Any],
        tags=["valuation"],
    )
    async def get_valuation_takeoff(
        round_id: UUID,
        principal: AuthenticatedPrincipal,
        session: DatabaseSession,
        plate_id: PlateIdQuery = None,
    ) -> dict[str, Any]:
        """Pacote de takeoff de uma folha da praça, com a âncora de evidência de cada item.

        `plate_id` é OPCIONAL e a ausência é a leitura da PRIMEIRA folha, campo por campo como
        antes da praça (F-046 T4c). É por ele que a revisão dos itens alcança as folhas 2..N:
        sem ele, o pacote da segunda folha só existia dentro do consolidado, que a tela não usa
        para revisar item.
        """
        _require_valuation_reviewer(principal)
        record = _load_valuation_round(session, round_id=round_id, tenant_id=principal.tenant_id)
        revision = head_revision(session, round_id=record.id, tenant_id=principal.tenant_id)
        if plate_id is None:
            return _takeoff_payload(record, revision)
        plates = round_plates(session, round_id=record.id, tenant_id=principal.tenant_id)
        return _takeoff_payload(record, revision, resolve_plate(plates, plate_id))

    @application.get(
        "/v1/valuation-rounds/{round_id}/takeoff/overlay",
        response_model=ValuationTakeoffOverlayResponse,
        tags=["valuation"],
    )
    async def get_valuation_takeoff_overlay(
        round_id: UUID,
        principal: AuthenticatedPrincipal,
        session: DatabaseSession,
        plate_id: PlateIdQuery = None,
    ) -> ValuationTakeoffOverlayResponse:
        """URL assinada do overlay e a idade dele; overlay vencido é `200`, nunca erro.

        Esconder a divergência seria pior do que mostrá-la: o desenho anterior continua
        sendo a única visão de onde cada número foi lido (ADR-0030). A URL assinada segue o
        regime da imagem da prancha — prefixo do tenant conferido antes do presign, e nunca
        registrada em log nem em auditoria (ADR-0028 D5).

        Um overlay por FOLHA, e nunca um overlay de praça: não existe pixel de praça
        (ADR-0057, decisão 3). `plate_id` é OPCIONAL e a ausência é o overlay da primeira
        folha, exatamente como antes; a idade é comparada contra o pacote DAQUELA folha, que é
        o único pacote de que aquele desenho pode ter nascido.
        """
        _require_valuation_reviewer(principal)
        record = _load_valuation_round(session, round_id=round_id, tenant_id=principal.tenant_id)
        revision = head_revision(session, round_id=record.id, tenant_id=principal.tenant_id)
        plate: ValuationRoundPlateRecord | None = None
        if plate_id is None:
            stored: Mapping[str, Any] = require_document(
                revision,
                "takeoff_packet_json",
                stage=STAGE_TAKEOFF,
                detail="a rodada ainda não tem pacote de takeoff publicado",
            )
        else:
            plates = round_plates(session, round_id=record.id, tenant_id=principal.tenant_id)
            plate = resolve_plate(plates, plate_id)
            stored = plate_packet_document(revision, plate)
        overlay_key = require_takeoff_overlay(revision, plate)
        image_url = signed_artifact_url(
            application.state.artifact_store,
            object_key=overlay_key,
            tenant_id=principal.tenant_id,
        )
        if image_url is None:
            raise _problem(
                "NOT_FOUND",
                status.HTTP_404_NOT_FOUND,
                "Overlay do takeoff não encontrado.",
            )
        packet_sha256 = document_digest(stored)
        state = takeoff_overlay_state(revision, packet_sha256=packet_sha256, plate=plate)
        return ValuationTakeoffOverlayResponse(
            round_id=UUID(record.id),
            version=record.version,
            image_url=image_url,
            image_sha256=cast(str | None, state["image_sha256"]),
            packet_sha256=packet_sha256,
            overlay_packet_sha256=cast(str | None, state["overlay_packet_sha256"]),
            stale=cast(bool, state["stale"]),
        )

    @application.post(
        "/v1/valuation-rounds/{round_id}/takeoff/decisions",
        response_model=dict[str, Any],
        tags=["valuation"],
    )
    async def decide_valuation_takeoff_items(
        round_id: UUID,
        payload: TakeoffDecisionRequest,
        request: Request,
        principal: AuthenticatedPrincipal,
        session: DatabaseSession,
        idempotency_key: Annotated[str, Depends(_require_idempotency)],
    ) -> dict[str, Any]:
        """Aplica o LOTE de decisões do orçamentista, grava a revisão e enfileira o overlay.

        O ato de revisão é o lote inteiro — uma revisão nova para todas as decisões, ou
        nenhuma. Decidir item a item produzia uma revisão por item, e com ela um
        `base_version` novo que invalidava o formulário ainda aberto na tela.

        A decisão é ato humano: ela avança o contador da rodada e o da cadeia de revisões.
        O overlay, não — ele é consequência, e é reconstruído fora do request path
        (ADR-0030). Entre a decisão e o desenho novo, a resposta já declara o overlay
        vencido, para que a tela não mostre o desenho anterior como se fosse deste pacote.

        `plate_id` no corpo diz QUAL folha da praça este lote revisa (F-046 T4c); sem ele, a
        primeira, exatamente como antes. O re-render do overlay só é enfileirado para a
        primeira folha: o comando de fila desenha o pacote de `takeoff_packet_json` e ainda
        não sabe da praça, então enfileirá-lo para a folha 2 seria um comando que não desenha
        nada. A resposta continua verdadeira nas duas — o overlay daquela folha sai declarado
        vencido, que é o que ele é, e não some da tela (ADR-0030).
        """
        _require_valuation_reviewer(principal)
        operation = f"valuation-rounds.takeoff-decisions:{round_id}"
        request_hash = _request_hash(payload)
        existing = _idempotent_response(
            session,
            principal=principal,
            operation=operation,
            key=idempotency_key,
            request_hash=request_hash,
        )
        if existing is not None:
            return existing

        record = _load_valuation_round(session, round_id=round_id, tenant_id=principal.tenant_id)
        require_base_version(record, payload.base_version)
        revision = head_revision(session, round_id=record.id, tenant_id=principal.tenant_id)
        # Sem folha nomeada, o caminho é o de sempre, recusa por recusa: a rodada de uma folha
        # não passa a carregar a praça só porque a praça passou a existir.
        plate: ValuationRoundPlateRecord | None = None
        if payload.plate_id is None:
            packet = require_takeoff_packet(revision)
        else:
            plates = round_plates(session, round_id=record.id, tenant_id=principal.tenant_id)
            plate = resolve_plate(plates, payload.plate_id)
            packet = require_plate_packet(revision, plate)
        try:
            # Identidade do `Principal` e instante do servidor: o corpo não carimba nenhum
            # dos dois. A regra de decisão é do domínio e não é reimplementada aqui.
            #
            # UM instante para o lote inteiro, e não um por decisão: elas foram tomadas no
            # mesmo ato, e carimbá-las com milissegundos diferentes inventaria uma ordem
            # que o revisor não declarou.
            decided_at = datetime.now(UTC)
            decisions = [
                TakeoffDecisionInput(
                    item_id=entrada.item_id,
                    action=entrada.action,
                    reviewer_id=principal.subject,
                    reviewer_role=VALUATION_REVIEWER_ROLE,
                    decided_at=decided_at,
                    quantity=parse_quantity(entrada.quantity),
                    unit=entrada.unit,
                    note=entrada.note,
                    item_note=entrada.item_note,
                )
                for entrada in payload.decisions
            ]
            # Lote atômico: `apply_takeoff_decisions` valida o conjunto (item repetido,
            # item inexistente, quantidade ausente em item ambíguo) antes de produzir
            # pacote nenhum, então metade aplicada não é estado alcançável.
            reviewed = apply_takeoff_decisions(packet, TakeoffDecisionBatch(decisions=decisions))
        except ValidationError as error:
            raise _valuation_model_problem(error) from error

        document = reviewed.model_dump(mode="json")
        packet_sha256 = document_digest(document)
        new_revision = append_revision(
            session,
            round_record=record,
            created_by=principal.subject,
            changes=plate_packet_changes(revision, plate, document),
        )
        record.updated_at = datetime.now(UTC)
        response = {
            **_takeoff_payload(record, new_revision, plate),
            "overlay": takeoff_overlay_state(
                new_revision, packet_sha256=packet_sha256, plate=plate
            ),
        }
        _store_idempotent_response(
            session,
            principal=principal,
            operation=operation,
            key=idempotency_key,
            request_hash=request_hash,
            response=ValuationDocumentResponse(response),
        )
        _record_audit(
            session,
            principal=principal,
            action="VALUATION_TAKEOFF_ITEM_DECIDED",
            resource_type="valuation_round",
            resource_id=record.id,
            request_id=request.state.request_id,
        )
        _record_round_event(
            session,
            principal=principal,
            event_type=EVENT_VALUATION_ACTION_RECORDED,
            action="VALUATION_TAKEOFF_ITEM_DECIDED",
            record=record,
        )
        # A decisão fica durável ANTES da fila, e nenhuma transação atravessa a publicação.
        _commit_valuation_revision(session)
        if plate is None or plate.position <= 1:
            _enqueue_takeoff_overlay_rerender(
                round_id=record.id,
                tenant_id=principal.tenant_id,
                packet_sha256=packet_sha256,
            )
        return response

    @application.get(
        "/v1/valuation-rounds/{round_id}/code-suggestions",
        response_model=dict[str, Any],
        tags=["valuation"],
    )
    async def get_valuation_code_suggestions(
        round_id: UUID,
        principal: AuthenticatedPrincipal,
        session: DatabaseSession,
        plate_id: PlateIdQuery = None,
    ) -> dict[str, Any]:
        """Shortlist de código por item confirmado: observação, nunca decisão (ADR-0021).

        Calculada UMA vez e persistida; leitura seguinte serve o que está gravado
        (`computed: false`). A gravação entra na cadeia de revisões **sem avançar a versão da
        rodada** (decisão humana de 2026-08-17): a shortlist é artefato derivado, e se um
        `GET` movesse o token de concorrência, a próxima decisão do orçamentista levaria
        `409` por algo que ele não fez.

        `plate_id` é OPCIONAL e a ausência é a shortlist da PRIMEIRA folha, campo por campo
        como antes da praça (F-046 T4d). Ela é por FOLHA porque é observação por ITEM, e os
        itens são os do pacote de uma prancha: servir a shortlist da primeira folha sob o
        cabeçalho da segunda ofereceria códigos para elementos que não estão naquele desenho.

        **Nenhuma chamada paga acontece aqui**, e isso é invariante, não circunstância
        (ADR-0054 D7). O cálculo é chamado sem braço semântico (`semantic=None`), então
        nenhum índice é procurado e nenhum rótulo é embutido: a shortlist que a primeira
        leitura grava é léxica, e a híbrida exige o recompute, que é ato humano com
        `Idempotency-Key` e `base_version`. O motivo viaja em `semantic_notes`.

        Mover a chamada paga para cá quebraria mais do que o custo: um `GET` que gasta é um
        `GET` que a tela dispara em polling. `tests/api/test_estimate_semantic_arm.py`
        guarda a invariante com um adapter que falha se for tocado.
        """
        _require_valuation_reviewer(principal)
        record = _load_valuation_round(session, round_id=round_id, tenant_id=principal.tenant_id)
        revision = head_revision(session, round_id=record.id, tenant_id=principal.tenant_id)
        plate = _resolve_code_plate(session, record, principal, plate_id)
        stored = suggestions_document_for_plate(revision, plate)
        if stored is not None:
            try:
                # Artefato gravado que não valida é recusa, e não recálculo silencioso: a
                # cura dele é o recompute explícito, que é ato humano e declarado.
                suggestions = CodeSuggestionSet.model_validate(stored)
            except ValidationError as error:
                raise _valuation_model_problem(error) from error
            return _suggestions_payload(
                record, document=stored, suggestions=suggestions, computed=False, notes=[]
            )

        packet = _packet_for_code_plate(revision, plate)
        require_reviewed_packet(packet)
        computed, notes, _telemetry = compute_round_suggestions(packet, _round_catalog(record))
        document = computed.model_dump(mode="json")
        append_revision(
            session,
            round_record=record,
            created_by=principal.subject,
            changes=plate_suggestions_changes(revision, plate, document),
            advance_version=False,
        )
        # `updated_at` da rodada continua marcando o último ato humano: a leitura que calcula
        # a shortlist não é um, e a cadeia de revisões carimba o próprio instante.
        response = _suggestions_payload(
            record, document=document, suggestions=computed, computed=True, notes=notes
        )
        try:
            session.commit()
        except IntegrityError:
            # Duas leituras simultâneas — e a tela faz polling — calculam a mesma shortlist
            # e disputam a mesma posição da cadeia. Perder essa corrida não é falha de
            # ninguém: o cálculo é determinístico, quem chegou antes gravou o mesmo
            # artefato, e servir o dele é a resposta certa. Um `500` aqui transformaria
            # concorrência normal de tela em erro de servidor.
            session.rollback()
            revision = head_revision(session, round_id=record.id, tenant_id=principal.tenant_id)
            stored = suggestions_document_for_plate(revision, plate)
            if stored is None:
                raise
            return _suggestions_payload(
                record,
                document=stored,
                suggestions=CodeSuggestionSet.model_validate(stored),
                computed=False,
                notes=[],
            )
        return response

    @application.post(
        "/v1/valuation-rounds/{round_id}/code-suggestions/recompute",
        response_model=dict[str, Any],
        tags=["valuation"],
    )
    async def recompute_valuation_code_suggestions(
        round_id: UUID,
        payload: RecomputeSuggestionsRequest,
        request: Request,
        principal: AuthenticatedPrincipal,
        session: DatabaseSession,
        idempotency_key: Annotated[str, Depends(_require_idempotency)],
    ) -> dict[str, Any]:
        """Recalcula a shortlist do zero pelo algoritmo corrente e avança a rodada.

        Ao contrário do `GET`, este é ato humano: ele descarta a shortlist anterior, então
        exige `base_version` e move o token de concorrência da rodada.

        É aqui, e só aqui, que o braço semântico roda (ADR-0054 D7): com índice publicado
        para o catálogo da rodada, entitlement ativo e via de embeddings no processo, os
        rótulos dos itens confirmados são embutidos numa chamada paga pequena e a shortlist
        sai híbrida. Faltando qualquer um dos três — ou com o índice recusado na amarração —
        a shortlist sai léxica **com o motivo declarado**, e o ato se completa: nada disso
        devolve `403`, porque perder o recompute inteiro por falta de um braço que é enfeite
        seria pior do que não ter o braço (D8).

        Shortlist que já carrega refino pago recusa com `409 SUGGESTIONS_ALREADY_REFINED` —
        recalcular descartaria o lineage da chamada paga. Artefato gravado que não valida
        como `CodeSuggestionSet` **não** cai nessa guarda: o recompute é exatamente a cura
        dele.
        """
        _require_valuation_reviewer(principal)
        operation = f"valuation-rounds.suggestions-recompute:{round_id}"
        request_hash = _request_hash(payload)
        existing = _idempotent_response(
            session,
            principal=principal,
            operation=operation,
            key=idempotency_key,
            request_hash=request_hash,
        )
        if existing is not None:
            return existing

        record = _load_valuation_round(session, round_id=round_id, tenant_id=principal.tenant_id)
        require_base_version(record, payload.base_version)
        revision = head_revision(session, round_id=record.id, tenant_id=principal.tenant_id)
        packet = require_takeoff_packet(revision)
        require_reviewed_packet(packet)
        require_unrefined_suggestions(suggestions_of(revision))
        catalog = _round_catalog(record)
        computed, notes, telemetry = compute_round_suggestions(
            packet,
            catalog,
            semantic=_semantic_arms(session, principal, [catalog])[0],
        )
        document = computed.model_dump(mode="json")
        append_revision(
            session,
            round_record=record,
            created_by=principal.subject,
            changes={"code_suggestions_json": document},
        )
        record.updated_at = datetime.now(UTC)
        response = _suggestions_payload(
            record, document=document, suggestions=computed, computed=True, notes=notes
        )
        _store_idempotent_response(
            session,
            principal=principal,
            operation=operation,
            key=idempotency_key,
            request_hash=request_hash,
            response=ValuationDocumentResponse(response),
        )
        _record_audit(
            session,
            principal=principal,
            action="VALUATION_CODE_SUGGESTIONS_RECOMPUTED",
            resource_type="valuation_round",
            resource_id=record.id,
            request_id=request.state.request_id,
        )
        _record_round_event(
            session,
            principal=principal,
            event_type=EVENT_VALUATION_ACTION_RECORDED,
            action="VALUATION_CODE_SUGGESTIONS_RECOMPUTED",
            record=record,
            extra_payload=telemetry.event_payload(),
        )
        _log_suggestions_recompute(record, telemetry)
        _commit_valuation_revision(session)
        return response

    @application.get(
        "/v1/valuation-rounds/{round_id}/catalog/search",
        response_model=dict[str, Any],
        tags=["valuation"],
    )
    async def search_valuation_catalog(
        round_id: UUID,
        principal: AuthenticatedPrincipal,
        session: DatabaseSession,
        q: Annotated[str, Query(min_length=1, max_length=200)],
        limit: Annotated[
            int, Query(ge=1, le=CATALOG_SEARCH_MAX_LIMIT)
        ] = CATALOG_SEARCH_DEFAULT_LIMIT,
        arm: Annotated[Literal["lexical", "hybrid"], Query()] = "lexical",
    ) -> dict[str, Any]:
        """Busca no catálogo instalado, léxica por padrão (decisão humana de 2026-08-17).

        `arm=hybrid` é braço PAGO e passa pelo mesmo portão da extração: sem autorização
        contratual do tenant, `403 AI_PROCESSING_NOT_AUTHORIZED` (ADR-0012). Com ela, a
        resposta ainda é `503 PROVIDER_UNAVAILABLE`, e a razão MUDOU com a F-041: o índice
        de embeddings agora É publicado (`/v1/platform/reference-catalog-indexes`), então o
        que falta não é o artefato — é que resolver o vetor da CONSULTA é chamada paga, e
        esta rota é um `GET` que dispara a cada tecla. A última frase deste docstring sempre
        foi a regra real, e agora é a única: nenhuma chamada de embedding acontece dentro de
        um `GET`, com ou sem índice (ADR-0054 D7 concentrou o gasto no recompute).
        Isso é estado honesto, não falha: cair no léxico fingindo ser híbrido esconderia do
        orçamentista que a vizinhança semântica não participou do que ele está lendo.
        """
        _require_valuation_reviewer(principal)
        record = _load_valuation_round(session, round_id=round_id, tenant_id=principal.tenant_id)
        if arm == "hybrid":
            _require_active_ai_entitlement(
                session,
                principal,
                real_providers_enabled=runtime_settings.real_providers_enabled,
            )
            raise _problem(
                "PROVIDER_UNAVAILABLE",
                status.HTTP_503_SERVICE_UNAVAILABLE,
                "A busca semântica não está disponível nesta rodada.",
                {"code": "SEMANTIC_INDEX_ABSENT"},
            )
        return {
            "round_id": record.id,
            "version": record.version,
            **search_round_catalog(_round_catalog(record), q, limit),
        }

    @application.get(
        "/v1/valuation-rounds/{round_id}/code-assignments",
        response_model=dict[str, Any],
        tags=["valuation"],
    )
    async def get_valuation_code_assignments(
        round_id: UUID,
        principal: AuthenticatedPrincipal,
        session: DatabaseSession,
        plate_id: PlateIdQuery = None,
    ) -> dict[str, Any]:
        """Decisões de código de uma folha e os itens dela que ainda esperam por uma.

        `plate_id` é OPCIONAL e a ausência é a leitura da PRIMEIRA folha, campo por campo como
        antes da praça (F-046 T4d). A etapa de código é POR FOLHA porque o conjunto é por
        prancha: `CodeAssignmentSet` carrega `plate_id`, `page_number` e `image_sha256`, e
        `pending_items` só faz sentido contra o pacote daquela folha (ADR-0057, decisão 6).
        """
        _require_valuation_reviewer(principal)
        record = _load_valuation_round(session, round_id=round_id, tenant_id=principal.tenant_id)
        revision = head_revision(session, round_id=record.id, tenant_id=principal.tenant_id)
        plate = _resolve_code_plate(session, record, principal, plate_id)
        packet = _packet_for_code_plate(revision, plate)
        return _assignments_payload(
            record,
            packet=packet,
            assignments=assignments_for_plate(revision, plate),
            document=assignments_document_for_plate(revision, plate),
        )

    @application.post(
        "/v1/valuation-rounds/{round_id}/code-assignments/decisions",
        response_model=dict[str, Any],
        tags=["valuation"],
    )
    async def decide_valuation_item_code(
        round_id: UUID,
        payload: CodeAssignmentDecisionRequest,
        request: Request,
        principal: AuthenticatedPrincipal,
        session: DatabaseSession,
        idempotency_key: Annotated[str, Depends(_require_idempotency)],
    ) -> dict[str, Any]:
        """Confirma ou rejeita o código de UM item, acumulando sobre o conjunto anterior.

        Acumular item a item é a semântica do domínio: é ele quem recusa a re-decisão
        (`ASSIGNMENT_ITEM_ALREADY_DECIDED`) e quem carrega adiante as confirmações já
        registradas. A rota não confere código, unidade nem estado do item — ela só monta a
        decisão com a identidade do `Principal` e o instante do servidor.

        `plate_id` no corpo diz em QUAL folha da praça o item foi lido (F-046 T4d); sem ele, a
        primeira, exatamente como antes. O conjunto acumulado é o DAQUELA folha, e é gravado no
        lugar dela: um conjunto é por prancha (ADR-0057, decisão 6), e o boletim da praça
        consome a união deles.
        """
        _require_valuation_reviewer(principal)
        operation = f"valuation-rounds.code-decisions:{round_id}"
        request_hash = _request_hash(payload)
        existing = _idempotent_response(
            session,
            principal=principal,
            operation=operation,
            key=idempotency_key,
            request_hash=request_hash,
        )
        if existing is not None:
            return existing

        record = _load_valuation_round(session, round_id=round_id, tenant_id=principal.tenant_id)
        require_base_version(record, payload.base_version)
        revision = head_revision(session, round_id=record.id, tenant_id=principal.tenant_id)
        plate = _resolve_code_plate(session, record, principal, payload.plate_id)
        packet = _packet_for_code_plate(revision, plate)
        previous = assignments_for_plate(revision, plate)
        catalog = _round_catalog(record)
        try:
            decision = CodeAssignmentInput(
                item_id=payload.item_id,
                action=payload.action,
                code=payload.code,
                reviewer_id=principal.subject,
                reviewer_role=VALUATION_REVIEWER_ROLE,
                decided_at=datetime.now(UTC),
                note=payload.note,
            )
            batch = CodeAssignmentBatch(assignments=[decision])
        except ValidationError as error:
            # Invariante do domínio embrulhada pelo validador: o código estável sai, a
            # mensagem do Pydantic não — ela pode ecoar o valor recusado.
            raise _valuation_model_problem(error) from error
        # Sem consolidado contratual: a rodada guarda catálogo, e o portão de exportação é
        # que responde por preço e unidade contra o contrato quando ele existir.
        assignments = apply_code_assignments(packet, batch, catalog, previous=previous)

        document = assignments.model_dump(mode="json")
        append_revision(
            session,
            round_record=record,
            created_by=principal.subject,
            changes=plate_assignments_changes(revision, plate, document),
        )
        record.updated_at = datetime.now(UTC)
        response = _assignments_payload(
            record, packet=packet, assignments=assignments, document=document
        )
        _store_idempotent_response(
            session,
            principal=principal,
            operation=operation,
            key=idempotency_key,
            request_hash=request_hash,
            response=ValuationDocumentResponse(response),
        )
        _record_audit(
            session,
            principal=principal,
            action="VALUATION_ITEM_CODE_DECIDED",
            resource_type="valuation_round",
            resource_id=record.id,
            request_id=request.state.request_id,
        )
        _record_round_event(
            session,
            principal=principal,
            event_type=EVENT_VALUATION_ACTION_RECORDED,
            action="VALUATION_ITEM_CODE_DECIDED",
            record=record,
        )
        _commit_valuation_revision(session)
        return response

    @application.post(
        "/v1/valuation-rounds/{round_id}/code-assignments/closures",
        response_model=dict[str, Any],
        tags=["valuation"],
    )
    async def close_valuation_item_package(
        round_id: UUID,
        payload: ValuationItemPackageClosureRequest,
        request: Request,
        principal: AuthenticatedPrincipal,
        session: DatabaseSession,
        idempotency_key: Annotated[str, Depends(_require_idempotency)],
    ) -> dict[str, Any]:
        """Declara COMPLETO o pacote de serviços de um item — o ato que a confirmação não faz.

        Existe porque a presença de um código deixou de significar que o elemento acabou.
        Sem esta rota, um item com um de seis códigos ficaria indistinguível de um item
        resolvido, e o boletim sairia pela metade sem ninguém ser avisado.

        É rota própria, e não uma bandeira em `/decisions`, porque `/decisions` carrega UMA
        decisão: um pacote de seis códigos nasce em seis chamadas, e a orçamentista não sabe
        de antemão qual será a última. Quem fecha afirma outra coisa, e afirmação separada
        merece endpoint separado — inclusive para a auditoria poder distingui-las.

        A rota não confere quantos códigos o item tem: fechar é decisão de quem monta o
        pacote. Item sem código confirmado, pacote já fechado e item fora do takeoff
        continuam sendo recusa do domínio.

        `plate_id` no corpo diz de QUAL folha da praça é o elemento (F-046 T4d); sem ele, a
        primeira, exatamente como antes. Fechar é afirmação sobre o pacote de um elemento, e
        elemento mora numa prancha."""
        _require_valuation_reviewer(principal)
        operation = f"valuation-rounds.code-closures:{round_id}"
        request_hash = _request_hash(payload)
        existing = _idempotent_response(
            session,
            principal=principal,
            operation=operation,
            key=idempotency_key,
            request_hash=request_hash,
        )
        if existing is not None:
            return existing

        record = _load_valuation_round(session, round_id=round_id, tenant_id=principal.tenant_id)
        require_base_version(record, payload.base_version)
        revision = head_revision(session, round_id=record.id, tenant_id=principal.tenant_id)
        plate = _resolve_code_plate(session, record, principal, payload.plate_id)
        packet = _packet_for_code_plate(revision, plate)
        previous = assignments_for_plate(revision, plate)
        catalog = _round_catalog(record)
        try:
            batch = CodeAssignmentBatch(
                closures=[
                    ItemPackageClosureInput(
                        item_id=payload.item_id,
                        reviewer_id=principal.subject,
                        reviewer_role=VALUATION_REVIEWER_ROLE,
                        decided_at=datetime.now(UTC),
                        note=payload.note,
                    )
                ]
            )
        except ValidationError as error:
            raise _valuation_model_problem(error) from error
        assignments = apply_code_assignments(packet, batch, catalog, previous=previous)

        document = assignments.model_dump(mode="json")
        append_revision(
            session,
            round_record=record,
            created_by=principal.subject,
            changes=plate_assignments_changes(revision, plate, document),
        )
        record.updated_at = datetime.now(UTC)
        response = _assignments_payload(
            record, packet=packet, assignments=assignments, document=document
        )
        _store_idempotent_response(
            session,
            principal=principal,
            operation=operation,
            key=idempotency_key,
            request_hash=request_hash,
            response=ValuationDocumentResponse(response),
        )
        _record_audit(
            session,
            principal=principal,
            action="VALUATION_ITEM_PACKAGE_CLOSED",
            resource_type="valuation_round",
            resource_id=record.id,
            request_id=request.state.request_id,
        )
        _record_round_event(
            session,
            principal=principal,
            event_type=EVENT_VALUATION_ACTION_RECORDED,
            action="VALUATION_ITEM_PACKAGE_CLOSED",
            record=record,
        )
        _commit_valuation_revision(session)
        return response

    @application.post(
        "/v1/valuation-rounds/{round_id}/code-assignments/revocations",
        response_model=dict[str, Any],
        tags=["valuation"],
    )
    async def revoke_valuation_item_code(
        round_id: UUID,
        payload: ValuationCodeAssignmentRevocationRequest,
        request: Request,
        principal: AuthenticatedPrincipal,
        session: DatabaseSession,
        idempotency_key: Annotated[str, Depends(_require_idempotency)],
    ) -> dict[str, Any]:
        """Desfaz um código confirmado por engano, sem refazer a rodada (F-045, ADR-0061).

        Até esta rota, a etapa só sabia avançar: a identidade da decisão é o par
        `(item, código)`, re-decidir um par é recusado, e não há rollback de revisão em lugar
        nenhum da `/v1`. Um código confirmado errado custava a praça inteira.

        Revogar é **decisão nova**, e não edição do passado: a revisão anterior continua
        gravada com o par confirmado lá dentro, e o conjunto novo registra em `revocations`
        quem desfez, quando e por quê — para que quem lê o conjunto corrente distinga "nunca
        decidido" de "decidido e desfeito" sem comparar revisões.

        **Desfazer reabre o pacote** do elemento, quando ele estava fechado: a completude foi
        afirmada sobre um pacote que acabou de mudar. O efeito adiante é o desejado — o
        boletim volta a recusar aquele elemento até alguém fechar de novo.

        Par que não está confirmado, item fora do takeoff e rodada do regime antigo continuam
        sendo recusa do domínio, que esta rota não reimplementa.

        `plate_id` no corpo diz em QUAL folha da praça o par foi confirmado (F-046 T4d); sem
        ele, a primeira, exatamente como antes. Desfazer é decisão nova sobre o conjunto
        DAQUELA folha, e é lá que ela é gravada.
        """
        _require_valuation_reviewer(principal)
        operation = f"valuation-rounds.code-revocations:{round_id}"
        request_hash = _request_hash(payload)
        existing = _idempotent_response(
            session,
            principal=principal,
            operation=operation,
            key=idempotency_key,
            request_hash=request_hash,
        )
        if existing is not None:
            return existing

        record = _load_valuation_round(session, round_id=round_id, tenant_id=principal.tenant_id)
        require_base_version(record, payload.base_version)
        revision = head_revision(session, round_id=record.id, tenant_id=principal.tenant_id)
        plate = _resolve_code_plate(session, record, principal, payload.plate_id)
        packet = _packet_for_code_plate(revision, plate)
        previous = assignments_for_plate(revision, plate)
        if previous is None:
            # Sem conjunto anterior não há par para desfazer. O `exception_handler` de
            # `ValuationValidationError` transforma isto no mesmo `problem+json` que o
            # domínio produziria, com o mesmo código estável.
            raise ValuationValidationError(
                "ASSIGNMENT_REVOCATION_PAIR_UNKNOWN",
                "esta rodada ainda não tem código confirmado para desfazer",
                {"item_id": payload.item_id, "code": payload.code},
            )
        try:
            revocation = CodeAssignmentRevocationInput(
                item_id=payload.item_id,
                code=payload.code,
                reviewer_id=principal.subject,
                reviewer_role=VALUATION_REVIEWER_ROLE,
                revoked_at=datetime.now(UTC),
                note=payload.note,
            )
        except ValidationError as error:
            raise _valuation_model_problem(error) from error
        assignments = apply_code_revocation(packet, revocation, previous)

        document = assignments.model_dump(mode="json")
        append_revision(
            session,
            round_record=record,
            created_by=principal.subject,
            changes=plate_assignments_changes(revision, plate, document),
        )
        record.updated_at = datetime.now(UTC)
        response = _assignments_payload(
            record, packet=packet, assignments=assignments, document=document
        )
        _store_idempotent_response(
            session,
            principal=principal,
            operation=operation,
            key=idempotency_key,
            request_hash=request_hash,
            response=ValuationDocumentResponse(response),
        )
        _record_audit(
            session,
            principal=principal,
            action="VALUATION_ITEM_CODE_REVOKED",
            resource_type="valuation_round",
            resource_id=record.id,
            request_id=request.state.request_id,
        )
        _record_round_event(
            session,
            principal=principal,
            event_type=EVENT_VALUATION_ACTION_RECORDED,
            action="VALUATION_ITEM_CODE_REVOKED",
            record=record,
        )
        _commit_valuation_revision(session)
        return response

    @application.get(
        "/v1/valuation-rounds/{round_id}/worksite",
        response_model=dict[str, Any],
        tags=["valuation"],
    )
    async def get_valuation_worksite(
        round_id: UUID,
        principal: AuthenticatedPrincipal,
        session: DatabaseSession,
    ) -> dict[str, Any]:
        """A praça: as folhas da rodada, o estado de cada uma e o consolidado (F-046).

        O consolidado é DERIVADO das folhas gravadas, dos pacotes das revisões e dos vínculos
        declarados — nunca servido de uma coluna que guardasse a soma dos três e envelhecesse
        sozinha assim que uma folha nova entrasse.

        Leitura tolerante, como o estado da rodada: praça que ainda não fecha sai com
        `consolidated.present = false`, as folhas pendentes nomeadas e o código da recusa,
        em vez de derrubar a tela. Quem recusa de verdade é a declaração do vínculo e o
        boletim, que é onde a resposta importa.
        """
        _require_valuation_reviewer(principal)
        record = _load_valuation_round(session, round_id=round_id, tenant_id=principal.tenant_id)
        revision = head_revision(session, round_id=record.id, tenant_id=principal.tenant_id)
        plates = round_plates(session, round_id=record.id, tenant_id=principal.tenant_id)
        return worksite_state(record, revision, plates)

    @application.post(
        "/v1/valuation-rounds/{round_id}/worksite/identity-links/preview",
        response_model=dict[str, Any],
        tags=["valuation"],
    )
    async def preview_valuation_identity_link(
        round_id: UUID,
        payload: PreviewIdentityLinkRequest,
        principal: AuthenticatedPrincipal,
        session: DatabaseSession,
    ) -> dict[str, Any]:
        """O efeito da fusão no total da praça — **sem gravar nada** (F-046 T4c).

        É LEITURA, e o corpo diz isso: sem `base_version`, sem `Idempotency-Key`, sem revisão
        nova e sem avançar a versão da rodada, como a pré-visualização do acervo de canteiro.

        Ela existe porque a conta é do SERVIDOR. A tela de medição não soma
        (`apps/web/AGENTS.md`), e sem esta rota a orçamentista só descobriria o efeito do
        vínculo depois de declará-lo — que é justamente a decisão que o pacote de design quis
        tornar informada. Todo decimal sai como TEXTO, pelo mesmo motivo do resto da jornada.

        As recusas são as MESMAS da declaração, e pelo mesmo caminho: o consolidado é montado
        com o vínculo candidato, então vínculo dentro da mesma folha, alvo inexistente e
        cadeia de vínculos recusam aqui exatamente como recusariam lá. Uma prévia que
        dissesse "pode" para o que o ato recusa seria pior do que prévia nenhuma.

        O que ela **não** faz é somar o que não tem soma: unidade divergente entre as duas
        leituras devolve os dois totais `null` com `unit_mismatch = true`, com as duas parcelas
        à vista. Um número inventado ali teria a aparência de conta conferida.
        """
        _require_valuation_reviewer(principal)
        record = _load_valuation_round(session, round_id=round_id, tenant_id=principal.tenant_id)
        revision = head_revision(session, round_id=record.id, tenant_id=principal.tenant_id)
        plates = round_plates(session, round_id=record.id, tenant_id=principal.tenant_id)
        try:
            candidate = declared_identity_link(
                kept=(payload.kept.plate_id, payload.kept.item_id),
                discarded=(payload.discarded.plate_id, payload.discarded.item_id),
                # A nota é do ATO e não da simulação; o modelo exige uma, e esta declara o que
                # ela é. Nada deste vínculo é gravado — ele vive nesta chamada e morre nela.
                note="pré-visualização do vínculo de identidade; nenhuma declaração foi gravada",
                declared_by=principal.subject,
                declared_at=datetime.now(UTC),
            )
            worksite = require_worksite_takeoff(
                record, revision, plates, identity_links=[*identity_links_of(revision), candidate]
            )
        except ValidationError as error:
            raise _valuation_model_problem(error) from error
        return {
            "round_id": record.id,
            "version": record.version,
            **identity_link_preview(
                worksite,
                worksite_packets(revision),
                kept=candidate.kept,
                discarded=candidate.discarded,
            ),
        }

    @application.post(
        "/v1/valuation-rounds/{round_id}/worksite/identity-links",
        response_model=dict[str, Any],
        tags=["valuation"],
    )
    async def declare_valuation_identity_link(
        round_id: UUID,
        payload: DeclareIdentityLinkRequest,
        request: Request,
        principal: AuthenticatedPrincipal,
        session: DatabaseSession,
        idempotency_key: Annotated[str, Depends(_require_idempotency)],
    ) -> dict[str, Any]:
        """Declara que duas leituras de folhas diferentes são o mesmo elemento (ADR-0057).

        É o único caminho de fusão que existe: nada aqui funde por rótulo, unidade ou
        proximidade, e sem esta declaração as duas leituras contam — o fail-closed erra para
        somar demais, e visivelmente (decisão 4).

        Ato humano de ponta a ponta: avança o contador da rodada, cria revisão NOVA
        (append-only, a lista de vínculos inteira gravada de uma vez) e carimba autor e
        instante do lado do servidor. O consolidado é remontado com o vínculo novo ANTES de
        gravar qualquer coisa: é essa montagem que aplica as recusas da T1 — vínculo dentro
        da mesma folha, vínculo incompleto, alvo inexistente e cadeia de vínculos —, e uma
        declaração recusada não deixa revisão nenhuma para trás.
        """
        _require_valuation_reviewer(principal)
        operation = f"valuation-rounds.identity-links:{round_id}"
        request_hash = _request_hash(payload)
        existing = _idempotent_response(
            session,
            principal=principal,
            operation=operation,
            key=idempotency_key,
            request_hash=request_hash,
        )
        if existing is not None:
            return existing

        record = _load_valuation_round(session, round_id=round_id, tenant_id=principal.tenant_id)
        require_base_version(record, payload.base_version)
        revision = head_revision(session, round_id=record.id, tenant_id=principal.tenant_id)
        plates = round_plates(session, round_id=record.id, tenant_id=principal.tenant_id)
        try:
            link = declared_identity_link(
                kept=(payload.kept.plate_id, payload.kept.item_id),
                discarded=(payload.discarded.plate_id, payload.discarded.item_id),
                note=payload.note,
                declared_by=principal.subject,
                declared_at=datetime.now(UTC),
            )
            links = [*identity_links_of(revision), link]
            # Monta o consolidado com o vínculo novo: é aqui que a T1 recusa. O resultado é
            # descartado de propósito — o que fica gravado são os vínculos, e o consolidado
            # volta a ser derivado na leitura seguinte.
            require_worksite_takeoff(record, revision, plates, identity_links=links)
        except ValidationError as error:
            raise _valuation_model_problem(error) from error

        new_revision = append_revision(
            session,
            round_record=record,
            created_by=principal.subject,
            changes={
                "worksite_identity_links_json": [
                    declared.model_dump(mode="json") for declared in links
                ]
            },
        )
        record.updated_at = datetime.now(UTC)
        response = worksite_state(record, new_revision, plates)
        _store_idempotent_response(
            session,
            principal=principal,
            operation=operation,
            key=idempotency_key,
            request_hash=request_hash,
            response=ValuationDocumentResponse(response),
        )
        _record_audit(
            session,
            principal=principal,
            action="VALUATION_ITEM_IDENTITY_DECLARED",
            resource_type="valuation_round",
            resource_id=record.id,
            request_id=request.state.request_id,
        )
        _record_round_event(
            session,
            principal=principal,
            event_type=EVENT_VALUATION_ACTION_RECORDED,
            action="VALUATION_ITEM_IDENTITY_DECLARED",
            record=record,
        )
        _commit_valuation_revision(session)
        return response

    @application.post(
        "/v1/valuation-rounds/{round_id}/calc",
        response_model=dict[str, Any],
        tags=["valuation"],
    )
    async def build_valuation_calc(
        round_id: UUID,
        payload: BuildValuationCalcRequest,
        request: Request,
        principal: AuthenticatedPrincipal,
        session: DatabaseSession,
        idempotency_key: Annotated[str, Depends(_require_idempotency)],
    ) -> dict[str, Any]:
        """Constrói boletim e memória de cálculo da PRAÇA INTEIRA (F-046 T4c, ADR-0057).

        Até a T4c esta rota media a PRIMEIRA folha: numa praça de N folhas o boletim media
        `1/N` e não dizia nada — exatamente o erro que a F-046 existe para impedir. Agora ela
        monta o consolidado das folhas gravadas e delega a `build_worksite_takeoff_valuation`:
        um boletim por folha, com a folha de origem preservada em cada memória, o total da
        praça saindo da consolidação por código que a PLANILHA GERAL já faz, e a leitura
        declarada como o mesmo elemento físico contando UMA vez.

        Praça de uma folha responde byte a byte como antes: `build_worksite_takeoff_bulletins`
        passa chave e nome da praça intactos quando a praça tem uma folha só (decisão 8), e a
        `Valuation` resultante é a mesma que `build_worksite_valuation` produzia.

        Duas recusas da praça passam a ser alcançáveis por aqui, as duas do domínio e nesta
        ordem: folha sem pacote extraído é `409 ROUND_STAGE_NOT_READY` nomeando as folhas, e
        folha com item ainda por revisar é `422` com `WORKSITE_TAKEOFF_PLATE_PENDING`.

        A identidade da obra vem da RODADA (`worksite_key`, `worksite_name`,
        `period_number`, `reference_label`, `address`, `contract_label`), nunca do corpo:
        em `/v1` esses rótulos são colunas de `ValuationRoundRecord` e o corpo carrega só a
        guarda de concorrência.

        `calc_plan=None` de propósito: o plano de cálculo POR ITEM é artefato de DIRETÓRIO do
        servidor de medição e a rodada de `/v1` não o publica. A memória de cálculo que a
        rodada aceita é a `CalcMatrix` (ADR-0053, F-038 T8), que vem no CORPO do build: quando
        presente, o boletim funde por código e resolve dependência; ausente, cada item recebe
        o bloco de quantidade direta que o próprio domínio gera — nunca uma receita suposta. A
        matriz posta é validada aqui e persistida em `calc_matrix_json` da revisão nova, para
        auditoria, antes de alimentar o builder.

        Esta rota **não aprova nada**: aprovação nominal da medição é ato próprio, com
        portão de saldo e contrato, e não pertence à construção do boletim.

        O que ela faz, quando a cabeça já trazia uma aprovação, é LEVÁ-LA ADIANTE — e
        preservar não é aprovar. A aprovação carregada continua amarrada ao digest do
        conteúdo ANTIGO, então a medição recém-montada nasce com a aprovação caduca: a
        exportação recusa com `APPROVAL_CONTENT_MISMATCH` até um ato novo, e a tela mostra os
        dois digests lado a lado em vez de fingir que ninguém nunca assinou. Descartá-la aqui
        apagaria em silêncio o fato de que uma aprovação existiu. Quem responde "houve
        aprovação antes?" é a rota, que tem a revisão em mãos, e não o domínio:
        `build_worksite_valuation` continua montando medição sem aprovação nenhuma. Ver
        `carry_approval_forward`.

        Duas recusas se parecem e não são a mesma coisa. Conjunto de códigos ainda
        inexistente é `409 ROUND_STAGE_NOT_READY` — etapa fora de ordem, o orçamentista tem
        o que fazer para sair dela. Conjunto existente com item confirmado sem decisão é
        `422 DOMAIN_VALIDATION_FAILED` com `CALC_ASSIGNMENT_MISSING`: invariante do
        domínio, e quem a levanta é `packages/valuation`. Catálogo com origem diferente do
        SCO fecha a medição licitada em `BULLETIN_PRICE_ORIGIN_FORBIDDEN` (ADR-0027) —
        item fora do contrato vira dossiê de aditivo, nunca preço de outra tabela.

        A guarda de `base_version` é mudança pretendida desta migração; ver
        `BuildValuationCalcRequest`.
        """
        _require_valuation_reviewer(principal)
        operation = f"valuation-rounds.calc:{round_id}"
        request_hash = _request_hash(payload)
        existing = _idempotent_response(
            session,
            principal=principal,
            operation=operation,
            key=idempotency_key,
            request_hash=request_hash,
        )
        if existing is not None:
            return existing

        record = _load_valuation_round(session, round_id=round_id, tenant_id=principal.tenant_id)
        require_base_version(record, payload.base_version)
        revision = head_revision(session, round_id=record.id, tenant_id=principal.tenant_id)
        # Chamada pela RECUSA, e o pacote é descartado: a rodada sem takeoff nenhum precisa
        # continuar saindo com a mesma ordem de recusas de antes da praça — takeoff, depois
        # código —, e é a partir daí que o consolidado assume.
        require_takeoff_packet(revision)
        assignments = require_assignments(revision)
        calc_matrix = _validate_calc_matrix(payload.calc_matrix)
        catalog = _round_catalog(record)
        plates = round_plates(session, round_id=record.id, tenant_id=principal.tenant_id)
        # O consolidado é montado ANTES do boletim porque é ele quem sabe de quais folhas a
        # praça é feita: sem esta linha o boletim seria o da PRIMEIRA folha, e meia praça
        # somada parece uma praça inteira.
        worksite = require_worksite_takeoff(record, revision, plates)
        valuation = build_worksite_takeoff_valuation(
            worksite,
            worksite_plate_inputs(
                revision,
                plates,
                catalog=catalog,
                first_assignments=assignments,
                calc_matrix=calc_matrix,
            ),
            catalog,
            worksite_name=record.worksite_name,
            period_number=record.period_number,
            reference_label=record.reference_label,
            address=record.address,
            contract_label=record.contract_label,
            # O MESMO template da exportação, aqui e não só lá: é este layout que decide
            # se o nome da folha cabe na aba, e a recusa precisa sair AGORA — no `.xlsx`
            # ela sairia depois de a praça inteira estar montada, servida e aprovada.
            template=default_template(),
        )
        # Preservar não é aprovar: a aprovação anterior segue adiante já caduca, apontando
        # para o digest do conteúdo que ela cobria.
        valuation = carry_approval_forward(valuation, readable_valuation(revision))

        document = valuation.model_dump(mode="json")
        # A matriz posta é gravada AO LADO do boletim (`None` no regime legado), auditável e
        # re-legível: cada revisão registra exatamente a matriz que gerou a memória dela.
        matrix_document = None if calc_matrix is None else calc_matrix.model_dump(mode="json")
        # O carimbo de "de que praça este boletim foi feito", gravado no mesmo ato que o
        # monta. Sem ele a rodada não tem como responder, depois, se a medição gravada ainda
        # descreve a praça — e a tela ficava mandando montar de novo sem oferecer como.
        # As fontes são as da CABEÇA (o build não altera nenhuma delas) e a matriz é a
        # POSTA, que é a que acabou de gerar esta memória.
        head_digests = {} if revision is None else dict(revision.artifact_digests_json or {})
        new_revision = append_revision(
            session,
            round_record=record,
            created_by=principal.subject,
            changes={
                "valuation_json": document,
                "calc_matrix_json": matrix_document,
                "artifact_digests_json": {
                    **head_digests,
                    BULLETIN_SOURCES_DIGEST: bulletin_sources_digest(
                        record, revision, plates, calc_matrix=matrix_document
                    ),
                },
            },
        )
        record.updated_at = datetime.now(UTC)
        response = _bulletin_payload(
            record, new_revision, plates, document=document, valuation=valuation
        )
        _store_idempotent_response(
            session,
            principal=principal,
            operation=operation,
            key=idempotency_key,
            request_hash=request_hash,
            response=ValuationDocumentResponse(response),
        )
        _record_audit(
            session,
            principal=principal,
            action="VALUATION_CALC_BUILT",
            resource_type="valuation_round",
            resource_id=record.id,
            request_id=request.state.request_id,
        )
        _record_round_event(
            session,
            principal=principal,
            event_type=EVENT_VALUATION_ACTION_RECORDED,
            action="VALUATION_CALC_BUILT",
            record=record,
        )
        _commit_valuation_revision(session)
        return response

    @application.get(
        "/v1/valuation-rounds/{round_id}/bulletin",
        response_model=dict[str, Any],
        tags=["valuation"],
    )
    async def get_valuation_bulletin(
        round_id: UUID,
        principal: AuthenticatedPrincipal,
        session: DatabaseSession,
    ) -> dict[str, Any]:
        """Boletim gravado, com os totais recomputados na leitura pelos validadores do modelo.

        Boletim ainda não construído é `409 ROUND_STAGE_NOT_READY`; boletim que não passa na
        revalidação é `422`, nunca um `200` com número que ninguém conferiu.

        A URL assinada da planilha é montada AQUI, na leitura, e só quando há planilha
        publicada — ela é credencial de leitura de curta vida e não pertence a nenhum
        artefato durável.
        """
        _require_valuation_reviewer(principal)
        record = _load_valuation_round(session, round_id=round_id, tenant_id=principal.tenant_id)
        revision = head_revision(session, round_id=record.id, tenant_id=principal.tenant_id)
        document = require_document(
            revision,
            "valuation_json",
            stage=STAGE_BULLETIN,
            detail="a rodada ainda não tem boletim construído",
        )
        payload = _bulletin_payload(
            record,
            revision,
            round_plates(session, round_id=record.id, tenant_id=principal.tenant_id),
            document=document,
            valuation=_revalidated_bulletin(document),
        )
        workbook_url = signed_artifact_url(
            application.state.artifact_store,
            object_key=bulletin_workbook_ref(revision),
            tenant_id=principal.tenant_id,
        )
        return {**payload, "workbook_url": workbook_url}

    @application.post(
        "/v1/valuation-rounds/{round_id}/approve",
        response_model=dict[str, Any],
        tags=["valuation"],
    )
    async def approve_valuation_round(
        round_id: UUID,
        payload: ApproveValuationRequest,
        request: Request,
        principal: AuthenticatedPrincipal,
        session: DatabaseSession,
        idempotency_key: Annotated[str, Depends(_require_idempotency)],
    ) -> dict[str, Any]:
        """Aprova nominalmente a medição da cabeça, amarrando o ato ao digest do conteúdo.

        Este é o ato que o portão de exportação cobra. Ele não recalcula, não confere preço e
        não decide nada sobre o boletim: ele registra QUEM assumiu a medição como está, QUANDO
        e SOBRE QUAL conteúdo — e é essa terceira parte que impede a assinatura de sobreviver
        a uma mudança do que foi assinado.

        A identidade é do JWT e só dele (critério 3 da F-028). O corpo carrega apenas
        `base_version`, e `ApproveValuationRequest` documenta por que não existe campo de
        nome nem de observação. A revisão nova AVANÇA `version`, porque aprovar é ato humano
        deliberado e a próxima decisão do orçamentista tem de partir do que ele viu aprovado.

        Boletim ainda não construído é `409 ROUND_STAGE_NOT_READY` — etapa fora de ordem;
        boletim que não revalida é `422`, pela mesma razão do `GET`: ninguém aprova um
        artefato que o domínio recusa.

        Aprovar de novo é o caminho normal da aprovação caduca do desenho aprovado, e não um
        erro: o ato é idempotente por conteúdo (mesmo revisor, mesmo digest e mesmo instante
        produzem o mesmo `decision_id`), mas cada chamada é uma revisão nova da cadeia
        append-only — o histórico guarda as duas assinaturas, que é o que um registro de
        aprovação existe para fazer.
        """
        _require_valuation_reviewer(principal)
        operation = f"valuation-rounds.approve:{round_id}"
        request_hash = _request_hash(payload)
        existing = _idempotent_response(
            session,
            principal=principal,
            operation=operation,
            key=idempotency_key,
            request_hash=request_hash,
        )
        if existing is not None:
            return existing

        record = _load_valuation_round(session, round_id=round_id, tenant_id=principal.tenant_id)
        require_base_version(record, payload.base_version)
        revision = head_revision(session, round_id=record.id, tenant_id=principal.tenant_id)
        document = require_document(
            revision,
            "valuation_json",
            stage=STAGE_BULLETIN,
            detail="a rodada ainda não tem boletim construído",
        )
        approved = approve_valuation(
            _revalidated_bulletin(document),
            reviewer_id=principal.subject,
            decided_at=datetime.now(UTC),
        )

        approved_document = approved.model_dump(mode="json")
        new_revision = append_revision(
            session,
            round_record=record,
            created_by=principal.subject,
            changes={"valuation_json": approved_document},
        )
        record.updated_at = datetime.now(UTC)
        response = _bulletin_payload(
            record,
            new_revision,
            round_plates(session, round_id=record.id, tenant_id=principal.tenant_id),
            document=approved_document,
            valuation=approved,
        )
        _store_idempotent_response(
            session,
            principal=principal,
            operation=operation,
            key=idempotency_key,
            request_hash=request_hash,
            response=ValuationDocumentResponse(response),
        )
        _record_audit(
            session,
            principal=principal,
            action="VALUATION_APPROVED",
            resource_type="valuation_round",
            resource_id=record.id,
            request_id=request.state.request_id,
        )
        _record_round_event(
            session,
            principal=principal,
            event_type=EVENT_VALUATION_ACTION_RECORDED,
            action="VALUATION_APPROVED",
            record=record,
        )
        _commit_valuation_revision(session)
        return response

    @application.post(
        "/v1/valuation-rounds/{round_id}/bulletin/export",
        response_model=dict[str, Any],
        tags=["valuation"],
    )
    async def export_valuation_bulletin(
        round_id: UUID,
        payload: ExportBulletinRequest,
        request: Request,
        principal: AuthenticatedPrincipal,
        session: DatabaseSession,
        idempotency_key: Annotated[str, Depends(_require_idempotency)],
    ) -> dict[str, Any]:
        """Publica o `.xlsx` do boletim: portão do domínio, auditoria e só então object store.

        A ordem é o portão, igual à do orçamento-base (ADR-0038). Primeiro
        `Valuation.ensure_exportable`, que é a regra do DOMÍNIO e não uma cópia dela aqui:
        medição sem aprovação, com aprovação de recusa ou com aprovação que não confere com o
        conteúdo atual sai como `422 DOMAIN_VALIDATION_FAILED` com
        `details.code = VALUATION_EXPORT_BLOCKED` e a lista de violações em `details.errors`.
        Depois a planilha é escrita num arquivo temporário, reaberta e reconferida contra a
        medição e o catálogo instalado — e só um laudo aprovado deixa os bytes subirem e a
        revisão nascer. Auditoria reprovada é `500` e não publica nada.

        O consolidado que o portão recebe é o `bulletin_export_contract` da rodada, cuja
        limitação está declarada por extenso lá: a cadeia de `/v1` não importa consolidado
        contratual, então os códigos de saldo e contrato não têm fato que os alimente, a
        conferência de preço fica com o auditor (`CATALOG_PRICE_MISMATCH`) e a aprovação
        continua valendo integralmente. Nenhum número é inventado para o portão passar.

        A exportação NÃO altera a medição: a revisão nova carrega o mesmo `valuation_json` da
        cabeça e acrescenta só a referência e o digest do `.xlsx`. `version` avança porque
        publicar é ato humano deliberado, no mesmo desenho do `build_estimate`.
        """
        _require_valuation_reviewer(principal)
        operation = f"valuation-rounds.bulletin-export:{round_id}"
        request_hash = _request_hash(payload)
        existing = _idempotent_response(
            session,
            principal=principal,
            operation=operation,
            key=idempotency_key,
            request_hash=request_hash,
        )
        if existing is not None:
            return existing

        record = _load_valuation_round(session, round_id=round_id, tenant_id=principal.tenant_id)
        require_base_version(record, payload.base_version)
        revision = head_revision(session, round_id=record.id, tenant_id=principal.tenant_id)
        document = require_document(
            revision,
            "valuation_json",
            stage=STAGE_BULLETIN,
            detail="a rodada ainda não tem boletim construído",
        )
        valuation = _revalidated_bulletin(document)
        # Portão do domínio ANTES de qualquer render: nada é escrito, nem em disco temporário,
        # para uma medição que não pode ser publicada.
        valuation.ensure_exportable(_export_contract_for(record, valuation))

        catalog = _round_catalog(record)
        # Portão fail-closed: grava, reabre e audita ANTES de qualquer publicação.
        rendered = render_valuation_workbook(valuation, catalog, default_template())
        object_key = bulletin_workbook_key(
            tenant_id=principal.tenant_id,
            round_id=record.id,
            valuation_sha256=document_digest(document),
        )
        # O objeto sobe ANTES do commit, pelo mesmo motivo do orçamento-base: uma revisão que
        # citasse um objeto ainda ausente seria um estado que nenhuma leitura consegue servir.
        # O contrário — objeto no store sem revisão que o cite — é inerte, porque a chave é
        # derivada do conteúdo e nada o alcança sem a revisão.
        application.state.artifact_store.write_object(
            object_key=object_key,
            body=rendered.body,
            content_type=BULLETIN_WORKBOOK_CONTENT_TYPE,
        )
        head_refs = {} if revision is None else dict(revision.artifact_refs_json or {})
        head_digests = {} if revision is None else dict(revision.artifact_digests_json or {})
        new_revision = append_revision(
            session,
            round_record=record,
            created_by=principal.subject,
            changes={
                "artifact_refs_json": {**head_refs, BULLETIN_WORKBOOK_REF: object_key},
                "artifact_digests_json": {
                    **head_digests,
                    BULLETIN_WORKBOOK_DIGEST: rendered.audit.workbook_sha256,
                },
            },
        )
        record.updated_at = datetime.now(UTC)
        response = _bulletin_payload(
            record,
            new_revision,
            round_plates(session, round_id=record.id, tenant_id=principal.tenant_id),
            document=document,
            valuation=valuation,
        )
        _store_idempotent_response(
            session,
            principal=principal,
            operation=operation,
            key=idempotency_key,
            request_hash=request_hash,
            response=ValuationDocumentResponse(response),
        )
        _record_audit(
            session,
            principal=principal,
            action="BULLETIN_EXPORTED",
            resource_type="valuation_round",
            resource_id=record.id,
            request_id=request.state.request_id,
        )
        _record_round_event(
            session,
            principal=principal,
            event_type=EVENT_VALUATION_ACTION_RECORDED,
            action="BULLETIN_EXPORTED",
            record=record,
        )
        _commit_valuation_revision(session)
        return response

    @application.post(
        "/v1/valuation-rounds/{round_id}/amendment-dossier",
        response_model=dict[str, Any],
        tags=["valuation"],
    )
    async def build_valuation_amendment_dossier(
        round_id: UUID,
        payload: BuildAmendmentDossierRequest,
        request: Request,
        principal: AuthenticatedPrincipal,
        session: DatabaseSession,
        idempotency_key: Annotated[str, Depends(_require_idempotency)],
    ) -> dict[str, Any]:
        """Constrói o dossiê do aditivo: itens confirmados cujo código foi REJEITADO.

        Espelho de `POST /calc`: o dossiê é o outro artefato de fechamento da rodada e
        nasce dos mesmos dois artefatos-base — pacote de takeoff e conjunto de códigos. Ele
        não carrega campo de preço por construção e nunca cria nem altera `Amendment`/RE-RA
        (ADR-0027, ADR-0018): pedir o aditivo à prefeitura é ato contratual humano, fora
        deste sistema.

        Rejeição na revisão do TAKEOFF não é aditivo — item que não se mede não vira
        pedido. O que entra aqui é só a rejeição de CÓDIGO de um item confirmado no
        takeoff, com a justificativa que o orçamentista registrou.

        Conjunto de códigos inexistente é `409 ROUND_STAGE_NOT_READY`; item confirmado sem
        decisão de código é `422 DOMAIN_VALIDATION_FAILED` com
        `AMENDMENT_DOSSIER_ASSIGNMENTS_INCOMPLETE`, porque o dossiê é artefato de
        fechamento e não publica foto parcial da rodada.

        A guarda de `base_version` é mudança pretendida desta migração; ver
        `BuildAmendmentDossierRequest`.
        """
        _require_valuation_reviewer(principal)
        operation = f"valuation-rounds.amendment-dossier:{round_id}"
        request_hash = _request_hash(payload)
        existing = _idempotent_response(
            session,
            principal=principal,
            operation=operation,
            key=idempotency_key,
            request_hash=request_hash,
        )
        if existing is not None:
            return existing

        record = _load_valuation_round(session, round_id=round_id, tenant_id=principal.tenant_id)
        require_base_version(record, payload.base_version)
        revision = head_revision(session, round_id=record.id, tenant_id=principal.tenant_id)
        packet = require_takeoff_packet(revision)
        assignments = require_assignments(revision)
        dossier = build_amendment_dossier(packet, assignments)

        document = dossier.model_dump(mode="json")
        append_revision(
            session,
            round_record=record,
            created_by=principal.subject,
            changes={"amendment_dossier_json": document},
        )
        record.updated_at = datetime.now(UTC)
        response = _dossier_payload(record, document=document, dossier=dossier)
        _store_idempotent_response(
            session,
            principal=principal,
            operation=operation,
            key=idempotency_key,
            request_hash=request_hash,
            response=ValuationDocumentResponse(response),
        )
        _record_audit(
            session,
            principal=principal,
            action="VALUATION_AMENDMENT_DOSSIER_BUILT",
            resource_type="valuation_round",
            resource_id=record.id,
            request_id=request.state.request_id,
        )
        _record_round_event(
            session,
            principal=principal,
            event_type=EVENT_VALUATION_ACTION_RECORDED,
            action="VALUATION_AMENDMENT_DOSSIER_BUILT",
            record=record,
        )
        _commit_valuation_revision(session)
        return response

    @application.get(
        "/v1/valuation-rounds/{round_id}/amendment-dossier",
        response_model=dict[str, Any],
        tags=["valuation"],
    )
    async def get_valuation_amendment_dossier(
        round_id: UUID,
        principal: AuthenticatedPrincipal,
        session: DatabaseSession,
    ) -> dict[str, Any]:
        """Dossiê gravado, revalidado na leitura: espelho de `GET /bulletin`.

        Dossiê ainda não construído é `409 ROUND_STAGE_NOT_READY`; dossiê que não passa na
        revalidação é `422` — a tela nunca renderiza dossiê inválido.
        """
        _require_valuation_reviewer(principal)
        record = _load_valuation_round(session, round_id=round_id, tenant_id=principal.tenant_id)
        revision = head_revision(session, round_id=record.id, tenant_id=principal.tenant_id)
        document = require_document(
            revision,
            "amendment_dossier_json",
            stage=STAGE_DOSSIER,
            detail="a rodada ainda não tem dossiê de aditivo construído",
        )
        return _dossier_payload(record, document=document, dossier=_revalidated_dossier(document))

    # -- Orçamento-base de obra (F-020, ADR-0038) ---------------------------------------
    #
    # Espelho de `/v1/valuation-rounds*`, com a mesma disciplina — papel como primeira linha
    # de todo handler (inclusive de leitura), `Idempotency-Key` em todo POST, `base_version`
    # em toda mutação e `problem+json` com código estável. O que muda é a fronteira do
    # ADR-0027: aqui há CASCATA de fontes de preço e BDI, e não há contrato, período nem
    # saldo.
    #
    # Aprovação existe e é PRÓPRIA desde a F-035 (ADR-0046), e por isso o papel não é um só:
    # a LEITURA aceita `orcamentista` ou `aprovador` (`_require_estimate_reader`), a mutação
    # da cadeia e o despacho continuam exigindo `orcamentista`, e só `.../estimate/approve`
    # exige `aprovador`.

    def _load_estimate_round(
        session: Session, *, round_id: UUID, tenant_id: str
    ) -> EstimateRoundRecord:
        """A rodada do tenant, ou `404`. Rodada de outro tenant é indistinguível de ausente."""
        record = estimate_rounds.load_round(session, round_id=str(round_id), tenant_id=tenant_id)
        if record is None:
            raise _problem(
                "NOT_FOUND", status.HTTP_404_NOT_FOUND, "Rodada de orçamento não encontrada."
            )
        return record

    def _estimate_round_heads(
        session: Session, *, tenant_id: str, round_ids: Sequence[str]
    ) -> dict[str, EstimateRoundRevisionRecord]:
        """Cabeça de cada rodada da página, numa consulta só (espelho da medição)."""
        if not round_ids:
            return {}
        latest = (
            select(
                EstimateRoundRevisionRecord.round_id.label("round_id"),
                func.max(EstimateRoundRevisionRecord.version).label("version"),
            )
            .where(
                EstimateRoundRevisionRecord.tenant_id == tenant_id,
                EstimateRoundRevisionRecord.round_id.in_(round_ids),
            )
            .group_by(EstimateRoundRevisionRecord.round_id)
            .subquery()
        )
        records = session.scalars(
            select(EstimateRoundRevisionRecord)
            .join(
                latest,
                and_(
                    EstimateRoundRevisionRecord.round_id == latest.c.round_id,
                    EstimateRoundRevisionRecord.version == latest.c.version,
                ),
            )
            .where(EstimateRoundRevisionRecord.tenant_id == tenant_id)
        )
        return {record.round_id: record for record in records}

    def _estimate_cascade(record: EstimateRoundRecord) -> list[PriceCatalog]:
        """Os catálogos da cascata NA ORDEM instalada, decodificados uma vez por digest.

        O cache é o mesmo da medição de propósito: ele é chaveado pelo digest do objeto,
        que é conteúdo idêntico byte a byte por construção, e não por rodada nem por
        tenant. Objeto sumido, divergente ou ilegível recusa com `CATALOG_REQUIRED`.
        """
        return estimate_rounds.load_cascade(
            application.state.artifact_store, record, cache=application.state.catalog_cache
        )

    def _estimate_cascade_response(record: EstimateRoundRecord) -> EstimateCascadeResponse:
        return EstimateCascadeResponse(
            round_id=UUID(record.id),
            version=record.version,
            cascade=estimate_rounds.cascade_entry_payload(estimate_rounds.cascade_entries(record)),
        )

    def _estimate_plate_response(
        record: EstimateRoundRecord,
        revision: EstimateRoundRevisionRecord | None,
        *,
        tenant: str,
    ) -> ValuationPlateResponse:
        """Metadados da prancha e, quando a página já foi promovida, a URL assinada dela.

        Reusa o modelo de resposta da medição porque a prancha é o MESMO conceito nas duas
        cadeias — um PDF ingerido e uma página promovida. `image_url` nulo é estado honesto;
        chave gravada fora do prefixo do tenant é tratada como inexistente e o presign nunca
        chega a ser chamado.
        """
        plate = estimate_rounds.require_plate(record)
        refs = {} if revision is None else dict(revision.artifact_refs_json or {})
        image_key = refs.get(PLATE_IMAGE_REF)
        image_url: str | None = None
        if image_key is not None:
            image_url = signed_artifact_url(
                application.state.artifact_store, object_key=image_key, tenant_id=tenant
            )
            if image_url is None:
                raise _problem(
                    "NOT_FOUND",
                    status.HTTP_404_NOT_FOUND,
                    "Imagem da prancha não encontrada.",
                )
        return ValuationPlateResponse(
            round_id=UUID(record.id),
            version=record.version,
            upload_id=UUID(plate.upload_id),
            source_sha256=plate.source_sha256,
            page_count=plate.page_count,
            image_url=image_url,
        )

    def _estimate_takeoff_payload(
        record: EstimateRoundRecord, revision: EstimateRoundRevisionRecord | None
    ) -> dict[str, Any]:
        stored = estimate_rounds.require_document(
            revision,
            "takeoff_packet_json",
            stage=STAGE_TAKEOFF,
            detail="a rodada ainda não tem pacote de takeoff publicado",
        )
        packet = estimate_rounds.require_takeoff_packet(revision)
        registered = registered_item_ids(
            None if revision is None else revision.takeoff_registration_json
        )
        return {
            "round_id": record.id,
            "version": record.version,
            "packet": anchored_packet(packet, registered),
            "packet_sha256": document_digest(stored),
            "review_status": review_status(packet),
            **takeoff_counts(packet),
            **anchor_counts(packet, registered),
        }

    def _estimate_suggestions_payload(
        record: EstimateRoundRecord,
        *,
        document: Mapping[str, Any],
        suggestions: CodeSuggestionSet,
        computed: bool,
        notes: list[str],
        precedent_blocks: list[dict[str, object]] | None = None,
    ) -> dict[str, Any]:
        """A shortlist como a tela a recebe, mais o precedente quando quem lê é o `GET`.

        `precedent_blocks` é `None` no recompute e lista (possivelmente vazia) no `GET`, e a
        chave `precedents` só existe quando ela é lista. A assimetria é deliberada: a
        resposta do recompute é gravada VERBATIM no registro de idempotência e devolvida de
        novo num replay, e congelar ali uma observação derivada faria uma releitura servir
        precedente velho como se fosse o corrente. O `GET` é a leitura canônica da shortlist,
        e é dele que a tela relê o bloco depois de qualquer ato.
        """
        payload: dict[str, Any] = {
            "round_id": record.id,
            "version": record.version,
            "suggestions": suggestions.model_dump(mode="json"),
            "suggestions_sha256": document_digest(document),
            "computed": computed,
            "matching": matching_of(suggestions),
            "semantic_notes": notes,
        }
        if precedent_blocks is not None:
            payload["precedents"] = precedent_blocks
        return payload

    def _estimate_precedents(
        session: Session,
        record: EstimateRoundRecord,
        packet: TakeoffPacket,
        *,
        tenant_id: str,
    ) -> list[dict[str, object]]:
        """O precedente dos itens confirmados desta rodada, sob a fonte de preço DELA.

        Leitura pura: um `SELECT` sobre o que o fechamento de pacote e a semeadura já
        gravaram (F-044 T2). **Nenhuma chamada paga entra aqui** e nenhuma revisão nasce — o
        `GET` da shortlist continua sem custo e sem avançar a versão da rodada (ADR-0054 D7).

        A fonte de preço é a do catálogo **cabeça** da cascata, que é o mesmo digest que
        amarra o conjunto de sugestões e o de decisões à rodada (`CodeSuggestionSet.
        catalog_sha256`). É uma fonte só, e não a cascata inteira, por duas razões que se
        somam: a contagem de praças de duas fontes não pode ser unida sem inflar o número que
        a tela mostra como argumento de autoridade, e o aceite do pacote cita UM
        `catalog_sha256` para os N códigos — oferecer códigos de duas tabelas produziria um
        pacote que a decisão seguinte não teria como gravar. **Consequência declarada**: um
        precedente confirmado citando a segunda fonte da cascata não é oferecido de volta.

        Cascata vazia devolve lista vazia em vez de recusar: sem catálogo, todo código do
        precedente seria omitido de qualquer forma, e é o mesmo resultado por um caminho que
        não muda o que esta leitura já respondia antes do bloco existir.
        """
        if not estimate_rounds.cascade_entries(record):
            return []
        catalog = _estimate_cascade(record)[0]
        items = packet.confirmed_items()
        entries = precedents.precedents_for(
            session,
            tenant_id,
            [item.label for item in items],
            catalog.source_sha256,
        )
        return precedents.shortlist_precedents(entries, items, catalog)

    def _estimate_assignments_payload(
        record: EstimateRoundRecord,
        *,
        packet: TakeoffPacket,
        assignments: CodeAssignmentSet | None,
        document: Mapping[str, Any] | None,
    ) -> dict[str, Any]:
        return {
            "round_id": record.id,
            "version": record.version,
            "assignments": None if assignments is None else assignments.model_dump(mode="json"),
            "assignments_sha256": None if document is None else document_digest(document),
            "confirmed": 0 if assignments is None else count_status(assignments, "confirmed"),
            "rejected": 0 if assignments is None else count_status(assignments, "rejected"),
            "closed": 0 if assignments is None else count_closed(assignments),
            "pending_items": [
                item_payload(item) for item in pending_code_items(packet, assignments)
            ],
        }

    def _estimate_payload(
        record: EstimateRoundRecord,
        revision: EstimateRoundRevisionRecord | None,
        *,
        document: Mapping[str, Any],
        estimate: Estimate,
    ) -> dict[str, Any]:
        """O orçamento como a tela o recebe. Dinheiro sai como TEXTO, e URL nunca sai daqui.

        Os totais viajam em texto pelo mesmo motivo do boletim: são `Decimal` truncados no
        centavo, e serializá-los como número de JSON devolveria um binário aproximado do
        valor que o domínio acabou de fixar.

        A URL assinada da planilha **não** entra: esta forma é a que o registro de
        idempotência guarda no banco, e gravar uma URL assinada seria persistir uma
        credencial de leitura num lugar que ninguém trata como segredo. Ela sai só no `GET`,
        montada na hora.

        O bloco de aprovação é derivado do orçamento REVALIDADO que a rota já tem em mãos, e
        não relido da revisão: as duas leituras responderiam a mesma coisa no caminho feliz,
        e usar a que a rota acabou de validar é o que faz a resposta do ato de assinar já
        sair com a aprovação que ele mesmo escreveu.
        """
        digests = {} if revision is None else dict(revision.artifact_digests_json or {})
        return {
            "round_id": record.id,
            "version": record.version,
            "estimate": estimate.model_dump(mode="json"),
            "estimate_sha256": document_digest(document),
            "bdi_percent": str(estimate.bdi_percent),
            "total_amount_without_bdi": str(estimate.total_amount_without_bdi),
            "total_amount": str(estimate.total_amount),
            "unpriced_item_ids": list(estimate.unpriced_item_ids),
            "workbook_present": estimate_rounds.estimate_workbook_ref(revision) is not None,
            "workbook_sha256": digests.get(estimate_rounds.ESTIMATE_WORKBOOK_DIGEST),
            "approval": estimate_rounds.approval_payload(estimate),
            **estimate_rounds.target_state(record, revision),
        }

    def _revalidated_estimate(document: Mapping[str, Any]) -> Estimate:
        """Orçamento gravado, revalidado na leitura: quem recomputa os totais é o modelo.

        `Estimate` refaz o BDI de cada linha, o total de cada linha, os dois totais do
        orçamento e o 1:1 com a memória de cálculo, além de conferir que toda linha aponta
        para uma fonte que está na cascata declarada. Servir o total como ele foi gravado
        faria um orçamento adulterado no banco passar por bom.
        """
        try:
            return Estimate.model_validate(dict(document))
        except ValidationError as error:
            raise _valuation_model_problem(error) from error

    def _enqueue_estimate_plate_extraction(
        *, round_id: str, extraction_id: str, tenant_id: str
    ) -> None:
        """Publica o comando com o intent já durável; falha de transporte é 503 repetível."""
        queue: QueueAdapter = application.state.queue
        try:
            queue.enqueue_estimate_plate_extraction(
                round_id=round_id,
                extraction_id=extraction_id,
                tenant_id=tenant_id,
            )
        except QUEUE_TRANSPORT_ERRORS as error:
            raise _problem(
                "PROCESSING_UNAVAILABLE",
                status.HTTP_503_SERVICE_UNAVAILABLE,
                "Extração registrada; repita o mesmo comando para reenfileirar com segurança.",
            ) from error

    def _enqueue_estimate_overlay_rerender(
        *, round_id: str, tenant_id: str, packet_sha256: str
    ) -> None:
        """Publica o re-render do overlay. Falha de transporte NÃO derruba a decisão.

        Mesma assimetria deliberada da medição (ADR-0030): o ato é a decisão do
        orçamentista, que já está durável quando este comando é publicado, e traduzir a
        recusa da fila em `503` faria o cliente supor que a decisão não valeu.
        """
        queue: QueueAdapter = application.state.queue
        with suppress(*QUEUE_TRANSPORT_ERRORS):
            queue.enqueue_estimate_takeoff_overlay_rerender(
                round_id=round_id, tenant_id=tenant_id, packet_sha256=packet_sha256
            )

    @application.post(
        "/v1/estimate-rounds",
        response_model=EstimateRoundResponse,
        status_code=status.HTTP_201_CREATED,
        tags=["estimate"],
    )
    async def create_estimate_round(
        payload: CreateEstimateRoundRequest,
        request: Request,
        principal: AuthenticatedPrincipal,
        session: DatabaseSession,
        idempotency_key: Annotated[str, Depends(_require_idempotency)],
    ) -> EstimateRoundResponse:
        """Abre a rodada do orçamento-base; a cascata de fontes entra depois, em ordem."""
        _require_valuation_reviewer(principal)
        request_hash = _request_hash(payload)
        existing = _idempotent_response(
            session,
            principal=principal,
            operation="estimate-rounds.create",
            key=idempotency_key,
            request_hash=request_hash,
        )
        if existing is not None:
            return EstimateRoundResponse.model_validate(existing)

        target_amount = (
            None
            if payload.target_amount is None
            else str(estimate_rounds.parse_target_amount(payload.target_amount))
        )
        if payload.pricing_regime is not None:
            # Cascata vazia por construção na abertura: a rodada nasce sem fonte. A recusa
            # possível aqui é só a da mão única, e ela vale desde o primeiro instante.
            estimate_rounds.ensure_regime_declarable(
                payload.pricing_regime, current=None, entries=()
            )
        now = datetime.now(UTC)
        round_id = new_uuid7()
        record = EstimateRoundRecord(
            id=str(round_id),
            tenant_id=principal.tenant_id,
            worksite_key=payload.worksite_key,
            worksite_name=payload.worksite_name,
            reference_label=payload.reference_label,
            address=payload.address,
            target_amount=target_amount,
            target_label=payload.target_label,
            pricing_regime=payload.pricing_regime,
            status="OPEN",
            version=1,
            catalog_cascade_json=[],
            extraction_status="idle",
            created_by=principal.subject,
            created_at=now,
            updated_at=now,
        )
        session.add(record)
        response = EstimateRoundResponse(
            round_id=round_id,
            version=record.version,
            status=record.status,
            created_at=now,
        )
        _store_idempotent_response(
            session,
            principal=principal,
            operation="estimate-rounds.create",
            key=idempotency_key,
            request_hash=request_hash,
            response=response,
        )
        _record_audit(
            session,
            principal=principal,
            action="ESTIMATE_ROUND_CREATED",
            resource_type="estimate_round",
            resource_id=str(round_id),
            request_id=request.state.request_id,
        )
        _record_round_event(
            session,
            principal=principal,
            event_type=EVENT_ESTIMATE_ACTION_RECORDED,
            action="ESTIMATE_ROUND_CREATED",
            record=record,
        )
        session.commit()
        return response

    @application.get(
        "/v1/estimate-rounds",
        response_model=EstimateRoundPage,
        tags=["estimate"],
    )
    async def list_estimate_rounds(
        principal: AuthenticatedPrincipal,
        session: DatabaseSession,
        limit: Annotated[int, Query(ge=1, le=100)] = 20,
        cursor: str | None = None,
    ) -> EstimateRoundPage:
        """Rodadas do tenant, da mais recente para a mais antiga, com cursor opaco."""
        _require_estimate_reader(principal)
        query = select(EstimateRoundRecord).where(
            EstimateRoundRecord.tenant_id == principal.tenant_id
        )
        if cursor is not None:
            created_at, identifier = _decode_round_cursor(cursor)
            # Forma explícita em vez de comparação de tupla, como na medição: row values
            # dependem da versão do SQLite.
            query = query.where(
                or_(
                    EstimateRoundRecord.created_at < created_at,
                    and_(
                        EstimateRoundRecord.created_at == created_at,
                        EstimateRoundRecord.id < identifier,
                    ),
                )
            )
        records = list(
            session.scalars(
                query.order_by(
                    EstimateRoundRecord.created_at.desc(), EstimateRoundRecord.id.desc()
                ).limit(limit + 1)
            )
        )
        page = records[:limit]
        heads = _estimate_round_heads(
            session,
            tenant_id=principal.tenant_id,
            round_ids=[record.id for record in page],
        )
        return EstimateRoundPage(
            items=[
                EstimateRoundSummary(
                    round_id=UUID(record.id),
                    worksite_key=record.worksite_key,
                    worksite_name=record.worksite_name,
                    reference_label=record.reference_label,
                    version=record.version,
                    status=record.status,
                    stage=estimate_rounds.current_stage(record, heads.get(record.id)),
                    extraction_status=record.extraction_status,
                    cascade_origins=[
                        entry.origin for entry in estimate_rounds.cascade_entries(record)
                    ],
                    target_amount=record.target_amount,
                    target_label=record.target_label,
                    pricing_regime=record.pricing_regime,
                    created_at=record.created_at,
                    updated_at=record.updated_at,
                )
                for record in page
            ],
            next_cursor=_encode_round_cursor(page[-1]) if len(records) > limit and page else None,
        )

    @application.get(
        "/v1/estimate-rounds/{round_id}",
        response_model=dict[str, Any],
        tags=["estimate"],
    )
    async def get_estimate_round(
        round_id: UUID,
        principal: AuthenticatedPrincipal,
        session: DatabaseSession,
    ) -> dict[str, Any]:
        """Estado da rodada por etapa, com a cascata na ordem que decide a precificação."""
        _require_estimate_reader(principal)
        record = _load_estimate_round(session, round_id=round_id, tenant_id=principal.tenant_id)
        revision = estimate_rounds.head_revision(
            session, round_id=record.id, tenant_id=principal.tenant_id
        )
        return estimate_rounds.round_state_payload(record, revision)

    @application.post(
        "/v1/estimate-rounds/{round_id}/target",
        response_model=dict[str, Any],
        tags=["estimate"],
    )
    async def set_estimate_target(
        round_id: UUID,
        payload: SetEstimateTargetRequest,
        request: Request,
        principal: AuthenticatedPrincipal,
        session: DatabaseSession,
        idempotency_key: Annotated[str, Depends(_require_idempotency)],
    ) -> dict[str, Any]:
        """Declara ou edita o teto de verba da rodada (ADR-0040); sem rota de remoção.

        O teto é dado da RODADA, não do artefato (decisão 1): grava só as duas colunas
        novas de `estimate_rounds` e avança a versão da rodada, como qualquer outro ato
        humano. Nenhuma revisão append-only nasce daqui — o teto não é artefato da cadeia,
        é parâmetro da rodada, como o BDI.
        """
        _require_valuation_reviewer(principal)
        operation = f"estimate-rounds.target:{round_id}"
        request_hash = _request_hash(payload)
        existing = _idempotent_response(
            session,
            principal=principal,
            operation=operation,
            key=idempotency_key,
            request_hash=request_hash,
        )
        if existing is not None:
            return existing

        record = _load_estimate_round(session, round_id=round_id, tenant_id=principal.tenant_id)
        estimate_rounds.require_base_version(record, payload.base_version)
        amount = estimate_rounds.parse_target_amount(payload.target_amount)
        record.target_amount = str(amount)
        record.target_label = payload.target_label
        record.version += 1
        record.updated_at = datetime.now(UTC)
        revision = estimate_rounds.head_revision(
            session, round_id=record.id, tenant_id=principal.tenant_id
        )
        response: dict[str, Any] = {
            "round_id": record.id,
            "version": record.version,
            **estimate_rounds.target_state(record, revision),
        }
        _store_idempotent_response(
            session,
            principal=principal,
            operation=operation,
            key=idempotency_key,
            request_hash=request_hash,
            response=ValuationDocumentResponse(response),
        )
        _record_audit(
            session,
            principal=principal,
            action="ESTIMATE_TARGET_SET",
            resource_type="estimate_round",
            resource_id=record.id,
            request_id=request.state.request_id,
        )
        _record_round_event(
            session,
            principal=principal,
            event_type=EVENT_ESTIMATE_ACTION_RECORDED,
            action="ESTIMATE_TARGET_SET",
            record=record,
        )
        session.commit()
        return response

    @application.post(
        "/v1/estimate-rounds/{round_id}/regime",
        response_model=dict[str, Any],
        tags=["estimate"],
    )
    async def set_estimate_regime(
        round_id: UUID,
        payload: SetEstimateRegimeRequest,
        request: Request,
        principal: AuthenticatedPrincipal,
        session: DatabaseSession,
        idempotency_key: Annotated[str, Depends(_require_idempotency)],
    ) -> dict[str, Any]:
        """Declara que a rodada corre sob contrato licitado (ADR-0045); sem volta.

        Mesmo desenho do teto (ADR-0040, decisão 2): o regime é dado da RODADA, grava uma
        coluna de `estimate_rounds` e avança a versão da rodada como qualquer ato humano.
        Nenhuma revisão append-only nasce daqui, e o `Estimate` não ganha campo — o
        orçamento continua puro e recomputável.

        Duas recusas, as duas antes de gravar qualquer coisa: `pre_bid` recusa com
        `409 ESTIMATE_REGIME_IRREVERSIBLE`, porque ausência de regime já é a pré-licitação
        e porque uma rodada declarada não volta atrás; cascata com fonte fora da tabela
        contratual recusa com `409 ESTIMATE_REGIME_CASCADE_DIRTY`, e a saída é remover a
        fonte por `POST .../catalogs/remove`, que já existe. Rodada sob contrato nunca
        contém fonte proibida — nem por declaração posterior, nem por instalação.
        """
        _require_valuation_reviewer(principal)
        operation = f"estimate-rounds.regime:{round_id}"
        request_hash = _request_hash(payload)
        existing = _idempotent_response(
            session,
            principal=principal,
            operation=operation,
            key=idempotency_key,
            request_hash=request_hash,
        )
        if existing is not None:
            return existing

        record = _load_estimate_round(session, round_id=round_id, tenant_id=principal.tenant_id)
        estimate_rounds.require_base_version(record, payload.base_version)
        estimate_rounds.ensure_regime_declarable(
            payload.pricing_regime,
            current=record.pricing_regime,
            entries=estimate_rounds.cascade_entries(record),
        )
        record.pricing_regime = payload.pricing_regime
        record.version += 1
        record.updated_at = datetime.now(UTC)
        revision = estimate_rounds.head_revision(
            session, round_id=record.id, tenant_id=principal.tenant_id
        )
        response: dict[str, Any] = {
            "round_id": record.id,
            "version": record.version,
            **estimate_rounds.regime_state(record, estimate_rounds.assignments_of(revision)),
        }
        _store_idempotent_response(
            session,
            principal=principal,
            operation=operation,
            key=idempotency_key,
            request_hash=request_hash,
            response=ValuationDocumentResponse(response),
        )
        _record_audit(
            session,
            principal=principal,
            action="ESTIMATE_REGIME_DECLARED",
            resource_type="estimate_round",
            resource_id=record.id,
            request_id=request.state.request_id,
        )
        session.commit()
        return response

    @application.get(
        "/v1/estimate-rounds/{round_id}/reference-catalogs",
        response_model=EstimateReferenceCatalogListResponse,
        tags=["estimate"],
    )
    async def list_estimate_reference_catalogs(
        round_id: UUID,
        principal: AuthenticatedPrincipal,
        session: DatabaseSession,
    ) -> EstimateReferenceCatalogListResponse:
        """As tabelas do acervo que ESTA rodada pode instalar (F-037, ADR-0047).

        A listagem vive sob a rodada, e não numa rota global, porque a rodada é quem
        conhece o regime: sob contrato licitado, o servidor já devolve só a origem que a
        instalação aceitaria. Uma rota global obrigaria a tela a reimplementar a regra do
        regime e a descobrir a divergência num `409` — exatamente o que a F-033 evitou ao
        publicar `allowed_cascade_origins` do servidor.

        Dois filtros, e só dois: **em circulação** (o que foi retirado deixa de ser
        oferecido, sem sumir do registro nem quebrar a rodada que já o instalou) e **aceito
        pelo regime**. Origem já instalada continua aparecendo: instalar a segunda da mesma
        origem recusa com `ESTIMATE_CASCADE_ORIGIN_DUPLICATE`, e esconder a tabela faria a
        lista mentir sobre o que o acervo tem.

        Leitura livre para quem opera o orçamento (decisão 5): o acervo é público, não há
        entitlement por tenant e não há tenant a comparar. O papel é exigido antes de
        qualquer lookup, e a rodada continua sendo do tenant — rodada alheia é `404`.
        """
        _require_estimate_reader(principal)
        record = _load_estimate_round(session, round_id=round_id, tenant_id=principal.tenant_id)
        published = session.scalars(
            select(ReferenceCatalogRecord).where(ReferenceCatalogRecord.status == STATUS_AVAILABLE)
        ).all()
        offered = [
            catalog
            for catalog in published
            if estimate_rounds.origin_allowed_under_regime(
                catalog.origin, regime=record.pricing_regime
            )
        ]
        # Ordenação em Python, como na listagem de plataforma: SQLite (testes) e PostgreSQL
        # (hospedado) não ordenam texto do mesmo jeito, e a tela lê a ordem.
        ordered = sorted(
            offered, key=lambda catalog: (catalog.origin, catalog.reference_month, catalog.id)
        )
        return EstimateReferenceCatalogListResponse(
            round_id=round_id,
            catalogs=[
                EstimateReferenceCatalogOption(
                    reference_catalog_id=UUID(catalog.id),
                    display_name=catalog.display_name,
                    origin=catalog.origin,
                    reference_month=catalog.reference_month,
                    entry_count=catalog.entry_count,
                    source_sha256=catalog.source_sha256,
                )
                for catalog in ordered
            ],
        )

    @application.post(
        "/v1/estimate-rounds/{round_id}/catalogs",
        response_model=EstimateCascadeResponse,
        status_code=status.HTTP_201_CREATED,
        tags=["estimate"],
    )
    async def install_estimate_catalog(
        round_id: UUID,
        payload: InstallEstimateCatalogRequest,
        request: Request,
        principal: AuthenticatedPrincipal,
        session: DatabaseSession,
        idempotency_key: Annotated[str, Depends(_require_idempotency)],
    ) -> EstimateCascadeResponse:
        """Instala uma fonte de preço no FIM da cascata; a posição é a precedência.

        A fonte vem de UM de dois caminhos, nunca dos dois: a tabela escolhida no acervo da
        plataforma (`reference_catalog_id`) ou o arquivo próprio do cliente (`upload_id`).
        A entrada gravada é a mesma nos dois casos, com a **procedência** declarada ao lado
        (ADR-0047 decisão 7) — e todas as regras da cascata valem iguais, porque o que muda
        é de onde o arquivo veio, não o que ele é.

        O catálogo é lido e validado ANTES de a entrada existir, como na criação da rodada
        de medição: uma fonte que não valida aqui viraria uma cascata inutilizável em toda
        etapa seguinte. Segunda fonte da mesma origem recusa com
        `409 ESTIMATE_CASCADE_ORIGIN_DUPLICATE` — o mesmo código que o domínio usa —, e não
        na montagem do orçamento, quando já não haveria o que corrigir sem abrir rodada nova.

        Na rodada sob contrato licitado (ADR-0045), fonte de origem fora da tabela
        contratual recusa aqui com `409 ESTIMATE_CASCADE_ORIGIN_FORBIDDEN`, pelo mesmo
        motivo e no mesmo instante: a alternativa seria descobrir o erro na medição, sobre
        serviço já executado. Vale igual para a tabela do acervo, que por isso nem chega a
        ser oferecida na escolha daquela rodada.
        """
        _require_valuation_reviewer(principal)
        provenance, source_id = _catalog_source(payload)
        operation = f"estimate-rounds.catalogs:{round_id}"
        request_hash = _request_hash(payload)
        existing = _idempotent_response(
            session,
            principal=principal,
            operation=operation,
            key=idempotency_key,
            request_hash=request_hash,
        )
        if existing is not None:
            return EstimateCascadeResponse.model_validate(existing)

        record = _load_estimate_round(session, round_id=round_id, tenant_id=principal.tenant_id)
        estimate_rounds.require_base_version(record, payload.base_version)
        entries = estimate_rounds.cascade_entries(record)
        upload: UploadRecord | None = None
        reference: ReferenceCatalogRecord | None = None
        if provenance == estimate_rounds.PROVENANCE_TENANT_UPLOAD:
            # O filtro por tenant do upload continua exatamente onde estava: o acervo é a
            # exceção autorizada, o arquivo do cliente não.
            upload = _require_valuation_upload(
                session,
                application,
                upload_id=source_id,
                principal=principal,
                content_type=CATALOG_CONTENT_TYPE,
                storage_flavor=runtime_settings.storage_flavor,
            )
            object_key = upload.object_key
            object_sha256 = upload.sha256.lower()
            unreadable_code = "INVALID_UPLOAD"
        else:
            reference = _require_available_reference_catalog(
                session, reference_catalog_id=source_id
            )
            object_key = reference.object_key
            object_sha256 = reference.object_sha256
            unreadable_code = "REFERENCE_CATALOG_UNREADABLE"

        catalog, summary = _install_catalog(
            application,
            object_key=object_key,
            object_sha256=object_sha256,
            unreadable_code=unreadable_code,
        )
        estimate_rounds.ensure_source_installable(entries, catalog, regime=record.pricing_regime)

        installed = estimate_rounds.installed_entry(
            provenance=provenance,
            upload_id=None if upload is None else upload.id,
            reference_catalog_id=None if reference is None else reference.id,
            object_key=object_key,
            object_sha256=object_sha256,
            catalog=catalog,
            summary=summary,
        )
        # Lista NOVA em vez de `append`: a coluna é JSON e o SQLAlchemy não observa mutação
        # no lugar de um `list` — sem reatribuir, a instalação não chegaria ao `UPDATE`.
        record.catalog_cascade_json = [
            *(entry_document for entry_document in record.catalog_cascade_json or []),
            installed,
        ]
        record.version += 1
        record.updated_at = datetime.now(UTC)
        if upload is not None:
            upload.status = "VERIFIED"
        response = _estimate_cascade_response(record)
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
            action="ESTIMATE_CATALOG_INSTALLED",
            resource_type="estimate_round",
            resource_id=record.id,
            request_id=request.state.request_id,
        )
        _record_round_event(
            session,
            principal=principal,
            event_type=EVENT_ESTIMATE_ACTION_RECORDED,
            action="ESTIMATE_CATALOG_INSTALLED",
            record=record,
        )
        session.commit()
        return response

    @application.post(
        "/v1/estimate-rounds/{round_id}/catalogs/order",
        response_model=EstimateCascadeResponse,
        tags=["estimate"],
    )
    async def reorder_estimate_cascade(
        round_id: UUID,
        payload: ReorderEstimateCascadeRequest,
        request: Request,
        principal: AuthenticatedPrincipal,
        session: DatabaseSession,
        idempotency_key: Annotated[str, Depends(_require_idempotency)],
    ) -> EstimateCascadeResponse:
        """Reordena a cascata instalada; nenhuma fonte entra nem sai por aqui.

        Reordenar é ATO humano com consequência visível: a shortlist e a busca passam a
        devolver o bloco da fonte promovida primeiro, e é assim que o orçamentista muda a
        preferência de tabela sem que nada seja recalculado escondido. Por isso avança o
        token de concorrência da rodada.
        """
        _require_valuation_reviewer(principal)
        operation = f"estimate-rounds.catalogs-order:{round_id}"
        request_hash = _request_hash(payload)
        existing = _idempotent_response(
            session,
            principal=principal,
            operation=operation,
            key=idempotency_key,
            request_hash=request_hash,
        )
        if existing is not None:
            return EstimateCascadeResponse.model_validate(existing)

        record = _load_estimate_round(session, round_id=round_id, tenant_id=principal.tenant_id)
        estimate_rounds.require_base_version(record, payload.base_version)
        entries = estimate_rounds.require_cascade(record)
        estimate_rounds.require_cascade_unlocked(
            estimate_rounds.head_revision(
                session, round_id=record.id, tenant_id=principal.tenant_id
            )
        )
        record.catalog_cascade_json = estimate_rounds.reordered_cascade(entries, payload.cascade)
        record.version += 1
        record.updated_at = datetime.now(UTC)
        response = _estimate_cascade_response(record)
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
            action="ESTIMATE_CASCADE_REORDERED",
            resource_type="estimate_round",
            resource_id=record.id,
            request_id=request.state.request_id,
        )
        _record_round_event(
            session,
            principal=principal,
            event_type=EVENT_ESTIMATE_ACTION_RECORDED,
            action="ESTIMATE_CASCADE_REORDERED",
            record=record,
        )
        session.commit()
        return response

    @application.post(
        "/v1/estimate-rounds/{round_id}/catalogs/remove",
        response_model=EstimateCascadeResponse,
        tags=["estimate"],
    )
    async def remove_estimate_cascade_source(
        round_id: UUID,
        payload: RemoveEstimateCascadeSourceRequest,
        request: Request,
        principal: AuthenticatedPrincipal,
        session: DatabaseSession,
        idempotency_key: Annotated[str, Depends(_require_idempotency)],
    ) -> EstimateCascadeResponse:
        """Remove uma fonte da cascata instalada, citada pelo `source_sha256` dela.

        Remover é decisão de código recusa quando decisão de código já registrada citou a
        fonte: apagar decisão do orçamentista não é ato desta API (`ESTIMATE_CASCADE_LOCKED`,
        mesmo código da reordenação, aqui por FONTE em vez de pela cascata inteira). Fonte
        que não está instalada recusa com o mesmo código da reordenação
        (`ESTIMATE_CASCADE_ORDER_INVALID`) — o corpo cita algo que a cascata não reconhece.
        """
        _require_valuation_reviewer(principal)
        operation = f"estimate-rounds.catalogs-remove:{round_id}"
        request_hash = _request_hash(payload)
        existing = _idempotent_response(
            session,
            principal=principal,
            operation=operation,
            key=idempotency_key,
            request_hash=request_hash,
        )
        if existing is not None:
            return EstimateCascadeResponse.model_validate(existing)

        record = _load_estimate_round(session, round_id=round_id, tenant_id=principal.tenant_id)
        estimate_rounds.require_base_version(record, payload.base_version)
        entries = estimate_rounds.require_cascade(record)
        estimate_rounds.require_cascade_source_unlocked(
            estimate_rounds.head_revision(
                session, round_id=record.id, tenant_id=principal.tenant_id
            ),
            payload.source_sha256,
        )
        record.catalog_cascade_json = estimate_rounds.removed_cascade(
            entries, payload.source_sha256
        )
        record.version += 1
        record.updated_at = datetime.now(UTC)
        response = _estimate_cascade_response(record)
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
            action="ESTIMATE_CASCADE_SOURCE_REMOVED",
            resource_type="estimate_round",
            resource_id=record.id,
            request_id=request.state.request_id,
        )
        _record_round_event(
            session,
            principal=principal,
            event_type=EVENT_ESTIMATE_ACTION_RECORDED,
            action="ESTIMATE_CASCADE_SOURCE_REMOVED",
            record=record,
        )
        session.commit()
        return response

    @application.post(
        "/v1/estimate-rounds/{round_id}/plate",
        response_model=ValuationPlateResponse,
        tags=["estimate"],
    )
    async def associate_estimate_plate(
        round_id: UUID,
        payload: AssociatePlateRequest,
        request: Request,
        principal: AuthenticatedPrincipal,
        session: DatabaseSession,
        idempotency_key: Annotated[str, Depends(_require_idempotency)],
    ) -> ValuationPlateResponse:
        """Associa o PDF já enviado pelo presign; a API não renderiza nem lê a prancha."""
        _require_valuation_reviewer(principal)
        operation = f"estimate-rounds.plate:{round_id}"
        request_hash = _request_hash(payload)
        existing = _idempotent_response(
            session,
            principal=principal,
            operation=operation,
            key=idempotency_key,
            request_hash=request_hash,
        )
        if existing is not None:
            return ValuationPlateResponse.model_validate(existing)

        record = _load_estimate_round(session, round_id=round_id, tenant_id=principal.tenant_id)
        estimate_rounds.require_base_version(record, payload.base_version)
        if record.plate_object_key is not None:
            raise _problem(
                "ROUND_PLATE_ALREADY_PRESENT",
                status.HTTP_409_CONFLICT,
                "A rodada já tem uma prancha associada.",
            )
        upload = _require_valuation_upload(
            session,
            application,
            upload_id=payload.upload_id,
            principal=principal,
            content_type=PDF_CONTENT_TYPE,
            storage_flavor=runtime_settings.storage_flavor,
        )
        now = datetime.now(UTC)
        record.plate_upload_id = str(payload.upload_id)
        record.plate_object_key = upload.object_key
        record.plate_source_sha256 = upload.sha256.lower()
        record.version += 1
        record.updated_at = now
        upload.status = "VERIFIED"
        response = _estimate_plate_response(record, None, tenant=principal.tenant_id)
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
            action="ESTIMATE_PLATE_ASSOCIATED",
            resource_type="estimate_round",
            resource_id=record.id,
            request_id=request.state.request_id,
        )
        _record_round_event(
            session,
            principal=principal,
            event_type=EVENT_ESTIMATE_ACTION_RECORDED,
            action="ESTIMATE_PLATE_ASSOCIATED",
            record=record,
        )
        session.commit()
        return response

    @application.get(
        "/v1/estimate-rounds/{round_id}/plate",
        response_model=ValuationPlateResponse,
        tags=["estimate"],
    )
    async def get_estimate_plate(
        round_id: UUID,
        principal: AuthenticatedPrincipal,
        session: DatabaseSession,
    ) -> ValuationPlateResponse:
        """Metadados e URL assinada da página promovida; a URL não vai para log nem auditoria."""
        _require_estimate_reader(principal)
        record = _load_estimate_round(session, round_id=round_id, tenant_id=principal.tenant_id)
        revision = estimate_rounds.head_revision(
            session, round_id=record.id, tenant_id=principal.tenant_id
        )
        return _estimate_plate_response(record, revision, tenant=principal.tenant_id)

    @application.post(
        "/v1/estimate-rounds/{round_id}/plate/extractions",
        response_model=ValuationExtractionResponse,
        status_code=status.HTTP_202_ACCEPTED,
        tags=["estimate"],
    )
    async def create_estimate_plate_extraction(
        round_id: UUID,
        payload: CreatePlateExtractionRequest,
        request: Request,
        principal: AuthenticatedPrincipal,
        session: DatabaseSession,
        idempotency_key: Annotated[str, Depends(_require_idempotency)],
    ) -> ValuationExtractionResponse:
        """Enfileira a extração paga da legenda; nenhum provider é chamado no request path."""
        _require_valuation_reviewer(principal)
        operation = f"estimate-rounds.extractions:{round_id}"
        request_hash = _request_hash(payload)
        existing = _idempotent_response(
            session,
            principal=principal,
            operation=operation,
            key=idempotency_key,
            request_hash=request_hash,
        )
        if existing is not None:
            replay = ValuationExtractionResponse.model_validate(existing)
            # Repetir o mesmo comando é o caminho de retomada quando a fila recusou: o
            # intent já está durável e o claim atômico do worker impede repagar o provider.
            _enqueue_estimate_plate_extraction(
                round_id=str(round_id),
                extraction_id=str(replay.extraction_id),
                tenant_id=principal.tenant_id,
            )
            return replay

        record = _load_estimate_round(session, round_id=round_id, tenant_id=principal.tenant_id)
        estimate_rounds.require_base_version(record, payload.base_version)
        estimate_rounds.require_plate(record)
        revision = estimate_rounds.head_revision(
            session, round_id=record.id, tenant_id=principal.tenant_id
        )
        if revision is not None and revision.takeoff_packet_json is not None:
            raise _problem(
                "ROUND_PLATE_ALREADY_PRESENT",
                status.HTTP_409_CONFLICT,
                "A rodada já tem pacote de takeoff publicado.",
            )
        if record.extraction_status in ("queued", "running"):
            raise _problem(
                "EXTRACTION_IN_PROGRESS",
                status.HTTP_409_CONFLICT,
                "Já existe uma extração em andamento nesta rodada.",
            )
        # Chamada paga de provider: entitlement contratual do tenant primeiro, e sem
        # enfileirar nada quando ele falta (ADR-0012).
        _require_active_ai_entitlement(
            session,
            principal,
            real_providers_enabled=runtime_settings.real_providers_enabled,
        )
        unavailable = extraction_unavailable(extraction_arm_spec())
        if unavailable is not None:
            raise _problem(
                "PROVIDER_UNAVAILABLE",
                status.HTTP_503_SERVICE_UNAVAILABLE,
                "A extração automática não está disponível neste ambiente.",
                {"code": unavailable.code},
            )

        now = datetime.now(UTC)
        extraction_id = new_uuid7()
        record.extraction_id = str(extraction_id)
        record.extraction_status = "queued"
        record.extraction_failure_code = None
        record.extraction_requested_by = principal.subject
        record.extraction_updated_at = now
        record.version += 1
        record.updated_at = now
        response = ValuationExtractionResponse(
            round_id=round_id,
            version=record.version,
            extraction_id=extraction_id,
            status=record.extraction_status,
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
            action="ESTIMATE_EXTRACTION_REQUESTED",
            resource_type="estimate_round",
            resource_id=record.id,
            request_id=request.state.request_id,
        )
        _record_round_event(
            session,
            principal=principal,
            event_type=EVENT_ESTIMATE_ACTION_RECORDED,
            action="ESTIMATE_EXTRACTION_REQUESTED",
            record=record,
        )
        # O intent é durável ANTES da fila, e nenhuma transação atravessa a publicação.
        session.commit()
        _enqueue_estimate_plate_extraction(
            round_id=str(round_id),
            extraction_id=str(extraction_id),
            tenant_id=principal.tenant_id,
        )
        return response

    @application.get(
        "/v1/estimate-rounds/{round_id}/takeoff",
        response_model=dict[str, Any],
        tags=["estimate"],
    )
    async def get_estimate_takeoff(
        round_id: UUID,
        principal: AuthenticatedPrincipal,
        session: DatabaseSession,
    ) -> dict[str, Any]:
        """Pacote de takeoff da rodada, com a âncora de evidência de cada item."""
        _require_estimate_reader(principal)
        record = _load_estimate_round(session, round_id=round_id, tenant_id=principal.tenant_id)
        revision = estimate_rounds.head_revision(
            session, round_id=record.id, tenant_id=principal.tenant_id
        )
        return _estimate_takeoff_payload(record, revision)

    @application.get(
        "/v1/estimate-rounds/{round_id}/takeoff/overlay",
        response_model=ValuationTakeoffOverlayResponse,
        tags=["estimate"],
    )
    async def get_estimate_takeoff_overlay(
        round_id: UUID,
        principal: AuthenticatedPrincipal,
        session: DatabaseSession,
    ) -> ValuationTakeoffOverlayResponse:
        """URL assinada do overlay e a idade dele; overlay vencido é `200`, nunca erro."""
        _require_estimate_reader(principal)
        record = _load_estimate_round(session, round_id=round_id, tenant_id=principal.tenant_id)
        revision = estimate_rounds.head_revision(
            session, round_id=record.id, tenant_id=principal.tenant_id
        )
        stored = estimate_rounds.require_document(
            revision,
            "takeoff_packet_json",
            stage=STAGE_TAKEOFF,
            detail="a rodada ainda não tem pacote de takeoff publicado",
        )
        overlay_key = estimate_rounds.require_takeoff_overlay(revision)
        image_url = signed_artifact_url(
            application.state.artifact_store,
            object_key=overlay_key,
            tenant_id=principal.tenant_id,
        )
        if image_url is None:
            raise _problem(
                "NOT_FOUND",
                status.HTTP_404_NOT_FOUND,
                "Overlay do takeoff não encontrado.",
            )
        packet_sha256 = document_digest(stored)
        state = estimate_rounds.takeoff_overlay_state(revision, packet_sha256=packet_sha256)
        return ValuationTakeoffOverlayResponse(
            round_id=UUID(record.id),
            version=record.version,
            image_url=image_url,
            image_sha256=cast(str | None, state["image_sha256"]),
            packet_sha256=packet_sha256,
            overlay_packet_sha256=cast(str | None, state["overlay_packet_sha256"]),
            stale=cast(bool, state["stale"]),
        )

    @application.post(
        "/v1/estimate-rounds/{round_id}/takeoff/decisions",
        response_model=dict[str, Any],
        tags=["estimate"],
    )
    async def decide_estimate_takeoff_items(
        round_id: UUID,
        payload: TakeoffDecisionRequest,
        request: Request,
        principal: AuthenticatedPrincipal,
        session: DatabaseSession,
        idempotency_key: Annotated[str, Depends(_require_idempotency)],
    ) -> dict[str, Any]:
        """Aplica o LOTE de decisões do orçamentista, grava a revisão e enfileira o overlay.

        Espelho da rota gêmea da medição, inclusive na atomicidade do lote."""
        _require_valuation_reviewer(principal)
        operation = f"estimate-rounds.takeoff-decisions:{round_id}"
        request_hash = _request_hash(payload)
        existing = _idempotent_response(
            session,
            principal=principal,
            operation=operation,
            key=idempotency_key,
            request_hash=request_hash,
        )
        if existing is not None:
            return existing

        record = _load_estimate_round(session, round_id=round_id, tenant_id=principal.tenant_id)
        estimate_rounds.require_base_version(record, payload.base_version)
        revision = estimate_rounds.head_revision(
            session, round_id=record.id, tenant_id=principal.tenant_id
        )
        packet = estimate_rounds.require_takeoff_packet(revision)
        try:
            # Identidade do `Principal` e instante do servidor: o corpo não carimba nenhum
            # dos dois. A regra de decisão é do domínio e não é reimplementada aqui.
            #
            # UM instante para o lote inteiro, e não um por decisão: elas foram tomadas no
            # mesmo ato, e carimbá-las com milissegundos diferentes inventaria uma ordem
            # que o revisor não declarou.
            decided_at = datetime.now(UTC)
            decisions = [
                TakeoffDecisionInput(
                    item_id=entrada.item_id,
                    action=entrada.action,
                    reviewer_id=principal.subject,
                    reviewer_role=VALUATION_REVIEWER_ROLE,
                    decided_at=decided_at,
                    quantity=parse_quantity(entrada.quantity),
                    unit=entrada.unit,
                    note=entrada.note,
                    item_note=entrada.item_note,
                )
                for entrada in payload.decisions
            ]
            # Lote atômico: `apply_takeoff_decisions` valida o conjunto (item repetido,
            # item inexistente, quantidade ausente em item ambíguo) antes de produzir
            # pacote nenhum, então metade aplicada não é estado alcançável.
            reviewed = apply_takeoff_decisions(packet, TakeoffDecisionBatch(decisions=decisions))
        except ValidationError as error:
            raise _valuation_model_problem(error) from error

        document = reviewed.model_dump(mode="json")
        packet_sha256 = document_digest(document)
        new_revision = estimate_rounds.append_revision(
            session,
            round_record=record,
            created_by=principal.subject,
            changes={"takeoff_packet_json": document},
        )
        record.updated_at = datetime.now(UTC)
        response = {
            **_estimate_takeoff_payload(record, new_revision),
            "overlay": estimate_rounds.takeoff_overlay_state(
                new_revision, packet_sha256=packet_sha256
            ),
        }
        _store_idempotent_response(
            session,
            principal=principal,
            operation=operation,
            key=idempotency_key,
            request_hash=request_hash,
            response=ValuationDocumentResponse(response),
        )
        _record_audit(
            session,
            principal=principal,
            action="ESTIMATE_TAKEOFF_ITEM_DECIDED",
            resource_type="estimate_round",
            resource_id=record.id,
            request_id=request.state.request_id,
        )
        _record_round_event(
            session,
            principal=principal,
            event_type=EVENT_ESTIMATE_ACTION_RECORDED,
            action="ESTIMATE_TAKEOFF_ITEM_DECIDED",
            record=record,
        )
        # A decisão fica durável ANTES da fila, e nenhuma transação atravessa a publicação.
        _commit_valuation_revision(session)
        _enqueue_estimate_overlay_rerender(
            round_id=record.id,
            tenant_id=principal.tenant_id,
            packet_sha256=packet_sha256,
        )
        return response

    @application.get(
        "/v1/estimate-rounds/{round_id}/code-suggestions",
        response_model=dict[str, Any],
        tags=["estimate"],
    )
    async def get_estimate_code_suggestions(
        round_id: UUID,
        principal: AuthenticatedPrincipal,
        session: DatabaseSession,
    ) -> dict[str, Any]:
        """Shortlist de código sobre a CASCATA por item confirmado: observação, nunca decisão.

        Os candidatos saem na ordem da cascata — cada fonte é um bloco —, e a gravação entra
        na cadeia de revisões **sem avançar a versão da rodada**: a shortlist é artefato
        derivado, e se um `GET` movesse o token de concorrência, a próxima decisão do
        orçamentista levaria `409` por algo que ele não fez.

        **Nenhuma chamada paga acontece aqui**, pelo mesmo motivo e com a mesma força da
        irmã da medição (ADR-0054 D7): o cálculo é chamado sem braço semântico (`arms=None`),
        nenhum índice é procurado e a shortlist gravada é léxica até o recálculo explícito.

        Desde a F-044 a resposta traz também `precedents`: o pacote de códigos que cada
        rótulo já disparou nas praças passadas deste tenant, com a contagem de praças. Ele
        **não muda nada** do que já estava aqui — `suggestions` continua igual, na mesma
        ordem e com os mesmos blocos por fonte —, e não acrescenta custo nenhum: é `SELECT`
        sobre o que o fechamento de pacote e a semeadura já gravaram. Continua sendo
        observação: nenhuma decisão nasce desta leitura.
        """
        _require_estimate_reader(principal)
        record = _load_estimate_round(session, round_id=round_id, tenant_id=principal.tenant_id)
        revision = estimate_rounds.head_revision(
            session, round_id=record.id, tenant_id=principal.tenant_id
        )
        stored = None if revision is None else revision.code_suggestions_json
        if stored is not None:
            try:
                # Artefato gravado que não valida é recusa, e não recálculo silencioso: a
                # cura dele é o recompute explícito, que é ato humano e declarado.
                suggestions = CodeSuggestionSet.model_validate(stored)
            except ValidationError as error:
                raise _valuation_model_problem(error) from error
            # `takeoff_packet_of`, e não `require_...`: a shortlist gravada implica pacote na
            # cabeça da cadeia, e uma leitura que já respondia `200` não passa a recusar por
            # causa de um bloco derivado.
            stored_packet = estimate_rounds.takeoff_packet_of(revision)
            return _estimate_suggestions_payload(
                record,
                document=stored,
                suggestions=suggestions,
                computed=False,
                notes=[],
                precedent_blocks=(
                    []
                    if stored_packet is None
                    else _estimate_precedents(
                        session, record, stored_packet, tenant_id=principal.tenant_id
                    )
                ),
            )

        packet = estimate_rounds.require_takeoff_packet(revision)
        require_reviewed_packet(packet)
        # O precedente é lido ANTES da revisão nova entrar na sessão: um `SELECT` com a
        # inserção pendente dispararia o autoflush e a colisão de duas leituras simultâneas
        # subiria aqui, fora do `try` que existe justamente para tratá-la.
        precedent_blocks = _estimate_precedents(
            session, record, packet, tenant_id=principal.tenant_id
        )
        computed, notes, _telemetry = estimate_rounds.compute_round_suggestions(
            packet, _estimate_cascade(record)
        )
        document = computed.model_dump(mode="json")
        estimate_rounds.append_revision(
            session,
            round_record=record,
            created_by=principal.subject,
            changes={"code_suggestions_json": document},
            advance_version=False,
        )
        response = _estimate_suggestions_payload(
            record,
            document=document,
            suggestions=computed,
            computed=True,
            notes=notes,
            precedent_blocks=precedent_blocks,
        )
        try:
            session.commit()
        except IntegrityError:
            # Duas leituras simultâneas — e a tela faz polling — calculam a mesma shortlist
            # e disputam a mesma posição da cadeia. O cálculo é determinístico, então servir
            # o artefato de quem chegou antes é a resposta certa.
            session.rollback()
            revision = estimate_rounds.head_revision(
                session, round_id=record.id, tenant_id=principal.tenant_id
            )
            stored = None if revision is None else revision.code_suggestions_json
            if stored is None:
                raise
            return _estimate_suggestions_payload(
                record,
                document=stored,
                suggestions=CodeSuggestionSet.model_validate(stored),
                computed=False,
                notes=[],
                # O bloco já foi lido antes da inserção que colidiu, e o precedente não
                # depende da revisão que se perdeu: quem chegou antes gravou a MESMA
                # shortlist, e o índice não mudou entre uma leitura e outra.
                precedent_blocks=precedent_blocks,
            )
        return response

    @application.post(
        "/v1/estimate-rounds/{round_id}/code-suggestions/recompute",
        response_model=dict[str, Any],
        tags=["estimate"],
    )
    async def recompute_estimate_code_suggestions(
        round_id: UUID,
        payload: RecomputeSuggestionsRequest,
        request: Request,
        principal: AuthenticatedPrincipal,
        session: DatabaseSession,
        idempotency_key: Annotated[str, Depends(_require_idempotency)],
    ) -> dict[str, Any]:
        """Recalcula a shortlist sobre a cascata CORRENTE e avança a rodada.

        É o caminho declarado de reler o efeito de uma reordenação da cascata: ao contrário
        do `GET`, este é ato humano, exige `base_version` e move o token de concorrência.

        É também onde o braço semântico roda, **por fonte** (ADR-0054 D5): cada catálogo da
        cascata é fundido com o índice dele, e os blocos continuam concatenados na ordem
        instalada — não há RRF entre fontes, porque similaridade de texto não desempata a
        precedência das tabelas. Fonte sem índice publicado entra só com o braço léxico e a
        nota diz **qual** ficou de fora (D6); cobertura parcial é estado normal, não falha.
        """
        _require_valuation_reviewer(principal)
        operation = f"estimate-rounds.suggestions-recompute:{round_id}"
        request_hash = _request_hash(payload)
        existing = _idempotent_response(
            session,
            principal=principal,
            operation=operation,
            key=idempotency_key,
            request_hash=request_hash,
        )
        if existing is not None:
            return existing

        record = _load_estimate_round(session, round_id=round_id, tenant_id=principal.tenant_id)
        estimate_rounds.require_base_version(record, payload.base_version)
        revision = estimate_rounds.head_revision(
            session, round_id=record.id, tenant_id=principal.tenant_id
        )
        packet = estimate_rounds.require_takeoff_packet(revision)
        require_reviewed_packet(packet)
        require_unrefined_suggestions(estimate_rounds.suggestions_of(revision))
        cascade = _estimate_cascade(record)
        computed, notes, telemetry = estimate_rounds.compute_round_suggestions(
            packet, cascade, arms=_semantic_arms(session, principal, cascade)
        )
        document = computed.model_dump(mode="json")
        estimate_rounds.append_revision(
            session,
            round_record=record,
            created_by=principal.subject,
            changes={"code_suggestions_json": document},
        )
        record.updated_at = datetime.now(UTC)
        response = _estimate_suggestions_payload(
            record, document=document, suggestions=computed, computed=True, notes=notes
        )
        _store_idempotent_response(
            session,
            principal=principal,
            operation=operation,
            key=idempotency_key,
            request_hash=request_hash,
            response=ValuationDocumentResponse(response),
        )
        _record_audit(
            session,
            principal=principal,
            action="ESTIMATE_CODE_SUGGESTIONS_RECOMPUTED",
            resource_type="estimate_round",
            resource_id=record.id,
            request_id=request.state.request_id,
        )
        _record_round_event(
            session,
            principal=principal,
            event_type=EVENT_ESTIMATE_ACTION_RECORDED,
            action="ESTIMATE_CODE_SUGGESTIONS_RECOMPUTED",
            record=record,
            extra_payload=telemetry.event_payload(),
        )
        _log_suggestions_recompute(record, telemetry)
        _commit_valuation_revision(session)
        return response

    @application.get(
        "/v1/estimate-rounds/{round_id}/catalog/search",
        response_model=dict[str, Any],
        tags=["estimate"],
    )
    async def search_estimate_cascade(
        round_id: UUID,
        principal: AuthenticatedPrincipal,
        session: DatabaseSession,
        q: Annotated[str, Query(min_length=1, max_length=200)],
        limit: Annotated[
            int, Query(ge=1, le=CATALOG_SEARCH_MAX_LIMIT)
        ] = CATALOG_SEARCH_DEFAULT_LIMIT,
    ) -> dict[str, Any]:
        """Busca léxica na cascata inteira; cada resultado diz de qual fonte e posição veio.

        Sem `arm`, e a razão MUDOU com a F-041: o índice de embeddings agora é publicado
        (`/v1/platform/reference-catalog-indexes`), então o que impede o braço híbrido aqui
        não é mais a falta do artefato — é o verbo. Resolver o vetor da consulta é chamada
        paga, e esta rota é um `GET` que dispara a cada tecla; pagar por tecla é o oposto
        exato da decisão 7 do ADR-0054, que concentrou o gasto no recompute explícito.
        Expor o parâmetro só para devolver `503` acrescentaria superfície que não existe —
        o motivo do braço ausente continua viajando em `semantic_notes`, e a busca nunca
        degrada em silêncio.
        """
        _require_estimate_reader(principal)
        record = _load_estimate_round(session, round_id=round_id, tenant_id=principal.tenant_id)
        return {
            "round_id": record.id,
            "version": record.version,
            **estimate_rounds.search_round_cascade(_estimate_cascade(record), q, limit),
        }

    @application.get(
        "/v1/estimate-rounds/{round_id}/code-assignments",
        response_model=dict[str, Any],
        tags=["estimate"],
    )
    async def get_estimate_code_assignments(
        round_id: UUID,
        principal: AuthenticatedPrincipal,
        session: DatabaseSession,
    ) -> dict[str, Any]:
        """Decisões de código da rodada e os itens confirmados que ainda esperam por uma."""
        _require_estimate_reader(principal)
        record = _load_estimate_round(session, round_id=round_id, tenant_id=principal.tenant_id)
        revision = estimate_rounds.head_revision(
            session, round_id=record.id, tenant_id=principal.tenant_id
        )
        packet = estimate_rounds.require_takeoff_packet(revision)
        return _estimate_assignments_payload(
            record,
            packet=packet,
            assignments=estimate_rounds.assignments_of(revision),
            document=None if revision is None else revision.code_assignments_json,
        )

    @application.post(
        "/v1/estimate-rounds/{round_id}/code-assignments/decisions",
        response_model=dict[str, Any],
        tags=["estimate"],
    )
    async def decide_estimate_item_code(
        round_id: UUID,
        payload: EstimateCodeAssignmentDecisionRequest,
        request: Request,
        principal: AuthenticatedPrincipal,
        session: DatabaseSession,
        idempotency_key: Annotated[str, Depends(_require_idempotency)],
    ) -> dict[str, Any]:
        """Confirma ou rejeita o código de um item CITANDO a fonte, acumulando sobre o anterior.

        A citação viaja na DECISÃO, e não só no relatório final: é ela que o orçamento usa,
        linha a linha, para dizer de qual tabela o preço veio. Código fora do catálogo
        citado, fonte fora da cascata, item já decidido e unidade incompatível sem nota
        continuam sendo recusa do domínio, que esta rota não reimplementa.

        Com `codes`, o corpo carrega o PACOTE do elemento (F-044): os N códigos entram num
        `CodeAssignmentBatch` só e viram **uma** revisão, com uma versão nova só. Não é
        atalho de conveniência — é o que impede o aceite de um precedente de aparecer na
        cadeia de revisões como N atos que ninguém praticou separadamente, e o que faz o
        lote falhar fechado: um código inválido derruba o lote inteiro no domínio, antes de
        qualquer escrita, em vez de gravar metade do pacote.

        Aceitar o pacote **não o fecha**. Fechar continua sendo `/closures`, e é ele que
        alimenta o índice de precedentes.
        """
        _require_valuation_reviewer(principal)
        operation = f"estimate-rounds.code-decisions:{round_id}"
        request_hash = _request_hash(payload)
        existing = _idempotent_response(
            session,
            principal=principal,
            operation=operation,
            key=idempotency_key,
            request_hash=request_hash,
        )
        if existing is not None:
            return existing

        record = _load_estimate_round(session, round_id=round_id, tenant_id=principal.tenant_id)
        estimate_rounds.require_base_version(record, payload.base_version)
        revision = estimate_rounds.head_revision(
            session, round_id=record.id, tenant_id=principal.tenant_id
        )
        packet = estimate_rounds.require_takeoff_packet(revision)
        previous = estimate_rounds.assignments_of(revision)
        cascade = _estimate_cascade(record)
        # UM instante para o lote inteiro: é um ato só do orçamentista, e carimbá-lo N vezes
        # faria N decisões nascerem em momentos diferentes. O `decision_id` continua único
        # por código, porque ele digere o código junto do instante.
        decided_at = datetime.now(UTC)
        chosen_codes: list[str | None] = (
            [payload.code] if payload.codes is None else list(payload.codes)
        )
        try:
            decisions = [
                CodeAssignmentInput(
                    item_id=payload.item_id,
                    action=payload.action,
                    code=code,
                    catalog_sha256=payload.catalog_sha256,
                    reviewer_id=principal.subject,
                    reviewer_role=VALUATION_REVIEWER_ROLE,
                    decided_at=decided_at,
                    note=payload.note,
                )
                for code in chosen_codes
            ]
            batch = CodeAssignmentBatch(assignments=decisions)
        except ValidationError as error:
            # Invariante do domínio embrulhada pelo validador: o código estável sai, a
            # mensagem do Pydantic não — ela pode ecoar o valor recusado.
            raise _valuation_model_problem(error) from error
        assignments = apply_code_assignments_over_cascade(packet, batch, cascade, previous=previous)

        document = assignments.model_dump(mode="json")
        estimate_rounds.append_revision(
            session,
            round_record=record,
            created_by=principal.subject,
            changes={"code_assignments_json": document},
        )
        record.updated_at = datetime.now(UTC)
        response = _estimate_assignments_payload(
            record, packet=packet, assignments=assignments, document=document
        )
        _store_idempotent_response(
            session,
            principal=principal,
            operation=operation,
            key=idempotency_key,
            request_hash=request_hash,
            response=ValuationDocumentResponse(response),
        )
        _record_audit(
            session,
            principal=principal,
            action="ESTIMATE_ITEM_CODE_DECIDED",
            resource_type="estimate_round",
            resource_id=record.id,
            request_id=request.state.request_id,
        )
        _record_round_event(
            session,
            principal=principal,
            event_type=EVENT_ESTIMATE_ACTION_RECORDED,
            action="ESTIMATE_ITEM_CODE_DECIDED",
            record=record,
        )
        _commit_valuation_revision(session)
        return response

    @application.post(
        "/v1/estimate-rounds/{round_id}/code-assignments/closures",
        response_model=dict[str, Any],
        tags=["estimate"],
    )
    async def close_estimate_item_package(
        round_id: UUID,
        payload: ItemPackageClosureRequest,
        request: Request,
        principal: AuthenticatedPrincipal,
        session: DatabaseSession,
        idempotency_key: Annotated[str, Depends(_require_idempotency)],
    ) -> dict[str, Any]:
        """Declara COMPLETO o pacote de serviços de um item — o ato que a confirmação não faz.

        Existe porque a presença de um código deixou de significar que o elemento acabou.
        Sem esta rota, um item com um de seis códigos ficaria indistinguível de um item
        resolvido, e o boletim sairia pela metade sem ninguém ser avisado.

        É rota própria, e não uma bandeira em `/decisions`, porque `/decisions` carrega UMA
        decisão: um pacote de seis códigos nasce em seis chamadas, e a orçamentista não sabe
        de antemão qual será a última. Quem fecha afirma outra coisa, e afirmação separada
        merece endpoint separado — inclusive para a auditoria poder distingui-las.

        A rota não confere quantos códigos o item tem: fechar é decisão de quem monta o
        pacote. Item sem código confirmado, pacote já fechado e item fora do takeoff
        continuam sendo recusa do domínio.

        Desde a F-044 o fechamento tem um **efeito a mais**, na mesma transação: as
        confirmações daquele item viram observações no índice de precedentes, para que o
        mesmo rótulo de legenda reencontre este pacote de códigos na praça seguinte. É
        observação, nunca decisão — nada é aplicado sem clique numa praça futura. Só código
        confirmado entra; rejeitado nunca. Refechar não duplica, e a contagem de praças do
        índice não infla."""
        _require_valuation_reviewer(principal)
        operation = f"estimate-rounds.code-closures:{round_id}"
        request_hash = _request_hash(payload)
        existing = _idempotent_response(
            session,
            principal=principal,
            operation=operation,
            key=idempotency_key,
            request_hash=request_hash,
        )
        if existing is not None:
            return existing

        record = _load_estimate_round(session, round_id=round_id, tenant_id=principal.tenant_id)
        estimate_rounds.require_base_version(record, payload.base_version)
        revision = estimate_rounds.head_revision(
            session, round_id=record.id, tenant_id=principal.tenant_id
        )
        packet = estimate_rounds.require_takeoff_packet(revision)
        previous = estimate_rounds.assignments_of(revision)
        cascade = _estimate_cascade(record)
        try:
            batch = CodeAssignmentBatch(
                closures=[
                    ItemPackageClosureInput(
                        item_id=payload.item_id,
                        reviewer_id=principal.subject,
                        reviewer_role=VALUATION_REVIEWER_ROLE,
                        decided_at=datetime.now(UTC),
                        note=payload.note,
                    )
                ]
            )
        except ValidationError as error:
            raise _valuation_model_problem(error) from error
        assignments = apply_code_assignments_over_cascade(packet, batch, cascade, previous=previous)

        document = assignments.model_dump(mode="json")
        estimate_rounds.append_revision(
            session,
            round_record=record,
            created_by=principal.subject,
            changes={"code_assignments_json": document},
        )
        # O precedente nasce AQUI, na mesma transação, porque fechar é o instante em que o
        # pacote daquele elemento está completo — indexar na confirmação de cada código
        # ensinaria pacote pela metade (F-044 T2, fonte A). Refechar não duplica.
        precedents.record_closure_precedents(
            session,
            tenant_id=principal.tenant_id,
            worksite_key=record.worksite_key,
            packet=packet,
            assignments=assignments,
            item_id=payload.item_id,
            created_by=principal.subject,
        )
        record.updated_at = datetime.now(UTC)
        response = _estimate_assignments_payload(
            record, packet=packet, assignments=assignments, document=document
        )
        _store_idempotent_response(
            session,
            principal=principal,
            operation=operation,
            key=idempotency_key,
            request_hash=request_hash,
            response=ValuationDocumentResponse(response),
        )
        _record_audit(
            session,
            principal=principal,
            action="ESTIMATE_ITEM_PACKAGE_CLOSED",
            resource_type="estimate_round",
            resource_id=record.id,
            request_id=request.state.request_id,
        )
        _record_round_event(
            session,
            principal=principal,
            event_type=EVENT_ESTIMATE_ACTION_RECORDED,
            action="ESTIMATE_ITEM_PACKAGE_CLOSED",
            record=record,
        )
        _commit_valuation_revision(session)
        return response

    @application.post(
        "/v1/estimate-rounds/{round_id}/code-assignments/revocations",
        response_model=dict[str, Any],
        tags=["estimate"],
    )
    async def revoke_estimate_item_code(
        round_id: UUID,
        payload: CodeAssignmentRevocationRequest,
        request: Request,
        principal: AuthenticatedPrincipal,
        session: DatabaseSession,
        idempotency_key: Annotated[str, Depends(_require_idempotency)],
    ) -> dict[str, Any]:
        """Desfaz um código confirmado por engano — e apaga o precedente que ele deixou.

        Irmã de `revoke_valuation_item_code`, com **um efeito a mais**, na mesma transação: a
        observação que o fechamento desta praça gravou no índice de precedentes para este par
        é removida (F-044 fonte A, ADR-0061 D4). Sem isso o índice seguiria ensinando à praça
        seguinte o código que esta praça desfez, com a autoridade de "você já fez assim" —
        que é o argumento mais forte que a shortlist tem.

        A compensação é cirúrgica: só a observação **desta praça** e só a de origem `round`.
        A contagem de praças do índice cai, e um precedente pode desaparecer da shortlist da
        próxima praça — que é exatamente o que se quer, porque ele deixou de ser verdade.

        Observação **semeada** de orçamento passado não é tocada: ela registra o que outra
        praça fez, e um ato desta rodada não tem autoridade sobre aquele arquivo.
        """
        _require_valuation_reviewer(principal)
        operation = f"estimate-rounds.code-revocations:{round_id}"
        request_hash = _request_hash(payload)
        existing = _idempotent_response(
            session,
            principal=principal,
            operation=operation,
            key=idempotency_key,
            request_hash=request_hash,
        )
        if existing is not None:
            return existing

        record = _load_estimate_round(session, round_id=round_id, tenant_id=principal.tenant_id)
        estimate_rounds.require_base_version(record, payload.base_version)
        revision = estimate_rounds.head_revision(
            session, round_id=record.id, tenant_id=principal.tenant_id
        )
        packet = estimate_rounds.require_takeoff_packet(revision)
        previous = estimate_rounds.assignments_of(revision)
        if previous is None:
            raise ValuationValidationError(
                "ASSIGNMENT_REVOCATION_PAIR_UNKNOWN",
                "esta rodada ainda não tem código confirmado para desfazer",
                {"item_id": payload.item_id, "code": payload.code},
            )
        # Recusa PROVISÓRIA e fail-closed (unknown 1 da F-045, decisão do dono ainda aberta):
        # revogar não remonta o orçamento, então o digest que a aprovação amarra continuaria
        # conferindo enquanto o conjunto de códigos por baixo dela mudou — e o portão de
        # exportação, que leria a divergência, não veria nada.
        if estimate_rounds.estimate_is_approved(revision):
            raise estimate_rounds.revocation_after_approval()
        # A fonte de preço do par sai do assignment que está sendo desfeito, e é lida ANTES
        # de ele deixar o conjunto: é ela a chave do índice, e pedi-la ao cliente deixaria a
        # tela afirmar algo que o servidor já sabe.
        price_source = next(
            (
                assignment.catalog_sha256 or PRICE_SOURCE_UNDECLARED
                for assignment in previous.assignments
                if assignment.item_id == payload.item_id
                and assignment.status == "confirmed"
                and assignment.code == payload.code
            ),
            None,
        )
        try:
            revocation = CodeAssignmentRevocationInput(
                item_id=payload.item_id,
                code=payload.code,
                reviewer_id=principal.subject,
                reviewer_role=VALUATION_REVIEWER_ROLE,
                revoked_at=datetime.now(UTC),
                note=payload.note,
            )
        except ValidationError as error:
            raise _valuation_model_problem(error) from error
        assignments = apply_code_revocation(packet, revocation, previous)

        document = assignments.model_dump(mode="json")
        estimate_rounds.append_revision(
            session,
            round_record=record,
            created_by=principal.subject,
            changes={"code_assignments_json": document},
        )
        if price_source is not None:
            precedents.revoke_closure_precedent(
                session,
                tenant_id=principal.tenant_id,
                worksite_key=record.worksite_key,
                packet=packet,
                item_id=payload.item_id,
                code=payload.code,
                price_source=price_source,
            )
        record.updated_at = datetime.now(UTC)
        response = _estimate_assignments_payload(
            record, packet=packet, assignments=assignments, document=document
        )
        _store_idempotent_response(
            session,
            principal=principal,
            operation=operation,
            key=idempotency_key,
            request_hash=request_hash,
            response=ValuationDocumentResponse(response),
        )
        _record_audit(
            session,
            principal=principal,
            action="ESTIMATE_ITEM_CODE_REVOKED",
            resource_type="estimate_round",
            resource_id=record.id,
            request_id=request.state.request_id,
        )
        _record_round_event(
            session,
            principal=principal,
            event_type=EVENT_ESTIMATE_ACTION_RECORDED,
            action="ESTIMATE_ITEM_CODE_REVOKED",
            record=record,
        )
        _commit_valuation_revision(session)
        return response

    @application.post(
        "/v1/precedents/seed",
        response_model=PrecedentSeedResponse,
        tags=["estimate"],
    )
    async def seed_precedents(
        payload: PrecedentSeedPacket,
        request: Request,
        principal: AuthenticatedPrincipal,
        session: DatabaseSession,
        idempotency_key: Annotated[str, Depends(_require_idempotency)],
    ) -> PrecedentSeedResponse:
        """Semeia o índice de precedentes com uma praça JÁ FEITA (F-044, fonte B).

        Sem ela o índice nasceria vazio — só uma rodada real existe no banco —, e o ganho
        medido no primeiro Human Gate da feature (54 a 120 linhas de código por praça)
        esperaria várias praças novas para começar a aparecer.

        **A planilha do cliente não sobe.** O que entra é o pacote que
        `croquito-valuation precedent-extract` produz na máquina de quem semeia: rótulo,
        código e fonte de preço — o mesmo dado que `takeoff_packet_json` das revisões já
        guarda, e por isso a semeadura não cria fronteira de retenção nova.

        Não é rota de rodada: a praça semeada muitas vezes nunca foi lançada no sistema, e
        pendurá-la numa rodada obrigaria a inventar uma. Por isso também não há
        `base_version` — nenhuma revisão é gravada e nenhuma versão avança.

        Três recusas, todas **antes** de qualquer escrita, de modo que um pacote recusado
        não deixa metade de si no índice:

        - `409 PRECEDENT_SEED_WORKSITE_CONFLICT` quando a `worksite_key` já é rodada real
          deste tenant. Misturar as duas origens sob a mesma chave juntaria o histórico
          importado de uma planilha com o que o sistema gravou dos atos da própria
          orçamentista — dois dados de qualidade diferente, indistinguíveis depois;
        - `422 PRECEDENT_SEED_STRATEGY_UNSUPPORTED` para pacote normalizado por outra
          estratégia, que criaria duas chaves para o mesmo rótulo;
        - `422 PRECEDENT_SEED_NORMALIZATION_MISMATCH`, nomeando as **posições** (nunca os
          rótulos), quando o servidor recalcula a normalização e discorda do pacote.

        Idempotente por `(tenant_id, worksite_key)`: reingerir a mesma praça devolve
        `observations_ingested: 0` e a contagem de praças do índice não se move — é ela que a
        tela mostra como argumento de autoridade, e um número inflado seria uma autoridade
        falsa.
        """
        _require_valuation_reviewer(principal)
        operation = "precedents.seed"
        request_hash = _request_hash(payload)
        existing = _idempotent_response(
            session,
            principal=principal,
            operation=operation,
            key=idempotency_key,
            request_hash=request_hash,
        )
        if existing is not None:
            return PrecedentSeedResponse.model_validate(existing)

        counts = precedents.ingest_seed_packet(
            session,
            tenant_id=principal.tenant_id,
            packet=payload,
            created_by=principal.subject,
        )
        response = PrecedentSeedResponse.model_validate(
            precedents.seed_payload(payload.worksite_key, counts)
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
            action="PRECEDENT_SEED_INGESTED",
            resource_type="precedent_worksite",
            # A chave da praça é identificador do tenant, não conteúdo de prancha: é o mesmo
            # `worksite_key` que a rodada já carrega. Rótulo de legenda não entra aqui.
            resource_id=payload.worksite_key,
            request_id=request.state.request_id,
            details={"observations_ingested": counts.ingested},
        )
        session.commit()
        return response

    @application.post(
        "/v1/estimate-rounds/{round_id}/estimate",
        response_model=dict[str, Any],
        tags=["estimate"],
    )
    async def build_estimate(
        round_id: UUID,
        payload: BuildEstimateRequest,
        request: Request,
        principal: AuthenticatedPrincipal,
        session: DatabaseSession,
        idempotency_key: Annotated[str, Depends(_require_idempotency)],
    ) -> dict[str, Any]:
        """Monta o orçamento-base — e **só** monta. Publicar virou ato próprio (ADR-0046).

        Até a F-035 esta rota montava, auditava e publicava o `.xlsx` num ato só, e por isso
        um orçamento nascia despachável: não existia o instante em que ele estava pronto e
        ainda não circulava, logo não havia o que aprovar "antes do despacho". A auditoria e
        a publicação saíram daqui para `POST .../estimate/export`, exatamente como `calc` faz
        na medição — monta e não publica. **É quebra declarada de contrato de rota**: quem
        consumia a resposta esperando planilha publicada precisa mudar.

        Grava também QUEM montou, em coluna própria da revisão. `created_by` não serviria
        para isso: ele é de quem fez o último ato, e depois de uma aprovação já não é quem
        montou — e é contra quem montou que a rota de aprovação compara o `sub` do JWT.

        A aprovação anterior é levada ADIANTE, já caduca (`carry_approval_forward`): ela
        continua apontando para o digest antigo, o despacho a recusa com
        `APPROVAL_CONTENT_MISMATCH`, e a leitura mostra os dois digests lado a lado.
        Descartá-la apagaria em silêncio o fato de que alguém assinou.

        Três precondições recusam com `409 ROUND_STAGE_NOT_READY`, porque as três são ORDEM
        da cadeia e não invariante violada: cascata vazia, takeoff ainda não revisado por
        inteiro e nenhuma decisão de código registrada. Confirmação sem fonte citada, código
        fora do catálogo citado e item confirmado sem decisão continuam sendo `422
        DOMAIN_VALIDATION_FAILED` com o código `ESTIMATE_*`/`ASSIGNMENT_*` do domínio.

        A identidade da obra vem da RODADA; o corpo carrega só a guarda de concorrência e o
        BDI.
        """
        _require_valuation_reviewer(principal)
        operation = f"estimate-rounds.estimate:{round_id}"
        request_hash = _request_hash(payload)
        existing = _idempotent_response(
            session,
            principal=principal,
            operation=operation,
            key=idempotency_key,
            request_hash=request_hash,
        )
        if existing is not None:
            return existing

        record = _load_estimate_round(session, round_id=round_id, tenant_id=principal.tenant_id)
        estimate_rounds.require_base_version(record, payload.base_version)
        bdi_percent = estimate_rounds.resolve_bdi_percent(
            payload.bdi_percent, regime=record.pricing_regime
        )
        cascade = _estimate_cascade(record)
        revision = estimate_rounds.head_revision(
            session, round_id=record.id, tenant_id=principal.tenant_id
        )
        packet = estimate_rounds.require_takeoff_packet(revision)
        estimate_rounds.require_reviewed_takeoff_stage(packet)
        assignments = estimate_rounds.require_assignments(revision)
        calc_matrix = _validate_calc_matrix(payload.calc_matrix)
        built = build_worksite_estimate(
            packet,
            assignments,
            cascade,
            worksite_key=record.worksite_key,
            worksite_name=record.worksite_name,
            bdi_percent=bdi_percent,
            address=record.address,
            calc_plan=None,
            calc_matrix=calc_matrix,
        )

        estimate = estimate_rounds.carry_approval_forward(
            built.estimate, estimate_rounds.readable_estimate(revision)
        )
        document = estimate.model_dump(mode="json")
        # A matriz posta é gravada AO LADO do orçamento (`None` no regime legado), auditável e
        # re-legível: cada revisão registra exatamente a matriz que gerou a memória dela.
        matrix_document = None if calc_matrix is None else calc_matrix.model_dump(mode="json")
        new_revision = estimate_rounds.append_revision(
            session,
            round_record=record,
            created_by=principal.subject,
            changes={
                "estimate_json": document,
                "estimate_built_by": principal.subject,
                "calc_matrix_json": matrix_document,
            },
        )
        record.updated_at = datetime.now(UTC)
        response = _estimate_payload(record, new_revision, document=document, estimate=estimate)
        _store_idempotent_response(
            session,
            principal=principal,
            operation=operation,
            key=idempotency_key,
            request_hash=request_hash,
            response=ValuationDocumentResponse(response),
        )
        _record_audit(
            session,
            principal=principal,
            action="ESTIMATE_BUILT",
            resource_type="estimate_round",
            resource_id=record.id,
            request_id=request.state.request_id,
        )
        _record_round_event(
            session,
            principal=principal,
            event_type=EVENT_ESTIMATE_ACTION_RECORDED,
            action="ESTIMATE_BUILT",
            record=record,
        )
        _commit_valuation_revision(session)
        return response

    @application.post(
        "/v1/estimate-rounds/{round_id}/estimate/approve",
        response_model=dict[str, Any],
        tags=["estimate"],
    )
    async def approve_estimate_round(
        round_id: UUID,
        payload: ApproveEstimateRequest,
        request: Request,
        principal: AuthenticatedPrincipal,
        session: DatabaseSession,
        idempotency_key: Annotated[str, Depends(_require_idempotency)],
    ) -> dict[str, Any]:
        """Assina nominalmente o orçamento da cabeça, amarrando o ato ao digest do conteúdo.

        Este é o ato que o portão de despacho cobra. Ele não recalcula, não confere preço e
        não decide nada sobre o orçamento: registra QUEM assumiu o orçamento como está,
        QUANDO e SOBRE QUAL conteúdo — e é essa terceira parte que impede a assinatura de
        sobreviver a uma mudança do que foi assinado.

        O papel é `aprovador`, e não `orcamentista` (ADR-0046, decisão 5): na cadeia real
        quem assina o orçamento não é quem o montou. A recusa de **auto-aprovação** fecha o
        buraco que sobraria: acumular os dois papéis no mesmo token não contorna, porque a
        comparação é de IDENTIDADE contra quem montou (`estimate_built_by`), não de papel.
        Sem ela o papel novo seria cerimônia.

        A identidade é do JWT e só dele (critério 4 da F-035). O corpo carrega apenas
        `base_version`, e `ApproveEstimateRequest` documenta por que não existe campo de nome
        nem de observação. A revisão nova AVANÇA `version`, porque assinar é ato humano
        deliberado e a próxima decisão do orçamentista tem de partir do que ele viu assinado.

        Orçamento ainda não montado é `409 ROUND_STAGE_NOT_READY` — etapa fora de ordem;
        orçamento que não revalida é `422`, pela mesma razão do `GET`: ninguém assina um
        artefato que o domínio recusa.

        Assinar de novo é o caminho normal da aprovação caduca do desenho aprovado, e não um
        erro: o ato é idempotente por conteúdo (mesmo aprovador, mesmo digest e mesmo
        instante produzem o mesmo `decision_id`), mas cada chamada é uma revisão nova da
        cadeia append-only — o histórico guarda as duas assinaturas, que é o que um registro
        de aprovação existe para fazer.
        """
        _require_estimate_approver(principal)
        operation = f"estimate-rounds.estimate-approve:{round_id}"
        request_hash = _request_hash(payload)
        existing = _idempotent_response(
            session,
            principal=principal,
            operation=operation,
            key=idempotency_key,
            request_hash=request_hash,
        )
        if existing is not None:
            return existing

        record = _load_estimate_round(session, round_id=round_id, tenant_id=principal.tenant_id)
        estimate_rounds.require_base_version(record, payload.base_version)
        revision = estimate_rounds.head_revision(
            session, round_id=record.id, tenant_id=principal.tenant_id
        )
        document = estimate_rounds.require_document(
            revision,
            "estimate_json",
            stage=estimate_rounds.STAGE_ESTIMATE,
            detail="a rodada ainda não tem orçamento montado",
        )
        built_by = estimate_rounds.estimate_built_by(revision)
        if built_by is None:
            raise estimate_rounds.approval_missing_author()
        if built_by == principal.subject:
            raise estimate_rounds.self_approval_forbidden()
        approved = estimate_rounds.approve_estimate(
            _revalidated_estimate(document),
            approver_id=principal.subject,
            decided_at=datetime.now(UTC),
        )

        approved_document = approved.model_dump(mode="json")
        new_revision = estimate_rounds.append_revision(
            session,
            round_record=record,
            created_by=principal.subject,
            changes={"estimate_json": approved_document},
        )
        record.updated_at = datetime.now(UTC)
        response = _estimate_payload(
            record, new_revision, document=approved_document, estimate=approved
        )
        _store_idempotent_response(
            session,
            principal=principal,
            operation=operation,
            key=idempotency_key,
            request_hash=request_hash,
            response=ValuationDocumentResponse(response),
        )
        _record_audit(
            session,
            principal=principal,
            action="ESTIMATE_APPROVED",
            resource_type="estimate_round",
            resource_id=record.id,
            request_id=request.state.request_id,
        )
        _record_round_event(
            session,
            principal=principal,
            event_type=EVENT_ESTIMATE_ACTION_RECORDED,
            action="ESTIMATE_APPROVED",
            record=record,
        )
        _commit_valuation_revision(session)
        return response

    @application.post(
        "/v1/estimate-rounds/{round_id}/estimate/export",
        response_model=dict[str, Any],
        tags=["estimate"],
    )
    async def export_estimate_workbook(
        round_id: UUID,
        payload: ExportEstimateRequest,
        request: Request,
        principal: AuthenticatedPrincipal,
        session: DatabaseSession,
        idempotency_key: Annotated[str, Depends(_require_idempotency)],
    ) -> dict[str, Any]:
        """Publica o `.xlsx` do orçamento: portão do domínio, auditoria e só então o store.

        A ordem **é** o portão, e é o coração da F-035. Primeiro `Estimate.ensure_exportable`,
        que é a regra do DOMÍNIO e não uma cópia dela aqui — é o que faz `croquito-valuation`
        obedecer à mesma regra que esta rota, em vez de haver duas verdades sobre o mesmo
        artefato. Orçamento sem assinatura, com assinatura de recusa ou com assinatura que
        não confere com o conteúdo atual sai como `422 DOMAIN_VALIDATION_FAILED` com
        `details.code = ESTIMATE_EXPORT_BLOCKED` e a lista de violações em `details.errors`.
        **Nada é escrito antes disso** — nem em disco temporário, nem no object store.

        Depois a planilha é escrita num arquivo temporário, reaberta e reconferida centavo a
        centavo, e só um laudo aprovado deixa os bytes subirem e a revisão nascer. Auditoria
        reprovada é `500 ESTIMATE_WORKBOOK_AUDIT_FAILED`, com os códigos dos achados e nunca
        os valores divergentes, e não publica nada.

        O portão daqui **não recebe contrato**, ao contrário do irmão da medição (ADR-0046,
        decisão 3): saldo, período e código no contrato não existem deste lado da fronteira
        do ADR-0027, e é a assinatura sem contrato que impede esses códigos de entrarem aqui.

        Despachar exige `orcamentista`, não `aprovador` (decisão 7): assinar é assumir o
        conteúdo, despachar é operar o envio, e o produto não funde os dois só porque
        acontecem em sequência.

        O `.xlsx` é endereçado pelo `content_digest()` — que exclui a aprovação —, e não pelo
        digest do documento gravado: assinar não muda o conteúdo orçado, e não pode mudar o
        endereço da planilha dele. A exportação NÃO altera o orçamento: a revisão nova carrega
        o mesmo `estimate_json` da cabeça e acrescenta só a referência e o digest do `.xlsx`.
        `version` avança porque publicar é ato humano deliberado.
        """
        _require_valuation_reviewer(principal)
        operation = f"estimate-rounds.estimate-export:{round_id}"
        request_hash = _request_hash(payload)
        existing = _idempotent_response(
            session,
            principal=principal,
            operation=operation,
            key=idempotency_key,
            request_hash=request_hash,
        )
        if existing is not None:
            return existing

        record = _load_estimate_round(session, round_id=round_id, tenant_id=principal.tenant_id)
        estimate_rounds.require_base_version(record, payload.base_version)
        revision = estimate_rounds.head_revision(
            session, round_id=record.id, tenant_id=principal.tenant_id
        )
        document = estimate_rounds.require_document(
            revision,
            "estimate_json",
            stage=estimate_rounds.STAGE_ESTIMATE,
            detail="a rodada ainda não tem orçamento montado",
        )
        estimate = _revalidated_estimate(document)
        # Portão do domínio ANTES de qualquer render: nada é escrito, nem em disco temporário,
        # para um orçamento que não pode ser despachado.
        estimate.ensure_exportable()

        # Portão fail-closed: grava, reabre e audita ANTES de qualquer publicação.
        rendered = estimate_rounds.render_estimate_workbook(estimate, default_template())
        object_key = estimate_rounds.estimate_workbook_key(
            tenant_id=principal.tenant_id,
            round_id=record.id,
            estimate_sha256=estimate.content_digest(),
        )
        # O objeto sobe ANTES do commit: uma revisão que referenciasse um objeto ainda
        # ausente seria um estado que nenhuma leitura conseguiria servir. O contrário —
        # objeto no store sem revisão que o cite — é inerte, porque a chave é derivada do
        # conteúdo e nada o alcança sem a revisão.
        application.state.artifact_store.write_object(
            object_key=object_key,
            body=rendered.body,
            content_type=estimate_rounds.ESTIMATE_WORKBOOK_CONTENT_TYPE,
        )
        head_refs = {} if revision is None else dict(revision.artifact_refs_json or {})
        head_digests = {} if revision is None else dict(revision.artifact_digests_json or {})
        new_revision = estimate_rounds.append_revision(
            session,
            round_record=record,
            created_by=principal.subject,
            changes={
                "artifact_refs_json": {
                    **head_refs,
                    estimate_rounds.ESTIMATE_WORKBOOK_REF: object_key,
                },
                "artifact_digests_json": {
                    **head_digests,
                    estimate_rounds.ESTIMATE_WORKBOOK_DIGEST: rendered.audit.workbook_sha256,
                },
            },
        )
        record.updated_at = datetime.now(UTC)
        response = _estimate_payload(record, new_revision, document=document, estimate=estimate)
        _store_idempotent_response(
            session,
            principal=principal,
            operation=operation,
            key=idempotency_key,
            request_hash=request_hash,
            response=ValuationDocumentResponse(response),
        )
        _record_audit(
            session,
            principal=principal,
            action="ESTIMATE_WORKBOOK_EXPORTED",
            resource_type="estimate_round",
            resource_id=record.id,
            request_id=request.state.request_id,
        )
        _record_round_event(
            session,
            principal=principal,
            event_type=EVENT_ESTIMATE_ACTION_RECORDED,
            action="ESTIMATE_WORKBOOK_EXPORTED",
            record=record,
        )
        _commit_valuation_revision(session)
        return response

    @application.get(
        "/v1/estimate-rounds/{round_id}/estimate",
        response_model=dict[str, Any],
        tags=["estimate"],
    )
    async def get_estimate(
        round_id: UUID,
        principal: AuthenticatedPrincipal,
        session: DatabaseSession,
    ) -> dict[str, Any]:
        """Orçamento gravado, revalidado na leitura, com a URL assinada da planilha.

        Orçamento ainda não montado devolve `409 ROUND_STAGE_NOT_READY`; orçamento que não
        passa na revalidação devolve `422`, nunca `200` com número que ninguém conferiu. A
        URL é montada aqui e agora, depois de conferido o prefixo do tenant, e nunca é
        gravada nem registrada em log ou auditoria.
        """
        _require_estimate_reader(principal)
        record = _load_estimate_round(session, round_id=round_id, tenant_id=principal.tenant_id)
        revision = estimate_rounds.head_revision(
            session, round_id=record.id, tenant_id=principal.tenant_id
        )
        document = estimate_rounds.require_document(
            revision,
            "estimate_json",
            stage=estimate_rounds.STAGE_ESTIMATE,
            detail="a rodada ainda não tem orçamento montado",
        )
        payload = _estimate_payload(
            record, revision, document=document, estimate=_revalidated_estimate(document)
        )
        workbook_url = signed_artifact_url(
            application.state.artifact_store,
            object_key=estimate_rounds.estimate_workbook_ref(revision),
            tenant_id=principal.tenant_id,
        )
        return {**payload, "workbook_url": workbook_url}

    # --- acervo de parcelas de canteiro na rodada (F-042, ADR-0060) -----------------------
    #
    # Quatro rotas e uma só fronteira: `site_setup_kits.visible_kits` — acervo de plataforma
    # (`tenant_id IS NULL`) MAIS o do tenant do JWT. Nenhuma delas recebe `tenant_id` no corpo.
    #
    # A divisão entre elas é a do Design Approval Package: escolher (lista), CONFERIR
    # (pré-visualização, que não grava) e aplicar (ato humano, com `base_version`). O motor é
    # `croquito_valuation.site_setup`, e ele não é reimplementado aqui.

    def _load_visible_site_setup_kit(
        session: Session, *, kit_id: UUID, tenant_id: str
    ) -> SiteSetupKitRecord:
        """O acervo que ESTE tenant enxerga, ou `404`.

        Acervo de outro tenant é indistinguível de inexistente, exatamente como uma rodada de
        outro tenant — é a fronteira do ADR-0060 aplicada ao lookup, e não só à listagem.

        Acervo fora de circulação existe e é encontrado, mas recusa com
        `409 SITE_SETUP_KIT_WITHDRAWN`: dizer `404` para algo que a rodada anterior aplicou
        faria a tela afirmar que o acervo nunca existiu.
        """
        record = session.scalar(
            select(SiteSetupKitRecord).where(
                SiteSetupKitRecord.id == str(kit_id),
                site_setup_kits.visible_kits(tenant_id),
            )
        )
        if record is None:
            raise _problem(
                "NOT_FOUND",
                status.HTTP_404_NOT_FOUND,
                "Acervo de parcelas de canteiro não encontrado.",
            )
        if record.withdrawn_at is not None:
            raise site_setup_kits.kit_withdrawn(record.id)
        return record

    def _estimate_available_codes(record: EstimateRoundRecord) -> set[str]:
        """Os códigos que a cascata desta rodada oferece, para a falha fechada do acervo.

        Passá-los ao motor é o que faz o código ausente recusar na PRÉ-VISUALIZAÇÃO, e não só
        na aplicação: o risco nomeado na feature é o acervo silenciosamente desatualizado —
        catálogo novo que retirou um código que o acervo cita —, e descobri-lo depois de
        aplicar seria descobri-lo com a matriz já mexida.
        """
        return {entry.code for catalog in _estimate_cascade(record) for entry in catalog.entries}

    @application.get(
        "/v1/estimate-rounds/{round_id}/site-setup-kits",
        response_model=EstimateSiteSetupKitListResponse,
        tags=["estimate"],
    )
    async def list_estimate_site_setup_kits(
        round_id: UUID,
        principal: AuthenticatedPrincipal,
        session: DatabaseSession,
    ) -> EstimateSiteSetupKitListResponse:
        """Os acervos que ESTA rodada pode aplicar (F-042, ADR-0060).

        Dois filtros, e só dois: **origem visível** — plataforma mais o acervo deste tenant,
        nunca o de outro — e **em circulação**, porque o que foi retirado deixa de ser
        oferecido sem sumir do registro nem quebrar a rodada que já o aplicou.

        Cada acervo sai com os parâmetros de obra que ele cita e quantas parcelas citam cada
        um: é o que a tela precisa para pedir os campos antes da pré-visualização, e é o
        servidor quem o calcula porque a regra é do domínio (`SiteSetupKit.parameter_names`).

        A rodada continua sendo do tenant — rodada alheia é `404`, e o papel é exigido antes de
        qualquer lookup.
        """
        _require_estimate_reader(principal)
        record = _load_estimate_round(session, round_id=round_id, tenant_id=principal.tenant_id)
        records = session.scalars(
            select(SiteSetupKitRecord).where(
                site_setup_kits.visible_kits(principal.tenant_id),
                SiteSetupKitRecord.withdrawn_at.is_(None),
            )
        ).all()
        # Ordenação em Python, como nas demais listagens: SQLite e PostgreSQL não ordenam
        # texto do mesmo jeito, e a tela lê a ordem.
        ordered = sorted(records, key=lambda kit: (kit.name, kit.kit_version, kit.id))
        return EstimateSiteSetupKitListResponse(
            round_id=round_id,
            version=record.version,
            kits=[
                EstimateSiteSetupKitOption.model_validate(
                    site_setup_kits.kit_option_payload(kit, site_setup_kits.load_kit(kit))
                )
                for kit in ordered
            ],
        )

    @application.post(
        "/v1/estimate-rounds/{round_id}/site-setup/preview",
        response_model=dict[str, Any],
        tags=["estimate"],
    )
    async def preview_estimate_site_setup(
        round_id: UUID,
        payload: SiteSetupPreviewRequest,
        principal: AuthenticatedPrincipal,
        session: DatabaseSession,
    ) -> dict[str, Any]:
        """O que vai nascer se o acervo for aplicado — **sem gravar nada**.

        É LEITURA, e o corpo diz isso: sem `base_version`, sem `Idempotency-Key`, sem revisão
        nova e sem avançar a versão da rodada, como o `GET` da shortlist (ADR-0054 D7). O
        controle que a feature exige contra "aplicar sem olhar" é justamente esta lista, com a
        conta de cada parcela à vista e a remoção individual antes do ato.

        `POST` e não `GET` porque o corpo carrega os parâmetros de obra e a lista de exclusões:
        pô-los em query string publicaria valores da obra na URL, que é o que os logs de
        infraestrutura registram.

        **Ela MARCA o que não pode nascer; quem RECUSA é o apply.** Parâmetro citado e não
        declarado sai em `missing_parameters` da linha, com `quantity: null`; código fora do
        catálogo da cascata sai em `code_absent`; e `blocked_parcel_ids` reúne as parcelas não
        excluídas que estão num dos dois estados. Recusar aqui era um beco sem saída: a saída
        oferecida pela recusa — remover na pré-visualização as parcelas que citam o parâmetro
        faltante — exigia a pré-visualização que a recusa impedia de existir.

        O que continua recusando: acervo invisível (`404`), acervo fora de circulação (`409`),
        parâmetro ilegível (`422 SITE_SETUP_PARAMETER_INVALID`) e exclusão que cita parcela
        que o acervo não tem (`422` com `SITE_SETUP_UNKNOWN_PARCEL`) — as três últimas são erro
        de quem chama, não estado do trabalho.

        Decimais saem como TEXTO, como no resto da jornada: a quantidade é `Decimal` no
        domínio, e um número de JSON já teria passado por binário. Quantidade que não pôde ser
        calculada sai `null`, nunca `"0"`.
        """
        _require_valuation_reviewer(principal)
        record = _load_estimate_round(session, round_id=round_id, tenant_id=principal.tenant_id)
        kit_record = _load_visible_site_setup_kit(
            session, kit_id=payload.kit_id, tenant_id=principal.tenant_id
        )
        kit = site_setup_kits.load_kit(kit_record)
        parameters = site_setup_kits.parse_parameters(payload.parameters)
        rows = preview_site_setup_kit(
            kit,
            parameters,
            excluded_parcel_ids=payload.excluded_parcel_ids,
            available_codes=_estimate_available_codes(record),
        )
        return {
            "round_id": record.id,
            "version": record.version,
            "kit_id": kit_record.id,
            "kit_version": kit.version,
            "rows": [site_setup_kits.preview_row_payload(row) for row in rows],
            "excluded_parcel_ids": list(payload.excluded_parcel_ids),
            "blocked_parcel_ids": site_setup_kits.blocked_parcel_ids(rows),
        }

    @application.get(
        "/v1/estimate-rounds/{round_id}/calc-matrix",
        response_model=dict[str, Any],
        tags=["estimate"],
    )
    async def get_estimate_calc_matrix(
        round_id: UUID,
        principal: AuthenticatedPrincipal,
        session: DatabaseSession,
    ) -> dict[str, Any]:
        """A `CalcMatrix` gravada na revisão corrente, revalidada na leitura — leitura pura.

        Não grava, não avança a versão da rodada e não tem `base_version`, como a leitura da
        etapa de códigos, cujo papel ela também usa (`_require_estimate_reader`): quem assina
        o orçamento precisa ler o que assina.

        Existe porque a matriz não saía em resposta nenhuma: a tela montava o rascunho, mandava
        no build e, depois de um recarregamento, não tinha como saber o que já estava gravado —
        o que fazia montar o orçamento apagar do banco o que o acervo tinha aplicado.

        `calc_matrix` é `null` no regime legado (revisão sem matriz, ou rodada ainda sem
        revisão), e não `409`: não ter matriz é estado normal da rodada, não etapa fora de
        ordem. O documento sai **como está gravado**, depois de passar de novo pelo validador
        do domínio (`matrix_of`, espelho de `load_kit`) — servir o que não valida faria a tela
        renderizar número que ninguém conferiu.
        """
        _require_estimate_reader(principal)
        record = _load_estimate_round(session, round_id=round_id, tenant_id=principal.tenant_id)
        revision = estimate_rounds.head_revision(
            session, round_id=record.id, tenant_id=principal.tenant_id
        )
        document = None if revision is None else revision.calc_matrix_json
        try:
            matrix = estimate_rounds.matrix_of(revision)
        except ValidationError as error:
            raise _valuation_model_problem(error) from error
        return {
            "round_id": record.id,
            "version": record.version,
            "calc_matrix": None if matrix is None else document,
        }

    @application.post(
        "/v1/estimate-rounds/{round_id}/site-setup/apply",
        response_model=dict[str, Any],
        tags=["estimate"],
    )
    async def apply_estimate_site_setup(
        round_id: UUID,
        payload: ApplySiteSetupKitRequest,
        request: Request,
        principal: AuthenticatedPrincipal,
        session: DatabaseSession,
        idempotency_key: Annotated[str, Depends(_require_idempotency)],
    ) -> dict[str, Any]:
        """Materializa as parcelas do acervo na `CalcMatrix` da rodada — ato humano.

        **A semântica de merge é o coração desta rota**, e ela é uma só: reaplicar substitui
        apenas as parcelas DAQUELE acervo.

        - lê a `calc_matrix_json` da revisão corrente, que pode ser `NULL` (regime legado); aí
          a matriz nasce só das contribuições geradas;
        - **remove** toda contribuição cuja `kit_origin.kit_version` seja igual à do acervo
          aplicado — são as da aplicação anterior do mesmo acervo, e mantê-las duplicaria cada
          parcela a cada reaplicação;
        - **preserva intactas** todas as demais: a autorada à mão (`kit_origin` nulo) e a de
          OUTRO acervo. É isso que torna reaplicar idempotente sem apagar trabalho manual;
        - insere as novas e grava a `CalcMatrix` resultante **validada** — nenhuma invariante
          de `calc_matrix.py` é contornada, inclusive a que proíbe parcela `STANDALONE` com
          elemento de origem.

        A guarda de concorrência é a de sempre (`base_version`), a revisão é append-only e a
        versão da rodada avança, porque aqui houve decisão humana. A pré-visualização, que não
        decidiu nada, não avança.
        """
        _require_valuation_reviewer(principal)
        operation = f"estimate-rounds.site-setup-apply:{round_id}"
        request_hash = _request_hash(payload)
        existing = _idempotent_response(
            session,
            principal=principal,
            operation=operation,
            key=idempotency_key,
            request_hash=request_hash,
        )
        if existing is not None:
            return existing

        record = _load_estimate_round(session, round_id=round_id, tenant_id=principal.tenant_id)
        estimate_rounds.require_base_version(record, payload.base_version)
        kit_record = _load_visible_site_setup_kit(
            session, kit_id=payload.kit_id, tenant_id=principal.tenant_id
        )
        kit = site_setup_kits.load_kit(kit_record)
        parameters = site_setup_kits.parse_parameters(payload.parameters)
        revision = estimate_rounds.head_revision(
            session, round_id=record.id, tenant_id=principal.tenant_id
        )
        produced = apply_site_setup_kit(
            kit,
            parameters,
            excluded_parcel_ids=payload.excluded_parcel_ids,
            available_codes=_estimate_available_codes(record),
        )
        try:
            merged, replaced = site_setup_kits.merge_site_setup_contributions(
                estimate_rounds.matrix_of(revision), produced, kit_version=kit.version
            )
        except ValidationError as error:
            raise _valuation_model_problem(error) from error

        document = merged.model_dump(mode="json")
        new_revision = estimate_rounds.append_revision(
            session,
            round_record=record,
            created_by=principal.subject,
            changes={"calc_matrix_json": document},
        )
        record.updated_at = datetime.now(UTC)
        response: dict[str, Any] = {
            "round_id": record.id,
            "version": record.version,
            "revision_id": new_revision.id,
            "revision_version": new_revision.version,
            "kit_id": kit_record.id,
            "kit_version": kit.version,
            "applied_parcel_count": sum(len(service.contributions) for service in produced),
            "replaced_parcel_count": replaced,
            "excluded_parcel_ids": list(payload.excluded_parcel_ids),
            "calc_matrix": document,
        }
        _store_idempotent_response(
            session,
            principal=principal,
            operation=operation,
            key=idempotency_key,
            request_hash=request_hash,
            response=ValuationDocumentResponse(response),
        )
        _record_audit(
            session,
            principal=principal,
            action="ESTIMATE_SITE_SETUP_APPLIED",
            resource_type="estimate_round",
            resource_id=record.id,
            request_id=request.state.request_id,
        )
        _record_round_event(
            session,
            principal=principal,
            event_type=EVENT_ESTIMATE_ACTION_RECORDED,
            action="ESTIMATE_SITE_SETUP_APPLIED",
            record=record,
        )
        _commit_valuation_revision(session)
        return response

    @application.post(
        "/v1/estimate-rounds/{round_id}/site-setup/kits",
        response_model=SiteSetupKitResponse,
        status_code=status.HTTP_201_CREATED,
        tags=["estimate"],
    )
    async def author_estimate_site_setup_kit(
        round_id: UUID,
        payload: AuthorSiteSetupKitRequest,
        request: Request,
        principal: AuthenticatedPrincipal,
        session: DatabaseSession,
        idempotency_key: Annotated[str, Depends(_require_idempotency)],
    ) -> SiteSetupKitResponse:
        """Grava um acervo DO TENANT a partir das parcelas `STANDALONE` da rodada corrente.

        É o Human Gate 4 da feature exercido pela API: o primeiro acervo é autorado por gente,
        a partir de uma praça já feita — o sistema não o infere de planilha antiga.

        Só entra contribuição `STANDALONE`: a base é a definição de "parcela de canteiro" no
        domínio, e uma parcela com origem em elemento da prancha viraria um acervo que só
        serviria àquela praça.

        `parameter_bindings` diz QUAIS operandos viram parâmetro; o resto vira constante. O
        sistema **não** adivinha, e binding que aponte para operando inexistente é recusa que
        **nomeia o binding** — ignorá-lo congelaria como constante um número que a orçamentista
        quis declarar, e o acervo nasceria errado sem ninguém ver.

        `base_version` é conferido porque o acervo é recortado da matriz que a orçamentista
        estava vendo; a rodada, porém, **não muda** — nenhuma revisão é gravada e o contador
        dela não avança, porque nada nela mudou. Avançar a versão faria as edições em voo da
        própria orçamentista devolverem `409` por um ato que não tocou a rodada.
        """
        _require_valuation_reviewer(principal)
        operation = f"estimate-rounds.site-setup-kits:{round_id}"
        request_hash = _request_hash(payload)
        existing_response = _idempotent_response(
            session,
            principal=principal,
            operation=operation,
            key=idempotency_key,
            request_hash=request_hash,
        )
        if existing_response is not None:
            return SiteSetupKitResponse.model_validate(existing_response)

        record = _load_estimate_round(session, round_id=round_id, tenant_id=principal.tenant_id)
        estimate_rounds.require_base_version(record, payload.base_version)
        revision = estimate_rounds.head_revision(
            session, round_id=record.id, tenant_id=principal.tenant_id
        )
        matrix = estimate_rounds.matrix_of(revision)
        if matrix is None:
            raise stage_not_ready(
                estimate_rounds.STAGE_ESTIMATE,
                detail="a rodada ainda não tem matriz de cálculo de onde recortar o acervo",
            )
        published = session.scalar(
            select(SiteSetupKitRecord).where(
                SiteSetupKitRecord.tenant_id == principal.tenant_id,
                SiteSetupKitRecord.name == payload.name,
                SiteSetupKitRecord.kit_version == payload.kit_version,
            )
        )
        if published is not None:
            raise site_setup_kits.already_published(payload.name, payload.kit_version)

        try:
            kit = site_setup_kits.author_site_setup_kit(
                matrix,
                kit_version=payload.kit_version,
                # De onde o acervo foi autorado, no molde de `HaulageTable.source_label`. É a
                # obra da própria rodada, e o acervo é do tenant dela.
                source_label=record.worksite_name,
                parameter_bindings=payload.parameter_bindings,
            )
        except ValidationError as error:
            raise _valuation_model_problem(error) from error

        document = kit.model_dump(mode="json")
        kit_record = SiteSetupKitRecord(
            id=str(new_uuid7()),
            tenant_id=principal.tenant_id,
            name=payload.name,
            kit_version=kit.version,
            source_label=kit.source_label,
            document_json=document,
            document_sha256=site_setup_kits.kit_document_digest(document),
            withdrawn_at=None,
            created_by=principal.subject,
            created_at=datetime.now(UTC),
        )
        session.add(kit_record)
        response = SiteSetupKitResponse.model_validate(
            site_setup_kits.kit_record_payload(kit_record, kit)
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
            action="ESTIMATE_SITE_SETUP_KIT_AUTHORED",
            resource_type="site_setup_kit",
            resource_id=kit_record.id,
            request_id=request.state.request_id,
            details={"site_setup_kit_id": kit_record.id, "kit_version": kit_record.kit_version},
        )
        session.commit()
        return response

    @application.get("/v1/surveys", response_model=CompletedSurveyPage, tags=["surveys"])
    async def list_completed_surveys(
        principal: AuthenticatedPrincipal,
        session: DatabaseSession,
        cursor: str | None = None,
        limit: Annotated[int, Query(ge=1, le=100)] = 25,
    ) -> CompletedSurveyPage:
        """Levantamentos concluídos que o escritório pode escolher para um job."""
        _reviewer_role(principal)
        query = select(SurveyRecord).where(
            SurveyRecord.tenant_id == principal.tenant_id,
            SurveyRecord.status == "COMPLETED",
        )
        if cursor is not None:
            created_at, identifier = _decode_round_cursor(cursor)
            query = query.where(
                or_(
                    SurveyRecord.created_at < created_at,
                    and_(
                        SurveyRecord.created_at == created_at,
                        SurveyRecord.id < identifier,
                    ),
                )
            )
        records = list(
            session.scalars(
                query.order_by(SurveyRecord.created_at.desc(), SurveyRecord.id.desc()).limit(
                    limit + 1
                )
            )
        )
        page = records[:limit]
        items: list[CompletedSurveySummary] = []
        for record in page:
            packet = SurveyPacket.model_validate(record.snapshot_json)
            photo_count = session.scalar(
                select(func.count(SurveyMediaRecord.id)).where(
                    SurveyMediaRecord.tenant_id == principal.tenant_id,
                    SurveyMediaRecord.survey_id == record.id,
                    SurveyMediaRecord.status == "CONFIRMED",
                    SurveyMediaRecord.mime_type.like("image/%"),
                )
            )
            items.append(
                CompletedSurveySummary(
                    survey_id=record.id,
                    name=record.name,
                    order_ref=record.order_ref,
                    version=record.version,
                    photo_count=int(photo_count or 0),
                    confirmed_measurement_count=sum(
                        measurement.status is FieldMeasurementStatus.CONFIRMED
                        for measurement in packet.measurements
                    ),
                    completed_at=record.updated_at,
                )
            )
        return CompletedSurveyPage(
            items=items,
            next_cursor=(_encode_round_cursor(page[-1]) if len(records) > limit and page else None),
        )

    @application.get(
        "/v1/jobs/{job_id}/field-evidence",
        response_model=FieldEvidenceResponse,
        tags=["field-evidence"],
    )
    async def get_field_evidence(
        job_id: UUID,
        principal: AuthenticatedPrincipal,
        session: DatabaseSession,
    ) -> FieldEvidenceResponse:
        _reviewer_role(principal)
        job = _load_job(session, job_id=job_id, tenant_id=principal.tenant_id)
        return _field_evidence_response(application, session, job=job)

    @application.post(
        "/v1/jobs/{job_id}/field-evidence/surveys/{survey_id}",
        response_model=JobSurveyLinkResponse,
        tags=["field-evidence"],
    )
    async def link_survey_to_job(
        job_id: UUID,
        survey_id: SurveyIdPath,
        payload: MutateJobSurveyLinkRequest,
        request: Request,
        principal: AuthenticatedPrincipal,
        session: DatabaseSession,
        idempotency_key: Annotated[str, Depends(_require_idempotency)],
    ) -> JobSurveyLinkResponse:
        _reviewer_role(principal)
        operation = f"field-evidence.link-survey:{job_id}:{survey_id}"
        request_hash = _request_hash(payload)
        existing = _idempotent_response(
            session,
            principal=principal,
            operation=operation,
            key=idempotency_key,
            request_hash=request_hash,
        )
        if existing is not None:
            return JobSurveyLinkResponse.model_validate(existing)
        job = _load_job(session, job_id=job_id, tenant_id=principal.tenant_id)
        survey = _load_survey(session, survey_id=survey_id, tenant_id=principal.tenant_id)
        if survey.status != "COMPLETED":
            raise _problem(
                "SURVEY_NOT_COMPLETED",
                status.HTTP_409_CONFLICT,
                "Somente levantamento concluído pode ser vinculado à revisão.",
            )
        link = session.scalar(
            select(JobSurveyLinkRecord).where(
                JobSurveyLinkRecord.tenant_id == principal.tenant_id,
                JobSurveyLinkRecord.job_id == job.id,
                JobSurveyLinkRecord.survey_id == survey_id,
            )
        )
        if link is None:
            if job.version != payload.base_version:
                raise _problem(
                    "REVISION_CONFLICT",
                    status.HTTP_409_CONFLICT,
                    "A evidência de campo do job mudou; releia antes de vincular.",
                )
            link = JobSurveyLinkRecord(
                id=str(new_uuid7()),
                tenant_id=principal.tenant_id,
                job_id=job.id,
                survey_id=survey.id,
                linked_by=principal.subject,
            )
            session.add(link)
            job.version += 1
            try:
                session.flush()
            except IntegrityError as error:
                session.rollback()
                raise _problem(
                    "REVISION_CONFLICT",
                    status.HTTP_409_CONFLICT,
                    "Um vínculo concorrente mudou a evidência do job.",
                ) from error
            _record_audit(
                session,
                principal=principal,
                action="JOB_SURVEY_LINKED",
                resource_type="job_survey_link",
                resource_id=link.id,
                request_id=request.state.request_id,
            )
        response = JobSurveyLinkResponse(
            job_id=job_id, survey_id=survey_id, linked=True, version=job.version
        )
        _store_idempotent_response(
            session,
            principal=principal,
            operation=operation,
            key=idempotency_key,
            request_hash=request_hash,
            response=response,
        )
        session.commit()
        return response

    @application.post(
        "/v1/jobs/{job_id}/field-evidence/surveys/{survey_id}/unlink",
        response_model=JobSurveyLinkResponse,
        tags=["field-evidence"],
    )
    async def unlink_survey_from_job(
        job_id: UUID,
        survey_id: SurveyIdPath,
        payload: MutateJobSurveyLinkRequest,
        request: Request,
        principal: AuthenticatedPrincipal,
        session: DatabaseSession,
        idempotency_key: Annotated[str, Depends(_require_idempotency)],
    ) -> JobSurveyLinkResponse:
        _reviewer_role(principal)
        operation = f"field-evidence.unlink-survey:{job_id}:{survey_id}"
        request_hash = _request_hash(payload)
        existing = _idempotent_response(
            session,
            principal=principal,
            operation=operation,
            key=idempotency_key,
            request_hash=request_hash,
        )
        if existing is not None:
            return JobSurveyLinkResponse.model_validate(existing)
        job = _load_job(session, job_id=job_id, tenant_id=principal.tenant_id)
        link = session.scalar(
            select(JobSurveyLinkRecord).where(
                JobSurveyLinkRecord.tenant_id == principal.tenant_id,
                JobSurveyLinkRecord.job_id == job.id,
                JobSurveyLinkRecord.survey_id == survey_id,
            )
        )
        if link is not None:
            if job.version != payload.base_version:
                raise _problem(
                    "REVISION_CONFLICT",
                    status.HTTP_409_CONFLICT,
                    "A evidência de campo do job mudou; releia antes de desvincular.",
                )
            resource_id = link.id
            session.delete(link)
            job.version += 1
            session.flush()
            _record_audit(
                session,
                principal=principal,
                action="JOB_SURVEY_UNLINKED",
                resource_type="job_survey_link",
                resource_id=resource_id,
                request_id=request.state.request_id,
            )
        response = JobSurveyLinkResponse(
            job_id=job_id, survey_id=survey_id, linked=False, version=job.version
        )
        _store_idempotent_response(
            session,
            principal=principal,
            operation=operation,
            key=idempotency_key,
            request_hash=request_hash,
            response=response,
        )
        session.commit()
        return response

    @application.post(
        "/v1/jobs/{job_id}/field-evidence/photos/presign",
        response_model=PresignJobFieldPhotoResponse,
        tags=["field-evidence"],
    )
    async def presign_job_field_photo(
        job_id: UUID,
        payload: PresignJobFieldPhotoRequest,
        request: Request,
        principal: AuthenticatedPrincipal,
        session: DatabaseSession,
        idempotency_key: Annotated[str, Depends(_require_idempotency)],
    ) -> PresignJobFieldPhotoResponse:
        """Cria metadado e uma URL nova sem persistir a credencial temporária."""
        _reviewer_role(principal)
        operation = f"field-evidence.photo-presign:{job_id}"
        request_hash = _request_hash(payload)

        def signed_response(
            photo: JobFieldPhotoRecord, *, version: int
        ) -> PresignJobFieldPhotoResponse:
            checksum = base64.b64encode(bytes.fromhex(photo.sha256)).decode("ascii")
            url = application.state.artifact_store.presign_upload(
                object_key=photo.object_key,
                checksum_sha256=checksum,
                content_type=photo.mime_type,
            )
            headers = {"Content-Type": photo.mime_type}
            if runtime_settings.storage_flavor == "s3":
                headers["x-amz-checksum-sha256"] = checksum
            return PresignJobFieldPhotoResponse(
                photo_id=UUID(photo.id),
                version=version,
                sha256=photo.sha256,
                url=url,
                headers=headers,
                expires_at=datetime.now(UTC) + timedelta(minutes=15),
            )

        replay = _idempotent_response(
            session,
            principal=principal,
            operation=operation,
            key=idempotency_key,
            request_hash=request_hash,
        )
        if replay is not None:
            intent = _PresignJobFieldPhotoIntent.model_validate(replay)
            photo = session.scalar(
                select(JobFieldPhotoRecord).where(
                    JobFieldPhotoRecord.id == str(intent.photo_id),
                    JobFieldPhotoRecord.job_id == str(job_id),
                    JobFieldPhotoRecord.tenant_id == principal.tenant_id,
                )
            )
            if photo is None:  # pragma: no cover - retenção nunca separa intent e foto
                raise _problem(
                    "NOT_FOUND", status.HTTP_404_NOT_FOUND, "Foto de campo não encontrada."
                )
            return signed_response(photo, version=intent.version)

        job = _load_job(session, job_id=job_id, tenant_id=principal.tenant_id)
        photo = session.scalar(
            select(JobFieldPhotoRecord).where(
                JobFieldPhotoRecord.job_id == job.id,
                JobFieldPhotoRecord.tenant_id == job.tenant_id,
                JobFieldPhotoRecord.sha256 == payload.sha256,
            )
        )
        if photo is None:
            if job.version != payload.base_version:
                raise _problem(
                    "REVISION_CONFLICT",
                    status.HTTP_409_CONFLICT,
                    "A evidência de campo do job mudou; releia antes de anexar.",
                )
            photo = JobFieldPhotoRecord(
                id=str(new_uuid7()),
                tenant_id=job.tenant_id,
                job_id=job.id,
                sha256=payload.sha256,
                mime_type=payload.mime_type,
                byte_size=payload.byte_size,
                object_key=(
                    f"tenants/{job.tenant_id}/jobs/{job.id}/field-evidence/media/{payload.sha256}"
                ),
                anchor_text=payload.anchor_text,
                status="PRESIGNED",
                created_by=principal.subject,
            )
            session.add(photo)
            job.version += 1
            session.flush()
            _record_audit(
                session,
                principal=principal,
                action="JOB_FIELD_PHOTO_PRESIGNED",
                resource_type="job_field_photo",
                resource_id=photo.id,
                request_id=request.state.request_id,
            )
        elif (
            photo.mime_type != payload.mime_type
            or photo.byte_size != payload.byte_size
            or photo.anchor_text != payload.anchor_text
        ):
            raise _problem(
                "FIELD_PHOTO_METADATA_MISMATCH",
                status.HTTP_409_CONFLICT,
                "O mesmo digest já foi declarado com metadados diferentes.",
            )
        intent = _PresignJobFieldPhotoIntent(photo_id=UUID(photo.id), version=job.version)
        _store_idempotent_response(
            session,
            principal=principal,
            operation=operation,
            key=idempotency_key,
            request_hash=request_hash,
            response=intent,
        )
        session.commit()
        return signed_response(photo, version=intent.version)

    @application.post(
        "/v1/jobs/{job_id}/field-evidence/photos/{photo_id}/confirm",
        response_model=JobFieldPhotoStateResponse,
        tags=["field-evidence"],
    )
    async def confirm_job_field_photo(
        job_id: UUID,
        photo_id: UUID,
        payload: ConfirmJobFieldPhotoRequest,
        request: Request,
        principal: AuthenticatedPrincipal,
        session: DatabaseSession,
        idempotency_key: Annotated[str, Depends(_require_idempotency)],
    ) -> JobFieldPhotoStateResponse:
        """Publica a foto no painel só depois de conferir tipo, tamanho e digest."""
        _reviewer_role(principal)
        operation = f"field-evidence.photo-confirm:{job_id}:{photo_id}"
        request_hash = _request_hash(payload)
        replay = _idempotent_response(
            session,
            principal=principal,
            operation=operation,
            key=idempotency_key,
            request_hash=request_hash,
        )
        if replay is not None:
            return JobFieldPhotoStateResponse.model_validate(replay)
        job = _load_job(session, job_id=job_id, tenant_id=principal.tenant_id)
        photo = session.scalar(
            select(JobFieldPhotoRecord).where(
                JobFieldPhotoRecord.id == str(photo_id),
                JobFieldPhotoRecord.job_id == job.id,
                JobFieldPhotoRecord.tenant_id == job.tenant_id,
            )
        )
        if photo is None:
            raise _problem("NOT_FOUND", status.HTTP_404_NOT_FOUND, "Foto não encontrada.")
        if photo.status != "CONFIRMED":
            if job.version != payload.base_version:
                raise _problem(
                    "REVISION_CONFLICT",
                    status.HTTP_409_CONFLICT,
                    "A evidência de campo do job mudou; releia antes de confirmar.",
                )
            uploaded = application.state.artifact_store.head_upload(object_key=photo.object_key)
            raw = application.state.artifact_store.read_object(
                object_key=photo.object_key, max_bytes=photo.byte_size
            )
            if (
                uploaded is None
                or uploaded.content_length != photo.byte_size
                or uploaded.content_type.lower() != photo.mime_type
                or raw is None
                or len(raw) != photo.byte_size
                or hashlib.sha256(raw).hexdigest() != photo.sha256
            ):
                raise _problem(
                    "FIELD_PHOTO_DIGEST_MISMATCH",
                    status.HTTP_409_CONFLICT,
                    "Foto ausente, inválida ou com integridade divergente do declarado.",
                )
            photo.status = "CONFIRMED"
            job.version += 1
            _record_audit(
                session,
                principal=principal,
                action="JOB_FIELD_PHOTO_CONFIRMED",
                resource_type="job_field_photo",
                resource_id=photo.id,
                request_id=request.state.request_id,
            )
        response = JobFieldPhotoStateResponse(
            photo_id=photo_id, status=photo.status, version=job.version
        )
        _store_idempotent_response(
            session,
            principal=principal,
            operation=operation,
            key=idempotency_key,
            request_hash=request_hash,
            response=response,
        )
        session.commit()
        return response

    @application.post(
        "/v1/jobs/{job_id}/field-evidence/photos/{origin}/{evidence_id}/reading",
        response_model=FieldPhotoAnalysisStateResponse,
        status_code=status.HTTP_202_ACCEPTED,
        tags=["field-evidence"],
    )
    async def request_field_photo_reading(
        job_id: UUID,
        origin: Literal["survey", "standalone"],
        evidence_id: UUID,
        payload: RequestFieldPhotoAnalysisRequest,
        request: Request,
        principal: AuthenticatedPrincipal,
        session: DatabaseSession,
        idempotency_key: Annotated[str, Depends(_require_idempotency)],
    ) -> FieldPhotoAnalysisStateResponse:
        """Enfileira leitura explícita; upload e vínculo jamais entram neste caminho."""
        _reviewer_role(principal)
        operation = f"field-evidence.reading:{job_id}:{origin}:{evidence_id}"
        request_hash = _request_hash(payload)
        replay = _idempotent_response(
            session,
            principal=principal,
            operation=operation,
            key=idempotency_key,
            request_hash=request_hash,
        )
        if replay is not None:
            response = FieldPhotoAnalysisStateResponse.model_validate(replay)
            state = session.get(FieldEvidenceAnalysisRecord, str(response.analysis_id))
            if state is not None and state.status == "QUEUED":
                try:
                    application.state.queue.enqueue_field_evidence_analysis(
                        analysis_id=state.id, job_id=str(job_id), tenant_id=principal.tenant_id
                    )
                except QUEUE_TRANSPORT_ERRORS as error:
                    raise _problem(
                        "PROCESSING_UNAVAILABLE",
                        status.HTTP_503_SERVICE_UNAVAILABLE,
                        "Leitura registrada; repita o mesmo comando para reenfileirar.",
                    ) from error
            return response

        job = _load_job(session, job_id=job_id, tenant_id=principal.tenant_id)
        _load_field_photo_target(session, job=job, origin=origin, evidence_id=evidence_id)
        _require_active_ai_entitlement(
            session,
            principal,
            real_providers_enabled=runtime_settings.real_providers_enabled,
        )
        _require_job_ai_authorization(
            session, job=job, real_providers_enabled=runtime_settings.real_providers_enabled
        )
        analysis = _field_analysis_state(
            session,
            tenant_id=job.tenant_id,
            job_id=job.id,
            origin=origin,
            evidence_id=str(evidence_id),
            task="reading",
        )
        if analysis is None:
            if job.version != payload.base_version:
                raise _problem(
                    "REVISION_CONFLICT",
                    status.HTTP_409_CONFLICT,
                    "A evidência de campo do job mudou; releia antes de solicitar análise.",
                )
            analysis = FieldEvidenceAnalysisRecord(
                id=str(new_uuid7()),
                tenant_id=job.tenant_id,
                job_id=job.id,
                origin=origin,
                evidence_id=str(evidence_id),
                task="reading",
                status="QUEUED",
                artifact_key=_field_analysis_object_key(
                    job=job,
                    origin=origin,
                    evidence_id=str(evidence_id),
                    task="reading",
                ),
                requested_by=principal.subject,
            )
            session.add(analysis)
            job.version += 1
            session.flush()
            _record_audit(
                session,
                principal=principal,
                action="FIELD_PHOTO_READING_REQUESTED",
                resource_type="field_evidence_analysis",
                resource_id=analysis.id,
                request_id=request.state.request_id,
            )
        response = FieldPhotoAnalysisStateResponse(
            analysis_id=UUID(analysis.id),
            task="reading",
            status=analysis.status,
            version=job.version,
        )
        _store_idempotent_response(
            session,
            principal=principal,
            operation=operation,
            key=idempotency_key,
            request_hash=request_hash,
            response=response,
        )
        session.commit()
        try:
            application.state.queue.enqueue_field_evidence_analysis(
                analysis_id=analysis.id, job_id=job.id, tenant_id=job.tenant_id
            )
        except QUEUE_TRANSPORT_ERRORS as error:
            raise _problem(
                "PROCESSING_UNAVAILABLE",
                status.HTTP_503_SERVICE_UNAVAILABLE,
                "Leitura registrada; repita o mesmo comando para reenfileirar.",
            ) from error
        return response

    @application.post(
        "/v1/jobs/{job_id}/field-evidence/photos/{origin}/{evidence_id}/classification",
        response_model=FieldPhotoAnalysisStateResponse,
        status_code=status.HTTP_202_ACCEPTED,
        tags=["field-evidence"],
    )
    async def request_field_photo_classification(
        job_id: UUID,
        origin: Literal["survey", "standalone"],
        evidence_id: UUID,
        payload: RequestFieldPhotoAnalysisRequest,
        request: Request,
        principal: AuthenticatedPrincipal,
        session: DatabaseSession,
        idempotency_key: Annotated[str, Depends(_require_idempotency)],
    ) -> FieldPhotoAnalysisStateResponse:
        """Enfileira classificação explícita; o único resultado possível é rascunho."""
        _reviewer_role(principal)
        if not runtime_settings.real_providers_enabled:
            raise _problem(
                "PROVIDER_UNAVAILABLE",
                status.HTTP_503_SERVICE_UNAVAILABLE,
                "Classificação visual por IA está desabilitada neste ambiente.",
            )
        operation = f"field-evidence.classification:{job_id}:{origin}:{evidence_id}"
        request_hash = _request_hash(payload)
        replay = _idempotent_response(
            session,
            principal=principal,
            operation=operation,
            key=idempotency_key,
            request_hash=request_hash,
        )
        if replay is not None:
            response = FieldPhotoAnalysisStateResponse.model_validate(replay)
            state = session.get(FieldEvidenceAnalysisRecord, str(response.analysis_id))
            if state is not None and state.status == "QUEUED":
                try:
                    application.state.queue.enqueue_field_evidence_analysis(
                        analysis_id=state.id,
                        job_id=str(job_id),
                        tenant_id=principal.tenant_id,
                    )
                except QUEUE_TRANSPORT_ERRORS as error:
                    raise _problem(
                        "PROCESSING_UNAVAILABLE",
                        status.HTTP_503_SERVICE_UNAVAILABLE,
                        "Classificação registrada; repita o mesmo comando para reenfileirar.",
                    ) from error
            return response

        job = _load_job(session, job_id=job_id, tenant_id=principal.tenant_id)
        _load_field_photo_target(session, job=job, origin=origin, evidence_id=evidence_id)
        _require_active_ai_entitlement(session, principal, real_providers_enabled=True)
        _require_job_ai_authorization(session, job=job, real_providers_enabled=True)
        analysis = _field_analysis_state(
            session,
            tenant_id=job.tenant_id,
            job_id=job.id,
            origin=origin,
            evidence_id=str(evidence_id),
            task="classification",
        )
        if analysis is None:
            if job.version != payload.base_version:
                raise _problem(
                    "REVISION_CONFLICT",
                    status.HTTP_409_CONFLICT,
                    "A evidência de campo do job mudou; releia antes de solicitar análise.",
                )
            analysis = FieldEvidenceAnalysisRecord(
                id=str(new_uuid7()),
                tenant_id=job.tenant_id,
                job_id=job.id,
                origin=origin,
                evidence_id=str(evidence_id),
                task="classification",
                status="QUEUED",
                artifact_key=_field_analysis_object_key(
                    job=job,
                    origin=origin,
                    evidence_id=str(evidence_id),
                    task="classification",
                ),
                requested_by=principal.subject,
            )
            session.add(analysis)
            job.version += 1
            session.flush()
            _record_audit(
                session,
                principal=principal,
                action="FIELD_PHOTO_CLASSIFICATION_REQUESTED",
                resource_type="field_evidence_analysis",
                resource_id=analysis.id,
                request_id=request.state.request_id,
            )
        response = FieldPhotoAnalysisStateResponse(
            analysis_id=UUID(analysis.id),
            task="classification",
            status=analysis.status,
            version=job.version,
        )
        _store_idempotent_response(
            session,
            principal=principal,
            operation=operation,
            key=idempotency_key,
            request_hash=request_hash,
            response=response,
        )
        session.commit()
        try:
            application.state.queue.enqueue_field_evidence_analysis(
                analysis_id=analysis.id, job_id=job.id, tenant_id=job.tenant_id
            )
        except QUEUE_TRANSPORT_ERRORS as error:
            raise _problem(
                "PROCESSING_UNAVAILABLE",
                status.HTTP_503_SERVICE_UNAVAILABLE,
                "Classificação registrada; repita o mesmo comando para reenfileirar.",
            ) from error
        return response

    @application.post(
        "/v1/jobs/{job_id}/field-evidence/photos/{origin}/{evidence_id}/values",
        response_model=ConfirmFieldPhotoValueResponse,
        tags=["field-evidence"],
    )
    async def confirm_field_photo_value(
        job_id: UUID,
        origin: Literal["survey", "standalone"],
        evidence_id: UUID,
        payload: ConfirmFieldPhotoValueRequest,
        request: Request,
        principal: AuthenticatedPrincipal,
        session: DatabaseSession,
        idempotency_key: Annotated[str, Depends(_require_idempotency)],
    ) -> ConfirmFieldPhotoValueResponse:
        """Confirma ou corrige um rascunho; associação como testemunha é outro ato."""
        _reviewer_role(principal)
        operation = f"field-evidence.value:{job_id}:{origin}:{evidence_id}"
        request_hash = _request_hash(payload)
        replay = _idempotent_response(
            session,
            principal=principal,
            operation=operation,
            key=idempotency_key,
            request_hash=request_hash,
        )
        if replay is not None:
            return ConfirmFieldPhotoValueResponse.model_validate(replay)
        job = _load_job(session, job_id=job_id, tenant_id=principal.tenant_id)
        _load_field_photo_target(session, job=job, origin=origin, evidence_id=evidence_id)
        if job.version != payload.base_version:
            raise _problem(
                "REVISION_CONFLICT",
                status.HTTP_409_CONFLICT,
                "A evidência de campo do job mudou; releia antes de confirmar a leitura.",
            )
        analysis = _field_analysis_state(
            session,
            tenant_id=job.tenant_id,
            job_id=job.id,
            origin=origin,
            evidence_id=str(evidence_id),
            task="reading",
        )
        document = (
            _read_field_analysis(
                application,
                object_key=analysis.artifact_key,
                tenant_id=job.tenant_id,
            )
            if analysis is not None
            and analysis.status == "PROCESSED"
            and analysis.artifact_key is not None
            else None
        )
        readings = document.get("readings") if document is not None else None
        if not isinstance(readings, list) or not any(
            isinstance(reading, dict) and reading.get("id") == payload.source_reading_id
            for reading in readings
        ):
            raise _problem(
                "FIELD_PHOTO_READING_NOT_FOUND",
                status.HTTP_409_CONFLICT,
                "A leitura precisa existir no resultado processado antes da confirmação.",
            )
        previous = session.scalar(
            select(FieldPhotoValueConfirmationRecord).where(
                FieldPhotoValueConfirmationRecord.tenant_id == job.tenant_id,
                FieldPhotoValueConfirmationRecord.job_id == job.id,
                FieldPhotoValueConfirmationRecord.origin == origin,
                FieldPhotoValueConfirmationRecord.evidence_id == str(evidence_id),
                FieldPhotoValueConfirmationRecord.source_reading_id == payload.source_reading_id,
                FieldPhotoValueConfirmationRecord.status == "ACTIVE",
            )
        )
        if previous is not None:
            previous.status = "SUPERSEDED"
        confirmation = FieldPhotoValueConfirmationRecord(
            id=str(new_uuid7()),
            tenant_id=job.tenant_id,
            job_id=job.id,
            origin=origin,
            evidence_id=str(evidence_id),
            source_reading_id=payload.source_reading_id,
            value_mm=payload.value_mm,
            kind=payload.kind,
            raw_text=payload.raw_text,
            supersedes_confirmation_id=(previous.id if previous is not None else None),
            status="ACTIVE",
            confirmed_by=principal.subject,
        )
        session.add(confirmation)
        job.version += 1
        session.flush()
        public_confirmation = FieldEvidenceConfirmedValue(
            confirmation_id=UUID(confirmation.id),
            source_reading_id=confirmation.source_reading_id,
            value_mm=confirmation.value_mm,
            kind=confirmation.kind,
            raw_text=confirmation.raw_text,
            confirmed_by=confirmation.confirmed_by,
            confirmed_at=confirmation.confirmed_at,
        )
        response = ConfirmFieldPhotoValueResponse(
            confirmation=public_confirmation, version=job.version
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
            action="FIELD_PHOTO_VALUE_CONFIRMED",
            resource_type="field_photo_value_confirmation",
            resource_id=confirmation.id,
            request_id=request.state.request_id,
        )
        session.commit()
        return response

    @application.post(
        "/v1/surveys/{survey_id}/operations",
        response_model=SurveyOperationsAckResponse,
        tags=["surveys"],
    )
    async def submit_survey_operations(
        survey_id: SurveyIdPath,
        payload: SubmitSurveyOperationsRequest,
        request: Request,
        principal: AuthenticatedPrincipal,
        session: DatabaseSession,
        idempotency_key: Annotated[str, Depends(_require_idempotency)],
    ) -> SurveyOperationsAckResponse:
        """Recebe um lote do outbox do aparelho e consolida o pacote do levantamento.

        A rota é a porta de entrada da sincronização (ADR-0043) e trabalha sob três regras
        que não são detalhe de implementação:

        1. O levantamento nasce aqui, na primeira chamada, com o id que o aparelho gerou
           offline — não existe rota de criação separada, porque em campo o levantamento já
           existe antes de haver rede.
        2. Operação já gravada é reconhecida de novo sem regravar e sem falhar: o aparelho
           reenvia por desenho, e um reenvio não pode ser erro.
        3. Buraco ou regressão de `seq` é CONFLITO, não erro de contrato: o servidor devolve
           o estado dele e deixa a pessoa decidir na tela 6b. Ele não escolhe versão
           vencedora, não funde estados e não apaga nada.
        """
        _require_field_technician(principal)
        _validate_survey_batch(survey_id, payload)
        operation = f"surveys.operations:{survey_id}"
        request_hash = _request_hash(payload)
        existing = _idempotent_response(
            session,
            principal=principal,
            operation=operation,
            key=idempotency_key,
            request_hash=request_hash,
        )
        if existing is not None:
            return SurveyOperationsAckResponse.model_validate(existing)

        now = datetime.now(UTC)
        # O histórico não é copiado para o snapshot: `survey_operation_records` é a fonte
        # dele, e mantê-lo nos dois lugares faria as duas divergirem no primeiro reenvio.
        snapshot = payload.survey.model_copy(update={"operations": []}).model_dump(mode="json")
        record = session.scalar(
            select(SurveyRecord).where(
                SurveyRecord.id == survey_id,
                SurveyRecord.tenant_id == principal.tenant_id,
            )
        )
        created = record is None
        if record is None:
            record = SurveyRecord(
                id=survey_id,
                tenant_id=principal.tenant_id,
                name=payload.survey.name,
                order_ref=payload.survey.order_id,
                status="OPEN",
                version=1,
                snapshot_json=snapshot,
                created_at=now,
                updated_at=now,
            )
            session.add(record)
            # A raiz precisa existir antes das operações: sem relacionamento declarado o ORM
            # não ordena os dois mappers, e o PostgreSQL cobra a chave estrangeira.
            try:
                session.flush()
            except IntegrityError as error:
                raise _survey_race_conflict(session) from error
        elif record.status != "OPEN":
            raise _survey_conflict(
                session,
                record=record,
                detail="Levantamento concluído não aceita operação nova.",
            )

        stored_ids = set(
            session.scalars(
                select(SurveyOperationRecord.id).where(
                    SurveyOperationRecord.survey_id == survey_id,
                    SurveyOperationRecord.tenant_id == principal.tenant_id,
                )
            )
        )
        pending = sorted(
            (
                operation_command
                for operation_command in payload.operations
                if operation_command.operation_id not in stored_ids
            ),
            key=lambda operation_command: operation_command.seq,
        )
        if pending:
            last_seq = _last_seq_by_device(
                session, survey_id=survey_id, tenant_id=principal.tenant_id
            )
            expected = last_seq.get(payload.device_id, 0) + 1
            if any(
                operation_command.seq != expected + offset
                for offset, operation_command in enumerate(pending)
            ):
                raise _survey_conflict(
                    session,
                    record=record,
                    detail=(
                        "A sequência do aparelho não continua de onde o servidor parou; "
                        "resolva o conflito no aparelho e reenvie."
                    ),
                )
            for operation_command in pending:
                session.add(
                    SurveyOperationRecord(
                        id=operation_command.operation_id,
                        tenant_id=principal.tenant_id,
                        survey_id=survey_id,
                        device_id=operation_command.device_id,
                        seq=operation_command.seq,
                        type=operation_command.type,
                        payload_json=operation_command.payload,
                        # O instante é o do aparelho, que é quando o ato de campo aconteceu;
                        # a hora de chegada fica no evento de auditoria.
                        created_at=operation_command.created_at,
                    )
                )
            record.snapshot_json = snapshot
            record.name = payload.survey.name
            record.order_ref = payload.survey.order_id
            record.updated_at = now
            if not created:
                # Na criação a versão 1 já É o estado deste lote; incrementá-la faria o
                # primeiro `base_version` do aparelho nascer errado.
                record.version += 1
            try:
                session.flush()
            except IntegrityError as error:
                raise _survey_race_conflict(session) from error

        response = SurveyOperationsAckResponse(
            survey_id=survey_id,
            acked_operation_ids=[
                operation_command.operation_id for operation_command in payload.operations
            ],
            version=record.version,
            last_seq_by_device=_last_seq_by_device(
                session, survey_id=survey_id, tenant_id=principal.tenant_id
            ),
        )
        _store_idempotent_response(
            session,
            principal=principal,
            operation=operation,
            key=idempotency_key,
            request_hash=request_hash,
            response=response,
        )
        if created:
            _record_audit(
                session,
                principal=principal,
                action="SURVEY_CREATED",
                resource_type="survey",
                resource_id=survey_id,
                request_id=request.state.request_id,
            )
        if pending:
            _record_audit(
                session,
                principal=principal,
                action="SURVEY_OPERATIONS_RECORDED",
                resource_type="survey",
                resource_id=survey_id,
                request_id=request.state.request_id,
            )
        session.commit()
        return response

    @application.get(
        "/v1/surveys/{survey_id}", response_model=SurveyStateResponse, tags=["surveys"]
    )
    async def get_survey(
        survey_id: SurveyIdPath,
        principal: AuthenticatedPrincipal,
        session: DatabaseSession,
    ) -> SurveyStateResponse:
        """O levantamento como o servidor o conhece: pacote, versão, sequências e mídia.

        Lê também com papel de revisão: o escritório consulta o que veio do campo antes de
        transformá-lo em observação do pipeline, mas nunca escreve por aqui.
        """
        _require_survey_reader(principal)
        record = _load_survey(session, survey_id=survey_id, tenant_id=principal.tenant_id)
        return _survey_state(session, record)

    @application.post(
        "/v1/surveys/{survey_id}/media/presign",
        response_model=PresignSurveyMediaResponse,
        tags=["surveys"],
    )
    async def presign_survey_media(
        survey_id: SurveyIdPath,
        payload: PresignSurveyMediaRequest,
        request: Request,
        principal: AuthenticatedPrincipal,
        session: DatabaseSession,
        idempotency_key: Annotated[str, Depends(_require_idempotency)],
    ) -> PresignSurveyMediaResponse:
        """Assina o envio de uma mídia JÁ referenciada no pacote (prancha 6a).

        Metadado antes da mídia é a ordem que sustenta a tela de progresso e o portão: uma
        foto cujo digest não está ancorado em nada seria um blob órfão no bucket do tenant,
        sem ponto do levantamento que a explique. Por isso o digest não referenciado é
        `409 SURVEY_MEDIA_NOT_REFERENCED`, e não um upload aceito "por precaução".
        """
        _require_field_technician(principal)
        record = _load_survey(session, survey_id=survey_id, tenant_id=principal.tenant_id)
        operation = f"surveys.media-presign:{survey_id}"
        request_hash = _request_hash(payload)
        existing = _idempotent_response(
            session,
            principal=principal,
            operation=operation,
            key=idempotency_key,
            request_hash=request_hash,
        )
        if existing is not None:
            return PresignSurveyMediaResponse.model_validate(existing)

        if payload.sha256 not in _survey_media_digests(
            SurveyPacket.model_validate(record.snapshot_json)
        ):
            raise _problem(
                "SURVEY_MEDIA_NOT_REFERENCED",
                status.HTTP_409_CONFLICT,
                "A mídia não está referenciada no levantamento; sincronize a âncora antes.",
            )

        object_key = f"tenants/{principal.tenant_id}/surveys/{survey_id}/media/{payload.sha256}"
        media = session.scalar(
            select(SurveyMediaRecord).where(
                SurveyMediaRecord.survey_id == survey_id,
                SurveyMediaRecord.tenant_id == principal.tenant_id,
                SurveyMediaRecord.sha256 == payload.sha256,
            )
        )
        if media is None:
            media = SurveyMediaRecord(
                id=str(new_uuid7()),
                tenant_id=principal.tenant_id,
                survey_id=survey_id,
                sha256=payload.sha256,
                mime_type=payload.mime_type,
                byte_size=payload.byte_size,
                object_key=object_key,
                status="PRESIGNED",
            )
            session.add(media)
            session.flush()
        elif media.status == "PRESIGNED":
            # Reassinar antes de confirmar é retomada de envio interrompido, caso normal em
            # campo. Mídia já CONFIRMADA não é rebaixada: isso republicaria o comando de
            # processamento na próxima confirmação.
            media.mime_type = payload.mime_type
            media.byte_size = payload.byte_size

        checksum_sha256 = base64.b64encode(bytes.fromhex(payload.sha256)).decode("ascii")
        artifact_store: ArtifactStore = application.state.artifact_store
        url = artifact_store.presign_upload(
            object_key=media.object_key,
            checksum_sha256=checksum_sha256,
            content_type=payload.mime_type,
        )
        headers: dict[str, str] = {"Content-Type": payload.mime_type}
        if runtime_settings.storage_flavor == "s3":
            # O header entra na assinatura só no S3; enviá-lo ao GCS faria o PUT falhar.
            headers["x-amz-checksum-sha256"] = checksum_sha256
        response = PresignSurveyMediaResponse(
            media_id=UUID(media.id),
            sha256=media.sha256,
            object_key=media.object_key,
            url=url,
            headers=headers,
            expires_at=datetime.now(UTC) + timedelta(minutes=15),
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
            action="SURVEY_MEDIA_PRESIGNED",
            resource_type="survey_media",
            resource_id=media.id,
            request_id=request.state.request_id,
        )
        session.commit()
        return response

    @application.post(
        "/v1/surveys/{survey_id}/media/{sha256}/confirm",
        response_model=SurveyStateResponse,
        tags=["surveys"],
    )
    async def confirm_survey_media(
        survey_id: SurveyIdPath,
        sha256: SurveyDigestPath,
        request: Request,
        principal: AuthenticatedPrincipal,
        session: DatabaseSession,
    ) -> SurveyStateResponse:
        """Confere o objeto enviado e publica o processamento da mídia — uma vez só.

        A conferência é a mesma da criação de job: tamanho contra o declarado e, no perfil
        de storage que assina checksum, o digest do próprio objeto. No perfil GCS o digest
        continua sendo verificado pelo worker, que relê os bytes — a integridade não é
        dispensada, é adiada, e o adiamento é registrado em auditoria.

        A publicação acontece na TRANSIÇÃO `PRESIGNED → CONFIRMED`. Confirmar de novo devolve
        o estado sem republicar; se a fila recusar, a mídia volta a `PRESIGNED` para que
        repetir o comando seja seguro e continue produzindo exatamente uma mensagem.
        """
        _require_field_technician(principal)
        record = _load_survey(session, survey_id=survey_id, tenant_id=principal.tenant_id)
        media = session.scalar(
            select(SurveyMediaRecord).where(
                SurveyMediaRecord.survey_id == survey_id,
                SurveyMediaRecord.tenant_id == principal.tenant_id,
                SurveyMediaRecord.sha256 == sha256,
            )
        )
        if media is None:
            raise _problem(
                "NOT_FOUND", status.HTTP_404_NOT_FOUND, "Mídia do levantamento não encontrada."
            )
        if media.status == "CONFIRMED":
            return _survey_state(session, record)

        expected_checksum = base64.b64encode(bytes.fromhex(media.sha256)).decode("ascii")
        uploaded_object = application.state.artifact_store.head_upload(object_key=media.object_key)
        checksum_deferred = runtime_settings.storage_flavor == "gcs"
        if (
            uploaded_object is None
            or uploaded_object.content_length != media.byte_size
            or (not checksum_deferred and uploaded_object.checksum_sha256 != expected_checksum)
        ):
            raise _problem(
                "SURVEY_MEDIA_DIGEST_MISMATCH",
                status.HTTP_409_CONFLICT,
                "Mídia ausente, incompleta ou com integridade divergente do declarado.",
            )

        media.status = "CONFIRMED"
        _record_audit(
            session,
            principal=principal,
            action="SURVEY_MEDIA_CONFIRMED",
            resource_type="survey_media",
            resource_id=media.id,
            request_id=request.state.request_id,
        )
        if checksum_deferred:
            _record_audit(
                session,
                principal=principal,
                action="SURVEY_MEDIA_CHECKSUM_DEFERRED_TO_WORKER",
                resource_type="survey_media",
                resource_id=media.id,
                request_id=request.state.request_id,
            )
        session.commit()

        queue: QueueAdapter = application.state.queue
        try:
            if SURVEY_MEDIA_COMMANDS[media.mime_type] == "photo":
                queue.enqueue_survey_photo_analysis(
                    survey_id=survey_id, media_id=media.id, tenant_id=principal.tenant_id
                )
            else:
                queue.enqueue_survey_transcription(
                    survey_id=survey_id, media_id=media.id, tenant_id=principal.tenant_id
                )
        except QUEUE_TRANSPORT_ERRORS as error:
            media.status = "PRESIGNED"
            session.commit()
            raise _problem(
                "PROCESSING_UNAVAILABLE",
                status.HTTP_503_SERVICE_UNAVAILABLE,
                "Mídia recebida; repita o mesmo comando para publicar o processamento.",
            ) from error
        return _survey_state(session, record)

    @application.post(
        "/v1/surveys/{survey_id}/complete",
        response_model=SurveyStateResponse,
        tags=["surveys"],
    )
    async def complete_survey(
        survey_id: SurveyIdPath,
        payload: CompleteSurveyRequest,
        request: Request,
        principal: AuthenticatedPrincipal,
        session: DatabaseSession,
        idempotency_key: Annotated[str, Depends(_require_idempotency)],
    ) -> SurveyStateResponse:
        """Fecha o levantamento e enfileira a exportação para o pipeline.

        Três precondições, nesta ordem, porque cada uma responde a uma pergunta diferente:
        o levantamento ainda está aberto; o aparelho está falando da versão que ele leu; e
        toda mídia que o pacote referencia já chegou íntegra. Concluir com foto pendente
        publicaria um levantamento cuja evidência ainda está no aparelho.
        """
        _require_field_technician(principal)
        record = _load_survey(session, survey_id=survey_id, tenant_id=principal.tenant_id)
        operation = f"surveys.complete:{survey_id}"
        request_hash = _request_hash(payload)
        existing = _idempotent_response(
            session,
            principal=principal,
            operation=operation,
            key=idempotency_key,
            request_hash=request_hash,
        )
        queue: QueueAdapter = application.state.queue
        if existing is not None:
            # Repetir o mesmo comando reenfileira, como em `POST /v1/jobs`: a intenção já é
            # durável, e uma mensagem perdida no transporte precisa de caminho de volta.
            try:
                queue.enqueue_survey_export(survey_id=survey_id, tenant_id=principal.tenant_id)
            except QUEUE_TRANSPORT_ERRORS as error:
                raise _problem(
                    "PROCESSING_UNAVAILABLE",
                    status.HTTP_503_SERVICE_UNAVAILABLE,
                    "Não foi possível publicar a exportação; repita o mesmo comando.",
                ) from error
            return SurveyStateResponse.model_validate(existing)

        if record.status != "OPEN":
            raise _survey_conflict(session, record=record, detail="Levantamento já foi concluído.")
        if record.version != payload.base_version:
            raise _survey_conflict(
                session,
                record=record,
                detail="Existe uma sincronização mais recente do levantamento.",
            )

        packet = SurveyPacket.model_validate(record.snapshot_json)
        if packet.status is not SurveyStatus.CONCLUDED:
            raise _problem(
                "SURVEY_NOT_CONCLUDED",
                status.HTTP_409_CONFLICT,
                "O pacote sincronizado ainda não declara a conclusão do levantamento.",
            )
        confirmed = {
            media.sha256
            for media in _survey_media_rows(
                session, survey_id=survey_id, tenant_id=principal.tenant_id
            )
            if media.status == "CONFIRMED"
        }
        pending_media = sorted(_survey_media_digests(packet) - confirmed)
        if pending_media:
            raise _problem(
                "SURVEY_MEDIA_PENDING",
                status.HTTP_409_CONFLICT,
                "Há mídia referenciada que ainda não chegou ao servidor.",
                {"pending_sha256": pending_media},
            )

        record.status = "COMPLETED"
        record.updated_at = datetime.now(UTC)
        response = _survey_state(session, record)
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
            action="SURVEY_COMPLETED",
            resource_type="survey",
            resource_id=survey_id,
            request_id=request.state.request_id,
        )
        session.commit()
        try:
            queue.enqueue_survey_export(survey_id=survey_id, tenant_id=principal.tenant_id)
        except QUEUE_TRANSPORT_ERRORS as error:
            raise _problem(
                "PROCESSING_UNAVAILABLE",
                status.HTTP_503_SERVICE_UNAVAILABLE,
                "Levantamento concluído; repita o mesmo comando para publicar a exportação.",
            ) from error
        return response

    return application


app = create_app()
