import type {
  DeclaredChain,
  DimensionChain,
  Review,
  TraceAppliedSpan,
  TraceContestedSpan,
  TraceUnappliedReading,
  VisionProposal,
} from "./api";

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
  diagonal: "diagonal",
  level: "nível",
  drop: "desnível",
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
  // F-051 T4. A tela de revisão já escreve a relação de cada candidata, e enum em inglês
  // não aparece para quem revisa (FDD, nomenclatura do painel de geometria) — por isso a
  // tradução entra junto com o valor novo do contrato. Como a candidata por identidade é
  // apresentada ao lado das de proximidade (destaque, ordem, ícone) é decisão da T6.
  element_identity: "identidade declarada do elemento",
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

/**
 * Padrão de elevação escrito na folha: `h` seguido de `=`, com espaço opcional e em
 * qualquer posição do texto ("muro Vizinho h=3,80", "H = 2,50"). A fronteira de palavra
 * existe para o `h` ser palavra e não sílaba de outra.
 */
const ELEVATION_PATTERN = /\bh\s*=/i;

/**
 * Sugestão de que a leitura é anotação da folha — um recado escrito, não a medida de um
 * elemento. Dois sinais independentes, cada um com a sua frase, para o revisor saber de
 * ONDE veio a sugestão: o pipeline classificou a linha como recado, ou o próprio texto
 * declara altura de elemento.
 *
 * Sugerir não é decidir: a opção só nasce marcada no formulário. A justificativa
 * continua obrigatória, os candidatos continuam na lista e trocar a seleção à mão vale
 * mais do que qualquer sugestão daqui.
 *
 * A heurística de texto é deliberadamente estreita. `h=` é inequívoco; "mureta 1,54" não
 * é — palavra de elemento vertical seguida de número puro continua sendo cota candidata,
 * e adivinhar classificação a partir dela seria inventar o que o revisor não escreveu.
 * Esse caso fica para o sinal do modelo.
 */
export function suggestedAnnotationHint(reading: Reading): string | null {
  if (reading.annotation_suggested === true) {
    return "sugestão: anotação da folha (o modelo leu como recado, não como cota)";
  }
  if (ELEVATION_PATTERN.test(reading.raw_text)) {
    return "sugestão: anotação da folha (o texto declara altura de elemento)";
  }
  return null;
}

/**
 * Aviso de segunda testemunha ausente: o braço de OCR leu a folha e não encontrou o
 * texto da leitura na mesma região. Caso fundador (24,75 vs 19,75 na V17): o pacote
 * sabia (`OCR_EVIDENCE_MISSING`) e a nota ficava só na telemetria, invisível na tela.
 *
 * Só `false` fala. Confirmação (`true`) e ausência de braço (`null`/indefinido) ficam
 * em silêncio: um `✓` em toda linha viraria ruído, e o braço nunca rodar não é o mesmo
 * alerta que o braço ter rodado e discordado.
 */
