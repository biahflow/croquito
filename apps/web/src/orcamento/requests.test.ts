import { describe, expect, it } from "vitest";

import {
  bdiPercentError,
  buildEstimateBody,
  cascadeOrderBody,
  cascadeRemoveBody,
  codeClosureBody,
  codeDecisionBody,
  createEstimateBody,
  installCatalogBody,
  installReferenceCatalogBody,
  regimeBody,
  takeoffDecisionBody,
  targetBody,
  tetoAmountError,
  versionBody,
  worksiteKeyError,
} from "./requests";
import { formatDecimalText, formatMoneyText, parseDecimalInput } from "./format";

/**
 * Identidade e carimbo NUNCA viajam: `reviewer_id`, `reviewer_role`, `decided_at` e
 * `decision_id` são do servidor, e o `extra="forbid"` da rota recusaria o corpo que os
 * trouxesse. Mandá-los seria pedir para carimbar decisão em nome de outra pessoa.
 */
const CARIMBOS = ["reviewer_id", "reviewer_role", "decided_at", "decision_id"];

describe("corpos das mutações", () => {
  it("toda mutação cita base_version, e só isso quando não há mais nada", () => {
    expect(versionBody(4)).toEqual({ base_version: 4 });
    expect(installCatalogBody("upload-1", 4)).toEqual({
      upload_id: "upload-1",
      base_version: 4,
    });
  });

  /**
   * A rota aceita EXATAMENTE uma fonte, e o corpo com as duas recusa
   * `422 ESTIMATE_CATALOG_SOURCE_INVALID`. Dois construtores com um caminho cada tornam
   * esse corpo ambíguo inexpressável nesta tela — é isto que os dois casos abaixo fixam.
   */
  it("instalar do acervo cita a tabela escolhida, e nunca um arquivo", () => {
    const body = installReferenceCatalogBody("tabela-do-acervo-1", 4);

    expect(body).toEqual({
      reference_catalog_id: "tabela-do-acervo-1",
      base_version: 4,
    });
    expect(body).not.toHaveProperty("upload_id");
  });

  it("instalar a tabela própria continua citando só o upload", () => {
    expect(installCatalogBody("upload-1", 9)).not.toHaveProperty(
      "reference_catalog_id",
    );
  });

  it("abrir orçamento não leva catálogo, período nem contrato", () => {
    const body = createEstimateBody({
      worksiteKey: " praca-do-exemplo ",
      worksiteName: " Praça do Exemplo ",
      referenceLabel: " ORÇAMENTO-BASE 2026 ",
    });

    expect(body).toEqual({
      worksite_key: "praca-do-exemplo",
      worksite_name: "Praça do Exemplo",
      reference_label: "ORÇAMENTO-BASE 2026",
    });
  });

  it("campo opcional vazio é OMITIDO, nunca enviado como string vazia", () => {
    const body = createEstimateBody({
      worksiteKey: "praca-do-exemplo",
      worksiteName: "Praça do Exemplo",
      referenceLabel: "ORÇAMENTO-BASE 2026",
      address: "   ",
    });

    expect(body).not.toHaveProperty("address");
  });

  /**
   * Regime na abertura (ADR-0045; F-033, revisão 2): a rodada nasce declarada quando a
   * escolha foi feita, e o corpo carrega o único regime declarável.
   */
  it("abrir sob contrato leva o regime declarado no corpo", () => {
    const body = createEstimateBody({
      worksiteKey: "praca-do-exemplo",
      worksiteName: "Praça do Exemplo",
      referenceLabel: "ORÇAMENTO-BASE 2026",
      pricingRegime: "contracted_demand",
    });

    expect(body.pricing_regime).toBe("contracted_demand");
  });

  /**
   * Sem escolha, a chave não existe: ausência não é um valor, é a falta dele — e é da
   * ausência que o servidor lê a pré-licitação. Mandar `pre_bid` aqui pediria a recusa
   * `ESTIMATE_REGIME_IRREVERSIBLE` sobre uma rodada que sequer existe.
   */
  it("sem regime escolhido o corpo não carrega pricing_regime nenhum", () => {
    const body = createEstimateBody({
      worksiteKey: "praca-do-exemplo",
      worksiteName: "Praça do Exemplo",
      referenceLabel: "ORÇAMENTO-BASE 2026",
    });

    expect(body).not.toHaveProperty("pricing_regime");
    expect(JSON.stringify(body)).not.toContain("pre_bid");
  });

  it("a reordenação manda a lista completa, copiada e na ordem pedida", () => {
    const cascade = ["a".repeat(64), "b".repeat(64)];
    const body = cascadeOrderBody({ cascade, baseVersion: 5 });

    expect(body).toEqual({ base_version: 5, cascade });
    expect(body.cascade).not.toBe(cascade);
  });

  it("a remoção manda só o digest da fonte e base_version, nada mais", () => {
    const body = cascadeRemoveBody({
      sourceSha256: "a".repeat(64),
      baseVersion: 5,
    });

    expect(body).toEqual({ base_version: 5, source_sha256: "a".repeat(64) });
  });

  it("o lote de takeoff não carrega carimbo de identidade", () => {
    const body = takeoffDecisionBody({
      baseVersion: 3,
      decisions: [
        {
          itemId: "ti_af6f85a49ea0b93d",
          action: "confirm",
          quantity: "340.50",
          unit: "m2",
          note: "  ",
        },
      ],
    });

    expect(body).toEqual({
      base_version: 3,
      decisions: [
        {
          item_id: "ti_af6f85a49ea0b93d",
          action: "confirm",
          quantity: "340.50",
          unit: "m2",
        },
      ],
    });
    for (const carimbo of CARIMBOS) {
      expect(body).not.toHaveProperty(carimbo);
      for (const decisao of body.decisions as Record<string, unknown>[]) {
        expect(decisao).not.toHaveProperty(carimbo);
      }
    }
  });
});

