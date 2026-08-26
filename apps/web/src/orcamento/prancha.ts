/**
 * Aritmética pura do zoom e do enquadramento da prancha, no orçamento-base.
 *
 * A prancha do projetista é lida numa tela, e a legenda é lida por quem vai conferir
 * quantidade contra desenho. Sem aproximar, `418,12 m²` é um número que a pessoa aceita
 * ou recusa no escuro: a âncora existe, está publicada no pacote (`evidence.bbox`), e não
 * adianta nada desenhada em 1.200 px de largura sobre uma prancha A1.
 *
 * O zoom é feito pelo `viewBox` do SVG, e não por `transform: scale` no contêiner. Não é
 * preferência de estilo: as âncoras são desenhadas no MESMO espaço de coordenadas da
 * imagem (`coordinate_space: "source_image_pixels"`), então mover o `viewBox` move
 * desenho e âncora juntos, por construção. Com `scale` no contêiner, imagem e marcações
 * seriam duas transformações independentes que precisam concordar — e o dia em que
 * discordassem, a tela mostraria a âncora ao lado do item errado com toda a autoridade de
 * um desenho.
 *
 * Todas as funções deste módulo são puras e trabalham em PIXELS DA IMAGEM FONTE, a mesma
 * unidade do pacote. Nada aqui sabe de evento de mouse, de React ou de CSS.
 */

/** Retângulo em pixels da imagem fonte, como o pacote grava. */
export type Caixa = {
  left: number;
  top: number;
  right: number;
  bottom: number;
};

/** Janela visível do SVG, em pixels da imagem fonte. */
export type ViewBox = {
  x: number;
  y: number;
  width: number;
  height: number;
};

/** Dimensões naturais da página promovida. */
export type Pagina = {
  width: number;
  height: number;
};

/**
 * Teto de aproximação. Oito vezes leva uma prancha A1 de 200 DPI a um zoom em que a cota
 * escrita é legível; acima disso o que se vê é o pixel do render, não o desenho.
 */
export const ZOOM_MAXIMO = 8;

/** Passo de um clique nos botões de aproximar/afastar. */
export const PASSO_ZOOM = 1.5;

/** Folga ao redor da âncora quando a tela enquadra um item, em fração da caixa. */
const MARGEM_ENQUADRAMENTO = 1.6;

/** A página inteira: é o estado inicial e o alvo do botão "ver a prancha inteira". */
export function paginaInteira(pagina: Pagina): ViewBox {
  return { x: 0, y: 0, width: pagina.width, height: pagina.height };
}

/** Quantas vezes a janela atual aproxima em relação à página inteira. */
export function fatorDeZoom(view: ViewBox, pagina: Pagina): number {
  if (view.width <= 0) {
    return 1;
  }
  return pagina.width / view.width;
}

/**
 * Mantém a janela dentro da página e dentro do teto de zoom.
 *
 * Prender a janela à página é o que impede a prancha de "escapar" para fora da tela num
 * arrasto longo, estado do qual quem está revisando só sai por tentativa e erro.
 */
export function limitarView(view: ViewBox, pagina: Pagina): ViewBox {
  const larguraMinima = pagina.width / ZOOM_MAXIMO;
  const alturaMinima = pagina.height / ZOOM_MAXIMO;
  const width = Math.min(pagina.width, Math.max(larguraMinima, view.width));
  // A altura acompanha a largura para a janela nunca deformar a prancha: proporção
  // diferente da página faria o SVG encaixar com barras e o clique cair fora do lugar.
  const height = Math.min(pagina.height, Math.max(alturaMinima, (width * pagina.height) / pagina.width));
  const x = Math.min(Math.max(0, view.x), Math.max(0, pagina.width - width));
  const y = Math.min(Math.max(0, view.y), Math.max(0, pagina.height - height));
  return { x, y, width, height };
}

/**
 * Aproxima ou afasta mantendo fixo o ponto `foco` (em pixels da imagem).
 *
 * O foco é o que faz o zoom parecer natural: aproximar sempre pelo centro obriga quem
 * revisa a arrastar de volta para o item que estava olhando, a cada clique.
 */
export function aplicarZoom(
  view: ViewBox,
  pagina: Pagina,
  fator: number,
  foco?: { x: number; y: number },
): ViewBox {
  if (fator <= 0) {
    return view;
  }
  const alvo = foco ?? { x: view.x + view.width / 2, y: view.y + view.height / 2 };
  const width = view.width / fator;
  const height = view.height / fator;
  // Fração do foco dentro da janela atual: preservá-la é o que mantém o ponto parado.
  const fracaoX = view.width === 0 ? 0.5 : (alvo.x - view.x) / view.width;
  const fracaoY = view.height === 0 ? 0.5 : (alvo.y - view.y) / view.height;
  return limitarView(
    { x: alvo.x - width * fracaoX, y: alvo.y - height * fracaoY, width, height },
    pagina,
  );
}

/** Desloca a janela. `dx`/`dy` vêm em pixels da imagem, já convertidos pelo chamador. */
export function arrastarView(view: ViewBox, pagina: Pagina, dx: number, dy: number): ViewBox {
  return limitarView({ ...view, x: view.x + dx, y: view.y + dy }, pagina);
}

/**
 * Enquadra uma âncora com folga, sem nunca aproximar além do teto.
 *
 * É o que a seleção cruzada usa: escolher o item na lista leva o desenho até ele. Caixa
 * degenerada (largura ou altura zero, que o pacote admite quando a extração marcou um
 * ponto) recebe uma janela mínima em vez de virar divisão por zero.
 */
export function enquadrarCaixa(caixa: Caixa, pagina: Pagina): ViewBox {
  const largura = Math.max(caixa.right - caixa.left, 1);
  const altura = Math.max(caixa.bottom - caixa.top, 1);
  const centroX = caixa.left + largura / 2;
  const centroY = caixa.top + altura / 2;
  const desejada = Math.max(largura, (altura * pagina.width) / pagina.height) * MARGEM_ENQUADRAMENTO;
  const width = Math.min(pagina.width, Math.max(pagina.width / ZOOM_MAXIMO, desejada));
  const height = (width * pagina.height) / pagina.width;
  return limitarView({ x: centroX - width / 2, y: centroY - height / 2, width, height }, pagina);
}

/**
 * A âncora está dentro da janela visível?
 *
 * Serve para a tela decidir se precisa mover o desenho ao selecionar um item: reenquadrar
 * uma âncora que já está à vista tira do lugar o que a pessoa estava olhando.
 */
export function caixaVisivel(caixa: Caixa, view: ViewBox): boolean {
  return (
    caixa.left >= view.x &&
    caixa.top >= view.y &&
    caixa.right <= view.x + view.width &&
    caixa.bottom <= view.y + view.height
  );
}

/**
 * Converte um ponto do elemento renderizado (fração 0..1 da largura/altura exibida) para
 * pixels da imagem, dentro da janela atual. É o que traduz roda do mouse e arrasto.
 */
export function pontoDaImagem(
  view: ViewBox,
  fracaoX: number,
  fracaoY: number,
): { x: number; y: number } {
  return { x: view.x + view.width * fracaoX, y: view.y + view.height * fracaoY };
}

/** `viewBox` como o atributo do SVG o espera. */
export function viewBoxAttr(view: ViewBox): string {
  return `${view.x} ${view.y} ${view.width} ${view.height}`;
}
