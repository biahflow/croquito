import { describe, expect, it } from "vitest";

import {
  assignmentStatusLabel,
  errorMessage,
  origensAceitasNaCascata,
  priceOriginLabel,
  priceOriginSeloClass,
} from "./labels";

describe("priceOriginLabel", () => {
  /**
   * SINAPI e SICRO entram como origens nomeadas de `PriceOrigin` (ADR-0039, F-026); a
   * orçamentista precisa ver a sigla real, não a chave crua do enum.
   */
  it("nomeia as origens novas SINAPI e SICRO", () => {
    expect(priceOriginLabel("sinapi")).toBe("SINAPI");
    expect(priceOriginLabel("sicro")).toBe("SICRO");
  });

  it("preserva as origens existentes", () => {
    expect(priceOriginLabel("sco")).toBe("SCO");
    expect(priceOriginLabel("emop")).toBe("EMOP");
    expect(priceOriginLabel("composition")).toBe("composição");
  });
});

describe("priceOriginSeloClass", () => {
  /**
   * O selo é redundância do texto (já escrito por `priceOriginLabel`); SINAPI e SICRO
   * caem no fallback neutro de propósito — cor nova por origem é decisão de design que
   * esta feature não tem (F-026/T1).
   */
  it("cai no fallback neutro para as origens novas, sem cor própria", () => {
    expect(priceOriginSeloClass("sinapi")).toBe("selo-neutro");
    expect(priceOriginSeloClass("sicro")).toBe("selo-neutro");
  });

  it("preserva a cor das origens que já tinham selo próprio", () => {
    expect(priceOriginSeloClass("sco")).toBe("selo-fonte-sco");
    expect(priceOriginSeloClass("emop")).toBe("selo-fonte-emop");
    expect(priceOriginSeloClass("composition")).toBe("selo-fonte-composicao");
  });
});

/**
 * Regime da rodada (ADR-0045, decisão 5): a rejeição é a MESMA decisão nos dois regimes, e
 * é o nome dela que muda. Nada novo é calculado, e é por isso que o rótulo é o ponto.
 */
describe("assignmentStatusLabel sob contrato licitado", () => {
  it("lê o item rejeitado como candidato a aditivo quando a rodada corre sob contrato", () => {
    expect(assignmentStatusLabel("rejected", true)).toBe("candidato a aditivo");
  });

  it("sem regime, segue lendo o que lê hoje", () => {
    expect(assignmentStatusLabel("rejected")).toBe("sem código na cascata");
    expect(assignmentStatusLabel("rejected", false)).toBe("sem código na cascata");
  });

  /** O regime não renomeia o que não é rejeição: confirmar é confirmar nos dois. */
  it("não muda o rótulo do código confirmado nem o de um status desconhecido", () => {
    expect(assignmentStatusLabel("confirmed", true)).toBe("código confirmado");
    expect(assignmentStatusLabel("confirmed")).toBe("código confirmado");
    expect(assignmentStatusLabel("inexistente", true)).toBe("inexistente");
  });
});

/**
 * A lista de origens aceitas vem do SERVIDOR (`regime.allowed_cascade_origins`). A tela
 * escreve o que leu; ela não guarda a própria cópia da regra nem afirma restrição sem tê-la
 * lido.
 */
describe("origensAceitasNaCascata", () => {
  it("nomeia as origens lidas do servidor, com a sigla da obra", () => {
    const frase = origensAceitasNaCascata(["sco"]);

    expect(frase).toContain("catálogo de SCO");
    expect(frase).toContain("recusado na instalação");
    expect(frase).toContain("nada é gravado");
  });

  it("escreve o que leu, mesmo que o servidor passe a aceitar mais de uma origem", () => {
    expect(origensAceitasNaCascata(["sco", "composition"])).toContain(
      "SCO, composição",
    );
  });

  it("lista vazia não vira frase: a tela não afirma restrição que não leu", () => {
    expect(origensAceitasNaCascata([])).toBeNull();
  });
});

/**
 * As três recusas do regime têm frase de obra própria, e as duas que recusam um ato dizem
 * por escrito que nada foi gravado (decisão 3 do pacote de design aprovado).
 */
describe("recusas do regime", () => {
  it("a origem proibida diz o que aconteceria se a fonte entrasse", () => {
    const frase = errorMessage("ESTIMATE_CASCADE_ORIGIN_FORBIDDEN");

    expect(frase).toContain("sob contrato licitado");
    expect(frase).toContain("a medição recusaria depois");
    expect(frase).toContain("Nada foi instalado e nada foi alterado");
  });

  it("a cascata suja manda remover a fonte, e diz que nada foi removido sozinho", () => {
    const frase = errorMessage("ESTIMATE_REGIME_CASCADE_DIRTY");

    expect(frase).toContain("Remova a fonte");
    expect(frase).toContain("nenhuma fonte é removida automaticamente");
    expect(frase).toContain("a declaração não foi gravada");
  });

  it("a mão única diz por que a volta não existe, em vez de sumir com o ato", () => {
    const frase = errorMessage("ESTIMATE_REGIME_IRREVERSIBLE");

    expect(frase).toContain("mão única");
    expect(frase).toContain("abra outra rodada");
  });
});
