import { describe, expect, it } from "vitest";
import type { OverlayState } from "./api";
import { overlayFreshness } from "./images";

function overlay(overrides: Partial<OverlayState> = {}): OverlayState {
  return {
    present: true,
    image_sha256: "b".repeat(64),
    overlay_packet_sha256: "c".repeat(64),
    stale: false,
    ...overrides,
  };
}

describe("overlayFreshness", () => {
  it("overlay do pacote corrente é declarado como atual", () => {
    const estado = overlayFreshness(overlay());

    expect(estado?.stale).toBe(false);
    expect(estado?.label).toBe("desenho do pacote atual");
  });

  /**
   * Entre a decisão e o re-render do worker o desenho é do pacote anterior (ADR-0030).
   * Isso não é erro: é estado, e ele precisa estar escrito — nunca só na borda.
   */
  it("overlay vencido é dito vencido, em palavra", () => {
    const estado = overlayFreshness(overlay({ stale: true }));

    expect(estado?.stale).toBe(true);
    expect(estado?.label).toBe("desenho do pacote anterior");
    expect(estado?.label).not.toBe("desenho do pacote atual");
    expect(estado?.explanation).toContain("comando de fila");
  });

  it("sem desenho publicado não afirma que ele está atual", () => {
    const estado = overlayFreshness(overlay({ present: false, stale: false }));

    expect(estado?.label).toBe("sem desenho publicado");
    expect(estado?.stale).toBe(true);
  });

  it("leitura ainda não feita não inventa estado", () => {
    expect(overlayFreshness(null)).toBeNull();
  });
});
