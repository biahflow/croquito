/**
 * Motor de validação — reproduz as regras geométricas da prancha 5 do Design Approval
 * Package (`docs/features/F-032-app-levantamento-campo/mock/README.md`).
 *
 * `x_mm`/`y_mm` são posição de CROQUITO (desenho), nunca métrica: nenhuma regra aqui lê
 * essas coordenadas. A verdade métrica são as `Measurement` declaradas — é o erro
 * conceitual central que este arquivo precisa evitar (Task Contract, Known Risks).
 */

import type { Measurement, Segment, Survey, SurveyPointId } from "./types";

export type FindingSeverity = "critical" | "warning";

export interface Finding {
  code: string;
  severity: FindingSeverity;
  /** Mensagem em português, escrita como na prancha 5 do Design Approval Package
   * (estado sempre escrito, nunca só cor). */
  message: string;
  refs: string[];
}

export interface RequiredItem {
  id: string;
  label: string;
  satisfied: boolean;
}

export interface ValidateSurveyOptions {
  toleranceMm: number;
  requiredItems?: RequiredItem[];
}

export interface SurveySummary {
  /** Medidas com `status === "confirmed"`. */
  confirmed_measurements: number;
  segments: number;
  critical_count: number;
  warning_count: number;
}

function pairKey(a: SurveyPointId, b: SurveyPointId): string {
  return [a, b].sort().join("::");
}

/** Chave de vínculo de uma medida — mesmo par/elemento e `kind` conta como o "mesmo
 * vínculo" para efeito de `MEASUREMENT_DIVERGENCE` (duas medidas do mesmo vínculo). */
function linkKey(measurement: Measurement): string | undefined {
  if (measurement.element_id !== undefined) {
    return `element:${measurement.element_id}:${measurement.kind}`;
  }
  if (measurement.from_point_id !== undefined && measurement.to_point_id !== undefined) {
    return `pair:${pairKey(measurement.from_point_id, measurement.to_point_id)}:${measurement.kind}`;
  }
  if (measurement.from_point_id !== undefined) {
    return `point:${measurement.from_point_id}:${measurement.kind}`;
  }
  if (measurement.to_point_id !== undefined) {
    return `point:${measurement.to_point_id}:${measurement.kind}`;
  }
  return undefined;
}

function degreeByPoint(segments: Segment[]): Map<SurveyPointId, number> {
  const degree = new Map<SurveyPointId, number>();
  for (const segment of segments) {
    degree.set(segment.from_point_id, (degree.get(segment.from_point_id) ?? 0) + 1);
    degree.set(segment.to_point_id, (degree.get(segment.to_point_id) ?? 0) + 1);
  }
  return degree;
}

/** Um componente conexo do grafo de segmentos tem ciclo sse #arestas >= #nós (grafo
 * simples, sem segmento duplicado — `addSegment` já impede duplicata). */
function hasCycle(segments: Segment[]): boolean {
  if (segments.length === 0) {
    return false;
  }
  const parent = new Map<SurveyPointId, SurveyPointId>();
  const find = (id: SurveyPointId): SurveyPointId => {
    let root = id;
    while (parent.get(root) !== undefined && parent.get(root) !== root) {
      root = parent.get(root)!;
    }
    return root;
  };
  const nodes = new Set<SurveyPointId>();
  for (const segment of segments) {
    nodes.add(segment.from_point_id);
    nodes.add(segment.to_point_id);
  }
  for (const node of nodes) {
    parent.set(node, node);
  }
  const edgeCountByComponent = new Map<SurveyPointId, number>();
  for (const segment of segments) {
    const rootFrom = find(segment.from_point_id);
    const rootTo = find(segment.to_point_id);
    const componentRoot = rootFrom < rootTo ? rootFrom : rootTo;
    if (rootFrom !== rootTo) {
      parent.set(rootFrom, componentRoot);
      parent.set(rootTo, componentRoot);
    }
  }
  for (const segment of segments) {
    const root = find(segment.from_point_id);
    edgeCountByComponent.set(root, (edgeCountByComponent.get(root) ?? 0) + 1);
  }
  const nodeCountByComponent = new Map<SurveyPointId, number>();
  for (const node of nodes) {
    const root = find(node);
    nodeCountByComponent.set(root, (nodeCountByComponent.get(root) ?? 0) + 1);
  }
  for (const [root, edgeCount] of edgeCountByComponent) {
    if (edgeCount >= (nodeCountByComponent.get(root) ?? 0)) {
      return true;
    }
  }
  return false;
}

