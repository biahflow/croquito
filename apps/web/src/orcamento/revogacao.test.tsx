import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import type { CodeAssignmentSet } from "@croquito/contracts";

import {
  abrirDesfazer,
  desfazerDoItem,
  desfeitosDoItem,
  pacoteFechado,
  pedidoDeDesfazer,
  podeDesfazer,
} from "./revogacao";
import { codeRevocationBody } from "./requests";
import { CaixaDeDesfazerCodigo, ListaDeDesfeitos } from "./OrcamentoApp";

/**
 * Desfazer um código confirmado (F-045), contra o pacote de design revisão 1 e o ADR-0061.
 *
 * Rótulos, códigos e motivos daqui são SINTÉTICOS: nenhum dado de praça real entra em testes.
 */

const ITEM = "ti_0000000000000001";
const OUTRO_ITEM = "ti_0000000000000002";
const PISO = "BP09100050(B)";
const TELA = "ET39050109(/)";

function conjunto(
  overrides: Partial<CodeAssignmentSet.CroquitoCodeAssignmentSet> = {},
): CodeAssignmentSet.CroquitoCodeAssignmentSet {
  return {
    schema_version: "2.0.0",
    plate_id: "PR-01",
    page_number: 1,
    image_sha256: "a".repeat(64),
    catalog_sha256: "b".repeat(64),
    assignments: [
      {
        item_id: ITEM,
        status: "confirmed",
        code: PISO,
        unit_compatible: true,
        decision: {
          decision_id: "vd_0000000000000001",
          action: "confirm",
          reviewer_id: "orcamentista",
          reviewer_role: "orcamentista",
          decided_at: "2026-08-28T12:00:00Z",
        },
      },
    ],
    closures: [],
    revocations: [],
    safety_notes: ["nota um", "nota dois"],
    ...overrides,
  } as CodeAssignmentSet.CroquitoCodeAssignmentSet;
}

const DESFEITO = {
  item_id: ITEM,
  code: TELA,
  revocation_id: "vr_0000000000000001",
  reviewer_id: "orcamentista",
  reviewer_role: "orcamentista",
  revoked_at: "2026-08-28T13:00:00Z",
  note: "entrou junto no aceite do precedente e não é desta praça",
};

describe("a caixa de desfazer", () => {
  it("nasce sem motivo, e sem motivo não há pedido", () => {
    const caixa = abrirDesfazer(ITEM, PISO);

    expect(caixa.motivo).toBe("");
    expect(podeDesfazer(caixa)).toBe(false);
    // Espaço em branco não é motivo.
    expect(podeDesfazer({ ...caixa, motivo: "   " })).toBe(false);
    expect(podeDesfazer({ ...caixa, motivo: "não é desta praça" })).toBe(true);
  });

  it("some quando o elemento aberto é outro", () => {
    const caixa = abrirDesfazer(ITEM, PISO);

    expect(desfazerDoItem(caixa, ITEM)).toBe(caixa);
    expect(desfazerDoItem(caixa, OUTRO_ITEM)).toBeNull();
    expect(desfazerDoItem(caixa, "")).toBeNull();
    expect(desfazerDoItem(null, ITEM)).toBeNull();
  });

  it("vira um pedido com o par, a versão-base e o motivo aparado", () => {
    const pedido = pedidoDeDesfazer(
      { ...abrirDesfazer(ITEM, PISO), motivo: "  não é desta praça  " },
      7,
    );

    expect(pedido).toEqual({
      itemId: ITEM,
      code: PISO,
      baseVersion: 7,
      note: "não é desta praça",
    });
    expect(codeRevocationBody(pedido)).toEqual({
      base_version: 7,
      item_id: ITEM,
      code: PISO,
      note: "não é desta praça",
    });
  });
});

