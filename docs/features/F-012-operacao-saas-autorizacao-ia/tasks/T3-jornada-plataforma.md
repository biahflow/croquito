# T3 — Jornada Plataforma na SPA

Task Contract no formato do [template global](../../../engineering-os/templates/task.md),
derivado do [plano válido](../plan.md). Autossuficiente.

## Identity

```text
feature_id: F-012
task_id: T3
parent_plan: docs/features/F-012-operacao-saas-autorizacao-ia/plan.md
depends_on: [T2]
```

## Goal

Quem tem o papel `platform_operator` vê uma terceira jornada — "Plataforma" — e
ativa/desativa o entitlement de IA de qualquer tenant pela tela, com
`agreement_reference`, sem curl e sem DevTools. Quem não tem o papel não vê o botão
e, forçando a query, recebe erro legível.

## Scope

- **`apps/web/src/route.ts`**: `PLATFORM_PARAM = "plataforma"`; variante
  `{ kind: "plataforma" }` em `Route`; leitura por PRESENÇA do parâmetro em
  `readRoute` (depois de `rodada` — precedência `job > rodada > plataforma`);
  `?plataforma=` em `routeSearch` (forma canônica, padrão `?rodada`).
  `entryRedirect` INTOCADO — a query inteira já viaja no state do OIDC (88-90),
  então `?plataforma` sobrevive ao login de graça. Atualizar o comentário de
  cabeçalho que recusou um kind para `/login` (19-23), contrastando os critérios:
  plataforma TEM forma canônica de query, é alternável pelo seletor e sobrevive a
  `routeSearch` — é jornada. `route.test.ts`: round-trips e precedência.
- **`apps/web/src/plataforma/`** (novo, espelho de `src/medicao/`):
  - `api.ts`: `fetchMe`, `listTenants`, `getEntitlement`, `setEntitlement` sobre o
    `apiJson` de `../api`; a mutação envia `Idempotency-Key: crypto.randomUUID()`
    por gesto (padrão das 13 mutações existentes; replay de retentativa reusa a
    chave — ver comentário em `../api.ts:485`). Tipos alinhados às respostas da T2.
  - `labels.ts`: problem+json → frase (403/`FORBIDDEN`, ausência de
    `agreement_reference`, rede) no padrão de `medicao/labels.ts`.
  - `PlatformApp.tsx`: lista de tenants com estado por extenso e datas; ação
    ativar/desativar POR LINHA com input de `agreement_reference` e gesto explícito
    de confirmação; formulário texto-livre "ativar tenant novo" (tenant só-Keycloak
    não aparece na lista — o PUT aceita qualquer tenant_id); erro persistente com
    `role="alert"`; sucesso transitório; cor nunca é o único indicador; 403 no meio
    da sessão (papel removido) mostra erro persistente, nunca tela branca.
  - Testes irmãos (vitest) com `fetch` mockado: payload do PUT, header
    Idempotency-Key presente, renderização dos estados, erro legível.
- **`apps/web/src/App.tsx`**: buscar `/v1/me` UMA vez após a sessão estabelecer;
  terceiro botão no `journey-switch` (~393-410) renderizado APENAS quando `roles`
  contém `platform_operator` — ausente, não desabilitado; `aria-current` como os
  outros; falha no `/v1/me` = sem botão (fail-closed, sem erro na tela); branch de
  render `route.kind === "plataforma"` (~450-456) montando `PlatformApp`.
  `App.test.tsx`: botão presente com papel, ausente sem papel.

Antes de escrever a tela, ler `docs/engineering/DESIGN_SYSTEM.md` (exigência do
`apps/web/AGENTS.md`) e o `apps/web/AGENTS.md`.

## Out of Scope

`auth.ts` (scopes/token — a SPA continua sem decodificar token), `CroquiApp.tsx`,
`MedicaoApp.tsx`, backend, contratos gerados.

## Acceptance Criteria

1. `make check` (inclui `tsc -b` + build) e `make test` (vitest) verdes.
2. Round-trip `?plataforma=` e precedência `job > rodada > plataforma` cobertos em
   `route.test.ts`.
3. Botão só com papel (teste), mutação com `Idempotency-Key` (teste), erro
   problem+json legível e persistente (teste).
4. Nenhum arquivo fora do escopo alterado.

## Validation

```text
baseline: make check e make test verdes após T2 na branch
required: full: make check
          full: make test
```

## Required Capabilities

```text
READ:     o repositório
WRITE:    apps/web/src/route.ts, apps/web/src/route.test.ts, apps/web/src/App.tsx,
          apps/web/src/App.test.tsx, apps/web/src/plataforma/** (novo)
VALIDATE: make check; make test
COMMIT:   forbidden — diff na árvore + BUILD REPORT
```

## Context to Read First

`AGENTS.md` raiz + `apps/web/AGENTS.md` + `docs/engineering/DESIGN_SYSTEM.md`;
`route.ts` inteiro; `App.tsx` 380-460; `src/medicao/` (padrão de módulo de
jornada); `api.ts` 460-560 (apiJson e Idempotency-Key); respostas reais da T2 em
`services/api/src/croquito_api/main.py`.

## Known Risks

Precedência de rotas; `/v1/me` chamado mais de uma vez por render; botão
"desabilitado" em vez de ausente (vaza a existência da área); esquecer que a lista
não mostra tenant sem pegada no banco (por isso o campo texto-livre é obrigatório).

## Human Gates

Nenhum no escopo.

## Reporting

`BUILD REPORT` completo do [contrato do Builder](../../../engineering-os/agents/builder.md),
gravado também em `docs/features/F-012-operacao-saas-autorizacao-ia/tasks/T3-build-report.md`.
