# F-025 — Evidência de execução

Status da feature: `READY_FOR_HUMAN_REVIEW` (2026-08-20). Pendem o merge da
branch `f-025-consultor-tracado` e a aceitação real na prancha do Guaxindiba —
atos humanos.

## Baseline

Branch criada a partir de `60e574d` (main), árvore limpa.
`uv run pytest tests/worker/test_tracing.py tests/worker/test_geometry_solver.py`
verde (91 testes); vitest 39 arquivos / 697 testes verdes; `make check` verde.

Falhas pré-existentes conhecidas (não atribuíveis a esta feature):

- `tests/api/test_migrations.py::test_medicao_nasce_depois_da_baseline_com_o_indice_da_listagem`
  quebrado desde a migração `0003` da F-020 (commit `9e5ba91`): o teste espera
  só as tabelas da medição e a `0003` criou as do orçamento. Só aparece com
  PostgreSQL real (CI); localmente é `skip`.

## Execução

| Task | Executor (harness) | Commit | Status |
|---|---|---|---|
| T1 — causas estruturadas, disputa nomeada, âncoras | `implementador-opus` (Claude Code, subagente) | `531f6f4` | `BUILD_COMPLETE` |
| T2 — consultor na tela, consertos, re-semeadura | `implementador-opus` (Claude Code, subagente) | `8cedb30` | `BUILD_COMPLETE` |

Os BUILD REPORTs completos estão preservados abaixo, por task, como
`PRIMARY_EXECUTION_EVIDENCE`. A revisão linha a linha dos dois diffs foi feita
pelo orquestrador da sessão (modelo principal), com re-execução dos portões.

## Revisão do orquestrador

- **T1**: diff inteiro lido; desvios 1–6 do report avaliados e ACEITOS (o
  downgrade `NotImplementedError` e o `server_default` de expand seguem
  ADR-0029 e a regra de expand/contract do `services/api/AGENTS.md`, que
  prevalecem sobre o texto do Task Contract; a 5-tupla de
  `_solve_group_geometry` resolve a incompatibilidade interna do contrato; a
  conversão explícita `Decimal→float` na fronteira evita `"5.00"` string no
  payload e está travada por teste e2e). `make check` completo verde após
  formatação do próprio Task Contract (única reprova, causada pelo documento
  do orquestrador, não pela entrega).
- **T2**: diff inteiro lido; desvios D1–D8 avaliados e ACEITOS (D8 — abrir a
  correção por efeito declarado após o de troca de leitura — replica o
  precedente do `chatPrefill` e é a solução correta). **Um achado de revisão
  corrigido pelo orquestrador** (incluído no commit `8cedb30`): o efeito de
  re-semeadura consumia a chave `${jobId}:${review.version}` no commit em que
  a restauração do rascunho ainda não publicou `batchIds`; no caminho
  "reload com rascunho anterior às decisões" (o cenário fundador da V17) a
  re-semeadura nunca rodaria para aquela versão. Conserto: seleção vazia não
  consome a chave. Portões re-executados verdes após o ajuste.

## Validação (estado FINAL)

- `make check` verde (ruff check/format, mypy strict 195 fontes, check_docs
  246 md, drift de contratos, build web, terraform fmt).
- `uv run pytest` (suíte inteira): 1703 passed, 10 skipped.
- vitest: 40 arquivos / 736 passed (697 do baseline + 39 novos).
- `make solver-eval`: `passed: true`, `audit_status: approved`.
- `make openapi-snapshot` executado deliberadamente (diff aditivo).
- `tests/api/test_migrations.py` executado contra PostgreSQL 17 real
  (contêiner descartável): gate de drift da `0004` verde; a única falha é a
  pré-existente da baseline (acima).

## Desvios de plano (`PLAN_DEVIATION`)

1. T1/`_solve_group_geometry`: 4-tupla planejada → 5-tupla entregue (a
   detecção de disputa é por grupo porque o id de faixa é local ao grupo).
   Impacto: nenhum fora do módulo. Resolução: aceito na revisão.
2. T1/migração: downgrade planejado como remoção de colunas → entregue
   forward-only (`NotImplementedError`), conforme ADR-0029/D2. Resolução:
   aceito; o contrato é que estava em desacordo com a regra do repo.
3. T1/escopo: `tests/api/test_migrations.py` ajustado fora da lista de escopo
   por quebra causada pela própria mudança (asserção de adoção estreitada para
   "nenhum `drop`/`alter` não aditivo"). Resolução: aceito na revisão.
4. T2/labels: assinatura de `traceUnappliedCauseLabel` recebe a entrada
   inteira em vez de `(cause, reading, proposals)` — molde literal do
   `traceBlockerLabel`. Resolução: aceito.
5. T2/consultor: `declare_axis` abre a correção da leitura (o controle de eixo
   real) em vez de "focar um controle independente" que não existe para
   leitura confirmada. Resolução: aceito.

