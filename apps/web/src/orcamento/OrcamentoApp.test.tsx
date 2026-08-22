import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import type { User } from "oidc-client-ts";

import {
  BannerOrcamentoMudou,
  BlocoConsumoDoTeto,
  FaixaTetoEstourado,
  LinhaTetoDaRodada,
  OrcamentoApp,
  PainelEscolhaDeFonte,
  PainelRegimeDaRodada,
  PainelSemAcesso,
  PainelTetoDaVerba,
  SeloFonte,
  SeloProcedencia,
  SeloRegime,
  SemPrecoNaCascata,
  TelaAuditoriaReprovada,
} from "./OrcamentoApp";
import {
  AVISO_ACERVO_FILTRADO,
  AVISO_ORCAMENTO,
  origensAceitasNaCascata,
} from "./labels";
import type { ReferenceCatalogOption } from "./api";
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
   * A linha fixa que declara o momento da jornada é decisão do pacote aprovado, e ela diz
   * as duas coisas que a confusão medição × orçamento custou: de onde vem o preço, e até
   * onde ele não vai.
   */
  it("declara o momento da jornada na linha fixa, inclusive sem sessão", () => {
    const html = renderToStaticMarkup(<OrcamentoApp session={null} />);

    expect(html).toContain(AVISO_ORCAMENTO);
    expect(html).toContain("pré-licitação");
    expect(html).toContain("nenhum preço daqui alcança um boletim de medição");
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

    expect(html).toContain("nada foi publicado");
    expect(html).toContain("O arquivo foi descartado");
    expect(html).toContain("o orçamento continua exatamente como estava");
    expect(html).toContain("CELL_VALUE_MISMATCH");
    expect(html).toContain('role="alert"');
    // Nenhum valor de célula: preço e quantidade do cliente não saem em mensagem de erro.
    expect(html).not.toContain("R$");
    expect(html).not.toContain("previsto");
    expect(html).not.toContain("encontrado");
  });

  it("sem lista de achados, continua sendo a tela — e não fabrica achado", () => {
    const html = renderToStaticMarkup(<TelaAuditoriaReprovada findings={[]} />);

    expect(html).toContain("nada foi publicado");
    expect(html).not.toContain("<li");
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
 * não é um valor, é a falta dele — e nada no primeiro render fala de contrato.
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
