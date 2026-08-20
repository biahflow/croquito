/* Arquivo gerado. Edite os modelos Pydantic e execute `make contracts`. */

export type CatalogSha256 = string;
export type ContractSha256 = string | null;
export type ImageSha256 = string;
export type PageNumber = number;
export type PlateId = string;
export type InputDigest = string;
export type ModelId = string;
export type PromptVersion = string;
export type Provider = string;
/**
 * @minItems 3
 */
export type SafetyNotes = [string, string, string, ...string[]];
export type SchemaVersion = "1.2.0";
export type Dims = number;
export type IndexSha256 = string;
export type ModelId1 = string;
export type Provider1 = string;
export type SuggesterVersion =
  | "lexical-sco-suggester-v1"
  | "lexical-sco-suggester-v1+llm-rerank-v1"
  | "lexical-cascade-sco-suggester-v1"
  | "hybrid-sco-suggester-v1"
  | "hybrid-sco-suggester-v1+llm-rerank-v1"
  | "hybrid-sco-suggester-v2"
  | "hybrid-sco-suggester-v2+llm-rerank-v1";
/**
 * @minItems 1
 */
export type Candidates = [CodeCandidate, ...CodeCandidate[]];
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
export type CatalogSha2561 = string | null;
export type Code = string;
export type Description = string;
export type InContract = boolean;
export type LexicalScore = number;
export type RefinementNote = string | null;
export type Status = "suggested";
export type Unit = string;
export type UnitCompatible = boolean;
export type UnitPrice = string;
export type ItemId = string;
export type Suggestions = CodeSuggestion[];
export type UnmatchedItemIds = string[];

/**
 * Pacote de sugestões de uma prancha: observação, nunca decisão.
 *
 * `suggester_version` conta a origem da ordem publicada, em duas dimensões independentes:
 * quem MONTOU a shortlist (lexical determinístico ou fusão híbrida) e se ela foi
 * **reordenada** depois por provider pago (sufixo `+llm-rerank-v1`). Os dois blocos de
 * lineage seguem a mesma regra de existir se e somente se o estágio aconteceu:
 * `refinement` para a chamada de refino, `semantic` para o braço de embeddings. É o que
 * impede o artefato de dizer "refinado" ou "híbrido" sem lineage — ou de carregar lineage
 * de uma chamada que não aconteceu.
 *
 * O `Literal` de `suggester_version` aceita `hybrid-sco-suggester-v1` E
 * `hybrid-sco-suggester-v2` (mais as formas `+llm-rerank-v1` de ambas): um artefato
 * gravado antes do bump para `v2` (rodada 2.2, amortecimento de ruído de legenda)
 * continua válido ao ser relido, e `validate_semantic_lineage` reconhece as duas versões
 * como híbridas pelo prefixo de família `SCO_HYBRID_SUGGESTER_FAMILY`, não pela versão
 * corrente — só a produção NOVA escreve `v2`.
 *
 * Com `lexical-cascade-sco-suggester-v1` (orçamento-base, `suggest_codes_over_cascade`) o
 * conjunto abrange mais de um catálogo: `catalog_sha256` do cabeçalho é o do catálogo
 * **cabeça** da cascata e a proveniência autoritativa passa a ser a de cada candidato
 * (`CodeCandidate.catalog_origin`/`catalog_sha256`). O cabeçalho continua existindo
 * porque ele amarra o conjunto à rodada; ele não afirma que todo candidato veio dali.
 */
export interface CroquitoCodeSuggestionSet {
  catalog_sha256: CatalogSha256;
  contract_sha256?: ContractSha256;
  image_sha256: ImageSha256;
  page_number: PageNumber;
  plate_id: PlateId;
  refinement?: SuggestionRefinement | null;
  safety_notes: SafetyNotes;
  schema_version?: SchemaVersion;
  semantic?: SuggestionSemantics | null;
  suggester_version?: SuggesterVersion;
  suggestions: Suggestions;
  unmatched_item_ids: UnmatchedItemIds;
}
/**
 * Lineage da chamada paga que reordenou a shortlist de uma prancha.
 *
 * Guarda o suficiente para reproduzir a auditoria da ordem publicada — quem respondeu,
 * com qual modelo, sob qual versão de prompt e sobre qual payload (`input_digest` é o
 * sha256 do texto enviado). `provider` é uma string simples de propósito: o `ADR-0016`
 * proíbe este pacote de importar o worker, então o enum de provider fica do lado de lá e
 * aqui entra só o valor dele.
 */
export interface SuggestionRefinement {
  input_digest: InputDigest;
  model_id: ModelId;
  prompt_version: PromptVersion;
  provider: Provider;
}
/**
 * Lineage do braço semântico que participou da fusão.
 *
 * Embedding não tem prompt: o que identifica a ordem produzida é o modelo, a dimensão do
 * espaço e o digest do índice do catálogo usado (`catalog-embeddings.json`). O digest do
 * próprio catálogo já viaja em `CodeSuggestionSet.catalog_sha256`, e é o índice que fica
 * amarrado a ele — trocar de índice sem trocar de catálogo aparece aqui.
 *
 * `provider` é string simples pelo mesmo motivo de `SuggestionRefinement.provider`: o
 * `ADR-0016` proíbe este pacote de importar o enum de provider do worker.
 */
export interface SuggestionSemantics {
  dims: Dims;
  index_sha256: IndexSha256;
  model_id: ModelId1;
  provider: Provider1;
}
/**
 * As sugestões elegíveis de um item, já ordenadas e cortadas em `max_candidates_per_item`.
 */
export interface CodeSuggestion {
  candidates: Candidates;
  item_id: ItemId;
}
/**
 * Um código do catálogo elegível para um item, com o porquê da ordem.
 *
 * A forma exigida do `code` depende de `catalog_origin`, pelo mesmo desenho de
 * `PriceCatalogEntry.validate_code_for_origin`: origem `sco` exige o padrão SCO estrito
 * (não a forma nua do contrato — só código com preço publicado é candidato, e a forma nua
 * nunca tem preço), as demais o superset estrutural não-SCO. Os defaults (`sco`/`None`)
 * preservam byte a byte todo artefato M1-M7 relido sem os campos novos.
 *
 * `catalog_sha256` é a proveniência do candidato quando a shortlist nasce de uma CASCATA
 * de fontes (orçamento-base, `suggest_codes_over_cascade`): com um catálogo só, o digest
 * já está no cabeçalho do conjunto e o campo continua vazio.
 *
 * `refinement_note` só existe depois de `apply_refinement`: é a justificativa do refino
 * pago para a ordem publicada, anotada no candidato que ficou em primeiro. Ela é
 * observação anexada ao candidato, nunca um campo que altere preço, unidade ou score.
 */
export interface CodeCandidate {
  catalog_origin?: PriceOrigin;
  catalog_sha256?: CatalogSha2561;
  code: Code;
  description: Description;
  in_contract: InContract;
  lexical_score: LexicalScore;
  refinement_note?: RefinementNote;
  status?: Status;
  unit: Unit;
  unit_compatible: UnitCompatible;
  unit_price: UnitPrice;
}
