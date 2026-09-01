import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import type { User } from "oidc-client-ts";
import type { Estimate } from "@croquito/contracts";
import type { GabaritoOption } from "./gabarito";

import {
  EscolhaDoGabarito,
  AtoDeAprovacao,
  AutoriaDeContribuicao,
  BannerOrcamentoMudou,
  BlocoConsumoDoTeto,
  FormularioDoAcervo,
  PainelParcelasDeCanteiro,
  EstadoDoBracoSemantico,
  FaixaTetoEstourado,
  LinhaTetoDaRodada,
  MemoriaDeCalculo,
  OrcamentoApp,
  ResumoDaMatriz,
  PainelEscolhaDeFonte,
  PainelRegimeDaRodada,
  PainelAutoAprovacaoRecusada,
  PainelSemAcesso,
  PainelDoLote,
  PranchaComAncoras,
  ItemDaLegenda,
  PainelSemPapelDeAprovador,
  PainelSemPapelDeOrcamentista,
  PainelTetoDaVerba,
  ProgressoDoDespacho,
  RegistroDaAprovacao,
  SeloDespacho,
  SeloFonte,
  SeloProcedencia,
  SeloRegime,
  SeloRegimeDaRodada,
  SemPrecoNaCascata,
  TelaAuditoriaReprovada,
  itemJaRevisado,
} from "./OrcamentoApp";
import {
  ACERVO_E_RECEITA,
  ACERVO_OPERANDO_NAO_DECLARADO,
  ACERVO_PARCELA_NAO_NASCE,
  ACERVO_REAPLICAR_SUBSTITUI,
  ACERVO_TEXTO_TRAZER_DE_VOLTA,
  AVISO_ACERVO_FILTRADO,
  AVISO_AMBIGUO_FORA_DO_LOTE,
  AVISO_ITEM_JA_REVISADO,
  AVISO_MEMORIA,
  AVISO_ORCAMENTO,
  AVISO_ORCAMENTO_SEM_RODADA,
  CANTEIRO_GRAVADO_DICA,
  CANTEIRO_QUANTIDADE_NA_MONTAGEM,
  DICA_LOTE_VAZIO,
  DICA_REGIME,
  fraseAplicarBloqueado,
  fraseCodigosAusentes,
  fraseParametrosFaltantes,
  RESUMO_MATRIZ_VAZIO,
  origensAceitasNaCascata,
} from "./labels";
import type { ReferenceCatalogOption } from "./api";
import {
  avancarParaParametros,
  contribuicoesDoAcervo,
  escolherAcervo,
  fluxoInicial,
  receberPrevia,
  type FluxoDoAcervo,
  type SiteSetupKit,
  type SiteSetupPreviewResponse,
} from "./acervo";
import {
  assembleCalcMatrix,
  disassembleCalcMatrix,
  emptyContributionForm,
  type CalcContributionDraft,
  type CalcContributionForm,
} from "./matrix";
import { derivarTeto } from "./teto";

/**
 * Render estático do primeiro estado: sem sessão, a jornada não chama a API e não inventa
 * orçamento. `renderToStaticMarkup` não roda efeitos, então isto é exatamente o que a
 * orçamentista vê antes de qualquer resposta.
 */
describe("OrcamentoApp sem sessão", () => {
  it("pede a sessão e não exibe orçamento, obra nem total", () => {
    const html = renderToStaticMarkup(<OrcamentoApp session={null} />);

    expect(html).toContain("Entre para abrir um orçamento");
    expect(html).toContain("autenticado e por tenant");
    // Nenhum número, obra ou código fabricado antes de o servidor responder.
    expect(html).not.toContain("R$");
    expect(html).not.toContain("Praça do Exemplo");
    expect(html).not.toContain("12.015.0030");
    expect(html).not.toContain("Total geral");
  });

  /**
   * A linha fixa continua dizendo as duas coisas que a confusão medição × orçamento
   * custou — de onde vem o preço e até onde ele não vai —, e para de dizer a terceira: sem
   * sessão não há rodada, e sem rodada não há regime a afirmar (F-033, revisão 2, tela 2).
   */
  it("declara de onde o preço vem sem afirmar o momento de uma rodada que não existe", () => {
    const html = renderToStaticMarkup(<OrcamentoApp session={null} />);

    expect(html).toContain(AVISO_ORCAMENTO_SEM_RODADA);
    expect(html).toContain("Nenhum preço daqui alcança um boletim de medição");
    expect(html).not.toContain(AVISO_ORCAMENTO);
    expect(html).not.toContain("pré-licitação");
    // Único eyebrow da jornada sobre painel branco: sem a veste clara ele herda a tinta da
    // topbar escura e o rótulo fica ilegível — trocaria "afirma um regime sobre nada" por
    // "não afirma nada porque ninguém vê".
    expect(html).toContain("eyebrow eyebrow-claro");
  });
});

/**
 * Com sessão e sem orçamento aberto (`?orcamento=`), a jornada começa por escolher — ou
 * abrir — um. Sem efeitos, a lista ainda não foi lida: o que aparece é a declaração
 * disso, nunca um orçamento fabricado.
 */
describe("OrcamentoApp com sessão e sem orçamento aberto", () => {
  const sessao = {
    access_token: "token-de-teste",
    profile: { sub: "orcamentista-de-teste" },
  } as unknown as User;

  it("oferece escolher um orçamento existente ou abrir um novo", () => {
    const html = renderToStaticMarkup(
      <OrcamentoApp session={sessao} roundId={null} />,
    );

    expect(html).toContain("Nenhum orçamento aberto");
    expect(html).toContain("Orçamentos do tenant");
    expect(html).toContain("Abrir orçamento novo");
    expect(html).toContain("A lista de orçamentos ainda não foi lida.");
  });

  /**
   * A cascata é a etapa seguinte e aceita mais de uma fonte: pedir catálogo na abertura
   * faria a primeira fonte parecer privilegiada.
   */
  it("não pede catálogo na abertura e declara que a cascata é a etapa seguinte", () => {
    const html = renderToStaticMarkup(
      <OrcamentoApp session={sessao} roundId={null} />,
    );

    expect(html).toContain("a cascata é a etapa seguinte");
    expect(html).not.toContain("Catálogo de preços (JSON)");
    // Nada de conceito de obra já licitada: período e contrato não existem aqui.
    expect(html).not.toContain("Número da medição");
    expect(html).not.toContain("Contrato");
  });

  /**
   * O teto nasce na abertura, opcional de verdade: campo vazio é "sem teto", não pede
   * justificativa, não avisa que falta preencher e não muda o botão.
   */
  it("oferece o teto e a demanda como opcionais, e o vazio é o caminho normal", () => {
    const html = renderToStaticMarkup(
      <OrcamentoApp session={sessao} roundId={null} />,
    );

    expect(html).toContain("Teto da verba (opcional)");
    expect(html).toContain("Demanda de origem (opcional)");
    expect(html).toContain("não é impresso na planilha e não impede nada");
    // Nenhuma recusa e nenhum botão desabilitado com os campos vazios.
    expect(html).not.toContain('role="alert"');
    expect(html).not.toContain("disabled");
  });

  it("não fabrica orçamento, obra nem total antes de ler a API", () => {
    const html = renderToStaticMarkup(
      <OrcamentoApp session={sessao} roundId={null} />,
    );

    expect(html).not.toContain("R$");
    expect(html).not.toContain("BDI 25");
    expect(html).not.toContain("Praça do Exemplo");
  });

  /**
   * A tela sem rodada não afirma o momento em lugar nenhum — nem na sobrescrita, nem na
   * faixa âmbar (F-033, revisão 2, tela 2). Era aqui que o defeito morava: não existe
   * rodada nesta tela, e mesmo assim ela dizia o regime de uma.
   */
  it("não afirma o momento onde não há rodada, nem no rótulo nem na faixa", () => {
    const html = renderToStaticMarkup(
      <OrcamentoApp session={sessao} roundId={null} />,
    );

    expect(html).toContain(">ORÇAMENTO-BASE<");
    expect(html).toContain(AVISO_ORCAMENTO_SEM_RODADA);
    expect(html).not.toContain("ORÇAMENTO-BASE · PRÉ-LICITAÇÃO");
    expect(html).not.toContain(AVISO_ORCAMENTO);
  });

  /**
   * A rodada pode nascer declarada (F-033, revisão 2, tela 3): o campo é visível, tem a
   * pergunta antes e a consequência depois, e a lacuna que o produto NÃO fecha é dita aqui
   * também — o caminho que virou principal não pode ser o que cala sobre ela.
   */
  it("oferece o regime na abertura, com a pergunta, a mão única e a lacuna", () => {
    const html = renderToStaticMarkup(
      <OrcamentoApp session={sessao} roundId={null} />,
    );

    expect(html).toContain("Regime");
    expect(html).toContain("contrato guarda-chuva já licitado");
    expect(html).toContain("Sob contrato, a cascata só aceita a tabela do contrato");
    expect(html).toContain("a rodada não volta para pré-licitação");
    expect(html).toContain(DICA_REGIME);
  });

  /**
   * Pré-licitação é o PADRÃO da abertura, e escolhê-la não é um ato: diferente do painel de
   * declarar depois, o botão continua ativo — simplesmente não se manda o campo.
   */
  it("nasce em pré-licitação, e o padrão não desliga o botão de abrir", () => {
    const html = renderToStaticMarkup(
      <OrcamentoApp session={sessao} roundId={null} />,
    );

    expect(html).toContain('<option value="" selected');
    // A asserção é sobre O BOTÃO, não sobre a página: `not.toContain("disabled")` no HTML
    // inteiro passaria a falhar no dia em que qualquer outro controle da tela nascesse
    // desabilitado, e falharia por motivo alheio ao que este teste protege.
    const botao = html.match(/<button type="submit"[^>]*>/)?.[0] ?? "";
    expect(botao).not.toBe("");
    expect(botao).not.toContain("disabled");
  });
});

/**
 * O selo de fonte é o elemento que a medição não tem: com mais de uma tabela na rodada,
 * de onde o preço veio deixa de ser redundante. Origem, data-base e posição vão ESCRITAS
 * — a cor da borda é redundância.
 */
describe("SeloFonte", () => {
  it("escreve origem, data-base e posição na cascata", () => {
    const html = renderToStaticMarkup(
      <SeloFonte origin="emop" referenceMonth="2026-07" position={2} />,
    );

    expect(html).toContain("EMOP");
    expect(html).toContain("data-base 2026-07");
    expect(html).toContain("2ª fonte da cascata");
    // A classe existe, mas é redundância — nunca o único indicador.
    expect(html).toContain("selo-fonte-emop");
  });

  it("sem posição conhecida, não inventa uma", () => {
    const html = renderToStaticMarkup(<SeloFonte origin="sco" />);

    expect(html).toContain("SCO");
    expect(html).not.toContain("fonte da cascata");
  });
});

/** Item sem preço é DECLARADO, nunca precificado por fora. */
describe("SemPrecoNaCascata", () => {
  it("declara o item e diz que o orçamento não inventa valor", () => {
    const html = renderToStaticMarkup(
      <SemPrecoNaCascata rotulos={["Bebedouro em aço inox · 2,00 un"]} />,
    );

    expect(html).toContain("Sem preço em nenhuma fonte");
    expect(html).toContain("Bebedouro em aço inox");
    expect(html).toContain("o orçamento não inventa valor");
    expect(html).toContain("sem preço na cascata");
  });

  it("sem item nenhum, a seção não aparece", () => {
    expect(renderToStaticMarkup(<SemPrecoNaCascata rotulos={[]} />)).toBe("");
  });
});

