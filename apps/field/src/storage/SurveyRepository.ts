import type { Survey } from "../domain/types";
import type { SurveyOperation } from "../outbox/types";

/**
 * Interface de persistência local. Isola o domínio de Dexie/IndexedDB (ADR-0043, D2): a
 * troca por SQLite/Capacitor deve ser possível sem reescrever `src/domain` nem `src/ui`.
 */
export interface SurveyRepository {
  getSurvey(surveyId: string): Promise<Survey | undefined>;
  saveSurvey(survey: Survey): Promise<void>;
  appendOperation(operation: SurveyOperation): Promise<void>;
  /** Operações ainda não reconhecidas (`status !== "acked"`) do survey, em ordem de
   * `seq`. */
  getPendingOperations(surveyId: string): Promise<SurveyOperation[]>;
  /** TODAS as operações do survey (inclusive `acked`), em ordem de `seq`. É a fonte para
   * calcular o próximo `seq`: pendências não servem, porque um ack encolheria a lista e a
   * sequência regrediria, reutilizando valores já emitidos. */
  listOperations(surveyId: string): Promise<SurveyOperation[]>;
  /** Marca a operação como reconhecida. Idempotente: reconhecer de novo uma operação já
   * reconhecida não é erro nem apaga histórico. */
  acknowledge(operationId: string): Promise<void>;
}
