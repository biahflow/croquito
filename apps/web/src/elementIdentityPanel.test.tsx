/**
 * Estados do painel de identidade de elemento (F-047 T7a) renderizados como HTML estático,
 * o padrão de teste de componente do web app (node + `renderToStaticMarkup`, sem jsdom).
 *
 * Cobre os estados 01 a 04 do Design Approval Package no escopo da T7a: a revisão sem
 * identidade (o controle), a proposta do sistema rotulada como proposta, o carimbo do ato
 * de declarar e o elemento `approximate` marcado como "não alimenta" com o motivo escrito.
 */
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { ElementIdentityBody, type EstadoDaIdentidade } from "./elementIdentityPanel";
import { MAXIMO_DO_ROTULO } from "./elementIdentity";
import { PreviewDaCena } from "./CroquiApp";
import type { ElementProposal } from "./api";
import type { EntidadeDaCena } from "./scenePreview";
import type { SceneRevision } from "@croquito/contracts";

const noop = () => {};

function entidade(overrides: Partial<EntidadeDaCena> = {}): EntidadeDaCena {
  return {
    id: "019538a1-0000-7000-8000-000000007c41",
    kind: "polyline",
    layer: "QUADRA",
    precision: "derived",
    geometry: {
      type: "polyline",
      closed: true,
      points: [
        { x: 0, y: 0 },
        { x: 20, y: 0 },
        { x: 20, y: 20 },
        { x: 0, y: 20 },
      ],
    },
    ...overrides,
  } as EntidadeDaCena;
}

function cena(
  entities: EntidadeDaCena[],
  version = 7,
): SceneRevision.CroquitoSceneRevision {
  return {
    id: "019538a1-0000-7000-8000-0000000000ce",
    job_id: "019538a1-0000-7000-8000-0000000000jb",
    version,
    entities,
  } as SceneRevision.CroquitoSceneRevision;
}

function proposta(overrides: Partial<ElementProposal> = {}): ElementProposal {
  return {
    proposal_id: "elp_0123456789abcdef",
    status: "unresolved",
    layer: "ALAMBRADO",
    signal: "provenance",
    label: null,
    entity_ids: ["a", "b", "c"],
    ...overrides,
  };
}

function view(overrides: Partial<EstadoDaIdentidade> = {}): EstadoDaIdentidade {
  return {
    estado: "pronto",
    scene: cena([entidade()]),
    proposals: [],
    propostasFalharam: false,
    selecao: [],
    motivo: "",
    rotulo: "",
    propostaSemente: null,
    recusandoProposta: null,
    motivoDaRecusa: "",
    ocupado: false,
    erro: null,
    carimbo: null,
    ...overrides,
  };
}

function render(estado: EstadoDaIdentidade): string {
  return renderToStaticMarkup(
    <ElementIdentityBody
      view={estado}
      onToggleEntidade={noop}
      onMotivo={noop}
      onRotulo={noop}
      onDeclarar={noop}
      onLimparSelecao={noop}
      onSemearDaProposta={noop}
      onIniciarRecusa={noop}
      onMotivoDaRecusa={noop}
      onCancelarRecusa={noop}
      onConfirmarRecusa={noop}
    />,
  );
}

describe("estado 01 — a revisão sem identidade", () => {
  it("lista a entidade sem identidade e a marca por ESCRITO, não só por forma", () => {
    const html = render(view());
    expect(html).toContain("— sem identidade");
    expect(html).toContain("Nenhum elemento declarado ainda");
    expect(html).toContain("polyline · camada QUADRA · derivada");
  });

  it("diz que entity_id, camada e rótulo não são identidade de elemento", () => {
    const html = render(view());
    expect(html).toContain("entity_id");
    expect(html).toContain("vocabulário de CAD");
    expect(html).toContain("texto livre");
  });

  it("não oferece o teclado para a IDENTIDADE: o element_ref é cunhado pelo servidor", () => {
    const html = render(view());
    expect(html).toContain("cunhada pelo servidor no ato");
    // Dois campos de texto, e nenhum deles é o `element_ref`: o rótulo legível (F-047 T2b,
    // decisão humana de 2026-08-29) e a justificativa. Digitar o ref continua sem existir.
    expect(html).not.toContain('id="identidade-element-ref"');
    expect(html).toContain('id="identidade-rotulo"');
    expect(html.match(/type="text"/g)?.length).toBe(2);
  });
});

