/**
 * Rótulos e mensagens da jornada de plataforma, em português como o resto do produto.
 *
 * Duas regras da casa moram aqui. A primeira: **estado é texto**, nunca só cor — "ativo",
 * "revogado" e "nunca autorizado" aparecem escritos, e nenhuma marca visual carrega
 * sozinha o significado. A segunda: a recusa do servidor chega com **código estável**, e é
 * o código que escolhe a frase; código desconhecido nunca vira mensagem inventada — sobra
 * a frase que o transporte montou, com o código dentro dela.
 */

import { ApiError } from "../api";
import type {
  Journey,
  JourneyAvailability,
  JourneyEntitlement,
  JourneyState,
  PlatformTenant,
} from "./api";

/** O que esta tela é e o que ela não é; fica visível acima da lista. */
export const AVISO_PLATAFORMA =
  "Autorização contratual de processamento por IA, por tenant. Ativar aqui libera o " +
  "envio de documentos daquele tenant aos provedores; a referência do contrato é o " +
  "registro do porquê. Nenhum documento é enviado por esta tela.";

/** Por que existe um campo de texto livre, e não só a lista. */
export const AVISO_TENANT_NOVO =
  "A lista mostra tenants com pegada no banco (autorização, projeto ou upload). Um " +
  "tenant que existe só no provedor de identidade ainda não aparece aqui — ative-o pelo " +
  "identificador exato do token (claim de tenant).";

/** Como a referência do contrato é usada; ela é obrigatória para ativar. */
export const DICA_REFERENCIA =
  "Referência lógica do contrato ou aditivo que autoriza o processamento (3 a 128 " +
  "caracteres). Ela fica gravada com quem autorizou e quando.";

/** O que a revogação faz — e o que ela não desfaz. */
export const AVISO_REVOGACAO =
  "Revogar bloqueia envios novos daquele tenant a partir de agora. O que já foi " +
  "processado continua como está, e a referência do contrato que autorizou permanece " +
  "gravada.";

/** Falha que não chegou a ser recusa da API: nem código estável há para citar. */
export const MENSAGEM_REDE =
  "Não foi possível falar com a API. Nada foi gravado — confira a conexão e tente de novo.";

/** Estado da lista antes de qualquer resposta; nenhum tenant é fabricado. */
export const MENSAGEM_SEM_LEITURA = "A lista de tenants ainda não foi lida.";

/** A união não devolveu tenant nenhum; é resultado, não falha. */
export const MENSAGEM_LISTA_VAZIA =
  "Nenhum tenant com pegada no banco ainda. Ative pelo identificador abaixo.";

/** Sem sessão não há plataforma: toda rota daqui é autenticada e exige papel. */
export const MENSAGEM_SEM_SESSAO =
  "Entre para administrar a autorização contratual — as rotas de plataforma são " +
  "autenticadas e exigem o papel de operador.";

const MENSAGENS_POR_CODIGO: Record<string, string> = {
  FORBIDDEN:
    "Sua conta não tem o papel de operador de plataforma. Administrar autorização " +
    "contratual exige esse papel — peça a quem opera a plataforma. Nada foi alterado.",
  AGREEMENT_REFERENCE_REQUIRED:
    "Ativar exige a referência do contrato que autoriza o processamento. Nada foi " +
    "gravado — escreva a referência e confirme de novo.",
  NOT_FOUND:
    "Este tenant nunca teve autorização contratual criada, então não há o que revogar.",
  IDEMPOTENCY_KEY_REQUIRED:
    "A chamada saiu sem chave de idempotência e foi recusada. Nada foi gravado; " +
    "confirme de novo.",
  IDEMPOTENCY_KEY_REUSED:
    "Esta chave de idempotência já foi usada com outro comando. Nada foi gravado; " +
    "recarregue a lista e confirme de novo.",
};

/**
 * Frase estável de um código de recusa, ou `null` quando o código não é conhecido aqui.
 * Devolver `null` é o que impede a tela de inventar explicação para código novo.
 */
export function errorMessage(code: string): string | null {
  return MENSAGENS_POR_CODIGO[code] ?? null;
}

/**
 * Frase de uma recusa qualquer.
 *
 * Código conhecido escolhe o texto; código desconhecido cai na frase que o transporte
 * montou — que já traz o código e o `detail` do servidor, e que carrega a copy aprovada
 * do 401 sem tenant. O que não é `ApiError` não chegou a ser resposta: é rede, e é assim
 * que aparece, sem stack e sem jargão de exceção na tela.
 */
