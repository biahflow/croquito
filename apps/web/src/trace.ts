import type {
  Review,
  ReviewReading,
  TraceAssociationTarget,
  TraceResidualSummary,
  TraceSolveRequest,
  TraceSolveResponse,
  VisionProposal,
} from "./api";
import { formatDecimal, proposalDisplayName } from "./labels";

/**
 * Montagem do aceite em lote do traçado. A tela declara o que o profissional aceitou;
 * quem resolve a geometria é o solver, no worker. Este módulo é puro de propósito: a
 * pré-validação e as frases de acompanhamento precisam ser testáveis sem DOM e sem rede.
 *
 * A pré-validação aqui é UX, não segurança — o servidor revalida o aceite inteiro e
 * recusa o que estiver inconsistente.
 */

export type TraceDetailMode = "solve" | "sketch";

export type TraceDetailGroupDraft = {
  detailId: string;
  title: string;
  proposalIds: string[];
  mode: TraceDetailMode;
};

/** Amarração declarada de uma leitura confirmada a um alvo de vão. */
export type SpanTargetDraft =
  | { kind: "single"; proposalId: string }
  | { kind: "pair"; proposalIds: [string, string] }
  | {
      kind: "declared";
      proposalId: string;
      /** Pares de âncoras em pixel da imagem; cada par elege um trecho interno. */
      spansPx: [[number, number], [number, number]][];
    };

/** Cota que mede um trecho desenhado pelo valor da geometria resolvida, sem leitura de origem. */
export type DerivedDimensionDraft = {
  proposalId: string;
  nearXPx: number;
  nearYPx: number;
  text?: string;
};

/** Alvo de nota geral, fora de qualquer elemento: sobe acima do título da prancha. */
export const NOTE_TARGET_STAMP = "carimbo";
/** Prefixo do alvo de nota que vira sufixo da linha de legenda do elemento. */
export const NOTE_LEGEND_PREFIX = "legenda:";

/**
 * Par mantido separado com o eixo da separação, em espelho de `KeepApartPair` do
 * worker (`services/worker/src/croquito_worker/tracing.py`). `axis: null` é o
 * comportamento histórico: separa nos dois eixos.
 */
export type KeepApartDraft = {
  first: string;
  second: string;
  axis: "x" | "y" | null;
};

export type TraceDraft = {
  /** Formas aceitas, na ordem em que foram marcadas no desenho. */
  proposalIds: string[];
  /** Regiões que a folha marca como hachuradas; declaração humana, nunca inferência. */
  hatch: Set<string>;
  /** Elementos que dispensam balão e legenda na prancha. */
  unlabelled: Set<string>;
  /** Elementos declarados intencionalmente não-ortogonais: entram como desenhados. */
  freeform: Set<string>;
  /** Elementos desenhados coincidentes que o revisor declara distintos. */
  keepApartPairs: KeepApartDraft[];
  detailGroups: TraceDetailGroupDraft[];
  /** Vão declarado por leitura confirmada: elemento único, par de elementos ou trecho interno. */
  associations: Record<string, SpanTargetDraft>;
  /** Alvo de nota por leitura confirmada: elemento, elemento orientado, legenda ou carimbo. */
  noteTargets: Record<string, string>;
  /** Cotas derivadas da geometria resolvida, apresentadas sem leitura de origem. */
  derivedDimensions: DerivedDimensionDraft[];
  /** Texto declarado que substitui o valor numérico exibido na cota do vão. */
  dimensionTexts: Record<string, string>;
  note: string;
  title: string;
};

export function emptyTraceDraft(): TraceDraft {
  return {
    proposalIds: [],
    hatch: new Set(),
    unlabelled: new Set(),
    freeform: new Set(),
    keepApartPairs: [],
    detailGroups: [],
    associations: {},
    noteTargets: {},
    derivedDimensions: [],
    dimensionTexts: {},
    note: "",
    title: "",
  };
}

/** Mesmo padrão do contrato: uma letra maiúscula e até sete caracteres maiúsculos. */
export const DETAIL_ID_PATTERN = /^[A-Z][A-Z0-9]{0,7}$/;

const MAX_TITLE_LENGTH = 120;
/** Limite da nota do aceite; exportado porque a conversa também escreve nela. */
export const MAX_NOTE_LENGTH = 500;

