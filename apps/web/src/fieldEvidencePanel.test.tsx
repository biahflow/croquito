/**
 * Estados do painel de evidência de campo (F-030 T3) renderizados como HTML estático, o
 * padrão de teste de componente do web app (node + `renderToStaticMarkup`, sem jsdom).
 *
 * Cobre os estados do Design Approval Package revisão 3 no escopo da T3: vazio, carregando,
 * sem análise/leitura pulada, recusa de IA, sem papel, e o modal com "Abrir original". A
 * fronteira "foto não mede" é asserida, e nenhum filtro associa foto a leitura.
 */
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import {
  CorrectObservationForm,
  FieldEvidenceBody,
  FieldPhotoModal,
  type FieldEvidenceView,
} from "./fieldEvidencePanel";
import type {
  FieldEvidence,
  FieldEvidencePhoto,
  FieldObservation,
} from "./api";
import { ALL_ANCHORS } from "./fieldEvidence";

const noop = () => {};

function photo(overrides: Partial<FieldEvidencePhoto> = {}): FieldEvidencePhoto {
  return {
    evidence_id: "media-1",
    origin: "survey",
    survey_id: "svy-1",
    sha256: "a".repeat(64),
    mime_type: "image/jpeg",
    anchors: [{ kind: "element", ref_id: "mureta oeste" }],
    anchor_text: null,
    captured_at: "2026-08-19T14:12:00Z",
    url: "https://storage.example/signed/media-1?sig=abc",
    analysis: null,
    classification: null,
    reading_status: "NOT_REQUESTED",
    classification_status: "NOT_REQUESTED",
    confirmed_values: [],
    ...overrides,
  };
}

function readyView(
  evidence: FieldEvidence,
  observations: FieldObservation[] = [],
): FieldEvidenceView {
  return {
    status: "ready",
    evidence,
    photos: evidence.photos,
    anchors: [],
    selectedAnchor: ALL_ANCHORS,
    surveyOptions: [],
    aiNotice: null,
    busy: false,
    editingValueKey: null,
    observations,
  };
}

function render(view: FieldEvidenceView, openPhoto: FieldEvidencePhoto | null = null) {
  return renderToStaticMarkup(
    <FieldEvidenceBody
      view={view}
      openPhoto={openPhoto}
      onSelectAnchor={noop}
      onLinkSurvey={noop}
      onUnlinkSurvey={noop}
      onUploadPhoto={noop}
      onRequestReading={noop}
      onOpenPhoto={noop}
      onClosePhoto={noop}
      onConfirmValueDirect={noop}
      onStartEditingValue={noop}
      onCancelEditingValue={noop}
      onSubmitValue={noop}
      onRequestClassification={noop}
      onRecordObservation={noop}
      onDismissObservation={noop}
      onCorrectObservation={noop}
    />,
  );
}

describe("estados do painel", () => {
  it("carregando mostra esqueleto, nem fotos nem 'não há fotos'", () => {
    const html = render({ status: "loading" });
    expect(html).toContain("Lendo o levantamento");
    expect(html).toContain("esqueleto");
    expect(html).not.toContain("Nenhum levantamento");
  });

  it("vazio oferece vincular e explica a alternativa de foto avulsa", () => {
    const html = render(
      readyView({ job_id: "j", version: 1, surveys: [], photos: [] }),
    );
    expect(html).toContain("Nenhum levantamento vinculado");
    expect(html).toContain("SEM VÍNCULO");
    expect(html).toContain("Subir foto avulsa");
    expect(html).toContain("Vincular");
  });

  it("normal declara que a foto não mede e mostra a âncora", () => {
    const html = render(
      readyView({
        job_id: "j",
        version: 2,
        surveys: [
          {
            survey_id: "svy-1",
            name: "Praça Guaxindiba",
            linked_by: "Ana",
            linked_at: "2026-08-19T10:00:00Z",
            measurements: [],
          },
        ],
        photos: [photo()],
      }),
    );
    expect(html).toContain("não tem escala e não fornece");
    expect(html).toContain("VINCULADO");
    expect(html).toContain("Elemento: mureta oeste");
    expect(html).toContain("O filtro não associa a foto a uma leitura");
  });

  it("sem análise é estado neutro, não erro", () => {
    const html = render(
      readyView({
        job_id: "j",
        version: 2,
        surveys: [],
        photos: [
          photo({ origin: "standalone", anchor_text: "Ponto 3", reading_status: "SKIPPED_DISABLED" }),
        ],
      }),
    );
    expect(html).toContain("LEITURA PULADA");
    expect(html).toContain("processamento pago não está habilitado");
    expect(html).not.toContain("app-alert");
  });

  it("recusa de IA aparece como aviso dentro do painel, sem esconder as fotos", () => {
    const view = readyView({
      job_id: "j",
      version: 2,
      surveys: [],
      photos: [photo()],
    });
    const html = render({
      ...view,
      aiNotice: "A leitura por IA não está habilitada para este cliente.",
    } as FieldEvidenceView);
    expect(html).toContain("app-alert");
    expect(html).toContain("não está habilitada");
    expect(html).toContain("Elemento: mureta oeste");
  });

  it("sem papel mostra a explicação autenticada, não uma tela vazia", () => {
    const html = render({
      status: "forbidden",
      message: "Ver a evidência de campo exige papel de revisão ou de campo, que esta conta não tem.",
    });
    expect(html).toContain("exige papel de revisão");
    expect(html).toContain("app-status");
  });
});

