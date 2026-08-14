import { describe, expect, it } from "vitest";

import type {
  Review,
  ReviewReading,
  TraceResidualSummary,
  TraceSolveResponse,
  VisionProposal,
} from "./api";
import {
  buildTraceSolveRequest,
  defaultFlagsForProposal,
  emptyTraceDraft,
  spanAxisIssue,
  traceDraftIssues,
  traceResidualSummaryLabel,
  traceSolveInFlight,
  traceSolveStatusLabel,
  withDefaultProposalFlags,
  type ProposalFlagContext,
  type TraceDraft,
  type TraceDraftContext,
} from "./trace";

function review(overrides: Partial<Review> = {}): Review {
  return {
    job_id: "0198c0de-0000-7000-8000-00000000000a",
    review_id: "0198c0de-0000-7000-8000-00000000000b",
    version: 4,
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
    ...overrides,
  };
}

function scene(version: number): NonNullable<Review["scene"]> {
  return {
    id: "0198c0de-0000-7000-8000-00000000000c",
    version,
    approved: false,
    entities: [],
  };
}

function draft(overrides: Partial<TraceDraft> = {}): TraceDraft {
  return { ...emptyTraceDraft(), ...overrides };
}

/**
 * vp_a carries the VLM label the extraction would write; vp_b and vp_c have none, so
 * they exercise the geometric description and the balloon that gives every duplicate
 * "linha" an address of its own (balloons ①②③ across the suite's assertions).
 */
function proposals(): VisionProposal[] {
  return [
    {
      id: "vp_a",
      kind: "line",
      precision: "unresolved",
      export: false,
      label: "Muro lateral",
      geometry: {
        type: "line",
        start: { x: 0, y: 0 },
        end: { x: 100, y: 0 },
      },
    },
    {
      id: "vp_b",
      kind: "line",
      precision: "unresolved",
      export: false,
      geometry: {
        type: "line",
        start: { x: 0, y: 0 },
        end: { x: 0, y: 400 },
      },
    },
    {
      id: "vp_c",
      kind: "line",
      precision: "unresolved",
      export: false,
      geometry: {
        type: "line",
        start: { x: 0, y: 0 },
        end: { x: 200, y: 0 },
      },
    },
  ];
}

/** Leitura confirmada padrão dos testes de vão/nota/derivada/texto de cota. */
function reading(overrides: Partial<ReviewReading> = {}): ReviewReading {
  return {
    id: "rd_1",
    raw_text: "4,40",
    kind: "width",
    status: "confirmed",
    ...overrides,
  };
}

function context(overrides: Partial<TraceDraftContext> = {}): TraceDraftContext {
  return {
    readings: [],
    selectedAssociations: {},
    ...overrides,
  };
}

function traceSolve(
  overrides: Partial<TraceSolveResponse> = {},
): TraceSolveResponse {
  return {
    trace_solve_id: "0198c0de-0000-7000-8000-00000000000d",
    job_id: "0198c0de-0000-7000-8000-00000000000a",
    status: "QUEUED",
    acceptance_id: "ta_0123456789abcdef",
    base_review_version: 4,
    base_scene_version: null,
    solve_status: null,
    blockers: [],
    unapplied_reading_ids: [],
    residual_summary: null,
    exact_entity_count: null,
    approximate_entity_count: null,
    note_count: null,
    scale_m_per_px: null,
    detail_group_scales: {},
    result_scene_revision_id: null,
    result_scene_version: null,
    result_review_version: null,
    failure_code: null,
    ...overrides,
  };
}

describe("emptyTraceDraft", () => {
  it("starts the span, note, derived dimension and dimension text fields empty", () => {
    const empty = emptyTraceDraft();

    expect(empty.associations).toEqual({});
    expect(empty.noteTargets).toEqual({});
    expect(empty.derivedDimensions).toEqual([]);
    expect(empty.dimensionTexts).toEqual({});
  });
});

