import { UserManager, WebStorageStateStore, type User } from "oidc-client-ts";

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
function jobFromState(state: unknown): string | null {
  if (typeof state !== "object" || state === null) {
    return null;
  }
  const job = (state as { job?: unknown }).job;
  return typeof job === "string" && job ? job : null;
}

/**
 * Limpa os parâmetros do retorno do OIDC e devolve à URL a revisão que o profissional
 * estava abrindo — sem isso o `?job` do link se perde no redirect e ele reencontra a
 * lista de projetos em vez do croqui.
 *
 * A URL é lida AGORA, e não antes do `await`: em desenvolvimento o React monta o efeito
 * duas vezes, a segunda chamada falha (o código de autorização é de uso único) e
 * reescrever com a foto velha apagaria o `job` que a primeira acabou de devolver.
 * Medido no smoke headless contra o stack local, que era o único a alcançar o redirect.
 */
function restoreUrlAfterRedirect(job: string | null): void {
  const params = new URLSearchParams(window.location.search);
  if (job && !params.has("job")) {
    params.set("job", job);
  }
  for (const param of ["code", "state", "session_state", "iss"]) {
    params.delete(param);
  }
  const query = params.toString();
  window.history.replaceState(
    null,
    "",
    query ? `?${query}` : window.location.pathname,
  );
}

export async function readSession(): Promise<User | null> {
  if (!manager) {
    return null;
  }
  const params = new URLSearchParams(window.location.search);
  if (params.has("code") && params.has("state")) {
    let redirected: User | null = null;
    try {
      redirected = await manager.signinRedirectCallback();
      return redirected;
    } catch {
      // Código de autorização é de uso único. Recarregar a página com ele ainda na
      // URL reenvia um código já gasto ("Code not valid"); cair para a sessão
      // armazenada é melhor do que derrubar a tela inteira.
    } finally {
      restoreUrlAfterRedirect(jobFromState(redirected?.state));
    }
  }
  const user = await manager.getUser();
  if (user?.expired) {
    await manager.removeUser();
    return null;
  }
  return user;
}

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
  // O `redirect_uri` é fixo na base da SPA; o job aberto viaja no `state` e é devolvido à
  // URL por `readSession`. Objeto simples de propósito: o `state` trafega serializado.
  const job = new URLSearchParams(window.location.search).get("job");
  await manager.signinRedirect(job ? { state: { job } } : undefined);
}

export async function signOut(): Promise<void> {
  if (!manager) {
    return;
  }
  await manager.signoutRedirect();
}
