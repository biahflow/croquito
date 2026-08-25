export type JobSummary = {
  job_id: string;
  status: string;
  stage: string;
};

export type ProjectSummary = {
  project_id: string;
  name: string;
  default_unit: "m" | "mm" | "rad" | "deg" | "m2";
  status: string;
  expires_at: string;
  latest_job: JobSummary | null;
};

export type Job = JobSummary & {
  project_id: string;
  expires_at: string;
  page_count: number | null;
  failure_code: string | null;
  created_at: string;
  updated_at: string;
};

export type EvidenceBox = {
  left: number;
  top: number;
  right: number;
  bottom: number;
};

/**
 * Decisão humana registrada na leitura. `rectifies_decision_id` presente significa que
 * esta decisão sucede outra, declaradamente: a anterior continua na revisão em que foi
 * tomada e nunca é apagada.
 */
export type ReadingDecision = {
  decision_id: string;
  action: "confirm" | "reject";
  reviewer_id: string;
  decided_at: string;
  note?: string | null;
  rectifies_decision_id?: string | null;
  // Quem decidiu (ADR-0041): `system` é a auto-associação por confiança calibrada, e só
  // confirma — corrigir uma decisão dela é o mesmo ato humano de retificação. Campo
  // ADITIVO: decisão gravada antes dele volta sem o campo e é lida como `human`, que é
  // o default do servidor.
  actor?: "human" | "system";
  // Por qual regra a máquina decidiu (ADR-0044): `cota` exigiu as duas confianças acima
  // do corte, `anotacao` dispensou a de leitura porque a cota não manda na geometria de
  // planta. Também ADITIVO: decisão de sistema gravada antes do campo é do tier `cota`,
  // o único que existia — o servidor a devolve já normalizada assim. Nunca vem em
  // decisão humana.
  auto_tier?: "cota" | "anotacao" | null;
};

export type ReviewReading = {
  id: string;
  raw_text: string;
  kind: string;
  status: "proposed" | "ambiguous" | "confirmed" | "rejected";
  value_si?: string | null;
  unit?: string;
  written_decimals?: number;
  target_hint?: string;
  // Sinal do pipeline: o modelo leu a linha como recado da folha (anotação), não como
  // cota de elemento. É observação, nunca decisão — quem declara continua sendo o
  // revisor. Opcional porque pacote persistido antes do campo responde sem ele.
  annotation_suggested?: boolean;
  // Corroboração determinística por OCR, registrada no nascimento da leitura: true = o
  // OCR leu o mesmo texto na mesma região; false = o OCR rodou e não encontrou; null/
  // ausente = braço indisponível ou pacote persistido antes do campo. Nunca rebaixa
  // status; é aviso de segunda testemunha, não decisão.
  ocr_corroborated?: boolean | null;
  evidence?: {
    coordinate_space: string;
    bbox: EvidenceBox;
  };
  decision?: ReadingDecision | null;
};

type PixelPoint = { x: number; y: number };

export type VisionProposal = {
  id: string;
  kind: "line" | "circle" | "contour";
  precision: "unresolved";
  export: false;
  // Semântica observada, presente só quando a proposta veio de um modelo: o caminho
  // determinístico não sabe o que a linha representa. `algorithm` e `quality_score`
  // acompanham toda proposta; ficam opcionais porque nenhuma tela depende deles.
  label?: string | null;
  layer_hint?: string | null;
  quality_score?: number;
  algorithm?: string;
  geometry:
    | { type: "line"; start: PixelPoint; end: PixelPoint }
    | { type: "circle"; center: PixelPoint; radius: number }
    // Contorno aberto existe: muro e limite de lote raramente fecham, e o worker
    // envia `closed: false` em vez de fechá-los à força.
    | { type: "polyline"; points: PixelPoint[]; closed: boolean };
};

export type ProposalCalibration = {
  calibration_id: string;
  scene_revision_id: string;
  scene_version: number;
  anchors: { proposal_id: string; entity_id: string; reversed: boolean }[];
  scale_m_per_px: number;
  rotation_radians: number;
  translation_m: [number, number];
  rmse_m: number;
  mode?: "similarity" | "affine";
  scale_x_m_per_px?: number | null;
  scale_y_m_per_px?: number | null;
  anisotropy?: number | null;
};

export type ProposalDecision = {
  proposal_id: string;
  action: "accept" | "reject";
  entity_id?: string;
  calibration_id?: string;
};

/**
 * Um termo da cadeia: a leitura, o valor em metros e o texto cru da folha.
 *
 * Os decimais viajam como STRING (o servidor serializa `Decimal`), e é assim que a tela
 * os exibe: converter para `number` para reescrever perderia a precisão escrita da cota,
 * que é justamente o que a conferência aritmética está julgando.
 */
export type ChainTerm = {
  reading_id: string;
  value_m: string;
  raw_text: string;
};

/** Uma soma de trechos comparada com um total, ambos lidos da folha. */
export type DimensionChain = {
  total: ChainTerm;
  parts: ChainTerm[];
  residual_m: string;
  tolerance_m: string;
};

/**
 * Uma cadeia declarada por uma pessoa, reconferida contra o pacote de hoje.
 *
 * O que fica gravado é a declaração; `chain`, `status` e `issue` são recomputados pelo
 * servidor a cada leitura. Daí `stale`: a cota participante pode ter sido retificada ou
 * rejeitada depois, e nesse caso a cadeia não some — ela avisa que perdeu o pé, sem
 * `chain`, e pede um ato humano (retratar ou declarar de novo).
 */
export type DeclaredChain = {
  chain_id: string;
  declared_by: string;
  declared_at: string;
  chain?: DimensionChain | null;
  status: "closes" | "mismatch" | "stale";
  issue?: { code: string; severity: string; message: string } | null;
};

