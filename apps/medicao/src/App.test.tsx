import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { App } from "./App";
import { AVISO_DOSSIE_GERADO, AVISO_DOSSIE_PREVIA } from "./labels";

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
    expect(html).toContain("croquito-valuation serve");
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

  it("sem OIDC configurado não pede login: o caminho do servidor local não muda", () => {
    const html = renderToStaticMarkup(<App />);

    expect(html).not.toContain("Sessão da orçamentista");
    expect(html).not.toContain("Verificando a sessão");
    expect(html).not.toContain(">Entrar<");
  });

  /**
   * O aviso permanente descreve a realidade da sessão: sem OIDC, a ferramenta é local e a
   * prancha vem da URL direta do servidor — nenhum object URL é criado, porque nenhuma
   * busca autenticada acontece.
   */
  it("sem OIDC o aviso continua sendo o da ferramenta local, sem object URL", () => {
    const html = renderToStaticMarkup(<App />);

    expect(html).not.toContain("Homologação remota autenticada");
    expect(html).not.toContain("blob:");
  });

  /**
   * O `base` do Vite é o de produção fora do `vite dev` (aqui, `/medicao/`), que é
   * exatamente a condição em que as duas telas dividem a origem. Em desenvolvimento
   * (`base` = `/`) cada app tem a sua porta e o link não é renderizado.
   */
  it("oferece a ida para a revisão quando as duas telas dividem a origem", () => {
    expect(import.meta.env.BASE_URL).toBe("/medicao/");

    const html = renderToStaticMarkup(<App />);

    expect(html).toContain('href="/revisao/"');
  });

  /**
   * A seção do dossiê do aditivo vive dentro da etapa "códigos", que só renderiza depois
   * de `takeoff !== null` (resposta do servidor). Sem servidor, nem o botão de gerar o
   * dossiê nem os dois avisos (prévia/gerado) podem aparecer — nenhum dossiê é fabricado.
   */
  it("não mostra o dossiê do aditivo nem seus avisos antes de ler o estado da rodada", () => {
    const html = renderToStaticMarkup(<App />);

    expect(html).not.toContain("Gerar dossiê do aditivo");
    expect(html).not.toContain("Regerar dossiê do aditivo");
    expect(html).not.toContain(AVISO_DOSSIE_PREVIA);
    expect(html).not.toContain(AVISO_DOSSIE_GERADO);
  });
});
