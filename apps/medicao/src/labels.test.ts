import { describe, expect, it } from "vitest";
import {
  assignmentStatusLabel,
  AVISO_FERRAMENTA_LOCAL,
  AVISO_LOCALIZACAO_NAO_CONFIRMADA,
  descricaoCalculoShortlist,
  errorMessage,
  itemStatusLabel,
  recipeLabel,
  unitLabel,
  unitMismatchHint,
} from "./labels";

describe("itemStatusLabel", () => {
  it("escreve o estado por extenso, para que a cor nunca seja o único indicador", () => {
    expect(itemStatusLabel("proposed")).toBe("proposto");
    expect(itemStatusLabel("ambiguous")).toBe("ambíguo");
    expect(itemStatusLabel("confirmed")).toBe("confirmado");
    expect(itemStatusLabel("rejected")).toBe("rejeitado");
  });
});

describe("assignmentStatusLabel", () => {
  it("diz o que a rejeição de código significa na obra", () => {
    expect(assignmentStatusLabel("confirmed")).toBe("código confirmado");
    expect(assignmentStatusLabel("rejected")).toBe("sem código no contrato");
  });
});

describe("unitLabel", () => {
  it("mostra a unidade como a obra a escreve", () => {
    expect(unitLabel("m2")).toBe("m²");
    expect(unitLabel("m3")).toBe("m³");
    expect(unitLabel("m")).toBe("m");
    expect(unitLabel("kg")).toBe("kg");
  });
});

describe("unitMismatchHint", () => {
  it("explica a nota obrigatória com as duas unidades e um exemplo de conversão", () => {
    const hint = unitMismatchHint("m", "m2");

    expect(hint).toContain("unidades diferentes (item em m, código em m²)");
    expect(hint).toContain("registre a conversão");
  });
});

describe("recipeLabel", () => {
  it("traduz a receita do bloco e devolve a chave crua quando não conhece", () => {
    expect(recipeLabel("direct_quantity")).toBe("quantidade direta");
    expect(recipeLabel("perim_height_minus_openings")).toBe(
      "perímetro × altura menos vãos",
    );
    expect(recipeLabel("receita_futura")).toBe("receita_futura");
  });
});

describe("errorMessage", () => {
  it("traduz o código estável da recusa do domínio", () => {
    expect(errorMessage("TAKEOFF_ITEM_ALREADY_REVIEWED")).toBe(
      "Este item já foi decidido; decisão não se sobrescreve.",
    );
    expect(errorMessage("LOCAL_STATE_MOVED")).toContain("recarregue o estado atual");
    expect(errorMessage("ASSIGNMENT_UNIT_INCOMPATIBLE_WITHOUT_NOTE")).toContain(
      "registre a conversão na nota",
    );
  });

  it("acrescenta o detalhe do servidor quando ele diz algo a mais", () => {
    const message = errorMessage(
      "LOCAL_ARTIFACT_MISSING",
      "imagem da prancha do pacote não está no diretório da rodada",
    );

    expect(message).toContain("Um artefato de entrada");
    expect(message).toContain("imagem da prancha do pacote");
  });

  it("fala do artefato genérico nas guardas de digest, que servem a mais de um artefato", () => {
    // O mesmo código cobre confirmações de código e shortlist de sugestões; quem nomeia
    // o artefato é o `detail` do servidor.
    const message = errorMessage(
      "LOCAL_BASE_DIGEST_REQUIRED",
      "já existe shortlist de sugestões; informe o digest-base lido",
    );

    expect(message).toContain("Este artefato da rodada já foi gravado");
    expect(message).toContain("já existe shortlist de sugestões");
    expect(message).not.toContain("conjunto de confirmações nesta rodada");
  });

  it("mostra código e detalhe crus quando o código não tem frase própria", () => {
    expect(errorMessage("CONTRACT_SEMANTICS_DIVERGENT", "histórico não fecha")).toBe(
      "CONTRACT_SEMANTICS_DIVERGENT: histórico não fecha",
    );
    expect(errorMessage("ERRO_SEM_DETALHE")).toBe("ERRO_SEM_DETALHE");
  });

  it("traduz as recusas do upload e da extração automática da prancha", () => {
    expect(errorMessage("LOCAL_ROUND_ALREADY_HAS_PLATE")).toContain(
      "uma rodada é uma prancha",
    );
    expect(errorMessage("LOCAL_EXTRACTION_BUSY")).toContain(
      "existe uma extração automática em andamento",
    );
    expect(errorMessage("LOCAL_EXTRACTION_UNAVAILABLE")).toContain(
      "indisponível no servidor",
    );
    expect(errorMessage("LOCAL_UPLOAD_INVALID")).toContain("não é um PDF de prancha");
  });
});

describe("AVISO_LOCALIZACAO_NAO_CONFIRMADA", () => {
  it("diz para decidir pela lista e pela prancha, sem prometer um retângulo", () => {
    expect(AVISO_LOCALIZACAO_NAO_CONFIRMADA).toContain("não confirmada");
    expect(AVISO_LOCALIZACAO_NAO_CONFIRMADA).toContain("decida pela lista e pela prancha");
  });
});

describe("AVISO_FERRAMENTA_LOCAL", () => {
  it("declara que medir não é aprovar nem exportar", () => {
    expect(AVISO_FERRAMENTA_LOCAL).toContain("medição sem aprovação");
    expect(AVISO_FERRAMENTA_LOCAL).toContain("atos separados");
  });
});

describe("descricaoCalculoShortlist", () => {
  it("com índice disponível, diz que embutir os rótulos é uma chamada paga cacheada", () => {
    const texto = descricaoCalculoShortlist("available");

    expect(texto).toContain("chamada paga");
    expect(texto).toContain("cacheada");
  });

  it("com índice limitado ao cache, não promete gasto nem promete shortlist lexical", () => {
    const texto = descricaoCalculoShortlist("limited");

    expect(texto).toContain("Nenhum provider é chamado");
    // Vetor já cacheado na rodada continua respondendo pelo híbrido: dizer "só lexical"
    // aqui descreveria errado a shortlist que vai sair.
    expect(texto).toContain("vetores já cacheados");
    expect(texto).toContain("sem cache, sai lexical");
  });

  it("sem índice, não promete gasto e diz que a shortlist sai só do léxico", () => {
    const texto = descricaoCalculoShortlist("unavailable");

    expect(texto).toContain("Nenhum provider é chamado");
    expect(texto).toContain("só pelo braço lexical");
  });
});
