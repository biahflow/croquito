import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import type { User } from "oidc-client-ts";

import type {
  JourneyAvailability,
  JourneyEntitlement,
  PlatformTenant,
  ReferenceCatalog,
  ReferenceCatalogIndex,
} from "./api";
import {
  AcervoDeCatalogos,
  AlertaPersistente,
  ColunaDoAmbiente,
  DisponibilidadeDeJornada,
  EstadoDasJornadas,
  FormularioDeAutorizacao,
  FormularioDePublicacao,
  FormularioDePublicacaoDeIndice,
  IndicesDeEmbeddings,
  LinhaAutorizacao,
  LinhaCatalogo,
  LinhaIndice,
  LinhaTenant,
  PlatformApp,
} from "./PlatformApp";

/**
 * `renderToStaticMarkup` não roda efeitos: o que sai destes renders é exatamente o
 * primeiro estado, antes de qualquer resposta da API. É o que garante que nenhum tenant,
 * contrato ou carimbo seja fabricado pela tela.
 */

const sessao = {
  access_token: "token-de-teste",
  profile: { sub: "operador-de-teste" },
} as unknown as User;

function tenant(overrides: Partial<PlatformTenant> = {}): PlatformTenant {
  return {
    tenant_id: "acme",
    enabled: false,
    agreement_reference: null,
    authorized_at: null,
    revoked_at: null,
    ...overrides,
  };
}

describe("PlatformApp sem sessão", () => {
  it("pede a sessão e não mostra tenant nenhum", () => {
    const html = renderToStaticMarkup(<PlatformApp session={null} />);

    expect(html).toContain("Entre para administrar a autorização contratual");
    expect(html).toContain("exigem o papel de operador");
    expect(html).not.toContain("Ativar autorização");
    expect(html).not.toContain("acme");
  });
});

describe("PlatformApp com sessão, antes da primeira resposta", () => {
  it("declara que a lista ainda não foi lida em vez de inventar tenant", () => {
    const html = renderToStaticMarkup(<PlatformApp session={sessao} />);

    expect(html).toContain("A lista de tenants ainda não foi lida.");
    expect(html).not.toContain("Autorização de IA:");
  });

  /**
   * O tenant que existe só no provedor de identidade não tem pegada no banco e por isso
   * não aparece na lista. Sem o campo de texto livre, ativá-lo seria impossível pela tela
   * — que é o ritual de `curl` que esta jornada veio substituir.
   */
  it("oferece ativar um tenant pelo identificador, com a razão escrita", () => {
    const html = renderToStaticMarkup(<PlatformApp session={sessao} />);

    expect(html).toContain("Identificador do tenant");
    expect(html).toContain("Ativar autorização deste tenant");
    expect(html).toContain("Consultar estado antes de ativar");
    expect(html).toContain("só no provedor de identidade");
    expect(html).toContain("Referência do contrato");
  });

  it("não fabrica sucesso nem erro antes de qualquer ato", () => {
    const html = renderToStaticMarkup(<PlatformApp session={sessao} />);

    expect(html).not.toContain('role="alert"');
    expect(html).not.toContain("app-toast");
  });
});

