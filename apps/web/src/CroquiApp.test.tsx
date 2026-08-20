import { renderToStaticMarkup } from "react-dom/server";
import type { User } from "oidc-client-ts";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, postReviewChains } from "./api";
import type { DeclaredChain, DimensionChain } from "./api";
import {
  AppAlert,
  ChainCloseHint,
  ChainsSection,
  CroquiApp,
  JobStatusBand,
  chainDraftIssue,
  EMPTY_CHAIN_DRAFT,
  jobFailureMessage,
  jobPresentationChanged,
  toggleChainTerm,
} from "./CroquiApp";

/**
 * Sessão sintética: a jornada recebe a sessão pronta da casca, e a renderização estática
 * não dispara efeito nenhum — nada é pedido à API por este teste.
 */
const session = {
  access_token: "sessao-sintetica-de-teste",
  profile: { sub: "revisor-de-teste" },
} as unknown as User;

describe("CroquiApp", () => {
  it("abre a área do tenant sem fabricar revisão, cena ou evidência", () => {
    const html = renderToStaticMarkup(
      <CroquiApp session={session} onSessionLost={() => undefined} />,
    );

    expect(html).toContain("Projetos e revisões");
    expect(html).not.toContain("DXF bloqueado");
    expect(html).not.toContain("Campo do Guaxindiba");
    expect(html).not.toContain("Simulação de decisão");
  });

  /**
   * A sessão tem um dono só (`readSession` consome um authorization code de uso único),
   * e é a casca. Esta jornada não desenha topbar, identidade nem Entrar/Sair.
   */
  it("não desenha a casca: sessão e navegação são da App", () => {
    const html = renderToStaticMarkup(
      <CroquiApp session={session} onSessionLost={() => undefined} />,
    );

    expect(html).not.toContain('class="topbar"');
    expect(html).not.toContain("Sessão:");
    expect(html).not.toContain(">Entrar<");
    expect(html).not.toContain(">Sair<");
    expect(html).not.toContain("revisor-de-teste");
    // O token nunca chega ao HTML.
    expect(html).not.toContain("sessao-sintetica-de-teste");
  });
});

/**
 * A faixa de acompanhamento é derivada do job, e não uma mensagem: derivada, o texto é o
 * mesmo entre duas voltas do poll de 2 s, o DOM não desmonta e a faixa não pisca.
 */
describe("JobStatusBand", () => {
  it("mostra o estado do job em processamento com role=status, sem cara de erro", () => {
    const html = renderToStaticMarkup(
      <JobStatusBand
        job={{ status: "PROCESSING", stage: "VISION" }}
        hasReview={false}
      />,
    );

    expect(html).toContain('role="status"');
    expect(html).toContain('class="app-status"');
    expect(html).toContain(
      "Em processamento. A revisão será aberta automaticamente quando estiver disponível.",
    );
    expect(html).not.toContain('role="alert"');
    expect(html).not.toContain("app-alert");
    // Estado não se fecha: some sozinho quando a revisão abre.
    expect(html).not.toContain("Fechar aviso");
  });

  it("some quando a revisão abre", () => {
    const html = renderToStaticMarkup(
      <JobStatusBand
        job={{ status: "REVIEW_REQUIRED", stage: "REVIEW" }}
        hasReview
      />,
    );

    expect(html).toBe("");
  });

  it("não desenha nada sem job aberto", () => {
    const html = renderToStaticMarkup(
      <JobStatusBand job={null} hasReview={false} />,
    );

    expect(html).toBe("");
  });

  it("não absorve a falha: job que falhou não vira faixa de estado", () => {
    const html = renderToStaticMarkup(
      <JobStatusBand job={{ status: "FAILED", stage: "VISION" }} hasReview={false} />,
    );

    expect(html).toBe("");
  });
});

/**
 * O poll de 2 s traz um objeto novo a cada volta. Trocar o job da tela por um igual
 * re-renderiza a jornada inteira — foi o "respiro" que o usuário reportou.
 */
describe("jobPresentationChanged", () => {
  it("mesmo status e mesmo stage não é mudança, mesmo em objeto novo", () => {
    const antes = { status: "PROCESSING", stage: "VISION" };
    const depois = { status: "PROCESSING", stage: "VISION" };

    expect(jobPresentationChanged(antes, depois)).toBe(false);
  });

  it("avanço de stage é mudança: a faixa de estado precisa acompanhar", () => {
    expect(
      jobPresentationChanged(
        { status: "PROCESSING", stage: "VISION" },
        { status: "PROCESSING", stage: "REVIEW" },
      ),
    ).toBe(true);
  });

  it("mudança de status é mudança, incluindo a virada para revisável e para falha", () => {
    expect(
      jobPresentationChanged(
        { status: "PROCESSING", stage: "REVIEW" },
        { status: "REVIEW_REQUIRED", stage: "REVIEW" },
      ),
    ).toBe(true);
    expect(
      jobPresentationChanged(
        { status: "PROCESSING", stage: "VISION" },
        { status: "FAILED", stage: "VISION" },
      ),
    ).toBe(true);
  });

  it("sem job aberto, o primeiro job é sempre mudança", () => {
    expect(
      jobPresentationChanged(null, { status: "UPLOADED", stage: "VALIDATING" }),
    ).toBe(true);
  });
});

