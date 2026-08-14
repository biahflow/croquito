import type { Review, VisionProposal } from "./api";

/**
 * Quem revisa é engenheiro ou projetista de obra, não desenvolvedor: identificador
 * técnico e enum em inglês não podem aparecer em texto visível. Este módulo é a única
 * fonte dos nomes exibidos no painel de revisão e é puro para ser testado sem DOM.
 */

type SceneEntity = NonNullable<Review["scene"]>["entities"][number];
type Reading = Review["packet"]["readings"][number];

/** Número com vírgula decimal, como a cota é escrita na folha. */
export function formatDecimal(value: number, decimals: number): string {
  return value.toFixed(decimals).replace(".", ",");
}

const CIRCLED_NUMBERS = [
  "①",
  "②",
  "③",
  "④",
  "⑤",
  "⑥",
  "⑦",
  "⑧",
  "⑨",
  "⑩",
  "⑪",
  "⑫",
  "⑬",
  "⑭",
  "⑮",
  "⑯",
  "⑰",
  "⑱",
  "⑲",
  "⑳",
];

/**
 * O balão acompanha a posição da proposta na lista e é o mesmo em toda a tela: é por
 * ele que o revisor amarra o que lê ao que vê no desenho. Passando de vinte, o balão
 * vira número escrito em vez de um caractere que muitas fontes não desenham.
 */
export function proposalBadge(ordinal: number): string {
  return CIRCLED_NUMBERS[ordinal - 1] ?? `nº ${ordinal}`;
}

const PRECISION_LABELS: Record<string, string> = {
  exact: "exata",
  derived: "derivada",
  approximate: "aproximada",
  unresolved: "não resolvida",
};

export function precisionLabel(precision: string): string {
  return PRECISION_LABELS[precision] ?? precision;
}

const DECISION_ACTION_LABELS: Record<string, string> = {
  pending: "pendente",
  accept: "aceita",
  reject: "rejeitada",
};

/** Proposta sem decisão registrada está pendente; ausência é estado, não erro. */
export function decisionActionLabel(action?: string | null): string {
  const key = action ?? "pending";
  return DECISION_ACTION_LABELS[key] ?? key;
}

const READING_STATUS_LABELS: Record<string, string> = {
  proposed: "proposta",
  ambiguous: "ambígua",
  confirmed: "confirmada",
  rejected: "rejeitada",
};

/** Feminino porque qualifica "a leitura"/"a cota", não o enum em si. */
export function readingStatusLabel(status: string): string {
  return READING_STATUS_LABELS[status] ?? status;
}

const MEASUREMENT_KIND_LABELS: Record<string, string> = {
  length: "comprimento",
  width: "largura",
  height: "altura",
  radius: "raio",
  diameter: "diâmetro",
};

export function measurementKindLabel(kind: string): string {
  return MEASUREMENT_KIND_LABELS[kind] ?? kind;
}

/**
 * Rótulo do eixo de separação do par manter-separados, em língua de obra — a direção
 * do desenho, não a letra do eixo. Mapeamento conferido em
 * `services/worker/src/croquito_worker/geometry_solver.py` (docstring de
 * `BandSeparation`) e no espelho `KeepApartPair` de
 * `services/worker/src/croquito_worker/tracing.py`: no caso do Guaxindiba, a mureta
 * e o patamar precisam ficar em "faixas X distintas" — o recuo HORIZONTAL de 3,30/4,80
 * que a folha cota — enquanto o encontro VERTICAL entre a base da mureta e a base do
 * campo é legítimo e não deve ser separado. Eixo x = lado a lado (horizontal); eixo y =
 * um acima do outro (vertical).
 */
const KEEP_APART_AXIS_LABELS: Record<"x" | "y", string> = {
  x: "separar só na horizontal (lado a lado)",
  y: "separar só na vertical (um acima do outro)",
};

