import { describe, expect, it } from "vitest";

import type { VisionProposal } from "./api";
import {
  MINIMO_DE_VERTICES,
  correcaoIssue,
  formaCorrigivel,
  iniciarCorrecao,
  inserirVertice,
  moverVertice,
  propostasSuperadas,
  removerDerivacao,
  removerVertice,
  unirFragmento,
  verticesDaProposta,
} from "./shapeCorrection";

/**
 * O caso real da F-018: o muro do Guaxindiba V3 com recuo 4,80 → 3,30 chegou como duas
 * `line` retas, com um vão entre elas, no lugar de uma forma com o degrau.
 */
const FRAGMENTO_A: VisionProposal = {
  id: "vp_1111111111111111",
  kind: "line",
  precision: "unresolved",
  export: false,
  algorithm: "geometry-extraction@2.0.1",
  quality_score: 0.82,
  geometry: { type: "line", start: { x: 60, y: 90 }, end: { x: 270, y: 90 } },
};

const FRAGMENTO_B: VisionProposal = {
  id: "vp_2222222222222222",
  kind: "line",
  precision: "unresolved",
  export: false,
  algorithm: "geometry-extraction@2.0.1",
  quality_score: 0.79,
  geometry: { type: "line", start: { x: 300, y: 196 }, end: { x: 470, y: 196 } },
};

const CIRCULO: VisionProposal = {
  id: "vp_3333333333333333",
  kind: "circle",
  precision: "unresolved",
  export: false,
  geometry: { type: "circle", center: { x: 50, y: 50 }, radius: 12 },
};

describe("o que é corrigível", () => {
  it("linha e polilinha têm vértices; círculo, não", () => {
    expect(formaCorrigivel(FRAGMENTO_A)).toBe(true);
    expect(verticesDaProposta(FRAGMENTO_A)).toEqual([
      { x: 60, y: 90 },
      { x: 270, y: 90 },
    ]);
    // Corrigir um círculo seria mexer em centro e raio, que não são vértices; inventar
    // quatro pontos para ele produziria uma forma que ninguém desenhou.
    expect(formaCorrigivel(CIRCULO)).toBe(false);
    expect(iniciarCorrecao(CIRCULO)).toBeNull();
  });

  it("o rascunho nasce citando a proposta de origem", () => {
    const correcao = iniciarCorrecao(FRAGMENTO_A);

    expect(correcao?.derivedFrom).toEqual(["vp_1111111111111111"]);
    expect(correcao?.vertices).toHaveLength(2);
    expect(correcao?.justificativa).toBe("");
  });
});

describe("união de fragmentos", () => {
  it("duas linhas viram UMA forma com o recuo, e as duas origens são citadas", () => {
    const inicial = iniciarCorrecao(FRAGMENTO_A);
    if (inicial === null) {
      throw new Error("fragmento deveria ser corrigível");
    }

    const unida = unirFragmento(inicial, FRAGMENTO_B);

    expect(unida.derivedFrom).toEqual(["vp_1111111111111111", "vp_2222222222222222"]);
    expect(unida.vertices).toEqual([
      { x: 60, y: 90 },
      { x: 270, y: 90 },
      { x: 300, y: 196 },
      { x: 470, y: 196 },
    ]);
  });

  it("o fragmento entra pela ponta mais próxima, invertido quando é o fim que encosta", () => {
    const inicial = iniciarCorrecao(FRAGMENTO_A);
    if (inicial === null) {
      throw new Error("fragmento deveria ser corrigível");
    }
    // Mesmo fragmento B, declarado ao contrário pela extração.
    const invertido: VisionProposal = {
      ...FRAGMENTO_B,
      geometry: { type: "line", start: { x: 470, y: 196 }, end: { x: 300, y: 196 } },
    };

    const unida = unirFragmento(inicial, invertido);

    // Costurar pela ordem de clique produziria um zigue-zague atravessando o desenho.
    expect(unida.vertices).toEqual([
      { x: 60, y: 90 },
      { x: 270, y: 90 },
      { x: 300, y: 196 },
      { x: 470, y: 196 },
    ]);
  });

  it("unir o mesmo fragmento duas vezes não duplica origem nem vértice", () => {
    const inicial = iniciarCorrecao(FRAGMENTO_A);
    if (inicial === null) {
      throw new Error("fragmento deveria ser corrigível");
    }
    const uma = unirFragmento(inicial, FRAGMENTO_B);

    const outra = unirFragmento(uma, FRAGMENTO_B);

    expect(outra).toEqual(uma);
  });

  it("tirar da união tira a origem, e não desfaz o que a pessoa já moveu", () => {
    const inicial = iniciarCorrecao(FRAGMENTO_A);
    if (inicial === null) {
      throw new Error("fragmento deveria ser corrigível");
    }
    const unida = moverVertice(unirFragmento(inicial, FRAGMENTO_B), 2, { x: 290, y: 190 });

    const reduzida = removerDerivacao(unida, "vp_2222222222222222");

    expect(reduzida.derivedFrom).toEqual(["vp_1111111111111111"]);
    // Desfazer o movimento junto seria decidir pela pessoa o que ela quis dizer.
    expect(reduzida.vertices).toEqual(unida.vertices);
  });
});

