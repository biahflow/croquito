/**
 * Classificação pura de erros do módulo de API: quando um `MedicaoApiError` é o convite a
 * recarregar (conflito da guarda otimista) e quando um erro é só o cancelamento de uma
 * busca anterior pelo `AbortController`, nunca falha de rede.
 */

import { MedicaoApiError, STATE_MOVED_CODE } from "./api";

/**
 * O artefato mudou no disco depois da leitura desta tela. Não é falha: é o sinal de
 * recarregar antes de decidir de novo — outro processo (o CLI, outra aba) mexeu na rodada.
 */
export function isStateMoved(error: unknown): boolean {
  return error instanceof MedicaoApiError && error.code === STATE_MOVED_CODE;
}

/**
 * `true` quando o erro é o cancelamento de um `AbortController` — nunca falha de rede.
 * A busca incremental cancela a consulta anterior a cada tecla; sem esta distinção, cada
 * cancelamento apareceria na tela como `LOCAL_SERVER_UNREACHABLE`.
 */
export function isAbortError(error: unknown): boolean {
  return error instanceof DOMException && error.name === "AbortError";
}
