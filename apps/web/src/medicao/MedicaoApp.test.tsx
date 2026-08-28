import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import type { User } from "oidc-client-ts";
import type {
  ApprovalState,
  BulletinResponse,
  IdentityLinkPreviewResponse,
  OverlayResponse,
  RoundSummary,
  TakeoffItem,
  ValuationOrigin,
  WorksiteResponse,
  WorksiteSheet,
} from "./api";
import {
  AcrescentarFolhas,
  AtoDeAprovacao,
  BannerRodadaMudou,
  AndamentoDaCodificacao,
  DeclararIdentidade,
  FaixaDeFolhas,
  FolhaSemPacote,
  HerancaDaRodadaAnterior,
  LerFolhasEmLote,
  MedicaoApp,
  OverlaySemRerender,
  PainelDaPraca,
  VINCULO_VAZIO,
  OrigemDoOrcamento,
  OverlayDoTakeoff,
  PainelSemAcesso,
  PreviaDaReRa,
  ProgressoExportacao,
  RegimeDeConferencia,
  RegistroDaAprovacao,
  ReRatificacaoDeclarada,
  ReRatificacaoFieldset,
  TelaAuditoriaReprovada,
} from "./MedicaoApp";
import type { LinhaDaPrevia, LinhaHerdada } from "./previa";
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


/**
 * A escolha da origem da rodada (F-036, ADR-0048).
 *
 * O que estes testes protegem é a distinção entre três estados que a tela não pode
 * confundir: "ainda não li", "não há" e "há, mas não serve ainda".
 */
describe("OrigemDoOrcamento", () => {
  const assinado: ValuationOrigin = {
    round_id: "0197f2a0-0000-7000-8000-0000000000c1",
    worksite_name: "PRACA SINTETICA OESTE",
    reference_label: "DEMANDA 2026/014",
    signature: "signed",
    approved_by: "aprovadora-sintetica",
    approved_at: "2026-08-22T12:00:00+00:00",
    estimate_digest: "9".repeat(64),
    code_count: 34,
    total_amount: "418902.17",
  };

  it("antes da primeira resposta não afirma nem lista nem ausência", () => {
    const html = renderToStaticMarkup(
      <OrigemDoOrcamento origens={null} escolhida={null} onEscolher={() => {}} />,
    );

    expect(html).toContain("Lendo os orçamentos assinados");
    expect(html).not.toContain("Nenhum orçamento assinado");
  });

  it("sem orçamento assinado, diz a ausência e nomeia a alternativa", () => {
    const html = renderToStaticMarkup(
      <OrigemDoOrcamento origens={[]} escolhida={null} onEscolher={() => {}} />,
    );

    expect(html).toContain("Nenhum orçamento assinado sob demanda contratada");
    expect(html).toContain("não confere contra contratado nenhum");
  });

  it("mostra quem assinou, quantos códigos e o total, com o digest abreviado", () => {
    const html = renderToStaticMarkup(
      <OrigemDoOrcamento
        origens={[assinado]}
        escolhida={null}
        onEscolher={() => {}}
      />,
    );

    expect(html).toContain("PRACA SINTETICA OESTE");
    expect(html).toContain("Assinado por aprovadora-sintetica");
    expect(html).toContain("34 códigos");
    expect(html).toContain("Assinado");
    expect(html).toContain("digest");
    // O digest aparece abreviado, nunca por extenso na linha.
    expect(html).not.toContain("9".repeat(64));
  });

  /**
   * Esconder faria a pessoa procurar um orçamento que ela sabe existir. Ele aparece, com o
   * motivo por extenso, e o rádio recusa a escolha.
   */
  it("assinatura caduca aparece com o motivo e não pode ser escolhida", () => {
    const html = renderToStaticMarkup(
      <OrigemDoOrcamento
        origens={[{ ...assinado, signature: "stale" }]}
        escolhida={null}
        onEscolher={() => {}}
      />,
    );

    expect(html).toContain("Assinatura caduca");
    expect(html).toContain("Assine a versão atual");
    expect(html).toContain("disabled");
  });

  it("orçamento sem assinatura aparece com o motivo próprio", () => {
    const html = renderToStaticMarkup(
      <OrigemDoOrcamento
        origens={[
          { ...assinado, signature: "unsigned", approved_by: null, estimate_digest: null },
        ]}
        escolhida={null}
        onEscolher={() => {}}
      />,
    );

    expect(html).toContain("Sem assinatura");
    expect(html).toContain("Ainda não foi assinado");
    expect(html).not.toContain("Assinado por");
  });

  /**
   * A procedência só existe depois da escolha, e ela é LIDA: obra, catálogo e contratado
   * aparecem como fato do orçamento, nunca como campo a preencher.
   */
  it("escolhido, mostra a procedência e diz que ela não é digitada", () => {
    const html = renderToStaticMarkup(
      <OrigemDoOrcamento
        origens={[assinado]}
        escolhida={assinado.round_id}
        onEscolher={() => {}}
      />,
    );

    expect(html).toContain("Contratado");
    expect(html).toContain("Saldo inicial");
    expect(html).toContain("igual ao contratado");
    expect(html).toContain("não são digitados");
    expect(html).not.toContain("<input type=\"text\"");
  });
});


