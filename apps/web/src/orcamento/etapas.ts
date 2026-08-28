/**
 * Jornada do orçamento-base: cascata → prancha → revisão do takeoff → códigos → BDI e
 * montagem → aprovação e despacho.
 *
 * A última etapa SUBSTITUIU "Planilha" na F-035 (ADR-0046, e a questão 1 do pacote de
 * design aprovado em 2026-08-22), não foi acrescentada depois dela: com a montagem
 * deixando de publicar, a planilha passa a nascer do despacho, e uma etapa sobre um arquivo
 * que ainda não existe não teria o que mostrar.
 *
 * A máquina de estados real é da API, e é ela quem recusa: cascata vazia e etapa fora de
 * ordem (`ROUND_STAGE_NOT_READY`), segunda prancha (`ROUND_PLATE_ALREADY_PRESENT`),
 * extração em voo (`EXTRACTION_IN_PROGRESS`), sugestão antes da revisão completa
 * (`TAKEOFF_REVIEW_INCOMPLETE`), montagem sem decisão de código
 * (`ESTIMATE_ASSIGNMENT_MISSING`), re-decisão (`*_ALREADY_*`), reordenação depois da
 * primeira decisão (`ESTIMATE_CASCADE_LOCKED`). Esta derivação apenas **espelha** o
 * estado da rodada já carregado (`GET /v1/estimate-rounds/{round_id}`), para a tela
 * mostrar uma etapa por vez com o motivo escrito em língua de obra. Nenhum gate daqui
 * substitui os do servidor: se as duas leituras discordarem, quem manda é a recusa dele.
 *
 * Uma exceção é declarada, e é declarada por ser exceção: a etapa **Prancha** aparece
 * bloqueada enquanto a cascata está vazia, e o servidor não recusa associar prancha nesse
 * estado. É ordem da JORNADA (a composição aprovada da F-020 abre pela cascata), não
 * afirmação sobre uma recusa do servidor — e ela nunca impede o ato: quem instalar a
 * fonte depois encontra a etapa aberta com a prancha já associada.
 *
 * Módulo puro: os motivos são frases de obra e precisam ser testáveis sem DOM e sem rede.
 */

import { extractionFailureMessage } from "./labels";
import type {
  ApprovalState,
  EstimateState,
  EstimateStateExtraction,
  EstimateStatePlate,
} from "./api";

export type EtapaId =
  | "cascata"
  | "prancha"
  | "revisao"
  | "codigos"
  | "montagem"
  | "aprovacao";

export type EtapaStatus = "blocked" | "available" | "done";

export type Etapa = {
  id: EtapaId;
  title: string;
  status: EtapaStatus;
  /** Resumo curto da etapa; é o que o cartão recolhido mostra. */
  summary: string;
  /** Motivo do bloqueio, presente somente quando a etapa está bloqueada. */
  blockedReason?: string;
};

export type Jornada = {
  etapas: Etapa[];
  /** Primeira etapa em aberto; etapa bloqueada nunca é a ativa. */
  etapaAtiva: EtapaId;
};

const ETAPA_ORDER: EtapaId[] = [
  "cascata",
  "prancha",
  "revisao",
  "codigos",
  "montagem",
  "aprovacao",
];

const ETAPA_TITLES: Record<EtapaId, string> = {
  cascata: "Cascata",
  prancha: "Prancha",
  revisao: "Revisão do takeoff",
  codigos: "Códigos",
  montagem: "BDI e montagem",
  aprovacao: "Aprovação e despacho",
};

const STATUS_LABELS: Record<EtapaStatus, string> = {
  blocked: "bloqueada",
  available: "em aberto",
  done: "concluída",
};

/** Estado da etapa em texto: marca e cor nunca são o único indicador. */
export function etapaStatusLabel(status: EtapaStatus): string {
  return STATUS_LABELS[status];
}

function plural(count: number, singular: string, many: string): string {
  return `${count} ${count === 1 ? singular : many}`;
}

