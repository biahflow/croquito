/**
 * A matriz de contribuições elemento × serviço (ADR-0053, F-038 "decisão 6"), do lado da
 * AUTORIA, na jornada do orçamento.
 *
 * O que a orçamentista monta na etapa de códigos é a `CalcMatrix`: para cada par
 * `(elemento, código)` ela declara COMO aquele elemento contribui para a quantidade
 * daquele serviço — a receita/grandeza, os operandos nomeados, e, quando é o caso, que a
 * parcela é PARCIAL (recorte medido dentro do elemento, com nota e teto) ou DEPENDENTE de
 * outro serviço. No `montar`, a tela junta tudo num objeto `CalcMatrix` e o manda no MESMO
 * corpo do build, ao lado do `bdi_percent`.
 *
 * O formato do JSON é ESPELHO do domínio Python (`packages/valuation/.../calc_matrix.py`):
 * `CalcMatrix → ServiceContributions → CalcContribution → CalcOperand`, com os MESMOS
 * valores de `StrEnum` em minúsculas (`direct_quantity`, `partial`, …) que o servidor
 * valida e que a memória de cálculo já renderizada (`MemoriaDeCalculo`) lê. Ele NÃO está
 * nos contratos gerados (`@croquito/contracts` gera `Estimate`, não a `CalcMatrix` de
 * entrada), então é digitado à mão aqui, num lugar só.
 *
 * Módulo PURO de propósito, no molde de `requests.ts`: montagem e conferências
 * client-side (teto da parcela parcial, nota obrigatória, auto-referência e ciclo) ficam
 * testáveis sem transporte e sem DOM. Elas são UX — o servidor é o portão final e recusa
 * com os mesmos códigos estáveis (`CALC_*`).
 */

import { parseDecimalInput } from "./format";

/** `schema_version` declarada pelo artefato; casada com `CALC_MATRIX_SCHEMA_VERSION` do domínio. */
export const CALC_MATRIX_SCHEMA_VERSION = "1.0.0" as const;

/**
 * De onde vem a parcela que um bloco acrescenta à quantidade do serviço (`ContributionBasis`
 * do domínio). Os valores são os do `StrEnum` — minúsculas —, não os nomes em maiúsculas: é
 * o que o servidor valida e o que `contributionBasisLabel` traduz.
 */
export type ContributionBasis =
  | "full"
  | "derived"
  | "partial"
  | "dependent"
  | "standalone";

/** Receita/grandeza da parcela (`CalcRecipe` do domínio), na forma do `StrEnum`. */
export type CalcRecipe =
  | "direct_quantity"
  | "length_times_width"
  | "perimeter_times_height"
  | "perim_height_minus_openings"
  | "qty_times_months"
  | "days_times_hours"
  | "declared_product";

/** As bases oferecidas na autoria, em ordem de leitura. */
export const CONTRIBUTION_BASES: readonly ContributionBasis[] = [
  "full",
  "derived",
  "partial",
  "dependent",
  "standalone",
];

/** As receitas oferecidas na autoria, em ordem de leitura. */
export const CALC_RECIPES: readonly CalcRecipe[] = [
  "direct_quantity",
  "length_times_width",
  "perimeter_times_height",
  "perim_height_minus_openings",
  "qty_times_months",
  "days_times_hours",
  "declared_product",
];

/** Operando impresso da memória: `name` é dado (chega em português), `value` é decimal texto. */
export type CalcOperand = { name: string; value: string; unit?: string | null };

/**
 * Proveniência de uma parcela nascida de um acervo de canteiro (F-042), no fio.
 *
 * Espelha `CalcContribution.kit_origin` do domínio, que é OPCIONAL: parcela autorada à mão
 * não tem o campo, e a matriz dela continua saindo byte-idêntica à de antes da feature.
 */
