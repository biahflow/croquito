import { describe, expect, it } from "vitest";

import {
  REVIEW_DECISION_BATCH_MAX,
  reviewDecisionBatchIssue,
  type ReviewReading,
} from "./api";
import { buildAnnotationBatch, suggestedAnnotationIds } from "./readingBatch";

function reading(overrides: Partial<ReviewReading> = {}): ReviewReading {
  return {
    id: "rd_0000000000000001",
    raw_text: "25,90",
    kind: "width",
    status: "proposed",
    ...overrides,
  };
}

/** Decisão registrada como a API a devolve; só o que a regra do lote olha importa. */
function decision(): NonNullable<ReviewReading["decision"]> {
  return {
    decision_id: "dc_0000000000000001",
    action: "confirm",
    reviewer_id: "revisor-de-teste",
    decided_at: "2026-08-20T12:00:00Z",
  };
}

describe("suggestedAnnotationIds", () => {
  it("elege a sugerida ainda não decidida, na ordem da lista", () => {
    const readings = [
      reading({ id: "rd_1", raw_text: "muro Vizinho h=3,80" }),
      reading({ id: "rd_2", annotation_suggested: true }),
    ];

    expect(suggestedAnnotationIds(readings)).toEqual(["rd_1", "rd_2"]);
  });

  /** Decisão gravada se corrige pela retificação, nunca por um segundo lote. */
  it("deixa de fora a sugerida que já tem decisão registrada", () => {
    const readings = [
      reading({ id: "rd_1", annotation_suggested: true, decision: decision() }),
      reading({ id: "rd_2", annotation_suggested: true }),
    ];

    expect(suggestedAnnotationIds(readings)).toEqual(["rd_2"]);
  });

  /** Cota de chão não entra: ela declara associação e eixo, uma a uma. */
  it("deixa de fora a leitura sem sugestão de anotação", () => {
    const readings = [reading({ id: "rd_1" }), reading({ id: "rd_2", raw_text: "H = 2,50" })];

    expect(suggestedAnnotationIds(readings)).toEqual(["rd_2"]);
  });
});

describe("buildAnnotationBatch", () => {
  it("replica a justificativa do revisor, aparada, em cada decisão individual", () => {
    const readings = [
      reading({ id: "rd_1", raw_text: "muro Vizinho h=3,80" }),
      reading({ id: "rd_2", annotation_suggested: true }),
    ];

    const batch = buildAnnotationBatch(
      readings,
      new Set(["rd_1", "rd_2"]),
      "  conferi as duas na folha: são recados  ",
    );

    expect(batch).toEqual([
      {
        reading_id: "rd_1",
        action: "confirm",
        annotation: true,
        justification: "conferi as duas na folha: são recados",
      },
      {
        reading_id: "rd_2",
        action: "confirm",
        annotation: true,
        justification: "conferi as duas na folha: são recados",
      },
    ]);
  });

  /** Anotação da folha não leva associação: o par é recusado pela API. */
  it("não manda associação de elemento em nenhum item", () => {
    const batch = buildAnnotationBatch(
      [reading({ id: "rd_1", annotation_suggested: true })],
      new Set(["rd_1"]),
      "recado da folha",
    );

    expect(batch[0]).not.toHaveProperty("association_proposal_id");
  });

  /**
   * Marcação envenenada — id de leitura já decidida, id sem sugestão, id que nem está
   * nesta revisão — não vira palavra humana gravada sobre uma cota.
   */
  it("filtra id decidido, id sem sugestão e id ausente da revisão", () => {
    const readings = [
      reading({ id: "rd_1", annotation_suggested: true, decision: decision() }),
      reading({ id: "rd_2" }),
      reading({ id: "rd_3", annotation_suggested: true }),
    ];

    const batch = buildAnnotationBatch(
      readings,
      new Set(["rd_1", "rd_2", "rd_3", "rd_fora_da_revisao"]),
      "só o que a folha declara como recado",
    );

    expect(batch.map((item) => item.reading_id)).toEqual(["rd_3"]);
  });

  /** Quem barra o envio vazio é a tela e o guard do transporte, não o montador. */
  it("devolve lista vazia quando nada está selecionado", () => {
    expect(
      buildAnnotationBatch(
        [reading({ id: "rd_1", annotation_suggested: true })],
        new Set(),
        "justificativa qualquer",
      ),
    ).toEqual([]);
  });
});

describe("reviewDecisionBatchIssue", () => {
  it("recusa envio vazio antes da rede", () => {
    expect(reviewDecisionBatchIssue(0)).toContain("pelo menos uma");
  });

  it("aceita de uma decisão até o teto do contrato do servidor", () => {
    expect(reviewDecisionBatchIssue(1)).toBeNull();
    expect(reviewDecisionBatchIssue(REVIEW_DECISION_BATCH_MAX)).toBeNull();
  });

  it("recusa acima do teto explicando o limite, em vez de colher um 422", () => {
    const issue = reviewDecisionBatchIssue(REVIEW_DECISION_BATCH_MAX + 1);

    expect(issue).toContain(String(REVIEW_DECISION_BATCH_MAX));
    expect(issue).toContain("lotes menores");
  });
});
