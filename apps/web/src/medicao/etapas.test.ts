import { describe, expect, it } from "vitest";
import type { RoundState, RoundStateExtraction } from "./api";
import { derivarEtapas, etapaStatusLabel, type EtapaId } from "./etapas";

/**
 * O estado abaixo é a FORMA que `GET /v1/valuation-rounds/{round_id}` devolve
 * (`round_state_payload`), a mesma que `tests/e2e/test_valuation_v1_chain.py` lê: chaves
 * em inglês, `extraction`/`plate` no lugar do que era diretório, e nenhuma mensagem pronta
 * — a frase da falha é escrita a partir do `failure_code` estável.
 */
const EXTRACTION_DONE: RoundStateExtraction = {
  status: "done",
  extraction_id: "0197f2a0-0000-7000-8000-0000000000ee",
  failure_code: null,
  lineage_present: true,
  updated_at: "2026-08-17T12:00:00+00:00",
};

function estado(overrides: {
  takeoff?: Partial<RoundState["takeoff"]>;
  codes?: Partial<RoundState["codes"]>;
  bulletin?: Partial<RoundState["bulletin"]>;
  extraction?: Partial<RoundStateExtraction>;
  plate?: Partial<RoundState["plate"]>;
}): RoundState {
  return {
    round_id: "0197f2a0-0000-7000-8000-000000000001",
    version: 4,
    status: "OPEN",
    reviewer_role: "orcamentista",
    worksite_key: "praca-sintetica-oeste",
    worksite_name: "PRACA SINTETICA OESTE",
    reference_label: "MEDICAO SINTETICA 01/2026",
    period_number: 1,
    address: null,
    contract_label: null,
    revision_id: "0197f2a0-0000-7000-8000-0000000000f1",
    revision_version: 1,
    catalog: {
      source_sha256: "c".repeat(64),
      summary: { source_label: "CATALOGO SINTETICO", entries: 5 },
    },
    artifacts: { takeoff_packet_json: "a".repeat(64) },
    plate: { present: true, source_sha256: "d".repeat(64), page_count: 1, ...overrides.plate },
    extraction: { ...EXTRACTION_DONE, ...overrides.extraction },
    takeoff: {
      present: true,
      packet_sha256: "a".repeat(64),
      plate_id: "plate-sintetica-v1",
      page_number: 1,
      review_status: "review_required",
      items: 7,
      proposed: 6,
      ambiguous: 1,
      confirmed: 0,
      rejected: 0,
      pending: 7,
      anchors_registered: 7,
      anchors_raw: 0,
      ...overrides.takeoff,
    },
    codes: {
      suggestions_present: false,
      suggestions_sha256: null,
      assignments_present: false,
      assignments_sha256: null,
      confirmed: 0,
      rejected: 0,
      pending: 0,
      ...overrides.codes,
    },
    bulletin: { present: false, valuation_sha256: null, ...overrides.bulletin },
    dossier: { present: false, dossier_sha256: null },
    created_at: "2026-08-17T11:00:00+00:00",
    updated_at: "2026-08-17T12:00:00+00:00",
  };
}

function porId(state: RoundState | null, id: EtapaId) {
  const etapa = derivarEtapas(state).etapas.find((candidate) => candidate.id === id);
  if (!etapa) {
    throw new Error(`etapa ${id} não derivada`);
  }
  return etapa;
}

