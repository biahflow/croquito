/**
 * Painel "Evidência de campo" da jornada de revisão (F-030 T3), conforme o Design Approval
 * Package revisão 3. Ele mostra e gerencia a evidência de campo: fotos vinculadas e
 * avulsas, qualidade e leitura textual sob demanda, vínculo de levantamento e upload de
 * foto avulsa, com modal que preserva a revisão e "Abrir original" na URL assinada corrente.
 *
 * Fronteiras que a tela honra:
 * - a foto responde "o que é", não mede — a frase é escrita, não implícita;
 * - nenhuma âncora é inferida e nenhum filtro associa foto a leitura;
 * - "sem análise" é estado neutro, não erro; quem recusa IA é o servidor;
 * - a URL assinada nunca é guardada em estado durável (cada carga traz uma fresca).
 */
import { useCallback, useEffect, useMemo, useState } from "react";

import {
  ApiError,
  confirmFieldPhotoValue,
  getFieldEvidence,
  linkSurveyToJob,
  listCompletedSurveys,
  requestFieldPhotoReading,
  unlinkSurveyFromJob,
  uploadStandaloneFieldPhoto,
  type CompletedSurveySummary,
  type FieldEvidence,
  type FieldEvidencePhoto,
  type FieldPhotoValueDraft,
} from "./api";
import {
  ALL_ANCHORS,
  anchorLabel,
  anchorOptions,
  canRequestReading,
  filterPhotosByAnchor,
  isAnalysisSkipped,
  isReadingInFlight,
  metersFromMm,
  mmFromValueHint,
  pendingPhotoValues,
  photoReadings,
  qualityBadge,
  readingBadge,
  shortInstant,
  surveyOptionLabel,
  type FieldPhotoReading,
  type StateBadge,
} from "./fieldEvidence";
import { measurementKindLabel } from "./labels";

/** As sete espécies de medida que o servidor aceita ao confirmar um valor lido em foto. */
const VALUE_KINDS: FieldPhotoValueDraft["kind"][] = [
  "length",
  "diagonal",
  "width",
  "radius",
  "level",
  "drop",
  "height",
];

const READING_POLL_MS = 2_000;

/** Frase de sem papel (estado 10): o painel inteiro é autenticado por papel. */
const FIELD_EVIDENCE_FORBIDDEN_MESSAGE =
  "Ver a evidência de campo exige papel de revisão ou de campo, que esta conta não tem.";

function aiRefusalMessage(error: ApiError): string {
  if (
    error.code === "AI_PROCESSING_NOT_AUTHORIZED" ||
    error.code === "AI_PROCESSING_ENTITLEMENT_REVOKED"
  ) {
    return (
      "A leitura por IA não está habilitada para este cliente. Ela depende de " +
      "autorização contratual de processamento, administrada por quem responde pela " +
      "plataforma. As fotos e a qualidade continuam disponíveis. Nada foi cobrado e nada " +
      "foi enviado para fora."
    );
  }
  if (error.code === "PROCESSING_UNAVAILABLE" || error.code === "PROVIDER_UNAVAILABLE") {
    return (
      "O processamento de IA está temporariamente indisponível. As fotos e a qualidade " +
      "continuam disponíveis; tente pedir a leitura de novo mais tarde."
    );
  }
  return error.message;
}

function StateChip({ badge }: { badge: StateBadge }) {
  return <span className={badge.tone}>{badge.label}</span>;
}

type ValueDraftSeed = {
  source_reading_id: string;
  value_mm: number | null;
  kind: FieldPhotoValueDraft["kind"];
  raw_text: string;
};

/**
 * Formulário de confirmação/correção de um valor lido em foto (Ato 1 do legado). Estado
 * local próprio, pré-preenchido a partir da dica de leitura ou do valor já confirmado. O
 * valor é digitado em metros e convertido para milímetros inteiros só no envio.
 */
