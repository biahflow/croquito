import type { VisionProposal } from "./api";
import type { ImagePoint } from "./selection";
import {
  NOTE_LEGEND_PREFIX,
  NOTE_TARGET_STAMP,
  type DerivedDimensionDraft,
  type SpanTargetDraft,
  type TraceDraft,
} from "./trace";

/**
 * Captura de vão, nota e cota derivada CLICANDO no desenho.
 *
 * Coordenada de pixel digitada é interface de desenvolvedor: quem revisa marca a âncora
 * onde a cota está escrita, no próprio croqui. Esta máquina existe para que a sequência
 * de cliques ("primeira forma", "segunda forma", "as duas pontas do trecho") seja
 * testável sem DOM — o App só traduz gesto em evento e aplica o `commit` no rascunho.
 *
 * Nada aqui decide geometria: o resultado é declaração humana que vai ao solver, no
 * worker, exatamente como os controles 2, 4 e 6 do estágio de traçado descrevem.
 */

export type CaptureState =
  /** Nenhuma amarração em andamento: o clique volta a marcar/desmarcar formas do lote. */
  | { kind: "idle" }
  | { kind: "pair"; readingId: string; firstProposalId: string | null }
  | { kind: "single"; readingId: string }
  | {
      kind: "declared";
      readingId: string;
      proposalId: string | null;
      /** Âncoras já clicadas, em pixels da imagem; cada DUAS fecham um trecho. */
      anchors: [number, number][];
    }
  /** A orientação (#v/#h) e as alternativas legenda/carimbo são escolhidas fora daqui. */
  | { kind: "note"; readingId: string }
  | { kind: "derived"; proposalId: string | null };

export type CaptureEvent =
  | { type: "shape"; proposalId: string }
  | { type: "point"; xPx: number; yPx: number }
  | { type: "cancel" };

/** Efeito pronto para aplicar no `TraceDraft`; um por gesto concluído. */
export type CaptureCommit =
  | { kind: "span"; readingId: string; target: SpanTargetDraft }
  | { kind: "note"; readingId: string; target: string }
  | { kind: "derived"; dimension: DerivedDimensionDraft };

export type CaptureResult = {
  /** Próximo estado da captura. */
  state: CaptureState;
  /** Presente só quando o gesto fechou uma declaração. */
  commit?: CaptureCommit;
  /** Instrução em língua de obra do estado resultante, para o banner vivo. */
  hint: string;
};

export const IDLE_CAPTURE: CaptureState = { kind: "idle" };

/** Trechos completos: âncora solta (número ímpar) fica de fora, nunca é adivinhada. */
function completeSpans(
  anchors: [number, number][],
): [[number, number], [number, number]][] {
  const spans: [[number, number], [number, number]][] = [];
  for (let index = 0; index + 1 < anchors.length; index += 2) {
    spans.push([anchors[index], anchors[index + 1]]);
  }
  return spans;
}

function closedSpansPhrase(anchors: [number, number][]): string {
  const closed = completeSpans(anchors).length;
  if (closed === 0) {
    return "nenhum trecho fechado ainda";
  }
  return closed === 1 ? "1 trecho fechado" : `${closed} trechos fechados`;
}

/**
 * A frase que o revisor lê enquanto a captura está de pé. Ela é função do estado: o
 * mesmo estado sempre pede a mesma coisa, inclusive depois de um clique que não valeu
 * (clicar duas vezes na mesma forma continua pedindo uma forma diferente).
 */
export function captureHint(state: CaptureState): string {
  switch (state.kind) {
    case "idle":
      return "Nenhuma amarração em andamento.";
    case "pair":
      return state.firstProposalId === null
        ? "Clique na primeira forma que este vão encosta."
        : "Agora clique na segunda forma do vão — precisa ser outra forma, não a mesma de novo.";
    case "single":
      return "Clique na forma que esta cota mede.";
    case "declared": {
      if (state.proposalId === null) {
        return "Clique na forma onde a cota mede um trecho interno.";
      }
      const closed = closedSpansPhrase(state.anchors);
      return state.anchors.length % 2 === 1
        ? `Uma ponta marcada; clique na outra ponta do trecho (${closed}; Esc conclui o que já fechou).`
        : `Clique nas duas pontas do trecho que a cota mede (${closed}; Esc conclui o que já fechou).`;
    }
    case "note":
      return "Clique na forma onde a anotação fica presa.";
    case "derived":
      return state.proposalId === null
        ? "Clique na forma que a cota derivada vai medir."
        : "Agora clique no ponto do desenho onde a cota deve pousar.";
  }
}

