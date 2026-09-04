import { describe, expect, it } from "vitest";

import { ApiError } from "../api";
import {
  describeError,
  exportBlockedViolations,
  isAbortError,
  isForbidden,
  isSelfApprovalForbidden,
  isWorkbookAuditFailure,
  orcamentoErrorCode,
  recusaDaAutoriaDeAcervo,
  recusaDeMutacao,
  recusaDoAcervo,
  siteSetupAbsentCodes,
  siteSetupMissingParameters,
  workbookAuditFindings,
} from "./errors";
import {
  errorMessage,
  fraseBindingsInvalidos,
  MENSAGEM_ORCAMENTO_MUDOU,
  RECUSA_BINDING_INVALIDO,
} from "./labels";

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
    // Aprovação nominal (F-035, ADR-0046).
    ["ESTIMATE_SELF_APPROVAL_FORBIDDEN", "não pode aprová-lo"],
    ["ESTIMATE_APPROVAL_AUTHOR_UNKNOWN", "não registra quem o montou"],
    ["ESTIMATE_EXPORT_BLOCKED", "nada foi publicado"],
    ["ESTIMATE_NOT_APPROVED", "aprovação nominal válida"],
    ["ESTIMATE_APPROVAL_REJECTED", "é de recusa"],
    ["APPROVAL_CONTENT_MISMATCH", "mudou depois da aprovação"],
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
 * O `403` GENÉRICO não nomeia papel, e desde a F-035 o motivo mudou: já não é decisão em
 * aberto (ADR-0046 fixou os papéis), é que este código chega de qualquer rota da jornada —
 * nomear um papel aqui acertaria numa rota e mentiria nas outras.
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
 * A auto-aprovação é `403` e **não** é falta de autorização (ADR-0046, decisão 6). Tratá-la
 * como falta de papel esconderia a jornada inteira de quem a enxerga, e mandaria a pessoa
 * procurar um papel que ela já tem — a comparação é de identidade contra quem montou.
 */
describe("auto-aprovação recusada", () => {
  const erro = apiError(
    "ESTIMATE_SELF_APPROVAL_FORBIDDEN",
    403,
    "quem montou o orçamento não pode aprová-lo; a assinatura é de outra pessoa",
  );

  it("tem classificação própria e NÃO é lida como falta de acesso", () => {
    expect(isSelfApprovalForbidden(erro)).toBe(true);
    expect(isForbidden(erro)).toBe(false);
    // Um `403` qualquer continua sendo falta de acesso; só este código sai da regra.
    expect(isSelfApprovalForbidden(apiError("FORBIDDEN", 403))).toBe(false);
  });

  it("a frase explica a regra e diz que acumular papéis não contorna", () => {
    const frase = describeError(erro);

    expect(frase).toContain("Acumular os dois papéis");
    expect(frase).toContain("identidade");
    expect(frase).toContain("Nada foi gravado");
  });
});

/**
 * O portão de despacho recusa por TODAS as violações de uma vez, e a lista inteira viaja em
 * `details.errors`. Mostrar só a primeira faria a orçamentista assinar de novo para
 * tropeçar na seguinte.
 */
