import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { CodeSuggestionSet } from "@croquito/contracts";

import {
  abrirConfirmacao,
  blocosDaShortlist,
  confirmacaoDoItem,
  fonteDoPrecedente,
  pedidoDeConfirmacao,
  podeConfirmar,
  precedenteDoItem,
  precedenteFraco,
  selosDosItens,
  type ItemPrecedent,
  type PrecedentCode,
} from "./precedente";
import { codeDecisionBody } from "./requests";
import { postCodeClosure, postCodeDecision, type CascadeEntry } from "./api";
import {
  BlocoDePrecedente,
  ConfirmacaoDePrecedente,
  SeloDePrecedenteDoItem,
} from "./OrcamentoApp";

/**
 * O precedente de código na tela (F-044), contra o Design Approval Package aprovado em
 * 2026-08-28.
 *
 * Os rótulos, códigos, preços e contagens daqui são SINTÉTICOS, como os do pacote de
 * design: nenhum dado de praça real entra em `tests/`.
 */

const SCO = "a".repeat(64);
const EMOP = "b".repeat(64);
/** Fonte que a rodada NÃO instalou: o precedente de outra tabela cita um digest destes. */
const FORA_DA_CASCATA = "c".repeat(64);

const CASCATA: CascadeEntry[] = [
  {
    position: 1,
    origin: "sco",
    source_sha256: SCO,
    reference_month: "2023-10",
    source_label: "SCO-Rio",
    summary: { entries: 900 },
  },
  {
    position: 2,
    origin: "emop",
    source_sha256: EMOP,
    reference_month: "2023-07",
    source_label: "EMOP",
    summary: { entries: 700 },
  },
];

function codigo(
  code: string,
  extra: Partial<PrecedentCode> = {},
): PrecedentCode {
  return {
    code,
    worksite_count: 4,
    description: "Pavimento rígido em concreto, e=10cm, com juntas",
    unit: "m2",
    unit_price: "118.42",
    unit_compatible: true,
    catalog_sha256: SCO,
    ...extra,
  };
}

const PISO: ItemPrecedent = {
  item_id: "ti_piso",
  normalized_label: "piso em concreto",
  worksite_count: 4,
  codes: [
    codigo("BP09100050(B)"),
    codigo("ET39050109(/)", {
      description: "Tela de aço soldada para armadura de piso",
      unit_price: "24.90",
    }),
  ],
};

const ALAMBRADO_DE_OUTRA_FONTE: ItemPrecedent = {
  item_id: "ti_alambrado",
  normalized_label: "alambrado h=3,00m",
  worksite_count: 3,
  codes: [codigo("PJ14150203(A)", { catalog_sha256: FORA_DA_CASCATA })],
};

const UMA_PRACA: ItemPrecedent = {
  item_id: "ti_piso",
  normalized_label: "piso em concreto",
  worksite_count: 1,
  codes: [codigo("BP09100060(B)", { worksite_count: 1, unit_price: "131.07" })],
};

function candidato(
  code: string,
  catalogSha256: string = SCO,
): CodeSuggestionSet.CodeCandidate {
  return {
    code,
    description: "descrição do catálogo",
    in_contract: true,
    lexical_score: 0.8,
    unit: "m2",
    unit_compatible: true,
    unit_price: "118.42",
    catalog_sha256: catalogSha256,
    catalog_origin: "sco",
  };
}

describe("o bloco existe, ou não existe", () => {
  it("existe com a contagem de praças quando o rótulo já foi decidido antes", () => {
    const precedente = precedenteDoItem([PISO], "ti_piso", CASCATA);

    expect(precedente).not.toBeNull();
    expect(precedente?.worksite_count).toBe(4);
    expect(precedente?.codes.map((code) => code.code)).toEqual([
      "BP09100050(B)",
      "ET39050109(/)",
    ]);
  });

  /**
   * Decisão 7 do pacote: quando não há precedente, o bloco NÃO existe — não aparece vazio
   * nem desabilitado. `null` aqui é o que faz a tela ser exatamente a de hoje.
   */
  it("não existe para rótulo inédito, para item nenhum e para lista ausente", () => {
    expect(precedenteDoItem([PISO], "ti_deck", CASCATA)).toBeNull();
    expect(precedenteDoItem([PISO], "", CASCATA)).toBeNull();
    expect(precedenteDoItem(undefined, "ti_piso", CASCATA)).toBeNull();
    expect(precedenteDoItem([], "ti_piso", CASCATA)).toBeNull();
  });

  /**
   * "Sugerir código que não existe na tabela vigente é pior que não sugerir nada": o
   * precedente de outra fonte de preço não é oferecido, e some inteiro em vez de virar
   * bloco com aviso.
   */
  it("não existe quando o precedente é de outra fonte de preço", () => {
    expect(
      precedenteDoItem([ALAMBRADO_DE_OUTRA_FONTE], "ti_alambrado", CASCATA),
    ).toBeNull();
  });

  it("mantém só os códigos cuja fonte a rodada instalou", () => {
    const misto: ItemPrecedent = {
      ...PISO,
      codes: [
        codigo("BP09100050(B)"),
        codigo("XX00000000(/)", { catalog_sha256: FORA_DA_CASCATA }),
      ],
    };

    const precedente = precedenteDoItem([misto], "ti_piso", CASCATA);

    expect(precedente?.codes.map((code) => code.code)).toEqual([
      "BP09100050(B)",
    ]);
  });

  it("o precedente de uma praça só é fraco; o de duas em diante não é", () => {
    expect(precedenteFraco(UMA_PRACA)).toBe(true);
    expect(precedenteFraco(PISO)).toBe(false);
    expect(precedenteFraco({ ...PISO, worksite_count: 2 })).toBe(false);
  });
});