const SEM_ESTADO = "Estado do orçamento ainda não lido.";

const MOTIVO_SEM_CASCATA =
  "a cascata ainda não tem fonte de preço; sem ela o orçamento não precifica nada";

function semEstado(reason: string): Jornada {
  return {
    etapas: ETAPA_ORDER.map((id) => ({
      id,
      title: ETAPA_TITLES[id],
      status: "blocked" as const,
      summary: SEM_ESTADO,
      blockedReason: reason,
    })),
    etapaAtiva: "cascata",
  };
}

/**
 * Resumo da etapa Prancha enquanto não há takeoff — a leitura da extração automática.
 *
 * A presença da prancha vem de `plate.present` (coluna da rodada) e o motivo da falha, do
 * `failure_code` traduzido: a API não manda mensagem pronta, e a frase de obra é escrita
 * a partir do código estável.
 */
function pranchaSummarySemTakeoff(
  extraction: EstimateStateExtraction,
  plate: EstimateStatePlate,
): string {
  switch (extraction.status) {
    case "queued":
      return "Leitura da legenda enfileirada; aguardando o processamento.";
    case "running":
      return "Lendo a legenda da prancha…";
    case "failed":
      return extractionFailureMessage(extraction.failure_code);
    default:
      return plate.present
        ? "Prancha enviada; a leitura automática ainda não foi disparada."
        : "Nenhuma prancha enviada neste orçamento.";
  }
}

/** Resumo curto da etapa nova enquanto ainda não há o que assinar. */
const SEM_ORCAMENTO_A_APROVAR = "Nada a aprovar: o orçamento ainda não foi montado.";

/**
 * Orçamento montado cujo bloco de aprovação não veio na leitura.
 *
 * O bloco só some quando o documento gravado deixou de validar no domínio
 * (`approval_state` devolve dicionário vazio nesse caso). Declarar a ausência é a única
 * resposta honesta: dizer "aguardando aprovação" afirmaria sobre uma assinatura que a tela
 * não leu, e dizer "aprovado" seria pior ainda.
 */
const SEM_LEITURA_DA_APROVACAO =
  "Orçamento montado, e o estado da assinatura não veio nesta leitura; recarregue o estado atual.";

/**
 * Resumo da etapa "Aprovação e despacho" a partir do bloco de aprovação do servidor.
 *
 * `approved` e `stale` são lidos JUNTOS: na aprovação caduca os dois valem ao mesmo tempo,
 * e um resumo que lesse só `approved` diria "aprovado" sobre um orçamento que o despacho já
 * vai recusar. A ordem das perguntas é a do desenho aprovado — caduca primeiro, porque ela
 * é o estado que exige ato humano.
 */
function resumoDaAprovacao(
  approval: ApprovalState,
  workbookPresent: boolean,
): string {
  if (approval.stale) {
    return "Aprovação caduca: o orçamento mudou depois de aprovado; aprove o orçamento atual.";
  }
  if (!approval.approved) {
    return "Orçamento montado, aguardando aprovação nominal.";
  }
  return workbookPresent
    ? "Orçamento aprovado e planilha despachada nesta rodada."
    : "Orçamento aprovado; a planilha ainda não foi despachada.";
}

/** Motivo do bloqueio das etapas seguintes enquanto não há takeoff. */
function motivoSemTakeoff(
  extraction: EstimateStateExtraction,
  plate: EstimateStatePlate,
): string {
  switch (extraction.status) {
    case "queued":
      return "a leitura automática da legenda está na fila";
    case "running":
      return "a leitura automática da legenda está em andamento";
    case "failed":
      return extractionFailureMessage(extraction.failure_code);
    default:
      return plate.present
        ? "a prancha ainda não virou pacote de takeoff; dispare a leitura automática na etapa Prancha"
        : "o orçamento ainda não tem prancha enviada; use a etapa Prancha para enviar";
  }
}

