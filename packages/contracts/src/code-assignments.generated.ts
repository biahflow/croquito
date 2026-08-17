/* Arquivo gerado. Edite os modelos Pydantic e execute `make contracts`. */

export type CatalogSha256 = string | null;
export type Code = string | null;
export type Action = "confirm" | "reject";
export type DecidedAt = string;
export type DecisionId = string;
export type Note = string | null;
export type ReviewerId = string;
export type ReviewerRole = "orcamentista";
export type ItemId = string;
export type Status = "confirmed" | "rejected";
export type UnitCompatible = boolean;
export type Assignments = CodeAssignment[];
export type CatalogSha2561 = string;
export type ContractSha256 = string | null;
export type ImageSha256 = string;
export type PageNumber = number;
export type PlateId = string;
/**
 * @minItems 2
 */
export type SafetyNotes = [string, string, ...string[]];
export type SchemaVersion = "1.0.0";

/**
 * Conjunto imutável de confirmações/rejeições de código de uma prancha.
 */
export interface CroquitoCodeAssignmentSet {
  assignments: Assignments;
  catalog_sha256: CatalogSha2561;
  contract_sha256?: ContractSha256;
  image_sha256: ImageSha256;
  page_number: PageNumber;
  plate_id: PlateId;
  safety_notes: SafetyNotes;
  schema_version?: SchemaVersion;
}
/**
 * Resultado imutável da confirmação/rejeição de código de um item.
 *
 * `catalog_sha256` carrega adiante a fonte citada na confirmação (vazio quando a rodada
 * tem um catálogo só, como em toda a medição licitada). É por ele que o orçamento-base
 * sabe, linha a linha, de qual tabela o preço veio — `build_worksite_estimate` exige a
 * citação e recusa a que não estiver na cascata.
 */
export interface CodeAssignment {
  catalog_sha256?: CatalogSha256;
  code?: Code;
  decision: ReviewerDecision;
  item_id: ItemId;
  status: Status;
  unit_compatible: UnitCompatible;
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
