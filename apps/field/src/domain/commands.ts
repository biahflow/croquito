/**
 * Comandos do levantamento — funções puras `(survey, args, nowIso) => CommandResult`.
 *
 * Nenhum comando muta `survey`; todos devolvem um `Survey` novo (ou um erro estruturado
 * com código estável). `nowIso` vem de quem chama (não usam `Date.now()` internamente)
 * para permanecerem determinísticos e testáveis.
 */

import type {
  ArrivalContext,
  CommandResult,
  ElementObject,
  ElementObjectId,
  GpsFix,
  Measurement,
  MeasurementId,
  MeasurementKind,
  MeasurementStatus,
  ObservationNote,
  PhotoAnchor,
  PhotoAnchorId,
  Segment,
  SegmentId,
  Survey,
  SurveyPoint,
  SurveyPointId,
  Waiver,
  WaiverId,
} from "./types";
import { surveyStatus, surveyWaivers } from "./types";
import type { Finding } from "./validation";

function fail(code: string, message: string): CommandResult {
  return { ok: false, error: { code, message } };
}

function ok(
  survey: Survey,
  nowIso: string,
  type: string,
  payload: Record<string, unknown>,
): CommandResult {
  return {
    ok: true,
    survey: { ...survey, updated_at: nowIso },
    operation: { type, payload },
  };
}

function pointExists(survey: Survey, id: SurveyPointId): boolean {
  return survey.points.some((point) => point.id === id);
}

function elementExists(survey: Survey, id: ElementObjectId): boolean {
  return survey.elements.some((element) => element.id === id);
}

function measurementIndex(survey: Survey, id: MeasurementId): number {
  return survey.measurements.findIndex((measurement) => measurement.id === id);
}

/** Mesmo par de pontos, em qualquer ordem — usado para deduplicar segmentos e para
 * casar o par declarado de uma medida com um segmento existente. */
function samePair(
  aFrom: SurveyPointId,
  aTo: SurveyPointId,
  bFrom: SurveyPointId,
  bTo: SurveyPointId,
): boolean {
  return (aFrom === bFrom && aTo === bTo) || (aFrom === bTo && aTo === bFrom);
}

function segmentExistsForPair(survey: Survey, from: SurveyPointId, to: SurveyPointId): boolean {
  return survey.segments.some((segment) =>
    samePair(segment.from_point_id, segment.to_point_id, from, to),
  );
}

// ---------------------------------------------------------------------------------
// addPoint
// ---------------------------------------------------------------------------------

export interface AddPointArgs {
  id: SurveyPointId;
  x_mm: number;
  y_mm: number;
}

export function addPoint(survey: Survey, args: AddPointArgs, nowIso: string): CommandResult {
  if (!Number.isInteger(args.x_mm) || !Number.isInteger(args.y_mm)) {
    return fail("INVALID_MM", "As coordenadas do ponto precisam ser inteiras, em milímetros.");
  }
  const point: SurveyPoint = {
    id: args.id,
    x_mm: args.x_mm,
    y_mm: args.y_mm,
    created_at: nowIso,
  };
  const next: Survey = { ...survey, points: [...survey.points, point] };
  return ok(next, nowIso, "point.add", { point });
}

// ---------------------------------------------------------------------------------
// addSegment
// ---------------------------------------------------------------------------------

export interface AddSegmentArgs {
  id: SegmentId;
  from_point_id: SurveyPointId;
  to_point_id: SurveyPointId;
}

export function addSegment(survey: Survey, args: AddSegmentArgs, nowIso: string): CommandResult {
  if (!pointExists(survey, args.from_point_id) || !pointExists(survey, args.to_point_id)) {
    return fail("UNKNOWN_POINT", "O segmento referencia um ponto que não existe no levantamento.");
  }
  if (args.from_point_id === args.to_point_id) {
    return fail("DEGENERATE_SEGMENT", "Um segmento precisa ligar dois pontos distintos.");
  }
  if (segmentExistsForPair(survey, args.from_point_id, args.to_point_id)) {
    return fail("DUPLICATE_SEGMENT", "Já existe um segmento entre esses dois pontos.");
  }
  const segment: Segment = {
    id: args.id,
    from_point_id: args.from_point_id,
    to_point_id: args.to_point_id,
    created_at: nowIso,
  };
  const next: Survey = { ...survey, segments: [...survey.segments, segment] };
  return ok(next, nowIso, "segment.add", { segment });
}

