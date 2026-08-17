import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type KeyboardEvent as ReactKeyboardEvent,
  type PointerEvent as ReactPointerEvent,
} from "react";
import type { User } from "oidc-client-ts";

import {
  codeSearchTerm,
  extractPlate,
  fetchImageObjectUrl,
  getBulletin,
  getCodes,
  getDossier,
  getState,
  getSuggestions,
  getTakeoff,
  isAbortError,
  isStateMoved,
  itemAnchor,
  MedicaoApiError,
  PLATE_IMAGE_PATH,
  plateImageSource,
  postCalcBuild,
  postCodeDecision,
  postDossierBuild,
  postSuggestionsRecompute,
  postTakeoffDecision,
  searchCatalog,
  setAccessTokenProvider,
  uploadPlate,
  type BulletinResponse,
  type CatalogSearchResponse,
  type CodeAssignment,
  type CodeCandidate,
  type CodesResponse,
  type CodeSuggestionSet,
  type DossierResponse,
  type ExtractionState,
  type RunState,
  type TakeoffItem,
  type TakeoffResponse,
} from "./api";
import { isOidcConfigured, onSessionRenewed, readSession, signIn, signOut } from "./auth";
import { BUSCA_DEBOUNCE_MS, consultaIncremental, resumoDaBusca } from "./busca";
import { derivarEtapas, etapaStatusLabel, type Etapa, type EtapaId } from "./etapas";
import { classifyExecucao } from "./execucao";
import { extractInclusoes, type Inclusao } from "./inclusoes";
import {
  formatDecimalText,
  formatMoneyText,
  formatQuantityText,
  formatTimestamp,
  parseQuantityInput,
  shortDigest,
} from "./format";
import {
  assignmentStatusLabel,
  AVISO_ADITIVO,
  AVISO_DOSSIE_GERADO,
  AVISO_DOSSIE_PREVIA,
  AVISO_LOCALIZACAO_NAO_CONFIRMADA,
  AVISO_QUANTIDADE_AMBIGUA,
  avisoDaFerramenta,
  descricaoCalculoShortlist,
  DICA_QUANTIDADE,
  errorMessage,
  itemStatusLabel,
  recipeLabel,
  unitLabel,
  unitMismatchHint,
} from "./labels";
import {
  bboxRect,
  clampZoom,
  MAX_ZOOM,
  MIN_ZOOM,
  panScrollOffset,
  PIN_DIAMETER_PX,
  pinPlacement,
  stageStyle,
  zoomAfterWheel,
  ZOOM_STEP,
  type PanOrigin,
} from "./viewport";

/** Duração do aviso de sucesso; recusa nenhuma expira sozinha. */
const TOAST_MS = 5000;

/** Intervalo do poll do `/state` enquanto a extração automática está `running`. */
const EXTRACTION_POLL_MS = 3000;

type DecisionAction = "" | "confirm" | "reject";

type CodeChoice = {
  code: string;
  description: string;
  unit: string;
  unit_price: string;
  /** Vem do servidor quando a escolha saiu da shortlist; `null` quando saiu da busca. */
  unit_compatible: boolean | null;
};

const EMPTY_DECISION = {
  action: "" as DecisionAction,
  quantity: "",
  unit: "",
  note: "",
  itemNote: "",
};

const EMPTY_CALC = {
  worksiteKey: "",
  worksiteName: "",
  periodNumber: "",
  referenceLabel: "",
  address: "",
  contractLabel: "",
};

function describeError(error: unknown): string {
  if (error instanceof MedicaoApiError) {
    return errorMessage(error.code, error.detail);
  }
  return error instanceof Error ? error.message : String(error);
}

/** Última pasta do caminho da rodada; é assim que a orçamentista chama a rodada. */
function nomeDaRodada(root: string): string {
  const parts = root.split("/").filter((part) => part.length > 0);
  return parts.length === 0 ? root : parts[parts.length - 1];
}

/** Confirmado e com código — o único caso em que faz sentido buscar a descrição dele. */
function isConfirmedWithCode(
  assignment: CodeAssignment,
): assignment is CodeAssignment & { code: string } {
  return assignment.status === "confirmed" && assignment.code !== null;
}

/** Unidades divergem? A resposta do servidor manda; a comparação textual é o fallback. */
function unidadesDivergem(itemUnit: string, choice: CodeChoice): boolean {
  if (choice.unit_compatible !== null) {
    return !choice.unit_compatible;
  }
  return itemUnit.trim().toLowerCase() !== choice.unit.trim().toLowerCase();
}

/** Selo de leitura da descrição; o `title` carrega a explicação da heurística. */
function SeloExecucao({ description }: { description: string }) {
  const hint = classifyExecucao(description);
  return (
    <span className={`selo selo-${hint.kind}`} title={hint.explanation}>
      {hint.label}
    </span>
  );
}

/** Tamanho de leitura de relance; trunca só a exibição — o dado (`title`, expandir) fica inteiro. */
const CHIP_TRUNCATE_LENGTH = 90;

function truncarChip(text: string): { curto: string; truncado: boolean } {
  if (text.length <= CHIP_TRUNCATE_LENGTH) {
    return { curto: text, truncado: false };
  }
  return { curto: `${text.slice(0, CHIP_TRUNCATE_LENGTH).trimEnd()}…`, truncado: true };
}

/**
 * Chip de inclusão/exclusão: citação literal do catálogo (`inclusoes.ts`), nunca só
 * cor — o prefixo por extenso ("Inclui:"/"Não inclui:") acompanha sempre o texto. Texto
 * longo trunca só na exibição; `title` e o clique (`<details>`) sempre dão acesso ao
 * texto inteiro.
 */
function ChipInclusao({
  prefixo,
  texto,
  tom,
}: {
  prefixo: string;
  texto: string;
  tom: "inclui" | "nao_inclui";
}) {
  const { curto, truncado } = truncarChip(texto);
  if (!truncado) {
    return (
      <span className={`chip chip-${tom}`} title={texto}>
        {prefixo} {texto}
      </span>
    );
  }
  return (
    <details className={`chip chip-${tom} chip-expansivel`}>
      <summary title={texto}>
        {prefixo} {curto}
      </summary>
      <p className="chip-texto-completo">{texto}</p>
    </details>
  );
}

/**
 * Linha de chips do que a descrição diz que inclui/não inclui, extraída por
 * `extractInclusoes`. Sem marcador conhecido, não mostra a seção — nunca inventa leitura.
 */
function Inclusoes({ description }: { description: string }) {
  const inclusoes = useMemo(() => extractInclusoes(description), [description]);
  if (inclusoes.length === 0) {
    return null;
  }
  return (
    <div
      className="inclusoes-lista"
      aria-label="O que a descrição diz que inclui ou não inclui"
    >
      {inclusoes.map((item: Inclusao, index) =>
        item.kind === "so_fornecimento" ? (
          <span key={index} className="chip chip-so-fornecimento">
            somente fornecimento — execução fora deste código
          </span>
        ) : (
          <ChipInclusao
            key={index}
            prefixo={item.kind === "inclui" ? "Inclui:" : "Não inclui:"}
            texto={item.text}
            tom={item.kind}
          />
        ),
      )}
    </div>
  );
}

function CartaoCodigo({
  code,
  description,
  unit,
  unitPrice,
  score,
  inContract,
  unitCompatible,
  selected,
  onChoose,
}: {
  code: string;
  description: string;
  unit: string;
  unitPrice: string;
  score: number | null;
  inContract: boolean | null;
  unitCompatible: boolean | null;
  selected: boolean;
  onChoose: () => void;
}) {
  return (
    <li className={`codigo-card ${selected ? "escolhido" : ""}`}>
      <div className="codigo-topo">
        <span className="codigo-code">{code}</span>
        <span className="codigo-preco">
          {formatMoneyText(unitPrice)} / {unitLabel(unit)}
        </span>
      </div>
      {/* Descrição inteira, com rolagem própria: cortá-la esconderia justamente a
          diferença entre fornecer e executar. */}
      <p className="codigo-descricao">{description}</p>
      <div className="codigo-selos">
        <SeloExecucao description={description} />
        {unitCompatible === null ? null : (
          <span className={`selo ${unitCompatible ? "selo-ok" : "selo-atencao"}`}>
            {unitCompatible ? "unidade compatível" : "unidade diferente da do item"}
          </span>
        )}
        {inContract === null ? null : (
          <span className={`selo ${inContract ? "selo-ok" : "selo-atencao"}`}>
            {inContract ? "no contrato" : "fora do contrato"}
          </span>
        )}
        {score === null ? null : (
          <span className="selo selo-neutro">
            afinidade lexical {score.toFixed(2).replace(".", ",")}
          </span>
        )}
      </div>
      <Inclusoes description={description} />
      <button type="button" className="botao-secundario" onClick={onChoose}>
        {selected ? "Escolhido" : "Escolher este código"}
      </button>
    </li>
  );
}

/**
 * Estado da extração automática da prancha na etapa "Prancha". `done` fica discreto
 * (uma linha com modelo e custo); `running`/`failed`/`unavailable` ganham mais destaque,
 * porque são os estados em que o orçamentista precisa agir ou esperar. O texto de
 * erro/aviso é o que o servidor já escreveu em `extracao.message` — língua de obra,
 * pronta; a tela não reescreve.
 */
