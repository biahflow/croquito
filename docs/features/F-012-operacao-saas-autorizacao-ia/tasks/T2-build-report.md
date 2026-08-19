# T2 — BUILD REPORT

Task: `docs/features/F-012-operacao-saas-autorizacao-ia/tasks/T2-api-plataforma.md`
Branch: `feat/f-012-operacao-saas-autorizacao-ia` (sem commit — diff na árvore + este relatório)
Baseline: `852f51d` / ponta local `b01af5a` (commit docs-only da F-012)

```text
BUILD REPORT

Status: BUILD_COMPLETE

Files changed:
  - services/api/src/croquito_api/main.py (+124)
      motivo: 3 modelos Pydantic novos (MeResponse, PlatformTenantResponse,
      PlatformTenantListResponse) junto de SetAiProcessingEntitlementRequest (~248);
      2 helpers (_all_known_tenant_ids, _platform_tenant_response) junto de
      _require_platform_operator (~1455); 3 rotas GET (/v1/me, /v1/platform/tenants,
      /v1/platform/tenants/{tenant_id}/ai-processing-entitlement) declaradas junto de
      /v1/meta e do PUT existente (~2184-2300), como pedia o spec.
  - tests/api/test_api.py (+141)
      motivo: 6 testes novos cobrindo os critérios de aceite (ver "Testes novos").
  - tests/api/openapi.snapshot.json (regenerado via `make openapi-snapshot`, +197/-0)
      motivo: ato deliberado do spec — snapshot precisa refletir as 3 rotas novas.
  - docs/architecture/API_CONTRACT.md (+22)
      motivo: documentar GET /v1/me e os dois GETs de plataforma na seção
      "Autorização contratual de IA" / "Metadados públicos", exigido pelo spec e pelo
      gate de paridade `test_toda_rota_exposta_esta_no_contrato`.

Validation executed:
  - make openapi-snapshot: regenerado; `git diff tests/api/openapi.snapshot.json`
    conferido linha a linha — 197 inserções, 0 remoções (`git diff --numstat`); todas
    as adições são as 3 rotas novas (/v1/me, GET /v1/platform/tenants, GET
    /v1/platform/tenants/{tenant_id}/ai-processing-entitlement) e os 3 schemas novos
    (MeResponse, PlatformTenantResponse, PlatformTenantListResponse). Nenhuma rota
    existente mudou.
  - uv run ruff check . -> All checks passed!
  - uv run ruff format --check . -> 358 files already formatted
  - uv run mypy packages/core/src packages/valuation/src services/api/src
    services/worker/src tests -> Success: no issues found in 187 source files
  - uv run python -m croquito_core.schema_export --check-dir packages/contracts ->
    sem drift (sem output = sem divergência)
  - npm run contracts:check -> sem drift
  - npm run web:check (tsc -b && vite build) -> build OK
  - uv run pytest tests/api/ -> 220 passed, 10 skipped
  - make test (uv run pytest completo + npm web:test) -> 1476 passed, 10 skipped
    (Python) + 529 passed (web, 29 arquivos)
  - uv run python scripts/check_docs.py -> 1 falha preexistente, ver "Desvios"

Validation skipped: none

Unavailable capabilities: none

Assumptions:
  - "Tenant que só tem project" não é alcançável pela API real (POST /v1/jobs sempre
    cria upload+project juntos no mesmo tenant), então o teste
    `test_platform_tenant_listing_unions_uploads_projects_and_entitlements` insere um
    `ProjectRecord` direto via `database.sessions()` para exercitar a tabela `projects`
    isolada na UNION — mesmo padrão já usado no teste existente de
    `AiProcessingAuthorizationRecord` (test_api.py:188-189).
  - `PlatformTenantResponse` é modelo distinto de `AiProcessingEntitlementResponse`
    (não reaproveitado), porque o spec exige campos opcionais (agreement_reference,
    authorized_at) que o modelo do PUT não tem, e explicitamente proíbe mudar o
    contrato do PUT.

Remaining risks:
  - Nenhum novo. UNION testada só contra SQLite (suíte de testes); dialeto
    PostgreSQL do HML não foi exercitado nesta task (fora do escopo/capacidades do
    Builder — nenhum ambiente PostgreSQL disponível aqui). A query usa apenas
    `select(...).distinct().union(...)` padrão do SQLAlchemy Core, sem SQL cru nem
    função específica de dialeto, então o risco de divergência é baixo, mas fica
    registrado como não verificado empiricamente em PostgreSQL.

Human decisions required: none no escopo desta task.
```

## Desvios conscientes do spec

1. **`make check` reprova em `scripts/check_docs.py` por motivo alheio ao diff
   desta task.** A falha é:
   `docs/features/F-012-operacao-saas-autorizacao-ia/feature.md: diretório de feature
   sem linha correspondente no roadmap`. Evidência de que é preexistente e fora do
   escopo de T2 (e também fora do escopo declarado de T1, que mexe em
   `services/worker` e `.github/workflows`): rodei `git stash` (sem `-u`) e
   `make check` na ponta `b01af5a` — commit **docs-only** que criou
   `docs/features/F-012.../feature.md` sem tocar `ROADMAP.md` — e a mesma falha já
   aparece, sem nenhuma mudança de código de T1 ou T2 presente. `ROADMAP.md` não está
   na lista `WRITE` das Required Capabilities desta task, então não editei — parei
   essa parte e registro aqui em vez de consertar área alheia (regra do próprio
   contrato: "Se algo reprovar em área que você não tocou, PARE e reporte").
   Confirmei que todos os demais passos de `make check` que dependem do meu diff
   passam quando rodados isoladamente: `ruff check`, `ruff format --check`, `mypy`
   estrito, `schema_export --check-dir`, `contracts:check` e `web:check` (tsc + vite
   build) — todos verdes. `infra-check` não foi afetado (nada em `infra/` foi tocado).
   `make test` completo passou (1476 + 529, ver acima).
2. Nenhum outro desvio. Escopo, modelos, rotas, guard, formato de resposta 200-sempre
   e ausência de idempotência/auditoria nas leituras seguem exatamente o spec.

## Oportunidades vistas e não implementadas (fora de escopo)

- A UI/consumo em `apps/web` das três rotas novas é a T3 (fora do escopo aqui).
- `feature.md`/`ROADMAP.md` não sincronizados — fora das Required Capabilities de T2
  (nem T1, pelo que se observa no diff paralelo, mexe nisso); provável trabalho de
  T4 (docs) ou ato humano de atualizar o roadmap.
- Não criei índice de tenants nem tabela de tenants — o spec é explícito: "Entidade
  tenant (F-014)" está fora de escopo.
