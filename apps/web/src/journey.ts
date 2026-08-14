import type { ExportArtifact, Review, TraceSolveResponse } from "./api";
import { exportStatusLabel } from "./approval";
import { traceSolveStatusLabel } from "./trace";

/**
 * Jornada da revisão: decisões → traçado → aprovação → exportação.
 *
 * A máquina de estados real é do servidor; esta derivação apenas ESPELHA o que a
 * página já carregou, para que a tela mostre uma etapa por vez em vez de todas ao
 * mesmo tempo. Nenhum gate daqui substitui os guards da API: traçado com leitura não
 * confirmada volta `review_required` do worker, aprovação exige entidades mais
 * critérios declarados e `ensure_exportable()`, e o export exige a aprovação da
 * revisão exata.
 *
 * O gate do traçado é estrito de propósito: enquanto houver leitura `proposed` ou
 * `ambiguous` no pacote, a etapa fica bloqueada com a contagem pendente no motivo.
 *
 * Módulo puro: os motivos de bloqueio são frases de obra e precisam ser testáveis sem
 * DOM e sem rede.
 */

export type JourneyStepId = "decisions" | "trace" | "approval" | "export";

export type JourneyStepStatus = "blocked" | "available" | "done";

export type JourneyStep = {
  id: JourneyStepId;
  title: string;
  status: JourneyStepStatus;
  /** Resumo curto da etapa; é o que a etapa recolhida mostra. */
  summary: string;
  /** Motivo em língua de obra, presente somente quando a etapa está bloqueada. */
  blockedReason?: string;
};

export type JourneyState = {
  steps: JourneyStep[];
  /** Primeira etapa em aberto; etapa bloqueada nunca é a ativa. */
  activeStep: JourneyStepId;
};

const STEP_ORDER: JourneyStepId[] = ["decisions", "trace", "approval", "export"];

const STEP_TITLES: Record<JourneyStepId, string> = {
  decisions: "Decisões",
  trace: "Traçado",
  approval: "Aprovação",
  export: "Exportação",
};

const STATUS_LABELS: Record<JourneyStepStatus, string> = {
  blocked: "bloqueada",
  available: "em aberto",
  done: "concluída",
};

/** Estado da etapa em texto: marca e cor nunca são o único indicador. */
export function journeyStepStatusLabel(status: JourneyStepStatus): string {
  return STATUS_LABELS[status];
}

function plural(count: number, singular: string, many: string): string {
  return `${count} ${count === 1 ? singular : many}`;
}

/** Leitura ainda sem decisão humana registrada. */
function isUndecided(status: string): boolean {
  return status === "proposed" || status === "ambiguous";
}

export function deriveJourney(input: {
  review: Review | null;
  traceSolve: TraceSolveResponse | null;
  exportArtifact: ExportArtifact | null;
  approvedRevisionId: string | null;
}): JourneyState {
  const { review, traceSolve, exportArtifact } = input;
  // O App guarda o id da revisão aprovada como texto vazio antes de existir.
  const approvedRevisionId = input.approvedRevisionId?.trim()
    ? input.approvedRevisionId
    : null;

  if (!review) {
    // A jornada não é renderizada sem revisão; a função ainda assim não pode explodir.
    return {
      steps: STEP_ORDER.map((id) => ({
        id,
        title: STEP_TITLES[id],
        status: "blocked",
        summary: "Nenhuma revisão aberta.",
        blockedReason: "aguarda a abertura de uma revisão",
      })),
      activeStep: "decisions",
    };
  }

  const readings = review.packet.readings;
  const undecidedCount = readings.filter((reading) =>
    isUndecided(reading.status),
  ).length;
  // Rejeitada é decidida: o que falta decidir é o que ainda está proposto ou ambíguo.
  const decidedCount = readings.length - undecidedCount;
  const decisionsDone = readings.length > 0 && undecidedCount === 0;

  const decisions: JourneyStep = {
    id: "decisions",
    title: STEP_TITLES.decisions,
    status: decisionsDone ? "done" : "available",
    summary:
      readings.length === 0
        ? "O pacote de revisão não trouxe leituras."
        : `${decidedCount} de ${plural(
            readings.length,
            "leitura decidida",
            "leituras decididas",
          )}`,
  };

  const entities = review.scene?.entities ?? [];
  const proposalCount = review.proposals?.proposals.length ?? 0;
  const traceSummary = traceSolve
    ? traceSolveStatusLabel(traceSolve)
    : entities.length > 0
      ? `Cena métrica com ${plural(entities.length, "elemento", "elementos")}.`
      : proposalCount > 0
        ? `${plural(
            proposalCount,
            "forma detectada",
            "formas detectadas",
          )} no desenho.`
        : "Nenhuma forma detectada no desenho.";
  const trace: JourneyStep = {
    id: "trace",
    title: STEP_TITLES.trace,
    status: "available",
    summary: traceSummary,
  };
  if (!decisionsDone) {
    trace.status = "blocked";
    trace.blockedReason =
      readings.length === 0
        ? "o pacote de revisão ainda não tem leituras para decidir"
        : `aguarda ${plural(
            undecidedCount,
            "leitura pendente",
            "leituras pendentes",
          )}`;
  } else if (!review.proposals) {
    trace.status = "blocked";
    trace.blockedReason = "o desenho ainda não tem formas detectadas";
  } else if (entities.length > 0) {
    trace.status = "done";
  }

  const approvalDone =
    review.scene?.approved === true || approvedRevisionId !== null;
  const approval: JourneyStep = {
    id: "approval",
    title: STEP_TITLES.approval,
    status: "available",
    summary: approvalDone
      ? review.scene
        ? `Cena v${review.scene.version} aprovada tecnicamente.`
        : "Aprovação técnica registrada."
      : entities.length > 0
        ? `Cena métrica com ${plural(
            entities.length,
            "elemento",
            "elementos",
          )} aguardando assinatura.`
        : "Nenhuma cena métrica para aprovar ainda.",
  };
  if (entities.length === 0) {
    approval.status = "blocked";
    approval.blockedReason = "aguarda o traçado resolvido";
  } else if (approvalDone) {
    approval.status = "done";
  }

  const exportStep: JourneyStep = {
    id: "export",
    title: STEP_TITLES.export,
    status: "available",
    // O motivo de uma exportação reprovada fica na própria seção, com os erros da
    // auditoria; no trilho ela volta a ser uma etapa em aberto, não um bloqueio.
    summary: exportStatusLabel(exportArtifact),
  };
  if (approval.status !== "done") {
    exportStep.status = "blocked";
    exportStep.blockedReason = "aguarda a aprovação técnica";
  } else if (exportArtifact?.status === "COMPLETED") {
    exportStep.status = "done";
  }

  const steps = [decisions, trace, approval, exportStep];
  // A ativa é a primeira etapa em aberto. Sem nenhuma em aberto (tudo concluído, ou o
  // que resta bloqueado), a jornada fica na última etapa alcançável em vez de abrir
  // uma etapa bloqueada.
  const openStep = steps.find((step) => step.status === "available");
  const lastReachable = [...steps]
    .reverse()
    .find((step) => step.status !== "blocked");
  return {
    steps,
    activeStep: openStep?.id ?? lastReachable?.id ?? "decisions",
  };
}