describe("LinhaTenant", () => {
  const inertes = {
    referencia: "",
    enviando: false,
    onAbrir: () => {},
    onCancelar: () => {},
    onReferencia: () => {},
    onConfirmar: () => {},
  };

  it("escreve o estado por extenso, e não só por cor", () => {
    const html = renderToStaticMarkup(
      <LinhaTenant
        tenant={tenant({
          enabled: true,
          agreement_reference: "contrato 05/2024",
          authorized_at: "2026-03-02T15:30:00Z",
        })}
        acao={null}
        {...inertes}
      />,
    );

    expect(html).toContain("Autorização de IA: ativo");
    expect(html).toContain("contrato 05/2024");
    expect(html).toContain("02/03/2026");
    // Ativo só oferece revogar; a ação disponível é a que falta fazer.
    expect(html).toContain("Revogar autorização");
    expect(html).not.toContain("Ativar autorização<");
  });

  it("distingue o tenant nunca autorizado do revogado", () => {
    const nunca = renderToStaticMarkup(
      <LinhaTenant tenant={tenant()} acao={null} {...inertes} />,
    );
    const revogado = renderToStaticMarkup(
      <LinhaTenant
        tenant={tenant({
          agreement_reference: "contrato 05/2024",
          authorized_at: "2026-03-02T15:30:00Z",
          revoked_at: "2026-03-09T15:30:00Z",
        })}
        acao={null}
        {...inertes}
      />,
    );

    expect(nunca).toContain("Autorização de IA: nunca autorizado");
    expect(nunca).toContain("Contrato: —");
    expect(revogado).toContain("Autorização de IA: revogado");
    expect(revogado).toContain("09/03/2026");
  });

  /**
   * A confirmação é gesto separado: abrir a ação não grava nada, e o botão nomeia o
   * tenant para que o ato não seja confirmado na linha errada.
   */
  it("a ativação pede a referência do contrato e uma confirmação nomeada", () => {
    const html = renderToStaticMarkup(
      <LinhaTenant
        tenant={tenant()}
        acao={{ enabled: true }}
        {...inertes}
      />,
    );

    expect(html).toContain("Referência do contrato");
    expect(html).toContain("Confirmar ativação de acme");
    expect(html).toContain("Cancelar");
    expect(html).toContain("3 a 128");
  });

  it("a revogação diz o que ela faz e o que ela não desfaz", () => {
    const html = renderToStaticMarkup(
      <LinhaTenant
        tenant={tenant({ enabled: true, agreement_reference: "contrato 05/2024" })}
        acao={{ enabled: false }}
        {...inertes}
      />,
    );

    expect(html).toContain("Confirmar revogação de acme");
    expect(html).toContain("bloqueia envios novos");
    expect(html).toContain("permanece");
    // Revogar não pede referência: o contrato que autorizou continua sendo o gravado.
    expect(html).not.toContain("<input");
  });
});

describe("AlertaPersistente", () => {
  it("é anunciado como alerta e não oferece fechar", () => {
    const html = renderToStaticMarkup(
      <AlertaPersistente mensagem="Sua conta não tem o papel de operador." />,
    );

    expect(html).toContain('role="alert"');
    expect(html).toContain("Sua conta não tem o papel de operador.");
    expect(html).not.toContain("app-alert-close");
  });
});

/**
 * Disponibilidade de jornada (F-034, fatia 2). Os renders abaixo cobrem os estados que o
 * pacote de design aprovado congelou em captura: normal, vazio, carregando e sem papel. A
 * recusa do servidor é a mesma faixa de erro já coberta por `AlertaPersistente`.
 */
describe("EstadoDasJornadas", () => {
  const ambiente: JourneyAvailability[] = [
    { journey: "croqui", state: "disabled" },
    { journey: "medicao", state: "enabled" },
    { journey: "orcamento", state: "pilot" },
  ];

  it("mostra o estado de cada jornada por palavra, com a pastilha ao lado", () => {
    const html = renderToStaticMarkup(
      <EstadoDasJornadas journeys={ambiente} />,
    );

    expect(html).toContain("Croqui");
    expect(html).toContain("INDISPONÍVEL");
    expect(html).toContain('class="neutral"');
    expect(html).toContain("Medição");
    expect(html).toContain("LIBERADA");
    expect(html).toContain('class="ready"');
    expect(html).toContain("Orçamento");
    expect(html).toContain("PILOTO");
    expect(html).toContain('class="blocked"');
  });

  /** O estado é mostrado, não editado: nenhum controle aparece na lista de estados. */
  it("não oferece jeito nenhum de mudar o estado", () => {
    const html = renderToStaticMarkup(
      <EstadoDasJornadas journeys={ambiente} />,
    );

    expect(html).not.toContain("<button");
    expect(html).not.toContain("<input");
    expect(html).not.toContain("<select");
  });
});

