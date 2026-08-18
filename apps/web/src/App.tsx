import { useCallback, useEffect, useState } from "react";
import sceneSchema from "@croquito/contracts/scene.schema.json";
import type { User } from "oidc-client-ts";

import {
  clearSession,
  isOidcConfigured,
  onSessionRenewed,
  readSession,
  signIn,
  signOut,
} from "./auth";
import { CroquiApp } from "./CroquiApp";
import { MedicaoApp } from "./medicao/MedicaoApp";
import { entryRedirect, readRoute, routeSearch, type Route } from "./route";
import logoDark from "./assets/croquito-logo-dark.svg";

const CROQUI_ROOT: Route = { kind: "croqui", jobId: "" };

function currentRoute(): Route {
  return typeof window === "undefined"
    ? CROQUI_ROOT
    : readRoute(window.location.search);
}

/**
 * Põe a URL no lugar que o ADR-0032 declara: sem sessão, a porta de entrada; com sessão,
 * a jornada. A decisão inteira — inclusive a exceção do retorno do OIDC, que é o que
 * separa produto de produto inacessível — é pura e mora em `route.ts`; aqui só o efeito.
 *
 * `replaceState` e não `location.assign`: recarregar a página jogaria fora o estado do
 * OIDC, que vive em memória, e é o mesmo mecanismo que a casca já usa para navegar.
 */
function applyEntryRedirect(hasSession: boolean): void {
  if (typeof window === "undefined") {
    return;
  }
  const target = entryRedirect(
    window.location,
    hasSession,
    import.meta.env.BASE_URL,
  );
  if (target !== null) {
    window.history.replaceState(null, "", target);
  }
}

/**
 * Casca do app: uma sessão OIDC, um build, um deploy (ADR-0028, D9). Ela autentica,
 * mostra a identidade e alterna entre as jornadas; quem resolve croqui ou medição são
 * os componentes de jornada, não ela.
 *
 * A sessão tem um dono só, e é aqui. `readSession()` consome o authorization code do
 * redirect, que é de uso único: se a casca e a jornada chamassem, a segunda chamada
 * falharia e a volta do login cairia na tela anônima.
 */
