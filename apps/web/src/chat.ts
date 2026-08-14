import type {
  ChatActDraft,
  ChatAnchors,
  ChatSessionSummary,
  ChatTurn,
  ReviewChatOutput,
  ReviewDecision,
  ReviewReading,
} from "./api";
import {
  MAX_NOTE_LENGTH,
  type SpanTargetDraft,
  type TraceDraft,
} from "./trace";

/**
 * Conversa da revisão, do lado da tela.
 *
 * O agente é observacional: ele responde e propõe rascunhos, e nada aqui submete ato
 * nenhum (ADR-0023). Este módulo traduz turno e rascunho para língua de obra e converte
 * o rascunho no formulário que o profissional ainda vai revisar e assinar — por isso é
 * puro: cada regra abaixo é verificável sem DOM e sem rede.
 *
 * Duas regras atravessam o arquivo inteiro:
 *
 * - O rascunho NUNCA porta valor de medida. O que a tela mostra como "valor escrito" vem
 *   sempre do pacote de revisão, pelo `reading_id` citado.
 * - Nenhuma conversão daqui vira envio. O resultado é sempre um formulário pré-preenchido
 *   ou um rascunho de aceite — atos que continuam esperando o comando humano.
 */

/** Mesmo limite do contrato (`ChatAnchors`); a tela apara antes de o servidor recusar. */
export const CHAT_ANCHOR_LIMIT = 20;

const QUESTION_MIN_LENGTH = 3;
const QUESTION_MAX_LENGTH = 500;

/** `null` quando a pergunta cabe no contrato; senão a frase mostrada ao profissional. */
export function chatQuestionIssue(question: string): string | null {
  const trimmed = question.trim();
  if (trimmed.length < QUESTION_MIN_LENGTH) {
    return "Escreva a pergunta sobre a folha (mínimo de 3 caracteres).";
  }
  if (trimmed.length > QUESTION_MAX_LENGTH) {
    return `A pergunta não pode passar de ${QUESTION_MAX_LENGTH} caracteres.`;
  }
  return null;
}

/**
 * Âncoras do envio, na ordem em que o profissional apontou. A poda pelo limite é
 * declarada na tela; aqui ela só impede um 422 previsível.
 */
export function buildChatAnchors(
  readingIds: string[],
  proposalIds: string[],
): ChatAnchors {
  return {
    reading_ids: [...new Set(readingIds)].slice(0, CHAT_ANCHOR_LIMIT),
    proposal_ids: [...new Set(proposalIds)].slice(0, CHAT_ANCHOR_LIMIT),
  };
}

/** A tela usa uma conversa só: a primeira aberta do job, nunca uma nova por pergunta. */
export function pickOpenChatSession(
  sessions: ChatSessionSummary[],
): ChatSessionSummary | null {
  return sessions.find((session) => session.status === "OPEN") ?? null;
}

/** Turno em voo: enquanto houver um, o servidor recusa a próxima pergunta da sessão. */
export function chatTurnInFlight(turn: ChatTurn | null | undefined): boolean {
  return turn?.status === "QUEUED" || turn?.status === "RUNNING";
}

const FAILURE_LABELS: Record<string, string> = {
  CHAT_ACT_UNKNOWN_REFERENCE:
    "a resposta citou algo que não está na folha; foi descartada por segurança",
  CHAT_PROVIDER_UNAVAILABLE:
    "nenhum agente está disponível para responder agora",
  CHAT_ANSWER_FAILED:
    "a resposta não chegou em forma aproveitável; pergunte de novo",
};

/** Motivo da falha em língua de obra; código desconhecido aparece como está, sem prosa inventada. */
export function chatFailureLabel(failureCode: string | null): string {
  if (!failureCode) {
    return "a resposta não chegou; pergunte de novo";
  }
  return FAILURE_LABELS[failureCode] ?? `a resposta falhou (${failureCode})`;
}

export function chatTurnStatusLabel(turn: ChatTurn): string {
  switch (turn.status) {
    case "QUEUED":
      return "na fila, aguardando resposta…";
    case "RUNNING":
      return "o agente está lendo a folha…";
    case "COMPLETED":
      return "o agente respondeu";
    case "FAILED":
      return `a pergunta falhou — ${chatFailureLabel(turn.failure_code)}; tente de novo`;
  }
}

/** Uma frase para o feed: quanto veio, e se veio sugestão para revisar. */
export function chatAnswerSummary(answer: ReviewChatOutput): string {
  if (answer.answer_kind === "uncertain") {
    return "ainda não dá para afirmar — o agente devolveu uma pergunta em aberto";
  }
  const count = answer.proposed_acts.length;
  if (count === 0) {
    return "respondeu sem sugerir nenhum ato";
  }
  return count === 1
    ? "respondeu com 1 sugestão para você revisar"
    : `respondeu com ${count} sugestões para você revisar`;
}

