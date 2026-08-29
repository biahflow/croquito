import { describe, expect, it } from "vitest";
import type { Valuation } from "@croquito/contracts";
import type { CodesResponse, WorksiteResponse, WorksiteSheet } from "./api";
import {
  avisoDoLoteDePromocao,
  boletimDaFolha,
  chaveDoBoletimDaFolha,
  codificacaoDasFolhas,
  estadoDaFolha,
  folhaDaChamada,
  folhaEmFoco,
  folhaLabel,
  folhasQueAindaCabem,
  memoriaDaFolha,
  paginasPromovidas,
  pracaPlural,
  recusaDaPraca,
  recusaDoVinculo,
  resumoDaCodificacao,
  resumoDaFolha,
  rotuloDoLoteDeExtracao,
  rotuloDoLoteDePromocao,
} from "./praca";

/**
 * Folha sintética. O padrão é a folha que ainda não foi extraída — o estado em que toda
 * folha nasce —, e cada teste declara só o que o caso dele muda.
 */
function folha(overrides: Partial<WorksiteSheet> = {}): WorksiteSheet {
  return {
    plate_id: "praca-sintetica-planta",
    position: 1,
    source_sha256: "a".repeat(64),
    page_number: 1,
    page_count: 6,
    extraction_status: null,
    extraction_failure_code: null,
    extraction_updated_at: null,
    takeoff_present: false,
    packet_sha256: null,
    review_status: null,
    item_count: null,
    pending_items: null,
    ...overrides,
  };
}

function praca(
  plates: WorksiteSheet[],
  overrides: Partial<WorksiteResponse> = {},
): WorksiteResponse {
  return {
    round_id: "0197f2a0-0000-7000-8000-000000000001",
    version: 4,
    worksite_key: "praca-sintetica-oeste",
    worksite_name: "Praça Sintética Oeste",
    plate_limit: 12,
    plates,
    identity_links: [],
    consolidated: {
      present: false,
      worksite_takeoff_sha256: null,
      document: null,
      pending_plate_ids: plates
        .filter((sheet) => !sheet.takeoff_present)
        .map((sheet) => sheet.plate_id),
      refusal_code: "ROUND_STAGE_NOT_READY",
    },
    ...overrides,
  };
}

const REVISADA = folha({
  takeoff_present: true,
  review_status: "complete",
  item_count: 4,
  pending_items: 0,
  packet_sha256: "b".repeat(64),
});

describe("estado da folha", () => {
  it("dá símbolo próprio e texto por extenso a cada estado — cor nunca é o único indicador", () => {
    const estados = [
      estadoDaFolha(REVISADA),
      estadoDaFolha(
        folha({ takeoff_present: true, review_status: "review_required", item_count: 3, pending_items: 2 }),
      ),
      estadoDaFolha(folha({ extraction_status: "running" })),
      estadoDaFolha(folha({ extraction_status: "failed", extraction_failure_code: "PROVIDER_EXECUTION_FAILED" })),
      estadoDaFolha(folha()),
    ];

    expect(estados.map((estado) => estado.id)).toEqual([
      "revisada",
      "pendente",
      "extraindo",
      "falhou",
      "nao-extraida",
    ]);
    // Cada estado tem símbolo e rótulo únicos: nenhum depende de cor para ser lido.
    expect(new Set(estados.map((estado) => estado.symbol)).size).toBe(5);
    expect(new Set(estados.map((estado) => estado.label)).size).toBe(5);
    for (const estado of estados) {
      expect(estado.label.length).toBeGreaterThan(5);
    }
  });

  /**
   * O pacote publicado manda: o espelho do estado de extração da folha pode não ter sido
   * reescrito ainda, e uma folha revisada não pode voltar a aparecer "em extração".
   */
  it("a folha com pacote publicado já não está em extração, mesmo com a fila dizendo o contrário", () => {
    const estado = estadoDaFolha(
      folha({
        takeoff_present: true,
        review_status: "complete",
        item_count: 2,
        pending_items: 0,
        extraction_status: "running",
      }),
    );

    expect(estado.id).toBe("revisada");
  });

  it("a folha que falhou traz a frase do código estável, não o código cru", () => {
    const resumo = resumoDaFolha(
      folha({ extraction_status: "failed", extraction_failure_code: "PROVIDER_EXECUTION_FAILED" }),
    );

    expect(resumo).not.toContain("PROVIDER_EXECUTION_FAILED");
    expect(resumo.length).toBeGreaterThan(20);
  });

  it("conta itens e decididos com o que o servidor mandou, e não escreve pendência que não existe", () => {
    expect(resumoDaFolha(REVISADA)).toBe("4 itens · 4 decididos");
    expect(
      resumoDaFolha(
        folha({ takeoff_present: true, review_status: "review_required", item_count: 3, pending_items: 2 }),
      ),
    ).toBe("3 itens · 1 decidido · 2 pendentes");
  });

  /**
   * Folha sem pacote tem contagem `null`, e `null` não é zero: dizer "0 itens" afirmaria
   * que a leitura aconteceu e não achou nada.
   */
  it("a folha ainda não extraída fala da página, e não de zero item", () => {
    const resumo = resumoDaFolha(folha({ page_number: 3 }));

    expect(resumo).toContain("Página 3");
    expect(resumo).not.toContain("0 itens");
  });
});

