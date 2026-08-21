export interface AppBarProps {
  title: string;
  /** Operações do outbox ainda não reconhecidas pelo servidor. */
  pendingCount: number;
  isOnline: boolean;
}

/**
 * Barra superior escura de todas as telas (pacote aprovado, transversal): pílula
 * Online/Offline de alto contraste e contador de pendências sempre visível.
 */
export function AppBar({ title, pendingCount, isOnline }: AppBarProps) {
  return (
    <header className="appbar">
      <span className="appbar-brand">{title}</span>
      <span className="appbar-spacer" />
      {pendingCount > 0 && (
        <span className="pill pill-queue">
          {pendingCount} {pendingCount === 1 ? "pendente" : "pendentes"}
        </span>
      )}
      <span className={`pill ${isOnline ? "pill-online" : "pill-offline"}`}>
        <span className="pill-dot" />
        {isOnline ? "Online" : "Offline"}
      </span>
    </header>
  );
}
