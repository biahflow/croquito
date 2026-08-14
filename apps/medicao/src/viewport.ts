/**
 * Geometria de apresentação da prancha na revisão do takeoff.
 *
 * Versão enxuta do padrão de `apps/web/src/viewport.ts`: imagem e overlay SVG usam o
 * **mesmo** transform, senão o retângulo desenhado deixa de cair sobre a linha da legenda
 * que ele diz marcar — e um bbox fora de registro é uma afirmação falsa sobre onde o
 * número foi lido. Nada aqui é dado de domínio: são estilos CSS e coordenadas de pixel da
 * imagem, nenhum deles enviado ao servidor.
 *
 * A prancha da legenda é retrato e não gira; por isso este módulo não tem rotação — o
 * viewer do croqui tem, porque lá a folha vem em paisagem.
 */

import type { CSSProperties } from "react";
import type { PlateBox } from "./api";

/** A prancha tem ~1700 px de largura; abaixo de 1× o texto da legenda some. */
export const MIN_ZOOM = 1;
export const MAX_ZOOM = 6;
export const ZOOM_STEP = 0.25;

export function clampZoom(zoom: number): number {
  if (!Number.isFinite(zoom)) {
    return MIN_ZOOM;
  }
  return Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, zoom));
}

/** Roda para cima (delta negativo) aproxima; o passo é o mesmo dos botões. */
export function zoomAfterWheel(zoom: number, deltaY: number): number {
  if (!Number.isFinite(deltaY) || deltaY === 0) {
    return clampZoom(zoom);
  }
  return clampZoom(zoom + (deltaY < 0 ? ZOOM_STEP : -ZOOM_STEP));
}

/** Lado sempre positivo: imagem ou bbox degenerada não pode virar divisão por zero. */
function side(value: number): number {
  return Number.isFinite(value) && value > 0 ? value : 1;
}

/**
 * Estilo do palco. O zoom cresce o palco em vez de escalar o conteúdo: conteúdo
 * transformado que ultrapassa a borda esquerda não entra na área rolável, e o canto da
 * prancha ficaria inalcançável justamente no zoom alto.
 */
export function stageStyle(
  zoom: number,
  imageWidthPx: number,
  imageHeightPx: number,
): CSSProperties {
  return {
    width: `${clampZoom(zoom) * 100}%`,
    aspectRatio: `${side(imageWidthPx)} / ${side(imageHeightPx)}`,
  };
}

export type PanOrigin = {
  pointerX: number;
  pointerY: number;
  scrollLeft: number;
  scrollTop: number;
};

/** Arrastar move o conteúdo junto com o ponteiro, então o scroll anda ao contrário. */
export function panScrollOffset(
  origin: PanOrigin,
  pointerX: number,
  pointerY: number,
): { scrollLeft: number; scrollTop: number } {
  return {
    scrollLeft: origin.scrollLeft - (pointerX - origin.pointerX),
    scrollTop: origin.scrollTop - (pointerY - origin.pointerY),
  };
}

export type SvgRect = { x: number; y: number; width: number; height: number };

/**
 * Retângulo SVG da bbox do item, nas coordenadas da imagem (o `viewBox` é a imagem
 * inteira). Lado nunca é zero: um retângulo sem área não seria clicável nem visível.
 */
export function bboxRect(bbox: PlateBox): SvgRect {
  const x = Math.min(bbox.left, bbox.right);
  const y = Math.min(bbox.top, bbox.bottom);
  return {
    x,
    y,
    width: side(Math.abs(bbox.right - bbox.left)),
    height: side(Math.abs(bbox.bottom - bbox.top)),
  };
}

/** Diâmetro padrão do pino numerado, em pixels de imagem. */
export const PIN_DIAMETER_PX = 36;

/** Múltiplo do diâmetro entre o centro do pino e a borda esquerda do bbox. */
const PIN_LEFT_OFFSET_RATIO = 0.8;

export type PinCircle = { cx: number; cy: number; r: number };

/** Mantém `value` dentro de `[min, max]`; quando a faixa é degenerada (pino maior que a
 * imagem), cai no meio dela em vez de produzir um valor fora dos dois lados. */
function clampInto(value: number, min: number, max: number): number {
  if (min > max) {
    return (min + max) / 2;
  }
  return Math.min(max, Math.max(min, value));
}

/** Distância do centro do círculo ao ponto mais próximo do retângulo, ao quadrado, contra
 * o raio ao quadrado: verdadeiro só quando círculo e retângulo realmente se sobrepõem
 * (encostar na borda não conta). */
function circleOverlapsRect(pin: PinCircle, rect: SvgRect): boolean {
  const closestX = Math.max(rect.x, Math.min(pin.cx, rect.x + rect.width));
  const closestY = Math.max(rect.y, Math.min(pin.cy, rect.y + rect.height));
  const dx = pin.cx - closestX;
  const dy = pin.cy - closestY;
  return dx * dx + dy * dy < pin.r * pin.r;
}

/**
 * Centro e raio do pino numerado de um item, sempre **fora** do próprio bbox — nunca
 * sobre o texto da linha da legenda que ele marca (o defeito visto na prancha real: o
 * círculo cobrindo letras de "PISO EM(1)CONCRETO"). Tenta a borda esquerda primeiro,
 * com o centro a `PIN_LEFT_OFFSET_RATIO` diâmetros de `bbox.left` e centralizado na
 * altura da linha; quando o bbox está encostado na borda esquerda da imagem e não sobra
 * espaço para o pino sem tocá-lo, cai para acima do canto superior-esquerdo. Sempre
 * clampado para dentro da imagem.
 *
 * Direita e abaixo do bbox entram como terceira e quarta tentativa, só para o canto raro
 * em que o item está encostado nas bordas esquerda E superior ao mesmo tempo (nem
 * esquerda nem acima sobram espaço) — a prancha real tem milhares de pixels e um item
 * assim não deveria existir, mas a função não devolve um pino sobreposto por causa
 * disso; se nenhuma das quatro direções sobrar, a mais próxima do pedido (acima) vence.
 *
 * Mesma intenção de posicionamento do `balloon_layout` do overlay do servidor
 * (`services/worker/src/croquitodxf_worker/valuation/takeoff_overlay.py`) —
 * reimplementada aqui, sem importar nada de lá: aquele módulo desenha PNG em Python no
 * worker, este é geometria pura de apresentação em TypeScript no navegador.
 */
export function pinPlacement(
  bbox: PlateBox,
  diameter: number,
  imageWidthPx: number,
  imageHeightPx: number,
): PinCircle {
  const rect = bboxRect(bbox);
  const r = side(diameter) / 2;
  const offset = PIN_LEFT_OFFSET_RATIO * side(diameter);
  const centerX = clampInto(rect.x + rect.width / 2, r, imageWidthPx - r);
  const centerY = clampInto(rect.y + rect.height / 2, r, imageHeightPx - r);
  const minX = r;
  const maxX = imageWidthPx - r;
  const minY = r;
  const maxY = imageHeightPx - r;

  const candidates: PinCircle[] = [
    { cx: clampInto(rect.x - offset, minX, maxX), cy: centerY, r }, // esquerda (pedido)
    { cx: centerX, cy: clampInto(rect.y - offset, minY, maxY), r }, // acima (fallback pedido)
    { cx: clampInto(rect.x + rect.width + offset, minX, maxX), cy: centerY, r }, // direita
    { cx: centerX, cy: clampInto(rect.y + rect.height + offset, minY, maxY), r }, // abaixo
  ];

  const fitting = candidates.find((candidate) => !circleOverlapsRect(candidate, rect));
  return fitting ?? candidates[1];
}