// ---------------------------------------------------------------------------------
// closePerimeter
// ---------------------------------------------------------------------------------

export interface ClosePerimeterArgs {
  id: SegmentId;
}

export function closePerimeter(
  survey: Survey,
  args: ClosePerimeterArgs,
  nowIso: string,
): CommandResult {
  const degree = new Map<SurveyPointId, number>();
  for (const segment of survey.segments) {
    degree.set(segment.from_point_id, (degree.get(segment.from_point_id) ?? 0) + 1);
    degree.set(segment.to_point_id, (degree.get(segment.to_point_id) ?? 0) + 1);
  }
  if (degree.size < 3) {
    return fail(
      "PERIMETER_TOO_SMALL",
      "É preciso pelo menos três pontos usados em segmentos para fechar um perímetro.",
    );
  }
  const openEnds = [...degree.entries()].filter(([, count]) => count === 1).map(([id]) => id);
  if (openEnds.length !== 2) {
    return fail(
      "PERIMETER_AMBIGUOUS",
      `Não há exatamente duas pontas abertas para fechar (encontradas: ${openEnds.length}) — ` +
        "feche os ramos soltos ou ligue os pontos manualmente antes de tentar de novo.",
    );
  }
  const [from, to] = openEnds as [SurveyPointId, SurveyPointId];
  if (segmentExistsForPair(survey, from, to)) {
    // Acontece quando as duas pontas abertas são um segmento solto à parte de um anel já
    // fechado: fechar duplicaria esse segmento (o que addSegment proíbe) e quebraria a
    // premissa de grafo simples do hasCycle da validação.
    return fail(
      "PERIMETER_AMBIGUOUS",
      "As duas pontas abertas já estão ligadas entre si por um segmento solto — " +
        "ligue esse trecho ao restante do desenho antes de fechar o perímetro.",
    );
  }
  const segment: Segment = { id: args.id, from_point_id: from, to_point_id: to, created_at: nowIso };
  const next: Survey = { ...survey, segments: [...survey.segments, segment] };
  return ok(next, nowIso, "perimeter.close", { segment });
}

// ---------------------------------------------------------------------------------
// addElement
// ---------------------------------------------------------------------------------

export interface AddElementArgs {
  id: ElementObjectId;
  label: string;
  point_ids: SurveyPointId[];
}

export function addElement(survey: Survey, args: AddElementArgs, nowIso: string): CommandResult {
  if (args.point_ids.length === 0 || !args.point_ids.every((id) => pointExists(survey, id))) {
    return fail(
      "ELEMENT_WITHOUT_POINT",
      "Um elemento precisa de pelo menos um ponto existente no levantamento.",
    );
  }
  const element: ElementObject = {
    id: args.id,
    label: args.label,
    point_ids: args.point_ids,
    created_at: nowIso,
  };
  const next: Survey = { ...survey, elements: [...survey.elements, element] };
  return ok(next, nowIso, "element.add", { element });
}

// ---------------------------------------------------------------------------------
// addMeasurement
// ---------------------------------------------------------------------------------

export interface AddMeasurementArgs {
  id: MeasurementId;
  value_mm: number;
  kind: MeasurementKind;
  from_point_id?: SurveyPointId;
  to_point_id?: SurveyPointId;
  /** Par de pontos do segundo segmento — só relevante para `kind === "angle"`. */
  second_from_point_id?: SurveyPointId;
  second_to_point_id?: SurveyPointId;
  element_id?: ElementObjectId;
  instrument: string;
  status: MeasurementStatus;
}

