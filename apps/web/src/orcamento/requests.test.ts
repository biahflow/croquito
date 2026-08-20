import { describe, expect, it } from "vitest";

import {
  bdiPercentError,
  buildEstimateBody,
  cascadeOrderBody,
  codeDecisionBody,
  createEstimateBody,
  installCatalogBody,
  takeoffDecisionBody,
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

  it("a reordenação manda a lista completa, copiada e na ordem pedida", () => {
    const cascade = ["a".repeat(64), "b".repeat(64)];
    const body = cascadeOrderBody({ cascade, baseVersion: 5 });

    expect(body).toEqual({ base_version: 5, cascade });
    expect(body.cascade).not.toBe(cascade);
  });

  it("a decisão de takeoff não carrega carimbo de identidade", () => {
    const body = takeoffDecisionBody({
      itemId: "ti_af6f85a49ea0b93d",
      action: "confirm",
      baseVersion: 3,
      quantity: "340.50",
      unit: "m2",
      note: "  ",
    });

    expect(body).toEqual({
      base_version: 3,
      item_id: "ti_af6f85a49ea0b93d",
      action: "confirm",
      quantity: "340.50",
      unit: "m2",
    });
    for (const carimbo of CARIMBOS) {
      expect(body).not.toHaveProperty(carimbo);
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
