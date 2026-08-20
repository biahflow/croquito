import { describe, expect, it } from "vitest";

import { ApiError } from "../api";
import {
  describeError,
  isAbortError,
  isForbidden,
  isWorkbookAuditFailure,
  orcamentoErrorCode,
  recusaDeMutacao,
  workbookAuditFindings,
} from "./errors";
import { errorMessage, MENSAGEM_ORCAMENTO_MUDOU } from "./labels";

function apiError(
  code: string,
  status = 422,
  detail: string | null = null,
  details: Record<string, unknown> = {},
): ApiError {
  return new ApiError(`falhou (${status})`, status, code, detail, details);
}

/**
 * Toda mensagem sai de TABELA: o código estável vem do servidor e a frase é escrita aqui.
 * Nenhuma mensagem é inventada em tempo de execução, e o código continua visível para o
 * suporte quando não há frase própria.
 */
describe("tradução dos códigos novos do orçamento", () => {
  const casos: [string, string][] = [
    ["ESTIMATE_CASCADE_ORIGIN_DUPLICATE", "Cada origem entra uma vez só"],
    ["ESTIMATE_CASCADE_LOCKED", "reordenar a cascata invalidaria"],
    ["ESTIMATE_CASCADE_ORDER_INVALID", "não é uma reordenação"],
    ["ESTIMATE_LINE_BDI_MISMATCH", "truncado no centavo"],
    ["ESTIMATE_LINE_SOURCE_UNKNOWN", "não está na cascata"],
    ["ESTIMATE_CODE_INVALID_FOR_ORIGIN", "formato da fonte"],
    ["ESTIMATE_BDI_INVALID", "percentual decimal"],
    ["ESTIMATE_ASSIGNMENT_CATALOG_REQUIRED", "sem fonte citada"],
    ["ASSIGNMENT_CATALOG_ON_REJECT", "recusar todas as fontes"],
    ["ASSIGNMENT_CATALOG_UNKNOWN", "não está na cascata"],
    ["ROUND_STAGE_NOT_READY", "conclua a etapa anterior"],
    ["ESTIMATE_WORKBOOK_AUDIT_FAILED", "nada foi publicado"],
    ["REVISION_CONFLICT", "recarregue o estado atual"],
  ];

  for (const [code, trecho] of casos) {
    it(`${code} vira frase de obra`, () => {
      const frase = errorMessage(code);

      expect(frase).toContain(trecho);
      // A frase é escrita, não o código repetido: um código cru na tela é o sintoma de
      // tradução ausente.
      expect(frase).not.toBe(code);
    });
  }

  it("código desconhecido aparece como veio, com o detalhe do servidor", () => {
    expect(errorMessage("ESTIMATE_ALGO_QUE_NAO_EXISTE", "motivo do servidor")).toBe(
      "ESTIMATE_ALGO_QUE_NAO_EXISTE: motivo do servidor",
    );
  });

  it("o detalhe do servidor entra como complemento, sem repetir a frase", () => {
    const frase = errorMessage(
      "ESTIMATE_CASCADE_LOCKED",
      "a rodada já tem decisão de código",
    );

    expect(frase).toContain("(a rodada já tem decisão de código)");
  });
});

/**
 * O `403` da jornada não nomeia papel: qual papel autoriza o orçamento é decisão humana
 * ainda aberta (Design Approval Package), e a frase não pode fingir que ela foi tomada.
 */
describe("403 sem nome de papel", () => {
  it("é reconhecido pelo código e pelo status", () => {
    expect(isForbidden(apiError("FORBIDDEN", 403))).toBe(true);
    expect(isForbidden(apiError("ALGO_OUTRO", 403))).toBe(true);
    expect(isForbidden(apiError("NOT_FOUND", 404))).toBe(false);
  });

  it("a frase pede o acesso sem citar papel nenhum", () => {
    const frase = errorMessage("FORBIDDEN");

    expect(frase).toContain("não tem o papel que autoriza");
    expect(frase.toLowerCase()).not.toContain("orcamentista");
    expect(frase.toLowerCase()).not.toContain("platform_operator");
    expect(frase.toLowerCase()).not.toContain("revisor");
  });
});

/**
 * A auditoria reprovada é desfecho de TELA, com os CÓDIGOS dos achados. `expected`/`found`
 * são preço e quantidade do cliente e a rota não os devolve — se um dia devolvesse, esta
 * leitura continuaria só com os códigos.
 */
describe("auditoria da planilha reprovada", () => {
  const erro = apiError("ESTIMATE_WORKBOOK_AUDIT_FAILED", 500, null, {
    finding_codes: ["CELL_VALUE_MISMATCH", "SHEET_MISSING"],
    finding_count: 2,
  });

  it("é classificada à parte do alerta comum", () => {
    expect(isWorkbookAuditFailure(erro)).toBe(true);
    expect(recusaDeMutacao(erro)).toEqual({
      conflito: false,
      auditoria: true,
      mensagem: expect.stringContaining("nada foi publicado"),
    });
  });

  it("devolve só os códigos dos achados", () => {
    expect(workbookAuditFindings(erro)).toEqual([
      "CELL_VALUE_MISMATCH",
      "SHEET_MISSING",
    ]);
  });

  it("envelope sem lista de achados não fabrica achado nenhum", () => {
    expect(workbookAuditFindings(apiError("ESTIMATE_WORKBOOK_AUDIT_FAILED", 500))).toEqual(
      [],
    );
    expect(workbookAuditFindings(new Error("qualquer coisa"))).toEqual([]);
  });
});

describe("desfecho de uma mutação recusada", () => {
  it("o 409 tem banner próprio e não vira alerta comum", () => {
    expect(recusaDeMutacao(apiError("REVISION_CONFLICT", 409))).toEqual({
      conflito: true,
      auditoria: false,
      mensagem: MENSAGEM_ORCAMENTO_MUDOU,
    });
  });

  it("qualquer outra recusa é a frase da regra que recusou", () => {
    const recusa = recusaDeMutacao(
      apiError("DOMAIN_VALIDATION_FAILED", 422, "recusado", {
        code: "ESTIMATE_LINE_BDI_MISMATCH",
      }),
    );

    expect(recusa.conflito).toBe(false);
    expect(recusa.auditoria).toBe(false);
    expect(recusa.mensagem).toContain("truncado no centavo");
  });

  it("erro sem envelope legível não vira código inventado", () => {
    const semCodigo = new ApiError("falhou", 500, null, null, {});

    expect(orcamentoErrorCode(semCodigo)).toBeNull();
    expect(describeError(semCodigo)).toBe("falhou");
    expect(describeError(new Error("rede caiu"))).toBe("rede caiu");
  });
});

/** Cancelamento de busca não é falha de rede e não pode virar alerta na tela. */
describe("cancelamento da busca incremental", () => {
  it("AbortError é reconhecido e nenhum outro erro é confundido com ele", () => {
    expect(isAbortError(new DOMException("cancelado", "AbortError"))).toBe(true);
    expect(isAbortError(new Error("AbortError"))).toBe(false);
    expect(isAbortError(apiError("NOT_FOUND", 404))).toBe(false);
  });
});
