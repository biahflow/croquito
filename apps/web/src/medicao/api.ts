/**
 * Cliente do servidor **local** de homologação da medição (Fase A do M6).
 *
 * Os tipos abaixo são escritos à mão como espelho do contrato de
 * `services/worker/src/croquito_worker/valuation/local_server.py` — mesma prática do
 * `apps/web/src/api.ts`, porque este contexto não tem schema gerado. Quando uma rota
 * mudar lá, ela muda aqui; nada nesta tela adivinha campo que o servidor não mandou.
 *
 * Três invariantes moram neste módulo:
 *
 * - **Identidade e carimbo nunca viajam.** `reviewer_id`, `reviewer_role`, `decided_at` e
 *   `decision_id` são do servidor (`extra="forbid"` recusa o corpo que os traz). Os
 *   construtores de corpo abaixo existem para que isso seja testável, não só prometido.
 * - **Mutação sempre cita o digest-base lido.** É a guarda otimista local, o substituto
 *   declarado do `base_version` da API de cena: decisão só entra sobre o estado que esta
 *   tela realmente leu.
 * - **`Decimal` viaja como texto.** Quantidade e dinheiro chegam em string e são exibidos
 *   como string formatada (`format.ts`); nenhum número da medição vira `number` aqui.
 */

/**
 * Base do servidor de medição; a UI não fala com mais nada.
 *
 * Em desenvolvimento é o servidor local em `http://localhost:8801`. No build servido pelo
 * nginx do host público a base é RELATIVA (`/medicao/api`), e o proxy same-origin leva a
 * chamada ao serviço interno — nenhum host aparece no bundle.
 */
export const apiBaseUrl =
  import.meta.env.VITE_MEDICAO_API_BASE_URL ?? "http://localhost:8801";

/**
 * Fonte do access token da sessão (`apps/web/src/auth.ts`), injetada pela tela.
 *
 * O módulo de API não conhece OIDC: ele pergunta o token a quem tem a sessão e manda o
 * `Authorization` quando existe resposta. Sem provider — o caminho do servidor local, que
 * não autentica (ADR-0020) — nenhum header extra é enviado e nada da rotina local muda.
 */
let accessTokenProvider: (() => string | null) | null = null;

export function setAccessTokenProvider(
  provider: (() => string | null) | null,
): void {
  accessTokenProvider = provider;
}

/** `{}` sem sessão; um `Authorization` quando o provider devolve token. */
function authHeaders(): Record<string, string> {
  const token = accessTokenProvider?.() ?? null;
  return token ? { Authorization: `Bearer ${token}` } : {};
}

export type TakeoffItemStatus =
  | "proposed"
  | "ambiguous"
  | "confirmed"
  | "rejected";

export type PlateBox = {
  left: number;
  top: number;
  right: number;
  bottom: number;
};

export type ReviewerDecision = {
  decision_id: string;
  action: "confirm" | "reject";
  reviewer_id: string;
  reviewer_role: string;
  decided_at: string;
  note: string | null;
};

/** `registered` = a bbox passou pelo registro fino contra a prancha; `raw` = ainda não. */
export type AnchorStatus = "registered" | "raw";

export type TakeoffItem = {
  id: string;
  evidence: {
    plate_id: string;
    page_number: number;
    image_sha256: string;
    coordinate_space: string;
    bbox: PlateBox;
  };
  raw_text: string;
  label: string;
  /** `Decimal` em texto; `null` no item ambíguo, que é a linha sem quantidade legível. */
  quantity: string | null;
  unit: string;
  source: string;
  extractor: string;
  extractor_version: string;
  note: string | null;
  status: TakeoffItemStatus;
  decision: ReviewerDecision | null;
  /** Ausente em servidor anterior a este campo (rollout local); `itemAnchor` trata a
   * ausência como `"raw"`, nunca como confirmado. */
  anchor?: AnchorStatus;
};

/**
 * Confiabilidade da localização (`evidence.bbox`) de um item na prancha, tolerante à
 * ausência do campo no servidor: sem `anchor`, o lado conservador é `"raw"` — nunca
 * desenhar um retângulo sobre a prancha sem confirmação de que ele está no lugar certo.
 */
