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
 *
 * Emenda de 2026-08-28 à decisão 5 do pacote, aprovada pelo dono: a recusa por parâmetro
 * faltante continua sendo falha FECHADA — nada é materializado pela metade —, mas ela
 * deixou de acontecer ANTES da prévia. A prévia MARCA a parcela que não pode nascer
 * (`parcelaBloqueada`) e o portão do ato passa a exigir que nenhuma bloqueada continue na
 * aplicação (`podeAplicar`). É o que abre a saída que a própria copy da recusa prometia —
 * "remova na pré-visualização as parcelas que os citam" — e que não existia, porque a
 * recusa vinha antes de haver pré-visualização onde remover.
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

/**
 * Operando impresso da parcela; `value` é decimal em texto, como o servidor o mandou.
 *
 * `value: null` é o operando que NÃO pôde ser calculado — o parâmetro que ele cita não foi
 * declarado —, e `parameter` diz de qual parâmetro de obra ele sai. Os dois juntos são o
 * que permite a linha bloqueada dizer o que falta em vez de mostrar uma conta pela metade.
 */
export type SiteSetupOperand = {
  name: string;
  value: string | null;
  unit: string | null;
  parameter: string | null;
};

/**
 * Uma parcela na pré-visualização, com a CONTA à vista: os operandos nomeados que vão sair
 * impressos na memória de cálculo, e a quantidade que o servidor computou deles.
 *
 * A prévia MARCA em vez de recusar: a parcela que não pode nascer volta com
 * `missing_parameters` (e então sem quantidade, porque a conta não fecha) ou com
 * `code_absent` (e então COM quantidade: a conta fecha, o que falta é o código no catálogo
 * desta rodada). As outras continuam calculadas. Era a recusa antecipada que fechava a
 * saída prometida pela própria copy — "remova na pré-visualização as parcelas que os
 * citam" —, porque a prévia nem existia.
 */
export type SiteSetupRow = {
  parcel_id: string;
  code: string;
  label: string;
  operands: SiteSetupOperand[];
  /** `null` é AUSÊNCIA de quantidade — a parcela não pôde ser calculada —, nunca zero. */
  quantity: string | null;
  /** Os parâmetros de obra que ESTA parcela cita e que não foram declarados. */
  missing_parameters: string[];
  /** `true` quando o código da parcela não existe no catálogo desta rodada. */
  code_absent: boolean;
};

/**
 * A pré-visualização: não avança versão e não grava nada. É o controle do risco central da
 * feature — o ganho é não digitar, e o risco é aplicar sem olhar.
 *
 * `rows` traz linha só para as parcelas NÃO excluídas no pedido, e `excluded_parcel_ids`
 * ecoa o que foi pedido. É por isso que a tela pede a prévia sem exclusão nenhuma
 * (`pedidoDaPrevia`) e remove localmente: uma linha que sumisse da resposta não teria de
 * onde voltar, e o desenho exige que a removida continue visível e riscada.
 *
 * `blocked_parcel_ids` é a lista do SERVIDOR sobre o que não pode nascer, e ela já ignora
 * as excluídas. A tela não a substitui pelo que lê das linhas: as duas se somam, para que
 * um bloqueio que o servidor conheça e a linha não nomeie continue bloqueando (falha
 * fechada) em vez de virar uma parcela aplicada em silêncio.
 */