/** `null` é o formato histórico do aceite: separa nos dois sentidos, sem eixo único. */
export function keepApartAxisLabel(axis: "x" | "y" | null): string {
  return axis === null ? "separar nos dois sentidos" : KEEP_APART_AXIS_LABELS[axis];
}

const RELATION_LABELS: Record<string, string> = {
  nearest_geometry: "geometria mais próxima",
  inside_or_near_circle: "dentro ou próximo do círculo",
};

export function relationLabel(relation: string): string {
  return RELATION_LABELS[relation] ?? relation;
}

const CALIBRATION_MODE_LABELS: Record<string, string> = {
  similarity: "semelhança (uma escala)",
  affine: "afim (escala por eixo)",
};

/** Calibração sem modo declarado é semelhança: é o default do contrato, não um palpite. */
export function calibrationModeLabel(mode?: string | null): string {
  const key = mode ?? "similarity";
  return CALIBRATION_MODE_LABELS[key] ?? key;
}

function lineOrientation(dx: number, dy: number): string {
  const degrees = (Math.atan2(dy, dx) * (180 / Math.PI) + 180) % 180;
  if (degrees < 20 || degrees > 160) {
    return "horizontal";
  }
  return degrees > 70 && degrees < 110 ? "vertical" : "inclinada";
}

/**
 * Sem calibração ativa a medida continua em pixel — escrever metro antes da régua
 * existir seria inventar dimensão. Com a régua, o comprimento sai aproximado e
 * declarado como tal.
 */
function pixelExtent(pixels: number, scaleMPerPx?: number | null): string {
  if (scaleMPerPx && scaleMPerPx > 0) {
    return `≈ ${formatDecimal(pixels * scaleMPerPx, 1)} m`;
  }
  return `${Math.round(pixels)} px`;
}

const LAYER_HINT_LABELS: Record<string, string> = {
  CONTORNO: "contorno",
  CAMPO: "campo",
  QUADRA: "quadra",
  MURO: "muro",
  ALAMBRADO: "alambrado",
  PORTAO: "portão",
  PATAMAR: "patamar",
  EQUIPAMENTOS: "equipamentos",
  DETALHES: "detalhes",
};

/**
 * O worker já converte "unknown" para `null` antes do contrato chegar ao front, mas a
 * checagem aqui é defensiva: nenhuma camada sugerida vale como qualificador visível.
 */
function layerHintLabel(hint?: string | null): string | null {
  if (!hint || hint === "unknown") {
    return null;
  }
  return LAYER_HINT_LABELS[hint] ?? hint.toLowerCase();
}

function geometryDescription(
  proposal: VisionProposal,
  scaleMPerPx?: number | null,
): string {
  const geometry = proposal.geometry;
  let description: string;
  if (geometry.type === "circle") {
    description = `círculo · raio ${pixelExtent(geometry.radius, scaleMPerPx)}`;
  } else if (geometry.type === "polyline") {
    const shape = geometry.closed ? "fechado" : "aberto";
    description = `contorno ${shape} · ${geometry.points.length} pontos`;
  } else {
    const dx = geometry.end.x - geometry.start.x;
    const dy = geometry.end.y - geometry.start.y;
    description = `linha ${lineOrientation(dx, dy)} · ${pixelExtent(
      Math.hypot(dx, dy),
      scaleMPerPx,
    )}`;
  }
  // Camada sugerida é um qualificador barato para distinguir formas sem rótulo da
  // extração; com rótulo VLM esta função nem é chamada (ver proposalDisplayName).
  const layer = layerHintLabel(proposal.layer_hint);
  return layer ? `${description} · ${layer}` : description;
}

/**
 * Oitenta e três propostas chamadas "linha horizontal" são indistinguíveis. O balão
 * dá endereço a cada uma; o rótulo da extração entra quando existe, e a descrição
 * geométrica entra quando não existe — o caminho determinístico não sabe o que a
 * linha representa e não deve fingir que sabe.
 */
