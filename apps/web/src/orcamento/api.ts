/**
 * Cliente do orçamento-base na API `/v1` autenticada (`/v1/estimate-rounds*`, F-020 T3).
 *
 * O transporte é o mesmo das outras jornadas (`apiJson` em `apps/web/src/api.ts`): ele
 * leva o `Authorization` da sessão OIDC, refaz a chamada uma vez quando o token expirou e
 * traduz o envelope de erro aninhado (`{detail: {code, detail, details}}`) num `ApiError`.
 * Este módulo não abre `fetch` nenhum por conta própria, exceto o `PUT` assinado do
 * presign — que é upload direto no object store e nunca passa pela API.
 *
 * Cinco invariantes moram aqui:
 *
 * - **A rodada é recurso.** Toda função cita `round_id`; nada nesta tela conversa com uma
 *   rodada implícita.
 * - **Identidade e carimbo nunca viajam.** `reviewer_id`, `reviewer_role`, `decided_at` e
 *   `decision_id` são do servidor (`extra="forbid"` recusa o corpo que os traz). Os
 *   construtores de corpo puros que garantem isso vivem em `requests.ts`.
 * - **Mutação cita `base_version` e manda `Idempotency-Key`.** A guarda otimista é da
 *   rodada e vale para a cadeia inteira; versão movida devolve `409 REVISION_CONFLICT`.
 * - **`Decimal` viaja como texto.** Quantidade, preço, total e o `bdi_percent` chegam e
 *   saem em string; nenhum número deste módulo vira `number`.
 * - **A fonte do preço é parte da decisão.** A confirmação de código cita
 *   `catalog_sha256`, e cada candidato declara de qual catálogo e de qual posição da
 *   cascata ele veio. É a diferença que separa este cliente do da medição.
 *
 * Os tipos de DOMÍNIO são os gerados de `@croquito/contracts` — pacote de takeoff,
 * shortlist, decisões de código e o `Estimate`. Escrito à mão aqui fica só o ENVELOPE de
 * cada rota (`round_id`, `version`, digests e contagens), que é da API e não do domínio.
 */

import type {
  CodeAssignmentSet,
  CodeSuggestionSet,
  Estimate,
  TakeoffPacket,
} from "@croquito/contracts";

import { apiJson, ApiError } from "../api";
import type {
  SiteSetupApplyResponse,
  SiteSetupKitListResponse,
  SiteSetupPreviewResponse,
} from "./acervo";
import type { CalcMatrix } from "./matrix";
import type { ItemPrecedent } from "./precedente";
import {
  buildEstimateBody,
  cascadeOrderBody,
  cascadeRemoveBody,
  codeClosureBody,
  codeDecisionBody,
  createEstimateBody,
  installCatalogBody,
  installReferenceCatalogBody,
  regimeBody,
  siteSetupApplyBody,
  siteSetupPreviewBody,
  takeoffDecisionBody,
  targetBody,
  versionBody,
} from "./requests";

export { ApiError };

/** `registered` = a bbox passou pelo registro fino contra a prancha; `raw` = ainda não. */
export type AnchorStatus = "registered" | "raw";

/**
 * Item do pacote com a âncora que a rota de leitura junta a ele (`anchored_packet`).
 * A junção é de leitura: o documento gravado não ganha campo nenhum, e por isso `anchor`
 * é envelope, não domínio.
 */
export type TakeoffItem = TakeoffPacket.TakeoffItem & { anchor?: AnchorStatus };

export type AnchoredTakeoffPacket = Omit<
  TakeoffPacket.CroquitoTakeoffPacket,
  "items"
> & { items: TakeoffItem[] };

/**
 * Etapa mais avançada que a rodada alcançou (`current_stage` em `estimate_rounds.py`).
 * A extração não aparece aqui: ela é estado próprio da raiz e pode estar em voo enquanto
 * a etapa corrente ainda é a prancha.
 */
export type EstimateStage =
  | "created"
  | "catalogs"
  | "plate"
  | "takeoff"
  | "code_assignments"
  | "estimate";

/**
 * Estado da chamada paga que lê a legenda. `queued` e `running` são o comando na fila;
 * `failed` traz `failure_code`. Não existe `unavailable`: ambiente sem provider recusa o
 * pedido na hora (`503 PROVIDER_UNAVAILABLE`) e a rodada continua `idle`.
 */
export type ExtractionStatus =
  | "idle"
  | "queued"
  | "running"
  | "done"
  | "failed";

/** Origem de preço como o domínio a nomeia (`PriceOrigin`). */
export type PriceOrigin = Estimate.PriceOrigin;

/**
 * Teto de verba declarado na rodada (ADR-0040): valor exato e o rótulo da demanda de onde
 * a verba veio. Os dois viajam como texto — o valor porque é `Decimal` exato, e um número
 * de JSON já teria passado por binário antes de chegar aqui.
 */
export type EstimateTarget = {
  amount: string;
  label: string | null;
};

/**
 * Bloco `{target, consumed, remaining, over}` que o servidor DERIVA a cada leitura
 * (ADR-0040, decisão 2); nada disto é persistido e nada disto é recomputado aqui.
 *
 * As quatro chaves são opcionais porque a ausência é significado, não omissão: rodada sem
 * teto não traz nenhuma delas (decisão 6 — ausência de teto não é um estado a comunicar),
 * e rodada com teto cujo orçamento ainda não foi montado traz só `target`, porque o
 * consumo depende do `total_amount` que só existe depois da montagem. `remaining` é
 * negativo no estouro, e `over` é estrito: consumir o teto inteiro está DENTRO dele.
 */
export type EstimateTargetState = {
  target?: EstimateTarget;
  consumed?: string;
  remaining?: string;
  over?: boolean;
};

/**
 * Regime de preço da rodada (ADR-0045). Um valor só, e é o único DECLARÁVEL: "demanda sob
 * contrato" é a praça orçada dentro de contrato guarda-chuva já licitado.
 *
 * Não existe o valor "pré-licitação" porque ele não é um valor: é a ausência do regime, e
 * a API a exprime omitindo o bloco inteiro. O `pre_bid` que a fronteira aceita no corpo
 * existe só para poder ser recusado com código estável (`ESTIMATE_REGIME_IRREVERSIBLE`), e
 * esta tela nunca o manda — o regime é mão única, e oferecer a volta seria oferecer o que
 * o servidor recusa.
 */
