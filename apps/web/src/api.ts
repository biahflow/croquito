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

async function apiJson<T>(
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
    // O mesmo Idempotency-Key volta na retentativa: replay, não segunda escrita.
    const renewed = await renewAccessToken();
    if (renewed) {
      response = await send(renewed);
    }
  }
  if (!response.ok) {
    const payload = (await response.json().catch(() => null)) as {
      detail?: { code?: string; detail?: string };
    } | null;
    const code = payload?.detail?.code;
    const renewFailure =
      response.status === 401 ? readLastRenewFailure() : null;
    const cause = renewFailure ? ` A renovação falhou: ${renewFailure}.` : "";
    throw new Error(
      code
        ? `${code}: ${payload?.detail?.detail ?? "Falha na API."}${cause}`
        : `Falha na API (${response.status}).${cause}`,
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

export async function submitReviewDecision(
  accessToken: string,
  jobId: string,
  baseVersion: number,
  decision: ReviewDecision,
): Promise<Review> {
  return apiJson<Review>(`/v1/jobs/${jobId}/review/decisions`, accessToken, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "Idempotency-Key": crypto.randomUUID(),
    },
    body: JSON.stringify({ base_version: baseVersion, decisions: [decision] }),
  });
}

export async function submitReviewRectification(
  accessToken: string,
  jobId: string,
  baseVersion: number,
  rectification: ReviewRectification,
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
    }),
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