export function itemAnchor(item: TakeoffItem): AnchorStatus {
  return item.anchor ?? "raw";
}

export type TakeoffPacket = {
  schema_version: string;
  plate_id: string;
  page_number: number;
  image_sha256: string;
  source_pdf_sha256: string;
  items: TakeoffItem[];
  safety_status: string;
  safety_notes: string[];
};

/** Contagens do pacote; o servidor manda sempre as quatro, zero inclusive. */
export type TakeoffCounts = {
  items: number;
  proposed: number;
  ambiguous: number;
  confirmed: number;
  rejected: number;
  pending: number;
};

export type RunStateTakeoff = Partial<TakeoffCounts> & {
  present: boolean;
  packet_sha256?: string;
  plate_id?: string;
  page_number?: number;
  review_status?: "review_required" | "complete";
};

export type RunStateCodes = {
  suggestions_present: boolean;
  suggestions_sha256: string | null;
  assignments_present: boolean;
  assignments_sha256: string | null;
  confirmed: number;
  rejected: number;
  /** Itens confirmados no takeoff ainda sem decisão de código; `null` sem pacote. */
  pending: number | null;
};

/** `idle` = sem prancha ou prancha ingerida sem disparo ainda; `unavailable` = servidor
 * sem teto de gasto/credencial — nunca chegou a chamar o provider; `failed` = chamou e
 * não fechou. Os dois últimos são visíveis na tela, nunca escondidos atrás de `idle`. */
export type ExtractionStatus = "idle" | "running" | "done" | "failed" | "unavailable";

/** Lineage e custo da chamada paga que leu a legenda; nunca a resposta bruta do provider. */
export type ExtractionExecution = {
  provider: string;
  model_id: string;
  prompt_version: string;
  input_digest: string;
  latency_ms: number;
  input_tokens: number;
  output_tokens: number;
  /** `Decimal` em texto, como todo dinheiro nesta tela; `null` quando o provider não informou. */
  estimated_cost_usd: string | null;
};

/** Etapa `extracao` do `/state`: o que a chamada paga fez, está fazendo ou não pôde fazer. */
export type ExtractionState = {
  status: ExtractionStatus;
  error_code: string | null;
  /** Já em língua de obra, escrita pelo servidor; a tela mostra como está, sem reescrever. */
  message: string | null;
  details: Record<string, unknown> | null;
  execution: ExtractionExecution | null;
  consented_source_sha256: string | null;
  arm: string;
  plate_pdf_present: boolean;
  /** Páginas do PDF enviado; só a página 1 vira prancha. `null` sem prancha nenhuma. */
  pages: number | null;
  page_number: number;
  /** Avisos declarados do servidor (ex.: PDF multi-página); a tela exibe literal, sem reescrever. */
  notes: string[];
};

/** Etapa `busca_semantica` do `/state`: disponível, limitada ao cache ou indisponível.
 * Nada aqui bloqueia a tela — é sempre informativo, com o motivo colado na mensagem. */
export type SemanticSearchState = {
  status: "available" | "limited" | "unavailable";
  message: string;
  index_present: boolean;
  model_id: string | null;
};

export type RunState = {
  server_version: string;
  root: string;
  reviewer_id: string;
  reviewer_role: string;
  artifacts: Record<string, string>;
  busca_semantica: SemanticSearchState;
  images: {
    plate: { present: boolean; filename: string | null };
    overlay: { present: boolean };
  };
  extracao: ExtractionState;
  takeoff: RunStateTakeoff;
  codes: RunStateCodes;
  bulletin: { present: boolean; valuation_sha256: string | null };
  dossier: { present: boolean; dossier_sha256: string | null };
};

export type TakeoffResponse = {
  packet: TakeoffPacket;
  packet_sha256: string;
};

export type TakeoffDecisionResponse = TakeoffCounts & {
  packet: TakeoffPacket;
  packet_sha256: string;
  review_status: "review_required" | "complete";
  overlay_written: boolean;
  notes: string[];
};

export type CodeCandidate = {
  code: string;
  description: string;
  unit: string;
  unit_price: string;
  unit_compatible: boolean;
  in_contract: boolean;
  lexical_score: number;
  status: string;
  refinement_note: string | null;
};