/**
 * "Li certo?" por leitura — observação do pipeline, nunca decisão nem veto de exportação.
 *
 * A tela só exibe o número ao lado da leitura que o sistema decidiu sozinho; ela não
 * compara com corte nenhum, não pré-marca nada e não deriva estado a partir dele.
 */
export type ReadingConfidence = {
  reading_id: string;
  reading_confidence: number;
};

/** A associação que um corte hipotético TERIA escolhido para uma leitura. */
export type ShadowChoice = {
  reading_id: string;
  proposal_id: string;
  reading_confidence: number;
  association_confidence: number;
};

/**
 * Um ponto da grade de cortes e o que ele teria decidido — registro de calibração, não
 * decisão. A tela não escolhe ponto da grade nem sugere corte: quem escolhe o corte é
 * uma pessoa, a partir do relatório de calibração (F-029).
 */
export type ShadowDecision = {
  reading_threshold: number;
  association_threshold: number;
  auto_choices: ShadowChoice[];
};

export type Review = {
  job_id: string;
  review_id: string;
  version: number;
  packet: {
    readings: ReviewReading[];
    region_candidates?: {
      id: string;
      kind: string;
      label: string;
      evidence: string;
    }[];
    safety_notes?: string[];
  };
  associations: {
    candidates: {
      reading_id: string;
      proposal_id: string;
      proposal_kind: string;
      relation: string;
      // Sinais de confiança do ranking (F-029). Opcionais porque pacote associado antes
      // deles responde sem eles; a tela nunca ordena, filtra ou decide por eles.
      association_confidence?: number;
      orientation_alignment?: number | null;
    }[];
  };
  proposals: {
    image_width_px: number;
    image_height_px: number;
    proposals: VisionProposal[];
  } | null;
  selected_associations: Record<string, string>;
  calibration: ProposalCalibration | null;
  proposal_decisions: ProposalDecision[];
  issues: { code: string; severity: string; message: string; status?: string }[];
  blockers: string[];
  // O critério de escopo viaja como par: `code` é a chave da declaração na aprovação,
  // `text` é a frase do caso que a tela mostra no lugar do código cru.
  required_criteria: { code: string; text: string }[];
  // Conferência aritmética das cotas confirmadas: sugestão calculada na hora e
  // declaração humana persistida. Nenhuma das duas entra em `blockers` — divergência de
  // cadeia é aviso para o revisor, nunca veto de exportação. Opcionais porque a resposta
  // idempotente gravada ANTES destes campos existirem é revalidada no replay e volta sem
  // eles (mesmo motivo do `default_factory` no servidor).
  suggested_chains?: DimensionChain[];
  declared_chains?: DeclaredChain[];
  // Confiança e calibração (F-029), todos observacionais e todos opcionais: revisão
  // gravada antes deles — ou por caminho que não os preenche — responde com listas
  // vazias e taxas nulas, e a tela cai no `?? []` como faz com as cadeias. Ausência é
  // ausência de registro, nunca zero medido.
  reading_confidences?: ReadingConfidence[];
  confidence_shadow?: ShadowDecision[];
  auto_association_rate?: number | null;
  review_rate?: number | null;
  // Testemunhas de campo (F-030): cada uma confronta o valor da cota com uma medida de
  // campo (trena do app ou valor lido em foto e confirmado), com a diferença já calculada
  // pelo servidor. Observacional — nunca entra em `blockers`, nunca promove precisão, nunca
  // classifica a diferença. Opcional pelo mesmo motivo das cadeias: revisão gravada antes
  // do campo responde sem ele, e a tela lê com `?? []`.
  field_witnesses?: FieldWitness[];
  scene: {
    id: string;
    version: number;
    approved: boolean;
    entities: {
      id: string;
      kind: string;
      precision: string;
      // A cena chega inteira; a tela lê apenas os extremos da linha, para descrever a
      // aresta em metros. As demais geometrias entram por `type` e nada mais.
      geometry: {
        type: string;
        start?: { x: number; y: number };
        end?: { x: number; y: number };
      };
      provenance?: { source_type: string; source_ids?: string[] } | null;
    }[];
    issues?: {
      code: string;
      severity: string;
      message: string;
      status?: string;
    }[];
  } | null;
  preview_urls: { source_image_url?: string; review_overlay_url?: string };
};

export type SceneApprovalRequest = {
  revision_id: string;
  accepted_approximations: string[];
  // Dois atos distintos e disjuntos: a cena cobre o critério (`covered`, issue resolvida)
  // ou o critério segue pendente e é assinado assim mesmo (`acknowledged`, issue aceita).
  covered_criteria: string[];
  acknowledged_criteria: string[];
  source_evidence_checked: true;
  geometry_checked: true;
  limitations_acknowledged: true;
  statement: string;
};

export type ApprovedScene = {
  id: string;
  version: number;
  approved: boolean;
};

export type ExportArtifact = {
  export_id: string;
  job_id: string;
  scene_revision_id: string;
  format: "dxf";
  status: "QUEUED" | "RUNNING" | "COMPLETED" | "FAILED";
  audit_status: string | null;
  dxf_sha256: string | null;
  failure_code: string | null;
  audit_errors: string[];
  package_url: string | null;
};

/** Detalhe do croqui resolvido fora da planta: `solve` mantém escala própria, `sketch` não tem escala. */
export type TraceDetailGroup = {
  detail_id: string;
  title: string;
  proposal_ids: string[];
  mode: "solve" | "sketch";
};

/** Par declarado distinto com o eixo da separação; `axis` ausente separa nos dois. */
export type KeepApartPair = {
  first: string;
  second: string;
  axis?: "x" | "y" | null;
};

/** Um elemento, um par de elementos (vão entre dois) ou um vão declarado no mesmo elemento. */
export type TraceAssociationTarget =
  | string
  | string[]
  | {
      proposal_id: string;
      spans_px: [[number, number], [number, number]][];
    };

