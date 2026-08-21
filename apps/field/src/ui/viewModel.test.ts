import { describe, expect, it } from "vitest";

import type { Measurement, Segment, Survey, SurveyPoint } from "../domain/types";
import { validateSurvey, type Finding } from "../domain/validation";
import {
  CANVAS_HEIGHT_MM,
  CANVAS_WIDTH_MM,
  DEFAULT_TOLERANCE_MM,
  buildDivergenceView,
  buildSegmentViews,
  confirmMeasurementLabel,
  findCriticalDivergence,
  formatDifference,
  formatMmAsMeters,
  legendChips,
  metersInputToMm,
  pointLabels,
  pressBackspace,
  pressComma,
  pressDigit,
  segmentLabelPosition,
  segmentLabelRotation,
  segmentLabels,
  selectPointForSegment,
  touchToMm,
} from "./viewModel";

const NOW = "2026-08-21T12:00:00.000Z";

function point(id: string, x_mm: number, y_mm: number): SurveyPoint {
  return { id, x_mm, y_mm, created_at: NOW };
}

function segment(id: string, from: string, to: string): Segment {
  return { id, from_point_id: from, to_point_id: to, created_at: NOW };
}

function measurement(overrides: Partial<Measurement> & { id: string }): Measurement {
  return {
    value_mm: 1000,
    kind: "length",
    instrument: "não informado",
    status: "confirmed",
    created_at: NOW,
    ...overrides,
  };
}

function surveyWith(overrides: Partial<Survey> = {}): Survey {
  return {
    id: "survey-1",
    name: "Levantamento de campo",
    points: [],
    segments: [],
    measurements: [],
    photo_anchors: [],
    elements: [],
    observations: [],
    created_at: NOW,
    updated_at: NOW,
    ...overrides,
  };
}

describe("touchToMm", () => {
  const world = { widthMm: 1000, heightMm: 1000 };

  it("converte o centro de um retângulo sem letterbox", () => {
    expect(touchToMm({ x: 50, y: 50 }, { width: 100, height: 100 }, world)).toEqual({
      x_mm: 500,
      y_mm: 500,
    });
  });

  it("desconta a tarja do letterbox quando o retângulo é mais largo que o mundo", () => {
    // 200 × 100 com mundo quadrado: escala 0,1, desenho de 100 px centrado (tarja de 50).
    expect(touchToMm({ x: 100, y: 50 }, { width: 200, height: 100 }, world)).toEqual({
      x_mm: 500,
      y_mm: 500,
    });
    expect(touchToMm({ x: 50, y: 0 }, { width: 200, height: 100 }, world)).toEqual({
      x_mm: 0,
      y_mm: 0,
    });
  });

  it("devolve null para toque na tarja, fora do desenho", () => {
    expect(touchToMm({ x: 10, y: 50 }, { width: 200, height: 100 }, world)).toBeNull();
  });

  it("devolve null para retângulo degenerado (elemento ainda sem layout)", () => {
    expect(touchToMm({ x: 0, y: 0 }, { width: 0, height: 0 }, world)).toBeNull();
  });

  it("devolve milímetros inteiros — nunca float", () => {
    const mm = touchToMm({ x: 33, y: 77 }, { width: 100, height: 100 }, world);
    expect(mm).not.toBeNull();
    expect(Number.isInteger(mm?.x_mm)).toBe(true);
    expect(Number.isInteger(mm?.y_mm)).toBe(true);
  });

  it("usa o mundo padrão do croqui quando nenhum é passado", () => {
    expect(touchToMm({ x: 0, y: 0 }, { width: 360, height: 472.5 })).toEqual({
      x_mm: 0,
      y_mm: 0,
    });
    expect(touchToMm({ x: 360, y: 472.5 }, { width: 360, height: 472.5 })).toEqual({
      x_mm: CANVAS_WIDTH_MM,
      y_mm: CANVAS_HEIGHT_MM,
    });
  });
});

