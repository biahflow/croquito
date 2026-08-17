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
import { readRoute, routeSearch, type Route } from "./route";
import logoDark from "./assets/croquito-logo-dark.svg";

const CROQUI_ROOT: Route = { kind: "croqui", jobId: "" };

function currentRoute(): Route {
  return typeof window === "undefined"
    ? CROQUI_ROOT
    : readRoute(window.location.search);
}

/**
 * Jornada da medição de obra. Ainda não migrou: as telas de revisão de takeoff,
 * confirmação de código e boletim continuam em `apps/medicao`, contra o servidor de
 * medição. Esta tela declara o estado em vez de simular a jornada — nenhuma rodada é
 * lida, nenhum número é exibido e nada aqui é dado de obra.
 *
 * Exportada para o teste: a casca só alcança as jornadas com sessão, e a renderização
 * estática não tem como criar uma.
 */
export function MedicaoJourney() {
  return (
    <section className="jornada-medicao" aria-labelledby="medicao-indisponivel">
      <span className="eyebrow">MEDIÇÃO DE OBRA</span>
      <h1 id="medicao-indisponivel">
        A jornada de medição ainda não está nesta build
      </h1>
      <p>
        As telas de revisão de takeoff, confirmação de código, boletim e dossiê
        do aditivo continuam no app de homologação da medição e migram para cá
        nas próximas etapas desta feature. Nenhuma rodada é lida ou exibida por
        esta tela.
      </p>
    </section>
  );
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
        return;
      }
      // Só agora a URL é confiável: `readSession` limpa o retorno do OIDC e devolve o
      // job que viajou no `state`. Ler a rota antes disso abriria a jornada errada.
      setRoute(currentRoute());
      setSession(currentSession);
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

  const handleSessionLost = useCallback((notice: string) => {
    void clearSession();
    setSession(null);
    setSessionNotice(notice);
  }, []);

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
          {/* Alternar jornada é navegação dentro da sessão; sem sessão não há o que abrir
              e o seletor não aparece. O estado ativo é escrito em `aria-current`, não só
              pintado. Trocar de jornada fecha a que estava aberta — a URL passa a
              declarar a jornada nova, e nada fica aberto por baixo do que se vê. */}
          {session ? (
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

      {session ? (
        route.kind === "croqui" ? (
          <CroquiApp session={session} onSessionLost={handleSessionLost} />
        ) : (
          <MedicaoJourney />
        )
      ) : (
        <section className="context-bar">
          <div>
            <span className="eyebrow">REVISÃO PROTEGIDA</span>
            <h1>Acesse uma revisão autenticada</h1>
          </div>
        </section>
      )}
    </main>
  );
}
