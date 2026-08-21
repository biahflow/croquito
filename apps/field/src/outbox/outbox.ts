import type { SurveyRepository } from "../storage/SurveyRepository";
import type { SurveyOperation } from "./types";

/**
 * Enfileira uma operação no outbox local. Não há transporte de rede aqui: quem envia é
 * `src/sync/engine.ts`, o único lugar autorizado a falar com a rede neste workspace
 * (`apps/field/AGENTS.md`). A função só grava via `SurveyRepository`, preservando a ordem
 * de `seq` que o chamador atribuiu.
 *
 * O caminho dos comandos de coleta NÃO passa mais por aqui: `applyCommand` grava survey e
 * operação juntos (`saveSurveyWithOperation`), porque as duas escritas precisam ser
 * atômicas. Esta função continua sendo o jeito de enfileirar uma operação sozinha, sem
 * mudança de survey — é o que a resolução de conflito (`conflict_resolution`) faz.
 */
export async function enqueueOperation(
  repository: SurveyRepository,
  operation: SurveyOperation,
): Promise<void> {
  await repository.appendOperation(operation);
}

/**
 * Reconhece uma operação: é o que o motor de sincronização chama para cada id devolvido em
 * `acked_operation_ids`. Idempotente — chamar duas vezes para a mesma `operationId` não
 * corrompe estado nem lança erro — e nunca remove a linha do outbox.
 */
export async function acknowledgeOperation(
  repository: SurveyRepository,
  operationId: string,
): Promise<void> {
  await repository.acknowledge(operationId);
}

/**
 * Próximo `seq` a partir das operações já conhecidas de um device — 1 se não houver
 * nenhuma, senão o maior `seq` da história VIVA + 1. Duas regras, e as duas importam:
 *
 * - `acked` ENTRA na conta: calcular sobre as pendências faria a sequência regredir depois
 *   de um ack e reutilizar um `seq` que o servidor já gravou (defeito corrigido na T1);
 * - `superseded` SAI da conta: essas operações pertencem à história que o técnico preteriu
 *   ao aceitar a versão do escritório (prancha 6b), e a operação de resolução já reancorou
 *   a sequência no ponto em que o servidor parou. Mantê-las na conta faria a próxima ação
 *   nascer no topo da história ABANDONADA — acima do que o servidor espera — e todo
 *   comando seguinte reabriria o conflito que a pessoa acabou de resolver.
 */
export function nextSeq(operations: readonly SurveyOperation[]): number {
  return (
    operations
      .filter((operation) => operation.status !== "superseded")
      .reduce((max, operation) => Math.max(max, operation.seq), 0) + 1
  );
}
