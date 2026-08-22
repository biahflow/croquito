import { describe, expect, it } from "vitest";

import type { Measurement, Survey } from "./types";
import { canConclude, summarize, validateSurvey } from "./validation";

const NOW = "2026-08-21T12:00:00.000Z";
const TOLERANCE_MM = 10;

function emptySurvey(): Survey {
  return {
    id: "survey-1",
    name: "Praça de teste",
    points: [],
    segments: [],
    measurements: [],
    photo_anchors: [],
    elements: [],
    observations: [],
    created_at: NOW,
    updated_at: NOW,
  };
}

function confirmedLength(id: string, from: string, to: string, value_mm: number): Measurement {
  return {
    id,
    value_mm,
    kind: "length",
    from_point_id: from,
    to_point_id: to,
    instrument: "trena",
    status: "confirmed",
    created_at: NOW,
  };
}

/** Triângulo 3-4-5 fechado por segmentos e com as três distâncias confirmadas — usado
 * como base "tudo certo" para vários testes negativos. */
function closedTriangleSurvey(): Survey {
  const survey = emptySurvey();
  survey.points = [
    { id: "p1", x_mm: 0, y_mm: 0, created_at: NOW },
    { id: "p2", x_mm: 300, y_mm: 0, created_at: NOW },
    { id: "p3", x_mm: 300, y_mm: 400, created_at: NOW },
  ];
  survey.segments = [
    { id: "s1", from_point_id: "p1", to_point_id: "p2", created_at: NOW },
    { id: "s2", from_point_id: "p2", to_point_id: "p3", created_at: NOW },
    { id: "s3", from_point_id: "p3", to_point_id: "p1", created_at: NOW },
  ];
  survey.measurements = [
    confirmedLength("m1", "p1", "p2", 3000),
    confirmedLength("m2", "p2", "p3", 4000),
    confirmedLength("m3", "p3", "p1", 5000),
  ];
  return survey;
}

describe("OPEN_PERIMETER", () => {
  it("positivo: caminho aberto (ponto de grau 1)", () => {
    const survey = emptySurvey();
    survey.points = [
      { id: "p1", x_mm: 0, y_mm: 0, created_at: NOW },
      { id: "p2", x_mm: 100, y_mm: 0, created_at: NOW },
      { id: "p3", x_mm: 100, y_mm: 100, created_at: NOW },
    ];
    survey.segments = [
      { id: "s1", from_point_id: "p1", to_point_id: "p2", created_at: NOW },
      { id: "s2", from_point_id: "p2", to_point_id: "p3", created_at: NOW },
    ];

    const findings = validateSurvey(survey, { toleranceMm: TOLERANCE_MM });

    expect(findings.some((f) => f.code === "OPEN_PERIMETER" && f.severity === "critical")).toBe(true);
  });

  it("negativo: perímetro fechado (ciclo, sem ponto de grau 1)", () => {
    const findings = validateSurvey(closedTriangleSurvey(), { toleranceMm: TOLERANCE_MM });

    expect(findings.some((f) => f.code === "OPEN_PERIMETER")).toBe(false);
  });
});

describe("SEGMENT_WITHOUT_MEASUREMENT", () => {
  it("positivo: segmento sem nenhuma medida length confirmada", () => {
    const survey = closedTriangleSurvey();
    survey.measurements = survey.measurements.filter((m) => m.id !== "m1");

    const findings = validateSurvey(survey, { toleranceMm: TOLERANCE_MM });

    expect(
      findings.some((f) => f.code === "SEGMENT_WITHOUT_MEASUREMENT" && f.refs.includes("s1")),
    ).toBe(true);
  });

  it("negativo: todo segmento com medida length confirmada", () => {
    const findings = validateSurvey(closedTriangleSurvey(), { toleranceMm: TOLERANCE_MM });

    expect(findings.some((f) => f.code === "SEGMENT_WITHOUT_MEASUREMENT")).toBe(false);
  });
});