/** Mantém a ordem do aceite nas listas auxiliares: payload estável entre montagens iguais. */
function inAcceptanceOrder(accepted: string[], marked: Set<string>): string[] {
  return accepted.filter((proposalId) => marked.has(proposalId));
}

/**
 * O corpo não carrega identidade nem relógio: `reviewer_id`, `reviewer_role`,
 * `decided_at` e `acceptance_id` vêm do JWT e do servidor. `base_scene_version` é
 * omitido quando o job ainda não tem cena — o traçado pode ser a primeira geometria
 * métrica do job, e mandar `null` seria declarar uma versão que não existe.
 */
export function buildTraceSolveRequest(
  draft: TraceDraft,
  review: Review,
): TraceSolveRequest {
  const accepted = [...draft.proposalIds];
  const request: TraceSolveRequest = {
    base_review_version: review.version,
    proposal_ids: accepted,
  };
  if (review.scene) {
    request.base_scene_version = review.scene.version;
  }
  const hatch = inAcceptanceOrder(accepted, draft.hatch);
  if (hatch.length > 0) {
    request.hatch_proposal_ids = hatch;
  }
  const unlabelled = inAcceptanceOrder(accepted, draft.unlabelled);
  if (unlabelled.length > 0) {
    request.unlabelled_proposal_ids = unlabelled;
  }
  const freeform = inAcceptanceOrder(accepted, draft.freeform);
  if (freeform.length > 0) {
    request.freeform_proposal_ids = freeform;
  }
  if (draft.keepApartPairs.length > 0) {
    // `axis: null` é o formato histórico do aceite (tupla, separa nos dois eixos); um
    // eixo declarado usa a forma objeto que o contrato aceita (api.ts KeepApartPair).
    request.keep_apart_pairs = draft.keepApartPairs.map((pair) =>
      pair.axis === null
        ? ([pair.first, pair.second] as [string, string])
        : { first: pair.first, second: pair.second, axis: pair.axis },
    );
  }
  if (draft.detailGroups.length > 0) {
    request.detail_groups = draft.detailGroups.map((group) => ({
      detail_id: group.detailId,
      title: group.title.trim(),
      proposal_ids: [...group.proposalIds],
      mode: group.mode,
    }));
  }
  const associationEntries = Object.entries(draft.associations);
  if (associationEntries.length > 0) {
    const associations: Record<string, TraceAssociationTarget> = {};
    for (const [readingId, target] of associationEntries) {
      switch (target.kind) {
        case "single":
          associations[readingId] = target.proposalId;
          break;
        case "pair":
          associations[readingId] = [...target.proposalIds];
          break;
        case "declared":
          associations[readingId] = {
            proposal_id: target.proposalId,
            spans_px: target.spansPx,
          };
          break;
      }
    }
    request.associations = associations;
  }
  const noteTargetEntries = Object.entries(draft.noteTargets);
  if (noteTargetEntries.length > 0) {
    request.note_associations = Object.fromEntries(noteTargetEntries);
  }
  if (draft.derivedDimensions.length > 0) {
    request.derived_dimensions = draft.derivedDimensions.map((dimension) => {
      const entry: {
        proposal_id: string;
        near_x_px: number;
        near_y_px: number;
        text?: string;
      } = {
        proposal_id: dimension.proposalId,
        near_x_px: dimension.nearXPx,
        near_y_px: dimension.nearYPx,
      };
      const text = dimension.text?.trim();
      if (text) {
        entry.text = text;
      }
      return entry;
    });
  }
  const dimensionTexts: Record<string, string> = {};
  for (const [readingId, text] of Object.entries(draft.dimensionTexts)) {
    const trimmed = text.trim();
    if (trimmed) {
      dimensionTexts[readingId] = trimmed;
    }
  }
  if (Object.keys(dimensionTexts).length > 0) {
    request.dimension_texts = dimensionTexts;
  }
  const note = draft.note.trim();
  if (note) {
    request.note = note;
  }
  const title = draft.title.trim();
  if (title) {
    request.title = title;
  }
  return request;
}

function capitalise(text: string): string {
  return text.charAt(0).toUpperCase() + text.slice(1);
}

function spanTargetProposalIds(target: SpanTargetDraft): string[] {
  switch (target.kind) {
    case "single":
      return [target.proposalId];
    case "pair":
      return [...target.proposalIds];
    case "declared":
      return [target.proposalId];
  }
}

