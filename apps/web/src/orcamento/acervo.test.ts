import { describe, expect, it } from "vitest";

import {
  acervoGravado,
  alternarExclusao,
  avancarParaParametros,
  codigosBloqueantes,
  contribuicoesDoAcervo,
  declararParametro,
  escolherAcervo,
  estaExcluida,
  fluxoInicial,
  parcelaBloqueada,
  parcelasAplicaveis,
  parcelasBloqueadas,
  parcelasDeCanteiro,
  parametrosBloqueantes,
  parametrosDoCorpo,
  pedidoDaPrevia,
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
import {
  assembleCalcMatrix,
  contributionKey,
  disassembleCalcMatrix,
  type CalcContributionDraft,
} from "./matrix";
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
        { name: "UNIDADES", value: "1", unit: "un", parameter: null },
        { name: "PRAZO", value: "2", unit: "mes", parameter: "prazo de obra" },
      ],
      quantity: "2.00",
      missing_parameters: [],
      code_absent: false,
    },
    {
      parcel_id: "p2",
      code: "AC01100020",
      label: "Aluguel de container",
      operands: [
        { name: "UNIDADES", value: "1", unit: "un", parameter: null },
        { name: "PRAZO", value: "2", unit: "mes", parameter: "prazo de obra" },
      ],
      quantity: "2.00",
      missing_parameters: [],
      code_absent: false,
    },
    {
      parcel_id: "p3",
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
 * A mesma prévia, agora com duas parcelas que NÃO podem nascer — uma por parâmetro não
 * declarado, outra por código fora do catálogo.
 *
 * É a emenda de 2026-08-28 à decisão 5: a prévia MARCA em vez de recusar. Antes, o pedido
 * inteiro voltava recusado e a saída que a copy prometia ("remova na pré-visualização as
 * parcelas que os citam") não existia, porque não havia pré-visualização onde remover.
 */
const PREVIA_COM_BLOQUEIO: SiteSetupPreviewResponse = {
  ...PREVIA,
  rows: [
    PREVIA.rows[0],
    {
      ...PREVIA.rows[1],
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
    // Código ausente vem COM quantidade: a conta fecha, o que falta é o código no
    // catálogo da rodada (contrato confirmado pela T4).
    { ...PREVIA.rows[2], code_absent: true },
  ],
  blocked_parcel_ids: ["p2", "p3"],
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

/**
 * A parcela BLOQUEADA e a saída que ela abre. Este bloco é o defeito 1 desta task: a recusa
 * antiga era um beco sem saída — ela prometia "remova na pré-visualização as parcelas que
 * os citam" e acontecia ANTES de existir pré-visualização.
 */
describe("parcela bloqueada na prévia", () => {
  function fluxoComBloqueio(): FluxoDoAcervo {
    return receberPrevia(
      declararParametro(
        avancarParaParametros(escolherAcervo(fluxoInicial(), KIT.kit_id), KIT),
        "prazo de obra",
        "2",
      ),
      PREVIA_COM_BLOQUEIO,
    );
  }

  it("bloqueia por parâmetro faltante, por código ausente e pela lista do servidor", () => {
    const previa = PREVIA_COM_BLOQUEIO;

    expect(parcelaBloqueada(previa, previa.rows[0])).toBe(false);
    expect(parcelaBloqueada(previa, previa.rows[1])).toBe(true);
    expect(parcelaBloqueada(previa, previa.rows[2])).toBe(true);
    // Falha FECHADA: bloqueio que só o servidor conhece continua bloqueando, mesmo com a
    // linha sem nomear causa nenhuma.
    expect(
      parcelaBloqueada(
        { ...previa, blocked_parcel_ids: ["p1"] },
        previa.rows[0],
      ),
    ).toBe(true);
  });

  it("a bloqueada sai da conta e fecha o ato, com os faltantes nomeados", () => {
    const fluxo = fluxoComBloqueio();

    expect(parcelasBloqueadas(fluxo).map((row) => row.parcel_id)).toEqual([
      "p2",
      "p3",
    ]);
    // Ela não é contada entre as que vão nascer: o botão prometeria o que não materializa.
    expect(parcelasAplicaveis(fluxo).map((row) => row.parcel_id)).toEqual(["p1"]);
    expect(podeAplicar(fluxo)).toBe(false);
    expect(parametrosBloqueantes(fluxo)).toEqual([
      "semiperímetro",
      "altura do alambrado",
    ]);
    expect(codigosBloqueantes(fluxo)).toEqual(["AC02200030"]);
  });

  /**
   * **O teste do defeito corrigido.** Remover as bloqueadas destrava o ato — é a saída que
   * a copy prometia e que não existia.
   */
  it("remover as bloqueadas destrava o aplicar, e as demais continuam intactas", () => {
    let fluxo = fluxoComBloqueio();
    expect(podeAplicar(fluxo)).toBe(false);

    fluxo = alternarExclusao(fluxo, "p2");
    // Uma só não basta: a outra continua bloqueando, e o motivo continua nomeado.
    expect(podeAplicar(fluxo)).toBe(false);
    expect(parcelasBloqueadas(fluxo).map((row) => row.parcel_id)).toEqual(["p3"]);

    fluxo = alternarExclusao(fluxo, "p3");
    expect(parcelasBloqueadas(fluxo)).toEqual([]);
    expect(podeAplicar(fluxo)).toBe(true);
    // A que sempre pôde nascer atravessou tudo isso sem mudar.
    expect(parcelasAplicaveis(fluxo)).toEqual([PREVIA_COM_BLOQUEIO.rows[0]]);
  });

  it("trazer a bloqueada de volta fecha o ato outra vez", () => {
    const fluxo = alternarExclusao(
      alternarExclusao(alternarExclusao(fluxoComBloqueio(), "p2"), "p3"),
      "p2",
    );

    expect(podeAplicar(fluxo)).toBe(false);
    expect(parcelasBloqueadas(fluxo).map((row) => row.parcel_id)).toEqual(["p2"]);
  });

  it("sem parcela livre, remover as bloqueadas não inventa o que aplicar", () => {
    let fluxo = receberPrevia(fluxoInicial(), {
      ...PREVIA_COM_BLOQUEIO,
      kit_id: "",
      rows: PREVIA_COM_BLOQUEIO.rows.slice(1),
    });
    fluxo = alternarExclusao(alternarExclusao(fluxo, "p2"), "p3");

    expect(parcelasBloqueadas(fluxo)).toEqual([]);
    expect(parcelasAplicaveis(fluxo)).toEqual([]);
    expect(podeAplicar(fluxo)).toBe(false);
  });
});

/**
 * A remoção é LOCAL. A prévia devolve linha só para as parcelas não excluídas: pedir a
 * prévia citando as removidas as faria sumir da resposta — e o pacote de design exige que a
 * removida continue visível e riscada, com "Trazer de volta". Nenhuma rota devolve as
 * parcelas cruas do acervo fora da prévia, então uma linha que sumisse não voltaria.
 */
describe("a remoção é local, e a prévia é pedida sem exclusões", () => {
  it("o pedido da prévia nunca leva exclusão, mesmo com parcelas removidas", () => {
    const fluxo = alternarExclusao(alternarExclusao(fluxoComPrevia(), "p2"), "p3");

    expect(pedidoDaPrevia(fluxo)).toEqual({
      kitId: KIT.kit_id,
      parameters: { "prazo de obra": "2" },
      excludedParcelIds: [],
    });
  });

  it("prévia nova preserva as marcações locais em vez de adotar a lista vazia", () => {
    const comRemocao = alternarExclusao(fluxoComPrevia(), "p2");
    const outroParametro = declararParametro(comRemocao, "prazo de obra", "3");

    // A prévia recalculada volta com todas as linhas e sem exclusão nenhuma ecoada.
    const recalculada = receberPrevia(outroParametro, PREVIA);

    expect(estaExcluida(recalculada, "p2")).toBe(true);
    expect(recalculada.previa?.rows).toHaveLength(3);
    expect(parcelasAplicaveis(recalculada).map((row) => row.parcel_id)).toEqual([
      "p1",
      "p3",
    ]);
  });

  it("o que o servidor declarar excluído entra por cima, sem duplicar", () => {
    const fluxo = receberPrevia(alternarExclusao(fluxoComPrevia(), "p2"), {
      ...PREVIA,
      excluded_parcel_ids: ["p2", "p3"],
    });

    expect(fluxo.excluidos).toEqual(["p2", "p3"]);
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
    // O rascunho leva nome, valor e unidade; o `parameter` do fio fica de fora, porque a
    // matriz não guarda de qual parâmetro o operando saiu — ele é da prévia.
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

  /**
   * A parcela HIDRATADA não sabe de qual acervo nasceu — a matriz gravada leva
   * `{kit_version, parcel_id}` e nada mais. Sem alcançá-la pela lista de `parcel_id` da
   * resposta, reaplicar depois de recarregar deixaria de pé, em silêncio, a parcela que a
   * nova aplicação removeu.
   */
  it("a reaplicação alcança a parcela hidratada, que não sabe o acervo de origem", () => {
    const hidratadas = Object.fromEntries(
      disassembleCalcMatrix(
        assembleCalcMatrix(contribuicoesDoAcervo(KIT, PREVIA, PREVIA.rows)),
      ).map((draft) => [contributionKey(draft.itemId, draft.code), draft]),
    );
    const mao = autoradaAMao();
    const atual = { ...hidratadas, [contributionKey(mao.itemId, mao.code)]: mao };
    expect(atual[contributionKey("p1", "AC01100010")]?.kitOrigin?.kitId).toBe("");

    // Reaplica só a primeira; a resposta enumera as três parcelas do acervo.
    const proximo = substituirParcelasDoAcervo(
      atual,
      KIT.kit_id,
      contribuicoesDoAcervo(KIT, PREVIA, [PREVIA.rows[0]]),
      PREVIA.rows.map((row) => row.parcel_id),
    );

    expect(proximo[contributionKey("p1", "AC01100010")]?.kitOrigin?.kitId).toBe(
      KIT.kit_id,
    );
    expect(proximo[contributionKey("p2", "AC01100020")]).toBeUndefined();
    expect(proximo[contributionKey("p3", "AC02200030")]).toBeUndefined();
    // A autorada à mão continua intocada, como em toda reaplicação.
    expect(proximo[contributionKey("entulho-extra", "AC09900001")]).toEqual(mao);
  });
});

/** O carimbo possível depois de um recarregamento: versão e contagem, e nada mais. */
describe("o que a matriz gravada diz de acervo", () => {
  it("conta as parcelas por versão e ignora as autoradas à mão", () => {
    const doAcervo = contribuicoesDoAcervo(KIT, PREVIA, PREVIA.rows);
    const deOutraVersao = contribuicoesDoAcervo(
      KIT,
      { ...PREVIA, kit_version: 3 },
      [PREVIA.rows[0]],
    );

    expect(acervoGravado([...doAcervo, autoradaAMao(), ...deOutraVersao])).toEqual([
      { kitVersion: 1, parcelas: 3 },
      { kitVersion: 3, parcelas: 1 },
    ]);
  });

  it("rodada sem parcela de acervo não produz carimbo nenhum", () => {
    expect(acervoGravado([autoradaAMao()])).toEqual([]);
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
