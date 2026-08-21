import { describe, expect, it } from "vitest";

import type { Survey } from "../domain/types";
import type { SurveyOperation } from "../outbox/types";
import { isSurveyPacketShape, MissingMediaError, toSurveyPacket, type MediaIndex } from "./contract";

const NOW = "2026-08-21T12:00:00.000Z";
const LATER = "2026-08-21T12:05:00.000Z";

const PHOTO_SHA256 = "a".repeat(64);
const ACCESS_PHOTO_SHA256 = "b".repeat(64);

function representativeSurvey(): Survey {
  return {
    id: "survey-1",
    name: "Praça Guaxindiba",
    order_id: "order-1",
    context: {
      instrument: "Trena laser",
      reference_note: "Poste de luz na esquina da praça",
      gps: { lat: -22.9, lng: -43.2, accuracy_m: 5 },
      access_media_ref: "media-access",
      arrived_at: NOW,
    },
    points: [
      { id: "p1", x_mm: 0, y_mm: 0, created_at: NOW },
      { id: "p2", x_mm: 5000, y_mm: -3200, created_at: NOW },
    ],
    segments: [{ id: "s1", from_point_id: "p1", to_point_id: "p2", created_at: NOW }],
    measurements: [
      {
        id: "m1",
        value_mm: 5852,
        kind: "length",
        from_point_id: "p1",
        to_point_id: "p2",
        instrument: "trena",
        status: "confirmed",
        created_at: NOW,
      },
      {
        id: "m2",
        value_mm: 1200,
        kind: "width",
        instrument: "estimado",
        status: "draft",
        justification: "medida provisória, confirmar com trena laser",
        created_at: LATER,
      },
    ],
    photo_anchors: [
      { id: "ph1", point_id: "p1", local_media_ref: "media-photo", created_at: NOW },
    ],
    elements: [{ id: "el1", label: "Banco", point_ids: ["p1"], created_at: NOW }],
    observations: [
      { id: "obs1", text: "Poste com fiação exposta", point_id: "p1", created_at: NOW },
    ],
    status: "concluded",
    waivers: [
      {
        id: "w1",
        finding_code: "OPEN_SEGMENT",
        ref_key: "s1",
        justification: "perímetro parcial aceito pelo cliente",
        created_at: LATER,
      },
    ],
    created_at: NOW,
    updated_at: LATER,
  };
}

function representativeOperations(): SurveyOperation[] {
  return [
    {
      operation_id: "op1",
      device_id: "device-1",
      survey_id: "survey-1",
      seq: 1,
      type: "point.add",
      payload: { point: { id: "p1", x_mm: 0, y_mm: 0 } },
      status: "acked",
      created_at: NOW,
    },
    {
      operation_id: "op2",
      device_id: "device-1",
      survey_id: "survey-1",
      seq: 2,
      type: "survey.conclude",
      payload: {},
      status: "pending",
      created_at: LATER,
    },
  ];
}

function representativeMediaIndex(): MediaIndex {
  return new Map([
    ["media-photo", { sha256: PHOTO_SHA256, mime_type: "image/jpeg", byte_size: 204800 }],
    ["media-access", { sha256: ACCESS_PHOTO_SHA256, mime_type: "image/jpeg", byte_size: 102400 }],
  ]);
}

