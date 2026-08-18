import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  fetchImageObjectUrl,
  getState,
  MedicaoApiError,
  PLATE_IMAGE_PATH,
  plateImageUrl,
  postSuggestionsRecompute,
  readProblem,
  SESSION_REJECTED_CODE,
  setAccessTokenProvider,
  STATE_MOVED_CODE,
  uploadPlate,
} from "./api";
import { isStateMoved } from "./errors";

function problemResponse(
  status: number,
  body: Record<string, unknown>,
): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/problem+json" },
  });
}

describe("readProblem", () => {
  it("preserva o código estável, a mensagem e os detalhes da recusa do domínio", async () => {
    const error = await readProblem(
      problemResponse(422, {
        code: "TAKEOFF_ITEM_ALREADY_REVIEWED",
        detail: "item de takeoff já revisado não pode ser sobrescrito",
        details: { id: "ti_af6f85a49ea0b93d" },
      }),
    );

    expect(error).toBeInstanceOf(MedicaoApiError);
    expect(error.code).toBe("TAKEOFF_ITEM_ALREADY_REVIEWED");
    expect(error.status).toBe(422);
    expect(error.detail).toContain("já revisado");
    expect(error.details).toEqual({ id: "ti_af6f85a49ea0b93d" });
  });

  it("reconhece o conflito da guarda otimista com os dois digests", async () => {
    const error = await readProblem(
      problemResponse(409, {
        code: STATE_MOVED_CODE,
        detail: "o artefato mudou depois da leitura; recarregue antes de decidir de novo",
        details: {
          artifact: "takeoff-packet.json",
          base_sha256: "a".repeat(64),
          current_sha256: "b".repeat(64),
        },
      }),
    );

    expect(isStateMoved(error)).toBe(true);
    expect(error.details.current_sha256).toBe("b".repeat(64));
  });

  it("corpo sem envelope não vira mensagem inventada", async () => {
    const error = await readProblem(new Response("<html>500</html>", { status: 500 }));

    expect(error.code).toBe("LOCAL_RESPONSE_UNREADABLE");
    expect(error.status).toBe(500);
    expect(isStateMoved(error)).toBe(false);
  });

  it("recusa de sessão sem envelope é dita como sessão, não como formato", async () => {
    const error = await readProblem(new Response("", { status: 401 }));

    expect(error.code).toBe(SESSION_REJECTED_CODE);
    expect(error.status).toBe(401);
  });

  it("envelope do servidor vence o código local, inclusive em 401", async () => {
    const error = await readProblem(
      problemResponse(401, {
        code: "MEDICAO_ROLE_REQUIRED",
        detail: "o papel orcamentista é exigido nesta rota",
        details: {},
      }),
    );

    expect(error.code).toBe("MEDICAO_ROLE_REQUIRED");
  });

  it("reconhece a recusa de segunda prancha na mesma rodada", async () => {
    const error = await readProblem(
      problemResponse(409, {
        code: "LOCAL_ROUND_ALREADY_HAS_PLATE",
        detail: "esta rodada já tem prancha; uma rodada é uma prancha",
        details: { reason: "a rodada já tem pacote de takeoff publicado" },
      }),
    );

    expect(error.code).toBe("LOCAL_ROUND_ALREADY_HAS_PLATE");
    expect(error.status).toBe(409);
    expect(isStateMoved(error)).toBe(false);
    expect(error.details.reason).toBe("a rodada já tem pacote de takeoff publicado");
  });

  it("reconhece a recusa de upload inválido, com o motivo nos detalhes", async () => {
    const error = await readProblem(
      problemResponse(422, {
        code: "LOCAL_UPLOAD_INVALID",
        detail: "o arquivo enviado não é um PDF de prancha aceitável",
        details: { reason: "o arquivo precisa ser um PDF (.pdf)" },
      }),
    );

    expect(error.code).toBe("LOCAL_UPLOAD_INVALID");
    expect(error.status).toBe(422);
    expect(error.details.reason).toBe("o arquivo precisa ser um PDF (.pdf)");
  });
});

/**
 * Injeção do token da sessão (modo hospedado, ADR-0026). O oráculo é o que sai no `fetch`:
 * o módulo de API não conhece OIDC, ele só pergunta o token a quem tem a sessão.
 */