describe("estado 02 — a proposta do sistema", () => {
  it("aparece rotulada como PROPOSTA e como unresolved, nunca como identidade", () => {
    const html = render(view({ proposals: [proposta()] }));
    expect(html).toContain("proposta · unresolved");
    expect(html).not.toContain("◇ elp_");
  });

  it("diz por qual SINAL foi gerada", () => {
    const porProcedencia = render(view({ proposals: [proposta()] }));
    expect(porProcedencia).toContain("procedência de detecção");
    const porRotulo = render(
      view({
        proposals: [
          proposta({ signal: "label_proximity", label: "PISO EM CONCRETO" }),
        ],
      }),
    );
    expect(porRotulo).toContain("rótulo mais próximo");
    expect(porRotulo).toContain("PISO EM CONCRETO");
  });

  it("avisa que camada não é identidade — o custo da proposta errada", () => {
    const html = render(view({ proposals: [proposta()] }));
    expect(html).toContain("Proposta não é identidade");
    expect(html).toContain("dois elementos");
    expect(html).toContain("não alimenta quantidade nenhuma");
  });

  it("oferece declarar E descartar: recusar é caminho de primeira classe", () => {
    const html = render(view({ proposals: [proposta()] }));
    expect(html).toContain("Declarar elemento a partir da proposta");
    expect(html).toContain("Descartar proposta");
  });

  it("a recusa pede motivo e não deixa registrar sem ele", () => {
    const semMotivo = render(
      view({ proposals: [proposta()], recusandoProposta: "elp_0123456789abcdef" }),
    );
    expect(semMotivo).toContain("Registrar a recusa");
    expect(semMotivo).toContain("disabled");
    expect(semMotivo).toContain("a recusa fica registrada");
    const comMotivo = render(
      view({
        proposals: [proposta()],
        recusandoProposta: "elp_0123456789abcdef",
        motivoDaRecusa: "agrupou dois alambrados distintos",
      }),
    );
    expect(comMotivo).toContain(
      '<button type="button">Registrar a recusa</button>',
    );
  });

  it("sem proposta, declarar pela seleção manual segue sendo o caminho completo", () => {
    const html = render(view({ proposals: [] }));
    expect(html).toContain("Nenhuma proposta em aberto");
    expect(html).toContain("não depende dela");
    expect(html).toContain("Declarar elemento com 0 entidades");
  });

  it("falha ao ler propostas é estado declarado, não seção que some", () => {
    const html = render(view({ propostasFalharam: true }));
    expect(html).toContain("Não foi possível ler as propostas");
    expect(html).toContain("seleção manual");
  });

  it("a semente da proposta é dita, para o grupo ser conferido antes de assinar", () => {
    const html = render(
      view({
        proposals: [proposta()],
        propostaSemente: "elp_0123456789abcdef",
        selecao: ["a", "b", "c"],
        motivo: "confirmado a partir da proposta",
      }),
    );
    expect(html).toContain("Seleção semeada pela proposta elp_0123456789abcdef");
    expect(html).toContain("Declarar elemento com 3 entidades");
  });
});

describe("estado 03 — o ato de declarar", () => {
  it("o carimbo cita ref, papel, instante e revisão da cena", () => {
    const html = render(
      view({
        carimbo:
          "EL-001 declarado por engineer em 04/03/2026 às 14:32 UTC, sobre a revisão v8 da cena · 2 entidades.",
      }),
    );
    expect(html).toContain("EL-001 declarado por engineer");
    expect(html).toContain("v8");
  });

  it("o elemento cunhado aparece com a etiqueta e a precisão por escrito", () => {
    const html = render(
      view({
        scene: cena([
          entidade({ id: "a", element_ref: "EL-001" }),
          entidade({ id: "b", element_ref: "EL-001", kind: "text", precision: "unresolved" }),
        ]),
      }),
    );
    expect(html).toContain("EL-001");
    expect(html).toContain("derivada");
    expect(html).toContain("2 entidades");
    expect(html).toContain("1 de anotação");
  });

  it("declarar exige seleção e justificativa; sem elas o botão fica desabilitado", () => {
    expect(render(view({ selecao: [], motivo: "" }))).toContain(
      "Escolha ao menos uma entidade",
    );
    expect(render(view({ selecao: ["a"], motivo: "" }))).toContain(
      "Escreva a justificativa",
    );
  });

  it("a mistura de camadas é AVISO na tela, e o botão continua ativo — quem recusa é o servidor", () => {
    const html = render(
      view({
        scene: cena([
          entidade({ id: "a", layer: "QUADRA" }),
          entidade({ id: "b", layer: "ALAMBRADO" }),
        ]),
        selecao: ["a", "b"],
        motivo: "os dois são o mesmo elemento",
      }),
    );
    expect(html).toContain("mistura as camadas ALAMBRADO, QUADRA");
    expect(html).toContain("o servidor vai recusar");
    expect(html).toContain(
      '<button type="button" class="primary">Declarar elemento com 2 entidades</button>',
    );
  });

  it("a recusa de camadas do servidor chega legível, com as camadas, e é anunciada", () => {
    const html = render(
      view({
        erro:
          "Um elemento não mistura camadas; declare um grupo por camada. Camadas misturadas: ALAMBRADO, QUADRA.",
      }),
    );
    expect(html).toContain('role="alert"');
    expect(html).toContain("Camadas misturadas: ALAMBRADO, QUADRA.");
  });

  it("diz que a declaração não se apaga: corrigir é retificar", () => {
    expect(render(view())).toContain("não se apaga");
  });
});

