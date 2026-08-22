import type { Survey, SurveyPointId } from "../domain/types";
import type { Finding } from "../domain/validation";
import type { Notice } from "./notice";
import { SurveyCanvas, type SurveyCanvasProps } from "./SurveyCanvas";
import type { MmPoint } from "./viewModel";

export interface CollectScreenProps {
  survey: Survey;
  findings: readonly Finding[];
  notice: Notice | null;
  /** Ação de escape do aviso (cancelar o modo de coleta em curso ou fechar o erro). */
  onCancelNotice: (() => void) | null;
  cancelNoticeLabel: string;
  selectedPointId: SurveyPointId | null;
  selectedSegmentId: string | null;
  onCanvasTap: ((point: MmPoint) => void) | null;
  onPointTap: ((pointId: SurveyPointId) => void) | null;
  onSegmentTap: ((segmentId: string) => void) | null;
  canUndo: boolean;
  onUndo: () => void;
  onOpenAddMenu: () => void;
  onMeasure: () => void;
  busy: boolean;
  /** Survey concluído (T5): coleta vira somente leitura — os três comandos da bottombar
   * ficam desabilitados. Sem tela nova; o aviso escrito chega pelo próprio `notice`. */
  readOnly: boolean;
}

/**
 * Prancha 3a — a tela principal: desenho dominando a tela e os três comandos embaixo, na
 * zona do polegar. "＋ Adicionar" é o único preenchimento verde (`--accent` com
 * `--accent-ink` por cima).
 */
export function CollectScreen({
  survey,
  findings,
  notice,
  onCancelNotice,
  cancelNoticeLabel,
  selectedPointId,
  selectedSegmentId,
  onCanvasTap,
  onPointTap,
  onSegmentTap,
  canUndo,
  onUndo,
  onOpenAddMenu,
  onMeasure,
  busy,
  readOnly,
}: CollectScreenProps) {
  const canvasProps: SurveyCanvasProps = {
    survey,
    findings,
    selectedPointId,
    selectedSegmentId,
    onCanvasTap,
    onPointTap,
    onSegmentTap,
  };

  return (
    <div className="screen">
      <div className="content" style={{ paddingBottom: 0 }}>
        {notice !== null && (
          <div className={`banner banner-${notice.tone}`} role="status">
            <span>{notice.text}</span>
            {onCancelNotice !== null && (
              <button type="button" className="banner-action" onClick={onCancelNotice}>
                {cancelNoticeLabel}
              </button>
            )}
          </div>
        )}
        <SurveyCanvas {...canvasProps} />
      </div>
      <div className="bottombar">
        <button
          type="button"
          className="btn"
          onClick={onUndo}
          disabled={!canUndo || busy || readOnly}
        >
          Desfazer
        </button>
        <button
          type="button"
          className="btn btn-primary"
          style={{ flex: 1.6 }}
          onClick={onOpenAddMenu}
          disabled={busy || readOnly}
        >
          ＋ Adicionar
        </button>
        <button type="button" className="btn" onClick={onMeasure} disabled={busy || readOnly}>
          Medir
        </button>
      </div>
    </div>
  );
}
