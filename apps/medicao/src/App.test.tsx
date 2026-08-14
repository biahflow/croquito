import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { App } from "./App";

/**
 * Render estático do primeiro estado: sem servidor local, a tela não inventa rodada.
 * `renderToStaticMarkup` não roda efeitos, então isto é exatamente o que a orçamentista
 * vê antes de qualquer resposta do `GET /state`.
 */
describe("App", () => {
  it("declara a natureza local da ferramenta e oferece recarregar, sem dado de obra", () => {
    const html = renderToStaticMarkup(<App />);

    expect(html).toContain(
      "Ferramenta local de homologação — medição sem aprovação; aprovar e exportar são atos separados.",
    );
    expect(html).toContain("Recarregar estado atual");
    expect(html).toContain("Rodada não carregada");
    expect(html).toContain("croquitodxf-valuation serve");
  });

  it("não mostra etapa alcançável nem número de medição antes de ler o estado", () => {
    const html = renderToStaticMarkup(<App />);

    expect(html).toContain("Etapa bloqueada");
    expect(html).not.toContain("em aberto");
    expect(html).not.toContain("concluída");
    expect(html).not.toContain("Total da medição");
    expect(html).not.toContain("R$");
    // Sem shortlist carregada não existe artefato a sobrescrever: o botão que regrava
    // `code-suggestions.json` não pode aparecer antes de haver o que recalcular.
    expect(html).not.toContain("Recalcular shortlist");
    // Nenhuma obra, código de catálogo ou quantidade fabricada aparece sem servidor.
    expect(html).not.toContain("Praça");
    expect(html).not.toContain("Campo do Toca");
    expect(html).not.toContain("AD04");
  });
});