/**
 * O `409` não é erro do ato: o orçamento andou, nada foi gravado e o caminho é recarregar
 * — com o formulário preservado.
 */
/**
 * A suíte do web roda em `environment: "node"` (apps/web/vite.config.ts): não há DOM, e
 * `useEffect` não executa em `renderToStaticMarkup`. O que se prova aqui, portanto, é o
 * estado ANTES de conhecer as dimensões da página — que é exatamente o estado em que a
 * tela não pode desenhar âncora nenhuma, porque não sabe onde ela cai. A aritmética do
 * zoom e do enquadramento é testada em `prancha.test.ts`, onde é pura.
 */
describe("PranchaComAncoras", () => {
  const item = {
    id: "item-1",
    label: "PISO EM CONCRETO",
    quantity: "418.12",
    unit: "m2",
    status: "confirmed",
    raw_text: "PISO EM CONCRETO 418,12m²",
    evidence: {
      plate_id: "prancha-local",
      page_number: 1,
      image_sha256: "a".repeat(64),
      coordinate_space: "source_image_pixels",
      bbox: { left: 100, top: 200, right: 300, bottom: 260 },
    },
  } as unknown as Parameters<typeof PranchaComAncoras>[0]["itens"][number];

  it("mostra a prancha enquanto as dimensões da página não são conhecidas", () => {
    const html = renderToStaticMarkup(
      <PranchaComAncoras src="blob:prancha" itens={[item]} selectedItemId="" onSelect={() => {}} />,
    );

    expect(html).toContain("Página promovida da prancha deste orçamento");
    expect(html).toContain("blob:prancha");
    // Sem página medida não há viewBox, e sem viewBox uma âncora desenhada cairia no
    // lugar errado — com toda a autoridade de um desenho.
    expect(html).not.toContain("<svg");
    expect(html).not.toContain("ancora");
  });
});

describe("BannerOrcamentoMudou", () => {
  it("diz que o orçamento mudou, que nada foi gravado e oferece recarregar", () => {
    const html = renderToStaticMarkup(<BannerOrcamentoMudou onReload={() => {}} />);

    expect(html).toContain("O orçamento mudou");
    expect(html).toContain("Nada foi gravado");
    expect(html).toContain("continua aqui");
    expect(html).toContain("Recarregar estado atual");
    expect(html).toContain('role="alert"');
    expect(html).toContain("banner-conflito");
  });
});

/**
 * O 403 é desenhado genérico de propósito: qual papel autoriza a jornada é decisão humana
 * ainda aberta, e o texto não pode fingir que ela foi tomada.
 */
describe("PainelSemAcesso", () => {
  it("pede o acesso sem nomear papel nenhum", () => {
    const html = renderToStaticMarkup(<PainelSemAcesso />);

    expect(html).toContain("Sem acesso ao orçamento");
    expect(html).toContain("não tem o papel que autoriza");
    expect(html).toContain("quem administra o acesso");
    // Nenhum NOME de papel: "quem administra o acesso" é a pessoa a procurar, não um
    // papel do Keycloak.
    for (const papel of ["orcamentista", "platform_operator", "revisor"]) {
      expect(html.toLowerCase()).not.toContain(papel);
    }
  });
});

/**
 * A falha da auditoria é uma TELA, não um rodapé: "nada foi publicado" dito por extenso,
 * com os códigos dos achados. `expected`/`found` são dado de cliente e não viajam.
 */
describe("TelaAuditoriaReprovada", () => {
  it("diz que nada foi publicado e mostra só os códigos dos achados", () => {
    const html = renderToStaticMarkup(
      <TelaAuditoriaReprovada findings={["CELL_VALUE_MISMATCH"]} />,
    );

    expect(html).toContain("Nada foi publicado");
    expect(html).toContain("o arquivo foi descartado");
    expect(html).toContain("CELL_VALUE_MISMATCH");
    expect(html).toContain('role="alert"');
    // Nenhum valor de célula: preço e quantidade do cliente não saem em mensagem de erro.
    expect(html).not.toContain("R$");
    expect(html).not.toContain("previsto");
    expect(html).not.toContain("encontrado");
  });

  /**
   * A faixa afirma por extenso as duas coisas que a auditoria reprovada NÃO desfez
   * (F-035, tela 8 do pacote aprovado): a aprovação continua válida e o orçamento não
   * mudou. Sem isso, "reprovou" pareceria ter derrubado a assinatura junto.
   */
  it("declara que a aprovação continua válida e que o orçamento não mudou", () => {
    const html = renderToStaticMarkup(<TelaAuditoriaReprovada findings={[]} />);

    expect(html).toContain("a aprovação continua válida");
    expect(html).toContain("o orçamento não mudou");
  });

  /**
   * O progresso é lista ESCRITA de quatro passos, e no desfecho reprovado ela diz onde
   * parou: o arquivo foi gravado, a reconferência recusou e a publicação não aconteceu.
   */
  it("sem lista de achados, continua sendo a tela — e não fabrica achado", () => {
    const html = renderToStaticMarkup(<TelaAuditoriaReprovada findings={[]} />);

    expect(html).toContain("Nada foi publicado");
    expect(html).toContain("reprovado");
    expect(html).toContain("não iniciado");
    expect(html).not.toContain("CELL_VALUE_MISMATCH");
  });
});

/* Teto de verba (F-027, ADR-0040) ------------------------------------------- */

const TETO_DENTRO = {
  target: { amount: "95000.00", label: "Relação de Praças 2026 · demanda 14" },
  consumed: "91996.44",
  remaining: "3003.56",
  over: false,
};

const TETO_LIMITE = {
  target: { amount: "91996.44", label: "Relação de Praças 2026 · demanda 14" },
  consumed: "91996.44",
  remaining: "0.00",
  over: false,
};

const TETO_ESTOURADO = {
  target: { amount: "85000.00", label: "Relação de Praças 2026 · demanda 14" },
  consumed: "91996.44",
  remaining: "-6996.44",
  over: true,
};

/**
 * Os três estados do bloco de consumo. Os dois primeiros são o MESMO estado de domínio e
 * compartilham a veste; o que os distingue é a palavra, e ela é sempre o primeiro
 * indicador — cor nunca é o único.
 */
describe("BlocoConsumoDoTeto", () => {
  it("dentro do teto: estado escrito, percentual e restante", () => {
    const html = renderToStaticMarkup(
      <BlocoConsumoDoTeto teto={derivarTeto(TETO_DENTRO)} />,
    );

    expect(html).toContain("Dentro do teto");
    expect(html).toContain("teto-dentro");
    expect(html).toContain("R$ 95.000,00");
    expect(html).toContain("R$ 91.996,44");
    expect(html).toContain("Restante");
    expect(html).toContain("R$ 3.003,56");
    expect(html).toContain("96,83% do teto");
    // O consumo diz qual dos dois totais ele comparou.
    expect(html).toContain("Consumo — total com BDI");
    expect(html).not.toContain("Acima do teto");
  });

  /** Limite exato NÃO é estouro, e a tela diz isso por extenso — sem cor própria. */
  it("no limite exato: a palavra declara que aquilo não é estouro, na mesma veste", () => {
    const html = renderToStaticMarkup(
      <BlocoConsumoDoTeto teto={derivarTeto(TETO_LIMITE)} />,
    );

    expect(html).toContain("No limite exato — não é estouro");
    expect(html).toContain("teto-limite");
    expect(html).toContain("100,00% do teto");
    expect(html).toContain("R$ 0,00");
    expect(html).toContain("Consumir o teto inteiro é estar dentro dele");
    // Nenhuma classe do estouro, e nenhuma cor de estado própria do limite exato.
    expect(html).not.toContain("teto-estourado");
    expect(html).not.toContain("Teto estourado");
  });

  it("estourado: quanto passou em valor e em percentual, e as três consequências", () => {
    const html = renderToStaticMarkup(
      <BlocoConsumoDoTeto teto={derivarTeto(TETO_ESTOURADO)} />,
    );

    expect(html).toContain("Teto estourado");
    expect(html).toContain("teto-estourado");
    expect(html).toContain("Acima do teto");
    expect(html).toContain("R$ 6.996,44");
    expect(html).toContain("108,23% do teto");
    expect(html).toContain("O orçamento não foi recusado.");
    expect(html).toContain("Nenhuma linha foi removida nem sugerida para remoção.");
    expect(html).toContain("Pedir verba adicional para a demanda é um caminho legítimo");
    // Nenhum botão: toda saída do estouro é decisão humana fora desta tela.
    expect(html).not.toContain("<button");
  });

  /** Ausência de teto não é um estado a comunicar (ADR-0040, decisão 6). */
  it("rodada sem teto não acrescenta nada à prévia", () => {
    expect(renderToStaticMarkup(<BlocoConsumoDoTeto teto={derivarTeto({})} />)).toBe("");
    expect(renderToStaticMarkup(<BlocoConsumoDoTeto teto={null} />)).toBe("");
  });
});

/**
 * A faixa é CONDIÇÃO da rodada, não episódio de uma etapa: ela não recebe etapa nenhuma
 * como propriedade, e o app a renderiza uma vez só, fora da etapa visível — por isso
 * acompanha todas elas, inclusive a Planilha.
 */
describe("FaixaTetoEstourado", () => {
  it("declara quanto passou, em valor e em percentual, e cita a demanda", () => {
    const html = renderToStaticMarkup(
      <FaixaTetoEstourado teto={derivarTeto(TETO_ESTOURADO)} />,
    );

    expect(html).toContain("Teto estourado");
    expect(html).toContain("R$ 6.996,44");
    expect(html).toContain("8,23% acima do teto de R$ 85.000,00");
    expect(html).toContain("Relação de Praças 2026 · demanda 14");
    expect(html).toContain("Nada foi recusado e nada foi cortado.");
    expect(html).toContain("nenhuma linha foi removida");
    expect(html).toContain("todas as etapas");
    expect(html).toContain('role="status"');
  });

  /**
   * A decisão mais declarada do pacote aprovado: nenhum botão dentro do aviso. Nem
   * "ajustar para caber" (que seria o corte automático que o contrato proíbe), nem "rever
   * o teto" (que ensinaria a subir o número até o aviso sumir).
   */
  it("não tem botão nenhum, nem link de remédio", () => {
    const html = renderToStaticMarkup(
      <FaixaTetoEstourado teto={derivarTeto(TETO_ESTOURADO)} />,
    );

    expect(html).not.toContain("<button");
    expect(html).not.toContain("<a ");
    expect(html).not.toContain("ajustar");
    expect(html).not.toContain("Rever o teto");
  });

  it("fora do estouro não existe faixa — limite exato incluído", () => {
    for (const bloco of [TETO_DENTRO, TETO_LIMITE, {}]) {
      expect(
        renderToStaticMarkup(<FaixaTetoEstourado teto={derivarTeto(bloco)} />),
      ).toBe("");
    }
  });
});

/**
 * O painel existe em toda rodada aberta, e essa é a única exceção declarada ao "rodada sem
 * teto é exatamente como hoje": sem ele, uma rodada aberta sem teto nunca poderia ganhar
 * um. Não há botão de remover — apagar um teto já declarado é questão que o ADR-0040 não
 * decidiu.
 */
