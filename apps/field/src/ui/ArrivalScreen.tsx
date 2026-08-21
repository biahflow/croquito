import { useEffect, useReducer, useRef, useState } from "react";

import type { GpsFix } from "../domain/types";
import { evaluateCapturedPhoto } from "../photos/evaluateCapturedPhoto";
import type { Notice } from "./notice";
import { PhotoQualityCard } from "./PhotoQualityCard";
import {
  INITIAL_PHOTO_QUALITY_GATE_STATE,
  photoQualityGateReducer,
} from "./photoQualityGate";

/** Lista fechada do segmented control (prancha 2) — o texto exato vira o `instrument`
 * gravado por `recordArrival` (mesma convenção de texto livre de `Measurement.instrument`;
 * ver comentário de `ArrivalContext` em `domain/types.ts`). */
const INSTRUMENTS = ["Trena laser", "Trena comum", "Outro"] as const;

type GpsProbeState = "pending" | "unavailable" | { fix: GpsFix };

const GPS_TIMEOUT_MS = 6_000;

/**
 * Pede a localização do aparelho uma vez, com timeout curto. GPS é referência geográfica,
 * nunca medição, e NUNCA bloqueia a chegada (Task Contract T4, Known Risks): erro,
 * negação ou timeout viram `"unavailable"`, não uma exceção nem um estado de bloqueio.
 */
function useGpsProbe(): GpsProbeState {
  const [state, setState] = useState<GpsProbeState>("pending");

  useEffect(() => {
    if (typeof navigator === "undefined" || navigator.geolocation === undefined) {
      setState("unavailable");
      return;
    }
    let cancelled = false;
    navigator.geolocation.getCurrentPosition(
      (position) => {
        if (cancelled) {
          return;
        }
        setState({
          fix: {
            lat: position.coords.latitude,
            lng: position.coords.longitude,
            accuracy_m: Math.round(position.coords.accuracy),
          },
        });
      },
      () => {
        if (!cancelled) {
          setState("unavailable");
        }
      },
      { timeout: GPS_TIMEOUT_MS, maximumAge: 0 },
    );
    return () => {
      cancelled = true;
    };
  }, []);

  return state;
}

export interface ArrivalScreenProps {
  notice: Notice | null;
  onConfirm: (args: { instrument: string; referenceNote: string; gps: GpsFix | "unavailable" }) => void;
  busy: boolean;
  /** `true` quando a foto do acesso já foi capturada e salva nesta chegada (T6) —
   * `FieldApp` deriva de um id de mídia local ainda não incluído no comando
   * `recordArrival` (só vai junto quando "Começar a coleta" é tocado). */
  accessPhotoCaptured: boolean;
  onCaptureAccessPhoto: (file: File) => void;
}

/**
 * Prancha 2 — chegada ao local: contexto que qualifica toda medida do dia, registrado uma
 * vez por levantamento. Uma tarefa por etapa (instrumento → referência → GPS → foto do
 * acesso), como no pacote aprovado.
 *
 * Foto do acesso (T6): a captura acontece AQUI (antes de "Começar a coleta"), com
 * `<input type="file" capture="environment">` nativo — sem tela de câmera própria. O
 * blob é salvo via `saveMedia` assim que o arquivo é escolhido (`onCaptureAccessPhoto`);
 * só a referência (`access_media_ref`) viaja com `recordArrival` ao confirmar a chegada
 * — mesma ordem "blob primeiro, âncora/comando depois" do fluxo de foto ancorada
 * (`PhotoAnchorScreen`).
 *
 * Qualidade de foto (Task Contract T15, prancha 7b): a captura NÃO chama mais
 * `onCaptureAccessPhoto` direto no `onChange` — primeiro avalia (segundo plano, resolução
 * reduzida). Foto "ok" (ou avaliação indisponível) persiste sozinha, sem tela nova (mesmo
 * comportamento de antes: nenhum toque a mais). Só um veredito não-"ok" interrompe com o
 * card de aviso (Refazer descarta sem persistir e reabre a câmera; Manter persiste).
 */
