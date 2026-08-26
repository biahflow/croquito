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
import { formatDecimalText } from "./format";
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
 *
 * Ele afirma o MOMENTO, e por isso só vale onde existe rodada em pré-licitação. Sem rodada
 * quem fala é `AVISO_ORCAMENTO_SEM_RODADA`.
 */
export const AVISO_ORCAMENTO =
  "Orçamento-base de pré-licitação; o preço vem da cascata declarada — nenhum preço " +
  "daqui alcança um boletim de medição.";

/**
 * A mesma linha fixa onde NÃO existe rodada nenhuma — sem sessão, sem acesso e sem
 * orçamento aberto (F-033, revisão 2 do Design Approval Package, tela 2).
 *
 * Nas três telas o regime não existe para ser afirmado: não há rodada de que ele fosse o
 * regime. A linha continua dizendo as duas coisas de sempre — de onde o preço vem e até
 * onde ele não vai —, e para de dizer a terceira, que era a única que a tela não sabia.
 */
export const AVISO_ORCAMENTO_SEM_RODADA =
  "O orçamento-base precifica pela cascata declarada na rodada. Nenhum preço daqui " +
  "alcança um boletim de medição.";

/* Regime da rodada (ADR-0045, F-033) --------------------------------------- */

/**
 * O selo do regime, nas duas superfícies em que ele aparece (cabeçalho da rodada e painel
 * da Cascata). O vocabulário é o que o ADR-0045 fixou: "demanda sob contrato" no domínio,
 * "Sob contrato licitado" na tela.
 */
export const SELO_REGIME = "SOB CONTRATO LICITADO";

/**
 * A linha fixa da rodada SOB CONTRATO, no lugar da de pré-licitação. O momento mudou, e a
 * linha que declara o momento muda com ele: aqui o preço já está fixado pelo contrato, e a
 * cascata deixou de ser livre.
 */
export const AVISO_ORCAMENTO_SOB_CONTRATO =
  "Demanda dentro de contrato já licitado: o preço está fixado pelo contrato, e só a " +
  "tabela contratual vale. Nenhum preço daqui alcança um boletim sem passar pela medição.";

/** O que o regime faz com a cascata, dito na aba onde a regra age. */
export const AVISO_CASCATA_SOB_CONTRATO =
  "Esta rodada corre sob contrato licitado. Instalar fonte de outra origem é recusado " +
  "aqui, na instalação — não na montagem, quando já não haveria o que corrigir.";

/**
 * As origens que a instalação aceitaria, escritas ao lado do campo do catálogo.
 *
 * A lista vem do SERVIDOR (`regime.allowed_cascade_origins`) e não de uma cópia desta
 * tela: a regra é de lá, e guardá-la aqui só produziria a divergência que aparece numa
 * recusa. Lista vazia não vira frase — a tela não afirma uma restrição que não leu.
 */
export function origensAceitasNaCascata(origins: readonly string[]): string | null {
  if (origins.length === 0) {
    return null;
  }
  const nomes = origins.map(priceOriginLabel).join(", ");
  return (
    `Sob contrato licitado, a cascata aceita catálogo de ${nomes} — a tabela do ` +
    "contrato. Catálogo de outra origem é recusado na instalação, e nada é gravado."
  );
}

/** O ato de declarar, no molde do teto: um seletor, um botão e o que ele decide. */
export const PERGUNTA_REGIME = "Esta demanda corre sob contrato licitado?";

/**
 * O painel de declarar DEPOIS deixou de ser o único caminho e continua sendo um caminho
 * (F-033, revisão 2, tela 5): quem abriu sem declarar corrige aqui. A frase diz onde a
 * rodada está antes de pedir o ato, porque é essa a informação que faltava a quem chega
 * neste painel sem ter passado pela abertura.
 */
