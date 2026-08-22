/**
 * Helpers puros/testáveis entre a captura de arquivo (UI) e o `MediaRecord` gravado no
 * repositório (Task Contract T6, Scope). Nenhuma função aqui conhece React, Dexie ou
 * âncora — só bytes, hash e o formato do registro.
 */

import type { MediaRecord } from "../storage/SurveyRepository";
import { sha256Hex } from "./hash";

export interface CapturedMedia {
  sha256: string;
  mime_type: string;
  byte_size: number;
  blob: Blob;
}

/**
 * Lê os bytes do arquivo escolhido pelo `<input type="file">` e calcula o SHA-256 do
 * conteúdo ORIGINAL — antes de qualquer processamento (não há compressão nesta fatia,
 * Task Contract T6, Out of Scope). Devolve os campos prontos para `buildMediaRecord`;
 * `id`/`created_at` ficam de fora porque quem chama decide o UUID e o instante (mesma
 * convenção dos comandos de domínio, que recebem `nowIso` de fora).
 */
export async function captureFile(file: File): Promise<CapturedMedia> {
  const buffer = await file.arrayBuffer();
  const sha256 = await sha256Hex(buffer);
  return {
    sha256,
    mime_type: file.type || "application/octet-stream",
    byte_size: buffer.byteLength,
    blob: file,
  };
}

export interface BuildMediaRecordArgs {
  id: string;
  sha256: string;
  mime_type: string;
  byte_size: number;
  blob: Blob;
  created_at: string;
}

/** Monta o `MediaRecord` a gravar via `SurveyRepository.saveMedia` — função pura, sem
 * I/O (Task Contract T6, Scope: "helpers puros testáveis... montagem do registro"). */
export function buildMediaRecord(args: BuildMediaRecordArgs): MediaRecord {
  return {
    id: args.id,
    sha256: args.sha256,
    mime_type: args.mime_type,
    byte_size: args.byte_size,
    blob: args.blob,
    created_at: args.created_at,
  };
}