describe("a praça e suas folhas", () => {
  it("uma folha só não é praça plural; a segunda folha a torna plural", () => {
    expect(pracaPlural(null)).toBe(false);
    expect(pracaPlural(praca([REVISADA]))).toBe(false);
    expect(pracaPlural(praca([REVISADA, folha({ plate_id: "detalhe", position: 2 })]))).toBe(
      true,
    );
  });

  it("o foco cai na primeira folha enquanto ninguém escolheu, e segue a escolha depois", () => {
    const segunda = folha({ plate_id: "detalhe", position: 2 });
    const estado = praca([REVISADA, segunda]);

    expect(folhaEmFoco(estado, "")?.plate_id).toBe(REVISADA.plate_id);
    expect(folhaEmFoco(estado, "detalhe")?.plate_id).toBe("detalhe");
    // Folha que não existe mais na praça não deixa a tela sem foco.
    expect(folhaEmFoco(estado, "folha-apagada")?.plate_id).toBe(REVISADA.plate_id);
    expect(folhaEmFoco(null, "detalhe")).toBeNull();
  });

  it("o cabeçalho diz qual folha de quantas", () => {
    expect(folhaLabel(2, 3)).toBe("folha 2 de 3");
  });

  it("o que ainda cabe sai do teto que o servidor declarou", () => {
    expect(folhasQueAindaCabem(praca([REVISADA], { plate_limit: 3 }))).toBe(2);
    expect(
      folhasQueAindaCabem(praca([REVISADA, folha({ plate_id: "b", position: 2 })], { plate_limit: 2 })),
    ).toBe(0);
    expect(folhasQueAindaCabem(null)).toBe(0);
  });
});

describe("a recusa da praça", () => {
  it("nomeia a folha que ainda não foi extraída", () => {
    const recusa = recusaDaPraca(
      praca([REVISADA, folha({ plate_id: "detalhe-playground", position: 2, extraction_status: "running" })]),
    );

    expect(recusa).not.toBeNull();
    expect(recusa?.message).toContain("folha 2 de 2");
    expect(recusa?.message).toContain("detalhe-playground");
    expect(recusa?.code).toBe("ROUND_STAGE_NOT_READY");
    expect(recusa?.folhas).toHaveLength(1);
  });

  it("nomeia a folha extraída que tem item sem decisão, e diz quantos", () => {
    const recusa = recusaDaPraca(
      praca(
        [
          REVISADA,
          folha({
            plate_id: "detalhe-playground",
            position: 2,
            takeoff_present: true,
            review_status: "review_required",
            item_count: 3,
            pending_items: 2,
          }),
        ],
        { consolidated: { present: false, worksite_takeoff_sha256: null, document: null, pending_plate_ids: [], refusal_code: "WORKSITE_TAKEOFF_PLATE_PENDING" } },
      ),
    );

    expect(recusa?.message).toContain("2 itens sem decisão");
    expect(recusa?.message).toContain("detalhe-playground");
    expect(recusa?.code).toBe("WORKSITE_TAKEOFF_PLATE_PENDING");
  });

  it("praça com consolidado montado não tem recusa nenhuma a mostrar", () => {
    const fechada = praca([REVISADA], {
      consolidated: {
        present: true,
        worksite_takeoff_sha256: "c".repeat(64),
        document: {
          worksite_key: "praca-sintetica-oeste",
          plates: [{ plate_id: REVISADA.plate_id, packet_digest: "b".repeat(64) }],
          identity_links: [],
        },
        pending_plate_ids: [],
        refusal_code: null,
      },
    });

    expect(recusaDaPraca(fechada)).toBeNull();
  });

  it("praça sem folha nenhuma diz isso, em vez de listar folha inexistente", () => {
    const recusa = recusaDaPraca(praca([]));

    expect(recusa?.folhas).toEqual([]);
    expect(recusa?.message).toContain("folha nenhuma");
  });
});

