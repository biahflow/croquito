import { describe, expect, it } from "vitest";

import type { CascadeEntry, EstimateState } from "./api";
import { derivarEtapas, etapaStatusLabel, type EtapaId } from "./etapas";

function fonte(overrides: Partial<CascadeEntry> = {}): CascadeEntry {
  return {
    position: 1,
    origin: "sco",
    source_sha256: "a".repeat(64),
    reference_month: "2026-04",
    source_label: "SCO 04/2026",
    summary: { entries: 3412 },
    ...overrides,
  };
}

function estado(overrides: Partial<EstimateState> = {}): EstimateState {
  return {
    round_id: "0197f2a0-0000-7000-8000-000000000009",
    version: 1,
    status: "OPEN",
    reviewer_role: "orcamentista",
    worksite_key: "praca-do-exemplo",
    worksite_name: "Praça do Exemplo",
    reference_label: "ORÇAMENTO-BASE 2026",
    address: null,
    revision_id: null,
    revision_version: null,
    cascade: [],
    artifacts: {},
    plate: { present: false, source_sha256: null, page_count: null },
    extraction: {
      status: "idle",
      extraction_id: null,
      failure_code: null,
      lineage_present: false,
      updated_at: null,
    },
    takeoff: { present: false },
    codes: {
      suggestions_present: false,
      suggestions_sha256: null,
      assignments_present: false,
      assignments_sha256: null,
      confirmed: 0,
      rejected: 0,
      pending: null,
    },
    estimate: {
      present: false,
      estimate_sha256: null,
      workbook_present: false,
      workbook_sha256: null,
    },
    created_at: "2026-08-20T10:00:00Z",
    updated_at: "2026-08-20T10:00:00Z",
    ...overrides,
  };
}

function etapa(state: EstimateState | null, id: EtapaId) {
  const found = derivarEtapas(state).etapas.find((item) => item.id === id);
  if (found === undefined) {
    throw new Error(`etapa ausente: ${id}`);
  }
  return found;
}

describe("estado ainda não lido", () => {
  it("bloqueia tudo e não inventa etapa em aberto", () => {
    const jornada = derivarEtapas(null);

    expect(jornada.etapaAtiva).toBe("cascata");
    expect(jornada.etapas).toHaveLength(6);
    expect(jornada.etapas.every((item) => item.status === "blocked")).toBe(true);
  });
});

/**
 * A cascata é a primeira etapa da jornada: um orçamento sem fonte de preço não precifica
 * nada, e a ordem instalada é a regra de precificação.
 */
describe("cascata", () => {
  it("orçamento recém-aberto abre na cascata, com ela vazia", () => {
    const jornada = derivarEtapas(estado());

    expect(jornada.etapaAtiva).toBe("cascata");
    expect(etapa(estado(), "cascata").status).toBe("available");
    expect(etapa(estado(), "cascata").summary).toContain("Nenhuma fonte");
  });

  it("com fontes instaladas, a etapa fica concluída e a ORDEM aparece no resumo", () => {
    const state = estado({
      cascade: [
        fonte(),
        fonte({
          position: 2,
          origin: "emop",
          source_sha256: "b".repeat(64),
          source_label: "EMOP 07/2026",
        }),
      ],
    });

    const cascata = etapa(state, "cascata");
    expect(cascata.status).toBe("done");
    expect(cascata.summary).toContain("sco → emop");
  });

  /**
   * Exceção declarada: o servidor não recusa associar prancha com a cascata vazia. É
   * ordem da JORNADA, e o motivo é escrito como tal — não como uma recusa do servidor.
   */
  it("a prancha espera a cascata, e o motivo é dito por extenso", () => {
    const prancha = etapa(estado(), "prancha");

    expect(prancha.status).toBe("blocked");
    expect(prancha.blockedReason).toContain("cascata ainda não tem fonte de preço");
  });

  it("instalada a primeira fonte, a prancha abre", () => {
    expect(etapa(estado({ cascade: [fonte()] }), "prancha").status).toBe("available");
  });
});

/** Espelho do que a medição já faz: o motivo do bloqueio conta o estado da extração. */
describe("prancha e leitura automática da legenda", () => {
  const comCascata = { cascade: [fonte()] };

  it("na fila, as etapas seguintes dizem que a leitura está na fila", () => {
    const state = estado({
      ...comCascata,
      plate: { present: true, source_sha256: "c".repeat(64), page_count: 1 },
      extraction: {
        status: "queued",
        extraction_id: "ex-1",
        failure_code: null,
        lineage_present: false,
        updated_at: null,
      },
    });

    expect(etapa(state, "prancha").summary).toContain("enfileirada");
    expect(etapa(state, "revisao").blockedReason).toContain("está na fila");
  });

  it("falha traz a frase do failure_code, nunca uma mensagem inventada", () => {
    const state = estado({
      ...comCascata,
      plate: { present: true, source_sha256: "c".repeat(64), page_count: 1 },
      extraction: {
        status: "failed",
        extraction_id: "ex-1",
        failure_code: "PROVIDER_EXECUTION_FAILED",
        lineage_present: false,
        updated_at: null,
      },
    });

    expect(etapa(state, "prancha").summary).toContain("nenhum artefato foi publicado");
    expect(etapa(state, "revisao").blockedReason).toContain("provider");
  });
});

