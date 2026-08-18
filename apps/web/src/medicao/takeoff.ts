/**
 * Derivação pura de estado de item de takeoff que não é geometria de apresentação
 * (`viewport.ts` fica só com estilos CSS e coordenadas de pixel, nenhum dado de domínio).
 */

import type { AnchorStatus, TakeoffItem } from "./api";

/**
 * Confiabilidade da localização (`evidence.bbox`) de um item na prancha, tolerante à
 * ausência do campo no servidor: sem `anchor`, o lado conservador é `"raw"` — nunca
 * desenhar um retângulo sobre a prancha sem confirmação de que ele está no lugar certo.
 */
export function itemAnchor(item: TakeoffItem): AnchorStatus {
  return item.anchor ?? "raw";
}
