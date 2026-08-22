/**
 * Backoff exponencial com jitter para as tentativas de envio (T9).
 *
 * A rede de campo não cai de vez: ela oscila. Repetir imediatamente queima bateria e a
 * janela de sinal; repetir sempre no mesmo instante faz vários aparelhos voltarem juntos
 * quando a antena volta. Daí exponencial + jitter, com limites nomeados em vez de números
 * soltos no meio do motor.
 *
 * Só falha TRANSITÓRIA repete (rede caiu, 5xx, 503 da fila). `4xx` não repete às cegas:
 * conflito, mídia não referenciada e digest divergente são decisões de contrato, e repetir
 * um pedido que o servidor já recusou por regra só atrasa o técnico.
 */

/** Tentativas de um mesmo lote dentro de uma passada de sincronização (1 envio + 3 retentativas). */
export const MAX_ATTEMPTS = 4;

/** Espera da primeira retentativa, antes do jitter. */
export const BASE_DELAY_MS = 500;

/** Teto da espera: acima disto o técnico já fechou o painel; a próxima passada resolve. */
export const MAX_DELAY_MS = 8_000;

/** Fração da espera sorteada (±25%) para dessincronizar aparelhos que voltam juntos. */
export const JITTER_RATIO = 0.25;

/**
 * Espera antes da tentativa `attempt` (1 = primeira retentativa). `random` é injetável
 * para o teste ser determinístico — nunca é fonte de decisão, só de dispersão.
 */
export function backoffDelayMs(attempt: number, random: () => number = Math.random): number {
  const exponential = Math.min(BASE_DELAY_MS * 2 ** Math.max(attempt - 1, 0), MAX_DELAY_MS);
  const jitter = exponential * JITTER_RATIO * (random() * 2 - 1);
  return Math.max(0, Math.round(exponential + jitter));
}
