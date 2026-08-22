import { describe, expect, it } from "vitest";

import { ApiError } from "../api";
import type {
  JourneyAvailability,
  JourneyEntitlement,
  PlatformTenant,
  ReferenceCatalog,
} from "./api";
import {
  describeError,
  describeJourneyError,
  digestCurto,
  errorMessage,
  estadoDaAutorizacao,
  estadoLabel,
  ESTADO_JORNADA_CLASSE,
  ESTADO_JORNADA_LABEL,
  formatarContagem,
  formatarDataBase,
  formatarDia,
  formatarInstante,
  MENSAGEM_ACERVO_SEM_LEITURA,
  MENSAGEM_ACERVO_VAZIO,
  MENSAGEM_REDE,
  mensagemForaDoPiloto,
  mensagemSemAutorizacao,
  resumoDoAcervo,
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

/**
 * Acervo de catálogos de referência (F-037). Os formatadores só trocam pontuação: nenhum
 * deles soma, arredonda ou adivinha um valor que o servidor não mandou.
 */
describe("formatadores do acervo", () => {
  it("mostra a data-base como a obra a escreve", () => {
    expect(formatarDataBase("2026-07")).toBe("07/2026");
    expect(formatarDataBase("2026-04")).toBe("04/2026");
  });

  /** Texto fora da forma volta como veio: a data-base é lida do arquivo, não inventada. */
  it("não adivinha data-base fora da forma AAAA-MM", () => {
    expect(formatarDataBase("julho de 2026")).toBe("julho de 2026");
    expect(formatarDataBase("2026")).toBe("2026");
  });

  it("agrupa o milhar da contagem sem mexer no número", () => {
    expect(formatarContagem(4865)).toBe("4.865");
    expect(formatarContagem(865)).toBe("865");
    expect(formatarContagem(1234567)).toBe("1.234.567");
    expect(formatarContagem(0)).toBe("0");
  });

  it("mostra só o dia do carimbo, e travessão quando não houve ato", () => {
    expect(formatarDia("2026-08-22T09:14:00")).toBe("22/08/2026");
    expect(formatarDia(null)).toBe("—");
    expect(formatarDia("não é data")).toBe("não é data");
  });

  it("trunca o digest para conferência visual", () => {
    expect(digestCurto("6f314c9".padEnd(64, "0"))).toBe("6f314c900000");
    expect(digestCurto(null)).toBe("—");
  });
});

describe("resumoDoAcervo", () => {
  function catalogo(overrides: Partial<ReferenceCatalog> = {}): ReferenceCatalog {
    return {
      reference_catalog_id: "0198-aaa",
      display_name: "SCO-Rio FGV06 desonerado",
      origin: "sco",
      reference_month: "2026-07",
      entry_count: 4865,
      object_sha256: "a".repeat(64),
      source_sha256: "b".repeat(64),
      available: true,
      published_by: "daniel",
      published_at: "2026-08-22T09:14:00Z",
      withdrawn_at: null,
      ...overrides,
    };
  }

  it("distingue não ter lido de ter lido e não haver nada", () => {
    expect(resumoDoAcervo(null, false)).toBe(MENSAGEM_ACERVO_SEM_LEITURA);
    expect(resumoDoAcervo(null, true)).toContain("Lendo o acervo");
    expect(resumoDoAcervo([], false)).toBe(MENSAGEM_ACERVO_VAZIO);
  });

  /** O que saiu de circulação é contado à parte: ele continua no acervo, e não na oferta. */
  it("conta em circulação e fora de circulação separadamente", () => {
    expect(resumoDoAcervo([catalogo()], false)).toBe("1 tabela em circulação.");
    expect(
      resumoDoAcervo(
        [
          catalogo(),
          catalogo({ reference_catalog_id: "0198-bbb" }),
          catalogo({
            reference_catalog_id: "0198-ccc",
            available: false,
            withdrawn_at: "2026-08-22T10:00:00Z",
          }),
        ],
        false,
      ),
    ).toBe("2 tabelas em circulação · 1 fora de circulação.");
  });
});

describe("recusas do acervo em palavra", () => {
  /**
   * As duas entradas novas do mapa são a forma SEM o fato declarado pelo servidor. Elas
   * existem para que qualquer chamador do mapa comum tenha frase, e são a MESMA copy que
   * `describeAcervoError` monta quando o fato existe.
   */
  it("os códigos da T1 têm frase estável no mapa", () => {
    expect(errorMessage("REFERENCE_CATALOG_ALREADY_PUBLISHED")).toContain(
      "já está publicada",
    );
    expect(errorMessage("REFERENCE_CATALOG_ORIGIN_NOT_PUBLISHABLE")).toContain(
      "não distribui tabela desta origem",
    );
    expect(errorMessage("INVALID_UPLOAD")).toContain("Nada foi publicado");
    expect(errorMessage("DOMAIN_VALIDATION_FAILED")).toContain(
      "catálogo normalizado",
    );
    expect(errorMessage("LIMIT_EXCEEDED")).toContain("limite de leitura");
    expect(errorMessage("UPLOAD_TRANSFER_FAILED")).toContain(
      "não foi concluído",
    );
  });

  /** A regra da casa que a seção nova não afrouxa. */
  it("código de acervo desconhecido continua devolvendo null", () => {
    expect(errorMessage("REFERENCE_CATALOG_QUALQUER_COISA")).toBeNull();
  });
});