export type CodeSuggestionSet = {
  schema_version: string;
  plate_id: string;
  page_number: number;
  image_sha256: string;
  catalog_sha256: string;
  contract_sha256: string | null;
  suggester_version: string;
  suggestions: { item_id: string; candidates: CodeCandidate[] }[];
  /** Itens confirmados sem nenhum candidato lexical: caminho é a busca no catálogo. */
  unmatched_item_ids: string[];
  safety_notes: string[];
};

export type SuggestionsResponse = {
  suggestions: CodeSuggestionSet;
  suggestions_sha256: string;
  /** `true` quando esta chamada calculou e gravou a shortlist agora. */
  computed: boolean;
  /** `hybrid` = fusão léxico + semântica; `lexical` = só o braço determinístico. Derivado
   * do `suggester_version` do próprio conjunto, então continua verdadeiro quando a
   * resposta vem do arquivo já gravado por outra sessão. */
  matching: "lexical" | "hybrid";
  /** Avisos do braço semântico, sempre em língua de obra; vazio quando ele não teve nada
   * a dizer (ou não foi nem tentado). */
  semantic_notes: string[];
};

export type CatalogSearchResult = {
  code: string;
  unit: string;
  unit_price: string;
  /** Descrição COMPLETA do catálogo; é ela que diz se o código inclui execução. */
  description: string;
};

export type CatalogSearchResponse = {
  query: string;
  terms: string[];
  limit: number;
  total_matches: number;
  results: CatalogSearchResult[];
  /** `hybrid` = fusão léxico + semântica; `lexical` = só o braço determinístico (inclusive
   * quando fixado por `arm=lexical`). */
  matching: "lexical" | "hybrid";
  /** Avisos do braço semântico em língua de obra; vazio quando ele não teve nada a dizer. */
  semantic_notes: string[];
};

export type CodeAssignment = {
  item_id: string;
  status: "confirmed" | "rejected";
  code: string | null;
  unit_compatible: boolean;
  decision: ReviewerDecision;
};

export type CodeAssignmentSet = {
  schema_version: string;
  plate_id: string;
  page_number: number;
  image_sha256: string;
  catalog_sha256: string;
  contract_sha256: string | null;
  assignments: CodeAssignment[];
  safety_notes: string[];
};

/** Item de takeoff como o servidor o lista nas pendências de código. */
export type PendingCodeItem = {
  item_id: string;
  label: string;
  raw_text: string;
  quantity: string | null;
  unit: string;
  note: string | null;
  status: TakeoffItemStatus;
};

export type CodesResponse = {
  assignments: CodeAssignmentSet | null;
  assignments_sha256: string | null;
  confirmed: number;
  rejected: number;
  pending_items: PendingCodeItem[];
};

export type CalcOperand = { name: string; value: string; unit: string | null };

export type CalcBlock = {
  label: string;
  recipe: string;
  operands: CalcOperand[];
  deductions: CalcOperand[];
  subtotal: string;
};

export type CalcSheet = {
  worksite_key: string;
  item_number: string;
  blocks: CalcBlock[];
  total_quantity: string;
};

export type BulletinLine = {
  item_number: string;
  code: string;
  description: string;
  unit: string;
  unit_price: string;
  quantity: string;
  total: string;
};

export type WorksiteBulletin = {
  worksite_key: string;
  worksite_name: string;
  address: string | null;
  contract_label: string | null;
  lines: BulletinLine[];
  total_amount: string;
};

export type Valuation = {
  schema_version: string;
  id: string;
  period_number: number;
  reference_label: string;
  bulletins: WorksiteBulletin[];
  calc_sheets: CalcSheet[];
  approval: unknown | null;
};

export type BulletinResponse = {
  valuation: Valuation;
  valuation_sha256: string;
  /** Total da medição; é propriedade do domínio, calculada no servidor. */
  total_amount: string;
};

/**
 * Item confirmado no takeoff cujo código foi rejeitado: candidato a aditivo já fechado
 * pelo servidor. Nenhum campo de preço existe aqui, por construção — o dossiê instrui o
 * pedido de aditivo (RE-RA), nunca precifica.
 */
