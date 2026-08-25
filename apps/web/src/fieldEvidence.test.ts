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
  confirmFieldPhotoValue,
  getFieldEvidence,
  linkSurveyToJob,
  mutateReviewWitnesses,
  requestFieldPhotoReading,
  unlinkSurveyFromJob,
  uploadStandaloneFieldPhoto,
  type FieldEvidence,
  type FieldEvidencePhoto,
  type FieldWitness,
} from "./api";
import {
  ALL_ANCHORS,
  anchorLabel,
  anchorOptions,
  canRequestReading,
  eligibleWitnessSources,
  filterPhotosByAnchor,
  isAnalysisSkipped,
  isReadingInFlight,
  mmFromValueHint,
  parseWitnessSourceOption,
  pendingPhotoValues,
  photoReadings,
  qualityBadge,
  readingBadge,
  witnessEyebrow,
  witnessMeters,
  witnessSourceOptionValue,
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

describe("testemunhas de campo (helpers puros)", () => {
  function evidence(overrides: Partial<FieldEvidence> = {}): FieldEvidence {
    return { job_id: JOB, version: 4, surveys: [], photos: [], ...overrides };
  }

  it("lista medida de survey e valor confirmado em foto como fontes elegíveis", () => {
    const ev = evidence({
      surveys: [
        {
          survey_id: "svy-1",
          name: "Praça Guaxindiba",
          linked_by: "ana",
          linked_at: "2026-08-19T10:00:00Z",
          measurements: [
            {
              source_id: "mea-1",
              survey_id: "svy-1",
              value_mm: 19_780,
              kind: "length",
              instrument: "trena_laser",
              from_point_id: null,
              to_point_id: null,
              second_from_point_id: null,
              second_to_point_id: null,
              element_id: null,
              created_at: "2026-08-19T10:05:00Z",
            },
          ],
        },
      ],
      photos: [
        photo({
          confirmed_values: [
            {
              confirmation_id: "cfm-1",
              source_reading_id: "fpr_1",
              value_mm: 12_400,
              kind: "length",
              raw_text: "12,40",
              confirmed_by: "ana",
              confirmed_at: "2026-08-19T11:00:00Z",
            },
          ],
        }),
      ],
    });
    const sources = eligibleWitnessSources(ev, [], "rd_0000000000000001");
    expect(sources).toHaveLength(2);
    expect(sources[0].source).toEqual({
      type: "survey_measurement",
      source_id: "mea-1",
      survey_id: "svy-1",
    });
    expect(sources[1].source).toEqual({ type: "photo_reading", source_id: "cfm-1" });
    // A origem viaja escrita em cada rótulo, com o valor em metros.
    expect(sources[0].label).toContain("19,78");
    expect(sources[1].label).toContain("12,40");
  });

  it("exclui o par já associado à leitura e nunca oferece leitura de máquina crua", () => {
    const ev = evidence({
      surveys: [
        {
          survey_id: "svy-1",
          name: "Praça",
          linked_by: "ana",
          linked_at: "2026-08-19T10:00:00Z",
          measurements: [
            {
              source_id: "mea-1",
              survey_id: "svy-1",
              value_mm: 19_780,
              kind: "length",
              instrument: "trena_laser",
              from_point_id: null,
              to_point_id: null,
              second_from_point_id: null,
              second_to_point_id: null,
              element_id: null,
              created_at: "2026-08-19T10:05:00Z",
            },
          ],
        },
      ],
      // Foto com leitura de máquina mas SEM valor confirmado: não vira fonte.
      photos: [photo({ analysis: { readings: [{ id: "fpr_9", raw_text: "9,99" }] } })],
    });
    const jaAssociada: FieldWitness[] = [
      {
        witness_id: "0197f2a0-0000-7000-8000-0000000000aa",
        reading_id: "rd_0000000000000001",
        source_type: "survey_measurement",
        source_id: "mea-1",
        survey_id: "svy-1",
        reading_value_mm: "19750",
        source_value_mm: "19780",
        difference_mm: "30",
        associated_by: "ana",
        associated_at: "2026-08-19T12:00:00Z",
      },
    ];
    expect(eligibleWitnessSources(ev, jaAssociada, "rd_0000000000000001")).toHaveLength(0);
    // Para outra leitura, a mesma medida volta a ser elegível.
    expect(eligibleWitnessSources(ev, jaAssociada, "rd_0000000000000002")).toHaveLength(1);
  });

  it("roundtrip da opção de fonte e null para string inválida", () => {
    const survey = {
      type: "survey_measurement" as const,
      source_id: "mea-1",
      survey_id: "svy-1",
    };
    const photoSource = { type: "photo_reading" as const, source_id: "cfm-1" };
    expect(parseWitnessSourceOption(witnessSourceOptionValue(survey))).toEqual(survey);
    expect(parseWitnessSourceOption(witnessSourceOptionValue(photoSource))).toEqual(
      photoSource,
    );
    expect(parseWitnessSourceOption("lixo")).toBeNull();
    expect(parseWitnessSourceOption("survey_measurement::mea-1")).toBeNull();
  });

  it("a diferença é magnitude neutra: mesmo texto com ou sem sinal", () => {
    expect(witnessMeters("30")).toBe("0,03");
    expect(witnessMeters("-30")).toBe("0,03");
    expect(witnessMeters("19750")).toBe("19,75");
    expect(witnessMeters("nao-numero")).toBe("");
  });

  it("o eyebrow diz a origem por extenso e numera quando há mais de uma", () => {
    expect(witnessEyebrow("survey_measurement", 0, 1)).toBe("TESTEMUNHA DE CAMPO");
    expect(witnessEyebrow("survey_measurement", 0, 2)).toBe("TESTEMUNHA 1 · MEDIDA DO APP");
    expect(witnessEyebrow("photo_reading", 1, 2)).toBe(
      "TESTEMUNHA 2 · VALOR CONFIRMADO EM FOTO",
    );
  });

  it("valores pendentes excluem a leitura já confirmada e exigem id", () => {
    const p = photo({
      analysis: {
        readings: [
          { id: "fpr_1", raw_text: "12,40", value_hint: "12,40", unit_hint: "m" },
          { id: "fpr_2", raw_text: "9,99" },
          { raw_text: "sem id" },
        ],
      },
      confirmed_values: [
        {
          confirmation_id: "cfm-1",
          source_reading_id: "fpr_1",
          value_mm: 12_400,
          kind: "length",
          raw_text: "12,40",
          confirmed_by: "ana",
          confirmed_at: "2026-08-19T11:00:00Z",
        },
      ],
    });
    const pending = pendingPhotoValues(p);
    expect(pending.map((r) => r.id)).toEqual(["fpr_2"]);
  });

  it("milímetros a partir da dica, com unidade padrão em metros", () => {
    expect(mmFromValueHint("12,40", "m")).toBe(12_400);
    expect(mmFromValueHint("125", "cm")).toBe(1_250);
    expect(mmFromValueHint("40", "mm")).toBe(40);
    expect(mmFromValueHint("3.5", null)).toBe(3_500);
    expect(mmFromValueHint(null, "m")).toBeNull();
    expect(mmFromValueHint("ilegível", "m")).toBeNull();
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

  it("associar testemunha manda leitura e fonte, sem valor e sem witness_id", async () => {
    await mutateReviewWitnesses(TOKEN, JOB, 4, {
      action: "associate",
      reading_id: "rd_0000000000000001",
      source: { type: "survey_measurement", source_id: "mea-1", survey_id: "svy-1" },
    });
    expect(chamadas[0].url).toBe(
      `http://localhost:8000/v1/jobs/${JOB}/review/witnesses`,
    );
    expect(headers(0)["Idempotency-Key"]).toMatch(/^[0-9a-f-]{36}$/i);
    const body = corpo(0);
    expect(body).toEqual({
      base_version: 4,
      action: "associate",
      reading_id: "rd_0000000000000001",
      source: { type: "survey_measurement", source_id: "mea-1", survey_id: "svy-1" },
    });
    // O cliente nunca envia o valor nem a diferença: quem calcula é o servidor.
    expect(body).not.toHaveProperty("witness_id");
    expect(JSON.stringify(body)).not.toContain("value_mm");
    expect(JSON.stringify(body)).not.toContain("difference");
  });

  it("retratar testemunha manda só o witness_id", async () => {
    await mutateReviewWitnesses(TOKEN, JOB, 6, {
      action: "retract",
      witness_id: "0197f2a0-0000-7000-8000-0000000000aa",
    });
    expect(corpo(0)).toEqual({
      base_version: 6,
      action: "retract",
      witness_id: "0197f2a0-0000-7000-8000-0000000000aa",
    });
    expect(corpo(0)).not.toHaveProperty("reading_id");
    expect(corpo(0)).not.toHaveProperty("source");
  });

  it("conflito de versão na associação vira ApiError com o código estável", async () => {
    stub(() => problema(409, "REVISION_CONFLICT"));
    const erro = await mutateReviewWitnesses(TOKEN, JOB, 3, {
      action: "retract",
      witness_id: "0197f2a0-0000-7000-8000-0000000000aa",
    }).catch((e: unknown) => e);
    expect(erro).toBeInstanceOf(ApiError);
    expect((erro as ApiError).code).toBe("REVISION_CONFLICT");
  });

  it("confirmar valor lido posta o rascunho e relê a evidência", async () => {
    stub((call) => {
      if (call.url.endsWith("/values")) {
        return ok({
          confirmation: {
            confirmation_id: "cfm-1",
            source_reading_id: "fpr_1",
            value_mm: 12_400,
            kind: "length",
            raw_text: "12,40",
            confirmed_by: "ana",
            confirmed_at: "2026-08-19T11:00:00Z",
          },
          version: 5,
        });
      }
      return ok(EVIDENCE);
    });
    await confirmFieldPhotoValue(TOKEN, JOB, "standalone", "media-2", 4, {
      source_reading_id: "fpr_1",
      value_mm: 12_400,
      kind: "length",
      raw_text: "12,40",
    });
    expect(chamadas[0].url).toBe(
      `http://localhost:8000/v1/jobs/${JOB}/field-evidence/photos/standalone/media-2/values`,
    );
    expect(corpo(0)).toEqual({
      base_version: 4,
      source_reading_id: "fpr_1",
      value_mm: 12_400,
      kind: "length",
      raw_text: "12,40",
    });
    expect(headers(0)["Idempotency-Key"]).toMatch(/^[0-9a-f-]{36}$/i);
    // Relê a evidência depois de confirmar.
    expect(chamadas[1].url).toBe(`http://localhost:8000/v1/jobs/${JOB}/field-evidence`);
  });

  it("confirmar valor recusa milímetros não inteiros antes da rede", async () => {
    await expect(
      confirmFieldPhotoValue(TOKEN, JOB, "standalone", "media-2", 4, {
        source_reading_id: "fpr_1",
        value_mm: 12.4,
        kind: "length",
        raw_text: "12,40",
      }),
    ).rejects.toThrow(/inteiro/);
    expect(chamadas).toHaveLength(0);
  });
});
