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

import { ApiError, apiJson } from "./api";
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