export type AmendmentDossierItem = {
  item_id: string;
  label: string;
  raw_text: string;
  /** `Decimal` em texto, como toda quantidade nesta tela. */
  quantity: string;
  unit: string;
  item_note: string | null;
  /** A nota da rejeição de código (`decision.note`); nunca inventada pela tela. */
  justification: string;
  decision: ReviewerDecision;
};

export type AmendmentDossier = {
  schema_version: string;
  plate_id: string;
  page_number: number;
  image_sha256: string;
  source_pdf_sha256: string;
  catalog_sha256: string;
  contract_sha256: string | null;
  /** Vazio é desfecho normal: rodada sem nenhuma rejeição de código não tem aditivo. */
  items: AmendmentDossierItem[];
  safety_notes: string[];
};

export type DossierResponse = {
  dossier: AmendmentDossier;
  dossier_sha256: string;
  item_count: number;
};

/** Envelope de erro do servidor local: `{code, detail, details}` em problem+json. */
export class MedicaoApiError extends Error {
  readonly code: string;
  readonly detail: string;
  readonly details: Record<string, unknown>;
  readonly status: number;

  constructor(
    status: number,
    code: string,
    detail: string,
    details: Record<string, unknown>,
  ) {
    super(`${code}: ${detail}`);
    this.name = "MedicaoApiError";
    this.status = status;
    this.code = code;
    this.detail = detail;
    this.details = details;
  }
}

/** Código do 409 de guarda otimista: o "REVISION_CONFLICT" desta ferramenta local. */
export const STATE_MOVED_CODE = "LOCAL_STATE_MOVED";

/**
 * O artefato mudou no disco depois da leitura desta tela. Não é falha: é o sinal de
 * recarregar antes de decidir de novo — outro processo (o CLI, outra aba) mexeu na rodada.
 */
export function isStateMoved(error: unknown): boolean {
  return error instanceof MedicaoApiError && error.code === STATE_MOVED_CODE;
}

/**
 * Recusa de sessão sem envelope legível (401/403). É código LOCAL, como
 * `LOCAL_RESPONSE_UNREADABLE`: ele só entra quando o servidor não disse nada de
 * aproveitável — envelope do servidor continua vencendo, sempre.
 */
export const SESSION_REJECTED_CODE = "LOCAL_SESSION_REJECTED";

/**
 * Traduz uma resposta não-ok no erro de domínio que ela carrega.
 *
 * Corpo ilegível não vira mensagem inventada: sobra o status e um código local
 * (`LOCAL_RESPONSE_UNREADABLE`, ou `LOCAL_SESSION_REJECTED` em 401/403) que a tela sabe
 * exibir. Sem isso, um 401 do modo hospedado apareceria como "respondeu fora do formato
 * esperado", que manda o revisor procurar o defeito no lugar errado.
 */
export async function readProblem(response: Response): Promise<MedicaoApiError> {
  const payload = (await response.json().catch(() => null)) as {
    code?: unknown;
    detail?: unknown;
    details?: unknown;
  } | null;
  const code = typeof payload?.code === "string" ? payload.code : null;
  const detail = typeof payload?.detail === "string" ? payload.detail : null;
  const details =
    payload?.details && typeof payload.details === "object"
      ? (payload.details as Record<string, unknown>)
      : {};
  if (code === null) {
    if (response.status === 401 || response.status === 403) {
      return new MedicaoApiError(
        response.status,
        SESSION_REJECTED_CODE,
        detail ?? `o servidor respondeu ${response.status} sem envelope de erro`,
        details,
      );
    }
    return new MedicaoApiError(
      response.status,
      "LOCAL_RESPONSE_UNREADABLE",
      detail ?? `o servidor local respondeu ${response.status} sem envelope de erro`,
      details,
    );
  }
  return new MedicaoApiError(response.status, code, detail ?? "", details);
}

/**
 * `true` quando o erro é o cancelamento de um `AbortController` — nunca falha de rede.
 * A busca incremental cancela a consulta anterior a cada tecla; sem esta distinção, cada
 * cancelamento apareceria na tela como `LOCAL_SERVER_UNREACHABLE`.
 */
export function isAbortError(error: unknown): boolean {
  return error instanceof DOMException && error.name === "AbortError";
}