export type PricingRegime = "contracted_demand";

/**
 * Bloco `{regime}` que o servidor DERIVA a cada leitura, no molde do teto (ADR-0045).
 *
 * `allowed_cascade_origins` vem do servidor porque a regra é do servidor: a tela declara o
 * que a instalação aceitaria em vez de guardar a própria cópia da lista e descobrir a
 * divergência numa recusa.
 *
 * `amendment_candidates` é `codes.rejected` LIDO SOB O REGIME — o mesmo número, do mesmo
 * conjunto, no mesmo instante. O que muda é o significado: item cuja confirmação de código
 * foi rejeitada é candidato a aditivo, e o sinal vem do julgamento de quem revisou, nunca
 * de uma conferência contra um contrato que o orçamento não modela.
 */
export type EstimateRegime = {
  value: PricingRegime;
  allowed_cascade_origins: PriceOrigin[];
  amendment_candidates: number;
};

/**
 * A chave é opcional porque a ausência é significado, não omissão: rodada de pré-licitação
 * não traz `regime` nenhum, e é ela a rodada de sempre — cascata livre e tela de hoje.
 */
export type EstimateRegimeState = {
  regime?: EstimateRegime;
};

/**
 * Linha da listagem de orçamentos do tenant.
 *
 * O teto aparece aqui em DOIS campos crus, sem `consumed`/`remaining`/`over`: a listagem
 * não lê a cabeça de cada rodada, e aquele bloco só pode ser derivado contra o
 * `total_amount` que vive na revisão. Rodada sem teto devolve os dois nulos, e a linha do
 * teto some da lista em vez de virar "teto: —".
 */
export type EstimateSummary = {
  round_id: string;
  worksite_key: string;
  worksite_name: string;
  reference_label: string;
  version: number;
  status: string;
  stage: EstimateStage;
  extraction_status: ExtractionStatus;
  /** Origens na ORDEM da cascata, que é a precedência de precificação. */
  cascade_origins: PriceOrigin[];
  target_amount: string | null;
  target_label: string | null;
  /**
   * O regime da rodada (ADR-0045), para o card dizê-lo antes de a pessoa abrir. `null` é a
   * pré-licitação: a listagem não inventa um valor para a ausência, e o card sem selo é
   * exatamente a rodada sem regime.
   */
  pricing_regime: PricingRegime | null;
  created_at: string;
  updated_at: string;
};

/** Página da listagem; `next_cursor` é opaco e só volta quando há mais o que ler. */
export type EstimatePage = {
  items: EstimateSummary[];
  next_cursor: string | null;
};

export type EstimateCreated = {
  round_id: string;
  version: number;
  status: string;
  created_at: string;
};

/**
 * Quem publicou o ARQUIVO de uma fonte instalada (ADR-0047, decisão 7).
 *
 * Não se confunde com `PriceOrigin`: origem é de onde o PREÇO vem (SCO, EMOP, SINAPI),
 * procedência é quem publicou o arquivo — o acervo da plataforma ou o próprio cliente.
 * Uma proveniência que não distinguisse as duas mentiria sobre a origem do preço.
 */
export type CatalogProvenance = "reference_catalog" | "tenant_upload";

/**
 * Uma fonte de preço instalada, com a posição que ela ocupa na cascata.
 *
 * `position` é derivado da ordem gravada e nunca é o dado autoritativo: a ORDEM da lista
 * é a precedência. `object_key` e `upload_id` não saem da API de propósito — a chave do
 * objeto é referência interna do store.
 *
 * `provenance` é OPCIONAL aqui porque a ausência é um caso legítimo, e não uma omissão do
 * contrato: fonte instalada antes da F-037 não tem o campo gravado, e a ausência lê como
 * `tenant_upload` — que é o que ela é, porque era o único caminho que existia. Nada é
 * reescrito retroativamente, e a leitura do padrão mora em `procedenciaDaFonte`.
 */
export type CascadeEntry = {
  position: number;
  origin: PriceOrigin;
  source_sha256: string;
  reference_month: string;
  source_label: string;
  provenance?: CatalogProvenance;
  summary: {
    source_label?: string;
    reference_month?: string;
    source_sha256?: string;
    entries?: number;
  };
};

/**
 * Uma tabela do acervo como a ESCOLHA da rodada a oferece.
 *
 * É deliberadamente mais pobre que a linha da administração da plataforma: `published_by`
 * é a identidade de um operador de outro tenant, e quem escolhe uma tabela pública não tem
 * por que saber quem a publicou. O que sai é o que distingue duas linhas na lista — nome,
 * origem, data-base e tamanho — mais o digest da fonte, que é a identidade que a cascata e
 * a decisão de código já citam.
 */
export type ReferenceCatalogOption = {
  reference_catalog_id: string;
  display_name: string;
  origin: PriceOrigin;
  reference_month: string;
  entry_count: number;
  source_sha256: string;
};

/**
 * O que ESTA rodada pode instalar do acervo, já filtrado pelo servidor.
 *
 * Os dois filtros — em circulação e aceito pelo regime — são aplicados lá, e é por isso
 * que a listagem vive sob a rodada e não numa rota global: a rodada é quem conhece o
 * regime. A tela mostra o que recebeu e não guarda cópia da regra; guardá-la só produziria
 * a divergência que aparece numa recusa.
 */
export type ReferenceCatalogListResponse = {
  round_id: string;
  catalogs: ReferenceCatalogOption[];
};

export type CascadeResponse = {
  round_id: string;
  version: number;
  cascade: CascadeEntry[];
};

/** Contagens do pacote; o servidor manda sempre todas, zero inclusive. */
export type TakeoffCounts = {
  items: number;
  proposed: number;
  ambiguous: number;
  confirmed: number;
  rejected: number;
  pending: number;
};

export type AnchorCounts = {
  anchors_registered: number;
  anchors_raw: number;
};

