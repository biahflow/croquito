/**
 * View-model da coleta — funções puras entre o motor de `src/domain` e o SVG/telas.
 *
 * Nada aqui recria regra de validação: as decorações do desenho vêm dos `Finding` que
 * `validateSurvey` devolveu, e as medidas exibidas vêm das `Measurement` declaradas. O
 * módulo só converte unidade, formata texto em português e organiza o que já foi
 * decidido pelo domínio.
 *
 * Não importa React nem Dexie (mesma disciplina de `src/domain`), por isso é testável em
 * ambiente node puro, sem DOM.
 */

import type { Measurement, Segment, Survey, SurveyPointId } from "../domain/types";
import type { Finding } from "../domain/validation";

/** Tolerância padrão desta fatia (50 mm), até a ordem de serviço trazer a sua (T4). */
export const DEFAULT_TOLERANCE_MM = 50;

/** Mundo do croqui, em mm. A proporção acompanha a área de desenho da prancha 3a
 * (358 × 470 ≈ 0,762); o toque é convertido para dentro desta janela. */
export const CANVAS_WIDTH_MM = 24_000;
export const CANVAS_HEIGHT_MM = 31_500;

export interface PixelPoint {
  /** px a partir da borda esquerda do elemento SVG. */
  x: number;
  /** px a partir da borda superior do elemento SVG. */
  y: number;
}

export interface PixelRect {
  width: number;
  height: number;
}

export interface WorldSize {
  widthMm: number;
  heightMm: number;
}

export interface MmPoint {
  x_mm: number;
  y_mm: number;
}

export const CANVAS_WORLD: WorldSize = {
  widthMm: CANVAS_WIDTH_MM,
  heightMm: CANVAS_HEIGHT_MM,
};

/**
 * Converte um toque (px relativos ao canto superior esquerdo do SVG) em mm INTEIROS do
 * croqui, respeitando o letterbox de `preserveAspectRatio="xMidYMid meet"`: o desenho é
 * escalado por `min(...)` e centrado, então as tarjas laterais não pertencem ao mundo.
 *
 * Devolve `null` para toque fora do desenho (tarja) ou para um retângulo degenerado —
 * quem chama simplesmente não emite comando, em vez de inventar um ponto na borda.
 */
export function touchToMm(
  touch: PixelPoint,
  rect: PixelRect,
  world: WorldSize = CANVAS_WORLD,
): MmPoint | null {
  if (rect.width <= 0 || rect.height <= 0) {
    return null;
  }
  const scale = Math.min(rect.width / world.widthMm, rect.height / world.heightMm);
  const offsetX = (rect.width - world.widthMm * scale) / 2;
  const offsetY = (rect.height - world.heightMm * scale) / 2;
  const xMm = (touch.x - offsetX) / scale;
  const yMm = (touch.y - offsetY) / scale;
  if (xMm < 0 || yMm < 0 || xMm > world.widthMm || yMm > world.heightMm) {
    return null;
  }
  return { x_mm: Math.round(xMm), y_mm: Math.round(yMm) };
}

// ---------------------------------------------------------------------------------
// metros com vírgula ↔ milímetros
// ---------------------------------------------------------------------------------

/** Metros com vírgula, até 3 casas (a resolução do mm). Ponto não é aceito: o teclado do
 * app tem vírgula, como a prancha 4a. */
const METERS_PATTERN = /^(\d{1,4})(?:,(\d{1,3}))?$/;

/**
 * "7,35" → 7350. Devolve `null` para entrada incompleta ou inválida ("", ",", "7,").
 *
 * Não valida domínio (valor positivo, vínculo obrigatório): isso é do comando
 * `addMeasurement`, e duplicar aqui produziria duas verdades sobre a mesma regra.
 */
export function metersInputToMm(input: string): number | null {
  const match = METERS_PATTERN.exec(input.trim());
  if (match === null) {
    return null;
  }
  const decimals = (match[2] ?? "").padEnd(3, "0");
  return Number(match[1]) * 1000 + Number(decimals);
}

