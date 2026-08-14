import { describe, expect, it } from "vitest";

import type { ExportArtifact, Review } from "./api";
import {
  approvalReadiness,
  deriveAcceptedApproximations,
  emptyApprovalForm,
  exportInFlight,
  exportStatusLabel,
  pendingScopeCriteria,
} from "./approval";

function review(overrides: Partial<Review> = {}): Review {
  return {
    job_id: "job",
    review_id: "review",
    version: 1,
    packet: { readings: [] },
    associations: { candidates: [] },
    proposals: null,
    selected_associations: {},
    calibration: null,
    proposal_decisions: [],
    issues: [],
    blockers: [],
    required_criteria: [],
    scene: {
      id: "scene",
      version: 1,
      approved: false,
      entities: [
        {
          id: "exact-1",
          kind: "line",
          precision: "exact",
          geometry: { type: "line" },
        },
      ],
      issues: [],
    },
    preview_urls: {},
    ...overrides,
  };
}

const completeForm = {
  ...emptyApprovalForm,
  sourceEvidenceChecked: true,
  geometryChecked: true,
  limitationsAcknowledged: true,
  statement: "Geometria conferida contra a evidência protegida do levantamento.",
};

describe("deriveAcceptedApproximations", () => {
  it("lists the traced scene's approximate entities even without proposal decisions", () => {
    const current = review({
      proposal_decisions: [],
      scene: {
        id: "scene",
        version: 1,
        approved: false,
        entities: [
          {
            id: "trace-approx",
            kind: "line",
            precision: "approximate",
            geometry: { type: "line", start: { x: 0, y: 0 }, end: { x: 0, y: 12 } },
          },
          {
            id: "trace-exact",
            kind: "line",
            precision: "exact",
            geometry: { type: "line", start: { x: 0, y: 0 }, end: { x: 5, y: 0 } },
          },
        ],
        issues: [],
      },
    });

    expect(deriveAcceptedApproximations(current)).toEqual([
      { entityId: "trace-approx", label: "aresta de 12,00 m · aproximada" },
    ]);
  });

  it("does not duplicate an entity accepted by decision that is also approximate in the scene", () => {
    const current = review({
      proposal_decisions: [
        { proposal_id: "vp_1", action: "accept", entity_id: "approx-1" },
      ],
      scene: {
        id: "scene",
        version: 1,
        approved: false,
        entities: [
          {
            id: "approx-1",
            kind: "line",
            precision: "approximate",
            geometry: { type: "line", start: { x: 0, y: 0 }, end: { x: 0, y: 7 } },
          },
        ],
        issues: [],
      },
    });

    expect(deriveAcceptedApproximations(current)).toHaveLength(1);
  });

  it("keeps only accepted decisions that produced an entity", () => {
    const current = review({
      proposal_decisions: [
        { proposal_id: "vp_1", action: "accept", entity_id: "approx-1" },
        { proposal_id: "vp_2", action: "reject" },
        { proposal_id: "vp_3", action: "accept" },
        { proposal_id: "vp_4", action: "accept", entity_id: "approx-1" },
      ],
    });

    expect(deriveAcceptedApproximations(current)).toEqual([
      { entityId: "approx-1", label: "elemento da cena" },
    ]);
  });

  it("describes the accepted entity so the approval text carries no identifier", () => {
    const current = review({
      proposal_decisions: [
        { proposal_id: "vp_1", action: "accept", entity_id: "approx-1" },
      ],
      scene: {
        id: "scene",
        version: 1,
        approved: false,
        entities: [
          {
            id: "approx-1",
            kind: "line",
            precision: "approximate",
            geometry: {
              type: "line",
              start: { x: 0, y: 0 },
              end: { x: 0, y: 33.9 },
            },
          },
        ],
        issues: [],
      },
    });

    expect(deriveAcceptedApproximations(current)).toEqual([
      { entityId: "approx-1", label: "aresta de 33,90 m · aproximada" },
    ]);
  });
});

