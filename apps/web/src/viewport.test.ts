import type { CSSProperties } from "react";
import { describe, expect, it } from "vitest";

import {
  clampZoom,
  evidenceCropStyle,
  isQuarterTurned,
  MAX_ZOOM,
  normalizeRotation,
  panScrollOffset,
  previewTransform,
  rotationShortcutDelta,
  stageAspect,
  stageStyle,
  type PixelBox,
} from "./viewport";

/** A folha do Guaxindiba renderizada a 200 DPI. */
const IMAGE_WIDTH = 4875;
const IMAGE_HEIGHT = 6718;

function percent(value: CSSProperties[keyof CSSProperties], base: number): number {
  if (typeof value !== "string" || !value.endsWith("%")) {
    throw new Error(`esperava um percentual, veio ${String(value)}`);
  }
  return (Number(value.slice(0, -1)) / 100) * base;
}

function ratio(value: CSSProperties[keyof CSSProperties]): number {
  const [width, height] = String(value).split(" / ").map(Number);
  return width / height;
}

/**
 * Resolve o recorte como o browser faria: percentuais horizontais (`width`, `left`)
 * contra a largura do bloco contêiner e verticais (`height`, `top`) contra a altura.
 * É essa distinção que prova o denominador de cada eixo.
 */
function layoutCrop(
  bbox: PixelBox,
  rotation: number,
  cropWidthPx: number,
): {
  cropHeightPx: number;
  pivotWidthPx: number;
  pivotHeightPx: number;
  imageWidthPx: number;
  imageHeightPx: number;
  imageLeftPx: number;
  imageTopPx: number;
} {
  const style = evidenceCropStyle(bbox, IMAGE_WIDTH, IMAGE_HEIGHT, rotation);
  const pivotWidthPx = percent(style.pivot.width, cropWidthPx);
  const pivotHeightPx = pivotWidthPx / ratio(style.pivot.aspectRatio);
  return {
    cropHeightPx: cropWidthPx / ratio(style.crop.aspectRatio),
    pivotWidthPx,
    pivotHeightPx,
    imageWidthPx: percent(style.image.width, pivotWidthPx),
    imageHeightPx: percent(style.image.height, pivotHeightPx),
    imageLeftPx: percent(style.image.left, pivotWidthPx),
    imageTopPx: percent(style.image.top, pivotHeightPx),
  };
}

describe("normalizeRotation", () => {
  it("mantém os quatro quartos de volta", () => {
    expect([0, 90, 180, 270].map(normalizeRotation)).toEqual([0, 90, 180, 270]);
  });

  it("traz valores fora da volta e negativos de volta ao intervalo", () => {
    expect(normalizeRotation(-90)).toBe(270);
    expect(normalizeRotation(360)).toBe(0);
    expect(normalizeRotation(450)).toBe(90);
    expect(normalizeRotation(-450)).toBe(270);
  });

  it("aceita lixo do localStorage sem contaminar o viewer", () => {
    expect(normalizeRotation(Number("nada"))).toBe(0);
    expect(normalizeRotation(Number.POSITIVE_INFINITY)).toBe(0);
    expect(normalizeRotation(89)).toBe(90);
  });

  it("marca como girada só a meia volta ímpar", () => {
    expect([0, 90, 180, 270].map(isQuarterTurned)).toEqual([
      false,
      true,
      false,
      true,
    ]);
  });
});

describe("clampZoom", () => {
  it("mantém o zoom entre 1 e 4", () => {
    expect(clampZoom(0.2)).toBe(1);
    expect(clampZoom(2.5)).toBe(2.5);
    expect(clampZoom(9)).toBe(MAX_ZOOM);
    expect(clampZoom(Number("x"))).toBe(1);
  });
});

describe("stageAspect", () => {
  it("troca os eixos em cada quarto de volta", () => {
    expect(stageAspect(IMAGE_WIDTH, IMAGE_HEIGHT, 0)).toBe("4875 / 6718");
    expect(stageAspect(IMAGE_WIDTH, IMAGE_HEIGHT, 90)).toBe("6718 / 4875");
    expect(stageAspect(IMAGE_WIDTH, IMAGE_HEIGHT, 180)).toBe("4875 / 6718");
    expect(stageAspect(IMAGE_WIDTH, IMAGE_HEIGHT, 270)).toBe("6718 / 4875");
  });

  it("não degenera quando a dimensão da imagem ainda é desconhecida", () => {
    expect(stageAspect(0, 0, 0)).toBe("1 / 1");
    expect(stageAspect(Number.NaN, IMAGE_HEIGHT, 90)).toBe("6718 / 1");
  });
});

