import { describe, expect, it } from "vitest";

import {
  AUDIO_MIME_CANDIDATES,
  browserVoiceDeps,
  selectAudioMime,
  startRecording,
  VoiceRecordingError,
  type MediaRecorderLike,
  type MicrophoneStreamLike,
  type VoiceRecorderDeps,
} from "./recorder";

/** Duplo do `MediaRecorder`: guarda os handlers e deixa o teste disparar os eventos na
 * ordem que o navegador dispara (dado → parada). Nenhum DOM envolvido. */
class FakeRecorder implements MediaRecorderLike {
  started = false;
  stopCalls = 0;
  private data: ((chunk: Blob) => void) | null = null;
  private stopped: (() => void) | null = null;
  private failed: ((message: string) => void) | null = null;

  constructor(readonly mimeType: string) {}

  start(): void {
    this.started = true;
  }

  stop(): void {
    this.stopCalls += 1;
  }

  onData(handler: (chunk: Blob) => void): void {
    this.data = handler;
  }

  onStop(handler: () => void): void {
    this.stopped = handler;
  }

  onError(handler: (message: string) => void): void {
    this.failed = handler;
  }

  emitData(chunk: Blob): void {
    this.data?.(chunk);
  }

  emitStop(): void {
    this.stopped?.();
  }

  emitError(message: string): void {
    this.failed?.(message);
  }
}

class FakeStream implements MicrophoneStreamLike {
  stopped = 0;

  getTracks(): { stop(): void }[] {
    return [{ stop: () => (this.stopped += 1) }];
  }
}

interface Harness {
  deps: VoiceRecorderDeps;
  stream: FakeStream;
  recorders: FakeRecorder[];
  advance: (ms: number) => void;
}

function harness(options: { supported?: string[]; denied?: boolean } = {}): Harness {
  const supported = options.supported ?? ["audio/webm;codecs=opus"];
  const stream = new FakeStream();
  const recorders: FakeRecorder[] = [];
  let clock = 1_000;
  return {
    stream,
    recorders,
    advance: (ms) => {
      clock += ms;
    },
    deps: {
      isTypeSupported: (mime) => supported.includes(mime),
      openMicrophone: async () => {
        if (options.denied === true) {
          throw new Error("NotAllowedError");
        }
        return stream;
      },
      createRecorder: (_stream, mimeType) => {
        const recorder = new FakeRecorder(mimeType);
        recorders.push(recorder);
        return recorder;
      },
      now: () => clock,
    },
  };
}

describe("selectAudioMime", () => {
  it("prefere WebM/Opus quando o aparelho suporta (Android/Chrome)", () => {
    const choice = selectAudioMime((mime) => mime === "audio/webm;codecs=opus");

    expect(choice.recorder_mime_type).toBe("audio/webm;codecs=opus");
    expect(choice.media_mime_type).toBe("audio/webm");
  });

  it("cai para MP4/AAC quando WebM não é suportado (iOS/Safari)", () => {
    const choice = selectAudioMime((mime) => mime.startsWith("audio/mp4"));

    expect(choice.recorder_mime_type).toBe("audio/mp4;codecs=mp4a.40.2");
    expect(choice.media_mime_type).toBe("audio/mp4");
  });

  it("aceita o contêiner sem parâmetro de codec quando é só ele que o aparelho declara", () => {
    expect(selectAudioMime((mime) => mime === "audio/webm").media_mime_type).toBe("audio/webm");
    expect(selectAudioMime((mime) => mime === "audio/mp4").media_mime_type).toBe("audio/mp4");
  });

  it("falha com AUDIO_FORMAT_UNSUPPORTED quando nenhum formato serve", () => {
    try {
      selectAudioMime(() => false);
      expect.unreachable("deveria ter lançado");
    } catch (error) {
      expect(error).toBeInstanceOf(VoiceRecordingError);
      expect((error as VoiceRecordingError).code).toBe("AUDIO_FORMAT_UNSUPPORTED");
    }
  });

  it("só oferece contêineres aceitos pelo contrato de mídia do levantamento", () => {
    for (const candidate of AUDIO_MIME_CANDIDATES) {
      expect(["audio/webm", "audio/mp4"]).toContain(candidate.media_mime_type);
      // O parâmetro `;codecs=` nunca chega ao `MediaRecord`: o presign fecha o tipo.
      expect(candidate.media_mime_type).not.toContain(";");
    }
  });
});

