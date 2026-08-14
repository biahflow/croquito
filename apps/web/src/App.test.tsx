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
});
