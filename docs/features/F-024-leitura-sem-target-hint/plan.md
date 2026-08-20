# F-024 — Plano de execução

```text
FEATURE EXECUTION PLAN

feature_id: F-024
goal: leitura com valor e sem target_hint entra no pacote com nota, em vez de
      morrer como INCOMPLETE
assumptions:
  - ReviewPacket fora do manifesto de contratos gerados (verificado na F-021)
  - apps/web/src/api.ts já tem target_hint?: string — nenhuma mudança no web
  - o funil atual (provider_review.py:562) une valor e hint num só teste
risks:
  - decisão registrada com target_hint na rectificação (ReadingDecisionInput):
    conferir que None não quebra o caminho de correção da API

tasks:
  - id: T1
    role: builder
    goal: campo opcional + funil separado + nota nova + testes + docs
    scope: services/worker/src/croquito_worker/review.py,
           services/worker/src/croquito_worker/provider_review.py,
           tests/worker/test_providers.py, tests/api/openapi.snapshot.json (regen),
           docs/ai/PROMPT_CONTRACTS.md, docs/architecture/API_CONTRACT.md
    out_of_scope: transcription.py, apps/web, prompts
    expected_areas: services/worker, tests, docs
    acceptance_criteria: ver tasks/T1-funil-target-hint.md
    depends_on: []
    validation: make check + make test + make provider-contract-demo
    required_capabilities: READ, WRITE, VALIDATE
    risk: laço de leituras é lógica de domínio sensível
    relative_effort: S

parallel_groups: [[T1]]
critical_path: T1
integration_strategy: única task
human_gates: nenhum além do plano já aprovado
planning_findings: nenhum
```
