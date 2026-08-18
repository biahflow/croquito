import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { App, journeyIsOpen } from "./App";

/**
 * A assimetria entre as duas jornadas é regra de produto, não detalhe de render: croqui
 * sempre exige sessão; medição exige sessão só onde há OIDC configurado, porque sem ele o
 * caminho é o servidor local do ADR-0020, que a F-003 declara fora de escopo remover.
 *
 * Ela é testada aqui, e não pelo HTML, porque `isOidcConfigured()` é lido do ambiente do
 * build: o render estático só alcança um dos dois regimes.
 */
describe("journeyIsOpen", () => {
  it("com sessão, as duas jornadas abrem", () => {
    expect(journeyIsOpen("croqui", true, true)).toBe(true);
    expect(journeyIsOpen("medicao", true, true)).toBe(true);
    expect(journeyIsOpen("croqui", true, false)).toBe(true);
    expect(journeyIsOpen("medicao", true, false)).toBe(true);
  });

  it("com OIDC configurado e sem sessão, nenhuma jornada abre", () => {
    expect(journeyIsOpen("croqui", false, true)).toBe(false);
    expect(journeyIsOpen("medicao", false, true)).toBe(false);
  });

  it("sem OIDC configurado, a medição abre e o croqui continua pedindo sessão", () => {
    expect(journeyIsOpen("medicao", false, false)).toBe(true);
    expect(journeyIsOpen("croqui", false, false)).toBe(false);
  });
});

/**
 * O render estático cai sempre na rota do croqui (sem `window`, `currentRoute()` devolve
 * a raiz) e neste ambiente não há `VITE_OIDC_*`. É, portanto, o lado exigente da
 * assimetria: croqui sem sessão, que continua fechado.
 */
describe("App", () => {
  it("na rota do croqui sem sessão, nenhuma jornada é exposta", () => {
    const html = renderToStaticMarkup(<App />);

    expect(html).toContain("Acesse uma revisão autenticada");
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
   * O seletor segue `journeyIsOpen`, não a sessão sozinha: sem OIDC configurado a medição
   * é alcançável (ADR-0020), e sem o seletor a orçamentista teria de digitar `?rodada=` na
   * barra de endereço para chegar até ela. Com OIDC e sem sessão ele some — coberto pelo
   * `journeyIsOpen` acima, que é o único regime que este render não alcança.
   */
  it("oferece a alternância de jornada porque a medição local é alcançável", () => {
    const html = renderToStaticMarkup(<App />);

    expect(html).toContain('aria-label="Jornadas"');
    expect(html).toContain(">Croqui<");
    expect(html).toContain(">Medição<");
    // Alcançável não é aberta: a jornada do croqui continua atrás da tela anônima.
    expect(html).toContain("Acesse uma revisão autenticada");
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
