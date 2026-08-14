import { describe, expect, it } from "vitest";

import type { VisionProposal } from "./api";
import {
  clientToImagePoint,
  isMarqueeDrag,
  marqueeSelection,
  normalizedRect,
  rectHitsGeometry,
  type ClientBox,
  type ImageRect,
} from "./selection";

/** A folha do Guaxindiba renderizada a 200 DPI. */
const IMAGE_WIDTH = 4875;
const IMAGE_HEIGHT = 6718;

/** Caixa do `.preview-transform` sem girar: retrato, como a folha. */
const UPRIGHT: ClientBox = { left: 100, top: 50, width: 400, height: 800 };
/** Um quarto de volta troca largura por altura na AABB devolvida pelo browser. */
const TURNED: ClientBox = { left: 100, top: 50, width: 800, height: 400 };

function imagePoint(
  clientX: number,
  clientY: number,
  box: ClientBox,
  rotation: number,
) {
  const point = clientToImagePoint(
    clientX,
    clientY,
    box,
    rotation,
    IMAGE_WIDTH,
    IMAGE_HEIGHT,
  );
  // Meia folha é 2437,5 px: arredondar para inteiro apagaria justamente o eixo que o
  // teste da rotação precisa distinguir. Quatro casas só absorvem ruído de ponto
  // flutuante.
  return [Number(point.x.toFixed(4)), Number(point.y.toFixed(4))];
}

function line(
  id: string,
  start: { x: number; y: number },
  end: { x: number; y: number },
): VisionProposal {
  return {
    id,
    kind: "line",
    precision: "unresolved",
    export: false,
    geometry: { type: "line", start, end },
  };
}

function rect(
  left: number,
  top: number,
  right: number,
  bottom: number,
): ImageRect {
  return { left, top, right, bottom };
}

describe("normalizedRect", () => {
  it("ordena os cantos qualquer que seja o sentido do arrasto", () => {
    const expected = rect(10, 20, 60, 80);
    expect(normalizedRect({ x: 60, y: 80 }, { x: 10, y: 20 })).toEqual(expected);
    expect(normalizedRect({ x: 10, y: 80 }, { x: 60, y: 20 })).toEqual(expected);
    expect(normalizedRect({ x: 60, y: 20 }, { x: 10, y: 80 })).toEqual(expected);
  });

  it("aceita o retângulo degenerado do clique parado", () => {
    expect(normalizedRect({ x: 7, y: 9 }, { x: 7, y: 9 })).toEqual(
      rect(7, 9, 7, 9),
    );
  });
});

describe("isMarqueeDrag", () => {
  it("trata deslocamento abaixo do limiar como clique", () => {
    expect(isMarqueeDrag(200, 300, 203, 302)).toBe(false);
    expect(isMarqueeDrag(200, 300, 200, 300)).toBe(false);
  });

  it("basta um eixo passar do limiar, em qualquer sentido", () => {
    expect(isMarqueeDrag(200, 300, 204, 300)).toBe(true);
    expect(isMarqueeDrag(200, 300, 200, 296)).toBe(true);
    expect(isMarqueeDrag(200, 300, 260, 380)).toBe(true);
  });
});

