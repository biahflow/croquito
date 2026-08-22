/**
 * Motor de sincronização do levantamento (F-032, T9) — o transporte real do outbox.
 *
 * Regras que não são detalhe de implementação, e que os testes deste módulo protegem:
 *
 * 1. **Nada local é apagado.** Operação vira `pending` antes do envio e `acked` depois da
 *    resposta; conflito resolvido em favor do escritório marca as operações preteridas
 *    como `superseded`. Nenhum caminho remove operação nem mídia (ADR-0043 D2).
 * 2. **Ordem declarada** (prancha 6a): metadados primeiro, mídia depois. É a ordem que o
 *    servidor cobra — foto cujo digest o pacote ainda não referencia é recusada com
 *    `SURVEY_MEDIA_NOT_REFERENCED` —, e é a ordem que o painel mostra.
 * 3. **Lote idempotente**: o `Idempotency-Key` é o id do lote e é REUSADO na retentativa
 *    do mesmo lote; a repetição é o comportamento normal do outbox, não um erro.
 * 4. **Conflito é apresentado, nunca resolvido em silêncio** (prancha 6b): o servidor
 *    devolve o estado dele, o motor expõe os dois lados e só age depois da decisão
 *    explícita do técnico, que vira operação `conflict_resolution` com justificativa.
 * 5. **Expiração não é erro**: `AUTH_REAUTH_REQUIRED` para o ENVIO e deixa a coleta
 *    intocada (prancha 6c).
 *
 * O motor não fala com a rede diretamente: `SyncApi` (`apiClient.ts`) é o único ponto de
 * transporte, e é injetado — daí os testes exercerem a cadeia inteira com `fetch` falso.
 */

import type { AccessTokenResult } from "../auth";
import { surveyStatus, type Survey } from "../domain/types";
import { createSerialQueue, type SerialQueue } from "../outbox/serialQueue";
import type { SurveyOperation } from "../outbox/types";
import type { MediaRecord, SurveyRepository } from "../storage/SurveyRepository";
import type { SyncApi, SyncFailure, SyncResult } from "./apiClient";
import { MAX_ATTEMPTS, backoffDelayMs } from "./backoff";
import { MissingMediaError, toSurveyPacket, type MediaMeta, type SurveyPacketShape } from "./contract";
import {
  SURVEY_MEDIA_DIGEST_MISMATCH,
  SURVEY_MEDIA_NOT_REFERENCED,
  type ServerSurveyState,
} from "./protocol";
import {
  emptyCategories,
  initialSyncState,
  type SyncCategory,
  type SyncCategoryState,
  type SyncConflictState,
  type SyncState,
} from "./state";

/** Decisão do técnico na prancha 6b. */
export type ConflictDecision = "keep_local" | "accept_server";

/** Tipo da operação que registra a decisão de conflito — mesmo nome que o servidor espera. */
export const CONFLICT_RESOLUTION_OPERATION = "conflict_resolution";

/**
 * Justificativa padrão de cada decisão. O pacote aprovado (prancha 6b) não tem campo de
 * texto livre: a justificativa É a decisão declarada, escrita por extenso, e viaja no
 * payload da operação. O parâmetro `justification` de `resolveConflict` existe para uma
 * tela futura poder mandar o texto do técnico sem mudar o motor.
 */
export const CONFLICT_JUSTIFICATION: Record<ConflictDecision, string> = {
  keep_local:
    "O técnico manteve a versão levantada em campo; a versão do escritório foi recusada na tela de conflito.",
  accept_server:
    "O técnico aceitou a versão do escritório; as ações locais preteridas seguem gravadas no aparelho.",
};

