import { describe, expect, it } from "vitest";
import {
  assignmentStatusLabel,
  AVISO_EXPORTACAO_FAIL_CLOSED,
  AVISO_LOCALIZACAO_NAO_CONFIRMADA,
  AVISO_MEDICAO,
  DESCRICAO_CALCULO_SHORTLIST,
  errorMessage,
  extractionFailureMessage,
  extractionStatusLabel,
  itemStatusLabel,
  MENSAGEM_APROVACAO_CADUCA,
  MENSAGEM_AUDITORIA_REPROVADA,
  MENSAGEM_RODADA_MUDOU,
  MENSAGEM_SEM_ACESSO,
  recipeLabel,
  stageLabel,
  unitLabel,
  unitMismatchHint,
  violationDetailLine,
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
    expect(errorMessage("ASSIGNMENT_UNIT_INCOMPATIBLE_WITHOUT_NOTE")).toContain(
      "registre a conversão na nota",
    );
    expect(errorMessage("CALC_ASSIGNMENT_MISSING")).toContain(
      "não é montado pela metade",
    );
  });

  it("o nome que não cabe na aba diz o que fazer e traz o teto do servidor", () => {
    const message = errorMessage(
      "WORKSITE_NAME_DOES_NOT_FIT_SHEET",
      "o nome da obra não cabe no nome da aba nem na forma curta; encurte o nome da obra "
        + "para no máximo 23 caracteres",
    );

    expect(message).toContain("encurte o nome da praça");
    // O teto é do SERVIDOR e chega no detalhe: a frase da tela não o repete de cabeça.
    expect(message).toContain("23 caracteres");
    expect(message).not.toContain("WORKSITE_NAME_DOES_NOT_FIT_SHEET");
  });

  it("o conflito de versão da rodada é dito como rodada que andou", () => {
    const message = errorMessage("REVISION_CONFLICT");

    expect(message).toContain("A rodada mudou");
    expect(message).toContain("recarregue o estado atual");
    expect(message).not.toContain("REVISION_CONFLICT");
  });

  it("as recusas de ETAPA da rodada têm frase própria, nunca o código cru", () => {
    for (const code of [
      "ROUND_STAGE_NOT_READY",
      "CATALOG_REQUIRED",
      "TAKEOFF_REVIEW_INCOMPLETE",
      "SUGGESTIONS_ALREADY_REFINED",
      "EXTRACTION_IN_PROGRESS",
      "ROUND_PLATE_ALREADY_PRESENT",
      "CATALOG_QUERY_EMPTY",
    ]) {
      const message = errorMessage(code);

      expect(message).not.toContain(code);
      expect(message.length).toBeGreaterThan(20);
    }
  });

  it("diz o que fazer quando o papel ou a autorização faltam", () => {
    expect(errorMessage("FORBIDDEN")).toContain("orçamentista");
    expect(errorMessage("AI_PROCESSING_NOT_AUTHORIZED")).toContain(
      "autorização contratual",
    );
  });

  it("acrescenta o detalhe do servidor quando ele diz algo a mais", () => {
    const message = errorMessage(
      "ROUND_STAGE_NOT_READY",
      "a rodada ainda não tem boletim construído",
    );

    expect(message).toContain("etapa ainda não está disponível");
    expect(message).toContain("ainda não tem boletim construído");
  });

  it("mostra código e detalhe crus quando o código não tem frase própria", () => {
    expect(errorMessage("CONTRACT_SEMANTICS_DIVERGENT", "histórico não fecha")).toBe(
      "CONTRACT_SEMANTICS_DIVERGENT: histórico não fecha",
    );
    expect(errorMessage("ERRO_SEM_DETALHE")).toBe("ERRO_SEM_DETALHE");
  });
});

describe("recusas da aprovação e do portão de exportação", () => {
  /**
   * Os códigos são do domínio (`Valuation.export_errors` e `audit_workbook`): a tela não
   * inventa nenhum, e cada um precisa de frase própria — mostrar o código cru mandaria a
   * orçamentista procurar o significado fora do produto.
   */
  it("todo código do portão tem frase própria, sem repetir o código", () => {
    for (const code of [
      "VALUATION_EXPORT_BLOCKED",
      "VALUATION_NOT_APPROVED",
      "VALUATION_APPROVAL_REJECTED",
      "APPROVAL_CONTENT_MISMATCH",
      "PERIOD_NOT_SEQUENTIAL",
      "BALANCE_EXCEEDED",
      "LINE_PRICE_NOT_IN_CONTRACT",
      "LINE_UNIT_NOT_IN_CONTRACT",
      "VALUATION_WORKBOOK_AUDIT_FAILED",
      "CELL_VALUE_MISMATCH",
      "CATALOG_PRICE_MISMATCH",
    ]) {
      const message = errorMessage(code);

      expect(message).not.toContain(code);
      expect(message.length).toBeGreaterThan(20);
    }
  });

  it("a medição sem aprovação manda aprovar, e a caduca manda aprovar de novo", () => {
    expect(errorMessage("VALUATION_NOT_APPROVED")).toContain("depois de aprovar");
    expect(errorMessage("APPROVAL_CONTENT_MISMATCH")).toContain(
      "aprove a medição atual",
    );
    // Nenhuma frase oferece publicar mesmo assim: essa saída não existe.
    expect(errorMessage("VALUATION_NOT_APPROVED")).not.toContain("mesmo assim");
    expect(errorMessage("APPROVAL_CONTENT_MISMATCH")).not.toContain("mesmo assim");
  });

  it("a auditoria reprovada diz que nada foi publicado", () => {
    expect(errorMessage("VALUATION_WORKBOOK_AUDIT_FAILED")).toContain(
      "nada foi publicado",
    );
    expect(MENSAGEM_AUDITORIA_REPROVADA).toContain("nada foi publicado");
    expect(MENSAGEM_AUDITORIA_REPROVADA).toContain("descartado");
  });
});

