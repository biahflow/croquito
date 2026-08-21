import { useState } from "react";

import type { Notice } from "./notice";
import {
  confirmMeasurementLabel,
  metersInputToMm,
  pressBackspace,
  pressComma,
  pressDigit,
} from "./viewModel";

const DIGIT_KEYS = ["7", "8", "9", "4", "5", "6", "1", "2", "3"] as const;

export interface MeasureScreenProps {
  /** Rótulo do destino da medida — o "S5" que o botão de confirmação repete. */
  targetLabel: string;
  /** "Comprimento · do ponto P4 ao ponto P5 · <instrumento>". */
  subtitle: string;
  notice: Notice | null;
  onConfirm: (valueMm: number) => void;
  onCancel: () => void;
  busy: boolean;
}

/**
 * Prancha 4a — registrar a medida: teclado numérico próprio, com vírgula, e um botão que
 * repete a frase inteira ("Confirmar 7,35 m para S5"). O técnico confirma valor e
 * destino, não um "OK" solto.
 *
 * O que está digitado é rascunho de tela; só a confirmação vira comando — e o comando
 * passa por `applyCommand`, que persiste antes de qualquer feedback.
 */
export function MeasureScreen({
  targetLabel,
  subtitle,
  notice,
  onConfirm,
  onCancel,
  busy,
}: MeasureScreenProps) {
  const [display, setDisplay] = useState("");
  const valueMm = metersInputToMm(display);

  return (
    <div className="screen">
      <div className="content">
        <h1 className="screen-title">Medir {targetLabel}</h1>
        <p className="sub">{subtitle}</p>
        {notice !== null && (
          <div className={`banner banner-${notice.tone}`} role="status">
            <span>{notice.text}</span>
          </div>
        )}
        <div className="numview">
          <span className={`numview-value ${display === "" ? "numview-value-empty" : ""}`}>
            {display === "" ? "0" : display}
          </span>
          <span className="numview-unit">m</span>
        </div>
        <div className="numpad">
          {DIGIT_KEYS.map((digit) => (
            <button
              key={digit}
              type="button"
              className="btn"
              onClick={() => setDisplay((current) => pressDigit(current, digit))}
            >
              {digit}
            </button>
          ))}
          <button
            type="button"
            className="btn"
            onClick={() => setDisplay((current) => pressComma(current))}
          >
            ,
          </button>
          <button
            type="button"
            className="btn"
            onClick={() => setDisplay((current) => pressDigit(current, "0"))}
          >
            0
          </button>
          <button
            type="button"
            className="btn"
            aria-label="Apagar último dígito"
            onClick={() => setDisplay((current) => pressBackspace(current))}
          >
            ⌫
          </button>
        </div>
        <button
          type="button"
          className="btn btn-primary btn-block"
          disabled={valueMm === null || busy}
          onClick={() => {
            if (valueMm !== null) {
              onConfirm(valueMm);
            }
          }}
        >
          {confirmMeasurementLabel(display, targetLabel)}
        </button>
        {/* Foto do visor é a fatia da câmera (T6); o rótulo diz o motivo do desabilitado. */}
        <button type="button" className="btn btn-block" disabled>
          Anexar foto do visor (em breve)
        </button>
        <button type="button" className="btn btn-block" onClick={onCancel} disabled={busy}>
          Cancelar
        </button>
      </div>
    </div>
  );
}
