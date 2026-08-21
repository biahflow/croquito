export interface AddMenuProps {
  onAddPoint: () => void;
  onConnectPoints: () => void;
  onAddPhotoAnchor: () => void;
  onAddObservation: () => void;
  onAddVoiceNote: () => void;
  onClosePerimeter: () => void;
  onConclude: () => void;
  onCancel: () => void;
  busy: boolean;
}

/**
 * Prancha 3b — menu Adicionar: lista plana de botões de 48 px, uma escolha por gesto.
 *
 * Curva/arco e elemento seguem desabilitados com o motivo no próprio rótulo: as telas de
 * definição de curva e o catálogo de elementos não fazem parte da revisão 1 do pacote
 * aprovado. Um item que abre uma tela não aprovada seria composição nova, não
 * implementação. "Foto ancorada" (T6) já habilita: o fluxo usa `<input type="file"
 * capture="environment">` nativo do aparelho — nunca uma tela de câmera própria, que o
 * pacote aprovado explicitamente deixa fora ("captura e revisão de foto (câmera
 * aberta)" — Design Approval Package, "Explicitamente não aprovado").
 *
 * "Observação por voz" (T12) usa a mesma lista: o item de menu da prancha 3b sempre citou
 * "Observação (texto ou voz)", e a voz ganhou entrada própria em vez de um seletor dentro
 * da tela de texto — uma escolha por gesto é a regra desta prancha.
 *
 * "Concluir levantamento" (T5) entra aqui, não na bottombar da prancha 3a: é a opção
 * menos invasiva ao pacote aprovado — 3a permanece com os três comandos exatos da
 * revisão 1, e este menu já é uma lista extensível (mesmo padrão de "Fechar perímetro",
 * que também não está nos itens originais da prancha 3b).
 */
export function AddMenu({
  onAddPoint,
  onConnectPoints,
  onAddPhotoAnchor,
  onAddObservation,
  onAddVoiceNote,
  onClosePerimeter,
  onConclude,
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
        <button
          type="button"
          className="btn btn-block btn-menu"
          onClick={onAddPhotoAnchor}
          disabled={busy}
        >
          📷&nbsp;&nbsp;Foto ancorada
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
          className="btn btn-block btn-menu"
          onClick={onAddVoiceNote}
          disabled={busy}
        >
          🎤&nbsp;&nbsp;Observação por voz
        </button>
        <button
          type="button"
          className="btn btn-dark btn-block"
          onClick={onClosePerimeter}
          disabled={busy}
        >
          Fechar perímetro
        </button>
        <button
          type="button"
          className="btn btn-dark btn-block"
          onClick={onConclude}
          disabled={busy}
        >
          Concluir levantamento
        </button>
        <button type="button" className="btn btn-block" onClick={onCancel} disabled={busy}>
          Cancelar
        </button>
      </div>
    </div>
  );
}
