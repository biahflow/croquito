import { describe, expect, it } from "vitest";

import {
  aplicarZoom,
  arrastarView,
  caixaVisivel,
  emblemaDaCaixa,
  raioDoEmblema,
  enquadrarCaixa,
  fatorDeZoom,
  limitarView,
  paginaInteira,
  pontoDaImagem,
  viewBoxAttr,
  ZOOM_MAXIMO,
  type Caixa,
  type Emblema,
  type Pagina,
  type ViewBox,
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

/**
 * O emblema numerado fica SEMPRE fora do bbox que ele marca: dentro, o círculo cobre
 * letras da linha da legenda — o defeito visto na prancha real ("PISO EM(1)CONCRETO") —,
 * e quem confere quantidade contra desenho perde justamente o texto que precisa ler.
 */
describe("emblemaDaCaixa", () => {
  const RAIO = 40;

  /** Sobreposição de verdade: encostar na borda do bbox não conta. */
  const sobrepoe = (emblema: Emblema, caixa: Caixa): boolean => {
    const largura = Math.max(caixa.right - caixa.left, 1);
    const altura = Math.max(caixa.bottom - caixa.top, 1);
    const proximoX = Math.max(caixa.left, Math.min(emblema.cx, caixa.left + largura));
    const proximoY = Math.max(caixa.top, Math.min(emblema.cy, caixa.top + altura));
    const dx = emblema.cx - proximoX;
    const dy = emblema.cy - proximoY;
    return dx * dx + dy * dy < emblema.r * emblema.r;
  };

  it("pede a esquerda da caixa, centrado na altura da linha", () => {
    const caixa: Caixa = { left: 2000, top: 1000, right: 2600, bottom: 1080 };
    const emblema = emblemaDaCaixa(caixa, RAIO, PAGINA);

    expect(emblema.r).toBe(RAIO);
    expect(emblema.cx).toBeLessThan(caixa.left);
    expect(emblema.cy).toBeCloseTo(1040);
    expect(sobrepoe(emblema, caixa)).toBe(false);
  });

  it("fica à esquerda da caixa com respiro, sem se afastar da linha que identifica", () => {
    // O emblema tem de sair da caixa e continuar ao lado dela: quem lê a lista procura o
    // número na MESMA altura do item, e um emblema atirado longe deixa de apontar a linha.
    // Este teste já exigiu 4 raios de afastamento, para escapar do rótulo — mas aquilo
    // compensava, na tela, um bbox que a extração entregava deslocado. Com a âncora certa
    // (`register_legend_bboxes` mede a borda da tabela na tinta) a folga volta a ser só
    // folga, e o teto abaixo é o que impede a compensação de voltar disfarçada.
    const caixa: Caixa = { left: 2000, top: 1000, right: 2600, bottom: 1080 };
    const emblema = emblemaDaCaixa(caixa, RAIO, PAGINA);

    const afastamento = caixa.left - emblema.cx;
    expect(afastamento).toBeGreaterThan(RAIO);
    expect(afastamento).toBeLessThanOrEqual(RAIO * 2);
    expect(sobrepoe(emblema, caixa)).toBe(false);
  });

  it("caixa no canto superior esquerdo não cabe à esquerda e sobe para cima dela", () => {
    // Sem espaço à esquerda (o centro seria clampado para dentro do próprio bbox), o
    // fallback pedido é acima; ainda assim tem de sobrar página acima da caixa.
    const caixa: Caixa = { left: 0, top: 300, right: 500, bottom: 380 };
    const emblema = emblemaDaCaixa(caixa, RAIO, PAGINA);

    expect(emblema.cy).toBeLessThan(caixa.top);
    expect(emblema.cx).toBeGreaterThanOrEqual(RAIO);
    expect(sobrepoe(emblema, caixa)).toBe(false);
  });

  it("caixa colada na borda direita continua com o emblema dentro da página", () => {
    const caixa: Caixa = { left: PAGINA.width - 400, top: 2000, right: PAGINA.width, bottom: 2090 };
    const emblema = emblemaDaCaixa(caixa, RAIO, PAGINA);

    expect(emblema.cx).toBeGreaterThanOrEqual(RAIO);
    expect(emblema.cx).toBeLessThanOrEqual(PAGINA.width - RAIO);
    expect(emblema.cy).toBeGreaterThanOrEqual(RAIO);
    expect(emblema.cy).toBeLessThanOrEqual(PAGINA.height - RAIO);
    expect(sobrepoe(emblema, caixa)).toBe(false);
  });

  it("caixa de largura zero não vira divisão por zero nem emblema sobreposto", () => {
    const ponto: Caixa = { left: 3000, top: 2000, right: 3000, bottom: 2000 };
    const emblema = emblemaDaCaixa(ponto, RAIO, PAGINA);

    expect(Number.isFinite(emblema.cx)).toBe(true);
    expect(Number.isFinite(emblema.cy)).toBe(true);
    expect(sobrepoe(emblema, ponto)).toBe(false);
  });

  it("nenhuma âncora do pacote recebe emblema sobre o próprio bbox", () => {
    const caixas: Caixa[] = [
      { left: 0, top: 0, right: 300, bottom: 90 },
      { left: 0, top: 0, right: PAGINA.width, bottom: 120 },
      { left: 120, top: 40, right: 900, bottom: 130 },
      { left: PAGINA.width - 200, top: PAGINA.height - 120, right: PAGINA.width, bottom: PAGINA.height },
      { left: 4000, top: 2300, right: 4100, bottom: 2300 },
    ];

    for (const caixa of caixas) {
      const emblema = emblemaDaCaixa(caixa, RAIO, PAGINA);
      expect(sobrepoe(emblema, caixa)).toBe(false);
    }
  });

  it("raio inválido não propaga NaN para o desenho", () => {
    const caixa: Caixa = { left: 2000, top: 1000, right: 2600, bottom: 1080 };
    const emblema = emblemaDaCaixa(caixa, Number.NaN, PAGINA);

    expect(emblema.r).toBe(1);
    expect(Number.isFinite(emblema.cx)).toBe(true);
    expect(Number.isFinite(emblema.cy)).toBe(true);
  });
});

/**
 * O raio do emblema é o que impede a coluna de números de virar uma pilha ilegível: numa
 * legenda densa o passo entre linhas é menor que o diâmetro que a janela pediria.
 */
describe("raioDoEmblema", () => {
  const linhaDensa: Caixa = { left: 7132, top: 2322, right: 8140, bottom: 2377 };

  it("nunca passa de meia altura da linha, para emblemas vizinhos não se cobrirem", () => {
    const view: ViewBox = { x: 6800, y: 2200, width: 1900, height: 1345 };
    const raio = raioDoEmblema(view, linhaDensa);
    const altura = linhaDensa.bottom - linhaDensa.top;

    expect(raio).toBeLessThanOrEqual(altura / 2);
    // Sem o teto, a janela pediria 1900/45 ≈ 42 — mais que a altura inteira da linha.
    expect(view.width / 45).toBeGreaterThan(altura / 2);
  });

  it("acompanha a janela quando a linha é alta o bastante para caber", () => {
    const alta: Caixa = { left: 0, top: 0, right: 1000, bottom: 400 };
    const view: ViewBox = { x: 0, y: 0, width: 1800, height: 1200 };

    expect(raioDoEmblema(view, alta)).toBeCloseTo(40);
  });

  it("respeita o piso de legibilidade mesmo em linha fininha", () => {
    const fina: Caixa = { left: 0, top: 0, right: 1000, bottom: 6 };
    const view: ViewBox = { x: 0, y: 0, width: 200, height: 140 };

    expect(raioDoEmblema(view, fina)).toBe(10);
  });
});
