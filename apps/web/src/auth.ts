import { UserManager, WebStorageStateStore, type User } from "oidc-client-ts";

import { readRoute, routeSearch } from "./route";

const authority = import.meta.env.VITE_OIDC_AUTHORITY;
const clientId = import.meta.env.VITE_OIDC_CLIENT_ID;
const browser = typeof window !== "undefined";

/**
 * Onde esta SPA está montada: `/` em desenvolvimento, `/revisao/` no build servido pelo
 * nginx do host público. O `redirect_uri` precisa ser esse caminho, e não a raiz do host:
 * o realm de homologação autoriza `/revisao/*` e `/medicao/*`, então voltar para `/`
 * seria recusado pelo Keycloak antes de o login fechar.
 */
const basePath = import.meta.env.BASE_URL;

const manager = browser && authority && clientId
  ? new UserManager({
      authority,
      client_id: clientId,
      redirect_uri: `${window.location.origin}${basePath}`,
      post_logout_redirect_uri: `${window.location.origin}${basePath}`,
      response_type: "code",
      scope: "openid profile",
      // O access token do Keycloak dura 5 min por padrão; uma sessão de revisão dura
      // muito mais. Sem renovação, o próximo POST falha com 401 no meio do trabalho.
      automaticSilentRenew: true,
      // A renovação roda num iframe oculto. SEM esta URI dedicada, o iframe cai no
      // `redirect_uri` e carrega a SPA INTEIRA — que processa o código da renovação como
      // login, troca-o pelo caminho errado e nunca responde ao pai (incidente de
      // 2026-08-19 em homologação). A página é entry própria do MESMO build (D2 do
      // ADR-0032 preservado) e está coberta pelos `redirectUris` existentes
      // (`/revisao/*`); nenhum realm muda.
      silent_redirect_uri: `${window.location.origin}${basePath}silent-renew.html`,
      userStore: new WebStorageStateStore({ store: window.sessionStorage }),
    })
  : null;

export function isOidcConfigured(): boolean {
  return manager !== null;
}

/** Entrega o token renovado para quem já está com uma sessão de revisão aberta. */
export function onSessionRenewed(listener: (user: User) => void): () => void {
  if (!manager) {
    return () => undefined;
  }
  manager.events.addUserLoaded(listener);
  return () => manager.events.removeUserLoaded(listener);
}

/**
 * O `state` do OIDC volta como foi mandado. Só o `job` interessa, e ele é lido com
 * desconfiança: qualquer outra forma vira "não veio job". Nada daqui é registrado.
 */
export function searchFromState(state: unknown): string | null {
  if (typeof state !== "object" || state === null) {
    return null;
  }
  const carried = state as { search?: unknown; job?: unknown };
  if (typeof carried.search === "string" && carried.search) {
    return carried.search;
  }
  // Forma antiga do `state`, de quando só a jornada do croqui existia. Continua aceita
  // porque um login iniciado antes desta build pode estar em voo agora, no navegador de
  // alguém: o `state` viaja pelo Keycloak e volta depois do deploy.
  const job = carried.job;
  return typeof job === "string" && job ? `?job=${encodeURIComponent(job)}` : null;
}

/**
 * Limpa os parâmetros do retorno do OIDC e devolve à URL a JORNADA que o profissional
 * estava abrindo — sem isso o `?job` ou o `?rodada` do link se perde no redirect e ele
 * reencontra a lista de projetos em vez do croqui, ou o croqui em vez da medição.
 *
 * O que viaja no `state` é a query canônica da rota (`route.ts`), e não só o job: desde a
 * casca de duas jornadas, devolver apenas o `job` mandaria quem abriu um link de medição
 * sem sessão para a jornada errada depois do login.
 *
 * A URL é lida AGORA, e não antes do `await`: em desenvolvimento o React monta o efeito
 * duas vezes, a segunda chamada falha (o código de autorização é de uso único) e
 * reescrever com a foto velha apagaria a rota que a primeira acabou de devolver.
 * Medido no smoke headless contra o stack local, que era o único a alcançar o redirect.
 */
