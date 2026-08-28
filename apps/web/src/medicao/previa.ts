/**
 * A herança da rodada anterior e a prévia da RE-RA, antes de gravar (F-040 T6, ADR-0056).
 *
 * Este módulo é a exceção declarada à regra "a tela nunca soma" do `apps/web/AGENTS.md`, e a
 * exceção tem fronteira estreita:
 *
 * - o que ele produz é **prévia**, nunca memória: é a projeção do que a rodada VAI nascer,
 *   mostrada enquanto ainda dá para desistir (decisão 6 do pacote de design aprovado). O
 *   número que a tela mostra DEPOIS de gravar continua vindo da resposta da API, e é o
 *   servidor que permanece autoridade — a prévia existe para que o efeito seja visível antes
 *   do POST, e não para substituir a conta do servidor;
 * - a aritmética é **exata em texto**, sobre `BigInt`, e reproduz a semântica de `Decimal` do
 *   Python: a escala do resultado de uma soma é a maior das duas escalas. Nenhum valor passa
 *   por `Number`, nada é arredondado e nada é truncado. `previa.test.ts` fixa os números
 *   contra os que a API devolve depois de gravar (`tests/api/test_valuation_round_from_estimate
 *   .py::test_a_medicao_seguinte_nasce_re_ratificada`), e é esse par que impede a prévia de
 *   divergir em silêncio;
 * - nenhuma conta de DINHEIRO acontece aqui. O total medido no período é a string que o
 *   boletim do servidor já traz.
 *
 * Onde a conta não fecha — texto que não é decimal legível —, o campo derivado sai `null` e a
 * tela declara a ausência. Inventar um número seria pior do que não mostrá-lo.
 */

import type {
  AmendmentDraft,
  BulletinResponse,
  CatalogSearchResult,
  RoundContractedPrice,
  RoundContractedQuantity,
  RoundSummary,
} from "./api";
import { formatDecimalText } from "./format";

type Fracao = { valor: bigint; escala: number };

/** Aceita "-4", "6", "1,50" e "1.50" — a mesma notação que `reratificacao.ts` já admite. */
const DECIMAL_TEXTO = /^([+-]?)(\d+)(?:[.,](\d+))?$/;

function paraFracao(texto: string): Fracao | null {
  const encontrado = DECIMAL_TEXTO.exec(texto.trim());
  if (encontrado === null) {
    return null;
  }
  const fracionaria = encontrado[3] ?? "";
  const valor = BigInt(`${encontrado[2]}${fracionaria}`);
  return {
    valor: encontrado[1] === "-" ? -valor : valor,
    escala: fracionaria.length,
  };
}

function escrever({ valor, escala }: Fracao): string {
  const negativo = valor < 0n;
  const digitos = (negativo ? -valor : valor).toString().padStart(escala + 1, "0");
  const corte = digitos.length - escala;
  const inteira = digitos.slice(0, corte);
  const fracionaria = escala === 0 ? "" : `.${digitos.slice(corte)}`;
  return `${negativo ? "-" : ""}${inteira}${fracionaria}`;
}

/**
 * `a + b` exato, ou `null` quando um dos dois não é decimal legível.
 *
 * A escala do resultado é a MAIOR das duas, que é exatamente o que `Decimal.__add__` faz no
 * Python: `Decimal("12.00") + Decimal("3")` é `Decimal("15.00")`, e não `Decimal("15")`.
 */
export function somarExato(a: string, b: string): string | null {
  const esquerda = paraFracao(a);
  const direita = paraFracao(b);
  if (esquerda === null || direita === null) {
    return null;
  }
  const escala = Math.max(esquerda.escala, direita.escala);
  const valor =
    esquerda.valor * 10n ** BigInt(escala - esquerda.escala) +
    direita.valor * 10n ** BigInt(escala - direita.escala);
  return escrever({ valor, escala });
}

/** `a - b` exato, ou `null` quando um dos dois não é decimal legível. */
export function subtrairExato(a: string, b: string): string | null {
  const direita = paraFracao(b);
  if (direita === null) {
    return null;
  }
  return somarExato(a, escrever({ valor: -direita.valor, escala: direita.escala }));
}

/** O efeito com sinal, em pt-BR: "+120,00", "-83,86". Só pontuação — nenhuma conta. */
export function efeitoEmPtBr(efeito: string): string {
  const negativo = efeito.trim().startsWith("-");
  const modulo = efeito.trim().replace(/^[+-]/, "");
  return `${negativo ? "-" : "+"}${formatDecimalText(modulo)}`;
}

