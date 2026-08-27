import { describe, expect, it } from "vitest";

import type { PriceAdjustmentDraft } from "./api";
import { DICA_FATOR, REAJUSTE_OPCOES, fatorEhLegivel, reajusteIssue } from "./reajuste";

const POR_INDICE: PriceAdjustmentDraft = {
  kind: "index_factor",
  referencePeriod: "08/2025 a 07/2026",
  indexLabel: "INCC-DI",
  factor: "1,0432",
};

describe("reajusteIssue", () => {
  it("não declarar é o caminho normal, e não é problema", () => {
    expect(reajusteIssue(null)).toBeNull();
  });

  it("declaração completa por índice pode ser enviada", () => {
    expect(reajusteIssue(POR_INDICE)).toBeNull();
  });

  it("fator sem índice recusa antes da rede, com o porquê", () => {
    const issue = reajusteIssue({ ...POR_INDICE, indexLabel: "  " });

    expect(issue).toContain("não é conferível");
    expect(issue).toContain("publicação oficial");
  });

  it("período de referência é exigido nos dois mecanismos", () => {
    expect(reajusteIssue({ ...POR_INDICE, referencePeriod: " " })).toContain(
      "período de referência",
    );
    expect(
      reajusteIssue({ kind: "catalog_version", referencePeriod: "" }),
    ).toContain("período de referência");
  });

  it("versão de tabela não exige fator nem índice", () => {
    expect(
      reajusteIssue({ kind: "catalog_version", referencePeriod: "data-base 07/2026" }),
    ).toBeNull();
  });

  it("fator ilegível recusa com a dica de notação", () => {
    const issue = reajusteIssue({ ...POR_INDICE, factor: "um pouco mais" });

    expect(issue).toContain(DICA_FATOR);
  });

  it("zero não é “sem reajuste”: sem reajuste é não declarar", () => {
    expect(reajusteIssue({ ...POR_INDICE, factor: "0" })).toContain("maior que zero");
  });
});

describe("fatorEhLegivel", () => {
  it("aceita as duas notações que a tela digita, e recusa o resto", () => {
    expect(fatorEhLegivel("1,0432")).toBe(true);
    expect(fatorEhLegivel("1.0432")).toBe(true);
    expect(fatorEhLegivel(" 1,05 ")).toBe(true);
    expect(fatorEhLegivel("1,04,32")).toBe(false);
    expect(fatorEhLegivel("")).toBe(false);
    expect(fatorEhLegivel("R$ 1,04")).toBe(false);
  });
});

describe("REAJUSTE_OPCOES", () => {
  it("as três formas aparecem juntas, e “sem reajuste” é a primeira", () => {
    expect(REAJUSTE_OPCOES.map((opcao) => opcao.valor)).toEqual([
      "none",
      "index_factor",
      "catalog_version",
    ]);
    // Cada uma explica o que é, por escrito: esconder as duas formas atrás de um menu faria
    // a segunda parecer exceção, e ela não é.
    for (const opcao of REAJUSTE_OPCOES) {
      expect(opcao.explicacao.length).toBeGreaterThan(0);
    }
  });
});
