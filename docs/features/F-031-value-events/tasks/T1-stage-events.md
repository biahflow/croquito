# T1 — Histórico de transição de estágio + custo de IA no lineage do croqui

Task Contract derivado do [plano](../plan.md). Autossuficiente.

## Identity

```text
feature_id: F-031
task_id: T1
parent_plan: docs/features/F-031-value-events/plan.md
depends_on: []
```

## Goal

Tornar o cycle time por etapa reconstruível (hoje `jobs.stage/status` são
sobrescritos sem histórico) e parar de descartar tokens/custo das chamadas de
IA do pipeline do croqui (hoje `ProviderLineage` ignora `execution.usage`).

## Baseline

Branch `feat/f-031-value-events` no worktree
`/Users/danielcampos/workspace/daniel/croquito-f031`, base `main@5148f80`,
árvore limpa (fora `docs/` desta feature). Antes de editar, rode e registre:
`uv run pytest tests/api tests/worker -q` (esperado verde; falha preexistente
é baseline, não é sua).

## Mapa verificado (leia antes de editar)

- `services/api/src/croquito_api/database.py` — `JobRecord` l.61-82 (campos
  `status`, `stage`, `failure_code`, `created_at`, `updated_at`); molde de
  tabela append-only: `ReviewDecisionRecord` l.203-223.
- Migrações: `services/api/src/croquito_api/migrations/versions/` — lineares
  `0001…0006`. A sua é `0008_job_stage_events.py` com
  `down_revision = "0006"` (**deliberado**: a 0007 está reservada pela F-029
  em outra branch; documente isso no docstring da migração). Siga o estilo
  da 0006.
- Worker muda stage/status por SQL cru dentro de `engine.begin()`:
  `services/worker/src/croquito_worker/local_queue.py` l.644-655
  (`_mark_failed`) e mais dois `UPDATE jobs SET` ~l.906 e ~l.960 — confirme
  com `grep -n "UPDATE jobs SET" services/worker/src/croquito_worker/local_queue.py`
  e cubra TODOS os sítios.
- API cria o job: grep `JobRecord(` em `services/api/src/croquito_api/main.py`
  (vizinho do audit `JOB_CREATED`).
- Lineage: `services/worker/src/croquito_worker/review.py` l.100-113
  (`ProviderLineage`); populado em
  `services/worker/src/croquito_worker/provider_review.py` l.98-109
  (`_lineage`) a partir de `ProviderExecution`
  (`services/worker/src/croquito_worker/providers.py` l.654-668;
  `usage: ProviderUsage` com `input_tokens`, `output_tokens`,
  `estimated_cost_usd: Decimal`). Grep `ProviderLineage(` no repo e cubra
  todos os construtores (ex.: transcription).
- IDs: `croquito_core.ids.new_uuid7`.

## Scope (comportamento)

### 1. Tabela `job_stage_events`

`JobStageEventRecord` em `database.py`, append-only:
`{id (str36, uuid7), tenant_id (indexado), job_id (FK jobs, indexado),
from_stage: str | None, to_stage: str, from_status: str | None,
to_status: str, source: str ("api" | "worker"), failure_code: str | None,
created_at (tz-aware)}`. Migração `0008` aditiva (forward-only; rollback =
drop table, descreva no docstring).

- **API**: ao criar o job, insira o evento inicial
  (`from_stage/from_status = None`, `source="api"`) na mesma sessão/transação
  do `JobRecord`.
- **Worker**: em cada `UPDATE jobs SET status/stage`, insira a linha na MESMA
  `engine.begin()` (mesma transação), com `from_stage/from_status` lidos do
  job antes do update (um `SELECT` na mesma conexão; não invente o valor).
  `source="worker"`; `failure_code` quando houver.

### 2. Custo no lineage

`ProviderLineage` ganha campos opcionais `input_tokens: int | None`,
`output_tokens: int | None`, `estimated_cost_usd: Decimal | None` (serialize
Decimal como string no `model_dump(mode="json")`, padrão do repo). `_lineage`
os popula de `execution.usage` quando presente. Nenhum comportamento muda além
de dados a mais no `packet_json`; replay de pacotes antigos sem os campos não
pode quebrar (defaults `None`).

## Out of Scope

Outbox/eventos (T2); rotas de métricas (T3); `apps/web`; poda/retenção;
mudanças em `providers.py`; qualquer mudança de comportamento do pipeline.
Não conserte falha preexistente fora do escopo — pare e reporte.

## Acceptance Criteria

1. Fluxo do worker sobre um job de teste gera linhas em `job_stage_events`
   com `from_*` corretos e na mesma transação (teste: falha injetada após o
   UPDATE e antes do commit não deixa evento órfão — use SQLite do harness de
   testes existente).
2. Criação de job pela API gera o evento inicial com `source="api"`.
3. `_mark_failed` registra `failure_code` no evento.
4. Pacote de review gerado com provider fake carrega tokens/custo no lineage;
   pacote antigo (fixture sem os campos) continua carregando com `None`.
5. Migração 0008 aplica na baseline (`tests/api/test_migrations.py` verde).
6. `make check` e `make test` verdes; snapshot OpenAPI só é regenerado se o
   contrato de resposta realmente mudou (regen deliberado, revise o diff).

## Validation

```bash
uv run pytest tests/api tests/worker tests/e2e -q
make check
make test
```

## Report

Termine com o `BUILD REPORT` completo do contrato do Builder (status, files
changed, validation executed/skipped, unavailable capabilities, assumptions,
remaining risks, human decisions required — `none` explícito onde vazio).