describe("LinhaAutorizacao", () => {
  function autorizacao(
    overrides: Partial<JourneyEntitlement> = {},
  ): JourneyEntitlement {
    return {
      tenant_id: "tenant-scalle",
      journey: "orcamento",
      enabled: true,
      agreement_reference: "contrato 05/2024 — aditivo 3",
      authorized_by: "daniel",
      authorized_at: "2026-08-22T09:14:00Z",
      revoked_at: null,
      ...overrides,
    };
  }

  const inertes = {
    enviando: false,
    onRevogar: () => {},
    onReautorizar: () => {},
  };

  it("mostra contrato, autor e data do ato, e oferece revogar", () => {
    const html = renderToStaticMarkup(
      <LinhaAutorizacao entitlement={autorizacao()} {...inertes} />,
    );

    expect(html).toContain("tenant-scalle");
    expect(html).toContain("Orçamento · piloto autorizado");
    expect(html).toContain("Contrato: contrato 05/2024 — aditivo 3");
    expect(html).toContain("Autorizado por daniel em ");
    expect(html).toContain("22/08/2026");
    expect(html).toContain("revogado em ");
    expect(html).toContain("—");
    expect(html).toContain("Revogar");
  });

  /** Revogar não apaga: a linha fica, com a data, e oferece autorizar de novo. */
  it("mantém a linha revogada, com a data da revogação", () => {
    const html = renderToStaticMarkup(
      <LinhaAutorizacao
        entitlement={autorizacao({
          enabled: false,
          revoked_at: "2026-08-22T08:02:00Z",
        })}
        {...inertes}
      />,
    );

    expect(html).toContain("Orçamento · autorização revogada");
    expect(html).toContain("Contrato: contrato 05/2024 — aditivo 3");
    expect(html).toContain("Autorizar de novo");
    expect(html).not.toContain(">Revogar<");
  });
});

describe("DisponibilidadeDeJornada", () => {
  it("não aparece sem sessão: a seção inteira é autenticada", () => {
    expect(
      renderToStaticMarkup(<DisponibilidadeDeJornada session={null} />),
    ).toBe("");
  });

  /**
   * `renderToStaticMarkup` não roda efeitos, então o que sai é o estado ANTES da primeira
   * resposta: nenhuma jornada, nenhum tenant e nenhum contrato fabricados, e o formulário
   * que não engana — ele não sabe ainda quais jornadas estão em piloto.
   */
  it("antes da primeira resposta não fabrica jornada nem autorização", () => {
    const html = renderToStaticMarkup(
      <DisponibilidadeDeJornada session={sessao} />,
    );

    expect(html).toContain("DISPONIBILIDADE DE JORNADA");
    expect(html).toContain("Quais jornadas existem para cada cliente");
    expect(html).toContain("Lendo a lista de autorizações…");
    expect(html).toContain(
      "Aguardando a lista para saber quais jornadas estão em piloto.",
    );
    // O formulário inteiro nasce desabilitado: sem a lista ele não sabe quais jornadas
    // estão em piloto, e um botão habilitado enganaria quem clica.
    expect(html).toContain('<input placeholder="tenant-exemplo" disabled=""');
    expect(html).toContain('<select disabled=""');
    expect(html).toContain(
      '<button class="button button-primary" type="submit" disabled=""',
    );
    // Nenhuma pastilha de estado antes de saber o estado.
    expect(html).not.toContain('class="neutral"');
    expect(html).not.toContain('class="ready"');
    expect(html).not.toContain('class="blocked"');
    expect(html).not.toContain('role="alert"');
  });

  it("não constrói o bloco reservado ao histórico, que é a F-017", () => {
    const html = renderToStaticMarkup(
      <DisponibilidadeDeJornada session={sessao} />,
    );

    expect(html).not.toContain("HISTÓRICO DE AUTORIZAÇÕES");
  });
});

describe("ColunaDoAmbiente", () => {
  const ambiente: JourneyAvailability[] = [
    { journey: "croqui", state: "disabled" },
    { journey: "medicao", state: "enabled" },
    { journey: "orcamento", state: "pilot" },
  ];

  /** Estado 1 do pacote aprovado: o que a seção é, o resumo e as três jornadas. */
  it("descreve o piloto, resume o ambiente e lista o estado das jornadas", () => {
    const html = renderToStaticMarkup(
      <ColunaDoAmbiente journeys={ambiente} />,
    );

    expect(html).toContain("DISPONIBILIDADE DE JORNADA");
    expect(html).toContain("Quais jornadas existem para cada cliente");
    expect(html).toContain("declarado no ambiente e não se edita por aqui");
    expect(html).toContain("<strong>piloto</strong>");
    expect(html).toContain("3 jornadas · 1 em piloto");
    expect(html).toContain("INDISPONÍVEL");
    expect(html).toContain("LIBERADA");
    expect(html).toContain("PILOTO");
  });

  /**
   * A decisão 2 do pacote aprovado: mudar o estado é configuração e publicação, e a tela
   * diz isso POR ESCRITO — não basta não oferecer o controle.
   */
  it("diz por escrito que o estado não se muda por aqui, e não oferece controle", () => {
    const html = renderToStaticMarkup(
      <ColunaDoAmbiente journeys={ambiente} />,
    );

    expect(html).toContain(
      "Mudar o estado de uma jornada é alterar a configuração do ambiente e publicar",
    );
    expect(html).not.toContain("<button");
    expect(html).not.toContain("<select");
  });

  it("durante a leitura diz o que está acontecendo, sem descrever lista que não há", () => {
    const html = renderToStaticMarkup(<ColunaDoAmbiente journeys={null} />);

    expect(html).toContain("Lendo a lista de autorizações…");
    expect(html).not.toContain("3 jornadas");
    expect(html).not.toContain("Mudar o estado de uma jornada");
  });
});

