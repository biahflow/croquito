import { describe, expect, it } from "vitest";
import { plateImageUrl } from "./api";
import { plateImageSource } from "./images";

describe("plateImageSource", () => {
  it("sem OIDC a prancha continua vindo da URL direta do servidor local", () => {
    expect(plateImageSource(false)).toBe(plateImageUrl);
  });

  it("com OIDC não há src antes da busca autenticada", () => {
    expect(plateImageSource(true)).toBeNull();
  });
});
