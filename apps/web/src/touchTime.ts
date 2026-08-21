import { useCallback, useEffect, useMemo, useRef } from "react";

/**
 * Cronômetro do tempo de interação humana na revisão (F-031 T4).
 *
 * O que se quer medir é *touch time*: quanto tempo uma pessoa passou de fato diante da
 * folha até registrar o ato. Não é o intervalo entre um envio e o seguinte — nele cabem
 * o café, a reunião e a noite de sono —, e é por isso que a conta é da tela e não do
 * servidor: só o navegador sabe que a aba ficou em segundo plano.
 *
 * Por isso `document.visibilityState === "hidden"` PAUSA o relógio. Aba em segundo plano
 * é tempo que não é trabalho, e somá-lo transformaria a métrica de esforço humano numa
 * medida de quanto tempo a página ficou aberta.
 *
 * O número é observacional do começo ao fim: viaja como campo opcional da mutação, o
 * servidor descarta o que for implausível e nada — decisão, geometria, exportação —
 * depende dele. Perder a medida nunca pode custar o ato humano que ela descreve.
 *
 * As funções abaixo são puras e recebem o instante de fora, para serem testáveis sem DOM
 * e sem relógio real; quem toca `document` é o hook no fim do arquivo.
 */

/** Relógio parcial: o que já foi acumulado e o início do trecho corrente. */
export type TouchClock = {
  /** Milissegundos já fechados em trechos anteriores, todos com a aba visível. */
  readonly accumulatedMs: number;
  /** Instante de início do trecho corrente; `null` quer dizer relógio pausado. */
  readonly runningSince: number | null;
};

/**
 * Trecho decorrido, nunca negativo.
 *
 * O relógio de origem é monotônico (`performance.now`), mas o `Date.now` de reserva não
 * é: ajuste de horário do sistema pode fazer `now` voltar. Um trecho negativo subtrairia
 * tempo de trabalho que aconteceu, então ele vale zero.
 */
function segmentMs(since: number, now: number): number {
  return now > since ? now - since : 0;
}

/** Relógio novo, correndo a partir de agora. Zera o que houvesse antes. */
export function startedTouchClock(now: number): TouchClock {
  return { accumulatedMs: 0, runningSince: now };
}

/** Fecha o trecho corrente e para. Pausar um relógio já pausado não muda nada. */
export function pausedTouchClock(clock: TouchClock, now: number): TouchClock {
  if (clock.runningSince === null) {
    return clock;
  }
  return {
    accumulatedMs: clock.accumulatedMs + segmentMs(clock.runningSince, now),
    runningSince: null,
  };
}

/** Abre um trecho novo. Retomar um relógio que já corre não reinicia o trecho. */
export function resumedTouchClock(clock: TouchClock, now: number): TouchClock {
  if (clock.runningSince !== null) {
    return clock;
  }
  return { accumulatedMs: clock.accumulatedMs, runningSince: now };
}

/** Total acumulado até `now`, em milissegundos inteiros. */
export function touchClockElapsedMs(clock: TouchClock, now: number): number {
  const running =
    clock.runningSince === null ? 0 : segmentMs(clock.runningSince, now);
  return Math.round(clock.accumulatedMs + running);
}

/**
 * Relógio monotônico quando o ambiente tem um; `Date.now` como reserva.
 *
 * `performance.now` não anda para trás quando o sistema acerta o horário, que é
 * justamente o risco de medir duração com o relógio de parede.
 */
function monotonicNow(): number {
  return typeof performance !== "undefined" &&
    typeof performance.now === "function"
    ? performance.now()
    : Date.now();
}

function documentHidden(): boolean {
  return (
    typeof document !== "undefined" && document.visibilityState === "hidden"
  );
}

export type TouchTimeHandle = {
  /** Recomeça a medida do zero — a revisão apresentada na tela mudou. */
  restart: () => void;
  /** Acumulado até agora, ou `null` se nenhuma sessão de revisão começou. */
  elapsedMs: () => number | null;
};

/**
 * Liga o cronômetro à aba: pausa ao esconder, retoma ao voltar.
 *
 * `elapsedMs()` NÃO zera o relógio: quem zera é `restart()`, chamado quando a revisão
 * apresentada muda. Assim, um envio que falhou (rede, conflito de revisão) não descarta
 * o tempo que a pessoa gastou — ele continua contando para a próxima tentativa, que é o
 * mesmo trabalho.
 */
export function useTouchTime(): TouchTimeHandle {
  const clock = useRef<TouchClock | null>(null);

  useEffect(() => {
    if (typeof document === "undefined") {
      return;
    }
    const onVisibilityChange = () => {
      const current = clock.current;
      if (current === null) {
        return;
      }
      clock.current = documentHidden()
        ? pausedTouchClock(current, monotonicNow())
        : resumedTouchClock(current, monotonicNow());
    };
    document.addEventListener("visibilitychange", onVisibilityChange);
    return () => {
      document.removeEventListener("visibilitychange", onVisibilityChange);
    };
  }, []);

  const restart = useCallback(() => {
    const now = monotonicNow();
    const started = startedTouchClock(now);
    // Revisão aberta com a aba já escondida (link restaurado em segundo plano) nasce
    // parada: o relógio só anda quando alguém está olhando.
    clock.current = documentHidden() ? pausedTouchClock(started, now) : started;
  }, []);

  const elapsedMs = useCallback(() => {
    const current = clock.current;
    return current === null ? null : touchClockElapsedMs(current, monotonicNow());
  }, []);

  return useMemo(() => ({ restart, elapsedMs }), [restart, elapsedMs]);
}
