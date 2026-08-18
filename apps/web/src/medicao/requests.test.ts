import { describe, expect, it } from "vitest";
import {
  calcBuildBody,
  codeDecisionBody,
  codeSearchTerm,
  suggestionsRecomputeBody,
  takeoffDecisionBody,
} from "./requests";

describe("takeoffDecisionBody", () => {
  it("sempre cita o digest-base e nunca carimba identidade ou horário", () => {
    const body = takeoffDecisionBody({
      itemId: "ti_af6f85a49ea0b93d",
      action: "confirm",
      basePacketSha256: "c".repeat(64),
      quantity: "18.40",
      note: "quantidade lida na prancha",
    });

    expect(body).toEqual({
      item_id: "ti_af6f85a49ea0b93d",
      action: "confirm",
      base_packet_sha256: "c".repeat(64),
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
      basePacketSha256: "c".repeat(64),
      quantity: "   ",
      unit: "",
      note: "  área de referência da prancha  ",
      itemNote: undefined,
    });

    expect(body).toEqual({
      item_id: "ti_af6f85a49ea0b93d",
      action: "reject",
      base_packet_sha256: "c".repeat(64),
      note: "área de referência da prancha",
    });
  });

  it("manda a quantidade como texto: o decimal escrito não passa por número", () => {
    const body = takeoffDecisionBody({
      itemId: "ti_af6f85a49ea0b93d",
      action: "confirm",
      basePacketSha256: "c".repeat(64),
      quantity: "58.50",
      unit: "m2",
    });

    expect(body.quantity).toBe("58.50");
    expect(typeof body.quantity).toBe("string");
  });
});

describe("codeDecisionBody", () => {
  it("cita o digest-base quando já existe conjunto de confirmações", () => {
    const body = codeDecisionBody({
      itemId: "ti_af6f85a49ea0b93d",
      action: "confirm",
      code: "AD04050060(/)",
      baseAssignmentsSha256: "d".repeat(64),
    });

    expect(body).toEqual({
      item_id: "ti_af6f85a49ea0b93d",
      action: "confirm",
      code: "AD04050060(/)",
      base_assignments_sha256: "d".repeat(64),
    });
  });

  it("omite o digest-base na primeira decisão; o servidor recusaria um digest inventado", () => {
    const body = codeDecisionBody({
      itemId: "ti_af6f85a49ea0b93d",
      action: "reject",
      note: "sem cotação aplicável no contrato",
      baseAssignmentsSha256: null,
    });

    expect(body).toEqual({
      item_id: "ti_af6f85a49ea0b93d",
      action: "reject",
      note: "sem cotação aplicável no contrato",
    });
    expect(Object.keys(body)).not.toContain("base_assignments_sha256");
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

describe("suggestionsRecomputeBody", () => {
  it("omite o digest-base quando ainda não existe shortlist", () => {
    expect(suggestionsRecomputeBody(null)).toEqual({});
  });

  it("cita o digest-base lido quando a shortlist já existe", () => {
    expect(suggestionsRecomputeBody("e".repeat(64))).toEqual({
      base_suggestions_sha256: "e".repeat(64),
    });
  });
});

describe("calcBuildBody", () => {
  it("monta a identificação da obra com o período como inteiro", () => {
    const body = calcBuildBody({
      worksiteKey: " praca-sintetica-oeste ",
      worksiteName: "Praça Sintética Oeste",
      periodNumber: "3",
      referenceLabel: "3ª MEDIÇÃO",
      address: "",
      contractLabel: "Contrato 05/2024",
    });

    expect(body).toEqual({
      worksite_key: "praca-sintetica-oeste",
      worksite_name: "Praça Sintética Oeste",
      period_number: 3,
      reference_label: "3ª MEDIÇÃO",
      contract_label: "Contrato 05/2024",
    });
  });
});