function EstadoExtracao({
  extracao,
  onRetry,
  retrying,
}: {
  extracao: ExtractionState;
  onRetry: () => void;
  retrying: boolean;
}) {
  return (
    <div className="extracao-status">
      {extracao.status === "running" ? (
        <p className="dica" role="status">
          Lendo a legenda da prancha… isso pode levar alguns instantes.
        </p>
      ) : extracao.status === "done" ? (
        <p className="dica">
          Extração concluída
          {extracao.execution === null ? "" : ` — modelo ${extracao.execution.model_id}`}
          {extracao.execution?.estimated_cost_usd == null
            ? ""
            : `, custo estimado US$ ${formatDecimalText(
                extracao.execution.estimated_cost_usd,
              )}`}
          .
        </p>
      ) : extracao.status === "failed" ? (
        <>
          <p className="banner-erro" role="alert">
            {extracao.message ?? "A extração automática falhou."}
            {extracao.error_code === null ? null : (
              <>
                {" "}
                <span className="mono">({extracao.error_code})</span>
              </>
            )}
          </p>
          <button
            type="button"
            className="botao-secundario"
            onClick={onRetry}
            disabled={retrying}
          >
            Tentar extração novamente
          </button>
        </>
      ) : extracao.status === "unavailable" ? (
        <>
          <p className="aviso-fixo aviso-inline">
            {extracao.message ?? "Extração automática indisponível no servidor."}
          </p>
          <button
            type="button"
            className="botao-secundario"
            onClick={onRetry}
            disabled={retrying}
          >
            Tentar extração novamente
          </button>
        </>
      ) : (
        // `idle` com prancha já ingerida: caso raro (rodada montada fora do upload da
        // tela), mas sem botão o orçamentista ficaria sem saída dentro da UI.
        <>
          <p className="dica">
            Prancha ingerida; a extração automática ainda não foi disparada.
          </p>
          <button
            type="button"
            className="botao-secundario"
            onClick={onRetry}
            disabled={retrying}
          >
            Disparar extração automática
          </button>
        </>
      )}
      {extracao.notes.map((note) => (
        <p key={note} className="dica">
          {note}
        </p>
      ))}
    </div>
  );
}

