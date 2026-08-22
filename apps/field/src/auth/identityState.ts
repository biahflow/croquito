/**
 * Máquina de estados da identidade do técnico em campo (ADR-0043 / Task Contract T10,
 * prancha 6c). Módulo puro e testável: nenhuma dependência de `oidc-client-ts`, `react`
 * nem de rede — só deriva o estado a partir dos fatos que `oidcClient.ts` observa.
 *
 * A regra central da tarefa vive aqui: expiração NUNCA é logout. `expired_offline` e
 * `reauth_required` são o mesmo fato (token de acesso vencido) sob duas circunstâncias
 * de rede diferentes — a coleta local continua íntegra nos dois; só o envio (T9) exige
 * `active`.
 */
export type IdentityState = "signed_out" | "active" | "expired_offline" | "reauth_required";

export interface IdentityStateInput {
  /** Existe uma sessão carregada do armazenamento local (`localStorage`), mesmo vencida. */
  hasSession: boolean;
  /** O access token da sessão carregada está vencido (`User.expired` do oidc-client-ts). */
  expired: boolean;
  /** `navigator.onLine` no momento da leitura — não garante alcançar o IdP, só descarta
   * a tentativa quando o aparelho está declaradamente offline. */
  online: boolean;
}

/**
 * Deriva o estado atual a partir dos fatos observados. Determinística e total: toda
 * combinação de entrada mapeia para exatamente um dos quatro estados.
 */
export function deriveIdentityState(input: IdentityStateInput): IdentityState {
  if (!input.hasSession) {
    return "signed_out";
  }
  if (!input.expired) {
    return "active";
  }
  return input.online ? "reauth_required" : "expired_offline";
}

/** Rótulo em português para o indicador de identidade no shell (prancha 6c). */
export function identityStateLabel(state: IdentityState): string {
  switch (state) {
    case "signed_out":
      return "Não identificado";
    case "active":
      return "Sessão ativa";
    case "expired_offline":
      return "Sessão vencida (offline)";
    case "reauth_required":
      return "Reautenticação necessária";
  }
}

/** Só os estados vencidos aceitam a ação "Entrar novamente"; `signed_out` usa "Entrar". */
export function isExpiredState(state: IdentityState): boolean {
  return state === "expired_offline" || state === "reauth_required";
}
