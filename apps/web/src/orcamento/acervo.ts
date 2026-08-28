/**
 * O ACERVO de parcelas de canteiro (F-042), do lado da tela.
 *
 * Das 43 linhas do documento real, 24 não têm origem nenhuma na prancha — canteiro, mão de
 * obra, andaime, transporte e entulho. Elas saem de um punhado de parâmetros da obra que se
 * repetem em toda praça, e hoje são digitadas uma a uma. O acervo é a RECEITA versionada
 * dessas parcelas: ele diz como cada uma se calcula, e nunca traz quantidade pronta.
 *
 * **Nenhum cálculo de quantidade acontece aqui.** A quantidade vem do servidor, que a
 * computa pelo mesmo caminho da matriz (`calc_matrix.py`); reimplementar a conta no
 * navegador criaria uma segunda aritmética, que divergiria da primeira no dia em que uma
 * das duas mudasse. Este módulo transporta strings decimais e ordena passos — ele não
 * multiplica, não soma e não arredonda nada.
 *
 * Módulo PURO de propósito, no molde de `matrix.ts` e `requests.ts`: o estado dos três
 * passos, as exclusões e o que habilita avançar ficam testáveis sem transporte e sem DOM.
 *
 * O que o pacote de design aprovado (revisão 1, 2026-08-28) fixou e este módulo carrega:
 *
 * - **três passos obrigatórios** — acervo, parâmetros, prévia —, e nenhum caminho que
 *   aplique sem passar pela prévia (`podeAplicar` exige a prévia do acervo escolhido);
 * - **parâmetro nasce vazio** (`avancarParaParametros` semeia `""`, nunca um valor);
 * - **remoção é por parcela e reversível** até aplicar (`alternarExclusao`), e remover uma
 *   nunca altera as demais;
 * - **reaplicar substitui as do mesmo acervo e nunca toca as autoradas à mão**
 *   (`substituirParcelasDoAcervo` filtra por `kitId`, não por base).
 */

import { parseDecimalInput } from "./format";
import {
  contributionKey,
  type CalcContributionDraft,
  type OperandDraft,
} from "./matrix";

// --- Espelhos do envelope da API --------------------------------------------
//
// Escrito à mão aqui, como o resto do envelope do orçamento: `@croquito/contracts` gera o
// domínio (`Estimate`, `TakeoffPacket`), não as rotas. Todo decimal atravessa como STRING.

/** De quem é o acervo: da plataforma (receita distribuída) ou do próprio tenant. */
export type SiteSetupKitOrigin = "platform" | "tenant";

/**
 * Um parâmetro de obra que o acervo CITA. `cited_by` é quantas parcelas dependem dele — é
 * o peso do que está sendo declarado, e por isso aparece ao lado do campo.
 */
export type SiteSetupParameter = {
  name: string;
  unit: string | null;
  cited_by: number;
};

/** Um acervo como a rodada o oferece: conjunto versionado de parcelas `STANDALONE`. */
export type SiteSetupKit = {
  kit_id: string;
  name: string;
  kit_version: number;
  origin: SiteSetupKitOrigin;
  source_label: string;
  parcel_count: number;
  parameters: SiteSetupParameter[];
  created_at: string;
};

export type SiteSetupKitListResponse = {
  round_id: string;
  version: number;
  kits: SiteSetupKit[];
};

/** Operando impresso da parcela; `value` é decimal em texto, como o servidor o mandou. */
export type SiteSetupOperand = {
  name: string;
  value: string;
  unit: string | null;
};

/**
 * Uma parcela na pré-visualização, com a CONTA à vista: os operandos nomeados que vão sair
 * impressos na memória de cálculo, e a quantidade que o servidor computou deles.
 */
export type SiteSetupRow = {
  parcel_id: string;
  code: string;
  label: string;
  operands: SiteSetupOperand[];
  quantity: string;
};

/**
 * A pré-visualização: não avança versão e não grava nada. É o controle do risco central da
 * feature — o ganho é não digitar, e o risco é aplicar sem olhar.
 */
export type SiteSetupPreviewResponse = {
  round_id: string;
  version: number;
  kit_id: string;
  kit_version: number;
  rows: SiteSetupRow[];
  excluded_parcel_ids: string[];
};

