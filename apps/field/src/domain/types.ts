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
  element_id?: ElementObjectId;
  /** Instrumento usado (ex.: "trena", "laser", "estimado"). */
  instrument: string;
  status: MeasurementStatus;
  created_at: string;
}

/** Âncora de uma foto a um ponto do levantamento — carrega só a referência local ao
 * arquivo, nunca a foto em si (o domínio não carrega blobs). */
export interface PhotoAnchor {
  id: PhotoAnchorId;
  point_id: SurveyPointId;
  local_media_ref: string;
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
  created_at: string;
  updated_at: string;
}
