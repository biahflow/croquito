import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "../api";
import {
  associatePlate,
  createPlateExtraction,
  createRound,
  getCodes,
  getRoundState,
  getTakeoff,
  getTakeoffOverlay,
  listRounds,
  postCalcBuild,
  postCodeDecision,
  postDossierBuild,
  postSuggestionsRecompute,
  postTakeoffDecision,
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
      itemId: "ti_af6f85a49ea0b93d",
      action: "confirm",
      baseVersion: 7,
      quantity: "18.40",
      note: "quantidade lida na prancha",
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
      item_id: "ti_af6f85a49ea0b93d",
      action: "confirm",
      quantity: "18.40",
      note: "quantidade lida na prancha",
    });
    // A quantidade viaja como TEXTO: um `Number()` no caminho perderia a escala escrita.
    expect(typeof body.quantity).toBe("string");
    for (const proibido of [
      "reviewer_id",
      "reviewer_role",
      "decided_at",
      "decision_id",
    ]) {
      expect(Object.keys(body)).not.toContain(proibido);
    }
  });

  it("cada mutação nasce com uma chave de idempotência própria", async () => {
    await postTakeoffDecision(TOKEN, ROUND, {
      itemId: "ti_af6f85a49ea0b93d",
      action: "reject",
      baseVersion: 7,
    });
    await postTakeoffDecision(TOKEN, ROUND, {
      itemId: "ti_af6f85a49ea0b93e",
      action: "reject",
      baseVersion: 8,
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
      itemId: "ti_af6f85a49ea0b93d",
      action: "confirm",
      baseVersion: 7,
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
