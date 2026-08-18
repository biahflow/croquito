/** Escolha pura de origem da imagem da prancha, conforme o modo de sessão. */

import { plateImageUrl } from "./api";

/**
 * `src` da prancha antes de qualquer busca: a URL direta no caminho local, `null` no
 * hospedado.
 *
 * Sem sessão OIDC (o servidor local do ADR-0020, que não autentica) a imagem continua
 * vindo pela URL direta — nenhum fetch a mais, nenhum object URL a revogar, exatamente o
 * que a ferramenta local sempre fez. Com sessão, o `null` é o estado honesto: ainda não há
 * imagem, porque ela só existe depois da busca autenticada.
 */
export function plateImageSource(oidcAtivo: boolean): string | null {
  return oidcAtivo ? null : plateImageUrl;
}
