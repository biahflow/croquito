/**
 * Transporte dos atos de identidade de elemento (F-047 T7a), com `fetch` mockado.
 *
 * O que estes testes fixam é o contrato do lado do cliente: a rota chamada, o
 * `base_version` citado, a `Idempotency-Key` por gesto e — o que mais importa — que o
 * corpo da declaração NUNCA carrega `element_ref`. Quem cunha o nome do elemento é o
 * servidor; mandá-lo daqui é recusado com `ELEMENT_REF_NOT_ASSIGNABLE`.
 */
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("./auth", () => ({
  renewAccessToken: vi.fn(async () => "token-renovado"),
  readLastRenewFailure: vi.fn(() => null),
}));

import {
  ApiError,
  declareElement,
  listElementProposals,
  rejectElementProposal,
} from "./api";

type Chamada = { url: string; init: RequestInit | undefined };

function capturar(corpo: unknown, status = 200): Chamada[] {
  const chamadas: Chamada[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      chamadas.push({ url, init });
      return new Response(JSON.stringify(corpo), {
        status,
        headers: { "Content-Type": "application/json" },
      });
    }),
  );
  return chamadas;
}

function cabecalho(chamada: Chamada, nome: string): string | undefined {
  return (chamada.init?.headers as Record<string, string> | undefined)?.[nome];
}

function corpoEnviado(chamada: Chamada): Record<string, unknown> {
  return JSON.parse(String(chamada.init?.body)) as Record<string, unknown>;
}

const CENA = {
  id: "019538a1-0000-7000-8000-0000000000ce",
  job_id: "job-1",
  version: 8,
  entities: [],
};

afterEach(() => {
  vi.unstubAllGlobals();
  vi.clearAllMocks();
});

describe("listElementProposals", () => {
  it("lê a rota de propostas do job, sem escrever nada", async () => {
    const chamadas = capturar({ scene_version: 7, proposals: [] });

    const lista = await listElementProposals("token", "job-1");

    expect(chamadas[0]?.url).toContain("/v1/jobs/job-1/elements/proposals");
    expect(chamadas[0]?.init?.method).toBeUndefined();
    expect(lista.scene_version).toBe(7);
  });
});

