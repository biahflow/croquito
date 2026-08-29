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

/**
 * A aprovação caduca dita por extenso (`APPROVAL_CONTENT_MISMATCH` derivado na leitura).
 *
 * Ela não é falha do ato: alguém assinou, e a medição mudou depois. A frase diz as duas
 * coisas que a orçamentista precisa saber — nada foi exportado, e a única saída é aprovar
 * de novo. Não existe "exportar assim mesmo", e o texto não pode sugerir que exista.
 */
export const MENSAGEM_APROVACAO_CADUCA =
  "A medição mudou depois de aprovada, e a aprovação não vale mais. Nada foi exportado, e " +
  "nada será exportado até a medição atual ser aprovada de novo.";

/** Aprovação registrada e válida: o que ela destrava, sem prometer arquivo nenhum. */
export const MENSAGEM_MEDICAO_APROVADA =
  "Medição aprovada. A exportação do boletim está liberada nesta rodada.";

/**
 * O que o clique de exportar faz, dito antes do clique. Três dos quatro passos acontecem
 * antes de existir arquivo publicado, e é isso que a frase precisa deixar claro.
 */
export const AVISO_EXPORTACAO_FAIL_CLOSED =
  "O arquivo é montado, gravado, reaberto e reconferido centavo a centavo antes de ser " +
  "publicado. Se a reconferência achar qualquer divergência, nada é publicado.";

/** Auditoria reprovada: o desfecho por extenso, porque "falhou" não diz o que aconteceu. */
export const MENSAGEM_AUDITORIA_REPROVADA =
  "A auditoria recusou o arquivo e nada foi publicado. O arquivo gerado foi descartado; a " +
  "rodada continua como estava e a aprovação registrada segue como estava.";

/**
 * `403` da rota, **sem nomear papel**. Qual papel a mensagem deve citar é decisão de copy e
 * de autorização ainda aberta no pacote de design aprovado da F-028; um texto que nomeasse
 * um papel afirmaria uma decisão que ninguém tomou. Quem autoriza continua sendo o backend.
 */
export const MENSAGEM_SEM_ACESSO =
  "Sua conta não tem autorização para a medição deste tenant. Peça a quem administra o " +
  "acesso da sua organização.";

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

/**
 * Estado da assinatura de um orçamento oferecido como origem (F-036).
 *
 * Texto dentro da pastilha, e não só cor: é a regra do design system, e aqui ela tem peso
 * extra porque a diferença entre "caduca" e "sem assinatura" muda o próximo ato.
 */
const ORIGIN_SIGNATURE_LABELS: LookupTable = {
  signed: "Assinado",
  stale: "Assinatura caduca",
  unsigned: "Sem assinatura",
};

export function originSignatureLabel(signature: string): string {
  return ORIGIN_SIGNATURE_LABELS[signature] ?? signature;
}

/** Por que este orçamento não serve ainda, na língua de quem vai resolver. */
const ORIGIN_SIGNATURE_HINTS: LookupTable = {
  stale:
    "Foi remontado depois de assinado, então a assinatura não vale para o conteúdo atual. " +
    "Assine a versão atual para abrir a medição a partir dela.",
  unsigned:
    "Ainda não foi assinado. Sem conteúdo aprovado não há contratado de onde abrir a " +
    "medição.",
};

export function originSignatureHint(signature: string): string | null {
  return ORIGIN_SIGNATURE_HINTS[signature] ?? null;
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
  declared_product: "produto dos fatores declarados",
};

export function recipeLabel(recipe: string): string {
  return RECIPE_LABELS[recipe] ?? recipe;
}

/**
 * Origem da quantidade do item, em língua de obra (F-047, ADR-0058).
 *
 * `scene_graph` é a origem NOVA e a única que dispensa digitação: o número atravessou a
 * fronteira do croqui aprovado, com a precisão declarada lá.
 */
const QUANTITY_SOURCE_LABELS: LookupTable = {
  legend_extraction: "legenda lida",
  manual: "digitada na revisão",
  scene_graph: "cena aprovada",
};

export function quantitySourceLabel(source: string): string {
  return QUANTITY_SOURCE_LABELS[source] ?? source;
}