/**
 * Aceite em lote do traçado. `reviewer_id`, `reviewer_role`, `decided_at` e
 * `acceptance_id` são derivados do JWT e do servidor: enviá-los é recusado com 422.
 * `base_scene_version` é omitido quando o job ainda não tem cena métrica.
 */
export type TraceSolveRequest = {
  base_review_version: number;
  base_scene_version?: number;
  proposal_ids: string[];
  hatch_proposal_ids?: string[];
  /**
   * `["vp_a", "vp_b"]` separa nos dois eixos; a forma objeto declara o eixo do
   * problema (o dente do muro separa em `x` e mantém o encontro vertical amarrado).
   */
  keep_apart_pairs?: ([string, string] | KeepApartPair)[];
  unlabelled_proposal_ids?: string[];
  freeform_proposal_ids?: string[];
  detail_groups?: TraceDetailGroup[];
  associations?: Record<string, TraceAssociationTarget>;
  note_associations?: Record<string, string>;
  derived_dimensions?: {
    proposal_id: string;
    near_x_px: number;
    near_y_px: number;
    text?: string;
  }[];
  dimension_texts?: Record<string, string>;
  note?: string;
  title?: string;
  feature_id?: string;
};

export type TraceResidualSummary = {
  count: number;
  failed_count: number;
  worst_code: string | null;
  worst_absolute_error_m: number | null;
  worst_tolerance_m: number | null;
};

/**
 * Diagnóstico do traçado (F-025), espelho aditivo do contrato: por que uma leitura
 * confirmada não virou vão, quem disputa o mesmo vão com quem e onde cada cota aplicada
 * ancorou na prancha. `cause` é código estável do domínio (mesmo formato de `Issue.code`)
 * — a frase em língua de obra é montada na tela, nunca no servidor.
 */
export type TraceUnappliedReading = {
  reading_id: string;
  cause: string;
  target_proposal_ids: string[];
};

export type TraceContestedSpan = {
  axis: "x" | "y";
  reading_ids: string[];
  /** Na mesma ordem de `reading_ids`. */
  values_m: number[];
  proposal_ids: string[];
};

export type TraceAppliedSpan = {
  reading_id: string;
  axis: "x" | "y";
  value_m: number;
  /** Coordenada ao longo do eixo no frame CAD da prancha, com `start_m <= end_m`. */
  start_m: number;
  end_m: number;
  proposal_id: string;
  second_proposal_id?: string | null;
  gap?: boolean;
};

export type TraceSolveResponse = {
  trace_solve_id: string;
  job_id: string;
  status: "QUEUED" | "RUNNING" | "COMPLETED" | "FAILED";
  acceptance_id: string;
  base_review_version: number;
  base_scene_version: number | null;
  solve_status: "solved_unapproved" | "review_required" | "conflict" | null;
  blockers: string[];
  unapplied_reading_ids: string[];
  // Aditivos: `unapplied_reading_ids` continua sendo o contrato antigo, na mesma ordem.
  // Opcionais porque registro persistido antes da mudança responde sem eles — e a tela
  // precisa se comportar como antes diante de um job antigo.
  unapplied_readings?: TraceUnappliedReading[];
  contested_spans?: TraceContestedSpan[];
  applied_spans?: TraceAppliedSpan[];
  residual_summary: TraceResidualSummary | null;
  exact_entity_count: number | null;
  approximate_entity_count: number | null;
  note_count: number | null;
  scale_m_per_px: number | null;
  detail_group_scales: Record<string, number>;
  result_scene_revision_id: string | null;
  result_scene_version: number | null;
  result_review_version: number | null;
  failure_code: string | null;
};

export type ReviewDecision = {
  reading_id: string;
  action: "confirm" | "correct" | "reject";
  justification: string;
  association_proposal_id?: string;
  /** Declaração de anotação da folha: confirma sem associar a elemento. */
  annotation?: boolean;
  raw_text?: string;
  value_si?: string;
  unit?: "m" | "mm";
  kind?: string;
  written_decimals?: number;
};

/**
 * Correção declarada de uma decisão já registrada. Não existe ação `correct` aqui: o
 * desfecho é confirmar ou rejeitar, e a associação é sempre redeclarada — a tela
 * pré-preenche a vigente, mas quem a envia é o revisor.
 */
export type ReviewRectification = {
  reading_id: string;
  action: "confirm" | "reject";
  rectifies_decision_id: string;
  justification: string;
  association_proposal_id?: string;
  annotation?: boolean;
  raw_text?: string;
  value_si?: string;
  unit?: "m" | "mm";
  kind?: string;
  written_decimals?: number;
};

/**
 * Rascunhos tipados da conversa da revisão. Cada um espelha, campo a campo, o contrato
 * servido pela API (`ReviewChatOutput` em
 * `services/worker/src/croquito_worker/providers.py`): é o corpo de um endpoint que
 * já existe, preenchido pelo agente e assinado pelo profissional (ADR-0023).
 */
export type ChatReadingDecisionDraft = {
  act: "reading_decision";
  reading_id: string;
  /** O rascunho não corrige medida: só confirma ou rejeita o que a folha já diz. */
  action: "confirm" | "reject";
  association_proposal_id?: string | null;
  annotation: boolean;
  /** Sugestão de texto; quem escreve a justificativa gravada é o revisor. */
  justification_draft: string;
};

/** Um elemento, ou o par de um vão entre dois (a tupla do contrato viaja como lista). */
export type ChatTraceAssociationDraft = {
  act: "trace_association";
  reading_id: string;
  target: string | [string, string];
};

export type ChatKeepApartDraft = {
  act: "keep_apart";
  first: string;
  second: string;
  axis?: "x" | "y" | null;
};

export type ChatNoteAssociationDraft = {
  act: "note_association";
  reading_id: string;
  /** `carimbo`, `legenda:vp_…` ou `vp_…` com sufixo opcional `#v`/`#h`. */
  target: string;
};

