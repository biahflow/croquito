/**
 * Wrapper de captura (Task Contract T15, Comportamento exigido item 2): decodifica o
 * blob recém-capturado em resolução reduzida e chama o módulo puro `assessPhotoQuality`.
 *
 * Falha de decodificação NUNCA bloqueia a foto: blob corrompido, formato sem suporte,
 * `createImageBitmap`/canvas indisponíveis no aparelho — qualquer uma dessas vira
 * `{ available: false }`, nunca uma exceção que propaga até a UI. Quem chama trata isso
 * como "sem aviso" (mesma regra da foto "ok": segue direto, sem interstício) — a
 * avaliação em si não é persistida em lugar nenhum (T15, Scope item 3: "registrada só em
 * memória de tela").
 */

import { decodeReducedImageDataInBrowser } from "./decodeReduced";
import { assessPhotoQuality, type PhotoQualityResult } from "./quality";

export type PhotoQualityEvaluation = ({ available: true } & PhotoQualityResult) | { available: false };

export async function evaluateCapturedPhoto(
  blob: Blob,
  decode: (blob: Blob) => Promise<ImageData> = decodeReducedImageDataInBrowser,
): Promise<PhotoQualityEvaluation> {
  try {
    const imageData = await decode(blob);
    return { available: true, ...assessPhotoQuality(imageData) };
  } catch {
    return { available: false };
  }
}
