/* Arquivo gerado. Edite os modelos Pydantic e execute `make contracts`. */

export type ByteSize = number;
export type MimeType = string;
export type Sha256 = string;
export type ArrivedAt = string;
export type Gps = GpsFix | "unavailable" | null;
export type AccuracyM = number;
export type Lat = number;
export type Lng = number;
export type Instrument = string;
export type ReferenceNote = string;
export type CreatedAt = string;
export type DeviceId = string;
export type CreatedAt1 = string;
export type Id = string;
export type Label = string;
export type PointIds = string[];
export type Elements = ElementObject[];
export type GpsFixes = GpsFix[];
export type CreatedAt2 = string;
export type ElementId = string | null;
export type FromPointId = string | null;
export type Id1 = string;
export type Instrument1 = string;
export type Justification = string | null;
/**
 * Espelho de `MeasurementKind` (`apps/field/src/domain/types.ts`).
 */
export type MeasurementKind =
  "length" | "diagonal" | "width" | "radius" | "level" | "drop" | "height" | "angle";
export type SecondFromPointId = string | null;
export type SecondToPointId = string | null;
/**
 * Espelho de `MeasurementStatus`.
 */
export type MeasurementStatus = "draft" | "confirmed";
export type ToPointId = string | null;
export type ValueMm = number;
export type Measurements = Measurement[];
export type CreatedAt3 = string;
export type ElementId1 = string | null;
export type Id2 = string;
export type NoteId = string | null;
export type PointId = string | null;
export type MediaAnchors = MediaAnchor[];
export type Name = string;
export type CreatedAt4 = string;
export type ElementId2 = string | null;
export type Id3 = string;
export type PointId1 = string | null;
export type Text = string;
export type Observations = ObservationNote[];
export type CreatedAt5 = string;
export type DeviceId1 = string;
export type OperationId = string;
export type Seq = number;
export type SurveyId = string;
export type Type = string;
export type Operations = SurveyOperation[];
export type OrderId = string | null;
export type CreatedAt6 = string;
export type Id4 = string;
export type XMm = number;
export type YMm = number;
export type Points = SurveyPoint[];
export type CreatedAt7 = string;
export type FromPointId1 = string;
export type Id5 = string;
export type ToPointId1 = string;
export type Segments = Segment[];
/**
 * Espelho de `SurveyStatus` (T5).
 */
export type SurveyStatus = "collecting" | "concluded";
export type SurveyId1 = string;
export type UpdatedAt = string;
export type CreatedAt8 = string;
export type FindingCode = string;
export type Id6 = string;
export type Justification1 = string;
export type RefKey = string;
export type Waivers = Waiver[];

/**
 * Pacote de levantamento de campo — o `Survey` inteiro pronto para sincronização
 * (T9). Sem `tenant_id`: tenant vem sempre do JWT no momento do envio.
 *
 * `status`/`waivers` viajam sempre resolvidos (equivalente a `surveyStatus`/
 * `surveyWaivers` do domínio, nunca o campo bruto opcional pré-T5); `order_id` e
 * `arrival_context` continuam opcionais porque o próprio domínio os declara assim
 * (levantamento legado sem ordem de origem; chegada ainda não registrada).
 */
export interface CroquitoSurveyPacket {
  arrival_context?: ArrivalContext | null;
  created_at: CreatedAt;
  device_id: DeviceId;
  elements?: Elements;
  gps_fixes?: GpsFixes;
  measurements?: Measurements;
  media_anchors?: MediaAnchors;
  name: Name;
  observations?: Observations;
  operations?: Operations;
  order_id?: OrderId;
  points?: Points;
  segments?: Segments;
  status: SurveyStatus;
  survey_id: SurveyId1;
  updated_at: UpdatedAt;
  waivers?: Waivers;
}
/**
 * Espelho de `ArrivalContext` (prancha 2). `access_media_ref` carrega a referência
 * de mídia resolvida (sha256/mime_type/byte_size), não o `MediaRecord.id` local —
 * mesma razão de `MediaAnchor.media_ref`.
 */