export type ChatPendingNoteDraft = {
  act: "pending_note";
  text: string;
};

export type ChatActDraft =
  | ChatReadingDecisionDraft
  | ChatTraceAssociationDraft
  | ChatKeepApartDraft
  | ChatNoteAssociationDraft
  | ChatPendingNoteDraft;

/**
 * Resposta observacional de um turno. `answer_kind="uncertain"` sempre traz
 * `open_question`: "ainda não sei" é saída de contrato, não falha.
 */
export type ReviewChatOutput = {
  task: "review-chat";
  answer_kind: "answer" | "uncertain";
  answer_text: string;
  evidence_notes: string[];
  open_question: string | null;
  proposed_acts: ChatActDraft[];
};

/** O que o profissional apontou ao perguntar; nada é inferido por proximidade. */
export type ChatAnchors = {
  reading_ids: string[];
  proposal_ids: string[];
};

export type ChatTurn = {
  chat_turn_id: string;
  chat_session_id: string;
  job_id: string;
  sequence: number;
  status: "QUEUED" | "RUNNING" | "COMPLETED" | "FAILED";
  question: string;
  anchors: ChatAnchors;
  answer: ReviewChatOutput | null;
  failure_code: string | null;
  created_at: string;
  updated_at: string;
};

export type ChatSession = {
  chat_session_id: string;
  job_id: string;
  status: "OPEN" | "CLOSED";
  base_review_revision_id: string;
  base_review_version: number;
  created_at: string;
  turns: ChatTurn[];
};

/** Lista magra: quem abre a tela escolhe uma conversa, não relê todas. */
export type ChatSessionSummary = {
  chat_session_id: string;
  status: "OPEN" | "CLOSED";
  created_at: string;
  turn_count: number;
};

type PresignedUpload = {
  upload_id: string;
  url: string;
  headers: Record<string, string>;
};

import { readLastRenewFailure, renewAccessToken } from "./auth";

const apiBaseUrl = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

/**
 * Recusa da API com o envelope aninhado (`{detail: {code, detail, details}}`) preservado.
 *
 * `message` continua sendo a frase que este módulo sempre montou — quem só a exibe não
 * muda de comportamento. O que a classe acrescenta é o que a jornada de medição precisa
 * ler sem reabrir a resposta: o `code` estável (para escolher a frase de obra), o status e
 * o `details`, onde viaja o código de invariante de domínio dentro de
 * `DOMAIN_VALIDATION_FAILED` (ADR-0028 D4). Resposta sem envelope legível não vira código
 * inventado: `code` fica `null` e sobra o status.
 */
export class ApiError extends Error {
  readonly status: number;
  readonly code: string | null;
  readonly detail: string | null;
  readonly details: Record<string, unknown>;

  constructor(
    message: string,
    status: number,
    code: string | null,
    detail: string | null,
    details: Record<string, unknown>,
  ) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.detail = detail;
    this.details = details;
  }
}

export async function apiJson<T>(
  path: string,
  accessToken: string,
  init?: RequestInit,
): Promise<T> {
  const send = (token: string) =>
    fetch(`${apiBaseUrl}${path}`, {
      ...init,
      headers: {
        Authorization: `Bearer ${token}`,
        ...(init?.headers ?? {}),
      },
    });
  let response = await send(accessToken);
  if (response.status === 401) {
    const primeiro = (await response
      .clone()
      .json()
      .catch(() => null)) as { detail?: { code?: string } } | null;
    // Conta sem tenant não se conserta com token novo: renovar aqui só dispara a
    // cascata do iframe de renovação para chegar ao MESMO 401 (incidente de
    // 2026-08-19). O erro segue direto para a tela, com a explicação certa.
    if (primeiro?.detail?.code !== "TOKEN_WITHOUT_TENANT") {
      // O mesmo Idempotency-Key volta na retentativa: replay, não segunda escrita.
      const renewed = await renewAccessToken();
      if (renewed) {
        response = await send(renewed);
      }
    }
  }
  if (!response.ok) {
    const payload = (await response.json().catch(() => null)) as {
      detail?: {
        code?: string;
        detail?: string;
        details?: Record<string, unknown>;
      };
    } | null;
    const code = payload?.detail?.code ?? null;
    const detail = payload?.detail?.detail ?? null;
    const details = payload?.detail?.details;
    const renewFailure =
      response.status === 401 ? readLastRenewFailure() : null;
    const cause = renewFailure ? ` A renovação falhou: ${renewFailure}.` : "";
    // Copy aprovada da revisão de 2026-08-19 (gate de texto): quem está autenticado e
    // sem organização precisa de orientação, não de um código cru — e precisa saber que
    // entrar de novo não muda o resultado.
    const message =
      code === "TOKEN_WITHOUT_TENANT"
        ? "Sua conta autenticou, mas ainda não está vinculada a uma organização. " +
          "Peça a quem administra o seu tenant para vincular sua conta — entrar de " +
          "novo não muda o resultado."
        : code
          ? `${code}: ${detail ?? "Falha na API."}${cause}`
          : `Falha na API (${response.status}).${cause}`;
    throw new ApiError(
      message,
      response.status,
      code,
      detail,
      details && typeof details === "object" ? details : {},
    );
  }
  return response.json() as Promise<T>;
}

export async function listProjects(
  accessToken: string,
): Promise<ProjectSummary[]> {
  return apiJson<ProjectSummary[]>("/v1/projects", accessToken);
}

export async function getJob(accessToken: string, jobId: string): Promise<Job> {
  return apiJson<Job>(`/v1/jobs/${jobId}`, accessToken);
}

export async function getReview(
  accessToken: string,
  jobId: string,
): Promise<Review> {
  return apiJson<Review>(`/v1/jobs/${jobId}/review`, accessToken);
}

