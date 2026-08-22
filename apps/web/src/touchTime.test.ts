/**
 * O cronômetro do touch time (F-031 T4) mede tempo diante da folha, não tempo de aba
 * aberta. Estes testes fixam a pausa por visibilidade — o comportamento que separa uma
 * medida de esforço humano de uma medida de quanto tempo a página ficou esquecida — e a
 * recusa de trecho negativo quando o relógio de reserva anda para trás.
 */
import { describe, expect, it } from "vitest";
import {
  pausedTouchClock,
  resumedTouchClock,
  startedTouchClock,
  touchClockElapsedMs,
  type TouchClock,
} from "./touchTime";

describe("cronômetro da sessão de revisão", () => {
  it("acumula o tempo decorrido enquanto corre", () => {
    const clock = startedTouchClock(1_000);

    expect(touchClockElapsedMs(clock, 5_200)).toBe(4_200);
  });

  it("aba em segundo plano não conta: o intervalo escondido fica de fora", () => {
    // 1s visível, 60s escondida, 2s visível de novo — a medida é 3s, e não 63s.
    let clock: TouchClock = startedTouchClock(0);
    clock = pausedTouchClock(clock, 1_000);
    clock = resumedTouchClock(clock, 61_000);

    expect(touchClockElapsedMs(clock, 63_000)).toBe(3_000);
  });

  it("relógio parado não anda: o total é o mesmo em qualquer instante posterior", () => {
    const clock = pausedTouchClock(startedTouchClock(0), 1_500);

    expect(touchClockElapsedMs(clock, 1_500)).toBe(1_500);
    expect(touchClockElapsedMs(clock, 900_000)).toBe(1_500);
  });

  it("pausar duas vezes não fecha o mesmo trecho duas vezes", () => {
    const clock = pausedTouchClock(pausedTouchClock(startedTouchClock(0), 1_000), 9_000);

    expect(touchClockElapsedMs(clock, 9_000)).toBe(1_000);
  });

  it("retomar um relógio que já corre não reinicia o trecho corrente", () => {
    const clock = resumedTouchClock(startedTouchClock(0), 5_000);

    expect(touchClockElapsedMs(clock, 8_000)).toBe(8_000);
  });

  it("recomeçar zera o acumulado: cada revisão apresentada mede o próprio tempo", () => {
    const primeira = pausedTouchClock(startedTouchClock(0), 4_200);

    expect(touchClockElapsedMs(startedTouchClock(4_200), 5_200)).toBe(1_000);
    // A primeira medida continua sendo a dela — nada é somado por engano.
    expect(touchClockElapsedMs(primeira, 5_200)).toBe(4_200);
  });

  it("relógio que anda para trás não subtrai trabalho que aconteceu", () => {
    // `Date.now` de reserva pode saltar com acerto de horário do sistema.
    const clock = startedTouchClock(10_000);

    expect(touchClockElapsedMs(clock, 4_000)).toBe(0);
  });
});
