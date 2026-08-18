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

/**
 * A rodada avançou depois desta leitura. Não é falha: é o sinal de recarregar antes de
 * decidir de novo — outra aba, outra pessoa ou o worker mexeram na rodada.
 */
export function isRevisionConflict(error: unknown): boolean {
  return error instanceof ApiError && error.code === REVISION_CONFLICT_CODE;
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
 * Desfecho de uma mutação recusada, para a tela não tratar os dois casos como um só.
 *
 * O `409` da rodada tem banner próprio, com o botão de recarregar e o formulário
 * preservado: ele não é falha do ato, é o aviso de que a rodada andou. Qualquer outra
 * recusa é a frase da regra que recusou, no alerta comum.
 */
export function recusaDeMutacao(error: unknown): {
  conflito: boolean;
  mensagem: string;
} {
  if (isRevisionConflict(error)) {
    return { conflito: true, mensagem: MENSAGEM_RODADA_MUDOU };
  }
  return { conflito: false, mensagem: describeError(error) };
}

/**
 * `true` quando o erro é o cancelamento de um `AbortController` — nunca falha de rede.
 * A busca incremental cancela a consulta anterior a cada tecla; sem esta distinção, cada
 * cancelamento apareceria na tela como falha da API.
 */
export function isAbortError(error: unknown): boolean {
  return error instanceof DOMException && error.name === "AbortError";
}
