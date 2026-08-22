/**
 * O oráculo destes testes é o que SAIU no `fetch`: caminho, método, corpo e cabeçalhos.
 * A jornada de plataforma grava autorização contratual, então o que viaja no `PUT` é o
 * registro do ato — e é ele que precisa estar fixado por teste, não a resposta simulada.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "../api";
import {
  entitlementBody,
  fetchMe,
  getEntitlement,
  journeyEntitlementBody,
  listJourneys,
  listReferenceCatalogs,
  listTenants,
  publishCatalogBody,
  publishReferenceCatalog,
  referenceCatalogPresignBody,
  setEntitlement,
  setJourneyEntitlement,
  uploadReferenceCatalog,
  withdrawReferenceCatalog,
} from "./api";
import { describeAcervoError, describeError } from "./labels";

/** Base do build de teste: `VITE_API_BASE_URL` não é declarada neste ambiente. */
const BASE = "http://localhost:8000";
const TOKEN = "token-de-teste";

type Chamada = { url: string; init: RequestInit | undefined };

const chamadas: Chamada[] = [];

function ok(body: unknown = {}): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });
}

/** Envelope de erro da API: `{detail: {code, detail, details}}`, aninhado. */
function problema(status: number, code: string, detail: string): Response {
  return new Response(JSON.stringify({ detail: { code, detail } }), {
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

describe("leituras da plataforma", () => {
  it("perguntam quem é o principal sem chave de idempotência", async () => {
    stub(() => ok({ subject: "op", tenant_id: "acme", roles: ["platform_operator"] }));

    const me = await fetchMe(TOKEN);

    expect(me.roles).toEqual(["platform_operator"]);
    expect(chamadas[0].url).toBe(`${BASE}/v1/me`);
    expect(headersDaChamada().Authorization).toBe(`Bearer ${TOKEN}`);
    expect(headersDaChamada()).not.toHaveProperty("Idempotency-Key");
  });

  it("desembrulham a lista de tenants na coleção que a tela percorre", async () => {
    stub(() =>
      ok({
        tenants: [
          {
            tenant_id: "acme",
            enabled: true,
            agreement_reference: "contrato 05/2024",
            authorized_at: "2026-08-19T12:00:00Z",
            revoked_at: null,
          },
        ],
      }),
    );

    const tenants = await listTenants(TOKEN);

    expect(chamadas[0].url).toBe(`${BASE}/v1/platform/tenants`);
    expect(tenants).toHaveLength(1);
    expect(tenants[0].tenant_id).toBe("acme");
  });

  it("leem o estado de um tenant pelo identificador, escapado no caminho", async () => {
    await getEntitlement(TOKEN, "tenant com espaço");

    expect(chamadas[0].url).toBe(
      `${BASE}/v1/platform/tenants/tenant%20com%20espa%C3%A7o/ai-processing-entitlement`,
    );
    expect(chamadas[0].init?.method).toBeUndefined();
  });
});

describe("mutação do entitlement", () => {
  it("ativa com PUT, referência do contrato e Idempotency-Key", async () => {
    await setEntitlement(TOKEN, {
      tenantId: "acme",
      enabled: true,
      agreementReference: "contrato 05/2024",
    });

    expect(chamadas[0].url).toBe(
      `${BASE}/v1/platform/tenants/acme/ai-processing-entitlement`,
    );
    expect(chamadas[0].init?.method).toBe("PUT");
    expect(headersDaChamada()["Content-Type"]).toBe("application/json");
    expect(headersDaChamada()["Idempotency-Key"]).toMatch(/^[0-9a-f-]{36}$/i);
    expect(corpoDaChamada()).toEqual({
      enabled: true,
      agreement_reference: "contrato 05/2024",
    });
  });

  it("dá uma chave de idempotência NOVA a cada gesto", async () => {
    await setEntitlement(TOKEN, {
      tenantId: "acme",
      enabled: true,
      agreementReference: "contrato 05/2024",
    });
    await setEntitlement(TOKEN, {
      tenantId: "acme",
      enabled: true,
      agreementReference: "contrato 05/2024",
    });

    expect(headersDaChamada(0)["Idempotency-Key"]).not.toBe(
      headersDaChamada(1)["Idempotency-Key"],
    );
  });

  it("revoga sem reescrever a referência do contrato que autorizou", async () => {
    await setEntitlement(TOKEN, {
      tenantId: "acme",
      enabled: false,
      agreementReference: "algo digitado na tela",
    });

    expect(corpoDaChamada()).toEqual({ enabled: false });
  });
});

describe("entitlementBody", () => {
  it("tira espaço das pontas da referência", () => {
    expect(
      entitlementBody({
        tenantId: "acme",
        enabled: true,
        agreementReference: "  contrato 05/2024  ",
      }),
    ).toEqual({ enabled: true, agreement_reference: "contrato 05/2024" });
  });

  /**
   * Referência vazia não vira string vazia no corpo: ela simplesmente não vai, e o
   * servidor recusa com `AGREEMENT_REFERENCE_REQUIRED`. Quem decide se o ato é válido é
   * a regra do backend, e a tela mostra a frase dessa recusa.
   */
  it("não inventa referência quando o campo está vazio", () => {
    expect(
      entitlementBody({ tenantId: "acme", enabled: true, agreementReference: "   " }),
    ).toEqual({ enabled: true });
    expect(entitlementBody({ tenantId: "acme", enabled: true })).toEqual({
      enabled: true,
    });
  });
});

describe("recusas legíveis", () => {
  it("o 403 sem papel vira frase, não código cru", async () => {
    stub(() =>
      problema(403, "FORBIDDEN", "Papel platform_operator é obrigatório."),
    );

    const erro = await listTenants(TOKEN).catch((e: unknown) => e);

    expect(erro).toBeInstanceOf(ApiError);
    expect((erro as ApiError).status).toBe(403);
    expect(describeError(erro)).toContain("papel de operador de plataforma");
    expect(describeError(erro)).toContain("Nada foi alterado");
  });

  it("ativar sem referência devolve a frase da regra que recusou", async () => {
    stub(() =>
      problema(
        422,
        "AGREEMENT_REFERENCE_REQUIRED",
        "Ativar processamento por IA exige a referência lógica do contrato.",
      ),
    );

    const erro = await setEntitlement(TOKEN, {
      tenantId: "acme",
      enabled: true,
    }).catch((e: unknown) => e);

    expect(describeError(erro)).toContain("referência do contrato");
    expect(describeError(erro)).toContain("Nada foi gravado");
  });

  it("revogar tenant nunca autorizado é dito como tal", async () => {
    stub(() => problema(404, "NOT_FOUND", "Autorização contratual não encontrada."));

    const erro = await setEntitlement(TOKEN, {
      tenantId: "acme",
      enabled: false,
    }).catch((e: unknown) => e);

    expect(describeError(erro)).toContain("nunca teve autorização contratual");
  });
});

describe("disponibilidade de jornada (F-034)", () => {
  it("lê o ambiente e as autorizações numa chamada só, sem chave de idempotência", async () => {
    stub(() =>
      ok({
        journeys: [
          { journey: "croqui", state: "disabled" },
          { journey: "medicao", state: "enabled" },
          { journey: "orcamento", state: "pilot" },
        ],
        entitlements: [
          {
            tenant_id: "tenant-scalle",
            journey: "orcamento",
            enabled: true,
            agreement_reference: "contrato 05/2024 — aditivo 3",
            authorized_by: "daniel",
            authorized_at: "2026-08-22T09:14:00Z",
            revoked_at: null,
          },
        ],
      }),
    );

    const resposta = await listJourneys(TOKEN);

    expect(chamadas[0].url).toBe(`${BASE}/v1/platform/journeys`);
    expect(chamadas[0].init?.method).toBeUndefined();
    expect(headersDaChamada()).not.toHaveProperty("Idempotency-Key");
    expect(resposta.journeys).toHaveLength(3);
    expect(resposta.entitlements[0].authorized_by).toBe("daniel");
  });

  it("autoriza no par (tenant, jornada) da URL, com contrato e chave por gesto", async () => {
    await setJourneyEntitlement(TOKEN, {
      tenantId: "tenant com espaço",
      journey: "orcamento",
      enabled: true,
      agreementReference: "  contrato 05/2024  ",
    });

    expect(chamadas[0].url).toBe(
      `${BASE}/v1/platform/tenants/tenant%20com%20espa%C3%A7o/journey-entitlements/orcamento`,
    );
    expect(chamadas[0].init?.method).toBe("PUT");
    expect(headersDaChamada()).toHaveProperty("Idempotency-Key");
    // A referência viaja sem espaço nas pontas; o par nunca vai no corpo.
    expect(corpoDaChamada()).toEqual({
      enabled: true,
      agreement_reference: "contrato 05/2024",
    });
  });

  /**
   * Revogar NÃO reescreve o contrato: o que autorizou continua sendo o que está gravado, e
   * mandar o que estava na tela apagaria o registro do ato original.
   */
  it("revoga sem mandar referência de contrato, mesmo com uma preenchida", () => {
    expect(
      journeyEntitlementBody({
        tenantId: "acme",
        journey: "croqui",
        enabled: false,
        agreementReference: "contrato 05/2024",
      }),
    ).toEqual({ enabled: false });
  });

  /**
   * Referência vazia não vira `agreement_reference: ""`: ela some do corpo e a recusa vem
   * do servidor com o código estável, como no entitlement de IA.
   */
  it("não inventa referência vazia ao autorizar", () => {
    expect(
      journeyEntitlementBody({
        tenantId: "acme",
        journey: "croqui",
        enabled: true,
        agreementReference: "   ",
      }),
    ).toEqual({ enabled: true });
  });
});

/**
 * Acervo de catálogos de referência (F-037).
 *
 * O oráculo continua sendo o que SAIU no `fetch`. Duas coisas são fixadas aqui porque um
 * erro nelas só apareceria como `422` em produção: o presign do acervo NÃO manda
 * `content_type`, e a publicação manda dois campos e nada mais.
 */
describe("acervo de catálogos", () => {
  /** Um `catalog.json` sintético; o conteúdo não importa, o digest dele sim. */
  function catalogFile(conteudo = '{"source_label":"SCO"}'): File {
    return new File([conteudo], "catalog.json", { type: "application/json" });
  }

  it("lê o acervo inteiro numa chamada, sem chave de idempotência", async () => {
    stub(() =>
      ok({
        catalogs: [
          {
            reference_catalog_id: "0198-aaa",
            display_name: "SCO-Rio FGV06 desonerado",
            origin: "sco",
            reference_month: "2026-07",
            entry_count: 4865,
            object_sha256: "6f314c9".padEnd(64, "0"),
            source_sha256: "a17b3e0".padEnd(64, "0"),
            available: true,
            published_by: "daniel",
            published_at: "2026-08-22T09:14:00Z",
            withdrawn_at: null,
          },
        ],
      }),
    );

    const catalogos = await listReferenceCatalogs(TOKEN);

    expect(chamadas[0].url).toBe(`${BASE}/v1/platform/reference-catalogs`);
    expect(chamadas[0].init?.method).toBeUndefined();
    expect(headersDaChamada()).not.toHaveProperty("Idempotency-Key");
    expect(catalogos).toHaveLength(1);
    expect(catalogos[0].display_name).toBe("SCO-Rio FGV06 desonerado");
  });

  /**
   * O tipo é FIXO na rota (`application/json`) e o corpo recusa campo desconhecido:
   * mandar `content_type` "por garantia" derrubaria a publicação com `422`.
   */
  it("o corpo do presign não carrega content_type", () => {
    expect(
      referenceCatalogPresignBody({
        filename: "catalog.json",
        sizeBytes: 1234,
        sha256: "a".repeat(64),
      }),
    ).toEqual({
      filename: "catalog.json",
      size_bytes: 1234,
      sha256: "a".repeat(64),
    });
  });

  it("o corpo da publicação tem dois campos, com o nome sem espaço nas pontas", () => {
    expect(
      publishCatalogBody({
        uploadId: "0198-upload",
        displayName: "  SINAPI RJ desonerado  ",
      }),
    ).toEqual({
      upload_id: "0198-upload",
      display_name: "SINAPI RJ desonerado",
    });
  });

  it("sobe pelo presign da plataforma e faz o PUT direto no store", async () => {
    stub((call) =>
      call.url.endsWith("/presign")
        ? ok({
            upload_id: "0198-upload",
            url: "https://store.example/objeto?assinado",
            headers: { "Content-Type": "application/json" },
          })
        : ok(),
    );

    const upload = await uploadReferenceCatalog(TOKEN, catalogFile());

    // A rota é a da PLATAFORMA, não `/v1/uploads/presign`: o presign do croqui está sob o
    // portão de disponibilidade de jornada, e o acervo não pode depender dele.
    expect(chamadas[0].url).toBe(
      `${BASE}/v1/platform/reference-catalogs/presign`,
    );
    expect(chamadas[0].init?.method).toBe("POST");
    expect(headersDaChamada(0)["Idempotency-Key"]).toMatch(/^[0-9a-f-]{36}$/i);
    expect(corpoDaChamada(0)).not.toHaveProperty("content_type");
    // O byte vai direto ao store, com os cabeçalhos que o servidor assinou.
    expect(chamadas[1].url).toBe("https://store.example/objeto?assinado");
    expect(chamadas[1].init?.method).toBe("PUT");
    expect(upload.uploadId).toBe("0198-upload");
    expect(upload.objectSha256).toMatch(/^[a-f0-9]{64}$/);
  });

  /** O digest é do conteúdo, não do nome: dois arquivos diferentes não colidem. */
  it("calcula o digest do conteúdo do arquivo", async () => {
    stub((call) =>
      call.url.endsWith("/presign")
        ? ok({ upload_id: "u", url: "https://store.example/o", headers: {} })
        : ok(),
    );

    const primeiro = await uploadReferenceCatalog(TOKEN, catalogFile("{}"));
    const segundo = await uploadReferenceCatalog(
      TOKEN,
      catalogFile('{"outro":1}'),
    );

    expect(primeiro.objectSha256).not.toBe(segundo.objectSha256);
  });

  it("o PUT que não conclui vira recusa com código próprio, e nada é publicado", async () => {
    stub((call) =>
      call.url.endsWith("/presign")
        ? ok({ upload_id: "u", url: "https://store.example/o", headers: {} })
        : new Response("", { status: 503 }),
    );

    const erro = await uploadReferenceCatalog(TOKEN, catalogFile()).catch(
      (e: unknown) => e,
    );

    expect(erro).toBeInstanceOf(ApiError);
    expect((erro as ApiError).code).toBe("UPLOAD_TRANSFER_FAILED");
    expect(describeAcervoError(erro)).toContain("Nada foi publicado");
    // A publicação nem chega a sair: só o presign e o PUT recusado.
    expect(chamadas).toHaveLength(2);
  });

  it("publica com POST, dois campos e chave de idempotência", async () => {
    await publishReferenceCatalog(TOKEN, {
      uploadId: "0198-upload",
      displayName: "SINAPI RJ desonerado",
    });

    expect(chamadas[0].url).toBe(`${BASE}/v1/platform/reference-catalogs`);
    expect(chamadas[0].init?.method).toBe("POST");
    expect(headersDaChamada()["Content-Type"]).toBe("application/json");
    expect(headersDaChamada()["Idempotency-Key"]).toMatch(/^[0-9a-f-]{36}$/i);
    expect(corpoDaChamada()).toEqual({
      upload_id: "0198-upload",
      display_name: "SINAPI RJ desonerado",
    });
  });

  /** Sem corpo: o ato é inteiramente identificado pela rota. */
  it("retira de circulação pelo identificador escapado, sem corpo", async () => {
    await withdrawReferenceCatalog(TOKEN, "0198 aaa/bbb");

    expect(chamadas[0].url).toBe(
      `${BASE}/v1/platform/reference-catalogs/0198%20aaa%2Fbbb/withdraw`,
    );
    expect(chamadas[0].init?.method).toBe("POST");
    expect(chamadas[0].init?.body).toBeUndefined();
    expect(headersDaChamada()).toHaveProperty("Idempotency-Key");
    expect(headersDaChamada()).not.toHaveProperty("Content-Type");
  });

  it("dá uma chave de idempotência NOVA a cada retirada", async () => {
    await withdrawReferenceCatalog(TOKEN, "a");
    await withdrawReferenceCatalog(TOKEN, "a");

    expect(headersDaChamada(0)["Idempotency-Key"]).not.toBe(
      headersDaChamada(1)["Idempotency-Key"],
    );
  });
});

describe("recusas do acervo", () => {
  it("republicar o mesmo conteúdo cita o digest que a tela subiu", async () => {
    stub(() =>
      problema(
        409,
        "REFERENCE_CATALOG_ALREADY_PUBLISHED",
        "Este conteúdo já está no acervo.",
      ),
    );

    const erro = await publishReferenceCatalog(TOKEN, {
      uploadId: "u",
      displayName: "SCO-Rio FGV06 desonerado",
    }).catch((e: unknown) => e);

    const frase = describeAcervoError(erro, "6f314c9".padEnd(64, "0"));
    expect(frase).toContain("já está publicada");
    expect(frase).toContain("sha256 6f314c900000");
    expect(frase).toContain("data-base nova é uma entrada nova");
  });

  /** Sem o digest a frase segue verdadeira e não inventa conteúdo nenhum. */
  it("a mesma recusa sem digest não fabrica um", async () => {
    stub(() =>
      problema(409, "REFERENCE_CATALOG_ALREADY_PUBLISHED", "Já está no acervo."),
    );

    const erro = await publishReferenceCatalog(TOKEN, {
      uploadId: "u",
      displayName: "qualquer",
    }).catch((e: unknown) => e);

    const frase = describeAcervoError(erro);
    expect(frase).toContain("já está publicada");
    expect(frase).not.toContain("sha256");
  });

  /** A origem vem do `details` do SERVIDOR; a tela nunca abre o `catalog.json`. */
  it("origem que a plataforma não distribui é nomeada pelo servidor", async () => {
    vi.stubGlobal("fetch", () =>
      Promise.resolve(
        new Response(
          JSON.stringify({
            detail: {
              code: "REFERENCE_CATALOG_ORIGIN_NOT_PUBLISHABLE",
              detail: "A plataforma não distribui tabela desta origem.",
              details: { origin: "emop" },
            },
          }),
          { status: 422 },
        ),
      ),
    );

    const erro = await publishReferenceCatalog(TOKEN, {
      uploadId: "u",
      displayName: "EMOP RJ",
    }).catch((e: unknown) => e);

    expect(describeAcervoError(erro)).toContain("de origem emop");
    expect(describeAcervoError(erro)).toContain("Nada foi publicado");
  });

  /**
   * `NOT_FOUND` significa duas coisas diferentes nesta jornada. No acervo ele não pode
   * virar a frase do tenant nunca autorizado — seria a explicação da seção errada.
   */
  it("catálogo inexistente não vira a frase do tenant nunca autorizado", async () => {
    stub(() => problema(404, "NOT_FOUND", "Catálogo do acervo não encontrado."));

    const erro = await withdrawReferenceCatalog(TOKEN, "0198-sumiu").catch(
      (e: unknown) => e,
    );

    expect(describeAcervoError(erro)).toContain("não está no acervo");
    expect(describeAcervoError(erro)).not.toContain("autorização contratual");
    // A seção de tenants continua com a frase dela.
    expect(describeError(erro)).toContain("nunca teve autorização contratual");
  });

  /** Código que a tela não conhece nunca vira frase inventada. */
  it("código desconhecido cai na frase do transporte, com o código dentro", async () => {
    stub(() => problema(418, "CODIGO_QUE_NAO_EXISTE", "Recusa nova."));

    const erro = await listReferenceCatalogs(TOKEN).catch((e: unknown) => e);

    expect(describeAcervoError(erro)).toContain("CODIGO_QUE_NAO_EXISTE");
  });
});
