import { useEffect, useState } from "react";

import { isStorageLow } from "../photos/quota";
import type { Notice } from "./notice";

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
 */
export function PhotoAnchorScreen({
  pointLabel,
  notice,
  busy,
  onConfirm,
  onCancel,
}: PhotoAnchorScreenProps) {
  const [file, setFile] = useState<File | null>(null);
  const [lowStorage, setLowStorage] = useState(false);

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
        <label className="btn btn-block" htmlFor="photo-anchor-file">
          {file === null ? "Tirar foto" : `Foto selecionada: ${file.name || "sem nome"}`}
        </label>
        <input
          id="photo-anchor-file"
          type="file"
          accept="image/*"
          capture="environment"
          style={{ display: "none" }}
          disabled={busy}
          onChange={(event) => {
            const selected = event.target.files?.[0];
            event.target.value = "";
            if (selected !== undefined) {
              setFile(selected);
            }
          }}
        />
        <button
          type="button"
          className="btn btn-primary btn-block"
          disabled={file === null || busy}
          onClick={() => {
            if (file !== null) {
              onConfirm(file);
            }
          }}
        >
          {file === null ? "Confirmar (tire uma foto antes)" : "Confirmar foto"}
        </button>
        <button type="button" className="btn btn-block" onClick={onCancel} disabled={busy}>
          Cancelar
        </button>
      </div>
    </div>
  );
}
