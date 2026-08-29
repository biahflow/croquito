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
  AmendmentDraft,
  CodeClosureDraft,
  CodeRevocationDaPracaDraft,
  CodeDecisionDraft,
  CreateRoundDraft,
  IdentityLinkDeclarationDraft,
  IdentityLinkDraft,
  DivergenceResolutionDraft,
  PriceAdjustmentDraft,
  SceneLinkDraft,
  TakeoffDecisionBatchDraft,
} from "./api";

/** Corpo mínimo de toda mutação da rodada: só a guarda de concorrência. */
export function versionBody(baseVersion: number): { base_version: number } {
  return { base_version: baseVersion };
}

/**
 * A folha da praça no corpo, quando há folha a nomear (F-046 T4c/T4d).
 *
 * Ausência **não viaja**: `plate_id` omitido é a PRIMEIRA folha, e é essa omissão que
 * mantém o corpo da rodada de uma prancha byte-idêntico ao de antes da praça (ADR-0057,
 * decisão 8). Mandar `null` seria declarar uma folha nula, que não é a mesma afirmação.
 */
export function plateBody(plateId: string | undefined): { plate_id?: string } {
  const plate = plateId?.trim();
  return plate ? { plate_id: plate } : {};
}

/**
 * Mesmo padrão que o domínio exige de `WorksiteBulletin` (`WORKSITE_KEY_PATTERN`) e que a
 * rota repete. A chave é IMUTÁVEL na rodada: aceitá-la livre faria a rodada nascer válida
 * e só quebrar na construção do boletim, dezenas de decisões depois.
 */
export const WORKSITE_KEY_PATTERN = /^[a-z0-9][a-z0-9-]{2,63}$/;

/**
 * Quantos caracteres o nome da obra tem dentro do nome das abas BM e MEMÓRIA da planilha.
 *
 * É o `worksite_sheet_budget` do template padrão (`packages/valuation/template.py`): 31 do
 * formato menos os 8 de `MEMÓRIA `, que é a mais longa das duas. Duplicado aqui pelo mesmo
 * motivo de `WORKSITE_KEY_PATTERN` — a tela precisa DIZER o teto antes de o nome ser
 * aceito, e quem o aplica continua sendo o servidor, que recusa a abertura da rodada com
 * `WORKSITE_NAME_DOES_NOT_FIT_SHEET` e devolve o teto no envelope.
 *
 * A tela não valida o nome, e a diferença é deliberada: um nome maior que o teto ainda
 * pode caber pelos degraus declarados (partículas fora, palavras do meio abreviadas), e
 * uma contagem de caracteres no navegador recusaria nomes que o domínio aceita.
 */
export const WORKSITE_SHEET_NAME_BUDGET = 23;

/** O teto do nome da obra em língua de obra, mostrado ANTES de o nome ser aceito. */
export const DICA_NOME_DA_OBRA =
  `vira o nome das abas BM e MEMÓRIA da planilha, que reservam ` +
  `${WORKSITE_SHEET_NAME_BUDGET} caracteres: nome maior é encurtado por degraus e, se não ` +
  `couber nem assim, a rodada é recusada na abertura`;

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
  } else if (draft.previousRoundId) {
    // A medição seguinte (F-040): obra, catálogo e contratado vêm da rodada anterior, e por
    // isso a obra também não vai no corpo — mesma regra da origem assinada.
    body.previous_round_id = draft.previousRoundId;
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
  const reRa = amendmentBody(draft.amendment);
  if (reRa !== null) {
    body.amendment = reRa;
  }
  return body;
}

/**
 * A RE-RA do corpo, ou `null` quando não há declaração (F-040).
 *
 * Linha em branco não viaja: código vazio não é "sem código". O item novo NÃO informa preço
 * — o servidor o materializa do catálogo contratual (ADR-0056, decisão 7). `declared_by` e
 * `declared_at` também não vão daqui: são do servidor, como no reajuste.
 */
export function amendmentBody(
  draft: AmendmentDraft | undefined,
): Record<string, unknown> | null {
  if (draft === undefined) {
    return null;
  }
  const lines = draft.lines
    .filter((line) => line.code.trim().length > 0 && line.quantityDelta.trim().length > 0)
    .map((line) => {
      const corpo: Record<string, unknown> = {
        code: line.code.trim(),
        quantity_delta: line.quantityDelta.trim(),
      };
      if (line.isNewItem) {
        corpo.is_new_item = true;
      }
      const nota = line.note?.trim();
      if (nota) {
        corpo.note = nota;
      }
      return corpo;
    });
  if (lines.length === 0) {
    return null;
  }
  const corpo: Record<string, unknown> = {
    label: draft.label.trim(),
    reference_period: draft.referencePeriod.trim(),
    lines,
  };
  const nota = draft.note?.trim();
  if (nota) {
    corpo.note = nota;
  }
  return corpo;
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
    // A folha também é do ATO (F-046 T4c): um lote é a legenda de UMA prancha. Ausente
    // NÃO viaja — a omissão é a primeira folha, e é ela que mantém o corpo da rodada de
    // uma prancha idêntico ao de antes da praça.
    ...plateBody(batch.plateId),
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
    ...plateBody(draft.plateId),
    item_id: draft.itemId,
  };
  const note = draft.note?.trim();
  if (note) {
    body.note = note;
  }
  return body;
}

