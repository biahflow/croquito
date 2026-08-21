import { describe, expect, it } from "vitest";

import type { Survey } from "../domain/types";
import { ORDERS } from "./fixture";
import { deriveOrderState, requiredItemsForOrder, surveyIdForOrder } from "./state";

const NOW = "2026-08-21T12:00:00.000Z";

function surveyFor(orderId: string): Survey {
  return {
    id: surveyIdForOrder(orderId),
    name: "Praça de teste",
    order_id: orderId,
    points: [],
    segments: [],
    measurements: [],
    photo_anchors: [],
    elements: [],
    observations: [],
    created_at: NOW,
    updated_at: NOW,
  };
}

describe("surveyIdForOrder", () => {
  it("deriva o id do survey a partir do id da ordem", () => {
    expect(surveyIdForOrder("order-guaxindiba")).toBe("survey-order-guaxindiba");
  });
});

describe("deriveOrderState", () => {
  it("é not_downloaded quando não existe survey local para a ordem", () => {
    expect(deriveOrderState(undefined)).toBe("not_downloaded");
  });

  it("é downloaded quando existe survey local para a ordem", () => {
    expect(deriveOrderState(surveyFor("order-guaxindiba"))).toBe("downloaded");
  });

  it("é downloaded (não concluded) quando o survey não tem `status` — retrocompatibilidade", () => {
    const legacySurvey = surveyFor("order-guaxindiba");
    expect(legacySurvey.status).toBeUndefined();

    expect(deriveOrderState(legacySurvey)).toBe("downloaded");
  });

  it("é concluded quando o survey local está com status concluded (T5)", () => {
    expect(deriveOrderState({ ...surveyFor("order-guaxindiba"), status: "concluded" })).toBe(
      "concluded",
    );
  });
});

describe("requiredItemsForOrder", () => {
  it("mapeia o checklist da ordem com foto-acesso pendente (sem survey) e o resto satisfeito (T4 §5)", () => {
    for (const order of ORDERS) {
      const items = requiredItemsForOrder(order);

      expect(items).toHaveLength(order.checklist.filter((item) => item.required).length);
      const fotoAcesso = items.find((item) => item.id === "foto-acesso");
      expect(fotoAcesso).toMatchObject({ satisfied: false });
      for (const item of items) {
        if (item.id !== "foto-acesso") {
          expect(item.satisfied).toBe(true);
        }
      }
    }
  });

  it("foto-acesso pendente quando o survey existe mas ainda não tem access_media_ref (T6)", () => {
    const order = ORDERS[0]!;
    const survey = surveyFor(order.id);

    const items = requiredItemsForOrder(order, survey);

    expect(items.find((item) => item.id === "foto-acesso")).toMatchObject({ satisfied: false });
  });

  it("foto-acesso satisfeito quando o survey tem access_media_ref gravado (T6)", () => {
    const order = ORDERS[0]!;
    const survey: Survey = {
      ...surveyFor(order.id),
      context: {
        instrument: "Trena laser",
        reference_note: "Canto do muro",
        gps: "unavailable",
        access_media_ref: "media-1",
        arrived_at: NOW,
      },
    };

    const items = requiredItemsForOrder(order, survey);

    expect(items.find((item) => item.id === "foto-acesso")).toMatchObject({ satisfied: true });
  });
});
