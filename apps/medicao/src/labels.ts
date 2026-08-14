/**
 * Rótulos e mensagens em língua de obra.
 *
 * Duas regras da casa moram aqui. A primeira: **estado é texto**, nunca só cor — o
 * `proposto`/`ambíguo`/`confirmado`/`rejeitado` aparece escrito ao lado de qualquer
 * marca visual. A segunda: a recusa do servidor chega com **código estável**, e é o
 * código que escolhe a frase; o `detail` do servidor entra como complemento e o código
 * desconhecido nunca vira mensagem inventada — ele aparece com o texto que veio.
 */

import type { TakeoffItemStatus } from "./api";

/** Aviso permanente da ferramenta; repetido no cabeçalho e no boletim. */
export const AVISO_FERRAMENTA_LOCAL =
  "Ferramenta local de homologação — medição sem aprovação; aprovar e exportar são atos separados.";

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
 * Item com `anchor !== "registered"` (`itemAnchor`): a bbox ainda não passou pelo
 * registro fino contra a prancha, então o retângulo não é desenhado — decidir por ele
 * seria confiar numa localização não confirmada.
 */
export const AVISO_LOCALIZACAO_NAO_CONFIRMADA =
  "Localização na prancha não confirmada para este item — decida pela lista e pela prancha.";

/**
 * O que o clique em "recalcular shortlist" vai custar, pelo status do braço semântico da
 * rodada (`RunState.busca_semantica.status`). É o texto ao lado do botão que grava
 * artefato no servidor — quem aperta precisa saber, antes do clique, se ele paga algo.
 */
export function descricaoCalculoShortlist(
  status: "available" | "limited" | "unavailable",
): string {
  if (status === "available") {
    return (
      "Com o índice semântico desta rodada, embutir os rótulos custa uma chamada paga " +
      "pequena, cacheada nesta rodada; consulta já embutida não é cobrada de novo."
    );
  }
  if (status === "limited") {
    // Índice presente e credencial ausente: o vetor que já está no cache da rodada
    // continua respondendo pelo híbrido. Prometer "só lexical" aqui seria descrever
    // errado a shortlist que vai sair.
    return (
      "Nenhum provider é chamado: com vetores já cacheados na rodada a shortlist ainda " +
      "sai híbrida; sem cache, sai lexical."
    );
  }
  return "Nenhum provider é chamado: a shortlist é calculada só pelo braço lexical.";
}

const ITEM_STATUS_LABELS: Record<TakeoffItemStatus, string> = {
  proposed: "proposto",
  ambiguous: "ambíguo",
  confirmed: "confirmado",
  rejected: "rejeitado",
};

export function itemStatusLabel(status: TakeoffItemStatus): string {
  return ITEM_STATUS_LABELS[status];
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
  // Guarda otimista e artefatos da rodada.
  LOCAL_STATE_MOVED:
    "O estado da rodada mudou depois desta leitura; recarregue o estado atual antes de decidir de novo.",
  LOCAL_ARTIFACT_MISSING:
    "Um artefato de entrada não está no diretório da rodada; gere-o pelo CLI antes de continuar.",
  // Os dois valem para qualquer artefato com guarda de digest (confirmações de código,
  // shortlist de sugestões): quem nomeia o artefato é o `detail` do servidor, e uma frase
  // fixa citando só as confirmações mentiria no recompute da shortlist.
  LOCAL_BASE_DIGEST_REQUIRED:
    "Este artefato da rodada já foi gravado; recarregue o estado para citar o digest atual dele.",
  LOCAL_BASE_DIGEST_UNEXPECTED:
    "Este artefato da rodada ainda não existe; recarregue o estado antes de continuar.",
  LOCAL_QUANTITY_INVALID:
    "A quantidade informada não é um número decimal exato. Use ponto como separador decimal (ex.: 18.40).",
  LOCAL_SEARCH_QUERY_EMPTY:
    "A busca exige ao menos uma palavra com dois caracteres ou mais.",
  LOCAL_REQUEST_INVALID:
    "O servidor recusou o formulário: algum campo não corresponde ao contrato da rota.",
  LOCAL_TAKEOFF_REVIEW_INCOMPLETE:
    "A sugestão de código exige a revisão do takeoff concluída.",
  LOCAL_SERVER_UNREACHABLE:
    "O servidor local não respondeu. Confira se `croquito-valuation serve` está no ar.",
  LOCAL_RESPONSE_UNREADABLE:
    "O servidor local respondeu fora do formato esperado.",
  // Prancha e extração automática.
  LOCAL_ROUND_ALREADY_HAS_PLATE:
    "Esta rodada já tem prancha; uma rodada é uma prancha. Para enviar outra, abra o servidor numa rodada nova.",
  LOCAL_EXTRACTION_BUSY:
    "Já existe uma extração automática em andamento nesta rodada; aguarde ela terminar.",
  LOCAL_EXTRACTION_UNAVAILABLE:
    "Extração automática indisponível no servidor local desta rodada.",
  LOCAL_UPLOAD_INVALID:
    "O arquivo enviado não é um PDF de prancha aceitável.",
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
  MODEL_VALIDATION_FAILED:
    "O documento gravado na rodada não corresponde ao contrato do modelo.",
};

/**
 * Mensagem exibida para uma recusa. O código manda; o `detail` do servidor acompanha
 * como complemento, e código sem frase própria mostra os dois — nunca uma frase
 * genérica que esconda o que o domínio disse.
 */
export function errorMessage(code: string, detail?: string): string {
  const known = ERROR_MESSAGES[code];
  const cleaned = detail?.trim();
  if (known) {
    return cleaned && !known.toLowerCase().includes(cleaned.toLowerCase())
      ? `${known} (${cleaned})`
      : known;
  }
  return cleaned ? `${code}: ${cleaned}` : code;
}