function ValueConfirmForm({
  seed,
  busy,
  onCancel,
  onSubmit,
}: {
  seed: ValueDraftSeed;
  busy: boolean;
  onCancel: () => void;
  onSubmit: (draft: FieldPhotoValueDraft) => void;
}) {
  const [meters, setMeters] = useState(
    seed.value_mm !== null ? metersFromMm(seed.value_mm) : "",
  );
  const [kind, setKind] = useState<FieldPhotoValueDraft["kind"]>(seed.kind);
  const [rawText, setRawText] = useState(seed.raw_text);

  const valueMm = mmFromValueHint(meters, "m");
  const trimmed = rawText.trim();
  const canSubmit =
    valueMm !== null && trimmed.length >= 1 && trimmed.length <= 200 && !busy;

  return (
    <form
      className="value-confirm-form"
      onSubmit={(event) => {
        event.preventDefault();
        if (valueMm === null || trimmed.length < 1) {
          return;
        }
        onSubmit({
          source_reading_id: seed.source_reading_id,
          value_mm: valueMm,
          kind,
          raw_text: trimmed,
        });
      }}
    >
      <label>
        Valor em metros
        <input
          type="text"
          inputMode="decimal"
          value={meters}
          placeholder="ex.: 12,40"
          onChange={(event) => setMeters(event.target.value)}
        />
      </label>
      <label>
        Espécie da medida
        <select
          value={kind}
          onChange={(event) =>
            setKind(event.target.value as FieldPhotoValueDraft["kind"])
          }
        >
          {VALUE_KINDS.map((option) => (
            <option key={option} value={option}>
              {measurementKindLabel(option)}
            </option>
          ))}
        </select>
      </label>
      <label>
        Texto lido no visor
        <input
          type="text"
          maxLength={200}
          value={rawText}
          onChange={(event) => setRawText(event.target.value)}
        />
      </label>
      <div className="acoes">
        <button type="submit" className="button button-primary" disabled={!canSubmit}>
          Confirmar o valor
        </button>
        <button
          type="button"
          className="button button-secondary"
          disabled={busy}
          onClick={onCancel}
        >
          Cancelar
        </button>
      </div>
    </form>
  );
}

/**
 * Ato 1 do caminho legado (estado 7): confirmar o valor lido por máquina numa foto. Mostra
 * as leituras ainda "A CONFIRMAR" e os valores já confirmados. Confirmar aqui é um ato;
 * associar à cota é outro, no painel da leitura — este bloco nunca oferece associação.
 */