export function App() {
  // Sessão do modo hospedado (ADR-0026). Sem OIDC configurado — o servidor local na
  // máquina do operador — `oidcAtivo` é `false` e tudo abaixo é inerte: nenhuma tela de
  // login, nenhum header a mais, exatamente o comportamento do ADR-0020.
  const oidcAtivo = isOidcConfigured();
  const [session, setSession] = useState<User | null>(null);
  // `false` só enquanto a sessão armazenada ainda não foi lida: sem isto, a volta do
  // redirect pisca "Entrar" antes de reconhecer quem já entrou.
  const [sessionChecked, setSessionChecked] = useState(!oidcAtivo);
  const [authError, setAuthError] = useState<string | null>(null);
  // O token é lido no instante da chamada (o `automaticSilentRenew` troca o objeto da
  // sessão sem avisar quem já capturou o valor), então o provider consulta esta ref.
  const sessionRef = useRef<User | null>(null);

  // Estado servido pela rodada; nada aqui é derivado de cálculo local.
  const [state, setState] = useState<RunState | null>(null);
  const [takeoff, setTakeoff] = useState<TakeoffResponse | null>(null);
  const [suggestions, setSuggestions] = useState<CodeSuggestionSet | null>(null);
  // Digest da shortlist lida; é ele que o recompute cita como base (guarda otimista).
  // `null` significa "esta rodada ainda não tem shortlist", não "não sei o digest": o
  // servidor recusa digest citado sem artefato e artefato sem digest citado.
  const [suggestionsSha256, setSuggestionsSha256] = useState<string | null>(null);
  const [codes, setCodes] = useState<CodesResponse | null>(null);
  const [bulletin, setBulletin] = useState<BulletinResponse | null>(null);
  const [dossier, setDossier] = useState<DossierResponse | null>(null);

  const [loading, setLoading] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [alertMessage, setAlertMessage] = useState<string | null>(null);
  const [stateMoved, setStateMoved] = useState(false);
  const [toast, setToast] = useState<string | null>(null);
  const [openStep, setOpenStep] = useState<EtapaId | null>(null);

  // Prancha (upload e extração automática).
  const [uploadFile, setUploadFile] = useState<File | null>(null);

  // Revisão do takeoff.
  const [selectedItemId, setSelectedItemId] = useState("");
  const [decision, setDecision] = useState(EMPTY_DECISION);
  const [zoom, setZoom] = useState(MIN_ZOOM);
  const [imageSize, setImageSize] = useState<{ width: number; height: number } | null>(
    null,
  );
  const canvasRef = useRef<HTMLDivElement | null>(null);
  const panOrigin = useRef<PanOrigin | null>(null);
  const [panning, setPanning] = useState(false);
  // `src` da prancha. No caminho local é a URL direta do servidor, como sempre foi; no
  // hospedado ela nasce `null` e vira um object URL depois da busca autenticada, porque
  // `<img src>` não leva o `Authorization` da sessão (ver o efeito mais abaixo).
  const [pranchaSrc, setPranchaSrc] = useState<string | null>(() =>
    plateImageSource(oidcAtivo),
  );
  // Prancha limpa por padrão: nenhuma marcação sobre a imagem que o projetista enviou.
  // Só o item selecionado ganha o retângulo fino, sem número. "Mostrar marcações"
  // revela retângulo + número de todos, para auditoria. Estado de componente, nunca em
  // storage — reabrir a ferramenta volta ao padrão limpo.
  const [mostrarMarcacoes, setMostrarMarcacoes] = useState(false);

  // Códigos.
  const [selectedPendingId, setSelectedPendingId] = useState("");
  const [codeChoice, setCodeChoice] = useState<CodeChoice | null>(null);
  const [codeNote, setCodeNote] = useState("");
  const [query, setQuery] = useState("");
  const [searchResult, setSearchResult] = useState<CatalogSearchResponse | null>(null);
  // Busca incremental: ela nunca toca `submitting` (cada tecla congelaria a tela inteira)
  // e nunca escreve no alerta global — erro transitório de digitação vira aviso ao lado
  // do campo, do lado de quem está digitando.
  const [buscando, setBuscando] = useState(false);
  const [buscaAviso, setBuscaAviso] = useState<string | null>(null);
  const buscaAbortRef = useRef<AbortController | null>(null);
  const buscaTimerRef = useRef<number | null>(null);
  // Último código confirmado nesta sessão: a decisão colapsa o cartão do item (ele some
  // da lista de pendentes), e sem isto a descrição completa e os chips escolhidos
  // desapareciam da tela no exato momento em que a decisão foi tomada.
  const [ultimoCodigoConfirmado, setUltimoCodigoConfirmado] = useState<{
    itemLabel: string;
    code: string;
    description: string;
    note: string;
  } | null>(null);
  // Cache em memória, por código: descrição completa dos códigos já confirmados
  // (persistentes entre recarregamentos, ao contrário de `ultimoCodigoConfirmado`).
  // `undefined` (chave ausente) = ainda não buscado; `null` = buscado e não encontrado
  // no catálogo desta rodada; nunca busca de novo um código que já está aqui.
  const [assignmentDescriptions, setAssignmentDescriptions] = useState<
    Record<string, string | null>
  >({});

  // Boletim.
  const [calcForm, setCalcForm] = useState(EMPTY_CALC);

  useEffect(() => {
    if (toast === null) {
      return;
    }
    const timer = setTimeout(() => setToast(null), TOAST_MS);
    return () => clearTimeout(timer);
  }, [toast]);

  useEffect(() => {
    sessionRef.current = session;
  }, [session]);

  // Liga o `Authorization` das chamadas à sessão desta tela e o desliga ao desmontar. Sem
  // OIDC nenhum provider é registrado: o módulo de API continua sem mandar header.
  useEffect(() => {
    if (!oidcAtivo) {
      return;
    }
    setAccessTokenProvider(() => sessionRef.current?.access_token ?? null);
    return () => setAccessTokenProvider(null);
  }, [oidcAtivo]);

  // Lê a sessão armazenada (ou fecha a volta do redirect) e acompanha a renovação
  // silenciosa. Falha aqui é de OIDC, e é dita como tal — erro de servidor tem outra causa
  // e outro lugar na tela.
  useEffect(() => {
    if (!oidcAtivo) {
      return;
    }
    const parar = onSessionRenewed((renewed) => setSession(renewed));
    void (async () => {
      try {
        setSession(await readSession());
      } catch (error) {
        setAuthError(
          `Não foi possível validar a sessão: ${
            error instanceof Error ? error.message : String(error)
          }`,
        );
      } finally {
        setSessionChecked(true);
      }
    })();
    return parar;
  }, [oidcAtivo]);

  const carregarEstado = useCallback(async () => {
    setLoading(true);
    try {
      const nextState = await getState();
      setState(nextState);
      setStateMoved(false);
      setAlertMessage(null);
      if (nextState.takeoff.present) {
        setTakeoff(await getTakeoff());
        setCodes(await getCodes());
      } else {
        setTakeoff(null);
        setCodes(null);
      }
      // A shortlist só é buscada quando já existe em disco: a primeira chamada de
      // `GET /suggestions` **calcula e grava** o artefato, e isso é ato do orçamentista,
      // não efeito colateral de abrir a tela. O digest vem da mesma resposta que a
      // shortlist exibida — é ele, e não o do `/state`, que descreve o que esta tela leu.
      if (nextState.codes.suggestions_present) {
        const response = await getSuggestions();
        setSuggestions(response.suggestions);
        setSuggestionsSha256(response.suggestions_sha256);
      } else {
        setSuggestions(null);
        setSuggestionsSha256(null);
      }
      setBulletin(nextState.bulletin.present ? await getBulletin() : null);
      setDossier(nextState.dossier.present ? await getDossier() : null);
    } catch (error) {
      setAlertMessage(describeError(error));
    } finally {
      setLoading(false);
    }
  }, []);

  // No modo hospedado a rodada só é lida depois que existe sessão: chamar o servidor sem
  // token devolveria 401 e escreveria um alerta de erro na tela de quem ainda nem entrou.
  // `autenticado` é booleano de propósito — a renovação silenciosa troca o objeto da
  // sessão, e depender dele recarregaria a rodada a cada renovação.
  const autenticado = !oidcAtivo || session !== null;

  useEffect(() => {
    if (!autenticado) {
      return;
    }
    void carregarEstado();
  }, [autenticado, carregarEstado]);

  /**
   * Envia o PDF da prancha (`POST /plates`). O consentimento é o próprio clique — a
   * decisão de que a leitura automática por IA é uma chamada paga já foi tomada pelo
   * usuário e está declarada no aviso ao lado do botão, não numa segunda pergunta.
   */
  const enviarPrancha = async () => {
    if (uploadFile === null) {
      return;
    }
    setSubmitting(true);
    setAlertMessage(null);
    try {
      const nextState = await uploadPlate(uploadFile);
      setState(nextState);
      setUploadFile(null);
      setToast("Prancha enviada; a leitura automática da legenda começou.");
    } catch (error) {
      setAlertMessage(describeError(error));
    } finally {
      setSubmitting(false);
    }
  };

  /** Re-dispara a extração de uma prancha já ingerida (`POST /plates/extract`). */
  const tentarExtracaoNovamente = async () => {
    setSubmitting(true);
    setAlertMessage(null);
    try {
      const nextState = await extractPlate();
      setState(nextState);
      setToast("Nova tentativa de extração automática iniciada.");
    } catch (error) {
      setAlertMessage(describeError(error));
    } finally {
      setSubmitting(false);
    }
  };

  /** Um ciclo do poll: relê o `/state` e, se a extração acabou de publicar o takeoff,
   * carrega o pacote e leva a tela direto para a revisão — sem clique nenhum. */
  const pollExtracao = useCallback(async () => {
    try {
      const nextState = await getState();
      setState(nextState);
      if (nextState.extracao.status !== "running" && nextState.takeoff.present) {
        setTakeoff(await getTakeoff());
        setCodes(await getCodes());
        setOpenStep("revisao");
      }
    } catch (error) {
      setAlertMessage(describeError(error));
    }
  }, []);

  // Poll do `/state` a cada ~3s enquanto a extração automática está `running`; para
  // sozinho assim que ela fecha (`done`, `failed` ou `unavailable`), porque a condição
  // do efeito deixa de valer no próximo render.
  useEffect(() => {
    if (state?.extracao.status !== "running") {
      return;
    }
    const timer = setInterval(() => void pollExtracao(), EXTRACTION_POLL_MS);
    return () => clearInterval(timer);
  }, [state?.extracao.status, pollExtracao]);

  // Zoom pela roda precisa de listener não passivo: sem `preventDefault` a página rola
  // junto e o desenho foge da mão.
  useEffect(() => {
    const canvas = canvasRef.current;
    if (canvas === null) {
      return;
    }
    const onWheel = (event: WheelEvent) => {
      event.preventDefault();
      setZoom((current) => zoomAfterWheel(current, event.deltaY));
    };
    canvas.addEventListener("wheel", onWheel, { passive: false });
    return () => canvas.removeEventListener("wheel", onWheel);
    // O canvas só existe na etapa de revisão: a etapa visível entra nas dependências
    // para o listener nascer junto com o elemento, e não uma navegação depois.
  }, [takeoff, openStep]);

  // Descrição completa de cada código já confirmado, para a lista persistente de
  // decisões sobreviver ao recarregamento (ao contrário de `ultimoCodigoConfirmado`,
  // que só existe nesta sessão). Busca por código exato no catálogo desta rodada; nunca
  // repete a busca de um código que já está no cache (achado ou não achado).
  //
  // Braço lexical fixado: esta varredura é automática (nasce de abrir a etapa, não de um
  // gesto) e roda uma consulta por código confirmado. O braço semântico só acrescentaria
  // vizinhos sem o código procurado — pagando embedding e escrevendo cache de consulta
  // por um resultado que o léxico já dá melhor, porque o casamento aqui é exato.
  useEffect(() => {
    const confirmedCodes = (codes?.assignments?.assignments ?? [])
      .filter(isConfirmedWithCode)
      .map((assignment) => assignment.code);
    const pendentes = Array.from(new Set(confirmedCodes)).filter(
      (code) => !(code in assignmentDescriptions),
    );
    if (pendentes.length === 0) {
      return;
    }
    let cancelado = false;
    void (async () => {
      for (const code of pendentes) {
        let description: string | null;
        try {
          const response = await searchCatalog(codeSearchTerm(code), 20, {
            arm: "lexical",
          });
          // Casamento pelo código EXATO: a busca pode devolver vários candidatos com o
          // mesmo prefixo, e mostrar a descrição de um código parecido seria mentir
          // sobre o que este código específico inclui.
          description = response.results.find((result) => result.code === code)?.description ?? null;
        } catch {
          description = null;
        }
        if (cancelado) {
          return;
        }
        setAssignmentDescriptions((current) => ({ ...current, [code]: description }));
      }
    })();
    return () => {
      cancelado = true;
    };
  }, [codes, assignmentDescriptions]);

  // Busca enquanto se digita, sempre pelo braço LEXICAL fixado (`arm: "lexical"`): a
  // consulta a cada tecla não pode virar chamada paga de embedding nem escrita de cache.
  // O braço híbrido continua atrás do gesto explícito (Enter/"Buscar"), em
  // `buscarNoCatalogo`. Aqui só entram consultas acima do limiar (`consultaIncremental`),
  // com debounce, e a resposta que chega depois de outra tecla é descartada — lista de
  // catálogo trocando sozinha por ordem de rede seria pior que não ter busca incremental.
  useEffect(() => {
    const consulta = consultaIncremental(query);
    if (consulta === null) {
      if (buscaTimerRef.current !== null) {
        window.clearTimeout(buscaTimerRef.current);
        buscaTimerRef.current = null;
      }
      buscaAbortRef.current?.abort();
      buscaAbortRef.current = null;
      setBuscando(false);
      setBuscaAviso(null);
      // Caixa esvaziada limpa a lista; caixa só encurtada mantém o último resultado,
      // que ainda é o que o servidor respondeu para o que está escrito antes.
      if (query.trim() === "") {
        setSearchResult(null);
      }
      return;
    }
    const timer = window.setTimeout(() => {
      buscaTimerRef.current = null;
      buscaAbortRef.current?.abort();
      const controller = new AbortController();
      buscaAbortRef.current = controller;
      setBuscando(true);
      void (async () => {
        try {
          const response = await searchCatalog(consulta, 20, {
            arm: "lexical",
            signal: controller.signal,
          });
          if (controller.signal.aborted) {
            return;
          }
          setSearchResult(response);
          setBuscaAviso(null);
        } catch (error) {
          if (isAbortError(error)) {
            return;
          }
          setBuscaAviso(describeError(error));
        } finally {
          // Só a consulta ainda corrente desliga o indicador: a que foi abortada por uma
          // tecla mais nova não pode apagar o "Buscando…" da que a substituiu.
          if (buscaAbortRef.current === controller) {
            buscaAbortRef.current = null;
            setBuscando(false);
          }
        }
      })();
    }, BUSCA_DEBOUNCE_MS);
    buscaTimerRef.current = timer;
    return () => window.clearTimeout(timer);
  }, [query]);

  const jornada = useMemo(() => derivarEtapas(state), [state]);
  const etapaVisivel: EtapaId | "rodada" = openStep === null ? "rodada" : openStep;
  const prancha = state?.images.plate ?? null;
  // Nome do arquivo servido: é ele que muda quando a rodada troca de prancha, e é por isso
  // que ele — e não o objeto de estado inteiro — decide quando rebuscar a imagem.
  const pranchaFilename = prancha?.present === true ? prancha.filename : null;

  // Modo hospedado (ADR-0026): a imagem vem por `fetch` com o mesmo `Authorization` das
  // outras chamadas e é exibida como object URL, revogado ao trocar de prancha ou
  // desmontar — object URL sobrevive ao componente e uma revisão abre a prancha muitas
  // vezes. Sem OIDC nada disso roda: o `src` continua sendo a URL direta do servidor local,
  // sem nenhuma requisição a mais.
  useEffect(() => {
    if (!oidcAtivo) {
      return;
    }
    if (!autenticado || pranchaFilename === null) {
      setPranchaSrc(null);
      return;
    }
    let cancelado = false;
    let criado: string | null = null;
    void (async () => {
      try {
        const url = await fetchImageObjectUrl(PLATE_IMAGE_PATH);
        if (cancelado) {
          URL.revokeObjectURL(url);
          return;
        }
        criado = url;
        setPranchaSrc(url);
      } catch (error) {
        setPranchaSrc(null);
        setAlertMessage(describeError(error));
      }
    })();
    return () => {
      cancelado = true;
      if (criado !== null) {
        URL.revokeObjectURL(criado);
      }
    };
  }, [oidcAtivo, autenticado, pranchaFilename]);

  const items = takeoff?.packet.items ?? [];
  const selectedItem = items.find((item) => item.id === selectedItemId) ?? null;
  const pendingItems = codes?.pending_items ?? [];
  const selectedPending =
    pendingItems.find((item) => item.item_id === selectedPendingId) ?? null;

  const atualizarEstado = useCallback(async () => {
    try {
      setState(await getState());
    } catch (error) {
      setAlertMessage(describeError(error));
    }
  }, []);

  const abrirEtapa = (etapa: Etapa) => {
    if (etapa.status === "blocked") {
      return;
    }
    setOpenStep(etapa.id);
  };

  const selecionarItem = (item: TakeoffItem) => {
    setSelectedItemId(item.id);
    setDecision(EMPTY_DECISION);
  };

  const startPan = (event: ReactPointerEvent<HTMLDivElement>) => {
    const canvas = canvasRef.current;
    if (canvas === null || event.button !== 0) {
      return;
    }
    panOrigin.current = {
      pointerX: event.clientX,
      pointerY: event.clientY,
      scrollLeft: canvas.scrollLeft,
      scrollTop: canvas.scrollTop,
    };
    setPanning(true);
  };

  const movePan = (event: ReactPointerEvent<HTMLDivElement>) => {
    const canvas = canvasRef.current;
    const origin = panOrigin.current;
    if (canvas === null || origin === null) {
      return;
    }
    const offset = panScrollOffset(origin, event.clientX, event.clientY);
    canvas.scrollLeft = offset.scrollLeft;
    canvas.scrollTop = offset.scrollTop;
  };

  const endPan = () => {
    panOrigin.current = null;
    setPanning(false);
  };

  const quantidadeParaServidor = parseQuantityInput(decision.quantity);
  const quantidadeInvalida =
    decision.quantity.trim().length > 0 && quantidadeParaServidor === null;
  const exigeQuantidade =
    decision.action === "confirm" && selectedItem?.status === "ambiguous";
  const decisaoBloqueada =
    submitting ||
    selectedItem === null ||
    decision.action === "" ||
    quantidadeInvalida ||
    (exigeQuantidade && quantidadeParaServidor === null);

  const enviarDecisao = async () => {
    if (selectedItem === null || takeoff === null || decision.action === "") {
      return;
    }
    setSubmitting(true);
    setAlertMessage(null);
    try {
      // Correção de dado só viaja com `confirm`: uma quantidade digitada e depois
      // abandonada ao trocar para "rejeitar" alteraria o item que está sendo descartado.
      const correcoes =
        decision.action === "confirm"
          ? {
              quantity: quantidadeParaServidor ?? undefined,
              unit: decision.unit,
              itemNote: decision.itemNote,
            }
          : {};
      const response = await postTakeoffDecision({
        itemId: selectedItem.id,
        action: decision.action,
        basePacketSha256: takeoff.packet_sha256,
        note: decision.note,
        ...correcoes,
      });
      setTakeoff({ packet: response.packet, packet_sha256: response.packet_sha256 });
      setDecision(EMPTY_DECISION);
      setStateMoved(false);
      setToast(
        `${selectedItem.label}: item ${
          decision.action === "confirm" ? "confirmado" : "rejeitado"
        }. Faltam ${response.pending} de ${response.items}.`,
      );
      if (response.notes.length > 0) {
        setAlertMessage(response.notes.join(" "));
      }
      await atualizarEstado();
      setCodes(await getCodes());
    } catch (error) {
      // O conflito tem banner próprio, com o botão de recarregar; repetir a mesma frase
      // no alerta genérico só empilharia ruído sobre a tela.
      if (isStateMoved(error)) {
        setStateMoved(true);
      } else {
        setAlertMessage(describeError(error));
      }
    } finally {
      setSubmitting(false);
    }
  };

  const calcularShortlist = async () => {
    setSubmitting(true);
    setAlertMessage(null);
    try {
      const response = await getSuggestions();
      setSuggestions(response.suggestions);
      setSuggestionsSha256(response.suggestions_sha256);
      // Híbrida ou lexical é o que a resposta declara (`matching`), não o que a tela
      // supõe: a mesma rodada muda de braço conforme índice, teto de gasto e credencial.
      const braco = response.matching === "hybrid" ? "híbrida" : "lexical";
      setToast(
        response.computed
          ? `Shortlist ${braco} calculada e gravada na rodada.`
          : `Shortlist ${braco} carregada da rodada.`,
      );
      await atualizarEstado();
    } catch (error) {
      setAlertMessage(describeError(error));
    } finally {
      setSubmitting(false);
    }
  };

  /**
   * Recompute explícito da shortlist (`POST /suggestions/recompute`). Sobrescreve o
   * artefato da rodada, então é gesto do orçamentista e nunca efeito de abrir a tela. O
   * digest-base lido viaja junto: rodada que andou entre a leitura e o clique vira o
   * banner de conflito de sempre, e shortlist com refino pago é recusada pelo servidor
   * (`LOCAL_SUGGESTIONS_REFINED`) em vez de perder o lineage da chamada paga.
   */
  const recalcularShortlist = async () => {
    setSubmitting(true);
    setAlertMessage(null);
    try {
      const response = await postSuggestionsRecompute(suggestionsSha256);
      setSuggestions(response.suggestions);
      setSuggestionsSha256(response.suggestions_sha256);
      setToast(
        response.matching === "hybrid"
          ? "Shortlist híbrida recalculada e regravada na rodada."
          : "Shortlist lexical recalculada e regravada na rodada.",
      );
      await atualizarEstado();
    } catch (error) {
      // O conflito tem banner próprio, com o botão de recarregar; repetir a mesma frase
      // no alerta genérico só empilharia ruído sobre a tela.
      if (isStateMoved(error)) {
        setStateMoved(true);
      } else {
        setAlertMessage(describeError(error));
      }
    } finally {
      setSubmitting(false);
    }
  };

  /**
   * Busca completa, pedida por Enter ou pelo botão: sem `arm`, ou seja, híbrida quando a
   * rodada tem índice, teto de gasto e credencial. O gasto pequeno da consulta nova fica
   * atrás deste gesto explícito, nunca da digitação.
   */
  const buscarNoCatalogo = async () => {
    // Cancela o lexical em voo: chegando depois, ele sobrescreveria com menos resultados
    // justamente a busca completa que acabou de ser pedida.
    if (buscaTimerRef.current !== null) {
      window.clearTimeout(buscaTimerRef.current);
      buscaTimerRef.current = null;
    }
    buscaAbortRef.current?.abort();
    buscaAbortRef.current = null;
    setBuscando(false);
    setBuscaAviso(null);
    setSubmitting(true);
    setAlertMessage(null);
    try {
      setSearchResult(await searchCatalog(query));
    } catch (error) {
      setSearchResult(null);
      setAlertMessage(describeError(error));
    } finally {
      setSubmitting(false);
    }
  };

  const divergenciaDeUnidade =
    selectedPending !== null &&
    codeChoice !== null &&
    unidadesDivergem(selectedPending.unit, codeChoice);
  const notaObrigatoria = divergenciaDeUnidade;

  const decidirCodigo = async (action: "confirm" | "reject") => {
    if (selectedPending === null || codes === null) {
      return;
    }
    setSubmitting(true);
    setAlertMessage(null);
    try {
      const response = await postCodeDecision({
        itemId: selectedPending.item_id,
        action,
        code: action === "confirm" ? codeChoice?.code : undefined,
        note: codeNote,
        baseAssignmentsSha256: codes.assignments_sha256,
      });
      // Captura o código e a descrição escolhidos ANTES de limpar `codeChoice`: é o
      // único lugar onde a descrição completa deste código está disponível na tela, já
      // que a lista de itens pendentes não vai mais mostrar este item confirmado.
      if (action === "confirm" && codeChoice !== null) {
        setUltimoCodigoConfirmado({
          itemLabel: selectedPending.label,
          code: codeChoice.code,
          description: codeChoice.description,
          note: codeNote.trim(),
        });
      }
      setCodes(response);
      setCodeChoice(null);
      setCodeNote("");
      setSelectedPendingId("");
      setStateMoved(false);
      setToast(
        action === "confirm"
          ? `${selectedPending.label}: código ${codeChoice?.code ?? ""} confirmado.`
          : `${selectedPending.label}: registrado como candidato a aditivo.`,
      );
      await atualizarEstado();
    } catch (error) {
      // O conflito tem banner próprio, com o botão de recarregar; repetir a mesma frase
      // no alerta genérico só empilharia ruído sobre a tela.
      if (isStateMoved(error)) {
        setStateMoved(true);
      } else {
        setAlertMessage(describeError(error));
      }
    } finally {
      setSubmitting(false);
    }
  };

  const montarBoletim = async () => {
    setSubmitting(true);
    setAlertMessage(null);
    try {
      const response = await postCalcBuild(calcForm);
      setBulletin(response);
      setToast("Boletim e memória gravados na rodada, sem aprovação.");
      await atualizarEstado();
    } catch (error) {
      setAlertMessage(describeError(error));
    } finally {
      setSubmitting(false);
    }
  };

  /**
   * Gera o dossiê do aditivo (`POST /dossier/build`). Mesma condição de elegibilidade do
   * botão de montar boletim (`jornada` → etapa `boletim` não bloqueada): o dossiê é o
   * outro artefato de FECHAMENTO da rodada e exige a mesma revisão completa com todo
   * código decidido.
   */
  const gerarDossie = async () => {
    setSubmitting(true);
    setAlertMessage(null);
    try {
      const response = await postDossierBuild();
      setDossier(response);
      setToast("Dossiê do aditivo gravado na rodada.");
      await atualizarEstado();
    } catch (error) {
      if (isStateMoved(error)) {
        setStateMoved(true);
      } else {
        setAlertMessage(describeError(error));
      }
    } finally {
      setSubmitting(false);
    }
  };

  const boletimEtapa = jornada.etapas.find((etapa) => etapa.id === "boletim") ?? null;
  const dossieDisponivel = boletimEtapa !== null && boletimEtapa.status !== "blocked";

  const shortlist =
    selectedPending === null
      ? []
      : (suggestions?.suggestions.find(
          (suggestion) => suggestion.item_id === selectedPending.item_id,
        )?.candidates ?? []);
  const semCandidato =
    selectedPending !== null &&
    (suggestions?.unmatched_item_ids.includes(selectedPending.item_id) ?? false);

  const labelDoItem = (itemId: string): string =>
    items.find((item) => item.id === itemId)?.label ?? itemId;

  const rejeitados = (codes?.assignments?.assignments ?? []).filter(
    (assignment) => assignment.status === "rejected",
  );
  const confirmados = (codes?.assignments?.assignments ?? []).filter(
    (assignment) => assignment.status === "confirmed",
  );
  const semCandidatoPendentes = (suggestions?.unmatched_item_ids ?? []).filter(
    (itemId) => pendingItems.some((item) => item.item_id === itemId),
  );

  // Porta do modo hospedado: sem sessão, nada da rodada é lido nem exibido — nem nome de
  // obra, nem caminho de artefato. Todos os hooks acima já rodaram, então esta saída
  // antecipada não altera a ordem de nenhum deles.
  if (!autenticado) {
    return (
      <div className="app-shell">
        <header className="topbar">
          <div>
            <span className="eyebrow">HOMOLOGAÇÃO DA MEDIÇÃO</span>
            <h1>{sessionChecked ? "Entrar" : "Verificando a sessão…"}</h1>
            <p className="topbar-meta">
              A rodada só é lida com sessão autenticada.
            </p>
          </div>
        </header>
        <div className="conteudo">
          <section className="painel" aria-labelledby="titulo-entrar">
            <h2 id="titulo-entrar">Sessão da orçamentista</h2>
            <p>
              Entre com a identidade do ambiente para revisar o takeoff, confirmar os
              códigos e montar o boletim. A decisão continua sendo carimbada pelo
              servidor, agora a partir do seu token.
            </p>
            {authError === null ? null : (
              <p className="banner-erro" role="alert">
                {authError}
              </p>
            )}
            <div className="acoes-linha">
              <button
                type="button"
                className="botao-primario"
                onClick={() => void signIn()}
                disabled={!sessionChecked}
              >
                Entrar
              </button>
            </div>
          </section>
        </div>
      </div>
    );
  }

  return (
    <div className="app-shell">
      <header className="topbar">
        <div>
          <span className="eyebrow">HOMOLOGAÇÃO LOCAL DA MEDIÇÃO</span>
          {/* Nome da rodada é a última pasta do caminho; o caminho inteiro fica logo
              abaixo, porque é ele que identifica de qual diretório saem os artefatos. */}
          <h1>{state === null ? "Rodada não carregada" : nomeDaRodada(state.root)}</h1>
          {state === null ? null : (
            <p className="topbar-meta mono">{state.root}</p>
          )}
          <p className="topbar-meta">
            {state === null
              ? "Nenhum estado lido do servidor local ainda."
              : `Revisor: ${state.reviewer_id} (${state.reviewer_role}) · servidor ${state.server_version}`}
          </p>
        </div>
        {/* Aviso permanente: ele não fecha, não recolhe e não expira. */}
        <p className="aviso-fixo">{avisoDaFerramenta(oidcAtivo)}</p>
        <div className="topbar-acoes">
          {/* As duas SPAs só convivem na mesma origem quando servidas em subrota; em
              desenvolvimento cada uma tem a sua porta e o link levaria a lugar nenhum. */}
          {import.meta.env.BASE_URL === "/" ? null : (
            <a className="topbar-link" href="/revisao/">
              Revisão
            </a>
          )}
          {session === null ? null : (
            <>
              <span className="topbar-meta">
                Sessão: {session.profile.preferred_username ?? session.profile.sub}
              </span>
              <button
                type="button"
                className="topbar-link topbar-link-botao"
                onClick={() => void signOut()}
              >
                Sair
              </button>
            </>
          )}
        </div>
      </header>

      <nav className="etapas" aria-label="Etapas da homologação">
        <button
          type="button"
          className={`etapa-tab ${etapaVisivel === "rodada" ? "ativa" : ""}`}
          onClick={() => setOpenStep(null)}
          aria-current={etapaVisivel === "rodada"}
        >
          Rodada
        </button>
        {jornada.etapas.map((etapa) => (
          <button
            key={etapa.id}
            type="button"
            className={`etapa-tab ${etapaVisivel === etapa.id ? "ativa" : ""} ${
              etapa.status
            }`}
            onClick={() => abrirEtapa(etapa)}
            disabled={etapa.status === "blocked"}
            aria-current={etapaVisivel === etapa.id}
            title={etapa.blockedReason ?? etapa.summary}
          >
            {etapa.title} · {etapaStatusLabel(etapa.status)}
          </button>
        ))}
        <button
          type="button"
          className="botao-secundario recarregar"
          onClick={() => void carregarEstado()}
          disabled={loading}
        >
          {loading ? "Recarregando…" : "Recarregar estado atual"}
        </button>
      </nav>

      {stateMoved ? (
        <div className="banner-conflito" role="alert">
          <p>
            O estado da rodada mudou depois desta leitura — outro processo mexeu nos
            arquivos. Nada foi gravado. Recarregue o estado atual e decida de novo; o que
            você escreveu no formulário continua aqui.
          </p>
          <button
            type="button"
            className="botao-primario"
            onClick={() => void carregarEstado()}
          >
            Recarregar estado atual
          </button>
        </div>
      ) : null}

      {alertMessage === null ? null : (
        <p className="banner-erro" role="alert">
          {alertMessage}
        </p>
      )}

      {toast === null ? null : (
        <p className="banner-sucesso" role="status">
          {toast}
        </p>
      )}

      <main className="conteudo">
        {etapaVisivel === "rodada" ? (
          <section className="painel" aria-label="Situação da rodada">
            <h2>Situação da rodada</h2>
            <ul className="cartoes">
              {jornada.etapas.map((etapa) => (
                <li key={etapa.id} className={`cartao ${etapa.status}`}>
                  <h3>{etapa.title}</h3>
                  <p className="cartao-status">
                    Etapa {etapaStatusLabel(etapa.status)}
                  </p>
                  <p>{etapa.summary}</p>
                  {etapa.blockedReason === undefined ? null : (
                    <p className="cartao-motivo">Bloqueada porque {etapa.blockedReason}.</p>
                  )}
                  <button
                    type="button"
                    className="botao-secundario"
                    onClick={() => abrirEtapa(etapa)}
                    disabled={etapa.status === "blocked"}
                  >
                    Abrir {etapa.title.toLowerCase()}
                  </button>
                </li>
              ))}
            </ul>

            {state === null ? (
              <p>
                O estado da rodada ainda não foi lido. Suba o servidor local com{" "}
                <code>croquito-valuation serve --root &lt;rodada&gt; --reviewer &lt;id&gt;</code>{" "}
                e use “Recarregar estado atual”.
              </p>
            ) : (
              <div className="artefatos">
                <h3>Artefatos da rodada</h3>
                <ul>
                  {Object.entries(state.artifacts).map(([name, digest]) => (
                    <li key={name}>
                      <span className="mono">{name}</span>{" "}
                      <span className="digest" title={digest}>
                        sha256 {shortDigest(digest)}
                      </span>
                    </li>
                  ))}
                </ul>
                <p>
                  Imagem da prancha:{" "}
                  {state.images.plate.present
                    ? state.images.plate.filename
                    : "ausente no diretório"}{" "}
                  · overlay: {state.images.overlay.present ? "gravado" : "ausente"}.
                </p>
              </div>
            )}
          </section>
        ) : null}

        {etapaVisivel === "prancha" ? (
          <section className="painel" aria-label="Prancha do projetista">
            <h2>Prancha do projetista</h2>
            {state === null ? (
              <p>O estado da rodada ainda não foi lido.</p>
            ) : state.extracao.plate_pdf_present ? (
              <EstadoExtracao
                extracao={state.extracao}
                onRetry={() => void tentarExtracaoNovamente()}
                retrying={submitting}
              />
            ) : (
              <form
                className="formulario"
                onSubmit={(event) => {
                  event.preventDefault();
                  void enviarPrancha();
                }}
              >
                <p>Nenhuma prancha enviada nesta rodada ainda.</p>
                <label className="campo">
                  Prancha do projetista (PDF)
                  <input
                    type="file"
                    accept=".pdf,application/pdf"
                    onChange={(event) => setUploadFile(event.target.files?.[0] ?? null)}
                  />
                </label>
                <p className="aviso-fixo aviso-inline">
                  Ao enviar, a leitura da legenda é feita automaticamente por IA (chamada
                  paga configurada no servidor).
                </p>
                <button
                  type="submit"
                  className="botao-primario"
                  disabled={uploadFile === null || submitting}
                >
                  {submitting ? "Enviando…" : "Enviar prancha"}
                </button>
              </form>
            )}
          </section>
        ) : null}

        {etapaVisivel === "revisao" && takeoff !== null ? (
          <section className="workspace" aria-label="Revisão do takeoff">
            <article className="painel prancha-painel">
              <div className="painel-cabecalho">
                <h2>Prancha e legenda</h2>
                <div className="cabecalho-controles">
                  <button
                    type="button"
                    className="botao-secundario"
                    onClick={() => setMostrarMarcacoes((current) => !current)}
                    aria-pressed={mostrarMarcacoes}
                  >
                    {mostrarMarcacoes ? "Ocultar marcações" : "Mostrar marcações"}
                  </button>
                  <div className="zoom-controles">
                    <button
                      type="button"
                      className="botao-secundario"
                      onClick={() => setZoom((current) => clampZoom(current - ZOOM_STEP))}
                      aria-label="Afastar o zoom da prancha"
                    >
                      −
                    </button>
                    <span className="zoom-leitura">
                      {zoom.toFixed(2).replace(".", ",")}×
                    </span>
                    <button
                      type="button"
                      className="botao-secundario"
                      onClick={() => setZoom((current) => clampZoom(current + ZOOM_STEP))}
                      aria-label="Aproximar o zoom da prancha"
                    >
                      +
                    </button>
                  </div>
                </div>
              </div>
              <p className="dica">
                Aqui é a prancha que o projetista enviou: por padrão nenhuma marcação
                fica sobre a imagem. Ao selecionar um item na lista, só o retângulo fino
                dele aparece, sem número. &quot;Mostrar marcações&quot; revela o
                retângulo e o número de todos os itens de uma vez, para auditoria — o
                estado por extenso fica sempre na lista ao lado, nunca só na cor. Role
                com a roda do mouse sobre a prancha para aproximar (de {MIN_ZOOM}× a{" "}
                {MAX_ZOOM}×) e arraste para deslocar.
              </p>
              {prancha !== null && !prancha.present ? (
                <p className="banner-erro" role="alert">
                  A imagem da prancha não está no diretório da rodada (ou não casa com o
                  digest do pacote). A lista de itens continua utilizável; o overlay não é
                  regravado enquanto ela faltar.
                </p>
              ) : null}
              <div
                className={`prancha-canvas ${panning ? "arrastando" : ""}`}
                ref={canvasRef}
                onPointerDown={startPan}
                onPointerMove={movePan}
                onPointerUp={endPan}
                onPointerCancel={endPan}
              >
                <div
                  className="prancha-stage"
                  style={
                    imageSize === null
                      ? undefined
                      : stageStyle(zoom, imageSize.width, imageSize.height)
                  }
                >
                  {(prancha === null || prancha.present) && pranchaSrc !== null ? (
                    <img
                      src={pranchaSrc}
                      alt="Prancha do projetista com a legenda quantificada"
                      draggable={false}
                      onLoad={(event) => {
                        const { naturalWidth, naturalHeight } = event.currentTarget;
                        setImageSize(
                          (current) =>
                            current ?? { width: naturalWidth, height: naturalHeight },
                        );
                      }}
                    />
                  ) : null}
                  {imageSize === null ? null : (
                    <svg
                      className="bbox-overlay"
                      viewBox={`0 0 ${imageSize.width} ${imageSize.height}`}
                      preserveAspectRatio="none"
                    >
                      {items.map((item, index) => {
                        const numero = index + 1;
                        const selecionado = item.id === selectedItemId;
                        // Item sem localização confirmada (`anchor !== "registered"`)
                        // nunca ganha retângulo nem número — nem selecionado, nem em
                        // "Mostrar marcações": desenhar um retângulo ali seria afirmar
                        // uma posição que o servidor ainda não confirmou.
                        const registrado = itemAnchor(item) === "registered";
                        // Prancha limpa por padrão: aqui é o lugar de somente a imagem
                        // que o projetista enviou. Nada desenhado, exceto o retângulo
                        // fino do item selecionado — sem número, ele sozinho não precisa
                        // de balão para se identificar. "Mostrar marcações" é o único
                        // jeito de ver todo mundo de uma vez, com número, para auditoria.
                        const mostrar = registrado && (mostrarMarcacoes || selecionado);
                        if (!mostrar) {
                          return null;
                        }
                        const rect = bboxRect(item.evidence.bbox);
                        // O número só existe no modo auditoria; mesmo lá, mora fora do
                        // bbox (`pinPlacement`) — dentro dele, o balão cobria letra da
                        // legenda ("PISO EM(1)CONCRETO" foi o defeito real).
                        const pin =
                          !mostrarMarcacoes || imageSize === null
                            ? null
                            : pinPlacement(
                                item.evidence.bbox,
                                PIN_DIAMETER_PX,
                                imageSize.width,
                                imageSize.height,
                              );
                        const onKeyDownSelecionar = (event: ReactKeyboardEvent<SVGGElement>) => {
                          if (event.key === "Enter" || event.key === " ") {
                            event.preventDefault();
                            selecionarItem(item);
                          }
                        };

                        return (
                          <g
                            key={item.id}
                            className={`bbox bbox-${item.status} ${
                              selecionado && mostrarMarcacoes ? "selecionado" : ""
                            }`}
                            role="button"
                            tabIndex={0}
                            aria-label={`Item ${numero}: ${item.label}, ${itemStatusLabel(
                              item.status,
                            )}`}
                            onClick={() => selecionarItem(item)}
                            onKeyDown={onKeyDownSelecionar}
                          >
                            <rect
                              x={rect.x}
                              y={rect.y}
                              width={rect.width}
                              height={rect.height}
                            />
                            {pin === null ? null : (
                              <>
                                <circle className="bbox-pino-circulo" cx={pin.cx} cy={pin.cy} r={pin.r} />
                                <text
                                  className="bbox-pino-texto"
                                  x={pin.cx}
                                  y={pin.cy + pin.r * 0.35}
                                  textAnchor="middle"
                                >
                                  {numero}
                                </text>
                              </>
                            )}
                          </g>
                        );
                      })}
                    </svg>
                  )}
                </div>
              </div>
            </article>

            <article className="painel lista-painel">
              <h2>Itens da legenda</h2>
              <p className="dica">
                {takeoff.packet.items.length} itens da prancha{" "}
                <span className="mono">{takeoff.packet.plate_id}</span>. Pacote sha256{" "}
                <span className="digest" title={takeoff.packet_sha256}>
                  {shortDigest(takeoff.packet_sha256)}
                </span>
                .
              </p>
              <ul className="itens">
                {items.map((item, index) => (
                  <li
                    key={item.id}
                    className={`item ${item.status} ${
                      item.id === selectedItemId ? "selecionado" : ""
                    }`}
                  >
                    <button
                      type="button"
                      className="item-botao"
                      onClick={() => selecionarItem(item)}
                      aria-pressed={item.id === selectedItemId}
                    >
                      <span className="item-numero">{index + 1}</span>
                      <span className="item-corpo">
                        <span className="item-rotulo">{item.label}</span>
                        <span className="item-estado">{itemStatusLabel(item.status)}</span>
                        <span className="item-quantidade">
                          {formatQuantityText(item.quantity, unitLabel(item.unit))}
                        </span>
                        <span className="mono item-raw">{item.raw_text}</span>
                        {item.note === null ? null : (
                          <span className="item-nota">Anotação: {item.note}</span>
                        )}
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            </article>

            <article className="painel decisao-painel">
              <h2>Decisão do item</h2>
              {selectedItem === null ? (
                <p>Escolha um item na lista ou clique no retângulo da prancha.</p>
              ) : selectedItem.decision !== null ? (
                <div className="decisao-registrada">
                  <p>
                    <strong>{selectedItem.label}</strong> —{" "}
                    {itemStatusLabel(selectedItem.status)}.
                  </p>
                  <p>
                    {selectedItem.decision.action === "confirm"
                      ? "Confirmado"
                      : "Rejeitado"}{" "}
                    por {selectedItem.decision.reviewer_id} em{" "}
                    {formatTimestamp(selectedItem.decision.decided_at)}.
                  </p>
                  {selectedItem.decision.note === null ? null : (
                    <p>Nota: {selectedItem.decision.note}</p>
                  )}
                  <p className="cartao-motivo">
                    Este item já foi decidido; decisão não se sobrescreve.
                  </p>
                </div>
              ) : (
                <form
                  className="formulario"
                  onSubmit={(event) => {
                    event.preventDefault();
                    void enviarDecisao();
                  }}
                >
                  <p>
                    <strong>{selectedItem.label}</strong> —{" "}
                    {itemStatusLabel(selectedItem.status)} ·{" "}
                    {formatQuantityText(
                      selectedItem.quantity,
                      unitLabel(selectedItem.unit),
                    )}
                  </p>
                  <p className="mono item-raw">{selectedItem.raw_text}</p>

                  <fieldset className="acoes">
                    <legend>Ato do orçamentista</legend>
                    {/* Nada pré-marcado: a decisão nasce do clique, nunca do default. */}
                    <label>
                      <input
                        type="radio"
                        name="acao"
                        value="confirm"
                        checked={decision.action === "confirm"}
                        onChange={() =>
                          setDecision((current) => ({ ...current, action: "confirm" }))
                        }
                      />
                      Confirmar item
                    </label>
                    <label>
                      <input
                        type="radio"
                        name="acao"
                        value="reject"
                        checked={decision.action === "reject"}
                        onChange={() =>
                          setDecision((current) => ({ ...current, action: "reject" }))
                        }
                      />
                      Rejeitar item
                    </label>
                  </fieldset>

                  {decision.action === "confirm" ? (
                    <>
                      <label className="campo">
                        Quantidade
                        {selectedItem.status === "ambiguous" ? (
                          <span className="campo-aviso">
                            obrigatória — {AVISO_QUANTIDADE_AMBIGUA}
                          </span>
                        ) : (
                          <span className="campo-dica">
                            em branco mantém a quantidade extraída
                          </span>
                        )}
                        <input
                          type="text"
                          inputMode="decimal"
                          value={decision.quantity}
                          onChange={(event) =>
                            setDecision((current) => ({
                              ...current,
                              quantity: event.target.value,
                            }))
                          }
                          aria-invalid={quantidadeInvalida}
                        />
                        <span className="campo-dica">
                          {DICA_QUANTIDADE}
                          {quantidadeParaServidor === null
                            ? ""
                            : ` Será enviada como ${quantidadeParaServidor}.`}
                        </span>
                      </label>
                      <label className="campo">
                        Unidade
                        <span className="campo-dica">
                          em branco mantém {unitLabel(selectedItem.unit)}
                        </span>
                        <input
                          type="text"
                          value={decision.unit}
                          onChange={(event) =>
                            setDecision((current) => ({
                              ...current,
                              unit: event.target.value,
                            }))
                          }
                        />
                      </label>
                      <label className="campo">
                        Anotação do item
                        <span className="campo-dica">
                          corrige o texto que acompanha a linha na legenda
                        </span>
                        <input
                          type="text"
                          value={decision.itemNote}
                          onChange={(event) =>
                            setDecision((current) => ({
                              ...current,
                              itemNote: event.target.value,
                            }))
                          }
                        />
                      </label>
                    </>
                  ) : null}

                  <label className="campo">
                    Nota da decisão
                    <span className="campo-dica">
                      documenta o ato: conversão de unidade, origem da quantidade, motivo
                      da rejeição
                    </span>
                    <textarea
                      value={decision.note}
                      rows={3}
                      onChange={(event) =>
                        setDecision((current) => ({
                          ...current,
                          note: event.target.value,
                        }))
                      }
                    />
                  </label>

                  {quantidadeInvalida ? (
                    <p className="campo-erro" role="alert">
                      Quantidade não reconhecida. {DICA_QUANTIDADE}
                    </p>
                  ) : null}
                  {exigeQuantidade && quantidadeParaServidor === null ? (
                    <p className="campo-erro">
                      Item ambíguo: informe a quantidade para confirmar.
                    </p>
                  ) : null}

                  <button
                    type="submit"
                    className="botao-primario"
                    disabled={decisaoBloqueada}
                  >
                    {submitting ? "Registrando…" : "Registrar decisão"}
                  </button>
                  <p className="dica">
                    Identidade e horário são do servidor: a decisão sai carimbada com{" "}
                    {state?.reviewer_id ?? "o revisor do processo"}.
                  </p>
                </form>
              )}
              {selectedItem === null || itemAnchor(selectedItem) === "registered" ? null : (
                <p className="aviso-fixo aviso-inline">
                  {AVISO_LOCALIZACAO_NAO_CONFIRMADA}
                </p>
              )}
            </article>
          </section>
        ) : null}

        {etapaVisivel === "codigos" && codes !== null ? (
          <section className="workspace duas-colunas" aria-label="Confirmação de código">
            <article className="painel lista-painel">
              <h2>Itens confirmados sem código</h2>
              {suggestions === null ? (
                <div className="shortlist-vazia">
                  <p>
                    A shortlist ainda não foi calculada nesta rodada. Calcular grava{" "}
                    <span className="mono">code-suggestions.json</span> no diretório.
                  </p>
                  {/* O custo do clique é o do braço semântico DESTA rodada; dizer
                      "nenhum provider é chamado" era falso em rodada com índice e
                      credencial. */}
                  {state === null ? null : (
                    <p className="dica">
                      {descricaoCalculoShortlist(state.busca_semantica.status)}
                    </p>
                  )}
                  <button
                    type="button"
                    className="botao-primario"
                    onClick={() => void calcularShortlist()}
                    disabled={submitting}
                  >
                    Calcular shortlist
                  </button>
                </div>
              ) : (
                <div className="shortlist-vazia">
                  <p className="dica">
                    Recalcular sobrescreve{" "}
                    <span className="mono">code-suggestions.json</span> com o algoritmo
                    atual do servidor; as decisões de código já registradas não mudam.
                  </p>
                  {state === null ? null : (
                    <p className="dica">
                      {descricaoCalculoShortlist(state.busca_semantica.status)}
                    </p>
                  )}
                  <button
                    type="button"
                    className="botao-secundario"
                    onClick={() => void recalcularShortlist()}
                    disabled={submitting}
                  >
                    Recalcular shortlist
                  </button>
                </div>
              )}
              {pendingItems.length === 0 ? (
                <p>Todos os itens confirmados já têm decisão de código.</p>
              ) : (
                <ul className="itens">
                  {pendingItems.map((item) => (
                    <li
                      key={item.item_id}
                      className={`item ${
                        item.item_id === selectedPendingId ? "selecionado" : ""
                      }`}
                    >
                      <button
                        type="button"
                        className="item-botao"
                        onClick={() => {
                          setSelectedPendingId(item.item_id);
                          setCodeChoice(null);
                          setCodeNote("");
                        }}
                        aria-pressed={item.item_id === selectedPendingId}
                      >
                        <span className="item-corpo">
                          <span className="item-rotulo">{item.label}</span>
                          <span className="item-quantidade">
                            {formatQuantityText(item.quantity, unitLabel(item.unit))}
                          </span>
                          <span className="mono item-raw">{item.raw_text}</span>
                          {item.note === null ? null : (
                            <span className="item-nota">Anotação: {item.note}</span>
                          )}
                        </span>
                      </button>
                    </li>
                  ))}
                </ul>
              )}

              <section className="confirmados" aria-label="Itens com código confirmado">
                <h3>Itens com código confirmado</h3>
                {confirmados.length === 0 ? (
                  <p>Nenhum código confirmado até agora.</p>
                ) : (
                  <ul className="confirmados-lista">
                    {confirmados.map((assignment) => {
                      const code = assignment.code;
                      // `code` só é `null` num assignment rejeitado; este filtro já é
                      // só de confirmados, mas o tipo do servidor permite `null` aqui.
                      const description = code === null ? null : assignmentDescriptions[code];
                      return (
                        <li key={assignment.item_id}>
                          <strong>{labelDoItem(assignment.item_id)}</strong> —{" "}
                          <span className="codigo-code">{code ?? "sem código"}</span>
                          {code === null ? null : description === undefined ? (
                            <p className="dica">Buscando descrição no catálogo…</p>
                          ) : description === null ? (
                            <p className="campo-aviso">
                              descrição não encontrada no catálogo desta rodada
                            </p>
                          ) : (
                            <>
                              <p className="codigo-descricao">{description}</p>
                              <Inclusoes description={description} />
                            </>
                          )}
                        </li>
                      );
                    })}
                  </ul>
                )}
              </section>

              <section className="aditivo" aria-label="Candidatos a aditivo">
                <h3>Sem código no contrato — candidatos a aditivo</h3>
                <p className="dica">{AVISO_ADITIVO}</p>
                {dossier === null ? (
                  <>
                    <p className="dica">{AVISO_DOSSIE_PREVIA}</p>
                    {rejeitados.length === 0 && semCandidatoPendentes.length === 0 ? (
                      <p>Nenhum item nesta condição até agora.</p>
                    ) : (
                      <ul className="aditivo-lista">
                        {rejeitados.map((assignment) => (
                          <li key={assignment.item_id}>
                            <strong>{labelDoItem(assignment.item_id)}</strong> —{" "}
                            {assignmentStatusLabel(assignment.status)}.{" "}
                            {assignment.decision.note ?? "sem nota registrada"}
                          </li>
                        ))}
                        {semCandidatoPendentes.map((itemId) => (
                          <li key={itemId}>
                            <strong>{labelDoItem(itemId)}</strong> — a shortlist não achou
                            candidato; busque no catálogo antes de tratar como aditivo.
                          </li>
                        ))}
                      </ul>
                    )}
                    {dossieDisponivel ? (
                      <button
                        type="button"
                        className="botao-secundario"
                        onClick={() => void gerarDossie()}
                        disabled={submitting}
                      >
                        {submitting ? "Gerando…" : "Gerar dossiê do aditivo"}
                      </button>
                    ) : (
                      <p className="cartao-motivo">
                        Gerar o dossiê exige a mesma condição do boletim:{" "}
                        {boletimEtapa?.blockedReason ??
                          "revisão do takeoff e decisão de código completas"}
                        .
                      </p>
                    )}
                  </>
                ) : (
                  <>
                    <p className="dica">{AVISO_DOSSIE_GERADO}</p>
                    <p>
                      Dossiê gerado nesta rodada · sha256{" "}
                      <span className="digest" title={dossier.dossier_sha256}>
                        {shortDigest(dossier.dossier_sha256)}
                      </span>
                    </p>
                    {dossier.dossier.items.length === 0 ? (
                      <p>Nenhum item entrou no dossiê nesta rodada.</p>
                    ) : (
                      <ul className="aditivo-lista">
                        {dossier.dossier.items.map((item) => (
                          <li key={item.item_id}>
                            <strong>{item.label}</strong> —{" "}
                            {formatQuantityText(item.quantity, unitLabel(item.unit))}
                            <p className="codigo-descricao">{item.justification}</p>
                          </li>
                        ))}
                      </ul>
                    )}
                    {dossieDisponivel ? (
                      <button
                        type="button"
                        className="botao-secundario"
                        onClick={() => void gerarDossie()}
                        disabled={submitting}
                      >
                        {submitting ? "Gerando…" : "Regerar dossiê do aditivo"}
                      </button>
                    ) : null}
                  </>
                )}
              </section>
            </article>

            <article className="painel codigos-painel">
              <h2>Código do item</h2>
              {selectedPending === null ? (
                <>
                  <p>Escolha um item pendente na lista ao lado.</p>
                  {ultimoCodigoConfirmado === null ? null : (
                    <div className="decisao-registrada">
                      <p>
                        <strong>{ultimoCodigoConfirmado.itemLabel}</strong> — código{" "}
                        <span className="codigo-code">{ultimoCodigoConfirmado.code}</span>{" "}
                        confirmado nesta sessão.
                      </p>
                      <p className="codigo-descricao">
                        {ultimoCodigoConfirmado.description}
                      </p>
                      <Inclusoes description={ultimoCodigoConfirmado.description} />
                      {ultimoCodigoConfirmado.note === "" ? null : (
                        <p>Nota: {ultimoCodigoConfirmado.note}</p>
                      )}
                      <p className="cartao-motivo">
                        Este é o último código confirmado nesta sessão; a lista de itens
                        pendentes já não o mostra.
                      </p>
                    </div>
                  )}
                </>
              ) : (
                <>
                  <p>
                    <strong>{selectedPending.label}</strong> ·{" "}
                    {formatQuantityText(
                      selectedPending.quantity,
                      unitLabel(selectedPending.unit),
                    )}
                  </p>

                  <h3>Shortlist do servidor</h3>
                  {semCandidato ? (
                    <p className="cartao-motivo">
                      A shortlist não achou candidato para este item. O caminho é a busca
                      no catálogo abaixo. Se a shortlist foi gravada por uma versão antiga
                      do servidor, recalcule-a no painel ao lado.
                    </p>
                  ) : null}
                  {shortlist.length === 0 && !semCandidato ? (
                    <p>
                      Sem shortlist carregada para este item. Calcule a shortlist ou use a
                      busca.
                    </p>
                  ) : (
                    <ul className="codigos">
                      {shortlist.map((candidate: CodeCandidate) => (
                        <CartaoCodigo
                          key={candidate.code}
                          code={candidate.code}
                          description={candidate.description}
                          unit={candidate.unit}
                          unitPrice={candidate.unit_price}
                          score={candidate.lexical_score}
                          inContract={candidate.in_contract}
                          unitCompatible={candidate.unit_compatible}
                          selected={codeChoice?.code === candidate.code}
                          onChoose={() =>
                            setCodeChoice({
                              code: candidate.code,
                              description: candidate.description,
                              unit: candidate.unit,
                              unit_price: candidate.unit_price,
                              unit_compatible: candidate.unit_compatible,
                            })
                          }
                        />
                      ))}
                    </ul>
                  )}

                  <h3>Busca no catálogo</h3>
                  <p className="dica">
                    Enquanto você digita, a busca é a lexical do servidor, sem chamada
                    paga. “Buscar” pede a busca completa da rodada — com o braço semântico
                    junto, quando ele estiver disponível.
                  </p>
                  <form
                    className="busca"
                    onSubmit={(event) => {
                      event.preventDefault();
                      void buscarNoCatalogo();
                    }}
                  >
                    <label className="campo">
                      Palavras ou código
                      <input
                        type="search"
                        value={query}
                        onChange={(event) => setQuery(event.target.value)}
                        placeholder="ex.: piso intertravado"
                      />
                    </label>
                    <button
                      type="submit"
                      className="botao-secundario"
                      disabled={submitting}
                    >
                      Buscar
                    </button>
                  </form>
                  {buscando ? (
                    <p className="dica" aria-live="polite">
                      Buscando no catálogo…
                    </p>
                  ) : null}
                  {/* Falha da busca incremental fica ao lado do campo: ela é transitória
                      (uma tecla a mais já refaz a consulta) e não merece o banner que a
                      tela reserva para recusa de mutação. */}
                  {buscaAviso === null ? null : (
                    <p className="campo-aviso" role="alert">
                      {buscaAviso}
                    </p>
                  )}
                  {searchResult === null ? null : (
                    <>
                      <p className="dica">{resumoDaBusca(searchResult)}</p>
                      {/* Degradação declarada pelo servidor não some da tela: é ela que
                          explica por que a lista veio só pelo léxico. */}
                      {searchResult.semantic_notes.map((note) => (
                        <p key={note} className="dica">
                          {note}
                        </p>
                      ))}
                      <ul className="codigos">
                        {searchResult.results.map((result) => (
                          <CartaoCodigo
                            key={result.code}
                            code={result.code}
                            description={result.description}
                            unit={result.unit}
                            unitPrice={result.unit_price}
                            score={null}
                            inContract={null}
                            unitCompatible={null}
                            selected={codeChoice?.code === result.code}
                            onChoose={() =>
                              setCodeChoice({
                                code: result.code,
                                description: result.description,
                                unit: result.unit,
                                unit_price: result.unit_price,
                                unit_compatible: null,
                              })
                            }
                          />
                        ))}
                      </ul>
                    </>
                  )}

                  <h3>Confirmação</h3>
                  <p>
                    {codeChoice === null
                      ? "Nenhum código escolhido ainda."
                      : `Escolhido: ${codeChoice.code} · ${formatMoneyText(
                          codeChoice.unit_price,
                        )} / ${unitLabel(codeChoice.unit)}`}
                  </p>
                  {divergenciaDeUnidade && codeChoice !== null ? (
                    <p className="campo-aviso" role="alert">
                      {unitMismatchHint(selectedPending.unit, codeChoice.unit)}
                    </p>
                  ) : null}
                  <label className="campo">
                    Nota da decisão
                    <span className="campo-dica">
                      {notaObrigatoria
                        ? "obrigatória: registre a conversão de unidade"
                        : "obrigatória para rejeitar; opcional para confirmar"}
                    </span>
                    <textarea
                      value={codeNote}
                      rows={3}
                      onChange={(event) => setCodeNote(event.target.value)}
                    />
                  </label>
                  <div className="acoes-linha">
                    <button
                      type="button"
                      className="botao-primario"
                      onClick={() => void decidirCodigo("confirm")}
                      disabled={
                        submitting ||
                        codeChoice === null ||
                        (notaObrigatoria && codeNote.trim().length === 0)
                      }
                    >
                      Confirmar código
                    </button>
                    <button
                      type="button"
                      className="botao-secundario"
                      onClick={() => void decidirCodigo("reject")}
                      disabled={submitting || codeNote.trim().length === 0}
                    >
                      Sem código no contrato (aditivo)
                    </button>
                  </div>
                  <p className="dica">
                    Rejeitar exige nota: é ela que vira o texto do pedido de aditivo.
                  </p>
                </>
              )}
            </article>
          </section>
        ) : null}

        {etapaVisivel === "boletim" ? (
          <section className="painel" aria-label="Boletim da medição">
            <h2>Boletim de medição</h2>
            <p className="aviso-fixo aviso-inline">{avisoDaFerramenta(oidcAtivo)}</p>
            {bulletin === null ? (
              <form
                className="formulario"
                onSubmit={(event) => {
                  event.preventDefault();
                  void montarBoletim();
                }}
              >
                <p>
                  A medição ainda não foi montada nesta rodada. Informe a obra e o período;
                  quantidades, preços e totais vêm do takeoff confirmado e do catálogo.
                </p>
                <label className="campo">
                  Chave da obra
                  <span className="campo-dica">
                    minúsculas, números e hífen (ex.: praca-sintetica-oeste)
                  </span>
                  <input
                    type="text"
                    value={calcForm.worksiteKey}
                    onChange={(event) =>
                      setCalcForm((current) => ({
                        ...current,
                        worksiteKey: event.target.value,
                      }))
                    }
                    required
                  />
                </label>
                <label className="campo">
                  Nome da obra
                  <input
                    type="text"
                    value={calcForm.worksiteName}
                    onChange={(event) =>
                      setCalcForm((current) => ({
                        ...current,
                        worksiteName: event.target.value,
                      }))
                    }
                    required
                  />
                </label>
                <label className="campo">
                  Número da medição
                  <input
                    type="number"
                    min={1}
                    value={calcForm.periodNumber}
                    onChange={(event) =>
                      setCalcForm((current) => ({
                        ...current,
                        periodNumber: event.target.value,
                      }))
                    }
                    required
                  />
                </label>
                <label className="campo">
                  Rótulo da medição
                  <span className="campo-dica">como aparece na planilha (ex.: 3ª MEDIÇÃO)</span>
                  <input
                    type="text"
                    value={calcForm.referenceLabel}
                    onChange={(event) =>
                      setCalcForm((current) => ({
                        ...current,
                        referenceLabel: event.target.value,
                      }))
                    }
                    required
                  />
                </label>
                <label className="campo">
                  Endereço (opcional)
                  <input
                    type="text"
                    value={calcForm.address}
                    onChange={(event) =>
                      setCalcForm((current) => ({
                        ...current,
                        address: event.target.value,
                      }))
                    }
                  />
                </label>
                <label className="campo">
                  Contrato (opcional)
                  <input
                    type="text"
                    value={calcForm.contractLabel}
                    onChange={(event) =>
                      setCalcForm((current) => ({
                        ...current,
                        contractLabel: event.target.value,
                      }))
                    }
                  />
                </label>
                <button type="submit" className="botao-primario" disabled={submitting}>
                  {submitting ? "Montando…" : "Montar boletim e memória"}
                </button>
              </form>
            ) : (
              <>
                <p>
                  Medição {bulletin.valuation.period_number} ·{" "}
                  {bulletin.valuation.reference_label} · sha256{" "}
                  <span className="digest" title={bulletin.valuation_sha256}>
                    {shortDigest(bulletin.valuation_sha256)}
                  </span>
                </p>
                {bulletin.valuation.bulletins.map((worksite) => (
                  <div key={worksite.worksite_key} className="obra">
                    <h3>
                      {worksite.worksite_name}{" "}
                      <span className="mono">({worksite.worksite_key})</span>
                    </h3>
                    <p>
                      {worksite.address ?? "endereço não informado"} ·{" "}
                      {worksite.contract_label ?? "contrato não informado"}
                    </p>
                    <table className="tabela">
                      <caption>Boletim de medição da obra</caption>
                      <thead>
                        <tr>
                          <th scope="col">Item</th>
                          <th scope="col">Código</th>
                          <th scope="col">Descrição</th>
                          <th scope="col">Un</th>
                          <th scope="col">Valor unit.</th>
                          <th scope="col">Quant.</th>
                          <th scope="col">Total</th>
                        </tr>
                      </thead>
                      <tbody>
                        {worksite.lines.map((line) => (
                          <tr key={line.item_number}>
                            <td>{line.item_number}</td>
                            <td className="mono">{line.code}</td>
                            <td className="celula-descricao">
                              <p className="boletim-descricao-texto">{line.description}</p>
                              <Inclusoes description={line.description} />
                            </td>
                            <td>{unitLabel(line.unit)}</td>
                            <td className="numero">{formatMoneyText(line.unit_price)}</td>
                            <td className="numero">{formatDecimalText(line.quantity)}</td>
                            <td className="numero">{formatMoneyText(line.total)}</td>
                          </tr>
                        ))}
                      </tbody>
                      <tfoot>
                        <tr>
                          <th scope="row" colSpan={6}>
                            Total da obra
                          </th>
                          <td className="numero">
                            {formatMoneyText(worksite.total_amount)}
                          </td>
                        </tr>
                      </tfoot>
                    </table>

                    <h4>Memória de cálculo</h4>
                    <ul className="memoria">
                      {bulletin.valuation.calc_sheets
                        .filter((sheet) => sheet.worksite_key === worksite.worksite_key)
                        .map((sheet) => (
                          <li key={sheet.item_number}>
                            <p>
                              <strong>Item {sheet.item_number}</strong> — total{" "}
                              {formatDecimalText(sheet.total_quantity)}
                            </p>
                            <ul>
                              {sheet.blocks.map((block, index) => (
                                <li key={`${sheet.item_number}-${index}`}>
                                  {block.label} ({recipeLabel(block.recipe)}):{" "}
                                  {block.operands
                                    .map(
                                      (operand) =>
                                        `${operand.name} ${formatDecimalText(
                                          operand.value,
                                        )}${operand.unit ? ` ${unitLabel(operand.unit)}` : ""}`,
                                    )
                                    .join(" × ")}
                                  {block.deductions.length === 0
                                    ? ""
                                    : ` − ${block.deductions
                                        .map(
                                          (deduction) =>
                                            `${deduction.name} ${formatDecimalText(
                                              deduction.value,
                                            )}`,
                                        )
                                        .join(" − ")}`}{" "}
                                  = {formatDecimalText(block.subtotal)}
                                </li>
                              ))}
                            </ul>
                          </li>
                        ))}
                    </ul>
                  </div>
                ))}
                <p className="total-geral">
                  Total da medição: {formatMoneyText(bulletin.total_amount)}
                </p>
                <p className="dica">
                  Todos os números desta tela vêm do JSON do servidor, que os recomputa na
                  leitura; nada é somado ou multiplicado aqui.
                </p>
              </>
            )}
          </section>
        ) : null}
      </main>
    </div>
  );
}
