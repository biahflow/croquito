/**
 * Estado/transições da checagem de qualidade de foto (Task Contract T15, prancha 7b da
 * DAP rev.2) — função pura entre a captura do arquivo e as duas telas que a usam
 * (`PhotoAnchorScreen`, foto ancorada T6; `ArrivalScreen`, foto do acesso T4). Mesma
 * disciplina de `ui/viewModel.ts` e `ui/syncViewModel.ts`: nada aqui importa React, então
 * a máquina de estados é testável em node puro, sem DOM.
 *
 * Fases:
 * - `empty`: nenhum arquivo selecionado ainda (estado inicial).
 * - `checking`: arquivo escolhido, avaliação (`evaluateCapturedPhoto`) em andamento —
 *   pode levar algumas centenas de ms (Task Contract T15, Contexto verificado, NFR).
 * - `warn`: avaliação concluiu com um veredito que NÃO é "ok" — a 7b deve aparecer
 *   (tag + banner + Refazer/Manter).
 * - `clear`: avaliação concluiu "ok" (ou a decodificação falhou e virou "indisponível")
 *   — segue direto, sem interstício (Task Contract T15, Comportamento exigido item 3:
 *   "Foto ok não ganha interstício").
 *
 * Decisão consciente (registrada no BUILD REPORT): "indisponível" (falha de decodificação)
 * é tratado como `clear`, não como `warn`. Não há evidência de problema para avisar sobre
 * — mostrar um card de aviso sem ter medido nada seria inventar um sinal que não existe, e
 * a regra "falha de decodificação NUNCA bloqueia a foto" (Task Contract T15,
 * Comportamento exigido item 2) fica mais forte não acrescentando fricção nenhuma.
 */

import type { PhotoQualityEvaluation } from "../photos/evaluateCapturedPhoto";
import type { PhotoQualityVerdict } from "../photos/quality";

/** Vereditos que disparam a 7b — todo `PhotoQualityVerdict` exceto "ok". */
export type PhotoQualityWarnVerdict = Exclude<PhotoQualityVerdict, "ok">;

export type PhotoQualityGateState =
  | { phase: "empty" }
  | { phase: "checking"; file: File }
  | { phase: "warn"; file: File; verdict: PhotoQualityWarnVerdict; reasons: string[] }
  | { phase: "clear"; file: File };

export const INITIAL_PHOTO_QUALITY_GATE_STATE: PhotoQualityGateState = { phase: "empty" };

export type PhotoQualityGateAction =
  | { type: "file-selected"; file: File }
  | { type: "evaluated"; file: File; outcome: PhotoQualityEvaluation }
  | { type: "reset" };

export function photoQualityGateReducer(
  state: PhotoQualityGateState,
  action: PhotoQualityGateAction,
): PhotoQualityGateState {
  switch (action.type) {
    case "file-selected":
      return { phase: "checking", file: action.file };
    case "evaluated": {
      // Uma avaliação só é aplicada se ainda for do arquivo pendente: se o técnico já
      // trocou de foto (ou cancelou) antes da Promise resolver, o resultado atrasado é
      // descartado — nunca reabre o card para uma foto que não é mais a selecionada.
      if (state.phase !== "checking" || state.file !== action.file) {
        return state;
      }
      if (action.outcome.available && action.outcome.verdict !== "ok") {
        return {
          phase: "warn",
          file: action.file,
          verdict: action.outcome.verdict,
          reasons: action.outcome.reasons,
        };
      }
      return { phase: "clear", file: action.file };
    }
    case "reset":
      return { phase: "empty" };
  }
}

const WARN_TAG_TEXT: Record<PhotoQualityWarnVerdict, string> = {
  blurry: "Nitidez baixa — possivelmente tremida",
  over: "Excesso de luz — possivelmente estourada",
  under: "Muito escura — possivelmente ilegível",
};

/** Texto escrito da tag de veredito (prancha 7b) — nunca só cor (`CLAUDE.md`: "Cor nunca
 * é o único indicador de precisão/issue"). */
export function photoQualityWarnTagText(verdict: PhotoQualityWarnVerdict): string {
  return WARN_TAG_TEXT[verdict];
}