type ParsedNoteTarget =
  | { kind: "stamp" }
  | { kind: "legend"; proposalId: string }
  | { kind: "plain"; proposalId: string; suffix: string | null };

/** Espelha `_note_target_proposals` do worker: `carimbo` não referencia forma, o
 * prefixo `legenda:` não recebe sufixo de orientação, e o `#` só existe no alvo direto. */
function parseNoteTarget(target: string): ParsedNoteTarget {
  if (target === NOTE_TARGET_STAMP) {
    return { kind: "stamp" };
  }
  if (target.startsWith(NOTE_LEGEND_PREFIX)) {
    return { kind: "legend", proposalId: target.slice(NOTE_LEGEND_PREFIX.length) };
  }
  const hashIndex = target.indexOf("#");
  if (hashIndex === -1) {
    return { kind: "plain", proposalId: target, suffix: null };
  }
  return {
    kind: "plain",
    proposalId: target.slice(0, hashIndex),
    suffix: target.slice(hashIndex + 1),
  };
}

function noteTargetProposalId(parsed: ParsedNoteTarget): string | null {
  return parsed.kind === "stamp" ? null : parsed.proposalId;
}

const MAX_DERIVED_DIMENSION_TEXT_LENGTH = 100;

function withinImage(
  x: number,
  y: number,
  widthPx: number | undefined,
  heightPx: number | undefined,
): boolean {
  if (widthPx === undefined || heightPx === undefined) {
    return true;
  }
  return x >= 0 && x <= widthPx && y >= 0 && y <= heightPx;
}

/**
 * Vão entre elementos e vão declarado precisam saber em que direção medem; vão de um
 * elemento único não precisa. A mensagem é a mesma que a lista agregada de pendências
 * mostra — o helper existe para a linha da própria cota poder acusar a falta no lugar
 * onde ela se resolve, sem duplicar o texto.
 */
export function spanAxisIssue(
  reading: ReviewReading | undefined,
  target: SpanTargetDraft,
): string | null {
  if (!reading || target.kind === "single") {
    return null;
  }
  if (reading.kind === "width" || reading.kind === "height") {
    return null;
  }
  return `A cota "${reading.raw_text}" foi confirmada sem eixo (largura/altura); o vão precisa saber em que direção mede.`;
}

/**
 * O que a montagem sabe sobre as cotas de uma forma: as amarrações herdadas da
 * associação observacional, as declaradas neste aceite e as leituras do pacote — só
 * leitura CONFIRMADA conta, porque cota ainda em dúvida não mede nada.
 */
export type ProposalFlagContext = {
  readings: ReviewReading[];
  selectedAssociations: Record<string, string>;
  associations: Record<string, SpanTargetDraft>;
};

/**
 * Declaração de partida de uma forma que ACABA de entrar no aceite. Forma sem nenhuma
 * cota confirmada amarrada não tem como ser regularizada por medida escrita: ela entra
 * "como desenhado", que é o que o croqui diz sobre ela. Com cota amarrada o padrão é o
 * contrário — a cota manda sobre o pixel e a forma é regularizada.
 *
 * Isto é ponto de partida, nunca decisão: a declaração continua escrita no chip da
 * lista ("como desenhado: sim") e o revisor a desfaz com um clique.
 */
export function defaultFlagsForProposal(
  proposalId: string,
  context: ProposalFlagContext,
): { freeform: boolean } {
  const confirmed = new Set(
    context.readings
      .filter((reading) => reading.status === "confirmed")
      .map((reading) => reading.id),
  );
  const inherited = Object.entries(context.selectedAssociations).some(
    ([readingId, target]) => target === proposalId && confirmed.has(readingId),
  );
  const declared = Object.entries(context.associations).some(
    ([readingId, target]) =>
      confirmed.has(readingId) &&
      spanTargetProposalIds(target).includes(proposalId),
  );
  return { freeform: !(inherited || declared) };
}

/**
 * Aplica os defaults às formas que acabaram de entrar na seleção. O que já estava na
 * montagem não é tocado: a declaração pode ter sido mexida pelo revisor, e sobrescrevê-la
 * por causa de um clique numa forma vizinha apagaria um ato humano. Marcar de novo uma
 * forma já marcada não duplica nada — a declaração é um conjunto.
 */
