/**
 * Classificação pura das recusas da API do orçamento-base: qual delas é o convite a
 * recarregar, qual é a falta de autorização que ganha tela própria, qual código escolhe a
 * frase de obra, e quando um erro é só o cancelamento de uma busca anterior pelo
 * `AbortController` — nunca falha de rede.
 *
 * Nada aqui inventa mensagem: o servidor manda código estável e `labels.ts` traduz por
 * tabela. Resposta sem envelope legível devolve o que o transporte montou.
 */

import { ApiError } from "../api";
import {
  errorMessage,
  fraseCodigosAusentes,
  fraseParametrosFaltantes,
  MENSAGEM_ORCAMENTO_MUDOU,
} from "./labels";

/** O `409` da guarda otimista da rodada de orçamento. */
export const REVISION_CONFLICT_CODE = "REVISION_CONFLICT";

/** Invariante de `packages/valuation` viaja DENTRO deste código, em `details.code`. */
export const DOMAIN_VALIDATION_CODE = "DOMAIN_VALIDATION_FAILED";

/** Falta do papel que autoriza a jornada; ganha tela própria, sem nomear papel nenhum. */
export const FORBIDDEN_CODE = "FORBIDDEN";

/** Auditoria de round-trip reprovada: nada foi publicado (ADR-0038). */
export const WORKBOOK_AUDIT_FAILED_CODE = "ESTIMATE_WORKBOOK_AUDIT_FAILED";

/**
 * Quem montou o orçamento não o assina (ADR-0046, decisão 6). É `403`, como a falta de
 * papel, e **não** é a falta de papel: a comparação é de identidade, e acumular
 * `orcamentista` e `aprovador` no mesmo token não contorna.
 */
export const SELF_APPROVAL_FORBIDDEN_CODE = "ESTIMATE_SELF_APPROVAL_FORBIDDEN";

/** Portão de domínio do despacho: viaja em `details.code` do `DOMAIN_VALIDATION_FAILED`. */
export const EXPORT_BLOCKED_CODE = "ESTIMATE_EXPORT_BLOCKED";

/**
 * As duas recusas próprias do acervo de canteiro (F-042), as duas em falha fechada.
 *
 * A primeira traz em `details.parameters` a lista de TODOS os parâmetros faltantes; a
 * segunda, em `details.codes`, os códigos que o catálogo da rodada não tem. Nenhuma das
 * duas materializa parcela nenhuma — nem as que estariam completas.
 */
export const SITE_SETUP_PARAMETER_MISSING_CODE = "SITE_SETUP_PARAMETER_MISSING";
export const SITE_SETUP_CODE_ABSENT_CODE = "SITE_SETUP_CODE_ABSENT";

/**
 * Binding de autoria que aponta para operando que a rodada não tem (F-042 T6).
 *
 * `details.bindings` traz as chaves recusadas — `"0.SEMANAS"` —, e é por elas que a tela
 * marca o campo exato em vez de dizer que "algo está errado". Um binding ignorado congelaria
 * como constante um número que a orçamentista quis declarar, e o acervo nasceria errado sem
 * ninguém ver; o servidor recusa nomeando, e a tela repete o nome.
 */
export const SITE_SETUP_BINDING_INVALID_CODE = "SITE_SETUP_BINDING_INVALID";

/**
 * O orçamento avançou depois desta leitura. Não é falha: é o sinal de recarregar antes de
 * refazer o ato — outra aba, outra pessoa ou o worker mexeram na rodada.
 */
export function isRevisionConflict(error: unknown): boolean {
  return error instanceof ApiError && error.code === REVISION_CONFLICT_CODE;
}

/**
 * Recusa de auto-aprovação (ADR-0046, decisão 6). Ela precisa de teste próprio ANTES de
 * `isForbidden`: as duas são `403`, e tratá-la como falta de autorização trocaria "quem
 * montou não assina" por "sua conta não tem acesso a esta jornada" — a pessoa sairia
 * procurando um papel que ela já tem.
 */
export function isSelfApprovalForbidden(error: unknown): boolean {
  return error instanceof ApiError && error.code === SELF_APPROVAL_FORBIDDEN_CODE;
}

/**
 * `403` da rota. A jornada é montada pela ROTA, não pelo papel: quem chega por link
 * direto sem autorização precisa ler o motivo, e o motivo é o que o backend respondeu —
 * barrar no cliente trocaria uma frase legível por uma tela em branco.
 *
 * A auto-aprovação fica de fora explicitamente, e não por ordem de chamada em quem usa: ela
 * é `403` por segregação de função, não por falta de papel, e quem a lesse como falta de
 * autorização esconderia a jornada inteira de alguém que a enxerga.
 */
