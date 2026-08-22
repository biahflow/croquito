/**
 * O oráculo destes testes é o que SAIU no `fetch`: caminho, método, corpo e cabeçalhos.
 * A jornada de plataforma grava autorização contratual, então o que viaja no `PUT` é o
 * registro do ato — e é ele que precisa estar fixado por teste, não a resposta simulada.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "../api";
import {
  entitlementBody,
  fetchMe,
  getEntitlement,
  journeyEntitlementBody,
  listJourneys,
  listTenants,
  setEntitlement,
  setJourneyEntitlement,
} from "./api";
import { describeError } from "./labels";

/** Base do build de teste: `VITE_API_BASE_URL` não é declarada neste ambiente. */
const BASE = "http://localhost:8000";
const TOKEN = "token-de-teste";

type Chamada = { url: string; init: RequestInit | undefined };

const chamadas: Chamada[] = [];

function ok(body: unknown = {}): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });
}

/** Envelope de erro da API: `{detail: {code, detail, details}}`, aninhado. */
function problema(status: number, code: string, detail: string): Response {
  return new Response(JSON.stringify({ detail: { code, detail } }), {
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

describe("leituras da plataforma", () => {
  it("perguntam quem é o principal sem chave de idempotência", async () => {
    stub(() => ok({ subject: "op", tenant_id: "acme", roles: ["platform_operator"] }));

    const me = await fetchMe(TOKEN);

    expect(me.roles).toEqual(["platform_operator"]);
    expect(chamadas[0].url).toBe(`${BASE}/v1/me`);
    expect(headersDaChamada().Authorization).toBe(`Bearer ${TOKEN}`);
    expect(headersDaChamada()).not.toHaveProperty("Idempotency-Key");
  });

  it("desembrulham a lista de tenants na coleção que a tela percorre", async () => {
    stub(() =>
      ok({
        tenants: [
          {
            tenant_id: "acme",
            enabled: true,
            agreement_reference: "contrato 05/2024",
            authorized_at: "2026-08-19T12:00:00Z",
            revoked_at: null,
          },
        ],
      }),
    );

    const tenants = await listTenants(TOKEN);

    expect(chamadas[0].url).toBe(`${BASE}/v1/platform/tenants`);
    expect(tenants).toHaveLength(1);
    expect(tenants[0].tenant_id).toBe("acme");
  });

  it("leem o estado de um tenant pelo identificador, escapado no caminho", async () => {
    await getEntitlement(TOKEN, "tenant com espaço");

    expect(chamadas[0].url).toBe(
      `${BASE}/v1/platform/tenants/tenant%20com%20espa%C3%A7o/ai-processing-entitlement`,
    );
    expect(chamadas[0].init?.method).toBeUndefined();
  });
});

describe("mutação do entitlement", () => {
  it("ativa com PUT, referência do contrato e Idempotency-Key", async () => {
    await setEntitlement(TOKEN, {
      tenantId: "acme",
      enabled: true,
      agreementReference: "contrato 05/2024",
    });

    expect(chamadas[0].url).toBe(
      `${BASE}/v1/platform/tenants/acme/ai-processing-entitlement`,
    );
    expect(chamadas[0].init?.method).toBe("PUT");
    expect(headersDaChamada()["Content-Type"]).toBe("application/json");
    expect(headersDaChamada()["Idempotency-Key"]).toMatch(/^[0-9a-f-]{36}$/i);
    expect(corpoDaChamada()).toEqual({
      enabled: true,
      agreement_reference: "contrato 05/2024",
    });
  });

  it("dá uma chave de idempotência NOVA a cada gesto", async () => {
    await setEntitlement(TOKEN, {
      tenantId: "acme",
      enabled: true,
      agreementReference: "contrato 05/2024",
    });
    await setEntitlement(TOKEN, {
      tenantId: "acme",
      enabled: true,
      agreementReference: "contrato 05/2024",
    });

    expect(headersDaChamada(0)["Idempotency-Key"]).not.toBe(
      headersDaChamada(1)["Idempotency-Key"],
    );
  });

  it("revoga sem reescrever a referência do contrato que autorizou", async () => {
    await setEntitlement(TOKEN, {
      tenantId: "acme",
      enabled: false,
      agreementReference: "algo digitado na tela",
    });

    expect(corpoDaChamada()).toEqual({ enabled: false });
  });
});

describe("entitlementBody", () => {
  it("tira espaço das pontas da referência", () => {
    expect(
      entitlementBody({
        tenantId: "acme",
        enabled: true,
        agreementReference: "  contrato 05/2024  ",
      }),
    ).toEqual({ enabled: true, agreement_reference: "contrato 05/2024" });
  });

  /**
   * Referência vazia não vira string vazia no corpo: ela simplesmente não vai, e o
   * servidor recusa com `AGREEMENT_REFERENCE_REQUIRED`. Quem decide se o ato é válido é
   * a regra do backend, e a tela mostra a frase dessa recusa.
   */
  it("não inventa referência quando o campo está vazio", () => {
    expect(
      entitlementBody({ tenantId: "acme", enabled: true, agreementReference: "   " }),
    ).toEqual({ enabled: true });
    expect(entitlementBody({ tenantId: "acme", enabled: true })).toEqual({
      enabled: true,
    });
  });
});

describe("recusas legíveis", () => {
  it("o 403 sem papel vira frase, não código cru", async () => {
    stub(() =>
      problema(403, "FORBIDDEN", "Papel platform_operator é obrigatório."),
    );

    const erro = await listTenants(TOKEN).catch((e: unknown) => e);

    expect(erro).toBeInstanceOf(ApiError);
    expect((erro as ApiError).status).toBe(403);
    expect(describeError(erro)).toContain("papel de operador de plataforma");
    expect(describeError(erro)).toContain("Nada foi alterado");
  });

  it("ativar sem referência devolve a frase da regra que recusou", async () => {
    stub(() =>
      problema(
        422,
        "AGREEMENT_REFERENCE_REQUIRED",
        "Ativar processamento por IA exige a referência lógica do contrato.",
      ),
    );

    const erro = await setEntitlement(TOKEN, {
      tenantId: "acme",
      enabled: true,
    }).catch((e: unknown) => e);

    expect(describeError(erro)).toContain("referência do contrato");
    expect(describeError(erro)).toContain("Nada foi gravado");
  });

  it("revogar tenant nunca autorizado é dito como tal", async () => {
    stub(() => problema(404, "NOT_FOUND", "Autorização contratual não encontrada."));

    const erro = await setEntitlement(TOKEN, {
      tenantId: "acme",
      enabled: false,
    }).catch((e: unknown) => e);

    expect(describeError(erro)).toContain("nunca teve autorização contratual");
  });
});

describe("disponibilidade de jornada (F-034)", () => {
  it("lê o ambiente e as autorizações numa chamada só, sem chave de idempotência", async () => {
    stub(() =>
      ok({
        journeys: [
          { journey: "croqui", state: "disabled" },
          { journey: "medicao", state: "enabled" },
          { journey: "orcamento", state: "pilot" },
        ],
        entitlements: [
          {
            tenant_id: "tenant-scalle",
            journey: "orcamento",
            enabled: true,
            agreement_reference: "contrato 05/2024 — aditivo 3",
            authorized_by: "daniel",
            authorized_at: "2026-08-22T09:14:00Z",
            revoked_at: null,
          },
        ],
      }),
    );

    const resposta = await listJourneys(TOKEN);

    expect(chamadas[0].url).toBe(`${BASE}/v1/platform/journeys`);
    expect(chamadas[0].init?.method).toBeUndefined();
    expect(headersDaChamada()).not.toHaveProperty("Idempotency-Key");
    expect(resposta.journeys).toHaveLength(3);
    expect(resposta.entitlements[0].authorized_by).toBe("daniel");
  });

  it("autoriza no par (tenant, jornada) da URL, com contrato e chave por gesto", async () => {
    await setJourneyEntitlement(TOKEN, {
      tenantId: "tenant com espaço",
      journey: "orcamento",
      enabled: true,
      agreementReference: "  contrato 05/2024  ",
    });

    expect(chamadas[0].url).toBe(
      `${BASE}/v1/platform/tenants/tenant%20com%20espa%C3%A7o/journey-entitlements/orcamento`,
    );
    expect(chamadas[0].init?.method).toBe("PUT");
    expect(headersDaChamada()).toHaveProperty("Idempotency-Key");
    // A referência viaja sem espaço nas pontas; o par nunca vai no corpo.
    expect(corpoDaChamada()).toEqual({
      enabled: true,
      agreement_reference: "contrato 05/2024",
    });
  });

  /**
   * Revogar NÃO reescreve o contrato: o que autorizou continua sendo o que está gravado, e
   * mandar o que estava na tela apagaria o registro do ato original.
   */
  it("revoga sem mandar referência de contrato, mesmo com uma preenchida", () => {
    expect(
      journeyEntitlementBody({
        tenantId: "acme",
        journey: "croqui",
        enabled: false,
        agreementReference: "contrato 05/2024",
      }),
    ).toEqual({ enabled: false });
  });

  /**
   * Referência vazia não vira `agreement_reference: ""`: ela some do corpo e a recusa vem
   * do servidor com o código estável, como no entitlement de IA.
   */
  it("não inventa referência vazia ao autorizar", () => {
    expect(
      journeyEntitlementBody({
        tenantId: "acme",
        journey: "croqui",
        enabled: true,
        agreementReference: "   ",
      }),
    ).toEqual({ enabled: true });
  });
});
