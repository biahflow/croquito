import { afterEach, describe, expect, it, vi } from "vitest";

import { isStorageLow, LOW_STORAGE_THRESHOLD_BYTES } from "./quota";

describe("isStorageLow", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("devolve false quando o navegador não tem navigator.storage.estimate", async () => {
    vi.stubGlobal("navigator", {});

    expect(await isStorageLow()).toBe(false);
  });

  it("devolve true quando o espaço livre estimado fica abaixo do limiar", async () => {
    vi.stubGlobal("navigator", {
      storage: {
        estimate: async () => ({ quota: LOW_STORAGE_THRESHOLD_BYTES - 1, usage: 0 }),
      },
    });

    expect(await isStorageLow()).toBe(true);
  });

  it("devolve false quando o espaço livre estimado fica acima do limiar", async () => {
    vi.stubGlobal("navigator", {
      storage: {
        estimate: async () => ({ quota: LOW_STORAGE_THRESHOLD_BYTES + 1_000_000, usage: 0 }),
      },
    });

    expect(await isStorageLow()).toBe(false);
  });

  it("devolve false quando a estimativa falha", async () => {
    vi.stubGlobal("navigator", {
      storage: {
        estimate: async () => {
          throw new Error("indisponível");
        },
      },
    });

    expect(await isStorageLow()).toBe(false);
  });
});
