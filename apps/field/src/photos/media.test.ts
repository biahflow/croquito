import { describe, expect, it } from "vitest";

import { buildMediaRecord, captureFile } from "./media";

describe("captureFile", () => {
  it("lê bytes, mede tamanho/tipo e calcula o SHA-256 do conteúdo original", async () => {
    const bytes = new TextEncoder().encode("abc");
    const file = new File([bytes], "foto.jpg", { type: "image/jpeg" });

    const captured = await captureFile(file);

    expect(captured.sha256).toBe(
      "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad",
    );
    expect(captured.byte_size).toBe(3);
    expect(captured.mime_type).toBe("image/jpeg");
    expect(captured.blob).toBe(file);
  });

  it("usa application/octet-stream quando o arquivo não declara tipo", async () => {
    const file = new File([], "foto");

    const captured = await captureFile(file);

    expect(captured.mime_type).toBe("application/octet-stream");
    expect(captured.byte_size).toBe(0);
  });
});

describe("buildMediaRecord", () => {
  it("monta o MediaRecord com exatamente os campos recebidos", () => {
    const blob = new Blob(["x"]);

    const record = buildMediaRecord({
      id: "media-1",
      sha256: "abc123",
      mime_type: "image/jpeg",
      byte_size: 1,
      blob,
      created_at: "2026-08-21T12:00:00.000Z",
    });

    expect(record).toEqual({
      id: "media-1",
      sha256: "abc123",
      mime_type: "image/jpeg",
      byte_size: 1,
      blob,
      created_at: "2026-08-21T12:00:00.000Z",
    });
  });
});
