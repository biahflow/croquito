import { describe, expect, it } from "vitest";
import {
  calcBuildBody,
  codeDecisionBody,
  codeSearchTerm,
  isAbortError,
  isStateMoved,
  itemAnchor,
  MedicaoApiError,
  readProblem,
  STATE_MOVED_CODE,
  suggestionsRecomputeBody,
  takeoffDecisionBody,
  type TakeoffItem,
} from "./api";

function problemResponse(
  status: number,
  body: Record<string, unknown>,
): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/problem+json" },
  });
}

describe("readProblem", () => {
  it("preserva o código estável, a mensagem e os detalhes da recusa do domínio", async () => {
    const error = await readProblem(
      problemResponse(422, {
        code: "TAKEOFF_ITEM_ALREADY_REVIEWED",
        detail: "item de takeoff já revisado não pode ser sobrescrito",
        details: { id: "ti_af6f85a49ea0b93d" },
      }),
    );

    expect(error).toBeInstanceOf(MedicaoApiError);
    expect(error.code).toBe("TAKEOFF_ITEM_ALREADY_REVIEWED");
    expect(error.status).toBe(422);
    expect(error.detail).toContain("já revisado");
    expect(error.details).toEqual({ id: "ti_af6f85a49ea0b93d" });
  });

  it("reconhece o conflito da guarda otimista com os dois digests", async () => {
    const error = await readProblem(
      problemResponse(409, {
        code: STATE_MOVED_CODE,
        detail: "o artefato mudou depois da leitura; recarregue antes de decidir de novo",
        details: {
          artifact: "takeoff-packet.json",
          base_sha256: "a".repeat(64),
          current_sha256: "b".repeat(64),
        },
      }),
    );

    expect(isStateMoved(error)).toBe(true);
    expect(error.details.current_sha256).toBe("b".repeat(64));
  });

  it("corpo sem envelope não vira mensagem inventada", async () => {
    const error = await readProblem(new Response("<html>500</html>", { status: 500 }));

    expect(error.code).toBe("LOCAL_RESPONSE_UNREADABLE");
    expect(error.status).toBe(500);
    expect(isStateMoved(error)).toBe(false);
  });

  it("reconhece a recusa de segunda prancha na mesma rodada", async () => {
    const error = await readProblem(
      problemResponse(409, {
        code: "LOCAL_ROUND_ALREADY_HAS_PLATE",
        detail: "esta rodada já tem prancha; uma rodada é uma prancha",
        details: { reason: "a rodada já tem pacote de takeoff publicado" },
      }),
    );

    expect(error.code).toBe("LOCAL_ROUND_ALREADY_HAS_PLATE");
    expect(error.status).toBe(409);
    expect(isStateMoved(error)).toBe(false);
    expect(error.details.reason).toBe("a rodada já tem pacote de takeoff publicado");
  });

  it("reconhece a recusa de upload inválido, com o motivo nos detalhes", async () => {
    const error = await readProblem(
      problemResponse(422, {
        code: "LOCAL_UPLOAD_INVALID",
        detail: "o arquivo enviado não é um PDF de prancha aceitável",
        details: { reason: "o arquivo precisa ser um PDF (.pdf)" },
      }),
    );

    expect(error.code).toBe("LOCAL_UPLOAD_INVALID");
    expect(error.status).toBe(422);
    expect(error.details.reason).toBe("o arquivo precisa ser um PDF (.pdf)");
  });
});

describe("isStateMoved", () => {
  it("só reconhece o conflito local; outro erro não vira convite a recarregar", () => {
    expect(isStateMoved(new Error("falha qualquer"))).toBe(false);
    expect(
      isStateMoved(new MedicaoApiError(404, "LOCAL_ARTIFACT_MISSING", "ausente", {})),
    ).toBe(false);
  });
});

function takeoffItem(anchor?: TakeoffItem["anchor"]): TakeoffItem {
  return {
    id: "ti_af6f85a49ea0b93d",
    evidence: {
      plate_id: "plate-sintetica-v1",
      page_number: 1,
      image_sha256: "a".repeat(64),
      coordinate_space: "pixel",
      bbox: { left: 10, top: 10, right: 100, bottom: 40 },
    },
    raw_text: "1 - PISO EM CONCRETO - 18,40 m2",
    label: "PISO EM CONCRETO",
    quantity: "18.40",
    unit: "m2",
    source: "vision",
    extractor: "opencv",
    extractor_version: "1.0.0",
    note: null,
    status: "proposed",
    decision: null,
    anchor,
  };
}

describe("itemAnchor", () => {
  it("lê 'registered' e 'raw' como vieram do servidor", () => {
    expect(itemAnchor(takeoffItem("registered"))).toBe("registered");
    expect(itemAnchor(takeoffItem("raw"))).toBe("raw");
  });

  it("campo ausente (servidor anterior a este contrato) trata como 'raw', nunca confirmado", () => {
    expect(itemAnchor(takeoffItem(undefined))).toBe("raw");
  });
});

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

describe("isAbortError", () => {
  it("reconhece o DOMException que fetch lança quando o AbortController cancela", () => {
    expect(isAbortError(new DOMException("aborted", "AbortError"))).toBe(true);
  });

  it("não confunde recusa do servidor ou falha qualquer com cancelamento", () => {
    expect(isAbortError(new MedicaoApiError(0, "LOCAL_SERVER_UNREACHABLE", "", {}))).toBe(
      false,
    );
    expect(isAbortError(new Error("falha qualquer"))).toBe(false);
    expect(isAbortError(new DOMException("timeout", "TimeoutError"))).toBe(false);
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
