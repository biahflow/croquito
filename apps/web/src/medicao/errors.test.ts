import { describe, expect, it } from "vitest";
import { MedicaoApiError } from "./api";
import { isAbortError, isStateMoved } from "./errors";

describe("isStateMoved", () => {
  it("só reconhece o conflito local; outro erro não vira convite a recarregar", () => {
    expect(isStateMoved(new Error("falha qualquer"))).toBe(false);
    expect(
      isStateMoved(new MedicaoApiError(404, "LOCAL_ARTIFACT_MISSING", "ausente", {})),
    ).toBe(false);
  });
});

describe("isAbortError", () => {
  it("reconhece o DOMException que fetch lança quando o AbortController cancela", () => {
    expect(isAbortError(new DOMException("aborted", "AbortError"))).toBe(true);
  });

  it("não confunde recusa do servidor ou falha qualquer com cancelamento", () => {
    expect(isAbortError(new MedicaoApiError(0, "LOCAL_SERVER_UNREACHABLE", "", {}))).toBe(
      false,
    );
    expect(isAbortError(new Error("falha qualquer"))).toBe(false);
    expect(isAbortError(new DOMException("timeout", "TimeoutError"))).toBe(false);
  });
});
