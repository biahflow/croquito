import { describe, expect, it } from "vitest";

import {
  acervosVersionaveis,
  autoriaInicial,
  bindingsDoCorpo,
  declararBinding,
  declararNomeDoAcervo,
  declararVersaoDoAcervo,
  escolherAcervoBase,
  escolherModoDeAutoria,
  motivoDeAutoriaIndisponivel,
  parametrosDaAutoria,
  parcelasAutoraveis,
  pedidoDaAutoria,
  podeAutorar,
  registrarAutoria,
  resumoDoQueEntra,
  type SiteSetupKitAuthoredResponse,
} from "./acervoAutoria";
import type { SiteSetupKit } from "./acervo";
import type { CalcMatrix } from "./matrix";
import { authorSiteSetupKitBody } from "./requests";

/**
 * A matriz GRAVADA de uma rodada que já aplicou um acervo e ganhou uma parcela à mão.
 *
 * O primeiro serviço traz uma parcela com origem na prancha (`full`) ANTES das de canteiro:
 * é ela que prova que o índice do binding conta só as `standalone` — se ela entrasse na
 * contagem, todo binding apontaria para a parcela seguinte.
 */
const MATRIZ: CalcMatrix = {
  schema_version: "1.0.0",
  services: [
    {
      code: "AD14100200",
      contributions: [
        {
          source_item_id: "ti_00000000000000b1",
          label: "ALAMBRADO GALVANIZADO",
          basis: "full",
          recipe: "declared_product",
          operands: [{ name: "COMPRIMENTO", value: "10.00", unit: "m" }],
          deductions: [],
          depends_on_code: null,
          note: null,
        },
        {
          source_item_id: null,
          label: "WC QUIMICO",
          basis: "standalone",
          recipe: "qty_times_months",
          operands: [
            { name: "QTD", value: "1", unit: null },
            { name: "MESES", value: "2", unit: "mes" },
          ],
          deductions: [],
          depends_on_code: null,
          note: null,
          kit_origin: { kit_version: "sco-site-setup-v1", parcel_id: "ss_aaaa" },
        },
      ],
    },
    {
      code: "AD19250300",
      contributions: [
        {
          source_item_id: null,
          label: "PLACA DE OBRA",
          basis: "standalone",
          recipe: "declared_product",
          operands: [
            { name: "COMP", value: "2.00", unit: "m" },
            { name: "LARG", value: "1.40", unit: "m" },
          ],
          deductions: [],
          depends_on_code: null,
          note: null,
        },
      ],
    },
  ],
};

const KIT_DO_TENANT: SiteSetupKit = {
  kit_id: "kit-do-tenant",
  name: "Canteiro — contrato SMH/Rio",
  kit_version: "sco-site-setup-v1",
  origin: "tenant",
  source_label: "PRACA CAMPO DO TOCA",
  parcel_count: 2,
  parameters: [{ name: "prazo de obra", unit: "mes", cited_by: 1 }],
  created_at: "2026-08-28T10:00:00Z",
};

const KIT_DA_PLATAFORMA: SiteSetupKit = {
  ...KIT_DO_TENANT,
  kit_id: "kit-da-plataforma",
  name: "Canteiro — acervo da plataforma",
  origin: "platform",
};

function fluxoPronto() {
  const parcelas = parcelasAutoraveis(MATRIZ);
  let fluxo = escolherModoDeAutoria(autoriaInicial(), "novo");
  fluxo = declararNomeDoAcervo(fluxo, "Canteiro — contrato SMH/Rio");
  fluxo = declararVersaoDoAcervo(fluxo, "2");
  return { fluxo, parcelas };
}

