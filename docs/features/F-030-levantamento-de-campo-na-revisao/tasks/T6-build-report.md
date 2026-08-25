# T6 — BUILD REPORT

Relatório do Builder para o [Task Contract T6](T6-classificacao-visual.md) da
[F-030](../feature.md). Executado diretamente na `main` (commit `12491f1`), sem push. A
evidência offline está separada da rodada paga real, que só entra após o gate humano de
corpus.

```text
BUILD REPORT

Status: BUILD_COMPLETE

Files changed:
  - services/worker/src/croquito_worker/providers.py
    PromptTask.FIELD_PHOTO_CLASSIFICATION (prompt 1.0.0, schema 1.0.0), template
    dedicado e schema FieldPhotoClassificationOutput: category (MURO|ALAMBRADO|PORTAO|
    PATAMAR|EQUIPAMENTOS|DETALHES|UNKNOWN), description, topology_notes e confidence
    ordinal. extra="forbid" — nenhum campo de medida, dimensão, coordenada ou precisão.
  - services/worker/src/croquito_worker/survey_photo_analysis.py
    run_classification_pass (só braço Anthropic, sem fallback) e
    build_field_evidence_classification_document (artefato field-evidence-classification/1
    com classification, provider_pass/failure_code e lineage; sem campo geométrico).
  - services/worker/src/croquito_worker/local_queue.py
    _handle_field_evidence_analysis aceita task classification, com passe dedicado e
    estados terminais idempotentes (DRAFT no sucesso; reentrega não rechama).
  - services/worker/src/croquito_worker/cli.py
    Subcomando field-photo-classification-eval (offline por padrão; braço real sob gate).
  - services/worker/src/croquito_worker/field_photo_classification_eval.py
    Eval offline determinística (7 categorias, schema/lineage/não-geometria, 3 payloads
    proibidos rejeitados) e harness da rodada real: LIVE_CASE_COUNT=6,
    CALL_RESERVE_USD=0.75, ABSOLUTE_BUDGET_USD=5.00, sem retry e sem rerun seletivo.
  - services/api/src/croquito_api/main.py
    Rota POST /v1/jobs/{id}/field-evidence/photos/{origin}/{evidence_id}/classification
    (202), com gates provider/entitlement/consentimento/kill-switch/versão antes de
    enfileirar. Upload/vínculo nunca enfileira classificação.
  - docs/ai/MODEL_ROUTING.md
    Rota da classificação visual: somente Anthropic claude-opus-5; sem fallback OpenAI.
  - docs/architecture/API_CONTRACT.md
  - tests/api/openapi.snapshot.json
    Contrato e snapshot da rota e do campo classification em FieldEvidencePhoto.
  - tests/worker/test_field_photo_classification_eval.py
  - tests/worker/test_field_evidence_analysis.py
  - tests/worker/test_providers.py
  - tests/api/test_field_evidence.py
  - tests/e2e/test_field_flow.py
    Eval offline 7/7, corpus de exatamente 6 casos distintos, live recusa antes da rede
    sem OpenAI desligado; artefato nasce DRAFT sem medida/geometria/fallback; API exige
    provider+entitlement antes de enfileirar (fila vazia até o ato explícito); prompt não
    geométrico e revisado por humano; hash congelado field-photo-classification@1.0.0.

Validation executed:
  - make test ....................................... exit 0
    Inclui a eval offline de classificação via pytest
    (tests/worker/test_field_photo_classification_eval.py) e os demais testes de worker,
    API e e2e da task.
  - make check ...................................... exit 0 até infra-check
    Ruff/formatação, mypy strict, check_docs, schema_export e drift de contratos verdes.
    O gate final `terraform fmt` (make infra-check) não roda nesta máquina — terraform
    não está instalado; limitação de ambiente, não de código. A T6 não toca infra.
  - rodada paga real ................................ PENDING_HUMAN_GATE
    Só executa após receber seis fotos próprias rotuladas fora do Git, uma chamada por
    item, mesmo candidato (claude-opus-5), teto absoluto US$ 5,00.

Validation skipped: none

Unavailable capabilities:
  - terraform ausente localmente: `make infra-check` não executa; roda no CI.
  - Corpus real de seis fotos rotuladas: ato humano pendente, fora do Git.

Assumptions:
  - A cobertura em CI da eval vem do teste pytest que chama run_offline_classification_eval,
    não de um alvo `check`/`test` que invoque o comando field-photo-classification-eval
    diretamente — mesmo padrão dos demais evals do repo (ex.: transcription-eval).
  - claude-opus-5 é o único candidato; OpenAI permanece desabilitado e o live recusa antes
    da rede se CROQUITO_OPENAI_ARM_ENABLED != false.

Remaining risks:
  - A rodada paga real ainda não foi exercida: os invariantes de custo (reserva 0,75, teto
    5,00, uma chamada por foto) estão cobertos por teste offline, mas o comportamento sob
    a API real da Anthropic só se confirma no gate humano de corpus.

Human decisions required:
  - Fornecer as seis fotos próprias rotuladas (fora do Git) e autorizar a rodada paga até
    US$ 5,00, uma chamada por item, no candidato claude-opus-5.
```
