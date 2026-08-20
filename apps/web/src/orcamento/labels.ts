/**
 * Rótulos e mensagens do orçamento-base, em língua de obra.
 *
 * Duas regras da casa moram aqui. A primeira: **estado é texto**, nunca só cor — o
 * `proposto`/`ambíguo`/`confirmado`/`rejeitado`, a origem do preço e a etapa aparecem
 * escritos ao lado de qualquer marca visual. A segunda: a recusa do servidor chega com
 * **código estável**, e é o código que escolhe a frase; o `detail` do servidor entra como
 * complemento e código desconhecido nunca vira mensagem inventada — ele aparece com o
 * texto que veio, para o suporte poder lê-lo.
 *
 * Todo texto daqui é PROPOSTA: o Design Approval Package da F-020 aprovou a composição
 * visual e registrou explicitamente que a copy final é gate humano ainda aberto.
 */

import type { TakeoffPacket } from "@croquito/contracts";

import type { PriceOrigin } from "./api";
import type { TetoEstado } from "./teto";

/**
 * Aviso permanente da jornada — a linha fixa que declara o momento do orçamento
 * (Design Approval Package, decisão "cada jornada declara seu momento em uma linha
 * fixa"). Ele diz as duas coisas que a confusão medição × orçamento custou: de onde vem o
 * preço, e até onde ele NÃO vai.
 *
 * A fronteira é a do [ADR-0027](docs/adr/0027-price-source-provenance-and-bid-boundary.md)
 * dita na tela, não só no código: em obra licitada o preço vem do contrato, e nada
 * montado aqui alcança um boletim de medição.
 */
export const AVISO_ORCAMENTO =
  "Orçamento-base de pré-licitação; o preço vem da cascata declarada — nenhum preço " +
  "daqui alcança um boletim de medição.";

/**
 * O `409 REVISION_CONFLICT` dito como o que ele é: o orçamento andou entre a leitura e o
 * ato. Não é falha do que se tentou fazer, e por isso a frase começa pelo orçamento e
 * termina dizendo que o formulário continua ali.
 */
export const MENSAGEM_ORCAMENTO_MUDOU =
  "O orçamento mudou depois desta leitura — outra sessão, ou o processamento da própria " +
  "rodada, avançou a versão. Nada foi gravado. Recarregue o estado atual e refaça o ato " +
  "sobre a versão nova; o que você escreveu no formulário continua aqui.";

/** A regra que a etapa da cascata existe para tornar visível. */
export const AVISO_CASCATA =
  "A ordem manda: para cada item, vale o preço da primeira fonte que tiver o código. " +
  "Uma origem entra uma vez só na cascata.";

/** Por que reordenar depois da primeira decisão de código é recusado pelo servidor. */
export const AVISO_CASCATA_TRAVADA =
  "Esta rodada já tem decisão de código: a ordem da cascata ficou travada, porque " +
  "reordená-la invalidaria as decisões já registradas.";

/** O BDI, dito uma vez, no lugar em que ele é digitado. */
export const AVISO_BDI =
  "Percentual único deste orçamento, aplicado a todas as linhas. O preço unitário com " +
  "BDI é truncado no centavo, linha a linha, e o total sai da soma truncada — o BDI " +
  "impresso é a diferença entre os dois totais, não o percentual aplicado ao total.";

/** Como escrever o BDI; o servidor recebe o número exato, sem arredondar. */
export const DICA_BDI =
  "Escreva 25,00 ou 25.00 — o percentual viaja como texto e o servidor o lê exato.";

/** Por que a quantidade do item ambíguo é responsabilidade de quem revisa. */
export const AVISO_QUANTIDADE_AMBIGUA =
  "a extração não conseguiu ler este número; quem o informa é você";

/** Como escrever a quantidade; o servidor recebe o número exato, sem arredondar. */
export const DICA_QUANTIDADE =
  "Escreva 18,40 ou 18.40 — a quantidade viaja como texto e o servidor a lê exata.";

/** Item que nenhuma fonte da cascata precifica: declarado, nunca precificado por fora. */
export const AVISO_SEM_PRECO =
  "Nenhuma fonte da cascata tem código para este item. Ele entra no orçamento declarado, " +
  "sem preço, no bloco de itens sem preço da planilha — o orçamento não inventa valor.";

/**
 * Item com `anchor !== "registered"`: a bbox ainda não passou pelo registro fino contra a
 * prancha, então decidir por ela seria confiar numa localização não confirmada.
 */
