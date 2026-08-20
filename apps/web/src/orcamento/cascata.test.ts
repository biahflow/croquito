import { describe, expect, it } from "vitest";

import type { CascadeEntry } from "./api";
import { canMove, entryOfDigest, reorderedDigests } from "./cascata";

const SCO = "a".repeat(64);
const EMOP = "b".repeat(64);
const COMPOSICAO = "c".repeat(64);

const CASCATA: CascadeEntry[] = [
  {
    position: 1,
    origin: "sco",
    source_sha256: SCO,
    reference_month: "2026-04",
    source_label: "SCO 04/2026",
    summary: {},
  },
  {
    position: 2,
    origin: "emop",
    source_sha256: EMOP,
    reference_month: "2026-07",
    source_label: "EMOP 07/2026",
    summary: {},
  },
  {
    position: 3,
    origin: "composition",
    source_sha256: COMPOSICAO,
    reference_month: "2026-08",
    source_label: "Composições próprias",
    summary: {},
  },
];

/**
 * A rota exige a PERMUTAÇÃO COMPLETA: um corpo parcial obrigaria o servidor a decidir
 * onde as fontes omitidas entram, e essa decisão é a que o ADR-0027 tira do código.
 */
describe("reordenação da cascata", () => {
  it("subir troca com a fonte de cima e devolve a lista inteira", () => {
    expect(reorderedDigests(CASCATA, EMOP, "up")).toEqual([EMOP, SCO, COMPOSICAO]);
  });

  it("descer troca com a fonte de baixo e devolve a lista inteira", () => {
    expect(reorderedDigests(CASCATA, SCO, "down")).toEqual([EMOP, SCO, COMPOSICAO]);
  });

  it("a lista nova é sempre uma permutação: mesmo conjunto, mesmo tamanho", () => {
    const nova = reorderedDigests(CASCATA, COMPOSICAO, "up");

    expect(nova).not.toBeNull();
    expect(nova).toHaveLength(CASCATA.length);
    expect([...(nova ?? [])].sort()).toEqual(
      CASCATA.map((entry) => entry.source_sha256).sort(),
    );
  });

  it("movimento que não existe devolve null, e não uma ordem parcial", () => {
    expect(reorderedDigests(CASCATA, SCO, "up")).toBeNull();
    expect(reorderedDigests(CASCATA, COMPOSICAO, "down")).toBeNull();
    expect(reorderedDigests(CASCATA, "d".repeat(64), "up")).toBeNull();
    expect(reorderedDigests([], SCO, "up")).toBeNull();
  });

  it("`canMove` é o mesmo julgamento, e é ele que desabilita o botão", () => {
    expect(canMove(CASCATA, SCO, "up")).toBe(false);
    expect(canMove(CASCATA, SCO, "down")).toBe(true);
    expect(canMove(CASCATA, COMPOSICAO, "down")).toBe(false);
  });
});

/**
 * A fonte que um candidato ou uma linha cita. `null` é estado honesto: um digest fora da
 * cascata é exatamente o que `ESTIMATE_LINE_SOURCE_UNKNOWN` recusa, e fingir uma posição
 * aqui esconderia o defeito.
 */
describe("fonte citada por digest", () => {
  it("acha a fonte instalada, com a posição que ela ocupa", () => {
    expect(entryOfDigest(CASCATA, EMOP)?.position).toBe(2);
    expect(entryOfDigest(CASCATA, EMOP)?.origin).toBe("emop");
  });

  it("digest fora da cascata, ausente ou vazio devolve null", () => {
    expect(entryOfDigest(CASCATA, "d".repeat(64))).toBeNull();
    expect(entryOfDigest(CASCATA, null)).toBeNull();
    expect(entryOfDigest(CASCATA, undefined)).toBeNull();
    expect(entryOfDigest(CASCATA, "")).toBeNull();
  });
});
