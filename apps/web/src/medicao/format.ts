/**
 * Exibição pt-BR dos números da medição.
 *
 * Regra do FDD que este módulo existe para não quebrar: **a tela nunca mostra um total
 * que o sistema não recomputou**. Aqui não há soma, produto, arredondamento nem
 * `Number()`: o servidor manda `Decimal` como texto ("1234.50") e estas funções apenas
 * trocam a pontuação para a convenção pt-BR ("1.234,50"). Nenhuma casa decimal é
 * acrescentada ou removida — a escala escrita é dado, não formatação: "18.4" continua
 * "18,4" e "61.20" continua "61,20".
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
 * Quantidade escrita pelo revisor → texto que o servidor entende (`Decimal(str)`).
 *
 * A conversão é de **notação**, nunca de valor: nenhum dígito é acrescentado, removido ou
 * arredondado. Só três formas são aceitas — "18.40" (a do servidor), "18,40" e
 * "1.234,50" —, e qualquer outra coisa devolve `null` para a tela recusar em vez de
 * mandar um número que o revisor não escreveu. A tela mostra o resultado antes de enviar,
 * então a leitura de "18.400" (que o servidor lê como dezoito inteiros e quatrocentos
 * milésimos) é conferível por quem digitou.
 */
export function parseQuantityInput(value: string): string | null {
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

/** Data e hora da decisão em pt-BR; texto inválido volta como veio. */
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