/**
 * A diferença de contrato para a medição, e a razão do módulo existir separado: com mais
 * de uma tabela na cascata, confirmar um código é escolher de qual catálogo o preço sai.
 */
describe("decisão de código com a fonte citada", () => {
  it("a confirmação leva código E fonte", () => {
    expect(
      codeDecisionBody({
        itemId: "ti_af6f85a49ea0b93d",
        action: "confirm",
        baseVersion: 2,
        code: " 12.015.0030 ",
        catalogSha256: " " + "b".repeat(64) + " ",
      }),
    ).toEqual({
      base_version: 2,
      item_id: "ti_af6f85a49ea0b93d",
      action: "confirm",
      code: "12.015.0030",
      catalog_sha256: "b".repeat(64),
    });
  });

  it("a rejeição leva nota e recusa levar código ou fonte", () => {
    const body = codeDecisionBody({
      itemId: "ti_af6f85a49ea0b93d",
      action: "reject",
      baseVersion: 2,
      code: "12.015.0030",
      catalogSha256: "b".repeat(64),
      note: "nenhuma fonte da cascata precifica este item",
    });

    expect(body).toEqual({
      base_version: 2,
      item_id: "ti_af6f85a49ea0b93d",
      action: "reject",
      note: "nenhuma fonte da cascata precifica este item",
    });
  });
});

/**
 * O BDI é `ExactDecimal` no domínio (ADR-0038, decisão 2): ele viaja como TEXTO, e nenhum
 * dígito é acrescentado, removido ou arredondado no caminho.
 */
