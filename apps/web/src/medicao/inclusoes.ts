/**
 * Leitura assistida da descrição do catálogo: o que o código diz que inclui ou não
 * inclui, em citação literal.
 *
 * A frase que decide a escolha do código está no meio da descrição em prosa —
 * "…inclusive compactação … e 'colchão' de areia para assentamento…", "exclusive
 * preparo de terreno", "Fornecimento e colocação." — e hoje ela só aparece espremida no
 * parágrafo corrido. Este módulo recorta esses trechos para virar chip de leitura de
 * relance, ao lado do parágrafo completo, que continua a fonte de verdade.
 *
 * Isto é **heurística textual declarada, para orientar a leitura**, na mesma família de
 * `execucao.ts`: ela não decide, não filtra, não ordena e não bloqueia nenhuma
 * confirmação. Toda `text` desta lista é um recorte literal da descrição — nunca
 * reescrita, resumida ou inferida. Quando nenhum marcador conhecido aparece, o
 * resultado é lista vazia: uma resposta honesta, não um palpite.
 *
 * Regras, na ordem em que são aplicadas:
 *
 * 1. Cada ocorrência de `inclusive <trecho>` vira `{kind:"inclui", text:"<trecho>"}`. O
 *    trecho vai do fim da palavra até `.`, `;`, o fim da descrição ou a próxima
 *    ocorrência de `inclusive`/`exclusive` — o que vier primeiro. Cobre múltiplas
 *    ocorrências na mesma descrição.
 * 2. Cada ocorrência de `exclusive <trecho>` vira `{kind:"nao_inclui", ...}`, com a
 *    mesma regra de corte.
 * 3. A frase `fornecimento e colocação` (qualquer caixa, com ou sem acento) vira
 *    `{kind:"inclui", text:"fornecimento e colocação"}` — rótulo fixo porque a frase é
 *    curta e sempre igual; não é um recorte de um trecho maior.
 * 4. A frase `com todos os materiais e equipamentos` vira `{kind:"inclui", text:
 *    <trecho literal>}`, extraído com a grafia exata da descrição.
 * 5. Quando `classifyExecucao` (de `execucao.ts`) lê a descrição como somente material,
 *    a lista ganha `{kind:"so_fornecimento"}` na primeira posição.
 * 6. O sufixo `(desonerado)` nunca entra em chip — é removido do fim de qualquer trecho
 *    capturado. Parêntese/colchete de fechamento solto no fim do trecho (a abertura
 *    ficou para trás, fora do recorte — ex.: "(inclusive encargos sociais)" recorta
 *    "encargos sociais)") também é removido; par completo dentro do trecho (ex.:
 *    "(NPK-04-14-08)") fica intacto. Chips repetidos (mesmo `kind` e mesmo texto,
 *    comparado sem acento e caixa) são descartados, mantendo a primeira ocorrência.
 * 7. Sem nenhum marcador conhecido, a lista é vazia; a tela não mostra a seção em vez de
 *    inventar uma leitura.
 */

import { classifyExecucao } from "./execucao";

export type Inclusao =
  | { kind: "inclui"; text: string }
  | { kind: "nao_inclui"; text: string }
  | { kind: "so_fornecimento" };