export function ArrivalScreen({
  notice,
  onConfirm,
  busy,
  accessPhotoCaptured,
  onCaptureAccessPhoto,
}: ArrivalScreenProps) {
  const [instrument, setInstrument] = useState<(typeof INSTRUMENTS)[number]>(INSTRUMENTS[0]);
  const [referenceNote, setReferenceNote] = useState("");
  const gpsProbe = useGpsProbe();
  const filled = referenceNote.trim().length > 0;
  const [photoGate, dispatchPhotoGate] = useReducer(
    photoQualityGateReducer,
    INITIAL_PHOTO_QUALITY_GATE_STATE,
  );
  const accessPhotoInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (photoGate.phase === "clear") {
      onCaptureAccessPhoto(photoGate.file);
      dispatchPhotoGate({ type: "reset" });
    }
  }, [photoGate, onCaptureAccessPhoto]);

  const handleAccessFileSelected = (selected: File) => {
    dispatchPhotoGate({ type: "file-selected", file: selected });
    void evaluateCapturedPhoto(selected).then((outcome) => {
      dispatchPhotoGate({ type: "evaluated", file: selected, outcome });
    });
  };

  const handleAccessPhotoRedo = () => {
    dispatchPhotoGate({ type: "reset" });
    // "reabre a câmera" (Task Contract T15): dispara o mesmo input nativo de novo.
    accessPhotoInputRef.current?.click();
  };

  const handleAccessPhotoKeep = () => {
    if (photoGate.phase === "warn") {
      onCaptureAccessPhoto(photoGate.file);
      dispatchPhotoGate({ type: "reset" });
    }
  };

  // O botão nunca espera o GPS (regra: GPS não bloqueia) — sem leitura pronta ainda,
  // grava "unavailable", o mesmo valor de uma leitura que falhou.
  const gpsForSubmit: GpsFix | "unavailable" =
    typeof gpsProbe === "object" ? gpsProbe.fix : "unavailable";

  return (
    <div className="screen">
      <div className="content">
        <h1 className="screen-title">Antes de medir</h1>
        <p className="sub">Registrado com cada medida deste levantamento.</p>
        {notice !== null && (
          <div className={`banner banner-${notice.tone}`} role="status">
            <span>{notice.text}</span>
          </div>
        )}
        <div className="field">
          <span className="field-label" id="arrival-instrument-label">
            Instrumento principal
          </span>
          <div className="seg" role="group" aria-labelledby="arrival-instrument-label">
            {INSTRUMENTS.map((option) => (
              <button
                key={option}
                type="button"
                className={instrument === option ? "seg-item seg-item-on" : "seg-item"}
                aria-pressed={instrument === option}
                onClick={() => setInstrument(option)}
              >
                {option}
              </button>
            ))}
          </div>
        </div>
        <div className="field">
          <label className="field-label" htmlFor="arrival-reference-note">
            Ponto de referência físico (permanente)
          </label>
          <input
            id="arrival-reference-note"
            className="field-input"
            type="text"
            value={referenceNote}
            placeholder="Ex.: Canto do muro da escola, lado norte"
            onChange={(event) => setReferenceNote(event.target.value)}
          />
        </div>
        {gpsProbe === "pending" && (
          <div className="check check-todo">
            <span className="check-state" />
            <div className="check-body">
              <b className="check-title">Localizando…</b>
              <small className="check-detail">Aguardando o GPS do aparelho.</small>
            </div>
          </div>
        )}
        {typeof gpsProbe === "object" && (
          <div className="check check-ok">
            <span className="check-state" />
            <div className="check-body">
              <b className="check-title">Localização registrada</b>
              <small className="check-detail">
                GPS {gpsProbe.fix.lat.toFixed(3)}, {gpsProbe.fix.lng.toFixed(3)} (±
                {gpsProbe.fix.accuracy_m} m) · serve para achar a obra, não para medir
              </small>
            </div>
          </div>
        )}
        {gpsProbe === "unavailable" && (
          <div className="check check-warn">
            <span className="check-state" />
            <div className="check-body">
              <b className="check-title">Localização não disponível — siga sem ela</b>
              <small className="check-detail">
                O GPS não respondeu a tempo ou o acesso foi negado.
              </small>
            </div>
          </div>
        )}
        <div className={accessPhotoCaptured ? "check check-ok" : "check check-warn"}>
          <span className="check-state" />
          <div className="check-body">
            <b className="check-title">
              {accessPhotoCaptured
                ? "Foto do acesso principal — registrada"
                : "Foto do acesso principal — pendente"}
            </b>
            <small className="check-detail">Obrigatória no checklist desta ordem</small>
          </div>
        </div>
        {photoGate.phase !== "warn" && (
          <label
            className="btn btn-block"
            htmlFor="arrival-access-photo"
            style={busy ? { opacity: 0.6, pointerEvents: "none" } : undefined}
          >
            {accessPhotoCaptured ? "Tirar outra foto do acesso" : "Tirar foto do acesso"}
          </label>
        )}
        <input
          id="arrival-access-photo"
          ref={accessPhotoInputRef}
          type="file"
          accept="image/*"
          capture="environment"
          style={{ display: "none" }}
          disabled={busy}
          onChange={(event) => {
            const file = event.target.files?.[0];
            event.target.value = "";
            if (file !== undefined) {
              handleAccessFileSelected(file);
            }
          }}
        />
        {photoGate.phase === "checking" && (
          <div className="banner banner-info" role="status">
            <span>Avaliando qualidade da foto do acesso…</span>
          </div>
        )}
        {photoGate.phase === "warn" && (
          <PhotoQualityCard
            fileName={photoGate.file.name || "sem nome"}
            verdict={photoGate.verdict}
            busy={busy}
            onRedo={handleAccessPhotoRedo}
            onKeep={handleAccessPhotoKeep}
          />
        )}
        <button
          type="button"
          className="btn btn-dark btn-block"
          disabled={!filled || busy}
          onClick={() => onConfirm({ instrument, referenceNote, gps: gpsForSubmit })}
        >
          Começar a coleta
        </button>
      </div>
    </div>
  );
}
