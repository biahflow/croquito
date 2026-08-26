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