export function mergedSearchAfterRedirect(
  currentSearch: string,
  carriedSearch: string | null,
): string {
  const params = new URLSearchParams(currentSearch);
  const carried = new URLSearchParams(carriedSearch ?? "");
  for (const [name, value] of carried) {
    // A URL corrente manda: se o profissional já está numa jornada declarada, o `state`
    // não a sequestra. Ele só repõe o que o redirect apagou.
    if (!params.has(name)) {
      params.set(name, value);
    }
  }
  for (const param of ["code", "state", "session_state", "iss"]) {
    params.delete(param);
  }
  const query = params.toString();
  return query ? `?${query}` : "";
}

function restoreUrlAfterRedirect(carriedSearch: string | null): void {
  const query = mergedSearchAfterRedirect(window.location.search, carriedSearch);
  window.history.replaceState(null, "", query || window.location.pathname);
}

export async function readSession(): Promise<User | null> {
  if (!manager) {
    return null;
  }
  const params = new URLSearchParams(window.location.search);
  let callbackFailure: unknown = null;
  if (params.has("code") && params.has("state")) {
    let redirected: User | null = null;
    try {
      // Um código de autorização, UMA troca: em desenvolvimento o React monta o efeito
      // duas vezes, e duas chamadas concorrentes gastariam o código de uso único — a
      // segunda falha com "Code not valid" e vira aviso falso na porta. O promise é
      // compartilhado no módulo para todo montador aguardar a mesma troca.
      sharedRedirectCallback ??= manager.signinRedirectCallback();
      redirected = await sharedRedirectCallback;
      return redirected;
    } catch (error) {
      // Código de autorização é de uso único. Recarregar a página com ele ainda na
      // URL reenvia um código já gasto ("Code not valid"); cair para a sessão
      // armazenada é melhor do que derrubar a tela inteira. Mas a falha fica
      // GUARDADA: se não houver sessão armazenada para cair, engolir o erro aqui
      // vira um loop silencioso — o rebote da porta (ADR-0032, D4) manda de volta
      // para /login sem nenhuma mensagem, o SSO devolve um código novo, a troca
      // falha de novo, e ninguém vê o porquê. Incidente real de 2026-08-19.
      callbackFailure = error;
    } finally {
      restoreUrlAfterRedirect(searchFromState(redirected?.state));
    }
  }
  const user = await manager.getUser();
  const alive = user !== null && !user.expired ? user : null;
  if (user?.expired) {
    await manager.removeUser();
  }
  if (alive === null && callbackFailure !== null) {
    // Falha real de callback, sem sessão viva para amortecê-la: sobe para a casca, que
    // a transforma em aviso visível na porta em vez de rebote mudo.
    throw callbackFailure instanceof Error ? callbackFailure : new Error(String(callbackFailure));
  }
  return alive;
}

/** Troca única do código de autorização, compartilhada entre montagens do efeito. */
let sharedRedirectCallback: Promise<User> | null = null;

/**
 * Renova o access token sob demanda. A renovação agendada corre contra o relógio;
 * uma decisão enviada no instante da expiração ainda pegaria o token velho.
 */
let lastRenewFailure: string | null = null;

export async function renewAccessToken(): Promise<string | null> {
  if (!manager) {
    return null;
  }
  try {
    const user = await manager.signinSilent();
    if (!user?.access_token) {
      lastRenewFailure = "renovação não devolveu access token";
      return null;
    }
    lastRenewFailure = null;
    return user.access_token;
  } catch (error) {
    lastRenewFailure = error instanceof Error ? error.message : String(error);
    return null;
  }
}

/** Sem isto, uma renovação quebrada aparece só como INVALID_TOKEN genérico. */
export function readLastRenewFailure(): string | null {
  return lastRenewFailure;
}

export async function clearSession(): Promise<void> {
  await manager?.removeUser();
}

export async function signIn(): Promise<void> {
  if (!manager) {
    throw new Error("OIDC não está configurado neste ambiente.");
  }
  // O `redirect_uri` é fixo na base da SPA; a jornada aberta viaja no `state` e é
  // devolvida à URL por `readSession`. Objeto simples de propósito: o `state` trafega
  // serializado. Vai a query canônica inteira, e não só o job, porque a medição também é
  // uma jornada endereçável e um link dela precisa sobreviver ao login.
  const search = routeSearch(readRoute(window.location.search));
  await manager.signinRedirect(search ? { state: { search } } : undefined);
}

export async function signOut(): Promise<void> {
  if (!manager) {
    return;
  }
  await manager.signoutRedirect();
}