describe("buildTraceSolveRequest", () => {
  it("omits the scene version when the job has no metric scene yet", () => {
    const request = buildTraceSolveRequest(
      draft({ proposalIds: ["vp_a", "vp_b"] }),
      review(),
    );

    expect(request).toEqual({
      base_review_version: 4,
      proposal_ids: ["vp_a", "vp_b"],
    });
    expect("base_scene_version" in request).toBe(false);
  });

  it("sends the current scene version when the job already has a scene", () => {
    const request = buildTraceSolveRequest(
      draft({ proposalIds: ["vp_a"] }),
      review({ scene: scene(7) }),
    );

    expect(request.base_scene_version).toBe(7);
    expect(request.base_review_version).toBe(4);
  });

  it("never carries reviewer identity, role, clock or acceptance id", () => {
    const request = buildTraceSolveRequest(
      draft({ proposalIds: ["vp_a"], note: "Conferido.", title: "CAMPO" }),
      review(),
    );

    for (const forbidden of [
      "reviewer_id",
      "reviewer_role",
      "decided_at",
      "acceptance_id",
    ]) {
      expect(forbidden in request).toBe(false);
    }
  });

  it("writes the auxiliary lists in acceptance order and drops empty ones", () => {
    const request = buildTraceSolveRequest(
      draft({
        proposalIds: ["vp_a", "vp_b", "vp_c"],
        hatch: new Set(["vp_c", "vp_a"]),
        freeform: new Set(["vp_b"]),
        keepApartPairs: [{ first: "vp_a", second: "vp_b", axis: null }],
      }),
      review(),
    );

    expect(request.hatch_proposal_ids).toEqual(["vp_a", "vp_c"]);
    expect(request.freeform_proposal_ids).toEqual(["vp_b"]);
    expect(request.keep_apart_pairs).toEqual([["vp_a", "vp_b"]]);
    expect("unlabelled_proposal_ids" in request).toBe(false);
    expect("detail_groups" in request).toBe(false);
  });

  it("emits a tuple for axis null (retrocompat) and an object for a declared axis", () => {
    const request = buildTraceSolveRequest(
      draft({
        proposalIds: ["vp_a", "vp_b", "vp_c", "vp_d"],
        keepApartPairs: [
          { first: "vp_a", second: "vp_b", axis: null },
          { first: "vp_a", second: "vp_c", axis: "x" },
          { first: "vp_b", second: "vp_d", axis: "y" },
        ],
      }),
      review(),
    );

    expect(request.keep_apart_pairs).toEqual([
      ["vp_a", "vp_b"],
      { first: "vp_a", second: "vp_c", axis: "x" },
      { first: "vp_b", second: "vp_d", axis: "y" },
    ]);
  });

  it("trims the optional texts and omits them when blank", () => {
    const withTexts = buildTraceSolveRequest(
      draft({
        proposalIds: ["vp_a"],
        note: "  Traçado conferido.  ",
        title: "  CAMPO GUAXINDIBA  ",
      }),
      review(),
    );
    const withoutTexts = buildTraceSolveRequest(
      draft({ proposalIds: ["vp_a"], note: "   ", title: "" }),
      review(),
    );

    expect(withTexts.note).toBe("Traçado conferido.");
    expect(withTexts.title).toBe("CAMPO GUAXINDIBA");
    expect("note" in withoutTexts).toBe(false);
    expect("title" in withoutTexts).toBe(false);
  });

  it("sends detail groups with the trimmed title and the declared mode", () => {
    const request = buildTraceSolveRequest(
      draft({
        proposalIds: ["vp_a", "vp_b"],
        detailGroups: [
          {
            detailId: "A",
            title: "  Painel de alambrado  ",
            proposalIds: ["vp_b"],
            mode: "sketch",
          },
        ],
      }),
      review(),
    );

    expect(request.detail_groups).toEqual([
      {
        detail_id: "A",
        title: "Painel de alambrado",
        proposal_ids: ["vp_b"],
        mode: "sketch",
      },
    ]);
  });

  it("serializes single, pair and declared associations to the exact wire shape", () => {
    const request = buildTraceSolveRequest(
      draft({
        proposalIds: ["vp_a", "vp_b", "vp_c"],
        associations: {
          rd_single: { kind: "single", proposalId: "vp_a" },
          rd_pair: { kind: "pair", proposalIds: ["vp_b", "vp_c"] },
          rd_declared: {
            kind: "declared",
            proposalId: "vp_a",
            spansPx: [
              [
                [100, 300],
                [220, 300],
              ],
            ],
          },
        },
      }),
      review(),
    );

    expect(request.associations).toEqual({
      rd_single: "vp_a",
      rd_pair: ["vp_b", "vp_c"],
      rd_declared: {
        proposal_id: "vp_a",
        spans_px: [
          [
            [100, 300],
            [220, 300],
          ],
        ],
      },
    });
  });

  it("serializes note targets as they are, and derived dimensions with the trimmed optional text", () => {
    const request = buildTraceSolveRequest(
      draft({
        proposalIds: ["vp_a", "vp_b"],
        noteTargets: { rd_note: "vp_a#v", rd_legend: "legenda:vp_b", rd_stamp: "carimbo" },
        derivedDimensions: [
          { proposalId: "vp_a", nearXPx: 10, nearYPx: 20, text: "  3,60 x 3,90  " },
          { proposalId: "vp_b", nearXPx: 30, nearYPx: 40 },
        ],
      }),
      review(),
    );

    expect(request.note_associations).toEqual({
      rd_note: "vp_a#v",
      rd_legend: "legenda:vp_b",
      rd_stamp: "carimbo",
    });
    expect(request.derived_dimensions).toEqual([
      { proposal_id: "vp_a", near_x_px: 10, near_y_px: 20, text: "3,60 x 3,90" },
      { proposal_id: "vp_b", near_x_px: 30, near_y_px: 40 },
    ]);
    expect("text" in (request.derived_dimensions?.[1] ?? {})).toBe(false);
  });

  it("trims dimension texts and drops entries that are blank after trim", () => {
    const request = buildTraceSolveRequest(
      draft({
        proposalIds: ["vp_a"],
        dimensionTexts: { rd_text: "  1,0 x 2,05  ", rd_blank: "   " },
      }),
      review(),
    );

    expect(request.dimension_texts).toEqual({ rd_text: "1,0 x 2,05" });
  });

  it("omits associations, note_associations, derived_dimensions and dimension_texts entirely when empty", () => {
    const request = buildTraceSolveRequest(draft({ proposalIds: ["vp_a"] }), review());

    expect("associations" in request).toBe(false);
    expect("note_associations" in request).toBe(false);
    expect("derived_dimensions" in request).toBe(false);
    expect("dimension_texts" in request).toBe(false);
  });

  it("omits dimension_texts entirely when every declared text is blank after trim", () => {
    const request = buildTraceSolveRequest(
      draft({ proposalIds: ["vp_a"], dimensionTexts: { rd_1: "   " } }),
      review(),
    );

    expect("dimension_texts" in request).toBe(false);
  });
});