/**
 * Opções de uma chamada deste módulo. `headers` é um objeto simples (e não `HeadersInit`)
 * de propósito: é o que todas as chamadas daqui usam, e é o que permite juntar o
 * `Authorization` ao que a chamada declarou sem perder nenhum dos dois.
 */
type RequestOptions = Omit<RequestInit, "headers"> & {
  headers?: Record<string, string>;
};

async function request<T>(path: string, init?: RequestOptions): Promise<T> {
  let response: Response;
  try {
    // O `Authorization` entra ANTES do que a chamada declarou, para que um header
    // explícito continue vencendo; nenhum outro header é tocado — o `uploadPlate` manda
    // `FormData` e um `Content-Type` escrito aqui quebraria o boundary do multipart.
    response = await fetch(`${apiBaseUrl}${path}`, {
      ...init,
      headers: { ...authHeaders(), ...(init?.headers ?? {}) },
    });
  } catch (cause) {
    if (cause instanceof DOMException && cause.name === "AbortError") {
      throw cause;
    }
    throw new MedicaoApiError(
      0,
      "LOCAL_SERVER_UNREACHABLE",
      "o servidor local não respondeu; confira se `croquito-valuation serve` está no ar",
      { base_url: apiBaseUrl, path },
    );
  }
  if (!response.ok) {
    throw await readProblem(response);
  }
  return (await response.json()) as T;
}

