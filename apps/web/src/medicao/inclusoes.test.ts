import { describe, expect, it } from "vitest";
import { extractInclusoes } from "./inclusoes";

describe("extractInclusoes", () => {
  it("BP09200350: extrai o inclusive corrido e a frase fixa de materiais e equipamentos", () => {
    const description =
      'com todos os materiais e equipamentos, inclusive compactação com soquete ' +
      'vibratório, corte dos blocos para arremate, com máquina de juntas (serra para ' +
      'concreto) e "colchão" de areia para assentamento e rejuntamento, de acordo com ' +
      "o projeto";

    const inclusoes = extractInclusoes(description);

    const clausula = inclusoes.find(
      (item) => item.kind === "inclui" && item.text.includes('"colchão" de areia'),
    );
    expect(clausula).toBeDefined();

    const materiais = inclusoes.find(
      (item) =>
        item.kind === "inclui" &&
        item.text === "com todos os materiais e equipamentos",
    );
    expect(materiais).toBeDefined();
  });

  it("PJ04100100(A): 'inclusive' captura o trecho inteiro até o ponto, sem '(desonerado)'", () => {
    const description =
      "GRAMA ESMERALDA. inclusive o fornecimento da grama, terra preta, preparo de " +
      "terreno e calagem.(desonerado)";

    const inclusoes = extractInclusoes(description);

    expect(inclusoes).toEqual([
      {
        kind: "inclui",
        text: "o fornecimento da grama, terra preta, preparo de terreno e calagem",
      },
    ]);
  });

  it("RV14250103(A): 'exclusive' vira não inclui, sem '(desonerado)'", () => {
    const description = "MURETA DE ARREMATE. exclusive preparo de terreno.(desonerado)";

    const inclusoes = extractInclusoes(description);

    expect(inclusoes).toEqual([{ kind: "nao_inclui", text: "preparo de terreno" }]);
  });

  it("RV14250100(C): 'inclusive preparo manual do terreno.' vira inclui", () => {
    const description = "PLANTIO DE GRAMA. inclusive preparo manual do terreno.";

    const inclusoes = extractInclusoes(description);

    expect(inclusoes).toEqual([{ kind: "inclui", text: "preparo manual do terreno" }]);
  });

  it("PJ24050153(B): 'Fornecimento e colocação.' vira inclui com rótulo fixo, não so_fornecimento", () => {
    const description = "BANCO DE CONCRETO. Fornecimento e colocação.(desonerado)";

    const inclusoes = extractInclusoes(description);

    expect(inclusoes).toEqual([{ kind: "inclui", text: "fornecimento e colocação" }]);
    expect(inclusoes.some((item) => item.kind === "so_fornecimento")).toBe(false);
  });

  it("PJ14050160(/): 'Fornecimento.' sem marcador de execução vira so_fornecimento", () => {
    const description = "MOURÃO DE CONCRETO. Fornecimento.(desonerado)";

    const inclusoes = extractInclusoes(description);

    expect(inclusoes).toEqual([{ kind: "so_fornecimento" }]);
  });

  it("descrição sem marcador conhecido devolve lista vazia", () => {
    expect(extractInclusoes("LUMINARIA DUPLA SINTETICA")).toEqual([]);
  });

  it("dedupe: 'Fornecimento e colocação' duas vezes na descrição vira um único chip", () => {
    const description =
      "PISO CIMENTÍCIO. Fornecimento e colocação. Observação: fornecimento e " +
      "colocação conforme projeto.";

    const inclusoes = extractInclusoes(description);

    expect(inclusoes).toEqual([{ kind: "inclui", text: "fornecimento e colocação" }]);
  });

  it("dedupe: duas cláusulas 'inclusive' com o mesmo trecho literal viram um único chip", () => {
    const description = "inclusive compactação; inclusive compactação.";

    const inclusoes = extractInclusoes(description);

    expect(inclusoes).toEqual([{ kind: "inclui", text: "compactação" }]);
  });

  it("cobre múltiplas ocorrências distintas de inclusive e exclusive na mesma descrição", () => {
    const description =
      "SERVIÇO COMPOSTO. inclusive transporte do material; exclusive preparo de base.";

    const inclusoes = extractInclusoes(description);

    expect(inclusoes).toEqual([
      { kind: "inclui", text: "transporte do material" },
      { kind: "nao_inclui", text: "preparo de base" },
    ]);
  });

  it("ignora acento e caixa ao procurar 'fornecimento e colocação'", () => {
    const inclusoes = extractInclusoes("FORNECIMENTO E COLOCACAO DE GRELHA.");

    expect(inclusoes).toEqual([{ kind: "inclui", text: "fornecimento e colocação" }]);
  });

  it("remove o parêntese de fechamento solto quando o recorte começa depois do '(' de abertura", () => {
    const description = "Programador de computador (inclusive encargos sociais).(desonerado)";

    const inclusoes = extractInclusoes(description);

    expect(inclusoes).toEqual([{ kind: "inclui", text: "encargos sociais" }]);
  });

  it("contra-teste: par de parênteses completo dentro do trecho fica intacto", () => {
    const description = "ADUBAÇÃO DE PLANTIO. inclusive adubo NPK (NPK-04-14-08).";

    const inclusoes = extractInclusoes(description);

    expect(inclusoes).toEqual([
      { kind: "inclui", text: "adubo NPK (NPK-04-14-08)" },
    ]);
  });
});
