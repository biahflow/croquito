/**
 * Estados do painel de identidade de elemento da REVISÃO (F-051 T6) renderizados como HTML
 * estático — o padrão de teste de componente do web app (node + `renderToStaticMarkup`).
 *
 * Cobre os estados 03, 04, 08 e 09 do Design Approval Package aprovado: a revisão sem
 * declaração nenhuma (o controle), a sugestão rotulada como proposta e nunca como
 * identidade, o campo do `element_ref` somente-leitura, o carimbo por papel, a revogada
 * como histórico, e os dois silêncios que NÃO são o mesmo texto — "zero sugestões" e
 * "falha ao ler as sugestões".
 */
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import {
  AVISO_DA_SUGESTAO,
  ReviewElementIdentityBody,
  type EstadoDaIdentidadeDaRevisao,
} from "./reviewElementIdentityPanel";
import type {
  ReviewElementDeclaration,
  ReviewElementSuggestion,
  VisionProposal,
} from "./api";

const noop = () => {};

const nomeDaProposta = (proposalId: string) => `① ${proposalId}`;

function proposta(overrides: Partial<VisionProposal> = {}): VisionProposal {
  return {
    id: "vp_1111111111111111",
    kind: "line",
    precision: "unresolved",
    export: false,
    geometry: { type: "line", start: { x: 0, y: 0 }, end: { x: 10, y: 0 } },
    ...overrides,
  } as VisionProposal;
}

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

function sugestao(
  overrides: Partial<ReviewElementSuggestion> = {},
): ReviewElementSuggestion {
  return {
    suggestion_id: "els_0123456789abcdef",
    status: "unresolved",
    label: "grade B",
    proposal_ids: ["vp_1111111111111111"],
    ...overrides,
  };
}

function view(
  overrides: Partial<EstadoDaIdentidadeDaRevisao> = {},
): EstadoDaIdentidadeDaRevisao {
  return {
    declaracoes: [],
    declaracoesFalharam: false,
    sugestoes: [],
    sugestoesFalharam: false,
    propostas: [proposta()],
    selecao: [],
    motivo: "",
    rotulo: "",
    sugestaoSemente: null,
    recusandoSugestao: null,
    motivoDaRecusa: "",
    renomeando: null,
    revogando: null,
    ocupado: false,
    erro: null,
    carimbo: null,
    ...overrides,
  };
}

function render(estado: EstadoDaIdentidadeDaRevisao): string {
  return renderToStaticMarkup(
    <ReviewElementIdentityBody
      view={estado}
      nomeDaProposta={nomeDaProposta}
      onAlternarProposta={noop}
      onMotivo={noop}
      onRotulo={noop}
      onDeclarar={noop}
      onLimparSelecao={noop}
      onSemearDaSugestao={noop}
      onIniciarRecusa={noop}
      onMotivoDaRecusa={noop}
      onCancelarRecusa={noop}
      onConfirmarRecusa={noop}
      onIniciarRenomear={noop}
      onRenomear={noop}
      onCancelarRenomear={noop}
      onConfirmarRenomear={noop}
      onIniciarRevogacao={noop}
      onRevogacao={noop}
      onCancelarRevogacao={noop}
      onConfirmarRevogacao={noop}
    />,
  );
}

