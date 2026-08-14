import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { App } from "./App";

describe("App", () => {
  it("não expõe a revisão sem uma sessão OIDC autenticada", () => {
    const html = renderToStaticMarkup(<App />);

    expect(html).toContain("Acesse uma revisão autenticada");
    expect(html).not.toContain("DXF bloqueado");
    expect(html).toContain("OIDC não está configurado");
    expect(html).not.toContain("UUID do job");
    expect(html).not.toContain("processamento global controlado");
    expect(html).not.toContain("Campo do Guaxindiba");
    expect(html).not.toContain("Simulação de decisão");
  });

  /**
   * O `base` do Vite é o de produção fora do `vite dev` (aqui, `/revisao/`), que é
   * exatamente a condição em que as duas telas dividem a origem — e é dele que sai o
   * `redirect_uri` do login, autorizado no realm como `/revisao/*`. Em desenvolvimento
   * (`base` = `/`) cada app tem a sua porta e o link não é renderizado.
   */
  it("liga a medição quando as duas telas dividem a origem", () => {
    expect(import.meta.env.BASE_URL).toBe("/revisao/");

    const html = renderToStaticMarkup(<App />);

    expect(html).toContain('href="/medicao/"');
    expect(html).toContain('href="/revisao/"');
  });
});
