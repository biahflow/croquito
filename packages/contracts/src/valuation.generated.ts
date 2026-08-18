/* Arquivo gerado. Edite os modelos Pydantic e execute `make contracts`. */

export type Action = "confirm" | "reject";
export type DecidedAt = string;
export type DecisionId = string;
export type Note = string | null;
export type ReviewerId = string;
export type ReviewerRole = "orcamentista";
export type ValuationDigest = string;
/**
 * @minItems 1
 */
export type Bulletins = [WorksiteBulletin, ...WorksiteBulletin[]];
export type Address = string | null;
export type ContractLabel = string | null;
/**
 * @minItems 1
 */
export type Lines = [BulletinLine, ...BulletinLine[]];
export type Code = string;
export type Description = string;
export type ItemNumber = string;
export type Quantity = string;
export type Total = string;
export type Unit = string;
export type UnitPrice = string;
export type TotalAmount = string;
export type WorksiteKey = string;
export type WorksiteName = string;
/**
 * @minItems 1
 */
export type CalcSheets = [CalcSheet, ...CalcSheet[]];
/**
 * @minItems 1
 */
export type Blocks = [CalcBlock, ...CalcBlock[]];
export type Name = string;
export type Unit1 = string | null;
export type Value = string;
export type Deductions = CalcOperand[];
export type Label = string;
/**
 * @minItems 1
 */
export type Operands = [CalcOperand, ...CalcOperand[]];
/**
 * Receitas de cálculo aceitas na memória; a lista é fechada por marco.
 */
export type CalcRecipe =
  | "direct_quantity"
  | "length_times_width"
  | "perimeter_times_height"
  | "perim_height_minus_openings"
  | "qty_times_months"
  | "days_times_hours";
export type Subtotal = string;
export type ItemNumber1 = string;
export type TotalQuantity = string;
export type WorksiteKey1 = string;
export type Id = string;
export type PeriodNumber = number;
export type ReferenceLabel = string;
export type SchemaVersion = "2.0.0";

/**
 * Medição de um período: um boletim por obra e as memórias de cálculo de cada item.
 *
 * Nada aqui carrega saldo contratual: o que já foi medido antes vive no
 * `ContractWorkbook`, que entra por parâmetro no portão de exportação
 * (`export_errors()`/`ensure_exportable()`). O portão falha fechado — medição sem
 * aprovação nominal válida, fora da sequência de períodos ou acima do saldo não vira
 * planilha publicada. Ver docs/architecture/VALUATION_CONTEXT.md.
 */
export interface CroquitoValuation {
  approval?: ValuationApproval | null;
  bulletins: Bulletins;
  calc_sheets: CalcSheets;
  id?: Id;
  period_number: PeriodNumber;
  reference_label: ReferenceLabel;
  schema_version?: SchemaVersion;
}
/**
 * Aprovação nominal amarrada por digest ao conteúdo exato aprovado.
 *
 * Aprovar um conteúdo e exportar outro é o erro que este modelo existe para impedir:
 * o digest é recomputado no portão e qualquer edição posterior invalida a aprovação.
 */
export interface ValuationApproval {
  decision: ReviewerDecision;
  valuation_digest: ValuationDigest;
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
 * Boletim de medição de uma obra.
 */
export interface WorksiteBulletin {
  address?: Address;
  contract_label?: ContractLabel;
  lines: Lines;
  total_amount: TotalAmount;
  worksite_key: WorksiteKey;
  worksite_name: WorksiteName;
}
/**
 * Linha do boletim de medição de uma obra.
 */
export interface BulletinLine {
  code: Code;
  description: Description;
  item_number: ItemNumber;
  quantity: Quantity;
  total: Total;
  unit: Unit;
  unit_price: UnitPrice;
}
/**
 * Memória de cálculo de um item do boletim de uma obra.
 *
 * A obra faz parte da identidade: o mesmo `item_number` se repete entre obras da mesma
 * medição, e só o par `(worksite_key, item_number)` identifica a memória.
 */
export interface CalcSheet {
  blocks: Blocks;
  item_number: ItemNumber1;
  total_quantity: TotalQuantity;
  worksite_key: WorksiteKey1;
}
/**
 * Bloco de cálculo de um item: operandos multiplicados menos deduções.
 */
export interface CalcBlock {
  deductions?: Deductions;
  label: Label;
  operands: Operands;
  recipe: CalcRecipe;
  subtotal: Subtotal;
}
/**
 * Parcela impressa da memória de cálculo.
 *
 * `name` é dado, não identificador: chega em português na planilha ("PERÍMETRO").
 */
export interface CalcOperand {
  name: Name;
  unit?: Unit1;
  value: Value;
}