export function FieldPhotoValueBlock({
  photo,
  editingSourceReadingId,
  busy,
  onConfirmDirect,
  onStartEditing,
  onCancelEditing,
  onSubmitValue,
}: {
  photo: FieldEvidencePhoto;
  editingSourceReadingId: string | null;
  busy: boolean;
  onConfirmDirect: (reading: FieldPhotoReading) => void;
  onStartEditing: (sourceReadingId: string) => void;
  onCancelEditing: () => void;
  onSubmitValue: (draft: FieldPhotoValueDraft) => void;
}) {
  const pending = pendingPhotoValues(photo);
  if (pending.length === 0 && photo.confirmed_values.length === 0) {
    return null;
  }
  return (
    <>
      {pending.map((reading) => {
        const readingId = reading.id;
        if (readingId === undefined) {
          return null;
        }
        const parsed = mmFromValueHint(reading.value_hint, reading.unit_hint);
        const editing = editingSourceReadingId === readingId;
        return (
          <div className="testemunha" key={`pending:${readingId}`}>
            <p className="eyebrow">VALOR LIDO NA FOTO — A CONFIRMAR</p>
            <div className="confronto">
              <span className="valor">
                <span>VISOR DA TRENA</span>
                <b>
                  {parsed !== null ? `${metersFromMm(parsed)} m` : `"${reading.raw_text}"`}
                </b>
              </span>
            </div>
            <small className="field-hint">
              Número lido por máquina no visor da foto. Ele <strong>não é testemunha
              ainda</strong>: confirmar o valor é um ato, associá-lo a uma cota é outro.
            </small>
            {editing ? (
              <ValueConfirmForm
                seed={{
                  source_reading_id: readingId,
                  value_mm: parsed,
                  kind: "length",
                  raw_text: reading.raw_text,
                }}
                busy={busy}
                onCancel={onCancelEditing}
                onSubmit={onSubmitValue}
              />
            ) : (
              <div className="acoes">
                {parsed !== null ? (
                  <button
                    type="button"
                    className="button button-primary"
                    disabled={busy}
                    onClick={() => onConfirmDirect(reading)}
                  >
                    Confirmar o valor
                  </button>
                ) : null}
                <button
                  type="button"
                  className="button button-secondary"
                  disabled={busy}
                  onClick={() => onStartEditing(readingId)}
                >
                  {parsed !== null ? "Corrigir" : "Informar o valor"}
                </button>
              </div>
            )}
          </div>
        );
      })}

      {photo.confirmed_values.map((confirmed) => {
        const editing = editingSourceReadingId === confirmed.source_reading_id;
        return (
          <div className="testemunha" key={`confirmed:${confirmed.confirmation_id}`}>
            <p className="eyebrow">VALOR CONFIRMADO EM FOTO</p>
            <div className="confronto">
              <span className="valor">
                <span>VISOR FOTOGRAFADO</span>
                <b>{metersFromMm(confirmed.value_mm)} m</b>
              </span>
            </div>
            <small className="field-hint">
              Confirmado por {confirmed.confirmed_by} em {shortInstant(confirmed.confirmed_at)}.
              Confirmado aqui, associado lá: a associação à cota é outro ato, no painel da
              leitura.
            </small>
            {editing ? (
              <ValueConfirmForm
                seed={{
                  source_reading_id: confirmed.source_reading_id,
                  value_mm: confirmed.value_mm,
                  kind: (VALUE_KINDS as string[]).includes(confirmed.kind)
                    ? (confirmed.kind as FieldPhotoValueDraft["kind"])
                    : "length",
                  raw_text: confirmed.raw_text,
                }}
                busy={busy}
                onCancel={onCancelEditing}
                onSubmit={onSubmitValue}
              />
            ) : (
              <div className="acoes">
                <button
                  type="button"
                  className="button button-secondary"
                  disabled={busy}
                  onClick={() => onStartEditing(confirmed.source_reading_id)}
                >
                  Corrigir
                </button>
              </div>
            )}
          </div>
        );
      })}
    </>
  );
}

/**
 * Cartão de uma foto: amostra, âncora declarada, pastilhas de qualidade e leitura, a
 * leitura textual quando existe, e o ato de pedir leitura quando cabe. Nada aqui mede.
 */
export function FieldPhotoCard({
  photo,
  busy,
  editingValueKey,
  onOpen,
  onRequestReading,
  onConfirmValueDirect,
  onStartEditingValue,
  onCancelEditingValue,
  onSubmitValue,
}: {
  photo: FieldEvidencePhoto;
  busy: boolean;
  editingValueKey: string | null;
  onOpen: (photo: FieldEvidencePhoto) => void;
  onRequestReading: (photo: FieldEvidencePhoto) => void;
  onConfirmValueDirect: (photo: FieldEvidencePhoto, reading: FieldPhotoReading) => void;
  onStartEditingValue: (photo: FieldEvidencePhoto, sourceReadingId: string) => void;
  onCancelEditingValue: () => void;
  onSubmitValue: (photo: FieldEvidencePhoto, draft: FieldPhotoValueDraft) => void;
}) {
  const quality = qualityBadge(photo);
  const reading = readingBadge(photo);
  const readings = photoReadings(photo);
  const captured = shortInstant(photo.captured_at);
  const valuePrefix = `${photo.origin}:${photo.evidence_id}:`;
  const editingSourceReadingId =
    editingValueKey !== null && editingValueKey.startsWith(valuePrefix)
      ? editingValueKey.slice(valuePrefix.length)
      : null;
  return (
    <li className="foto">
      <button
        type="button"
        className="foto-amostra-button"
        onClick={() => onOpen(photo)}
        aria-label={`Ampliar foto — ${anchorLabel(photo)}`}
      >
        <span className="foto-amostra" aria-hidden="true" />
      </button>
      <span className="ancora">{anchorLabel(photo)}</span>
      <span className="foto-meta">
        {quality ? <StateChip badge={quality} /> : null}
        {reading ? <StateChip badge={reading} /> : null}
        {photo.origin === "standalone" ? (
          <span className="neutral">AVULSA</span>
        ) : null}
        {captured ? <span className="field-hint">{captured}</span> : null}
      </span>
      {isAnalysisSkipped(photo) ? (
        <p className="leitura">
          A leitura de texto não rodou — o processamento pago não está habilitado para
          este cliente. Estado honesto, não erro.
        </p>
      ) : null}
      {readings.length > 0 ? (
        <p className="leitura">
          <strong>Lido na foto:</strong>{" "}
          {readings.map((item) => `"${item.raw_text}"`).join(", ")} — leitura de texto
          escrito, não medida.
        </p>
      ) : null}
      <div className="acoes">
        <button
          type="button"
          className="button button-secondary"
          onClick={() => onOpen(photo)}
        >
          Ampliar foto
        </button>
        {canRequestReading(photo) ? (
          <button
            type="button"
            className="button button-secondary"
            disabled={busy}
            onClick={() => onRequestReading(photo)}
          >
            Pedir leitura de texto
          </button>
        ) : null}
        {isReadingInFlight(photo) ? (
          <span className="field-hint">Lendo o texto da foto…</span>
        ) : null}
      </div>
      <FieldPhotoValueBlock
        photo={photo}
        editingSourceReadingId={editingSourceReadingId}
        busy={busy}
        onConfirmDirect={(reading) => onConfirmValueDirect(photo, reading)}
        onStartEditing={(sourceReadingId) => onStartEditingValue(photo, sourceReadingId)}
        onCancelEditing={onCancelEditingValue}
        onSubmitValue={(draft) => onSubmitValue(photo, draft)}
      />
    </li>
  );
}