const PERIMETER = {
  code: "ACC_GUA_001",
  text: "Perímetro, linha central, círculo, áreas e gols são entidades CAD limpas.",
};
const BLEACHERS = {
  code: "ACC_GUA_002",
  text: "A arquibancada aparece no desenho com a cota declarada na folha.",
};

/** Uma revisão cujos critérios do caso estão todos abertos na cena. */
function openCriteria(criteria: { code: string; text: string }[]): Review {
  return review({
    required_criteria: criteria,
    scene: {
      id: "scene",
      version: 1,
      approved: false,
      entities: [],
      issues: criteria.map((criterion) => ({
        code: criterion.code,
        severity: "critical",
        message: criterion.text,
        status: "open",
      })),
    },
  });
}

describe("pendingScopeCriteria", () => {
  it("lists only declared criteria that are still open", () => {
    const current = review({
      required_criteria: [PERIMETER, BLEACHERS],
      scene: {
        id: "scene",
        version: 1,
        approved: false,
        entities: [],
        issues: [
          { code: "ACC_GUA_001", severity: "critical", message: "", status: "open" },
          {
            code: "ACC_GUA_002",
            severity: "critical",
            message: "",
            status: "accepted",
          },
        ],
      },
    });

    expect(pendingScopeCriteria(current)).toEqual([PERIMETER]);
  });
});

describe("approvalReadiness", () => {
  it("approves once every verification is explicit", () => {
    expect(approvalReadiness(review(), completeForm)).toEqual({
      canApprove: true,
      reasons: [],
    });
  });

  it("refuses without a scene", () => {
    const readiness = approvalReadiness(review({ scene: null }), completeForm);
    expect(readiness.canApprove).toBe(false);
    expect(readiness.reasons).toContain("A cena métrica ainda não foi criada.");
  });

  it("names each missing verification", () => {
    const readiness = approvalReadiness(review(), emptyApprovalForm);
    expect(readiness.canApprove).toBe(false);
    expect(readiness.reasons).toHaveLength(4);
  });

  it("refuses a statement shorter than twenty characters", () => {
    const readiness = approvalReadiness(review(), {
      ...completeForm,
      statement: "curto",
    });
    expect(readiness.canApprove).toBe(false);
    expect(readiness.reasons).toContain(
      "A declaração precisa ter entre 20 e 500 caracteres.",
    );
  });

  it("accepts traced approximate geometry: the batch acceptance already covered it", () => {
    const current = review({
      scene: {
        id: "scene",
        version: 1,
        approved: false,
        entities: [
          {
            id: "approx-1",
            kind: "circle",
            precision: "approximate",
            geometry: { type: "circle" },
          },
        ],
        issues: [],
      },
    });

    const readiness = approvalReadiness(current, completeForm);
    expect(readiness.canApprove).toBe(true);
    expect(readiness.reasons).not.toContain(
      "Existe geometria aproximada na cena que não foi aceita explicitamente.",
    );
  });

  it("never lets a geometry blocker be acknowledged away", () => {
    const current = review({
      required_criteria: [PERIMETER],
      scene: {
        id: "scene",
        version: 1,
        approved: false,
        entities: [],
        issues: [
          {
            code: "NUMERIC_RESIDUAL_EXCEEDS_TOLERANCE",
            severity: "critical",
            message: "",
            status: "open",
          },
        ],
      },
    });

    const readiness = approvalReadiness(current, {
      ...completeForm,
      acknowledgedCriteria: ["NUMERIC_RESIDUAL_EXCEEDS_TOLERANCE", "ACC_GUA_001"],
    });

    expect(readiness.canApprove).toBe(false);
    expect(readiness.reasons.join(" ")).toContain(
      "NUMERIC_RESIDUAL_EXCEEDS_TOLERANCE",
    );
  });

  it("names the criterion text when a declaration is missing", () => {
    const readiness = approvalReadiness(openCriteria([PERIMETER]), completeForm);

    expect(readiness.canApprove).toBe(false);
    expect(readiness.reasons.join(" ")).toContain(PERIMETER.text);
    expect(readiness.reasons.join(" ")).toContain(
      "coberto pela cena ou pendente reconhecido",
    );
  });

  it("accepts one declaration per criterion, covered or acknowledged", () => {
    const current = openCriteria([PERIMETER, BLEACHERS]);

    expect(
      approvalReadiness(current, {
        ...completeForm,
        coveredCriteria: [PERIMETER.code],
      }).reasons.join(" "),
    ).toContain(BLEACHERS.text);
    expect(
      approvalReadiness(current, {
        ...completeForm,
        coveredCriteria: [PERIMETER.code],
        acknowledgedCriteria: [BLEACHERS.code],
      }),
    ).toEqual({ canApprove: true, reasons: [] });
  });

  it("clears a pending criterion by coverage the same way acknowledgement does", () => {
    const current = openCriteria([PERIMETER]);

    expect(
      approvalReadiness(current, {
        ...completeForm,
        coveredCriteria: [PERIMETER.code],
      }).canApprove,
    ).toBe(true);
    expect(
      approvalReadiness(current, {
        ...completeForm,
        acknowledgedCriteria: [PERIMETER.code],
      }).canApprove,
    ).toBe(true);
  });

  it("refuses the same criterion declared covered and pending", () => {
    const readiness = approvalReadiness(openCriteria([PERIMETER]), {
      ...completeForm,
      coveredCriteria: [PERIMETER.code],
      acknowledgedCriteria: [PERIMETER.code],
    });

    expect(readiness.canApprove).toBe(false);
    expect(readiness.reasons).toContain(
      `Um critério não pode ser coberto e pendente ao mesmo tempo: ${PERIMETER.code}.`,
    );
  });
});

