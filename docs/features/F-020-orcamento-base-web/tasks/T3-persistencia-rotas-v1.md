# T3 — Recurso `/v1/estimate-rounds*`: persistência, camada de aplicação e rotas

Task Contract no formato do template global (`docs/engineering-os/templates/task.md`),
derivado do [plano válido](../plan.md). Autossuficiente: assuma o Core, este
contrato, o [ADR-0038](../../../adr/0038-bdi-como-conceito-de-pre-licitacao.md) e o
repositório. O espelho de referência é o recurso `/v1/valuation-rounds*` inteiro —
leia-o antes de escrever qualquer rota.

## Identity

```text
feature_id: F-020
task_id: T3
parent_plan: docs/features/F-020-orcamento-base-web/plan.md
depends_on: [T1, T2]
```

## Goal

A cadeia do orçamento-base (abrir → cascata de catálogos → prancha → extração →
takeoff → códigos com fonte → montar com BDI → ler/planilha) roda inteira por
rotas `/v1` autenticadas, com a mesma disciplina da medição: papel exigido
inclusive na leitura, `Idempotency-Key`, `base_version`/409, `problem+json`.

## Baseline

T1 e T2 integrados na branch; `make check` e `make test` verdes. O gate do
ADR-0029 (`tests/api/test_migrations.py:141-155`,
`test_baseline_nao_diverge_dos_modelos`) roda só com `CROQUITO_TEST_POSTGRES_URL`;
sem Postgres local, declare-o em `Validation skipped` no BUILD REPORT.

## Scope

### Persistência — `services/api/src/croquito_api/database.py`

Tabelas novas espelhando as da medição (`ValuationRoundRecord`, linha 434-503;
`ValuationRoundRevisionRecord`, 506-537):

- `EstimateRoundRecord` (`estimate_rounds`): mesmos campos de identidade,
  concorrência (`version`), prancha, extração e carimbos — MAS no lugar dos
  campos de catálogo único (`catalog_upload_id/object_key/source_sha256/summary_json`),
  uma coluna `catalog_cascade_json` (JSON, default list): lista ORDENADA de
  entradas `{upload_id, object_key, source_sha256, origin, reference_month,
  source_label, summary}`. A ordem é a cascata — regra de precificação como dado
  (ADR-0027). Índice espelho de `ix_valuation_rounds_tenant_created` (448-450).
- `EstimateRoundRevisionRecord` (`estimate_round_revisions`): espelho append-only
  com `UniqueConstraint(round_id, version)`; colunas de artefato:
  `takeoff_packet_json, takeoff_registration_json, code_suggestions_json,
  code_assignments_json, estimate_json, extraction_lineage_json` +
  `artifact_refs_json`/`artifact_digests_json`. (Sem `valuation_json` nem
  `amendment_dossier_json` — não existem neste momento do domínio.)

Migração `0003_*` gerada por `make db-revision MESSAGE=...` e revisada à mão
(forward-only; docstring explicando, como em `0002_medicao_valuation_rounds.py`).
`BASELINE_TABLES` de `bootstrap.py` segue o precedente da 0002 (não inclui as
tabelas novas).

### Camada de aplicação — `services/api/src/croquito_api/estimate_rounds.py` (novo)

Espelho estrutural de `valuation_rounds.py` (777 linhas; leia o cabeçalho 1-24 —
nada de FastAPI aqui): `load_round`/`head_revision` escopados por tenant,
`require_base_version` (409 `REVISION_CONFLICT`), `append_revision` append-only,
precondições de etapa com `RoundRefusal` e códigos estáveis, `current_stage`,
`signed_artifact_url` (só sob `tenants/{tenant_id}/`), `round_state_payload`.
Reuse por IMPORT o que for idêntico (ex.: `RoundRefusal`, cache de catálogo) em
vez de copiar; copie só o que muda de tabela. Regras novas:

- instalar catálogo com `origin` repetido na cascata recusa
  `ESTIMATE_CASCADE_ORIGIN_DUPLICATE` (mesmo código do domínio, T1/estimate.py:181-191);
- montagem sem cascata instalada, sem takeoff revisado ou sem códigos decididos
  recusa `ROUND_STAGE_NOT_READY` (padrão existente).

### Rotas — `services/api/src/croquito_api/main.py` (ao FINAL do arquivo, depois
das rotas de valuation; a sessão paralela de traçado edita a faixa ~2245-4488 —
não toque nela)

