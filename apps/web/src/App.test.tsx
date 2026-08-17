import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { App, MedicaoJourney } from "./App";

describe("App", () => {
  it("não expõe nenhuma jornada sem uma sessão OIDC autenticada", () => {
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
    // Nada da medição.
    expect(html).not.toContain("MEDIÇÃO DE OBRA");
  });

  it("não oferece alternância de jornada sem sessão", () => {
    const html = renderToStaticMarkup(<App />);

    expect(html).not.toContain('aria-label="Jornadas"');
    expect(html).not.toContain(">Croqui<");
    expect(html).not.toContain(">Medição<");
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

describe("MedicaoJourney", () => {
  it("declara que a jornada ainda não está nesta build, sem simular rodada", () => {
    const html = renderToStaticMarkup(<MedicaoJourney />);

    expect(html).toContain("ainda não está nesta build");
    expect(html).toContain("Nenhuma rodada é lida ou exibida");
    // Nenhum dado de obra: nem dinheiro, nem quantidade, nem código de catálogo. O
    // texto visível não tem sequer um dígito — a tela só declara o estado.
    const text = html.replace(/<[^>]+>/g, "");
    expect(text).not.toContain("R$");
    expect(text).not.toMatch(/\d/);
  });
});
