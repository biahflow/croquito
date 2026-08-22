import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { App, JourneySwitch } from "./App";
import { PLATFORM_OPERATOR_ROLE, type Journey } from "./plataforma/api";
import { entryRedirect, LOGIN_PATH, type Route } from "./route";

/**
 * As duas jornadas têm o mesmo regime: sessão OIDC ou nada. A medição já teve um caminho
 * sem sessão (o servidor local do ADR-0020, em outra origem); ele saiu com a migração para
 * a API `/v1` (ADR-0028), e toda rota de medição é autenticada e por tenant.
 *
 * O render estático cai sempre na rota do croqui (sem `window`, `currentRoute()` devolve a
 * raiz) e neste ambiente não há `VITE_OIDC_*` — é, portanto, o regime sem sessão, no qual
 * NENHUMA das duas jornadas é alcançável, e no qual a porta de entrada mostra o estado de
 * ambiente indisponível.
 */
describe("App", () => {
  it("na rota do croqui sem sessão, nenhuma jornada é exposta", () => {
    const html = renderToStaticMarkup(<App />);

    // A porta, com o texto aprovado em 2026-08-18 — revisão 2, a copy inteira do mock
    // (registro em docs/features/F-007-tela-de-login/mock/README.md).
    expect(html).toContain("Do croqui ao orçamento.");
    expect(html).toContain("ACESSO RESTRITO");
    expect(html).toContain("Entrar no Croquito");
    expect(html).toContain("Sua senha é digitada no provedor de identidade, nunca aqui.");
    expect(html).toContain("Ainda não tem acesso?");
    expect(html).toContain(
      "O ambiente está indisponível agora. Tente de novo em instantes — se " +
        "persistir, avise a operação.",
    );
    // Nada do croqui.
    expect(html).not.toContain("DXF bloqueado");
    expect(html).not.toContain("UUID do job");
    expect(html).not.toContain("processamento global controlado");
    expect(html).not.toContain("Campo do Guaxindiba");
    expect(html).not.toContain("Simulação de decisão");
    expect(html).not.toContain("Projetos e revisões");
    // Nada da medição: os dois cabeçalhos possíveis da jornada começam por aqui. E a
    // pílula de ambiente não existe mais em lugar nenhum — decisão humana de 2026-08-19:
    // a URL diferencia o ambiente.
    expect(html).not.toContain("HOMOLOGAÇÃO");
  });

  /**
   * ADR-0032, D3: `/login` é o único lugar onde o produto se apresenta sem sessão, e
   * NENHUMA peça da casca das jornadas é renderizada antes de haver sessão. Não é estética:
   * a casca identifica a sessão e alterna jornadas que a próxima chamada recusaria com
   * 401. Cada asserção abaixo nomeia uma peça citada na decisão.
   */
  it("sem sessão, nenhuma peça da casca das jornadas é renderizada", () => {
    const html = renderToStaticMarkup(<App />);

    expect(html).not.toContain("app-shell");
    expect(html).not.toContain("topbar");
    expect(html).not.toContain("topbar-actions");
    expect(html).not.toContain("identity-pill");
    expect(html).not.toContain('aria-label="Jornadas"');
    expect(html).not.toContain(">Medição<");
    expect(html).not.toContain(">Orçamento<");
    // A promessa da porta cita a palavra "orçamento" e é texto aprovado: o que não pode
    // aparecer é o BOTÃO da jornada, conferido acima na forma exata do elemento.
    expect(html).toContain("Do croqui ao orçamento.");
  });

  /**
   * Critério 9 da F-007: sem identity provider configurado no realm, o botão do login
   * federado NÃO é renderizado — nem desabilitado, nem oculto por CSS. Nenhum dos dois
   * realms (`keycloak/croquito-realm.json`, `keycloak/croquito-hml-realm.json`) declara
   * `identityProviders`, então é ausência do DOM que se afirma aqui.
   */
  it("sem identity provider no realm, o botão do Google não existe no DOM", () => {
    const html = renderToStaticMarkup(<App />);

    expect(html).not.toContain("Entrar com Google");
    expect(html).not.toContain("login-button-federated");
    expect(html).not.toContain("login-federated");
    // O CTA próprio continua lá — o que falta é o provedor, não a porta.
    expect(html).toContain("login-cta");
  });
});

/**
 * Croqui, Medição e Orçamento são oferecidos pela lista `journeys` que `GET /v1/me`
 * resolveu (F-034, 2026-08-22) — a SPA não recalcula papel nem ambiente, só renderiza o
 * que chegou. A Plataforma segue por PAPEL, não pela lista: ela não é jornada. A regra é
 * conferida no seletor, que é onde ela vive: a casca inteira só renderiza com sessão, e
 * nenhuma das duas condições depende de sessão nenhuma.
 */
