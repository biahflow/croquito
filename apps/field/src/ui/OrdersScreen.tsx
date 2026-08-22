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
          // "Concluída" (T5) é status do survey, nunca um estado próprio da ordem — ver
          // `orders/state.ts`. Tanto "downloaded" quanto "concluded" já têm o survey
          // local, então abrem do mesmo jeito (concluído abre em somente leitura).
          const hasLocalSurvey = state !== "not_downloaded";
          const concluded = state === "concluded";
          return (
            <div className="card" key={order.id}>
              <span className={hasLocalSurvey ? "tag tag-ok" : "tag"}>
                {concluded
                  ? "Concluída"
                  : hasLocalSurvey
                    ? "Baixada — abre offline"
                    : "Não baixada"}
              </span>
              <span className="card-title">{order.name}</span>
              <span className="card-meta">
                {hasLocalSurvey
                  ? `${order.location} · ${order.scope_label} · ${order.checklist.length} itens no checklist`
                  : `Escopo: ${order.scope_label} · ${order.checklist.length} itens no checklist`}
              </span>
              {hasLocalSurvey ? (
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
