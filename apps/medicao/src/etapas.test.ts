import { describe, expect, it } from "vitest";
import type { ExtractionState, RunState } from "./api";
import { derivarEtapas, etapaStatusLabel, type EtapaId } from "./etapas";

const EXTRACAO_DONE: ExtractionState = {
  status: "done",
  error_code: null,
  message: "extração concluída; todo item nasce para a revisão do orçamentista",
  details: null,
  execution: null,
  consented_source_sha256: "c".repeat(64),
  arm: "anthropic:claude-fixture",
  plate_pdf_present: true,
  pages: 1,
  page_number: 1,
  notes: [],
};

function estado(overrides: {
  takeoff?: Partial<RunState["takeoff"]>;
  codes?: Partial<RunState["codes"]>;
  bulletin?: Partial<RunState["bulletin"]>;
  extracao?: Partial<ExtractionState>;
}): RunState {
  return {
    server_version: "local-valuation-server-v1",
    root: "/rodada",
    reviewer_id: "orcamentista-de-teste",
    reviewer_role: "orcamentista",
    artifacts: {},
    busca_semantica: {
      status: "unavailable",
      message: "busca semântica indisponível: sem índice",
      index_present: false,
      model_id: null,
    },
    images: { plate: { present: true, filename: "prancha.png" }, overlay: { present: true } },
    extracao: { ...EXTRACAO_DONE, ...overrides.extracao },
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
  };
}

function porId(state: RunState | null, id: EtapaId) {
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
      extracao: {
        status: "idle",
        message: "nenhuma prancha enviada nesta rodada",
        plate_pdf_present: false,
        pages: null,
      },
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

  it("prancha ingerida, extração em andamento: Prancha em aberto e revisão bloqueada pelo motivo certo", () => {
    const state = estado({
      takeoff: { present: false },
      extracao: {
        status: "running",
        message: "extração automática em andamento; chamada paga configurada no servidor",
        plate_pdf_present: true,
        pages: 1,
      },
    });

    expect(porId(state, "prancha").status).toBe("available");
    expect(porId(state, "prancha").summary).toContain("Lendo a legenda");
    expect(porId(state, "revisao").blockedReason).toContain(
      "extração automática da prancha está em andamento",
    );
    expect(porId(state, "codigos").blockedReason).toContain("em andamento");
    expect(porId(state, "boletim").blockedReason).toContain("em andamento");
  });

  it("extração falhou: o motivo do bloqueio é a mensagem declarada pelo servidor", () => {
    const state = estado({
      takeoff: { present: false },
      extracao: {
        status: "failed",
        error_code: "PROVIDER_EXECUTION_FAILED",
        message: "a chamada ao provider falhou; nenhum artefato foi publicado",
        plate_pdf_present: true,
        pages: 1,
      },
    });

    expect(porId(state, "prancha").summary).toBe(
      "a chamada ao provider falhou; nenhum artefato foi publicado",
    );
    expect(porId(state, "revisao").blockedReason).toBe(
      "a chamada ao provider falhou; nenhum artefato foi publicado",
    );
  });

  it("extração indisponível: o motivo do bloqueio é a mensagem declarada pelo servidor", () => {
    const state = estado({
      takeoff: { present: false },
      extracao: {
        status: "unavailable",
        error_code: "LOCAL_EXTRACTION_UNAVAILABLE",
        message: "extração automática indisponível: teto de gasto não configurado no servidor",
        plate_pdf_present: true,
        pages: 1,
      },
    });

    expect(porId(state, "prancha").summary).toContain("teto de gasto não configurado");
    expect(porId(state, "revisao").blockedReason).toContain("teto de gasto não configurado");
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
