/**
 * Tipo da operação do outbox. Puro e serializável — sem transporte de rede embutido; quem
 * envia é `src/sync/engine.ts` (T9), o único lugar do workspace autorizado a falar com a
 * rede (`apps/field/AGENTS.md`).
 */

/**
 * Ciclo de vida da operação no aparelho:
 *
 * - `local` — gravada pelo comando, nunca oferecida ao servidor ainda;
 * - `pending` — já entrou num lote que saiu para o servidor (marcada ANTES do envio, para
 *   que um app fechado no meio do POST reencontre a operação e a reenvie);
 * - `acked` — o servidor confirmou o `operation_id` (`acked_operation_ids`);
 * - `superseded` — o técnico resolveu um conflito aceitando a versão do escritório
 *   (prancha 6b): a operação local **continua gravada** e visível no histórico, apenas
 *   deixa de ser oferecida ao servidor. Nada é apagado (ADR-0043 D2).
 *
 * `superseded` é valor NOVO da união (T9) e não exige migração de schema Dexie: `status` é
 * índice simples sobre a coluna, e um valor novo é dado, não estrutura (ver
 * `DexieSurveyRepository`).
 */
export type SurveyOperationStatus = "local" | "pending" | "acked" | "superseded";

export interface SurveyOperation {
  /** UUID gerado no dispositivo — é o mesmo valor que a sincronização usará como
   * `Idempotency-Key`, quando essa fatia existir. */
  operation_id: string;
  device_id: string;
  survey_id: string;
  /** Sequência crescente por `device_id`. Quem gera a operação é quem sabe a ordem real
   * das ações do usuário; esta camada não a infere. */
  seq: number;
  type: string;
  payload: Record<string, unknown>;
  status: SurveyOperationStatus;
  created_at: string;
}
