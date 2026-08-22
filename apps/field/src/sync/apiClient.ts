/**
 * ÚNICO módulo do workspace `apps/field` que fala com a rede (`apps/field/AGENTS.md`,
 * autorização dada pela T9). Traduz `/v1/surveys` (T8) em resultados tipados: nenhuma
 * exceção de rede escapa daqui, nenhum corpo bruto do servidor sobe para a UI e nada é
 * registrado em log — nem URL assinada, nem digest, nem conteúdo de mídia
 * (`AGENTS.md` da raiz, regras de dados e segurança).
 *
 * `fetch` é injetável para o teste exercer o cliente inteiro (cabeçalhos, `Idempotency-Key`,
 * leitura de `problem+json`) sem tocar rede de verdade.
 */

import {
  parseOperationsAck,
  parsePresignedMedia,
  parseServerConflict,
  parseServerSurveyState,
  type OperationsAck,
  type PresignedMedia,
  type ServerConflict,
  type ServerSurveyState,
  type SubmitOperationsBody,
} from "./protocol";

/**
 * Falha de uma chamada. `transient` diz se REPETIR faz sentido — é a única coisa que o
 * motor precisa perguntar para decidir entre backoff e parar (ver `backoff.ts`).
 */
export type SyncFailure =
  | { kind: "network"; transient: true; message: string }
  | { kind: "unauthorized"; transient: false }
  | { kind: "conflict"; transient: false; detail: string; conflict: ServerConflict }
  | {
      kind: "problem";
      transient: boolean;
      status: number;
      code: string;
      detail: string;
      details: Record<string, unknown> | null;
    }
  | { kind: "malformed"; transient: false; message: string };

export type SyncResult<T> = { ok: true; value: T } | { ok: false; failure: SyncFailure };

export interface SyncApi {
  /** Lote do outbox + pacote consolidado. `batchId` é o `Idempotency-Key`. */
  submitOperations(input: {
    token: string;
    surveyId: string;
    batchId: string;
    body: SubmitOperationsBody;
  }): Promise<SyncResult<OperationsAck>>;
  getSurveyState(input: {
    token: string;
    surveyId: string;
  }): Promise<SyncResult<ServerSurveyState | null>>;
  presignMedia(input: {
    token: string;
    surveyId: string;
    idempotencyKey: string;
    sha256: string;
    mimeType: string;
    byteSize: number;
  }): Promise<SyncResult<PresignedMedia>>;
  uploadMedia(input: {
    url: string;
    headers: Record<string, string>;
    blob: Blob;
  }): Promise<SyncResult<null>>;
  confirmMedia(input: {
    token: string;
    surveyId: string;
    sha256: string;
  }): Promise<SyncResult<ServerSurveyState>>;
  completeSurvey(input: {
    token: string;
    surveyId: string;
    idempotencyKey: string;
    baseVersion: number;
  }): Promise<SyncResult<ServerSurveyState>>;
}

export type FetchLike = (input: string, init: RequestInit) => Promise<Response>;

/** Status que valem retentativa: o servidor não recusou por regra, ele não conseguiu
 * responder agora (indisponibilidade, timeout de gateway, fila indisponível). */
function isTransientStatus(status: number): boolean {
  return status >= 500 || status === 408 || status === 429;
}

function problemBody(payload: unknown): { code: string; detail: string; details: Record<string, unknown> | null } {
  // `problem_handler` da API devolve `{type,title,status,code,request_id,detail}` onde
  // `detail` é o corpo estruturado da rota (`{code, detail, details}`). Lemos os dois
  // níveis sem supor qual deles chegou.
  const root = typeof payload === "object" && payload !== null ? (payload as Record<string, unknown>) : {};
  const nested =
    typeof root.detail === "object" && root.detail !== null
      ? (root.detail as Record<string, unknown>)
      : {};
  const code =
    typeof nested.code === "string"
      ? nested.code
      : typeof root.code === "string"
        ? root.code
        : "HTTP_ERROR";
  const detail =
    typeof nested.detail === "string"
      ? nested.detail
      : typeof root.detail === "string"
        ? root.detail
        : "A sincronização não foi aceita pelo servidor.";
  const details =
    typeof nested.details === "object" && nested.details !== null
      ? (nested.details as Record<string, unknown>)
      : null;
  return { code, detail, details };
}

async function readJson(response: Response): Promise<unknown> {
  try {
    return (await response.json()) as unknown;
  } catch {
    return null;
  }
}

/** Falha do próprio `fetch` (DNS, offline, TLS, timeout do navegador). A mensagem NUNCA
 * é o texto do erro do navegador: seria texto de origem desconhecida na tela do técnico. */
const NETWORK_FAILURE: SyncFailure = {
  kind: "network",
  transient: true,
  message: "Não foi possível falar com o servidor agora.",
};