describe("ato 1 do legado: confirmar valor lido (estado 7)", () => {
  const readingPhoto = photo({
    origin: "standalone",
    anchor_text: "Visor da trena",
    reading_status: "PROCESSED",
    analysis: {
      readings: [
        { id: "fpr_1", raw_text: "12,40", value_hint: "12,40", unit_hint: "m" },
      ],
    },
  });

  it("mostra o valor a confirmar com os dois atos, e nunca oferece associar", () => {
    const html = render(
      readyView({ job_id: "j", version: 3, surveys: [], photos: [readingPhoto] }),
    );
    expect(html).toContain("VALOR LIDO NA FOTO — A CONFIRMAR");
    expect(html).toContain("VISOR DA TRENA");
    expect(html).toContain("12,40 m");
    expect(html).toContain("não é testemunha ainda");
    expect(html).toContain("Confirmar o valor");
    expect(html).toContain("Corrigir");
    // Associar é outro ato, em outro painel: aqui nunca aparece.
    expect(html).not.toContain("Associar");
  });

  it("valor já confirmado mostra autoria e a fronteira dos dois atos", () => {
    const confirmedPhoto = photo({
      origin: "standalone",
      anchor_text: "Visor",
      confirmed_values: [
        {
          confirmation_id: "cfm-1",
          source_reading_id: "fpr_1",
          value_mm: 12_400,
          kind: "length",
          raw_text: "12,40",
          confirmed_by: "Ana",
          confirmed_at: "2026-08-19T11:00:00Z",
        },
      ],
    });
    const html = render(
      readyView({ job_id: "j", version: 3, surveys: [], photos: [confirmedPhoto] }),
    );
    expect(html).toContain("VALOR CONFIRMADO EM FOTO");
    expect(html).toContain("Confirmado por Ana");
    expect(html).toContain("a associação à cota é outro ato");
    expect(html).toContain("Corrigir");
    expect(html).not.toContain("Associar");
  });

  it("em edição mostra o formulário de valor e some com o botão direto", () => {
    const view = readyView({
      job_id: "j",
      version: 3,
      surveys: [],
      photos: [readingPhoto],
    });
    const html = render({
      ...view,
      editingValueKey: "standalone:media-1:fpr_1",
    } as FieldEvidenceView);
    expect(html).toContain("Valor em metros");
    expect(html).toContain("Espécie da medida");
    expect(html).toContain("Texto lido no visor");
    expect(html).toContain("Cancelar");
  });
});

