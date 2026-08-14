import { describe, expect, it } from "vitest";

import type { Review, VisionProposal } from "./api";
import {
  calibrationModeLabel,
  decisionActionLabel,
  derivedAnchorTitle,
  derivedDimensionLabel,
  formatDecimal,
  keepApartAxisLabel,
  measurementKindLabel,
  metricEdgeLabel,
  precisionLabel,
  proposalBadge,
  proposalDisplayName,
  readingLabel,
  readingStatusLabel,
  regionKindLabel,
  relationLabel,
  reviewBlockerLabel,
  suggestedAxisHint,
  traceBlockerLabel,
} from "./labels";

type SceneEntity = NonNullable<Review["scene"]>["entities"][number];

function lineProposal(overrides: Partial<VisionProposal> = {}): VisionProposal {
  return {
    id: "vp_0000000000000001",
    kind: "line",
    precision: "unresolved",
    export: false,
    geometry: {
      type: "line",
      start: { x: 100, y: 100 },
      end: { x: 100, y: 500 },
    },
    ...overrides,
  };
}

describe("proposalBadge", () => {
  it("uses a circled number up to twenty and a written number after it", () => {
    expect(proposalBadge(1)).toBe("①");
    expect(proposalBadge(12)).toBe("⑫");
    expect(proposalBadge(20)).toBe("⑳");
    expect(proposalBadge(21)).toBe("nº 21");
    expect(proposalBadge(83)).toBe("nº 83");
  });
});

describe("proposalDisplayName", () => {
  it("prefers the label the extraction wrote, in the professional's words", () => {
    const named = lineProposal({
      label: "Contorno principal do campo sintético",
    });

    expect(proposalDisplayName(named, 1)).toBe(
      "① Contorno principal do campo sintético",
    );
  });

  it("falls back to the geometric description in pixels without a ruler", () => {
    expect(proposalDisplayName(lineProposal(), 12)).toBe(
      "⑫ linha vertical · 400 px",
    );
  });

  it("reads the length in metres once the calibration is active", () => {
    expect(proposalDisplayName(lineProposal(), 12, 0.085)).toBe(
      "⑫ linha vertical · ≈ 34,0 m",
    );
  });

  it("ignores a blank label instead of showing an empty name", () => {
    expect(proposalDisplayName(lineProposal({ label: "   " }), 2)).toBe(
      "② linha vertical · 400 px",
    );
  });

  it("names orientation from the drawn direction", () => {
    const horizontal = lineProposal({
      geometry: {
        type: "line",
        start: { x: 0, y: 40 },
        end: { x: 300, y: 40 },
      },
    });
    const diagonal = lineProposal({
      geometry: {
        type: "line",
        start: { x: 0, y: 0 },
        end: { x: 200, y: 200 },
      },
    });

    expect(proposalDisplayName(horizontal, 3)).toBe(
      "③ linha horizontal · 300 px",
    );
    expect(proposalDisplayName(diagonal, 4)).toContain("linha inclinada");
  });

  it("describes a circle by its radius and a contour by its points", () => {
    const circle = lineProposal({
      kind: "circle",
      geometry: { type: "circle", center: { x: 50, y: 50 }, radius: 120 },
    });
    const openContour = lineProposal({
      kind: "contour",
      geometry: {
        type: "polyline",
        points: [
          { x: 0, y: 0 },
          { x: 10, y: 0 },
          { x: 10, y: 10 },
        ],
        closed: false,
      },
    });

    expect(proposalDisplayName(circle, 5)).toBe("⑤ círculo · raio 120 px");
    expect(proposalDisplayName(circle, 5, 0.05)).toBe(
      "⑤ círculo · raio ≈ 6,0 m",
    );
    expect(proposalDisplayName(openContour, 6)).toBe(
      "⑥ contorno aberto · 3 pontos",
    );
    expect(
      proposalDisplayName(
        lineProposal({
          kind: "contour",
          geometry: {
            type: "polyline",
            points: [
              { x: 0, y: 0 },
              { x: 10, y: 0 },
              { x: 10, y: 10 },
            ],
            closed: true,
          },
        }),
        7,
      ),
    ).toBe("⑦ contorno fechado · 3 pontos");
  });

  it("says the geometry is missing instead of printing an identifier", () => {
    expect(proposalDisplayName(undefined, 1)).toBe("geometria indisponível");
  });

  it("appends the suggested layer as a qualifier when there is no VLM label", () => {
    expect(
      proposalDisplayName(lineProposal({ layer_hint: "ALAMBRADO" }), 12, 0.085),
    ).toBe("⑫ linha vertical · ≈ 34,0 m · alambrado");
  });

  it("accents the layer hint that needs it and lowercases the rest verbatim", () => {
    expect(
      proposalDisplayName(lineProposal({ layer_hint: "PORTAO" }), 1),
    ).toBe("① linha vertical · 400 px · portão");
  });

  it("lowercases an unmapped layer hint instead of dropping the qualifier", () => {
    expect(
      proposalDisplayName(lineProposal({ layer_hint: "TELA_AEREA" }), 1),
    ).toBe("① linha vertical · 400 px · tela_aerea");
  });

  it("does not add a qualifier for a missing or unknown layer hint", () => {
    expect(proposalDisplayName(lineProposal({ layer_hint: null }), 1)).toBe(
      "① linha vertical · 400 px",
    );
    expect(
      proposalDisplayName(lineProposal({ layer_hint: "unknown" }), 1),
    ).toBe("① linha vertical · 400 px");
  });

  it("ignores the layer hint once a VLM label already describes the shape", () => {
    expect(
      proposalDisplayName(
        lineProposal({ label: "Muro lateral", layer_hint: "MURO" }),
        1,
      ),
    ).toBe("① Muro lateral");
  });
});

