import { describe, expect, it } from "vitest";

import {
  avisoDeRevisao,
  corpoDoDespacho,
  gabaritoEscolhido,
  procedenciaDaPlanilha,
  resumoDoArquivo,
  rotuloDoGabarito,
} from "./gabarito";
import type { GabaritoOption } from "./gabarito";

function gabarito(overrides: Partial<GabaritoOption> = {}): GabaritoOption {
  return {
    estimate_template_id: "01930000-0000-7000-8000-0000000000a1",
    name: "PLANILHA ORÇAMENTÁRIA — SMH/Rio",
    template_version: "2023-10",
    origin: "platform",
    source_label: "Prefeitura sintética",
    sheet_name: "PLANILHA ORÇAMENTÁRIA",
    memory_sheet_name: "MEMÓRIA DE CÁLCULO",
    row_count: 433,
    priced_row_count: 433,
    document_sha256: "a".repeat(64),
    ...overrides,
  };
}

describe("o rótulo do gabarito", () => {
  it("traz nome, revisão e tamanho — a revisão junto do nome, sempre", () => {
    expect(rotuloDoGabarito(gabarito())).toBe(
      "PLANILHA ORÇAMENTÁRIA — SMH/Rio · rev. 2023-10 · 433 linhas",
    );
  });

  it("uma linha não vira “1 linhas”", () => {
    expect(rotuloDoGabarito(gabarito({ row_count: 1 }))).toContain("· 1 linha");
  });
});

describe("o aviso de revisão", () => {
  it("nomeia a revisão e pede confirmação a quem entrega", () => {
    const aviso = avisoDeRevisao(gabarito());
    expect(aviso).toContain("2023-10");
    expect(aviso).toContain("quem entrega à prefeitura");
  });

  it("sem gabarito não há aviso: não há revisão a confirmar", () => {
    expect(avisoDeRevisao(null)).toBeNull();
  });

  it("a tela NÃO decide que uma revisão está velha — o aviso vale para toda escolha", () => {
    // Duas revisões do mesmo gabarito, e as duas avisam. Eleger a "mais nova" seria a
    // máquina decidindo o que é ato de quem entrega à prefeitura.
    const antiga = avisoDeRevisao(gabarito({ template_version: "2023-10" }));
    const nova = avisoDeRevisao(gabarito({ template_version: "2026-08" }));
    expect(antiga).not.toBeNull();
    expect(nova).not.toBeNull();
  });
});

describe("o resumo do que vai no arquivo", () => {
  it("conta linhas e nomeia as duas abas, sem somar nada", () => {
    const resumo = resumoDoArquivo(gabarito({ row_count: 433, priced_row_count: 43 }));
    expect(resumo.totalDeLinhas).toBe(433);
    expect(resumo.comPreco).toBe(43);
    expect(resumo.abas).toEqual(["PLANILHA ORÇAMENTÁRIA", "MEMÓRIA DE CÁLCULO"]);
  });
});

describe("a escolha", () => {
  const lista = [gabarito(), gabarito({ estimate_template_id: "outro", name: "OUTRO" })];

  it("string vazia é “sem gabarito”, e é opção de primeira classe", () => {
    expect(gabaritoEscolhido(lista, "")).toBeNull();
  });

  it("id desconhecido não escolhe nada, em vez de escolher o primeiro", () => {
    expect(gabaritoEscolhido(lista, "nao-existe")).toBeNull();
  });

  it("id conhecido escolhe o gabarito daquele id", () => {
    expect(gabaritoEscolhido(lista, "outro")?.name).toBe("OUTRO");
  });
});

describe("o corpo do despacho", () => {
  it("sem gabarito, o corpo é o de sempre — nenhum campo novo viaja", () => {
    const corpo = corpoDoDespacho(7, null);
    expect(corpo).toEqual({ base_version: 7 });
    expect(corpo).not.toHaveProperty("estimate_template_id");
  });

  it("com gabarito, viaja o id — nunca a revisão, que o servidor lê do documento", () => {
    const corpo = corpoDoDespacho(7, gabarito());
    expect(corpo).toEqual({
      base_version: 7,
      estimate_template_id: "01930000-0000-7000-8000-0000000000a1",
    });
    expect(corpo).not.toHaveProperty("template_version");
  });
});

describe("a procedência da planilha publicada", () => {
  it("sem carimbo, DIZ que saiu sem gabarito — ausência é afirmação, não silêncio", () => {
    expect(procedenciaDaPlanilha(null)).toContain("sem gabarito");
    expect(procedenciaDaPlanilha(undefined)).toContain("na ordem do próprio orçamento");
  });

  it("com carimbo, nomeia o gabarito e a revisão que geraram o arquivo", () => {
    const texto = procedenciaDaPlanilha({
      estimate_template_id: "x",
      name: "PLANILHA ORÇAMENTÁRIA — SMH/Rio",
      template_version: "2023-10",
      document_sha256: "a".repeat(64),
    });
    expect(texto).toContain("PLANILHA ORÇAMENTÁRIA — SMH/Rio");
    expect(texto).toContain("2023-10");
  });
});