describe("declareElement", () => {
  it("cita base_version, manda Idempotency-Key e NÃO manda element_ref", async () => {
    const chamadas = capturar({
      act: "declared",
      element_ref: "EL-001",
      entity_ids: ["a", "b"],
      acted_by_role: "engineer",
      acted_at: "2026-03-04T14:32:00Z",
      scene: CENA,
    });

    const ato = await declareElement("token", "job-1", {
      base_version: 7,
      entity_ids: ["a", "b"],
      reason: "polígono e rótulo são o mesmo piso",
    });

    const chamada = chamadas[0]!;
    expect(chamada.url).toContain("/v1/jobs/job-1/elements");
    expect(chamada.init?.method).toBe("POST");
    expect(cabecalho(chamada, "Idempotency-Key")).toMatch(/[0-9a-f-]{36}/);
    const corpo = corpoEnviado(chamada);
    expect(corpo["base_version"]).toBe(7);
    expect(corpo["entity_ids"]).toEqual(["a", "b"]);
    expect(corpo).not.toHaveProperty("element_ref");
    // Sem nome escrito, o campo NÃO é enviado: `""` é recusado pelo servidor, e declarar
    // sem rótulo é omitir (F-047 T2b).
    expect(corpo).not.toHaveProperty("label");
    expect(ato.element_ref).toBe("EL-001");
    expect(ato.scene.version).toBe(8);
  });

  it("manda o rótulo legível quando a pessoa escreveu um, no MESMO ato", async () => {
    const chamadas = capturar({
      act: "declared",
      element_ref: "EL-001",
      label: "Alambrado da quadra",
      entity_ids: ["a"],
      acted_by_role: "engineer",
      acted_at: "2026-03-04T14:32:00Z",
      scene: CENA,
    });

    const ato = await declareElement("token", "job-1", {
      base_version: 7,
      entity_ids: ["a"],
      reason: "o alambrado inteiro",
      label: "Alambrado da quadra",
    });

    expect(corpoEnviado(chamadas[0]!)["label"]).toBe("Alambrado da quadra");
    expect(ato.label).toBe("Alambrado da quadra");
    // E continua sem cunhar nome de identidade do lado do cliente.
    expect(corpoEnviado(chamadas[0]!)).not.toHaveProperty("element_ref");
  });

  it("cada gesto leva uma Idempotency-Key própria", async () => {
    const chamadas = capturar({
      act: "declared",
      element_ref: "EL-001",
      entity_ids: ["a"],
      acted_by_role: "engineer",
      acted_at: "2026-03-04T14:32:00Z",
      scene: CENA,
    });

    await declareElement("token", "job-1", {
      base_version: 7,
      entity_ids: ["a"],
      reason: "primeiro ato",
    });
    await declareElement("token", "job-1", {
      base_version: 8,
      entity_ids: ["b"],
      reason: "segundo ato",
    });

    expect(cabecalho(chamadas[0]!, "Idempotency-Key")).not.toBe(
      cabecalho(chamadas[1]!, "Idempotency-Key"),
    );
  });

  it("a recusa de camadas do servidor chega com código e detalhes preservados", async () => {
    capturar(
      {
        detail: {
          code: "ELEMENT_REF_LAYER_MISMATCH",
          detail: "Um elemento não mistura camadas; declare um grupo por camada.",
          details: { layers: ["ALAMBRADO", "PISO"] },
        },
      },
      422,
    );

    const erro = await declareElement("token", "job-1", {
      base_version: 7,
      entity_ids: ["a", "b"],
      reason: "grupo que mistura camadas",
    }).catch((e: unknown) => e);

    expect(erro).toBeInstanceOf(ApiError);
    expect((erro as ApiError).code).toBe("ELEMENT_REF_LAYER_MISMATCH");
    expect((erro as ApiError).details["layers"]).toEqual(["ALAMBRADO", "PISO"]);
  });
});

describe("rejectElementProposal", () => {
  it("cita a proposta na rota, manda motivo e NÃO cita base_version", async () => {
    const chamadas = capturar({
      proposal_id: "elp_abc",
      entity_ids: ["a", "b"],
      rejected_by_role: "engineer",
      rejected_at: "2026-03-04T14:40:00Z",
    });

    const recusa = await rejectElementProposal("token", "job-1", "elp_abc", {
      reason: "agrupou dois alambrados distintos",
    });

    const chamada = chamadas[0]!;
    expect(chamada.url).toContain(
      "/v1/jobs/job-1/elements/proposals/elp_abc/rejections",
    );
    expect(chamada.init?.method).toBe("POST");
    expect(cabecalho(chamada, "Idempotency-Key")).toMatch(/[0-9a-f-]{36}/);
    const corpo = corpoEnviado(chamada);
    expect(corpo["reason"]).toBe("agrupou dois alambrados distintos");
    // O ato não toca a cena: não há concorrência otimista a conferir.
    expect(corpo).not.toHaveProperty("base_version");
    expect(recusa.rejected_by_role).toBe("engineer");
  });

  it("proposta já recusada volta como código estável, não como falha genérica", async () => {
    capturar(
      {
        detail: {
          code: "ELEMENT_PROPOSAL_NOT_FOUND",
          detail: "Esta proposta já foi recusada; ela não é mais oferecida.",
        },
      },
      404,
    );

    const erro = await rejectElementProposal("token", "job-1", "elp_abc", {
      reason: "motivo qualquer",
    }).catch((e: unknown) => e);

    expect((erro as ApiError).code).toBe("ELEMENT_PROPOSAL_NOT_FOUND");
  });
});