/** 7350 → "7,35"; 12000 → "12,00"; 7355 → "7,355"; 5 → "0,005". Duas casas por padrão
 * (como as cotas da prancha 3a), três quando o milímetro não é zero. */
export function formatMmAsMeters(valueMm: number): string {
  const rounded = Math.round(valueMm);
  const sign = rounded < 0 ? "-" : "";
  const abs = Math.abs(rounded);
  const whole = Math.floor(abs / 1000);
  const rest = String(abs % 1000).padStart(3, "0");
  const decimals = rest.endsWith("0") ? rest.slice(0, 2) : rest;
  return `${sign}${whole},${decimals}`;
}

/** "15 cm" para 150 mm, "5 cm" para 50 mm, "8 mm" para 8, "1,20 m" a partir de 1 m — a
 * diferença por extenso da prancha 4b. */
export function formatDifference(valueMm: number): string {
  const abs = Math.abs(Math.round(valueMm));
  if (abs >= 1000) {
    return `${formatMmAsMeters(abs)} m`;
  }
  if (abs >= 10 && abs % 10 === 0) {
    return `${abs / 10} cm`;
  }
  return `${abs} mm`;
}

// ---------------------------------------------------------------------------------
// teclado numérico próprio (prancha 4a)
// ---------------------------------------------------------------------------------

const MAX_WHOLE_DIGITS = 4;
const MAX_DECIMAL_DIGITS = 3;

export function pressDigit(display: string, digit: string): string {
  if (!/^\d$/.test(digit)) {
    return display;
  }
  const commaIndex = display.indexOf(",");
  if (commaIndex === -1) {
    if (display === "0") {
      return digit;
    }
    return display.length >= MAX_WHOLE_DIGITS ? display : display + digit;
  }
  const decimals = display.slice(commaIndex + 1);
  return decimals.length >= MAX_DECIMAL_DIGITS ? display : display + digit;
}

export function pressComma(display: string): string {
  if (display.includes(",")) {
    return display;
  }
  return display === "" ? "0," : `${display},`;
}

export function pressBackspace(display: string): string {
  return display.slice(0, -1);
}

/**
 * A frase inteira do botão de confirmação (prancha 4a): o técnico confirma valor e
 * destino, não um "OK" solto. Sem medida digitada, o rótulo do botão desabilitado diz o
 * porquê — regra do pacote aprovado (5a).
 */
export function confirmMeasurementLabel(display: string, targetLabel: string): string {
  const valueMm = metersInputToMm(display);
  if (valueMm === null) {
    return `Confirmar (digite a medida de ${targetLabel})`;
  }
  return `Confirmar ${formatMmAsMeters(valueMm)} m para ${targetLabel}`;
}

// ---------------------------------------------------------------------------------
// rótulos estáveis (S1…, P1…)
// ---------------------------------------------------------------------------------

/** Rótulo por ordem de criação: o primeiro segmento é S1, o segundo S2 e assim por
 * diante. É rótulo de tela, nunca identidade — a identidade é o UUID. */
export function segmentLabels(segments: readonly Segment[]): Map<string, string> {
  return new Map(segments.map((segment, index) => [segment.id, `S${index + 1}`]));
}

export function pointLabels(points: readonly { id: string }[]): Map<string, string> {
  return new Map(points.map((point, index) => [point.id, `P${index + 1}`]));
}

// ---------------------------------------------------------------------------------
// decoração do desenho
// ---------------------------------------------------------------------------------

function pairKey(a: SurveyPointId, b: SurveyPointId): string {
  return [a, b].sort().join("::");
}

/** Medida de comprimento CONFIRMADA do par de pontos do segmento, se houver. Leitura de
 * dado declarado — não é revalidação. */