/**
 * Decisão 9 do ADR-0048: rodada com vínculo e rodada sem vínculo têm garantias diferentes e
 * NÃO podem parecer iguais. Os dois testes abaixo leem o mesmo lugar da tela e exigem que
 * ele diga coisas opostas.
 */
describe("RegimeDeConferencia", () => {
  it("com origem assinada, nomeia o que passa a ser recusado", () => {
    const html = renderToStaticMarkup(
      <RegimeDeConferencia
        contracted={{
          origin: "signed_estimate",
          estimate_round_id: "0197f2a0-0000-7000-8000-0000000000c1",
          estimate_digest: "9".repeat(64),
          code_count: 34,
        }}
      />,
    );

    expect(html).toContain("Confere contra o orçamento assinado");
    expect(html).toContain("34 códigos");
    expect(html).toContain("acima do saldo");
    expect(html).toContain("digest do conteúdo assinado");
    expect(html).not.toContain("9".repeat(64) + "<");
  });

  it("sem origem assinada, declara o que NÃO é verificado", () => {
    const html = renderToStaticMarkup(
      <RegimeDeConferencia
        contracted={{
          origin: "none",
          estimate_round_id: null,
          estimate_digest: null,
        }}
      />,
    );

    expect(html).toContain("Sem contratado de origem");
    expect(html).toContain("não são verificados aqui");
    expect(html).toContain('role="alert"');
    expect(html).not.toContain("Confere contra o orçamento assinado");
  });
});

describe("ReRatificacaoDeclarada", () => {
  it("mostra a RE-RA declarada e a conta contratado → vigente → saldo", () => {
    const html = renderToStaticMarkup(
      <ReRatificacaoDeclarada
        contracted={{
          origin: "signed_estimate",
          estimate_round_id: "0197f2a0-0000-7000-8000-0000000000c1",
          estimate_digest: "9".repeat(64),
          amendments: [
            {
              label: "1ª RE-RA",
              reference_period: "Processo 123/2026",
              declared_by: "ana",
              declared_at: "2026-08-27T13:00:00+00:00",
              lines: [{ code: "CE04100010(/)", quantity_delta: "-2.00" }],
            },
          ],
          quantities: [
            {
              code: "CE04100010(/)",
              item_number: "1",
              description: "ALAMBRADO",
              unit: "m",
              contracted_quantity: "12.00",
              current_quantity: "10.00",
              current_balance_quantity: "10.00",
              re_ratified: true,
            },
          ],
        }}
      />,
    );

    // O selo diz "re-ratificada" por escrito — a cor não é o único indicador.
    expect(html).toContain("re-ratificada");
    expect(html).toContain("1ª RE-RA");
    expect(html).toContain("Processo 123/2026");
    expect(html).toContain("declarada por ana");
    // A conta é visível: contratado 12,00 → vigente 10,00, e não um número escrito à parte.
    expect(html).toContain("12.00");
    expect(html).toContain("10.00");
  });

  it("sem RE-RA declarada, não empurra o assunto para quem não o tem", () => {
    const html = renderToStaticMarkup(
      <ReRatificacaoDeclarada
        contracted={{
          origin: "signed_estimate",
          estimate_round_id: "0197f2a0-0000-7000-8000-0000000000c1",
          estimate_digest: "9".repeat(64),
        }}
      />,
    );

    expect(html).toBe("");
  });
});

describe("ReRatificacaoFieldset", () => {
  it("sem RE-RA, mostra só o convite a declarar", () => {
    const html = renderToStaticMarkup(
      <ReRatificacaoFieldset value={null} onChange={() => {}} />,
    );

    expect(html).toContain("Declarar uma RE-RA nesta abertura");
    expect(html).not.toContain("Nome curto");
  });

  it("com RE-RA, mostra os campos e a linha de código e efeito", () => {
    const html = renderToStaticMarkup(
      <ReRatificacaoFieldset
        value={{ label: "1ª RE-RA", referencePeriod: "", lines: [{ code: "", quantityDelta: "" }] }}
        onChange={() => {}}
      />,
    );

    expect(html).toContain("Nome curto");
    expect(html).toContain("Processo ou publicação");
    expect(html).toContain("adicionar código");
    expect(html).toContain("item novo");
  });
});

/**
 * A praça de várias folhas na tela (F-046). Todos os render são estáticos: o que se prova
 * aqui é o que a orçamentista lê, e nenhum número de obra é fabricado pela tela.
 */