describe("setAccessTokenProvider", () => {
  const chamadas: { url: string; init: RequestInit | undefined }[] = [];

  beforeEach(() => {
    chamadas.length = 0;
    vi.stubGlobal("fetch", (url: string, init?: RequestInit) => {
      chamadas.push({ url, init });
      return Promise.resolve(
        new Response("{}", {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
      );
    });
  });

  afterEach(() => {
    setAccessTokenProvider(null);
    vi.unstubAllGlobals();
  });

  function headersDaChamada(indice = 0): Record<string, string> {
    return (chamadas[indice]?.init?.headers ?? {}) as Record<string, string>;
  }

  it("sem provider nenhum header de sessão é enviado (servidor local do ADR-0020)", async () => {
    await getState();

    expect(chamadas).toHaveLength(1);
    expect(headersDaChamada()).not.toHaveProperty("Authorization");
  });

  it("com provider, a chamada carrega o Bearer da sessão", async () => {
    setAccessTokenProvider(() => "token-de-teste");

    await getState();

    expect(headersDaChamada().Authorization).toBe("Bearer token-de-teste");
  });

  it("o token é lido a cada chamada, então a renovação silenciosa entra sozinha", async () => {
    let token = "primeiro";
    setAccessTokenProvider(() => token);

    await getState();
    token = "renovado";
    await getState();

    expect(headersDaChamada(0).Authorization).toBe("Bearer primeiro");
    expect(headersDaChamada(1).Authorization).toBe("Bearer renovado");
  });

  it("sessão encerrada não vira header vazio", async () => {
    setAccessTokenProvider(() => null);

    await getState();

    expect(headersDaChamada()).not.toHaveProperty("Authorization");
  });

  it("o Content-Type do POST sobrevive ao Authorization", async () => {
    setAccessTokenProvider(() => "token-de-teste");

    await postSuggestionsRecompute(null);

    expect(headersDaChamada().Authorization).toBe("Bearer token-de-teste");
    expect(headersDaChamada()["Content-Type"]).toBe("application/json");
  });

  it("o upload multipart continua sem Content-Type escrito pelo cliente", async () => {
    setAccessTokenProvider(() => "token-de-teste");

    await uploadPlate(
      new File(["%PDF-1.4 sintetico"], "prancha.pdf", { type: "application/pdf" }),
    );

    expect(headersDaChamada().Authorization).toBe("Bearer token-de-teste");
    // O boundary é escrito pelo navegador; um `Content-Type` daqui quebraria o parsing.
    expect(headersDaChamada()).not.toHaveProperty("Content-Type");
  });
});

/**
 * Imagem da prancha no modo hospedado: `<img src>` não leva header nenhum, então ela é
 * buscada como qualquer outra chamada e vira object URL. Sem sessão, o caminho local do
 * ADR-0020 continua exibindo a URL direta, sem requisição a mais.
 */
describe("fetchImageObjectUrl", () => {
  const chamadas: { url: string; init: RequestInit | undefined }[] = [];

  beforeEach(() => {
    chamadas.length = 0;
    vi.stubGlobal("fetch", (url: string, init?: RequestInit) => {
      chamadas.push({ url, init });
      return Promise.resolve(
        new Response(new Blob([new Uint8Array([137, 80, 78, 71])]), {
          status: 200,
          headers: { "Content-Type": "image/png" },
        }),
      );
    });
  });

  afterEach(() => {
    setAccessTokenProvider(null);
    vi.unstubAllGlobals();
  });

  it("busca a imagem com o Bearer da sessão e devolve um object URL", async () => {
    setAccessTokenProvider(() => "token-de-teste");

    const url = await fetchImageObjectUrl(PLATE_IMAGE_PATH);

    expect(chamadas).toHaveLength(1);
    expect(chamadas[0]?.url).toBe(plateImageUrl);
    expect(
      (chamadas[0]?.init?.headers as Record<string, string>).Authorization,
    ).toBe("Bearer token-de-teste");
    expect(url.startsWith("blob:")).toBe(true);
    URL.revokeObjectURL(url);
  });

  it("sem sessão nenhum header a mais é enviado", async () => {
    const url = await fetchImageObjectUrl(PLATE_IMAGE_PATH);

    expect(chamadas[0]?.init?.headers).not.toHaveProperty("Authorization");
    URL.revokeObjectURL(url);
  });

  it("recusa do servidor vira o erro de domínio, nunca um object URL vazio", async () => {
    vi.stubGlobal("fetch", () =>
      Promise.resolve(
        new Response(JSON.stringify({ code: "HOSTED_SESSION_INVALID", detail: "entre de novo" }), {
          status: 401,
          headers: { "Content-Type": "application/problem+json" },
        }),
      ),
    );

    await expect(fetchImageObjectUrl(PLATE_IMAGE_PATH)).rejects.toMatchObject({
      code: "HOSTED_SESSION_INVALID",
      status: 401,
    });
  });

  it("servidor fora do ar é dito como servidor fora do ar", async () => {
    vi.stubGlobal("fetch", () => Promise.reject(new TypeError("failed to fetch")));

    await expect(fetchImageObjectUrl(PLATE_IMAGE_PATH)).rejects.toMatchObject({
      code: "LOCAL_SERVER_UNREACHABLE",
    });
  });
});
