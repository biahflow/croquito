import { useState } from "react";

import type { Notice } from "./notice";

export interface TextEntryScreenProps {
  title: string;
  description: string;
  label: string;
  placeholder: string;
  confirmLabel: string;
  /** Rótulo do botão desabilitado, dizendo o porquê (regra do pacote aprovado). */
  emptyConfirmLabel: string;
  notice: Notice | null;
  onConfirm: (text: string) => void;
  onCancel: () => void;
  busy: boolean;
}

/**
 * Entrada de texto de uma linha só de trabalho — observação de campo e motivo de
 * divergência.
 *
 * Composição montada com as primitivas já aprovadas (título de tela, campo da prancha 2,
 * botão primário e Cancelar da prancha 3b); o pacote aprovado não desenha uma prancha
 * própria para digitar texto, e inventar uma seria composição nova. Voz fica de fora: o
 * MVP registra observação só como texto (Feature Contract).
 */
export function TextEntryScreen({
  title,
  description,
  label,
  placeholder,
  confirmLabel,
  emptyConfirmLabel,
  notice,
  onConfirm,
  onCancel,
  busy,
}: TextEntryScreenProps) {
  const [text, setText] = useState("");
  const filled = text.trim().length > 0;

  return (
    <div className="screen">
      <div className="content">
        <h1 className="screen-title">{title}</h1>
        <p className="sub">{description}</p>
        {notice !== null && (
          <div className={`banner banner-${notice.tone}`} role="status">
            <span>{notice.text}</span>
          </div>
        )}
        <div className="field">
          <label className="field-label" htmlFor="text-entry">
            {label}
          </label>
          <textarea
            id="text-entry"
            className="field-input"
            rows={4}
            value={text}
            placeholder={placeholder}
            onChange={(event) => setText(event.target.value)}
          />
        </div>
        <button
          type="button"
          className="btn btn-primary btn-block"
          disabled={!filled || busy}
          onClick={() => onConfirm(text)}
        >
          {filled ? confirmLabel : emptyConfirmLabel}
        </button>
        <button type="button" className="btn btn-block" onClick={onCancel} disabled={busy}>
          Cancelar
        </button>
      </div>
    </div>
  );
}
