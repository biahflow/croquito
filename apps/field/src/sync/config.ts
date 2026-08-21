/**
 * Configuração de transporte da sincronização (T9).
 *
 * Sem `VITE_CROQUITO_API_BASE_URL` o app segue funcionando exatamente como antes desta
 * tarefa — coleta local, outbox local, painel em "modo local". A ausência da env não é
 * erro: é o modo em que o app roda hoje no aparelho do técnico enquanto o ambiente
 * hospedado não está configurado, e nenhum caminho de coleta pode quebrar por causa dela.
 */

/** Nome da env, exportado para o painel poder dizer, escrito, o que falta configurar. */
export const API_BASE_URL_ENV = "VITE_CROQUITO_API_BASE_URL";

/**
 * Normaliza o valor da env: string vazia, espaço em branco e valor não-string viram
 * `null` (modo local). A barra final é removida para que as rotas possam ser concatenadas
 * como `${base}/v1/surveys/...` sem barra dupla.
 */
export function normalizeApiBaseUrl(value: unknown): string | null {
  if (typeof value !== "string") {
    return null;
  }
  const trimmed = value.trim().replace(/\/+$/, "");
  return trimmed === "" ? null : trimmed;
}

/** Base da API neste build — `null` quando a env não foi declarada (modo local). */
export const API_BASE_URL: string | null = normalizeApiBaseUrl(
  import.meta.env.VITE_CROQUITO_API_BASE_URL,
);