describe("parcelasAutoraveis", () => {
  /**
   * O índice é a posição na lista de `standalone` percorrida na ordem dos serviços — o
   * mesmo que `standalone_contributions` enumera do lado Python. A parcela com origem na
   * prancha não entra e não conta.
   */
  it("enumera só o canteiro, na ordem do servidor, e ignora a parcela da prancha", () => {
    const parcelas = parcelasAutoraveis(MATRIZ);

    expect(parcelas.map((parcela) => parcela.label)).toEqual([
      "WC QUIMICO",
      "PLACA DE OBRA",
    ]);
    expect(parcelas.map((parcela) => parcela.indice)).toEqual([0, 1]);
    expect(parcelas[0].code).toBe("AD14100200");
    expect(parcelas[1].code).toBe("AD19250300");
    // A chave do binding já sai montada com o índice certo.
    expect(parcelas[0].operandos.map((operando) => operando.chave)).toEqual([
      "0.QTD",
      "0.MESES",
    ]);
    expect(parcelas[1].operandos[0].chave).toBe("1.COMP");
  });

  it("declara a origem de cada parcela pela versão que a matriz gravou", () => {
    const parcelas = parcelasAutoraveis(MATRIZ);

    expect(parcelas[0].kitVersion).toBe("sco-site-setup-v1");
    expect(parcelas[1].kitVersion).toBeNull();
    expect(resumoDoQueEntra(parcelas)).toEqual({ total: 2, doAcervo: 1, aMao: 1 });
  });

  /** Regime legado: rodada sem matriz não tem canteiro gravado, e nada é fabricado dela. */
  it("matriz ausente devolve lista vazia", () => {
    expect(parcelasAutoraveis(null)).toEqual([]);
    expect(resumoDoQueEntra([])).toEqual({ total: 0, doAcervo: 0, aMao: 0 });
  });

  /**
   * Um binding vale para o operando E para a dedução de mesmo nome dentro da mesma
   * contribuição: o modelo não distingue os dois espaços de nome. Duas linhas com o mesmo
   * nome fariam a segunda parecer uma declaração à parte que não existe.
   */
  it("um nome que é operando e dedução vira uma linha só, e ela o diz", () => {
    const parcelas = parcelasAutoraveis({
      schema_version: "1.0.0",
      services: [
        {
          code: "AD19050500",
          contributions: [
            {
              source_item_id: null,
              label: "VIGIA",
              basis: "standalone",
              recipe: "days_times_hours",
              operands: [
                { name: "DIAS", value: "23", unit: "dia" },
                { name: "HORAS", value: "12", unit: "h" },
              ],
              deductions: [{ name: "DIAS", value: "1", unit: "dia" }],
              depends_on_code: null,
              note: null,
            },
          ],
        },
      ],
    });

    expect(parcelas[0].operandos.map((operando) => operando.nome)).toEqual([
      "DIAS",
      "HORAS",
    ]);
    expect(parcelas[0].operandos[0].tambemDeducao).toBe(true);
    expect(parcelas[0].operandos[1].tambemDeducao).toBe(false);
  });
});

describe("o formulário da autoria", () => {
  /** Nada nasce escolhido: um modo pré-marcado criaria acervo novo por omissão. */
  it("abre sem modo, sem nome, sem versão e sem binding nenhum", () => {
    expect(autoriaInicial()).toEqual({
      modo: "",
      kitId: "",
      nome: "",
      versao: "",
      bindings: {},
    });
  });

  it("versionar traz o nome DO acervo escolhido, e não um nome digitado", () => {
    const fluxo = escolherAcervoBase(
      escolherModoDeAutoria(autoriaInicial(), "versao"),
      KIT_DO_TENANT,
    );

    expect(fluxo.modo).toBe("versao");
    expect(fluxo.kitId).toBe(KIT_DO_TENANT.kit_id);
    expect(fluxo.nome).toBe(KIT_DO_TENANT.name);
  });

  /**
   * Trocar de modo não arrasta o nome do outro: publicar sob um nome que a pessoa não
   * digitou é exatamente o que a chave `(nome, versão)` do servidor tornaria permanente.
   */
  it("trocar de modo limpa o acervo de base e o nome, mas preserva os bindings", () => {
    const comBase = declararBinding(
      escolherAcervoBase(
        escolherModoDeAutoria(autoriaInicial(), "versao"),
        KIT_DO_TENANT,
      ),
      "0.MESES",
      "prazo de obra",
    );

    const novo = escolherModoDeAutoria(comBase, "novo");

    expect(novo.kitId).toBe("");
    expect(novo.nome).toBe("");
    expect(novo.bindings).toEqual({ "0.MESES": "prazo de obra" });
  });

  /** Vazio é "fica constante", que é o default do domínio — não uma declaração vazia. */
  it("apagar o campo do parâmetro devolve o operando à condição de constante", () => {
    const declarado = declararBinding(autoriaInicial(), "0.MESES", "prazo de obra");
    const apagado = declararBinding(declarado, "0.MESES", "   ");

    expect(bindingsDoCorpo(declarado)).toEqual({ "0.MESES": "prazo de obra" });
    expect(apagado.bindings).toEqual({});
    expect(bindingsDoCorpo(apagado)).toEqual({});
  });

  it("o corpo tira o espaço em volta do nome do parâmetro", () => {
    const fluxo = declararBinding(autoriaInicial(), "1.COMP", "  largura da placa  ");

    expect(bindingsDoCorpo(fluxo)).toEqual({ "1.COMP": "largura da placa" });
  });
});