## Riscos remanescentes e follow-ups

- Aplicar a migração `0004` no ambiente hospedado: ato de produção, exige
  aprovação humana.
- `test_medicao_nasce_depois_da_baseline_com_o_indice_da_listagem`: consertar
  na esteira da F-020 (pré-existente, fora do escopo desta feature).
- Interação real do painel (clique → estado) não tem teste automatizado: os
  testes web são SSR estático sem DOM; a lógica de decisão dos consertos está
  coberta em `traceAdvisor.test.ts` e a fiação segue o precedente testado do
  chat. Conferência real na prancha do Guaxindiba fica com o usuário.
- Oportunidades registradas e não implementadas: `rectify` para
  `TRACE_SPAN_VALUE_OR_DECISION_MISSING`; `keep_apart` com o eixo da disputa
  (`contested.axis`); teste de interação com jsdom (dependência nova).

## BUILD REPORT — T1 (verbatim)

```text
Status: BUILD_COMPLETE
Files changed: tracing.py; local_queue.py; database.py;
  migrations/versions/0004_trace_solve_diagnostics.py (nova); main.py;
  tests/api/openapi.snapshot.json (regen); tests/worker/test_tracing.py;
  tests/api/test_api.py; tests/e2e/test_full_flow.py;
  tests/api/test_migrations.py; docs/architecture/API_CONTRACT.md;
  docs/architecture/TRACE_STAGE.md
Validation executed: ruff check/format; mypy (195 fontes, sem issues);
  check_docs; schema_export --check; contracts:check; web build;
  infra-check; pytest suíte inteira (1703 passed, 10 skipped); vitest 697;
  make solver-eval (passed, audit approved); openapi contract (11 passed);
  test_migrations contra PostgreSQL 17 real (11 passed, 1 failed
  pré-existente da F-020)
Validation skipped: nenhuma
Unavailable capabilities: none
Assumptions: retorno de _span_from_reading como Literal fechado
  (TraceUnappliedCause) e cause:str+regex no modelo persistido;
  TRACE_SPAN_EDGE_NOT_FOUND/SAME_BAND separados de um `or` único sem mudança
  de comportamento; early returns review_required só preenchem os dois campos
  de não aplicadas; causas previstas conferidas nos cenários existentes
Remaining risks: TRACE_TARGET_AS_DRAWN checado antes do laço de segmentos
  muda um caso de borda (freeform com faixa por encosto que antes aplicava —
  hoje recusa com causa explícita); ContestedSpanOut sem min_length=2 na
  resposta (leitura tolerante de linha antiga); migração 0004 nunca rodou em
  homologação; apps/web ainda não conhece os campos (T2)
Human decisions required: formatar o Task Contract T1 (feito pelo
  orquestrador); destino do teste de migração quebrado pela F-020; aplicar a
  0004 em ambiente hospedado
```

## BUILD REPORT — T2 (verbatim)

```text
Status: BUILD_COMPLETE
Files changed: api.ts; labels.ts; traceAdvisor.ts (novo);
  traceAdvisor.test.ts (novo); trace.ts; trace.test.ts; traceStorage.ts;
  traceStorage.test.ts; labels.test.ts; CroquiApp.tsx; styles.css;
  docs/product/FDD.md
Validation executed: make check verde (ruff, mypy strict, check_docs,
  schema/contracts, tsc+vite, terraform fmt); vitest 40 arquivos / 736
  passed; make test extra (pytest 1703 passed, 10 skipped)
Validation skipped: none
Unavailable capabilities: none
Assumptions: "decidida de outro modo" = leitura não mais `confirmed` nesta
  revisão; rectify/declare_axis só com decision gravada; applied_spans pode
  ter mais de uma entrada por leitura (chave de render usa índice)
Desvios: D1 assinatura de traceUnappliedCauseLabel (entrada inteira, molde
  traceBlockerLabel); D2 rawCode do vão em disputa = "contested_spans"
  (nome da lista da resposta, nunca um cause inventado); D3 declare_axis
  abre a correção (o controle real do eixo); D4 advisorFixLabel/advisorFixKey
  puros adicionados; D5 keep_apart com axis:null (tipo do fix sem eixo);
  D6 guarda extra em TRACE_TARGET_AS_DRAWN (alvo precisa estar na seleção);
  D7 reuso de .blocker-list, só .advisor-fixes novo (styles.css, não
  index.css); D8 correção aberta por efeito declarado após o de troca de
  leitura (precedente chatPrefill)
Remaining risks: interação clique→estado sem teste automatizado (SSR sem
  DOM); re-semeadura no commit de chegada da revisão era no-op com chave
  consumida (R2 — CORRIGIDO pelo orquestrador na revisão: seleção vazia não
  consome a chave); nenhum job real com unapplied_readings observado ainda
Human decisions required: commit e merge (orquestrador/usuário); aceitação
  real na prancha do Guaxindiba
```