function hasLinkedPointPair(
  survey: Survey,
  from: SurveyPointId | undefined,
  to: SurveyPointId | undefined,
): boolean {
  return (
    from !== undefined &&
    to !== undefined &&
    from !== to &&
    pointExists(survey, from) &&
    pointExists(survey, to)
  );
}

/** Confere o vínculo obrigatório por `kind`, conforme a tabela da Especificação §2 do
 * Task Contract T2. Devolve `true` quando o vínculo declarado é válido. */
function isLinked(survey: Survey, args: AddMeasurementArgs): boolean {
  switch (args.kind) {
    case "length":
    case "diagonal":
      return hasLinkedPointPair(survey, args.from_point_id, args.to_point_id);
    case "width":
    case "height":
    case "radius":
      return (
        (args.element_id !== undefined && elementExists(survey, args.element_id)) ||
        hasLinkedPointPair(survey, args.from_point_id, args.to_point_id)
      );
    case "level":
    case "drop":
      return (
        (args.from_point_id !== undefined && pointExists(survey, args.from_point_id)) ||
        (args.to_point_id !== undefined && pointExists(survey, args.to_point_id))
      );
    case "angle":
      return (
        args.from_point_id !== undefined &&
        args.to_point_id !== undefined &&
        args.second_from_point_id !== undefined &&
        args.second_to_point_id !== undefined &&
        segmentExistsForPair(survey, args.from_point_id, args.to_point_id) &&
        segmentExistsForPair(survey, args.second_from_point_id, args.second_to_point_id)
      );
    default:
      return false;
  }
}

export function addMeasurement(
  survey: Survey,
  args: AddMeasurementArgs,
  nowIso: string,
): CommandResult {
  // Código reaproveitado de addPoint: mesma família de regra ("mm inteiro"), o Task
  // Contract não nomeia um código próprio para "value_mm inteiro > 0" — ver BUILD REPORT.
  if (!Number.isInteger(args.value_mm) || args.value_mm <= 0) {
    return fail("INVALID_MM", "O valor da medida precisa ser um inteiro positivo, em milímetros.");
  }
  if (!isLinked(survey, args)) {
    return fail(
      "MEASUREMENT_UNLINKED",
      `Medida do tipo "${args.kind}" precisa do vínculo obrigatório (pontos ou elemento existentes) antes de ser registrada.`,
    );
  }
  const measurement: Measurement = {
    id: args.id,
    value_mm: args.value_mm,
    kind: args.kind,
    from_point_id: args.from_point_id,
    to_point_id: args.to_point_id,
    second_from_point_id: args.second_from_point_id,
    second_to_point_id: args.second_to_point_id,
    element_id: args.element_id,
    instrument: args.instrument,
    status: args.status,
    created_at: nowIso,
  };
  const next: Survey = { ...survey, measurements: [...survey.measurements, measurement] };
  return ok(next, nowIso, "measurement.add", { measurement });
}

// ---------------------------------------------------------------------------------
// addObservation
// ---------------------------------------------------------------------------------

export interface AddObservationArgs {
  id: string;
  text: string;
  point_id?: SurveyPointId;
  element_id?: ElementObjectId;
}

export function addObservation(
  survey: Survey,
  args: AddObservationArgs,
  nowIso: string,
): CommandResult {
  if (args.text.trim().length === 0) {
    return fail("EMPTY_TEXT", "O texto da observação não pode ficar vazio.");
  }
  const observation: ObservationNote = {
    id: args.id,
    text: args.text,
    point_id: args.point_id,
    element_id: args.element_id,
    created_at: nowIso,
  };
  const next: Survey = { ...survey, observations: [...survey.observations, observation] };
  return ok(next, nowIso, "observation.add", { observation });
}

// ---------------------------------------------------------------------------------
// justifyMeasurement
// ---------------------------------------------------------------------------------

export interface JustifyMeasurementArgs {
  measurement_id: MeasurementId;
  justification: string;
}

