/**
 * O PRECEDENTE de código na shortlist (F-044), do lado da tela.
 *
 * A shortlist casa texto contra a descrição do catálogo e recomeça do zero em toda praça.
 * O precedente é a outra memória: o rótulo que já foi decidido antes traz de volta o
 * pacote de códigos que ele disparou, com a contagem de em quantas praças isso aconteceu.
 * Ele **antecede** a cascata sem substituí-la — a via léxica continua atendendo o rótulo
 * inédito, e a ordem instalada por fonte de preço não é tocada.
 *
 * Módulo PURO de propósito, no molde de `acervo.ts` e `matrix.ts`: o que o bloco mostra, o
 * que a lista de confirmação vai gravar e o pedido que sai daí ficam testáveis sem
 * transporte e sem DOM.
 *
 * O que o Design Approval Package aprovado (revisão 1, 2026-08-28) fixou e este módulo
 * carrega:
 *
 * - **bloco próprio ACIMA dos blocos por fonte, sem reordenar a cascata** — por isso
 *   `blocosDaShortlist` devolve a lista de candidatos EXATAMENTE como a recebeu (a mesma
 *   referência), e o precedente sai por um campo separado;
 * - **um código pode aparecer duas vezes**, no precedente e no bloco da fonte: nada aqui
 *   remove candidato repetido, porque esconder a repetição faria o bloco da cascata
 *   parecer incompleto;
 * - **sem precedente, ou com fonte de preço diferente, o bloco NÃO EXISTE** — as funções
 *   devolvem `null`, e não um precedente vazio que a tela teria de desabilitar;
 * - **o aceite é do pacote inteiro do rótulo, em uma revisão só, com a lista à vista**
 *   (`abrirConfirmacao` → `pedidoDeConfirmacao`, um pedido com os N códigos);
 * - **aceitar o precedente não fecha o pacote**: o pedido que sai daqui é sempre
 *   `confirm`, e o fechamento continua sendo ato próprio, de outra rota.
 *
 * **Precedente é observação, nunca decisão.** Nada neste módulo grava: ele monta o que
 * está à vista e o corpo que o clique de confirmar levará.
 */

import type { CascadeEntry, CodeDecisionDraft } from "./api";
import { entryOfDigest } from "./cascata";

// --- Espelho do envelope da API ---------------------------------------------
//
// Escrito à mão aqui, como o resto do envelope do orçamento: `@croquito/contracts` gera o
// domínio, não as rotas. Todo decimal atravessa como STRING e nunca vira `number`.

/**
 * Um código que o rótulo já disparou antes, com a contagem de praças em que ele apareceu.
 *
 * `worksite_count` é do CÓDIGO; o do rótulo vive em `ItemPrecedent` e pode ser maior — um
 * pacote de quatro praças pode ter um código que só três delas usaram.
 */
export type PrecedentCode = {
  code: string;
  worksite_count: number;
  description: string;
  unit: string;
  /** Decimal em TEXTO, como todo dinheiro desta jornada. */
  unit_price: string;
  unit_compatible: boolean;
  catalog_sha256: string;
};

/** O precedente de um elemento pendente: o rótulo normalizado e o pacote que ele dispara. */
export type ItemPrecedent = {
  item_id: string;
  normalized_label: string;
  worksite_count: number;
  codes: PrecedentCode[];
};

/**
 * Abaixo de duas praças o precedente é uma decisão única, que pode ter sido um engano — e
 * exibi-la com autoridade propaga o engano. O pacote de design decidiu que o caso é
 * MARCADO, nunca escondido: o limiar de quantas praças fazem um precedente confiável
 * continua em aberto (unknown 3 da feature) e não é decidido aqui.
 */
export const PRACAS_DE_PRECEDENTE_FRACO = 1;

/**
 * O precedente do item, com os códigos cuja fonte está instalada NESTA rodada — ou `null`
 * quando não há precedente, quando ele é de outra fonte de preço, ou quando sobrou nenhum
 * código depois do filtro.
 *
 * O filtro por cascata é a segunda tranca da decisão 7 do pacote: o servidor já omite
 * código fora do catálogo vigente, e aqui um código que cite catálogo que a rodada não
 * instalou também não é oferecido. Sugerir código que não existe na tabela vigente é o
 * pior resultado possível — pior que não sugerir nada —, e um bloco desabilitado seria o
 * controle inerte que o pacote proíbe.
 */
export function precedenteDoItem(
  precedents: readonly ItemPrecedent[] | undefined,
  itemId: string,
  cascade: readonly CascadeEntry[],
): ItemPrecedent | null {
  if (precedents === undefined || itemId === "") {
    return null;
  }
  const precedente = precedents.find((entry) => entry.item_id === itemId);
  if (precedente === undefined) {
    return null;
  }
  const codes = precedente.codes.filter(
    (code) => entryOfDigest(cascade, code.catalog_sha256) !== null,
  );
  if (codes.length === 0) {
    return null;
  }
  return { ...precedente, codes };
}

/**
 * A fonte de preço do precedente — a entrada da cascata que TODOS os códigos dele citam —,
 * ou `null` quando eles não convergem para uma só.
 *
 * O índice é chaveado por (rótulo, fonte de preço), então o normal é haver uma fonte só, e
 * é ela que o cabeçalho do bloco nomeia. `null` é estado honesto: um precedente que
 * atravessasse duas tabelas não pode ser rotulado com o nome de uma delas, e a fonte de
 * cada código continua sendo o `catalog_sha256` que ele carrega.
 */