export const DESCRICAO_REGIME =
  "Esta rodada foi aberta em pré-licitação. Declare aqui se ela for, na verdade, orçada " +
  "dentro de um contrato guarda-chuva já licitado — a partir daí a cascata só aceita a " +
  "tabela do contrato.";

/* Regime na abertura da rodada (F-033, revisão 2, tela 3) ------------------- */

/** A pergunta, antes do seletor: ela é a escolha inteira, com as duas saídas escritas. */
export const PERGUNTA_REGIME_ABERTURA =
  "a demanda corre dentro de um contrato guarda-chuva já licitado, ou é orçamento de " +
  "pré-licitação?";

/**
 * A consequência e a mão única, ditas ANTES do clique — é isso que distingue o campo da
 * "caixa de marcar escondida no formulário de abertura" que a revisão 1 recusou (decisão 2
 * da revisão 2). O destaque é a regra que a escolha liga; o resto é o que ela custa.
 */
export const AVISO_REGIME_ABERTURA = {
  destaque: "Sob contrato, a cascata só aceita a tabela do contrato",
  texto:
    ", e declarar é mão única: a rodada não volta para pré-licitação. Corrigir um engano " +
    "é abrir outra rodada.",
} as const;

/**
 * Por que um card da lista não tem selo. O silêncio também diz (decisão 4 da revisão 2), e
 * dizer isso uma vez ao pé da lista evita que a ausência do selo leia como dado faltando.
 */
export const AVISO_CARD_SEM_REGIME =
  "Rodada sem selo é rodada em pré-licitação: ausência não é um valor, é a falta dele.";

/**
 * O que a declaração NÃO faz, dito antes do clique. Restringir a origem garante que o
 * preço veio do SCO; não garante que veio da tabela, data-base e desconto DAQUELE
 * contrato — a lacuna que o ADR-0045 nomeia e deixa aberta.
 *
 * Ela aparece nos DOIS lugares em que se declara: no campo da abertura e no painel de
 * declarar depois. Não migrou de um para o outro — com a abertura virando o caminho
 * principal, deixá-la só no painel faria o produto parar de dizer o que ele NÃO garante
 * justamente no ato que virou o normal.
 */
export const DICA_REGIME =
  "Restringir a origem não confere o contrato: o sistema garante que o preço veio do " +
  "SCO, não que veio da tabela, data-base e desconto daquele contrato.";

/** Declarar é mão única, e a tela diz isso antes, não na recusa. */
export const AVISO_REGIME_MAO_UNICA =
  "Declarar é mão única: a rodada não volta para pré-licitação, e as decisões tomadas " +
  "sob o regime continuam de pé. Corrigir um engano é abrir outra rodada.";

/** As duas opções do seletor: onde a rodada está, e para onde ela pode ir. */
export const REGIME_OPCAO_PRE_LICITACAO = "Pré-licitação (padrão)";
export const REGIME_OPCAO_SOB_CONTRATO = "Demanda sob contrato";

/**
 * De onde vem o sinal de candidato a aditivo — do julgamento de quem revisou, e não de uma
 * conferência contra um contrato que o orçamento não modela (ADR-0045, decisão 5).
 */
export const AVISO_CANDIDATO_ADITIVO =
  "Item cuja confirmação de código foi rejeitada, numa rodada sob contrato, é candidato " +
  "a aditivo: não há código na tabela contratual que o cubra, segundo o julgamento de " +
  "quem revisou.";

/** O limite do que o produto afirma, escrito ao lado do sinal. */
export const DICA_CANDIDATO_ADITIVO =
  "O produto afirma que a orçamentista não achou código na tabela contratual — nunca que " +
  "o item não existe no contrato. O orçamento não conhece o contrato como entidade.";

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

/* Acervo de tabelas da plataforma (F-037, ADR-0047) ------------------------- */