function confirmedLengthFor(survey: Survey, segment: Segment): Measurement | undefined {
  const key = pairKey(segment.from_point_id, segment.to_point_id);
  return survey.measurements.find(
    (measurement) =>
      measurement.kind === "length" &&
      measurement.status === "confirmed" &&
      measurement.from_point_id !== undefined &&
      measurement.to_point_id !== undefined &&
      pairKey(measurement.from_point_id, measurement.to_point_id) === key,
  );
}

export interface SegmentView {
  id: string;
  label: string;
  x1_mm: number;
  y1_mm: number;
  x2_mm: number;
  y2_mm: number;
  /** `true` quando o motor apontou `SEGMENT_WITHOUT_MEASUREMENT` para este segmento. */
  without_measurement: boolean;
  /** Texto desenhado junto do segmento — cota com "✓" ou o estado escrito por extenso. */
  label_text: string;
  measurement_mm: number | null;
}

/**
 * Traduz survey + findings do motor em segmentos desenháveis.
 *
 * O tracejado vermelho só existe porque `SEGMENT_WITHOUT_MEASUREMENT` apontou para o
 * segmento; a UI não decide isso por conta própria.
 */
export function buildSegmentViews(survey: Survey, findings: readonly Finding[]): SegmentView[] {
  const labels = segmentLabels(survey.segments);
  const withoutMeasurement = new Set(
    findings
      .filter((finding) => finding.code === "SEGMENT_WITHOUT_MEASUREMENT")
      .flatMap((finding) => finding.refs),
  );
  const pointById = new Map(survey.points.map((point) => [point.id, point]));

  const views: SegmentView[] = [];
  for (const segment of survey.segments) {
    const from = pointById.get(segment.from_point_id);
    const to = pointById.get(segment.to_point_id);
    if (from === undefined || to === undefined) {
      // Referência pendurada já vira `DANGLING_REFERENCE` na lista escrita de pendências;
      // aqui só não há o que desenhar.
      continue;
    }
    const label = labels.get(segment.id) ?? "S?";
    const measurement = confirmedLengthFor(survey, segment);
    const missing = withoutMeasurement.has(segment.id);
    views.push({
      id: segment.id,
      label,
      x1_mm: from.x_mm,
      y1_mm: from.y_mm,
      x2_mm: to.x_mm,
      y2_mm: to.y_mm,
      without_measurement: missing,
      measurement_mm: measurement?.value_mm ?? null,
      label_text: missing
        ? `${label} · sem medida`
        : measurement !== undefined
          ? `${formatMmAsMeters(measurement.value_mm)} m ✓`
          : label,
    });
  }
  return views;
}

export interface ElementView {
  id: string;
  label: string;
  x_mm: number;
  y_mm: number;
  width_mm: number;
  height_mm: number;
}

const ELEMENT_PADDING_MM = 400;
const ELEMENT_MIN_SIZE_MM = 1_600;

/** Área suave com rótulo em volta dos pontos do elemento (prancha 3a). */
export function buildElementViews(survey: Survey): ElementView[] {
  const pointById = new Map(survey.points.map((point) => [point.id, point]));
  const views: ElementView[] = [];
  for (const element of survey.elements) {
    const points = element.point_ids
      .map((id) => pointById.get(id))
      .filter((point): point is NonNullable<typeof point> => point !== undefined);
    if (points.length === 0) {
      continue;
    }
    const xs = points.map((point) => point.x_mm);
    const ys = points.map((point) => point.y_mm);
    const minX = Math.min(...xs) - ELEMENT_PADDING_MM;
    const minY = Math.min(...ys) - ELEMENT_PADDING_MM;
    views.push({
      id: element.id,
      label: element.label,
      x_mm: minX,
      y_mm: minY,
      width_mm: Math.max(Math.max(...xs) + ELEMENT_PADDING_MM - minX, ELEMENT_MIN_SIZE_MM),
      height_mm: Math.max(Math.max(...ys) + ELEMENT_PADDING_MM - minY, ELEMENT_MIN_SIZE_MM),
    });
  }
  return views;
}

