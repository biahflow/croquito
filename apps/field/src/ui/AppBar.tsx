import { identityStateLabel, isExpiredState, type IdentityState } from "../auth";

export interface IdentityBarProps {
  state: IdentityState;
  /** Nome (ou usuário/subject como alternativa) da sessão OIDC — `null` só em
   * `signed_out`, quando não há sessão nenhuma para nomear. Continua presente em
   * `expired_offline`/`reauth_required`: expiração não apaga a identidade, só o access
   * token (Task Contract T10). */
  displayName: string | null;
  /** `true` quando a sessão está carregada mas a claim `realm_access.roles` não contém
   * `field_technician` — aviso somente informativo; quem autoriza de verdade é o
   * backend a cada chamada, o app nunca bloqueia a coleta por isto. */
  missingRole: boolean;
  onAction: () => void;
}

export interface AppBarProps {
  title: string;
  /** Operações do outbox ainda não reconhecidas pelo servidor. */
  pendingCount: number;
  isOnline: boolean;
  /** `null` quando o OIDC não está configurado neste ambiente (sem `VITE_OIDC_*`) — o
   * app opera em modo local, sem identidade, exatamente como antes desta tarefa. */
  identity: IdentityBarProps | null;
}

/**
 * Barra superior escura de todas as telas (pacote aprovado, transversal): pílula
 * Online/Offline de alto contraste, contador de pendências e, desde a T10, o indicador
 * de identidade da prancha 6c — nome/estado do login e a ação "Entrar"/"Entrar
 * novamente" quando aplicável. Nunca é tela nova: cabe na mesma barra de sempre.
 */
export function AppBar({ title, pendingCount, isOnline, identity }: AppBarProps) {
  return (
    <header className="appbar">
      <span className="appbar-brand">{title}</span>
      {identity !== null && (
        <span className={`pill identity-pill${isExpiredState(identity.state) ? " identity-pill-warn" : ""}`}>
          {identity.displayName ?? identityStateLabel(identity.state)}
          {/* Quando há nome, o estado precisa vir escrito ao lado dele (regra 5 do Design
              System — cor nunca é o único portador de significado); sem nome, o texto
              principal já É o rótulo do estado, e repeti-lo aqui só duplicaria. */}
          {identity.displayName !== null && identity.state !== "active" && (
            <span className="identity-status"> · {identityStateLabel(identity.state)}</span>
          )}
          {identity.missingRole && <span className="identity-status"> · sem papel de técnico</span>}
        </span>
      )}
      <span className="appbar-spacer" />
      {identity !== null && identity.state !== "active" && (
        <button type="button" className="btn btn-primary identity-action" onClick={identity.onAction}>
          {isExpiredState(identity.state) ? "Entrar novamente" : "Entrar"}
        </button>
      )}
      {pendingCount > 0 && (
        <span className="pill pill-queue">
          {pendingCount} {pendingCount === 1 ? "pendente" : "pendentes"}
        </span>
      )}
      <span className={`pill ${isOnline ? "pill-online" : "pill-offline"}`}>
        <span className="pill-dot" />
        {isOnline ? "Online" : "Offline"}
      </span>
    </header>
  );
}
