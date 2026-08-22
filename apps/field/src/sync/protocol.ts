/**
 * Formas do protocolo `/v1/surveys` como o app as consome (T8 → T9).
 *
 * Tudo o que volta da rede chega como `unknown` (JSON desserializado) e passa por um
 * guarda de forma antes de virar estado do app — mesma disciplina de `contract.ts`, e a
 * razão é a mesma: um corpo diferente do combinado (proxy, página de erro de um portal
 * cativo, versão nova da API) precisa virar falha declarada, não `undefined` circulando
 * pelo motor.
 *
 * Nada aqui republica o vocabulário do servidor: os códigos de erro são os do contrato
 * (`SURVEY_CONFLICT`, `SURVEY_MEDIA_NOT_REFERENCED`, `SURVEY_MEDIA_DIGEST_MISMATCH`,
 * `SURVEY_MEDIA_PENDING`, `SURVEY_NOT_CONCLUDED`, `SURVEY_PACKET_INVALID`) e viajam como
 * texto opaco para o painel escrever.
 */

import type { SurveyPacketShape } from "./contract";
import { isSurveyPacketShape } from "./contract";

/** Códigos de erro do servidor que esta fatia trata por nome. */
export const SURVEY_CONFLICT = "SURVEY_CONFLICT";
export const SURVEY_MEDIA_NOT_REFERENCED = "SURVEY_MEDIA_NOT_REFERENCED";
export const SURVEY_MEDIA_DIGEST_MISMATCH = "SURVEY_MEDIA_DIGEST_MISMATCH";
export const SURVEY_MEDIA_PENDING = "SURVEY_MEDIA_PENDING";

/** Corpo de `POST /v1/surveys/{id}/operations`. */
export interface SubmitOperationsBody {
  device_id: string;
  survey: SurveyPacketShape;
  operations: SurveyPacketShape["operations"];
}

/** Resposta de ack do lote. */
export interface OperationsAck {
  survey_id: string;
  acked_operation_ids: string[];
  version: number;
  last_seq_by_device: Record<string, number>;
}

/** Resposta do presign de mídia. Sem log, sem persistência: a URL assinada morre no PUT. */
export interface PresignedMedia {
  sha256: string;
  object_key: string;
  url: string;
  headers: Record<string, string>;
}

/** Estado do levantamento como o servidor o conhece (`GET`, `confirm`, `complete`). */
export interface ServerSurveyState {
  version: number;
  status: string;
  last_seq_by_device: Record<string, number>;
  media: { sha256: string; mime_type: string; status: string }[];
  survey: SurveyPacketShape | null;
}

/** `details` do `409 SURVEY_CONFLICT` — o que a prancha 6b precisa para deixar a decisão
 * com a pessoa. `server_snapshot` é `null` quando o conflito é de corrida de escrita, em
 * que o servidor deliberadamente não anexa um estado que já vai mudar. */
export interface ServerConflict {
  server_version: number | null;
  last_seq_by_device: Record<string, number>;
  server_snapshot: SurveyPacketShape | null;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function toSeqMap(value: unknown): Record<string, number> {
  if (!isRecord(value)) {
    return {};
  }
  const entries: [string, number][] = [];
  for (const [device, seq] of Object.entries(value)) {
    if (typeof seq === "number" && Number.isFinite(seq)) {
      entries.push([device, seq]);
    }
  }
  return Object.fromEntries(entries);
}

export function parseOperationsAck(value: unknown): OperationsAck | null {
  if (!isRecord(value) || typeof value.survey_id !== "string" || typeof value.version !== "number") {
    return null;
  }
  const acked = value.acked_operation_ids;
  if (!Array.isArray(acked) || !acked.every((item) => typeof item === "string")) {
    return null;
  }
  return {
    survey_id: value.survey_id,
    acked_operation_ids: acked,
    version: value.version,
    last_seq_by_device: toSeqMap(value.last_seq_by_device),
  };
}

export function parsePresignedMedia(value: unknown): PresignedMedia | null {
  if (
    !isRecord(value) ||
    typeof value.sha256 !== "string" ||
    typeof value.object_key !== "string" ||
    typeof value.url !== "string"
  ) {
    return null;
  }
  const headers: Record<string, string> = {};
  if (isRecord(value.headers)) {
    for (const [name, headerValue] of Object.entries(value.headers)) {
      if (typeof headerValue === "string") {
        headers[name] = headerValue;
      }
    }
  }
  return {
    sha256: value.sha256,
    object_key: value.object_key,
    url: value.url,
    headers,
  };
}

export function parseServerSurveyState(value: unknown): ServerSurveyState | null {
  if (!isRecord(value) || typeof value.version !== "number" || typeof value.status !== "string") {
    return null;
  }
  const media: ServerSurveyState["media"] = [];
  if (Array.isArray(value.media)) {
    for (const entry of value.media) {
      if (
        isRecord(entry) &&
        typeof entry.sha256 === "string" &&
        typeof entry.mime_type === "string" &&
        typeof entry.status === "string"
      ) {
        media.push({ sha256: entry.sha256, mime_type: entry.mime_type, status: entry.status });
      }
    }
  }
  return {
    version: value.version,
    status: value.status,
    last_seq_by_device: toSeqMap(value.last_seq_by_device),
    media,
    survey: isSurveyPacketShape(value.survey) ? value.survey : null,
  };
}

/**
 * Lê o `details` do conflito. O `server_snapshot` só é aceito quando passa pelo guarda de
 * forma do contrato (T7): um snapshot malformado vira `null` e o painel mostra o conflito
 * sem a comparação, em vez de o motor tratar lixo como estado do servidor — e, sobretudo,
 * em vez de reenviar um pacote inválido como "versão do escritório".
 */
export function parseServerConflict(details: unknown): ServerConflict {
  if (!isRecord(details)) {
    return { server_version: null, last_seq_by_device: {}, server_snapshot: null };
  }
  return {
    server_version: typeof details.server_version === "number" ? details.server_version : null,
    last_seq_by_device: toSeqMap(details.last_seq_by_device),
    server_snapshot: isSurveyPacketShape(details.server_snapshot) ? details.server_snapshot : null,
  };
}