describe("traceDraftIssues", () => {
  it("accepts a plain selection without complaint", () => {
    expect(
      traceDraftIssues(draft({ proposalIds: ["vp_a", "vp_b"] }), proposals()),
    ).toEqual([]);
  });

  it("asks for a selection when nothing is marked", () => {
    expect(traceDraftIssues(draft(), proposals())).toContain(
      "Selecione ao menos uma forma do desenho para aceitar o traçado.",
    );
  });

  it("names the shape accepted twice instead of an aggregated warning", () => {
    expect(
      traceDraftIssues(
        draft({ proposalIds: ["vp_a", "vp_a"] }),
        proposals(),
      ),
    ).toContain('A forma "① Muro lateral" aparece mais de uma vez no aceite.');
  });

  it("names the shape behind every flag pointing outside the acceptance", () => {
    const outside = (field: "hatch" | "unlabelled" | "freeform") =>
      traceDraftIssues(
        draft({ proposalIds: ["vp_a"], [field]: new Set(["vp_b"]) }),
        proposals(),
      );

    expect(outside("hatch")).toContain(
      'A forma "② linha vertical · 400 px" está marcada como hachura e saiu da seleção: marque-a de novo ou desfaça a hachura.',
    );
    expect(outside("unlabelled")).toContain(
      'A forma "② linha vertical · 400 px" está marcada como sem legenda e saiu da seleção: marque-a de novo ou desfaça a marcação.',
    );
    expect(outside("freeform")).toContain(
      'A forma "② linha vertical · 400 px" está marcada como desenhada e saiu da seleção: marque-a de novo ou desfaça a marcação.',
    );
  });

  it("names the shape a keep-apart pair points to twice", () => {
    expect(
      traceDraftIssues(
        draft({
          proposalIds: ["vp_a"],
          keepApartPairs: [{ first: "vp_a", second: "vp_a", axis: null }],
        }),
        proposals(),
      ),
    ).toContain(
      'O par de manter separados aponta a forma "① Muro lateral" duas vezes; ele precisa de duas formas distintas.',
    );
  });

  it("names the shape a keep-apart pair cites after it left the selection", () => {
    expect(
      traceDraftIssues(
        draft({
          proposalIds: ["vp_a"],
          keepApartPairs: [{ first: "vp_a", second: "vp_b", axis: null }],
        }),
        proposals(),
      ),
    ).toContain(
      'O par de manter separados cita a forma "② linha vertical · 400 px", que saiu da seleção: marque-a de novo ou desfaça o par.',
    );
  });

  it("validates the detail code against the contract pattern", () => {
    const invalid = traceDraftIssues(
      draft({
        proposalIds: ["vp_a", "vp_b"],
        detailGroups: [
          { detailId: "a1", title: "Painel", proposalIds: ["vp_b"], mode: "solve" },
        ],
      }),
      proposals(),
    );
    const valid = traceDraftIssues(
      draft({
        proposalIds: ["vp_a", "vp_b"],
        detailGroups: [
          { detailId: "B2", title: "Painel", proposalIds: ["vp_b"], mode: "solve" },
        ],
      }),
      proposals(),
    );

    expect(invalid).toContain(
      "O código do detalhe começa por letra maiúscula e tem até oito caracteres maiúsculos, como A ou B2.",
    );
    expect(valid).toEqual([]);
  });

  it("catches a duplicated detail code and a missing title", () => {
    const issues = traceDraftIssues(
      draft({
        proposalIds: ["vp_a", "vp_b", "vp_c"],
        detailGroups: [
          { detailId: "A", title: "Painel", proposalIds: ["vp_b"], mode: "solve" },
          { detailId: "A", title: "  ", proposalIds: ["vp_c"], mode: "solve" },
        ],
      }),
      proposals(),
    );

    expect(issues).toContain("Dois grupos de detalhe estão com o mesmo código.");
    expect(issues).toContain("Todo grupo de detalhe precisa de um título.");
  });

  it("names the shape repeated across detail groups and still flags an empty group", () => {
    const issues = traceDraftIssues(
      draft({
        proposalIds: ["vp_a", "vp_b"],
        detailGroups: [
          { detailId: "A", title: "Painel", proposalIds: ["vp_b"], mode: "solve" },
          { detailId: "B", title: "Arquibancada", proposalIds: ["vp_b"], mode: "solve" },
          { detailId: "C", title: "Vazio", proposalIds: [], mode: "solve" },
        ],
      }),
      proposals(),
    );

    expect(issues).toContain(
      'A forma "② linha vertical · 400 px" está em mais de um grupo de detalhe.',
    );
    expect(issues).toContain("Todo grupo de detalhe precisa de ao menos uma forma.");
  });

  it("names the group code and the shape a detail group cites after it left the selection", () => {
    expect(
      traceDraftIssues(
        draft({
          proposalIds: ["vp_a"],
          detailGroups: [
            { detailId: "A", title: "Painel", proposalIds: ["vp_b"], mode: "solve" },
          ],
        }),
        proposals(),
      ),
    ).toContain(
      'O grupo de detalhe A cita a forma "② linha vertical · 400 px", que saiu da seleção: marque-a de novo ou desfaça o grupo.',
    );
  });

  it("refuses an acceptance where every shape went into detail groups", () => {
    expect(
      traceDraftIssues(
        draft({
          proposalIds: ["vp_a", "vp_b"],
          detailGroups: [
            {
              detailId: "A",
              title: "Painel",
              proposalIds: ["vp_a", "vp_b"],
              mode: "solve",
            },
          ],
        }),
        proposals(),
      ),
    ).toContain(
      "A planta principal ficaria vazia: deixe ao menos uma forma fora dos grupos de detalhe.",
    );
  });

  it("refuses texts longer than the contract accepts", () => {
    const issues = traceDraftIssues(
      draft({
        proposalIds: ["vp_a"],
        title: "T".repeat(121),
        note: "N".repeat(501),
      }),
      proposals(),
    );

    expect(issues).toContain(
      "O título da prancha não pode passar de 120 caracteres.",
    );
    expect(issues).toContain(
      "A nota do aceite não pode passar de 500 caracteres.",
    );
  });

  it("describes a shape no longer in the drawing instead of showing a raw id", () => {
    expect(
      traceDraftIssues(
        draft({ proposalIds: ["vp_a"], hatch: new Set(["vp_ghost"]) }),
        proposals(),
      ),
    ).toContain(
      "Uma forma que não está mais no desenho está marcada como hachura e saiu da seleção: marque-a de novo ou desfaça a hachura.",
    );
  });

  it("reads the shape length in metres, with a decimal comma, once the ruler is active", () => {
    expect(
      traceDraftIssues(
        draft({ proposalIds: ["vp_b", "vp_b"] }),
        proposals(),
        0.01,
      ),
    ).toContain(
      'A forma "② linha vertical · ≈ 4,0 m" aparece mais de uma vez no aceite.',
    );
  });

  it("names no raw identifier in any message even when the shapes are unknown", () => {
    const issues = traceDraftIssues(
      draft({
        proposalIds: ["vp_a", "vp_a"],
        hatch: new Set(["vp_z"]),
        unlabelled: new Set(["vp_z"]),
        freeform: new Set(["vp_z"]),
        keepApartPairs: [{ first: "vp_a", second: "vp_a", axis: null }],
        detailGroups: [
          { detailId: "a1", title: "", proposalIds: ["vp_z"], mode: "solve" },
        ],
      }),
      proposals(),
    );

    expect(issues.length).toBeGreaterThan(0);
    for (const issue of issues) {
      expect(issue).not.toContain("vp_");
      expect(issue).not.toContain("rd_");
    }
  });

  it("stays exactly as before when called with three arguments (retrocompatibility)", () => {
    const withoutContext = traceDraftIssues(
      draft({ proposalIds: ["vp_a", "vp_a"] }),
      proposals(),
      0.01,
    );

    expect(withoutContext).toEqual([
      'A forma "① Muro lateral" aparece mais de uma vez no aceite.',
    ]);
  });

  describe("vãos (associations)", () => {
    it("flags a single-target association whose shape left the acceptance", () => {
      expect(
        traceDraftIssues(
          draft({
            proposalIds: ["vp_a"],
            associations: { rd_1: { kind: "single", proposalId: "vp_b" } },
          }),
          proposals(),
        ),
      ).toContain(
        'A forma "② linha vertical · 400 px" está amarrada como vão e saiu da seleção: marque-a de novo ou desfaça a amarração.',
      );
    });

    it("does not flag a single-target association whose shape stayed in the acceptance", () => {
      expect(
        traceDraftIssues(
          draft({
            proposalIds: ["vp_a"],
            associations: { rd_1: { kind: "single", proposalId: "vp_a" } },
          }),
          proposals(),
        ),
      ).toEqual([]);
    });

    it("flags each shape of a pair association that left the acceptance", () => {
      const issues = traceDraftIssues(
        draft({
          proposalIds: ["vp_a"],
          associations: { rd_1: { kind: "pair", proposalIds: ["vp_a", "vp_b"] } },
        }),
        proposals(),
      );

      expect(issues).toContain(
        'A forma "② linha vertical · 400 px" está amarrada como vão e saiu da seleção: marque-a de novo ou desfaça a amarração.',
      );
    });

    it("flags a declared association whose element left the acceptance", () => {
      expect(
        traceDraftIssues(
          draft({
            proposalIds: ["vp_a"],
            associations: {
              rd_1: {
                kind: "declared",
                proposalId: "vp_b",
                spansPx: [[[0, 0], [10, 0]]],
              },
            },
          }),
          proposals(),
        ),
      ).toContain(
        'A forma "② linha vertical · 400 px" está amarrada como vão e saiu da seleção: marque-a de novo ou desfaça a amarração.',
      );
    });

    it("names the shape a pair association points to twice", () => {
      expect(
        traceDraftIssues(
          draft({
            proposalIds: ["vp_a"],
            associations: { rd_1: { kind: "pair", proposalIds: ["vp_a", "vp_a"] } },
          }),
          proposals(),
        ),
      ).toContain(
        'O vão declarado para uma cota que não está mais no pacote aponta a forma "① Muro lateral" duas vezes; ele precisa de duas formas distintas.',
      );
    });

    it("does not flag a pair association pointing to two distinct shapes", () => {
      expect(
        traceDraftIssues(
          draft({
            proposalIds: ["vp_a", "vp_b"],
            associations: { rd_1: { kind: "pair", proposalIds: ["vp_a", "vp_b"] } },
          }),
          proposals(),
        ),
      ).toEqual([]);
    });

    it("refuses a declared association without any span", () => {
      expect(
        traceDraftIssues(
          draft({
            proposalIds: ["vp_a"],
            associations: { rd_1: { kind: "declared", proposalId: "vp_a", spansPx: [] } },
          }),
          proposals(),
        ),
      ).toContain(
        'Uma cota que não está mais no pacote está com vão declarado sem nenhum trecho: adicione ao menos um par de âncoras.',
      );
    });

    it("refuses a declared span whose two anchors are the same point", () => {
      expect(
        traceDraftIssues(
          draft({
            proposalIds: ["vp_a"],
            associations: {
              rd_1: {
                kind: "declared",
                proposalId: "vp_a",
                spansPx: [[[100, 300], [100, 300]]],
              },
            },
          }),
          proposals(),
        ),
      ).toContain(
        'Uma cota que não está mais no pacote tem um trecho cujas duas pontas apontam o mesmo ponto; marque duas âncoras distintas.',
      );
    });

    it("accepts a declared association with distinct anchors", () => {
      expect(
        traceDraftIssues(
          draft({
            proposalIds: ["vp_a"],
            associations: {
              rd_1: {
                kind: "declared",
                proposalId: "vp_a",
                spansPx: [[[100, 300], [220, 300]]],
              },
            },
          }),
          proposals(),
        ),
      ).toEqual([]);
    });
  });

  describe("notas (noteTargets)", () => {
    it("flags a note target whose shape left the acceptance", () => {
      expect(
        traceDraftIssues(
          draft({ proposalIds: ["vp_a"], noteTargets: { rd_1: "vp_b" } }),
          proposals(),
        ),
      ).toContain(
        'A forma "② linha vertical · 400 px" está amarrada como nota e saiu da seleção: marque-a de novo ou desfaça a amarração.',
      );
    });

    it("does not flag the general stamp target, which cites no shape", () => {
      expect(
        traceDraftIssues(
          draft({ proposalIds: ["vp_a"], noteTargets: { rd_1: "carimbo" } }),
          proposals(),
        ),
      ).toEqual([]);
    });

    it("does not flag a legend note target whose shape stayed accepted", () => {
      expect(
        traceDraftIssues(
          draft({ proposalIds: ["vp_a"], noteTargets: { rd_1: "legenda:vp_a" } }),
          proposals(),
        ),
      ).toEqual([]);
    });

    it("refuses a note suffix other than v or h", () => {
      expect(
        traceDraftIssues(
          draft({ proposalIds: ["vp_a"], noteTargets: { rd_1: "vp_a#x" } }),
          proposals(),
        ),
      ).toContain(
        'Uma cota que não está mais no pacote tem nota com orientação inválida: a orientação da nota é v (vertical) ou h (horizontal).',
      );
    });

    it("accepts the v and h note suffixes", () => {
      expect(
        traceDraftIssues(
          draft({ proposalIds: ["vp_a"], noteTargets: { rd_1: "vp_a#v" } }),
          proposals(),
        ),
      ).toEqual([]);
      expect(
        traceDraftIssues(
          draft({ proposalIds: ["vp_a"], noteTargets: { rd_1: "vp_a#h" } }),
          proposals(),
        ),
      ).toEqual([]);
    });
  });

  describe("textos de cota (dimensionTexts) e cotas derivadas (derivedDimensions)", () => {
    it("refuses a dimension text that is blank after trim", () => {
      expect(
        traceDraftIssues(
          draft({ proposalIds: ["vp_a"], dimensionTexts: { rd_1: "   " } }),
          proposals(),
        ),
      ).toContain(
        'O texto de uma cota que não está mais no pacote está vazio; escreva a especificação ou remova o texto.',
      );
    });

    it("accepts a non-blank dimension text", () => {
      expect(
        traceDraftIssues(
          draft({ proposalIds: ["vp_a"], dimensionTexts: { rd_1: "1,0 x 2,05" } }),
          proposals(),
        ),
      ).toEqual([]);
    });

    it("flags a derived dimension pointing to a shape that left the acceptance", () => {
      expect(
        traceDraftIssues(
          draft({
            proposalIds: ["vp_a"],
            derivedDimensions: [{ proposalId: "vp_b", nearXPx: 10, nearYPx: 20 }],
          }),
          proposals(),
        ),
      ).toContain(
        'A forma "② linha vertical · 400 px" está amarrada como cota derivada e saiu da seleção: marque-a de novo ou desfaça a amarração.',
      );
    });

    it("refuses a derived dimension text longer than the worker's contract limit", () => {
      expect(
        traceDraftIssues(
          draft({
            proposalIds: ["vp_a"],
            derivedDimensions: [
              { proposalId: "vp_a", nearXPx: 10, nearYPx: 20, text: "T".repeat(101) },
            ],
          }),
          proposals(),
        ),
      ).toContain(
        'A forma "① Muro lateral" tem o texto da cota derivada maior que 100 caracteres.',
      );
    });

    it("accepts a derived dimension text within the limit", () => {
      expect(
        traceDraftIssues(
          draft({
            proposalIds: ["vp_a"],
            derivedDimensions: [
              { proposalId: "vp_a", nearXPx: 10, nearYPx: 20, text: "T".repeat(100) },
            ],
          }),
          proposals(),
        ),
      ).toEqual([]);
    });
  });

  describe("leitura amarrada como vão e nota ao mesmo tempo", () => {
    it("refuses the same reading as both a span and a note target", () => {
      expect(
        traceDraftIssues(
          draft({
            proposalIds: ["vp_a"],
            associations: { rd_1: { kind: "single", proposalId: "vp_a" } },
            noteTargets: { rd_1: "vp_a" },
          }),
          proposals(),
        ),
      ).toContain(
        'Uma cota que não está mais no pacote está amarrada como vão e como nota ao mesmo tempo; escolha um destino.',
      );
    });

    it("accepts a reading tied to a span and a different reading tied to a note", () => {
      expect(
        traceDraftIssues(
          draft({
            proposalIds: ["vp_a"],
            associations: { rd_1: { kind: "single", proposalId: "vp_a" } },
            noteTargets: { rd_2: "vp_a" },
          }),
          proposals(),
        ),
      ).toEqual([]);
    });
  });

  describe("contexto (readings, selectedAssociations, dimensões da imagem)", () => {
    it("does not run the context-only rules when no context is given", () => {
      expect(
        traceDraftIssues(
          draft({
            proposalIds: ["vp_a"],
            associations: { rd_1: { kind: "single", proposalId: "vp_a" } },
          }),
          proposals(),
        ),
      ).toEqual([]);
    });

    it("requires the cited reading to exist in the packet and be confirmed", () => {
      const missing = traceDraftIssues(
        draft({
          proposalIds: ["vp_a"],
          associations: { rd_missing: { kind: "single", proposalId: "vp_a" } },
        }),
        proposals(),
        null,
        context({ readings: [] }),
      );
      const unconfirmed = traceDraftIssues(
        draft({
          proposalIds: ["vp_a"],
          associations: { rd_1: { kind: "single", proposalId: "vp_a" } },
        }),
        proposals(),
        null,
        context({ readings: [reading({ id: "rd_1", status: "proposed" })] }),
      );

      expect(missing).toContain(
        'Uma cota que não está mais no pacote ainda não foi confirmada: decida a leitura antes de amarrar o vão/nota.',
      );
      expect(unconfirmed).toContain(
        'A cota "4,40" ainda não foi confirmada: decida a leitura antes de amarrar o vão/nota.',
      );
    });

    it("accepts a reading that exists in the packet and is confirmed", () => {
      expect(
        traceDraftIssues(
          draft({
            proposalIds: ["vp_a"],
            associations: { rd_1: { kind: "single", proposalId: "vp_a" } },
          }),
          proposals(),
          null,
          context({ readings: [reading({ id: "rd_1" })] }),
        ),
      ).toEqual([]);
    });

    it("requires a declared axis for pair and declared associations, but not for single", () => {
      const pairWithoutAxis = traceDraftIssues(
        draft({
          proposalIds: ["vp_a", "vp_b"],
          associations: { rd_1: { kind: "pair", proposalIds: ["vp_a", "vp_b"] } },
        }),
        proposals(),
        null,
        context({ readings: [reading({ id: "rd_1", raw_text: "6,60", kind: "length" })] }),
      );
      const singleWithoutAxis = traceDraftIssues(
        draft({
          proposalIds: ["vp_a"],
          associations: { rd_1: { kind: "single", proposalId: "vp_a" } },
        }),
        proposals(),
        null,
        context({ readings: [reading({ id: "rd_1", kind: "length" })] }),
      );

      expect(pairWithoutAxis).toContain(
        'A cota "6,60" foi confirmada sem eixo (largura/altura); o vão precisa saber em que direção mede.',
      );
      expect(singleWithoutAxis).toEqual([]);
    });

    it("accepts pair and declared associations backed by a width or height reading", () => {
      expect(
        traceDraftIssues(
          draft({
            proposalIds: ["vp_a", "vp_b"],
            associations: { rd_1: { kind: "pair", proposalIds: ["vp_a", "vp_b"] } },
          }),
          proposals(),
          null,
          context({ readings: [reading({ id: "rd_1", kind: "width" })] }),
        ),
      ).toEqual([]);
    });

    it("refuses a declared anchor outside the image bounds", () => {
      expect(
        traceDraftIssues(
          draft({
            proposalIds: ["vp_a"],
            associations: {
              rd_1: {
                kind: "declared",
                proposalId: "vp_a",
                spansPx: [[[100, 300], [900, 300]]],
              },
            },
          }),
          proposals(),
          null,
          context({ readings: [reading({ id: "rd_1" })], imageWidthPx: 600, imageHeightPx: 700 }),
        ),
      ).toContain(
        'A cota "4,40" tem uma âncora fora da imagem; ajuste o ponto para dentro do desenho.',
      );
    });

    it("accepts a declared anchor inside the image bounds", () => {
      expect(
        traceDraftIssues(
          draft({
            proposalIds: ["vp_a"],
            associations: {
              rd_1: {
                kind: "declared",
                proposalId: "vp_a",
                spansPx: [[[100, 300], [220, 300]]],
              },
            },
          }),
          proposals(),
          null,
          context({ readings: [reading({ id: "rd_1" })], imageWidthPx: 600, imageHeightPx: 700 }),
        ),
      ).toEqual([]);
    });

    it("refuses a derived dimension point outside the image bounds", () => {
      expect(
        traceDraftIssues(
          draft({
            proposalIds: ["vp_a"],
            derivedDimensions: [{ proposalId: "vp_a", nearXPx: 900, nearYPx: 20 }],
          }),
          proposals(),
          null,
          context({ imageWidthPx: 600, imageHeightPx: 700 }),
        ),
      ).toContain(
        'A forma "① Muro lateral" tem a cota derivada com o ponto fora da imagem; ajuste o ponto para dentro do desenho.',
      );
    });

    it("requires a dimension text's reading to have an inherited or declared span", () => {
      const withoutSpan = traceDraftIssues(
        draft({
          proposalIds: ["vp_a"],
          dimensionTexts: { rd_1: "1,0 x 2,05" },
        }),
        proposals(),
        null,
        context({ readings: [reading({ id: "rd_1" })] }),
      );

      expect(withoutSpan).toContain(
        'Texto de cota sem vão: amarre a cota "4,40" a um elemento antes de declarar o texto.',
      );
    });

    it("accepts a dimension text whose reading has a span declared in this draft", () => {
      expect(
        traceDraftIssues(
          draft({
            proposalIds: ["vp_a"],
            associations: { rd_1: { kind: "single", proposalId: "vp_a" } },
            dimensionTexts: { rd_1: "1,0 x 2,05" },
          }),
          proposals(),
          null,
          context({ readings: [reading({ id: "rd_1" })] }),
        ),
      ).toEqual([]);
    });

    it("accepts a dimension text whose reading has a span inherited from the observational association", () => {
      expect(
        traceDraftIssues(
          draft({
            proposalIds: ["vp_a"],
            dimensionTexts: { rd_1: "1,0 x 2,05" },
          }),
          proposals(),
          null,
          context({
            readings: [reading({ id: "rd_1" })],
            selectedAssociations: { rd_1: "vp_a" },
          }),
        ),
      ).toEqual([]);
    });
  });
});