/** Precisão declarada pela entidade da cena. É palavra, nunca só traço ou cor. */
const PRECISION_LABELS: LookupTable = {
  exact: "exata",
  derived: "derivada",
  approximate: "aproximada",
  unresolved: "não resolvida",
};

export function precisionLabel(precision: string): string {
  return PRECISION_LABELS[precision] ?? precision;
}

/**
 * A conta da tolerância, por extenso.
 *
 * É FRASE, não cálculo: a diferença e a tolerância de cada divergência chegam prontas do
 * servidor, que as recomputa e confere na gravação. A tela escreve a regra para que quem
 * lê saiba de onde os dois números saíram — e não refaz nenhum deles.
 */
export const FORMULA_DA_TOLERANCIA =
  "tolerância = maior entre 1% da quantidade da legenda e 0,01 na unidade do item";

/**
 * Por que a divergência não concilia sozinha. É o texto do bloqueio, e ele diz que a
 * recusa é diagnóstico: os dois números continuam gravados, e a decisão é de gente.
 */
export const AVISO_DIVERGENCIA_ABERTA =
  "A cena é auditada, mas auditada não é sempre certa: um elemento mal traçado produz " +
  "comprimento errado com precisão declarada, e a legenda pode ter um dígito trocado. O " +
  "sistema não sabe qual é qual — por isso mostra os dois e recusa fechar. Nenhuma origem " +
  "apaga a outra.";

/**
 * Por que a terceira opção não existe na tela (ADR-0058, aceite de 2026-08-28).
 *
 * Digitar uma terceira quantidade aqui seria exatamente a redigitação que a feature existe
 * para eliminar. Quem quer um número que não é nem o da cena nem o da legenda corrige a
 * ORIGEM, cada uma na sua jornada.
 */
export const RAZAO_SEM_TERCEIRA_ESCOLHA =
  "Indisponível: uma terceira quantidade digitada aqui seria a redigitação que esta " +
  "feature existe para eliminar. Se as duas estão erradas, o caminho é corrigir o croqui " +
  "ou a leitura da legenda, cada um na sua jornada.";

/**
 * Por que não há campo de quantidade no item alimentado pela cena (ADR-0058, decisões 5 e
 * 7). A ação não some da tela: ela fica visível com a razão ao lado, para que a ausência
 * seja lida como decisão e não como falta.
 */
export const RAZAO_SEM_CAMPO_DE_QUANTIDADE =
  "Não existe campo de quantidade neste item: a quantidade veio da cena aprovada. A " +
  "redigitação era onde o erro entrava, e o jeito de eliminá-la é não oferecer o teclado.";

/** As duas escolhas que resolvem uma divergência — e só elas. */
const DIVERGENCE_CHOICE_LABELS: LookupTable = {
  scene: "vale a cena",
  legend: "vale a legenda",
};

export function divergenceChoiceLabel(choice: string): string {
  return DIVERGENCE_CHOICE_LABELS[choice] ?? choice;
}

/** Desfecho do confronto para um item do pacote. Três desfechos, e só três. */
const SCENE_OUTCOME_LABELS: LookupTable = {
  fed: "alimentado pela cena",
  divergence_recorded: "divergência gravada",
  unchanged: "sem mudança",
};

export function sceneOutcomeLabel(outcome: string): string {
  return SCENE_OUTCOME_LABELS[outcome] ?? outcome;
}

/**
 * Por que o item não recebeu quantidade da cena, item a item.
 *
 * A tabela junta os DOIS enums que o servidor manda no mesmo campo do relatório — os
 * motivos de a cena não ter número (`QuantityUnresolvedReason`) e os de o item ficar
 * intacto (`SceneConfrontationSkipReason`). Os valores são disjuntos de propósito, então
 * uma tabela só não confunde um motivo com o outro. Motivo desconhecido aparece como veio:
 * inventar a frase esconderia o que o domínio disse.
 */
