import { describe, expect, it } from "vitest";

import { ApiError } from "../api";
import type { PlatformTenant } from "./api";
import {
  describeError,
  errorMessage,
  estadoLabel,
  formatarInstante,
  MENSAGEM_REDE,
} from "./labels";

function tenant(overrides: Partial<PlatformTenant> = {}): PlatformTenant {
  return {
    tenant_id: "acme",
    enabled: false,
    agreement_reference: null,
    authorized_at: null,
    revoked_at: null,
    ...overrides,
  };
}

describe("estadoLabel", () => {
  /**
   * O tenant nunca autorizado e o revogado chegam os dois com `enabled: false`; dizer
   * "inativo" para ambos esconderia do operador se houve ou não um ato antes.
   */
  it("separa nunca autorizado de revogado, que a API não distingue por enabled", () => {
    expect(estadoLabel(tenant())).toBe("nunca autorizado");
    expect(
      estadoLabel(
        tenant({
          authorized_at: "2026-08-19T12:00:00Z",
          revoked_at: "2026-08-19T18:00:00Z",
        }),
      ),
    ).toBe("revogado");
    expect(
      estadoLabel(tenant({ enabled: true, authorized_at: "2026-08-19T12:00:00Z" })),
    ).toBe("ativo");
  });
});

describe("formatarInstante", () => {
  it("marca a ausência de carimbo em vez de fabricar data", () => {
    expect(formatarInstante(null)).toBe("—");
  });

  it("devolve o texto original quando não é data reconhecível", () => {
    expect(formatarInstante("carimbo do servidor")).toBe("carimbo do servidor");
  });

  it("formata data e hora em pt-BR", () => {
    expect(formatarInstante("2026-03-02T15:30:00Z")).toMatch(
      /^0[12]\/03\/2026 \d{2}:\d{2}$/,
    );
  });
});

describe("describeError", () => {
  it("escolhe a frase pelo código estável", () => {
    const erro = new ApiError(
      "FORBIDDEN: Papel platform_operator é obrigatório.",
      403,
      "FORBIDDEN",
      "Papel platform_operator é obrigatório.",
      {},
    );

    expect(describeError(erro)).toBe(errorMessage("FORBIDDEN"));
    // O nome do papel não é jogado cru na tela; a frase explica o que fazer.
    expect(describeError(erro)).toContain("peça a quem opera a plataforma");
  });

  /**
   * Código novo no servidor não vira explicação inventada aqui: sobra a frase que o
   * transporte montou, que já carrega o código e o `detail` — inclusive a copy aprovada
   * do 401 sem tenant, que não pode ser reescrita por esta jornada.
   */
  it("preserva a mensagem do transporte quando o código é desconhecido", () => {
    const erro = new ApiError(
      "CODIGO_NOVO: alguma coisa aconteceu.",
      409,
      "CODIGO_NOVO",
      "alguma coisa aconteceu.",
      {},
    );

    expect(errorMessage("CODIGO_NOVO")).toBeNull();
    expect(describeError(erro)).toBe("CODIGO_NOVO: alguma coisa aconteceu.");
  });

  it("o que não chegou a ser resposta é dito como rede, sem stack na tela", () => {
    expect(describeError(new TypeError("fetch failed"))).toBe(MENSAGEM_REDE);
    expect(describeError("qualquer coisa")).toBe(MENSAGEM_REDE);
    expect(describeError(new TypeError("fetch failed"))).toContain(
      "Nada foi gravado",
    );
  });
});
