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
import { ehZeroDecimal } from "./teto";
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
 * Motivo de o teto escrito não servir — ou `null` quando ele serve, **campo vazio
 * incluído**: teto é opcional, e vazio é "sem teto" (ADR-0040, decisão 6).
 *
 * As duas recusas são separadas porque as causas são diferentes e o caminho de saída
 * também: texto que não é valor em reais precisa da notação aceita, e zero precisa saber
 * que **zero não é "sem teto"** — quem não tem verba prevista deixa o campo vazio, e a
 * tela recusa a ambiguidade em vez de escolher por quem digitou. O servidor continua sendo
 * a autoridade (`422 ESTIMATE_TARGET_INVALID`); esta é só a recusa que evita a viagem.
 */
export function tetoAmountError(value: string): string | null {
  if (value.trim().length === 0) {
    return null;
  }
  const amount = parseDecimalInput(value);
  if (amount === null) {
    return (
      "O teto precisa ser um valor em reais, maior que zero. Escreva 85.000,00 ou " +
      "85000.00; para abrir a rodada sem teto, deixe o campo vazio."
    );
  }
  if (ehZeroDecimal(amount)) {
    return (
      "O teto é a verba prevista para a demanda e precisa ser maior que zero. Para " +
      "abrir a rodada sem teto, deixe o campo vazio."
    );
  }
  return null;
}

/**
 * Corpo do `POST /v1/estimate-rounds`. Sem catálogo e sem período: a cascata é a etapa
 * seguinte (e aceita mais de uma fonte), e período é conceito da obra já licitada.
 *
 * O teto entra pelas mesmas regras dos outros opcionais — campo vazio é OMITIDO, e a
 * rodada nasce sem teto, que é o caminho normal. Valor que não serve também é omitido em
 * vez de ir torto: a tela já o recusou (`tetoAmountError`) e o botão não estava
 * disponível, então chegar aqui com ele significa que algo escapou, e mandar "0,00" numa
 * rodada nova gravaria uma ambiguidade que o ADR-0040 recusa.
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
  return { ...body, ...targetFields(draft.targetAmount, draft.targetLabel) };
}

/**
 * As duas chaves do teto — ou `{}`, que é "não mande teto nenhum".
 *
 * Uma definição só para as duas rotas que aceitam teto (abrir a rodada e gravar o teto),
 * porque a regra é a mesma nas duas: valor que a tela recusaria não vira corpo, e rótulo
 * vazio é omitido em vez de virar rótulo em branco gravado na rodada.
 */
function targetFields(
  targetAmount?: string,
  targetLabel?: string,
): Record<string, string> {
  const escrito = targetAmount?.trim();
  if (!escrito || tetoAmountError(escrito) !== null) {
    return {};
  }
  const amount = parseDecimalInput(escrito);
  if (amount === null) {
    return {};
  }
  const fields: Record<string, string> = { target_amount: amount };
  const label = targetLabel?.trim();
  if (label) {
    fields.target_label = label;
  }
  return fields;
}

/**
 * Corpo do `POST .../target`: a guarda otimista de sempre mais o teto em texto decimal.
 *
 * Devolve `null` quando o teto não serve — inclusive quando ele é zero. É a mesma forma do
 * `buildEstimateBody`: valor que a tela recusaria não vira viagem, e a recusa continua
 * sendo do servidor por último.
 */
export function targetBody(
  baseVersion: number,
  targetAmount: string,
  targetLabel?: string,
): Record<string, string | number> | null {
  const fields = targetFields(targetAmount, targetLabel);
  if (fields.target_amount === undefined) {
    return null;
  }
  return { ...versionBody(baseVersion), ...fields };
}

/**
 * Corpo do `POST .../regime`: a guarda otimista de sempre e o único regime declarável.
 *
 * `pricing_regime` é constante de propósito. A fronteira aceita `pre_bid` no schema para
 * poder recusá-lo com código estável (`ESTIMATE_REGIME_IRREVERSIBLE`, ADR-0045 + mão única
 * do plano da F-033); a tela não tem esse ato, então o corpo não tem esse parâmetro. Um
 * argumento aqui daria à jornada a forma de um ato que ela não oferece.
 */
export function regimeBody(
  baseVersion: number,
): Record<string, string | number> {
  return { ...versionBody(baseVersion), pricing_regime: "contracted_demand" };
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
