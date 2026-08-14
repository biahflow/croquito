import { describe, expect, it } from "vitest";

import type { ChatActDraft, ChatTurn, ReviewChatOutput, ReviewReading } from "./api";
import {
  applyDraftToTraceDraft,
  buildChatAnchors,
  chatActAnchor,
  chatActLabel,
  chatAnswerSummary,
  chatFailureLabel,
  chatQuestionIssue,
  chatTurnInFlight,
  chatTurnStatusLabel,
  draftToReviewDecision,
  pickOpenChatSession,
} from "./chat";
import { emptyTraceDraft, MAX_NOTE_LENGTH, type TraceDraft } from "./trace";

const READING_ID = "rd_1111111111111111";
const OTHER_READING_ID = "rd_2222222222222222";
const PROPOSAL_ID = "vp_1111111111111111";
const OTHER_PROPOSAL_ID = "vp_2222222222222222";

function reading(overrides: Partial<ReviewReading> = {}): ReviewReading {
  return {
    id: READING_ID,
    raw_text: "21,75",
    kind: "width",
    status: "proposed",
    ...overrides,
  };
}

function turn(overrides: Partial<ChatTurn> = {}): ChatTurn {
  return {
    chat_turn_id: "ct_1",
    chat_session_id: "cs_1",
    job_id: "job-1",
    sequence: 1,
    status: "QUEUED",
    question: "Essa cota mede o patamar ou a mureta?",
    anchors: { reading_ids: [], proposal_ids: [] },
    answer: null,
    failure_code: null,
    created_at: "2026-08-13T10:00:00Z",
    updated_at: "2026-08-13T10:00:00Z",
    ...overrides,
  };
}

function answer(overrides: Partial<ReviewChatOutput> = {}): ReviewChatOutput {
  return {
    task: "review-chat",
    answer_kind: "answer",
    answer_text: "A cota está escrita ao lado do elemento apontado.",
    evidence_notes: [],
    open_question: null,
    proposed_acts: [],
    ...overrides,
  };
}

const naming = {
  proposalName: (proposalId: string) =>
    proposalId === PROPOSAL_ID ? "① linha vertical" : "② linha horizontal",
  readings: [reading()],
};

function draft(overrides: Partial<TraceDraft> = {}): TraceDraft {
  return { ...emptyTraceDraft(), ...overrides };
}

describe("pergunta", () => {
  it("recusa texto curto demais e texto acima do contrato", () => {
    expect(chatQuestionIssue("  a ")).toContain("mínimo de 3 caracteres");
    expect(chatQuestionIssue("x".repeat(501))).toContain("500 caracteres");
  });

  it("aceita a pergunta que cabe no contrato", () => {
    expect(chatQuestionIssue("Essa cota mede o patamar?")).toBeNull();
  });
});

describe("âncoras", () => {
  it("apara pelo limite do contrato e não repete id", () => {
    const anchors = buildChatAnchors(
      [READING_ID, READING_ID],
      Array.from({ length: 25 }, (_, index) => `vp_${index}`),
    );
    expect(anchors.reading_ids).toEqual([READING_ID]);
    expect(anchors.proposal_ids).toHaveLength(20);
    expect(anchors.proposal_ids[0]).toBe("vp_0");
  });
});

describe("sessão", () => {
  it("reusa a primeira conversa aberta e ignora as encerradas", () => {
    expect(
      pickOpenChatSession([
        {
          chat_session_id: "cs_old",
          status: "CLOSED",
          created_at: "2026-08-13T09:00:00Z",
          turn_count: 3,
        },
        {
          chat_session_id: "cs_open",
          status: "OPEN",
          created_at: "2026-08-13T10:00:00Z",
          turn_count: 0,
        },
      ])?.chat_session_id,
    ).toBe("cs_open");
  });

  it("devolve nada quando não há conversa aberta", () => {
    expect(pickOpenChatSession([])).toBeNull();
  });
});