export type SiteSetupPreviewResponse = {
  round_id: string;
  version: number;
  kit_id: string;
  kit_version: number;
  rows: SiteSetupRow[];
  excluded_parcel_ids: string[];
  blocked_parcel_ids: string[];
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
 * O pedido da pré-visualização a partir do fluxo — **sem exclusão nenhuma, sempre**.
 *
 * A prévia devolve linha só para as parcelas NÃO excluídas (contrato da rota, confirmado
 * pela T4 em 2026-08-28): pedir a prévia citando as removidas as faria SUMIR da resposta, e
 * o pacote de design exige que a parcela removida continue visível e riscada, com "Trazer
 * de volta". Nenhuma rota devolve as parcelas cruas do acervo fora da prévia, então uma
 * linha que sumisse não teria de onde voltar.
 *
 * A remoção é, portanto, LOCAL: ela marca o `parcel_id` no estado e só viaja no `apply`.
 */
export function pedidoDaPrevia(fluxo: FluxoDoAcervo): {
  kitId: string;
  parameters: Record<string, string>;
  excludedParcelIds: readonly string[];
} {
  return {
    kitId: fluxo.kitId,
    parameters: parametrosDoCorpo(fluxo),
    excludedParcelIds: [],
  };
}

/**
 * Recebe a pré-visualização e entra no passo 3.
 *
 * As marcações LOCAIS de remoção sobrevivem a uma prévia nova: a prévia é pedida sem
 * exclusões (`pedidoDaPrevia`), então a lista que a resposta ecoa vem vazia — adotá-la
 * apagaria o que a pessoa removeu ao trocar um parâmetro e pedir a conta de novo. O que o
 * servidor declarar excluído entra por cima, porque sobre isso ele é a autoridade.
 */
export function receberPrevia(
  fluxo: FluxoDoAcervo,
  previa: SiteSetupPreviewResponse,
): FluxoDoAcervo {
  const excluidos = [...fluxo.excluidos];
  for (const parcelId of previa.excluded_parcel_ids) {
    if (!excluidos.includes(parcelId)) {
      excluidos.push(parcelId);
    }
  }
  return { ...fluxo, passo: "previa", previa, excluidos };
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
 * Campo vazio NÃO barra aqui de propósito, e agora menos ainda: a prévia com parâmetro
 * faltante é justamente onde se lê QUAIS parcelas o citam — o acervo só declara a contagem,
 * e quem sabe é o servidor. Barrar no cliente esconderia essa leitura atrás de um botão
 * apagado que não explica nada.
 */
export function podePreVisualizar(fluxo: FluxoDoAcervo): boolean {
  return fluxo.kitId !== "";
}

/**
 * `true` quando a parcela NÃO pode nascer nesta rodada: falta parâmetro que ela cita, o
 * código dela não está no catálogo, ou o servidor a declarou bloqueada.
 *
 * A união das três é falha FECHADA de propósito: um bloqueio que o servidor conheça e a
 * linha não nomeie continua bloqueando — o modo de falha caro da feature é a planilha
 * parcial com aparência de completa.
 */
export function parcelaBloqueada(
  previa: SiteSetupPreviewResponse,
  row: SiteSetupRow,
): boolean {
  return (
    row.code_absent ||
    row.missing_parameters.length > 0 ||
    previa.blocked_parcel_ids.includes(row.parcel_id)
  );
}

/**
 * As parcelas bloqueadas que AINDA estão na aplicação — bloqueada e removida não bloqueia
 * mais nada, e é exatamente essa a saída que a copy da recusa prometia e que não existia:
 * remover as duas que não podem nascer deixa as outras vinte e duas aplicáveis.
 */
export function parcelasBloqueadas(fluxo: FluxoDoAcervo): SiteSetupRow[] {
  if (fluxo.previa === null) {
    return [];
  }
  const previa = fluxo.previa;
  return previa.rows.filter(
    (row) => !fluxo.excluidos.includes(row.parcel_id) && parcelaBloqueada(previa, row),
  );
}

/** Os parâmetros que as parcelas bloqueadas citam, sem repetir e na ordem de aparição. */
export function parametrosBloqueantes(fluxo: FluxoDoAcervo): string[] {
  const nomes: string[] = [];
  for (const row of parcelasBloqueadas(fluxo)) {
    for (const nome of row.missing_parameters) {
      if (!nomes.includes(nome)) {
        nomes.push(nome);
      }
    }
  }
  return nomes;
}

/** Os códigos das parcelas bloqueadas por ausência no catálogo, na ordem de aparição. */
export function codigosBloqueantes(fluxo: FluxoDoAcervo): string[] {
  const codigos: string[] = [];
  for (const row of parcelasBloqueadas(fluxo)) {
    if (row.code_absent && !codigos.includes(row.code)) {
      codigos.push(row.code);
    }
  }
  return codigos;
}

/**
 * As parcelas que vão nascer: as da prévia menos as removidas e menos as bloqueadas.
 *
 * A bloqueada sai da conta sem sair da tela, como a removida: contá-la faria o botão
 * prometer vinte e quatro parcelas para materializar vinte e duas.
 */
export function parcelasAplicaveis(fluxo: FluxoDoAcervo): SiteSetupRow[] {
  if (fluxo.previa === null) {
    return [];
  }
  const previa = fluxo.previa;
  return previa.rows.filter(
    (row) => !fluxo.excluidos.includes(row.parcel_id) && !parcelaBloqueada(previa, row),
  );
}

/**
 * O portão do ato: **não existe caminho que aplique sem passar pela pré-visualização**.
 *
 * Exige estar no passo 3, com uma prévia do acervo escolhido, ao menos uma parcela por
 * nascer e NENHUMA parcela bloqueada ainda na aplicação. É a leitura em código do risco
 * declarado na feature — "o ganho é justamente não digitar, e o risco é a orçamentista
 * aplicar sem olhar" — mais a decisão 5 do pacote, que proíbe materializar "o que dá".
 *
 * A tela não assume a recusa do servidor: ele continua recusando fechado se o ato chegar
 * mesmo assim. O que mudou é que agora a tela sabe, parcela a parcela, o que falta — e por
 * isso pode dizer o motivo ao lado do controle em vez de só apagá-lo.
 */
export function podeAplicar(fluxo: FluxoDoAcervo): boolean {
  return (
    fluxo.passo === "previa" &&
    fluxo.previa !== null &&
    fluxo.previa.kit_id === fluxo.kitId &&
    parcelasBloqueadas(fluxo).length === 0 &&
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
    // e nunca reenviada: o fio leva os operandos, e o subtotal é do servidor. Parcela sem
    // quantidade não chega aqui (bloqueada não nasce), e se chegasse a chave some em vez de
    // a tela inventar um número.
    ...(row.quantity === null ? {} : { kitQuantity: row.quantity }),
  }));
}

