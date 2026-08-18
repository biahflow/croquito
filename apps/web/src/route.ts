/**
 * Fronteira entre as duas jornadas do app: a revisão do croqui e a medição de obra.
 * Módulo puro, sem DOM e sem lib de router — quem tem `window` (a casca) lê a query e
 * pergunta aqui qual jornada abrir; quem navega pede a query canônica de volta.
 *
 * Duas regras carregam o desenho:
 *
 * - O croqui é a jornada sem marca. `?job=<uuid>` e a raiz da SPA continuam abrindo a
 *   revisão exatamente como antes desta casca existir — é o que preserva todo link já
 *   publicado, inclusive o que o smoke headless persegue através do redirect do OIDC.
 * - A medição é declarada por `?rodada`. Aí quem manda é a PRESENÇA do parâmetro, não o
 *   valor: `?rodada=` é "jornada de medição, nenhuma rodada aberta", um estado que
 *   precisa ser representável na URL para sobreviver a um reload.
 *
 * Parâmetro desconhecido não é jornada e não é preservado: `routeSearch` escreve só o que
 * `Route` carrega, então navegar limpa a query de tudo que não seja a jornada.
 */

export type Route =
  | { readonly kind: "croqui"; readonly jobId: string }
  | { readonly kind: "medicao"; readonly roundId: string };

/** Nome histórico do parâmetro da revisão; mudá-lo quebraria links já entregues. */
export const JOB_PARAM = "job";

/** Marca da medição, em português como o resto do vocabulário dessa jornada. */
export const ROUND_PARAM = "rodada";

/**
 * `search` é a query com ou sem `?` (aceita `window.location.search` direto).
 *
 * Com os dois parâmetros presentes o croqui vence. Não é sorteio nem ordem de leitura:
 * o link do croqui é o que já circula, e um `?rodada` colado depois dele não pode
 * sequestrar a revisão que o profissional pediu.
 */
export function readRoute(search: string): Route {
  const params = new URLSearchParams(search);
  // `?job=` vazio não abre revisão nenhuma; vale como parâmetro ausente.
  const jobId = params.get(JOB_PARAM);
  if (jobId) {
    return { kind: "croqui", jobId };
  }
  const roundId = params.get(ROUND_PARAM);
  if (roundId !== null) {
    return { kind: "medicao", roundId };
  }
  return { kind: "croqui", jobId: "" };
}

/**
 * Query canônica da rota, com `?` quando há algo a escrever e `""` quando não há. As
 * formas canônicas são `""`, `?job=<id>`, `?rodada=` e `?rodada=<id>`, e para elas
 * `routeSearch(readRoute(s)) === s`.
 */
export function routeSearch(route: Route): string {
  const params = new URLSearchParams();
  if (route.kind === "croqui") {
    if (!route.jobId) {
      return "";
    }
    params.set(JOB_PARAM, route.jobId);
  } else {
    params.set(ROUND_PARAM, route.roundId);
  }
  return `?${params.toString()}`;
}