describe("estado do turno em língua de obra", () => {
  it("descreve fila, execução e resposta", () => {
    expect(chatTurnStatusLabel(turn())).toBe("na fila, aguardando resposta…");
    expect(chatTurnStatusLabel(turn({ status: "RUNNING" }))).toContain(
      "lendo a folha",
    );
    expect(chatTurnStatusLabel(turn({ status: "COMPLETED" }))).toBe(
      "o agente respondeu",
    );
  });

  it("explica a recusa por citação desconhecida sem código cru na frase", () => {
    const label = chatTurnStatusLabel(
      turn({ status: "FAILED", failure_code: "CHAT_ACT_UNKNOWN_REFERENCE" }),
    );
    expect(label).toContain("não está na folha");
    expect(label).not.toContain("CHAT_ACT_UNKNOWN_REFERENCE");
  });

  it("mostra o código estável quando ele não tem frase própria", () => {
    expect(chatFailureLabel("CHAT_SOMETHING_NEW")).toContain(
      "CHAT_SOMETHING_NEW",
    );
  });

  it("sabe quando ainda há turno em voo", () => {
    expect(chatTurnInFlight(turn())).toBe(true);
    expect(chatTurnInFlight(turn({ status: "RUNNING" }))).toBe(true);
    expect(chatTurnInFlight(turn({ status: "COMPLETED" }))).toBe(false);
    expect(chatTurnInFlight(null)).toBe(false);
  });
});

describe("resumo da resposta", () => {
  it("conta as sugestões", () => {
    expect(
      chatAnswerSummary(
        answer({
          proposed_acts: [{ act: "pending_note", text: "Falta a cota do vão." }],
        }),
      ),
    ).toBe("respondeu com 1 sugestão para você revisar");
    expect(
      chatAnswerSummary(
        answer({
          proposed_acts: [
            { act: "pending_note", text: "Falta a cota do vão." },
            { act: "keep_apart", first: PROPOSAL_ID, second: OTHER_PROPOSAL_ID },
          ],
        }),
      ),
    ).toContain("2 sugestões");
  });

  it("declara a incerteza em vez de fingir resposta", () => {
    expect(
      chatAnswerSummary(
        answer({
          answer_kind: "uncertain",
          open_question: "A cota mede o patamar ou a mureta?",
        }),
      ),
    ).toContain("ainda não dá para afirmar");
  });

  it("resposta incerta não traz ato para aplicar", () => {
    const uncertain = answer({
      answer_kind: "uncertain",
      open_question: "A cota mede o patamar ou a mureta?",
    });
    expect(uncertain.proposed_acts).toEqual([]);
  });
});

describe("âncora do cartão", () => {
  it("aponta leitura e formas citadas por cada ato", () => {
    expect(
      chatActAnchor({
        act: "reading_decision",
        reading_id: READING_ID,
        action: "confirm",
        association_proposal_id: PROPOSAL_ID,
        annotation: false,
        justification_draft: "Cota conferida.",
      }),
    ).toEqual({ readingId: READING_ID, proposalIds: [PROPOSAL_ID] });
    expect(
      chatActAnchor({
        act: "trace_association",
        reading_id: READING_ID,
        target: [PROPOSAL_ID, OTHER_PROPOSAL_ID],
      }),
    ).toEqual({
      readingId: READING_ID,
      proposalIds: [PROPOSAL_ID, OTHER_PROPOSAL_ID],
    });
    expect(
      chatActAnchor({
        act: "note_association",
        reading_id: READING_ID,
        target: `legenda:${PROPOSAL_ID}`,
      }),
    ).toEqual({ readingId: READING_ID, proposalIds: [PROPOSAL_ID] });
    expect(
      chatActAnchor({
        act: "note_association",
        reading_id: READING_ID,
        target: `${PROPOSAL_ID}#v`,
      }).proposalIds,
    ).toEqual([PROPOSAL_ID]);
    expect(
      chatActAnchor({ act: "note_association", reading_id: READING_ID, target: "carimbo" })
        .proposalIds,
    ).toEqual([]);
    expect(chatActAnchor({ act: "pending_note", text: "Falta cota." })).toEqual({
      readingId: null,
      proposalIds: [],
    });
  });
});

