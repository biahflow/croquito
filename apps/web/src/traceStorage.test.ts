import { describe, expect, it } from "vitest";

import { emptyTraceDraft, type TraceDraft } from "./trace";
import {
  parseTraceDraft,
  serializeTraceDraft,
  traceDraftStorageKey,
} from "./traceStorage";

function draft(overrides: Partial<TraceDraft> = {}): TraceDraft {
  return { ...emptyTraceDraft(), ...overrides };
}

const allPending = new Set(["vp_a", "vp_b", "vp_c"]);

describe("chave do rascunho", () => {
  it("é por job", () => {
    expect(traceDraftStorageKey("job-1")).toBe(
      "croquitodxf:trace-draft:job-1",
    );
  });
});

describe("ida e volta do rascunho", () => {
  it("preserva declarações, marcações e amarrações", () => {
    const original = draft({
      proposalIds: ["vp_a", "vp_b"],
      hatch: new Set(["vp_a"]),
      unlabelled: new Set(["vp_b"]),
      freeform: new Set(["vp_a"]),
      keepApartPairs: [{ first: "vp_a", second: "vp_b", axis: null }],
      detailGroups: [
        {
          detailId: "A",
          title: "Painel de alambrado",
          proposalIds: ["vp_b"],
          mode: "sketch",
        },
      ],
      associations: {
        rd_1: { kind: "pair", proposalIds: ["vp_a", "vp_b"] },
        rd_2: {
          kind: "declared",
          proposalId: "vp_a",
          spansPx: [
            [
              [10, 20],
              [30, 40],
            ],
          ],
        },
        rd_3: { kind: "single", proposalId: "vp_c" },
      },
      noteTargets: { rd_4: "vp_a#v", rd_5: "carimbo" },
      derivedDimensions: [
        { proposalId: "vp_b", nearXPx: 12, nearYPx: 34, text: "3,60 x 3,90" },
      ],
      dimensionTexts: { rd_1: "1,0 x 2,05" },
      note: "Aceite do lote da planta",
      title: "Campo do Guaxindiba",
    });

    const restored = parseTraceDraft(
      serializeTraceDraft(original, new Set(["vp_a", "vp_b"])),
      allPending,
    );

    expect(restored).not.toBeNull();
    expect(restored?.batchIds).toEqual(["vp_a", "vp_b"]);
    expect(restored?.declarations).toEqual(original);
  });

  it("rascunho vazio volta vazio", () => {
    const restored = parseTraceDraft(
      serializeTraceDraft(emptyTraceDraft(), new Set()),
      allPending,
    );

    expect(restored?.declarations).toEqual(emptyTraceDraft());
    expect(restored?.batchIds).toEqual([]);
  });

  it("cota derivada sem texto não ganha campo de texto na volta", () => {
    const restored = parseTraceDraft(
      serializeTraceDraft(
        draft({ derivedDimensions: [{ proposalId: "vp_a", nearXPx: 1, nearYPx: 2 }] }),
        new Set(),
      ),
      allPending,
    );

    expect(restored?.declarations.derivedDimensions).toEqual([
      { proposalId: "vp_a", nearXPx: 1, nearYPx: 2 },
    ]);
  });
});

describe("formas já decididas", () => {
  it("saem do lote e da lista de aceite, porque decisão registrada é imutável", () => {
    const stored = serializeTraceDraft(
      draft({ proposalIds: ["vp_a", "vp_b"] }),
      new Set(["vp_a", "vp_b"]),
    );

    const restored = parseTraceDraft(stored, new Set(["vp_b"]));

    expect(restored?.batchIds).toEqual(["vp_b"]);
    expect(restored?.declarations.proposalIds).toEqual(["vp_b"]);
  });

  it("a amarração da forma decidida volta como está, para a pré-validação acusar", () => {
    const stored = serializeTraceDraft(
      draft({
        proposalIds: ["vp_a"],
        associations: { rd_1: { kind: "single", proposalId: "vp_a" } },
      }),
      new Set(["vp_a"]),
    );

    const restored = parseTraceDraft(stored, new Set());

    expect(restored?.batchIds).toEqual([]);
    expect(restored?.declarations.associations).toEqual({
      rd_1: { kind: "single", proposalId: "vp_a" },
    });
  });
});