function checkOpenPerimeter(survey: Survey): Finding[] {
  const degree = degreeByPoint(survey.segments);
  const openEnds = [...degree.entries()].filter(([, count]) => count === 1).map(([id]) => id);
  if (openEnds.length === 0 && hasCycle(survey.segments)) {
    return [];
  }
  return [
    {
      code: "OPEN_PERIMETER",
      severity: "critical",
      message:
        openEnds.length > 0
          ? "Perímetro aberto: há ponta solta em pelo menos um ponto."
          : "Perímetro aberto: os segmentos declarados não fecham um ciclo.",
      refs: openEnds,
    },
  ];
}

function checkSegmentWithoutMeasurement(survey: Survey): Finding[] {
  const findings: Finding[] = [];
  for (const segment of survey.segments) {
    const hasConfirmedLength = survey.measurements.some(
      (measurement) =>
        measurement.kind === "length" &&
        measurement.status === "confirmed" &&
        measurement.from_point_id !== undefined &&
        measurement.to_point_id !== undefined &&
        pairKey(measurement.from_point_id, measurement.to_point_id) ===
          pairKey(segment.from_point_id, segment.to_point_id),
    );
    if (!hasConfirmedLength) {
      findings.push({
        code: "SEGMENT_WITHOUT_MEASUREMENT",
        severity: "critical",
        message: "Segmento sem medida de comprimento confirmada entre os pontos ligados.",
        refs: [segment.id],
      });
    }
  }
  return findings;
}

function checkTriangleMismatch(survey: Survey, toleranceMm: number): Finding[] {
  const distanceByPair = new Map<string, { value_mm: number; a: SurveyPointId; b: SurveyPointId }>();
  for (const measurement of survey.measurements) {
    if (
      (measurement.kind !== "length" && measurement.kind !== "diagonal") ||
      measurement.status !== "confirmed" ||
      measurement.from_point_id === undefined ||
      measurement.to_point_id === undefined
    ) {
      continue;
    }
    const key = pairKey(measurement.from_point_id, measurement.to_point_id);
    // Primeira medida confirmada do par vence — divergência entre duas medidas do mesmo
    // vínculo é responsabilidade de MEASUREMENT_DIVERGENCE, não desta regra.
    if (!distanceByPair.has(key)) {
      distanceByPair.set(key, {
        value_mm: measurement.value_mm,
        a: measurement.from_point_id,
        b: measurement.to_point_id,
      });
    }
  }
  const pointIds = [...new Set([...distanceByPair.values()].flatMap((d) => [d.a, d.b]))];
  const findings: Finding[] = [];
  const seenTriangles = new Set<string>();
  for (let i = 0; i < pointIds.length; i += 1) {
    for (let j = i + 1; j < pointIds.length; j += 1) {
      for (let k = j + 1; k < pointIds.length; k += 1) {
        const [a, b, c] = [pointIds[i]!, pointIds[j]!, pointIds[k]!];
        const ab = distanceByPair.get(pairKey(a, b));
        const bc = distanceByPair.get(pairKey(b, c));
        const ac = distanceByPair.get(pairKey(a, c));
        if (!ab || !bc || !ac) {
          continue;
        }
        const triangleKey = [a, b, c].sort().join("::");
        if (seenTriangles.has(triangleKey)) {
          continue;
        }
        seenTriangles.add(triangleKey);
        const sides = [ab.value_mm, bc.value_mm, ac.value_mm];
        const violates = sides.some((side, index) => {
          const others = sides.filter((_, otherIndex) => otherIndex !== index);
          const sumOthers = others[0]! + others[1]!;
          return sumOthers + toleranceMm < side;
        });
        if (violates) {
          findings.push({
            code: "TRIANGLE_MISMATCH",
            severity: "critical",
            message:
              "Diagonal incompatível com os lados declarados: a desigualdade triangular falha além da tolerância.",
            refs: [a, b, c],
          });
        }
      }
    }
  }
  return findings;
}

function checkMeasurementDivergence(survey: Survey, toleranceMm: number): Finding[] {
  const byLink = new Map<string, Measurement[]>();
  for (const measurement of survey.measurements) {
    if (measurement.status !== "confirmed") {
      continue;
    }
    const key = linkKey(measurement);
    if (key === undefined) {
      continue;
    }
    const group = byLink.get(key) ?? [];
    group.push(measurement);
    byLink.set(key, group);
  }
  const findings: Finding[] = [];
  for (const group of byLink.values()) {
    if (group.length < 2) {
      continue;
    }
    const values = group.map((m) => m.value_mm);
    const diff = Math.max(...values) - Math.min(...values);
    if (diff <= toleranceMm) {
      continue;
    }
    const justified = group.some((m) => (m.justification ?? "").trim().length > 0);
    findings.push({
      code: "MEASUREMENT_DIVERGENCE",
      severity: justified ? "warning" : "critical",
      message: justified
        ? "Divergência entre medidas confirmadas do mesmo vínculo, mantida com motivo registrado."
        : "Divergência entre duas medidas confirmadas do mesmo vínculo, acima da tolerância.",
      refs: group.map((m) => m.id),
    });
  }
  return findings;
}