/** NFKD sem acento e em caixa baixa: mesma leitura usada em `execucao.ts`. */
function normalize(text: string): string {
  return text
    .normalize("NFKD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase();
}

/** Remove o sufixo "(desonerado)", em qualquer caixa, do fim do trecho capturado. */
function stripDesonerado(text: string): string {
  return text.replace(/\(\s*desonerado\s*\)\s*$/i, "").trim();
}

/** Fechamento (`)`/`]`) e sua abertura correspondente. */
const CLOSING_TO_OPENING: Readonly<Record<string, string>> = { ")": "(", "]": "[" };

/**
 * Remove parêntese/colchete de fechamento solto no fim do trecho — sobra de um recorte
 * que começou DEPOIS da abertura correspondente, fora do próprio trecho (ex.:
 * "(inclusive encargos sociais)" recorta "encargos sociais)": o "(" ficou para trás, o
 * ")" não). Só mexe na borda, e só quando o fechamento final não tem abertura par DENTRO
 * do trecho — pontuação interna e par completo (ex.: "(NPK-04-14-08)") ficam intactos.
 */
function stripDanglingClosing(text: string): string {
  let result = text;
  while (result.length > 0) {
    const last = result[result.length - 1];
    const opening = CLOSING_TO_OPENING[last];
    if (opening === undefined) {
      break;
    }
    const opens = result.split(opening).length - 1;
    const closes = result.split(last).length - 1;
    if (closes <= opens) {
      break;
    }
    result = result.slice(0, -1).trimEnd();
  }
  return result;
}

type ClauseMarker = "inclusive" | "exclusive";

/** Ocorrências de `inclusive`/`exclusive` como palavra inteira, na ordem do texto. */
function findClauseMarkers(
  description: string,
): { index: number; end: number; marker: ClauseMarker }[] {
  const matches: { index: number; end: number; marker: ClauseMarker }[] = [];
  const markerRegex = /\b(inclusive|exclusive)\b/gi;
  let match: RegExpExecArray | null;
  while ((match = markerRegex.exec(description)) !== null) {
    matches.push({
      index: match.index,
      end: match.index + match[0].length,
      marker: match[0].toLowerCase() as ClauseMarker,
    });
  }
  return matches;
}

/** Regras 1 e 2: um `inclui`/`nao_inclui` por ocorrência de `inclusive`/`exclusive`. */
function extractClauses(description: string): Inclusao[] {
  const markers = findClauseMarkers(description);
  const clauses: Inclusao[] = [];
  for (let position = 0; position < markers.length; position += 1) {
    const current = markers[position];
    const next = markers[position + 1];
    const boundaries = [description.length];
    if (next !== undefined) {
      boundaries.push(next.index);
    }
    const dotIndex = description.indexOf(".", current.end);
    if (dotIndex !== -1) {
      boundaries.push(dotIndex);
    }
    const semicolonIndex = description.indexOf(";", current.end);
    if (semicolonIndex !== -1) {
      boundaries.push(semicolonIndex);
    }
    const cut = Math.min(...boundaries);
    const text = stripDanglingClosing(
      stripDesonerado(description.slice(current.end, cut).trim()),
    );
    if (text.length === 0) {
      continue;
    }
    clauses.push(
      current.marker === "inclusive"
        ? { kind: "inclui", text }
        : { kind: "nao_inclui", text },
    );
  }
  return clauses;
}

/** Chave de dedupe: `so_fornecimento` é único por natureza; os demais por texto normalizado. */
function dedupeKey(item: Inclusao): string {
  return item.kind === "so_fornecimento" ? "so_fornecimento" : `${item.kind}:${normalize(item.text)}`;
}

function dedupe(items: Inclusao[]): Inclusao[] {
  const seen = new Set<string>();
  const result: Inclusao[] = [];
  for (const item of items) {
    const key = dedupeKey(item);
    if (seen.has(key)) {
      continue;
    }
    seen.add(key);
    result.push(item);
  }
  return result;
}

export function extractInclusoes(description: string): Inclusao[] {
  const items: Inclusao[] = [];

  // Regra 5: somente material vai no início, quando a heurística de execução assim lê.
  if (classifyExecucao(description).kind === "somente_material") {
    items.push({ kind: "so_fornecimento" });
  }

  // Regras 1 e 2: cláusulas de inclusive/exclusive, na ordem em que aparecem.
  items.push(...extractClauses(description));

  // Regra 3: rótulo fixo, independente de caixa ou acento na descrição.
  if (normalize(description).includes("fornecimento e colocacao")) {
    items.push({ kind: "inclui", text: "fornecimento e colocação" });
  }

  // Regra 4: trecho literal, com a grafia exata encontrada na descrição.
  const materiaisMatch = /com todos os materiais e equipamentos/i.exec(description);
  if (materiaisMatch !== null) {
    items.push({ kind: "inclui", text: materiaisMatch[0] });
  }

  return dedupe(items);
}