export type KitOrigin = { kit_version: string; parcel_id: string };
/* `kit_version` é TEXTO, e não número: o domínio o declara como `str` de 1 a 40
   caracteres (`SiteSetupOrigin`, `models.py`), e um acervo se chama
   "sco-site-setup-v1", não `1`. Mandá-lo como número faz `CalcMatrix.model_validate`
   recusar a matriz inteira no build, com `string_type`. */

/** A célula da matriz: a parcela que UM elemento acrescenta à quantidade de UM serviço. */
export type CalcContribution = {
  source_item_id: string | null;
  label: string;
  basis: ContributionBasis;
  recipe: CalcRecipe;
  operands: CalcOperand[];
  deductions: CalcOperand[];
  depends_on_code: string | null;
  note: string | null;
  /**
   * `undefined` na matriz que a TELA monta (o campo é omitido) e `null` na que ela LÊ de
   * volta: `model_dump` do Pydantic serializa o opcional ausente como `null` em vez de
   * omiti-lo. As duas formas significam "autorada à mão", e quem lê precisa aceitar as duas.
   */
  kit_origin?: KitOrigin | null;
};

/** As parcelas que um serviço (`code`) recebe de todos os elementos que o alimentam. */
export type ServiceContributions = {
  code: string;
  contributions: CalcContribution[];
};

/** A matriz elemento × serviço da prancha: um `ServiceContributions` por código. */
export type CalcMatrix = {
  schema_version: typeof CALC_MATRIX_SCHEMA_VERSION;
  services: ServiceContributions[];
};

// --- Rascunhos de autoria (estado da tela, não do fio) ----------------------

/** Operando na tela: `value` guarda o texto que a orçamentista digitou. */
export type OperandDraft = { name: string; value: string; unit: string };

/**
 * O rascunho da autoria de UMA parcela, enquanto o editor está aberto. `basis` e `recipe`
 * começam VAZIOS de propósito (decisão 4 do pacote — nada nasce pré-marcado): escolher é
 * ato humano, e um default afirmaria a base por quem não a declarou.
 */
export type CalcContributionForm = {
  label: string;
  basis: ContributionBasis | "";
  recipe: CalcRecipe | "";
  operands: OperandDraft[];
  deductions: OperandDraft[];
  dependsOnCode: string;
  note: string;
};

/**
 * A contribuição JÁ salva de um par `(elemento, código)`. `itemQuantity` viaja junto com o
 * rascunho para o teto da parcela `PARTIAL` continuar conferível na montagem, mesmo depois
 * de a lista de pendências ter saído da tela.
 */
export type CalcContributionDraft = {
  itemId: string;
  code: string;
  itemQuantity: string | null;
  label: string;
  basis: ContributionBasis;
  recipe: CalcRecipe;
  operands: OperandDraft[];
  deductions: OperandDraft[];
  dependsOnCode: string;
  note: string;
  /**
   * De qual acervo de canteiro a parcela nasceu (F-042). Ausente é "autorada à mão", e é o
   * caso de toda contribuição autorada no editor. Carrega mais do que o fio (`kitId` e o
   * nome do acervo) porque é a tela que precisa distinguir DOIS acervos aplicados na mesma
   * rodada — reaplicar substitui as do mesmo acervo e não toca nas outras.
   */
  kitOrigin?: KitProvenance;
  /**
   * A quantidade que o SERVIDOR computou para esta parcela, guardada só para ser exibida.
   * Ela não viaja de volta: o fio leva os operandos, e o subtotal é recomputado lá. A tela
   * nunca a recalcula — ela é a string decimal que chegou.
   */
  kitQuantity?: string;
};

/** Proveniência de acervo do lado da TELA; o fio leva só `{kit_version, parcel_id}`. */
export type KitProvenance = {
  /**
   * `""` quando a parcela foi HIDRATADA da matriz gravada: o fio não diz de qual acervo ela
   * nasceu, e afirmar um seria inventar identidade a partir de uma versão. Quem reaplica
   * alcança essas parcelas pela lista de `parcel_id` da resposta, não por este campo.
   */
  kitId: string;
  /** `""` na parcela hidratada, pela mesma razão. */
  kitName: string;
  kitVersion: string;
  parcelId: string;
};

