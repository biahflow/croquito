export interface AddMenuProps {
  onAddPoint: () => void;
  onConnectPoints: () => void;
  onAddObservation: () => void;
  onClosePerimeter: () => void;
  onCancel: () => void;
  busy: boolean;
}

/**
 * Prancha 3b — menu Adicionar: lista plana de botões de 48 px, uma escolha por gesto.
 *
 * Curva/arco, elemento e foto aparecem desabilitados com o motivo no próprio rótulo: as
 * telas de definição de curva e o catálogo de elementos não fazem parte da revisão 1 do
 * pacote aprovado, e a foto real é fatia própria (T6). Um item que abre uma tela não
 * aprovada seria composição nova, não implementação.
 */
export function AddMenu({
  onAddPoint,
  onConnectPoints,
  onAddObservation,
  onClosePerimeter,
  onCancel,
  busy,
}: AddMenuProps) {
  return (
    <div className="screen">
      <div className="content">
        <h1 className="screen-title">Adicionar</h1>
        <p className="sub">O desenho continua atrás; uma escolha por vez.</p>
        <button
          type="button"
          className="btn btn-block btn-menu"
          onClick={onAddPoint}
          disabled={busy}
        >
          ●&nbsp;&nbsp;Ponto
        </button>
        <button
          type="button"
          className="btn btn-block btn-menu"
          onClick={onConnectPoints}
          disabled={busy}
        >
          ─&nbsp;&nbsp;Ligar pontos (segmento)
        </button>
        <button type="button" className="btn btn-block btn-menu" disabled>
          ◠&nbsp;&nbsp;Curva / arco (em breve)
        </button>
        <button type="button" className="btn btn-block btn-menu" disabled>
          ▢&nbsp;&nbsp;Elemento (em breve)
        </button>
        <button type="button" className="btn btn-block btn-menu" disabled>
          📷&nbsp;&nbsp;Foto ancorada (em breve)
        </button>
        <button
          type="button"
          className="btn btn-block btn-menu"
          onClick={onAddObservation}
          disabled={busy}
        >
          ✎&nbsp;&nbsp;Observação (texto)
        </button>
        <button
          type="button"
          className="btn btn-dark btn-block"
          onClick={onClosePerimeter}
          disabled={busy}
        >
          Fechar perímetro
        </button>
        <button type="button" className="btn btn-block" onClick={onCancel} disabled={busy}>
          Cancelar
        </button>
      </div>
    </div>
  );
}
