/**
 * Jornada da medição: prancha(s) → revisão do takeoff → códigos → praça → boletim →
 * aprovação e exportação.
 *
 * A etapa `praça` e o plural de `prancha` só existem a partir da SEGUNDA folha (F-046,
 * ADR-0057, decisão 8): a rodada de uma prancha responde exatamente como respondia antes,
 * sem faixa de folhas e sem etapa nova.
 *
 * A máquina de estados real é da API, e é ela quem recusa: folha repetida na praça
 * (`ROUND_PLATE_ALREADY_PRESENT`), extração em voo (`EXTRACTION_IN_PROGRESS`), sugestão de
 * código antes da revisão completa (`TAKEOFF_REVIEW_INCOMPLETE`), etapa fora de ordem
 * (`ROUND_STAGE_NOT_READY`), boletim com item confirmado sem código
 * (`CALC_ASSIGNMENT_MISSING`), re-decisão (`*_ALREADY_*`). Esta derivação apenas
 * **espelha** o estado da rodada já carregado (`GET /v1/valuation-rounds/{round_id}`),
 * para a tela mostrar uma etapa por vez com o motivo escrito em língua de obra. Nenhum
 * gate daqui substitui os do servidor: se as duas leituras discordarem, quem manda é a
 * recusa dele.
 *
 * Módulo puro: os motivos são frases de obra e precisam ser testáveis sem DOM e sem rede.
 */

import { extractionFailureMessage } from "./labels";
import { pracaPlural, recusaDaPraca } from "./praca";
import type {
  ApprovalState,
  RoundState,
  RoundStateExtraction,
  RoundStatePlate,
  WorksiteResponse,
} from "./api";

export type EtapaId =
  | "prancha"
  | "revisao"
  | "codigos"
  | "praca"
  | "boletim"
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
  "prancha",
  "revisao",
  "codigos",
  "boletim",
  "aprovacao",
];

const ETAPA_TITLES: Record<EtapaId, string> = {
  prancha: "Prancha",
  revisao: "Revisão do takeoff",
  codigos: "Códigos",
  praca: "Praça",
  boletim: "Boletim",
  aprovacao: "Aprovação e exportação",
};

/**
 * O título da primeira etapa é SINGULAR até a segunda folha existir (ADR-0057, decisão 8).
 *
 * A praça de uma folha continua exatamente como era: "Prancha", sem faixa e sem etapa
 * própria. O plural nasce no momento em que a segunda folha é acrescentada, e não antes.
 */
function tituloDaPrancha(plural: boolean): string {
  return plural ? "Pranchas" : ETAPA_TITLES.prancha;
}

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

/**
 * Resumo da etapa Prancha enquanto não há takeoff — a leitura da extração automática.
 *
 * A presença da prancha vem de `plate.present` (coluna da rodada) e o motivo da falha, do
 * `failure_code` traduzido: a API não manda mensagem pronta, e a frase de obra é escrita
 * aqui a partir do código estável.
 */
function pranchaSummarySemTakeoff(
  extraction: RoundStateExtraction,
  plate: RoundStatePlate,
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
        : "Nenhuma prancha enviada nesta rodada.";
  }
}

/** Motivo do bloqueio de revisão/códigos/boletim enquanto não há takeoff. */
function motivoSemTakeoff(
  extraction: RoundStateExtraction,
  plate: RoundStatePlate,
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
        : "a rodada ainda não tem prancha enviada; use a etapa Prancha para enviar";
  }
}

/** Resumo curto da etapa nova quando ainda não há o que aprovar. */
const SEM_MEDICAO_A_APROVAR = "Nada a aprovar: a medição ainda não foi montada.";

/**
 * O boletim gravado deixou de descrever a praça: quem diz isso é o servidor (`stale` do
 * bloco `bulletin`), comparando as fontes que geraram a medição com as de agora.
 */
export const BOLETIM_VENCIDO =
  "Boletim vencido: a rodada mudou depois de a medição ser montada; monte o boletim de novo.";

/** O que a aprovação em vigor perde ao boletim ser remontado. Preservar não é aprovar. */
export const REMONTAR_CADUCA_A_APROVACAO =
  "Esta medição está aprovada. Remontar não apaga a aprovação — ela continua registrada e " +
  "à vista —, mas ela passa a caducar: a exportação recusa até uma aprovação nova sobre o " +
  "conteúdo novo.";

/**
 * Resumo da etapa "Aprovação e exportação" a partir do bloco de aprovação do servidor.
 *
 * `approved` e `stale` são lidos JUNTOS: na aprovação caduca os dois valem ao mesmo tempo,
 * e um resumo que lesse só `approved` diria "aprovada" sobre uma medição que a exportação
 * já vai recusar. A ordem das perguntas é a do desenho aprovado — caduca primeiro, porque
 * ela é o estado que exige ato humano.
 */
function resumoDaAprovacao(approval: ApprovalState, workbookPresent: boolean): string {
  if (approval.stale) {
    return "Aprovação caduca: a medição mudou depois de aprovada; aprove a medição atual.";
  }
  if (!approval.approved) {
    return "Medição montada, aguardando aprovação nominal.";
  }
  return workbookPresent
    ? "Medição aprovada e boletim publicado nesta rodada."
    : "Medição aprovada; o boletim ainda não foi exportado.";
}

/**
 * A etapa da praça, entre Códigos e Boletim (pacote de design aprovado, decisão 2).
 *
 * Ela só existe na praça de VÁRIAS folhas, e o que a bloqueia é a recusa que o servidor já
 * declarou ao montar o consolidado — folha sem pacote, folha com item sem decisão. Nenhum
 * gate nasce aqui: `recusaDaPraca` só lê `consolidated` e as contagens por folha.
 */