/**
 * Estados em que o próximo clique é PONTO, não forma.
 *
 * O App usa isto para rotear: âncora de trecho e ponto de cota derivada caem quase
 * sempre em cima do traço do elemento, então clique sobre forma também precisa virar
 * ponto — do contrário a ponta do trecho seria impossível de marcar.
 */
export function captureExpectsPoint(state: CaptureState): boolean {
  return (
    (state.kind === "declared" && state.proposalId !== null) ||
    (state.kind === "derived" && state.proposalId !== null)
  );
}

/** Leitura amarrada por esta captura, quando o gesto pertence a uma leitura. */
export function captureReadingId(state: CaptureState): string | null {
  switch (state.kind) {
    case "pair":
    case "single":
    case "declared":
    case "note":
      return state.readingId;
    default:
      return null;
  }
}

function settle(state: CaptureState, commit?: CaptureCommit): CaptureResult {
  return { state, commit, hint: captureHint(state) };
}

/**
 * Um gesto por vez, sem estado escondido. Evento que não faz sentido no estado atual
 * não muda nada — repetir o hint é a resposta, nunca um efeito surpresa.
 */
export function reduceCapture(
  state: CaptureState,
  event: CaptureEvent,
): CaptureResult {
  if (event.type === "cancel") {
    // Cancelar um vão declarado não joga fora o que já está fechado: Esc é o "concluí",
    // e só a âncora solta (par incompleto) é descartada.
    if (state.kind === "declared" && state.proposalId !== null) {
      const spansPx = completeSpans(state.anchors);
      if (spansPx.length > 0) {
        return settle(IDLE_CAPTURE, {
          kind: "span",
          readingId: state.readingId,
          target: { kind: "declared", proposalId: state.proposalId, spansPx },
        });
      }
    }
    return settle(IDLE_CAPTURE);
  }

  switch (state.kind) {
    case "idle":
      return settle(state);
    case "pair": {
      if (event.type !== "shape") {
        return settle(state);
      }
      if (state.firstProposalId === null) {
        return settle({ ...state, firstProposalId: event.proposalId });
      }
      // Vão em par amarra DUAS formas; a mesma duas vezes não é vão.
      if (state.firstProposalId === event.proposalId) {
        return settle(state);
      }
      return settle(IDLE_CAPTURE, {
        kind: "span",
        readingId: state.readingId,
        target: {
          kind: "pair",
          proposalIds: [state.firstProposalId, event.proposalId],
        },
      });
    }
    case "single": {
      if (event.type !== "shape") {
        return settle(state);
      }
      return settle(IDLE_CAPTURE, {
        kind: "span",
        readingId: state.readingId,
        target: { kind: "single", proposalId: event.proposalId },
      });
    }
    case "declared": {
      if (event.type === "shape") {
        return state.proposalId === null
          ? settle({ ...state, proposalId: event.proposalId })
          : settle(state);
      }
      if (state.proposalId === null) {
        return settle(state);
      }
      return settle({
        ...state,
        anchors: [...state.anchors, [event.xPx, event.yPx]],
      });
    }
    case "note": {
      if (event.type !== "shape") {
        return settle(state);
      }
      return settle(IDLE_CAPTURE, {
        kind: "note",
        readingId: state.readingId,
        target: event.proposalId,
      });
    }
    case "derived": {
      if (event.type === "shape") {
        return state.proposalId === null
          ? settle({ ...state, proposalId: event.proposalId })
          : settle(state);
      }
      if (state.proposalId === null) {
        return settle(state);
      }
      return settle(IDLE_CAPTURE, {
        kind: "derived",
        dimension: {
          proposalId: state.proposalId,
          nearXPx: event.xPx,
          nearYPx: event.yPx,
        },
      });
    }
  }
}

