import { describe, expect, it } from "vitest";

import { ApiError } from "../api";
import type {
  JourneyAvailability,
  JourneyEntitlement,
  PlatformTenant,
  ReferenceCatalog,
  ReferenceCatalogIndex,
} from "./api";
import {
  AVISO_INDICE_VEM_DO_CLI,
  AVISO_RETIRADA_INDICE,
  describeError,
  describeIndiceError,
  describeJourneyError,
  digestCurto,
  errorMessage,
  estadoDaAutorizacao,
  estadoDoIndice,
  estadoLabel,
  ESTADO_JORNADA_CLASSE,
  ESTADO_JORNADA_LABEL,
  formatarContagem,
  formatarDataBase,
  formatarDia,
  formatarInstante,
  MENSAGEM_ACERVO_SEM_LEITURA,
  MENSAGEM_ACERVO_VAZIO,
  MENSAGEM_INDICE_NAO_ENCONTRADO,
  MENSAGEM_INDICES_SEM_LEITURA,
  MENSAGEM_INDICES_VAZIO,
  MENSAGEM_REDE,
  mensagemForaDoPiloto,
  mensagemIndiceDeOutroCatalogo,
  mensagemIndiceGrandeDemais,
  mensagemSemAutorizacao,
  nomeDoCatalogoIndexado,
  resumoDoAcervo,
  resumoDoAmbiente,
  resumoDosIndices,
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

/**
 * Índice de embeddings (F-041, ADR-0054).
 *
 * O oráculo destas asserções é o que o SERVIDOR recusa — `reference_catalog_indexes.py` e
 * as quatro rotas de `main.py` —, não uma mensagem inventada aqui. Os quatro códigos novos
 * precisam ter frase estável: nenhum deles pode chegar cru à tela pelo caminho genérico.
 */
function catalogoDoAcervo(
  overrides: Partial<ReferenceCatalog> = {},
): ReferenceCatalog {
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

function indice(
  overrides: Partial<ReferenceCatalogIndex> = {},
): ReferenceCatalogIndex {
  return {
    reference_catalog_index_id: "0198-idx",
    reference_catalog_id: "0198-aaa",
    catalog_source_sha256: "a17b3e0".padEnd(64, "0"),
    text_recipe: "code-description-unit-v1",
    provider: "openai",
    model_id: "text-embedding-3-small",
    dims: 1536,
    code_count: 4964,
    object_sha256: "6f314c9".padEnd(64, "0"),
    available: true,
    published_by: "daniel",
    published_at: "2026-08-28T09:14:00Z",
    withdrawn_at: null,
    ...overrides,
  };
}

describe("recusas do índice em palavra", () => {
  /** Nenhum dos quatro cai no caminho genérico que mostraria o código cru. */
  it("os quatro códigos novos têm frase estável no mapa", () => {
    expect(errorMessage("REFERENCE_CATALOG_INDEX_TOO_LARGE")).toContain(
      "recusado por inteiro",
    );
    expect(errorMessage("REFERENCE_CATALOG_INDEX_UNREADABLE")).toContain(
      "não pôde ser lido",
    );
    expect(
      errorMessage("REFERENCE_CATALOG_INDEX_CATALOG_MISMATCH"),
    ).toContain("construído sobre outro catálogo");
    expect(
      errorMessage("REFERENCE_CATALOG_INDEX_ALREADY_PUBLISHED"),
    ).toContain("publicação é imutável");
  });

  /** Nenhuma das quatro frases devolve o código cru para a tela. */
  it("nenhuma das frases carrega o código de erro dentro dela", () => {
    for (const code of [
      "REFERENCE_CATALOG_INDEX_TOO_LARGE",
      "REFERENCE_CATALOG_INDEX_UNREADABLE",
      "REFERENCE_CATALOG_INDEX_CATALOG_MISMATCH",
      "REFERENCE_CATALOG_INDEX_ALREADY_PUBLISHED",
    ]) {
      expect(errorMessage(code)).not.toBeNull();
      expect(errorMessage(code)).not.toContain(code);
    }
  });

  /**
   * O teto vem do `details` do servidor (`max_bytes`), e não de um número copiado para a
   * tela: 64 MiB é decisão de `CATALOG_INDEX_MAX_BYTES`, e o dia em que ela mudar a frase
   * muda junto. Sem o fato, a frase segue verdadeira e não inventa teto nenhum.
   */
  it("a recusa por tamanho cita o teto que o servidor declarou", () => {
    const erro = new ApiError(
      "grande demais",
      422,
      "REFERENCE_CATALOG_INDEX_TOO_LARGE",
      "excede",
      { max_bytes: 64 * 1024 * 1024, size_bytes: 90_000_000 },
    );

    expect(describeIndiceError(erro)).toContain("64 MiB");
    expect(describeIndiceError(erro)).toContain("Nada foi publicado");
    expect(mensagemIndiceGrandeDemais(null)).not.toContain("MiB");
  });

  /**
   * O código de domínio que o servidor declara em `details.code` escolhe o complemento;
   * código que a tela não conhece não vira explicação inventada.
   */
  it("a recusa de leitura traduz o motivo de domínio declarado", () => {
    const invalido = new ApiError("ilegível", 422, "REFERENCE_CATALOG_INDEX_UNREADABLE", "", {
      code: "INDEX_PAYLOAD_INVALID",
    });
    const desconhecido = new ApiError(
      "ilegível",
      422,
      "REFERENCE_CATALOG_INDEX_UNREADABLE",
      "",
      { code: "INDEX_CODIGO_QUE_NAO_EXISTE" },
    );

    expect(describeIndiceError(invalido)).toContain("contrato do índice");
    expect(describeIndiceError(desconhecido)).toContain("não pôde ser lido");
    expect(describeIndiceError(desconhecido)).not.toContain(
      "INDEX_CODIGO_QUE_NAO_EXISTE",
    );
    // As duas mandam construir pelo CLI, porque é lá que o índice nasce (ADR-0054 D4).
    expect(describeIndiceError(invalido)).toContain("index-catalog");
  });

  /** Os dois digests vêm do servidor; sem eles a frase não inventa nenhum. */
  it("o índice de outro catálogo confronta os digests declarados", () => {
    const erro = new ApiError("outro catálogo", 422, "REFERENCE_CATALOG_INDEX_CATALOG_MISMATCH", "", {
      index_catalog_sha256: "aaaaaaaaaaaa".padEnd(64, "1"),
      catalog_source_sha256: "bbbbbbbbbbbb".padEnd(64, "2"),
    });

    expect(describeIndiceError(erro)).toContain("aaaaaaaaaaaa");
    expect(describeIndiceError(erro)).toContain("bbbbbbbbbbbb");
    expect(mensagemIndiceDeOutroCatalogo(null, null)).not.toContain("sha256");
  });

  /**
   * `NOT_FOUND` significa três coisas diferentes nesta jornada. Na seção de índices ele não
   * pode dizer "tenant nunca autorizado" nem "não está no acervo".
   */
  it("NOT_FOUND na seção de índices não mostra a frase da seção vizinha", () => {
    const erro = new ApiError("não achado", 404, "NOT_FOUND", "", {});

    expect(describeIndiceError(erro)).toBe(MENSAGEM_INDICE_NAO_ENCONTRADO);
    expect(describeIndiceError(erro)).not.toContain("autorização contratual");
    expect(describeIndiceError(erro)).not.toContain("não está no acervo");
  });
});

describe("estado e resumo dos índices", () => {
  /** Estado por extenso, nas duas pontas: cor nunca carrega isso sozinha. */
  it("escreve os dois estados de circulação", () => {
    expect(estadoDoIndice(indice())).toBe("em circulação");
    expect(
      estadoDoIndice(
        indice({ available: false, withdrawn_at: "2026-08-28T11:00:00Z" }),
      ),
    ).toBe("fora de circulação");
  });

  it("distingue não ter lido de ter lido e não haver nada", () => {
    expect(resumoDosIndices(null, false)).toBe(MENSAGEM_INDICES_SEM_LEITURA);
    expect(resumoDosIndices(null, true)).toContain("Lendo os índices");
    expect(resumoDosIndices([], false)).toBe(MENSAGEM_INDICES_VAZIO);
  });

  /** O que saiu de circulação continua na lista, e é contado à parte. */
  it("conta em circulação e fora de circulação separadamente", () => {
    expect(resumoDosIndices([indice()], false)).toBe("1 índice em circulação.");
    expect(
      resumoDosIndices(
        [
          indice(),
          indice({ reference_catalog_index_id: "0198-idy" }),
          indice({
            reference_catalog_index_id: "0198-idz",
            available: false,
            withdrawn_at: "2026-08-28T11:00:00Z",
          }),
        ],
        false,
      ),
    ).toBe("2 índices em circulação · 1 fora de circulação.");
  });

  /**
   * O nome da tabela vem do acervo lido ao lado. Sem ele, a frase cita o digest da FONTE,
   * que o próprio índice carrega — nome nenhum é adivinhado pelo identificador.
   */
  it("nomeia a tabela pelo acervo, e cai no digest da fonte quando ele não foi lido", () => {
    const acervo = [
      catalogoDoAcervo({
        reference_catalog_id: "0198-aaa",
        display_name: "SCO-Rio FGV06 desonerado",
      }),
    ];

    expect(nomeDoCatalogoIndexado(indice(), acervo)).toBe(
      "SCO-Rio FGV06 desonerado",
    );
    expect(nomeDoCatalogoIndexado(indice(), null)).toContain("sha256 a17b3e0");
    expect(
      nomeDoCatalogoIndexado(indice({ reference_catalog_id: "outro" }), acervo),
    ).toContain("sha256 a17b3e0");
  });
});

/**
 * O que a seção afirma sobre si mesma, fixado por teste porque as duas afirmações são
 * decisões escritas do ADR-0054 e não escolha de copy: o índice nasce no CLI (D4) e
 * retirar não apaga.
 */
describe("copy da administração de índices", () => {
  it("diz que o índice é construído pelo CLI, nunca pela tela", () => {
    expect(AVISO_INDICE_VEM_DO_CLI.comando).toBe("index-catalog");
    expect(AVISO_INDICE_VEM_DO_CLI.depois).toContain("nunca o constrói");
  });

  it("diz que retirar não apaga, e por que a shortlist gravada continua valendo", () => {
    expect(AVISO_RETIRADA_INDICE).toContain("Retirar não apaga");
    expect(AVISO_RETIRADA_INDICE).toContain("digest do índice que a produziu");
    expect(AVISO_RETIRADA_INDICE).toContain("braço léxico");
  });

  /** Sem índice a shortlist sai léxica, e isso é estado normal (D6), não falha. */
  it("a lista vazia declara a consequência sem chamá-la de erro", () => {
    expect(MENSAGEM_INDICES_VAZIO).toContain("estado normal");
  });
});