/**
 * Modal da foto ampliada (estado 1b). Preserva a revisão por baixo e oferece o arquivo
 * original em nova aba, com a URL assinada corrente — nunca uma guardada.
 */
export function FieldPhotoModal({
  photo,
  onClose,
}: {
  photo: FieldEvidencePhoto;
  onClose: () => void;
}) {
  return (
    <div className="modal-overlay" role="presentation" onClick={onClose}>
      <div
        className="modal-card"
        role="dialog"
        aria-modal="true"
        aria-label={`Foto de campo — ${anchorLabel(photo)}`}
        onClick={(event) => event.stopPropagation()}
      >
        <div className="panel-heading">
          <div>
            <p className="eyebrow">{anchorLabel(photo).toUpperCase()}</p>
            <h2 className="modal-title">
              Foto de campo · {shortInstant(photo.captured_at)}
            </h2>
          </div>
          <button
            type="button"
            className="button button-secondary"
            onClick={onClose}
          >
            Fechar
          </button>
        </div>
        <img
          className="modal-media"
          src={photo.url}
          alt={`Foto de campo ancorada em ${anchorLabel(photo)}`}
          draggable={false}
        />
        <div className="modal-actions">
          <span className="field-hint">
            A foto responde o que é. Ela não mede: nada daqui vira cota, entidade ou
            precisão.
          </span>
          <a
            className="button button-secondary"
            href={photo.url}
            target="_blank"
            rel="noopener noreferrer"
          >
            Abrir original ↗
          </a>
        </div>
      </div>
    </div>
  );
}

export type FieldEvidenceView =
  | { status: "loading" }
  | { status: "forbidden"; message: string }
  | { status: "error"; message: string }
  | {
      status: "ready";
      evidence: FieldEvidence;
      photos: FieldEvidencePhoto[];
      anchors: string[];
      selectedAnchor: string;
      surveyOptions: CompletedSurveySummary[];
      aiNotice: string | null;
      busy: boolean;
      editingValueKey: string | null;
    };

/**
 * Corpo puro do painel: função só do `view` e dos handlers, sem efeito nem fetch — é o que
 * os testes renderizam para cobrir cada estado (vazio, carregando, sem análise, recusa,
 * sem papel). O container abaixo calcula o `view` e passa os atos.
 */
