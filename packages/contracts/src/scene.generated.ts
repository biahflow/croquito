/* Arquivo gerado. Edite os modelos Pydantic e execute `make contracts`. */

export type AcceptedApproximationIds = string[];
export type Approved = boolean;
/**
 * @minItems 1
 */
export type EntityIds = [string, ...string[]];
export type Hard = boolean;
export type Id = string;
export type Kind = string;
export type Satisfied = boolean | null;
export type Tolerance = number;
export type Constraints = Constraint[];
export type CreatedAt = string;
export type ElementRef = string | null;
export type Export = boolean;
export type Fill = "none" | "hatch";
export type Geometry =
  | LineGeometry
  | PolylineGeometry
  | CircleGeometry
  | ArcGeometry
  | SplineGeometry
  | TextGeometry
  | DimensionGeometry
  | DiameterDimensionGeometry;
export type X = number;
export type Y = number;
export type Type = "line";
export type Closed = boolean;
/**
 * @minItems 2
 */
export type Points = [Point2D, Point2D, ...Point2D[]];
export type Type1 = "polyline";
export type Radius = number;
export type Type2 = "circle";
export type EndAngle = number;
export type Radius1 = number;
export type StartAngle = number;
export type Type3 = "arc";
/**
 * @minItems 3
 */
export type FitPoints = [Point2D, Point2D, Point2D, ...Point2D[]];
export type Type4 = "spline";
export type Height = number;
export type Rotation = number;
export type Text = string;
export type Type5 = "text";
export type TextOverride = string | null;
export type Type6 = "dimension";
export type Angle = number;
export type Radius2 = number;
export type TextOverride1 = string | null;
export type Type7 = "diameter_dimension";
export type Id1 = string;
export type EntityKind =
  "line" | "polyline" | "circle" | "arc" | "spline" | "text" | "dimension" | "diameter_dimension";
export type LayerName =
  | "CONTORNO"
  | "CAMPO"
  | "QUADRA"
  | "MURO"
  | "ALAMBRADO"
  | "PORTAO"
  | "PATAMAR"
  | "EQUIPAMENTOS"
  | "COTAS"
  | "TEXTOS"
  | "DETALHES"
  | "APROXIMADO"
  | "REVISAO";
export type Precision = "exact" | "derived" | "approximate" | "unresolved";
/**
 * @minItems 1
 * @maxItems 20
 */
export type SourceIds =
  | [string]
  | [string, string]
  | [string, string, string]
  | [string, string, string, string]
  | [string, string, string, string, string]
  | [string, string, string, string, string, string]
  | [string, string, string, string, string, string, string]
  | [string, string, string, string, string, string, string, string]
  | [string, string, string, string, string, string, string, string, string]
  | [string, string, string, string, string, string, string, string, string, string]
  | [string, string, string, string, string, string, string, string, string, string, string]
  | [string, string, string, string, string, string, string, string, string, string, string, string]
  | [
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
    ]
  | [
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
    ]
  | [
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
    ]
  | [
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
    ]
  | [
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
    ]
  | [
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
    ]
  | [
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
    ]
  | [
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
    ];
export type SourceType = string;
export type SummaryCode = string;
export type Entities = Entity[];
export type Id2 = string;
export type Code = string;
export type EntityIds1 = string[];
export type Id3 = string;
export type Message = string;
export type IssueSeverity = "info" | "warning" | "critical";
export type IssueStatus = "open" | "resolved" | "accepted";
export type Issues = Issue[];
export type JobId = string;
export type Confirmed = boolean;
export type EntityId = string;
export type Id4 = string;
export type MeasurementKind =
  "length" | "width" | "height" | "radius" | "diameter" | "angle" | "area";
export type RawText = string | null;
export type UnitCode = "m" | "mm" | "rad" | "deg" | "m2";
export type ValueSi = number | string | null;
export type WrittenDecimals = number;
export type Measurements = Measurement[];
export type SchemaVersion = "1.0.0";
export type Version = number;

export interface CroquitoSceneRevision {
  accepted_approximation_ids?: AcceptedApproximationIds;
  approved?: Approved;
  constraints?: Constraints;
  created_at?: CreatedAt;
  element_labels?: ElementLabels;
  entities: Entities;
  id?: Id2;
  issues?: Issues;
  job_id: JobId;
  measurements?: Measurements;
  schema_version?: SchemaVersion;
  version: Version;
}
export interface Constraint {
  entity_ids: EntityIds;
  hard?: Hard;
  id?: Id;
  kind: Kind;
  satisfied?: Satisfied;
  tolerance: Tolerance;
}
export interface ElementLabels {
  /**
   * This interface was referenced by `ElementLabels`'s JSON-Schema definition
   * via the `patternProperty` "^EL-\d{3,}$".
   */
  [k: string]: string;
}
export interface Entity {
  element_ref?: ElementRef;
  export?: Export;
  fill?: Fill;
  geometry: Geometry;
  id?: Id1;
  kind: EntityKind;
  layer: LayerName;
  precision: Precision;
  provenance?: Provenance | null;
}
export interface LineGeometry {
  end: Point2D;
  start: Point2D;
  type?: Type;
}
export interface Point2D {
  x: X;
  y: Y;
}
export interface PolylineGeometry {
  closed?: Closed;
  points: Points;
  type?: Type1;
}
export interface CircleGeometry {
  center: Point2D;
  radius: Radius;
  type?: Type2;
}
export interface ArcGeometry {
  center: Point2D;
  end_angle: EndAngle;
  radius: Radius1;
  start_angle: StartAngle;
  type?: Type3;
}
export interface SplineGeometry {
  fit_points: FitPoints;
  type?: Type4;
}
export interface TextGeometry {
  height: Height;
  insertion: Point2D;
  rotation?: Rotation;
  text: Text;
  type?: Type5;
}
export interface DimensionGeometry {
  base: Point2D;
  first: Point2D;
  second: Point2D;
  text_override?: TextOverride;
  type?: Type6;
}
/**
 * Cota diametral (⌀) de um círculo, desenhada como DIMENSION diametral no CAD.
 */
export interface DiameterDimensionGeometry {
  angle: Angle;
  center: Point2D;
  radius: Radius2;
  text_override?: TextOverride1;
  type?: Type7;
}
export interface Provenance {
  source_ids: SourceIds;
  source_type: SourceType;
  summary_code: SummaryCode;
}
export interface Issue {
  code: Code;
  entity_ids?: EntityIds1;
  id?: Id3;
  message: Message;
  severity: IssueSeverity;
  status?: IssueStatus;
}
export interface Measurement {
  confirmed?: Confirmed;
  entity_id: EntityId;
  id?: Id4;
  kind: MeasurementKind;
  provenance?: Provenance | null;
  raw_text?: RawText;
  unit: UnitCode;
  value_si?: ValueSi;
  written_decimals?: WrittenDecimals;
}
