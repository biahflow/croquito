/**
 * Único módulo de mapeamento domínio↔contrato do pacote de levantamento (F-032, T7).
 *
 * `apps/field/src/domain/types.ts` é a fonte oficial do levantamento; este módulo só
 * traduz `Survey` (+ histórico de operações do outbox) para o contrato canônico gerado
 * (`packages/core/src/croquito_core/field.py` → `@croquito/contracts`
 * `src/survey-packet.generated.ts`). Puro de propósito: sem `fetch`, sem Dexie, sem
 * import de UI (`apps/field/AGENTS.md` proíbe transporte de rede fora de uma tarefa que
 * autorize explicitamente a sincronização — T9). Quem monta o `MediaIndex` e chama
 * `SurveyRepository.listOperations` é o chamador, nunca este arquivo.
 *
 * Mídia sempre viaja por identidade de conteúdo (sha256/mime_type/byte_size), nunca pela
 * referência local (`MediaRecord.id`) — que só tem sentido dentro do dispositivo de
 * origem: é por isso que `toSurveyPacket` recebe um `MediaIndex` já resolvido em vez de
 * ler o storage.
 */

import type {
  ArrivalContext,
  ElementObject,
  Measurement,
  ObservationNote,
  PhotoAnchor,
  Segment,
  Survey,
  SurveyPoint,
  Waiver,
} from "../domain/types";
import { surveyStatus, surveyWaivers } from "../domain/types";
import type { SurveyOperation } from "../outbox/types";
import type { MediaRecord } from "../storage/SurveyRepository";
import type { SurveyPacket } from "@croquito/contracts";

/** Metadado de mídia sem o `blob` — o que o pacote de sincronização pode carregar. */
export type MediaMeta = Pick<MediaRecord, "sha256" | "mime_type" | "byte_size">;

/**
 * Índice de mídia local já resolvido, chaveado por `MediaRecord.id`. Quem chama
 * `toSurveyPacket` monta este índice com `SurveyRepository.getMedia` para cada
 * `local_media_ref`/`access_media_ref`/`audio_media_ref` referenciado pelo survey — este
 * módulo nunca lê storage diretamente.
 */
export type MediaIndex = ReadonlyMap<string, MediaMeta>;

export type SurveyPacketShape = SurveyPacket.CroquitoSurveyPacket;

type PacketMediaRef = SurveyPacket.MediaRef;

/**
 * Lançado quando o survey referencia um `MediaRecord.id` ausente de `mediaIndex` —
 * precondição de quem monta o índice (deveria ter chamado `getMedia` para toda
 * referência do survey antes de empacotar), não uma forma válida de pacote incompleto.
 */
export class MissingMediaError extends Error {
  constructor(mediaId: string) {
    super(`Mídia referenciada pelo survey e ausente do índice: ${mediaId}`);
    this.name = "MissingMediaError";
  }
}

function resolveMediaRef(mediaId: string, mediaIndex: MediaIndex): PacketMediaRef {
  const meta = mediaIndex.get(mediaId);
  if (meta === undefined) {
    throw new MissingMediaError(mediaId);
  }
  return { sha256: meta.sha256, mime_type: meta.mime_type, byte_size: meta.byte_size };
}

function resolveOptionalMediaRef(
  mediaId: string | undefined,
  mediaIndex: MediaIndex,
): PacketMediaRef | undefined {
  return mediaId === undefined ? undefined : resolveMediaRef(mediaId, mediaIndex);
}

function toPacketPoint(point: SurveyPoint): SurveyPacket.SurveyPoint {
  return { id: point.id, x_mm: point.x_mm, y_mm: point.y_mm, created_at: point.created_at };
}

function toPacketSegment(segment: Segment): SurveyPacket.Segment {
  return {
    id: segment.id,
    from_point_id: segment.from_point_id,
    to_point_id: segment.to_point_id,
    created_at: segment.created_at,
  };
}

function toPacketMeasurement(measurement: Measurement): SurveyPacket.Measurement {
  return {
    id: measurement.id,
    value_mm: measurement.value_mm,
    kind: measurement.kind,
    from_point_id: measurement.from_point_id,
    to_point_id: measurement.to_point_id,
    second_from_point_id: measurement.second_from_point_id,
    second_to_point_id: measurement.second_to_point_id,
    element_id: measurement.element_id,
    instrument: measurement.instrument,
    status: measurement.status,
    justification: measurement.justification,
    created_at: measurement.created_at,
  };
}

