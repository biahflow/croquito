/**
 * Lógica pura do painel de evidência de campo (F-030 T3): rótulo de âncora, filtro manual
 * por âncora, e derivação das pastilhas de estado a partir do que o servidor mandou.
 *
 * Nada aqui infere associação, esconde foto ou fabrica número. O filtro é escolha do
 * revisor e a pastilha só traduz um estado que já veio da API — cor nunca é o único
 * indicador, então cada pastilha carrega texto por extenso.
 */
import type {
  FieldEvidencePhoto,
  FieldEvidenceMeasurement,
} from "./api";

/**
 * O rótulo que o campo declarou para a foto. Avulsa traz `anchor_text` livre; a de
 * levantamento traz âncoras tipadas (`point`/`element`/`note`) que o técnico registrou.
 * Ausência é dita, nunca preenchida por inferência.
 */
export function anchorLabel(photo: FieldEvidencePhoto): string {
  if (photo.origin === "standalone") {
    const text = photo.anchor_text?.trim();
    return text && text.length > 0 ? text : "Sem âncora declarada";
  }
  if (photo.anchors.length === 0) {
    return "Sem âncora declarada";
  }
  return photo.anchors
    .map((anchor) => {
      const prefix =
        anchor.kind === "element"
          ? "Elemento"
          : anchor.kind === "point"
            ? "Ponto"
            : "Nota";
      return `${prefix}: ${anchor.ref_id}`;
    })
    .join(" · ");
}

/** Marcador da opção "todas as fotos" do filtro — nunca é uma âncora real. */
export const ALL_ANCHORS = "__all__";

/**
 * As âncoras distintas presentes nas fotos, na ordem em que aparecem, para montar o filtro
 * manual. A opção "todas" é responsabilidade da tela; aqui só vêm as âncoras reais.
 */
export function anchorOptions(photos: FieldEvidencePhoto[]): string[] {
  const seen = new Set<string>();
  const options: string[] = [];
  for (const photo of photos) {
    const label = anchorLabel(photo);
    if (!seen.has(label)) {
      seen.add(label);
      options.push(label);
    }
  }
  return options;
}

/**
 * Filtro manual: `ALL_ANCHORS` (ou uma âncora que não existe mais) devolve todas as fotos.
 * O filtro nunca associa a foto a uma leitura — é só recorte de exibição.
 */
export function filterPhotosByAnchor(
  photos: FieldEvidencePhoto[],
  selected: string,
): FieldEvidencePhoto[] {
  if (selected === ALL_ANCHORS) {
    return photos;
  }
  return photos.filter((photo) => anchorLabel(photo) === selected);
}

export type BadgeTone = "ready" | "blocked" | "neutral";

export type StateBadge = {
  label: string;
  tone: BadgeTone;
};

/**
 * Pastilha de qualidade da foto, derivada dos `findings` do passe offline. Sem análise,
 * não há pastilha (a leitura ainda não rodou); sem achado, a nitidez está boa; com achado,
 * o primeiro sinal traduzido — texto sempre presente, cor nunca sozinha.
 */
export function qualityBadge(photo: FieldEvidencePhoto): StateBadge | null {
  const quality = photo.analysis?.["quality"];
  if (!quality || typeof quality !== "object") {
    return null;
  }
  const findings = (quality as { findings?: unknown }).findings;
  if (!Array.isArray(findings) || findings.length === 0) {
    return { label: "NITIDEZ BOA", tone: "ready" };
  }
  const first = String(findings[0]);
  const translated: Record<string, string> = {
    PHOTO_LOW_SHARPNESS: "POUCA NITIDEZ",
    PHOTO_OVEREXPOSED: "ESTOURADA",
    PHOTO_UNDEREXPOSED: "CONTRALUZ",
    PHOTO_LOW_RESOLUTION: "RESOLUÇÃO BAIXA",
  };
  return { label: translated[first] ?? "QUALIDADE APURADA", tone: "blocked" };
}

/**
 * Pastilha do estado da leitura textual, traduzindo o `reading_status` do servidor. Estado
 * ausente/pulado/falho é neutro, nunca erro de domínio: a foto continua lá, só a leitura
 * não veio. `null` quer dizer "nada a dizer ainda" (leitura não pedida).
 */
