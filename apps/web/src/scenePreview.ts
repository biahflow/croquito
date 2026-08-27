/**
 * Derivação pura do preview da cena resolvida (F-019).
 *
 * A cena é métrica e tem **Y para cima**; a tela é Y para baixo. Todo ponto que entra aqui
 * sai espelhado UMA vez, em `pontoDoDesenho`, e daí em diante tudo — enquadramento, cotas,
 * barra de escala — trabalha no mesmo espaço. Espelhar em vários lugares é como uma
 * inversão de eixo passa despercebida numa geometria simétrica e aparece só na obra.
 *
 * As unidades deste módulo são **metros da cena**, nunca pixels: o `viewBox` do SVG carrega
 * a conversão, e por isso o desenho e as cotas se movem juntos por construção. Nada aqui
 * sabe de React, de evento de mouse ou de CSS.
 *
 * Não reusa `orcamento/prancha.ts` de propósito: aquele módulo enquadra uma imagem em
 * pixels de página, com piso em `paginaInteira`; este enquadra geometria em metros, com Y
 * espelhado e sem página que limite. São a mesma ideia sobre espaços diferentes, e a
 * convenção do repositório já é ter a aritmética de viewport por jornada
 * (`viewport.ts`, `medicao/viewport.ts`).
 */

import type { SceneRevision } from "@croquito/contracts";

import { precisionLabel } from "./labels";

/** A entidade da cena e a precisão dela vêm do contrato gerado, nunca redeclaradas aqui. */
export type EntidadeDaCena = SceneRevision.Entity;
export type PrecisaoDaCena = SceneRevision.Precision;

/** Ponto no espaço do desenho: metros, Y já espelhado. */
export type PontoDoDesenho = {
  x: number;
  y: number;
};

/** Retângulo no espaço do desenho. */
export type CaixaDaCena = {
  left: number;
  top: number;
  right: number;
  bottom: number;
};

export type ViewBoxDaCena = {
  x: number;
  y: number;
  width: number;
  height: number;
};

/**
 * Forma desenhável. `precisao` viaja na forma porque é ela que decide o traço — e o traço,
 * não a cor, é o indicador primário da precisão (Design Approval Package, decisão 2).
 */
export type FormaDaCena =
  | {
      tipo: "caminho";
      entityId: string;
      precisao: PrecisaoDaCena;
      camada: string;
      pontos: PontoDoDesenho[];
      fechado: boolean;
    }
  | {
      tipo: "circulo";
      entityId: string;
      precisao: PrecisaoDaCena;
      camada: string;
      centro: PontoDoDesenho;
      raio: number;
    };

export type PrecisaoNoDesenho = {
  precisao: PrecisaoDaCena;
  /** Nome da precisão por extenso; a legenda não depende de cor nem de traço. */
  nome: string;
  /** Como a forma é traçada, dito em palavras — é o par escrito do estilo. */
  traco: string;
};

/**
 * As quatro precisões e o traço de cada uma. O texto é o que faz o critério 3 da F-019
 * valer: quem lê a legenda em preto e branco distingue as quatro.
 *
 * O nome vem de `precisionLabel`, que já é a fonte do vocabulário de precisão na tela;
 * repeti-lo aqui abriria a porta para a legenda do desenho e o resto da revisão chamarem a
 * mesma precisão por nomes diferentes.
 */
export const PRECISOES_NO_DESENHO: PrecisaoNoDesenho[] = [
  { precisao: "exact", nome: precisionLabel("exact"), traco: "traço grosso contínuo" },
  { precisao: "derived", nome: precisionLabel("derived"), traco: "traço fino contínuo" },
  { precisao: "approximate", nome: precisionLabel("approximate"), traco: "tracejado" },
  { precisao: "unresolved", nome: precisionLabel("unresolved"), traco: "pontilhado" },
];

/** Espelha o Y: é a ÚNICA passagem do espaço da cena para o espaço do desenho. */
export function pontoDoDesenho(ponto: { x: number; y: number }): PontoDoDesenho {
  return { x: ponto.x, y: -ponto.y };
}

/**
 * A forma desenhável de uma entidade, ou `null` quando não há geometria a traçar.
 *
 * Texto e cota **não** são desenhados: a cena os carrega para o DXF, e reproduzi-los aqui
 * faria o preview imitar a prancha — que é justamente o que ele não pode parecer.
 */
