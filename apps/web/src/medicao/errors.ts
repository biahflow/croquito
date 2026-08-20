/**
 * Classificação pura das recusas da API: qual delas é o convite a recarregar a rodada,
 * qual código escolhe a frase de obra e quando um erro é só o cancelamento de uma busca
 * anterior pelo `AbortController`, nunca falha de rede.
 */

import { ApiError } from "../api";
import { errorMessage, MENSAGEM_RODADA_MUDOU } from "./labels";

/** O `409` da guarda otimista da rodada; é ele que substituiu o conflito por digest. */
export const REVISION_CONFLICT_CODE = "REVISION_CONFLICT";

/** Invariante de `packages/valuation` viaja DENTRO deste código, em `details.code`. */
export const DOMAIN_VALIDATION_CODE = "DOMAIN_VALIDATION_FAILED";

/** Falta do papel que autoriza a rodada; ganha tela própria, sem nomear papel nenhum. */
export const FORBIDDEN_CODE = "FORBIDDEN";

/** Portão de exportação do domínio: a lista de violações viaja em `details.errors`. */
export const EXPORT_BLOCKED_CODE = "VALUATION_EXPORT_BLOCKED";

/** Auditoria de round-trip da planilha reprovada: nada foi publicado. */
export const WORKBOOK_AUDIT_FAILED_CODE = "VALUATION_WORKBOOK_AUDIT_FAILED";

/**
 * A rodada avançou depois desta leitura. Não é falha: é o sinal de recarregar antes de
 * decidir de novo — outra aba, outra pessoa ou o worker mexeram na rodada.
 */
export function isRevisionConflict(error: unknown): boolean {
  return error instanceof ApiError && error.code === REVISION_CONFLICT_CODE;
}

/**
 * `403` da rota. A jornada é montada pela ROTA, não pelo papel: quem chega por link direto
 * sem autorização precisa ler o motivo, e barrar no cliente trocaria uma frase legível por
 * uma tela vazia. Quem autoriza é sempre o backend.
 */
export function isForbidden(error: unknown): boolean {
  return (
    error instanceof ApiError &&
    (error.code === FORBIDDEN_CODE || error.status === 403)
  );
}

/**
 * Auditoria da planilha reprovada. É desfecho de TELA, não rodapé: nada foi publicado, e
 * dizê-lo por extenso é o que separa "falhou" de "publicou algo que ninguém conferiu".
 */
export function isWorkbookAuditFailure(error: unknown): boolean {
  return error instanceof ApiError && error.code === WORKBOOK_AUDIT_FAILED_CODE;
}

/**
 * Códigos dos achados que reprovaram a auditoria, na ordem em que o servidor os mandou.
 *
 * Só os CÓDIGOS viajam, de propósito: `expected`/`found` de um achado são o preço, a
 * quantidade e o total da obra do cliente, e a rota não os devolve numa mensagem de erro.
 * Envelope sem a lista devolve vazio, nunca um achado fabricado.
 */
export function workbookAuditFindings(error: unknown): string[] {
  if (!(error instanceof ApiError)) {
    return [];
  }
  const codes = error.details.finding_codes;
  if (!Array.isArray(codes)) {
    return [];
  }
  return codes.filter((code): code is string => typeof code === "string");
}

/** Uma violação do portão de exportação: o código estável e as partes que o acompanham. */
export type ExportViolation = {
  code: string;
  /** Segmentos depois do código, na ordem em que o domínio os escreveu. */
  parts: string[];
};

/**
 * Violações abertas do portão de exportação (`Valuation.export_errors`).
 *
 * O domínio escreve cada violação como `CODIGO` ou `CODIGO:parte:parte`
 * (`PERIOD_NOT_SEQUENTIAL:3:4`, `CODE_NOT_IN_CONTRACT:praca:04:09.001.0100-A`), e a lista
 * inteira viaja em `details.errors` do `VALUATION_EXPORT_BLOCKED`. A separação é feita
 * aqui, para a tela mostrar TODAS as violações traduzidas em vez de uma frase só: o portão
 * recusa por todas de uma vez, e esconder as demais faria a orçamentista aprovar de novo
 * para tropeçar na seguinte.
 *
 * Recusa que não é do portão — ou envelope sem a lista — devolve vazio, nunca uma violação
 * inventada.
 */
export function exportBlockedViolations(error: unknown): ExportViolation[] {
  if (!(error instanceof ApiError) || medicaoErrorCode(error) !== EXPORT_BLOCKED_CODE) {
    return [];
  }
  const errors = error.details.errors;
  if (!Array.isArray(errors)) {
    return [];
  }
  return errors
    .filter((violation): violation is string => typeof violation === "string")
    .map((violation) => {
      const [code, ...parts] = violation.split(":");
      return { code, parts };
    });
}

/**
 * Código que escolhe a frase mostrada ao orçamentista.
 *
 * Em `DOMAIN_VALIDATION_FAILED` quem recusou é a invariante do domínio, e ela viaja em
 * `details.code` (`TAKEOFF_*`, `ASSIGNMENT_*`, `CALC_*`, `AMENDMENT_DOSSIER_*`): mostrar
 * o código da API ali esconderia o que o domínio disse. Nos demais casos o código da API
 * é o que há. Resposta sem envelope legível não vira código inventado — devolve `null`.
 */
export function medicaoErrorCode(error: ApiError): string | null {
  if (error.code === DOMAIN_VALIDATION_CODE) {
    const domain = error.details.code;
    if (typeof domain === "string" && domain.length > 0) {
      return domain;
    }
  }
  return error.code;
}

/**
 * Frase de obra de uma recusa. O código estável escolhe o texto; sem envelope legível
 * sobra a frase que o transporte montou, nunca uma mensagem inventada.
 */
export function describeError(error: unknown): string {
  if (error instanceof ApiError) {
    const code = medicaoErrorCode(error);
    return code === null ? error.message : errorMessage(code, error.detail);
  }
  return error instanceof Error ? error.message : String(error);
}

/**
 * Desfecho de uma mutação recusada, para a tela não tratar os casos como um só.
 *
 * O `409` da rodada tem banner próprio, com o botão de recarregar e o formulário
 * preservado: ele não é falha do ato, é o aviso de que a rodada andou. A auditoria
 * reprovada da planilha é uma TELA, e por isso sai marcada aqui em vez de virar mais um
 * alerta. Qualquer outra recusa é a frase da regra que recusou, no alerta comum.
 */
export function recusaDeMutacao(error: unknown): {
  conflito: boolean;
  auditoria: boolean;
  mensagem: string;
} {
  if (isRevisionConflict(error)) {
    return { conflito: true, auditoria: false, mensagem: MENSAGEM_RODADA_MUDOU };
  }
  return {
    conflito: false,
    auditoria: isWorkbookAuditFailure(error),
    mensagem: describeError(error),
  };
}

/**
 * `true` quando o erro é o cancelamento de um `AbortController` — nunca falha de rede.
 * A busca incremental cancela a consulta anterior a cada tecla; sem esta distinção, cada
 * cancelamento apareceria na tela como falha da API.
 */
export function isAbortError(error: unknown): boolean {
  return error instanceof DOMException && error.name === "AbortError";
}
