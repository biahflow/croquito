import {
  emptyTraceDraft,
  type DerivedDimensionDraft,
  type KeepApartDraft,
  type SpanTargetDraft,
  type TraceDetailGroupDraft,
  type TraceDetailMode,
  type TraceDraft,
} from "./trace";

/**
 * Rascunho do aceite de traçado entre recargas da página.
 *
 * Amarrar as cotas de uma folha leva dezenas de cliques no desenho; perder isso num F5
 * é perder o trabalho, não a conveniência. O armazenamento é `sessionStorage`, pelo
 * mesmo motivo da declaração de aprovação: sobrevive ao reload, morre com a aba, e a
 * leitura do documento do cliente não fica no disco depois da sessão.
 *
 * Aqui só entra o que o revisor já declarou — `Set` vira lista, e nada é inventado na
 * volta. A captura em andamento não é persistida: gesto pela metade não é declaração.
 * Este módulo é puro para ser testável sem DOM; quem toca o storage é o App.
 */

const STORAGE_PREFIX = "croquitodxf:trace-draft:";

export function traceDraftStorageKey(jobId: string): string {
  return `${STORAGE_PREFIX}${jobId}`;
}

/** Rascunho restaurado: as declarações e as formas que continuam marcadas no lote. */
export type RestoredTraceDraft = {
  declarations: TraceDraft;
  batchIds: string[];
};