function toPacketMediaAnchor(
  anchor: PhotoAnchor,
  mediaIndex: MediaIndex,
): SurveyPacket.MediaAnchor {
  return {
    id: anchor.id,
    media_ref: resolveMediaRef(anchor.local_media_ref, mediaIndex),
    point_id: anchor.point_id,
    element_id: anchor.element_id,
    // Domínio só ancora foto a ponto/elemento (`PhotoAnchor`). O áudio de T12 NÃO passa
    // por aqui: ele viaja em `observations[].audio_media_ref`, que é o vínculo que a nota
    // já tem — duplicá-lo como âncora criaria duas verdades sobre o mesmo arquivo.
    note_id: undefined,
    created_at: anchor.created_at,
  };
}

/**
 * Observação com o áudio (T12) resolvido por identidade de conteúdo, igual a foto: o
 * `MediaRecord.id` local nunca viaja, só sha256/mime/tamanho.
 *
 * Nota só-de-voz viaja com `text: ""` e é aceita pelo contrato canônico desde a rodada
 * de correção da T12 (`croquito_core.field.ObservationNote` exige texto não-vazio OU
 * `audio_media_ref` — a mesma regra `EMPTY_TEXT` do domínio); o mapeamento manda o texto
 * como ele é.
 */
function toPacketObservation(
  note: ObservationNote,
  mediaIndex: MediaIndex,
): SurveyPacket.ObservationNote {
  return {
    id: note.id,
    text: note.text,
    point_id: note.point_id,
    element_id: note.element_id,
    audio_media_ref: resolveOptionalMediaRef(note.audio_media_ref, mediaIndex),
    created_at: note.created_at,
  };
}

function toPacketElement(element: ElementObject): SurveyPacket.ElementObject {
  return {
    id: element.id,
    label: element.label,
    point_ids: element.point_ids,
    created_at: element.created_at,
  };
}

function toPacketWaiver(waiver: Waiver): SurveyPacket.Waiver {
  return {
    id: waiver.id,
    finding_code: waiver.finding_code,
    ref_key: waiver.ref_key,
    justification: waiver.justification,
    created_at: waiver.created_at,
  };
}

function toPacketArrivalContext(
  context: ArrivalContext,
  mediaIndex: MediaIndex,
): SurveyPacket.ArrivalContext {
  return {
    instrument: context.instrument,
    reference_note: context.reference_note,
    gps: context.gps,
    access_media_ref: resolveOptionalMediaRef(context.access_media_ref, mediaIndex),
    arrived_at: context.arrived_at,
  };
}

function toPacketOperation(operation: SurveyOperation): SurveyPacket.SurveyOperation {
  return {
    operation_id: operation.operation_id,
    device_id: operation.device_id,
    survey_id: operation.survey_id,
    seq: operation.seq,
    type: operation.type,
    payload: operation.payload,
    created_at: operation.created_at,
  };
}

/**
 * Deriva `device_id` do histórico de operações: `Survey` não guarda o campo (é o outbox
 * que sabe qual dispositivo agiu), e o Task Contract não acrescenta um parâmetro à parte
 * para isto. Decisão do Builder (T7): usa o `device_id` da primeira operação em `seq`;
 * um survey sem nenhuma operação ainda não tem o que sincronizar, por isso é erro, não
 * pacote parcial silencioso.
 */
function deviceIdFromOperations(operations: readonly SurveyOperation[]): string {
  const first = operations[0];
  if (first === undefined) {
    throw new Error(
      "toSurveyPacket exige ao menos uma operação no outbox para determinar device_id",
    );
  }
  return first.device_id;
}

/**
 * Constrói o `SurveyPacket` canônico a partir do `Survey` (fonte oficial), do histórico
 * de operações do outbox e de um índice de mídia já resolvido. Sem `tenant_id`: tenant
 * vem sempre do JWT no momento do envio (T9), nunca deste mapeamento.
 */
