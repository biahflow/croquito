# F-020 — Plano de execução

```text
FEATURE EXECUTION PLAN

feature_id: F-020
goal: a orçamentista abre um orçamento-base pela web, instala a cascata de
      catálogos na ordem que declarar, associa a prancha, revisa o takeoff,
      confirma códigos citando a fonte, declara o BDI e obtém a planilha .xlsx
      no layout da prefeitura com proveniência por linha — sem CLI
assumptions:
  - Design Approval Package revisão 1 aprovado em 2026-08-20 (mock/README.md);
    papel de acesso decidido: reusa o da medição (role `orcamentista`,
    REVIEWER_ROLE de round_view.py:25, checado por _require_valuation_reviewer
    em main.py:1224-1236)
  - ADR-0038 (Proposed) fixa a semântica do BDI; o aceite é gate humano listado
    ao final, mas as decisões 1-6 dele são a especificação usada pelas tasks
  - Estimate NÃO está no manifesto de contratos (verificado) — o bump de
    ESTIMATE_SCHEMA_VERSION 1.0.0 → 2.0.0 acontece ANTES da publicação, então
    nenhum consumidor externo do schema existe ainda
  - o golden tests/valuation/golden/estimate-demo.canonical.json muda de forma
    DELIBERADA nesta feature (campos de BDI no schema v2) — é parada declarada
    aqui no plano, não regeneração silenciosa
  - a garantia de "byte-idêntico" do boletim é, na prática do repositório,
    identidade de conteúdo lógico via canonicalize_workbook (a data interna do
    zip muda a cada gravação — workbook_writer.py:1267-1271); o critério de
    aceite 8 é satisfeito pelos goldens da medição inalterados
risks:
  - main.py tem 6294 linhas e a sessão paralela de traçado também o toca
    (faixa ~2245-4488); as rotas novas entram ao final (>6294), risco de
    conflito baixo mas real em imports/estado — integração final rebaseia na main
  - template.py e workbook_writer.py são compartilhados com o boletim da
    medição: coluna nova obrigatória quebraria o boletim — colunas ADITIVAS e
    OPCIONAIS, com os goldens da medição como prova
  - dinheiro: truncamento no centavo linha a linha (rounding.py) é lógica de
    domínio sensível — revisão linha a linha do diff de T1 e T2 pelo modelo
    principal

tasks:
  - id: T1
    role: builder
    goal: BDI entra no domínio Estimate (schema v2) e Estimate é publicado no
          manifesto de contratos; CLI build-estimate/estimate-demo declaram BDI
    scope: packages/valuation/src/croquito_valuation/estimate.py,
           packages/contracts/contracts.manifest.json (+ gerados via make contracts),
           services/worker/src/croquito_worker/valuation/cli.py (build-estimate,
           estimate-demo), services/worker/src/croquito_worker/valuation/estimate_fixture.py,
           tests/valuation/test_estimate.py, tests/valuation/golden/estimate-demo.canonical.json,
           tests/e2e/test_valuation_full_chain.py (fixture estimate_chain)
    out_of_scope: escritor/auditor de planilha (T2), API, web, medição
    expected_areas: packages/valuation, packages/contracts, services/worker, tests
    acceptance_criteria: ver tasks/T1-dominio-bdi-contrato.md
    depends_on: []
    validation: make check + make test + make valuation-estimate-demo
    required_capabilities: READ, WRITE, VALIDATE
    risk: aritmética de dinheiro e bump de schema — núcleo do domínio
    relative_effort: M
  - id: T2
    role: builder
    goal: caminho Estimate do escritor de planilha (adaptador, não
          generalização) com colunas FONTE e VALOR UNIT. C/ BDI aditivas, e
          auditor de recomputação próprio fail-closed
    scope: packages/valuation/src/croquito_valuation/template.py,
           packages/valuation/src/croquito_valuation/estimate_workbook.py (novo),
           packages/valuation/src/croquito_valuation/canonical.py (audit do estimate),
           services/worker/src/croquito_worker/valuation/cli.py (export do estimate-demo),
           tests/valuation/test_estimate_workbook.py (novo),
           tests/valuation/test_canonical_golden.py
    out_of_scope: mudar write_valuation_workbook/audit_workbook da medição além
                  do modelo de layout aditivo; API; web
    expected_areas: packages/valuation, services/worker, tests
    acceptance_criteria: ver tasks/T2-escritor-auditor-estimate.md
    depends_on: [T1]
    validation: make check + make test + make valuation-demo + make valuation-estimate-demo
    required_capabilities: READ, WRITE, VALIDATE
    risk: layout compartilhado com o boletim; goldens da medição são o detector
    relative_effort: M
  - id: T3
    role: builder
    goal: recurso /v1/estimate-rounds* completo espelhando /v1/valuation-rounds*
          (tabelas novas, camada de aplicação, rotas, extração, snapshot OpenAPI)
    scope: services/api/src/croquito_api/database.py,
           services/api/src/croquito_api/migrations/versions/0003_*.py (nova),
           services/api/src/croquito_api/estimate_rounds.py (novo, espelho de
           valuation_rounds.py), services/api/src/croquito_api/main.py (rotas ao
           final do arquivo), tests/api/test_estimate_round_routes.py (novo),
           tests/api/openapi.snapshot.json (ato deliberado)
    out_of_scope: web; CLI; mudar rotas ou tabelas da medição; providers.py
    expected_areas: services/api, tests/api
    acceptance_criteria: ver tasks/T3-persistencia-rotas-v1.md
    depends_on: [T1, T2]
    validation: make check + make test (inclui gate ADR-0029 quando
                CROQUITO_TEST_POSTGRES_URL existir; no mínimo os testes de rota)
    required_capabilities: READ, WRITE, VALIDATE
    risk: arquivo main.py grande e vivo, compartilhado com a sessão de traçado
    relative_effort: L
  - id: T4
    role: builder
    goal: terceira jornada "Orçamento" na SPA, espelhando a estrutura da
          medição, conforme o design aprovado (revisão 1)
    scope: apps/web/src/route.ts, apps/web/src/App.tsx,
           apps/web/src/orcamento/ (novo, espelho estrutural de src/medicao/),
           apps/web/src/orcamento/styles.css (tokens existentes, nada de cor nova),
           testes vitest correspondentes
    out_of_scope: src/medicao/ (a linha fixa da medição NÃO entra — o pacote
                  aprovado diz "o da medição continua o que já é"); CroquiApp;
                  capture/trace/chat do croqui
    expected_areas: apps/web
    acceptance_criteria: ver tasks/T4-jornada-web.md
    depends_on: [T1, T3]
    validation: make check + npm --workspace @croquito/web run test
    required_capabilities: READ, WRITE, VALIDATE
    risk: App.tsx/route.ts são compartilhados com o croqui; integração ampla
    relative_effort: L
  - id: T5
    role: builder
    goal: e2e novo da cadeia inteira do orçamento pelas rotas /v1, espelhando a
          fixture estimate_chain do e2e do CLI, sem passar pelo CLI
    scope: tests/e2e/test_estimate_rounds_v1.py (novo)
    out_of_scope: alterar o e2e do CLI além do que T1 já tocou; web
    expected_areas: tests/e2e
    acceptance_criteria: ver tasks/T5-e2e-v1.md
    depends_on: [T1, T2, T3]
    validation: make check + make test (o arquivo novo roda no make test)
    required_capabilities: READ, WRITE, VALIDATE
    risk: baixo — consome o que T3 publicou, in-process como o e2e existente
    relative_effort: M

  - id: T6
    role: builder
    goal: worker consome os comandos da rodada de orçamento (extração da prancha
          e re-render do overlay) que T3 passou a publicar na fila
    scope: services/worker/src/croquito_worker/local_queue.py,
           tests/worker/test_estimate_extraction_worker.py (novo, espelho de
           tests/worker/test_valuation_extraction_worker.py)
    out_of_scope: API; web; providers.py; handlers do croqui e da medição
    expected_areas: services/worker, tests/worker
    acceptance_criteria: ver tasks/T6-worker-consumo.md
    depends_on: [T3]
    validation: make check + make test
    required_capabilities: READ, WRITE, VALIDATE
    risk: arquivo grande vivo (local_queue.py, 1953 linhas) com caminho de
          provider pago; espelho de handler existente com oráculo de teste claro
    relative_effort: M

parallel_groups: [[T4, T6], [T4, T5]]
critical_path: T1 → T2 → T3 → T4 (domínio antes do escritor, escritor antes da
               rota de montagem, rota antes da tela; T3 e T4 são os L)
integration_strategy: tasks executam em sequência na branch f-020-orcamento-web
                      (worktree isolado da sessão de traçado); T4 e T5 podem
                      correr em paralelo (conjuntos de arquivos disjuntos).
                      Contratos entre tasks fixados NESTE plano: nomes de campo
                      do BDI (T1), assinatura do escritor/auditor (T2), paths e
                      payloads das rotas (T3). Integração final: rebase na main
                      + make check + make test + make valuation-demo +
                      make valuation-estimate-demo na árvore com todos os diffs.
human_gates: aprovação deste plano antes do build; aceite do ADR-0038; copy
             final e conferência contra o exemplar real (continuam abertas por
             declaração do pacote aprovado); merge na main e deploy
planning_findings: nenhum ARCHITECTURE_DECISION_REQUIRED além do ADR-0038 já
                   Proposed; PARALLELISM_RISK com a SESSÃO EXTERNA de traçado
                   registrado nos risks (main.py, docs) — mitigado por worktree
                   e rebase; entre as tasks deste plano, ausente

plan_deviations:
  - task: T6 (nova, pós-congelamento)
    planned: o plano congelado não tinha task para o LADO CONSUMIDOR dos
             comandos de fila da rodada de orçamento; T3 (escopo services/api)
             passou a publicar `extract_estimate_plate` e
             `rerender_estimate_takeoff_overlay`, e nenhum handler do worker os
             conhece
    actual: T6 criada espelhando os handlers da medição em local_queue.py
            (dispatch 508-527, handlers 1721/1888)
    impact: sem T6, POST /plate/extractions publicaria comando que apodrece na
            fila em ambiente implantado; T5 (e2e /v1) depende de T6 para a etapa
            de extração
    resolution: T5 passa a depender de [T1, T2, T3, T6]; T4 e T6 correm em
                paralelo (arquivos disjuntos)
```
