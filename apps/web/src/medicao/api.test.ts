import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "../api";
import {
  appendPlates,
  associatePlate,
  createPlateExtraction,
  createPlatesExtraction,
  createRound,
  declareIdentityLink,
  getCodes,
  getPlate,
  getRoundState,
  getSuggestions,
  getTakeoff,
  getTakeoffOverlay,
  getBulletin,
  getWorksite,
  listRounds,
  postApprove,
  postBulletinExport,
  postCalcBuild,
  postCodeClosure,
  postCodeDecision,
  postCodeRevocation,
  postDossierBuild,
  postSuggestionsRecompute,
  postTakeoffDecision,
  previewIdentityLink,
  previewRound,
  searchCatalog,
  uploadCatalog,
} from "./api";
import { describeError, isRevisionConflict, medicaoErrorCode } from "./errors";

/** Base do build de teste: `VITE_API_BASE_URL` não é declarada neste ambiente. */
const BASE = "http://localhost:8000";
const TOKEN = "token-de-teste";
const ROUND = "0197f2a0-0000-7000-8000-000000000001";

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

describe("leituras da rodada", () => {
  it("citam a rodada no caminho e levam o Bearer da sessão, sem chave de idempotência", async () => {
    await getRoundState(TOKEN, ROUND);

    expect(chamadas).toHaveLength(1);
    expect(chamadas[0].url).toBe(`${BASE}/v1/valuation-rounds/${ROUND}`);
    expect(headersDaChamada().Authorization).toBe(`Bearer ${TOKEN}`);
    expect(headersDaChamada()).not.toHaveProperty("Idempotency-Key");
  });

  it("cada etapa lê o caminho dela, sempre sob a rodada", async () => {
    await getTakeoff(TOKEN, ROUND);
    await getTakeoffOverlay(TOKEN, ROUND);
    await getCodes(TOKEN, ROUND);

    expect(chamadas.map((call) => call.url)).toEqual([
      `${BASE}/v1/valuation-rounds/${ROUND}/takeoff`,
      `${BASE}/v1/valuation-rounds/${ROUND}/takeoff/overlay`,
      `${BASE}/v1/valuation-rounds/${ROUND}/code-assignments`,
    ]);
  });

  it("a listagem de rodadas passa o cursor opaco como veio", async () => {
    await listRounds(TOKEN, { cursor: "Y3Vyc29y", limit: 5 });

    expect(chamadas[0].url).toBe(
      `${BASE}/v1/valuation-rounds?limit=5&cursor=Y3Vyc29y`,
    );
  });

  /**
   * A busca é a lexical do catálogo instalado. O braço híbrido é pago e depende de índice
   * que nenhuma rota de `/v1` publica: pedi-lo devolveria `503` a cada tecla.
   */
  it("a busca no catálogo fixa o braço lexical", async () => {
    await searchCatalog(TOKEN, ROUND, "alambrado", 5);

    expect(chamadas[0].url).toBe(
      `${BASE}/v1/valuation-rounds/${ROUND}/catalog/search?q=alambrado&limit=5&arm=lexical`,
    );
    expect(chamadas[0].url).not.toContain("hybrid");
  });
});