export const AVISO_LOCALIZACAO_NAO_CONFIRMADA =
  "Localização na prancha não confirmada para este item — decida pela lista e pela prancha.";

/**
 * O que o clique em "calcular/recalcular shortlist" vai custar. É o texto ao lado do
 * botão que grava artefato na rodada: nenhuma rota de `/v1` publica índice de embeddings,
 * então o braço semântico não participa e nenhum provider é chamado.
 */
export const DESCRICAO_CALCULO_SHORTLIST =
  "Nenhum provider é chamado: a shortlist é calculada só pelo braço lexical, sobre a " +
  "cascata inteira e na ordem instalada.";

/** O que a montagem faz, dito antes do clique que grava planilha no servidor. */
export const DESCRICAO_MONTAGEM =
  "Montar grava o orçamento na rodada e publica a planilha — depois de a auditoria " +
  "reabrir o arquivo e reconferi-lo. Auditoria reprovada não publica nada.";

/* Teto de verba da rodada (ADR-0040) ---------------------------------------- */

/** Como escrever o teto; o servidor recebe o número exato, sem arredondar. */
export const DICA_TETO =
  "a verba prevista para esta demanda, em reais. Escreva 85.000,00 ou 85000.00 — o valor " +
  "viaja como texto e o servidor o lê exato.";

/** O rótulo é de LEITURA: ele nomeia a verba para quem lê, e não identifica nada. */
export const DICA_TETO_DEMANDA =
  "de onde a verba veio, como você a chama (ex.: Relação de Praças 2026 · demanda 14). É " +
  "rótulo de leitura, não identificador.";

/** O que declarar um teto significa — e o que ele não faz — dito na abertura da rodada. */
export const AVISO_TETO_ABERTURA =
  "O teto é meta de trabalho desta rodada: ele não entra no orçamento montado, não é " +
  "impresso na planilha e não impede nada. Sem ele, o orçamento se comporta exatamente " +
  "como hoje.";

/**
 * A pergunta que aparece sozinha quando o teto muda: o orçamento já montado é refeito?
 * Não — muda a régua, não a peça (ADR-0040, decisão 1: o teto é da rodada, não do
 * artefato).
 */
export const AVISO_TETO_EDICAO =
  "Alterar o teto não remonta o orçamento e não muda um centavo dele: o consumo passa a " +
  "ser lido contra o teto novo, e o orçamento montado continua o mesmo documento, com os " +
  "mesmos totais. O teto vive na rodada, não no orçamento — quem abrir o arquivo montado " +
  "não encontra teto nenhum lá dentro.";

/** Qual dos dois totais o consumo compara — a prévia mostra os dois, e ela precisa dizer. */
export const AVISO_CONSUMO_COM_BDI =
  "O consumo é o total com BDI, que é o valor submissível; o total sem BDI não é " +
  "comparado com o teto. Os dois lados são valores já truncados no centavo pelo servidor " +
  "— a tela não soma, não arredonda e não recalcula dinheiro.";

/** Limite exato dito por extenso como NÃO estouro (ADR-0040, decisão 3). */
export const AVISO_TETO_LIMITE =
  "Consumir o teto inteiro é estar dentro dele. O estouro começa no primeiro centavo além " +
  "do teto, e este orçamento não passou nenhum. Nenhum aviso de estouro aparece nesta " +
  "rodada.";

/**
 * O segundo parágrafo da faixa de estouro: o aviso declara a própria permanência e diz o
 * que ele NÃO é. Estouro não recusa nada (ADR-0040, decisão 4).
 */
export const AVISO_TETO_ESTOURADO = {
  destaque: "Nada foi recusado e nada foi cortado.",
  texto:
    "O orçamento está montado, a planilha continua disponível e nenhuma linha foi " +
    "removida. Este aviso não fecha, não recolhe e acompanha a rodada em todas as etapas " +
    "enquanto o consumo passar o teto.",
} as const;

/**
 * As três consequências do estouro, escritas. São a parte mais autoral do texto e a mais
 * fácil de errar — o pacote de design aprovou a composição e registrou que a copy final
 * continua sendo gate humano aberto.
 */
