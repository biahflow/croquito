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
import { readRoute, routeSearch, type Route } from "./route";
import logoDark from "./assets/croquito-logo-dark.svg";

const CROQUI_ROOT: Route = { kind: "croqui", jobId: "" };

function currentRoute(): Route {
  return typeof window === "undefined"
    ? CROQUI_ROOT
    : readRoute(window.location.search);
}

/**
 * As duas jornadas têm regimes de autenticação DIFERENTES, e a assimetria é deliberada.
 * Ela mora aqui, pura e testável, porque quem ler `App.tsx` depois vai querer reduzi-la a
 * uma condição só — e reduzir apaga um dos dois caminhos.
 *
 * - **Croqui exige sessão, sempre.** Evidência e decisão de cena são de tenant
 *   autenticado; sem OIDC configurado o app já mostrava a tela anônima antes desta casca
 *   existir, e isso não muda.
 * - **Medição exige sessão QUANDO há OIDC configurado** — a API `/v1` do ADR-0028 (D9).
 *   Sem OIDC configurado a jornada continua ALCANÇÁVEL, e é ela quem diz o que falta: as
 *   rotas de medição são todas autenticadas, então a tela pede a sessão em vez de chamar
 *   a API. Fechá-la aqui apagaria a distinção entre "não há jornada" e "entre para abrir
 *   uma rodada", e a remoção do caminho local do ADR-0020 é tarefa própria da F-003.
 *
 * `hasSession` é booleano de propósito: a renovação silenciosa troca o objeto da sessão, e
 * o que decide o acesso é haver uma, não qual é.
 */
export function journeyIsOpen(
  kind: Route["kind"],
  hasSession: boolean,
  oidcConfigured: boolean,
): boolean {
  if (hasSession) {
    return true;
  }
  return kind === "medicao" && !oidcConfigured;
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

  const oidcConfigured = isOidcConfigured();
  const medicaoAberta = journeyIsOpen("medicao", session !== null, oidcConfigured);
  // O seletor abre jornada; ele aparece quando existe jornada a abrir. Com OIDC e sem
  // sessão não existe nenhuma, e ele some — como antes desta assimetria.
  const trocaDeJornada =
    medicaoAberta || journeyIsOpen("croqui", session !== null, oidcConfigured);

  // Tela anônima das duas jornadas: nenhuma evidência, decisão ou rodada é exibida sem a
  // sessão que a jornada pedida exige.
  const telaAnonima = (
    <section className="context-bar">
      <div>
        <span className="eyebrow">REVISÃO PROTEGIDA</span>
        <h1>Acesse uma revisão autenticada</h1>
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
          {/* Alternar jornada só faz sentido quando há jornada aberta; o seletor segue
              `journeyIsOpen`, não a sessão sozinha. O estado ativo é escrito em
              `aria-current`, não só pintado. Trocar de jornada fecha a que estava aberta —
              a URL passa a declarar a jornada nova, e nada fica aberto por baixo do que se
              vê. */}
          {trocaDeJornada ? (
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
      {route.kind === "medicao" ? (
        medicaoAberta ? (
          <MedicaoApp
            session={session}
            roundId={route.roundId}
            onOpenRound={handleOpenRound}
          />
        ) : (
          telaAnonima
        )
      ) : session ? (
        <CroquiApp session={session} onSessionLost={handleSessionLost} />
      ) : (
        telaAnonima
      )}
    </main>
  );
}
