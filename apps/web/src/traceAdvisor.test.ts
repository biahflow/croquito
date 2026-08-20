import { describe, expect, it } from "vitest";

import type {
  Review,
  ReviewReading,
  TraceSolveResponse,
  VisionProposal,
} from "./api";
import { emptyTraceDraft, type TraceDraft } from "./trace";
import { adviseTrace, advisorFixKey, advisorFixLabel } from "./traceAdvisor";

function proposal(id: string, overrides: Partial<VisionProposal> = {}): VisionProposal {
  return {
    id,
    kind: "line",
    precision: "unresolved",
    export: false,
    geometry: {
      type: "line",
      start: { x: 100, y: 100 },
      end: { x: 100, y: 500 },
    },
    ...overrides,
  };
}

const PROPOSALS = [
  proposal("vp_a", { label: "muro" }),
  proposal("vp_b", { label: "campo" }),
  proposal("vp_c", { label: "patamar" }),
  proposal("vp_d", { label: "alambrado" }),
  proposal("vp_e", { label: "portão" }),
];

function reading(
  id: string,
  overrides: Partial<ReviewReading> = {},
): ReviewReading {
  return {
    id,
    raw_text: "6,60",
    kind: "width",
    status: "confirmed",
    value_si: "6.60",
    unit: "m",
    decision: {
      decision_id: `dc_${id}`,
      action: "confirm",
      reviewer_id: "rv_1",
      decided_at: "2026-08-20T12:00:00Z",
    },
    ...overrides,
  };
}

