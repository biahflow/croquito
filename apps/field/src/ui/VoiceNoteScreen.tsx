import { useCallback, useEffect, useRef, useState } from "react";

import { isStorageLow } from "../photos/quota";
import { formatElapsed } from "../voice/format";
import {
  browserVoiceDeps,
  startRecording,
  VoiceRecordingError,
  type RecordedAudio,
  type VoiceRecording,
} from "../voice/recorder";
import type { Notice } from "./notice";

/** Início real da gravação. Constante de módulo (não um `default` inline) para não trocar
 * de identidade a cada render e reiniciar o efeito que grava. */
const startBrowserRecording = (): Promise<VoiceRecording> => startRecording(browserVoiceDeps());

export interface VoiceNoteScreenProps {
  /** Onde a nota fica ancorada, por extenso — a primeira linha do card da prancha 7a. */
  anchorLabel: string;
  notice: Notice | null;
  busy: boolean;
  /** Recebe o áudio gravado; quem persiste é `FieldApp` (blob nunca entra em estado de
   * React, `apps/field/AGENTS.md`). */
  onConfirm: (recorded: RecordedAudio) => void;
  onCancel: () => void;
  /** Injetável para teste e para ambiente sem `MediaRecorder`. */
  start?: () => Promise<VoiceRecording>;
}

type Phase = "starting" | "recording" | "saving" | "error";

function messageOf(error: unknown): string {
  return error instanceof VoiceRecordingError
    ? error.message
    : "A gravação não pôde ser concluída neste aparelho.";
}

/**
 * Prancha 7a da DAP rev.2 — nota de voz gravada offline, ancorada, com destino escrito.
 *
 * A tela abre JÁ gravando (a prancha não tem botão de iniciar): o único passo entre abrir
 * e gravar é a permissão do sistema, e esse instante é dito por escrito ("Pedindo acesso
 * ao microfone…") em vez de ficar mudo. Cancelar descarta tudo — nenhum `saveMedia`
 * acontece, porque nenhum blob chega a sair de `voice/recorder.ts`.
 *
 * Estado sempre escrito, nunca só colorido: cronômetro, âncora, destino da transcrição e
 * motivo de falha são texto.
 */
export function VoiceNoteScreen({
  anchorLabel,
  notice,
  busy,
  onConfirm,
  onCancel,
  start = startBrowserRecording,
}: VoiceNoteScreenProps) {
  const [phase, setPhase] = useState<Phase>("starting");
  const [errorText, setErrorText] = useState<string | null>(null);
  const [elapsedMs, setElapsedMs] = useState(0);
  const [attempt, setAttempt] = useState(0);
  const [lowStorage, setLowStorage] = useState(false);
  /** A gravação viva — fora do estado de React de propósito: ela carrega o blob. */
  const recordingRef = useRef<VoiceRecording | null>(null);

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

  useEffect(() => {
    let abandoned = false;
    setPhase("starting");
    setErrorText(null);
    setElapsedMs(0);
    void (async () => {
      try {
        const recording = await start();
        if (abandoned) {
          // Tela saiu do ar enquanto o sistema decidia a permissão: descarta na hora.
          recording.cancel();
          return;
        }
        recordingRef.current = recording;
        setPhase("recording");
      } catch (error) {
        if (abandoned) {
          return;
        }
        setErrorText(messageOf(error));
        setPhase("error");
      }
    })();
    return () => {
      abandoned = true;
      // Sair da tela é cancelar: gravação sem tela é gravação sem dono.
      recordingRef.current?.cancel();
      recordingRef.current = null;
    };
  }, [start, attempt]);

  useEffect(() => {
    if (phase !== "recording") {
      return;
    }
    const intervalId = window.setInterval(() => {
      setElapsedMs(recordingRef.current?.elapsedMs() ?? 0);
    }, 250);
    return () => window.clearInterval(intervalId);
  }, [phase]);

  const handleStop = useCallback(() => {
    const recording = recordingRef.current;
    if (recording === null) {
      return;
    }
    setPhase("saving");
    void (async () => {
      try {
        const audio = await recording.stop();
        recordingRef.current = null;
        onConfirm(audio);
      } catch (error) {
        recordingRef.current = null;
        setErrorText(messageOf(error));
        setPhase("error");
      }
    })();
  }, [onConfirm]);

  const handleCancel = useCallback(() => {
    recordingRef.current?.cancel();
    recordingRef.current = null;
    onCancel();
  }, [onCancel]);

  const cardTitle =
    phase === "recording"
      ? `Gravando… ${formatElapsed(elapsedMs)}`
      : phase === "starting"
        ? "Pedindo acesso ao microfone…"
        : phase === "saving"
          ? "Guardando a nota neste aparelho…"
          : "Gravação interrompida";

  const cardHint =
    phase === "recording"
      ? "Toque em Parar quando terminar. O áudio fica neste aparelho e sobe junto com as fotos."
      : phase === "starting"
        ? "Autorize o microfone para começar a gravar. Nada é enviado agora."
        : phase === "saving"
          ? "O áudio está sendo guardado antes de qualquer envio."
          : "Nada foi guardado.";

  return (
    <div className="screen">
      <div className="content">
        <h1 className="screen-title">Observação por voz</h1>
        {notice !== null && (
          <div className={`banner banner-${notice.tone}`} role="status">
            <span>{notice.text}</span>
          </div>
        )}
        {errorText !== null && (
          <div className="banner banner-error" role="status">
            <span>{errorText}</span>
          </div>
        )}
        {lowStorage && (
          <div className="banner banner-warn" role="status">
            <span>
              Pouco espaço livre neste aparelho (menos de 50 MB) — a nota de voz pode não ser
              gravada.
            </span>
          </div>
        )}
        <div className="card">
          <span className="card-meta">Ancorada em · {anchorLabel}</span>
          <span className="card-title">{cardTitle}</span>
          <span className="card-meta">{cardHint}</span>
        </div>
        {phase === "error" ? (
          <button
            type="button"
            className="btn btn-primary btn-block"
            onClick={() => setAttempt((value) => value + 1)}
            disabled={busy}
          >
            Tentar gravar de novo
          </button>
        ) : (
          <button
            type="button"
            className="btn btn-dark btn-block"
            onClick={handleStop}
            disabled={phase !== "recording" || busy}
          >
            {phase === "recording" ? "■ Parar gravação" : "■ Parar gravação (aguarde)"}
          </button>
        )}
        <button
          type="button"
          className="btn btn-block"
          onClick={handleCancel}
          disabled={phase === "saving" || busy}
        >
          Cancelar (nada é guardado)
        </button>
        <div className="banner banner-info" role="status">
          <span>
            A transcrição para texto acontece no servidor, depois do envio, e chega como
            rascunho para conferência — o áudio original nunca é substituído.
          </span>
        </div>
      </div>
    </div>
  );
}