export function justifyMeasurement(
  survey: Survey,
  args: JustifyMeasurementArgs,
  nowIso: string,
): CommandResult {
  const index = measurementIndex(survey, args.measurement_id);
  if (index === -1) {
    return fail("UNKNOWN_MEASUREMENT", "A medida a justificar não existe neste levantamento.");
  }
  if (args.justification.trim().length === 0) {
    return fail("EMPTY_TEXT", "O motivo registrado não pode ficar vazio.");
  }
  const measurements = [...survey.measurements];
  measurements[index] = { ...measurements[index]!, justification: args.justification };
  const next: Survey = { ...survey, measurements };
  return ok(next, nowIso, "measurement.justify", {
    measurement_id: args.measurement_id,
    justification: args.justification,
  });
}

// ---------------------------------------------------------------------------------
// addPhotoAnchor
// ---------------------------------------------------------------------------------

export interface AddPhotoAnchorArgs {
  id: PhotoAnchorId;
  local_media_ref: string;
  point_id?: SurveyPointId;
  element_id?: ElementObjectId;
}

export function addPhotoAnchor(
  survey: Survey,
  args: AddPhotoAnchorArgs,
  nowIso: string,
): CommandResult {
  const linkedToPoint = args.point_id !== undefined && pointExists(survey, args.point_id);
  const linkedToElement = args.element_id !== undefined && elementExists(survey, args.element_id);
  if (!linkedToPoint && !linkedToElement) {
    return fail(
      "ANCHOR_UNLINKED",
      "Uma foto precisa estar ancorada a um ponto ou elemento existente no levantamento.",
    );
  }
  const anchor: PhotoAnchor = {
    id: args.id,
    point_id: args.point_id,
    element_id: args.element_id,
    local_media_ref: args.local_media_ref,
    created_at: nowIso,
  };
  const next: Survey = { ...survey, photo_anchors: [...survey.photo_anchors, anchor] };
  return ok(next, nowIso, "photo_anchor.add", { anchor });
}

// ---------------------------------------------------------------------------------
// recordArrival
// ---------------------------------------------------------------------------------

export interface RecordArrivalArgs {
  instrument: string;
  reference_note: string;
  gps?: GpsFix | "unavailable";
  /** `MediaRecord.id` da foto do acesso principal, já salva via `saveMedia` antes deste
   * comando (T6) — ver o comentário de `ArrivalContext.access_media_ref` em
   * `domain/types.ts` para a decisão de reusar este comando em vez de um novo. */
  access_media_ref?: string;
}

/**
 * Registra o contexto da chegada ao local (prancha 2 do Design Approval Package): uma
 * tarefa por survey, chamada antes de "Começar a coleta".
 *
 * GPS NUNCA bloqueia (Task Contract T4, Known Risks): `args.gps` é opcional e aceita
 * `"unavailable"` sem que este comando rejeite — só a referência física vazia falha. A
 * foto do acesso (T6) segue a mesma regra: `args.access_media_ref` é opcional, e sua
 * ausência não bloqueia a chegada — o item fica pendente no checklist
 * (`orders/state.ts`, `requiredItemsForOrder`), nunca um erro deste comando.
 */
export function recordArrival(
  survey: Survey,
  args: RecordArrivalArgs,
  nowIso: string,
): CommandResult {
  if (args.reference_note.trim().length === 0) {
    return fail("EMPTY_TEXT", "A referência física não pode ficar vazia.");
  }
  const context: ArrivalContext = {
    instrument: args.instrument,
    reference_note: args.reference_note,
    gps: args.gps,
    access_media_ref: args.access_media_ref,
    arrived_at: nowIso,
  };
  const next: Survey = { ...survey, context };
  return ok(next, nowIso, "arrival.record", { context });
}

// ---------------------------------------------------------------------------------
// waiveFinding
// ---------------------------------------------------------------------------------

export interface WaiveFindingArgs {
  id: WaiverId;
  finding_code: string;
  ref_key: string;
  justification: string;
}