// --- Códigos de recusa client-side ------------------------------------------
//
// Os dois primeiros são ESPELHO dos códigos que o servidor devolve em `422` (a validação
// final é dele); os demais são guardas locais que evitam a viagem de um rascunho incompleto.

export const CALC_PARTIAL_EXCEEDS_ITEM = "CALC_PARTIAL_EXCEEDS_ITEM";
export const CALC_PARTIAL_NOTE_REQUIRED = "CALC_PARTIAL_NOTE_REQUIRED";
export const CALC_MATRIX_SELF_DEPENDENCY = "CALC_MATRIX_SELF_DEPENDENCY";
export const CALC_MATRIX_DEPENDENCY_CYCLE = "CALC_MATRIX_DEPENDENCY_CYCLE";
export const CALC_CONTRIBUTION_DEPENDENT_WITHOUT_CODE =
  "CALC_CONTRIBUTION_DEPENDENT_WITHOUT_CODE";
export const CALC_BASIS_REQUIRED = "CALC_BASIS_REQUIRED";
export const CALC_RECIPE_REQUIRED = "CALC_RECIPE_REQUIRED";
export const CALC_LABEL_REQUIRED = "CALC_LABEL_REQUIRED";
export const CALC_OPERAND_REQUIRED = "CALC_OPERAND_REQUIRED";
export const CALC_OPERAND_INVALID = "CALC_OPERAND_INVALID";

/** A chave estável de um par `(elemento, código)` no mapa de contribuições da tela. */
export function contributionKey(itemId: string, code: string): string {
  return `${itemId}::${code}`;
}

/** Um operando vazio, para o editor começar com uma linha a preencher. */
export function emptyOperand(): OperandDraft {
  return { name: "", value: "", unit: "" };
}

/**
 * O rascunho inicial de uma parcela nova: `basis`/`recipe` vazios, uma linha de operando, e
 * o `label` semeado pelo rótulo do elemento — texto editável, não uma decisão presumida.
 */
export function emptyContributionForm(label: string): CalcContributionForm {
  return {
    label,
    basis: "",
    recipe: "",
    operands: [emptyOperand()],
    deductions: [],
    dependsOnCode: "",
    note: "",
  };
}

/** Reidrata o editor a partir de uma contribuição já salva, para reabrir e corrigir. */
export function formFromDraft(draft: CalcContributionDraft): CalcContributionForm {
  return {
    label: draft.label,
    basis: draft.basis,
    recipe: draft.recipe,
    operands: draft.operands.length > 0 ? [...draft.operands] : [emptyOperand()],
    deductions: [...draft.deductions],
    dependsOnCode: draft.dependsOnCode,
    note: draft.note,
  };
}

/** Converte um texto decimal digitado em número para a conferência de UX; `NaN` se não for. */
function decimalToNumber(value: string): number {
  const normalized = parseDecimalInput(value);
  return normalized === null ? Number.NaN : Number(normalized);
}

/**
 * O subtotal recomputado de uma parcela — produto dos operandos menos as deduções — como
 * NÚMERO, só para a conferência do teto na tela. No fio a parcela NÃO carrega subtotal: o
 * servidor o recomputa dos operandos. `NaN` quando algum valor não é decimal.
 */
export function contributionSubtotal(
  operands: readonly OperandDraft[],
  deductions: readonly OperandDraft[],
): number {
  const product = operands.reduce(
    (acc, operand) => acc * decimalToNumber(operand.value),
    1,
  );
  const deducted = deductions.reduce(
    (acc, operand) => acc + decimalToNumber(operand.value),
    0,
  );
  return product - deducted;
}