export interface SyncEngineDeps {
  repository: SurveyRepository;
  /** `null` quando não há `VITE_CROQUITO_API_BASE_URL` — o motor opera em modo local. */
  api: SyncApi | null;
  deviceId: string;
  getFreshAccessToken: () => Promise<AccessTokenResult>;
  now?: () => Date;
  isOnline?: () => boolean;
  newBatchId?: () => string;
  newOperationId?: () => string;
  sleep?: (ms: number) => Promise<void>;
  random?: () => number;
  /** Uma sincronização por vez (mesma fila serial dos comandos de coleta). */
  queue?: SerialQueue;
  onState?: (state: SyncState) => void;
}

export interface SyncEngine {
  getState(): SyncState;
  /** Uma passada completa: metadados → mídia → conclusão. Nunca lança. */
  syncSurvey(surveyId: string): Promise<SyncState>;
  /** Aplica a decisão da prancha 6b e reenvia. Nunca lança. */
  resolveConflict(decision: ConflictDecision, justification?: string): Promise<SyncState>;
  /** Estado do painel a partir SÓ do que o aparelho sabe — sem tocar a rede. É o que a
   * abertura do painel usa: abrir a prancha 6 não pode disparar envio. */
  refreshLocal(surveyId: string): Promise<SyncState>;
}

interface MediaJob {
  category: SyncCategory;
  media: MediaRecord;
}

const CATEGORY_FAILURE_PREFIX: Record<SyncCategory, string> = {
  metadata: "Geometria e medidas",
  anchored_photo: "Fotos ancoradas",
  access_photo: "Foto do acesso",
  audio: "Áudios",
};

function defaultSleep(ms: number): Promise<void> {
  return new Promise((resolve) => {
    setTimeout(resolve, ms);
  });
}

/**
 * Mídia que o levantamento REFERENCIA, por categoria da prancha 6a e sem repetição de
 * digest (a mesma foto ancorada duas vezes sobe uma vez só).
 *
 * Mídia órfã — gravada no aparelho e não referenciada pelo survey, como a foto do acesso
 * capturada e abandonada antes de "Começar a coleta" (dívida registrada na revisão de T6)
 * — simplesmente não entra aqui: não é enviada e não é apagada. O servidor recusaria o
 * digest de qualquer forma (`SURVEY_MEDIA_NOT_REFERENCED`), e apagar dado local é
 * proibido nesta fatia.
 */
async function planMedia(
  repository: SurveyRepository,
  survey: Survey,
): Promise<{
  jobs: MediaJob[];
  missing: { category: SyncCategory; media_id: string }[];
  /** Índice para `toSurveyPacket`, com TODA referência resolvida — inclusive as que o
   * envio deduplica. Duas âncoras da mesma foto sobem uma vez, mas as duas continuam
   * precisando resolver o `media_ref` no pacote. */
  index: Map<string, MediaMeta>;
}> {
  const jobs: MediaJob[] = [];
  const missing: { category: SyncCategory; media_id: string }[] = [];
  const index = new Map<string, MediaMeta>();
  const seenDigests = new Set<string>();
  const references: { category: SyncCategory; media_id: string }[] = [
    ...survey.photo_anchors.map((anchor) => ({
      category: "anchored_photo" as SyncCategory,
      media_id: anchor.local_media_ref,
    })),
  ];
  if (survey.context?.access_media_ref !== undefined) {
    references.push({ category: "access_photo", media_id: survey.context.access_media_ref });
  }
  // Áudio das notas de voz (T12) por último: é a ordem da prancha 6a e a ordem em que o
  // painel lista. Mesma regra das fotos — a mídia sobe por identidade de conteúdo, e o
  // digest só é aceito pelo servidor depois que a nota que o referencia sincronizou.
  for (const note of survey.observations) {
    if (note.audio_media_ref !== undefined) {
      references.push({ category: "audio", media_id: note.audio_media_ref });
    }
  }
  for (const reference of references) {
    const media = await repository.getMedia(reference.media_id);
    if (media === undefined) {
      missing.push(reference);
      continue;
    }
    index.set(media.id, {
      sha256: media.sha256,
      mime_type: media.mime_type,
      byte_size: media.byte_size,
    });
    if (seenDigests.has(media.sha256)) {
      continue;
    }
    seenDigests.add(media.sha256);
    jobs.push({ category: reference.category, media });
  }
  return { jobs, missing, index };
}