function folhaDeTeste(overrides: Partial<WorksiteSheet> = {}): WorksiteSheet {
  return {
    plate_id: "planta-geral",
    position: 1,
    source_sha256: "a".repeat(64),
    page_number: 1,
    page_count: 6,
    extraction_status: "done",
    extraction_failure_code: null,
    extraction_updated_at: null,
    takeoff_present: true,
    packet_sha256: "b".repeat(64),
    review_status: "complete",
    item_count: 4,
    pending_items: 0,
    ...overrides,
  };
}

/**
 * O boletim da praça como `POST .../calc` o devolve desde a T4c: UM boletim por folha,
 * com a chave sufixada pela posição, e a memória de cada parcela na folha onde a leitura
 * foi feita. Nenhum número desta fixture é recalculado pela tela — é isso que os testes
 * do painel provam.
 */
function boletimDaPracaDeTeste(): BulletinResponse {
  return {
    round_id: "0197f2a0-0000-7000-8000-000000000001",
    version: 9,
    valuation_sha256: "e".repeat(64),
    total_amount: "9000.00",
    workbook_present: false,
    workbook_sha256: null,
    approval: {
      approved: false,
      approved_by: null,
      approved_at: null,
      approved_digest: null,
      current_digest: "e".repeat(64),
      stale: false,
    },
    valuation: {
      period_number: 1,
      reference_label: "AGOSTO/2026",
      bulletins: [
        {
          worksite_key: "praca-sintetica-oeste-p1",
          worksite_name: "Praça Sintética Oeste P1",
          total_amount: "6000.00",
          lines: [
            {
              item_number: "1",
              code: "04.02.010",
              description: "ALAMBRADO",
              unit: "m",
              unit_price: "150.00",
              quantity: "40.00",
              total: "6000.00",
            },
          ],
        },
        {
          worksite_key: "praca-sintetica-oeste-p2",
          worksite_name: "Praça Sintética Oeste P2",
          total_amount: "3000.00",
          lines: [
            {
              item_number: "1",
              code: "04.02.010",
              description: "ALAMBRADO",
              unit: "m",
              unit_price: "150.00",
              quantity: "20.00",
              total: "3000.00",
            },
          ],
        },
      ],
      calc_sheets: [
        {
          worksite_key: "praca-sintetica-oeste-p1",
          item_number: "1",
          total_quantity: "40.00",
          blocks: [
            {
              label: "PERÍMETRO NORTE",
              recipe: "length",
              operands: [{ name: "COMPRIMENTO", value: "40.00", unit: "m" }],
              subtotal: "40.00",
            },
          ],
        },
        {
          worksite_key: "praca-sintetica-oeste-p2",
          item_number: "1",
          total_quantity: "20.00",
          blocks: [
            {
              label: "PERÍMETRO SUL",
              recipe: "length",
              operands: [{ name: "COMPRIMENTO", value: "20.00", unit: "m" }],
              subtotal: "20.00",
            },
          ],
        },
      ],
    },
  } as unknown as BulletinResponse;
}

describe("FaixaDeFolhas", () => {
  it("diz o estado de cada folha por extenso e marca o foco em palavra", () => {
    const html = renderToStaticMarkup(
      <FaixaDeFolhas
        folhas={[
          folhaDeTeste(),
          folhaDeTeste({
            plate_id: "detalhe-playground",
            position: 2,
            review_status: "review_required",
            item_count: 3,
            pending_items: 2,
          }),
        ]}
        emFoco="detalhe-playground"
        onFocar={() => undefined}
      />,
    );

    expect(html).toContain("extraída e revisada");
    expect(html).toContain("pendente de revisão");
    expect(html).toContain("em foco");
    expect(html).toContain("Folha 2 de 2");
    expect(html).toContain("detalhe-playground");
    // O foco tem marca escrita, e não só a classe que o desenha.
    expect(html).toContain('aria-current="true"');
  });
});

describe("AcrescentarFolhas", () => {
  it("não marca nenhuma página por padrão e escreve o custo no botão", () => {
    const html = renderToStaticMarkup(
      <AcrescentarFolhas
        paginas={6}
        jaPromovidas={[1]}
        selecionadas={[]}
        aindaCabem={11}
        onAlternar={() => undefined}
        onConfirmar={() => undefined}
        submitting={false}
      />,
    );

    expect(html).not.toContain("checked");
    expect(html).toContain("nenhuma vem marcada por padrão");
    expect(html).toContain("já é folha desta praça");
    // Sem seleção, o botão não promete folha nenhuma e fica desabilitado.
    expect(html).toContain("Escolha as páginas que viram prancha");
    expect(html).toContain("disabled");
  });

  it("com páginas marcadas, o botão diz quantas folhas o ato acrescenta", () => {
    const html = renderToStaticMarkup(
      <AcrescentarFolhas
        paginas={6}
        jaPromovidas={[]}
        selecionadas={[1, 3, 5]}
        aindaCabem={11}
        onAlternar={() => undefined}
        onConfirmar={() => undefined}
        submitting={false}
      />,
    );

    expect(html).toContain("Acrescentar 3 folhas à praça");
    expect(html).toContain("3 páginas selecionadas");
  });

  it("seleção acima do teto da praça vira recusa lida, com o botão travado", () => {
    const html = renderToStaticMarkup(
      <AcrescentarFolhas
        paginas={6}
        jaPromovidas={[]}
        selecionadas={[1, 2, 3]}
        aindaCabem={1}
        onAlternar={() => undefined}
        onConfirmar={() => undefined}
        submitting={false}
      />,
    );

    expect(html).toContain('role="alert"');
    expect(html).toContain("desmarque");
    expect(html).toContain("disabled");
  });
});

