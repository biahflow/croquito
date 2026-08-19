# T2 — API legível de plataforma: /v1/me e GETs do entitlement

Task Contract no formato do [template global](../../../engineering-os/templates/task.md),
derivado do [plano válido](../plan.md). Autossuficiente.

## Identity

```text
feature_id: F-012
task_id: T2
parent_plan: docs/features/F-012-operacao-saas-autorizacao-ia/plan.md
depends_on: none
```

## Goal

A plataforma vira superfície legível: a SPA descobre quem é o principal
(`GET /v1/me`) e o operador lista tenants e consulta o estado do entitlement por
rota — hoje só existe o PUT, e o estado é ilegível sem acesso ao banco.

## Scope

Em `services/api/src/croquito_api/main.py` (rotas como closures em `create_app`,
padrão do arquivo):

- **`GET /v1/me`** (declarar junto de `/v1/meta`, ~2184): exige só autenticação
  (nenhum papel); responde `MeResponse {subject: str, tenant_id: str, roles:
  list[str]}` com `sorted(roles)` do principal (o parse já existe — `auth.py:21-24`).
  NUNCA devolve claims brutos nem token; nada disso em log.
- **`GET /v1/platform/tenants`** (junto do PUT, ~2196): guard
  `_require_platform_operator` (1455-1461). Fonte: UNION real de
  `SELECT DISTINCT tenant_id` sobre `tenant_ai_processing_entitlements`, `projects`
  e `uploads` (uploads = pegada mais precoce), com left-join/lookup do entitlement
  de cada um; ordenação determinística por `tenant_id` (SQLite dos testes e
  PostgreSQL do HML têm que concordar). Resposta
  `PlatformTenantListResponse {tenants: list[PlatformTenantResponse]}`.
- **`GET /v1/platform/tenants/{tenant_id}/ai-processing-entitlement`**: mesmo
  guard; responde **200 sempre** — `PlatformTenantResponse {tenant_id, enabled:
  bool, agreement_reference: str | None, authorized_at: datetime | None,
  revoked_at: datetime | None}`; tenant nunca ativado = `enabled: false` com nulos
  (não há tabela de tenants; 404 seria arbitrário).
- Leituras: SEM `Idempotency-Key`, SEM auditoria (auditoria segue só no PUT). O
  `AiProcessingEntitlementResponse` do PUT NÃO muda.
- Modelos Pydantic novos junto de `SetAiProcessingEntitlementRequest` (~248).

Testes em `tests/api/test_api.py` (helper `_headers(...)` já existe):
403 sem papel nos dois GETs de plataforma; `/v1/me` devolve subject/tenant/roles
com e sem `platform_operator`; listagem inclui tenant que só tem upload, tenant que
só tem project e tenant com entitlement; GET unitário nunca-ativado → PUT ativa →
GET reflete → PUT revoga → GET reflete.

Contrato: rodar `make openapi-snapshot` (ato deliberado, Makefile:60-65) e conferir
que o diff de `tests/api/openapi.snapshot.json` SÓ adiciona as três rotas novas.
Atualizar `docs/architecture/API_CONTRACT.md` (seção "Autorização contratual de
IA", ~89): os dois GETs e o `/v1/me`.

## Out of Scope

Front (T3). PUT existente. Worker. Entidade tenant (F-014). Qualquer rota além das
três.

## Acceptance Criteria

1. `make check` e `make test` verdes (inclui o teste de contrato OpenAPI).
2. Diff do snapshot só com adições (checado por git diff).
3. 403 sem papel; 200-disabled para nunca-ativado; tenant só-upload listado —
   todos cobertos por teste.
4. `/v1/me` sem papel exigido, sem claims brutos.

## Validation

```text
baseline: make check e make test verdes na ponta da branch (base 852f51d)
required: full: make openapi-snapshot (deliberado) + make check + make test
```

## Required Capabilities

```text
READ:     o repositório
WRITE:    services/api/src/croquito_api/main.py, tests/api/test_api.py,
          tests/api/openapi.snapshot.json (via make openapi-snapshot),
          docs/architecture/API_CONTRACT.md
VALIDATE: make openapi-snapshot; make check; make test
COMMIT:   forbidden — diff na árvore + BUILD REPORT
```

## Context to Read First

`AGENTS.md`, `CLAUDE.md`, `main.py` 1455-1461 e 2184-2290, `auth.py` (principal e
roles), `database.py` (tabelas com tenant_id), `test_api.py:139-204`,
`API_CONTRACT.md` seção de IA.

## Known Risks

UNION×dialeto (SQLite/PostgreSQL); vazamento de claims no /v1/me; snapshot com
mudança em rota existente = regressão.

## Human Gates

Nenhum no escopo.

## Reporting

`BUILD REPORT` completo do [contrato do Builder](../../../engineering-os/agents/builder.md),
gravado também em `docs/features/F-012-operacao-saas-autorizacao-ia/tasks/T2-build-report.md`.