/**
 * Gesto concluído aplicado ao rascunho do aceite. Uma leitura tem um destino só, então
 * amarrar de novo substitui a amarração anterior em vez de acumular; cota derivada não
 * pertence a leitura nenhuma e entra na lista.
 */
export function applyCaptureCommit(
  draft: TraceDraft,
  commit: CaptureCommit,
): TraceDraft {
  switch (commit.kind) {
    case "span":
      return {
        ...draft,
        associations: {
          ...draft.associations,
          [commit.readingId]: commit.target,
        },
      };
    case "note":
      return {
        ...draft,
        noteTargets: { ...draft.noteTargets, [commit.readingId]: commit.target },
      };
    case "derived":
      return {
        ...draft,
        derivedDimensions: [...draft.derivedDimensions, commit.dimension],
      };
  }
}

/** Orientação da aresta âncora da nota presa; `auto` deixa o traçado decidir. */
export type NoteOrientation = "auto" | "v" | "h";

export type NoteTargetChoice =
  | { kind: "shape"; proposalId: string; orientation: NoteOrientation }
  | { kind: "legend"; proposalId: string }
  | { kind: "stamp" };

/**
 * Espelha o formato do alvo de nota do worker (`carimbo`, `legenda:vp_…`, `vp_…[#v|#h]`).
 * Sufixo que não é `v` nem `h` volta como `auto`: a pré-validação de `trace.ts` já acusa
 * o alvo inválido, e a escolha do revisor é refeita pelo próprio seletor.
 */
export function parseNoteTarget(target: string): NoteTargetChoice {
  if (target === NOTE_TARGET_STAMP) {
    return { kind: "stamp" };
  }
  if (target.startsWith(NOTE_LEGEND_PREFIX)) {
    return {
      kind: "legend",
      proposalId: target.slice(NOTE_LEGEND_PREFIX.length),
    };
  }
  const hashIndex = target.indexOf("#");
  if (hashIndex === -1) {
    return { kind: "shape", proposalId: target, orientation: "auto" };
  }
  const suffix = target.slice(hashIndex + 1);
  return {
    kind: "shape",
    proposalId: target.slice(0, hashIndex),
    orientation: suffix === "v" || suffix === "h" ? suffix : "auto",
  };
}

export function formatNoteTarget(choice: NoteTargetChoice): string {
  switch (choice.kind) {
    case "stamp":
      return NOTE_TARGET_STAMP;
    case "legend":
      return `${NOTE_LEGEND_PREFIX}${choice.proposalId}`;
    case "shape":
      return choice.orientation === "auto"
        ? choice.proposalId
        : `${choice.proposalId}#${choice.orientation}`;
  }
}

/**
 * Centro aparente da forma, em pixels da imagem, só para desenhar o rascunho do vão em
 * par sobre o palco. É apresentação: nenhum valor daqui é enviado à API nem vira
 * geometria — quem resolve o vão é o solver, a partir das formas declaradas.
 */
export function proposalCentrePx(
  geometry: VisionProposal["geometry"],
): ImagePoint {
  if (geometry.type === "line") {
    return {
      x: (geometry.start.x + geometry.end.x) / 2,
      y: (geometry.start.y + geometry.end.y) / 2,
    };
  }
  if (geometry.type === "circle") {
    return { x: geometry.center.x, y: geometry.center.y };
  }
  const points = geometry.points;
  if (points.length === 0) {
    return { x: 0, y: 0 };
  }
  // Centro da caixa envolvente, e não média dos vértices: contorno com muitos pontos
  // numa ponta puxaria a média para lá e a linha do vão sairia do elemento.
  let left = points[0].x;
  let right = points[0].x;
  let top = points[0].y;
  let bottom = points[0].y;
  for (const point of points) {
    left = Math.min(left, point.x);
    right = Math.max(right, point.x);
    top = Math.min(top, point.y);
    bottom = Math.max(bottom, point.y);
  }
  return { x: (left + right) / 2, y: (top + bottom) / 2 };
}