describe("PainelTetoDaVerba", () => {
  const props = {
    versao: 12,
    gravando: false,
    onValor: () => {},
    onRotulo: () => {},
    onGravar: () => {},
  };

  it("em rodada sem teto aparece vazio, silencioso e sem gravar nada", () => {
    const html = renderToStaticMarkup(
      <PainelTetoDaVerba {...props} valor="" rotulo="" />,
    );

    expect(html).toContain("Teto da verba");
    expect(html).toContain("Demanda de origem (opcional)");
    // Botão indisponível: não há o que gravar, e apagar teto não é ato desta tela.
    expect(html).toContain("disabled");
    expect(html).not.toContain("Remover");
    expect(html).not.toContain('role="alert"');
  });

  it("com teto declarado, diz o que a edição NÃO faz e cita a versão da rodada", () => {
    const html = renderToStaticMarkup(
      <PainelTetoDaVerba
        {...props}
        valor="85.000,00"
        rotulo="Relação de Praças 2026 · demanda 14"
      />,
    );

    expect(html).toContain("Gravar teto");
    expect(html).toContain("não remonta o orçamento");
    expect(html).toContain("rodada versão 12");
    expect(html).not.toContain("disabled");
  });

  /** Zero é recusado NA TELA, com a frase que ensina qual é o caminho de não ter teto. */
  it("recusa 0,00 no campo e deixa o botão indisponível", () => {
    const html = renderToStaticMarkup(
      <PainelTetoDaVerba {...props} valor="0,00" rotulo="" />,
    );

    expect(html).toContain("precisa ser maior que zero");
    expect(html).toContain("deixe o campo vazio");
    expect(html).toContain('role="alert"');
    expect(html).toContain('aria-invalid="true"');
    expect(html).toContain("disabled");
  });

  it("enquanto grava, campo e botão ficam indisponíveis", () => {
    const html = renderToStaticMarkup(
      <PainelTetoDaVerba {...props} valor="120.000,00" rotulo="" gravando />,
    );

    expect(html).toContain("Gravando…");
    expect(html).toContain("disabled");
  });
});

/**
 * A rodada sem teto é a de hoje: a faixa é renderizada UMA vez, fora da etapa visível
 * (`FaixaTetoEstourado` não recebe etapa nenhuma), e sem teto ela não existe em nenhuma
 * delas. Sem efeitos o estado da rodada ainda não foi lido, que é o caso mais forte de
 * "não fabricar": nenhum vestígio de teto aparece antes de o servidor responder.
 */
describe("rodada aberta sem teto lido", () => {
  const sessao = {
    access_token: "token-de-teste",
    profile: { sub: "orcamentista-de-teste" },
  } as unknown as User;

  it("não mostra faixa, bloco de consumo nem número de teto em etapa nenhuma", () => {
    const html = renderToStaticMarkup(
      <OrcamentoApp
        session={sessao}
        roundId="0197f2a0-0000-7000-8000-000000000009"
      />,
    );

    expect(html).toContain("Etapas do orçamento");
    expect(html).not.toContain("teto-faixa");
    expect(html).not.toContain("teto-consumo");
    expect(html).not.toContain("Teto estourado");
    expect(html).not.toContain("Dentro do teto");
    expect(html).not.toContain("sem teto");
    expect(html).not.toContain("R$");
  });
});

/** A linha do teto na lista existe SÓ na rodada que tem teto. */
describe("LinhaTetoDaRodada", () => {
  it("mostra o teto e a demanda quando a rodada tem teto", () => {
    const html = renderToStaticMarkup(
      <LinhaTetoDaRodada
        amount="85000.00"
        label="Relação de Praças 2026 · demanda 14"
      />,
    );

    expect(html).toContain("R$ 85.000,00");
    expect(html).toContain("Relação de Praças 2026 · demanda 14");
  });

  it("rodada sem teto não ganha linha, nem “sem teto”, nem “teto: —”", () => {
    expect(
      renderToStaticMarkup(<LinhaTetoDaRodada amount={null} label={null} />),
    ).toBe("");
  });

  it("com teto e sem demanda, não inventa rótulo", () => {
    const html = renderToStaticMarkup(
      <LinhaTetoDaRodada amount="85000.00" label={null} />,
    );

    expect(html).toContain("R$ 85.000,00");
    expect(html).not.toContain("·");
  });
});

/**
 * BDI por grupo é elemento RESERVADO no pacote aprovado: "até lá não é renderizado — some
 * da tela, não vira controle desligado". Nenhum vestígio dele existe no produto.
 */
describe("BDI por grupo não é renderizado", () => {
  const sessao = {
    access_token: "token-de-teste",
    profile: { sub: "orcamentista-de-teste" },
  } as unknown as User;

  it("não há bloco reservado nem controle desligado em nenhum estado inicial", () => {
    for (const html of [
      renderToStaticMarkup(<OrcamentoApp session={null} />),
      renderToStaticMarkup(<OrcamentoApp session={sessao} roundId={null} />),
    ]) {
      expect(html).not.toContain("BDI por grupo");
      expect(html).not.toContain("reservado");
      expect(html).not.toContain("Reservado");
    }
  });
});

/**
 * O selo do regime (F-033, revisão 1 aprovada em 2026-08-22): o único valor visual novo do
 * pacote, e a única peça que a rodada sob contrato acrescenta ao cabeçalho e à aba Cascata.
 * O que ele diz vai ESCRITO — a forma de contorno é redundância.
 */
describe("SeloRegime", () => {
  it("escreve o regime por extenso, no vocabulário que o ADR-0045 fixou", () => {
    expect(renderToStaticMarkup(<SeloRegime />)).toContain(
      "SOB CONTRATO LICITADO",
    );
  });

  it("tem uma veste por superfície: a escura do topbar e a clara do painel", () => {
    const escuro = renderToStaticMarkup(<SeloRegime />);
    const claro = renderToStaticMarkup(<SeloRegime variante="claro" />);

    expect(escuro).toContain("selo-regime");
    expect(escuro).not.toContain("selo-regime-claro");
    expect(claro).toContain("selo-regime-claro");
    // As duas dizem a mesma coisa: a diferença é de superfície, nunca de conteúdo.
    expect(claro).toContain("SOB CONTRATO LICITADO");
  });
});

/**
 * O selo no CARD da lista (F-033, revisão 2, decisão 4): o card diz o regime antes de a
 * rodada ser aberta, e o silêncio também diz — card sem selo é rodada em pré-licitação.
 */
describe("SeloRegimeDaRodada", () => {
  it("mostra o mesmo selo, na veste clara, quando a rodada tem regime", () => {
    const html = renderToStaticMarkup(
      <SeloRegimeDaRodada regime="contracted_demand" />,
    );

    expect(html).toContain("SOB CONTRATO LICITADO");
    expect(html).toContain("selo-regime-claro");
  });

  it("sem regime não há selo nenhum: a ausência não vira 'regime: —'", () => {
    expect(renderToStaticMarkup(<SeloRegimeDaRodada regime={null} />)).toBe("");
  });
});

/**
 * Declarar o regime é ato próprio, com seletor e botão (decisão 4 do pacote aprovado) — e
 * mão única: o painel não oferece a volta para pré-licitação, que o servidor recusa com
 * `ESTIMATE_REGIME_IRREVERSIBLE`.
 */
describe("PainelRegimeDaRodada", () => {
  function painel(valor: "" | "contracted_demand" = "") {
    return renderToStaticMarkup(
      <PainelRegimeDaRodada
        valor={valor}
        versao={4}
        declarando={false}
        onValor={() => {}}
        onDeclarar={() => {}}
      />,
    );
  }

  it("pergunta, explica o que a declaração faz e grava sobre a versão lida", () => {
    const html = painel();

    expect(html).toContain("Esta demanda corre sob contrato licitado?");
    expect(html).toContain("contrato guarda-chuva já licitado");
    expect(html).toContain("Declarar");
    expect(html).toContain("rodada versão 4");
  });

  /** O que a declaração NÃO faz, dito ANTES do clique — a lacuna que o ADR-0045 nomeia. */
  it("declara que restringir a origem não confere o contrato", () => {
    const html = painel();

    expect(html).toContain("Restringir a origem não confere o contrato");
    expect(html).toContain("não que veio da tabela, data-base e desconto");
  });

  /** Mão única, escrita antes e não só na recusa. */
  it("diz que a rodada não volta para pré-licitação", () => {
    expect(painel()).toContain("mão única");
    expect(painel()).toContain("abrir outra rodada");
  });

  /**
   * "Pré-licitação" é onde a rodada JÁ está, e escolhê-la não é um ato: o botão continua
   * desligado. É assim que o painel mostra as duas opções sem oferecer a volta.
   */
  it("com a pré-licitação escolhida, declarar está desligado", () => {
    expect(painel()).toContain("disabled");
  });

  it("escolhida a demanda sob contrato, declarar fica disponível", () => {
    expect(painel("contracted_demand")).not.toContain("disabled");
  });
});

/**
 * Rodada SEM regime é a tela de hoje, sem nenhuma peça nova (decisão 5 do pacote): ausência
 * não é um valor, é a falta dele.
 *
 * Com a revisão 2 a abertura passou a OFERECER a escolha, e oferecer não é afirmar: o que
 * nenhum destes renders pode conter continua sendo o selo, o candidato a aditivo e a frase
 * que declara a rodada sob contrato licitado.
 */
describe("rodada sem regime declarado", () => {
  const sessao = {
    access_token: "token-de-teste",
    profile: { sub: "orcamentista-de-teste" },
  } as unknown as User;

  it("mantém a linha fixa e a sobrescrita da pré-licitação", () => {
    const html = renderToStaticMarkup(
      <OrcamentoApp session={sessao} roundId="0197f2a0-0000-7000-8000-000000000009" />,
    );

    expect(html).toContain("ORÇAMENTO-BASE · PRÉ-LICITAÇÃO");
    expect(html).toContain(AVISO_ORCAMENTO);
    expect(html).not.toContain("DEMANDA SOB CONTRATO");
  });

  it("não tem selo, não tem candidato a aditivo e não fala em contrato licitado", () => {
    for (const html of [
      renderToStaticMarkup(<OrcamentoApp session={null} />),
      renderToStaticMarkup(<OrcamentoApp session={sessao} roundId={null} />),
      renderToStaticMarkup(
        <OrcamentoApp session={sessao} roundId="0197f2a0-0000-7000-8000-000000000009" />,
      ),
    ]) {
      expect(html).not.toContain("SOB CONTRATO LICITADO");
      expect(html).not.toContain("selo-regime");
      expect(html).not.toContain("candidato a aditivo");
      expect(html).not.toContain("contrato licitado");
    }
  });
});

/**
 * Procedência da fonte instalada (F-037, revisão 1 aprovada, tela 4). A marca é a
 * PALAVRA — cor nunca é o único indicador — e a ausência do campo continua legível.
 */
describe("SeloProcedencia", () => {
  it("escreve de onde o arquivo veio, por extenso", () => {
    expect(
      renderToStaticMarkup(<SeloProcedencia provenance="reference_catalog" />),
    ).toContain("DO ACERVO");
    expect(
      renderToStaticMarkup(<SeloProcedencia provenance="tenant_upload" />),
    ).toContain("TABELA PRÓPRIA");
  });

  /** Cascata instalada antes da feature não tem o campo e não vira "desconhecido". */
  it("sem o campo, lê como tabela própria — que é o que ela é", () => {
    const html = renderToStaticMarkup(<SeloProcedencia />);

    expect(html).toContain("TABELA PRÓPRIA");
    expect(html).not.toContain("desconhec");
  });

  it("a classe é redundância da palavra, nunca o indicador sozinho", () => {
    const html = renderToStaticMarkup(
      <SeloProcedencia provenance="reference_catalog" />,
    );

    expect(html).toContain("selo-procedencia");
    expect(html).toContain(">DO ACERVO<");
  });
});