describe("exportStatusLabel", () => {
  it("covers every artifact state", () => {
    const base: ExportArtifact = {
      export_id: "export",
      job_id: "job",
      scene_revision_id: "scene",
      format: "dxf",
      status: "QUEUED",
      audit_status: null,
      dxf_sha256: null,
      failure_code: null,
      audit_errors: [],
      package_url: null,
    };

    expect(exportStatusLabel(null)).toBe("Nenhuma exportação solicitada.");
    expect(exportStatusLabel(base)).toBe("Exportação na fila.");
    expect(exportStatusLabel({ ...base, status: "RUNNING" })).toContain("auditando");
    expect(exportStatusLabel({ ...base, status: "COMPLETED" })).toContain("disponível");
    expect(
      exportStatusLabel({
        ...base,
        status: "FAILED",
        failure_code: "EXPORT_AUDIT_FAILED",
      }),
    ).toContain("EXPORT_AUDIT_FAILED");
  });
});

describe("exportInFlight", () => {
  const base: ExportArtifact = {
    export_id: "export",
    job_id: "job",
    scene_revision_id: "scene",
    format: "dxf",
    status: "QUEUED",
    audit_status: null,
    dxf_sha256: null,
    failure_code: null,
    audit_errors: [],
    package_url: null,
  };

  it("holds the button while the worker still owns the export", () => {
    expect(exportInFlight(base)).toBe(true);
    expect(exportInFlight({ ...base, status: "RUNNING" })).toBe(true);
  });

  it("frees a new export before the first one and after a failed audit", () => {
    expect(exportInFlight(null)).toBe(false);
    expect(
      exportInFlight({
        ...base,
        status: "FAILED",
        failure_code: "EXPORT_AUDIT_FAILED",
        audit_errors: ["ENTITY_WITHOUT_PROVENANCE"],
      }),
    ).toBe(false);
  });

  it("frees a new export after a completed package: the scene may have moved", () => {
    expect(exportInFlight({ ...base, status: "COMPLETED" })).toBe(false);
  });
});