describe("dicionários de enum", () => {
  it("translates every decision action and treats absence as pending", () => {
    expect(decisionActionLabel(undefined)).toBe("pendente");
    expect(decisionActionLabel(null)).toBe("pendente");
    expect(decisionActionLabel("accept")).toBe("aceita");
    expect(decisionActionLabel("reject")).toBe("rejeitada");
    expect(decisionActionLabel("deferred")).toBe("deferred");
  });

  it("translates every measurement kind", () => {
    expect(measurementKindLabel("length")).toBe("comprimento");
    expect(measurementKindLabel("width")).toBe("largura");
    expect(measurementKindLabel("height")).toBe("altura");
    expect(measurementKindLabel("radius")).toBe("raio");
    expect(measurementKindLabel("diameter")).toBe("diâmetro");
    expect(measurementKindLabel("angle")).toBe("angle");
  });

  it("translates the association relations", () => {
    expect(relationLabel("nearest_geometry")).toBe("geometria mais próxima");
    expect(relationLabel("inside_or_near_circle")).toBe(
      "dentro ou próximo do círculo",
    );
    expect(relationLabel("same_layer")).toBe("same_layer");
  });

  it("translates the calibration mode and defaults to the contract's", () => {
    expect(calibrationModeLabel("similarity")).toBe("semelhança (uma escala)");
    expect(calibrationModeLabel("affine")).toBe("afim (escala por eixo)");
    expect(calibrationModeLabel(undefined)).toBe("semelhança (uma escala)");
    expect(calibrationModeLabel("projective")).toBe("projective");
  });

  it("translates the keep-apart axis into drawing-site direction", () => {
    expect(keepApartAxisLabel(null)).toBe("separar nos dois sentidos");
    expect(keepApartAxisLabel("x")).toBe("separar só na horizontal (lado a lado)");
    expect(keepApartAxisLabel("y")).toBe("separar só na vertical (um acima do outro)");
  });

  it("translates precision without hiding an unknown value", () => {
    expect(precisionLabel("exact")).toBe("exata");
    expect(precisionLabel("derived")).toBe("derivada");
    expect(precisionLabel("approximate")).toBe("aproximada");
    expect(precisionLabel("unresolved")).toBe("não resolvida");
    expect(precisionLabel("measured")).toBe("measured");
  });

  it("translates every reading status", () => {
    expect(readingStatusLabel("proposed")).toBe("proposta");
    expect(readingStatusLabel("ambiguous")).toBe("ambígua");
    expect(readingStatusLabel("confirmed")).toBe("confirmada");
    expect(readingStatusLabel("rejected")).toBe("rejeitada");
    expect(readingStatusLabel("expired")).toBe("expired");
  });
});

