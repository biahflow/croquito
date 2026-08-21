/**
 * SHA-256 de bytes já lidos, via `crypto.subtle.digest` (Web Crypto — disponível no
 * navegador e, para teste, no Node do vitest). Função pura e testável com bytes
 * conhecidos (Task Contract T6, Acceptance Criteria 1) — não lê arquivo, não conhece
 * `File`/`Blob`; quem chama já trouxe os bytes (ver `photos/media.ts`).
 *
 * Nunca loga os bytes nem o resultado: convenção de segurança do repositório (nunca
 * logar conteúdo de foto) — este módulo simplesmente não tem nenhuma chamada de log.
 */
export async function sha256Hex(bytes: ArrayBuffer | Uint8Array): Promise<string> {
  const view = bytes instanceof Uint8Array ? bytes : new Uint8Array(bytes);
  // Cópia para um Uint8Array<ArrayBuffer> "fresco": `view` pode carregar um
  // `ArrayBufferLike` (ex.: `SharedArrayBuffer`) que `crypto.subtle.digest` (tipado como
  // `BufferSource` = `ArrayBufferView<ArrayBuffer> | ArrayBuffer`) não aceita — a cópia
  // evita o erro de tipo sem mudar o resultado (mesmos bytes).
  const copy = new Uint8Array(view.byteLength);
  copy.set(view);
  const digest = await crypto.subtle.digest("SHA-256", copy.buffer);
  return [...new Uint8Array(digest)].map((byte) => byte.toString(16).padStart(2, "0")).join("");
}