describe("seletor de jornadas", () => {
  const CROQUI: Route = { kind: "croqui", jobId: "" };
  const TODAS_JORNADAS: Journey[] = ["croqui", "medicao", "orcamento"];

  it("com as três jornadas na lista e o papel de operador, o seletor é o de sempre", () => {
    const html = renderToStaticMarkup(
      <JourneySwitch
        route={CROQUI}
        journeys={TODAS_JORNADAS}
        roles={["revisor", PLATFORM_OPERATOR_ROLE]}
        onOpen={() => {}}
      />,
    );

    expect(html).toContain(">Plataforma<");
    expect(html).toContain(">Croqui<");
    expect(html).toContain(">Medição<");
    expect(html).toContain(">Orçamento<");
    expect(html).not.toContain("app-alert");
  });

  /**
   * F-034 (2026-08-22) inverteu o que este teste media: Orçamento não é mais
   * incondicional (a leitura de "qual papel autoriza é decisão humana aberta" fechou), e
   * passa a depender exatamente da lista que o servidor devolveu — nunca de papel, que
   * segue sendo assunto só da Plataforma.
   */
  it("Orçamento aparece quando a lista o inclui, sem depender de papel nenhum", () => {
    const html = renderToStaticMarkup(
      <JourneySwitch
        route={CROQUI}
        journeys={["orcamento"]}
        roles={[]}
        onOpen={() => {}}
      />,
    );

    expect(html).toContain(">Orçamento<");
    expect(html).not.toContain("disabled");
  });

  /**
   * Ausente da lista, o botão não existe — nem desabilitado, o mesmo mecanismo que já
   * valia só para a Plataforma. Croqui e Medição continuam presentes: a ausência é por
   * jornada, não um efeito colateral das outras.
   */
  it("Orçamento ausente da lista não aparece, mesmo com Croqui e Medição presentes", () => {
    const html = renderToStaticMarkup(
      <JourneySwitch
        route={CROQUI}
        journeys={["croqui", "medicao"]}
        roles={[]}
        onOpen={() => {}}
      />,
    );

    expect(html).not.toContain(">Orçamento<");
    expect(html).not.toContain("disabled");
    expect(html).toContain(">Croqui<");
    expect(html).toContain(">Medição<");
  });

  /**
   * "Ainda não sei" e "sei que não há nenhuma" são estados diferentes. Enquanto `/v1/me`
   * não respondeu a lista é `null`, e o seletor não afirma nada: nem abas, nem aviso.
   * Tratar os dois como lista vazia faria TODA sessão — inclusive a de quem tem as três
   * jornadas — exibir "nenhuma jornada liberada" durante a ida e volta da chamada.
   */
  it("enquanto a lista não foi resolvida, o seletor não mostra abas nem aviso", () => {
    const html = renderToStaticMarkup(
      <JourneySwitch route={CROQUI} journeys={null} roles={[]} onOpen={() => {}} />,
    );

    expect(html).not.toContain("app-alert");
    expect(html).not.toContain(">Croqui<");
    expect(html).not.toContain(">Medição<");
    expect(html).not.toContain(">Orçamento<");
  });

  it("a jornada do orçamento aberta é declarada em aria-current", () => {
    const html = renderToStaticMarkup(
      <JourneySwitch
        route={{ kind: "orcamento", roundId: null }}
        journeys={["orcamento"]}
        roles={[]}
        onOpen={() => {}}
      />,
    );

    expect(html).toContain('aria-current="page">Orçamento<');
  });

  /**
   * Ausente, não desabilitado: um botão apagado anunciaria a existência de uma área que
   * aquela conta não administra. Sem papel, o elemento da Plataforma não existe no DOM;
   * Croqui e Medição continuam vindo da lista, não do papel.
   */
  it("sem o papel, o botão da Plataforma não existe — nem desabilitado", () => {
    const html = renderToStaticMarkup(
      <JourneySwitch
        route={CROQUI}
        journeys={["croqui", "medicao"]}
        roles={["revisor"]}
        onOpen={() => {}}
      />,
    );

    expect(html).not.toContain("Plataforma");
    expect(html).not.toContain("disabled");
    // As duas jornadas de sempre continuam lá.
    expect(html).toContain(">Croqui<");
    expect(html).toContain(">Medição<");
  });

  /**
   * Falha em `/v1/me` deixa papéis E jornadas vazios (fail-closed): nenhuma aba de
   * produto aparece, e o aviso escrito ocupa o lugar do seletor — texto, não silêncio,
   * porque a tela não pode mudar sem explicação.
   */
  it("lista vazia: nenhuma aba de jornada e o aviso escrito com role=alert", () => {
    const html = renderToStaticMarkup(
      <JourneySwitch route={CROQUI} journeys={[]} roles={[]} onOpen={() => {}} />,
    );

    expect(html).not.toContain(">Croqui<");
    expect(html).not.toContain(">Medição<");
    expect(html).not.toContain(">Orçamento<");
    expect(html).not.toContain("Plataforma");
    expect(html).toContain('role="alert"');
    expect(html).toContain("não tem nenhuma jornada liberada");
  });

  /**
   * Lista vazia não apaga a Plataforma: ela é governada por papel, não pela lista, e
   * continua sendo o lugar onde a disponibilidade das outras jornadas é administrada.
   */
  it("lista vazia com papel de operador: aviso e Plataforma convivem", () => {
    const html = renderToStaticMarkup(
      <JourneySwitch
        route={CROQUI}
        journeys={[]}
        roles={[PLATFORM_OPERATOR_ROLE]}
        onOpen={() => {}}
      />,
    );

    expect(html).toContain('role="alert"');
    expect(html).toContain(">Plataforma<");
  });

  it("a jornada aberta é declarada em aria-current, não só pintada", () => {
    const html = renderToStaticMarkup(
      <JourneySwitch
        route={{ kind: "plataforma" }}
        journeys={TODAS_JORNADAS}
        roles={[PLATFORM_OPERATOR_ROLE]}
        onOpen={() => {}}
      />,
    );

    expect(html).toContain('aria-current="page">Plataforma<');
  });
});

