import { describe, expect, it } from "vitest";

import { ApiError } from "../api";
import type {
  JourneyAvailability,
  JourneyEntitlement,
  PlatformTenant,
} from "./api";
import {
  describeError,
  describeJourneyError,
  errorMessage,
  estadoDaAutorizacao,
  estadoLabel,
  ESTADO_JORNADA_CLASSE,
  ESTADO_JORNADA_LABEL,
  formatarInstante,
  MENSAGEM_REDE,
  mensagemForaDoPiloto,
  mensagemSemAutorizacao,
  resumoDoAmbiente,
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

describe("rótulos da disponibilidade de jornada (F-034)", () => {
  const ambiente: JourneyAvailability[] = [
    { journey: "croqui", state: "disabled" },
    { journey: "medicao", state: "enabled" },
    { journey: "orcamento", state: "pilot" },
  ];

  function autorizacao(
    overrides: Partial<JourneyEntitlement> = {},
  ): JourneyEntitlement {
    return {
      tenant_id: "tenant-scalle",
      journey: "orcamento",
      enabled: true,
      agreement_reference: "contrato 05/2024 — aditivo 3",
      authorized_by: "daniel",
      authorized_at: "2026-08-22T09:14:00Z",
      revoked_at: null,
      ...overrides,
    };
  }

  it("escreve o estado do ambiente por extenso, e não só por cor", () => {
    expect(ESTADO_JORNADA_LABEL.enabled).toBe("LIBERADA");
    expect(ESTADO_JORNADA_LABEL.pilot).toBe("PILOTO");
    expect(ESTADO_JORNADA_LABEL.disabled).toBe("INDISPONÍVEL");
    // `neutral` é o único valor visual novo do pacote aprovado; os outros dois já existiam.
    expect(ESTADO_JORNADA_CLASSE.disabled).toBe("neutral");
    expect(ESTADO_JORNADA_CLASSE.enabled).toBe("ready");
    expect(ESTADO_JORNADA_CLASSE.pilot).toBe("blocked");
  });

  it("resume quantas jornadas existem e quantas estão em piloto", () => {
    expect(resumoDoAmbiente(ambiente)).toBe("3 jornadas · 1 em piloto");
    expect(resumoDoAmbiente([ambiente[0]])).toBe("1 jornada · 0 em piloto");
  });

  /** A lista vazia não some: ela nomeia a consequência de ninguém estar autorizado. */
  it("explica o vazio nomeando as jornadas em piloto", () => {
    expect(mensagemSemAutorizacao(ambiente)).toBe(
      "Nenhum cliente autorizado em jornada de piloto. Enquanto isso, a jornada " +
        "Orçamento não existe para nenhum tenant.",
    );
    expect(
      mensagemSemAutorizacao([
        { journey: "croqui", state: "pilot" },
        { journey: "medicao", state: "pilot" },
        { journey: "orcamento", state: "enabled" },
      ]),
    ).toContain("as jornadas Croqui e Medição não existe");
    expect(
      mensagemSemAutorizacao([{ journey: "croqui", state: "enabled" }]),
    ).toBe(
      "Nenhuma jornada está em piloto neste ambiente, então não há autorização a " +
        "conceder por aqui.",
    );
  });

  it("separa autorizado de revogado na linha da lista", () => {
    expect(estadoDaAutorizacao(autorizacao())).toBe(
      "Orçamento · piloto autorizado",
    );
    expect(
      estadoDaAutorizacao(
        autorizacao({ enabled: false, revoked_at: "2026-08-22T08:02:00Z" }),
      ),
    ).toBe("Orçamento · autorização revogada");
  });

  /**
   * A frase da recusa é a do pacote aprovado, por extenso, e muda com o estado: a jornada
   * liberada e a indisponível não são recusadas pelo mesmo motivo.
   */
  it("diz por extenso por que a jornada não aceita autorização", () => {
    expect(mensagemForaDoPiloto("medicao", "enabled")).toBe(
      "A jornada Medição não está em piloto neste ambiente: ela já existe para todos " +
        "os clientes, e autorizar um cliente nela não teria efeito.",
    );
    expect(mensagemForaDoPiloto("croqui", "disabled")).toBe(
      "A jornada Croqui não está em piloto neste ambiente: ela não existe aqui, e " +
        "autorizar um cliente nela não teria efeito.",
    );
  });

  describe("describeJourneyError", () => {
    function recusa(details: Record<string, unknown>): ApiError {
      return new ApiError(
        "JOURNEY_NOT_IN_PILOT: recusa crua",
        409,
        "JOURNEY_NOT_IN_PILOT",
        "recusa crua",
        details,
      );
    }

    /**
     * A jornada e o estado vêm do que o SERVIDOR declarou, não do que a tela achava que
     * sabia: a lista carregada pode estar velha, e a frase precisa descrever o que de fato
     * barrou o ato.
     */
    it("compõe a frase a partir dos fatos declarados na recusa", () => {
      expect(
        describeJourneyError(recusa({ journey: "medicao", state: "enabled" })),
      ).toBe(mensagemForaDoPiloto("medicao", "enabled"));
    });

    it("não inventa frase quando a recusa não declara jornada e estado", () => {
      expect(describeJourneyError(recusa({}))).toBe(
        "JOURNEY_NOT_IN_PILOT: recusa crua",
      );
      expect(describeJourneyError(recusa({ journey: "inventada", state: "x" }))).toBe(
        "JOURNEY_NOT_IN_PILOT: recusa crua",
      );
    });

    it("cai no caminho comum para os outros códigos e para falha de rede", () => {
      const forbidden = new ApiError("cru", 403, "FORBIDDEN", "cru", {});
      expect(describeJourneyError(forbidden)).toBe(describeError(forbidden));
      expect(describeJourneyError(new TypeError("fetch failed"))).toBe(
        MENSAGEM_REDE,
      );
    });
  });
});