export function ocrWitnessHint(reading: Reading): string | null {
  if (reading.ocr_corroborated === false) {
    return (
      "sem segunda testemunha: o OCR leu a folha e não encontrou este texto — confira " +
      "o recorte (leitura trocada é o caso clássico: 1↔2, 9↔4)"
    );
  }
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
 * Vista de exceções da revisão (F-029): as contagens que o revisor lê no topo.
 *
 * `auto` são as cotas que o sistema confirmou sozinho por dupla testemunha, `annotation`
 * as anotações que ele confirmou por testemunha única (elevações e recados da folha —
 * ADR-0044), `review` as que ainda esperam uma pessoa e têm a quem associar, e
 * `unresolved` as que esperam uma pessoa sem candidato nenhum no desenho — o pior caso, e
 * por isso ele tem contador próprio em vez de ficar escondido dentro do total pendente.
 *
 * Cota e anotação contam separado porque o que se aceita de um rótulo não é o que se
 * aceita de uma medida: somá-las esconderia justamente a diferença de custo do erro que
 * fez os dois tiers existirem.
 *
 * O ícone acompanha a palavra e nunca a substitui: quem lê por leitor de tela ouve
 * "4 auto-associadas", não um caractere. Os dois atos de máquina compartilham o ⚙ de
 * propósito — o que os distingue é a palavra, como manda a regra de não indicar estado
 * só por marca visual.
 */
export type ExceptionCounterKind =
  | "auto"
  | "annotation"
  | "review"
  | "unresolved";

const EXCEPTION_COUNTER_LABELS: Record<
  ExceptionCounterKind,
  { icon: string; one: string; many: string }
> = {
  auto: { icon: "⚙", one: "auto-associada", many: "auto-associadas" },
  annotation: {
    icon: "⚙",
    one: "anotação automática",
    many: "anotações automáticas",
  },
  review: { icon: "⚠", one: "precisa de revisão", many: "precisam de revisão" },
  unresolved: { icon: "✗", one: "não resolvida", many: "não resolvidas" },
};

export function exceptionCounterLabel(
  kind: ExceptionCounterKind,
  count: number,
): string {
  const label = EXCEPTION_COUNTER_LABELS[kind];
  return `${label.icon} ${count} ${count === 1 ? label.one : label.many}`;
}

/** Os dois estados do filtro da lista; nenhum deles decide nada, só o que fica à vista. */
export function exceptionFilterLabel(mode: "only" | "all"): string {
  return mode === "only" ? "só exceções" : "todas";
}

/**
 * Versão do score que produziu uma auto-decisão, extraída da identidade do ator-máquina
 * (`system:auto-association@1.0.0`, carimbada pelo worker em `system_reviewer_id`).
 *
 * `null` quando a identidade não tem esse formato: a tela então diz apenas que o sistema
 * associou, sem inventar uma versão e sem despejar o identificador cru na leitura corrida.
 */
export function autoDecisionScoreVersion(reviewerId: string): string | null {
  const match = /^system:[^@]+@(.+)$/.exec(reviewerId.trim());
  return match ? match[1] : null;
}

/**
 * Proveniência de máquina por extenso, do lado da leitura: por qual regra o sistema
 * decidiu e com que versão de score. Texto, nunca só cor — e nunca o `reviewer_id` cru.
 *
 * O tier muda a PALAVRA, não só o tom: "anotação automática" avisa que aquela linha
 * entrou com uma testemunha só porque não manda na geometria, e quem revisa precisa
 * poder pesar isso sem abrir a justificativa. Sem tier declarado — decisão de sistema
 * gravada antes do campo — a frase é a de sempre, que descreve o tier de cota.
 */
export function autoDecisionProvenanceLabel(
  reviewerId: string,
  tier?: "cota" | "anotacao" | null,
): string {
  const version = autoDecisionScoreVersion(reviewerId);
  const act =
    tier === "anotacao" ? "anotação automática" : "associada pelo sistema";
  return version ? `${act} · score ${version}` : act;
}

/**
 * Confiança da leitura como o pipeline a registrou, com vírgula decimal.
 *
 * É observação exibida ao lado da decisão que ela motivou, e não um veredito: a tela não
 * compara com corte, não classifica em faixas e não esconde nada por causa dela.
 */
export function readingConfidenceLabel(confidence: number): string {
  return `confiança ${formatDecimal(confidence, 2)}`;
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

/** Nome de obra da forma pelo balão da lista; forma que saiu do desenho é dita assim. */
function shapePhrase(
  proposalId: string,
  proposals: VisionProposal[],
  scaleMPerPx?: number | null,
): string {
  const index = proposals.findIndex((item) => item.id === proposalId);
  return index >= 0
    ? `a forma "${proposalDisplayName(proposals[index], index + 1, scaleMPerPx)}"`
    : "uma forma que não está mais no desenho";
}

/**
 * Por que uma cota confirmada não virou vão, em língua de obra (F-025). O molde é o
 * `traceBlockerLabel`: a causa é código estável do domínio, a frase diz o que aconteceu e
 * o que costuma consertar, e a forma é citada pelo balão que o revisor reconhece na lista.
 * Código desconhecido devolve o próprio código — esconder um descarte é pior do que
 * mostrá-lo cru.
 *
 * A entrada é a `TraceUnappliedReading` inteira, e não só `cause`: nomear a forma pelo
 * balão exige o alvo que a associação apontava, que viaja na própria entrada.
 */
export function traceUnappliedCauseLabel(
  unapplied: TraceUnappliedReading,
  readings: Reading[],
  proposals: VisionProposal[],
  scaleMPerPx?: number | null,
): string {
  const reading = readings.find((item) => item.id === unapplied.reading_id);
  const measurement = reading
    ? `a cota "${readingLabel(reading)}"`
    : "uma cota do lote";
  const targets = unapplied.target_proposal_ids;
  const shapes = targets.length
    ? targets.map((id) => shapePhrase(id, proposals, scaleMPerPx)).join(" e ")
    : "a forma que ela aponta";

  switch (unapplied.cause) {
    case "TRACE_SPAN_VALUE_OR_DECISION_MISSING":
      return `${capitalise(measurement)} chegou ao traçado sem valor em metros ou sem decisão humana completa: reveja a leitura na revisão de cotas.`;
    case "TRACE_SPAN_AXIS_UNDECLARED":
      return `${capitalise(measurement)} não declara em que direção mede: corrija o tipo para largura (horizontal) ou altura (vertical).`;
    case "TRACE_SPAN_EDGE_NOT_FOUND":
      return `Nenhuma aresta perpendicular ao eixo de ${measurement} foi encontrada em ${shapes}: reaponte a âncora do vão.`;
    case "TRACE_SPAN_SAME_BAND":
      return `As duas âncoras de ${measurement} caíram na mesma faixa do desenho (${shapes}): declare o par como mantido separado no eixo do problema.`;
    case "TRACE_TARGET_AS_DRAWN":
      return `${capitalise(shapes)} está aceita como desenhada; cota de elemento único não amarra em forma livre — trate a forma como retangular ou amarre ${measurement} a um vão.`;
    case "TRACE_SPAN_NOT_ORTHOGONAL":
      return `${capitalise(shapes)} não tem trecho ortogonal compatível com o eixo de ${measurement}: amarre a cota ao trecho ortogonal certo.`;
    case "TRACE_NOTE_ZERO_LENGTH":
      return `A nota de ${measurement} está ancorada num trecho de comprimento zero: reaponte a nota na folha.`;
    case "TRACE_NOTE_UNSUPPORTED_GEOMETRY":
      return `${capitalise(shapes)} não tem aresta que sustente a nota de ${measurement}: reaponte a nota para um elemento com aresta.`;
    default:
      return unapplied.cause;
  }
}

/**
 * Onde a cota aplicada ancorou, em metros da prancha. É o contrário do descarte: a frase
 * diz que a medida escrita pegou, e onde — o revisor confere o traçado contra a folha sem
 * abrir o DXF.
 */
export function traceAppliedAnchorsLabel(span: TraceAppliedSpan): string {
  const axis = span.axis === "x" ? "na horizontal" : "na vertical";
  const kind = span.gap ? ", como vão entre duas formas" : "";
  return `${formatDecimal(span.value_m, 2)} amarra ${formatDecimal(
    span.start_m,
    2,
  )} m → ${formatDecimal(span.end_m, 2)} m ${axis}${kind}.`;
}

/**
 * Duas ou mais cotas confirmadas prometendo distâncias diferentes para o mesmo vão. O
 * texto cru de cada leitura é o que o revisor procura na folha; leitura que saiu do
 * pacote entra pelo valor em metros que o traçado leu dela, nunca por um id opaco.
 */
export function traceContestedSpanLabel(
  contested: TraceContestedSpan,
  readings: Reading[],
): string {
  const axis =
    contested.axis === "x" ? "eixo X (horizontal)" : "eixo Y (vertical)";
  const parts = contested.reading_ids.map((readingId, index) => {
    const reading = readings.find((item) => item.id === readingId);
    if (reading) {
      return `"${reading.raw_text}"`;
    }
    const value = contested.values_m[index];
    return value === undefined
      ? "uma cota fora do pacote"
      : `${formatDecimal(value, 2)} m`;
  });
  if (parts.length === 0) {
    return `Duas cotas confirmadas disputam o mesmo vão no ${axis}.`;
  }
  const list =
    parts.length === 1
      ? parts[0]
      : `${parts.slice(0, -1).join(", ")} e ${parts[parts.length - 1]}`;
  return `${list} disputam o mesmo vão no ${axis}; os valores escritos não fecham entre si.`;
}

/**
 * Decimal do servidor exibido como foi escrito: só a pontuação muda.
 *
 * `formatDecimal` arredonda para um número fixo de casas, e é o que serve para medida
 * derivada de pixel. Aqui não serve: a folga de uma cadeia é `0,015 m` porque a cota
 * prometeu centímetro, e reescrevê-la com duas casas ("0,02") mudaria o que o servidor
 * conferiu. Resíduo pequeno arredondado para `0,00 m` chegaria a dizer que uma cadeia
 * que não fecha não tem diferença nenhuma.
 */
function chainDecimal(value: string): string {
  return value.trim().replace(".", ",");
}

/** Diferença em módulo: o sinal do resíduo é conta interna, não leitura de obra. */
function chainAbsolute(value: string): string {
  return chainDecimal(value).replace(/^[+-]/, "");
}

/** `Number("")` é zero, e zero aqui diria "fecha certinho" sobre um campo vazio. */
function chainNumber(value: string): number {
  const text = value.trim();
  return text === "" ? Number.NaN : Number(text);
}

/** A cadeia fecha quando o resíduo cabe na tolerância — a mesma regra do servidor. */
function chainCloses(chain: DimensionChain): boolean {
  const residual = chainNumber(chain.residual_m);
  const tolerance = chainNumber(chain.tolerance_m);
  if (Number.isNaN(residual) || Number.isNaN(tolerance)) {
    return false;
  }
  return Math.abs(residual) <= tolerance;
}

const CHAIN_STATUS_LABELS: Record<string, string> = {
  closes: "confere",
  mismatch: "não fecha",
  stale: "perdeu o pé",
};

/** Estado da cadeia por extenso: cor nunca é o único indicador do que ela está dizendo. */
export function chainStatusLabel(status: string): string {
  return CHAIN_STATUS_LABELS[status] ?? status;
}

/**
 * A conta como o revisor a confere na folha: as parcelas somadas contra o total.
 *
 * O sinal entre a soma e o total é `=` só quando a cadeia fecha; quando não fecha, `≠`,
 * porque escrever igualdade onde há diferença seria a tela afirmando o que o servidor
 * negou. A frase depois do `·` diz o mesmo em palavra — o símbolo sozinho não é aviso.
 *
 * `status` vem da cadeia declarada, que o servidor reconfere; sem ele (sugestão) a
 * comparação é feita aqui pela mesma regra.
 */
export function chainSumLabel(
  chain: DimensionChain,
  status?: "closes" | "mismatch",
): string {
  const closes = status ? status === "closes" : chainCloses(chain);
  const parts = chain.parts.map((term) => chainDecimal(term.value_m)).join(" + ");
  const total = chainDecimal(chain.total.value_m);
  if (closes) {
    return `${parts} = ${total} · confere (folga ${chainDecimal(
      chain.tolerance_m,
    )} m)`;
  }
  return `${parts} ≠ ${total} · não fecha (diferença de ${chainAbsolute(
    chain.residual_m,
  )} m)`;
}

/**
 * Leituras que participam de alguma soma que fecha — total e parcelas.
 *
 * É indício fraco de propósito: no croqui real, 3 das 4 somas que fecham são
 * coincidência aritmética. Serve para o revisor olhar antes, nunca para confirmar
 * leitura, liberar exportação ou dispensar a evidência. Cadeia que não fecha (e a que
 * perdeu o pé) não corrobora ninguém.
 */
export function chainCorroboratedReadingIds(chains: {
  suggested_chains?: DimensionChain[];
  declared_chains?: DeclaredChain[];
}): Set<string> {
  const ids = new Set<string>();
  const add = (chain: DimensionChain) => {
    ids.add(chain.total.reading_id);
    for (const part of chain.parts) {
      ids.add(part.reading_id);
    }
  };
  for (const chain of chains.suggested_chains ?? []) {
    if (chainCloses(chain)) {
      add(chain);
    }
  }
  for (const declared of chains.declared_chains ?? []) {
    if (declared.status === "closes" && declared.chain) {
      add(declared.chain);
    }
  }
  return ids;
}