describe("stageStyle", () => {
  it("cresce o palco com o zoom para que a folha inteira continue alcançável", () => {
    expect(stageStyle(1, 0, IMAGE_WIDTH, IMAGE_HEIGHT)).toEqual({
      width: "100%",
      aspectRatio: "4875 / 6718",
    });
    expect(stageStyle(4, 90, IMAGE_WIDTH, IMAGE_HEIGHT)).toEqual({
      width: "400%",
      aspectRatio: "6718 / 4875",
    });
  });

  it("nunca aceita zoom fora do intervalo do controle", () => {
    expect(stageStyle(12, 0, IMAGE_WIDTH, IMAGE_HEIGHT).width).toBe("400%");
    expect(stageStyle(0, 0, IMAGE_WIDTH, IMAGE_HEIGHT).width).toBe("100%");
  });
});

describe("previewTransform", () => {
  it("gira em torno do centro sem escalar o conteúdo", () => {
    expect(previewTransform(0, IMAGE_WIDTH, IMAGE_HEIGHT)).toEqual({
      width: "100%",
      transform: "translate(-50%, -50%) rotate(0deg)",
    });
    expect(previewTransform(180, IMAGE_WIDTH, IMAGE_HEIGHT)).toEqual({
      width: "100%",
      transform: "translate(-50%, -50%) rotate(180deg)",
    });
  });

  it("compensa a largura quando o desenho está deitado", () => {
    const right = previewTransform(90, IMAGE_WIDTH, IMAGE_HEIGHT);
    const left = previewTransform(-90, IMAGE_WIDTH, IMAGE_HEIGHT);
    expect(right.width).toBe(`${(IMAGE_WIDTH / IMAGE_HEIGHT) * 100}%`);
    expect(left.width).toBe(right.width);
    expect(left.transform).toBe("translate(-50%, -50%) rotate(270deg)");
  });

  it("preenche o palco girado exatamente: a caixa girada tem o tamanho do palco", () => {
    const stageWidthPx = 800;
    const stageHeightPx =
      stageWidthPx / ratio(stageAspect(IMAGE_WIDTH, IMAGE_HEIGHT, 90));
    const boxWidthPx = percent(
      previewTransform(90, IMAGE_WIDTH, IMAGE_HEIGHT).width,
      stageWidthPx,
    );
    // A altura vem da proporção natural da imagem, que a `<img>` preserva.
    const boxHeightPx = boxWidthPx * (IMAGE_HEIGHT / IMAGE_WIDTH);
    // Girada, a largura da caixa vira altura visível e vice-versa.
    expect(boxHeightPx).toBeCloseTo(stageWidthPx, 6);
    expect(boxWidthPx).toBeCloseTo(stageHeightPx, 6);
  });
});

