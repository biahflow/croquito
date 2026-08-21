/**
 * Testes do motor de sincronização (T9). NENHUMA rede real: o `fetch` é falso e o cliente
 * de API é o de produção, para que cabeçalho, `Idempotency-Key`, ordem das chamadas e
 * leitura de `problem+json` sejam exercidos de ponta a ponta.
 *
 * O que estes testes protegem: o lote sai em ordem de `seq` com chave idempotente estável
 * na retentativa; o ack marca (nunca apaga) as operações; conflito vira estado apresentado
 * e a decisão do técnico volta como `conflict_resolution`; mídia só depois dos metadados;
 * digest divergente vira erro escrito e acionável; e token vencido para o envio sem tocar
 * a coleta.
 */

import { beforeEach, describe, expect, it } from "vitest";

import { addPoint } from "../domain/commands";
import type { Survey } from "../domain/types";
import { applyCommand } from "../outbox/applyCommand";
import type { SurveyOperation } from "../outbox/types";
import { DexieSurveyRepository } from "../storage/DexieSurveyRepository";
import type { MediaRecord, SurveyRepository } from "../storage/SurveyRepository";
import { createSyncApi, type FetchLike } from "./apiClient";
import { toSurveyPacket } from "./contract";
import { createSyncEngine, type SyncEngine } from "./engine";
import type { SyncState } from "./state";

const NOW = "2026-08-21T15:12:00.000Z";
const DEVICE = "device-1";
const SURVEY_ID = "survey-1";
const BASE_URL = "https://api.croquito.test";
const TOKEN = "token-de-teste";
const PHOTO_SHA256 = "a".repeat(64);
const PHOTO_BYTES = new Uint8Array([1, 2, 3, 4, 5, 6, 7, 8]);

interface RecordedCall {
  url: string;
  method: string;
  headers: Record<string, string>;
  body: unknown;
}

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

/** Mesmo envelope do `problem_handler` da API (código no topo e no `detail` aninhado). */
function problemResponse(
  status: number,
  code: string,
  detail: string,
  details?: Record<string, unknown>,
): Response {
  return new Response(
    JSON.stringify({
      type: `https://errors.croquito.local/${code.toLowerCase()}`,
      title: code,
      status,
      code,
      request_id: "req-teste",
      detail: { code, detail, ...(details === undefined ? {} : { details }) },
    }),
    { status, headers: { "Content-Type": "application/problem+json" } },
  );
}

function headersOf(init: RequestInit): Record<string, string> {
  const raw = init.headers;
  return raw === undefined ? {} : { ...(raw as Record<string, string>) };
}

function createFakeFetch(responder: (call: RecordedCall) => Response): {
  fetch: FetchLike;
  calls: RecordedCall[];
} {
  const calls: RecordedCall[] = [];
  const fetchImpl: FetchLike = async (input, init) => {
    const call: RecordedCall = {
      url: input,
      method: init.method ?? "GET",
      headers: headersOf(init),
      body:
        typeof init.body === "string" ? (JSON.parse(init.body) as unknown) : (init.body ?? null),
    };
    calls.push(call);
    return responder(call);
  };
  return { fetch: fetchImpl, calls };
}

function surveyFixture(overrides: Partial<Survey> = {}): Survey {
  return {
    id: SURVEY_ID,
    name: "Guaxindiba",
    order_id: "order-1",
    context: {
      instrument: "Trena laser",
      reference_note: "Poste na esquina",
      arrived_at: NOW,
    },
    points: [{ id: "p1", x_mm: 0, y_mm: 0, created_at: NOW }],
    segments: [],
    measurements: [],
    photo_anchors: [],
    elements: [],
    observations: [],
    created_at: NOW,
    updated_at: NOW,
    ...overrides,
  };
}

function operationFixture(seq: number, overrides: Partial<SurveyOperation> = {}): SurveyOperation {
  return {
    operation_id: `op-${seq}`,
    device_id: DEVICE,
    survey_id: SURVEY_ID,
    seq,
    type: "point.add",
    payload: { point_id: `p${seq}` },
    status: "local",
    created_at: NOW,
    ...overrides,
  };
}

