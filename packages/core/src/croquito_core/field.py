"""Contrato canônico do pacote de levantamento de campo (F-032, T7).

`SurveyPacket` é o espelho serializável do `Survey` de `apps/field/src/domain/types.ts`
— a PWA offline-first do técnico em campo (ADR-0043). O mapeamento domínio↔contrato vive
em `apps/field/src/sync/contract.ts` (único lugar que conhece os dois lados); este módulo
só declara a forma do dado, sem nenhuma lógica de sincronização (T9, fora do escopo desta
tarefa) — o pacote exportado entra no pipeline como observação (`unresolved`/
`approximate`), sujeita aos portões existentes, nunca como geometria resolvida.

`tenant_id` não aparece aqui de propósito: tenant vem sempre do JWT no momento da
sincronização, nunca do corpo do pacote (mesma regra de `services/api`).

Convenções seguidas de `croquito_core.models`: `ContractModel` para `extra="forbid"` +
validação em atribuição, docstrings em português, identificadores em inglês, milímetros
sempre `int` (nunca `float`) porque `apps/field/AGENTS.md` proíbe ponto flutuante nas
coordenadas e medidas do levantamento.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any, Final, Literal

from pydantic import Field, model_validator

from croquito_core.models import ContractModel

SURVEY_SCHEMA_VERSION: Final = "1.0.0"

SHA256_PATTERN: Final = r"^[a-f0-9]{64}$"

_MM_BOUND: Final = 1_000_000
"""Limite sensato para coordenadas/medidas em mm: 1 km. Levantamento de campo (praças,
lotes) nunca se aproxima dessa ordem de grandeza; o limite existe para pegar dado
corrompido (ex.: mm confundido com outra unidade), não para expressar uma regra de
negócio real."""


class MeasurementKind(StrEnum):
    """Espelho de `MeasurementKind` (`apps/field/src/domain/types.ts`)."""

    LENGTH = "length"
    DIAGONAL = "diagonal"
    WIDTH = "width"
    RADIUS = "radius"
    LEVEL = "level"
    DROP = "drop"
    HEIGHT = "height"
    ANGLE = "angle"


class MeasurementStatus(StrEnum):
    """Espelho de `MeasurementStatus`."""

    DRAFT = "draft"
    CONFIRMED = "confirmed"


class SurveyStatus(StrEnum):
    """Espelho de `SurveyStatus` (T5)."""

    COLLECTING = "collecting"
    CONCLUDED = "concluded"


class MediaRef(ContractModel):
    """Referência a um arquivo de mídia local — nunca o blob (`apps/field/AGENTS.md`:
    "o domínio não carrega blobs"). `sha256`/`mime_type`/`byte_size` espelham
    `MediaRecord` (`apps/field/src/storage/SurveyRepository.ts`), sem o campo `blob`."""

    sha256: str = Field(pattern=SHA256_PATTERN)
    mime_type: str = Field(min_length=1, max_length=100)
    byte_size: int = Field(ge=0)


class SurveyPoint(ContractModel):
    """Espelho de `SurveyPoint`."""

    id: str = Field(min_length=1)
    x_mm: int = Field(ge=-_MM_BOUND, le=_MM_BOUND)
    y_mm: int = Field(ge=-_MM_BOUND, le=_MM_BOUND)
    created_at: datetime


class Segment(ContractModel):
    """Espelho de `Segment` — ligação observada entre dois pontos, sem medida
    confirmada."""

    id: str = Field(min_length=1)
    from_point_id: str = Field(min_length=1)
    to_point_id: str = Field(min_length=1)
    created_at: datetime


class Measurement(ContractModel):
    """Espelho de `Measurement`. `value_mm` nunca é negativo — diferente de
    `x_mm`/`y_mm`, que são coordenadas relativas a uma origem local e podem ser
    negativas."""

    id: str = Field(min_length=1)
    value_mm: int = Field(ge=0, le=_MM_BOUND)
    kind: MeasurementKind
    from_point_id: str | None = None
    to_point_id: str | None = None
    second_from_point_id: str | None = None
    second_to_point_id: str | None = None
    element_id: str | None = None
    instrument: str = Field(min_length=1, max_length=200)
    status: MeasurementStatus
    justification: str | None = Field(default=None, max_length=1000)
    created_at: datetime


class MediaAnchor(ContractModel):
    """Âncora de uma foto OU áudio a um ponto, elemento ou nota do levantamento — envelope
    único para os dois tipos de mídia (`local_media_ref`/áudio de T12), sempre resolvido
    para `media_ref` (sha256/mime_type/byte_size) pelo mapeamento de
    `apps/field/src/sync/contract.ts`, nunca a referência local (`MediaRecord.id`), que só
    tem sentido dentro do dispositivo de origem."""

    id: str = Field(min_length=1)
    media_ref: MediaRef
    point_id: str | None = None
    element_id: str | None = None
    note_id: str | None = None
    created_at: datetime


class ObservationNote(ContractModel):
    """Espelho de `ObservationNote`. Desde a T12 (prancha 7a da DAP rev.2, aprovada) a
    nota pode ser texto, voz (`audio_media_ref`) ou os dois; o que continua inválido é a
    nota VAZIA — sem texto e sem áudio ela não registra nada, mesma regra `EMPTY_TEXT`
    do domínio do app (`apps/field/src/domain/commands.ts`)."""

    id: str = Field(min_length=1)
    text: str = Field(max_length=5000)
    point_id: str | None = None
    element_id: str | None = None
    audio_media_ref: MediaRef | None = None
    created_at: datetime

    @model_validator(mode="after")
    def validate_text_or_audio(self) -> ObservationNote:
        """Nota só-de-voz viaja com `text: ""`; nota sem texto E sem áudio é recusada."""
        if self.text.strip() == "" and self.audio_media_ref is None:
            raise ValueError("observação precisa de texto não-vazio ou de nota de voz")
        return self


class ElementObject(ContractModel):
    """Espelho de `ElementObject`."""

    id: str = Field(min_length=1)
    label: str = Field(min_length=1, max_length=200)
    point_ids: list[str] = Field(default_factory=list)
    created_at: datetime


class GpsFix(ContractModel):
    """Espelho de `GpsFix` — referência geográfica, nunca medição."""

    lat: float
    lng: float
    accuracy_m: float = Field(ge=0)


class ArrivalContext(ContractModel):
    """Espelho de `ArrivalContext` (prancha 2). `access_media_ref` carrega a referência
    de mídia resolvida (sha256/mime_type/byte_size), não o `MediaRecord.id` local —
    mesma razão de `MediaAnchor.media_ref`."""

    instrument: str = Field(min_length=1, max_length=200)
    reference_note: str = Field(max_length=2000)
    gps: GpsFix | Literal["unavailable"] | None = None
    access_media_ref: MediaRef | None = None
    arrived_at: datetime


class Waiver(ContractModel):
    """Espelho de `Waiver` (prancha 5b) — justificativa de pendência não crítica mantida
    na conclusão."""

    id: str = Field(min_length=1)
    finding_code: str = Field(min_length=1, max_length=200)
    ref_key: str = Field(min_length=1, max_length=200)
    justification: str = Field(min_length=1, max_length=1000)
    created_at: datetime


class SurveyOperation(ContractModel):
    """Espelho de `SurveyOperation` (`apps/field/src/outbox/types.ts`) — histórico do
    outbox, sem `status`: reconhecimento (`ack`) é estado local do app, nunca viaja no
    pacote."""

    operation_id: str = Field(min_length=1)
    device_id: str = Field(min_length=1)
    survey_id: str = Field(min_length=1)
    seq: int = Field(ge=1)
    type: str = Field(min_length=1, max_length=100)
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class SurveyPacket(ContractModel):
    """Pacote de levantamento de campo — o `Survey` inteiro pronto para sincronização
    (T9). Sem `tenant_id`: tenant vem sempre do JWT no momento do envio.

    `status`/`waivers` viajam sempre resolvidos (equivalente a `surveyStatus`/
    `surveyWaivers` do domínio, nunca o campo bruto opcional pré-T5); `order_id` e
    `arrival_context` continuam opcionais porque o próprio domínio os declara assim
    (levantamento legado sem ordem de origem; chegada ainda não registrada)."""

    survey_id: str = Field(min_length=1)
    name: str = Field(min_length=1, max_length=200)
    order_id: str | None = None
    device_id: str = Field(min_length=1)
    created_at: datetime
    updated_at: datetime
    points: list[SurveyPoint] = Field(default_factory=list)
    segments: list[Segment] = Field(default_factory=list)
    measurements: list[Measurement] = Field(default_factory=list)
    media_anchors: list[MediaAnchor] = Field(default_factory=list)
    elements: list[ElementObject] = Field(default_factory=list)
    observations: list[ObservationNote] = Field(default_factory=list)
    gps_fixes: list[GpsFix] = Field(default_factory=list)
    arrival_context: ArrivalContext | None = None
    status: SurveyStatus
    waivers: list[Waiver] = Field(default_factory=list)
    operations: list[SurveyOperation] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_operations_belong_to_survey(self) -> SurveyPacket:
        """Guarda barata contra o pacote errado: uma operação do outbox de outro survey
        aqui dentro seria um bug de montagem silencioso, não um dado válido."""
        alheias = [op.operation_id for op in self.operations if op.survey_id != self.survey_id]
        if alheias:
            raise ValueError(
                f"operações de outro survey no pacote: {alheias} (survey_id={self.survey_id})"
            )
        return self
