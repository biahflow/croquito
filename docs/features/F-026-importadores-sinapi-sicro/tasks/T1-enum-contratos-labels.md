# T1 — `PriceOrigin` ganha `sinapi`/`sicro`; bump minor dos schemas; labels

Task Contract derivado do [plano válido](../plan.md). Autossuficiente: assuma o Core
(pinado em `docs/engineering-os/`), este contrato, o
[ADR-0039](../../../adr/0039-sinapi-sicro-como-origens-de-preco.md) (Accepted) e o
repositório.

## Identity

```text
feature_id: F-026
task_id: T1
parent_plan: docs/features/F-026-importadores-sinapi-sicro/plan.md
depends_on: []
```

## Goal

O enum `PriceOrigin` ganha `SINAPI = "sinapi"` e `SICRO = "sicro"`; os DOIS schemas
publicados que o embutem sobem versão minor ANTES de `make contracts`; a web ganha os
textos das origens novas; o guardrail da medição é coberto nomeando-as.

## Baseline

`make check` e `make test` verdes na branch `f-026-importadores`.

## Scope

- `packages/valuation/src/croquito_valuation/models.py` (enum nas linhas 95-107):
  valores novos + docstring estendida. `NON_SCO_CODE_PATTERN` (linha 43) NÃO muda —
  as origens novas caem no superset não-SCO como o EMOP (verificado: nenhum lugar do
  código faz match exaustivo por origem; tudo compara `== PriceOrigin.SCO` ou
  origem-do-catálogo).
- `packages/valuation/src/croquito_valuation/assignment.py:62`:
  `SUGGESTION_SCHEMA_VERSION` `"1.1.0"` → `"1.2.0"` (o schema
  `code-suggestions.schema.json` embute o enum em `CodeCandidate.catalog_origin`).
  Se a versão aparecer como `Literal` em campo de modelo, acompanhe.
- `packages/valuation/src/croquito_valuation/estimate.py:59`:
  `ESTIMATE_SCHEMA_VERSION` `"2.0.0"` → `"2.1.0"` + o `Literal` do campo
  `schema_version` do `Estimate`.
- `make contracts` e commit dos gerados (nunca editar `.schema.json`/`.generated.ts`
  à mão).
- `tests/valuation/golden/estimate-demo.canonical.json`: ÚNICA mudança esperada é
  `schema_version` (linha 211) — regenere pelo caminho oficial do golden; qualquer
  outro diff é parada obrigatória. Ajuste as asserções de versão hardcoded que
  existirem nos testes (`test_canonical_golden.py`/`test_estimate.py`) — desvio
  autorizado por consequência direta, escopo mínimo.
- `apps/web/src/orcamento/labels.ts`: `PRICE_ORIGIN_LABELS` (145-149) ganha
  `sinapi: "SINAPI"` e `sicro: "SICRO"`. `priceOriginSeloClass` (160-167) NÃO ganha
  entrada: as origens novas caem no fallback `selo-neutro` de propósito (cor nova é
  decisão de design que esta feature não tem) — registre no BUILD REPORT. Teste de
  label correspondente.
- Guardrail: testes novos provando `BULLETIN_PRICE_ORIGIN_FORBIDDEN` com catálogo
  `sinapi` e com `sicro` (padrão dos existentes em `tests/valuation/test_calc.py:464`
  e `tests/valuation/test_writer_roundtrip.py:219`).

## Out of scope

- Importadores, fixtures e CLI (T2); e2e (T3).
- Qualquer outro schema do manifesto (verificado: só os dois acima embutem o enum).
- CSS/cores; `styles.css` não muda.

## Acceptance criteria

1. `make check` (sem drift de contratos) e `make test` verdes.
2. Diff do golden restrito a `schema_version`.
3. Guardrail coberto nomeando `sinapi` e `sicro`.
4. `make valuation-estimate-demo` verde e determinística.

## Validation

```bash
make check
make test
uv run pytest tests/valuation/test_calc.py tests/valuation/test_writer_roundtrip.py tests/valuation/test_canonical_golden.py -x -q
make valuation-estimate-demo
```

## Required capabilities

READ, WRITE, VALIDATE. Sem COMMIT: deixe o diff na árvore.

## Report

`BUILD REPORT` completo em
docs/features/F-026-importadores-sinapi-sicro/tasks/T1-build-report.md.