describe("o lote de páginas", () => {
  it("as páginas já promovidas saem do mesmo documento, e só dele", () => {
    const outroDocumento = "d".repeat(64);
    const estado = praca([
      folha({ plate_id: "p1", position: 1, page_number: 1 }),
      folha({ plate_id: "p3", position: 2, page_number: 3 }),
      folha({ plate_id: "p9", position: 3, page_number: 9, source_sha256: outroDocumento }),
    ]);

    expect(paginasPromovidas(estado, "A".repeat(64))).toEqual([1, 3]);
    expect(paginasPromovidas(estado, outroDocumento)).toEqual([9]);
    expect(paginasPromovidas(estado, null)).toEqual([]);
    expect(paginasPromovidas(null, "a".repeat(64))).toEqual([]);
  });

  /**
   * O custo por folha não pode aparecer só na fatura: o número de folhas que o ato
   * acrescenta fica escrito no próprio botão, antes do clique.
   */
  it("o botão escreve quantas folhas o ato acrescenta", () => {
    expect(rotuloDoLoteDePromocao(3)).toContain("3 folhas");
    expect(rotuloDoLoteDePromocao(1)).toContain("1 folha");
    expect(rotuloDoLoteDePromocao(0)).not.toMatch(/\d/);
  });

  it("o botão da leitura escreve quantas chamadas pagas ela dispara", () => {
    expect(rotuloDoLoteDeExtracao(3)).toContain("3 chamadas pagas");
    expect(rotuloDoLoteDeExtracao(1)).toContain("1 chamada paga");
    expect(rotuloDoLoteDeExtracao(0)).not.toMatch(/\d/);
  });

  it("o aviso repete o número do botão e diz que promover não lê legenda", () => {
    const aviso = avisoDoLoteDePromocao(2);

    expect(aviso).toContain("2 páginas selecionadas");
    expect(aviso).toContain("leitura é ato à parte");
  });
});

describe("a transição de estado de uma folha", () => {
  /**
   * A vida de uma folha, na ordem em que ela acontece: acrescentada, enfileirada, extraída
   * com item pendente, revisada. A praça só fecha no último passo, e é o consolidado do
   * servidor que diz isso — a recusa some junto com a pendência.
   */
  it("vai de acrescentada a revisada, e a praça só fecha no fim", () => {
    const passos: WorksiteSheet[] = [
      folha({ plate_id: "detalhe", position: 2 }),
      folha({ plate_id: "detalhe", position: 2, extraction_status: "queued" }),
      folha({
        plate_id: "detalhe",
        position: 2,
        extraction_status: "done",
        takeoff_present: true,
        review_status: "review_required",
        item_count: 3,
        pending_items: 1,
        packet_sha256: "e".repeat(64),
      }),
      folha({
        plate_id: "detalhe",
        position: 2,
        extraction_status: "done",
        takeoff_present: true,
        review_status: "complete",
        item_count: 3,
        pending_items: 0,
        packet_sha256: "e".repeat(64),
      }),
    ];

    expect(passos.map((passo) => estadoDaFolha(passo).id)).toEqual([
      "nao-extraida",
      "extraindo",
      "pendente",
      "revisada",
    ]);

    // A recusa acompanha o passo, e o consolidado do servidor é quem a encerra.
    const recusas = passos.map((passo) => recusaDaPraca(praca([REVISADA, passo])));
    expect(recusas.every((recusa) => recusa !== null)).toBe(true);
    expect(recusas[0]?.message).toContain("ainda não extraída");
    expect(recusas[2]?.message).toContain("1 item sem decisão");
    expect(recusas[3]?.message).toContain("o servidor ainda não montou");

    const fechada = praca([REVISADA, passos[3]], {
      consolidated: {
        present: true,
        worksite_takeoff_sha256: "c".repeat(64),
        document: {
          worksite_key: "praca-sintetica-oeste",
          plates: [
            { plate_id: REVISADA.plate_id, packet_digest: "b".repeat(64) },
            { plate_id: "detalhe", packet_digest: "e".repeat(64) },
          ],
          identity_links: [],
        },
        pending_plate_ids: [],
        refusal_code: null,
      },
    });
    expect(recusaDaPraca(fechada)).toBeNull();
  });
});