describe("frase do ato", () => {
  it("usa o valor como escrito no pacote e o nome de obra da forma", () => {
    const label = chatActLabel(
      {
        act: "reading_decision",
        reading_id: READING_ID,
        action: "confirm",
        association_proposal_id: PROPOSAL_ID,
        annotation: false,
        justification_draft: "Cota conferida.",
      },
      naming,
    );
    expect(label).toContain('"21,75"');
    expect(label).toContain("① linha vertical");
    expect(label).not.toContain(READING_ID);
    expect(label).not.toContain(PROPOSAL_ID);
  });

  it("não inventa valor para leitura que saiu do pacote", () => {
    const label = chatActLabel(
      {
        act: "trace_association",
        reading_id: OTHER_READING_ID,
        target: PROPOSAL_ID,
      },
      naming,
    );
    expect(label).toContain("não está no pacote");
    expect(label).not.toContain("21,75");
  });

  it("descreve par mantido separado, nota e pendência", () => {
    expect(
      chatActLabel(
        {
          act: "keep_apart",
          first: PROPOSAL_ID,
          second: OTHER_PROPOSAL_ID,
          axis: "x",
        },
        naming,
      ),
    ).toContain("eixo horizontal");
    expect(
      chatActLabel(
        { act: "note_association", reading_id: READING_ID, target: "carimbo" },
        naming,
      ),
    ).toContain("carimbo");
    expect(
      chatActLabel({ act: "pending_note", text: "Falta a cota do vão." }, naming),
    ).toContain("Falta a cota do vão.");
  });
});

describe("rascunho de decisão vira formulário", () => {
  const decisionDraft: ChatActDraft = {
    act: "reading_decision",
    reading_id: READING_ID,
    action: "confirm",
    association_proposal_id: PROPOSAL_ID,
    annotation: false,
    justification_draft: "Cota conferida contra o recorte da evidência.",
  };

  it("preenche associação e justificativa sem carregar medida nenhuma", () => {
    const decision = draftToReviewDecision(decisionDraft, [reading()]);
    expect(decision).toEqual({
      reading_id: READING_ID,
      action: "confirm",
      justification: "Cota conferida contra o recorte da evidência.",
      association_proposal_id: PROPOSAL_ID,
      annotation: undefined,
    });
    // O valor escrito continua sendo o do pacote: o rascunho não o transporta.
    expect(decision).not.toHaveProperty("raw_text");
    expect(decision).not.toHaveProperty("value_si");
    expect(decision).not.toHaveProperty("unit");
    expect(decision).not.toHaveProperty("kind");
  });

  it("declara anotação da folha sem associação", () => {
    const decision = draftToReviewDecision(
      { ...decisionDraft, annotation: true },
      [reading()],
    );
    expect(decision?.annotation).toBe(true);
    expect(decision?.association_proposal_id).toBeUndefined();
  });

  it("rejeição não leva associação", () => {
    const decision = draftToReviewDecision(
      { ...decisionDraft, action: "reject" },
      [reading()],
    );
    expect(decision?.action).toBe("reject");
    expect(decision?.association_proposal_id).toBeUndefined();
  });

  it("recusa leitura fora do pacote", () => {
    expect(draftToReviewDecision(decisionDraft, [])).toBeNull();
  });

  it("recusa leitura já decidida: corrigir é ato declarado próprio", () => {
    expect(
      draftToReviewDecision(decisionDraft, [reading({ status: "confirmed" })]),
    ).toBeNull();
    expect(
      draftToReviewDecision(decisionDraft, [reading({ status: "rejected" })]),
    ).toBeNull();
  });

  it("ato que não é decisão de leitura não vira decisão", () => {
    expect(
      draftToReviewDecision({ act: "pending_note", text: "Falta cota." }, [
        reading(),
      ]),
    ).toBeNull();
  });
});

