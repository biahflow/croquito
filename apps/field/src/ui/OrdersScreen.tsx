import type { Order } from "../orders/types";
import type { OrderState } from "../orders/state";

export interface OrdersScreenProps {
  orders: Order[];
  stateByOrderId: Map<string, OrderState>;
  isOnline: boolean;
  busy: boolean;
  onDownload: (order: Order) => void;
  onOpen: (order: Order) => void;
}

/**
 * Prancha 1 — a porta do app: um cartão por ordem, estado sempre escrito na etiqueta
 * (nunca só cor). "Baixar" cria o levantamento local da ordem (instantâneo, sem rede —
 * Task Contract T4, Out of Scope); offline desabilita o download de ordem nova, mas
 * ordens já baixadas continuam abrindo normalmente.
 */
export function OrdersScreen({
  orders,
  stateByOrderId,
  isOnline,
  busy,
  onDownload,
  onOpen,
}: OrdersScreenProps) {
  if (orders.length === 0) {
    return (
      <div className="screen">
        <div className="content">
          <h1 className="screen-title">Ordens de levantamento</h1>
          <div className="banner banner-info" role="status">
            <span>
              Nenhuma ordem atribuída a você. Quando o escritório designar um
              levantamento, ele aparece aqui — baixe antes de sair para o campo.
            </span>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="screen">
      <div className="content">
        <h1 className="screen-title">Ordens de levantamento</h1>
        <p className="sub">
          {orders.length} {orders.length === 1 ? "ordem" : "ordens"}
        </p>
        {!isOnline && (
          <div className="banner banner-info" role="status">
            <span>
              Você está sem internet. As ordens já baixadas abrem normalmente; baixar uma
              ordem nova exige conexão.
            </span>
          </div>
        )}
        {orders.map((order) => {
          const state = stateByOrderId.get(order.id) ?? "not_downloaded";
          const downloaded = state === "downloaded";
          return (
            <div className="card" key={order.id}>
              <span className={downloaded ? "tag tag-ok" : "tag"}>
                {downloaded ? "Baixada — abre offline" : "Não baixada"}
              </span>
              <span className="card-title">{order.name}</span>
              <span className="card-meta">
                {downloaded
                  ? `${order.location} · ${order.scope_label} · ${order.checklist.length} itens no checklist`
                  : `Escopo: ${order.scope_label} · ${order.checklist.length} itens no checklist`}
              </span>
              {downloaded ? (
                <button
                  type="button"
                  className="btn btn-dark btn-block"
                  onClick={() => onOpen(order)}
                  disabled={busy}
                >
                  Abrir levantamento
                </button>
              ) : (
                <button
                  type="button"
                  className="btn btn-block"
                  onClick={() => onDownload(order)}
                  disabled={busy || !isOnline}
                >
                  {isOnline ? "Baixar para usar offline" : "Baixar (sem conexão)"}
                </button>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
