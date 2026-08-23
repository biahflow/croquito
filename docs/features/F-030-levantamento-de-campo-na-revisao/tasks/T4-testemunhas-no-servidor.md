# T4 — Testemunhas de medida no servidor

## Identity

```text
feature_id: F-030
task_id: T4
parent_plan: docs/features/F-030-levantamento-de-campo-na-revisao/plan.md
depends_on: T2
```

## Goal

O revisor associa ou retrata várias testemunhas explícitas de uma leitura sem alterar cena,
precisão, solver, blockers ou exportação.

## Scope

- Confirmação/correção humana do valor textual lido em foto avulsa.
- `POST /v1/jobs/{job_id}/review/witnesses` versionado e idempotente para associar/retratar.
- Fontes: `Measurement` do app com status `confirmed`, ou leitura de foto já confirmada.
- Valor resolvido no servidor; autoria/instante/origem persistidos em `field_witnesses_json`.
- Várias testemunhas por leitura; diferença individual calculada e semanticamente neutra.
- Testes negativos de inferência, promoção, blocker, solver e exportação.

## Out of Scope

Interface, tolerância numérica, classificação concorda/discorda, alteração da cena.

## Acceptance Criteria

1. Confirmar o valor e associá-lo são atos separados com versões/idempotência próprias.
2. Valor vindo do cliente nunca substitui o valor canônico resolvido no servidor.
3. Medida draft e leitura de foto não confirmada são recusadas.
4. Associação não nasce de valor, `kind`, rótulo, âncora ou proximidade.
5. Várias testemunhas coexistem e podem ser retratadas individualmente.
6. Testes provam que nenhuma testemunha muda precisão, blockers, solver, cena ou exportação.
7. `make test` passa com os testes positivos e negativos da task.

## Validation

```text
baseline: T2 BUILD_COMPLETE e gates verdes
required: make check
required: make test
```

## Required Capabilities

```text
READ:     packages/core, services/api, tests, docs
WRITE:    packages/core, services/api, tests, docs
VALIDATE: comandos de Validation
COMMIT:   allowed
```

## Context to Read First

ADR-0049 decisões 4–8 e 16; T2/report; precedente `declared_chains`; composição de revisão,
portão de exportação e regras de versionamento/idempotência.

## Known Risks

Confiar em valor do corpo, tornar testemunha uma decisão, substituir em vez de empilhar ou
inventar um limiar escondido.

## Human Gates

Qualquer tolerância ou classificação da diferença exige calibração e decisão futura; pare.

## Reporting

Criar `T4-build-report.md` com o `BUILD REPORT` completo.