export interface PhotoAnchorView {
  id: string;
  x_mm: number;
  y_mm: number;
}

/** Ícone de foto sobre o ponto ancorado (ou sobre o primeiro ponto do elemento). */
export function buildPhotoAnchorViews(survey: Survey): PhotoAnchorView[] {
  const pointById = new Map(survey.points.map((point) => [point.id, point]));
  const elementById = new Map(survey.elements.map((element) => [element.id, element]));
  const views: PhotoAnchorView[] = [];
  for (const anchor of survey.photo_anchors) {
    const direct = anchor.point_id === undefined ? undefined : pointById.get(anchor.point_id);
    const viaElement =
      anchor.element_id === undefined
        ? undefined
        : pointById.get(elementById.get(anchor.element_id)?.point_ids[0] ?? "");
    const point = direct ?? viaElement;
    if (point === undefined) {
      continue;
    }
    views.push({ id: anchor.id, x_mm: point.x_mm, y_mm: point.y_mm });
  }
  return views;
}

/** Centro dos pontos do croqui — usado para jogar a cota para o lado de FORA do desenho. */
export function pointsCentroid(survey: Survey): MmPoint {
  if (survey.points.length === 0) {
    return { x_mm: CANVAS_WIDTH_MM / 2, y_mm: CANVAS_HEIGHT_MM / 2 };
  }
  const sum = survey.points.reduce(
    (acc, point) => ({ x: acc.x + point.x_mm, y: acc.y + point.y_mm }),
    { x: 0, y: 0 },
  );
  return {
    x_mm: Math.round(sum.x / survey.points.length),
    y_mm: Math.round(sum.y / survey.points.length),
  };
}

/**
 * Posição do rótulo de um segmento: no meio dele, deslocado na perpendicular, do lado
 * oposto ao centro do desenho (a cota fica por fora, como na prancha 3a).
 */
export function segmentLabelPosition(
  segment: Pick<SegmentView, "x1_mm" | "y1_mm" | "x2_mm" | "y2_mm">,
  centroid: MmPoint,
  offsetMm: number,
): MmPoint {
  const midX = (segment.x1_mm + segment.x2_mm) / 2;
  const midY = (segment.y1_mm + segment.y2_mm) / 2;
  const dx = segment.x2_mm - segment.x1_mm;
  const dy = segment.y2_mm - segment.y1_mm;
  const length = Math.hypot(dx, dy);
  if (length === 0) {
    return { x_mm: Math.round(midX), y_mm: Math.round(midY - offsetMm) };
  }
  let normalX = -dy / length;
  let normalY = dx / length;
  // Do lado oposto ao centro: se a normal aponta para dentro, inverte.
  if ((midX - centroid.x_mm) * normalX + (midY - centroid.y_mm) * normalY < 0) {
    normalX = -normalX;
    normalY = -normalY;
  }
  return {
    x_mm: Math.round(midX + normalX * offsetMm),
    y_mm: Math.round(midY + normalY * offsetMm),
  };
}

/**
 * Ângulo (graus) em que o rótulo do segmento é escrito: ao longo dele, sempre legível da
 * esquerda para a direita — é o que a prancha 3a faz ao girar a cota do lado vertical em
 * 90°. Sem isso, o texto horizontal atravessa o traço nos segmentos verticais.
 */
export function segmentLabelRotation(
  segment: Pick<SegmentView, "x1_mm" | "y1_mm" | "x2_mm" | "y2_mm">,
): number {
  const dx = segment.x2_mm - segment.x1_mm;
  const dy = segment.y2_mm - segment.y1_mm;
  if (dx === 0 && dy === 0) {
    return 0;
  }
  const degrees = (Math.atan2(dy, dx) * 180) / Math.PI;
  if (degrees > 90) {
    return degrees - 180;
  }
  // `<= -90` e não `< -90`: o segmento vertical de baixo para cima daria -90, e a
  // prancha 3a escreve a cota vertical girada em +90.
  if (degrees <= -90) {
    return degrees + 180;
  }
  return degrees;
}