Espelho 1:1 da tabela de `/v1/valuation-rounds*` (decorators nas linhas
5232-6266), sob `/v1/estimate-rounds`:

| Método | Path |
|---|---|
| POST/GET | `/v1/estimate-rounds` |
| GET | `/v1/estimate-rounds/{round_id}` |
| POST | `/v1/estimate-rounds/{round_id}/catalogs` (instala entrada da cascata, por presign como o catálogo da medição) |
| POST | `/v1/estimate-rounds/{round_id}/catalogs/order` (reordena; corpo = lista completa dos digests na ordem nova) |
| POST/GET | `/v1/estimate-rounds/{round_id}/plate` |
| POST | `/v1/estimate-rounds/{round_id}/plate/extractions` |
| GET | `/v1/estimate-rounds/{round_id}/takeoff` e `/takeoff/overlay` |
| POST | `/v1/estimate-rounds/{round_id}/takeoff/decisions` |
| GET/POST | `/v1/estimate-rounds/{round_id}/code-suggestions` (+ `/recompute`) |
| GET | `/v1/estimate-rounds/{round_id}/catalog/search` (busca na cascata, resultado carrega `origin` + posição na cascata) |
| GET/POST | `/v1/estimate-rounds/{round_id}/code-assignments` (+ `/decisions`; a decisão cita o catálogo da cascata — fonte na decisão, não só no relatório) |
| POST | `/v1/estimate-rounds/{round_id}/estimate` (corpo: `base_version`, `bdi_percent` string decimal; monta via `build_worksite_estimate` de T1, escreve e audita via T2 fail-closed, publica `.xlsx` no object store e grava `estimate_json` em revisão nova) |
| GET | `/v1/estimate-rounds/{round_id}/estimate` (estado + URL assinada da planilha publicada) |

Disciplina idêntica à medição, mesmos helpers:

- papel: `_require_valuation_reviewer` (main.py:1224-1236, role `orcamentista`)
  como PRIMEIRA linha de cada handler, inclusive GET — decisão humana de
  2026-08-20 (reusa o papel da medição);
- `Depends(_require_idempotency)` (2134-2144) em todo POST; `_idempotent_response`
  (1115-1138) / `_store_idempotent_response` (1141-1160);
- `require_base_version` em toda mutação após carregar o record;
- recusas como `RoundRefusal` → `problem+json` com a invariante em `details.code`
  (tradução existente, main.py:~1239); resposta bruta de provider nunca sai.

### Snapshot OpenAPI

`make openapi-snapshot` (ato deliberado); o diff de
`tests/api/openapi.snapshot.json` deve ser SÓ adição (critério 1 da feature).

### Testes — `tests/api/test_estimate_round_routes.py` (novo)

Espelhe a estrutura de `tests/api/test_valuation_round_routes.py`. Cobertura
mínima nomeada: 403 sem papel em GET e POST; POST sem `Idempotency-Key` recusa;
`base_version` velho → 409 `REVISION_CONFLICT`; `Idempotency-Key` reusada com
payload diferente → 409 `IDEMPOTENCY_KEY_REUSED`; origem repetida na cascata →
`ESTIMATE_CASCADE_ORIGIN_DUPLICATE`; caminho feliz até `estimate_json` + planilha
publicada; auditoria divergente → nada publicado e recusa estável; reordenação da
cascata muda a precificação da sugestão seguinte.

## Out of scope

- Rotas e tabelas da medição: nenhuma linha muda.
- Web (T4), CLI, `providers.py`, e a faixa do croqui em `main.py`.
- e2e (T5).

## Acceptance criteria

1. `make check` e `make test` verdes; snapshot OpenAPI atualizado por ato
   deliberado com diff só de adição.
2. Toda a cobertura mínima de testes acima passando com os códigos exatos.
3. Migração 0003 forward-only revisada (não só autogenerate cru), com docstring.
4. `git diff` não toca rota nem tabela existente da medição.

## Validation

```bash
make check
make test
uv run pytest tests/api/test_estimate_round_routes.py -x -q
uv run pytest tests/api/test_openapi_contract.py tests/api/test_migrations.py -q
```

## Required capabilities

READ, WRITE, VALIDATE. Sem COMMIT: deixe o diff na árvore.

## Report

`BUILD REPORT` completo, gravado em
docs/features/F-020-orcamento-base-web/tasks/T3-build-report.md.