describe("LerFolhasEmLote", () => {
  it("escreve quantas chamadas pagas o lote dispara e não marca folha nenhuma", () => {
    const folhas = [
      folhaDeTeste({ plate_id: "detalhe", position: 2, takeoff_present: false }),
      folhaDeTeste({ plate_id: "corte", position: 3, takeoff_present: false }),
    ];

    const vazio = renderToStaticMarkup(
      <LerFolhasEmLote
        folhas={folhas}
        selecionadas={[]}
        onAlternar={() => undefined}
        onConfirmar={() => undefined}
        submitting={false}
      />,
    );
    const marcado = renderToStaticMarkup(
      <LerFolhasEmLote
        folhas={folhas}
        selecionadas={["detalhe", "corte"]}
        onAlternar={() => undefined}
        onConfirmar={() => undefined}
        submitting={false}
      />,
    );

    expect(vazio).not.toContain("checked");
    expect(vazio).toContain("disabled");
    expect(marcado).toContain("2 chamadas pagas");
    expect(marcado).toContain("chamada paga de IA");
  });
});

describe("FolhaSemPacote", () => {
  /**
   * Sob o cabeçalho de uma folha, a imagem de outra seria uma afirmação falsa com cara de
   * evidência. A folha ainda não lida declara a ausência e não desenha nada.
   */
  it("declara a ausência em palavra e não desenha imagem nenhuma", () => {
    const html = renderToStaticMarkup(
      <FolhaSemPacote
        folha={folhaDeTeste({
          plate_id: "detalhe-playground",
          position: 2,
          takeoff_present: false,
          packet_sha256: null,
          review_status: null,
          item_count: null,
          pending_items: null,
          extraction_status: null,
        })}
        total={3}
      />,
    );

    expect(html).toContain("folha 2 de 3");
    expect(html).toContain('role="alert"');
    expect(html).toContain("ainda não tem pacote de takeoff");
    expect(html).toContain("Não existe overlay da praça");
    expect(html).not.toContain("<img");
  });

  /** A ausência que a T5 declarava — "a API responde pela primeira folha" — acabou. */
  it("não promete mais que a leitura por folha falta na API", () => {
    const html = renderToStaticMarkup(
      <FolhaSemPacote
        folha={folhaDeTeste({ plate_id: "detalhe", position: 2, takeoff_present: false })}
        total={2}
      />,
    );

    expect(html).not.toContain("ainda não é servida pela API");
    expect(html).not.toContain("responde pela primeira");
  });
});

/**
 * O re-render do overlay ainda é o da primeira folha (limitação declarada da T4c): a tela
 * DIZ isso na folha 2 em diante, em vez de esconder o desenho vencido.
 */
describe("OverlaySemRerender", () => {
  it("declara que o desenho desta folha não é refeito e não chama isso de erro", () => {
    const html = renderToStaticMarkup(
      <OverlaySemRerender
        folha={folhaDeTeste({ plate_id: "detalhe", position: 2 })}
        total={2}
      />,
    );

    expect(html).toContain("folha 2 de 2");
    expect(html).toContain("não é refeito");
    expect(html).toContain("vencido");
    // Estado declarado, não recusa: o boletim e as quantidades continuam corretos.
    expect(html).toContain('role="status"');
    expect(html).not.toContain('role="alert"');
  });
});

/**
 * A etapa de códigos é por folha, e sem esta lista a orçamentista veria "nada pendente" na
 * folha aberta sem saber que outra folha trava o boletim da praça inteira.
 */
describe("AndamentoDaCodificacao", () => {
  it("mostra o que falta em cada folha com as contagens do servidor", () => {
    const html = renderToStaticMarkup(
      <AndamentoDaCodificacao
        folhas={[
          { plateId: "planta-geral", position: 1, confirmed: 4, closed: 3, pending: 0 },
          { plateId: "detalhe", position: 2, confirmed: 1, closed: 0, pending: 2 },
        ]}
        total={2}
        emFoco="planta-geral"
        onFocar={() => undefined}
      />,
    );

    expect(html).toContain("folha 1 de 2");
    expect(html).toContain("folha 2 de 2");
    expect(html).toContain("nada pendente");
    expect(html).toContain("2 elementos pendentes");
    expect(html).toContain("codificando esta");
    expect(html).toContain("união");
  });

  /** Sem leitura de folha nenhuma, nada é escrito: ausência não vira zero. */
  it("some inteira quando nenhuma folha foi lida", () => {
    const html = renderToStaticMarkup(
      <AndamentoDaCodificacao
        folhas={[]}
        total={2}
        emFoco=""
        onFocar={() => undefined}
      />,
    );

    expect(html).toBe("");
  });
});

