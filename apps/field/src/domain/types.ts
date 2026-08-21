/**
 * Modelo de domínio do levantamento de campo.
 *
 * Tipos serializáveis puros — nenhum import de UI (React) nem de storage (Dexie).
 * `apps/field/AGENTS.md` cita esta regra: a fonte oficial do levantamento é este modelo,
 * nunca o canvas.
 *
 * Convenções:
 * - coordenadas e medidas em **milímetros inteiros** (mm), relativas à origem local do
 *   levantamento (não é lat/long — referência geográfica, quando existir, é um dado à
 *   parte);
 * - IDs são `string` (UUID, atribuído por quem cria o registro);
 * - datas são ISO 8601 em UTC.
 */

export type Millimeters = number;

export type SurveyPointId = string;
export type SegmentId = string;
export type MeasurementId = string;
export type PhotoAnchorId = string;
export type ElementObjectId = string;

/** Um ponto físico marcado em campo. */
export interface SurveyPoint {
  id: SurveyPointId;
  /** Coordenada X em mm inteiros, relativa à origem local do levantamento. */
  x_mm: Millimeters;
  /** Coordenada Y em mm inteiros, relativa à origem local do levantamento. */
  y_mm: Millimeters;
  created_at: string;
}

/** Ligação entre dois pontos — não implica medida confirmada, só topologia observada. */
export interface Segment {
  id: SegmentId;
  from_point_id: SurveyPointId;
  to_point_id: SurveyPointId;
  created_at: string;
}

export type MeasurementKind =
  | "length"
  | "diagonal"
  | "width"
  | "radius"
  | "level"
  | "drop"
  | "height"
  | "angle";

export type MeasurementStatus = "draft" | "confirmed";

/** Uma medida tomada em campo, sempre em mm inteiros — inclusive quando `kind` é
 * "angle" (grau não é uma unidade desta fatia; o valor angular ainda viaja em `value_mm`
 * até uma tarefa futura decidir a unidade própria). */
export interface Measurement {
  id: MeasurementId;
  value_mm: Millimeters;
  kind: MeasurementKind;
  from_point_id?: SurveyPointId;
  to_point_id?: SurveyPointId;
  /** Segundo segmento de uma medida `angle`, referenciado pelo seu par de pontos — o
   * primeiro segmento é `from_point_id`/`to_point_id`. Só usado quando `kind === "angle"`;
   * T2 acrescenta este par porque a regra de vínculo do comando `addMeasurement`
   * ("angle exige dois segmentos referenciáveis por par de pontos") não é representável
   * só com o par existente (ver commands.ts). */
  second_from_point_id?: SurveyPointId;
  second_to_point_id?: SurveyPointId;
  element_id?: ElementObjectId;
  /** Instrumento usado (ex.: "trena", "laser", "estimado"). */
  instrument: string;
  status: MeasurementStatus;
  /** Motivo registrado quando uma divergência ou pendência é mantida em vez de
   * sobrescrita silenciosamente (prancha 4b/5b do Design Approval Package). */
  justification?: string;
  created_at: string;
}

/** Âncora de uma foto a um ponto OU elemento do levantamento — carrega só a referência
 * local ao arquivo, nunca a foto em si (o domínio não carrega blobs).
 *
 * `point_id` era obrigatório no scaffold da fatia 0; T2 o torna opcional e acrescenta
 * `element_id` porque o comando `addPhotoAnchor` exige "ponto OU elemento existente"
 * (`ANCHOR_UNLINKED`) — sem os dois campos opcionais, ancorar a um elemento seria
 * impossível. Nenhum outro arquivo do workspace construía `PhotoAnchor` fora de
 * `src/domain`, então a mudança não exige ajuste em `src/ui`/`src/storage`. */
export interface PhotoAnchor {
  id: PhotoAnchorId;
  point_id?: SurveyPointId;
  element_id?: ElementObjectId;
  local_media_ref: string;
  created_at: string;
}

/** Anotação de campo em texto — "voz fora do MVP" (Feature Contract): o item de menu
 * "Observação (texto ou voz)" cita voz, mas o MVP só grava texto. */
export interface ObservationNote {
  id: string;
  text: string;
  point_id?: SurveyPointId;
  element_id?: ElementObjectId;
  created_at: string;
}

/** Um elemento identificado em campo (ex.: banco, poste, árvore), amarrado a um ou mais
 * pontos. */
export interface ElementObject {
  id: ElementObjectId;
  label: string;
  point_ids: SurveyPointId[];
  created_at: string;
}

/** O levantamento inteiro — a unidade de persistência e sincronização. */
export interface Survey {
  id: string;
  name: string;
  points: SurveyPoint[];
  segments: Segment[];
  measurements: Measurement[];
  photo_anchors: PhotoAnchor[];
  elements: ElementObject[];
  observations: ObservationNote[];
  created_at: string;
  updated_at: string;
}

/**
 * Resultado de um comando de domínio. Erro estruturado com código estável em
 * SCREAMING_SNAKE (mesmo padrão de `croquito_core.errors`, sem parsing de string) —
 * mensagens sempre em português.
 */
export type CommandResult =
  | { ok: true; survey: Survey; operation: { type: string; payload: Record<string, unknown> } }
  | { ok: false; error: { code: string; message: string } };