function residualSummary(
  overrides: Partial<TraceResidualSummary> = {},
): TraceResidualSummary {
  return {
    count: 0,
    failed_count: 0,
    worst_code: null,
    worst_absolute_error_m: null,
    worst_tolerance_m: null,
    ...overrides,
  };
}

describe("traceResidualSummaryLabel", () => {
  it("does not invent a sentence when there is nothing to summarise", () => {
    expect(traceResidualSummaryLabel(null)).toBeNull();
    expect(traceResidualSummaryLabel(residualSummary({ count: 0 }))).toBeNull();
  });

  it("reports a clean pass with a decimal comma and stays factual with a failure", () => {
    expect(
      traceResidualSummaryLabel(
        residualSummary({
          count: 27,
          failed_count: 0,
          worst_code: "SPAN_RESIDUAL_X",
          worst_absolute_error_m: 0.003,
          worst_tolerance_m: 0.005,
        }),
      ),
    ).toBe(
      "27 cotas conferidas contra a geometria; a pior diferença foi 0,003 m no trecho medido na horizontal, dentro da tolerância de 0,005 m.",
    );

    expect(
      traceResidualSummaryLabel(
        residualSummary({
          count: 27,
          failed_count: 2,
          worst_code: "GAP_RESIDUAL_X",
          worst_absolute_error_m: 0.012,
          worst_tolerance_m: 0.005,
        }),
      ),
    ).toBe(
      "2 de 27 cotas não fecham com a geometria dentro da tolerância; a pior diferença é de 0,012 m no vão medido na horizontal, contra tolerância de 0,005 m.",
    );
  });

  it("keeps the singular for a single checked dimension", () => {
    expect(
      traceResidualSummaryLabel(
        residualSummary({ count: 1, failed_count: 0 }),
      ),
    ).toBe("1 cota conferida contra a geometria.");
  });

  it("falls back to a generic clause for an unknown residual code", () => {
    expect(
      traceResidualSummaryLabel(
        residualSummary({
          count: 5,
          failed_count: 0,
          worst_code: "SOMETHING_NEW",
          worst_absolute_error_m: 0.001,
          worst_tolerance_m: 0.002,
        }),
      ),
    ).toBe(
      "5 cotas conferidas contra a geometria; a pior diferença foi 0,001 m na pior cota conferida, dentro da tolerância de 0,002 m.",
    );
  });

  it("keeps only the first clause when the worst residual is not declared", () => {
    expect(
      traceResidualSummaryLabel(residualSummary({ count: 4, failed_count: 0 })),
    ).toBe("4 cotas conferidas contra a geometria.");
    expect(
      traceResidualSummaryLabel(residualSummary({ count: 4, failed_count: 1 })),
    ).toBe("1 de 4 cotas não fecham com a geometria dentro da tolerância.");
  });
});

