import { describe, expect, it } from "vitest";

import { readRoute, routeSearch, type Route } from "./route";

const JOB = "0198f0a1-2b3c-7d4e-8f90-1a2b3c4d5e6f";
const ROUND = "0198f0a1-2b3c-7d4e-8f90-aaaabbbbcccc";

describe("readRoute", () => {
  it("abre o croqui na raiz da SPA, sem parâmetro nenhum", () => {
    expect(readRoute("")).toEqual({ kind: "croqui", jobId: "" });
    expect(readRoute("?")).toEqual({ kind: "croqui", jobId: "" });
  });

  it("abre o croqui com ?job, que é o link já publicado", () => {
    expect(readRoute(`?job=${JOB}`)).toEqual({ kind: "croqui", jobId: JOB });
    // Sem o `?` na frente: `window.location.search` vem com ele, o resto do código nem sempre.
    expect(readRoute(`job=${JOB}`)).toEqual({ kind: "croqui", jobId: JOB });
  });

  it("abre a medição com ?rodada", () => {
    expect(readRoute(`?rodada=${ROUND}`)).toEqual({
      kind: "medicao",
      roundId: ROUND,
    });
  });

  it("abre a medição sem rodada quando ?rodada vem vazio, porque presença manda", () => {
    expect(readRoute("?rodada=")).toEqual({ kind: "medicao", roundId: "" });
  });

  it("dá o croqui como vencedor quando as duas jornadas vêm na mesma URL", () => {
    expect(readRoute(`?job=${JOB}&rodada=${ROUND}`)).toEqual({
      kind: "croqui",
      jobId: JOB,
    });
    // A ordem dos parâmetros não decide nada: o croqui vence dos dois lados.
    expect(readRoute(`?rodada=${ROUND}&job=${JOB}`)).toEqual({
      kind: "croqui",
      jobId: JOB,
    });
  });

  it("trata ?job vazio como job ausente e deixa a medição responder", () => {
    expect(readRoute("?job=")).toEqual({ kind: "croqui", jobId: "" });
    expect(readRoute(`?job=&rodada=${ROUND}`)).toEqual({
      kind: "medicao",
      roundId: ROUND,
    });
  });

  it("ignora parâmetro desconhecido em vez de deixá-lo escolher jornada", () => {
    expect(readRoute("?tenant=acme&debug=1")).toEqual({
      kind: "croqui",
      jobId: "",
    });
    expect(readRoute(`?job=${JOB}&debug=1`)).toEqual({
      kind: "croqui",
      jobId: JOB,
    });
  });

  it("lê o valor percent-encoded como veio escrito, sem adivinhar formato", () => {
    expect(readRoute("?job=a%20b")).toEqual({ kind: "croqui", jobId: "a b" });
  });
});

describe("routeSearch", () => {
  it("não escreve query para o croqui sem job", () => {
    expect(routeSearch({ kind: "croqui", jobId: "" })).toBe("");
  });

  it("escreve ?job para o croqui aberto", () => {
    expect(routeSearch({ kind: "croqui", jobId: JOB })).toBe(`?job=${JOB}`);
  });

  it("escreve ?rodada para a medição, inclusive sem rodada aberta", () => {
    expect(routeSearch({ kind: "medicao", roundId: ROUND })).toBe(
      `?rodada=${ROUND}`,
    );
    expect(routeSearch({ kind: "medicao", roundId: "" })).toBe("?rodada=");
  });

  it("escapa o valor em vez de injetá-lo cru na query", () => {
    expect(routeSearch({ kind: "croqui", jobId: "a b&c" })).toBe(
      "?job=a+b%26c",
    );
  });

  it("não carrega parâmetro que não seja da jornada", () => {
    const route = readRoute(`?job=${JOB}&debug=1&tenant=acme`);

    expect(routeSearch(route)).toBe(`?job=${JOB}`);
  });
});

describe("round-trip das formas canônicas", () => {
  const canonical = ["", `?job=${JOB}`, "?rodada=", `?rodada=${ROUND}`];

  for (const search of canonical) {
    it(`preserva ${search === "" ? "a raiz" : search}`, () => {
      expect(routeSearch(readRoute(search))).toBe(search);
    });
  }

  const routes: Route[] = [
    { kind: "croqui", jobId: "" },
    { kind: "croqui", jobId: JOB },
    { kind: "medicao", roundId: "" },
    { kind: "medicao", roundId: ROUND },
  ];

  for (const route of routes) {
    it(`preserva a rota ${route.kind} ${
      route.kind === "croqui" ? route.jobId : route.roundId
    }`, () => {
      expect(readRoute(routeSearch(route))).toEqual(route);
    });
  }
});
