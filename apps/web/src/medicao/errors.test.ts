import { describe, expect, it } from "vitest";
import { ApiError } from "../api";
import {
  describeError,
  exportBlockedViolations,
  isAbortError,
  isForbidden,
  isRevisionConflict,
  isWorkbookAuditFailure,
  medicaoErrorCode,
  recusaDeMutacao,
  workbookAuditFindings,
} from "./errors";

function recusa(
  status: number,
  code: string | null,
  detail = "",
  details: Record<string, unknown> = {},
): ApiError {
  return new ApiError(`${code}: ${detail}`, status, code, detail, details);
}

describe("isRevisionConflict", () => {
  it("só reconhece o conflito de versão da rodada", () => {
    expect(isRevisionConflict(recusa(409, "REVISION_CONFLICT"))).toBe(true);
    expect(isRevisionConflict(recusa(409, "ROUND_PLATE_ALREADY_PRESENT"))).toBe(false);
    expect(isRevisionConflict(recusa(404, "NOT_FOUND"))).toBe(false);
    expect(isRevisionConflict(new Error("falha qualquer"))).toBe(false);
  });
});

describe("medicaoErrorCode", () => {
  it("prefere a invariante do domínio quando ela viaja em details.code", () => {
    const erro = recusa(422, "DOMAIN_VALIDATION_FAILED", "recusa do domínio", {
      code: "ASSIGNMENT_ITEM_ALREADY_DECIDED",
    });

    expect(medicaoErrorCode(erro)).toBe("ASSIGNMENT_ITEM_ALREADY_DECIDED");
  });

  it("sem invariante declarada, o código da API é o que há", () => {
    expect(medicaoErrorCode(recusa(422, "DOMAIN_VALIDATION_FAILED"))).toBe(
      "DOMAIN_VALIDATION_FAILED",
    );
    expect(medicaoErrorCode(recusa(409, "CATALOG_REQUIRED"))).toBe("CATALOG_REQUIRED");
  });

  it("envelope ilegível devolve nulo em vez de código inventado", () => {
    expect(medicaoErrorCode(recusa(502, null))).toBeNull();
  });
});

describe("recusaDeMutacao", () => {
  /**
   * O `409` da rodada não é falha do ato: ele tem banner próprio, com o botão de
   * recarregar e o formulário preservado. Tratá-lo como erro comum mandaria a
   * orçamentista procurar o defeito no que ela acabou de escrever.
   */
  it("o 409 REVISION_CONFLICT vira 'a rodada mudou', nunca erro genérico", () => {
    const desfecho = recusaDeMutacao(recusa(409, "REVISION_CONFLICT", "A newer revision exists."));

    expect(desfecho.conflito).toBe(true);
    expect(desfecho.mensagem).toContain("A rodada mudou");
    expect(desfecho.mensagem).toContain("Nada foi gravado");
    expect(desfecho.mensagem).toContain("continua aqui");
  });

  it("qualquer outra recusa é a frase da regra que recusou, no alerta comum", () => {
    const desfecho = recusaDeMutacao(
      recusa(422, "DOMAIN_VALIDATION_FAILED", "há item confirmado sem código", {
        code: "CALC_ASSIGNMENT_MISSING",
      }),
    );

    expect(desfecho.conflito).toBe(false);
    expect(desfecho.mensagem).toContain("não é montado pela metade");
    expect(desfecho.mensagem).not.toContain("A rodada mudou");
  });
});

describe("isForbidden", () => {
  it("reconhece a falta de autorização pelo código e pelo status", () => {
    expect(isForbidden(recusa(403, "FORBIDDEN"))).toBe(true);
    expect(isForbidden(recusa(403, "OUTRO_CODIGO"))).toBe(true);
    expect(isForbidden(recusa(404, "NOT_FOUND"))).toBe(false);
    expect(isForbidden(new Error("falha qualquer"))).toBe(false);
  });
});

