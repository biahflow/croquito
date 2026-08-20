# F-010 fatia 1 — Plano de execução

```text
FEATURE EXECUTION PLAN

feature_id: F-010
goal: confirmar em lote as leituras sugeridas como anotação, com uma
      justificativa do revisor replicada por decisão individual
assumptions:
  - API já aceita 1..50 decisões atômicas (main.py:364-366, 2700-2894);
    justificativa por item; uma Idempotency-Key e um base_version por lote
  - precedente de justificativa única replicada: lote de propostas
    (main.py:3671-3674); aqui a replicação é no cliente
  - padrão de teste do web: módulos puros em node + SSR estático; sem jsdom
risks:
  - linha da lista é <button> único — reestruturar sem quebrar seleção
    individual nem acessibilidade
  - pré-marcação não pode sobrescrever desmarcação do revisor no mesmo
    review.version (guarda por ref, molde openedTraceStepRef)

tasks:
  - id: T1
    role: builder
    goal: api.ts em lista + readingBatch.ts puro + painel/checkbox no CroquiApp
          + FDD
    scope: apps/web/src/api.ts, apps/web/src/readingBatch.ts (novo),
           apps/web/src/readingBatch.test.ts (novo), apps/web/src/CroquiApp.tsx,
           apps/web/src/index.css (se a linha reestruturada pedir),
           docs/product/FDD.md
    out_of_scope: services/**, labels.ts (só importar), chat/trace/retificação,
                  lote de rejeição/cotas
    expected_areas: apps/web, docs/product
    acceptance_criteria: ver tasks/T1-lote-anotacoes.md
    depends_on: []
    validation: make check + npm --workspace @croquito/web run test
    required_capabilities: READ, WRITE, VALIDATE
    risk: arquivo grande vivo; reestruturação de linha com acessibilidade
    relative_effort: M

parallel_groups: [[T1]]
critical_path: T1
integration_strategy: única task
human_gates: plano aprovado; aceitação real na revisão da V17
planning_findings: nenhum
```