describe("mutações da rodada", () => {
  it("a decisão de takeoff cita base_version, manda Idempotency-Key e não carimba identidade", async () => {
    await postTakeoffDecision(TOKEN, ROUND, {
      baseVersion: 7,
      decisions: [
        {
          itemId: "ti_af6f85a49ea0b93d",
          action: "confirm",
          quantity: "18.40",
          note: "quantidade lida na prancha",
        },
      ],
    });

    expect(chamadas[0].url).toBe(
      `${BASE}/v1/valuation-rounds/${ROUND}/takeoff/decisions`,
    );
    expect(chamadas[0].init?.method).toBe("POST");
    expect(headersDaChamada()["Content-Type"]).toBe("application/json");
    expect(headersDaChamada()["Idempotency-Key"]).toMatch(
      /^[0-9a-f-]{36}$/i,
    );
    const body = corpoDaChamada();
    expect(body).toEqual({
      base_version: 7,
      decisions: [
        {
          item_id: "ti_af6f85a49ea0b93d",
          action: "confirm",
          quantity: "18.40",
          note: "quantidade lida na prancha",
        },
      ],
    });
    const decisoes = body.decisions as Record<string, unknown>[];
    // A quantidade viaja como TEXTO: um `Number()` no caminho perderia a escala escrita.
    expect(typeof decisoes[0].quantity).toBe("string");
    for (const proibido of [
      "reviewer_id",
      "reviewer_role",
      "decided_at",
      "decision_id",
    ]) {
      expect(Object.keys(body)).not.toContain(proibido);
      expect(Object.keys(decisoes[0])).not.toContain(proibido);
    }
  });

  it("cada mutação nasce com uma chave de idempotência própria", async () => {
    await postTakeoffDecision(TOKEN, ROUND, {
      baseVersion: 7,
      decisions: [{ itemId: "ti_af6f85a49ea0b93d", action: "reject" }],
    });
    await postTakeoffDecision(TOKEN, ROUND, {
      baseVersion: 8,
      decisions: [{ itemId: "ti_af6f85a49ea0b93e", action: "reject" }],
    });

    expect(headersDaChamada(0)["Idempotency-Key"]).not.toBe(
      headersDaChamada(1)["Idempotency-Key"],
    );
  });

  it("a decisão de código manda o código só na confirmação", async () => {
    await postCodeDecision(TOKEN, ROUND, {
      itemId: "ti_af6f85a49ea0b93d",
      action: "reject",
      baseVersion: 9,
      code: "AD04050060(/)",
      note: "sem cotação aplicável no contrato",
    });

    expect(chamadas[0].url).toBe(
      `${BASE}/v1/valuation-rounds/${ROUND}/code-assignments/decisions`,
    );
    expect(corpoDaChamada()).toEqual({
      base_version: 9,
      item_id: "ti_af6f85a49ea0b93d",
      action: "reject",
      note: "sem cotação aplicável no contrato",
    });
  });

  /**
   * Boletim, dossiê e recompute recebem SÓ a guarda de concorrência: a identidade da obra
   * é atributo da rodada, declarado na criação, e reenviá-la aqui seria reescrevê-la no
   * meio da cadeia.
   */
  it("boletim, dossiê e recompute mandam apenas a versão-base", async () => {
    await postCalcBuild(TOKEN, ROUND, 11);
    await postDossierBuild(TOKEN, ROUND, 12);
    await postSuggestionsRecompute(TOKEN, ROUND, 13);

    expect(chamadas.map((call) => call.url)).toEqual([
      `${BASE}/v1/valuation-rounds/${ROUND}/calc`,
      `${BASE}/v1/valuation-rounds/${ROUND}/amendment-dossier`,
      `${BASE}/v1/valuation-rounds/${ROUND}/code-suggestions/recompute`,
    ]);
    expect(corpoDaChamada(0)).toEqual({ base_version: 11 });
    expect(corpoDaChamada(1)).toEqual({ base_version: 12 });
    expect(corpoDaChamada(2)).toEqual({ base_version: 13 });
    for (const indice of [0, 1, 2]) {
      expect(headersDaChamada(indice)["Idempotency-Key"]).toMatch(/^[0-9a-f-]{36}$/i);
    }
  });

  it("a prancha entra por upload_id e a extração é pedido próprio", async () => {
    await associatePlate(TOKEN, ROUND, "0197f2a0-0000-7000-8000-0000000000aa", 2);
    await createPlateExtraction(TOKEN, ROUND, 3);

    expect(corpoDaChamada(0)).toEqual({
      upload_id: "0197f2a0-0000-7000-8000-0000000000aa",
      base_version: 2,
    });
    expect(chamadas[1].url).toBe(
      `${BASE}/v1/valuation-rounds/${ROUND}/plate/extractions`,
    );
    expect(corpoDaChamada(1)).toEqual({ base_version: 3 });
  });
});