describe("portão de despacho recusado", () => {
  const erro = apiError("DOMAIN_VALIDATION_FAILED", 422, "recusado", {
    code: "ESTIMATE_EXPORT_BLOCKED",
    errors: ["ESTIMATE_NOT_APPROVED", "APPROVAL_CONTENT_MISMATCH"],
  });

  it("devolve todas as violações, na ordem em que o servidor as mandou", () => {
    expect(exportBlockedViolations(erro)).toEqual([
      "ESTIMATE_NOT_APPROVED",
      "APPROVAL_CONTENT_MISMATCH",
    ]);
  });

  it("recusa que não é do portão, ou envelope sem lista, não fabrica violação", () => {
    expect(
      exportBlockedViolations(
        apiError("DOMAIN_VALIDATION_FAILED", 422, null, {
          code: "ESTIMATE_EXPORT_BLOCKED",
        }),
      ),
    ).toEqual([]);
    expect(exportBlockedViolations(apiError("REVISION_CONFLICT", 409))).toEqual([]);
    expect(exportBlockedViolations(new Error("rede caiu"))).toEqual([]);
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

/**
 * As duas recusas do acervo de parcelas de canteiro (F-042), as duas em falha FECHADA.
 *
 * O que elas precisam garantir é que a frase NOMEIA o que faltou: aplicar "o que dá"
 * produziria uma planilha parcial com aparência de completa, e mostrar um faltante de cada
 * vez faria a orçamentista voltar tantas vezes quantos forem os campos.
 */
describe("recusas do acervo de canteiro", () => {
  it("nomeia TODOS os parâmetros faltantes, e devolve a lista para marcar os campos", () => {
    const recusa = recusaDoAcervo(
      apiError("SITE_SETUP_PARAMETER_MISSING", 422, null, {
        parameters: ["semiperímetro", "altura do alambrado"],
      }),
    );

    expect(recusa.parametros).toEqual(["semiperímetro", "altura do alambrado"]);
    expect(recusa.mensagem).toContain("Nada foi aplicado");
    expect(recusa.mensagem).toContain("semiperímetro");
    expect(recusa.mensagem).toContain("altura do alambrado");
    expect(recusa.conflito).toBe(false);
    expect(recusa.codigos).toEqual([]);
  });

  it("nomeia o código ausente do catálogo em vez de pular a parcela em silêncio", () => {
    const recusa = recusaDoAcervo(
      apiError("SITE_SETUP_CODE_ABSENT", 422, null, {
        codes: ["AC03100050"],
      }),
    );

    expect(recusa.codigos).toEqual(["AC03100050"]);
    expect(recusa.mensagem).toContain("AC03100050");
    expect(recusa.mensagem).toContain("Nada foi aplicado");
  });

  it("envelope sem a lista devolve a frase base, nunca um faltante fabricado", () => {
    const recusa = recusaDoAcervo(apiError("SITE_SETUP_PARAMETER_MISSING"));

    expect(recusa.parametros).toEqual([]);
    expect(recusa.mensagem).toContain("Nada foi aplicado");
  });

  it("lista de outro código não é lida como faltante deste", () => {
    expect(
      siteSetupMissingParameters(
        apiError("SITE_SETUP_CODE_ABSENT", 422, null, { parameters: ["prazo"] }),
      ),
    ).toEqual([]);
    expect(siteSetupAbsentCodes(new Error("rede caiu"))).toEqual([]);
  });

  /** O `409` continua tendo banner próprio: ele não é falha do ato, é o orçamento andando. */
  it("o conflito de revisão não vira recusa do acervo", () => {
    const recusa = recusaDoAcervo(apiError("REVISION_CONFLICT", 409));

    expect(recusa.conflito).toBe(true);
    expect(recusa.parametros).toEqual([]);
    expect(recusa.mensagem).toBe(MENSAGEM_ORCAMENTO_MUDOU);
  });
});

/**
 * As recusas da AUTORIA de acervo (F-042 T6). Nenhuma delas grava coisa alguma, e a rodada
 * não muda em caso nenhum — a autoria nunca escreve na rodada.
 */
describe("recusas da autoria de acervo", () => {
  it("nomeia os bindings que o servidor não achou, para marcar os campos exatos", () => {
    const recusa = recusaDaAutoriaDeAcervo(
      apiError("SITE_SETUP_BINDING_INVALID", 422, null, {
        bindings: ["0.SEMANAS", "9.MESES"],
      }),
    );

    expect(recusa.conflito).toBe(false);
    expect(recusa.bindings).toEqual(["0.SEMANAS", "9.MESES"]);
    expect(recusa.mensagem).toContain("Nada foi guardado");
  });

  /**
   * Nome repetido é `409`, e **não** é o conflito de revisão: tratá-lo como tal ofereceria
   * "recarregar o orçamento" a quem só precisa declarar outra versão.
   */
  it("o acervo já publicado é frase própria, e não o banner do orçamento mudou", () => {
    const recusa = recusaDaAutoriaDeAcervo(
      apiError("SITE_SETUP_KIT_ALREADY_PUBLISHED", 409, null, {
        name: "Canteiro — contrato SMH/Rio",
        kit_version: "2",
      }),
    );

    expect(recusa.conflito).toBe(false);
    expect(recusa.bindings).toEqual([]);
    expect(recusa.mensagem).toContain("Acervo é imutável");
    expect(recusa.mensagem).not.toBe(MENSAGEM_ORCAMENTO_MUDOU);
  });

  it("a rodada sem parcela de canteiro diz por que não há acervo a recortar", () => {
    const recusa = recusaDaAutoriaDeAcervo(apiError("SITE_SETUP_KIT_EMPTY"));

    expect(recusa.mensagem).toContain("nenhuma parcela de canteiro gravada");
    expect(recusa.bindings).toEqual([]);
  });

  it("o conflito de revisão continua sendo o banner do orçamento", () => {
    const recusa = recusaDaAutoriaDeAcervo(apiError("REVISION_CONFLICT", 409));

    expect(recusa.conflito).toBe(true);
    expect(recusa.mensagem).toBe(MENSAGEM_ORCAMENTO_MUDOU);
  });

  it("envelope sem a lista devolve a frase base, nunca um binding fabricado", () => {
    const recusa = recusaDaAutoriaDeAcervo(apiError("SITE_SETUP_BINDING_INVALID"));

    expect(recusa.bindings).toEqual([]);
    expect(fraseBindingsInvalidos(recusa.bindings)).toBe(RECUSA_BINDING_INVALIDO);
  });

  it("a frase nomeia as declarações recusadas quando a lista veio", () => {
    const frase = fraseBindingsInvalidos(["0.SEMANAS", "9.MESES"]);

    expect(frase).toContain("0.SEMANAS");
    expect(frase).toContain("9.MESES");
  });
});
