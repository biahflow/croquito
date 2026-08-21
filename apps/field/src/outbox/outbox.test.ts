import { beforeEach, describe, expect, it } from "vitest";

import { DexieSurveyRepository } from "../storage/DexieSurveyRepository";
import type { SurveyRepository } from "../storage/SurveyRepository";
import { acknowledgeOperation, enqueueOperation, nextSeq } from "./outbox";
import type { SurveyOperation } from "./types";

function makeOperation(overrides: Partial<SurveyOperation> = {}): SurveyOperation {
  return {
    operation_id: "op-1",
    device_id: "device-1",
    survey_id: "survey-1",
    seq: 1,
    type: "point.add",
    payload: {},
    status: "local",
    created_at: "2026-08-21T12:00:00.000Z",
    ...overrides,
  };
}

describe("outbox", () => {
  let repository: SurveyRepository;

  beforeEach(() => {
    repository = new DexieSurveyRepository(`test-db-${Math.random().toString(36).slice(2)}`);
  });

  it("enfileirar preserva a ordem de seq mesmo fora de ordem de inserção", async () => {
    await enqueueOperation(repository, makeOperation({ operation_id: "op-2", seq: 2 }));
    await enqueueOperation(repository, makeOperation({ operation_id: "op-1", seq: 1 }));
    await enqueueOperation(repository, makeOperation({ operation_id: "op-3", seq: 3 }));

    const pending = await repository.getPendingOperations("survey-1");

    expect(pending.map((operation) => operation.operation_id)).toEqual(["op-1", "op-2", "op-3"]);
    expect(pending.map((operation) => operation.seq)).toEqual([1, 2, 3]);
  });

  it("ack é idempotente — ack duplo não corrompe estado nem lança erro", async () => {
    await enqueueOperation(repository, makeOperation());

    await acknowledgeOperation(repository, "op-1");
    await expect(acknowledgeOperation(repository, "op-1")).resolves.not.toThrow();

    const pending = await repository.getPendingOperations("survey-1");
    expect(pending).toHaveLength(0);
  });

  it("ack de operation_id desconhecido não corrompe estado nem lança erro", async () => {
    await enqueueOperation(repository, makeOperation());

    await expect(acknowledgeOperation(repository, "nao-existe")).resolves.not.toThrow();

    const pending = await repository.getPendingOperations("survey-1");
    expect(pending).toHaveLength(1);
  });

  describe("nextSeq", () => {
    it("devolve 1 para lista vazia", () => {
      expect(nextSeq([])).toBe(1);
    });

    it("não regride depois de um ack — seq vem do histórico completo, não das pendências", async () => {
      await enqueueOperation(repository, makeOperation({ operation_id: "op-1", seq: 1 }));
      await acknowledgeOperation(repository, "op-1");

      const pending = await repository.getPendingOperations("survey-1");
      const history = await repository.listOperations("survey-1");

      // Sobre as pendências a sequência regrediria para 1, colidindo com o seq já emitido
      // pela operação reconhecida; sobre o histórico completo ela segue em frente.
      expect(nextSeq(pending)).toBe(1);
      expect(nextSeq(history)).toBe(2);
    });

    it("devolve o maior seq existente + 1, mesmo fora de ordem", () => {
      const operations = [
        makeOperation({ operation_id: "a", seq: 3 }),
        makeOperation({ operation_id: "b", seq: 1 }),
        makeOperation({ operation_id: "c", seq: 2 }),
      ];

      expect(nextSeq(operations)).toBe(4);
    });
  });
});
