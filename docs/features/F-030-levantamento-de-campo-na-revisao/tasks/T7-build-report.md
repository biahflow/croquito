# T7 — BUILD REPORT

Relatório do Builder para o [Task Contract T7](T7-observacoes-de-campo.md) da
[F-030](../feature.md). Executado na branch `feat/f-030-t5-t7`, sem push.

```text
BUILD REPORT

Status: BUILD_COMPLETE

Files changed:
  - services/api/src/croquito_api/main.py
    Modelos FieldObservationCategory/Source/Response/Command; rota POST
    /v1/jobs/{id}/review/field-observations no molde de mutate_review_witnesses (registrar,
    corrigir append-only com supersedes, descartar como entrada DISMISSED); campo
    field_observations em ReviewResponse e em _review_response; helper
    _field_observation_source (copia lineage do artefato, nunca do cliente). Nenhuma cena
    nova, nenhum scene_revision_id alterado.
  - docs/architecture/API_CONTRACT.md
    Seção da rota e do campo field_observations do GET review.
  - tests/api/openapi.snapshot.json
    Snapshot regenerado com a rota e os três modelos.
  - tests/api/test_review_field_observations.py
    Registrar não toca cena/exportação; corrigir preserva a proposta da IA; descartar não
    apaga a classificação; replay idempotente + 409; papel 403 / tenant 404; erros nomeados.
  - apps/web/src/api.ts
    Tipos FieldObservation/Source/Category/Command; campo field_observations em Review;
    submitFieldObservation e requestFieldPhotoClassification.
  - apps/web/src/fieldEvidence.ts
    classificationDraft, classificationLineage, predicados de estado da classificação,
    activeObservationFor, draftHandled, FIELD_OBSERVATION_CATEGORIES.
  - apps/web/src/fieldEvidencePanel.tsx
    ClassificationDraftBlock (estado 8) + CorrectObservationForm no FieldPhotoCard; props
    review/onReviewMutated e handlers de classificação/observação no container; polling
    estendido para a classificação em fila.
  - apps/web/src/CroquiApp.tsx
    Passa review e setReview ao painel de evidência.
  - apps/web/src/fieldEvidence.test.ts
    Puras da classificação/observação + transporte de submitFieldObservation e
    requestFieldPhotoClassification (Idempotency-Key, base_version, 409, sem cena no corpo).
  - apps/web/src/fieldEvidencePanel.test.tsx
    Estado 8: proposta com lineage e fronteira, classificando, registrada sem "Registrar",
    descartada sem ações, correção sem descrição pré-preenchida, "Pedir classificação".

Validation executed:
  - pytest tests/api/test_review_field_observations.py
           tests/api/test_review_field_witnesses.py
           tests/api/test_field_evidence.py
           tests/api/test_openapi_contract.py ...... exit 0 (31 passed)
  - mypy strict (135 fontes) ...................... exit 0
  - ruff check main.py ............................ exit 0
  - npm --workspace @croquito/web run test ........ exit 0 (1134 passed)
  - npm --workspace @croquito/web run build ....... exit 0
  - make check ................................... green até infra-check (terraform ausente
    no ambiente — nenhuma mudança em infra/)
  - make test (suíte completa) ................... rodada em execução no fechamento; os
    subconjuntos impactados (api de campo, contrato, web) passaram

Validation skipped: terraform fmt (binário ausente no ambiente; nenhuma mudança em infra)

Unavailable capabilities: terraform CLI

Assumptions:
  - A observação sempre nasce de um rascunho de classificação em DRAFT (o servidor exige a
    análise task=classification em DRAFT com artefato); o rascunho DRAFT garante categoria e
    lineage presentes.
  - A `source` da observação (categoria proposta e lineage) é copiada do artefato pelo
    servidor; o revisor pode registrar uma categoria diferente da proposta, e a proposta fica
    preservada em source.category.
  - Descartar grava uma entrada DISMISSED versionada (registro do ato), não uma observação
    ativa, para a UI não reexibir o rascunho e o replay idempotente funcionar; a classificação
    e a evidência permanecem intactas.

Remaining risks:
  - A primeira rodada paga real da classificação (T6) segue PENDING_HUMAN_GATE e não afeta
    esta UI, que só exibe rascunho e registra/descarta.

Human decisions required: none
```
