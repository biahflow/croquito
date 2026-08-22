const ACTIVE_ORDER_STORAGE_KEY = "croquito-field-active-order-id";

/**
 * Ordem aberta neste aparelho, estável entre sessões — é o que faz o reload voltar direto
 * à chegada/coleta da ordem aberta em vez de cair na lista (Task Contract T4, Acceptance
 * Criteria 3). Mesma disciplina de `ui/device.ts`: localStorage, não estado de React.
 */
export function getActiveOrderId(): string | null {
  return localStorage.getItem(ACTIVE_ORDER_STORAGE_KEY);
}

export function setActiveOrderId(orderId: string): void {
  localStorage.setItem(ACTIVE_ORDER_STORAGE_KEY, orderId);
}

export function clearActiveOrderId(): void {
  localStorage.removeItem(ACTIVE_ORDER_STORAGE_KEY);
}