export function formaDaEntidade(entity: EntidadeDaCena): FormaDaCena | null {
  const entityId = entity.id ?? "";
  const camada = entity.layer;
  const precisao = entity.precision;
  const geometry = entity.geometry;
  if (geometry.type === "line") {
    return {
      tipo: "caminho",
      entityId,
      precisao,
      camada,
      pontos: [pontoDoDesenho(geometry.start), pontoDoDesenho(geometry.end)],
      fechado: false,
    };
  }
  if (geometry.type === "polyline") {
    return {
      tipo: "caminho",
      entityId,
      precisao,
      camada,
      pontos: geometry.points.map(pontoDoDesenho),
      fechado: geometry.closed ?? false,
    };
  }
  if (geometry.type === "spline") {
    // Traçada como polilinha pelos pontos de ajuste: o preview é leitura de trabalho, e
    // interpolar a curva aqui inventaria uma forma que o DXF resolve por outro caminho.
    return {
      tipo: "caminho",
      entityId,
      precisao,
      camada,
      pontos: geometry.fit_points.map(pontoDoDesenho),
      fechado: false,
    };
  }
  if (geometry.type === "circle") {
    return {
      tipo: "circulo",
      entityId,
      precisao,
      camada,
      centro: pontoDoDesenho(geometry.center),
      raio: geometry.radius,
    };
  }
  if (geometry.type === "arc") {
    return {
      tipo: "caminho",
      entityId,
      precisao,
      camada,
      pontos: pontosDoArco(geometry),
      fechado: false,
    };
  }
  return null;
}

/**
 * O arco vira polilinha de 24 segmentos. Ângulo da cena é em radianos e cresce no sentido
 * anti-horário com Y para cima; o espelhamento acontece em `pontoDoDesenho`, como em todo
 * o resto — o ângulo não é negado aqui, senão a inversão existiria em dois lugares.
 */
function pontosDoArco(geometry: {
  center: { x: number; y: number };
  radius: number;
  start_angle: number;
  end_angle: number;
}): PontoDoDesenho[] {
  const passos = 24;
  const varredura = geometry.end_angle - geometry.start_angle;
  const pontos: PontoDoDesenho[] = [];
  for (let indice = 0; indice <= passos; indice += 1) {
    const angulo = geometry.start_angle + (varredura * indice) / passos;
    pontos.push(
      pontoDoDesenho({
        x: geometry.center.x + geometry.radius * Math.cos(angulo),
        y: geometry.center.y + geometry.radius * Math.sin(angulo),
      }),
    );
  }
  return pontos;
}

/** Todas as formas desenháveis da cena, na ordem em que a cena as declara. */
export function formasDaCena(entities: EntidadeDaCena[]): FormaDaCena[] {
  return entities
    .map(formaDaEntidade)
    .filter((forma): forma is FormaDaCena => forma !== null);
}

/** Caixa que contém todas as formas, ou `null` quando não há o que desenhar. */
export function caixaDasFormas(formas: FormaDaCena[]): CaixaDaCena | null {
  let left = Number.POSITIVE_INFINITY;
  let top = Number.POSITIVE_INFINITY;
  let right = Number.NEGATIVE_INFINITY;
  let bottom = Number.NEGATIVE_INFINITY;
  for (const forma of formas) {
    const pontos =
      forma.tipo === "circulo"
        ? [
            { x: forma.centro.x - forma.raio, y: forma.centro.y - forma.raio },
            { x: forma.centro.x + forma.raio, y: forma.centro.y + forma.raio },
          ]
        : forma.pontos;
    for (const ponto of pontos) {
      left = Math.min(left, ponto.x);
      right = Math.max(right, ponto.x);
      top = Math.min(top, ponto.y);
      bottom = Math.max(bottom, ponto.y);
    }
  }
  if (!Number.isFinite(left) || !Number.isFinite(top)) {
    return null;
  }
  return { left, top, right, bottom };
}

/**
 * Enquadramento inicial: a caixa da cena com uma folga proporcional, nunca colada à borda.
 *
 * Cena degenerada — uma única linha horizontal, por exemplo — tem altura zero, e um
 * `viewBox` de altura zero não desenha nada. A folga mínima em metros é o que impede esse
 * caso de virar tela vazia sem explicação.
 */
