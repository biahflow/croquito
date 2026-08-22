/**
 * O painel da prancha 6 derivado do estado do motor — sem DOM, como `viewModel.test.ts`.
 *
 * O que estes testes protegem: todo estado aparece ESCRITO (cor nunca é o único portador
 * de significado); categoria sem nada a enviar não vira linha vazia na tela; offline, modo
 * local e reautenticação não são apresentados como falha; e os dois lados do conflito
 * dizem origem, instrumento e hora antes de pedir a decisão.
 */

import { describe, expect, it } from "vitest";

import { initialSyncState, type SyncConflictState, type SyncState } from "../sync";
import {
  SYNC_RETENTION_NOTE,
  buildCategoryViews,
  buildConflictView,
  formatClock,
  syncActionLabel,
  syncBanner,
  syncScreenTitle,
} from "./syncViewModel";

/** Hora LOCAL do aparelho: montada a partir de uma data local para o teste não depender do
 * fuso da máquina que roda a suíte. */
const LOCAL_17_02 = new Date(2026, 7, 21, 17, 2, 0).toISOString();

function stateWith(overrides: Partial<SyncState>): SyncState {
  return { ...initialSyncState(), survey_id: "survey-1", ...overrides };
}

function categories(state: SyncState, changes: Partial<SyncState["categories"][number]>[]): SyncState {
  return {
    ...state,
    categories: state.categories.map((entry, index) => ({ ...entry, ...(changes[index] ?? {}) })),
  };
}

describe("formatClock", () => {
  it("escreve hora e minuto locais", () => {
    expect(formatClock(LOCAL_17_02)).toBe("17:02");
  });

  it("data inválida não quebra a tela", () => {
    expect(formatClock("nao-e-data")).toBe("");
  });
});

describe("buildCategoryViews", () => {
  it("categoria sem nada a enviar não vira linha (áudios até a T12)", () => {
    const state = categories(stateWith({ phase: "done" }), [
      { total: 37, sent: 37 },
      { total: 12, sent: 8 },
    ]);

    const views = buildCategoryViews(state);

    expect(views.map((view) => view.category)).toEqual(["metadata", "anchored_photo"]);
  });

  it("escreve o progresso por categoria como a prancha 6a", () => {
    const state = categories(
      stateWith({ phase: "sending_media", last_synced_at: LOCAL_17_02 }),
      [
        { total: 37, sent: 37, status: "sent" },
        { total: 12, sent: 8, status: "running" },
      ],
    );

    const [metadata, photos] = buildCategoryViews(state);

    expect(metadata?.title).toBe("Geometria e medidas — enviadas");
    expect(metadata?.detail).toBe("37 operações confirmadas pelo servidor às 17:02");
    expect(metadata?.tone).toBe("ok");
    expect(photos?.title).toBe("Fotos — 8 de 12 enviadas");
    expect(photos?.detail).toContain("um arquivo com falha não trava os outros");
    expect(photos?.tone).toBe("todo");
  });

  it("falha de um arquivo aparece escrita na própria linha", () => {
    const state = categories(stateWith({ phase: "error" }), [
      { total: 1, sent: 1 },
      { total: 3, sent: 2, failed: 1, status: "partial", failure_detail: "Fotos: o arquivo chegou diferente do que saiu do aparelho." },
    ]);

    const [, photos] = buildCategoryViews(state);

    expect(photos?.tone).toBe("warn");
    expect(photos?.detail).toContain("chegou diferente");
    expect(photos?.title).toBe("Fotos — 2 de 3 enviadas");
  });
});

describe("syncBanner", () => {
  it("modo local e offline não são apresentados como falha", () => {
    expect(syncBanner(stateWith({ phase: "local_mode" }))?.tone).toBe("info");
    expect(syncBanner(stateWith({ phase: "local_mode" }))?.text).toContain(
      "VITE_CROQUITO_API_BASE_URL",
    );
    const offline = syncBanner(stateWith({ phase: "offline" }));
    expect(offline?.tone).toBe("info");
    expect(offline?.text).toContain("Aguardando conexão");
  });

  it("sessão vencida diz que a coleta continua (prancha 6c)", () => {
    const banner = syncBanner(stateWith({ phase: "reauth_required" }));

    expect(banner?.tone).toBe("warn");
    expect(banner?.text).toContain("A coleta continua normal");
  });

  it("erro mostra a mensagem do motor, não um texto genérico", () => {
    const banner = syncBanner(
      stateWith({
        phase: "error",
        error: { code: "SYNC_ENVIO_INCOMPLETO", message: "Parte do levantamento não foi aceita." },
      }),
    );

    expect(banner).toEqual({ tone: "error", text: "Parte do levantamento não foi aceita." });
  });

  it("conclusão enviada é dita por extenso", () => {
    const banner = syncBanner(stateWith({ phase: "done", completed: true }));

    expect(banner?.tone).toBe("ok");
    expect(banner?.text).toContain("Levantamento concluído e enviado");
  });
});

describe("prancha 6b", () => {
  const conflict: SyncConflictState = {
    detail: "A sequência do aparelho não continua de onde o servidor parou.",
    server_version: 7,
    server_last_seq: 12,
    server_snapshot: null,
    local_pending_operations: 3,
    local_instrument: "Trena laser",
    server_instrument: "ajuste manual",
    local_updated_at: LOCAL_17_02,
    server_updated_at: LOCAL_17_02,
  };

  it("nomeia o levantamento no título", () => {
    expect(syncScreenTitle(stateWith({ phase: "conflict", conflict }), "Guaxindiba")).toBe(
      "Conflito em Guaxindiba",
    );
  });

  it("cada lado declara origem, instrumento e hora antes da decisão", () => {
    const view = buildConflictView(conflict);

    expect(view.local.origin).toBe("No seu aparelho · você");
    expect(view.local.meta).toBe("Trena laser · 17:02");
    expect(view.local.value).toBe("3 ações não enviadas");
    expect(view.server.origin).toBe("No servidor · escritório");
    expect(view.server.meta).toBe("ajuste manual · 17:02");
    expect(view.server.value).toBe("Versão 7");
    expect(view.keep_label).toBe("Manter a minha (3 ações)");
    expect(view.accept_label).toBe("Aceitar a do escritório (versão 7)");
  });

  it("o aviso do conflito diz que as duas versões ficam", () => {
    const banner = syncBanner(stateWith({ phase: "conflict", conflict }));

    expect(banner?.tone).toBe("error");
    expect(banner?.text).toContain("as duas ficam no histórico");
  });
});

describe("syncActionLabel", () => {
  it("diz quantas pendências vão sair", () => {
    expect(syncActionLabel(stateWith({ pending_operations: 3 }))).toBe("Enviar 3 pendências");
    expect(syncActionLabel(stateWith({ pending_operations: 1 }))).toBe("Enviar 1 pendência");
    expect(syncActionLabel(stateWith({ pending_operations: 0 }))).toBe("Enviar agora");
  });

  it("durante o envio o rótulo acompanha a fase", () => {
    expect(syncActionLabel(stateWith({ phase: "sending_media", pending_operations: 2 }))).toBe(
      "Enviando…",
    );
    expect(syncActionLabel(stateWith({ phase: "completing" }))).toBe("Fechando no servidor…");
  });
});

describe("nota de retenção", () => {
  it("é a regra da fatia, escrita na tela", () => {
    expect(SYNC_RETENTION_NOTE).toContain("Nada é apagado deste aparelho");
  });
});
