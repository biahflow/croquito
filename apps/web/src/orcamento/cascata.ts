/**
 * A ordem da cascata como gesto: subir e descer uma fonte, e a lista completa de digests
 * que o servidor recebe.
 *
 * A rota de reordenação (`POST .../catalogs/order`) exige a **permutação completa** da
 * cascata instalada — acrescentar, remover ou repetir fonte por ali seria instalar
 * catálogo por uma porta que não lê nem valida catálogo nenhum. Este módulo é onde essa
 * regra fica testável sem transporte: ele só troca duas posições vizinhas e devolve a
 * lista inteira, na ordem nova.
 *
 * Nenhuma ordem é inventada: o movimento é de uma posição, pedido por clique, e a fonte
 * do topo não sobe nem a do fim desce.
 */

import type { CascadeEntry } from "./api";

export type CascadeMove = "up" | "down";

/**
 * A cascata na ordem nova, por `source_sha256`, ou `null` quando o movimento não existe
 * (primeira subindo, última descendo, digest fora da cascata). `null` é "nada a pedir",
 * e não uma ordem parcial que o servidor teria de completar por conta própria.
 */
export function reorderedDigests(
  entries: readonly CascadeEntry[],
  sourceSha256: string,
  move: CascadeMove,
): string[] | null {
  const digests = entries.map((entry) => entry.source_sha256);
  const from = digests.indexOf(sourceSha256);
  if (from < 0) {
    return null;
  }
  const to = move === "up" ? from - 1 : from + 1;
  if (to < 0 || to >= digests.length) {
    return null;
  }
  const next = [...digests];
  [next[from], next[to]] = [next[to], next[from]];
  return next;
}

/** `true` quando o movimento existe — é o que decide o `disabled` de cada botão. */
export function canMove(
  entries: readonly CascadeEntry[],
  sourceSha256: string,
  move: CascadeMove,
): boolean {
  return reorderedDigests(entries, sourceSha256, move) !== null;
}

/**
 * A fonte da cascata que um candidato ou uma linha cita, ou `null` quando o digest não
 * está instalada nesta rodada.
 *
 * `null` é estado honesto e aparece na tela como tal: uma linha que cita catálogo fora da
 * cascata é exatamente o que `ESTIMATE_LINE_SOURCE_UNKNOWN` recusa, e fingir uma posição
 * aqui esconderia o defeito.
 */
export function entryOfDigest(
  entries: readonly CascadeEntry[],
  catalogSha256: string | null | undefined,
): CascadeEntry | null {
  if (!catalogSha256) {
    return null;
  }
  return (
    entries.find((entry) => entry.source_sha256 === catalogSha256) ?? null
  );
}