describe("spanAxisIssue", () => {
  it("asks for the axis on a pair and on a declared span", () => {
    const withoutAxis = reading({ raw_text: "6,60", kind: "length" });

    expect(
      spanAxisIssue(withoutAxis, {
        kind: "pair",
        proposalIds: ["vp_a", "vp_b"],
      }),
    ).toBe(
      'A cota "6,60" foi confirmada sem eixo (largura/altura); o vão precisa saber em que direção mede.',
    );
    expect(
      spanAxisIssue(withoutAxis, {
        kind: "declared",
        proposalId: "vp_a",
        spansPx: [
          [
            [10, 10],
            [20, 20],
          ],
        ],
      }),
    ).toContain("sem eixo");
  });

  it("stays quiet for a single shape, for width/height and for a reading that vanished", () => {
    expect(
      spanAxisIssue(reading({ kind: "length" }), {
        kind: "single",
        proposalId: "vp_a",
      }),
    ).toBeNull();
    expect(
      spanAxisIssue(reading({ kind: "width" }), {
        kind: "pair",
        proposalIds: ["vp_a", "vp_b"],
      }),
    ).toBeNull();
    expect(
      spanAxisIssue(reading({ kind: "height" }), {
        kind: "pair",
        proposalIds: ["vp_a", "vp_b"],
      }),
    ).toBeNull();
    expect(
      spanAxisIssue(undefined, { kind: "pair", proposalIds: ["vp_a", "vp_b"] }),
    ).toBeNull();
  });

  it("says the same sentence the aggregated list says", () => {
    const withoutAxis = reading({ raw_text: "6,60", kind: "length" });

    expect(
      traceDraftIssues(
        draft({
          proposalIds: ["vp_a", "vp_b"],
          associations: { rd_1: { kind: "pair", proposalIds: ["vp_a", "vp_b"] } },
        }),
        proposals(),
        null,
        context({ readings: [withoutAxis] }),
      ),
    ).toContain(
      spanAxisIssue(withoutAxis, {
        kind: "pair",
        proposalIds: ["vp_a", "vp_b"],
      }),
    );
  });
});