export function proposalDisplayName(
  proposal: VisionProposal | undefined,
  ordinal: number,
  scaleMPerPx?: number | null,
): string {
  if (!proposal) {
    return "geometria indisponível";
  }
  const label = proposal.label?.trim();
  const description = label
    ? label
    : geometryDescription(proposal, scaleMPerPx);
  return `${proposalBadge(ordinal)} ${description}`;
}

/**
 * A cena métrica não nomeia entidade; o que o revisor reconhece nela é o comprimento
 * já resolvido e o quanto ele é confiável.
 */
export function metricEdgeLabel(entity: SceneEntity | undefined): string {
  const geometry = entity?.geometry;
  if (!entity || geometry?.type !== "line" || !geometry.start || !geometry.end) {
    return "elemento da cena";
  }
  const length = Math.hypot(
    geometry.end.x - geometry.start.x,
    geometry.end.y - geometry.start.y,
  );
  return `aresta de ${formatDecimal(length, 2)} m · ${precisionLabel(
    entity.precision,
  )}`;
}

export function readingLabel(reading: Reading): string {
  return `${reading.raw_text} · ${measurementKindLabel(reading.kind)}`;
}

/**
 * Cota derivada na lista do aceite. O revisor a reconhece pela forma que ela mede e
 * pelo ponto que ele mesmo clicou na folha — a coordenada em pixel é endereço de
 * máquina e sai do texto visível (fica no `title`, ver `derivedAnchorTitle`).
 */
export function derivedDimensionLabel(proposalName: string): string {
  return `${proposalName} — no ponto indicado na folha`;
}

/** A coordenada crua continua acessível para conferência, fora da leitura corrida. */
export function derivedAnchorTitle(xPx: number, yPx: number): string {
  return `âncora na folha: ${Math.round(xPx)}, ${Math.round(yPx)} px`;
}

/** Razão mínima entre os lados do recorte para a cota ter orientação declarável. */
const AXIS_HINT_RATIO = 1.5;

/**
 * Sugestão de eixo lida da própria evidência: cota escrita deitada na folha quase
 * sempre mede largura, cota em pé mede altura. É dica textual e nada mais — o campo
 * continua sem nada pré-selecionado, e quem declara o eixo é o revisor.
 *
 * O bbox é da FOLHA, no espaço de pixels da imagem de origem: a rotação escolhida no
 * visualizador é preferência de leitura e não muda a orientação do que está escrito.
 * Recorte declarado em outro espaço de coordenadas não produz sugestão nenhuma —
 * palpitar sobre um espaço desconhecido seria inventar direção.
 */
export function suggestedAxisHint(evidence: Reading["evidence"]): string | null {
  if (!evidence || evidence.coordinate_space !== "source_image_pixels") {
    return null;
  }
  const width = evidence.bbox.right - evidence.bbox.left;
  const height = evidence.bbox.bottom - evidence.bbox.top;
  if (width <= 0 || height <= 0) {
    return null;
  }
  if (width / height >= AXIS_HINT_RATIO) {
    return "sugestão: largura (a cota está deitada na folha)";
  }
  if (height / width >= AXIS_HINT_RATIO) {
    return "sugestão: altura (a cota está em pé na folha)";
  }
  // Recorte quase quadrado não diz em que direção a cota mede; sem sugestão.
  return null;
}

function capitalise(text: string): string {
  return text.charAt(0).toUpperCase() + text.slice(1);
}

const REGION_KIND_LABELS: Record<string, string> = {
  main_plan: "planta principal",
  detail: "detalhe construtivo",
  material_list: "lista de materiais",
  annotation_cluster: "bloco de anotações",
  unknown: "papel ainda não identificado",
};

/** Enum bruto do worker (`RegionKind`) nunca aparece cru para quem revisa o papel. */
export function regionKindLabel(kind: string): string {
  return REGION_KIND_LABELS[kind] ?? kind;
}

