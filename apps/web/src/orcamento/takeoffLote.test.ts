import { describe, expect, it } from "vitest";

import { AVISO_AMBIGUO_FORA_DO_LOTE, AVISO_ITEM_JA_REVISADO } from "./labels";
import { takeoffDecisionBody } from "./requests";
import {
  avisoDeAnotacaoEmMassa,
  CAMPOS_VAZIOS,
  itemJaRevisado,
  montarAnotacao,
  motivoNaoMarcavel,
  rotuloAnotarEmMassa,
} from "./takeoffLote";
import type { TakeoffItem } from "./api";

/** Item do pacote, no mínimo que estas regras leem. */
const item = (
  id: string,
  status: string,
  quantity: string | null = "418.12",
): TakeoffItem =>
  ({
    id,
    label: "PISO EM CONCRETO",
    quantity,
    unit: "m2",
    status,
  }) as unknown as TakeoffItem;

describe("itemJaRevisado", () => {
  it("reconhece o item já decidido, confirmado ou rejeitado", () => {
    expect(itemJaRevisado(item("i1", "confirmed"))).toBe(true);
    expect(itemJaRevisado(item("i2", "rejected"))).toBe(true);
  });

  it("item proposto ou ambíguo ainda não foi decidido", () => {
    expect(itemJaRevisado(item("i3", "proposed"))).toBe(false);
    expect(itemJaRevisado(item("i4", "ambiguous", null))).toBe(false);
    expect(itemJaRevisado(null)).toBe(false);
  });
});

describe("motivoNaoMarcavel", () => {
  it("item proposto entra na marcação em massa", () => {
    expect(motivoNaoMarcavel(item("i1", "proposed"))).toBeNull();
  });

  /** Decisão não se sobrescreve, e o lote é atômico: ele derrubaria as outras decisões. */
  it("item já revisado fica de fora, e diz por quê", () => {
    expect(motivoNaoMarcavel(item("i2", "confirmed"))).toBe(AVISO_ITEM_JA_REVISADO);
    expect(motivoNaoMarcavel(item("i3", "rejected"))).toBe(AVISO_ITEM_JA_REVISADO);
  });

  /** Confirmar em massa é confirmar a quantidade lida; no ambíguo não há quantidade lida. */
  it("item ambíguo fica de fora, com a razão própria dele", () => {
    const motivo = motivoNaoMarcavel(item("i4", "ambiguous", null));
    expect(motivo).toBe(AVISO_AMBIGUO_FORA_DO_LOTE);
    expect(motivo).not.toBe(AVISO_ITEM_JA_REVISADO);
  });
});

describe("montarAnotacao", () => {
  /**
   * O caminho da marcação em massa: confirma a quantidade que a legenda diz, e por isso
   * NÃO carrega quantidade nem unidade — mandá-las seria a tela reescrevendo o dado lido.
   */
  it("sem nada escrito, confirma o item sem corrigir quantidade nem unidade", () => {
    const montagem = montarAnotacao(item("i1", "proposed"), "confirm", CAMPOS_VAZIOS);

    expect(montagem.recusa).toBeNull();
    expect(montagem.anotacao).toEqual({
      itemId: "i1",
      action: "confirm",
      quantity: undefined,
      unit: undefined,
      note: undefined,
      itemNote: undefined,
    });
  });

  /** O corpo que viaja não leva campo ausente como string vazia. */
  it("a anotação em massa vira um corpo com item e ação, e mais nada", () => {
    const montagem = montarAnotacao(item("i1", "proposed"), "confirm", CAMPOS_VAZIOS);
    const corpo = takeoffDecisionBody({
      baseVersion: 7,
      decisions: montagem.anotacao === null ? [] : [montagem.anotacao],
    });

    expect(corpo).toEqual({
      base_version: 7,
      decisions: [{ item_id: "i1", action: "confirm" }],
    });
  });

  it("quantidade escrita em pt-BR viaja como decimal do servidor", () => {
    const montagem = montarAnotacao(item("i1", "proposed"), "confirm", {
      ...CAMPOS_VAZIOS,
      quantity: "418,12",
      unit: " m2 ",
      note: "conferido contra a prancha",
    });

    expect(montagem.anotacao?.quantity).toBe("418.12");
    expect(montagem.anotacao?.unit).toBe("m2");
    expect(montagem.anotacao?.note).toBe("conferido contra a prancha");
  });

  it("quantidade que não é decimal recusa a anotação inteira", () => {
    const montagem = montarAnotacao(item("i1", "proposed"), "confirm", {
      ...CAMPOS_VAZIOS,
      quantity: "quatrocentos",
    });

    expect(montagem.anotacao).toBeNull();
    expect(montagem.recusa).toContain("nada foi anotado");
  });

  it("item já revisado não vira anotação nenhuma", () => {
    const montagem = montarAnotacao(item("i2", "confirmed"), "confirm", CAMPOS_VAZIOS);

    expect(montagem.anotacao).toBeNull();
    expect(montagem.recusa).toBe(AVISO_ITEM_JA_REVISADO);
  });

  it("rejeitar é a mesma montagem, com a ação declarada", () => {
    const montagem = montarAnotacao(item("i1", "proposed"), "reject", {
      ...CAMPOS_VAZIOS,
      note: "não existe no desenho",
    });

    expect(montagem.anotacao?.action).toBe("reject");
    expect(montagem.anotacao?.note).toBe("não existe no desenho");
  });
});

describe("rotuloAnotarEmMassa e avisoDeAnotacaoEmMassa", () => {
  it("uma marcada fala no singular", () => {
    expect(rotuloAnotarEmMassa(1)).toBe("Anotar 1 como confirmado");
    expect(avisoDeAnotacaoEmMassa(1)).toContain("1 decisão anotada");
  });

  it("mais de uma fala no plural", () => {
    expect(rotuloAnotarEmMassa(3)).toBe("Anotar 3 como confirmados");
    expect(avisoDeAnotacaoEmMassa(3)).toContain("3 decisões anotadas");
  });

  /** "Anotado" não é "gravado", e o aviso não pode deixar a dúvida. */
  it("o aviso diz que gravar ainda não aconteceu", () => {
    expect(avisoDeAnotacaoEmMassa(3)).toContain("ainda não foram gravadas");
    expect(avisoDeAnotacaoEmMassa(1)).toContain("ainda não foi gravada");
  });
});