export function withDefaultProposalFlags(
  draft: TraceDraft,
  addedProposalIds: string[],
  context: ProposalFlagContext,
): TraceDraft {
  const freeform = addedProposalIds.filter(
    (proposalId) => defaultFlagsForProposal(proposalId, context).freeform,
  );
  if (freeform.length === 0) {
    return draft;
  }
  return { ...draft, freeform: new Set([...draft.freeform, ...freeform]) };
}

/**
 * Contexto opcional de `traceDraftIssues`: leituras do pacote, vãos herdados da
 * associação observacional e as dimensões da imagem-base. Sem contexto, as validações
 * que dependem dele simplesmente não rodam — retrocompatibilidade com as três
 * chamadas existentes.
 */
export type TraceDraftContext = {
  readings: ReviewReading[];
  selectedAssociations: Record<string, string>;
  imageWidthPx?: number;
  imageHeightPx?: number;
};

/**
 * Pendências da montagem, em língua de obra e sem identificador técnico: a mensagem
 * diz o que está errado e o que fazer, e a forma ofensora é citada pelo nome/balão que o
 * revisor reconhece na lista — uma issue por forma, nunca um booleano agregado. Uma
 * forma que saiu do próprio desenho (não só da seleção) ganha frase própria em vez de
 * um nome que não existe mais.
 *
 * A pré-validação é UX, não segurança — o servidor revalida o aceite inteiro e recusa
 * o que estiver inconsistente.
 */
