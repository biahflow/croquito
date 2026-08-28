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

/** Piso do raio do emblema, em pixels de tela: abaixo disto o número não se lê. */
const RAIO_MINIMO_DO_EMBLEMA = 10;

/** Fração da janela visível que o emblema ocupa quando a linha é alta o bastante. */
const FRACAO_DA_JANELA = 1 / 45;

/**
 * Raio do emblema de um item: fração da JANELA, e não da página — senão aproximar 8×
 * deixaria o emblema do tamanho de um item inteiro —, mas nunca maior que meia altura da
 * linha que ele marca.
 *
 * O teto pela altura é o que impede emblemas de linhas vizinhas de se cobrirem: numa
 * legenda densa o passo entre linhas é menor que o diâmetro que a janela pediria, e seis
 * itens viravam uma coluna de círculos empilhados em que não se lê número nenhum. O piso
 * de {@link RAIO_MINIMO_DO_EMBLEMA} vence o teto quando a linha é fininha: emblema
 * ilegível é pior que emblema que encosta no vizinho.
 */
export function raioDoEmblema(view: ViewBox, caixa: Caixa): number {
  const altura = Math.max(caixa.bottom - caixa.top, 1);
  return Math.max(Math.min(view.width * FRACAO_DA_JANELA, altura / 2), RAIO_MINIMO_DO_EMBLEMA);
}

/** Centro e raio do emblema numerado de um item, em pixels da imagem fonte. */
export type Emblema = { cx: number; cy: number; r: number };

/**
 * Múltiplo do RAIO entre o centro do emblema e a borda do bbox que ele marca.
 *
 * Meio diâmetro apenas encosta: 1,6 dá o respiro que separa o emblema da borda sem o
 * jogar longe da linha que ele identifica.
 *
 * Este número já foi 4,5 por um motivo que não era dele. Na prancha real o emblema caía
 * sobre o rótulo, e afastá-lo mais parecia o conserto — mas a causa era o bbox: a
 * extração entregava uma faixa X deslocada para dentro da tabela, e o "fora do bbox"
 * ficava em cima do texto justamente porque o bbox não era o da linha. Quem conserta isso
 * é `register_legend_bboxes`, que agora mede as bordas da tabela na tinta das réguas.
 * Afastamento de tela não compensa âncora errada — só espalha o erro.
 */
const AFASTAMENTO_DO_EMBLEMA = 1.6;

/** Mantém `valor` dentro de `[min, max]`; faixa degenerada (emblema maior que a página)
 * cai no meio dela, em vez de produzir um valor fora dos dois lados. */
function prenderEntre(valor: number, min: number, max: number): number {
  if (min > max) {
    return (min + max) / 2;
  }
  return Math.min(max, Math.max(min, valor));
}

/** Distância do centro do emblema ao ponto mais próximo do retângulo, ao quadrado, contra
 * o raio ao quadrado: verdadeiro só quando emblema e retângulo realmente se sobrepõem
 * (encostar na borda não conta). */
function emblemaSobrepoe(
  emblema: Emblema,
  x: number,
  y: number,
  largura: number,
  altura: number,
): boolean {
  const proximoX = Math.max(x, Math.min(emblema.cx, x + largura));
  const proximoY = Math.max(y, Math.min(emblema.cy, y + altura));
  const dx = emblema.cx - proximoX;
  const dy = emblema.cy - proximoY;
  return dx * dx + dy * dy < emblema.r * emblema.r;
}

/**
 * Centro e raio do emblema numerado de um item, sempre **fora** do próprio bbox — nunca
 * sobre a linha da legenda que ele marca. O defeito que originou a regra foi visto na
 * prancha real da medição: o número desenhado dentro da caixa cobria letras de
 * "PISO EM(1)CONCRETO", e quem conferia quantidade contra desenho perdia justamente o
 * texto que precisava ler.
 *
 * Tenta a borda esquerda primeiro, com o centro a `AFASTAMENTO_DO_EMBLEMA` raios de
 * `caixa.left` e centralizado na altura da linha; quando o item está encostado na borda
 * esquerda da página e não sobra espaço, cai para acima do canto superior-esquerdo.
 * Direita e abaixo entram como terceira e quarta tentativa, só para o canto raro em que o
 * item encosta nas bordas esquerda E superior ao mesmo tempo; se nenhuma das quatro
 * direções couber, vence a segunda (acima), que é o fallback pedido.
 *
 * Porte da mesma intenção de `pinPlacement` (`apps/web/src/medicao/viewport.ts`), e não
 * import: as duas jornadas não compartilham módulo de apresentação, e lá a função fala em
 * `PlateBox`/`SvgRect` e diâmetro fixo, enquanto aqui ela fala em `Caixa`, `Pagina` e um
 * raio que o chamador calcula a partir do zoom corrente.
 *
 * Caixa degenerada (largura ou altura zero, que o pacote admite quando a extração marcou
 * um ponto) recebe lado mínimo, como em `enquadrarCaixa`, em vez de virar divisão por
 * zero. Tudo é clampado para dentro da página.
 */
export function emblemaDaCaixa(caixa: Caixa, raio: number, pagina: Pagina): Emblema {
  const r = Number.isFinite(raio) && raio > 0 ? raio : 1;
  const largura = Math.max(caixa.right - caixa.left, 1);
  const altura = Math.max(caixa.bottom - caixa.top, 1);
  const afastamento = AFASTAMENTO_DO_EMBLEMA * r;
  const minX = r;
  const maxX = pagina.width - r;
  const minY = r;
  const maxY = pagina.height - r;
  const centroX = prenderEntre(caixa.left + largura / 2, minX, maxX);
  const centroY = prenderEntre(caixa.top + altura / 2, minY, maxY);

  const candidatos: Emblema[] = [
    { cx: prenderEntre(caixa.left - afastamento, minX, maxX), cy: centroY, r }, // esquerda (pedido)
    { cx: centroX, cy: prenderEntre(caixa.top - afastamento, minY, maxY), r }, // acima (fallback)
    { cx: prenderEntre(caixa.left + largura + afastamento, minX, maxX), cy: centroY, r }, // direita
    { cx: centroX, cy: prenderEntre(caixa.top + altura + afastamento, minY, maxY), r }, // abaixo
  ];

  const cabe = candidatos.find(
    (candidato) => !emblemaSobrepoe(candidato, caixa.left, caixa.top, largura, altura),
  );
  return cabe ?? candidatos[1];
}