describe("metricEdgeLabel", () => {
  const edge: SceneEntity = {
    id: "0198c0de-0000-7000-8000-000000000001",
    kind: "line",
    precision: "exact",
    geometry: {
      type: "line",
      start: { x: 0, y: 0 },
      end: { x: 25.9, y: 0 },
    },
  };

  it("describes a metric edge by length and precision", () => {
    expect(metricEdgeLabel(edge)).toBe("aresta de 25,90 m · exata");
    expect(metricEdgeLabel({ ...edge, precision: "approximate" })).toBe(
      "aresta de 25,90 m · aproximada",
    );
  });

  it("stays generic for a non-line entity", () => {
    expect(
      metricEdgeLabel({ ...edge, kind: "circle", geometry: { type: "circle" } }),
    ).toBe("elemento da cena");
  });

  it("stays generic for a line without endpoints and for a missing entity", () => {
    expect(metricEdgeLabel({ ...edge, geometry: { type: "line" } })).toBe(
      "elemento da cena",
    );
    expect(metricEdgeLabel(undefined)).toBe("elemento da cena");
  });
});

describe("readingLabel", () => {
  it("keeps the written text and translates the kind", () => {
    expect(
      readingLabel({
        id: "rd_0000000000000001",
        raw_text: "21,75",
        kind: "height",
        status: "proposed",
      }),
    ).toBe("21,75 · altura");
  });
});

describe("reviewBlockerLabel", () => {
  const readings: Review["packet"]["readings"] = [
    {
      id: "rd_0000000000000001",
      raw_text: "21,75",
      kind: "height",
      status: "proposed",
    },
  ];
  const label = (blocker: string) => reviewBlockerLabel(blocker, readings);

  it("writes the three complete rectangular-solver codes in full, without a subject", () => {
    expect(label("CENTRE_CIRCLE_READING_REQUIRED")).toBe(
      "O campo pede o círculo central e nenhuma cota de raio ou diâmetro foi lida: confirme ou corrija uma leitura de raio ou diâmetro.",
    );
    expect(label("CENTRE_CIRCLE_EXCEEDS_FIELD")).toBe(
      "O círculo central confirmado não cabe dentro do campo: confira o raio ou diâmetro e as cotas de largura e altura.",
    );
    expect(label("NUMERIC_RESIDUAL_EXCEEDS_TOLERANCE")).toBe(
      "Uma medida confirmada não fecha com a geometria dentro da tolerância da cota escrita: confira as cotas confirmadas antes de aprovar.",
    );
  });

  it("says what a superseded decision costs, in the language of the site", () => {
    expect(label("READING_DECISION_SUPERSEDED")).toBe(
      "Uma medida foi corrigida depois do desenho: refaça o traçado da parte que dependia dela antes de exportar.",
    );
  });

  it("names a superseded calibration instead of calling it a scope criterion", () => {
    expect(label("CALIBRATION_SUPERSEDED")).toBe(
      "A régua da folha mudou depois que as formas foram atualizadas: refaça a calibração antes de seguir.",
    );
  });

  it("keeps the prefix/suffix decomposition and names the reading", () => {
    expect(
      label("WIDTH_HUMAN_CONFIRMATION_REQUIRED:rd_0000000000000001"),
    ).toBe('Cota de largura "21,75" aguarda sua confirmação.');
  });

  it("falls back to the scope-pending clause for an unmapped code instead of the wrong sentence", () => {
    expect(label("ACC_TOC_002")).toBe("Critério de escopo pendente: ACC_TOC_002");
  });
});

describe("regionKindLabel", () => {
  it("translates every worker region kind and returns unmapped values verbatim", () => {
    expect(regionKindLabel("main_plan")).toBe("planta principal");
    expect(regionKindLabel("detail")).toBe("detalhe construtivo");
    expect(regionKindLabel("material_list")).toBe("lista de materiais");
    expect(regionKindLabel("annotation_cluster")).toBe("bloco de anotações");
    expect(regionKindLabel("unknown")).toBe("papel ainda não identificado");
    expect(regionKindLabel("something_new")).toBe("something_new");
  });
});