describe("vértices", () => {
  const base = iniciarCorrecao(FRAGMENTO_A);
  if (base === null) {
    throw new Error("fragmento deveria ser corrigível");
  }

  it("mover troca só o vértice escolhido, e nunca sai da imagem", () => {
    const movida = moverVertice(base, 1, { x: 268, y: 116 });

    expect(movida.vertices).toEqual([
      { x: 60, y: 90 },
      { x: 268, y: 116 },
    ]);
    expect(moverVertice(base, 0, { x: -5, y: -5 }).vertices[0]).toEqual({ x: 0, y: 0 });
    expect(moverVertice(base, 9, { x: 1, y: 1 })).toEqual(base);
  });

  it("inserir cria o ponto no meio do segmento, sem mexer nas pontas", () => {
    const inserida = inserirVertice(base, 0);

    expect(inserida.vertices).toEqual([
      { x: 60, y: 90 },
      { x: 165, y: 90 },
      { x: 270, y: 90 },
    ]);
  });

  it("remover respeita o piso de dois: forma sem segmento não é forma", () => {
    const tres = inserirVertice(base, 0);

    expect(removerVertice(tres, 1).vertices).toHaveLength(2);
    expect(removerVertice(base, 0)).toEqual(base);
    expect(base.vertices.length).toBe(MINIMO_DE_VERTICES);
  });
});

describe("correcaoIssue", () => {
  const base = iniciarCorrecao(FRAGMENTO_A);
  if (base === null) {
    throw new Error("fragmento deveria ser corrigível");
  }
  const pronta = { ...base, justificativa: "Muro com recuo; a extração perdeu o degrau." };

  it("rascunho completo pode ser gravado", () => {
    expect(correcaoIssue(pronta)).toBeNull();
  });

  it("sem forma de origem a gravação é recusada na tela, antes da rede", () => {
    const issue = correcaoIssue({ ...pronta, derivedFrom: [] });

    expect(issue).toContain("forma observada de origem");
    expect(issue).toContain("desenho é CAD");
  });

  it("sem justificativa também: corrigir a forma é decisão de domínio", () => {
    expect(correcaoIssue({ ...pronta, justificativa: "  " })).toContain("justificativa");
  });
});

describe("propostasSuperadas", () => {
  it("superada é derivado da derivação, nunca de um campo do fragmento", () => {
    const correcao: VisionProposal = {
      id: "vp_4444444444444444",
      kind: "contour",
      precision: "unresolved",
      export: false,
      algorithm: "human-shape-correction-v1",
      derived_from: ["vp_1111111111111111", "vp_2222222222222222"],
      geometry: {
        type: "polyline",
        closed: false,
        points: [
          { x: 60, y: 90 },
          { x: 270, y: 90 },
          { x: 300, y: 196 },
        ],
      },
    };

    const superadas = propostasSuperadas([correcao]);

    expect(superadas.has("vp_1111111111111111")).toBe(true);
    expect(superadas.has("vp_2222222222222222")).toBe(true);
    expect(superadas.has("vp_4444444444444444")).toBe(false);
    // Nenhum campo do fragmento diz "fui superado": a relação está na correção.
    expect(FRAGMENTO_A).not.toHaveProperty("superseded_by");
  });

  it("sem correção nenhuma, nada é superado", () => {
    expect(propostasSuperadas([]).size).toBe(0);
  });
});
