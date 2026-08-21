import { describe, expect, it } from "vitest";

import { buildMediaRecord } from "../photos/media";
import { formatElapsed } from "./format";
import { captureAudio } from "./media";

describe("captureAudio", () => {
  it("calcula o SHA-256 dos bytes gravados e preserva o contêiner real", async () => {
    const blob = new Blob([new TextEncoder().encode("abc")], { type: "audio/webm" });

    const captured = await captureAudio({ blob, mime_type: "audio/webm", duration_ms: 3_000 });

    expect(captured.sha256).toBe(
      "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad",
    );
    expect(captured.byte_size).toBe(3);
    expect(captured.mime_type).toBe("audio/webm");
    expect(captured.blob).toBe(blob);
  });

  it("mantém audio/mp4 quando foi o aparelho que gravou em MP4", async () => {
    const blob = new Blob([new Uint8Array([1, 2])], { type: "audio/mp4" });

    const captured = await captureAudio({ blob, mime_type: "audio/mp4", duration_ms: 1_000 });

    expect(captured.mime_type).toBe("audio/mp4");
  });

  it("alimenta o mesmo buildMediaRecord das fotos — áudio não tem tabela própria", async () => {
    const blob = new Blob([new Uint8Array([7])], { type: "audio/webm" });
    const captured = await captureAudio({ blob, mime_type: "audio/webm", duration_ms: 500 });

    const record = buildMediaRecord({
      id: "media-audio",
      sha256: captured.sha256,
      mime_type: captured.mime_type,
      byte_size: captured.byte_size,
      blob: captured.blob,
      created_at: "2026-08-21T12:00:00.000Z",
    });

    expect(record).toEqual({
      id: "media-audio",
      sha256: captured.sha256,
      mime_type: "audio/webm",
      byte_size: 1,
      blob,
      created_at: "2026-08-21T12:00:00.000Z",
    });
  });
});

describe("formatElapsed", () => {
  it("escreve o cronômetro da prancha 7a em minutos:segundos", () => {
    expect(formatElapsed(0)).toBe("0:00");
    expect(formatElapsed(12_400)).toBe("0:12");
    expect(formatElapsed(60_000)).toBe("1:00");
    expect(formatElapsed(125_900)).toBe("2:05");
  });

  it("nunca escreve tempo negativo", () => {
    expect(formatElapsed(-500)).toBe("0:00");
  });
});
