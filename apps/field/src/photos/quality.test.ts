import { describe, expect, it } from "vitest";

import {
  assessPhotoQuality,
  BLUR_VARIANCE_THRESHOLD,
  CLIPPED_HIGHLIGHTS_FRACTION_THRESHOLD,
  CLIPPED_SHADOWS_FRACTION_THRESHOLD,
} from "./quality";

/**
 * `ImageData` sintética, gerada em código (Task Contract T15, Comportamento exigido item
 * 1: "sem fixture binária") — nunca lê um arquivo real de imagem. `pixelFn` devolve
 * `[r, g, b]` (0–255) para cada posição; alpha sempre 255 (opaco).
 */
function makeImageData(
  width: number,
  height: number,
  pixelFn: (x: number, y: number) => readonly [number, number, number],
): ImageData {
  const data = new Uint8ClampedArray(width * height * 4);
  for (let y = 0; y < height; y++) {
    for (let x = 0; x < width; x++) {
      const [r, g, b] = pixelFn(x, y);
      const i = (y * width + x) * 4;
      data[i] = r;
      data[i + 1] = g;
      data[i + 2] = b;
      data[i + 3] = 255;
    }
  }
  return { data, width, height, colorSpace: "srgb" };
}

/**
 * Xadrez perfeito de amplitude `delta` em torno de `base` (valores `base − delta` e
 * `base + delta` alternados). Cada pixel interior tem os 4 vizinhos da paridade oposta,
 * então o Laplaciano vale `±4·(2·delta) = ±8·delta` em todo pixel interior — constante em
 * módulo, sinal alternado, média zero — e a variância fecha exatamente em
 * `(8·delta)² = 64·delta²`. Serve para mirar `sharpness` num valor exato sem calcular a
 * variância à mão para cada caso (conferido nos dois testes de caso limítrofe abaixo).
 */
function checkerboard(width: number, height: number, base: number, delta: number): ImageData {
  return makeImageData(width, height, (x, y) => {
    const v = (x + y) % 2 === 0 ? base - delta : base + delta;
    return [v, v, v];
  });
}

function flat(width: number, height: number, value: number): ImageData {
  return makeImageData(width, height, () => [value, value, value]);
}

/** Predominantemente uma luma extrema (estouro/esmagamento), com ruído esparso a cada 4
 * pixels para gerar bordas reais (sem ruído a variância ficaria perto de zero e o veredito
 * viraria "blurry" em vez de "over"/"under" — a imagem real de uma parede muito clara ou
 * escura tem textura, não é um retângulo perfeitamente uniforme). */
function mostlyExtreme(
  width: number,
  height: number,
  extreme: number,
  noise: number,
): ImageData {
  return makeImageData(width, height, (x, y) => {
    const isNoise = x % 4 === 0 && y % 4 === 0;
    const v = isNoise ? noise : extreme;
    return [v, v, v];
  });
}

const SIZE = 64;

describe("assessPhotoQuality", () => {
  it("classifica uma imagem nítida (xadrez de contraste médio, sem estouro) como ok", () => {
    const image = checkerboard(SIZE, SIZE, 128, 55);

    const result = assessPhotoQuality(image);

    expect(result.sharpness).toBeGreaterThan(BLUR_VARIANCE_THRESHOLD);
    expect(result.verdict).toBe("ok");
    expect(result.reasons).toEqual([]);
    expect(result.exposure.clippedHighlights).toBe(0);
    expect(result.exposure.clippedShadows).toBe(0);
  });

  it("classifica uma imagem borrada (luma constante, variância zero do Laplaciano) como blurry", () => {
    const image = flat(SIZE, SIZE, 128);

    const result = assessPhotoQuality(image);

    expect(result.sharpness).toBe(0);
    expect(result.verdict).toBe("blurry");
    expect(result.reasons).toContain("Nitidez baixa — possivelmente tremida ou fora de foco.");
  });

  it("classifica uma imagem majoritariamente estourada (excesso de luz) como over", () => {
    const image = mostlyExtreme(SIZE, SIZE, 255, 200);

    const result = assessPhotoQuality(image);

    expect(result.exposure.clippedHighlights).toBeGreaterThan(CLIPPED_HIGHLIGHTS_FRACTION_THRESHOLD);
    expect(result.verdict).toBe("over");
    expect(result.reasons).toContain("Muitos trechos estourados de luz — difícil de ler.");
  });

  it("classifica uma imagem majoritariamente escura (sombra esmagada) como under", () => {
    const image = mostlyExtreme(SIZE, SIZE, 3, 40);

    const result = assessPhotoQuality(image);

    expect(result.exposure.clippedShadows).toBeGreaterThan(CLIPPED_SHADOWS_FRACTION_THRESHOLD);
    expect(result.verdict).toBe("under");
    expect(result.reasons).toContain("Imagem muito escura — difícil de ler.");
  });

  it("caso limítrofe: variância de Laplaciano logo ACIMA do limiar de borrão não é blurry", () => {
    // xadrez com delta=5 → variância = 64·5² = 1600, acima de BLUR_VARIANCE_THRESHOLD
    // (1024) com margem suficiente para não depender de arredondamento de ponto flutuante.
    const delta = 5;
    const image = checkerboard(SIZE, SIZE, 128, delta);
    expect(64 * delta ** 2).toBeGreaterThan(BLUR_VARIANCE_THRESHOLD);

    const result = assessPhotoQuality(image);

    expect(result.verdict).not.toBe("blurry");
  });

  it("caso limítrofe: variância de Laplaciano logo ABAIXO do limiar de borrão é blurry", () => {
    // delta=3 → variância = 64·3² = 576, abaixo do limiar (1024).
    const delta = 3;
    const image = checkerboard(SIZE, SIZE, 128, delta);
    expect(64 * delta ** 2).toBeLessThan(BLUR_VARIANCE_THRESHOLD);

    const result = assessPhotoQuality(image);

    expect(result.verdict).toBe("blurry");
  });

  it("é determinístico: a mesma ImageData sempre devolve o mesmo resultado", () => {
    const image = checkerboard(SIZE, SIZE, 128, 55);

    expect(assessPhotoQuality(image)).toEqual(assessPhotoQuality(image));
  });
});
