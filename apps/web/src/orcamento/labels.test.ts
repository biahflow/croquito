import { describe, expect, it } from "vitest";

import {
  assignmentStatusLabel,
  AVISO_ACERVO_FILTRADO,
  errorMessage,
  opcaoDoAcervo,
  origensAceitasNaCascata,
  priceOriginLabel,
  priceOriginSeloClass,
  procedenciaDaFonte,
} from "./labels";

describe("priceOriginLabel", () => {
  /**
   * SINAPI e SICRO entram como origens nomeadas de `PriceOrigin` (ADR-0039, F-026); a
   * orçamentista precisa ver a sigla real, não a chave crua do enum.
   */
  it("nomeia as origens novas SINAPI e SICRO", () => {
    expect(priceOriginLabel("sinapi")).toBe("SINAPI");
    expect(priceOriginLabel("sicro")).toBe("SICRO");
  });

  it("preserva as origens existentes", () => {
    expect(priceOriginLabel("sco")).toBe("SCO");
    expect(priceOriginLabel("emop")).toBe("EMOP");
    expect(priceOriginLabel("composition")).toBe("composição");
  });
});

describe("priceOriginSeloClass", () => {
  /**
   * O selo é redundância do texto (já escrito por `priceOriginLabel`); SINAPI e SICRO
   * caem no fallback neutro de propósito — cor nova por origem é decisão de design que
   * esta feature não tem (F-026/T1).
   */
  it("cai no fallback neutro para as origens novas, sem cor própria", () => {
    expect(priceOriginSeloClass("sinapi")).toBe("selo-neutro");
    expect(priceOriginSeloClass("sicro")).toBe("selo-neutro");
  });

  it("preserva a cor das origens que já tinham selo próprio", () => {
    expect(priceOriginSeloClass("sco")).toBe("selo-fonte-sco");
    expect(priceOriginSeloClass("emop")).toBe("selo-fonte-emop");
    expect(priceOriginSeloClass("composition")).toBe("selo-fonte-composicao");
  });
});

/**
 * Regime da rodada (ADR-0045, decisão 5): a rejeição é a MESMA decisão nos dois regimes, e
 * é o nome dela que muda. Nada novo é calculado, e é por isso que o rótulo é o ponto.
 */
describe("assignmentStatusLabel sob contrato licitado", () => {
  it("lê o item rejeitado como candidato a aditivo quando a rodada corre sob contrato", () => {
    expect(assignmentStatusLabel("rejected", true)).toBe("candidato a aditivo");
  });

  it("sem regime, segue lendo o que lê hoje", () => {
    expect(assignmentStatusLabel("rejected")).toBe("sem código na cascata");
    expect(assignmentStatusLabel("rejected", false)).toBe("sem código na cascata");
  });

  /** O regime não renomeia o que não é rejeição: confirmar é confirmar nos dois. */
  it("não muda o rótulo do código confirmado nem o de um status desconhecido", () => {
    expect(assignmentStatusLabel("confirmed", true)).toBe("código confirmado");
    expect(assignmentStatusLabel("confirmed")).toBe("código confirmado");
    expect(assignmentStatusLabel("inexistente", true)).toBe("inexistente");
  });
});

/**
 * A lista de origens aceitas vem do SERVIDOR (`regime.allowed_cascade_origins`). A tela
 * escreve o que leu; ela não guarda a própria cópia da regra nem afirma restrição sem tê-la
 * lido.
 */
describe("origensAceitasNaCascata", () => {
  it("nomeia as origens lidas do servidor, com a sigla da obra", () => {
    const frase = origensAceitasNaCascata(["sco"]);

    expect(frase).toContain("catálogo de SCO");
    expect(frase).toContain("recusado na instalação");
    expect(frase).toContain("nada é gravado");
  });

  it("escreve o que leu, mesmo que o servidor passe a aceitar mais de uma origem", () => {
    expect(origensAceitasNaCascata(["sco", "composition"])).toContain(
      "SCO, composição",
    );
  });

  it("lista vazia não vira frase: a tela não afirma restrição que não leu", () => {
    expect(origensAceitasNaCascata([])).toBeNull();
  });
});

/**
 * As três recusas do regime têm frase de obra própria, e as duas que recusam um ato dizem
 * por escrito que nada foi gravado (decisão 3 do pacote de design aprovado).
 */