export function describeError(error: unknown): string {
  if (error instanceof ApiError) {
    const frase = error.code === null ? null : errorMessage(error.code);
    return frase ?? error.message;
  }
  return MENSAGEM_REDE;
}

/**
 * Estado do entitlement por extenso. São três, não dois: o tenant que nunca foi
 * autorizado e o que teve a autorização revogada estão ambos com `enabled: false`, e
 * tratá-los como a mesma coisa esconderia do operador se houve ou não um ato antes.
 */
export function estadoLabel(tenant: PlatformTenant): string {
  if (tenant.enabled) {
    return "ativo";
  }
  return tenant.authorized_at === null ? "nunca autorizado" : "revogado";
}

/**
 * Data e hora em pt-BR, no fuso de quem está lendo a tela.
 *
 * Cópia deliberada da mesma regra em `medicao/format.ts`: as jornadas não se importam
 * umas às outras (só o transporte em `../api` é comum), e acoplar a plataforma ao módulo
 * de formatação da medição faria uma jornada quebrar a outra. Texto não reconhecível como
 * data volta como veio — o carimbo do servidor nunca é adivinhado.
 */
export function formatarInstante(value: string | null): string {
  if (value === null) {
    return "—";
  }
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return value;
  }
  const pad = (part: number) => String(part).padStart(2, "0");
  return (
    `${pad(parsed.getDate())}/${pad(parsed.getMonth() + 1)}/${parsed.getFullYear()}` +
    ` ${pad(parsed.getHours())}:${pad(parsed.getMinutes())}`
  );
}

// --------------------------------------------------------------------------------------
// Disponibilidade de jornada por tenant (F-034, fatia 2)
//
// Toda a copy desta seção vem do Design Approval Package revisão 1, aprovado por ato
// humano em 2026-08-22. O registro de aprovação diz explicitamente que o TEXTO não foi
// aprovado — ele é proposta e segue pendente de um gate próprio.

/**
 * Nome de cada jornada na tela. Vem do seletor que já existe (`App.tsx`) e não é decidido
 * aqui: o pacote aprovado exclui o nome das jornadas do que ele aprova.
 */
export const JORNADA_LABEL: Record<Journey, string> = {
  croqui: "Croqui",
  medicao: "Medição",
  orcamento: "Orçamento",
};

/**
 * Estado do ambiente por extenso. Cor nunca é o único indicador: a palavra fica ao lado da
 * pastilha, e é ela que carrega o significado.
 */
export const ESTADO_JORNADA_LABEL: Record<JourneyState, string> = {
  enabled: "LIBERADA",
  pilot: "PILOTO",
  disabled: "INDISPONÍVEL",
};

/**
 * Pastilha de cada estado. `ready` e `blocked` já existem na folha; `neutral` é o único
 * valor visual novo do pacote aprovado (lá chamado `.neutro`), e existe porque as duas
 * pastilhas atuais são "positivo" e "atenção" — um módulo que não existe neste ambiente
 * não é nenhum dos dois.
 */
export const ESTADO_JORNADA_CLASSE: Record<JourneyState, string> = {
  enabled: "ready",
  pilot: "blocked",
  disabled: "neutral",
};

/**
 * O que a seção é. A ênfase em "piloto" é do pacote aprovado, então a frase é entregue em
 * três pedaços em vez de virar HTML dentro de uma string.
 */
export const AVISO_DISPONIBILIDADE = {
  antes:
    "O estado de cada jornada é declarado no ambiente e não se edita por aqui. Em ",
  enfase: "piloto",
  depois:
    ", a jornada existe só para os clientes autorizados abaixo — é onde esta tela age.",
} as const;

/** Por que não há interruptor de estado nesta tela. */
export const AVISO_ESTADO_NAO_EDITAVEL =
  "Mudar o estado de uma jornada é alterar a configuração do ambiente e publicar — não é " +
  "ato de tela.";

/** O que o formulário faz e o que ele grava junto. */
export const DICA_AUTORIZAR_PILOTO =
  "Só jornadas em piloto aceitam autorização. A referência do contrato fica gravada com " +
  "quem autorizou e quando.";

