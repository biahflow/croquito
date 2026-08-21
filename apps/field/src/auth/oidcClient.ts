import { UserManager, WebStorageStateStore, type User } from "oidc-client-ts";

import { deriveIdentityState, type IdentityState } from "./identityState";

const authority = import.meta.env.VITE_OIDC_AUTHORITY;
const clientId = import.meta.env.VITE_OIDC_CLIENT_ID;
const browser = typeof window !== "undefined";

/** Mesmo padrão de `apps/web/src/auth.ts`: em produção o build pode nascer sob um
 * subcaminho; `BASE_URL` cobre isso sem exigir uma env nova quando o app de campo
 * continuar servido na raiz do seu próprio host. */
const basePath = import.meta.env.BASE_URL;

/** Identidade exibida no shell — nunca usada para autorizar nada localmente; o backend
 * revalida o token a cada chamada (mesmas claims que `croquito_core/oidc.py:83-101` lê). */
export interface Identity {
  subject: string;
  name?: string;
  roles: string[];
  tenant: string;
}

export type AccessTokenResult =
  | { ok: true; token: string }
  | { ok: false; reason: "AUTH_REAUTH_REQUIRED" };

/** Subconjunto do `UserManager` do `oidc-client-ts` que este módulo consome — permite
 * injetar um fake nos testes (Task Contract T10, §5: "com UserManager fake — sem rede
 * real"), sem tocar o singleton real usado em produção. */
export interface SessionManagerLike {
  getUser(): Promise<User | null>;
  signinSilent(): Promise<User | null>;
  signinRedirect(): Promise<void>;
  signoutRedirect(): Promise<void>;
  signinRedirectCallback(): Promise<User>;
}

/**
 * Decodifica o payload de um JWT sem verificar assinatura — uso é só de EXIBIÇÃO
 * (nome, papel, tenant no indicador do shell); a validação de verdade é sempre do
 * backend, que confere assinatura, issuer e audience antes de aceitar qualquer chamada.
 * Nunca lança: token malformado devolve `null` e a UI cai para "sem papel declarado".
 */
function decodeJwtPayload(token: string): Record<string, unknown> | null {
  const segment = token.split(".")[1];
  if (segment === undefined) {
    return null;
  }
  try {
    const base64 = segment.replaceAll("-", "+").replaceAll("_", "/");
    const padded = base64 + "=".repeat((4 - (base64.length % 4)) % 4);
    const json = typeof atob === "function" ? atob(padded) : "";
    const parsed: unknown = JSON.parse(json);
    return typeof parsed === "object" && parsed !== null ? (parsed as Record<string, unknown>) : null;
  } catch {
    return null;
  }
}

function rolesFromClaims(claims: Record<string, unknown>): string[] {
  const realmAccess = claims.realm_access;
  if (typeof realmAccess !== "object" || realmAccess === null) {
    return [];
  }
  const roles = (realmAccess as { roles?: unknown }).roles;
  return Array.isArray(roles) ? roles.filter((role): role is string => typeof role === "string") : [];
}

function identityFromUser(user: User): Identity {
  const claims = decodeJwtPayload(user.access_token) ?? {};
  const tenant = typeof claims.tenant_id === "string" ? claims.tenant_id : "";
  return {
    subject: user.profile.sub,
    name: user.profile.name ?? user.profile.preferred_username,
    roles: rolesFromClaims(claims),
    tenant,
  };
}

export interface AuthClient {
  isOidcConfigured(): boolean;
  readIdentity(): Promise<Identity | null>;
  readIdentityState(online: boolean): Promise<IdentityState>;
  completeSignInRedirect(): Promise<void>;
  getFreshAccessToken(): Promise<AccessTokenResult>;
  signIn(): Promise<void>;
  signOut(): Promise<void>;
}

/**
 * Constrói o cliente de autenticação sobre um `SessionManagerLike` — a instância real
 * (condicional às envs `VITE_OIDC_*`) ou um fake de teste. Toda a lógica de estado mora
 * aqui; o módulo exporta funções já ligadas ao gerenciador real logo abaixo.
 */
