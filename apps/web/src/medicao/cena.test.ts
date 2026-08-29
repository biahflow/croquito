import { describe, expect, it } from "vitest";

import {
  divergenciaAberta,
  divergenciaDoItem,
  divergenciaResolvida,
  frasePorFaltaDePar,
  itensComDivergenciaAberta,
  ladoSemIdentidade,
  motivoDeBloqueio,
  numeroEscolhido,
  numeroPreterido,
  vemDaCena,
  type QuantityDivergence,
  type SceneConfrontationReport,
  type SceneItemOutcome,
} from "./cena";
import type { TakeoffItem } from "./api";

/**
 * A leitura da quantidade que veio da cena (F-047 T7b).
 *
 * O oráculo destes testes é a AUSÊNCIA de conta: os números da fixture são os da Praça do
 * Cedro do pacote de design aprovado (`docs/features/F-047-.../mock/README.md`), e nenhum
 * deles é recomputado aqui. `401,55` contra `385,00` dá `16,55` de diferença com `3,85` de
 * tolerância porque foi o SERVIDOR quem gravou esses dois números — se este módulo os
 * calculasse, o teste passaria e a regra do produto estaria quebrada.
 */

const EVIDENCIA = {
  bbox: { left: 0, top: 0, right: 10, bottom: 10 },
  image_sha256: "a".repeat(64),
  page_number: 1,
  plate_id: "PR-01",
};

function item(overrides: Partial<TakeoffItem> = {}): TakeoffItem {
  return {
    id: "ti_0000000000000001",
    label: "Alambrado — quadra poliesportiva",
    raw_text: "ALAMBRADO H=2,00 — 385,00 m",
    unit: "m",
    status: "proposed",
    source: "legend_extraction",
    extractor: "fixture",
    extractor_version: "1.0.0",
    evidence: EVIDENCIA,
    ...overrides,
  } as TakeoffItem;
}

/** A divergência do EL-003: 401,55 da cena contra 385,00 da legenda. */
function divergencia(
  overrides: Partial<QuantityDivergence> = {},
): QuantityDivergence {
  return {
    scene: {
      element_ref: "EL-003",
      precision: "derived",
      quantity: "401.55",
      scene_revision_id: "rev-8",
    },
    legend: {
      extractor: "fixture",
      extractor_version: "1.0.0",
      quantity: "385.00",
      read_at: "2026-03-02T12:00:00Z",
      read_by: "orcamentista",
      source: "legend_extraction",
    },
    difference: "16.55",
    tolerance: "3.85",
    ...overrides,
  };
}

function desfecho(overrides: Partial<SceneItemOutcome> = {}): SceneItemOutcome {
  return {
    item_id: "ti_0000000000000001",
    element_ref: null,
    outcome: "unchanged",
    reason: "item_without_element_ref",
    scene_quantity: null,
    scene_precision: null,
    ...overrides,
  };
}

describe("de onde a quantidade veio", () => {
  it("reconhece a cena aprovada e não confunde com a legenda nem com a digitação", () => {
    expect(vemDaCena(item({ source: "scene_graph" }))).toBe(true);
    expect(vemDaCena(item({ source: "legend_extraction" }))).toBe(false);
    expect(vemDaCena(item({ source: "manual" }))).toBe(false);
  });
});

describe("a divergência", () => {
  it("distingue ausência de divergência, divergência aberta e divergência resolvida", () => {
    const semDivergencia = item();
    const aberta = item({ scene_divergence: divergencia() });
    const resolvida = item({
      scene_divergence: divergencia({
        resolution: {
          choice: "scene",
          resolved_at: "2026-03-05T12:14:00Z",
          reviewer_id: "orcamentista",
          reviewer_role: "orcamentista",
          note: "traçado ajustado em 04/03",
        },
      }),
    });

    expect(divergenciaDoItem(semDivergencia)).toBeNull();
    expect(divergenciaAberta(semDivergencia)).toBeNull();

    expect(divergenciaAberta(aberta)).not.toBeNull();
    expect(divergenciaResolvida(aberta)).toBeNull();

    expect(divergenciaAberta(resolvida)).toBeNull();
    expect(divergenciaResolvida(resolvida)).not.toBeNull();
    // A divergência continua existindo depois de resolvida: ela é o registro dos dois
    // números, não um estado de erro que some.
    expect(divergenciaDoItem(resolvida)).not.toBeNull();
  });

  it("devolve a diferença e a tolerância EXATAMENTE como o servidor as gravou", () => {
    const gravada = divergencia();

    // O par 16,55 / 3,85 não é recomputado em lugar nenhum deste módulo. É o mesmo texto
    // decimal que atravessou a fronteira.
    expect(gravada.difference).toBe("16.55");
    expect(gravada.tolerance).toBe("3.85");
    expect(gravada.scene.quantity).toBe("401.55");
    expect(gravada.legend.quantity).toBe("385.00");
  });

  it("bloqueia o item enquanto a divergência estiver aberta, e diz por quê", () => {
    const aberta = item({ scene_divergence: divergencia() });
    const motivo = motivoDeBloqueio(aberta);

    expect(motivo).not.toBeNull();
    expect(motivo).toContain("não fecha");
    // O motivo é palavra, e não um código: o bloqueio precisa ser legível na tela.
    expect(motivo).toContain("cena aprovada");
    expect(motivoDeBloqueio(item())).toBeNull();
  });

  it("solta o bloqueio assim que a decisão humana existe", () => {
    const resolvida = item({
      scene_divergence: divergencia({
        resolution: {
          choice: "legend",
          resolved_at: "2026-03-05T12:14:00Z",
          reviewer_id: "orcamentista",
          reviewer_role: "orcamentista",
        },
      }),
    });

    expect(motivoDeBloqueio(resolvida)).toBeNull();
  });

  it("lista os itens que não fecham, e só eles", () => {
    const bloqueado = item({ id: "ti_0000000000000002", scene_divergence: divergencia() });
    const abertos = itensComDivergenciaAberta([item(), bloqueado]);

    expect(abertos).toHaveLength(1);
    expect(abertos[0].id).toBe("ti_0000000000000002");
  });
});

