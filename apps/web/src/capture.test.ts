import { describe, expect, it } from "vitest";

import type { Review } from "./api";
import {
  applyCaptureCommit,
  captureExpectsPoint,
  captureHint,
  captureReadingId,
  formatNoteTarget,
  IDLE_CAPTURE,
  parseNoteTarget,
  proposalCentrePx,
  reduceCapture,
  type CaptureCommit,
  type CaptureState,
} from "./capture";
import { buildTraceSolveRequest, emptyTraceDraft, type TraceDraft } from "./trace";

/** Encadeia eventos como o palco encadeia cliques; devolve o último resultado. */
function run(
  state: CaptureState,
  ...events: Parameters<typeof reduceCapture>[1][]
): ReturnType<typeof reduceCapture> {
  let result = reduceCapture(state, events[0]);
  for (const event of events.slice(1)) {
    result = reduceCapture(result.state, event);
  }
  return result;
}

const shape = (proposalId: string) =>
  ({ type: "shape", proposalId }) as const;
const point = (xPx: number, yPx: number) =>
  ({ type: "point", xPx, yPx }) as const;
const cancel = { type: "cancel" } as const;

describe("captura de vão em par", () => {
  it("fecha o vão com duas formas distintas e volta ao repouso", () => {
    const result = run(
      { kind: "pair", readingId: "rd_1", firstProposalId: null },
      shape("vp_a"),
      shape("vp_b"),
    );

    expect(result.state).toEqual(IDLE_CAPTURE);
    expect(result.commit).toEqual({
      kind: "span",
      readingId: "rd_1",
      target: { kind: "pair", proposalIds: ["vp_a", "vp_b"] },
    });
  });

  it("guarda a primeira forma sem concluir e pede a segunda", () => {
    const result = reduceCapture(
      { kind: "pair", readingId: "rd_1", firstProposalId: null },
      shape("vp_a"),
    );

    expect(result.state).toEqual({
      kind: "pair",
      readingId: "rd_1",
      firstProposalId: "vp_a",
    });
    expect(result.commit).toBeUndefined();
    expect(result.hint).toContain("segunda forma");
  });

  it("clicar duas vezes na mesma forma não conclui e continua pedindo outra", () => {
    const result = run(
      { kind: "pair", readingId: "rd_1", firstProposalId: null },
      shape("vp_a"),
      shape("vp_a"),
    );

    expect(result.state).toEqual({
      kind: "pair",
      readingId: "rd_1",
      firstProposalId: "vp_a",
    });
    expect(result.commit).toBeUndefined();
    expect(result.hint).toContain("não a mesma de novo");
  });

  it("clique em ponto não muda o estado do par", () => {
    const state: CaptureState = {
      kind: "pair",
      readingId: "rd_1",
      firstProposalId: "vp_a",
    };

    const result = reduceCapture(state, point(10, 20));

    expect(result.state).toBe(state);
    expect(result.commit).toBeUndefined();
  });

  it("cancelar o par não declara vão nenhum", () => {
    const result = run(
      { kind: "pair", readingId: "rd_1", firstProposalId: null },
      shape("vp_a"),
      cancel,
    );

    expect(result.state).toEqual(IDLE_CAPTURE);
    expect(result.commit).toBeUndefined();
  });
});

describe("captura de reamarração simples", () => {
  it("um clique em forma fecha a amarração", () => {
    const result = reduceCapture(
      { kind: "single", readingId: "rd_2" },
      shape("vp_c"),
    );

    expect(result.state).toEqual(IDLE_CAPTURE);
    expect(result.commit).toEqual({
      kind: "span",
      readingId: "rd_2",
      target: { kind: "single", proposalId: "vp_c" },
    });
  });

  it("clique em ponto não amarra nada", () => {
    const result = reduceCapture(
      { kind: "single", readingId: "rd_2" },
      point(5, 5),
    );

    expect(result.commit).toBeUndefined();
    expect(result.state).toEqual({ kind: "single", readingId: "rd_2" });
  });

  it("cancelar não amarra nada", () => {
    const result = reduceCapture({ kind: "single", readingId: "rd_2" }, cancel);

    expect(result.state).toEqual(IDLE_CAPTURE);
    expect(result.commit).toBeUndefined();
  });
});

