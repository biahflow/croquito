/**
 * Jornada da homologação: prancha → revisão do takeoff → códigos → boletim.
 *
 * A máquina de estados real é do servidor local, e ele é quem recusa: upload de segunda
 * prancha (`LOCAL_ROUND_ALREADY_HAS_PLATE`), extração em andamento
 * (`LOCAL_EXTRACTION_BUSY`), sugestão de código antes da revisão completa
 * (`LOCAL_TAKEOFF_REVIEW_INCOMPLETE`), boletim com item confirmado sem código
 * (`CALC_ASSIGNMENT_MISSING`), re-decisão (`*_ALREADY_*`). Esta derivação apenas
 * **espelha** o `GET /state` já carregado, para a tela mostrar uma etapa por vez com o
 * motivo escrito em língua de obra. Nenhum gate daqui substitui os do servidor: se as
 * duas leituras discordarem, quem manda é a recusa dele.
 *
 * Módulo puro: os motivos são frases de obra e precisam ser testáveis sem DOM e sem rede.
 */

import type { ExtractionState, RunState } from "./api";

export type EtapaId = "prancha" | "revisao" | "codigos" | "boletim";

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

const ETAPA_ORDER: EtapaId[] = ["prancha", "revisao", "codigos", "boletim"];

const ETAPA_TITLES: Record<EtapaId, string> = {
  prancha: "Prancha",
  revisao: "Revisão do takeoff",
  codigos: "Códigos",
  boletim: "Boletim",
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

const SEM_ESTADO = "Estado da rodada ainda não lido.";

function semEstado(reason: string): Jornada {
  return {
    etapas: ETAPA_ORDER.map((id) => ({
      id,
      title: ETAPA_TITLES[id],
      status: "blocked" as const,
      summary: SEM_ESTADO,
      blockedReason: reason,
    })),
    etapaAtiva: "prancha",
  };
}

/** Resumo da etapa Prancha enquanto não há takeoff — a leitura da extração automática. */
function pranchaSummarySemTakeoff(extracao: ExtractionState): string {
  switch (extracao.status) {
    case "running":
      return "Lendo a legenda da prancha…";
    case "failed":
      return extracao.message ?? "A extração automática da prancha falhou.";
    case "unavailable":
      return extracao.message ?? "Extração automática indisponível no servidor.";
    default:
      return extracao.plate_pdf_present
        ? "Prancha ingerida; a extração automática ainda não foi disparada."
        : "Nenhuma prancha enviada nesta rodada.";
  }
}

/** Motivo do bloqueio de revisão/códigos/boletim enquanto não há takeoff. */
function motivoSemTakeoff(extracao: ExtractionState): string {
  switch (extracao.status) {
    case "running":
      return "a extração automática da prancha está em andamento";
    case "failed":
      return extracao.message ?? "a extração automática da prancha falhou";
    case "unavailable":
      return extracao.message ?? "a extração automática está indisponível no servidor";
    default:
      return "a rodada ainda não tem prancha enviada; use a etapa Prancha para enviar";
  }
}

export function derivarEtapas(state: RunState | null): Jornada {
  if (state === null) {
    return semEstado("aguarda a leitura do estado da rodada");
  }
  const takeoff = state.takeoff;
  const extracao = state.extracao;

  if (!takeoff.present) {
    const motivo = motivoSemTakeoff(extracao);
    const etapas: Etapa[] = [
      {
        id: "prancha",
        title: ETAPA_TITLES.prancha,
        status: "available",
        summary: pranchaSummarySemTakeoff(extracao),
      },
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
        id: "boletim",
        title: ETAPA_TITLES.boletim,
        status: "blocked",
        summary: "Boletim ainda não montado.",
        blockedReason: motivo,
      },
    ];
    return { etapas, etapaAtiva: "prancha" };
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
        ? `${state.codes.confirmed} códigos confirmados, ${state.codes.rejected} sem código no contrato.`
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
      "nenhum item foi confirmado no takeoff; não há quantitativo a codificar";
  } else if (codigosPendentes === 0) {
    codigos.status = "done";
  }

  const boletim: Etapa = {
    id: "boletim",
    title: ETAPA_TITLES.boletim,
    status: "available",
    summary: state.bulletin.present
      ? "Medição gravada nesta rodada, sem aprovação."
      : "Boletim ainda não montado.",
  };
  if (codigos.status !== "done") {
    boletim.status = "blocked";
    boletim.blockedReason = revisaoCompleta
      ? confirmed === 0
        ? "nenhum item confirmado no takeoff"
        : `aguarda a decisão de código de ${plural(
            codigosPendentes,
            "item",
            "itens",
          )}`
      : `aguarda ${plural(pending, "item", "itens")} da revisão do takeoff`;
  } else if (state.bulletin.present) {
    boletim.status = "done";
  }

  const etapas = [prancha, revisao, codigos, boletim];
  // A ativa é a primeira em aberto. Com tudo concluído (ou o que resta bloqueado), fica
  // na última alcançável em vez de abrir uma etapa bloqueada.
  const aberta = etapas.find((etapa) => etapa.status === "available");
  const ultimaAlcancavel = [...etapas]
    .reverse()
    .find((etapa) => etapa.status !== "blocked");
  return {
    etapas,
    etapaAtiva: aberta?.id ?? ultimaAlcancavel?.id ?? "prancha",
  };
}
