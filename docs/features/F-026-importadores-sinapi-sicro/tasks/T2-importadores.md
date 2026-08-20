# T2 — Importadores SINAPI e SICRO (layout como dado, fail-closed) + CLI

Task Contract derivado do [plano válido](../plan.md). Autossuficiente: assuma o Core,
este contrato, o [ADR-0039](../../../adr/0039-sinapi-sicro-como-origens-de-preco.md)
(Accepted) e o repositório. O molde é o importador EMOP INTEIRO — leia
`packages/valuation/src/croquito_valuation/emop.py`,
`services/worker/src/croquito_worker/valuation/emop_fixture.py` e
`tests/valuation/test_emop.py` antes de escrever qualquer linha.

## Identity

```text
feature_id: F-026
task_id: T2
parent_plan: docs/features/F-026-importadores-sinapi-sicro/plan.md
depends_on: [T1]
```

## Goal

Dois importadores novos, um por fonte, que leem planilha `.xlsx` sintética com layout
declarado como dado e produzem `PriceCatalog` com `origin` próprio (`sinapi`/`sicro`),
digest e `reference_month` — recusando fail-closed qualquer divergência de layout. Os
dois comandos de CLI espelham `import-emop`.

## Baseline

T1 integrado na branch; `make check` e `make test` verdes.

## Scope

### `packages/valuation/src/croquito_valuation/sinapi.py` e `sicro.py` (novos)

Molde: `emop.py` (layout 75-131, importação 299-388). Diferenças permitidas: o
arquivo de entrada é `.xlsx` (leitor mínimo via `openpyxl` `read_only` — openpyxl já
é dependência do projeto; NADA de dependência nova) em vez de `.DBF`. Cada fonte tem:

- `SinapiCatalogLayout`/`SicroCatalogLayout`: `source_label`, `reference_month`,
  `sheet_name`, `header_row`, colunas por letra (`code_column`, `description_column`,
  `unit_column`, `price_column`), `code_pattern` (validado como no EMOP: compila e
  recusa casar vazio). O padrão REAL de cada fonte é dado do layout; o
  `code_pattern` da fixture fixa o sintético.
- `read_sinapi_catalog_with_report`/`read_sicro_catalog_with_report`: fail-closed na
  ordem do EMOP — estrutura do arquivo → aba/campo declarado ausente
  (`SINAPI_SHEET_MISSING`/`SINAPI_FIELD_MISSING`, idem SICRO) → por linha (código
  fora do padrão, preço não numérico/negativo — `Decimal` a partir do valor da
  célula SEM passar por float; célula float do xlsx recusa a linha
  (`*_ROW_UNPARSEABLE`) em vez de converter, coerente com `ExactDecimal` — descrição
  vazia) → planilha sem linha válida (`*_EMPTY`). Catálogo sai sempre com a origem
  da fonte; entradas com a mesma origem (o `CATALOG_ORIGIN_MIXED` do domínio é a
  segunda linha).

### Fixtures — `services/worker/src/croquito_worker/valuation/sinapi_fixture.py` e
`sicro_fixture.py` (novos)

Molde `emop_fixture.py`: gerador determinístico do `.xlsx` sintético (openpyxl, data
fixa como o escritor de planilhas já faz), layout casado
(`sinapi_fixture_layout()`/...), padrões de código próprios e distintos — SINAPI
numérico puro (ex.: `^\d{7}$`), SICRO com prefixo próprio (ex.: `^\d{4}\.\d{2}\.\d{2}$`)
— e gabarito de entradas esperadas para os testes. Parametrização mínima para os
testes de recusa adulterarem o arquivo (como `write_emop_dbf` faz).

### CLI — `services/worker/src/croquito_worker/valuation/cli.py`

`import-sinapi` e `import-sicro` espelhando `import-emop` (parser 2703-2718, função
`run_import_emop` 764-807, dispatch em `main()` 3081): `--input`, `--layout`
(obrigatório, JSON do layout), `--output`; publica `catalog.json` + relatório de
importação próprio; recusa com exit code 2 sem publicar nada.

### Testes — `tests/valuation/test_sinapi.py` e `test_sicro.py` (novos)

Espelho da ESTRUTURA de `test_emop.py` (20 testes, linhas 46-341), por fonte: feliz
casando o gabarito; reimportação → mesmo id; aba/campo ausente; código fora do
padrão; preço adulterado não numérico; descrição vazia; planilha vazia; layout com
regex que não compila / casa vazio; `Decimal` nunca passa por float; CLI publica só
catálogo+relatório; CLI recusa arquivo quebrado e layout inválido sem publicar.

## Out of scope

- Enum/labels/schemas (T1 já fez); e2e (T3); rota/tela; demos.
- Formato real dos arquivos oficiais (fecha como dado do layout quando existirem).
- Tocar `emop.py`/`emop_fixture.py`/`test_emop.py` — se precisar generalizar algo
  deles, PARE e reporte em vez de refatorar área alheia.

## Acceptance criteria

1. `make check` e `make test` verdes.
2. Cada recusa nomeada acima coberta por teste com código estável por fonte.
3. Nenhum float no caminho do preço (teste prova).
4. CLI: recusa não publica nada (teste prova, nas duas fontes).

## Validation

```bash
make check
make test
uv run pytest tests/valuation/test_sinapi.py tests/valuation/test_sicro.py -x -q
```

## Required capabilities

READ, WRITE, VALIDATE. Sem COMMIT: deixe o diff na árvore.

## Report

`BUILD REPORT` completo em
docs/features/F-026-importadores-sinapi-sicro/tasks/T2-build-report.md.
