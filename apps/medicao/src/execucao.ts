/**
 * Leitura assistida da descrição do catálogo: o código inclui a execução ou é só material?
 *
 * O catálogo público escreve isso em prosa, no fim da descrição: "Fornecimento e
 * colocação." inclui a mão de obra, "Fornecimento." não inclui, e as composições de
 * serviço começam por "Execução de …". Dois códigos com a mesma descrição técnica e
 * finais diferentes têm preços muito distintos, e escolher o errado é medir serviço que
 * não foi contratado — ou deixar de medir o que foi.
 *
 * Isto é **heurística textual declarada, para orientar a leitura**: um marcador na frase,
 * nada mais. Ela não decide, não filtra, não ordena e não bloqueia nenhuma confirmação —
 * quem decide é a orçamentista, lendo a descrição completa que a tela mostra ao lado.
 * Quando a frase não tem marcador conhecido, o resultado é `indefinido`, que é uma
 * resposta honesta e não um palpite.
 */

export type ExecucaoKind = "execucao_incluida" | "somente_material" | "indefinido";

export type ExecucaoHint = {
  kind: ExecucaoKind;
  /** Texto curto do selo mostrado no cartão do código. */
  label: string;
  /** Frase que explica a leitura e assume a heurística, exibida no `title` do selo. */
  explanation: string;
  /** Marcador que produziu a classificação; `null` quando nenhum foi encontrado. */
  marker: string | null;
};

/**
 * Marcadores de execução incluída, na ordem em que são procurados. A lista é o contrato
 * desta heurística: crescer a lista é mudar o que a tela afirma, e por isso ela é
 * explícita em vez de uma expressão regular esperta.
 */
export const EXECUCAO_MARKERS: readonly string[] = [
  "fornecimento e colocacao",
  "fornecimento e instalacao",
  "fornecimento e assentamento",
  "fornecimento e plantio",
  "execucao de",
  "plantio",
  "inclusive",
];

/** Marcadores de fornecimento puro; só valem quando nenhum marcador de execução aparece. */
export const MATERIAL_MARKERS: readonly string[] = ["fornecimento"];

/** NFKD sem acento e em caixa baixa: a mesma leitura que o servidor faz do catálogo. */
function normalize(text: string): string {
  return text
    .normalize("NFKD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase();
}

export function classifyExecucao(description: string): ExecucaoHint {
  const text = normalize(description);
  const execucao = EXECUCAO_MARKERS.find((marker) => text.includes(marker));
  if (execucao !== undefined) {
    return {
      kind: "execucao_incluida",
      label: "execução incluída",
      explanation:
        `Leitura da descrição: ela contém "${execucao}", que costuma indicar mão de obra` +
        " incluída. É uma dica de leitura da frase — confira a descrição completa; a decisão é sua.",
      marker: execucao,
    };
  }
  const material = MATERIAL_MARKERS.find((marker) => text.includes(marker));
  if (material !== undefined) {
    return {
      kind: "somente_material",
      label: "somente material",
      explanation:
        `Leitura da descrição: ela diz "${material}" e não traz marcador de execução,` +
        " o que costuma indicar material sem mão de obra. É uma dica de leitura da frase" +
        " — confira a descrição completa; a decisão é sua.",
      marker: material,
    };
  }
  return {
    kind: "indefinido",
    label: "escopo não declarado",
    explanation:
      "A descrição não traz marcador conhecido de fornecimento ou de execução; leia a" +
      " descrição completa para decidir o que o código cobre.",
    marker: null,
  };
}