describe("aprovação nominal e exportação do boletim", () => {
  /**
   * O ato nominal (VAL-05) manda SÓ a versão-base. Identidade e carimbo são do servidor: o
   * nome que a medição publica é o do subject do JWT, e um campo de "nome do aprovador" no
   * corpo faria do ato nominal um campo de texto — o servidor recusaria (`extra="forbid"`),
   * e o cliente não tenta.
   */
  it("aprovar e exportar mandam apenas base_version, com chave de idempotência", async () => {
    await postApprove(TOKEN, ROUND, 14);
    await postBulletinExport(TOKEN, ROUND, 15);

    expect(chamadas.map((call) => call.url)).toEqual([
      `${BASE}/v1/valuation-rounds/${ROUND}/approve`,
      `${BASE}/v1/valuation-rounds/${ROUND}/bulletin/export`,
    ]);
    expect(corpoDaChamada(0)).toEqual({ base_version: 14 });
    expect(corpoDaChamada(1)).toEqual({ base_version: 15 });
    for (const indice of [0, 1]) {
      expect(chamadas[indice].init?.method).toBe("POST");
      expect(headersDaChamada(indice)["Idempotency-Key"]).toMatch(/^[0-9a-f-]{36}$/i);
      for (const proibido of [
        "reviewer_id",
        "reviewer_role",
        "decided_at",
        "decision_id",
      ]) {
        expect(Object.keys(corpoDaChamada(indice))).not.toContain(proibido);
      }
    }
  });

  /**
   * A URL assinada da planilha só existe na LEITURA: ela é credencial de curta vida, e a
   * resposta do `POST` é o que o registro de idempotência guarda no banco.
   */
  it("a leitura do boletim traz a aprovação, a planilha e a URL assinada", async () => {
    stub(() =>
      ok({
        round_id: ROUND,
        version: 16,
        valuation: {},
        valuation_sha256: "a".repeat(64),
        total_amount: "91996.44",
        workbook_present: true,
        workbook_sha256: "f".repeat(64),
        workbook_url: "https://armazenamento.example/boletim.xlsx?assinatura=x",
        approval: {
          approved: true,
          approved_by: "orcamentista-de-teste",
          approved_at: "2026-08-20T14:32:00+00:00",
          approved_digest: "e".repeat(64),
          current_digest: "e".repeat(64),
          stale: false,
        },
      }),
    );

    const boletim = await getBulletin(TOKEN, ROUND);

    expect(chamadas).toHaveLength(1);
    expect(headersDaChamada()).not.toHaveProperty("Idempotency-Key");
    expect(boletim.approval.approved).toBe(true);
    expect(boletim.approval.stale).toBe(false);
    expect(boletim.workbook_url).toContain("assinatura=x");
  });

  /**
   * A aprovação CADUCA é o estado que só existe lendo os dois campos: houve ato humano
   * (`approved`) e ele não cobre mais o conteúdo atual (`stale`), com os dois digests
   * divergentes para a tela mostrar lado a lado.
   */
  it("a aprovação caduca chega com approved e stale verdadeiros ao mesmo tempo", async () => {
    stub(() =>
      ok({
        round_id: ROUND,
        version: 17,
        valuation: {},
        valuation_sha256: "a".repeat(64),
        total_amount: "91996.44",
        workbook_present: false,
        workbook_sha256: null,
        approval: {
          approved: true,
          approved_by: "orcamentista-de-teste",
          approved_at: "2026-08-20T14:32:00+00:00",
          approved_digest: "e".repeat(64),
          current_digest: "d".repeat(64),
          stale: true,
        },
      }),
    );

    const boletim = await getBulletin(TOKEN, ROUND);

    expect(boletim.approval.approved).toBe(true);
    expect(boletim.approval.stale).toBe(true);
    expect(boletim.approval.approved_digest).not.toBe(boletim.approval.current_digest);
  });

  it("a recusa do portão traz a lista de violações do domínio", async () => {
    stub(() =>
      problema(422, "DOMAIN_VALIDATION_FAILED", "medição possui violações abertas", {
        code: "VALUATION_EXPORT_BLOCKED",
        errors: ["VALUATION_NOT_APPROVED"],
      }),
    );

    const erro = (await postBulletinExport(TOKEN, ROUND, 18).catch(
      (error: unknown) => error,
    )) as ApiError;

    expect(medicaoErrorCode(erro)).toBe("VALUATION_EXPORT_BLOCKED");
    expect(erro.details.errors).toEqual(["VALUATION_NOT_APPROVED"]);
  });
});

