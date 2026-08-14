/**
 * Sessão OIDC da homologação hospedada da medição (ADR-0026).
 *
 * Este módulo é o espelho de `apps/web/src/auth.ts` — mesmo realm, mesmo client público
 * (`croquito-web`), mesmo armazenamento em `sessionStorage`. Ele não é compartilhado por
 * import porque os dois apps não compartilham build; é cópia declarada, como a paleta.
 *
 * Duas regras moram aqui:
 *
 * - **Sem OIDC configurado, nada muda.** É o caminho do desenvolvimento local
 *   (`croquito-valuation serve` na máquina do operador, ADR-0020): sem
 *   `VITE_OIDC_AUTHORITY`/`VITE_OIDC_CLIENT_ID` o gerenciador nem nasce, `isOidcConfigured()`
 *   devolve `false` e a tela funciona como sempre funcionou.
 * - **O `redirect_uri` é a base da SPA**, não a raiz do host: o realm de homologação
 *   autoriza `/revisao/*` e `/medicao/*`, e voltar para `/` seria recusado pelo Keycloak.
 */

import { UserManager, WebStorageStateStore, type User } from "oidc-client-ts";

const authority = import.meta.env.VITE_OIDC_AUTHORITY;
const clientId = import.meta.env.VITE_OIDC_CLIENT_ID;
const browser = typeof window !== "undefined";

/** `/` em desenvolvimento; `/medicao/` no build servido pelo nginx do host público. */
const basePath = import.meta.env.BASE_URL;

const manager =
  browser && authority && clientId
    ? new UserManager({
        authority,
        client_id: clientId,
        redirect_uri: `${window.location.origin}${basePath}`,
        post_logout_redirect_uri: `${window.location.origin}${basePath}`,
        response_type: "code",
        scope: "openid profile",
        // Uma homologação de medição dura muito mais que os 5 min do access token do
        // Keycloak; sem renovação, a próxima decisão falharia com 401 no meio do trabalho.
        automaticSilentRenew: true,
        userStore: new WebStorageStateStore({ store: window.sessionStorage }),
      })
    : null;

export function isOidcConfigured(): boolean {
  return manager !== null;
}

/** Entrega o token renovado para quem já está com a rodada aberta. */
export function onSessionRenewed(listener: (user: User) => void): () => void {
  if (!manager) {
    return () => undefined;
  }
  manager.events.addUserLoaded(listener);
  return () => manager.events.removeUserLoaded(listener);
}

/**
 * Tira da URL os parâmetros do retorno do OIDC, preservando o que já estava lá. Sem isso o
 * `code` gasto continuaria na barra de endereço e um recarregamento tentaria trocá-lo de
 * novo. Nada daqui é registrado.
 */
function restoreUrlAfterRedirect(): void {
  const params = new URLSearchParams(window.location.search);
  for (const param of ["code", "state", "session_state", "iss"]) {
    params.delete(param);
  }
  const query = params.toString();
  window.history.replaceState(null, "", query ? `?${query}` : window.location.pathname);
}

export async function readSession(): Promise<User | null> {
  if (!manager) {
    return null;
  }
  const params = new URLSearchParams(window.location.search);
  if (params.has("code") && params.has("state")) {
    try {
      return await manager.signinRedirectCallback();
    } catch {
      // Código de autorização é de uso único: recarregar a página com ele ainda na URL
      // reenvia um código já gasto. Cair para a sessão armazenada é melhor do que
      // derrubar a tela inteira.
    } finally {
      restoreUrlAfterRedirect();
    }
  }
  const user = await manager.getUser();
  if (user?.expired) {
    await manager.removeUser();
    return null;
  }
  return user;
}

export async function signIn(): Promise<void> {
  if (!manager) {
    throw new Error("OIDC não está configurado neste ambiente.");
  }
  await manager.signinRedirect();
}

export async function signOut(): Promise<void> {
  if (!manager) {
    return;
  }
  await manager.signoutRedirect();
}
