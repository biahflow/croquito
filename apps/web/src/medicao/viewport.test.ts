import { describe, expect, it } from "vitest";
import type { PlateBox } from "./api";
import {
  bboxRect,
  clampZoom,
  MAX_ZOOM,
  MIN_ZOOM,
  panScrollOffset,
  pinPlacement,
  stageStyle,
  zoomAfterWheel,
  ZOOM_STEP,
  type PinCircle,
} from "./viewport";

describe("clampZoom", () => {
  it("mantém o zoom dentro dos limites e trata valor inválido", () => {
    expect(clampZoom(2)).toBe(2);
    expect(clampZoom(0.1)).toBe(MIN_ZOOM);
    expect(clampZoom(99)).toBe(MAX_ZOOM);
    expect(clampZoom(Number.NaN)).toBe(MIN_ZOOM);
  });
});

describe("zoomAfterWheel", () => {
  it("roda para cima aproxima, para baixo afasta, e respeita os limites", () => {
    expect(zoomAfterWheel(2, -1)).toBe(2 + ZOOM_STEP);
    expect(zoomAfterWheel(2, 1)).toBe(2 - ZOOM_STEP);
    expect(zoomAfterWheel(MIN_ZOOM, 10)).toBe(MIN_ZOOM);
    expect(zoomAfterWheel(MAX_ZOOM, -10)).toBe(MAX_ZOOM);
  });

  it("roda sem deslocamento não mexe no zoom", () => {
    expect(zoomAfterWheel(1.5, 0)).toBe(1.5);
    expect(zoomAfterWheel(1.5, Number.NaN)).toBe(1.5);
  });
});

describe("stageStyle", () => {
  it("cresce o palco com o zoom e preserva a proporção da imagem", () => {
    expect(stageStyle(1, 1700, 2200)).toEqual({
      width: "100%",
      aspectRatio: "1700 / 2200",
    });
    expect(stageStyle(2.5, 1700, 2200).width).toBe("250%");
  });

  it("imagem sem dimensão conhecida não vira divisão por zero", () => {
    expect(stageStyle(1, 0, 0).aspectRatio).toBe("1 / 1");
  });
});

describe("panScrollOffset", () => {
  it("move o scroll ao contrário do ponteiro, para o desenho seguir a mão", () => {
    const origin = { pointerX: 100, pointerY: 80, scrollLeft: 400, scrollTop: 300 };

    expect(panScrollOffset(origin, 140, 60)).toEqual({
      scrollLeft: 360,
      scrollTop: 320,
    });
  });
});

describe("bboxRect", () => {
  it("converte a bbox da evidência no retângulo do overlay", () => {
    expect(bboxRect({ left: 1042, top: 250, right: 1675, bottom: 317 })).toEqual({
      x: 1042,
      y: 250,
      width: 633,
      height: 67,
    });
  });

  it("bbox degenerada ainda produz retângulo clicável", () => {
    expect(bboxRect({ left: 10, top: 10, right: 10, bottom: 10 })).toEqual({
      x: 10,
      y: 10,
      width: 1,
      height: 1,
    });
  });
});

describe("pinPlacement", () => {
  const IMAGE_WIDTH = 1700;
  const IMAGE_HEIGHT = 2200;
  const DIAMETER = 36;

  /** Distância do centro do círculo ao ponto mais próximo do retângulo, ao quadrado —
   * o oráculo de "não intersecta": círculo e bbox só se tocam se essa distância for
   * menor que o raio ao quadrado. */
  function overlapsBbox(pin: PinCircle, bbox: PlateBox): boolean {
    const rect = bboxRect(bbox);
    const closestX = Math.max(rect.x, Math.min(pin.cx, rect.x + rect.width));
    const closestY = Math.max(rect.y, Math.min(pin.cy, rect.y + rect.height));
    const dx = pin.cx - closestX;
    const dy = pin.cy - closestY;
    return dx * dx + dy * dy < pin.r * pin.r - 1e-6;
  }

  it("ancora à esquerda do bbox, a 0,8 diâmetro de bbox.left, centralizado na altura da linha", () => {
    const bbox = { left: 1042, top: 250, right: 1675, bottom: 317 };

    const pin = pinPlacement(bbox, DIAMETER, IMAGE_WIDTH, IMAGE_HEIGHT);

    expect(pin.r).toBe(DIAMETER / 2);
    expect(pin.cx).toBe(1042 - 0.8 * DIAMETER);
    expect(pin.cy).toBe((250 + 317) / 2);
    expect(overlapsBbox(pin, bbox)).toBe(false);
  });

  it("cai para acima do canto superior-esquerdo quando o bbox está encostado na borda esquerda", () => {
    const bbox = { left: 3, top: 400, right: 300, bottom: 460 };

    const pin = pinPlacement(bbox, DIAMETER, IMAGE_WIDTH, IMAGE_HEIGHT);

    // Sem espaço à esquerda: o pino sobe para cima do bbox em vez de descer sobre ele.
    expect(pin.cy).toBeLessThan(400);
    expect(overlapsBbox(pin, bbox)).toBe(false);
  });

  it("clampa para dentro da imagem quando o bbox está no canto superior-esquerdo", () => {
    const bbox = { left: 2, top: 2, right: 120, bottom: 40 };

    const pin = pinPlacement(bbox, DIAMETER, IMAGE_WIDTH, IMAGE_HEIGHT);

    expect(pin.cx).toBeGreaterThanOrEqual(pin.r);
    expect(pin.cy).toBeGreaterThanOrEqual(pin.r);
    expect(overlapsBbox(pin, bbox)).toBe(false);
  });

  it("clampa para dentro da imagem quando o bbox está encostado na borda inferior", () => {
    const bbox = { left: 900, top: IMAGE_HEIGHT - 5, right: 1020, bottom: IMAGE_HEIGHT };

    const pin = pinPlacement(bbox, DIAMETER, IMAGE_WIDTH, IMAGE_HEIGHT);

    expect(pin.cy).toBeLessThanOrEqual(IMAGE_HEIGHT - pin.r);
    expect(overlapsBbox(pin, bbox)).toBe(false);
  });

  it("nunca intersecta o próprio bbox, numa varredura de posições pela imagem", () => {
    const positions = [
      { left: 0, top: 0 },
      { left: 5, top: 5 },
      { left: 900, top: 100 },
      { left: IMAGE_WIDTH - 130, top: 50 },
      { left: 50, top: IMAGE_HEIGHT - 50 },
      { left: IMAGE_WIDTH - 130, top: IMAGE_HEIGHT - 50 },
    ];
    for (const { left, top } of positions) {
      const bbox = { left, top, right: left + 120, bottom: top + 34 };
      const pin = pinPlacement(bbox, DIAMETER, IMAGE_WIDTH, IMAGE_HEIGHT);
      expect(overlapsBbox(pin, bbox)).toBe(false);
    }
  });
});
