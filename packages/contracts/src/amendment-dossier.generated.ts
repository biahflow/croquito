/* Arquivo gerado. Edite os modelos Pydantic e execute `make contracts`. */

export type CatalogSha256 = string;
export type ContractSha256 = string | null;
export type ImageSha256 = string;
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
export type ItemId = string;
export type ItemNote = string | null;
export type Justification = string;
export type Label = string;
export type Quantity = string;
export type RawText = string;
export type Unit = string;
export type Items = AmendmentDossierItem[];
export type PageNumber1 = number;
export type PlateId1 = string;
/**
 * @minItems 2
 */
export type SafetyNotes = [string, string, ...string[]];
export type SchemaVersion = "1.0.0";
export type SourcePdfSha256 = string;

/**
 * Dossiê do aditivo de uma prancha.
 *
 * Lista `items` vazia é desfecho normal: uma rodada sem nenhuma rejeição de código não
 * tem aditivo, e isso não é uma condição de erro.
 */
export interface CroquitoAmendmentDossier {
  catalog_sha256: CatalogSha256;
  contract_sha256?: ContractSha256;
  image_sha256: ImageSha256;
  items: Items;
  page_number: PageNumber1;
  plate_id: PlateId1;
  safety_notes: SafetyNotes;
  schema_version?: SchemaVersion;
  source_pdf_sha256: SourcePdfSha256;
}
/**
 * Um item confirmado no takeoff cujo código foi rejeitado: candidato a aditivo.
 *
 * Nenhum campo de preço existe aqui, por construção: o dossiê instrui o pedido de
 * aditivo, nunca o precifica. `justification` é a `decision.note` da rejeição de
 * código, nunca inventada; `item_note` é a anotação que já acompanhava o item na
 * legenda (ex.: `h=1.00m`), distinta da justificativa da rejeição.
 */
export interface AmendmentDossierItem {
  decision: ReviewerDecision;
  evidence: PlateEvidence;
  item_id: ItemId;
  item_note?: ItemNote;
  justification: Justification;
  label: Label;
  quantity: Quantity;
  raw_text: RawText;
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