function review(overrides: Partial<Review> = {}): Review {
  return {
    job_id: "0198c0de-0000-7000-8000-00000000000a",
    review_id: "0198c0de-0000-7000-8000-00000000000b",
    version: 4,
    packet: { readings: [reading("rd_1")] },
    associations: { candidates: [] },
    proposals: {
      image_width_px: 1000,
      image_height_px: 1000,
      proposals: PROPOSALS,
    },
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

function solve(overrides: Partial<TraceSolveResponse> = {}): TraceSolveResponse {
  return {
    trace_solve_id: "0198c0de-0000-7000-8000-00000000000d",
    job_id: "0198c0de-0000-7000-8000-00000000000a",
    status: "COMPLETED",
    acceptance_id: "ac_1",
    base_review_version: 4,
    base_scene_version: null,
    solve_status: "review_required",
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

function draft(overrides: Partial<TraceDraft> = {}): TraceDraft {
  return {
    ...emptyTraceDraft(),
    proposalIds: ["vp_a", "vp_b", "vp_c", "vp_d", "vp_e"],
    ...overrides,
  };
}

function candidates(
  readingId: string,
  proposalIds: string[],
): Review["associations"]["candidates"] {
  return proposalIds.map((proposalId) => ({
    reading_id: readingId,
    proposal_id: proposalId,
    proposal_kind: "line",
    relation: "nearest_geometry",
  }));
}

describe("resposta sem diagnóstico", () => {
  it("não produz achado nenhum — job antigo se comporta como antes", () => {
    expect(
      adviseTrace(
        solve({ unapplied_reading_ids: ["rd_1"] }),
        review(),
        draft(),
      ),
    ).toEqual([]);
  });
});

describe("uma causa por vez", () => {
  it("TRACE_TARGET_AS_DRAWN oferece tratar como retangular cada alvo declarado desenhado", () => {
    const findings = adviseTrace(
      solve({
        unapplied_readings: [
          {
            reading_id: "rd_1",
            cause: "TRACE_TARGET_AS_DRAWN",
            target_proposal_ids: ["vp_a", "vp_b"],
          },
        ],
      }),
      review(),
      draft({ freeform: new Set(["vp_a"]) }),
    );
    expect(findings).toHaveLength(1);
    expect(findings[0].rawCode).toBe("TRACE_TARGET_AS_DRAWN");
    expect(findings[0].readingId).toBe("rd_1");
    expect(findings[0].message).toContain("aceita como desenhada");
    // vp_b não está declarada desenhada: não há flag para desfazer nela.
    expect(findings[0].fixes).toEqual([
      { kind: "treat_rectangular", proposalId: "vp_a" },
    ]);
  });

  it("TRACE_TARGET_AS_DRAWN não oferece conserto para forma fora do aceite", () => {
    const findings = adviseTrace(
      solve({
        unapplied_readings: [
          {
            reading_id: "rd_1",
            cause: "TRACE_TARGET_AS_DRAWN",
            target_proposal_ids: ["vp_a"],
          },
        ],
      }),
      review(),
      draft({ proposalIds: ["vp_b"], freeform: new Set(["vp_a"]) }),
    );
    expect(findings[0].fixes).toEqual([]);
  });

  it("TRACE_SPAN_AXIS_UNDECLARED oferece declarar o eixo", () => {
    const findings = adviseTrace(
      solve({
        unapplied_readings: [
          {
            reading_id: "rd_1",
            cause: "TRACE_SPAN_AXIS_UNDECLARED",
            target_proposal_ids: ["vp_a"],
          },
        ],
      }),
      review({ packet: { readings: [reading("rd_1", { kind: "length" })] } }),
      draft(),
    );
    expect(findings[0].message).toContain("não declara em que direção mede");
    expect(findings[0].fixes).toEqual([
      { kind: "declare_axis", readingId: "rd_1" },
    ]);
  });

  it.each([
    "TRACE_SPAN_EDGE_NOT_FOUND",
    "TRACE_SPAN_SAME_BAND",
    "TRACE_SPAN_NOT_ORTHOGONAL",
  ])("%s oferece alternativas de amarração e a correção da leitura", (cause) => {
    const findings = adviseTrace(
      solve({
        unapplied_readings: [
          { reading_id: "rd_1", cause, target_proposal_ids: ["vp_a"] },
        ],
      }),
      review({
        associations: {
          candidates: candidates("rd_1", ["vp_a", "vp_b", "vp_c"]),
        },
      }),
      draft(),
    );
    expect(findings[0].rawCode).toBe(cause);
    expect(findings[0].fixes).toEqual([
      {
        kind: "reassociate",
        readingId: "rd_1",
        proposalId: "vp_b",
        label: "② campo",
      },
      {
        kind: "reassociate",
        readingId: "rd_1",
        proposalId: "vp_c",
        label: "③ patamar",
      },
      { kind: "rectify", readingId: "rd_1" },
    ]);
  });

  it("oferece no máximo três alternativas, na ordem ranqueada da revisão", () => {
    const findings = adviseTrace(
      solve({
        unapplied_readings: [
          {
            reading_id: "rd_1",
            cause: "TRACE_SPAN_EDGE_NOT_FOUND",
            target_proposal_ids: ["vp_a"],
          },
        ],
      }),
      review({
        associations: {
          candidates: candidates("rd_1", ["vp_b", "vp_c", "vp_d", "vp_e"]),
        },
      }),
      draft(),
    );
    const reassociated = findings[0].fixes.filter(
      (fix) => fix.kind === "reassociate",
    );
    expect(reassociated.map((fix) => fix.proposalId)).toEqual([
      "vp_b",
      "vp_c",
      "vp_d",
    ]);
  });

  it("ignora candidato de outra leitura e candidato fora do aceite", () => {
    const findings = adviseTrace(
      solve({
        unapplied_readings: [
          {
            reading_id: "rd_1",
            cause: "TRACE_SPAN_EDGE_NOT_FOUND",
            target_proposal_ids: ["vp_a"],
          },
        ],
      }),
      review({
        associations: {
          candidates: [
            ...candidates("rd_1", ["vp_b", "vp_c"]),
            ...candidates("rd_9", ["vp_d"]),
          ],
        },
      }),
      draft({ proposalIds: ["vp_a", "vp_b"] }),
    );
    expect(
      findings[0].fixes.filter((fix) => fix.kind === "reassociate"),
    ).toEqual([
      {
        kind: "reassociate",
        readingId: "rd_1",
        proposalId: "vp_b",
        label: "② campo",
      },
    ]);
  });

  it.each(["TRACE_NOTE_ZERO_LENGTH", "TRACE_NOTE_UNSUPPORTED_GEOMETRY"])(
    "%s é diagnóstico honesto, sem conserto de um clique",
    (cause) => {
      const findings = adviseTrace(
        solve({
          unapplied_readings: [
            { reading_id: "rd_1", cause, target_proposal_ids: ["vp_a"] },
          ],
        }),
        review({
          associations: { candidates: candidates("rd_1", ["vp_b"]) },
        }),
        draft(),
      );
      expect(findings[0].rawCode).toBe(cause);
      expect(findings[0].message).not.toBe(cause);
      expect(findings[0].fixes).toEqual([]);
    },
  );

  it("TRACE_SPAN_VALUE_OR_DECISION_MISSING se resolve na revisão de cotas, sem botão", () => {
    const findings = adviseTrace(
      solve({
        unapplied_readings: [
          {
            reading_id: "rd_1",
            cause: "TRACE_SPAN_VALUE_OR_DECISION_MISSING",
            target_proposal_ids: [],
          },
        ],
      }),
      review(),
      draft(),
    );
    expect(findings[0].message).toContain("revisão de cotas");
    expect(findings[0].fixes).toEqual([]);
  });

  it("causa desconhecida aparece crua, nunca escondida", () => {
    const findings = adviseTrace(
      solve({
        unapplied_readings: [
          {
            reading_id: "rd_1",
            cause: "TRACE_SOMETHING_NEW",
            target_proposal_ids: [],
          },
        ],
      }),
      review(),
      draft(),
    );
    expect(findings[0].message).toBe("TRACE_SOMETHING_NEW");
    expect(findings[0].rawCode).toBe("TRACE_SOMETHING_NEW");
    expect(findings[0].fixes).toEqual([]);
  });
});

describe("conserto conferido contra o estado atual", () => {
  it("leitura decidida de outro modo depois do aceite não recebe conserto", () => {
    const findings = adviseTrace(
      solve({
        unapplied_readings: [
          {
            reading_id: "rd_1",
            cause: "TRACE_SPAN_EDGE_NOT_FOUND",
            target_proposal_ids: ["vp_a"],
          },
        ],
      }),
      review({
        packet: { readings: [reading("rd_1", { status: "rejected" })] },
        associations: { candidates: candidates("rd_1", ["vp_b"]) },
      }),
      draft(),
    );
    expect(findings).toHaveLength(1);
    expect(findings[0].fixes).toEqual([]);
  });

  it("leitura que não está nesta revisão não recebe conserto", () => {
    const findings = adviseTrace(
      solve({
        unapplied_readings: [
          {
            reading_id: "rd_fora",
            cause: "TRACE_SPAN_EDGE_NOT_FOUND",
            target_proposal_ids: ["vp_a"],
          },
        ],
      }),
      review({
        associations: { candidates: candidates("rd_fora", ["vp_b"]) },
      }),
      draft(),
    );
    expect(findings[0].fixes).toEqual([]);
    expect(findings[0].message).toContain("uma cota do lote");
  });

  it("leitura confirmada sem decisão gravada não oferece correção", () => {
    const findings = adviseTrace(
      solve({
        unapplied_readings: [
          {
            reading_id: "rd_1",
            cause: "TRACE_SPAN_SAME_BAND",
            target_proposal_ids: ["vp_a"],
          },
        ],
      }),
      review({
        packet: { readings: [reading("rd_1", { decision: null })] },
        associations: { candidates: candidates("rd_1", ["vp_b"]) },
      }),
      draft(),
    );
    expect(findings[0].fixes.some((fix) => fix.kind === "rectify")).toBe(false);
  });
});

describe("vão em disputa", () => {
  const contested = {
    axis: "x" as const,
    reading_ids: ["rd_1", "rd_2"],
    values_m: [1.5, 8.6],
    proposal_ids: ["vp_a", "vp_b"],
  };
  const disputed = review({
    packet: {
      readings: [
        reading("rd_1", { raw_text: "1,50" }),
        reading("rd_2", { raw_text: "8,60" }),
      ],
    },
    associations: { candidates: candidates("rd_1", ["vp_c"]) },
  });

  it("nomeia o par pelos textos crus e oferece manter separados", () => {
    const findings = adviseTrace(
      solve({ contested_spans: [contested] }),
      disputed,
      draft(),
    );
    expect(findings).toHaveLength(1);
    expect(findings[0].readingId).toBeUndefined();
    expect(findings[0].rawCode).toBe("contested_spans");
    expect(findings[0].message).toContain('"1,50"');
    expect(findings[0].message).toContain('"8,60"');
    expect(findings[0].fixes).toEqual([
      {
        kind: "reassociate",
        readingId: "rd_1",
        proposalId: "vp_c",
        label: "③ patamar",
      },
      { kind: "rectify", readingId: "rd_1" },
      { kind: "rectify", readingId: "rd_2" },
      { kind: "keep_apart", first: "vp_a", second: "vp_b" },
    ]);
  });

  it("uma forma só não vira par a manter separado", () => {
    const findings = adviseTrace(
      solve({
        contested_spans: [{ ...contested, proposal_ids: ["vp_a"] }],
      }),
      disputed,
      draft(),
    );
    expect(findings[0].fixes.some((fix) => fix.kind === "keep_apart")).toBe(
      false,
    );
  });

  it("par já declarado distinto não é oferecido de novo", () => {
    const findings = adviseTrace(
      solve({ contested_spans: [contested] }),
      disputed,
      draft({
        keepApartPairs: [{ first: "vp_b", second: "vp_a", axis: "x" }],
      }),
    );
    expect(findings[0].fixes.some((fix) => fix.kind === "keep_apart")).toBe(
      false,
    );
  });

  it("entra depois das leituras não aplicadas, na ordem do contrato", () => {
    const findings = adviseTrace(
      solve({
        unapplied_readings: [
          {
            reading_id: "rd_1",
            cause: "TRACE_NOTE_ZERO_LENGTH",
            target_proposal_ids: [],
          },
        ],
        contested_spans: [contested],
      }),
      disputed,
      draft(),
    );
    expect(findings.map((finding) => finding.rawCode)).toEqual([
      "TRACE_NOTE_ZERO_LENGTH",
      "contested_spans",
    ]);
  });
});

describe("botões do consultor", () => {
  it("nomeiam o conserto em língua de obra e têm chave estável", () => {
    expect(
      advisorFixLabel({ kind: "treat_rectangular", proposalId: "vp_a" }),
    ).toBe("Tratar a forma como retangular");
    expect(
      advisorFixLabel({
        kind: "reassociate",
        readingId: "rd_1",
        proposalId: "vp_b",
        label: "② campo",
      }),
    ).toBe("Amarrar a ② campo");
    expect(advisorFixLabel({ kind: "declare_axis", readingId: "rd_1" })).toBe(
      "Declarar o eixo da cota",
    );
    expect(
      advisorFixLabel({ kind: "keep_apart", first: "vp_a", second: "vp_b" }),
    ).toBe("Manter as duas separadas");
    expect(advisorFixLabel({ kind: "rectify", readingId: "rd_1" })).toBe(
      "Corrigir a leitura",
    );
    expect(advisorFixKey({ kind: "rectify", readingId: "rd_1" })).toBe(
      "rectify:rd_1",
    );
    expect(
      advisorFixKey({
        kind: "reassociate",
        readingId: "rd_1",
        proposalId: "vp_b",
        label: "② campo",
      }),
    ).toBe("reassociate:rd_1:vp_b");
  });
});
