# F-031 — Plano de execução (fatia 1)

```text
FEATURE EXECUTION PLAN

feature_id: F-031
goal: persistir os fatos de valor que faltam (transições de estágio, custo de
      IA no lineage do croqui, touch time), emitir eventos de domínio por
      outbox transacional com relay para broker (Pub/Sub via adapter), expor
      read-model de métricas por job/tenant e ligar logging estruturado JSON
      na API e no worker
assumptions:
  - branch feat/f-031-value-events em worktree isolado, base main@5148f80;
    NADA integra na main nesta rodada (decisão do usuário: incremento, não MVP)
  - a migração 0007 está reservada pela F-029 (outra sessão, mesmo checkout
    original); esta branch usa 0008/0009/0010 com down_revision="0006" —
    números e encadeamento serão reconferidos no rebase de integração
  - alembic linear 0001…0006 na base desta branch; migrações novas são
    aditivas (tabelas novas + coluna nullable)
  - worker escreve no banco via SQL cru (text()) e engine.begin()
    (local_queue.py:644-655); API escreve via ORM na mesma sessão do request
  - google-cloud-pubsub já é dependência (pubsub_queue.py) e o pyproject é
    único na raiz — o worker pode importá-la em adapter carregado sob demanda
  - _record_audit (main.py:1545-1565) marca os pontos de ato humano na API;
    a emissão de evento entra ao lado dele, na mesma transação
risks:
  - PARALLELISM_RISK (inter-branch): F-029 em execução na main tocará
    main.py, review.py e migração 0007; o rebase de integração desta branch
    renumera migrações e resolve conflitos em main.py — registrado como nota
    de integração, não resolvido aqui
  - main.py (~8.6k linhas) e CroquiApp.tsx são arquivos grandes vivos — tasks
    sequenciais, nunca duas em paralelo no mesmo arquivo
  - payload de evento/log nunca carrega conteúdo (regra CLAUDE.md); revisão
    linha a linha caça exatamente isso
  - volume: domain_events cresce com o uso; fatia 1 não faz retenção/poda
    (documentado no ADR-0042 como consequência aceita)

tasks:
  - id: T1
    role: builder
    goal: histórico de transição de estágio por job + tokens/custo no lineage
          do pipeline do croqui
    scope: services/api/src/croquito_api/database.py,
           services/api/src/croquito_api/main.py (criação de job),
           services/api/src/croquito_api/migrations/versions/ (0008),
           services/worker/src/croquito_worker/local_queue.py,
           services/worker/src/croquito_worker/review.py (ProviderLineage),
           services/worker/src/croquito_worker/provider_review.py,
           tests/api, tests/worker, tests/e2e/test_full_flow.py
    out_of_scope: outbox/eventos (T2), métricas (T3), apps/web, cli.py novo
    expected_areas: services/api, services/worker, tests
    acceptance_criteria: ver tasks/T1-stage-events.md
    depends_on: []
    validation: uv run pytest tests/api tests/worker tests/e2e -q + make check
    required_capabilities: READ, WRITE, VALIDATE
    risk: main.py vivo; migração nova
    relative_effort: S

  - id: T2
    role: builder
    goal: outbox transacional domain_events + porta DomainEventPublisher
          (adapters file e Pub/Sub) + relay CLI publish-events + emissão nos
          atos humanos da API e nas transições do worker
    scope: packages/core/src/croquito_core/events.py (novo),
           services/api/src/croquito_api/database.py,
           services/api/src/croquito_api/main.py (pontos de _record_audit),
           services/api/src/croquito_api/migrations/versions/ (0009),
           services/worker/src/croquito_worker/local_queue.py,
           services/worker/src/croquito_worker/domain_event_publisher.py (novo),
           services/worker/src/croquito_worker/cli.py,
           tests/api, tests/worker, tests/e2e
    out_of_scope: métricas (T3), web, provisionamento de tópico, retenção
    expected_areas: packages/core, services/api, services/worker, tests
    acceptance_criteria: ver tasks/T2-outbox-publisher.md
    depends_on: [T1]
    validation: uv run pytest tests/api tests/worker tests/e2e -q + make check
    required_capabilities: READ, WRITE, VALIDATE
    risk: muitos pontos de toque em main.py; transacionalidade
    relative_effort: L

  - id: T3
    role: builder
    goal: read-model de métricas por job e agregado por tenant + CLI
          value-report
    scope: services/api/src/croquito_api/main.py (rotas novas),
           services/worker/src/croquito_worker/cli.py,
           tests/api (inclui snapshot OpenAPI regen), tests/worker,
           docs/architecture/API_CONTRACT.md
    out_of_scope: dashboard, ROI, baseline AS-IS, campos da F-029 além de
                  placeholders null
    expected_areas: services/api, services/worker, tests, docs
    acceptance_criteria: ver tasks/T3-metrics-readmodel.md
    depends_on: [T1, T2]
    validation: uv run pytest tests/api tests/worker -q + make openapi-snapshot
                + make check
    required_capabilities: READ, WRITE, VALIDATE
    risk: agregação correta por tenant; main.py vivo
    relative_effort: M

  - id: T5
    role: builder
    goal: logging estruturado JSON de API e worker (stdlib)
    scope: packages/core/src/croquito_core/logging_config.py (novo),
           services/api/src/croquito_api/main.py (create_app + middleware),
           services/worker/src/croquito_worker/cli.py,
           services/worker/src/croquito_worker/local_queue.py (dispatch),
           tests/core (novo se preciso), tests/api, tests/worker
    out_of_scope: OpenTelemetry/traces/alarmes/dashboards; mudar mensagens de
                  domínio existentes
    expected_areas: packages/core, services/api, services/worker, tests
    acceptance_criteria: ver tasks/T5-structured-logging.md
    depends_on: [T3]
    validation: uv run pytest tests -q + make check
    required_capabilities: READ, WRITE, VALIDATE
    risk: não vazar conteúdo em log; não quebrar saída JSON de CLIs que
          imprimem em stdout
    relative_effort: S

  - id: T4
    role: builder
    goal: touch time real — interaction_ms medido na tela de revisão e
          persistido por revisão
    scope: services/api/src/croquito_api/main.py (payloads de decisões/
           retificações/aprovação), services/api/src/croquito_api/database.py,
           services/api/src/croquito_api/migrations/versions/ (0010),
           apps/web/src/api.ts, apps/web/src/CroquiApp.tsx e testes,
           tests/api (snapshot OpenAPI regen)
    out_of_scope: qualquer telemetria além de duração; UI nova; medição
    expected_areas: services/api, apps/web, tests
    acceptance_criteria: ver tasks/T4-touch-time-web.md
    depends_on: [T5]
    validation: uv run pytest tests/api -q + npm --workspace @croquito/web run
                test + make check
    required_capabilities: READ, WRITE, VALIDATE
    risk: CroquiApp.tsx vivo; campo deve ser estritamente observacional
    relative_effort: S

parallel_groups: []   # sequencial — main.py é ponto de toque de T1,T2,T3,T5,T4
critical_path: T1 → T2 → T3 (fatos → emissão → leitura); T5/T4 são cauda curta
integration_strategy: commits focados por task na branch feat/f-031-value-events;
                      SEM merge/push nesta rodada — integração é gate humano
                      (rebase pós-F-029, renumeração 0008/0009/0010, sync docs)
human_gates: aceite do ADR-0042; integração da branch; tópico Pub/Sub e
             migrações no hosted
planning_findings: PARALLELISM_RISK inter-branch com F-029 (main.py, review.py,
                   numeração de migração) — aceito e documentado; nenhuma
                   ARCHITECTURE_DECISION_REQUIRED além do ADR-0042 já proposto
```
