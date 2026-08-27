/**
 * Rascunho da correção humana de forma (F-018), puro.
 *
 * Nada aqui grava, chama rede ou decide: o rascunho vive na tela até a pessoa gravá-lo, e
 * é o servidor que valida a forma resultante. A regra que este módulo carrega é a do
 * [ADR-0050](../../../docs/adr/0050-correcao-humana-de-forma-como-proposta-derivada.md):
 * a correção DERIVA de propostas observadas e nunca as substitui.
 *
 * O espaço é o da proposta — PIXELS da imagem fonte —, o mesmo do overlay que desenha as
 * formas sobre a prancha. Nenhuma conversão para metros acontece aqui: correção de forma
 * não promove precisão, e um número em metros no rascunho sugeriria o contrário.
 */

import type { VisionProposal } from "./api";

export type VerticeDaCorrecao = {
  x: number;
  y: number;
};

export type CorrecaoEmCurso = {
  /** Propostas observadas de que esta forma nasce; nunca vazio ao gravar. */
  derivedFrom: string[];
  vertices: VerticeDaCorrecao[];
  justificativa: string;
};

/** Piso de vértices: com menos de dois não há segmento, e sem segmento não há forma. */
export const MINIMO_DE_VERTICES = 2;

/** Teto do contrato de geometria (`PixelPolyline`), repetido para o excesso morrer na tela. */
export const MAXIMO_DE_VERTICES = 200;

/**
 * Os vértices de uma proposta, na ordem em que ela os declara.
 *
 * Círculo não entra: corrigir um círculo seria mexer em centro e raio, que não são
 * vértices, e inventar quatro pontos para ele produziria uma forma que ninguém desenhou.
 */
export function verticesDaProposta(proposal: VisionProposal): VerticeDaCorrecao[] | null {
  const geometry = proposal.geometry;
  if (geometry.type === "line") {
    return [
      { x: geometry.start.x, y: geometry.start.y },
      { x: geometry.end.x, y: geometry.end.y },
    ];
  }
  if (geometry.type === "polyline") {
    return geometry.points.map((ponto) => ({ x: ponto.x, y: ponto.y }));
  }
  return null;
}

/** `true` quando a proposta pode virar rascunho de correção. */
export function formaCorrigivel(proposal: VisionProposal): boolean {
  return verticesDaProposta(proposal) !== null;
}

/** Abre o rascunho a partir de UMA proposta observada. */
export function iniciarCorrecao(proposal: VisionProposal): CorrecaoEmCurso | null {
  const vertices = verticesDaProposta(proposal);
  if (vertices === null) {
    return null;
  }
  return { derivedFrom: [proposal.id], vertices, justificativa: "" };
}

/**
 * Acrescenta um fragmento ao rascunho: a união do caso Guaxindiba.
 *
 * Os vértices do fragmento entram na ponta MAIS PRÓXIMA da forma em curso, e invertidos
 * quando é o fim dele que encosta — costurar pela ordem de clique produziria um zigue-zague
 * atravessando o desenho, que é exatamente o que a união existe para evitar. A forma
 * resultante segue sendo revista à mão: isto é ordem de partida, não geometria decidida.
 */
export function unirFragmento(
  correcao: CorrecaoEmCurso,
  proposal: VisionProposal,
): CorrecaoEmCurso {
  const novos = verticesDaProposta(proposal);
  if (novos === null || correcao.derivedFrom.includes(proposal.id)) {
    return correcao;
  }
  const inicio = correcao.vertices[0];
  const fim = correcao.vertices[correcao.vertices.length - 1];
  const candidatos: { vertices: VerticeDaCorrecao[]; distancia: number }[] = [
    { vertices: [...correcao.vertices, ...novos], distancia: distancia(fim, novos[0]) },
    {
      vertices: [...correcao.vertices, ...[...novos].reverse()],
      distancia: distancia(fim, novos[novos.length - 1]),
    },
    {
      vertices: [...[...novos].reverse(), ...correcao.vertices],
      distancia: distancia(inicio, novos[0]),
    },
    { vertices: [...novos, ...correcao.vertices], distancia: distancia(inicio, novos[novos.length - 1]) },
  ];
  const melhor = candidatos.reduce((atual, candidato) =>
    candidato.distancia < atual.distancia ? candidato : atual,
  );
  return {
    ...correcao,
    derivedFrom: [...correcao.derivedFrom, proposal.id],
    vertices: melhor.vertices.slice(0, MAXIMO_DE_VERTICES),
  };
}