describe("FormularioDeAutorizacao", () => {
  const ambiente: JourneyAvailability[] = [
    { journey: "croqui", state: "disabled" },
    { journey: "medicao", state: "enabled" },
    { journey: "orcamento", state: "pilot" },
  ];

  const inertes = {
    referencia: "",
    enviando: false,
    onTenantId: () => {},
    onJornada: () => {},
    onReferencia: () => {},
    onAutorizar: () => {},
  };

  /**
   * As três jornadas são oferecidas, inclusive as que não estão em piloto: quem recusa é o
   * servidor, com a frase por extenso. É o estado 4 do pacote aprovado — sem esta escolha
   * a recusa desenhada seria inalcançável.
   */
  it("oferece as três jornadas, não só as em piloto", () => {
    const html = renderToStaticMarkup(
      <FormularioDeAutorizacao
        journeys={ambiente}
        dica="Só jornadas em piloto aceitam autorização."
        tenantId="tenant-scalle"
        jornada="medicao"
        {...inertes}
      />,
    );

    expect(html).toContain('value="croqui"');
    expect(html).toContain('value="medicao"');
    expect(html).toContain('value="orcamento"');
    expect(html).toContain("Identificador do tenant");
    expect(html).toContain("Referência do contrato");
    expect(html).toContain("Autorizar");
    // Com tenant escrito e a lista lida, o botão não fica travado.
    expect(html).not.toContain('type="submit" disabled=""');
  });

  it("não deixa autorizar sem identificador de tenant", () => {
    const html = renderToStaticMarkup(
      <FormularioDeAutorizacao
        journeys={ambiente}
        dica="Nenhum cliente autorizado em jornada de piloto."
        tenantId="   "
        jornada="orcamento"
        {...inertes}
      />,
    );

    expect(html).toContain('type="submit" disabled=""');
    expect(html).toContain("Nenhum cliente autorizado em jornada de piloto.");
  });
});

/**
 * Acervo de catálogos de referência (F-037). Os renders abaixo cobrem os estados que o
 * pacote aprovado congelou nas telas 7 e 8: a lista com uma linha fora de circulação, a
 * publicação e a leitura ainda em curso. A recusa do servidor é a mesma faixa de erro já
 * coberta por `AlertaPersistente`.
 */
