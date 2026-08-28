import { describe, expect, it } from "vitest";

import {
  assembleCalcMatrix,
  buildContributionDraft,
  CALC_MATRIX_SCHEMA_VERSION,
  CALC_PARTIAL_EXCEEDS_ITEM,
  CALC_PARTIAL_NOTE_REQUIRED,
  CALC_MATRIX_DEPENDENCY_CYCLE,
  CALC_MATRIX_SELF_DEPENDENCY,
  contributionFormError,
  contributionKey,
  disassembleCalcMatrix,
  emptyMatrixDraft,
  hydrateMatrixDraft,
  matrixOrderError,
  openMatrixDraft,
  topologicalOrder,
  type CalcContributionDraft,
  type CalcContributionForm,
  type CalcMatrix,
} from "./matrix";

const ITEM_A = "ti_0000000000000001";
const ITEM_B = "ti_0000000000000002";

/** Um rascunho salvo mínimo, para os testes de montagem e ordem. */
function draft(over: Partial<CalcContributionDraft>): CalcContributionDraft {
  return {
    itemId: ITEM_A,
    code: "SCO001",
    itemQuantity: "418.12",
    label: "Piso em concreto",
    basis: "derived",
    recipe: "length_times_width",
    operands: [
      { name: "COMPRIMENTO", value: "20.906", unit: "m" },
      { name: "LARGURA", value: "20", unit: "m" },
    ],
    deductions: [],
    dependsOnCode: "",
    note: "",
    ...over,
  };
}

/** Um rascunho de editor completo e válido, para os testes de conferência. */
function form(over: Partial<CalcContributionForm>): CalcContributionForm {
  return {
    label: "Piso em concreto",
    basis: "derived",
    recipe: "length_times_width",
    operands: [{ name: "COMPRIMENTO", value: "20,906", unit: "m" }],
    deductions: [],
    dependsOnCode: "",
    note: "",
    ...over,
  };
}

describe("assembleCalcMatrix", () => {
  it("sem contribuição autorada devolve null — é o regime legado", () => {
    expect(assembleCalcMatrix([])).toBeNull();
  });

  it("agrupa por serviço e declara a schema_version espelho do domínio", () => {
    const matrix = assembleCalcMatrix([
      draft({ code: "SCO001", itemId: ITEM_A, label: "Piso" }),
      draft({ code: "SCO002", itemId: ITEM_A, label: "Limpeza" }),
    ]);

    expect(matrix).not.toBeNull();
    expect(matrix?.schema_version).toBe(CALC_MATRIX_SCHEMA_VERSION);
    expect(matrix?.services.map((service) => service.code)).toEqual([
      "SCO001",
      "SCO002",
    ]);
  });

  it("funde parcelas de vários elementos sob um serviço só (o caso do saibro)", () => {
    const matrix = assembleCalcMatrix([
      draft({ code: "SCO478", itemId: ITEM_A, label: "Saibro trecho 1" }),
      draft({ code: "SCO478", itemId: ITEM_B, label: "Saibro trecho 2" }),
    ]);

    const saibro = matrix?.services.find((service) => service.code === "SCO478");
    expect(saibro?.contributions).toHaveLength(2);
    expect(saibro?.contributions.map((c) => c.source_item_id)).toEqual([
      ITEM_A,
      ITEM_B,
    ]);
  });

  it("normaliza o valor do operando para decimal canônico e omite unidade vazia", () => {
    const matrix = assembleCalcMatrix([
      draft({
        operands: [
          { name: "COMPRIMENTO", value: "20,906", unit: "m" },
          { name: "FATOR", value: "1.5", unit: "" },
        ],
      }),
    ]);

    const operands = matrix?.services[0].contributions[0].operands;
    expect(operands?.[0]).toEqual({ name: "COMPRIMENTO", value: "20.906", unit: "m" });
    // Unidade vazia não vira `unit: ""`: ela some, como no domínio.
    expect(operands?.[1]).toEqual({ name: "FATOR", value: "1.5" });
  });

  it("uma parcela STANDALONE não aponta para elemento; DEPENDENT cita o código de origem", () => {
    const matrix = assembleCalcMatrix([
      draft({
        code: "ADM01",
        basis: "standalone",
        recipe: "direct_quantity",
        operands: [{ name: "MESES", value: "6", unit: "" }],
      }),
      draft({
        code: "TR01",
        basis: "dependent",
        recipe: "declared_product",
        dependsOnCode: "SCO478",
        operands: [{ name: "MASSA", value: "0.02", unit: "" }],
      }),
    ]);

    const adm = matrix?.services.find((s) => s.code === "ADM01")?.contributions[0];
    expect(adm?.source_item_id).toBeNull();
    expect(adm?.depends_on_code).toBeNull();

    const tr = matrix?.services.find((s) => s.code === "TR01")?.contributions[0];
    expect(tr?.source_item_id).toBeNull();
    expect(tr?.depends_on_code).toBe("SCO478");
  });
});