describe("a cascata continua idêntica", () => {
  const candidatos = [candidato("BP09100050(B)"), candidato("BP09100060(B)")];

  /**
   * O oráculo desta feature: o precedente entra ACIMA, e os blocos por fonte saem
   * exatamente como entraram — mesma referência de array, logo mesma ordem e mesmo
   * conteúdo. Reordenar a cascata é contrato de outra decisão (ADR-0021 / F-020).
   */
  it("devolve os candidatos como vieram, com e sem precedente", () => {
    const comPrecedente = blocosDaShortlist(
      candidatos,
      [PISO],
      "ti_piso",
      CASCATA,
    );
    const semPrecedente = blocosDaShortlist(candidatos, [], "ti_piso", CASCATA);
    const fonteDiferente = blocosDaShortlist(
      candidatos,
      [ALAMBRADO_DE_OUTRA_FONTE],
      "ti_alambrado",
      CASCATA,
    );

    expect(comPrecedente.candidatos).toBe(candidatos);
    expect(semPrecedente.candidatos).toBe(candidatos);
    expect(fonteDiferente.candidatos).toBe(candidatos);
    expect(comPrecedente.candidatos.map((item) => item.code)).toEqual([
      "BP09100050(B)",
      "BP09100060(B)",
    ]);
    expect(semPrecedente.precedente).toBeNull();
    expect(fonteDiferente.precedente).toBeNull();
  });

  /**
   * Decisão 3: um código pode aparecer duas vezes — no precedente e no bloco da fonte —, e
   * isso é intencional. Esconder a repetição faria o bloco da cascata parecer incompleto.
   */
  it("não remove da cascata o código que o precedente também traz", () => {
    const blocos = blocosDaShortlist(candidatos, [PISO], "ti_piso", CASCATA);

    expect(blocos.precedente?.codes.map((code) => code.code)).toContain(
      "BP09100050(B)",
    );
    expect(blocos.candidatos.map((item) => item.code)).toContain(
      "BP09100050(B)",
    );
  });
});

describe("os selos da lista de elementos", () => {
  it("dão a contagem a quem tem precedente e marcam inédito quem não tem", () => {
    const selos = selosDosItens(
      [PISO],
      ["ti_piso", "ti_deck"],
      CASCATA,
    );

    expect(selos.get("ti_piso")).toEqual({
      kind: "precedente",
      worksiteCount: 4,
    });
    expect(selos.get("ti_deck")).toEqual({ kind: "inedito" });
  });

  /**
   * Rodada sem precedente nenhum é a tela de hoje: nem selo, nem "rótulo inédito" em todo
   * item anunciando uma memória que a rodada inteira não tem.
   */
  it("ficam vazios quando nenhum elemento tem precedente visível", () => {
    expect(selosDosItens([], ["ti_piso", "ti_deck"], CASCATA).size).toBe(0);
    expect(
      selosDosItens(undefined, ["ti_piso", "ti_deck"], CASCATA).size,
    ).toBe(0);
    expect(
      selosDosItens([ALAMBRADO_DE_OUTRA_FONTE], ["ti_alambrado"], CASCATA).size,
    ).toBe(0);
  });
});

