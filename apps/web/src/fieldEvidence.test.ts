/**
 * Lógica pura do painel de evidência de campo e o transporte das rotas T1/T2 (F-030 T3).
 *
 * O oráculo do transporte é o que SAIU no `fetch`: toda mutação prova `Idempotency-Key` e
 * `base_version`, o upload avulso prova presign→PUT→confirm com SHA-256, e as recusas
 * viram `ApiError` com o código estável. Nenhum filtro associa foto a leitura.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("./auth", () => ({
  renewAccessToken: vi.fn(async () => null),
  readLastRenewFailure: vi.fn(() => null),
}));

import {
  ApiError,
  getFieldEvidence,
  linkSurveyToJob,
  requestFieldPhotoReading,
  unlinkSurveyFromJob,
  uploadStandaloneFieldPhoto,
  type FieldEvidence,
  type FieldEvidencePhoto,
} from "./api";
import {
  ALL_ANCHORS,
  anchorLabel,
  anchorOptions,
  canRequestReading,
  filterPhotosByAnchor,
  isAnalysisSkipped,
  isReadingInFlight,
  photoReadings,
  qualityBadge,
  readingBadge,
} from "./fieldEvidence";

const TOKEN = "token-de-teste";
const JOB = "0197f2a0-0000-7000-8000-000000000001";

function photo(overrides: Partial<FieldEvidencePhoto> = {}): FieldEvidencePhoto {
  return {
    evidence_id: "media-1",
    origin: "survey",
    survey_id: "svy-1",
    sha256: "a".repeat(64),
    mime_type: "image/jpeg",
    anchors: [{ kind: "element", ref_id: "mureta oeste" }],
    anchor_text: null,
    captured_at: "2026-08-19T14:12:00Z",
    url: "https://storage.example/signed/media-1?sig=abc",
    analysis: null,
    classification: null,
    reading_status: "NOT_REQUESTED",
    classification_status: "NOT_REQUESTED",
    confirmed_values: [],
    ...overrides,
  };
}

describe("âncora e filtro", () => {
  it("rotula âncora tipada de levantamento e âncora livre de foto avulsa", () => {
    expect(anchorLabel(photo())).toBe("Elemento: mureta oeste");
    expect(
      anchorLabel(
        photo({ origin: "standalone", anchors: [], anchor_text: "recuo frontal" }),
      ),
    ).toBe("recuo frontal");
    expect(anchorLabel(photo({ anchors: [{ kind: "point", ref_id: "7" }] }))).toBe(
      "Ponto: 7",
    );
  });

  it("declara ausência de âncora em vez de inventar uma", () => {
    expect(
      anchorLabel(photo({ origin: "standalone", anchors: [], anchor_text: null })),
    ).toBe("Sem âncora declarada");
  });

  it("lista âncoras distintas na ordem de aparição", () => {
    const photos = [
      photo({ evidence_id: "a", anchors: [{ kind: "element", ref_id: "muro" }] }),
      photo({ evidence_id: "b", anchors: [{ kind: "point", ref_id: "7" }] }),
      photo({ evidence_id: "c", anchors: [{ kind: "element", ref_id: "muro" }] }),
    ];
    expect(anchorOptions(photos)).toEqual(["Elemento: muro", "Ponto: 7"]);
  });

  it("o filtro é recorte de exibição e nunca associa: só compara o rótulo declarado", () => {
    const photos = [
      photo({ evidence_id: "a", anchors: [{ kind: "element", ref_id: "muro" }] }),
      photo({ evidence_id: "b", anchors: [{ kind: "point", ref_id: "7" }] }),
    ];
    expect(filterPhotosByAnchor(photos, ALL_ANCHORS)).toHaveLength(2);
    expect(
      filterPhotosByAnchor(photos, "Elemento: muro").map((p) => p.evidence_id),
    ).toEqual(["a"]);
    // Âncora que não existe mais não esconde tudo por engano: cai para "todas".
    expect(filterPhotosByAnchor(photos, "sumiu")).toHaveLength(0);
  });
});

describe("pastilhas de estado", () => {
  it("qualidade sem achado é nitidez boa; com achado, o sinal traduzido", () => {
    expect(qualityBadge(photo({ analysis: { quality: { findings: [] } } }))).toEqual({
      label: "NITIDEZ BOA",
      tone: "ready",
    });
    expect(
      qualityBadge(
        photo({ analysis: { quality: { findings: ["PHOTO_UNDEREXPOSED"] } } }),
      ),
    ).toEqual({ label: "CONTRALUZ", tone: "blocked" });
    expect(qualityBadge(photo({ analysis: null }))).toBeNull();
  });

  it("leitura pulada e falha são neutras, nunca erro de domínio", () => {
    expect(readingBadge(photo({ reading_status: "SKIPPED_DISABLED" }))).toEqual({
      label: "LEITURA PULADA",
      tone: "neutral",
    });
    expect(readingBadge(photo({ reading_status: "FAILED_PERMANENT" }))).toEqual({
      label: "LEITURA FALHOU",
      tone: "neutral",
    });
    expect(readingBadge(photo({ reading_status: "PROCESSED" }))).toBeNull();
    expect(readingBadge(photo({ reading_status: "NOT_REQUESTED" }))).toBeNull();
  });

  it("distingue leitura pedível, em curso e pulada", () => {
    expect(canRequestReading(photo({ reading_status: "NOT_REQUESTED" }))).toBe(true);
    expect(canRequestReading(photo({ reading_status: "FAILED_TRANSIENT" }))).toBe(true);
    expect(canRequestReading(photo({ reading_status: "QUEUED" }))).toBe(false);
    expect(isReadingInFlight(photo({ reading_status: "QUEUED" }))).toBe(true);
    expect(isAnalysisSkipped(photo({ reading_status: "SKIPPED_NO_ENTITLEMENT" }))).toBe(
      true,
    );
  });

  it("as leituras são texto de rascunho e nunca número medido", () => {
    const readings = photoReadings(
      photo({
        analysis: {
          readings: [
            { id: "fpr_1", raw_text: "PLACA OBRA 12,50 M", confidence: "high" },
            { raw_text: "" },
            { nao_tem_raw: true },
          ],
        },
      }),
    );
    expect(readings).toHaveLength(1);
    expect(readings[0].raw_text).toBe("PLACA OBRA 12,50 M");
  });
});

// --- Transporte (o oráculo é o que saiu no fetch) ---

type Chamada = { url: string; init: RequestInit | undefined };
const chamadas: Chamada[] = [];

function ok(body: unknown = {}): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });
}

function problema(status: number, code: string): Response {
  return new Response(JSON.stringify({ detail: { code, detail: code } }), {
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

function headers(indice = 0): Record<string, string> {
  return (chamadas[indice]?.init?.headers ?? {}) as Record<string, string>;
}

function corpo(indice = 0): Record<string, unknown> {
  return JSON.parse(String(chamadas[indice]?.init?.body ?? "{}"));
}

const EVIDENCE: FieldEvidence = {
  job_id: JOB,
  version: 4,
  surveys: [],
  photos: [],
};

describe("transporte da evidência de campo", () => {
  beforeEach(() => {
    chamadas.length = 0;
    stub(() => ok(EVIDENCE));
  });
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.clearAllMocks();
  });

  it("GET field-evidence só autentica, sem mutação", async () => {
    await getFieldEvidence(TOKEN, JOB);
    expect(chamadas[0].url).toBe(`http://localhost:8000/v1/jobs/${JOB}/field-evidence`);
    expect(headers().Authorization).toBe(`Bearer ${TOKEN}`);
    expect(headers()).not.toHaveProperty("Idempotency-Key");
  });

  it("vincular manda base_version e Idempotency-Key e relê a evidência", async () => {
    await linkSurveyToJob(TOKEN, JOB, "svy-1", 4);
    expect(chamadas[0].url).toBe(
      `http://localhost:8000/v1/jobs/${JOB}/field-evidence/surveys/svy-1`,
    );
    expect(headers(0)["Idempotency-Key"]).toMatch(/^[0-9a-f-]{36}$/i);
    expect(corpo(0)).toEqual({ base_version: 4 });
    // Segundo GET reconfere a evidência depois do vínculo.
    expect(chamadas[1].url).toBe(
      `http://localhost:8000/v1/jobs/${JOB}/field-evidence`,
    );
  });

  it("desvincular usa a rota de unlink com a mesma guarda otimista", async () => {
    await unlinkSurveyFromJob(TOKEN, JOB, "svy-1", 5);
    expect(chamadas[0].url).toBe(
      `http://localhost:8000/v1/jobs/${JOB}/field-evidence/surveys/svy-1/unlink`,
    );
    expect(corpo(0)).toEqual({ base_version: 5 });
    expect(headers(0)["Idempotency-Key"]).toMatch(/^[0-9a-f-]{36}$/i);
  });

  it("pedir leitura posta base_version com Idempotency-Key na rota da origem", async () => {
    stub(() => ok({ analysis_id: "an-1", task: "reading", status: "QUEUED", version: 5 }));
    const state = await requestFieldPhotoReading(TOKEN, JOB, "standalone", "media-2", 4);
    expect(state.task).toBe("reading");
    expect(chamadas[0].url).toBe(
      `http://localhost:8000/v1/jobs/${JOB}/field-evidence/photos/standalone/media-2/reading`,
    );
    expect(corpo(0)).toEqual({ base_version: 4 });
    expect(headers(0)["Idempotency-Key"]).toMatch(/^[0-9a-f-]{36}$/i);
  });

  it("foto avulsa: presign com SHA-256, PUT direto e confirm, e recarrega", async () => {
    stub((call) => {
      if (call.url.endsWith("/photos/presign")) {
        return ok({
          photo_id: "pht-1",
          version: 5,
          sha256: "z".repeat(64),
          url: "https://storage.example/put/pht-1",
          headers: { "x-amz-meta": "1" },
          expires_at: "2026-08-25T00:00:00Z",
        });
      }
      return ok(EVIDENCE);
    });
    const file = new File([new Uint8Array([1, 2, 3])], "foto.jpg", {
      type: "image/jpeg",
    });
    await uploadStandaloneFieldPhoto(TOKEN, JOB, 4, file, "recuo frontal");

    const presign = corpo(0);
    expect(chamadas[0].url).toBe(
      `http://localhost:8000/v1/jobs/${JOB}/field-evidence/photos/presign`,
    );
    expect(presign.base_version).toBe(4);
    expect(presign.mime_type).toBe("image/jpeg");
    expect(presign.byte_size).toBe(3);
    expect(presign.anchor_text).toBe("recuo frontal");
    expect(String(presign.sha256)).toMatch(/^[0-9a-f]{64}$/);
    expect(headers(0)["Idempotency-Key"]).toMatch(/^[0-9a-f-]{36}$/i);

    // PUT direto no storage com os headers assinados, sem Authorization.
    expect(chamadas[1].url).toBe("https://storage.example/put/pht-1");
    expect(chamadas[1].init?.method).toBe("PUT");

    // Confirmar usa a versão devolvida pelo presign, não a base original.
    expect(chamadas[2].url).toBe(
      `http://localhost:8000/v1/jobs/${JOB}/field-evidence/photos/pht-1/confirm`,
    );
    expect(corpo(2)).toEqual({ base_version: 5 });
  });

  it("foto avulsa recusa MIME fora do contrato antes de tocar a rede", async () => {
    const file = new File([new Uint8Array([1])], "a.gif", { type: "image/gif" });
    await expect(
      uploadStandaloneFieldPhoto(TOKEN, JOB, 4, file, "âncora"),
    ).rejects.toThrow(/JPEG, PNG ou WebP/);
    expect(chamadas).toHaveLength(0);
  });

  it("foto avulsa exige âncora declarada antes da rede", async () => {
    const file = new File([new Uint8Array([1])], "a.jpg", { type: "image/jpeg" });
    await expect(
      uploadStandaloneFieldPhoto(TOKEN, JOB, 4, file, "   "),
    ).rejects.toThrow(/âncora/);
    expect(chamadas).toHaveLength(0);
  });

  it("conflito de versão vira ApiError com o código estável", async () => {
    stub(() => problema(409, "REVISION_CONFLICT"));
    const erro = await linkSurveyToJob(TOKEN, JOB, "svy-1", 3).catch(
      (e: unknown) => e,
    );
    expect(erro).toBeInstanceOf(ApiError);
    expect((erro as ApiError).status).toBe(409);
    expect((erro as ApiError).code).toBe("REVISION_CONFLICT");
  });

  it("levantamento não concluído recusa fechado", async () => {
    stub(() => problema(409, "SURVEY_NOT_COMPLETED"));
    const erro = await linkSurveyToJob(TOKEN, JOB, "svy-1", 4).catch(
      (e: unknown) => e,
    );
    expect((erro as ApiError).code).toBe("SURVEY_NOT_COMPLETED");
  });
});