describe("PainelDaPraca", () => {
  const base: WorksiteResponse = {
    round_id: "0197f2a0-0000-7000-8000-000000000001",
    version: 4,
    worksite_key: "praca-sintetica-oeste",
    worksite_name: "Praça Sintética Oeste",
    plate_limit: 12,
    plates: [
      folhaDeTeste(),
      folhaDeTeste({ plate_id: "detalhe-playground", position: 2 }),
    ],
    identity_links: [],
    consolidated: {
      present: true,
      worksite_takeoff_sha256: "c".repeat(64),
      document: {
        worksite_key: "praca-sintetica-oeste",
        plates: [
          { plate_id: "planta-geral", packet_digest: "b".repeat(64) },
          { plate_id: "detalhe-playground", packet_digest: "d".repeat(64) },
        ],
        identity_links: [],
      },
      pending_plate_ids: [],
      refusal_code: null,
    },
  };

  it("mostra as folhas do consolidado por digest e não fabrica dinheiro nenhum", () => {
    const html = renderToStaticMarkup(<PainelDaPraca worksite={base} bulletin={null} />);

    expect(html).toContain("planta-geral");
    expect(html).toContain("detalhe-playground");
    expect(html).toContain("não contém itens");
    // Nenhum total, preço ou quantidade é escrito por esta tela.
    expect(html).not.toContain("R$");
    expect(html).not.toContain("Total da praça");
  });

  it("sem vínculo declarado, diz que duas leituras contam as duas", () => {
    const html = renderToStaticMarkup(<PainelDaPraca worksite={base} bulletin={null} />);

    expect(html).toContain("contam as duas");
    expect(html).toContain("não funde por rótulo");
  });

  it("o vínculo declarado aparece com a parcela que fica, autor, instante e nota", () => {
    const html = renderToStaticMarkup(
      <PainelDaPraca
        worksite={{
          ...base,
          identity_links: [
            {
              kept: { plate_id: "planta-geral", item_id: "ti_b3d5e820a7c14f69" },
              discarded: {
                plate_id: "detalhe-playground",
                item_id: "ti_5d2f83b60e4a1c97",
              },
              declared_by: "orcamentista-de-teste",
              declared_at: "2026-08-28T12:41:00+00:00",
              note: "mesmo trecho de alambrado do perímetro",
            },
          ],
        }}
        bulletin={null}
      />,
    );

    expect(html).toContain("identidade declarada");
    expect(html).toContain("a parcela que fica");
    expect(html).toContain("fundida, não contribui");
    expect(html).toContain("orcamentista-de-teste");
    expect(html).toContain("mesmo trecho de alambrado do perímetro");
  });

  it("a recusa nomeia a folha pendente e mostra o código estável do servidor", () => {
    const html = renderToStaticMarkup(
      <PainelDaPraca
        worksite={{
          ...base,
          plates: [
            folhaDeTeste(),
            folhaDeTeste({
              plate_id: "detalhe-playground",
              position: 2,
              takeoff_present: false,
              packet_sha256: null,
              review_status: null,
              item_count: null,
              pending_items: null,
              extraction_status: "running",
            }),
          ],
          consolidated: {
            present: false,
            worksite_takeoff_sha256: null,
            document: null,
            pending_plate_ids: ["detalhe-playground"],
            refusal_code: "ROUND_STAGE_NOT_READY",
          },
        }}
        bulletin={null}
      />,
    );

    expect(html).toContain('role="alert"');
    expect(html).toContain("folha 2 de 2");
    expect(html).toContain("detalhe-playground");
    expect(html).toContain("ROUND_STAGE_NOT_READY");
  });

  /**
   * Sem boletim montado não há número nenhum a mostrar — e a ausência é declarada, nunca
   * preenchida com zero.
   */
  it("sem boletim montado, declara a ausência e não escreve dinheiro nenhum", () => {
    const html = renderToStaticMarkup(<PainelDaPraca worksite={base} bulletin={null} />);

    expect(html).toContain("ainda não tem boletim montado");
    expect(html).not.toContain("R$");
    expect(html).not.toContain("Total da praça");
  });

  /**
   * Com boletim, os NÚMEROS aparecem — e cada um deles é a string que o servidor mandou.
   * O oráculo é textual de propósito: qualquer soma feita aqui produziria um número que
   * não está na resposta.
   */
  it("mostra o total por código e a memória por folha, com os números do servidor", () => {
    const html = renderToStaticMarkup(
      <PainelDaPraca worksite={base} bulletin={boletimDaPracaDeTeste()} />,
    );

    // O total da praça é `total_amount`, do servidor — não a soma das duas folhas.
    expect(html).toContain("Total da praça: R$ 9.000,00");
    // Uma linha por código, com a folha nomeada e o total daquela folha.
    expect(html).toContain("folha 1 de 2");
    expect(html).toContain("folha 2 de 2");
    expect(html).toContain("04.02.010");
    expect(html).toContain("R$ 6.000,00");
    expect(html).toContain("R$ 3.000,00");
    // A memória de cada folha, com a parcela na folha onde a leitura foi feita.
    expect(html).toContain("Memória desta folha");
    expect(html).toContain("PERÍMETRO NORTE");
    expect(html).toContain("PERÍMETRO SUL");
  });

  /**
   * A soma do mesmo código ENTRE folhas é da PLANILHA GERAL, na exportação. Esta tela diz
   * isso em palavra em vez de somar — é a regra da casa, e a deriva de centavo do
   * ADR-0062 mora no mesmo lugar.
   */
  it("declara que a soma por código entre folhas e a deriva de centavo são da planilha", () => {
    const html = renderToStaticMarkup(
      <PainelDaPraca worksite={base} bulletin={boletimDaPracaDeTeste()} />,
    );

    expect(html).toContain("soma dele entre as folhas");
    expect(html).toContain("ADR-0062");
    expect(html).toContain("não a calcula");
  });

  /**
   * Boletim montado antes de a folha entrar na praça: o painel DIZ que aquela folha ficou
   * de fora, em vez de rotular o boletim da folha 1 com o cabeçalho da folha 2.
   */
  it("boletim que não cobre a folha vira recusa lida, nunca boletim de outra folha", () => {
    const boletim = boletimDaPracaDeTeste();
    const html = renderToStaticMarkup(
      <PainelDaPraca
        worksite={base}
        bulletin={{
          ...boletim,
          valuation: {
            ...boletim.valuation,
            bulletins: [boletim.valuation.bulletins[0]],
            calc_sheets: [boletim.valuation.calc_sheets[0]],
          },
        }}
      />,
    );

    expect(html).toContain('role="alert"');
    expect(html).toContain("não cobre esta folha");
    expect(html).toContain("praca-sintetica-oeste-p2");
  });
});