export function traceDraftIssues(
  draft: TraceDraft,
  proposals: VisionProposal[],
  scaleMPerPx?: number | null,
  context?: TraceDraftContext,
): string[] {
  const nameOf = (proposalId: string): string => {
    const index = proposals.findIndex((p) => p.id === proposalId);
    return index >= 0
      ? `a forma "${proposalDisplayName(proposals[index], index + 1, scaleMPerPx ?? null)}"`
      : "uma forma que não está mais no desenho";
  };

  const issues: string[] = [];
  const accepted = new Set(draft.proposalIds);
  if (accepted.size === 0) {
    issues.push(
      "Selecione ao menos uma forma do desenho para aceitar o traçado.",
    );
  }
  const seen = new Set<string>();
  const duplicated = new Set<string>();
  for (const proposalId of draft.proposalIds) {
    if (seen.has(proposalId)) {
      duplicated.add(proposalId);
    }
    seen.add(proposalId);
  }
  for (const proposalId of duplicated) {
    issues.push(`${capitalise(nameOf(proposalId))} aparece mais de uma vez no aceite.`);
  }
  const outsideAcceptanceIds = (marked: Set<string>): string[] =>
    [...marked].filter((proposalId) => !accepted.has(proposalId));
  for (const proposalId of outsideAcceptanceIds(draft.hatch)) {
    issues.push(
      `${capitalise(nameOf(proposalId))} está marcada como hachura e saiu da seleção: marque-a de novo ou desfaça a hachura.`,
    );
  }
  for (const proposalId of outsideAcceptanceIds(draft.unlabelled)) {
    issues.push(
      `${capitalise(nameOf(proposalId))} está marcada como sem legenda e saiu da seleção: marque-a de novo ou desfaça a marcação.`,
    );
  }
  for (const proposalId of outsideAcceptanceIds(draft.freeform)) {
    issues.push(
      `${capitalise(nameOf(proposalId))} está marcada como desenhada e saiu da seleção: marque-a de novo ou desfaça a marcação.`,
    );
  }
  for (const { first, second } of draft.keepApartPairs) {
    if (first === second) {
      issues.push(
        `O par de manter separados aponta ${nameOf(first)} duas vezes; ele precisa de duas formas distintas.`,
      );
    }
  }
  for (const { first, second } of draft.keepApartPairs) {
    for (const proposalId of [first, second]) {
      if (!accepted.has(proposalId)) {
        issues.push(
          `O par de manter separados cita ${nameOf(proposalId)}, que saiu da seleção: marque-a de novo ou desfaça o par.`,
        );
      }
    }
  }
  const detailIds = draft.detailGroups.map((group) => group.detailId);
  if (detailIds.some((detailId) => !DETAIL_ID_PATTERN.test(detailId))) {
    issues.push(
      "O código do detalhe começa por letra maiúscula e tem até oito caracteres maiúsculos, como A ou B2.",
    );
  }
  if (new Set(detailIds).size !== detailIds.length) {
    issues.push("Dois grupos de detalhe estão com o mesmo código.");
  }
  if (draft.detailGroups.some((group) => group.title.trim().length === 0)) {
    issues.push("Todo grupo de detalhe precisa de um título.");
  }
  if (
    draft.detailGroups.some((group) => group.title.trim().length > MAX_TITLE_LENGTH)
  ) {
    issues.push(
      `O título do grupo de detalhe não pode passar de ${MAX_TITLE_LENGTH} caracteres.`,
    );
  }
  if (draft.detailGroups.some((group) => group.proposalIds.length === 0)) {
    issues.push("Todo grupo de detalhe precisa de ao menos uma forma.");
  }
  const grouped = new Set<string>();
  const repeatedAcrossGroups = new Set<string>();
  for (const group of draft.detailGroups) {
    for (const proposalId of group.proposalIds) {
      if (!accepted.has(proposalId)) {
        issues.push(
          `O grupo de detalhe ${group.detailId} cita ${nameOf(proposalId)}, que saiu da seleção: marque-a de novo ou desfaça o grupo.`,
        );
      }
      if (grouped.has(proposalId)) {
        repeatedAcrossGroups.add(proposalId);
      }
      grouped.add(proposalId);
    }
  }
  for (const proposalId of repeatedAcrossGroups) {
    issues.push(`${capitalise(nameOf(proposalId))} está em mais de um grupo de detalhe.`);
  }
  if (
    accepted.size > 0 &&
    grouped.size > 0 &&
    [...accepted].every((proposalId) => grouped.has(proposalId))
  ) {
    issues.push(
      "A planta principal ficaria vazia: deixe ao menos uma forma fora dos grupos de detalhe.",
    );
  }
  if (draft.title.trim().length > MAX_TITLE_LENGTH) {
    issues.push(
      `O título da prancha não pode passar de ${MAX_TITLE_LENGTH} caracteres.`,
    );
  }
  if (draft.note.trim().length > MAX_NOTE_LENGTH) {
    issues.push(
      `A nota do aceite não pode passar de ${MAX_NOTE_LENGTH} caracteres.`,
    );
  }

  const readingPhrase = (readingId: string): string => {
    const reading = context?.readings.find((r) => r.id === readingId);
    return reading
      ? `a cota "${reading.raw_text}"`
      : "uma cota que não está mais no pacote";
  };

  // Regra 1 — todo alvo de forma citado em vão, nota ou cota derivada precisa
  // continuar na seleção aceita.
  for (const target of Object.values(draft.associations)) {
    for (const proposalId of spanTargetProposalIds(target)) {
      if (!accepted.has(proposalId)) {
        issues.push(
          `${capitalise(nameOf(proposalId))} está amarrada como vão e saiu da seleção: marque-a de novo ou desfaça a amarração.`,
        );
      }
    }
  }
  for (const noteTarget of Object.values(draft.noteTargets)) {
    const proposalId = noteTargetProposalId(parseNoteTarget(noteTarget));
    if (proposalId !== null && !accepted.has(proposalId)) {
      issues.push(
        `${capitalise(nameOf(proposalId))} está amarrada como nota e saiu da seleção: marque-a de novo ou desfaça a amarração.`,
      );
    }
  }
  for (const dimension of draft.derivedDimensions) {
    if (!accepted.has(dimension.proposalId)) {
      issues.push(
        `${capitalise(nameOf(dimension.proposalId))} está amarrada como cota derivada e saiu da seleção: marque-a de novo ou desfaça a amarração.`,
      );
    }
  }

  // Regra 2 — vão entre dois elementos precisa apontar formas distintas.
  for (const [readingId, target] of Object.entries(draft.associations)) {
    if (target.kind === "pair" && target.proposalIds[0] === target.proposalIds[1]) {
      issues.push(
        `O vão declarado para ${readingPhrase(readingId)} aponta ${nameOf(target.proposalIds[0])} duas vezes; ele precisa de duas formas distintas.`,
      );
    }
  }

  // Regra 3 — vão declarado precisa de ao menos um trecho, e nenhum trecho pode ter
  // as duas âncoras no mesmo ponto.
  for (const [readingId, target] of Object.entries(draft.associations)) {
    if (target.kind !== "declared") {
      continue;
    }
    if (target.spansPx.length === 0) {
      issues.push(
        `${capitalise(readingPhrase(readingId))} está com vão declarado sem nenhum trecho: adicione ao menos um par de âncoras.`,
      );
    }
    for (const [start, end] of target.spansPx) {
      if (start[0] === end[0] && start[1] === end[1]) {
        issues.push(
          `${capitalise(readingPhrase(readingId))} tem um trecho cujas duas pontas apontam o mesmo ponto; marque duas âncoras distintas.`,
        );
      }
    }
  }

  // Regra 4 — sufixo de orientação de nota só admite v ou h.
  for (const [readingId, noteTarget] of Object.entries(draft.noteTargets)) {
    const parsed = parseNoteTarget(noteTarget);
    if (
      parsed.kind === "plain" &&
      parsed.suffix !== null &&
      parsed.suffix !== "v" &&
      parsed.suffix !== "h"
    ) {
      issues.push(
        `${capitalise(readingPhrase(readingId))} tem nota com orientação inválida: a orientação da nota é v (vertical) ou h (horizontal).`,
      );
    }
  }

  // Regra 5 — texto de cota declarado não pode ficar vazio.
  for (const [readingId, text] of Object.entries(draft.dimensionTexts)) {
    if (text.trim().length === 0) {
      issues.push(
        `O texto de ${readingPhrase(readingId)} está vazio; escreva a especificação ou remova o texto.`,
      );
    }
  }

  // Regra 6 — texto da cota derivada respeita o limite do contrato do worker.
  for (const dimension of draft.derivedDimensions) {
    if ((dimension.text ?? "").length > MAX_DERIVED_DIMENSION_TEXT_LENGTH) {
      issues.push(
        `${capitalise(nameOf(dimension.proposalId))} tem o texto da cota derivada maior que ${MAX_DERIVED_DIMENSION_TEXT_LENGTH} caracteres.`,
      );
    }
  }

  // Regra 7 — a mesma leitura não pode virar vão e nota ao mesmo tempo.
  for (const readingId of Object.keys(draft.associations)) {
    if (readingId in draft.noteTargets) {
      issues.push(
        `${capitalise(readingPhrase(readingId))} está amarrada como vão e como nota ao mesmo tempo; escolha um destino.`,
      );
    }
  }

  if (context) {
    const isConfirmed = (readingId: string): boolean =>
      context.readings.some((r) => r.id === readingId && r.status === "confirmed");

    // Regra 8 — leitura citada em vão, nota ou texto de cota precisa existir no
    // pacote e estar confirmada.
    const citedReadingIds = new Set<string>([
      ...Object.keys(draft.associations),
      ...Object.keys(draft.noteTargets),
      ...Object.keys(draft.dimensionTexts),
    ]);
    for (const readingId of citedReadingIds) {
      if (!isConfirmed(readingId)) {
        issues.push(
          `${capitalise(readingPhrase(readingId))} ainda não foi confirmada: decida a leitura antes de amarrar o vão/nota.`,
        );
      }
    }

    // Regra 9 — vão entre elementos e vão declarado exigem eixo confirmado
    // (largura/altura); vão de um elemento único não exige eixo.
    for (const [readingId, target] of Object.entries(draft.associations)) {
      const axisIssue = spanAxisIssue(
        context.readings.find((r) => r.id === readingId),
        target,
      );
      if (axisIssue) {
        issues.push(axisIssue);
      }
    }

    // Regra 10 — âncoras de vão declarado e ponto de cota derivada dentro dos
    // limites da imagem, quando as dimensões da imagem são conhecidas.
    for (const [readingId, target] of Object.entries(draft.associations)) {
      if (target.kind !== "declared") {
        continue;
      }
      const outside = target.spansPx.some(
        ([start, end]) =>
          !withinImage(start[0], start[1], context.imageWidthPx, context.imageHeightPx) ||
          !withinImage(end[0], end[1], context.imageWidthPx, context.imageHeightPx),
      );
      if (outside) {
        issues.push(
          `${capitalise(readingPhrase(readingId))} tem uma âncora fora da imagem; ajuste o ponto para dentro do desenho.`,
        );
      }
    }
    for (const dimension of draft.derivedDimensions) {
      if (
        !withinImage(dimension.nearXPx, dimension.nearYPx, context.imageWidthPx, context.imageHeightPx)
      ) {
        issues.push(
          `${capitalise(nameOf(dimension.proposalId))} tem a cota derivada com o ponto fora da imagem; ajuste o ponto para dentro do desenho.`,
        );
      }
    }

    // Regra 11 — texto de cota exige vão herdado da associação observacional ou
    // declarado neste aceite; espelha o blocker DIMENSION_TEXT_WITHOUT_SPAN do worker.
    for (const readingId of Object.keys(draft.dimensionTexts)) {
      const hasSpan =
        readingId in draft.associations || readingId in context.selectedAssociations;
      if (!hasSpan) {
        issues.push(
          `Texto de cota sem vão: amarre ${readingPhrase(readingId)} a um elemento antes de declarar o texto.`,
        );
      }
    }
  }

  return issues;
}