export function toSurveyPacket(
  survey: Survey,
  operations: readonly SurveyOperation[],
  mediaIndex: MediaIndex,
): SurveyPacketShape {
  return {
    survey_id: survey.id,
    name: survey.name,
    order_id: survey.order_id,
    device_id: deviceIdFromOperations(operations),
    created_at: survey.created_at,
    updated_at: survey.updated_at,
    points: survey.points.map(toPacketPoint),
    segments: survey.segments.map(toPacketSegment),
    measurements: survey.measurements.map(toPacketMeasurement),
    media_anchors: survey.photo_anchors.map((anchor) => toPacketMediaAnchor(anchor, mediaIndex)),
    elements: survey.elements.map(toPacketElement),
    observations: survey.observations.map((note) => toPacketObservation(note, mediaIndex)),
    gps_fixes: [],
    arrival_context:
      survey.context === undefined
        ? undefined
        : toPacketArrivalContext(survey.context, mediaIndex),
    status: surveyStatus(survey),
    waivers: surveyWaivers(survey).map(toPacketWaiver),
    operations: operations.map(toPacketOperation),
  };
}

// -----------------------------------------------------------------------------------
// Validação de forma na volta
// -----------------------------------------------------------------------------------
//
// Um pacote que volta da sincronização (T9) chega como `unknown` (JSON desserializado) —
// antes de tratá-lo como `SurveyPacketShape`, confere a forma dos campos que a fatia
// atual produz e consome. Checagem estrutural leve, não uma reimplementação de validador
// de JSON Schema: cobre presença/tipo dos campos e o formato de cada item de coleção,
// não invariantes de negócio (essas continuam nos comandos de `src/domain`).

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isNonEmptyString(value: unknown): value is string {
  return typeof value === "string" && value.length > 0;
}

function isOptionalString(value: unknown): boolean {
  return value === undefined || value === null || typeof value === "string";
}

function isArrayOf<T>(value: unknown, guard: (item: unknown) => item is T): value is T[] {
  return value === undefined || (Array.isArray(value) && value.every(guard));
}

const SURVEY_STATUSES = ["collecting", "concluded"] as const;
const MEASUREMENT_KINDS = [
  "length",
  "diagonal",
  "width",
  "radius",
  "level",
  "drop",
  "height",
  "angle",
] as const;
const MEASUREMENT_STATUSES = ["draft", "confirmed"] as const;

function isMediaRefShape(value: unknown): value is PacketMediaRef {
  return (
    isRecord(value) &&
    typeof value.sha256 === "string" &&
    /^[a-f0-9]{64}$/.test(value.sha256) &&
    typeof value.mime_type === "string" &&
    typeof value.byte_size === "number"
  );
}

function isPointShape(value: unknown): value is SurveyPacket.SurveyPoint {
  return (
    isRecord(value) &&
    isNonEmptyString(value.id) &&
    typeof value.x_mm === "number" &&
    typeof value.y_mm === "number" &&
    isNonEmptyString(value.created_at)
  );
}

function isSegmentShape(value: unknown): value is SurveyPacket.Segment {
  return (
    isRecord(value) &&
    isNonEmptyString(value.id) &&
    isNonEmptyString(value.from_point_id) &&
    isNonEmptyString(value.to_point_id) &&
    isNonEmptyString(value.created_at)
  );
}

function isMeasurementShape(value: unknown): value is SurveyPacket.Measurement {
  return (
    isRecord(value) &&
    isNonEmptyString(value.id) &&
    typeof value.value_mm === "number" &&
    typeof value.kind === "string" &&
    (MEASUREMENT_KINDS as readonly string[]).includes(value.kind) &&
    typeof value.status === "string" &&
    (MEASUREMENT_STATUSES as readonly string[]).includes(value.status) &&
    isNonEmptyString(value.instrument) &&
    isOptionalString(value.from_point_id) &&
    isOptionalString(value.to_point_id) &&
    isOptionalString(value.element_id) &&
    isOptionalString(value.justification) &&
    isNonEmptyString(value.created_at)
  );
}

function isMediaAnchorShape(value: unknown): value is SurveyPacket.MediaAnchor {
  return (
    isRecord(value) &&
    isNonEmptyString(value.id) &&
    isMediaRefShape(value.media_ref) &&
    isOptionalString(value.point_id) &&
    isOptionalString(value.element_id) &&
    isOptionalString(value.note_id) &&
    isNonEmptyString(value.created_at)
  );
}