function distancia(a: VerticeDaCorrecao, b: VerticeDaCorrecao): number {
  return Math.hypot(a.x - b.x, a.y - b.y);
}

/**
 * Tira uma proposta da derivação, e com ela os vértices que ela trouxe.
 *
 * Os vértices NÃO voltam ao estado original: a pessoa pode tê-los movido depois de unir, e
 * desfazer o movimento junto seria decidir por ela. O que a retirada garante é a regra do
 * ADR — a forma não pode continuar citando uma origem que não está mais no ato.
 */
export function removerDerivacao(
  correcao: CorrecaoEmCurso,
  proposalId: string,
): CorrecaoEmCurso {
  return {
    ...correcao,
    derivedFrom: correcao.derivedFrom.filter((item) => item !== proposalId),
  };
}

/** Move um vértice para a posição nova, em pixels da imagem fonte. */
export function moverVertice(
  correcao: CorrecaoEmCurso,
  indice: number,
  posicao: VerticeDaCorrecao,
): CorrecaoEmCurso {
  if (indice < 0 || indice >= correcao.vertices.length) {
    return correcao;
  }
  const vertices = [...correcao.vertices];
  vertices[indice] = { x: Math.max(posicao.x, 0), y: Math.max(posicao.y, 0) };
  return { ...correcao, vertices };
}

/** Insere um vértice no meio do segmento que começa em `indice`. */
export function inserirVertice(
  correcao: CorrecaoEmCurso,
  indice: number,
): CorrecaoEmCurso {
  if (
    indice < 0 ||
    indice >= correcao.vertices.length - 1 ||
    correcao.vertices.length >= MAXIMO_DE_VERTICES
  ) {
    return correcao;
  }
  const anterior = correcao.vertices[indice];
  const proximo = correcao.vertices[indice + 1];
  const meio = { x: (anterior.x + proximo.x) / 2, y: (anterior.y + proximo.y) / 2 };
  const vertices = [...correcao.vertices];
  vertices.splice(indice + 1, 0, meio);
  return { ...correcao, vertices };
}

/** Remove um vértice, respeitando o piso de dois. */
export function removerVertice(
  correcao: CorrecaoEmCurso,
  indice: number,
): CorrecaoEmCurso {
  if (
    correcao.vertices.length <= MINIMO_DE_VERTICES ||
    indice < 0 ||
    indice >= correcao.vertices.length
  ) {
    return correcao;
  }
  return {
    ...correcao,
    vertices: correcao.vertices.filter((_, posicao) => posicao !== indice),
  };
}

/**
 * `null` quando o rascunho pode ser gravado; senão a frase que a tela mostra.
 *
 * A recusa acontece na tela ANTES da rede pelo mesmo motivo do lote de decisões: quem
 * revisa lê uma frase em vez de um 422.
 */
export function correcaoIssue(correcao: CorrecaoEmCurso): string | null {
  if (correcao.derivedFrom.length === 0) {
    return (
      "Uma correção precisa citar ao menos uma forma observada de origem. Sem ela isto " +
      "não é correção, é desenho — e desenho é CAD, não revisão."
    );
  }
  if (correcao.vertices.length < MINIMO_DE_VERTICES) {
    return "Uma forma precisa de pelo menos dois vértices.";
  }
  if (correcao.vertices.length > MAXIMO_DE_VERTICES) {
    return `Uma forma comporta no máximo ${MAXIMO_DE_VERTICES} vértices.`;
  }
  if (correcao.justificativa.trim().length < 3) {
    return "Corrigir a forma é decisão de domínio: escreva a justificativa.";
  }
  return null;
}

/**
 * Propostas superadas: as citadas por alguma correção gravada.
 *
 * Derivado da derivação, nunca lido de um campo do fragmento (ADR-0050, decisão 4) — um
 * campo gravado que duplica esta relação acabaria discordando dela.
 */
export function propostasSuperadas(correcoes: VisionProposal[]): Set<string> {
  const superadas = new Set<string>();
  for (const correcao of correcoes) {
    for (const origem of correcao.derived_from ?? []) {
      superadas.add(origem);
    }
  }
  return superadas;
}