function plural(count: number, singular: string, many: string): string {
  return `${count} ${count === 1 ? singular : many}`;
}

/** Aceite em voo: já enviado e ainda não resolvido pelo worker. */
export function traceSolveInFlight(response: TraceSolveResponse | null): boolean {
  return response?.status === "QUEUED" || response?.status === "RUNNING";
}

/** Estado do aceite em uma frase; o resultado detalhado fica na própria seção. */
export function traceSolveStatusLabel(
  response: TraceSolveResponse | null,
): string {
  if (!response) {
    return "Nenhum aceite de traçado enviado.";
  }
  if (response.status === "QUEUED") {
    return "Aceite de traçado na fila.";
  }
  if (response.status === "RUNNING") {
    return "Resolvendo o traçado…";
  }
  if (response.status === "FAILED") {
    return `O traçado falhou (${response.failure_code ?? "causa não registrada"}).`;
  }
  switch (response.solve_status) {
    case "solved_unapproved":
      return `Traçado resolvido — ${plural(
        response.exact_entity_count ?? 0,
        "elemento exato",
        "elementos exatos",
      )} e ${plural(
        response.approximate_entity_count ?? 0,
        "aproximado",
        "aproximados",
      )}.`;
    case "review_required":
      return `O traçado precisa de revisão — ${plural(
        response.blockers.length,
        "pendência",
        "pendências",
      )}.`;
    case "conflict":
      return "Outra decisão entrou antes deste aceite; refaça o traçado sobre a versão nova.";
    default:
      return "Traçado concluído.";
  }
}

