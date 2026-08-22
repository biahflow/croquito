/**
 * O 401 da API tem duas naturezas e o cliente precisa tratá-las diferente: token vencido
 * se resolve renovando; conta sem tenant NÃO — renovar só dispara a cascata do iframe
 * para chegar ao mesmo 401 (incidente de 2026-08-19). Estes testes fixam a bifurcação e
 * a copy aprovada da explicação.
 */
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("./auth", () => ({
  renewAccessToken: vi.fn(async () => "token-renovado"),
  readLastRenewFailure: vi.fn(() => null),
}));

import {
  ApiError,
  apiJson,
  submitReviewDecisions,
  submitReviewRectification,
} from "./api";
import type { ReviewDecision, ReviewRectification } from "./api";
import { renewAccessToken } from "./auth";

function resposta401(code: string): Response {
  return new Response(JSON.stringify({ detail: { code, detail: null } }), {
    status: 401,
    headers: { "Content-Type": "application/json" },
  });
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.clearAllMocks();
});

describe("apiJson e o 401", () => {
  it("conta sem tenant não tenta renovar e explica em vez de expor código cru", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => resposta401("TOKEN_WITHOUT_TENANT")),
    );

    const erro = await apiJson("/v1/projects", "token-atual").catch(
      (e: unknown) => e,
    );

    expect(erro).toBeInstanceOf(ApiError);
    expect((erro as ApiError).code).toBe("TOKEN_WITHOUT_TENANT");
    expect((erro as ApiError).message).toContain(
      "não está vinculada a uma organização",
    );
    expect((erro as ApiError).message).toContain("entrar de novo não muda");
    expect(renewAccessToken).not.toHaveBeenCalled();
  });

  it("token vencido renova uma vez e repete a chamada com o token novo", async () => {
    const tokens: string[] = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(async (_url: string, init?: RequestInit) => {
        const auth = (init?.headers as Record<string, string>).Authorization;
        tokens.push(auth);
        return auth === "Bearer token-renovado"
          ? new Response(JSON.stringify({ ok: true }), { status: 200 })
          : resposta401("INVALID_TOKEN");
      }),
    );

    const corpo = await apiJson<{ ok: boolean }>("/v1/projects", "token-vencido");

    expect(corpo).toEqual({ ok: true });
    expect(renewAccessToken).toHaveBeenCalledTimes(1);
    expect(tokens).toEqual(["Bearer token-vencido", "Bearer token-renovado"]);
  });
});

/**
 * Touch time (F-031 T4): o transporte carrega a medida quando ela existe e OMITE a
 * chave quando não existe. Ausente quer dizer "não medido" — publicar `null` afirmaria
 * que alguém mediu zero, que é diferente.
 */
describe("touch time no envio da revisão", () => {
  const decisao: ReviewDecision = {
    reading_id: "rd_1111111111111111",
    action: "confirm",
    justification: "Conferido na evidência protegida.",
    association_proposal_id: "vp_1111111111111111",
  };
  const correcao: ReviewRectification = {
    reading_id: "rd_1111111111111111",
    action: "confirm",
    rectifies_decision_id: "hd_1111111111111111",
    justification: "A cota foi transcrita errada; conferida de novo na folha.",
    association_proposal_id: "vp_1111111111111111",
  };

  function capturaCorpo(): { corpos: Record<string, unknown>[] } {
    const corpos: Record<string, unknown>[] = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(async (_url: string, init?: RequestInit) => {
        corpos.push(JSON.parse(String(init?.body)) as Record<string, unknown>);
        return new Response(JSON.stringify({ version: 2 }), { status: 200 });
      }),
    );
    return { corpos };
  }

  it("decisões enviam o acumulado medido, arredondado em milissegundos", async () => {
    const { corpos } = capturaCorpo();

    await submitReviewDecisions("token", "job-1", 1, [decisao], 4_200.6);

    expect(corpos[0].interaction_ms).toBe(4_201);
    expect(corpos[0].base_version).toBe(1);
  });

  it("correção declarada envia a medida do próprio ato", async () => {
    const { corpos } = capturaCorpo();

    await submitReviewRectification("token", "job-1", 2, correcao, 3_000);

    expect(corpos[0].interaction_ms).toBe(3_000);
  });

  it("sem medida, a chave não viaja — nem como null", async () => {
    const { corpos } = capturaCorpo();

    await submitReviewDecisions("token", "job-1", 1, [decisao]);
    await submitReviewDecisions("token", "job-1", 1, [decisao], null);
    await submitReviewRectification("token", "job-1", 2, correcao);

    expect(corpos.every((corpo) => !("interaction_ms" in corpo))).toBe(true);
  });

  it("medida implausível não viaja e o envio continua acontecendo", async () => {
    const { corpos } = capturaCorpo();

    await submitReviewDecisions("token", "job-1", 1, [decisao], -5);
    await submitReviewDecisions("token", "job-1", 1, [decisao], Number.NaN);

    expect(corpos).toHaveLength(2);
    expect(corpos.every((corpo) => !("interaction_ms" in corpo))).toBe(true);
  });
});