/**
 * A escolha da fonte (F-037, telas 2, 3, 5 e 6): a lista é o caminho principal e o
 * arquivo próprio é a alternativa NOMEADA — ela diz para quem serve, e não some.
 */
describe("PainelEscolhaDeFonte", () => {
  const ACERVO: ReferenceCatalogOption[] = [
    {
      reference_catalog_id: "0197f2a0-0000-7000-8000-00000000aaaa",
      display_name: "SCO-Rio FGV06 desonerado",
      origin: "sco",
      reference_month: "2026-07",
      entry_count: 4865,
      source_sha256: "a".repeat(64),
    },
    {
      reference_catalog_id: "0197f2a0-0000-7000-8000-00000000bbbb",
      display_name: "SINAPI RJ desonerado",
      origin: "sinapi",
      reference_month: "2026-07",
      entry_count: 12034,
      source_sha256: "b".repeat(64),
    },
  ];

  const props = {
    acervo: ACERVO,
    acervoAviso: null,
    escolhida: "",
    arquivo: null,
    tabelaPropria: false,
    regimeAceita: null,
    sobContrato: false,
    instalando: false,
    onEscolher: () => {},
    onArquivo: () => {},
    onTabelaPropria: () => {},
    onInstalarDoAcervo: () => {},
    onInstalarArquivo: () => {},
  };

  it("oferece a lista com nome, data-base e contagem, e nada nasce escolhido", () => {
    const html = renderToStaticMarkup(<PainelEscolhaDeFonte {...props} />);

    expect(html).toContain("Tabela de preços");
    expect(html).toContain("Escolha uma tabela…");
    expect(html).toContain("SCO-Rio FGV06 desonerado · ref. 2026-07 · 4.865 itens");
    expect(html).toContain("SINAPI RJ desonerado · ref. 2026-07 · 12.034 itens");
    expect(html).toContain("Instalar tabela");
    // Sem escolha, o ato não está disponível: nada é instalado por engano.
    expect(html).toContain("disabled");
  });

  /** A alternativa não some, e ela diz PARA QUEM serve antes do clique. */
  it("nomeia a alternativa da tabela própria em vez de escondê-la", () => {
    const html = renderToStaticMarkup(<PainelEscolhaDeFonte {...props} />);

    expect(html).toContain("a do seu contrato, ou uma que você licenciou");
    expect(html).toContain("Enviar arquivo");
  });

  /** Escolhida uma tabela, o botão instala — e o caminho não pede arquivo nenhum. */
  it("com a tabela escolhida, instala sem pedir arquivo", () => {
    const html = renderToStaticMarkup(
      <PainelEscolhaDeFonte
        {...props}
        escolhida="0197f2a0-0000-7000-8000-00000000aaaa"
      />,
    );

    expect(html).not.toContain('type="file"');
    expect(html).not.toContain("disabled");
  });

  /**
   * Tela 3: o caminho de hoje, inteiro. O campo, o `accept` e o rótulo do botão são os
   * mesmos que já estavam no ar — o que mudou é a ordem em que ele aparece.
   */
  it("no modo tabela própria, o formulário de arquivo é o de hoje", () => {
    const html = renderToStaticMarkup(
      <PainelEscolhaDeFonte {...props} tabelaPropria />,
    );

    expect(html).toContain("Enviar tabela própria");
    expect(html).toContain("a EMOP, que é paga");
    expect(html).toContain("Catálogo de preços (JSON)");
    expect(html).toContain('type="file"');
    expect(html).toContain('accept=".json,application/json"');
    expect(html).toContain("Entra no FIM da cascata. Uma origem só entra uma vez.");
    expect(html).toContain("Instalar catálogo");
    // A volta para a lista existe: a alternativa não é um beco sem saída.
    expect(html).toContain("Voltar para a lista");
  });

  it("sem arquivo escolhido, o caminho da tabela própria não instala nada", () => {
    const semArquivo = renderToStaticMarkup(
      <PainelEscolhaDeFonte {...props} tabelaPropria />,
    );
    const comArquivo = renderToStaticMarkup(
      <PainelEscolhaDeFonte
        {...props}
        tabelaPropria
        arquivo={new File(["{}"], "catalogo.json", { type: "application/json" })}
      />,
    );

    expect(semArquivo).toContain("disabled");
    expect(comArquivo).not.toContain("disabled");
  });

  /**
   * Tela 5: a lista já vem filtrada do SERVIDOR, e a tela explica por escrito por que ela
   * pode estar mais curta. Ela não reimplementa a regra — a frase das origens aceitas
   * continua sendo a que o servidor mandou.
   */
  it("sob contrato, explica a lista curta sem guardar cópia da regra", () => {
    const html = renderToStaticMarkup(
      <PainelEscolhaDeFonte
        {...props}
        acervo={[ACERVO[0]]}
        sobContrato
        regimeAceita={origensAceitasNaCascata(["sco"])}
      />,
    );

    expect(html).toContain(AVISO_ACERVO_FILTRADO);
    expect(html).toContain("catálogo de SCO");
    expect(html).toContain("SCO-Rio FGV06 desonerado");
    expect(html).not.toContain("SINAPI");
  });

  /** Tela 6: acervo vazio é ESTADO, não erro — e a saída fica na mesma tela. */
  it("acervo vazio afirma que a plataforma não publicou e oferece o arquivo", () => {
    const html = renderToStaticMarkup(
      <PainelEscolhaDeFonte {...props} acervo={[]} />,
    );

    expect(html).toContain("Nenhuma tabela disponível");
    expect(html).toContain("A plataforma ainda não publicou");
    expect(html).toContain("Enviar tabela própria");
    // Estado, não falha: nada de alerta de erro nesta tela.
    expect(html).not.toContain('role="alert"');
  });

  /** Lista não lida não é acervo vazio, e a tela não confunde as duas. */
  it("lista ainda não lida é declarada, nunca disfarçada de acervo vazio", () => {
    const html = renderToStaticMarkup(
      <PainelEscolhaDeFonte {...props} acervo={null} />,
    );

    expect(html).toContain("ainda não foi lida");
    expect(html).not.toContain("Nenhuma tabela disponível");
    // O caminho do arquivo próprio continua oferecido enquanto a lista não chega.
    expect(html).toContain("Enviar arquivo");
  });

  /** Falha de leitura do acervo é persistente e não esconde o outro caminho. */
  it("falha ao ler o acervo aparece como aviso, com o arquivo próprio ainda oferecido", () => {
    const html = renderToStaticMarkup(
      <PainelEscolhaDeFonte
        {...props}
        acervo={null}
        acervoAviso="A lista de tabelas da plataforma não pôde ser lida agora."
      />,
    );

    expect(html).toContain('role="alert"');
    expect(html).toContain("não pôde ser lida agora");
    expect(html).toContain("Enviar arquivo");
  });
});
/**
 * O ato nominal (F-035, ADR-0046), em dois passos explícitos e sem campo de nome.
 *
 * Estes testes fixam o que o pacote de design aprovado decidiu e o que não pode ser
 * "simplificado" depois: a consequência dita ANTES do botão, a identidade mostrada e nunca
 * digitável, e o segundo passo repetindo a consequência em vez de perguntar "tem certeza?".
 */
describe("AtoDeAprovacao", () => {
  const props = {
    titulo: "Aprovar o orçamento de Praça do Exemplo",
    identidade: "marina.gestora",
    contentDigest: "9c41ab7" + "0".repeat(57),
    gravando: false,
    onAprovar: () => {},
    onConfirmar: () => {},
    onCancelar: () => {},
  };

  it("primeiro passo: as três consequências antes do botão", () => {
    const html = renderToStaticMarkup(
      <AtoDeAprovacao {...props} confirmando={false} />,
    );

    expect(html).toContain("Antes de aprovar, o que aprovar faz");
    expect(html).toContain("Publica o seu nome");
    expect(html).toContain("Libera o despacho");
    expect(html).toContain("Vale só para este orçamento");
    expect(html).toContain("Aprovar este orçamento");
    // O segundo passo ainda não aconteceu: nada de confirmação nesta tela.
    expect(html).not.toContain("Confirmar aprovação nominal");
  });

  /**
   * A identidade é MOSTRADA, nunca digitável (decisão 3 do pacote): um campo de nome
   * prometeria um efeito que ele não tem, porque o servidor lê o subject do token e recusa
   * qualquer nome vindo do cliente.
   */
  it("mostra a identidade da sessão e não oferece campo de nome", () => {
    const html = renderToStaticMarkup(
      <AtoDeAprovacao {...props} confirmando={false} />,
    );

    expect(html).toContain("Você aprova como");
    expect(html).toContain("marina.gestora");
    expect(html).toContain("recusa qualquer nome que venha do cliente");
    expect(html).not.toContain("<input");
    expect(html).not.toContain("<textarea");
  });

  it("segundo passo repete a consequência sobre o âmbar, com saída de cancelar", () => {
    const html = renderToStaticMarkup(
      <AtoDeAprovacao {...props} confirmando={true} />,
    );

    expect(html).toContain("ato-confirmacao");
    expect(html).toContain("Confirmar a aprovação nominal?");
    expect(html).toContain("o despacho da planilha fica liberado");
    expect(html).toContain("Cancelar");
    // Não é "tem certeza?" vazio: o nome e o conteúdo assinado aparecem de novo.
    expect(html).toContain("marina.gestora");
    expect(html).toContain("sha256 9c41ab7");
  });

  it("enquanto grava, os dois botões ficam indisponíveis e a tela diz por quê", () => {
    const html = renderToStaticMarkup(
      <AtoDeAprovacao {...props} confirmando={true} gravando={true} />,
    );

    expect(html).toContain("disabled");
    expect(html).toContain("chave de idempotência");
  });
});

/**
 * O registro é quem, quando e sobre qual conteúdo — e na caducidade os DOIS digests lado a
 * lado, com a PALAVRA marcando o estado. Cor nunca é o único indicador.
 */
describe("RegistroDaAprovacao", () => {
  const aprovada = {
    approved: true,
    approved_by: "marina.gestora",
    approved_at: "2026-08-22T18:41:00Z",
    approved_digest: "9c41ab7" + "0".repeat(57),
    current_digest: "9c41ab7" + "0".repeat(57),
    stale: false,
  };

  it("aprovação válida traz quem, quando e o conteúdo assinado", () => {
    const html = renderToStaticMarkup(
      <RegistroDaAprovacao approval={aprovada} />,
    );

    expect(html).toContain("Aprovada");
    expect(html).toContain("Quem aprovou");
    expect(html).toContain("marina.gestora");
    expect(html).toContain("Quando");
    expect(html).toContain("igual ao do orçamento atual");
    // Um digest só: não há o que comparar enquanto o conteúdo não mudou.
    expect(html).not.toContain("digest-par");
  });

  it("na caducidade, a PALAVRA marca o estado e os dois digests aparecem", () => {
    const html = renderToStaticMarkup(
      <RegistroDaAprovacao
        approval={{
          ...aprovada,
          current_digest: "2e77d04" + "0".repeat(57),
          stale: true,
        }}
      />,
    );

    expect(html).toContain("Aprovação caduca");
    expect(html).toContain("digest-par");
    expect(html).toContain("Conteúdo aprovado");
    expect(html).toContain("Conteúdo atual");
    expect(html).toContain("sha256 9c41ab7");
    expect(html).toContain("sha256 2e77d04");
    // O registro velho NÃO some: quem assinou continua nomeado.
    expect(html).toContain("marina.gestora");
    // O tracejado âmbar é redundância da palavra, não a marca sozinha.
    expect(html).toContain("registro-caduca");
  });

  it("sem ato nenhum registrado, não inventa registro", () => {
    const html = renderToStaticMarkup(
      <RegistroDaAprovacao
        approval={{
          approved: false,
          approved_by: null,
          approved_at: null,
          approved_digest: null,
          current_digest: "9c41ab7" + "0".repeat(57),
          stale: false,
        }}
      />,
    );

    expect(html).toBe("");
  });
});