describe("BDI como string decimal", () => {
  it("aceita a notação pt-BR e a do servidor, preservando a escala escrita", () => {
    expect(buildEstimateBody("25,00", 8)).toEqual({
      base_version: 8,
      bdi_percent: "25.00",
    });
    expect(buildEstimateBody("25.00", 8)?.bdi_percent).toBe("25.00");
    expect(buildEstimateBody("25", 8)?.bdi_percent).toBe("25");
    expect(buildEstimateBody("1.234,5678", 8)?.bdi_percent).toBe("1234.5678");
  });

  it("o valor enviado é sempre uma string, nunca um number", () => {
    const body = buildEstimateBody("25,00", 8);

    expect(typeof body?.bdi_percent).toBe("string");
  });

  it("texto que não é decimal exato não vira corpo nenhum", () => {
    for (const invalido of ["25%", "vinte e cinco", "", "  ", "25,", "1,2,3", "-5"]) {
      expect(buildEstimateBody(invalido, 8)).toBeNull();
    }
  });

  it("a recusa explica a notação aceita antes da viagem", () => {
    expect(bdiPercentError("")).toContain("Informe o percentual");
    expect(bdiPercentError("25%")).toContain("25,00 ou 25.00");
    expect(bdiPercentError("25,00")).toBeNull();
    expect(bdiPercentError("0")).toBeNull();
  });
});

/**
 * Teto de verba (ADR-0040): campo vazio é "sem teto" e não pede justificativa; `0,00` é
 * recusado pela tela, porque **zero não é "sem teto"** e escolher por quem digitou seria
 * gravar uma ambiguidade.
 */
describe("teto de verba", () => {
  it("campo vazio serve: teto é opcional e sem teto nada muda", () => {
    expect(tetoAmountError("")).toBeNull();
    expect(tetoAmountError("   ")).toBeNull();
  });

  it("zero é recusado, e a recusa ensina qual é o caminho de não ter teto", () => {
    for (const zero of ["0", "0,00", "0.00", "0,000"]) {
      const erro = tetoAmountError(zero);
      expect(erro).toContain("maior que zero");
      expect(erro).toContain("deixe o campo vazio");
    }
  });

  it("texto que não é valor em reais é recusado com a notação aceita", () => {
    for (const invalido of [
      "oitenta e cinco mil",
      "R$ 85.000,00",
      "-1,00",
      "85,",
      "1,2,3",
    ]) {
      expect(tetoAmountError(invalido)).toContain("85.000,00 ou 85000.00");
    }
  });

  it("valor escrito nas três notações da jornada serve", () => {
    expect(tetoAmountError("85000.00")).toBeNull();
    expect(tetoAmountError("85000,00")).toBeNull();
    expect(tetoAmountError("85.000,00")).toBeNull();
  });

  it("o corpo do teto cita base_version e manda o valor em texto do servidor", () => {
    expect(targetBody(12, "85.000,00", " Relação de Praças 2026 · demanda 14 ")).toEqual({
      base_version: 12,
      target_amount: "85000.00",
      target_label: "Relação de Praças 2026 · demanda 14",
    });
  });

  it("rótulo vazio é OMITIDO, nunca gravado como rótulo em branco", () => {
    const body = targetBody(12, "85000.00", "   ");

    expect(body).toEqual({ base_version: 12, target_amount: "85000.00" });
    expect(body).not.toHaveProperty("target_label");
  });

  it("valor que a tela recusaria não vira viagem — zero incluído", () => {
    for (const invalido of ["", "0,00", "zero", "-1"]) {
      expect(targetBody(12, invalido)).toBeNull();
    }
  });

  it("abrir rodada sem teto manda o corpo de sempre, sem campo nenhum a mais", () => {
    const body = createEstimateBody({
      worksiteKey: "praca-do-exemplo",
      worksiteName: "Praça do Exemplo",
      referenceLabel: "ORÇAMENTO-BASE 2026",
      targetAmount: "  ",
      targetLabel: "Relação de Praças 2026 · demanda 14",
    });

    expect(body).not.toHaveProperty("target_amount");
    // Sem teto, o rótulo da demanda não tem o que rotular.
    expect(body).not.toHaveProperty("target_label");
  });

  it("abrir rodada com teto leva valor e rótulo em texto", () => {
    const body = createEstimateBody({
      worksiteKey: "praca-do-exemplo",
      worksiteName: "Praça do Exemplo",
      referenceLabel: "ORÇAMENTO-BASE 2026",
      targetAmount: "85.000,00",
      targetLabel: " Relação de Praças 2026 · demanda 14 ",
    });

    expect(body.target_amount).toBe("85000.00");
    expect(body.target_label).toBe("Relação de Praças 2026 · demanda 14");
  });

  it("teto inválido na abertura não escapa para o corpo", () => {
    const body = createEstimateBody({
      worksiteKey: "praca-do-exemplo",
      worksiteName: "Praça do Exemplo",
      referenceLabel: "ORÇAMENTO-BASE 2026",
      targetAmount: "0,00",
    });

    expect(body).not.toHaveProperty("target_amount");
  });
});