export function FieldEvidenceBody({
  view,
  openPhoto,
  onSelectAnchor,
  onLinkSurvey,
  onUnlinkSurvey,
  onUploadPhoto,
  onRequestReading,
  onOpenPhoto,
  onClosePhoto,
  onConfirmValueDirect,
  onStartEditingValue,
  onCancelEditingValue,
  onSubmitValue,
}: {
  view: FieldEvidenceView;
  openPhoto: FieldEvidencePhoto | null;
  onSelectAnchor: (anchor: string) => void;
  onLinkSurvey: (surveyId: string) => void;
  onUnlinkSurvey: (surveyId: string) => void;
  onUploadPhoto: (file: File, anchorText: string) => void;
  onRequestReading: (photo: FieldEvidencePhoto) => void;
  onOpenPhoto: (photo: FieldEvidencePhoto) => void;
  onClosePhoto: () => void;
  onConfirmValueDirect: (photo: FieldEvidencePhoto, reading: FieldPhotoReading) => void;
  onStartEditingValue: (photo: FieldEvidencePhoto, sourceReadingId: string) => void;
  onCancelEditingValue: () => void;
  onSubmitValue: (photo: FieldEvidencePhoto, draft: FieldPhotoValueDraft) => void;
}) {
  if (view.status === "loading") {
    return (
      <section className="panel field-evidence-panel" aria-label="Evidência de campo">
        <div className="panel-heading">
          <div>
            <p className="eyebrow">EVIDÊNCIA DE CAMPO</p>
            <h2 className="panel-title">Lendo o levantamento…</h2>
          </div>
        </div>
        <div className="panel-body" aria-hidden="true">
          <div className="esqueleto" style={{ width: "58%" }} />
          <div className="esqueleto" style={{ width: "84%" }} />
          <div className="esqueleto" style={{ width: "37%" }} />
        </div>
      </section>
    );
  }

  if (view.status === "forbidden") {
    return (
      <section className="panel field-evidence-panel" aria-label="Evidência de campo">
        <p className="app-status" role="status">
          {view.message}
        </p>
      </section>
    );
  }

  if (view.status === "error") {
    return (
      <section className="panel field-evidence-panel" aria-label="Evidência de campo">
        <p className="app-alert" role="alert">
          {view.message}
        </p>
      </section>
    );
  }

  const { evidence, photos } = view;
  const linked = evidence.surveys.length > 0;
  const totalPhotos = evidence.photos.length;
  const hasAnyPhoto = totalPhotos > 0;

  return (
    <section className="panel field-evidence-panel" aria-label="Evidência de campo">
      <div className="panel-heading">
        <div>
          <p className="eyebrow">EVIDÊNCIA DE CAMPO</p>
          <h2 className="panel-title">
            {linked
              ? `Levantamento vinculado · ${totalPhotos} ${
                  totalPhotos === 1 ? "foto" : "fotos"
                }`
              : hasAnyPhoto
                ? `Fotos avulsas · ${totalPhotos} ${
                    totalPhotos === 1 ? "foto" : "fotos"
                  }`
                : "Nenhum levantamento vinculado"}
          </h2>
        </div>
        <span className={linked ? "ready" : "neutral"}>
          {linked ? "VINCULADO" : "SEM VÍNCULO"}
        </span>
      </div>
      <div className="panel-body">
        <p className="field-hint field-evidence-boundary">
          A foto responde <strong>o que é</strong>. Ela não tem escala e não fornece
          medida — nada daqui vira cota, entidade ou precisão.
        </p>

        {view.aiNotice ? (
          <p className="app-alert" role="alert">
            {view.aiNotice}
          </p>
        ) : null}

        {hasAnyPhoto ? (
          <div className="filtro">
            <label>
              Filtrar pela âncora declarada
              <select
                value={view.selectedAnchor}
                onChange={(event) => onSelectAnchor(event.target.value)}
              >
                <option value={ALL_ANCHORS}>Todas as fotos</option>
                {view.anchors.map((anchor) => (
                  <option key={anchor} value={anchor}>
                    {anchor}
                  </option>
                ))}
              </select>
            </label>
            <span className="field-hint">
              O filtro não associa a foto a uma leitura.
            </span>
          </div>
        ) : null}

        {hasAnyPhoto ? (
          <ul className="fotos">
            {photos.map((photo) => (
              <FieldPhotoCard
                key={`${photo.origin}:${photo.evidence_id}`}
                photo={photo}
                busy={view.busy}
                editingValueKey={view.editingValueKey}
                onOpen={onOpenPhoto}
                onRequestReading={onRequestReading}
                onConfirmValueDirect={onConfirmValueDirect}
                onStartEditingValue={onStartEditingValue}
                onCancelEditingValue={onCancelEditingValue}
                onSubmitValue={onSubmitValue}
              />
            ))}
          </ul>
        ) : (
          <p className="field-hint">
            Esta prancha não está ligada a nenhum levantamento de campo. Vincular traz as
            fotos que o técnico ancorou; sem isso, dá para subir fotos avulsas aqui mesmo.
          </p>
        )}

        <LinkAndUploadForm
          surveyOptions={view.surveyOptions}
          linkedSurveys={evidence.surveys.map((survey) => ({
            survey_id: survey.survey_id,
            name: survey.name,
          }))}
          busy={view.busy}
          onLinkSurvey={onLinkSurvey}
          onUnlinkSurvey={onUnlinkSurvey}
          onUploadPhoto={onUploadPhoto}
        />
      </div>

      {openPhoto ? (
        <FieldPhotoModal photo={openPhoto} onClose={onClosePhoto} />
      ) : null}
    </section>
  );
}

