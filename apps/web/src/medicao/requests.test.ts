import { describe, expect, it } from "vitest";
import {
  appendPlatesBody,
  codeClosureBody,
  codeDecisionBody,
  codeRevocationBody,
  codeSearchTerm,
  createRoundBody,
  identityLinkBody,
  identityLinkPreviewBody,
  plateBody,
  platesExtractionBody,
  priceAdjustmentBody,
  takeoffDecisionBody,
  versionBody,
  worksiteKeyError,
} from "./requests";

describe("versionBody", () => {
  it("toda mutação leva a guarda de concorrência da rodada e nada além dela", () => {
    expect(versionBody(7)).toEqual({ base_version: 7 });
  });
});

/** As decisões do lote, já no formato do corpo, para inspeção item a item. */
function decisoesDoCorpo(
  body: Record<string, unknown>,
): Record<string, unknown>[] {
  return body.decisions as Record<string, unknown>[];
}

describe("takeoffDecisionBody", () => {
  it("a versão-base é UMA para o lote inteiro e nunca carimba identidade ou horário", () => {
    const body = takeoffDecisionBody({
      baseVersion: 7,
      decisions: [
        {
          itemId: "ti_af6f85a49ea0b93d",
          action: "confirm",
          quantity: "18.40",
          note: "quantidade lida na prancha",
        },
      ],
    });

    expect(body).toEqual({
      base_version: 7,
      decisions: [
        {
          item_id: "ti_af6f85a49ea0b93d",
          action: "confirm",
          quantity: "18.40",
          note: "quantidade lida na prancha",
        },
      ],
    });
    for (const forbidden of [
      "reviewer_id",
      "reviewer_role",
      "decided_at",
      "decision_id",
    ]) {
      expect(Object.keys(body)).not.toContain(forbidden);
      expect(Object.keys(decisoesDoCorpo(body)[0])).not.toContain(forbidden);
    }
  });

  it("o lote leva todas as decisões na ordem em que foram anotadas, e só uma versão-base", () => {
    const body = takeoffDecisionBody({
      baseVersion: 7,
      decisions: [
        { itemId: "ti_af6f85a49ea0b93d", action: "confirm", quantity: "18.40" },
        { itemId: "ti_af6f85a49ea0b93e", action: "reject" },
        { itemId: "ti_af6f85a49ea0b93f", action: "confirm", quantity: "3.00" },
      ],
    });

    expect(body.base_version).toBe(7);
    expect(decisoesDoCorpo(body).map((decisao) => decisao.item_id)).toEqual([
      "ti_af6f85a49ea0b93d",
      "ti_af6f85a49ea0b93e",
      "ti_af6f85a49ea0b93f",
    ]);
    // A versão-base não se repete dentro de decisão nenhuma: ela é do ato, não do item.
    for (const decisao of decisoesDoCorpo(body)) {
      expect(decisao).not.toHaveProperty("base_version");
    }
  });

  it("omite campo em branco em vez de mandar correção vazia", () => {
    const body = takeoffDecisionBody({
      baseVersion: 9,
      decisions: [
        {
          itemId: "ti_af6f85a49ea0b93d",
          action: "reject",
          quantity: "   ",
          unit: "",
          note: "  área de referência da prancha  ",
          itemNote: undefined,
        },
      ],
    });

    expect(body).toEqual({
      base_version: 9,
      decisions: [
        {
          item_id: "ti_af6f85a49ea0b93d",
          action: "reject",
          note: "área de referência da prancha",
        },
      ],
    });
  });

  it("manda a quantidade como texto: o decimal escrito não passa por número", () => {
    const body = takeoffDecisionBody({
      baseVersion: 3,
      decisions: [
        {
          itemId: "ti_af6f85a49ea0b93d",
          action: "confirm",
          quantity: "58.50",
          unit: "m2",
        },
      ],
    });

    expect(decisoesDoCorpo(body)[0].quantity).toBe("58.50");
    expect(typeof decisoesDoCorpo(body)[0].quantity).toBe("string");
  });
});