describe("captura de vão declarado no próprio elemento", () => {
  const start: CaptureState = {
    kind: "declared",
    readingId: "rd_3",
    proposalId: null,
    anchors: [],
  };

  it("forma e duas pontas fecham um trecho ao concluir", () => {
    const result = run(start, shape("vp_a"), point(10, 20), point(30, 40), cancel);

    expect(result.state).toEqual(IDLE_CAPTURE);
    expect(result.commit).toEqual({
      kind: "span",
      readingId: "rd_3",
      target: {
        kind: "declared",
        proposalId: "vp_a",
        spansPx: [
          [
            [10, 20],
            [30, 40],
          ],
        ],
      },
    });
  });

  it("quatro pontas fecham dois trechos do mesmo valor", () => {
    const result = run(
      start,
      shape("vp_a"),
      point(10, 20),
      point(30, 40),
      point(50, 60),
      point(70, 80),
      cancel,
    );

    expect(result.commit).toEqual({
      kind: "span",
      readingId: "rd_3",
      target: {
        kind: "declared",
        proposalId: "vp_a",
        spansPx: [
          [
            [10, 20],
            [30, 40],
          ],
          [
            [50, 60],
            [70, 80],
          ],
        ],
      },
    });
  });

  it("concluir com par incompleto mantém os trechos já fechados e descarta a ponta solta", () => {
    const result = run(
      start,
      shape("vp_a"),
      point(10, 20),
      point(30, 40),
      point(50, 60),
      cancel,
    );

    expect(result.commit).toEqual({
      kind: "span",
      readingId: "rd_3",
      target: {
        kind: "declared",
        proposalId: "vp_a",
        spansPx: [
          [
            [10, 20],
            [30, 40],
          ],
        ],
      },
    });
  });

  it("concluir sem nenhum trecho fechado não declara vão", () => {
    const result = run(start, shape("vp_a"), point(10, 20), cancel);

    expect(result.state).toEqual(IDLE_CAPTURE);
    expect(result.commit).toBeUndefined();
  });

  it("concluir sem sequer escolher a forma não declara vão", () => {
    const result = reduceCapture(start, cancel);

    expect(result.state).toEqual(IDLE_CAPTURE);
    expect(result.commit).toBeUndefined();
  });

  it("ponto antes da forma não vira âncora", () => {
    const result = reduceCapture(start, point(10, 20));

    expect(result.state).toEqual(start);
  });

  it("segunda forma clicada não troca o elemento do vão", () => {
    const result = run(start, shape("vp_a"), shape("vp_b"));

    expect(result.state).toEqual({
      kind: "declared",
      readingId: "rd_3",
      proposalId: "vp_a",
      anchors: [],
    });
  });

  it("o hint conta os trechos fechados e ensina o Esc", () => {
    const first = run(start, shape("vp_a"));
    expect(first.hint).toContain("nenhum trecho fechado ainda");

    const half = run(start, shape("vp_a"), point(10, 20));
    expect(half.hint).toContain("outra ponta");

    const one = run(start, shape("vp_a"), point(10, 20), point(30, 40));
    expect(one.hint).toContain("1 trecho fechado");
    expect(one.hint).toContain("Esc");

    const two = run(
      start,
      shape("vp_a"),
      point(10, 20),
      point(30, 40),
      point(50, 60),
      point(70, 80),
    );
    expect(two.hint).toContain("2 trechos fechados");
  });
});

describe("captura de nota presa", () => {
  it("um clique em forma prende a nota, sem orientação declarada", () => {
    const result = reduceCapture(
      { kind: "note", readingId: "rd_4" },
      shape("vp_b"),
    );

    expect(result.state).toEqual(IDLE_CAPTURE);
    expect(result.commit).toEqual({
      kind: "note",
      readingId: "rd_4",
      target: "vp_b",
    });
  });

  it("clique em ponto não prende nota", () => {
    const result = reduceCapture(
      { kind: "note", readingId: "rd_4" },
      point(1, 2),
    );

    expect(result.commit).toBeUndefined();
  });
});

describe("captura de cota derivada", () => {
  const start: CaptureState = { kind: "derived", proposalId: null };

  it("forma e ponto fecham a cota derivada", () => {
    const result = run(start, shape("vp_c"), point(120, 340));

    expect(result.state).toEqual(IDLE_CAPTURE);
    expect(result.commit).toEqual({
      kind: "derived",
      dimension: { proposalId: "vp_c", nearXPx: 120, nearYPx: 340 },
    });
  });

  it("ponto antes da forma não fecha nada", () => {
    const result = reduceCapture(start, point(120, 340));

    expect(result.state).toEqual(start);
    expect(result.commit).toBeUndefined();
  });

  it("segunda forma clicada não troca o alvo", () => {
    const result = run(start, shape("vp_c"), shape("vp_a"));

    expect(result.state).toEqual({ kind: "derived", proposalId: "vp_c" });
  });

  it("cancelar no meio não declara cota", () => {
    const result = run(start, shape("vp_c"), cancel);

    expect(result.state).toEqual(IDLE_CAPTURE);
    expect(result.commit).toBeUndefined();
  });
});

