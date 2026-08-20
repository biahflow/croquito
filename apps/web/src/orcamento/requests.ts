/**
 * Corpos de requisição do orçamento-base `/v1`, derivados dos rascunhos da tela.
 *
 * Espelham o contrato das rotas `/v1/estimate-rounds*`
 * (`services/api/src/croquito_api/main.py`): campo vazio é omitido em vez de ir como
 * string vazia (`""` seria uma correção do dado, não a ausência de correção), e
 * identidade/horário nunca aparecem — o servidor recusaria (`extra="forbid"`), e
 * mandá-los seria pedir para carimbar decisão em nome de outra pessoa. Toda mutação cita
 * `base_version`: a guarda otimista é da rodada e vale para a cadeia inteira.
 *
 * A diferença de contrato para a medição é uma só, e é a razão do módulo existir
 * separado: **a confirmação de código CITA a fonte de preço** (`catalog_sha256`). Com
 * mais de uma tabela na cascata, resolver o código pela ordem seria a máquina escolhendo
 * quem precifica o item.
 *
 * Módulo puro de propósito: é aqui que a regra "o que sai no corpo" fica testável sem
 * transporte.
 */

import { parseDecimalInput } from "./format";
import type {
  CascadeOrderDraft,
  CascadeRemoveDraft,
  CodeDecisionDraft,
  CreateEstimateDraft,
  TakeoffDecisionDraft,
} from "./api";

/** Corpo mínimo de toda mutação da rodada: só a guarda de concorrência. */
export function versionBody(baseVersion: number): { base_version: number } {
  return { base_version: baseVersion };
}

/**
 * Mesmo padrão que o domínio exige do `Estimate` (`WORKSITE_KEY_PATTERN`) e que a rota
 * repete. A chave é IMUTÁVEL na rodada: aceitá-la livre faria um orçamento nascer válido
 * e só quebrar na montagem, dezenas de decisões depois.
 */
export const WORKSITE_KEY_PATTERN = /^[a-z0-9][a-z0-9-]{2,63}$/;

/**
 * Motivo, em língua de obra, de a chave da obra não servir — ou `null` quando ela serve.
 * A recusa do servidor continua valendo; esta é só a que evita a viagem.
 */
export function worksiteKeyError(value: string): string | null {
  const key = value.trim();
  if (key.length === 0) {
    return "Informe a chave da obra.";
  }
  if (!WORKSITE_KEY_PATTERN.test(key)) {
    return (
      "A chave da obra aceita apenas minúsculas, números e hífen, começa por letra ou " +
      "número e tem de 3 a 64 caracteres (ex.: praca-do-exemplo)."
    );
  }
  return null;
}

/**
 * Corpo do `POST /v1/estimate-rounds`. Sem catálogo e sem período: a cascata é a etapa
 * seguinte (e aceita mais de uma fonte), e período é conceito da obra já licitada.
 */
export function createEstimateBody(
  draft: CreateEstimateDraft,
): Record<string, string> {
  const body: Record<string, string> = {
    worksite_key: draft.worksiteKey.trim(),
    worksite_name: draft.worksiteName.trim(),
    reference_label: draft.referenceLabel.trim(),
  };
  const address = draft.address?.trim();
  if (address) {
    body.address = address;
  }
  return body;
}

/** Corpo do `POST .../catalogs`: o JSON do catálogo já subiu pelo presign. */
export function installCatalogBody(
  uploadId: string,
  baseVersion: number,
): Record<string, string | number> {
  return { upload_id: uploadId, ...versionBody(baseVersion) };
}

/**
 * Corpo do `POST .../catalogs/order`: a lista COMPLETA dos digests, na ordem nova.
 *
 * Completa, e não "mova esta fonte para a posição N", porque a ordem inteira é a regra de
 * precificação: um corpo parcial obrigaria o servidor a decidir onde as fontes omitidas
 * entram, e essa decisão é exatamente a que o ADR-0027 tira do código.
 */
export function cascadeOrderBody(
  draft: CascadeOrderDraft,
): Record<string, string[] | number> {
  return { ...versionBody(draft.baseVersion), cascade: [...draft.cascade] };
}

/** Corpo do `POST .../catalogs/remove`: o digest da fonte a remover, e nada mais. */
export function cascadeRemoveBody(
  draft: CascadeRemoveDraft,
): Record<string, string | number> {
  return {
    ...versionBody(draft.baseVersion),
    source_sha256: draft.sourceSha256,
  };
}

export function takeoffDecisionBody(
  draft: TakeoffDecisionDraft,
): Record<string, string | number> {
  const body: Record<string, string | number> = {
    ...versionBody(draft.baseVersion),
    item_id: draft.itemId,
    action: draft.action,
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

/**
 * Corpo do `POST .../code-assignments/decisions`.
 *
 * A confirmação leva `code` E `catalog_sha256` — a rota recusa confirmação sem fonte
 * citada (`ESTIMATE_ASSIGNMENT_CATALOG_REQUIRED`). A rejeição leva nota e NÃO leva fonte:
 * rejeitar é recusar todas as fontes, não uma delas, e o servidor recusa a citação junto
 * da rejeição (`ASSIGNMENT_CATALOG_ON_REJECT`). A tela já manda só o que cabe em cada ato.
 */
export function codeDecisionBody(
  draft: CodeDecisionDraft,
): Record<string, string | number> {
  const body: Record<string, string | number> = {
    ...versionBody(draft.baseVersion),
    item_id: draft.itemId,
    action: draft.action,
  };
  if (draft.action === "confirm") {
    const code = draft.code?.trim();
    if (code) {
      body.code = code;
    }
    const catalog = draft.catalogSha256?.trim();
    if (catalog) {
      body.catalog_sha256 = catalog;
    }
  }
  const note = draft.note?.trim();
  if (note) {
    body.note = note;
  }
  return body;
}

/**
 * Motivo de o BDI escrito não servir — ou `null` quando ele serve. O servidor continua
 * sendo a autoridade (`422 ESTIMATE_BDI_INVALID`); esta é só a recusa que evita a viagem
 * e explica a notação aceita a quem está digitando.
 */
export function bdiPercentError(value: string): string | null {
  if (value.trim().length === 0) {
    return "Informe o percentual de BDI deste orçamento.";
  }
  if (parseDecimalInput(value) === null) {
    return (
      "O BDI é um percentual decimal — escreva 25,00 ou 25.00. Ele não é arredondado " +
      "nem convertido: viaja como texto para o servidor lê-lo exato."
    );
  }
  return null;
}

/**
 * Corpo do `POST .../estimate`. `bdi_percent` sai como TEXTO decimal, sempre: ele é
 * `ExactDecimal` no domínio (ADR-0038, decisão 2), que recusa `float`. Texto que não é
 * decimal devolve `null` aqui, e a tela recusa antes de chamar.
 */
export function buildEstimateBody(
  bdiPercent: string,
  baseVersion: number,
): Record<string, string | number> | null {
  const percent = parseDecimalInput(bdiPercent);
  if (percent === null) {
    return null;
  }
  return { ...versionBody(baseVersion), bdi_percent: percent };
}
