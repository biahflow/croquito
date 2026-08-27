/**
 * Corpos de requisição da medição `/v1`, derivados dos rascunhos da tela.
 *
 * Espelham o contrato das rotas de `services/api/src/croquito_api/main.py`: campo vazio é
 * omitido em vez de ir como string vazia (`""` seria uma correção do dado, não a ausência
 * de correção), e identidade/horário nunca aparecem — o servidor recusaria
 * (`extra="forbid"`), e mandá-los seria pedir para carimbar decisão em nome de outra
 * pessoa. Toda mutação cita `base_version`: a guarda otimista é da rodada e vale para a
 * cadeia inteira.
 *
 * Módulo puro de propósito: é aqui que a regra "o que sai no corpo" fica testável sem
 * transporte.
 */

import type {
  CodeClosureDraft,
  CodeDecisionDraft,
  CreateRoundDraft,
  PriceAdjustmentDraft,
  TakeoffDecisionBatchDraft,
} from "./api";

/** Corpo mínimo de toda mutação da rodada: só a guarda de concorrência. */
export function versionBody(baseVersion: number): { base_version: number } {
  return { base_version: baseVersion };
}

/**
 * Mesmo padrão que o domínio exige de `WorksiteBulletin` (`WORKSITE_KEY_PATTERN`) e que a
 * rota repete. A chave é IMUTÁVEL na rodada: aceitá-la livre faria a rodada nascer válida
 * e só quebrar na construção do boletim, dezenas de decisões depois.
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
      "número e tem de 3 a 64 caracteres (ex.: praca-sintetica-oeste)."
    );
  }
  return null;
}

/**
 * Corpo do `POST /v1/valuation-rounds`, nas DUAS origens (F-036, ADR-0048).
 *
 * `period_number` é o único inteiro do contrato. Na origem por upload, o catálogo entra pelo
 * `upload_id` do presign, nunca embutido no JSON.
 *
 * Na origem por **orçamento assinado**, a obra e o endereço **não vão no corpo** — e a
 * omissão é a regra, não uma economia: eles vêm do conteúdo aprovado, e o servidor recusa
 * quem os declarar. Aceitá-los abriria a porta para a rodada medir uma praça diferente da
 * que foi orçada, e nenhum número do consolidado é informado por humano.
 */
export function createRoundBody(draft: CreateRoundDraft): Record<string, unknown> {
  const body: Record<string, unknown> = {
    reference_label: draft.referenceLabel.trim(),
    period_number: Number(draft.periodNumber.trim()),
  };
  if (draft.estimateRoundId) {
    body.estimate_round_id = draft.estimateRoundId;
  } else {
    body.worksite_key = draft.worksiteKey.trim();
    body.worksite_name = draft.worksiteName.trim();
    if (draft.catalogUploadId) {
      body.catalog_upload_id = draft.catalogUploadId;
    }
    const address = draft.address?.trim();
    if (address) {
      body.address = address;
    }
  }
  const contractLabel = draft.contractLabel?.trim();
  if (contractLabel) {
    body.contract_label = contractLabel;
  }
  const reajuste = priceAdjustmentBody(draft.priceAdjustment);
  if (reajuste !== null) {
    body.price_adjustment = reajuste;
  }
  return body;
}

/**
 * O reajuste do corpo, ou `null` quando não há declaração (F-039).
 *
 * Campo em branco NÃO viaja, como no resto da jornada: string vazia não é "sem índice", é um
 * índice vazio, e o servidor a recusaria. E os dois mecanismos não se misturam — o que
 * pertence ao outro `kind` fica de fora, porque mandá-lo seria declarar duas coisas fingindo
 * ser uma.
 */
export function priceAdjustmentBody(
  draft: PriceAdjustmentDraft | undefined,
): Record<string, string> | null {
  if (draft === undefined) {
    return null;
  }
  const corpo: Record<string, string> = {
    kind: draft.kind,
    reference_period: draft.referencePeriod.trim(),
  };
  const nota = draft.note?.trim();
  if (nota) {
    corpo.note = nota;
  }
  if (draft.kind === "index_factor") {
    const indice = draft.indexLabel?.trim();
    const fator = draft.factor?.trim();
    if (indice) {
      corpo.index_label = indice;
    }
    if (fator) {
      corpo.factor = fator;
    }
    return corpo;
  }
  const catalogo = draft.catalogUploadId?.trim();
  if (catalogo) {
    corpo.catalog_upload_id = catalogo;
  }
  return corpo;
}

export function takeoffDecisionBody(
  batch: TakeoffDecisionBatchDraft,
): Record<string, unknown> {
  return {
    // A versão-base é do ATO, não do item: ela cita a revisão que a pessoa tinha na tela
    // quando decidiu, e o lote inteiro é gravado contra ela.
    ...versionBody(batch.baseVersion),
    decisions: batch.decisions.map((draft) => {
      const decisao: Record<string, string> = {
        item_id: draft.itemId,
        action: draft.action,
      };
      // Campo opcional em branco NÃO viaja: string vazia não é "sem nota", é uma nota
      // vazia, e o servidor a recusaria por `min_length`.
      const optional: [string, string | undefined][] = [
        ["quantity", draft.quantity],
        ["unit", draft.unit],
        ["note", draft.note],
        ["item_note", draft.itemNote],
      ];
      for (const [key, value] of optional) {
        const cleaned = value?.trim();
        if (cleaned) {
          decisao[key] = cleaned;
        }
      }
      return decisao;
    }),
  };
}

/**
 * Corpo do `POST .../code-assignments/decisions`. A rota exige justificativa na rejeição
 * (é ela que vira o texto do pedido de aditivo) e recusa `code` junto dela; a tela já
 * manda só o que cabe em cada ato.
 */
/**
 * Corpo do `POST .../code-assignments/closures`.
 *
 * Fechar não leva código: a afirmação é sobre o ELEMENTO — "o pacote de serviços dele está
 * completo" —, e não sobre mais um serviço. A nota é opcional, ao contrário da rejeição:
 * fechar é o curso normal do trabalho, e nota obrigatória em ato rotineiro vira ruído.
 */
export function codeClosureBody(
  draft: CodeClosureDraft,
): Record<string, string | number> {
  const body: Record<string, string | number> = {
    ...versionBody(draft.baseVersion),
    item_id: draft.itemId,
  };
  const note = draft.note?.trim();
  if (note) {
    body.note = note;
  }
  return body;
}

export function codeDecisionBody(
  draft: CodeDecisionDraft,
): Record<string, string | number> {
  const body: Record<string, string | number> = {
    ...versionBody(draft.baseVersion),
    item_id: draft.itemId,
    action: draft.action,
  };
  const code = draft.code?.trim();
  if (code && draft.action === "confirm") {
    body.code = code;
  }
  const note = draft.note?.trim();
  if (note) {
    body.note = note;
  }
  return body;
}

/**
 * Termo de busca para recuperar a descrição completa de um código já confirmado, via
 * `GET .../catalog/search`. O servidor tokeniza o código (`lexical_tokens`, NFKD sem
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