/**
 * Teto de decisões por envio, igual ao `max_length` do contrato do servidor
 * (`SubmitReviewDecisionsRequest`, em `services/api/src/croquito_api/main.py`). Repetido
 * aqui para o excesso morrer antes da rede: o revisor lê uma frase em vez de um 422.
 */
export const REVIEW_DECISION_BATCH_MAX = 50;

/** `null` quando o lote cabe no contrato; senão a frase que a tela mostra ao revisor. */
export function reviewDecisionBatchIssue(count: number): string | null {
  if (count < 1) {
    return "Nenhuma leitura selecionada: um envio de decisões precisa de pelo menos uma.";
  }
  if (count > REVIEW_DECISION_BATCH_MAX) {
    return `O envio vai até ${REVIEW_DECISION_BATCH_MAX} decisões de uma vez, e ${count} passam desse limite. Divida em lotes menores.`;
  }
  return null;
}

/**
 * Campo opcional de touch time do envio (F-031 T4).
 *
 * Ausente quer dizer "não medido", e é por isso que a chave SOME em vez de sair `null`:
 * o cronômetro pode nunca ter começado. Medida implausível também não viaja — o servidor
 * a descartaria de qualquer forma, e nenhuma mutação é recusada por causa dela.
 */
function touchTimeField(interactionMs?: number | null): {
  interaction_ms?: number;
} {
  if (
    typeof interactionMs !== "number" ||
    !Number.isFinite(interactionMs) ||
    interactionMs < 0
  ) {
    return {};
  }
  return { interaction_ms: Math.round(interactionMs) };
}

/**
 * Um envio, N decisões atômicas: a rota sempre recebeu uma lista, e cada item vira um
 * `HumanDecision` próprio no servidor. Uma `Idempotency-Key` e um `base_version` por
 * envio — o lote inteiro entra ou nada entra.
 */
export async function submitReviewDecisions(
  accessToken: string,
  jobId: string,
  baseVersion: number,
  decisions: ReviewDecision[],
  interactionMs?: number | null,
): Promise<Review> {
  const issue = reviewDecisionBatchIssue(decisions.length);
  if (issue) {
    throw new Error(issue);
  }
  return apiJson<Review>(`/v1/jobs/${jobId}/review/decisions`, accessToken, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "Idempotency-Key": crypto.randomUUID(),
    },
    body: JSON.stringify({
      base_version: baseVersion,
      decisions,
      ...touchTimeField(interactionMs),
    }),
  });
}

export async function submitReviewRectification(
  accessToken: string,
  jobId: string,
  baseVersion: number,
  rectification: ReviewRectification,
  interactionMs?: number | null,
): Promise<Review> {
  return apiJson<Review>(`/v1/jobs/${jobId}/review/rectifications`, accessToken, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "Idempotency-Key": crypto.randomUUID(),
    },
    body: JSON.stringify({
      base_version: baseVersion,
      rectifications: [rectification],
      ...touchTimeField(interactionMs),
    }),
  });
}

/**
 * Declarar ou retratar uma cadeia. O corpo é disjunto de propósito: `declare` leva total
 * e parcelas, `retract` leva o identificador da cadeia — o cliente não monta um comando
 * com os dois, e quem valida o resto continua sendo o servidor (`CHAIN_INVALID`,
 * `CHAIN_NOT_FOUND`).
 */
export type ReviewChainCommand =
  | { action: "declare"; total_id: string; part_ids: string[] }
  | { action: "retract"; chain_id: string };

/**
 * Uma `Idempotency-Key` e um `base_version` por gesto, como as demais mutações da
 * revisão: declarar e retratar são atos humanos e cada um cria uma revisão de leitura
 * nova no servidor. A resposta é o `Review` já reconferido.
 */
export async function postReviewChains(
  accessToken: string,
  jobId: string,
  baseVersion: number,
  command: ReviewChainCommand,
): Promise<Review> {
  return apiJson<Review>(`/v1/jobs/${jobId}/review/chains`, accessToken, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "Idempotency-Key": crypto.randomUUID(),
    },
    body: JSON.stringify({ base_version: baseVersion, ...command }),
  });
}

export async function createProposalCalibration(
  accessToken: string,
  jobId: string,
  baseReviewVersion: number,
  baseSceneVersion: number,
  anchors: { proposal_id: string; entity_id?: string; reversed?: boolean }[],
): Promise<Review> {
  return apiJson<Review>(`/v1/jobs/${jobId}/review/calibration`, accessToken, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "Idempotency-Key": crypto.randomUUID(),
    },
    body: JSON.stringify({
      base_review_version: baseReviewVersion,
      base_scene_version: baseSceneVersion,
      anchors,
    }),
  });
}

export async function annotateDimension(
  accessToken: string,
  jobId: string,
  baseReviewVersion: number,
  baseSceneVersion: number,
  readingId: string,
  entityId: string,
  justification: string,
): Promise<Review> {
  return apiJson<Review>(`/v1/jobs/${jobId}/review/dimensions`, accessToken, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "Idempotency-Key": crypto.randomUUID(),
    },
    body: JSON.stringify({
      base_review_version: baseReviewVersion,
      base_scene_version: baseSceneVersion,
      reading_id: readingId,
      entity_id: entityId,
      justification,
    }),
  });
}

export async function submitProposalBatch(
  accessToken: string,
  jobId: string,
  baseReviewVersion: number,
  baseSceneVersion: number,
  proposalIds: string[],
  action: "accept" | "reject",
  justification: string,
  calibrationId?: string,
): Promise<Review> {
  return apiJson<Review>(`/v1/jobs/${jobId}/review/proposals/batch`, accessToken, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "Idempotency-Key": crypto.randomUUID(),
    },
    body: JSON.stringify({
      base_review_version: baseReviewVersion,
      base_scene_version: baseSceneVersion,
      proposal_ids: proposalIds,
      action,
      justification,
      calibration_id: calibrationId,
    }),
  });
}