export function isForbidden(error: unknown): boolean {
  return (
    error instanceof ApiError &&
    !isSelfApprovalForbidden(error) &&
    (error.code === FORBIDDEN_CODE || error.status === 403)
  );
}

/**
 * Auditoria da planilha reprovada. É desfecho de TELA, não rodapé: nada foi publicado, e
 * dizê-lo por extenso é o que separa "falhou" de "publicou algo que ninguém conferiu".
 */
export function isWorkbookAuditFailure(error: unknown): boolean {
  return error instanceof ApiError && error.code === WORKBOOK_AUDIT_FAILED_CODE;
}

/**
 * Códigos dos achados que reprovaram a auditoria, na ordem em que o servidor os mandou.
 *
 * Só os CÓDIGOS viajam, de propósito: `expected`/`found` de um achado são preço e
 * quantidade do cliente, e a rota não os devolve numa mensagem de erro. Envelope sem a
 * lista devolve vazio, nunca um achado fabricado.
 */
export function workbookAuditFindings(error: unknown): string[] {
  if (!(error instanceof ApiError)) {
    return [];
  }
  const codes = error.details.finding_codes;
  if (!Array.isArray(codes)) {
    return [];
  }
  return codes.filter((code): code is string => typeof code === "string");
}

/**
 * Violações abertas do portão de domínio do despacho, na ordem em que o servidor as mandou.
 *
 * O portão recusa por TODAS de uma vez (`Estimate.export_errors`), e a lista inteira viaja
 * em `details.errors` do `ESTIMATE_EXPORT_BLOCKED`. Mostrar só a primeira faria a
 * orçamentista assinar de novo para tropeçar na seguinte.
 *
 * Cada violação é um código puro (`ESTIMATE_NOT_APPROVED`, `ESTIMATE_APPROVAL_REJECTED`,
 * `APPROVAL_CONTENT_MISMATCH`), sem os dois-pontos e as partes que o portão da medição
 * carrega: saldo, período e contrato não existem deste lado da fronteira do ADR-0027, e
 * inventar aqui um formato composto seria descrever um detalhe que a rota não manda.
 *
 * Recusa que não é do portão — ou envelope sem a lista — devolve vazio, nunca uma violação
 * inventada.
 */
export function exportBlockedViolations(error: unknown): string[] {
  if (!(error instanceof ApiError) || orcamentoErrorCode(error) !== EXPORT_BLOCKED_CODE) {
    return [];
  }
  const errors = error.details.errors;
  if (!Array.isArray(errors)) {
    return [];
  }
  return errors.filter((code): code is string => typeof code === "string");
}

/**
 * Código que escolhe a frase mostrada à orçamentista.
 *
 * Em `DOMAIN_VALIDATION_FAILED` quem recusou é a invariante do domínio, e ela viaja em
 * `details.code` (`ESTIMATE_*`, `ASSIGNMENT_*`, `TAKEOFF_*`, `CATALOG_*`): mostrar o
 * código da API ali esconderia o que o domínio disse. Nos demais casos o código da API é
 * o que há. Resposta sem envelope legível não vira código inventado — devolve `null`.
 */
export function orcamentoErrorCode(error: ApiError): string | null {
  if (error.code === DOMAIN_VALIDATION_CODE) {
    const domain = error.details.code;
    if (typeof domain === "string" && domain.length > 0) {
      return domain;
    }
  }
  return error.code;
}

/**
 * Frase de obra de uma recusa. O código estável escolhe o texto; sem envelope legível
 * sobra a frase que o transporte montou, nunca uma mensagem inventada.
 */
export function describeError(error: unknown): string {
  if (error instanceof ApiError) {
    const code = orcamentoErrorCode(error);
    return code === null ? error.message : errorMessage(code, error.detail);
  }
  return error instanceof Error ? error.message : String(error);
}

/**
 * Nomes dos parâmetros de obra que faltaram, na ordem em que o servidor os mandou.
 *
 * A recusa nomeia TODOS de uma vez (`details.parameters`), e é assim que ela chega aqui:
 * mostrar um por vez faria a orçamentista voltar tantas vezes quantos forem os campos.
 * Envelope sem a lista devolve vazio, nunca um faltante fabricado.
 */
export function siteSetupMissingParameters(error: unknown): string[] {
  return listaDeTexto(error, SITE_SETUP_PARAMETER_MISSING_CODE, "parameters");
}

