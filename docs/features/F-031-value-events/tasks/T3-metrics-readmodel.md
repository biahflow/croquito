# T3 — Read-model de métricas: `/v1/metrics/*` e CLI `value-report`

Task Contract derivado do [plano](../plan.md). Autossuficiente.

## Identity

```text
feature_id: F-031
task_id: T3
parent_plan: docs/features/F-031-value-events/plan.md
depends_on: [T1, T2]
```

## Goal

Expor o "TO-BE medido" calculado só de dados persistidos: cycle time por
etapa, atos humanos, correction rate e custo de IA por job — por job e
agregado por período/tenant. Nada é armazenado novo: é leitura derivada.

## Baseline

T1+T2 na branch. Rode e registre: `uv run pytest tests/api -q`.

## Mapa verificado (leia antes de editar)

- Fontes: `job_stage_events` (T1), `review_revisions`/`review_decisions`
  (`database.py` l.153-223; `action ∈ confirm|correct|reject` verbatim,
  `rectifies_decision_id`), `proposal_decisions` l.229-244, `approvals`
  l.248-263, `export_artifacts` l.268-292, `chat_turns` l.386-417 (colunas
  `input_tokens/output_tokens/estimated_cost_usd`), lineage do croqui no
  `packet_json` (T1), `valuation/estimate_round_revisions` +
  `extraction_lineage_json`.
- Rotas: closures em `create_app()` de
  `services/api/src/croquito_api/main.py`; `tenant_id` SEMPRE do JWT
  (`principal`), nunca de query/body — siga qualquer rota GET vizinha
  (ex.: a de review) como molde de auth + 404 problem+json.
- Snapshot OpenAPI: `make openapi-snapshot` deliberado;
  `tests/api/test_openapi_contract.py` é o gate.
- CLI: `services/worker/src/croquito_worker/cli.py` (padrão dos subcomandos;
  o worker acessa o banco por engine, como `local_queue.py`).
- Docs: `docs/architecture/API_CONTRACT.md` (adicionar as rotas novas,
  seguindo o formato do arquivo).

## Scope (comportamento)

### 1. `GET /v1/jobs/{job_id}/metrics`

(rota aninhada no job, coerente com as vizinhas). Resposta:

```json
{
  "job_id": "...",
  "cycle": {
    "total_ms": 0,
    "stages": [{"stage": "...", "status": "...", "duration_ms": 0}]
  },
  "human": {
    "review_revisions": 0,
    "decisions_total": 0,
    "confirmed": 0,
    "corrected": 0,
    "rejected": 0,
    "correction_rate": 0.0,
    "rectifications": 0,
    "interaction_ms_total": null
  },
  "automation": {"auto_association_rate": null, "review_rate": null},
  "ai_cost": {
    "calls": 0,
    "input_tokens": 0,
    "output_tokens": 0,
    "estimated_cost_usd": "0"
  }
}
```

- `cycle`: derive de `job_stage_events` (deltas consecutivos; etapa aberta =
  sem `duration_ms`). `total_ms` = criação do job → último evento.
- `human`: da revisão de review corrente e das linhas de `review_decisions`
  (`corrected` = `action == "correct"`); `correction_rate` =
  corrected/decisions_total (null se 0 decisões — nunca divida por zero).
  `interaction_ms_total` fica `null` até a T4 existir.
- `automation`: **placeholders `null`** — os valores reais são da F-029;
  não implemente nada dela.
- `ai_cost`: soma de `chat_turns` do job + lineage do `packet_json` (campos
  da T1) — some o que existir, `Decimal` serializado string.
- Tenant do JWT; job de outro tenant → 404 padrão (não 403 — siga as
  vizinhas).

### 2. `GET /v1/metrics/summary?from=...&to=...`

Agregado do tenant no período (`created_at` do job): `jobs_total`,
`jobs_completed`, `jobs_failed`, médias de `cycle.total_ms` e
`correction_rate` (sobre jobs com decisões), soma de `ai_cost`. Rounds de
medição/orçamento: `valuation_rounds_total`/`estimate_rounds_total` e soma de
custo dos `extraction_lineage_json`. Datas malformadas → 422 problem+json
código estável.

### 3. CLI `croquito-demo value-report --job <id> [--output f.json]`

Mesmo cálculo por job direto do banco (`CROQUITO_DATABASE_URL`), stdout JSON
idêntico ao da rota (menos auth). Exit 0; job inexistente → exit 1 com
mensagem em stderr.

Extraia o cálculo para função(ões) puras compartilháveis (módulo novo em
`services/api/src/croquito_api/` importável pelo CLI, ou duplicação mínima
justificada no report — prefira a função pura testável).

## Out of Scope

Dashboard/ROI/baseline; persistir agregados; métricas da F-029 além dos
placeholders; eventos novos; `apps/web`. Não conserte falha preexistente
fora do escopo — pare e reporte.

## Acceptance Criteria

1. Job de teste com fluxo completo → `cycle.stages` coerente com
   `job_stage_events`; job recém-criado → etapa aberta sem duração.
2. Lote com 2 confirm + 1 correct + 1 reject → contagens exatas e
   `correction_rate = 0.25`; job sem decisões → `correction_rate: null`.
3. Job com `chat_turns` → `ai_cost` soma tokens/custo; sem custo → zeros.
4. Job de outro tenant → 404; `summary` nunca vaza dados de outro tenant
   (teste com dois tenants).
5. `value-report` reproduz o JSON da rota para o mesmo job.
6. Snapshot OpenAPI regenerado deliberadamente (diff só com as rotas novas);
   `API_CONTRACT.md` atualizado; `make check` e `make test` verdes.

## Validation

```bash
uv run pytest tests/api tests/worker -q
make openapi-snapshot   # deliberado, revisar diff
make check
make test
```

## Report

Termine com o `BUILD REPORT` completo (todos os campos; `none` explícito
onde vazio).
