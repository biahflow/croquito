import { describe, expect, it } from "vitest";

import type { AmendmentDraft } from "./api";
import { DICA_DELTA, deltaEhLegivel, reRaIssue } from "./reratificacao";

const COMPLETA: AmendmentDraft = {
  label: "1ª RE-RA",
  referencePeriod: "Processo 123/2026",
  lines: [{ code: "CE04100010(/)", quantityDelta: "-4,00" }],
};

describe("reRaIssue", () => {
  it("não re-ratificar é o caminho normal, e não é problema", () => {
    expect(reRaIssue(null)).toBeNull();
  });

  it("declaração completa pode ser enviada", () => {
    expect(reRaIssue(COMPLETA)).toBeNull();
  });

  it("sem nome curto recusa antes da rede", () => {
    expect(reRaIssue({ ...COMPLETA, label: "  " })).toContain("nome curto");
  });

  it("sem processo declarado recusa: a declaração precisa ser conferível", () => {
    const issue = reRaIssue({ ...COMPLETA, referencePeriod: " " });

    expect(issue).toContain("conferir");
  });

  it("código sem efeito é declaração pela metade", () => {
    const issue = reRaIssue({
      ...COMPLETA,
      lines: [{ code: "CE04100010(/)", quantityDelta: "" }],
    });

    expect(issue).toContain("efeito");
    expect(issue).toContain(DICA_DELTA);
  });

  it("efeito sem código também recusa, com o porquê", () => {
    const issue = reRaIssue({
      ...COMPLETA,
      lines: [{ code: "  ", quantityDelta: "-4,00" }],
    });

    expect(issue).toContain("sem código");
  });

  it("efeito ilegível recusa com a dica de notação", () => {
    const issue = reRaIssue({
      ...COMPLETA,
      lines: [{ code: "CE04100010(/)", quantityDelta: "um pouco menos" }],
    });

    expect(issue).toContain(DICA_DELTA);
  });

  it("efeito zero não é RE-RA: sem mudança é não declarar", () => {
    const issue = reRaIssue({
      ...COMPLETA,
      lines: [{ code: "CE04100010(/)", quantityDelta: "0" }],
    });

    expect(issue).toContain("não declarar");
  });

  it("linha inteiramente em branco é ignorada, e não vira erro", () => {
    expect(
      reRaIssue({
        ...COMPLETA,
        lines: [{ code: "CE04100010(/)", quantityDelta: "-4,00" }, { code: "", quantityDelta: "" }],
      }),
    ).toBeNull();
  });
});

describe("deltaEhLegivel", () => {
  it("aceita o efeito com sinal e as duas notações, e recusa o resto", () => {
    expect(deltaEhLegivel("-4")).toBe(true);
    expect(deltaEhLegivel("+6")).toBe(true);
    expect(deltaEhLegivel("1,50")).toBe(true);
    expect(deltaEhLegivel("1.50")).toBe(true);
    expect(deltaEhLegivel(" -4,00 ")).toBe(true);
    expect(deltaEhLegivel("1,0,0")).toBe(false);
    expect(deltaEhLegivel("")).toBe(false);
    expect(deltaEhLegivel("quatro")).toBe(false);
  });
});