describe("parametrosDaAutoria", () => {
  /** A lista é o RESULTADO do que foi declarado; sem binding, ela é vazia. */
  it("sem binding nenhum não sugere parâmetro algum", () => {
    const { fluxo, parcelas } = fluxoPronto();

    expect(parametrosDaAutoria(fluxo, parcelas, null)).toEqual([]);
  });

  it("agrupa por nome, conta os operandos e zera a unidade quando elas discordam", () => {
    const { fluxo, parcelas } = fluxoPronto();
    const declarado = declararBinding(
      declararBinding(
        declararBinding(fluxo, "0.MESES", "prazo de obra"),
        "1.COMP",
        "lado da placa",
      ),
      "1.LARG",
      "lado da placa",
    );

    const parametros = parametrosDaAutoria(declarado, parcelas, null);

    expect(parametros).toEqual([
      { nome: "prazo de obra", unidade: "mes", citadoPor: 1, novo: false },
      { nome: "lado da placa", unidade: "m", citadoPor: 2, novo: false },
    ]);
  });

  /**
   * "novo" é comparação contra o acervo de BASE, e só existe quando há base. No acervo novo
   * tudo seria novidade, e marcar tudo não diria nada.
   */
  it("marca como novo só o parâmetro que o acervo de base não citava", () => {
    const parcelas = parcelasAutoraveis(MATRIZ);
    let fluxo = escolherAcervoBase(
      escolherModoDeAutoria(autoriaInicial(), "versao"),
      KIT_DO_TENANT,
    );
    fluxo = declararVersaoDoAcervo(fluxo, "2");
    fluxo = declararBinding(fluxo, "0.MESES", "prazo de obra");
    fluxo = declararBinding(fluxo, "1.COMP", "caçambas de entulho");

    const comBase = parametrosDaAutoria(fluxo, parcelas, KIT_DO_TENANT);
    const semBase = parametrosDaAutoria(fluxo, parcelas, null);

    expect(comBase.map((parametro) => [parametro.nome, parametro.novo])).toEqual([
      ["prazo de obra", false],
      ["caçambas de entulho", true],
    ]);
    expect(semBase.every((parametro) => !parametro.novo)).toBe(true);
  });
});

describe("acervosVersionaveis", () => {
  /**
   * A rota grava sempre um acervo do tenant: "versão nova" de um acervo de plataforma
   * criaria um homônimo do tenant — bifurcação com aparência de continuação (ADR-0060).
   */
  it("só o acervo do próprio tenant ganha versão nova", () => {
    expect(
      acervosVersionaveis([KIT_DA_PLATAFORMA, KIT_DO_TENANT]).map((kit) => kit.kit_id),
    ).toEqual(["kit-do-tenant"]);
  });
});