const SCENE_REASON_LABELS: LookupTable = {
  // A cena não tinha número para o item.
  item_without_element_ref:
    "o item da legenda não declarou identidade de elemento — falta o par do lado da legenda",
  element_ref_absent_from_scene:
    "a identidade declarada neste item não aparece em nenhuma linha do quantitativos.csv — falta o par do lado da cena",
  precision_not_eligible:
    "a linha da cena é aproximada ou não resolvida: não alimenta a medição e também não compara",
  unit_not_derivable_from_scene:
    "a unidade deste item não é de comprimento nem de área; a cena não a produz",
  unit_mismatch:
    "a linha da cena traz a outra grandeza (área para item em metro, ou comprimento para item em m²)",
  length_ambiguous:
    "a linha da cena traz comprimento E perímetro; escolher um por conta própria seria palpite",
  quantity_absent: "a linha da cena não traz grandeza nenhuma",
  quantity_not_positive:
    "a grandeza da cena é zero ou negativa; quantidade de medição é sempre positiva",
  // O item ficou intacto, mesmo com a cena tendo número.
  item_rejected:
    "linha rejeitada pelo orçamentista: ela não vira boletim, então confrontá-la não destrava nada",
  already_fed_from_scene:
    "a quantidade deste item já nasceu da cena; não há legenda para confrontar",
  divergence_already_recorded:
    "este item já tem divergência gravada; regravá-la apagaria o número que alguém está olhando ou a decisão já tomada",
  within_tolerance:
    "os dois números existem e concordam dentro da tolerância nomeada: concordar não é evento",
};