describe("estado de repouso e hints", () => {
  it("em repouso nenhum evento produz efeito", () => {
    for (const event of [shape("vp_a"), point(1, 1), cancel]) {
      const result = reduceCapture(IDLE_CAPTURE, event);
      expect(result.state).toEqual(IDLE_CAPTURE);
      expect(result.commit).toBeUndefined();
    }
  });

  it("todo estado tem instrução escrita", () => {
    const states: CaptureState[] = [
      IDLE_CAPTURE,
      { kind: "pair", readingId: "rd_1", firstProposalId: null },
      { kind: "pair", readingId: "rd_1", firstProposalId: "vp_a" },
      { kind: "single", readingId: "rd_1" },
      { kind: "declared", readingId: "rd_1", proposalId: null, anchors: [] },
      { kind: "declared", readingId: "rd_1", proposalId: "vp_a", anchors: [] },
      { kind: "note", readingId: "rd_1" },
      { kind: "derived", proposalId: null },
      { kind: "derived", proposalId: "vp_a" },
    ];

    for (const state of states) {
      expect(captureHint(state).length).toBeGreaterThan(0);
    }
  });

  it("só espera ponto depois que a forma da captura já foi escolhida", () => {
    expect(captureExpectsPoint(IDLE_CAPTURE)).toBe(false);
    expect(
      captureExpectsPoint({
        kind: "pair",
        readingId: "rd_1",
        firstProposalId: "vp_a",
      }),
    ).toBe(false);
    expect(
      captureExpectsPoint({
        kind: "declared",
        readingId: "rd_1",
        proposalId: null,
        anchors: [],
      }),
    ).toBe(false);
    expect(
      captureExpectsPoint({
        kind: "declared",
        readingId: "rd_1",
        proposalId: "vp_a",
        anchors: [],
      }),
    ).toBe(true);
    expect(captureExpectsPoint({ kind: "derived", proposalId: null })).toBe(
      false,
    );
    expect(captureExpectsPoint({ kind: "derived", proposalId: "vp_a" })).toBe(
      true,
    );
  });

  it("a leitura da captura acompanha o gesto, e a cota derivada não tem leitura", () => {
    expect(
      captureReadingId({ kind: "note", readingId: "rd_9" }),
    ).toBe("rd_9");
    expect(captureReadingId({ kind: "derived", proposalId: null })).toBeNull();
    expect(captureReadingId(IDLE_CAPTURE)).toBeNull();
  });
});

describe("alvo de nota", () => {
  it("carimbo, legenda e elemento com orientação vão e voltam", () => {
    expect(parseNoteTarget("carimbo")).toEqual({ kind: "stamp" });
    expect(parseNoteTarget("legenda:vp_a")).toEqual({
      kind: "legend",
      proposalId: "vp_a",
    });
    expect(parseNoteTarget("vp_a")).toEqual({
      kind: "shape",
      proposalId: "vp_a",
      orientation: "auto",
    });
    expect(parseNoteTarget("vp_a#v")).toEqual({
      kind: "shape",
      proposalId: "vp_a",
      orientation: "v",
    });
    expect(parseNoteTarget("vp_a#h")).toEqual({
      kind: "shape",
      proposalId: "vp_a",
      orientation: "h",
    });

    for (const target of ["carimbo", "legenda:vp_a", "vp_a", "vp_a#v", "vp_a#h"]) {
      expect(formatNoteTarget(parseNoteTarget(target))).toBe(target);
    }
  });

  it("orientação desconhecida volta como automática", () => {
    expect(parseNoteTarget("vp_a#z")).toEqual({
      kind: "shape",
      proposalId: "vp_a",
      orientation: "auto",
    });
  });
});

