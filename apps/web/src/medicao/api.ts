/**
 * Cliente da medição de obra na API `/v1` autenticada (ADR-0028, F-003 T20).
 *
 * O transporte é o mesmo do croqui (`apiJson` em `apps/web/src/api.ts`): ele leva o
 * `Authorization` da sessão OIDC, refaz a chamada uma vez quando o token expirou e traduz
 * o envelope de erro aninhado (`{detail: {code, detail, details}}`) num `ApiError`. Este
 * módulo não abre `fetch` nenhum por conta própria — nem para imagem, que agora chega por
 * URL assinada dentro do corpo (D5) e vai direto no `src`.
 *
 * Quatro invariantes moram aqui:
 *
 * - **A rodada é recurso.** Toda função cita `round_id`; nada nesta tela conversa com uma
 *   rodada implícita.
 * - **Identidade e carimbo nunca viajam.** `reviewer_id`, `reviewer_role`, `decided_at` e
 *   `decision_id` são do servidor (`extra="forbid"` recusa o corpo que os traz). Os
 *   construtores de corpo puros que garantem isso vivem em `requests.ts`.
 * - **Mutação cita `base_version` e manda `Idempotency-Key`.** A guarda otimista é da
 *   rodada e vale para a cadeia inteira; versão movida devolve `409 REVISION_CONFLICT`.
 * - **`Decimal` viaja como texto.** Quantidade e dinheiro chegam em string e são exibidos
 *   como string formatada (`format.ts`); nenhum número da medição vira `number` aqui.
 *
 * Os tipos de DOMÍNIO são os gerados de `@croquito/contracts` — pacote de takeoff,
 * shortlist, confirmações de código, medição e dossiê. Escrito à mão aqui fica só o
 * ENVELOPE de cada rota (`round_id`, `version`, digests e contagens), que é da API e não
 * do domínio.
 */

import type {
  AmendmentDossier,
  CodeAssignmentSet,
  CodeSuggestionSet,
  TakeoffPacket,
  Valuation,
} from "@croquito/contracts";

import { apiJson, ApiError } from "../api";
import {
  codeClosureBody,
  codeDecisionBody,
  createRoundBody,
  takeoffDecisionBody,
  versionBody,
} from "./requests";

export { ApiError };

/** `registered` = a bbox passou pelo registro fino contra a prancha; `raw` = ainda não. */
export type AnchorStatus = "registered" | "raw";

/**
 * Item do pacote com a âncora que a rota de leitura junta a ele (`anchored_packet`).
 *
 * A junção é de leitura: o documento gravado não ganha campo nenhum e o digest continua
 * sendo o dos bytes guardados. Por isso `anchor` é envelope, não domínio — e a ausência
 * dele é tratada como `"raw"` por `itemAnchor`, nunca como confirmado.
 */
export type TakeoffItem = TakeoffPacket.TakeoffItem & { anchor?: AnchorStatus };

export type AnchoredTakeoffPacket = Omit<
  TakeoffPacket.CroquitoTakeoffPacket,
  "items"
> & { items: TakeoffItem[] };

/** Etapa mais avançada que a rodada alcançou; a extração tem estado próprio. */
export type RoundStage =
  | "created"
  | "plate"
  | "extraction"
  | "takeoff"
  | "code_assignments"
  | "bulletin"
  | "amendment_dossier";

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

/** Linha da listagem de rodadas do tenant. */
export type RoundSummary = {
  round_id: string;
  worksite_key: string;
  worksite_name: string;
  reference_label: string;
  period_number: number;
  version: number;
  status: string;
  stage: RoundStage;
  extraction_status: ExtractionStatus;
  created_at: string;
  updated_at: string;
  /** Se a medição foi aprovada e não caducou (F-040): o selo da tela. */
  approved?: boolean;
  /** Se esta rodada pode abrir a medição seguinte: aprovada E com consolidado gravado. */
  can_open_next?: boolean;
};

