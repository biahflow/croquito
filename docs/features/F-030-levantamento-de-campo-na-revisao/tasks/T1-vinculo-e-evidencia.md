# T1 — Vínculo job ↔ levantamento e leitura da evidência

## Identity

```text
feature_id: F-030
task_id: T1
parent_plan: docs/features/F-030-levantamento-de-campo-na-revisao/plan.md
depends_on: none
```

## Goal

O escritório consegue listar levantamentos concluídos, vinculá-los ou desvinculá-los de um
job e ler, numa rota própria, as fotos confirmadas, análises existentes e medidas confirmadas.

## Scope

- Migration aditiva e forward-only `0017`: vínculo muitos-para-muitos job ↔ survey, com tenant,
  autor e instante; colunas JSON versionadas de testemunhas e observações na revisão.
- Modelos, schemas e rotas da API para listar surveys concluídos, vincular, desvincular e
  `GET /v1/jobs/{job_id}/field-evidence`.
- URL assinada criada somente na resposta para mídia `CONFIRMED`; leitura do artefato de
  análise já persistido; medidas `confirmed` incluídas com origem explícita.
- Snapshot OpenAPI, contrato da API e testes determinísticos/API/migration.

## Out of Scope

Upload avulso, chamada de IA, testemunhas, interface, infraestrutura e deploy.

## Acceptance Criteria

1. Um survey concluído pode atender vários jobs e um job pode vincular vários surveys.
2. Vincular e desvincular exigem papel de escritório, `Idempotency-Key` e versão otimista.
3. Evidência de outro tenant responde `404`; papel incorreto não recebe metadado nem URL.
4. A resposta nunca contém mídia não confirmada e nenhuma URL assinada é persistida.
5. Job sem vínculo preserva o comportamento existente e devolve coleção vazia.
6. `make test` passa com cobertura de rota, migration e snapshot OpenAPI da task.

## Validation

```text
baseline: make check; make test — verdes em main@721cb8b (2378 Python, 1075 web, 261 field)
required: make check
required: make test
```

## Required Capabilities

```text
READ:     packages/core, services/api, migrations, tests, docs
WRITE:    packages/core, services/api, migrations, tests, docs
VALIDATE: comandos de Validation
COMMIT:   allowed
```

## Context to Read First

ADR-0049; feature e plano da F-030; `services/api/AGENTS.md`; modelos `Survey*Record`,
`ReviewRevisionRecord`, helpers de papel/idempotência e o fluxo de URL assinada existente.

## Known Risks

Vazar URL ou metadado entre tenants; transformar ausência de análise em erro; incluir mídia
`PRESIGNED`; carregar a evidência no `ReviewResponse`; migration destrutiva.

## Human Gates

Nenhum dentro da task. Apply em banco hospedado é rollout da T8, não execução desta task.

## Reporting

Criar `T1-build-report.md` com o `BUILD REPORT` completo do contrato de Builder.