describe("LinhaCatalogo", () => {
  function catalogo(overrides: Partial<ReferenceCatalog> = {}): ReferenceCatalog {
    return {
      reference_catalog_id: "0198-aaa",
      display_name: "SCO-Rio FGV06 desonerado",
      origin: "sco",
      reference_month: "2026-07",
      entry_count: 4865,
      object_sha256: "6f314c9".padEnd(64, "0"),
      source_sha256: "a17b3e0".padEnd(64, "0"),
      available: true,
      published_by: "daniel",
      published_at: "2026-08-22T09:14:00Z",
      withdrawn_at: null,
      ...overrides,
    };
  }

  const inertes = { enviando: false, onRetirar: () => {} };

  it("mostra origem, data-base, contagem, digest e quem publicou", () => {
    const html = renderToStaticMarkup(
      <LinhaCatalogo catalogo={catalogo()} {...inertes} />,
    );

    expect(html).toContain("SCO-Rio FGV06 desonerado");
    expect(html).toContain("origem sco");
    expect(html).toContain("ref.");
    expect(html).toContain("07/2026");
    expect(html).toContain("4.865");
    expect(html).toContain("sha256 6f314c900000");
    expect(html).toContain("publicada por daniel em ");
    expect(html).toContain("22/08/2026");
    expect(html).toContain("Retirar de circulação");
  });

  /** O digest inteiro fica no `title`; a tela mostra o curto para conferência. */
  it("guarda o digest inteiro no title, e não na linha", () => {
    const html = renderToStaticMarkup(
      <LinhaCatalogo catalogo={catalogo()} {...inertes} />,
    );

    expect(html).toContain(`title="${"6f314c9".padEnd(64, "0")}"`);
  });

  /**
   * Retirar não apaga: a linha continua, com a PALAVRA e a data. Cor nunca é o único
   * indicador — a pastilha carrega o texto e a linha o repete por extenso.
   */
  it("mantém a linha fora de circulação, com a marca escrita e a data", () => {
    const html = renderToStaticMarkup(
      <LinhaCatalogo
        catalogo={catalogo({
          reference_month: "2026-04",
          available: false,
          withdrawn_at: "2026-08-22T11:00:00Z",
        })}
        {...inertes}
      />,
    );

    expect(html).toContain("FORA DE CIRCULAÇÃO");
    expect(html).toContain("retirada de circulação em ");
    expect(html).toContain("04/2026");
    expect(html).toContain('class="neutral"');
    // Quem já saiu de circulação não oferece sair de novo.
    expect(html).not.toContain("<button");
  });

  /**
   * A contagem de rodadas que ainda referenciam a tabela está desenhada no pacote e NÃO
   * entra: nenhuma rota a devolve hoje, e escrevê-la seria fabricar um número.
   */
  it("não fabrica a contagem de rodadas que ainda referenciam", () => {
    const html = renderToStaticMarkup(
      <LinhaCatalogo
        catalogo={catalogo({
          available: false,
          withdrawn_at: "2026-08-22T11:00:00Z",
        })}
        {...inertes}
      />,
    );

    expect(html).not.toContain("rodadas ainda a referenciam");
  });
});

describe("FormularioDePublicacao", () => {
  const inertes = {
    campoArquivoKey: 0,
    onArquivo: () => {},
    onNomeExibicao: () => {},
    onPublicar: () => {},
  };

  it("pede o catálogo normalizado e o nome de exibição, e diz de onde vem o resto", () => {
    const html = renderToStaticMarkup(
      <FormularioDePublicacao
        arquivoEscolhido
        nomeExibicao="SINAPI RJ desonerado"
        enviando={false}
        {...inertes}
      />,
    );

    expect(html).toContain("Catálogo normalizado (JSON)");
    expect(html).toContain('type="file"');
    expect(html).toContain("Nome de exibição");
    expect(html).toContain("é o que a orçamentista lê na lista");
    expect(html).toContain("<code>import-sinapi</code>");
    expect(html).toContain("<code>catalog.json</code>");
    expect(html).toContain(
      "Origem, data-base e contagem de itens vêm de dentro do arquivo",
    );
    expect(html).toContain("Publicar");
    expect(html).not.toContain('type="submit" disabled=""');
  });

  /**
   * Sem arquivo não há o que publicar; e o nome curto demais é o `min_length` do
   * CONTRATO, repetido para o operador ler uma frase em vez de um 422 sem código.
   */
  it("não publica sem arquivo nem com nome de exibição curto demais", () => {
    const semArquivo = renderToStaticMarkup(
      <FormularioDePublicacao
        arquivoEscolhido={false}
        nomeExibicao="SINAPI RJ desonerado"
        enviando={false}
        {...inertes}
      />,
    );
    const nomeCurto = renderToStaticMarkup(
      <FormularioDePublicacao
        arquivoEscolhido
        nomeExibicao=" a "
        enviando={false}
        {...inertes}
      />,
    );

    expect(semArquivo).toContain('type="submit" disabled=""');
    expect(nomeCurto).toContain('type="submit" disabled=""');
  });

  /** Origem, data-base e contagem não são digitadas: não existe campo para elas. */
  it("não oferece campo para o que vem de dentro do arquivo", () => {
    const html = renderToStaticMarkup(
      <FormularioDePublicacao
        arquivoEscolhido
        nomeExibicao="SINAPI RJ desonerado"
        enviando={false}
        {...inertes}
      />,
    );

    expect(html).not.toContain("Data-base");
    expect(html).not.toContain("Origem<");
    expect(html).not.toContain("Contagem");
    expect(html).not.toContain("<select");
  });
});

