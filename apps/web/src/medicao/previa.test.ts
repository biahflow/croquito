import { describe, expect, it } from "vitest";

import type {
  AmendmentDraft,
  BulletinResponse,
  CatalogSearchResult,
  RoundContractedPrice,
  RoundContractedQuantity,
  RoundSummary,
} from "./api";
import {
  aberturaDaMedicaoSeguinte,
  codigosParaResolver,
  efeitoEmPtBr,
  herancaDaRodadaAnterior,
  medidoPorCodigo,
  previaDaReRa,
  somarExato,
  subtrairExato,
} from "./previa";

/**
 * A herança da rodada anterior e a prévia da RE-RA (F-040 T6, decisões 4 e 6 do pacote).
 *
 * O caso central deste arquivo **não é uma tautologia**: os números esperados são os que a API
 * devolve depois de gravar, fixados do outro lado por
 * `tests/api/test_valuation_round_from_estimate.py::test_a_medicao_seguinte_nasce_re_ratificada`.
 * Se o domínio mudar a conta, aquele teste reprova; se a prévia divergir dele, este reprova. É
 * esse par que impede a tela de mostrar, antes de gravar, um número que o servidor não faria.
 */

const CODE = "CE04100010(/)";
const CODE_NEW = "CE04100020(/)";

/** O read-model da rodada anterior: 12,00 contratados, nenhum período ainda somado nela. */
const QUANTIDADES: RoundContractedQuantity[] = [
  {
    code: CODE,
    item_number: "1.1",
    description: "ALAMBRADO GALVANIZADO",
    unit: "m",
    contracted_quantity: "12.00",
    current_quantity: "12.00",
    current_balance_quantity: "12.00",
    re_ratified: false,
  },
];

const PRECOS: RoundContractedPrice[] = [
  {
    code: CODE,
    item_number: "1.1",
    description: "ALAMBRADO GALVANIZADO",
    unit: "m",
    contracted_unit_price: "50.00",
    current_unit_price: "50.00",
    adjusted: false,
  },
];

/** O boletim aprovado do período 1: 5,00 medidos, a 50,00 cada. */
const BOLETIM = {
  round_id: "rodada-anterior",
  version: 3,
  valuation: {
    period_number: 1,
    reference_label: "Medição 1",
    calc_sheets: [],
    bulletins: [
      {
        worksite_key: "praca-orcada-sintetica",
        worksite_name: "PRACA ORCADA SINTETICA",
        total_amount: "250.00",
        lines: [
          {
            code: CODE,
            description: "ALAMBRADO GALVANIZADO",
            item_number: "1.1",
            quantity: "5.00",
            total: "250.00",
            unit: "m",
            unit_price: "50.00",
          },
        ],
      },
    ],
  },
  valuation_sha256: "d".repeat(64),
  total_amount: "250.00",
  approval: {
    approved: true,
    stale: false,
    approved_by: "orcamentista",
    approved_at: "2026-08-01T12:00:00+00:00",
    approved_digest: "d".repeat(64),
  },
  workbook_present: false,
  workbook_sha256: null,
} as unknown as BulletinResponse;

const ITEM_NOVO_DO_CATALOGO: CatalogSearchResult = {
  code: CODE_NEW,
  unit: "un",
  unit_price: "30.00",
  description: "PORTAO SINTETICO GALVANIZADO",
  origin: "SCO",
  lexical_score: 1,
  semantic_score: null,
};

const DECLARACAO: AmendmentDraft = {
  label: "2ª RE-RA",
  referencePeriod: "Processo 123/2026",
  lines: [
    { code: CODE, quantityDelta: "3" },
    { code: CODE_NEW, quantityDelta: "2", isNewItem: true },
  ],
};