/**
 * O selo do despacho é o único valor visual novo do pacote. Ele diz a palavra e NÃO diz
 * data: nenhuma rota do orçamento devolve o instante do despacho, e carimbar o `updated_at`
 * da rodada daria a um número que muda a cada mutação a aparência de registro de publicação.
 */
describe("SeloDespacho", () => {
  it("declara os dois estados por extenso", () => {
    expect(renderToStaticMarkup(<SeloDespacho despachado={false} />)).toContain(
      "NÃO DESPACHADO",
    );
    expect(renderToStaticMarkup(<SeloDespacho despachado={true} />)).toContain(
      "DESPACHADO",
    );
  });

  it("não carimba data que o servidor não devolve", () => {
    const html = renderToStaticMarkup(<SeloDespacho despachado={true} />);

    expect(html).not.toContain("EM ");
    expect(html).not.toMatch(/\d{2}\/\d{2}\/\d{4}/);
  });
});

/**
 * O despacho é passo a passo ESCRITO, nunca barra (decisão 6 do pacote): três dos quatro
 * passos acontecem antes de existir arquivo publicado.
 */
describe("ProgressoDoDespacho", () => {
  it("são quatro passos nomeados, e o portão de domínio é o primeiro", () => {
    const html = renderToStaticMarkup(<ProgressoDoDespacho estado="em-voo" />);

    expect(html).toContain("portão de domínio");
    expect(html).toContain("arquivo temporário");
    expect(html).toContain("reconferida centavo a centavo");
    expect(html).toContain("publicação");
    // Nada de barra: nenhum `progress` e nenhuma percentagem.
    expect(html).not.toContain("<progress");
    expect(html).not.toContain("%");
  });

  /**
   * Em voo, a tela não observa em qual passo o servidor está — e não finge que observa.
   * É a única coisa da rendição aprovada que não pode ser reproduzida sem inventar estado.
   */
  it("em voo, nenhum passo é declarado concluído", () => {
    const html = renderToStaticMarkup(<ProgressoDoDespacho estado="em-voo" />);

    expect(html).toContain("no servidor");
    expect(html).not.toContain("concluído");
    expect(html).toContain("Nada é publicado antes do quarto passo");
  });

  it("reprovado diz onde parou: gravado, recusado na reconferência, não publicado", () => {
    const html = renderToStaticMarkup(
      <ProgressoDoDespacho estado="reprovado" />,
    );

    expect(html).toContain("reprovado");
    expect(html).toContain("não iniciado");
  });
});

/**
 * O `403` da assinatura não é a tela de "sem acesso": quem chega aqui lê o orçamento
 * inteiro (a leitura aceita `orcamentista` ou `aprovador`) e só não exerce o ato.
 */
/**
 * O `403` do DESPACHO também não é a tela de "sem acesso": desde a F-035 quem só tem
 * `aprovador` lê a jornada inteira e assina — o que falta é quem opere o envio.
 */
describe("PainelSemPapelDeOrcamentista", () => {
  it("nomeia o papel do despacho e preserva a assinatura já registrada", () => {
    const html = renderToStaticMarkup(<PainelSemPapelDeOrcamentista />);

    expect(html).toContain("papel orcamentista");
    expect(html).toContain("A aprovação registrada continua valendo");
    expect(html).toContain("Nada foi publicado");
    expect(html).not.toContain("Sem acesso ao orçamento");
  });
});

describe("PainelAutoAprovacaoRecusada", () => {
  it("explica a regra em vez de só negar, e não nomeia quem montou", () => {
    const html = renderToStaticMarkup(<PainelAutoAprovacaoRecusada />);

    expect(html).toContain("Acumular os dois papéis");
    expect(html).toContain("identidade e não de papel");
    expect(html).toContain("Nada foi gravado");
    expect(html).toContain('role="alert"');
    // O nome de quem montou não viaja na recusa, e a tela não o fabrica.
    expect(html).not.toContain("montado por");
  });
});

describe("PainelSemPapelDeAprovador", () => {
  it("nomeia o papel que falta e diz que nada foi gravado", () => {
    const html = renderToStaticMarkup(<PainelSemPapelDeAprovador />);

    expect(html).toContain("papel aprovador");
    expect(html).toContain("Nada foi gravado");
    expect(html).toContain('role="alert"');
    // Não é a tela de sem acesso à jornada: ela continua sendo lida.
    expect(html).not.toContain("Sem acesso ao orçamento");
  });
});

/**
 * Memória de cálculo na jornada do orçamento (F-038 T9, Design Approval Package, decisão
 * 3). Ela é o artefato que explica DE ONDE veio cada quantidade, e antes só existia na
 * medição — `calc_sheets` já chegava ao cliente e faltava mostrá-la. A fixture é a praça do
 * ADR-0053: o piso (`DERIVED`, geometria) e a parcela de limpeza (`PARTIAL`, declarada
 * dentro do piso), mais um serviço `DEPENDENT` que tira a quantidade de outro código.
 */
const MEMORIA_FIXTURE: readonly Estimate.CalcSheet[] = [
  {
    worksite_key: "praca-do-exemplo",
    item_number: "1",
    total_quantity: "418.12",
    blocks: [
      {
        label: "Piso em concreto",
        basis: "derived",
        recipe: "length_times_width",
        operands: [
          { name: "COMPRIMENTO", value: "20.906", unit: "m" },
          { name: "LARGURA", value: "20.00", unit: "m" },
        ],
        subtotal: "418.12",
      },
    ],
  },
  {
    worksite_key: "praca-do-exemplo",
    item_number: "2",
    total_quantity: "170.00",
    blocks: [
      {
        label: "Limpeza sobre o piso",
        basis: "partial",
        recipe: "declared_product",
        operands: [{ name: "AREA DECLARADA", value: "170.00", unit: "m2" }],
        subtotal: "170.00",
      },
    ],
  },
  {
    worksite_key: "praca-do-exemplo",
    item_number: "3",
    total_quantity: "8.36",
    blocks: [
      {
        label: "Transporte do material",
        basis: "dependent",
        derived_from_code: "BP04050350(/)",
        recipe: "declared_product",
        operands: [
          { name: "QUANTIDADE BP04050350(/)", value: "478.74" },
          { name: "MASSA", value: "0.02" },
        ],
        subtotal: "8.36",
      },
    ],
  },
];

describe("MemoriaDeCalculo", () => {
  it("mostra as parcelas, a receita e o subtotal recomputado pelo servidor", () => {
    const html = renderToStaticMarkup(
      <MemoriaDeCalculo calcSheets={MEMORIA_FIXTURE} />,
    );

    expect(html).toContain("Memória de cálculo");
    expect(html).toContain(AVISO_MEMORIA);
    // Cada serviço é um item numerado, com o total que o servidor recomputou.
    expect(html).toContain("Item 1");
    expect(html).toContain("Piso em concreto");
    expect(html).toContain("comprimento × largura");
    expect(html).toContain("418,12");
    // A tela não soma nem multiplica: o texto diz isso por extenso.
    expect(html).toContain("a tela não multiplica nem soma");
  });

  it("nomeia a base da parcela e a proveniência derivada por EXTENSO, não só por cor", () => {
    const html = renderToStaticMarkup(
      <MemoriaDeCalculo calcSheets={MEMORIA_FIXTURE} />,
    );

    // Decisão 5: parcela parcial e serviço derivado de outro são palavra, não veste.
    expect(html).toContain("parcela parcial declarada");
    expect(html).toContain("derivada da geometria");
    expect(html).toContain("derivada da quantidade de BP04050350(/)");
  });

  it("não inventa memória quando o orçamento ainda não foi montado", () => {
    const html = renderToStaticMarkup(<MemoriaDeCalculo calcSheets={[]} />);

    expect(html).toBe("");
  });

  it("omite a base quando o artefato é anterior à matriz (basis não declarada)", () => {
    const legado: readonly Estimate.CalcSheet[] = [
      {
        worksite_key: "praca-do-exemplo",
        item_number: "1",
        total_quantity: "10.00",
        blocks: [
          {
            label: "Serviço legado",
            recipe: "direct_quantity",
            operands: [{ name: "QUANTIDADE", value: "10.00" }],
            subtotal: "10.00",
          },
        ],
      },
    ];
    const html = renderToStaticMarkup(<MemoriaDeCalculo calcSheets={legado} />);

    expect(html).toContain("Serviço legado");
    // Ausência não afirma "espelho": nenhuma base é fabricada para o bloco legado.
    expect(html).not.toContain("espelho do elemento");
    expect(html).not.toContain("memoria-base");
  });
});

/** Um rascunho salvo de contribuição, para as fixtures do resumo da matriz. */
function contribuicao(over: Partial<CalcContributionDraft>): CalcContributionDraft {
  return {
    itemId: "ti_0000000000000001",
    code: "SCO001",
    itemQuantity: "418.12",
    label: "Piso em concreto",
    basis: "derived",
    recipe: "length_times_width",
    operands: [{ name: "COMPRIMENTO", value: "20.906", unit: "m" }],
    deductions: [],
    dependsOnCode: "",
    note: "",
    ...over,
  };
}

/**
 * Autoria da contribuição (F-038 "decisão 6", painéis A1–A2/B1–B2 do mock). O editor pede a
 * base, a grandeza e os operandos; a parcela PARCIAL pede nota e mostra o teto do elemento.
 * Nada nasce pré-marcado (decisão 4) e a base é dita por extenso (decisão 5).
 */