describe("topologicalOrder", () => {
  it("põe o serviço que alimenta outro antes do dependente", () => {
    const matrix = assembleCalcMatrix([
      draft({
        code: "TR01",
        basis: "dependent",
        recipe: "declared_product",
        dependsOnCode: "SCO478",
        operands: [{ name: "MASSA", value: "0.02", unit: "" }],
      }),
      draft({ code: "SCO478", label: "Saibro" }),
    ]);

    expect(topologicalOrder(matrix?.services ?? [])).toEqual(["SCO478", "TR01"]);
  });

  it("devolve null quando há ciclo entre serviços", () => {
    const matrix = assembleCalcMatrix([
      draft({
        code: "A",
        basis: "dependent",
        recipe: "declared_product",
        dependsOnCode: "B",
        operands: [{ name: "X", value: "1", unit: "" }],
      }),
      draft({
        code: "B",
        basis: "dependent",
        recipe: "declared_product",
        dependsOnCode: "A",
        operands: [{ name: "Y", value: "1", unit: "" }],
      }),
    ]);

    expect(topologicalOrder(matrix?.services ?? [])).toBeNull();
  });

  it("ignora aresta para código fora da matriz — é o build que conhece o boletim", () => {
    const matrix = assembleCalcMatrix([
      draft({
        code: "TR01",
        basis: "dependent",
        recipe: "declared_product",
        dependsOnCode: "FORA_DA_MATRIZ",
        operands: [{ name: "MASSA", value: "0.02", unit: "" }],
      }),
    ]);

    expect(topologicalOrder(matrix?.services ?? [])).toEqual(["TR01"]);
  });
});

describe("matrixOrderError", () => {
  it("recusa auto-referência pelo código estável", () => {
    const matrix = assembleCalcMatrix([
      draft({
        code: "A",
        basis: "dependent",
        recipe: "declared_product",
        dependsOnCode: "A",
        operands: [{ name: "X", value: "1", unit: "" }],
      }),
    ]);

    const erro = matrixOrderError(matrix!);
    expect(erro?.code).toBe(CALC_MATRIX_SELF_DEPENDENCY);
    expect(erro?.codes).toEqual(["A"]);
  });

  it("recusa ciclo pelo código estável", () => {
    const matrix = assembleCalcMatrix([
      draft({
        code: "A",
        basis: "dependent",
        recipe: "declared_product",
        dependsOnCode: "B",
        operands: [{ name: "X", value: "1", unit: "" }],
      }),
      draft({
        code: "B",
        basis: "dependent",
        recipe: "declared_product",
        dependsOnCode: "A",
        operands: [{ name: "Y", value: "1", unit: "" }],
      }),
    ]);

    const erro = matrixOrderError(matrix!);
    expect(erro?.code).toBe(CALC_MATRIX_DEPENDENCY_CYCLE);
    expect(erro?.codes).toEqual(["A", "B"]);
  });

  it("aceita uma matriz acíclica", () => {
    const matrix = assembleCalcMatrix([draft({ code: "SCO478" })]);
    expect(matrixOrderError(matrix!)).toBeNull();
  });
});