describe("aritmética exata em texto", () => {
  it("soma com a escala do Python: 12,00 + 3 é 15,00, e não 15", () => {
    expect(somarExato("12.00", "3")).toBe("15.00");
    expect(somarExato("0.00", "2")).toBe("2.00");
    expect(somarExato("783.86", "120")).toBe("903.86");
    expect(somarExato("783.86", "-83.86")).toBe("700.00");
  });

  it("subtrai preservando a maior escala e o sinal", () => {
    expect(subtrairExato("15.00", "5.00")).toBe("10.00");
    expect(subtrairExato("12.00", "12.00")).toBe("0.00");
    expect(subtrairExato("5", "12.500")).toBe("-7.500");
  });

  it("aceita vírgula como o campo da tela a produz, e recusa o que não é decimal", () => {
    expect(somarExato("12.00", "1,50")).toBe("13.50");
    expect(somarExato("12.00", "três")).toBeNull();
    expect(subtrairExato("", "1")).toBeNull();
  });

  it("não perde precisão onde `Number` perderia", () => {
    // 0.1 + 0.2 em ponto flutuante dá 0.30000000000000004; aqui é texto e BigInt.
    expect(somarExato("0.1", "0.2")).toBe("0.3");
    expect(somarExato("9007199254740993.00", "1.00")).toBe("9007199254740994.00");
  });

  it("mostra o efeito com sinal, em pt-BR, sem fazer conta nenhuma", () => {
    expect(efeitoEmPtBr("+120")).toBe("+120");
    expect(efeitoEmPtBr("-83.86")).toBe("-83,86");
    expect(efeitoEmPtBr("+1200.50")).toBe("+1.200,50");
  });
});

describe("a porta da medição seguinte", () => {
  const rodada = {
    round_id: "01a0-rodada-1",
    worksite_key: "praca-orcada-sintetica",
    worksite_name: "PRACA ORCADA SINTETICA",
    reference_label: "Medição 1 — agosto/2026",
    period_number: 1,
    version: 3,
    status: "OPEN",
    stage: "bulletin",
    extraction_status: "idle",
    created_at: "2026-08-01T00:00:00+00:00",
    updated_at: "2026-08-01T00:00:00+00:00",
    approved: true,
    can_open_next: true,
  } as unknown as RoundSummary;

  it("calcula o período em vez de pedi-lo, e cita a rodada anterior", () => {
    expect(aberturaDaMedicaoSeguinte(rodada)).toEqual({
      previousRoundId: "01a0-rodada-1",
      periodNumber: "2",
      referenceLabel: "Medição 2 — PRACA ORCADA SINTETICA",
    });
  });
});

describe("a herança da rodada anterior", () => {
  it("soma o período que fechou ao acumulado e apura o saldo da rodada nova", () => {
    const heranca = herancaDaRodadaAnterior(
      QUANTIDADES,
      PRECOS,
      medidoPorCodigo(BOLETIM),
    );

    expect(heranca).toHaveLength(1);
    const linha = heranca[0];
    expect(linha.contratado).toBe("12.00");
    // Sem RE-RA, contratado e vigente repetem o mesmo número DE PROPÓSITO (decisão 4).
    expect(linha.vigente).toBe("12.00");
    expect(linha.medidoNoPeriodo).toBe("5.00");
    expect(linha.acumulado).toBe("5.00");
    expect(linha.saldo).toBe("7.00");
    expect(linha.unitPrice).toBe("50.00");
    expect(linha.reRatificada).toBe(false);
  });

  it("código sem medição no período entra com zero, e não some da herança", () => {
    const heranca = herancaDaRodadaAnterior(QUANTIDADES, PRECOS, {});

    expect(heranca[0].medidoNoPeriodo).toBe("0.00");
    expect(heranca[0].acumulado).toBe("0.00");
    expect(heranca[0].saldo).toBe("12.00");
  });

  it("soma o mesmo código medido em duas obras da mesma rodada", () => {
    const duasObras = {
      ...BOLETIM,
      valuation: {
        ...BOLETIM.valuation,
        bulletins: [
          BOLETIM.valuation.bulletins[0],
          {
            ...BOLETIM.valuation.bulletins[0],
            worksite_key: "outra-praca",
            lines: [{ ...BOLETIM.valuation.bulletins[0].lines[0], quantity: "1.50" }],
          },
        ],
      },
    } as unknown as BulletinResponse;

    expect(medidoPorCodigo(duasObras)).toEqual({ [CODE]: "6.50" });
  });

  it("sem boletim lido, não inventa medição nenhuma", () => {
    expect(medidoPorCodigo(null)).toEqual({});
  });

  it("número ilegível do servidor vira ausência declarada, nunca um número inventado", () => {
    const heranca = herancaDaRodadaAnterior(
      [{ ...QUANTIDADES[0], current_balance_quantity: "—" }],
      PRECOS,
      medidoPorCodigo(BOLETIM),
    );

    expect(heranca[0].acumulado).toBeNull();
    expect(heranca[0].saldo).toBeNull();
  });
});