describe("TRIANGLE_MISMATCH", () => {
  it("negativo: dentro da tolerância (3-4-5 exato)", () => {
    const findings = validateSurvey(closedTriangleSurvey(), { toleranceMm: TOLERANCE_MM });

    expect(findings.some((f) => f.code === "TRIANGLE_MISMATCH")).toBe(false);
  });

  it("positivo: fora da tolerância (diagonal incompatível com os lados)", () => {
    const survey = closedTriangleSurvey();
    // p1-p2 = 3000, p2-p3 = 4000, mas p3-p1 declarado como 10000 — bem acima de 3000+4000.
    survey.measurements = [
      confirmedLength("m1", "p1", "p2", 3000),
      confirmedLength("m2", "p2", "p3", 4000),
      confirmedLength("m3", "p3", "p1", 10000),
    ];

    const findings = validateSurvey(survey, { toleranceMm: TOLERANCE_MM });

    expect(findings.some((f) => f.code === "TRIANGLE_MISMATCH")).toBe(true);
  });

  it("dentro da tolerância declarada não dispara (folga pequena)", () => {
    const survey = closedTriangleSurvey();
    survey.measurements = [
      confirmedLength("m1", "p1", "p2", 3000),
      confirmedLength("m2", "p2", "p3", 4000),
      // 3000 + 4000 = 7000; 7005 fica dentro de uma tolerância de 10mm.
      confirmedLength("m3", "p3", "p1", 6995),
    ];

    const findings = validateSurvey(survey, { toleranceMm: TOLERANCE_MM });

    expect(findings.some((f) => f.code === "TRIANGLE_MISMATCH")).toBe(false);
  });
});

describe("MEASUREMENT_DIVERGENCE", () => {
  function surveyWithDivergentPair(): Survey {
    const survey = emptySurvey();
    survey.points = [
      { id: "p1", x_mm: 0, y_mm: 0, created_at: NOW },
      { id: "p2", x_mm: 100, y_mm: 0, created_at: NOW },
    ];
    survey.measurements = [
      confirmedLength("m1", "p1", "p2", 1000),
      confirmedLength("m2", "p1", "p2", 1050),
    ];
    return survey;
  }

  it("sem justificativa: critical", () => {
    const findings = validateSurvey(surveyWithDivergentPair(), { toleranceMm: TOLERANCE_MM });

    const finding = findings.find((f) => f.code === "MEASUREMENT_DIVERGENCE");
    expect(finding?.severity).toBe("critical");
  });

  it("com justificativa: warning", () => {
    const survey = surveyWithDivergentPair();
    survey.measurements[1]!.justification = "Segunda medição confirma diferença do piso";

    const findings = validateSurvey(survey, { toleranceMm: TOLERANCE_MM });

    const finding = findings.find((f) => f.code === "MEASUREMENT_DIVERGENCE");
    expect(finding?.severity).toBe("warning");
  });

  it("negativo: dentro da tolerância não diverge", () => {
    const survey = surveyWithDivergentPair();
    survey.measurements[1]!.value_mm = 1005;

    const findings = validateSurvey(survey, { toleranceMm: TOLERANCE_MM });

    expect(findings.some((f) => f.code === "MEASUREMENT_DIVERGENCE")).toBe(false);
  });
});

describe("DANGLING_REFERENCE", () => {
  it("positivo: segmento referencia ponto inexistente", () => {
    const survey = emptySurvey();
    survey.points = [{ id: "p1", x_mm: 0, y_mm: 0, created_at: NOW }];
    survey.segments = [{ id: "s1", from_point_id: "p1", to_point_id: "p9", created_at: NOW }];

    const findings = validateSurvey(survey, { toleranceMm: TOLERANCE_MM });

    expect(
      findings.some((f) => f.code === "DANGLING_REFERENCE" && f.refs.includes("p9")),
    ).toBe(true);
  });

  it("negativo: todas as referências existem", () => {
    const findings = validateSurvey(closedTriangleSurvey(), { toleranceMm: TOLERANCE_MM });

    expect(findings.some((f) => f.code === "DANGLING_REFERENCE")).toBe(false);
  });
});