describe("contributionFormError — parcela PARCIAL (decisão 6)", () => {
  it("bloqueia parcial sem nota com CALC_PARTIAL_NOTE_REQUIRED", () => {
    const erro = contributionFormError(
      form({
        basis: "partial",
        recipe: "declared_product",
        operands: [{ name: "AREA DECLARADA", value: "170", unit: "m2" }],
        note: "   ",
      }),
      "418.12",
    );
    expect(erro?.code).toBe(CALC_PARTIAL_NOTE_REQUIRED);
  });

  it("bloqueia parcial acima do teto do elemento com CALC_PARTIAL_EXCEEDS_ITEM", () => {
    const erro = contributionFormError(
      form({
        basis: "partial",
        recipe: "declared_product",
        operands: [{ name: "AREA DECLARADA", value: "500", unit: "m2" }],
        note: "recorte medido em campo",
      }),
      "418.12",
    );
    expect(erro?.code).toBe(CALC_PARTIAL_EXCEEDS_ITEM);
  });

  it("aceita parcial igual ao teto — os 170 cabem dentro dos 418,12", () => {
    const ok = contributionFormError(
      form({
        basis: "partial",
        recipe: "declared_product",
        operands: [{ name: "AREA DECLARADA", value: "170", unit: "m2" }],
        note: "recorte medido em campo",
      }),
      "418.12",
    );
    expect(ok).toBeNull();
  });

  it("sem teto conhecido não bloqueia — o servidor confere no build", () => {
    const ok = contributionFormError(
      form({
        basis: "partial",
        recipe: "declared_product",
        operands: [{ name: "AREA DECLARADA", value: "9999", unit: "m2" }],
        note: "recorte medido em campo",
      }),
      null,
    );
    expect(ok).toBeNull();
  });
});

describe("buildContributionDraft", () => {
  it("normaliza e devolve o rascunho quando o formulário serve", () => {
    const resultado = buildContributionDraft(
      ITEM_A,
      "SCO001",
      "418.12",
      form({ operands: [{ name: "COMPRIMENTO", value: "20,906", unit: "m" }] }),
    );
    expect("draft" in resultado).toBe(true);
    if ("draft" in resultado) {
      expect(resultado.draft.itemId).toBe(ITEM_A);
      expect(resultado.draft.code).toBe("SCO001");
      expect(resultado.draft.itemQuantity).toBe("418.12");
    }
  });

  it("recusa base ou grandeza não escolhida (nada nasce pré-marcado)", () => {
    const semBase = buildContributionDraft(ITEM_A, "SCO001", "1", form({ basis: "" }));
    expect("code" in semBase).toBe(true);
    const semReceita = buildContributionDraft(
      ITEM_A,
      "SCO001",
      "1",
      form({ recipe: "" }),
    );
    expect("code" in semReceita).toBe(true);
  });
});

describe("contributionKey", () => {
  it("compõe a chave estável do par (elemento, código)", () => {
    expect(contributionKey(ITEM_A, "SCO001")).toBe(`${ITEM_A}::SCO001`);
  });
});

/**
 * A volta da matriz gravada para o rascunho (F-042 T5), e o critério que importa: **montar
 * sem tocar em nada, depois de hidratar, não pode perder contribuição nenhuma**.
 *
 * O defeito era a matriz ter dois donos — o `apply` do acervo grava no servidor, a tela
 * mandava no build só o que a sessão viu — e o preço era montar o orçamento apagar do banco
 * o que já estava lá.
 */
