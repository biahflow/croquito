/**
 * A declaração de RE-RA, do lado da tela (F-040, ADR-0056).
 *
 * Puro: valida a FORMA da declaração antes da rede, para quem abre a rodada ler uma frase em
 * vez de um 422. O que este módulo não faz — e não pode fazer — é conferir o TEOR da
 * publicação: o sistema não tem como saber se o Processo 123/2026 de fato re-ratificou aquele
 * código. O que ele exige é que a declaração seja **conferível** por quem revisa, contra a
 * publicação oficial: quem declarou, quando, contra qual processo, e o efeito código a código.
 */

import type { AmendmentDraft } from "./api";

export const DICA_DELTA =
  "Escreva o efeito com sinal: -4 reduz, +6 acresce. O delta viaja como texto e o servidor o " +
  "lê exato.";

/** Aceita "-4", "6", "1,50" e "1.50"; recusa o resto. Notação, nunca conversão de valor. */
export function deltaEhLegivel(texto: string): boolean {
  return /^[+-]?\d+(?:[.,]\d+)?$/.test(texto.trim());
}

function deltaEhZero(texto: string): boolean {
  return Number(texto.trim().replace(",", ".")) === 0;
}

/**
 * `null` quando a declaração pode ser enviada; senão a frase que a tela mostra.
 *
 * Sem declaração nenhuma também é `null`: não re-ratificar É o caminho normal, e a ausência
 * não é erro. Uma linha inteiramente em branco é ignorada (a tela oferece linhas vazias para
 * preencher); mas um código sem delta, ou um delta sem código, é declaração pela metade.
 */
export function reRaIssue(draft: AmendmentDraft | null): string | null {
  if (draft === null) {
    return null;
  }
  if (draft.label.trim().length === 0) {
    return "Dê um nome curto à RE-RA — é como ela aparece na memória.";
  }
  if (draft.referencePeriod.trim().length === 0) {
    return "Declare o processo ou a publicação que re-ratificou o contrato, para quem revisa conferir.";
  }
  const preenchidas = draft.lines.filter(
    (line) => line.code.trim().length > 0 || line.quantityDelta.trim().length > 0,
  );
  if (preenchidas.length === 0) {
    return "Declare ao menos um código e o efeito da RE-RA sobre ele.";
  }
  for (const line of preenchidas) {
    if (line.code.trim().length === 0) {
      return "Uma linha tem efeito sem código: diga qual código a RE-RA altera.";
    }
    const delta = line.quantityDelta.trim();
    if (delta.length === 0) {
      return `Declare o efeito da RE-RA sobre ${line.code.trim()}. ${DICA_DELTA}`;
    }
    if (!deltaEhLegivel(delta)) {
      return `O efeito sobre ${line.code.trim()} não é um decimal exato. ${DICA_DELTA}`;
    }
    if (deltaEhZero(delta)) {
      return `Efeito zero não é RE-RA sobre ${line.code.trim()}: não declarar é o caminho de "sem mudança".`;
    }
  }
  return null;
}
