/**
 * View-model do painel de sincronização (prancha 6a/6b) — funções puras entre o estado do
 * motor (`src/sync/state.ts`) e o JSX de `SyncScreen.tsx`.
 *
 * Não importa React, não importa Dexie e não fala com a rede: é testável em node puro,
 * como `viewModel.ts`. Nada aqui decide sincronização; só escreve em português o que o
 * motor já apurou — e escreve SEMPRE, porque cor não pode ser o único portador de estado
 * (regra 5 do Design System, citada em `styles.css`).
 */

import type { SyncCategory, SyncCategoryState, SyncConflictState, SyncState } from "../sync";
import { API_BASE_URL_ENV } from "../sync";
import type { Notice } from "./notice";

const CATEGORY_LABEL: Record<SyncCategory, string> = {
  metadata: "Geometria e medidas",
  anchored_photo: "Fotos",
  access_photo: "Foto do acesso",
  audio: "Áudios",
};

/** Concordância do particípio de cada categoria ("enviadas" × "enviada"). */
const CATEGORY_SENT_WORD: Record<SyncCategory, { singular: string; plural: string }> = {
  metadata: { singular: "enviada", plural: "enviadas" },
  anchored_photo: { singular: "enviada", plural: "enviadas" },
  access_photo: { singular: "enviada", plural: "enviadas" },
  audio: { singular: "enviado", plural: "enviados" },
};

/** Hora local do aparelho ("17:02") — o técnico compara com o relógio do pulso dele, não
 * com UTC. Sem segundos: a prancha 6a mostra hora e minuto. */
export function formatClock(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) {
    return "";
  }
  const hours = String(date.getHours()).padStart(2, "0");
  const minutes = String(date.getMinutes()).padStart(2, "0");
  return `${hours}:${minutes}`;
}

function plural(count: number, singular: string, pluralForm: string): string {
  return count === 1 ? singular : pluralForm;
}

export type SyncRowTone = "ok" | "warn" | "error" | "todo";

export interface SyncCategoryView {
  category: SyncCategory;
  /** "Fotos — 8 de 12 enviadas" (prancha 6a). */
  title: string;
  /** Segunda linha escrita: o que está acontecendo ou o motivo da falha. */
  detail: string;
  tone: SyncRowTone;
}

function categoryTitle(entry: SyncCategoryState): string {
  const label = CATEGORY_LABEL[entry.category];
  const word = CATEGORY_SENT_WORD[entry.category];
  if (entry.sent >= entry.total && entry.failed === 0) {
    return `${label} — ${plural(entry.total, word.singular, word.plural)}`;
  }
  return `${label} — ${entry.sent} de ${entry.total} ${word.plural}`;
}

function categoryDetail(entry: SyncCategoryState, state: SyncState): string {
  if (entry.failure_detail !== null) {
    return entry.failure_detail;
  }
  if (entry.category === "metadata") {
    if (entry.sent === entry.total && entry.total > 0 && state.last_synced_at !== null) {
      return `${entry.sent} ${plural(entry.sent, "operação confirmada", "operações confirmadas")} pelo servidor às ${formatClock(state.last_synced_at)}`;
    }
    const waiting = Math.max(entry.total - entry.sent, 0);
    return `${waiting} ${plural(waiting, "ação aguarda", "ações aguardam")} envio; os metadados sobem antes das fotos.`;
  }
  if (entry.sent === entry.total && entry.failed === 0) {
    return "Confirmadas pelo servidor.";
  }
  if (state.phase === "idle" || state.phase === "offline" || state.phase === "local_mode") {
    return "Sobem depois dos metadados, quando o envio começar.";
  }
  return "Envio continua sozinho; um arquivo com falha não trava os outros.";
}

function categoryTone(entry: SyncCategoryState): SyncRowTone {
  if (entry.failed > 0) {
    return "warn";
  }
  if (entry.total > 0 && entry.sent === entry.total) {
    return "ok";
  }
  return "todo";
}

/**
 * As linhas da prancha 6a, na ordem declarada de envio. Categoria sem nada a enviar não
 * aparece — é o caso dos áudios num levantamento sem nenhuma nota de voz (T12).
 */
export function buildCategoryViews(state: SyncState): SyncCategoryView[] {
  return state.categories
    .filter((entry) => entry.total > 0)
    .map((entry) => ({
      category: entry.category,
      title: categoryTitle(entry),
      detail: categoryDetail(entry, state),
      tone: categoryTone(entry),
    }));
}