describe("upload do catálogo", () => {
  /**
   * O byte nunca passa pela API: ela assina, o navegador faz o `PUT` direto no
   * armazenamento e a criação da rodada recebe só o identificador.
   */
  it("assina, sobe direto e devolve o upload_id a citar na rodada", async () => {
    stub((call) =>
      call.url.includes("/v1/uploads/presign")
        ? ok({
            upload_id: "0197f2a0-0000-7000-8000-0000000000bb",
            object_key: "tenants/t/uploads/x/catalogo.json",
            url: "https://armazenamento.example/assinado",
            headers: { "Content-Type": "application/json" },
            expires_at: "2026-08-18T00:00:00Z",
          })
        : ok(),
    );

    const uploadId = await uploadCatalog(
      TOKEN,
      new File(['{"entries":[]}'], "catalogo.json", { type: "application/json" }),
    );

    expect(uploadId).toBe("0197f2a0-0000-7000-8000-0000000000bb");
    expect(chamadas[0].url).toBe(`${BASE}/v1/uploads/presign`);
    const presign = corpoDaChamada(0);
    expect(presign.content_type).toBe("application/json");
    expect(presign.sha256).toMatch(/^[0-9a-f]{64}$/);
    expect(chamadas[1].url).toBe("https://armazenamento.example/assinado");
    expect(chamadas[1].init?.method).toBe("PUT");
    // O `PUT` direto não leva o Bearer: quem autoriza é a assinatura da URL.
    expect(chamadas[1].init?.headers).not.toHaveProperty("Authorization");
  });

  it("falha do PUT assinado é dita como envio, não como arquivo inválido", async () => {
    stub((call) =>
      call.url.includes("/v1/uploads/presign")
        ? ok({
            upload_id: "0197f2a0-0000-7000-8000-0000000000bb",
            object_key: "tenants/t/uploads/x/catalogo.json",
            url: "https://armazenamento.example/assinado",
            headers: {},
            expires_at: "2026-08-18T00:00:00Z",
          })
        : new Response("", { status: 403 }),
    );

    const erro = (await uploadCatalog(
      TOKEN,
      new File(['{"entries":[]}'], "catalogo.json", { type: "application/json" }),
    ).catch((error: unknown) => error)) as ApiError;

    expect(erro.code).toBe("UPLOAD_TRANSFER_FAILED");
    expect(describeError(erro)).toContain("envio direto do arquivo");
  });

  it("a criação da rodada cita o upload do catálogo e o período como inteiro", async () => {
    await createRound(TOKEN, {
      worksiteKey: "praca-sintetica-oeste",
      worksiteName: "Praça Sintética Oeste",
      catalogUploadId: "0197f2a0-0000-7000-8000-0000000000bb",
      referenceLabel: "3ª MEDIÇÃO",
      periodNumber: "3",
      address: "",
      contractLabel: "Contrato 05/2024",
    });

    expect(chamadas[0].url).toBe(`${BASE}/v1/valuation-rounds`);
    expect(corpoDaChamada()).toEqual({
      worksite_key: "praca-sintetica-oeste",
      worksite_name: "Praça Sintética Oeste",
      catalog_upload_id: "0197f2a0-0000-7000-8000-0000000000bb",
      reference_label: "3ª MEDIÇÃO",
      period_number: 3,
      contract_label: "Contrato 05/2024",
    });
  });

  /**
   * A prévia é `POST` porque a declaração viaja no corpo, mas **não é mutação** (F-040 T7):
   * sem `Idempotency-Key` e sem `base_version`, porque não há nada a repetir nem a versionar.
   */
  it("a prévia é POST de leitura: sem chave de idempotência e sem base_version", async () => {
    await previewRound(TOKEN, {
      previousRoundId: ROUND,
      periodNumber: "2",
      amendment: {
        label: "2ª RE-RA",
        referencePeriod: "Processo 123/2026",
        lines: [{ code: "CE04100010(/)", quantityDelta: "3" }],
      },
    });

    expect(chamadas[0].url).toBe(`${BASE}/v1/valuation-round-previews`);
    expect(headersDaChamada().Authorization).toBe(`Bearer ${TOKEN}`);
    expect(headersDaChamada()).not.toHaveProperty("Idempotency-Key");
    expect(corpoDaChamada()).toEqual({
      previous_round_id: ROUND,
      period_number: 2,
      amendment: {
        label: "2ª RE-RA",
        reference_period: "Processo 123/2026",
        lines: [{ code: "CE04100010(/)", quantity_delta: "3" }],
      },
    });
    expect(corpoDaChamada()).not.toHaveProperty("base_version");
  });
});