describe("a caixa desenhada", () => {
  it("pede o motivo, escreve o efeito e não grava sem justificativa", () => {
    const html = renderToStaticMarkup(
      <CaixaDeDesfazerCodigo
        caixa={abrirDesfazer(ITEM, PISO)}
        pacoteFechado={false}
        submitting={false}
        onChange={() => undefined}
        onDesfazer={() => undefined}
        onCancelar={() => undefined}
      />,
    );

    expect(html).toContain("Desfazer BP09100050(B)");
    expect(html).toContain("(obrigatório)");
    // As três linhas do efeito, inclusive a que ninguém adivinharia sozinho.
    expect(html).toContain("tira BP09100050(B) do pacote deste elemento");
    expect(html).toContain("a confirmação continua na revisão anterior");
    expect(html).toContain("apaga o precedente que este código deixou");
    expect(html).toContain("Desfazer não bane o código");
    // Sem motivo, o botão que grava está desabilitado.
    expect(html).toMatch(/Desfazer o código<\/button>/);
    expect(html.match(/disabled=""/g)?.length).toBe(1);
  });

  it("com o pacote fechado, avisa que reabre — e o botão diz isso", () => {
    const html = renderToStaticMarkup(
      <CaixaDeDesfazerCodigo
        caixa={{ ...abrirDesfazer(ITEM, PISO), motivo: "não é desta praça" }}
        pacoteFechado
        submitting={false}
        onChange={() => undefined}
        onDesfazer={() => undefined}
        onCancelar={() => undefined}
      />,
    );

    expect(html).toContain("Desfazer e reabrir o pacote");
    expect(html).toContain("a exportação do orçamento recusa este elemento");
    expect(html).not.toContain("disabled");
  });

  it("não desenha nada sem clique", () => {
    expect(
      renderToStaticMarkup(
        <CaixaDeDesfazerCodigo
          caixa={null}
          pacoteFechado={false}
          submitting={false}
          onChange={() => undefined}
          onDesfazer={() => undefined}
          onCancelar={() => undefined}
        />,
      ),
    ).toBe("");
  });
});

describe("o que foi desfeito continua à vista", () => {
  it("lista o par desfeito com motivo, autor e instante", () => {
    const desfeitos = desfeitosDoItem(
      conjunto({ revocations: [DESFEITO] } as never),
      ITEM,
    );

    expect(desfeitos.map((item) => item.code)).toEqual([TELA]);
    const html = renderToStaticMarkup(<ListaDeDesfeitos desfeitos={desfeitos} />);
    expect(html).toContain("Desfeitos neste elemento");
    expect(html).toContain(TELA);
    expect(html).toContain("desfeito");
    expect(html).toContain("entrou junto no aceite do precedente");
  });

  /** Desfazer não bane: o par reconfirmado voltou a valer e sai da lista. */
  it("o par que voltou a ser confirmado não aparece como desfeito", () => {
    const reconfirmado = conjunto({
      revocations: [{ ...DESFEITO, code: PISO }],
    } as never);

    expect(desfeitosDoItem(reconfirmado, ITEM)).toEqual([]);
  });

  it("não desenha nada quando não há desfeito nenhum", () => {
    expect(desfeitosDoItem(conjunto(), ITEM)).toEqual([]);
    expect(desfeitosDoItem(null, ITEM)).toEqual([]);
    expect(renderToStaticMarkup(<ListaDeDesfeitos desfeitos={[]} />)).toBe("");
  });

  it("o desfeito de outro elemento não vaza para este", () => {
    const conjunto_ = conjunto({
      revocations: [{ ...DESFEITO, item_id: OUTRO_ITEM }],
    } as never);

    expect(desfeitosDoItem(conjunto_, ITEM)).toEqual([]);
    expect(desfeitosDoItem(conjunto_, OUTRO_ITEM).map((item) => item.code)).toEqual([TELA]);
  });
});

describe("o pacote fechado", () => {
  it("é reconhecido pelo fechamento gravado, e só dele", () => {
    expect(pacoteFechado(conjunto(), ITEM)).toBe(false);
    expect(
      pacoteFechado(
        conjunto({
          closures: [
            {
              item_id: ITEM,
              decision: {
                decision_id: "vd_0000000000000002",
                action: "confirm",
                reviewer_id: "orcamentista",
                reviewer_role: "orcamentista",
                decided_at: "2026-08-28T12:30:00Z",
              },
            },
          ],
        } as never),
        ITEM,
      ),
    ).toBe(true);
    expect(pacoteFechado(null, ITEM)).toBe(false);
  });
});
