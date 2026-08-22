import { describe, expect, it } from "vitest";

import { evaluateCapturedPhoto } from "./evaluateCapturedPhoto";

/** `ImageData` sintética (xadrez nítido de amplitude 55, mesmo raciocínio de
 * `quality.test.ts`) — o decoder injetado devolve isto em vez de decodificar bytes reais. */
function sharpCheckerboard(width: number, height: number): ImageData {
  const data = new Uint8ClampedArray(width * height * 4);
  for (let y = 0; y < height; y++) {
    for (let x = 0; x < width; x++) {
      const v = (x + y) % 2 === 0 ? 73 : 183;
      const i = (y * width + x) * 4;
      data[i] = v;
      data[i + 1] = v;
      data[i + 2] = v;
      data[i + 3] = 255;
    }
  }
  return { data, width, height, colorSpace: "srgb" };
}

describe("evaluateCapturedPhoto", () => {
  it("decodifica via o decoder injetado e devolve o veredito do módulo puro", async () => {
    const decode = async () => sharpCheckerboard(16, 16);

    const outcome = await evaluateCapturedPhoto(new Blob(["foto"]), decode);

    expect(outcome.available).toBe(true);
    if (outcome.available) {
      expect(outcome.verdict).toBe("ok");
    }
  });

  it("nunca bloqueia a foto quando a decodificação falha — devolve available: false", async () => {
    const decode = async (): Promise<ImageData> => {
      throw new Error("formato não suportado neste aparelho");
    };

    const outcome = await evaluateCapturedPhoto(new Blob(["foto"]), decode);

    expect(outcome).toEqual({ available: false });
  });

  it("devolve available: false quando o blob decodifica para uma imagem degenerada que o decoder rejeita", async () => {
    const decode = async (): Promise<ImageData> => {
      throw new Error("Canvas 2D indisponível neste navegador.");
    };

    const outcome = await evaluateCapturedPhoto(new Blob([]), decode);

    expect(outcome).toEqual({ available: false });
  });

  it("usa o decoder padrão (browser) quando nenhum é injetado — falha graciosamente sem createImageBitmap/document", async () => {
    // Ambiente de teste é node puro (`vite.config.ts`, `test.environment: "node"`): sem
    // `createImageBitmap` nem `document`, o decoder padrão sempre lança, e o wrapper
    // absorve isso — a mesma garantia teria efeito com um blob corrompido no navegador.
    const outcome = await evaluateCapturedPhoto(new Blob(["foto"]));

    expect(outcome).toEqual({ available: false });
  });
});
