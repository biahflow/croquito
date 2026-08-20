# F-023 — Plano de execução (fatia 1)

```text
FEATURE EXECUTION PLAN

feature_id: F-023
goal: ligar o motor de fechamento de cadeias (dimension_closure.py, órfão) ao
      pipeline, à API e à tela: sugestões que fecham na resposta de review,
      declaração humana de cadeia persistida e re-conferida (mismatch vira
      WARNING visível, nunca blocker), CLI check-chains para calibração
assumptions:
  - a API já importa o worker no request path (main.py:169-176 importa
    ReviewPacket, solve_rectangle, tracing); importar dimension_closure segue
    o padrão, e o custo (~milhares de somas Decimal p/ ~12 cotas) é da mesma
    classe do solve_rectangle já servido on-line
  - _review_response (main.py:2145) é o ponto único de serialização de review;
    campos novos com default_factory=list cobrem replay idempotente de
    respostas gravadas antes do campo (precedente: required_criteria,
    main.py:528-537)
  - o canal de tipos do web para review é apps/web/src/api.ts escrito à mão
    (contracts gerados só carregam SceneRevision/valuation) — make contracts
    não é afetado
  - migrações lineares 0001→0005; a 0006 é aditiva (coluna JSON com
    server_default de lista vazia)
risks:
  - falso conforto da corroboração: 3 de 4 fechamentos do croqui real são
    coincidência — copy fraca ("Σ fecha"), cautela fixa, zero efeito de estado
  - main.py (8.346 l.) e CroquiApp.tsx são arquivos grandes vivos
  - migração 0006 se soma às 0004/0005 ainda não aplicadas no hosted —
    aplicar juntas no deploy (ato do usuário)
  - vocabulário: a seção chama-se "Somas de cotas", nunca "conferência do
    traçado" (o LSQ do tracing é mecanismo irmão e independente)

tasks:
  - id: T1
    role: builder
    goal: cadeias sugeridas e declaradas na resposta de review, rota de
          declaração/retração com persistência e supersessão, CLI check-chains
    scope: services/api/src/croquito_api/main.py,
           services/api/src/croquito_api/database.py,
           services/api/src/croquito_api/migrations/versions/ (0006, aditiva),
           services/worker/src/croquito_worker/cli.py,
           tests/api/test_api.py, tests/api/openapi.snapshot.json (regen),
           tests/worker/test_cli.py, tests/e2e/test_full_flow.py
    out_of_scope: dimension_closure.py e seus testes, apps/web,
                  export_errors()/blockers, tracing.py, croquito_core.models
    expected_areas: services/api, services/worker, tests
    acceptance_criteria: ver tasks/T1-backend.md
    depends_on: []
    validation: make check + uv run pytest tests/api tests/worker/test_cli.py
                tests/e2e -q + make test
    required_capabilities: READ, WRITE, VALIDATE
    risk: arquivo grande vivo (main.py); contrato de API + migração
    relative_effort: M

  - id: T2
    role: builder
    goal: seção "Somas de cotas" na revisão com declaração/retração, avisos de
          mismatch/stale e badge de corroboração
    scope: apps/web/src/api.ts, apps/web/src/labels.ts,
           apps/web/src/labels.test.ts, apps/web/src/CroquiApp.tsx,
           apps/web/src/CroquiApp.test.tsx, apps/web/src/styles.css (se preciso)
    out_of_scope: services/**, trace/traceAdvisor (só vizinhança visual),
                  submissão automática de qualquer declaração
    expected_areas: apps/web
    acceptance_criteria: ver tasks/T2-web.md
    depends_on: [T1]
    validation: make check + npm --workspace @croquito/web run test
    required_capabilities: READ, WRITE, VALIDATE
    risk: arquivo grande vivo (CroquiApp.tsx); não quebrar seleção/polling
    relative_effort: M

parallel_groups: [[T1]]
critical_path: T1 → T2 (T2 consome o contrato novo de T1)
integration_strategy: main direto (portão de quality desligado na rodada,
                      registrado); commit por task
human_gates: escopo e declaração de cadeia decididos em 2026-08-20 (aprovação
             do plano); migração no hosted e push/deploy são do usuário
planning_findings: nenhum
```