/**
 * Códigos que o solver retangular emite sem sujeito (nenhum `:id` depois do código):
 * o texto inteiro já é a mensagem, e um código novo sem entrada aqui cairia no
 * fallback de decomposição prefixo/sufixo abaixo, que não o reconhece.
 */
const REVIEW_BLOCKER_CODES: Record<string, string> = {
  CENTRE_CIRCLE_READING_REQUIRED:
    "O campo pede o círculo central e nenhuma cota de raio ou diâmetro foi lida: confirme ou corrija uma leitura de raio ou diâmetro.",
  CENTRE_CIRCLE_EXCEEDS_FIELD:
    "O círculo central confirmado não cabe dentro do campo: confira o raio ou diâmetro e as cotas de largura e altura.",
  NUMERIC_RESIDUAL_EXCEEDS_TOLERANCE:
    "Uma medida confirmada não fecha com a geometria dentro da tolerância da cota escrita: confira as cotas confirmadas antes de aprovar.",
  READING_DECISION_SUPERSEDED:
    "Uma medida foi corrigida depois do desenho: refaça o traçado da parte que dependia dela antes de exportar.",
  CALIBRATION_SUPERSEDED:
    "A régua da folha mudou depois que as formas foram atualizadas: refaça a calibração antes de seguir.",
};

const REVIEW_BLOCKER_REASONS: Record<string, string> = {
  HUMAN_CONFIRMATION_REQUIRED: "aguarda sua confirmação",
  INCOMPLETE_CONFIRMATION: "foi confirmada sem valor utilizável",
  KIND_MISMATCH: "tem tipo incompatível com o que o solver espera",
  READING_NOT_FOUND: "não existe no pacote de revisão",
  EXPLICIT_ASSOCIATION_REQUIRED: "precisa de uma associação explícita",
};

const REVIEW_BLOCKER_SUBJECTS: Record<string, string> = {
  WIDTH: "Cota de largura",
  HEIGHT: "Cota de altura",
  CENTRE_CIRCLE: "Cota do círculo central",
};

/**
 * O revisor precisa saber o que falta, não o identificador interno. O código
 * continua visível ao lado no call site: é ele que vale no registro de auditoria.
 */
export function reviewBlockerLabel(
  blocker: string,
  readings: Reading[],
): string {
  const [code, readingId] = blocker.split(":");
  if (REVIEW_BLOCKER_CODES[code]) {
    return REVIEW_BLOCKER_CODES[code];
  }
  const reading = readings.find((item) => item.id === readingId);
  const subject = Object.keys(REVIEW_BLOCKER_SUBJECTS).find((prefix) =>
    code.startsWith(`${prefix}_`),
  );
  const reason = Object.keys(REVIEW_BLOCKER_REASONS).find((suffix) =>
    code.endsWith(suffix),
  );
  if (!reason) {
    return reading
      ? `Critério pendente na leitura "${reading.raw_text}"`
      : `Critério de escopo pendente: ${code}`;
  }
  const what = subject
    ? REVIEW_BLOCKER_SUBJECTS[subject]
    : reading
      ? "Leitura"
      : "Uma leitura";
  const detail = reading ? ` "${reading.raw_text}"` : "";
  return `${what}${detail} ${REVIEW_BLOCKER_REASONS[reason]}.`;
}

/**
 * Blockers do traçado chegam como `CODIGO:<id>`, com id de leitura (`rd_…`), de forma
 * (`vp_…`) ou de grupo de detalhe. O revisor precisa saber qual cota ou qual forma
 * precisa dele — o identificador fica no `code` ao lado, que é o que vale na auditoria.
 * Código desconhecido devolve o próprio código: esconder um bloqueio é pior do que
 * mostrá-lo cru.
 */