/** O delta como o servidor o lerá: sinal explícito, ponto decimal, sem espaço. */
function efeitoCanonico(texto: string): string | null {
  const fracao = paraFracao(texto);
  if (fracao === null) {
    return null;
  }
  const escrito = escrever(fracao);
  return escrito.startsWith("-") ? escrito : `+${escrito}`;
}

/**
 * O que a abertura da medição seguinte já sabe sem perguntar nada (decisões 1 e 2 do pacote).
 *
 * O período NÃO é digitado: é o da rodada anterior mais um. O rótulo nasce preenchido porque
 * é texto de planilha, e continua editável — ele é copy da prefeitura, não número do contrato.
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
 * Quanto cada código foi medido no período aprovado da rodada anterior.
 *
 * Espelha o que o servidor faz em `_origin_from_previous_round`: soma as linhas de TODAS as
 * obras do boletim, porque uma rodada pode medir mais de uma praça e o consolidado é por
 * código. Código ausente do boletim não entra — ausência é zero, e quem lê a herança recebe
 * "0,00" da própria montagem, não daqui.
 */
export function medidoPorCodigo(bulletin: BulletinResponse | null): Record<string, string> {
  const medido: Record<string, string> = {};
  if (bulletin === null) {
    return medido;
  }
  for (const obra of bulletin.valuation.bulletins) {
    for (const linha of obra.lines) {
      const anterior = medido[linha.code];
      const soma = anterior === undefined ? linha.quantity : somarExato(anterior, linha.quantity);
      if (soma !== null) {
        medido[linha.code] = soma;
      }
    }
  }
  return medido;
}

/** Uma linha do que vem da rodada anterior, código a código (estado 02 do pacote). */
export type LinhaHerdada = {
  code: string;
  itemNumber: string;
  description: string;
  unit: string;
  /** Preço unitário VIGENTE na rodada anterior; `null` quando a leitura não trouxe preços. */
  unitPrice: string | null;
  contratado: string;
  vigente: string;
  medidoNoPeriodo: string;
  /** Acumulado da rodada `n+1`: o da anterior mais o período que ela mediu. */
  acumulado: string | null;
  /** Saldo da rodada `n+1`: vigente menos o acumulado acima. */
  saldo: string | null;
  reRatificada: boolean;
};

/**
 * A herança da rodada anterior, como a rodada `n+1` a receberá.
 *
 * Duas contas, e as duas são identidades do domínio, não invenções da tela:
 *
 * - o acumulado que a rodada anterior tinha é `vigente − saldo` (é a definição de
 *   `ContractWorkbook.current_balance_quantity`), e o da rodada seguinte soma a ele o que foi
 *   medido no período aprovado (é o que `build_next_round_contract` faz);
 * - o saldo da rodada seguinte é `vigente − acumulado`, pela mesma definição.
 *
 * Sem RE-RA, contratado e vigente repetem o mesmo número **de propósito** (decisão 4 do pacote
 * aprovado): é o que faz a diferença aparecer no dia em que ela existir.
 */
export function herancaDaRodadaAnterior(
  quantities: RoundContractedQuantity[],
  prices: RoundContractedPrice[],
  medido: Record<string, string>,
): LinhaHerdada[] {
  const precoPorCodigo = new Map(prices.map((preco) => [preco.code, preco.current_unit_price]));
  return quantities.map((quantidade) => {
    const medidoNoPeriodo = medido[quantidade.code] ?? "0.00";
    const acumuladoAnterior = subtrairExato(
      quantidade.current_quantity,
      quantidade.current_balance_quantity,
    );
    const acumulado =
      acumuladoAnterior === null ? null : somarExato(acumuladoAnterior, medidoNoPeriodo);
    return {
      code: quantidade.code,
      itemNumber: quantidade.item_number,
      description: quantidade.description,
      unit: quantidade.unit,
      unitPrice: precoPorCodigo.get(quantidade.code) ?? null,
      contratado: quantidade.contracted_quantity,
      vigente: quantidade.current_quantity,
      medidoNoPeriodo,
      acumulado,
      saldo: acumulado === null ? null : subtrairExato(quantidade.current_quantity, acumulado),
      reRatificada: quantidade.re_ratified,
    };
  });
}

