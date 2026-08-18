import { describe, expect, it } from "vitest";
import { classifyExecucao } from "./execucao";

describe("classifyExecucao", () => {
  it("lê 'Fornecimento e colocação' como execução incluída", () => {
    const hint = classifyExecucao(
      "BANCO DE CONCRETO PRE-MOLDADO, COM ENCOSTO. Fornecimento e colocação.(desonerado)",
    );

    expect(hint.kind).toBe("execucao_incluida");
    expect(hint.label).toBe("execução incluída");
    expect(hint.marker).toBe("fornecimento e colocacao");
  });

  it("lê 'Fornecimento.' sem marcador de execução como somente material", () => {
    const hint = classifyExecucao(
      "MOURAO DE CONCRETO ARMADO, SECAO 10X10CM. Fornecimento. (desonerado)",
    );

    expect(hint.kind).toBe("somente_material");
    expect(hint.marker).toBe("fornecimento");
  });

  it("lê composição que começa por 'Execução de' como execução incluída", () => {
    const hint = classifyExecucao(
      "Execução de pavimentação em piso intertravado de concreto, e=6cm.",
    );

    expect(hint.kind).toBe("execucao_incluida");
    expect(hint.marker).toBe("execucao de");
  });

  it("ignora acento e caixa ao procurar o marcador", () => {
    expect(classifyExecucao("FORNECIMENTO E COLOCAÇÃO DE GRELHA").kind).toBe(
      "execucao_incluida",
    );
    expect(classifyExecucao("EXECUCAO DE MURETA EM ALVENARIA").kind).toBe(
      "execucao_incluida",
    );
  });

  it("trata plantio e 'inclusive' como serviço, mesmo com fornecimento na frase", () => {
    expect(
      classifyExecucao("GRAMA ESMERALDA EM PLACAS. Fornecimento e plantio.").kind,
    ).toBe("execucao_incluida");
    expect(
      classifyExecucao("ALAMBRADO EM TELA GALVANIZADA, inclusive montagem.").kind,
    ).toBe("execucao_incluida");
  });

  it("declara indefinido quando a frase não tem marcador conhecido", () => {
    const hint = classifyExecucao("LUMINARIA DUPLA SINTETICA");

    expect(hint.kind).toBe("indefinido");
    expect(hint.marker).toBeNull();
    expect(hint.label).toBe("escopo não declarado");
  });

  it("assume a natureza de dica em toda explicação: a decisão continua sendo humana", () => {
    const descriptions = [
      "PISO. Fornecimento e colocação.",
      "PISO. Fornecimento.",
      "PISO INTERTRAVADO SINTETICO 6CM CINZA",
    ];

    for (const description of descriptions) {
      expect(classifyExecucao(description).explanation).toContain("descrição completa");
    }
  });
});
