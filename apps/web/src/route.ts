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
 *
 * Desde o ADR-0032 existe também UM estado de caminho, a porta de entrada (`/login`), e ele
 * é representado FORA de `Route`, numa camada acima da jornada: `Route` continua derivando
 * só da query, e o que entra aqui é a decisão pura de rebote (`entryRedirect`), que a casca
 * executa com `history.replaceState` depois de ler a sessão. A alternativa considerada era
 * um terceiro `kind` em `Route`; ela foi recusada porque `/login` não é jornada — não tem
 * forma canônica de query, não é alternável pelo seletor e não sobrevive a `routeSearch`.
 */

export type Route =
  | { readonly kind: "croqui"; readonly jobId: string }
  | { readonly kind: "medicao"; readonly roundId: string };

/** Nome histórico do parâmetro da revisão; mudá-lo quebraria links já entregues. */
export const JOB_PARAM = "job";

/** Marca da medição, em português como o resto do vocabulário dessa jornada. */
export const ROUND_PARAM = "rodada";

/**
 * Caminho da porta de entrada (ADR-0032, D1/D2). A borda serve nele o MESMO `index.html`
 * da SPA, com os assets continuando sob `BASE_URL`; em desenvolvimento o fallback do Vite
 * faz o mesmo. Ele é onde se CLICA para entrar e não é `redirect_uri` (D5): `/login` não
 * entra nos `redirectUris` de realm nenhum, e aparecer ali é sinal de desenho errado.
 */
export const LOGIN_PATH = "/login";

/**
 * Os parâmetros que o retorno do OIDC carrega na query. Quem os consome é `readSession()`
 * em `auth.ts`; aqui eles só são reconhecidos, nunca lidos nem registrados.
 */
const OIDC_RETURN_PARAMS = ["code", "state"] as const;

/** `/login/` digitado com barra é o mesmo lugar; a borda casa só a forma exata. */
function isLoginPath(pathname: string): boolean {
  return pathname === LOGIN_PATH || pathname === `${LOGIN_PATH}/`;
}

/** `""`, `"?"` e `"job=x"` são a mesma query escrita de três jeitos. */
function normalizeSearch(search: string): string {
  if (!search || search === "?") {
    return "";
  }
  return search.startsWith("?") ? search : `?${search}`;
}

/**
 * Para onde a URL corrente deve ser reescrita, ou `null` quando ela já está no lugar
 * certo. Função pura de propósito: a regra que fecha (ou não) um loop de login precisa ser
 * verificável sem DOM. Quem aplica o resultado é a casca, com `history.replaceState` —
 * redirecionar com reload jogaria fora o estado do OIDC, que vive em memória.
 *
 * `journeyPath` é onde a SPA está montada (`import.meta.env.BASE_URL`): `/revisao/` no
 * build servido pelo nginx, `/` em desenvolvimento.
 */
export function entryRedirect(
  location: { readonly pathname: string; readonly search: string },
  hasSession: boolean,
  journeyPath: string,
): string | null {
  const search = normalizeSearch(location.search);
  // A EXCEÇÃO VEM PRIMEIRO, e é decisão (ADR-0032, D4), não otimização. O retorno do OIDC
  // chega em `/revisao/?code=…&state=…` num instante em que ainda NÃO existe sessão em
  // memória: `readSession()` só a estabelece depois de `signinRedirectCallback()`. Rebater
  // essa URL manda o código de autorização para uma tela que não sabe gastá-lo e fecha um
  // loop de login que tranca todos para fora, inclusive quem consertaria.
  const params = new URLSearchParams(search);
  if (OIDC_RETURN_PARAMS.every((name) => params.has(name))) {
    return null;
  }
  if (!hasSession && !isLoginPath(location.pathname)) {
    // Vai a query ORIGINAL inteira, não a canônica da jornada: o `?job=<uuid>` do link
    // entregue precisa sobreviver ao salto para depois viajar no `state` do login.
    return `${LOGIN_PATH}${search}`;
  }
  if (hasSession && isLoginPath(location.pathname)) {
    return `${journeyPath}${search}`;
  }
  return null;
}

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
