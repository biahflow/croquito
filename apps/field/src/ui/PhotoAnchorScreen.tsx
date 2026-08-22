import { useEffect, useReducer, useRef, useState } from "react";

import { evaluateCapturedPhoto } from "../photos/evaluateCapturedPhoto";
import { isStorageLow } from "../photos/quota";
import type { Notice } from "./notice";
import { PhotoQualityCard } from "./PhotoQualityCard";
import {
  INITIAL_PHOTO_QUALITY_GATE_STATE,
  photoQualityGateReducer,
} from "./photoQualityGate";

export interface PhotoAnchorScreenProps {
  /** Rótulo do ponto já escolhido como âncora (ex.: "P3") — a escolha acontece ANTES
   * desta tela, tocando o ponto no desenho (modo `pick-photo-point` em `FieldApp`). */
  pointLabel: string;
  notice: Notice | null;
  busy: boolean;
  onConfirm: (file: File) => void;
  onCancel: () => void;
}

/**
 * Fluxo "Foto ancorada" (Task Contract T6, Scope): a âncora já foi escolhida (tocar num
 * ponto do desenho); aqui só falta capturar o arquivo e confirmar — o comando
 * `addPhotoAnchor` só é chamado na confirmação (ver `FieldApp.handleConfirmPhotoAnchor`),
 * nunca antes.
 *
 * A captura usa `<input type="file" accept="image/*" capture="environment">` nativo do
 * aparelho — sem tela de câmera própria (fora do pacote aprovado) e sem
 * preview/visualizador da foto (Task Contract T6, Out of Scope): o nome do arquivo
 * confirma a escolha, a imagem em si nunca é exibida nem logada.
 *
 * Qualidade de foto (Task Contract T15, prancha 7b): assim que o arquivo é escolhido, a
 * avaliação roda em segundo plano (`evaluateCapturedPhoto`, resolução reduzida) — o toque
 * que capturou a foto não espera por ela (NFR ≤100ms). Enquanto isso, a tela mostra
 * "Avaliando…"; se o veredito não for "ok", o card de aviso substitui o botão
 * "Confirmar foto" (Refazer descarta e reabre a câmera; Manter segue exatamente o fluxo
 * de antes, chamando `onConfirm`). Foto "ok" (ou avaliação indisponível) segue direto.
 */
export function PhotoAnchorScreen({
  pointLabel,
  notice,
  busy,
  onConfirm,
  onCancel,
}: PhotoAnchorScreenProps) {
  const [gate, dispatch] = useReducer(photoQualityGateReducer, INITIAL_PHOTO_QUALITY_GATE_STATE);
  const [lowStorage, setLowStorage] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const file = gate.phase === "empty" ? null : gate.file;

  useEffect(() => {
    let cancelled = false;
    void isStorageLow().then((low) => {
      if (!cancelled) {
        setLowStorage(low);
      }
    });
    return () => {
      cancelled = true;
    };
  }, []);

  const handleFileSelected = (selected: File) => {
    dispatch({ type: "file-selected", file: selected });
    void evaluateCapturedPhoto(selected).then((outcome) => {
      dispatch({ type: "evaluated", file: selected, outcome });
    });
  };

  const handleRedo = () => {
    dispatch({ type: "reset" });
    // "reabre a câmera" (Task Contract T15): dispara o mesmo input nativo de novo, em vez
    // de exigir que o técnico ache o botão "Tirar foto" de novo na tela.
    inputRef.current?.click();
  };

  const handleKeep = () => {
    if (gate.phase === "warn") {
      onConfirm(gate.file);
    }
  };

  return (
    <div className="screen">
      <div className="content">
        <h1 className="screen-title">Foto ancorada — {pointLabel}</h1>
        <p className="sub">A foto fica vinculada a este ponto do desenho.</p>
        {notice !== null && (
          <div className={`banner banner-${notice.tone}`} role="status">
            <span>{notice.text}</span>
          </div>
        )}
        {lowStorage && (
          <div className="banner banner-warn" role="status">
            <span>
              Pouco espaço livre neste aparelho (menos de 50 MB) — a foto pode não ser
              gravada.
            </span>
          </div>
        )}
        {gate.phase !== "warn" && (
          <label className="btn btn-block" htmlFor="photo-anchor-file">
            {file === null ? "Tirar foto" : `Foto selecionada: ${file.name || "sem nome"}`}
          </label>
        )}
        <input
          id="photo-anchor-file"
          ref={inputRef}
          type="file"
          accept="image/*"
          capture="environment"
          style={{ display: "none" }}
          disabled={busy}
          onChange={(event) => {
            const selected = event.target.files?.[0];
            event.target.value = "";
            if (selected !== undefined) {
              handleFileSelected(selected);
            }
          }}
        />
        {gate.phase === "checking" && (
          <div className="banner banner-info" role="status">
            <span>Avaliando qualidade da foto…</span>
          </div>
        )}
        {gate.phase === "warn" ? (
          <PhotoQualityCard
            fileName={gate.file.name || "sem nome"}
            verdict={gate.verdict}
            busy={busy}
            onRedo={handleRedo}
            onKeep={handleKeep}
          />
        ) : (
          <button
            type="button"
            className="btn btn-primary btn-block"
            disabled={file === null || busy || gate.phase === "checking"}
            onClick={() => {
              if (file !== null) {
                onConfirm(file);
              }
            }}
          >
            {file === null ? "Confirmar (tire uma foto antes)" : "Confirmar foto"}
          </button>
        )}
        <button type="button" className="btn btn-block" onClick={onCancel} disabled={busy}>
          Cancelar
        </button>
      </div>
    </div>
  );
}