describe("traceBlockerLabel", () => {
  const readings: Review["packet"]["readings"] = [
    {
      id: "rd_0000000000000001",
      raw_text: "21,75",
      kind: "height",
      status: "proposed",
    },
  ];
  const proposals = [
    lineProposal({ id: "vp_0000000000000001", label: "Muro lateral" }),
  ];
  const label = (blocker: string) =>
    traceBlockerLabel(blocker, readings, proposals);

  it("names the measurement that still waits for the professional", () => {
    expect(label("TRACE_HUMAN_CONFIRMATION_REQUIRED:rd_0000000000000001")).toBe(
      'A cota "21,75 · altura" precisa da sua confirmação antes do traçado.',
    );
  });

  it("keeps the sentence readable when the measurement is unknown", () => {
    expect(label("TRACE_HUMAN_CONFIRMATION_REQUIRED:rd_9999999999999999")).toBe(
      "Uma cota do lote precisa da sua confirmação antes do traçado.",
    );
  });

  it("explains an invalid association and a reading outside the packet", () => {
    expect(label("TRACE_ASSOCIATION_INVALID:rd_0000000000000001")).toBe(
      'A associação de a cota "21,75 · altura" não é válida: aponte um elemento, um par de elementos ou um vão declarado.',
    );
    expect(label("TRACE_READING_NOT_FOUND:rd_9999999999999999")).toBe(
      "Uma cota citada no aceite não existe mais no pacote de revisão: recarregue a revisão e refaça o lote.",
    );
  });

  it("tells the professional to bring the associated shape into the batch", () => {
    expect(label("ASSOCIATED_PROPOSAL_NOT_ACCEPTED:rd_0000000000000001")).toBe(
      'A cota "21,75 · altura" está amarrada a uma forma fora do aceite: inclua essa forma na seleção.',
    );
  });

  it("names the accepted shape that vanished from the drawing", () => {
    expect(label("ACCEPTED_PROPOSAL_NOT_FOUND:vp_0000000000000001")).toBe(
      'A forma "① Muro lateral" não existe mais entre as formas detectadas: recarregue a revisão e refaça a seleção.',
    );
  });

  it("explains a span that crosses a detail group", () => {
    expect(
      label("TRACE_ASSOCIATION_CROSSES_DETAIL_GROUP:rd_0000000000000001"),
    ).toBe(
      'A cota "21,75 · altura" liga a planta a um grupo de detalhe: a cota de vão precisa ficar dentro do mesmo grupo.',
    );
  });

  it("names the detail group with no applied measurement", () => {
    expect(label("DETAIL_GROUP_WITHOUT_APPLIED_READING:C")).toBe(
      "O grupo de detalhe C não tem nenhuma cota aplicada: confirme uma cota do grupo ou declare-o como sem escala.",
    );
  });

  it("explains the two ways a sketch detail refuses a measurement", () => {
    expect(label("TRACE_GAP_ON_SKETCH_DETAIL:rd_0000000000000001")).toBe(
      'A cota "21,75 · altura" mede um vão dentro de um detalhe sem escala: vão só vale onde a escala é verdadeira.',
    );
    expect(label("DERIVED_DIMENSION_ON_SKETCH_DETAIL:vp_0000000000000001")).toBe(
      'Foi pedida uma cota medida sobre a forma "① Muro lateral", que está num detalhe sem escala: desenho sem escala não pode ser medido.',
    );
  });

  it("explains a derived dimension over a shape left out of the batch", () => {
    expect(
      label("DERIVED_DIMENSION_TARGET_NOT_ACCEPTED:vp_0000000000000001"),
    ).toBe(
      'Foi pedida uma cota medida sobre a forma "① Muro lateral", que não está no aceite: inclua essa forma na seleção.',
    );
  });

  it("explains a declared text without a measured span", () => {
    expect(label("DIMENSION_TEXT_WITHOUT_SPAN:rd_0000000000000001")).toBe(
      'O texto declarado para a cota "21,75 · altura" não tem trecho medido correspondente.',
    );
  });

  it("handles the blocker that carries no subject", () => {
    expect(label("NO_CONFIRMED_MEASUREMENT_REACHES_TRACE")).toBe(
      "Nenhuma cota confirmada alcança as formas aceitas: confirme e associe ao menos uma cota antes de traçar.",
    );
  });

  it("names the circle whose two confirmed readings disagree", () => {
    expect(label("TRACE_CIRCLE_READINGS_CONFLICT:vp_0000000000000001")).toBe(
      'Duas cotas confirmadas dão medidas diferentes para o mesmo círculo (a forma "① Muro lateral"): confira os valores de raio e diâmetro antes de traçar.',
    );
  });

  it("names the shape whose confirmed dimensions inverted its spatial order", () => {
    expect(label("TRACE_BAND_ORDER_INVERTED:vp_0000000000000001")).toBe(
      'A forma "① Muro lateral" trocaria de lado com uma vizinha: as cotas confirmadas mandam uma linha para o outro lado de onde o croqui a desenhou. Confira os valores e as associações das cotas perto dessa forma.',
    );
  });

  it("names the numeric residual blocker without any subject", () => {
    expect(label("NUMERIC_RESIDUAL_EXCEEDS_TOLERANCE")).toBe(
      "Uma cota confirmada não fecha com a geometria traçada dentro da tolerância da cota escrita: confira as cotas confirmadas e as formas aceitas.",
    );
  });

  it("names the shape by its balloon when its hatch outline does not close", () => {
    expect(label("HATCH_TARGET_NOT_CLOSED:vp_0000000000000001")).toBe(
      'A forma "① Muro lateral" está marcada como hachura, mas o contorno não fecha: desfaça a marcação de hachura ou aceite um contorno fechado.',
    );
  });

  it("shows an unknown blocker verbatim instead of hiding it", () => {
    expect(label("TRACE_SOMETHING_NEW:rd_0000000000000001")).toBe(
      "TRACE_SOMETHING_NEW:rd_0000000000000001",
    );
  });

  it("reads the shape in metres once the ruler exists", () => {
    expect(
      traceBlockerLabel(
        "ACCEPTED_PROPOSAL_NOT_FOUND:vp_0000000000000002",
        readings,
        [lineProposal({ id: "vp_0000000000000002" })],
        0.085,
      ),
    ).toContain("① linha vertical · ≈ 34,0 m");
  });
});