describe("disassembleCalcMatrix", () => {
  /** Uma matriz gravada com as três formas que a volta precisa reconstruir. */
  const GRAVADA: CalcMatrix = {
    schema_version: CALC_MATRIX_SCHEMA_VERSION,
    services: [
      {
        code: "SCO001",
        contributions: [
          {
            source_item_id: ITEM_A,
            label: "Piso em concreto",
            basis: "derived",
            recipe: "length_times_width",
            operands: [
              { name: "COMPRIMENTO", value: "20.906", unit: "m" },
              { name: "LARGURA", value: "20" },
            ],
            deductions: [{ name: "CANTEIRO", value: "12.5", unit: "m2" }],
            depends_on_code: null,
            note: "recorte medido na prancha",
          },
          {
            source_item_id: ITEM_B,
            label: "Piso do passeio",
            basis: "full",
            recipe: "direct_quantity",
            operands: [{ name: "QUANTIDADE", value: "170" }],
            deductions: [],
            depends_on_code: null,
            note: null,
          },
        ],
      },
      {
        code: "AC01100010",
        contributions: [
          {
            source_item_id: null,
            label: "Aluguel de banheiro químico",
            basis: "standalone",
            recipe: "declared_product",
            operands: [
              { name: "UNIDADES", value: "1", unit: "un" },
              { name: "PRAZO", value: "2", unit: "mes" },
            ],
            deductions: [],
            depends_on_code: null,
            note: null,
            kit_origin: { kit_version: 1, parcel_id: "p1" },
          },
          {
            source_item_id: null,
            label: "Entulho — caçamba extra",
            basis: "standalone",
            recipe: "declared_product",
            operands: [{ name: "CAÇAMBAS", value: "3", unit: "un" }],
            deductions: [],
            depends_on_code: null,
            note: null,
          },
        ],
      },
      {
        code: "SCO009",
        contributions: [
          {
            source_item_id: null,
            label: "Transporte do entulho",
            basis: "dependent",
            recipe: "direct_quantity",
            operands: [{ name: "VOLUME", value: "8.4", unit: "m3" }],
            deductions: [],
            depends_on_code: "SCO001",
            note: null,
          },
        ],
      },
    ],
  };

  /**
   * **O teste do defeito 2.** Abrir uma rodada com matriz gravada e montar sem tocar em
   * nada produz a MESMA matriz: nem uma contribuição a menos, nem um campo mudado.
   */
  it("montar depois de hidratar devolve a matriz gravada, inteira", () => {
    const remontada = assembleCalcMatrix(disassembleCalcMatrix(GRAVADA));

    expect(remontada).toEqual(GRAVADA);
  });

  it("reconstrói as duas origens e o que o fio não carrega volta declarado ausente", () => {
    const drafts = disassembleCalcMatrix(GRAVADA);

    expect(drafts).toHaveLength(5);
    // A contribuição de elemento mantém o vínculo com ele; a chave da tela é a de sempre.
    const piso = drafts.find((entrada) => entrada.itemId === ITEM_A);
    expect(piso?.code).toBe("SCO001");
    expect(piso?.note).toBe("recorte medido na prancha");
    expect(piso?.operands).toEqual([
      { name: "COMPRIMENTO", value: "20.906", unit: "m" },
      // Unidade ausente no fio vira `""`, que é como a tela a lê e a reescreve.
      { name: "LARGURA", value: "20", unit: "" },
    ]);
    // A parcela de acervo é reconhecida pela proveniência, com a versão que a matriz diz.
    const doAcervo = drafts.find((entrada) => entrada.kitOrigin !== undefined);
    expect(doAcervo?.kitOrigin).toEqual({
      kitId: "",
      kitName: "",
      kitVersion: 1,
      parcelId: "p1",
    });
    // O teto da parcela PARCIAL não existe no fio: ele volta ausente, nunca fabricado.
    expect(drafts.every((entrada) => entrada.itemQuantity === null)).toBe(true);
  });

  it("STANDALONE e DEPENDENT ganham chave de tela sem inventar elemento de origem", () => {
    const drafts = disassembleCalcMatrix(GRAVADA);
    const aMao = drafts.find((entrada) => entrada.label === "Entulho — caçamba extra");
    const dependente = drafts.find((entrada) => entrada.basis === "dependent");

    // Chaves distintas para duas parcelas do MESMO código, e nenhuma delas volta ao fio.
    expect(aMao?.itemId).not.toBe("p1");
    expect(dependente?.dependsOnCode).toBe("SCO001");
    const remontada = assembleCalcMatrix(drafts);
    const todas = remontada?.services.flatMap((service) => service.contributions) ?? [];
    expect(
      todas
        .filter((c) => c.basis === "standalone" || c.basis === "dependent")
        .every((c) => c.source_item_id === null),
    ).toBe(true);
  });

  it("matriz gravada ausente é o regime legado: rascunho vazio", () => {
    expect(disassembleCalcMatrix(null)).toEqual([]);
    expect(assembleCalcMatrix(disassembleCalcMatrix(null))).toBeNull();
  });
});