function etapaDaPraca(worksite: WorksiteResponse): Etapa {
  const recusa = recusaDaPraca(worksite);
  const folhas = worksite.plates.length;
  if (recusa !== null) {
    return {
      id: "praca",
      title: ETAPA_TITLES.praca,
      status: "blocked",
      summary: `Praça de ${folhas} folhas; o consolidado ainda não fecha.`,
      blockedReason: recusa.folhas.length === 0
        ? "o consolidado da praça ainda não foi montado pelo servidor"
        : `falta terminar ${recusa.folhas.join("; ")}`,
    };
  }
  return {
    id: "praca",
    title: ETAPA_TITLES.praca,
    status: "available",
    summary: `Praça de ${folhas} folhas; consolidado montado sobre os pacotes das folhas.`,
  };
}

export function derivarEtapas(
  state: RoundState | null,
  worksite: WorksiteResponse | null = null,
): Jornada {
  if (state === null) {
    return semEstado("aguarda a leitura do estado da rodada");
  }
  const takeoff = state.takeoff;
  const extraction = state.extraction;
  const plate = state.plate;
  const variasFolhas = pracaPlural(worksite);
  const praca = variasFolhas && worksite !== null ? etapaDaPraca(worksite) : null;

  if (!takeoff.present) {
    const motivo = motivoSemTakeoff(extraction, plate);
    const etapas: Etapa[] = [
      {
        id: "prancha",
        title: tituloDaPrancha(variasFolhas),
        status: "available",
        summary: pranchaSummarySemTakeoff(extraction, plate),
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
      ...(praca === null ? [] : [praca]),
      {
        id: "boletim",
        title: ETAPA_TITLES.boletim,
        status: "blocked",
        summary: "Boletim ainda não montado.",
        blockedReason: motivo,
      },
      {
        id: "aprovacao",
        title: ETAPA_TITLES.aprovacao,
        status: "blocked",
        summary: SEM_MEDICAO_A_APROVAR,
        blockedReason: motivo,
      },
    ];
    return { etapas, etapaAtiva: "prancha" };
  }

  const prancha: Etapa = {
    id: "prancha",
    title: tituloDaPrancha(variasFolhas),
    status: "done",
    summary: variasFolhas
      ? `Praça de ${worksite?.plates.length ?? 0} folhas; a primeira já virou pacote de takeoff.`
      : "Prancha lida; legenda quantificada disponível para revisão.",
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

  // A etapa Boletim não antecipa mais o estado da aprovação: quem o declara é a etapa que
  // tem o bloco de aprovação do servidor em mãos. Dizer aqui "sem aprovação" mentiria
  // exatamente no caso em que a medição JÁ foi aprovada.
  //
  // `stale` é o boletim VENCIDO: o servidor comparou as fontes que o geraram com as de
  // agora e disse que já não são as mesmas. Ele nunca é deduzido aqui.
  const boletimVencido = state.bulletin.present && state.bulletin.stale;
  const boletim: Etapa = {
    id: "boletim",
    title: ETAPA_TITLES.boletim,
    status: "available",
    summary: boletimVencido
      ? BOLETIM_VENCIDO
      : state.bulletin.present
        ? "Medição gravada nesta rodada."
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
  } else if (state.bulletin.present && !boletimVencido) {
    // Boletim vencido continua "em aberto", e não "concluída": há um ato a fazer nele — o
    // de montá-lo de novo —, e etapa concluída é etapa da qual o orçamentista pode sair.
    boletim.status = "done";
  }
  // Praça de várias folhas com consolidado que não fecha bloqueia o boletim: meia praça
  // somada parece uma praça inteira (ADR-0057, decisão 7). Não é gate inventado aqui — é a
  // recusa que o servidor já declarou no consolidado, espelhada uma etapa adiante.
  if (praca !== null && praca.status === "blocked") {
    boletim.status = "blocked";
    boletim.blockedReason = praca.blockedReason;
  }

  // Aprovação e exportação: a etapa só existe sobre medição montada, e só fica "concluída"
  // quando há arquivo publicado — aprovar é metade do fechamento, e a jornada não declara
  // pronto o que ainda não entregou o boletim.
  const aprovacao: Etapa = {
    id: "aprovacao",
    title: ETAPA_TITLES.aprovacao,
    status: "available",
    summary: SEM_MEDICAO_A_APROVAR,
  };
  if (boletim.status === "blocked" || !state.bulletin.present) {
    aprovacao.status = "blocked";
    aprovacao.blockedReason =
      boletim.blockedReason ?? "aguarda a medição ser montada na etapa Boletim";
  } else {
    const approval = state.bulletin.approval;
    aprovacao.summary = resumoDaAprovacao(approval, state.bulletin.workbook_present);
    // Boletim vencido não deixa a jornada fechar: o arquivo publicado descreve a praça de
    // antes do último ato, e chamar isso de concluído é o mesmo erro de meia praça somada
    // parecer praça inteira. A assinatura anterior continua legível na etapa.
    if (
      approval.approved &&
      !approval.stale &&
      state.bulletin.workbook_present &&
      !boletimVencido
    ) {
      aprovacao.status = "done";
    }
  }

  const etapas = [
    prancha,
    revisao,
    codigos,
    ...(praca === null ? [] : [praca]),
    boletim,
    aprovacao,
  ];
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
