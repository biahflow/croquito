/**
 * Ponte entre a gravação (`recorder.ts`) e o `MediaRecord` do repositório — espelho exato
 * de `photos/media.ts`: hash do conteúdo ORIGINAL antes de qualquer outra coisa, e nenhum
 * conhecimento de React, Dexie ou âncora.
 *
 * O `MediaRecord` é agnóstico de tipo (blob + mime), então áudio não precisa de tabela nem
 * de migração Dexie: o mesmo `buildMediaRecord` de foto monta o registro.
 */

import { sha256Hex } from "../photos/hash";
import type { CapturedMedia } from "../photos/media";
import type { RecordedAudio } from "./recorder";

/**
 * Lê os bytes gravados, calcula o SHA-256 e devolve os campos prontos para
 * `buildMediaRecord`. O mime é o contêiner REAL escolhido pelo aparelho na hora de gravar
 * (`audio/webm` ou `audio/mp4`) — nunca um valor fixo, e nunca uma conversão.
 */
export async function captureAudio(recorded: RecordedAudio): Promise<CapturedMedia> {
  const buffer = await recorded.blob.arrayBuffer();
  const sha256 = await sha256Hex(buffer);
  return {
    sha256,
    mime_type: recorded.mime_type,
    byte_size: buffer.byteLength,
    blob: recorded.blob,
  };
}