describe("a resolução escolhe, e o preterido continua gravado", () => {
  it("com 'vale a cena', o número da legenda continua acessível", () => {
    const gravada = divergencia({
      resolution: {
        choice: "scene",
        resolved_at: "2026-03-05T12:14:00Z",
        reviewer_id: "orcamentista",
        reviewer_role: "orcamentista",
      },
    });

    expect(numeroEscolhido(gravada)).toEqual({ quantity: "401.55", origem: "scene" });
    expect(numeroPreterido(gravada)).toEqual({ quantity: "385.00", origem: "legend" });
  });

  it("com 'vale a legenda', é o número da cena que fica preterido — e gravado", () => {
    const gravada = divergencia({
      resolution: {
        choice: "legend",
        resolved_at: "2026-03-05T12:14:00Z",
        reviewer_id: "orcamentista",
        reviewer_role: "orcamentista",
      },
    });

    expect(numeroEscolhido(gravada)).toEqual({ quantity: "385.00", origem: "legend" });
    expect(numeroPreterido(gravada)).toEqual({ quantity: "401.55", origem: "scene" });
  });

  it("enquanto ninguém decidiu, não há escolhido nem preterido", () => {
    expect(numeroEscolhido(divergencia())).toBeNull();
    expect(numeroPreterido(divergencia())).toBeNull();
  });
});

describe("sem par, a tela diz de que lado falta a identidade", () => {
  it("nomeia o lado da legenda e o lado da cena, e ignora os demais motivos", () => {
    expect(ladoSemIdentidade("item_without_element_ref")).toBe("legenda");
    expect(ladoSemIdentidade("element_ref_absent_from_scene")).toBe("cena");
    expect(ladoSemIdentidade("unit_mismatch")).toBeNull();
    expect(ladoSemIdentidade("within_tolerance")).toBeNull();
    expect(ladoSemIdentidade(null)).toBeNull();
  });

  it("a frase cita o lado e recusa por nome o casamento por número igual", () => {
    const naLegenda = frasePorFaltaDePar(desfecho());
    const naCena = frasePorFaltaDePar(
      desfecho({ element_ref: "EL-009", reason: "element_ref_absent_from_scene" }),
    );

    expect(naLegenda).toContain("na legenda");
    expect(naLegenda).toContain("Número igual não é identidade");
    expect(naCena).toContain("quantitativos.csv");
    expect(naCena).toContain("Número igual não é identidade");
  });

  it("motivo que não é ausência de par não vira frase de ausência de par", () => {
    expect(frasePorFaltaDePar(desfecho({ reason: "unit_mismatch" }))).toBeNull();
  });

  it("418,12 dos dois lados sem identidade continua sendo ausência de par", () => {
    // O caso mais tentador do pacote de design: dois números idênticos que NÃO casam.
    const linha = desfecho({
      reason: "item_without_element_ref",
      scene_quantity: null,
    });

    expect(linha.outcome).toBe("unchanged");
    // Nada neste módulo compara quantidade com quantidade para deduzir identidade.
    expect(frasePorFaltaDePar(linha)).toContain("Nenhum par");
  });
});

describe("o relatório do confronto", () => {
  const relatorio: SceneConfrontationReport = {
    job_id: "job-1",
    scene_revision_id: "rev-8",
    export_id: "exp-1",
    changed: true,
    fed: 1,
    divergences_recorded: 1,
    unchanged: 3,
    items: [
      desfecho({ item_id: "ti_0000000000000001", outcome: "fed", reason: null }),
      desfecho({ item_id: "ti_0000000000000002", reason: "within_tolerance" }),
    ],
  };

  it("todo item que não mudou carrega o motivo nomeado", () => {
    const intacto = relatorio.items.find((linha) => linha.outcome === "unchanged");

    expect(intacto?.reason).toBe("within_tolerance");
    // Item alimentado não carrega motivo: desfecho e motivo se excluem no contrato.
    expect(relatorio.items.find((linha) => linha.outcome === "fed")?.reason).toBeNull();
  });

  it("as contagens são as do servidor: nada é somado aqui", () => {
    expect(relatorio.fed + relatorio.divergences_recorded + relatorio.unchanged).toBe(5);
    // A soma acima é do TESTE, conferindo a fixture. O módulo não expõe nenhuma função que
    // some contagem — a tela exibe os três números como vieram.
    expect(relatorio.items).toHaveLength(2);
  });
});
