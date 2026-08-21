/**
 * Estado observável da sincronização — o que a prancha 6 desenha.
 *
 * Puro e serializável: o motor (`engine.ts`) produz, o painel (`ui/syncViewModel.ts`)
 * escreve em português. Nenhum campo aqui carrega blob, URL assinada, token ou conteúdo de
 * mídia; o painel só precisa de contagens, estados e identificadores opacos.
 */

import type { SurveyPacketShape } from "./contract";

/**
 * Categorias de envio da prancha 6a. A ordem declarada é a ordem em que o motor envia, e é
 * a ordem em que o painel lista: metadados sempre primeiro (é a regra que o servidor
 * cobra — mídia sem âncora sincronizada é recusada), mídia depois.
 *
 * `audio` existe hoje sempre com total 0: o domínio ainda não grava áudio (voz é T12) e o
 * painel esconde categoria vazia. Está declarada porque o contrato do pacote (T7) já
 * carrega `audio_media_ref`, e a categoria da 6a é a mesma.
 */
export const SYNC_CATEGORIES = ["metadata", "anchored_photo", "access_photo", "audio"] as const;

export type SyncCategory = (typeof SYNC_CATEGORIES)[number];

export type SyncCategoryStatus = "waiting" | "running" | "sent" | "partial";

export interface SyncCategoryState {
  category: SyncCategory;
  /** Itens desta categoria que o levantamento referencia. */
  total: number;
  /** Confirmados pelo servidor (ack de operação, ou `confirm` de mídia). */
  sent: number;
  /** Falharam nesta passada — não travam as outras (prancha 6a). */
  failed: number;
  status: SyncCategoryStatus;
  /** Motivo escrito da última falha desta categoria, quando houve. */
  failure_detail: string | null;
}

/**
 * Fase da passada. `local_mode` e `offline` não são erro: são o app fazendo o que deve
 * quando não há transporte configurado ou não há rede.
 */
export type SyncPhase =
  | "local_mode"
  | "idle"
  | "offline"
  | "reauth_required"
  | "sending_metadata"
  | "sending_media"
  | "completing"
  | "done"
  | "conflict"
  | "error";

/** O conflito da prancha 6b: os dois lados e o que decidir. */
export interface SyncConflictState {
  /** Mensagem do servidor (português, código estável do contrato). */
  detail: string;
  server_version: number | null;
  /** Último `seq` que o servidor tem deste aparelho — a âncora da reancoragem local. */
  server_last_seq: number;
  server_snapshot: SurveyPacketShape | null;
  /** Operações locais ainda não reconhecidas no instante do conflito. */
  local_pending_operations: number;
  /** Instrumento declarado na chegada, de cada lado (prancha 6b: origem/autor/instrumento). */
  local_instrument: string | null;
  server_instrument: string | null;
  /** Instante da última ação local e da última atualização do servidor. */
  local_updated_at: string | null;
  server_updated_at: string | null;
}

export interface SyncState {
  survey_id: string | null;
  phase: SyncPhase;
  /** Operações no outbox que ainda não foram reconhecidas (o "N pendentes" da barra). */
  pending_operations: number;
  categories: SyncCategoryState[];
  /** Versão do levantamento no servidor, quando conhecida. */
  server_version: number | null;
  /** Instante da última resposta aceita pelo servidor nesta sessão. */
  last_synced_at: string | null;
  /** `true` depois de `complete` aceito. */
  completed: boolean;
  conflict: SyncConflictState | null;
  error: { code: string; message: string } | null;
}

export function emptyCategories(): SyncCategoryState[] {
  return SYNC_CATEGORIES.map((category) => ({
    category,
    total: 0,
    sent: 0,
    failed: 0,
    status: "waiting" as SyncCategoryStatus,
    failure_detail: null,
  }));
}

export function initialSyncState(phase: SyncPhase = "idle"): SyncState {
  return {
    survey_id: null,
    phase,
    pending_operations: 0,
    categories: emptyCategories(),
    server_version: null,
    last_synced_at: null,
    completed: false,
    conflict: null,
    error: null,
  };
}
