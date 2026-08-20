# F-025 — Plano de execução

```text
FEATURE EXECUTION PLAN

feature_id: F-025
goal: cada leitura não aplicada com causa estruturada e conserto de um clique
      no rascunho do aceite; vãos em disputa nomeados; âncoras por leitura
      aplicada; re-semeadura dos flags freeform não tocados à mão
assumptions:
  - a causa é calculável no ponto do descarte (_span_from_reading tem reading,
    targets, topology e bands; tracing.py:579-775)
  - o contrato é aditivo: unapplied_reading_ids e blockers preservados,
    campos novos ao lado (padrão da fatia 2 da F-010)
  - o mecanismo de "aplicar ao rascunho sem enviar" já existe
    (applyDraftToTraceDraft, chat.ts:304-396) e é o molde do conserto
  - traceBlockerLabel (labels.ts:434-493) é o molde de código→língua de obra
risks:
  - _span_from_reading tem ~8 pontos de retorno None; trocar o tipo de retorno
    exige revisitar todos os chamadores e manter mypy strict verde
  - contested_spans depende de band ids por grupo (planta × detail groups têm
    topologias separadas) — detecção é por grupo, agregação no resultado
  - CroquiApp.tsx é arquivo grande vivo; o painel novo não pode quebrar a
    seleção nem o polling existentes
  - re-semeadura toca ato humano: só flags fora de manualFlagIds

tasks:
  - id: T1
    role: builder
    goal: causas estruturadas por leitura não aplicada, vão em disputa nomeado
          e âncoras aplicadas no resultado, registro e resposta do trace-solve
    scope: services/worker/src/croquito_worker/tracing.py,
           services/worker/src/croquito_worker/local_queue.py,
           services/api/src/croquito_api/main.py,
           services/api/src/croquito_api/database.py,
           services/api/src/croquito_api/migrations/versions/ (nova, aditiva),
           tests/worker/test_tracing.py, tests/api/openapi.snapshot.json (regen),
           docs/architecture/API_CONTRACT.md, docs/architecture/TRACE_STAGE.md
    out_of_scope: geometry_solver.py (LSQ intocado), export/dxf, apps/web,
                  export_errors(), rectangle_solver, chat
    expected_areas: services/worker, services/api, tests, docs/architecture
    acceptance_criteria: ver tasks/T1-causas-estruturadas.md
    depends_on: []
    validation: make check + uv run pytest tests/worker/test_tracing.py
                tests/api -q + make test + make solver-eval
    required_capabilities: READ, WRITE, VALIDATE
    risk: arquivo grande vivo (tracing.py); tipo de retorno com ~8 saídas
    relative_effort: M

  - id: T2
    role: builder
    goal: painel do consultor com conserto de um clique, âncoras em língua de
          obra e re-semeadura dos flags não tocados
    scope: apps/web/src/api.ts, apps/web/src/labels.ts,
           apps/web/src/traceAdvisor.ts (novo),
           apps/web/src/traceAdvisor.test.ts (novo), apps/web/src/trace.ts,
           apps/web/src/trace.test.ts, apps/web/src/traceStorage.ts,
           apps/web/src/traceStorage.test.ts, apps/web/src/labels.test.ts,
           apps/web/src/CroquiApp.tsx, apps/web/src/index.css (se preciso),
           docs/product/FDD.md
    out_of_scope: services/**, chat.ts (só reusar moldes), etiqueta "pendente"
                  da lista de propostas (F-011), submissão automática de
                  qualquer conserto
    expected_areas: apps/web, docs/product
    acceptance_criteria: ver tasks/T2-consultor-web.md
    depends_on: [T1]
    validation: make check + npm --workspace @croquito/web run test
    required_capabilities: READ, WRITE, VALIDATE
    risk: arquivo grande vivo (CroquiApp.tsx); re-semeadura toca ato humano
    relative_effort: M

parallel_groups: [[T1]]
critical_path: T1 → T2 (T2 consome o contrato novo de T1)
integration_strategy: branch única f-025-consultor-tracado; commit por task
human_gates: classificação/prioridade/escopo decididos em 2026-08-20;
             merge e aceitação real na prancha do Guaxindiba são do usuário
planning_findings: nenhum
```
