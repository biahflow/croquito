import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "../api";
import {
  associatePlate,
  createEstimate,
  createPlateExtraction,
  getCodes,
  getEstimate,
  getEstimateState,
  getSuggestions,
  getTakeoff,
  getTakeoffOverlay,
  installCatalog,
  installReferenceCatalog,
  listEstimates,
  listReferenceCatalogs,
  postApproveEstimate,
  postBuildEstimate,
  postCodeDecision,
  postExportEstimate,
  postRegime,
  postSuggestionsRecompute,
  postTakeoffDecision,
  postTarget,
  removeCascadeSource,
  reorderCascade,
  searchCascade,
} from "./api";
import { describeError, isRevisionConflict, orcamentoErrorCode } from "./errors";
import type { CalcMatrix } from "./matrix";

/** Base do build de teste: `VITE_API_BASE_URL` não é declarada neste ambiente. */
const BASE = "http://localhost:8000";
const TOKEN = "token-de-teste";
const ROUND = "0197f2a0-0000-7000-8000-000000000009";
const SCO = "a".repeat(64);
const EMOP = "b".repeat(64);

type Chamada = { url: string; init: RequestInit | undefined };

const chamadas: Chamada[] = [];

/** Resposta JSON qualquer; o corpo importa pouco — o oráculo é o que SAIU no `fetch`. */
function ok(body: unknown = {}): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });
}

/** Envelope de erro da API: `{detail: {code, detail, details}}`, aninhado. */
function problema(
  status: number,
  code: string,
  detail: string,
  details: Record<string, unknown> = {},
): Response {
  return new Response(JSON.stringify({ detail: { code, detail, details } }), {
    status,
    headers: { "Content-Type": "application/problem+json" },
  });
}

function stub(responder: (call: Chamada) => Response): void {
  vi.stubGlobal("fetch", (url: string, init?: RequestInit) => {
    const call = { url, init };
    chamadas.push(call);
    return Promise.resolve(responder(call));
  });
}

function headersDaChamada(indice = 0): Record<string, string> {
  return (chamadas[indice]?.init?.headers ?? {}) as Record<string, string>;
}

function corpoDaChamada(indice = 0): Record<string, unknown> {
  return JSON.parse(String(chamadas[indice]?.init?.body ?? "{}"));
}