describe("recusas do regime", () => {
  it("a origem proibida diz o que aconteceria se a fonte entrasse", () => {
    const frase = errorMessage("ESTIMATE_CASCADE_ORIGIN_FORBIDDEN");

    expect(frase).toContain("sob contrato licitado");
    expect(frase).toContain("a medição recusaria depois");
    expect(frase).toContain("Nada foi instalado e nada foi alterado");
  });

  it("a cascata suja manda remover a fonte, e diz que nada foi removido sozinho", () => {
    const frase = errorMessage("ESTIMATE_REGIME_CASCADE_DIRTY");

    expect(frase).toContain("Remova a fonte");
    expect(frase).toContain("nenhuma fonte é removida automaticamente");
    expect(frase).toContain("a declaração não foi gravada");
  });

  it("a mão única diz por que a volta não existe, em vez de sumir com o ato", () => {
    const frase = errorMessage("ESTIMATE_REGIME_IRREVERSIBLE");

    expect(frase).toContain("mão única");
    expect(frase).toContain("abra outra rodada");
  });
});

/**
 * Acervo de tabelas da plataforma (F-037, ADR-0047 decisão 7). A procedência é o FATO de
 * quem publicou o arquivo, e a marca dela é a PALAVRA — a veste do selo é redundância.
 */
describe("procedência da fonte instalada", () => {
  it("nomeia por extenso os dois caminhos que existem", () => {
    expect(procedenciaDaFonte("reference_catalog")).toBe("DO ACERVO");
    expect(procedenciaDaFonte("tenant_upload")).toBe("TABELA PRÓPRIA");
  });

  /**
   * Cascata instalada ANTES da feature não tem o campo, e a ausência lê como tabela
   * própria — que é o que ela é, porque era o único caminho que existia. Ela continua
   * legível; nada é reescrito para trás e nada aparece como "desconhecido".
   */
  it("a ausência do campo lê como tabela própria, sem inventar um terceiro estado", () => {
    expect(procedenciaDaFonte()).toBe("TABELA PRÓPRIA");
    expect(procedenciaDaFonte(null)).toBe("TABELA PRÓPRIA");
    expect(procedenciaDaFonte(undefined)).toBe("TABELA PRÓPRIA");
  });
});

describe("opção do acervo", () => {
  /**
   * O que distingue duas linhas que sem isto seriam ambas "SCO": nome, data-base e
   * tamanho (decisão 2 do pacote aprovado). A contagem é agrupada em milhar, e a
   * conversão é de PONTUAÇÃO — nenhum dígito é acrescentado nem removido.
   */
  it("carrega nome, data-base e contagem numa linha só", () => {
    expect(
      opcaoDoAcervo({
        display_name: "SCO-Rio FGV06 desonerado",
        reference_month: "2026-07",
        entry_count: 4865,
      }),
    ).toBe("SCO-Rio FGV06 desonerado · ref. 2026-07 · 4.865 itens");
  });

  it("contagem pequena não ganha separador que ela não tem", () => {
    expect(
      opcaoDoAcervo({
        display_name: "SICRO RJ",
        reference_month: "2026-06",
        entry_count: 12,
      }),
    ).toContain("12 itens");
  });
});

/**
 * O filtro do regime é do SERVIDOR. A frase que explica a lista mais curta não nomeia
 * origem nenhuma: nomeá-las seria guardar aqui uma cópia da regra, exatamente o que
 * `origensAceitasNaCascata` existe para não fazer.
 */
describe("aviso da lista filtrada", () => {
  it("diz que o filtro é do servidor sem repetir a regra do regime", () => {
    expect(AVISO_ACERVO_FILTRADO).toContain("filtrada pelo servidor");
    expect(AVISO_ACERVO_FILTRADO).toContain("oferecer uma recusa");
    expect(AVISO_ACERVO_FILTRADO).not.toContain("SINAPI");
    expect(AVISO_ACERVO_FILTRADO).not.toContain("SICRO");
    expect(AVISO_ACERVO_FILTRADO).not.toContain("SCO");
  });
});

/**
 * As recusas do acervo são de INSTALAÇÃO, e as três declaram que nada foi gravado: a
 * lista que a tela leu pode ter envelhecido entre a leitura e o clique.
 */
describe("recusas do acervo", () => {
  it("a tabela retirada não vira erro da tela nem apaga as rodadas que a usam", () => {
    const frase = errorMessage("REFERENCE_CATALOG_WITHDRAWN");

    expect(frase).toContain("saiu de circulação");
    expect(frase).toContain("continua valendo nas rodadas que já a instalaram");
    expect(frase).toContain("nada foi instalado");
  });

  it("a fonte ambígua diz qual é a regra e que nada foi instalado", () => {
    const frase = errorMessage("ESTIMATE_CATALOG_SOURCE_INVALID");

    expect(frase).toContain("nunca as duas");
    expect(frase).toContain("nada foi instalado");
  });
});
