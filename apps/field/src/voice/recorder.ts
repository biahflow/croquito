/**
 * Gravação de nota de voz no aparelho (F-032, T12, prancha 7a da DAP rev.2).
 *
 * Espelho de `src/photos/`: aqui só nascem bytes + mime; quem grava no repositório é o
 * chamador (`buildMediaRecord` → `SurveyRepository.saveMedia`), e quem ancora a nota é o
 * comando de domínio. Nada neste módulo fala com a rede (`apps/field/AGENTS.md`:
 * transporte é exclusividade de `src/sync/`), então gravar funciona 100% offline.
 *
 * Duas regras que os testes protegem:
 *
 * 1. **O formato é o do aparelho, nunca uma conversão.** `MediaRecorder.isTypeSupported`
 *    decide entre WebM/Opus (Android/Chrome) e MP4/AAC (iOS/Safari); o áudio é gravado e
 *    guardado como saiu do codificador do sistema. Transcodificar em campo custaria
 *    bateria e degradaria o que a transcrição (T13) vai ouvir.
 * 2. **Cancelar não guarda nada.** `cancel()` descarta os pedaços já recebidos, solta o
 *    microfone e nunca resolve um blob — nenhum `saveMedia` acontece, porque nenhum blob
 *    chega a quem grava.
 */

/** Códigos estáveis (SCREAMING_SNAKE, mesma disciplina de `croquito_core.errors` e dos
 * comandos de domínio): quem trata a falha compara código, nunca texto. */
export type VoiceErrorCode =
  | "AUDIO_FORMAT_UNSUPPORTED"
  | "AUDIO_PERMISSION_DENIED"
  | "AUDIO_RECORDING_FAILED"
  | "AUDIO_EMPTY";

/** Falha estruturada da gravação — mensagem em português, pronta para o banner da tela. */
export class VoiceRecordingError extends Error {
  readonly code: VoiceErrorCode;

  constructor(code: VoiceErrorCode, message: string) {
    super(message);
    this.name = "VoiceRecordingError";
    this.code = code;
  }
}

/** Contêiner aceito pelo contrato de mídia do levantamento (`PresignSurveyMediaRequest`
 * fecha `mime_type` em `audio/webm`/`audio/mp4`). */
export type AudioContainerMime = "audio/webm" | "audio/mp4";

export interface AudioMimeChoice {
  /** O que é pedido ao `MediaRecorder` — pode carregar o parâmetro `;codecs=`. */
  recorder_mime_type: string;
  /**
   * O que é gravado no `MediaRecord` e assinado no presign: só o contêiner. O parâmetro
   * `;codecs=` descreve o mesmo arquivo e é recusado pelo contrato da API (`Literal`), por
   * isso não viaja — o tipo continua sendo o REAL do arquivo (webm ou mp4), nunca um
   * palpite fixo.
   */
  media_mime_type: AudioContainerMime;
}

/**
 * Ordem de preferência: Opus em WebM primeiro (menor arquivo por minuto, é o que
 * Android/Chrome grava), AAC em MP4 depois (único caminho do iOS/Safari). As variantes sem
 * `;codecs=` existem porque alguns navegadores só respondem `true` para o tipo simples.
 */
export const AUDIO_MIME_CANDIDATES: readonly AudioMimeChoice[] = [
  { recorder_mime_type: "audio/webm;codecs=opus", media_mime_type: "audio/webm" },
  { recorder_mime_type: "audio/webm", media_mime_type: "audio/webm" },
  { recorder_mime_type: "audio/mp4;codecs=mp4a.40.2", media_mime_type: "audio/mp4" },
  { recorder_mime_type: "audio/mp4", media_mime_type: "audio/mp4" },
];

/**
 * Primeiro formato que o aparelho declara suportar. Sem nenhum, é erro escrito
 * (`AUDIO_FORMAT_UNSUPPORTED`) — nunca uma tentativa às cegas que produziria um arquivo
 * que o servidor recusaria depois, longe do técnico.
 */