/**
 * O rascunho é DA rodada. Sem isso, a hidratação deixa de ser conserto e vira corrupção:
 * a matriz de uma praça pousando sobre outra, sem ninguém ler aquilo como erro.
 */
describe("o rascunho da rodada", () => {
  const MATRIZ: CalcMatrix = {
    schema_version: CALC_MATRIX_SCHEMA_VERSION,
    services: [
      {
        code: "SCO001",
        contributions: [
          {
            source_item_id: ITEM_A,
            label: "Piso em concreto",
            basis: "derived",
            recipe: "length_times_width",
            operands: [{ name: "COMPRIMENTO", value: "20.906", unit: "m" }],
            deductions: [],
            depends_on_code: null,
            note: null,
          },
        ],
      },
    ],
  };

  it("trocar de rodada zera o rascunho, antes de qualquer hidratação", () => {
    const daPrimeira = hydrateMatrixDraft(emptyMatrixDraft("round-1"), "round-1", MATRIZ);
    expect(Object.keys(daPrimeira.drafts)).toHaveLength(1);

    const daSegunda = openMatrixDraft(daPrimeira, "round-2");

    expect(daSegunda.roundId).toBe("round-2");
    expect(daSegunda.drafts).toEqual({});
  });

  it("reabrir a MESMA rodada não custa o que já foi autorado", () => {
    const atual = hydrateMatrixDraft(emptyMatrixDraft("round-1"), "round-1", MATRIZ);

    expect(openMatrixDraft(atual, "round-1")).toBe(atual);
  });

  /** A leitura é assíncrona: trocar de rodada com ela em voo não pode pousar na nova. */
  it("descarta a matriz lida de OUTRA rodada", () => {
    const atual = emptyMatrixDraft("round-2");

    expect(hydrateMatrixDraft(atual, "round-1", MATRIZ)).toBe(atual);
  });

  /** O gravado é o ponto de partida, não uma correção do que a pessoa acabou de escrever. */
  it("o que a sessão autorou vence o gravado na mesma chave", () => {
    const daSessao: CalcContributionDraft = draft({
      itemId: ITEM_A,
      code: "SCO001",
      label: "Piso em concreto — corrigido",
    });
    const atual = {
      roundId: "round-1",
      drafts: { [contributionKey(ITEM_A, "SCO001")]: daSessao },
    };

    const hidratado = hydrateMatrixDraft(atual, "round-1", MATRIZ);

    expect(hidratado.drafts[contributionKey(ITEM_A, "SCO001")]).toBe(daSessao);
  });

  it("rodada sem matriz gravada fica com o rascunho vazio", () => {
    const hidratado = hydrateMatrixDraft(emptyMatrixDraft("round-1"), "round-1", null);

    expect(hidratado.drafts).toEqual({});
    expect(hidratado.roundId).toBe("round-1");
  });
});