describe("envelope de erro aninhado", () => {
  it("o 409 da rodada é lido como conflito de versão, não como falha genérica", async () => {
    stub(() =>
      problema(409, "REVISION_CONFLICT", "A newer revision exists.", {
        base_version: 7,
        current_version: 9,
      }),
    );

    const erro = await postCalcBuild(TOKEN, ROUND, 7).catch(
      (error: unknown) => error,
    );

    expect(erro).toBeInstanceOf(ApiError);
    const apiError = erro as ApiError;
    expect(apiError.status).toBe(409);
    expect(apiError.code).toBe("REVISION_CONFLICT");
    expect(apiError.details.current_version).toBe(9);
    expect(isRevisionConflict(apiError)).toBe(true);
    expect(describeError(apiError)).toContain("A rodada mudou");
  });

  /**
   * A API não republica o vocabulário do domínio: a invariante de `packages/valuation`
   * viaja em `details.code` dentro de `DOMAIN_VALIDATION_FAILED`, e é ela que escolhe a
   * frase mostrada ao orçamentista.
   */
  it("a invariante do domínio é lida de details.code, não do código da API", async () => {
    stub(() =>
      problema(
        422,
        "DOMAIN_VALIDATION_FAILED",
        "item de takeoff já revisado não pode ser sobrescrito",
        { id: "ti_af6f85a49ea0b93d", code: "TAKEOFF_ITEM_ALREADY_REVIEWED" },
      ),
    );

    const erro = (await postTakeoffDecision(TOKEN, ROUND, {
      baseVersion: 7,
      decisions: [{ itemId: "ti_af6f85a49ea0b93d", action: "confirm" }],
    }).catch((error: unknown) => error)) as ApiError;

    expect(erro.code).toBe("DOMAIN_VALIDATION_FAILED");
    expect(medicaoErrorCode(erro)).toBe("TAKEOFF_ITEM_ALREADY_REVIEWED");
    expect(describeError(erro)).toContain("decisão não se sobrescreve");
    expect(isRevisionConflict(erro)).toBe(false);
  });

  it("recusa de etapa fora de ordem chega com o código estável da API", async () => {
    stub(() =>
      problema(
        409,
        "ROUND_STAGE_NOT_READY",
        "a rodada ainda não tem pacote de takeoff publicado",
        { stage: "takeoff" },
      ),
    );

    const erro = (await getTakeoff(TOKEN, ROUND).catch(
      (error: unknown) => error,
    )) as ApiError;

    expect(medicaoErrorCode(erro)).toBe("ROUND_STAGE_NOT_READY");
    expect(describeError(erro)).toContain("etapa ainda não está disponível");
  });

  it("corpo sem envelope legível não vira código inventado", async () => {
    stub(() => new Response("<html>500</html>", { status: 500 }));

    const erro = (await getRoundState(TOKEN, ROUND).catch(
      (error: unknown) => error,
    )) as ApiError;

    expect(erro.code).toBeNull();
    expect(medicaoErrorCode(erro)).toBeNull();
    expect(describeError(erro)).toContain("500");
  });
});

describe("imagem por URL assinada", () => {
  /**
   * A URL assinada vem no CORPO e vai direto no `src`: nenhuma busca autenticada de
   * imagem acontece, e nada dela é registrado.
   */
  it("o overlay chega com a URL no corpo e a idade declarada, sem segunda requisição", async () => {
    stub(() =>
      ok({
        round_id: ROUND,
        version: 12,
        image_url: "https://armazenamento.example/overlay?assinatura=x",
        image_sha256: "b".repeat(64),
        packet_sha256: "c".repeat(64),
        overlay_packet_sha256: "d".repeat(64),
        present: true,
        stale: true,
      }),
    );

    const overlay = await getTakeoffOverlay(TOKEN, ROUND);

    expect(chamadas).toHaveLength(1);
    expect(overlay.image_url).toContain("assinatura=x");
    expect(overlay.stale).toBe(true);
    expect(overlay.overlay_packet_sha256).not.toBe(overlay.packet_sha256);
  });
});