describe("AutoriaDeContribuicao", () => {
  const noop = () => undefined;

  function render(
    form: CalcContributionForm,
    over: Partial<Parameters<typeof AutoriaDeContribuicao>[0]> = {},
  ): string {
    return renderToStaticMarkup(
      <AutoriaDeContribuicao
        code="SCO001"
        itemUnit="m2"
        itemQuantity="418.12"
        form={form}
        erro={null}
        codigosDisponiveis={["SCO478", "SCO001"]}
        onChange={noop}
        onSalvar={noop}
        onCancelar={noop}
        submitting={false}
        {...over}
      />,
    );
  }

  it("oferece as grandezas e as bases por extenso, nada pré-marcado", () => {
    const html = render(emptyContributionForm("Piso em concreto"));

    // Grandezas (receitas) em língua de obra.
    expect(html).toContain("comprimento × largura");
    expect(html).toContain("perímetro × altura menos vãos");
    // Bases por extenso, não só cor.
    expect(html).toContain("parcela parcial declarada");
    expect(html).toContain("derivada de outro serviço");
    // Placeholder de "escolha": a base começa vazia.
    expect(html).toContain("Escolha de onde vem a parcela…");
  });

  it("na parcela PARCIAL mostra o teto do elemento e pede a justificativa", () => {
    const html = render({
      ...emptyContributionForm("Limpeza sobre o piso"),
      basis: "partial",
    });

    // O teto (quantidade do elemento) aparece por extenso, com a unidade.
    expect(html).toContain("Teto desta parcela");
    expect(html).toContain("418,12");
    // A nota é obrigatória e a regra é dita.
    expect(html).toContain("Justificativa da parcela (obrigatória)");
    expect(html).toContain("dentro do teto do elemento");
  });

  it("na parcela DEPENDENT oferece o serviço de origem, menos o próprio código", () => {
    const html = render({
      ...emptyContributionForm("Transporte"),
      basis: "dependent",
    });

    expect(html).toContain("Depende de qual serviço");
    expect(html).toContain('value="SCO478"');
    // O próprio código não é opção de origem (evita a auto-referência já na tela).
    expect(html).not.toContain('value="SCO001"');
  });

  it("mostra a recusa da validação como alerta ao lado do editor", () => {
    const html = render(emptyContributionForm("Piso"), {
      erro: "A parcela precisa de um rótulo — é o texto que aparece na memória de cálculo.",
    });

    expect(html).toContain('role="alert"');
    expect(html).toContain("texto que aparece na memória");
  });
});

/**
 * Resumo da matriz (F-038 "decisão 6", painéis A3–A5/C1–C5 do mock): a ordem topológica de
 * cálculo, o serviço que funde parcelas de vários elementos, e a recusa de ciclo/auto-
 * referência escrita por extenso — nunca escondida atrás de interação (decisão 5).
 */
describe("ResumoDaMatriz", () => {
  it("declara o regime legado quando não há contribuição autorada (C4/vazio)", () => {
    const html = renderToStaticMarkup(<ResumoDaMatriz matrix={null} />);
    expect(html).toContain(RESUMO_MATRIZ_VAZIO);
  });

  it("numera a ordem de cálculo com o dependente depois da origem (A3)", () => {
    const matrix = assembleCalcMatrix([
      contribuicao({
        code: "TR01",
        label: "Transporte",
        basis: "dependent",
        recipe: "declared_product",
        dependsOnCode: "SCO478",
        operands: [{ name: "MASSA", value: "0.02", unit: "" }],
      }),
      contribuicao({ code: "SCO478", label: "Saibro" }),
    ]);
    const html = renderToStaticMarkup(<ResumoDaMatriz matrix={matrix} />);

    // A origem vem primeiro (1.), o dependente depois (2.).
    const posSaibro = html.indexOf("SCO478");
    const posTransporte = html.indexOf("TR01");
    expect(posSaibro).toBeGreaterThanOrEqual(0);
    expect(posSaibro).toBeLessThan(posTransporte);
    expect(html).toContain("derivada da quantidade de SCO478");
  });

  it("diz por extenso que um serviço funde parcelas de vários elementos (C3/saibro)", () => {
    const matrix = assembleCalcMatrix([
      contribuicao({
        code: "SCO478",
        itemId: "ti_0000000000000001",
        label: "Saibro trecho 1",
      }),
      contribuicao({
        code: "SCO478",
        itemId: "ti_0000000000000002",
        label: "Saibro trecho 2",
      }),
    ]);
    const html = renderToStaticMarkup(<ResumoDaMatriz matrix={matrix} />);

    expect(html).toContain("funde parcelas de 2 elementos");
  });

  it("recusa o ciclo por extenso, com os códigos, nunca escondido (A4)", () => {
    const matrix = assembleCalcMatrix([
      contribuicao({
        code: "A",
        basis: "dependent",
        recipe: "declared_product",
        dependsOnCode: "B",
        operands: [{ name: "X", value: "1", unit: "" }],
      }),
      contribuicao({
        code: "B",
        basis: "dependent",
        recipe: "declared_product",
        dependsOnCode: "A",
        operands: [{ name: "Y", value: "1", unit: "" }],
      }),
    ]);
    const html = renderToStaticMarkup(<ResumoDaMatriz matrix={matrix} />);

    expect(html).toContain('role="alert"');
    expect(html).toContain("dependência cíclica");
    expect(html).toContain("(A, B)");
  });

  it("recusa a auto-referência por extenso (A4)", () => {
    const matrix = assembleCalcMatrix([
      contribuicao({
        code: "A",
        basis: "dependent",
        recipe: "declared_product",
        dependsOnCode: "A",
        operands: [{ name: "X", value: "1", unit: "" }],
      }),
    ]);
    const html = renderToStaticMarkup(<ResumoDaMatriz matrix={matrix} />);

    expect(html).toContain('role="alert"');
    expect(html).toContain("não pode derivar de si mesmo");
  });
});

/**
 * A guarda que o lote atômico exige da tela: item já decidido não entra na anotação.
 * Sem ela, uma linha já revisada derrubaria com ela todas as outras decisões do ato —
 * o servidor recusa o lote inteiro (`TAKEOFF_ITEM_ALREADY_REVIEWED`), não só a linha.
 */
describe("itemJaRevisado", () => {
  const item = (status: string): Parameters<typeof itemJaRevisado>[0] =>
    ({ status }) as Parameters<typeof itemJaRevisado>[0];

  it("item já decidido não pode ser anotado de novo", () => {
    expect(itemJaRevisado(item("confirmed"))).toBe(true);
    expect(itemJaRevisado(item("rejected"))).toBe(true);
  });

  it("item pendente — proposto ou ambíguo — é justamente o que se decide", () => {
    expect(itemJaRevisado(item("proposed"))).toBe(false);
    expect(itemJaRevisado(item("ambiguous"))).toBe(false);
  });

  it("sem item selecionado não há o que anotar, e nada é bloqueado por engano", () => {
    expect(itemJaRevisado(null)).toBe(false);
  });
});

/** Item da legenda, no mínimo que a linha lê. */
const itemDaLegenda = (
  id: string,
  status: string,
  quantity: string | null = "418.12",
): Parameters<typeof ItemDaLegenda>[0]["item"] =>
  ({
    id,
    label: "PISO EM CONCRETO",
    quantity,
    unit: "m2",
    status,
    anchor: "registered",
  }) as unknown as Parameters<typeof ItemDaLegenda>[0]["item"];

const linha = (
  item: Parameters<typeof ItemDaLegenda>[0]["item"],
  marcado = false,
): string =>
  renderToStaticMarkup(
    <ItemDaLegenda
      item={item}
      numero={1}
      selecionado={false}
      anotado={false}
      marcado={marcado}
      onSelecionar={() => {}}
      onAlternarMarcado={() => {}}
    />,
  );

/**
 * Marcar é ato por item: nada nasce marcado, e "confirmar tudo" não existe. Quem não pode
 * entrar na marcação em massa diz POR QUÊ, em texto — caixa cinzenta sem explicação é a
 * tela recusando em silêncio.
 */
describe("ItemDaLegenda", () => {
  it("a caixa de seleção nasce desmarcada", () => {
    const html = linha(itemDaLegenda("i1", "proposed"));

    expect(html).toContain('type="checkbox"');
    expect(html).not.toContain("checked");
    expect(html).not.toContain("disabled");
  });

  it("a caixa diz o que marca, para quem navega por leitor de tela", () => {
    expect(linha(itemDaLegenda("i1", "proposed"))).toContain(
      'aria-label="Marcar PISO EM CONCRETO para confirmar em lote"',
    );
  });

  it("marcado só quando a tela manda; o componente não decide por conta própria", () => {
    expect(linha(itemDaLegenda("i1", "proposed"), true)).toContain("checked");
  });

  it("item já revisado tem a caixa desabilitada E o motivo em texto", () => {
    const html = linha(itemDaLegenda("i2", "confirmed"));

    expect(html).toContain("disabled");
    expect(html).toContain(AVISO_ITEM_JA_REVISADO);
  });

  it("item ambíguo fica fora do lote em massa, com a razão própria dele", () => {
    const html = linha(itemDaLegenda("i3", "ambiguous", null));

    expect(html).toContain("disabled");
    expect(html).toContain(AVISO_AMBIGUO_FORA_DO_LOTE);
  });

  /** A caixa fora do botão é o que impede marcar de arrastar o desenho junto. */
  it("a caixa de seleção não mora dentro do botão que seleciona o item", () => {
    const html = linha(itemDaLegenda("i1", "proposed"));
    const caixa = html.indexOf('type="checkbox"');
    const botao = html.indexOf('class="item-botao"');

    expect(caixa).toBeGreaterThan(-1);
    expect(botao).toBeGreaterThan(caixa);
  });
});

/**
 * "Marcado", "anotado" e "gravado" são três estados do mundo. O painel do lote é onde a
 * tela os distingue — por isso ele existe mesmo vazio, e por isso vazio ele não oferece
 * gravar: não há o que gravar.
 */
describe("PainelDoLote", () => {
  const anotacao = (itemId: string) =>
    ({ itemId, action: "confirm" }) as Parameters<typeof PainelDoLote>[0]["lote"][number];

  it("aparece com zero anotações e explica que anotar não é gravar", () => {
    const html = renderToStaticMarkup(
      <PainelDoLote
        lote={[]}
        itens={[]}
        submitting={false}
        onRemover={() => {}}
        onGravar={() => {}}
        onDescartar={() => {}}
      />,
    );

    expect(html).toContain("Nenhuma decisão anotada ainda");
    expect(html).toContain(DICA_LOTE_VAZIO);
    // Sem anotação não há ato a gravar nem a descartar, e botão que não faz nada convida
    // a achar que fez.
    expect(html).not.toContain("Gravar");
    expect(html).not.toContain("Descartar");
  });

  it("com anotações, conta quantas são e oferece o ato atômico", () => {
    const html = renderToStaticMarkup(
      <PainelDoLote
        lote={[anotacao("i1"), anotacao("i2"), anotacao("i3")]}
        itens={[itemDaLegenda("i1", "proposed")]}
        submitting={false}
        onRemover={() => {}}
        onGravar={() => {}}
        onDescartar={() => {}}
      />,
    );

    expect(html).toContain("3 decisões anotadas");
    expect(html).toContain("Gravar 3 decisões");
    expect(html).toContain("Descartar anotações");
    // O rótulo do item vem do pacote; o que não está na lista aparece pelo id, nunca
    // fabricado.
    expect(html).toContain("PISO EM CONCRETO");
    expect(html).toContain("i2");
  });

  it("uma anotação fala no singular", () => {
    const html = renderToStaticMarkup(
      <PainelDoLote
        lote={[anotacao("i1")]}
        itens={[]}
        submitting={false}
        onRemover={() => {}}
        onGravar={() => {}}
        onDescartar={() => {}}
      />,
    );

    expect(html).toContain("1 decisão anotada");
    expect(html).toContain("Gravar 1 decisão");
  });
});

/**
 * O bloco da aba "Códigos" que diz o que a shortlist custa e qual delas está na tela
 * (F-041, ADR-0054). Render puro: nada aqui chama a API, e o `matching` vem sempre da
 * resposta do servidor — a tela nunca o deduz.
 */