export function enquadramentoInicial(caixa: CaixaDaCena): ViewBoxDaCena {
  const largura = Math.max(caixa.right - caixa.left, 0);
  const altura = Math.max(caixa.bottom - caixa.top, 0);
  const folga = Math.max(largura, altura) * 0.08;
  const folgaMinima = 0.5;
  const margem = Math.max(folga, folgaMinima);
  return {
    x: caixa.left - margem,
    y: caixa.top - margem,
    width: largura + margem * 2,
    height: altura + margem * 2,
  };
}

export const ZOOM_MAXIMO_DA_CENA = 12;
export const PASSO_DE_ZOOM_DA_CENA = 1.5;

/** Quantas vezes a view está aproximada em relação ao enquadramento inteiro. */
export function fatorDeZoomDaCena(view: ViewBoxDaCena, inteiro: ViewBoxDaCena): number {
  if (view.width <= 0) {
    return 1;
  }
  return inteiro.width / view.width;
}

/**
 * Aproxima ou afasta em torno de um ponto do desenho, preservando-o sob o cursor.
 * O teto existe para o traço não virar borrão; o piso é o enquadramento inteiro, porque
 * afastar além do desenho só produz vazio.
 */
export function aplicarZoomDaCena(
  view: ViewBoxDaCena,
  inteiro: ViewBoxDaCena,
  fator: number,
  foco: PontoDoDesenho,
): ViewBoxDaCena {
  const zoomAtual = fatorDeZoomDaCena(view, inteiro);
  const zoomAlvo = Math.min(Math.max(zoomAtual * fator, 1), ZOOM_MAXIMO_DA_CENA);
  const largura = inteiro.width / zoomAlvo;
  const altura = inteiro.height / zoomAlvo;
  const razaoX = view.width === 0 ? 0.5 : (foco.x - view.x) / view.width;
  const razaoY = view.height === 0 ? 0.5 : (foco.y - view.y) / view.height;
  return limitarViewDaCena(
    { x: foco.x - largura * razaoX, y: foco.y - altura * razaoY, width: largura, height: altura },
    inteiro,
  );
}

/** Arrasta a view em metros do desenho, sem deixá-la sair do enquadramento inteiro. */
export function arrastarViewDaCena(
  view: ViewBoxDaCena,
  inteiro: ViewBoxDaCena,
  dx: number,
  dy: number,
): ViewBoxDaCena {
  return limitarViewDaCena({ ...view, x: view.x + dx, y: view.y + dy }, inteiro);
}

/** A view nunca é maior que o enquadramento inteiro nem sai dele. */
export function limitarViewDaCena(
  view: ViewBoxDaCena,
  inteiro: ViewBoxDaCena,
): ViewBoxDaCena {
  const width = Math.min(view.width, inteiro.width);
  const height = Math.min(view.height, inteiro.height);
  const x = Math.min(Math.max(view.x, inteiro.x), inteiro.x + inteiro.width - width);
  const y = Math.min(Math.max(view.y, inteiro.y), inteiro.y + inteiro.height - height);
  return { x, y, width, height };
}

export function viewBoxDaCenaAttr(view: ViewBoxDaCena): string {
  return `${view.x} ${view.y} ${view.width} ${view.height}`;
}

/** Comprimentos "redondos" de barra de escala, em metros. */
const COMPRIMENTOS_DE_ESCALA = [
  0.1, 0.25, 0.5, 1, 2, 2.5, 5, 10, 20, 25, 50, 100, 200, 250, 500,
];

export type BarraDeEscala = {
  /** Comprimento da barra, em metros da cena. */
  metros: number;
  /** O rótulo escrito ao lado dela. */
  rotulo: string;
};

/**
 * A maior medida redonda que ocupa até um quarto da largura visível. Sem barra, um desenho
 * sem cota não diz se aquilo tem 3 ou 30 metros — e ela acompanha o zoom porque é derivada
 * da view, não do enquadramento inteiro.
 */
export function barraDeEscala(view: ViewBoxDaCena): BarraDeEscala {
  const alvo = view.width / 4;
  let escolhido = COMPRIMENTOS_DE_ESCALA[0];
  for (const candidato of COMPRIMENTOS_DE_ESCALA) {
    if (candidato <= alvo) {
      escolhido = candidato;
    }
  }
  return { metros: escolhido, rotulo: rotuloDeMetros(escolhido) };
}

