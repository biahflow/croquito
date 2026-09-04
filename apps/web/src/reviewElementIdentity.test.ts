/**
 * A derivação pura da identidade de elemento na revisão (F-051 T6).
 *
 * O que estes testes protegem: o casamento hint↔rótulo é o MESMO que o servidor cunhou
 * (igualdade normalizada ou palavra inteira, nunca parecença); o grupo do seletor sai
 * rotulado por escrito e nunca vazio; a candidata cuja identidade foi revogada não se
 * apresenta como identidade viva; e nenhuma frase da tela cita score ou distância.
 */
import { describe, expect, it } from "vitest";

import {
  agruparCandidatas,
  carimboDoAtoDaRevisao,
  dicaDeHintSemCasamento,
  dicaDoCasamento,
  hintCasaComORotulo,
  hintDoModelo,
  identidadesAtivas,
  mensagemDoErroDaRevisao,
  problemaDaDeclaracaoDaRevisao,
  problemaDaRevogacao,
  problemaDoRenomear,
  propostasDeclaradas,
  propostasSemIdentidade,
  RELACAO_POR_IDENTIDADE,
} from "./reviewElementIdentity";
import type { ReviewElementDeclaration, ReviewReading, VisionProposal } from "./api";

function declaracao(
  overrides: Partial<ReviewElementDeclaration> = {},
): ReviewElementDeclaration {
  return {
    element_ref: "EL-002",
    label: "B — fecho da área de lazer",
    proposal_ids: ["vp_1111111111111111", "vp_2222222222222222"],
    status: "active",
    declared_by_role: "engineer",
    declared_at: "2026-09-04T20:05:00Z",
    revoked_by_role: null,
    revoked_at: null,
    ...overrides,
  };
}

function leitura(overrides: Partial<ReviewReading> = {}): ReviewReading {
  return {
    id: "rd_1111111111111111",
    raw_text: "(B) → C= 56m",
    kind: "length",
    status: "proposed",
    ...overrides,
  };
}

function proposta(overrides: Partial<VisionProposal> = {}): VisionProposal {
  return {
    id: "vp_1111111111111111",
    kind: "line",
    precision: "unresolved",
    export: false,
    geometry: { type: "line", start: { x: 0, y: 0 }, end: { x: 10, y: 0 } },
    ...overrides,
  } as VisionProposal;
}

const identidade = (proposalId: string) => ({
  proposal_id: proposalId,
  relation: RELACAO_POR_IDENTIDADE,
});

const proximidade = (proposalId: string) => ({
  proposal_id: proposalId,
  relation: "nearest_geometry",
});

describe("hintCasaComORotulo", () => {
  it("casa por igualdade, ignorando caixa e espaço nas pontas", () => {
    expect(hintCasaComORotulo("B", "B")).toBe(true);
    expect(hintCasaComORotulo(" b ", "B")).toBe(true);
    expect(hintCasaComORotulo("Grade B", "grade b")).toBe(true);
  });

  it("casa o hint como palavra inteira do rótulo, com os separadores do contrato", () => {
    expect(hintCasaComORotulo("B", "grade B")).toBe(true);
    expect(hintCasaComORotulo("B", "B — fecho da área de lazer")).toBe(true);
    expect(hintCasaComORotulo("B", "grade B / lateral")).toBe(true);
    expect(hintCasaComORotulo("B", "B: arquibancada")).toBe(true);
  });

  it("não casa por parecença, prefixo ou substring — nunca fuzzy silencioso", () => {
    expect(hintCasaComORotulo("E", "B")).toBe(false);
    expect(hintCasaComORotulo("B", "fecho")).toBe(false);
    expect(hintCasaComORotulo("B", "BOMBA")).toBe(false);
    expect(hintCasaComORotulo("", "B")).toBe(false);
    expect(hintCasaComORotulo("   ", "B")).toBe(false);
  });

  it("é assimétrico de propósito: o hint procura o rótulo, não o contrário", () => {
    expect(hintCasaComORotulo("B", "grade B")).toBe(true);
    expect(hintCasaComORotulo("grade B", "B")).toBe(false);
  });

  it("não apaga acento: apagar a diferença seria adivinhar a palavra escrita", () => {
    expect(hintCasaComORotulo("área", "área de lazer")).toBe(true);
    expect(hintCasaComORotulo("area", "área de lazer")).toBe(false);
  });
});