export type EstimateStateTakeoff = Partial<TakeoffCounts> &
  Partial<AnchorCounts> & {
    present: boolean;
    packet_sha256?: string | null;
    plate_id?: string;
    page_number?: number;
    review_status?: "review_required" | "complete";
  };

export type EstimateStateCodes = {
  suggestions_present: boolean;
  suggestions_sha256: string | null;
  assignments_present: boolean;
  assignments_sha256: string | null;
  confirmed: number;
  rejected: number;
  /** Itens confirmados no takeoff ainda sem decisão de código; `null` sem pacote. */
  pending: number | null;
};

export type EstimateStateExtraction = {
  status: ExtractionStatus;
  extraction_id: string | null;
  /** Código estável do desfecho que não publicou nada; `labels.ts` o traduz. */
  failure_code: string | null;
  lineage_present: boolean;
  updated_at: string | null;
};

export type EstimateStatePlate = {
  present: boolean;
  source_sha256: string | null;
  page_count: number | null;
};

/**
 * O orçamento montado, como o estado da rodada o declara. `workbook_present` é a planilha
 * publicada — desde a F-035 ela só existe depois do DESPACHO (`POST .../estimate/export`),
 * e o despacho só acontece atrás do portão de aprovação e da auditoria de round-trip.
 * Montar não publica mais nada (ADR-0046, decisão 2).
 */
export type EstimateStateEstimate = {
  present: boolean;
  estimate_sha256: string | null;
  workbook_present: boolean;
  workbook_sha256: string | null;
};

/**
 * Aprovação nominal do orçamento-base (ADR-0046), como o servidor a DERIVA na leitura.
 *
 * Dois campos precisam ser lidos JUNTOS, e é por isso que eles vêm no mesmo bloco.
 * `approved` diz que houve ato de aprovação (a decisão `confirm`); `stale` diz que o
 * conteúdo mudou depois dele. Na aprovação **caduca** os dois valem ao mesmo tempo — houve
 * assinatura, e ela não cobre mais o que está na tela —, então uma tela que lesse só
 * `approved` ofereceria um despacho que a rota já vai recusar com
 * `APPROVAL_CONTENT_MISMATCH`.
 *
 * `stale` nunca é gravado: ele é a relação entre `approved_digest` (o conteúdo que foi
 * assinado) e `current_digest` (o que está gravado agora), calculada na leitura. Os dois
 * digests viajam para a tela poder mostrá-los lado a lado, como o desenho aprovado pede.
 *
 * Cópia deliberada da forma do irmão da medição (`medicao/api.ts`), e não import: as
 * jornadas compartilham o transporte, nunca se importam entre si.
 */
export type ApprovalState = {
  approved: boolean;
  /** Subject do JWT de quem aprovou; identidade nunca vem do cliente. */
  approved_by: string | null;
  approved_at: string | null;
  approved_digest: string | null;
  current_digest: string | null;
  stale: boolean;
};

/**
 * O bloco `{approval}` do estado da rodada, no padrão do teto e do regime: a chave só
 * aparece quando há orçamento LEGÍVEL na cabeça.
 *
 * A ausência é significado, não omissão. Rodada sem orçamento montado — ou com um
 * orçamento que não revalida mais — não traz o bloco, e devolver `approval: null` faria a
 * tela ter de distinguir "não há orçamento" de "há orçamento sem assinatura", que é
 * justamente o que `approved: false` já diz.
 */
export type EstimateApprovalState = {
  approval?: ApprovalState;
};

export type EstimateState = EstimateTargetState &
  EstimateRegimeState &
  EstimateApprovalState & {
    round_id: string;
    version: number;
    status: string;
    reviewer_role: string;
    worksite_key: string;
    worksite_name: string;
    reference_label: string;
    address: string | null;
    revision_id: string | null;
    revision_version: number | null;
    /** A cascata na ordem instalada; vazia é a rodada recém-aberta. */
    cascade: CascadeEntry[];
    artifacts: Record<string, string>;
    plate: EstimateStatePlate;
    extraction: EstimateStateExtraction;
    takeoff: EstimateStateTakeoff;
    codes: EstimateStateCodes;
    estimate: EstimateStateEstimate;
    created_at: string;
    updated_at: string;
  };

/**
 * Metadados da prancha. `image_url` é URL assinada de curta duração da página promovida:
 * ela vai direto no `src` da imagem, sem header nenhum, e **nunca** entra em log.
 */
export type PlateResponse = {
  round_id: string;
  version: number;
  upload_id: string;
  source_sha256: string;
  page_count: number | null;
  image_url: string | null;
};

export type ExtractionResponse = {
  round_id: string;
  version: number;
  extraction_id: string;
  status: ExtractionStatus;
};

/**
 * Idade do overlay declarada na leitura (ADR-0030): `stale` é a comparação entre o pacote
 * que originou o desenho e o pacote corrente. Overlay vencido é `200` com a marca, nunca
 * erro — ele continua sendo a única visão de onde cada número foi lido.
 */
export type OverlayState = {
  present: boolean;
  image_sha256: string | null;
  overlay_packet_sha256: string | null;
  stale: boolean;
};

export type OverlayResponse = OverlayState & {
  round_id: string;
  version: number;
  /** URL assinada de curta duração; vai no `src` e nunca em log. */
  image_url: string;
  packet_sha256: string;
};

export type TakeoffResponse = TakeoffCounts &
  AnchorCounts & {
    round_id: string;
    version: number;
    packet: AnchoredTakeoffPacket;
    packet_sha256: string;
    review_status: "review_required" | "complete";
  };

export type TakeoffDecisionResponse = TakeoffResponse & {
  overlay: OverlayState;
};