describe("codeDecisionBody", () => {
  it("confirmação leva o código escolhido e a versão-base", () => {
    const body = codeDecisionBody({
      itemId: "ti_af6f85a49ea0b93d",
      action: "confirm",
      baseVersion: 11,
      code: "AD04050060(/)",
    });

    expect(body).toEqual({
      base_version: 11,
      item_id: "ti_af6f85a49ea0b93d",
      action: "confirm",
      code: "AD04050060(/)",
    });
  });

  /** A rota recusa `code` na rejeição: o item vira candidato a aditivo, não escolha. */
  it("rejeição leva a justificativa e nunca o código", () => {
    const body = codeDecisionBody({
      itemId: "ti_af6f85a49ea0b93d",
      action: "reject",
      baseVersion: 12,
      code: "AD04050060(/)",
      note: "sem cotação aplicável no contrato",
    });

    expect(body).toEqual({
      base_version: 12,
      item_id: "ti_af6f85a49ea0b93d",
      action: "reject",
      note: "sem cotação aplicável no contrato",
    });
    expect(Object.keys(body)).not.toContain("code");
  });
});

describe("worksiteKeyError", () => {
  /**
   * A chave é imutável na rodada e o padrão é o mesmo que o domínio exige do boletim:
   * recusá-la aqui evita uma rodada que nasce válida e só quebra no fechamento.
   */
  it("aceita a forma que o domínio exige", () => {
    expect(worksiteKeyError("praca-sintetica-oeste")).toBeNull();
    expect(worksiteKeyError("  praca-01  ")).toBeNull();
  });

  it("recusa maiúscula, acento, espaço e chave curta demais, dizendo por quê", () => {
    for (const invalida of ["PRAÇA X", "praça-x", "praca oeste", "ab", "-praca"]) {
      const erro = worksiteKeyError(invalida);
      expect(erro).not.toBeNull();
      expect(erro).toContain("minúsculas, números e hífen");
    }
  });

  it("campo vazio pede a chave em vez de descrever o padrão", () => {
    expect(worksiteKeyError("   ")).toBe("Informe a chave da obra.");
  });
});

describe("createRoundBody", () => {
  it("monta a identidade da obra com o período como inteiro e o catálogo por upload", () => {
    const body = createRoundBody({
      worksiteKey: " praca-sintetica-oeste ",
      worksiteName: "Praça Sintética Oeste",
      catalogUploadId: "0197f2a0-0000-7000-8000-0000000000bb",
      periodNumber: "3",
      referenceLabel: "3ª MEDIÇÃO",
      address: "",
      contractLabel: "Contrato 05/2024",
    });

    expect(body).toEqual({
      worksite_key: "praca-sintetica-oeste",
      worksite_name: "Praça Sintética Oeste",
      catalog_upload_id: "0197f2a0-0000-7000-8000-0000000000bb",
      period_number: 3,
      reference_label: "3ª MEDIÇÃO",
      contract_label: "Contrato 05/2024",
    });
  });

  /**
   * A obra NÃO vai no corpo quando a origem é o orçamento assinado, e a omissão é a regra:
   * ela vem do conteúdo aprovado e o servidor recusa quem a declarar. Aceitá-la abriria a
   * porta para a rodada medir uma praça diferente da que foi orçada (F-036, ADR-0048).
   */
  it("na origem por orçamento assinado, a obra e o endereço não são declarados", () => {
    const body = createRoundBody({
      worksiteKey: "praca-que-nao-deve-ir",
      worksiteName: "Praça que não deve ir",
      estimateRoundId: "0197f2a0-0000-7000-8000-0000000000cc",
      periodNumber: "1",
      referenceLabel: "1ª MEDIÇÃO",
      address: "Rua que não deve ir, 100",
    });

    expect(body).toEqual({
      estimate_round_id: "0197f2a0-0000-7000-8000-0000000000cc",
      period_number: 1,
      reference_label: "1ª MEDIÇÃO",
    });
  });

  it("na origem por orçamento, o rótulo do contrato continua sendo da rodada", () => {
    const body = createRoundBody({
      worksiteKey: "",
      worksiteName: "",
      estimateRoundId: "0197f2a0-0000-7000-8000-0000000000cc",
      periodNumber: "2",
      referenceLabel: "2ª MEDIÇÃO",
      contractLabel: "Contrato 05/2024",
    });

    expect(body.contract_label).toBe("Contrato 05/2024");
    expect(body.worksite_key).toBeUndefined();
  });

  it("na medição seguinte, cita a rodada anterior e não declara obra (F-040)", () => {
    const body = createRoundBody({
      worksiteKey: "praca-que-nao-deve-ir",
      worksiteName: "Praça que não deve ir",
      previousRoundId: "0197f2a0-0000-7000-8000-0000000000dd",
      periodNumber: "2",
      referenceLabel: "2ª MEDIÇÃO",
      address: "Rua que não deve ir",
    });

    expect(body).toEqual({
      previous_round_id: "0197f2a0-0000-7000-8000-0000000000dd",
      period_number: 2,
      reference_label: "2ª MEDIÇÃO",
    });
  });

  it("leva a RE-RA declarada, sem preço de item novo (o servidor materializa)", () => {
    const body = createRoundBody({
      worksiteKey: "",
      worksiteName: "",
      estimateRoundId: "0197f2a0-0000-7000-8000-0000000000cc",
      periodNumber: "1",
      referenceLabel: "1ª MEDIÇÃO",
      amendment: {
        label: " 1ª RE-RA ",
        referencePeriod: " Processo 123/2026 ",
        lines: [
          { code: " CE04100010(/) ", quantityDelta: " -4,00 " },
          { code: "CE04100020(/)", quantityDelta: "6,00", isNewItem: true },
          { code: "", quantityDelta: "" },
        ],
      },
    });

    expect(body.amendment).toEqual({
      label: "1ª RE-RA",
      reference_period: "Processo 123/2026",
      lines: [
        { code: "CE04100010(/)", quantity_delta: "-4,00" },
        { code: "CE04100020(/)", quantity_delta: "6,00", is_new_item: true },
      ],
    });
  });
});

