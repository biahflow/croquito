/**
 * A declaração de reajuste, do lado da tela (F-039, ADR-0055).
 *
 * Puro: valida a FORMA da declaração antes da rede, para quem abre a rodada ler uma frase em
 * vez de um 422. O que este módulo não faz — e não pode fazer — é validar o VALOR do índice:
 * o sistema não tem como saber se 1,0432 é o INCC do período. O que ele exige é que a
 * declaração seja **conferível** por quem revisa, contra a publicação oficial.
 */

import type { PriceAdjustmentDraft } from "./api";

export const DICA_FATOR =
  "Escreva 1,0432 ou 1.0432 — o fator viaja como texto e o servidor o lê exato.";

export const REAJUSTE_OPCOES = [
  {
    valor: "none" as const,
    titulo: "Sem reajuste",
    explicacao: "O contrato paga os mesmos preços do período anterior.",
  },
  {
    valor: "index_factor" as const,
    titulo: "Reajuste por índice",
    explicacao: "Fator sobre o preço contratado, com índice e período declarados.",
  },
  {
    valor: "catalog_version" as const,
    titulo: "Nova versão da tabela contratual",
    explicacao: "O contrato passou a pagar por outra data-base da tabela.",
  },
];

/** Aceita "1,0432" e "1.0432"; recusa o resto. Conversão de NOTAÇÃO, nunca de valor. */
export function fatorEhLegivel(texto: string): boolean {
  return /^\d+(?:[.,]\d+)?$/.test(texto.trim());
}

/**
 * `null` quando a declaração pode ser enviada; senão a frase que a tela mostra.
 *
 * Sem declaração nenhuma também é `null`: não declarar É o caminho normal.
 */
export function reajusteIssue(draft: PriceAdjustmentDraft | null): string | null {
  if (draft === null) {
    return null;
  }
  if (draft.referencePeriod.trim().length === 0) {
    return "Declare o período de referência do reajuste, como a publicação oficial o nomeia.";
  }
  if (draft.kind === "catalog_version") {
    return null;
  }
  if ((draft.indexLabel ?? "").trim().length === 0) {
    return (
      "Fator sem índice não é conferível contra a publicação oficial. Declare qual índice " +
      "reajustou o contrato."
    );
  }
  const fator = (draft.factor ?? "").trim();
  if (fator.length === 0) {
    return "Declare o fator do reajuste.";
  }
  if (!fatorEhLegivel(fator)) {
    return `O fator escrito não é um decimal exato. ${DICA_FATOR}`;
  }
  if (Number(fator.replace(",", ".")) <= 0) {
    return "O fator precisa ser maior que zero — “sem reajuste” é não declarar, não declarar zero.";
  }
  return null;
}