export type SuggestionsResponse = {
  round_id: string;
  version: number;
  suggestions: CodeSuggestionSet.CroquitoCodeSuggestionSet;
  suggestions_sha256: string;
  /** `true` quando esta chamada calculou e gravou a shortlist agora. */
  computed: boolean;
  matching: "lexical" | "hybrid";
  /** Motivo declarado do braço semântico; a busca nunca degrada em silêncio. */
  semantic_notes: string[];
  /**
   * O que o rótulo de cada elemento já disparou em praças anteriores (F-044), com a
   * contagem de praças. Envelope da rota, e não do documento da shortlist: o precedente é
   * junção de LEITURA sobre o índice, e o artefato gravado não ganha campo nenhum.
   *
   * **Opcional de propósito.** Item sem precedente não aparece na lista, e resposta sem a
   * chave é a shortlist de hoje — nos dois casos o bloco de precedente simplesmente não
   * existe na tela. Nada aqui degrada a via léxica, que continua atendendo o rótulo
   * inédito.
   *
   * O `GET` continua sem pagar nada e sem avançar a versão da rodada (ADR-0054 D7): o
   * índice sai do que já está gravado no banco.
   */
  precedents?: ItemPrecedent[];
};

/**
 * Um resultado da busca na cascata. Os três últimos campos são o que a medição não tem:
 * de qual origem, de qual catálogo e de que posição da cascata o preço veio.
 *
 * `origin` NÃO é a origem do preço: ali o servidor nomeia o BRAÇO da busca
 * (`lexical`/`semantic`). Quem diz a fonte é `price_origin`.
 */
export type CascadeSearchResult = {
  code: string;
  unit: string;
  unit_price: string;
  /** Descrição COMPLETA do catálogo; é ela que diz se o código inclui execução. */
  description: string;
  origin: string;
  lexical_score: number;
  semantic_score: number | null;
  price_origin: PriceOrigin;
  catalog_sha256: string;
  cascade_position: number;
};

export type CascadeSearchResponse = {
  round_id: string;
  version: number;
  query: string;
  terms: string[];
  limit: number;
  total_matches: number;
  semantic_matches: number;
  results: CascadeSearchResult[];
  matching: "lexical";
  semantic_notes: string[];
  expanded_terms?: Record<string, string[]>;
};

/** Item de takeoff como a API o lista nas pendências de código. */
export type PendingCodeItem = {
  item_id: string;
  label: string;
  raw_text: string;
  quantity: string | null;
  unit: string;
  note: string | null;
  status: TakeoffPacket.TakeoffItemStatus;
};

export type CodesResponse = {
  round_id: string;
  version: number;
  assignments: CodeAssignmentSet.CroquitoCodeAssignmentSet | null;
  assignments_sha256: string | null;
  confirmed: number;
  rejected: number;
  /**
   * Elementos com o pacote de serviços declarado COMPLETO. Difere de `confirmed`, que conta
   * pares `(item, código)`: um elemento que dispara seis serviços soma seis ali e um aqui.
   */
  closed: number;
  pending_items: PendingCodeItem[];
};

/**
 * O orçamento montado. Os totais viajam em TEXTO porque são `Decimal` truncados no
 * centavo: serializá-los como número de JSON devolveria um binário aproximado do valor
 * que o domínio acabou de fixar.
 *
 * `workbook_url` só existe na leitura (`GET`), montada na hora: a forma que o registro de
 * idempotência guarda no banco não carrega URL assinada.
 *
 * `approval` vem SEMPRE — aqui já existe orçamento, e "sem assinatura" é `approved: false`,
 * não ausência de bloco. É o contrário do estado da rodada, onde a chave some justamente
 * porque pode não haver orçamento nenhum.
 */
export type EstimateResponse = EstimateTargetState & {
  round_id: string;
  version: number;
  estimate: Estimate.CroquitoEstimate;
  estimate_sha256: string;
  bdi_percent: string;
  total_amount_without_bdi: string;
  total_amount: string;
  /** Itens sem preço em nenhuma fonte da cascata; declarados, nunca precificados. */
  unpriced_item_ids: string[];
  workbook_present: boolean;
  workbook_sha256: string | null;
  workbook_url?: string | null;
  approval: ApprovalState;
};

type PresignedUpload = {
  upload_id: string;
  object_key: string;
  url: string;
  headers: Record<string, string>;
  expires_at: string;
};

export type CreateEstimateDraft = {
  worksiteKey: string;
  worksiteName: string;
  referenceLabel: string;
  address?: string;
  /** Teto de verba, opcional: campo vazio é "sem teto", e sem teto nada muda (ADR-0040). */
  targetAmount?: string;
  targetLabel?: string;
  /**
   * Regime da rodada na ABERTURA (ADR-0045, F-033 revisão 2): a rodada pode nascer já
   * declarada. O tipo é o único regime declarável, e a ausência é a pré-licitação — por
   * isso o campo é opcional aqui e some do corpo quando não houver escolha.
   */
  pricingRegime?: PricingRegime;
};

export type CascadeOrderDraft = {
  /** A cascata COMPLETA, na ordem nova, por `source_sha256`. */
  cascade: readonly string[];
  baseVersion: number;
};

export type CascadeRemoveDraft = {
  /** O digest da fonte a remover; o mesmo que a confirmação de código cita. */
  sourceSha256: string;
  baseVersion: number;
};

export type TakeoffDecisionDraft = {
  itemId: string;
  action: "confirm" | "reject";
  /** Quantidade escrita pela orçamentista, em texto: `Decimal` não passa por `number`. */
  quantity?: string;
  unit?: string;
  note?: string;
  itemNote?: string;
};

/**
 * O ato de revisão do takeoff é um LOTE: a rota `/takeoff/decisions` só aceita lote, e a
 * `base_version` é UMA para o conjunto. Item a item, cada decisão avançava a versão e
 * invalidava o formulário que ainda estava aberto na tela.
 */
export type TakeoffDecisionBatchDraft = {
  baseVersion: number;
  decisions: TakeoffDecisionDraft[];
};

export type CodeClosureDraft = {
  itemId: string;
  baseVersion: number;
  note?: string;
};

export type CodeDecisionDraft = {
  itemId: string;
  action: "confirm" | "reject";
  baseVersion: number;
  code?: string;
  /** A fonte citada na confirmação; sem ela o servidor recusa o ato. */
  catalogSha256?: string;
  /**
   * Os N códigos do aceite de PACOTE (F-044): o precedente é do rótulo, e o rótulo dispara
   * um pacote inteiro, que entra numa revisão só.
   *
   * Mutuamente exclusivo com `code`/`catalogSha256` — a rota aceita um ou o outro, e cada
   * código do precedente já carrega a fonte de onde veio. `codeDecisionBody` é quem
   * garante que os dois nunca saem no mesmo corpo.
   */
  codes?: readonly string[];
  note?: string;
};