describe("codeSearchTerm", () => {
  it("remove o sufixo de variante entre parênteses, mantendo o código base", () => {
    expect(codeSearchTerm("AD04050060(/)")).toBe("AD04050060");
    expect(codeSearchTerm("PJ24050153(B)")).toBe("PJ24050153");
  });

  it("código sem sufixo volta sem alteração", () => {
    expect(codeSearchTerm("IE00040849")).toBe("IE00040849");
  });

  it("ignora espaço nas pontas antes e depois de remover o sufixo", () => {
    expect(codeSearchTerm("  AD04050060(/)  ")).toBe("AD04050060");
  });

  it("cai nos dez primeiros caracteres quando remover o sufixo não deixa nada", () => {
    // Caso degenerado (nunca visto num código SCO real: a base tem sempre dez
    // caracteres antes do parêntese) que só existe para exercitar o fallback.
    expect(codeSearchTerm("(ABCDEFGHIJKLMNO)")).toBe("(ABCDEFGHI");
  });
});

describe("fechamento de pacote de serviços", () => {
  it("o fechamento fala do ELEMENTO: não leva código nem fonte", () => {
    expect(
      codeClosureBody({
        itemId: "ti_af6f85a49ea0b93d",
        baseVersion: 4,
      }),
    ).toEqual({
      base_version: 4,
      item_id: "ti_af6f85a49ea0b93d",
    });
  });

  it("a nota é opcional e viaja aparada quando existe", () => {
    expect(
      codeClosureBody({
        itemId: "ti_af6f85a49ea0b93d",
        baseVersion: 4,
        note: "  o alambrado é a estrutura mais a tela; não há terceiro serviço  ",
      }),
    ).toEqual({
      base_version: 4,
      item_id: "ti_af6f85a49ea0b93d",
      note: "o alambrado é a estrutura mais a tela; não há terceiro serviço",
    });
  });

  it("nota em branco é omitida, nunca enviada como string vazia", () => {
    const body = codeClosureBody({
      itemId: "ti_af6f85a49ea0b93d",
      baseVersion: 4,
      note: "   ",
    });

    expect(Object.keys(body)).not.toContain("note");
  });
});

