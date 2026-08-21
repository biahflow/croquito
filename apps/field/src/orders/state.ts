/**
 * Estado da ordem — DERIVADO do survey local, nunca duplicado (Task Contract T4,
 * Especificação §2 e Known Risks).
 *
 * "Baixada" existe sse há um survey local cujo id é `survey-<order_id>`; "concluída" é
 * estado de T5 e não é inventado aqui.
 */

import type { Survey } from "../domain/types";
import type { RequiredItem } from "../domain/validation";
import type { Order, OrderId } from "./types";

export type OrderState = "not_downloaded" | "downloaded";

/** Um survey local por ordem (Especificação §6) — o id é determinístico a partir do id
 * da ordem, então nenhum índice extra precisa ser mantido para achar o survey de uma
 * ordem. */
export function surveyIdForOrder(orderId: OrderId): string {
  return `survey-${orderId}`;
}

/** `survey` é o resultado de `SurveyRepository.getSurvey(surveyIdForOrder(order.id))` —
 * esta função só lê presença/ausência, nunca consulta o repositório por conta própria
 * (mantém a lógica pura e testável sem IndexedDB). */
export function deriveOrderState(survey: Survey | undefined): OrderState {
  return survey === undefined ? "not_downloaded" : "downloaded";
}

/**
 * Checklist da ordem no formato que `validateSurvey` consome (Task Contract T4,
 * Especificação §5): só `foto-acesso` é verificável hoje — e permanece pendente até T6
 * entregar a captura; os demais itens contam como satisfeitos, porque a materialização
 * item a item é de fatias futuras e não deve virar regra inventada aqui.
 */
export function requiredItemsForOrder(order: Order): RequiredItem[] {
  return order.checklist
    .filter((item) => item.required)
    .map((item) => ({
      id: item.id,
      label: item.label,
      satisfied: item.id !== "foto-acesso",
    }));
}
