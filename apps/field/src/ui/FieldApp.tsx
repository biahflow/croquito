import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import {
  addMeasurement,
  addObservation,
  addPoint,
  addSegment,
  closePerimeter,
  justifyMeasurement,
  recordArrival,
  undoLast,
  type CommandHistoryEntry,
} from "../domain/commands";
import type { CommandResult, GpsFix, Segment, Survey, SurveyPointId } from "../domain/types";
import { validateSurvey } from "../domain/validation";
import { applyCommand } from "../outbox/applyCommand";
import { createSerialQueue } from "../outbox/serialQueue";
import { clearActiveOrderId, getActiveOrderId, setActiveOrderId } from "../orders/activeOrder";
import { ORDERS } from "../orders/fixture";
import {
  deriveOrderState,
  requiredItemsForOrder,
  surveyIdForOrder,
  type OrderState,
} from "../orders/state";
import type { Order, OrderId } from "../orders/types";
import type { SurveyRepository } from "../storage/SurveyRepository";
import { AddMenu } from "./AddMenu";
import { ArrivalScreen } from "./ArrivalScreen";
import { AppBar } from "./AppBar";
import { CollectScreen } from "./CollectScreen";
import { getOrCreateDeviceId } from "./device";
import { DivergenceScreen } from "./DivergenceScreen";
import { MeasureScreen } from "./MeasureScreen";
import type { Notice } from "./notice";
import { OrdersScreen } from "./OrdersScreen";
import { TextEntryScreen } from "./TextEntryScreen";
import {
  DEFAULT_TOLERANCE_MM,
  buildDivergenceView,
  findCriticalDivergence,
  pointLabels,
  segmentLabels,
  selectPointForSegment,
  type MmPoint,
} from "./viewModel";

const APP_BRAND = "croquito campo";

/**
 * Instrumento ainda não declarado. Sobrevive como fallback defensivo (Especificação §6 do
 * Task Contract T4): na prática, T4 garante que toda coleta passa antes pela chegada
 * (`recordArrival`), então `survey.context` deveria sempre existir na tela de medir.
 */
const UNDECLARED_INSTRUMENT = "não informado";

/** Tela raiz do app — a navegação ordens → chegada → coleta do Task Contract T4.
 * `"loading"` é só o instante entre montar e decidir, a partir da ordem ativa persistida
 * (`orders/activeOrder.ts`), se reabre direto na chegada/coleta ou cai na lista. */
type Screen = { kind: "loading" } | { kind: "orders" } | { kind: "arrival" } | { kind: "survey" };

type Mode =
  | { kind: "collect" }
  | { kind: "add-menu" }
  | { kind: "pick-point" }
  | { kind: "pick-pair" }
  | { kind: "measure"; segment_id: string }
  | { kind: "divergence"; segment_id: string; measurement_id: string }
  | { kind: "justify"; segment_id: string; measurement_id: string }
  | { kind: "observation" };

function createSurveyForOrder(order: Order, nowIso: string): Survey {
  return {
    id: surveyIdForOrder(order.id),
    // Nome curto: é o que a AppBar de chegada/coleta exibe (pranchas 2-5 do Design
    // Approval Package mostram "Guaxindiba", nunca "Praça de Guaxindiba"). O cartão da
    // lista (prancha 1) usa `order.name` (nome completo), não este campo.
    name: order.short_name,
    order_id: order.id,
    points: [],
    segments: [],
    measurements: [],
    photo_anchors: [],
    elements: [],
    observations: [],
    created_at: nowIso,
    updated_at: nowIso,
  };
}

export interface FieldAppProps {
  repository: SurveyRepository;
}

/**
 * Orquestra o app: ordens (fixture local) → chegada (`recordArrival`) → coleta (motor de
 * `src/domain` → `applyCommand` → estado de React). Nenhum caminho desta tela grava
 * direto no repositório nem atualiza o estado antes de a operação estar no outbox — a
 * criação do survey ao baixar uma ordem é a única exceção deliberada: não é uma operação
 * do outbox (não muta um survey existente), é a criação do recurso, mesmo padrão que T3
 * já usava para o survey único do scaffold.
 *
 * A pilha de undo (`CommandHistoryEntry`) vive aqui, fora do `Survey` — é quem aplica os
 * comandos que guarda o snapshot anterior, por decisão de T2.
 */
