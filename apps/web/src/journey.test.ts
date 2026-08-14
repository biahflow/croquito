import { describe, expect, it } from "vitest";

import type {
  ExportArtifact,
  Review,
  ReviewReading,
  TraceSolveResponse,
  VisionProposal,
} from "./api";
import {
  deriveJourney,
  journeyStepStatusLabel,
  type JourneyStepId,
  type JourneyState,
} from "./journey";

function reading(
  id: string,
  status: ReviewReading["status"] = "proposed",
): ReviewReading {
  return { id, raw_text: "21,75", kind: "width", status };
}

const LINE: VisionProposal = {
  id: "vp_1",
  kind: "line",
  precision: "unresolved",
  export: false,
  geometry: { type: "line", start: { x: 0, y: 0 }, end: { x: 10, y: 0 } },
};

function review(overrides: Partial<Review> = {}): Review {
  return {
    job_id: "job",
    review_id: "review",
    version: 1,
    packet: { readings: [] },
    associations: { candidates: [] },
    proposals: { image_width_px: 100, image_height_px: 80, proposals: [LINE] },
    selected_associations: {},
    calibration: null,
    proposal_decisions: [],
    issues: [],
    blockers: [],
    required_criteria: [],
    scene: null,
    preview_urls: {},
    ...overrides,
  };
}

/** Cena métrica não aprovada com uma entidade traçada. */
function scene(overrides: Partial<NonNullable<Review["scene"]>> = {}) {
  return {
    id: "scene",
    version: 2,
    approved: false,
    entities: [
      {
        id: "entity-1",
        kind: "line",
        precision: "exact",
        geometry: { type: "line" },
      },
    ],
    issues: [],
    ...overrides,
  };
}

const TRACE_SOLVE: TraceSolveResponse = {
  trace_solve_id: "trace",
  job_id: "job",
  status: "COMPLETED",
  acceptance_id: "acceptance",
  base_review_version: 1,
  base_scene_version: null,
  solve_status: "solved_unapproved",
  blockers: [],
  unapplied_reading_ids: [],
  residual_summary: null,
  exact_entity_count: 4,
  approximate_entity_count: 1,
  note_count: 0,
  scale_m_per_px: null,
  detail_group_scales: {},
  result_scene_revision_id: "scene",
  result_scene_version: 2,
  result_review_version: 2,
  failure_code: null,
};

const EXPORT: ExportArtifact = {
  export_id: "export",
  job_id: "job",
  scene_revision_id: "scene",
  format: "dxf",
  status: "QUEUED",
  audit_status: null,
  dxf_sha256: null,
  failure_code: null,
  audit_errors: [],
  package_url: null,
};

function journey(
  overrides: {
    review?: Review | null;
    traceSolve?: TraceSolveResponse | null;
    exportArtifact?: ExportArtifact | null;
    approvedRevisionId?: string | null;
  } = {},
): JourneyState {
  return deriveJourney({
    review: review(),
    traceSolve: null,
    exportArtifact: null,
    approvedRevisionId: null,
    ...overrides,
  });
}

function step(state: JourneyState, id: JourneyStepId) {
  const found = state.steps.find((candidate) => candidate.id === id);
  if (!found) {
    throw new Error(`etapa ausente na jornada: ${id}`);
  }
  return found;
}

describe("deriveJourney — decisões", () => {
  it("conclui a etapa quando nenhuma leitura está proposta ou ambígua", () => {
    const state = journey({
      review: review({
        packet: {
          readings: [reading("r1", "confirmed"), reading("r2", "confirmed")],
        },
      }),
    });

    expect(step(state, "decisions").status).toBe("done");
    expect(step(state, "decisions").summary).toBe("2 de 2 leituras decididas");
  });

  it("conta leitura rejeitada como decidida", () => {
    const state = journey({
      review: review({
        packet: {
          readings: [reading("r1", "rejected"), reading("r2", "confirmed")],
        },
      }),
    });

    expect(step(state, "decisions").status).toBe("done");
  });

  it("segue em aberto enquanto houver leitura ambígua", () => {
    const state = journey({
      review: review({
        packet: {
          readings: [reading("r1", "confirmed"), reading("r2", "ambiguous")],
        },
      }),
    });

    expect(step(state, "decisions").status).toBe("available");
    expect(step(state, "decisions").summary).toBe("1 de 2 leituras decididas");
    expect(step(state, "decisions").blockedReason).toBeUndefined();
  });

  it("não conclui a etapa com o pacote sem leitura nenhuma", () => {
    const state = journey({ review: review({ packet: { readings: [] } }) });

    expect(step(state, "decisions").status).toBe("available");
    expect(step(state, "decisions").summary).toBe(
      "O pacote de revisão não trouxe leituras.",
    );
  });
});

