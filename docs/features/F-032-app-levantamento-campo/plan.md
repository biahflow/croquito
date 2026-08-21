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

---

# F-032 — Execution Plan (MVP local, fatias 1–3)

Segundo plano da feature, produzido após a satisfação dos dois gates: ADR-0043 aceito e
[Design Approval Package revisão 1](mock/README.md) aprovado, ambos por ato humano em
2026-08-21. Cobre o MVP **local** (pranchas 1–5 do pacote aprovado + fotos): coleta
completa sem rede. A sincronização real e as rotas `/v1/surveys` (prancha 6) ficam
para um terceiro plano, próprio, porque atravessam API, migração e contratos gerados.

```text
FEATURE EXECUTION PLAN

feature_id: F-032
goal: Transformar o scaffold em app coletável offline: motor de domínio e validação,
  telas de coleta e medida (pranchas 3–4), ordens e chegada (pranchas 1–2), conclusão
  com bloqueio por crítico (prancha 5) e fotos ancoradas — tudo local, sem transporte.
assumptions: portões verdes na branch (baseline pós db95ef3); DAP rev.1 é a
  autoridade visual — divergência material exige revisão 2 aprovada; ordens são
  fixture local sintética até existir backend (o botão "Baixar" da prancha 1 fica como
  superfície reservada).
risks: T3 é a maior tarefa (UI+persistência+undo) — degrau opus por integração ampla;
  validação de diagonal usa desigualdade triangular entre medidas declaradas (não
  posições do desenho), decisão registrada no contrato de T2.

tasks:
  - id: T2
    role: builder
    goal: Motor puro de comandos de coleta e validação de campo em src/domain
      (tasks/T2-motor-dominio-validacao.md)
    scope: apps/field/src/domain/**
    out_of_scope: UI, storage, outbox, services/**, docs/**
    acceptance_criteria: ver Task Contract T2
    depends_on: []
    validation: npm run field:test; npm run field:check; make check; make test
    required_capabilities: READ repo; WRITE apps/field/src/domain/**; VALIDATE
      perfis acima; COMMIT forbidden
    risk: inventar regra de validação fora do Feature Contract/DAP
    relative_effort: M
  - id: T3
    role: builder
    goal: Telas de coleta e medida (pranchas 3–4) sobre o motor de T2, persistindo
      cada comando via SurveyRepository+outbox (tasks/T3-telas-coleta-medida.md)
    scope: apps/field/src/ui/**, apps/field/src/styles.css, apps/field/src/outbox/**
      (integração), apps/field/src/main.tsx
    out_of_scope: rede, ordens, conclusão, fotos reais, services/**
    acceptance_criteria: ver Task Contract T3
    depends_on: [T2]
    validation: npm run field:test; npm run field:check; make check; make test
    required_capabilities: READ repo; WRITE escopo acima; VALIDATE perfis acima;
      COMMIT forbidden
    risk: canvas virar fonte de verdade; divergir do DAP sem revisão
    relative_effort: L
  - id: T4
    role: builder
    goal: Ordens de levantamento e chegada ao local (pranchas 1–2) com fixture local
      sintética; "Baixar" como superfície reservada desabilitada
    scope: apps/field/src/orders/** (novo), apps/field/src/ui/** (navegação)
    out_of_scope: rede/download real, backend
    acceptance_criteria: contrato derivado quando a onda 2 for autorizada
    depends_on: [T2]
    validation: mesmos perfis
    required_capabilities: idem T3
    risk: inventar modelo de ordem que conflite com o futuro contrato do backend
    relative_effort: M
  - id: T5
    role: builder
    goal: Conclusão com bloqueio por crítico e justificativa de pendência (prancha 5),
      checklist vindo do motor de T2
    scope: apps/field/src/ui/**
    out_of_scope: envio do pacote (sync)
    acceptance_criteria: contrato derivado quando a onda 2 for autorizada
    depends_on: [T3, T4]
    validation: mesmos perfis
    required_capabilities: idem T3
    risk: permitir concluir com crítico aberto
    relative_effort: M
  - id: T6
    role: builder
    goal: Fotos ancoradas — captura via input da câmera, SHA-256 (WebCrypto), blob no
      IndexedDB atrás do repositório, vínculo a ponto/elemento
    scope: apps/field/src/photos/** (novo), src/storage/**, src/ui/** (integração)
    out_of_scope: upload, desfoque, IA
    acceptance_criteria: contrato derivado quando a onda 2 for autorizada
    depends_on: [T3]
    validation: mesmos perfis
    required_capabilities: idem T3
    risk: blob grande sem aviso de quota
    relative_effort: M

parallel_groups: [T3, T4] após T2; [T5, T6] após suas dependências
critical_path: T2 → T3 → T5 (motor → tela principal → conclusão; T3 é o maior esforço)
integration_strategy: ondas na mesma branch — onda 1 = T2+T3 (contratos publicados
  neste commit), onda 2 = T4+T5+T6 (contratos derivados ao iniciar); revisão linha a
  linha e commit pelo modelo principal ao fim de cada tarefa; portões completos por
  onda.
human_gates: revisão 2 do DAP se qualquer prancha mudar materialmente; decisão de
  merge/push da branch; autorização da onda 2 após entrega da onda 1.
planning_findings: nenhuma decisão de arquitetura pendente (ADR-0043 cobre); sync e
  /v1/surveys deliberadamente fora — plano próprio (registrado como fatia futura no
  Feature Contract).
```

## Validação do plano (fatias 1–3)

`PLAN_VALID` — 2026-08-21. IDs únicos, dependências existentes, DAG acíclico
(T2→{T3∥T4}→T5; T3→T6), critérios/validação com comandos reais, paralelismo sem
sobreposição de arquivos (T3 = ui/outbox, T4 = orders/navegação — toque comum em
`src/ui` na navegação é sequenciado pela ordem de ondas), gates nomeados.
