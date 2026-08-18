/**
 * Rótulos e mensagens em língua de obra.
 *
 * Duas regras da casa moram aqui. A primeira: **estado é texto**, nunca só cor — o
 * `proposto`/`ambíguo`/`confirmado`/`rejeitado` aparece escrito ao lado de qualquer
 * marca visual. A segunda: a recusa do servidor chega com **código estável**, e é o
 * código que escolhe a frase; o `detail` do servidor entra como complemento e o código
 * desconhecido nunca vira mensagem inventada — ele aparece com o texto que veio.
 */

import type { TakeoffPacket } from "@croquito/contracts";

/**
 * Aviso permanente da jornada; repetido no cabeçalho e no boletim.
 *
 * A sessão é sempre autenticada (ADR-0028): a decisão é carimbada com a identidade de
 * quem entrou, nunca com a de quem subiu um processo. A segunda metade não mudou porque a
 * regra não mudou — medir continua não sendo aprovar nem exportar.
 */
export const AVISO_MEDICAO =
  "Medição autenticada; decisões carimbadas com sua identidade — medição sem aprovação; " +
  "aprovar e exportar são atos separados.";

/**
 * O `409 REVISION_CONFLICT` dito como o que ele é: a rodada andou entre a leitura e o
 * ato. Não é falha do que se tentou fazer, e por isso a frase começa pela rodada e termina
 * dizendo que o formulário continua ali.
 */
export const MENSAGEM_RODADA_MUDOU =
  "A rodada mudou depois desta leitura — outra sessão, ou o processamento da própria " +
  "rodada, avançou a versão. Nada foi gravado. Recarregue o estado atual e decida de " +
  "novo; o que você escreveu no formulário continua aqui.";

/** Por que a quantidade do item ambíguo é responsabilidade de quem revisa. */
export const AVISO_QUANTIDADE_AMBIGUA =
  "a extração não conseguiu ler este número; quem o informa é você";

/** Como escrever a quantidade; o servidor recebe o número exato, sem arredondar. */
export const DICA_QUANTIDADE =
  "Escreva 18,40 ou 18.40 — a quantidade viaja como texto e o servidor a lê exata.";

/** Regra da obra licitada, mostrada na seção de candidatos a aditivo. */
export const AVISO_ADITIVO =
  "Em obra licitada, item sem código no contrato não é precificado por fora: ele vira " +
  "pedido de aditivo (RE-RA) para a prefeitura. Esta lista é o insumo dessa conversa.";

/**
 * Enquanto `GET /dossier` ainda não tem artefato: a lista de candidatos calculada nesta
 * tela é só prévia, nunca o dossiê. O dossiê nasce no servidor, fecha a rodada (exige
 * decisão de código para todo item confirmado) e é ele quem instrui o pedido de aditivo.
 */
export const AVISO_DOSSIE_PREVIA =
  "Prévia calculada nesta tela — ainda não é o dossiê. Gere o dossiê para o servidor " +
  "fechar a lista oficial com a justificativa de cada rejeição.";

/** Mostrado com o dossiê já gravado na rodada: a lista abaixo passou a vir do servidor. */
export const AVISO_DOSSIE_GERADO =
  "Dossiê gravado nesta rodada. Ele não precifica nenhum item e não cria nem altera " +
  "pedido de aditivo (RE-RA) — a solicitação à prefeitura continua sendo ato humano.";

/**
 * Item com `anchor !== "registered"` (`itemAnchor`): a bbox ainda não passou pelo
 * registro fino contra a prancha, então o retângulo não é desenhado — decidir por ele
 * seria confiar numa localização não confirmada.
 */
export const AVISO_LOCALIZACAO_NAO_CONFIRMADA =
  "Localização na prancha não confirmada para este item — decida pela lista e pela prancha.";

/**
 * O que o clique em "calcular/recalcular shortlist" vai custar. É o texto ao lado do botão
 * que grava artefato na rodada — quem aperta precisa saber, antes do clique, se ele paga
 * algo. Na rodada de `/v1` a resposta é uma só, e ela é declarada: nenhuma rota publica
 * índice de embeddings, então o braço semântico não participa e nenhum provider é chamado.
 */
