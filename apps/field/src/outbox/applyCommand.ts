import type { CommandResult, Survey } from "../domain/types";
import type { SurveyRepository } from "../storage/SurveyRepository";
import { nextSeq } from "./outbox";
import type { SurveyOperation } from "./types";

export interface ApplyCommandOptions {
  device_id: string;
  /** UUID da operação — gerado por quem chama (é o mesmo valor que a sincronização usará
   * como `Idempotency-Key`, quando essa fatia existir). */
  operation_id: string;
  created_at: string;
}

export type ApplyCommandOutcome =
  | { ok: true; survey: Survey; operation: SurveyOperation }
  | { ok: false; error: { code: string; message: string } };

/**
 * Aplica o resultado de um comando de domínio: **persistência antes do estado**.
 *
 * A regra de `apps/field/AGENTS.md` — "toda ação do usuário persiste localmente via
 * `SurveyRepository` antes do feedback visual" — só é verificável se existir um caminho
 * único por onde todo comando passa. É este. Quem chama não deve gravar survey nem
 * enfileirar operação por conta própria: entrega o `CommandResult` aqui e só usa o
 * `survey` devolvido, que já está no IndexedDB junto da operação correspondente.
 *
 * Comando com erro não grava nada — nem survey, nem operação — e devolve o erro
 * estruturado do domínio (código estável + mensagem em português) para a tela mostrar.
 *
 * Comando ok grava os dois numa transação ÚNICA (`saveSurveyWithOperation`, T9): antes
 * disso eram duas escritas independentes e um app fechado entre elas deixava o survey
 * avançado sem a operação correspondente no outbox — a ação existiria no aparelho e nunca
 * chegaria ao servidor.
 */
export async function applyCommand(
  repository: SurveyRepository,
  survey: Survey,
  result: CommandResult,
  options: ApplyCommandOptions,
): Promise<ApplyCommandOutcome> {
  if (!result.ok) {
    return { ok: false, error: result.error };
  }

  const next = result.survey;

  // `survey.id` (o survey de ENTRADA) é a identidade autoritativa da operação: nenhum
  // comando troca de levantamento, e ancorar no estado anterior evita que um resultado
  // com id divergente enfileire a operação em outro survey.
  //
  // O histórico do device é a entrada de `nextSeq`, e é `nextSeq` que decide o que conta:
  // `acked` ENTRA (sobre as pendências a sequência regrediria depois de um ack,
  // reutilizando seq já emitido) e `superseded` SAI (história preterida ao aceitar a
  // versão do escritório, já reancorada pela operação de resolução). A regra inteira, com
  // o porquê de cada metade, está em `outbox.ts`.
  const history = await repository.listOperations(survey.id);
  const operation: SurveyOperation = {
    operation_id: options.operation_id,
    device_id: options.device_id,
    survey_id: survey.id,
    seq: nextSeq(history.filter((entry) => entry.device_id === options.device_id)),
    type: result.operation.type,
    payload: result.operation.payload,
    status: "local",
    created_at: options.created_at,
  };
  await repository.saveSurveyWithOperation(next, operation);

  return { ok: true, survey: next, operation };
}
