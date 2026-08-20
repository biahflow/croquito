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
import {
  buildEstimateBody,
  cascadeOrderBody,
  cascadeRemoveBody,
  codeDecisionBody,
  createEstimateBody,
  installCatalogBody,
  takeoffDecisionBody,
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

/** Linha da listagem de orçamentos do tenant. */
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
 * Uma fonte de preço instalada, com a posição que ela ocupa na cascata.
 *
 * `position` é derivado da ordem gravada e nunca é o dado autoritativo: a ORDEM da lista
 * é a precedência. `object_key` e `upload_id` não saem da API de propósito — a chave do
 * objeto é referência interna do store.
 */
export type CascadeEntry = {
  position: number;
  origin: PriceOrigin;
  source_sha256: string;
  reference_month: string;
  source_label: string;
  summary: {
    source_label?: string;
    reference_month?: string;
    source_sha256?: string;
    entries?: number;
  };
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
 * publicada — ela só existe depois de a auditoria de round-trip aprovar o arquivo, porque
 * auditoria reprovada não publica nada (ADR-0038).
 */
export type EstimateStateEstimate = {
  present: boolean;
  estimate_sha256: string | null;
  workbook_present: boolean;
  workbook_sha256: string | null;
};

export type EstimateState = {
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
  pending_items: PendingCodeItem[];
};

/**
 * O orçamento montado. Os totais viajam em TEXTO porque são `Decimal` truncados no
 * centavo: serializá-los como número de JSON devolveria um binário aproximado do valor
 * que o domínio acabou de fixar.
 *
 * `workbook_url` só existe na leitura (`GET`), montada na hora: a forma que o registro de
 * idempotência guarda no banco não carrega URL assinada.
 */
export type EstimateResponse = {
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
  baseVersion: number;
  /** Quantidade escrita pela orçamentista, em texto: `Decimal` não passa por `number`. */
  quantity?: string;
  unit?: string;
  note?: string;
  itemNote?: string;
};

export type CodeDecisionDraft = {
  itemId: string;
  action: "confirm" | "reject";
  baseVersion: number;
  code?: string;
  /** A fonte citada na confirmação; sem ela o servidor recusa o ato. */
  catalogSha256?: string;
  note?: string;
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

/** Instala uma fonte no FIM da cascata; a posição é a precedência de precificação. */
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
  draft: TakeoffDecisionDraft,
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
 * Sem `arm`, ao contrário da medição: a rota do orçamento não expõe o parâmetro, porque o
 * braço híbrido depende de índice de embeddings que nenhuma rota de `/v1` publica. O
 * motivo continua viajando em `semantic_notes` e a tela o exibe — a busca não degrada em
 * silêncio.
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
 * Monta o orçamento-base e publica a planilha, nesta ordem e atrás do mesmo portão: o
 * `.xlsx` é gravado, reaberto e reconferido centavo a centavo, e auditoria reprovada
 * (`500 ESTIMATE_WORKBOOK_AUDIT_FAILED`) não publica nada.
 *
 * `bdi_percent` é o percentual ÚNICO do orçamento inteiro e viaja como texto. Corpo que
 * não é decimal exato não sai daqui: `buildEstimateBody` devolve `null` e a recusa é da
 * tela, antes da viagem.
 */
export function postBuildEstimate(
  accessToken: string,
  roundId: string,
  bdiPercent: string,
  baseVersion: number,
): Promise<EstimateResponse> {
  const body = buildEstimateBody(bdiPercent, baseVersion);
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

/** Orçamento gravado, revalidado pelo servidor na leitura, com a URL assinada da planilha. */
export function getEstimate(
  accessToken: string,
  roundId: string,
): Promise<EstimateResponse> {
  return apiJson<EstimateResponse>(roundPath(roundId, "/estimate"), accessToken);
}
