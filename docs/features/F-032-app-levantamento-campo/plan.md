# F-032 — Execution Plan (fatia 0)

Plano da fatia 0 apenas: o scaffold técnico autorizado pelo plano aprovado pelo usuário
em 2026-08-21. As fatias com superfície de usuário (2+ do Feature Contract) serão
planejadas depois dos gates humanos (aceite do ADR-0043 e Design Approval Package) e não
fazem parte deste plano.

```text
FEATURE EXECUTION PLAN

feature_id: F-032
goal: Fundar o workspace apps/field como PWA offline-first coberta pelos portões do
  monorepo, com modelo de domínio serializável, persistência local atrás de interface e
  esqueleto de outbox — sem telas finais e sem tocar a API.
assumptions: portões (make check / make test) verdes na baseline da branch
  f-032-app-levantamento-campo (worktree ../croquito-f032, base main@5148f80); nenhum
  outro trabalho concorrente toca package.json raiz ou Makefile nesta branch.
risks: PLAN_DEVIATION de numeração já ocorrido antes do congelamento (feature nasceu
  como F-031/ADR-0042 no plano aprovado; renumerada para F-032/ADR-0043 ao constatar
  que outra sessão publicou F-031 e ADR-0042 na branch feat/f-031-value-events);
  demais riscos no Task Contract.

tasks:
  - id: T1
    role: builder
    goal: Scaffold do apps/field conforme tasks/T1-scaffold-apps-field.md
    scope: apps/field/** (novo), package.json raiz, Makefile
    out_of_scope: services/**, packages/**, apps/web/**, docs/** (além dos já escritos),
      .github/**, infra/**
    expected_areas: apps/field, package.json, Makefile
    acceptance_criteria: ver Task Contract T1 (critérios 1–5 do Feature Contract,
      fatia 0)
    depends_on: []
    validation: make check; make test (perfis lint/typecheck/build/unit do monorepo,
      agora cobrindo field:check e field:test)
    required_capabilities: READ repo; WRITE apps/field/**, package.json, Makefile;
      VALIDATE make check, make test; COMMIT forbidden
    risk: quebrar make check dos workspaces existentes ao mexer em package.json/Makefile
    relative_effort: M

parallel_groups: nenhum (tarefa única)
critical_path: T1 (única tarefa)
integration_strategy: tarefa única na branch f-032-app-levantamento-campo; commit pelo
  modelo principal da sessão após revisão linha a linha; merge na main é gate humano
  (dispara a esteira deploy-hml).
human_gates: aceite do ADR-0043; Design Approval Package antes do planejamento das
  fatias 2+; decisão humana de merge da branch.
planning_findings: DESIGN_APPROVAL_REQUIRED registrado para as fatias de superfície
  (não planejadas aqui); a fatia 0 não entrega superfície aprovada — o shell de UI é
  declaradamente descartável.
```

## Validação do plano

`PLAN_VALID` — 2026-08-21. Tarefa única com ID único, sem dependências, sem
paralelismo, critérios e validação nomeados no Task Contract com comandos reais do
projeto; escopo bounded em arquivos; gates humanos nomeados; nenhum requisito da
fatia 0 sem dono.

## PLAN_DEVIATION

- 2026-08-21 (antes do congelamento, registrado por transparência): renumeração
  F-031→F-032 e ADR-0042→ADR-0043 por colisão de ID com a branch
  `feat/f-031-value-events`, detectada ao criar a worktree. Escopo inalterado.
