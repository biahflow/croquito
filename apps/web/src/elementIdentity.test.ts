/**
 * Derivação pura da identidade de elemento (F-047 T7a).
 *
 * O que estes testes provam é a fronteira, não o desenho: quem alimenta a medição, quem
 * não alimenta e por quê, que anotação não decide precisão de elemento, e que nenhuma
 * função aqui faz conta de quantidade.
 */
import { describe, expect, it } from "vitest";

import {
  alimentaAMedicao,
  alternarEntidade,
  avisoDeCamadasMisturadas,
  camadasDaSelecao,
  carimboDoAto,
  cenaTemIdentidade,
  descricaoDaEntidade,
  ehAnotacao,
  elementosDeclarados,
  entidadesSemIdentidade,
  MAXIMO_DE_ENTIDADES,
  MAXIMO_DO_ROTULO,
  mensagemDoErroDeIdentidade,
  motivoDeNaoAlimentar,
  precisaoMaisFraca,
  problemaDaDeclaracao,
  problemaDaRecusa,
  problemaDoRotulo,
  sinalDaProposta,
} from "./elementIdentity";
import type { EntidadeDaCena } from "./scenePreview";

function entidade(overrides: Partial<EntidadeDaCena> = {}): EntidadeDaCena {
  return {
    id: "019538a1-0000-7000-8000-00000000ffff",
    kind: "polyline",
    layer: "QUADRA",
    precision: "derived",
    geometry: {
      type: "polyline",
      closed: true,
      points: [
        { x: 0, y: 0 },
        { x: 10, y: 0 },
        { x: 10, y: 4 },
        { x: 0, y: 4 },
      ],
    },
    ...overrides,
  } as EntidadeDaCena;
}

describe("a fronteira da precisão", () => {
  it("só exact e derived alimentam a medição", () => {
    expect(alimentaAMedicao("exact")).toBe(true);
    expect(alimentaAMedicao("derived")).toBe(true);
    expect(alimentaAMedicao("approximate")).toBe(false);
    expect(alimentaAMedicao("unresolved")).toBe(false);
    expect(alimentaAMedicao(null)).toBe(false);
  });

  it("aproximada tem motivo escrito, e o motivo cita o dinheiro", () => {
    const motivo = motivoDeNaoAlimentar("approximate");
    expect(motivo).toContain("aproximada");
    expect(motivo).toContain("R$");
    expect(motivo).toContain("nem sob aceite explícito");
  });

  it("não resolvida tem motivo próprio, e ele cita o export", () => {
    expect(motivoDeNaoAlimentar("unresolved")).toContain("export");
  });

  it("precisão que alimenta não produz motivo", () => {
    expect(motivoDeNaoAlimentar("exact")).toBeNull();
    expect(motivoDeNaoAlimentar("derived")).toBeNull();
  });

  it("a precisão do elemento é a MAIS FRACA das entidades — falha fechado", () => {
    expect(precisaoMaisFraca(["exact", "approximate"])).toBe("approximate");
    expect(precisaoMaisFraca(["derived", "exact"])).toBe("derived");
    expect(precisaoMaisFraca(["unresolved", "approximate"])).toBe("unresolved");
    expect(precisaoMaisFraca([])).toBeNull();
  });
});