describe("a lista de confirmação", () => {
  it("carrega o elemento e some quando o elemento aberto é outro", () => {
    const confirmacao = abrirConfirmacao(PISO, "PISO EM CONCRETO");

    expect(confirmacao.itemId).toBe("ti_piso");
    expect(confirmacao.codes.map((code) => code.code)).toEqual([
      "BP09100050(B)",
      "ET39050109(/)",
    ]);
    expect(podeConfirmar(confirmacao)).toBe(true);
    expect(confirmacaoDoItem(confirmacao, "ti_piso")).toBe(confirmacao);
    expect(confirmacaoDoItem(confirmacao, "ti_alambrado")).toBeNull();
    expect(confirmacaoDoItem(confirmacao, "")).toBeNull();
    expect(confirmacaoDoItem(null, "ti_piso")).toBeNull();
  });

  /** Um pedido, N códigos, e `confirm` — nunca fechamento. */
  it("vira um pedido só, com os N códigos e a versão-base da rodada", () => {
    const pedido = pedidoDeConfirmacao(
      abrirConfirmacao(PISO, "PISO EM CONCRETO"),
      7,
    );

    expect(pedido).toEqual({
      itemId: "ti_piso",
      action: "confirm",
      baseVersion: 7,
      codes: ["BP09100050(B)", "ET39050109(/)"],
    });
    expect(codeDecisionBody(pedido)).toEqual({
      base_version: 7,
      item_id: "ti_piso",
      action: "confirm",
      codes: ["BP09100050(B)", "ET39050109(/)"],
    });
  });

  /**
   * `codes` e `code` são mutuamente exclusivos no contrato da rota: o corpo do lote não
   * leva o singular, e o corpo singular continua exatamente como era.
   */
  it("o corpo do lote não leva o código singular, e o singular não leva codes", () => {
    expect(
      codeDecisionBody({
        itemId: "ti_piso",
        action: "confirm",
        baseVersion: 7,
        codes: [" BP09100050(B) ", "", "ET39050109(/)"],
        code: "BP09100060(B)",
        catalogSha256: SCO,
      }),
    ).toEqual({
      base_version: 7,
      item_id: "ti_piso",
      action: "confirm",
      codes: ["BP09100050(B)", "ET39050109(/)"],
    });

    expect(
      codeDecisionBody({
        itemId: "ti_piso",
        action: "confirm",
        baseVersion: 7,
        codes: [],
        code: "BP09100060(B)",
        catalogSha256: SCO,
      }),
    ).toEqual({
      base_version: 7,
      item_id: "ti_piso",
      action: "confirm",
      code: "BP09100060(B)",
      catalog_sha256: SCO,
    });
  });
});