export function FieldApp({ repository }: FieldAppProps) {
  const [screen, setScreen] = useState<Screen>({ kind: "loading" });
  const [orderStates, setOrderStates] = useState<Map<OrderId, OrderState>>(new Map());
  const [currentOrder, setCurrentOrder] = useState<Order | null>(null);
  const [survey, setSurveyState] = useState<Survey | null>(null);
  const surveyRef = useRef<Survey | null>(null);
  const [history, setHistory] = useState<CommandHistoryEntry[]>([]);
  const [mode, setMode] = useState<Mode>({ kind: "collect" });
  const [notice, setNotice] = useState<Notice | null>(null);
  const [selectedPointId, setSelectedPointId] = useState<SurveyPointId | null>(null);
  const [selectedSegmentId, setSelectedSegmentId] = useState<string | null>(null);
  const [pendingCount, setPendingCount] = useState(0);
  const [busy, setBusy] = useState(false);
  const [isOnline, setIsOnline] = useState(() =>
    typeof navigator === "undefined" ? true : navigator.onLine,
  );

  const commitSurvey = useCallback((next: Survey) => {
    surveyRef.current = next;
    setSurveyState(next);
  }, []);

  const refreshOrderStates = useCallback(async () => {
    const entries = await Promise.all(
      ORDERS.map(async (order): Promise<[OrderId, OrderState]> => {
        const existing = await repository.getSurvey(surveyIdForOrder(order.id));
        return [order.id, deriveOrderState(existing)];
      }),
    );
    setOrderStates(new Map(entries));
  }, [repository]);

  // Decide a tela inicial: ordem ativa persistida (reload volta direto à chegada/coleta —
  // AC3) ou a lista de ordens.
  useEffect(() => {
    let cancelled = false;
    void (async () => {
      const activeOrderId = getActiveOrderId();
      const activeOrder = activeOrderId === null
        ? undefined
        : ORDERS.find((order) => order.id === activeOrderId);
      if (activeOrder !== undefined) {
        const loaded = await repository.getSurvey(surveyIdForOrder(activeOrder.id));
        if (loaded !== undefined) {
          if (cancelled) {
            return;
          }
          setCurrentOrder(activeOrder);
          commitSurvey(loaded);
          const pending = await repository.getPendingOperations(loaded.id);
          if (cancelled) {
            return;
          }
          setPendingCount(pending.length);
          setScreen(loaded.context === undefined ? { kind: "arrival" } : { kind: "survey" });
          return;
        }
        // Ordem ativa referenciada não existe mais localmente (ex.: banco limpo por
        // fora) — cai para a lista em vez de travar numa referência morta.
        clearActiveOrderId();
      }
      await refreshOrderStates();
      if (!cancelled) {
        setScreen({ kind: "orders" });
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [repository, commitSurvey, refreshOrderStates]);

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

  const findings = useMemo(
    () =>
      survey === null
        ? []
        : validateSurvey(survey, {
            toleranceMm: DEFAULT_TOLERANCE_MM,
            // Task Contract T4, §5: o checklist da ordem entra na validação como
            // requiredItems (hoje só foto-acesso fica pendente; ver orders/state.ts).
            requiredItems:
              currentOrder === null ? undefined : requiredItemsForOrder(currentOrder),
          }),
    [survey, currentOrder],
  );

  /** Toques em campo chegam mais rápido que a persistência: a fila garante que cada
   * comando leia o estado que o anterior gravou (ver serialQueue.ts). */
  const queueRef = useRef(createSerialQueue());

  /**
   * Caminho único de todo comando: domínio → `applyCommand` (survey + operação gravados)
   * → estado de React, serializado pela fila. O comando é CONSTRUÍDO só na vez dele
   * (`build` recebe o survey mais recente) — construir antes, fora da fila, reintroduziria
   * a corrida de dois toques lendo o mesmo estado. Devolve o survey novo, ou `null`
   * quando o comando falhou — nesse caso nada foi persistido e a mensagem estruturada do
   * domínio vai para o banner.
   */
  const apply = useCallback(
    (
      build: (current: Survey) => CommandResult,
      options?: { undo?: boolean },
    ): Promise<Survey | null> =>
      queueRef.current(async (): Promise<Survey | null> => {
        const current = surveyRef.current;
        if (current === null) {
          return null;
        }
        setBusy(true);
        try {
          const outcome = await applyCommand(repository, current, build(current), {
            device_id: getOrCreateDeviceId(),
            operation_id: crypto.randomUUID(),
            created_at: new Date().toISOString(),
          });
          if (!outcome.ok) {
            setNotice({ tone: "error", text: outcome.error.message });
            return null;
          }
          setHistory((stack) =>
            options?.undo === true
              ? stack.slice(0, -1)
              : [
                  ...stack,
                  { command_id: outcome.operation.operation_id, previous_survey: current },
                ],
          );
          commitSurvey(outcome.survey);
          const pending = await repository.getPendingOperations(outcome.survey.id);
          setPendingCount(pending.length);
          return outcome.survey;
        } finally {
          setBusy(false);
        }
      }),
    [repository, commitSurvey],
  );

  const backToCollect = useCallback((next?: Notice | null) => {
    setMode({ kind: "collect" });
    setSelectedPointId(null);
    setNotice(next ?? null);
  }, []);

  const handleDownloadOrder = useCallback(
    (order: Order) => {
      void (async () => {
        setBusy(true);
        try {
          const existing = await repository.getSurvey(surveyIdForOrder(order.id));
          if (existing === undefined) {
            await repository.saveSurvey(createSurveyForOrder(order, new Date().toISOString()));
          }
          await refreshOrderStates();
        } finally {
          setBusy(false);
        }
      })();
    },
    [repository, refreshOrderStates],
  );

  const handleOpenOrder = useCallback(
    (order: Order) => {
      void (async () => {
        setBusy(true);
        try {
          const loaded = await repository.getSurvey(surveyIdForOrder(order.id));
          if (loaded === undefined) {
            return;
          }
          setCurrentOrder(order);
          commitSurvey(loaded);
          setHistory([]);
          setMode({ kind: "collect" });
          setSelectedPointId(null);
          setSelectedSegmentId(null);
          setNotice(null);
          const pending = await repository.getPendingOperations(loaded.id);
          setPendingCount(pending.length);
          setActiveOrderId(order.id);
          setScreen(loaded.context === undefined ? { kind: "arrival" } : { kind: "survey" });
        } finally {
          setBusy(false);
        }
      })();
    },
    [repository, commitSurvey],
  );

  const handleRecordArrival = useCallback(
    (args: { instrument: string; referenceNote: string; gps: GpsFix | "unavailable" }) => {
      void (async () => {
        const next = await apply((current) =>
          recordArrival(
            current,
            {
              instrument: args.instrument,
              reference_note: args.referenceNote,
              gps: args.gps,
            },
            new Date().toISOString(),
          ),
        );
        if (next !== null) {
          setNotice(null);
          setScreen({ kind: "survey" });
        }
      })();
    },
    [apply],
  );

  const handleCanvasTap = useCallback(
    (point: MmPoint) => {
      setNotice(null);
      void apply((current) =>
        addPoint(
          current,
          { id: crypto.randomUUID(), x_mm: point.x_mm, y_mm: point.y_mm },
          new Date().toISOString(),
        ),
      );
    },
    [apply],
  );

  const handlePointTap = useCallback(
    (pointId: SurveyPointId) => {
      const selection = selectPointForSegment(selectedPointId, pointId);
      setSelectedPointId(selection.first);
      if (selection.pair === null) {
        setNotice(null);
        return;
      }
      const [from, to] = selection.pair;
      setNotice(null);
      void (async () => {
        const next = await apply((current) =>
          addSegment(
            current,
            { id: crypto.randomUUID(), from_point_id: from, to_point_id: to },
            new Date().toISOString(),
          ),
        );
        if (next !== null) {
          // Encadear: a ponta recém-ligada já fica escolhida para o próximo segmento.
          setSelectedPointId(to);
        }
      })();
    },
    [apply, selectedPointId],
  );

  const handleSegmentTap = useCallback((segmentId: string) => {
    setSelectedSegmentId(segmentId);
    setNotice(null);
    setMode({ kind: "measure", segment_id: segmentId });
  }, []);

  const handleMeasureButton = useCallback(() => {
    if (selectedSegmentId === null) {
      setNotice({
        tone: "info",
        text: "Toque num segmento do desenho para medir — a cota nasce vinculada aos dois pontos.",
      });
      return;
    }
    setMode({ kind: "measure", segment_id: selectedSegmentId });
  }, [selectedSegmentId]);

  const handleUndo = useCallback(() => {
    const entry = history[history.length - 1];
    if (entry === undefined) {
      return;
    }
    setSelectedPointId(null);
    setSelectedSegmentId(null);
    setNotice(null);
    void apply((current) => undoLast(current, entry, new Date().toISOString()), { undo: true });
  }, [apply, history]);

  const handleClosePerimeter = useCallback(() => {
    void (async () => {
      const next = await apply((current) =>
        closePerimeter(current, { id: crypto.randomUUID() }, new Date().toISOString()),
      );
      if (next !== null) {
        backToCollect({ tone: "ok", text: "Perímetro fechado." });
      } else {
        setMode({ kind: "collect" });
      }
    })();
  }, [apply, backToCollect]);

  const handleConfirmMeasurement = useCallback(
    (segment: Segment, valueMm: number) => {
      const measurementId = crypto.randomUUID();
      void (async () => {
        const next = await apply((current) =>
          addMeasurement(
            current,
            {
              id: measurementId,
              value_mm: valueMm,
              kind: "length",
              from_point_id: segment.from_point_id,
              to_point_id: segment.to_point_id,
              instrument: surveyRef.current?.context?.instrument ?? UNDECLARED_INSTRUMENT,
              status: "confirmed",
            },
            new Date().toISOString(),
          ),
        );
        if (next === null) {
          return;
        }
        const nextFindings = validateSurvey(next, { toleranceMm: DEFAULT_TOLERANCE_MM });
        const divergence = findCriticalDivergence(measurementId, nextFindings);
        if (divergence !== null) {
          setMode({
            kind: "divergence",
            segment_id: segment.id,
            measurement_id: measurementId,
          });
          return;
        }
        setSelectedSegmentId(null);
        backToCollect();
      })();
    },
    [apply, backToCollect],
  );

  const handleJustify = useCallback(
    (measurementId: string, text: string) => {
      void (async () => {
        const next = await apply((current) =>
          justifyMeasurement(
            current,
            { measurement_id: measurementId, justification: text },
            new Date().toISOString(),
          ),
        );
        if (next !== null) {
          setSelectedSegmentId(null);
          backToCollect({
            tone: "warn",
            text: "Motivo registrado. As duas leituras ficam no histórico do levantamento.",
          });
        }
      })();
    },
    [apply, backToCollect],
  );

  const handleObservation = useCallback(
    (text: string) => {
      void (async () => {
        const next = await apply((current) =>
          addObservation(current, { id: crypto.randomUUID(), text }, new Date().toISOString()),
        );
        if (next !== null) {
          backToCollect({ tone: "ok", text: "Observação registrada." });
        }
      })();
    },
    [apply, backToCollect],
  );

  if (screen.kind === "loading") {
    return (
      <div className="flex h-dvh flex-col">
        <AppBar title={APP_BRAND} pendingCount={0} isOnline={isOnline} />
        <div className="screen">
          <div className="content">
            <p className="sub">Abrindo o levantamento guardado neste aparelho…</p>
          </div>
        </div>
      </div>
    );
  }

  if (screen.kind === "orders") {
    return (
      <div className="flex h-dvh flex-col">
        <AppBar title={APP_BRAND} pendingCount={0} isOnline={isOnline} />
        <OrdersScreen
          orders={ORDERS}
          stateByOrderId={orderStates}
          isOnline={isOnline}
          busy={busy}
          onDownload={handleDownloadOrder}
          onOpen={handleOpenOrder}
        />
      </div>
    );
  }

  if (screen.kind === "arrival") {
    return (
      <div className="flex h-dvh flex-col">
        <AppBar title={currentOrder?.short_name ?? APP_BRAND} pendingCount={0} isOnline={isOnline} />
        <ArrivalScreen notice={notice} onConfirm={handleRecordArrival} busy={busy} />
      </div>
    );
  }

  // screen.kind === "survey" a partir daqui — a navegação garante `survey` carregado; o
  // fallback abaixo só cobre a corrida entre `setScreen` e o próximo render.
  if (survey === null) {
    return (
      <div className="flex h-dvh flex-col">
        <AppBar title={currentOrder?.short_name ?? APP_BRAND} pendingCount={0} isOnline={isOnline} />
        <div className="screen">
          <div className="content">
            <p className="sub">Abrindo o levantamento guardado neste aparelho…</p>
          </div>
        </div>
      </div>
    );
  }

  const segmentLabelById = segmentLabels(survey.segments);
  const pointLabelById = pointLabels(survey.points);
  const instrumentLabel = survey.context?.instrument ?? UNDECLARED_INSTRUMENT;

  const instruction: Notice | null =
    mode.kind === "pick-point"
      ? { tone: "info", text: "Toque no desenho para marcar um ponto. Cada toque marca outro." }
      : mode.kind === "pick-pair"
        ? {
            tone: "info",
            text:
              selectedPointId === null
                ? "Toque no primeiro ponto e depois no segundo para ligá-los."
                : "Ponto inicial escolhido. Toque no segundo ponto para ligar.",
          }
        : null;

  const renderCollect = () => (
    <CollectScreen
      survey={survey}
      findings={findings}
      notice={notice ?? instruction}
      onCancelNotice={
        mode.kind === "pick-point" || mode.kind === "pick-pair"
          ? () => backToCollect()
          : notice !== null
            ? () => setNotice(null)
            : null
      }
      cancelNoticeLabel={notice !== null && instruction === null ? "Fechar" : "Cancelar"}
      selectedPointId={selectedPointId}
      selectedSegmentId={selectedSegmentId}
      onCanvasTap={mode.kind === "pick-point" ? handleCanvasTap : null}
      onPointTap={mode.kind === "pick-pair" ? handlePointTap : null}
      onSegmentTap={mode.kind === "collect" ? handleSegmentTap : null}
      canUndo={history.length > 0}
      onUndo={handleUndo}
      onOpenAddMenu={() => {
        setNotice(null);
        setMode({ kind: "add-menu" });
      }}
      onMeasure={handleMeasureButton}
      busy={busy}
    />
  );

  const renderMeasure = (segmentId: string) => {
    const segment = survey.segments.find((candidate) => candidate.id === segmentId);
    if (segment === undefined) {
      return renderCollect();
    }
    const label = segmentLabelById.get(segment.id) ?? "segmento";
    const from = pointLabelById.get(segment.from_point_id) ?? "?";
    const to = pointLabelById.get(segment.to_point_id) ?? "?";
    return (
      <MeasureScreen
        targetLabel={label}
        subtitle={`Comprimento · do ponto ${from} ao ponto ${to} · instrumento ${instrumentLabel}`}
        notice={notice}
        onConfirm={(valueMm) => handleConfirmMeasurement(segment, valueMm)}
        onCancel={() => {
          setSelectedSegmentId(null);
          backToCollect();
        }}
        busy={busy}
      />
    );
  };

  const renderScreen = () => {
    switch (mode.kind) {
      case "add-menu":
        return (
          <AddMenu
            onAddPoint={() => setMode({ kind: "pick-point" })}
            onConnectPoints={() => {
              setSelectedPointId(null);
              setMode({ kind: "pick-pair" });
            }}
            onAddObservation={() => setMode({ kind: "observation" })}
            onClosePerimeter={handleClosePerimeter}
            onCancel={() => backToCollect()}
            busy={busy}
          />
        );
      case "measure":
        return renderMeasure(mode.segment_id);
      case "divergence": {
        const finding = findCriticalDivergence(mode.measurement_id, findings);
        if (finding === null) {
          return renderCollect();
        }
        const view = buildDivergenceView(
          survey,
          finding,
          mode.measurement_id,
          DEFAULT_TOLERANCE_MM,
        );
        return (
          <DivergenceScreen
            targetLabel={segmentLabelById.get(mode.segment_id) ?? "segmento"}
            view={view}
            onMeasureAgain={() => setMode({ kind: "measure", segment_id: mode.segment_id })}
            onJustify={() =>
              setMode({
                kind: "justify",
                segment_id: mode.segment_id,
                measurement_id: mode.measurement_id,
              })
            }
            busy={busy}
          />
        );
      }
      case "justify": {
        const label = segmentLabelById.get(mode.segment_id) ?? "segmento";
        const measurementId = mode.measurement_id;
        return (
          <TextEntryScreen
            title={`Motivo da divergência em ${label}`}
            description="As duas leituras continuam registradas; o motivo viaja com elas."
            label="Por que as duas medidas ficam?"
            placeholder="Ex.: obstáculo impediu apoiar a trena no mesmo eixo"
            confirmLabel="Registrar motivo e manter as duas"
            emptyConfirmLabel="Registrar motivo (escreva o motivo)"
            notice={notice}
            onConfirm={(text) => handleJustify(measurementId, text)}
            onCancel={() =>
              setMode({
                kind: "divergence",
                segment_id: mode.segment_id,
                measurement_id: measurementId,
              })
            }
            busy={busy}
          />
        );
      }
      case "observation":
        return (
          <TextEntryScreen
            title="Observação"
            description="Anotação de campo em texto, guardada com o levantamento."
            label="O que registrar"
            placeholder="Ex.: piso do acesso norte afundado junto ao poste"
            confirmLabel="Registrar observação"
            emptyConfirmLabel="Registrar observação (escreva o texto)"
            notice={notice}
            onConfirm={handleObservation}
            onCancel={() => backToCollect()}
            busy={busy}
          />
        );
      default:
        return renderCollect();
    }
  };

  return (
    <div className="flex h-dvh flex-col">
      <AppBar title={survey.name} pendingCount={pendingCount} isOnline={isOnline} />
      {renderScreen()}
    </div>
  );
}