export function selectAudioMime(isTypeSupported: (mime: string) => boolean): AudioMimeChoice {
  for (const candidate of AUDIO_MIME_CANDIDATES) {
    if (isTypeSupported(candidate.recorder_mime_type)) {
      return candidate;
    }
  }
  throw new VoiceRecordingError(
    "AUDIO_FORMAT_UNSUPPORTED",
    "Este aparelho não grava áudio em nenhum formato aceito pelo levantamento (WebM/Opus ou MP4/AAC).",
  );
}

/** Superfície mínima do `MediaRecorder` que este módulo usa — o adaptador do navegador
 * fica em `browserVoiceDeps`, e o teste injeta um duplo sem DOM. */
export interface MediaRecorderLike {
  start(): void;
  stop(): void;
  onData(handler: (chunk: Blob) => void): void;
  onStop(handler: () => void): void;
  onError(handler: (message: string) => void): void;
}

/** Superfície mínima do `MediaStream`: só o suficiente para soltar o microfone no fim. */
export interface MicrophoneStreamLike {
  getTracks(): { stop(): void }[];
}

export interface VoiceRecorderDeps {
  isTypeSupported: (mime: string) => boolean;
  /** Abre o microfone (`getUserMedia`) — rejeitar aqui é permissão negada, não erro. */
  openMicrophone: () => Promise<MicrophoneStreamLike>;
  createRecorder: (stream: MicrophoneStreamLike, mimeType: string) => MediaRecorderLike;
  now: () => number;
}

/** O que sai da gravação: bytes, o contêiner real e a duração medida. Nunca é gravado em
 * estado de React — vai direto de `stop()` para quem persiste. */
export interface RecordedAudio {
  blob: Blob;
  mime_type: AudioContainerMime;
  duration_ms: number;
}

export interface VoiceRecording {
  /** Contêiner escolhido para ESTA gravação (`audio/webm` ou `audio/mp4`). */
  readonly mime_type: AudioContainerMime;
  /** Milissegundos desde o início — a fonte do "Gravando… 0:12" da prancha 7a. */
  elapsedMs(): number;
  /** Encerra e devolve o áudio. Rejeita com `VoiceRecordingError` se nada foi gravado. */
  stop(): Promise<RecordedAudio>;
  /** Descarta tudo: nenhum blob é devolvido, nada é persistido, o microfone é solto. */
  cancel(): void;
}

type RecordingPhase = "recording" | "stopping" | "finished" | "cancelled";

/**
 * Começa a gravar. A escolha do formato acontece ANTES de pedir o microfone: um aparelho
 * que não grava nenhum formato aceito precisa dizer isso sem antes acender a luz do
 * microfone.
 */
