import { useCallback, useEffect, useRef, useState } from "react";

import type { Survey, SurveyPoint } from "../domain/types";
import { enqueueOperation, nextSeq } from "../outbox/outbox";
import type { SurveyOperation } from "../outbox/types";
import type { SurveyRepository } from "../storage/SurveyRepository";

const DEVICE_ID_STORAGE_KEY = "croquito-field-device-id";
const SURVEY_ID = "survey-scaffold";

function getOrCreateDeviceId(): string {
  const existing = localStorage.getItem(DEVICE_ID_STORAGE_KEY);
  if (existing) {
    return existing;
  }
  const id = crypto.randomUUID();
  localStorage.setItem(DEVICE_ID_STORAGE_KEY, id);
  return id;
}

function emptySurvey(id: string): Survey {
  const now = new Date().toISOString();
  return {
    id,
    name: "Levantamento (esqueleto)",
    points: [],
    segments: [],
    measurements: [],
    photo_anchors: [],
    elements: [],
    observations: [],
    created_at: now,
    updated_at: now,
  };
}

export interface FieldShellProps {
  repository: SurveyRepository;
}

/**
 * Shell de uma tela só — declaradamente descartável (Feature Contract da F-032, gate de
 * Design Approval registrado ali). Existe para provar o fluxo ação → persistência local
 * → undo com indicador de offline, não para ser a tela final.
 */
export function FieldShell({ repository }: FieldShellProps) {
  const [survey, setSurvey] = useState<Survey | null>(null);
  const [pendingCount, setPendingCount] = useState(0);
  const [isOnline, setIsOnline] = useState(() =>
    typeof navigator === "undefined" ? true : navigator.onLine,
  );
  const deviceIdRef = useRef<string | null>(null);

  const refreshPendingCount = useCallback(
    async (surveyId: string) => {
      const pending = await repository.getPendingOperations(surveyId);
      setPendingCount(pending.length);
    },
    [repository],
  );

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      const existing = await repository.getSurvey(SURVEY_ID);
      const loaded = existing ?? emptySurvey(SURVEY_ID);
      if (!existing) {
        await repository.saveSurvey(loaded);
      }
      if (!cancelled) {
        setSurvey(loaded);
        await refreshPendingCount(loaded.id);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [repository, refreshPendingCount]);

  useEffect(() => {
    const handleOnline = () => setIsOnline(true);
    const handleOffline = () => setIsOnline(false);
    window.addEventListener("online", handleOnline);
    window.addEventListener("offline", handleOffline);
    return () => {
      window.removeEventListener("online", handleOnline);
      window.removeEventListener("offline", handleOffline);
    };
  }, []);

  const recordOperation = useCallback(
    async (surveyId: string, type: string, payload: Record<string, unknown>) => {
      deviceIdRef.current ??= getOrCreateDeviceId();
      const deviceId = deviceIdRef.current;
      // seq vem do histórico COMPLETO do device (inclusive acked): calcular sobre as
      // pendências faria a sequência regredir depois de um ack, reutilizando seq já
      // emitidos.
      const history = await repository.listOperations(surveyId);
      const operation: SurveyOperation = {
        operation_id: crypto.randomUUID(),
        device_id: deviceId,
        survey_id: surveyId,
        seq: nextSeq(history.filter((op) => op.device_id === deviceId)),
        type,
        payload,
        status: "local",
        created_at: new Date().toISOString(),
      };
      await enqueueOperation(repository, operation);
      await refreshPendingCount(surveyId);
    },
    [repository, refreshPendingCount],
  );

  const handleAddPoint = useCallback(async () => {
    if (!survey) {
      return;
    }
    const point: SurveyPoint = {
      id: crypto.randomUUID(),
      x_mm: 200 + survey.points.length * 300,
      y_mm: 200,
      created_at: new Date().toISOString(),
    };
    const next: Survey = {
      ...survey,
      points: [...survey.points, point],
      updated_at: point.created_at,
    };
    // Persiste ANTES do feedback visual (regra de `apps/field/AGENTS.md`): só depois de
    // `saveSurvey` resolver é que o estado de React muda e o ponto aparece no SVG.
    await repository.saveSurvey(next);
    await recordOperation(survey.id, "point.add", { point });
    setSurvey(next);
  }, [survey, repository, recordOperation]);

  const handleUndo = useCallback(async () => {
    if (!survey || survey.points.length === 0) {
      return;
    }
    const removedPoint = survey.points[survey.points.length - 1];
    const next: Survey = {
      ...survey,
      points: survey.points.slice(0, -1),
      updated_at: new Date().toISOString(),
    };
    await repository.saveSurvey(next);
    await recordOperation(survey.id, "point.remove", { point_id: removedPoint.id });
    setSurvey(next);
  }, [survey, repository, recordOperation]);

  return (
    <div className="flex h-screen w-screen flex-col bg-slate-950 text-slate-50">
      <header className="flex items-center justify-between gap-4 border-b border-slate-800 px-4 py-3">
        <span
          className={`text-sm font-medium ${isOnline ? "text-emerald-400" : "text-amber-400"}`}
        >
          {isOnline ? "Online" : "Offline"}
        </span>
        <span className="text-sm text-slate-300">{pendingCount} operação(ões) pendente(s)</span>
      </header>
      <main className="flex-1 overflow-hidden">
        <svg
          role="img"
          aria-label="Área de desenho do levantamento"
          viewBox="0 0 2000 1200"
          className="h-full w-full bg-slate-900"
        >
          {survey?.points.map((point) => (
            <circle key={point.id} cx={point.x_mm / 10} cy={point.y_mm / 10} r={8} fill="#38bdf8" />
          ))}
        </svg>
      </main>
      <footer className="flex gap-3 border-t border-slate-800 p-4">
        <button
          type="button"
          onClick={() => void handleAddPoint()}
          disabled={!survey}
          className="min-h-[48px] flex-1 rounded-lg bg-sky-600 px-4 text-base font-semibold text-white disabled:opacity-50"
        >
          Adicionar ponto
        </button>
        <button
          type="button"
          onClick={() => void handleUndo()}
          disabled={!survey || survey.points.length === 0}
          className="min-h-[48px] flex-1 rounded-lg bg-slate-700 px-4 text-base font-semibold text-white disabled:opacity-50"
        >
          Desfazer
        </button>
      </footer>
    </div>
  );
}