describe("evidenceCropStyle", () => {
  // Cota escrita na vertical: muito mais alta do que larga, o caso que denuncia
  // um denominador trocado entre os eixos.
  const tallBox: PixelBox = { left: 1200, top: 3000, right: 1300, bottom: 3800 };

  it("faz a bbox cair exatamente sobre a janela do recorte", () => {
    const cropWidthPx = 300;
    const layout = layoutCrop(tallBox, 0, cropWidthPx);
    const scale = cropWidthPx / (tallBox.right - tallBox.left);

    expect(layout.pivotWidthPx).toBeCloseTo(cropWidthPx, 6);
    expect(layout.cropHeightPx).toBeCloseTo(
      (tallBox.bottom - tallBox.top) * scale,
      6,
    );
    expect(layout.pivotHeightPx).toBeCloseTo(layout.cropHeightPx, 6);
    // A imagem inteira entra na mesma escala nos dois eixos...
    expect(layout.imageWidthPx).toBeCloseTo(IMAGE_WIDTH * scale, 6);
    expect(layout.imageHeightPx).toBeCloseTo(IMAGE_HEIGHT * scale, 6);
    // ...e o canto superior esquerdo da bbox encosta no canto da janela.
    expect(layout.imageLeftPx).toBeCloseTo(-tallBox.left * scale, 6);
    expect(layout.imageTopPx).toBeCloseTo(-tallBox.top * scale, 6);
  });

  it("prova que o denominador vertical é a altura da bbox, não a largura", () => {
    const cropWidthPx = 300;
    const style = evidenceCropStyle(tallBox, IMAGE_WIDTH, IMAGE_HEIGHT, 0);
    const layout = layoutCrop(tallBox, 0, cropWidthPx);
    const boxWidth = tallBox.right - tallBox.left;
    const boxHeight = tallBox.bottom - tallBox.top;

    // `top` é percentual do bloco contêiner na vertical, e a altura do pivô é
    // `larguraDoPivô * bh / bw`; por isso o denominador correto é `bh`.
    expect(style.image.top).toBe(`${(-tallBox.top / boxHeight) * 100}%`);
    expect(layout.imageTopPx).toBeCloseTo(-9000, 6);
    // O "conserto" intuitivo (denominador `bw`, como em percentuais de margin)
    // jogaria a tinta oito vezes mais longe numa cota escrita na vertical.
    const wrongTopPx =
      ((-tallBox.top / boxWidth) * 100 * layout.pivotHeightPx) / 100;
    expect(wrongTopPx).toBeCloseTo(-9000 * (boxHeight / boxWidth), 6);
    expect(wrongTopPx).not.toBeCloseTo(layout.imageTopPx, 6);
  });

  it("gira o recorte sem tirar a bbox da janela", () => {
    const cropWidthPx = 300;
    const layout = layoutCrop(tallBox, 90, cropWidthPx);

    // A janela ficou deitada e o pivô, ainda em pé, cabe girado dentro dela.
    expect(layout.cropHeightPx).toBeCloseTo(
      cropWidthPx /
        ((tallBox.bottom - tallBox.top) / (tallBox.right - tallBox.left)),
      6,
    );
    expect(layout.pivotHeightPx).toBeCloseTo(cropWidthPx, 6);
    expect(layout.pivotWidthPx).toBeCloseTo(layout.cropHeightPx, 6);
    const scale = layout.pivotWidthPx / (tallBox.right - tallBox.left);
    expect(layout.imageLeftPx).toBeCloseTo(-tallBox.left * scale, 6);
    expect(layout.imageTopPx).toBeCloseTo(-tallBox.top * scale, 6);
  });

  it("mantém o mesmo pivô nas quatro rotações e só troca a janela", () => {
    const styles = [0, 90, 180, 270].map((rotation) =>
      evidenceCropStyle(tallBox, IMAGE_WIDTH, IMAGE_HEIGHT, rotation),
    );
    expect(styles.map((style) => style.crop.aspectRatio)).toEqual([
      "100 / 800",
      "800 / 100",
      "100 / 800",
      "800 / 100",
    ]);
    expect(styles.map((style) => style.pivot.transform)).toEqual([
      "translate(-50%, -50%) rotate(0deg)",
      "translate(-50%, -50%) rotate(90deg)",
      "translate(-50%, -50%) rotate(180deg)",
      "translate(-50%, -50%) rotate(270deg)",
    ]);
    expect(new Set(styles.map((style) => style.image.top)).size).toBe(1);
  });

  it("não produz NaN com bbox degenerada", () => {
    const style = evidenceCropStyle(
      { left: 10, top: 10, right: 10, bottom: 10 },
      0,
      0,
      0,
    );
    const values = [
      ...Object.values(style.crop),
      ...Object.values(style.pivot),
      ...Object.values(style.image),
    ].join(" ");
    expect(values).not.toContain("NaN");
    expect(values).not.toContain("Infinity");
  });
});

describe("rotationShortcutDelta", () => {
  it("gira à direita com a tecla e à esquerda com shift", () => {
    expect(rotationShortcutDelta({ key: "r" })).toBe(90);
    expect(rotationShortcutDelta({ key: "R", shiftKey: true })).toBe(-90);
  });

  it("ignora a tecla enquanto o revisor digita ou usa um atalho do sistema", () => {
    expect(rotationShortcutDelta({ key: "r", typingInField: true })).toBeNull();
    expect(rotationShortcutDelta({ key: "r", ctrlKey: true })).toBeNull();
    expect(rotationShortcutDelta({ key: "r", metaKey: true })).toBeNull();
    expect(rotationShortcutDelta({ key: "r", altKey: true })).toBeNull();
    expect(rotationShortcutDelta({ key: "z" })).toBeNull();
  });
});

describe("panScrollOffset", () => {
  it("move o conteúdo junto com o ponteiro", () => {
    const origin = {
      pointerX: 400,
      pointerY: 300,
      scrollLeft: 120,
      scrollTop: 80,
    };
    expect(panScrollOffset(origin, 450, 320)).toEqual({
      scrollLeft: 70,
      scrollTop: 60,
    });
    expect(panScrollOffset(origin, 350, 280)).toEqual({
      scrollLeft: 170,
      scrollTop: 100,
    });
  });
});
