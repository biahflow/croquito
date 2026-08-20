import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "../api";
import {
  associatePlate,
  createEstimate,
  createPlateExtraction,
  getCodes,
  getEstimate,
  getEstimateState,
  getSuggestions,
  getTakeoff,
  getTakeoffOverlay,
  installCatalog,
  listEstimates,
  postBuildEstimate,
  postCodeDecision,
  postSuggestionsRecompute,
  postTakeoffDecision,
  reorderCascade,
  searchCascade,
} from "./api";
import { describeError, isRevisionConflict, orcamentoErrorCode } from "./errors";

/** Base do build de teste: `VITE_API_BASE_URL` não é declarada neste ambiente. */
const BASE = "http://localhost:8000";
const TOKEN = "token-de-teste";
const ROUND = "0197f2a0-0000-7000-8000-000000000009";
const SCO = "a".repeat(64);
const EMOP = "b".repeat(64);

type Chamada = { url: string; init: RequestInit | undefined };

const chamadas: Chamada[] = [];

/** Resposta JSON qualquer; o corpo importa pouco — o oráculo é o que SAIU no `fetch`. */
function ok(body: unknown = {}): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });
}

/** Envelope de erro da API: `{detail: {code, detail, details}}`, aninhado. */
function problema(
  status: number,
  code: string,
  detail: string,
  details: Record<string, unknown> = {},
): Response {
  return new Response(JSON.stringify({ detail: { code, detail, details } }), {
    status,
    headers: { "Content-Type": "application/problem+json" },
  });
}

function stub(responder: (call: Chamada) => Response): void {
  vi.stubGlobal("fetch", (url: string, init?: RequestInit) => {
    const call = { url, init };
    chamadas.push(call);
    return Promise.resolve(responder(call));
  });
}

function headersDaChamada(indice = 0): Record<string, string> {
  return (chamadas[indice]?.init?.headers ?? {}) as Record<string, string>;
}

function corpoDaChamada(indice = 0): Record<string, unknown> {
  return JSON.parse(String(chamadas[indice]?.init?.body ?? "{}"));
}

