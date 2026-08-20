import type { Review, ReviewReading, TraceSolveResponse } from "./api";
import {
  proposalDisplayName,
  traceContestedSpanLabel,
  traceUnappliedCauseLabel,
} from "./labels";
import type { TraceDraft } from "./trace";

/**
 * Consultor do traçado: o que o resultado diagnosticou, dito em língua de obra, com os
 * consertos que cabem em um clique.
 *
 * É o espelho SEM IA dos rascunhos da conversa (`applyDraftToTraceDraft`, chat.ts): um
 * produtor determinístico de atos que o revisor assina, nunca um executor. Nenhum
 * conserto envia nada e nenhum conserto marca forma na seleção — marcar é ato do revisor
 * no desenho, exatamente como no precedente da conversa.
 *
 * Módulo puro, testável sem DOM: quem decide o que vira botão é esta regra, e não a
 * marcação visual da tela.
 */

export type AdvisorFix =
  /** Tira a forma de "como desenhado" para a cota de elemento único poder amarrá-la. */
  | { kind: "treat_rectangular"; proposalId: string }
  /** Troca o alvo da cota no rascunho do aceite por um candidato alternativo. */
  | { kind: "reassociate"; readingId: string; proposalId: string; label: string }
  /** Abre a leitura onde o eixo (largura/altura) é declarado. */
  | { kind: "declare_axis"; readingId: string }
  /** Declara duas formas coincidentes como distintas no aceite. */
  | { kind: "keep_apart"; first: string; second: string }
  /** Abre a correção da leitura com os valores vigentes pré-preenchidos. */
  | { kind: "rectify"; readingId: string };

export type AdvisorFinding = {
  /** Ausente no vão em disputa: o achado é do par, não de uma leitura só. */
  readingId?: string;
  /** Frase em língua de obra, montada por `labels.ts`. */
  message: string;
  /** Código cru exibido ao lado da frase; esconder o diagnóstico é pior do que o cru. */
  rawCode: string;
  fixes: AdvisorFix[];
};

/**
 * Diagnóstico do vão em disputa não tem código de causa no contrato — ele é uma lista
 * própria da resposta. O código cru exibido nomeia essa lista, em vez de inventar um
 * `cause` que o servidor nunca emite.
 */
export const CONTESTED_SPAN_CODE = "contested_spans";

/** Teto de alternativas oferecidas por leitura: a lista já vem ranqueada pelo servidor. */
const MAX_ALTERNATIVES = 3;

/**
 * Leitura elegível a conserto: existe NESTA revisão e continua confirmada. Leitura
 * decidida de outro modo depois do aceite (rejeitada, reaberta, retificada para outro
 * desfecho) não recebe botão — o conserto seria escrito sobre um estado que não é mais o
 * da tela. Mesma proteção do lote de leituras (`readingBatch.ts`).
 */
function eligibleReading(
  review: Review,
  readingId: string,
): ReviewReading | undefined {
  const reading = review.packet.readings.find((item) => item.id === readingId);
  return reading?.status === "confirmed" ? reading : undefined;
}

/** Correção só existe sobre decisão gravada: sem alvo declarado não há o que retificar. */
function rectifiable(reading: ReviewReading | undefined): boolean {
  return Boolean(reading?.decision);
}

function shapeLabel(review: Review, proposalId: string): string {
  const proposals = review.proposals?.proposals ?? [];
  const index = proposals.findIndex((item) => item.id === proposalId);
  return index >= 0
    ? proposalDisplayName(
        proposals[index],
        index + 1,
        review.calibration?.scale_m_per_px ?? null,
      )
    : proposalId;
}

/**
 * Alternativas de amarração para a leitura: candidatos observacionais da revisão, na
 * ordem em que o servidor os ranqueou, sem o alvo que o traçado já tentou e sem forma
 * fora do aceite — amarrar a uma forma não selecionada só trocaria um descarte por um
 * bloqueio.
 */
function alternativeFixes(
  review: Review,
  draft: TraceDraft,
  readingId: string,
  currentTargets: string[],
): AdvisorFix[] {
  const accepted = new Set(draft.proposalIds);
  const excluded = new Set(currentTargets);
  const seen = new Set<string>();
  const fixes: AdvisorFix[] = [];
  for (const candidate of review.associations.candidates) {
    if (candidate.reading_id !== readingId) {
      continue;
    }
    if (excluded.has(candidate.proposal_id) || seen.has(candidate.proposal_id)) {
      continue;
    }
    if (!accepted.has(candidate.proposal_id)) {
      continue;
    }
    seen.add(candidate.proposal_id);
    fixes.push({
      kind: "reassociate",
      readingId,
      proposalId: candidate.proposal_id,
      label: shapeLabel(review, candidate.proposal_id),
    });
    if (fixes.length === MAX_ALTERNATIVES) {
      break;
    }
  }
  return fixes;
}

function keepApartDeclared(draft: TraceDraft, first: string, second: string): boolean {
  return draft.keepApartPairs.some(
    (pair) =>
      (pair.first === first && pair.second === second) ||
      (pair.first === second && pair.second === first),
  );
}