export interface ArrivalContext {
  access_media_ref?: MediaRef | null;
  arrived_at: ArrivedAt;
  gps?: Gps;
  instrument: Instrument;
  reference_note: ReferenceNote;
}
/**
 * Referência a um arquivo de mídia local — nunca o blob (`apps/field/AGENTS.md`:
 * "o domínio não carrega blobs"). `sha256`/`mime_type`/`byte_size` espelham
 * `MediaRecord` (`apps/field/src/storage/SurveyRepository.ts`), sem o campo `blob`.
 */
export interface MediaRef {
  byte_size: ByteSize;
  mime_type: MimeType;
  sha256: Sha256;
}
/**
 * Espelho de `GpsFix` — referência geográfica, nunca medição.
 */
export interface GpsFix {
  accuracy_m: AccuracyM;
  lat: Lat;
  lng: Lng;
}
/**
 * Espelho de `ElementObject`.
 */
export interface ElementObject {
  created_at: CreatedAt1;
  id: Id;
  label: Label;
  point_ids?: PointIds;
}
/**
 * Espelho de `Measurement`. `value_mm` nunca é negativo — diferente de
 * `x_mm`/`y_mm`, que são coordenadas relativas a uma origem local e podem ser
 * negativas.
 */
export interface Measurement {
  created_at: CreatedAt2;
  element_id?: ElementId;
  from_point_id?: FromPointId;
  id: Id1;
  instrument: Instrument1;
  justification?: Justification;
  kind: MeasurementKind;
  second_from_point_id?: SecondFromPointId;
  second_to_point_id?: SecondToPointId;
  status: MeasurementStatus;
  to_point_id?: ToPointId;
  value_mm: ValueMm;
}
/**
 * Âncora de uma foto OU áudio a um ponto, elemento ou nota do levantamento — envelope
 * único para os dois tipos de mídia (`local_media_ref`/áudio de T12), sempre resolvido
 * para `media_ref` (sha256/mime_type/byte_size) pelo mapeamento de
 * `apps/field/src/sync/contract.ts`, nunca a referência local (`MediaRecord.id`), que só
 * tem sentido dentro do dispositivo de origem.
 */
export interface MediaAnchor {
  created_at: CreatedAt3;
  element_id?: ElementId1;
  id: Id2;
  media_ref: MediaRef;
  note_id?: NoteId;
  point_id?: PointId;
}
/**
 * Espelho de `ObservationNote`. Desde a T12 (prancha 7a da DAP rev.2, aprovada) a
 * nota pode ser texto, voz (`audio_media_ref`) ou os dois; o que continua inválido é a
 * nota VAZIA — sem texto e sem áudio ela não registra nada, mesma regra `EMPTY_TEXT`
 * do domínio do app (`apps/field/src/domain/commands.ts`).
 */
export interface ObservationNote {
  audio_media_ref?: MediaRef | null;
  created_at: CreatedAt4;
  element_id?: ElementId2;
  id: Id3;
  point_id?: PointId1;
  text: Text;
}
/**
 * Espelho de `SurveyOperation` (`apps/field/src/outbox/types.ts`) — histórico do
 * outbox, sem `status`: reconhecimento (`ack`) é estado local do app, nunca viaja no
 * pacote.
 */
export interface SurveyOperation {
  created_at: CreatedAt5;
  device_id: DeviceId1;
  operation_id: OperationId;
  payload?: Payload;
  seq: Seq;
  survey_id: SurveyId;
  type: Type;
}
export interface Payload {
  [k: string]: unknown;
}
/**
 * Espelho de `SurveyPoint`.
 */
export interface SurveyPoint {
  created_at: CreatedAt6;
  id: Id4;
  x_mm: XMm;
  y_mm: YMm;
}
/**
 * Espelho de `Segment` — ligação observada entre dois pontos, sem medida
 * confirmada.
 */
export interface Segment {
  created_at: CreatedAt7;
  from_point_id: FromPointId1;
  id: Id5;
  to_point_id: ToPointId1;
}
/**
 * Espelho de `Waiver` (prancha 5b) — justificativa de pendência não crítica mantida
 * na conclusão.
 */
export interface Waiver {
  created_at: CreatedAt8;
  finding_code: FindingCode;
  id: Id6;
  justification: Justification1;
  ref_key: RefKey;
}