/** Operandos preenchidos: linha sem nome nem valor é ruído da digitação, não parcela. */
function preenchidos(operands: readonly OperandDraft[]): OperandDraft[] {
  return operands.filter(
    (operand) => operand.name.trim().length > 0 || operand.value.trim().length > 0,
  );
}

/**
 * Motivo de um rascunho de parcela não poder ser salvo — ou `null` quando ele serve.
 *
 * As conferências são as que o par sabe sozinho (o teto de `PARTIAL` depende do elemento,
 * e por isso `itemQuantity` entra), na MESMA ordem em que a orçamentista as encontra. O
 * servidor continua sendo o portão final; isto evita a viagem e explica o que falta.
 */
export function contributionFormError(
  form: CalcContributionForm,
  itemQuantity: string | null,
): { code: string } | null {
  if (form.label.trim().length === 0) {
    return { code: CALC_LABEL_REQUIRED };
  }
  if (form.basis === "") {
    return { code: CALC_BASIS_REQUIRED };
  }
  if (form.recipe === "") {
    return { code: CALC_RECIPE_REQUIRED };
  }
  const operandos = preenchidos(form.operands);
  if (operandos.length === 0) {
    return { code: CALC_OPERAND_REQUIRED };
  }
  for (const operand of operandos) {
    if (operand.name.trim().length === 0 || parseDecimalInput(operand.value) === null) {
      return { code: CALC_OPERAND_INVALID };
    }
  }
  for (const deduction of preenchidos(form.deductions)) {
    if (deduction.name.trim().length === 0 || parseDecimalInput(deduction.value) === null) {
      return { code: CALC_OPERAND_INVALID };
    }
  }
  if (form.basis === "dependent" && form.dependsOnCode.trim().length === 0) {
    return { code: CALC_CONTRIBUTION_DEPENDENT_WITHOUT_CODE };
  }
  if (form.basis === "partial") {
    if (form.note.trim().length === 0) {
      return { code: CALC_PARTIAL_NOTE_REQUIRED };
    }
    if (itemQuantity !== null) {
      const cap = Number(parseDecimalInput(itemQuantity) ?? "NaN");
      const subtotal = contributionSubtotal(operandos, preenchidos(form.deductions));
      // Igual ao teto é lícito (os 170 dentro dos 418,12); só ACIMA dele é recusa. A folga
      // de 1e-9 absorve o ruído do produto em `number` — a conferência exata é do servidor.
      if (Number.isFinite(cap) && subtotal > cap + 1e-9) {
        return { code: CALC_PARTIAL_EXCEEDS_ITEM };
      }
    }
  }
  return null;
}

/** Normaliza um operando de tela para o fio: valor vira decimal canônico, unidade some se vazia. */
function toOperand(operand: OperandDraft): CalcOperand {
  const value = parseDecimalInput(operand.value) ?? operand.value.trim();
  const unit = operand.unit.trim();
  return unit.length > 0
    ? { name: operand.name.trim(), value, unit }
    : { name: operand.name.trim(), value };
}

/**
 * Salva um rascunho: valida-o e, se serve, devolve o `CalcContributionDraft` normalizado.
 * Rascunho recusado devolve o código da recusa, para a tela dizer o que falta.
 */
export function buildContributionDraft(
  itemId: string,
  code: string,
  itemQuantity: string | null,
  form: CalcContributionForm,
): { draft: CalcContributionDraft } | { code: string } {
  const erro = contributionFormError(form, itemQuantity);
  if (erro !== null) {
    return erro;
  }
  // Passou pela validação: `basis` e `recipe` não são mais vazios.
  const basis = form.basis as ContributionBasis;
  const recipe = form.recipe as CalcRecipe;
  return {
    draft: {
      itemId,
      code,
      itemQuantity,
      label: form.label.trim(),
      basis,
      recipe,
      operands: preenchidos(form.operands),
      deductions: preenchidos(form.deductions),
      dependsOnCode: basis === "dependent" ? form.dependsOnCode.trim() : "",
      note: form.note.trim(),
    },
  };
}

