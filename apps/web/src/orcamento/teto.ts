/**
 * Leitura do teto de verba da rodada (ADR-0040) — derivação pura, sem DOM e sem rede.
 *
 * A comparação é do SERVIDOR: `{target, consumed, remaining, over}` chega derivado a cada
 * leitura da rodada, e `over` é a única autoridade sobre o estouro (ADR-0040, decisão 3 —
 * limite exato NÃO é estouro). Este módulo não decide isso de novo; ele só arruma o que
 * chegou na forma que a tela mostra.
 *
 * **A tela nunca recomputa dinheiro.** Teto, consumo, restante e excedente saem daqui
 * exatamente como o servidor os escreveu: a única operação aplicada a um valor em reais é
 * tirar o sinal de menos do restante negativo, que é troca de notação, não conta. O ÚNICO
 * número calculado aqui é o percentual — e o Design Approval Package aprovado prevê os
 * dois caminhos para ele ("no servidor, junto do bloco, ou na tela, a partir dos dois
 * valores já truncados"), fixando só que dinheiro não se recalcula. O payload da rodada
 * não traz o percentual, então ele é calculado aqui.
 *
 * O percentual é razão, não dinheiro, e mesmo assim não passa por `float`: os dois lados
 * viram inteiros exatos (`BigInt`) e a divisão é truncada na segunda casa, como o domínio
 * trunca no centavo. Ele é informação SECUNDÁRIA — quem diz o estado é a palavra da
 * etiqueta, escrita a partir de `over`. Num consumo que passa o teto por uma fração
 * pequena demais para aparecer na segunda casa, o percentual mostra "100,00%" enquanto a
 * etiqueta diz "Teto estourado": a palavra é que vale, e é ela que vem primeiro na tela.
 */

import type { EstimateTargetState } from "./api";

/**
 * Estado do consumo. `dentro` e `limite` são o MESMO estado de domínio (ADR-0040,
 * decisão 3) e compartilham a veste; o que muda é a palavra, que no limite exato diz por
 * extenso que aquilo não é estouro.
 */
export type TetoEstado = "dentro" | "limite" | "estourado";

export type TetoDerivado = {
  estado: TetoEstado;
  /** Teto declarado, no texto decimal do servidor. */
  teto: string;
  /** Rótulo da demanda de origem; `null` quando a rodada não declarou nenhum. */
  rotulo: string | null;
  /** Consumo — o total COM BDI, no texto decimal do servidor. */
  consumo: string;
  /** Restante, sempre não negativo; `null` no estouro, onde a linha é o excedente. */
  restante: string | null;
  /** Quanto passou do teto, sem o sinal; `null` fora do estouro. */
  excedente: string | null;
  /** Percentual do teto já consumido, truncado na segunda casa; `null` se indivisível. */
  percentualConsumido: string | null;
  /** Percentual ACIMA do teto, truncado na segunda casa; `null` fora do estouro. */
  percentualAcima: string | null;
};

const DECIMAL_TEXT = /^-?\d+(\.\d+)?$/;

type DecimalExato = { valor: bigint; escala: number };

/**
 * Decimal em texto → inteiro exato com a escala em que ele foi escrito. Texto que não é
 * decimal simples devolve `null`: inventar um número para ele seria pior do que não
 * mostrar o percentual.
 */
function decimalExato(texto: string): DecimalExato | null {
  const limpo = texto.trim();
  if (!DECIMAL_TEXT.test(limpo)) {
    return null;
  }
  const negativo = limpo.startsWith("-");
  const semSinal = negativo ? limpo.slice(1) : limpo;
  const [inteiro, fracao = ""] = semSinal.split(".");
  const digitos = BigInt(inteiro + fracao);
  return { valor: negativo ? -digitos : digitos, escala: fracao.length };
}

/** `true` quando o decimal escrito vale zero, em qualquer escala ("0", "0.00", "-0.0"). */
export function ehZeroDecimal(texto: string): boolean {
  const exato = decimalExato(texto);
  return exato !== null && exato.valor === 0n;
}

/**
 * Valor absoluto de um decimal em TEXTO. Nenhuma conta: o sinal de menos é retirado da
 * string, e o número que o servidor escreveu continua dígito por dígito o mesmo.
 */
export function semSinal(texto: string): string {
  const limpo = texto.trim();
  return limpo.startsWith("-") ? limpo.slice(1) : limpo;
}

/**
 * `valor` sobre `teto` em percentual, truncado na segunda casa e devolvido na notação do
 * servidor ("96.83") — quem troca a pontuação para pt-BR é `format.ts`, como no resto da
 * jornada.
 *
 * Trunca, não arredonda, pelo mesmo motivo que o domínio trunca no centavo: mostrar uma
 * casa que ninguém escreveu é inventar precisão. Teto zero ou texto ilegível devolvem
 * `null`, e a tela omite o percentual em vez de mostrar um número fabricado.
 */
export function percentualDoTeto(valor: string, teto: string): string | null {
  const numerador = decimalExato(valor);
  const denominador = decimalExato(teto);
  if (numerador === null || denominador === null) {
    return null;
  }
  if (numerador.valor < 0n || denominador.valor <= 0n) {
    return null;
  }
  const escala = Math.max(numerador.escala, denominador.escala);
  const acima = numerador.valor * 10n ** BigInt(escala - numerador.escala);
  const abaixo = denominador.valor * 10n ** BigInt(escala - denominador.escala);
  // `× 10000` e não `× 100`: a divisão inteira do `BigInt` trunca, e as duas casas do
  // percentual precisam estar dentro do inteiro antes dela.
  const centesimos = (acima * 10000n) / abaixo;
  const inteiro = centesimos / 100n;
  const fracao = centesimos % 100n;
  return `${inteiro}.${String(fracao).padStart(2, "0")}`;
}

/**
 * Bloco do teto como a tela o mostra — ou `null`, que é "não há nada a mostrar".
 *
 * `null` cobre os dois casos em que a rodada não tem consumo a declarar: rodada SEM teto
 * (ADR-0040, decisão 6 — ausência de teto não é um estado a comunicar) e rodada com teto
 * cujo orçamento ainda não foi montado, onde o servidor manda só `target` porque o
 * consumo depende de um `total_amount` que ainda não existe.
 */
export function derivarTeto(
  bloco: EstimateTargetState | null | undefined,
): TetoDerivado | null {
  const alvo = bloco?.target;
  if (
    alvo === undefined ||
    bloco?.consumed === undefined ||
    bloco.remaining === undefined ||
    bloco.over === undefined
  ) {
    return null;
  }
  const estado: TetoEstado = bloco.over
    ? "estourado"
    : ehZeroDecimal(bloco.remaining)
      ? "limite"
      : "dentro";
  const excedente = estado === "estourado" ? semSinal(bloco.remaining) : null;
  return {
    estado,
    teto: alvo.amount,
    rotulo: alvo.label ?? null,
    consumo: bloco.consumed,
    restante: estado === "estourado" ? null : bloco.remaining,
    excedente,
    percentualConsumido: percentualDoTeto(bloco.consumed, alvo.amount),
    percentualAcima:
      excedente === null ? null : percentualDoTeto(excedente, alvo.amount),
  };
}
