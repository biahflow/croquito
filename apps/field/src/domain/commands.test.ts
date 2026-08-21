import { describe, expect, it } from "vitest";

import {
  addElement,
  addMeasurement,
  addObservation,
  addPhotoAnchor,
  addPoint,
  addSegment,
  closePerimeter,
  justifyMeasurement,
  undoLast,
  type CommandHistoryEntry,
} from "./commands";
import type { Survey } from "./types";

const NOW = "2026-08-21T12:00:00.000Z";
const LATER = "2026-08-21T12:05:00.000Z";

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

function mustOk<T extends { ok: boolean }>(result: T): T & { ok: true } {
  expect(result.ok).toBe(true);
  return result as T & { ok: true };
}

function mustFail<T extends { ok: boolean }>(result: T): T & { ok: false } {
  expect(result.ok).toBe(false);
  return result as T & { ok: false };
}

describe("addPoint", () => {
  it("acrescenta o ponto e emite a operação point.add", () => {
    const result = mustOk(addPoint(emptySurvey(), { id: "p1", x_mm: 100, y_mm: 200 }, NOW));

    expect(result.survey.points).toEqual([{ id: "p1", x_mm: 100, y_mm: 200, created_at: NOW }]);
    expect(result.survey.updated_at).toBe(NOW);
    expect(result.operation).toEqual({ type: "point.add", payload: { point: result.survey.points[0] } });
  });

  it("rejeita coordenada não inteira com INVALID_MM", () => {
    const result = mustFail(addPoint(emptySurvey(), { id: "p1", x_mm: 100.5, y_mm: 200 }, NOW));

    expect(result.error.code).toBe("INVALID_MM");
  });
});

describe("addSegment", () => {
  function surveyWithTwoPoints(): Survey {
    const survey = emptySurvey();
    survey.points = [
      { id: "p1", x_mm: 0, y_mm: 0, created_at: NOW },
      { id: "p2", x_mm: 100, y_mm: 0, created_at: NOW },
    ];
    return survey;
  }

  it("acrescenta o segmento entre dois pontos existentes e distintos", () => {
    const result = mustOk(
      addSegment(surveyWithTwoPoints(), { id: "s1", from_point_id: "p1", to_point_id: "p2" }, NOW),
    );

    expect(result.survey.segments).toEqual([
      { id: "s1", from_point_id: "p1", to_point_id: "p2", created_at: NOW },
    ]);
  });

  it("rejeita ponto desconhecido com UNKNOWN_POINT", () => {
    const result = mustFail(
      addSegment(surveyWithTwoPoints(), { id: "s1", from_point_id: "p1", to_point_id: "p9" }, NOW),
    );

    expect(result.error.code).toBe("UNKNOWN_POINT");
  });

  it("rejeita segmento com os dois pontos iguais com DEGENERATE_SEGMENT", () => {
    const result = mustFail(
      addSegment(surveyWithTwoPoints(), { id: "s1", from_point_id: "p1", to_point_id: "p1" }, NOW),
    );

    expect(result.error.code).toBe("DEGENERATE_SEGMENT");
  });

  it("rejeita segmento duplicado (mesmo par, ordem invertida) com DUPLICATE_SEGMENT", () => {
    const first = mustOk(
      addSegment(surveyWithTwoPoints(), { id: "s1", from_point_id: "p1", to_point_id: "p2" }, NOW),
    );

    const result = mustFail(
      addSegment(first.survey, { id: "s2", from_point_id: "p2", to_point_id: "p1" }, NOW),
    );

    expect(result.error.code).toBe("DUPLICATE_SEGMENT");
  });
});