/** Mensagem escrita de uma falha — nunca o corpo bruto do servidor, nunca a URL assinada. */
function failureMessage(failure: SyncFailure): string {
  switch (failure.kind) {
    case "network":
      return failure.message;
    case "unauthorized":
      return "O servidor recusou a identidade deste aparelho para sincronizar.";
    case "conflict":
      return failure.detail;
    case "malformed":
      return failure.message;
    case "problem":
      return failure.detail;
  }
}

function failureCode(failure: SyncFailure): string {
  switch (failure.kind) {
    case "network":
      return "SYNC_SEM_RESPOSTA";
    case "unauthorized":
      return "SYNC_NAO_AUTORIZADO";
    case "conflict":
      return "SURVEY_CONFLICT";
    case "malformed":
      return "SYNC_RESPOSTA_INESPERADA";
    case "problem":
      return failure.code;
  }
}

export function createSyncEngine(deps: SyncEngineDeps): SyncEngine {
  const {
    repository,
    api,
    deviceId,
    getFreshAccessToken,
    now = () => new Date(),
    isOnline = () => (typeof navigator === "undefined" ? true : navigator.onLine),
    newBatchId = () => crypto.randomUUID(),
    newOperationId = () => crypto.randomUUID(),
    sleep = defaultSleep,
    random = Math.random,
    queue = createSerialQueue(),
    onState,
  } = deps;

  let state: SyncState = initialSyncState(api === null ? "local_mode" : "idle");

  function publish(next: SyncState): SyncState {
    state = next;
    onState?.(state);
    return state;
  }

  function patch(changes: Partial<SyncState>): SyncState {
    return publish({ ...state, ...changes });
  }

  function patchCategory(category: SyncCategory, changes: Partial<SyncCategoryState>): SyncState {
    return patch({
      categories: state.categories.map((entry) =>
        entry.category === category ? { ...entry, ...changes } : entry,
      ),
    });
  }

  function categoryOf(category: SyncCategory): SyncCategoryState {
    return (
      state.categories.find((entry) => entry.category === category) ?? {
        category,
        total: 0,
        sent: 0,
        failed: 0,
        status: "waiting",
        failure_detail: null,
      }
    );
  }

  function noteCategoryFailure(category: SyncCategory, message: string): void {
    const current = categoryOf(category);
    patchCategory(category, {
      failed: current.failed + 1,
      status: "partial",
      failure_detail: `${CATEGORY_FAILURE_PREFIX[category]}: ${message}`,
    });
  }

  /**
   * Repete SÓ falha transitória (rede/5xx), com backoff. A mesma chamada é refeita com os
   * mesmos argumentos — inclusive o `Idempotency-Key` do lote —, que é o que torna o
   * reenvio seguro do lado do servidor.
   */
  async function withRetry<T>(attempt: () => Promise<SyncResult<T>>): Promise<SyncResult<T>> {
    let last: SyncResult<T> = await attempt();
    for (let round = 1; round < MAX_ATTEMPTS; round += 1) {
      if (last.ok || !last.failure.transient) {
        return last;
      }
      await sleep(backoffDelayMs(round, random));
      last = await attempt();
    }
    return last;
  }

  function conflictStateFrom(
    failure: Extract<SyncFailure, { kind: "conflict" }>,
    survey: Survey,
    pendingCount: number,
  ): SyncConflictState {
    const snapshot = failure.conflict.server_snapshot;
    return {
      detail: failure.detail,
      server_version: failure.conflict.server_version,
      server_last_seq: failure.conflict.last_seq_by_device[deviceId] ?? 0,
      server_snapshot: snapshot,
      local_pending_operations: pendingCount,
      local_instrument: survey.context?.instrument ?? null,
      server_instrument: snapshot?.arrival_context?.instrument ?? null,
      local_updated_at: survey.updated_at,
      server_updated_at: snapshot?.updated_at ?? null,
    };
  }

  /** Operações que este aparelho pode oferecer: não reconhecidas, não preteridas, deste
   * `device_id` (o servidor recusa lote com operação de outro aparelho) e em ordem de
   * `seq`. */
  async function pendingForDevice(surveyId: string): Promise<SurveyOperation[]> {
    const pending = await repository.getPendingOperations(surveyId);
    return pending
      .filter((operation) => operation.device_id === deviceId)
      .sort((a, b) => a.seq - b.seq);
  }

  async function countPending(surveyId: string): Promise<number> {
    return (await repository.getPendingOperations(surveyId)).length;
  }

  /**
   * O que o aparelho sabe sozinho: quantas operações faltam confirmar e quanta mídia o
   * levantamento referencia. Sem rede — é o estado que o painel mostra ao abrir, antes de
   * o técnico decidir enviar.
   *
   * Mídia aparece como "0 de N" até uma passada de sincronização dizer o contrário: a
   * confirmação do servidor não é guardada no aparelho, e supor "já enviei" sem o servidor
   * ter dito seria exatamente o tipo de otimismo que esta fatia não pode ter.
   */
  async function refreshLocal(surveyId: string): Promise<SyncState> {
    if (state.survey_id === surveyId && state.phase === "conflict") {
      // Conflito aberto não é apagado por reabrir o painel: a decisão continua pendente.
      return state;
    }
    const sameSurvey = state.survey_id === surveyId;
    const survey = await repository.getSurvey(surveyId);
    const history = await repository.listOperations(surveyId);
    const sendable = history.filter((operation) => operation.status !== "superseded");
    const acked = sendable.filter((operation) => operation.status === "acked").length;
    const media =
      survey === undefined
        ? { jobs: [], missing: [], index: new Map<string, MediaMeta>() }
        : await planMedia(repository, survey);
    return publish({
      survey_id: surveyId,
      phase: api === null ? "local_mode" : isOnline() ? "idle" : "offline",
      pending_operations: await countPending(surveyId),
      categories: emptyCategories().map((entry) =>
        entry.category === "metadata"
          ? {
              ...entry,
              total: sendable.length,
              sent: acked,
              status: acked === sendable.length ? "sent" : "waiting",
            }
          : {
              ...entry,
              total: media.jobs.filter((job) => job.category === entry.category).length,
            },
      ),
      server_version: sameSurvey ? state.server_version : null,
      last_synced_at: sameSurvey ? state.last_synced_at : null,
      completed: sameSurvey ? state.completed : false,
      conflict: null,
      error: null,
    });
  }

  async function runSync(surveyId: string, packetOverride?: SurveyPacketShape): Promise<SyncState> {
    // Começo de passada: as contagens desta passada zeram, mas o que já era verdade sobre
    // ESTE levantamento (pendências, versão e hora do último ack) permanece — piscar "0
    // pendentes" na barra no meio de um envio seria dizer algo falso por um instante.
    const sameSurvey = state.survey_id === surveyId;
    publish({
      ...initialSyncState(api === null ? "local_mode" : "idle"),
      survey_id: surveyId,
      pending_operations: sameSurvey ? state.pending_operations : 0,
      server_version: sameSurvey ? state.server_version : null,
      last_synced_at: sameSurvey ? state.last_synced_at : null,
      categories: emptyCategories(),
    });

    if (api === null) {
      return patch({
        phase: "local_mode",
        pending_operations: await countPending(surveyId),
      });
    }

    const survey = await repository.getSurvey(surveyId);
    if (survey === undefined) {
      return patch({
        phase: "error",
        error: {
          code: "SYNC_LEVANTAMENTO_AUSENTE",
          message: "O levantamento não está mais guardado neste aparelho.",
        },
      });
    }

    const history = await repository.listOperations(surveyId);
    const sendable = history.filter((operation) => operation.status !== "superseded");
    const ackedCount = sendable.filter((operation) => operation.status === "acked").length;
    patch({
      pending_operations: await countPending(surveyId),
      categories: state.categories.map((entry) =>
        entry.category === "metadata"
          ? {
              ...entry,
              total: sendable.length,
              sent: ackedCount,
              status: sendable.length === 0 || ackedCount === sendable.length ? "sent" : "waiting",
            }
          : entry,
      ),
    });

    if (!isOnline()) {
      return patch({ phase: "offline" });
    }

    const token = await getFreshAccessToken();
    if (!token.ok) {
      // Prancha 6c: o envio para, a coleta não. Nada do outbox é tocado aqui.
      return patch({ phase: "reauth_required" });
    }

    const media = await planMedia(repository, survey);
    patch({
      categories: state.categories.map((entry) => {
        const total = media.jobs.filter((job) => job.category === entry.category).length;
        return entry.category === "metadata" ? entry : { ...entry, total };
      }),
    });
    for (const reference of media.missing) {
      noteCategoryFailure(
        reference.category,
        "um arquivo referenciado pelo levantamento não está mais neste aparelho.",
      );
    }

    // ---- 1. metadados ------------------------------------------------------------
    const batch = await pendingForDevice(surveyId);
    if (batch.length > 0) {
      patch({ phase: "sending_metadata" });
      patchCategory("metadata", { status: "running" });
      let packet: SurveyPacketShape;
      try {
        packet = packetOverride ?? toSurveyPacket(survey, batch, media.index);
      } catch (error) {
        const message =
          error instanceof MissingMediaError
            ? "Um arquivo referenciado pelo levantamento (foto ou áudio) não está mais neste aparelho; o pacote não pode ser montado."
            : "O levantamento não pôde ser empacotado para envio.";
        return patch({
          phase: "error",
          error: { code: "SYNC_PACOTE_INVALIDO", message },
        });
      }

      // Marca `pending` ANTES do envio: app fechado no meio do POST reencontra a operação
      // e a reoferece — o servidor reconhece pelo `operation_id` sem duplicar.
      await repository.saveOperations(
        batch.map((operation) => ({ ...operation, status: "pending" as const })),
      );

      const batchId = newBatchId();
      const submitted = await withRetry(() =>
        api.submitOperations({
          token: token.token,
          surveyId,
          batchId,
          body: {
            device_id: deviceId,
            survey: packet,
            operations: batch.map((operation) => ({
              operation_id: operation.operation_id,
              device_id: operation.device_id,
              survey_id: operation.survey_id,
              seq: operation.seq,
              type: operation.type,
              payload: operation.payload,
              created_at: operation.created_at,
            })),
          },
        }),
      );

      if (!submitted.ok) {
        const failure = submitted.failure;
        if (failure.kind === "conflict") {
          return patch({
            phase: "conflict",
            conflict: conflictStateFrom(failure, survey, batch.length),
            pending_operations: await countPending(surveyId),
          });
        }
        if (failure.kind === "unauthorized") {
          return patch({ phase: "reauth_required" });
        }
        noteCategoryFailure("metadata", failureMessage(failure));
        return patch({
          phase: "error",
          error: { code: failureCode(failure), message: failureMessage(failure) },
          pending_operations: await countPending(surveyId),
        });
      }

      const ack = submitted.value;
      const ackedIds = new Set(ack.acked_operation_ids);
      const ackedNow = batch.filter((operation) => ackedIds.has(operation.operation_id));
      await repository.saveOperations(
        ackedNow.map((operation) => ({ ...operation, status: "acked" as const })),
      );
      const stillPending = await countPending(surveyId);
      patch({
        server_version: ack.version,
        last_synced_at: now().toISOString(),
        pending_operations: stillPending,
      });
      patchCategory("metadata", {
        // Confirmadas ao todo: as que já estavam reconhecidas mais as deste lote. Contar o
        // lote inteiro como enviado seria mentir quando o servidor reconhece só parte dele.
        sent: ackedCount + ackedNow.length,
        status: stillPending === 0 ? "sent" : "partial",
      });
    }

    // ---- 2. estado do servidor (versão + mídia já confirmada) ---------------------
    const remote = await withRetry(() => api.getSurveyState({ token: token.token, surveyId }));
    let serverState: ServerSurveyState | null = null;
    if (remote.ok) {
      serverState = remote.value;
      if (serverState !== null) {
        patch({ server_version: serverState.version, completed: serverState.status !== "OPEN" });
      }
    } else if (remote.failure.kind === "unauthorized") {
      return patch({ phase: "reauth_required" });
    }

    // ---- 3. mídia, por categoria (prancha 6a) ------------------------------------
    const confirmedDigests = new Set(
      (serverState?.media ?? [])
        .filter((entry) => entry.status === "CONFIRMED")
        .map((entry) => entry.sha256),
    );
    if (media.jobs.length > 0) {
      patch({ phase: "sending_media" });
      for (const job of media.jobs) {
        const category = job.category;
        if (confirmedDigests.has(job.media.sha256)) {
          const current = categoryOf(category);
          patchCategory(category, {
            sent: current.sent + 1,
            status: current.failed > 0 ? "partial" : "sent",
          });
          continue;
        }
        patchCategory(category, { status: "running" });
        const sent = await uploadOne(job, token.token, surveyId);
        const current = categoryOf(category);
        if (sent) {
          const sentCount = current.sent + 1;
          patchCategory(category, {
            sent: sentCount,
            status:
              current.failed === 0 && sentCount === current.total
                ? "sent"
                : current.failed === 0
                  ? "running"
                  : "partial",
          });
        }
        // Falha de um item não trava os outros (prancha 6a): o laço continua.
      }
      // Fecha as categorias que terminaram sem falha.
      for (const entry of state.categories) {
        if (entry.total > 0 && entry.failed === 0 && entry.sent === entry.total) {
          patchCategory(entry.category, { status: "sent" });
        }
      }
    }

    // ---- 4. conclusão -------------------------------------------------------------
    // Conclusão exige TODA mídia referenciada confirmada — é a mesma precondição que o
    // servidor cobra (`SURVEY_MEDIA_PENDING`); pedir a conclusão sem ela só produziria um
    // 409 previsível.
    const mediaComplete = state.categories.every(
      (entry) => entry.category === "metadata" || (entry.failed === 0 && entry.sent === entry.total),
    );
    const pendingAfter = await countPending(surveyId);
    const serverVersion = state.server_version;
    if (
      surveyStatus(survey) === "concluded" &&
      mediaComplete &&
      pendingAfter === 0 &&
      serverVersion !== null &&
      !state.completed
    ) {
      patch({ phase: "completing" });
      const completed = await withRetry(() =>
        api.completeSurvey({
          token: token.token,
          surveyId,
          // Chave estável por versão: repetir a conclusão do mesmo estado é o caminho de
          // volta de uma mensagem perdida, não uma conclusão nova (T8).
          idempotencyKey: `complete:${surveyId}:${serverVersion}`,
          baseVersion: serverVersion,
        }),
      );
      if (completed.ok) {
        patch({
          completed: true,
          server_version: completed.value.version,
          last_synced_at: now().toISOString(),
        });
      } else if (completed.failure.kind === "conflict") {
        return patch({
          phase: "conflict",
          conflict: conflictStateFrom(completed.failure, survey, pendingAfter),
        });
      } else if (completed.failure.kind === "unauthorized") {
        return patch({ phase: "reauth_required" });
      } else {
        return patch({
          phase: "error",
          error: {
            code: failureCode(completed.failure),
            message: failureMessage(completed.failure),
          },
        });
      }
    }

    const anyFailure = state.categories.some((entry) => entry.failed > 0);
    return patch({
      phase: anyFailure ? "error" : "done",
      pending_operations: pendingAfter,
      error: anyFailure
        ? {
            code: "SYNC_ENVIO_INCOMPLETO",
            message:
              "Parte do levantamento não foi aceita pelo servidor. Nada foi apagado deste aparelho; toque em enviar de novo.",
          }
        : null,
    });
  }

  /** presign → PUT → confirm de UM arquivo. Devolve `false` sem lançar quando falha. */
  async function uploadOne(job: MediaJob, token: string, surveyId: string): Promise<boolean> {
    if (api === null) {
      return false;
    }
    const presigned = await withRetry(() =>
      api.presignMedia({
        token,
        surveyId,
        // Chave determinística por arquivo: retomar um envio interrompido em campo é o
        // caso normal, e a mesma chave com o mesmo corpo devolve a mesma assinatura.
        idempotencyKey: `media-presign:${surveyId}:${job.media.sha256}`,
        sha256: job.media.sha256,
        mimeType: job.media.mime_type,
        byteSize: job.media.byte_size,
      }),
    );
    if (!presigned.ok) {
      const failure = presigned.failure;
      noteCategoryFailure(
        job.category,
        failure.kind === "problem" && failure.code === SURVEY_MEDIA_NOT_REFERENCED
          ? "o servidor ainda não conhece a âncora deste arquivo; ele sobe na próxima sincronização."
          : failureMessage(failure),
      );
      return false;
    }

    const uploaded = await withRetry(() =>
      api.uploadMedia({
        url: presigned.value.url,
        headers: presigned.value.headers,
        blob: job.media.blob,
      }),
    );
    if (!uploaded.ok) {
      noteCategoryFailure(job.category, failureMessage(uploaded.failure));
      return false;
    }

    const confirmed = await withRetry(() =>
      api.confirmMedia({ token, surveyId, sha256: job.media.sha256 }),
    );
    if (!confirmed.ok) {
      const failure = confirmed.failure;
      noteCategoryFailure(
        job.category,
        failure.kind === "problem" && failure.code === SURVEY_MEDIA_DIGEST_MISMATCH
          ? "o arquivo chegou diferente do que saiu do aparelho; ele será reenviado na próxima sincronização."
          : failureMessage(failure),
      );
      return false;
    }
    patch({ server_version: confirmed.value.version });
    return true;
  }

  async function applyConflictDecision(
    decision: ConflictDecision,
    justification: string,
  ): Promise<SyncState> {
    const conflict = state.conflict;
    const surveyId = state.survey_id;
    if (conflict === null || surveyId === null) {
      return state;
    }
    const pending = await pendingForDevice(surveyId);
    /**
     * A história local que o técnico preterir ao aceitar a versão do escritório. São dois
     * conjuntos, e os dois precisam sair:
     *
     * 1. o que ainda não foi reconhecido (`local`/`pending`) — é o trabalho local que a
     *    decisão acabou de recusar, esteja o `seq` acima ou abaixo do servidor;
     * 2. o que está `acked` ACIMA do último `seq` que o servidor tem — reconhecido numa
     *    história que o servidor perdeu ou nunca teve (restauração de backup, ambiente
     *    trocado), e portanto igualmente abandonado.
     *
     * Deixar (2) vivo era o defeito: `nextSeq` continuaria contando a partir do topo
     * abandonado, a próxima ação do técnico nasceria acima do que o servidor espera e cada
     * comando seguinte reabriria a prancha 6b — a decisão nunca "pegaria". O que fica vivo
     * é exatamente a história que o servidor reconhece (`acked` até `server_last_seq`),
     * mais a operação de resolução logo acima dela.
     */
    const abandoned = (await repository.listOperations(surveyId)).filter(
      (operation) =>
        operation.device_id === deviceId &&
        operation.status !== "superseded" &&
        (operation.status !== "acked" || operation.seq > conflict.server_last_seq),
    );
    // Reancora a sequência local no ponto em que o servidor parou. Só o `seq` muda —
    // `operation_id`, `payload` e `created_at` continuam os mesmos, e o servidor filtra
    // pelo `operation_id` o que já tiver gravado. Sem isto, o mesmo buraco de sequência que
    // abriu o conflito reapareceria em todo reenvio. Em `accept_server` não há o que
    // reancorar: a história local acima do servidor sai da fila inteira.
    const rebased =
      decision === "keep_local"
        ? pending.map((operation, index) => ({
            ...operation,
            seq: conflict.server_last_seq + 1 + index,
            status: "local" as const,
          }))
        : [];
    const resolution: SurveyOperation = {
      operation_id: newOperationId(),
      device_id: deviceId,
      survey_id: surveyId,
      seq: conflict.server_last_seq + 1 + rebased.length,
      type: CONFLICT_RESOLUTION_OPERATION,
      payload: {
        decision,
        justification,
        server_version: conflict.server_version,
        server_last_seq: conflict.server_last_seq,
        superseded_operation_ids:
          decision === "accept_server" ? abandoned.map((operation) => operation.operation_id) : [],
      },
      status: "local",
      created_at: now().toISOString(),
    };

    if (decision === "keep_local") {
      // Uma escrita só: reancorar metade das operações deixaria o outbox num estado que
      // nenhum caminho de leitura espera.
      await repository.saveOperations([...rebased, resolution]);
      return runSync(surveyId);
    }

    // `accept_server`: a história local acima do servidor (pendente OU já reconhecida numa
    // história que o servidor não tem) SAI da fila de envio e da contagem de `seq`, e
    // CONTINUA gravada (`superseded`, nunca removida). O lote seguinte leva só a decisão, e
    // leva o pacote do SERVIDOR — mandar o pacote local aqui sobrescreveria no servidor
    // exatamente a versão que o técnico acabou de aceitar.
    await repository.saveOperations([
      ...abandoned.map((operation) => ({ ...operation, status: "superseded" as const })),
      resolution,
    ]);
    const snapshot = conflict.server_snapshot;
    if (snapshot === null) {
      // Conflito de corrida de escrita não traz o estado do servidor (T8). A decisão fica
      // registrada; a próxima passada relê o estado e reenvia só a resolução.
      return patch({
        phase: "idle",
        conflict: null,
        pending_operations: await countPending(surveyId),
      });
    }
    return runSync(surveyId, snapshot);
  }

  return {
    getState: () => state,
    syncSurvey: (surveyId) =>
      queue(async () => {
        try {
          return await runSync(surveyId);
        } catch {
          // Rede em campo produz falhas que nenhum contrato previu; o painel precisa de um
          // estado escrito, não de uma promessa rejeitada subindo até o React.
          return patch({
            phase: "error",
            error: {
              code: "SYNC_FALHA_INESPERADA",
              message: "A sincronização parou por um erro inesperado. Nada foi apagado do aparelho.",
            },
          });
        }
      }),
    resolveConflict: (decision, justification) =>
      queue(async () => {
        try {
          return await applyConflictDecision(
            decision,
            justification ?? CONFLICT_JUSTIFICATION[decision],
          );
        } catch {
          return patch({
            phase: "error",
            error: {
              code: "SYNC_FALHA_INESPERADA",
              message: "A decisão foi registrada, mas o reenvio parou por um erro inesperado.",
            },
          });
        }
      }),
    refreshLocal: (surveyId) => queue(() => refreshLocal(surveyId)),
  };
}