describe("startRecording", () => {
  it("grava e devolve o blob com o contêiner real do aparelho e a duração medida", async () => {
    const context = harness();

    const recording = await startRecording(context.deps);
    expect(recording.mime_type).toBe("audio/webm");
    expect(context.recorders[0]?.mimeType).toBe("audio/webm;codecs=opus");

    context.advance(12_000);
    expect(recording.elapsedMs()).toBe(12_000);

    const pending = recording.stop();
    context.recorders[0]?.emitData(new Blob([new Uint8Array([1, 2, 3])]));
    context.recorders[0]?.emitStop();
    const audio = await pending;

    expect(audio.mime_type).toBe("audio/webm");
    expect(audio.blob.type).toBe("audio/webm");
    expect(audio.blob.size).toBe(3);
    expect(audio.duration_ms).toBe(12_000);
    // Microfone solto depois de parar: a luz do aparelho não fica acesa por engano.
    expect(context.stream.stopped).toBe(1);
  });

  it("grava em MP4 quando é o que o aparelho suporta, sem transcodificar", async () => {
    const context = harness({ supported: ["audio/mp4;codecs=mp4a.40.2"] });

    const recording = await startRecording(context.deps);
    const pending = recording.stop();
    context.recorders[0]?.emitData(new Blob([new Uint8Array([9, 9])]));
    context.recorders[0]?.emitStop();
    const audio = await pending;

    expect(audio.mime_type).toBe("audio/mp4");
    expect(audio.blob.size).toBe(2);
  });

  it("cancelar descarta os pedaços, solta o microfone e não devolve nenhum blob", async () => {
    const context = harness();
    const recording = await startRecording(context.deps);
    const recorder = context.recorders[0];

    recorder?.emitData(new Blob([new Uint8Array([1, 2, 3, 4])]));
    recording.cancel();
    // Pedaço que ainda estava a caminho quando o técnico cancelou: descartado também.
    recorder?.emitData(new Blob([new Uint8Array([5, 6])]));
    recorder?.emitStop();

    expect(context.stream.stopped).toBeGreaterThanOrEqual(1);
    // Não há caminho que devolva áudio depois de cancelar: `stop` recusa.
    await expect(recording.stop()).rejects.toBeInstanceOf(VoiceRecordingError);
  });

  it("falha com AUDIO_PERMISSION_DENIED quando o microfone não é liberado", async () => {
    const context = harness({ denied: true });

    await expect(startRecording(context.deps)).rejects.toMatchObject({
      code: "AUDIO_PERMISSION_DENIED",
    });
  });

  it("falha com AUDIO_FORMAT_UNSUPPORTED antes de pedir o microfone", async () => {
    const context = harness({ supported: [] });

    await expect(startRecording(context.deps)).rejects.toMatchObject({
      code: "AUDIO_FORMAT_UNSUPPORTED",
    });
    expect(context.recorders).toHaveLength(0);
  });

  it("falha com AUDIO_EMPTY quando nada foi capturado", async () => {
    const context = harness();
    const recording = await startRecording(context.deps);

    const pending = recording.stop();
    context.recorders[0]?.emitStop();

    await expect(pending).rejects.toMatchObject({ code: "AUDIO_EMPTY" });
  });

  it("falha com AUDIO_RECORDING_FAILED quando o aparelho interrompe a gravação", async () => {
    const context = harness();
    const recording = await startRecording(context.deps);

    const pending = recording.stop();
    context.recorders[0]?.emitError("A gravação foi interrompida pelo aparelho.");

    await expect(pending).rejects.toMatchObject({ code: "AUDIO_RECORDING_FAILED" });
    expect(context.stream.stopped).toBe(1);
  });

  it("congela o cronômetro depois de parar", async () => {
    const context = harness();
    const recording = await startRecording(context.deps);

    context.advance(5_000);
    const pending = recording.stop();
    context.recorders[0]?.emitData(new Blob([new Uint8Array([1])]));
    context.recorders[0]?.emitStop();
    await pending;
    context.advance(30_000);

    expect(recording.elapsedMs()).toBe(5_000);
  });
});

describe("browserVoiceDeps", () => {
  it("declara nenhum formato suportado onde não existe MediaRecorder (node do vitest)", () => {
    const deps = browserVoiceDeps();

    expect(deps.isTypeSupported("audio/webm;codecs=opus")).toBe(false);
  });
});
