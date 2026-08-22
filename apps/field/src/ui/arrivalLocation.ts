/**
 * Texto do check de localização da chegada (Task Contract T17, prancha 2 da DAP rev.2):
 * nome + endereço da ordem no lugar de coordenadas cruas. Função pura — nada aqui importa
 * React nem `navigator.geolocation`, mesma disciplina de `ui/photoQualityGate.ts`, então é
 * testável em node puro, sem DOM.
 *
 * O `GpsFix` continua exatamente como antes desta tarefa (domínio/outbox intocados,
 * `apps/field/AGENTS.md`) — só deixa de ser IMPRESSO na tela. A distância aproximada
 * "a ~X m" usa a fórmula de Haversine entre o fix do GPS e `Order.address_location`,
 * ambos já conhecidos localmente: NUNCA geocodificação reversa, NUNCA rede. Sem os dois
 * pontos, a parte da distância é omitida — nunca inventada.
 */

import type { GpsFix } from "../domain/types";
import type { Order } from "../orders/types";

const EARTH_RADIUS_M = 6371000;

function toRadians(deg: number): number {
  return (deg * Math.PI) / 180;
}

type LatLng = { lat: number; lng: number };

/** Distância aproximada entre dois pontos já conhecidos (fórmula de Haversine) — não é
 * medição, só referência geográfica (mesma regra de `GpsFix`). */
function haversineMeters(a: LatLng, b: LatLng): number {
  const dLat = toRadians(b.lat - a.lat);
  const dLng = toRadians(b.lng - a.lng);
  const lat1 = toRadians(a.lat);
  const lat2 = toRadians(b.lat);
  const h = Math.sin(dLat / 2) ** 2 + Math.cos(lat1) * Math.cos(lat2) * Math.sin(dLng / 2) ** 2;
  return 2 * EARTH_RADIUS_M * Math.asin(Math.min(1, Math.sqrt(h)));
}

export interface ArrivalLocationText {
  title: string;
  detail: string;
}

const LOCATION_DISCLAIMER = "a localização serve para achar a obra, não para medir";

/**
 * `order === null` é o fallback defensivo de uma corrida entre telas — `ArrivalScreen` só
 * renderiza com uma ordem ativa em uso normal, mas o texto não pode quebrar se acontecer.
 * `fix` é o GPS resolvido (`undefined` enquanto pendente ou quando indisponível — as duas
 * situações omitem a distância do mesmo jeito, já que o efeito na tela é idêntico).
 */
export function describeArrivalLocation(order: Order | null, fix: GpsFix | undefined): ArrivalLocationText {
  if (order === null) {
    return {
      title: "Local confirmado",
      detail: `A localização serve para achar a obra, não para medir.`,
    };
  }
  const place = order.address !== undefined ? `${order.address} · ${order.location}` : order.location;
  const distance =
    fix !== undefined && order.address_location !== undefined
      ? ` — a ~${Math.round(haversineMeters(fix, order.address_location))} m do endereço da ordem`
      : "";
  return {
    title: `Local confirmado — ${order.name}`,
    detail: `${place}${distance} · ${LOCATION_DISCLAIMER}`,
  };
}