/**
 * A aplicação — ato humano, que avança a versão da rodada. Mesmo formato da prévia: são as
 * parcelas que nasceram, e é delas que a matriz da tela recebe a proveniência.
 */
export type SiteSetupApplyResponse = SiteSetupPreviewResponse;

// --- Estado dos três passos --------------------------------------------------

/** Os três passos, na ordem em que a orçamentista os encontra. */
export type PassoDoAcervo = "acervo" | "parametros" | "previa";

/**
 * O fluxo aberto. `previa` é a pré-visualização VÁLIDA para o que está declarado agora:
 * mexer em parâmetro a invalida, porque uma prévia calculada com outros números não
 * descreve mais o que seria aplicado.
 */
export type FluxoDoAcervo = {
  passo: PassoDoAcervo;
  /** `""` é "nenhum acervo escolhido"; a escolha é ato, e nada nasce pré-marcado. */
  kitId: string;
  /** O texto digitado por parâmetro citado. Texto, sempre: nada vira `number` aqui. */
  parametros: Record<string, string>;
  /** As parcelas removidas na prévia, por `parcel_id`. Reversível até aplicar. */
  excluidos: readonly string[];
  previa: SiteSetupPreviewResponse | null;
};

/** O fluxo recém-aberto: passo 1, nenhum acervo escolhido, nada declarado. */
export function fluxoInicial(): FluxoDoAcervo {
  return {
    passo: "acervo",
    kitId: "",
    parametros: {},
    excluidos: [],
    previa: null,
  };
}

/**
 * Escolhe o acervo, sem sair do passo 1: escolher e avançar são gestos diferentes, e o
 * cartão escolhido precisa ser lido antes de a pessoa seguir.
 *
 * Trocar de acervo zera o que foi declarado: os parâmetros do acervo anterior podem nem
 * existir no novo, e carregá-los adiante seria pré-preencher campo por dedução.
 */
export function escolherAcervo(fluxo: FluxoDoAcervo, kitId: string): FluxoDoAcervo {
  if (fluxo.kitId === kitId) {
    return fluxo;
  }
  return { ...fluxoInicial(), kitId };
}

/**
 * Passo 2: um campo por parâmetro citado, todos VAZIOS.
 *
 * Decisão 4 do pacote aprovado: o sistema nunca infere um parâmetro. A prancha imprime
 * "ÁREA DE INTERVENÇÃO", e capturá-la é tentador — enquanto não estiver verificado que ela
 * alimenta alguma destas parcelas, o valor é declarado por gente. Nem mesmo os parâmetros
 * da última aplicação semeiam estes campos: o carimbo os MOSTRA, para serem relidos, e
 * relê-los é ato de quem digita.
 */
export function avancarParaParametros(
  fluxo: FluxoDoAcervo,
  kit: SiteSetupKit,
): FluxoDoAcervo {
  const parametros: Record<string, string> = {};
  for (const parametro of kit.parameters) {
    parametros[parametro.name] = fluxo.parametros[parametro.name] ?? "";
  }
  return { ...fluxo, kitId: kit.kit_id, passo: "parametros", parametros, previa: null };
}

/**
 * Declara um parâmetro. Qualquer edição INVALIDA a prévia: aplicar com uma prévia velha
 * mandaria para o servidor números que ninguém viu calculados.
 */
export function declararParametro(
  fluxo: FluxoDoAcervo,
  nome: string,
  valor: string,
): FluxoDoAcervo {
  return {
    ...fluxo,
    parametros: { ...fluxo.parametros, [nome]: valor },
    previa: null,
  };
}

/** Volta ao passo 2 e descarta a prévia: ela vale para os números que a geraram. */
export function voltarParaParametros(fluxo: FluxoDoAcervo): FluxoDoAcervo {
  return { ...fluxo, passo: "parametros", previa: null };
}

/**
 * Recebe a pré-visualização e entra no passo 3. A resposta traz as exclusões que o servidor
 * conhece; a tela adota a lista dele, que é a autoritativa sobre o que foi calculado.
 */
export function receberPrevia(
  fluxo: FluxoDoAcervo,
  previa: SiteSetupPreviewResponse,
): FluxoDoAcervo {
  return {
    ...fluxo,
    passo: "previa",
    previa,
    excluidos: [...previa.excluded_parcel_ids],
  };
}