/**
 * A declaração de identidade (pacote de design aprovado, decisão 11). O ato só é oferecido
 * COM a prévia do servidor: foi por faltar essa rota que a T5 se recusou a oferecê-lo.
 */
describe("DeclararIdentidade", () => {
  const itens = {
    "planta-geral": [
      {
        id: "ti_b3d5e820a7c14f69",
        label: "ALAMBRADO",
        raw_text: "ALAMBRADO 40,00 m",
        quantity: "40.00",
        unit: "m",
        status: "proposed",
        evidence: { bbox: [0, 0, 10, 10], page_number: 1 },
      },
    ],
    "detalhe-playground": [
      {
        id: "ti_5d2f83b60e4a1c97",
        label: "ALAMBRADO",
        raw_text: "ALAMBRADO 40,00 m",
        quantity: "40.00",
        unit: "m",
        status: "proposed",
        evidence: { bbox: [0, 0, 10, 10], page_number: 1 },
      },
    ],
  } as unknown as Record<string, TakeoffItem[]>;

  const folhas = [
    folhaDeTeste(),
    folhaDeTeste({ plate_id: "detalhe-playground", position: 2 }),
  ];

  const previa: IdentityLinkPreviewResponse = {
    round_id: "0197f2a0-0000-7000-8000-000000000001",
    version: 7,
    worksite_key: "praca-sintetica-oeste",
    kept: {
      plate_id: "planta-geral",
      item_id: "ti_b3d5e820a7c14f69",
      label: "ALAMBRADO",
      unit: "m",
      status: "proposed",
      quantity: "40.00",
    },
    discarded: {
      plate_id: "detalhe-playground",
      item_id: "ti_5d2f83b60e4a1c97",
      label: "ALAMBRADO",
      unit: "m",
      status: "proposed",
      quantity: "40.00",
    },
    unit_mismatch: false,
    total_before: "80.00",
    total_after: "40.00",
  };

  const rascunhoDaPrevia = {
    kept: { plate_id: "planta-geral", item_id: "ti_b3d5e820a7c14f69" },
    discarded: { plate_id: "detalhe-playground", item_id: "ti_5d2f83b60e4a1c97" },
    note: "",
  };

  function render(
    props: Partial<Parameters<typeof DeclararIdentidade>[0]> = {},
  ): string {
    return renderToStaticMarkup(
      <DeclararIdentidade
        folhas={folhas}
        itensPorFolha={itens}
        rascunho={VINCULO_VAZIO}
        previa={null}
        onRascunho={() => undefined}
        onPrever={() => undefined}
        onDeclarar={() => undefined}
        previewing={false}
        submitting={false}
        {...props}
      />,
    );
  }

  it("nada nasce escolhido e a declaração não é oferecida sem prévia", () => {
    const html = render();

    expect(html).toContain("escolha a folha");
    expect(html).toContain("Escolha as duas leituras");
    expect(html).toContain("esta tela nunca soma");
    expect(html).not.toContain("Declarar identidade");
    // Nenhuma folha e nenhuma leitura vêm marcadas: o que está escolhido é o vazio, e
    // fundir por rótulo, unidade ou proximidade é exatamente o que o ADR-0057 proíbe.
    expect(html).toContain('<option value="" selected="">escolha a folha</option>');
    expect(html).not.toContain('value="planta-geral" selected');
    expect(html).not.toContain('value="ti_b3d5e820a7c14f69" selected');
  });

  it("as duas leituras na mesma folha são recusadas antes da viagem", () => {
    const html = render({
      rascunho: {
        kept: { plate_id: "planta-geral", item_id: "ti_b3d5e820a7c14f69" },
        discarded: { plate_id: "planta-geral", item_id: "ti_5d2f83b60e4a1c97" },
        note: "",
      },
    });

    expect(html).toContain("entre folhas diferentes");
    expect(html).not.toContain("Declarar identidade");
  });

  it("com a prévia do par, mostra total antes e depois — os dois do servidor", () => {
    const html = render({ rascunho: rascunhoDaPrevia, previa });

    expect(html).toContain("Total hoje, sem o vínculo");
    expect(html).toContain("80,00 m");
    expect(html).toContain("Total depois do vínculo");
    expect(html).toContain("40,00 m");
    expect(html).toContain("Declarar identidade");
  });

  /**
   * Sem motivo escrito o ato não sai: o vínculo muda o total, e quem confere depois
   * precisa ler por que duas leituras viraram uma.
   */
  it("declarar fica travado sem motivo e liberado com ele", () => {
    expect(render({ rascunho: rascunhoDaPrevia, previa })).toContain("disabled");
    const comMotivo = render({
      rascunho: { ...rascunhoDaPrevia, note: "mesmo alambrado do perímetro" },
      previa,
    });

    expect(comMotivo).toContain("Declarar identidade");
    expect(comMotivo).not.toMatch(/Declarar identidade[^<]*<\/button>[\s\S]*disabled/);
  });

  /** Prévia de OUTRO par não vale: ela some, e com ela some o botão de declarar. */
  it("trocar a leitura depois de pré-visualizar apaga o número da tela", () => {
    const html = render({
      rascunho: {
        ...rascunhoDaPrevia,
        discarded: { plate_id: "detalhe-playground", item_id: "ti_outro_item_xxxx" },
      },
      previa,
    });

    expect(html).not.toContain("Total hoje, sem o vínculo");
    expect(html).not.toContain("Declarar identidade");
  });

  /**
   * Unidade divergente não tem soma, e um número escrito ali teria a aparência de conta
   * conferida. Os dois totais saem `null` do servidor e a tela não os inventa.
   */
  it("unidade divergente não vira soma: a recusa é lida e nenhum total é escrito", () => {
    const html = render({
      rascunho: rascunhoDaPrevia,
      previa: {
        ...previa,
        discarded: { ...previa.discarded, unit: "m2" },
        unit_mismatch: true,
        total_before: null,
        total_after: null,
      },
    });

    expect(html).toContain('role="alert"');
    expect(html).toContain("unidades diferentes");
    expect(html).not.toContain("Total hoje, sem o vínculo");
  });
});

