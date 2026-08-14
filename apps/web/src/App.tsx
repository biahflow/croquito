import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type FormEvent,
  type MouseEvent as ReactMouseEvent,
  type PointerEvent as ReactPointerEvent,
} from "react";
import sceneSchema from "@croquito/contracts/scene.schema.json";
import type { User } from "oidc-client-ts";

import {
  annotateDimension,
  approveScene,
  createChatSession,
  createChatTurn,
  createProjectUpload,
  createProposalCalibration,
  createTraceSolve,
  getChatSession,
  getExport,
  getJob,
  getReview,
  getTraceSolve,
  listChatSessions,
  listProjects,
  requestExport,
  submitProposalBatch,
  submitProposalDecision,
  submitReviewDecision,
  submitReviewRectification,
  type ChatActDraft,
  type ChatSession,
  type ExportArtifact,
  type Review,
  type ReviewDecision,
  type ReviewReading,
  type ProjectSummary,
  type Job,
  type TraceSolveResponse,
} from "./api";
import {
  approvalReadiness,
  deriveAcceptedApproximations,
  emptyApprovalForm,
  exportInFlight,
  exportStatusLabel,
  pendingScopeCriteria,
  type ApprovalForm,
} from "./approval";
import {
  calibrationModeLabel,
  decisionActionLabel,
  derivedAnchorTitle,
  derivedDimensionLabel,
  formatDecimal,
  keepApartAxisLabel,
  measurementKindLabel,
  metricEdgeLabel,
  proposalDisplayName,
  readingLabel,
  readingStatusLabel,
  regionKindLabel,
  relationLabel,
  reviewBlockerLabel,
  suggestedAxisHint,
  traceBlockerLabel,
} from "./labels";
import {
  applyDraftToTraceDraft,
  buildChatAnchors,
  chatActAnchor,
  chatActLabel,
  chatAnswerSummary,
  chatQuestionIssue,
  chatTurnInFlight,
  chatTurnStatusLabel,
  CHAT_ANCHOR_LIMIT,
  draftToReviewDecision,
  pickOpenChatSession,
} from "./chat";
import {
  buildRectification,
  decisionMoment,
  rectificationPrefill,
  rectificationTarget,
  showsDecisionForm,
  showsDecisionRecord,
} from "./rectification";
import {
  buildTraceSolveRequest,
  DETAIL_ID_PATTERN,
  emptyTraceDraft,
  spanAxisIssue,
  traceDraftIssues,
  traceResidualSummaryLabel,
  traceSolveInFlight,
  traceSolveStatusLabel,
  withDefaultProposalFlags,
  type DerivedDimensionDraft,
  type ProposalFlagContext,
  type SpanTargetDraft,
  type TraceDetailMode,
  type TraceDraft,
} from "./trace";
import {
  applyCaptureCommit,
  captureExpectsPoint,
  captureHint,
  formatNoteTarget,
  IDLE_CAPTURE,
  parseNoteTarget,
  proposalCentrePx,
  reduceCapture,
  type CaptureEvent,
  type CaptureState,
  type NoteOrientation,
} from "./capture";
import {
  parseTraceDraft,
  serializeTraceDraft,
  traceDraftStorageKey,
} from "./traceStorage";
import {
  JUSTIFICATION_MAX_LENGTH,
  JUSTIFICATION_MIN_LENGTH,
  justificationIssue,
} from "./justification";
import {
  deriveJourney,
  journeyStepStatusLabel,
  type JourneyStepId,
} from "./journey";
import {
  clientToImagePoint,
  isMarqueeDrag,
  marqueeSelection,
  normalizedRect,
  type ImagePoint,
} from "./selection";
import {
  clearSession,
  isOidcConfigured,
  onSessionRenewed,
  readSession,
  signIn,
  signOut,
} from "./auth";
import {
  clampZoom,
  evidenceCropStyle,
  MAX_ZOOM,
  MIN_ZOOM,
  normalizeRotation,
  panScrollOffset,
  previewTransform,
  rotationShortcutDelta,
  ROTATION_SHORTCUT_KEY,
  stageStyle,
  ZOOM_STEP,
  type EvidenceCropStyle,
  type PanOrigin,
} from "./viewport";
import logoDark from "./assets/croquito-logo-dark.svg";

const MEASUREMENT_KINDS = [
  "length",
  "width",
  "height",
  "radius",
  "diameter",
] as const;

/**
 * Escolha explícita de "esta leitura é anotação da folha, não mede elemento".
 * Satisfaz o portão de associação como DECLARAÇÃO consciente (a tela aérea do
 * Guaxindiba); a decisão vai ao servidor sem `association_proposal_id` e a
 * leitura confirmada segue como aviso "não aplicada", nunca como restrição.
 * O valor nunca é enviado — não colide com o padrão `vp_...`.
 */
const ANNOTATION_OPTION = "annotation:no-element";

/** A cota escrita usa vírgula; a API exige ponto e conta as casas escritas. */
function parseWrittenValue(
  input: string,
): { value_si: string; written_decimals: number } | null {
  const normalized = input.trim().replace(",", ".");
  if (!/^\d+(?:\.\d+)?$/.test(normalized) || Number(normalized) <= 0) {
    return null;
  }
  return {
    value_si: normalized,
    written_decimals: normalized.split(".")[1]?.length ?? 0,
  };
}

/**
 * O identificador técnico não aparece em texto: quem precisa dele para abrir chamado
 * ou conferir auditoria copia daqui. `key={value}` no uso devolve o botão ao estado
 * inicial quando a seleção muda.
 */
function CopyIdButton({ value, label }: { value: string; label: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <button
      type="button"
      className="copy-id"
      title={value}
      aria-label={`Copiar identificador técnico de ${label}`}
      onClick={() => {
        void (async () => {
          try {
            const clipboard =
              typeof navigator === "undefined" ? undefined : navigator.clipboard;
            if (!clipboard) {
              return;
            }
            await clipboard.writeText(value);
            setCopied(true);
          } catch {
            // Copiar é conveniência; sem permissão a revisão continua utilizável.
          }
        })();
      }}
    >
      {copied ? "ID copiado" : "Copiar ID"}
    </button>
  );
}

/**
 * A rotação escolhida é preferência de leitura da folha, não dado do levantamento: ela
 * fica só no browser, por job, e nunca entra em decisão, manifesto, pacote ou API.
 * `localStorage` e não `sessionStorage` porque o revisor volta ao mesmo croqui deitado
 * em outro dia, e reencontrar o desenho em pé é o ponto do controle.
 */
const VIEWER_ROTATION_KEY = "croquito:viewer-rotation";

function readStoredRotation(jobId: string): number {
  if (typeof window === "undefined" || !jobId) {
    return 0;
  }
  try {
    return normalizeRotation(
      Number(window.localStorage.getItem(`${VIEWER_ROTATION_KEY}:${jobId}`)),
    );
  } catch {
    return 0;
  }
}

function writeStoredRotation(jobId: string, rotation: number): void {
  if (typeof window === "undefined" || !jobId) {
    return;
  }
  try {
    window.localStorage.setItem(
      `${VIEWER_ROTATION_KEY}:${jobId}`,
      String(normalizeRotation(rotation)),
    );
  } catch {
    // Storage indisponível só custa a preferência; a revisão continua utilizável.
  }
}

/**
 * Rascunho do aceite de traçado por job. `sessionStorage` pelo mesmo motivo da
 * declaração de aprovação: amarrar as cotas de uma folha leva dezenas de cliques e um
 * F5 não pode custar isso, mas o que foi lido do documento do cliente morre com a aba.
 */
function readStoredTraceDraft(jobId: string): string | null {
  if (typeof window === "undefined" || !jobId) {
    return null;
  }
  try {
    return window.sessionStorage.getItem(traceDraftStorageKey(jobId));
  } catch {
    return null;
  }
}

function writeStoredTraceDraft(jobId: string, value: string): void {
  if (typeof window === "undefined" || !jobId) {
    return;
  }
  try {
    window.sessionStorage.setItem(traceDraftStorageKey(jobId), value);
  } catch {
    // Storage indisponível só custa o rascunho; a revisão continua utilizável.
  }
}

function clearStoredTraceDraft(jobId: string): void {
  if (typeof window === "undefined" || !jobId) {
    return;
  }
  try {
    window.sessionStorage.removeItem(traceDraftStorageKey(jobId));
  } catch {
    // Idem: nada aqui pode impedir a revisão de seguir.
  }
}

/**
 * Recorte ampliado da leitura selecionada, com giro próprio.
 *
 * A pergunta ancora na evidência: tanto a decisão da leitura quanto a amarração do vão
 * mostram o mesmo pedaço da folha, com o mesmo mecanismo, para o revisor responder
 * olhando o que está escrito e não o identificador da cota.
 */
function EvidenceZoom({
  preview,
  crop,
  rotation,
  onRotate,
  altText,
  onNaturalSize,
}: {
  preview: string;
  crop: EvidenceCropStyle;
  rotation: number;
  onRotate: () => void;
  altText: string;
  onNaturalSize: (size: { width: number; height: number }) => void;
}) {
  return (
    <div className="evidence-zoom">
      <div className="evidence-zoom-head">
        <span>Recorte da evidência</span>
        <span className="rotate-readout">
          Recorte {normalizeRotation(rotation)}°
        </span>
        <button
          type="button"
          className="rotate-button"
          onClick={onRotate}
          aria-label="Girar o recorte 90 graus à direita"
          title="Girar 90° à direita"
        >
          ↻
        </button>
      </div>
      <div className="evidence-crop" style={crop.crop}>
        {/* O pivô tem sempre a caixa do recorte sem girar, então os percentuais
            internos referem-se aos pixels da bbox. */}
        <div className="evidence-pivot" style={crop.pivot}>
          <img
            src={preview}
            alt={altText}
            style={crop.image}
            onLoad={(event) => {
              // Mesmo cuidado do palco: `currentTarget` morre com a propagação;
              // capturar antes do updater.
              const { naturalWidth, naturalHeight } = event.currentTarget;
              onNaturalSize({ width: naturalWidth, height: naturalHeight });
            }}
          />
        </div>
      </div>
    </div>
  );
}

/** Orientação da aresta que ancora a nota presa; `auto` deixa o traçado decidir. */
const NOTE_ORIENTATION_LABELS: Record<NoteOrientation, string> = {
  auto: "automática",
  v: "vertical (#v)",
  h: "horizontal (#h)",
};

/**
 * As três declarações por forma do aceite de traçado. Cada uma é um ato do revisor
 * sobre um elemento aceito, nunca inferência: hachura marca região da folha, sem
 * legenda tira o nome da prancha e "como desenhado" declara o elemento não-ortogonal.
 */
const TRACE_FLAGS = [
  { field: "hatch", label: "hachura" },
  { field: "unlabelled", label: "sem legenda" },
  { field: "freeform", label: "como desenhado" },
] as const;

const DETAIL_MODE_LABELS: Record<TraceDetailMode, string> = {
  solve: "escala verdadeira",
  sketch: "sem escala",
};

/** Job cuja revisão existe e continua consultável depois dos atos formais. */
const REVIEWABLE_JOB_STATUSES = new Set([
  "REVIEW_REQUIRED",
  "APPROVED",
  "EXPORTING",
  "COMPLETED",
]);

function jobStatusLabel(job: Pick<Job, "status" | "stage">): string {
  if (job.status === "FAILED") {
    return "Falhou";
  }
  if (job.status === "REVIEW_REQUIRED") {
    return "Pronto para revisão";
  }
  if (job.status === "APPROVED") {
    return "Aprovado — revisão consultável";
  }
  if (job.status === "EXPORTING") {
    return "Exportando";
  }
  if (job.status === "COMPLETED") {
    return "Exportado — revisão consultável";
  }
  if (job.status === "UPLOADED" || job.status === "PROCESSING") {
    return "Em processamento";
  }
  return job.stage.toLowerCase();
}