export function readingBadge(photo: FieldEvidencePhoto): StateBadge | null {
  switch (photo.reading_status) {
    case "QUEUED":
      return { label: "LENDO…", tone: "neutral" };
    case "PROCESSED":
    case "DRAFT":
      return null;
    case "SKIPPED_DISABLED":
    case "SKIPPED_NO_ENTITLEMENT":
      return { label: "LEITURA PULADA", tone: "neutral" };
    case "FAILED_TRANSIENT":
    case "FAILED_PERMANENT":
      return { label: "LEITURA FALHOU", tone: "neutral" };
    default:
      // NOT_REQUESTED e qualquer estado desconhecido: sem pastilha, com botão de pedir.
      return null;
  }
}

/** Se a leitura ainda pode ser pedida (foto sem leitura pedida ou com falha transitória). */
export function canRequestReading(photo: FieldEvidencePhoto): boolean {
  return (
    photo.reading_status === "NOT_REQUESTED" ||
    photo.reading_status === "FAILED_TRANSIENT"
  );
}

/** Está lendo agora — a tela mostra estado de carregando, não oferece novo pedido. */
export function isReadingInFlight(photo: FieldEvidencePhoto): boolean {
  return photo.reading_status === "QUEUED";
}

/** Verdadeiro quando o passe pago foi deliberadamente pulado (sem análise honesta). */
export function isAnalysisSkipped(photo: FieldEvidencePhoto): boolean {
  return (
    photo.reading_status === "SKIPPED_DISABLED" ||
    photo.reading_status === "SKIPPED_NO_ENTITLEMENT"
  );
}

export type FieldPhotoReading = {
  id?: string;
  raw_text: string;
  target_hint?: string | null;
  value_hint?: string | null;
  unit_hint?: string | null;
  confidence?: string | null;
};

/**
 * As leituras que o passe produziu, como texto para exibir. Cada uma é rascunho e não vira
 * medida — a tela nunca deriva cota daqui. Defensivo: só devolve o que tem `raw_text`.
 */
export function photoReadings(photo: FieldEvidencePhoto): FieldPhotoReading[] {
  const readings = photo.analysis?.["readings"];
  if (!Array.isArray(readings)) {
    return [];
  }
  const out: FieldPhotoReading[] = [];
  for (const item of readings) {
    if (!item || typeof item !== "object") {
      continue;
    }
    const raw = (item as { raw_text?: unknown }).raw_text;
    if (typeof raw !== "string" || raw.length === 0) {
      continue;
    }
    const record = item as Record<string, unknown>;
    out.push({
      id: typeof record.id === "string" ? record.id : undefined,
      raw_text: raw,
      target_hint:
        typeof record.target_hint === "string" ? record.target_hint : null,
      value_hint:
        record.value_hint === null || record.value_hint === undefined
          ? null
          : String(record.value_hint),
      unit_hint:
        typeof record.unit_hint === "string" ? record.unit_hint : null,
      confidence:
        typeof record.confidence === "string" ? record.confidence : null,
    });
  }
  return out;
}

/** Metros a partir de milímetros inteiros, formatados em pt-BR (só apresentação). */
export function metersFromMm(valueMm: number): string {
  return (valueMm / 1000).toLocaleString("pt-BR", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

/** Instante ISO em data/hora pt-BR curta; string vazia se ilegível. */
export function shortInstant(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) {
    return "";
  }
  return date.toLocaleString("pt-BR", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

/** Rótulo curto de uma opção de levantamento para o seletor de vínculo. */
export function surveyOptionLabel(name: string, photoCount: number): string {
  const fotos = photoCount === 1 ? "1 foto" : `${photoCount} fotos`;
  return `${name} (${fotos})`;
}

/** Total de medições confirmadas nos levantamentos vinculados (só exibição). */
export function confirmedMeasurementCount(
  surveys: { measurements: FieldEvidenceMeasurement[] }[],
): number {
  return surveys.reduce((total, survey) => total + survey.measurements.length, 0);
}