describe("closePerimeter", () => {
  function surveyWithOpenPath(): Survey {
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
    return survey;
  }

  it("fecha ligando as duas pontas abertas (pontos de grau 1)", () => {
    const result = mustOk(closePerimeter(surveyWithOpenPath(), { id: "s3" }, NOW));

    expect(result.survey.segments).toHaveLength(3);
    const closing = result.survey.segments[2]!;
    expect([closing.from_point_id, closing.to_point_id].sort()).toEqual(["p1", "p3"]);
    expect(result.operation.type).toBe("perimeter.close");
  });

  it("com menos de três pontos usados falha com PERIMETER_TOO_SMALL", () => {
    const survey = emptySurvey();
    survey.points = [
      { id: "p1", x_mm: 0, y_mm: 0, created_at: NOW },
      { id: "p2", x_mm: 100, y_mm: 0, created_at: NOW },
    ];
    survey.segments = [{ id: "s1", from_point_id: "p1", to_point_id: "p2", created_at: NOW }];

    const result = mustFail(closePerimeter(survey, { id: "s2" }, NOW));

    expect(result.error.code).toBe("PERIMETER_TOO_SMALL");
  });

  it("sem exatamente duas pontas abertas falha com PERIMETER_AMBIGUOUS", () => {
    const survey = surveyWithOpenPath();
    // Um quarto ponto isolado num segmento à parte cria quatro pontas abertas ao todo.
    survey.points.push({ id: "p4", x_mm: 500, y_mm: 500, created_at: NOW });
    survey.points.push({ id: "p5", x_mm: 600, y_mm: 500, created_at: NOW });
    survey.segments.push({ id: "s4", from_point_id: "p4", to_point_id: "p5", created_at: NOW });

    const result = mustFail(closePerimeter(survey, { id: "s3" }, NOW));

    expect(result.error.code).toBe("PERIMETER_AMBIGUOUS");
    expect(result.error.message).toContain("pontas abertas");
  });

  it("não duplica segmento quando as duas pontas abertas já estão ligadas entre si", () => {
    // Anel fechado p1-p2-p3 + segmento solto p4-p5: as únicas pontas abertas são p4 e
    // p5, que JÁ têm segmento entre si — fechar duplicaria s4 e quebraria a premissa de
    // grafo simples do hasCycle da validação.
    const survey = surveyWithOpenPath();
    survey.segments.push({ id: "s3", from_point_id: "p3", to_point_id: "p1", created_at: NOW });
    survey.points.push({ id: "p4", x_mm: 500, y_mm: 500, created_at: NOW });
    survey.points.push({ id: "p5", x_mm: 600, y_mm: 500, created_at: NOW });
    survey.segments.push({ id: "s4", from_point_id: "p4", to_point_id: "p5", created_at: NOW });

    const result = mustFail(closePerimeter(survey, { id: "s5" }, NOW));

    expect(result.error.code).toBe("PERIMETER_AMBIGUOUS");
    expect(result.error.message).toContain("já estão ligadas");
  });
});

describe("addElement", () => {
  function surveyWithPoint(): Survey {
    const survey = emptySurvey();
    survey.points = [{ id: "p1", x_mm: 0, y_mm: 0, created_at: NOW }];
    return survey;
  }

  it("acrescenta o elemento vinculado a um ponto existente", () => {
    const result = mustOk(
      addElement(surveyWithPoint(), { id: "e1", label: "Banco", point_ids: ["p1"] }, NOW),
    );

    expect(result.survey.elements).toEqual([
      { id: "e1", label: "Banco", point_ids: ["p1"], created_at: NOW },
    ]);
  });

  it("rejeita elemento sem nenhum ponto com ELEMENT_WITHOUT_POINT", () => {
    const result = mustFail(
      addElement(surveyWithPoint(), { id: "e1", label: "Banco", point_ids: [] }, NOW),
    );

    expect(result.error.code).toBe("ELEMENT_WITHOUT_POINT");
  });

  it("rejeita elemento com ponto inexistente com ELEMENT_WITHOUT_POINT", () => {
    const result = mustFail(
      addElement(surveyWithPoint(), { id: "e1", label: "Banco", point_ids: ["p9"] }, NOW),
    );

    expect(result.error.code).toBe("ELEMENT_WITHOUT_POINT");
  });
});