describe("hintDoModelo", () => {
  it("devolve o rótulo aparado quando o modelo leu um", () => {
    expect(hintDoModelo(leitura({ target_entity_label: " B " }))).toBe("B");
  });

  it("ausência é ausência: sem campo, vazio ou só espaço não vira chip", () => {
    expect(hintDoModelo(leitura())).toBeNull();
    expect(hintDoModelo(leitura({ target_entity_label: null }))).toBeNull();
    expect(hintDoModelo(leitura({ target_entity_label: "   " }))).toBeNull();
  });
});

describe("identidadesAtivas e propostasDeclaradas", () => {
  it("revogada fica na lista e não conta como identidade nem cobre proposta", () => {
    const declaracoes = [
      declaracao(),
      declaracao({
        element_ref: "EL-003",
        label: "C",
        proposal_ids: ["vp_3333333333333333"],
        status: "revoked",
        revoked_by_role: "engineer",
        revoked_at: "2026-09-04T21:00:00Z",
      }),
    ];

    expect(identidadesAtivas(declaracoes).map((item) => item.element_ref)).toEqual([
      "EL-002",
    ]);
    expect([...propostasDeclaradas(declaracoes)]).toEqual([
      "vp_1111111111111111",
      "vp_2222222222222222",
    ]);
  });

  it("propostas liberadas pela revogação voltam a poder ser declaradas", () => {
    const propostas = [proposta(), proposta({ id: "vp_3333333333333333" })];
    const revogada = declaracao({
      proposal_ids: ["vp_1111111111111111"],
      status: "revoked",
    });

    expect(propostasSemIdentidade(propostas, [revogada]).map((item) => item.id)).toEqual([
      "vp_1111111111111111",
      "vp_3333333333333333",
    ]);
    expect(
      propostasSemIdentidade(propostas, [
        declaracao({ proposal_ids: ["vp_1111111111111111"] }),
      ]).map((item) => item.id),
    ).toEqual(["vp_3333333333333333"]);
  });
});

describe("agruparCandidatas", () => {
  it("sem candidata por identidade não cria grupo nenhum — a lista sai plana", () => {
    const agrupadas = agruparCandidatas(
      [proximidade("vp_9999999999999999"), proximidade("vp_8888888888888888")],
      [],
    );

    expect(agrupadas.grupos).toEqual([]);
    expect(agrupadas.proximidade.map((item) => item.proposal_id)).toEqual([
      "vp_9999999999999999",
      "vp_8888888888888888",
    ]);
  });

  it("agrupa por elemento dono e rotula o grupo por escrito, com etiqueta e rótulo", () => {
    const agrupadas = agruparCandidatas(
      [
        identidade("vp_1111111111111111"),
        proximidade("vp_9999999999999999"),
        identidade("vp_2222222222222222"),
      ],
      [declaracao()],
    );

    expect(agrupadas.grupos).toHaveLength(1);
    expect(agrupadas.grupos[0].rotuloDoGrupo).toBe(
      "Pela identidade — ◇ EL-002 · B — fecho da área de lazer",
    );
    expect(agrupadas.grupos[0].candidatas.map((item) => item.proposal_id)).toEqual([
      "vp_1111111111111111",
      "vp_2222222222222222",
    ]);
    expect(agrupadas.proximidade.map((item) => item.proposal_id)).toEqual([
      "vp_9999999999999999",
    ]);
  });

  it("dois elementos que casam com o mesmo hint viram dois grupos, na ordem do ref", () => {
    const agrupadas = agruparCandidatas(
      [identidade("vp_3333333333333333"), identidade("vp_1111111111111111")],
      [
        declaracao({
          element_ref: "EL-004",
          label: "alambrado B",
          proposal_ids: ["vp_3333333333333333"],
        }),
        declaracao({ label: "grade B", proposal_ids: ["vp_1111111111111111"] }),
      ],
    );

    expect(agrupadas.grupos.map((grupo) => grupo.elementRef)).toEqual([
      "EL-002",
      "EL-004",
    ]);
  });

  it("elemento sem rótulo é dito por escrito, nunca como um traço mudo", () => {
    const agrupadas = agruparCandidatas(
      [identidade("vp_1111111111111111")],
      [declaracao({ label: null, proposal_ids: ["vp_1111111111111111"] })],
    );

    expect(agrupadas.grupos[0].rotuloDoGrupo).toBe(
      "Pela identidade — ◇ EL-002 · sem rótulo",
    );
  });

  it("candidata sustentada por identidade REVOGADA diz que ela foi revogada", () => {
    const agrupadas = agruparCandidatas(
      [identidade("vp_1111111111111111")],
      [
        declaracao({
          proposal_ids: ["vp_1111111111111111"],
          status: "revoked",
          revoked_by_role: "engineer",
          revoked_at: "2026-09-04T21:00:00Z",
        }),
      ],
    );

    expect(agrupadas.grupos[0].revogada).toBe(true);
    expect(agrupadas.grupos[0].rotuloDoGrupo).toContain("(identidade revogada)");
  });

  it("candidata sem dono legível não inventa ref: vira resíduo declarado, e por último", () => {
    const agrupadas = agruparCandidatas(
      [identidade("vp_7777777777777777"), identidade("vp_1111111111111111")],
      [declaracao({ proposal_ids: ["vp_1111111111111111"] })],
    );

    expect(agrupadas.grupos.map((grupo) => grupo.rotuloDoGrupo)).toEqual([
      "Pela identidade — ◇ EL-002 · B — fecho da área de lazer",
      "Pela identidade do elemento declarado",
    ]);
    expect(agrupadas.grupos[1].elementRef).toBeNull();
  });
});