/**
 * A procedência de uma fonte instalada, por EXTENSO — a palavra é a marca, e a veste do
 * selo é redundância (decisão 3 do pacote aprovado da F-037).
 *
 * Fonte sem o campo é a instalada antes desta superfície: ela lê como tabela própria, que
 * é o que ela é, porque era o único caminho que existia. Nada é reescrito para trás.
 */
export function procedenciaDaFonte(provenance?: string | null): string {
  return provenance === "reference_catalog" ? "DO ACERVO" : "TABELA PRÓPRIA";
}

/** O rótulo do campo de escolha: a lista é o caminho principal, e ela é de tabelas. */
export const ROTULO_TABELA_DO_ACERVO = "Tabela de preços";

/** A opção vazia do seletor: nada nasce escolhido, como em toda decisão desta jornada. */
export const OPCAO_TABELA_NAO_ESCOLHIDA = "Escolha uma tabela…";

/**
 * Uma linha da lista, com o que distingue duas tabelas que sem isso seriam ambas "SCO":
 * nome, data-base e tamanho (decisão 2 do pacote aprovado).
 *
 * A contagem é agrupada em milhar pela mesma função dos outros números da tela — é troca
 * de pontuação, nunca aritmética.
 */
export function opcaoDoAcervo(catalog: {
  display_name: string;
  reference_month: string;
  entry_count: number;
}): string {
  return (
    `${catalog.display_name} · ref. ${catalog.reference_month} · ` +
    `${formatDecimalText(String(catalog.entry_count))} itens`
  );
}

/**
 * Por que a lista pode estar mais curta do que o acervo, sem repetir a regra do regime.
 *
 * A frase diz que o filtro é do SERVIDOR e o que ele evita; ela não nomeia as origens
 * recusadas, porque nomeá-las seria guardar aqui uma cópia da regra — exatamente o que
 * `origensAceitasNaCascata` existe para não fazer.
 */
export const AVISO_ACERVO_FILTRADO =
  "Esta lista já vem filtrada pelo servidor: tabela que o regime desta rodada não " +
  "aceitaria não aparece aqui, porque oferecê-la seria oferecer uma recusa.";

/** Acervo vazio é ESTADO, não erro: a plataforma ainda não publicou (decisão 5). */
export const TITULO_ACERVO_VAZIO = "Nenhuma tabela disponível";

export const AVISO_ACERVO_VAZIO =
  "A plataforma ainda não publicou nenhuma tabela de referência que sirva a esta rodada. " +
  "Enquanto isso, envie a sua.";

/** A lista ainda não foi lida — declarado, nunca disfarçado de acervo vazio. */
export const AVISO_ACERVO_NAO_LIDO =
  "A lista de tabelas desta rodada ainda não foi lida.";

/** Falha de LEITURA do acervo: ela não esconde o caminho do arquivo próprio. */
export const AVISO_ACERVO_INDISPONIVEL =
  "A lista de tabelas da plataforma não pôde ser lida agora. O caminho da tabela própria " +
  "continua disponível abaixo.";

/** A alternativa nomeada: quem ela serve, dito antes do clique (decisão 1). */
export const CONVITE_TABELA_PROPRIA =
  "Tem uma tabela própria — a do seu contrato, ou uma que você licenciou?";

export const ACAO_TABELA_PROPRIA = "Enviar arquivo";

export const TITULO_TABELA_PROPRIA = "Enviar tabela própria";

export const DESCRICAO_TABELA_PROPRIA =
  "Para tabela que a plataforma não distribui — a EMOP, que é paga, ou o catálogo " +
  "específico do seu contrato.";

export const ACAO_VOLTAR_PARA_A_LISTA = "Voltar para a lista";

/** O que a procedência NÃO muda, ao lado da cascata que a declara. */
export const AVISO_PROCEDENCIA =
  "O digest é o mesmo nos dois casos: o que muda é quem publicou o arquivo, não como o " +
  "preço é lido.";

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