describe("falha do job", () => {
  it("continua sendo aviso, em .app-alert com role=alert", () => {
    const message = jobFailureMessage({ status: "FAILED" });
    expect(message).toBe(
      "Este processamento falhou. Consulte a equipe responsável para repetir a etapa segura.",
    );

    const html = renderToStaticMarkup(
      <AppAlert message={message ?? ""} onClose={() => undefined} />,
    );

    expect(html).toContain('class="app-alert"');
    expect(html).toContain('role="alert"');
    expect(html).toContain("Este processamento falhou.");
    expect(html).toContain("Fechar aviso");
  });

  it("estado do ciclo de vida não vira mensagem", () => {
    expect(jobFailureMessage({ status: "PROCESSING" })).toBeNull();
    expect(jobFailureMessage({ status: "UPLOADED" })).toBeNull();
    expect(jobFailureMessage({ status: "REVIEW_REQUIRED" })).toBeNull();
  });
});

/**
 * "Somas de cotas" (F-023): o que as cotas confirmadas dizem umas das outras.
 *
 * O ambiente de teste do web é `node` e não monta DOM — não há evento de clique aqui. O
 * fluxo é coberto pelas peças que o decidem: a regra de marcação (`toggleChainTerm`), o
 * portão do envio (`chainDraftIssue`), o transporte com `fetch` dublado (corpo,
 * `base_version` e `Idempotency-Key`) e a renderização estática do resultado.
 */
const chainThatCloses: DimensionChain = {
  total: { reading_id: "rd_0000000000000001", value_m: "25.90", raw_text: "25,90" },
  parts: [
    { reading_id: "rd_0000000000000002", value_m: "12.49", raw_text: "12,49" },
    { reading_id: "rd_0000000000000003", value_m: "13.41", raw_text: "13,41" },
  ],
  residual_m: "0.00",
  tolerance_m: "0.015",
};

const chainThatMisses: DimensionChain = {
  total: { reading_id: "rd_0000000000000005", value_m: "21.75", raw_text: "21,75" },
  parts: [
    { reading_id: "rd_0000000000000006", value_m: "12.49", raw_text: "12,49" },
    { reading_id: "rd_0000000000000007", value_m: "6.36", raw_text: "6,36" },
  ],
  residual_m: "-2.90",
  tolerance_m: "0.015",
};

const declaredMismatch: DeclaredChain = {
  chain_id: "ch_mismatch",
  declared_by: "revisor-da-obra",
  declared_at: "2026-08-20T13:45:00Z",
  chain: chainThatMisses,
  status: "mismatch",
  issue: {
    code: "DIMENSION_CHAIN_MISMATCH",
    severity: "warning",
    message:
      "As cotas declaradas não fecham: 12.49 + 6.36 = 18.85 contra 21.75 " +
      "(diferença de 2.90 m). Confira se falta um trecho no croqui.",
  },
};

const declaredStale: DeclaredChain = {
  chain_id: "ch_stale",
  declared_by: "revisor-da-obra",
  declared_at: "2026-08-20T14:10:00Z",
  chain: null,
  status: "stale",
  issue: {
    code: "CHAIN_READING_SUPERSEDED",
    severity: "warning",
    message:
      "Uma das cotas desta cadeia deixou de estar confirmada depois que ela foi " +
      "declarada; confira a cadeia e declare de novo, ou retrate-a.",
  },
};

function renderChains(props: Partial<Parameters<typeof ChainsSection>[0]> = {}) {
  return renderToStaticMarkup(
    <ChainsSection
      suggested={[]}
      declared={[]}
      draft={null}
      candidateCount={0}
      submitting={false}
      onStartDeclaring={() => undefined}
      onCancelDeclaring={() => undefined}
      onConfirmDeclaring={() => undefined}
      onRetract={() => undefined}
      onSelectReading={() => undefined}
      {...props}
    />,
  );
}