/** O que o rascunho cita: é por aqui que o cartão ancora na evidência da folha. */
export type ChatActAnchor = {
  readingId: string | null;
  proposalIds: string[];
};

export function chatActAnchor(draft: ChatActDraft): ChatActAnchor {
  switch (draft.act) {
    case "reading_decision":
      return {
        readingId: draft.reading_id,
        proposalIds: draft.association_proposal_id
          ? [draft.association_proposal_id]
          : [],
      };
    case "trace_association":
      return {
        readingId: draft.reading_id,
        proposalIds:
          typeof draft.target === "string" ? [draft.target] : [...draft.target],
      };
    case "keep_apart":
      return { readingId: null, proposalIds: [draft.first, draft.second] };
    case "note_association":
      return {
        readingId: draft.reading_id,
        proposalIds: noteTargetProposalIds(draft.target),
      };
    case "pending_note":
      return { readingId: null, proposalIds: [] };
  }
}

const NOTE_TARGET_STAMP = "carimbo";
const NOTE_LEGEND_PREFIX = "legenda:";

function noteTargetProposalIds(target: string): string[] {
  if (target === NOTE_TARGET_STAMP) {
    return [];
  }
  const withoutPrefix = target.startsWith(NOTE_LEGEND_PREFIX)
    ? target.slice(NOTE_LEGEND_PREFIX.length)
    : target;
  const hashIndex = withoutPrefix.indexOf("#");
  return [hashIndex === -1 ? withoutPrefix : withoutPrefix.slice(0, hashIndex)];
}

/** Nome de obra de cada forma, para o cartão nunca falar por identificador. */
export type ChatActNaming = {
  proposalName: (proposalId: string) => string;
  readings: ReviewReading[];
};

function readingOf(
  readings: ReviewReading[],
  readingId: string,
): ReviewReading | undefined {
  return readings.find((reading) => reading.id === readingId);
}

/**
 * O valor como está escrito na folha, sempre do pacote. Uma leitura que não está mais no
 * pacote é dita assim, em vez de a tela repetir o que o rascunho afirmou.
 */
function writtenValue(readings: ReviewReading[], readingId: string): string {
  const reading = readingOf(readings, readingId);
  return reading ? `"${reading.raw_text}"` : "uma cota que não está no pacote";
}

/** Frase do ato para o cartão: o que ele faria, com o valor como escrito na folha. */
export function chatActLabel(
  draft: ChatActDraft,
  naming: ChatActNaming,
): string {
  const { proposalName, readings } = naming;
  switch (draft.act) {
    case "reading_decision": {
      const value = writtenValue(readings, draft.reading_id);
      if (draft.action === "reject") {
        return `Rejeitar a leitura ${value}.`;
      }
      if (draft.annotation) {
        return `Confirmar a leitura ${value} como anotação da folha, sem medir elemento.`;
      }
      return draft.association_proposal_id
        ? `Confirmar a leitura ${value} associada a ${proposalName(draft.association_proposal_id)}.`
        : `Confirmar a leitura ${value} — a associação ainda precisa ser escolhida por você.`;
    }
    case "trace_association": {
      const value = writtenValue(readings, draft.reading_id);
      return typeof draft.target === "string"
        ? `Amarrar a cota ${value} ao vão de ${proposalName(draft.target)}.`
        : `Amarrar a cota ${value} ao vão entre ${proposalName(draft.target[0])} e ${proposalName(draft.target[1])}.`;
    }
    case "keep_apart": {
      const axis =
        draft.axis === "x"
          ? " no eixo horizontal"
          : draft.axis === "y"
            ? " no eixo vertical"
            : "";
      return `Declarar que ${proposalName(draft.first)} e ${proposalName(draft.second)} são elementos distintos${axis}.`;
    }
    case "note_association": {
      const value = writtenValue(readings, draft.reading_id);
      if (draft.target === NOTE_TARGET_STAMP) {
        return `Levar a anotação ${value} para o carimbo da prancha.`;
      }
      const [proposalId] = noteTargetProposalIds(draft.target);
      return draft.target.startsWith(NOTE_LEGEND_PREFIX)
        ? `Levar a anotação ${value} para a legenda de ${proposalName(proposalId)}.`
        : `Prender a anotação ${value} a ${proposalName(proposalId)}.`;
    }
    case "pending_note":
      return `Registrar a pendência para o projetista: "${draft.text}".`;
  }
}

/**
 * Rascunho de decisão → corpo da decisão que o profissional vai assinar.
 *
 * Devolve `null` quando o ato não é decisão de leitura, quando a leitura citada não está
 * no pacote e quando ela já foi decidida: decisão registrada é imutável, e corrigi-la é
 * ato declarado próprio (ADR-0022), nunca uma segunda decisão vinda de sugestão.
 *
 * Nada de medida entra aqui. `action` do contrato é só `confirm`/`reject` — não existe
 * `correct` por sugestão —, então `raw_text`, `value_si`, `unit` e `kind` ficam de fora
 * por construção: o que a folha diz continua vindo do pacote.
 */