describe("dicaDoCasamento e dicaDeHintSemCasamento", () => {
  it("explica o casamento sem citar score nem distância", () => {
    const { grupos } = agruparCandidatas(
      [identidade("vp_1111111111111111")],
      [declaracao()],
    );
    const dica = dicaDoCasamento("B", grupos);

    expect(dica).toBe(
      "O hint “B” casa com o elemento declarado ◇ EL-002 · B — fecho da área de lazer — " +
        "as propostas dele entram como candidatas pela identidade, independente de distância.",
    );
    expect(dica).not.toMatch(/px|score|confian|distância de|\d+,\d+/);
  });

  it("dois elementos casando entram os dois na frase", () => {
    const { grupos } = agruparCandidatas(
      [identidade("vp_1111111111111111"), identidade("vp_3333333333333333")],
      [
        declaracao({ label: "grade B", proposal_ids: ["vp_1111111111111111"] }),
        declaracao({
          element_ref: "EL-004",
          label: "alambrado B",
          proposal_ids: ["vp_3333333333333333"],
        }),
      ],
    );

    expect(dicaDoCasamento("B", grupos)).toContain(
      "casa com os elementos declarados ◇ EL-002 · grade B e ◇ EL-004 · alambrado B",
    );
  });

  it("sem grupo não há o que explicar", () => {
    expect(dicaDoCasamento("B", [])).toBeNull();
  });

  it("hint que não casa fala apenas quando há identidade ativa no job", () => {
    expect(dicaDeHintSemCasamento("E", [declaracao()], [])).toBe(
      "Nenhum elemento declarado tem o rótulo “E” — nenhuma candidata nova. O hint fica " +
        "visível, esperando ou uma declaração ou uma correção.",
    );
    // Controle (DAP estado 09): sem declaração nenhuma, a etapa é a de hoje.
    expect(dicaDeHintSemCasamento("E", [], [])).toBeNull();
    // Sem hint não há o que dizer.
    expect(dicaDeHintSemCasamento(null, [declaracao()], [])).toBeNull();
    // Só revogada também não fala: revogada não é identidade.
    expect(
      dicaDeHintSemCasamento("E", [declaracao({ status: "revoked" })], []),
    ).toBeNull();
  });
});

