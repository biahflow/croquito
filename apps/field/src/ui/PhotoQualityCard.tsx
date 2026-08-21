import { photoQualityWarnTagText, type PhotoQualityWarnVerdict } from "./photoQualityGate";

export interface PhotoQualityCardProps {
  fileName: string;
  verdict: PhotoQualityWarnVerdict;
  busy: boolean;
  /** Descarta a captura atual (ainda não ancorada/persistida) e reabre a câmera. */
  onRedo: () => void;
  /** Segue o fluxo existente (persiste a foto exatamente como se não houvesse aviso). */
  onKeep: () => void;
}

/**
 * Prancha 7b da DAP rev.2 — aviso de qualidade de foto calculado NO APARELHO, não
 * bloqueante: o técnico decide, e "Manter assim mesmo" nunca vira erro depois (Task
 * Contract T15, Goal). Usado pelas duas capturas (`PhotoAnchorScreen` e `ArrivalScreen`)
 * só quando `assessPhotoQuality` devolve um veredito diferente de "ok" — foto ok segue
 * direto, sem este card.
 */
export function PhotoQualityCard({ fileName, verdict, busy, onRedo, onKeep }: PhotoQualityCardProps) {
  return (
    <div className="card">
      <span className="card-meta">📷 {fileName}</span>
      <span className="tag tag-warn">{photoQualityWarnTagText(verdict)}</span>
      <div className="banner banner-warn" role="status">
        <span>
          Verificação feita neste aparelho, sem internet. Refazer agora evita voltar ao
          local por foto ilegível — mas a decisão é sua: nada bloqueia.
        </span>
      </div>
      <button type="button" className="btn btn-primary btn-block" onClick={onRedo} disabled={busy}>
        Refazer a foto
      </button>
      <button type="button" className="btn btn-block" onClick={onKeep} disabled={busy}>
        Manter assim mesmo
      </button>
    </div>
  );
}