describe("defaultFlagsForProposal", () => {
  function flagContext(
    overrides: Partial<ProposalFlagContext> = {},
  ): ProposalFlagContext {
    return {
      readings: [],
      selectedAssociations: {},
      associations: {},
      ...overrides,
    };
  }

  it("starts a shape without any confirmed dimension as drawn", () => {
    expect(defaultFlagsForProposal("vp_a", flagContext())).toEqual({
      freeform: true,
    });
  });

  it("leaves a shape measured by an inherited confirmed reading alone", () => {
    expect(
      defaultFlagsForProposal(
        "vp_a",
        flagContext({
          readings: [reading({ id: "rd_1" })],
          selectedAssociations: { rd_1: "vp_a" },
        }),
      ),
    ).toEqual({ freeform: false });
  });

  it("counts a span declared in this acceptance, including one leg of a pair", () => {
    expect(
      defaultFlagsForProposal(
        "vp_b",
        flagContext({
          readings: [reading({ id: "rd_1" })],
          associations: {
            rd_1: { kind: "pair", proposalIds: ["vp_a", "vp_b"] },
          },
        }),
      ),
    ).toEqual({ freeform: false });
  });

  it("ignores a reading that is not confirmed: doubt does not measure anything", () => {
    expect(
      defaultFlagsForProposal(
        "vp_a",
        flagContext({
          readings: [reading({ id: "rd_1", status: "proposed" })],
          selectedAssociations: { rd_1: "vp_a" },
        }),
      ),
    ).toEqual({ freeform: true });
  });
});