export const CONSEQUENCIAS_DO_ESTOURO: readonly {
  destaque: string;
  texto: string;
}[] = [
  {
    destaque: "O orçamento não foi recusado.",
    texto:
      "Ele está montado, com as mesmas linhas, e a planilha continua disponível para " +
      "exportação.",
  },
  {
    destaque: "Nenhuma linha foi removida nem sugerida para remoção.",
    texto:
      "Que item sai para caber na verba é julgamento de engenharia, e o produto não " +
      "escolhe item.",
  },
  {
    destaque: "Pedir verba adicional para a demanda é um caminho legítimo,",
    texto:
      "e é fora daqui que ele acontece. O número que você precisa levar para essa " +
      "conversa é o de cima.",
  },
];

const TETO_ETIQUETAS: Record<TetoEstado, string> = {
  dentro: "Dentro do teto",
  limite: "No limite exato — não é estouro",
  estourado: "Teto estourado",
};

/**
 * O estado do consumo ESCRITO — a palavra vem antes de qualquer cor, e no limite exato ela
 * diz por extenso que aquilo não é estouro, porque limite exato e "dentro do teto" são o
 * mesmo estado de domínio e compartilham a veste.
 */
export function tetoEtiqueta(estado: TetoEstado): string {
  return TETO_ETIQUETAS[estado];
}

/** Classe da veste do bloco de consumo; é redundância da etiqueta escrita, nunca o dado. */
export function tetoClasse(estado: TetoEstado): string {
  return `teto-${estado}`;
}

/** Tabela de rótulos por chave livre: a busca pode não achar, e o tipo diz isso. */
type LookupTable = Record<string, string | undefined>;

const ITEM_STATUS_LABELS: Record<TakeoffPacket.TakeoffItemStatus, string> = {
  proposed: "proposto",
  ambiguous: "ambíguo",
  confirmed: "confirmado",
  rejected: "rejeitado",
};

export function itemStatusLabel(
  status: TakeoffPacket.TakeoffItemStatus,
): string {
  return ITEM_STATUS_LABELS[status];
}

/** Etapa da rodada na listagem (`current_stage` da API), em língua de obra. */
const STAGE_LABELS: LookupTable = {
  created: "orçamento aberto",
  catalogs: "cascata de catálogos",
  plate: "prancha enviada",
  takeoff: "revisão do takeoff",
  code_assignments: "decisão de código",
  estimate: "orçamento montado",
};

export function stageLabel(stage: string): string {
  return STAGE_LABELS[stage] ?? stage;
}

/** Estado da leitura automática da legenda, por extenso. */
const EXTRACTION_STATUS_LABELS: LookupTable = {
  idle: "não disparada",
  queued: "na fila",
  running: "em andamento",
  done: "concluída",
  failed: "falhou",
};

export function extractionStatusLabel(status: string): string {
  return EXTRACTION_STATUS_LABELS[status] ?? status;
}

/**
 * Origem do preço como a orçamentista a nomeia. É o dado que o orçamento imprime e a
 * medição não tem: com mais de uma tabela na rodada, "de onde veio o preço" deixa de ser
 * redundante e vira parte da decisão.
 */
const PRICE_ORIGIN_LABELS: LookupTable = {
  sco: "SCO",
  emop: "EMOP",
  composition: "composição",
  sinapi: "SINAPI",
  sicro: "SICRO",
};

export function priceOriginLabel(origin: string): string {
  return PRICE_ORIGIN_LABELS[origin] ?? origin;
}

/**
 * Classe do selo de fonte. Ela é REDUNDÂNCIA do texto que já vai dentro do selo: a origem
 * aparece escrita em todo candidato e em toda linha, e nenhuma decisão depende de
 * distinguir a cor da borda.
 */
export function priceOriginSeloClass(origin: string): string {
  const known: LookupTable = {
    sco: "selo-fonte-sco",
    emop: "selo-fonte-emop",
    composition: "selo-fonte-composicao",
  };
  return known[origin] ?? "selo-neutro";
}

/** Posição na cascata, por extenso; é ela que explica por que um preço ganhou do outro. */
export function cascadePositionLabel(position: number): string {
  return `${position}ª fonte da cascata`;
}

/** A fonte de um candidato ou de uma linha, numa frase só. */
export function priceSourceLabel(
  origin: PriceOrigin | string,
  referenceMonth?: string | null,
): string {
  const label = priceOriginLabel(origin);
  return referenceMonth ? `${label} · data-base ${referenceMonth}` : label;
}

/**
 * Unidade como a obra a escreve. É troca de grafia para leitura — `m2` continua sendo
 * `m2` no dado que viaja ao servidor.
 */