export function createAuthClient(manager: SessionManagerLike | null): AuthClient {
  /** Troca única do código de autorização, compartilhada entre montagens do efeito
   * (mesmo defeito de duplo-mount do StrictMode que `apps/web/src/auth.ts` documenta). */
  let sharedRedirectCallback: Promise<User> | null = null;

  /** Lê a sessão armazenada tal como está — inclusive vencida. NUNCA remove a sessão por
   * expiração (diferença deliberada de `apps/web/src/auth.ts`, que apaga o usuário vencido
   * porque ali expiração é logout; aqui expiração é só estado, ponto central da tarefa). */
  async function loadStoredUser(): Promise<User | null> {
    if (!manager) {
      return null;
    }
    return manager.getUser();
  }

  async function readIdentity(): Promise<Identity | null> {
    const user = await loadStoredUser();
    return user === null ? null : identityFromUser(user);
  }

  async function readIdentityState(online: boolean): Promise<IdentityState> {
    const user = await loadStoredUser();
    return deriveIdentityState({
      hasSession: user !== null,
      expired: user?.expired ?? false,
      online,
    });
  }

  /**
   * Processa o retorno do Keycloak quando presente (`?code&state` na URL) e limpa esses
   * parâmetros depois. Sem `state` de rota para carregar de volta: o app de campo não tem
   * navegação por query string (a ordem ativa vive em `localStorage`,
   * `orders/activeOrder.ts`), então não há nada a devolver à URL além de removê-la do
   * retorno do OIDC. Uma falha aqui NUNCA é jogada adiante — um código de uso único já
   * gasto (duplo-mount, refresh com o código ainda na URL) apenas deixa a sessão
   * armazenada, se houver, ser lida do jeito que já é: por estado, nunca bloqueando a tela.
   */
  async function completeSignInRedirect(): Promise<void> {
    if (!manager || typeof window === "undefined") {
      return;
    }
    const params = new URLSearchParams(window.location.search);
    if (!params.has("code") || !params.has("state")) {
      return;
    }
    try {
      sharedRedirectCallback ??= manager.signinRedirectCallback();
      await sharedRedirectCallback;
    } catch {
      // Engolido de propósito: ver comentário da função.
    } finally {
      params.delete("code");
      params.delete("state");
      params.delete("session_state");
      params.delete("iss");
      const query = params.toString();
      window.history.replaceState(null, "", query ? `?${query}` : window.location.pathname);
    }
  }

  /** Renova o access token sob demanda. Falha silenciosa de propósito (offline, refresh
   * token também vencido): quem chama decide o que fazer com `null`, a sessão local não
   * é tocada. */
  async function renewAccessToken(): Promise<string | null> {
    if (!manager) {
      return null;
    }
    try {
      const user = await manager.signinSilent();
      return user?.access_token ?? null;
    } catch {
      return null;
    }
  }

  /**
   * Token pronto para a T9 usar no envio. Devolve um ESTADO tipado — nunca lança string
   * de exceção (Task Contract T10, Comportamento exigido §1) — porque
   * `AUTH_REAUTH_REQUIRED` não é uma falha inesperada do SyncEngine, é uma condição
   * normal e esperada do app de campo: o técnico pode ficar dias em campo com o login
   * vencido sem que isso seja um erro.
   */
  async function getFreshAccessToken(): Promise<AccessTokenResult> {
    if (!manager) {
      return { ok: false, reason: "AUTH_REAUTH_REQUIRED" };
    }
    const user = await manager.getUser();
    if (user === null) {
      return { ok: false, reason: "AUTH_REAUTH_REQUIRED" };
    }
    if (!user.expired) {
      return { ok: true, token: user.access_token };
    }
    const renewed = await renewAccessToken();
    return renewed === null
      ? { ok: false, reason: "AUTH_REAUTH_REQUIRED" }
      : { ok: true, token: renewed };
  }

  async function signIn(): Promise<void> {
    if (!manager) {
      throw new Error("OIDC não está configurado neste ambiente.");
    }
    await manager.signinRedirect();
  }

  async function signOut(): Promise<void> {
    if (!manager) {
      return;
    }
    await manager.signoutRedirect();
  }

  return {
    isOidcConfigured: () => manager !== null,
    readIdentity,
    readIdentityState,
    completeSignInRedirect,
    getFreshAccessToken,
    signIn,
    signOut,
  };
}

const realManager: SessionManagerLike | null =
  browser && authority && clientId
    ? new UserManager({
        authority,
        client_id: clientId,
        redirect_uri: `${window.location.origin}${basePath}`,
        post_logout_redirect_uri: `${window.location.origin}${basePath}`,
        response_type: "code",
        scope: "openid profile",
        // O access token dura poucos minutos; um levantamento em campo dura o turno
        // inteiro. A renovação automática só ajuda quando há rede — offline ela falha em
        // silêncio (ver `renewAccessToken`), e é exatamente esse silêncio que o estado
        // `expired_offline` torna visível sem derrubar a sessão local.
        automaticSilentRenew: true,
        // Entry PRÓPRIO do iframe de renovação. SEM esta URI dedicada, o iframe cai no
        // `redirect_uri` e carrega o app inteiro — que processaria o código da renovação
        // como login novo e nunca responderia ao pai (mesmo incidente de 2026-08-19 que
        // `apps/web/src/auth.ts` documenta; a causa é do `oidc-client-ts`, não específica
        // da SPA de revisão, e se repete aqui sem este entry).
        silent_redirect_uri: `${window.location.origin}${basePath}silent-renew.html`,
        // Diferença deliberada do escritório (Task Contract T10): `apps/web` guarda a
        // sessão em `sessionStorage` porque a jornada de revisão não sobrevive a fechar a
        // aba. O app de campo precisa sobreviver a reiniciar o aparelho dias depois,
        // offline — `localStorage` é o único dos dois que persiste por conta própria.
        userStore: new WebStorageStateStore({ store: window.localStorage }),
      })
    : null;

const client = createAuthClient(realManager);

export const isOidcConfigured = client.isOidcConfigured;
export const readIdentity = client.readIdentity;
export const readIdentityState = client.readIdentityState;
export const completeSignInRedirect = client.completeSignInRedirect;
export const getFreshAccessToken = client.getFreshAccessToken;
export const signIn = client.signIn;
export const signOut = client.signOut;
