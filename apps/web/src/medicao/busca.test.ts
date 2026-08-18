import { describe, expect, it } from "vitest";
import type { CatalogSearchResponse, CatalogSearchResult } from "./api";
import { BUSCA_MIN_CARACTERES, consultaIncremental, resumoDaBusca } from "./busca";

function resultado(code: string): CatalogSearchResult {
  return { code, unit: "m2", unit_price: "10.00", description: `ITEM ${code}` };
}

function resposta(over: Partial<CatalogSearchResponse>): CatalogSearchResponse {
  return {
    query: "gramado",
    terms: ["gramado"],
    limit: 20,
    total_matches: 1,
    results: [resultado("AD04050060(/)")],
    matching: "lexical",
    semantic_notes: [],
    ...over,
  };
}

describe("consultaIncremental", () => {
  it("consulta vazia não dispara", () => {
    expect(consultaIncremental("")).toBeNull();
  });

  it("consulta abaixo do limiar não dispara", () => {
    expect(BUSCA_MIN_CARACTERES).toBe(3);
    expect(consultaIncremental("gr")).toBeNull();
  });

  it("só espaço conta como vazia depois do trim", () => {
    expect(consultaIncremental("   ")).toBeNull();
  });

  it("consulta no limiar ou acima dispara, já trimada", () => {
    expect(consultaIncremental("  gramado  ")).toBe("gramado");
    expect(consultaIncremental("piso")).toBe("piso");
  });
});

describe("resumoDaBusca", () => {
  it("página completa: todos os itens que casaram por palavra vieram, sem 'mostrando'", () => {
    const resumo = resumoDaBusca(
      resposta({
        terms: ["gramado"],
        total_matches: 2,
        results: [resultado("AD04050060(/)"), resultado("AD04050061(/)")],
        matching: "lexical",
      }),
    );

    expect(resumo).toBe("2 itens do catálogo casam com gramado.");
    expect(resumo).not.toContain("mostrando");
  });

  it("página cortada: declara o total casado e o corte mostrado", () => {
    const resumo = resumoDaBusca(
      resposta({
        terms: ["gramado"],
        limit: 1,
        total_matches: 5,
        results: [resultado("AD04050060(/)")],
        matching: "lexical",
      }),
    );

    expect(resumo).toBe(
      "5 itens do catálogo casam com gramado; mostrando os 1 mais relevantes.",
    );
  });

  it("híbrido com vizinhos sem palavra em comum: explica a diferença entre os dois totais", () => {
    const resumo = resumoDaBusca(
      resposta({
        terms: ["refletor"],
        total_matches: 2,
        results: [resultado("MB01300010(/)"), resultado("MB01300011(/)"), resultado("MB01300012(/)")],
        matching: "hybrid",
      }),
    );

    expect(resumo).toBe(
      "2 itens casam por palavra com refletor; a lista traz 3 resultados porque o braço " +
        "semântico acrescenta vizinhos sem palavra em comum.",
    );
  });

  it("singular correto quando só um item casa", () => {
    const resumo = resumoDaBusca(
      resposta({
        terms: ["banco"],
        total_matches: 1,
        results: [resultado("MB01100010(/)")],
        matching: "lexical",
      }),
    );

    expect(resumo).toBe("1 item do catálogo casa com banco.");
  });
});
