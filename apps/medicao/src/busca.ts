/**
 * Braço lexical da busca no catálogo: derivação pura de quando disparar a consulta e do
 * resumo em língua de obra do que voltou.
 *
 * Módulo puro de propósito: debounce e limiar de caracteres são regra de UX, não de rede,
 * e o resumo da resposta precisa ser testável sem DOM e sem servidor. Nada aqui decide
 * `arm` — a tela escolhe se fixa o léxico (`searchCatalog(..., { arm: "lexical" })`) ou
 * deixa o servidor tentar o híbrido; este módulo só lê o `matching` que voltou.
 */

import type { CatalogSearchResponse } from "./api";

/** Tempo de espera após a última tecla antes de disparar a busca. */
export const BUSCA_DEBOUNCE_MS = 300;

/** Abaixo deste tamanho a consulta não dispara: poucas letras trazem ruído demais. */
export const BUSCA_MIN_CARACTERES = 3;

/**
 * Consulta pronta para disparar, ou `null` quando ainda não vale a pena — texto vazio,
 * só espaço ou abaixo do limiar. O chamador decide o debounce; esta função só decide SE.
 */
export function consultaIncremental(query: string): string | null {
  const trimmed = query.trim();
  return trimmed.length < BUSCA_MIN_CARACTERES ? null : trimmed;
}

function itemPalavra(count: number): string {
  return count === 1 ? "item" : "itens";
}

function casaVerbo(count: number): string {
  return count === 1 ? "casa" : "casam";
}

/**
 * Frase de obra que resume a resposta da busca, em quatro ramos:
 *
 * 1. A página trouxe TODOS os itens que casaram por palavra (`results.length ===
 *    total_matches`): sem "mostrando", porque não sobrou nada de fora.
 * 2. O léxico casou mais do que a página mostra (`results.length < total_matches`):
 *    declara o corte, "mostrando os M mais relevantes".
 * 3. O híbrido acrescentou vizinhos SEM palavra em comum (`matching === "hybrid"` e
 *    `results.length > total_matches`): o total por palavra e o total da lista contam
 *    histórias diferentes, e a frase explica a diferença em vez de escondê-la.
 * 4. Singular correto em qualquer um dos ramos acima ("1 item do catálogo casa…"), nunca
 *    "1 itens".
 */
export function resumoDaBusca(result: CatalogSearchResponse): string {
  const termos = result.terms.join(", ");
  const total = result.total_matches;
  const mostrados = result.results.length;

  if (result.matching === "hybrid" && mostrados > total) {
    return (
      `${total} ${itemPalavra(total)} ${casaVerbo(total)} por palavra com ${termos}; a lista ` +
      `traz ${mostrados} resultados porque o braço semântico acrescenta vizinhos sem ` +
      "palavra em comum."
    );
  }
  if (mostrados < total) {
    return (
      `${total} ${itemPalavra(total)} do catálogo ${casaVerbo(total)} com ${termos}; ` +
      `mostrando os ${mostrados} mais relevantes.`
    );
  }
  return `${total} ${itemPalavra(total)} do catálogo ${casaVerbo(total)} com ${termos}.`;
}
