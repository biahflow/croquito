import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { App, JourneySwitch } from "./App";
import { PLATFORM_OPERATOR_ROLE } from "./plataforma/api";
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
   * a casca anuncia versão de schema e alterna jornadas que a próxima chamada recusaria com
   * 401. Cada asserção abaixo nomeia uma peça citada na decisão.
   */
  it("sem sessão, nenhuma peça da casca das jornadas é renderizada", () => {
    const html = renderToStaticMarkup(<App />);

    expect(html).not.toContain("app-shell");
    expect(html).not.toContain("topbar");
    expect(html).not.toContain("schema-pill");
    expect(html).not.toContain("identity-pill");
    expect(html).not.toContain('aria-label="Jornadas"');
    expect(html).not.toContain(">Medição<");
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
 * A jornada de plataforma é oferecida por PAPEL, e o papel vem da API (`GET /v1/me`) —
 * a SPA não decodifica token. A regra é conferida no seletor, que é onde ela vive: a
 * casca inteira só renderiza com sessão, e a condição não depende de sessão nenhuma.
 */
describe("seletor de jornadas", () => {
  const CROQUI: Route = { kind: "croqui", jobId: "" };

  it("com o papel de operador, a Plataforma aparece no seletor", () => {
    const html = renderToStaticMarkup(
      <JourneySwitch
        route={CROQUI}
        roles={["revisor", PLATFORM_OPERATOR_ROLE]}
        onOpen={() => {}}
      />,
    );

    expect(html).toContain(">Plataforma<");
    expect(html).toContain(">Croqui<");
    expect(html).toContain(">Medição<");
  });

  /**
   * Ausente, não desabilitado: um botão apagado anunciaria a existência de uma área que
   * aquela conta não administra. Sem papel, o elemento não existe no DOM.
   */
  it("sem o papel, o botão não existe — nem desabilitado", () => {
    const html = renderToStaticMarkup(
      <JourneySwitch route={CROQUI} roles={["revisor"]} onOpen={() => {}} />,
    );

    expect(html).not.toContain("Plataforma");
    expect(html).not.toContain("disabled");
    // As duas jornadas de sempre continuam lá.
    expect(html).toContain(">Croqui<");
    expect(html).toContain(">Medição<");
  });

  /**
   * Falha em `/v1/me` deixa os papéis vazios (fail-closed): a jornada some do seletor e
   * nenhum erro é jogado na cara de quem entrou para revisar um croqui.
   */
  it("sem resposta de papéis, o seletor é o de antes desta feature", () => {
    const html = renderToStaticMarkup(
      <JourneySwitch route={CROQUI} roles={[]} onOpen={() => {}} />,
    );

    expect(html).not.toContain("Plataforma");
  });

  it("a jornada aberta é declarada em aria-current, não só pintada", () => {
    const html = renderToStaticMarkup(
      <JourneySwitch
        route={{ kind: "plataforma" }}
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