/**
 * Registra a justificativa de uma pendência não crítica mantida na conclusão (prancha 5b
 * do Design Approval Package, Task Contract T5). NÃO valida `finding_code`/`ref_key`
 * contra os findings correntes do survey — eles mudam a cada comando, então o waiver
 * referencia código+ref por valor, não um finding vivo; por isso não existe
 * `UNKNOWN_FINDING_REF` (Task Contract T5, Scope).
 */
export function waiveFinding(
  survey: Survey,
  args: WaiveFindingArgs,
  nowIso: string,
): CommandResult {
  if (args.justification.trim().length === 0) {
    return fail("EMPTY_TEXT", "O motivo registrado não pode ficar vazio.");
  }
  const waiver: Waiver = {
    id: args.id,
    finding_code: args.finding_code,
    ref_key: args.ref_key,
    justification: args.justification,
    created_at: nowIso,
  };
  const next: Survey = { ...survey, waivers: [...surveyWaivers(survey), waiver] };
  return ok(next, nowIso, "finding.waive", { waiver });
}

// ---------------------------------------------------------------------------------
// concludeSurvey
// ---------------------------------------------------------------------------------

export interface ConcludeSurveyArgs {
  /** Findings do motor no momento da conclusão (Task Contract T5, Especificação §2) —
   * quem chama sempre passa o resultado mais recente de `validateSurvey`; este comando
   * não recalcula validação. */
  findings: Finding[];
}

export function concludeSurvey(
  survey: Survey,
  args: ConcludeSurveyArgs,
  nowIso: string,
): CommandResult {
  if (surveyStatus(survey) === "concluded") {
    return fail("ALREADY_CONCLUDED", "Este levantamento já foi concluído.");
  }
  if (args.findings.some((finding) => finding.severity === "critical")) {
    return fail(
      "CANNOT_CONCLUDE",
      "Não é possível concluir com itens críticos abertos — resolva-os antes.",
    );
  }
  const next: Survey = { ...survey, status: "concluded" };
  return ok(next, nowIso, "survey.conclude", {});
}

// ---------------------------------------------------------------------------------
// undoLast
// ---------------------------------------------------------------------------------

/**
 * Entrada da pilha de undo. Vive FORA do `Survey` (que precisa continuar serializável
 * sozinho — risco citado no Task Contract): quem aplica os comandos guarda essa pilha à
 * parte, empilhando o `Survey` anterior a cada comando bem-sucedido e desempilhando ao
 * chamar `undoLast`.
 */
export interface CommandHistoryEntry {
  /** id do comando que este entry desfaz (ex.: o `id` passado a `addPoint`). */
  command_id: string;
  /** Estado do survey imediatamente ANTES do comando ter sido aplicado. */
  previous_survey: Survey;
}

/**
 * Desfaz o último comando aplicado.
 *
 * Decisão de implementação (Task Contract pede a escolha documentada em comentário):
 * reconstrução, não inverso estrutural. `undoLast` não recalcula um "comando inverso"
 * por tipo de operação (o que exigiria um caso especial por comando, incluindo casos
 * sem inverso óbvio como `justifyMeasurement` sobrescrevendo uma justificativa antiga);
 * em vez disso, quem chama guarda o `Survey` de antes de cada comando em uma pilha
 * própria (`CommandHistoryEntry`, fora do domínio serializável) e `undoLast` apenas
 * devolve esse snapshot anterior verbatim, campo a campo — é o que garante a ida-e-volta
 * exata que o critério de aceite pede. `nowIso` não é usado para recalcular `updated_at`
 * porque restaurar o snapshot anterior EXATO (inclusive seu `updated_at` original) é o
 * que torna a reconstrução fiel.
 */
export function undoLast(
  survey: Survey,
  args: CommandHistoryEntry,
  nowIso: string,
): CommandResult {
  void survey;
  void nowIso;
  return {
    ok: true,
    survey: args.previous_survey,
    operation: { type: "command.undo", payload: { undone_command_id: args.command_id } },
  };
}