/**
 * Vincular levantamento e subir foto avulsa: dois atos, cada um com o estado de formulário
 * próprio. A âncora da foto avulsa é declarada pelo revisor, obrigatória, nunca inferida.
 */
export function LinkAndUploadForm({
  surveyOptions,
  linkedSurveys,
  busy,
  onLinkSurvey,
  onUnlinkSurvey,
  onUploadPhoto,
}: {
  surveyOptions: CompletedSurveySummary[];
  linkedSurveys: { survey_id: string; name: string }[];
  busy: boolean;
  onLinkSurvey: (surveyId: string) => void;
  onUnlinkSurvey: (surveyId: string) => void;
  onUploadPhoto: (file: File, anchorText: string) => void;
}) {
  const [surveyId, setSurveyId] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [anchorText, setAnchorText] = useState("");

  const canUpload = file !== null && anchorText.trim().length > 0 && !busy;

  return (
    <div className="field-evidence-forms">
      <div className="vinculo-form">
        <label>
          Vincular levantamento
          <select
            value={surveyId}
            onChange={(event) => setSurveyId(event.target.value)}
          >
            <option value="">Escolha um levantamento concluído…</option>
            {surveyOptions.map((survey) => (
              <option key={survey.survey_id} value={survey.survey_id}>
                {surveyOptionLabel(survey.name, survey.photo_count)}
              </option>
            ))}
          </select>
        </label>
        <button
          type="button"
          className="button button-primary"
          disabled={surveyId === "" || busy}
          onClick={() => onLinkSurvey(surveyId)}
        >
          Vincular
        </button>
      </div>

      {linkedSurveys.length > 0 ? (
        <ul className="linked-surveys">
          {linkedSurveys.map((survey) => (
            <li key={survey.survey_id} className="linked-survey">
              <span>{survey.name}</span>
              <button
                type="button"
                className="button button-secondary"
                disabled={busy}
                onClick={() => onUnlinkSurvey(survey.survey_id)}
              >
                Desvincular
              </button>
            </li>
          ))}
        </ul>
      ) : null}

      <form
        className="upload-avulsa"
        onSubmit={(event) => {
          event.preventDefault();
          if (file && anchorText.trim().length > 0) {
            onUploadPhoto(file, anchorText.trim());
            setFile(null);
            setAnchorText("");
          }
        }}
      >
        <label>
          Foto avulsa (JPEG, PNG ou WebP)
          <input
            type="file"
            accept="image/jpeg,image/png,image/webp"
            onChange={(event) => setFile(event.target.files?.[0] ?? null)}
          />
        </label>
        <label>
          Âncora declarada
          <input
            type="text"
            maxLength={500}
            value={anchorText}
            placeholder="ex.: Elemento: mureta oeste"
            onChange={(event) => setAnchorText(event.target.value)}
          />
        </label>
        <button
          type="submit"
          className="button button-secondary"
          disabled={!canUpload}
        >
          Subir foto avulsa
        </button>
      </form>
    </div>
  );
}

