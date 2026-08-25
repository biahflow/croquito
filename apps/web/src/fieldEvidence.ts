/**
 * Lógica pura do painel de evidência de campo (F-030 T3): rótulo de âncora, filtro manual
 * por âncora, e derivação das pastilhas de estado a partir do que o servidor mandou.
 *
 * Nada aqui infere associação, esconde foto ou fabrica número. O filtro é escolha do
 * revisor e a pastilha só traduz um estado que já veio da API — cor nunca é o único
 * indicador, então cada pastilha carrega texto por extenso.
 */
import type {
  FieldEvidence,
  FieldEvidencePhoto,
  FieldEvidenceMeasurement,
  FieldWitness,
  FieldWitnessSource,
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

// --- Testemunhas de campo (F-030 T5) ---
//
// O confronto de dois números com a origem de cada um. A diferença é magnitude neutra: nada
// aqui devolve tom, ícone ou juízo de concordância — enquanto não há tolerância calibrada, a
// tela só mostra os dois valores e a diferença (ADR-0049 D7, emenda 1). A escolha da fonte é
// ato humano: os helpers montam a lista de opções elegíveis, mas nunca pré-selecionam nem
// inferem associação a partir de âncora, proximidade ou valor.

/**
 * Valor de option estável e reversível para o seletor de fonte. A medida do app carrega
 * `survey_id`; a leitura de foto não. Roundtrip com `parseWitnessSourceOption`.
 */
export function witnessSourceOptionValue(source: FieldWitnessSource): string {
  if (source.type === "survey_measurement") {
    return `survey_measurement:${source.survey_id ?? ""}:${source.source_id}`;
  }
  return `photo_reading:${source.source_id}`;
}

/** Inverso de `witnessSourceOptionValue`; `null` para qualquer string que não parseia. */
export function parseWitnessSourceOption(value: string): FieldWitnessSource | null {
  if (value.startsWith("survey_measurement:")) {
    const rest = value.slice("survey_measurement:".length);
    const sep = rest.indexOf(":");
    if (sep <= 0) {
      return null;
    }
    const surveyId = rest.slice(0, sep);
    const sourceId = rest.slice(sep + 1);
    if (surveyId.length === 0 || sourceId.length === 0) {
      return null;
    }
    return { type: "survey_measurement", source_id: sourceId, survey_id: surveyId };
  }
  if (value.startsWith("photo_reading:")) {
    const sourceId = value.slice("photo_reading:".length);
    return sourceId.length > 0 ? { type: "photo_reading", source_id: sourceId } : null;
  }
  return null;
}

export type EligibleWitnessSource = {
  source: FieldWitnessSource;
  label: string;
  value_mm: number;
};

/** Chave quádrupla de uma associação, no molde do servidor, para excluir pares já ligados. */
function witnessKey(
  readingId: string,
  sourceType: FieldWitness["source_type"],
  sourceId: string,
  surveyId: string | null,
): string {
  return `${readingId}|${sourceType}|${sourceId}|${surveyId ?? ""}`;
}

/**
 * As fontes de campo que ainda podem virar testemunha desta leitura: medidas confirmadas dos
 * levantamentos vinculados e valores já confirmados em foto (ACTIVE), menos os pares já
 * associados à leitura. Leitura de máquina sem confirmação NUNCA entra — confirmar o valor é
 * outro ato. A lista nunca é filtrada por âncora nem ordenada por proximidade.
 */
export function eligibleWitnessSources(
  evidence: FieldEvidence,
  witnesses: FieldWitness[],
  readingId: string,
): EligibleWitnessSource[] {
  const taken = new Set(
    witnesses
      .filter((witness) => witness.reading_id === readingId)
      .map((witness) =>
        witnessKey(readingId, witness.source_type, witness.source_id, witness.survey_id),
      ),
  );
  const out: EligibleWitnessSource[] = [];
  for (const survey of evidence.surveys) {
    for (const measurement of survey.measurements) {
      const key = witnessKey(
        readingId,
        "survey_measurement",
        measurement.source_id,
        survey.survey_id,
      );
      if (taken.has(key)) {
        continue;
      }
      out.push({
        source: {
          type: "survey_measurement",
          source_id: measurement.source_id,
          survey_id: survey.survey_id,
        },
        label: `Medida do app · ${metersFromMm(measurement.value_mm)} m · ${survey.name}`,
        value_mm: measurement.value_mm,
      });
    }
  }
  for (const photo of evidence.photos) {
    for (const confirmed of photo.confirmed_values) {
      const key = witnessKey(readingId, "photo_reading", confirmed.confirmation_id, null);
      if (taken.has(key)) {
        continue;
      }
      out.push({
        source: { type: "photo_reading", source_id: confirmed.confirmation_id },
        label: `Valor confirmado em foto · ${metersFromMm(confirmed.value_mm)} m · ${confirmed.confirmed_by}`,
        value_mm: confirmed.value_mm,
      });
    }
  }
  return out;
}

/**
 * O eyebrow de cada bloco de testemunha. Com uma só, "TESTEMUNHA DE CAMPO"; com várias, cada
 * bloco é numerado e diz a origem por extenso — nunca há resumo nem hierarquia entre fontes.
 */
export function witnessEyebrow(
  sourceType: FieldWitness["source_type"],
  index: number,
  total: number,
): string {
  if (total <= 1) {
    return "TESTEMUNHA DE CAMPO";
  }
  const origem =
    sourceType === "survey_measurement" ? "MEDIDA DO APP" : "VALOR CONFIRMADO EM FOTO";
  return `TESTEMUNHA ${index + 1} · ${origem}`;
}

/** O rótulo do segundo valor do confronto, por extenso, escrito ao lado do número. */
export function witnessSourceValueLabel(sourceType: FieldWitness["source_type"]): string {
  return sourceType === "survey_measurement" ? "TRENA EM CAMPO" : "VISOR FOTOGRAFADO";
}

/**
 * Metros a partir de um `Decimal` em milímetros que veio como string. Magnitude sem sinal: a
 * diferença é neutra, e a tela nunca escreve "+"/"−" nem colore o número.
 */
export function witnessMeters(mmDecimal: string): string {
  const parsed = Number(mmDecimal);
  if (!Number.isFinite(parsed)) {
    return "";
  }
  return metersFromMm(Math.abs(parsed));
}

/**
 * As leituras de máquina da foto que ainda não têm valor confirmado (estado 7, "A
 * CONFIRMAR"). Só entram leituras com `id` — sem ele não há `source_reading_id` para
 * confirmar. Uma leitura já confirmada some da lista.
 */
export function pendingPhotoValues(photo: FieldEvidencePhoto): FieldPhotoReading[] {
  const confirmed = new Set(
    photo.confirmed_values.map((value) => value.source_reading_id),
  );
  return photoReadings(photo).filter(
    (reading) => reading.id !== undefined && !confirmed.has(reading.id),
  );
}

/**
 * Milímetros inteiros a partir das dicas de valor/unidade de uma leitura, só para pré-
 * preencher o formulário de confirmação. Aceita vírgula ou ponto decimal; unidade ausente é
 * lida como metros (o app de campo mede em metros). `null` quando não dá para parsear.
 */
export function mmFromValueHint(
  valueHint: string | null | undefined,
  unitHint: string | null | undefined,
): number | null {
  if (valueHint === null || valueHint === undefined) {
    return null;
  }
  const parsed = Number(valueHint.trim().replace(",", "."));
  if (!Number.isFinite(parsed) || parsed < 0) {
    return null;
  }
  const unit = (unitHint ?? "m").trim().toLowerCase();
  const factor = unit === "mm" ? 1 : unit === "cm" ? 10 : 1000;
  return Math.round(parsed * factor);
}