export async function submitProposalDecision(
  accessToken: string,
  jobId: string,
  baseReviewVersion: number,
  baseSceneVersion: number,
  proposalId: string,
  action: "accept" | "reject",
  justification: string,
  calibrationId?: string,
): Promise<Review> {
  return apiJson<Review>(`/v1/jobs/${jobId}/review/proposals`, accessToken, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "Idempotency-Key": crypto.randomUUID(),
    },
    body: JSON.stringify({
      base_review_version: baseReviewVersion,
      base_scene_version: baseSceneVersion,
      proposal_id: proposalId,
      action,
      justification,
      calibration_id: calibrationId,
    }),
  });
}

/**
 * O traçado é trabalho pesado e roda no worker: a API valida, persiste a intenção e
 * devolve 202. O resultado vem por polling em `getTraceSolve`, nunca nesta resposta.
 */
export async function createTraceSolve(
  accessToken: string,
  jobId: string,
  request: TraceSolveRequest,
): Promise<TraceSolveResponse> {
  return apiJson<TraceSolveResponse>(
    `/v1/jobs/${jobId}/trace-solves`,
    accessToken,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Idempotency-Key": crypto.randomUUID(),
      },
      body: JSON.stringify(request),
    },
  );
}

export async function getTraceSolve(
  accessToken: string,
  jobId: string,
  traceSolveId: string,
): Promise<TraceSolveResponse> {
  return apiJson<TraceSolveResponse>(
    `/v1/jobs/${jobId}/trace-solves/${traceSolveId}`,
    accessToken,
  );
}

/**
 * Abre a conversa da revisão. O corpo é `{}` de propósito: a revisão-base é fixada pelo
 * servidor na revisão corrente e não acompanha o job depois disso.
 */
export async function createChatSession(
  accessToken: string,
  jobId: string,
): Promise<ChatSession> {
  return apiJson<ChatSession>(`/v1/jobs/${jobId}/chat-sessions`, accessToken, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "Idempotency-Key": crypto.randomUUID(),
    },
    body: JSON.stringify({}),
  });
}

/**
 * Publica a pergunta e devolve `202`: quem chama o modelo é o worker, e a resposta
 * chega por polling em `getChatSession`, nunca nesta resposta.
 */
export async function createChatTurn(
  accessToken: string,
  jobId: string,
  sessionId: string,
  question: { question: string; anchors: ChatAnchors },
): Promise<ChatTurn> {
  return apiJson<ChatTurn>(
    `/v1/jobs/${jobId}/chat-sessions/${sessionId}/turns`,
    accessToken,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Idempotency-Key": crypto.randomUUID(),
      },
      body: JSON.stringify(question),
    },
  );
}

export async function getChatSession(
  accessToken: string,
  jobId: string,
  sessionId: string,
): Promise<ChatSession> {
  return apiJson<ChatSession>(
    `/v1/jobs/${jobId}/chat-sessions/${sessionId}`,
    accessToken,
  );
}

export async function listChatSessions(
  accessToken: string,
  jobId: string,
): Promise<ChatSessionSummary[]> {
  return apiJson<ChatSessionSummary[]>(
    `/v1/jobs/${jobId}/chat-sessions`,
    accessToken,
  );
}

export async function approveScene(
  accessToken: string,
  jobId: string,
  approval: SceneApprovalRequest,
): Promise<ApprovedScene> {
  return apiJson<ApprovedScene>(`/v1/jobs/${jobId}/approve`, accessToken, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "Idempotency-Key": crypto.randomUUID(),
    },
    body: JSON.stringify(approval),
  });
}

export async function requestExport(
  accessToken: string,
  jobId: string,
  revisionId: string,
): Promise<ExportArtifact> {
  return apiJson<ExportArtifact>(`/v1/jobs/${jobId}/exports`, accessToken, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "Idempotency-Key": crypto.randomUUID(),
    },
    body: JSON.stringify({ revision_id: revisionId, format: "dxf" }),
  });
}

export async function getExport(
  accessToken: string,
  jobId: string,
  exportId: string,
): Promise<ExportArtifact> {
  return apiJson<ExportArtifact>(
    `/v1/jobs/${jobId}/exports/${exportId}`,
    accessToken,
  );
}

function toHex(buffer: ArrayBuffer): string {
  return Array.from(new Uint8Array(buffer), (value) =>
    value.toString(16).padStart(2, "0"),
  ).join("");
}

// --- Evidência de campo (F-030) ---
//
// Tipos escritos à mão porque não há contrato REST gerado (só os schemas de domínio de
// `@croquito/contracts`), espelhando os modelos de `services/api/src/croquito_api/main.py`
// (`FieldEvidenceResponse` e vizinhos). `photo.url` é assinada por resposta e nunca deve
// ser persistida em estado durável — cada `getFieldEvidence` traz uma URL fresca.

export type FieldEvidenceAnchor = {
  kind: "point" | "element" | "note";
  ref_id: string;
};

export type FieldEvidenceMeasurement = {
  source_id: string;
  survey_id: string;
  value_mm: number;
  kind: string;
  instrument: string;
  from_point_id: string | null;
  to_point_id: string | null;
  second_from_point_id: string | null;
  second_to_point_id: string | null;
  element_id: string | null;
  created_at: string;
};

export type FieldEvidenceConfirmedValue = {
  confirmation_id: string;
  source_reading_id: string;
  value_mm: number;
  kind: string;
  raw_text: string;
  confirmed_by: string;
  confirmed_at: string;
};

