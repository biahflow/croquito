/**
 * Corpos de requisição do servidor local, derivados dos rascunhos da tela.
 *
 * Espelham o contrato de `services/worker/src/croquito_worker/valuation/local_server.py`:
 * campo vazio é omitido em vez de ir como string vazia (`""` seria uma correção do dado,
 * não a ausência de correção), e identidade/horário nunca aparecem — o servidor recusaria
 * (`extra="forbid"`), e mandá-los seria pedir para carimbar decisão em nome de outra
 * pessoa. Isto ainda monta o formato do servidor local, com guarda por digest; a conversão
 * para `base_version` é de uma tarefa seguinte.
 */

import type { CalcBuildDraft, CodeDecisionDraft, TakeoffDecisionDraft } from "./api";

export function takeoffDecisionBody(
  draft: TakeoffDecisionDraft,
): Record<string, string> {
  const body: Record<string, string> = {
    item_id: draft.itemId,
    action: draft.action,
    base_packet_sha256: draft.basePacketSha256,
  };
  const optional: [string, string | undefined][] = [
    ["quantity", draft.quantity],
    ["unit", draft.unit],
    ["note", draft.note],
    ["item_note", draft.itemNote],
  ];
  for (const [key, value] of optional) {
    const cleaned = value?.trim();
    if (cleaned) {
      body[key] = cleaned;
    }
  }
  return body;
}

export function codeDecisionBody(
  draft: CodeDecisionDraft,
): Record<string, string> {
  const body: Record<string, string> = {
    item_id: draft.itemId,
    action: draft.action,
  };
  const code = draft.code?.trim();
  if (code) {
    body.code = code;
  }
  const note = draft.note?.trim();
  if (note) {
    body.note = note;
  }
  if (draft.baseAssignmentsSha256) {
    body.base_assignments_sha256 = draft.baseAssignmentsSha256;
  }
  return body;
}

/**
 * Termo de busca para recuperar a descrição completa de um código já confirmado, via
 * `GET /catalog/search`. O servidor tokeniza o código (`lexical_tokens`, NFKD sem
 * acento) e descarta token com menos de dois caracteres, então o sufixo de variante
 * entre parênteses (`(A)`, `(B)`, `(/)`) já sai da busca sozinho na maioria dos casos —
 * esta função só existe para o caso em que ele não sair: remove o sufixo primeiro e,
 * se sobrar vazio (código malformado), cai nos dez primeiros caracteres, que é o
 * tamanho do código base SCO.
 */
export function codeSearchTerm(code: string): string {
  const trimmed = code.trim();
  const withoutSuffix = trimmed.replace(/\([^)]*\)\s*$/, "").trim();
  return withoutSuffix.length > 0 ? withoutSuffix : trimmed.slice(0, 10);
}

/** Corpo do `POST /calc/build`; `period_number` é o único inteiro do contrato. */
export function calcBuildBody(
  draft: CalcBuildDraft,
): Record<string, string | number> {
  const body: Record<string, string | number> = {
    worksite_key: draft.worksiteKey.trim(),
    worksite_name: draft.worksiteName.trim(),
    period_number: Number(draft.periodNumber.trim()),
    reference_label: draft.referenceLabel.trim(),
  };
  const address = draft.address?.trim();
  if (address) {
    body.address = address;
  }
  const contractLabel = draft.contractLabel?.trim();
  if (contractLabel) {
    body.contract_label = contractLabel;
  }
  return body;
}

/**
 * Corpo do `POST /suggestions/recompute`. A chave só entra quando há digest-base a
 * citar — omitida, e não vazia, porque o servidor recusa `base_suggestions_sha256`
 * citado sem shortlist prévia (`LOCAL_BASE_DIGEST_UNEXPECTED`).
 */
export function suggestionsRecomputeBody(
  baseSuggestionsSha256: string | null,
): Record<string, string> {
  const body: Record<string, string> = {};
  if (baseSuggestionsSha256) {
    body.base_suggestions_sha256 = baseSuggestionsSha256;
  }
  return body;
}
