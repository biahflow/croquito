import { describe, expect, it } from "vitest";

import { priceOriginLabel, priceOriginSeloClass } from "./labels";

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