const UNIT_LABELS: LookupTable = {
  m2: "m²",
  m3: "m³",
  un: "un",
  m: "m",
};

export function unitLabel(unit: string): string {
  return UNIT_LABELS[unit.trim().toLowerCase()] ?? unit;
}

const ASSIGNMENT_STATUS_LABELS: LookupTable = {
  confirmed: "código confirmado",
  rejected: "sem código na cascata",
};

export function assignmentStatusLabel(status: string): string {
  return ASSIGNMENT_STATUS_LABELS[status] ?? status;
}

/**
 * Frase que a nota obrigatória precisa registrar quando a unidade do item não é a do
 * código escolhido. O exemplo é o caso real do alambrado: metro linear medido, código
 * cotado em área.
 */
export function unitMismatchHint(itemUnit: string, codeUnit: string): string {
  return (
    `unidades diferentes (item em ${unitLabel(itemUnit)}, código em ${unitLabel(codeUnit)})` +
    " — registre a conversão, ex.: 47,01 m × h 1,00 m = 47,01 m²"
  );
}

const ERROR_MESSAGES: LookupTable = {
  // Guarda otimista, sessão e autorização da API `/v1`.
  REVISION_CONFLICT:
    "O orçamento mudou depois desta leitura; recarregue o estado atual antes de refazer o ato.",
  NOT_FOUND: "Este orçamento não existe ou não pertence ao seu tenant.",
  // O 403 NÃO nomeia papel: qual papel autoriza esta jornada é decisão humana ainda
  // aberta (Design Approval Package, "questões em aberto"), e o texto não pode fingir
  // que ela foi tomada.
  FORBIDDEN:
    "Sua conta não tem o papel que autoriza a jornada de orçamento neste tenant. Peça a quem administra o acesso da sua organização.",
  IDEMPOTENCY_KEY_REUSED:
    "Esta chave de idempotência já foi usada com outro conteúdo; recarregue o estado e refaça o ato.",
  // Etapas da rodada: a cadeia tem ordem, e sair dela é caminho normal da orçamentista.
  ROUND_STAGE_NOT_READY:
    "Esta etapa ainda não está disponível neste orçamento; conclua a etapa anterior antes de continuar.",
  ROUND_PLATE_ALREADY_PRESENT:
    "Este orçamento já tem prancha; um orçamento é uma prancha. Para enviar outra, abra outro orçamento.",
  EXTRACTION_IN_PROGRESS:
    "Já existe uma leitura automática em andamento neste orçamento; aguarde ela terminar.",
  TAKEOFF_REVIEW_INCOMPLETE:
    "A sugestão de código exige a revisão do takeoff concluída.",
  SUGGESTIONS_ALREADY_REFINED:
    "A shortlist deste orçamento carrega refino pago; recalcular descartaria o lineage da chamada.",
  // Cascata de fontes de preço — a etapa que a medição não tem.
  ESTIMATE_CASCADE_ORIGIN_DUPLICATE:
    "Esta cascata já tem uma fonte desta origem. Cada origem entra uma vez só; para trocar a data-base, abra outro orçamento com a fonte nova.",
  ESTIMATE_CASCADE_ORDER_INVALID:
    "A ordem informada não é uma reordenação das fontes instaladas; a reordenação não acrescenta, não remove e não repete fonte.",
  ESTIMATE_CASCADE_LOCKED:
    "Este orçamento já tem decisão de código: reordenar a cascata invalidaria as decisões registradas, e apagar decisão não é ato desta tela.",
  ESTIMATE_CASCADE_EMPTY:
    "O orçamento não tem fonte de preço instalada; sem cascata não há o que precificar.",
  ESTIMATE_CASCADE_CONTRACT_FORBIDDEN:
    "Contrato de obra licitada não entra na cascata do orçamento-base: antes da licitação não existe contrato.",
  CATALOG_REQUIRED:
    "Um catálogo da cascata não pôde ser lido; sem ele não há código nem preço a consultar.",
  CATALOG_QUERY_EMPTY:
    "A busca exige ao menos uma palavra com dois caracteres ou mais.",
  // Uploads e chamada paga.
  INVALID_UPLOAD:
    "O arquivo enviado não é aceitável para este orçamento; confira o formato e envie de novo.",
  UPLOAD_TRANSFER_FAILED:
    "O envio direto do arquivo ao armazenamento não foi concluído; tente enviar de novo.",
  LIMIT_EXCEEDED: "O arquivo enviado excede o limite aceito pela API.",
  PROCESSING_UNAVAILABLE:
    "A fila de processamento não aceitou o comando agora; tente de novo em instantes.",
  PROVIDER_UNAVAILABLE:
    "A leitura automática não está disponível neste ambiente; nenhum provider foi chamado.",
  AI_PROCESSING_NOT_AUTHORIZED:
    "O seu tenant não tem autorização contratual para processamento por IA; fale com quem administra o contrato.",
  DOMAIN_VALIDATION_FAILED:
    "O servidor recusou este ato por uma regra de domínio do orçamento-base.",
  MODEL_VALIDATION_FAILED:
    "O documento gravado neste orçamento não corresponde ao contrato do modelo.",
  // Invariantes de `packages/valuation`: viajam em `details.code` do
  // `DOMAIN_VALIDATION_FAILED`, e é o código do domínio, não o da API, que escolhe a frase.
  LOCAL_QUANTITY_INVALID:
    "A quantidade informada não é um número decimal exato. Use ponto ou vírgula como separador decimal (ex.: 18.40).",
  ESTIMATE_BDI_INVALID:
    "O BDI informado não é um percentual decimal finito e não negativo. Escreva 25,00 ou 25.00.",
  // Teto de verba: zero e negativo são recusados pelo servidor, e "sem teto" é a ausência
  // do campo — nunca zero (ADR-0040, decisão 1).
  ESTIMATE_TARGET_INVALID:
    "O teto de verba não é um valor em reais maior que zero. Escreva 85.000,00 ou 85000.00; para a rodada não ter teto, o campo fica vazio.",
  // Revisão do takeoff.
  TAKEOFF_ITEM_ALREADY_REVIEWED:
    "Este item já foi decidido; decisão não se sobrescreve.",
  TAKEOFF_ITEM_CONFIRMED_INCOMPLETE:
    "Confirmar este item exige a quantidade: a extração não conseguiu lê-la.",
  TAKEOFF_ITEM_AMBIGUOUS_WITH_QUANTITY:
    "Item ambíguo é a linha sem quantidade legível; ela não pode chegar preenchida.",
  TAKEOFF_DECISION_UNKNOWN_ITEM:
    "A decisão aponta para um item que não está no pacote desta prancha.",
  // Decisão de código, agora com a fonte citada.
  ASSIGNMENT_ITEM_ALREADY_DECIDED:
    "O código deste item já foi decidido; decisão não se sobrescreve.",
  ASSIGNMENT_ITEM_NOT_CONFIRMED:
    "Só item confirmado na revisão do takeoff recebe código.",
  ASSIGNMENT_UNIT_INCOMPATIBLE_WITHOUT_NOTE:
    "A unidade do código não é a do item: registre a conversão na nota para confirmar.",
  ASSIGNMENT_CODE_INVALID:
    "O código informado não tem a estrutura de um código com preço publicado nesta origem.",
  ASSIGNMENT_CODE_NOT_IN_CATALOG:
    "O código informado não está no catálogo citado; escolha um código da fonte que você citou.",
  ASSIGNMENT_CODE_REQUIRED: "Confirmar exige escolher um código de uma das fontes.",
  ASSIGNMENT_CODE_ON_REJECT:
    "Rejeitar não leva código: o item fica declarado sem preço na cascata.",
  ASSIGNMENT_CATALOG_REQUIRED:
    "Confirmar um código exige citar de qual fonte da cascata o preço sai.",
  ASSIGNMENT_CATALOG_ON_REJECT:
    "Rejeitar é recusar todas as fontes, não uma delas: a rejeição não cita catálogo.",
  ASSIGNMENT_CATALOG_UNKNOWN:
    "A fonte citada não está na cascata deste orçamento; instale-a ou escolha um código de uma das fontes instaladas.",
  ASSIGNMENT_CATALOG_MISMATCH:
    "As decisões deste orçamento foram calculadas sobre outra cascata; recarregue o estado atual antes de decidir de novo.",
  ASSIGNMENT_PACKET_MISMATCH:
    "As decisões de código deste orçamento pertencem a outra prancha.",
  SUGGESTION_NO_CONFIRMED_ITEMS:
    "Não há item confirmado no takeoff; revise o takeoff antes de sugerir códigos.",
  // Montagem do orçamento.
  ESTIMATE_ASSIGNMENT_MISSING:
    "Há item confirmado sem decisão de código; o orçamento não é montado pela metade.",
  ESTIMATE_ASSIGNMENT_CATALOG_REQUIRED:
    "Há confirmação de código sem fonte citada; sem ela a linha não sabe de onde o preço veio.",
  ESTIMATE_ASSIGNMENT_UNKNOWN_ITEM:
    "Há confirmação de código para um item que não está confirmado no takeoff deste orçamento.",
  ESTIMATE_ASSIGNMENT_PACKET_MISMATCH:
    "As confirmações de código deste orçamento pertencem a outra prancha.",
  ESTIMATE_NO_ITEMS: "Não há item precificável para montar o orçamento desta obra.",
  ESTIMATE_LINE_SOURCE_UNKNOWN:
    "Uma linha cita um catálogo que não está na cascata deste orçamento. Instale a fonte ou escolha um código de uma das fontes instaladas.",
  ESTIMATE_CODE_INVALID_FOR_ORIGIN:
    "O código escolhido não tem o formato da fonte de onde ele diz vir.",
  ESTIMATE_LINE_BDI_MISMATCH:
    "O preço com BDI de uma linha não confere com o percentual do orçamento; o preço com BDI é recomputado e truncado no centavo pelo servidor.",
  ESTIMATE_LINE_TOTAL_MISMATCH:
    "O total de uma linha não confere com preço com BDI × quantidade.",
  ESTIMATE_TOTAL_MISMATCH:
    "O total geral não confere com a soma das linhas truncadas no centavo.",
  ESTIMATE_TOTAL_WITHOUT_BDI_MISMATCH:
    "O total sem BDI não confere com a soma das linhas sem o percentual.",
  ESTIMATE_QUANTITY_MISMATCH:
    "A quantidade de uma linha diverge da memória de cálculo do item.",
  ESTIMATE_CALC_SHEET_MISMATCH:
    "As linhas do orçamento e a memória de cálculo não estão em correspondência 1:1.",
  ESTIMATE_DUPLICATE_ITEM: "Há item repetido no orçamento montado.",
  ESTIMATE_UNPRICED_ITEM_INVALID:
    "A lista de itens sem preço não corresponde aos itens confirmados sem código na cascata.",
  ESTIMATE_QUANTITY_SCALE_UNSUPPORTED:
    "A escala da quantidade informada não é suportada pelo cálculo do orçamento.",
  // Planilha: o portão fail-closed do ADR-0038.
  ESTIMATE_WORKBOOK_AUDIT_FAILED:
    "A auditoria recusou a planilha e nada foi publicado. O arquivo gerado foi descartado; o orçamento continua como estava.",
};

