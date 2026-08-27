import { describe, expect, it } from "vitest";

import {
  PRECISOES_NO_DESENHO,
  aplicarZoomDaCena,
  arrastarViewDaCena,
  barraDeEscala,
  caixaDasFormas,
  contagemPorPrecisao,
  enquadramentoInicial,
  fatorDeZoomDaCena,
  formaDaEntidade,
  formasDaCena,
  limitarViewDaCena,
  pontoDoDesenho,
  vaosAplicadosDesenhados,
  vaosEmDisputaDesenhados,
  viewBoxDaCenaAttr,
  type EntidadeDaCena,
} from "./scenePreview";

/**
 * Fixture ASSIMÉTRICA de propósito: é a única que pega inversão de eixo. Uma cena
 * simétrica desenhada de cabeça para baixo parece correta, e o erro só apareceria na obra
 * (critério 5 da F-019).
 *
 * A geometria é um "L": sobe pela esquerda e avança para a direita no alto.
 */
const MURO_EM_L: EntidadeDaCena = {
  id: "01930000-0000-7000-8000-000000000001",
  kind: "polyline",
  layer: "MURO",
  precision: "exact",
  geometry: {
    type: "polyline",
    closed: false,
    points: [
      { x: 0, y: 0 },
      { x: 0, y: 6 },
      { x: 10, y: 6 },
    ],
  },
};

function entidade(
  precision: EntidadeDaCena["precision"],
  id: string,
): EntidadeDaCena {
  return {
    id,
    kind: "line",
    layer: "CONTORNO",
    precision,
    geometry: { type: "line", start: { x: 0, y: 0 }, end: { x: 4, y: 0 } },
  };
}

describe("pontoDoDesenho", () => {
  it("espelha o Y uma vez, e só o Y: a cena tem Y para cima e a tela não", () => {
    expect(pontoDoDesenho({ x: 3, y: 7 })).toEqual({ x: 3, y: -7 });
    expect(pontoDoDesenho({ x: -2, y: -5 })).toEqual({ x: -2, y: 5 });
  });
});

describe("formaDaEntidade", () => {
  it("a geometria assimétrica sai espelhada, e o alto da cena vira o alto do desenho", () => {
    const forma = formaDaEntidade(MURO_EM_L);

    expect(forma?.tipo).toBe("caminho");
    if (forma?.tipo !== "caminho") {
      throw new Error("forma inesperada");
    }
    expect(forma.pontos).toEqual([
      { x: 0, y: -0 },
      { x: 0, y: -6 },
      { x: 10, y: -6 },
    ]);
    // O trecho horizontal está no ALTO da cena (y = 6) e, no desenho, tem o menor Y —
    // que é o alto da tela. Se algum dia isso inverter, o desenho sai de cabeça para baixo.
    const horizontal = forma.pontos[2];
    const base = forma.pontos[0];
    expect(horizontal.y).toBeLessThan(base.y);
  });

  it("linha, círculo, arco e spline viram forma; texto e cota, não", () => {
    const circulo = formaDaEntidade({
      id: "c1",
      kind: "circle",
      layer: "CAMPO",
      precision: "approximate",
      geometry: { type: "circle", center: { x: 5, y: 5 }, radius: 2 },
    });
    expect(circulo).toEqual({
      tipo: "circulo",
      entityId: "c1",
      precisao: "approximate",
      camada: "CAMPO",
      centro: { x: 5, y: -5 },
      raio: 2,
    });

    const arco = formaDaEntidade({
      id: "a1",
      kind: "arc",
      layer: "DETALHES",
      precision: "derived",
      geometry: {
        type: "arc",
        center: { x: 0, y: 0 },
        radius: 1,
        start_angle: 0,
        end_angle: Math.PI / 2,
      },
    });
    expect(arco?.tipo).toBe("caminho");
    if (arco?.tipo === "caminho") {
      // Quarto de volta: começa em (1, 0) e termina em (0, 1) da cena — espelhado, (0, -1).
      expect(arco.pontos[0].x).toBeCloseTo(1);
      expect(arco.pontos[arco.pontos.length - 1].y).toBeCloseTo(-1);
    }

    const texto = formaDaEntidade({
      id: "t1",
      kind: "text",
      layer: "TEXTOS",
      precision: "exact",
      geometry: { type: "text", insertion: { x: 0, y: 0 }, text: "P1", height: 0.2 },
    });
    // O preview é leitura de trabalho: desenhar o texto o faria imitar a prancha.
    expect(texto).toBeNull();

    const cota = formaDaEntidade({
      id: "d1",
      kind: "dimension",
      layer: "COTAS",
      precision: "exact",
      geometry: {
        type: "dimension",
        base: { x: 0, y: -1 },
        first: { x: 0, y: 0 },
        second: { x: 4, y: 0 },
      },
    });
    expect(cota).toBeNull();
  });
});