// ---------------------------------------------------------------------------------
// seleção de pontos (ligar dois pontos)
// ---------------------------------------------------------------------------------

export interface PointSelectionState {
  /** Primeiro ponto escolhido, realçado no desenho. */
  first: SurveyPointId | null;
  /** Par completo — quem chama emite `addSegment` e limpa a seleção. */
  pair: [SurveyPointId, SurveyPointId] | null;
}

/** Toque no mesmo ponto cancela a escolha; toque num segundo ponto fecha o par. */
export function selectPointForSegment(
  first: SurveyPointId | null,
  pointId: SurveyPointId,
): PointSelectionState {
  if (first === null) {
    return { first: pointId, pair: null };
  }
  if (first === pointId) {
    return { first: null, pair: null };
  }
  return { first: null, pair: [first, pointId] };
}

// ---------------------------------------------------------------------------------
// legenda e divergência
// ---------------------------------------------------------------------------------

export interface LegendChips {
  ok: string | null;
  error: string | null;
}

/** Os dois selos do canto do desenho (prancha 3a) — contagem sempre escrita. */
export function legendChips(survey: Survey, findings: readonly Finding[]): LegendChips {
  const confirmed = survey.measurements.filter(
    (measurement) => measurement.status === "confirmed",
  ).length;
  const missing = findings.filter(
    (finding) => finding.code === "SEGMENT_WITHOUT_MEASUREMENT",
  ).length;
  return {
    ok: confirmed === 0 ? null : `${confirmed} ${confirmed === 1 ? "medida" : "medidas"} ✓`,
    error:
      missing === 0
        ? null
        : `${missing} ${missing === 1 ? "segmento sem medida" : "segmentos sem medida"}`,
  };
}

/** A divergência que o motor apontou para esta medida, se ainda for crítica (uma vez
 * justificada, ela vira `warning` e não reabre a tela 4b). */
export function findCriticalDivergence(
  measurementId: string,
  findings: readonly Finding[],
): Finding | null {
  return (
    findings.find(
      (finding) =>
        finding.code === "MEASUREMENT_DIVERGENCE" &&
        finding.severity === "critical" &&
        finding.refs.includes(measurementId),
    ) ?? null
  );
}

export interface DivergenceReading {
  id: string;
  label: string;
  value_label: string;
}

export interface DivergenceView {
  readings: DivergenceReading[];
  difference_mm: number;
  message: string;
}

/** Monta a prancha 4b a partir das medidas referenciadas pelo finding — as duas leituras
 * ficam, nada é sobrescrito. */
export function buildDivergenceView(
  survey: Survey,
  finding: Finding,
  newestMeasurementId: string,
  toleranceMm: number,
): DivergenceView {
  const measurements = finding.refs
    .map((ref) => survey.measurements.find((measurement) => measurement.id === ref))
    .filter((measurement): measurement is Measurement => measurement !== undefined)
    .sort((a, b) => a.created_at.localeCompare(b.created_at));
  const values = measurements.map((measurement) => measurement.value_mm);
  const differenceMm = values.length === 0 ? 0 : Math.max(...values) - Math.min(...values);
  return {
    readings: measurements.map((measurement, index) => ({
      id: measurement.id,
      label: `${index + 1}ª medição${measurement.id === newestMeasurementId ? " (agora)" : ""}`,
      value_label: `${formatMmAsMeters(measurement.value_mm)} m`,
    })),
    difference_mm: differenceMm,
    message:
      `Diferença de ${formatDifference(differenceMm)} — acima da tolerância deste ` +
      `levantamento (${formatDifference(toleranceMm)}). Meça de novo ou registre o ` +
      "motivo; as duas leituras ficam no histórico.",
  };
}
