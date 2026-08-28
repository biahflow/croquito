/**
 * Desfazer um código confirmado (F-045), do lado da tela.
 *
 * A etapa de códigos só sabia avançar: a identidade da decisão é o par `(elemento, código)`,
 * re-decidir um par é recusado e não há rollback de revisão. Um código confirmado por engano
 * custava a praça inteira. Este módulo é a metade de tela do ato que fecha essa lacuna.
 *
 * Módulo PURO de propósito, no molde de `precedente.ts` e `acervo.ts`: o que a caixa mostra,
 * o que o clique vai gravar e o que aparece como desfeito ficam testáveis sem transporte e
 * sem DOM.
 *
 * O que o Design Approval Package (revisão 1) e o ADR-0061 fixaram e este módulo carrega:
 *
 * - **o motivo é obrigatório** — `podeDesfazer` é falso sem ele, e o pedido não se monta;
 * - **desfazer reabre o pacote** quando ele estava fechado, e o botão diz isso antes do
 *   clique (`pacoteFechado`);
 * - **o desfeito continua à vista**, numa lista própria do elemento (`desfeitosDoItem`) —
 *   "nunca decidido" e "decidido e desfeito" não podem parecer a mesma coisa;
 * - **desfazer não bane o código**: um par reconfirmado sai da lista de desfeitos, porque
 *   ele voltou a valer, ainda que o ato de ter desfeito continue gravado no conjunto.
 *
 * Nada aqui grava: o módulo monta o que está à vista e o corpo que o clique levará.
 */

import type { CodeAssignmentSet } from "@croquito/contracts";

import type { CodeRevocationDraft } from "./api";

/** O registro de um par desfeito, como o servidor o devolve no conjunto corrente. */
export type CodigoDesfeito = {
  item_id: string;
  code: string;
  revocation_id: string;
  reviewer_id: string;
  revoked_at: string;
  note: string;
};

/** A caixa aberta: de qual elemento, qual código, e o motivo em digitação. */
export type CaixaDeDesfazer = {
  itemId: string;
  code: string;
  motivo: string;
};

/** Põe a caixa à vista. O motivo nasce vazio, e sem ele nada é gravado. */
export function abrirDesfazer(itemId: string, code: string): CaixaDeDesfazer {
  return { itemId, code, motivo: "" };
}

/**
 * A caixa aberta, se ela for DESTE elemento — ou `null`. Trocar de elemento com a caixa
 * aberta não pode deixar em pé um formulário que promete desfazer código de outro item, pela
 * mesma razão que vale para a confirmação de precedente.
 *
 * O nome não é `caixaDoItem` porque na tela do orçamento "caixa" já significa a caixa
 * delimitadora do item na prancha (`OrcamentoApp.tsx`), e dois sentidos para a mesma palavra
 * no mesmo arquivo confundiriam quem lê depois.
 */
export function desfazerDoItem(
  caixa: CaixaDeDesfazer | null,
  itemId: string,
): CaixaDeDesfazer | null {
  if (caixa === null || itemId === "" || caixa.itemId !== itemId) {
    return null;
  }
  return caixa;
}

/** `true` quando há motivo escrito. Espaço em branco não é motivo. */
export function podeDesfazer(caixa: CaixaDeDesfazer): boolean {
  return caixa.motivo.trim().length > 0;
}

/** O rascunho do pedido. Só se monta com motivo — a obrigação está no tipo e aqui. */
export function pedidoDeDesfazer(
  caixa: CaixaDeDesfazer,
  baseVersion: number,
): CodeRevocationDraft {
  return {
    itemId: caixa.itemId,
    code: caixa.code,
    baseVersion,
    note: caixa.motivo.trim(),
  };
}

/**
 * `true` quando o pacote deste elemento está declarado completo.
 *
 * Serve ao texto do botão: desfazer um código de pacote fechado **reabre** o pacote, e
 * reabrir em silêncio é a pior versão disto — a exportação passa a recusar o elemento, e a
 * pessoa descobriria três telas depois.
 */
export function pacoteFechado(
  assignments: CodeAssignmentSet.CroquitoCodeAssignmentSet | null,
  itemId: string,
): boolean {
  if (assignments === null) {
    return false;
  }
  return (assignments.closures ?? []).some((closure) => closure.item_id === itemId);
}

/**
 * Os códigos desfeitos deste elemento que **continuam** desfeitos.
 *
 * Um par reconfirmado depois de revogado some da lista: ele voltou a valer, e mostrá-lo como
 * desfeito ao lado dele mesmo confirmado seria dizer duas coisas contrárias sobre o mesmo
 * código. O ato de ter desfeito continua no conjunto — o que esta lista responde é outra
 * pergunta: "por que este elemento não tem mais aquele código?".
 */
export function desfeitosDoItem(
  assignments: CodeAssignmentSet.CroquitoCodeAssignmentSet | null,
  itemId: string,
): CodigoDesfeito[] {
  if (assignments === null || itemId === "") {
    return [];
  }
  const confirmados = new Set(
    (assignments.assignments ?? [])
      .filter(
        (assignment) => assignment.item_id === itemId && assignment.status === "confirmed",
      )
      .map((assignment) => assignment.code),
  );
  return ((assignments.revocations ?? []) as CodigoDesfeito[]).filter(
    (revocation) =>
      revocation.item_id === itemId && !confirmados.has(revocation.code),
  );
}