/**
 * Remove — ou traz de volta — UMA parcela. A removida sai da conta, não da tela: quem
 * desenha a lista continua mostrando a linha, riscada. Nenhuma outra parcela é tocada, e a
 * prévia continua válida para as que ficaram, porque parcela não depende de parcela.
 */
export function alternarExclusao(
  fluxo: FluxoDoAcervo,
  parcelId: string,
): FluxoDoAcervo {
  const excluidos = fluxo.excluidos.includes(parcelId)
    ? fluxo.excluidos.filter((id) => id !== parcelId)
    : [...fluxo.excluidos, parcelId];
  return { ...fluxo, excluidos };
}

/** `true` quando a parcela está removida da aplicação. */
export function estaExcluida(fluxo: FluxoDoAcervo, parcelId: string): boolean {
  return fluxo.excluidos.includes(parcelId);
}

/** Passo 1 → 2: só depende de haver acervo escolhido. */
export function podeAvancarParaParametros(fluxo: FluxoDoAcervo): boolean {
  return fluxo.kitId !== "";
}

/**
 * Passo 2 → 3: pedir a prévia depende de haver acervo escolhido, e só disso.
 *
 * Campo vazio NÃO barra aqui de propósito. Quem recusa por parâmetro faltante é o servidor,
 * que nomeia TODOS os que faltam de uma vez (`SITE_SETUP_PARAMETER_MISSING`) — e ele é
 * quem sabe quais parcelas citam quais parâmetros, dado que o acervo só declara a contagem.
 * Barrar no cliente trocaria a recusa que nomeia por um botão apagado que não explica nada.
 */
export function podePreVisualizar(fluxo: FluxoDoAcervo): boolean {
  return fluxo.kitId !== "";
}

/** As parcelas que vão nascer: as da prévia menos as removidas. */
export function parcelasAplicaveis(fluxo: FluxoDoAcervo): SiteSetupRow[] {
  if (fluxo.previa === null) {
    return [];
  }
  return fluxo.previa.rows.filter((row) => !fluxo.excluidos.includes(row.parcel_id));
}

/**
 * O portão do ato: **não existe caminho que aplique sem passar pela pré-visualização**.
 *
 * Exige estar no passo 3, com uma prévia do acervo escolhido e ao menos uma parcela por
 * nascer. É a leitura em código do risco declarado na feature — "o ganho é justamente não
 * digitar, e o risco é a orçamentista aplicar sem olhar".
 */
export function podeAplicar(fluxo: FluxoDoAcervo): boolean {
  return (
    fluxo.passo === "previa" &&
    fluxo.previa !== null &&
    fluxo.previa.kit_id === fluxo.kitId &&
    parcelasAplicaveis(fluxo).length > 0
  );
}

/**
 * Os parâmetros como o corpo os leva: nome → decimal em TEXTO.
 *
 * Campo vazio é OMITIDO, no padrão de `requests.ts`: `""` não é "declarei vazio", é a
 * ausência da declaração — e é dessa ausência que o servidor lê o faltante. A conversão é
 * de NOTAÇÃO, nunca de valor ("132,21" → "132.21"), pela mesma função da quantidade e do
 * BDI; texto que não é decimal viaja como foi escrito, para o servidor recusá-lo com código
 * estável em vez de a tela mandar um número que ninguém digitou.
 */
export function parametrosDoCorpo(fluxo: FluxoDoAcervo): Record<string, string> {
  const corpo: Record<string, string> = {};
  for (const [nome, valor] of Object.entries(fluxo.parametros)) {
    const escrito = valor.trim();
    if (escrito.length === 0) {
      continue;
    }
    corpo[nome] = parseDecimalInput(escrito) ?? escrito;
  }
  return corpo;
}

// --- O carimbo da última aplicação -------------------------------------------

/**
 * O que a tela guarda da aplicação que acabou de acontecer — o carimbo do estado 07.
 *
 * Ele existe para que reaplicar não seja um salto no escuro: mostra o acervo, a versão, o
 * instante e os parâmetros usados. É registro de LEITURA e nunca semeia campo nenhum.
 */
export type AplicacaoDeAcervo = {
  kitId: string;
  kitName: string;
  kitVersion: number;
  parametros: Record<string, string>;
  parcelas: number;
  appliedAt: string;
};