/**
 * O que a montagem faz, dito antes do clique. Desde a F-035 ela só MONTA: a planilha
 * deixou de nascer aqui, e prometê-la neste texto seria descrever a rota anterior.
 */
export const DESCRICAO_MONTAGEM =
  "Montar grava o orçamento na rodada e não publica planilha nenhuma. Publicar é ato " +
  "próprio, na etapa “Aprovação e despacho”, e depende da assinatura.";

/* Aprovação nominal e despacho (F-035, ADR-0046) ---------------------------- */

/**
 * A aprovação caduca dita por extenso (`APPROVAL_CONTENT_MISMATCH` derivado na leitura).
 *
 * Ela não é falha do ato: alguém assinou, e o orçamento mudou depois. A frase diz as duas
 * coisas que a orçamentista precisa saber — nada foi despachado, e a única saída é aprovar
 * de novo. Não existe "despachar assim mesmo", e o texto não pode sugerir que exista.
 */
export const MENSAGEM_APROVACAO_CADUCA =
  "O orçamento mudou depois de aprovado, e a aprovação não vale mais. Nada foi despachado, " +
  "e nada será despachado até o orçamento atual ser aprovado de novo.";

/** Aprovação registrada e válida: o que ela destrava, sem prometer arquivo nenhum. */
export const MENSAGEM_ORCAMENTO_APROVADO =
  "Orçamento aprovado. O despacho da planilha está liberado nesta rodada.";

/** Despacho concluído: o que passou a existir, e o que continua sendo do servidor. */
export const MENSAGEM_ORCAMENTO_DESPACHADO =
  "Planilha despachada: a auditoria reabriu o arquivo e o reconferiu antes de publicar.";

/**
 * O que o clique de despachar faz, dito antes do clique. Três dos quatro passos acontecem
 * antes de existir arquivo publicado, e é por isso que o progresso é lista escrita.
 */
export const AVISO_DESPACHO_FAIL_CLOSED =
  "O arquivo é montado, gravado, reaberto e reconferido centavo a centavo antes de ser " +
  "publicado. Se a reconferência achar qualquer divergência, nada é publicado.";

/** Por que assinar e despachar não são o mesmo ato, dito ao lado dos dois botões. */
export const AVISO_ASSINAR_NAO_E_DESPACHAR =
  "Despachar exige o papel orcamentista. Assinar é assumir o conteúdo; despachar é operar " +
  "o envio — o produto não funde os dois só porque acontecem em sequência.";

/** Por que não há campo de nome no ato nominal. A identidade é mostrada, nunca digitada. */
export const AVISO_IDENTIDADE_DA_SESSAO =
  "Não existe campo de nome nesta tela: quem aprova é quem entrou, e o servidor lê a " +
  "identidade do token e recusa qualquer nome que venha do cliente.";

/** O arquivo é endereçado pelo digest: despachar de novo não sobrescreve o anterior. */
export const AVISO_PLANILHA_ENDERECADA_PELO_DIGEST =
  "O arquivo é endereçado pelo digest: despachar de novo nunca sobrescreve a planilha que " +
  "uma revisão anterior ainda referencia.";

/**
 * O título da etapa "Aprovação e despacho", pelos dois campos lidos JUNTOS.
 *
 * A caducidade é perguntada PRIMEIRO, como no resumo da etapa: na aprovação caduca
 * `aprovado` e `caduca` valem ao mesmo tempo, e um título que lesse só o primeiro diria
 * "Orçamento aprovado" sobre um orçamento que o despacho já vai recusar.
 */
export function tituloDaAprovacao(
  aprovado: boolean,
  caduca: boolean,
  despachado: boolean,
): string {
  if (caduca) {
    return "O orçamento mudou depois de aprovado";
  }
  if (!aprovado) {
    return "Orçamento montado, aguardando aprovação nominal";
  }
  return despachado ? "Orçamento aprovado e despachado" : "Orçamento aprovado";
}

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

