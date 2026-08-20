/**
 * Exibição pt-BR dos números do orçamento-base.
 *
 * **Cópia deliberada de `medicao/format.ts`, não import.** A regra da casa é que as
 * jornadas só compartilham o transporte (`../api`) e nunca se importam entre si — é o
 * mesmo precedente de `formatarInstante` em `plataforma/api.ts`. Se as duas folhas
 * divergirem, é porque uma decisão de produto separou os dois momentos, e não porque uma
 * ficou para trás sem que ninguém percebesse.
 *
 * A regra que este módulo existe para não quebrar é a mesma: **a tela nunca mostra um
 * número que o servidor não recomputou**. Aqui não há soma, produto, arredondamento nem
 * `Number()` — o servidor manda `Decimal` como texto ("1234.50") e estas funções apenas
 * trocam a pontuação para a convenção pt-BR ("1.234,50"). Nenhuma casa decimal é
 * acrescentada ou removida: a escala escrita é dado, não formatação.
 *
 * Texto que não é um decimal simples volta como veio. Inventar um número para ele seria
 * pior do que mostrar o que o servidor mandou.
 */

const DECIMAL_TEXT = /^-?\d+(\.\d+)?$/;

function groupThousands(digits: string): string {
  let grouped = "";
  for (let index = digits.length; index > 0; index -= 3) {
    const start = Math.max(0, index - 3);
    grouped = digits.slice(start, index) + (grouped ? "." + grouped : "");
  }
  return grouped;
}

/** "1234.50" → "1.234,50"; "18.4" → "18,4"; "7" → "7". */
export function formatDecimalText(value: string): string {
  const text = value.trim();
  if (!DECIMAL_TEXT.test(text)) {
    return text;
  }
  const negative = text.startsWith("-");
  const unsigned = negative ? text.slice(1) : text;
  const [whole, fraction] = unsigned.split(".");
  const formatted =
    groupThousands(whole) + (fraction === undefined ? "" : `,${fraction}`);
  return negative ? `-${formatted}` : formatted;
}

/** Dinheiro: o mesmo texto do servidor, com o símbolo na frente. */
export function formatMoneyText(value: string): string {
  return `R$ ${formatDecimalText(value)}`;
}

/** Percentual do BDI como o servidor o gravou; nenhuma casa é acrescentada. */
export function formatPercentText(value: string): string {
  return `${formatDecimalText(value)}%`;
}

/**
 * Quantidade com unidade. Quantidade ausente é a linha ambígua — ela aparece como
 * "sem quantidade legível", nunca como zero.
 */
export function formatQuantityText(
  value: string | null,
  unitLabel: string,
): string {
  if (value === null) {
    return "sem quantidade legível";
  }
  return `${formatDecimalText(value)} ${unitLabel}`;
}

const PT_BR_DECIMAL = /^\d+,\d+$/;
const PT_BR_GROUPED = /^\d{1,3}(\.\d{3})+,\d+$/;
const SERVER_DECIMAL = /^\d+(\.\d+)?$/;

/**
 * Decimal escrito pela orçamentista → texto que o servidor entende (`Decimal(str)`).
 *
 * Vale para os dois decimais que esta jornada digita: a quantidade do takeoff e o
 * percentual de BDI. A conversão é de **notação**, nunca de valor — nenhum dígito é
 * acrescentado, removido ou arredondado, e nada vira `number` no caminho, porque um
 * `float` de JSON já teria passado por binário antes de chegar à rota (ADR-0038,
 * decisão 2). Só três formas são aceitas: "25.00" (a do servidor), "25,00" e "1.234,50";
 * qualquer outra devolve `null` para a tela recusar em vez de mandar um número que
 * ninguém escreveu.
 */
export function parseDecimalInput(value: string): string | null {
  const text = value.trim();
  if (text.length === 0) {
    return null;
  }
  if (SERVER_DECIMAL.test(text)) {
    return text;
  }
  if (PT_BR_DECIMAL.test(text)) {
    return text.replace(",", ".");
  }
  if (PT_BR_GROUPED.test(text)) {
    return text.replaceAll(".", "").replace(",", ".");
  }
  return null;
}

/** Digest curto para conferência visual; o valor inteiro fica no `title` de quem chama. */
export function shortDigest(digest: string | null | undefined): string {
  if (!digest) {
    return "—";
  }
  return digest.slice(0, 12);
}

/** Data e hora em pt-BR; texto inválido volta como veio. */
export function formatTimestamp(value: string): string {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return value;
  }
  const pad = (part: number) => String(part).padStart(2, "0");
  return (
    `${pad(parsed.getDate())}/${pad(parsed.getMonth() + 1)}/${parsed.getFullYear()}` +
    ` ${pad(parsed.getHours())}:${pad(parsed.getMinutes())}`
  );
}
