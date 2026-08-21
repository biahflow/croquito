import { User } from "oidc-client-ts";
import { afterEach, describe, expect, it, vi } from "vitest";

import { createAuthClient, type SessionManagerLike } from "./oidcClient";

/** Codifica um payload de JWT em base64url — só o suficiente para `decodeJwtPayload`
 * (uso interno de `oidcClient.ts`) reconstituir as claims; header e assinatura não
 * importam porque o módulo nunca verifica assinatura (isso é dever do backend). */
function fakeAccessToken(payload: Record<string, unknown>): string {
  const base64url = (value: unknown) =>
    btoa(JSON.stringify(value)).replaceAll("+", "-").replaceAll("/", "_").replace(/=+$/, "");
  return `${base64url({ alg: "none", typ: "JWT" })}.${base64url(payload)}.assinatura-nao-verificada`;
}

function fakeUser(args: {
  expired: boolean;
  sub?: string;
  name?: string;
  roles?: string[];
  tenant?: string;
}): User {
  const claims: Record<string, unknown> = {
    realm_access: { roles: args.roles ?? ["field_technician"] },
    tenant_id: args.tenant ?? "tenant-guaxindiba",
  };
  return new User({
    access_token: fakeAccessToken(claims),
    token_type: "Bearer",
    profile: {
      sub: args.sub ?? "tecnico-1",
      iss: "https://keycloak.test/realms/croquito",
      aud: "croquito-field",
      exp: 9_999_999_999,
      iat: 1_000_000_000,
      name: args.name,
      preferred_username: args.name,
    },
    // Passado (expirado) ou daqui a uma hora (válido) — o suficiente para a getter
    // `expired` do `User` real do oidc-client-ts decidir sozinha, sem reimplementar a
    // conta aqui.
    expires_at: args.expired ? 1_000 : Math.floor(Date.now() / 1000) + 3_600,
  });
}

/** Fake mínimo do `UserManager` — nenhuma chamada de rede, controlado pelo teste
 * (Task Contract T10, §5: "com UserManager fake — sem rede real"). */
class FakeManager implements SessionManagerLike {
  storedUser: User | null;
  silentRenewResult: User | null | "throw";
  signinRedirectCallbackResult: User | "throw";
  signInCalls = 0;
  signOutCalls = 0;

  constructor(args: {
    storedUser?: User | null;
    silentRenewResult?: User | null | "throw";
    signinRedirectCallbackResult?: User | "throw";
  }) {
    this.storedUser = args.storedUser ?? null;
    this.silentRenewResult = args.silentRenewResult ?? null;
    this.signinRedirectCallbackResult = args.signinRedirectCallbackResult ?? "throw";
  }

  async getUser(): Promise<User | null> {
    return this.storedUser;
  }

  async signinSilent(): Promise<User | null> {
    if (this.silentRenewResult === "throw") {
      // Sem rede: `signinSilent` do oidc-client-ts real rejeita a promise, nunca lança
      // string simples — o fake reproduz a MESMA forma.
      throw new Error("network unreachable");
    }
    return this.silentRenewResult;
  }

  async signinRedirect(): Promise<void> {
    this.signInCalls += 1;
  }

  async signoutRedirect(): Promise<void> {
    this.signOutCalls += 1;
  }

  async signinRedirectCallback(): Promise<User> {
    if (this.signinRedirectCallbackResult === "throw") {
      throw new Error("code not valid");
    }
    return this.signinRedirectCallbackResult;
  }
}

describe("getFreshAccessToken nos quatro estados de identidade", () => {
  it("signed_out: sem sessão armazenada, devolve AUTH_REAUTH_REQUIRED (nunca lança)", async () => {
    const client = createAuthClient(new FakeManager({ storedUser: null }));

    const result = await client.getFreshAccessToken();

    expect(result).toEqual({ ok: false, reason: "AUTH_REAUTH_REQUIRED" });
  });

  it("active: sessão válida devolve o token direto, sem tentar renovar", async () => {
    const user = fakeUser({ expired: false });
    const manager = new FakeManager({ storedUser: user, silentRenewResult: "throw" });
    const client = createAuthClient(manager);

    const result = await client.getFreshAccessToken();

    expect(result).toEqual({ ok: true, token: user.access_token });
  });

  it("expired_offline: renovação falha (sem rede) — estado tipado, não exceção", async () => {
    const user = fakeUser({ expired: true });
    const manager = new FakeManager({ storedUser: user, silentRenewResult: "throw" });
    const client = createAuthClient(manager);

    await expect(client.getFreshAccessToken()).resolves.toEqual({
      ok: false,
      reason: "AUTH_REAUTH_REQUIRED",
    });
  });

  it("reauth_required: renovação online devolve null (IdP exige login interativo)", async () => {
    const user = fakeUser({ expired: true });
    const manager = new FakeManager({ storedUser: user, silentRenewResult: null });
    const client = createAuthClient(manager);

    await expect(client.getFreshAccessToken()).resolves.toEqual({
      ok: false,
      reason: "AUTH_REAUTH_REQUIRED",
    });
  });

  it("token renovado com sucesso volta a ok:true", async () => {
    const expiredUser = fakeUser({ expired: true });
    const renewedUser = fakeUser({ expired: false });
    const manager = new FakeManager({
      storedUser: expiredUser,
      silentRenewResult: renewedUser,
    });
    const client = createAuthClient(manager);

    await expect(client.getFreshAccessToken()).resolves.toEqual({
      ok: true,
      token: renewedUser.access_token,
    });
  });
});