describe("deriveJourney — traçado", () => {
  const undecided = review({
    packet: {
      readings: [
        reading("r1", "confirmed"),
        reading("r2", "proposed"),
        reading("r3", "ambiguous"),
      ],
    },
  });
  const decided = review({
    packet: { readings: [reading("r1", "confirmed")] },
  });

  it("bloqueia com a contagem pendente enquanto as decisões não fecham", () => {
    const state = journey({ review: undecided });

    expect(step(state, "trace").status).toBe("blocked");
    expect(step(state, "trace").blockedReason).toBe(
      "aguarda 2 leituras pendentes",
    );
  });

  it("bloqueia citando o pacote vazio quando não há leitura para decidir", () => {
    const state = journey({ review: review({ packet: { readings: [] } }) });

    expect(step(state, "trace").blockedReason).toBe(
      "o pacote de revisão ainda não tem leituras para decidir",
    );
  });

  it("bloqueia quando o desenho não trouxe formas detectadas", () => {
    const state = journey({
      review: review({
        packet: { readings: [reading("r1", "confirmed")] },
        proposals: null,
      }),
    });

    expect(step(state, "trace").status).toBe("blocked");
    expect(step(state, "trace").blockedReason).toBe(
      "o desenho ainda não tem formas detectadas",
    );
  });

  it("abre com as decisões fechadas e formas no desenho", () => {
    const state = journey({ review: decided });

    expect(step(state, "trace").status).toBe("available");
    expect(step(state, "trace").summary).toBe("1 forma detectada no desenho.");
  });

  it("conclui quando a cena métrica tem entidade", () => {
    const state = journey({
      review: review({
        packet: { readings: [reading("r1", "confirmed")] },
        scene: scene(),
      }),
    });

    expect(step(state, "trace").status).toBe("done");
    expect(step(state, "trace").summary).toBe("Cena métrica com 1 elemento.");
  });

  it("resume pelo estado do último aceite, sem duplicar a frase do traçado", () => {
    const state = journey({ review: decided, traceSolve: TRACE_SOLVE });

    expect(step(state, "trace").summary).toBe(
      "Traçado resolvido — 4 elementos exatos e 1 aproximado.",
    );
  });

  it("mantém o gate estrito mesmo com cena já traçada e leitura pendente", () => {
    const state = journey({
      review: review({
        packet: { readings: [reading("r1", "confirmed"), reading("r2")] },
        scene: scene(),
      }),
    });

    expect(step(state, "trace").status).toBe("blocked");
    expect(step(state, "trace").blockedReason).toBe(
      "aguarda 1 leitura pendente",
    );
  });
});

describe("deriveJourney — aprovação", () => {
  const traced = review({
    packet: { readings: [reading("r1", "confirmed")] },
    scene: scene(),
  });

  it("bloqueia sem cena com entidades", () => {
    const state = journey({
      review: review({ packet: { readings: [reading("r1", "confirmed")] } }),
    });

    expect(step(state, "approval").status).toBe("blocked");
    expect(step(state, "approval").blockedReason).toBe(
      "aguarda o traçado resolvido",
    );
  });

  it("bloqueia com cena existente mas vazia", () => {
    const state = journey({
      review: review({
        packet: { readings: [reading("r1", "confirmed")] },
        scene: scene({ entities: [] }),
      }),
    });

    expect(step(state, "approval").status).toBe("blocked");
  });

  it("abre quando a cena traçada aguarda assinatura", () => {
    const state = journey({ review: traced });

    expect(step(state, "approval").status).toBe("available");
    expect(step(state, "approval").summary).toBe(
      "Cena métrica com 1 elemento aguardando assinatura.",
    );
  });

  it("conclui com a cena aprovada", () => {
    const state = journey({
      review: review({
        packet: { readings: [reading("r1", "confirmed")] },
        scene: scene({ approved: true }),
      }),
    });

    expect(step(state, "approval").status).toBe("done");
    expect(step(state, "approval").summary).toBe(
      "Cena v2 aprovada tecnicamente.",
    );
  });

  it("conclui pela aprovação recém-registrada nesta sessão", () => {
    const state = journey({ review: traced, approvedRevisionId: "revision-7" });

    expect(step(state, "approval").status).toBe("done");
  });

  it("ignora o identificador de revisão vazio que o App guarda antes de aprovar", () => {
    const state = journey({ review: traced, approvedRevisionId: "" });

    expect(step(state, "approval").status).toBe("available");
  });
});

