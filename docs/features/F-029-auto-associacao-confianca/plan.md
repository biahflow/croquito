# F-029 — Plano de execução

Produzido em 2026-08-21 a partir do [Feature Contract](feature.md), com inspeção
verificada do código (linhas citadas nos Task Contracts). Aguarda aprovação
humana para congelar (`READY_FOR_BUILD`).

```text
FEATURE EXECUTION PLAN

feature_id: F-029
goal: score determinístico de confiança por cota (leitura × associação),
  shadow log persistido, métricas e eval de associação, e modo automático
  local atrás de flag com decisão de ator-máquina — sem nenhuma mudança de
  comportamento com a flag desligada.
assumptions:
  - Nenhum provider devolve confiança numérica hoje (verificado: nenhum campo
    `confidence` em providers.py/provider_review.py). `reading_confidence` é
    composto de sinais já existentes: `ocr_corroborated` (review.py:136),
    participação em cadeia que fecha (dimension_closure.py) e coerência
    valor/unidade. Mudar contrato de provider está fora de escopo.
  - Não existe rotação de texto no pacote de revisão (EvidenceRegion só tem
    bbox — review.py:54-59). O sinal de orientação é o alinhamento entre o
    eixo dominante do bbox da evidência e a direção do segmento candidato
    (derivada de PixelLine.start/end, vision.py:70-74).
  - A decisão humana vive no worker (review.py:72-97), não em
    croquito_core.models: a extensão de ator-máquina muda OpenAPI
    (make openapi-snapshot), não o scene schema. Se a listagem de
    auto-decisões na auditoria exigir campo novo em Provenance (core), aí
    `make contracts` entra — risco registrado em T4.
risks:
  - Threshold sem base: o gate sintético não substitui calibração real; por
    isso o threshold NÃO tem default no código e a flag exige valor explícito.
  - CroquiApp.tsx tem 5784 linhas: T5 é integração em arquivo grande vivo.
  - Dados reais em output/ têm retenção de 7 dias; o relatório de calibração
    precisa rodar enquanto as revisões humanas existirem no banco local.

tasks:
  - id: T1
    role: builder
    goal: sinais tipados novos e duas confianças determinísticas no worker
    scope: association.py (campos aditivos no candidato), módulo novo de
      score (reading_confidence + association_confidence 0-1), consumo de
      dimension_closure como sinal, função pura de shadow (o que seria
      auto-decidido em cada threshold)
    out_of_scope: persistência, API, flag, tela, eval
    expected_areas: services/worker/src/croquito_worker/association.py,
      services/worker/src/croquito_worker/association_confidence.py (novo),
      tests/worker/test_association.py,
      tests/worker/test_association_confidence.py (novo)
    acceptance_criteria: ver tasks/T1-sinais-score.md
    depends_on: []
    validation: make check; uv run pytest tests/worker/test_association.py
      tests/worker/test_association_confidence.py
    required_capabilities: READ, WRITE, VALIDATE
    risk: baixo — mudança aditiva observacional; determinismo é o critério
    relative_effort: M
  - id: T2
    role: builder
    goal: shadow log persistido por revisão e exposto na resposta de review
    scope: migração aditiva 0007 (coluna JSON em review_revisions),
      cômputo do shadow na gravação da revisão, campos observacionais na
      ReviewResponse (confidences por leitura/candidato + shadow + métricas
      auto_association_rate/review_rate), snapshot OpenAPI
    out_of_scope: qualquer decisão automática; mudança de comportamento de
      rotas existentes; tela
    expected_areas: services/api/src/croquito_api/migrations/versions/0007_*.py,
      services/api/src/croquito_api/database.py,
      services/api/src/croquito_api/main.py, tests/api/test_api.py,
      tests/api/test_migrations.py
    acceptance_criteria: ver tasks/T2-shadow-api.md
    depends_on: [T1]
    validation: make check; uv run pytest tests/api
    required_capabilities: READ, WRITE, VALIDATE
    risk: médio — replay idempotente de respostas gravadas antes dos campos
      novos (precedente F-023: default_factory, main.py:567-575)
    relative_effort: S
  - id: T3
    role: builder
    goal: eval determinística de associação com gate + relatório de calibração
    scope: CLI association-eval (fixture sintética programática, gate zero
      auto-associação errada) e calibration-report (replay das revisões
      locais: shadow × decisões humanas, tabela threshold × taxa × erro),
      make targets
    out_of_scope: chamadas pagas; CI com dados reais; escolha do threshold
    expected_areas: services/worker/src/croquito_worker/association_eval.py
      (novo), services/worker/src/croquito_worker/cli.py, Makefile,
      tests/worker/test_association_eval.py (novo)
    acceptance_criteria: ver tasks/T3-eval-calibracao.md
    depends_on: [T1, T2]
    validation: make check; make association-eval;
      uv run pytest tests/worker/test_association_eval.py
    required_capabilities: READ, WRITE, VALIDATE
    risk: baixo — molde existente (vision_eval.py)
    relative_effort: M
  - id: T4
    role: builder
    goal: modo automático local atrás de flag com ator-máquina e auditoria
    scope: CROQUITO_AUTO_ASSOCIATION_ENABLED (padrão false, padrão de leitura
      estrita de providers.py:2792-2810) + CROQUITO_AUTO_ASSOCIATION_THRESHOLD
      obrigatório sem default; extensão do modelo de decisão conforme
      ADR-0041 aceito; aplicação de auto-decisões acima do threshold na
      gravação da revisão; associação explícita para o solver; auto-decisões
      listadas nominalmente na auditoria do export; retificação existente
      cobre auto-decisão
    out_of_scope: tela; qualquer ambiente hospedado; mudar o portão
      export_errors()
    expected_areas: services/worker/src/croquito_worker/review.py,
      services/worker/src/croquito_worker/dxf.py,
      services/api/src/croquito_api/local_queue.py,
      services/api/src/croquito_api/main.py, tests/worker, tests/api,
      tests/e2e/test_full_flow.py
    acceptance_criteria: ver tasks/T4-modo-automatico.md
    depends_on: [T1, T2]
    validation: make check; make test; make smoke-local (flag desligada);
      rodada local com flag ligada conforme Task Contract
    required_capabilities: READ, WRITE, VALIDATE
    risk: alto — toca o invariante fail-closed; gate ADR-0041 antes de
      iniciar; flag desligada deve ser bit a bit idêntica a hoje
    relative_effort: L
  - id: T5
    role: builder
    goal: revisão web só de exceções — contadores, badge e filtro
    scope: contadores auto-associadas/revisão necessária/não resolvidas,
      badge de linha auto-decidida (cor nunca único indicador), filtro de
      exceções, tipos em api.ts e labels.ts, testes vitest
    out_of_scope: redesenho da tela; edição de forma (F-018); preview (F-019)
    expected_areas: apps/web/src/CroquiApp.tsx, apps/web/src/api.ts,
      apps/web/src/labels.ts, apps/web/src (testes)
    acceptance_criteria: ver tasks/T5-web-excecoes.md
    depends_on: [T4]
    validation: make check; npm --workspace @croquito/web run test
    required_capabilities: READ, WRITE, VALIDATE
    risk: médio — integração em CroquiApp.tsx (arquivo grande vivo)
    relative_effort: M

parallel_groups: [[T3, T4]] — após T2; áreas disjuntas (T3: eval/cli/Makefile;
  T4: review/local_queue/dxf). Nenhum PARALLELISM_RISK não resolvido; os dois
  adicionam testes em tests/worker em arquivos distintos.
critical_path: T1 → T2 → T4 → T5 — T4 é o maior esforço (L) e carrega o gate
  ADR-0041; T5 só nasce depois do mock aprovado.
integration_strategy: integração contínua na branch de trabalho, revisão
  linha a linha do modelo da sessão por task, portões completos a cada task;
  T4 só integra com ADR-0041 aceito; nada é ligado por padrão em momento
  algum.
human_gates:
  - aprovação deste plano (congela para READY_FOR_BUILD);
  - aceite do ADR-0041 antes de T4 (o texto do ADR é produzido pela sessão
    principal, fora dos Task Contracts — decisão de arquitetura não é task
    de builder);
  - aprovação do mock simples da vista de exceções antes de T5;
  - escolha do threshold operacional a partir do relatório de T3 (não
    bloqueia o código de T4; bloqueia o uso real da flag);
  - ligar a flag fora do ambiente local permanece proibido neste contrato.
planning_findings:
  - ARCHITECTURE_DECISION_REQUIRED: ADR-0041 (decisão de ator-máquina no
    modelo de decisão) — direção aprovada no spec; forma final é do ADR.
  - Confiança numérica de provider inexistente e rotação de texto inexistente
    no pacote: registradas como assumptions acima, com os sinais substitutos.
  - solver feedback (resíduos) existe no resultado do solve
    (tracing.py:349-371) e não realimenta associação hoje; entra como sinal
    OPCIONAL quando a revisão tem diagnóstico de solve, nunca como requisito
    do score.
```