/**
 * O que a pré-visualização do acervo de canteiro cita (F-042): o acervo, os parâmetros de
 * obra declarados e as parcelas removidas. Os valores são decimais em TEXTO.
 */
export type SiteSetupPreviewDraft = {
  kitId: string;
  parameters: Readonly<Record<string, string>>;
  excludedParcelIds: readonly string[];
};

/** A aplicação é o mesmo conteúdo da prévia mais a guarda otimista da rodada. */
export type SiteSetupApplyDraft = SiteSetupPreviewDraft & {
  baseVersion: number;
};

const JSON_HEADERS: Record<string, string> = {
  "Content-Type": "application/json",
};

/** Cabeçalhos de uma mutação: JSON e a chave de idempotência da tentativa. */
function mutationHeaders(): Record<string, string> {
  return { ...JSON_HEADERS, "Idempotency-Key": crypto.randomUUID() };
}

function post<T>(
  path: string,
  accessToken: string,
  body: Record<string, unknown>,
): Promise<T> {
  return apiJson<T>(path, accessToken, {
    method: "POST",
    headers: mutationHeaders(),
    body: JSON.stringify(body),
  });
}

function roundPath(roundId: string, suffix = ""): string {
  return `/v1/estimate-rounds/${encodeURIComponent(roundId)}${suffix}`;
}

function toHex(buffer: ArrayBuffer): string {
  return Array.from(new Uint8Array(buffer), (value) =>
    value.toString(16).padStart(2, "0"),
  ).join("");
}

/**
 * Sobe um arquivo pelo presign e devolve o `upload_id` a citar depois.
 *
 * Cópia deliberada do mesmo helper da medição, e não import: as jornadas compartilham o
 * transporte, nunca se importam entre si. O byte não passa pela API — ela assina, o
 * navegador faz o `PUT` direto no object store e a rota seguinte recebe só o
 * identificador. O digest é calculado aqui e conferido lá: upload incompleto é recusado
 * em vez de virar cascata com catálogo pela metade.
 */
async function uploadFile(
  accessToken: string,
  file: File,
  contentType: "application/pdf" | "application/json",
): Promise<string> {
  const digest = toHex(
    await crypto.subtle.digest("SHA-256", await file.arrayBuffer()),
  );
  const presigned = await post<PresignedUpload>(
    "/v1/uploads/presign",
    accessToken,
    {
      filename: file.name,
      content_type: contentType,
      size_bytes: file.size,
      sha256: digest,
    },
  );
  const upload = await fetch(presigned.url, {
    method: "PUT",
    headers: presigned.headers,
    body: file,
  });
  if (!upload.ok) {
    // Código próprio: a falha aqui é do `PUT` direto no armazenamento, e chamá-la de
    // `INVALID_UPLOAD` mandaria conferir o arquivo quando o defeito é o envio.
    throw new ApiError(
      "O envio direto do arquivo não foi concluído. Tente novamente.",
      upload.status,
      "UPLOAD_TRANSFER_FAILED",
      "o PUT assinado do arquivo não foi concluído",
      {},
    );
  }
  return presigned.upload_id;
}

/** Catálogo de preços (JSON do `PriceCatalog`) que vai entrar na cascata, pelo presign. */
export function uploadCatalog(
  accessToken: string,
  file: File,
): Promise<string> {
  return uploadFile(accessToken, file, "application/json");
}

/** PDF da prancha do projetista, pelo presign; a API não recebe PDF em JSON. */
export function uploadPlateFile(
  accessToken: string,
  file: File,
): Promise<string> {
  return uploadFile(accessToken, file, "application/pdf");
}

export function listEstimates(
  accessToken: string,
  options?: { limit?: number; cursor?: string | null },
): Promise<EstimatePage> {
  const params = new URLSearchParams();
  if (options?.limit !== undefined) {
    params.set("limit", String(options.limit));
  }
  if (options?.cursor) {
    params.set("cursor", options.cursor);
  }
  const query = params.toString();
  return apiJson<EstimatePage>(
    `/v1/estimate-rounds${query ? `?${query}` : ""}`,
    accessToken,
  );
}

/**
 * Abre a rodada de orçamento. Ela nasce SEM fonte de preço: a cascata é a etapa seguinte
 * e aceita mais de uma, em ordem declarada — instalar uma só na criação faria a primeira
 * fonte parecer privilegiada.
 */
export function createEstimate(
  accessToken: string,
  draft: CreateEstimateDraft,
): Promise<EstimateCreated> {
  return post<EstimateCreated>(
    "/v1/estimate-rounds",
    accessToken,
    createEstimateBody(draft),
  );
}

export function getEstimateState(
  accessToken: string,
  roundId: string,
): Promise<EstimateState> {
  return apiJson<EstimateState>(roundPath(roundId), accessToken);
}

/**
 * Resposta do `POST .../target`: a rodada com a versão nova e o bloco do teto já derivado
 * contra a cabeça atual — sem `consumed` quando ainda não há orçamento montado.
 */
export type EstimateTargetResponse = EstimateTargetState & {
  round_id: string;
  version: number;
};

/**
 * Declara ou edita o teto de verba da rodada (ADR-0040, decisão 1). Não existe contraparte
 * de remoção: o pacote de design deixou "apagar um teto já declarado" como questão aberta,
 * e inventar o ato aqui seria decidi-la.
 *
 * `targetAmount` sai como TEXTO decimal, como o BDI: ele é `Decimal` exato no domínio, e
 * texto que não é decimal — ou que vale zero — não sai daqui. "Sem teto" é campo vazio na
 * abertura da rodada, nunca `0,00`, e a recusa da tela chega antes desta.
 */