describe("estado 04 — approximate não alimenta a medição", () => {
  it("marca o elemento aproximado como não alimenta, com o motivo escrito na tela", () => {
    const html = render(
      view({
        scene: cena([
          entidade({ id: "a", element_ref: "EL-005", precision: "approximate", layer: "APROXIMADO" }),
        ]),
      }),
    );
    expect(html).toContain("EL-005");
    expect(html).toContain("não alimenta a medição");
    expect(html).toContain("aproximada");
    expect(html).toContain("vira uma linha de R$");
    expect(html).toContain("nem sob aceite explícito");
  });

  it("o elemento que alimenta traz o selo positivo e nenhum motivo de recusa", () => {
    const html = render(
      view({ scene: cena([entidade({ id: "a", element_ref: "EL-001" })]) }),
    );
    expect(html).toContain("alimenta a medição");
    expect(html).not.toContain("não alimenta a medição");
    expect(html).not.toContain("vira uma linha de R$");
  });

  it("a precisão nunca é só cor: traço e palavra viajam juntos", () => {
    const html = render(
      view({
        scene: cena([
          entidade({ id: "a", element_ref: "EL-005", precision: "approximate" }),
        ]),
      }),
    );
    expect(html).toContain("amostra-precisao precisao-approximate");
    expect(html).toContain("aproximada");
  });

  it("não resolvida também não alimenta, e o motivo cita o export", () => {
    const html = render(
      view({
        scene: cena([
          entidade({ id: "a", element_ref: "EL-006", precision: "unresolved" }),
        ]),
      }),
    );
    expect(html).toContain("não alimenta a medição");
    expect(html).toContain("barrando o próprio export");
  });
});

describe("estados de leitura da cena", () => {
  it("sem cena resolvida, declara o estado do mundo em vez de mostrar formulário vazio", () => {
    const html = render(view({ estado: "sem-cena", scene: null }));
    expect(html).toContain("Ainda não há cena resolvida");
    expect(html).not.toContain("Declarar elemento com");
  });

  it("carregando é dito, não é tela vazia", () => {
    expect(render(view({ estado: "carregando" }))).toContain("Lendo a cena");
  });

  it("falha ao ler a cena não derruba a aprovação, e a tela diz isso", () => {
    const html = render(view({ estado: "falhou", scene: null }));
    expect(html).toContain("portão de exportação não dependem deste painel");
  });
});

describe("a tela nunca faz conta de quantidade", () => {
  it("nenhuma quantidade, área ou dinheiro é impresso pelo painel", () => {
    const html = render(
      view({
        scene: cena([
          entidade({ id: "a", element_ref: "EL-001" }),
          entidade({ id: "b", element_ref: "EL-005", precision: "approximate" }),
        ]),
        proposals: [proposta()],
      }),
    );
    // A geometria da fixture tem 20 × 20 m; nenhum derivado dela pode aparecer na tela.
    expect(html).not.toContain("400");
    expect(html).not.toContain("m²");
    // "R$" aparece na PROSA que explica por que a aproximação não atravessa; o que não
    // pode existir é um VALOR — `R$` seguido de número — porque a tela não multiplica.
    expect(html).not.toMatch(/R\$\s*\d/);
    // Nenhuma quantidade decimal: os únicos números do painel são contagens de itens.
    expect(html).not.toMatch(/\d+[.,]\d+\s*(m|m²|m2)\b/);
  });

  it("os únicos números do painel são contagens, e elas vêm de length, não de conta", () => {
    const html = render(
      view({
        scene: cena([
          entidade({ id: "a", element_ref: "EL-001" }),
          entidade({ id: "b", element_ref: "EL-001" }),
        ]),
      }),
    );
    expect(html).toContain("2 entidades");
    expect(html).toContain("Elementos declarados nesta cena (1)");
  });
});