export function traceBlockerLabel(
  blocker: string,
  readings: Reading[],
  proposals: VisionProposal[],
  scaleMPerPx?: number | null,
): string {
  const separator = blocker.indexOf(":");
  const code = separator === -1 ? blocker : blocker.slice(0, separator);
  const subject = separator === -1 ? "" : blocker.slice(separator + 1);
  const reading = readings.find((item) => item.id === subject);
  const measurement = reading
    ? `a cota "${readingLabel(reading)}"`
    : "uma cota do lote";
  const proposalIndex = proposals.findIndex((item) => item.id === subject);
  const shape =
    proposalIndex >= 0
      ? `a forma "${proposalDisplayName(
          proposals[proposalIndex],
          proposalIndex + 1,
          scaleMPerPx,
        )}"`
      : "uma forma do aceite";

  switch (code) {
    case "TRACE_HUMAN_CONFIRMATION_REQUIRED":
      return `${capitalise(measurement)} precisa da sua confirmação antes do traçado.`;
    case "TRACE_ASSOCIATION_INVALID":
      return `A associação de ${measurement} não é válida: aponte um elemento, um par de elementos ou um vão declarado.`;
    case "TRACE_READING_NOT_FOUND":
      return "Uma cota citada no aceite não existe mais no pacote de revisão: recarregue a revisão e refaça o lote.";
    case "ASSOCIATED_PROPOSAL_NOT_ACCEPTED":
      return `${capitalise(measurement)} está amarrada a uma forma fora do aceite: inclua essa forma na seleção.`;
    case "ACCEPTED_PROPOSAL_NOT_FOUND":
      return `${capitalise(shape)} não existe mais entre as formas detectadas: recarregue a revisão e refaça a seleção.`;
    case "TRACE_ASSOCIATION_CROSSES_DETAIL_GROUP":
      return `${capitalise(measurement)} liga a planta a um grupo de detalhe: a cota de vão precisa ficar dentro do mesmo grupo.`;
    case "DETAIL_GROUP_WITHOUT_APPLIED_READING":
      return `O grupo de detalhe ${subject} não tem nenhuma cota aplicada: confirme uma cota do grupo ou declare-o como sem escala.`;
    case "TRACE_GAP_ON_SKETCH_DETAIL":
      return `${capitalise(measurement)} mede um vão dentro de um detalhe sem escala: vão só vale onde a escala é verdadeira.`;
    case "DERIVED_DIMENSION_ON_SKETCH_DETAIL":
      return `Foi pedida uma cota medida sobre ${shape}, que está num detalhe sem escala: desenho sem escala não pode ser medido.`;
    case "DERIVED_DIMENSION_TARGET_NOT_ACCEPTED":
      return `Foi pedida uma cota medida sobre ${shape}, que não está no aceite: inclua essa forma na seleção.`;
    case "DIMENSION_TEXT_WITHOUT_SPAN":
      return `O texto declarado para ${measurement} não tem trecho medido correspondente.`;
    case "NO_CONFIRMED_MEASUREMENT_REACHES_TRACE":
      return "Nenhuma cota confirmada alcança as formas aceitas: confirme e associe ao menos uma cota antes de traçar.";
    case "TRACE_CIRCLE_READINGS_CONFLICT":
      return `Duas cotas confirmadas dão medidas diferentes para o mesmo círculo (${shape}): confira os valores de raio e diâmetro antes de traçar.`;
    case "TRACE_BAND_ORDER_INVERTED":
      return `${capitalise(shape)} trocaria de lado com uma vizinha: as cotas confirmadas mandam uma linha para o outro lado de onde o croqui a desenhou. Confira os valores e as associações das cotas perto dessa forma.`;
    case "NUMERIC_RESIDUAL_EXCEEDS_TOLERANCE":
      return "Uma cota confirmada não fecha com a geometria traçada dentro da tolerância da cota escrita: confira as cotas confirmadas e as formas aceitas.";
    case "HATCH_TARGET_NOT_CLOSED":
      return `${capitalise(shape)} está marcada como hachura, mas o contorno não fecha: desfaça a marcação de hachura ou aceite um contorno fechado.`;
    default:
      return blocker;
  }
}