/**
 * A regra de porta de entrada do ADR-0032 (D3/D4) é decisão pura e mora em `route.ts`; a
 * casca só a aplica com `replaceState` depois de `readSession()`. Os testes ficam aqui,
 * junto do estado sem sessão que eles governam, e não em `route.test.ts`, que cobre a
 * jornada. Eles rodam sem DOM porque a decisão é pura — o ambiente de teste do workspace
 * é `node`, e o efeito no `history` é alcançado pelo smoke headless, o único teste que
 * atravessa o redirect de verdade.
 */
describe("rebote da porta de entrada", () => {
  const JOB = "0198f0a1-2b3c-7d4e-8f90-1a2b3c4d5e6f";
  const JORNADA = "/revisao/";

  /**
   * O risco nº 1 da feature: sem esta exceção, o retorno do OIDC — que chega ANTES de
   * existir sessão em memória — é rebatido para `/login` e o login nunca fecha. Remover a
   * exceção de `entryRedirect` faz este teste falhar; é o critério 5 do contrato.
   */
  it("nunca rebate o retorno do OIDC, mesmo sem sessão", () => {
    expect(
      entryRedirect(
        { pathname: JORNADA, search: "?code=abc123&state=xyz789" },
        false,
        JORNADA,
      ),
    ).toBeNull();
    // O caso que o smoke headless persegue: link `?job=` que atravessou o login.
    expect(
      entryRedirect(
        { pathname: JORNADA, search: `?job=${JOB}&code=abc123&state=xyz789` },
        false,
        JORNADA,
      ),
    ).toBeNull();
  });

  /**
   * A exceção é estreita de propósito: só a URL que tem os DOIS parâmetros é retorno do
   * OIDC. Um `?code=` solto num link qualquer não compra passagem para dentro.
   */
  it("não confunde parâmetro solto com retorno do OIDC", () => {
    expect(
      entryRedirect({ pathname: JORNADA, search: "?code=abc123" }, false, JORNADA),
    ).toBe(`${LOGIN_PATH}?code=abc123`);
    expect(
      entryRedirect({ pathname: JORNADA, search: "?state=xyz789" }, false, JORNADA),
    ).toBe(`${LOGIN_PATH}?state=xyz789`);
  });

  it("sem sessão, leva a jornada para /login preservando a query original", () => {
    expect(
      entryRedirect({ pathname: JORNADA, search: `?job=${JOB}` }, false, JORNADA),
    ).toBe(`${LOGIN_PATH}?job=${JOB}`);
    // A raiz da SPA e a medição caem na mesma regra; `?rodada=` vazio é jornada declarada
    // e precisa sobreviver ao salto tanto quanto o `?job`.
    expect(entryRedirect({ pathname: JORNADA, search: "" }, false, JORNADA)).toBe(
      LOGIN_PATH,
    );
    expect(
      entryRedirect({ pathname: JORNADA, search: "?rodada=" }, false, JORNADA),
    ).toBe(`${LOGIN_PATH}?rodada=`);
  });

  it("com sessão, tira /login da frente e devolve a jornada com a query", () => {
    expect(entryRedirect({ pathname: LOGIN_PATH, search: "" }, true, JORNADA)).toBe(
      JORNADA,
    );
    expect(
      entryRedirect({ pathname: LOGIN_PATH, search: `?job=${JOB}` }, true, JORNADA),
    ).toBe(`${JORNADA}?job=${JOB}`);
    // Em desenvolvimento a SPA é servida na raiz; o destino é `BASE_URL`, não `/revisao/`
    // escrito à mão.
    expect(entryRedirect({ pathname: LOGIN_PATH, search: "" }, true, "/")).toBe("/");
  });

  it("não rebate quem já está no lugar certo", () => {
    expect(
      entryRedirect({ pathname: LOGIN_PATH, search: `?job=${JOB}` }, false, JORNADA),
    ).toBeNull();
    expect(
      entryRedirect({ pathname: JORNADA, search: `?job=${JOB}` }, true, JORNADA),
    ).toBeNull();
    // `/login/` digitado com barra é o mesmo lugar, e rebatê-lo seria um loop.
    expect(
      entryRedirect({ pathname: `${LOGIN_PATH}/`, search: "" }, false, JORNADA),
    ).toBeNull();
  });
});