describe("ReviewElementIdentityBody", () => {
  it("sem declaração e sem sugestão, diz os dois silêncios por escrito", () => {
    const html = render(view());

    expect(html).toContain("Elementos declarados nesta revisão (0)");
    expect(html).toContain("Nenhum elemento declarado ainda.");
    expect(html).toContain("Sugestões a partir do rótulo do modelo (0)");
    expect(html).toContain("Nenhuma sugestão em aberto");
    // Controle: nada de identidade é afirmado, e a etiqueta ◇ não aparece à toa.
    expect(html).not.toContain("EL-0");
  });

  it("falha de leitura das sugestões é texto DIFERENTE de zero sugestões", () => {
    const vazio = render(view());
    const falha = render(view({ sugestoesFalharam: true }));

    expect(falha).toContain("Não foi possível ler as sugestões do sistema");
    expect(falha).not.toContain("Nenhuma sugestão em aberto");
    expect(vazio).not.toContain("Não foi possível ler as sugestões do sistema");
  });

  it("falha ao ler as declarações não finge lista vazia", () => {
    const html = render(view({ declaracoesFalharam: true }));

    expect(html).toContain("Não foi possível ler as identidades declaradas");
    expect(html).not.toContain("Nenhum elemento declarado ainda.");
  });

  it("a sugestão vem com o selo escrito e tracejado, e com o aviso fixo antes dela", () => {
    const html = render(view({ sugestoes: [sugestao()] }));

    expect(html).toContain(AVISO_DA_SUGESTAO);
    expect(html).toContain('class="selo-proposta"');
    expect(html).toContain("proposta · unresolved");
    expect(html).toContain("rótulo do modelo “grade B”");
    // Um único caminho de escrita: a sugestão semeia o ato, não é um ato próprio.
    expect(html).toContain("Declarar elemento a partir da proposta");
    expect(html).toContain("Descartar proposta");
  });

  it("descartar sugestão exige motivo escrito, e o impedimento aparece no campo", () => {
    const html = render(
      view({ sugestoes: [sugestao()], recusandoSugestao: "els_0123456789abcdef" }),
    );

    expect(html).toContain("Por que esta sugestão não descreve um elemento");
    expect(html).toContain("Escreva por que a proposta não descreve um elemento");
    expect(html).toContain("Registrar a recusa");
  });

  it("o element_ref é somente-leitura e nasce VAZIO: quem cunha é o servidor", () => {
    const html = render(view());

    expect(html).toContain('id="identidade-revisao-ref"');
    expect(html).toContain('readOnly=""');
    expect(html).toContain('placeholder="cunhada no ato pelo servidor"');
    expect(html).toContain("nunca digitada, nunca inferida, nunca reaproveitada");
  });

  it("o botão de declarar conta as propostas e fica bloqueado sem seleção ou motivo", () => {
    const semNada = render(view());
    const pronto = render(
      view({ selecao: ["vp_1111111111111111"], motivo: "Contorno e portão são o fecho." }),
    );

    expect(semNada).toContain("Declarar elemento com 0 propostas");
    expect(semNada).toContain("disabled=\"\"");
    expect(pronto).toContain("Declarar elemento com 1 proposta");
    expect(pronto).not.toContain("um elemento da revisão é declarado sobre geometria");
  });

  it("a semente da sugestão aparece escrita, e ela não declara nada sozinha", () => {
    const html = render(
      view({ sugestaoSemente: "els_0123456789abcdef", selecao: ["vp_1111111111111111"] }),
    );

    expect(html).toContain("Seleção semeada pela sugestão els_0123456789abcdef");
    expect(html).toContain("aceitar uma sugestão errada declara identidade errada");
  });

  it("a identidade declarada sai com etiqueta ◇, rótulo ao lado e carimbo por PAPEL", () => {
    const html = render(view({ declaracoes: [declaracao()] }));

    expect(html).toContain('class="etiqueta-elemento"');
    expect(html).toContain("EL-002");
    expect(html).toContain("B — fecho da área de lazer");
    expect(html).toContain("2 propostas");
    expect(html).toContain("Declarada por engineer em 04/09/2026 às 20:05 UTC");
    expect(html).toContain("Renomear rótulo");
    expect(html).toContain("Revogar identidade");
  });

  it("identidade sem rótulo escreve “sem rótulo”, nunca um traço mudo", () => {
    const html = render(view({ declaracoes: [declaracao({ label: null })] }));

    expect(html).toContain("sem rótulo");
  });

  it("a revogada fica no histórico, com a palavra e o carimbo de quem revogou", () => {
    const html = render(
      view({
        declaracoes: [
          declaracao({
            status: "revoked",
            revoked_by_role: "architect",
            revoked_at: "2026-09-04T21:30:00Z",
          }),
        ],
      }),
    );

    expect(html).toContain("elemento-revogado");
    expect(html).toContain("identidade revogada");
    expect(html).toContain("Revogada por architect em 04/09/2026 às 21:30 UTC");
    expect(html).toContain("não volta ao estoque");
    // Revogada não oferece renomear nem revogar de novo.
    expect(html).not.toContain("Renomear rótulo");
    expect(html).not.toContain("Revogar identidade");
  });

  it("revogar diz, no lugar do ato, que associação confirmada NÃO é desfeita", () => {
    const html = render(
      view({
        declaracoes: [declaracao()],
        revogando: { elementRef: "EL-002", motivo: "" },
      }),
    );

    expect(html).toContain("Por que esta identidade deixa de valer");
    expect(html).toContain("não desfaz associação já confirmada");
    expect(html).toContain("retificação de decisão");
  });

  it("renomear avisa que o casamento se move junto com o nome", () => {
    const html = render(
      view({
        declaracoes: [declaracao()],
        renomeando: { elementRef: "EL-002", rotulo: "grade B", motivo: "" },
      }),
    );

    expect(html).toContain("Rótulo novo");
    expect(html).toContain("deixa de ser candidato das leituras com o hint antigo");
  });

  it("proposta já declarada não é oferecida para outro elemento", () => {
    const html = render(
      view({
        propostas: [proposta(), proposta({ id: "vp_2222222222222222" })],
        declaracoes: [declaracao({ proposal_ids: ["vp_1111111111111111"] })],
      }),
    );

    expect(html).toContain("① vp_2222222222222222");
    // A declarada some da lista de seleção, mas continua citada na identidade dela.
    expect(html.split("① vp_1111111111111111")).toHaveLength(1);
  });

  it("revisão sem proposta nenhuma manda o revisor para o caminho da anotação", () => {
    const html = render(view({ propostas: [] }));

    expect(html).toContain("ainda não tem propostas de geometria");
    expect(html).toContain("anotação da folha");
  });

  it("erro é persistente e anunciado; carimbo é o registro do ato", () => {
    const html = render(
      view({ erro: "A revisão mudou desde que esta tela a leu", carimbo: "EL-002 declarado" }),
    );

    expect(html).toContain('role="alert"');
    expect(html).toContain("A revisão mudou desde que esta tela a leu");
    expect(html).toContain('class="identidade-carimbo"');
  });
});