describe("clientToImagePoint", () => {
  it("mapeia cantos e centro sem rotação", () => {
    expect(imagePoint(100, 50, UPRIGHT, 0)).toEqual([0, 0]);
    expect(imagePoint(500, 850, UPRIGHT, 0)).toEqual([IMAGE_WIDTH, IMAGE_HEIGHT]);
    expect(imagePoint(300, 450, UPRIGHT, 0)).toEqual([
      IMAGE_WIDTH / 2,
      IMAGE_HEIGHT / 2,
    ]);
  });

  it("segue o canto da imagem em cada quarto de volta", () => {
    // Girando um quarto de volta à direita, o canto superior esquerdo da folha vai
    // para o canto superior direito da caixa; meia volta o joga para o inferior
    // direito e três quartos para o inferior esquerdo.
    expect(imagePoint(900, 50, TURNED, 90)).toEqual([0, 0]);
    expect(imagePoint(500, 850, UPRIGHT, 180)).toEqual([0, 0]);
    expect(imagePoint(100, 450, TURNED, 270)).toEqual([0, 0]);
  });

  it("mapeia o canto oposto da folha em cada quarto de volta", () => {
    const opposite = [IMAGE_WIDTH, IMAGE_HEIGHT];
    expect(imagePoint(100, 450, TURNED, 90)).toEqual(opposite);
    expect(imagePoint(100, 50, UPRIGHT, 180)).toEqual(opposite);
    expect(imagePoint(900, 50, TURNED, 270)).toEqual(opposite);
  });

  it("mantém o centro no centro em todas as rotações", () => {
    const center = [IMAGE_WIDTH / 2, IMAGE_HEIGHT / 2];
    expect(imagePoint(300, 450, UPRIGHT, 0)).toEqual(center);
    expect(imagePoint(500, 250, TURNED, 90)).toEqual(center);
    expect(imagePoint(300, 450, UPRIGHT, 180)).toEqual(center);
    expect(imagePoint(500, 250, TURNED, 270)).toEqual(center);
  });

  it("distingue os eixos girados: meia altura da folha vira meia largura da caixa", () => {
    // A 90°, andar para a direita na tela é descer na folha.
    expect(imagePoint(500, 50, TURNED, 90)).toEqual([0, IMAGE_HEIGHT / 2]);
    expect(imagePoint(900, 250, TURNED, 90)).toEqual([IMAGE_WIDTH / 2, 0]);
  });

  it("prende o ponteiro à folha quando o arrasto sai da caixa", () => {
    expect(imagePoint(-4000, -4000, UPRIGHT, 0)).toEqual([0, 0]);
    expect(imagePoint(9000, 9000, UPRIGHT, 0)).toEqual([
      IMAGE_WIDTH,
      IMAGE_HEIGHT,
    ]);
    expect(imagePoint(9000, -4000, TURNED, 90)).toEqual([0, 0]);
  });

  it("devolve a origem, e não NaN, quando a caixa ainda não foi medida", () => {
    for (const box of [
      { left: 100, top: 50, width: 0, height: 800 },
      { left: 100, top: 50, width: 400, height: 0 },
      { left: 100, top: 50, width: Number.NaN, height: 800 },
    ]) {
      const point = clientToImagePoint(
        320,
        480,
        box,
        90,
        IMAGE_WIDTH,
        IMAGE_HEIGHT,
      );
      expect(point).toEqual({ x: 0, y: 0 });
    }
  });

  it("normaliza rotação fora dos quartos de volta como o viewer", () => {
    expect(imagePoint(900, 50, TURNED, -270)).toEqual([0, 0]);
    expect(imagePoint(900, 50, TURNED, 450)).toEqual([0, 0]);
  });
});

describe("rectHitsGeometry — linha", () => {
  const crossing = rect(40, 0, 60, 100);

  it("seleciona a linha que atravessa sem ter extremo dentro", () => {
    expect(
      rectHitsGeometry(crossing, {
        type: "line",
        start: { x: 0, y: 50 },
        end: { x: 200, y: 50 },
      }),
    ).toBe(true);
  });

  it("seleciona a linha com um extremo dentro", () => {
    expect(
      rectHitsGeometry(crossing, {
        type: "line",
        start: { x: 50, y: 50 },
        end: { x: 500, y: 900 },
      }),
    ).toBe(true);
  });

  it("seleciona a diagonal que corta o canto", () => {
    expect(
      rectHitsGeometry(rect(0, 0, 10, 10), {
        type: "line",
        start: { x: 9, y: 0 },
        end: { x: 20, y: 11 },
      }),
    ).toBe(true);
  });

  it("ignora a linha que passa longe", () => {
    expect(
      rectHitsGeometry(crossing, {
        type: "line",
        start: { x: 0, y: 200 },
        end: { x: 200, y: 200 },
      }),
    ).toBe(false);
  });

  it("ignora a linha cuja projeção cruza o retângulo mas o segmento não chega lá", () => {
    expect(
      rectHitsGeometry(crossing, {
        type: "line",
        start: { x: 0, y: 50 },
        end: { x: 20, y: 50 },
      }),
    ).toBe(false);
  });

  it("encostar basta: o critério é crossing, não envolvimento", () => {
    expect(
      rectHitsGeometry(crossing, {
        type: "line",
        start: { x: 60, y: 0 },
        end: { x: 60, y: 100 },
      }),
    ).toBe(true);
  });
});

