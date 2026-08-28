import { describe, expect, it } from "vitest";

import {
  alternarExclusao,
  avancarParaParametros,
  contribuicoesDoAcervo,
  declararParametro,
  escolherAcervo,
  estaExcluida,
  fluxoInicial,
  parcelasAplicaveis,
  parcelasDeCanteiro,
  parametrosDoCorpo,
  podeAplicar,
  podeAvancarParaParametros,
  receberPrevia,
  registrarAplicacao,
  substituirParcelasDoAcervo,
  voltarParaParametros,
  type FluxoDoAcervo,
  type SiteSetupKit,
  type SiteSetupPreviewResponse,
} from "./acervo";
import { assembleCalcMatrix, contributionKey, type CalcContributionDraft } from "./matrix";
import { siteSetupApplyBody, siteSetupPreviewBody } from "./requests";

const KIT: SiteSetupKit = {
  kit_id: "kit-canteiro-smh",
  name: "Canteiro — contrato SMH/Rio",
  kit_version: 1,
  origin: "platform",
  source_label: "acervo da plataforma",
  parcel_count: 3,
  parameters: [
    { name: "prazo de obra", unit: "mes", cited_by: 2 },
    { name: "semiperímetro", unit: "m", cited_by: 1 },
    { name: "dias de vigia", unit: null, cited_by: 1 },
  ],
  created_at: "2026-08-12T10:00:00Z",
};

const PREVIA: SiteSetupPreviewResponse = {
  round_id: "round-1",
  version: 7,
  kit_id: KIT.kit_id,
  kit_version: 1,
  rows: [
    {
      parcel_id: "p1",
      code: "AC01100010",
      label: "Aluguel de banheiro químico",
      operands: [
        { name: "UNIDADES", value: "1", unit: "un" },
        { name: "PRAZO", value: "2", unit: "mes" },
      ],
      quantity: "2.00",
    },
    {
      parcel_id: "p2",
      code: "AC01100020",
      label: "Aluguel de container",
      operands: [
        { name: "UNIDADES", value: "1", unit: "un" },
        { name: "PRAZO", value: "2", unit: "mes" },
      ],
      quantity: "2.00",
    },
    {
      parcel_id: "p3",
      code: "AC02200030",
      label: "Vigia diurno",
      operands: [
        { name: "DIAS", value: "23", unit: null },
        { name: "HORAS", value: "12", unit: "h" },
      ],
      quantity: "276.00",
    },
  ],
  excluded_parcel_ids: [],
};

/** O fluxo já no passo 3, que é o único de onde a aplicação sai. */
function fluxoComPrevia(): FluxoDoAcervo {
  const escolhido = escolherAcervo(fluxoInicial(), KIT.kit_id);
  const comCampos = avancarParaParametros(escolhido, KIT);
  const declarado = declararParametro(comCampos, "prazo de obra", "2");
  return receberPrevia(declarado, PREVIA);
}