function photoMedia(): MediaRecord {
  const blob = new Blob([PHOTO_BYTES], { type: "image/jpeg" });
  return {
    id: "media-photo",
    sha256: PHOTO_SHA256,
    mime_type: "image/jpeg",
    byte_size: blob.size,
    blob,
    created_at: NOW,
  };
}

function ackBody(operationIds: string[], version: number, lastSeq: number): unknown {
  return {
    survey_id: SURVEY_ID,
    acked_operation_ids: operationIds,
    version,
    last_seq_by_device: { [DEVICE]: lastSeq },
  };
}

function stateBody(version: number, media: unknown[] = [], status = "OPEN"): unknown {
  return {
    version,
    status,
    last_seq_by_device: { [DEVICE]: version },
    media,
    survey: null,
  };
}

/**
 * Servidor falso que cobra a MESMA regra da rota real (T8,
 * `submit_survey_operations`): operação já gravada é reconhecida de novo sem regravar, e
 * o que sobra precisa continuar exatamente de `last_seq + 1`, contíguo. É o que permite
 * provar que o aparelho volta a falar a sequência do servidor depois de um conflito — um
 * responder que sempre devolve 200 não provaria nada disso.
 */
function contiguityServer(initial: { lastSeq: number; snapshot: unknown }): (
  call: RecordedCall,
) => Response {
  const stored = new Set<string>();
  let lastSeq = initial.lastSeq;
  let version = 4;
  return (call) => {
    if (!call.url.endsWith("/operations")) {
      return jsonResponse(200, stateBody(version));
    }
    const body = call.body as { operations: { operation_id: string; seq: number }[] };
    const incoming = body.operations.filter(
      (operation) => !stored.has(operation.operation_id),
    );
    const expected = lastSeq + 1;
    if (incoming.some((operation, index) => operation.seq !== expected + index)) {
      return problemResponse(409, "SURVEY_CONFLICT", "Sequência divergente.", {
        server_version: version,
        last_seq_by_device: { [DEVICE]: lastSeq },
        server_snapshot: initial.snapshot,
      });
    }
    for (const operation of incoming) {
      stored.add(operation.operation_id);
      lastSeq = Math.max(lastSeq, operation.seq);
    }
    if (incoming.length > 0) {
      version += 1;
    }
    return jsonResponse(
      200,
      ackBody(
        body.operations.map((operation) => operation.operation_id),
        version,
        lastSeq,
      ),
    );
  };
}

interface Harness {
  repository: SurveyRepository;
  engine: SyncEngine;
  calls: RecordedCall[];
  states: SyncState[];
}

function harness(
  responder: (call: RecordedCall) => Response,
  options: {
    repository: SurveyRepository;
    token?: () => Promise<{ ok: true; token: string } | { ok: false; reason: "AUTH_REAUTH_REQUIRED" }>;
    isOnline?: () => boolean;
    api?: "real" | "none";
  },
): Harness {
  const { fetch: fetchImpl, calls } = createFakeFetch(responder);
  const states: SyncState[] = [];
  const engine = createSyncEngine({
    repository: options.repository,
    api: options.api === "none" ? null : createSyncApi(BASE_URL, fetchImpl),
    deviceId: DEVICE,
    getFreshAccessToken: options.token ?? (async () => ({ ok: true, token: TOKEN })),
    isOnline: options.isOnline ?? (() => true),
    now: () => new Date(NOW),
    newBatchId: () => "batch-1",
    newOperationId: () => "op-resolucao",
    sleep: async () => undefined,
    random: () => 0,
    onState: (state) => states.push(state),
  });
  return { repository: options.repository, engine, calls, states };
}

