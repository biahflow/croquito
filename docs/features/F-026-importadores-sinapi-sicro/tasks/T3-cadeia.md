# T3 — A cadeia do orçamento prova as origens novas de ponta a ponta

Task Contract derivado do [plano válido](../plan.md). Autossuficiente: assuma o Core,
este contrato e o repositório.

## Identity

```text
feature_id: F-026
task_id: T3
parent_plan: docs/features/F-026-importadores-sinapi-sicro/plan.md
depends_on: [T1, T2]
```

## Goal

Critério 3 da feature: cascata com origem nova percorre a cadeia inteira — decisão de
código citando a fonte, linha com proveniência nova, coluna `FONTE` impressa — sem
enfraquecer nenhum teste existente.

## Baseline

T1 e T2 integrados na branch; `make check` e `make test` verdes.

## Scope

- `tests/e2e/test_estimate_rounds_v1.py`: a cascata do e2e `/v1` ganha uma fonte
  `sinapi` (catálogo produzido pelo importador real de T2 sobre a fixture, instalado
  por upload/rota como as demais); pelo menos um item decidido citando-a; asserções:
  linha do `Estimate` com `price_origin == "sinapi"` e planilha reaberta com
  `SINAPI` na célula `FONTE` da linha.
- `tests/e2e/test_valuation_full_chain.py`: teste novo (ou extensão da fixture
  `estimate_chain`) com `import-sinapi` E `import-sicro` pelo CLI e cascata de cinco
  fontes no `build-estimate`, validando o `estimate.json` resultante.
- NENHUMA asserção existente é afrouxada; contagens/valores existentes só mudam se
  forem consequência direta e declarada da fonte nova no cenário (prefira cenário
  aditivo a alterar o existente).

## Out of scope

- Código de produção: se a cadeia não fechar, é achado de T1/T2 — PARE e reporte.
- Demos e goldens (nada muda aqui).

## Acceptance criteria

1. `make check` e `make test` verdes.
2. As asserções nomeadas existem e nomeiam `sinapi`/`sicro` literalmente.

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
docs/features/F-026-importadores-sinapi-sicro/tasks/T3-build-report.md.
