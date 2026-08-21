/**
 * Testes do único módulo de transporte do app — com `fetch` falso, nunca rede real.
 *
 * O que importa aqui é a tradução: `problem+json` vira falha tipada com o código estável
 * do contrato, `409 SURVEY_CONFLICT` vira conflito com o estado do servidor já conferido
 * pelo guarda de forma, `401/403` vira "não autorizado" (e não um erro genérico que o
 * painel apresentaria como falha de rede) e corpo fora do contrato vira falha declarada.
 */

import { describe, expect, it } from "vitest";

import { createSyncApi, type FetchLike } from "./apiClient";
import { normalizeApiBaseUrl } from "./config";

const TOKEN = "token-de-teste";
const SURVEY_ID = "survey-1";

function stub(response: Response): { fetch: FetchLike; urls: string[] } {
  const urls: string[] = [];
  return {
    urls,
    fetch: async (input) => {
      urls.push(input);
      return response;
    },
  };
}

function problem(status: number, code: string, detail: string, details?: unknown): Response {
  return new Response(
    JSON.stringify({ status, code, title: code, detail: { code, detail, details } }),
    { status, headers: { "Content-Type": "application/problem+json" } },
  );
}

describe("normalizeApiBaseUrl", () => {
  it("sem env (ou env vazia) é modo local, não erro", () => {
    expect(normalizeApiBaseUrl(undefined)).toBeNull();
    expect(normalizeApiBaseUrl("")).toBeNull();
    expect(normalizeApiBaseUrl("   ")).toBeNull();
  });

  it("remove a barra final para as rotas concatenarem sem barra dupla", () => {
    expect(normalizeApiBaseUrl("https://api.croquito.test/")).toBe("https://api.croquito.test");
  });
});

describe("createSyncApi", () => {
  it("traduz 409 SURVEY_CONFLICT no estado do servidor da prancha 6b", async () => {
    const { fetch } = stub(
      problem(409, "SURVEY_CONFLICT", "Sequência divergente.", {
        server_version: 7,
        last_seq_by_device: { "device-1": 12 },
        server_snapshot: { survey_id: "nao-e-um-pacote" },
      }),
    );
    const api = createSyncApi("https://api.croquito.test", fetch);

    const result = await api.completeSurvey({
      token: TOKEN,
      surveyId: SURVEY_ID,
      idempotencyKey: "k",
      baseVersion: 7,
    });

    expect(result.ok).toBe(false);
    if (result.ok) {
      return;
    }
    expect(result.failure.kind).toBe("conflict");
    if (result.failure.kind !== "conflict") {
      return;
    }
    expect(result.failure.transient).toBe(false);
    expect(result.failure.conflict.server_version).toBe(7);
    expect(result.failure.conflict.last_seq_by_device).toEqual({ "device-1": 12 });
    // Snapshot que não passa no guarda de forma do contrato não vira estado do servidor.
    expect(result.failure.conflict.server_snapshot).toBeNull();
  });

  it("401 é falta de autorização, não falha de rede", async () => {
    const { fetch } = stub(new Response(null, { status: 401 }));
    const api = createSyncApi("https://api.croquito.test", fetch);

    const result = await api.getSurveyState({ token: TOKEN, surveyId: SURVEY_ID });

    expect(result).toEqual({ ok: false, failure: { kind: "unauthorized", transient: false } });
  });

  it("levantamento inexistente no servidor não é erro", async () => {
    const { fetch } = stub(problem(404, "NOT_FOUND", "Levantamento não encontrado."));
    const api = createSyncApi("https://api.croquito.test", fetch);

    const result = await api.getSurveyState({ token: TOKEN, surveyId: SURVEY_ID });

    expect(result).toEqual({ ok: true, value: null });
  });

  it("5xx é transitório e 422 não é", async () => {
    const api503 = createSyncApi(
      "https://api.croquito.test",
      stub(problem(503, "PROCESSING_UNAVAILABLE", "Indisponível.")).fetch,
    );
    const api422 = createSyncApi(
      "https://api.croquito.test",
      stub(problem(422, "SURVEY_PACKET_INVALID", "Pacote inválido.")).fetch,
    );

    const transient = await api422.presignMedia({
      token: TOKEN,
      surveyId: SURVEY_ID,
      idempotencyKey: "k",
      sha256: "a".repeat(64),
      mimeType: "image/jpeg",
      byteSize: 10,
    });
    const unavailable = await api503.presignMedia({
      token: TOKEN,
      surveyId: SURVEY_ID,
      idempotencyKey: "k",
      sha256: "a".repeat(64),
      mimeType: "image/jpeg",
      byteSize: 10,
    });

    expect(transient.ok).toBe(false);
    expect(!transient.ok && transient.failure.transient).toBe(false);
    expect(!transient.ok && transient.failure.kind === "problem" && transient.failure.code).toBe(
      "SURVEY_PACKET_INVALID",
    );
    expect(!unavailable.ok && unavailable.failure.transient).toBe(true);
  });

  it("corpo fora do contrato vira falha declarada, não estado meio lido", async () => {
    const { fetch } = stub(new Response("<html>portal cativo</html>", { status: 200 }));
    const api = createSyncApi("https://api.croquito.test", fetch);

    const result = await api.submitOperations({
      token: TOKEN,
      surveyId: SURVEY_ID,
      batchId: "batch-1",
      body: {
        device_id: "device-1",
        survey: { survey_id: SURVEY_ID } as never,
        operations: [],
      },
    });

    expect(result.ok).toBe(false);
    expect(!result.ok && result.failure.kind).toBe("malformed");
  });
});