function rotuloDeMetros(metros: number): string {
  const texto = Number.isInteger(metros)
    ? String(metros)
    : metros.toFixed(2).replace(/0$/, "");
  return `${texto.replace(".", ",")} m`;
}

export type ContagemPorPrecisao = {
  precisao: PrecisaoDaCena;
  nome: string;
  quantidade: number;
};

/** Quantas entidades em cada precisão; precisão sem entidade nenhuma não aparece. */
export function contagemPorPrecisao(entities: EntidadeDaCena[]): ContagemPorPrecisao[] {
  return PRECISOES_NO_DESENHO.map((item) => ({
    precisao: item.precisao,
    nome: item.nome,
    quantidade: entities.filter((entity) => entity.precision === item.precisao).length,
  })).filter((item) => item.quantidade > 0);
}

export type VaoAplicadoDesenhado = {
  readingId: string;
  eixo: "x" | "y";
  valorM: number;
  /** Extremos da cota no eixo dela, em metros do desenho. */
  de: number;
  ate: number;
  /** Onde a cota é desenhada no outro eixo: fora da caixa, para não cobrir a geometria. */
  offset: number;
  rotulo: string;
};

export type VaoAplicadoDoServidor = {
  reading_id: string;
  axis: "x" | "y";
  value_m: number;
  start_m: number;
  end_m: number;
};

/**
 * Vãos aplicados viram cota desenhada onde ancoraram — eles declaram `start_m`/`end_m`,
 * então há posição a respeitar.
 *
 * O eixo Y é espelhado como qualquer ponto da cena, e por isso `de`/`ate` saem invertidos
 * de propósito no eixo vertical: quem desenha só precisa do menor e do maior.
 */
export function vaosAplicadosDesenhados(
  vaos: VaoAplicadoDoServidor[],
  caixa: CaixaDaCena,
): VaoAplicadoDesenhado[] {
  const largura = caixa.right - caixa.left;
  const altura = caixa.bottom - caixa.top;
  const afastamento = Math.max(Math.max(largura, altura) * 0.05, 0.3);
  return vaos.map((vao) => {
    const de = vao.axis === "x" ? vao.start_m : -vao.end_m;
    const ate = vao.axis === "x" ? vao.end_m : -vao.start_m;
    return {
      readingId: vao.reading_id,
      eixo: vao.axis,
      valorM: vao.value_m,
      de: Math.min(de, ate),
      ate: Math.max(de, ate),
      offset: vao.axis === "x" ? caixa.bottom + afastamento : caixa.right + afastamento,
      rotulo: `${formatarMetros(vao.value_m)} m`,
    };
  });
}

export type VaoEmDisputaDesenhado = {
  eixo: "x" | "y";
  valoresM: number[];
  readingIds: string[];
  rotulo: string;
  /** Onde a faixa é desenhada no outro eixo. */
  offset: number;
};

export type VaoEmDisputaDoServidor = {
  axis: "x" | "y";
  values_m: number[];
  reading_ids: string[];
};

/**
 * Vão em disputa vira FAIXA do eixo, não cota posicionada.
 *
 * `ContestedSpanOut` declara eixo, valores e leituras — e **não** declara posição. Desenhar
 * a disputa num ponto exato inventaria o dado que falta; a faixa cobre o eixo inteiro e a
 * tela diz, por escrito, que a posição não é declarada pelo servidor (Design Approval
 * Package da F-019, decisão 4).
 */
export function vaosEmDisputaDesenhados(
  vaos: VaoEmDisputaDoServidor[],
  caixa: CaixaDaCena,
): VaoEmDisputaDesenhado[] {
  const largura = caixa.right - caixa.left;
  const altura = caixa.bottom - caixa.top;
  const afastamento = Math.max(Math.max(largura, altura) * 0.05, 0.3);
  return vaos.map((vao, indice) => ({
    eixo: vao.axis,
    valoresM: vao.values_m,
    readingIds: vao.reading_ids,
    rotulo: `eixo ${vao.axis.toUpperCase()} em disputa · ${vao.values_m
      .map((valor) => `${formatarMetros(valor)} m`)
      .join(" × ")}`,
    offset:
      vao.axis === "x"
        ? caixa.top - afastamento * (indice + 1)
        : caixa.left - afastamento * (indice + 1),
  }));
}

function formatarMetros(valor: number): string {
  return valor.toFixed(2).replace(".", ",");
}
