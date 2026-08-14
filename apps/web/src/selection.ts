import type { VisionProposal } from "./api";
import { normalizeRotation } from "./viewport";

/**
 * Seleção por retângulo (Shift+arrasto) no viewer da revisão.
 *
 * Com dezenas de formas detectadas, marcar uma a uma é o gargalo do aceite em lote.
 * Este módulo é puro de propósito: toda a matemática — inversão da rotação do palco e
 * os predicados de toque — precisa ser testável sem DOM, como `viewport.ts`. Nada aqui
 * é geometria de domínio: são pixels da imagem de preview usados para escolher quais
 * propostas entram na seleção. Nenhum valor destas funções é enviado à API.
 */

export type ImagePoint = { x: number; y: number };

export type ImageRect = {
  left: number;
  top: number;
  right: number;
  bottom: number;
};

/** Recorte do `getBoundingClientRect()` que interessa à inversão. */
export type ClientBox = {
  left: number;
  top: number;
  width: number;
  height: number;
};

/**
 * Abaixo disso o gesto é clique, não arrasto: Shift+clique parado continua caindo no
 * `onClick` da forma, que marca e desmarca uma a uma.
 */
export const MARQUEE_MIN_DRAG_CLIENT_PX = 4;

export function normalizedRect(a: ImagePoint, b: ImagePoint): ImageRect {
  return {
    left: Math.min(a.x, b.x),
    top: Math.min(a.y, b.y),
    right: Math.max(a.x, b.x),
    bottom: Math.max(a.y, b.y),
  };
}

/** Distância de Chebyshev: arrastar 4 px em um dos eixos já é retângulo. */
export function isMarqueeDrag(
  originClientX: number,
  originClientY: number,
  clientX: number,
  clientY: number,
): boolean {
  return (
    Math.max(
      Math.abs(clientX - originClientX),
      Math.abs(clientY - originClientY),
    ) >= MARQUEE_MIN_DRAG_CLIENT_PX
  );
}

function clampUnit(value: number): number {
  if (!Number.isFinite(value)) {
    return 0;
  }
  return Math.min(1, Math.max(0, value));
}

/** Lado sempre positivo, no mesmo espírito de `viewport.ts`. */
function side(value: number): number {
  return Number.isFinite(value) && value > 0 ? value : 1;
}

/**
 * Ponto do viewport em pixels da imagem.
 *
 * `box` é o `getBoundingClientRect()` do `.preview-transform` NO MOMENTO do evento: em
 * quartos de volta a AABB devolvida é a caixa girada exata, e por serem coordenadas de
 * viewport ela já embute zoom e scroll — o palco cresce com o zoom, então nada além da
 * caixa entra na conta.
 *
 * Com `u` e `v` normalizados na caixa girada, a inversão de cada quarto de volta sai da
 * matriz de rotação do CSS (`rotate` positivo é horário porque y cresce para baixo):
 *
 * | rotação | x | y |
 * |---|---|---|
 * | 0 | u·W | v·H |
 * | 90 | v·W | (1−u)·H |
 * | 180 | (1−u)·W | (1−v)·H |
 * | 270 | (1−v)·W | u·H |
 */
export function clientToImagePoint(
  clientX: number,
  clientY: number,
  box: ClientBox,
  rotation: number,
  imageWidthPx: number,
  imageHeightPx: number,
): ImagePoint {
  if (
    !Number.isFinite(box.width) ||
    !Number.isFinite(box.height) ||
    box.width <= 0 ||
    box.height <= 0
  ) {
    // Caixa degenerada: o elemento ainda não foi medido. Devolver a origem é melhor do
    // que devolver NaN, que contaminaria o retângulo inteiro.
    return { x: 0, y: 0 };
  }
  const width = side(imageWidthPx);
  const height = side(imageHeightPx);
  const u = clampUnit((clientX - box.left) / box.width);
  const v = clampUnit((clientY - box.top) / box.height);
  switch (normalizeRotation(rotation)) {
    case 90:
      return { x: v * width, y: (1 - u) * height };
    case 180:
      return { x: (1 - u) * width, y: (1 - v) * height };
    case 270:
      return { x: (1 - v) * width, y: u * height };
    default:
      return { x: u * width, y: v * height };
  }
}

