# F-009 — Plano de execução

```text
FEATURE EXECUTION PLAN

feature_id: F-009
goal: upload real no HML gera pacote de revisão via providers OpenAI+Anthropic
      direto (sem AWS), com fallback transparente e OCR determinístico Cloud Vision
assumptions:
  - AnthropicProviderAdapter (API direta) existente cobre as tasks de imagem+texto
    (providers.py:960-1073, testado)
  - o resultado do OCR do Textract não tem consumidor (código morto verificado)
  - dataset_id só é checado por igualdade interna packet/associations/proposals
  - providers_json do consent não tem leitor (metadado de auditoria)
risks:
  - âncora do laço de leituras no modo braço único (provider_review.py:203-261)
  - ordem dos excepts BUDGET_EXCEEDED × fallback
  - aritmética de timeout (60s × 3 tentativas × 4-6 chamadas vs --timeout 900)
  - custo de reentrega: DLQ em 5 entregas ⇒ pior caso 5 × teto

tasks:
  - id: T1
    role: builder
    goal: suite hospedada com braços openai+anthropic, sem boto3, rótulos honestos
    scope: providers.py, provider_review.py (renames + remoção OCR morto),
           local_queue.py, main.py:2484, testes alterados
    out_of_scope: fallback novo (T2), braço ocr (T3), build_extraction_arm/valuation
    expected_areas: services/worker, services/api, tests
    acceptance_criteria: ver tasks/T1-suite-sem-aws.md
    depends_on: []
    validation: make check + make test
    required_capabilities: READ, WRITE, VALIDATE
    risk: integração ampla em arquivo grande vivo (providers.py ~1900 linhas)
    relative_effort: M
  - id: T2
    role: builder
    goal: fallback por tarefa com degradação transparente (Anthropic primário)
    scope: provider_review.py (helper + matriz), testes novos
    out_of_scope: braço ocr, mudanças de prompt/template
    expected_areas: services/worker, tests
    acceptance_criteria: ver tasks/T2-fallback.md
    depends_on: [T1]
    validation: make check + make test
    required_capabilities: READ, WRITE, VALIDATE
    risk: lógica de domínio sensível (âncora do laço, budget)
    relative_effort: M
  - id: T3
    role: builder
    goal: braço OCR Cloud Vision com corroboração real por leitura
    scope: adapter novo, campo ocr opcional na suite, corroboração no snapshot,
           fixture sintética, eval de recall
    out_of_scope: Document AI, F-010
    expected_areas: services/worker, tests, Makefile (target de eval)
    acceptance_criteria: ver tasks/T3-ocr-cloud-vision.md
    depends_on: [T1]
    validation: make check + make test + eval novo
    required_capabilities: READ, WRITE, VALIDATE
    risk: chamada GCP nova (ADC), normalização de bbox
    relative_effort: M
  - id: T4
    role: builder
    goal: ADR-0035, MODEL_ROUTING, runbook HML, ROADMAP F-010
    scope: docs/
    out_of_scope: código
    expected_areas: docs
    acceptance_criteria: ver tasks/T4-docs.md
    depends_on: [T1, T2, T3]
    validation: make check (check_docs valida links)
    required_capabilities: READ, WRITE, VALIDATE
    risk: baixo
    relative_effort: S
  - id: T5
    role: builder
    goal: deploy-hml.yml + Terraform biahflow/infra preparados (sem apply)
    scope: .github/workflows/deploy-hml.yml; repo irmão
           /Users/danielcampos/workspace/daniel/infra envs/hml/croquito
    out_of_scope: apply, valores de segredo, entitlement
    expected_areas: .github/workflows, repo irmão
    acceptance_criteria: ver tasks/T5-deploy-infra.md
    depends_on: []
    validation: make check; terraform fmt/validate no repo irmão
    required_capabilities: READ, WRITE, VALIDATE
    risk: guardrail de infraestrutura (nunca apply)
    relative_effort: S

parallel_groups: [T1, T5] e depois [T2, T3]
critical_path: T1 → T2 → T4 (T1 é a base de tudo; T2 carrega a lógica mais sensível)
integration_strategy: branch única feat/f-009-suite-hospedada-sem-aws; revisão linha
  a linha pelo modelo principal da sessão após cada entrega; portões completos antes
  do PR
human_gates: ADR-0035, terraform apply, segredos, entitlement, merge/deploy
planning_findings: PARALLELISM_RISK nenhum (arquivos disjuntos por grupo);
  ARCHITECTURE_DECISION_REQUIRED coberto pelo ADR-0035 (Proposed nesta entrega,
  aceitação humana)
```