describe("addMeasurement", () => {
  function surveyWithPointsSegmentsAndElement(): Survey {
    const survey = emptySurvey();
    survey.points = [
      { id: "p1", x_mm: 0, y_mm: 0, created_at: NOW },
      { id: "p2", x_mm: 100, y_mm: 0, created_at: NOW },
      { id: "p3", x_mm: 100, y_mm: 100, created_at: NOW },
      { id: "p4", x_mm: 0, y_mm: 100, created_at: NOW },
    ];
    survey.segments = [
      { id: "s1", from_point_id: "p1", to_point_id: "p2", created_at: NOW },
      { id: "s2", from_point_id: "p2", to_point_id: "p3", created_at: NOW },
    ];
    survey.elements = [{ id: "e1", label: "Banco", point_ids: ["p1"], created_at: NOW }];
    return survey;
  }

  it("value_mm precisa ser inteiro positivo (INVALID_MM)", () => {
    const result = mustFail(
      addMeasurement(
        surveyWithPointsSegmentsAndElement(),
        {
          id: "m1",
          value_mm: 0,
          kind: "length",
          from_point_id: "p1",
          to_point_id: "p2",
          instrument: "trena",
          status: "confirmed",
        },
        NOW,
      ),
    );

    expect(result.error.code).toBe("INVALID_MM");
  });

  it("length exige par de pontos existentes", () => {
    const survey = surveyWithPointsSegmentsAndElement();
    const ok = mustOk(
      addMeasurement(
        survey,
        {
          id: "m1",
          value_mm: 1000,
          kind: "length",
          from_point_id: "p1",
          to_point_id: "p2",
          instrument: "trena",
          status: "confirmed",
        },
        NOW,
      ),
    );
    expect(ok.survey.measurements).toHaveLength(1);

    const missingPair = mustFail(
      addMeasurement(
        survey,
        { id: "m2", value_mm: 1000, kind: "length", from_point_id: "p1", instrument: "trena", status: "confirmed" },
        NOW,
      ),
    );
    expect(missingPair.error.code).toBe("MEASUREMENT_UNLINKED");
  });

  it("diagonal exige par de pontos existentes (MEASUREMENT_UNLINKED com ponto inexistente)", () => {
    const result = mustFail(
      addMeasurement(
        surveyWithPointsSegmentsAndElement(),
        {
          id: "m1",
          value_mm: 1414,
          kind: "diagonal",
          from_point_id: "p1",
          to_point_id: "p9",
          instrument: "trena",
          status: "confirmed",
        },
        NOW,
      ),
    );

    expect(result.error.code).toBe("MEASUREMENT_UNLINKED");
  });

  it("width/height/radius aceitam element_id OU par de pontos", () => {
    const survey = surveyWithPointsSegmentsAndElement();

    const byElement = mustOk(
      addMeasurement(
        survey,
        { id: "m1", value_mm: 500, kind: "width", element_id: "e1", instrument: "trena", status: "confirmed" },
        NOW,
      ),
    );
    expect(byElement.survey.measurements).toHaveLength(1);

    const byPoints = mustOk(
      addMeasurement(
        survey,
        {
          id: "m2",
          value_mm: 500,
          kind: "height",
          from_point_id: "p1",
          to_point_id: "p2",
          instrument: "trena",
          status: "confirmed",
        },
        NOW,
      ),
    );
    expect(byPoints.survey.measurements).toHaveLength(1);
  });

  it("width sem element_id nem par de pontos falha com MEASUREMENT_UNLINKED", () => {
    const result = mustFail(
      addMeasurement(
        surveyWithPointsSegmentsAndElement(),
        { id: "m1", value_mm: 500, kind: "radius", instrument: "trena", status: "confirmed" },
        NOW,
      ),
    );

    expect(result.error.code).toBe("MEASUREMENT_UNLINKED");
  });

  it("level/drop exigem ao menos um ponto existente", () => {
    const survey = surveyWithPointsSegmentsAndElement();

    const ok = mustOk(
      addMeasurement(
        survey,
        { id: "m1", value_mm: 50, kind: "level", from_point_id: "p1", instrument: "trena", status: "confirmed" },
        NOW,
      ),
    );
    expect(ok.survey.measurements).toHaveLength(1);

    const missing = mustFail(
      addMeasurement(
        survey,
        { id: "m2", value_mm: 50, kind: "drop", instrument: "trena", status: "confirmed" },
        NOW,
      ),
    );
    expect(missing.error.code).toBe("MEASUREMENT_UNLINKED");
  });

  it("angle exige dois segmentos referenciáveis por par de pontos", () => {
    const survey = surveyWithPointsSegmentsAndElement();

    const ok = mustOk(
      addMeasurement(
        survey,
        {
          id: "m1",
          value_mm: 90,
          kind: "angle",
          from_point_id: "p1",
          to_point_id: "p2",
          second_from_point_id: "p2",
          second_to_point_id: "p3",
          instrument: "trena",
          status: "confirmed",
        },
        NOW,
      ),
    );
    expect(ok.survey.measurements).toHaveLength(1);

    const missingSecondSegment = mustFail(
      addMeasurement(
        survey,
        {
          id: "m2",
          value_mm: 90,
          kind: "angle",
          from_point_id: "p1",
          to_point_id: "p2",
          second_from_point_id: "p3",
          second_to_point_id: "p4",
          instrument: "trena",
          status: "confirmed",
        },
        NOW,
      ),
    );
    expect(missingSecondSegment.error.code).toBe("MEASUREMENT_UNLINKED");
  });
});

describe("addObservation", () => {
  it("acrescenta a observação com texto não vazio", () => {
    const result = mustOk(addObservation(emptySurvey(), { id: "o1", text: "Poste inclinado" }, NOW));

    expect(result.survey.observations).toEqual([
      { id: "o1", text: "Poste inclinado", point_id: undefined, element_id: undefined, created_at: NOW },
    ]);
  });

  it("rejeita texto vazio com EMPTY_TEXT", () => {
    const result = mustFail(addObservation(emptySurvey(), { id: "o1", text: "   " }, NOW));

    expect(result.error.code).toBe("EMPTY_TEXT");
  });
});