export function postTarget(
  accessToken: string,
  roundId: string,
  baseVersion: number,
  targetAmount: string,
  targetLabel?: string,
): Promise<EstimateTargetResponse> {
  const body = targetBody(baseVersion, targetAmount, targetLabel);
  if (body === null) {
    return Promise.reject(
      new ApiError(
        "O teto informado não é um valor em reais maior que zero.",
        422,
        "ESTIMATE_TARGET_INVALID",
        "o teto de verba é um valor decimal finito e maior que zero",
        {},
      ),
    );
  }
  return post<EstimateTargetResponse>(
    roundPath(roundId, "/target"),
    accessToken,
    body,
  );
}

/**
 * Resposta do `POST .../regime`: a rodada com a versão nova e o bloco do regime já
 * derivado, do mesmo jeito que a leitura da rodada o traz.
 */
export type EstimateRegimeResponse = EstimateRegimeState & {
  round_id: string;
  version: number;
};

/**
 * Declara que a rodada corre sob contrato licitado (ADR-0045). Um ato, uma direção: o
 * corpo não tem parâmetro de regime porque só existe um valor declarável, e o `pre_bid`
 * que a fronteira aceita para poder recusá-lo (`ESTIMATE_REGIME_IRREVERSIBLE`) não sai
 * daqui. Não existe contraparte de retração — o regime é mão única, e desfazer um engano é
 * abrir outra rodada.
 *
 * Recusa possível que a tela não antecipa: cascata com fonte fora da tabela contratual
 * devolve `409 ESTIMATE_REGIME_CASCADE_DIRTY` sem gravar nada. Quem decide isso é o
 * servidor, contra a cascata que ele tem — não a cópia que esta tela leu.
 */
export function postRegime(
  accessToken: string,
  roundId: string,
  baseVersion: number,
): Promise<EstimateRegimeResponse> {
  return post<EstimateRegimeResponse>(
    roundPath(roundId, "/regime"),
    accessToken,
    regimeBody(baseVersion),
  );
}

/**
 * As tabelas do acervo que ESTA rodada pode instalar (F-037, ADR-0047).
 *
 * Leitura pura: sem `Idempotency-Key`, sem gravar nada e sem parâmetro de filtro — os dois
 * filtros (em circulação e aceito pelo regime) são do servidor. A tela não pergunta "quais
 * origens?"; ela lê o que a rodada oferece.
 */
export function listReferenceCatalogs(
  accessToken: string,
  roundId: string,
): Promise<ReferenceCatalogListResponse> {
  return apiJson<ReferenceCatalogListResponse>(
    roundPath(roundId, "/reference-catalogs"),
    accessToken,
  );
}

/**
 * Instala a tabela PRÓPRIA do cliente no FIM da cascata; a posição é a precedência de
 * precificação. O JSON já subiu pelo presign, e é o `upload_id` que a rota cita.
 */
export function installCatalog(
  accessToken: string,
  roundId: string,
  uploadId: string,
  baseVersion: number,
): Promise<CascadeResponse> {
  return post<CascadeResponse>(
    roundPath(roundId, "/catalogs"),
    accessToken,
    installCatalogBody(uploadId, baseVersion),
  );
}

/**
 * Instala uma tabela do ACERVO no fim da cascata, pela mesma rota e com as mesmas regras.
 *
 * Função separada, e não um parâmetro a mais em `installCatalog`, porque a rota aceita
 * **exatamente uma** das duas fontes: um corpo com as duas — ou com nenhuma — recusa
 * `422 ESTIMATE_CATALOG_SOURCE_INVALID`. Duas funções com um caminho cada tornam esse
 * corpo ambíguo inexpressável daqui, em vez de dependerem de quem chama lembrar da regra.
 */
export function installReferenceCatalog(
  accessToken: string,
  roundId: string,
  referenceCatalogId: string,
  baseVersion: number,
): Promise<CascadeResponse> {
  return post<CascadeResponse>(
    roundPath(roundId, "/catalogs"),
    accessToken,
    installReferenceCatalogBody(referenceCatalogId, baseVersion),
  );
}

/**
 * Reordena a cascata instalada; nenhuma fonte entra nem sai por aqui. O ato tem efeito
 * visível na etapa seguinte — a shortlist e a busca passam a devolver o bloco da fonte
 * promovida primeiro —, e por isso avança a versão da rodada.
 */
export function reorderCascade(
  accessToken: string,
  roundId: string,
  draft: CascadeOrderDraft,
): Promise<CascadeResponse> {
  return post<CascadeResponse>(
    roundPath(roundId, "/catalogs/order"),
    accessToken,
    cascadeOrderBody(draft),
  );
}

/**
 * Remove uma fonte da cascata pelo `source_sha256` dela. Fonte já citada por decisão de
 * código registrada recusa (`ESTIMATE_CASCADE_LOCKED`); a rota não apaga decisão.
 */
export function removeCascadeSource(
  accessToken: string,
  roundId: string,
  draft: CascadeRemoveDraft,
): Promise<CascadeResponse> {
  return post<CascadeResponse>(
    roundPath(roundId, "/catalogs/remove"),
    accessToken,
    cascadeRemoveBody(draft),
  );
}

/** Associa o PDF já enviado à rodada; uma rodada tem no máximo uma prancha. */
export function associatePlate(
  accessToken: string,
  roundId: string,
  uploadId: string,
  baseVersion: number,
): Promise<PlateResponse> {
  return post<PlateResponse>(roundPath(roundId, "/plate"), accessToken, {
    upload_id: uploadId,
    ...versionBody(baseVersion),
  });
}

export function getPlate(
  accessToken: string,
  roundId: string,
): Promise<PlateResponse> {
  return apiJson<PlateResponse>(roundPath(roundId, "/plate"), accessToken);
}

/**
 * Enfileira a leitura automática da legenda (`202`). É chamada PAGA de provider: ela
 * depende da autorização contratual do tenant e de o ambiente ter provider configurado, e
 * nenhum byte de prancha volta nesta resposta.
 */
export function createPlateExtraction(
  accessToken: string,
  roundId: string,
  baseVersion: number,
): Promise<ExtractionResponse> {
  return post<ExtractionResponse>(
    roundPath(roundId, "/plate/extractions"),
    accessToken,
    versionBody(baseVersion),
  );
}

