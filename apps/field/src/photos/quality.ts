/**
 * Checagem de qualidade de foto NO APARELHO, sem rede, sem provider (Task Contract T15,
 * prancha 7b da DAP rev.2). Módulo puro: recebe pixels já decodificados
 * (`ImageData`) e devolve um veredito escrito — nunca decide sozinho se a foto é boa o
 * bastante, só descreve o que mediu. O aviso resultante nunca bloqueia a captura (quem
 * decide é o técnico, ver `ui/photoQualityGate.ts`) e o veredito NÃO é persistido no
 * domínio nesta fatia (T15, Scope item 3) — é orientação do momento, descartável.
 *
 * ATENÇÃO: os limiares abaixo são HEURÍSTICA INICIAL, não regra de negócio. Foram
 * escolhidos para separar corretamente as quatro imagens sintéticas do Acceptance
 * Criteria (nítida/borrada/estourada/escura) com margem, não calibrados contra fotos
 * reais de campo — a calibração é trabalho do piloto (Task Contract T15, Goal), não
 * desta tarefa.
 */

/** Luma (Rec. 601, mesma ponderação do NTSC) usado tanto para o Laplaciano quanto para a
 * contagem de exposição — um único espaço de brilho para as duas medidas. */
const LUMA_R = 0.299;
const LUMA_G = 0.587;
const LUMA_B = 0.114;

/**
 * Variância do Laplaciano 3×3 abaixo da qual a foto é considerada borrada — HEURÍSTICA A
 * CALIBRAR. `1024` separa com folga a imagem "nítida" sintética (variância ≈ 48 400) e a
 * "borrada" sintética (variância 0) deste Task Contract; qualquer foto real decide a
 * calibração fina no piloto.
 */
export const BLUR_VARIANCE_THRESHOLD = 1024;

/** Luma (0–255) a partir do qual um pixel conta como "estourado" (excesso de luz) —
 * HEURÍSTICA A CALIBRAR. */
export const HIGHLIGHT_LUMA_THRESHOLD = 250;

/** Luma (0–255) abaixo do qual um pixel conta como "esmagado" (sombra sem detalhe) —
 * HEURÍSTICA A CALIBRAR. */
export const SHADOW_LUMA_THRESHOLD = 8;

/** Fração de pixels estourados acima da qual a foto vira "over" — HEURÍSTICA A
 * CALIBRAR. `0.35` (35%) exige que boa parte do quadro esteja estourada, não só um brilho
 * pontual (reflexo, lâmpada). */
export const CLIPPED_HIGHLIGHTS_FRACTION_THRESHOLD = 0.35;

/** Fração de pixels esmagados acima da qual a foto vira "under" — HEURÍSTICA A CALIBRAR,
 * mesmo raciocínio do limiar de estouro. */
export const CLIPPED_SHADOWS_FRACTION_THRESHOLD = 0.35;

export type PhotoQualityVerdict = "ok" | "blurry" | "under" | "over";

export interface PhotoQualityExposure {
  /** Fração (0–1) de pixels com luma ≥ `HIGHLIGHT_LUMA_THRESHOLD`. */
  clippedHighlights: number;
  /** Fração (0–1) de pixels com luma ≤ `SHADOW_LUMA_THRESHOLD`. */
  clippedShadows: number;
}

export interface PhotoQualityResult {
  /** Variância do Laplaciano da luma — quanto maior, mais nítida a foto. */
  sharpness: number;
  exposure: PhotoQualityExposure;
  verdict: PhotoQualityVerdict;
  /** Motivos em português, um por condição disparada (pode ter mais de um; o `verdict`
   * é só o de maior prioridade — ver `pickVerdict`). Vazio quando `verdict === "ok"`. */
  reasons: string[];
}

/** Prioridade de veredito quando mais de uma condição dispara ao mesmo tempo: borrada
 * primeiro (foto ilegível de qualquer jeito), depois estouro de luz, depois sombra —
 * mesma ordem em que um técnico julgaria "dá pra usar mesmo assim". */
function pickVerdict(isBlurry: boolean, isOver: boolean, isUnder: boolean): PhotoQualityVerdict {
  if (isBlurry) {
    return "blurry";
  }
  if (isOver) {
    return "over";
  }
  if (isUnder) {
    return "under";
  }
  return "ok";
}

/**
 * Avalia nitidez (variância do Laplaciano 3×3 sobre a luma) e exposição (fração de
 * pixels estourados/esmagados) de uma imagem já decodificada. Determinístico: mesma
 * `ImageData` sempre devolve o mesmo resultado — sem aleatoriedade, sem I/O, sem relógio.
 *
 * O Laplaciano só é calculado nos pixels interiores (borda de 1px de fora): imagens
 * degeneradas (`width < 3` ou `height < 3`, não deveria acontecer após a redução do
 * wrapper, mas o módulo puro não confia nisso) não têm nenhum pixel interior — `sharpness`
 * vira `+Infinity` (não há evidência de borrão, então não classifica como borrada) em vez
 * de `NaN`.
 */
export function assessPhotoQuality(data: ImageData): PhotoQualityResult {
  const { width, height } = data;
  const pixels = data.data;
  const totalPixels = width * height;
  const luma = new Float64Array(totalPixels);
  for (let pixelIndex = 0; pixelIndex < totalPixels; pixelIndex++) {
    const byteIndex = pixelIndex * 4;
    luma[pixelIndex] =
      LUMA_R * pixels[byteIndex] + LUMA_G * pixels[byteIndex + 1] + LUMA_B * pixels[byteIndex + 2];
  }

  let laplacianSum = 0;
  let laplacianSumSq = 0;
  let interiorCount = 0;
  for (let y = 1; y < height - 1; y++) {
    for (let x = 1; x < width - 1; x++) {
      const idx = y * width + x;
      const laplacian =
        -4 * luma[idx] + luma[idx - 1] + luma[idx + 1] + luma[idx - width] + luma[idx + width];
      laplacianSum += laplacian;
      laplacianSumSq += laplacian * laplacian;
      interiorCount++;
    }
  }
  const sharpness =
    interiorCount === 0
      ? Number.POSITIVE_INFINITY
      : laplacianSumSq / interiorCount - (laplacianSum / interiorCount) ** 2;

  let highlightCount = 0;
  let shadowCount = 0;
  for (let pixelIndex = 0; pixelIndex < totalPixels; pixelIndex++) {
    const value = luma[pixelIndex];
    if (value >= HIGHLIGHT_LUMA_THRESHOLD) {
      highlightCount++;
    }
    if (value <= SHADOW_LUMA_THRESHOLD) {
      shadowCount++;
    }
  }
  const clippedHighlights = totalPixels === 0 ? 0 : highlightCount / totalPixels;
  const clippedShadows = totalPixels === 0 ? 0 : shadowCount / totalPixels;

  const isBlurry = sharpness < BLUR_VARIANCE_THRESHOLD;
  const isOver = clippedHighlights > CLIPPED_HIGHLIGHTS_FRACTION_THRESHOLD;
  const isUnder = clippedShadows > CLIPPED_SHADOWS_FRACTION_THRESHOLD;

  const reasons: string[] = [];
  if (isBlurry) {
    reasons.push("Nitidez baixa — possivelmente tremida ou fora de foco.");
  }
  if (isOver) {
    reasons.push("Muitos trechos estourados de luz — difícil de ler.");
  }
  if (isUnder) {
    reasons.push("Imagem muito escura — difícil de ler.");
  }

  return {
    sharpness,
    exposure: { clippedHighlights, clippedShadows },
    verdict: pickVerdict(isBlurry, isOver, isUnder),
    reasons,
  };
}