/**
 * A praça de várias folhas (F-046). O oráculo é o que SAIU no `fetch`: caminho sob a
 * rodada, `base_version` em toda mutação, `Idempotency-Key` por gesto e nenhuma identidade
 * carimbada pelo cliente.
 */
describe("a praça de várias folhas", () => {
  it("a leitura da praça é GET sob a rodada, sem chave de idempotência", async () => {
    await getWorksite(TOKEN, ROUND);

    expect(chamadas[0].url).toBe(`${BASE}/v1/valuation-rounds/${ROUND}/worksite`);
    expect(chamadas[0].init?.method ?? "GET").toBe("GET");
    expect(headersDaChamada()).not.toHaveProperty("Idempotency-Key");
  });

  it("promover folhas manda as páginas escolhidas, sem repetir e em ordem", async () => {
    await appendPlates(TOKEN, ROUND, "0197f2a0-0000-7000-8000-0000000000aa", [1, 3, 3, 5], 4);

    expect(chamadas[0].url).toBe(`${BASE}/v1/valuation-rounds/${ROUND}/plates`);
    expect(chamadas[0].init?.method).toBe("POST");
    expect(headersDaChamada()["Idempotency-Key"]).toMatch(/^[0-9a-f-]{36}$/i);
    expect(corpoDaChamada()).toEqual({
      base_version: 4,
      upload_id: "0197f2a0-0000-7000-8000-0000000000aa",
      page_numbers: [1, 3, 5],
    });
  });

  /**
   * Cada folha do lote é uma chamada paga: a lista marcada é a autorização, e ela sai como
   * foi marcada — nenhuma folha entra por conveniência do cliente.
   */
  it("o lote de leitura manda exatamente as folhas marcadas, com base_version", async () => {
    await createPlatesExtraction(TOKEN, ROUND, ["planta-geral", "detalhe", "planta-geral"], 9);

    expect(chamadas[0].url).toBe(
      `${BASE}/v1/valuation-rounds/${ROUND}/plates/extractions`,
    );
    expect(corpoDaChamada()).toEqual({
      base_version: 9,
      plate_ids: ["planta-geral", "detalhe"],
    });
    const corpo = corpoDaChamada();
    expect(corpo).not.toHaveProperty("reviewer_id");
    expect(corpo).not.toHaveProperty("declared_at");
  });

  it("a recusa da praça chega com o código estável e a folha citada nos detalhes", async () => {
    stub(() =>
      problema(409, "ROUND_STAGE_NOT_READY", "a praça só fecha com todas as folhas extraídas", {
        stage: "worksite",
        pending_plate_ids: ["detalhe-playground"],
      }),
    );

    const erro = (await getWorksite(TOKEN, ROUND).catch(
      (error: unknown) => error,
    )) as ApiError;

    expect(erro).toBeInstanceOf(ApiError);
    expect(medicaoErrorCode(erro)).toBe("ROUND_STAGE_NOT_READY");
    expect(erro.details.pending_plate_ids).toEqual(["detalhe-playground"]);
  });

  it("o teto da praça chega como recusa própria, e não como conflito de versão", async () => {
    stub(() =>
      problema(409, "ROUND_PLATE_LIMIT_REACHED", "a praça atingiu o limite de folhas por rodada", {
        limit: 12,
      }),
    );

    const erro = (await appendPlates(
      TOKEN,
      ROUND,
      "0197f2a0-0000-7000-8000-0000000000aa",
      [2],
      4,
    ).catch((error: unknown) => error)) as ApiError;

    expect(medicaoErrorCode(erro)).toBe("ROUND_PLATE_LIMIT_REACHED");
    expect(isRevisionConflict(erro)).toBe(false);
    expect(describeError(erro)).not.toContain("ROUND_PLATE_LIMIT_REACHED");
  });
});