describe("priceAdjustmentBody", () => {
  it("sem declaração o corpo não leva reajuste nenhum", () => {
    expect(priceAdjustmentBody(undefined)).toBeNull();
  });

  it("por índice leva fator, índice e período — e nada da outra forma", () => {
    const corpo = priceAdjustmentBody({
      kind: "index_factor",
      referencePeriod: "08/2025 a 07/2026",
      indexLabel: "INCC-DI",
      factor: "1,0432",
    });

    expect(corpo).toEqual({
      kind: "index_factor",
      reference_period: "08/2025 a 07/2026",
      index_label: "INCC-DI",
      factor: "1,0432",
    });
    // Os dois mecanismos não se misturam: mandar os dois seria declarar duas coisas
    // fingindo ser uma.
    expect(corpo).not.toHaveProperty("catalog_upload_id");
  });

  it("por versão de tabela leva o catálogo, e nunca o fator", () => {
    const corpo = priceAdjustmentBody({
      kind: "catalog_version",
      referencePeriod: "data-base 07/2026",
      catalogUploadId: "01930000-0000-7000-8000-0000000000aa",
      // Resíduo do formulário anterior: o corpo não pode carregá-lo.
      factor: "1,0432",
      indexLabel: "INCC-DI",
    });

    expect(corpo).toEqual({
      kind: "catalog_version",
      reference_period: "data-base 07/2026",
      catalog_upload_id: "01930000-0000-7000-8000-0000000000aa",
    });
  });

  it("campo em branco não viaja: string vazia não é “sem índice”", () => {
    const corpo = priceAdjustmentBody({
      kind: "index_factor",
      referencePeriod: "08/2025 a 07/2026",
      indexLabel: "  ",
      factor: "1,0432",
      note: "   ",
    });

    expect(corpo).not.toHaveProperty("index_label");
    expect(corpo).not.toHaveProperty("note");
  });

  it("o fator viaja como TEXTO: o decimal escrito não passa por número", () => {
    const corpo = priceAdjustmentBody({
      kind: "index_factor",
      referencePeriod: "08/2025 a 07/2026",
      indexLabel: "INCC-DI",
      factor: "1,0432",
    });

    expect(typeof corpo?.factor).toBe("string");
  });
});

/**
 * Os corpos do lote da praça (F-046 T4). A regra que eles guardam é a mesma da tela: a
 * escolha é explícita, e nada é acrescentado por conveniência do cliente.
 */
describe("os lotes da praça", () => {
  it("promover manda a guarda de concorrência, o documento e as páginas escolhidas", () => {
    const corpo = appendPlatesBody("0197f2a0-0000-7000-8000-0000000000aa", [3, 1], 7);

    expect(corpo).toEqual({
      base_version: 7,
      upload_id: "0197f2a0-0000-7000-8000-0000000000aa",
      page_numbers: [3, 1],
    });
  });

  it("página repetida no lote não vira duas folhas", () => {
    const corpo = appendPlatesBody("0197f2a0-0000-7000-8000-0000000000aa", [2, 2, 4], 7);

    expect(corpo.page_numbers).toEqual([2, 4]);
  });

  /**
   * Lote vazio VIAJA: a recusa (`ROUND_PLATE_PAGES_REQUIRED`) é do servidor, e um corpo
   * inventado aqui — uma página "por padrão" — seria a escolha explícita contornada pelo
   * cliente.
   */
  it("lote vazio sai vazio, para o servidor recusar", () => {
    expect(appendPlatesBody("0197f2a0-0000-7000-8000-0000000000aa", [], 7).page_numbers).toEqual(
      [],
    );
    expect(platesExtractionBody([], 7).plate_ids).toEqual([]);
  });

  it("o lote de leitura manda as folhas marcadas, sem repetir e sem carimbar identidade", () => {
    const corpo = platesExtractionBody(["planta-geral", "detalhe", "planta-geral"], 9);

    expect(corpo).toEqual({
      base_version: 9,
      plate_ids: ["planta-geral", "detalhe"],
    });
    expect(corpo).not.toHaveProperty("reviewer_id");
    expect(corpo).not.toHaveProperty("requested_at");
  });
});

/**
 * A folha no corpo dos atos por folha (F-046 T4c/T4d).
 *
 * A regra que estes testes guardam é a da OMISSÃO: folha ausente não viaja, e é por isso
 * que o corpo da rodada de uma prancha continua idêntico ao de antes da praça.
 */