/** A contribuição de fio a partir do rascunho salvo, com os vínculos que a base implica. */
function toContribution(draft: CalcContributionDraft): CalcContribution {
  const source_item_id =
    draft.basis === "standalone" || draft.basis === "dependent" ? null : draft.itemId;
  const depends_on_code =
    draft.basis === "dependent" && draft.dependsOnCode.length > 0
      ? draft.dependsOnCode
      : null;
  const note = draft.note.trim();
  const contribution: CalcContribution = {
    source_item_id,
    label: draft.label,
    basis: draft.basis,
    recipe: draft.recipe,
    operands: draft.operands.map(toOperand),
    deductions: draft.deductions.map(toOperand),
    depends_on_code,
    note: note.length > 0 ? note : null,
  };
  // A proveniência só entra quando existe: parcela autorada à mão continua saindo sem a
  // chave, e a matriz de quem não usa acervo é a mesma de antes da F-042.
  if (draft.kitOrigin !== undefined) {
    contribution.kit_origin = {
      kit_version: draft.kitOrigin.kitVersion,
      parcel_id: draft.kitOrigin.parcelId,
    };
  }
  return contribution;
}

/**
 * Junta as contribuições salvas numa `CalcMatrix`, agrupadas por serviço (`code`) na ordem
 * de primeira aparição. Sem contribuição nenhuma devolve `null` — é o regime legado (código
 * único por item), que o servidor monta byte-idêntico ao de hoje.
 */
export function assembleCalcMatrix(
  drafts: readonly CalcContributionDraft[],
): CalcMatrix | null {
  if (drafts.length === 0) {
    return null;
  }
  const byCode = new Map<string, CalcContribution[]>();
  for (const draft of drafts) {
    const bucket = byCode.get(draft.code);
    const contribution = toContribution(draft);
    if (bucket === undefined) {
      byCode.set(draft.code, [contribution]);
    } else {
      bucket.push(contribution);
    }
  }
  const services: ServiceContributions[] = [];
  for (const [code, contributions] of byCode) {
    services.push({ code, contributions });
  }
  return { schema_version: CALC_MATRIX_SCHEMA_VERSION, services };
}

// --- A volta: da matriz GRAVADA para o rascunho da tela ---------------------
//
// A matriz tinha dois donos. O `apply` do acervo (F-042) a grava no servidor; a tela monta
// o rascunho em memória e manda a matriz INTEIRA no build. Enquanto a sessão vive, os dois
// concordam — mas depois de um recarregamento a tela perde o rascunho, e montar o orçamento
// apagava do banco o que estava gravado. A raiz é anterior ao acervo (a matriz nunca foi
// lida de volta desde a F-038, e o mesmo valia para as contribuições autoradas à mão); o
// acervo, que grava vinte e quatro parcelas de uma vez, a tornou grave.
//
// Decisão do dono, 2026-08-28: a tela HIDRATA o rascunho a partir do que está gravado.

/**
 * O elemento de origem SINTÉTICO de uma contribuição que o fio não amarra a elemento
 * nenhum: `STANDALONE` e `DEPENDENT` viajam com `source_item_id: null` por regra do
 * domínio, e a chave `(elemento, código)` da tela precisa de alguma metade estável.
 *
 * Ele é chave de TELA e nunca volta ao fio: `toContribution` devolve `null` para essas duas
 * bases, então a matriz remontada sai igual à que foi lida.
 */
const ELEMENTO_SINTETICO = "sem-elemento";

/** Operando do fio → linha do rascunho; unidade ausente é `""`, que é como a tela a lê. */
function toOperandDraft(operand: CalcOperand): OperandDraft {
  return { name: operand.name, value: operand.value, unit: operand.unit ?? "" };
}