describe("withDefaultProposalFlags", () => {
  const emptyContext: ProposalFlagContext = {
    readings: [],
    selectedAssociations: {},
    associations: {},
  };

  it("marks only the shapes that just entered the acceptance", () => {
    const next = withDefaultProposalFlags(
      draft({ proposalIds: ["vp_a"] }),
      ["vp_b"],
      emptyContext,
    );

    expect([...next.freeform]).toEqual(["vp_b"]);
  });

  it("does not touch a declaration the reviewer already changed", () => {
    const measured: ProposalFlagContext = {
      readings: [reading({ id: "rd_1" })],
      selectedAssociations: { rd_1: "vp_a" },
      associations: {},
    };
    const withUserChoice = draft({ freeform: new Set(["vp_a"]) });

    expect([
      ...withDefaultProposalFlags(withUserChoice, ["vp_b"], measured).freeform,
    ]).toEqual(["vp_a", "vp_b"]);
    expect(withDefaultProposalFlags(withUserChoice, [], measured)).toBe(
      withUserChoice,
    );
  });

  it("marking the same shape again does not duplicate the declaration", () => {
    const once = withDefaultProposalFlags(draft(), ["vp_a"], emptyContext);
    const twice = withDefaultProposalFlags(once, ["vp_a"], emptyContext);

    expect([...twice.freeform]).toEqual(["vp_a"]);
  });
});