describe("o transporte do aceite de pacote", () => {
  const BASE = "http://localhost:8000";
  const TOKEN = "token-de-teste";
  const ROUND = "0197f2a0-0000-7000-8000-000000000009";
  const chamadas: { url: string; init: RequestInit | undefined }[] = [];

  beforeEach(() => {
    chamadas.length = 0;
    vi.stubGlobal("fetch", (url: string, init?: RequestInit) => {
      chamadas.push({ url, init });
      return Promise.resolve(
        new Response(JSON.stringify({}), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
      );
    });
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  /**
   * Aceitar o precedente é UM pedido com os N códigos — e não N pedidos —, e ele **não**
   * fecha o pacote: o fechamento continua sendo ato separado, de outra rota (F-038).
   */
  it("manda um pedido só, com os N códigos, e não toca na rota de fechamento", async () => {
    await postCodeDecision(
      TOKEN,
      ROUND,
      pedidoDeConfirmacao(abrirConfirmacao(PISO, "PISO EM CONCRETO"), 7),
    );

    expect(chamadas).toHaveLength(1);
    expect(chamadas[0].url).toBe(
      `${BASE}/v1/estimate-rounds/${ROUND}/code-assignments/decisions`,
    );
    expect(JSON.parse(String(chamadas[0].init?.body))).toEqual({
      base_version: 7,
      item_id: "ti_piso",
      action: "confirm",
      codes: ["BP09100050(B)", "ET39050109(/)"],
    });
    expect(
      chamadas.some((chamada) => chamada.url.includes("/closures")),
    ).toBe(false);

    // A rota de fechamento continua existindo e é OUTRO ato, com outro corpo.
    await postCodeClosure(TOKEN, ROUND, { itemId: "ti_piso", baseVersion: 8 });
    expect(chamadas).toHaveLength(2);
    expect(chamadas[1].url).toBe(
      `${BASE}/v1/estimate-rounds/${ROUND}/code-assignments/closures`,
    );
    expect(JSON.parse(String(chamadas[1].init?.body))).not.toHaveProperty(
      "codes",
    );
  });
});

describe("o bloco desenhado", () => {
  it("diz a contagem de praças escrita e não é distinguido só por cor", () => {
    const precedente = precedenteDoItem([PISO], "ti_piso", CASCATA);
    const html = renderToStaticMarkup(
      <BlocoDePrecedente
        precedente={precedente}
        fonte={
          precedente === null ? null : fonteDoPrecedente(precedente, CASCATA)
        }
        onAceitar={() => undefined}
        submitting={false}
      />,
    );

    expect(html).toContain("Você já usou isto em 4 praças");
    // De qual tabela vieram estes códigos, escrito no mesmo selo da cascata.
    expect(html).toContain("SCO");
    expect(html).toContain("BP09100050(B)");
    expect(html).toContain("ET39050109(/)");
    expect(html).toContain("Aceitar os 2 códigos deste rótulo");
    expect(html).toContain("observação, não decisão");
    // A repetição do código nos dois blocos é declarada por extenso.
    expect(html).toContain("aparece duas vezes");
    // Rodada de uma praça só não é este caso: nada de aviso âmbar aqui.
    expect(html).not.toContain("Decisão de uma praça só");
  });

  it("o precedente de uma praça só traz o aviso por extenso", () => {
    const html = renderToStaticMarkup(
      <BlocoDePrecedente
        precedente={precedenteDoItem([UMA_PRACA], "ti_piso", CASCATA)}
        fonte={null}
        onAceitar={() => undefined}
        submitting={false}
      />,
    );

    expect(html).toContain("Você usou isto em 1 praça");
    expect(html).toContain("Decisão de uma praça só");
    expect(html).toContain("Aceitar o código deste rótulo");
  });

  /** Nem vazio, nem desabilitado: sem precedente não há elemento nenhum na árvore. */
  it("não desenha nada sem precedente", () => {
    expect(
      renderToStaticMarkup(
        <BlocoDePrecedente
          precedente={null}
          fonte={null}
          onAceitar={() => undefined}
          submitting={false}
        />,
      ),
    ).toBe("");
  });

  /**
   * A fonte de preço do bloco é a das duas pontas: uma só quando todos os códigos a citam,
   * e `null` quando não convergem — rotular um precedente de duas tabelas com o nome de
   * uma delas seria afirmar o que não se sabe.
   */
  it("nomeia a fonte quando ela é uma só, e se cala quando não é", () => {
    expect(fonteDoPrecedente(PISO, CASCATA)?.source_sha256).toBe(SCO);

    const misturado: ItemPrecedent = {
      ...PISO,
      codes: [
        codigo("BP09100050(B)"),
        codigo("EM00000001(/)", { catalog_sha256: EMOP }),
      ],
    };
    expect(fonteDoPrecedente(misturado, CASCATA)).toBeNull();
  });

  it("o selo do elemento aparece com a contagem, e some quando não há memória", () => {
    const selos = selosDosItens([PISO], ["ti_piso", "ti_deck"], CASCATA);

    expect(
      renderToStaticMarkup(
        <SeloDePrecedenteDoItem selo={selos.get("ti_piso")} />,
      ),
    ).toContain("precedente em 4 praças");
    expect(
      renderToStaticMarkup(
        <SeloDePrecedenteDoItem selo={selos.get("ti_deck")} />,
      ),
    ).toContain("rótulo inédito");
    expect(
      renderToStaticMarkup(<SeloDePrecedenteDoItem selo={undefined} />),
    ).toBe("");
  });
});

describe("a confirmação desenhada", () => {
  it("mostra o que vai ser gravado e diz que o pacote não fecha por isso", () => {
    const html = renderToStaticMarkup(
      <ConfirmacaoDePrecedente
        confirmacao={abrirConfirmacao(PISO, "PISO EM CONCRETO")}
        submitting={false}
        onConfirmar={() => undefined}
        onCancelar={() => undefined}
      />,
    );

    expect(html).toContain("Antes de confirmar, o que vai ser gravado:");
    expect(html).toContain("BP09100050(B)");
    expect(html).toContain("ET39050109(/)");
    // Os preços saem como o servidor os mandou, só com a pontuação pt-BR.
    expect(html).toContain("118,42");
    expect(html).toContain("24,90");
    expect(html).toContain("numa revisão só");
    expect(html).toContain("não fecha o pacote sozinho");
    expect(html).toContain("Confirmar os 2 códigos");
    expect(html).toContain("Nada é aplicado sem este clique");
  });

  it("não desenha nada quando não há pacote à vista", () => {
    expect(
      renderToStaticMarkup(
        <ConfirmacaoDePrecedente
          confirmacao={null}
          submitting={false}
          onConfirmar={() => undefined}
          onCancelar={() => undefined}
        />,
      ),
    ).toBe("");
  });
});
