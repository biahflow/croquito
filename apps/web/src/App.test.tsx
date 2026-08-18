import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { App } from "./App";

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
   * O seletor abre jornada, e sem sessão não existe jornada a abrir — inclusive a da
   * medição, que deixou de ter caminho sem sessão quando o servidor local saiu. Oferecer a
   * alternância aqui prometeria uma tela que a próxima chamada recusaria com 401.
   */
  it("sem sessão, não oferece a alternância de jornada", () => {
    const html = renderToStaticMarkup(<App />);

    expect(html).not.toContain('aria-label="Jornadas"');
    expect(html).not.toContain(">Medição<");
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
