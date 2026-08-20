import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import type { User } from "oidc-client-ts";

import {
  BannerOrcamentoMudou,
  OrcamentoApp,
  PainelSemAcesso,
  SeloFonte,
  SemPrecoNaCascata,
  TelaAuditoriaReprovada,
} from "./OrcamentoApp";
import { AVISO_ORCAMENTO } from "./labels";

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
