import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import type { User } from "oidc-client-ts";
import type { OverlayResponse } from "./api";
import {
  BannerRodadaMudou,
  MedicaoApp,
  OverlayDoTakeoff,
} from "./MedicaoApp";
import { AVISO_DOSSIE_GERADO, AVISO_DOSSIE_PREVIA } from "./labels";

/**
 * Render estático do primeiro estado: sem sessão, a jornada não chama a API e não inventa
 * rodada. `renderToStaticMarkup` não roda efeitos, então isto é exatamente o que a
 * orçamentista vê antes de qualquer resposta.
 *
 * `session={null}` é o estado honesto de quem ainda não entrou: toda rota da medição é
 * autenticada e por tenant (ADR-0028), e quem tem a tela de entrar é a casca.
 */
describe("MedicaoApp sem sessão", () => {
  it("pede a sessão e não exibe rodada, obra ou número de medição", () => {
    const html = renderToStaticMarkup(<MedicaoApp session={null} />);

    expect(html).toContain("Entre para abrir uma rodada");
    expect(html).toContain("autenticada e por tenant");
    expect(html).toContain("medição sem aprovação");
    // Nenhuma obra, código de catálogo, quantidade ou total fabricado.
    expect(html).not.toContain("Total da medição");
    expect(html).not.toContain("R$");
    expect(html).not.toContain("Praça");
    expect(html).not.toContain("Campo do Toca");
    expect(html).not.toContain("AD04");
  });

  it("não sobrou nenhuma promessa do servidor local de homologação", () => {
    const html = renderToStaticMarkup(<MedicaoApp session={null} />);

    expect(html).not.toContain("croquito-valuation serve");
    expect(html).not.toContain("localhost:8801");
    expect(html).not.toContain("Ferramenta local");
    expect(html).not.toContain("diretório da rodada");
  });

  /**
   * A seção do dossiê do aditivo vive dentro da etapa "códigos", que só renderiza depois
   * da resposta do servidor. Sem sessão, nem o botão de gerar o dossiê nem os dois avisos
   * (prévia/gerado) podem aparecer — nenhum dossiê é fabricado.
   */
  it("não mostra o dossiê do aditivo nem seus avisos antes de ler a rodada", () => {
    const html = renderToStaticMarkup(<MedicaoApp session={null} />);

    expect(html).not.toContain("Gerar dossiê do aditivo");
    expect(html).not.toContain("Regerar dossiê do aditivo");
    expect(html).not.toContain(AVISO_DOSSIE_PREVIA);
    expect(html).not.toContain(AVISO_DOSSIE_GERADO);
  });
});

/**
 * Com sessão e sem rodada aberta (`?rodada=`), a jornada começa por escolher — ou abrir —
 * uma rodada. `renderToStaticMarkup` não roda efeitos, então a lista ainda não foi lida: o
 * que aparece é a declaração disso, nunca uma rodada fabricada.
 */
describe("MedicaoApp com sessão e sem rodada aberta", () => {
  const sessao = {
    access_token: "token-de-teste",
    profile: { sub: "orcamentista-de-teste" },
  } as unknown as User;

  it("oferece escolher uma rodada existente ou abrir uma nova", () => {
    const html = renderToStaticMarkup(
      <MedicaoApp session={sessao} roundId="" />,
    );

    expect(html).toContain("Rodadas de medição");
    expect(html).toContain("Abrir rodada nova");
    expect(html).toContain("Catálogo de preços (JSON)");
    expect(html).toContain("A lista de rodadas ainda não foi lida.");
  });

  it("declara que o catálogo é imutável na rodada e pede a chave no padrão do domínio", () => {
    const html = renderToStaticMarkup(
      <MedicaoApp session={sessao} roundId="" />,
    );

    expect(html).toContain("imutável na rodada");
    expect(html).toContain("minúsculas, números e hífen");
  });

  it("não fabrica rodada, obra nem total antes de ler a API", () => {
    const html = renderToStaticMarkup(
      <MedicaoApp session={sessao} roundId="" />,
    );

    expect(html).not.toContain("Total da medição");
    expect(html).not.toContain("R$");
    expect(html).not.toContain("Campo do Toca");
    expect(html).not.toContain("AD04");
  });
});

function overlayResponse(overrides: Partial<OverlayResponse> = {}): OverlayResponse {
  return {
    round_id: "0197f2a0-0000-7000-8000-000000000001",
    version: 12,
    image_url: "https://armazenamento.example/overlay?assinatura=x",
    image_sha256: "b".repeat(64),
    packet_sha256: "c".repeat(64),
    overlay_packet_sha256: "c".repeat(64),
    present: true,
    stale: false,
    ...overrides,
  };
}

/**
 * O overlay é redesenhado por comando de fila (ADR-0030): entre a decisão e o desenho novo
 * ele é do pacote anterior. A tela mostra o desenho E a marca — em palavra, porque um
 * desenho vencido engana com a autoridade de um desenho.
 */
describe("OverlayDoTakeoff", () => {
  it("overlay do pacote corrente é exibido como atual", () => {
    const html = renderToStaticMarkup(
      <OverlayDoTakeoff overlay={overlayResponse()} />,
    );

    expect(html).toContain("desenho do pacote atual");
    expect(html).not.toContain("desenho do pacote anterior");
    expect(html).not.toContain("overlay-vencido");
  });

  it("overlay vencido é mostrado como vencido, com os dois digests e sem depender de cor", () => {
    const html = renderToStaticMarkup(
      <OverlayDoTakeoff
        overlay={overlayResponse({
          stale: true,
          overlay_packet_sha256: "d".repeat(64),
        })}
      />,
    );

    // A marca é TEXTO: ela sobrevive a qualquer folha de estilo.
    expect(html).toContain("desenho do pacote anterior");
    expect(html).toContain("Desenho vencido");
    expect(html).toContain("dddddddddddd");
    expect(html).toContain("cccccccccccc");
    expect(html).not.toContain("desenho do pacote atual");
    // A classe de estado existe, mas é redundância — nunca o único indicador.
    expect(html).toContain("overlay-vencido");
    // O desenho anterior continua na tela: ele é a única visão de onde cada número foi
    // lido, e escondê-lo seria pior do que declará-lo vencido.
    expect(html).toContain("assinatura=x");
  });

  it("sem desenho publicado não afirma que o overlay está atual", () => {
    const html = renderToStaticMarkup(
      <OverlayDoTakeoff overlay={overlayResponse({ present: false, stale: true })} />,
    );

    expect(html).toContain("sem desenho publicado");
    expect(html).not.toContain("<img");
  });
});

/**
 * O `409 REVISION_CONFLICT` não é erro do ato: a rodada andou, nada foi gravado e o
 * caminho é recarregar — com o formulário preservado.
 */
describe("BannerRodadaMudou", () => {
  it("diz que a rodada mudou, que nada foi gravado e oferece recarregar", () => {
    const html = renderToStaticMarkup(<BannerRodadaMudou onReload={() => {}} />);

    expect(html).toContain("A rodada mudou");
    expect(html).toContain("Nada foi gravado");
    expect(html).toContain("continua aqui");
    expect(html).toContain("Recarregar estado atual");
    expect(html).toContain('role="alert"');
    // Nada do vocabulário do servidor de arquivos: a guarda é de VERSÃO da rodada.
    expect(html).not.toContain("digest");
    expect(html).not.toContain("arquivos");
  });
});
