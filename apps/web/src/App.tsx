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
 * Texto da porta de entrada, aprovado por ato humano em 2026-08-18 e fixado palavra por
 * palavra no Task Contract da T3 (`docs/features/F-007-tela-de-login/tasks/`). Ele está
 * junto num lugar só porque mudar qualquer uma destas linhas REABRE o gate humano: quem
 * editar aqui está mexendo num artefato aprovado, não em copy de tela.
 */
const PROMESSA = "Do croqui ao orçamento.";
const CTA_ENTRAR = "Entrar";
const CONVITE =
  "O acesso nasce por convite. Peça o seu a quem administra sua organização.";
const AMBIENTE_INDISPONIVEL =
  "O ambiente está indisponível agora. Tente de novo em instantes — se persistir, " +
  "avise a operação.";
const TITULO_LOGIN = "Entrar — Croquito";
/** Título de `index.html`, para onde a aba volta assim que a sessão existe. */
const TITULO_JORNADA = "Croquito";

/**
 * Host de homologação, o único ambiente em que a pílula aparece (decisão humana de
 * 2026-08-18). O mecanismo é o HOSTNAME, e não uma variável de ambiente nova: `apps/web`
 * hoje só lê `VITE_OIDC_*` e `VITE_API_BASE_URL`, nenhuma delas descreve ambiente, e
 * inventar `VITE_ENVIRONMENT` obrigaria a mexer no build, no Dockerfile e no serviço de
 * homologação para exibir um rótulo. O endereço já é o fato — está no ADR-0032 e no realm
 * (`redirectUris` de `croquito-hml`) — e derivar dele mantém a decisão em um lugar só.
 *
 * Consequência aceita: em desenvolvimento e em produção a pílula não aparece, que é
 * exatamente o que foi decidido.
 */
const HOMOLOGATION_HOST = "croquito-hml.biahflow.ai";

export function isHomologationHost(hostname: string): boolean {
  return hostname === HOMOLOGATION_HOST;
}

function currentHostname(): string {
  return typeof window === "undefined" ? "" : window.location.hostname;
}

/**
 * Existe identity provider federado configurado no realm? Enquanto não existir, o botão
 * "Entrar com Google" **não é renderizado** — nem desabilitado, nem oculto por CSS
 * (critério 9 da F-007). Hoje a resposta é `false` por fato verificado, não por
 * conveniência: nem `keycloak/croquito-realm.json` nem `keycloak/croquito-hml-realm.json`
 * declaram `identityProviders`.
 *
 * Quem liga o provedor é a F-008 (ADR-0033); é lá que esta função passa a perguntar ao
 * realm em vez de responder por constante. O lugar do botão — o divisor e a posição dentro
 * do card — já nasce desenhado, para que a tela aprovada não precise ser redesenhada.
 */