beforeEach(() => {
  chamadas.length = 0;
  stub(() => ok());
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("leituras do orçamento", () => {
  it("citam a rodada no caminho e levam o Bearer da sessão, sem chave de idempotência", async () => {
    await getEstimateState(TOKEN, ROUND);

    expect(chamadas).toHaveLength(1);
    expect(chamadas[0].url).toBe(`${BASE}/v1/estimate-rounds/${ROUND}`);
    expect(headersDaChamada().Authorization).toBe(`Bearer ${TOKEN}`);
    expect(headersDaChamada()).not.toHaveProperty("Idempotency-Key");
  });

  it("cada etapa lê o caminho dela, sempre sob a rodada de orçamento", async () => {
    await getTakeoff(TOKEN, ROUND);
    await getTakeoffOverlay(TOKEN, ROUND);
    await getSuggestions(TOKEN, ROUND);
    await getCodes(TOKEN, ROUND);
    await getEstimate(TOKEN, ROUND);

    expect(chamadas.map((call) => call.url)).toEqual([
      `${BASE}/v1/estimate-rounds/${ROUND}/takeoff`,
      `${BASE}/v1/estimate-rounds/${ROUND}/takeoff/overlay`,
      `${BASE}/v1/estimate-rounds/${ROUND}/code-suggestions`,
      `${BASE}/v1/estimate-rounds/${ROUND}/code-assignments`,
      `${BASE}/v1/estimate-rounds/${ROUND}/estimate`,
    ]);
    // Nenhuma rota da medição é chamada por engano: as jornadas não se cruzam.
    expect(chamadas.every((call) => !call.url.includes("valuation-rounds"))).toBe(
      true,
    );
  });

  it("a listagem passa o cursor opaco como veio", async () => {
    await listEstimates(TOKEN, { cursor: "Y3Vyc29y", limit: 5 });

    expect(chamadas[0].url).toBe(
      `${BASE}/v1/estimate-rounds?limit=5&cursor=Y3Vyc29y`,
    );
  });

  /**
   * A rota do orçamento NÃO expõe `arm`: o braço híbrido depende de índice de embeddings
   * que nenhuma rota de `/v1` publica, e mandar o parâmetro inventaria contrato.
   */
  it("a busca na cascata não manda braço nenhum", async () => {
    await searchCascade(TOKEN, ROUND, "piso intertravado", 5);

    expect(chamadas[0].url).toBe(
      `${BASE}/v1/estimate-rounds/${ROUND}/catalog/search?q=piso+intertravado&limit=5`,
    );
    expect(chamadas[0].url).not.toContain("arm=");
  });
});

describe("mutações do orçamento", () => {
  it("abrir orçamento não manda catálogo nem período, e manda Idempotency-Key", async () => {
    await createEstimate(TOKEN, {
      worksiteKey: "praca-do-exemplo",
      worksiteName: "Praça do Exemplo",
      referenceLabel: "ORÇAMENTO-BASE 2026",
      address: "  Rua Sintética, s/n  ",
    });

    expect(chamadas[0].url).toBe(`${BASE}/v1/estimate-rounds`);
    expect(headersDaChamada()["Idempotency-Key"]).toMatch(/^[0-9a-f-]{36}$/);
    expect(corpoDaChamada()).toEqual({
      worksite_key: "praca-do-exemplo",
      worksite_name: "Praça do Exemplo",
      reference_label: "ORÇAMENTO-BASE 2026",
      address: "Rua Sintética, s/n",
    });
    expect(corpoDaChamada()).not.toHaveProperty("catalog_upload_id");
    expect(corpoDaChamada()).not.toHaveProperty("period_number");
    expect(corpoDaChamada()).not.toHaveProperty("contract_label");
  });

  it("instalar catálogo cita base_version e o upload, e nada mais", async () => {
    await installCatalog(TOKEN, ROUND, "upload-1", 3);

    expect(chamadas[0].url).toBe(`${BASE}/v1/estimate-rounds/${ROUND}/catalogs`);
    expect(corpoDaChamada()).toEqual({ upload_id: "upload-1", base_version: 3 });
  });

  /** A reordenação é a permutação COMPLETA: corpo parcial faria o servidor escolher. */
  it("reordenar manda a cascata inteira, na ordem nova", async () => {
    await reorderCascade(TOKEN, ROUND, { cascade: [EMOP, SCO], baseVersion: 7 });

    expect(chamadas[0].url).toBe(
      `${BASE}/v1/estimate-rounds/${ROUND}/catalogs/order`,
    );
    expect(corpoDaChamada()).toEqual({ base_version: 7, cascade: [EMOP, SCO] });
  });

  it("a decisão de takeoff cita base_version e não carimba identidade", async () => {
    await postTakeoffDecision(TOKEN, ROUND, {
      itemId: "ti_af6f85a49ea0b93d",
      action: "confirm",
      baseVersion: 7,
      quantity: "340.50",
      note: "quantidade lida na prancha",
    });

    expect(chamadas[0].url).toBe(
      `${BASE}/v1/estimate-rounds/${ROUND}/takeoff/decisions`,
    );
    const corpo = corpoDaChamada();
    expect(corpo.base_version).toBe(7);
    expect(corpo.quantity).toBe("340.50");
    for (const proibido of [
      "reviewer_id",
      "reviewer_role",
      "decided_at",
      "decision_id",
    ]) {
      expect(corpo).not.toHaveProperty(proibido);
    }
  });

  /**
   * A diferença que dá nome ao módulo: confirmar um código é escolher de QUAL catálogo
   * aquele preço sai. A citação viaja na decisão, não só no relatório.
   */
  it("a confirmação de código cita a fonte de preço", async () => {
    await postCodeDecision(TOKEN, ROUND, {
      itemId: "ti_af6f85a49ea0b93d",
      action: "confirm",
      baseVersion: 4,
      code: "12.015.0030",
      catalogSha256: EMOP,
    });

    expect(chamadas[0].url).toBe(
      `${BASE}/v1/estimate-rounds/${ROUND}/code-assignments/decisions`,
    );
    expect(corpoDaChamada()).toEqual({
      base_version: 4,
      item_id: "ti_af6f85a49ea0b93d",
      action: "confirm",
      code: "12.015.0030",
      catalog_sha256: EMOP,
    });
  });

  /** Rejeitar é recusar TODAS as fontes, não uma delas: a rejeição não cita catálogo. */
  it("a rejeição leva nota e não leva código nem fonte", async () => {
    await postCodeDecision(TOKEN, ROUND, {
      itemId: "ti_af6f85a49ea0b93d",
      action: "reject",
      baseVersion: 4,
      code: "12.015.0030",
      catalogSha256: EMOP,
      note: "mobiliário fora do escopo desta praça",
    });

    const corpo = corpoDaChamada();
    expect(corpo.note).toBe("mobiliário fora do escopo desta praça");
    expect(corpo).not.toHaveProperty("code");
    expect(corpo).not.toHaveProperty("catalog_sha256");
  });

  it("o recompute da shortlist é ato humano e cita base_version", async () => {
    await postSuggestionsRecompute(TOKEN, ROUND, 9);

    expect(chamadas[0].url).toBe(
      `${BASE}/v1/estimate-rounds/${ROUND}/code-suggestions/recompute`,
    );
    expect(corpoDaChamada()).toEqual({ base_version: 9 });
  });

  it("a prancha e a extração citam base_version, cada uma no caminho dela", async () => {
    await associatePlate(TOKEN, ROUND, "upload-2", 2);
    await createPlateExtraction(TOKEN, ROUND, 3);

    expect(chamadas.map((call) => call.url)).toEqual([
      `${BASE}/v1/estimate-rounds/${ROUND}/plate`,
      `${BASE}/v1/estimate-rounds/${ROUND}/plate/extractions`,
    ]);
    expect(corpoDaChamada(0)).toEqual({ upload_id: "upload-2", base_version: 2 });
    expect(corpoDaChamada(1)).toEqual({ base_version: 3 });
  });
});

/**
 * O BDI é `ExactDecimal` no domínio (ADR-0038, decisão 2): ele viaja como TEXTO, porque
 * um número de JSON já teria passado por binário antes de chegar à rota.
 */
describe("BDI da montagem", () => {
  it("sai como string decimal, na forma que o servidor lê", async () => {
    await postBuildEstimate(TOKEN, ROUND, "25,00", 11);

    expect(chamadas[0].url).toBe(`${BASE}/v1/estimate-rounds/${ROUND}/estimate`);
    const corpo = corpoDaChamada();
    expect(corpo).toEqual({ base_version: 11, bdi_percent: "25.00" });
    expect(typeof corpo.bdi_percent).toBe("string");
  });

  it("nenhuma casa decimal é acrescentada nem removida", async () => {
    await postBuildEstimate(TOKEN, ROUND, "25", 11);
    expect(corpoDaChamada(0).bdi_percent).toBe("25");

    chamadas.length = 0;
    await postBuildEstimate(TOKEN, ROUND, "1.234,5678", 11);
    expect(corpoDaChamada(0).bdi_percent).toBe("1234.5678");
  });

  it("texto que não é decimal exato não chega a viajar", async () => {
    await expect(postBuildEstimate(TOKEN, ROUND, "25%", 11)).rejects.toBeInstanceOf(
      ApiError,
    );

    expect(chamadas).toHaveLength(0);
  });
});

describe("recusas traduzidas", () => {
  it("o 409 da rodada é o convite a recarregar, não falha do ato", async () => {
    stub(() =>
      problema(409, "REVISION_CONFLICT", "a rodada mudou depois da leitura", {
        base_version: 3,
        current_version: 4,
      }),
    );

    await installCatalog(TOKEN, ROUND, "upload-1", 3).catch((error: unknown) => {
      expect(isRevisionConflict(error)).toBe(true);
      expect(describeError(error)).toContain("recarregue o estado atual");
    });
    expect.assertions(2);
  });

  /** Origem repetida na cascata é recusa de DOMÍNIO com frase própria, por tabela. */
  it("origem repetida na cascata sai como a frase da cascata", async () => {
    stub(() =>
      problema(
        409,
        "ESTIMATE_CASCADE_ORIGIN_DUPLICATE",
        "a cascata já tem um catálogo desta origem",
        { origin: "emop" },
      ),
    );

    await installCatalog(TOKEN, ROUND, "upload-1", 3).catch((error: unknown) => {
      expect(describeError(error)).toContain("Cada origem entra uma vez só");
      expect(error).toBeInstanceOf(ApiError);
      expect(orcamentoErrorCode(error as ApiError)).toBe(
        "ESTIMATE_CASCADE_ORIGIN_DUPLICATE",
      );
    });
    expect.assertions(3);
  });

  /**
   * Invariante de `packages/valuation` viaja DENTRO de `DOMAIN_VALIDATION_FAILED`, em
   * `details.code`: é ela, e não o código da API, que escolhe a frase.
   */
  it("o código do domínio ganha do código da API na escolha da frase", async () => {
    stub(() =>
      problema(422, "DOMAIN_VALIDATION_FAILED", "orçamento recusado", {
        code: "ESTIMATE_LINE_SOURCE_UNKNOWN",
      }),
    );

    await postBuildEstimate(TOKEN, ROUND, "25.00", 11).catch((error: unknown) => {
      expect(error).toBeInstanceOf(ApiError);
      expect(orcamentoErrorCode(error as ApiError)).toBe(
        "ESTIMATE_LINE_SOURCE_UNKNOWN",
      );
      expect(describeError(error)).toContain("não está na cascata");
    });
    expect.assertions(3);
  });
});