export function draftToReviewDecision(
  draft: ChatActDraft,
  readings: ReviewReading[],
): ReviewDecision | null {
  if (draft.act !== "reading_decision") {
    return null;
  }
  const reading = readingOf(readings, draft.reading_id);
  if (!reading) {
    return null;
  }
  if (reading.status === "confirmed" || reading.status === "rejected") {
    return null;
  }
  const rejecting = draft.action === "reject";
  return {
    reading_id: draft.reading_id,
    action: draft.action,
    // Sugestão de texto: a tela deixa editável e o revisor assina o que ele escrever.
    justification: draft.justification_draft,
    association_proposal_id:
      rejecting || draft.annotation
        ? undefined
        : (draft.association_proposal_id ?? undefined),
    annotation: !rejecting && draft.annotation ? true : undefined,
  };
}

/** Desfecho da aplicação de um rascunho sobre o aceite de traçado já montado. */
export type TraceDraftApplication = {
  /** O aceite resultante; o próprio recebido quando nada foi aplicado. */
  draft: TraceDraft;
  applied: boolean;
  /** O que entrou — ou por que não entrou —, em língua de obra. */
  message: string;
};

function unchanged(draft: TraceDraft, message: string): TraceDraftApplication {
  return { draft, applied: false, message };
}

/**
 * Rascunho de traçado aplicado sobre o aceite persistido — nunca enviado.
 *
 * O que ele deliberadamente NÃO faz:
 *
 * - não marca forma nenhuma na seleção: marcar é ato do revisor no desenho, e a
 *   pré-validação do aceite já diz, em língua de obra, quando uma amarração cita forma
 *   fora da seleção;
 * - não apaga declaração humana: alvo já declarado para a mesma leitura é substituído
 *   pelo rascunho apenas no campo do próprio rascunho, e par já declarado é ignorado em
 *   vez de duplicado;
 * - não trunca a pendência escrita: se ela não couber no limite da nota do aceite, nada
 *   é aplicado e o motivo é dito.
 */
export function applyDraftToTraceDraft(
  draft: ChatActDraft,
  traceDraft: TraceDraft,
): TraceDraftApplication {
  switch (draft.act) {
    case "reading_decision":
      return unchanged(
        traceDraft,
        "Este rascunho é de decisão de leitura, não do aceite de traçado.",
      );
    case "trace_association": {
      const target: SpanTargetDraft =
        typeof draft.target === "string"
          ? { kind: "single", proposalId: draft.target }
          : {
              kind: "pair",
              proposalIds: [draft.target[0], draft.target[1]],
            };
      return {
        draft: {
          ...traceDraft,
          associations: {
            ...traceDraft.associations,
            [draft.reading_id]: target,
          },
        },
        applied: true,
        message: "Vão declarado no aceite de traçado.",
      };
    }
    case "keep_apart": {
      const duplicate = traceDraft.keepApartPairs.some(
        (pair) =>
          (pair.first === draft.first && pair.second === draft.second) ||
          (pair.first === draft.second && pair.second === draft.first),
      );
      if (duplicate) {
        return unchanged(
          traceDraft,
          "Esse par já está declarado como distinto no aceite.",
        );
      }
      return {
        draft: {
          ...traceDraft,
          keepApartPairs: [
            ...traceDraft.keepApartPairs,
            { first: draft.first, second: draft.second, axis: draft.axis ?? null },
          ],
        },
        applied: true,
        message: "Par declarado distinto no aceite de traçado.",
      };
    }
    case "note_association":
      return {
        draft: {
          ...traceDraft,
          noteTargets: {
            ...traceDraft.noteTargets,
            [draft.reading_id]: draft.target,
          },
        },
        applied: true,
        message: "Nota amarrada no aceite de traçado.",
      };
    case "pending_note": {
      const text = draft.text.trim();
      const current = traceDraft.note.trim();
      if (!text) {
        return unchanged(traceDraft, "A pendência sugerida está vazia.");
      }
      // Texto idêntico já escrito não vira segunda linha: a nota do aceite é lida por
      // quem recebe a prancha, e repetição vira ruído.
      const parts = current ? current.split("; ") : [];
      if (parts.some((part) => part.trim() === text)) {
        return unchanged(traceDraft, "Essa pendência já está na nota do aceite.");
      }
      const next = current ? `${current}; ${text}` : text;
      if (next.length > MAX_NOTE_LENGTH) {
        return unchanged(
          traceDraft,
          `A pendência não cabe na nota do aceite (limite de ${MAX_NOTE_LENGTH} caracteres); escreva-a você mesmo.`,
        );
      }
      return {
        draft: { ...traceDraft, note: next },
        applied: true,
        message: "Pendência escrita na nota do aceite.",
      };
    }
  }
}
