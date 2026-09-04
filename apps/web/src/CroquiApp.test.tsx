import { renderToStaticMarkup } from "react-dom/server";
import type { SceneRevision } from "@croquito/contracts";
import type { User } from "oidc-client-ts";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, postReviewChains } from "./api";
import type {
  DeclaredChain,
  DimensionChain,
  FieldWitness,
  Review,
  ReviewElementDeclaration,
  ReviewReading,
} from "./api";
import { agruparCandidatas } from "./reviewElementIdentity";
import {
  AppAlert,
  AutoDecisionBadge,
  blockerReadingIds,
  CandidatasDaAssociacao,
  ChainCloseHint,
  ChainsSection,
  CroquiApp,
  HintDoModeloChip,
  DecisionAuthorLine,
  exceptionCounts,
  ExceptionsBand,
  FieldWitnessesSection,
  isSystemAnnotation,
  isSystemDecided,
  JobStatusBand,
  chainDraftIssue,
  EMPTY_CHAIN_DRAFT,
  jobFailureMessage,
  jobPresentationChanged,
  PreviewDaCena,
  readingIdsWithCandidate,
  toggleChainTerm,
  visibleReadings,
  type WitnessSourcesView,
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

function witness(overrides: Partial<FieldWitness> = {}): FieldWitness {
  return {
    witness_id: "0197f2a0-0000-7000-8000-0000000000aa",
    reading_id: "rd_0000000000000001",
    source_type: "survey_measurement",
    source_id: "mea-1",
    survey_id: "svy-1",
    reading_value_mm: "19750",
    source_value_mm: "19780",
    difference_mm: "30",
    associated_by: "Ana",
    associated_at: "2026-08-20T13:00:00Z",
    ...overrides,
  };
}

const confirmedReading: ReviewReading = {
  id: "rd_0000000000000001",
  raw_text: "19,75",
  kind: "length",
  status: "confirmed",
  value_si: "19.75",
  unit: "m",
};

function renderWitnesses(
  props: Partial<Parameters<typeof FieldWitnessesSection>[0]> = {},
) {
  const sourcesView: WitnessSourcesView = props.sourcesView ?? { status: "closed" };
  return renderToStaticMarkup(
    <FieldWitnessesSection
      reading={props.reading ?? confirmedReading}
      witnesses={props.witnesses ?? []}
      canAssociate={props.canAssociate ?? true}
      sourcesView={sourcesView}
      selectedSource={props.selectedSource ?? ""}
      submitting={props.submitting ?? false}
      message={props.message ?? null}
      onStartAssociating={() => undefined}
      onCancelAssociating={() => undefined}
      onSelectSource={() => undefined}
      onConfirmAssociation={() => undefined}
      onRetract={() => undefined}
    />,
  );
}

describe("FieldWitnessesSection", () => {
  it("confronta cota e trena com diferença neutra, sem juízo de concordância", () => {
    const html = renderWitnesses({ witnesses: [witness()] });

    expect(html).toContain("TESTEMUNHA DE CAMPO");
    expect(html).toContain("COTA DA PRANCHA");
    expect(html).toContain("19,75");
    expect(html).toContain("TRENA EM CAMPO");
    expect(html).toContain("19,78");
    expect(html).toContain("DIFERENÇA");
    expect(html).toContain("0,03");
    expect(html).toContain("Associada por");
    expect(html).toContain("Retirar testemunha");
    // A diferença é neutra: nenhum vocabulário nem veste de concordância/alerta. (A cópia
    // explica que não escolhe "vencedor", então esse termo não é asserido negativamente.)
    expect(html).not.toContain("concorda");
    expect(html).not.toContain("diverge");
    expect(html).not.toContain("confere");
    expect(html).not.toContain("⚠");
    expect(html).not.toContain("ocr-warning");
    // A diferença não veste tom de estado (as classes de pastilha do painel).
    expect(html).not.toContain('class="blocked"');
    expect(html).not.toContain('class="ready"');
  });

  it("empilha várias testemunhas sem hierarquia e sem faixa-resumo", () => {
    const html = renderWitnesses({
      witnesses: [
        witness(),
        witness({
          witness_id: "0197f2a0-0000-7000-8000-0000000000bb",
          source_type: "photo_reading",
          source_id: "cfm-1",
          survey_id: null,
          source_value_mm: "19700",
          difference_mm: "-50",
        }),
      ],
    });

    expect(html).toContain("TESTEMUNHA 1 · MEDIDA DO APP");
    expect(html).toContain("TESTEMUNHA 2 · VALOR CONFIRMADO EM FOTO");
    expect(html).toContain("VISOR FOTOGRAFADO");
    // A cota da prancha aparece uma vez por testemunha; nenhuma é escolhida vencedora.
    expect(html.split("COTA DA PRANCHA").length - 1).toBe(2);
    // A segunda diferença também é magnitude neutra (sem sinal).
    expect(html).toContain("0,05");
  });

  it("leitura não confirmada com testemunha mostra o gate, sem oferecer associar", () => {
    const html = renderWitnesses({
      canAssociate: false,
      witnesses: [witness()],
      reading: { ...confirmedReading, status: "proposed", value_si: null },
    });

    // A cota da prancha nunca some: a testemunha guarda o valor que confrontou.
    expect(html).toContain("COTA DA PRANCHA");
    expect(html).toContain("Confirme a leitura");
    expect(html).not.toContain("Associar testemunha de campo");
  });

  it("sem testemunha e sem poder associar, a seção não aparece", () => {
    const html = renderWitnesses({
      canAssociate: false,
      witnesses: [],
      reading: { ...confirmedReading, status: "proposed", value_si: null },
    });
    expect(html).toBe("");
  });

  it("sem fonte elegível mostra o porquê e não deixa botão morto de associar", () => {
    const html = renderWitnesses({ sourcesView: { status: "ready", sources: [] } });

    expect(html).toContain("Nenhuma fonte de campo elegível");
    expect(html).toContain("Fechar");
    expect(html).not.toContain("<select");
  });

  it("com fontes, o select nasce vazio e associar fica fechado sem escolha", () => {
    const html = renderWitnesses({
      sourcesView: {
        status: "ready",
        sources: [
          {
            source: { type: "survey_measurement", source_id: "mea-1", survey_id: "svy-1" },
            label: "Medida do app · 19,78 m · Praça",
            value_mm: 19_780,
          },
        ],
      },
      selectedSource: "",
    });

    expect(html).toContain("Escolha a fonte de campo…");
    expect(html).toContain("Medida do app · 19,78 m · Praça");
    expect(html).toContain("nunca associam nada");
    // "Associar" existe mas está desabilitado enquanto nada foi escolhido.
    expect(html).toContain("Associar");
    expect(html).toContain("disabled");
  });

  it("carregando e erro têm estados próprios, sem select de fonte", () => {
    expect(renderWitnesses({ sourcesView: { status: "loading" } })).toContain(
      "Buscando as fontes de campo",
    );
    const erro = renderWitnesses({
      sourcesView: { status: "error", message: "Falha ao carregar." },
    });
    expect(erro).toContain('role="alert"');
    expect(erro).toContain("Tentar de novo");
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

/**
 * Vista de exceções (F-029): o que o sistema decidiu sozinho e o que sobrou para gente.
 *
 * O ambiente de teste do web é `node` e não monta DOM — o gesto no chip não existe aqui.
 * O que é coberto são as peças que o decidem: a contagem (`exceptionCounts`), o recorte
 * da lista (`visibleReadings`), a leitura de blockers (`blockerReadingIds`) e a
 * renderização estática da faixa, da marca da linha e do registro da decisão.
 */
function reading(overrides: Partial<ReviewReading> = {}): ReviewReading {
  return {
    id: "rd_0000000000000001",
    raw_text: "12,49",
    kind: "width",
    status: "proposed",
    ...overrides,
  };
}

function systemDecision(
  overrides: Partial<NonNullable<ReviewReading["decision"]>> = {},
) {
  return {
    decision_id: "hd_00000000000000aa",
    action: "confirm" as const,
    actor: "system" as const,
    reviewer_id: "system:auto-association@1.0.0",
    decided_at: "2026-08-21T12:00:00Z",
    note:
      "Decisão automática de associação (corte 0.9, score 1.0.0): confiança de leitura " +
      "0.97 e de associação 0.93, ambas acima do corte.",
    ...overrides,
  };
}

const humanDecision = {
  decision_id: "hd_00000000000000bb",
  action: "confirm" as const,
  reviewer_id: "revisor-da-obra",
  decided_at: "2026-08-21T13:00:00Z",
};

describe("exceptionCounts", () => {
  it("separa auto-decidida, pendente com candidato e pendente sem ninguém a associar", () => {
    const readings = [
      reading({ id: "rd_auto", status: "confirmed", decision: systemDecision() }),
      reading({ id: "rd_pendente_com_candidato" }),
      reading({ id: "rd_pendente_sem_candidato", status: "ambiguous" }),
      reading({ id: "rd_humana", status: "confirmed", decision: humanDecision }),
    ];

    expect(
      exceptionCounts(readings, new Set(["rd_pendente_com_candidato", "rd_auto"])),
    ).toEqual({ auto: 1, autoNote: 0, review: 1, unresolved: 1 });
  });

  it("não conta ninguém numa revisão sem modo automático: a tela é a de sempre", () => {
    const readings = [
      reading({ id: "rd_humana", status: "confirmed", decision: humanDecision }),
      reading({ id: "rd_pendente" }),
    ];

    expect(exceptionCounts(readings, new Set(["rd_pendente"]))).toEqual({
      auto: 0,
      autoNote: 0,
      review: 1,
      unresolved: 0,
    });
  });

  it("lê decisão sem `actor` como humana, que é o default do servidor", () => {
    const semAtor = reading({
      id: "rd_antiga",
      status: "confirmed",
      decision: { ...humanDecision, reviewer_id: "revisor-antigo" },
    });

    expect(isSystemDecided(semAtor)).toBe(false);
    expect(exceptionCounts([semAtor], new Set())).toEqual({
      auto: 0,
      autoNote: 0,
      review: 0,
      unresolved: 0,
    });
  });

  it("uma cota retificada por gente sai da contagem de automáticas", () => {
    const retificada = reading({
      id: "rd_auto",
      status: "confirmed",
      decision: {
        ...humanDecision,
        rectifies_decision_id: "hd_00000000000000aa",
      },
    });

    expect(exceptionCounts([retificada], new Set(["rd_auto"])).auto).toBe(0);
  });
});

/**
 * Tier de anotação (ADR-0044): a máquina confirma com uma testemunha só o que não manda
 * na geometria de planta. A tela lê o tier do que o servidor gravou — ela não reaplica a
 * regra de elegibilidade, que mora no worker.
 */
function annotationDecision(
  overrides: Partial<NonNullable<ReviewReading["decision"]>> = {},
) {
  return systemDecision({
    decision_id: "hd_00000000000000cc",
    auto_tier: "anotacao" as const,
    note:
      "Anotação automática (corte 0.7, score 1.0.0): confiança de associação 0.9 acima " +
      "do corte; leitura sem papel de geometria de planta, com confiança de leitura " +
      "0.45 registrada e não exigida.",
    ...overrides,
  });
}

describe("exceptionCounts por tier", () => {
  it("conta cota automática e anotação automática em contadores separados", () => {
    const readings = [
      reading({ id: "rd_cota", status: "confirmed", decision: systemDecision() }),
      reading({
        id: "rd_elevacao",
        kind: "height",
        status: "confirmed",
        decision: annotationDecision(),
      }),
      reading({ id: "rd_pendente" }),
    ];

    expect(
      exceptionCounts(readings, new Set(["rd_cota", "rd_elevacao", "rd_pendente"])),
    ).toEqual({ auto: 1, autoNote: 1, review: 1, unresolved: 0 });
  });

  it("decisão de sistema sem tier declarado conta como cota, o único que existia", () => {
    const antiga = reading({
      id: "rd_antiga",
      status: "confirmed",
      decision: systemDecision(),
    });

    expect(isSystemAnnotation(antiga)).toBe(false);
    expect(exceptionCounts([antiga], new Set(["rd_antiga"])).auto).toBe(1);
  });

  it("o tier vem do servidor, nunca do kind da leitura", () => {
    // Uma elevação decidida pelo tier de cota (passou nos dois eixos) continua sendo
    // cota automática: se a tela re-derivasse a regra pelo `kind`, ela diria outra coisa.
    const elevacaoPorDuplaTestemunha = reading({
      id: "rd_elevacao_forte",
      kind: "height",
      status: "confirmed",
      decision: systemDecision({ auto_tier: "cota" }),
    });

    expect(isSystemAnnotation(elevacaoPorDuplaTestemunha)).toBe(false);
    expect(
      exceptionCounts([elevacaoPorDuplaTestemunha], new Set(["rd_elevacao_forte"])),
    ).toEqual({ auto: 1, autoNote: 0, review: 0, unresolved: 0 });
  });
});

describe("visibleReadings", () => {
  const auto = reading({
    id: "rd_auto",
    status: "confirmed",
    decision: systemDecision(),
  });
  const humana = reading({
    id: "rd_humana",
    status: "confirmed",
    decision: humanDecision,
  });
  const pendente = reading({ id: "rd_pendente" });

  it("sem filtro, a lista é a inteira e na mesma ordem", () => {
    expect(visibleReadings([auto, humana, pendente], false, new Set())).toEqual([
      auto,
      humana,
      pendente,
    ]);
  });

  it("com filtro, esconde só o que já tem decisão — nunca o pendente", () => {
    expect(visibleReadings([auto, humana, pendente], true, new Set())).toEqual([
      pendente,
    ]);
  });

  it("nunca esconde a linha citada por um bloqueio, mesmo já decidida", () => {
    const blockers = blockerReadingIds([
      "WIDTH_HUMAN_CONFIRMATION_REQUIRED:rd_auto",
      "NUMERIC_RESIDUAL_EXCEEDS_TOLERANCE",
    ]);

    expect(blockers).toEqual(new Set(["rd_auto"]));
    expect(visibleReadings([auto, humana, pendente], true, blockers)).toEqual([
      auto,
      pendente,
    ]);
  });

  it("com uma cadeia em declaração, as confirmadas continuam marcáveis na lista", () => {
    // Termo de cadeia é sempre leitura CONFIRMADA (F-023): escondê-la com o filtro
    // ligado deixaria o revisor sem o que marcar no meio do ato.
    const emDeclaracao = new Set(["rd_auto", "rd_humana"]);

    expect(
      visibleReadings([auto, humana, pendente], true, emDeclaracao),
    ).toEqual([auto, humana, pendente]);
  });
});

describe("readingIdsWithCandidate", () => {
  it("junta os candidatos por leitura, sem repetir a mesma cota", () => {
    expect(
      readingIdsWithCandidate([
        { reading_id: "rd_1" },
        { reading_id: "rd_1" },
        { reading_id: "rd_2" },
      ]),
    ).toEqual(new Set(["rd_1", "rd_2"]));
  });

  it("resposta sem candidato nenhum não inventa associação", () => {
    expect(readingIdsWithCandidate([])).toEqual(new Set());
  });
});

describe("ExceptionsBand", () => {
  function renderBand(
    props: Partial<Parameters<typeof ExceptionsBand>[0]> = {},
  ) {
    return renderToStaticMarkup(
      <ExceptionsBand
        counts={{ auto: 4, autoNote: 0, review: 2, unresolved: 1 }}
        onlyExceptions={false}
        hiddenCount={0}
        onChange={() => undefined}
        {...props}
      />,
    );
  }

  it("mostra os três contadores por extenso e os dois estados do filtro", () => {
    const html = renderBand();

    expect(html).toContain("⚙ 4 auto-associadas");
    expect(html).toContain("⚠ 2 precisam de revisão");
    expect(html).toContain("✗ 1 não resolvida");
    expect(html).toContain("só exceções");
    expect(html).toContain(">todas<");
    // O estado do filtro é anunciável, não só desenhado.
    expect(html).toContain('aria-pressed="false"');
    expect(html).toContain('aria-pressed="true"');
    expect(html).toContain('aria-label="Exceções da revisão"');
    // A faixa declara o que a máquina fez e o que ela não fez.
    expect(html).toContain("continua corrigível por você");
    expect(html).toContain("Nada aqui aprova cena nem libera exportação.");
  });

  it("não existe sem auto-decisão: a revisão sem modo automático é a de hoje", () => {
    expect(
      renderBand({ counts: { auto: 0, autoNote: 0, review: 5, unresolved: 2 } }),
    ).toBe("");
  });

  it("declara as anotações automáticas em contador próprio quando houver", () => {
    const html = renderBand({
      counts: { auto: 4, autoNote: 3, review: 2, unresolved: 1 },
    });

    expect(html).toContain("⚙ 4 auto-associadas");
    expect(html).toContain("⚙ 3 anotações automáticas");
    // A faixa explica por que a anotação entrou com uma testemunha só — e diz que ela
    // não prendeu elemento nenhum, que é o que a mantém fora da geometria.
    expect(html).toContain("entraram com uma testemunha");
    expect(html).toContain("sem elemento associado");
    expect(html).toContain("não medem a planta");
  });

  it("sem anotação automática, o contador dela não aparece zerado", () => {
    const html = renderBand();

    expect(html).not.toContain("anotações automáticas");
    expect(html).not.toContain("anotação automática");
  });

  it("existe com anotação automática mesmo sem nenhuma cota automática", () => {
    const html = renderBand({
      counts: { auto: 0, autoNote: 2, review: 5, unresolved: 0 },
    });

    expect(html).toContain("⚙ 2 anotações automáticas");
    expect(html).toContain("⚙ 0 auto-associadas");
  });

  it("com o filtro ligado, declara quantas linhas saíram e o que continua à vista", () => {
    const html = renderBand({ onlyExceptions: true, hiddenCount: 4 });

    expect(html).toContain("4 leituras já decididas estão fora da lista.");
    expect(html).toContain(
      "Bloqueios, avisos e leituras citadas por um bloqueio continuam à vista.",
    );
    expect(html).toContain('aria-live="polite"');
  });

  it("conta uma linha escondida no singular", () => {
    const html = renderBand({ onlyExceptions: true, hiddenCount: 1 });

    expect(html).toContain("1 leitura já decidida está fora da lista.");
  });
});

describe("AutoDecisionBadge", () => {
  it("marca a linha com ícone e frase, e mostra a confiança registrada", () => {
    const html = renderToStaticMarkup(
      <AutoDecisionBadge
        reading={reading({ status: "confirmed", decision: systemDecision() })}
        confidence={0.97}
      />,
    );

    // Texto, não só cor: a frase inteira está escrita na linha.
    expect(html).toContain("associada pelo sistema · score 1.0.0");
    expect(html).toContain("⚙");
    expect(html).toContain("confiança 0,97");
    // O identificador técnico do ator-máquina não vai para a leitura corrida.
    expect(html).not.toContain("system:auto-association");
    // A correção continua prometida na própria marca.
    expect(html).toContain("Corrija-a como qualquer decisão registrada.");
  });

  it("sem confiança na resposta, a marca continua — o número é que falta", () => {
    const html = renderToStaticMarkup(
      <AutoDecisionBadge
        reading={reading({ status: "confirmed", decision: systemDecision() })}
      />,
    );

    expect(html).toContain("associada pelo sistema");
    // Sem número não há segunda marca: nada de "confiança —" nem de zero inventado.
    expect(html).not.toContain("auto-confidence");
    expect(html).not.toMatch(/confiança \d/);
  });

  it("distingue a anotação automática da cota associada pelo sistema", () => {
    const html = renderToStaticMarkup(
      <AutoDecisionBadge
        reading={reading({
          kind: "height",
          status: "confirmed",
          decision: annotationDecision(),
        })}
        confidence={0.45}
      />,
    );

    // Palavra diferente, não só tom diferente.
    expect(html).toContain("anotação automática · score 1.0.0");
    expect(html).not.toContain("associada pelo sistema");
    expect(html).toContain("sem elemento associado");
    expect(html).toContain("não entra na geometria");
    // A confiança que não foi exigida continua à vista, sem ser escondida.
    expect(html).toContain("confiança 0,45");
  });

  it("não marca decisão humana nem leitura pendente", () => {
    expect(
      renderToStaticMarkup(
        <AutoDecisionBadge
          reading={reading({ status: "confirmed", decision: humanDecision })}
        />,
      ),
    ).toBe("");
    expect(renderToStaticMarkup(<AutoDecisionBadge reading={reading()} />)).toBe(
      "",
    );
  });
});

describe("DecisionAuthorLine", () => {
  it("declara a decisão de máquina como tal, com a versão do score", () => {
    const html = renderToStaticMarkup(
      <DecisionAuthorLine
        reading={reading({ status: "confirmed", decision: systemDecision() })}
      />,
    );

    expect(html).toContain("Confirmada <strong>pelo sistema</strong>");
    expect(html).toContain("sem toque humano");
    expect(html).toContain("com o score 1.0.0");
    expect(html).toContain("21/08/2026 às 12:00 UTC");
    expect(html).toContain("Corrigi-la é ato seu");
    expect(html).not.toContain("system:auto-association");
  });

  it("a anotação automática diz por que uma leitura só bastou", () => {
    const html = renderToStaticMarkup(
      <DecisionAuthorLine
        reading={reading({
          kind: "height",
          status: "confirmed",
          decision: annotationDecision(),
        })}
      />,
    );

    expect(html).toContain("Confirmada <strong>pelo sistema</strong>");
    expect(html).toContain("Como anotação, sem elemento associado");
    expect(html).toContain("uma leitura só bastou");
    expect(html).toContain("nada foi preso à geometria");
    // A dica do elemento provável mora na justificativa registrada, que a tela mostra
    // logo abaixo — a frase manda o revisor até ela em vez de repetir o identificador.
    expect(html).toContain("elemento provável");
    expect(html).toContain("Corrigi-la é ato seu");
  });

  it("a decisão humana continua escrita como sempre foi", () => {
    const html = renderToStaticMarkup(
      <DecisionAuthorLine
        reading={reading({ status: "confirmed", decision: humanDecision })}
      />,
    );

    expect(html).toContain("Decidida por <strong>revisor-da-obra</strong>");
    expect(html).toContain("21/08/2026 às 13:00 UTC");
    expect(html).not.toContain("sistema");
  });

  it("leitura sem decisão não inventa autoria", () => {
    expect(renderToStaticMarkup(<DecisionAuthorLine reading={reading()} />)).toBe(
      "",
    );
  });
});

/**
 * Critério de aceite 1 da T5 (F-029): resposta SEM os campos novos — replay gravado antes
 * deles, ou revisão com o modo automático desligado — continua produzindo a tela de hoje.
 *
 * O objeto é tipado como `Review` de propósito: se algum campo da F-029 deixasse de ser
 * opcional, este teste pararia de compilar antes de parar de passar.
 */
describe("revisão sem os campos de confiança", () => {
  const antiga: Review = {
    job_id: "job-1",
    review_id: "rev-1",
    version: 3,
    packet: {
      readings: [
        reading({ id: "rd_pendente" }),
        reading({
          id: "rd_humana",
          status: "confirmed",
          decision: humanDecision,
        }),
      ],
    },
    associations: {
      candidates: [
        {
          reading_id: "rd_pendente",
          proposal_id: "vp_0000000000000001",
          proposal_kind: "line",
          relation: "nearest_geometry",
        },
      ],
    },
    proposals: null,
    selected_associations: {},
    calibration: null,
    proposal_decisions: [],
    issues: [],
    blockers: [],
    required_criteria: [],
    scene: null,
    preview_urls: {},
  };

  it("não acende a faixa, não filtra nada e não marca linha nenhuma", () => {
    const counts = exceptionCounts(
      antiga.packet.readings,
      readingIdsWithCandidate(antiga.associations.candidates),
    );

    expect(counts).toEqual({ auto: 0, autoNote: 0, review: 1, unresolved: 0 });
    expect(
      renderToStaticMarkup(
        <ExceptionsBand
          counts={counts}
          onlyExceptions={false}
          hiddenCount={0}
          onChange={() => undefined}
        />,
      ),
    ).toBe("");
    expect(
      visibleReadings(
        antiga.packet.readings,
        false,
        blockerReadingIds(antiga.blockers),
      ),
    ).toEqual(antiga.packet.readings);
    for (const item of antiga.packet.readings) {
      expect(renderToStaticMarkup(<AutoDecisionBadge reading={item} />)).toBe("");
    }
  });

  it("as confianças ausentes ficam ausentes: nada de zero medido", () => {
    expect(antiga.reading_confidences).toBeUndefined();
    expect(antiga.confidence_shadow).toBeUndefined();
    expect(antiga.auto_association_rate).toBeUndefined();
    expect(antiga.review_rate).toBeUndefined();
    // O `?? []` é o mesmo da tela: ausência vira lista vazia, nunca número.
    expect(antiga.reading_confidences ?? []).toEqual([]);
  });
});


/**
 * Preview da cena resolvida (F-019). O render é estático — `renderToStaticMarkup` não roda
 * efeito nenhum —, então o que se lê aqui é exatamente o que a revisora vê antes de
 * qualquer interação.
 */
describe("PreviewDaCena", () => {
  const cena: SceneRevision.CroquitoSceneRevision = {
    id: "01930000-0000-7000-8000-0000000000aa",
    job_id: "01930000-0000-7000-8000-0000000000bb",
    version: 5,
    entities: [
      {
        id: "e1",
        kind: "polyline",
        layer: "MURO",
        precision: "exact",
        geometry: {
          type: "polyline",
          closed: false,
          points: [
            { x: 0, y: 0 },
            { x: 0, y: 6 },
            { x: 10, y: 6 },
          ],
        },
      },
      {
        id: "e2",
        kind: "circle",
        layer: "CAMPO",
        precision: "unresolved",
        geometry: { type: "circle", center: { x: 12, y: 2 }, radius: 3 },
      },
    ],
  };

  it("sem cena, declara que não há o que desenhar em vez de mostrar erro", () => {
    const html = renderToStaticMarkup(
      <PreviewDaCena scene={null} estado="sem-cena" appliedSpans={[]} contestedSpans={[]} />,
    );

    expect(html).toContain("Ainda não há cena resolvida para ver");
    expect(html).not.toContain("svg");
  });

  it("a legenda nomeia as quatro precisões E descreve o traço de cada uma", () => {
    const html = renderToStaticMarkup(
      <PreviewDaCena scene={cena} estado="pronto" appliedSpans={[]} contestedSpans={[]} />,
    );

    for (const nome of ["exata", "derivada", "aproximada", "não resolvida"]) {
      expect(html).toContain(nome);
    }
    // O par escrito do estilo: quem não distingue traço fino de grosso lê a diferença.
    for (const traco of [
      "traço grosso contínuo",
      "traço fino contínuo",
      "tracejado",
      "pontilhado",
    ]) {
      expect(html).toContain(traco);
    }
  });

  it("cada forma leva a classe da própria precisão, e não uma cor", () => {
    const html = renderToStaticMarkup(
      <PreviewDaCena scene={cena} estado="pronto" appliedSpans={[]} contestedSpans={[]} />,
    );

    expect(html).toContain("cena-forma precisao-exact");
    expect(html).toContain("cena-forma precisao-unresolved");
    // Nenhuma cor viaja no markup: a distinção é de classe e de traço, resolvida na folha.
    expect(html).not.toContain("stroke=");
    expect(html).not.toContain("fill=");
  });

  it("entidade não resolvida é declarada como impedimento de exportação", () => {
    const html = renderToStaticMarkup(
      <PreviewDaCena scene={cena} estado="pronto" appliedSpans={[]} contestedSpans={[]} />,
    );

    expect(html).toContain("impede a exportação");
    expect(html).toContain("leitura, não laudo");
  });

  it("vão aplicado vira cota desenhada; vão em disputa declara que não tem posição", () => {
    const html = renderToStaticMarkup(
      <PreviewDaCena
        scene={cena}
        estado="pronto"
        appliedSpans={[
          {
            reading_id: "rd_0000000000000001",
            axis: "x",
            value_m: 9.5,
            start_m: 0.5,
            end_m: 10,
            proposal_id: "vp_0000000000000001",
          },
        ]}
        contestedSpans={[
          {
            axis: "x",
            reading_ids: ["rd_0000000000000002", "rd_0000000000000003"],
            values_m: [4.8, 3.3],
            proposal_ids: ["vp_0000000000000002"],
          },
        ]}
      />,
    );

    expect(html).toContain("aplicada · 9,50 m");
    expect(html).toContain("eixo X em disputa · 4,80 m × 3,30 m");
    // A limitação é dita na tela, e não escondida atrás de um desenho preciso demais.
    expect(html).toContain("não é declarada pelo servidor");
  });

  it("o preview não oferece edição: ver e corrigir são features diferentes", () => {
    const html = renderToStaticMarkup(
      <PreviewDaCena scene={cena} estado="pronto" appliedSpans={[]} contestedSpans={[]} />,
    );

    expect(html).toContain("Ver não é corrigir");
    expect(html).not.toContain("Corrigir forma");
  });
});

/**
 * O seletor de associação com as candidatas por identidade (F-051 T6), nos estados 05, 07
 * e 09 do Design Approval Package: o grupo por identidade ACIMA do de proximidade, nenhum
 * grupo vazio, e a lista plana de sempre quando não há identidade nenhuma.
 */
describe("CandidatasDaAssociacao", () => {
  const nomeDaProposta = (proposalId: string) => `① ${proposalId}`;

  const identidade = (proposalId: string) => ({
    proposal_id: proposalId,
    relation: "element_identity",
  });
  const perto = (proposalId: string) => ({
    proposal_id: proposalId,
    relation: "nearest_geometry",
  });

  function declaracao(
    overrides: Partial<ReviewElementDeclaration> = {},
  ): ReviewElementDeclaration {
    return {
      element_ref: "EL-002",
      label: "B — fecho da área de lazer",
      proposal_ids: ["vp_1111111111111111", "vp_2222222222222222"],
      status: "active",
      declared_by_role: "engineer",
      declared_at: "2026-09-04T20:05:00Z",
      revoked_by_role: null,
      revoked_at: null,
      ...overrides,
    };
  }

  function render(
    candidatas: readonly { proposal_id: string; relation: string }[],
    declaracoes: ReviewElementDeclaration[],
  ): string {
    return renderToStaticMarkup(
      <select>
        <CandidatasDaAssociacao
          agrupadas={agruparCandidatas(candidatas, declaracoes)}
          nomeDaProposta={nomeDaProposta}
        />
      </select>,
    );
  }

  it("sem identidade declarada, a lista é a de hoje: plana, sem grupo nenhum", () => {
    const html = render([perto("vp_9999999999999999")], []);

    expect(html).not.toContain("<optgroup");
    expect(html).toContain("① vp_9999999999999999 · geometria mais próxima");
  });

  it("com identidade, o grupo dela vem ACIMA do de proximidade, rotulado por escrito", () => {
    const html = render(
      [perto("vp_9999999999999999"), identidade("vp_1111111111111111")],
      [declaracao()],
    );

    const porIdentidade = html.indexOf(
      '<optgroup label="Pela identidade — ◇ EL-002 · B — fecho da área de lazer"',
    );
    const porProximidade = html.indexOf('<optgroup label="Pela proximidade"');

    // O primeiro grupo do seletor é o da identidade, e o da proximidade vem depois dele.
    expect(porIdentidade).toBe(html.indexOf("<optgroup"));
    expect(porIdentidade).toBeLessThan(porProximidade);
    expect(html).toContain("① vp_1111111111111111 · identidade declarada do elemento");
  });

  it("nenhum grupo vazio: só identidade não desenha o grupo da proximidade", () => {
    const html = render([identidade("vp_1111111111111111")], [declaracao()]);

    expect(html).toContain("Pela identidade — ◇ EL-002");
    expect(html).not.toContain("Pela proximidade");
  });

  it("a tela não mostra score nem distância — ela não ordena nem decide por eles", () => {
    // A candidata como a API a entrega, com os sinais de confiança da F-029 dentro dela.
    const daApi: Review["associations"]["candidates"] = [
      {
        reading_id: "rd_1111111111111111",
        proposal_id: "vp_1111111111111111",
        proposal_kind: "line",
        relation: "element_identity",
        association_confidence: 0,
        orientation_alignment: null,
      },
      {
        reading_id: "rd_1111111111111111",
        proposal_id: "vp_9999999999999999",
        proposal_kind: "line",
        relation: "nearest_geometry",
        association_confidence: 0.87,
        orientation_alignment: 0.99,
      },
    ];
    const html = render(daApi, [declaracao()]);

    expect(html).not.toContain("0.87");
    expect(html).not.toContain("0,87");
    expect(html).not.toMatch(/\bpx\b/);
  });
});

/**
 * O chip do hint do modelo (F-051 T6, estado 02 do pacote): tracejado E com a origem
 * escrita, porque sugestão nunca se veste de identidade.
 */
describe("HintDoModeloChip", () => {
  const leitura = (overrides: Partial<ReviewReading> = {}): ReviewReading => ({
    id: "rd_1111111111111111",
    raw_text: "(B) → C= 56m",
    kind: "length",
    status: "proposed",
    ...overrides,
  });

  it("escreve a origem do hint ao lado do valor lido", () => {
    const html = renderToStaticMarkup(
      <HintDoModeloChip reading={leitura({ target_entity_label: "B" })} />,
    );

    expect(html).toContain('class="hint-modelo"');
    expect(html).toContain("elemento (hint do modelo)");
    expect(html).toContain("<strong>B</strong>");
  });

  it("leitura sem hint não ganha chip — ausência é ausência, não chip vazio", () => {
    expect(renderToStaticMarkup(<HintDoModeloChip reading={leitura()} />)).toBe("");
    expect(
      renderToStaticMarkup(
        <HintDoModeloChip reading={leitura({ target_entity_label: null })} />,
      ),
    ).toBe("");
  });
});
