import { describe, expect, it } from "vitest";

import { justificationIssue } from "./justification";

const TOO_SHORT = "Escreva a justificativa nas suas palavras (mínimo de 3 caracteres).";
const TOO_LONG = "A justificativa não pode passar de 500 caracteres.";

describe("justificationIssue", () => {
  it("rejects an empty string", () => {
    expect(justificationIssue("")).toBe(TOO_SHORT);
  });

  it("rejects two characters", () => {
    expect(justificationIssue("ab")).toBe(TOO_SHORT);
  });

  it("trims before counting, so padded short text is still rejected", () => {
    expect(justificationIssue("  ab  ")).toBe(TOO_SHORT);
  });

  it("accepts exactly three trimmed characters", () => {
    expect(justificationIssue("abc")).toBeNull();
    expect(justificationIssue("  abc  ")).toBeNull();
  });

  it("accepts exactly five hundred characters", () => {
    expect(justificationIssue("a".repeat(500))).toBeNull();
  });

  it("rejects five hundred and one characters", () => {
    expect(justificationIssue("a".repeat(501))).toBe(TOO_LONG);
  });
});
