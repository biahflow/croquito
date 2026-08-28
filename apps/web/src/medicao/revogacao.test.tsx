import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { CaixaDeDesfazerCodigo, ListaDeDesfeitos } from "./MedicaoApp";
import { codeRevocationBody } from "./requests";
import { abrirDesfazer, pedidoDeDesfazer } from "../codeRevocation";

/**
 * Desfazer um código confirmado na jornada de MEDIÇÃO (F-045, pacote de design revisão 2).
 *
 * O módulo puro é o mesmo do orçamento-base e está testado em `src/codeRevocation.test.tsx`;
 * o que se prova aqui é o que é DESTA jornada: a copy sem a linha do precedente, o transporte
 * e os dois componentes.
 */

const ITEM = "ti_0000000000000001";
const CODE = "CE04100010(/)";

describe("a caixa da medição", () => {
  it("pede o motivo e escreve o efeito — SEM prometer o precedente", () => {
    const html = renderToStaticMarkup(
      <CaixaDeDesfazerCodigo
        caixa={abrirDesfazer(ITEM, CODE)}
        pacoteFechado={false}
        submitting={false}
        onChange={() => undefined}
        onDesfazer={() => undefined}
        onCancelar={() => undefined}
      />,
    );

    expect(html).toContain("Desfazer CE04100010(/)");
    expect(html).toContain("(obrigatório)");
    expect(html).toContain("tira CE04100010(/) do pacote deste item");
    expect(html).toContain("a confirmação continua na revisão anterior");
    // A linha do precedente é do orçamento-base: aqui ela seria uma promessa falsa.
    expect(html).not.toContain("precedente");
    // Sem motivo, o botão que grava fica desabilitado.
    expect(html.match(/disabled=""/g)?.length).toBe(1);
  });

  it("com o pacote fechado, avisa que reabre e que o boletim recusa o item", () => {
    const html = renderToStaticMarkup(
      <CaixaDeDesfazerCodigo
        caixa={{ ...abrirDesfazer(ITEM, CODE), motivo: "confirmei o código errado" }}
        pacoteFechado
        submitting={false}
        onChange={() => undefined}
        onDesfazer={() => undefined}
        onCancelar={() => undefined}
      />,
    );

    expect(html).toContain("Desfazer e reabrir o pacote");
    expect(html).toContain("o boletim recusa este item");
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

describe("a lista de desfeitos da medição", () => {
  it("mostra o código riscado, o selo escrito e o motivo", () => {
    const html = renderToStaticMarkup(
      <ListaDeDesfeitos
        desfeitos={[
          {
            item_id: ITEM,
            code: CODE,
            revocation_id: "vr_0000000000000001",
            reviewer_id: "orcamentista",
            revoked_at: "2026-08-28T13:00:00Z",
            note: "confirmei o código errado neste item",
          },
        ]}
      />,
    );

    expect(html).toContain("Desfeitos neste item");
    expect(html).toContain("codigo-desfeito");
    expect(html).toContain("desfeito");
    expect(html).toContain("confirmei o código errado neste item");
  });

  it("não desenha nada quando não há desfeito", () => {
    expect(renderToStaticMarkup(<ListaDeDesfeitos desfeitos={[]} />)).toBe("");
  });
});

describe("o transporte da medição", () => {
  it("manda o par, a versão-base e o motivo aparado", () => {
    const pedido = pedidoDeDesfazer(
      { ...abrirDesfazer(ITEM, CODE), motivo: "  não é deste item  " },
      9,
    );

    expect(codeRevocationBody(pedido)).toEqual({
      base_version: 9,
      item_id: ITEM,
      code: CODE,
      note: "não é deste item",
    });
  });
});