export function getTakeoff(
  accessToken: string,
  roundId: string,
): Promise<TakeoffResponse> {
  return apiJson<TakeoffResponse>(roundPath(roundId, "/takeoff"), accessToken);
}

export function getTakeoffOverlay(
  accessToken: string,
  roundId: string,
): Promise<OverlayResponse> {
  return apiJson<OverlayResponse>(
    roundPath(roundId, "/takeoff/overlay"),
    accessToken,
  );
}

export function postTakeoffDecision(
  accessToken: string,
  roundId: string,
  draft: TakeoffDecisionBatchDraft,
): Promise<TakeoffDecisionResponse> {
  return post<TakeoffDecisionResponse>(
    roundPath(roundId, "/takeoff/decisions"),
    accessToken,
    takeoffDecisionBody(draft),
  );
}

/**
 * Shortlist da rodada, calculada sobre a CASCATA. A primeira leitura **calcula e grava**
 * o artefato (`computed`) sem avançar a versão da rodada — a shortlist é derivada, e um
 * `GET` não é ato humano. Por isso a tela só a busca por gesto explícito.
 */
export function getSuggestions(
  accessToken: string,
  roundId: string,
): Promise<SuggestionsResponse> {
  return apiJson<SuggestionsResponse>(
    roundPath(roundId, "/code-suggestions"),
    accessToken,
  );
}

/**
 * Recompute explícito da shortlist: é o caminho declarado de reler o efeito de uma
 * reordenação da cascata. Ao contrário do `GET`, é ato humano, cita `base_version` e
 * avança a rodada.
 *
 * É também o ÚNICO ponto em que o braço semântico pode custar (F-041, ADR-0054 D7): cada
 * fonte com índice de embeddings publicado embute os rótulos da rodada e entra na fusão.
 * Fonte sem índice, tenant sem autorização contratual ou ambiente sem provider **não**
 * derrubam o ato — a shortlist sai léxica e o motivo vem em `semantic_notes`.
 */
export function postSuggestionsRecompute(
  accessToken: string,
  roundId: string,
  baseVersion: number,
): Promise<SuggestionsResponse> {
  return post<SuggestionsResponse>(
    roundPath(roundId, "/code-suggestions/recompute"),
    accessToken,
    versionBody(baseVersion),
  );
}

/**
 * Busca léxica na cascata inteira, um bloco por fonte, na ordem instalada.
 *
 * Sem `arm`, ao contrário da medição: a rota do orçamento não expõe o parâmetro, e a busca
 * segue léxica mesmo depois de o índice de embeddings virar artefato publicado da
 * plataforma (F-041, ADR-0054). O braço semântico roda no RECOMPUTE, que é ato humano com
 * `base_version`, e não numa busca que dispara a cada tecla — pagar por tecla seria o
 * oposto da decisão D7. O motivo continua viajando em `semantic_notes` e a tela o exibe: a
 * busca não degrada em silêncio.
 */
export function searchCascade(
  accessToken: string,
  roundId: string,
  query: string,
  limit = 20,
  options?: { signal?: AbortSignal },
): Promise<CascadeSearchResponse> {
  const params = new URLSearchParams({ q: query, limit: String(limit) });
  return apiJson<CascadeSearchResponse>(
    roundPath(roundId, `/catalog/search?${params.toString()}`),
    accessToken,
    { signal: options?.signal },
  );
}

export function getCodes(
  accessToken: string,
  roundId: string,
): Promise<CodesResponse> {
  return apiJson<CodesResponse>(
    roundPath(roundId, "/code-assignments"),
    accessToken,
  );
}

export function postCodeDecision(
  accessToken: string,
  roundId: string,
  draft: CodeDecisionDraft,
): Promise<CodesResponse> {
  return post<CodesResponse>(
    roundPath(roundId, "/code-assignments/decisions"),
    accessToken,
    codeDecisionBody(draft),
  );
}

/**
 * Declara COMPLETO o pacote de serviços de um item — ato próprio, rota própria.
 *
 * Confirmar um código deixou de significar que o elemento acabou: ele pode disparar outros
 * serviços, e só este ato afirma que não dispara.
 */
export function postCodeClosure(
  accessToken: string,
  roundId: string,
  draft: CodeClosureDraft,
): Promise<CodesResponse> {
  return post<CodesResponse>(
    roundPath(roundId, "/code-assignments/closures"),
    accessToken,
    codeClosureBody(draft),
  );
}

/**
 * Os acervos de parcelas de canteiro que ESTA rodada pode aplicar (F-042).
 *
 * Leitura pura, no molde de `listReferenceCatalogs`: sem `Idempotency-Key`, sem gravar nada
 * e sem parâmetro de filtro. Cada acervo declara a versão, quantas parcelas traz e quais
 * parâmetros de obra ele CITA — a tela não deduz nenhum deles.
 */
export function listSiteSetupKits(
  accessToken: string,
  roundId: string,
): Promise<SiteSetupKitListResponse> {
  return apiJson<SiteSetupKitListResponse>(
    roundPath(roundId, "/site-setup-kits"),
    accessToken,
  );
}

/**
 * Pré-visualiza as parcelas que nasceriam: **não avança versão e não grava nada**.
 *
 * É o passo obrigatório do desenho aprovado, e a razão de ele existir é o risco declarado
 * na feature — o ganho é não digitar, e o risco é aplicar sem olhar. A resposta traz a
 * CONTA de cada parcela (os operandos nomeados) e a quantidade que o servidor computou;
 * nenhuma delas é recalculada aqui.
 *
 * Recusas próprias: `SITE_SETUP_PARAMETER_MISSING` nomeia TODOS os parâmetros faltantes e
 * `SITE_SETUP_CODE_ABSENT` nomeia os códigos que o catálogo da rodada não tem. As duas são
 * falha fechada: nada é materializado, nem as parcelas que estariam completas.
 */
export function postSiteSetupPreview(
  accessToken: string,
  roundId: string,
  draft: SiteSetupPreviewDraft,
): Promise<SiteSetupPreviewResponse> {
  return post<SiteSetupPreviewResponse>(
    roundPath(roundId, "/site-setup/preview"),
    accessToken,
    siteSetupPreviewBody(draft),
  );
}