function checkDanglingReferences(survey: Survey): Finding[] {
  const findings: Finding[] = [];
  const pointIds = new Set(survey.points.map((p) => p.id));
  const elementIds = new Set(survey.elements.map((e) => e.id));

  for (const segment of survey.segments) {
    for (const pointId of [segment.from_point_id, segment.to_point_id]) {
      if (!pointIds.has(pointId)) {
        findings.push({
          code: "DANGLING_REFERENCE",
          severity: "critical",
          message: `Segmento referencia um ponto inexistente (${pointId}).`,
          refs: [segment.id, pointId],
        });
      }
    }
  }
  for (const measurement of survey.measurements) {
    const refs: Array<[string | undefined, "point" | "element"]> = [
      [measurement.from_point_id, "point"],
      [measurement.to_point_id, "point"],
      [measurement.second_from_point_id, "point"],
      [measurement.second_to_point_id, "point"],
      [measurement.element_id, "element"],
    ];
    for (const [id, kind] of refs) {
      if (id === undefined) {
        continue;
      }
      const exists = kind === "point" ? pointIds.has(id) : elementIds.has(id);
      if (!exists) {
        findings.push({
          code: "DANGLING_REFERENCE",
          severity: "critical",
          message: `Medida referencia um ${kind === "point" ? "ponto" : "elemento"} inexistente (${id}).`,
          refs: [measurement.id, id],
        });
      }
    }
  }
  for (const anchor of survey.photo_anchors) {
    if (anchor.point_id !== undefined && !pointIds.has(anchor.point_id)) {
      findings.push({
        code: "DANGLING_REFERENCE",
        severity: "critical",
        message: `Âncora de foto referencia um ponto inexistente (${anchor.point_id}).`,
        refs: [anchor.id, anchor.point_id],
      });
    }
    if (anchor.element_id !== undefined && !elementIds.has(anchor.element_id)) {
      findings.push({
        code: "DANGLING_REFERENCE",
        severity: "critical",
        message: `Âncora de foto referencia um elemento inexistente (${anchor.element_id}).`,
        refs: [anchor.id, anchor.element_id],
      });
    }
  }
  for (const element of survey.elements) {
    for (const pointId of element.point_ids) {
      if (!pointIds.has(pointId)) {
        findings.push({
          code: "DANGLING_REFERENCE",
          severity: "critical",
          message: `Elemento referencia um ponto inexistente (${pointId}).`,
          refs: [element.id, pointId],
        });
      }
    }
  }
  return findings;
}

function checkRequiredItemsPending(requiredItems: RequiredItem[]): Finding[] {
  return requiredItems
    .filter((item) => !item.satisfied)
    .map((item) => ({
      code: "REQUIRED_ITEM_PENDING",
      severity: "warning" as const,
      message: `Item obrigatório pendente: ${item.label}.`,
      refs: [item.id],
    }));
}

function checkElementWithoutPhoto(survey: Survey): Finding[] {
  const findings: Finding[] = [];
  for (const element of survey.elements) {
    const elementPointIds = new Set<SurveyPointId>(element.point_ids);
    const hasPhoto = survey.photo_anchors.some(
      (anchor) =>
        anchor.element_id === element.id ||
        (anchor.point_id !== undefined && elementPointIds.has(anchor.point_id)),
    );
    if (!hasPhoto) {
      findings.push({
        code: "ELEMENT_WITHOUT_PHOTO",
        severity: "warning",
        message: `Elemento "${element.label}" sem foto ancorada.`,
        refs: [element.id],
      });
    }
  }
  return findings;
}

export function validateSurvey(survey: Survey, opts: ValidateSurveyOptions): Finding[] {
  return [
    ...checkOpenPerimeter(survey),
    ...checkSegmentWithoutMeasurement(survey),
    ...checkTriangleMismatch(survey, opts.toleranceMm),
    ...checkMeasurementDivergence(survey, opts.toleranceMm),
    ...checkDanglingReferences(survey),
    ...checkRequiredItemsPending(opts.requiredItems ?? []),
    ...checkElementWithoutPhoto(survey),
  ];
}

export function summarize(survey: Survey, findings: Finding[]): SurveySummary {
  return {
    confirmed_measurements: survey.measurements.filter((m) => m.status === "confirmed").length,
    segments: survey.segments.length,
    critical_count: findings.filter((f) => f.severity === "critical").length,
    warning_count: findings.filter((f) => f.severity === "warning").length,
  };
}

export function canConclude(findings: Finding[]): boolean {
  return findings.every((finding) => finding.severity !== "critical");
}