/**
 * A inversa de `assembleCalcMatrix`: a matriz gravada volta a ser rascunho da tela.
 *
 * O espelho é à mão, como o resto deste arquivo, e a volta perde exatamente três coisas
 * que o fio não carrega — nenhuma delas fabricada aqui:
 *
 * - `itemQuantity` (o teto da parcela `PARTIAL`) não existe na matriz; ele volta `null`, e
 *   quem reabre o editor recebe o teto do elemento de novo (`abrirAutoria`), que é a fonte;
 * - a IDENTIDADE do acervo (`kitId`/`kitName`) não está no fio — ele leva só
 *   `{kit_version, parcel_id}` —, então a proveniência reconstruída tem `kitId` vazio. O
 *   selo continua dizendo "do acervo v1", que é o que a matriz afirma;
 * - o elemento de origem de `STANDALONE`/`DEPENDENT`, que o domínio proíbe no fio.
 *
 * `null` (rodada sem matriz gravada) devolve rascunho vazio: é o regime legado, e ele não
 * pode virar contribuição nenhuma.
 */
export function disassembleCalcMatrix(
  matrix: CalcMatrix | null,
): CalcContributionDraft[] {
  if (matrix === null) {
    return [];
  }
  const drafts: CalcContributionDraft[] = [];
  for (const service of matrix.services) {
    service.contributions.forEach((contribution, index) => {
      const itemId =
        contribution.source_item_id ??
        contribution.kit_origin?.parcel_id ??
        `${ELEMENTO_SINTETICO}:${service.code}:${index}`;
      const draft: CalcContributionDraft = {
        itemId,
        code: service.code,
        itemQuantity: null,
        label: contribution.label,
        basis: contribution.basis,
        recipe: contribution.recipe,
        operands: contribution.operands.map(toOperandDraft),
        deductions: contribution.deductions.map(toOperandDraft),
        dependsOnCode: contribution.depends_on_code ?? "",
        note: contribution.note ?? "",
      };
      // A parcela autorada à mão chega com `kit_origin: null`, e não com o campo ausente:
      // `model_dump` do Pydantic serializa o opcional como `null`. Testar só contra
      // `undefined` entrava aqui com `null` e derrubava a jornada inteira ao ler a matriz
      // gravada — tela em branco, não mensagem. Achado pela evidência de navegador da T6
      // (2026-09-04), numa rodada com uma parcela de acervo e uma autorada à mão.
      const kitOrigin = contribution.kit_origin;
      if (kitOrigin !== undefined && kitOrigin !== null) {
        draft.kitOrigin = {
          kitId: "",
          kitName: "",
          kitVersion: kitOrigin.kit_version,
          parcelId: kitOrigin.parcel_id,
        };
      }
      drafts.push(draft);
    });
  }
  return drafts;
}

/**
 * O rascunho da matriz E a rodada a que ele pertence, juntos num estado só.
 *
 * A rodada anda no mesmo lugar que os rascunhos de propósito: com a hidratação, um rascunho
 * que sobrevive à troca de rodada deixa de ser sujeira de tela e vira contribuição de uma
 * praça aplicada a outra — corrupção silenciosa, que ninguém lê como erro.
 */
export type MatrixDraftState = {
  /** `null` é "nenhuma rodada aberta". */
  roundId: string | null;
  /** As contribuições salvas, indexadas por `contributionKey`. */
  drafts: Record<string, CalcContributionDraft>;
};

/** O rascunho de uma rodada recém-aberta: vazio, sempre. */
export function emptyMatrixDraft(roundId: string | null): MatrixDraftState {
  return { roundId, drafts: {} };
}

/**
 * Abre uma rodada no rascunho. Rodada DIFERENTE zera tudo — nada da anterior atravessa —, e
 * a mesma rodada devolve o estado intacto, para reabrir a mesma rodada não custar o que já
 * foi autorado.
 */
export function openMatrixDraft(
  state: MatrixDraftState,
  roundId: string | null,
): MatrixDraftState {
  if (state.roundId === roundId) {
    return state;
  }
  return emptyMatrixDraft(roundId);
}