/**
 * O corpo de desfazer um código confirmado (F-045).
 *
 * A nota é OBRIGATÓRIA aqui — ao contrário do fechamento, onde é opcional —, e por isso entra
 * sem o `if` que o fechamento tem: um corpo sem motivo é recusado pelo servidor, e omiti-lo
 * aqui esconderia a recusa em vez de provocá-la cedo.
 */
export function codeRevocationBody(
  draft: CodeRevocationDaPracaDraft,
): Record<string, string | number> {
  return {
    ...versionBody(draft.baseVersion),
    ...plateBody(draft.plateId),
    item_id: draft.itemId,
    code: draft.code,
    note: draft.note.trim(),
  };
}

/**
 * Corpo do `POST .../scene-link`: o elo declarado com o croqui aprovado (F-047 T4b).
 *
 * Só o job viaja. `scene_revision_id`, `export_id` e o digest do DXF são DESCOBERTOS pelo
 * servidor a partir do export publicado mais recente daquele job, e `declared_by`/
 * `declared_at` são carimbo dele — mandar qualquer um deles daqui seria pedir para
 * carimbar em nome de outra pessoa, e `extra="forbid"` recusaria o corpo inteiro.
 */
export function sceneLinkBody(
  draft: SceneLinkDraft,
): Record<string, string | number> {
  return {
    ...versionBody(draft.baseVersion),
    job_id: draft.jobId.trim(),
  };
}

/**
 * Corpo do `POST .../takeoff/divergences/resolutions` (F-047 T5).
 *
 * `choice` é `scene` ou `legend`, e não há terceiro valor: uma terceira quantidade digitada
 * aqui seria a redigitação que a feature existe para eliminar (ADR-0058, decisão 6). O
 * motivo é opcional no contrato da rota e vai só quando escrito — string vazia não é
 * "sem motivo", é um motivo vazio, e o servidor a recusaria por `min_length`.
 */
export function divergenceResolutionBody(
  draft: DivergenceResolutionDraft,
): Record<string, string | number> {
  const body: Record<string, string | number> = {
    ...versionBody(draft.baseVersion),
    item_id: draft.itemId,
    choice: draft.choice,
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
    ...plateBody(draft.plateId),
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
 * O corpo de promover páginas a folhas da praça em lote (F-046 T4).
 *
 * As páginas viajam **na ordem escolhida e sem repetição**, e a lista nunca é preenchida por
 * omissão: promover todas as páginas de um documento foi recusado nominalmente no pacote de
 * design aprovado, e um corpo montado "por padrão" aqui seria essa recusa contornada pelo
 * cliente. Lote vazio é recusa do servidor (`ROUND_PLATE_PAGES_REQUIRED`), e é ele quem a diz.
 */
export function appendPlatesBody(
  uploadId: string,
  pageNumbers: readonly number[],
  baseVersion: number,
): Record<string, unknown> {
  return {
    ...versionBody(baseVersion),
    upload_id: uploadId,
    page_numbers: [...new Set(pageNumbers)],
  };
}

/**
 * O corpo do lote de extração (F-046 T4): quais folhas vão para a chamada paga.
 *
 * Cada folha é uma chamada paga; a lista é a autorização, e por isso ela sai daqui
 * exatamente como foi marcada, sem folha acrescentada por conveniência.
 */
export function platesExtractionBody(
  plateIds: readonly string[],
  baseVersion: number,
): Record<string, unknown> {
  return {
    ...versionBody(baseVersion),
    plate_ids: [...new Set(plateIds)],
  };
}

/**
 * O corpo da PRÉVIA da fusão (F-046 T4c): só os dois endereços.
 *
 * Sem `base_version` — nada é gravado e a versão da rodada não anda — e **sem nota**: a
 * justificativa é do ato, não da simulação. Mandá-la aqui faria a prévia parecer meio
 * ato, e o servidor recusaria o campo a mais (`extra="forbid"`).
 */
export function identityLinkPreviewBody(
  draft: IdentityLinkDraft,
): Record<string, unknown> {
  return {
    kept: { ...draft.kept },
    discarded: { ...draft.discarded },
  };
}

/**
 * O corpo da DECLARAÇÃO de identidade (F-046 T1).
 *
 * A prévia mais o que só o ato tem: `base_version` e a nota obrigatória. Autor e instante
 * NÃO viajam — vêm do JWT e do relógio do servidor, como em toda decisão desta cadeia; um
 * corpo que os carimbasse deixaria o cliente escolher a procedência do próprio ato.
 */
export function identityLinkBody(
  draft: IdentityLinkDeclarationDraft,
): Record<string, unknown> {
  return {
    ...versionBody(draft.baseVersion),
    ...identityLinkPreviewBody(draft),
    note: draft.note.trim(),
  };
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