describe("ChainsSection", () => {
  it("mostra as declaradas antes das sugeridas, com autoria e o botão de retirar", () => {
    const html = renderChains({
      declared: [
        {
          chain_id: "ch_closes",
          declared_by: "revisor-da-obra",
          declared_at: "2026-08-20T13:00:00Z",
          chain: chainThatCloses,
          status: "closes",
        },
      ],
      suggested: [chainThatMisses],
      candidateCount: 4,
    });

    expect(html).toContain("Somas de cotas");
    expect(html).toContain("Cadeia declarada");
    expect(html).toContain("12,49 + 13,41 = 25,90 · confere (folga 0,015 m)");
    expect(html).toContain("Declarada por");
    expect(html).toContain("revisor-da-obra");
    expect(html).toContain("20/08/2026 às 13:00 UTC");
    expect(html).toContain("Retirar");
    // Cautela escrita ao lado das sugestões, não em nota de rodapé.
    expect(html).toContain(
      "Coincidência aritmética é comum; use como pista, não como prova",
    );
    expect(html.indexOf("Cadeia declarada")).toBeLessThan(
      html.indexOf("Coincidência aritmética"),
    );
  });

  it("nunca esconde o aviso de quem não fecha: frase do servidor e código cru", () => {
    const html = renderChains({ declared: [declaredMismatch], candidateCount: 4 });

    expect(html).toContain("não fecha");
    expect(html).toContain("As cotas declaradas não fecham");
    expect(html).toContain("DIMENSION_CHAIN_MISMATCH");
    // A soma escrita não afirma igualdade onde o servidor achou diferença.
    expect(html).toContain("12,49 + 6,36 ≠ 21,75");
    expect(html).toContain("diferença de 2,90 m");
    // O aviso é texto, não só cor: a classe é reforço.
    expect(html).toContain("chain-warning");
  });

  it("declara em palavra a cadeia que perdeu o pé, mesmo sem soma para mostrar", () => {
    const html = renderChains({ declared: [declaredStale], candidateCount: 4 });

    expect(html).toContain("perdeu o pé");
    expect(html).toContain("deixou de estar confirmada");
    expect(html).toContain("CHAIN_READING_SUPERSEDED");
    expect(html).toContain("Retirar");
  });

  it("some inteira quando não há cadeia nem leitura confirmada para declarar", () => {
    // É o caso do replay antigo: `suggested_chains`/`declared_chains` chegam `undefined`,
    // a tela cai no `?? []` e a seção não existe — sem quadro vazio e sem quebrar.
    expect(renderChains()).toBe("");
  });

  it("oferece o começo da declaração quando há confirmadas, sem inventar cadeia", () => {
    const html = renderChains({ candidateCount: 3 });

    expect(html).toContain("Declarar cadeia");
    expect(html).toContain("chain-panel");
    expect(html).not.toContain("chain-item");
    expect(html).not.toContain("Coincidência aritmética");
  });

  it("em modo de declaração pede o ato humano e não envia nada sozinha", () => {
    const html = renderChains({
      draft: EMPTY_CHAIN_DRAFT,
      candidateCount: 3,
    });

    expect(html).toContain("Total ainda não marcado");
    expect(html).toContain("Marque na lista a leitura que é o total da cadeia.");
    expect(html).toContain("Confirmar cadeia");
    expect(html).toContain("Cancelar");
    // Sem total e sem parcelas, confirmar está fechado.
    expect(html).toContain("disabled");
  });
});

describe("ChainCloseHint", () => {
  it("é pista fraca e declarada como tal, nunca confirmação", () => {
    const html = renderToStaticMarkup(<ChainCloseHint corroborated />);

    expect(html).toContain("Σ fecha");
    expect(html).toContain("chain-hint");
    expect(html).toContain("não confirmação");
  });

  it("não desenha nada para a leitura que nenhuma soma corrobora", () => {
    expect(
      renderToStaticMarkup(<ChainCloseHint corroborated={false} />),
    ).toBe("");
  });
});

describe("toggleChainTerm", () => {
  it("o primeiro clique é o total e os seguintes são parcelas", () => {
    const primeiro = toggleChainTerm(EMPTY_CHAIN_DRAFT, "rd_1");
    const segundo = toggleChainTerm(primeiro, "rd_2");
    const terceiro = toggleChainTerm(segundo, "rd_3");

    expect(terceiro).toEqual({
      totalId: "rd_1",
      partIds: ["rd_2", "rd_3"],
    });
  });

  it("clicar de novo desmarca, tanto o total quanto a parcela", () => {
    const draft = { totalId: "rd_1", partIds: ["rd_2", "rd_3"] };

    expect(toggleChainTerm(draft, "rd_2")).toEqual({
      totalId: "rd_1",
      partIds: ["rd_3"],
    });
    expect(toggleChainTerm(draft, "rd_1")).toEqual({
      totalId: null,
      partIds: ["rd_2", "rd_3"],
    });
  });

  it("não muda o rascunho anterior: a marcação é substituída, nunca mutada", () => {
    const draft = { totalId: "rd_1", partIds: ["rd_2"] };
    toggleChainTerm(draft, "rd_3");

    expect(draft).toEqual({ totalId: "rd_1", partIds: ["rd_2"] });
  });
});

