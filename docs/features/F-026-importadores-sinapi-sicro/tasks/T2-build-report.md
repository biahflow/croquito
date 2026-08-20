# BUILD REPORT — F-026/T2 — Importadores SINAPI e SICRO

```text
Status: BUILD_COMPLETE
Files changed: ver lista abaixo
Validation executed: make check; make test; uv run pytest tests/valuation/test_sinapi.py tests/valuation/test_sicro.py -x -q
Validation skipped: none
Unavailable capabilities: none
Assumptions: ver seção "Assunções conscientes"
Remaining risks: ver seção "Riscos remanescentes"
Human decisions required: none
```

## Arquivos alterados/criados

Novos:

- `packages/valuation/src/croquito_valuation/sinapi.py` — leitor `.xlsx` mínimo do
  catálogo SINAPI (`SinapiCatalogLayout`, `read_sinapi_catalog[_with_report]`),
  espelhando `emop.py` (fail-closed, `origin=PriceOrigin.SINAPI`, `Decimal` nunca via
  `float`).
- `packages/valuation/src/croquito_valuation/sicro.py` — idem para SICRO
  (`SicroCatalogLayout`, `read_sicro_catalog[_with_report]`, `origin=PriceOrigin.SICRO`);
  deliberadamente NÃO compartilha implementação com `sinapi.py` (ADR-0039 rejeita
  importador único multi-formato).
- `services/worker/src/croquito_worker/valuation/sinapi_fixture.py` — gerador
  determinístico do `.xlsx` sintético SINAPI (openpyxl), layout casado, gabarito
  (`expected_sinapi_entries`) e parametrização de recusa (`price_as_float`), tudo num
  arquivo só (o Task Contract pediu essa forma mais simples do que o split
  EMOP/`tests/valuation/emop_fixture.py`, já que o layout SINAPI não tem o par
  leitor-DBF/DBF-de-teste que motivou aquele split).
- `services/worker/src/croquito_worker/valuation/sicro_fixture.py` — idem para SICRO.
- `tests/valuation/test_sinapi.py` — 18 testes (ver seção "Testes novos").
- `tests/valuation/test_sicro.py` — 18 testes espelho.

Modificados:

- `services/worker/src/croquito_worker/valuation/cli.py` — imports de `sinapi.py`/
  `sicro.py`; constantes `SINAPI_IMPORT_REPORT_FILENAME`/`SICRO_IMPORT_REPORT_FILENAME`;
  dataclasses `ValuationSinapiImportResult`/`ValuationSicroImportResult`; funções
  `run_import_sinapi`/`run_import_sicro` (espelho de `run_import_emop`); comandos
  `_command_import_sinapi`/`_command_import_sicro`; subparsers `import-sinapi`/
  `import-sicro` (`--input`/`--layout`/`--output`, `--layout` obrigatório); dispatch em
  `main()`.

Não tocados (INTOCÁVEIS por contrato, confirmado no diff final):
`packages/valuation/src/croquito_valuation/emop.py`,
`services/worker/src/croquito_worker/valuation/emop_fixture.py`,
`tests/valuation/test_emop.py`, `tests/valuation/emop_fixture.py`.

Arquivos de T1 na árvore (não meus, não tocados; confirmados pelo `git status` inicial e
final — mesmo conjunto): `apps/web/src/orcamento/labels.ts`,
`apps/web/src/orcamento/labels.test.ts`, `packages/contracts/schemas/*.json`,
`packages/contracts/src/*.generated.ts`, `packages/valuation/src/croquito_valuation/
assignment.py`, `packages/valuation/src/croquito_valuation/estimate.py`,
`packages/valuation/src/croquito_valuation/models.py` (já trazia `PriceOrigin.SINAPI`/
`SICRO` do T1 — usados aqui, não alterados), `tests/valuation/golden/
estimate-demo.canonical.json`, `tests/valuation/test_assignment.py`,
`tests/valuation/test_calc.py`, `tests/valuation/test_writer_roundtrip.py`,
`docs/features/F-026-importadores-sinapi-sicro/tasks/T1-build-report.md`.

## Testes novos

Por fonte (`test_sinapi.py`/`test_sicro.py`, 18 testes cada, espelhando a estrutura de
`test_emop.py`):

1. Caminho feliz: entradas batem o gabarito, `origin`, `reference_month`, digest.
2. Linhas em branco são puladas, contadas em `notes.blank_row_count`/`blank_rows` e
   nunca importadas (equivalente ao registro deletado do EMOP; a fixture grava a linha
   em branco no MEIO da faixa escrita — como última linha ela nunca apareceria na
   extensão usada da planilha, prova feita manualmente com `openpyxl` antes de escrever
   o código).
3. Reimportar os mesmos bytes devolve o mesmo `catalog.id`.
4. Arquivo `.xlsx` estruturalmente quebrado (bytes não são um zip válido) recusa
   `*_XLSX_UNSUPPORTED`.
5. Aba declarada no layout ausente do arquivo recusa `*_SHEET_MISSING`.
6. Coluna declarada no layout fora da extensão real da tabela recusa `*_FIELD_MISSING`
   com a letra da coluna em `details["columns"]`.
7. Código fora do `code_pattern` do layout recusa `*_ROW_UNPARSEABLE` com a linha certa.
8. Preço não numérico (texto adulterado) recusa `*_ROW_UNPARSEABLE`.
9. Preço negativo recusa `*_ROW_UNPARSEABLE`.
10. Célula de preço gravada como número binário (`float`) do openpyxl recusa a linha em
    vez de converter — a prova negativa de "`Decimal` nunca passa por `float`"
    (`*_ROW_UNPARSEABLE`).