function isObservationShape(value: unknown): value is SurveyPacket.ObservationNote {
  return (
    isRecord(value) &&
    isNonEmptyString(value.id) &&
    typeof value.text === "string" &&
    isOptionalString(value.point_id) &&
    isOptionalString(value.element_id) &&
    (value.audio_media_ref === undefined ||
      value.audio_media_ref === null ||
      isMediaRefShape(value.audio_media_ref)) &&
    isNonEmptyString(value.created_at)
  );
}

function isElementShape(value: unknown): value is SurveyPacket.ElementObject {
  return (
    isRecord(value) &&
    isNonEmptyString(value.id) &&
    typeof value.label === "string" &&
    isArrayOf(value.point_ids, (item): item is string => typeof item === "string") &&
    isNonEmptyString(value.created_at)
  );
}

function isGpsFixShape(value: unknown): value is SurveyPacket.GpsFix {
  return (
    isRecord(value) &&
    typeof value.lat === "number" &&
    typeof value.lng === "number" &&
    typeof value.accuracy_m === "number"
  );
}

function isWaiverShape(value: unknown): value is SurveyPacket.Waiver {
  return (
    isRecord(value) &&
    isNonEmptyString(value.id) &&
    isNonEmptyString(value.finding_code) &&
    isNonEmptyString(value.ref_key) &&
    isNonEmptyString(value.justification) &&
    isNonEmptyString(value.created_at)
  );
}

function isOperationShape(value: unknown): value is SurveyPacket.SurveyOperation {
  return (
    isRecord(value) &&
    isNonEmptyString(value.operation_id) &&
    isNonEmptyString(value.device_id) &&
    isNonEmptyString(value.survey_id) &&
    typeof value.seq === "number" &&
    value.seq >= 1 &&
    isNonEmptyString(value.type) &&
    (value.payload === undefined || isRecord(value.payload)) &&
    isNonEmptyString(value.created_at)
  );
}

function isArrivalContextShape(value: unknown): value is SurveyPacket.ArrivalContext {
  if (!isRecord(value)) {
    return false;
  }
  const gpsOk =
    value.gps === undefined ||
    value.gps === null ||
    value.gps === "unavailable" ||
    isGpsFixShape(value.gps);
  const mediaOk =
    value.access_media_ref === undefined ||
    value.access_media_ref === null ||
    isMediaRefShape(value.access_media_ref);
  return (
    isNonEmptyString(value.instrument) &&
    typeof value.reference_note === "string" &&
    isNonEmptyString(value.arrived_at) &&
    gpsOk &&
    mediaOk
  );
}

/**
 * Confere a forma de um `SurveyPacket` desserializado de JSON — não revalida
 * invariantes de negócio (essas vivem nos comandos de `src/domain`), só a forma que este
 * módulo produz e consome.
 */
export function isSurveyPacketShape(value: unknown): value is SurveyPacketShape {
  if (!isRecord(value)) {
    return false;
  }
  return (
    isNonEmptyString(value.survey_id) &&
    isNonEmptyString(value.name) &&
    isOptionalString(value.order_id) &&
    isNonEmptyString(value.device_id) &&
    isNonEmptyString(value.created_at) &&
    isNonEmptyString(value.updated_at) &&
    typeof value.status === "string" &&
    (SURVEY_STATUSES as readonly string[]).includes(value.status) &&
    isArrayOf(value.points, isPointShape) &&
    isArrayOf(value.segments, isSegmentShape) &&
    isArrayOf(value.measurements, isMeasurementShape) &&
    isArrayOf(value.media_anchors, isMediaAnchorShape) &&
    isArrayOf(value.elements, isElementShape) &&
    isArrayOf(value.observations, isObservationShape) &&
    isArrayOf(value.gps_fixes, isGpsFixShape) &&
    isArrayOf(value.waivers, isWaiverShape) &&
    isArrayOf(value.operations, isOperationShape) &&
    (value.arrival_context === undefined ||
      value.arrival_context === null ||
      isArrivalContextShape(value.arrival_context))
  );
}
