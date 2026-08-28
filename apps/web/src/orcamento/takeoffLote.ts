/**
 * Regras puras do LOTE de decisões da revisão do takeoff, no orçamento-base.
 *
 * Módulo separado de `requests.ts` de propósito: lá mora o que vai no CORPO da requisição
 * (o contrato das rotas `/v1/estimate-rounds*`), aqui mora o que a TELA pode montar e
 * quem ela pode marcar antes de qualquer requisição existir. São perguntas diferentes —
 * "o lote aceita este item?" não é uma pergunta de serialização —, e misturá-las faria o
 * módulo de contrato passar a decidir comportamento de tela.
 *
 * O ato de revisão é o lote inteiro: uma revisão para todas as decisões, ou nenhuma. É por
 * isso que a montagem do rascunho vive aqui e é usada pelos DOIS caminhos que anotam — o
 * formulário item a item e a marcação em massa. Duas montagens seriam duas regras, e a que
 * ninguém testasse seria a que gravaria errado.
 *
 * Nada aqui sabe de React, de DOM ou de transporte.
 */

import type { TakeoffDecisionDraft, TakeoffItem } from "./api";
import { parseDecimalInput } from "./format";
import {
  AVISO_AMBIGUO_FORA_DO_LOTE,
  AVISO_ITEM_JA_REVISADO,
  DICA_QUANTIDADE,
} from "./labels";

/** Campos escritos no formulário de decisão, ainda em texto cru da tela. */
export type CamposDaDecisao = {
  /** Quantidade corrigida, em texto: `Decimal` não passa por `number`. */
  quantity: string;
  unit: string;
  note: string;
  itemNote: string;
};

/** Formulário sem nada escrito: é o que a marcação em massa anota. */
export const CAMPOS_VAZIOS: CamposDaDecisao = {
  quantity: "",
  unit: "",
  note: "",
  itemNote: "",
};

/**
 * Montagem do rascunho: ou a anotação pronta, ou a recusa em língua de obra. Nunca as
 * duas, e nunca nenhuma — quem chama não precisa adivinhar o que aconteceu.
 */
export type MontagemDaAnotacao =
  | { anotacao: TakeoffDecisionDraft; recusa: null }
  | { anotacao: null; recusa: string };

/**
 * Item que já recebeu decisão do orçamentista. Decisão não se sobrescreve (o domínio
 * recusa com `TAKEOFF_ITEM_ALREADY_REVIEWED`), e como o lote é atômico, deixar um item
 * assim entrar na anotação derrubaria o ato inteiro por causa dele.
 */
export function itemJaRevisado(item: TakeoffItem | null): boolean {
  return item !== null && (item.status === "confirmed" || item.status === "rejected");
}

/**
 * Por que este item NÃO pode entrar na marcação em massa — ou `null` quando pode.
 *
 * Marcar em massa é um só ato: "confirmo a quantidade que a legenda diz". Dois itens não
 * cabem nele, e cada um por uma razão própria:
 *
 * - o já revisado, porque decisão não se sobrescreve e ele derrubaria o lote atômico;
 * - o ambíguo, porque a legenda não diz quantidade nenhuma — confirmá-lo em massa
 *   carimbaria um número que ninguém escreveu.
 *
 * O motivo volta em TEXTO, e não como booleano, porque a tela precisa dizê-lo por
 * extenso: caixa de seleção cinzenta sem explicação é a tela recusando em silêncio.
 */
export function motivoNaoMarcavel(item: TakeoffItem): string | null {
  if (itemJaRevisado(item)) {
    return AVISO_ITEM_JA_REVISADO;
  }
  if (item.status === "ambiguous") {
    return AVISO_AMBIGUO_FORA_DO_LOTE;
  }
  return null;
}

/**
 * Monta a anotação de um item a partir do que está escrito no formulário.
 *
 * Campo em branco vira ausência (`undefined`), e não string vazia: `""` seria uma correção
 * para "nada", quando o que houve foi a pessoa não corrigir — a quantidade lida da legenda
 * permanece. É a mesma regra que `requests.ts` aplica no corpo, afirmada já no rascunho
 * para que a própria tela não exiba unidade vazia como se fosse escolha.
 *
 * A quantidade escrita é conferida aqui: decimal que não é decimal recusa a anotação
 * inteira, em vez de viajar e derrubar o lote no servidor.
 */
export function montarAnotacao(
  item: TakeoffItem,
  action: "confirm" | "reject",
  campos: CamposDaDecisao,
): MontagemDaAnotacao {
  if (itemJaRevisado(item)) {
    return { anotacao: null, recusa: AVISO_ITEM_JA_REVISADO };
  }
  const escrita = campos.quantity.trim();
  const quantity = escrita.length === 0 ? undefined : (parseDecimalInput(escrita) ?? undefined);
  if (escrita.length > 0 && quantity === undefined) {
    return {
      anotacao: null,
      recusa: `A quantidade escrita não é um decimal exato; nada foi anotado. ${DICA_QUANTIDADE}`,
    };
  }
  return {
    anotacao: {
      itemId: item.id,
      action,
      quantity,
      unit: textoOuAusencia(campos.unit),
      note: textoOuAusencia(campos.note),
      itemNote: textoOuAusencia(campos.itemNote),
    },
    recusa: null,
  };
}

/** Rótulo do botão que anota as marcadas, com singular e plural corretos. */
export function rotuloAnotarEmMassa(quantidade: number): string {
  return quantidade === 1
    ? "Anotar 1 como confirmado"
    : `Anotar ${quantidade} como confirmados`;
}

/** Aviso depois de anotar em massa: quantas entraram e que gravar ainda não aconteceu. */
export function avisoDeAnotacaoEmMassa(quantidade: number): string {
  return quantidade === 1
    ? "1 decisão anotada no lote; ela ainda não foi gravada."
    : `${quantidade} decisões anotadas no lote; elas ainda não foram gravadas.`;
}

function textoOuAusencia(valor: string): string | undefined {
  const limpo = valor.trim();
  return limpo.length === 0 ? undefined : limpo;
}