describe("chainDraftIssue", () => {
  it("pede o total antes de tudo", () => {
    expect(chainDraftIssue(EMPTY_CHAIN_DRAFT)).toBe(
      "Marque na lista a leitura que é o total da cadeia.",
    );
  });

  it("exige duas parcelas, como o servidor exige", () => {
    expect(chainDraftIssue({ totalId: "rd_1", partIds: ["rd_2"] })).toBe(
      "Uma cadeia precisa de pelo menos duas parcelas.",
    );
  });

  it("libera a cadeia mínima", () => {
    expect(
      chainDraftIssue({ totalId: "rd_1", partIds: ["rd_2", "rd_3"] }),
    ).toBeNull();
  });

  it("avisa antes da rede quando o lote passa do teto do contrato", () => {
    const partIds = Array.from({ length: 17 }, (_, index) => `rd_${index}`);

    expect(chainDraftIssue({ totalId: "rd_total", partIds })).toContain(
      "vai até 16 parcelas",
    );
  });
});

describe("declaração de cadeia pela rota da revisão", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("marca, confirma e recebe a revisão nova com a cadeia declarada", async () => {
    const declarada: DeclaredChain = {
      chain_id: "ch_novo",
      declared_by: "revisor-da-obra",
      declared_at: "2026-08-20T15:00:00Z",
      chain: chainThatCloses,
      status: "closes",
    };
    const enviados: { body: unknown; headers: Record<string, string> }[] = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(async (_url: string, init?: RequestInit) => {
        enviados.push({
          body: JSON.parse(String(init?.body)),
          headers: init?.headers as Record<string, string>,
        });
        return new Response(
          JSON.stringify({ version: 8, declared_chains: [declarada] }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        );
      }),
    );

    // A marcação é do revisor, uma leitura por vez.
    const draft = ["rd_0000000000000001", "rd_0000000000000002", "rd_0000000000000003"]
      .reduce(toggleChainTerm, EMPTY_CHAIN_DRAFT);
    expect(chainDraftIssue(draft)).toBeNull();

    const next = await postReviewChains("token", "job-1", 7, {
      action: "declare",
      total_id: draft.totalId ?? "",
      part_ids: draft.partIds,
    });

    expect(enviados[0].body).toEqual({
      base_version: 7,
      action: "declare",
      total_id: "rd_0000000000000001",
      part_ids: ["rd_0000000000000002", "rd_0000000000000003"],
    });
    expect(enviados[0].headers["Idempotency-Key"]).toBeTruthy();
    expect(next.version).toBe(8);

    const html = renderChains({
      declared: next.declared_chains ?? [],
      candidateCount: 3,
    });
    expect(html).toContain("12,49 + 13,41 = 25,90 · confere (folga 0,015 m)");
  });

  it("retratar leva o identificador da cadeia e o base_version corrente", async () => {
    const enviados: unknown[] = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(async (_url: string, init?: RequestInit) => {
        enviados.push(JSON.parse(String(init?.body)));
        return new Response(JSON.stringify({ version: 9, declared_chains: [] }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }),
    );

    await postReviewChains("token", "job-1", 8, {
      action: "retract",
      chain_id: "ch_novo",
    });

    expect(enviados[0]).toEqual({
      base_version: 8,
      action: "retract",
      chain_id: "ch_novo",
    });
  });

  it("CHAIN_INVALID vira aviso na tela, como as demais recusas de mutação", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(
        async () =>
          new Response(
            JSON.stringify({
              detail: {
                code: "CHAIN_INVALID",
                detail: "O total não pode ser também parcela de si mesmo.",
              },
            }),
            { status: 422, headers: { "Content-Type": "application/json" } },
          ),
      ),
    );

    const erro = await postReviewChains("token", "job-1", 7, {
      action: "declare",
      total_id: "rd_0000000000000001",
      part_ids: ["rd_0000000000000001", "rd_0000000000000002"],
    }).catch((e: unknown) => e);

    expect(erro).toBeInstanceOf(ApiError);
    const message = (erro as ApiError).message;
    expect(message).toContain("CHAIN_INVALID");
    expect(message).toContain("O total não pode ser também parcela de si mesmo.");

    const html = renderToStaticMarkup(
      <AppAlert message={message} onClose={() => undefined} />,
    );
    expect(html).toContain('role="alert"');
    expect(html).toContain("O total não pode ser também parcela de si mesmo.");
  });
});