describe("justifyMeasurement", () => {
  function surveyWithMeasurement(): Survey {
    const survey = emptySurvey();
    survey.points = [
      { id: "p1", x_mm: 0, y_mm: 0, created_at: NOW },
      { id: "p2", x_mm: 100, y_mm: 0, created_at: NOW },
    ];
    survey.measurements = [
      {
        id: "m1",
        value_mm: 1000,
        kind: "length",
        from_point_id: "p1",
        to_point_id: "p2",
        instrument: "trena",
        status: "confirmed",
        created_at: NOW,
      },
    ];
    return survey;
  }

  it("grava a justificativa na medida existente", () => {
    const result = mustOk(
      justifyMeasurement(
        surveyWithMeasurement(),
        { measurement_id: "m1", justification: "Acesso interditado" },
        NOW,
      ),
    );

    expect(result.survey.measurements[0]?.justification).toBe("Acesso interditado");
  });

  it("rejeita medida inexistente com UNKNOWN_MEASUREMENT", () => {
    const result = mustFail(
      justifyMeasurement(surveyWithMeasurement(), { measurement_id: "m9", justification: "x" }, NOW),
    );

    expect(result.error.code).toBe("UNKNOWN_MEASUREMENT");
  });

  it("rejeita justificativa vazia com EMPTY_TEXT", () => {
    const result = mustFail(
      justifyMeasurement(surveyWithMeasurement(), { measurement_id: "m1", justification: "  " }, NOW),
    );

    expect(result.error.code).toBe("EMPTY_TEXT");
  });
});

describe("addPhotoAnchor", () => {
  function surveyWithPointAndElement(): Survey {
    const survey = emptySurvey();
    survey.points = [{ id: "p1", x_mm: 0, y_mm: 0, created_at: NOW }];
    survey.elements = [{ id: "e1", label: "Banco", point_ids: ["p1"], created_at: NOW }];
    return survey;
  }

  it("ancora a um ponto existente", () => {
    const result = mustOk(
      addPhotoAnchor(
        surveyWithPointAndElement(),
        { id: "a1", local_media_ref: "media://1", point_id: "p1" },
        NOW,
      ),
    );

    expect(result.survey.photo_anchors).toHaveLength(1);
  });

  it("ancora a um elemento existente", () => {
    const result = mustOk(
      addPhotoAnchor(
        surveyWithPointAndElement(),
        { id: "a1", local_media_ref: "media://1", element_id: "e1" },
        NOW,
      ),
    );

    expect(result.survey.photo_anchors).toHaveLength(1);
  });

  it("rejeita âncora sem ponto nem elemento com ANCHOR_UNLINKED", () => {
    const result = mustFail(
      addPhotoAnchor(surveyWithPointAndElement(), { id: "a1", local_media_ref: "media://1" }, NOW),
    );

    expect(result.error.code).toBe("ANCHOR_UNLINKED");
  });
});

describe("undoLast", () => {
  it("ida-e-volta: aplicar N comandos e desfazer N volta ao estado inicial campo a campo", () => {
    const initial = emptySurvey();
    const history: CommandHistoryEntry[] = [];
    let survey = initial;

    const step1 = mustOk(addPoint(survey, { id: "p1", x_mm: 0, y_mm: 0 }, NOW));
    history.push({ command_id: "p1", previous_survey: survey });
    survey = step1.survey;

    const step2 = mustOk(addPoint(survey, { id: "p2", x_mm: 100, y_mm: 0 }, LATER));
    history.push({ command_id: "p2", previous_survey: survey });
    survey = step2.survey;

    const step3 = mustOk(
      addSegment(survey, { id: "s1", from_point_id: "p1", to_point_id: "p2" }, LATER),
    );
    history.push({ command_id: "s1", previous_survey: survey });
    survey = step3.survey;

    expect(survey.points).toHaveLength(2);
    expect(survey.segments).toHaveLength(1);

    // Desfaz os três comandos, na ordem inversa de aplicação.
    for (let i = history.length - 1; i >= 0; i -= 1) {
      const entry = history[i]!;
      const undone = mustOk(undoLast(survey, entry, LATER));
      expect(undone.operation).toEqual({
        type: "command.undo",
        payload: { undone_command_id: entry.command_id },
      });
      survey = undone.survey;
    }

    expect(survey).toEqual(initial);
  });
});
