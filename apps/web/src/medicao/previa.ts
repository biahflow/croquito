/**
 * A abertura da medição seguinte e a prévia do que a declaração faz (F-040, ADR-0056).
 *
 * **A conta não está aqui.** Ela está no servidor, em `POST /v1/valuation-round-previews`, e
 * este módulo só decide *o que perguntar*, *quando perguntar* e *o que exibir*. Foi a T7 que
 * mudou isso: a T6 tinha posto a aritmética da prévia no navegador — sobre `BigInt`, exata,
 * cuidadosa e ainda assim errada de lugar. A regra da jornada de medição é explícita em
 * `apps/web/AGENTS.md` e o critério de aceite VAL-07 a cita:
 *
 * > A tela **nunca** soma, multiplica ou arredonda dinheiro/quantidade: exibe as strings
 * > decimais que o servidor mandou.
 *
 * Ela não é regra de estilo. Para projetar no cliente era preciso rederivar duas identidades
 * do domínio que nenhuma leitura expunha — o acumulado (`vigente − saldo`) e o medido do
 * período, somado das linhas do boletim —, que é exatamente a duplicação de lógica de domínio
 * que a regra existe para impedir: o dia em que o servidor mudasse uma delas, a tela mostraria
 * um número plausível e errado, sem nada acusando.
 *
 * O que sobrou aqui é chamada, estado e exibição. `efeitoEmPtBr` só troca pontuação, como
 * `format.ts`.
 */

import type { AmendmentDraft, PriceAdjustmentDraft, RoundPreviewLine, RoundSummary } from "./api";
import type { RoundPreviewDraft, RoundPreviewResponse } from "./api";
import { formatDecimalText } from "./format";

/** O efeito com sinal, em pt-BR: "+120,00", "-83,86". Só pontuação — nenhuma conta.
 *
 * O sinal já vem explícito do servidor (`amendment_delta`); aqui ele é separado do módulo
 * para que `formatDecimalText` receba só dígitos, e recolocado do lado esquerdo.
 */
export function efeitoEmPtBr(efeito: string): string {
  const negativo = efeito.trim().startsWith("-");
  const modulo = efeito.trim().replace(/^[+-]/, "");
  return `${negativo ? "-" : "+"}${formatDecimalText(modulo)}`;
}

/**
 * O que a abertura da medição seguinte já sabe sem perguntar nada (decisões 1 e 2 do pacote).
 *
 * O período NÃO é digitado: é o da rodada anterior mais um. Isso é a ORDEM de uma medição, e
 * não quantidade nem dinheiro — a regra que a T7 restaurou fala desses dois. E quem decide de
 * verdade continua sendo o servidor: período fora de sequência é recusado com
 * `PERIOD_NOT_SEQUENTIAL`, tanto na prévia quanto na criação.
 *
 * O rótulo nasce preenchido porque é texto de planilha, e continua editável — ele é copy da
 * prefeitura, não número do contrato.
 */
export function aberturaDaMedicaoSeguinte(round: RoundSummary): {
  previousRoundId: string;
  periodNumber: string;
  referenceLabel: string;
} {
  const periodo = round.period_number + 1;
  return {
    previousRoundId: round.round_id,
    periodNumber: String(periodo),
    referenceLabel: `Medição ${periodo} — ${round.worksite_name}`,
  };
}

/**
 * O estado da prévia na tela, por extenso.
 *
 * `indisponivel` existe porque a prévia **informa, não bloqueia**: falhar em projetar não
 * pode impedir de declarar — quem confere o consolidado é o servidor, na criação. O que a
 * tela deve fazer é dizer que não conseguiu projetar, em vez de mostrar tabela vazia ou,
 * pior, número inventado.
 */
export type EstadoDaPrevia =
  | { status: "ausente" }
  | { status: "carregando" }
  | { status: "pronta"; previa: RoundPreviewResponse }
  | { status: "indisponivel"; motivo: string };

/**
 * O pedido da prévia, ou `null` quando não há origem contratada escolhida.
 *
 * Sem contratado não há contratado, vigente nem saldo a projetar: a porta do catálogo por
 * upload abre rodada sem nada disso, e o servidor recusaria o pedido.
 */
export function pedidoDaPrevia(input: {
  estimateRoundId?: string | null;
  previousRoundId?: string | null;
  periodNumber: string;
  priceAdjustment?: PriceAdjustmentDraft | null;
  amendment?: AmendmentDraft | null;
}): RoundPreviewDraft | null {
  const periodo = input.periodNumber.trim();
  if (periodo.length === 0 || !Number.isFinite(Number(periodo))) {
    return null;
  }
  if (input.estimateRoundId) {
    return {
      estimateRoundId: input.estimateRoundId,
      periodNumber: periodo,
      priceAdjustment: input.priceAdjustment ?? undefined,
      amendment: input.amendment ?? undefined,
    };
  }
  if (input.previousRoundId) {
    return {
      previousRoundId: input.previousRoundId,
      periodNumber: periodo,
      priceAdjustment: input.priceAdjustment ?? undefined,
      amendment: input.amendment ?? undefined,
    };
  }
  return null;
}

/** Uma linha que a declaração cita: aqui o efeito existe, e o tipo diz isso. */
export type LinhaDeclarada = RoundPreviewLine & { amendment_delta: string };

/**
 * As linhas que a declaração desta abertura CITA — as únicas que a prévia do efeito mostra.
 *
 * O servidor devolve o consolidado inteiro (é ele que a herança exibe); `amendment_delta`
 * nulo é "a RE-RA não fala deste código", que não é a mesma coisa que delta zero declarado.
 *
 * O retorno é estreitado de propósito: sem isso, a tabela do efeito precisaria de um valor
 * de reserva para um caso que este filtro acabou de tornar impossível, e valor de reserva
 * que nunca acontece é exatamente o que ninguém revisa.
 */
export function linhasDeclaradas(previa: RoundPreviewResponse | null): LinhaDeclarada[] {
  if (previa === null) {
    return [];
  }
  return previa.lines.filter(
    (linha): linha is LinhaDeclarada => linha.amendment_delta !== null,
  );
}