function identityProvidersConfigured(): boolean {
  return false;
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

  // A aba também é a porta: quem manda o endereço para alguém manda um título junto. O
  // efeito roda só no browser, e devolve o título de `index.html` assim que há sessão.
  useEffect(() => {
    if (typeof document === "undefined") {
      return;
    }
    document.title = session === null ? TITULO_LOGIN : TITULO_JORNADA;
  }, [session]);

  // O estado sem sessão é a porta de entrada (`/login`, ADR-0032 D3), e não mais a casca
  // vazia de uma jornada: nenhuma evidência, decisão ou rodada existe antes da sessão.
  // Ela retorna CEDO, e é isso que cumpre o D3 — nenhuma peça da casca (topbar, marca,
  // pílula de schema, alternância de jornada) chega a ser construída antes da sessão.
  //
  // As duas jornadas têm o MESMO regime: sessão OIDC ou nada. A medição já teve um caminho
  // sem sessão (o servidor local do ADR-0020, falado por outra origem); ele saiu com a
  // migração para a API `/v1` (ADR-0028), e toda rota de medição é autenticada e por
  // tenant. Depois deste retorno, portanto, `session` existe — e a casca inteira, inclusive
  // a alternância de jornada, deixa de precisar perguntar.
  if (session === null) {
    // Sem OIDC configurado não há como entrar, e a distinção que a F-006 pagou caro para
    // aprender ("você não entrou" ≠ "o ambiente caiu") é o que esta tela precisa dizer: o
    // aviso vira estado da porta, com o CTA desabilitado, e não um `<p>` solto acima de
    // uma casca vazia.
    const ambienteNoAr = isOidcConfigured();
    return (
      <main className="login">
        {/* Painel de marca. O croqui e a promessa são o que a porta apresenta antes de
            pedir qualquer coisa; nenhum dado de projeto existe aqui. */}
        <div className="login-showcase">
          <div className="login-showcase-grid" aria-hidden="true" />
          <img className="login-wordmark" src={logoDark} alt="Croquito" />
          <h1 className="login-promise">{PROMESSA}</h1>
          {/* Croqui vetorial do mock aprovado (revisão 2): decoração de marca, sem
              conteúdo — quem usa leitor de tela não perde nada ao pulá-lo. */}
          <svg
            className="login-croqui"
            viewBox="0 0 320 190"
            fill="none"
            aria-hidden="true"
          >
            <path
              className="login-croqui-line"
              d="M24 150 L24 62 L108 22 L192 62 L192 150 Z"
              strokeWidth="2"
              strokeLinejoin="round"
            />
            <path
              className="login-croqui-line login-croqui-far"
              d="M192 62 L276 40 L276 128 L192 150"
              strokeWidth="2"
              strokeLinejoin="round"
            />
            <path
              className="login-croqui-detail"
              d="M62 150 L62 104 L94 104 L94 150"
              strokeWidth="1.5"
            />
            <path
              className="login-croqui-detail"
              d="M128 74 L166 74 L166 106 L128 106 Z"
              strokeWidth="1.5"
            />
            <path
              className="login-croqui-dim"
              d="M24 172 L192 172 M24 166 L24 178 M192 166 L192 178"
              strokeWidth="1.5"
            />
            <path
              className="login-croqui-dim login-croqui-far"
              d="M300 40 L300 128 M294 40 L306 40 M294 128 L306 128"
              strokeWidth="1.5"
            />
            <circle className="login-croqui-node" cx="108" cy="22" r="3.6" />
            <circle className="login-croqui-node" cx="192" cy="62" r="3.6" />
            <circle className="login-croqui-node" cx="24" cy="62" r="3.6" />
          </svg>
        </div>

        <div className="login-panel">
          <div className="login-card">
            {/* Símbolo da marca, o mesmo de `apps/web/public/favicon.svg`. Embutido para
                não depender de um caminho de asset: `/login` é servido pelo build de
                `/revisao/` (ADR-0032, D2). */}
            <svg
              className="login-mark"
              viewBox="0 0 100 100"
              role="img"
              aria-label="Croquito"
            >
              <rect width="100" height="100" rx="22" fill="var(--dark)" />
              <rect
                x="30"
                y="30"
                width="40"
                height="40"
                fill="none"
                stroke="var(--accent)"
                strokeWidth="11"
              />
            </svg>

            {!ambienteNoAr ? (
              <p className="login-alert" role="alert">
                <svg
                  className="login-alert-icon"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  aria-hidden="true"
                >
                  <path d="M12 9v5M12 17.5v.5" />
                  <path d="M10.3 3.9 2.4 17.5A1.8 1.8 0 0 0 4 20.2h16a1.8 1.8 0 0 0 1.6-2.7L13.7 3.9a1.8 1.8 0 0 0-3.4 0z" />
                </svg>
                <span>{AMBIENTE_INDISPONIVEL}</span>
              </p>
            ) : null}
            {/* Erro de sessão é outro assunto que o ambiente fora do ar: ele é a razão
                pela qual alguém que ESTAVA dentro voltou para a porta. Persistente, como
                a folha manda para erro. */}
            {sessionNotice ? (
              <p className="login-alert" role="alert">
                <span>{sessionNotice}</span>
              </p>
            ) : null}

            <button
              className="login-cta"
              type="button"
              disabled={!ambienteNoAr}
              onClick={() => void signIn()}
            >
              {CTA_ENTRAR}
              <svg
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2.4"
                strokeLinecap="round"
                strokeLinejoin="round"
                aria-hidden="true"
              >
                <path d="M5 12h13M13 6l6 6-6 6" />
              </svg>
            </button>

            {/* Espaço do login federado. O divisor acompanha o botão porque separar uma
                opção de nenhuma outra seria um traço sem função: o slot é o par, e ele só
                existe quando existe provedor. */}
            {identityProvidersConfigured() ? (
              <div className="login-federated">
                <div className="login-divider" aria-hidden="true" />
                {/* F-008: os botões dos provedores do realm entram aqui. */}
              </div>
            ) : null}

            <hr className="login-rule" />
            {isHomologationHost(currentHostname()) ? (
              <p className="login-env">
                <span className="login-env-pill">HOMOLOGAÇÃO</span>
              </p>
            ) : null}
            <p className="login-invite">{CONVITE}</p>
          </div>
        </div>
      </main>
    );
  }

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
          <span className="schema-pill">
            Cena {sceneSchema.$id?.split("/").at(-1)}
          </span>
          <span className="identity-pill">
            Sessão: {session.profile.preferred_username ?? session.profile.sub}
          </span>
          {/* Entrar saiu da topbar: o ato de entrar é o objeto de maior peso da porta, e
              não um botão discreto ao lado da pílula de schema (ADR-0032, D3). Aqui só
              resta sair. */}
          <button
            className="button button-quiet"
            type="button"
            onClick={() => void signOut()}
          >
            Sair
          </button>
        </div>
      </header>

      {/* O aviso de OIDC ausente era um `<p>` solto acima da casca vazia; ele virou estado
          da porta de entrada, que é onde "o ambiente caiu" precisa ser lido. Com sessão em
          mão, OIDC está configurado por construção. */}
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
