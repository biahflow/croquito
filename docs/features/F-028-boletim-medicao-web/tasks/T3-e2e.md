# T3 — e2e: aprovação nominal + export do boletim pelas rotas `/v1`

Task Contract derivado do [plano válido](../plan.md). Autossuficiente: assuma o Core,
este contrato e o repositório.

## Identity

```text
feature_id: F-028
task_id: T3
parent_plan: docs/features/F-028-boletim-medicao-web/plan.md
depends_on: [T1]
```

## Goal

Critérios 5 e 6 da feature: a cadeia com aprovação + export roda por `/v1` sem CLI, e
o boletim exportado pela rota é logicamente idêntico ao do CLI sobre a mesma medição.

## Baseline

T1 integrado na branch; `make check` e `make test` verdes. T2 corre em paralelo em
`apps/web/` — não toque lá.

## Scope

Em `tests/e2e/` (estender `test_valuation_v1_chain.py` ou arquivo novo ao lado, no
mesmo padrão de infra in-process):

- Cadeia até o `/calc` como o e2e existente já faz; então:
  1. exportar ANTES de aprovar → `VALUATION_EXPORT_BLOCKED` com
     `VALUATION_NOT_APPROVED` na lista de `details`;
  2. `POST .../approve` → aprovação embutida (GET expõe `approved`, `approved_by` =
     subject do token, `stale: false`);
  3. `POST .../bulletin/export` → publicado; reabrir o `.xlsx` do fake store e
     comparar com o caminho do CLI (`run_export_valuation` sobre a MESMA
     `Valuation`/catálogo/template) via `canonicalize_workbook` — conteúdo lógico
     idêntico (criterion 5);
  4. recalc (`/calc` de novo) → GET expõe `stale: true`; export recusa com
     `APPROVAL_CONTENT_MISMATCH`; aprovar de novo → export volta a passar.
- A comparação com o CLI usa import das funções do worker SÓ dentro do teste de
  paridade (o resto da cadeia não passa pelo CLI — é a prova do criterion 6).

## Out of scope

- Código de produção (achado de T1 ⇒ PARE e reporte); web; demos e goldens.

## Acceptance criteria

1. `make check` e `make test` verdes com o e2e novo.
2. Paridade lógica CLI×rota provada por canonicalização, não por bytes.
3. Recusas nomeadas com os códigos exatos.

## Validation

```bash
make check
make test
uv run pytest tests/e2e -q
```

## Required capabilities

READ, WRITE, VALIDATE. Sem COMMIT: deixe o diff na árvore.

## Report

`BUILD REPORT` completo em
docs/features/F-028-boletim-medicao-web/tasks/T3-build-report.md.