describe("elementosDeclarados", () => {
  it("agrupa por element_ref, na ordem em que os refs foram cunhados", () => {
    const elementos = elementosDeclarados([
      entidade({ id: "b", element_ref: "EL-002", layer: "MURO", precision: "exact" }),
      entidade({ id: "a", element_ref: "EL-001" }),
      entidade({ id: "c", element_ref: "EL-001" }),
    ]);
    expect(elementos.map((item) => item.elementRef)).toEqual(["EL-001", "EL-002"]);
    expect(elementos[0]?.entityIds).toEqual(["a", "c"]);
    expect(elementos[0]?.camada).toBe("QUADRA");
  });

  it("marca o elemento derivado como alimenta, sem motivo", () => {
    const [elemento] = elementosDeclarados([entidade({ element_ref: "EL-001" })]);
    expect(elemento?.alimenta).toBe(true);
    expect(elemento?.precisaoNome).toBe("derivada");
    expect(elemento?.motivo).toBeNull();
  });

  it("marca o elemento aproximado como NÃO alimenta, com o motivo escrito", () => {
    const [elemento] = elementosDeclarados([
      entidade({ element_ref: "EL-005", precision: "approximate", layer: "APROXIMADO" }),
    ]);
    expect(elemento?.alimenta).toBe(false);
    expect(elemento?.precisaoNome).toBe("aproximada");
    expect(elemento?.motivo).toContain("R$");
  });

  it("uma entidade aproximada rebaixa o elemento inteiro", () => {
    const [elemento] = elementosDeclarados([
      entidade({ id: "a", element_ref: "EL-003", precision: "exact" }),
      entidade({ id: "b", element_ref: "EL-003", precision: "approximate" }),
    ]);
    expect(elemento?.precisao).toBe("approximate");
    expect(elemento?.alimenta).toBe(false);
  });

  it("anotação não decide a precisão do elemento, e é contada por escrito", () => {
    // O rótulo TEXT chega `unresolved`; sem o recorte de anotação ele reprovaria um
    // elemento que o servidor e o `quantitativos.csv` consideram bom.
    const [elemento] = elementosDeclarados([
      entidade({ id: "a", element_ref: "EL-001", precision: "derived" }),
      entidade({
        id: "b",
        element_ref: "EL-001",
        kind: "text",
        precision: "unresolved",
      }),
    ]);
    expect(elemento?.precisao).toBe("derived");
    expect(elemento?.alimenta).toBe(true);
    expect(elemento?.anotacoes).toBe(1);
  });

  it("elemento só de anotação não alimenta, e diz que anotação não é quantidade", () => {
    const [elemento] = elementosDeclarados([
      entidade({ element_ref: "EL-009", kind: "text", precision: "unresolved" }),
    ]);
    expect(elemento?.precisao).toBeNull();
    expect(elemento?.alimenta).toBe(false);
    expect(elemento?.motivo).toContain("anotação");
    expect(elemento?.precisaoNome).toBe("sem geometria física");
  });

  it("o recorte de anotação é o mesmo do backend: text, dimension e diameter_dimension", () => {
    expect(ehAnotacao(entidade({ kind: "text" }))).toBe(true);
    expect(ehAnotacao(entidade({ kind: "dimension" }))).toBe(true);
    expect(ehAnotacao(entidade({ kind: "diameter_dimension" }))).toBe(true);
    expect(ehAnotacao(entidade({ kind: "polyline" }))).toBe(false);
    expect(ehAnotacao(entidade({ kind: "circle" }))).toBe(false);
  });
});

describe("o controle: cena sem identidade nenhuma", () => {
  it("cenaTemIdentidade é falso quando nenhuma entidade tem element_ref", () => {
    expect(cenaTemIdentidade([entidade({ id: "a" }), entidade({ id: "b" })])).toBe(false);
  });

  it("cenaTemIdentidade é verdadeiro assim que uma entidade tem element_ref", () => {
    expect(
      cenaTemIdentidade([entidade({ id: "a" }), entidade({ id: "b", element_ref: "EL-001" })]),
    ).toBe(true);
  });

  it("sem identidade declarada não existe elemento nenhum a listar", () => {
    expect(elementosDeclarados([entidade({ id: "a" }), entidade({ id: "b" })])).toEqual([]);
  });

  it("entidade com element_ref nulo continua sem identidade", () => {
    const semIdentidade = entidadesSemIdentidade([
      entidade({ id: "a", element_ref: null }),
      entidade({ id: "b", element_ref: "EL-001" }),
    ]);
    expect(semIdentidade.map((item) => item.id)).toEqual(["a"]);
  });
});