describe("do gesto ao pedido de aceite", () => {
  const review: Review = {
    job_id: "0198c0de-0000-7000-8000-00000000000a",
    review_id: "0198c0de-0000-7000-8000-00000000000b",
    version: 7,
    packet: { readings: [] },
    associations: { candidates: [] },
    proposals: null,
    selected_associations: {},
    calibration: null,
    proposal_decisions: [],
    issues: [],
    blockers: [],
    required_criteria: [],
    scene: null,
    preview_urls: {},
  };

  /** Aplica no rascunho os gestos concluídos, como a tela faz a cada commit. */
  function draftFrom(...commits: CaptureCommit[]): TraceDraft {
    return commits.reduce(applyCaptureCommit, {
      ...emptyTraceDraft(),
      proposalIds: ["vp_a", "vp_b", "vp_c"],
    });
  }

  it("o vão em par clicado vira o par de formas no corpo do aceite", () => {
    const commit = run(
      { kind: "pair", readingId: "rd_1", firstProposalId: null },
      shape("vp_a"),
      shape("vp_b"),
    ).commit;

    const request = buildTraceSolveRequest(draftFrom(commit!), review);

    expect(request.associations).toEqual({ rd_1: ["vp_a", "vp_b"] });
  });

  it("o vão declarado clicado vira o elemento com os trechos em pixel", () => {
    const commit = run(
      { kind: "declared", readingId: "rd_2", proposalId: null, anchors: [] },
      shape("vp_a"),
      point(10, 20),
      point(30, 40),
      cancel,
    ).commit;

    const request = buildTraceSolveRequest(draftFrom(commit!), review);

    expect(request.associations).toEqual({
      rd_2: {
        proposal_id: "vp_a",
        spans_px: [
          [
            [10, 20],
            [30, 40],
          ],
        ],
      },
    });
  });

  it("nota e cota derivada clicadas viajam nos campos próprios", () => {
    const note = reduceCapture(
      { kind: "note", readingId: "rd_3" },
      shape("vp_c"),
    ).commit;
    const derived = run(
      { kind: "derived", proposalId: null },
      shape("vp_b"),
      point(120, 340),
    ).commit;

    const request = buildTraceSolveRequest(draftFrom(note!, derived!), review);

    expect(request.note_associations).toEqual({ rd_3: "vp_c" });
    expect(request.derived_dimensions).toEqual([
      { proposal_id: "vp_b", near_x_px: 120, near_y_px: 340 },
    ]);
  });

  it("amarrar a mesma leitura de novo substitui a amarração anterior", () => {
    const first = reduceCapture(
      { kind: "single", readingId: "rd_1" },
      shape("vp_a"),
    ).commit;
    const second = run(
      { kind: "pair", readingId: "rd_1", firstProposalId: null },
      shape("vp_b"),
      shape("vp_c"),
    ).commit;

    const draft = draftFrom(first!, second!);

    expect(draft.associations).toEqual({
      rd_1: { kind: "pair", proposalIds: ["vp_b", "vp_c"] },
    });
  });

  it("cada cota derivada é um item novo, nunca substituição", () => {
    const first = run(
      { kind: "derived", proposalId: null },
      shape("vp_a"),
      point(1, 2),
    ).commit;
    const second = run(
      { kind: "derived", proposalId: null },
      shape("vp_a"),
      point(3, 4),
    ).commit;

    expect(draftFrom(first!, second!).derivedDimensions).toEqual([
      { proposalId: "vp_a", nearXPx: 1, nearYPx: 2 },
      { proposalId: "vp_a", nearXPx: 3, nearYPx: 4 },
    ]);
  });
});

describe("centro aparente da forma", () => {
  it("linha usa o ponto médio", () => {
    expect(
      proposalCentrePx({
        type: "line",
        start: { x: 0, y: 0 },
        end: { x: 100, y: 40 },
      }),
    ).toEqual({ x: 50, y: 20 });
  });

  it("círculo usa o próprio centro", () => {
    expect(
      proposalCentrePx({ type: "circle", center: { x: 12, y: 34 }, radius: 9 }),
    ).toEqual({ x: 12, y: 34 });
  });

  it("contorno usa o centro da caixa envolvente, não a média dos vértices", () => {
    expect(
      proposalCentrePx({
        type: "polyline",
        closed: true,
        points: [
          { x: 0, y: 0 },
          { x: 1, y: 0 },
          { x: 2, y: 0 },
          { x: 100, y: 50 },
        ],
      }),
    ).toEqual({ x: 50, y: 25 });
  });

  it("contorno sem pontos não inventa posição", () => {
    expect(
      proposalCentrePx({ type: "polyline", closed: false, points: [] }),
    ).toEqual({ x: 0, y: 0 });
  });
});
