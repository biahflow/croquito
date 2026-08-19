# F-012 — Plano de execução

```text
FEATURE EXECUTION PLAN

feature_id: F-012
goal: operação de autorização de IA vira fluxo de produto — tela no lugar de curl,
      contrato no lugar de digest; zero redeploy por documento
assumptions:
  - extraction_eval.py lê a allowlist por função própria (152-157), nunca via
    LocalWorkerSettings — remover do worker não toca o caminho offline
  - consent nasce automático no POST /v1/jobs com entitlement ativo (main.py:2455-2491)
  - o backend já parseia roles do token (auth.py:21-24); a SPA não decodifica token
  - a query original inteira viaja no state do OIDC (route.ts:88-90) — ?plataforma
    sobrevive ao login sem mudança no entryRedirect
risks:
  - vizinhança do bloco removido no worker (consent 466-488 e suite 523-532 intocados)
  - UNION com ordenação determinística concordando entre SQLite e PostgreSQL
  - snapshot OpenAPI: diff só de adição
  - precedência de rotas job > rodada > plataforma

tasks:
  - id: T1
    role: builder
    goal: allowlist de digest fora do caminho hospedado; ADR-0036
    scope: local_queue.py, test_local_queue.py, deploy-hml.yml, docs/adr/0036
    out_of_scope: extraction_eval/valuation; consent; suite
    expected_areas: services/worker, tests, .github, docs/adr
    acceptance_criteria: ver tasks/T1-allowlist-fora.md
    depends_on: []
    validation: make check + make test
    required_capabilities: READ, WRITE, VALIDATE
    risk: baixo, mas vizinho de código sensível
    relative_effort: S
  - id: T2
    role: builder
    goal: /v1/me + GETs de plataforma com contrato atualizado
    scope: main.py, tests/api, openapi snapshot, API_CONTRACT.md
    out_of_scope: PUT existente; front
    expected_areas: services/api, tests/api, docs/architecture
    acceptance_criteria: ver tasks/T2-api-plataforma.md
    depends_on: []
    validation: make openapi-snapshot + make check + make test
    required_capabilities: READ, WRITE, VALIDATE
    risk: médio (superfície /v1 nova)
    relative_effort: S
  - id: T3
    role: builder
    goal: jornada Plataforma na SPA
    scope: route.ts, App.tsx, src/plataforma/ novo, testes vitest
    out_of_scope: CroquiApp/MedicaoApp; auth.ts
    expected_areas: apps/web
    acceptance_criteria: ver tasks/T3-jornada-plataforma.md
    depends_on: [T2]
    validation: make check + make test
    required_capabilities: READ, WRITE, VALIDATE
    risk: médio (integra route/App/módulo novo; UX de plataforma)
    relative_effort: M
  - id: T4
    role: builder
    goal: runbook sem passos manuais; ROADMAP com F-012 e inventário F-013..F-017
    scope: docs/
    out_of_scope: código
    expected_areas: docs
    acceptance_criteria: ver tasks/T4-docs.md
    depends_on: [T1, T2, T3]
    validation: make check (check_docs)
    required_capabilities: READ, WRITE, VALIDATE
    risk: baixo
    relative_effort: S

parallel_groups: [T1, T2] e depois [T3]
critical_path: T2 → T3 (a jornada depende da API)
integration_strategy: branch feat/f-012-operacao-saas-autorizacao-ia (base = ponta
  da F-009; PR aberto após o merge do #19 mostra só o delta); revisão linha a linha
  pelo modelo principal após cada entrega; portões completos antes do PR
human_gates: merge do PR #19 (pré-requisito), aceite do ADR-0036, merge desta
planning_findings: PARALLELISM_RISK nenhum (T1 worker/deploy, T2 api — disjuntos);
  ARCHITECTURE_DECISION_REQUIRED coberto pelo ADR-0036 (postura sem allowlist
  documental, ratificada pelo usuário em 2026-08-19)
```
