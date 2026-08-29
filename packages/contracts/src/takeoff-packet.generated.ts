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
export type ElementRef = string | null;
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
export type AbsoluteFloor = string | null;
export type Difference = string;
export type Extractor1 = string;
export type ExtractorVersion1 = string;
export type Quantity1 = string;
export type ReadAt = string | null;
export type ReadBy = string | null;
export type Source = "legend_extraction" | "manual";
export type LegendRatio = string | null;
export type RelativeTolerance = string | null;
/**
 * Qual dos DOIS números passa a valer. Não há um terceiro valor, de propósito.
 *
 * "Nenhuma das duas" não é oferecida (ADR-0058, aceite de 2026-08-28): digitar uma
 * terceira quantidade na resolução seria a redigitação que a feature existe para
 * eliminar. Quem quiser um número que não é nem o da cena nem o da legenda corrige a
 * origem — a legenda, pela decisão de takeoff; a cena, pelo traçado — e volta aqui.
 */
export type DivergenceChoice = "scene" | "legend";
export type Note2 = string | null;
export type ResolvedAt = string;
export type ReviewerId1 = string;
export type ReviewerRole1 = "orcamentista";
export type ElementRef1 = string;
export type Precision = "exact" | "derived" | "approximate" | "unresolved";
export type Quantity2 = string;
export type SceneRevisionId = string | null;
export type Tolerance = string;
/**
 * Qual das duas parcelas GOVERNOU a tolerância nomeada: a relativa (1% da legenda) ou
 * o piso absoluto. Existe para a tela não precisar comparar `relative_tolerance` com
 * `absolute_floor` — o servidor já decidiu e nomeia.
 */
export type ToleranceBound = "relative" | "absolute_floor";
export type Source1 = "legend_extraction" | "manual" | "scene_graph";
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
export type SchemaVersion = "1.0.0" | "1.1.0" | "1.2.0" | "1.3.0";
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
 * Espelho de `DimensionReading`. `source` era a porta discriminada reservada no roadmap
 * (`docs/product/ROADMAP.md`) para quando o quantitativo pudesse nascer do scene graph
 * aprovado em vez da extração de legenda; a F-047 T4 a abriu com `scene_graph`.
 */
export interface TakeoffItem {
  decision?: ReviewerDecision | null;
  element_ref?: ElementRef;
  evidence: PlateEvidence;
  extractor: Extractor;
  extractor_version: ExtractorVersion;
  id: Id;
  label: Label;
  note?: Note1;
  quantity?: Quantity;
  raw_text: RawText;
  scene_divergence?: QuantityDivergence | null;
  scene_precision?: Precision | null;
  source: Source1;
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
/**
 * A issue: os dois números, as duas origens, a diferença e a tolerância que ela furou.
 *
 * O modelo se recusa a existir dentro da tolerância (`QUANTITY_DIVERGENCE_WITHIN_TOLERANCE`)
 * e a carregar uma diferença ou uma tolerância que não sejam as recomputadas dos próprios
 * números. Assim a issue nunca é um rótulo colado por fora: ela é o resultado da conta,
 * conferido na construção e a cada releitura do JSON gravado.
 *
 * `relative_tolerance`, `absolute_floor`, `tolerance_bound` e `legend_ratio` (F-047 T5b)
 * são a mesma conta por extenso que a tela precisa mostrar (pacote de design aprovado,
 * estado 06) — nascem OPCIONAIS e conferidos do mesmo jeito quando presentes, porque uma
 * divergência gravada antes desta mudança precisa continuar legível sem eles.
 */
export interface QuantityDivergence {
  absolute_floor?: AbsoluteFloor;
  difference: Difference;
  legend: LegendQuantityOrigin;
  legend_ratio?: LegendRatio;
  relative_tolerance?: RelativeTolerance;
  resolution?: QuantityDivergenceResolution | null;
  scene: SceneQuantityOrigin;
  tolerance: Tolerance;
  tolerance_bound?: ToleranceBound | null;
}
/**
 * De onde veio o número da LEGENDA: quem leu, com que versão, e quando foi decidido.
 *
 * `read_by`/`read_at` só existem depois da decisão do orçamentista sobre o item: antes
 * dela quem "leu" é o extrator, e carimbar um instante humano que ninguém praticou seria
 * inventar a metade mais auditada da origem.
 */
export interface LegendQuantityOrigin {
  extractor: Extractor1;
  extractor_version: ExtractorVersion1;
  quantity: Quantity1;
  read_at?: ReadAt;
  read_by?: ReadBy;
  source: Source;
}
/**
 * O ato humano que escolhe um dos dois números, com autor e instante.
 *
 * Espelha `ReviewerDecision` na forma, não no significado: aqui não se confirma nem se
 * rejeita um item — declara-se qual origem prevalece numa divergência já aberta.
 */
export interface QuantityDivergenceResolution {
  choice: DivergenceChoice;
  note?: Note2;
  resolved_at: ResolvedAt;
  reviewer_id: ReviewerId1;
  reviewer_role: ReviewerRole1;
}
/**
 * De onde veio o número da CENA: identidade do elemento, precisão declarada e revisão.
 *
 * A precisão é a que a entidade declarou e nunca sobe, como em toda a travessia
 * (ADR-0058 decisão 4): só `exact` e `derived` chegam até aqui, porque `approximate` não
 * alimenta quantidade e portanto também não tem com o que divergir.
 */
export interface SceneQuantityOrigin {
  element_ref: ElementRef1;
  precision: Precision;
  quantity: Quantity2;
  scene_revision_id?: SceneRevisionId;
}
