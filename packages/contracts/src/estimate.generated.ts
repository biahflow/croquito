/* Arquivo gerado. Edite os modelos Pydantic e execute `make contracts`. */

export type Address = string | null;
export type Action = "confirm" | "reject";
export type ApproverId = string;
export type ApproverRole = "aprovador";
export type DecidedAt = string;
export type DecisionId = string;
export type Note = string | null;
export type EstimateDigest = string;
export type BdiPercent = string;
/**
 * @minItems 1
 */
export type CalcSheets = [CalcSheet, ...CalcSheet[]];
/**
 * @minItems 1
 */
export type Blocks = [CalcBlock, ...CalcBlock[]];
export type Name = string;
export type Unit = string | null;
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
export type ItemNumber = string;
export type TotalQuantity = string;
export type WorksiteKey = string;
/**
 * @minItems 1
 */
export type Cascade = [CatalogSource, ...CatalogSource[]];
/**
 * Fonte de preço de um catálogo: onde a cotação nasceu.
 *
 * Regra da orçamentista (M8): em obra LICITADA (`Valuation`/`WorksiteBulletin`), o
 * contrato manda e preço nunca vem de outra fonte (`BULLETIN_PRICE_ORIGIN_FORBIDDEN` em
 * `calc.py`/`workbook_writer.py`). A cadeia SCO → EMOP → SINAPI → SICRO → composição só
 * vale PRÉ-licitação (orçamento-base, fase futura); um catálogo carrega só UMA origem
 * (`CATALOG_ORIGIN_MIXED`) — mistura de fontes acontece na cascata, nunca dentro dele.
 *
 * `SINAPI` e `SICRO` (ADR-0039) são as duas tabelas de referência nacionais, cada uma
 * com importador próprio (F-026); caem no mesmo superset estrutural não-SCO que a EMOP
 * e a composição (`NON_SCO_CODE_PATTERN`) — o padrão real do código de cada fonte é
 * dado do layout do importador dela, não deste enum.
 */
export type PriceOrigin = "sco" | "emop" | "composition" | "sinapi" | "sicro";
export type ReferenceMonth = string;
export type SourceLabel = string;
export type SourceSha256 = string;
export type ImageSha256 = string;
/**
 * @minItems 1
 */
export type Lines = [EstimateLine, ...EstimateLine[]];
export type CatalogSha256 = string;
export type Code = string;
export type Description = string;
export type ItemNumber1 = string;
export type Quantity = string;
export type ReferenceMonth1 = string;
export type SourceLabel1 = string;
export type Total = string;
export type Unit1 = string;
export type UnitPrice = string;
export type UnitPriceWithBdi = string;
export type PageNumber = number;
export type PlateId = string;
/**
 * @minItems 2
 */
export type SafetyNotes = [string, string, ...string[]];
export type SchemaVersion = "2.2.0";
export type SourcePdfSha256 = string;
export type TotalAmount = string;
export type TotalAmountWithoutBdi = string;
export type UnpricedItemIds = string[];
export type WorksiteKey1 = string;
export type WorksiteName = string;

/**
 * Orçamento-base de uma obra, amarrado à prancha e à cascata que o precificou.
 *
 * Sem período, sem contrato e sem saldo: nenhum desses conceitos existe antes da
 * licitação. Aprovação existe e é própria (`approval`, ADR-0046): nominal, amarrada por
 * digest ao conteúdo exato assinado, com portão de exportação
 * (`export_errors()`/`ensure_exportable()`) que **não** recebe contrato — é a assinatura
 * sem contrato que mantém a fronteira do ADR-0027 de pé.
 *
 * A memória de cálculo é a MESMA do boletim (`CalcSheet`, montada por
 * `build_calc_blocks`), e a relação 1:1 entre linha e memória é validada como na medição —
 * quantidade que diverge da memória recusa.
 *
 * `bdi_percent` é o BDI do orçamento inteiro (ADR-0038): percentual único, nunca por
 * linha nem por grupo. `total_amount` já embute o BDI (é a soma dos `total` das linhas,
 * que recomputam sobre `unit_price_with_bdi`); `total_amount_without_bdi` é a mesma soma
 * sem o percentual, para quem for imprimir a diferença entre os dois totais truncados —
 * nunca o percentual aplicado ao total geral (decisão 4).
 */