describe("rectHitsGeometry — círculo", () => {
  const circle = {
    type: "circle" as const,
    center: { x: 100, y: 100 },
    radius: 50,
  };

  it("seleciona quando o retângulo toca o traço", () => {
    expect(rectHitsGeometry(rect(140, 90, 200, 110), circle)).toBe(true);
  });

  it("seleciona o círculo inteiro contido no retângulo", () => {
    expect(rectHitsGeometry(rect(0, 0, 300, 300), circle)).toBe(true);
  });

  it("não seleciona o retângulo inteiro dentro do círculo: o traço não foi tocado", () => {
    expect(rectHitsGeometry(rect(90, 90, 110, 110), circle)).toBe(false);
  });

  it("não seleciona o retângulo fora do alcance do traço", () => {
    expect(rectHitsGeometry(rect(300, 300, 400, 400), circle)).toBe(false);
  });

  it("seleciona quando a borda do retângulo tangencia o traço", () => {
    expect(rectHitsGeometry(rect(150, 95, 200, 105), circle)).toBe(true);
  });
});

describe("rectHitsGeometry — polilinha", () => {
  const points = [
    { x: 0, y: 0 },
    { x: 100, y: 0 },
    { x: 100, y: 100 },
    { x: 0, y: 100 },
  ];
  /** Só o segmento de fechamento (0,100)→(0,0) passa por aqui. */
  const closingOnly = rect(-5, 40, 5, 60);

  it("seleciona pelo segmento intermediário", () => {
    expect(
      rectHitsGeometry(rect(95, 40, 105, 60), {
        type: "polyline",
        points,
        closed: false,
      }),
    ).toBe(true);
  });

  it("contorno aberto não ganha o segmento de fechamento", () => {
    expect(
      rectHitsGeometry(closingOnly, { type: "polyline", points, closed: false }),
    ).toBe(false);
  });

  it("contorno fechado responde pelo segmento de fechamento", () => {
    expect(
      rectHitsGeometry(closingOnly, { type: "polyline", points, closed: true }),
    ).toBe(true);
  });

  it("ignora a polilinha inteiramente fora", () => {
    expect(
      rectHitsGeometry(rect(500, 500, 600, 600), {
        type: "polyline",
        points,
        closed: true,
      }),
    ).toBe(false);
  });

  it("polilinha degenerada de um ponto vale pelo ponto", () => {
    const single = [{ x: 10, y: 10 }];
    expect(
      rectHitsGeometry(rect(0, 0, 20, 20), {
        type: "polyline",
        points: single,
        closed: false,
      }),
    ).toBe(true);
    expect(
      rectHitsGeometry(rect(30, 30, 40, 40), {
        type: "polyline",
        points: single,
        closed: false,
      }),
    ).toBe(false);
  });
});

describe("marqueeSelection", () => {
  const proposals: VisionProposal[] = [
    line("vp_a", { x: 0, y: 10 }, { x: 200, y: 10 }),
    line("vp_b", { x: 0, y: 20 }, { x: 200, y: 20 }),
    line("vp_c", { x: 0, y: 30 }, { x: 200, y: 30 }),
    line("vp_d", { x: 0, y: 900 }, { x: 200, y: 900 }),
  ];

  it("devolve os ids tocados na ordem da lista", () => {
    expect(marqueeSelection(rect(50, 0, 60, 100), proposals, new Set())).toEqual(
      ["vp_a", "vp_b", "vp_c"],
    );
  });

  it("mantém a ordem da lista mesmo com o arrasto de baixo para cima", () => {
    const upward = normalizedRect({ x: 60, y: 100 }, { x: 50, y: 0 });
    expect(marqueeSelection(upward, proposals, new Set())).toEqual([
      "vp_a",
      "vp_b",
      "vp_c",
    ]);
  });

  it("exclui proposta já decidida: decisão registrada é imutável", () => {
    expect(
      marqueeSelection(
        rect(50, 0, 60, 100),
        proposals,
        new Set(["vp_b", "vp_d"]),
      ),
    ).toEqual(["vp_a", "vp_c"]);
  });

  it("devolve vazio quando o retângulo não toca nada", () => {
    expect(
      marqueeSelection(rect(50, 400, 60, 500), proposals, new Set()),
    ).toEqual([]);
  });

  it("devolve vazio sem propostas", () => {
    expect(marqueeSelection(rect(0, 0, 1000, 1000), [], new Set())).toEqual([]);
  });
});