describe("AcervoDeCatalogos", () => {
  it("não aparece sem sessão: a seção inteira é autenticada", () => {
    expect(renderToStaticMarkup(<AcervoDeCatalogos session={null} />)).toBe("");
  });

  /**
   * `renderToStaticMarkup` não roda efeitos, então o que sai é o estado ANTES da primeira
   * resposta: nenhuma tabela, nenhum digest e nenhum carimbo fabricados.
   */
  it("antes da primeira resposta não fabrica tabela nenhuma", () => {
    const html = renderToStaticMarkup(<AcervoDeCatalogos session={sessao} />);

    expect(html).toContain("ACERVO DE TABELAS DE REFERÊNCIA");
    expect(html).toContain("Tabelas publicadas");
    expect(html).toContain("O acervo ainda não foi lido.");
    expect(html).toContain("data-base nova é entrada nova");
    // Sem lista não há ato a explicar: a consequência de retirar só aparece junto das
    // linhas onde o botão existe.
    expect(html).not.toContain("Retirar não apaga");
    expect(html).not.toContain("sha256");
    expect(html).not.toContain("FORA DE CIRCULAÇÃO");
    expect(html).not.toContain('role="alert"');
    expect(html).not.toContain("app-toast");
  });

  /** O bloco reservado do pacote (tela 9) não é construído nesta feature. */
  it("não constrói a atualização automática, que é o bloco reservado", () => {
    const html = renderToStaticMarkup(<AcervoDeCatalogos session={sessao} />);

    expect(html).not.toContain("ATUALIZAÇÃO AUTOMÁTICA");
  });

  /**
   * O acervo NÃO tem toast de sucesso, e isto é decisão de desenho, não esquecimento.
   *
   * `.app-toast` é `position: fixed` no canto inferior direito (`src/styles.css`), e a
   * jornada de Plataforma empilha seções: um toast por seção sobreporia duas faixas no
   * mesmo pixel quando dois atos acontecessem dentro da mesma janela. Aqui a confirmação
   * é a releitura da lista, como em `DisponibilidadeDeJornada` — a linha nova aparece
   * publicada, a retirada aparece fora de circulação.
   */
  it("confirma o ato pela releitura da lista, não por um toast que sobreporia o da seção vizinha", () => {
    const comCatalogo = renderToStaticMarkup(
      <AcervoDeCatalogos session={sessao} />,
    );

    expect(comCatalogo).not.toContain("app-toast");
    expect(comCatalogo).not.toContain("publicada para todos os tenants");
    expect(comCatalogo).not.toContain("saiu de circulação. As rodadas");
  });
});

/**
 * A divergência 1 do pacote aprovado, fixada por teste: a jornada de Plataforma não tem
 * abas, e o acervo entra como uma terceira `<section>` empilhada. Se alguém introduzir a
 * fita de abas desenhada no mock, este teste cai.
 */
describe("composição da jornada de plataforma", () => {
  it("empilha as seções e não introduz navegação por abas", () => {
    const html = renderToStaticMarkup(<PlatformApp session={sessao} />);

    expect(
      html.split('class="authenticated-workspace"').length - 1,
    ).toBe(4);
    expect(html).toContain("Autorização contratual de IA");
    expect(html).toContain("Quais jornadas existem para cada cliente");
    expect(html).toContain("Tabelas publicadas");
    expect(html).toContain("Índices publicados");
    expect(html).not.toContain('role="tablist"');
    expect(html).not.toContain('role="tab"');
    expect(html).not.toContain("Acervo de tabelas<");
  });
});

/**
 * Índices de embeddings (F-041, ADR-0054).
 *
 * `renderToStaticMarkup` não roda efeitos: o que sai destes renders é o primeiro estado,
 * antes de qualquer resposta da API. É o que garante que nenhum índice, digest ou carimbo
 * seja fabricado pela tela.
 */
function catalogoIndexado(
  overrides: Partial<ReferenceCatalog> = {},
): ReferenceCatalog {
  return {
    reference_catalog_id: "0198-aaa",
    display_name: "SCO-Rio FGV06 desonerado",
    origin: "sco",
    reference_month: "2026-07",
    entry_count: 4964,
    object_sha256: "6f314c9".padEnd(64, "0"),
    source_sha256: "a17b3e0".padEnd(64, "0"),
    available: true,
    published_by: "daniel",
    published_at: "2026-08-22T09:14:00Z",
    withdrawn_at: null,
    ...overrides,
  };
}