/** Uma linha da prévia: contratado → efeito → vigente → saldo novo (estado 04 do pacote). */
export type LinhaDaPrevia = {
  code: string;
  description: string;
  unit: string;
  unitPrice: string | null;
  /** O código não existe no consolidado herdado: a linha nasce com esta RE-RA. */
  itemNovo: boolean;
  /** Item novo cuja descrição, unidade e preço ainda não foram resolvidos no catálogo. */
  pendente: boolean;
  contratado: string;
  vigenteHoje: string;
  /** O delta como declarado, com sinal explícito. */
  efeito: string;
  vigenteNovo: string | null;
  acumulado: string;
  saldoNovo: string | null;
};

/**
 * Os códigos que a declaração cita e que NÃO existem no consolidado herdado.
 *
 * São exatamente os que precisam ser resolvidos no catálogo contratual da rodada anterior
 * (ADR-0056, decisão 7): sem descrição, unidade e preço, a linha não tem de onde nascer, e o
 * servidor recusaria com `AMENDMENT_NEW_ITEM_CODE_MISSING`.
 */
export function codigosParaResolver(
  draft: AmendmentDraft | null,
  heranca: LinhaHerdada[],
): string[] {
  if (draft === null) {
    return [];
  }
  const herdados = new Set(heranca.map((linha) => linha.code));
  const novos: string[] = [];
  for (const linha of draft.lines) {
    const code = linha.code.trim();
    if (code.length > 0 && !herdados.has(code) && !novos.includes(code)) {
      novos.push(code);
    }
  }
  return novos;
}

/**
 * A prévia do efeito da RE-RA sobre a herança, antes de gravar.
 *
 * O vigente **não é digitado**: ele é `vigente hoje + efeito declarado`, e é por isso que não
 * existe campo onde escrevê-lo (decisão 6 do pacote). O saldo novo é `vigente novo − acumulado`
 * — o acumulado não se move, porque período já medido não é reescrito (ADR-0055, decisão 6).
 *
 * A coluna "vigente hoje" é acréscimo consciente às sete colunas do mock: sem ela, um
 * consolidado que já chega re-ratificado da rodada anterior faria a conta `contratado + efeito`
 * parecer errada. Sem RE-RA anterior ela repete o contratado, que é o mesmo propósito da
 * decisão 4.
 */
export function previaDaReRa(
  heranca: LinhaHerdada[],
  draft: AmendmentDraft | null,
  catalogo: Record<string, CatalogSearchResult | null>,
): LinhaDaPrevia[] {
  if (draft === null) {
    return [];
  }
  const herdadaPorCodigo = new Map(heranca.map((linha) => [linha.code, linha]));
  const linhas: LinhaDaPrevia[] = [];
  for (const declarada of draft.lines) {
    const code = declarada.code.trim();
    const efeito = efeitoCanonico(declarada.quantityDelta);
    if (code.length === 0 || efeito === null) {
      continue;
    }
    const herdada = herdadaPorCodigo.get(code);
    if (herdada !== undefined) {
      const vigenteNovo = somarExato(herdada.vigente, efeito);
      const acumulado = herdada.acumulado ?? "0.00";
      linhas.push({
        code,
        description: herdada.description,
        unit: herdada.unit,
        unitPrice: herdada.unitPrice,
        itemNovo: false,
        pendente: false,
        contratado: herdada.contratado,
        vigenteHoje: herdada.vigente,
        efeito,
        vigenteNovo,
        acumulado,
        saldoNovo: vigenteNovo === null ? null : subtrairExato(vigenteNovo, acumulado),
      });
      continue;
    }
    // Item novo: a linha nasce zerada e o vigente É o delta (ADR-0056, decisão 7). Descrição,
    // unidade e preço vêm do catálogo contratual, e enquanto não vierem a linha é declarada
    // PENDENTE em vez de aparecer com campo em branco fingindo estar resolvida.
    const doCatalogo = catalogo[code] ?? null;
    const vigenteNovo = somarExato("0.00", efeito);
    linhas.push({
      code,
      description: doCatalogo?.description ?? "",
      unit: doCatalogo?.unit ?? "",
      unitPrice: doCatalogo?.unit_price ?? null,
      itemNovo: true,
      pendente: doCatalogo === null,
      contratado: "0.00",
      vigenteHoje: "0.00",
      efeito,
      vigenteNovo,
      acumulado: "0.00",
      saldoNovo: vigenteNovo,
    });
  }
  return linhas;
}
