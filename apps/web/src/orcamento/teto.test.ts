import { describe, expect, it } from "vitest";

import {
  derivarTeto,
  ehZeroDecimal,
  percentualDoTeto,
  semSinal,
} from "./teto";

/**
 * A comparação é do servidor (ADR-0040, decisão 2) e chega derivada; o que se testa aqui é
 * que a tela **não a refaz** — nem o estado, nem os valores em reais.
 */
describe("derivarTeto", () => {
  const dentro = {
    target: { amount: "95000.00", label: "Relação de Praças 2026 · demanda 14" },
    consumed: "91996.44",
    remaining: "3003.56",
    over: false,
  };

  it("dentro do teto: restante positivo, sem excedente e com o rótulo da demanda", () => {
    const teto = derivarTeto(dentro);

    expect(teto).not.toBeNull();
    expect(teto?.estado).toBe("dentro");
    expect(teto?.restante).toBe("3003.56");
    expect(teto?.excedente).toBeNull();
    expect(teto?.percentualAcima).toBeNull();
    expect(teto?.rotulo).toBe("Relação de Praças 2026 · demanda 14");
    // Os valores em reais saem exatamente como o servidor os escreveu.
    expect(teto?.teto).toBe("95000.00");
    expect(teto?.consumo).toBe("91996.44");
  });

  /** Consumir o teto inteiro é estar DENTRO dele (ADR-0040, decisão 3). */
  it("limite exato é estado próprio na palavra, mas não é estouro", () => {
    const teto = derivarTeto({
      target: { amount: "91996.44", label: null },
      consumed: "91996.44",
      remaining: "0.00",
      over: false,
    });

    expect(teto?.estado).toBe("limite");
    expect(teto?.restante).toBe("0.00");
    expect(teto?.excedente).toBeNull();
    expect(teto?.percentualConsumido).toBe("100.00");
  });

  it("estourado: o excedente é o restante negativo sem o sinal, e nada é recalculado", () => {
    const teto = derivarTeto({
      target: { amount: "85000.00", label: "Relação de Praças 2026 · demanda 14" },
      consumed: "91996.44",
      remaining: "-6996.44",
      over: true,
    });

    expect(teto?.estado).toBe("estourado");
    expect(teto?.excedente).toBe("6996.44");
    expect(teto?.restante).toBeNull();
    expect(teto?.percentualConsumido).toBe("108.23");
    expect(teto?.percentualAcima).toBe("8.23");
  });

  /**
   * `over` é a autoridade: mesmo restante zero, um `over` verdadeiro continua estouro. A
   * tela não recompara centavos para "corrigir" o servidor.
   */
  it("o estado vem de `over`, nunca de uma comparação refeita na tela", () => {
    const teto = derivarTeto({
      target: { amount: "100.00", label: null },
      consumed: "100.00",
      remaining: "0.00",
      over: true,
    });

    expect(teto?.estado).toBe("estourado");
  });

  it("rodada sem teto não tem bloco nenhum a mostrar", () => {
    expect(derivarTeto({})).toBeNull();
    expect(derivarTeto(null)).toBeNull();
    expect(derivarTeto(undefined)).toBeNull();
  });

  /** Teto declarado antes de montar: o servidor manda só `target`, e não há consumo. */
  it("com teto e sem orçamento montado, ainda não há consumo a comparar", () => {
    expect(
      derivarTeto({ target: { amount: "85000.00", label: null } }),
    ).toBeNull();
  });

  it("rótulo ausente não vira rótulo em branco", () => {
    expect(derivarTeto({ ...dentro, target: { amount: "1.00", label: null } })?.rotulo).toBeNull();
  });
});

/**
 * O percentual é o ÚNICO número que a tela calcula, e o pacote de design aprovado prevê
 * esse caminho ("na tela, a partir dos dois valores já truncados"). Ele é razão, não
 * dinheiro — e mesmo assim não passa por `float`.
 */
describe("percentualDoTeto", () => {
  it("trunca na segunda casa, como o domínio trunca no centavo", () => {
    // 91996.44 / 95000.00 = 96,8383…% — a terceira casa não vira arredondamento.
    expect(percentualDoTeto("91996.44", "95000.00")).toBe("96.83");
    expect(percentualDoTeto("91996.44", "85000.00")).toBe("108.23");
    expect(percentualDoTeto("6996.44", "85000.00")).toBe("8.23");
  });

  it("escalas diferentes dos dois lados não se perdem", () => {
    expect(percentualDoTeto("50", "200.0000")).toBe("25.00");
    expect(percentualDoTeto("1.5", "3")).toBe("50.00");
  });

  it("valor exato devolve o percentual exato", () => {
    expect(percentualDoTeto("85000.00", "85000.00")).toBe("100.00");
    expect(percentualDoTeto("0.00", "85000.00")).toBe("0.00");
  });

  /** Teto zero ou texto ilegível não viram número fabricado. */
  it("sem divisão possível, não inventa percentual", () => {
    expect(percentualDoTeto("10.00", "0.00")).toBeNull();
    expect(percentualDoTeto("dez mil", "85000.00")).toBeNull();
    expect(percentualDoTeto("10.00", "oitenta mil")).toBeNull();
    expect(percentualDoTeto("-10.00", "85000.00")).toBeNull();
  });

  /**
   * Valores grandes: `BigInt` não perde dígito onde `Number` já teria perdido. O teto de
   * uma demanda inteira em centavos passa longe do seguro do ponto flutuante.
   */
  it("não perde precisão em valor grande", () => {
    expect(
      percentualDoTeto("9007199254740993.01", "9007199254740993.01"),
    ).toBe("100.00");
  });
});

describe("ehZeroDecimal", () => {
  it("reconhece zero em qualquer escala", () => {
    for (const texto of ["0", "0.0", "0.00", "-0.00", "00.000"]) {
      expect(ehZeroDecimal(texto)).toBe(true);
    }
  });

  it("não confunde zero com valor escrito nem com texto ilegível", () => {
    for (const texto of ["0.01", "-0.01", "1", "", "zero"]) {
      expect(ehZeroDecimal(texto)).toBe(false);
    }
  });
});

describe("semSinal", () => {
  it("tira o sinal sem tocar em um dígito sequer", () => {
    expect(semSinal("-6996.44")).toBe("6996.44");
    expect(semSinal("6996.44")).toBe("6996.44");
    expect(semSinal("-0.00")).toBe("0.00");
  });
});