beforeEach(() => {
  chamadas.length = 0;
  stub(() => ok());
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("leituras do orçamento", () => {
  it("citam a rodada no caminho e levam o Bearer da sessão, sem chave de idempotência", async () => {
    await getEstimateState(TOKEN, ROUND);

    expect(chamadas).toHaveLength(1);
    expect(chamadas[0].url).toBe(`${BASE}/v1/estimate-rounds/${ROUND}`);
    expect(headersDaChamada().Authorization).toBe(`Bearer ${TOKEN}`);
    expect(headersDaChamada()).not.toHaveProperty("Idempotency-Key");
  });

  it("cada etapa lê o caminho dela, sempre sob a rodada de orçamento", async () => {
    await getTakeoff(TOKEN, ROUND);
    await getTakeoffOverlay(TOKEN, ROUND);
    await getSuggestions(TOKEN, ROUND);
    await getCodes(TOKEN, ROUND);
    await getEstimate(TOKEN, ROUND);

    expect(chamadas.map((call) => call.url)).toEqual([
      `${BASE}/v1/estimate-rounds/${ROUND}/takeoff`,
      `${BASE}/v1/estimate-rounds/${ROUND}/takeoff/overlay`,
      `${BASE}/v1/estimate-rounds/${ROUND}/code-suggestions`,
      `${BASE}/v1/estimate-rounds/${ROUND}/code-assignments`,
      `${BASE}/v1/estimate-rounds/${ROUND}/estimate`,
    ]);
    // Nenhuma rota da medição é chamada por engano: as jornadas não se cruzam.
    expect(chamadas.every((call) => !call.url.includes("valuation-rounds"))).toBe(
      true,
    );
  });

  it("a listagem passa o cursor opaco como veio", async () => {
    await listEstimates(TOKEN, { cursor: "Y3Vyc29y", limit: 5 });

    expect(chamadas[0].url).toBe(
      `${BASE}/v1/estimate-rounds?limit=5&cursor=Y3Vyc29y`,
    );
  });

  /**
   * O acervo é lido SOB a rodada, porque é a rodada que conhece o regime — e os dois
   * filtros (circulação e regime) são do servidor. A tela não manda parâmetro de filtro
   * nenhum: mandá-lo seria guardar aqui uma cópia da regra que a instalação aplica.
   */
  it("o acervo da rodada é leitura pura, sem filtro e sem chave de idempotência", async () => {
    await listReferenceCatalogs(TOKEN, ROUND);

    expect(chamadas).toHaveLength(1);
    expect(chamadas[0].url).toBe(
      `${BASE}/v1/estimate-rounds/${ROUND}/reference-catalogs`,
    );
    expect(chamadas[0].init?.method ?? "GET").toBe("GET");
    expect(headersDaChamada().Authorization).toBe(`Bearer ${TOKEN}`);
    expect(headersDaChamada()).not.toHaveProperty("Idempotency-Key");
    expect(chamadas[0].url).not.toContain("origin=");
  });

  /**
   * A rota do orçamento NÃO expõe `arm`: o braço híbrido depende de índice de embeddings
   * que nenhuma rota de `/v1` publica, e mandar o parâmetro inventaria contrato.
   */
  it("a busca na cascata não manda braço nenhum", async () => {
    await searchCascade(TOKEN, ROUND, "piso intertravado", 5);

    expect(chamadas[0].url).toBe(
      `${BASE}/v1/estimate-rounds/${ROUND}/catalog/search?q=piso+intertravado&limit=5`,
    );
    expect(chamadas[0].url).not.toContain("arm=");
  });
});

describe("mutações do orçamento", () => {
  it("abrir orçamento não manda catálogo nem período, e manda Idempotency-Key", async () => {
    await createEstimate(TOKEN, {
      worksiteKey: "praca-do-exemplo",
      worksiteName: "Praça do Exemplo",
      referenceLabel: "ORÇAMENTO-BASE 2026",
      address: "  Rua Sintética, s/n  ",
    });

    expect(chamadas[0].url).toBe(`${BASE}/v1/estimate-rounds`);
    expect(headersDaChamada()["Idempotency-Key"]).toMatch(/^[0-9a-f-]{36}$/);
    expect(corpoDaChamada()).toEqual({
      worksite_key: "praca-do-exemplo",
      worksite_name: "Praça do Exemplo",
      reference_label: "ORÇAMENTO-BASE 2026",
      address: "Rua Sintética, s/n",
    });
    expect(corpoDaChamada()).not.toHaveProperty("catalog_upload_id");
    expect(corpoDaChamada()).not.toHaveProperty("period_number");
    expect(corpoDaChamada()).not.toHaveProperty("contract_label");
  });

  it("instalar catálogo cita base_version e o upload, e nada mais", async () => {
    await installCatalog(TOKEN, ROUND, "upload-1", 3);

    expect(chamadas[0].url).toBe(`${BASE}/v1/estimate-rounds/${ROUND}/catalogs`);
    expect(corpoDaChamada()).toEqual({ upload_id: "upload-1", base_version: 3 });
    // O caminho do arquivo próprio segue exatamente como era: nenhuma tabela do acervo
    // entra no corpo dele por engano.
    expect(corpoDaChamada()).not.toHaveProperty("reference_catalog_id");
  });

  /**
   * A tabela do acervo entra pela MESMA rota, com a mesma guarda otimista e a mesma chave
   * de idempotência — o que muda é qual fonte o corpo cita, e ele cita exatamente uma.
   */
  it("instalar do acervo usa a mesma rota, citando a tabela e nenhum arquivo", async () => {
    await installReferenceCatalog(TOKEN, ROUND, "tabela-do-acervo-1", 3);

    expect(chamadas[0].url).toBe(`${BASE}/v1/estimate-rounds/${ROUND}/catalogs`);
    expect(headersDaChamada()["Idempotency-Key"]).toMatch(/^[0-9a-f-]{36}$/);
    expect(corpoDaChamada()).toEqual({
      reference_catalog_id: "tabela-do-acervo-1",
      base_version: 3,
    });
    expect(corpoDaChamada()).not.toHaveProperty("upload_id");
  });

  /** A reordenação é a permutação COMPLETA: corpo parcial faria o servidor escolher. */
  it("reordenar manda a cascata inteira, na ordem nova", async () => {
    await reorderCascade(TOKEN, ROUND, { cascade: [EMOP, SCO], baseVersion: 7 });

    expect(chamadas[0].url).toBe(
      `${BASE}/v1/estimate-rounds/${ROUND}/catalogs/order`,
    );
    expect(corpoDaChamada()).toEqual({ base_version: 7, cascade: [EMOP, SCO] });
  });

  it("remover manda só o digest da fonte e base_version, e a chave de idempotência", async () => {
    await removeCascadeSource(TOKEN, ROUND, { sourceSha256: SCO, baseVersion: 7 });

    expect(chamadas[0].url).toBe(
      `${BASE}/v1/estimate-rounds/${ROUND}/catalogs/remove`,
    );
    expect(corpoDaChamada()).toEqual({ base_version: 7, source_sha256: SCO });
    expect(headersDaChamada()["Idempotency-Key"]).toMatch(/^[0-9a-f-]{36}$/);
  });

  it("o lote de takeoff cita UMA base_version para todas as decisões e não carimba identidade", async () => {
    await postTakeoffDecision(TOKEN, ROUND, {
      baseVersion: 7,
      decisions: [
        {
          itemId: "ti_af6f85a49ea0b93d",
          action: "confirm",
          quantity: "340.50",
          note: "quantidade lida na prancha",
        },
        { itemId: "ti_af6f85a49ea0b93e", action: "reject" },
      ],
    });

    expect(chamadas[0].url).toBe(
      `${BASE}/v1/estimate-rounds/${ROUND}/takeoff/decisions`,
    );
    const corpo = corpoDaChamada();
    expect(corpo.base_version).toBe(7);
    const decisoes = corpo.decisions as Record<string, unknown>[];
    expect(decisoes).toHaveLength(2);
    expect(decisoes[0].quantity).toBe("340.50");
    for (const proibido of [
      "reviewer_id",
      "reviewer_role",
      "decided_at",
      "decision_id",
    ]) {
      expect(corpo).not.toHaveProperty(proibido);
      for (const decisao of decisoes) {
        expect(decisao).not.toHaveProperty(proibido);
      }
    }
  });

  /**
   * A diferença que dá nome ao módulo: confirmar um código é escolher de QUAL catálogo
   * aquele preço sai. A citação viaja na decisão, não só no relatório.
   */
  it("a confirmação de código cita a fonte de preço", async () => {
    await postCodeDecision(TOKEN, ROUND, {
      itemId: "ti_af6f85a49ea0b93d",
      action: "confirm",
      baseVersion: 4,
      code: "12.015.0030",
      catalogSha256: EMOP,
    });

    expect(chamadas[0].url).toBe(
      `${BASE}/v1/estimate-rounds/${ROUND}/code-assignments/decisions`,
    );
    expect(corpoDaChamada()).toEqual({
      base_version: 4,
      item_id: "ti_af6f85a49ea0b93d",
      action: "confirm",
      code: "12.015.0030",
      catalog_sha256: EMOP,
    });
  });

  /** Rejeitar é recusar TODAS as fontes, não uma delas: a rejeição não cita catálogo. */
  it("a rejeição leva nota e não leva código nem fonte", async () => {
    await postCodeDecision(TOKEN, ROUND, {
      itemId: "ti_af6f85a49ea0b93d",
      action: "reject",
      baseVersion: 4,
      code: "12.015.0030",
      catalogSha256: EMOP,
      note: "mobiliário fora do escopo desta praça",
    });

    const corpo = corpoDaChamada();
    expect(corpo.note).toBe("mobiliário fora do escopo desta praça");
    expect(corpo).not.toHaveProperty("code");
    expect(corpo).not.toHaveProperty("catalog_sha256");
  });

  it("o recompute da shortlist é ato humano e cita base_version", async () => {
    await postSuggestionsRecompute(TOKEN, ROUND, 9);

    expect(chamadas[0].url).toBe(
      `${BASE}/v1/estimate-rounds/${ROUND}/code-suggestions/recompute`,
    );
    expect(corpoDaChamada()).toEqual({ base_version: 9 });
  });

  it("a prancha e a extração citam base_version, cada uma no caminho dela", async () => {
    await associatePlate(TOKEN, ROUND, "upload-2", 2);
    await createPlateExtraction(TOKEN, ROUND, 3);

    expect(chamadas.map((call) => call.url)).toEqual([
      `${BASE}/v1/estimate-rounds/${ROUND}/plate`,
      `${BASE}/v1/estimate-rounds/${ROUND}/plate/extractions`,
    ]);
    expect(corpoDaChamada(0)).toEqual({ upload_id: "upload-2", base_version: 2 });
    expect(corpoDaChamada(1)).toEqual({ base_version: 3 });
  });
});

/**
 * O BDI é `ExactDecimal` no domínio (ADR-0038, decisão 2): ele viaja como TEXTO, porque
 * um número de JSON já teria passado por binário antes de chegar à rota.
 */
describe("BDI da montagem", () => {
  it("sai como string decimal, na forma que o servidor lê", async () => {
    await postBuildEstimate(TOKEN, ROUND, "25,00", 11);

    expect(chamadas[0].url).toBe(`${BASE}/v1/estimate-rounds/${ROUND}/estimate`);
    const corpo = corpoDaChamada();
    expect(corpo).toEqual({ base_version: 11, bdi_percent: "25.00" });
    expect(typeof corpo.bdi_percent).toBe("string");
  });

  it("nenhuma casa decimal é acrescentada nem removida", async () => {
    await postBuildEstimate(TOKEN, ROUND, "25", 11);
    expect(corpoDaChamada(0).bdi_percent).toBe("25");

    chamadas.length = 0;
    await postBuildEstimate(TOKEN, ROUND, "1.234,5678", 11);
    expect(corpoDaChamada(0).bdi_percent).toBe("1234.5678");
  });

  it("texto que não é decimal exato não chega a viajar", async () => {
    await expect(postBuildEstimate(TOKEN, ROUND, "25%", 11)).rejects.toBeInstanceOf(
      ApiError,
    );

    expect(chamadas).toHaveLength(0);
  });
});

/**
 * A matriz elemento × serviço (F-038 "decisão 6", ADR-0053) viaja no MESMO corpo do build,
 * ao lado do BDI, e SÓ quando a orçamentista autorou contribuição. Sem matriz, o corpo é o
 * de sempre — é o que garante que o regime legado (código único por item) siga byte-idêntico.
 */
describe("matriz de contribuições na montagem", () => {
  const MATRIZ: CalcMatrix = {
    schema_version: "1.0.0",
    services: [
      {
        code: "SCO001",
        contributions: [
          {
            source_item_id: "ti_0000000000000001",
            label: "Piso em concreto",
            basis: "derived",
            recipe: "length_times_width",
            operands: [
              { name: "COMPRIMENTO", value: "20.906", unit: "m" },
              { name: "LARGURA", value: "20.00", unit: "m" },
            ],
            deductions: [],
            depends_on_code: null,
            note: null,
          },
        ],
      },
    ],
  };

  it("vai como calc_matrix ao lado do BDI quando há contribuição autorada", async () => {
    await postBuildEstimate(TOKEN, ROUND, "25,00", 11, MATRIZ);

    const corpo = corpoDaChamada();
    expect(corpo).toEqual({
      base_version: 11,
      bdi_percent: "25.00",
      calc_matrix: MATRIZ,
    });
  });

  it("sem matriz (null) o corpo é o de sempre — regime legado byte-idêntico", async () => {
    await postBuildEstimate(TOKEN, ROUND, "25,00", 11, null);

    expect(corpoDaChamada()).toEqual({ base_version: 11, bdi_percent: "25.00" });
    expect(corpoDaChamada()).not.toHaveProperty("calc_matrix");
  });
});

/**
 * Aprovação nominal e despacho (F-035, ADR-0046): dois atos, duas rotas, dois papéis.
 *
 * O oráculo aqui é o que SAIU no `fetch`: a rota certa, a chave de idempotência e um corpo
 * que carrega SÓ a guarda de concorrência. A identidade não viaja — e é justamente por não
 * viajar que o ato é nominal de verdade, com o nome vindo do token.
 */
describe("aprovação e despacho do orçamento", () => {
  it("aprovar cita a rota de assinatura e manda só base_version", async () => {
    await postApproveEstimate(TOKEN, ROUND, 12);

    expect(chamadas).toHaveLength(1);
    expect(chamadas[0].url).toBe(
      `${BASE}/v1/estimate-rounds/${ROUND}/estimate/approve`,
    );
    expect(chamadas[0].init?.method).toBe("POST");
    expect(headersDaChamada()).toHaveProperty("Idempotency-Key");
    expect(corpoDaChamada()).toEqual({ base_version: 12 });
  });

  it("despachar cita a rota de exportação e manda só base_version", async () => {
    await postExportEstimate(TOKEN, ROUND, 13);

    expect(chamadas).toHaveLength(1);
    expect(chamadas[0].url).toBe(
      `${BASE}/v1/estimate-rounds/${ROUND}/estimate/export`,
    );
    expect(chamadas[0].init?.method).toBe("POST");
    expect(headersDaChamada()).toHaveProperty("Idempotency-Key");
    expect(corpoDaChamada()).toEqual({ base_version: 13 });
  });

  /**
   * O servidor recusa com `422` qualquer corpo que traga identidade. A tela não depende
   * dessa recusa: o corpo não tem por onde carregá-la, e é isso que este teste fixa.
   */
  it("nenhum campo de identidade sai no corpo dos dois atos", async () => {
    await postApproveEstimate(TOKEN, ROUND, 12);
    await postExportEstimate(TOKEN, ROUND, 13);

    for (const indice of [0, 1]) {
      const corpo = corpoDaChamada(indice);
      expect(Object.keys(corpo)).toEqual(["base_version"]);
      for (const campo of [
        "approver_id",
        "approver_role",
        "decided_at",
        "decision_id",
        "note",
      ]) {
        expect(corpo).not.toHaveProperty(campo);
      }
    }
  });

  /** Cada chamada leva chave PRÓPRIA: aprovar de novo é ato novo, não repetição do anterior. */
  it("aprovar de novo leva chave de idempotência nova", async () => {
    await postApproveEstimate(TOKEN, ROUND, 12);
    await postApproveEstimate(TOKEN, ROUND, 13);

    expect(headersDaChamada(0)["Idempotency-Key"]).not.toBe(
      headersDaChamada(1)["Idempotency-Key"],
    );
  });

  /**
   * A montagem deixou de publicar (ADR-0046, decisão 2): ela não pode, por engano, chamar
   * a rota de despacho — a quebra declarada é exatamente essa separação.
   */
  it("montar não chama a rota de despacho", async () => {
    await postBuildEstimate(TOKEN, ROUND, "25,00", 11);

    expect(chamadas.map((call) => call.url)).toEqual([
      `${BASE}/v1/estimate-rounds/${ROUND}/estimate`,
    ]);
  });
});

/**
 * Teto de verba (ADR-0040): mutação como qualquer outra — versão base, chave de
 * idempotência e o valor em TEXTO. Não existe rota de remoção, e a tela não inventa uma.
 */
describe("teto da rodada", () => {
  it("grava na rota da rodada, com base_version e chave de idempotência", async () => {
    await postTarget(TOKEN, ROUND, 12, "85.000,00", "Relação de Praças 2026 · demanda 14");

    expect(chamadas[0].url).toBe(`${BASE}/v1/estimate-rounds/${ROUND}/target`);
    expect(chamadas[0].init?.method).toBe("POST");
    expect(headersDaChamada()).toHaveProperty("Idempotency-Key");
    const corpo = corpoDaChamada();
    expect(corpo).toEqual({
      base_version: 12,
      target_amount: "85000.00",
      target_label: "Relação de Praças 2026 · demanda 14",
    });
    expect(typeof corpo.target_amount).toBe("string");
  });

  it("sem rótulo da demanda, o corpo não leva rótulo em branco", async () => {
    await postTarget(TOKEN, ROUND, 12, "85000.00");

    expect(corpoDaChamada()).toEqual({
      base_version: 12,
      target_amount: "85000.00",
    });
  });

  /** Zero não é "sem teto": ele nem chega a virar chamada. */
  it("valor recusado pela tela não chega a viajar", async () => {
    for (const invalido of ["0,00", "oitenta e cinco mil", ""]) {
      await expect(postTarget(TOKEN, ROUND, 12, invalido)).rejects.toBeInstanceOf(
        ApiError,
      );
    }

    expect(chamadas).toHaveLength(0);
  });
});

/**
 * Regime da rodada (ADR-0045): mesmo desenho do teto, com uma diferença que é a decisão —
 * o corpo não tem parâmetro, porque só existe um valor declarável e a volta não é ato
 * desta tela.
 */
describe("regime da rodada", () => {
  it("declara na rota da rodada, com base_version e chave de idempotência", async () => {
    await postRegime(TOKEN, ROUND, 12);

    expect(chamadas).toHaveLength(1);
    expect(chamadas[0].url).toBe(`${BASE}/v1/estimate-rounds/${ROUND}/regime`);
    expect(chamadas[0].init?.method).toBe("POST");
    expect(headersDaChamada()).toHaveProperty("Idempotency-Key");
    expect(corpoDaChamada()).toEqual({
      base_version: 12,
      pricing_regime: "contracted_demand",
    });
  });

  /** Mão única: a pré-licitação não sai daqui nem por engano de chamada. */
  it("nunca manda `pre_bid`, que é a volta que o servidor recusa", async () => {
    await postRegime(TOKEN, ROUND, 3);

    expect(JSON.stringify(corpoDaChamada())).not.toContain("pre_bid");
  });

  /**
   * A recusa da cascata suja é do SERVIDOR, contra a cascata que ele tem. A tela não a
   * antecipa: ela viaja, é recusada e a frase chega por extenso.
   */
  it("deixa a cascata suja ser recusada pelo servidor, e traduz a recusa", async () => {
    stub(() =>
      problema(
        409,
        "ESTIMATE_REGIME_CASCADE_DIRTY",
        "a cascata tem fonte fora da tabela contratual",
        { origins: ["emop"], allowed_origins: ["sco"] },
      ),
    );

    const erro = await postRegime(TOKEN, ROUND, 12).catch((error) => error);

    expect(erro).toBeInstanceOf(ApiError);
    expect(orcamentoErrorCode(erro as ApiError)).toBe(
      "ESTIMATE_REGIME_CASCADE_DIRTY",
    );
    expect(describeError(erro)).toContain("Remova a fonte e declare de novo");
    expect(describeError(erro)).toContain("a declaração não foi gravada");
  });

  /** A recusa da instalação nasce na INSTALAÇÃO, e a frase diz o que teria acontecido. */
  it("traduz a origem proibida dizendo o que a medição faria com aquele preço", async () => {
    stub(() =>
      problema(
        409,
        "ESTIMATE_CASCADE_ORIGIN_FORBIDDEN",
        "a rodada corre sob contrato licitado",
        { origin: "emop", allowed_origins: ["sco"] },
      ),
    );

    const erro = await installCatalog(TOKEN, ROUND, "upload", 4).catch(
      (error) => error,
    );

    expect(describeError(erro)).toContain(
      "sobre serviço já executado",
    );
    expect(describeError(erro)).toContain("Nada foi instalado e nada foi alterado");
  });
});

describe("recusas traduzidas", () => {
  /**
   * A lista que a tela leu pode envelhecer entre a leitura e o clique: uma tabela retirada
   * de circulação nesse intervalo recusa na instalação. A frase diz as três coisas que
   * importam — a tabela saiu, as rodadas que já a instalaram continuam de pé, e nada foi
   * gravado agora.
   */
  it("tabela retirada entre a leitura e o clique é recusa de instalação, não erro da tela", async () => {
    stub(() =>
      problema(
        409,
        "REFERENCE_CATALOG_WITHDRAWN",
        "a tabela saiu de circulação",
        { reference_catalog_id: "tabela-do-acervo-1" },
      ),
    );

    const erro = await installReferenceCatalog(
      TOKEN,
      ROUND,
      "tabela-do-acervo-1",
      3,
    ).catch((error: unknown) => error);

    expect(describeError(erro)).toContain("saiu de circulação");
    expect(describeError(erro)).toContain(
      "continua valendo nas rodadas que já a instalaram",
    );
    expect(describeError(erro)).toContain("nada foi instalado");
  });

  /** As regras da cascata valem iguais, venha o arquivo do acervo ou do cliente. */
  it("origem repetida recusa igual quando a fonte veio do acervo", async () => {
    stub(() =>
      problema(
        409,
        "ESTIMATE_CASCADE_ORIGIN_DUPLICATE",
        "a cascata já tem um catálogo desta origem",
        { origin: "sco" },
      ),
    );

    const erro = await installReferenceCatalog(
      TOKEN,
      ROUND,
      "tabela-do-acervo-1",
      3,
    ).catch((error: unknown) => error);

    expect(describeError(erro)).toContain("Cada origem entra uma vez só");
  });

  it("o 409 da rodada é o convite a recarregar, não falha do ato", async () => {
    stub(() =>
      problema(409, "REVISION_CONFLICT", "a rodada mudou depois da leitura", {
        base_version: 3,
        current_version: 4,
      }),
    );

    await installCatalog(TOKEN, ROUND, "upload-1", 3).catch((error: unknown) => {
      expect(isRevisionConflict(error)).toBe(true);
      expect(describeError(error)).toContain("recarregue o estado atual");
    });
    expect.assertions(2);
  });

  /** Origem repetida na cascata é recusa de DOMÍNIO com frase própria, por tabela. */
  it("origem repetida na cascata sai como a frase da cascata", async () => {
    stub(() =>
      problema(
        409,
        "ESTIMATE_CASCADE_ORIGIN_DUPLICATE",
        "a cascata já tem um catálogo desta origem",
        { origin: "emop" },
      ),
    );

    await installCatalog(TOKEN, ROUND, "upload-1", 3).catch((error: unknown) => {
      expect(describeError(error)).toContain("Cada origem entra uma vez só");
      expect(error).toBeInstanceOf(ApiError);
      expect(orcamentoErrorCode(error as ApiError)).toBe(
        "ESTIMATE_CASCADE_ORIGIN_DUPLICATE",
      );
    });
    expect.assertions(3);
  });

  /**
   * Invariante de `packages/valuation` viaja DENTRO de `DOMAIN_VALIDATION_FAILED`, em
   * `details.code`: é ela, e não o código da API, que escolhe a frase.
   */
  it("o código do domínio ganha do código da API na escolha da frase", async () => {
    stub(() =>
      problema(422, "DOMAIN_VALIDATION_FAILED", "orçamento recusado", {
        code: "ESTIMATE_LINE_SOURCE_UNKNOWN",
      }),
    );

    await postBuildEstimate(TOKEN, ROUND, "25.00", 11).catch((error: unknown) => {
      expect(error).toBeInstanceOf(ApiError);
      expect(orcamentoErrorCode(error as ApiError)).toBe(
        "ESTIMATE_LINE_SOURCE_UNKNOWN",
      );
      expect(describeError(error)).toContain("não está na cascata");
    });
    expect.assertions(3);
  });
});