/**
 * A folha que TODA chamada da tela nomeia. `undefined` na praça de uma folha é a regra
 * que mantém a rodada de uma prancha idêntica à de antes da praça (ADR-0057, decisão 8).
 */
describe("a folha nomeada nas chamadas", () => {
  it("praça de uma folha não nomeia folha nenhuma", () => {
    expect(folhaDaChamada(praca([REVISADA]), "")).toBeUndefined();
    expect(folhaDaChamada(praca([REVISADA]), REVISADA.plate_id)).toBeUndefined();
    expect(folhaDaChamada(null, "qualquer")).toBeUndefined();
  });

  it("praça plural nomeia a folha em foco — e a primeira enquanto ninguém escolheu", () => {
    const detalhe = folha({ plate_id: "detalhe", position: 2, takeoff_present: true });
    const plural = praca([REVISADA, detalhe]);

    expect(folhaDaChamada(plural, "")).toBe(REVISADA.plate_id);
    expect(folhaDaChamada(plural, "detalhe")).toBe("detalhe");
    // Folha que não é desta praça cai na primeira, como `folhaEmFoco`: nomear uma folha
    // que não existe faria o servidor recusar com `ROUND_PLATE_NOT_FOUND`.
    expect(folhaDaChamada(plural, "de-outra-rodada")).toBe(REVISADA.plate_id);
  });
});

/**
 * O boletim de cada folha. A chave é espelho de `worksite_calc._plate_labels`: sem sufixo
 * na praça de uma folha, `-pN` a partir da segunda.
 */
describe("o boletim de cada folha", () => {
  const valuation = {
    period_number: 1,
    reference_label: "AGOSTO/2026",
    bulletins: [
      {
        worksite_key: "praca-sintetica-oeste-p1",
        worksite_name: "Praça Sintética Oeste P1",
        total_amount: "6000.00",
        lines: [
          {
            item_number: "1",
            code: "04.02.010",
            description: "ALAMBRADO",
            unit: "m",
            unit_price: "150.00",
            quantity: "40.00",
            total: "6000.00",
          },
        ],
      },
      {
        worksite_key: "praca-sintetica-oeste-p2",
        worksite_name: "Praça Sintética Oeste P2",
        total_amount: "3000.00",
        lines: [
          {
            item_number: "1",
            code: "04.02.010",
            description: "ALAMBRADO",
            unit: "m",
            unit_price: "150.00",
            quantity: "20.00",
            total: "3000.00",
          },
        ],
      },
    ],
    calc_sheets: [
      {
        worksite_key: "praca-sintetica-oeste-p1",
        item_number: "1",
        total_quantity: "40.00",
        blocks: [
          {
            label: "PERÍMETRO NORTE",
            recipe: "length",
            operands: [{ name: "COMPRIMENTO", value: "40.00", unit: "m" }],
            subtotal: "40.00",
          },
        ],
      },
      {
        worksite_key: "praca-sintetica-oeste-p2",
        item_number: "1",
        total_quantity: "20.00",
        blocks: [
          {
            label: "PERÍMETRO SUL",
            recipe: "length",
            operands: [{ name: "COMPRIMENTO", value: "20.00", unit: "m" }],
            subtotal: "20.00",
          },
        ],
      },
    ],
  } as unknown as Valuation.CroquitoValuation;

  it("a chave é a da praça com uma folha e ganha o sufixo da posição a partir de duas", () => {
    expect(chaveDoBoletimDaFolha("praca-sintetica-oeste", 1, 1)).toBe(
      "praca-sintetica-oeste",
    );
    expect(chaveDoBoletimDaFolha("praca-sintetica-oeste", 1, 2)).toBe(
      "praca-sintetica-oeste-p1",
    );
    expect(chaveDoBoletimDaFolha("praca-sintetica-oeste", 3, 4)).toBe(
      "praca-sintetica-oeste-p3",
    );
  });

  it("casa boletim e memória por CHAVE, e a memória fica na folha onde a leitura foi feita", () => {
    const segunda = folha({ plate_id: "detalhe", position: 2, takeoff_present: true });

    const primeiro = boletimDaFolha(valuation, "praca-sintetica-oeste", REVISADA, 2);
    const segundo = boletimDaFolha(valuation, "praca-sintetica-oeste", segunda, 2);

    expect(primeiro?.total_amount).toBe("6000.00");
    expect(segundo?.total_amount).toBe("3000.00");
    expect(
      memoriaDaFolha(valuation, "praca-sintetica-oeste-p1")[0]?.blocks[0]?.label,
    ).toBe("PERÍMETRO NORTE");
    expect(
      memoriaDaFolha(valuation, "praca-sintetica-oeste-p2")[0]?.blocks[0]?.label,
    ).toBe("PERÍMETRO SUL");
  });

  /**
   * Boletim montado antes de a folha entrar: casar por chave DEVOLVE `null`, e é isso que
   * permite dizer "esta folha ficou de fora" em vez de rotular o boletim da folha 1 com o
   * cabeçalho da folha 2 — que é o que casar por posição na lista faria.
   */
  it("folha fora do boletim gravado devolve null, nunca o boletim de outra folha", () => {
    const terceira = folha({ plate_id: "corte", position: 3, takeoff_present: true });

    expect(boletimDaFolha(valuation, "praca-sintetica-oeste", terceira, 3)).toBeNull();
    expect(memoriaDaFolha(valuation, "praca-sintetica-oeste-p3")).toEqual([]);
    expect(boletimDaFolha(null, "praca-sintetica-oeste", REVISADA, 2)).toBeNull();
  });
});