describe("a folha no corpo dos atos", () => {
  it("folha ausente, vazia ou em branco não vira campo nenhum", () => {
    expect(plateBody(undefined)).toEqual({});
    expect(plateBody("")).toEqual({});
    expect(plateBody("   ")).toEqual({});
    expect(plateBody("detalhe")).toEqual({ plate_id: "detalhe" });
  });

  it("o lote de revisão nomeia a folha do ATO, e não de cada decisão", () => {
    const corpo = takeoffDecisionBody({
      baseVersion: 7,
      plateId: "detalhe",
      decisions: [{ itemId: "ti_1", action: "confirm" }],
    });

    expect(corpo.plate_id).toBe("detalhe");
    expect(decisoesDoCorpo(corpo)[0]).not.toHaveProperty("plate_id");
  });

  it("sem folha, os quatro corpos saem exatamente como saíam antes da praça", () => {
    expect(
      takeoffDecisionBody({
        baseVersion: 7,
        decisions: [{ itemId: "ti_1", action: "confirm" }],
      }),
    ).toEqual({
      base_version: 7,
      decisions: [{ item_id: "ti_1", action: "confirm" }],
    });
    expect(
      codeDecisionBody({
        itemId: "ti_1",
        action: "confirm",
        baseVersion: 7,
        code: "04.02.010",
      }),
    ).toEqual({ base_version: 7, item_id: "ti_1", action: "confirm", code: "04.02.010" });
    expect(codeClosureBody({ itemId: "ti_1", baseVersion: 7 })).toEqual({
      base_version: 7,
      item_id: "ti_1",
    });
    expect(
      codeRevocationBody({
        itemId: "ti_1",
        code: "04.02.010",
        baseVersion: 7,
        note: "código trocado por engano",
      }),
    ).toEqual({
      base_version: 7,
      item_id: "ti_1",
      code: "04.02.010",
      note: "código trocado por engano",
    });
  });

  it("com folha, os três atos de código a nomeiam — `item_id` não é único entre folhas", () => {
    expect(
      codeDecisionBody({
        itemId: "ti_1",
        action: "confirm",
        baseVersion: 7,
        plateId: "detalhe",
        code: "04.02.010",
      }).plate_id,
    ).toBe("detalhe");
    expect(
      codeClosureBody({ itemId: "ti_1", baseVersion: 7, plateId: "detalhe" }).plate_id,
    ).toBe("detalhe");
    expect(
      codeRevocationBody({
        itemId: "ti_1",
        code: "04.02.010",
        baseVersion: 7,
        plateId: "detalhe",
        note: "código trocado por engano",
      }).plate_id,
    ).toBe("detalhe");
  });
});

/**
 * O vínculo de identidade (F-046 T1/T4c). A prévia é LEITURA: sem `base_version` e sem
 * nota, porque a justificativa é do ato e não da simulação.
 */
describe("o vínculo de identidade", () => {
  const kept = { plate_id: "planta-geral", item_id: "ti_b3d5e820a7c14f69" };
  const discarded = { plate_id: "detalhe", item_id: "ti_5d2f83b60e4a1c97" };

  it("a prévia leva só os dois endereços — nem versão, nem nota, nem identidade", () => {
    const corpo = identityLinkPreviewBody({ kept, discarded });

    expect(corpo).toEqual({ kept, discarded });
    expect(corpo).not.toHaveProperty("base_version");
    expect(corpo).not.toHaveProperty("note");
    expect(corpo).not.toHaveProperty("declared_by");
    expect(corpo).not.toHaveProperty("declared_at");
  });

  it("o ato leva a versão-base e a nota, e nunca carimba autor nem instante", () => {
    const corpo = identityLinkBody({
      kept,
      discarded,
      baseVersion: 7,
      note: "  mesmo trecho de alambrado do perímetro  ",
    });

    expect(corpo).toEqual({
      base_version: 7,
      kept,
      discarded,
      note: "mesmo trecho de alambrado do perímetro",
    });
    expect(corpo).not.toHaveProperty("declared_by");
    expect(corpo).not.toHaveProperty("declared_at");
  });
});
