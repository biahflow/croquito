import type { ReviewDecision, ReviewReading } from "./api";
import { suggestedAnnotationHint } from "./labels";

/**
 * Lote de confirmação das leituras que o pipeline sugeriu como anotação da folha.
 *
 * Módulo puro, testável sem DOM: quem decide o que entra no lote é esta regra, e não a
 * marcação visual. A sugestão vem de `suggestedAnnotationHint` (F-021) e continua sendo
 * observação — o lote só existe para poupar o revisor de repetir o mesmo ato dezenas de
 * vezes; ele não confirma nada sozinho.
 */

/**
 * Leituras elegíveis ao lote, na ordem em que a lista as mostra: sem decisão registrada
 * e com sugestão de anotação. Leitura já decidida fica de fora porque decisão gravada se
 * corrige pelo caminho da retificação, nunca por um segundo envio em lote; e leitura sem
 * sugestão fica de fora porque cota de chão precisa declarar associação e eixo, um a um.
 */
export function suggestedAnnotationIds(readings: ReviewReading[]): string[] {
  return readings
    .filter(
      (reading) => !reading.decision && suggestedAnnotationHint(reading) !== null,
    )
    .map((reading) => reading.id);
}

/**
 * Monta as decisões individuais do lote: uma justificativa escrita pelo revisor,
 * replicada em cada `HumanDecision` gravada. É o espelho cliente do que o lote de
 * propostas já faz no servidor (`submit_proposal_batch`, em
 * `services/api/src/croquito_api/main.py`), onde a mesma palavra acompanha cada decisão
 * do lote — o registro auditado continua sendo por leitura, com autor e motivo.
 *
 * A seleção é FILTRADA contra as elegíveis: id já decidido, id de leitura sem sugestão
 * ou id que nem está mais nesta revisão não vira decisão. Marcação envenenada (seleção
 * de uma versão anterior, rascunho colado, defeito de tela) não pode virar palavra
 * humana gravada sobre uma cota.
 *
 * Sem `association_proposal_id`: anotação da folha não leva associação de elemento, e a
 * API recusa o par (`Anotação da folha não leva associação de elemento.`).
 */
export function buildAnnotationBatch(
  readings: ReviewReading[],
  selectedIds: Set<string>,
  justification: string,
): ReviewDecision[] {
  return suggestedAnnotationIds(readings)
    .filter((readingId) => selectedIds.has(readingId))
    .map((readingId) => ({
      reading_id: readingId,
      action: "confirm" as const,
      annotation: true,
      justification: justification.trim(),
    }));
}
