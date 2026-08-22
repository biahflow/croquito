# T4 — Touch time real: `interaction_ms` da tela de revisão

Task Contract derivado do [plano](../plan.md). Autossuficiente.

## Identity

```text
feature_id: F-031
task_id: T4
parent_plan: docs/features/F-031-value-events/plan.md
depends_on: [T5]
```

## Goal

A tela de revisão passa a cronometrar o tempo de interação humana e enviá-lo
como campo **opcional e observacional** nas mutações; o servidor persiste por
revisão e o expõe nas métricas (T3) e no evento (T2). Ausência ou valor
absurdo NUNCA invalida a mutação.

## Baseline

T1–T3+T5 na branch. Rode e registre: `uv run pytest tests/api -q` e
`npm --workspace @croquito/web run test`.

## Mapa verificado (leia antes de editar)

- API: rotas de mutação de review em
  `services/api/src/croquito_api/main.py` — decisões
  (`submit_review_decisions`, ~l.3147), retificações (~l.3344), aprovação
  (`/approve`). Payloads Pydantic correspondentes (ex.:
  `ReviewDecisionCommand` ~l.373 e o modelo do batch).
- Persistência: `ReviewRevisionRecord`
  (`services/api/src/croquito_api/database.py` l.153-190) — coluna nova
  `interaction_ms: int | None`. Migração `0010_review_interaction_ms.py`,
  `down_revision = "0009"`, aditiva (coluna nullable).
- Evento (T2): `review.decisions_recorded.v1` / `rectifications_recorded.v1`
  ganham `interaction_ms` quando presente (contrato já prevê o campo
  opcional).
- Métricas (T3): `human.interaction_ms_total` deixa de ser sempre `null` —
  soma dos `interaction_ms` das revisões do job.
- Web: `apps/web/src/api.ts` — `submitReviewDecisions` l.660-678,
  `submitReviewRectification` l.680-697; a tela de revisão vive em
  `apps/web/src/CroquiApp.tsx` (arquivo grande vivo — mudança mínima).
- Snapshot OpenAPI: `make openapi-snapshot` deliberado;
  `docs/architecture/API_CONTRACT.md` atualizado.

## Scope (comportamento)

### 1. API

- Campo opcional `interaction_ms: int | None = None` no payload do batch de
  decisões, das retificações e da aprovação. Validação leve: negativo ou
  > 24h → **descartar para `None`** (nunca 422 — é telemetria, não dado de
  negócio). Persistir na `ReviewRevisionRecord` criada pela mutação (a
  aprovação, que não cria revisão de review, persiste no registro que já
  cria — se não houver coluna natural, deixe a aprovação de fora e registre
  a decisão no report).
- Propagar ao evento correspondente e ao cálculo de T3.

### 2. Web

- Cronômetro por sessão de revisão: inicia quando o pacote carrega/recarrega
  e envia o acumulado no submit de decisões/retificações; zera após submit.
  `document.visibilityState === "hidden"` pausa o relógio (não conte tempo
  de aba em background). Implementação mínima (hook/util pequeno + testes);
  nenhuma UI nova.

### 3. Replay/compatibilidade

Respostas idempotentes gravadas antes do campo fazem replay sem quebrar;
cliente antigo (sem o campo) continua funcionando.

## Out of Scope

Qualquer telemetria além de duração (cliques, teclas, heatmap); telas da
medição; mudanças visuais; `packages/contracts`. Não conserte falha
preexistente fora do escopo — pare e reporte.

## Acceptance Criteria

1. Batch com `interaction_ms: 4200` → coluna preenchida, evento carrega o
   campo, `GET /v1/jobs/{id}/metrics` soma em `interaction_ms_total`.
2. Batch sem o campo → tudo funciona como hoje (`None`); `interaction_ms: -5`
   ou absurdo → persistido `None`, mutação aceita.
3. Web: teste (vitest) de que o submit envia o campo e de que a pausa por
   visibilidade não conta; nenhum teste existente quebrou.
4. Migração 0010 verde em `tests/api/test_migrations.py`; snapshot OpenAPI
   regenerado deliberadamente; `API_CONTRACT.md` atualizado.
5. `make check`, `make test` e a suíte do web verdes.

## Validation

```bash
uv run pytest tests/api -q
npm --workspace @croquito/web run test
make openapi-snapshot   # deliberado, revisar diff
make check
make test
```

## Report

Termine com o `BUILD REPORT` completo (todos os campos; `none` explícito
onde vazio).
