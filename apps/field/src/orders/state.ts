/**
 * Estado da ordem — DERIVADO do survey local, nunca duplicado (Task Contract T4,
 * Especificação §2 e Known Risks).
 *
 * "Baixada" existe sse há um survey local cujo id é `survey-<order_id>`; "concluída"
 * (T5) é `surveyStatus(survey) === "concluded"` — mesmo dado que `ConcludeScreen` usa
 * para desbloquear o botão, nunca um estado próprio da ordem.
 */

import { surveyStatus, type Survey } from "../domain/types";
import type { RequiredItem } from "../domain/validation";
import type { Order, OrderId } from "./types";

export type OrderState = "not_downloaded" | "downloaded" | "concluded";

/** Um survey local por ordem (Especificação §6) — o id é determinístico a partir do id
 * da ordem, então nenhum índice extra precisa ser mantido para achar o survey de uma
 * ordem. */
export function surveyIdForOrder(orderId: OrderId): string {
  return `survey-${orderId}`;
}

/** `survey` é o resultado de `SurveyRepository.getSurvey(surveyIdForOrder(order.id))` —
 * esta função só lê presença/ausência e status, nunca consulta o repositório por conta
 * própria (mantém a lógica pura e testável sem IndexedDB). */
export function deriveOrderState(survey: Survey | undefined): OrderState {
  if (survey === undefined) {
    return "not_downloaded";
  }
  return surveyStatus(survey) === "concluded" ? "concluded" : "downloaded";
}

/**
 * Checklist da ordem no formato que `validateSurvey` consome (Task Contract T4,
 * Especificação §5; satisfação de `foto-acesso` refeita em T6, Scope): só `foto-acesso`
 * é verificável hoje, e agora É derivado — satisfeito quando existe mídia do acesso
 * gravada para este survey (`survey.context?.access_media_ref`, preenchido por
 * `recordArrival` quando a foto é capturada na chegada, T6). Sem `survey` (ordem ainda
 * não baixada/aberta), conta como pendente — mesmo comportamento anterior a T6. Os
 * demais itens contam como satisfeitos, porque a materialização item a item é de fatias
 * futuras e não deve virar regra inventada aqui.
 */
export function requiredItemsForOrder(order: Order, survey?: Survey): RequiredItem[] {
  return order.checklist
    .filter((item) => item.required)
    .map((item) => ({
      id: item.id,
      label: item.label,
      satisfied:
        item.id === "foto-acesso" ? survey?.context?.access_media_ref !== undefined : true,
    }));
}
