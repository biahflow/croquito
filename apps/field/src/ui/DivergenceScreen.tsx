import type { DivergenceView } from "./viewModel";

export interface DivergenceScreenProps {
  /** Rótulo do segmento conferido — "S2" na prancha 4b. */
  targetLabel: string;
  view: DivergenceView;
  onMeasureAgain: () => void;
  onJustify: () => void;
  busy: boolean;
}

/**
 * Prancha 4b — divergência entre duas medidas confirmadas do mesmo vínculo, acima da
 * tolerância. Nada é sobrescrito em silêncio: as duas leituras já estão persistidas, a
 * diferença é explicada por extenso e a saída é explícita — medir de novo ou registrar o
 * motivo e manter as duas.
 *
 * A divergência não é calculada aqui: ela vem do `MEASUREMENT_DIVERGENCE` que
 * `validateSurvey` apontou.
 */
export function DivergenceScreen({
  targetLabel,
  view,
  onMeasureAgain,
  onJustify,
  busy,
}: DivergenceScreenProps) {
  return (
    <div className="screen">
      <div className="content">
        <h1 className="screen-title">Conferência de {targetLabel}</h1>
        <p className="sub">Duas medidas confirmadas para o mesmo vínculo.</p>
        {view.readings.map((reading) => (
          <div className="card" key={reading.id}>
            <span className="card-meta">{reading.label}</span>
            <span className="card-title">{reading.value_label}</span>
          </div>
        ))}
        <div className="banner banner-error" role="status">
          <span>{view.message}</span>
        </div>
        <button
          type="button"
          className="btn btn-dark btn-block"
          onClick={onMeasureAgain}
          disabled={busy}
        >
          Medir de novo
        </button>
        <button type="button" className="btn btn-block" onClick={onJustify} disabled={busy}>
          Registrar motivo e manter as duas
        </button>
      </div>
    </div>
  );
}
