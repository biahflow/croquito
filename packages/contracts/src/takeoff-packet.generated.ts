/* Arquivo gerado. Edite os modelos Pydantic e execute `make contracts`. */

export type ImageSha256 = string;
/**
 * @minItems 1
 */
export type Items = [TakeoffItem, ...TakeoffItem[]];
export type Action = "confirm" | "reject";
export type DecidedAt = string;
export type DecisionId = string;
export type Note = string | null;
export type ReviewerId = string;
export type ReviewerRole = "orcamentista";
export type Bottom = number;
export type Left = number;
export type Right = number;
export type Top = number;
export type CoordinateSpace = "source_image_pixels";
export type ImageSha2561 = string;
export type PageNumber = number;
export type PlateId = string;
export type Extractor = string;
export type ExtractorVersion = string;
export type Id = string;
export type Label = string;
export type Note1 = string | null;
export type Quantity = string | null;
export type RawText = string;
export type Source = "legend_extraction" | "manual";
/**
 * Espelho de `ReadingStatus`: estado de revisão de uma linha da legenda.
 *
 * `AMBIGUOUS` é a linha cuja extração identificou o elemento mas não conseguiu ler a
 * quantidade — por isso ela nunca carrega `quantity`.
 */
export type TakeoffItemStatus = "proposed" | "ambiguous" | "confirmed" | "rejected";
export type Unit = string;
export type PageNumber1 = number;
export type PlateId1 = string;
/**
 * @minItems 2
 */
export type SafetyNotes = [string, string, ...string[]];
export type SafetyStatus = "human_review_required";
export type SchemaVersion = "1.0.0";
export type SourcePdfSha256 = string;

/**
 * Pacote de takeoff de uma prancha: espelho de `ReviewPacket`.
 *
 * O JSON canônico é a fonte de verdade da extração; `safety_status` fixo lembra que a
 * decisão do orçamentista continua obrigatória e nada aqui é quantitativo aprovado.
 */
export interface CroquitoTakeoffPacket {
  image_sha256: ImageSha256;
  items: Items;
  page_number: PageNumber1;
  plate_id: PlateId1;
  safety_notes: SafetyNotes;
  safety_status?: SafetyStatus;
  schema_version?: SchemaVersion;
  source_pdf_sha256: SourcePdfSha256;
}
/**
 * Uma linha da legenda quantificada, do estado observado ao confirmado pelo orçamentista.
 *
 * Espelho de `DimensionReading`. `source` é a porta discriminada reservada no roadmap
 * (`docs/product/ROADMAP.md`) para quando o quantitativo puder nascer do scene graph
 * aprovado em vez da extração de legenda.
 */
export interface TakeoffItem {
  decision?: ReviewerDecision | null;
  evidence: PlateEvidence;
  extractor: Extractor;
  extractor_version: ExtractorVersion;
  id: Id;
  label: Label;
  note?: Note1;
  quantity?: Quantity;
  raw_text: RawText;
  source: Source;
  status: TakeoffItemStatus;
  unit: Unit;
}
/**
 * Decisão humana rastreável do orçamentista.
 *
 * Duplicação local deliberada do `HumanDecision` do contexto de cena: o ADR-0016 mantém
 * os dois contextos separados, e uma decisão sobre medição não é uma decisão sobre
 * geometria. O que se repete é a forma, não o significado.
 */
export interface ReviewerDecision {
  action: Action;
  decided_at: DecidedAt;
  decision_id: DecisionId;
  note?: Note;
  reviewer_id: ReviewerId;
  reviewer_role: ReviewerRole;
}
/**
 * Espelho de `EvidenceRegion`: âncora da prancha para a linha da legenda lida.
 */
export interface PlateEvidence {
  bbox: PlateBox;
  coordinate_space?: CoordinateSpace;
  image_sha256: ImageSha2561;
  page_number: PageNumber;
  plate_id: PlateId;
}
/**
 * Espelho de `PixelBox`: recorte em pixels da prancha onde o item foi lido.
 */
export interface PlateBox {
  bottom: Bottom;
  left: Left;
  right: Right;
  top: Top;
}
