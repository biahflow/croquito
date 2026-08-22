/**
 * Fronteira pública da sincronização. `src/ui` e `src/outbox` importam daqui — o
 * transporte (`apiClient.ts`) fica atrás desta fachada, e é o único lugar do workspace
 * autorizado a falar com a rede (`apps/field/AGENTS.md`).
 */

export { createSyncApi, type FetchLike, type SyncApi, type SyncFailure } from "./apiClient";
export { API_BASE_URL, API_BASE_URL_ENV, DEV_TEST_TOKEN, normalizeApiBaseUrl } from "./config";
export type { MediaIndex, MediaMeta, SurveyPacketShape } from "./contract";
export { isSurveyPacketShape, MissingMediaError, toSurveyPacket } from "./contract";
export {
  CONFLICT_JUSTIFICATION,
  CONFLICT_RESOLUTION_OPERATION,
  createSyncEngine,
  type ConflictDecision,
  type SyncEngine,
  type SyncEngineDeps,
} from "./engine";
export {
  SYNC_CATEGORIES,
  initialSyncState,
  type SyncCategory,
  type SyncCategoryState,
  type SyncConflictState,
  type SyncPhase,
  type SyncState,
} from "./state";