/** Causas cujo conserto é reapontar o alvo da cota; nota tem controle próprio. */
const REASSOCIABLE_CAUSES = new Set([
  "TRACE_SPAN_EDGE_NOT_FOUND",
  "TRACE_SPAN_SAME_BAND",
  "TRACE_SPAN_NOT_ORTHOGONAL",
]);

function unappliedFixes(
  cause: string,
  targets: string[],
  readingId: string,
  review: Review,
  draft: TraceDraft,
): AdvisorFix[] {
  const reading = eligibleReading(review, readingId);
  if (!reading) {
    return [];
  }
  if (cause === "TRACE_TARGET_AS_DRAWN") {
    // A forma precisa continuar no aceite E declarada como desenhada: fora da seleção
    // quem acusa é a pré-validação da montagem, e desfazer o flag ali não conserta nada.
    const accepted = new Set(draft.proposalIds);
    return targets
      .filter(
        (proposalId) =>
          accepted.has(proposalId) && draft.freeform.has(proposalId),
      )
      .map((proposalId) => ({ kind: "treat_rectangular" as const, proposalId }));
  }
  if (cause === "TRACE_SPAN_AXIS_UNDECLARED") {
    return rectifiable(reading) ? [{ kind: "declare_axis", readingId }] : [];
  }
  if (REASSOCIABLE_CAUSES.has(cause)) {
    const fixes = alternativeFixes(review, draft, readingId, targets);
    if (rectifiable(reading)) {
      fixes.push({ kind: "rectify", readingId });
    }
    return fixes;
  }
  // Notas e causas sem conserto mecânico ficam como diagnóstico honesto: o conserto da
  // nota é reposicioná-la, e esse controle já existe na própria etapa.
  return [];
}

function contestedFinding(
  contested: NonNullable<TraceSolveResponse["contested_spans"]>[number],
  review: Review,
  draft: TraceDraft,
): AdvisorFinding {
  const fixes: AdvisorFix[] = [];
  for (const readingId of contested.reading_ids) {
    const reading = eligibleReading(review, readingId);
    if (!reading) {
      continue;
    }
    fixes.push(
      ...alternativeFixes(review, draft, readingId, contested.proposal_ids),
    );
    if (rectifiable(reading)) {
      fixes.push({ kind: "rectify", readingId });
    }
  }
  // Manter separados só faz sentido com um par nomeado; três formas disputando o mesmo
  // vão é um desenho que o revisor precisa olhar, não um par para declarar.
  if (contested.proposal_ids.length === 2) {
    const [first, second] = contested.proposal_ids;
    const accepted = new Set(draft.proposalIds);
    if (
      first !== second &&
      accepted.has(first) &&
      accepted.has(second) &&
      !keepApartDeclared(draft, first, second)
    ) {
      fixes.push({ kind: "keep_apart", first, second });
    }
  }
  return {
    message: traceContestedSpanLabel(contested, review.packet.readings),
    rawCode: CONTESTED_SPAN_CODE,
    fixes,
  };
}

/**
 * Achados do resultado corrente, na ordem do contrato: primeiro as leituras que não
 * viraram vão, depois os vãos em disputa. Resposta sem os campos de diagnóstico (registro
 * anterior à F-025) devolve lista vazia, e a tela segue mostrando o que mostrava antes.
 */
export function adviseTrace(
  solve: TraceSolveResponse,
  review: Review,
  draft: TraceDraft,
): AdvisorFinding[] {
  const proposals = review.proposals?.proposals ?? [];
  const scale = review.calibration?.scale_m_per_px ?? null;
  const findings: AdvisorFinding[] = (solve.unapplied_readings ?? []).map(
    (unapplied) => ({
      readingId: unapplied.reading_id,
      message: traceUnappliedCauseLabel(
        unapplied,
        review.packet.readings,
        proposals,
        scale,
      ),
      rawCode: unapplied.cause,
      fixes: unappliedFixes(
        unapplied.cause,
        unapplied.target_proposal_ids,
        unapplied.reading_id,
        review,
        draft,
      ),
    }),
  );
  for (const contested of solve.contested_spans ?? []) {
    findings.push(contestedFinding(contested, review, draft));
  }
  return findings;
}

/** Texto do botão do conserto; o alvo já é nomeado na frase do achado. */
export function advisorFixLabel(fix: AdvisorFix): string {
  switch (fix.kind) {
    case "treat_rectangular":
      return "Tratar a forma como retangular";
    case "reassociate":
      return `Amarrar a ${fix.label}`;
    case "declare_axis":
      return "Declarar o eixo da cota";
    case "keep_apart":
      return "Manter as duas separadas";
    case "rectify":
      return "Corrigir a leitura";
  }
}

/** Chave estável de render: o mesmo conserto nunca aparece duas vezes no mesmo achado. */
export function advisorFixKey(fix: AdvisorFix): string {
  switch (fix.kind) {
    case "treat_rectangular":
      return `${fix.kind}:${fix.proposalId}`;
    case "reassociate":
      return `${fix.kind}:${fix.readingId}:${fix.proposalId}`;
    case "declare_axis":
    case "rectify":
      return `${fix.kind}:${fix.readingId}`;
    case "keep_apart":
      return `${fix.kind}:${fix.first}:${fix.second}`;
  }
}