describe("a prévia da RE-RA, antes de gravar", () => {
  const heranca = herancaDaRodadaAnterior(QUANTIDADES, PRECOS, medidoPorCodigo(BOLETIM));

  /**
   * O caso que fecha o AC 4: os seis números abaixo são exatamente os que
   * `test_a_medicao_seguinte_nasce_re_ratificada` afirma sobre a resposta da API depois do
   * POST. A prévia os mostra ANTES.
   */
  it("bate com o que a API devolve depois de gravar", () => {
    const linhas = previaDaReRa(heranca, DECLARACAO, {
      [CODE_NEW]: ITEM_NOVO_DO_CATALOGO,
    });

    expect(linhas).toHaveLength(2);

    const herdada = linhas[0];
    expect(herdada.contratado).toBe("12.00");
    expect(herdada.vigenteHoje).toBe("12.00");
    expect(herdada.efeito).toBe("+3");
    expect(herdada.vigenteNovo).toBe("15.00");
    expect(herdada.acumulado).toBe("5.00");
    expect(herdada.saldoNovo).toBe("10.00");
    expect(herdada.itemNovo).toBe(false);

    const nova = linhas[1];
    expect(nova.contratado).toBe("0.00");
    expect(nova.vigenteNovo).toBe("2.00");
    expect(nova.saldoNovo).toBe("2.00");
    expect(nova.itemNovo).toBe(true);
  });

  it("resolve descrição, unidade e preço do item novo no catálogo contratual", () => {
    const linhas = previaDaReRa(heranca, DECLARACAO, {
      [CODE_NEW]: ITEM_NOVO_DO_CATALOGO,
    });

    expect(linhas[1].description).toBe("PORTAO SINTETICO GALVANIZADO");
    expect(linhas[1].unit).toBe("un");
    expect(linhas[1].unitPrice).toBe("30.00");
    expect(linhas[1].pendente).toBe(false);
  });

  it("item novo ainda não resolvido é declarado pendente, sem campo em branco fingindo dado", () => {
    const linhas = previaDaReRa(heranca, DECLARACAO, {});

    expect(linhas[1].pendente).toBe(true);
    expect(linhas[1].description).toBe("");
    expect(linhas[1].unitPrice).toBeNull();
  });

  it("efeito negativo reduz o vigente e o saldo na mesma medida", () => {
    const linhas = previaDaReRa(heranca, {
      ...DECLARACAO,
      lines: [{ code: CODE, quantityDelta: "-2.00" }],
    }, {});

    expect(linhas[0].efeito).toBe("-2.00");
    expect(linhas[0].vigenteNovo).toBe("10.00");
    expect(linhas[0].saldoNovo).toBe("5.00");
  });

  it("consolidado que JÁ chega re-ratificado soma sobre o vigente, não sobre o contratado", () => {
    const jaReRatificado = herancaDaRodadaAnterior(
      [
        {
          ...QUANTIDADES[0],
          current_quantity: "20.00",
          current_balance_quantity: "20.00",
          re_ratified: true,
        },
      ],
      PRECOS,
      medidoPorCodigo(BOLETIM),
    );

    const linhas = previaDaReRa(jaReRatificado, {
      ...DECLARACAO,
      lines: [{ code: CODE, quantityDelta: "3" }],
    }, {});

    expect(linhas[0].contratado).toBe("12.00");
    expect(linhas[0].vigenteHoje).toBe("20.00");
    expect(linhas[0].vigenteNovo).toBe("23.00");
  });

  it("sem declaração, não há prévia — e linha pela metade não vira linha", () => {
    expect(previaDaReRa(heranca, null, {})).toEqual([]);
    expect(
      previaDaReRa(heranca, { ...DECLARACAO, lines: [{ code: CODE, quantityDelta: "" }] }, {}),
    ).toEqual([]);
    expect(
      previaDaReRa(heranca, { ...DECLARACAO, lines: [{ code: "", quantityDelta: "3" }] }, {}),
    ).toEqual([]);
  });
});

describe("os códigos a resolver no catálogo", () => {
  const heranca = herancaDaRodadaAnterior(QUANTIDADES, PRECOS, medidoPorCodigo(BOLETIM));

  it("são só os que não existem no consolidado herdado, sem repetição", () => {
    expect(codigosParaResolver(DECLARACAO, heranca)).toEqual([CODE_NEW]);
    expect(
      codigosParaResolver(
        {
          ...DECLARACAO,
          lines: [
            { code: CODE_NEW, quantityDelta: "1" },
            { code: CODE_NEW, quantityDelta: "2" },
          ],
        },
        heranca,
      ),
    ).toEqual([CODE_NEW]);
  });

  it("sem declaração, não pergunta nada ao catálogo", () => {
    expect(codigosParaResolver(null, heranca)).toEqual([]);
  });
});