/** Página da listagem; `next_cursor` é opaco e só volta quando há mais o que ler. */
export type RoundPage = {
  items: RoundSummary[];
  next_cursor: string | null;
};

export type RoundCreated = {
  round_id: string;
  version: number;
  status: string;
  created_at: string;
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

export type RoundStateTakeoff = Partial<TakeoffCounts> &
  Partial<AnchorCounts> & {
    present: boolean;
    packet_sha256?: string | null;
    plate_id?: string;
    page_number?: number;
    review_status?: "review_required" | "complete";
  };

export type RoundStateCodes = {
  suggestions_present: boolean;
  suggestions_sha256: string | null;
  assignments_present: boolean;
  assignments_sha256: string | null;
  confirmed: number;
  rejected: number;
  /** Itens confirmados no takeoff ainda sem decisão de código; `null` sem pacote. */
  pending: number | null;
};

/** Etapa `extraction` do estado da rodada: o que a chamada paga fez ou está fazendo. */
export type RoundStateExtraction = {
  status: ExtractionStatus;
  extraction_id: string | null;
  /** Código estável do desfecho que não publicou nada; `labels.ts` o traduz. */
  failure_code: string | null;
  lineage_present: boolean;
  updated_at: string | null;
};

export type RoundStatePlate = {
  present: boolean;
  source_sha256: string | null;
  page_count: number | null;
};

/**
 * Aprovação nominal da medição (VAL-05), como o servidor a DERIVA na leitura.
 *
 * Dois campos precisam ser lidos JUNTOS, e é por isso que eles vêm no mesmo bloco.
 * `approved` diz que houve ato de aprovação (a decisão `confirm`); `stale` diz que o
 * conteúdo mudou depois dele. Na aprovação **caduca** os dois valem ao mesmo tempo — houve
 * assinatura, e ela não cobre mais o que está na tela —, então uma tela que lesse só
 * `approved` ofereceria uma exportação que a rota já vai recusar com
 * `APPROVAL_CONTENT_MISMATCH`.
 *
 * `stale` nunca é gravado: ele é a relação entre `approved_digest` (o conteúdo que foi
 * assinado) e `current_digest` (o que está gravado agora), calculada na leitura. Os dois
 * digests viajam para a tela poder mostrá-los lado a lado, como o desenho aprovado pede.
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
 * Etapa `bulletin` do estado da rodada. `workbook_present` é a planilha publicada — só
 * existe depois de a auditoria de round-trip aprovar o arquivo, e o digest é o dos BYTES
 * dela, não o da medição.
 */
export type RoundStateBulletin = {
  present: boolean;
  valuation_sha256: string | null;
  workbook_present: boolean;
  workbook_sha256: string | null;
  approval: ApprovalState;
};

/**
 * Reajuste declarado na abertura da rodada (F-039, ADR-0055), como o servidor o gravou.
 *
 * Os campos de cada mecanismo são exclusivos: `index_factor` traz índice e fator,
 * `catalog_version` traz a versão da tabela. `declared_by`/`declared_at` são do servidor.
 */
export type RoundPriceAdjustment = {
  kind: "index_factor" | "catalog_version";
  declared_by: string;
  declared_at: string;
  reference_period: string;
  note?: string | null;
  index_label?: string | null;
  /** Texto: fator é `Decimal` exato e não passa por `number`. */
  factor?: string | null;
  catalog_label?: string | null;
  catalog_sha256?: string | null;
};

/** Contratado e vigente por código — a conta que a memória mostra. */
export type RoundContractedPrice = {
  code: string;
  item_number: string;
  description: string;
  unit: string;
  contracted_unit_price: string;
  current_unit_price: string;
  adjusted: boolean;
};

/** O efeito de uma RE-RA sobre um código: delta com sinal, ou item novo materializado. */
export type RoundAmendmentLine = {
  code: string;
  /** Texto: delta é `Decimal` exato e não passa por `number`. */
  quantity_delta: string;
  is_new_item?: boolean;
  note?: string | null;
  description?: string | null;
  unit?: string | null;
  unit_price?: string | null;
};

/**
 * Uma RE-RA declarada, com a procedência que a torna conferível (F-040, ADR-0056).
 * `declared_by`/`declared_at` são do servidor.
 */
export type RoundAmendment = {
  label: string;
  declared_by?: string | null;
  declared_at?: string | null;
  reference_period?: string | null;
  note?: string | null;
  lines: RoundAmendmentLine[];
};

/** Contratado e vigente por código, em QUANTIDADE — a conta que a memória mostra (F-040). */
export type RoundContractedQuantity = {
  code: string;
  item_number: string;
  description: string;
  unit: string;
  contracted_quantity: string;
  current_quantity: string;
  current_balance_quantity: string;
  re_ratified: boolean;
};

/** O regime de conferência da rodada; sem origem assinada, saldo e período não são checados. */
export type RoundStateContracted = {
  origin: "none" | "signed_estimate";
  estimate_round_id: string | null;
  estimate_digest: string | null;
  code_count?: number | null;
  /**
   * Reajustes declarados. Lista VAZIA é ausência de reajuste — fato sobre a rodada, e não
   * campo que some: a tela precisa distinguir "não reajustou" de "não sei".
   *
   * Opcional porque rodada lida antes da F-039 responde sem o campo, e a tela usa `?? []`.
   */
  price_adjustments?: RoundPriceAdjustment[];
  prices?: RoundContractedPrice[];
  /**
   * RE-RA declaradas na abertura (F-040). Lista VAZIA é ausência de re-ratificação — fato
   * sobre a rodada, como o reajuste. Opcional porque rodada lida antes da F-040 responde sem
   * o campo, e a tela usa `?? []`.
   */
  amendments?: RoundAmendment[];
  quantities?: RoundContractedQuantity[];
};

export type RoundState = {
  round_id: string;
  version: number;
  status: string;
  reviewer_role: string;
  worksite_key: string;
  worksite_name: string;
  reference_label: string;
  period_number: number;
  address: string | null;
  contract_label: string | null;
  revision_id: string | null;
  revision_version: number | null;
  catalog: {
    source_sha256: string;
    summary: {
      source_label?: string;
      reference_month?: string;
      source_sha256?: string;
      entries?: number;
    };
  };
  /**
   * Contra o que esta rodada confere (F-036, ADR-0048 decisão 9).
   *
   * `origin: "none"` é o estado de sempre e vem DECLARADO, não deduzido da ausência de um
   * campo: quem lê a rodada precisa saber que ali não se confere saldo, e não descobrir isso
   * por omissão. As duas rodadas não podem parecer iguais.
   */
  contracted: RoundStateContracted;
  artifacts: Record<string, string>;
  plate: RoundStatePlate;
  extraction: RoundStateExtraction;
  takeoff: RoundStateTakeoff;
  codes: RoundStateCodes;
  bulletin: RoundStateBulletin;
  dossier: { present: boolean; dossier_sha256: string | null };
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

/**
 * Resposta da decisão: a rodada já em versão nova, com o pacote regravado, mais a idade
 * do overlay. Ele fica vencido até o worker redesenhá-lo, e isso não é erro.
 */
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
  /** Derivado do `suggester_version` do próprio conjunto, nunca do estado do processo. */
  matching: "lexical" | "hybrid";
  /** Motivo declarado do braço semântico; vazio quando ele não teve nada a dizer. */
  semantic_notes: string[];
};

export type CatalogSearchResult = {
  code: string;
  unit: string;
  unit_price: string;
  /** Descrição COMPLETA do catálogo; é ela que diz se o código inclui execução. */
  description: string;
  origin: string;
  lexical_score: number;
  semantic_score: number | null;
};

export type CatalogSearchResponse = {
  round_id: string;
  version: number;
  query: string;
  terms: string[];
  limit: number;
  total_matches: number;
  semantic_matches: number;
  results: CatalogSearchResult[];
  matching: "lexical" | "hybrid";
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

export type BulletinResponse = {
  round_id: string;
  version: number;
  valuation: Valuation.CroquitoValuation;
  valuation_sha256: string;
  /** Total da medição; é propriedade do domínio, recomputada no servidor. */
  total_amount: string;
  /** Aprovação nominal e sua caducidade; ler `approved` e `stale` juntos. */
  approval: ApprovalState;
  workbook_present: boolean;
  /** Digest dos BYTES do `.xlsx` publicado; `null` enquanto não houver planilha. */
  workbook_sha256: string | null;
  /**
   * URL assinada de curta duração da planilha, montada na LEITURA e ausente na resposta
   * das mutações: ela é credencial e não pertence a nenhum artefato durável (o registro de
   * idempotência guarda a resposta do `POST`). Vai direto no `href` e nunca em log.
   */
  workbook_url?: string | null;
};

export type DossierResponse = {
  round_id: string;
  version: number;
  dossier: AmendmentDossier.CroquitoAmendmentDossier;
  dossier_sha256: string;
  item_count: number;
};

type PresignedUpload = {
  upload_id: string;
  object_key: string;
  url: string;
  headers: Record<string, string>;
  expires_at: string;
};

/**
 * Estado da assinatura de um orçamento que pode originar uma medição (F-036).
 *
 * Três estados por extenso, e não um booleano, porque cada um leva a um ato diferente:
 * `signed` abre a medição, `stale` pede assinar a versão atual, `unsigned` pede assinar.
 */
export type OriginSignature = "signed" | "stale" | "unsigned";

/** Um orçamento oferecido como origem, como `GET /v1/valuation-origins` o devolve. */
export type ValuationOrigin = {
  round_id: string;
  worksite_name: string;
  reference_label: string;
  signature: OriginSignature;
  approved_by: string | null;
  approved_at: string | null;
  /** Digest do conteúdo ASSINADO; a tela mostra abreviado, o servidor guarda inteiro. */
  estimate_digest: string | null;
  code_count: number;
  total_amount: string;
};

/**
 * O rascunho da rodada nova, nas duas origens (F-036, ADR-0048).
 *
 * `catalogUploadId` e `estimateRoundId` são exclusivos, e a obra só existe na primeira: na
 * origem assinada ela vem do conteúdo aprovado, e o servidor **recusa** declará-la — aceitar
 * abriria a porta para medir uma praça diferente da que foi orçada.
 */
/**
 * A declaração do reajuste na abertura (F-039). Só existe no caminho do orçamento assinado:
 * sem contratado não há preço contratual a reajustar, e o servidor recusa.
 *
 * `factor` é TEXTO pelo mesmo motivo da quantidade do takeoff: `Decimal` exato não passa por
 * `number`.
 */
export type PriceAdjustmentDraft = {
  kind: "index_factor" | "catalog_version";
  referencePeriod: string;
  indexLabel?: string;
  factor?: string;
  catalogUploadId?: string;
  note?: string;
};

/** Uma linha da RE-RA na tela: código, delta em texto e, se item novo, o marcador. */
export type AmendmentLineDraft = {
  code: string;
  /** Texto: delta é `Decimal` exato e não passa por `number`. */
  quantityDelta: string;
  isNewItem?: boolean;
  note?: string;
};

/**
 * A declaração da RE-RA na abertura (F-040). Só existe no caminho contratado (orçamento
 * assinado ou medição seguinte): sem contratado não há quantidade a re-ratificar. O item novo
 * NÃO informa preço — o servidor o materializa do catálogo contratual (ADR-0056, decisão 7).
 */
export type AmendmentDraft = {
  label: string;
  referencePeriod: string;
  note?: string;
  lines: AmendmentLineDraft[];
};

export type CreateRoundDraft = {
  worksiteKey: string;
  worksiteName: string;
  catalogUploadId?: string;
  estimateRoundId?: string;
  /** A medição seguinte (F-040): abre a rodada `n+1` a partir da rodada anterior aprovada. */
  previousRoundId?: string;
  referenceLabel: string;
  periodNumber: string;
  address?: string;
  contractLabel?: string;
  priceAdjustment?: PriceAdjustmentDraft;
  amendment?: AmendmentDraft;
};

export type TakeoffDecisionDraft = {
  itemId: string;
  action: "confirm" | "reject";
  /** Quantidade escrita pelo revisor, em texto: `Decimal` não passa por `number`. */
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
  return `/v1/valuation-rounds/${encodeURIComponent(roundId)}${suffix}`;
}

function toHex(buffer: ArrayBuffer): string {
  return Array.from(new Uint8Array(buffer), (value) =>
    value.toString(16).padStart(2, "0"),
  ).join("");
}

/**
 * Sobe um arquivo pelo presign e devolve o `upload_id` a citar depois.
 *
 * O byte nunca passa pela API: ela assina, o navegador faz o `PUT` direto no object store
 * e a rota seguinte recebe só o identificador. O digest é calculado aqui e conferido lá —
 * upload incompleto é recusado em vez de virar rodada com catálogo pela metade.
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

/** Catálogo de preços da rodada nova (JSON do `PriceCatalog`), pelo presign. */
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

export function listRounds(
  accessToken: string,
  options?: { limit?: number; cursor?: string | null },
): Promise<RoundPage> {
  const params = new URLSearchParams();
  if (options?.limit !== undefined) {
    params.set("limit", String(options.limit));
  }
  if (options?.cursor) {
    params.set("cursor", options.cursor);
  }
  const query = params.toString();
  return apiJson<RoundPage>(
    `/v1/valuation-rounds${query ? `?${query}` : ""}`,
    accessToken,
  );
}

/**
 * Abre a rodada com o catálogo já enviado. O catálogo é instalado na criação e é imutável
 * nela: trocar de catálogo é abrir outra rodada.
 */
export function createRound(
  accessToken: string,
  draft: CreateRoundDraft,
): Promise<RoundCreated> {
  return post<RoundCreated>(
    "/v1/valuation-rounds",
    accessToken,
    createRoundBody(draft),
  );
}

/**
 * Orçamentos que podem originar uma medição.
 *
 * Mora sob a jornada da MEDIÇÃO (`/v1/valuation-origins`), e não sob a do orçamento: um
 * tenant com o orçamento indisponível e a medição liberada continua abrindo medição.
 */
export function listValuationOrigins(
  accessToken: string,
): Promise<{ items: ValuationOrigin[] }> {
  return apiJson<{ items: ValuationOrigin[] }>(
    "/v1/valuation-origins",
    accessToken,
  );
}

export function getRoundState(
  accessToken: string,
  roundId: string,
): Promise<RoundState> {
  return apiJson<RoundState>(roundPath(roundId), accessToken);
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
 * depende da autorização contratual do tenant e do ambiente ter provider configurado, e
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
 * Shortlist da rodada. A primeira leitura **calcula e grava** o artefato (`computed`), sem
 * avançar a versão da rodada — a shortlist é derivada, e um `GET` não é ato humano. Por
 * isso a tela só a busca por gesto explícito na etapa de códigos.
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
 * Recompute explícito da shortlist: descarta a anterior, então é ato humano, cita
 * `base_version` e avança a rodada. Shortlist com refino pago é recusada
 * (`409 SUGGESTIONS_ALREADY_REFINED`) em vez de perder o lineage da chamada paga.
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
 * Busca no catálogo instalado, sempre pelo braço LEXICAL — que é o padrão da rota e o
 * único braço que a rodada de `/v1` tem: o híbrido depende de índice de embeddings que
 * nenhuma rota publica, e pedi-lo devolveria `503` a cada consulta. O motivo viaja na
 * própria resposta (`semantic_notes`) e a tela o exibe: a busca não degrada em silêncio.
 */
export function searchCatalog(
  accessToken: string,
  roundId: string,
  query: string,
  limit = 20,
  options?: { signal?: AbortSignal },
): Promise<CatalogSearchResponse> {
  const params = new URLSearchParams({
    q: query,
    limit: String(limit),
    arm: "lexical",
  });
  return apiJson<CatalogSearchResponse>(
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
 * Constrói boletim e memória de cálculo. O corpo é só a guarda de concorrência: a
 * identidade da obra (`worksite_key`, `worksite_name`, `period_number`,
 * `reference_label`, `address`, `contract_label`) é atributo da RODADA e foi declarada na
 * criação — quem a quiser mudar abre rodada nova.
 */
export function postCalcBuild(
  accessToken: string,
  roundId: string,
  baseVersion: number,
): Promise<BulletinResponse> {
  return post<BulletinResponse>(
    roundPath(roundId, "/calc"),
    accessToken,
    versionBody(baseVersion),
  );
}

export function getBulletin(
  accessToken: string,
  roundId: string,
): Promise<BulletinResponse> {
  return apiJson<BulletinResponse>(roundPath(roundId, "/bulletin"), accessToken);
}

/**
 * Aprovação nominal da medição da cabeça (VAL-05).
 *
 * O corpo é SÓ a guarda de concorrência. Quem aprova é o subject do JWT e o instante é o
 * relógio do servidor: não existe campo de nome do aprovador nesta jornada, e o servidor
 * recusa (`422`) qualquer corpo que traga `reviewer_id`, `reviewer_role`, `decided_at` ou
 * `decision_id`. A tela MOSTRA a identidade da sessão; ela nunca a digita nem a envia.
 *
 * Aprovar de novo é o caminho normal da aprovação caduca, não um erro: cada chamada é uma
 * revisão nova da cadeia append-only, e o histórico guarda as duas assinaturas.
 */
export function postApprove(
  accessToken: string,
  roundId: string,
  baseVersion: number,
): Promise<BulletinResponse> {
  return post<BulletinResponse>(
    roundPath(roundId, "/approve"),
    accessToken,
    versionBody(baseVersion),
  );
}

/**
 * Publica o `.xlsx` do boletim depois dos dois portões do servidor.
 *
 * Não há nada a escolher aqui — nem formato, nem layout, nem "exportar assim mesmo": a
 * medição é a da cabeça, o layout é o da prefeitura e a aprovação válida é precondição.
 * Sem ela a rota recusa com `VALUATION_EXPORT_BLOCKED`; auditoria de round-trip reprovada
 * é `VALUATION_WORKBOOK_AUDIT_FAILED` e **não publica nada**.
 *
 * A resposta não traz `workbook_url`: a URL assinada só sai na leitura (`getBulletin`).
 */
export function postBulletinExport(
  accessToken: string,
  roundId: string,
  baseVersion: number,
): Promise<BulletinResponse> {
  return post<BulletinResponse>(
    roundPath(roundId, "/bulletin/export"),
    accessToken,
    versionBody(baseVersion),
  );
}

/** Dossiê do aditivo: espelho de `postCalcBuild`, dos mesmos dois artefatos-base. */
export function postDossierBuild(
  accessToken: string,
  roundId: string,
  baseVersion: number,
): Promise<DossierResponse> {
  return post<DossierResponse>(
    roundPath(roundId, "/amendment-dossier"),
    accessToken,
    versionBody(baseVersion),
  );
}

export function getDossier(
  accessToken: string,
  roundId: string,
): Promise<DossierResponse> {
  return apiJson<DossierResponse>(
    roundPath(roundId, "/amendment-dossier"),
    accessToken,
  );
}