describe("revisão, códigos, montagem e planilha", () => {
  const base = {
    cascade: [fonte()],
    plate: { present: true, source_sha256: "c".repeat(64), page_count: 1 },
  };

  const revisaoIncompleta = estado({
    ...base,
    takeoff: {
      present: true,
      items: 4,
      proposed: 2,
      ambiguous: 0,
      confirmed: 2,
      rejected: 0,
      pending: 2,
      review_status: "review_required",
    },
    codes: {
      suggestions_present: false,
      suggestions_sha256: null,
      assignments_present: false,
      assignments_sha256: null,
      confirmed: 0,
      rejected: 0,
      pending: 2,
    },
  });

  it("revisão incompleta trava os códigos e a montagem, contando o que falta", () => {
    expect(etapa(revisaoIncompleta, "revisao").status).toBe("available");
    expect(etapa(revisaoIncompleta, "revisao").summary).toBe("2 de 4 itens decididos.");
    expect(etapa(revisaoIncompleta, "codigos").blockedReason).toContain(
      "2 itens ainda sem decisão",
    );
    expect(etapa(revisaoIncompleta, "montagem").status).toBe("blocked");
  });

  const codigosPendentes = estado({
    ...base,
    takeoff: {
      present: true,
      items: 4,
      proposed: 0,
      ambiguous: 0,
      confirmed: 3,
      rejected: 1,
      pending: 0,
      review_status: "complete",
    },
    codes: {
      suggestions_present: true,
      suggestions_sha256: "d".repeat(64),
      assignments_present: true,
      assignments_sha256: "e".repeat(64),
      confirmed: 1,
      rejected: 0,
      pending: 2,
    },
  });

  it("com código pendente, a montagem espera e diz quantos faltam", () => {
    expect(etapa(codigosPendentes, "codigos").status).toBe("available");
    expect(etapa(codigosPendentes, "montagem").status).toBe("blocked");
    expect(etapa(codigosPendentes, "montagem").blockedReason).toContain("2 itens");
  });

  const prontoParaMontar = estado({
    ...base,
    takeoff: {
      present: true,
      items: 4,
      proposed: 0,
      ambiguous: 0,
      confirmed: 3,
      rejected: 1,
      pending: 0,
      review_status: "complete",
    },
    codes: {
      suggestions_present: true,
      suggestions_sha256: "d".repeat(64),
      assignments_present: true,
      assignments_sha256: "e".repeat(64),
      confirmed: 3,
      rejected: 0,
      pending: 0,
    },
  });

  it("com tudo decidido, a montagem abre e a planilha ainda não existe", () => {
    const jornada = derivarEtapas(prontoParaMontar);

    expect(jornada.etapaAtiva).toBe("montagem");
    expect(etapa(prontoParaMontar, "codigos").status).toBe("done");
    expect(etapa(prontoParaMontar, "montagem").status).toBe("available");
    expect(etapa(prontoParaMontar, "planilha").status).toBe("blocked");
    expect(etapa(prontoParaMontar, "planilha").blockedReason).toContain(
      "ainda não foi montado",
    );
  });

  /**
   * `estimate.present` e `workbook_present` são campos DISTINTOS do estado, e a diferença
   * entre eles é o portão: auditoria reprovada não publica planilha nenhuma.
   */
  it("orçamento montado sem planilha aprovada não conclui a etapa da planilha", () => {
    const state = estado({
      ...prontoParaMontar,
      estimate: {
        present: true,
        estimate_sha256: "f".repeat(64),
        workbook_present: false,
        workbook_sha256: null,
      },
    });

    expect(etapa(state, "montagem").status).toBe("done");
    expect(etapa(state, "planilha").status).toBe("blocked");
    expect(etapa(state, "planilha").blockedReason).toContain(
      "nenhuma planilha aprovada pela auditoria",
    );
  });

  it("com a planilha publicada, a jornada fecha na planilha", () => {
    const state = estado({
      ...prontoParaMontar,
      estimate: {
        present: true,
        estimate_sha256: "f".repeat(64),
        workbook_present: true,
        workbook_sha256: "0".repeat(64),
      },
    });

    expect(etapa(state, "planilha").status).toBe("done");
    expect(derivarEtapas(state).etapaAtiva).toBe("planilha");
  });
});

describe("estado da etapa em texto", () => {
  it("cada estado tem palavra própria; cor nunca é o único indicador", () => {
    expect(etapaStatusLabel("blocked")).toBe("bloqueada");
    expect(etapaStatusLabel("available")).toBe("em aberto");
    expect(etapaStatusLabel("done")).toBe("concluída");
  });
});