11. Descrição vazia recusa `*_ROW_UNPARSEABLE`.
12. Tabela com toda linha em branco recusa `*_EMPTY`.
13-14. Layout com `code_pattern` que não compila / que casa a string vazia recusa
    `*_LAYOUT_CODE_PATTERN_INVALID` (via `ValidationError`/`valuation_error_codes`).
15. CLI `import-sinapi`/`import-sicro` feliz publica só `catalog.json` +
    `sinapi-import-report.json`/`sicro-import-report.json`, com `consolidado:
    "not_imported"` e nota citando `BULLETIN_PRICE_ORIGIN_FORBIDDEN`.
16. CLI recusa arquivo `.xlsx` quebrado sem publicar nada (`exit_code == 2`, diretório
    vazio ou inexistente).
17. CLI recusa layout inválido sem publicar nada.
18. Prova positiva "`Decimal` nunca passa por `float`": todo `unit_price` do caminho
    feliz é `Decimal` e bate o gabarito.

Total: 36 testes novos, todos verdes na primeira execução completa.

## Saída resumida dos portões

- `make check` — ruff check (limpo), ruff format (limpo após uma rodada de
  `ruff format` nos 4 arquivos novos/editados que ainda não estavam formatados), mypy
  strict (`Success: no issues found in 200 source files`), `check_docs.py` (links e
  lifecycle ok), `schema_export --check-dir` (sem drift), `contracts:check` (sem
  drift), `web:check` (`tsc -b && vite build` ok), `infra-check` (`terraform fmt
  -check`) — todos verdes.
- `make test` — `1735 passed, 13 skipped` (pytest, inclui os 36 testes novos) +
  `697 passed` (vitest, `apps/web`) — todos verdes.
- `uv run pytest tests/valuation/test_sinapi.py tests/valuation/test_sicro.py -x -q` —
  36 passed.

## Baseline

Confirmado antes de editar (via leitura do estado da árvore herdado de T1, já
documentado no relatório de T1) e reconfirmado ao final por `make check`/`make test`
completos: ambos verdes, nenhuma falha pré-existente na área tocada.

## Desvios conscientes do spec

1. **Família/subgrupo do catálogo SINAPI/SICRO não vêm do layout.** O Task Contract
   lista o layout de cada fonte como `source_label, reference_month, sheet_name,
   header_row, code_column, description_column, unit_column, price_column,
   code_pattern` — sem coluna de família/subgrupo (diferente do EMOP, cujo `.DBF`
   publica essa hierarquia em campos próprios). Como
   `PriceCatalogEntry.family_code/family_name/subgroup_code/subgroup_name` são
   obrigatórios no modelo canônico (`models.py`, sem default), decidi preencher os
   quatro com um valor único e determinístico por catálogo: `family_code =
   subgroup_code = "SINAPI"`/`"SICRO"` (constante `SINAPI_FAMILY_CODE`/
   `SICRO_FAMILY_CODE`, exportada do próprio módulo) e `family_name = subgroup_name =
   layout.source_label`. Documentei a decisão no docstring de cada módulo (seção
   "Família e subgrupo"). Nada na cadeia da medição ou na cascata do orçamento-base
   (fase futura, ainda não implementada) lê família/subgrupo de um catálogo
   `sinapi`/`sicro`, então a simplificação não perde informação que algum consumidor
   atual precise — mas é uma escolha de design que o próximo trabalho sobre a cascata
   (quando ela existir) deve revisitar se precisar de hierarquia real por fonte.
2. **"Campo declarado ausente" implementado como coluna fora da extensão real da
   planilha (`column_index_from_string(letter) > worksheet.max_column`), não como
   validação de texto de cabeçalho.** O EMOP detecta campo ausente pelo NOME do campo
   não existir entre os descritores do `.DBF`; como o layout SINAPI/SICRO usa colunas
   por LETRA (não por nome), não há um "nome" para comparar. Escolhi o check
   estrutural mais direto e determinístico (a coluna letra aponta para fora da faixa
   de colunas que a planilha realmente usa) em vez de exigir um texto de cabeçalho
   declarado no layout (que o contrato não pediu). Comportamento verificado
   manualmente com `openpyxl` antes de codificar (ver testes 6 de cada arquivo).
3. **Checagem de duplicidade de coluna considerada e descartada.** Cheguei a cogitar um
   `model_validator` extra tipo `SINAPI_LAYOUT_DUPLICATE_COLUMN` (mirror de
   `SheetColumns.validate_distinct_letters` em `template.py`), mas o contrato só pediu
   validação de `code_pattern` no layout — removi para não expandir escopo além do
   pedido.
4. **Contagem de testes.** O contrato menciona "20 testes" como referência ao tamanho
   de `test_emop.py`; a contagem real de `test_emop.py` é 17. Escrevi 18 por fonte
   (17 espelhando EMOP um a um + 1 teste extra de "linhas em branco" simétrico ao
   "registro deletado" do EMOP, que o EMOP cobre dentro do teste feliz mas aqui ganhou
   teste próprio por clareza). Nenhuma recusa nomeada no contrato ficou sem teste
   dedicado.

## Oportunidades vistas e NÃO implementadas (fora de escopo)

- Layout com opção de hierarquia família/subgrupo em colunas próprias (como
  `CatalogLayout.hierarchy_columns` do MAPÃO) — o contrato não pediu, e adicionaria
  campos ao layout que o Task Contract fixou explicitamente.
- Wiring de `sinapi_fixture.py`/`sicro_fixture.py` em `estimate-demo` ou em qualquer
  outro comando de demo — fora de escopo explícito ("Out of scope: ... demos").
- Rota HTTP/tela web para os dois importadores novos — fora de escopo explícito
  ("rota/tela").
- e2e da cascata de origens (T3) — fora de escopo desta task.