/** O andamento da codificação por folha: contagens do servidor, nunca deduzidas. */
describe("a codificação por folha", () => {
  function codes(overrides: Partial<CodesResponse> = {}): CodesResponse {
    return {
      round_id: "0197f2a0-0000-7000-8000-000000000001",
      version: 9,
      assignments: null,
      assignments_sha256: null,
      confirmed: 0,
      rejected: 0,
      closed: 0,
      pending_items: [],
      ...overrides,
    };
  }

  const detalhe = folha({ plate_id: "detalhe", position: 2, takeoff_present: true });

  it("só entra a folha que foi lida — ausência não vira zero", () => {
    const lidas = codificacaoDasFolhas(praca([REVISADA, detalhe]), {
      [REVISADA.plate_id]: codes({ confirmed: 4, closed: 3 }),
    });

    expect(lidas).toHaveLength(1);
    expect(lidas[0].plateId).toBe(REVISADA.plate_id);
    expect(lidas[0].confirmed).toBe(4);
    expect(lidas[0].closed).toBe(3);
    expect(lidas[0].pending).toBe(0);
  });

  it("o pendente é o tamanho da lista que o servidor mandou daquela folha", () => {
    const lidas = codificacaoDasFolhas(praca([REVISADA, detalhe]), {
      [REVISADA.plate_id]: codes(),
      detalhe: codes({
        confirmed: 1,
        pending_items: [
          {
            item_id: "ti_1",
            label: "ALAMBRADO",
            raw_text: "ALAMBRADO 40,00 m",
            quantity: "40.00",
            unit: "m",
            note: null,
            status: "confirmed",
          },
        ],
      }),
    });

    expect(lidas.map((item) => item.pending)).toEqual([0, 1]);
    expect(resumoDaCodificacao(lidas[0], 2)).toContain("nada pendente");
    expect(resumoDaCodificacao(lidas[1], 2)).toContain("folha 2 de 2");
    expect(resumoDaCodificacao(lidas[1], 2)).toContain("1 elemento pendente");
  });
});

/**
 * As recusas do vínculo que NÃO dependem do servidor. Nenhuma outra é antecipada: alvo
 * inexistente e cadeia de vínculos são recusas dele, e adivinhá-las aqui seria decidir no
 * lugar dele.
 */
describe("a recusa do vínculo de identidade", () => {
  const primeira = { plate_id: "planta-geral", item_id: "ti_1" };
  const segunda = { plate_id: "detalhe", item_id: "ti_2" };

  it("endereço incompleto pede as duas leituras", () => {
    expect(recusaDoVinculo({ plate_id: "", item_id: "" }, segunda)).toContain(
      "Escolha as duas leituras",
    );
    expect(recusaDoVinculo(primeira, { plate_id: "detalhe", item_id: "" })).toContain(
      "Escolha as duas leituras",
    );
  });

  it("as duas leituras na mesma folha são recusadas antes da viagem", () => {
    const recusa = recusaDoVinculo(primeira, {
      plate_id: "planta-geral",
      item_id: "ti_2",
    });

    expect(recusa).toContain("entre folhas diferentes");
    expect(recusa).toContain("rejeitando um deles na revisão");
  });

  it("par completo em folhas diferentes passa — quem recusa o resto é o servidor", () => {
    expect(recusaDoVinculo(primeira, segunda)).toBeNull();
  });
});