export function serializeTraceDraft(
  draft: TraceDraft,
  batchIds: ReadonlySet<string>,
): string {
  return JSON.stringify({
    batchIds: [...batchIds],
    proposalIds: draft.proposalIds,
    hatch: [...draft.hatch],
    unlabelled: [...draft.unlabelled],
    freeform: [...draft.freeform],
    keepApartPairs: draft.keepApartPairs,
    detailGroups: draft.detailGroups,
    associations: draft.associations,
    noteTargets: draft.noteTargets,
    derivedDimensions: draft.derivedDimensions,
    dimensionTexts: draft.dimensionTexts,
    note: draft.note,
    title: draft.title,
  });
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function stringList(value: unknown): string[] {
  return Array.isArray(value) && value.every((item) => typeof item === "string")
    ? [...(value as string[])]
    : [];
}

function stringMap(value: unknown): Record<string, string> {
  if (!isRecord(value)) {
    return {};
  }
  const result: Record<string, string> = {};
  for (const [key, item] of Object.entries(value)) {
    if (typeof item === "string") {
      result[key] = item;
    }
  }
  return result;
}

function isPoint(value: unknown): value is [number, number] {
  return (
    Array.isArray(value) &&
    value.length === 2 &&
    value.every((item) => typeof item === "number" && Number.isFinite(item))
  );
}

function isKeepApartAxis(value: unknown): value is "x" | "y" | null {
  return value === null || value === "x" || value === "y";
}

/**
 * Rascunhos antigos gravaram o par como tupla `[first, second]` (formato histórico,
 * separa nos dois eixos). Migra para `{first, second, axis: null}` no lugar. O formato
 * novo é validado campo a campo; eixo fora de `x`/`y`/`null` descarta só o par, não o
 * rascunho inteiro.
 */
function keepApartPairs(value: unknown): KeepApartDraft[] {
  if (!Array.isArray(value)) {
    return [];
  }
  const pairs: KeepApartDraft[] = [];
  for (const item of value) {
    if (
      Array.isArray(item) &&
      item.length === 2 &&
      item.every((entry) => typeof entry === "string")
    ) {
      const [first, second] = item as [string, string];
      pairs.push({ first, second, axis: null });
      continue;
    }
    if (
      isRecord(item) &&
      typeof item.first === "string" &&
      typeof item.second === "string" &&
      isKeepApartAxis(item.axis)
    ) {
      pairs.push({ first: item.first, second: item.second, axis: item.axis });
    }
  }
  return pairs;
}

function detailGroups(value: unknown): TraceDetailGroupDraft[] {
  if (!Array.isArray(value)) {
    return [];
  }
  const groups: TraceDetailGroupDraft[] = [];
  for (const item of value) {
    if (!isRecord(item)) {
      continue;
    }
    const mode = item.mode;
    if (
      typeof item.detailId !== "string" ||
      typeof item.title !== "string" ||
      (mode !== "solve" && mode !== "sketch")
    ) {
      continue;
    }
    groups.push({
      detailId: item.detailId,
      title: item.title,
      proposalIds: stringList(item.proposalIds),
      mode: mode as TraceDetailMode,
    });
  }
  return groups;
}

/**
 * Alvo de vão malformado é descartado inteiro em vez de restaurado pela metade: um
 * `kind` desconhecido atravessaria a pré-validação e só apareceria como erro do
 * servidor. Guardar menos é melhor do que guardar errado.
 */
function spanTarget(value: unknown): SpanTargetDraft | null {
  if (!isRecord(value)) {
    return null;
  }
  if (value.kind === "single" && typeof value.proposalId === "string") {
    return { kind: "single", proposalId: value.proposalId };
  }
  if (
    value.kind === "pair" &&
    Array.isArray(value.proposalIds) &&
    value.proposalIds.length === 2 &&
    value.proposalIds.every((item) => typeof item === "string")
  ) {
    const [first, second] = value.proposalIds as string[];
    return { kind: "pair", proposalIds: [first, second] };
  }
  if (
    value.kind === "declared" &&
    typeof value.proposalId === "string" &&
    Array.isArray(value.spansPx)
  ) {
    const spansPx = value.spansPx.filter(
      (span): span is [[number, number], [number, number]] =>
        Array.isArray(span) && span.length === 2 && span.every(isPoint),
    );
    return { kind: "declared", proposalId: value.proposalId, spansPx };
  }
  return null;
}

function associations(value: unknown): Record<string, SpanTargetDraft> {
  if (!isRecord(value)) {
    return {};
  }
  const result: Record<string, SpanTargetDraft> = {};
  for (const [readingId, item] of Object.entries(value)) {
    const target = spanTarget(item);
    if (target) {
      result[readingId] = target;
    }
  }
  return result;
}

function derivedDimensions(value: unknown): DerivedDimensionDraft[] {
  if (!Array.isArray(value)) {
    return [];
  }
  const dimensions: DerivedDimensionDraft[] = [];
  for (const item of value) {
    if (
      !isRecord(item) ||
      typeof item.proposalId !== "string" ||
      typeof item.nearXPx !== "number" ||
      typeof item.nearYPx !== "number" ||
      !Number.isFinite(item.nearXPx) ||
      !Number.isFinite(item.nearYPx)
    ) {
      continue;
    }
    const dimension: DerivedDimensionDraft = {
      proposalId: item.proposalId,
      nearXPx: item.nearXPx,
      nearYPx: item.nearYPx,
    };
    if (typeof item.text === "string") {
      dimension.text = item.text;
    }
    dimensions.push(dimension);
  }
  return dimensions;
}

function text(value: unknown): string {
  return typeof value === "string" ? value : "";
}

/**
 * Rascunho gravado de volta ao estado da tela.
 *
 * As formas marcadas são filtradas pelas que continuam SEM decisão: decisão registrada
 * é imutável e o lote só existe para o que ainda está pendente. As amarrações voltam
 * como estão — a pré-validação de `trace.ts` é quem acusa alvo que saiu do desenho, em
 * língua de obra, em vez de o rascunho sumir em silêncio.
 */
export function parseTraceDraft(
  raw: string,
  undecidedProposalIds: ReadonlySet<string>,
): RestoredTraceDraft | null {
  let parsed: unknown;
  try {
    parsed = JSON.parse(raw);
  } catch {
    return null;
  }
  if (!isRecord(parsed)) {
    return null;
  }
  const pending = (proposalId: string) => undecidedProposalIds.has(proposalId);
  return {
    declarations: {
      ...emptyTraceDraft(),
      proposalIds: stringList(parsed.proposalIds).filter(pending),
      hatch: new Set(stringList(parsed.hatch)),
      unlabelled: new Set(stringList(parsed.unlabelled)),
      freeform: new Set(stringList(parsed.freeform)),
      keepApartPairs: keepApartPairs(parsed.keepApartPairs),
      detailGroups: detailGroups(parsed.detailGroups),
      associations: associations(parsed.associations),
      noteTargets: stringMap(parsed.noteTargets),
      derivedDimensions: derivedDimensions(parsed.derivedDimensions),
      dimensionTexts: stringMap(parsed.dimensionTexts),
      note: text(parsed.note),
      title: text(parsed.title),
    },
    batchIds: stringList(parsed.batchIds).filter(pending),
  };
}
