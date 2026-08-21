import { describe, expect, it } from "vitest";

import type { ReviewReading } from "./api";
import {
  buildRectification,
  decisionMoment,
  rectificationPrefill,
  rectificationTarget,
  showsDecisionForm,
  showsDecisionRecord,
} from "./rectification";

const ANNOTATION_OPTION = "annotation:no-element";

function confirmedReading(overrides: Partial<ReviewReading> = {}): ReviewReading {
  return {
    id: "rd_1111111111111111",
    raw_text: "25,90",
    kind: "width",
    status: "confirmed",
    value_si: "25.90",
    unit: "m",
    written_decimals: 2,
    decision: {
      decision_id: "hd_aaaaaaaaaaaaaaaa",
      action: "confirm",
      reviewer_id: "eng-01",
      decided_at: "2026-08-13T14:22:00Z",
      note: "Conferido na evidência protegida.",
    },
    ...overrides,
  };
}

describe("rectificationPrefill", () => {
  it("traz os valores vigentes e a associação registrada, com justificativa vazia", () => {
    const prefill = rectificationPrefill(
      confirmedReading(),
      "vp_1111111111111111",
      ANNOTATION_OPTION,
    );

    expect(prefill).toEqual({
      associationValue: "vp_1111111111111111",
      rawText: "25,90",
      value: "25,90",
      unit: "m",
      kind: "width",
      justification: "",
    });
  });

  it("mostra a anotação da folha já selecionada quando a leitura foi decidida assim", () => {
    const prefill = rectificationPrefill(
      confirmedReading(),
      undefined,
      ANNOTATION_OPTION,
    );

    expect(prefill.associationValue).toBe(ANNOTATION_OPTION);
  });

  it("trata a anotação AUTOMÁTICA como a declarada por uma pessoa", () => {
    // ADR-0044 (D1a): a auto-anotação nasce confirmada e sem entrada em
    // `selected_associations`, que é a mesma forma do ato humano. A correção declarada
    // não tem associação a pré-preencher — ela abre na opção "anotação da folha", e o
    // que se corrige é a decisão, não um vínculo que não existe.
    const prefill = rectificationPrefill(
      confirmedReading({
        kind: "height",
        raw_text: "h=3,80",
        value_si: "3.80",
        decision: {
          decision_id: "hd_cccccccccccccccc",
          action: "confirm",
          actor: "system",
          auto_tier: "anotacao",
          reviewer_id: "system:auto-association@1.0.0",
          decided_at: "2026-08-21T12:00:00Z",
          note: "Anotação automática (corte vigente 0.7, score 1.0.0): …",
        },
      }),
      undefined,
      ANNOTATION_OPTION,
    );

    expect(prefill.associationValue).toBe(ANNOTATION_OPTION);
    expect(prefill.rawText).toBe("h=3,80");
    expect(prefill.justification).toBe("");
  });

  it("não escolhe nada por uma leitura rejeitada: ela nunca teve elemento associado", () => {
    const prefill = rectificationPrefill(
      confirmedReading({
        status: "rejected",
        decision: {
          decision_id: "hd_bbbbbbbbbbbbbbbb",
          action: "reject",
          reviewer_id: "eng-01",
          decided_at: "2026-08-13T14:22:00Z",
        },
      }),
      undefined,
      ANNOTATION_OPTION,
    );

    expect(prefill.associationValue).toBe("");
  });
});

describe("rectificationTarget", () => {
  it("é o identificador da decisão vigente", () => {
    expect(rectificationTarget(confirmedReading())).toBe("hd_aaaaaaaaaaaaaaaa");
  });

  it("é nulo na leitura ainda não decidida", () => {
    expect(
      rectificationTarget(
        confirmedReading({ status: "proposed", decision: null }),
      ),
    ).toBeNull();
  });
});

describe("o que a tela mostra em cada estado da leitura", () => {
  it("mostra o registro decidido e o botão de correção, sem reabrir o formulário", () => {
    const decided = confirmedReading();

    expect(showsDecisionRecord(decided, null)).toBe(true);
    expect(showsDecisionForm(decided, null)).toBe(false);
  });

  it("troca o registro pelo formulário quando a correção começa", () => {
    const decided = confirmedReading();

    expect(showsDecisionForm(decided, decided.id)).toBe(true);
    expect(showsDecisionRecord(decided, decided.id)).toBe(false);
  });

  it("mantém o fluxo da leitura pendente exatamente como era", () => {
    const pending = confirmedReading({ status: "proposed", decision: null });

    expect(showsDecisionForm(pending, null)).toBe(true);
    expect(showsDecisionRecord(pending, null)).toBe(false);
    expect(showsDecisionForm(confirmedReading({ status: "ambiguous" }), null)).toBe(
      true,
    );
  });
});

describe("buildRectification", () => {
  it("cita a decisão corrigida, redeclara a associação e leva a justificativa", () => {
    const command = buildRectification(confirmedReading(), {
      action: "confirm",
      justification: "  A cota mede a altura, conferida na folha.  ",
      associationValue: "vp_1111111111111111",
      annotationOption: ANNOTATION_OPTION,
      rawText: "21,75",
      written: { value_si: "21.75", written_decimals: 2 },
      unit: "m",
      kind: "height",
    });

    expect(command).toEqual({
      reading_id: "rd_1111111111111111",
      action: "confirm",
      rectifies_decision_id: "hd_aaaaaaaaaaaaaaaa",
      justification: "A cota mede a altura, conferida na folha.",
      association_proposal_id: "vp_1111111111111111",
      annotation: undefined,
      raw_text: "21,75",
      value_si: "21.75",
      written_decimals: 2,
      unit: "m",
      kind: "height",
    });
  });

  it("declara anotação da folha sem associação, e a rejeição também não leva elemento", () => {
    const annotated = buildRectification(confirmedReading(), {
      action: "confirm",
      justification: "É anotação da folha, não mede elemento.",
      associationValue: ANNOTATION_OPTION,
      annotationOption: ANNOTATION_OPTION,
      rawText: "25,90",
      written: null,
      unit: "m",
      kind: "width",
    });
    const rejected = buildRectification(confirmedReading(), {
      action: "reject",
      justification: "A cota não existe na folha.",
      associationValue: "vp_1111111111111111",
      annotationOption: ANNOTATION_OPTION,
      rawText: "25,90",
      written: null,
      unit: "m",
      kind: "width",
    });

    expect(annotated?.annotation).toBe(true);
    expect(annotated?.association_proposal_id).toBeUndefined();
    expect(rejected?.annotation).toBeUndefined();
    expect(rejected?.association_proposal_id).toBeUndefined();
    expect(rejected?.value_si).toBeUndefined();
  });

  it("não monta comando para leitura sem decisão registrada", () => {
    const command = buildRectification(
      confirmedReading({ status: "proposed", decision: null }),
      {
        action: "confirm",
        justification: "Sem alvo declarado não há correção.",
        associationValue: "vp_1111111111111111",
        annotationOption: ANNOTATION_OPTION,
        rawText: "25,90",
        written: null,
        unit: "m",
        kind: "width",
      },
    );

    expect(command).toBeNull();
  });
});

describe("decisionMoment", () => {
  it("mostra a data em UTC, igual em qualquer máquina", () => {
    expect(decisionMoment("2026-08-13T14:22:00Z")).toBe(
      "13/08/2026 às 14:22 UTC",
    );
  });

  it("devolve o texto original quando a data não é legível", () => {
    expect(decisionMoment("sem data")).toBe("sem data");
  });
});