/**
 * A folha em TODA leitura e em TODA decisão (F-046 T4c/T4d).
 *
 * O oráculo é o que saiu no `fetch`: URL com `plate_id` em query nas leituras, `plate_id`
 * no corpo nas decisões, e — a parte que mantém a rodada de uma prancha idêntica — nada
 * disso quando não há folha a nomear.
 */
describe("a folha em cada chamada da praça", () => {
  it("sem folha, as cinco leituras saem na URL de sempre, sem query nenhuma", async () => {
    await getPlate(TOKEN, ROUND);
    await getTakeoff(TOKEN, ROUND);
    await getTakeoffOverlay(TOKEN, ROUND);
    await getCodes(TOKEN, ROUND);
    await getSuggestions(TOKEN, ROUND);

    expect(chamadas.map((chamada) => chamada.url)).toEqual([
      `${BASE}/v1/valuation-rounds/${ROUND}/plate`,
      `${BASE}/v1/valuation-rounds/${ROUND}/takeoff`,
      `${BASE}/v1/valuation-rounds/${ROUND}/takeoff/overlay`,
      `${BASE}/v1/valuation-rounds/${ROUND}/code-assignments`,
      `${BASE}/v1/valuation-rounds/${ROUND}/code-suggestions`,
    ]);
  });

  it("com folha, as cinco leituras a nomeiam em query, já escapada", async () => {
    await getPlate(TOKEN, ROUND, "detalhe playground");
    await getTakeoff(TOKEN, ROUND, "detalhe");
    await getTakeoffOverlay(TOKEN, ROUND, "detalhe");
    await getCodes(TOKEN, ROUND, "detalhe");
    await getSuggestions(TOKEN, ROUND, "detalhe");

    expect(chamadas[0].url).toBe(
      `${BASE}/v1/valuation-rounds/${ROUND}/plate?plate_id=detalhe%20playground`,
    );
    expect(chamadas.slice(1).map((chamada) => chamada.url)).toEqual([
      `${BASE}/v1/valuation-rounds/${ROUND}/takeoff?plate_id=detalhe`,
      `${BASE}/v1/valuation-rounds/${ROUND}/takeoff/overlay?plate_id=detalhe`,
      `${BASE}/v1/valuation-rounds/${ROUND}/code-assignments?plate_id=detalhe`,
      `${BASE}/v1/valuation-rounds/${ROUND}/code-suggestions?plate_id=detalhe`,
    ]);
  });

  it("as quatro decisões levam a folha no CORPO, com base_version e chave de idempotência", async () => {
    await postTakeoffDecision(TOKEN, ROUND, {
      baseVersion: 4,
      plateId: "detalhe",
      decisions: [{ itemId: "ti_1", action: "confirm" }],
    });
    await postCodeDecision(TOKEN, ROUND, {
      itemId: "ti_1",
      action: "confirm",
      baseVersion: 5,
      plateId: "detalhe",
      code: "04.02.010",
    });
    await postCodeClosure(TOKEN, ROUND, {
      itemId: "ti_1",
      baseVersion: 6,
      plateId: "detalhe",
    });
    await postCodeRevocation(TOKEN, ROUND, {
      itemId: "ti_1",
      code: "04.02.010",
      baseVersion: 7,
      plateId: "detalhe",
      note: "código trocado por engano",
    });

    expect(chamadas.map((chamada) => chamada.url)).toEqual([
      `${BASE}/v1/valuation-rounds/${ROUND}/takeoff/decisions`,
      `${BASE}/v1/valuation-rounds/${ROUND}/code-assignments/decisions`,
      `${BASE}/v1/valuation-rounds/${ROUND}/code-assignments/closures`,
      `${BASE}/v1/valuation-rounds/${ROUND}/code-assignments/revocations`,
    ]);
    for (let indice = 0; indice < 4; indice += 1) {
      expect(corpoDaChamada(indice).plate_id).toBe("detalhe");
      expect(corpoDaChamada(indice).base_version).toBe(4 + indice);
      expect(headersDaChamada(indice)["Idempotency-Key"]).toMatch(/^[0-9a-f-]{36}$/i);
    }
  });
});

/**
 * A prévia e o ato do vínculo de identidade (F-046 T1/T4c). A prévia é LEITURA — nada é
 * gravado, a versão da rodada não anda —, e é ela que permite oferecer o ato sem que a
 * tela some nada.
 */