describe("metros com vírgula ↔ mm", () => {
  it("converte metros com vírgula em mm inteiros", () => {
    expect(metersInputToMm("7,35")).toBe(7350);
    expect(metersInputToMm("7")).toBe(7000);
    expect(metersInputToMm("12,4")).toBe(12400);
    expect(metersInputToMm("0,005")).toBe(5);
  });

  it("recusa entrada incompleta ou fora do teclado do app", () => {
    expect(metersInputToMm("")).toBeNull();
    expect(metersInputToMm(",")).toBeNull();
    expect(metersInputToMm("7,")).toBeNull();
    expect(metersInputToMm("7.35")).toBeNull();
    expect(metersInputToMm("abc")).toBeNull();
    expect(metersInputToMm("7,3567")).toBeNull();
  });

  it("formata mm em metros com vírgula, duas casas por padrão", () => {
    expect(formatMmAsMeters(7350)).toBe("7,35");
    expect(formatMmAsMeters(12000)).toBe("12,00");
    expect(formatMmAsMeters(6200)).toBe("6,20");
    expect(formatMmAsMeters(5)).toBe("0,005");
    expect(formatMmAsMeters(7355)).toBe("7,355");
  });

  it("ida e volta preserva o valor", () => {
    for (const valueMm of [7350, 12400, 9800, 6200, 5, 1]) {
      expect(metersInputToMm(formatMmAsMeters(valueMm))).toBe(valueMm);
    }
  });

  it("escreve a diferença por extenso como a prancha 4b", () => {
    expect(formatDifference(150)).toBe("15 cm");
    expect(formatDifference(50)).toBe("5 cm");
    expect(formatDifference(8)).toBe("8 mm");
    expect(formatDifference(1200)).toBe("1,20 m");
  });
});

describe("teclado numérico", () => {
  it("digita respeitando uma vírgula e três casas", () => {
    let display = "";
    for (const key of ["7", ",", "3", "5"]) {
      display = key === "," ? pressComma(display) : pressDigit(display, key);
    }
    expect(display).toBe("7,35");
    expect(pressComma(display)).toBe("7,35");
    expect(pressDigit(pressDigit(display, "6"), "9")).toBe("7,356");
  });

  it("vírgula sem inteiro digitado começa em 0,", () => {
    expect(pressComma("")).toBe("0,");
    expect(pressDigit(pressComma(""), "5")).toBe("0,5");
  });

  it("não deixa zero à esquerda nem estoura os inteiros", () => {
    expect(pressDigit("0", "7")).toBe("7");
    expect(pressDigit("1234", "5")).toBe("1234");
  });

  it("apaga o último dígito", () => {
    expect(pressBackspace("7,35")).toBe("7,3");
    expect(pressBackspace("")).toBe("");
  });

  it("a confirmação repete a frase inteira, e o desabilitado diz o porquê", () => {
    expect(confirmMeasurementLabel("7,35", "S5")).toBe("Confirmar 7,35 m para S5");
    expect(confirmMeasurementLabel("", "S5")).toBe("Confirmar (digite a medida de S5)");
  });
});

describe("seleção de par de pontos", () => {
  it("primeiro toque escolhe, segundo fecha o par", () => {
    const first = selectPointForSegment(null, "p1");
    expect(first).toEqual({ first: "p1", pair: null });
    expect(selectPointForSegment(first.first, "p2")).toEqual({
      first: null,
      pair: ["p1", "p2"],
    });
  });

  it("tocar de novo no mesmo ponto cancela a escolha", () => {
    expect(selectPointForSegment("p1", "p1")).toEqual({ first: null, pair: null });
  });
});

describe("rótulos", () => {
  it("nomeia segmentos e pontos por ordem de criação", () => {
    const survey = surveyWith({
      points: [point("a", 0, 0), point("b", 1000, 0)],
      segments: [segment("s-a", "a", "b")],
    });
    expect(segmentLabels(survey.segments).get("s-a")).toBe("S1");
    expect(pointLabels(survey.points).get("b")).toBe("P2");
  });
});