describe("auditoria da planilha reprovada", () => {
  const auditoria = recusa(
    500,
    "VALUATION_WORKBOOK_AUDIT_FAILED",
    "a planilha do boletim não confere com a medição aprovada; nada foi publicado",
    { finding_codes: ["CELL_VALUE_MISMATCH"], finding_count: 1 },
  );

  it("é desfecho próprio, não mais um erro comum", () => {
    expect(isWorkbookAuditFailure(auditoria)).toBe(true);
    expect(isWorkbookAuditFailure(recusa(500, "OUTRA_FALHA"))).toBe(false);
    expect(recusaDeMutacao(auditoria).auditoria).toBe(true);
    expect(recusaDeMutacao(auditoria).conflito).toBe(false);
    expect(recusaDeMutacao(recusa(409, "REVISION_CONFLICT")).auditoria).toBe(false);
  });

  /**
   * Só os CÓDIGOS viajam: `expected`/`found` de um achado são preço, quantidade e total da
   * obra do cliente, e a rota não os devolve numa mensagem de erro.
   */
  it("devolve os códigos dos achados, e nunca um achado fabricado", () => {
    expect(workbookAuditFindings(auditoria)).toEqual(["CELL_VALUE_MISMATCH"]);
    expect(workbookAuditFindings(recusa(500, "VALUATION_WORKBOOK_AUDIT_FAILED"))).toEqual(
      [],
    );
    expect(workbookAuditFindings(new Error("falha qualquer"))).toEqual([]);
  });
});

describe("exportBlockedViolations", () => {
  function portao(errors: unknown): ReturnType<typeof recusa> {
    return recusa(422, "DOMAIN_VALIDATION_FAILED", "medição possui violações abertas", {
      code: "VALUATION_EXPORT_BLOCKED",
      errors,
    });
  }

  /**
   * O portão recusa por TODAS as violações de uma vez. Mostrar só a primeira faria a
   * orçamentista aprovar de novo para tropeçar na seguinte.
   */
  it("separa código e partes de cada violação, na ordem em que o domínio as escreveu", () => {
    const violacoes = exportBlockedViolations(
      portao([
        "VALUATION_NOT_APPROVED",
        "PERIOD_NOT_SEQUENTIAL:3:4",
        "CODE_NOT_IN_CONTRACT:praca-sintetica-oeste:04:09.001.0100-A",
      ]),
    );

    expect(violacoes).toEqual([
      { code: "VALUATION_NOT_APPROVED", parts: [] },
      { code: "PERIOD_NOT_SEQUENTIAL", parts: ["3", "4"] },
      {
        code: "CODE_NOT_IN_CONTRACT",
        parts: ["praca-sintetica-oeste", "04", "09.001.0100-A"],
      },
    ]);
  });

  it("recusa que não é do portão, ou sem a lista, não vira violação inventada", () => {
    expect(exportBlockedViolations(portao(undefined))).toEqual([]);
    expect(
      exportBlockedViolations(
        recusa(422, "DOMAIN_VALIDATION_FAILED", "outra regra", {
          code: "CALC_ASSIGNMENT_MISSING",
          errors: ["ALGO"],
        }),
      ),
    ).toEqual([]);
    expect(exportBlockedViolations(new Error("falha qualquer"))).toEqual([]);
  });
});

describe("describeError", () => {
  it("erro que não é da API volta com a própria mensagem", () => {
    expect(describeError(new Error("falha de rede"))).toBe("falha de rede");
    expect(describeError("texto solto")).toBe("texto solto");
  });
});

describe("isAbortError", () => {
  it("reconhece o DOMException que fetch lança quando o AbortController cancela", () => {
    expect(isAbortError(new DOMException("aborted", "AbortError"))).toBe(true);
  });

  it("não confunde recusa do servidor ou falha qualquer com cancelamento", () => {
    expect(isAbortError(recusa(503, "PROCESSING_UNAVAILABLE"))).toBe(false);
    expect(isAbortError(new Error("falha qualquer"))).toBe(false);
    expect(isAbortError(new DOMException("timeout", "TimeoutError"))).toBe(false);
  });
});
