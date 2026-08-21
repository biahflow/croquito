/**
 * Decodifica um blob de foto em `ImageData` REDUZIDA (lado maior ≤
 * `MAX_REDUCED_SIDE_PX`) para alimentar `assessPhotoQuality` (Task Contract T15,
 * Contexto verificado: "getImageData em resolução REDUZIDA... para não travar aparelho
 * fraco; documentar a redução como decisão de custo"). Reduzir antes de medir é a decisão
 * de custo em si: o Laplaciano é O(largura×altura), então decodificar no tamanho original
 * (câmeras atuais entregam múltiplos megapixels) multiplicaria o custo por 10x–50x sem
 * ganho de sinal para nitidez/exposição em resolução de tela.
 *
 * Só fala com `createImageBitmap`/`<canvas>` (APIs de navegador) — mesmo padrão de
 * `voice/recorder.ts` (`browserVoiceDeps`): a dependência real fica isolada numa função
 * própria para o teste injetar um duplo sem DOM.
 */

/** Lado maior, em pixels, da imagem reduzida — Task Contract T15, Contexto verificado
 * ("ex.: lado maior ≤512px"). Não é heurística de qualidade (não afeta nitidez/exposição
 * calculadas), é orçamento de custo: maior janela = mais preciso e mais lento. */
export const MAX_REDUCED_SIDE_PX = 512;

/** Decodifica `blob` e devolve os pixels já reduzidos. Lança em qualquer falha (blob não é
 * imagem, decodificação sem suporte, canvas indisponível) — quem chama
 * (`evaluateCapturedPhoto`) é responsável por nunca deixar essa falha bloquear a foto. */
export async function decodeReducedImageDataInBrowser(blob: Blob): Promise<ImageData> {
  const bitmap = await createImageBitmap(blob);
  try {
    const scale = Math.min(1, MAX_REDUCED_SIDE_PX / Math.max(bitmap.width, bitmap.height));
    const width = Math.max(1, Math.round(bitmap.width * scale));
    const height = Math.max(1, Math.round(bitmap.height * scale));
    const canvas = document.createElement("canvas");
    canvas.width = width;
    canvas.height = height;
    const context = canvas.getContext("2d");
    if (context === null) {
      throw new Error("Canvas 2D indisponível neste navegador.");
    }
    context.drawImage(bitmap, 0, 0, width, height);
    return context.getImageData(0, 0, width, height);
  } finally {
    bitmap.close();
  }
}
