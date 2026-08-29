/**
 * Leitura pura da quantidade que veio da CENA aprovada (F-047 T7b, ADR-0058).
 *
 * A regra que este módulo existe para não quebrar é a mesma de `format.ts`, e aqui ela
 * pesa mais: **nada aqui calcula**. Não há soma, subtração, produto, porcentagem nem
 * `Number()`. A diferença e a tolerância de uma divergência são texto decimal que o
 * servidor recomputou e conferiu na gravação (`QuantityDivergence` se recusa a existir
 * com uma diferença que não seja a dos próprios números); refazer a conta no navegador
 * criaria um segundo cálculo que ninguém audita e que discordaria do gravado no dia em
 * que a tolerância mudar.
 *
 * O que este módulo faz é ESCOLHER e NOMEAR: qual dos dois números foi escolhido, qual
 * ficou preterido, de que lado falta a identidade, se o item fecha. Selecionar um campo
 * não é calcular.
 *
 * Duas ausências deliberadas, porque a tela precisa distinguir uma da outra:
 * - item sem `scene_divergence` é item que não divergiu (ou que nunca foi confrontado);
 * - divergência sem `resolution` é divergência ABERTA, e ela bloqueia o item.
 */

import type { TakeoffPacket } from "@croquito/contracts";

import type { TakeoffItem } from "./api";

/** Origem da quantidade do item; `scene_graph` é a porta que a F-047 T4 abriu. */
export type QuantitySource = TakeoffPacket.Source1;

/** Precisão declarada pela entidade da cena; nunca sobe ao atravessar a fronteira. */
export type Precision = TakeoffPacket.Precision;

export type QuantityDivergence = TakeoffPacket.QuantityDivergence;

/** As duas — e só as duas — escolhas que resolvem uma divergência (ADR-0058, decisão 6). */
export type DivergenceChoice = TakeoffPacket.DivergenceChoice;

/** O que o confronto fez com um item. Três desfechos, e só três. */
export type SceneConfrontationOutcome = "fed" | "divergence_recorded" | "unchanged";

/**
 * Uma linha do relatório do confronto. `reason` viaja como texto porque o servidor manda
 * dois enums disjuntos no mesmo campo (o motivo de a cena não ter número e o motivo de o
 * item ficar intacto): a tela traduz pelo valor, e valor desconhecido aparece como veio em
 * vez de virar frase inventada.
 */
export type SceneItemOutcome = {
  item_id: string;
  element_ref: string | null;
  outcome: SceneConfrontationOutcome;
  reason: string | null;
  scene_quantity: string | null;
  scene_precision: Precision | null;
};

/**
 * O relatório do confronto, item a item. TODOS os itens do pacote aparecem, inclusive os
 * intactos: ausência na lista nunca é como este produto diz que não havia número.
 */
export type SceneConfrontationReport = {
  job_id: string;
  scene_revision_id: string;
  export_id: string;
  changed: boolean;
  fed: number;
  divergences_recorded: number;
  unchanged: number;
  items: SceneItemOutcome[];
};

/**
 * O croqui declarado desta rodada, ou a ausência DECLARADA dele.
 *
 * `present: false` é informação e não omissão: rodada sem elo é rodada que ninguém ligou a
 * croqui nenhum, e a jornada segue exatamente como antes da F-047.
 */
export type SceneLinkState =
  | { present: false }
  | {
      present: true;
      job_id: string;
      scene_revision_id: string;
      export_id: string;
      dxf_sha256: string | null;
      declared_by: string;
      declared_at: string;
    };

/**
 * Motivos em que a identidade falta na LEGENDA — o item de takeoff não declarou
 * `element_ref`, então nenhuma linha da cena pode ser casada com ele.
 */
const SEM_IDENTIDADE_NA_LEGENDA = "item_without_element_ref";

/**
 * Motivos em que a identidade falta na CENA — o item declarou a sua, e nenhuma linha do
 * `quantitativos.csv` a cita.
 */
const SEM_IDENTIDADE_NA_CENA = "element_ref_absent_from_scene";

/** `true` quando a quantidade deste item nasceu da cena aprovada, e não da legenda. */
export function vemDaCena(item: TakeoffItem): boolean {
  return item.source === "scene_graph";
}

/**
 * A divergência gravada neste item, aberta ou resolvida — `null` quando não há nenhuma.
 *
 * O contrato admite `undefined` (item de pacote gravado antes da F-047) e `null` (item
 * confrontado sem divergir); os dois significam a mesma coisa para quem desenha.
 */
export function divergenciaDoItem(item: TakeoffItem): QuantityDivergence | null {
  return item.scene_divergence ?? null;
}