describe("decoração do desenho a partir dos findings do motor", () => {
  const survey = surveyWith({
    points: [point("p1", 0, 0), point("p2", 4000, 0), point("p3", 4000, 3000)],
    segments: [segment("s1", "p1", "p2"), segment("s2", "p2", "p3")],
    measurements: [
      measurement({ id: "m1", value_mm: 4000, from_point_id: "p1", to_point_id: "p2" }),
    ],
  });

  it("tracejado e rótulo escrito só onde SEGMENT_WITHOUT_MEASUREMENT apontou", () => {
    const findings = validateSurvey(survey, { toleranceMm: DEFAULT_TOLERANCE_MM });
    const views = buildSegmentViews(survey, findings);

    const measured = views.find((view) => view.id === "s1");
    const missing = views.find((view) => view.id === "s2");
    expect(measured?.without_measurement).toBe(false);
    expect(measured?.label_text).toBe("4,00 m ✓");
    expect(measured?.measurement_mm).toBe(4000);
    expect(missing?.without_measurement).toBe(true);
    expect(missing?.label_text).toBe("S2 · sem medida");
    expect(missing?.measurement_mm).toBeNull();
  });

  it("sem finding para o segmento, a UI não inventa a decoração", () => {
    // Mesmo survey, lista de findings vazia: nenhum tracejado, porque a regra é do motor.
    const views = buildSegmentViews(survey, []);
    expect(views.every((view) => !view.without_measurement)).toBe(true);
  });

  it("segmento com medida só de rascunho continua sem cota", () => {
    const draft = surveyWith({
      points: survey.points,
      segments: survey.segments,
      measurements: [
        measurement({
          id: "m2",
          value_mm: 3000,
          from_point_id: "p2",
          to_point_id: "p3",
          status: "draft",
        }),
      ],
    });
    const findings = validateSurvey(draft, { toleranceMm: DEFAULT_TOLERANCE_MM });
    const view = buildSegmentViews(draft, findings).find((candidate) => candidate.id === "s2");
    expect(view?.measurement_mm).toBeNull();
    expect(view?.label_text).toBe("S2 · sem medida");
  });

  it("os selos da legenda contam medidas confirmadas e segmentos sem medida", () => {
    const findings = validateSurvey(survey, { toleranceMm: DEFAULT_TOLERANCE_MM });
    expect(legendChips(survey, findings)).toEqual({
      ok: "1 medida ✓",
      error: "1 segmento sem medida",
    });
    expect(legendChips(surveyWith(), [])).toEqual({ ok: null, error: null });
  });

  it("a cota é escrita ao longo do segmento, sempre legível da esquerda para a direita", () => {
    expect(segmentLabelRotation({ x1_mm: 0, y1_mm: 0, x2_mm: 4000, y2_mm: 0 })).toBe(0);
    expect(segmentLabelRotation({ x1_mm: 0, y1_mm: 0, x2_mm: 0, y2_mm: 4000 })).toBe(90);
    // De baixo para cima: gira 90° em vez de 270°, para o texto não sair de cabeça baixa.
    expect(segmentLabelRotation({ x1_mm: 0, y1_mm: 4000, x2_mm: 0, y2_mm: 0 })).toBe(90);
    expect(segmentLabelRotation({ x1_mm: 4000, y1_mm: 0, x2_mm: 0, y2_mm: 0 })).toBe(0);
  });

  it("a cota vai para o lado de fora do desenho", () => {
    const centroid = { x_mm: 2000, y_mm: 2000 };
    const above = segmentLabelPosition(
      { x1_mm: 0, y1_mm: 0, x2_mm: 4000, y2_mm: 0 },
      centroid,
      900,
    );
    expect(above.x_mm).toBe(2000);
    expect(above.y_mm).toBe(-900);
  });
});

describe("divergência entre duas leituras", () => {
  const survey = surveyWith({
    points: [point("p1", 0, 0), point("p2", 12400, 0)],
    segments: [segment("s1", "p1", "p2")],
    measurements: [
      measurement({
        id: "m1",
        value_mm: 12400,
        from_point_id: "p1",
        to_point_id: "p2",
        created_at: "2026-08-21T12:00:00.000Z",
      }),
      measurement({
        id: "m2",
        value_mm: 12550,
        from_point_id: "p1",
        to_point_id: "p2",
        created_at: "2026-08-21T12:05:00.000Z",
      }),
    ],
  });
  const findings = validateSurvey(survey, { toleranceMm: DEFAULT_TOLERANCE_MM });

  it("acha a divergência crítica da medida recém-confirmada", () => {
    const finding = findCriticalDivergence("m2", findings);
    expect(finding?.code).toBe("MEASUREMENT_DIVERGENCE");
    expect(findCriticalDivergence("m3", findings)).toBeNull();
  });

  it("ignora divergência já justificada (vira warning, não reabre a tela)", () => {
    const justified: Finding[] = findings.map((finding) =>
      finding.code === "MEASUREMENT_DIVERGENCE"
        ? { ...finding, severity: "warning" as const }
        : finding,
    );
    expect(findCriticalDivergence("m2", justified)).toBeNull();
  });

  it("monta as duas leituras em ordem, com a diferença por extenso", () => {
    const finding = findCriticalDivergence("m2", findings);
    expect(finding).not.toBeNull();
    const view = buildDivergenceView(survey, finding!, "m2", DEFAULT_TOLERANCE_MM);
    expect(view.readings).toEqual([
      { id: "m1", label: "1ª medição", value_label: "12,40 m" },
      { id: "m2", label: "2ª medição (agora)", value_label: "12,55 m" },
    ]);
    expect(view.difference_mm).toBe(150);
    expect(view.message).toContain("Diferença de 15 cm");
    expect(view.message).toContain("(5 cm)");
  });
});
