import { describe, expect, it } from "vitest";

import type { AmendmentDraft, RoundPreviewResponse, RoundSummary } from "./api";
import {
  aberturaDaMedicaoSeguinte,
  efeitoEmPtBr,
  linhasDeclaradas,
  pedidoDaPrevia,
} from "./previa";

/**
 * A abertura da medição seguinte e a prévia (F-040, decisões 1, 2 e 6 do pacote aprovado).
 *
 * O que se mede aqui mudou com a T7, e mudou de propósito: **não há mais aritmética a testar**.
 * A conta saiu para `POST /v1/valuation-round-previews`, e quem a fixa contra o consolidado
 * realmente gravado é `tests/api/test_valuation_round_preview.py`. O que sobrou neste módulo é
 * o que ele passou a ser — o que perguntar, o que é declaração e o que é ausência dela —, e é
 * isso que estes testes cobrem.
 */

const CODE = "CE04100010(/)";
const CODE_NEW = "CE04100020(/)";

const RODADA_ANTERIOR = {
  round_id: "0197f2a0-0000-7000-8000-0000000000d1",
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

/** Uma resposta do servidor, com o código citado pela RE-RA e outro que ela não cita. */
const PREVIA: RoundPreviewResponse = {
  worksite_key: "praca-orcada-sintetica",
  worksite_name: "PRACA ORCADA SINTETICA",
  period_number: 2,
  previous_period_number: 1,
  measured_total_amount: "250.00",
  lines: [
    {
      code: CODE,
      item_number: "1.1",
      description: "ALAMBRADO GALVANIZADO",
      unit: "m",
      contracted_unit_price: "50.00",
      current_unit_price: "50.00",
      new_unit_price: "50.00",
      contracted_quantity: "12.00",
      current_quantity: "12.00",
      current_balance_quantity: "7.00",
      accumulated_quantity: "5.00",
      measured_quantity: "5.00",
      re_ratified: false,
      amendment_delta: "+3.00",
      new_current_quantity: "15.00",
      new_balance_quantity: "10.00",
      is_new_item: false,
    },
    {
      code: "CE04100099(/)",
      item_number: "1.2",
      description: "MEIO-FIO SINTETICO",
      unit: "m",
      contracted_unit_price: "20.00",
      current_unit_price: "20.00",
      new_unit_price: "20.00",
      contracted_quantity: "8.00",
      current_quantity: "8.00",
      current_balance_quantity: "8.00",
      accumulated_quantity: "0.00",
      measured_quantity: "0.00",
      re_ratified: false,
      amendment_delta: null,
      new_current_quantity: "8.00",
      new_balance_quantity: "8.00",
      is_new_item: false,
    },
    {
      code: CODE_NEW,
      item_number: "2",
      description: "PORTAO SINTETICO GALVANIZADO",
      unit: "un",
      contracted_unit_price: "30.00",
      current_unit_price: "30.00",
      new_unit_price: "30.00",
      contracted_quantity: "0.00",
      current_quantity: "0.00",
      current_balance_quantity: "0.00",
      accumulated_quantity: "0.00",
      measured_quantity: "0.00",
      re_ratified: false,
      amendment_delta: "+2.00",
      new_current_quantity: "2.00",
      new_balance_quantity: "2.00",
      is_new_item: true,
    },
  ],
};

const RE_RA: AmendmentDraft = {
  label: "2ª RE-RA",
  referencePeriod: "Processo 123/2026",
  lines: [
    { code: CODE, quantityDelta: "3" },
    { code: CODE_NEW, quantityDelta: "2", isNewItem: true },
  ],
};

describe("aberturaDaMedicaoSeguinte", () => {
  it("resolve origem, período e rótulo sem criar rodada nenhuma", () => {
    expect(aberturaDaMedicaoSeguinte(RODADA_ANTERIOR)).toEqual({
      previousRoundId: "0197f2a0-0000-7000-8000-0000000000d1",
      periodNumber: "2",
      referenceLabel: "Medição 2 — PRACA ORCADA SINTETICA",
    });
  });
});

describe("efeitoEmPtBr", () => {
  it("mantém o sinal do servidor à esquerda e só troca a pontuação", () => {
    expect(efeitoEmPtBr("+120.00")).toBe("+120,00");
    expect(efeitoEmPtBr("-83.86")).toBe("-83,86");
  });

  it("delta sem sinal explícito é acréscimo, não subtração", () => {
    expect(efeitoEmPtBr("6.00")).toBe("+6,00");
  });
});

describe("pedidoDaPrevia", () => {
  it("monta o pedido da medição seguinte com a declaração junto", () => {
    expect(
      pedidoDaPrevia({
        previousRoundId: RODADA_ANTERIOR.round_id,
        periodNumber: "2",
        amendment: RE_RA,
      }),
    ).toEqual({
      previousRoundId: RODADA_ANTERIOR.round_id,
      periodNumber: "2",
      priceAdjustment: undefined,
      amendment: RE_RA,
    });
  });

  it("monta o pedido do orçamento assinado, que também tem contratado a projetar", () => {
    const pedido = pedidoDaPrevia({
      estimateRoundId: "0197f2a0-0000-7000-8000-0000000000e1",
      periodNumber: "1",
    });

    expect(pedido?.estimateRoundId).toBe("0197f2a0-0000-7000-8000-0000000000e1");
    expect(pedido?.previousRoundId).toBeUndefined();
  });

  it("sem origem contratada não há o que projetar", () => {
    // A porta do catálogo por upload abre rodada SEM contratado: não existe contratado,
    // vigente nem saldo a mostrar, e pedir a prévia prometeria uma conta que não há.
    expect(pedidoDaPrevia({ periodNumber: "1" })).toBeNull();
  });

  it("período em branco ou ilegível não vira pedido", () => {
    expect(
      pedidoDaPrevia({ previousRoundId: RODADA_ANTERIOR.round_id, periodNumber: "  " }),
    ).toBeNull();
    expect(
      pedidoDaPrevia({ previousRoundId: RODADA_ANTERIOR.round_id, periodNumber: "segunda" }),
    ).toBeNull();
  });
});

describe("linhasDeclaradas", () => {
  it("mostra só os códigos que a declaração cita", () => {
    // `amendment_delta` nulo é "a RE-RA não fala deste código", que não é delta zero
    // declarado: a linha existe no consolidado e não pertence à tabela do efeito.
    expect(linhasDeclaradas(PREVIA).map((linha) => linha.code)).toEqual([CODE, CODE_NEW]);
  });

  it("sem resposta do servidor, nenhuma linha — nunca uma tabela inventada", () => {
    expect(linhasDeclaradas(null)).toEqual([]);
  });
});
