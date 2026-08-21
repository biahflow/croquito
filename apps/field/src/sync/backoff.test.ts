import { describe, expect, it } from "vitest";

import { BASE_DELAY_MS, JITTER_RATIO, MAX_DELAY_MS, backoffDelayMs } from "./backoff";

describe("backoffDelayMs", () => {
  it("cresce exponencialmente até o teto", () => {
    const semJitter = () => 0.5;
    expect(backoffDelayMs(1, semJitter)).toBe(BASE_DELAY_MS);
    expect(backoffDelayMs(2, semJitter)).toBe(BASE_DELAY_MS * 2);
    expect(backoffDelayMs(3, semJitter)).toBe(BASE_DELAY_MS * 4);
    expect(backoffDelayMs(20, semJitter)).toBe(MAX_DELAY_MS);
  });

  it("o jitter dispersa a espera dentro da fração declarada", () => {
    const menor = backoffDelayMs(2, () => 0);
    const maior = backoffDelayMs(2, () => 1);
    expect(menor).toBe(Math.round(BASE_DELAY_MS * 2 * (1 - JITTER_RATIO)));
    expect(maior).toBe(Math.round(BASE_DELAY_MS * 2 * (1 + JITTER_RATIO)));
  });

  it("nunca devolve espera negativa", () => {
    expect(backoffDelayMs(0, () => 0)).toBeGreaterThanOrEqual(0);
  });
});
