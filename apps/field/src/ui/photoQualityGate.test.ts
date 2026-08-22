import { describe, expect, it } from "vitest";

import {
  INITIAL_PHOTO_QUALITY_GATE_STATE,
  photoQualityGateReducer,
  photoQualityWarnTagText,
} from "./photoQualityGate";

function file(name = "foto.jpg"): File {
  return new File([], name);
}

describe("photoQualityGateReducer", () => {
  it("começa vazio", () => {
    expect(INITIAL_PHOTO_QUALITY_GATE_STATE).toEqual({ phase: "empty" });
  });

  it("file-selected entra em checking com o arquivo escolhido", () => {
    const f = file();

    const next = photoQualityGateReducer(INITIAL_PHOTO_QUALITY_GATE_STATE, {
      type: "file-selected",
      file: f,
    });

    expect(next).toEqual({ phase: "checking", file: f });
  });

  it("evaluated com veredito ok vira clear — segue direto, sem aviso (T15, item 3)", () => {
    const f = file();
    const checking = photoQualityGateReducer(INITIAL_PHOTO_QUALITY_GATE_STATE, {
      type: "file-selected",
      file: f,
    });

    const next = photoQualityGateReducer(checking, {
      type: "evaluated",
      file: f,
      outcome: {
        available: true,
        sharpness: 999_999,
        exposure: { clippedHighlights: 0, clippedShadows: 0 },
        verdict: "ok",
        reasons: [],
      },
    });

    expect(next).toEqual({ phase: "clear", file: f });
  });

  it("evaluated indisponível (falha de decodificação) também vira clear, nunca warn", () => {
    const f = file();
    const checking = photoQualityGateReducer(INITIAL_PHOTO_QUALITY_GATE_STATE, {
      type: "file-selected",
      file: f,
    });

    const next = photoQualityGateReducer(checking, {
      type: "evaluated",
      file: f,
      outcome: { available: false },
    });

    expect(next).toEqual({ phase: "clear", file: f });
  });

  it("evaluated com veredito não-ok vira warn com o veredito e os motivos", () => {
    const f = file();
    const checking = photoQualityGateReducer(INITIAL_PHOTO_QUALITY_GATE_STATE, {
      type: "file-selected",
      file: f,
    });

    const next = photoQualityGateReducer(checking, {
      type: "evaluated",
      file: f,
      outcome: {
        available: true,
        sharpness: 0,
        exposure: { clippedHighlights: 0, clippedShadows: 0 },
        verdict: "blurry",
        reasons: ["Nitidez baixa — possivelmente tremida ou fora de foco."],
      },
    });

    expect(next).toEqual({
      phase: "warn",
      file: f,
      verdict: "blurry",
      reasons: ["Nitidez baixa — possivelmente tremida ou fora de foco."],
    });
  });

  it("descarta uma avaliação atrasada de um arquivo que não é mais o pendente (técnico já trocou de foto)", () => {
    const first = file("primeira.jpg");
    const second = file("segunda.jpg");
    const checkingFirst = photoQualityGateReducer(INITIAL_PHOTO_QUALITY_GATE_STATE, {
      type: "file-selected",
      file: first,
    });
    const checkingSecond = photoQualityGateReducer(checkingFirst, {
      type: "file-selected",
      file: second,
    });

    // A avaliação da PRIMEIRA foto chega depois de o técnico já ter trocado para a segunda.
    const next = photoQualityGateReducer(checkingSecond, {
      type: "evaluated",
      file: first,
      outcome: {
        available: true,
        sharpness: 0,
        exposure: { clippedHighlights: 0, clippedShadows: 0 },
        verdict: "blurry",
        reasons: ["Nitidez baixa — possivelmente tremida ou fora de foco."],
      },
    });

    expect(next).toEqual({ phase: "checking", file: second });
  });

  it("reset volta para empty a partir de qualquer fase (Refazer descarta sem persistir)", () => {
    const f = file();
    const warn = photoQualityGateReducer(
      photoQualityGateReducer(INITIAL_PHOTO_QUALITY_GATE_STATE, { type: "file-selected", file: f }),
      {
        type: "evaluated",
        file: f,
        outcome: {
          available: true,
          sharpness: 0,
          exposure: { clippedHighlights: 0, clippedShadows: 0 },
          verdict: "under",
          reasons: ["Imagem muito escura — difícil de ler."],
        },
      },
    );

    const next = photoQualityGateReducer(warn, { type: "reset" });

    expect(next).toEqual({ phase: "empty" });
  });
});

describe("photoQualityWarnTagText", () => {
  it("devolve texto escrito distinto para cada veredito de aviso (nunca só cor)", () => {
    expect(photoQualityWarnTagText("blurry")).toMatch(/nitidez/i);
    expect(photoQualityWarnTagText("over")).toMatch(/luz/i);
    expect(photoQualityWarnTagText("under")).toMatch(/escura/i);
  });
});