export function sceneReasonLabel(reason: string): string {
  return SCENE_REASON_LABELS[reason] ?? reason;
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
  // Abertura a partir de orçamento assinado (F-036, ADR-0048).
  ESTIMATE_ORIGIN_REGIME_REQUIRED:
    "Só orçamento sob demanda contratada vira contratado da medição: fora desse regime existem a licitação e o deságio entre o orçamento e o contrato.",
  ESTIMATE_ORIGIN_NOT_SIGNED:
    "Este orçamento não tem assinatura válida; sem conteúdo aprovado não há contratado de onde abrir a medição.",
  // Etapas da rodada: a cadeia tem ordem, e sair dela é caminho normal do orçamentista.
  ROUND_STAGE_NOT_READY:
    "Esta etapa ainda não está disponível nesta rodada; conclua a etapa anterior antes de continuar.",
  // Desde a F-046 a segunda folha é o caso normal: o que este código recusa é a folha
  // REPETIDA — mesma origem e mesma página — e não a segunda prancha da praça.
  ROUND_PLATE_ALREADY_PRESENT:
    "Esta folha já está na praça: mesma origem e mesma página. Escolha outra página, ou envie outro documento.",
  ROUND_PLATE_LIMIT_REACHED:
    "A praça atingiu o limite de folhas por rodada; nenhuma folha nova foi acrescentada.",
  ROUND_PLATE_PAGES_REQUIRED:
    "O lote chegou sem escolha nenhuma; marque as páginas que viram prancha, ou as folhas que vão para a leitura.",
  ROUND_PLATE_NOT_FOUND:
    "Uma das folhas escolhidas não é desta praça; recarregue o estado atual e escolha de novo.",
  // A praça de várias folhas (F-046, ADR-0057).
  WORKSITE_TAKEOFF_PLATE_PENDING:
    "A praça não fecha com folha pendente de revisão: item proposto ou ambíguo em qualquer folha bloqueia o boletim da obra.",
  WORKSITE_LINK_SAME_PLATE:
    "O vínculo de identidade é entre folhas diferentes; duas leituras da mesma folha são dois itens da legenda, e item repetido dentro de uma folha se resolve rejeitando um deles na revisão.",
  WORKSITE_LINK_INCOMPLETE:
    "O vínculo de identidade exige a nota: autor e instante são carimbados pelo servidor, mas o motivo é de quem declara.",
  WORKSITE_LINK_UNKNOWN_TARGET:
    "O vínculo de identidade aponta para uma folha ou um item que não está no consolidado desta praça.",
  WORKSITE_LINK_CHAIN_NOT_SUPPORTED:
    "Vínculos de identidade não formam cadeia: declare o vínculo direto entre as duas leituras em vez de encadear.",
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
    "Este código já foi decidido para o item; decisão não se sobrescreve.",
  ASSIGNMENT_DUPLICATE_ITEM:
    "Um item recebe uma rejeição só: rejeitar é recusar todos os códigos de uma vez.",
  ASSIGNMENT_DUPLICATE_PAIR:
    "Este código já está no pacote deste item; escolha outro.",
  ASSIGNMENT_REJECT_WITH_CONFIRMED:
    "Rejeitar é declarar que nenhum serviço precifica este elemento, e ele já tem código confirmado.",
  ASSIGNMENT_ITEM_ALREADY_CLOSED:
    "O pacote deste item já foi declarado completo; não entra código novo.",
  ASSIGNMENT_DUPLICATE_CLOSURE:
    "O pacote deste item já foi declarado completo.",
  ASSIGNMENT_CLOSURE_WITHOUT_ASSIGNMENT:
    "Confirme ao menos um código antes de fechar o pacote; rejeitar já encerra o item.",
  ASSIGNMENT_CLOSURE_NOT_SUPPORTED:
    "Esta rodada foi montada antes do pacote de serviços e não tem pacote a fechar.",
  ASSIGNMENT_BATCH_EMPTY:
    "O envio precisa levar ao menos uma decisão de código ou um fechamento de pacote.",
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
  CALC_PACKAGE_NOT_CLOSED:
    "Há item com pacote de serviços em aberto; o boletim não é montado pela metade.",
  CALC_PACKAGE_NOT_SUPPORTED:
    "Item com mais de um código ainda não vira boletim: a matriz de contribuições resolve o pacote.",
  CALC_CONTRIBUTION_WITHOUT_SOURCE_ITEM:
    "A parcela nasce de um elemento da prancha e precisa dizer de qual.",
  CALC_CONTRIBUTION_CODE_INVALID:
    "O código de origem da parcela não tem a forma de um código de catálogo.",
  // Coerência da parcela e da matriz (ADR-0053, F-038): rótulos nas duas jornadas, mesma
  // regra da casa. A dependência resolvida no build da medição usa `error_prefix="CALC"`.
  CALC_CONTRIBUTION_STANDALONE_WITH_ITEM:
    "Parcela de canteiro não nasce de elemento da prancha; ela não aponta para nenhum item.",
  CALC_CONTRIBUTION_DEPENDENT_WITHOUT_CODE:
    "Parcela derivada de outro serviço precisa dizer de qual código ela vem.",
  CALC_CONTRIBUTION_CODE_WITHOUT_DEPENDENCY:
    "Só parcela derivada de outro serviço cita um código de origem; esta base não é derivada.",
  CALC_MATRIX_DUPLICATE_CODE:
    "Há mais de um conjunto de contribuições para o mesmo serviço; cada código entra uma vez.",
  CALC_MATRIX_SELF_DEPENDENCY:
    "Um serviço não pode derivar de si mesmo; a memória não teria ordem de cálculo.",
  CALC_MATRIX_DEPENDENCY_CYCLE:
    "Há dependência cíclica entre serviços; a memória não tem ordem de cálculo. Desfaça o ciclo.",
  CALC_MATRIX_DEPENDENCY_UNKNOWN:
    "Uma parcela derivada aponta para um serviço que não está no boletim; inclua-o ou corrija a origem.",
  CALC_MATRIX_DEPENDENCY_UNPRICED:
    "Uma parcela derivada aponta para um serviço sem código confirmado; confirme o código de origem antes.",
  CALC_PLAN_QUANTITY_MISMATCH:
    "A decomposição do plano de cálculo não fecha com a quantidade confirmada.",
  CALC_NO_ITEMS: "Não há item medido para montar o boletim desta obra.",
  BULLETIN_PRICE_ORIGIN_FORBIDDEN:
    "Em obra licitada o preço vem do contrato: item de outra tabela não entra no boletim, vira pedido de aditivo.",
  // Aprovação nominal e portão de exportação (VAL-05). Os códigos são do domínio
  // (`Valuation.export_errors`) e chegam na lista de `VALUATION_EXPORT_BLOCKED`.
  VALUATION_EXPORT_BLOCKED:
    "O portão de exportação recusou esta medição; nada foi publicado. Os motivos abertos estão listados abaixo.",
  VALUATION_NOT_APPROVED:
    "Esta medição não tem aprovação nominal válida. Exportar é o passo depois de aprovar: aprove a medição e a exportação fica liberada.",
  VALUATION_APPROVAL_REJECTED:
    "A decisão registrada para esta medição é de recusa, não de aprovação; medição recusada não é exportada.",
  APPROVAL_CONTENT_MISMATCH:
    "A medição mudou depois da aprovação. A aprovação registrada vale para o conteúdo aprovado, não para o atual — aprove a medição atual.",
  PERIOD_NOT_SEQUENTIAL:
    "Esta rodada não é o próximo período do contrato: o período medido não é o que o consolidado espera.",
  BALANCE_EXCEEDED:
    "A quantidade medida deste código passa do saldo contratual disponível; o excedente não entra no boletim.",
  LINE_PRICE_NOT_IN_CONTRACT:
    "O preço unitário deste código no boletim não é o do contrato desta obra.",
  LINE_UNIT_NOT_IN_CONTRACT:
    "A unidade deste código no boletim não é a do contrato desta obra.",
  VALUATION_WORKBOOK_AUDIT_FAILED:
    "A planilha gerada não confere com a medição aprovada; nada foi publicado e o arquivo foi descartado.",
  // Achados da auditoria de round-trip (`audit_workbook`). Só os CÓDIGOS voltam do
  // servidor: o valor esperado e o encontrado são dinheiro e quantidade da obra.
  SHEET_MISSING: "Uma aba que a medição exige não foi encontrada no arquivo reaberto.",
  SHEET_UNEXPECTED: "O arquivo reaberto tem uma aba que a medição não pediu.",
  CELL_MISSING: "Uma célula que a medição exige está vazia no arquivo reaberto.",
  CELL_UNEXPECTED: "O arquivo reaberto tem conteúdo numa célula que deveria estar vazia.",
  CELL_KIND_MISMATCH:
    "Uma célula do arquivo reaberto tem outro tipo de conteúdo (texto onde deveria haver número, ou o contrário).",
  CELL_VALUE_MISMATCH:
    "Uma célula do arquivo reaberto não tem o valor que a medição declara; um centavo de diferença basta para não publicar.",
  CELL_FORMULA_MISMATCH:
    "Uma fórmula do arquivo reaberto não é a que a medição declara.",
  CATALOG_CODE_MISSING:
    "Um código impresso na planilha não está no catálogo instalado nesta rodada.",
  CATALOG_PRICE_MISMATCH:
    "Um preço impresso na planilha não é o do catálogo instalado nesta rodada.",
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
  // Elo com o croqui aprovado e confronto com a cena (F-047, ADR-0058).
  SCENE_LINK_REQUIRED:
    "Esta rodada não declarou qual croqui aprovado a alimenta; declare o elo antes de confrontar as quantidades.",
  SCENE_LINK_SCENE_NOT_APPROVED:
    "O croqui indicado não tem cena aprovada; só cena aprovada alimenta medição.",
  SCENE_LINK_EXPORT_REQUIRED:
    "O croqui indicado está aprovado mas ainda não tem pacote publicado; sem o pacote não há quantitativos.csv de onde ler.",
  SCENE_PACKAGE_REQUIRED:
    "O pacote do croqui declarado por esta rodada não pôde ser lido; nada foi alterado no takeoff.",
  QUANTITY_SOURCE_CSV_INVALID:
    "O quantitativos.csv do pacote declarado não segue o contrato de colunas; nada foi alterado no takeoff.",
  QUANTITY_DIVERGENCE_ALREADY_RECORDED:
    "Este item já tem divergência gravada; regravá-la apagaria o número que está na tela ou a decisão já tomada.",
  TAKEOFF_DIVERGENCE_UNKNOWN_ITEM:
    "Este item não está no pacote de takeoff desta rodada.",
  TAKEOFF_DIVERGENCE_ABSENT:
    "Este item não tem divergência para resolver.",
  TAKEOFF_DIVERGENCE_ALREADY_RESOLVED:
    "Esta divergência já foi resolvida; decisão não se sobrescreve.",
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

/**
 * Nome de cada parte que o domínio escreve depois do código da violação, na ordem de
 * `Valuation.export_errors` (`PERIOD_NOT_SEQUENTIAL:esperado:recebido`,
 * `CODE_NOT_IN_CONTRACT:obra:item:código`). Sem esta tabela, `…:3:4` chegaria à tela como
 * dois números sem nome.
 */
const VIOLATION_PART_LABELS: Record<string, string[] | undefined> = {
  PERIOD_NOT_SEQUENTIAL: ["esperado", "recebido"],
  CODE_NOT_IN_CONTRACT: ["obra", "item", "código"],
  CODE_AMBIGUOUS_IN_CONTRACT: ["obra", "item", "código"],
  LINE_PRICE_NOT_IN_CONTRACT: ["código"],
  LINE_UNIT_NOT_IN_CONTRACT: ["código"],
  BALANCE_EXCEEDED: ["código"],
};

/**
 * Linha do código estável de uma violação do portão, com as partes nomeadas — é o que fica
 * visível ao lado da frase para quem dá suporte. Parte sem rótulo conhecido aparece como
 * veio: nomear por adivinhação seria pior do que mostrar o segmento cru.
 */
export function violationDetailLine(
  code: string,
  parts: readonly string[],
): string {
  const labels = VIOLATION_PART_LABELS[code] ?? [];
  const described = parts.map((part, index) => {
    const label = labels[index];
    return label === undefined ? part : `${label} ${part}`;
  });
  return [code, ...described].join(" · ");
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


/* Desfazer um código confirmado (F-045, pacote de design revisão 2) -----------
 *
 * A copy é a mesma do orçamento-base, menos uma linha: aqui não existe precedente a apagar —
 * o índice é da pré-licitação, e a obra licitada não tem shortlist que aprenda. Repetir
 * aquela frase seria prometer um efeito que não acontece.
 */

/** O botão de cada código do pacote. Ele só abre a caixa; não grava. */
export const DESFAZER_BOTAO = "Desfazer este código";

/** O título da caixa, com o código à vista: o ato é do par, não do elemento. */
export function fraseDesfazerTitulo(code: string): string {
  return `Desfazer ${code}`;
}

/** O campo obrigatório. "(obrigatório)" vai escrito, e não sinalizado por asterisco. */
export const DESFAZER_MOTIVO_LABEL = "Por que este código sai do pacote? (obrigatório)";

/** As duas linhas do efeito — a terceira, a do precedente, é só do orçamento-base. */
export function frasesEfeitoDesfazer(code: string): readonly string[] {
  return [
    `tira ${code} do pacote deste item;`,
    "registra quem desfez, quando e o motivo — a confirmação continua na revisão anterior.",
  ];
}

/** O botão que grava, e o nome que ele assume quando o pacote está fechado. */
export function fraseDesfazerConfirmar(pacoteFechado: boolean): string {
  return pacoteFechado ? "Desfazer e reabrir o pacote" : "Desfazer o código";
}

/** O aviso do pacote fechado, por extenso e antes do clique. */
export const DESFAZER_AVISO_PACOTE_FECHADO =
  "O pacote deste item está fechado. Desfazer um código reabre o pacote: a completude foi " +
  "afirmada sobre um pacote que vai mudar, e ela precisa ser afirmada de novo. Enquanto " +
  "estiver aberto, o boletim recusa este item.";

/** Desfazer é conserto, não punição — e quem lê precisa saber antes de hesitar. */
export const DESFAZER_NAO_BANE =
  "Desfazer não bane o código: se for engano, ele pode ser confirmado de novo neste mesmo " +
  "item.";

export const DESFAZER_CANCELAR = "Cancelar";

/** O título da lista do que foi desfeito e continua desfeito. */
export const DESFEITOS_TITULO = "Desfeitos neste item";

/** O selo de cada linha da lista. A palavra, não a cor, é o que distingue. */
export const DESFEITO_SELO = "desfeito";

/** O aviso do sucesso: desfez, e o que isso deixou para trás. */
export function fraseDesfeitoGravado(code: string, reabriu: boolean): string {
  const base = `${code} saiu do pacote deste item, com o motivo registrado.`;
  return reabriu
    ? `${base} O pacote voltou a ficar em aberto: feche-o de novo quando não houver mais serviços.`
    : base;
}