describe("toSurveyPacket", () => {
  it("produz um pacote com a forma gerada e preserva mm/sha256 em round-trip", () => {
    const survey = representativeSurvey();
    const operations = representativeOperations();
    const mediaIndex = representativeMediaIndex();

    const packet = toSurveyPacket(survey, operations, mediaIndex);

    expect(isSurveyPacketShape(packet)).toBe(true);

    expect(packet.survey_id).toBe("survey-1");
    expect(packet.device_id).toBe("device-1");
    expect(packet.status).toBe("concluded");

    // mm inteiros preservados, inclusive coordenada negativa.
    expect(packet.points).toEqual([
      { id: "p1", x_mm: 0, y_mm: 0, created_at: NOW },
      { id: "p2", x_mm: 5000, y_mm: -3200, created_at: NOW },
    ]);
    expect(packet.measurements?.[0]?.value_mm).toBe(5852);
    expect(packet.measurements?.[1]?.status).toBe("draft");
    expect(packet.measurements?.[1]?.justification).toBe(
      "medida provisória, confirmar com trena laser",
    );

    // sha256 resolvido a partir do índice de mídia, nunca a referência local.
    expect(packet.media_anchors).toEqual([
      {
        id: "ph1",
        media_ref: { sha256: PHOTO_SHA256, mime_type: "image/jpeg", byte_size: 204800 },
        point_id: "p1",
        element_id: undefined,
        note_id: undefined,
        created_at: NOW,
      },
    ]);
    expect(packet.arrival_context?.access_media_ref).toEqual({
      sha256: ACCESS_PHOTO_SHA256,
      mime_type: "image/jpeg",
      byte_size: 102400,
    });
    expect(packet.arrival_context?.gps).toEqual({ lat: -22.9, lng: -43.2, accuracy_m: 5 });

    // observação sem áudio: campo preparado, sempre undefined nesta fatia.
    expect(packet.observations?.[0]?.audio_media_ref).toBeUndefined();

    // waiver de conclusão preservado.
    expect(packet.waivers).toEqual([
      {
        id: "w1",
        finding_code: "OPEN_SEGMENT",
        ref_key: "s1",
        justification: "perímetro parcial aceito pelo cliente",
        created_at: LATER,
      },
    ]);

    // histórico do outbox completo, sem o campo `status` local.
    expect(packet.operations).toEqual([
      {
        operation_id: "op1",
        device_id: "device-1",
        survey_id: "survey-1",
        seq: 1,
        type: "point.add",
        payload: { point: { id: "p1", x_mm: 0, y_mm: 0 } },
        created_at: NOW,
      },
      {
        operation_id: "op2",
        device_id: "device-1",
        survey_id: "survey-1",
        seq: 2,
        type: "survey.conclude",
        payload: {},
        created_at: LATER,
      },
    ]);
    expect((packet.operations as { status?: unknown }[])[0]?.status).toBeUndefined();
  });

  it("lê status/waivers retrocompatíveis quando o survey é legado (pré-T5)", () => {
    const survey = representativeSurvey();
    delete survey.status;
    delete survey.waivers;

    const packet = toSurveyPacket(survey, representativeOperations(), representativeMediaIndex());

    expect(packet.status).toBe("collecting");
    expect(packet.waivers).toEqual([]);
  });

  it("lança MissingMediaError quando a foto ancorada não está no índice de mídia", () => {
    const survey = representativeSurvey();

    expect(() => toSurveyPacket(survey, representativeOperations(), new Map())).toThrow(
      MissingMediaError,
    );
  });

  it("lança quando não há nenhuma operação para determinar device_id", () => {
    const survey = representativeSurvey();

    expect(() => toSurveyPacket(survey, [], representativeMediaIndex())).toThrow();
  });
});

describe("isSurveyPacketShape", () => {
  it("rejeita objeto sem os campos obrigatórios", () => {
    expect(isSurveyPacketShape({})).toBe(false);
    expect(isSurveyPacketShape(null)).toBe(false);
    expect(isSurveyPacketShape("not an object")).toBe(false);
  });

  it("rejeita status fora do enum", () => {
    const packet = toSurveyPacket(
      representativeSurvey(),
      representativeOperations(),
      representativeMediaIndex(),
    );

    expect(isSurveyPacketShape({ ...packet, status: "invalid" })).toBe(false);
  });

  it("aceita o próprio pacote produzido por toSurveyPacket", () => {
    const packet = toSurveyPacket(
      representativeSurvey(),
      representativeOperations(),
      representativeMediaIndex(),
    );

    expect(isSurveyPacketShape(packet)).toBe(true);
  });
});