/** Uma parcela autorada à MÃO: `STANDALONE` como as do acervo, e sem proveniência. */
function autoradaAMao(): CalcContributionDraft {
  return {
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
}

describe("os três passos", () => {
  it("nasce no passo 1, sem acervo escolhido e sem nada declarado", () => {
    const fluxo = fluxoInicial();

    expect(fluxo.passo).toBe("acervo");
    expect(fluxo.kitId).toBe("");
    expect(fluxo.parametros).toEqual({});
    expect(fluxo.previa).toBeNull();
    expect(podeAvancarParaParametros(fluxo)).toBe(false);
  });

  /** Decisão 4 do pacote: o sistema nunca infere nem pré-preenche um parâmetro. */
  it("cria um campo VAZIO por parâmetro citado, e nenhum valor", () => {
    const fluxo = avancarParaParametros(
      escolherAcervo(fluxoInicial(), KIT.kit_id),
      KIT,
    );

    expect(fluxo.passo).toBe("parametros");
    expect(Object.keys(fluxo.parametros)).toEqual([
      "prazo de obra",
      "semiperímetro",
      "dias de vigia",
    ]);
    expect(Object.values(fluxo.parametros)).toEqual(["", "", ""]);
  });

  it("trocar de acervo descarta o que foi declarado para o anterior", () => {
    const declarado = declararParametro(
      avancarParaParametros(escolherAcervo(fluxoInicial(), KIT.kit_id), KIT),
      "prazo de obra",
      "2",
    );

    const outro = escolherAcervo(declarado, "kit-reduzido");

    expect(outro.kitId).toBe("kit-reduzido");
    expect(outro.parametros).toEqual({});
    expect(outro.passo).toBe("acervo");
  });
});

/**
 * O ponto inegociável da feature: o ganho é não digitar, e o risco é aplicar sem olhar. A
 * pré-visualização é o controle, e não existe caminho que a pule.
 */
describe("não existe caminho que aplique sem passar pela prévia", () => {
  it("recusa aplicar no passo 1 e no passo 2, mesmo com tudo declarado", () => {
    const escolhido = escolherAcervo(fluxoInicial(), KIT.kit_id);
    expect(podeAplicar(escolhido)).toBe(false);

    let comParametros = avancarParaParametros(escolhido, KIT);
    for (const parametro of KIT.parameters) {
      comParametros = declararParametro(comParametros, parametro.name, "2");
    }
    expect(comParametros.passo).toBe("parametros");
    expect(podeAplicar(comParametros)).toBe(false);
  });

  it("libera aplicar só no passo 3, com a prévia do acervo escolhido", () => {
    expect(podeAplicar(fluxoComPrevia())).toBe(true);
  });

  it("voltar aos parâmetros descarta a prévia e fecha o caminho de novo", () => {
    const devolvido = voltarParaParametros(fluxoComPrevia());

    expect(devolvido.previa).toBeNull();
    expect(podeAplicar(devolvido)).toBe(false);
  });

  it("mexer num parâmetro invalida a prévia: ela vale para os números que a geraram", () => {
    const mexido = declararParametro(fluxoComPrevia(), "prazo de obra", "3");

    expect(mexido.previa).toBeNull();
    expect(podeAplicar(mexido)).toBe(false);
  });

  it("prévia de OUTRO acervo não serve para aplicar o escolhido", () => {
    const trocado = { ...fluxoComPrevia(), kitId: "kit-reduzido" };

    expect(podeAplicar(trocado)).toBe(false);
  });

  it("sem nenhuma parcela por nascer não há o que aplicar", () => {
    let fluxo = fluxoComPrevia();
    for (const row of PREVIA.rows) {
      fluxo = alternarExclusao(fluxo, row.parcel_id);
    }

    expect(parcelasAplicaveis(fluxo)).toEqual([]);
    expect(podeAplicar(fluxo)).toBe(false);
  });
});

/** Decisão 6: a parcela removida sai da conta, não da tela — e é reversível até aplicar. */
describe("remoção por parcela", () => {
  it("remover uma não altera as demais", () => {
    const fluxo = alternarExclusao(fluxoComPrevia(), "p2");

    expect(estaExcluida(fluxo, "p2")).toBe(true);
    expect(parcelasAplicaveis(fluxo).map((row) => row.parcel_id)).toEqual([
      "p1",
      "p3",
    ]);
    // As que ficaram são as MESMAS linhas, com a mesma conta e a mesma quantidade.
    expect(parcelasAplicaveis(fluxo)[0]).toEqual(PREVIA.rows[0]);
    expect(parcelasAplicaveis(fluxo)[1]).toEqual(PREVIA.rows[2]);
  });

  it("a removida continua na prévia, para a tela poder mostrá-la riscada", () => {
    const fluxo = alternarExclusao(fluxoComPrevia(), "p2");

    expect(fluxo.previa?.rows.map((row) => row.parcel_id)).toEqual([
      "p1",
      "p2",
      "p3",
    ]);
  });

  it("é reversível: o mesmo gesto traz a parcela de volta", () => {
    const fluxo = alternarExclusao(alternarExclusao(fluxoComPrevia(), "p2"), "p2");

    expect(estaExcluida(fluxo, "p2")).toBe(false);
    expect(parcelasAplicaveis(fluxo)).toHaveLength(3);
    expect(podeAplicar(fluxo)).toBe(true);
  });
});

describe("parâmetros no corpo", () => {
  /**
   * Campo vazio é OMITIDO: `""` não é "declarei vazio", é a ausência da declaração — e é
   * dela que o servidor lê o faltante, para recusar nomeando todos.
   */
  it("omite o não declarado em vez de mandar string vazia", () => {
    const fluxo = declararParametro(
      avancarParaParametros(escolherAcervo(fluxoInicial(), KIT.kit_id), KIT),
      "prazo de obra",
      "2",
    );

    expect(parametrosDoCorpo(fluxo)).toEqual({ "prazo de obra": "2" });
  });

  /** Conversão de NOTAÇÃO, nunca de valor: nenhum dígito entra, sai ou é arredondado. */
  it("normaliza a pontuação pt-BR e mantém o decimal como texto", () => {
    let fluxo = avancarParaParametros(escolherAcervo(fluxoInicial(), KIT.kit_id), KIT);
    fluxo = declararParametro(fluxo, "semiperímetro", "132,21");
    fluxo = declararParametro(fluxo, "dias de vigia", "23");

    const corpo = parametrosDoCorpo(fluxo);

    expect(corpo).toEqual({ "semiperímetro": "132.21", "dias de vigia": "23" });
    expect(typeof corpo["semiperímetro"]).toBe("string");
  });

  it("texto que não é decimal viaja como foi escrito, para o servidor recusá-lo", () => {
    const fluxo = declararParametro(
      avancarParaParametros(escolherAcervo(fluxoInicial(), KIT.kit_id), KIT),
      "prazo de obra",
      "dois meses",
    );

    expect(parametrosDoCorpo(fluxo)).toEqual({ "prazo de obra": "dois meses" });
  });
});

describe("corpos das duas rotas", () => {
  /** A prévia não grava nada e não avança a rodada: citar versão a faria parecer um ato. */
  it("o corpo da prévia não leva base_version", () => {
    const corpo = siteSetupPreviewBody({
      kitId: KIT.kit_id,
      parameters: { "prazo de obra": "2" },
      excludedParcelIds: ["p2"],
    });

    expect(corpo).toEqual({
      kit_id: KIT.kit_id,
      parameters: { "prazo de obra": "2" },
      excluded_parcel_ids: ["p2"],
    });
    expect(corpo.base_version).toBeUndefined();
  });

  it("o corpo da aplicação repete a prévia e acrescenta a guarda otimista", () => {
    expect(
      siteSetupApplyBody({
        kitId: KIT.kit_id,
        parameters: { "prazo de obra": "2" },
        excludedParcelIds: [],
        baseVersion: 7,
      }),
    ).toEqual({
      base_version: 7,
      kit_id: KIT.kit_id,
      parameters: { "prazo de obra": "2" },
      excluded_parcel_ids: [],
    });
  });
});

describe("da aplicação para a matriz", () => {
  it("copia operandos e quantidade do servidor, sem recalcular nada", () => {
    const [primeira] = contribuicoesDoAcervo(KIT, PREVIA, [PREVIA.rows[0]]);

    expect(primeira.basis).toBe("standalone");
    expect(primeira.operands).toEqual([
      { name: "UNIDADES", value: "1", unit: "un" },
      { name: "PRAZO", value: "2", unit: "mes" },
    ]);
    // A quantidade é a string do servidor, guardada para exibição — nunca recomputada.
    expect(primeira.kitQuantity).toBe("2.00");
    expect(primeira.kitOrigin).toEqual({
      kitId: KIT.kit_id,
      kitName: KIT.name,
      kitVersion: 1,
      parcelId: "p1",
    });
  });

  /**
   * `STANDALONE` proíbe `source_item_id` (validação já existente do domínio): o `parcel_id`
   * é só a chave de tela, e não pode vazar para o fio como elemento de origem.
   */
  it("no fio a parcela do acervo não cita elemento de origem", () => {
    const matriz = assembleCalcMatrix(contribuicoesDoAcervo(KIT, PREVIA, PREVIA.rows));
    const contribuicoes = matriz?.services.flatMap((service) => service.contributions);

    expect(contribuicoes?.every((c) => c.source_item_id === null)).toBe(true);
    expect(contribuicoes?.[0]?.kit_origin).toEqual({
      kit_version: 1,
      parcel_id: "p1",
    });
  });

  /** Sem proveniência a matriz sai como antes da feature: a chave nem aparece. */
  it("parcela autorada à mão continua sem a chave de proveniência", () => {
    const matriz = assembleCalcMatrix([autoradaAMao()]);
    const contribuicao = matriz?.services[0]?.contributions[0];

    expect(contribuicao).not.toHaveProperty("kit_origin");
  });
});

/** Decisão 8: reaplicar substitui as do mesmo acervo e nunca toca as autoradas à mão. */
describe("reaplicação", () => {
  function comAcervoAplicado(): Record<string, CalcContributionDraft> {
    const mao = autoradaAMao();
    const doAcervo = contribuicoesDoAcervo(KIT, PREVIA, PREVIA.rows);
    const mapa: Record<string, CalcContributionDraft> = {
      [contributionKey(mao.itemId, mao.code)]: mao,
    };
    for (const draft of doAcervo) {
      mapa[contributionKey(draft.itemId, draft.code)] = draft;
    }
    return mapa;
  }

  it("substitui as parcelas do acervo e preserva a autorada à mão", () => {
    const atual = comAcervoAplicado();
    const novas = contribuicoesDoAcervo(KIT, PREVIA, [PREVIA.rows[0]]);

    const proximo = substituirParcelasDoAcervo(atual, KIT.kit_id, novas);

    expect(Object.keys(proximo)).toHaveLength(2);
    expect(proximo[contributionKey("entulho-extra", "AC09900001")]).toEqual(
      autoradaAMao(),
    );
    expect(proximo[contributionKey("p1", "AC01100010")]?.label).toBe(
      "Aluguel de banheiro químico",
    );
    // As duas que não foram reaplicadas saíram: reaplicar não duplica nem acumula.
    expect(proximo[contributionKey("p2", "AC01100020")]).toBeUndefined();
  });

  it("não toca nas parcelas de OUTRO acervo", () => {
    const deOutro = contribuicoesDoAcervo(
      { ...KIT, kit_id: "kit-reduzido", name: "Canteiro reduzido" },
      { ...PREVIA, kit_id: "kit-reduzido" },
      [PREVIA.rows[2]],
    );
    const atual = {
      ...comAcervoAplicado(),
      [contributionKey("p3", "AC02200030")]: deOutro[0],
    };

    const proximo = substituirParcelasDoAcervo(atual, KIT.kit_id, []);

    expect(proximo[contributionKey("p3", "AC02200030")]?.kitOrigin?.kitId).toBe(
      "kit-reduzido",
    );
    expect(proximo[contributionKey("entulho-extra", "AC09900001")]).toBeDefined();
  });

  it("lista como parcela de canteiro toda contribuição STANDALONE, das duas origens", () => {
    const parcelas = parcelasDeCanteiro(comAcervoAplicado());

    expect(parcelas).toHaveLength(4);
    expect(parcelas.filter((p) => p.kitOrigin === undefined)).toHaveLength(1);
  });
});

describe("carimbo da aplicação", () => {
  it("registra acervo, versão, parâmetros usados e quantas parcelas nasceram", () => {
    const carimbo = registrarAplicacao(
      KIT,
      PREVIA,
      { "prazo de obra": "2" },
      3,
      "2026-08-28T14:02:00Z",
    );

    expect(carimbo).toEqual({
      kitId: KIT.kit_id,
      kitName: KIT.name,
      kitVersion: 1,
      parametros: { "prazo de obra": "2" },
      parcelas: 3,
      appliedAt: "2026-08-28T14:02:00Z",
    });
  });
});
