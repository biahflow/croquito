/**
 * Tipos da ordem de levantamento (prancha 1 do Design Approval Package).
 *
 * Esta fatia (T4) não tem rede: a fixture local (`fixture.ts`) é o "servidor". A origem
 * real da ordem (quem a cria, onde) é um `Unknown` do Feature Contract, a decidir no
 * design de uma fatia futura de sincronização.
 */

export type OrderId = string;

export interface ChecklistItem {
  id: string;
  label: string;
  required: boolean;
}

export interface Order {
  id: OrderId;
  /** Nome completo, como aparece no cartão da lista (prancha 1). */
  name: string;
  /** Nome curto, como aparece na AppBar das telas de chegada e coleta (pranchas 2+). */
  short_name: string;
  location: string;
  scope_label: string;
  checklist: ChecklistItem[];
}
