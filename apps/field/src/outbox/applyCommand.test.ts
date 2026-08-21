import { beforeEach, describe, expect, it } from "vitest";

import { addPoint, addSegment } from "../domain/commands";
import type { Survey } from "../domain/types";
import { DexieSurveyRepository } from "../storage/DexieSurveyRepository";
import type { SurveyRepository } from "../storage/SurveyRepository";
import { applyCommand } from "./applyCommand";
import { acknowledgeOperation } from "./outbox";
import type { SurveyOperation } from "./types";

const NOW = "2026-08-21T12:00:00.000Z";
const DEVICE = "device-1";

function emptySurvey(): Survey {
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
  };
}

/** Envelope que registra a ordem das chamadas — é como se verifica "persistiu ANTES de
 * devolver" sem depender de DOM. */
function recording(inner: SurveyRepository, calls: string[]): SurveyRepository {
  return {
    getSurvey: (id) => inner.getSurvey(id),
    saveSurvey: async (survey) => {
      calls.push("saveSurvey");
      await inner.saveSurvey(survey);
    },
    appendOperation: async (operation) => {
      calls.push("appendOperation");
      await inner.appendOperation(operation);
    },
    getPendingOperations: (id) => inner.getPendingOperations(id),
    listOperations: async (id) => {
      calls.push("listOperations");
      return inner.listOperations(id);
    },
    acknowledge: (id) => inner.acknowledge(id),
    saveMedia: (record) => inner.saveMedia(record),
    getMedia: (id) => inner.getMedia(id),
  };
}

describe("applyCommand", () => {
  let repository: SurveyRepository;
  let calls: string[];
  let recorded: SurveyRepository;

  beforeEach(() => {
    repository = new DexieSurveyRepository(`test-db-${Math.random().toString(36).slice(2)}`);
    calls = [];
    recorded = recording(repository, calls);
  });

  it("comando ok grava survey e operação ANTES de devolver o estado novo", async () => {
    const survey = emptySurvey();
    await repository.saveSurvey(survey);

    const outcome = await applyCommand(
      recorded,
      survey,
      addPoint(survey, { id: "p1", x_mm: 1200, y_mm: 3400 }, NOW),
      { device_id: DEVICE, operation_id: "op-1", created_at: NOW },
    );

    expect(outcome.ok).toBe(true);
    // No instante em que a promessa resolve, o estado novo já está no banco local.
    const stored = await repository.getSurvey("survey-1");
    expect(stored?.points).toHaveLength(1);
    expect(stored?.points[0]?.x_mm).toBe(1200);
    const operations = await repository.listOperations("survey-1");
    expect(operations).toHaveLength(1);
    expect(operations[0]?.type).toBe("point.add");
    expect(operations[0]?.status).toBe("local");
    expect(calls).toEqual(["saveSurvey", "listOperations", "appendOperation"]);
  });

  it("comando com erro não persiste nada e devolve o erro estruturado do domínio", async () => {
    const survey = emptySurvey();
    await repository.saveSurvey(survey);

    const outcome = await applyCommand(
      recorded,
      survey,
      addSegment(survey, { id: "s1", from_point_id: "nao-existe", to_point_id: "outro" }, NOW),
      { device_id: DEVICE, operation_id: "op-1", created_at: NOW },
    );

    expect(outcome).toEqual({
      ok: false,
      error: {
        code: "UNKNOWN_POINT",
        message: "O segmento referencia um ponto que não existe no levantamento.",
      },
    });
    expect(calls).toEqual([]);
    const stored = await repository.getSurvey("survey-1");
    expect(stored?.segments).toEqual([]);
    expect(await repository.listOperations("survey-1")).toEqual([]);
  });

  it("seq cresce por device e não regride depois de um ack", async () => {
    let survey = emptySurvey();
    await repository.saveSurvey(survey);

    const first = await applyCommand(
      repository,
      survey,
      addPoint(survey, { id: "p1", x_mm: 0, y_mm: 0 }, NOW),
      { device_id: DEVICE, operation_id: "op-1", created_at: NOW },
    );
    expect(first.ok).toBe(true);
    if (!first.ok) {
      return;
    }
    expect(first.operation.seq).toBe(1);
    survey = first.survey;

    await acknowledgeOperation(repository, "op-1");

    const second = await applyCommand(
      repository,
      survey,
      addPoint(survey, { id: "p2", x_mm: 1000, y_mm: 0 }, NOW),
      { device_id: DEVICE, operation_id: "op-2", created_at: NOW },
    );
    expect(second.ok).toBe(true);
    if (!second.ok) {
      return;
    }
    // Sobre as pendências a sequência voltaria para 1, colidindo com o seq já emitido.
    expect(second.operation.seq).toBe(2);
  });

  it("operação de outro device não avança a sequência deste aparelho", async () => {
    const survey = emptySurvey();
    await repository.saveSurvey(survey);
    const alien: SurveyOperation = {
      operation_id: "op-alien",
      device_id: "outro-aparelho",
      survey_id: "survey-1",
      seq: 9,
      type: "point.add",
      payload: {},
      status: "local",
      created_at: NOW,
    };
    await repository.appendOperation(alien);

    const outcome = await applyCommand(
      repository,
      survey,
      addPoint(survey, { id: "p1", x_mm: 0, y_mm: 0 }, NOW),
      { device_id: DEVICE, operation_id: "op-1", created_at: NOW },
    );

    expect(outcome.ok).toBe(true);
    if (outcome.ok) {
      expect(outcome.operation.seq).toBe(1);
    }
  });

  it("a operação é enfileirada no survey de entrada, não no id devolvido pelo comando", async () => {
    const survey = emptySurvey();
    await repository.saveSurvey(survey);

    const outcome = await applyCommand(
      repository,
      survey,
      addPoint(survey, { id: "p1", x_mm: 0, y_mm: 0 }, NOW),
      { device_id: DEVICE, operation_id: "op-1", created_at: NOW },
    );

    expect(outcome.ok).toBe(true);
    if (outcome.ok) {
      expect(outcome.operation.survey_id).toBe("survey-1");
      expect(outcome.operation.device_id).toBe(DEVICE);
      expect(outcome.operation.created_at).toBe(NOW);
    }
  });
});