describe("a seleção manual", () => {
  it("alterna entidade preservando a ordem em que foi escolhida", () => {
    expect(alternarEntidade([], "a")).toEqual(["a"]);
    expect(alternarEntidade(["a"], "b")).toEqual(["a", "b"]);
    expect(alternarEntidade(["a", "b"], "a")).toEqual(["b"]);
  });

  it("exige ao menos uma entidade, e diz que quem declara é a pessoa", () => {
    expect(problemaDaDeclaracao([], "motivo bom")).toContain("ao menos uma entidade");
    expect(problemaDaDeclaracao([], "motivo bom")).toContain("proximidade");
  });

  it("exige justificativa com o mínimo que o servidor aceita", () => {
    expect(problemaDaDeclaracao(["a"], "ab")).toContain("justificativa");
    expect(problemaDaDeclaracao(["a"], "abc")).toBeNull();
  });

  it("recusa grupo acima do teto que o servidor aceita", () => {
    const grande = Array.from({ length: MAXIMO_DE_ENTIDADES + 1 }, (_v, i) => `e${i}`);
    expect(problemaDaDeclaracao(grande, "motivo bom")).toContain(
      String(MAXIMO_DE_ENTIDADES),
    );
  });

  it("mistura de camadas é AVISO, nunca bloqueio — quem recusa é o servidor", () => {
    const entities = [
      entidade({ id: "a", layer: "QUADRA" }),
      entidade({ id: "b", layer: "MURO" }),
    ];
    expect(camadasDaSelecao(entities, ["a", "b"])).toEqual(["MURO", "QUADRA"]);
    expect(avisoDeCamadasMisturadas(["MURO", "QUADRA"])).toContain("MURO");
    expect(problemaDaDeclaracao(["a", "b"], "motivo bom")).toBeNull();
  });

  it("uma camada só não gera aviso", () => {
    expect(avisoDeCamadasMisturadas(["QUADRA"])).toBeNull();
  });

  it("a recusa de proposta também exige motivo", () => {
    expect(problemaDaRecusa("ab")).toContain("registrada");
    expect(problemaDaRecusa("agrupou dois alambrados distintos")).toBeNull();
  });
});

describe("a proposta se apresenta como proposta", () => {
  it("cada sinal vira frase, e a frase diz por que o agrupamento foi proposto", () => {
    expect(sinalDaProposta("provenance")).toContain("procedência");
    expect(sinalDaProposta("label_proximity")).toContain("rótulo");
  });

  it("sinal desconhecido não vira frase inventada", () => {
    expect(sinalDaProposta("outro_sinal")).toBe("outro_sinal");
  });
});

describe("a recusa do servidor chega legível", () => {
  const erro = (
    code: string | null,
    details: Record<string, unknown> = {},
  ) => ({ code, detail: "detalhe do servidor", details, message: "mensagem crua" });

  it("camadas misturadas dizem QUAIS camadas foram misturadas", () => {
    const mensagem = mensagemDoErroDeIdentidade(
      erro("ELEMENT_REF_LAYER_MISMATCH", { layers: ["ALAMBRADO", "QUADRA"] }),
    );
    expect(mensagem).toContain("não mistura camadas");
    expect(mensagem).toContain("ALAMBRADO, QUADRA");
  });

  it("camadas misturadas sem detalhe ainda explicam a regra", () => {
    expect(mensagemDoErroDeIdentidade(erro("ELEMENT_REF_LAYER_MISMATCH"))).toContain(
      "um grupo por camada",
    );
  });

  it("entidade já declarada explica que mover são dois atos", () => {
    const mensagem = mensagemDoErroDeIdentidade(
      erro("ELEMENT_ALREADY_DECLARED", { entity_ids: ["a"] }),
    );
    expect(mensagem).toContain("dois atos");
    expect(mensagem).toContain("a");
  });

  it("cunhagem do cliente explica de quem é o nome", () => {
    expect(mensagemDoErroDeIdentidade(erro("ELEMENT_REF_NOT_ASSIGNABLE"))).toContain(
      "cunhado pelo servidor",
    );
  });

  it("conflito de revisão manda recarregar, não repetir", () => {
    expect(mensagemDoErroDeIdentidade(erro("REVISION_CONFLICT"))).toContain("Recarregue");
  });

  it("proposta sumida explica as três causas possíveis", () => {
    expect(mensagemDoErroDeIdentidade(erro("ELEMENT_PROPOSAL_NOT_FOUND"))).toContain(
      "recusada",
    );
  });

  it("código desconhecido devolve o detalhe do servidor, não uma frase inventada", () => {
    expect(mensagemDoErroDeIdentidade(erro("QUALQUER_OUTRO"))).toBe("detalhe do servidor");
  });

  it("sem código e sem detalhe, sobra a mensagem crua", () => {
    expect(
      mensagemDoErroDeIdentidade({
        code: null,
        detail: null,
        details: {},
        message: "mensagem crua",
      }),
    ).toBe("mensagem crua");
  });
});