export interface CroquitoEstimate {
  address?: Address;
  approval?: EstimateApproval | null;
  bdi_percent: BdiPercent;
  calc_sheets: CalcSheets;
  cascade: Cascade;
  image_sha256: ImageSha256;
  lines: Lines;
  page_number: PageNumber;
  plate_id: PlateId;
  safety_notes: SafetyNotes;
  schema_version?: SchemaVersion;
  source_pdf_sha256: SourcePdfSha256;
  total_amount: TotalAmount;
  total_amount_without_bdi: TotalAmountWithoutBdi;
  unpriced_item_ids?: UnpricedItemIds;
  worksite_key: WorksiteKey1;
  worksite_name: WorksiteName;
}
/**
 * Aprovação nominal amarrada por digest ao conteúdo exato aprovado.
 *
 * Aprovar um conteúdo e despachar outro é o erro que este modelo existe para impedir: o
 * digest é recomputado no portão e qualquer edição posterior do orçamento torna a
 * aprovação caduca em vez de silenciosamente válida.
 */
export interface EstimateApproval {
  decision: EstimateApproverDecision;
  estimate_digest: EstimateDigest;
}
/**
 * Decisão humana rastreável de quem aprova o orçamento-base.
 *
 * Duplicação local deliberada da FORMA de `ReviewerDecision` (ADR-0046, decisão 4), não
 * reuso dele: lá o papel é `Literal["orcamentista"]` e ampliá-lo faria um papel do
 * orçamento aparecer no vocabulário da medição. Aqui o papel é `aprovador` — na cadeia
 * real quem assina o orçamento não é quem o montou (decisão 5) — e o prefixo do id é
 * próprio. O que se repete é a forma, não o significado.
 */
export interface EstimateApproverDecision {
  action: Action;
  approver_id: ApproverId;
  approver_role: ApproverRole;
  decided_at: DecidedAt;
  decision_id: DecisionId;
  note?: Note;
}
/**
 * Memória de cálculo de um item do boletim de uma obra.
 *
 * A obra faz parte da identidade: o mesmo `item_number` se repete entre obras da mesma
 * medição, e só o par `(worksite_key, item_number)` identifica a memória.
 */
export interface CalcSheet {
  blocks: Blocks;
  item_number: ItemNumber;
  total_quantity: TotalQuantity;
  worksite_key: WorksiteKey;
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
  unit?: Unit;
  value: Value;
}
/**
 * Uma fonte de preço no manifesto da cascata: quem é, de quando e de qual arquivo.
 */
export interface CatalogSource {
  origin: PriceOrigin;
  reference_month: ReferenceMonth;
  source_label: SourceLabel;
  source_sha256: SourceSha256;
}
/**
 * Linha do orçamento-base: preço, quantidade e a fonte de onde o preço veio.
 *
 * Espelho de `BulletinLine` com a diferença que dá nome ao módulo: o boletim só tem preço
 * de contrato e por isso não precisa dizer de onde ele veio; aqui a fonte é parte da
 * linha, e o código obedece à forma da origem dela. `unit_price` é o preço de fonte, sem
 * BDI; `unit_price_with_bdi` é o preço com o percentual do orçamento aplicado e truncado
 * no centavo (ADR-0038, decisão 3) — é ele, não `unit_price`, que o total recomputa.
 */
export interface EstimateLine {
  catalog_sha256: CatalogSha256;
  code: Code;
  description: Description;
  item_number: ItemNumber1;
  price_origin: PriceOrigin;
  quantity: Quantity;
  reference_month: ReferenceMonth1;
  source_label: SourceLabel1;
  total: Total;
  unit: Unit1;
  unit_price: UnitPrice;
  unit_price_with_bdi: UnitPriceWithBdi;
}