/**
 * Segmento × retângulo por Liang-Barsky: verdadeiro quando qualquer parte do segmento
 * cai dentro do retângulo, inclusive quando ele só encosta ou está inteiramente contido.
 * Segmento degenerado (extremos iguais) vira teste de ponto dentro do retângulo.
 */
function segmentHitsRect(a: ImagePoint, b: ImagePoint, rect: ImageRect): boolean {
  const dx = b.x - a.x;
  const dy = b.y - a.y;
  const edges: [number, number][] = [
    [-dx, a.x - rect.left],
    [dx, rect.right - a.x],
    [-dy, a.y - rect.top],
    [dy, rect.bottom - a.y],
  ];
  let enter = 0;
  let exit = 1;
  for (const [p, q] of edges) {
    if (p === 0) {
      // Paralelo à aresta: só sobrevive quem já está do lado de dentro dela.
      if (q < 0) {
        return false;
      }
      continue;
    }
    const t = q / p;
    if (p < 0) {
      enter = Math.max(enter, t);
    } else {
      exit = Math.min(exit, t);
    }
    if (enter > exit) {
      return false;
    }
  }
  return true;
}

function pointInRect(point: ImagePoint, rect: ImageRect): boolean {
  return (
    point.x >= rect.left &&
    point.x <= rect.right &&
    point.y >= rect.top &&
    point.y <= rect.bottom
  );
}

/** Distância do centro ao ponto mais próximo do retângulo; zero quando está dentro. */
function minDistanceToRect(center: ImagePoint, rect: ImageRect): number {
  const dx = Math.max(rect.left - center.x, 0, center.x - rect.right);
  const dy = Math.max(rect.top - center.y, 0, center.y - rect.bottom);
  return Math.hypot(dx, dy);
}

/** Distância do centro ao canto mais distante do retângulo. */
function maxDistanceToRect(center: ImagePoint, rect: ImageRect): number {
  const dx = Math.max(Math.abs(center.x - rect.left), Math.abs(center.x - rect.right));
  const dy = Math.max(Math.abs(center.y - rect.top), Math.abs(center.y - rect.bottom));
  return Math.hypot(dx, dy);
}

/**
 * Toque entre o retângulo e a geometria real da proposta, não a bbox dela.
 *
 * O critério é CROSSING: encostar basta. O viés é deliberado — no CAD, selecionar de
 * mais custa um clique para desmarcar, selecionar de menos obriga o revisor a desenhar
 * um retângulo gigante e conferir forma por forma.
 *
 * O círculo é testado como ANEL, porque o traço é o desenho e o preenchimento é `none`:
 * um retângulo inteiramente dentro do círculo, sem tocar a linha, não seleciona nada.
 */
export function rectHitsGeometry(
  rect: ImageRect,
  geometry: VisionProposal["geometry"],
): boolean {
  if (geometry.type === "line") {
    return segmentHitsRect(geometry.start, geometry.end, rect);
  }
  if (geometry.type === "circle") {
    const radius = Math.abs(geometry.radius);
    return (
      minDistanceToRect(geometry.center, rect) <= radius &&
      radius <= maxDistanceToRect(geometry.center, rect)
    );
  }
  const points = geometry.points;
  if (points.length === 0) {
    return false;
  }
  if (points.length === 1) {
    return pointInRect(points[0], rect);
  }
  for (let index = 0; index + 1 < points.length; index += 1) {
    if (segmentHitsRect(points[index], points[index + 1], rect)) {
      return true;
    }
  }
  // Contorno aberto — muro, limite de lote — não ganha o segmento de fechamento.
  return (
    geometry.closed &&
    segmentHitsRect(points[points.length - 1], points[0], rect)
  );
}

/**
 * Ids que o retângulo adiciona à seleção, na ordem da lista de propostas.
 *
 * Proposta com decisão registrada fica de fora: decisão é imutável e a seleção em lote
 * só existe para o que ainda está pendente.
 */
export function marqueeSelection(
  rect: ImageRect,
  proposals: VisionProposal[],
  decidedProposalIds: ReadonlySet<string>,
): string[] {
  return proposals
    .filter(
      (proposal) =>
        !decidedProposalIds.has(proposal.id) &&
        rectHitsGeometry(rect, proposal.geometry),
    )
    .map((proposal) => proposal.id);
}
