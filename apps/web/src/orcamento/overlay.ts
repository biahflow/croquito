/**
 * Leitura pura da idade do overlay do takeoff (ADR-0030), no orçamento-base.
 *
 * Cópia deliberada de `medicao/images.ts`, não import: as jornadas só compartilham o
 * transporte. O desenho das âncoras é reconstruído FORA do request path, e entre a
 * decisão da orçamentista e o re-render do worker existe uma janela em que o overlay
 * servido é o do pacote anterior. A rota declara isso (`stale`) e a tela precisa
 * mostrá-lo — em palavra, nunca só em cor, porque um desenho vencido engana com a
 * autoridade de um desenho.
 */

import type { OverlayState } from "./api";

export type OverlayFreshness = {
  /** Estado por extenso, ao lado de qualquer marca visual. */
  label: string;
  /** O que ele significa para quem está decidindo. */
  explanation: string;
  stale: boolean;
};

const ATUAL: OverlayFreshness = {
  label: "desenho do pacote atual",
  explanation:
    "As âncoras desenhadas correspondem ao pacote de takeoff que está nesta tela.",
  stale: false,
};

const VENCIDO: OverlayFreshness = {
  label: "desenho do pacote anterior",
  explanation:
    "Este desenho é de antes da última decisão: o overlay é redesenhado fora do pedido, " +
    "por comando de fila, e ainda não foi republicado. A lista ao lado já está atualizada.",
  stale: true,
};

/**
 * Overlay ausente é diferente de overlay vencido: sem desenho nenhum não há o que
 * mostrar, e afirmar "atual" seria falso.
 */
const AUSENTE: OverlayFreshness = {
  label: "sem desenho publicado",
  explanation:
    "Este orçamento ainda não tem overlay das âncoras publicado pelo worker.",
  stale: true,
};

/** Estado do overlay em texto; `null` é a leitura ainda não feita. */
export function overlayFreshness(
  overlay: OverlayState | null,
): OverlayFreshness | null {
  if (overlay === null) {
    return null;
  }
  if (!overlay.present) {
    return AUSENTE;
  }
  return overlay.stale ? VENCIDO : ATUAL;
}