/**
 * A herança e a prévia da medição seguinte (F-040 T6, decisões 4 e 6 do pacote aprovado).
 *
 * As duas são componentes exportados justamente para serem provadas aqui, fora do App: o que
 * se mede é o que a orçamentista lê ANTES de gravar.
 */
const RODADA_ANTERIOR = {
  round_id: "0197f2a0-0000-7000-8000-0000000000d1",
  worksite_key: "praca-orcada-sintetica",
  worksite_name: "PRACA ORCADA SINTETICA",
  reference_label: "Medição 1 — agosto/2026",
  period_number: 1,
  version: 3,
  status: "OPEN",
  stage: "bulletin",
  extraction_status: "idle",
  created_at: "2026-08-01T00:00:00+00:00",
  updated_at: "2026-08-01T00:00:00+00:00",
  approved: true,
  can_open_next: true,
} as unknown as RoundSummary;

const HERANCA: LinhaHerdada[] = [
  {
    code: "CE04100010(/)",
    itemNumber: "1.1",
    description: "ALAMBRADO GALVANIZADO",
    unit: "m",
    unitPrice: "50.00",
    contratado: "12.00",
    vigente: "12.00",
    medidoNoPeriodo: "5.00",
    acumulado: "5.00",
    saldo: "7.00",
    reRatificada: false,
  },
];