describe("EstadoDoBracoSemantico", () => {
  it("mostra os DOIS custos, e não afirma mais que nenhum provider é chamado", () => {
    const html = renderToStaticMarkup(
      <EstadoDoBracoSemantico matching={null} notas={[]} />,
    );

    expect(html).not.toContain("Nenhum provider é chamado");
    expect(html).toContain("Ler a shortlist não chama provider nenhum");
    expect(html).toContain("Recalcular é ato à parte e pode ser chamada paga");
  });

  /** Sem shortlist lida não há braço a nomear: a tela não inventa um estado. */
  it("não nomeia braço nenhum antes da primeira leitura", () => {
    const html = renderToStaticMarkup(
      <EstadoDoBracoSemantico matching={null} notas={[]} />,
    );

    expect(html).not.toContain("Esta shortlist é");
  });

  /** Criterio 2: dá para ver, em texto, qual das duas está diante da pessoa. */
  it("declara em palavra se a shortlist na tela é léxica ou híbrida", () => {
    const lexical = renderToStaticMarkup(
      <EstadoDoBracoSemantico matching="lexical" notas={[]} />,
    );
    const hibrida = renderToStaticMarkup(
      <EstadoDoBracoSemantico matching="hybrid" notas={[]} />,
    );

    expect(lexical).toContain("Esta shortlist é léxica");
    expect(hibrida).toContain("Esta shortlist é híbrida");
    expect(hibrida).toContain("ao menos uma fonte");
  });

  /**
   * As notas chegam prontas do servidor, nomeando a fonte que ficou sem índice. A tela as
   * exibe COMO VIERAM — reescrevê-las aqui faria a tela discordar de quem calculou.
   */
  it("mostra as notas do servidor como vieram, com um título por cima", () => {
    const html = renderToStaticMarkup(
      <EstadoDoBracoSemantico
        matching="hybrid"
        notas={[
          "braço semântico indisponível: fonte 2 (emop) sem índice de embeddings publicado",
        ]}
      />,
    );

    expect(html).toContain("Onde o braço semântico não entrou");
    expect(html).toContain(
      "braço semântico indisponível: fonte 2 (emop) sem índice de embeddings publicado",
    );
  });

  /** Sem nota, não há título de lista vazia ocupando espaço. */
  it("não põe título quando o servidor não mandou nota nenhuma", () => {
    const html = renderToStaticMarkup(
      <EstadoDoBracoSemantico matching="hybrid" notas={[]} />,
    );

    expect(html).not.toContain("Onde o braço semântico não entrou");
    expect(html).not.toContain("<ul");
  });
});

/**
 * O acervo de parcelas de canteiro (F-042, pacote de design revisão 1 aprovado em
 * 2026-08-28). Das 43 linhas do documento real, 24 não têm origem nenhuma na prancha; o
 * que estes testes guardam são as decisões que impedem essa aceleração de virar planilha
 * que ninguém revisou.
 */
const KIT_DO_CANTEIRO: SiteSetupKit = {
  kit_id: "kit-canteiro-smh",
  name: "Canteiro — contrato SMH/Rio",
  kit_version: "sco-site-setup-v1",
  origin: "platform",
  source_label: "acervo da plataforma",
  parcel_count: 3,
  parameters: [
    { name: "prazo de obra", unit: "mes", cited_by: 6 },
    { name: "semiperímetro", unit: "m", cited_by: 2 },
  ],
  created_at: "2026-08-12T10:00:00Z",
};

const PREVIA_DO_CANTEIRO: SiteSetupPreviewResponse = {
  round_id: "round-1",
  version: 7,
  kit_id: KIT_DO_CANTEIRO.kit_id,
  kit_version: "sco-site-setup-v1",
  rows: [
    {
      parcel_id: "p1",
      code: "AC01100010",
      label: "Aluguel de banheiro químico",
      operands: [
        { name: "UNIDADES", value: "1", unit: "un", parameter: null },
        { name: "PRAZO", value: "2", unit: "mes", parameter: "prazo de obra" },
      ],
      quantity: "2.00",
      missing_parameters: [],
      code_absent: false,
    },
    {
      parcel_id: "p2",
      code: "AC02200030",
      label: "Vigia diurno",
      operands: [
        { name: "DIAS", value: "23", unit: null, parameter: "dias de vigia" },
        { name: "HORAS", value: "12", unit: "h", parameter: null },
      ],
      quantity: "276.00",
      missing_parameters: [],
      code_absent: false,
    },
  ],
  excluded_parcel_ids: [],
  blocked_parcel_ids: [],
};

/**
 * A prévia que MARCA em vez de recusar (emenda de 2026-08-28 à decisão 5): duas parcelas
 * não podem nascer — uma por parâmetro não declarado, outra por código fora do catálogo —,
 * e as demais continuam calculadas, à espera da remoção que destrava o ato.
 */
const PREVIA_COM_BLOQUEIO: SiteSetupPreviewResponse = {
  ...PREVIA_DO_CANTEIRO,
  rows: [
    PREVIA_DO_CANTEIRO.rows[0],
    {
      ...PREVIA_DO_CANTEIRO.rows[1],
      operands: [
        { name: "SEMIPERÍMETRO", value: null, unit: "m", parameter: "semiperímetro" },
        {
          name: "ALTURA",
          value: null,
          unit: "m",
          parameter: "altura do alambrado",
        },
      ],
      quantity: null,
      missing_parameters: ["semiperímetro", "altura do alambrado"],
    },
    // Código ausente vem COM quantidade: a conta fecha, e o que falta é o código no
    // catálogo desta rodada. A linha mostra o MOTIVO no lugar do número — a parcela não
    // vai nascer, e imprimir a quantidade dela sugeriria o contrário.
    {
      parcel_id: "p3",
      code: "AC03100050",
      label: "Placa de obra",
      operands: [{ name: "ÁREA", value: "6", unit: "m2", parameter: null }],
      quantity: "6.00",
      missing_parameters: [],
      code_absent: true,
    },
  ],
  blocked_parcel_ids: ["p2", "p3"],
};

function fluxoNoPasso(passo: "acervo" | "parametros" | "previa"): FluxoDoAcervo {
  const escolhido = escolherAcervo(fluxoInicial(), KIT_DO_CANTEIRO.kit_id);
  if (passo === "acervo") {
    return escolhido;
  }
  const comCampos = avancarParaParametros(escolhido, KIT_DO_CANTEIRO);
  if (passo === "parametros") {
    return comCampos;
  }
  return receberPrevia(comCampos, PREVIA_DO_CANTEIRO);
}

describe("FormularioDoAcervo", () => {
  const noop = () => undefined;

  function render(
    fluxo: FluxoDoAcervo,
    over: Partial<Parameters<typeof FormularioDoAcervo>[0]> = {},
  ): string {
    return renderToStaticMarkup(
      <FormularioDoAcervo
        kits={[KIT_DO_CANTEIRO]}
        fluxo={fluxo}
        recusa={null}
        submitting={false}
        onEscolher={noop}
        onAvancar={noop}
        onParametro={noop}
        onPreVisualizar={noop}
        onVoltar={noop}
        onAlternar={noop}
        onAplicar={noop}
        onCancelar={noop}
        {...over}
      />,
    );
  }

  /**
   * O ponto inegociável: um "aplicar tudo" ao lado da escolha destruiria o controle do
   * risco declarado na feature, e por isso ele não existe em passo nenhum antes da prévia.
   */
  it("não oferece aplicar no passo 1 nem no passo 2", () => {
    const passo1 = render(fluxoNoPasso("acervo"));
    expect(passo1).toContain("Continuar");
    expect(passo1).not.toContain("Aplicar 2");
    expect(passo1).not.toContain("Aplicar as");

    const passo2 = render(fluxoNoPasso("parametros"));
    expect(passo2).toContain("Pré-visualizar as parcelas");
    expect(passo2).not.toContain("Aplicar 2");
  });

  it("no passo 1 mostra a versão do acervo, que é parte da identidade dele", () => {
    const html = render(fluxoNoPasso("acervo"));

    expect(html).toContain("Canteiro — contrato SMH/Rio");
    expect(html).toContain("versão sco-site-setup-v1");
    // Escolhido dito por extenso, não só pela borda do cartão.
    expect(html).toContain("escolhido");
    expect(html).toContain(ACERVO_E_RECEITA);
  });

  /** Decisão 4: campo nasce vazio, com a unidade e o peso do que está sendo declarado. */
  it("no passo 2 os campos nascem vazios, com unidade e quantas parcelas citam", () => {
    const html = render(fluxoNoPasso("parametros"));

    expect(html).toContain("prazo de obra");
    expect(html).toContain("citado por 6 parcelas");
    expect(html).toContain("semiperímetro");
    expect(html).toContain("citado por 2 parcelas");
    // Nenhum valor pré-preenchido: todo campo do passo 2 está vazio.
    expect(html).toContain('value=""');
    expect(html).not.toContain('value="2"');
    expect(html).toContain("não preenche nenhum sozinho");
  });

  /** Decisão 3: a prévia mostra a CONTA — os operandos nomeados —, não só a quantidade. */
  it("no passo 3 mostra os operandos nomeados de cada parcela, não só a quantidade", () => {
    const html = render(fluxoNoPasso("previa"));

    expect(html).toContain("UNIDADES 1 un × PRAZO 2 mes");
    expect(html).toContain("DIAS 23 × HORAS 12 h");
    expect(html).toContain("276,00");
    expect(html).toContain("Aplicar 2 parcelas");
  });

  it("a recusa que nomeia os faltantes marca os campos e não aplica nada", () => {
    const html = render(fluxoNoPasso("parametros"), {
      recusa: {
        parametros: ["prazo de obra", "semiperímetro"],
        codigos: [],
        mensagem: fraseParametrosFaltantes(["prazo de obra", "semiperímetro"]),
      },
    });

    expect(html).toContain('role="alert"');
    expect(html).toContain("Nada foi aplicado");
    expect(html).toContain("prazo de obra e semiperímetro");
    // Os dois campos marcados, e a falta dita ao lado — não só pela borda.
    expect(html).toContain('aria-invalid="true"');
    expect(html).toContain("falta declarar");
  });

  it("a recusa do código ausente nomeia o código", () => {
    const html = render(fluxoNoPasso("parametros"), {
      recusa: {
        parametros: [],
        codigos: ["AC03100050"],
        mensagem: fraseCodigosAusentes(["AC03100050"]),
      },
    });

    expect(html).toContain("AC03100050");
    expect(html).toContain("Nada foi aplicado");
  });

  /** Decisão 6: a removida sai da conta, não da tela — e volta com um clique. */
  it("a parcela removida continua visível, dita removida, e as demais não mudam", () => {
    const html = render({
      ...fluxoNoPasso("previa"),
      excluidos: ["p1"],
    });

    expect(html).toContain("Aluguel de banheiro químico");
    expect(html).toContain("acervo-linha-removida");
    // "Removida" por extenso, além do risco na fonte.
    expect(html).toContain("removida");
    expect(html).toContain(ACERVO_PARCELA_NAO_NASCE);
    expect(html).toContain(ACERVO_TEXTO_TRAZER_DE_VOLTA);
    // A que ficou continua com a conta e a quantidade intactas.
    expect(html).toContain("DIAS 23 × HORAS 12 h");
    expect(html).toContain("276,00");
    expect(html).toContain("1 será aplicada");
    expect(html).toContain("1 removida");
    expect(html).toContain("Aplicar 1 parcela");
  });

  /**
   * A linha BLOQUEADA, e a saída que ela abre. A recusa antiga era um beco sem saída: ela
   * prometia "remova na pré-visualização as parcelas que os citam" e acontecia antes de
   * existir pré-visualização onde remover.
   */
  it("a linha bloqueada diz o que falta, nomeando, e continua removível", () => {
    const html = render({
      ...fluxoNoPasso("previa"),
      previa: PREVIA_COM_BLOQUEIO,
    });

    // No lugar da quantidade, o que falta — por extenso e nomeando os dois parâmetros.
    expect(html).toContain("falta declarar semiperímetro e altura do alambrado");
    expect(html).toContain("código fora do catálogo desta rodada");
    // Não é só a veste da linha: o estado vai escrito no selo.
    expect(html).toContain("acervo-linha-bloqueada");
    expect(html).toContain("não pode nascer");
    // O operando sem valor é dito ausente, nunca mostrado como zero.
    expect(html).toContain(`SEMIPERÍMETRO ${ACERVO_OPERANDO_NAO_DECLARADO}`);
    // A bloqueada continua removível: é isso que destrava o ato.
    expect(html.match(/Remover</g) ?? []).toHaveLength(3);
    expect(html).toContain("1 será aplicada");
    expect(html).toContain("2 bloqueadas");
    // A bloqueada por CÓDIGO tem quantidade calculada, e ainda assim o que a célula diz é
    // o motivo: ela não vai nascer, e o número sugeriria o contrário.
    expect(html).not.toContain("6,00");
  });

  /** O motivo vai ao LADO do controle: indisponível e mudo é o que não pode acontecer. */
  it("aplicar indisponível traz o motivo nomeado, não só o botão apagado", () => {
    const html = render({
      ...fluxoNoPasso("previa"),
      previa: PREVIA_COM_BLOQUEIO,
    });

    expect(html).toContain('role="alert"');
    expect(html).toContain(
      fraseAplicarBloqueado(
        2,
        ["semiperímetro", "altura do alambrado"],
        ["AC03100050"],
      ),
    );
    expect(html).toContain("remova essas parcelas");
    const aplicar = html.match(/<button[^>]*>Aplicar 1 parcela</)?.[0] ?? "";
    expect(aplicar).not.toBe("");
    expect(aplicar).toContain("disabled");
  });

  /** **O teste do defeito corrigido**: remover as bloqueadas destrava o aplicar. */
  it("removidas as bloqueadas, o ato fica disponível e o motivo some", () => {
    const html = render({
      ...fluxoNoPasso("previa"),
      previa: PREVIA_COM_BLOQUEIO,
      excluidos: ["p2", "p3"],
    });

    const aplicar = html.match(/<button[^>]*>Aplicar 1 parcela</)?.[0] ?? "";
    expect(aplicar).not.toBe("");
    expect(aplicar).not.toContain("disabled");
    expect(html).not.toContain("não podem nascer");
    // As removidas continuam na tela, riscadas — elas saem da conta, não da lista.
    expect(html).toContain("Placa de obra");
    expect(html).toContain(ACERVO_TEXTO_TRAZER_DE_VOLTA);
  });

  it("com todas removidas o ato fica indisponível — não há o que aplicar", () => {
    const html = render({
      ...fluxoNoPasso("previa"),
      excluidos: ["p1", "p2"],
    });

    expect(html).toContain("Aplicar 0 parcelas");
    // A asserção é sobre O BOTÃO de aplicar: `toContain("disabled")` na marcação inteira
    // passaria por causa de qualquer outro controle desabilitado da prévia.
    const aplicar = html.match(/<button[^>]*>Aplicar 0 parcelas</)?.[0] ?? "";
    expect(aplicar).not.toBe("");
    expect(aplicar).toContain("disabled");
  });
});