describe("REQUIRED_ITEM_PENDING", () => {
  it("positivo: item obrigatório pendente", () => {
    const findings = validateSurvey(closedTriangleSurvey(), {
      toleranceMm: TOLERANCE_MM,
      requiredItems: [{ id: "instrumento", label: "Instrumento usado", satisfied: false }],
    });

    expect(
      findings.some((f) => f.code === "REQUIRED_ITEM_PENDING" && f.severity === "warning"),
    ).toBe(true);
  });

  it("negativo: item obrigatório satisfeito", () => {
    const findings = validateSurvey(closedTriangleSurvey(), {
      toleranceMm: TOLERANCE_MM,
      requiredItems: [{ id: "instrumento", label: "Instrumento usado", satisfied: true }],
    });

    expect(findings.some((f) => f.code === "REQUIRED_ITEM_PENDING")).toBe(false);
  });
});

describe("ELEMENT_WITHOUT_PHOTO", () => {
  it("positivo: elemento sem foto ancorada a ele nem a seus pontos", () => {
    const survey = closedTriangleSurvey();
    survey.elements = [{ id: "e1", label: "Banco", point_ids: ["p1"], created_at: NOW }];

    const findings = validateSurvey(survey, { toleranceMm: TOLERANCE_MM });

    expect(
      findings.some((f) => f.code === "ELEMENT_WITHOUT_PHOTO" && f.severity === "warning"),
    ).toBe(true);
  });

  it("negativo: foto ancorada diretamente ao elemento", () => {
    const survey = closedTriangleSurvey();
    survey.elements = [{ id: "e1", label: "Banco", point_ids: ["p1"], created_at: NOW }];
    survey.photo_anchors = [
      { id: "a1", element_id: "e1", local_media_ref: "media://1", created_at: NOW },
    ];

    const findings = validateSurvey(survey, { toleranceMm: TOLERANCE_MM });

    expect(findings.some((f) => f.code === "ELEMENT_WITHOUT_PHOTO")).toBe(false);
  });

  it("negativo: foto ancorada a um ponto do elemento", () => {
    const survey = closedTriangleSurvey();
    survey.elements = [{ id: "e1", label: "Banco", point_ids: ["p1"], created_at: NOW }];
    survey.photo_anchors = [{ id: "a1", point_id: "p1", local_media_ref: "media://1", created_at: NOW }];

    const findings = validateSurvey(survey, { toleranceMm: TOLERANCE_MM });

    expect(findings.some((f) => f.code === "ELEMENT_WITHOUT_PHOTO")).toBe(false);
  });
});

describe("canConclude", () => {
  it("true quando não há finding crítico", () => {
    expect(canConclude([{ code: "REQUIRED_ITEM_PENDING", severity: "warning", message: "x", refs: [] }])).toBe(
      true,
    );
  });

  it("false quando há ao menos um finding crítico", () => {
    expect(
      canConclude([
        { code: "REQUIRED_ITEM_PENDING", severity: "warning", message: "x", refs: [] },
        { code: "OPEN_PERIMETER", severity: "critical", message: "y", refs: [] },
      ]),
    ).toBe(false);
  });
});

describe("summarize", () => {
  it("conta medidas confirmadas, segmentos, críticos e atenções", () => {
    const survey = closedTriangleSurvey();
    survey.elements = [{ id: "e1", label: "Banco", point_ids: ["p1"], created_at: NOW }];
    const findings = validateSurvey(survey, { toleranceMm: TOLERANCE_MM });

    const summary = summarize(survey, findings);

    expect(summary.confirmed_measurements).toBe(3);
    expect(summary.segments).toBe(3);
    expect(summary.critical_count).toBe(findings.filter((f) => f.severity === "critical").length);
    expect(summary.warning_count).toBe(findings.filter((f) => f.severity === "warning").length);
  });
});
