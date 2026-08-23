# T3 — Painel de evidência na revisão web

## Identity

```text
feature_id: F-030
task_id: T3
parent_plan: docs/features/F-030-levantamento-de-campo-na-revisao/plan.md
depends_on: T2
```

## Goal

A jornada web mostra e gerencia a evidência de campo conforme o Design Approval Package
revisão 3 aprovado.

## Scope

- Cliente tipado das rotas T1/T2 e componentes testáveis do painel.
- Listar/vincular/desvincular surveys, subir foto avulsa e pedir leitura textual.
- Todas as fotos visíveis por padrão; filtro manual pela âncora declarada.
- Modal de foto que preserva o contexto da revisão e oferece “Abrir original” em nova aba.
- Estados vazio, carregando, sem análise, mídia inválida, leitura pulada, recusa e sem papel.

## Out of Scope

Regras de autorização no browser, testemunhas, classificação visual e mudanças de serviço.

## Acceptance Criteria

1. O painel corresponde ao DAP rev. 3 e declara que foto não mede.
2. Nenhum filtro ou clique associa automaticamente evidência a leitura.
3. Modal fecha sem perder a leitura em revisão; “Abrir original” usa URL assinada corrente.
4. Erros de MIME, acesso e IA desabilitada aparecem sem revelar metadado indevido.
5. `npm --workspace @croquito/web run test` passa com estados e interações cobertos.

## Validation

```text
baseline: T2 BUILD_COMPLETE e gates verdes
required: npm --workspace @croquito/web run test
required: npm --workspace @croquito/web run build
required: make check
```

## Required Capabilities

```text
READ:     apps/web, docs/features/F-030, contrato OpenAPI
WRITE:    apps/web, tests web, docs da task
VALIDATE: comandos de Validation
COMMIT:   allowed
```

## Context to Read First

DAP rev. 3; ADR-0049; T1/T2 e reports; `apps/web/AGENTS.md`; componentes existentes de
`CroquiApp.tsx`, estilos e cliente HTTP.

## Known Risks

Guardar URL assinada em estado durável, inferir âncora, esconder fotos por padrão ou perder o
contexto da decisão quando o modal abre.

## Human Gates

DAP rev. 3 já foi aprovado. Alteração material de interação exige nova revisão e parada.

## Reporting

Criar `T3-build-report.md` com o `BUILD REPORT` completo.
