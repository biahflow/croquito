import { describe, expect, it } from "vitest";

import { mergedSearchAfterRedirect, searchFromState } from "./auth";
import { readRoute, routeSearch } from "./route";

/**
 * O `state` do OIDC é a única coisa que atravessa o redirect do Keycloak. Desde a casca de
 * duas jornadas ele carrega a query canônica da rota, e não só o job — sem isso quem abre
 * um link de medição sem sessão volta do login no croqui, na jornada errada.
 */
describe("searchFromState", () => {
  it("devolve a query canônica que a rota gravou", () => {
    expect(searchFromState({ search: "?rodada=r-1" })).toBe("?rodada=r-1");
    expect(searchFromState({ search: "?job=j-1" })).toBe("?job=j-1");
  });

  it("aceita a forma antiga do state, porque um login pode estar em voo no deploy", () => {
    // O `state` viaja pelo Keycloak: alguém que clicou em Entrar antes desta build volta
    // depois dela. Recusar a forma antiga jogaria essa pessoa na lista de projetos.
    expect(searchFromState({ job: "j-antigo" })).toBe("?job=j-antigo");
  });

  it("escapa o valor da forma antiga em vez de concatenar texto cru", () => {
    expect(searchFromState({ job: "a b&c=d" })).toBe("?job=a%20b%26c%3Dd");
  });

  it("trata qualquer outra forma como ausência, sem confiar no que voltou", () => {
    expect(searchFromState(null)).toBeNull();
    expect(searchFromState(undefined)).toBeNull();
    expect(searchFromState("?job=j-1")).toBeNull();
    expect(searchFromState({})).toBeNull();
    expect(searchFromState({ search: "" })).toBeNull();
    expect(searchFromState({ job: "" })).toBeNull();
    expect(searchFromState({ job: 7 })).toBeNull();
  });

  it("prefere a forma nova quando as duas vêm juntas", () => {
    expect(searchFromState({ search: "?rodada=r-1", job: "j-1" })).toBe("?rodada=r-1");
  });
});

describe("mergedSearchAfterRedirect", () => {
  it("apaga os parâmetros do retorno do OIDC", () => {
    const merged = mergedSearchAfterRedirect(
      "?code=abc&state=xyz&session_state=s&iss=https%3A%2F%2Fkc",
      null,
    );

    expect(merged).toBe("");
  });

  it("repõe a jornada que o redirect apagou", () => {
    expect(mergedSearchAfterRedirect("?code=abc&state=xyz", "?rodada=r-1")).toBe("?rodada=r-1");
    expect(mergedSearchAfterRedirect("?code=abc&state=xyz", "?job=j-1")).toBe("?job=j-1");
  });

  it("não deixa o state sequestrar a jornada que a URL já declara", () => {
    // Chegar com `?job` e trazer `?rodada` no state significa que a URL corrente é mais
    // nova; o state repõe o que falta, nunca troca o que está lá.
    const merged = mergedSearchAfterRedirect("?job=j-1&code=abc&state=xyz", "?rodada=r-1");

    expect(readRoute(merged).kind).toBe("croqui");
    expect(merged).toContain("job=j-1");
    expect(merged).toContain("rodada=r-1");
  });

  it("preserva parâmetro que não é do OIDC nem da jornada", () => {
    expect(mergedSearchAfterRedirect("?utm=x&code=abc&state=xyz", null)).toBe("?utm=x");
  });

  it("o que volta do redirect é lido de volta como a jornada que foi pedida", () => {
    for (const search of ["?job=j-1", "?rodada=r-1", "?rodada="]) {
      const merged = mergedSearchAfterRedirect("?code=abc&state=xyz", search);

      expect(routeSearch(readRoute(merged))).toBe(search);
    }
  });
});
