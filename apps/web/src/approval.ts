import type { ExportArtifact, Review } from "./api";
import { metricEdgeLabel } from "./labels";

export type ApprovalForm = {
  sourceEvidenceChecked: boolean;
  geometryChecked: boolean;
  limitationsAcknowledged: boolean;
  /** Critérios que a cena em aprovação cobre. Disjunto de `acknowledgedCriteria`. */
  coveredCriteria: string[];
  /** Critérios que seguem pendentes fora da cena e são assinados assim mesmo. */
  acknowledgedCriteria: string[];
  statement: string;
};

export const emptyApprovalForm: ApprovalForm = {
  sourceEvidenceChecked: false,
  geometryChecked: false,
  limitationsAcknowledged: false,
  coveredCriteria: [],
  acknowledgedCriteria: [],
  statement: "",
};

/** Uma aproximação aceita: o id vai para a API, o rótulo vai para a tela. */
export type AcceptedApproximation = {
  entityId: string;
  label: string;
};

/** Entities the professional accepted from a pixel proposal, in acceptance order. */
export function deriveAcceptedApproximations(
  review: Review,
): AcceptedApproximation[] {
  const accepted: AcceptedApproximation[] = [];
  for (const decision of review.proposal_decisions) {
    if (decision.action !== "accept" || !decision.entity_id) {
      continue;
    }
    const entityId = decision.entity_id;
    if (accepted.some((item) => item.entityId === entityId)) {
      continue;
    }
    accepted.push({
      entityId,
      label: metricEdgeLabel(
        review.scene?.entities.find((entity) => entity.id === entityId),
      ),
    });
  }
  // A cena traçada também produz `approximate` (layer APROXIMADO), aceita em lote por
  // pessoa identificada no próprio TraceAcceptance — a aprovação as lista nominalmente,
  // senão o portão APPROXIMATION_NOT_ACCEPTED recusa uma cena que o revisor já aceitou.
  for (const entity of review.scene?.entities ?? []) {
    if (entity.precision !== "approximate") {
      continue;
    }
    if (accepted.some((item) => item.entityId === entity.id)) {
      continue;
    }
    accepted.push({ entityId: entity.id, label: metricEdgeLabel(entity) });
  }
  return accepted;
}

/** Um critério do caso: o código vai para a API, o texto é o que o profissional lê. */
export type ScopeCriterion = { code: string; text: string };

/** Scope criteria still open on the scene; geometry blockers are never listed here. */
export function pendingScopeCriteria(review: Review): ScopeCriterion[] {
  const open = new Set(
    (review.scene?.issues ?? review.issues)
      .filter(
        (issue) =>
          issue.severity === "critical" &&
          (issue.status ?? "open") === "open",
      )
      .map((issue) => issue.code),
  );
  return review.required_criteria.filter((criterion) => open.has(criterion.code));
}

export type ApprovalReadiness = {
  canApprove: boolean;
  reasons: string[];
};

export function approvalReadiness(
  review: Review,
  form: ApprovalForm,
): ApprovalReadiness {
  const reasons: string[] = [];
  const scene = review.scene;
  if (!scene) {
    reasons.push("A cena métrica ainda não foi criada.");
    return { canApprove: false, reasons };
  }
  if (scene.approved) {
    reasons.push("Esta revisão já foi aprovada.");
    return { canApprove: false, reasons };
  }
  if (scene.entities.some((entity) => entity.precision === "unresolved")) {
    reasons.push("A cena ainda contém geometria não resolvida.");
  }
  const approximate = scene.entities
    .filter((entity) => entity.precision === "approximate")
    .map((entity) => entity.id);
  const accepted = deriveAcceptedApproximations(review).map(
    (item) => item.entityId,
  );
  if (approximate.some((id) => !accepted.includes(id))) {
    reasons.push(
      "Existe geometria aproximada na cena que não foi aceita explicitamente.",
    );
  }
  const pending = pendingScopeCriteria(review);
  // Cada critério pendente precisa de exatamente uma das duas declarações. A frase cita o
  // texto do critério, que é o que o profissional reconhece; o código sozinho não é aviso.
  const undeclared = pending.filter(
    (criterion) =>
      !form.coveredCriteria.includes(criterion.code) &&
      !form.acknowledgedCriteria.includes(criterion.code),
  );
  if (undeclared.length > 0) {
    reasons.push(
      `Declare cada critério do caso, coberto pela cena ou pendente reconhecido: ${undeclared
        .map((criterion) => criterion.text)
        .join(" · ")}`,
    );
  }
  // A tela usa radios e não deixa isso acontecer; o módulo é puro e recusa mesmo assim.
  const conflicting = form.coveredCriteria.filter((code) =>
    form.acknowledgedCriteria.includes(code),
  );
  if (conflicting.length > 0) {
    reasons.push(
      `Um critério não pode ser coberto e pendente ao mesmo tempo: ${conflicting.join(", ")}.`,
    );
  }
  const declarableCodes = review.required_criteria.map(
    (criterion) => criterion.code,
  );
  const blockingIssues = (scene.issues ?? review.issues).filter(
    (issue) =>
      issue.severity === "critical" &&
      (issue.status ?? "open") === "open" &&
      !declarableCodes.includes(issue.code),
  );
  if (blockingIssues.length > 0) {
    reasons.push(
      `Pendências críticas de geometria impedem a aprovação: ${blockingIssues
        .map((issue) => issue.code)
        .join(", ")}.`,
    );
  }
  if (!form.sourceEvidenceChecked) {
    reasons.push("Confirme que a evidência de origem foi verificada.");
  }
  if (!form.geometryChecked) {
    reasons.push("Confirme que a geometria foi verificada.");
  }
  if (!form.limitationsAcknowledged) {
    reasons.push("Confirme que as limitações foram reconhecidas.");
  }
  const statement = form.statement.trim();
  if (statement.length < 20 || statement.length > 500) {
    reasons.push("A declaração precisa ter entre 20 e 500 caracteres.");
  }
  return { canApprove: reasons.length === 0, reasons };
}

/**
 * Exportação em voo: já enviada e ainda não resolvida pelo worker — espelho de
 * `traceSolveInFlight`. Só ela trava o botão. Exportação que FALHOU não pode travar o
 * reenvio: a auditoria recusou, o revisor corrigiu a cena e precisa exportar de novo.
 * Concluída também libera: a cena pode ter mudado e um pacote novo é legítimo.
 */
export function exportInFlight(artifact: ExportArtifact | null): boolean {
  return artifact?.status === "QUEUED" || artifact?.status === "RUNNING";
}

export function exportStatusLabel(artifact: ExportArtifact | null): string {
  if (!artifact) {
    return "Nenhuma exportação solicitada.";
  }
  switch (artifact.status) {
    case "QUEUED":
      return "Exportação na fila.";
    case "RUNNING":
      return "Gerando e auditando o DXF.";
    case "COMPLETED":
      return "Pacote auditado e disponível.";
    case "FAILED":
      return `Exportação falhou: ${artifact.failure_code ?? "erro desconhecido"}.`;
  }
}
