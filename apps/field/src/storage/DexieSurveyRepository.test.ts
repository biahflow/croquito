import Dexie from "dexie";
import { beforeEach, describe, expect, it } from "vitest";

import type { Survey } from "../domain/types";
import type { SurveyOperation } from "../outbox/types";
import { DexieSurveyRepository } from "./DexieSurveyRepository";
import type { MediaRecord } from "./SurveyRepository";

function makeSurvey(id: string): Survey {
  const now = "2026-08-21T12:00:00.000Z";
  return {
    id,
    name: "Praça de teste",
    points: [{ id: "point-1", x_mm: 1000, y_mm: 2000, created_at: now }],
    segments: [],
    measurements: [],
    photo_anchors: [],
    elements: [],
    observations: [],
    created_at: now,
    updated_at: now,
  };
}

function makeOperation(overrides: Partial<SurveyOperation> = {}): SurveyOperation {
  return {
    operation_id: "op-1",
    device_id: "device-1",
    survey_id: "survey-1",
    seq: 1,
    type: "point.add",
    payload: { point_id: "point-1" },
    status: "local",
    created_at: "2026-08-21T12:00:00.000Z",
    ...overrides,
  };
}

describe("DexieSurveyRepository", () => {
  // Nome único por teste: fake-indexeddb mantém os bancos vivos entre instâncias no mesmo
  // processo, então reusar um nome entre `it`s vazaria estado de um teste para o outro.
  let databaseName: string;

  beforeEach(() => {
    databaseName = `test-db-${Math.random().toString(36).slice(2)}`;
  });

  it("salva e recupera um survey", async () => {
    const repository = new DexieSurveyRepository(databaseName);
    const survey = makeSurvey("survey-1");

    await repository.saveSurvey(survey);
    const loaded = await repository.getSurvey("survey-1");

    expect(loaded).toEqual(survey);

    repository.close();
  });

  it("devolve undefined para survey inexistente", async () => {
    const repository = new DexieSurveyRepository(databaseName);

    const loaded = await repository.getSurvey("nao-existe");

    expect(loaded).toBeUndefined();

    repository.close();
  });

  it("operação pendente sobrevive a reabrir o banco", async () => {
    const first = new DexieSurveyRepository(databaseName);
    await first.appendOperation(makeOperation());
    first.close();

    // Uma instância nova apontando para o mesmo nome simula reabrir o app depois de
    // fechado — se a persistência fosse só em memória do objeto Dexie (e não no
    // IndexedDB de fato), esta segunda instância não veria a operação.
    const reopened = new DexieSurveyRepository(databaseName);
    const pending = await reopened.getPendingOperations("survey-1");

    expect(pending).toHaveLength(1);
    expect(pending[0]?.operation_id).toBe("op-1");

    reopened.close();
  });

  it("acknowledge remove a operação da lista de pendências sem apagar o histórico", async () => {
    const repository = new DexieSurveyRepository(databaseName);
    await repository.appendOperation(makeOperation());

    await repository.acknowledge("op-1");
    const pending = await repository.getPendingOperations("survey-1");

    expect(pending).toHaveLength(0);

    // A linha continua existindo (só o status mudou) — se o acknowledge apagasse o
    // registro em vez de marcar `status: "acked"`, este get direto na tabela interna
    // voltaria undefined e o teste pegaria a diferença. O cast para `any` só existe no
    // teste, para inspecionar o Dexie por baixo do contrato público de
    // `SurveyRepository`.
    const internalDb = (repository as any).db as {
      operations: { get(id: string): Promise<SurveyOperation | undefined> };
    };
    const stillThere = await internalDb.operations.get("op-1");
    expect(stillThere).toMatchObject({ operation_id: "op-1", status: "acked" });

    repository.close();
  });

  it("saveMedia/getMedia fazem roundtrip com o sha256 persistido", async () => {
    const repository = new DexieSurveyRepository(databaseName);
    const blob = new Blob([new Uint8Array([1, 2, 3])], { type: "image/jpeg" });
    const record: MediaRecord = {
      id: "media-1",
      sha256: "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad",
      mime_type: "image/jpeg",
      byte_size: 3,
      blob,
      created_at: "2026-08-21T12:00:00.000Z",
    };

    await repository.saveMedia(record);
    const loaded = await repository.getMedia("media-1");

    expect(loaded).toEqual(record);
    expect(loaded?.sha256).toBe(
      "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad",
    );

    repository.close();
  });

  it("getMedia devolve undefined para mídia inexistente", async () => {
    const repository = new DexieSurveyRepository(databaseName);

    const loaded = await repository.getMedia("nao-existe");

    expect(loaded).toBeUndefined();

    repository.close();
  });

  it("mídia salva sobrevive a reabrir o banco (mesma garantia de operação pendente)", async () => {
    const first = new DexieSurveyRepository(databaseName);
    const blob = new Blob([new Uint8Array([9, 9])], { type: "image/png" });
    await first.saveMedia({
      id: "media-2",
      sha256: "hash-2",
      mime_type: "image/png",
      byte_size: 2,
      blob,
      created_at: "2026-08-21T12:00:00.000Z",
    });
    first.close();

    const reopened = new DexieSurveyRepository(databaseName);
    const loaded = await reopened.getMedia("media-2");

    expect(loaded?.id).toBe("media-2");

    reopened.close();
  });

  it("abre um banco criado na v1 (só surveys/operations) sem perder dados — migração para v2", async () => {
    // Simula um aparelho que já tinha o app antes de T6: só as duas tabelas da v1
    // existem no IndexedDB. `DexieSurveyRepository` (v2) precisa abrir esse banco sem
    // apagar o survey nem a operação pendente já gravados.
    class LegacyFieldDatabase extends Dexie {
      surveys!: Dexie.Table<Survey, string>;
      operations!: Dexie.Table<SurveyOperation, string>;

      constructor(name: string) {
        super(name);
        this.version(1).stores({
          surveys: "id",
          operations: "operation_id, survey_id, status",
        });
      }
    }

    const legacy = new LegacyFieldDatabase(databaseName);
    await legacy.surveys.put(makeSurvey("survey-legacy"));
    await legacy.operations.put(makeOperation({ operation_id: "op-legacy", survey_id: "survey-legacy" }));
    legacy.close();

    const upgraded = new DexieSurveyRepository(databaseName);
    const survey = await upgraded.getSurvey("survey-legacy");
    const pending = await upgraded.getPendingOperations("survey-legacy");

    expect(survey?.id).toBe("survey-legacy");
    expect(pending).toHaveLength(1);
    expect(pending[0]?.operation_id).toBe("op-legacy");

    // A tabela nova funciona no banco migrado.
    await upgraded.saveMedia({
      id: "media-after-migration",
      sha256: "hash-3",
      mime_type: "image/jpeg",
      byte_size: 1,
      blob: new Blob([new Uint8Array([1])]),
      created_at: "2026-08-21T12:00:00.000Z",
    });
    const media = await upgraded.getMedia("media-after-migration");
    expect(media?.id).toBe("media-after-migration");

    upgraded.close();
  });
});