/**
 * Container do painel: mantém o estado da evidência, faz as cargas e mutações e traduz as
 * recusas do servidor em estado neutro ou aviso. Ele não decide autorização — só mostra o
 * que a API respondeu.
 */
export function FieldEvidencePanel({
  accessToken,
  jobId,
}: {
  accessToken: string;
  jobId: string;
}) {
  const [evidence, setEvidence] = useState<FieldEvidence | null>(null);
  const [loading, setLoading] = useState(true);
  const [forbidden, setForbidden] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [aiNotice, setAiNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [selectedAnchor, setSelectedAnchor] = useState(ALL_ANCHORS);
  const [surveyOptions, setSurveyOptions] = useState<CompletedSurveySummary[]>([]);
  const [openPhotoKey, setOpenPhotoKey] = useState<string | null>(null);
  // Qual valor lido está em edição: `${origin}:${evidence_id}:${source_reading_id}`.
  const [editingValueKey, setEditingValueKey] = useState<string | null>(null);

  const load = useCallback(
    async (options?: { silent?: boolean }) => {
      if (!options?.silent) {
        setLoading(true);
      }
      try {
        const next = await getFieldEvidence(accessToken, jobId);
        setEvidence(next);
        setForbidden(false);
        setErrorMessage(null);
      } catch (error) {
        if (error instanceof ApiError && error.status === 403) {
          setForbidden(true);
          setErrorMessage(FIELD_EVIDENCE_FORBIDDEN_MESSAGE);
        } else {
          setErrorMessage(
            error instanceof Error
              ? error.message
              : "Não foi possível carregar a evidência de campo.",
          );
        }
      } finally {
        if (!options?.silent) {
          setLoading(false);
        }
      }
    },
    [accessToken, jobId],
  );

  useEffect(() => {
    void load();
  }, [load]);

  // Levantamentos disponíveis para vincular: carga única, sem bloquear o painel se falhar.
  useEffect(() => {
    let alive = true;
    void (async () => {
      try {
        const page = await listCompletedSurveys(accessToken);
        if (alive) {
          setSurveyOptions(page.items);
        }
      } catch {
        // A lista de vínculo é auxiliar: sua falha não derruba a evidência já carregada.
      }
    })();
    return () => {
      alive = false;
    };
  }, [accessToken, jobId]);

  // Polling enquanto uma leitura está na fila: a leitura chega no próximo GET, com URL
  // assinada fresca. Para quando nenhuma foto estiver mais lendo.
  const anyReadingInFlight = useMemo(
    () => (evidence?.photos ?? []).some(isReadingInFlight),
    [evidence],
  );
  useEffect(() => {
    if (!anyReadingInFlight) {
      return;
    }
    const timer = window.setTimeout(() => {
      void load({ silent: true });
    }, READING_POLL_MS);
    return () => window.clearTimeout(timer);
  }, [anyReadingInFlight, load, evidence]);

  const runMutation = useCallback(async (action: () => Promise<FieldEvidence>) => {
    setBusy(true);
    setErrorMessage(null);
    try {
      const next = await action();
      setEvidence(next);
    } catch (error) {
      setErrorMessage(
        error instanceof Error ? error.message : "A ação não foi concluída.",
      );
    } finally {
      setBusy(false);
    }
  }, []);

  const baseVersion = evidence?.version ?? 0;

  const onLinkSurvey = useCallback(
    (surveyId: string) =>
      void runMutation(() =>
        linkSurveyToJob(accessToken, jobId, surveyId, baseVersion),
      ),
    [accessToken, jobId, baseVersion, runMutation],
  );

  const onUnlinkSurvey = useCallback(
    (surveyId: string) =>
      void runMutation(() =>
        unlinkSurveyFromJob(accessToken, jobId, surveyId, baseVersion),
      ),
    [accessToken, jobId, baseVersion, runMutation],
  );

  const onUploadPhoto = useCallback(
    (file: File, anchorText: string) =>
      void runMutation(() =>
        uploadStandaloneFieldPhoto(
          accessToken,
          jobId,
          baseVersion,
          file,
          anchorText,
        ),
      ),
    [accessToken, jobId, baseVersion, runMutation],
  );

  const onRequestReading = useCallback(
    async (photo: FieldEvidencePhoto) => {
      setBusy(true);
      setAiNotice(null);
      try {
        await requestFieldPhotoReading(
          accessToken,
          jobId,
          photo.origin,
          photo.evidence_id,
          baseVersion,
        );
        await load({ silent: true });
      } catch (error) {
        if (error instanceof ApiError) {
          setAiNotice(aiRefusalMessage(error));
        } else {
          setErrorMessage(
            error instanceof Error ? error.message : "O pedido de leitura falhou.",
          );
        }
      } finally {
        setBusy(false);
      }
    },
    [accessToken, jobId, baseVersion, load],
  );

  const onConfirmValue = useCallback(
    async (photo: FieldEvidencePhoto, draft: FieldPhotoValueDraft) => {
      setBusy(true);
      setErrorMessage(null);
      try {
        const next = await confirmFieldPhotoValue(
          accessToken,
          jobId,
          photo.origin,
          photo.evidence_id,
          baseVersion,
          draft,
        );
        setEvidence(next);
        setEditingValueKey(null);
      } catch (error) {
        if (error instanceof ApiError && error.status === 409) {
          await load({ silent: true });
          setErrorMessage(
            "A evidência mudou enquanto você confirmava o valor. Recarreguei a versão " +
              "atual; confira e confirme de novo.",
          );
        } else {
          setErrorMessage(
            error instanceof Error
              ? error.message
              : "A confirmação do valor não foi concluída.",
          );
        }
      } finally {
        setBusy(false);
      }
    },
    [accessToken, jobId, baseVersion, load],
  );

  const onConfirmValueDirect = useCallback(
    (photo: FieldEvidencePhoto, reading: FieldPhotoReading) => {
      if (reading.id === undefined) {
        return;
      }
      const valueMm = mmFromValueHint(reading.value_hint, reading.unit_hint);
      if (valueMm === null) {
        setEditingValueKey(`${photo.origin}:${photo.evidence_id}:${reading.id}`);
        return;
      }
      void onConfirmValue(photo, {
        source_reading_id: reading.id,
        value_mm: valueMm,
        kind: "length",
        raw_text: reading.raw_text,
      });
    },
    [onConfirmValue],
  );

  const photos = evidence?.photos ?? [];
  const filtered = filterPhotosByAnchor(photos, selectedAnchor);
  const openPhoto =
    openPhotoKey === null
      ? null
      : (photos.find(
          (photo) => `${photo.origin}:${photo.evidence_id}` === openPhotoKey,
        ) ?? null);

  const view: FieldEvidenceView = loading
    ? { status: "loading" }
    : forbidden
      ? { status: "forbidden", message: errorMessage ?? "" }
      : evidence === null
        ? {
            status: "error",
            message: errorMessage ?? "Não foi possível carregar a evidência de campo.",
          }
        : {
            status: "ready",
            evidence,
            photos: filtered,
            anchors: anchorOptions(photos),
            selectedAnchor,
            surveyOptions,
            aiNotice,
            busy,
            editingValueKey,
          };

  return (
    <FieldEvidenceBody
      view={view}
      openPhoto={openPhoto}
      onSelectAnchor={setSelectedAnchor}
      onLinkSurvey={onLinkSurvey}
      onUnlinkSurvey={onUnlinkSurvey}
      onUploadPhoto={onUploadPhoto}
      onRequestReading={(photo) => void onRequestReading(photo)}
      onOpenPhoto={(photo) =>
        setOpenPhotoKey(`${photo.origin}:${photo.evidence_id}`)
      }
      onClosePhoto={() => setOpenPhotoKey(null)}
      onConfirmValueDirect={onConfirmValueDirect}
      onStartEditingValue={(photo, sourceReadingId) =>
        setEditingValueKey(`${photo.origin}:${photo.evidence_id}:${sourceReadingId}`)
      }
      onCancelEditingValue={() => setEditingValueKey(null)}
      onSubmitValue={(photo, draft) => void onConfirmValue(photo, draft)}
    />
  );
}