describe("impedimentos dos atos da revisão", () => {
  it("declarar exige proposta e justificativa, e diz o caminho da anotação", () => {
    expect(problemaDaDeclaracaoDaRevisao([], "motivo suficiente")).toContain(
      "anotação da folha",
    );
    expect(problemaDaDeclaracaoDaRevisao(["vp_1"], "ab")).toContain(
      "justificativa do agrupamento",
    );
    expect(problemaDaDeclaracaoDaRevisao(["vp_1"], "  abc  ")).toBeNull();
  });

  it("revogar e renomear exigem motivo; renomear exige também o nome novo", () => {
    expect(problemaDaRevogacao("")).toContain("revogação fica registrada");
    expect(problemaDaRevogacao("agrupamento errado")).toBeNull();
    expect(problemaDoRenomear("  ", "motivo bom")).toContain("apagar o nome não é renomear");
    expect(problemaDoRenomear("C", "ab")).toContain("renomear é ato declarado");
    expect(problemaDoRenomear("C", "conferido com a folha")).toBeNull();
  });

  it("motivo acima do teto do contrato é recusado antes de a requisição sair", () => {
    expect(problemaDaRevogacao("x".repeat(501))).toContain("no máximo 500 caracteres");
  });
});

describe("carimboDoAtoDaRevisao", () => {
  it("cita papel, instante, versão do pacote de revisão e a contagem de propostas", () => {
    const carimbo = carimboDoAtoDaRevisao(
      {
        act: "declared",
        element_ref: "EL-002",
        label: "B — fecho da área de lazer",
        acted_by_role: "engineer",
        proposal_ids: ["vp_1111111111111111", "vp_2222222222222222"],
        review_version: 5,
      },
      "04/09/2026 às 20:05 UTC",
    );

    expect(carimbo).toBe(
      "EL-002 “B — fecho da área de lazer” declarado por engineer em 04/09/2026 às 20:05 " +
        "UTC, sobre a revisão v5 do pacote de revisão · 2 propostas.",
    );
  });

  it("nomeia cada ato pelo verbo dele, e a identidade sem rótulo sai sem aspas vazias", () => {
    const base = {
      element_ref: "EL-002",
      acted_by_role: "architect",
      proposal_ids: ["vp_1111111111111111"],
      review_version: 6,
    };

    expect(carimboDoAtoDaRevisao({ ...base, act: "revoked", label: null }, "x")).toContain(
      "EL-002 revogado por architect",
    );
    expect(
      carimboDoAtoDaRevisao({ ...base, act: "relabeled", label: "C" }, "x"),
    ).toContain("EL-002 “C” renomeado por architect");
    expect(carimboDoAtoDaRevisao({ ...base, act: "declared", label: null }, "x")).toContain(
      "· 1 proposta.",
    );
  });
});

describe("mensagemDoErroDaRevisao", () => {
  const erro = (code: string, details: Record<string, unknown> = {}) => ({
    code,
    detail: null,
    details,
    message: "falhou",
  });

  it("o rótulo duplicado aponta o elemento existente e diz o que fazer", () => {
    const mensagem = mensagemDoErroDaRevisao(
      erro("ELEMENT_LABEL_ALREADY_USED", { element_ref: "EL-002" }),
    );

    expect(mensagem).toContain("referente inequívoco");
    expect(mensagem).toContain("EL-002");
  });

  it("fala de PROPOSTA, não de entidade — a cena ainda não existe nesta etapa", () => {
    expect(mensagemDoErroDaRevisao(erro("ELEMENT_ALREADY_DECLARED"))).toContain(
      "Proposta já declarada",
    );
    expect(mensagemDoErroDaRevisao(erro("PROPOSALS_NOT_READY"))).toContain(
      "anotação da folha",
    );
  });

  it("o conflito manda recarregar a revisão atual — o idioma que a tela já tem", () => {
    expect(mensagemDoErroDaRevisao(erro("REVISION_CONFLICT"))).toContain(
      "Recarregue a revisão atual",
    );
  });

  it("devolve null no código que a camada da cena já traduz", () => {
    expect(mensagemDoErroDaRevisao(erro("ELEMENT_REF_NOT_ASSIGNABLE"))).toBeNull();
    expect(mensagemDoErroDaRevisao(erro("ELEMENT_LABEL_INVALID"))).toBeNull();
  });
});