describe("enquadramento", () => {
  it("a caixa cobre todas as formas, inclusive o raio do círculo", () => {
    const caixa = caixaDasFormas(
      formasDaCena([
        MURO_EM_L,
        {
          id: "c1",
          kind: "circle",
          layer: "CAMPO",
          precision: "unresolved",
          geometry: { type: "circle", center: { x: 12, y: 2 }, radius: 3 },
        },
      ]),
    );

    expect(caixa).toEqual({ left: 0, top: -6, right: 15, bottom: 1 });
  });

  it("cena sem forma nenhuma não tem caixa, e quem chama decide o que dizer", () => {
    expect(caixaDasFormas([])).toBeNull();
  });

  it("cena degenerada continua desenhável: a folga mínima impede viewBox de altura zero", () => {
    const view = enquadramentoInicial({ left: 0, top: 0, right: 10, bottom: 0 });

    expect(view.height).toBeGreaterThan(0);
    expect(view.width).toBeGreaterThan(10);
  });

  it("o enquadramento nunca cola na borda da geometria", () => {
    const view = enquadramentoInicial({ left: 0, top: -6, right: 10, bottom: 0 });

    expect(view.x).toBeLessThan(0);
    expect(view.y).toBeLessThan(-6);
    expect(view.x + view.width).toBeGreaterThan(10);
  });
});

describe("zoom e recorte", () => {
  const inteiro = enquadramentoInicial({ left: 0, top: -6, right: 10, bottom: 0 });

  /** Metros são float: a comparação é por tolerância, nunca por igualdade de bit. */
  function esperarMesmaView(view: typeof inteiro, esperado: typeof inteiro): void {
    expect(view.x).toBeCloseTo(esperado.x, 9);
    expect(view.y).toBeCloseTo(esperado.y, 9);
    expect(view.width).toBeCloseTo(esperado.width, 9);
    expect(view.height).toBeCloseTo(esperado.height, 9);
  }

  it("aproximar preserva o ponto sob o cursor", () => {
    const foco = { x: 8, y: -5 };
    const view = aplicarZoomDaCena(inteiro, inteiro, 2, foco);

    expect(fatorDeZoomDaCena(view, inteiro)).toBeCloseTo(2);
    expect(foco.x).toBeGreaterThanOrEqual(view.x);
    expect(foco.x).toBeLessThanOrEqual(view.x + view.width);
    expect(foco.y).toBeGreaterThanOrEqual(view.y);
    expect(foco.y).toBeLessThanOrEqual(view.y + view.height);
  });

  it("afastar não passa do enquadramento inteiro, e aproximar tem teto", () => {
    const afastado = aplicarZoomDaCena(inteiro, inteiro, 0.1, { x: 5, y: -3 });
    esperarMesmaView(afastado, inteiro);

    let view = inteiro;
    for (let passo = 0; passo < 30; passo += 1) {
      view = aplicarZoomDaCena(view, inteiro, 1.5, { x: 5, y: -3 });
    }
    expect(fatorDeZoomDaCena(view, inteiro)).toBeLessThanOrEqual(12);
  });

  it("arrastar não deixa a view sair do desenho", () => {
    const aproximado = aplicarZoomDaCena(inteiro, inteiro, 4, { x: 5, y: -3 });
    const arrastado = arrastarViewDaCena(aproximado, inteiro, 1000, 1000);

    expect(arrastado.x + arrastado.width).toBeLessThanOrEqual(inteiro.x + inteiro.width + 1e-9);
    expect(arrastado.y + arrastado.height).toBeLessThanOrEqual(inteiro.y + inteiro.height + 1e-9);
  });

  it("view maior que o enquadramento é encolhida até caber", () => {
    const limitada = limitarViewDaCena(
      { x: -100, y: -100, width: 1000, height: 1000 },
      inteiro,
    );

    esperarMesmaView(limitada, inteiro);
  });

  it("o atributo do viewBox é a view em metros, na ordem do SVG", () => {
    expect(viewBoxDaCenaAttr({ x: 1, y: -2, width: 3, height: 4 })).toBe("1 -2 3 4");
  });
});