describe("PainelParcelasDeCanteiro", () => {
  const doAcervo = contribuicoesDoAcervo(
    KIT_DO_CANTEIRO,
    PREVIA_DO_CANTEIRO,
    PREVIA_DO_CANTEIRO.rows,
  );
  const aMao: CalcContributionDraft = {
    itemId: "entulho-extra",
    code: "AC09900001",
    itemQuantity: null,
    label: "Entulho — caçamba extra",
    basis: "standalone",
    recipe: "declared_product",
    operands: [{ name: "CAÇAMBAS", value: "3", unit: "un" }],
    deductions: [],
    dependsOnCode: "",
    note: "",
  };

  it("declara o estado vazio sem inventar parcela nenhuma", () => {
    const html = renderToStaticMarkup(
      <PainelParcelasDeCanteiro
        parcelas={[]}
        aplicacao={null}
        aviso={null}
        onAplicarAcervo={() => undefined}
        submitting={false}
      />,
    );

    expect(html).toContain("nenhuma parcela nesta rodada");
    expect(html).toContain("Aplicar um acervo");
    expect(html).not.toContain("276,00");
  });

  /** Decisão 7: o que distingue a origem é o TEXTO do selo, nunca a cor. */
  it("distingue a parcela do acervo da autorada à mão por texto", () => {
    const html = renderToStaticMarkup(
      <PainelParcelasDeCanteiro
        parcelas={[...doAcervo, aMao]}
        aplicacao={null}
        aviso={null}
        onAplicarAcervo={() => undefined}
        submitting={false}
      />,
    );

    expect(html).toContain("do acervo sco-site-setup-v1");
    expect(html).toContain("autorada à mão");
    // A quantidade exibida é a string que o servidor computou.
    expect(html).toContain("276,00");
    // A autorada à mão não ganha quantidade fabricada: quem a computa é o servidor.
    expect(html).toContain(CANTEIRO_QUANTIDADE_NA_MONTAGEM);
  });

  it("o carimbo mostra os parâmetros da última aplicação e diz que não pré-preenche", () => {
    const html = renderToStaticMarkup(
      <PainelParcelasDeCanteiro
        parcelas={doAcervo}
        aplicacao={{
          kitId: KIT_DO_CANTEIRO.kit_id,
          kitName: KIT_DO_CANTEIRO.name,
          kitVersion: "sco-site-setup-v1",
          parametros: { "prazo de obra": "2", "semiperímetro": "132.21" },
          parcelas: 2,
          appliedAt: "2026-08-28T14:02:00Z",
        }}
        aviso={null}
        onAplicarAcervo={() => undefined}
        submitting={false}
      />,
    );

    expect(html).toContain("prazo de obra 2");
    expect(html).toContain("semiperímetro 132,21");
    expect(html).toContain("começa com os campos vazios");
    expect(html).toContain(ACERVO_REAPLICAR_SUBSTITUI);
    // Com acervo já aplicado, o ato oferecido é reaplicar.
    expect(html).toContain("Reaplicar um acervo");
  });

  /**
   * Depois de um recarregamento não há aplicação NESTA sessão, e o carimbo possível é o do
   * que está gravado: a matriz diz a versão do acervo e a parcela, e não diz mais. O nome
   * do acervo não é deduzido para preencher a lacuna.
   */
  it("sem aplicação na sessão, carimba o que está GRAVADO: versão e contagem", () => {
    const hidratadas = disassembleCalcMatrix(
      assembleCalcMatrix(doAcervo),
    );
    const html = renderToStaticMarkup(
      <PainelParcelasDeCanteiro
        parcelas={hidratadas}
        aplicacao={null}
        aviso={null}
        onAplicarAcervo={() => undefined}
        submitting={false}
      />,
    );

    expect(html).toContain(
      "Do que está gravado nesta rodada: 2 parcelas do acervo sco-site-setup-v1",
    );
    expect(html).toContain(CANTEIRO_GRAVADO_DICA);
    expect(html).toContain(ACERVO_REAPLICAR_SUBSTITUI);
    // O selo continua distinguindo por texto, com a versão que a matriz afirma.
    expect(html).toContain("do acervo sco-site-setup-v1");
    // Nenhum nome de acervo inventado, e nenhum parâmetro fabricado.
    expect(html).not.toContain("Canteiro — contrato SMH/Rio");
    expect(html).not.toContain("prazo de obra");
  });

  /** Falha de leitura não some em silêncio, e não esconde o resto da etapa. */
  it("declara a falha de leitura do acervo em vez de ficar calado", () => {
    const html = renderToStaticMarkup(
      <PainelParcelasDeCanteiro
        parcelas={[]}
        aplicacao={null}
        aviso="A lista não pôde ser lida."
        onAplicarAcervo={null}
        submitting={false}
      />,
    );

    expect(html).toContain('role="alert"');
    expect(html).toContain("A lista não pôde ser lida.");
    // Sem acervo a aplicar, nenhum botão inerte é desenhado.
    expect(html).not.toContain("Aplicar um acervo");
  });
});

/**
 * A escolha do gabarito no despacho (F-043 T3, estado 02 do pacote aprovado).
 *
 * Render estático: o que se prova é o que a orçamentista lê antes de gerar o arquivo.
 */
function gabaritoDeTeste(
  overrides: Partial<GabaritoOption> = {},
): GabaritoOption {
  return {
    estimate_template_id: "01930000-0000-7000-8000-0000000000a1",
    name: "PLANILHA ORÇAMENTÁRIA — SMH/Rio",
    template_version: "2023-10",
    origin: "platform",
    source_label: "Prefeitura sintética",
    sheet_name: "PLANILHA ORÇAMENTÁRIA",
    memory_sheet_name: "MEMÓRIA DE CÁLCULO",
    row_count: 433,
    priced_row_count: 43,
    document_sha256: "a".repeat(64),
    ...overrides,
  };
}

describe("a escolha do gabarito no despacho", () => {
  it("sem gabarito no acervo, a superfície inteira não aparece", () => {
    const html = renderToStaticMarkup(
      <EscolhaDoGabarito gabaritos={[]} escolhido="" onEscolher={() => {}} />,
    );

    expect(html).toBe("");
  });

  it("oferece “sem gabarito” como opção, e não como ausência", () => {
    const html = renderToStaticMarkup(
      <EscolhaDoGabarito
        gabaritos={[gabaritoDeTeste()]}
        escolhido=""
        onEscolher={() => {}}
      />,
    );

    expect(html).toContain("Sem gabarito");
    expect(html).toContain("na ordem do próprio orçamento");
    // Nada escolhido: nem aviso de revisão, nem resumo do arquivo.
    expect(html).not.toContain("O que vai no arquivo");
    expect(html).not.toContain("revisão aceita");
  });

  it("a revisão aparece no seletor, junto do nome", () => {
    const html = renderToStaticMarkup(
      <EscolhaDoGabarito
        gabaritos={[gabaritoDeTeste()]}
        escolhido=""
        onEscolher={() => {}}
      />,
    );

    expect(html).toContain("rev. 2023-10");
    expect(html).toContain("433 linhas");
  });

  it("escolhido, mostra o aviso de revisão e o que vai no arquivo", () => {
    const html = renderToStaticMarkup(
      <EscolhaDoGabarito
        gabaritos={[gabaritoDeTeste()]}
        escolhido="01930000-0000-7000-8000-0000000000a1"
        onEscolher={() => {}}
      />,
    );

    expect(html).toContain("2023-10");
    expect(html).toContain("quem entrega à prefeitura");
    expect(html).toContain("O que vai no arquivo");
    expect(html).toContain("433 no gabarito");
    expect(html).toContain("43 com preço declarado");
    expect(html).toContain("MEMÓRIA DE CÁLCULO");
    // O aviso é lido por leitor de tela, não só visto.
    expect(html).toContain('role="status"');
  });

  it("diz que a revisão é impressa dentro do arquivo", () => {
    const html = renderToStaticMarkup(
      <EscolhaDoGabarito
        gabaritos={[gabaritoDeTeste()]}
        escolhido="01930000-0000-7000-8000-0000000000a1"
        onEscolher={() => {}}
      />,
    );

    expect(html).toContain("dentro");
    expect(html).toContain("fora do sistema");
  });
});
