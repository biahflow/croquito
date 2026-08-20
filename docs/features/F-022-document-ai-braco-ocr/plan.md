# F-022 — Plano de execução

```text
FEATURE EXECUTION PLAN

feature_id: F-022
goal: braço OCR da suite hospedada montável como Document AI por configuração
      (CROQUITO_DOCAI_PROCESSOR), Cloud Vision permanecendo o default sem o env,
      com contrato OcrOutput intacto e docs de vendor atualizados
assumptions:
  - OcrOutput/OcrLineOutput (providers.py:471-479) e a corroboração em
    provider_review.py:195-229 não mudam — o adapter novo produz o mesmo shape
  - o hash congelado do prompt `ocr` (test_providers.py:1989) é do template da
    tarefa, não do vendor — não muda
  - google-auth já é dependência (pyproject.toml:15-19); Document AI via REST não
    precisa de SDK novo
  - precedente de substituição: ADR-0035 D1 (classe fica, suite deixa de montar)
risks:
  - _ocr_failure (providers.py:937-971) fixa o nome gcp_vision nos logs — precisa
    parametrizar sem quebrar os testes de log existentes
  - granularidade de linha muda (parágrafo→linha de layout); corroboração por
    interseção tolera, mas o eval comparativo pago é o gate de promoção (fora deste
    plano, gate humano)
  - bbox do DocAI vem em normalizedVertices (polígono) — conversão para o
    NormalizedBox retangular precisa recusar polígono degenerado, nunca inventar

tasks:
  - id: T1
    role: builder
    goal: adapter GcpDocumentAiOcrAdapter + montagem por configuração + testes
    scope: services/worker/src/croquito_worker/providers.py,
           tests/worker/test_providers.py
    out_of_scope: provider_review.py, ocr_eval.py, fixtures sintéticas (continuam
                  em GCP_VISION), docs (T2), infra/provisionamento
    expected_areas: services/worker, tests
    acceptance_criteria: ver tasks/T1-adapter-docai.md
    depends_on: []
    validation: make check + make test + make provider-contract-demo + make ocr-eval
    required_capabilities: READ, WRITE, VALIDATE
    risk: arquivo grande vivo (~2800 linhas), enum e logger compartilhados
    relative_effort: M
  - id: T2
    role: builder
    goal: docs de vendor/operacão atualizados para a suite real com a escalada
    scope: docs/ai/MODEL_ROUTING.md, docs/operations/HML.md,
           docs/operations/RUNBOOK_PROCESSING_FAILURES.md,
           docs/security/AI_VENDOR_RISK.md, docs/security/PRIVACY_LGPD.md,
           AGENTS.md (linha do Textract), docs/STATUS.md (linhas 89-93 e 762)
    out_of_scope: reescrever ADRs aceitos (0002/0004 são imutáveis), ROADMAP linhas
                  89/93 históricas (registro de época), código
    expected_areas: docs, AGENTS.md
    acceptance_criteria: ver tasks/T2-docs-vendor.md
    depends_on: [T1]
    validation: make check (check_docs)
    required_capabilities: READ, WRITE, VALIDATE
    risk: baixo; risco real é afirmar estado que o código não tem — cada frase
          nova precisa apontar código ou ADR
    relative_effort: S

parallel_groups: [[T1]]
critical_path: T1 → T2 (docs descrevem o que T1 entregou)
integration_strategy: T2 só começa com o diff de T1 na árvore; validação integrada
                      é make check + make test com os dois diffs
human_gates: aceite do ADR-0037; provisionamento GCP e env em HML (atos humanos,
             fora do código); eval comparativo pago antes de promover o braço
planning_findings: nenhum ARCHITECTURE_DECISION_REQUIRED além do ADR-0037 já
                   Proposed; PARALLELISM_RISK ausente
```