/**
 * Operando do fio → linha do rascunho; unidade ausente vira `""`, que é como a tela a lê.
 *
 * Valor ausente vira `""` pela mesma razão: campo vazio é o que a tela sabe editar, e não
 * há operando ausente entre as parcelas que NASCERAM — a bloqueada não é aplicada.
 */
function paraOperandDraft(operand: SiteSetupOperand): OperandDraft {
  return {
    name: operand.name,
    value: operand.value ?? "",
    unit: operand.unit ?? "",
  };
}

/**
 * Reaplicar substitui as parcelas DAQUELE acervo e não toca em mais nada (decisão 8).
 *
 * O filtro é por `kitId`, não por base: parcela `STANDALONE` autorada à mão tem a mesma
 * base e não pode ser varrida por uma reaplicação — ela é trabalho de gente sobre esta
 * praça. Parcelas de OUTRO acervo também ficam.
 *
 * `parcelasDoAcervo` são os `parcel_id` que a aplicação tocou: as linhas que nasceram mais
 * as que a resposta ecoou como excluídas — a prévia e a aplicação não devolvem linha para
 * parcela excluída, e sem o eco a removida ficaria de fora. Ele existe por causa da
 * hidratação: a matriz
 * gravada leva `{kit_version, parcel_id}` e NÃO leva a identidade do acervo, então a
 * parcela reconstruída da leitura tem `kitId` vazio e o filtro por acervo não a alcança.
 * Sem esta lista, reaplicar depois de recarregar deixaria de pé, em silêncio, a parcela que
 * a nova aplicação removeu.
 */
export function substituirParcelasDoAcervo(
  contribuicoes: Readonly<Record<string, CalcContributionDraft>>,
  kitId: string,
  novas: readonly CalcContributionDraft[],
  parcelasDoAcervo: readonly string[] = [],
): Record<string, CalcContributionDraft> {
  const proximo: Record<string, CalcContributionDraft> = {};
  for (const [chave, draft] of Object.entries(contribuicoes)) {
    const origem = draft.kitOrigin;
    const doMesmoAcervo =
      origem !== undefined &&
      (origem.kitId === kitId || parcelasDoAcervo.includes(origem.parcelId));
    if (!doMesmoAcervo) {
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

/** Quantas parcelas de acervo a rodada tem, por versão de acervo, na ordem de aparição. */
export type AcervoGravado = { kitVersion: number; parcelas: number };

/**
 * O que a matriz GRAVADA diz sobre acervo: quantas parcelas, de qual versão. É o carimbo
 * possível depois de um recarregamento — a matriz não guarda a identidade do acervo nem os
 * parâmetros que foram declarados, e nada disso é deduzido aqui.
 */
export function acervoGravado(
  parcelas: readonly CalcContributionDraft[],
): AcervoGravado[] {
  const porVersao: AcervoGravado[] = [];
  for (const parcela of parcelas) {
    const versao = parcela.kitOrigin?.kitVersion;
    if (versao === undefined) {
      continue;
    }
    const entrada = porVersao.find((atual) => atual.kitVersion === versao);
    if (entrada === undefined) {
      porVersao.push({ kitVersion: versao, parcelas: 1 });
    } else {
      entrada.parcelas += 1;
    }
  }
  return porVersao;
}
