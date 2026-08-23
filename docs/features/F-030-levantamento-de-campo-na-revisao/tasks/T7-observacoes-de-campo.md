# T7 — Observações humanas sobre a classificação

## Identity

```text
feature_id: F-030
task_id: T7
parent_plan: docs/features/F-030-levantamento-de-campo-na-revisao/plan.md
depends_on: T3, T6
```

## Goal

O rascunho da IA aparece com lineage e o revisor pode registrar ou descartar sua conclusão
numa observação versionada fora da `SceneRevision`.

## Scope

- `POST /v1/jobs/{job_id}/review/field-observations`, otimista e idempotente.
- Observação com categoria controlada, descrição livre, fonte/classificação e autoria.
- Descarte auditado sem criar observação ativa.
- UI do rascunho, estados desabilitado/pendente/falha e atos registrar/descartar.
- Testes de que aceitar, corrigir ou descartar não modifica cena nem exportação.

## Out of Scope

Endpoint antigo `/review/notes`, `Entity`, `Issue`, blocker, solver e qualquer mutação de
geometria.

## Acceptance Criteria

1. Categoria e descrição registradas resultam de ato explícito e podem ser corrigidas.
2. A observação viaja em `field_observations_json`; digest/revisão de cena permanecem iguais.
3. Descartar não cria entidade nem remove evidência/classificação.
4. Papel/tenant/versionamento/idempotência falham fechados.
5. Testes API e web provam invariância da cena e da exportação.

## Validation

```text
baseline: T3 e T6 BUILD_COMPLETE e gates verdes
required: make check
required: make test
required: npm --workspace @croquito/web run test
```

## Required Capabilities

```text
READ:     packages/core, services/api, apps/web, tests, docs
WRITE:    packages/core, services/api, apps/web, tests, docs
VALIDATE: comandos de Validation
COMMIT:   allowed
```

## Context to Read First

ADR-0049 decisão 3/emenda; DAP rev. 3 estado 8; T3/T6 e reports; revisão e audit log atuais.

## Known Risks

Reutilizar `/review/notes` e contaminar a cena, registrar proposta sem ato humano ou apagar o
artefato de classificação ao descartar.

## Human Gates

Alterar a observação para entidade/issue/nota de cena exige nova decisão de arquitetura.

## Reporting

Criar `T7-build-report.md` com o `BUILD REPORT` completo.