describe("o carimbo do ato", () => {
  it("cita o ref, o PAPEL, o instante e a revisão da cena", () => {
    const texto = carimboDoAto(
      { element_ref: "EL-001", acted_by_role: "engineer", entity_ids: ["a", "b"] },
      "04/03/2026 às 14:32 UTC",
      7,
    );
    expect(texto).toContain("EL-001");
    expect(texto).toContain("engineer");
    expect(texto).toContain("04/03/2026 às 14:32 UTC");
    expect(texto).toContain("v7");
    expect(texto).toContain("2 entidades");
  });

  it("uma entidade só é dita no singular", () => {
    expect(
      carimboDoAto(
        { element_ref: "EL-002", acted_by_role: "engineer", entity_ids: ["a"] },
        "instante",
        3,
      ),
    ).toContain("1 entidade");
  });
});

describe("o rótulo legível do elemento (F-047 T2b)", () => {
  it("vem do mapa da cena, por element_ref, e nunca da entidade", () => {
    const [elemento] = elementosDeclarados(
      [entidade({ id: "a", element_ref: "EL-001" })],
      { "EL-001": "Alambrado da quadra" },
    );
    expect(elemento?.rotulo).toBe("Alambrado da quadra");
  });

  it("elemento sem nome tem rótulo nulo — e a tela dirá isso por escrito", () => {
    const [elemento] = elementosDeclarados([entidade({ id: "a", element_ref: "EL-001" })]);
    expect(elemento?.rotulo).toBeNull();
  });

  it("dois elementos com o MESMO rótulo continuam sendo dois elementos", () => {
    // Critério 5 na derivação da tela: o rótulo não agrupa nada. Quem agrupa é o ref.
    const elementos = elementosDeclarados(
      [
        entidade({ id: "a", element_ref: "EL-001" }),
        entidade({ id: "b", element_ref: "EL-002" }),
      ],
      { "EL-001": "Alambrado da quadra", "EL-002": "Alambrado da quadra" },
    );
    expect(elementos).toHaveLength(2);
    expect(elementos.map((elemento) => elemento.elementRef)).toEqual(["EL-001", "EL-002"]);
    expect(elementos.map((elemento) => elemento.rotulo)).toEqual([
      "Alambrado da quadra",
      "Alambrado da quadra",
    ]);
  });

  it("rótulo em branco não é impedimento: nomear é opcional", () => {
    expect(problemaDoRotulo("")).toBeNull();
    expect(problemaDoRotulo("Alambrado da quadra")).toBeNull();
  });

  it("rótulo só de espaço é impedimento, e o texto ensina o que fazer", () => {
    expect(problemaDoRotulo("   ")).toContain("deixe o campo vazio");
  });

  it("rótulo acima do teto do contrato é impedimento", () => {
    expect(problemaDoRotulo("A".repeat(MAXIMO_DO_ROTULO))).toBeNull();
    expect(problemaDoRotulo("A".repeat(MAXIMO_DO_ROTULO + 1))).toContain(
      String(MAXIMO_DO_ROTULO),
    );
  });

  it("a recusa do rótulo pelo servidor chega legível", () => {
    expect(
      mensagemDoErroDeIdentidade({
        code: "ELEMENT_LABEL_INVALID",
        detail: null,
        details: {},
        message: "",
      }),
    ).toContain("em branco");
  });

  it("o carimbo cita o nome dado, depois do ref e entre aspas", () => {
    const texto = carimboDoAto(
      {
        element_ref: "EL-001",
        acted_by_role: "engineer",
        entity_ids: ["a"],
        label: "Alambrado da quadra",
      },
      "instante",
      4,
    );
    expect(texto).toContain("EL-001 “Alambrado da quadra” declarado");
  });

  it("sem nome, o carimbo continua exatamente como era", () => {
    expect(
      carimboDoAto(
        { element_ref: "EL-001", acted_by_role: "engineer", entity_ids: ["a"], label: null },
        "instante",
        4,
      ),
    ).toContain("EL-001 declarado por engineer");
  });
});

describe("descricaoDaEntidade", () => {
  it("diz espécie, camada e precisão por escrito", () => {
    expect(descricaoDaEntidade(entidade({ kind: "polyline", layer: "QUADRA" }))).toBe(
      "polyline · camada QUADRA · derivada",
    );
  });

  it("marca anotação como anotação", () => {
    expect(descricaoDaEntidade(entidade({ kind: "text" }))).toContain("anotação");
  });
});