/**
 * Mensagem exibida para uma recusa. O código manda; o `detail` do servidor acompanha
 * como complemento, e código sem frase própria mostra os dois — nunca uma frase genérica
 * que esconda o que o domínio disse.
 */
export function errorMessage(code: string, detail?: string | null): string {
  const known = ERROR_MESSAGES[code];
  const cleaned = detail?.trim();
  if (known) {
    return cleaned && !known.toLowerCase().includes(cleaned.toLowerCase())
      ? `${known} (${cleaned})`
      : known;
  }
  return cleaned ? `${code}: ${cleaned}` : code;
}

const EXTRACTION_FAILURE_MESSAGES: LookupTable = {
  PROVIDER_EXECUTION_FAILED:
    "A chamada ao provider falhou; nenhum artefato foi publicado neste orçamento.",
  EXTRACTION_PAGE_NOT_BOUND:
    "A página promovida não corresponde à prancha autorizada para leitura automática.",
  MODEL_VALIDATION_FAILED:
    "A leitura automática devolveu um pacote fora do contrato do modelo; nada foi publicado.",
  VALUATION_EXTRACTION_FAILED:
    "A leitura automática da legenda não fechou; nenhum artefato foi publicado.",
};

/**
 * Por que a leitura automática da legenda não publicou nada. O código estável vem da
 * rodada (`extraction.failure_code`) e é ele que escolhe a frase — o servidor não manda
 * mensagem pronta em `/v1`, e inventar uma sem código seria pior do que dizer o que se
 * sabe. Código desconhecido aparece como veio, nunca escondido.
 */
export function extractionFailureMessage(code: string | null): string {
  if (code === null) {
    return "A leitura automática da legenda falhou neste orçamento.";
  }
  return (
    EXTRACTION_FAILURE_MESSAGES[code] ??
    `A leitura automática da legenda falhou (${code}).`
  );
}
