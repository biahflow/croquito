/**
 * Correção de decisão registrada, na parte que não depende de DOM: o que a tela
 * pré-preenche a partir do que já está gravado e o que ela envia à API.
 *
 * Duas regras do domínio moram aqui e são testadas sem tela: a associação é sempre
 * redeclarada (pré-preenchida, nunca herdada em silêncio) e a justificativa nasce
 * vazia — corrigir o registro de um profissional é um ato novo, com texto novo.
 */
import type { ReviewReading, ReviewRectification } from "./api";

export type RectificationPrefill = {
  /** Proposta associada, o marcador de anotação da folha, ou vazio quando não há. */
  associationValue: string;
  rawText: string;
  value: string;
  unit: "m" | "mm";
  kind: string;
  justification: "";
};

/** Número como a cota é escrita na folha; o valor gravado usa ponto. */
function writtenValue(value: string | null | undefined): string {
  return (value ?? "").replace(".", ",");
}

/**
 * Valores vigentes da leitura decidida. `annotationOption` é o marcador da tela para
 * "anotação da folha, não mede elemento": uma leitura confirmada sem associação foi
 * decidida assim, e a correção precisa mostrar isso já selecionado.
 */
export function rectificationPrefill(
  reading: ReviewReading,
  currentAssociationProposalId: string | undefined,
  annotationOption: string,
): RectificationPrefill {
  let associationValue = "";
  if (currentAssociationProposalId) {
    associationValue = currentAssociationProposalId;
  } else if (reading.status === "confirmed") {
    associationValue = annotationOption;
  }
  return {
    associationValue,
    rawText: reading.raw_text,
    value: writtenValue(reading.value_si),
    unit: reading.unit === "mm" ? "mm" : "m",
    kind: reading.kind,
    justification: "",
  };
}

/** `null` quando a leitura não tem decisão a corrigir — ela usa a decisão normal. */
export function rectificationTarget(reading: ReviewReading): string | null {
  return reading.decision?.decision_id ?? null;
}

/**
 * O formulário de decisão aparece para leitura ainda pendente e, reusado inteiro, para
 * a correção em curso. Uma leitura decidida nunca reabre o formulário sozinha.
 */
export function showsDecisionForm(
  reading: ReviewReading,
  rectifyingReadingId: string | null,
): boolean {
  return (
    ["proposed", "ambiguous"].includes(reading.status) ||
    rectifyingReadingId === reading.id
  );
}

/** O registro somente-leitura da decisão, com o botão que abre a correção. */
export function showsDecisionRecord(
  reading: ReviewReading,
  rectifyingReadingId: string | null,
): boolean {
  return (
    rectifyingReadingId !== reading.id &&
    ["confirmed", "rejected"].includes(reading.status) &&
    Boolean(reading.decision)
  );
}

/**
 * Momento da decisão em UTC, como o servidor a gravou. Formatado aqui, e não pelo
 * locale do navegador, para o registro lido na tela ser o mesmo em qualquer máquina.
 */
export function decisionMoment(decidedAt: string): string {
  const parsed = new Date(decidedAt);
  if (Number.isNaN(parsed.getTime())) {
    return decidedAt;
  }
  const pad = (value: number) => String(value).padStart(2, "0");
  return (
    `${pad(parsed.getUTCDate())}/${pad(parsed.getUTCMonth() + 1)}/` +
    `${parsed.getUTCFullYear()} às ${pad(parsed.getUTCHours())}:` +
    `${pad(parsed.getUTCMinutes())} UTC`
  );
}

export type RectificationForm = {
  action: "confirm" | "reject";
  justification: string;
  associationValue: string;
  annotationOption: string;
  rawText: string;
  written: { value_si: string; written_decimals: number } | null;
  unit: "m" | "mm";
  kind: string;
  /**
   * Correção do rótulo de elemento que o modelo leu no balão (F-051). Aditivo: em branco
   * não viaja, e o hint vigente da leitura fica como está — corrigir o hint é parte desta
   * mesma correção declarada, nunca um ato à parte.
   */
  entityLabel?: string;
};

/**
 * Monta o comando enviado à API. Devolve `null` quando a leitura não carrega decisão
 * vigente: sem alvo declarado não há correção, e inventar um seria escrever por cima
 * de um registro que a tela não leu.
 */
export function buildRectification(
  reading: ReviewReading,
  form: RectificationForm,
): ReviewRectification | null {
  const target = rectificationTarget(reading);
  if (!target) {
    return null;
  }
  const annotation =
    form.action === "confirm" && form.associationValue === form.annotationOption;
  return {
    reading_id: reading.id,
    action: form.action,
    rectifies_decision_id: target,
    justification: form.justification.trim(),
    association_proposal_id:
      form.action === "reject" || annotation ? undefined : form.associationValue,
    annotation: annotation ? true : undefined,
    raw_text: form.rawText.trim() || undefined,
    value_si: form.written?.value_si,
    written_decimals: form.written?.written_decimals,
    unit: form.written ? form.unit : undefined,
    kind: form.kind || undefined,
    target_entity_label: form.entityLabel?.trim() || undefined,
  };
}