/**
 * Aplica o acervo — ato humano, que avança a versão da rodada.
 *
 * O corpo repete o que foi pré-visualizado (acervo, parâmetros, exclusões) e acrescenta a
 * `base_version`. Reaplicar o mesmo acervo é o caminho normal, não erro: o servidor
 * substitui as parcelas dele, e as autoradas à mão continuam intactas.
 */
export function postSiteSetupApply(
  accessToken: string,
  roundId: string,
  draft: SiteSetupApplyDraft,
): Promise<SiteSetupApplyResponse> {
  return post<SiteSetupApplyResponse>(
    roundPath(roundId, "/site-setup/apply"),
    accessToken,
    siteSetupApplyBody(draft),
  );
}

/**
 * A matriz de contribuições GRAVADA da rodada. `calc_matrix: null` é a rodada que nunca
 * teve matriz — o regime legado —, e não é o mesmo que uma matriz vazia.
 */
export type CalcMatrixResponse = {
  round_id: string;
  version: number;
  calc_matrix: CalcMatrix | null;
};

/**
 * Lê a matriz gravada da rodada. Leitura PURA: sem `Idempotency-Key`, sem `base_version` e
 * sem gravar nada.
 *
 * Ela existe porque a matriz tinha dois donos: o `apply` do acervo (F-042) grava no
 * servidor, e a tela mandava no build a matriz montada só do que a sessão viu. Depois de um
 * recarregamento, montar o orçamento apagava do banco o que o acervo tinha aplicado. É por
 * esta rota que o rascunho volta a partir do que está gravado.
 */
export function getCalcMatrix(
  accessToken: string,
  roundId: string,
): Promise<CalcMatrixResponse> {
  return apiJson<CalcMatrixResponse>(
    roundPath(roundId, "/calc-matrix"),
    accessToken,
  );
}

/**
 * Monta o orçamento-base — e **só** monta (ADR-0046, decisão 2). Nenhuma planilha nasce
 * daqui desde a F-035: publicar é `postExportEstimate`, atrás do portão de aprovação.
 *
 * `bdi_percent` é o percentual ÚNICO do orçamento inteiro e viaja como texto. Corpo que
 * não é decimal exato não sai daqui: `buildEstimateBody` devolve `null` e a recusa é da
 * tela, antes da viagem.
 *
 * `calcMatrix` (F-038 "decisão 6", ADR-0053) é a matriz elemento × serviço que a
 * orçamentista montou na etapa de códigos. É OPCIONAL — sem contribuição autorada ela é
 * omitida e o servidor monta o regime legado byte-idêntico. Quando vem, viaja como
 * `calc_matrix` no mesmo corpo do build, e o servidor a valida (é o portão final).
 */
export function postBuildEstimate(
  accessToken: string,
  roundId: string,
  bdiPercent: string,
  baseVersion: number,
  calcMatrix?: CalcMatrix | null,
): Promise<EstimateResponse> {
  const body = buildEstimateBody(bdiPercent, baseVersion, calcMatrix);
  if (body === null) {
    return Promise.reject(
      new ApiError(
        "O BDI informado não é um número decimal exato.",
        422,
        "ESTIMATE_BDI_INVALID",
        "o BDI do orçamento é um percentual decimal escrito como texto",
        {},
      ),
    );
  }
  return post<EstimateResponse>(roundPath(roundId, "/estimate"), accessToken, body);
}

/**
 * Aprovação nominal do orçamento da cabeça (ADR-0046). Papel exigido: `aprovador`.
 *
 * O corpo é SÓ a guarda de concorrência. Quem aprova é o subject do JWT e o instante é o
 * relógio do servidor: não existe campo de nome do aprovador nesta jornada, e o servidor
 * recusa (`422`) qualquer corpo que traga `approver_id`, `approver_role`, `decided_at` ou
 * `decision_id`. A tela MOSTRA a identidade da sessão; ela nunca a digita nem a envia.
 *
 * Quem montou não assina: o mesmo subject devolve `403 ESTIMATE_SELF_APPROVAL_FORBIDDEN`
 * mesmo com os dois papéis no token, porque a comparação é de identidade e não de papel.
 *
 * Aprovar de novo é o caminho normal da aprovação caduca, não um erro: cada chamada é uma
 * revisão nova da cadeia append-only, e o histórico guarda as duas assinaturas.
 */
export function postApproveEstimate(
  accessToken: string,
  roundId: string,
  baseVersion: number,
): Promise<EstimateResponse> {
  return post<EstimateResponse>(
    roundPath(roundId, "/estimate/approve"),
    accessToken,
    versionBody(baseVersion),
  );
}

/**
 * Despacha a planilha do orçamento depois dos dois portões do servidor. Papel exigido:
 * `orcamentista` — assinar é assumir o conteúdo, despachar é operar o envio.
 *
 * Não há nada a escolher aqui: nem formato, nem layout, nem "despachar assim mesmo". O
 * orçamento é o da cabeça, o layout é o da prefeitura e a aprovação válida é precondição.
 * Sem ela a rota recusa com `ESTIMATE_EXPORT_BLOCKED` e **nada é escrito**, nem em arquivo
 * temporário; auditoria de round-trip reprovada é `ESTIMATE_WORKBOOK_AUDIT_FAILED` e
 * também não publica nada.
 *
 * A resposta não traz `workbook_url`: a URL assinada só sai na leitura (`getEstimate`).
 */
export function postExportEstimate(
  accessToken: string,
  roundId: string,
  baseVersion: number,
): Promise<EstimateResponse> {
  return post<EstimateResponse>(
    roundPath(roundId, "/estimate/export"),
    accessToken,
    versionBody(baseVersion),
  );
}

/** Orçamento gravado, revalidado pelo servidor na leitura, com a URL assinada da planilha. */
export function getEstimate(
  accessToken: string,
  roundId: string,
): Promise<EstimateResponse> {
  return apiJson<EstimateResponse>(roundPath(roundId, "/estimate"), accessToken);
}
