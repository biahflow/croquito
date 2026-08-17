import { renderToStaticMarkup } from "react-dom/server";
import type { User } from "oidc-client-ts";
import { describe, expect, it } from "vitest";
import { CroquiApp } from "./CroquiApp";

/**
 * Sessão sintética: a jornada recebe a sessão pronta da casca, e a renderização estática
 * não dispara efeito nenhum — nada é pedido à API por este teste.
 */
const session = {
  access_token: "sessao-sintetica-de-teste",
  profile: { sub: "revisor-de-teste" },
} as unknown as User;

describe("CroquiApp", () => {
  it("abre a área do tenant sem fabricar revisão, cena ou evidência", () => {
    const html = renderToStaticMarkup(
      <CroquiApp session={session} onSessionLost={() => undefined} />,
    );

    expect(html).toContain("Projetos e revisões");
    expect(html).not.toContain("DXF bloqueado");
    expect(html).not.toContain("Campo do Guaxindiba");
    expect(html).not.toContain("Simulação de decisão");
  });

  /**
   * A sessão tem um dono só (`readSession` consome um authorization code de uso único),
   * e é a casca. Esta jornada não desenha topbar, identidade nem Entrar/Sair.
   */
  it("não desenha a casca: sessão e navegação são da App", () => {
    const html = renderToStaticMarkup(
      <CroquiApp session={session} onSessionLost={() => undefined} />,
    );

    expect(html).not.toContain('class="topbar"');
    expect(html).not.toContain("Sessão:");
    expect(html).not.toContain(">Entrar<");
    expect(html).not.toContain(">Sair<");
    expect(html).not.toContain("revisor-de-teste");
    // O token nunca chega ao HTML.
    expect(html).not.toContain("sessao-sintetica-de-teste");
  });
});
