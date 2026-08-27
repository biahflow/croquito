import { describe, expect, it } from "vitest";

import {
  aplicarZoom,
  arrastarView,
  caixaVisivel,
  enquadrarCaixa,
  fatorDeZoom,
  limitarView,
  paginaInteira,
  pontoDaImagem,
  viewBoxAttr,
  ZOOM_MAXIMO,
  type Caixa,
  type Pagina,
} from "./prancha";

/** Uma prancha A1 a 200 DPI, que é a ordem de grandeza do que o worker promove. */
const PAGINA: Pagina = { width: 6600, height: 4677 };

describe("paginaInteira", () => {
  it("começa mostrando a prancha inteira, sem zoom", () => {
    const view = paginaInteira(PAGINA);
    expect(view).toEqual({ x: 0, y: 0, width: 6600, height: 4677 });
    expect(fatorDeZoom(view, PAGINA)).toBe(1);
  });
});

describe("limitarView", () => {
  it("prende a janela dentro da página quando o arrasto passa da borda", () => {
    const view = limitarView({ x: -500, y: -900, width: 3300, height: 2338.5 }, PAGINA);
    expect(view.x).toBe(0);
    expect(view.y).toBe(0);
  });

  it("prende a janela na borda oposta também", () => {
    const view = limitarView({ x: 99999, y: 99999, width: 3300, height: 2338.5 }, PAGINA);
    expect(view.x).toBeCloseTo(3300);
    expect(view.y).toBeCloseTo(PAGINA.height - 2338.5);
  });

  it("recusa aproximar além do teto declarado", () => {
    const view = limitarView({ x: 0, y: 0, width: 1, height: 1 }, PAGINA);
    expect(fatorDeZoom(view, PAGINA)).toBeCloseTo(ZOOM_MAXIMO);
  });

  it("nunca deforma a prancha: a janela mantém a proporção da página", () => {
    const view = limitarView({ x: 0, y: 0, width: 3300, height: 10 }, PAGINA);
    expect(view.width / view.height).toBeCloseTo(PAGINA.width / PAGINA.height);
  });
});

describe("aplicarZoom", () => {
  it("mantém parado o ponto focado, que é o item que a pessoa está olhando", () => {
    const inicial = paginaInteira(PAGINA);
    const foco = { x: 1650, y: 1169 };
    const view = aplicarZoom(inicial, PAGINA, 2, foco);
    const fracaoX = (foco.x - view.x) / view.width;
    const fracaoY = (foco.y - view.y) / view.height;
    expect(fracaoX).toBeCloseTo(0.25);
    expect(fracaoY).toBeCloseTo(0.25);
    expect(fatorDeZoom(view, PAGINA)).toBeCloseTo(2);
  });

  it("sem foco declarado, aproxima pelo centro da janela", () => {
    const view = aplicarZoom(paginaInteira(PAGINA), PAGINA, 2);
    expect(view.x + view.width / 2).toBeCloseTo(PAGINA.width / 2);
    expect(view.y + view.height / 2).toBeCloseTo(PAGINA.height / 2);
  });

  it("afastar volta para a página inteira e não passa disso", () => {
    const perto = aplicarZoom(paginaInteira(PAGINA), PAGINA, 4);
    const longe = aplicarZoom(perto, PAGINA, 1 / 100);
    expect(longe).toEqual(paginaInteira(PAGINA));
  });

  it("fator inválido devolve a janela intacta em vez de produzir NaN", () => {
    const view = paginaInteira(PAGINA);
    expect(aplicarZoom(view, PAGINA, 0)).toEqual(view);
    expect(aplicarZoom(view, PAGINA, -2)).toEqual(view);
  });
});

describe("arrastarView", () => {
  it("desloca a janela e continua presa à página", () => {
    const perto = aplicarZoom(paginaInteira(PAGINA), PAGINA, 4);
    const movida = arrastarView(perto, PAGINA, 200, 100);
    expect(movida.x).toBeCloseTo(perto.x + 200);
    expect(movida.y).toBeCloseTo(perto.y + 100);
    expect(arrastarView(perto, PAGINA, -99999, -99999).x).toBe(0);
  });
});

describe("enquadrarCaixa", () => {
  const ancora: Caixa = { left: 5200, top: 700, right: 5600, bottom: 900 };

  it("centraliza a âncora do item escolhido", () => {
    const view = enquadrarCaixa(ancora, PAGINA);
    expect(view.x + view.width / 2).toBeCloseTo(5400);
    expect(view.y + view.height / 2).toBeCloseTo(800);
  });

  it("deixa folga em volta: a âncora colada na borda não se lê", () => {
    const view = enquadrarCaixa(ancora, PAGINA);
    expect(view.width).toBeGreaterThan(ancora.right - ancora.left);
    expect(caixaVisivel(ancora, view)).toBe(true);
  });

  it("âncora minúscula não estoura o teto de zoom", () => {
    const ponto: Caixa = { left: 3000, top: 2000, right: 3000, bottom: 2000 };
    const view = enquadrarCaixa(ponto, PAGINA);
    expect(fatorDeZoom(view, PAGINA)).toBeLessThanOrEqual(ZOOM_MAXIMO + 0.001);
  });

  it("âncora no canto continua dentro da página, sem janela negativa", () => {
    const canto: Caixa = { left: 0, top: 0, right: 120, bottom: 80 };
    const view = enquadrarCaixa(canto, PAGINA);
    expect(view.x).toBe(0);
    expect(view.y).toBe(0);
    expect(caixaVisivel(canto, view)).toBe(true);
  });
});

describe("caixaVisivel", () => {
  it("distingue a âncora à vista da que ficou fora da janela", () => {
    const view = { x: 0, y: 0, width: 3300, height: 2338.5 };
    expect(caixaVisivel({ left: 100, top: 100, right: 200, bottom: 200 }, view)).toBe(true);
    expect(caixaVisivel({ left: 5200, top: 700, right: 5600, bottom: 900 }, view)).toBe(false);
  });
});

describe("pontoDaImagem", () => {
  it("traduz a fração do elemento renderizado para pixel da prancha", () => {
    const view = { x: 1000, y: 500, width: 2000, height: 1400 };
    expect(pontoDaImagem(view, 0.5, 0.5)).toEqual({ x: 2000, y: 1200 });
    expect(pontoDaImagem(view, 0, 0)).toEqual({ x: 1000, y: 500 });
  });
});

describe("viewBoxAttr", () => {
  it("escreve o atributo na ordem que o SVG espera", () => {
    expect(viewBoxAttr({ x: 10, y: 20, width: 30, height: 40 })).toBe("10 20 30 40");
  });
});