export function App() {
  const [session, setSession] = useState<User | null>(null);
  const [route, setRoute] = useState<Route>(currentRoute);
  // Erro de sessão é da casca e é persistente: ele sobrevive à jornada que saiu da tela.
  const [sessionNotice, setSessionNotice] = useState<string | null>(null);

  useEffect(() => {
    if (!isOidcConfigured()) {
      // Sem OIDC configurado não há sessão possível, e o estado sem sessão é a porta de
      // entrada: é lá que "você não entrou" e "o ambiente está fora do ar" se distinguem
      // (ADR-0032, D3). A exceção do retorno do OIDC vale aqui também — este caminho não
      // passou por `readSession()`, então a URL pode ainda carregar `code`+`state`.
      applyEntryRedirect(false);
      return;
    }
    void (async () => {
      let currentSession: User | null;
      try {
        currentSession = await readSession();
      } catch (error) {
        // Falha aqui é OIDC de verdade; erro de API tem outra causa e outro dono.
        setSessionNotice(
          `Não foi possível validar a sessão OIDC: ${
            error instanceof Error ? error.message : String(error)
          }`,
        );
        applyEntryRedirect(false);
        return;
      }
      // Só agora a URL é confiável: `readSession` limpa o retorno do OIDC e devolve o
      // job que viajou no `state`. Ler a rota antes disso abriria a jornada errada.
      setRoute(currentRoute());
      setSession(currentSession);
      // O rebote entra DEPOIS dessa ordem, e a ordem é o que o mantém seguro: quando ele
      // corre, o código de uso único já foi gasto e `code`/`state` já saíram da URL.
      applyEntryRedirect(currentSession !== null);
    })();
    return onSessionRenewed(setSession);
  }, []);

  const openJourney = useCallback(
    (next: Route) => {
      // Clicar na jornada já aberta não é navegação. Reescrever a URL aqui apagaria o
      // `?job` que a jornada do croqui mantém nela (a jornada não remonta, porque a
      // casca não troca de componente), e a tela ficaria divergente do endereço.
      if (next.kind === route.kind) {
        return;
      }
      setRoute(next);
      window.history.replaceState(
        null,
        "",
        routeSearch(next) || window.location.pathname,
      );
    },
    [route.kind],
  );

  /**
   * A rodada aberta na medição é declarada na URL (`?rodada=<id>`), como o `?job` do
   * croqui: sem isso, recarregar a página devolveria a orçamentista à lista de rodadas no
   * meio de uma revisão. Quem escolhe a rodada é a jornada; a casca só escreve o endereço,
   * sem remontar nada — `replaceState` não navega.
   */
  const handleOpenRound = useCallback((roundId: string) => {
    const next: Route = { kind: "medicao", roundId };
    setRoute(next);
    window.history.replaceState(null, "", routeSearch(next));
  }, []);

  const handleSessionLost = useCallback((notice: string) => {
    void clearSession();
    setSession(null);
    setSessionNotice(notice);
  }, []);

  // As duas jornadas têm o MESMO regime: sessão OIDC ou nada. A medição já teve um
  // caminho sem sessão (o servidor local do ADR-0020, falado por outra origem); ele saiu
  // com a migração para a API `/v1` (ADR-0028), e toda rota de medição é autenticada e por
  // tenant. O seletor abre jornada, então ele só aparece quando existe jornada a abrir.
  const autenticado = session !== null;

  // O estado sem sessão é a porta de entrada (`/login`, ADR-0032 D3), e não mais a casca
  // vazia de uma jornada: nenhuma evidência, decisão ou rodada existe antes da sessão.
  // PLACEHOLDER declarado: o texto e o visual aprovados, e a retirada da casca das
  // jornadas daqui, são da T3 — esta task entrega o estado e o rebote.
  const telaLogin = (
    <section className="context-bar">
      <div>
        <span className="eyebrow">ENTRADA</span>
        <h1>Entre para continuar</h1>
      </div>
    </section>
  );

  return (
    <main className="app-shell">
      <header className="topbar">
        {/* Início desta SPA, não raiz do host: em homologação a raiz redireciona para cá,
            e o caminho da marca deve ser o mesmo que o `redirect_uri` do login. */}
        <a
          className="brand"
          href={import.meta.env.BASE_URL}
          aria-label="Croquito - início"
        >
          <img className="brand-logo" src={logoDark} alt="Croquito" />
          <small>Revisão humana autenticada</small>
        </a>
        <div className="topbar-actions">
          {/* Alternar jornada só faz sentido quando há jornada aberta, e sem sessão não
              há nenhuma. O estado ativo é escrito em `aria-current`, não só pintado.
              Trocar de jornada fecha a que estava aberta — a URL passa a declarar a
              jornada nova, e nada fica aberto por baixo do que se vê. */}
          {autenticado ? (
            <nav className="journey-switch" aria-label="Jornadas">
              <button
                className="topbar-link"
                type="button"
                aria-current={route.kind === "croqui" ? "page" : undefined}
                onClick={() => openJourney(CROQUI_ROOT)}
              >
                Croqui
              </button>
              <button
                className="topbar-link"
                type="button"
                aria-current={route.kind === "medicao" ? "page" : undefined}
                onClick={() => openJourney({ kind: "medicao", roundId: "" })}
              >
                Medição
              </button>
            </nav>
          ) : null}
          <span className="schema-pill">
            Cena {sceneSchema.$id?.split("/").at(-1)}
          </span>
          {session ? (
            <span className="identity-pill">
              Sessão:{" "}
              {session.profile.preferred_username ?? session.profile.sub}
            </span>
          ) : null}
          {isOidcConfigured() && !session ? (
            <button
              className="button button-quiet"
              type="button"
              onClick={() => void signIn()}
            >
              Entrar
            </button>
          ) : null}
          {session ? (
            <button
              className="button button-quiet"
              type="button"
              onClick={() => void signOut()}
            >
              Sair
            </button>
          ) : null}
        </div>
      </header>

      {!isOidcConfigured() ? (
        <p className="session-error">
          OIDC não está configurado neste ambiente; nenhuma evidência ou decisão
          é exibida.
        </p>
      ) : null}
      {sessionNotice ? (
        <p className="app-alert" role="alert">
          <span>{sessionNotice}</span>
          <button
            type="button"
            className="app-alert-close"
            onClick={() => setSessionNotice(null)}
            aria-label="Fechar aviso"
          >
            ×
          </button>
        </p>
      ) : null}

      {/* A medição fala com a API `/v1` autenticada (ADR-0028): a sessão desce por prop e
          a rodada aberta vem da URL, para sobreviver a um reload. */}
      {!session ? (
        telaLogin
      ) : route.kind === "medicao" ? (
        <MedicaoApp
          session={session}
          roundId={route.roundId}
          onOpenRound={handleOpenRound}
        />
      ) : (
        <CroquiApp session={session} onSessionLost={handleSessionLost} />
      )}
    </main>
  );
}