/**
 * Hidrata o rascunho com a matriz GRAVADA da rodada `roundId`.
 *
 * Duas guardas, as duas por causa do mesmo risco:
 *
 * - leitura de OUTRA rodada é descartada. A leitura é assíncrona, e trocar de rodada com
 *   ela em voo faria a matriz da anterior pousar sobre a nova;
 * - o que a SESSÃO autorou vence o gravado na mesma chave. O gravado é o ponto de partida,
 *   não uma correção do que a pessoa acabou de escrever.
 */
export function hydrateMatrixDraft(
  state: MatrixDraftState,
  roundId: string,
  stored: CalcMatrix | null,
): MatrixDraftState {
  if (state.roundId !== roundId) {
    return state;
  }
  const drafts: Record<string, CalcContributionDraft> = {};
  for (const draft of disassembleCalcMatrix(stored)) {
    drafts[contributionKey(draft.itemId, draft.code)] = draft;
  }
  return { roundId, drafts: { ...drafts, ...state.drafts } };
}

/** Grafo `code → {códigos de que ele depende}`, só das parcelas `DEPENDENT`. */
function dependencyEdges(
  services: readonly ServiceContributions[],
): Map<string, Set<string>> {
  const edges = new Map<string, Set<string>>();
  for (const service of services) {
    const targets = edges.get(service.code) ?? new Set<string>();
    edges.set(service.code, targets);
    for (const contribution of service.contributions) {
      if (contribution.basis === "dependent" && contribution.depends_on_code) {
        targets.add(contribution.depends_on_code);
      }
    }
  }
  return edges;
}

/**
 * A ordem em que os serviços podem ser calculados (Kahn), ou `null` quando há ciclo. O
 * serviço que alimenta outro vem antes; o empate segue a ordem de aparição. Arestas para
 * códigos fora da matriz são ignoradas — é o build que conhece o boletim. Espelha
 * `_topological_order` do domínio.
 */
export function topologicalOrder(
  services: readonly ServiceContributions[],
): string[] | null {
  const order = services.map((service) => service.code);
  const known = new Set(order);
  const rawEdges = dependencyEdges(services);
  const edges = new Map<string, Set<string>>();
  for (const [code, targets] of rawEdges) {
    edges.set(code, new Set([...targets].filter((target) => known.has(target))));
  }
  const inDegree = new Map<string, number>();
  for (const code of order) {
    inDegree.set(code, edges.get(code)?.size ?? 0);
  }
  const ready = order.filter((code) => (inDegree.get(code) ?? 0) === 0);
  const resolved: string[] = [];
  while (ready.length > 0) {
    const code = ready.shift() as string;
    resolved.push(code);
    for (const dependent of order) {
      if (edges.get(dependent)?.has(code)) {
        const next = (inDegree.get(dependent) ?? 0) - 1;
        inDegree.set(dependent, next);
        if (next === 0) {
          ready.push(dependent);
        }
      }
    }
  }
  return resolved.length === order.length ? resolved : null;
}

/**
 * Recusa de ordem da matriz montada: auto-referência e ciclo, escritos por CÓDIGO estável
 * (nunca escondidos atrás de interação — decisão 5). Espelha os validadores de `CalcMatrix`.
 * `null` quando a matriz tem ordem de cálculo.
 */
export function matrixOrderError(
  matrix: CalcMatrix,
): { code: string; codes: string[] } | null {
  const edges = dependencyEdges(matrix.services);
  const selfReferencing = [...edges.entries()]
    .filter(([code, targets]) => targets.has(code))
    .map(([code]) => code)
    .sort();
  if (selfReferencing.length > 0) {
    return { code: CALC_MATRIX_SELF_DEPENDENCY, codes: selfReferencing };
  }
  if (topologicalOrder(matrix.services) === null) {
    return {
      code: CALC_MATRIX_DEPENDENCY_CYCLE,
      codes: matrix.services.map((service) => service.code).sort(),
    };
  }
  return null;
}