/**
 * A tela deve buscar a shortlist de códigos agora?
 *
 * Existe porque essa lista NÃO tem botão: ela é carregada sozinha, e a decisão de quando
 * pedi-la é regra de jornada, não detalhe de um `useEffect`.
 *
 * Duas condições, e as duas importam. Já existir shortlist gravada é motivo óbvio. Não
 * existir só autoriza o pedido quando a revisão do takeoff está **completa**: é a mesma
 * condição que a rota exige (`require_reviewed_packet`), e pedir antes dela é recusa
 * garantida (`TAKEOFF_REVIEW_INCOMPLETE`) — repetida a cada volta do poll do estado.
 *
 * Pedir é seguro como efeito de abrir a tela: o `GET` roda sem braço semântico, então não
 * gasta, e grava sem avançar a versão, então não provoca `409` na decisão seguinte
 * (ADR-0054 D7). O recálculo, esse sim pago e versionado, continua sendo ato humano.
 */
export function deveCarregarSugestoes(state: EstimateState | null): boolean {
  if (state === null) {
    return false;
  }
  return state.codes.suggestions_present || state.takeoff.review_status === "complete";
}

export function derivarEtapas(state: EstimateState | null): Jornada {
  if (state === null) {
    return semEstado("aguarda a leitura do estado do orçamento");
  }
  const { cascade, takeoff, extraction, plate } = state;
  const cascataInstalada = cascade.length > 0;

  const cascata: Etapa = {
    id: "cascata",
    title: ETAPA_TITLES.cascata,
    status: cascataInstalada ? "done" : "available",
    summary: cascataInstalada
      ? `${plural(cascade.length, "fonte instalada", "fontes instaladas")}, na ordem: ${cascade
          .map((entry) => entry.origin)
          .join(" → ")}.`
      : "Nenhuma fonte de preço instalada neste orçamento.",
  };

  if (!takeoff.present) {
    const motivo = motivoSemTakeoff(extraction, plate);
    const prancha: Etapa = {
      id: "prancha",
      title: ETAPA_TITLES.prancha,
      status: cascataInstalada ? "available" : "blocked",
      summary: pranchaSummarySemTakeoff(extraction, plate),
    };
    if (!cascataInstalada) {
      prancha.blockedReason = MOTIVO_SEM_CASCATA;
    }
    const bloqueadas: Etapa[] = [
      {
        id: "revisao",
        title: ETAPA_TITLES.revisao,
        status: "blocked",
        summary: "Aguarda a prancha virar pacote de takeoff.",
        blockedReason: motivo,
      },
      {
        id: "codigos",
        title: ETAPA_TITLES.codigos,
        status: "blocked",
        summary: "Aguarda o fim da revisão do takeoff.",
        blockedReason: motivo,
      },
      {
        id: "montagem",
        title: ETAPA_TITLES.montagem,
        status: "blocked",
        summary: "Orçamento ainda não montado.",
        blockedReason: motivo,
      },
      {
        id: "aprovacao",
        title: ETAPA_TITLES.aprovacao,
        status: "blocked",
        summary: SEM_ORCAMENTO_A_APROVAR,
        blockedReason: motivo,
      },
    ];
    const etapas = [cascata, prancha, ...bloqueadas];
    const aberta = etapas.find((etapa) => etapa.status === "available");
    return { etapas, etapaAtiva: aberta?.id ?? "cascata" };
  }

  const prancha: Etapa = {
    id: "prancha",
    title: ETAPA_TITLES.prancha,
    status: "done",
    summary: "Prancha lida; legenda quantificada disponível para revisão.",
  };

  const total = takeoff.items ?? 0;
  const pending = takeoff.pending ?? 0;
  const confirmed = takeoff.confirmed ?? 0;
  const rejected = takeoff.rejected ?? 0;
  const revisaoCompleta = takeoff.review_status === "complete";

  const revisao: Etapa = {
    id: "revisao",
    title: ETAPA_TITLES.revisao,
    status: revisaoCompleta ? "done" : "available",
    summary: revisaoCompleta
      ? `Revisão completa: ${confirmed} confirmados, ${rejected} rejeitados.`
      : `${total - pending} de ${plural(total, "item decidido", "itens decididos")}.`,
  };

  // `pending` do servidor é "item confirmado no takeoff ainda sem decisão de código";
  // ele só é `null` quando não há pacote, caso já tratado acima.
  const codigosPendentes = state.codes.pending ?? 0;
  const codigos: Etapa = {
    id: "codigos",
    title: ETAPA_TITLES.codigos,
    status: "available",
    summary: revisaoCompleta
      ? codigosPendentes === 0
        ? `${state.codes.confirmed} códigos confirmados, ${state.codes.rejected} sem preço na cascata.`
        : `Revisão completa, ${plural(
            codigosPendentes,
            "código pendente",
            "códigos pendentes",
          )}.`
      : "Aguarda o fim da revisão do takeoff.",
  };
  if (!revisaoCompleta) {
    codigos.status = "blocked";
    codigos.blockedReason = `${plural(
      pending,
      "item ainda sem decisão",
      "itens ainda sem decisão",
    )} no takeoff`;
  } else if (confirmed === 0) {
    codigos.status = "blocked";
    codigos.blockedReason =
      "nenhum item foi confirmado no takeoff; não há quantitativo a precificar";
  } else if (codigosPendentes === 0) {
    codigos.status = "done";
  }

  const montagem: Etapa = {
    id: "montagem",
    title: ETAPA_TITLES.montagem,
    status: "available",
    summary: state.estimate.present
      ? "Orçamento montado nesta rodada."
      : "BDI ainda não declarado; orçamento não montado.",
  };
  if (!cascataInstalada) {
    montagem.status = "blocked";
    montagem.blockedReason = MOTIVO_SEM_CASCATA;
  } else if (codigos.status !== "done") {
    montagem.status = "blocked";
    montagem.blockedReason = revisaoCompleta
      ? confirmed === 0
        ? "nenhum item confirmado no takeoff"
        : `aguarda a decisão de código de ${plural(codigosPendentes, "item", "itens")}`
      : `aguarda ${plural(pending, "item", "itens")} da revisão do takeoff`;
  } else if (state.estimate.present) {
    montagem.status = "done";
  }

  // Aprovação e despacho: a etapa só existe sobre orçamento montado, e só fica "concluída"
  // quando há planilha despachada — assinar é metade do fechamento, e a jornada não declara
  // pronto o que ainda não entregou o arquivo.
  const aprovacao: Etapa = {
    id: "aprovacao",
    title: ETAPA_TITLES.aprovacao,
    status: "available",
    summary: SEM_ORCAMENTO_A_APROVAR,
  };
  if (montagem.status === "blocked" || !state.estimate.present) {
    aprovacao.status = "blocked";
    aprovacao.blockedReason =
      montagem.blockedReason ??
      "o orçamento ainda não foi montado na etapa BDI e montagem";
  } else {
    const approval = state.approval;
    aprovacao.summary =
      approval === undefined
        ? SEM_LEITURA_DA_APROVACAO
        : resumoDaAprovacao(approval, state.estimate.workbook_present);
    if (
      approval !== undefined &&
      approval.approved &&
      !approval.stale &&
      state.estimate.workbook_present
    ) {
      aprovacao.status = "done";
    }
  }

  const etapas = [cascata, prancha, revisao, codigos, montagem, aprovacao];
  // A ativa é a primeira em aberto. Com tudo concluído (ou o que resta bloqueado), fica
  // na última alcançável em vez de abrir uma etapa bloqueada.
  const aberta = etapas.find((etapa) => etapa.status === "available");
  const ultimaAlcancavel = [...etapas]
    .reverse()
    .find((etapa) => etapa.status !== "blocked");
  return {
    etapas,
    etapaAtiva: aberta?.id ?? ultimaAlcancavel?.id ?? "cascata",
  };
}