describe("violationDetailLine", () => {
  it("nomeia as partes que o domínio escreve depois do código", () => {
    expect(violationDetailLine("PERIOD_NOT_SEQUENTIAL", ["3", "4"])).toBe(
      "PERIOD_NOT_SEQUENTIAL · esperado 3 · recebido 4",
    );
    expect(
      violationDetailLine("CODE_NOT_IN_CONTRACT", ["praca", "04", "09.001.0100-A"]),
    ).toBe("CODE_NOT_IN_CONTRACT · obra praca · item 04 · código 09.001.0100-A");
  });

  it("código sem parte é só o código, e parte sem rótulo aparece como veio", () => {
    expect(violationDetailLine("VALUATION_NOT_APPROVED", [])).toBe(
      "VALUATION_NOT_APPROVED",
    );
    expect(violationDetailLine("CODIGO_NOVO_DO_DOMINIO", ["x", "y"])).toBe(
      "CODIGO_NOVO_DO_DOMINIO · x · y",
    );
  });
});

describe("avisos da aprovação e da exportação", () => {
  it("a aprovação caduca diz que nada foi exportado e que a saída é aprovar de novo", () => {
    expect(MENSAGEM_APROVACAO_CADUCA).toContain("não vale mais");
    expect(MENSAGEM_APROVACAO_CADUCA).toContain("aprovada de novo");
    expect(MENSAGEM_APROVACAO_CADUCA).not.toContain("mesmo assim");
  });

  it("o aviso da exportação declara o portão antes do clique", () => {
    expect(AVISO_EXPORTACAO_FAIL_CLOSED).toContain("reconferido");
    expect(AVISO_EXPORTACAO_FAIL_CLOSED).toContain("nada é publicado");
  });

  /**
   * Qual papel a mensagem deve citar é decisão de autorização ainda aberta no pacote de
   * design aprovado: nomear um papel aqui afirmaria uma decisão que ninguém tomou.
   */
  it("o 403 da etapa não nomeia papel nenhum", () => {
    expect(MENSAGEM_SEM_ACESSO).toContain("não tem autorização");
    expect(MENSAGEM_SEM_ACESSO).not.toContain("orçamentista");
    expect(MENSAGEM_SEM_ACESSO).not.toContain("papel");
  });
});

describe("stageLabel e extractionStatusLabel", () => {
  it("escrevem etapa e estado da leitura por extenso", () => {
    expect(stageLabel("amendment_dossier")).toBe("dossiê do aditivo");
    expect(stageLabel("etapa_futura")).toBe("etapa_futura");
    expect(extractionStatusLabel("queued")).toBe("na fila");
    expect(extractionStatusLabel("failed")).toBe("falhou");
    expect(extractionStatusLabel("estado_futuro")).toBe("estado_futuro");
  });
});

describe("extractionFailureMessage", () => {
  it("traduz o código estável da falha da leitura automática", () => {
    expect(extractionFailureMessage("PROVIDER_EXECUTION_FAILED")).toContain(
      "nenhum artefato foi publicado",
    );
    expect(extractionFailureMessage("EXTRACTION_PAGE_NOT_BOUND")).toContain(
      "página promovida",
    );
  });

  it("código desconhecido aparece como veio, sem frase inventada", () => {
    expect(extractionFailureMessage("CODIGO_NOVO")).toContain("CODIGO_NOVO");
  });

  it("sem código, diz o que se sabe e nada além", () => {
    expect(extractionFailureMessage(null)).toBe(
      "A leitura automática da legenda falhou nesta rodada.",
    );
  });
});

describe("AVISO_LOCALIZACAO_NAO_CONFIRMADA", () => {
  it("diz para decidir pela lista e pela prancha, sem prometer um retângulo", () => {
    expect(AVISO_LOCALIZACAO_NAO_CONFIRMADA).toContain("não confirmada");
    expect(AVISO_LOCALIZACAO_NAO_CONFIRMADA).toContain("decida pela lista e pela prancha");
  });
});

describe("AVISO_MEDICAO", () => {
  it("declara a identidade da sessão e que medir não é aprovar nem exportar", () => {
    expect(AVISO_MEDICAO).toContain("carimbadas com sua identidade");
    expect(AVISO_MEDICAO).toContain("medição sem aprovação");
    expect(AVISO_MEDICAO).toContain("atos separados");
    expect(AVISO_MEDICAO).not.toContain("Ferramenta local");
  });
});

describe("MENSAGEM_RODADA_MUDOU", () => {
  it("diz que nada foi gravado e que o formulário continua ali", () => {
    expect(MENSAGEM_RODADA_MUDOU).toContain("A rodada mudou");
    expect(MENSAGEM_RODADA_MUDOU).toContain("Nada foi gravado");
    expect(MENSAGEM_RODADA_MUDOU).toContain("continua aqui");
  });
});

describe("DESCRICAO_CALCULO_SHORTLIST", () => {
  it("declara o custo do clique: nenhum provider, só o braço lexical", () => {
    expect(DESCRICAO_CALCULO_SHORTLIST).toContain("Nenhum provider é chamado");
    expect(DESCRICAO_CALCULO_SHORTLIST).toContain("só pelo braço lexical");
  });
});