describe("rascunho da classificação e observação (estado 8)", () => {
  const draftPhoto = photo({
    origin: "standalone",
    anchor_text: "Alambrado do fundo",
    classification_status: "DRAFT",
    classification: {
      classification: {
        category: "ALAMBRADO",
        description: "Tela de alambrado sobre mureta baixa.",
        topology_notes: ["fecha à direita"],
        confidence: "high",
      },
      lineage: {
        provider: "anthropic",
        model_id: "claude-opus-5",
        prompt: {
          prompt_id: "field-photo-classification",
          prompt_version: "field-photo-classification@1.0.0",
          schema_version: "1.0.0",
        },
      },
    },
  });

  function observation(overrides: Partial<FieldObservation> = {}): FieldObservation {
    return {
      observation_id: "obs-1",
      origin: "standalone",
      evidence_id: "media-1",
      status: "ACTIVE",
      category: "ALAMBRADO",
      description: "Concordo: é alambrado.",
      source: { analysis_id: "an-1", category: "ALAMBRADO" },
      supersedes_observation_id: null,
      recorded_by: "Ana",
      recorded_at: "2026-08-20T13:00:00Z",
      ...overrides,
    };
  }

  it("mostra a proposta com lineage, a fronteira e os dois atos", () => {
    const html = render(
      readyView({ job_id: "j", version: 3, surveys: [], photos: [draftPhoto] }),
    );
    expect(html).toContain("PROPOSTA DA IA — A CONFIRMAR");
    expect(html).toContain("Alambrado");
    expect(html).toContain("Tela de alambrado sobre mureta baixa");
    expect(html).toContain("nenhuma dimensão vem daqui");
    expect(html).toContain("field-photo-classification@1.0.0");
    expect(html).toContain("modelo claude-opus-5");
    expect(html).toContain("Registrar como nota de revisão");
    expect(html).toContain("Descartar");
  });

  it("classificando mostra o carregando, sem os botões de registrar", () => {
    const inFlight = photo({
      origin: "standalone",
      classification_status: "QUEUED",
    });
    const html = render(
      readyView({ job_id: "j", version: 3, surveys: [], photos: [inFlight] }),
    );
    expect(html).toContain("Classificando a foto");
    expect(html).not.toContain("Registrar como nota de revisão");
  });

  it("observação registrada mostra autoria e corrigir, não mais registrar", () => {
    const html = render(
      readyView(
        { job_id: "j", version: 3, surveys: [], photos: [draftPhoto] },
        [observation()],
      ),
    );
    expect(html).toContain("OBSERVAÇÃO REGISTRADA");
    expect(html).toContain("Registrada por Ana");
    expect(html).toContain("Corrigir observação");
    expect(html).not.toContain("Registrar como nota de revisão");
  });

  it("o formulário de correção não pré-preenche a descrição do revisor", () => {
    const html = renderToStaticMarkup(
      <CorrectObservationForm
        currentCategory="ALAMBRADO"
        busy={false}
        onCancel={noop}
        onSubmit={noop}
      />,
    );
    // A categoria vem pré-selecionada (escolha controlada), mas o campo de descrição nasce
    // vazio — nenhuma justificativa é semeada, como em todo o produto.
    expect(html).toContain("Sua observação");
    expect(html).toContain('value=""');
    expect(html).not.toContain("Concordo");
  });

  it("rascunho descartado registra o ato e não reoferece as ações", () => {
    const html = render(
      readyView(
        { job_id: "j", version: 3, surveys: [], photos: [draftPhoto] },
        [observation({ status: "DISMISSED", category: null, description: null })],
      ),
    );
    expect(html).toContain("descartado por Ana");
    expect(html).not.toContain("Registrar como nota de revisão");
    expect(html).not.toContain("Corrigir observação");
  });

  it("sem rascunho e podendo pedir, oferece 'Pedir classificação'", () => {
    const html = render(
      readyView({
        job_id: "j",
        version: 3,
        surveys: [],
        photos: [photo({ origin: "standalone", classification_status: "NOT_REQUESTED" })],
      }),
    );
    expect(html).toContain("Pedir classificação");
  });
});

describe("modal da foto", () => {
  it("preserva o contexto e oferece o original na URL assinada corrente", () => {
    const html = renderToStaticMarkup(
      <FieldPhotoModal photo={photo()} onClose={noop} />,
    );
    expect(html).toContain('role="dialog"');
    expect(html).toContain('aria-modal="true"');
    expect(html).toContain("Abrir original");
    // O href do original é a URL assinada corrente da resposta, não uma guardada.
    expect(html).toContain("https://storage.example/signed/media-1?sig=abc");
    expect(html).toContain('target="_blank"');
    expect(html).toContain("Ela não mede");
  });
});