/** Códigos que o catálogo da rodada não tem, na ordem em que o servidor os mandou. */
export function siteSetupAbsentCodes(error: unknown): string[] {
  return listaDeTexto(error, SITE_SETUP_CODE_ABSENT_CODE, "codes");
}

/** A lista de textos de um `details`, só quando a recusa é a que a declara. */
function listaDeTexto(error: unknown, code: string, chave: string): string[] {
  if (!(error instanceof ApiError) || orcamentoErrorCode(error) !== code) {
    return [];
  }
  const valores = error.details[chave];
  if (!Array.isArray(valores)) {
    return [];
  }
  return valores.filter((valor): valor is string => typeof valor === "string");
}

/**
 * Desfecho de uma recusa do acervo de canteiro (F-042), para a tela dizer o que falta.
 *
 * As duas recusas próprias são falha FECHADA e ganham a frase que NOMEIA o que faltou —
 * parâmetros ou códigos. `parametros` também volta preenchida para a tela poder marcar os
 * campos correspondentes: os nomes são os do servidor, e a tela não deduz nenhum. Qualquer
 * outra recusa cai no envelope comum das mutações, com o `409` continuando a ter banner
 * próprio.
 */
export function recusaDoAcervo(error: unknown): {
  conflito: boolean;
  parametros: string[];
  codigos: string[];
  mensagem: string;
} {
  if (isRevisionConflict(error)) {
    return {
      conflito: true,
      parametros: [],
      codigos: [],
      mensagem: MENSAGEM_ORCAMENTO_MUDOU,
    };
  }
  const parametros = siteSetupMissingParameters(error);
  if (parametros.length > 0) {
    return {
      conflito: false,
      parametros,
      codigos: [],
      mensagem: fraseParametrosFaltantes(parametros),
    };
  }
  const codigos = siteSetupAbsentCodes(error);
  if (codigos.length > 0) {
    return {
      conflito: false,
      parametros: [],
      codigos,
      mensagem: fraseCodigosAusentes(codigos),
    };
  }
  return {
    conflito: false,
    parametros: [],
    codigos: [],
    mensagem: describeError(error),
  };
}

/**
 * Desfecho de uma recusa da AUTORIA de acervo (F-042 T6), para a tela dizer o que falta.
 *
 * `bindings` volta preenchida só na recusa que os nomeia, e é ela que marca os campos exatos
 * do formulário — a tela não deduz nenhum. As demais recusas próprias (nome e versão já
 * publicados, rodada sem parcela de canteiro) não têm lista: elas são uma frase, e o pacote
 * de design deliberadamente não desenhou estado próprio para elas. O `409` da guarda otimista
 * continua tendo o banner do orçamento, como em toda mutação da jornada.
 */
export function recusaDaAutoriaDeAcervo(error: unknown): {
  conflito: boolean;
  bindings: string[];
  mensagem: string;
} {
  if (isRevisionConflict(error)) {
    return { conflito: true, bindings: [], mensagem: MENSAGEM_ORCAMENTO_MUDOU };
  }
  return {
    conflito: false,
    bindings: listaDeTexto(error, SITE_SETUP_BINDING_INVALID_CODE, "bindings"),
    mensagem: describeError(error),
  };
}

/**
 * Desfecho de uma mutação recusada, para a tela não tratar os casos como um só.
 *
 * O `409` do orçamento tem banner próprio, com o botão de recarregar e o formulário
 * preservado: ele não é falha do ato, é o aviso de que o orçamento andou. A auditoria
 * reprovada é uma TELA, e por isso sai marcada aqui em vez de virar mais um alerta.
 * Qualquer outra recusa é a frase da regra que recusou, no alerta comum.
 */
export function recusaDeMutacao(error: unknown): {
  conflito: boolean;
  auditoria: boolean;
  mensagem: string;
} {
  if (isRevisionConflict(error)) {
    return {
      conflito: true,
      auditoria: false,
      mensagem: MENSAGEM_ORCAMENTO_MUDOU,
    };
  }
  return {
    conflito: false,
    auditoria: isWorkbookAuditFailure(error),
    mensagem: describeError(error),
  };
}

/**
 * `true` quando o erro é o cancelamento de um `AbortController` — nunca falha de rede.
 * A busca incremental cancela a consulta anterior a cada tecla; sem esta distinção, cada
 * cancelamento apareceria na tela como falha da API.
 */
export function isAbortError(error: unknown): boolean {
  return error instanceof DOMException && error.name === "AbortError";
}