export function fonteDoPrecedente(
  precedente: ItemPrecedent,
  cascade: readonly CascadeEntry[],
): CascadeEntry | null {
  const digests = new Set(precedente.codes.map((code) => code.catalog_sha256));
  if (digests.size !== 1) {
    return null;
  }
  return entryOfDigest(cascade, [...digests][0]);
}

/** `true` quando o precedente vem de uma praça só — o caso do aviso âmbar. */
export function precedenteFraco(precedente: ItemPrecedent): boolean {
  return precedente.worksite_count <= PRACAS_DE_PRECEDENTE_FRACO;
}

/** O selo de um elemento na lista de pendências. */
export type SeloDeItem =
  | { kind: "precedente"; worksiteCount: number }
  | { kind: "inedito" };

/**
 * O selo de cada elemento pendente — e `Map` VAZIO quando nenhum deles tem precedente
 * visível nesta rodada.
 *
 * O mapa vazio é a decisão 7 aplicada à lista: numa rodada sem precedente nenhum, a tela é
 * exatamente a de hoje, sem selo "rótulo inédito" em todo item para anunciar uma memória
 * que não existe. O selo de inédito só faz sentido ao lado de irmãos que TÊM precedente,
 * que é como o pacote aprovado o desenha.
 */
export function selosDosItens(
  precedents: readonly ItemPrecedent[] | undefined,
  itemIds: readonly string[],
  cascade: readonly CascadeEntry[],
): Map<string, SeloDeItem> {
  const selos = new Map<string, SeloDeItem>();
  const comPrecedente = new Map<string, number>();
  for (const itemId of itemIds) {
    const precedente = precedenteDoItem(precedents, itemId, cascade);
    if (precedente !== null) {
      comPrecedente.set(itemId, precedente.worksite_count);
    }
  }
  if (comPrecedente.size === 0) {
    return selos;
  }
  for (const itemId of itemIds) {
    const contagem = comPrecedente.get(itemId);
    selos.set(
      itemId,
      contagem === undefined
        ? { kind: "inedito" }
        : { kind: "precedente", worksiteCount: contagem },
    );
  }
  return selos;
}

/**
 * Os dois blocos da shortlist do elemento aberto, na ordem em que a tela os desenha.
 *
 * `candidatos` sai **como entrou**, na mesma ordem e com o mesmo conteúdo — é a mesma
 * referência de array, e é isso que o teste prova. A cascata é contrato de outra decisão
 * (ADR-0021 e a cascata da F-020); o precedente entra por cima dela, nunca dentro dela.
 */
export function blocosDaShortlist<Candidato>(
  candidatos: readonly Candidato[],
  precedents: readonly ItemPrecedent[] | undefined,
  itemId: string,
  cascade: readonly CascadeEntry[],
): { precedente: ItemPrecedent | null; candidatos: readonly Candidato[] } {
  return {
    precedente: precedenteDoItem(precedents, itemId, cascade),
    candidatos,
  };
}

/**
 * O pacote que o clique de aceitar põe à vista, antes de qualquer gravação. Ele é do
 * ELEMENTO: `itemId` viaja junto para que uma confirmação aberta nunca seja lida como se
 * fosse de outro item.
 */
export type ConfirmacaoDoPrecedente = {
  itemId: string;
  rotulo: string;
  codes: readonly PrecedentCode[];
};

/** Põe o pacote à vista. Nada é gravado aqui: o ato é o clique seguinte. */
export function abrirConfirmacao(
  precedente: ItemPrecedent,
  rotulo: string,
): ConfirmacaoDoPrecedente {
  return {
    itemId: precedente.item_id,
    rotulo,
    codes: [...precedente.codes],
  };
}

/**
 * A confirmação aberta, se ela for DESTE elemento — ou `null`. Trocar de elemento com a
 * lista aberta não pode deixar em pé uma lista que promete gravar códigos noutro item.
 */
export function confirmacaoDoItem(
  confirmacao: ConfirmacaoDoPrecedente | null,
  itemId: string,
): ConfirmacaoDoPrecedente | null {
  if (confirmacao === null || itemId === "" || confirmacao.itemId !== itemId) {
    return null;
  }
  return confirmacao;
}

/** `true` quando há o que gravar; lista vazia nunca vira pedido. */
export function podeConfirmar(confirmacao: ConfirmacaoDoPrecedente): boolean {
  return confirmacao.codes.length > 0;
}

/**
 * O rascunho do ÚNICO pedido que o aceite dispara: `confirm` com os N códigos do rótulo,
 * numa revisão só.
 *
 * `action` é sempre `confirm`, e nunca fechamento: aceitar o precedente não declara o
 * pacote completo — o fechamento continua sendo ato separado (F-038), e um atalho que
 * fechasse junto tiraria da orçamentista a decisão de dizer "acabou".
 */
export function pedidoDeConfirmacao(
  confirmacao: ConfirmacaoDoPrecedente,
  baseVersion: number,
): CodeDecisionDraft {
  return {
    itemId: confirmacao.itemId,
    action: "confirm",
    baseVersion,
    codes: confirmacao.codes.map((code) => code.code),
  };
}
