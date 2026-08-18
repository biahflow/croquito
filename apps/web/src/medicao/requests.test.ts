import { describe, expect, it } from "vitest";
import {
  codeDecisionBody,
  codeSearchTerm,
  createRoundBody,
  takeoffDecisionBody,
  versionBody,
  worksiteKeyError,
} from "./requests";

describe("versionBody", () => {
  it("toda mutação leva a guarda de concorrência da rodada e nada além dela", () => {
    expect(versionBody(7)).toEqual({ base_version: 7 });
  });
});

describe("takeoffDecisionBody", () => {
  it("sempre cita a versão-base e nunca carimba identidade ou horário", () => {
    const body = takeoffDecisionBody({
      itemId: "ti_af6f85a49ea0b93d",
      action: "confirm",
      baseVersion: 7,
      quantity: "18.40",
      note: "quantidade lida na prancha",
    });

    expect(body).toEqual({
      base_version: 7,
      item_id: "ti_af6f85a49ea0b93d",
      action: "confirm",
      quantity: "18.40",
      note: "quantidade lida na prancha",
    });
    for (const forbidden of [
      "reviewer_id",
      "reviewer_role",
      "decided_at",
      "decision_id",
    ]) {
      expect(Object.keys(body)).not.toContain(forbidden);
    }
  });

  it("omite campo em branco em vez de mandar correção vazia", () => {
    const body = takeoffDecisionBody({
      itemId: "ti_af6f85a49ea0b93d",
      action: "reject",
      baseVersion: 9,
      quantity: "   ",
      unit: "",
      note: "  área de referência da prancha  ",
      itemNote: undefined,
    });

    expect(body).toEqual({
      base_version: 9,
      item_id: "ti_af6f85a49ea0b93d",
      action: "reject",
      note: "área de referência da prancha",
    });
  });

  it("manda a quantidade como texto: o decimal escrito não passa por número", () => {
    const body = takeoffDecisionBody({
      itemId: "ti_af6f85a49ea0b93d",
      action: "confirm",
      baseVersion: 3,
      quantity: "58.50",
      unit: "m2",
    });

    expect(body.quantity).toBe("58.50");
    expect(typeof body.quantity).toBe("string");
  });
});

describe("codeDecisionBody", () => {
  it("confirmação leva o código escolhido e a versão-base", () => {
    const body = codeDecisionBody({
      itemId: "ti_af6f85a49ea0b93d",
      action: "confirm",
      baseVersion: 11,
      code: "AD04050060(/)",
    });

    expect(body).toEqual({
      base_version: 11,
      item_id: "ti_af6f85a49ea0b93d",
      action: "confirm",
      code: "AD04050060(/)",
    });
  });

  /** A rota recusa `code` na rejeição: o item vira candidato a aditivo, não escolha. */
  it("rejeição leva a justificativa e nunca o código", () => {
    const body = codeDecisionBody({
      itemId: "ti_af6f85a49ea0b93d",
      action: "reject",
      baseVersion: 12,
      code: "AD04050060(/)",
      note: "sem cotação aplicável no contrato",
    });

    expect(body).toEqual({
      base_version: 12,
      item_id: "ti_af6f85a49ea0b93d",
      action: "reject",
      note: "sem cotação aplicável no contrato",
    });
    expect(Object.keys(body)).not.toContain("code");
  });
});

describe("worksiteKeyError", () => {
  /**
   * A chave é imutável na rodada e o padrão é o mesmo que o domínio exige do boletim:
   * recusá-la aqui evita uma rodada que nasce válida e só quebra no fechamento.
   */
  it("aceita a forma que o domínio exige", () => {
    expect(worksiteKeyError("praca-sintetica-oeste")).toBeNull();
    expect(worksiteKeyError("  praca-01  ")).toBeNull();
  });

  it("recusa maiúscula, acento, espaço e chave curta demais, dizendo por quê", () => {
    for (const invalida of ["PRAÇA X", "praça-x", "praca oeste", "ab", "-praca"]) {
      const erro = worksiteKeyError(invalida);
      expect(erro).not.toBeNull();
      expect(erro).toContain("minúsculas, números e hífen");
    }
  });

  it("campo vazio pede a chave em vez de descrever o padrão", () => {
    expect(worksiteKeyError("   ")).toBe("Informe a chave da obra.");
  });
});

describe("createRoundBody", () => {
  it("monta a identidade da obra com o período como inteiro e o catálogo por upload", () => {
    const body = createRoundBody({
      worksiteKey: " praca-sintetica-oeste ",
      worksiteName: "Praça Sintética Oeste",
      catalogUploadId: "0197f2a0-0000-7000-8000-0000000000bb",
      periodNumber: "3",
      referenceLabel: "3ª MEDIÇÃO",
      address: "",
      contractLabel: "Contrato 05/2024",
    });

    expect(body).toEqual({
      worksite_key: "praca-sintetica-oeste",
      worksite_name: "Praça Sintética Oeste",
      catalog_upload_id: "0197f2a0-0000-7000-8000-0000000000bb",
      period_number: 3,
      reference_label: "3ª MEDIÇÃO",
      contract_label: "Contrato 05/2024",
    });
  });
});

describe("codeSearchTerm", () => {
  it("remove o sufixo de variante entre parênteses, mantendo o código base", () => {
    expect(codeSearchTerm("AD04050060(/)")).toBe("AD04050060");
    expect(codeSearchTerm("PJ24050153(B)")).toBe("PJ24050153");
  });

  it("código sem sufixo volta sem alteração", () => {
    expect(codeSearchTerm("IE00040849")).toBe("IE00040849");
  });

  it("ignora espaço nas pontas antes e depois de remover o sufixo", () => {
    expect(codeSearchTerm("  AD04050060(/)  ")).toBe("AD04050060");
  });

  it("cai nos dez primeiros caracteres quando remover o sufixo não deixa nada", () => {
    // Caso degenerado (nunca visto num código SCO real: a base tem sempre dez
    // caracteres antes do parêntese) que só existe para exercitar o fallback.
    expect(codeSearchTerm("(ABCDEFGHIJKLMNO)")).toBe("(ABCDEFGHI");
  });
});
