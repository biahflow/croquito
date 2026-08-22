import { surveyWaivers, type Survey, type Waiver } from "../domain/types";
import { summarize, type Finding } from "../domain/validation";
import type { Notice } from "./notice";
import { segmentLabels } from "./viewModel";

export interface ConcludeScreenProps {
  survey: Survey;
  findings: readonly Finding[];
  notice: Notice | null;
  /** Toque num crítico de segmento (`SEGMENT_WITHOUT_MEASUREMENT`) — leva à coleta com o
   * segmento já selecionado (Task Contract T5, Especificação §1). */
  onSegmentFindingTap: (segmentId: string) => void;
  /** Abre a entrada de texto do motivo para uma pendência de atenção sem waiver ainda. */
  onJustify: (finding: Finding) => void;
  onConclude: () => void;
  onCancel: () => void;
  busy: boolean;
}

/** `ref_key` do waiver de um finding: o primeiro `ref`, ou o próprio código quando o
 * finding não tem refs (mesma regra do comando `waiveFinding`, Task Contract T5). */
function findingRefKey(finding: Finding): string {
  return finding.refs[0] ?? finding.code;
}

function waiverFor(waivers: readonly Waiver[], finding: Finding): Waiver | undefined {
  const refKey = findingRefKey(finding);
  return waivers.find(
    (waiver) => waiver.finding_code === finding.code && waiver.ref_key === refKey,
  );
}

function pluralize(count: number, singular: string, plural: string): string {
  return count === 1 ? singular : plural;
}

function findingKey(finding: Finding): string {
  return `${finding.code}:${finding.refs.join(",")}`;
}

/**
 * Prancha 5 — validação e conclusão: os findings do motor, sempre escritos pelo
 * semáforo crítico/atenção/ok (Task Contract T5, Especificação §1). Crítico bloqueia o
 * botão com o motivo no próprio rótulo (5a); atenção sobrevive justificada (5b). Nada
 * aqui recalcula validação — `findings` vem de `validateSurvey` e o resumo, de
 * `summarize` (Especificação §3); "área derivada" da prancha 5a não existe no motor e
 * fica de fora (Out of Scope).
 */
export function ConcludeScreen({
  survey,
  findings,
  notice,
  onSegmentFindingTap,
  onJustify,
  onConclude,
  onCancel,
  busy,
}: ConcludeScreenProps) {
  const waivers = surveyWaivers(survey);
  const criticals = findings.filter((finding) => finding.severity === "critical");
  const warnings = findings.filter((finding) => finding.severity === "warning");
  const summary = summarize(survey, [...findings]);
  const segmentLabelById = segmentLabels(survey.segments);
  const canConcludeNow = criticals.length === 0;

  const confirmLabel = canConcludeNow
    ? "Concluir levantamento"
    : `Concluir (${criticals.length} ${pluralize(
        criticals.length,
        "item crítico aberto",
        "itens críticos abertos",
      )})`;

  const summaryDetail = `${summary.confirmed_measurements} ${pluralize(
    summary.confirmed_measurements,
    "medida confirmada",
    "medidas confirmadas",
  )} · ${summary.segments} ${pluralize(summary.segments, "segmento", "segmentos")}`;

  return (
    <div className="screen">
      <div className="content">
        <h1 className="screen-title">Concluir levantamento</h1>
        {notice !== null && (
          <div className={`banner banner-${notice.tone}`} role="status">
            <span>{notice.text}</span>
          </div>
        )}
        {criticals.map((finding) => {
          const isSegmentFinding = finding.code === "SEGMENT_WITHOUT_MEASUREMENT";
          const segmentId = finding.refs[0];
          if (isSegmentFinding && segmentId !== undefined) {
            const segmentLabel = segmentLabelById.get(segmentId) ?? "segmento";
            return (
              <button
                key={findingKey(finding)}
                type="button"
                className="check check-error"
                style={{ width: "100%", textAlign: "left", cursor: "pointer" }}
                onClick={() => onSegmentFindingTap(segmentId)}
                disabled={busy}
              >
                <span className="check-state" />
                <div className="check-body">
                  <b className="check-title">Crítico — {segmentLabel} sem medida</b>
                  <small className="check-detail">{finding.message}</small>
                  <br />
                  <small className="check-detail">
                    Toque para ir direto ao segmento no desenho
                  </small>
                </div>
              </button>
            );
          }
          return (
            <div key={findingKey(finding)} className="check check-error">
              <span className="check-state" />
              <div className="check-body">
                <b className="check-title">Crítico</b>
                <small className="check-detail">{finding.message}</small>
              </div>
            </div>
          );
        })}
        {warnings.map((finding) => {
          const waiver = waiverFor(waivers, finding);
          return (
            <div key={findingKey(finding)} className="check check-warn">
              <span className="check-state" />
              <div className="check-body">
                <b className="check-title">Atenção</b>
                <small className="check-detail">{finding.message}</small>
                {waiver !== undefined ? (
                  <>
                    <br />
                    <small className="check-detail">
                      Justificativa: &quot;{waiver.justification}&quot;
                    </small>
                  </>
                ) : (
                  <>
                    <br />
                    <small className="check-detail">
                      Pendência não crítica: pode concluir com justificativa
                    </small>
                    <button
                      type="button"
                      className="btn"
                      onClick={() => onJustify(finding)}
                      disabled={busy}
                    >
                      Justificar
                    </button>
                  </>
                )}
              </div>
            </div>
          );
        })}
        <div className={`check ${canConcludeNow ? "check-ok" : "check-todo"}`}>
          <span className="check-state" />
          <div className="check-body">
            <b className="check-title">
              {canConcludeNow ? "Sem itens críticos" : "Resumo do levantamento"}
            </b>
            <small className="check-detail">{summaryDetail}</small>
          </div>
        </div>
        {canConcludeNow && (
          <div className="banner banner-ok" role="status">
            <span>
              Pronto para concluir. Os dados ficam guardados neste aparelho; o envio
              chega com a sincronização.
            </span>
          </div>
        )}
        <button
          type="button"
          className="btn btn-primary btn-block"
          disabled={!canConcludeNow || busy}
          onClick={onConclude}
        >
          {confirmLabel}
        </button>
        <button type="button" className="btn btn-block" onClick={onCancel} disabled={busy}>
          Voltar à coleta
        </button>
      </div>
    </div>
  );
}