export function App() {
  const [session, setSession] = useState<User | null>(null);
  const [projects, setProjects] = useState<ProjectSummary[]>([]);
  const [jobId, setJobId] = useState(() =>
    typeof window === "undefined"
      ? ""
      : (new URLSearchParams(window.location.search).get("job") ?? ""),
  );
  const [selectedJob, setSelectedJob] = useState<Job | null>(null);
  const [review, setReview] = useState<Review | null>(null);
  const [selectedReadingId, setSelectedReadingId] = useState("");
  const [selectedProposalId, setSelectedProposalId] = useState("");
  const [correction, setCorrection] = useState("");
  const [correctionValue, setCorrectionValue] = useState("");
  const [correctionUnit, setCorrectionUnit] = useState<"m" | "mm">("m");
  const [correctionKind, setCorrectionKind] = useState("");
  // Correção de decisão registrada em curso. Enquanto for null, leitura decidida só
  // mostra o registro: o formulário não reabre sozinho.
  const [rectifyingReadingId, setRectifyingReadingId] = useState<string | null>(
    null,
  );
  // Nunca pré-preenchido: o texto gravado como justificativa é sempre do revisor.
  const [decisionJustification, setDecisionJustification] = useState("");
  const [loading, setLoading] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [conflict, setConflict] = useState(false);
  const [pollTick, setPollTick] = useState(0);
  // Sucesso pode sumir sozinho; erro não. Um erro que se apaga é um erro perdido.
  const [toast, setToast] = useState<string | null>(null);
  const [showProposals, setShowProposals] = useState(false);
  const [batchIds, setBatchIds] = useState<Set<string>>(new Set());
  const [batchJustification, setBatchJustification] = useState("");
  const [bindingReadingId, setBindingReadingId] = useState<string | null>(null);
  // Nunca pré-preenchido: o texto gravado como justificativa é sempre do revisor.
  const [bindingJustification, setBindingJustification] = useState("");
  const [zoom, setZoom] = useState(MIN_ZOOM);
  const [rotation, setRotation] = useState(0);
  const [evidenceRotation, setEvidenceRotation] = useState(0);
  // Sem `proposals` a revisão não declara as dimensões da página; a própria imagem
  // carregada informa o tamanho para o palco e para o overlay da evidência.
  const [naturalImageSize, setNaturalImageSize] = useState<{
    width: number;
    height: number;
  } | null>(null);
  const [panning, setPanning] = useState(false);
  // Retângulo de seleção em pixels da imagem, só para desenhar o rastro do arrasto.
  const [marquee, setMarquee] = useState<{
    start: ImagePoint;
    current: ImagePoint;
  } | null>(null);
  const drawingCanvasRef = useRef<HTMLDivElement | null>(null);
  const previewTransformRef = useRef<HTMLDivElement | null>(null);
  const panOriginRef = useRef<(PanOrigin & { pointerId: number }) | null>(null);
  // A origem do retângulo mora na ref, e não só no estado: o ponto que decide a
  // seleção não pode depender de o último `pointermove` já ter sido renderizado.
  const marqueeOriginRef = useRef<{
    pointerId: number;
    clientX: number;
    clientY: number;
    start: ImagePoint;
  } | null>(null);
  const [selectedGeometryProposalId, setSelectedGeometryProposalId] =
    useState("");
  const [firstAnchorProposalId, setFirstAnchorProposalId] = useState("");
  const [secondAnchorProposalId, setSecondAnchorProposalId] = useState("");
  const [proposalJustification, setProposalJustification] = useState("");
  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [projectName, setProjectName] = useState("");
  const [defaultUnit, setDefaultUnit] = useState<"m" | "mm">("m");
  const [approvalForm, setApprovalForm] =
    useState<ApprovalForm>(emptyApprovalForm);
  const [approvedRevisionId, setApprovedRevisionId] = useState("");
  const [exportArtifact, setExportArtifact] = useState<ExportArtifact | null>(
    null,
  );
  // O aceite de traçado reusa a seleção do lote: `batchIds` continua sendo a única
  // fonte das formas escolhidas, e este estado guarda só o que se declara sobre elas.
  const [traceDeclarations, setTraceDeclarations] =
    useState<TraceDraft>(emptyTraceDraft);
  const [traceSolve, setTraceSolve] = useState<TraceSolveResponse | null>(null);
  const [detailId, setDetailId] = useState("");
  const [detailTitle, setDetailTitle] = useState("");
  const [detailMode, setDetailMode] = useState<TraceDetailMode>("solve");
  // Um aceite concluído só é tratado uma vez; o polling continua devolvendo o mesmo
  // registro e recarregar a revisão em laço apagaria a seleção do próximo lote.
  const handledTraceSolveRef = useRef<string | null>(null);
  // Conversa da revisão. O painel é auxiliar: ele não é etapa da jornada, não guarda
  // nada em storage nesta fatia e nenhum caminho daqui submete ato — a sessão vem do
  // servidor e o rascunho só chega até o formulário que o profissional assina.
  const [chatOpen, setChatOpen] = useState(false);
  const [chatSession, setChatSession] = useState<ChatSession | null>(null);
  const [chatQuestion, setChatQuestion] = useState("");
  const [chatSending, setChatSending] = useState(false);
  // Erro da conversa mora no painel: o `message` global pertence ao fluxo de decisão e
  // aparece dentro do formulário dela.
  const [chatMessage, setChatMessage] = useState<string | null>(null);
  // Âncoras que o revisor tirou da pergunta antes de enviar; a seleção da tela continua
  // intacta, quem some é só o que a pergunta cita.
  const [chatDroppedAnchors, setChatDroppedAnchors] = useState<Set<string>>(
    new Set(),
  );
  const [chatEvidenceRotation, setChatEvidenceRotation] = useState(0);
  // Rascunho de decisão a caminho do formulário. Ele não pode ser escrito direto no
  // estado do formulário: trocar de leitura dispara o efeito que limpa justificativa e
  // associação, e o rascunho seria apagado no mesmo commit.
  const [chatPrefill, setChatPrefill] = useState<{
    readingId: string;
    associationValue: string;
    justification: string;
  } | null>(null);
  // A conversa é buscada uma vez por projeto, quando o painel abre.
  const chatLoadedJobRef = useRef<string | null>(null);
  // Gesto de amarração em andamento (vão, nota, cota derivada). Ele é estado de tela,
  // nunca vai à API, e não é persistido: gesto pela metade não é declaração.
  const [capture, setCapture] = useState<CaptureState>(IDLE_CAPTURE);
  // A máquina lê o estado corrente da ref, e não do closure: dois cliques no mesmo
  // tique (forma e ponto) precisam enxergar o resultado do anterior.
  const captureRef = useRef<CaptureState>(IDLE_CAPTURE);
  // O rascunho só é regravado depois de restaurado para este job; sem isto a troca de
  // projeto grava o rascunho antigo por cima do rascunho do projeto aberto.
  const restoredTraceJobRef = useRef<string | null>(null);
  // Etapa reaberta por clique. Enquanto for null, a jornada segue o fluxo sozinha.
  const [openStep, setOpenStep] = useState<JourneyStepId | null>(null);

  const selectedReading =
    review?.packet.readings.find(
      (reading) => reading.id === selectedReadingId,
    ) ?? null;
  const selectedEvidenceBox =
    selectedReading?.evidence?.coordinate_space === "source_image_pixels"
      ? selectedReading.evidence.bbox
      : null;
  const preview = review?.preview_urls.source_image_url;
  const overlay = review?.preview_urls.review_overlay_url;
  // A revisão declara as dimensões da página quando traz propostas de visão. Quando não
  // traz, a imagem carregada é a única fonte — e é fonte de apresentação, não de
  // geometria: nada aqui vira coordenada enviada à API.
  const imageWidthPx =
    review?.proposals?.image_width_px ?? naturalImageSize?.width ?? 0;
  const imageHeightPx =
    review?.proposals?.image_height_px ?? naturalImageSize?.height ?? 0;
  const hasImageSize = imageWidthPx > 0 && imageHeightPx > 0;
  const evidenceCrop = selectedEvidenceBox
    ? evidenceCropStyle(
        selectedEvidenceBox,
        imageWidthPx,
        imageHeightPx,
        evidenceRotation,
      )
    : null;
  const marqueeRect = marquee
    ? normalizedRect(marquee.start, marquee.current)
    : null;
  const candidates = useMemo(
    () =>
      review?.associations.candidates.filter(
        (candidate) => candidate.reading_id === selectedReadingId,
      ) ?? [],
    [review, selectedReadingId],
  );
  const confirmedCount =
    review?.packet.readings.filter((reading) => reading.status === "confirmed")
      .length ?? 0;
  const proposals = review?.proposals?.proposals ?? [];
  const proposalById = new Map(
    proposals.map((proposal) => [proposal.id, proposal]),
  );
  // O balão numerado vem da posição na lista e vale em toda a tela: lista, associação,
  // calibração e régua têm de chamar a mesma proposta pelo mesmo nome.
  const proposalOrdinalById = new Map(
    proposals.map((proposal, index) => [proposal.id, index + 1]),
  );
  const entityById = new Map(
    (review?.scene?.entities ?? []).map((entity) => [entity.id, entity]),
  );
  const proposalName = (proposalId: string | undefined): string =>
    proposalDisplayName(
      proposalId ? proposalById.get(proposalId) : undefined,
      proposalOrdinalById.get(proposalId ?? "") ?? 0,
      review?.calibration?.scale_m_per_px,
    );
  // Só proposta aceita virou entidade na cena; é nela que uma cota pode ser amarrada.
  const tracedProposalIds = new Set(
    (review?.proposal_decisions ?? [])
      .filter((decision) => decision.action === "accept" && decision.entity_id)
      .map((decision) => decision.proposal_id),
  );
  const boundReadingIds = new Set(
    (review?.scene?.entities ?? [])
      .filter(
        (entity) =>
          entity.kind === "dimension" || entity.kind === "diameter_dimension",
      )
      .flatMap((entity) => entity.provenance?.source_ids ?? []),
  );
  const readingIsBound = (readingId: string) => boundReadingIds.has(readingId);
  const undecidedProposals = proposals.filter(
    (proposal) =>
      !(review?.proposal_decisions ?? []).some(
        (decision) => decision.proposal_id === proposal.id,
      ),
  );
  const proposalDecisionById = new Map(
    review?.proposal_decisions.map((decision) => [
      decision.proposal_id,
      decision,
    ]) ?? [],
  );
  const lineProposals = proposals.filter(
    (proposal) =>
      proposal.kind === "line" && !proposalDecisionById.has(proposal.id),
  );
  const anchorEntities =
    review?.scene?.entities.filter(
      (entity) =>
        entity.kind === "line" &&
        (entity.precision === "exact" || entity.precision === "derived"),
    ) ?? [];
  const selectedGeometryProposal =
    proposals.find((proposal) => proposal.id === selectedGeometryProposalId) ??
    null;
  const readiness = review
    ? approvalReadiness(review, approvalForm)
    : { canApprove: false, reasons: [] };
  const scopeCriteria = review ? pendingScopeCriteria(review) : [];
  // O texto canônico do critério vem de `required_criteria`; a issue da cena diz em qual
  // dos dois desfechos ele parou. Issue que não é critério declarado não entra no resumo.
  const criterionTexts = new Map(
    (review?.required_criteria ?? []).map((criterion) => [
      criterion.code,
      criterion.text,
    ]),
  );
  const declaredCriteriaTexts = (status: "resolved" | "accepted") =>
    (review?.scene?.issues ?? [])
      .filter(
        (issue) => issue.status === status && criterionTexts.has(issue.code),
      )
      .map((issue) => criterionTexts.get(issue.code) ?? issue.message);
  const coveredSceneCriteria = declaredCriteriaTexts("resolved");
  const acknowledgedSceneCriteria = declaredCriteriaTexts("accepted");
  const acceptedApproximations = review
    ? deriveAcceptedApproximations(review)
    : [];
  const traceDraft = useMemo<TraceDraft>(
    () => ({ ...traceDeclarations, proposalIds: [...batchIds] }),
    [traceDeclarations, batchIds],
  );
  // O contexto liga a pré-validação ao pacote real: leitura confirmada, vão herdado da
  // associação observacional e os limites da página. Sem ele as regras que dependem
  // desses dados simplesmente não rodariam.
  const traceIssues = traceDraftIssues(
    traceDraft,
    proposals,
    review?.calibration?.scale_m_per_px,
    review
      ? {
          readings: review.packet.readings,
          selectedAssociations: review.selected_associations,
          imageWidthPx: review.proposals?.image_width_px,
          imageHeightPx: review.proposals?.image_height_px,
        }
      : undefined,
  );
  const traceResidualLabel = traceResidualSummaryLabel(
    traceSolve?.residual_summary ?? null,
  );
  const groupedProposalIds = new Set(
    traceDraft.detailGroups.flatMap((group) => group.proposalIds),
  );
  // Agrupar leva para o detalhe só o que ainda não está em grupo nenhum: a mesma forma
  // em dois grupos é recusada pelo contrato, e o revisor agrupa um detalhe por vez.
  const ungroupedSelection = traceDraft.proposalIds.filter(
    (proposalId) => !groupedProposalIds.has(proposalId),
  );
  // Leitura confirmada é o sujeito da amarração: decisão registrada é imutável e esta
  // subseção nunca a reabre — ela só declara o que a cota mede no desenho.
  const confirmedReadings =
    review?.packet.readings.filter((reading) => reading.status === "confirmed") ??
    [];
  const capturing = capture.kind !== "idle";
  /**
   * Rascunho desenhado sobre a folha: âncoras dos trechos, ponto da cota derivada e a
   * linha do vão entre duas formas. É eco visual do que a lista já diz por escrito —
   * desenho e cor nunca são o único indicador — e nunca intercepta clique.
   */
  const draftAnchors = [
    ...Object.entries(traceDraft.associations).flatMap(([readingId, target]) =>
      target.kind === "declared"
        ? target.spansPx.flatMap((span, spanIndex) =>
            span.map((anchor, endIndex) => ({
              key: `span:${readingId}:${spanIndex}:${endIndex}`,
              x: anchor[0],
              y: anchor[1],
            })),
          )
        : [],
    ),
    ...traceDraft.derivedDimensions.map((dimension, index) => ({
      key: `derived:${index}`,
      x: dimension.nearXPx,
      y: dimension.nearYPx,
    })),
    ...(capture.kind === "declared"
      ? capture.anchors.map((anchor, index) => ({
          key: `capture:${index}`,
          x: anchor[0],
          y: anchor[1],
        }))
      : []),
  ];
  const draftSpanLines = Object.entries(traceDraft.associations).flatMap(
    ([readingId, target]) => {
      if (target.kind === "declared") {
        return target.spansPx.map((span, spanIndex) => ({
          key: `declared:${readingId}:${spanIndex}`,
          x1: span[0][0],
          y1: span[0][1],
          x2: span[1][0],
          y2: span[1][1],
        }));
      }
      if (target.kind !== "pair") {
        return [];
      }
      const first = proposalById.get(target.proposalIds[0]);
      const second = proposalById.get(target.proposalIds[1]);
      if (!first || !second) {
        return [];
      }
      const from = proposalCentrePx(first.geometry);
      const to = proposalCentrePx(second.geometry);
      return [
        { key: `pair:${readingId}`, x1: from.x, y1: from.y, x2: to.x, y2: to.y },
      ];
    },
  );
  // O marcador vive no espaço da folha (milhares de pixels): raio fixo sumiria. O traço
  // continua em `non-scaling-stroke`, como o resto do overlay.
  const draftMarkerRadius = Math.max(
    4,
    Math.round(Math.max(imageWidthPx, imageHeightPx) / 160),
  );
  // Área de clique das formas: com `non-scaling-stroke` o navegador testa o traço na
  // geometria PRÉ-transformação, e uma linha fina da folha escalada fica com alvo
  // sub-pixel — medido com elementFromPoint: nenhum acerto em ±3px do eixo. O gêmeo
  // de acerto usa traço em unidades da folha (hit-test convencional) e fica invisível.
  const hitStrokeWidth = Math.max(
    8,
    Math.round(Math.max(imageWidthPx, imageHeightPx) / 300),
  );

  const dispatchCapture = useCallback((event: CaptureEvent) => {
    const result = reduceCapture(captureRef.current, event);
    captureRef.current = result.state;
    setCapture(result.state);
    const commit = result.commit;
    if (commit) {
      setTraceDeclarations((current) => applyCaptureCommit(current, commit));
    }
  }, []);

  const beginCapture = useCallback(
    (next: CaptureState) => {
      // Trocar de gesto conclui o anterior: um vão declarado pela metade não perde os
      // trechos que já fecharam.
      dispatchCapture({ type: "cancel" });
      // Sem o overlay de pé não há onde clicar; entrar em captura abre as formas.
      setShowProposals(true);
      captureRef.current = next;
      setCapture(next);
    },
    [dispatchCapture],
  );

  /** Clique parado no palco vira âncora em pixels da imagem, na rotação atual. */
  function dispatchImagePoint(clientX: number, clientY: number) {
    const transform = previewTransformRef.current;
    if (!transform) {
      return;
    }
    const point = clientToImagePoint(
      clientX,
      clientY,
      transform.getBoundingClientRect(),
      rotation,
      imageWidthPx,
      imageHeightPx,
    );
    // A âncora é um pixel da folha; o subpixel do ponteiro não acrescenta informação.
    dispatchCapture({
      type: "point",
      xPx: Math.round(point.x),
      yPx: Math.round(point.y),
    });
  }

  /**
   * Na captura o clique na forma vale mesmo sobre forma já decidida — um vão pode
   * amarrar um elemento aceito antes. E quando o gesto espera PONTO, o clique sobre a
   * forma também é ponto: a ponta do trecho quase sempre cai em cima do traço.
   */
  function handleCaptureShapeClick(
    proposalId: string,
    event: ReactMouseEvent<SVGElement>,
  ) {
    if (captureExpectsPoint(capture)) {
      dispatchImagePoint(event.clientX, event.clientY);
      return;
    }
    dispatchCapture({ type: "shape", proposalId });
  }

  // A jornada é derivada do que a página já tem; nenhuma chamada nova entra aqui.
  const journey = useMemo(
    () =>
      deriveJourney({
        review,
        traceSolve,
        exportArtifact,
        approvedRevisionId,
      }),
    [review, traceSolve, exportArtifact, approvedRevisionId],
  );
  // Etapa efetivamente aberta: a escolhida por clique ou, na falta dela, a ativa.
  // Etapa bloqueada nunca abre, nem por um clique que envelheceu.
  const openStepId = openStep ?? journey.activeStep;
  const visibleStep =
    journey.steps.find((step) => step.id === openStepId)?.status === "blocked"
      ? null
      : openStepId;

  // Quando o servidor faz a jornada andar — o traçado resolveu, a aprovação entrou —, a
  // tela volta a seguir o fluxo: a etapa reaberta por clique deixa de valer.
  useEffect(() => {
    setOpenStep(null);
  }, [journey.activeStep]);

  // O painel da conversa acompanha as duas etapas em que a folha ainda está em leitura.
  // Ele não é etapa da jornada: some quando a revisão passa a ser aprovação ou export.
  const chatAvailable =
    review !== null && (visibleStep === "decisions" || visibleStep === "trace");
  const traceStepAvailable =
    journey.steps.find((step) => step.id === "trace")?.status !== "blocked";
  const chatTurns = chatSession?.turns ?? [];
  const lastChatTurn = chatTurns[chatTurns.length - 1] ?? null;
  // Espelho do `traceSolveInFlight`: com turno em voo o servidor recusa a próxima
  // pergunta da sessão (`CHAT_TURN_PENDING`), então a tela nem a oferece.
  const chatBusy = chatTurnInFlight(lastChatTurn);
  // A pergunta aponta o que o revisor já tem em mãos: a leitura aberta e as formas
  // marcadas no desenho. Nada é inferido por proximidade, e cada chip sai por clique.
  const chatAnchors = buildChatAnchors(
    selectedReadingId && !chatDroppedAnchors.has(selectedReadingId)
      ? [selectedReadingId]
      : [],
    [...batchIds].filter((proposalId) => !chatDroppedAnchors.has(proposalId)),
  );
  const chatAnchorChips = [
    ...chatAnchors.reading_ids.map((readingId) => {
      const anchored = review?.packet.readings.find(
        (reading) => reading.id === readingId,
      );
      return {
        id: readingId,
        label: anchored ? readingLabel(anchored) : "leitura selecionada",
      };
    }),
    ...chatAnchors.proposal_ids.map((proposalId) => ({
      id: proposalId,
      label: proposalName(proposalId),
    })),
  ];
  const chatAnchorOverflow =
    [...batchIds].filter((proposalId) => !chatDroppedAnchors.has(proposalId))
      .length > CHAT_ANCHOR_LIMIT;

  function showApiError(error: unknown, fallback: string) {
    const text = error instanceof Error ? error.message : fallback;
    if (text.startsWith("INVALID_TOKEN:")) {
      void clearSession();
      setSession(null);
      setProjects([]);
      setReview(null);
      setSelectedJob(null);
      setMessage("Sua sessão expirou. Entre novamente para continuar.");
      return;
    }
    setMessage(text);
  }

  async function loadReview(accessToken: string, requestedJobId = jobId) {
    if (!requestedJobId) {
      return;
    }
    setLoading(true);
    setMessage(null);
    try {
      const current = await getReview(accessToken, requestedJobId);
      setReview(current);
      const firstPending = current.packet.readings.find((reading) =>
        ["proposed", "ambiguous"].includes(reading.status),
      );
      const reading = firstPending ?? current.packet.readings[0];
      setSelectedReadingId(reading?.id ?? "");
      const firstCandidate = current.associations.candidates.find(
        (candidate) => candidate.reading_id === reading?.id,
      );
      setSelectedProposalId(firstCandidate?.proposal_id ?? "");
      const firstProposal = current.proposals?.proposals.find(
        (proposal) =>
          !current.proposal_decisions.some(
            (decision) => decision.proposal_id === proposal.id,
          ),
      );
      setSelectedGeometryProposalId(firstProposal?.id ?? "");
      setConflict(false);
    } catch (error) {
      setReview(null);
      setMessage(
        error instanceof Error
          ? error.message
          : "Não foi possível carregar a revisão.",
      );
    } finally {
      setLoading(false);
    }
  }

  async function openJob(accessToken: string, requestedJobId: string) {
    setJobId(requestedJobId);
    window.history.replaceState(
      null,
      "",
      `?job=${encodeURIComponent(requestedJobId)}`,
    );
    setLoading(true);
    setMessage(null);
    try {
      const current = await getJob(accessToken, requestedJobId);
      setSelectedJob(current);
      if (REVIEWABLE_JOB_STATUSES.has(current.status)) {
        // A revisão sobrevive à aprovação e ao export: a jornada reabre as etapas
        // concluídas para conferência e para uma nova rodada de traçado.
        await loadReview(accessToken, requestedJobId);
      } else {
        setReview(null);
        setMessage(
          current.status === "FAILED"
            ? "Este processamento falhou. Consulte a equipe responsável para repetir a etapa segura."
            : `${jobStatusLabel(current)}. A revisão será aberta automaticamente quando estiver disponível.`,
        );
      }
    } catch (error) {
      setReview(null);
      setSelectedJob(null);
      setMessage(
        error instanceof Error
          ? error.message
          : "Não foi possível carregar o projeto.",
      );
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    if (!isOidcConfigured()) {
      return;
    }
    void (async () => {
      let currentSession: User | null;
      try {
        currentSession = await readSession();
      } catch (error) {
        // Falha aqui é OIDC de verdade; erro de API abaixo tem outra causa.
        setMessage(
          `Não foi possível validar a sessão OIDC: ${
            error instanceof Error ? error.message : String(error)
          }`,
        );
        return;
      }
      setSession(currentSession);
      if (!currentSession?.access_token) {
        return;
      }
      try {
        setProjects(await listProjects(currentSession.access_token));
        if (jobId) {
          await openJob(currentSession.access_token, jobId);
        }
      } catch (error) {
        showApiError(error, "Não foi possível carregar os projetos do tenant.");
      }
    })();
    return onSessionRenewed(setSession);
  }, []);

  /**
   * O `?job` do link só é lido na montagem, e a volta do Keycloak reescreve a URL
   * depois disso (`readSession` devolve à URL o job que viajou no `state`). Esta
   * releitura fecha a corrida: uma vez só, quando a sessão fica pronta e nenhum job
   * está aberto. Sem ela, quem abre um link de revisão sem sessão volta do login na
   * lista de projetos e precisa reencontrar o croqui.
   */
  const urlJobRereadRef = useRef(false);
  useEffect(() => {
    if (!session?.access_token || jobId || urlJobRereadRef.current) {
      return;
    }
    urlJobRereadRef.current = true;
    const fromUrl = new URLSearchParams(window.location.search).get("job");
    if (fromUrl) {
      void openJob(session.access_token, fromUrl);
    }
  }, [session?.access_token, jobId]);

  useEffect(() => {
    if (
      !session?.access_token ||
      !jobId ||
      review ||
      selectedJob?.status === "FAILED"
    ) {
      return;
    }
    const retry = window.setTimeout(() => {
      // `pollTick` reagenda a próxima tentativa. Sem ele, um job parado no mesmo
      // status deixa as dependências idênticas e o efeito nunca volta a rodar.
      void openJob(session.access_token, jobId).finally(() =>
        setPollTick((tick) => tick + 1),
      );
    }, 2_000);
    return () => window.clearTimeout(retry);
  }, [jobId, review, selectedJob?.status, session?.access_token, pollTick]);

  // A declaração tem 20 a 500 caracteres e se perdia inteira a cada recarga.
  // sessionStorage e não localStorage: sobrevive ao reload, morre com a aba, e o texto
  // do profissional sobre documento de cliente não fica no disco depois da sessão.
  useEffect(() => {
    if (!jobId) {
      return;
    }
    const draft = window.sessionStorage.getItem(`croquito:approval:${jobId}`);
    if (!draft) {
      return;
    }
    try {
      setApprovalForm({ ...emptyApprovalForm, ...JSON.parse(draft) });
    } catch {
      window.sessionStorage.removeItem(`croquito:approval:${jobId}`);
    }
  }, [jobId]);

  useEffect(() => {
    if (!jobId) {
      return;
    }
    window.sessionStorage.setItem(
      `croquito:approval:${jobId}`,
      JSON.stringify(approvalForm),
    );
  }, [jobId, approvalForm]);

  useEffect(() => {
    if (!toast) {
      return;
    }
    const dismiss = window.setTimeout(() => setToast(null), 5_000);
    return () => window.clearTimeout(dismiss);
  }, [toast]);

  useEffect(() => {
    const candidate = candidates[0]?.proposal_id ?? "";
    setSelectedProposalId(candidate);
    setCorrection("");
    setCorrectionValue("");
    setCorrectionUnit("m");
    setCorrectionKind("");
    setDecisionJustification("");
    // Trocar de leitura fecha a correção em curso: o formulário aberto pertence à
    // leitura que o revisor estava corrigindo, não à próxima.
    setRectifyingReadingId(null);
    // O recorte nasce na rotação em que o revisor está lendo a folha e continua
    // ajustável sozinho: as cotas da mesma folha estão escritas em orientações
    // diferentes entre si. `rotation` é lido, de propósito, no instante da seleção.
    setEvidenceRotation(rotation);
  }, [selectedReadingId]);

  /**
   * Rascunho da conversa levado ao formulário de decisão.
   *
   * Este efeito é declarado DEPOIS do efeito de troca de leitura de propósito: os dois
   * disparam no mesmo commit quando o rascunho seleciona outra leitura, e o de cima
   * limpa justificativa e associação. Quem escreve por último é este.
   */
  useEffect(() => {
    if (!chatPrefill || chatPrefill.readingId !== selectedReadingId) {
      return;
    }
    setSelectedProposalId(chatPrefill.associationValue);
    setDecisionJustification(chatPrefill.justification);
    setChatPrefill(null);
  }, [chatPrefill, selectedReadingId]);

  // Preferência de leitura por job, restaurada ao reabrir o mesmo croqui.
  useEffect(() => {
    setRotation(readStoredRotation(jobId));
  }, [jobId]);

  useEffect(() => {
    setNaturalImageSize(null);
  }, [preview]);

  const rotateViewer = useCallback(
    (delta: number) => {
      const next = normalizeRotation(rotation + delta);
      setRotation(next);
      writeStoredRotation(jobId, next);
    },
    [jobId, rotation],
  );

  useEffect(() => {
    if (!preview) {
      return;
    }
    function handleKeyDown(event: KeyboardEvent) {
      const target = event.target as HTMLElement | null;
      const tagName = target?.tagName ?? "";
      const delta = rotationShortcutDelta({
        key: event.key,
        shiftKey: event.shiftKey,
        ctrlKey: event.ctrlKey,
        metaKey: event.metaKey,
        altKey: event.altKey,
        typingInField:
          target?.isContentEditable === true ||
          ["INPUT", "TEXTAREA", "SELECT"].includes(tagName),
      });
      if (delta === null) {
        return;
      }
      event.preventDefault();
      rotateViewer(delta);
    }
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [preview, rotateViewer]);

  /**
   * Pan por arrasto no próprio container rolável: imagem e overlays são filhos do mesmo
   * transform, então eles andam juntos por construção. Scroll e teclado continuam
   * valendo; o arrasto só é mais direto quando a folha está ampliada.
   */
  function startPan(event: ReactPointerEvent<HTMLDivElement>) {
    const canvas = drawingCanvasRef.current;
    if (!canvas || event.button !== 0 || event.pointerType === "touch") {
      return;
    }
    const target = event.target as Element | null;
    // Clique em controle ou em proposta clicável pertence ao controle, não ao arrasto —
    // inclusive no gêmeo de acerto, que é quem recebe o ponteiro em cima do traço.
    if (
      target?.closest(
        "button, a, input, select, textarea, .proposal-shape, .proposal-hit",
      )
    ) {
      return;
    }
    // Shift+arrasto desenha o retângulo de seleção; sem Shift o gesto continua sendo
    // pan. Durante a amarração de uma cota o alvo é uma linha só, não um lote.
    const transform = previewTransformRef.current;
    if (
      event.shiftKey &&
      transform &&
      review?.proposals &&
      showProposals &&
      !bindingReadingId &&
      !capturing
    ) {
      const start = clientToImagePoint(
        event.clientX,
        event.clientY,
        transform.getBoundingClientRect(),
        rotation,
        imageWidthPx,
        imageHeightPx,
      );
      marqueeOriginRef.current = {
        pointerId: event.pointerId,
        clientX: event.clientX,
        clientY: event.clientY,
        start,
      };
      setMarquee({ start, current: start });
      canvas.setPointerCapture(event.pointerId);
      // Sem isto o arrasto com Shift vira seleção de texto da página.
      event.preventDefault();
      return;
    }
    panOriginRef.current = {
      pointerId: event.pointerId,
      pointerX: event.clientX,
      pointerY: event.clientY,
      scrollLeft: canvas.scrollLeft,
      scrollTop: canvas.scrollTop,
    };
    canvas.setPointerCapture(event.pointerId);
    setPanning(true);
  }

  function movePan(event: ReactPointerEvent<HTMLDivElement>) {
    const marqueeOrigin = marqueeOriginRef.current;
    if (marqueeOrigin) {
      const transform = previewTransformRef.current;
      if (marqueeOrigin.pointerId !== event.pointerId || !transform) {
        return;
      }
      const current = clientToImagePoint(
        event.clientX,
        event.clientY,
        transform.getBoundingClientRect(),
        rotation,
        imageWidthPx,
        imageHeightPx,
      );
      setMarquee({ start: marqueeOrigin.start, current });
      return;
    }
    const origin = panOriginRef.current;
    const canvas = drawingCanvasRef.current;
    if (!origin || !canvas || origin.pointerId !== event.pointerId) {
      return;
    }
    const next = panScrollOffset(origin, event.clientX, event.clientY);
    canvas.scrollLeft = next.scrollLeft;
    canvas.scrollTop = next.scrollTop;
  }

  /** Solta a captura do ponteiro no fim do gesto, qualquer que tenha sido ele. */
  function releaseCanvasPointer(pointerId: number) {
    const canvas = drawingCanvasRef.current;
    if (canvas?.hasPointerCapture(pointerId)) {
      canvas.releasePointerCapture(pointerId);
    }
  }

  function endPan(event: ReactPointerEvent<HTMLDivElement>) {
    const marqueeOrigin = marqueeOriginRef.current;
    if (marqueeOrigin) {
      if (marqueeOrigin.pointerId !== event.pointerId) {
        return;
      }
      marqueeOriginRef.current = null;
      const transform = previewTransformRef.current;
      // Abaixo do limiar o gesto foi um Shift+clique parado: quem decide é o `onClick`
      // da forma, que continua marcando e desmarcando uma a uma.
      if (
        transform &&
        isMarqueeDrag(
          marqueeOrigin.clientX,
          marqueeOrigin.clientY,
          event.clientX,
          event.clientY,
        )
      ) {
        const end = clientToImagePoint(
          event.clientX,
          event.clientY,
          transform.getBoundingClientRect(),
          rotation,
          imageWidthPx,
          imageHeightPx,
        );
        const picked = marqueeSelection(
          normalizedRect(marqueeOrigin.start, end),
          review?.proposals?.proposals ?? [],
          new Set(proposalDecisionById.keys()),
        );
        // O retângulo só soma: desmarcar continua sendo clique na forma.
        setBatchIds((current) => new Set([...current, ...picked]));
        markAddedProposals(picked.filter((id) => !batchIds.has(id)));
      }
      setMarquee(null);
      releaseCanvasPointer(event.pointerId);
      return;
    }
    const origin = panOriginRef.current;
    if (!origin || origin.pointerId !== event.pointerId) {
      return;
    }
    panOriginRef.current = null;
    setPanning(false);
    releaseCanvasPointer(event.pointerId);
    // Clique parado no palco durante a captura vira ponto; arrasto continua sendo pan,
    // pelo mesmo limiar que separa clique de retângulo. Gesto que o estado da captura
    // não espera é ignorado pela própria máquina, sem efeito nenhum aqui.
    if (
      capturing &&
      !isMarqueeDrag(
        origin.pointerX,
        origin.pointerY,
        event.clientX,
        event.clientY,
      )
    ) {
      dispatchImagePoint(event.clientX, event.clientY);
    }
  }

  /** Cancelamento não é conclusão: o retângulo some sem alterar a seleção. */
  function cancelPan(event: ReactPointerEvent<HTMLDivElement>) {
    if (marqueeOriginRef.current?.pointerId === event.pointerId) {
      marqueeOriginRef.current = null;
      setMarquee(null);
      releaseCanvasPointer(event.pointerId);
      return;
    }
    endPan(event);
  }

  useEffect(() => {
    const token = session?.access_token;
    // Mesmo predicado do botão: acompanhar e travar são a mesma pergunta.
    if (!token || !exportArtifact || !exportInFlight(exportArtifact)) {
      return;
    }
    const poll = window.setTimeout(() => {
      void getExport(token, jobId, exportArtifact.export_id)
        .then(setExportArtifact)
        .catch(() =>
          setMessage("Não foi possível consultar o estado da exportação."),
        );
    }, 2_000);
    return () => window.clearTimeout(poll);
  }, [exportArtifact, jobId, session?.access_token]);

  useEffect(() => {
    const availableLines = proposals.filter(
      (proposal) =>
        proposal.kind === "line" && !proposalDecisionById.has(proposal.id),
    );
    setFirstAnchorProposalId(availableLines[0]?.id ?? "");
    setSecondAnchorProposalId(availableLines[1]?.id ?? "");
    setProposalJustification("");
  }, [review]);

  async function submitDecision(action: ReviewDecision["action"]) {
    if (!session?.access_token) {
      setMessage("Sua sessão não está ativa. Entre novamente para decidir.");
      return;
    }
    if (!review || !selectedReading) {
      return;
    }
    if (action !== "reject" && !selectedProposalId) {
      setMessage(
        "Selecione a associação explícita antes de confirmar — ou declare que a leitura é anotação da folha.",
      );
      return;
    }
    let written: ReturnType<typeof parseWrittenValue> = null;
    if (action === "correct" && correctionValue.trim()) {
      written = parseWrittenValue(correctionValue);
      if (!written) {
        setMessage("Informe o valor corrigido como número positivo, ex.: 21,75.");
        return;
      }
      if (!correction.trim()) {
        setMessage(
          "Ao corrigir o valor, transcreva também o texto lido na evidência.",
        );
        return;
      }
    }
    const issue = justificationIssue(decisionJustification);
    if (issue) {
      setMessage(issue);
      return;
    }
    setSubmitting(true);
    setMessage(null);
    try {
      const decision: ReviewDecision = {
        reading_id: selectedReading.id,
        action,
        justification: decisionJustification.trim(),
        association_proposal_id:
          action === "reject" || selectedProposalId === ANNOTATION_OPTION
            ? undefined
            : selectedProposalId,
        annotation:
          action !== "reject" && selectedProposalId === ANNOTATION_OPTION
            ? true
            : undefined,
        raw_text:
          action === "correct" && correction.trim() ? correction : undefined,
        value_si: written?.value_si,
        written_decimals: written?.written_decimals,
        unit: written ? correctionUnit : undefined,
        kind:
          action === "correct" && correctionKind ? correctionKind : undefined,
      };
      const next = await submitReviewDecision(
        session.access_token,
        jobId,
        review.version,
        decision,
      );
      setReview(next);
      setConflict(false);
      setDecisionJustification("");
      const pending = next.packet.readings.find((reading) =>
        ["proposed", "ambiguous"].includes(reading.status),
      );
      setSelectedReadingId(pending?.id ?? next.packet.readings[0]?.id ?? "");
      // A tela pula para a próxima leitura sozinha: sem o aviso, o revisor não sabe
      // se a decisão entrou ou se ele perdeu a seleção.
      setToast("Decisão registrada.");
    } catch (error) {
      const text =
        error instanceof Error
          ? error.message
          : "Não foi possível registrar a decisão.";
      setConflict(text.includes("REVISION_CONFLICT"));
      setMessage(text);
    } finally {
      setSubmitting(false);
    }
  }

  /** Abre o mesmo formulário da decisão com os valores vigentes já preenchidos. */
  function startRectification(reading: ReviewReading) {
    const prefill = rectificationPrefill(
      reading,
      review?.selected_associations[reading.id],
      ANNOTATION_OPTION,
    );
    setSelectedProposalId(prefill.associationValue);
    setCorrection(prefill.rawText);
    setCorrectionValue(prefill.value);
    setCorrectionUnit(prefill.unit);
    setCorrectionKind(prefill.kind);
    setDecisionJustification(prefill.justification);
    setMessage(null);
    setRectifyingReadingId(reading.id);
  }

  function cancelRectification() {
    setRectifyingReadingId(null);
    setDecisionJustification("");
    setMessage(null);
  }

  async function submitRectification(action: "confirm" | "reject") {
    if (!session?.access_token) {
      setMessage("Sua sessão não está ativa. Entre novamente para corrigir.");
      return;
    }
    if (!review || !selectedReading || !rectificationTarget(selectedReading)) {
      return;
    }
    if (action !== "reject" && !selectedProposalId) {
      setMessage(
        "Selecione a associação explícita antes de registrar a correção — ou declare que a leitura é anotação da folha.",
      );
      return;
    }
    let written: ReturnType<typeof parseWrittenValue> = null;
    if (action !== "reject" && correctionValue.trim()) {
      written = parseWrittenValue(correctionValue);
      if (!written) {
        setMessage("Informe o valor corrigido como número positivo, ex.: 21,75.");
        return;
      }
    }
    const issue = justificationIssue(decisionJustification);
    if (issue) {
      setMessage(issue);
      return;
    }
    const command = buildRectification(selectedReading, {
      action,
      justification: decisionJustification,
      associationValue: selectedProposalId,
      annotationOption: ANNOTATION_OPTION,
      rawText: correction,
      written,
      unit: correctionUnit,
      kind: correctionKind,
    });
    if (!command) {
      return;
    }
    setSubmitting(true);
    setMessage(null);
    try {
      const next = await submitReviewRectification(
        session.access_token,
        jobId,
        review.version,
        command,
      );
      setReview(next);
      setConflict(false);
      setRectifyingReadingId(null);
      setDecisionJustification("");
      setToast("Correção registrada. A decisão anterior segue no histórico.");
    } catch (error) {
      const text =
        error instanceof Error
          ? error.message
          : "Não foi possível registrar a correção.";
      setConflict(text.includes("REVISION_CONFLICT"));
      setMessage(text);
    } finally {
      setSubmitting(false);
    }
  }

  async function bindDimension(proposalId: string) {
    const entityId = proposalDecisionById.get(proposalId)?.entity_id;
    if (!session?.access_token || !review?.scene || !bindingReadingId || !entityId) {
      return;
    }
    const issue = justificationIssue(bindingJustification);
    if (issue) {
      setMessage(
        bindingJustification.trim().length < JUSTIFICATION_MIN_LENGTH
          ? "Escreva por que esta linha corresponde à cota (mínimo de 3 caracteres)."
          : issue,
      );
      return;
    }
    setSubmitting(true);
    setMessage(null);
    try {
      const next = await annotateDimension(
        session.access_token,
        jobId,
        review.version,
        review.scene.version,
        bindingReadingId,
        entityId,
        bindingJustification.trim(),
      );
      setReview(next);
      setBindingReadingId(null);
      setBindingJustification("");
      setConflict(false);
      setToast("Cota amarrada; a linha assumiu a medida escrita.");
    } catch (error) {
      const text =
        error instanceof Error
          ? error.message
          : "Não foi possível amarrar a cota.";
      setConflict(text.includes("REVISION_CONFLICT"));
      setMessage(text);
    } finally {
      setSubmitting(false);
    }
  }

  /**
   * Forma que entra na seleção sem nenhuma cota confirmada amarrada nasce declarada
   * "como desenhado": sem medida escrita não há o que regularizar, e era essa a
   * marcação que o revisor refazia à mão forma a forma. Só no momento de entrar —
   * quem já estava na montagem não é tocado, porque a declaração pode ser dele.
   */
  function markAddedProposals(addedProposalIds: string[]) {
    if (addedProposalIds.length === 0) {
      return;
    }
    const context: ProposalFlagContext = {
      readings: review?.packet.readings ?? [],
      selectedAssociations: review?.selected_associations ?? {},
      associations: traceDeclarations.associations,
    };
    setTraceDeclarations((current) =>
      withDefaultProposalFlags(current, addedProposalIds, context),
    );
  }

  function toggleBatch(proposalId: string) {
    const adding = !batchIds.has(proposalId);
    setBatchIds((current) => {
      const next = new Set(current);
      if (!next.delete(proposalId)) {
        next.add(proposalId);
      }
      return next;
    });
    if (adding) {
      markAddedProposals([proposalId]);
    }
  }

  async function submitBatch(action: "accept" | "reject") {
    if (!session?.access_token) {
      setMessage("Sua sessão não está ativa. Entre novamente para decidir.");
      return;
    }
    if (!review?.scene || batchIds.size === 0) {
      return;
    }
    const batchIssue = justificationIssue(batchJustification);
    if (batchIssue) {
      setMessage(batchIssue);
      return;
    }
    if (action === "accept" && !review.calibration) {
      setMessage(
        "Confirme a calibração pixel→metro antes de aceitar geometria aproximada.",
      );
      return;
    }
    setSubmitting(true);
    setMessage(null);
    try {
      const next = await submitProposalBatch(
        session.access_token,
        jobId,
        review.version,
        review.scene.version,
        [...batchIds],
        action,
        batchJustification.trim(),
        action === "accept" ? review.calibration?.calibration_id : undefined,
      );
      const decided = batchIds.size;
      setReview(next);
      setBatchIds(new Set());
      setBatchJustification("");
      setConflict(false);
      setToast(
        action === "accept"
          ? `${decided} propostas traçadas como geometria aproximada.`
          : `${decided} propostas rejeitadas.`,
      );
    } catch (error) {
      const text =
        error instanceof Error
          ? error.message
          : "Não foi possível registrar o lote.";
      setConflict(text.includes("REVISION_CONFLICT"));
      setMessage(text);
    } finally {
      setSubmitting(false);
    }
  }

  function toggleTraceFlag(
    field: "hatch" | "unlabelled" | "freeform",
    proposalId: string,
  ) {
    setTraceDeclarations((current) => {
      const next = new Set(current[field]);
      if (!next.delete(proposalId)) {
        next.add(proposalId);
      }
      return { ...current, [field]: next };
    });
  }

  /**
   * Desfazer a amarração devolve a leitura ao estado anterior — herdada ou anotação da
   * folha. O texto declarado da cota sai junto quando não sobra vão nenhum: texto sem
   * trecho medido é exatamente o que o worker recusa (`DIMENSION_TEXT_WITHOUT_SPAN`).
   */
  function removeSpanTarget(readingId: string) {
    const inherited = Boolean(review?.selected_associations[readingId]);
    setTraceDeclarations((current) => {
      const associations = { ...current.associations };
      delete associations[readingId];
      const dimensionTexts = { ...current.dimensionTexts };
      if (!inherited) {
        delete dimensionTexts[readingId];
      }
      return { ...current, associations, dimensionTexts };
    });
  }

  function removeNoteTarget(readingId: string) {
    setTraceDeclarations((current) => {
      const noteTargets = { ...current.noteTargets };
      delete noteTargets[readingId];
      return { ...current, noteTargets };
    });
  }

  function declareNoteTarget(readingId: string, target: string) {
    setTraceDeclarations((current) => ({
      ...current,
      noteTargets: { ...current.noteTargets, [readingId]: target },
    }));
  }

  /** Campo vazio remove a declaração em vez de gravar texto em branco. */
  function setDimensionText(readingId: string, text: string) {
    setTraceDeclarations((current) => {
      const dimensionTexts = { ...current.dimensionTexts };
      if (text.trim()) {
        dimensionTexts[readingId] = text;
      } else {
        delete dimensionTexts[readingId];
      }
      return { ...current, dimensionTexts };
    });
  }

  function updateDerivedDimension(
    index: number,
    change: Partial<DerivedDimensionDraft>,
  ) {
    setTraceDeclarations((current) => ({
      ...current,
      derivedDimensions: current.derivedDimensions.map((dimension, position) =>
        position === index ? { ...dimension, ...change } : dimension,
      ),
    }));
  }

  function removeDerivedDimension(index: number) {
    setTraceDeclarations((current) => ({
      ...current,
      derivedDimensions: current.derivedDimensions.filter(
        (_, position) => position !== index,
      ),
    }));
  }

  /** Descrição do vão declarado, pelo nome de obra das formas — nunca pelo id. */
  function spanTargetSummary(target: SpanTargetDraft): string {
    switch (target.kind) {
      case "single":
        return `vão declarado na forma ${proposalName(target.proposalId)}`;
      case "pair":
        return `vão entre ${proposalName(target.proposalIds[0])} e ${proposalName(
          target.proposalIds[1],
        )}`;
      case "declared":
        return `vão com ${target.spansPx.length} ${
          target.spansPx.length === 1 ? "trecho" : "trechos"
        } no próprio elemento ${proposalName(target.proposalId)}`;
    }
  }

  function noteTargetSummary(target: string): string {
    const choice = parseNoteTarget(target);
    if (choice.kind === "stamp") {
      return "nota geral, no carimbo da prancha";
    }
    if (choice.kind === "legend") {
      return `nota na legenda de ${proposalName(choice.proposalId)}`;
    }
    return `nota presa a ${proposalName(choice.proposalId)} · orientação ${
      NOTE_ORIENTATION_LABELS[choice.orientation]
    }`;
  }

  function groupSelectionAsDetail() {
    const code = detailId.trim().toUpperCase();
    if (!DETAIL_ID_PATTERN.test(code)) {
      setMessage(
        "O código do detalhe começa por letra maiúscula e tem até oito caracteres maiúsculos, como A ou B2.",
      );
      return;
    }
    if (!detailTitle.trim()) {
      setMessage("Escreva o título do grupo de detalhe.");
      return;
    }
    if (ungroupedSelection.length === 0) {
      setMessage("Selecione as formas do detalhe antes de agrupá-las.");
      return;
    }
    setTraceDeclarations((current) => ({
      ...current,
      detailGroups: [
        ...current.detailGroups,
        {
          detailId: code,
          title: detailTitle.trim(),
          proposalIds: ungroupedSelection,
          mode: detailMode,
        },
      ],
    }));
    setDetailId("");
    setDetailTitle("");
    setMessage(null);
  }

  function removeDetailGroup(code: string) {
    setTraceDeclarations((current) => ({
      ...current,
      detailGroups: current.detailGroups.filter(
        (group) => group.detailId !== code,
      ),
    }));
  }

  function keepSelectionApart() {
    const pair = traceDraft.proposalIds;
    if (pair.length !== 2) {
      return;
    }
    setTraceDeclarations((current) => ({
      ...current,
      keepApartPairs: [
        ...current.keepApartPairs,
        // Comportamento histórico: separa nos dois sentidos até o revisor escolher
        // um eixo na lista abaixo.
        { first: pair[0], second: pair[1], axis: null },
      ],
    }));
  }

  function removeKeepApartPair(index: number) {
    setTraceDeclarations((current) => ({
      ...current,
      keepApartPairs: current.keepApartPairs.filter(
        (_, position) => position !== index,
      ),
    }));
  }

  function setKeepApartAxis(index: number, axis: "x" | "y" | null) {
    setTraceDeclarations((current) => ({
      ...current,
      keepApartPairs: current.keepApartPairs.map((pair, position) =>
        position === index ? { ...pair, axis } : pair,
      ),
    }));
  }

  async function submitTraceSolve() {
    if (!session?.access_token) {
      setMessage("Sua sessão não está ativa. Entre novamente para aceitar.");
      return;
    }
    if (!review || traceIssues.length > 0) {
      return;
    }
    if (traceSolveInFlight(traceSolve)) {
      // Defesa contra Enter/duplo-evento: o botão já desabilita, mas o guard aqui
      // cobre o disparo direto de submitTraceSolve enquanto o aceite anterior segue
      // em voo.
      return;
    }
    setSubmitting(true);
    setMessage(null);
    try {
      const created = await createTraceSolve(
        session.access_token,
        jobId,
        buildTraceSolveRequest(traceDraft, review),
      );
      handledTraceSolveRef.current = null;
      setTraceSolve(created);
      setConflict(false);
    } catch (error) {
      const text =
        error instanceof Error
          ? error.message
          : "Não foi possível enviar o aceite do traçado.";
      setConflict(text.includes("REVISION_CONFLICT"));
      setMessage(text);
    } finally {
      setSubmitting(false);
    }
  }

  // O traçado roda no worker: a tela acompanha o registro até ele fechar, no mesmo
  // ritmo do export.
  useEffect(() => {
    const token = session?.access_token;
    const pending =
      traceSolve?.status === "QUEUED" || traceSolve?.status === "RUNNING";
    if (!token || !traceSolve || !pending) {
      return;
    }
    const poll = window.setTimeout(() => {
      void getTraceSolve(token, jobId, traceSolve.trace_solve_id)
        .then(setTraceSolve)
        .catch(() =>
          setMessage("Não foi possível consultar o estado do traçado."),
        );
    }, 2_000);
    return () => window.clearTimeout(poll);
  }, [traceSolve, jobId, session?.access_token]);

  useEffect(() => {
    const token = session?.access_token;
    if (!token || traceSolve?.status !== "COMPLETED") {
      return;
    }
    if (handledTraceSolveRef.current === traceSolve.trace_solve_id) {
      return;
    }
    handledTraceSolveRef.current = traceSolve.trace_solve_id;
    if (traceSolve.solve_status === "solved_unapproved") {
      // A cena métrica é outra: recarregar é o que traz as versões novas de revisão e
      // de cena. A montagem FICA: o traçado é iterativo (o revisor ajusta um vão e
      // reenvia), e apagar as amarrações a cada rodada custou horas de reconstrução
      // no primeiro caso real (Guaxindiba v2, 2026-08-13).
      void loadReview(token, jobId).then(() => {
        setToast(
          "Traçado resolvido; a cena métrica foi atualizada e sua montagem continua aqui para a próxima rodada.",
        );
      });
      return;
    }
    if (traceSolve.solve_status === "conflict") {
      // Revisão que andou não é erro de servidor: a montagem é preservada para o
      // revisor reenviar o mesmo lote sobre as versões novas.
      void loadReview(token, jobId).then(() =>
        setMessage(
          "Outra decisão entrou antes deste aceite. A revisão foi recarregada e sua seleção continua montada: envie o traçado de novo.",
        ),
      );
    }
  }, [traceSolve, jobId, session?.access_token]);

  /**
   * Recorte da leitura citada por um rascunho, no mesmo mecanismo da seção de decisão:
   * o cartão ancora no que está escrito na folha, não no identificador da cota.
   */
  function chatDraftEvidence(
    readingId: string | null,
  ): { reading: ReviewReading; crop: EvidenceCropStyle } | null {
    if (!readingId || !hasImageSize) {
      return null;
    }
    const anchored = review?.packet.readings.find(
      (reading) => reading.id === readingId,
    );
    if (anchored?.evidence?.coordinate_space !== "source_image_pixels") {
      return null;
    }
    return {
      reading: anchored,
      crop: evidenceCropStyle(
        anchored.evidence.bbox,
        imageWidthPx,
        imageHeightPx,
        chatEvidenceRotation,
      ),
    };
  }

  /** Erro do painel fica no painel; sessão expirada continua sendo assunto global. */
  function reportChatError(error: unknown, fallback: string) {
    const text = error instanceof Error ? error.message : fallback;
    if (text.startsWith("INVALID_TOKEN:")) {
      showApiError(error, fallback);
      return;
    }
    setChatMessage(text);
  }

  /**
   * Pergunta publicada; a resposta vem por polling, como export e traçado. A conversa é
   * criada sob demanda e reusa a que já está aberta no job — a tela usa uma só.
   */
  async function sendChatQuestion() {
    const token = session?.access_token;
    if (!token) {
      setChatMessage("Sua sessão não está ativa. Entre novamente para perguntar.");
      return;
    }
    // Guard de duplo-envio: o botão já desabilita, e o servidor recusa a segunda
    // pergunta em voo; aqui o clique repetido simplesmente não vira chamada.
    if (!review || chatSending || chatBusy) {
      return;
    }
    const issue = chatQuestionIssue(chatQuestion);
    if (issue) {
      setChatMessage(issue);
      return;
    }
    setChatSending(true);
    setChatMessage(null);
    try {
      let current = chatSession;
      if (!current || current.status !== "OPEN") {
        const existing = pickOpenChatSession(
          await listChatSessions(token, jobId),
        );
        current = existing
          ? await getChatSession(token, jobId, existing.chat_session_id)
          : await createChatSession(token, jobId);
      }
      const turn = await createChatTurn(token, jobId, current.chat_session_id, {
        question: chatQuestion.trim(),
        anchors: chatAnchors,
      });
      setChatSession({
        ...current,
        // Replay idempotente devolve o mesmo turno: ele substitui, não duplica.
        turns: [
          ...current.turns.filter(
            (item) => item.chat_turn_id !== turn.chat_turn_id,
          ),
          turn,
        ],
      });
      setChatQuestion("");
      setChatDroppedAnchors(new Set());
    } catch (error) {
      reportChatError(error, "Não foi possível enviar a pergunta.");
    } finally {
      setChatSending(false);
    }
  }

  /**
   * "Usar este rascunho" PRÉ-PREENCHE e nada mais: decisão de leitura abre o formulário
   * com associação e justificativa sugeridas — editáveis —, e ato de traçado entra no
   * aceite montado. O envio continua sendo o comando humano de sempre.
   */
  function applyChatDraft(draft: ChatActDraft) {
    if (draft.act === "reading_decision") {
      const decision = draftToReviewDecision(
        draft,
        review?.packet.readings ?? [],
      );
      if (!decision) {
        setChatMessage(
          "Este rascunho não pode ser usado: a leitura citada não está pendente nesta revisão.",
        );
        return;
      }
      setOpenStep("decisions");
      setRectifyingReadingId(null);
      setSelectedReadingId(decision.reading_id);
      setChatPrefill({
        readingId: decision.reading_id,
        associationValue: decision.annotation
          ? ANNOTATION_OPTION
          : (decision.association_proposal_id ?? ""),
        justification: decision.justification,
      });
      setChatMessage(null);
      setToast(
        "Rascunho no formulário de decisão — confira a evidência, ajuste a justificativa e assine.",
      );
      return;
    }
    const applied = applyDraftToTraceDraft(draft, traceDraft);
    if (!applied.applied) {
      setChatMessage(applied.message);
      return;
    }
    setTraceDeclarations((current) => ({
      ...applied.draft,
      // A seleção do lote é ato do revisor no desenho: o rascunho não marca forma.
      proposalIds: current.proposalIds,
    }));
    if (traceStepAvailable) {
      setOpenStep("trace");
    }
    setChatMessage(null);
    setToast("Sugestão aplicada ao aceite — revise antes de enviar.");
  }

  // A conversa do job é buscada quando o painel abre, e não antes: sem abrir o painel
  // nenhuma chamada de conversa sai da tela.
  useEffect(() => {
    const token = session?.access_token;
    if (
      !chatOpen ||
      !token ||
      !jobId ||
      chatSession ||
      chatLoadedJobRef.current === jobId
    ) {
      return;
    }
    chatLoadedJobRef.current = jobId;
    void (async () => {
      try {
        const existing = pickOpenChatSession(
          await listChatSessions(token, jobId),
        );
        if (existing) {
          setChatSession(
            await getChatSession(token, jobId, existing.chat_session_id),
          );
        }
      } catch (error) {
        reportChatError(error, "Não foi possível carregar a conversa.");
      }
    })();
  }, [chatOpen, jobId, chatSession, session?.access_token]);

  // Mesmo ritmo do traçado: o turno fecha no worker e a tela acompanha o registro.
  useEffect(() => {
    const token = session?.access_token;
    if (!token || !chatSession || !chatBusy) {
      return;
    }
    const poll = window.setTimeout(() => {
      void getChatSession(token, jobId, chatSession.chat_session_id)
        .then(setChatSession)
        .catch(() =>
          setChatMessage(
            "Não foi possível consultar a conversa; ela continua no servidor.",
          ),
        );
    }, 2_000);
    return () => window.clearTimeout(poll);
  }, [chatSession, chatBusy, jobId, session?.access_token]);

  // Trocar de projeto não carrega conversa nem pergunta do projeto anterior.
  useEffect(() => {
    setChatSession(null);
    setChatQuestion("");
    setChatMessage(null);
    setChatDroppedAnchors(new Set());
    setChatPrefill(null);
    chatLoadedJobRef.current = null;
  }, [jobId]);

  // Trocar de projeto não carrega aceite nem resultado do projeto anterior.
  useEffect(() => {
    setTraceSolve(null);
    setTraceDeclarations(emptyTraceDraft());
    handledTraceSolveRef.current = null;
    captureRef.current = IDLE_CAPTURE;
    setCapture(IDLE_CAPTURE);
  }, [jobId]);

  /**
   * Rascunho do traçado de volta ao abrir o job: uma vez por projeto e só depois que a
   * revisão chega, porque é ela que diz quais formas continuam sem decisão. Amarração
   * que aponta forma decidida volta como está — a pré-validação acusa em língua de
   * obra, o que é melhor do que sumir com a declaração em silêncio.
   */
  useEffect(() => {
    // A revisão em tela ainda pode ser a do projeto anterior enquanto a nova carrega;
    // restaurar contra ela filtraria o rascunho por formas de outro desenho.
    if (!jobId || review?.job_id !== jobId || restoredTraceJobRef.current === jobId) {
      return;
    }
    restoredTraceJobRef.current = jobId;
    const stored = readStoredTraceDraft(jobId);
    if (!stored) {
      return;
    }
    const restored = parseTraceDraft(
      stored,
      new Set(undecidedProposals.map((proposal) => proposal.id)),
    );
    if (!restored) {
      clearStoredTraceDraft(jobId);
      return;
    }
    setTraceDeclarations(restored.declarations);
    setBatchIds(new Set(restored.batchIds));
  }, [jobId, review]);

  useEffect(() => {
    if (!jobId || restoredTraceJobRef.current !== jobId) {
      return;
    }
    writeStoredTraceDraft(jobId, serializeTraceDraft(traceDraft, batchIds));
  }, [jobId, traceDraft, batchIds]);

  // Esc conclui a captura: no vão declarado ele fecha o que já está marcado; nos demais
  // gestos ele desiste sem declarar nada.
  useEffect(() => {
    if (!capturing) {
      return;
    }
    function handleKeyDown(event: KeyboardEvent) {
      if (event.key !== "Escape") {
        return;
      }
      event.preventDefault();
      dispatchCapture({ type: "cancel" });
    }
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [capturing, dispatchCapture]);

  // A etapa de traçado pode sair de cena (jornada anda, revisor reabre outra etapa):
  // captura órfã não sobrevive à saída, e o que já fechou é preservado.
  useEffect(() => {
    if (visibleStep === "trace") {
      return;
    }
    dispatchCapture({ type: "cancel" });
  }, [visibleStep, dispatchCapture]);

  async function submitCalibration() {
    if (
      !session?.access_token ||
      !review?.scene ||
      !firstAnchorProposalId ||
      !secondAnchorProposalId
    ) {
      setMessage("Selecione duas linhas do desenho para calibrar.");
      return;
    }
    if (firstAnchorProposalId === secondAnchorProposalId) {
      setMessage("As duas linhas de calibração precisam ser diferentes.");
      return;
    }
    setSubmitting(true);
    setMessage(null);
    try {
      const next = await createProposalCalibration(
        session.access_token,
        jobId,
        review.version,
        review.scene.version,
        // Sem entity_id: o servidor descobre a que aresta métrica cada linha
        // corresponde e recusa se o ajuste não reproduzir as âncoras.
        [
          { proposal_id: firstAnchorProposalId },
          { proposal_id: secondAnchorProposalId },
        ],
      );
      setReview(next);
      setConflict(false);
      setToast(
        next.calibration
          ? `Calibração confirmada com erro de ${next.calibration.rmse_m.toFixed(2)} m.`
          : "Calibração confirmada.",
      );
    } catch (error) {
      const text =
        error instanceof Error
          ? error.message
          : "Não foi possível registrar a calibração.";
      setConflict(text.includes("REVISION_CONFLICT"));
      setMessage(text);
    } finally {
      setSubmitting(false);
    }
  }

  // Um critério cai em exatamente um dos dois conjuntos: declarar um desfecho retira o
  // outro, e nenhum dos dois nasce marcado.
  function declareCriterion(code: string, outcome: "covered" | "acknowledged") {
    const withoutCovered = approvalForm.coveredCriteria.filter(
      (item) => item !== code,
    );
    const withoutAcknowledged = approvalForm.acknowledgedCriteria.filter(
      (item) => item !== code,
    );
    setApprovalForm({
      ...approvalForm,
      coveredCriteria:
        outcome === "covered" ? [...withoutCovered, code] : withoutCovered,
      acknowledgedCriteria:
        outcome === "acknowledged"
          ? [...withoutAcknowledged, code]
          : withoutAcknowledged,
    });
  }

  async function submitApproval() {
    if (!session?.access_token) {
      setMessage("Sua sessão não está ativa. Entre novamente para aprovar.");
      return;
    }
    if (!review?.scene || !readiness.canApprove) {
      return;
    }
    setSubmitting(true);
    setMessage(null);
    try {
      const approved = await approveScene(session.access_token, jobId, {
        revision_id: review.scene.id,
        accepted_approximations: deriveAcceptedApproximations(review).map(
          (item) => item.entityId,
        ),
        covered_criteria: approvalForm.coveredCriteria,
        acknowledged_criteria: approvalForm.acknowledgedCriteria,
        source_evidence_checked: true,
        geometry_checked: true,
        limitations_acknowledged: true,
        statement: approvalForm.statement.trim(),
      });
      setApprovedRevisionId(approved.id);
      setApprovalForm(emptyApprovalForm);
      window.sessionStorage.removeItem(`croquito:approval:${jobId}`);
      setReview(await getReview(session.access_token, jobId));
      setConflict(false);
      setToast(`Cena v${approved.version} aprovada tecnicamente.`);
    } catch (error) {
      const text =
        error instanceof Error
          ? error.message
          : "Não foi possível registrar a aprovação técnica.";
      setConflict(text.includes("REVISION_CONFLICT"));
      setMessage(text);
    } finally {
      setSubmitting(false);
    }
  }

  async function startExport() {
    if (!session?.access_token || !approvedRevisionId) {
      return;
    }
    setSubmitting(true);
    setMessage(null);
    try {
      setExportArtifact(
        await requestExport(session.access_token, jobId, approvedRevisionId),
      );
    } catch (error) {
      showApiError(error, "Não foi possível solicitar a exportação.");
    } finally {
      setSubmitting(false);
    }
  }

  async function submitGeometryProposal(action: "accept" | "reject") {
    if (!session?.access_token || !review?.scene || !selectedGeometryProposal) {
      setMessage("Selecione a proposta antes de decidir.");
      return;
    }
    const issue = justificationIssue(proposalJustification);
    if (issue) {
      setMessage(issue);
      return;
    }
    if (action === "accept" && !review.calibration) {
      setMessage(
        "Crie uma calibração confirmada antes de aceitar uma proposta.",
      );
      return;
    }
    setSubmitting(true);
    setMessage(null);
    try {
      const next = await submitProposalDecision(
        session.access_token,
        jobId,
        review.version,
        review.scene.version,
        selectedGeometryProposal.id,
        action,
        proposalJustification.trim(),
        action === "accept" ? review.calibration?.calibration_id : undefined,
      );
      setReview(next);
      const pending = next.proposals?.proposals.find(
        (proposal) =>
          !next.proposal_decisions.some(
            (decision) => decision.proposal_id === proposal.id,
          ),
      );
      setSelectedGeometryProposalId(pending?.id ?? "");
      setProposalJustification("");
      setConflict(false);
    } catch (error) {
      const text =
        error instanceof Error
          ? error.message
          : "Não foi possível registrar a decisão da proposta.";
      setConflict(text.includes("REVISION_CONFLICT"));
      setMessage(text);
    } finally {
      setSubmitting(false);
    }
  }

  function openProject(project: ProjectSummary) {
    if (!session?.access_token || !project.latest_job) {
      setMessage("Este projeto ainda não tem processamento para revisar.");
      return;
    }
    void openJob(session.access_token, project.latest_job.job_id);
  }

  async function submitUpload(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!session?.access_token || !uploadFile || !projectName) {
      return;
    }
    setSubmitting(true);
    setMessage(null);
    try {
      const job = await createProjectUpload(
        session.access_token,
        uploadFile,
        projectName,
        defaultUnit,
      );
      setJobId(job.job_id);
      setSelectedJob(job);
      setReview(null);
      window.history.replaceState(
        null,
        "",
        `?job=${encodeURIComponent(job.job_id)}`,
      );
      setProjects(await listProjects(session.access_token));
      setUploadFile(null);
      setProjectName("");
      setMessage(
        "Projeto criado. A revisão será aberta automaticamente quando estiver disponível.",
      );
    } catch (error) {
      showApiError(error, "Não foi possível criar o job.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="app-shell">
      <header className="topbar">
        <a className="brand" href="/" aria-label="Croquito - início">
          <img className="brand-logo" src={logoDark} alt="Croquito" />
          <small>Revisão humana autenticada</small>
        </a>
        <div className="topbar-actions">
          <span className="schema-pill">
            Cena {sceneSchema.$id?.split("/").at(-1)}
          </span>
          {session ? (
            <span className="identity-pill">
              Sessão:{" "}
              {session.profile.preferred_username ?? session.profile.sub}
            </span>
          ) : null}
          {isOidcConfigured() && !session ? (
            <button
              className="button button-quiet"
              type="button"
              onClick={() => void signIn()}
            >
              Entrar
            </button>
          ) : null}
          {session ? (
            <button
              className="button button-quiet"
              type="button"
              onClick={() => void signOut()}
            >
              Sair
            </button>
          ) : null}
        </div>
      </header>

      <section className="context-bar">
        <div>
          <span className="eyebrow">REVISÃO PROTEGIDA</span>
          <h1>
            {review
              ? `Revisão ${review.version}`
              : session
                ? "Projetos"
                : "Acesse uma revisão autenticada"}
          </h1>
        </div>
        {review ? (
          <span className={review.scene?.approved ? "ready" : "blocked"}>
            {review.scene?.approved ? "Aprovada" : "DXF bloqueado"}
          </span>
        ) : null}
      </section>

      {!isOidcConfigured() ? (
        <p className="session-error">
          OIDC não está configurado neste ambiente; nenhuma evidência ou decisão
          é exibida.
        </p>
      ) : null}
      {message ? (
        <p className="app-alert" role="alert">
          <span>{message}</span>
          <button
            type="button"
            className="app-alert-close"
            onClick={() => setMessage(null)}
            aria-label="Fechar aviso"
          >
            ×
          </button>
        </p>
      ) : null}
      {toast ? (
        <p className="app-toast" role="status">
          {toast}
        </p>
      ) : null}
      {conflict && session?.access_token ? (
        <button
          className="reload-review"
          type="button"
          onClick={() => void loadReview(session.access_token)}
        >
          Recarregar revisão atual
        </button>
      ) : null}

      {session ? (
        <section
          className="authenticated-workspace"
          aria-labelledby="open-review-title"
        >
          <div>
            <span className="eyebrow">TENANT ATUAL</span>
            <h2 id="open-review-title">Projetos e revisões</h2>
            <p>
              Selecione um projeto para acompanhar o processamento ou abrir a
              revisão disponível.
            </p>
          </div>
          <form
            className="upload-form"
            onSubmit={submitUpload}
            aria-label="Criar projeto e enviar PDF"
          >
            <label>
              Projeto
              <input
                value={projectName}
                onChange={(event) => setProjectName(event.target.value)}
                maxLength={160}
                required
              />
            </label>
            <label>
              PDF
              <input
                type="file"
                accept="application/pdf,.pdf"
                onChange={(event) =>
                  setUploadFile(event.target.files?.[0] ?? null)
                }
                required
              />
            </label>
            <label>
              Unidade padrão
              <select
                value={defaultUnit}
                onChange={(event) =>
                  setDefaultUnit(event.target.value as "m" | "mm")
                }
              >
                <option value="m">metros</option>
                <option value="mm">milímetros</option>
              </select>
            </label>
            <button
              className="button button-primary"
              type="submit"
              disabled={submitting || !uploadFile}
            >
              {submitting ? "Enviando…" : "Enviar PDF e criar job"}
            </button>
          </form>
          {selectedJob && !review ? (
            <p className="job-status" aria-live="polite">
              <strong>{jobStatusLabel(selectedJob)}</strong>
              <span>{loading ? "Atualizando…" : "Acompanhamento ativo"}</span>
            </p>
          ) : null}
          {projects.length > 0 ? (
            <ul className="project-list" aria-label="Projetos do tenant atual">
              {projects.map((project) => (
                <li key={project.project_id}>
                  <div>
                    <strong>{project.name}</strong>
                    <span>
                      {project.latest_job
                        ? jobStatusLabel(project.latest_job)
                        : "Sem processamento"}
                    </span>
                  </div>
                  {project.latest_job ? (
                    <button
                      className="button button-quiet project-action"
                      type="button"
                      disabled={loading}
                      onClick={() => openProject(project)}
                    >
                      {REVIEWABLE_JOB_STATUSES.has(project.latest_job.status)
                        ? "Abrir revisão"
                        : "Acompanhar projeto"}
                    </button>
                  ) : null}
                </li>
              ))}
            </ul>
          ) : null}
        </section>
      ) : null}

      {review ? (
        <section className="workspace" aria-label="Área de revisão">
          <aside className="panel journey-panel" aria-label="Etapas da revisão">
            {/* O trilho espelha a máquina de estados do servidor: ele mostra uma etapa
                por vez e nunca substitui os guards da API. */}
            <nav className="journey" aria-label="Jornada da revisão">
              <ol className="journey-steps" aria-live="polite">
                {journey.steps.map((step, index) => {
                  const open = step.id === visibleStep;
                  const blocked = step.status === "blocked";
                  return (
                    <li
                      key={step.id}
                      className={`journey-step ${step.status}${
                        step.id === journey.activeStep ? " active" : ""
                      }${open ? " open" : ""}`}
                    >
                      <button
                        type="button"
                        className="journey-step-button"
                        disabled={blocked}
                        aria-current={
                          step.id === journey.activeStep ? "step" : undefined
                        }
                        aria-expanded={open}
                        onClick={() => setOpenStep(step.id)}
                      >
                        {/* Marca, estado escrito e motivo: cor nunca é o único
                            indicador do que a etapa espera. */}
                        <span className="journey-mark" aria-hidden="true">
                          {step.status === "done" ? "✓" : blocked ? "○" : "●"}
                        </span>
                        <span className="journey-step-text">
                          <strong>
                            {index + 1}. {step.title}
                          </strong>
                          <small>{step.blockedReason ?? step.summary}</small>
                        </span>
                        <small className="journey-step-status">
                          {journeyStepStatusLabel(step.status)}
                        </small>
                      </button>
                    </li>
                  );
                })}
              </ol>
            </nav>
            {visibleStep === "decisions" ? (
              <section
                className="journey-section"
                aria-label="Etapa de decisões das leituras"
              >
                <div className="panel-heading">
                  <div>
                    <span className="eyebrow">EVIDÊNCIAS</span>
                    <h2 id="review-title">Leituras</h2>
                  </div>
                  <span className="counter">{review.packet.readings.length}</span>
                </div>
                <div className="review-list">
                  {review.packet.readings.map((reading) => (
                    <button
                      key={reading.id}
                      type="button"
                      aria-pressed={reading.id === selectedReadingId}
                      className={
                        reading.id === selectedReadingId
                          ? "review-row selected"
                          : "review-row"
                      }
                      onClick={() => setSelectedReadingId(reading.id)}
                    >
                      <span
                        className={`status-dot ${reading.status}`}
                        aria-hidden="true"
                      />
                      <span>{readingLabel(reading)}</span>
                      <small>{readingStatusLabel(reading.status)}</small>
                    </button>
                  ))}
                </div>
                {review.packet.safety_notes?.includes(
                  "REGION_CLASSIFICATION_REQUIRED",
                ) ? (
                  <section
                    className="issue-panel"
                    aria-label="Classificação de região necessária"
                  >
                    <strong>Classificação de página necessária</strong>
                    <p>
                      Nenhuma região foi enviada para extração até uma planta
                      principal ser definida.
                    </p>
                    <ul>
                      {review.packet.region_candidates?.map((region) => (
                        <li key={region.id} title={region.kind}>
                          {region.label} · {regionKindLabel(region.kind)}
                        </li>
                      ))}
                    </ul>
                  </section>
                ) : null}
                {selectedReading &&
                selectedReading.decision &&
                showsDecisionRecord(selectedReading, rectifyingReadingId) ? (
                  <section
                    className="decision-controls"
                    aria-label="Decisão registrada da leitura selecionada"
                  >
                    <div className="decision-title">
                      <strong title={selectedReading.id}>
                        {readingLabel(selectedReading)}
                      </strong>
                      <CopyIdButton
                        key={selectedReading.id}
                        value={selectedReading.id}
                        label={readingLabel(selectedReading)}
                      />
                    </div>
                    <p className="reading-current">
                      {selectedReading.status === "rejected"
                        ? "Rejeitada por "
                        : "Decidida por "}
                      <strong>{selectedReading.decision.reviewer_id}</strong> em{" "}
                      {decisionMoment(selectedReading.decision.decided_at)}
                      {selectedReading.decision.rectifies_decision_id
                        ? " (esta já é uma correção de uma decisão anterior)"
                        : ""}
                      .
                    </p>
                    {selectedReading.decision.note ? (
                      <p className="reading-current">
                        Justificativa registrada:{" "}
                        <em>{selectedReading.decision.note}</em>
                      </p>
                    ) : null}
                    <button
                      type="button"
                      disabled={submitting}
                      onClick={() => startRectification(selectedReading)}
                    >
                      Corrigir decisão registrada
                    </button>
                  </section>
                ) : null}
                {selectedReading &&
                showsDecisionForm(selectedReading, rectifyingReadingId) ? (
                  <section
                    className="decision-controls"
                    aria-label="Decisão da leitura selecionada"
                  >
                    <div className="decision-title">
                      <strong title={selectedReading.id}>
                        {readingLabel(selectedReading)}
                      </strong>
                      <CopyIdButton
                        key={selectedReading.id}
                        value={selectedReading.id}
                        label={readingLabel(selectedReading)}
                      />
                    </div>
                    {rectifyingReadingId === selectedReading.id ? (
                      <p className="batch-hint">
                        A decisão anterior fica guardada no histórico da obra — nada
                        se apaga. Escreva por que a medida muda e confirme a
                        associação, mesmo que ela continue a mesma.
                      </p>
                    ) : null}
                    {preview && evidenceCrop ? (
                      <EvidenceZoom
                        preview={preview}
                        crop={evidenceCrop}
                        rotation={evidenceRotation}
                        onRotate={() =>
                          setEvidenceRotation((current) =>
                            normalizeRotation(current + 90),
                          )
                        }
                        altText={`Recorte ampliado da leitura ${selectedReading.raw_text}`}
                        onNaturalSize={(size) =>
                          setNaturalImageSize((current) => current ?? size)
                        }
                      />
                    ) : null}
                    {message ? (
                      <p className="decision-error" role="alert">
                        {message}
                      </p>
                    ) : null}
                    <label>
                      Associação explícita
                      <select
                        value={selectedProposalId}
                        onChange={(event) =>
                          setSelectedProposalId(event.target.value)
                        }
                      >
                        <option value="">Selecione um candidato</option>
                        <option value={ANNOTATION_OPTION}>
                          Anotação da folha — não mede um elemento
                        </option>
                        {candidates.map((candidate) => (
                          <option
                            key={candidate.proposal_id}
                            value={candidate.proposal_id}
                          >
                            {proposalName(candidate.proposal_id)} ·{" "}
                            {relationLabel(candidate.relation)}
                          </option>
                        ))}
                      </select>
                    </label>
                    <p className="reading-current">
                      Proposta atual: <strong>{selectedReading.raw_text}</strong>
                      {selectedReading.value_si
                        ? ` → ${selectedReading.value_si} ${selectedReading.unit ?? ""}`
                        : ""}{" "}
                      · {measurementKindLabel(selectedReading.kind)}
                    </p>
                    <label>
                      Correção de texto (opcional)
                      <input
                        value={correction}
                        onChange={(event) => setCorrection(event.target.value)}
                        placeholder={selectedReading.raw_text}
                      />
                    </label>
                    <label>
                      Valor corrigido (opcional)
                      <input
                        value={correctionValue}
                        onChange={(event) => setCorrectionValue(event.target.value)}
                        inputMode="decimal"
                        placeholder={selectedReading.value_si ?? "ex.: 21,75"}
                      />
                    </label>
                    <label>
                      Unidade do valor corrigido
                      <select
                        value={correctionUnit}
                        disabled={!correctionValue.trim()}
                        onChange={(event) =>
                          setCorrectionUnit(event.target.value as "m" | "mm")
                        }
                      >
                        <option value="m">metros</option>
                        <option value="mm">milímetros</option>
                      </select>
                    </label>
                    <label>
                      Tipo corrigido (opcional)
                      <select
                        value={correctionKind}
                        onChange={(event) => setCorrectionKind(event.target.value)}
                      >
                        <option value="">
                          manter {measurementKindLabel(selectedReading.kind)}
                        </option>
                        {MEASUREMENT_KINDS.filter(
                          (kind) => kind !== selectedReading.kind,
                        ).map((kind) => (
                          <option key={kind} value={kind}>
                            {measurementKindLabel(kind)}
                          </option>
                        ))}
                      </select>
                      <small className="field-hint">
                        O tipo diz ao desenho em que direção a cota mede: largura →
                        horizontal, altura → vertical. Comprimento não declara
                        direção — prefira largura ou altura quando o trecho for reto.
                      </small>
                      {/* Dica lida do formato do recorte na folha; nada é
                          pré-selecionado, quem declara o eixo é o revisor. */}
                      {suggestedAxisHint(selectedReading.evidence) ? (
                        <small className="field-hint">
                          {suggestedAxisHint(selectedReading.evidence)}
                        </small>
                      ) : null}
                    </label>
                    <label>
                      {rectifyingReadingId === selectedReading.id
                        ? `Justificativa da correção (${decisionJustification.trim().length}/${JUSTIFICATION_MAX_LENGTH})`
                        : `Justificativa da decisão (${decisionJustification.trim().length}/${JUSTIFICATION_MAX_LENGTH})`}
                      <input
                        value={decisionJustification}
                        onChange={(event) =>
                          setDecisionJustification(event.target.value)
                        }
                        placeholder={
                          rectifyingReadingId === selectedReading.id
                            ? "Por que a medida registrada muda, nas suas palavras"
                            : "O que você conferiu na evidência, nas suas palavras"
                        }
                        maxLength={JUSTIFICATION_MAX_LENGTH}
                      />
                    </label>
                    {/* O texto do botão diz que o envio está em curso — o mesmo
                        padrão do envio do PDF. Sem isso, a espera de rede parecia
                        clique perdido e o revisor clicava de novo. */}
                    {rectifyingReadingId === selectedReading.id ? (
                      <div>
                        <button
                          type="button"
                          disabled={submitting}
                          onClick={() => void submitRectification("confirm")}
                        >
                          {submitting ? "Enviando…" : "Registrar correção"}
                        </button>
                        <button
                          type="button"
                          disabled={submitting}
                          onClick={() => void submitRectification("reject")}
                        >
                          {submitting
                            ? "Enviando…"
                            : "Registrar correção como rejeição"}
                        </button>
                        <button
                          type="button"
                          disabled={submitting}
                          onClick={cancelRectification}
                        >
                          Cancelar
                        </button>
                      </div>
                    ) : (
                      <div>
                        <button
                          type="button"
                          disabled={submitting}
                          onClick={() => void submitDecision("confirm")}
                        >
                          {submitting ? "Enviando…" : "Confirmar"}
                        </button>
                        <button
                          type="button"
                          disabled={
                            submitting ||
                            (!correction.trim() &&
                              !correctionValue.trim() &&
                              !correctionKind)
                          }
                          onClick={() => void submitDecision("correct")}
                        >
                          {submitting ? "Enviando…" : "Corrigir e confirmar"}
                        </button>
                        <button
                          type="button"
                          disabled={submitting}
                          onClick={() => void submitDecision("reject")}
                        >
                          {submitting ? "Enviando…" : "Rejeitar"}
                        </button>
                      </div>
                    )}
                  </section>
                ) : null}
                {selectedReading?.status === "confirmed" &&
                rectifyingReadingId !== selectedReading.id ? (
                  <section className="binding-controls" aria-label="Cota no desenho">
                    {readingIsBound(selectedReading.id) ? (
                      <p className="batch-hint">
                        Esta cota já está amarrada a uma linha do desenho.
                      </p>
                    ) : bindingReadingId === selectedReading.id ? (
                      <>
                        <p className="batch-hint">
                          Clique na linha traçada que corresponde a{" "}
                          <strong>{selectedReading.raw_text}</strong>. Ela vai assumir
                          essa medida.
                        </p>
                        <label>
                          Justificativa da amarração
                          <input
                            value={bindingJustification}
                            onChange={(event) =>
                              setBindingJustification(event.target.value)
                            }
                            placeholder="Por que esta linha é a da cota, nas suas palavras"
                            maxLength={JUSTIFICATION_MAX_LENGTH}
                          />
                        </label>
                        <button
                          type="button"
                          disabled={submitting}
                          onClick={() => {
                            setBindingReadingId(null);
                            setBindingJustification("");
                          }}
                        >
                          Cancelar
                        </button>
                      </>
                    ) : (
                      <button
                        type="button"
                        disabled={submitting || tracedProposalIds.size === 0}
                        onClick={() => {
                          setShowProposals(true);
                          setBindingReadingId(selectedReading.id);
                          setBindingJustification("");
                        }}
                      >
                        Amarrar cota a uma linha traçada
                      </button>
                    )}
                    {tracedProposalIds.size === 0 ? (
                      <p className="batch-hint">
                        Nenhuma linha traçada ainda. Aceite geometria aproximada antes.
                      </p>
                    ) : null}
                  </section>
                ) : null}
              </section>
            ) : null}
            {visibleStep === "trace" ? (
              <section
                className="journey-section"
                aria-label="Etapa de traçado do desenho"
              >
                {proposals.length > 0 && !showProposals ? (
                  <button
                    type="button"
                    className="proposal-toggle"
                    onClick={() => setShowProposals(true)}
                  >
                    Geometria aproximada · {proposals.length} propostas
                    <small>
                      Opcional. Só é necessária para aceitar geometria sem cota escrita.
                    </small>
                  </button>
                ) : null}
                {proposals.length > 0 && showProposals ? (
                  <section
                    className="proposal-controls"
                    aria-labelledby="proposal-title"
                  >
                    <div className="proposal-heading">
                      <div>
                        <span className="eyebrow">GEOMETRIA EM REVISÃO</span>
                        <h3 id="proposal-title">Formas detectadas no desenho</h3>
                      </div>
                      <button
                        type="button"
                        className="rotate-button"
                        onClick={() => setShowProposals(false)}
                        aria-label="Recolher propostas"
                        title="Recolher"
                      >
                        ×
                      </button>
                    </div>
                    <section className="batch-controls" aria-label="Decisão em lote">
                      {/* A contagem muda por gesto no desenho, longe deste painel: quem
                          usa leitor de tela precisa ouvir o novo total. */}
                      <p className="batch-count" aria-live="polite">
                        <strong>{batchIds.size}</strong> de {undecidedProposals.length}{" "}
                        selecionadas
                      </p>
                      <p className="batch-hint">
                        Clique nas formas do desenho para marcar ou desmarcar.
                        Shift+arrasto desenha um retângulo e adiciona à seleção tudo o
                        que ele tocar; arrasto simples continua deslocando o desenho.
                      </p>
                      <div className="batch-buttons">
                        <button
                          type="button"
                          onClick={() => {
                            const all = undecidedProposals.map(
                              (item) => item.id,
                            );
                            setBatchIds(new Set(all));
                            markAddedProposals(
                              all.filter((id) => !batchIds.has(id)),
                            );
                          }}
                        >
                          Selecionar todas
                        </button>
                        <button
                          type="button"
                          disabled={batchIds.size === 0}
                          onClick={() => setBatchIds(new Set())}
                        >
                          Limpar
                        </button>
                      </div>
                      <label>
                        Justificativa do lote
                        <input
                          value={batchJustification}
                          onChange={(event) =>
                            setBatchJustification(event.target.value)
                          }
                        />
                      </label>
                      {review.calibration ? (
                        <p className="batch-hint">
                          Régua por {calibrationModeLabel(review.calibration.mode)}
                          {review.calibration.anisotropy &&
                          review.calibration.anisotropy > 1.01
                            ? ` · os eixos divergem ${formatDecimal(
                                (review.calibration.anisotropy - 1) * 100,
                                1,
                              )}% em escala; círculos sairão como polilinhas`
                            : ""}
                        </p>
                      ) : (
                        <p className="batch-hint">
                          Confirme a calibração abaixo antes de aceitar.
                        </p>
                      )}
                      <div className="batch-buttons">
                        <button
                          type="button"
                          disabled={
                            submitting || batchIds.size === 0 || !review.calibration
                          }
                          onClick={() => void submitBatch("accept")}
                        >
                          Aceitar {batchIds.size} como aproximadas
                        </button>
                        <button
                          type="button"
                          disabled={submitting || batchIds.size === 0}
                          onClick={() => void submitBatch("reject")}
                        >
                          Rejeitar {batchIds.size}
                        </button>
                      </div>
                    </section>
                    {confirmedCount > 0 ? (
                      <section
                        className="trace-controls"
                        aria-labelledby="trace-acceptance-title"
                      >
                        <h4 id="trace-acceptance-title">Aceite de traçado</h4>
                        <p className="batch-hint">
                          Usa as mesmas formas marcadas acima. Você declara o que
                          aceitou; quem resolve a cena em metros é o solver, no
                          servidor, com a cota confirmada mandando sobre o pixel.
                        </p>
                        {traceDraft.proposalIds.length === 0 ? (
                          <p className="batch-hint">
                            Nenhuma forma marcada ainda. Clique nas formas do desenho.
                          </p>
                        ) : (
                          <ul
                            className="trace-selection"
                            aria-label="Formas no aceite de traçado"
                          >
                            {traceDraft.proposalIds.map((proposalId) => (
                              <li key={proposalId} title={proposalId}>
                                <span>{proposalName(proposalId)}</span>
                                <span className="trace-flags">
                                  {TRACE_FLAGS.map((flag) => {
                                    const marked =
                                      traceDraft[flag.field].has(proposalId);
                                    return (
                                      <button
                                        key={flag.field}
                                        type="button"
                                        className={
                                          marked ? "trace-flag marked" : "trace-flag"
                                        }
                                        aria-pressed={marked}
                                        disabled={submitting}
                                        onClick={() =>
                                          toggleTraceFlag(flag.field, proposalId)
                                        }
                                      >
                                        {flag.label}: {marked ? "sim" : "não"}
                                      </button>
                                    );
                                  })}
                                </span>
                              </li>
                            ))}
                          </ul>
                        )}
                        <section
                          className="trace-spans"
                          aria-labelledby="trace-spans-title"
                        >
                          <h5 id="trace-spans-title">Vãos e amarrações</h5>
                          <p className="batch-hint">
                            A cota confirmada que não mede um elemento sozinho —
                            vão entre duas formas, trecho interno do mesmo
                            elemento, anotação da folha — é declarada aqui,
                            clicando no desenho. Se ainda não souber, deixe como
                            está: a leitura continua valendo do jeito que foi
                            decidida.
                          </p>
                          {/* A faixa fica sempre montada: região viva que só nasce
                              junto com o texto não é anunciada por leitor de tela, e o
                              gesto acontece no desenho, longe deste painel. */}
                          <div
                            className={
                              capturing
                                ? "capture-banner active"
                                : "capture-banner"
                            }
                          >
                            <p aria-live="polite">{captureHint(capture)}</p>
                            {capturing ? (
                              <button
                                type="button"
                                onClick={() =>
                                  dispatchCapture({ type: "cancel" })
                                }
                              >
                                Cancelar (Esc)
                              </button>
                            ) : null}
                          </div>
                          {confirmedReadings.length === 0 ? (
                            <p className="batch-hint">
                              Nenhuma cota confirmada ainda: decida as leituras
                              antes de amarrá-las ao desenho.
                            </p>
                          ) : (
                            <ul
                              className="trace-selection"
                              aria-label="Cotas confirmadas e suas amarrações"
                            >
                              {confirmedReadings.map((reading) => {
                                const draftSpan =
                                  traceDraft.associations[reading.id];
                                const draftNote =
                                  traceDraft.noteTargets[reading.id];
                                // Leitura confirmada SEM vão herdado é anotação da
                                // folha: é ela que costuma amarrar duas formas.
                                const inherited =
                                  review.selected_associations[reading.id];
                                const rowSelected =
                                  reading.id === selectedReadingId;
                                const noteChoice = draftNote
                                  ? parseNoteTarget(draftNote)
                                  : null;
                                // A pendência de eixo se resolve aqui, na cota: a
                                // lista agregada continua acusando, mas quem vai
                                // corrigi-la precisa vê-la na própria linha.
                                const axisMissing = draftSpan
                                  ? spanAxisIssue(reading, draftSpan)
                                  : null;
                                return (
                                  <li key={reading.id} title={reading.id}>
                                    <button
                                      type="button"
                                      className={
                                        rowSelected
                                          ? "span-row selected"
                                          : "span-row"
                                      }
                                      aria-pressed={rowSelected}
                                      onClick={() =>
                                        setSelectedReadingId(reading.id)
                                      }
                                    >
                                      <span>{readingLabel(reading)}</span>
                                      <small>
                                        {draftSpan
                                          ? spanTargetSummary(draftSpan)
                                          : draftNote
                                            ? noteTargetSummary(draftNote)
                                            : inherited
                                              ? `mede a forma ${proposalName(inherited)}`
                                              : "anotação da folha — sem vão"}
                                      </small>
                                    </button>
                                    {/* O texto é o indicador; a cor só reforça. */}
                                    {axisMissing ? (
                                      <small className="axis-warning">
                                        falta o eixo: confirme se esta medida é
                                        largura ou altura
                                      </small>
                                    ) : null}
                                    {/* A pergunta ancora na folha: a linha aberta
                                        mostra o mesmo recorte da etapa de decisão. */}
                                    {rowSelected && preview && evidenceCrop ? (
                                      <EvidenceZoom
                                        preview={preview}
                                        crop={evidenceCrop}
                                        rotation={evidenceRotation}
                                        onRotate={() =>
                                          setEvidenceRotation((current) =>
                                            normalizeRotation(current + 90),
                                          )
                                        }
                                        altText={`Recorte ampliado da cota ${reading.raw_text}`}
                                        onNaturalSize={(size) =>
                                          setNaturalImageSize(
                                            (current) => current ?? size,
                                          )
                                        }
                                      />
                                    ) : null}
                                    <span className="trace-flags">
                                      {draftSpan || draftNote ? (
                                        <button
                                          type="button"
                                          className="trace-action"
                                          disabled={submitting}
                                          onClick={() =>
                                            draftSpan
                                              ? removeSpanTarget(reading.id)
                                              : removeNoteTarget(reading.id)
                                          }
                                        >
                                          Desfazer
                                        </button>
                                      ) : (
                                        <>
                                          {inherited ? (
                                            <button
                                              type="button"
                                              className="trace-action"
                                              disabled={submitting}
                                              onClick={() =>
                                                beginCapture({
                                                  kind: "single",
                                                  readingId: reading.id,
                                                })
                                              }
                                            >
                                              Reamarrar
                                            </button>
                                          ) : null}
                                          <button
                                            type="button"
                                            className="trace-action"
                                            disabled={submitting}
                                            onClick={() =>
                                              beginCapture({
                                                kind: "pair",
                                                readingId: reading.id,
                                                firstProposalId: null,
                                              })
                                            }
                                          >
                                            {inherited
                                              ? "Virar vão em par"
                                              : "Vão em par"}
                                          </button>
                                          <button
                                            type="button"
                                            className="trace-action"
                                            disabled={submitting}
                                            onClick={() =>
                                              beginCapture({
                                                kind: "declared",
                                                readingId: reading.id,
                                                proposalId: null,
                                                anchors: [],
                                              })
                                            }
                                          >
                                            Vão no próprio elemento
                                          </button>
                                          {inherited ? null : (
                                            <>
                                              <button
                                                type="button"
                                                className="trace-action"
                                                disabled={submitting}
                                                onClick={() =>
                                                  beginCapture({
                                                    kind: "note",
                                                    readingId: reading.id,
                                                  })
                                                }
                                              >
                                                Nota presa
                                              </button>
                                              <button
                                                type="button"
                                                className="trace-action"
                                                disabled={submitting}
                                                onClick={() =>
                                                  declareNoteTarget(
                                                    reading.id,
                                                    formatNoteTarget({
                                                      kind: "stamp",
                                                    }),
                                                  )
                                                }
                                              >
                                                Nota no carimbo
                                              </button>
                                            </>
                                          )}
                                        </>
                                      )}
                                    </span>
                                    {/* Nota no carimbo não tem forma nem orientação:
                                        a única ação dela é desfazer, acima. */}
                                    {noteChoice && noteChoice.kind !== "stamp" ? (
                                      <span className="trace-flags">
                                        {noteChoice.kind === "shape" ? (
                                          <label className="span-field">
                                            Orientação da nota
                                            <select
                                              value={noteChoice.orientation}
                                              disabled={submitting}
                                              onChange={(event) =>
                                                declareNoteTarget(
                                                  reading.id,
                                                  formatNoteTarget({
                                                    ...noteChoice,
                                                    orientation: event.target
                                                      .value as NoteOrientation,
                                                  }),
                                                )
                                              }
                                            >
                                              {(
                                                [
                                                  "auto",
                                                  "v",
                                                  "h",
                                                ] as NoteOrientation[]
                                              ).map((orientation) => (
                                                <option
                                                  key={orientation}
                                                  value={orientation}
                                                >
                                                  {
                                                    NOTE_ORIENTATION_LABELS[
                                                      orientation
                                                    ]
                                                  }
                                                </option>
                                              ))}
                                            </select>
                                          </label>
                                        ) : null}
                                        {noteChoice.kind === "shape" ? (
                                          <button
                                            type="button"
                                            className="trace-action"
                                            disabled={submitting}
                                            onClick={() =>
                                              declareNoteTarget(
                                                reading.id,
                                                formatNoteTarget({
                                                  kind: "legend",
                                                  proposalId:
                                                    noteChoice.proposalId,
                                                }),
                                              )
                                            }
                                          >
                                            Na legenda da forma
                                          </button>
                                        ) : null}
                                        {noteChoice.kind === "legend" ? (
                                          <button
                                            type="button"
                                            className="trace-action"
                                            disabled={submitting}
                                            onClick={() =>
                                              declareNoteTarget(
                                                reading.id,
                                                formatNoteTarget({
                                                  kind: "shape",
                                                  proposalId:
                                                    noteChoice.proposalId,
                                                  orientation: "auto",
                                                }),
                                              )
                                            }
                                          >
                                            Presa ao elemento
                                          </button>
                                        ) : null}
                                        <button
                                          type="button"
                                          className="trace-action"
                                          disabled={submitting}
                                          onClick={() =>
                                            declareNoteTarget(
                                              reading.id,
                                              formatNoteTarget({ kind: "stamp" }),
                                            )
                                          }
                                        >
                                          No carimbo
                                        </button>
                                      </span>
                                    ) : null}
                                    {/* Texto declarado só existe onde há trecho
                                        medido: sem vão ele é recusado no worker. */}
                                    {draftSpan || inherited ? (
                                      <label className="span-field">
                                        Texto da cota (opcional)
                                        <input
                                          value={
                                            traceDraft.dimensionTexts[
                                              reading.id
                                            ] ?? ""
                                          }
                                          maxLength={100}
                                          disabled={submitting}
                                          placeholder="ex.: 1,0 x 2,05"
                                          onChange={(event) =>
                                            setDimensionText(
                                              reading.id,
                                              event.target.value,
                                            )
                                          }
                                        />
                                      </label>
                                    ) : null}
                                  </li>
                                );
                              })}
                            </ul>
                          )}
                          <div className="batch-buttons">
                            <button
                              type="button"
                              disabled={submitting}
                              onClick={() =>
                                beginCapture({
                                  kind: "derived",
                                  proposalId: null,
                                })
                              }
                            >
                              Adicionar cota derivada
                            </button>
                          </div>
                          <p className="batch-hint">
                            Cota derivada mede um trecho desenhado pelo valor que
                            o solver resolveu — o 1,50 do dente do muro, que é
                            4,80 − 3,30. O número vem da geometria, nunca de
                            leitura da folha: clique na forma e depois no ponto
                            onde a cota deve pousar.
                          </p>
                          {traceDraft.derivedDimensions.length ? (
                            <ul
                              className="trace-selection"
                              aria-label="Cotas derivadas declaradas"
                            >
                              {traceDraft.derivedDimensions.map(
                                (dimension, index) => (
                                  <li
                                    key={`${dimension.proposalId}:${index}`}
                                    title={dimension.proposalId}
                                  >
                                    {/* A coordenada crua é endereço de máquina:
                                        ela fica no título, para conferência. */}
                                    <span
                                      title={derivedAnchorTitle(
                                        dimension.nearXPx,
                                        dimension.nearYPx,
                                      )}
                                    >
                                      {derivedDimensionLabel(
                                        proposalName(dimension.proposalId),
                                      )}
                                    </span>
                                    <label className="span-field">
                                      Texto da cota derivada (opcional)
                                      <input
                                        value={dimension.text ?? ""}
                                        maxLength={100}
                                        disabled={submitting}
                                        placeholder="ex.: 3,60 x 3,90"
                                        onChange={(event) =>
                                          updateDerivedDimension(index, {
                                            text: event.target.value,
                                          })
                                        }
                                      />
                                    </label>
                                    <span className="trace-flags">
                                      <button
                                        type="button"
                                        className="trace-action"
                                        disabled={submitting}
                                        onClick={() =>
                                          removeDerivedDimension(index)
                                        }
                                      >
                                        Desfazer
                                      </button>
                                    </span>
                                  </li>
                                ),
                              )}
                            </ul>
                          ) : null}
                        </section>
                        <fieldset
                          className="calibration-controls trace-detail-controls"
                          disabled={submitting}
                        >
                          <legend>Grupo de detalhe</legend>
                          <p className="proposal-hint">
                            Painel, arquibancada ou isométrico desenhado ao lado da
                            planta. Agrupe as formas do detalhe; o restante da
                            seleção continua na planta principal.
                          </p>
                          <label>
                            Código do detalhe
                            <input
                              value={detailId}
                              maxLength={8}
                              onChange={(event) => setDetailId(event.target.value)}
                            />
                          </label>
                          <label>
                            Título do detalhe
                            <input
                              value={detailTitle}
                              maxLength={120}
                              onChange={(event) =>
                                setDetailTitle(event.target.value)
                              }
                            />
                          </label>
                          <label>
                            Escala do detalhe
                            <select
                              value={detailMode}
                              onChange={(event) =>
                                setDetailMode(
                                  event.target.value as TraceDetailMode,
                                )
                              }
                            >
                              <option value="solve">
                                {DETAIL_MODE_LABELS.solve}
                              </option>
                              <option value="sketch">
                                {DETAIL_MODE_LABELS.sketch}
                              </option>
                            </select>
                          </label>
                          <button
                            type="button"
                            disabled={ungroupedSelection.length === 0}
                            onClick={groupSelectionAsDetail}
                          >
                            Agrupar seleção como detalhe (
                            {ungroupedSelection.length}{" "}
                            {ungroupedSelection.length === 1 ? "forma" : "formas"})
                          </button>
                        </fieldset>
                        {traceDraft.detailGroups.length ? (
                          <ul
                            className="trace-declarations"
                            aria-label="Grupos de detalhe declarados"
                          >
                            {traceDraft.detailGroups.map((group) => (
                              <li key={group.detailId}>
                                <span>
                                  Detalhe {group.detailId} · {group.title} ·{" "}
                                  {DETAIL_MODE_LABELS[group.mode]} ·{" "}
                                  {group.proposalIds.length}{" "}
                                  {group.proposalIds.length === 1
                                    ? "forma"
                                    : "formas"}
                                </span>
                                <button
                                  type="button"
                                  disabled={submitting}
                                  onClick={() => removeDetailGroup(group.detailId)}
                                >
                                  Desfazer
                                </button>
                              </li>
                            ))}
                          </ul>
                        ) : null}
                        <div className="batch-buttons">
                          <button
                            type="button"
                            disabled={submitting || traceDraft.proposalIds.length !== 2}
                            onClick={keepSelectionApart}
                          >
                            Manter separados os dois selecionados
                          </button>
                        </div>
                        <p className="batch-hint">
                          Dois elementos desenhados um sobre o outro que você
                          reconhece como distintos: marque exatamente duas formas
                          para declará-los.
                        </p>
                        {traceDraft.keepApartPairs.length ? (
                          <ul
                            className="trace-declarations"
                            aria-label="Pares mantidos separados"
                          >
                            {traceDraft.keepApartPairs.map((pair, index) => (
                              <li key={`${pair.first}:${pair.second}`}>
                                <span>
                                  {proposalName(pair.first)} e{" "}
                                  {proposalName(pair.second)}
                                </span>
                                <span className="keep-apart-controls">
                                  <select
                                    aria-label={`Sentido da separação entre ${proposalName(
                                      pair.first,
                                    )} e ${proposalName(pair.second)}`}
                                    value={pair.axis ?? ""}
                                    disabled={submitting}
                                    onChange={(event) =>
                                      setKeepApartAxis(
                                        index,
                                        event.target.value === ""
                                          ? null
                                          : (event.target.value as "x" | "y"),
                                      )
                                    }
                                  >
                                    <option value="">
                                      {keepApartAxisLabel(null)}
                                    </option>
                                    <option value="x">
                                      {keepApartAxisLabel("x")}
                                    </option>
                                    <option value="y">
                                      {keepApartAxisLabel("y")}
                                    </option>
                                  </select>
                                  <button
                                    type="button"
                                    disabled={submitting}
                                    onClick={() => removeKeepApartPair(index)}
                                  >
                                    Desfazer
                                  </button>
                                </span>
                              </li>
                            ))}
                          </ul>
                        ) : null}
                        <label>
                          Título da prancha (opcional)
                          <input
                            value={traceDeclarations.title}
                            maxLength={120}
                            disabled={submitting}
                            onChange={(event) =>
                              setTraceDeclarations((current) => ({
                                ...current,
                                title: event.target.value,
                              }))
                            }
                          />
                        </label>
                        <label>
                          Nota do aceite (opcional)
                          <input
                            value={traceDeclarations.note}
                            maxLength={500}
                            disabled={submitting}
                            onChange={(event) =>
                              setTraceDeclarations((current) => ({
                                ...current,
                                note: event.target.value,
                              }))
                            }
                          />
                        </label>
                        {traceIssues.length ? (
                          <ul
                            className="trace-issues"
                            aria-label="Pendências do aceite de traçado"
                          >
                            {traceIssues.map((issue) => (
                              <li key={issue}>{issue}</li>
                            ))}
                          </ul>
                        ) : null}
                        <div className="batch-buttons">
                          <button
                            type="button"
                            disabled={
                              submitting ||
                              traceIssues.length > 0 ||
                              traceSolveInFlight(traceSolve)
                            }
                            onClick={() => void submitTraceSolve()}
                          >
                            {submitting ? (
                              "Enviando…"
                            ) : (
                              <>
                                Aceitar traçado (
                                {traceDraft.proposalIds.length}{" "}
                                {traceDraft.proposalIds.length === 1
                                  ? "forma"
                                  : "formas"}
                                )
                              </>
                            )}
                          </button>
                        </div>
                        <div className="trace-status" aria-live="polite">
                          <p>{traceSolveStatusLabel(traceSolve)}</p>
                          {traceResidualLabel ? (
                            <p className="batch-hint">
                              {traceResidualLabel}
                              {traceSolve?.residual_summary?.worst_code ? (
                                <>
                                  {" "}
                                  <code>
                                    {traceSolve.residual_summary.worst_code}
                                  </code>
                                </>
                              ) : null}
                            </p>
                          ) : null}
                          {traceSolve?.blockers.length ? (
                            <ul
                              className="blocker-list"
                              aria-label="Pendências do traçado"
                            >
                              {traceSolve.blockers.map((blocker) => (
                                <li key={blocker}>
                                  {traceBlockerLabel(
                                    blocker,
                                    review.packet.readings,
                                    proposals,
                                    review.calibration?.scale_m_per_px,
                                  )}
                                  <code>{blocker}</code>
                                </li>
                              ))}
                            </ul>
                          ) : null}
                          {traceSolve?.unapplied_reading_ids.length ? (
                            <ul
                              className="trace-declarations"
                              aria-label="Cotas não aplicadas ao traçado"
                            >
                              {traceSolve.unapplied_reading_ids.map((readingId) => {
                                const reading = review.packet.readings.find(
                                  (item) => item.id === readingId,
                                );
                                return (
                                  <li key={readingId} title={readingId}>
                                    <span>
                                      Não aplicada:{" "}
                                      {reading
                                        ? readingLabel(reading)
                                        : "cota fora do pacote de revisão"}
                                    </span>
                                  </li>
                                );
                              })}
                            </ul>
                          ) : null}
                        </div>
                      </section>
                    ) : null}
                    <div
                      className="proposal-list"
                      aria-label="Propostas geométricas"
                    >
                      {proposals.map((proposal) => {
                        const decision = proposalDecisionById.get(proposal.id);
                        return (
                          <button
                            key={proposal.id}
                            type="button"
                            aria-pressed={
                              proposal.id === selectedGeometryProposalId
                            }
                            className={
                              proposal.id === selectedGeometryProposalId
                                ? "proposal-row selected"
                                : "proposal-row"
                            }
                            onClick={() =>
                              setSelectedGeometryProposalId(proposal.id)
                            }
                            title={proposal.id}
                          >
                            <span
                              className={`status-dot ${decision?.action === "reject" ? "rejected" : decision?.action === "accept" ? "review" : "ambiguous"}`}
                              aria-hidden="true"
                            />
                            <span>{proposalName(proposal.id)}</span>
                            <small>{decisionActionLabel(decision?.action)}</small>
                          </button>
                        );
                      })}
                    </div>
                    {/* Caminho legado de aproximação: com o traçado em lote a régua
                        pixel→metro só é necessária para aceitar forma sem cota escrita.
                        Fica recolhida para não competir com o aceite do traçado. */}
                    <details className="calibration-details">
                      <summary>Calibração pixel→metro (caminho de aproximação)</summary>
                      {review.scene &&
                      lineProposals.length >= 2 &&
                      anchorEntities.length >= 2 ? (
                        <fieldset
                          className="calibration-controls"
                          disabled={submitting}
                        >
                          <legend>Régua da conversão pixel→metro</legend>
                          <p className="proposal-hint">
                            Escolha duas linhas retas do desenho que correspondam a
                            medidas já resolvidas da cena; elas viram a régua da
                            conversão pixel→metro.
                          </p>
                          <label>
                            Régua — primeira linha
                            <select
                              value={firstAnchorProposalId}
                              onChange={(event) =>
                                setFirstAnchorProposalId(event.target.value)
                              }
                            >
                              {lineProposals.map((proposal) => (
                                <option key={proposal.id} value={proposal.id}>
                                  {proposalName(proposal.id)}
                                </option>
                              ))}
                            </select>
                          </label>
                          <label>
                            Régua — segunda linha
                            <select
                              value={secondAnchorProposalId}
                              onChange={(event) =>
                                setSecondAnchorProposalId(event.target.value)
                              }
                            >
                              {lineProposals.map((proposal) => (
                                <option key={proposal.id} value={proposal.id}>
                                  {proposalName(proposal.id)}
                                </option>
                              ))}
                            </select>
                          </label>
                          <button
                            type="button"
                            onClick={() => void submitCalibration()}
                          >
                            Confirmar calibração
                          </button>
                        </fieldset>
                      ) : (
                        <p className="proposal-hint">
                          Para calibrar são precisas duas linhas retas detectadas no
                          desenho e duas medidas já resolvidas na cena (exatas ou
                          derivadas).
                        </p>
                      )}
                      {review.calibration ? (
                        <>
                          <p className="calibration-summary">
                            Calibração ativa · resíduo de{" "}
                            {formatDecimal(review.calibration.rmse_m, 2)} m · a
                            geometria continua aproximada até virar cota.
                          </p>
                          {review.calibration.anchors.length ? (
                            <ul
                              className="calibration-anchors"
                              aria-label="Régua da calibração"
                            >
                              {review.calibration.anchors.map((anchor) => (
                                <li
                                  key={`${anchor.proposal_id}:${anchor.entity_id}`}
                                  title={`${anchor.proposal_id} ↔ ${anchor.entity_id}`}
                                >
                                  Régua: {proposalName(anchor.proposal_id)} ↔{" "}
                                  {metricEdgeLabel(entityById.get(anchor.entity_id))}
                                </li>
                              ))}
                            </ul>
                          ) : null}
                        </>
                      ) : null}
                    </details>
                    {selectedGeometryProposal ? (
                      <div
                        className="proposal-decision"
                        aria-label="Decisão da proposta selecionada"
                      >
                        <div className="decision-title">
                          <strong title={selectedGeometryProposal.id}>
                            {proposalName(selectedGeometryProposal.id)}
                          </strong>
                          <CopyIdButton
                            key={selectedGeometryProposal.id}
                            value={selectedGeometryProposal.id}
                            label={proposalName(selectedGeometryProposal.id)}
                          />
                        </div>
                        <label>
                          Justificativa
                          <input
                            value={proposalJustification}
                            onChange={(event) =>
                              setProposalJustification(event.target.value)
                            }
                          />
                        </label>
                        <div>
                          <button
                            type="button"
                            disabled={
                              submitting ||
                              !review.calibration ||
                              !proposalJustification
                            }
                            onClick={() => void submitGeometryProposal("accept")}
                          >
                            Aceitar como aproximada
                          </button>
                          <button
                            type="button"
                            disabled={submitting || !proposalJustification}
                            onClick={() => void submitGeometryProposal("reject")}
                          >
                            Rejeitar proposta
                          </button>
                        </div>
                      </div>
                    ) : null}
                  </section>
                ) : null}
              </section>
            ) : null}
            {visibleStep === "approval" ? (
              <section
                className="journey-section"
                aria-label="Etapa de aprovação técnica"
              >
                <div className="panel-heading">
                  <div>
                    <span className="eyebrow">GUARDRAILS</span>
                    <h2 id="audit-title">Estado de publicação</h2>
                  </div>
                  <span className={review.scene?.approved ? "ready" : "blocked"}>
                    {review.scene?.approved ? "Aprovado" : "Bloqueado"}
                  </span>
                </div>
                <dl className="audit-list">
                  <div>
                    <dt>Leituras confirmadas</dt>
                    <dd>
                      {confirmedCount} de {review.packet.readings.length}
                    </dd>
                  </div>
                  <div>
                    <dt>Revisão</dt>
                    <dd>v{review.version}</dd>
                  </div>
                  <div>
                    <dt>Cena métrica</dt>
                    <dd>
                      {!review.scene
                        ? "Não criada"
                        : review.scene.approved
                          ? `Aprovada v${review.scene.version}`
                          : "Rascunho não aprovado"}
                    </dd>
                  </div>
                  <div>
                    <dt>DXF</dt>
                    <dd>{exportStatusLabel(exportArtifact)}</dd>
                  </div>
                </dl>
                <section className="issue-panel" aria-label="Bloqueios e issues">
                  <strong>Bloqueios visíveis</strong>
                  {review.blockers.length ? (
                    <ul className="blocker-list">
                      {review.blockers.map((blocker) => (
                        <li key={blocker}>
                          {reviewBlockerLabel(blocker, review.packet.readings)}
                          <code>{blocker}</code>
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <p>
                      A aprovação técnica e a auditoria ainda são necessárias antes
                      de exportar.
                    </p>
                  )}
                </section>
                {review.scene && !review.scene.approved ? (
                  <fieldset className="approval-controls">
                    <legend>Aprovação técnica</legend>
                    <label>
                      <input
                        type="checkbox"
                        checked={approvalForm.sourceEvidenceChecked}
                        onChange={(event) =>
                          setApprovalForm({
                            ...approvalForm,
                            sourceEvidenceChecked: event.target.checked,
                          })
                        }
                      />
                      Verifiquei a evidência de origem no material protegido.
                    </label>
                    <label>
                      <input
                        type="checkbox"
                        checked={approvalForm.geometryChecked}
                        onChange={(event) =>
                          setApprovalForm({
                            ...approvalForm,
                            geometryChecked: event.target.checked,
                          })
                        }
                      />
                      Verifiquei a geometria resultante da cena.
                    </label>
                    <label>
                      <input
                        type="checkbox"
                        checked={approvalForm.limitationsAcknowledged}
                        onChange={(event) =>
                          setApprovalForm({
                            ...approvalForm,
                            limitationsAcknowledged: event.target.checked,
                          })
                        }
                      />
                      Reconheço as limitações declaradas deste pacote.
                    </label>
                    {acceptedApproximations.length ? (
                      <p>
                        {acceptedApproximations.length === 1
                          ? "1 geometria aproximada será aceita nominalmente: "
                          : `${acceptedApproximations.length} geometrias aproximadas serão aceitas nominalmente: `}
                        {acceptedApproximations.map((item, index) => (
                          <span key={item.entityId} title={item.entityId}>
                            {index > 0 ? ", " : ""}
                            {item.label}
                          </span>
                        ))}
                        .
                      </p>
                    ) : null}
                    {scopeCriteria.length ? (
                      <div className="scope-criteria">
                        <strong>Critérios de escopo deste caso</strong>
                        <p className="scope-criteria-hint">
                          Declare cada critério: coberto pela cena métrica que está
                          sendo aprovada ou pendente reconhecido fora dela. Nenhuma
                          das duas opções vem marcada.
                        </p>
                        {scopeCriteria.map((criterion) => (
                          <fieldset
                            key={criterion.code}
                            className="criterion-declaration"
                          >
                            <legend>
                              {criterion.text}
                              <code>{criterion.code}</code>
                            </legend>
                            <label>
                              <input
                                type="radio"
                                name={`criterion-${criterion.code}`}
                                checked={approvalForm.coveredCriteria.includes(
                                  criterion.code,
                                )}
                                onChange={() =>
                                  declareCriterion(criterion.code, "covered")
                                }
                              />
                              Coberto pela cena métrica
                            </label>
                            <label>
                              <input
                                type="radio"
                                name={`criterion-${criterion.code}`}
                                checked={approvalForm.acknowledgedCriteria.includes(
                                  criterion.code,
                                )}
                                onChange={() =>
                                  declareCriterion(criterion.code, "acknowledged")
                                }
                              />
                              Reconheço como pendente fora da cena
                            </label>
                          </fieldset>
                        ))}
                      </div>
                    ) : null}
                    <label>
                      Declaração técnica ({approvalForm.statement.trim().length}/500)
                      <textarea
                        value={approvalForm.statement}
                        maxLength={500}
                        onChange={(event) =>
                          setApprovalForm({
                            ...approvalForm,
                            statement: event.target.value,
                          })
                        }
                      />
                    </label>
                    {readiness.reasons.length ? (
                      <ul className="readiness-reasons">
                        {readiness.reasons.map((reason) => (
                          <li key={reason}>{reason}</li>
                        ))}
                      </ul>
                    ) : null}
                    <button
                      type="button"
                      disabled={submitting || !readiness.canApprove}
                      onClick={() => void submitApproval()}
                    >
                      {submitting ? "Enviando…" : "Aprovar tecnicamente"}
                    </button>
                  </fieldset>
                ) : review.scene?.approved ? (
                  <section className="approval-summary" aria-label="Aprovação técnica">
                    <strong>Aprovada tecnicamente</strong>
                    <p>
                      Cena v{review.scene.version} assinada. O formulário de aprovação
                      não se aplica mais a esta revisão.
                    </p>
                    {coveredSceneCriteria.length ? (
                      <p>
                        Cobertos pela cena: {coveredSceneCriteria.join(" · ")}
                      </p>
                    ) : null}
                    {acknowledgedSceneCriteria.length ? (
                      <p>
                        Reconhecidos como pendentes:{" "}
                        {acknowledgedSceneCriteria.join(" · ")}
                      </p>
                    ) : null}
                  </section>
                ) : null}
              </section>
            ) : null}
            {visibleStep === "export" ? (
              <section
                className="journey-section"
                aria-label="Etapa de exportação do DXF"
              >
                {approvedRevisionId || review.scene?.approved ? (
                  <section className="export-controls" aria-label="Exportação">
                    {/* Só exportação em voo trava o botão. Auditoria que reprovou
                        precisa poder ser reenviada depois da correção; pacote
                        pronto também, porque a cena pode ter mudado desde ele. */}
                    <button
                      type="button"
                      disabled={submitting || exportInFlight(exportArtifact)}
                      onClick={() => void startExport()}
                    >
                      {submitting ? "Enviando…" : "Exportar DXF"}
                    </button>
                    <p aria-live="polite">{exportStatusLabel(exportArtifact)}</p>
                    {exportArtifact?.status === "COMPLETED" &&
                    exportArtifact.package_url ? (
                      <p>
                        <a href={exportArtifact.package_url} rel="noreferrer" download>
                          Baixar pacote auditado
                        </a>{" "}
                        · auditoria {exportArtifact.audit_status}
                        <br />
                        SHA-256 <code>{exportArtifact.dxf_sha256}</code>
                      </p>
                    ) : null}
                    {exportArtifact?.status === "FAILED" ? (
                      <ul>
                        {exportArtifact.audit_errors.map((error) => (
                          <li key={error}>{error}</li>
                        ))}
                      </ul>
                    ) : null}
                  </section>
                ) : null}
              </section>
            ) : null}
            {/* Painel auxiliar, fora da jornada: a conversa não é etapa, não libera
                nada e acompanha as duas etapas em que a folha ainda está em leitura. */}
            {chatAvailable ? (
              <details
                className="chat-details"
                open={chatOpen}
                onToggle={(event) => setChatOpen(event.currentTarget.open)}
              >
                <summary>Conversa sobre a folha</summary>
                <section className="chat-panel" aria-label="Conversa sobre a folha">
                  <p className="batch-hint">
                    Pergunte o que a folha não deixa claro. A resposta é
                    observação: cada sugestão vira formulário preenchido para você
                    conferir, nunca ato registrado.
                  </p>
                  {chatTurns.length === 0 ? (
                    <p className="chat-empty">
                      Nenhuma pergunta nesta revisão ainda.
                    </p>
                  ) : (
                    <ol
                      className="chat-feed"
                      aria-label="Perguntas e respostas desta revisão"
                    >
                      {chatTurns.map((turn) => (
                        <li key={turn.chat_turn_id} className="chat-turn">
                          <p className="chat-question">
                            <strong>Você perguntou</strong>
                            <span>{turn.question}</span>
                          </p>
                          {/* Estado sempre escrito: a espera e a falha não são
                              indicadas só por cor nem só por posição. */}
                          <p className="chat-state" aria-live="polite">
                            {chatTurnStatusLabel(turn)}
                          </p>
                          {turn.answer ? (
                            <div className="chat-answer">
                              <p>{turn.answer.answer_text}</p>
                              <p className="chat-state">
                                {chatAnswerSummary(turn.answer)}
                              </p>
                              {turn.answer.open_question ? (
                                <p className="chat-open-question">
                                  <strong>Pergunta em aberto:</strong>{" "}
                                  {turn.answer.open_question}
                                </p>
                              ) : null}
                              {turn.answer.evidence_notes.length > 0 ? (
                                <ul className="chat-notes">
                                  {turn.answer.evidence_notes.map(
                                    (note, index) => (
                                      <li key={`${turn.chat_turn_id}:${index}`}>
                                        {note}
                                      </li>
                                    ),
                                  )}
                                </ul>
                              ) : null}
                              {turn.answer.proposed_acts.map((draft, index) => {
                                const anchor = chatActAnchor(draft);
                                const evidence = chatDraftEvidence(
                                  anchor.readingId,
                                );
                                const blocked =
                                  draft.act === "reading_decision" &&
                                  draftToReviewDecision(
                                    draft,
                                    review.packet.readings,
                                  ) === null;
                                return (
                                  <section
                                    key={`${turn.chat_turn_id}:${index}`}
                                    className="chat-draft"
                                    aria-label={`Rascunho ${index + 1} desta resposta`}
                                  >
                                    <p className="chat-draft-act">
                                      {chatActLabel(draft, {
                                        proposalName,
                                        readings: review.packet.readings,
                                      })}
                                    </p>
                                    {preview && evidence ? (
                                      <EvidenceZoom
                                        preview={preview}
                                        crop={evidence.crop}
                                        rotation={chatEvidenceRotation}
                                        onRotate={() =>
                                          setChatEvidenceRotation((current) =>
                                            normalizeRotation(current + 90),
                                          )
                                        }
                                        altText={`Recorte ampliado da leitura ${evidence.reading.raw_text}`}
                                        onNaturalSize={(size) =>
                                          setNaturalImageSize(
                                            (current) => current ?? size,
                                          )
                                        }
                                      />
                                    ) : null}
                                    {anchor.proposalIds.length > 0 ? (
                                      <div className="chat-draft-shapes">
                                        {anchor.proposalIds.map((proposalId) => (
                                          <button
                                            key={proposalId}
                                            type="button"
                                            className="button button-quiet"
                                            aria-label={`Destacar ${proposalName(proposalId)} no desenho`}
                                            onClick={() => {
                                              setShowProposals(true);
                                              setSelectedGeometryProposalId(
                                                proposalId,
                                              );
                                            }}
                                          >
                                            {proposalName(proposalId)}
                                          </button>
                                        ))}
                                      </div>
                                    ) : null}
                                    <button
                                      type="button"
                                      disabled={blocked}
                                      onClick={() => applyChatDraft(draft)}
                                    >
                                      Usar este rascunho
                                    </button>
                                    {blocked ? (
                                      <small className="field-hint">
                                        A leitura citada já foi decidida ou não está
                                        nesta revisão. Corrigir decisão registrada é
                                        ato próprio, com palavra nova.
                                      </small>
                                    ) : null}
                                  </section>
                                );
                              })}
                            </div>
                          ) : null}
                        </li>
                      ))}
                    </ol>
                  )}
                  <div className="chat-compose">
                    {chatAnchorChips.length > 0 ? (
                      <ul className="chat-anchors" aria-label="Âncoras desta pergunta">
                        {chatAnchorChips.map((chip) => (
                          <li key={chip.id}>
                            <span>{chip.label}</span>
                            <button
                              type="button"
                              className="rotate-button"
                              aria-label={`Tirar ${chip.label} das âncoras da pergunta`}
                              title="Tirar da pergunta"
                              onClick={() =>
                                setChatDroppedAnchors((current) =>
                                  new Set(current).add(chip.id),
                                )
                              }
                            >
                              ×
                            </button>
                          </li>
                        ))}
                      </ul>
                    ) : (
                      <p className="batch-hint">
                        Sem âncora: selecione uma leitura ou marque formas no desenho
                        para apontar o que a pergunta cita.
                      </p>
                    )}
                    {chatAnchorOverflow ? (
                      <p className="batch-hint">
                        Mais de {CHAT_ANCHOR_LIMIT} formas marcadas; só as{" "}
                        {CHAT_ANCHOR_LIMIT} primeiras viajam como âncora.
                      </p>
                    ) : null}
                    <label>
                      Pergunta sobre a folha
                      <textarea
                        value={chatQuestion}
                        onChange={(event) => setChatQuestion(event.target.value)}
                        rows={3}
                        maxLength={500}
                        placeholder="Ex.: essa cota mede a borda do patamar ou a mureta desenhada por cima?"
                      />
                    </label>
                    <div className="chat-compose-actions">
                      <button
                        type="button"
                        disabled={chatSending || chatBusy}
                        onClick={() => void sendChatQuestion()}
                      >
                        {chatSending ? "Enviando…" : "Perguntar"}
                      </button>
                      <small>{chatQuestion.trim().length}/500</small>
                    </div>
                    {chatBusy ? (
                      <p className="batch-hint">
                        Uma pergunta por vez: a anterior ainda está sendo respondida.
                      </p>
                    ) : null}
                    {chatMessage ? (
                      <p className="decision-error" role="alert">
                        {chatMessage}
                      </p>
                    ) : null}
                  </div>
                  <p className="chat-guard">
                    Nada aqui entra no desenho sem a sua confirmação.
                  </p>
                </section>
              </details>
            ) : null}
            <div className="policy-note">
              <strong>Sem falsa precisão</strong>
              <p>
                Cotas confirmadas e associação explícita criam somente uma cena
                rascunho. A exportação exige aprovação técnica explícita e a
                auditoria do DXF gerado.
              </p>
            </div>
          </aside>

          <article
            className="panel drawing-panel"
            aria-labelledby="drawing-title"
          >
            <div className="panel-heading drawing-heading">
              <div>
                <span className="eyebrow">PREVIEW E OVERLAY</span>
                <h2 id="drawing-title">Transformação sincronizada</h2>
                <p className="viewer-hint" id="drawing-hint">
                  Tecla {ROTATION_SHORTCUT_KEY} gira 90° à direita e Shift+
                  {ROTATION_SHORTCUT_KEY} à esquerda. Arraste o desenho para
                  deslocar; a rotação escolhida volta na próxima abertura. Com as
                  formas detectadas abertas, Shift+arrasto seleciona por retângulo.
                </p>
              </div>
              <div className="viewer-controls">
                <label className="zoom-control">
                  Zoom
                  <input
                    aria-label="Zoom do preview"
                    type="range"
                    min={MIN_ZOOM}
                    max={MAX_ZOOM}
                    step={ZOOM_STEP}
                    value={zoom}
                    onChange={(event) =>
                      setZoom(clampZoom(Number(event.target.value)))
                    }
                  />
                </label>
                <span className="rotate-readout">{zoom.toFixed(1)}×</span>
                <button
                  type="button"
                  className="rotate-button"
                  onClick={() => rotateViewer(-90)}
                  aria-label="Girar 90 graus à esquerda"
                  aria-keyshortcuts={`Shift+${ROTATION_SHORTCUT_KEY}`}
                  title={`Girar 90° à esquerda (Shift+${ROTATION_SHORTCUT_KEY})`}
                >
                  ↺
                </button>
                <button
                  type="button"
                  className="rotate-button"
                  onClick={() => rotateViewer(90)}
                  aria-label="Girar 90 graus à direita"
                  aria-keyshortcuts={ROTATION_SHORTCUT_KEY}
                  title={`Girar 90° à direita (${ROTATION_SHORTCUT_KEY})`}
                >
                  ↻
                </button>
                {/* O estado da rotação é texto, nunca só o ícone do botão. */}
                <span className="rotate-readout">Rotação {rotation}°</span>
              </div>
            </div>
            <div
              className={`drawing-canvas ${preview ? "pannable" : ""} ${
                panning ? "panning" : ""
              }`}
              aria-live="polite"
              ref={drawingCanvasRef}
              tabIndex={preview ? 0 : -1}
              aria-label={
                preview
                  ? "Desenho: arraste para deslocar, setas do teclado para rolar"
                  : undefined
              }
              aria-describedby={preview ? "drawing-hint" : undefined}
              onPointerDown={startPan}
              onPointerMove={movePan}
              onPointerUp={endPan}
              onPointerCancel={cancelPan}
            >
              {preview ? (
                // Enquanto a dimensão da página não é conhecida, o palco não inventa
                // proporção: a imagem se mede sozinha no fluxo e o transform assume
                // assim que ela carrega.
                <div
                  className="preview-stage"
                  style={
                    hasImageSize
                      ? stageStyle(zoom, rotation, imageWidthPx, imageHeightPx)
                      : undefined
                  }
                >
                <div
                  className={`preview-transform ${hasImageSize ? "" : "measuring"}`}
                  ref={previewTransformRef}
                  style={
                    hasImageSize
                      ? previewTransform(rotation, imageWidthPx, imageHeightPx)
                      : undefined
                  }
                >
                  <img
                    src={preview}
                    alt="Imagem original protegida do desenho"
                    // Sem isto o browser inicia o arrasto nativo da imagem e o pan morre.
                    draggable={false}
                    onLoad={(event) => {
                      // `currentTarget` só existe durante a propagação; dentro do
                      // updater (que roda depois) ele já é null. Capturar antes.
                      const { naturalWidth, naturalHeight } = event.currentTarget;
                      setNaturalImageSize(
                        (current) =>
                          current ?? { width: naturalWidth, height: naturalHeight },
                      );
                    }}
                  />
                  {overlay ? (
                    <img
                      className="review-overlay"
                      src={overlay}
                      alt="Overlay de evidências e leituras"
                      draggable={false}
                    />
                  ) : null}
                  {review.proposals ? (
                    <svg
                      className={`proposal-overlay ${showProposals || bindingReadingId || capturing ? "pickable" : ""}`}
                      aria-hidden="true"
                      viewBox={`0 0 ${review.proposals.image_width_px} ${review.proposals.image_height_px}`}
                      preserveAspectRatio="none"
                    >
                      {proposals.map((proposal) => {
                        const selected =
                          proposal.id === selectedGeometryProposalId;
                        const associating =
                          proposal.id === selectedProposalId &&
                          selectedReading !== null;
                        const decision = proposalDecisionById.get(proposal.id);
                        const batched = batchIds.has(proposal.id);
                        const bindable =
                          bindingReadingId !== null &&
                          tracedProposalIds.has(proposal.id);
                        const className = `proposal-shape ${selected ? "selected" : ""} ${associating ? "associating" : ""} ${batched ? "batched" : ""} ${bindable ? "bindable" : ""} ${decision?.action ?? "pending"}`;
                        // Na captura toda forma responde, inclusive a já decidida: um
                        // vão pode amarrar um elemento aceito antes. Amarrando uma cota,
                        // só linha já traçada responde. Fora disso, só o que ainda não
                        // foi decidido: decisão registrada é imutável.
                        const pick = capturing
                          ? (event: ReactMouseEvent<SVGElement>) =>
                              handleCaptureShapeClick(proposal.id, event)
                          : bindingReadingId
                            ? bindable
                              ? () => void bindDimension(proposal.id)
                              : undefined
                            : decision
                              ? undefined
                              : () => toggleBatch(proposal.id);
                        // O clique mora no grupo: a forma visível continua fina e o
                        // gêmeo transparente por cima dá o alvo que o dedo acerta.
                        if (proposal.geometry.type === "line") {
                          const { start, end } = proposal.geometry;
                          return (
                            <g key={proposal.id} onClick={pick}>
                              <line
                                className={className}
                                x1={start.x}
                                y1={start.y}
                                x2={end.x}
                                y2={end.y}
                              />
                              <line
                                className="proposal-hit"
                                strokeWidth={hitStrokeWidth}
                                x1={start.x}
                                y1={start.y}
                                x2={end.x}
                                y2={end.y}
                              />
                            </g>
                          );
                        }
                        if (proposal.geometry.type === "circle") {
                          const { center, radius } = proposal.geometry;
                          return (
                            <g key={proposal.id} onClick={pick}>
                              <circle
                                className={className}
                                cx={center.x}
                                cy={center.y}
                                r={radius}
                              />
                              <circle
                                className="proposal-hit"
                                strokeWidth={hitStrokeWidth}
                                cx={center.x}
                                cy={center.y}
                                r={radius}
                              />
                            </g>
                          );
                        }
                        const points = proposal.geometry.points
                          .map((point) => `${point.x},${point.y}`)
                          .join(" ");
                        return (
                          <g key={proposal.id} onClick={pick}>
                            <polyline className={className} points={points} />
                            <polyline
                              className="proposal-hit"
                              strokeWidth={hitStrokeWidth}
                              points={points}
                            />
                          </g>
                        );
                      })}
                      {marqueeRect ? (
                        <rect
                          className="marquee-rect"
                          x={marqueeRect.left}
                          y={marqueeRect.top}
                          width={marqueeRect.right - marqueeRect.left}
                          height={marqueeRect.bottom - marqueeRect.top}
                        />
                      ) : null}
                    </svg>
                  ) : null}
                  {/* Rascunho das amarrações: SVG próprio, nunca clicável, para não
                      disputar o cursor com as formas por baixo dele. */}
                  {review.proposals &&
                  (draftSpanLines.length > 0 || draftAnchors.length > 0) ? (
                    <svg
                      className="proposal-overlay draft-overlay"
                      aria-hidden="true"
                      viewBox={`0 0 ${review.proposals.image_width_px} ${review.proposals.image_height_px}`}
                      preserveAspectRatio="none"
                    >
                      {draftSpanLines.map((line) => (
                        <line
                          key={line.key}
                          className="draft-span"
                          x1={line.x1}
                          y1={line.y1}
                          x2={line.x2}
                          y2={line.y2}
                        />
                      ))}
                      {draftAnchors.map((anchor) => (
                        <circle
                          key={anchor.key}
                          className="draft-anchor"
                          cx={anchor.x}
                          cy={anchor.y}
                          r={draftMarkerRadius}
                        />
                      ))}
                    </svg>
                  ) : null}
                  {/* O recorte da leitura tem SVG próprio: ele precisa aparecer mesmo
                      quando a revisão não trouxe propostas de visão, e as dimensões da
                      página podem vir da imagem carregada. */}
                  {selectedEvidenceBox && hasImageSize ? (
                    <svg
                      className="proposal-overlay evidence-overlay"
                      aria-hidden="true"
                      viewBox={`0 0 ${imageWidthPx} ${imageHeightPx}`}
                      preserveAspectRatio="none"
                    >
                      <rect
                        className="reading-evidence"
                        x={selectedEvidenceBox.left}
                        y={selectedEvidenceBox.top}
                        width={
                          selectedEvidenceBox.right - selectedEvidenceBox.left
                        }
                        height={
                          selectedEvidenceBox.bottom - selectedEvidenceBox.top
                        }
                      />
                    </svg>
                  ) : null}
                </div>
                </div>
              ) : (
                <p className="preview-empty">
                  A revisão não contém preview disponível. A evidência continua
                  restrita ao tenant.
                </p>
              )}
            </div>
          </article>
        </section>
      ) : null}
    </main>
  );
}