describe("deriveJourney — exportação", () => {
  const approved = review({
    packet: { readings: [reading("r1", "confirmed")] },
    scene: scene({ approved: true }),
  });

  it("bloqueia até a aprovação técnica", () => {
    const state = journey({
      review: review({
        packet: { readings: [reading("r1", "confirmed")] },
        scene: scene(),
      }),
    });

    expect(step(state, "export").status).toBe("blocked");
    expect(step(state, "export").blockedReason).toBe(
      "aguarda a aprovação técnica",
    );
  });

  it("abre com a cena aprovada e nenhuma exportação pedida", () => {
    const state = journey({ review: approved });

    expect(step(state, "export").status).toBe("available");
    expect(step(state, "export").summary).toBe(
      "Nenhuma exportação solicitada.",
    );
  });

  it("conclui com o pacote auditado disponível", () => {
    const state = journey({
      review: approved,
      exportArtifact: { ...EXPORT, status: "COMPLETED" },
    });

    expect(step(state, "export").status).toBe("done");
  });

  it("volta a etapa em aberto quando a exportação falha, sem virar bloqueio do trilho", () => {
    const state = journey({
      review: approved,
      exportArtifact: {
        ...EXPORT,
        status: "FAILED",
        failure_code: "EXPORT_AUDIT_FAILED",
      },
    });

    expect(step(state, "export").status).toBe("available");
    expect(step(state, "export").blockedReason).toBeUndefined();
    expect(step(state, "export").summary).toContain("EXPORT_AUDIT_FAILED");
  });
});

describe("deriveJourney — etapa ativa", () => {
  it("fica nas decisões enquanto houver leitura pendente", () => {
    expect(journey().activeStep).toBe("decisions");
  });

  it("anda para o traçado assim que todas as leituras estão decididas", () => {
    const state = journey({
      review: review({ packet: { readings: [reading("r1", "confirmed")] } }),
    });

    expect(state.activeStep).toBe("trace");
  });

  it("anda para a aprovação quando a cena métrica existe", () => {
    const state = journey({
      review: review({
        packet: { readings: [reading("r1", "confirmed")] },
        scene: scene(),
      }),
    });

    expect(state.activeStep).toBe("approval");
  });

  it("anda para a exportação depois da aprovação", () => {
    const state = journey({
      review: review({
        packet: { readings: [reading("r1", "confirmed")] },
        scene: scene({ approved: true }),
      }),
    });

    expect(state.activeStep).toBe("export");
  });

  it("fica na exportação quando toda a jornada está concluída", () => {
    const state = journey({
      review: review({
        packet: { readings: [reading("r1", "confirmed")] },
        scene: scene({ approved: true }),
      }),
      exportArtifact: { ...EXPORT, status: "COMPLETED" },
    });

    expect(state.steps.every((item) => item.status === "done")).toBe(true);
    expect(state.activeStep).toBe("export");
  });

  it("nunca ativa uma etapa bloqueada: sem formas detectadas a jornada volta às decisões", () => {
    const state = journey({
      review: review({
        packet: { readings: [reading("r1", "confirmed")] },
        proposals: null,
      }),
    });

    expect(step(state, "trace").status).toBe("blocked");
    expect(state.activeStep).toBe("decisions");
  });
});

describe("deriveJourney — sem revisão aberta", () => {
  it("bloqueia tudo com motivo neutro em vez de explodir", () => {
    const state = deriveJourney({
      review: null,
      traceSolve: null,
      exportArtifact: null,
      approvedRevisionId: null,
    });

    expect(state.steps).toHaveLength(4);
    expect(
      state.steps.every(
        (item) =>
          item.status === "blocked" &&
          item.blockedReason === "aguarda a abertura de uma revisão",
      ),
    ).toBe(true);
    expect(state.activeStep).toBe("decisions");
  });
});

describe("journeyStepStatusLabel", () => {
  it("escreve o estado de cada etapa", () => {
    expect(journeyStepStatusLabel("blocked")).toBe("bloqueada");
    expect(journeyStepStatusLabel("available")).toBe("em aberto");
    expect(journeyStepStatusLabel("done")).toBe("concluída");
  });
});