describe("createSyncEngine", () => {
  let repository: SurveyRepository;

  beforeEach(() => {
    repository = new DexieSurveyRepository(`test-db-${Math.random().toString(36).slice(2)}`);
  });

  async function seed(
    survey: Survey,
    operations: SurveyOperation[],
    media?: MediaRecord,
  ): Promise<void> {
    await repository.saveSurvey(survey);
    for (const operation of operations) {
      await repository.appendOperation(operation);
    }
    if (media !== undefined) {
      await repository.saveMedia(media);
    }
  }

  it("envia o lote em ordem de seq e reusa a mesma Idempotency-Key na retentativa", async () => {
    await seed(surveyFixture(), [operationFixture(2), operationFixture(1)]);
    let submits = 0;
    const { engine, calls } = harness(
      (call) => {
        if (call.url.endsWith("/operations")) {
          submits += 1;
          // Primeira tentativa cai num 503 (falha transitória, a rede de campo oscila).
          return submits === 1
            ? problemResponse(503, "PROCESSING_UNAVAILABLE", "Tente de novo.")
            : jsonResponse(200, ackBody(["op-1", "op-2"], 1, 2));
        }
        return jsonResponse(200, stateBody(1));
      },
      { repository },
    );

    const state = await engine.syncSurvey(SURVEY_ID);

    expect(state.phase).toBe("done");
    const submitCalls = calls.filter((call) => call.url.endsWith("/operations"));
    expect(submitCalls).toHaveLength(2);
    const keys = submitCalls.map((call) => call.headers["Idempotency-Key"]);
    expect(keys[0]).toBe("batch-1");
    expect(keys[1]).toBe(keys[0]);
    const body = submitCalls[0]?.body as { device_id: string; operations: { seq: number }[] };
    expect(body.device_id).toBe(DEVICE);
    expect(body.operations.map((operation) => operation.seq)).toEqual([1, 2]);
    expect(submitCalls[0]?.headers.Authorization).toBe(`Bearer ${TOKEN}`);
  });

  it("o ack marca as operações e não apaga nenhuma linha do outbox", async () => {
    await seed(surveyFixture(), [operationFixture(1), operationFixture(2)]);
    const { engine } = harness(
      (call) =>
        call.url.endsWith("/operations")
          ? jsonResponse(200, ackBody(["op-1", "op-2"], 1, 2))
          : jsonResponse(200, stateBody(1)),
      { repository },
    );

    const state = await engine.syncSurvey(SURVEY_ID);

    expect(state.pending_operations).toBe(0);
    expect(state.server_version).toBe(1);
    const stored = await repository.listOperations(SURVEY_ID);
    expect(stored).toHaveLength(2);
    expect(stored.every((operation) => operation.status === "acked")).toBe(true);
    const metadata = state.categories.find((entry) => entry.category === "metadata");
    expect(metadata).toMatchObject({ total: 2, sent: 2, failed: 0, status: "sent" });
  });

  it("operação reconhecida só em parte continua pendente, sem sumir", async () => {
    await seed(surveyFixture(), [operationFixture(1), operationFixture(2)]);
    const { engine } = harness(
      (call) =>
        call.url.endsWith("/operations")
          ? jsonResponse(200, ackBody(["op-1"], 1, 1))
          : jsonResponse(200, stateBody(1)),
      { repository },
    );

    const state = await engine.syncSurvey(SURVEY_ID);

    expect(state.pending_operations).toBe(1);
    const stored = await repository.listOperations(SURVEY_ID);
    expect(stored.map((operation) => operation.status)).toEqual(["acked", "pending"]);
  });

  it("a mídia só sai depois dos metadados e passa por presign, PUT e confirm", async () => {
    const survey = surveyFixture({
      photo_anchors: [{ id: "ph1", point_id: "p1", local_media_ref: "media-photo", created_at: NOW }],
    });
    await seed(survey, [operationFixture(1)], photoMedia());
    const { engine, calls } = harness(
      (call) => {
        if (call.url.endsWith("/operations")) {
          return jsonResponse(200, ackBody(["op-1"], 1, 1));
        }
        if (call.url.endsWith("/media/presign")) {
          return jsonResponse(200, {
            media_id: "11111111-1111-1111-1111-111111111111",
            sha256: PHOTO_SHA256,
            object_key: `tenants/t/surveys/${SURVEY_ID}/media/${PHOTO_SHA256}`,
            url: "https://storage.croquito.test/assinada",
            headers: { "Content-Type": "image/jpeg" },
            expires_at: NOW,
          });
        }
        if (call.url.endsWith("/confirm")) {
          return jsonResponse(
            200,
            stateBody(1, [{ sha256: PHOTO_SHA256, mime_type: "image/jpeg", status: "CONFIRMED" }]),
          );
        }
        if (call.method === "PUT") {
          return new Response(null, { status: 200 });
        }
        return jsonResponse(200, stateBody(1));
      },
      { repository },
    );

    const state = await engine.syncSurvey(SURVEY_ID);

    expect(state.phase).toBe("done");
    expect(calls.map((call) => `${call.method} ${call.url.replace(BASE_URL, "")}`)).toEqual([
      `POST /v1/surveys/${SURVEY_ID}/operations`,
      `GET /v1/surveys/${SURVEY_ID}`,
      `POST /v1/surveys/${SURVEY_ID}/media/presign`,
      "PUT https://storage.croquito.test/assinada",
      `POST /v1/surveys/${SURVEY_ID}/media/${PHOTO_SHA256}/confirm`,
    ]);
    // O PUT vai sem `Authorization`: a assinatura já É a autorização.
    const put = calls.find((call) => call.method === "PUT");
    expect(put?.headers.Authorization).toBeUndefined();
    const photos = state.categories.find((entry) => entry.category === "anchored_photo");
    expect(photos).toMatchObject({ total: 1, sent: 1, failed: 0, status: "sent" });
  });

  it("duas âncoras da mesma foto sobem uma vez, e o pacote resolve as duas", async () => {
    const survey = surveyFixture({
      photo_anchors: [
        { id: "ph1", point_id: "p1", local_media_ref: "media-photo", created_at: NOW },
        { id: "ph2", point_id: "p1", local_media_ref: "media-copia", created_at: NOW },
      ],
    });
    await seed(survey, [operationFixture(1)], photoMedia());
    // Mesmo conteúdo (mesmo digest), outra linha de mídia — é o que acontece quando a
    // mesma foto é ancorada duas vezes.
    await repository.saveMedia({ ...photoMedia(), id: "media-copia" });
    const { engine, calls } = harness(
      (call) => {
        if (call.url.endsWith("/operations")) {
          return jsonResponse(200, ackBody(["op-1"], 1, 1));
        }
        if (call.url.endsWith("/media/presign")) {
          return jsonResponse(200, {
            media_id: "11111111-1111-1111-1111-111111111111",
            sha256: PHOTO_SHA256,
            object_key: "chave",
            url: "https://storage.croquito.test/assinada",
            headers: {},
            expires_at: NOW,
          });
        }
        if (call.method === "PUT") {
          return new Response(null, { status: 200 });
        }
        return jsonResponse(200, stateBody(1));
      },
      { repository },
    );

    const state = await engine.syncSurvey(SURVEY_ID);

    // O pacote precisa resolver as DUAS referências, senão nem sai do aparelho.
    const submitted = calls[0]?.body as { survey: { media_anchors: { id: string }[] } };
    expect(submitted.survey.media_anchors.map((anchor) => anchor.id)).toEqual(["ph1", "ph2"]);
    expect(calls.filter((call) => call.method === "PUT")).toHaveLength(1);
    expect(state.phase).toBe("done");
  });

  it("mídia já confirmada no servidor não é reenviada", async () => {
    const survey = surveyFixture({
      photo_anchors: [{ id: "ph1", point_id: "p1", local_media_ref: "media-photo", created_at: NOW }],
    });
    await seed(survey, [operationFixture(1)], photoMedia());
    const { engine, calls } = harness(
      (call) =>
        call.url.endsWith("/operations")
          ? jsonResponse(200, ackBody(["op-1"], 1, 1))
          : jsonResponse(
              200,
              stateBody(1, [{ sha256: PHOTO_SHA256, mime_type: "image/jpeg", status: "CONFIRMED" }]),
            ),
      { repository },
    );

    const state = await engine.syncSurvey(SURVEY_ID);

    expect(calls.some((call) => call.method === "PUT")).toBe(false);
    expect(state.categories.find((entry) => entry.category === "anchored_photo")).toMatchObject({
      sent: 1,
      status: "sent",
    });
  });

  it("digest divergente vira erro escrito e acionável, sem travar o resto", async () => {
    const survey = surveyFixture({
      photo_anchors: [{ id: "ph1", point_id: "p1", local_media_ref: "media-photo", created_at: NOW }],
    });
    await seed(survey, [operationFixture(1)], photoMedia());
    const { engine } = harness(
      (call) => {
        if (call.url.endsWith("/operations")) {
          return jsonResponse(200, ackBody(["op-1"], 1, 1));
        }
        if (call.url.endsWith("/media/presign")) {
          return jsonResponse(200, {
            media_id: "11111111-1111-1111-1111-111111111111",
            sha256: PHOTO_SHA256,
            object_key: "chave",
            url: "https://storage.croquito.test/assinada",
            headers: {},
            expires_at: NOW,
          });
        }
        if (call.method === "PUT") {
          return new Response(null, { status: 200 });
        }
        if (call.url.endsWith("/confirm")) {
          return problemResponse(
            409,
            "SURVEY_MEDIA_DIGEST_MISMATCH",
            "Mídia ausente, incompleta ou com integridade divergente do declarado.",
          );
        }
        return jsonResponse(200, stateBody(1));
      },
      { repository },
    );

    const state = await engine.syncSurvey(SURVEY_ID);

    expect(state.phase).toBe("error");
    expect(state.error?.code).toBe("SYNC_ENVIO_INCOMPLETO");
    const photos = state.categories.find((entry) => entry.category === "anchored_photo");
    expect(photos?.failed).toBe(1);
    expect(photos?.failure_detail).toContain("chegou diferente do que saiu do aparelho");
    // Metadados seguem confirmados: a falha de uma foto não desfaz o que já foi aceito.
    expect(state.categories.find((entry) => entry.category === "metadata")?.sent).toBe(1);
    const stored = await repository.listOperations(SURVEY_ID);
    expect(stored[0]?.status).toBe("acked");
  });

  it("conflito abre o estado da prancha 6b sem tocar o outbox", async () => {
    await seed(surveyFixture(), [operationFixture(6)]);
    const serverSnapshot = toSurveyPacket(
      surveyFixture({ name: "Guaxindiba", updated_at: "2026-08-21T16:05:00.000Z" }),
      [operationFixture(5, { device_id: DEVICE })],
      new Map(),
    );
    const { engine } = harness(
      (call) =>
        call.url.endsWith("/operations")
          ? problemResponse(
              409,
              "SURVEY_CONFLICT",
              "A sequência do aparelho não continua de onde o servidor parou; resolva o conflito no aparelho e reenvie.",
              {
                server_version: 4,
                last_seq_by_device: { [DEVICE]: 5 },
                server_snapshot: serverSnapshot,
              },
            )
          : jsonResponse(200, stateBody(4)),
      { repository },
    );

    const state = await engine.syncSurvey(SURVEY_ID);

    expect(state.phase).toBe("conflict");
    expect(state.conflict).toMatchObject({
      server_version: 4,
      server_last_seq: 5,
      local_pending_operations: 1,
      local_instrument: "Trena laser",
      server_instrument: "Trena laser",
    });
    expect(state.conflict?.detail).toContain("sequência do aparelho");
    // Nada foi apagado nem reconhecido: a operação continua no outbox, marcada como
    // oferecida ao servidor.
    const stored = await repository.listOperations(SURVEY_ID);
    expect(stored).toHaveLength(1);
    expect(stored[0]?.status).toBe("pending");
  });

  it("manter a minha reancora a sequência e reenvia com a decisão registrada", async () => {
    await seed(surveyFixture(), [operationFixture(6), operationFixture(7)]);
    let submits = 0;
    const { engine, calls } = harness(
      (call) => {
        if (call.url.endsWith("/operations")) {
          submits += 1;
          return submits === 1
            ? problemResponse(409, "SURVEY_CONFLICT", "Sequência divergente.", {
                server_version: 4,
                last_seq_by_device: { [DEVICE]: 9 },
                server_snapshot: null,
              })
            : jsonResponse(200, ackBody(["op-6", "op-7", "op-resolucao"], 5, 12));
        }
        return jsonResponse(200, stateBody(5));
      },
      { repository },
    );

    await engine.syncSurvey(SURVEY_ID);
    const state = await engine.resolveConflict("keep_local");

    expect(state.phase).toBe("done");
    const resent = calls.filter((call) => call.url.endsWith("/operations"))[1];
    const body = resent?.body as {
      operations: { operation_id: string; seq: number; type: string; payload: Record<string, unknown> }[];
    };
    expect(body.operations.map((operation) => [operation.operation_id, operation.seq])).toEqual([
      ["op-6", 10],
      ["op-7", 11],
      ["op-resolucao", 12],
    ]);
    const resolution = body.operations[2];
    expect(resolution?.type).toBe("conflict_resolution");
    expect(resolution?.payload.decision).toBe("keep_local");
    expect(typeof resolution?.payload.justification).toBe("string");
    expect(state.pending_operations).toBe(0);
    // A retentativa do lote novo tem chave própria — é outro lote, não o mesmo.
    expect(resent?.headers["Idempotency-Key"]).toBe("batch-1");
  });

  it("aceitar a do escritório preteriu o local sem apagar e reenvia o pacote do servidor", async () => {
    await seed(surveyFixture(), [operationFixture(6)]);
    const serverSnapshot = toSurveyPacket(
      surveyFixture({ name: "Guaxindiba (escritório)" }),
      [operationFixture(9, { operation_id: "op-servidor" })],
      new Map(),
    );
    let submits = 0;
    const { engine, calls } = harness(
      (call) => {
        if (call.url.endsWith("/operations")) {
          submits += 1;
          return submits === 1
            ? problemResponse(409, "SURVEY_CONFLICT", "Sequência divergente.", {
                server_version: 4,
                last_seq_by_device: { [DEVICE]: 9 },
                server_snapshot: serverSnapshot,
              })
            : jsonResponse(200, ackBody(["op-resolucao"], 5, 10));
        }
        return jsonResponse(200, stateBody(5));
      },
      { repository },
    );

    await engine.syncSurvey(SURVEY_ID);
    const state = await engine.resolveConflict("accept_server");

    const resent = calls.filter((call) => call.url.endsWith("/operations"))[1];
    const body = resent?.body as {
      survey: { name: string };
      operations: { operation_id: string; seq: number; payload: Record<string, unknown> }[];
    };
    // O pacote enviado é o do SERVIDOR: mandar o local aqui sobrescreveria justamente a
    // versão que o técnico acabou de aceitar.
    expect(body.survey.name).toBe("Guaxindiba (escritório)");
    expect(body.operations).toHaveLength(1);
    expect(body.operations[0]?.operation_id).toBe("op-resolucao");
    expect(body.operations[0]?.seq).toBe(10);
    expect(body.operations[0]?.payload.superseded_operation_ids).toEqual(["op-6"]);
    // A operação preterida continua gravada, fora da fila de envio.
    const stored = await repository.listOperations(SURVEY_ID);
    expect(stored.find((operation) => operation.operation_id === "op-6")?.status).toBe(
      "superseded",
    );
    expect(await repository.getPendingOperations(SURVEY_ID)).toEqual([]);
    expect(state.pending_operations).toBe(0);
  });

  it("depois de aceitar o escritório, a próxima edição continua a sequência do servidor", async () => {
    // Regressão do defeito encontrado na revisão da T9: com a história local preterida
    // ainda contando para `nextSeq`, a ação seguinte nascia no topo abandonado (seq 8),
    // o servidor esperava 4, e TODA edição posterior reabria a prancha 6b — a decisão do
    // técnico nunca "pegava".
    const survey = surveyFixture();
    await seed(survey, [
      operationFixture(1, { status: "acked" }),
      // `acked` numa história que o servidor não tem (restauração, ambiente trocado):
      // pertence ao mesmo passado abandonado que as pendentes.
      operationFixture(5, { status: "acked" }),
      operationFixture(6),
      operationFixture(7),
    ]);
    const serverSnapshot = toSurveyPacket(
      surveyFixture({ name: "Guaxindiba (escritório)" }),
      [operationFixture(2, { operation_id: "op-servidor" })],
      new Map(),
    );
    const { engine, calls } = harness(contiguityServer({ lastSeq: 2, snapshot: serverSnapshot }), {
      repository,
    });

    const conflicted = await engine.syncSurvey(SURVEY_ID);
    expect(conflicted.phase).toBe("conflict");
    const resolved = await engine.resolveConflict("accept_server");
    expect(resolved.phase).toBe("done");

    // A resolução ocupou o lugar seguinte ao do servidor…
    const stored = await repository.listOperations(SURVEY_ID);
    const resolution = stored.find((operation) => operation.operation_id === "op-resolucao");
    expect(resolution?.seq).toBe(3);
    expect(resolution?.status).toBe("acked");
    // …e toda a história acima do servidor saiu da fila SEM ser apagada, inclusive a que
    // estava `acked`.
    expect(
      stored
        .filter((operation) => operation.status === "superseded")
        .map((operation) => operation.operation_id),
    ).toEqual(["op-5", "op-6", "op-7"]);
    expect(stored).toHaveLength(5);
    // A operação `acked` ABAIXO do último seq do servidor continua viva: é história que o
    // servidor reconhece.
    expect(stored.find((operation) => operation.operation_id === "op-1")?.status).toBe("acked");

    // A próxima ação do técnico nasce em resolução+1 (4), que é o que o servidor espera…
    const nextCommand = await applyCommand(
      repository,
      survey,
      addPoint(survey, { id: "p9", x_mm: 100, y_mm: 100 }, NOW),
      { device_id: DEVICE, operation_id: "op-depois", created_at: NOW },
    );
    expect(nextCommand.ok && nextCommand.operation.seq).toBe(4);

    // …e a sincronização seguinte fecha sem conflito nenhum.
    const after = await engine.syncSurvey(SURVEY_ID);
    expect(after.phase).toBe("done");
    expect(after.conflict).toBeNull();
    expect(after.pending_operations).toBe(0);
    expect(calls.filter((call) => call.url.endsWith("/operations"))).toHaveLength(3);
  });

  it("manter a minha também deixa a sequência alinhada para a edição seguinte", async () => {
    const survey = surveyFixture();
    await seed(survey, [operationFixture(6), operationFixture(7)]);
    const { engine } = harness(contiguityServer({ lastSeq: 2, snapshot: null }), { repository });

    expect((await engine.syncSurvey(SURVEY_ID)).phase).toBe("conflict");
    const resolved = await engine.resolveConflict("keep_local");

    expect(resolved.phase).toBe("done");
    // Reancoradas em 3 e 4, resolução em 5 — nenhuma delas é história abandonada, então
    // todas continuam contando para o próximo `seq`.
    const stored = await repository.listOperations(SURVEY_ID);
    expect(stored.map((operation) => operation.seq)).toEqual([3, 4, 5]);
    expect(stored.every((operation) => operation.status === "acked")).toBe(true);

    const nextCommand = await applyCommand(
      repository,
      survey,
      addPoint(survey, { id: "p9", x_mm: 100, y_mm: 100 }, NOW),
      { device_id: DEVICE, operation_id: "op-depois", created_at: NOW },
    );
    expect(nextCommand.ok && nextCommand.operation.seq).toBe(6);
    expect((await engine.syncSurvey(SURVEY_ID)).phase).toBe("done");
  });

  it("levantamento concluído com tudo confirmado fecha no servidor", async () => {
    await seed(surveyFixture({ status: "concluded" }), [operationFixture(1)]);
    const { engine, calls } = harness(
      (call) => {
        if (call.url.endsWith("/operations")) {
          return jsonResponse(200, ackBody(["op-1"], 2, 1));
        }
        if (call.url.endsWith("/complete")) {
          return jsonResponse(200, stateBody(2, [], "COMPLETED"));
        }
        return jsonResponse(200, stateBody(2));
      },
      { repository },
    );

    const state = await engine.syncSurvey(SURVEY_ID);

    const complete = calls.find((call) => call.url.endsWith("/complete"));
    expect(complete?.body).toEqual({ base_version: 2 });
    expect(complete?.headers["Idempotency-Key"]).toBe(`complete:${SURVEY_ID}:2`);
    expect(state.completed).toBe(true);
    expect(state.phase).toBe("done");
  });

  it("não conclui enquanto houver mídia pendente", async () => {
    const survey = surveyFixture({
      status: "concluded",
      photo_anchors: [{ id: "ph1", point_id: "p1", local_media_ref: "media-photo", created_at: NOW }],
    });
    await seed(survey, [operationFixture(1)], photoMedia());
    const { engine, calls } = harness(
      (call) => {
        if (call.url.endsWith("/operations")) {
          return jsonResponse(200, ackBody(["op-1"], 1, 1));
        }
        if (call.url.endsWith("/media/presign")) {
          return problemResponse(
            409,
            "SURVEY_MEDIA_NOT_REFERENCED",
            "A mídia não está referenciada no levantamento; sincronize a âncora antes.",
          );
        }
        return jsonResponse(200, stateBody(1));
      },
      { repository },
    );

    const state = await engine.syncSurvey(SURVEY_ID);

    expect(calls.some((call) => call.url.endsWith("/complete"))).toBe(false);
    expect(state.completed).toBe(false);
    expect(
      state.categories.find((entry) => entry.category === "anchored_photo")?.failure_detail,
    ).toContain("ainda não conhece a âncora");
  });

  it("token vencido para o envio e não toca a coleta (prancha 6c)", async () => {
    await seed(surveyFixture(), [operationFixture(1)]);
    const { engine, calls } = harness(() => jsonResponse(200, {}), {
      repository,
      token: async () => ({ ok: false, reason: "AUTH_REAUTH_REQUIRED" }),
    });

    const state = await engine.syncSurvey(SURVEY_ID);

    expect(state.phase).toBe("reauth_required");
    expect(calls).toEqual([]);
    const stored = await repository.listOperations(SURVEY_ID);
    expect(stored[0]?.status).toBe("local");
    expect(await repository.getSurvey(SURVEY_ID)).toBeDefined();
  });

  it("offline não tenta a rede e mostra o estado de espera", async () => {
    await seed(surveyFixture(), [operationFixture(1)]);
    const { engine, calls } = harness(() => jsonResponse(200, {}), {
      repository,
      isOnline: () => false,
    });

    const state = await engine.syncSurvey(SURVEY_ID);

    expect(state.phase).toBe("offline");
    expect(state.pending_operations).toBe(1);
    expect(calls).toEqual([]);
  });

  it("sem API configurada o motor opera em modo local", async () => {
    await seed(surveyFixture(), [operationFixture(1)]);
    const { engine, calls } = harness(() => jsonResponse(200, {}), { repository, api: "none" });

    const state = await engine.syncSurvey(SURVEY_ID);

    expect(state.phase).toBe("local_mode");
    expect(state.pending_operations).toBe(1);
    expect(calls).toEqual([]);
  });

  it("abrir o painel lê só o aparelho: totais por categoria sem tocar a rede", async () => {
    const survey = surveyFixture({
      photo_anchors: [{ id: "ph1", point_id: "p1", local_media_ref: "media-photo", created_at: NOW }],
    });
    await seed(survey, [operationFixture(1, { status: "acked" }), operationFixture(2)], photoMedia());
    const { engine, calls } = harness(() => jsonResponse(200, {}), { repository });

    const state = await engine.refreshLocal(SURVEY_ID);

    expect(calls).toEqual([]);
    expect(state.phase).toBe("idle");
    expect(state.pending_operations).toBe(1);
    expect(state.categories.find((entry) => entry.category === "metadata")).toMatchObject({
      total: 2,
      sent: 1,
    });
    expect(state.categories.find((entry) => entry.category === "anchored_photo")).toMatchObject({
      total: 1,
      sent: 0,
    });
  });

  it("reabrir o painel com conflito aberto não apaga a decisão pendente", async () => {
    await seed(surveyFixture(), [operationFixture(6)]);
    const { engine } = harness(
      (call) =>
        call.url.endsWith("/operations")
          ? problemResponse(409, "SURVEY_CONFLICT", "Sequência divergente.", {
              server_version: 4,
              last_seq_by_device: { [DEVICE]: 9 },
              server_snapshot: null,
            })
          : jsonResponse(200, stateBody(4)),
      { repository },
    );
    await engine.syncSurvey(SURVEY_ID);

    const state = await engine.refreshLocal(SURVEY_ID);

    expect(state.phase).toBe("conflict");
    expect(state.conflict).not.toBeNull();
  });

  it("falha de rede não vira exceção: vira estado escrito, com o outbox intacto", async () => {
    await seed(surveyFixture(), [operationFixture(1)]);
    const { engine } = harness(
      () => {
        throw new TypeError("Failed to fetch");
      },
      { repository },
    );

    const state = await engine.syncSurvey(SURVEY_ID);

    expect(state.phase).toBe("error");
    expect(state.error?.code).toBe("SYNC_SEM_RESPOSTA");
    expect(state.pending_operations).toBe(1);
    const stored = await repository.listOperations(SURVEY_ID);
    expect(stored).toHaveLength(1);
  });
});
