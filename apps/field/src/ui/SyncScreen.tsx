import type { ConflictDecision, SyncState } from "../sync";
import {
  SYNC_RETENTION_NOTE,
  buildCategoryViews,
  buildConflictView,
  syncActionLabel,
  syncBanner,
  syncScreenTitle,
} from "./syncViewModel";

export interface SyncScreenProps {
  state: SyncState;
  surveyName: string;
  onSend: () => void;
  onResolveConflict: (decision: ConflictDecision) => void;
  onBack: () => void;
  busy: boolean;
}

/**
 * Prancha 6 — sincronização (6a) e conflito (6b).
 *
 * A tela não decide nada: as linhas de progresso, o aviso do topo e os dois lados do
 * conflito vêm de `syncViewModel.ts`, que por sua vez só escreve o que o motor apurou.
 * Todo estado sinalizado por cor está também escrito (regra 5 do Design System), e o
 * rodapé repete a garantia que sustenta a fatia inteira: nada local é apagado antes do
 * ack.
 *
 * Superfícies fora da prancha 6 não entram aqui: o estado de sessão vencida (6c) continua
 * no indicador do `AppBar` (T10) e o painel só o cita por escrito.
 */
export function SyncScreen({
  state,
  surveyName,
  onSend,
  onResolveConflict,
  onBack,
  busy,
}: SyncScreenProps) {
  const banner = syncBanner(state);
  const categories = buildCategoryViews(state);
  const conflict = state.phase === "conflict" && state.conflict !== null ? state.conflict : null;
  const conflictView = conflict === null ? null : buildConflictView(conflict);
  const sending =
    state.phase === "sending_metadata" ||
    state.phase === "sending_media" ||
    state.phase === "completing";
  const canSend = state.phase !== "local_mode" && conflict === null && !sending && !busy;

  return (
    <div className="screen">
      <div className="content">
        <h1 className="screen-title">{syncScreenTitle(state, surveyName)}</h1>
        {banner !== null && (
          <div className={`banner banner-${banner.tone}`} role="status">
            <span>{banner.text}</span>
          </div>
        )}

        {conflictView !== null ? (
          <>
            <div className="card">
              <span className="card-meta">{conflictView.local.origin}</span>
              {conflictView.local.meta !== "" && (
                <span className="card-meta">{conflictView.local.meta}</span>
              )}
              <b className="card-title">{conflictView.local.value}</b>
            </div>
            <div className="card">
              <span className="card-meta">{conflictView.server.origin}</span>
              {conflictView.server.meta !== "" && (
                <span className="card-meta">{conflictView.server.meta}</span>
              )}
              <b className="card-title">{conflictView.server.value}</b>
            </div>
            <button
              type="button"
              className="btn btn-dark btn-block"
              onClick={() => onResolveConflict("keep_local")}
              disabled={busy}
            >
              {conflictView.keep_label}
            </button>
            <button
              type="button"
              className="btn btn-block"
              onClick={() => onResolveConflict("accept_server")}
              disabled={busy}
            >
              {conflictView.accept_label}
            </button>
            <p className="sub">
              As duas versões continuam registradas: a decisão vira uma operação com
              justificativa no histórico do levantamento, e nenhuma leitura deste aparelho é
              apagada.
            </p>
          </>
        ) : (
          <>
            {categories.map((view) => (
              <div key={view.category} className={`check check-${view.tone}`}>
                <span className="check-state" />
                <div className="check-body">
                  <b className="check-title">{view.title}</b>
                  <small className="check-detail">{view.detail}</small>
                </div>
              </div>
            ))}
            {categories.length === 0 && (
              <div className="check check-todo">
                <span className="check-state" />
                <div className="check-body">
                  <b className="check-title">Nada a enviar por enquanto</b>
                  <small className="check-detail">
                    Assim que houver ações de coleta, elas aparecem aqui por categoria.
                  </small>
                </div>
              </div>
            )}
            <div className="banner banner-info" role="note">
              <span>{SYNC_RETENTION_NOTE}</span>
            </div>
            {state.phase !== "local_mode" && (
              <button
                type="button"
                className="btn btn-primary btn-block"
                onClick={onSend}
                disabled={!canSend}
              >
                {syncActionLabel(state)}
              </button>
            )}
          </>
        )}

        <button type="button" className="btn btn-block" onClick={onBack} disabled={busy}>
          Voltar à coleta
        </button>
      </div>
    </div>
  );
}