export function createSyncApi(baseUrl: string, fetchImpl: FetchLike): SyncApi {
  const base = baseUrl.replace(/\/+$/, "");

  async function send(
    path: string,
    init: RequestInit,
  ): Promise<{ ok: true; response: Response } | { ok: false; failure: SyncFailure }> {
    try {
      return { ok: true, response: await fetchImpl(`${base}${path}`, init) };
    } catch {
      return { ok: false, failure: NETWORK_FAILURE };
    }
  }

  async function failureFor(response: Response): Promise<SyncFailure> {
    if (response.status === 401 || response.status === 403) {
      return { kind: "unauthorized", transient: false };
    }
    const payload = await readJson(response);
    const { code, detail, details } = problemBody(payload);
    if (response.status === 409 && code === "SURVEY_CONFLICT") {
      return { kind: "conflict", transient: false, detail, conflict: parseServerConflict(details) };
    }
    return {
      kind: "problem",
      transient: isTransientStatus(response.status),
      status: response.status,
      code,
      detail,
      details,
    };
  }

  function authHeaders(token: string): Record<string, string> {
    return { Authorization: `Bearer ${token}`, Accept: "application/json" };
  }

  async function postJson<T>(input: {
    path: string;
    token: string;
    idempotencyKey?: string;
    body?: unknown;
    parse: (value: unknown) => T | null;
  }): Promise<SyncResult<T>> {
    const headers: Record<string, string> = {
      ...authHeaders(input.token),
      "Content-Type": "application/json",
    };
    if (input.idempotencyKey !== undefined) {
      headers["Idempotency-Key"] = input.idempotencyKey;
    }
    const sent = await send(input.path, {
      method: "POST",
      headers,
      body: JSON.stringify(input.body ?? {}),
    });
    if (!sent.ok) {
      return { ok: false, failure: sent.failure };
    }
    if (!sent.response.ok) {
      return { ok: false, failure: await failureFor(sent.response) };
    }
    const parsed = input.parse(await readJson(sent.response));
    if (parsed === null) {
      return {
        ok: false,
        failure: {
          kind: "malformed",
          transient: false,
          message: "O servidor respondeu num formato que este app não reconhece.",
        },
      };
    }
    return { ok: true, value: parsed };
  }

  return {
    submitOperations: ({ token, surveyId, batchId, body }) =>
      postJson({
        path: `/v1/surveys/${encodeURIComponent(surveyId)}/operations`,
        token,
        idempotencyKey: batchId,
        body,
        parse: parseOperationsAck,
      }),

    async getSurveyState({ token, surveyId }) {
      const sent = await send(`/v1/surveys/${encodeURIComponent(surveyId)}`, {
        method: "GET",
        headers: authHeaders(token),
      });
      if (!sent.ok) {
        return { ok: false, failure: sent.failure };
      }
      if (sent.response.status === 404) {
        // Levantamento que ainda não existe no servidor não é erro: é o estado normal de
        // um levantamento que nunca sincronizou.
        return { ok: true, value: null };
      }
      if (!sent.response.ok) {
        return { ok: false, failure: await failureFor(sent.response) };
      }
      const parsed = parseServerSurveyState(await readJson(sent.response));
      return parsed === null
        ? {
            ok: false,
            failure: {
              kind: "malformed",
              transient: false,
              message: "O servidor respondeu num formato que este app não reconhece.",
            },
          }
        : { ok: true, value: parsed };
    },

    presignMedia: ({ token, surveyId, idempotencyKey, sha256, mimeType, byteSize }) =>
      postJson({
        path: `/v1/surveys/${encodeURIComponent(surveyId)}/media/presign`,
        token,
        idempotencyKey,
        body: { sha256, mime_type: mimeType, byte_size: byteSize },
        parse: parsePresignedMedia,
      }),

    async uploadMedia({ url, headers, blob }) {
      // PUT direto no storage assinado — a URL é ABSOLUTA e não passa por `base`: sem
      // `Authorization` (a assinatura JÁ é a autorização) e sem tocar o corpo, porque o
      // digest combinado no presign é do arquivo como ele está no aparelho.
      let response: Response;
      try {
        response = await fetchImpl(url, { method: "PUT", headers, body: blob });
      } catch {
        return { ok: false, failure: NETWORK_FAILURE };
      }
      if (!response.ok) {
        return {
          ok: false,
          failure: {
            kind: "problem",
            transient: isTransientStatus(response.status),
            status: response.status,
            code: "MEDIA_UPLOAD_FAILED",
            detail: "O envio do arquivo foi recusado pelo armazenamento.",
            details: null,
          },
        };
      }
      return { ok: true, value: null };
    },

    // `confirm` NÃO leva `Idempotency-Key`: o digest no caminho já identifica a mídia, e a
    // rota trata a repetição devolvendo o estado sem republicar processamento (T8).
    confirmMedia: ({ token, surveyId, sha256 }) =>
      postJson({
        path: `/v1/surveys/${encodeURIComponent(surveyId)}/media/${encodeURIComponent(sha256)}/confirm`,
        token,
        parse: parseServerSurveyState,
      }),

    completeSurvey: ({ token, surveyId, idempotencyKey, baseVersion }) =>
      postJson({
        path: `/v1/surveys/${encodeURIComponent(surveyId)}/complete`,
        token,
        idempotencyKey,
        body: { base_version: baseVersion },
        parse: parseServerSurveyState,
      }),
  };
}