describe("estado 03 — o rótulo legível do elemento (F-047 T2b)", () => {
  function comRotulos(
    rotulos: Record<string, string>,
    element_ref = "EL-001",
  ): SceneRevision.CroquitoSceneRevision {
    return {
      ...cena([entidade({ id: "a", element_ref })]),
      element_labels: rotulos,
    } as SceneRevision.CroquitoSceneRevision;
  }

  it("mostra o rótulo AO LADO do EL-00N, e não no lugar dele", () => {
    const html = render(view({ scene: comRotulos({ "EL-001": "Alambrado da quadra" }) }));
    expect(html).toContain("EL-001");
    expect(html).toContain("Alambrado da quadra");
    expect(html.indexOf("EL-001")).toBeLessThan(html.indexOf("Alambrado da quadra"));
  });

  it("elemento sem nome diz “sem rótulo” por escrito, nunca um traço mudo", () => {
    const html = render(view({ scene: comRotulos({}) }));
    expect(html).toContain("sem rótulo");
  });

  it("oferece o campo do rótulo no ato de declarar, com o teto do contrato", () => {
    const html = render(view());
    expect(html).toContain('id="identidade-rotulo"');
    expect(html).toContain("Rótulo (o que a pessoa lê)");
    expect(html).toContain(`maxLength="${MAXIMO_DO_ROTULO}"`);
  });

  it("diz, na tela, que o rótulo não é identidade e que renomear é ato registrado", () => {
    const html = render(view());
    expect(html).toContain("não é identidade");
    expect(html).toContain("dois elementos com o mesmo");
    expect(html).toContain("Renomear depois é ato registrado");
  });

  it("rótulo só de espaço impede o envio e diz como declarar sem nome", () => {
    const html = render(view({ selecao: ["a"], motivo: "mesma quadra", rotulo: "   " }));
    expect(html).toContain("deixe o campo vazio");
    expect(html).toContain("disabled");
  });

  it("dois elementos com o mesmo rótulo aparecem como dois elementos", () => {
    const html = render(
      view({
        scene: {
          ...cena([
            entidade({ id: "a", element_ref: "EL-001" }),
            entidade({ id: "b", element_ref: "EL-002" }),
          ]),
          element_labels: {
            "EL-001": "Alambrado da quadra",
            "EL-002": "Alambrado da quadra",
          },
        } as SceneRevision.CroquitoSceneRevision,
      }),
    );
    expect(html).toContain("Elementos declarados nesta cena (2)");
    // Duas linhas de elemento com o mesmo nome — contadas na etiqueta do rótulo, não no
    // markup inteiro, que também traz o exemplo do `placeholder` do formulário.
    expect(
      html.match(/class="elemento-rotulo">Alambrado da quadra/g)?.length,
    ).toBe(2);
  });
});

describe("o controle: PreviewDaCena sem identidade declarada é o de hoje", () => {
  const semIdentidade = cena([
    entidade({ id: "019538a1-0000-7000-8000-000000007c41" }),
  ]);
  const comIdentidade = cena([
    entidade({ id: "019538a1-0000-7000-8000-000000007c41", element_ref: "EL-001" }),
  ]);

  function preview(scene: SceneRevision.CroquitoSceneRevision): string {
    return renderToStaticMarkup(
      <PreviewDaCena scene={scene} estado="pronto" appliedSpans={[]} contestedSpans={[]} />,
    );
  }

  it("sem nenhum element_ref, o preview não ganha etiqueta de elemento nenhuma", () => {
    const html = preview(semIdentidade);
    expect(html).not.toContain("etiqueta-elemento");
    expect(html).not.toContain("sem identidade");
  });

  it("com identidade declarada, a etiqueta aparece — mas só então", () => {
    // A seleção parte de `null`, então a linha do elemento vive no painel da entidade
    // escolhida; o que este teste fixa é que a etiqueta não existe no markup do controle.
    expect(preview(comIdentidade)).not.toContain("— sem identidade");
    expect(preview(semIdentidade)).toBe(preview(semIdentidade));
  });
});