function postJson<T>(path: string, body: Record<string, unknown>): Promise<T> {
  return request<T>(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export type TakeoffDecisionDraft = {
  itemId: string;
  action: "confirm" | "reject";
  basePacketSha256: string;
  /** Quantidade escrita pelo revisor, em texto: `Decimal` não passa por `number`. */
  quantity?: string;
  unit?: string;
  note?: string;
  itemNote?: string;
};

/**
 * Corpo do `POST /takeoff/decisions`.
 *
 * Campo vazio é omitido em vez de ir como string vazia: `""` seria uma correção do dado
 * ("apague o rótulo"), não a ausência de correção. Identidade e horário não aparecem —
 * o servidor recusaria (`extra="forbid"`), e mandá-los seria pedir para carimbar decisão
 * em nome de outra pessoa.
 */
export function takeoffDecisionBody(
  draft: TakeoffDecisionDraft,
): Record<string, string> {
  const body: Record<string, string> = {
    item_id: draft.itemId,
    action: draft.action,
    base_packet_sha256: draft.basePacketSha256,
  };
  const optional: [string, string | undefined][] = [
    ["quantity", draft.quantity],
    ["unit", draft.unit],
    ["note", draft.note],
    ["item_note", draft.itemNote],
  ];
  for (const [key, value] of optional) {
    const cleaned = value?.trim();
    if (cleaned) {
      body[key] = cleaned;
    }
  }
  return body;
}

export type CodeDecisionDraft = {
  itemId: string;
  action: "confirm" | "reject";
  code?: string;
  note?: string;
  /**
   * Digest do conjunto de confirmações lido. É `null` enquanto o arquivo não existe: o
   * servidor recusa digest citado sem conjunto (`LOCAL_BASE_DIGEST_UNEXPECTED`) e recusa
   * conjunto existente sem digest (`LOCAL_BASE_DIGEST_REQUIRED`).
   */
  baseAssignmentsSha256: string | null;
};

export function codeDecisionBody(
  draft: CodeDecisionDraft,
): Record<string, string> {
  const body: Record<string, string> = {
    item_id: draft.itemId,
    action: draft.action,
  };
  const code = draft.code?.trim();
  if (code) {
    body.code = code;
  }
  const note = draft.note?.trim();
  if (note) {
    body.note = note;
  }
  if (draft.baseAssignmentsSha256) {
    body.base_assignments_sha256 = draft.baseAssignmentsSha256;
  }
  return body;
}

/**
 * Termo de busca para recuperar a descrição completa de um código já confirmado, via
 * `GET /catalog/search`. O servidor tokeniza o código (`lexical_tokens`, NFKD sem
 * acento) e descarta token com menos de dois caracteres, então o sufixo de variante
 * entre parênteses (`(A)`, `(B)`, `(/)`) já sai da busca sozinho na maioria dos casos —
 * esta função só existe para o caso em que ele não sair: remove o sufixo primeiro e,
 * se sobrar vazio (código malformado), cai nos dez primeiros caracteres, que é o
 * tamanho do código base SCO.
 */
export function codeSearchTerm(code: string): string {
  const trimmed = code.trim();
  const withoutSuffix = trimmed.replace(/\([^)]*\)\s*$/, "").trim();
  return withoutSuffix.length > 0 ? withoutSuffix : trimmed.slice(0, 10);
}

export type CalcBuildDraft = {
  worksiteKey: string;
  worksiteName: string;
  periodNumber: string;
  referenceLabel: string;
  address?: string;
  contractLabel?: string;
};

/** Corpo do `POST /calc/build`; `period_number` é o único inteiro do contrato. */
export function calcBuildBody(
  draft: CalcBuildDraft,
): Record<string, string | number> {
  const body: Record<string, string | number> = {
    worksite_key: draft.worksiteKey.trim(),
    worksite_name: draft.worksiteName.trim(),
    period_number: Number(draft.periodNumber.trim()),
    reference_label: draft.referenceLabel.trim(),
  };
  const address = draft.address?.trim();
  if (address) {
    body.address = address;
  }
  const contractLabel = draft.contractLabel?.trim();
  if (contractLabel) {
    body.contract_label = contractLabel;
  }
  return body;
}

export function getState(): Promise<RunState> {
  return request<RunState>("/state");
}

export function getTakeoff(): Promise<TakeoffResponse> {
  return request<TakeoffResponse>("/takeoff");
}

/**
 * Envia o PDF da prancha do projetista (`POST /plates`, multipart). O envio É o
 * consentimento do documento para a leitura automática por IA — a resposta chega assim
 * que a prancha está na rodada, **sem esperar** a chamada paga terminar; quem acompanha o
 * desfecho é `state.extracao` no `/state` seguinte. Sem `Content-Type` manual: o
 * navegador escreve o boundary do multipart sozinho, e um header errado aqui quebra o
 * parsing do servidor.
 */
export function uploadPlate(file: File): Promise<RunState> {
  const body = new FormData();
  body.append("file", file);
  return request<RunState>("/plates", { method: "POST", body });
}

/**
 * Re-dispara a extração de uma prancha já ingerida (`POST /plates/extract`), para falha
 * transitória do provider ou servidor subido sem teto de gasto não obrigarem a reenviar
 * o documento.
 */
export function extractPlate(): Promise<RunState> {
  return request<RunState>("/plates/extract", { method: "POST" });
}

export function postTakeoffDecision(
  draft: TakeoffDecisionDraft,
): Promise<TakeoffDecisionResponse> {
  return postJson<TakeoffDecisionResponse>(
    "/takeoff/decisions",
    takeoffDecisionBody(draft),
  );
}

/**
 * Shortlist do servidor. A primeira chamada **calcula e grava** o artefato (`computed`);
 * por isso a tela só a busca na etapa de códigos, que já exige revisão completa. Esta
 * rota nunca recalcula um artefato já gravado — para isso é `postSuggestionsRecompute`.
 */
export function getSuggestions(): Promise<SuggestionsResponse> {
  return request<SuggestionsResponse>("/suggestions");
}

/**
 * Corpo do `POST /suggestions/recompute`. A chave só entra quando há digest-base a
 * citar — omitida, e não vazia, porque o servidor recusa `base_suggestions_sha256`
 * citado sem shortlist prévia (`LOCAL_BASE_DIGEST_UNEXPECTED`).
 */
export function suggestionsRecomputeBody(
  baseSuggestionsSha256: string | null,
): Record<string, string> {
  const body: Record<string, string> = {};
  if (baseSuggestionsSha256) {
    body.base_suggestions_sha256 = baseSuggestionsSha256;
  }
  return body;
}

/**
 * Recompute explícito da shortlist (`POST /suggestions/recompute`): grava artefato no
 * servidor, então só acontece pelo gesto do usuário — nunca automático. `null` só é aceito
 * quando ainda não existe shortlist nesta rodada.
 */
export function postSuggestionsRecompute(
  baseSuggestionsSha256: string | null,
): Promise<SuggestionsResponse> {
  return postJson<SuggestionsResponse>(
    "/suggestions/recompute",
    suggestionsRecomputeBody(baseSuggestionsSha256),
  );
}

export function searchCatalog(
  query: string,
  limit = 20,
  options?: { arm?: "auto" | "lexical"; signal?: AbortSignal },
): Promise<CatalogSearchResponse> {
  const params = new URLSearchParams({ q: query, limit: String(limit) });
  if (options?.arm === "lexical") {
    params.set("arm", "lexical");
  }
  return request<CatalogSearchResponse>(`/catalog/search?${params.toString()}`, {
    signal: options?.signal,
  });
}

export function getCodes(): Promise<CodesResponse> {
  return request<CodesResponse>("/codes");
}

export function postCodeDecision(
  draft: CodeDecisionDraft,
): Promise<CodesResponse> {
  return postJson<CodesResponse>("/codes/decisions", codeDecisionBody(draft));
}

export function postCalcBuild(draft: CalcBuildDraft): Promise<BulletinResponse> {
  return postJson<BulletinResponse>("/calc/build", calcBuildBody(draft));
}

export function getBulletin(): Promise<BulletinResponse> {
  return request<BulletinResponse>("/bulletin");
}

/**
 * Monta o dossiê do aditivo (`POST /dossier/build`). Espelho de `POST /calc/build`
 * (`postCalcBuild`): a rota real que ele espelha não tem guarda de digest-base — ela
 * sempre reconstrói do estado ATUAL do takeoff e das confirmações de código já gravados
 * na rodada, sem corpo a enviar, como `extractPlate`.
 */
export function postDossierBuild(): Promise<DossierResponse> {
  return request<DossierResponse>("/dossier/build", { method: "POST" });
}

export function getDossier(): Promise<DossierResponse> {
  return request<DossierResponse>("/dossier");
}

/** Rotas de imagem sem parâmetro de caminho: a UI escolhe a etapa, nunca o arquivo. */
export const PLATE_IMAGE_PATH = "/images/plate";
export const OVERLAY_IMAGE_PATH = "/images/overlay";

export const plateImageUrl = `${apiBaseUrl}${PLATE_IMAGE_PATH}`;
export const overlayImageUrl = `${apiBaseUrl}${OVERLAY_IMAGE_PATH}`;

/**
 * Baixa uma imagem do servidor COM o `Authorization` da sessão e devolve um object URL.
 *
 * `<img src={url}>` não passa por este módulo: o navegador busca a imagem sozinho, sem
 * header nenhum, e no modo hospedado (ADR-0026) isso é um 401 — a prancha sumiria da tela
 * de quem está autenticado. Buscar por `fetch` e virar `blob:` é o que faz a imagem
 * atravessar a mesma porta que o resto das chamadas.
 *
 * Quem chama fica responsável por `URL.revokeObjectURL` quando trocar ou desmontar: object
 * URL vive até o fim do documento, e uma rodada de revisão abre a prancha muitas vezes.
 */
export async function fetchImageObjectUrl(path: string): Promise<string> {
  let response: Response;
  try {
    response = await fetch(`${apiBaseUrl}${path}`, { headers: authHeaders() });
  } catch (cause) {
    if (cause instanceof DOMException && cause.name === "AbortError") {
      throw cause;
    }
    throw new MedicaoApiError(
      0,
      "LOCAL_SERVER_UNREACHABLE",
      "o servidor local não respondeu; confira se `croquito-valuation serve` está no ar",
      { base_url: apiBaseUrl, path },
    );
  }
  if (!response.ok) {
    throw await readProblem(response);
  }
  return URL.createObjectURL(await response.blob());
}

/**
 * `src` da prancha antes de qualquer busca: a URL direta no caminho local, `null` no
 * hospedado.
 *
 * Sem sessão OIDC (o servidor local do ADR-0020, que não autentica) a imagem continua
 * vindo pela URL direta — nenhum fetch a mais, nenhum object URL a revogar, exatamente o
 * que a ferramenta local sempre fez. Com sessão, o `null` é o estado honesto: ainda não há
 * imagem, porque ela só existe depois da busca autenticada.
 */
export function plateImageSource(oidcAtivo: boolean): string | null {
  return oidcAtivo ? null : plateImageUrl;
}