function indicePublicado(
  overrides: Partial<ReferenceCatalogIndex> = {},
): ReferenceCatalogIndex {
  return {
    reference_catalog_index_id: "0198-idx",
    reference_catalog_id: "0198-aaa",
    catalog_source_sha256: "a17b3e0".padEnd(64, "0"),
    text_recipe: "code-description-unit-v1",
    provider: "openai",
    model_id: "text-embedding-3-small",
    dims: 1536,
    code_count: 4964,
    object_sha256: "6f314c9".padEnd(64, "0"),
    available: true,
    published_by: "daniel",
    published_at: "2026-08-28T09:14:00Z",
    withdrawn_at: null,
    ...overrides,
  };
}

describe("LinhaIndice", () => {
  const inertes = { enviando: false, onRetirar: () => {} };

  it("mostra a identidade da publicação e o estado por extenso", () => {
    const html = renderToStaticMarkup(
      <LinhaIndice
        indice={indicePublicado()}
        catalogos={[catalogoIndexado()]}
        {...inertes}
      />,
    );

    expect(html).toContain("SCO-Rio FGV06 desonerado");
    expect(html).toContain("em circulação");
    expect(html).toContain("code-description-unit-v1");
    expect(html).toContain("text-embedding-3-small");
    expect(html).toContain("1536 dimensões");
    expect(html).toContain("4.964 códigos");
    expect(html).toContain("sha256 6f314c900000");
    expect(html).toContain("publicado por daniel em 28/08/2026");
    expect(html).toContain("Retirar de circulação");
  });

  /** Nenhum vetor sai na resposta, e nem a chave do objeto: nada disso pode aparecer. */
  it("não mostra chave de objeto nem vetor, e não oferece baixar o índice", () => {
    const html = renderToStaticMarkup(
      <LinhaIndice
        indice={indicePublicado()}
        catalogos={[catalogoIndexado()]}
        {...inertes}
      />,
    );

    expect(html).not.toContain("platform/reference-catalog-indexes/");
    expect(html).not.toContain("vectors");
    expect(html).not.toContain("Baixar");
    expect(html).not.toContain("<a ");
  });

  /**
   * Retirado continua na lista, com a palavra e a data — e sem o botão, porque o ato já
   * aconteceu. Cor nunca carrega isso sozinha: a pastilha traz a PALAVRA.
   */
  it("o índice retirado fica na lista, com a palavra e a data, e sem botão", () => {
    const html = renderToStaticMarkup(
      <LinhaIndice
        indice={indicePublicado({
          available: false,
          withdrawn_at: "2026-08-28T11:00:00Z",
        })}
        catalogos={[catalogoIndexado()]}
        {...inertes}
      />,
    );

    expect(html).toContain("fora de circulação");
    expect(html).toContain("FORA DE CIRCULAÇÃO");
    expect(html).toContain("retirado de circulação em 28/08/2026");
    expect(html).not.toContain("Retirar de circulação");
  });

  /** Sem o acervo lido, a linha cita o digest da fonte em vez de inventar um nome. */
  it("cai no digest da fonte quando o acervo ainda não foi lido", () => {
    const html = renderToStaticMarkup(
      <LinhaIndice indice={indicePublicado()} catalogos={null} {...inertes} />,
    );

    expect(html).toContain("sha256 a17b3e000000");
    expect(html).not.toContain("SCO-Rio FGV06 desonerado");
  });
});