describe("chave da obra", () => {
  it("repete o padrão que o domínio exige, e explica o que ele aceita", () => {
    expect(worksiteKeyError("praca-do-exemplo")).toBeNull();
    expect(worksiteKeyError("")).toContain("Informe a chave");
    expect(worksiteKeyError("Praça")).toContain("minúsculas");
    expect(worksiteKeyError("ab")).toContain("minúsculas");
    expect(worksiteKeyError("-comeca-com-hifen")).toContain("minúsculas");
  });
});

/**
 * A tela não soma, não multiplica e não arredonda: o servidor manda `Decimal` como texto
 * e a formatação só troca a pontuação.
 */
describe("formatação pt-BR sem aritmética", () => {
  it("troca a pontuação sem mexer na escala escrita", () => {
    expect(formatDecimalText("73598.74")).toBe("73.598,74");
    expect(formatDecimalText("18.4")).toBe("18,4");
    expect(formatDecimalText("7")).toBe("7");
    expect(formatMoneyText("96.80")).toBe("R$ 96,80");
  });

  it("texto que não é decimal simples volta como veio", () => {
    expect(formatDecimalText("sem preço")).toBe("sem preço");
  });

  it("round-trip textual: o que a tela lê volta como o servidor escreveu", () => {
    for (const valor of ["25.00", "1234.5678", "0.01", "340.50"]) {
      expect(parseDecimalInput(formatDecimalText(valor))).toBe(valor);
    }
  });
});

/**
 * O corpo da declaração do regime (ADR-0045). Ele NÃO tem parâmetro de regime, e isso é a
 * decisão: só existe um valor declarável, e a volta para pré-licitação — que a fronteira
 * aceita no schema só para recusá-la — não é ato desta tela.
 */
describe("corpo do regime da rodada", () => {
  it("cita a versão base e declara o único regime gravável", () => {
    expect(regimeBody(7)).toEqual({
      base_version: 7,
      pricing_regime: "contracted_demand",
    });
  });

  it("não tem como exprimir a volta para pré-licitação", () => {
    expect(JSON.stringify(regimeBody(1))).not.toContain("pre_bid");
  });
});

describe("fechamento de pacote de serviços", () => {
  it("o fechamento fala do ELEMENTO: não leva código nem fonte", () => {
    expect(
      codeClosureBody({
        itemId: "ti_af6f85a49ea0b93d",
        baseVersion: 4,
      }),
    ).toEqual({
      base_version: 4,
      item_id: "ti_af6f85a49ea0b93d",
    });
  });

  it("a nota é opcional e viaja aparada quando existe", () => {
    expect(
      codeClosureBody({
        itemId: "ti_af6f85a49ea0b93d",
        baseVersion: 4,
        note: "  o alambrado é a estrutura mais a tela; não há terceiro serviço  ",
      }),
    ).toEqual({
      base_version: 4,
      item_id: "ti_af6f85a49ea0b93d",
      note: "o alambrado é a estrutura mais a tela; não há terceiro serviço",
    });
  });

  it("nota em branco é omitida, nunca enviada como string vazia", () => {
    const body = codeClosureBody({
      itemId: "ti_af6f85a49ea0b93d",
      baseVersion: 4,
      note: "   ",
    });

    expect(Object.keys(body)).not.toContain("note");
  });
});
