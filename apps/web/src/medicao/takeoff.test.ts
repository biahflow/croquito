import { describe, expect, it } from "vitest";
import type { TakeoffItem } from "./api";
import { itemAnchor } from "./takeoff";

function takeoffItem(anchor?: TakeoffItem["anchor"]): TakeoffItem {
  return {
    id: "ti_af6f85a49ea0b93d",
    evidence: {
      plate_id: "plate-sintetica-v1",
      page_number: 1,
      image_sha256: "a".repeat(64),
      coordinate_space: "source_image_pixels",
      bbox: { left: 10, top: 10, right: 100, bottom: 40 },
    },
    raw_text: "1 - PISO EM CONCRETO - 18,40 m2",
    label: "PISO EM CONCRETO",
    quantity: "18.40",
    unit: "m2",
    source: "legend_extraction",
    extractor: "opencv",
    extractor_version: "1.0.0",
    note: null,
    status: "proposed",
    decision: null,
    anchor,
  };
}

describe("itemAnchor", () => {
  it("lê 'registered' e 'raw' como vieram do servidor", () => {
    expect(itemAnchor(takeoffItem("registered"))).toBe("registered");
    expect(itemAnchor(takeoffItem("raw"))).toBe("raw");
  });

  it("campo ausente trata como 'raw', nunca como localização confirmada", () => {
    expect(itemAnchor(takeoffItem(undefined))).toBe("raw");
  });
});