export type FieldEvidencePhoto = {
  evidence_id: string;
  origin: "survey" | "standalone";
  survey_id: string | null;
  sha256: string;
  mime_type: string;
  anchors: FieldEvidenceAnchor[];
  anchor_text: string | null;
  captured_at: string;
  /** Assinada por resposta: exibir e "abrir original", nunca guardar. */
  url: string;
  analysis: Record<string, unknown> | null;
  classification: Record<string, unknown> | null;
  reading_status: string;
  classification_status: string;
  confirmed_values: FieldEvidenceConfirmedValue[];
};

export type LinkedSurveyEvidence = {
  survey_id: string;
  name: string;
  linked_by: string;
  linked_at: string;
  measurements: FieldEvidenceMeasurement[];
};

export type FieldEvidence = {
  job_id: string;
  version: number;
  surveys: LinkedSurveyEvidence[];
  photos: FieldEvidencePhoto[];
};

export type CompletedSurveySummary = {
  survey_id: string;
  name: string;
  order_ref: string | null;
  version: number;
  photo_count: number;
  confirmed_measurement_count: number;
  completed_at: string;
};

export type CompletedSurveyPage = {
  items: CompletedSurveySummary[];
  next_cursor: string | null;
};

export type FieldPhotoAnalysisState = {
  analysis_id: string;
  task: "reading" | "classification";
  status: string;
  version: number;
};

// A fonte de uma testemunha, no molde do servidor (`FieldWitnessSource`): a medida do app
// carrega `survey_id`; o valor lido em foto nunca. O cliente escolhe a fonte, nunca o valor
// — o servidor lê o valor da fonte e calcula a diferença.
export type FieldWitnessSource = {
  type: "survey_measurement" | "photo_reading";
  source_id: string;
  survey_id?: string;
};

// Uma testemunha já associada a uma leitura. Os três valores em milímetros viajam como
// STRING (o servidor serializa `Decimal`): reescrevê-los como `number` perderia a precisão
// escrita, e a diferença é justamente o que o revisor está lendo. `difference_mm` é só um
// número — não há `status`, `agrees` nem tom de alerta, por decisão de projeto (ADR-0049).
export type FieldWitness = {
  witness_id: string;
  reading_id: string;
  source_type: "survey_measurement" | "photo_reading";
  source_id: string;
  survey_id: string | null;
  reading_value_mm: string;
  source_value_mm: string;
  difference_mm: string;
  associated_by: string;
  associated_at: string;
};

// Associar e retratar são atos disjuntos: a união impede o cliente de mandar `witness_id`
// junto com `source`, espelhando o `model_validator` de `ReviewWitnessCommand` no servidor.
export type ReviewWitnessCommand =
  | { action: "associate"; reading_id: string; source: FieldWitnessSource }
  | { action: "retract"; witness_id: string };

// O primeiro ato do caminho legado: confirmar o valor lido por máquina numa foto. É
// append-only no servidor; associá-lo a uma cota é outro ato, na rota de testemunhas.
export type FieldPhotoValueDraft = {
  source_reading_id: string;
  value_mm: number;
  kind: "length" | "diagonal" | "width" | "radius" | "level" | "drop" | "height";
  raw_text: string;
};

export async function getFieldEvidence(
  accessToken: string,
  jobId: string,
): Promise<FieldEvidence> {
  return apiJson<FieldEvidence>(
    `/v1/jobs/${jobId}/field-evidence`,
    accessToken,
  );
}

export async function listCompletedSurveys(
  accessToken: string,
  cursor?: string | null,
): Promise<CompletedSurveyPage> {
  const query = cursor ? `?cursor=${encodeURIComponent(cursor)}` : "";
  return apiJson<CompletedSurveyPage>(`/v1/surveys${query}`, accessToken);
}

/**
 * Vincular ou desvincular um levantamento é ato humano: uma `Idempotency-Key` e o
 * `base_version` da evidência por gesto. Repetir um vínculo já existente é sucesso sem
 * avançar versão; versão movida entre carga e envio volta `409 REVISION_CONFLICT`.
 */
export async function linkSurveyToJob(
  accessToken: string,
  jobId: string,
  surveyId: string,
  baseVersion: number,
): Promise<FieldEvidence> {
  await apiJson(
    `/v1/jobs/${jobId}/field-evidence/surveys/${encodeURIComponent(surveyId)}`,
    accessToken,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Idempotency-Key": crypto.randomUUID(),
      },
      body: JSON.stringify({ base_version: baseVersion }),
    },
  );
  return getFieldEvidence(accessToken, jobId);
}

export async function unlinkSurveyFromJob(
  accessToken: string,
  jobId: string,
  surveyId: string,
  baseVersion: number,
): Promise<FieldEvidence> {
  await apiJson(
    `/v1/jobs/${jobId}/field-evidence/surveys/${encodeURIComponent(surveyId)}/unlink`,
    accessToken,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Idempotency-Key": crypto.randomUUID(),
      },
      body: JSON.stringify({ base_version: baseVersion }),
    },
  );
  return getFieldEvidence(accessToken, jobId);
}

/**
 * Foto avulsa: presign → PUT direto no storage → confirmar, o mesmo molde do upload de
 * projeto. A âncora é declarada pelo revisor (não inferida); MIME e tamanho seguem o
 * contrato do servidor para o excesso morrer antes da rede.
 */
