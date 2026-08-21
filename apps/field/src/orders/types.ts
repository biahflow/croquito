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
  /** Endereço legível da ordem (T17, DAP rev.2, prancha 2), exibido na chegada no lugar
   * de coordenadas — aditivo: ordem sem este campo (fixture legada) mostra só `location`,
   * nunca quebra. */
  address?: string;
  /** Ponto de referência geográfico do endereço, só para o texto aproximado "a ~X m" da
   * chegada (Haversine local, `ui/arrivalLocation.ts`) — NUNCA geocodificação reversa nem
   * rede; é dado estático da fixture, referência geográfica, nunca medição (mesma regra
   * de `GpsFix`). Aditivo: ordem sem este campo simplesmente não mostra a distância. */
  address_location?: { lat: number; lng: number };
}