/** Título da tela: "Sincronização", ou o conflito nomeando o levantamento (prancha 6b). */
export function syncScreenTitle(state: SyncState, surveyName: string): string {
  return state.phase === "conflict" ? `Conflito em ${surveyName}` : "Sincronização";
}

/**
 * O aviso escrito no topo do painel. Estado que não é erro (modo local, offline,
 * reautenticação) nunca é apresentado como falha — é a circunstância, dita por extenso.
 */
export function syncBanner(state: SyncState): Notice | null {
  switch (state.phase) {
    case "local_mode":
      return {
        tone: "info",
        text: `Modo local: este aparelho não tem servidor configurado (${API_BASE_URL_ENV}). A coleta funciona normalmente e nada é apagado.`,
      };
    case "offline":
      return {
        tone: "info",
        text: "Aguardando conexão. O levantamento continua guardado neste aparelho e sobe assim que houver rede.",
      };
    case "reauth_required":
      return {
        tone: "warn",
        text: "Reautenticação necessária para enviar. A coleta continua normal — toque em “Entrar novamente” na barra e envie depois.",
      };
    case "conflict":
      return {
        tone: "error",
        text: `${state.conflict?.detail ?? "O servidor recusou o envio por divergência."} Escolha qual vale — as duas ficam no histórico.`,
      };
    case "error":
      return { tone: "error", text: state.error?.message ?? "A sincronização não foi concluída." };
    case "sending_metadata":
      return { tone: "info", text: "Enviando geometria e medidas…" };
    case "sending_media":
      return { tone: "info", text: "Enviando fotos e áudios…" };
    case "completing":
      return { tone: "info", text: "Fechando o levantamento no servidor…" };
    case "done":
      return state.completed
        ? {
            tone: "ok",
            text: "Levantamento concluído e enviado. O escritório já pode abri-lo.",
          }
        : { tone: "ok", text: "Tudo o que havia para enviar foi confirmado pelo servidor." };
    case "idle":
      return null;
  }
}

/** Rodapé fixo da 6a — a regra que o técnico precisa ler, não deduzir. */
export const SYNC_RETENTION_NOTE =
  "Nada é apagado deste aparelho antes da confirmação do servidor.";

export interface ConflictSideView {
  /** "No seu aparelho · você" / "No servidor · escritório". */
  origin: string;
  /** Instrumento e hora, quando declarados. */
  meta: string;
  /** A grandeza que a pessoa compara. */
  value: string;
}

export interface ConflictView {
  local: ConflictSideView;
  server: ConflictSideView;
  keep_label: string;
  accept_label: string;
}

/**
 * Os dois lados da prancha 6b. O autor do lado do servidor é "escritório", e não um nome:
 * o contrato `/v1/surveys` não devolve autor da alteração, e inventar um nome na tela
 * seria pior do que declarar a origem que a API garante.
 */
export function buildConflictView(conflict: SyncConflictState): ConflictView {
  const localParts = [
    conflict.local_instrument,
    conflict.local_updated_at === null ? null : formatClock(conflict.local_updated_at),
  ].filter((part): part is string => part !== null && part !== "");
  const serverParts = [
    conflict.server_instrument,
    conflict.server_updated_at === null ? null : formatClock(conflict.server_updated_at),
  ].filter((part): part is string => part !== null && part !== "");
  const pending = conflict.local_pending_operations;
  const versionLabel =
    conflict.server_version === null ? "versão mais recente" : `versão ${conflict.server_version}`;
  return {
    local: {
      origin: "No seu aparelho · você",
      meta: localParts.join(" · "),
      value: `${pending} ${plural(pending, "ação não enviada", "ações não enviadas")}`,
    },
    server: {
      origin: "No servidor · escritório",
      meta: serverParts.join(" · "),
      value: versionLabel.charAt(0).toUpperCase() + versionLabel.slice(1),
    },
    keep_label: `Manter a minha (${pending} ${plural(pending, "ação", "ações")})`,
    accept_label: `Aceitar a do escritório (${versionLabel})`,
  };
}

/** Rótulo do botão de envio, sempre dizendo o que vai acontecer. */
export function syncActionLabel(state: SyncState): string {
  if (state.phase === "sending_metadata" || state.phase === "sending_media") {
    return "Enviando…";
  }
  if (state.phase === "completing") {
    return "Fechando no servidor…";
  }
  if (state.pending_operations > 0) {
    return `Enviar ${state.pending_operations} ${plural(state.pending_operations, "pendência", "pendências")}`;
  }
  return "Enviar agora";
}