/** Monta o carimbo a partir do que foi aplicado; `appliedAt` é o instante de quem chama. */
export function registrarAplicacao(
  kit: SiteSetupKit,
  resposta: SiteSetupApplyResponse,
  parametros: Readonly<Record<string, string>>,
  parcelas: number,
  appliedAt: string,
): AplicacaoDeAcervo {
  return {
    kitId: kit.kit_id,
    kitName: kit.name,
    kitVersion: resposta.kit_version,
    parametros: { ...parametros },
    parcelas,
    appliedAt,
  };
}

// --- Da aplicação para a matriz de contribuições -----------------------------

/**
 * As parcelas aplicadas viram contribuições `STANDALONE` da matriz da rodada — a mesma
 * `CalcMatrix` das demais, não um caminho paralelo de cálculo (constraint da feature).
 *
 * Operandos e quantidade vêm do servidor e são COPIADOS como texto. A `recipe` declarada é
 * `declared_product`, que é o que o envelope da prévia permite afirmar: ele traz os
 * operandos e o produto deles, e não a grandeza de origem — escolher `qty_times_months` ou
 * `days_times_hours` a partir do nome de um operando seria inferir a receita pelo rótulo.
 */
export function contribuicoesDoAcervo(
  kit: SiteSetupKit,
  resposta: SiteSetupApplyResponse,
  parcelas: readonly SiteSetupRow[],
): CalcContributionDraft[] {
  return parcelas.map((row) => ({
    // A parcela de canteiro não tem elemento de origem (`STANDALONE` proíbe
    // `source_item_id`): o `parcel_id` entra só como a metade da chave que identifica a
    // linha na tela, e `assembleCalcMatrix` já o descarta ao montar o fio.
    itemId: row.parcel_id,
    code: row.code,
    itemQuantity: null,
    label: row.label,
    basis: "standalone" as const,
    recipe: "declared_product" as const,
    operands: row.operands.map(paraOperandDraft),
    deductions: [],
    dependsOnCode: "",
    note: "",
    kitOrigin: {
      kitId: kit.kit_id,
      kitName: kit.name,
      kitVersion: resposta.kit_version,
      parcelId: row.parcel_id,
    },
    // A quantidade que o SERVIDOR computou, guardada para ser exibida — nunca recomputada,
    // e nunca reenviada: o fio leva os operandos, e o subtotal é do servidor.
    kitQuantity: row.quantity,
  }));
}

/** Operando do fio → linha do rascunho; unidade ausente vira `""`, que é como a tela a lê. */
function paraOperandDraft(operand: SiteSetupOperand): OperandDraft {
  return { name: operand.name, value: operand.value, unit: operand.unit ?? "" };
}

/**
 * Reaplicar substitui as parcelas DAQUELE acervo e não toca em mais nada (decisão 8).
 *
 * O filtro é por `kitId`, não por base: parcela `STANDALONE` autorada à mão tem a mesma
 * base e não pode ser varrida por uma reaplicação — ela é trabalho de gente sobre esta
 * praça. Parcelas de OUTRO acervo também ficam.
 */
export function substituirParcelasDoAcervo(
  contribuicoes: Readonly<Record<string, CalcContributionDraft>>,
  kitId: string,
  novas: readonly CalcContributionDraft[],
): Record<string, CalcContributionDraft> {
  const proximo: Record<string, CalcContributionDraft> = {};
  for (const [chave, draft] of Object.entries(contribuicoes)) {
    if (draft.kitOrigin?.kitId !== kitId) {
      proximo[chave] = draft;
    }
  }
  for (const draft of novas) {
    proximo[contributionKey(draft.itemId, draft.code)] = draft;
  }
  return proximo;
}

/**
 * As parcelas de canteiro da rodada: toda contribuição `STANDALONE`, venha do acervo ou da
 * mão. As duas convivem na mesma lista — o que as distingue é o selo de origem, escrito por
 * extenso (decisão 7).
 */
export function parcelasDeCanteiro(
  contribuicoes: Readonly<Record<string, CalcContributionDraft>>,
): CalcContributionDraft[] {
  return Object.values(contribuicoes).filter((draft) => draft.basis === "standalone");
}
