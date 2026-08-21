import { describe, expect, it } from "vitest";

import { deriveIdentityState, identityStateLabel, isExpiredState } from "./identityState";

/**
 * Ponto central da tarefa T10: token vencido NUNCA é logout. `expired_offline` e
 * `reauth_required` são o mesmo fato (sessão vencida) sob duas circunstâncias de rede —
 * a coleta continua íntegra nos dois; só muda o que o app pode fazer no envio (T9).
 */
describe("deriveIdentityState", () => {
  it("sem sessão carregada é signed_out, online ou offline", () => {
    expect(deriveIdentityState({ hasSession: false, expired: false, online: true })).toBe(
      "signed_out",
    );
    expect(deriveIdentityState({ hasSession: false, expired: false, online: false })).toBe(
      "signed_out",
    );
    // Mesmo um `expired: true` teórico sem sessão não muda nada: sem sessão não há o que
    // vencer.
    expect(deriveIdentityState({ hasSession: false, expired: true, online: true })).toBe(
      "signed_out",
    );
  });

  it("sessão carregada e não vencida é active, independente de estar online", () => {
    expect(deriveIdentityState({ hasSession: true, expired: false, online: true })).toBe("active");
    expect(deriveIdentityState({ hasSession: true, expired: false, online: false })).toBe("active");
  });

  it("sessão vencida com rede é reauth_required", () => {
    expect(deriveIdentityState({ hasSession: true, expired: true, online: true })).toBe(
      "reauth_required",
    );
  });

  it("sessão vencida sem rede é expired_offline — a coleta não é bloqueada por isto", () => {
    expect(deriveIdentityState({ hasSession: true, expired: true, online: false })).toBe(
      "expired_offline",
    );
  });

  it("transição: active -> expired_offline ao vencer o token offline", () => {
    const active = deriveIdentityState({ hasSession: true, expired: false, online: false });
    const afterExpiry = deriveIdentityState({ hasSession: true, expired: true, online: false });
    expect(active).toBe("active");
    expect(afterExpiry).toBe("expired_offline");
  });

  it("transição: expired_offline -> reauth_required ao a rede voltar, sem novo login", () => {
    const offline = deriveIdentityState({ hasSession: true, expired: true, online: false });
    const backOnline = deriveIdentityState({ hasSession: true, expired: true, online: true });
    expect(offline).toBe("expired_offline");
    expect(backOnline).toBe("reauth_required");
  });

  it("transição: reauth_required -> active após renovar (mesma sessão, expired vira false)", () => {
    const beforeRenew = deriveIdentityState({ hasSession: true, expired: true, online: true });
    const afterRenew = deriveIdentityState({ hasSession: true, expired: false, online: true });
    expect(beforeRenew).toBe("reauth_required");
    expect(afterRenew).toBe("active");
  });

  it("transição: signed_out -> active após login (hasSession vira true)", () => {
    const before = deriveIdentityState({ hasSession: false, expired: false, online: true });
    const after = deriveIdentityState({ hasSession: true, expired: false, online: true });
    expect(before).toBe("signed_out");
    expect(after).toBe("active");
  });
});

describe("identityStateLabel", () => {
  it("tem um rótulo em português para cada estado", () => {
    expect(identityStateLabel("signed_out")).toBe("Não identificado");
    expect(identityStateLabel("active")).toBe("Sessão ativa");
    expect(identityStateLabel("expired_offline")).toBe("Sessão vencida (offline)");
    expect(identityStateLabel("reauth_required")).toBe("Reautenticação necessária");
  });
});

describe("isExpiredState", () => {
  it("só os dois estados vencidos pedem a ação 'Entrar novamente'", () => {
    expect(isExpiredState("expired_offline")).toBe(true);
    expect(isExpiredState("reauth_required")).toBe(true);
    expect(isExpiredState("signed_out")).toBe(false);
    expect(isExpiredState("active")).toBe(false);
  });
});
