import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import type { User } from "oidc-client-ts";
import type { ApprovalState, OverlayResponse } from "./api";
import {
  AtoDeAprovacao,
  BannerRodadaMudou,
  MedicaoApp,
  OverlayDoTakeoff,
  PainelSemAcesso,
  ProgressoExportacao,
  RegistroDaAprovacao,
  TelaAuditoriaReprovada,
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

const APROVACAO_PENDENTE: ApprovalState = {
  approved: false,
  approved_by: null,
  approved_at: null,
  approved_digest: null,
  current_digest: "4f2a".padEnd(64, "0"),
  stale: false,
};

const APROVACAO_REGISTRADA: ApprovalState = {
  approved: true,
  approved_by: "orcamentista-de-teste",
  approved_at: "2026-08-20T14:32:00+00:00",
  approved_digest: "4f2a".padEnd(64, "0"),
  current_digest: "4f2a".padEnd(64, "0"),
  stale: false,
};

/** Houve ato humano E a medição mudou depois dele: os dois campos valem ao mesmo tempo. */
const APROVACAO_CADUCA: ApprovalState = {
  ...APROVACAO_REGISTRADA,
  current_digest: "a9c1".padEnd(64, "0"),
  stale: true,
};

function ato(overrides: { confirmando?: boolean; gravando?: boolean } = {}): string {
  return renderToStaticMarkup(
    <AtoDeAprovacao
      titulo="Aprovar a medição 3 de PRACA SINTETICA OESTE"
      identidade="orcamentista-de-teste"
      papel="orcamentista"
      contentDigest={APROVACAO_PENDENTE.current_digest}
      confirmando={overrides.confirmando ?? false}
      gravando={overrides.gravando ?? false}
      onAprovar={() => {}}
      onConfirmar={() => {}}
      onCancelar={() => {}}
    />,
  );
}

/**
 * O ato nominal em DOIS atos explícitos (decisão humana de 2026-08-20). O que este bloco
 * de teste protege é o desenho aprovado: a consequência antes do botão, a identidade
 * mostrada e nunca digitável, e um segundo passo que REPETE a consequência em vez de
 * perguntar "tem certeza?".
 */
describe("AtoDeAprovacao", () => {
  it("no repouso, diz a consequência por extenso ANTES do botão", () => {
    const html = ato();

    expect(html).toContain("Ato nominal · VAL-05");
    expect(html).toContain("Antes de aprovar, o que aprovar faz:");
    expect(html).toContain("Publica o seu nome.");
    expect(html).toContain("Libera a exportação.");
    expect(html).toContain("Vale só para esta medição");
    // A consequência vem antes do botão no próprio documento, não só na intenção.
    expect(html.indexOf("Publica o seu nome.")).toBeLessThan(
      html.indexOf("Aprovar esta medição"),
    );
    // O primeiro clique ainda não aprova: o segundo ato só aparece depois dele.
    expect(html).not.toContain("Confirmar aprovação nominal");
  });

  /**
   * Não existe campo de nome do aprovador nesta tela: o servidor lê a identidade do token
   * e recusa qualquer nome que venha do cliente. Um campo aqui prometeria um efeito que
   * ele não tem.
   */
  it("mostra a identidade da sessão e não oferece nenhum campo digitável", () => {
    const html = ato();

    expect(html).toContain("Você aprova como");
    expect(html).toContain("orcamentista-de-teste");
    expect(html).toContain("Papel orcamentista");
    expect(html).not.toContain("<input");
    expect(html).not.toContain("<textarea");
  });

  it("o segundo ato repete a consequência e é o único que confirma", () => {
    const html = ato({ confirmando: true });

    expect(html).toContain("Confirmar a aprovação nominal?");
    expect(html).toContain("fica registrado como quem aprovou");
    expect(html).toContain("a exportação do boletim fica liberada");
    expect(html).toContain("Confirmar aprovação nominal");
    expect(html).toContain("Cancelar");
    // O primeiro botão sai de cena: um clique só nunca aprova.
    expect(html).not.toContain("Aprovar esta medição");
    expect(html).not.toContain("tem certeza");
  });

  it("enquanto grava, os dois botões ficam indisponíveis", () => {
    const html = ato({ confirmando: true, gravando: true });

    expect(html).toContain("Aprovando…");
    expect(html.match(/disabled/g)).toHaveLength(2);
    expect(html).toContain("chave de idempotência");
  });
});

/**
 * O registro é o que a jornada mostra depois do ato: quem, quando e sobre qual conteúdo. O
 * digest é o vínculo que faz a aprovação caducar sozinha — e a aprovação caduca é o estado
 * em que `approved` e `stale` valem ao mesmo tempo.
 */
describe("RegistroDaAprovacao", () => {
  it("medição nunca aprovada não inventa registro nenhum", () => {
    const html = renderToStaticMarkup(
      <RegistroDaAprovacao approval={APROVACAO_PENDENTE} papel="orcamentista" />,
    );

    expect(html).toBe("");
  });

  it("aprovada mostra quem, quando e o conteúdo assinado", () => {
    const html = renderToStaticMarkup(
      <RegistroDaAprovacao approval={APROVACAO_REGISTRADA} papel="orcamentista" />,
    );

    expect(html).toContain("Aprovada");
    expect(html).toContain("orcamentista-de-teste");
    expect(html).toContain("20/08/2026");
    expect(html).toContain("igual ao da medição atual");
    expect(html).not.toContain("registro-caduca");
    expect(html).not.toContain("APPROVAL_CONTENT_MISMATCH");
  });

  it("caduca mostra a palavra, os dois digests e o código — e nenhuma saída por fora", () => {
    const html = renderToStaticMarkup(
      <RegistroDaAprovacao approval={APROVACAO_CADUCA} papel="orcamentista" />,
    );

    // A marca do estado é a PALAVRA; o tracejado é redundância dela.
    expect(html).toContain("Aprovação caduca");
    expect(html).toContain("registro-caduca");
    expect(html).toContain("Conteúdo aprovado");
    expect(html).toContain("Conteúdo atual");
    expect(html).toContain("4f2a00000000");
    expect(html).toContain("a9c100000000");
    expect(html).toContain("APPROVAL_CONTENT_MISMATCH");
    // O registro velho não é apagado — foi um ato humano que aconteceu.
    expect(html).toContain("orcamentista-de-teste");
    expect(html).not.toContain("mesmo assim");
    expect(html).not.toContain("igual ao da medição atual");
  });
});

/**
 * Quatro passos escritos, nunca uma barra: três deles acontecem antes de existir arquivo
 * publicado, e barra sugeriria que o arquivo já está quase pronto.
 */
describe("ProgressoExportacao", () => {
  it("em voo, declara que nada foi publicado e não finge saber o passo", () => {
    const html = renderToStaticMarkup(<ProgressoExportacao estado="em-voo" />);

    expect(html).toContain("Montar a planilha no modelo da prefeitura");
    expect(html).toContain("Reabrir e reconferir célula a célula");
    expect(html).toContain("Publicar");
    expect(html).toContain("Nada foi publicado até a resposta chegar");
    expect(html).not.toContain("feito");
  });

  it("reprovado diz onde parou: gravou, reconferiu e não publicou", () => {
    const html = renderToStaticMarkup(<ProgressoExportacao estado="reprovado" />);

    expect(html).toContain("reprovado");
    expect(html).toContain("não iniciado");
  });
});

/**
 * Auditoria reprovada é TELA, não rodapé: nada foi publicado, e dizê-lo por extenso é o
 * que separa "falhou" de "publicou algo que ninguém conferiu".
 */
describe("TelaAuditoriaReprovada", () => {
  it("diz que nada foi publicado, lista os códigos e traduz cada um", () => {
    const html = renderToStaticMarkup(
      <TelaAuditoriaReprovada findings={["CELL_VALUE_MISMATCH"]} onDismiss={() => {}} />,
    );

    expect(html).toContain("nada foi publicado");
    expect(html).toContain("CELL_VALUE_MISMATCH");
    expect(html).toContain("um centavo de diferença basta para não publicar");
    expect(html).toContain('role="alert"');
    // O valor esperado e o encontrado não voltam do servidor: eles são dinheiro do cliente.
    expect(html).toContain("não voltam do servidor");
    expect(html).not.toContain("R$");
  });

  it("sem achado declarado, não fabrica tabela nenhuma", () => {
    const html = renderToStaticMarkup(<TelaAuditoriaReprovada findings={[]} />);

    expect(html).toContain("nada foi publicado");
    expect(html).not.toContain("<table");
  });
});

/** O `403` é tela, e a mensagem não nomeia papel — a decisão de copy não foi tomada. */
describe("PainelSemAcesso", () => {
  it("explica a falta de autorização sem nomear papel nenhum", () => {
    const html = renderToStaticMarkup(<PainelSemAcesso />);

    expect(html).toContain("Sem acesso a esta rodada");
    expect(html).toContain("não tem autorização");
    expect(html).toContain('role="alert"');
    expect(html).not.toContain("orcamentista");
    expect(html).not.toContain("orçamentista");
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
