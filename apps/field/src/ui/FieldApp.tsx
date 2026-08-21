import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import {
  completeSignInRedirect,
  getFreshAccessToken,
  isOidcConfigured,
  readIdentity,
  readIdentityState,
  signIn,
  type Identity,
  type IdentityState,
} from "../auth";
import {
  addMeasurement,
  addObservation,
  addPhotoAnchor,
  addPoint,
  addSegment,
  closePerimeter,
  concludeSurvey,
  justifyMeasurement,
  recordArrival,
  undoLast,
  waiveFinding,
  type CommandHistoryEntry,
} from "../domain/commands";
import type { CommandResult, GpsFix, Segment, Survey, SurveyPointId } from "../domain/types";
import { surveyStatus } from "../domain/types";
import type { Finding } from "../domain/validation";
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
import { buildMediaRecord, captureFile } from "../photos/media";
import type { SurveyRepository } from "../storage/SurveyRepository";
import {
  API_BASE_URL,
  createSyncApi,
  createSyncEngine,
  initialSyncState,
  type ConflictDecision,
  type SyncState,
} from "../sync";
import { AddMenu } from "./AddMenu";
import { ArrivalScreen } from "./ArrivalScreen";
import { AppBar, type IdentityBarProps } from "./AppBar";
import { CollectScreen } from "./CollectScreen";
import { ConcludeScreen } from "./ConcludeScreen";
import { getOrCreateDeviceId } from "./device";
import { DivergenceScreen } from "./DivergenceScreen";
import { MeasureScreen } from "./MeasureScreen";
import type { Notice } from "./notice";
import { OrdersScreen } from "./OrdersScreen";
import { PhotoAnchorScreen } from "./PhotoAnchorScreen";
import { SyncScreen } from "./SyncScreen";
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
  | { kind: "pick-photo-point" }
  | { kind: "photo-anchor"; point_id: SurveyPointId }
  | { kind: "measure"; segment_id: string }
  | { kind: "divergence"; segment_id: string; measurement_id: string }
  | { kind: "justify"; segment_id: string; measurement_id: string }
  | { kind: "observation" }
  | { kind: "conclude" }
  | { kind: "sync" }
  | { kind: "waive-finding"; finding_code: string; ref_key: string };

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
  /** `MediaRecord.id` da foto do acesso já capturada nesta chegada (T6) — vive fora do
   * `Survey` até "Começar a coleta" empacotar em `recordArrival`; `handleOpenOrder`
   * limpa ao trocar de ordem. */
  const [accessMediaRef, setAccessMediaRef] = useState<string | null>(null);
  const [pendingCount, setPendingCount] = useState(0);
  const [syncState, setSyncState] = useState<SyncState>(() =>
    initialSyncState(API_BASE_URL === null ? "local_mode" : "idle"),
  );
  const [busy, setBusy] = useState(false);
  const [isOnline, setIsOnline] = useState(() =>
    typeof navigator === "undefined" ? true : navigator.onLine,
  );

  const commitSurvey = useCallback((next: Survey) => {
    surveyRef.current = next;
    setSurveyState(next);
  }, []);

  /**
   * Motor de sincronização (T9), instância única por montagem. Sem
   * `VITE_CROQUITO_API_BASE_URL` a API é `null`: o motor opera em modo local, nenhuma
   * chamada de rede sai do app e a coleta é exatamente a de antes desta tarefa. O token
   * vem da T10 (`getFreshAccessToken`), que devolve estado — nunca exceção.
   */
  const syncEngine = useMemo(
    () =>
      createSyncEngine({
        repository,
        api:
          API_BASE_URL === null
            ? null
            : createSyncApi(API_BASE_URL, (input, init) => fetch(input, init)),
        deviceId: getOrCreateDeviceId(),
        getFreshAccessToken,
        onState: setSyncState,
      }),
    [repository],
  );

  // O contador "N pendentes" da barra passa a ler o outbox real depois de cada passada de
  // sincronização (o ack muda o que está pendente sem passar por nenhum comando).
  useEffect(() => {
    if (syncState.survey_id !== null && syncState.survey_id === surveyRef.current?.id) {
      setPendingCount(syncState.pending_operations);
    }
  }, [syncState]);

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

  /** Identidade do técnico (Task Contract T10, prancha 6c). `null`/`"signed_out"` em
   * ambiente sem `VITE_OIDC_*` — o app opera em modo local, como antes desta tarefa. */
  const [identity, setIdentity] = useState<Identity | null>(null);
  const [identityState, setIdentityState] = useState<IdentityState>("signed_out");

  // Processa o retorno do Keycloak (se houver `?code&state` na URL) uma única vez ao
  // montar, depois carrega a sessão armazenada tal como está — inclusive vencida: a
  // T10 nunca trata expiração como logout (ver `auth/oidcClient.ts`).
  useEffect(() => {
    if (!isOidcConfigured()) {
      return;
    }
    let cancelled = false;
    void (async () => {
      await completeSignInRedirect();
      const loadedIdentity = await readIdentity();
      if (!cancelled) {
        setIdentity(loadedIdentity);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  // Recomputa o estado de identidade quando a rede muda de mão (offline ↔ online é o
  // que distingue `expired_offline` de `reauth_required`, prancha 6c) e periodicamente,
  // para um token que vence com o app já aberto virar visível sem exigir reload.
  useEffect(() => {
    if (!isOidcConfigured()) {
      return;
    }
    let cancelled = false;
    const refresh = () => {
      void readIdentityState(isOnline).then((state) => {
        if (!cancelled) {
          setIdentityState(state);
        }
      });
    };
    refresh();
    const intervalId = window.setInterval(refresh, 60_000);
    return () => {
      cancelled = true;
      window.clearInterval(intervalId);
    };
  }, [isOnline]);

  const handleIdentityAction = useCallback(() => {
    void signIn();
  }, []);

  /** Vista para a barra (Task Contract T10, §3): `null` some com o indicador inteiro em
   * ambiente sem OIDC configurado — nada muda do comportamento anterior a esta tarefa. */
  const identityBar: IdentityBarProps | null = isOidcConfigured()
    ? {
        state: identityState,
        displayName: identity?.name ?? identity?.subject ?? null,
        // Aviso só informativo (Task Contract T10, §4): quem autoriza de verdade é o
        // backend a cada chamada; o app nunca bloqueia a coleta por papel ausente aqui.
        missingRole: identity !== null && !identity.roles.includes("field_technician"),
        onAction: handleIdentityAction,
      }
    : null;

  const findings = useMemo(
    () =>
      survey === null
        ? []
        : validateSurvey(survey, {
            toleranceMm: DEFAULT_TOLERANCE_MM,
            // Task Contract T4, §5 (foto-acesso derivada em T6): o checklist da ordem
            // entra na validação como requiredItems, com `survey` para derivar
            // foto-acesso a partir de `survey.context?.access_media_ref`.
            requiredItems:
              currentOrder === null ? undefined : requiredItemsForOrder(currentOrder, survey),
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
          setAccessMediaRef(null);
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
              // T6: a foto do acesso já foi capturada e salva (handleCaptureAccessPhoto)
              // antes deste botão ser tocado — aqui só a referência viaja no comando.
              access_media_ref: accessMediaRef ?? undefined,
            },
            new Date().toISOString(),
          ),
        );
        if (next !== null) {
          setAccessMediaRef(null);
          setNotice(null);
          setScreen({ kind: "survey" });
        }
      })();
    },
    [apply, accessMediaRef],
  );

  /**
   * Captura a foto do acesso na chegada (T6): grava o blob no repositório ANTES de
   * qualquer comando (mesma ordem "blob primeiro, âncora depois" do fluxo de foto
   * ancorada) — só o `MediaRecord.id` resultante fica em estado de React
   * (`accessMediaRef`), nunca o blob nem seu conteúdo. `recordArrival` (acionado só ao
   * tocar "Começar a coleta") é quem de fato liga essa referência ao survey via comando.
   */
  const handleCaptureAccessPhoto = useCallback(
    (file: File) => {
      void (async () => {
        setBusy(true);
        try {
          const captured = await captureFile(file);
          const record = buildMediaRecord({
            id: crypto.randomUUID(),
            sha256: captured.sha256,
            mime_type: captured.mime_type,
            byte_size: captured.byte_size,
            blob: captured.blob,
            created_at: new Date().toISOString(),
          });
          await repository.saveMedia(record);
          setAccessMediaRef(record.id);
          setNotice({ tone: "ok", text: "Foto do acesso registrada." });
        } finally {
          setBusy(false);
        }
      })();
    },
    [repository],
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

  /** Painel da prancha 6 — abre pela pílula de pendências da barra. Abrir NÃO dispara
   * envio: quem decide falar com a rede em campo é o técnico, tocando "Enviar". */
  const handleOpenSync = useCallback(() => {
    setNotice(null);
    setMode({ kind: "sync" });
    const current = surveyRef.current;
    if (current !== null) {
      // Só leitura local: o painel abre dizendo a verdade do outbox sem gastar rede.
      void syncEngine.refreshLocal(current.id);
    }
  }, [syncEngine]);

  const handleSendSync = useCallback(() => {
    const current = surveyRef.current;
    if (current === null) {
      return;
    }
    void syncEngine.syncSurvey(current.id);
  }, [syncEngine]);

  const handleResolveConflict = useCallback(
    (decision: ConflictDecision) => {
      void syncEngine.resolveConflict(decision);
    },
    [syncEngine],
  );

  const handleSegmentTap = useCallback((segmentId: string) => {
    setSelectedSegmentId(segmentId);
    setNotice(null);
    setMode({ kind: "measure", segment_id: segmentId });
  }, []);

  /** Escolha da âncora do fluxo "Foto ancorada" (T6): toque num ponto EXISTENTE do
   * desenho (não cria ponto novo, diferente de `handleCanvasTap`) — elemento como âncora
   * fica para quando existir catálogo (Task Contract T6, Scope). Só abre a tela de
   * captura; o comando `addPhotoAnchor` só roda na confirmação. */
  const handlePhotoAnchorPointTap = useCallback((pointId: SurveyPointId) => {
    setNotice(null);
    setMode({ kind: "photo-anchor", point_id: pointId });
  }, []);

  /**
   * Confirma a foto ancorada (T6): grava o blob primeiro (`saveMedia`), depois a âncora
   * via comando (`addPhotoAnchor` → `apply` → `applyCommand`) — nunca o inverso, e a
   * âncora sempre passa pelo comando (nunca é escrita direto no survey).
   */
  const handleConfirmPhotoAnchor = useCallback(
    (pointId: SurveyPointId, file: File) => {
      void (async () => {
        setBusy(true);
        try {
          const captured = await captureFile(file);
          const record = buildMediaRecord({
            id: crypto.randomUUID(),
            sha256: captured.sha256,
            mime_type: captured.mime_type,
            byte_size: captured.byte_size,
            blob: captured.blob,
            created_at: new Date().toISOString(),
          });
          await repository.saveMedia(record);
          const next = await apply((current) =>
            addPhotoAnchor(
              current,
              { id: crypto.randomUUID(), local_media_ref: record.id, point_id: pointId },
              new Date().toISOString(),
            ),
          );
          if (next !== null) {
            backToCollect({ tone: "ok", text: "Foto ancorada." });
          }
        } finally {
          setBusy(false);
        }
      })();
    },
    [apply, backToCollect, repository],
  );

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

  /** Toque num crítico de segmento na prancha 5: volta à coleta com o segmento já
   * selecionado (Task Contract T5, Especificação §1) — não pula direto para medir, quem
   * decide o próximo passo é o técnico, tocando "Medir" como em qualquer segmento. */
  const handleSegmentFindingTap = useCallback((segmentId: string) => {
    setSelectedSegmentId(segmentId);
    setNotice(null);
    setMode({ kind: "collect" });
  }, []);

  const handleOpenJustify = useCallback((finding: Finding) => {
    setNotice(null);
    setMode({
      kind: "waive-finding",
      finding_code: finding.code,
      ref_key: finding.refs[0] ?? finding.code,
    });
  }, []);

  const handleWaive = useCallback(
    (findingCode: string, refKey: string, text: string) => {
      void (async () => {
        const next = await apply((current) =>
          waiveFinding(
            current,
            {
              id: crypto.randomUUID(),
              finding_code: findingCode,
              ref_key: refKey,
              justification: text,
            },
            new Date().toISOString(),
          ),
        );
        if (next !== null) {
          setMode({ kind: "conclude" });
          setNotice({
            tone: "warn",
            text: "Motivo registrado. A pendência segue na lista, justificada.",
          });
        }
      })();
    },
    [apply],
  );

  /**
   * Conclui o levantamento (prancha 5): recalcula `findings` sobre o survey mais recente
   * dentro da própria fila de comandos, em vez de reusar o `findings` memoizado do
   * render — evita gatear a conclusão num estado que já ficou velho por um comando
   * anterior ainda em trânsito na fila (Task Contract T5, Especificação §2).
   */
  const handleConclude = useCallback(() => {
    void (async () => {
      const next = await apply((current) =>
        concludeSurvey(
          current,
          {
            findings: validateSurvey(current, {
              toleranceMm: DEFAULT_TOLERANCE_MM,
              requiredItems:
                currentOrder === null ? undefined : requiredItemsForOrder(currentOrder, current),
            }),
          },
          new Date().toISOString(),
        ),
      );
      if (next === null) {
        return;
      }
      // Volta às ordens (prancha 1a) com a ordem "Concluída" — limpar a ordem ativa faz
      // o reload cair na lista, não reabrir o survey que acabou de ser concluído.
      clearActiveOrderId();
      setCurrentOrder(null);
      setSelectedPointId(null);
      setSelectedSegmentId(null);
      setMode({ kind: "collect" });
      setNotice(null);
      await refreshOrderStates();
      setScreen({ kind: "orders" });
    })();
  }, [apply, currentOrder, refreshOrderStates]);

  if (screen.kind === "loading") {
    return (
      <div className="flex h-dvh flex-col">
        <AppBar title={APP_BRAND} pendingCount={0} isOnline={isOnline} identity={identityBar} />
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
        <AppBar title={APP_BRAND} pendingCount={0} isOnline={isOnline} identity={identityBar} />
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
        <AppBar title={currentOrder?.short_name ?? APP_BRAND} pendingCount={0} isOnline={isOnline} identity={identityBar} />
        <ArrivalScreen
          notice={notice}
          onConfirm={handleRecordArrival}
          busy={busy}
          accessPhotoCaptured={accessMediaRef !== null}
          onCaptureAccessPhoto={handleCaptureAccessPhoto}
        />
      </div>
    );
  }

  // screen.kind === "survey" a partir daqui — a navegação garante `survey` carregado; o
  // fallback abaixo só cobre a corrida entre `setScreen` e o próximo render.
  if (survey === null) {
    return (
      <div className="flex h-dvh flex-col">
        <AppBar title={currentOrder?.short_name ?? APP_BRAND} pendingCount={0} isOnline={isOnline} identity={identityBar} />
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
  // Survey concluído (T5): coleta vira somente leitura, sem tela nova — o aviso escrito
  // substitui qualquer notice/instrução em curso e os três comandos da bottombar somem
  // (Task Contract T5, Scope).
  const isConcluded = surveyStatus(survey) === "concluded";
  const concludedNotice: Notice = {
    tone: "info",
    text: "Levantamento concluído — somente leitura. Os dados ficam guardados neste aparelho.",
  };

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
        : mode.kind === "pick-photo-point"
          ? { tone: "info", text: "Toque num ponto do desenho para ancorar a foto." }
          : null;

  const renderCollect = () => (
    <CollectScreen
      survey={survey}
      findings={findings}
      notice={isConcluded ? concludedNotice : (notice ?? instruction)}
      onCancelNotice={
        isConcluded
          ? null
          : mode.kind === "pick-point" || mode.kind === "pick-pair" || mode.kind === "pick-photo-point"
            ? () => backToCollect()
            : notice !== null
              ? () => setNotice(null)
              : null
      }
      cancelNoticeLabel={notice !== null && instruction === null ? "Fechar" : "Cancelar"}
      selectedPointId={selectedPointId}
      selectedSegmentId={selectedSegmentId}
      onCanvasTap={isConcluded ? null : mode.kind === "pick-point" ? handleCanvasTap : null}
      onPointTap={
        isConcluded
          ? null
          : mode.kind === "pick-pair"
            ? handlePointTap
            : mode.kind === "pick-photo-point"
              ? handlePhotoAnchorPointTap
              : null
      }
      onSegmentTap={isConcluded ? null : mode.kind === "collect" ? handleSegmentTap : null}
      canUndo={!isConcluded && history.length > 0}
      onUndo={handleUndo}
      onOpenAddMenu={() => {
        setNotice(null);
        setMode({ kind: "add-menu" });
      }}
      onMeasure={handleMeasureButton}
      busy={busy}
      readOnly={isConcluded}
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
            onAddPhotoAnchor={() => {
              setSelectedPointId(null);
              setMode({ kind: "pick-photo-point" });
            }}
            onAddObservation={() => setMode({ kind: "observation" })}
            onClosePerimeter={handleClosePerimeter}
            onConclude={() => {
              setNotice(null);
              setMode({ kind: "conclude" });
            }}
            onCancel={() => backToCollect()}
            busy={busy}
          />
        );
      case "measure":
        return renderMeasure(mode.segment_id);
      case "photo-anchor": {
        const pointId = mode.point_id;
        const label = pointLabelById.get(pointId) ?? "ponto";
        return (
          <PhotoAnchorScreen
            pointLabel={label}
            notice={notice}
            busy={busy}
            onConfirm={(file) => handleConfirmPhotoAnchor(pointId, file)}
            onCancel={() => backToCollect()}
          />
        );
      }
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
      case "conclude":
        return (
          <ConcludeScreen
            survey={survey}
            findings={findings}
            notice={notice}
            onSegmentFindingTap={handleSegmentFindingTap}
            onJustify={handleOpenJustify}
            onConclude={handleConclude}
            onCancel={() => backToCollect()}
            busy={busy}
          />
        );
      case "sync":
        return (
          <SyncScreen
            state={syncState}
            surveyName={survey.name}
            onSend={handleSendSync}
            onResolveConflict={handleResolveConflict}
            onBack={() => backToCollect()}
            busy={busy}
          />
        );
      case "waive-finding": {
        const findingCode = mode.finding_code;
        const refKey = mode.ref_key;
        return (
          <TextEntryScreen
            title="Justificar pendência"
            description="A pendência segue registrada; o motivo vira dado para o projetista."
            label="Motivo"
            placeholder="Ex.: acesso lateral interditado por obra da CEDAE"
            confirmLabel="Registrar motivo"
            emptyConfirmLabel="Registrar motivo (escreva o texto)"
            notice={notice}
            onConfirm={(text) => handleWaive(findingCode, refKey, text)}
            onCancel={() => setMode({ kind: "conclude" })}
            busy={busy}
          />
        );
      }
      default:
        return renderCollect();
    }
  };

  return (
    <div className="flex h-dvh flex-col">
      <AppBar
        title={survey.name}
        pendingCount={pendingCount}
        onOpenSync={handleOpenSync}
        isOnline={isOnline}
        identity={identityBar}
      />
      {renderScreen()}
    </div>
  );
}