/** Leitura em curso: o texto diz o que está acontecendo, e o botão não engana. */
export const MENSAGEM_JORNADAS_CARREGANDO = "Lendo a lista de autorizações…";

/** O formulário durante a leitura: ele ainda não sabe quais jornadas estão em piloto. */
export const DICA_JORNADAS_CARREGANDO =
  "Aguardando a lista para saber quais jornadas estão em piloto.";

/** Depois de uma recusa: o que fazer, e a garantia de que nada foi gravado. */
export const DICA_APOS_RECUSA = "Corrija a jornada e tente de novo. Nada foi gravado.";

/** Conta sem `platform_operator`: lê o motivo, não uma tela em branco. */
export const MENSAGEM_JORNADAS_SEM_PAPEL =
  "Esta área é administrada por quem tem o papel de plataforma. Sua conta não o tem, " +
  "então a lista não é carregada e nenhuma autorização pode ser concedida por aqui.";

/** O que fazer a respeito. */
export const DICA_JORNADAS_SEM_PAPEL =
  "Peça o acesso a quem administra a plataforma.";

/** Resumo do ambiente: quantas jornadas existem e quantas estão em piloto. */
export function resumoDoAmbiente(journeys: JourneyAvailability[]): string {
  const pilotos = journeys.filter((entry) => entry.state === "pilot").length;
  const jornadas = `${journeys.length} jornada${journeys.length === 1 ? "" : "s"}`;
  return `${jornadas} · ${pilotos} em piloto`;
}

/**
 * A lista vazia não some, ela explica — e a explicação nomeia a consequência: enquanto
 * ninguém for autorizado, a jornada em piloto não existe para tenant nenhum.
 */
export function mensagemSemAutorizacao(journeys: JourneyAvailability[]): string {
  const pilotos = journeys
    .filter((entry) => entry.state === "pilot")
    .map((entry) => JORNADA_LABEL[entry.journey]);
  if (pilotos.length === 0) {
    return (
      "Nenhuma jornada está em piloto neste ambiente, então não há autorização a " +
      "conceder por aqui."
    );
  }
  const nomes =
    pilotos.length === 1
      ? `a jornada ${pilotos[0]}`
      : `as jornadas ${pilotos.slice(0, -1).join(", ")} e ${pilotos[pilotos.length - 1]}`;
  return (
    "Nenhum cliente autorizado em jornada de piloto. Enquanto isso, " +
    `${nomes} não existe para nenhum tenant.`
  );
}

/** Estado de uma autorização por extenso, na linha da lista. */
export function estadoDaAutorizacao(entitlement: JourneyEntitlement): string {
  const jornada = JORNADA_LABEL[entitlement.journey];
  return entitlement.enabled
    ? `${jornada} · piloto autorizado`
    : `${jornada} · autorização revogada`;
}

/**
 * Frase por extenso da recusa de jornada fora do piloto.
 *
 * A jornada e o estado vêm do `details` que o SERVIDOR declarou na recusa, e não do que a
 * tela achava que sabia: a lista carregada pode estar velha, e a frase precisa descrever o
 * que de fato barrou o ato.
 */
export function mensagemForaDoPiloto(
  journey: Journey,
  state: JourneyState,
): string {
  const jornada = JORNADA_LABEL[journey];
  const motivo =
    state === "enabled"
      ? "ela já existe para todos os clientes"
      : "ela não existe aqui";
  return (
    `A jornada ${jornada} não está em piloto neste ambiente: ${motivo}, e autorizar ` +
    "um cliente nela não teria efeito."
  );
}

/**
 * Frase de uma recusa da administração de jornada.
 *
 * `JOURNEY_NOT_IN_PILOT` é o único código composto: ele precisa nomear a jornada e o
 * estado, que só existem no `details` da recusa. Sem os dois fatos declarados, a frase não
 * é inventada — cai no caminho comum, que já cita o código.
 */
export function describeJourneyError(error: unknown): string {
  if (error instanceof ApiError && error.code === "JOURNEY_NOT_IN_PILOT") {
    const { journey, state } = error.details;
    if (
      typeof journey === "string" &&
      journey in JORNADA_LABEL &&
      typeof state === "string" &&
      state in ESTADO_JORNADA_LABEL
    ) {
      return mensagemForaDoPiloto(journey as Journey, state as JourneyState);
    }
  }
  return describeError(error);
}