describe("rascunho aplicado ao aceite de traçado", () => {
  it("declara vão de um elemento e vão entre dois", () => {
    const single = applyDraftToTraceDraft(
      { act: "trace_association", reading_id: READING_ID, target: PROPOSAL_ID },
      draft(),
    );
    expect(single.applied).toBe(true);
    expect(single.draft.associations[READING_ID]).toEqual({
      kind: "single",
      proposalId: PROPOSAL_ID,
    });

    const pair = applyDraftToTraceDraft(
      {
        act: "trace_association",
        reading_id: READING_ID,
        target: [PROPOSAL_ID, OTHER_PROPOSAL_ID],
      },
      draft(),
    );
    expect(pair.draft.associations[READING_ID]).toEqual({
      kind: "pair",
      proposalIds: [PROPOSAL_ID, OTHER_PROPOSAL_ID],
    });
  });

  it("não marca forma nenhuma na seleção do lote", () => {
    const applied = applyDraftToTraceDraft(
      { act: "trace_association", reading_id: READING_ID, target: PROPOSAL_ID },
      draft(),
    );
    expect(applied.draft.proposalIds).toEqual([]);
  });

  it("acrescenta par distinto e ignora par já declarado, em qualquer ordem", () => {
    const first = applyDraftToTraceDraft(
      { act: "keep_apart", first: PROPOSAL_ID, second: OTHER_PROPOSAL_ID, axis: "y" },
      draft(),
    );
    expect(first.draft.keepApartPairs).toEqual([
      { first: PROPOSAL_ID, second: OTHER_PROPOSAL_ID, axis: "y" },
    ]);

    const repeated = applyDraftToTraceDraft(
      { act: "keep_apart", first: OTHER_PROPOSAL_ID, second: PROPOSAL_ID },
      first.draft,
    );
    expect(repeated.applied).toBe(false);
    expect(repeated.draft.keepApartPairs).toHaveLength(1);
  });

  it("par sem eixo declarado separa nos dois, como o aceite histórico", () => {
    const applied = applyDraftToTraceDraft(
      { act: "keep_apart", first: PROPOSAL_ID, second: OTHER_PROPOSAL_ID },
      draft(),
    );
    expect(applied.draft.keepApartPairs[0].axis).toBeNull();
  });

  it("amarra nota pelo alvo declarado", () => {
    const applied = applyDraftToTraceDraft(
      {
        act: "note_association",
        reading_id: READING_ID,
        target: `legenda:${PROPOSAL_ID}`,
      },
      draft(),
    );
    expect(applied.draft.noteTargets[READING_ID]).toBe(`legenda:${PROPOSAL_ID}`);
  });

  it("concatena a pendência com separador e não duplica texto idêntico", () => {
    const first = applyDraftToTraceDraft(
      { act: "pending_note", text: "Falta a cota do vão direito." },
      draft({ note: "Prancha sem escala declarada." }),
    );
    expect(first.draft.note).toBe(
      "Prancha sem escala declarada.; Falta a cota do vão direito.",
    );

    const repeated = applyDraftToTraceDraft(
      { act: "pending_note", text: "Falta a cota do vão direito." },
      first.draft,
    );
    expect(repeated.applied).toBe(false);
    expect(repeated.draft.note).toBe(first.draft.note);
  });

  it("respeita o limite da nota em vez de truncar a pendência", () => {
    const current = "a".repeat(MAX_NOTE_LENGTH - 10);
    const applied = applyDraftToTraceDraft(
      { act: "pending_note", text: "pendência que não cabe" },
      draft({ note: current }),
    );
    expect(applied.applied).toBe(false);
    expect(applied.draft.note).toBe(current);
    expect(applied.message).toContain("500");
  });

  it("rascunho de decisão não entra no aceite de traçado", () => {
    const applied = applyDraftToTraceDraft(
      {
        act: "reading_decision",
        reading_id: READING_ID,
        action: "confirm",
        annotation: false,
        justification_draft: "Cota conferida.",
      },
      draft(),
    );
    expect(applied.applied).toBe(false);
    expect(applied.draft).toEqual(draft());
  });
});