describe("barraDeEscala", () => {
  it("a barra é uma medida redonda que cabe em um quarto da largura visível", () => {
    const barra = barraDeEscala({ x: 0, y: 0, width: 24, height: 12 });

    expect(barra.metros).toBe(5);
    expect(barra.rotulo).toBe("5 m");
  });

  it("aproximar encolhe a barra: ela é derivada da view, não do desenho inteiro", () => {
    const longe = barraDeEscala({ x: 0, y: 0, width: 100, height: 40 });
    const perto = barraDeEscala({ x: 0, y: 0, width: 4, height: 2 });

    expect(longe.metros).toBeGreaterThan(perto.metros);
    expect(perto.rotulo).toBe("1 m");
  });

  it("medida fracionária é escrita com vírgula, como todo número da tela", () => {
    expect(barraDeEscala({ x: 0, y: 0, width: 1.2, height: 1 }).rotulo).toBe("0,25 m");
  });
});

describe("contagemPorPrecisao", () => {
  it("conta por precisão e omite as que não têm entidade nenhuma", () => {
    const contagem = contagemPorPrecisao([
      entidade("exact", "e1"),
      entidade("exact", "e2"),
      entidade("unresolved", "e3"),
    ]);

    expect(contagem).toEqual([
      { precisao: "exact", nome: "exata", quantidade: 2 },
      { precisao: "unresolved", nome: "não resolvida", quantidade: 1 },
    ]);
  });

  it("as quatro precisões têm nome e traço escritos: a legenda não depende de cor", () => {
    expect(PRECISOES_NO_DESENHO).toHaveLength(4);
    for (const item of PRECISOES_NO_DESENHO) {
      expect(item.nome.length).toBeGreaterThan(0);
      expect(item.traco.length).toBeGreaterThan(0);
    }
    // Quatro traços distintos: se dois coincidirem, duas precisões viram uma no desenho.
    expect(new Set(PRECISOES_NO_DESENHO.map((item) => item.traco)).size).toBe(4);
  });
});

describe("vãos do consultor sobre a geometria", () => {
  const caixa = { left: 0, top: -6, right: 10, bottom: 0 };

  it("vão aplicado vira cota onde ancorou, fora da geometria", () => {
    const [vao] = vaosAplicadosDesenhados(
      [
        {
          reading_id: "rd_0000000000000001",
          axis: "x",
          value_m: 9.5,
          start_m: 0.5,
          end_m: 10,
        },
      ],
      caixa,
    );

    expect(vao.de).toBe(0.5);
    expect(vao.ate).toBe(10);
    expect(vao.rotulo).toBe("9,50 m");
    // Desenhada abaixo da caixa: cota em cima da geometria esconderia o que ela mede.
    expect(vao.offset).toBeGreaterThan(caixa.bottom);
  });

  it("no eixo Y a cota acompanha o espelhamento, e de/até saem ordenados", () => {
    const [vao] = vaosAplicadosDesenhados(
      [
        {
          reading_id: "rd_0000000000000002",
          axis: "y",
          value_m: 5.5,
          start_m: 0.5,
          end_m: 6,
        },
      ],
      caixa,
    );

    expect(vao.de).toBe(-6);
    expect(vao.ate).toBe(-0.5);
    expect(vao.de).toBeLessThan(vao.ate);
    expect(vao.offset).toBeGreaterThan(caixa.right);
  });

  it("vão em disputa é faixa do eixo, com os valores que se contradizem", () => {
    const [vao] = vaosEmDisputaDesenhados(
      [
        {
          axis: "x",
          values_m: [4.8, 3.3],
          reading_ids: ["rd_0000000000000003", "rd_0000000000000004"],
        },
      ],
      caixa,
    );

    expect(vao.eixo).toBe("x");
    expect(vao.rotulo).toBe("eixo X em disputa · 4,80 m × 3,30 m");
    expect(vao.readingIds).toHaveLength(2);
    // Fora da caixa, e sem posição AO LONGO do eixo: o servidor não a declara, e inventá-la
    // seria desenhar dado que não existe.
    expect(vao.offset).toBeLessThan(caixa.top);
    expect(vao).not.toHaveProperty("de");
    expect(vao).not.toHaveProperty("ate");
  });

  it("duas disputas não se sobrepõem: cada uma ganha a própria faixa", () => {
    const vaos = vaosEmDisputaDesenhados(
      [
        { axis: "x", values_m: [4.8, 3.3], reading_ids: ["rd_1"] },
        { axis: "x", values_m: [2.1, 2.4], reading_ids: ["rd_2"] },
      ],
      caixa,
    );

    expect(vaos[0].offset).not.toBe(vaos[1].offset);
  });
});