export const DESCRICAO_CALCULO_SHORTLIST =
  "Nenhum provider é chamado: a shortlist da rodada é calculada só pelo braço lexical.";

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

/** Etapa da rodada na listagem, em língua de obra. */
const STAGE_LABELS: LookupTable = {
  created: "rodada aberta",
  plate: "prancha enviada",
  extraction: "leitura da legenda",
  takeoff: "revisão do takeoff",
  code_assignments: "confirmação de código",
  bulletin: "boletim montado",
  amendment_dossier: "dossiê do aditivo",
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

/** Tabela de rótulos por chave livre: a busca pode não achar, e o tipo diz isso. */
type LookupTable = Record<string, string | undefined>;

const ASSIGNMENT_STATUS_LABELS: LookupTable = {
  confirmed: "código confirmado",
  rejected: "sem código no contrato",
};

export function assignmentStatusLabel(status: string): string {
  return ASSIGNMENT_STATUS_LABELS[status] ?? status;
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

/**
 * Receita do bloco de memória em língua de obra. O identificador do domínio continua
 * visível ao lado no bloco: quem confere a planilha lê a frase, quem confere o JSON
 * reconhece a chave.
 */
const RECIPE_LABELS: LookupTable = {
  direct_quantity: "quantidade direta",
  length_times_width: "comprimento × largura",
  perimeter_times_height: "perímetro × altura",
  perim_height_minus_openings: "perímetro × altura menos vãos",
  qty_times_months: "quantidade × meses",
  days_times_hours: "dias × horas",
};

export function recipeLabel(recipe: string): string {
  return RECIPE_LABELS[recipe] ?? recipe;
}

const ERROR_MESSAGES: LookupTable = {
  // Guarda otimista e sessão da API `/v1`.
  REVISION_CONFLICT:
    "A rodada mudou depois desta leitura; recarregue o estado atual antes de decidir de novo.",
  NOT_FOUND:
    "Esta rodada não existe ou não pertence ao seu tenant.",
  FORBIDDEN:
    "O seu usuário não tem o papel de orçamentista neste ambiente. Peça a quem administra o ambiente antes de decidir.",
  IDEMPOTENCY_KEY_REUSED:
    "Esta chave de idempotência já foi usada com outro conteúdo; recarregue o estado e refaça o ato.",
  // Etapas da rodada: a cadeia tem ordem, e sair dela é caminho normal do orçamentista.
  ROUND_STAGE_NOT_READY:
    "Esta etapa ainda não está disponível nesta rodada; conclua a etapa anterior antes de continuar.",
  ROUND_PLATE_ALREADY_PRESENT:
    "Esta rodada já tem prancha; uma rodada é uma prancha. Para enviar outra, abra uma rodada nova.",
  EXTRACTION_IN_PROGRESS:
    "Já existe uma leitura automática em andamento nesta rodada; aguarde ela terminar.",
  TAKEOFF_REVIEW_INCOMPLETE:
    "A sugestão de código exige a revisão do takeoff concluída.",
  SUGGESTIONS_ALREADY_REFINED:
    "A shortlist desta rodada carrega refino pago; recalcular descartaria o lineage da chamada.",
  CATALOG_REQUIRED:
    "O catálogo de preços desta rodada não pôde ser lido; sem ele não há código nem preço a consultar.",
  CATALOG_QUERY_EMPTY:
    "A busca exige ao menos uma palavra com dois caracteres ou mais.",
  // Uploads e chamada paga.
  INVALID_UPLOAD:
    "O arquivo enviado não é aceitável para esta rodada; confira o formato e envie de novo.",
  // Falha do `PUT` assinado, não do arquivo: o byte não chegou ao armazenamento.
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
    "O servidor recusou este ato por uma regra de domínio da medição.",
  // Invariante de `packages/valuation`: viaja em `details.code` do
  // `DOMAIN_VALIDATION_FAILED` e é ela, não o código da API, que escolhe a frase.
  LOCAL_QUANTITY_INVALID:
    "A quantidade informada não é um número decimal exato. Use ponto como separador decimal (ex.: 18.40).",
  // Revisão do takeoff.
  TAKEOFF_ITEM_ALREADY_REVIEWED:
    "Este item já foi decidido; decisão não se sobrescreve.",
  TAKEOFF_ITEM_CONFIRMED_INCOMPLETE:
    "Confirmar este item exige a quantidade: a extração não conseguiu lê-la.",
  TAKEOFF_ITEM_AMBIGUOUS_WITH_QUANTITY:
    "Item ambíguo é a linha sem quantidade legível; ela não pode chegar preenchida.",
  TAKEOFF_DECISION_UNKNOWN_ITEM:
    "A decisão aponta para um item que não está no pacote desta prancha.",
  // Confirmação de código.
  ASSIGNMENT_ITEM_ALREADY_DECIDED:
    "O código deste item já foi decidido; decisão não se sobrescreve.",
  ASSIGNMENT_ITEM_NOT_CONFIRMED:
    "Só item confirmado na revisão do takeoff recebe código.",
  ASSIGNMENT_UNIT_INCOMPATIBLE_WITHOUT_NOTE:
    "A unidade do código não é a do item: registre a conversão na nota para confirmar.",
  ASSIGNMENT_CODE_INVALID:
    "O código informado não tem a estrutura de um código SCO com preço publicado.",
  ASSIGNMENT_CODE_NOT_IN_CATALOG:
    "O código informado não está no catálogo importado desta rodada.",
  ASSIGNMENT_CODE_REQUIRED: "Confirmar exige escolher um código do catálogo.",
  ASSIGNMENT_CODE_ON_REJECT:
    "Rejeitar não leva código: o item fica como candidato a aditivo.",
  CODE_NOT_IN_CONTRACT:
    "O código existe no catálogo mas não está no contrato desta obra; ele é candidato a aditivo.",
  CODE_AMBIGUOUS_IN_CONTRACT:
    "O contrato repete este código em mais de um grupo; o boletim não carrega grupo, então ele é recusado em vez de escolhido.",
  SUGGESTION_NO_CONFIRMED_ITEMS:
    "Não há item confirmado no takeoff; revise o takeoff antes de sugerir códigos.",
  // Boletim.
  CALC_ASSIGNMENT_MISSING:
    "Há item confirmado sem decisão de código; o boletim não é montado pela metade.",
  CALC_PLAN_QUANTITY_MISMATCH:
    "A decomposição do plano de cálculo não fecha com a quantidade confirmada.",
  CALC_NO_ITEMS: "Não há item medido para montar o boletim desta obra.",
  BULLETIN_PRICE_ORIGIN_FORBIDDEN:
    "Em obra licitada o preço vem do contrato: item de outra tabela não entra no boletim, vira pedido de aditivo.",
  MODEL_VALIDATION_FAILED:
    "O documento gravado na rodada não corresponde ao contrato do modelo.",
  // Dossiê do aditivo.
  AMENDMENT_DOSSIER_ASSIGNMENTS_INCOMPLETE:
    "Há item confirmado sem decisão de código; o dossiê não é montado pela metade.",
  AMENDMENT_DOSSIER_JUSTIFICATION_MISSING:
    "Há rejeição de código sem nota registrada; a nota é a justificativa do aditivo.",
  AMENDMENT_DOSSIER_UNKNOWN_ITEM:
    "Há confirmação de código para um item que não está confirmado no takeoff desta rodada.",
  AMENDMENT_DOSSIER_PACKET_MISMATCH:
    "As confirmações de código desta rodada pertencem a outra prancha.",
};

/**
 * Mensagem exibida para uma recusa. O código manda; o `detail` do servidor acompanha
 * como complemento, e código sem frase própria mostra os dois — nunca uma frase
 * genérica que esconda o que o domínio disse.
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
    "A chamada ao provider falhou; nenhum artefato foi publicado nesta rodada.",
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
    return "A leitura automática da legenda falhou nesta rodada.";
  }
  return (
    EXTRACTION_FAILURE_MESSAGES[code] ??
    `A leitura automática da legenda falhou (${code}).`
  );
}
