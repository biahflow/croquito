# T4 — Runbook sem passos manuais, ROADMAP com inventário SaaS

Task Contract no formato do [template global](../../../engineering-os/templates/task.md),
derivado do [plano válido](../plan.md). Autossuficiente.

## Identity

```text
feature_id: F-012
task_id: T4
parent_plan: docs/features/F-012-operacao-saas-autorizacao-ia/plan.md
depends_on: [T1, T2, T3]
```

## Goal

A documentação reflete a operação nova: ativar IA é uma tela, documento não passa
por digest, e todo gargalo manual restante tem número no roadmap. Espelhe o que o
código FAZ (leia os diffs e build reports T1-T3 antes).

## Scope

- **`docs/operations/HML.md`** (seção "Providers de IA"): tabela de envs sem a
  linha da allowlist; runbook reescrito — passos de infra viram histórico
  concluído; "entitlement via curl" vira "ativar pela jornada Plataforma
  (`?plataforma=`), papel `platform_operator`"; passos de digest e
  redeploy-por-documento SOMEM; "subir o PDF pela SPA depois da ativação" e kill
  switch/aviso de custo FICAM.
- **`docs/product/ROADMAP.md`**: linha e parágrafo da F-012 (aprovada 2026-08-19,
  HIGH); inventário novo com uma linha cada — F-013 UI de membros do tenant
  (depende de F-008), F-014 entidade tenant + onboarding self-service, F-015
  recriar job de upload existente, F-016 rotação de chaves/segredos de provider,
  F-017 custo agregado por tenant + trilha de auditoria do entitlement na tela.
  F-008 permanece BLOCKED (decisão de provedor de e-mail é do usuário).
- **`docs/STATUS.md`**: parágrafo da F-012 no estilo dos existentes.
- **`docs/features/F-012-operacao-saas-autorizacao-ia/feature.md`**: Status real ao
  fim da execução.
- **FDD** (`docs/product/FDD.md` ou onde a Disciplina de mudança do AGENTS.md
  mandar — verifique): a jornada Plataforma como comportamento novo.
- Conferir se `docs/ai/MODEL_ROUTING.md` ou o ADR-0035 mencionam a allowlist como
  viva no caminho hospedado — se sim, nota curta apontando o ADR-0036 (sem
  reescrever o ADR-0035, que é registro histórico).

## Out of Scope

Código; mudar decisões; evidence.md (integração).

## Acceptance Criteria

1. `make check` verde (check_docs valida todos os links).
2. Runbook sem nenhuma menção a digest/redeploy por documento como passo vivo.
3. F-012..F-017 no ROADMAP com uma linha cada e datas.

## Validation

```text
baseline: make check verde após T1-T3 na branch
required: full: make check
```

## Required Capabilities

```text
READ:     o repositório (inclusive git diff da branch e build reports T1-T3)
WRITE:    docs/ somente
VALIDATE: make check
COMMIT:   forbidden — diff na árvore + BUILD REPORT
```

## Context to Read First

`AGENTS.md` (Disciplina de mudança), build reports T1-T3, `HML.md` seção de
providers inteira, `ROADMAP.md`, `ADR-0036` escrito pela T1.

## Known Risks

Link quebrado reprova CI; registrar intenção em vez de realidade.

## Human Gates

Nenhum no escopo.

## Reporting

`BUILD REPORT` completo do [contrato do Builder](../../../engineering-os/agents/builder.md),
gravado também em `docs/features/F-012-operacao-saas-autorizacao-ia/tasks/T4-build-report.md`.