describe("formatDecimal", () => {
  it("writes the decimal separator the way the drawing does", () => {
    expect(formatDecimal(25.9, 2)).toBe("25,90");
    expect(formatDecimal(3.14159, 1)).toBe("3,1");
    expect(formatDecimal(12, 0)).toBe("12");
  });
});

describe("derivedDimensionLabel", () => {
  it("names the derived dimension by its shape, without a pixel address", () => {
    expect(derivedDimensionLabel("① Muro lateral")).toBe(
      "① Muro lateral — no ponto indicado na folha",
    );
  });
});

describe("derivedAnchorTitle", () => {
  it("keeps the raw anchor available for checking, rounded to the sheet pixel", () => {
    expect(derivedAnchorTitle(1234.4, 567.5)).toBe(
      "âncora na folha: 1234, 568 px",
    );
  });
});

describe("suggestedAxisHint", () => {
  function evidence(
    bbox: { left: number; top: number; right: number; bottom: number },
    coordinateSpace = "source_image_pixels",
  ) {
    return { coordinate_space: coordinateSpace, bbox };
  }

  it("suggests width when the dimension lies flat on the sheet", () => {
    expect(
      suggestedAxisHint(
        evidence({ left: 100, top: 200, right: 400, bottom: 240 }),
      ),
    ).toBe("sugestão: largura (a cota está deitada na folha)");
  });

  it("suggests height when the dimension stands upright on the sheet", () => {
    expect(
      suggestedAxisHint(
        evidence({ left: 100, top: 200, right: 140, bottom: 500 }),
      ),
    ).toBe("sugestão: altura (a cota está em pé na folha)");
  });

  it("says nothing about an almost square crop", () => {
    expect(
      suggestedAxisHint(
        evidence({ left: 0, top: 0, right: 100, bottom: 80 }),
      ),
    ).toBeNull();
  });

  it("holds the 1.5 threshold on both sides", () => {
    expect(
      suggestedAxisHint(evidence({ left: 0, top: 0, right: 149, bottom: 100 })),
    ).toBeNull();
    expect(
      suggestedAxisHint(evidence({ left: 0, top: 0, right: 150, bottom: 100 })),
    ).toBe("sugestão: largura (a cota está deitada na folha)");
    expect(
      suggestedAxisHint(evidence({ left: 0, top: 0, right: 100, bottom: 150 })),
    ).toBe("sugestão: altura (a cota está em pé na folha)");
  });

  it("does not guess without evidence, on a degenerate box or in another space", () => {
    expect(suggestedAxisHint(undefined)).toBeNull();
    expect(
      suggestedAxisHint(evidence({ left: 10, top: 10, right: 10, bottom: 90 })),
    ).toBeNull();
    expect(
      suggestedAxisHint(
        evidence({ left: 0, top: 0, right: 400, bottom: 40 }, "page_points"),
      ),
    ).toBeNull();
  });
});
