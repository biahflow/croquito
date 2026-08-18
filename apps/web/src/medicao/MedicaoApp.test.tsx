import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { MedicaoApp } from "./MedicaoApp";
import { AVISO_DOSSIE_GERADO, AVISO_DOSSIE_PREVIA } from "./labels";

/**
 * Render estático do primeiro estado: sem servidor local, a tela não inventa rodada.
 * `renderToStaticMarkup` não roda efeitos, então isto é exatamente o que a orçamentista
 * vê antes de qualquer resposta do `GET /state`.
 *
 * `session={null}` é o caminho local do ADR-0020 — a casca entrega a sessão, e neste
 * ambiente (sem `VITE_OIDC_*`) não há nenhuma para entregar.
 */
describe("MedicaoApp", () => {
  it("declara a natureza local da ferramenta e oferece recarregar, sem dado de obra", () => {
    const html = renderToStaticMarkup(<MedicaoApp session={null} />);

    expect(html).toContain(
      "Ferramenta local de homologação — medição sem aprovação; aprovar e exportar são atos separados.",
    );
    expect(html).toContain("Recarregar estado atual");
    expect(html).toContain("Rodada não carregada");
    expect(html).toContain("croquito-valuation serve");
  });

  it("não mostra etapa alcançável nem número de medição antes de ler o estado", () => {
    const html = renderToStaticMarkup(<MedicaoApp session={null} />);

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

  /**
   * A porta de login saiu daqui (é da casca) e a sessão virou prop. Sem sessão, a jornada
   * não exibe identidade nem oferece sair: é a tela local do ADR-0020, que nunca teve
   * essas coisas. O que ela NÃO pode fazer é inventá-las de volta.
   */
  it("sem sessão não mostra identidade nem sair: o caminho do servidor local não muda", () => {
    const html = renderToStaticMarkup(<MedicaoApp session={null} />);

    expect(html).not.toContain("Sessão:");
    expect(html).not.toContain(">Sair<");
    expect(html).not.toContain(">Entrar<");
  });

  /**
   * O aviso permanente descreve a realidade da sessão: sem OIDC, a ferramenta é local e a
   * prancha vem da URL direta do servidor — nenhum object URL é criado, porque nenhuma
   * busca autenticada acontece.
   */
  it("sem OIDC o aviso continua sendo o da ferramenta local, sem object URL", () => {
    const html = renderToStaticMarkup(<MedicaoApp session={null} />);

    expect(html).not.toContain("Homologação remota autenticada");
    expect(html).not.toContain("blob:");
  });

  /**
   * A seção do dossiê do aditivo vive dentro da etapa "códigos", que só renderiza depois
   * de `takeoff !== null` (resposta do servidor). Sem servidor, nem o botão de gerar o
   * dossiê nem os dois avisos (prévia/gerado) podem aparecer — nenhum dossiê é fabricado.
   */
  it("não mostra o dossiê do aditivo nem seus avisos antes de ler o estado da rodada", () => {
    const html = renderToStaticMarkup(<MedicaoApp session={null} />);

    expect(html).not.toContain("Gerar dossiê do aditivo");
    expect(html).not.toContain("Regerar dossiê do aditivo");
    expect(html).not.toContain(AVISO_DOSSIE_PREVIA);
    expect(html).not.toContain(AVISO_DOSSIE_GERADO);
  });
});
