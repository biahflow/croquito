# T8 — E2E, evidência e rollout em HML

## Identity

```text
feature_id: F-030
task_id: T8
parent_plan: docs/features/F-030-levantamento-de-campo-na-revisao/plan.md
depends_on: T5, T7
```

## Goal

A entrega completa é validada localmente, publicada somente em HML e encerrada com evidência
reproduzível em `READY_FOR_HUMAN_REVIEW`.

## Scope

- E2E da jornada: survey vinculado, foto avulsa, leitura confirmada, várias testemunhas,
  classificação e observação; exportação permanece possível.
- Migration `0017` num PostgreSQL vazio, snapshot OpenAPI, ausência de drift e gates completos.
- Rodada real única de seis fotos após corpus humano, usando o candidato T6 e teto de US$ 5.
- No repo `biahflow/infra`: retenção por prefixo que preserve `surveys/` e
  `jobs/*/field-evidence/`; branch/PR, `terraform plan` revisado e apply em HML.
- Um único push da `main`; acompanhamento de `deploy-hml`; smoke autenticado e isolamento.
- `evidence.md`, roadmap, STATUS e Feature Contract em `READY_FOR_HUMAN_REVIEW`.

## Out of Scope

Produção, rerun pago para escolher resultado, `make docs`, aceite humano final e estado `DONE`.

## Acceptance Criteria

1. `make check`, `make test`, testes web, OpenAPI, migration vazia e Terraform passam.
2. Rodada real: schema/lineage 6/6, nenhuma medida/geometria 6/6, categoria ≥5/6, zero erro
   com confiança alta e custo ≤ US$ 5; qualquer falha interrompe publicação completa.
3. Infra preserva os prefixos duráveis e o plano externo é revisado antes do apply HML.
4. Deploy HML conclui migration/API/worker/web no mesmo SHA e produção não é tocada.
5. Smoke cobre autenticação, tenant, vínculo, foto, testemunhas, IA desabilitada sem entitlement
   e jornada completa sem repetir a rodada paga.
6. Diff final é apenas F-030/infra autorizada; commits locais permanecem separados e um único
   push integra a `main`.

## Validation

```text
baseline: T5 e T7 BUILD_COMPLETE e todos os gates locais verdes
required: make check
required: make test
required: npm --workspace @croquito/web run test
required: make infra-check
```

## Required Capabilities

```text
READ:     repositório croquito, biahflow/infra, GitHub Actions e HML
WRITE:    testes/evidência/docs, branch de infra, estado HML autorizado
VALIDATE: comandos locais, terraform plan/apply, workflows e smoke HML
COMMIT:   allowed
```

## Context to Read First

Feature/plano/evidence da F-030; reports T1–T7; ADR-0049; workflows de deploy; AGENTS do repo
de infra; runbooks de HML e migration; contrato da eval real.

## Known Risks

Publicar após gate pago falho, expirar evidência, aplicar produção, repetir chamada, misturar
SHAs no HML ou marcar `DONE` sem aceite humano.

## Human Gates

- Corpus de seis fotos/rótulos precisa ser fornecido fora do Git antes da rodada real.
- `terraform plan` do repo externo deve ser revisado antes do apply.
- `DONE` exige aceite humano posterior da entrega em HML.

## Reporting

Criar `T8-build-report.md` e consolidar `../evidence.md` com commits, testes, eval paga, custo,
Terraform, deploy e smoke.