describe("eixo do par manter-separados", () => {
  it("migra a tupla antiga (rascunho de usuário real) para axis: null", () => {
    const restored = parseTraceDraft(
      JSON.stringify({ keepApartPairs: [["vp_a", "vp_b"]] }),
      allPending,
    );

    expect(restored?.declarations.keepApartPairs).toEqual([
      { first: "vp_a", second: "vp_b", axis: null },
    ]);
  });

  it("aceita o formato objeto com eixo x ou y validado", () => {
    const restored = parseTraceDraft(
      JSON.stringify({
        keepApartPairs: [
          { first: "vp_a", second: "vp_b", axis: "x" },
          { first: "vp_c", second: "vp_d", axis: "y" },
        ],
      }),
      allPending,
    );

    expect(restored?.declarations.keepApartPairs).toEqual([
      { first: "vp_a", second: "vp_b", axis: "x" },
      { first: "vp_c", second: "vp_d", axis: "y" },
    ]);
  });

  it("eixo fora de x/y/null descarta só o par, não o rascunho inteiro", () => {
    const restored = parseTraceDraft(
      JSON.stringify({
        keepApartPairs: [
          { first: "vp_a", second: "vp_b", axis: "z" },
          { first: "vp_c", second: "vp_d", axis: "x" },
        ],
      }),
      allPending,
    );

    expect(restored?.declarations.keepApartPairs).toEqual([
      { first: "vp_c", second: "vp_d", axis: "x" },
    ]);
  });

  it("ida e volta do formato novo preserva o eixo declarado", () => {
    const original = draft({
      keepApartPairs: [
        { first: "vp_a", second: "vp_b", axis: "x" },
        { first: "vp_c", second: "vp_d", axis: null },
      ],
    });

    const restored = parseTraceDraft(
      serializeTraceDraft(original, new Set()),
      allPending,
    );

    expect(restored?.declarations.keepApartPairs).toEqual(
      original.keepApartPairs,
    );
  });
});

describe("conteúdo corrompido", () => {
  it("JSON inválido não restaura nada", () => {
    expect(parseTraceDraft("{", allPending)).toBeNull();
    expect(parseTraceDraft("[]", allPending)).toBeNull();
    expect(parseTraceDraft('"texto"', allPending)).toBeNull();
  });

  it("campo com tipo errado volta ao valor vazio em vez de contaminar o rascunho", () => {
    const restored = parseTraceDraft(
      JSON.stringify({
        batchIds: "vp_a",
        hatch: [1, 2],
        keepApartPairs: [["vp_a"], ["vp_a", "vp_b"]],
        detailGroups: [{ detailId: "A", title: "Sem modo" }],
        noteTargets: { rd_1: 7, rd_2: "carimbo" },
        dimensionTexts: { rd_1: "1,0 x 2,05" },
        note: 42,
        title: null,
      }),
      allPending,
    );

    expect(restored?.batchIds).toEqual([]);
    expect(restored?.declarations.hatch.size).toBe(0);
    expect(restored?.declarations.keepApartPairs).toEqual([
      { first: "vp_a", second: "vp_b", axis: null },
    ]);
    expect(restored?.declarations.detailGroups).toEqual([]);
    expect(restored?.declarations.noteTargets).toEqual({ rd_2: "carimbo" });
    expect(restored?.declarations.dimensionTexts).toEqual({
      rd_1: "1,0 x 2,05",
    });
    expect(restored?.declarations.note).toBe("");
    expect(restored?.declarations.title).toBe("");
  });

  it("alvo de vão malformado é descartado inteiro", () => {
    const restored = parseTraceDraft(
      JSON.stringify({
        associations: {
          rd_1: { kind: "triple", proposalIds: ["vp_a", "vp_b", "vp_c"] },
          rd_2: { kind: "pair", proposalIds: ["vp_a"] },
          rd_3: { kind: "single", proposalId: "vp_a" },
          rd_4: {
            kind: "declared",
            proposalId: "vp_a",
            spansPx: [[[1, 2]], [[1, 2], [3, 4]]],
          },
        },
      }),
      allPending,
    );

    expect(restored?.declarations.associations).toEqual({
      rd_3: { kind: "single", proposalId: "vp_a" },
      rd_4: {
        kind: "declared",
        proposalId: "vp_a",
        spansPx: [
          [
            [1, 2],
            [3, 4],
          ],
        ],
      },
    });
  });

  it("cota derivada sem ponto numérico é descartada", () => {
    const restored = parseTraceDraft(
      JSON.stringify({
        derivedDimensions: [
          { proposalId: "vp_a", nearXPx: "12", nearYPx: 34 },
          { proposalId: "vp_b", nearXPx: 12, nearYPx: 34 },
        ],
      }),
      allPending,
    );

    expect(restored?.declarations.derivedDimensions).toEqual([
      { proposalId: "vp_b", nearXPx: 12, nearYPx: 34 },
    ]);
  });
});
