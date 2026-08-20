import { describe, expect, it } from "vitest";

import { readRoute, routeSearch, type Route } from "./route";

const JOB = "0198f0a1-2b3c-7d4e-8f90-1a2b3c4d5e6f";
const ROUND = "0198f0a1-2b3c-7d4e-8f90-aaaabbbbcccc";
const ESTIMATE = "0198f0a1-2b3c-7d4e-8f90-ddddeeeeffff";

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

  it("abre o orçamento com ?orcamento=<id>", () => {
    expect(readRoute(`?orcamento=${ESTIMATE}`)).toEqual({
      kind: "orcamento",
      roundId: ESTIMATE,
    });
    expect(readRoute(`orcamento=${ESTIMATE}`)).toEqual({
      kind: "orcamento",
      roundId: ESTIMATE,
    });
  });

  /**
   * `?orcamento=` vazio é "jornada do orçamento, nenhum orçamento aberto". Ele vira
   * `null` e não `""`: a ausência é um estado da jornada (a tela de abertura), e o tipo
   * a declara em vez de deixar cada leitor interpretar uma string vazia.
   */
  it("abre o orçamento sem orçamento nenhum quando ?orcamento vem vazio", () => {
    expect(readRoute("?orcamento=")).toEqual({ kind: "orcamento", roundId: null });
  });

  it("abre a plataforma com ?plataforma, também por presença", () => {
    expect(readRoute("?plataforma=")).toEqual({ kind: "plataforma" });
    // O valor é ignorado: não há recurso aberto para citar na query.
    expect(readRoute("?plataforma=1")).toEqual({ kind: "plataforma" });
    expect(readRoute("plataforma=")).toEqual({ kind: "plataforma" });
  });

  it("respeita a precedência job > rodada > orcamento > plataforma", () => {
    expect(readRoute(`?job=${JOB}&plataforma=`)).toEqual({
      kind: "croqui",
      jobId: JOB,
    });
    expect(readRoute(`?rodada=${ROUND}&plataforma=`)).toEqual({
      kind: "medicao",
      roundId: ROUND,
    });
    // O link do croqui e o da rodada já circulam: nem um `?orcamento=` colado depois
    // deles sequestra o trabalho pedido.
    expect(readRoute(`?job=${JOB}&orcamento=${ESTIMATE}`)).toEqual({
      kind: "croqui",
      jobId: JOB,
    });
    expect(readRoute(`?rodada=${ROUND}&orcamento=${ESTIMATE}`)).toEqual({
      kind: "medicao",
      roundId: ROUND,
    });
    // O orçamento ganha da plataforma, que é a única cujo endereço se digita.
    expect(readRoute(`?plataforma=&orcamento=${ESTIMATE}`)).toEqual({
      kind: "orcamento",
      roundId: ESTIMATE,
    });
    // A ordem de escrita não decide nada; a precedência é a mesma dos dois lados.
    expect(readRoute(`?plataforma=&rodada=${ROUND}`)).toEqual({
      kind: "medicao",
      roundId: ROUND,
    });
    expect(
      readRoute(`?plataforma=&orcamento=${ESTIMATE}&job=${JOB}&rodada=${ROUND}`),
    ).toEqual({ kind: "croqui", jobId: JOB });
  });

  /** `?rodada=` vazio continua sendo jornada declarada, e ganha do orçamento. */
  it("rodada vazia ainda vence o orçamento, porque presença manda dos dois lados", () => {
    expect(readRoute(`?rodada=&orcamento=${ESTIMATE}`)).toEqual({
      kind: "medicao",
      roundId: "",
    });
  });

  it("trata ?job vazio como job ausente e deixa a plataforma responder", () => {
    expect(readRoute("?job=&plataforma=")).toEqual({ kind: "plataforma" });
  });

  it("trata ?job vazio como job ausente e deixa o orçamento responder", () => {
    expect(readRoute(`?job=&orcamento=${ESTIMATE}`)).toEqual({
      kind: "orcamento",
      roundId: ESTIMATE,
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

  it("escreve ?orcamento para o orçamento, inclusive sem orçamento aberto", () => {
    expect(routeSearch({ kind: "orcamento", roundId: ESTIMATE })).toBe(
      `?orcamento=${ESTIMATE}`,
    );
    expect(routeSearch({ kind: "orcamento", roundId: null })).toBe("?orcamento=");
  });

  it("escreve ?plataforma= para a plataforma, sem valor nenhum", () => {
    expect(routeSearch({ kind: "plataforma" })).toBe("?plataforma=");
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
  const canonical = [
    "",
    `?job=${JOB}`,
    "?rodada=",
    `?rodada=${ROUND}`,
    "?orcamento=",
    `?orcamento=${ESTIMATE}`,
    "?plataforma=",
  ];

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
    { kind: "orcamento", roundId: null },
    { kind: "orcamento", roundId: ESTIMATE },
    { kind: "plataforma" },
  ];

  function recurso(route: Route): string {
    if (route.kind === "croqui") {
      return route.jobId;
    }
    if (route.kind === "medicao") {
      return route.roundId;
    }
    if (route.kind === "orcamento") {
      return route.roundId ?? "sem orçamento aberto";
    }
    return "";
  }

  for (const route of routes) {
    it(`preserva a rota ${route.kind} ${recurso(route)}`, () => {
      expect(readRoute(routeSearch(route))).toEqual(route);
    });
  }
});