export async function startRecording(deps: VoiceRecorderDeps): Promise<VoiceRecording> {
  const choice = selectAudioMime(deps.isTypeSupported);

  let stream: MicrophoneStreamLike;
  try {
    stream = await deps.openMicrophone();
  } catch {
    throw new VoiceRecordingError(
      "AUDIO_PERMISSION_DENIED",
      "O microfone não foi liberado para o app. Autorize o acesso ao microfone e tente de novo.",
    );
  }

  let recorder: MediaRecorderLike;
  try {
    recorder = deps.createRecorder(stream, choice.recorder_mime_type);
  } catch {
    releaseStream(stream);
    throw new VoiceRecordingError(
      "AUDIO_RECORDING_FAILED",
      "A gravação não pôde ser iniciada neste aparelho.",
    );
  }

  const chunks: Blob[] = [];
  let phase: RecordingPhase = "recording";
  const startedAt = deps.now();
  let stoppedAt: number | null = null;
  let settle: ((outcome: { ok: true; audio: RecordedAudio } | { ok: false; error: VoiceRecordingError }) => void) | null =
    null;

  function finish(outcome: { ok: true; audio: RecordedAudio } | { ok: false; error: VoiceRecordingError }): void {
    const pending = settle;
    settle = null;
    pending?.(outcome);
  }

  recorder.onData((chunk) => {
    // Depois de cancelar, o pedaço que ainda estava a caminho é descartado: cancelar não
    // guarda NADA (prancha 7a).
    if (phase === "cancelled" || chunk.size === 0) {
      return;
    }
    chunks.push(chunk);
  });

  recorder.onStop(() => {
    if (phase === "cancelled") {
      releaseStream(stream);
      return;
    }
    stoppedAt = deps.now();
    phase = "finished";
    releaseStream(stream);
    const blob = new Blob(chunks, { type: choice.media_mime_type });
    if (blob.size === 0) {
      finish({
        ok: false,
        error: new VoiceRecordingError(
          "AUDIO_EMPTY",
          "Nada foi gravado — o microfone não capturou áudio. Tente de novo.",
        ),
      });
      return;
    }
    finish({
      ok: true,
      audio: {
        blob,
        mime_type: choice.media_mime_type,
        duration_ms: stoppedAt - startedAt,
      },
    });
  });

  recorder.onError((message) => {
    if (phase === "cancelled" || phase === "finished") {
      return;
    }
    phase = "finished";
    releaseStream(stream);
    finish({ ok: false, error: new VoiceRecordingError("AUDIO_RECORDING_FAILED", message) });
  });

  try {
    recorder.start();
  } catch {
    releaseStream(stream);
    throw new VoiceRecordingError(
      "AUDIO_RECORDING_FAILED",
      "A gravação não pôde ser iniciada neste aparelho.",
    );
  }

  return {
    mime_type: choice.media_mime_type,
    elapsedMs: () => (stoppedAt ?? deps.now()) - startedAt,
    stop: () =>
      new Promise<RecordedAudio>((resolve, reject) => {
        if (phase !== "recording") {
          reject(
            new VoiceRecordingError(
              "AUDIO_RECORDING_FAILED",
              "Esta gravação já foi encerrada.",
            ),
          );
          return;
        }
        phase = "stopping";
        settle = (outcome) => {
          if (outcome.ok) {
            resolve(outcome.audio);
          } else {
            reject(outcome.error);
          }
        };
        try {
          recorder.stop();
        } catch {
          phase = "finished";
          releaseStream(stream);
          finish({
            ok: false,
            error: new VoiceRecordingError(
              "AUDIO_RECORDING_FAILED",
              "A gravação foi interrompida pelo aparelho antes de terminar.",
            ),
          });
        }
      }),
    cancel: () => {
      if (phase === "cancelled" || phase === "finished") {
        return;
      }
      phase = "cancelled";
      chunks.length = 0;
      stoppedAt = deps.now();
      try {
        recorder.stop();
      } catch {
        // Recorder já inativo: o microfone ainda precisa ser solto.
      }
      releaseStream(stream);
      finish({
        ok: false,
        error: new VoiceRecordingError("AUDIO_RECORDING_FAILED", "A gravação foi cancelada."),
      });
    },
  };
}

function releaseStream(stream: MicrophoneStreamLike): void {
  for (const track of stream.getTracks()) {
    try {
      track.stop();
    } catch {
      // Soltar o microfone é melhor-esforço: uma trilha já encerrada não é falha.
    }
  }
}

/**
 * Dependências reais do navegador. Fica isolado aqui (e não espalhado pela tela) para que
 * o módulo continue testável em node puro: nenhum teste toca `MediaRecorder` de verdade.
 */
export function browserVoiceDeps(): VoiceRecorderDeps {
  return {
    isTypeSupported: (mime) =>
      typeof MediaRecorder !== "undefined" && MediaRecorder.isTypeSupported(mime),
    openMicrophone: async () => {
      if (typeof navigator === "undefined" || navigator.mediaDevices === undefined) {
        throw new VoiceRecordingError(
          "AUDIO_PERMISSION_DENIED",
          "Este aparelho não oferece acesso ao microfone para o app.",
        );
      }
      return navigator.mediaDevices.getUserMedia({ audio: true });
    },
    createRecorder: (stream, mimeType) => {
      const recorder = new MediaRecorder(stream as MediaStream, { mimeType });
      return {
        start: () => recorder.start(),
        stop: () => recorder.stop(),
        onData: (handler) => {
          recorder.ondataavailable = (event) => handler(event.data);
        },
        onStop: (handler) => {
          recorder.onstop = () => handler();
        },
        onError: (handler) => {
          recorder.onerror = () =>
            handler("A gravação foi interrompida pelo aparelho antes de terminar.");
        },
      };
    },
    now: () => Date.now(),
  };
}