/**
 * O código de resíduo não carrega identificador de leitura ou forma — tipo mais eixo é
 * o máximo honesto que dá para nomear sem inventar. Código desconhecido cai numa
 * cláusula genérica em vez de mostrar o enum cru.
 */
const RESIDUAL_LOCATION_LABELS: Record<string, string> = {
  SPAN_RESIDUAL_X: "no trecho medido na horizontal",
  SPAN_RESIDUAL_Y: "no trecho medido na vertical",
  GAP_RESIDUAL_X: "no vão medido na horizontal",
  GAP_RESIDUAL_Y: "no vão medido na vertical",
  WIDTH_RESIDUAL: "na cota de largura",
  HEIGHT_RESIDUAL: "na cota de altura",
};

function residualLocationLabel(code: string): string {
  return RESIDUAL_LOCATION_LABELS[code] ?? "na pior cota conferida";
}

/**
 * Resumo em língua de obra de quanto as cotas confirmadas fecharam com a geometria
 * traçada. `null` ou nenhuma cota conferida não inventa frase. Quando alguma cota falha
 * a tolerância, o blocker `NUMERIC_RESIDUAL_EXCEEDS_TOLERANCE` já está na lista de
 * pendências — este resumo é factual, sem repetir o alarme.
 */
export function traceResidualSummaryLabel(
  summary: TraceResidualSummary | null,
): string | null {
  if (!summary || summary.count === 0) {
    return null;
  }
  const firstClause =
    summary.failed_count === 0
      ? `${plural(summary.count, "cota conferida", "cotas conferidas")} contra a geometria`
      : `${summary.failed_count} de ${summary.count} cotas não fecham com a geometria dentro da tolerância`;
  if (
    summary.worst_code === null ||
    summary.worst_absolute_error_m === null ||
    summary.worst_tolerance_m === null
  ) {
    return `${firstClause}.`;
  }
  const location = residualLocationLabel(summary.worst_code);
  const errorText = formatDecimal(summary.worst_absolute_error_m, 3);
  const toleranceText = formatDecimal(summary.worst_tolerance_m, 3);
  const worstClause =
    summary.failed_count === 0
      ? `a pior diferença foi ${errorText} m ${location}, dentro da tolerância de ${toleranceText} m`
      : `a pior diferença é de ${errorText} m ${location}, contra tolerância de ${toleranceText} m`;
  return `${firstClause}; ${worstClause}.`;
}