describe("FormularioDePublicacaoDeIndice", () => {
  const inertes = {
    campoArquivoKey: 0,
    onArquivo: () => {},
    onCatalogo: () => {},
    onPublicar: () => {},
  };

  it("pede o arquivo e a tabela, e diz que o índice vem do CLI", () => {
    const html = renderToStaticMarkup(
      <FormularioDePublicacaoDeIndice
        catalogos={[catalogoIndexado()]}
        catalogoId="0198-aaa"
        arquivoEscolhido
        enviando={false}
        {...inertes}
      />,
    );

    expect(html).toContain("Índice de embeddings (JSON)");
    expect(html).toContain('type="file"');
    expect(html).toContain("Tabela indexada");
    expect(html).toContain("<code>index-catalog</code>");
    expect(html).toContain("<code>catalog-embeddings.json</code>");
    expect(html).toContain("nunca o constrói");
    expect(html).toContain("não são digitados");
    expect(html).toContain("Publicar índice");
    expect(html).not.toContain('type="submit" disabled=""');
  });

  /** Nada na tela sugere que o índice é construído aqui (ADR-0054 D4). */
  it("não oferece construir índice nem campo que descreva o conteúdo", () => {
    const html = renderToStaticMarkup(
      <FormularioDePublicacaoDeIndice
        catalogos={[catalogoIndexado()]}
        catalogoId="0198-aaa"
        arquivoEscolhido
        enviando={false}
        {...inertes}
      />,
    );

    expect(html).not.toContain("Construir");
    expect(html).not.toContain("Gerar");
    expect(html).not.toContain("Indexar");
    expect(html).not.toContain("Receita de texto<");
    expect(html).not.toContain("Modelo<");
    expect(html).not.toContain("Dimensões");
  });

  it("não publica sem arquivo nem sem tabela escolhida", () => {
    const semArquivo = renderToStaticMarkup(
      <FormularioDePublicacaoDeIndice
        catalogos={[catalogoIndexado()]}
        catalogoId="0198-aaa"
        arquivoEscolhido={false}
        enviando={false}
        {...inertes}
      />,
    );
    const semTabela = renderToStaticMarkup(
      <FormularioDePublicacaoDeIndice
        catalogos={[]}
        catalogoId=""
        arquivoEscolhido
        enviando={false}
        {...inertes}
      />,
    );

    expect(semArquivo).toContain('type="submit" disabled=""');
    expect(semTabela).toContain('type="submit" disabled=""');
    expect(semTabela).toContain("Nenhuma tabela no acervo para indexar");
  });

  /**
   * A tabela fora de circulação continua na escolha, com a palavra ao lado: o índice é
   * resolvido pelo digest da FONTE (ADR-0054 D3), então ele segue servindo qualquer
   * catálogo com os mesmos bytes de origem.
   */
  it("oferece também a tabela fora de circulação, dizendo qual é qual", () => {
    const html = renderToStaticMarkup(
      <FormularioDePublicacaoDeIndice
        catalogos={[
          catalogoIndexado(),
          catalogoIndexado({
            reference_catalog_id: "0198-bbb",
            display_name: "SCO-Rio FGV06 anterior",
            available: false,
            withdrawn_at: "2026-08-22T11:00:00Z",
          }),
        ]}
        catalogoId="0198-aaa"
        arquivoEscolhido
        enviando={false}
        {...inertes}
      />,
    );

    expect(html).toContain("SCO-Rio FGV06 anterior · 07/2026 (fora de circulação)");
  });
});

describe("IndicesDeEmbeddings", () => {
  it("não aparece sem sessão: a seção inteira é autenticada", () => {
    expect(renderToStaticMarkup(<IndicesDeEmbeddings session={null} />)).toBe("");
  });

  it("antes da primeira resposta não fabrica índice nenhum", () => {
    const html = renderToStaticMarkup(<IndicesDeEmbeddings session={sessao} />);

    expect(html).toContain("ÍNDICES DE EMBEDDINGS");
    expect(html).toContain("Índices publicados");
    expect(html).toContain("Os índices ainda não foram lidos.");
    expect(html).not.toContain("sha256");
    expect(html).not.toContain("FORA DE CIRCULAÇÃO");
    expect(html).not.toContain('role="alert"');
    expect(html).not.toContain("app-toast");
  });

  /**
   * A consequência de retirar só aparece junto das linhas onde o botão existe — sem lista
   * não há ato a explicar, e o estado da seção já está escrito na coluna ao lado.
   */
  it("o aviso de que retirar não apaga só aparece junto da lista", () => {
    const html = renderToStaticMarkup(<IndicesDeEmbeddings session={sessao} />);

    expect(html).not.toContain("Retirar não apaga");
  });

  /** Publicar é ato de plataforma; construir continua sendo do CLI. */
  it("declara que o servidor lê o índice e nunca o constrói", () => {
    const html = renderToStaticMarkup(<IndicesDeEmbeddings session={sessao} />);

    expect(html).toContain("<code>index-catalog</code>");
    expect(html).toContain("nunca o constrói");
    expect(html).not.toContain("Construir índice");
  });
});