describe("readIdentityState", () => {
  it("deriva os quatro estados a partir do fake manager + flag online", async () => {
    const signedOut = createAuthClient(new FakeManager({ storedUser: null }));
    expect(await signedOut.readIdentityState(true)).toBe("signed_out");

    const active = createAuthClient(new FakeManager({ storedUser: fakeUser({ expired: false }) }));
    expect(await active.readIdentityState(false)).toBe("active");

    const expired = createAuthClient(new FakeManager({ storedUser: fakeUser({ expired: true }) }));
    expect(await expired.readIdentityState(false)).toBe("expired_offline");
    expect(await expired.readIdentityState(true)).toBe("reauth_required");
  });
});

describe("readIdentity", () => {
  it("expiração nunca é logout: a identidade permanece legível com o token vencido", async () => {
    const user = fakeUser({
      expired: true,
      sub: "tecnico-2",
      name: "Cria da Toca",
      roles: ["field_technician", "outro_papel"],
      tenant: "tenant-toca",
    });
    const client = createAuthClient(new FakeManager({ storedUser: user }));

    await expect(client.readIdentity()).resolves.toEqual({
      subject: "tecnico-2",
      name: "Cria da Toca",
      roles: ["field_technician", "outro_papel"],
      tenant: "tenant-toca",
    });
  });

  it("sem sessão devolve null", async () => {
    const client = createAuthClient(new FakeManager({ storedUser: null }));

    await expect(client.readIdentity()).resolves.toBeNull();
  });

  it("expõe o aviso de papel: papel ausente aparece nas roles lidas, sem bloquear nada", async () => {
    const user = fakeUser({ expired: false, roles: ["outro_papel"] });
    const client = createAuthClient(new FakeManager({ storedUser: user }));

    const identity = await client.readIdentity();

    expect(identity?.roles).toEqual(["outro_papel"]);
    expect(identity?.roles.includes("field_technician")).toBe(false);
  });
});

describe("app sem env OIDC continua operando (modo local)", () => {
  const client = createAuthClient(null);

  it("isOidcConfigured é false", () => {
    expect(client.isOidcConfigured()).toBe(false);
  });

  it("readIdentity/readIdentityState não quebram sem UserManager", async () => {
    await expect(client.readIdentity()).resolves.toBeNull();
    await expect(client.readIdentityState(true)).resolves.toBe("signed_out");
  });

  it("getFreshAccessToken devolve o estado tipado, nunca lança", async () => {
    await expect(client.getFreshAccessToken()).resolves.toEqual({
      ok: false,
      reason: "AUTH_REAUTH_REQUIRED",
    });
  });

  it("signOut não faz nada (sem manager) e signIn recusa explicitamente", async () => {
    await expect(client.signOut()).resolves.toBeUndefined();
    await expect(client.signIn()).rejects.toThrow("OIDC não está configurado");
  });
});

describe("completeSignInRedirect", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("sem code/state na URL, não chama o callback nem mexe no histórico", async () => {
    const replaceState = vi.fn();
    vi.stubGlobal("window", {
      location: { search: "", pathname: "/" },
      history: { replaceState },
    });
    const manager = new FakeManager({ signinRedirectCallbackResult: "throw" });
    const client = createAuthClient(manager);

    await client.completeSignInRedirect();

    expect(replaceState).not.toHaveBeenCalled();
  });

  it("com code/state, troca o código e limpa a URL do retorno do OIDC", async () => {
    const replaceState = vi.fn();
    vi.stubGlobal("window", {
      location: { search: "?code=abc&state=xyz&session_state=s&iss=https://kc", pathname: "/" },
      history: { replaceState },
    });
    const manager = new FakeManager({
      signinRedirectCallbackResult: fakeUser({ expired: false }),
    });
    const client = createAuthClient(manager);

    await client.completeSignInRedirect();

    expect(replaceState).toHaveBeenCalledWith(null, "", "/");
  });

  it("código já gasto (falha do callback) não propaga exceção", async () => {
    vi.stubGlobal("window", {
      location: { search: "?code=abc&state=xyz", pathname: "/" },
      history: { replaceState: vi.fn() },
    });
    const manager = new FakeManager({ signinRedirectCallbackResult: "throw" });
    const client = createAuthClient(manager);

    await expect(client.completeSignInRedirect()).resolves.toBeUndefined();
  });
});