describe("o portão do ato", () => {
  it("guarda quando modo, nome e versão estão declarados e há parcela gravada", () => {
    const { fluxo, parcelas } = fluxoPronto();

    expect(motivoDeAutoriaIndisponivel(fluxo, parcelas)).toBeNull();
    expect(podeAutorar(fluxo, parcelas)).toBe(true);
  });

  it("nomeia o motivo de estar indisponível, um de cada vez e na ordem de leitura", () => {
    const parcelas = parcelasAutoraveis(MATRIZ);
    const semParcelas = fluxoPronto().fluxo;
    const semModo = autoriaInicial();
    const semBase = escolherModoDeAutoria(autoriaInicial(), "versao");
    const semNome = declararVersaoDoAcervo(
      declararNomeDoAcervo(escolherModoDeAutoria(autoriaInicial(), "novo"), "ab"),
      "2",
    );
    const semVersao = declararNomeDoAcervo(
      escolherModoDeAutoria(autoriaInicial(), "novo"),
      "Canteiro do contrato",
    );

    expect(motivoDeAutoriaIndisponivel(semParcelas, [])).toBe("sem-parcelas");
    expect(motivoDeAutoriaIndisponivel(semModo, parcelas)).toBe("sem-modo");
    expect(motivoDeAutoriaIndisponivel(semBase, parcelas)).toBe("sem-acervo-base");
    expect(motivoDeAutoriaIndisponivel(semNome, parcelas)).toBe("sem-nome");
    expect(motivoDeAutoriaIndisponivel(semVersao, parcelas)).toBe("sem-versao");
    for (const fluxo of [semModo, semBase, semNome, semVersao]) {
      expect(podeAutorar(fluxo, parcelas)).toBe(false);
    }
  });

  /**
   * Nome repetido NÃO é barrado aqui: essa recusa é do servidor
   * (`409 SITE_SETUP_KIT_ALREADY_PUBLISHED`), que é a autoridade sobre a regra.
   * Reimplementá-la no cliente criaria duas.
   */
  it("não barra o nome que já existe: quem recusa isso é o servidor", () => {
    const parcelas = parcelasAutoraveis(MATRIZ);
    let fluxo = escolherAcervoBase(
      escolherModoDeAutoria(autoriaInicial(), "versao"),
      KIT_DO_TENANT,
    );
    fluxo = declararVersaoDoAcervo(fluxo, KIT_DO_TENANT.kit_version);

    expect(podeAutorar(fluxo, parcelas)).toBe(true);
  });
});

describe("o corpo do pedido", () => {
  it("no acervo novo leva o nome digitado, a versão e os bindings declarados", () => {
    const { fluxo } = fluxoPronto();
    const declarado = declararBinding(fluxo, "0.MESES", "prazo de obra");

    expect(authorSiteSetupKitBody({ baseVersion: 7, ...pedidoDaAutoria(declarado) })).toEqual(
      {
        base_version: 7,
        name: "Canteiro — contrato SMH/Rio",
        kit_version: "2",
        parameter_bindings: { "0.MESES": "prazo de obra" },
      },
    );
  });

  it("na versão nova leva o nome DO acervo de base, sem parâmetro quando nada foi declarado", () => {
    let fluxo = escolherAcervoBase(
      escolherModoDeAutoria(autoriaInicial(), "versao"),
      KIT_DO_TENANT,
    );
    fluxo = declararVersaoDoAcervo(fluxo, "  2.0.0  ");

    expect(authorSiteSetupKitBody({ baseVersion: 12, ...pedidoDaAutoria(fluxo) })).toEqual({
      base_version: 12,
      name: KIT_DO_TENANT.name,
      kit_version: "2.0.0",
      parameter_bindings: {},
    });
  });
});

describe("registrarAutoria", () => {
  /** `parcel_count` é do servidor: a tela não reconta o que ele já contou. */
  it("guarda o que foi salvo sem recontar nada", () => {
    const resposta: SiteSetupKitAuthoredResponse = {
      kit_id: "kit-novo",
      name: "Canteiro — contrato SMH/Rio",
      kit_version: "2",
      origin: "tenant",
      source_label: "PRACA CAMPO DO TOCA",
      parcel_count: 5,
      document_sha256: "a".repeat(64),
      available: true,
      created_by: "sub-orcamentista",
      created_at: "2026-09-04T10:00:00Z",
      withdrawn_at: null,
    };

    expect(registrarAutoria(resposta)).toEqual({
      kitId: "kit-novo",
      nome: "Canteiro — contrato SMH/Rio",
      versao: "2",
      parcelas: 5,
    });
  });
});