/**
 * Sob contrato licitado, a rejeição continua sendo a MESMA decisão e ganha outro nome: o
 * item que ninguém achou na tabela contratual é candidato a aditivo (ADR-0045, decisão 5).
 * Nada novo é calculado — muda o que a rejeição significa quando a rodada corre sob
 * contrato, e por isso o rótulo é o ponto de mudança.
 *
 * Fora do regime a rejeição segue lendo o que lê hoje: "sem código na cascata" é a frase
 * de uma rodada de pré-licitação, onde não há contrato de que aditar.
 */
const ASSIGNMENT_STATUS_LABELS_SOB_CONTRATO: LookupTable = {
  rejected: "candidato a aditivo",
};

export function assignmentStatusLabel(
  status: string,
  sobContrato = false,
): string {
  const sobRegime = sobContrato
    ? ASSIGNMENT_STATUS_LABELS_SOB_CONTRATO[status]
    : undefined;
  return sobRegime ?? ASSIGNMENT_STATUS_LABELS[status] ?? status;
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

/* Memória de cálculo na jornada do orçamento (ADR-0053, F-038 T9) ----------- */

/**
 * A memória de cálculo passou a existir aqui (Design Approval Package, decisão 3): com a
 * matriz elemento × serviço, ela é o artefato que explica DE ONDE veio cada quantidade. A
 * frase diz que nada é recomputado na tela — todos os subtotais e totais vêm do servidor.
 */
export const AVISO_MEMORIA =
  "A memória mostra, para cada serviço, as parcelas que os elementos da prancha somam à " +
  "quantidade — e de qual elemento cada parcela veio. Os subtotais e o total vêm do " +
  "servidor; a tela não multiplica nem soma.";

/**
 * Receita do bloco de memória em língua de obra. O identificador do domínio continua
 * visível ao lado no bloco: quem confere a planilha lê a frase, quem confere o JSON
 * reconhece a chave. Espelho deliberado do `recipeLabel` da medição — as jornadas
 * compartilham o vocabulário do domínio, nunca o módulo.
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
 * A base de contribuição de uma parcela por extenso (`ContributionBasis`, ADR-0053,
 * decisão 3). É rótulo TEXTUAL, não cor (Design Approval Package, decisão 5): parcela
 * parcial e serviço derivado de outro precisam de palavra, não só de veste.
 *
 * `PARTIAL` é o ponto de honestidade do desenho — os 170 m² de limpeza dentro dos 418,12
 * do piso são DECLARADOS, com nota e teto, nunca recomputados. `DEPENDENT` diz que a
 * quantidade veio de outro serviço, e `derivadaDeLabel` nomeia qual.
 */
const CONTRIBUTION_BASIS_LABELS: LookupTable = {
  full: "espelho do elemento",
  derived: "derivada da geometria",
  partial: "parcela parcial declarada",
  dependent: "derivada de outro serviço",
  standalone: "de canteiro, sem origem geométrica",
};

/**
 * `basis` nasce `null` ("não declarado") em artefato anterior à matriz (ADR-0053, decisão
 * 3): a ausência não afirma nada, e a tela não inventa "espelho" para ela — devolve `null`
 * e o bloco simplesmente não exibe a base.
 */
export function contributionBasisLabel(
  basis: string | null | undefined,
): string | null {
  if (!basis) {
    return null;
  }
  return CONTRIBUTION_BASIS_LABELS[basis] ?? basis;
}

/** De qual serviço uma parcela `DEPENDENT` tirou a quantidade — a proveniência, escrita. */
export function derivadaDeLabel(code: string): string {
  return `derivada da quantidade de ${code}`;
}

/**
 * Copy da AUTORIA da matriz (F-038 "decisão 6"). A copy final é decisão-à-parte do pacote
 * (o mock aprova a direção, não o texto), mas as strings ficam AQUI, nunca no JSX — é a
 * mesma regra do resto da jornada. A base é dita por extenso ao lado da cor, sempre.
 */
export const AUTORIA_TITULO = "Contribuição deste elemento para o serviço";

export const AUTORIA_DICA =
  "Um elemento da prancha pode alimentar vários serviços, e cada parcela declara COMO: a " +
  "grandeza, os operandos nomeados e, quando é o caso, que ela é parcial (recorte medido " +
  "dentro do elemento) ou derivada de outro serviço. Os subtotais são recomputados pelo " +
  "servidor; a tela não multiplica nem soma.";

export const AUTORIA_DICA_PARCIAL =
  "Parcela parcial é DECLARADA, não recomputada: escreva o número, a justificativa e ela é " +
  "conferida contra o teto do elemento (nunca maior que a quantidade dele).";

export const AUTORIA_ROTULO_TETO = "Teto desta parcela (quantidade do elemento)";

export const AUTORIA_SEM_TETO =
  "O elemento ainda não tem quantidade confirmada, então não há teto a conferir aqui; o " +
  "servidor confere no build.";

export const RESUMO_MATRIZ_TITULO = "Ordem de cálculo dos serviços";

export const RESUMO_MATRIZ_DICA =
  "Um serviço que alimenta outro é calculado antes. A ordem abaixo é a que o orçamento " +
  "seguirá; ciclo e auto-referência são recusados por extenso, não escondidos.";

export const RESUMO_MATRIZ_VAZIO =
  "Nenhuma contribuição autorada ainda. Sem matriz, o orçamento usa o regime de um código " +
  "por item, como antes.";

/**
 * Frase curta que explica cada base na hora de escolher — não é o rótulo do resultado
 * (`contributionBasisLabel`), é a ajuda da autoria. `null` quando a base não é conhecida.
 */
const CONTRIBUTION_BASIS_HINTS: LookupTable = {
  full: "a parcela é a quantidade confirmada do elemento, inteira.",
  derived: "sai da geometria do elemento por uma fórmula (perímetro × altura).",
  partial: "recorte medido à parte, declarado, dentro do teto do elemento.",
  dependent: "vem da quantidade de OUTRO serviço (transporte, carga, bota-fora).",
  standalone: "não tem origem geométrica: canteiro e administração.",
};

export function contributionBasisHint(basis: string): string | null {
  return CONTRIBUTION_BASIS_HINTS[basis] ?? null;
}

const ERROR_MESSAGES: LookupTable = {
  // Guarda otimista, sessão e autorização da API `/v1`.
  REVISION_CONFLICT:
    "O orçamento mudou depois desta leitura; recarregue o estado atual antes de refazer o ato.",
  NOT_FOUND: "Este orçamento não existe ou não pertence ao seu tenant.",
  // O 403 genérico NÃO nomeia papel, e desde a F-035 o motivo mudou: já não é decisão em
  // aberto (ADR-0046 fixou `orcamentista` para a cadeia e o despacho, `aprovador` para a
  // assinatura, e a leitura aceita os dois), é que este código chega de QUALQUER rota da
  // jornada — nomear um papel aqui acertaria numa rota e mentiria nas outras. Quem tem
  // papel próprio a nomear é a assinatura, e ela tem código próprio
  // (`ESTIMATE_SELF_APPROVAL_FORBIDDEN`) ou tela própria.
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
  // Regime da rodada (ADR-0045): as duas recusas dizem o que aconteceria se a fonte
  // entrasse, e as duas declaram por extenso que nada foi gravado.
  ESTIMATE_CASCADE_ORIGIN_FORBIDDEN:
    "Esta rodada corre sob contrato licitado: a cascata só aceita a tabela do contrato (SCO). Uma fonte de outra origem produziria aqui um preço que a medição recusaria depois, sobre serviço já executado. Nada foi instalado e nada foi alterado.",
  ESTIMATE_REGIME_CASCADE_DIRTY:
    "Não é possível declarar esta rodada como demanda sob contrato enquanto a cascata tiver fonte fora da tabela contratual. Remova a fonte e declare de novo — nenhuma fonte é removida automaticamente, e a declaração não foi gravada.",
  ESTIMATE_REGIME_IRREVERSIBLE:
    "O regime é mão única: uma rodada declarada sob contrato licitado não volta para pré-licitação, e a ausência de regime já é a pré-licitação. Para orçar sob a outra regra, abra outra rodada.",
  // Acervo de tabelas da plataforma (F-037, ADR-0047). As três recusas são de INSTALAÇÃO,
  // e as três declaram que nada foi gravado — a lista que a tela leu pode ter envelhecido
  // entre a leitura e o clique, e é o servidor quem tem a versão de agora.
  REFERENCE_CATALOG_WITHDRAWN:
    "Esta tabela saiu de circulação depois que a lista foi lida; ela continua valendo nas rodadas que já a instalaram, mas não entra em nenhuma nova. Recarregue a lista e escolha outra — nada foi instalado.",
  REFERENCE_CATALOG_UNREADABLE:
    "O arquivo desta tabela do acervo não pôde ser lido pelo servidor; nada foi instalado. Avise quem administra a plataforma.",
  ESTIMATE_CATALOG_SOURCE_INVALID:
    "A instalação cita a tabela do acervo ou o arquivo próprio, nunca as duas e nunca nenhuma; nada foi instalado. Recarregue a tela e refaça a escolha.",
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
  ESTIMATE_PACKAGE_NOT_CLOSED:
    "Há item com pacote de serviços em aberto; o orçamento não é montado pela metade.",
  ESTIMATE_PACKAGE_NOT_SUPPORTED:
    "Item com mais de um código ainda não vira orçamento: a matriz de contribuições resolve o pacote.",
  CALC_CONTRIBUTION_WITHOUT_SOURCE_ITEM:
    "A parcela nasce de um elemento da prancha e precisa dizer de qual.",
  CALC_CONTRIBUTION_CODE_INVALID:
    "O código de origem da parcela não tem a forma de um código de catálogo.",
  // Coerência da parcela na matriz (ADR-0053, F-038): a base declarada e os campos que ela
  // exige precisam bater. As frases nomeiam a base para quem lê a recusa, nunca a cor.
  CALC_CONTRIBUTION_STANDALONE_WITH_ITEM:
    "Parcela de canteiro não nasce de elemento da prancha; ela não aponta para nenhum item.",
  CALC_CONTRIBUTION_DEPENDENT_WITHOUT_CODE:
    "Parcela derivada de outro serviço precisa dizer de qual código ela vem.",
  CALC_CONTRIBUTION_CODE_WITHOUT_DEPENDENCY:
    "Só parcela derivada de outro serviço cita um código de origem; esta base não é derivada.",
  // Matriz elemento × serviço: a leitura do artefato recusa duplicidade e ciclo, para a
  // memória ter ordem de cálculo. As três chegam como `DOMAIN_VALIDATION_FAILED`.
  CALC_MATRIX_DUPLICATE_CODE:
    "Há mais de um conjunto de contribuições para o mesmo serviço; cada código entra uma vez.",
  CALC_MATRIX_SELF_DEPENDENCY:
    "Um serviço não pode derivar de si mesmo; a memória não teria ordem de cálculo.",
  CALC_MATRIX_DEPENDENCY_CYCLE:
    "Há dependência cíclica entre serviços; a memória não tem ordem de cálculo. Desfaça o ciclo.",
  // Parcela PARCIAL (F-038 "decisão 6"): número declarado dentro do elemento, com nota e
  // teto. As duas frases nomeiam a regra por extenso — o servidor devolve os mesmos códigos.
  CALC_PARTIAL_EXCEEDS_ITEM:
    "A parcela parcial não pode passar da quantidade do elemento: os 170 m² de limpeza cabem dentro dos 418,12 do piso, nunca o contrário. Reduza o valor até o teto do elemento.",
  CALC_PARTIAL_NOTE_REQUIRED:
    "A parcela parcial é declarada, não recomputada: sem a nota que justifica o recorte, ela não é montada. Escreva de onde vem o número.",
  // Guardas locais da autoria da contribuição, para o rascunho incompleto não viajar. Não
  // são recusa do servidor — são o que falta preencher antes de salvar a parcela.
  CALC_BASIS_REQUIRED:
    "Escolha de onde vem a parcela (base da contribuição); nada é presumido por você.",
  CALC_RECIPE_REQUIRED:
    "Escolha a grandeza da parcela (a receita de cálculo) antes de salvar.",
  CALC_LABEL_REQUIRED:
    "A parcela precisa de um rótulo — é o texto que aparece na memória de cálculo.",
  CALC_OPERAND_REQUIRED:
    "A parcela precisa de ao menos um operando nomeado com valor.",
  CALC_OPERAND_INVALID:
    "Cada operando tem um nome e um valor decimal (escreva 20,00 ou 20.00); o valor viaja como texto para o servidor lê-lo exato.",
  // Dependência resolvida no build do orçamento (`error_prefix="ESTIMATE"`): a parcela
  // derivada aponta para um serviço que precisa existir no boletim e ter código confirmado.
  ESTIMATE_MATRIX_DEPENDENCY_UNKNOWN:
    "Uma parcela derivada aponta para um serviço que não está no orçamento; inclua-o ou corrija a origem.",
  ESTIMATE_MATRIX_DEPENDENCY_UNPRICED:
    "Uma parcela derivada aponta para um serviço sem código confirmado; confirme o código de origem antes.",
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
  // Aprovação nominal (F-035, ADR-0046). As duas primeiras são `403`/`409` da própria
  // rota de assinatura; as demais chegam no portão de domínio do despacho.
  ESTIMATE_SELF_APPROVAL_FORBIDDEN:
    "Quem montou este orçamento não pode aprová-lo: a assinatura tem de vir de outra pessoa com o papel aprovador. Acumular os dois papéis no mesmo acesso não muda essa regra, porque a comparação é de identidade e não de papel. Nada foi gravado — o orçamento segue montado e não assinado.",
  ESTIMATE_APPROVAL_AUTHOR_UNKNOWN:
    "Este orçamento não registra quem o montou, e sem isso não há contra quem conferir a segregação entre montar e assinar. Remonte o orçamento na etapa “BDI e montagem” antes de aprovar.",
  // Portão de domínio do despacho: o servidor recusa por TODAS as violações de uma vez, e a
  // lista inteira chega em `details.errors` do `ESTIMATE_EXPORT_BLOCKED`.
  ESTIMATE_EXPORT_BLOCKED:
    "O portão de despacho recusou este orçamento; nada foi publicado. Os motivos abertos estão listados abaixo.",
  ESTIMATE_NOT_APPROVED:
    "Este orçamento não tem aprovação nominal válida. Despachar é o passo depois de aprovar: aprove o orçamento e a planilha fica liberada.",
  ESTIMATE_APPROVAL_REJECTED:
    "A decisão registrada para este orçamento é de recusa, não de aprovação; orçamento recusado não é despachado.",
  APPROVAL_CONTENT_MISMATCH:
    "O orçamento mudou depois da aprovação. A aprovação registrada vale para o conteúdo aprovado, não para o atual — aprove o orçamento atual.",
  // Planilha: o portão fail-closed do ADR-0038.
  ESTIMATE_WORKBOOK_AUDIT_FAILED:
    "A auditoria recusou a planilha e nada foi publicado. O arquivo gerado foi descartado; a aprovação continua válida e o orçamento não mudou.",
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
