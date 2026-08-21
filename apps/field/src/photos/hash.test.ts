import { describe, expect, it } from "vitest";

import { sha256Hex } from "./hash";

describe("sha256Hex", () => {
  it("calcula o SHA-256 de bytes vazios (valor conhecido)", async () => {
    const hash = await sha256Hex(new Uint8Array(0));

    expect(hash).toBe("e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855");
  });

  it("calcula o SHA-256 de 'abc' em UTF-8 (valor conhecido, vetor de teste do NIST)", async () => {
    const bytes = new TextEncoder().encode("abc");

    const hash = await sha256Hex(bytes);

    expect(hash).toBe("ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad");
  });

  it("aceita ArrayBuffer, não só Uint8Array", async () => {
    const bytes = new TextEncoder().encode("abc");

    const hash = await sha256Hex(bytes.buffer);

    expect(hash).toBe("ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad");
  });
});
