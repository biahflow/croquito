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
import type { PlatformTenant } from "./api";

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