export async function uploadStandaloneFieldPhoto(
  accessToken: string,
  jobId: string,
  baseVersion: number,
  file: File,
  anchorText: string,
): Promise<FieldEvidence> {
  const mime = file.type;
  if (mime !== "image/jpeg" && mime !== "image/png" && mime !== "image/webp") {
    throw new Error("A foto precisa ser JPEG, PNG ou WebP.");
  }
  if (file.size === 0 || file.size > 25_000_000) {
    throw new Error("A foto deve ter entre 1 byte e 25 MB.");
  }
  const trimmed = anchorText.trim();
  if (trimmed.length < 1 || trimmed.length > 500) {
    throw new Error("Declare uma âncora de 1 a 500 caracteres para a foto.");
  }
  const digest = toHex(
    await crypto.subtle.digest("SHA-256", await file.arrayBuffer()),
  );
  const presigned = await apiJson<PresignJobFieldPhotoResponse>(
    `/v1/jobs/${jobId}/field-evidence/photos/presign`,
    accessToken,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Idempotency-Key": crypto.randomUUID(),
      },
      body: JSON.stringify({
        base_version: baseVersion,
        sha256: digest,
        mime_type: mime,
        byte_size: file.size,
        anchor_text: trimmed,
      }),
    },
  );
  const upload = await fetch(presigned.url, {
    method: "PUT",
    headers: presigned.headers,
    body: file,
  });
  if (!upload.ok) {
    throw new Error("O upload direto da foto não foi concluído. Tente novamente.");
  }
  await apiJson(
    `/v1/jobs/${jobId}/field-evidence/photos/${presigned.photo_id}/confirm`,
    accessToken,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Idempotency-Key": crypto.randomUUID(),
      },
      body: JSON.stringify({ base_version: presigned.version }),
    },
  );
  return getFieldEvidence(accessToken, jobId);
}

type PresignJobFieldPhotoResponse = {
  photo_id: string;
  version: number;
  sha256: string;
  url: string;
  headers: Record<string, string>;
  expires_at: string;
};

/**
 * Pedido explícito de leitura textual de uma foto confirmada. Responde `202`: o worker
 * resolve fora do request, e o resultado chega no próximo `getFieldEvidence`.
 */
export async function requestFieldPhotoReading(
  accessToken: string,
  jobId: string,
  origin: "survey" | "standalone",
  evidenceId: string,
  baseVersion: number,
): Promise<FieldPhotoAnalysisState> {
  return apiJson<FieldPhotoAnalysisState>(
    `/v1/jobs/${jobId}/field-evidence/photos/${origin}/${encodeURIComponent(evidenceId)}/reading`,
    accessToken,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Idempotency-Key": crypto.randomUUID(),
      },
      body: JSON.stringify({ base_version: baseVersion }),
    },
  );
}

/**
 * Associar ou retratar uma testemunha de campo (F-030). Uma `Idempotency-Key` e o
 * `base_version` da revisão por gesto, como as demais mutações da revisão: cada ato cria
 * uma revisão de leitura nova e a resposta é o `Review` já reconferido. O cliente escolhe a
 * leitura e a fonte; o valor e a diferença são resolvidos pelo servidor.
 */
export async function mutateReviewWitnesses(
  accessToken: string,
  jobId: string,
  baseVersion: number,
  command: ReviewWitnessCommand,
): Promise<Review> {
  return apiJson<Review>(`/v1/jobs/${jobId}/review/witnesses`, accessToken, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "Idempotency-Key": crypto.randomUUID(),
    },
    body: JSON.stringify({ base_version: baseVersion, ...command }),
  });
}

/**
 * Ato 1 do caminho legado: confirmar o valor lido por máquina numa foto. POST append-only
 * seguido do re-GET da evidência, o mesmo molde de `linkSurveyToJob`. Não vira testemunha
 * aqui: associá-lo a uma cota é o segundo ato, na rota de testemunhas. A validação de forma
 * mata o excesso antes da rede, para o revisor ver uma frase e não um 422.
 */
export async function confirmFieldPhotoValue(
  accessToken: string,
  jobId: string,
  origin: "survey" | "standalone",
  evidenceId: string,
  baseVersion: number,
  draft: FieldPhotoValueDraft,
): Promise<FieldEvidence> {
  if (!Number.isInteger(draft.value_mm) || draft.value_mm < 0) {
    throw new Error("O valor confirmado precisa ser um número inteiro de milímetros.");
  }
  const rawText = draft.raw_text.trim();
  if (rawText.length < 1 || rawText.length > 200) {
    throw new Error("O texto lido deve ter de 1 a 200 caracteres.");
  }
  await apiJson(
    `/v1/jobs/${jobId}/field-evidence/photos/${origin}/${encodeURIComponent(evidenceId)}/values`,
    accessToken,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Idempotency-Key": crypto.randomUUID(),
      },
      body: JSON.stringify({
        base_version: baseVersion,
        source_reading_id: draft.source_reading_id,
        value_mm: draft.value_mm,
        kind: draft.kind,
        raw_text: rawText,
      }),
    },
  );
  return getFieldEvidence(accessToken, jobId);
}

export async function createProjectUpload(
  accessToken: string,
  file: File,
  projectName: string,
  defaultUnit: "m" | "mm",
): Promise<Job> {
  if (
    file.type !== "application/pdf" ||
    !file.name.toLowerCase().endsWith(".pdf")
  ) {
    throw new Error("Selecione um arquivo PDF.");
  }
  if (file.size === 0 || file.size > 100_000_000) {
    throw new Error("O PDF deve ter entre 1 byte e 100 MB.");
  }
  const digest = toHex(
    await crypto.subtle.digest("SHA-256", await file.arrayBuffer()),
  );
  const presigned = await apiJson<PresignedUpload>(
    "/v1/uploads/presign",
    accessToken,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Idempotency-Key": crypto.randomUUID(),
      },
      body: JSON.stringify({
        filename: file.name,
        content_type: "application/pdf",
        size_bytes: file.size,
        sha256: digest,
      }),
    },
  );
  const upload = await fetch(presigned.url, {
    method: "PUT",
    headers: presigned.headers,
    body: file,
  });
  if (!upload.ok) {
    throw new Error("O upload direto não foi concluído. Tente novamente.");
  }
  return apiJson<Job>("/v1/jobs", accessToken, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "Idempotency-Key": crypto.randomUUID(),
    },
    body: JSON.stringify({
      upload_id: presigned.upload_id,
      project_name: projectName,
      default_unit: defaultUnit,
    }),
  });
}