describe("o vínculo de identidade na praça", () => {
  const kept = { plate_id: "planta-geral", item_id: "ti_b3d5e820a7c14f69" };
  const discarded = { plate_id: "detalhe", item_id: "ti_5d2f83b60e4a1c97" };

  it("a prévia é POST sob a praça, sem base_version e sem nota", async () => {
    await previewIdentityLink(TOKEN, ROUND, { kept, discarded });

    expect(chamadas[0].url).toBe(
      `${BASE}/v1/valuation-rounds/${ROUND}/worksite/identity-links/preview`,
    );
    expect(chamadas[0].init?.method).toBe("POST");
    expect(corpoDaChamada()).toEqual({ kept, discarded });
  });

  /** Os totais chegam como TEXTO e são usados como texto: nada vira `number` aqui. */
  it("os totais da prévia chegam como string decimal, calculados pelo servidor", async () => {
    stub(() =>
      ok({
        round_id: ROUND,
        version: 7,
        worksite_key: "praca-sintetica-oeste",
        kept: { ...kept, label: "ALAMBRADO", unit: "m", status: "proposed", quantity: "40.00" },
        discarded: {
          ...discarded,
          label: "ALAMBRADO",
          unit: "m",
          status: "proposed",
          quantity: "40.00",
        },
        unit_mismatch: false,
        total_before: "80.00",
        total_after: "40.00",
      }),
    );

    const previa = await previewIdentityLink(TOKEN, ROUND, { kept, discarded });

    expect(previa.total_before).toBe("80.00");
    expect(previa.total_after).toBe("40.00");
    expect(typeof previa.total_before).toBe("string");
  });

  it("unidade divergente devolve os totais nulos, e nenhum número é fabricado", async () => {
    stub(() =>
      ok({
        round_id: ROUND,
        version: 7,
        worksite_key: "praca-sintetica-oeste",
        kept: { ...kept, label: "ALAMBRADO", unit: "m", status: "proposed", quantity: "40.00" },
        discarded: {
          ...discarded,
          label: "ALAMBRADO",
          unit: "m2",
          status: "proposed",
          quantity: "40.00",
        },
        unit_mismatch: true,
        total_before: null,
        total_after: null,
      }),
    );

    const previa = await previewIdentityLink(TOKEN, ROUND, { kept, discarded });

    expect(previa.unit_mismatch).toBe(true);
    expect(previa.total_before).toBeNull();
    expect(previa.total_after).toBeNull();
  });

  it("o ato leva base_version, nota e chave de idempotência, e nunca a identidade de quem declara", async () => {
    await declareIdentityLink(TOKEN, ROUND, {
      kept,
      discarded,
      baseVersion: 7,
      note: "mesmo trecho de alambrado do perímetro",
    });

    expect(chamadas[0].url).toBe(
      `${BASE}/v1/valuation-rounds/${ROUND}/worksite/identity-links`,
    );
    expect(headersDaChamada()["Idempotency-Key"]).toMatch(/^[0-9a-f-]{36}$/i);
    expect(corpoDaChamada()).toEqual({
      base_version: 7,
      kept,
      discarded,
      note: "mesmo trecho de alambrado do perímetro",
    });
    expect(corpoDaChamada()).not.toHaveProperty("declared_by");
    expect(corpoDaChamada()).not.toHaveProperty("declared_at");
  });

  /** A prévia recusa o MESMO que a declaração recusaria — é esse o ponto dela. */
  it("vínculo dentro da mesma folha é recusado na prévia, com o código do domínio", async () => {
    stub(() =>
      problema(422, "DOMAIN_VALIDATION_FAILED", "vínculo de identidade dentro da mesma folha", {
        code: "WORKSITE_LINK_SAME_PLATE",
      }),
    );

    const erro = (await previewIdentityLink(TOKEN, ROUND, {
      kept,
      discarded: { plate_id: "planta-geral", item_id: "ti_5d2f83b60e4a1c97" },
    }).catch((error: unknown) => error)) as ApiError;

    expect(medicaoErrorCode(erro)).toBe("WORKSITE_LINK_SAME_PLATE");
    expect(describeError(erro)).toContain("folhas diferentes");
  });
});
