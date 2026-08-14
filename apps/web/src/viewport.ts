import type { CSSProperties } from "react";

/**
 * Geometria de apresentação do viewer de revisão.
 *
 * O croqui é desenhado em paisagem numa página retrato e as anotações da folha estão
 * giradas entre si, então o revisor precisa girar o desenho e ampliar a cota. Nada aqui
 * é geometria de domínio: são estilos CSS derivados de pixels da imagem de preview.
 * Nenhum valor destas funções é enviado à API, gravado no manifesto ou usado pelo solver.
 */

/** A folha tem ~4875 px de largura; 2× era pouco para ler uma cota escrita à mão. */
export const MIN_ZOOM = 1;
export const MAX_ZOOM = 4;
export const ZOOM_STEP = 0.1;

/** Tecla do atalho de rotação, também publicada em `aria-keyshortcuts`. */
export const ROTATION_SHORTCUT_KEY = "R";

export type PixelBox = {
  left: number;
  top: number;
  right: number;
  bottom: number;
};

/** O viewer só oferece quartos de volta; qualquer outro valor é normalizado. */
export function normalizeRotation(degrees: number): number {
  if (!Number.isFinite(degrees)) {
    return 0;
  }
  const quarter = Math.round(degrees / 90) * 90;
  return ((quarter % 360) + 360) % 360;
}

export function isQuarterTurned(rotation: number): boolean {
  return normalizeRotation(rotation) % 180 !== 0;
}

export function clampZoom(zoom: number): number {
  if (!Number.isFinite(zoom)) {
    return MIN_ZOOM;
  }
  return Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, zoom));
}

/** Lado sempre positivo: imagem ou bbox degenerada não pode virar divisão por zero. */
function side(value: number): number {
  return Number.isFinite(value) && value > 0 ? value : 1;
}

/**
 * Proporção da caixa que o desenho ocupa depois de girado: um quarto de volta troca
 * largura por altura.
 */
export function stageAspect(
  imageWidthPx: number,
  imageHeightPx: number,
  rotation: number,
): string {
  const width = side(imageWidthPx);
  const height = side(imageHeightPx);
  return isQuarterTurned(rotation)
    ? `${height} / ${width}`
    : `${width} / ${height}`;
}

/**
 * Estilo do palco. O zoom cresce o palco em vez de escalar só o conteúdo: conteúdo
 * transformado que ultrapassa as bordas superior e esquerda não entra na área rolável,
 * então `scale()` num elemento centralizado tornaria o canto superior esquerdo da folha
 * inalcançável justamente no zoom alto. Crescendo o palco, todo o desenho continua
 * acessível por scroll, teclado ou arrasto.
 */
export function stageStyle(
  zoom: number,
  rotation: number,
  imageWidthPx: number,
  imageHeightPx: number,
): CSSProperties {
  return {
    width: `${clampZoom(zoom) * 100}%`,
    aspectRatio: stageAspect(imageWidthPx, imageHeightPx, rotation),
  };
}

/**
 * Estilo do elemento que carrega imagem e overlays juntos. Ele gira em torno do próprio
 * centro, o que preserva o registro entre a tinta e os overlays em qualquer rotação.
 */
export function previewTransform(
  rotation: number,
  imageWidthPx: number,
  imageHeightPx: number,
): CSSProperties {
  const width = side(imageWidthPx);
  const height = side(imageHeightPx);
  const turn = normalizeRotation(rotation);
  return {
    // Girado um quarto de volta, a largura visível passa a ser a altura da imagem:
    // o elemento precisa crescer na proporção para preencher o palco já girado.
    width: isQuarterTurned(turn) ? `${(width / height) * 100}%` : "100%",
    transform: `translate(-50%, -50%) rotate(${turn}deg)`,
  };
}

export type EvidenceCropStyle = {
  /** Janela do recorte, com a proporção da bbox já girada. */
  crop: CSSProperties;
  /** Caixa da bbox sem girar, que gira em torno do próprio centro. */
  pivot: CSSProperties;
  /** Imagem inteira deslocada para que a bbox caia exatamente sobre a janela. */
  image: CSSProperties;
};

/**
 * Recorte ampliado da leitura selecionada.
 *
 * O pivô tem a proporção da bbox (`aspect-ratio: bw / bh`), então sua altura é
 * `larguraDoPivô * bh / bw`. É por isso que os denominadores mudam por eixo:
 *
 * - `width` e `left` são percentuais de posicionamento horizontal e resolvem contra a
 *   LARGURA do pivô, então o denominador é a largura da bbox (`bw`);
 * - `height` e `top` resolvem contra a ALTURA do bloco contêiner (CSS 2.1 §9.3.2 e
 *   §10.5), então o denominador é a altura da bbox (`bh`).
 *
 * Nos dois eixos o resultado é o mesmo fator `larguraDoPivô / bw` px por pixel de imagem.
 * Usar `bw` no `top` — o erro intuitivo, porque percentuais de `margin`/`padding` são
 * relativos à largura — deslocaria o recorte de cotas escritas na vertical, onde a bbox é
 * muito mais alta do que larga. `viewport.test.ts` resolve os percentuais como o CSS faz
 * e prova a coincidência com uma bbox 100 × 800.
 */
export function evidenceCropStyle(
  bbox: PixelBox,
  imageWidthPx: number,
  imageHeightPx: number,
  rotation: number,
): EvidenceCropStyle {
  const boxWidth = side(bbox.right - bbox.left);
  const boxHeight = side(bbox.bottom - bbox.top);
  const imageWidth = side(imageWidthPx);
  const imageHeight = side(imageHeightPx);
  const turned = isQuarterTurned(rotation);
  return {
    crop: {
      aspectRatio: turned
        ? `${boxHeight} / ${boxWidth}`
        : `${boxWidth} / ${boxHeight}`,
    },
    pivot: {
      width: turned ? `${(boxWidth / boxHeight) * 100}%` : "100%",
      aspectRatio: `${boxWidth} / ${boxHeight}`,
      transform: `translate(-50%, -50%) rotate(${normalizeRotation(rotation)}deg)`,
    },
    image: {
      width: `${(imageWidth / boxWidth) * 100}%`,
      height: `${(imageHeight / boxHeight) * 100}%`,
      left: `${(-bbox.left / boxWidth) * 100}%`,
      top: `${(-bbox.top / boxHeight) * 100}%`,
    },
  };
}

export type RotationShortcutEvent = {
  key: string;
  shiftKey?: boolean;
  ctrlKey?: boolean;
  metaKey?: boolean;
  altKey?: boolean;
  /** `true` quando o foco está num campo editável: a tecla pertence ao campo. */
  typingInField?: boolean;
};

/** Quanto girar por causa de uma tecla, ou `null` quando a tecla não é o atalho. */
export function rotationShortcutDelta(
  event: RotationShortcutEvent,
): number | null {
  if (event.ctrlKey || event.metaKey || event.altKey || event.typingInField) {
    return null;
  }
  if (event.key.toUpperCase() !== ROTATION_SHORTCUT_KEY) {
    return null;
  }
  return event.shiftKey ? -90 : 90;
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
