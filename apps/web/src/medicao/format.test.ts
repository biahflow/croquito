import { describe, expect, it } from "vitest";
import {
  formatDecimalText,
  formatMoneyText,
  formatQuantityText,
  formatTimestamp,
  parseQuantityInput,
  shortDigest,
} from "./format";

describe("formatDecimalText", () => {
  it("troca a pontuação para pt-BR sem mexer na escala escrita", () => {
    expect(formatDecimalText("1234.50")).toBe("1.234,50");
    expect(formatDecimalText("61.20")).toBe("61,20");
    expect(formatDecimalText("18.4")).toBe("18,4");
    expect(formatDecimalText("7")).toBe("7");
  });

  it("agrupa milhar em números longos e preserva o sinal", () => {
    expect(formatDecimalText("36404.07")).toBe("36.404,07");
    expect(formatDecimalText("171025043.01")).toBe("171.025.043,01");
    expect(formatDecimalText("-12.34")).toBe("-12,34");
  });

  it("faz round-trip textual: os dígitos exibidos são os do servidor", () => {
    for (const value of ["0.00", "11.84", "89.30", "1234567.89"]) {
      const shown = formatDecimalText(value);
      const back = shown.replaceAll(".", "").replace(",", ".");
      expect(back).toBe(value);
    }
  });

  it("devolve texto que não é decimal simples sem inventar número", () => {
    expect(formatDecimalText("1,15")).toBe("1,15");
    expect(formatDecimalText("não informado")).toBe("não informado");
    expect(formatDecimalText("1e3")).toBe("1e3");
  });
});

describe("formatMoneyText", () => {
  it("prefixa o símbolo sem recalcular o valor", () => {
    expect(formatMoneyText("8029.44")).toBe("R$ 8.029,44");
  });
});

describe("formatQuantityText", () => {
  it("declara a ausência de quantidade em vez de mostrar zero", () => {
    expect(formatQuantityText(null, "m²")).toBe("sem quantidade legível");
    expect(formatQuantityText("58.50", "m²")).toBe("58,50 m²");
  });
});

describe("parseQuantityInput", () => {
  it("aceita a notação do servidor sem tocar nos dígitos", () => {
    expect(parseQuantityInput("18.40")).toBe("18.40");
    expect(parseQuantityInput(" 61.20 ")).toBe("61.20");
    expect(parseQuantityInput("7")).toBe("7");
  });

  it("aceita a notação pt-BR e converte só a pontuação", () => {
    expect(parseQuantityInput("18,40")).toBe("18.40");
    expect(parseQuantityInput("1.234,50")).toBe("1234.50");
    expect(parseQuantityInput("58,5")).toBe("58.5");
  });

  it("recusa o que não é quantidade escrita, em vez de adivinhar", () => {
    expect(parseQuantityInput("")).toBeNull();
    expect(parseQuantityInput("   ")).toBeNull();
    expect(parseQuantityInput("18,40 m2")).toBeNull();
    expect(parseQuantityInput("1.2.3")).toBeNull();
    expect(parseQuantityInput("-4,5")).toBeNull();
    expect(parseQuantityInput("1e3")).toBeNull();
    expect(parseQuantityInput("cerca de 18")).toBeNull();
  });
});

describe("shortDigest", () => {
  it("encurta o digest e marca a ausência", () => {
    expect(shortDigest("e7c0fb91592e377521e649f6dabd4076")).toBe("e7c0fb91592e");
    expect(shortDigest(null)).toBe("—");
  });
});

describe("formatTimestamp", () => {
  it("devolve o texto original quando não é data reconhecível", () => {
    expect(formatTimestamp("carimbo do servidor")).toBe("carimbo do servidor");
  });

  it("formata data e hora em pt-BR", () => {
    expect(formatTimestamp("2026-03-02T15:30:00Z")).toMatch(
      /^0[12]\/03\/2026 \d{2}:\d{2}$/,
    );
  });
});