describe("derivarEtapas", () => {
  it("sem estado lido, tudo fica bloqueado e a jornada não explode", () => {
    const jornada = derivarEtapas(null);

    expect(jornada.etapas.map((etapa) => etapa.id)).toEqual([
      "prancha",
      "revisao",
      "codigos",
      "boletim",
    ]);
    expect(jornada.etapas.map((etapa) => etapa.status)).toEqual([
      "blocked",
      "blocked",
      "blocked",
      "blocked",
    ]);
    expect(jornada.etapaAtiva).toBe("prancha");
    expect(jornada.etapas[0].blockedReason).toContain("aguarda a leitura do estado");
  });

  it("rodada sem prancha nenhuma: Prancha fica em aberto, o resto bloqueado com o motivo", () => {
    const state = estado({
      takeoff: { present: false },
      plate: { present: false, source_sha256: null, page_count: null },
      extraction: { status: "idle", extraction_id: null, lineage_present: false },
    });
    const jornada = derivarEtapas(state);

    expect(porId(state, "prancha").status).toBe("available");
    expect(porId(state, "prancha").summary).toContain("Nenhuma prancha enviada");
    expect(porId(state, "revisao").status).toBe("blocked");
    expect(porId(state, "revisao").blockedReason).toContain("use a etapa Prancha");
    expect(porId(state, "codigos").status).toBe("blocked");
    expect(porId(state, "boletim").status).toBe("blocked");
    expect(jornada.etapaAtiva).toBe("prancha");
  });

  /**
   * Prancha associada e leitura ainda não disparada é caminho normal: em `/v1` associar a
   * prancha e pedir a extração são dois atos, e o segundo pode ter sido recusado por
   * entitlement ou ambiente sem provider.
   */
  it("prancha enviada sem leitura disparada manda de volta à etapa Prancha", () => {
    const state = estado({
      takeoff: { present: false },
      extraction: { status: "idle", extraction_id: null, lineage_present: false },
    });

    expect(porId(state, "prancha").summary).toContain("ainda não foi disparada");
    expect(porId(state, "revisao").blockedReason).toContain(
      "dispare a leitura automática",
    );
  });

  it("leitura na fila e leitura em andamento têm motivos distintos", () => {
    const naFila = estado({
      takeoff: { present: false },
      extraction: { status: "queued" },
    });
    const rodando = estado({
      takeoff: { present: false },
      extraction: { status: "running" },
    });

    expect(porId(naFila, "prancha").summary).toContain("enfileirada");
    expect(porId(naFila, "revisao").blockedReason).toContain("está na fila");
    expect(porId(rodando, "prancha").summary).toContain("Lendo a legenda");
    expect(porId(rodando, "revisao").blockedReason).toContain("em andamento");
    expect(porId(rodando, "boletim").blockedReason).toContain("em andamento");
  });

  it("leitura que falhou traduz o código estável da rodada em frase de obra", () => {
    const state = estado({
      takeoff: { present: false },
      extraction: {
        status: "failed",
        failure_code: "PROVIDER_EXECUTION_FAILED",
        lineage_present: false,
      },
    });

    expect(porId(state, "prancha").summary).toBe(
      "A chamada ao provider falhou; nenhum artefato foi publicado nesta rodada.",
    );
    expect(porId(state, "revisao").blockedReason).toBe(
      "A chamada ao provider falhou; nenhum artefato foi publicado nesta rodada.",
    );
  });

  it("falha sem código conhecido não vira frase inventada", () => {
    const state = estado({
      takeoff: { present: false },
      extraction: { status: "failed", failure_code: "CODIGO_NOVO_DO_SERVIDOR" },
    });

    expect(porId(state, "prancha").summary).toContain("CODIGO_NOVO_DO_SERVIDOR");
  });

  it("prancha lida vira etapa concluída assim que o takeoff existe", () => {
    const state = estado({});

    expect(porId(state, "prancha").status).toBe("done");
    expect(porId(state, "prancha").summary).toContain("disponível para revisão");
  });

  it("revisão em aberto conta os itens já decididos e bloqueia códigos com o motivo", () => {
    const state = estado({
      takeoff: { pending: 2, proposed: 1, ambiguous: 1, confirmed: 4, rejected: 1 },
    });
    const jornada = derivarEtapas(state);

    expect(jornada.etapaAtiva).toBe("revisao");
    expect(porId(state, "revisao").summary).toBe("5 de 7 itens decididos.");
    expect(porId(state, "codigos").status).toBe("blocked");
    expect(porId(state, "codigos").blockedReason).toBe(
      "2 itens ainda sem decisão no takeoff",
    );
    expect(porId(state, "boletim").blockedReason).toBe(
      "aguarda 2 itens da revisão do takeoff",
    );
  });

  it("um único item pendente fala no singular", () => {
    const state = estado({
      takeoff: { pending: 1, proposed: 1, ambiguous: 0, confirmed: 6, rejected: 0 },
    });

    expect(porId(state, "codigos").blockedReason).toBe(
      "1 item ainda sem decisão no takeoff",
    );
  });

  it("revisão completa abre códigos e diz quantos faltam", () => {
    const state = estado({
      takeoff: {
        review_status: "complete",
        pending: 0,
        proposed: 0,
        ambiguous: 0,
        confirmed: 6,
        rejected: 1,
      },
      codes: { pending: 3, confirmed: 2, rejected: 1, assignments_present: true },
    });
    const jornada = derivarEtapas(state);

    expect(jornada.etapaAtiva).toBe("codigos");
    expect(porId(state, "revisao").status).toBe("done");
    expect(porId(state, "revisao").summary).toBe(
      "Revisão completa: 6 confirmados, 1 rejeitados.",
    );
    expect(porId(state, "codigos").status).toBe("available");
    expect(porId(state, "codigos").summary).toBe("Revisão completa, 3 códigos pendentes.");
    expect(porId(state, "boletim").status).toBe("blocked");
    expect(porId(state, "boletim").blockedReason).toBe(
      "aguarda a decisão de código de 3 itens",
    );
  });

  it("revisão que rejeitou tudo bloqueia códigos: não há quantitativo a codificar", () => {
    const state = estado({
      takeoff: {
        review_status: "complete",
        pending: 0,
        proposed: 0,
        ambiguous: 0,
        confirmed: 0,
        rejected: 7,
      },
    });

    expect(porId(state, "codigos").status).toBe("blocked");
    expect(porId(state, "codigos").blockedReason).toContain("nenhum item foi confirmado");
    expect(porId(state, "boletim").blockedReason).toBe("nenhum item confirmado no takeoff");
    expect(derivarEtapas(state).etapaAtiva).toBe("revisao");
  });

  it("códigos decididos abrem o boletim, ainda não montado", () => {
    const state = estado({
      takeoff: {
        review_status: "complete",
        pending: 0,
        proposed: 0,
        ambiguous: 0,
        confirmed: 6,
        rejected: 1,
      },
      codes: { pending: 0, confirmed: 5, rejected: 1, assignments_present: true },
    });
    const jornada = derivarEtapas(state);

    expect(porId(state, "codigos").status).toBe("done");
    expect(porId(state, "codigos").summary).toBe(
      "5 códigos confirmados, 1 sem código no contrato.",
    );
    expect(jornada.etapaAtiva).toBe("boletim");
    expect(porId(state, "boletim").status).toBe("available");
  });

  it("medição gravada conclui a jornada e a etapa ativa é a última alcançável", () => {
    const state = estado({
      takeoff: {
        review_status: "complete",
        pending: 0,
        proposed: 0,
        ambiguous: 0,
        confirmed: 6,
        rejected: 1,
      },
      codes: { pending: 0, confirmed: 6, rejected: 0, assignments_present: true },
      bulletin: { present: true, valuation_sha256: "b".repeat(64) },
    });
    const jornada = derivarEtapas(state);

    expect(jornada.etapas.map((etapa) => etapa.status)).toEqual([
      "done",
      "done",
      "done",
      "done",
    ]);
    expect(jornada.etapaAtiva).toBe("boletim");
    expect(porId(state, "boletim").summary).toContain("sem aprovação");
  });
});

describe("etapaStatusLabel", () => {
  it("escreve o estado da etapa", () => {
    expect(etapaStatusLabel("blocked")).toBe("bloqueada");
    expect(etapaStatusLabel("available")).toBe("em aberto");
    expect(etapaStatusLabel("done")).toBe("concluída");
  });
});
