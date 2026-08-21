import type { SurveyRepository } from "../storage/SurveyRepository";
import type { SurveyOperation } from "./types";

/**
 * Enfileira uma operação no outbox local. Não há transporte de rede aqui (fora de escopo
 * desta tarefa — ADR-0043, D2 trata a sincronização como fatia futura); a função só grava
 * via `SurveyRepository`, preservando a ordem de `seq` que o chamador atribuiu.
 */
export async function enqueueOperation(
  repository: SurveyRepository,
  operation: SurveyOperation,
): Promise<void> {
  await repository.appendOperation(operation);
}

/**
 * Reconhece uma operação (simulação de ack — sem transporte real). Idempotente: chamar
 * duas vezes para a mesma `operationId` não corrompe estado nem lança erro.
 */
export async function acknowledgeOperation(
  repository: SurveyRepository,
  operationId: string,
): Promise<void> {
  await repository.acknowledge(operationId);
}

/** Próximo `seq` a partir da lista de operações já conhecidas de um device — 1 se a lista
 * estiver vazia, senão o maior `seq` existente + 1. */
export function nextSeq(operations: readonly SurveyOperation[]): number {
  return operations.reduce((max, operation) => Math.max(max, operation.seq), 0) + 1;
}