/** A divergência que ainda espera decisão humana; `null` quando não há ou já foi resolvida. */
export function divergenciaAberta(item: TakeoffItem): QuantityDivergence | null {
  const divergencia = divergenciaDoItem(item);
  if (divergencia === null || divergencia.resolution) {
    return null;
  }
  return divergencia;
}

/** A divergência já decidida, com o carimbo de quem escolheu; `null` quando não há. */
export function divergenciaResolvida(item: TakeoffItem): QuantityDivergence | null {
  const divergencia = divergenciaDoItem(item);
  if (divergencia === null || !divergencia.resolution) {
    return null;
  }
  return divergencia;
}

/**
 * Por que este item não fecha, por extenso — ou `null` quando nada o bloqueia.
 *
 * Bloqueio é diagnóstico, não recusa: a frase diz o que falta e qual é o próximo ato, em
 * vez de só marcar o item. Quem lê a tela precisa saber que a decisão continua sendo dele.
 */
export function motivoDeBloqueio(item: TakeoffItem): string | null {
  if (divergenciaAberta(item) === null) {
    return null;
  }
  return (
    "Divergência aberta entre a cena aprovada e a legenda lida: este item não fecha " +
    "enquanto ninguém escolher qual das duas origens vale."
  );
}

/** Um dos dois números de uma divergência, com a origem que o produziu. */
export type NumeroDaDivergencia = {
  quantity: string;
  origem: DivergenceChoice;
};

/**
 * O número que a decisão humana escolheu; `null` enquanto a divergência estiver aberta.
 *
 * É seleção, nunca conta: o valor devolvido é literalmente a string que o servidor gravou
 * na origem escolhida.
 */
export function numeroEscolhido(
  divergencia: QuantityDivergence,
): NumeroDaDivergencia | null {
  const resolucao = divergencia.resolution;
  if (!resolucao) {
    return null;
  }
  return resolucao.choice === "scene"
    ? { quantity: divergencia.scene.quantity, origem: "scene" }
    : { quantity: divergencia.legend.quantity, origem: "legend" };
}

/**
 * O número PRETERIDO, que continua gravado; `null` enquanto a divergência estiver aberta.
 *
 * Resolver não apaga: quem abrir a memória de cálculo meses depois vê os dois números, a
 * diferença, a tolerância vigente e quem decidiu.
 */
export function numeroPreterido(
  divergencia: QuantityDivergence,
): NumeroDaDivergencia | null {
  const resolucao = divergencia.resolution;
  if (!resolucao) {
    return null;
  }
  return resolucao.choice === "scene"
    ? { quantity: divergencia.legend.quantity, origem: "legend" }
    : { quantity: divergencia.scene.quantity, origem: "scene" };
}

/**
 * De que lado falta a identidade, quando o motivo do relatório é ausência de par.
 *
 * "Não encontrado" sem lado manda a pessoa procurar nos dois; esta função é o que permite
 * à tela dizer onde declarar. `null` quando o motivo é outro.
 */
export function ladoSemIdentidade(
  reason: string | null,
): "legenda" | "cena" | null {
  if (reason === SEM_IDENTIDADE_NA_LEGENDA) {
    return "legenda";
  }
  if (reason === SEM_IDENTIDADE_NA_CENA) {
    return "cena";
  }
  return null;
}

/**
 * A frase que substitui o palpite quando não há par.
 *
 * Ela nomeia o lado e o próximo ato. Nunca sugere casar por número igual, por proximidade
 * do balão, pela ordem das linhas nem por rótulo parecido — é a rejeição central do
 * ADR-0058, e `418,12` de um lado com `418,12` do outro continua sendo ausência de par.
 */
export function frasePorFaltaDePar(outcome: SceneItemOutcome): string | null {
  const lado = ladoSemIdentidade(outcome.reason);
  if (lado === "legenda") {
    return (
      "Nenhum par. Este item não tem quantidade vinda da cena porque a identidade do " +
      "elemento não está declarada na legenda. Declare-a no croqui e cite-a neste item, " +
      "ou siga com a quantidade lida — como hoje. Número igual não é identidade."
    );
  }
  if (lado === "cena") {
    return (
      "Nenhum par. A identidade declarada neste item não aparece em nenhuma linha do " +
      "quantitativos.csv do croqui declarado. Declare-a na cena, ou siga com a " +
      "quantidade lida. Número igual não é identidade."
    );
  }
  return null;
}

/**
 * Itens do pacote com divergência ABERTA, na ordem em que o pacote os traz.
 *
 * Contar itens não é contar dinheiro: é cardinalidade de lista, e é o que a etapa precisa
 * para dizer quantos itens não fecham sem que ninguém percorra os dois lados na mão.
 */
export function itensComDivergenciaAberta(items: TakeoffItem[]): TakeoffItem[] {
  return items.filter((item) => divergenciaAberta(item) !== null);
}
