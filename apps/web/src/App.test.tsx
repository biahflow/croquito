import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { App } from "./App";
import { entryRedirect, LOGIN_PATH } from "./route";

/**
 * As duas jornadas têm o mesmo regime: sessão OIDC ou nada. A medição já teve um caminho
 * sem sessão (o servidor local do ADR-0020, em outra origem); ele saiu com a migração para
 * a API `/v1` (ADR-0028), e toda rota de medição é autenticada e por tenant.
 *
 * O render estático cai sempre na rota do croqui (sem `window`, `currentRoute()` devolve a
 * raiz) e neste ambiente não há `VITE_OIDC_*` — é, portanto, o regime sem sessão, no qual
 * NENHUMA das duas jornadas é alcançável.
 */
describe("App", () => {
  it("na rota do croqui sem sessão, nenhuma jornada é exposta", () => {
    const html = renderToStaticMarkup(<App />);

    expect(html).toContain("Entre para continuar");
    expect(html).toContain("OIDC não está configurado");
    // Nada do croqui.
    expect(html).not.toContain("DXF bloqueado");
    expect(html).not.toContain("UUID do job");
    expect(html).not.toContain("processamento global controlado");
    expect(html).not.toContain("Campo do Guaxindiba");
    expect(html).not.toContain("Simulação de decisão");
    expect(html).not.toContain("Projetos e revisões");
    // Nada da medição: os dois cabeçalhos possíveis da jornada começam por aqui.
    expect(html).not.toContain("HOMOLOGAÇÃO");
  });

  /**
   * O seletor abre jornada, e sem sessão não existe jornada a abrir — inclusive a da
   * medição, que deixou de ter caminho sem sessão quando o servidor local saiu. Oferecer a
   * alternância aqui prometeria uma tela que a próxima chamada recusaria com 401.
   */
  it("sem sessão, não oferece a alternância de jornada", () => {
    const html = renderToStaticMarkup(<App />);

    expect(html).not.toContain('aria-label="Jornadas"');
    expect(html).not.toContain(">Medição<");
    expect(html).toContain("Entre para continuar");
  });

  /**
   * Substitui o teste que afirmava o link entre as duas origens: com as jornadas dentro
   * do mesmo build (ADR-0028, D9) não existe segunda origem para linkar, e a marca
   * continua apontando para a base desta SPA — que é também o `redirect_uri` do login.
   */
  it("não linka uma segunda origem: a medição é jornada, não outro app", () => {
    expect(import.meta.env.BASE_URL).toBe("/revisao/");

    const html = renderToStaticMarkup(<App />);

    expect(html).not.toContain('href="/medicao/"');
    expect(html).toContain('href="/revisao/"');
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
