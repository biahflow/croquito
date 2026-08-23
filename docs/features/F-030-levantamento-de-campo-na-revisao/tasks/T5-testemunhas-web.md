# T5 — Testemunhas empilhadas na revisão web

## Identity

```text
feature_id: F-030
task_id: T5
parent_plan: docs/features/F-030-levantamento-de-campo-na-revisao/plan.md
depends_on: T3, T4
```

## Goal

Cada leitura exibe e gerencia suas testemunhas com origem, valor e diferença próprios, sem
classificar a diferença e sem confundir testemunha com cota.

## Scope

- Cliente e UI para confirmar/corrigir leitura de foto, associar e retratar testemunhas.
- Caminho legado em dois atos; seleção explícita da leitura e da fonte.
- Várias testemunhas empilhadas, com origem/autoria/instante e diferença neutra.
- Estados de concorrência otimista, erro e ausência de fonte elegível.

## Out of Scope

Serviços, tolerância, alertas de concordância/discordância e alteração automática da revisão.

## Acceptance Criteria

1. A UI não oferece associação antes da confirmação do valor lido em foto.
2. Associação e confirmação têm ações e feedback separados.
3. Testemunhas coexistem, podem ser retratadas e nunca ocultam a cota da prancha.
4. Nenhum texto, cor ou ícone afirma concordância ou discordância.
5. `npm --workspace @croquito/web run test` passa com múltiplas testemunhas e concorrência.

## Validation

```text
baseline: T3 e T4 BUILD_COMPLETE e gates verdes
required: npm --workspace @croquito/web run test
required: npm --workspace @croquito/web run build
required: make check
```

## Required Capabilities

```text
READ:     apps/web, DAP, contratos T3/T4 e OpenAPI
WRITE:    apps/web, testes web, docs da task
VALIDATE: comandos de Validation
COMMIT:   allowed
```

## Context to Read First

DAP rev. 3 estados 5–7; ADR-0049; reports T3/T4; `apps/web/AGENTS.md`.

## Known Risks

Fundir os dois atos do legado, escolher testemunha vencedora, usar cor de alerta ou inferir
associação a partir da âncora selecionada.

## Human Gates

Qualquer regra de tolerância ou promoção automática exige parada.

## Reporting

Criar `T5-build-report.md` com o `BUILD REPORT` completo.