describe("traceSolveInFlight", () => {
  it("is false when nothing was sent yet", () => {
    expect(traceSolveInFlight(null)).toBe(false);
  });

  it("is true while queued", () => {
    expect(traceSolveInFlight(traceSolve({ status: "QUEUED" }))).toBe(true);
  });

  it("is true while running", () => {
    expect(traceSolveInFlight(traceSolve({ status: "RUNNING" }))).toBe(true);
  });

  it("is false once completed", () => {
    expect(traceSolveInFlight(traceSolve({ status: "COMPLETED" }))).toBe(
      false,
    );
  });

  it("is false once failed", () => {
    expect(traceSolveInFlight(traceSolve({ status: "FAILED" }))).toBe(false);
  });
});

describe("traceSolveStatusLabel", () => {
  it("says nothing was sent before the first acceptance", () => {
    expect(traceSolveStatusLabel(null)).toBe(
      "Nenhum aceite de traçado enviado.",
    );
  });

  it("follows the queue and the run", () => {
    expect(traceSolveStatusLabel(traceSolve({ status: "QUEUED" }))).toBe(
      "Aceite de traçado na fila.",
    );
    expect(traceSolveStatusLabel(traceSolve({ status: "RUNNING" }))).toBe(
      "Resolvendo o traçado…",
    );
  });

  it("counts the resolved geometry by precision", () => {
    expect(
      traceSolveStatusLabel(
        traceSolve({
          status: "COMPLETED",
          solve_status: "solved_unapproved",
          exact_entity_count: 12,
          approximate_entity_count: 4,
        }),
      ),
    ).toBe("Traçado resolvido — 12 elementos exatos e 4 aproximados.");
    expect(
      traceSolveStatusLabel(
        traceSolve({
          status: "COMPLETED",
          solve_status: "solved_unapproved",
          exact_entity_count: 1,
          approximate_entity_count: 1,
        }),
      ),
    ).toBe("Traçado resolvido — 1 elemento exato e 1 aproximado.");
  });

  it("counts the pending blockers when the trace needs review", () => {
    expect(
      traceSolveStatusLabel(
        traceSolve({
          status: "COMPLETED",
          solve_status: "review_required",
          blockers: ["TRACE_HUMAN_CONFIRMATION_REQUIRED:rd_1"],
        }),
      ),
    ).toBe("O traçado precisa de revisão — 1 pendência.");
    expect(
      traceSolveStatusLabel(
        traceSolve({
          status: "COMPLETED",
          solve_status: "review_required",
          blockers: ["A:rd_1", "B:rd_2"],
        }),
      ),
    ).toBe("O traçado precisa de revisão — 2 pendências.");
  });

  it("explains a revision that moved as an instruction, not as an error", () => {
    expect(
      traceSolveStatusLabel(
        traceSolve({
          status: "COMPLETED",
          solve_status: "conflict",
          failure_code: "REVISION_MOVED",
        }),
      ),
    ).toBe(
      "Outra decisão entrou antes deste aceite; refaça o traçado sobre a versão nova.",
    );
  });

  it("keeps the failure code visible and survives its absence", () => {
    expect(
      traceSolveStatusLabel(
        traceSolve({ status: "FAILED", failure_code: "TRACE_STAGE_FAILED" }),
      ),
    ).toBe("O traçado falhou (TRACE_STAGE_FAILED).");
    expect(traceSolveStatusLabel(traceSolve({ status: "FAILED" }))).toBe(
      "O traçado falhou (causa não registrada).",
    );
  });

  it("stays readable when the solve status is not declared", () => {
    expect(traceSolveStatusLabel(traceSolve({ status: "COMPLETED" }))).toBe(
      "Traçado concluído.",
    );
  });
});
