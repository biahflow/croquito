import Dexie, { type Table } from "dexie";

import type { Survey } from "../domain/types";
import type { SurveyOperation } from "../outbox/types";
import type { MediaRecord, SurveyRepository } from "./SurveyRepository";

class FieldDatabase extends Dexie {
  surveys!: Table<Survey, string>;
  operations!: Table<SurveyOperation, string>;
  media!: Table<MediaRecord, string>;

  constructor(name: string) {
    super(name);
    this.version(1).stores({
      surveys: "id",
      // Chave primária é operation_id; survey_id e status são índices simples — o volume
      // por survey é pequeno o bastante para filtrar/ordenar em memória (ver
      // getPendingOperations abaixo) em vez de um índice composto.
      operations: "operation_id, survey_id, status",
    });
    // T6: tabela `media` nova. Dexie só exige, numa versão nova, o `stores()` das tabelas
    // que MUDAM — `surveys`/`operations` não aparecem aqui de propósito, e continuam
    // com o schema (e os dados) da v1 intactos; um banco já aberto na v1 sobe para a v2
    // sem perder nada (ver DexieSurveyRepository.test.ts, "abre um banco criado na v1").
    this.version(2).stores({
      media: "id",
    });
  }
}

/**
 * Implementação de `SurveyRepository` sobre IndexedDB via Dexie (ADR-0043, D2). O nome do
 * banco é parametrizável para permitir testes isolados sem um survey vazar para outro.
 */
export class DexieSurveyRepository implements SurveyRepository {
  private readonly db: FieldDatabase;

  constructor(databaseName = "croquito-field") {
    this.db = new FieldDatabase(databaseName);
  }

  async getSurvey(surveyId: string): Promise<Survey | undefined> {
    return this.db.surveys.get(surveyId);
  }

  async saveSurvey(survey: Survey): Promise<void> {
    await this.db.surveys.put(survey);
  }

  async appendOperation(operation: SurveyOperation): Promise<void> {
    await this.db.operations.put(operation);
  }

  /**
   * Survey e operação numa transação `rw` única sobre as duas tabelas. Uma falha em
   * qualquer das duas escritas aborta a transação inteira: o IndexedDB desfaz o `put` já
   * executado e o banco volta ao estado anterior ao comando — nunca sobra survey avançado
   * sem operação no outbox (dívida registrada na revisão de T3).
   *
   * Não há migração de schema aqui: `surveys` e `operations` são as mesmas tabelas da v1;
   * o que muda é só a atomicidade da escrita.
   */
  async saveSurveyWithOperation(survey: Survey, operation: SurveyOperation): Promise<void> {
    await this.db.transaction("rw", this.db.surveys, this.db.operations, async () => {
      await this.db.surveys.put(survey);
      await this.db.operations.put(operation);
    });
  }

  async getPendingOperations(surveyId: string): Promise<SurveyOperation[]> {
    const all = await this.listOperations(surveyId);
    // `superseded` sai da fila de envio mas continua no histórico (`listOperations`): a
    // operação preterida por uma resolução de conflito não é reoferecida ao servidor nem
    // contada como pendência na barra, e mesmo assim nunca é apagada.
    return all.filter(
      (operation) => operation.status !== "acked" && operation.status !== "superseded",
    );
  }

  async listOperations(surveyId: string): Promise<SurveyOperation[]> {
    const all = await this.db.operations.where("survey_id").equals(surveyId).toArray();
    return all.sort((a, b) => a.seq - b.seq);
  }

  async acknowledge(operationId: string): Promise<void> {
    // update() em chave inexistente devolve 0 sem lançar — reconhecer duas vezes (ou uma
    // operação que já sumiu) não corrompe estado nem apaga histórico.
    await this.db.operations.update(operationId, { status: "acked" });
  }

  async saveOperations(operations: readonly SurveyOperation[]): Promise<void> {
    if (operations.length === 0) {
      return;
    }
    // `bulkPut` numa transação implícita única: marcar meio lote como `pending` e o resto
    // não deixaria o outbox num estado que nenhum caminho de leitura espera.
    await this.db.operations.bulkPut([...operations]);
  }

  async saveMedia(record: MediaRecord): Promise<void> {
    await this.db.media.put(record);
  }

  async getMedia(mediaId: string): Promise<MediaRecord | undefined> {
    return this.db.media.get(mediaId);
  }

  /** Fecha a conexão — usado nos testes para simular "reabrir o app" com uma instância
   * nova apontando para o mesmo banco. */
  close(): void {
    this.db.close();
  }
}
