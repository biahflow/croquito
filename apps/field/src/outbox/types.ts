/**
 * Tipo da operação do outbox. Puro e serializável — sem transporte de rede embutido; esta
 * fatia só enfileira e reconhece localmente (ver `outbox.ts`).
 */

export type SurveyOperationStatus = "local" | "pending" | "acked";

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