describe("HerancaDaRodadaAnterior", () => {
  it("mostra o que vem da rodada anterior código a código, antes de qualquer declaração", () => {
    const html = renderToStaticMarkup(
      <HerancaDaRodadaAnterior
        round={RODADA_ANTERIOR}
        heranca={HERANCA}
        totalMedido="250.00"
      />,
    );

    expect(html).toContain("O que vem da rodada anterior");
    expect(html).toContain("CE04100010(/)");
    expect(html).toContain("Contratado");
    expect(html).toContain("Vigente");
    expect(html).toContain("Período 1");
    expect(html).toContain("Acumulado");
    expect(html).toContain("Saldo");
    // Contratado e vigente repetem o mesmo número DE PROPÓSITO (decisão 4 do pacote).
    expect(html.match(/12,00/g)?.length).toBe(2);
    expect(html).toContain("5,00");
    expect(html).toContain("7,00");
    expect(html).toContain("R$ 250,00");
    expect(html).toContain("vigente é igual a contratado");
  });

  it("antes da resposta, não afirma herança nenhuma", () => {
    const html = renderToStaticMarkup(
      <HerancaDaRodadaAnterior round={RODADA_ANTERIOR} heranca={null} totalMedido={null} />,
    );

    expect(html).toContain("Lendo o que vem da rodada anterior");
    expect(html).not.toContain("Contratado");
  });

  it("sem contratado legível, declara a ausência em vez de mostrar tabela vazia", () => {
    const html = renderToStaticMarkup(
      <HerancaDaRodadaAnterior round={RODADA_ANTERIOR} heranca={[]} totalMedido={null} />,
    );

    expect(html).toContain("não devolveu o contratado código a código");
    expect(html).toContain('role="alert"');
  });

  it("número que o servidor mandou ilegível vira palavra, nunca um zero inventado", () => {
    const html = renderToStaticMarkup(
      <HerancaDaRodadaAnterior
        round={RODADA_ANTERIOR}
        heranca={[{ ...HERANCA[0], acumulado: null, saldo: null }]}
        totalMedido={null}
      />,
    );

    expect(html.match(/não legível/g)?.length).toBe(2);
    expect(html).not.toContain(">0,00<");
  });
});

describe("PreviaDaReRa", () => {
  const linhas: LinhaDaPrevia[] = [
    {
      code: "CE04100010(/)",
      description: "ALAMBRADO GALVANIZADO",
      unit: "m",
      unitPrice: "50.00",
      itemNovo: false,
      pendente: false,
      contratado: "12.00",
      vigenteHoje: "12.00",
      efeito: "+3",
      vigenteNovo: "15.00",
      acumulado: "5.00",
      saldoNovo: "10.00",
    },
    {
      code: "CE04100020(/)",
      description: "PORTAO SINTETICO GALVANIZADO",
      unit: "un",
      unitPrice: "30.00",
      itemNovo: true,
      pendente: false,
      contratado: "0.00",
      vigenteHoje: "0.00",
      efeito: "+2",
      vigenteNovo: "2.00",
      acumulado: "0.00",
      saldoNovo: "2.00",
    },
  ];

  it("mostra contratado → efeito → vigente → saldo novo, e diz que é prévia", () => {
    const html = renderToStaticMarkup(<PreviaDaReRa linhas={linhas} />);

    expect(html).toContain("Prévia: o que a declaração faz, antes de gravar");
    expect(html).toContain("Vigente novo");
    expect(html).toContain("Saldo novo");
    expect(html).toContain("+3");
    expect(html).toContain("15,00");
    expect(html).toContain("10,00");
    // O vigente é resultado de uma conta visível, e a tela diz que não se digita (decisão 6).
    expect(html).toContain("não é digitado");
    // A autoridade continua sendo do servidor, e a tela declara isso.
    expect(html).toContain("quem grava e confere o consolidado é o servidor");
  });

  it("marca o item novo por escrito e mostra o preço resolvido do catálogo", () => {
    const html = renderToStaticMarkup(<PreviaDaReRa linhas={linhas} />);

    expect(html).toContain("item novo");
    expect(html).toContain("PORTAO SINTETICO GALVANIZADO");
    expect(html).toContain("R$ 30,00");
    expect(html).toContain("2,00");
  });

  it("item novo não resolvido é dito por extenso, com o aviso persistente", () => {
    const html = renderToStaticMarkup(
      <PreviaDaReRa
        linhas={[
          { ...linhas[1], pendente: true, description: "", unit: "", unitPrice: null },
        ]}
      />,
    );

    expect(html).toContain("não encontrado no catálogo contratual");
    expect(html).toContain("o servidor recusará a abertura");
    expect(html).toContain('role="alert"');
  });

  it("sem declaração, não há prévia na tela", () => {
    expect(renderToStaticMarkup(<PreviaDaReRa linhas={[]} />)).toBe("");
  });
});
