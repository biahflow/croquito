# F-038 T7 — A memória comporta quatro operandos

Issue: [#79](https://github.com/biahflow/croquito/issues/79) · Estado: **entregue**

## Goal

`default_template()` (`template.py`) definia `operand_columns` com **três** colunas
(`["C", "D", "E"]`) e o escritor recusava bloco mais largo com `MEMORY_BLOCK_TOO_WIDE`
(`workbook_writer.py:437`). A memória real do Campo do Toca tem blocos de **quatro**
operandos — a sapata do alambrado é `0,6 x 0,6 x 0,6 x 58 postes` = 12,53 m³ e o transporte
é `quantidade x densidade x espessura x distância`. Nenhum cabia.

**Única tarefa da F-038 que muda o layout impresso da planilha** — por isso vai isolada.

## Leia antes de editar

- `packages/valuation/src/croquito_valuation/workbook_writer.py`, `_plan_block`: o produto é
  uma faixa contígua `=ROUND(PRODUCT(primeiro:último),2)`, então as colunas de operando
  precisam ser **contíguas** e nunca abarcar a coluna de subtotal.
- `MemoryLayout` (`template.py`): `subtotal_column` deriva de `columns.quantity.letter`; o
  validador `TEMPLATE_COLUMN_CONFLICT` proíbe operando na coluna de subtotal.

## Scope

- `operand_columns` de 3 para **6** (`C..H`): quatro fatores + dedução + folga.
- Para caber seis operandos à esquerda do subtotal, a QUANT. e o TOTAL da aba MEMÓRIA
  recuam de `F`/`G` para **`I`/`J`**. A aba BOLETIM (`columns`) não muda — só a memória.

## Out of scope

- Qualquer outra aba (BOLETIM, PLANILHA GERAL, MAPÃO) — o diff do golden prova que ficaram
  intactas.
- Preencher os quatro operandos de verdade a partir da matriz: isso é a cadeia da T4/T6; aqui
  só o layout passa a comportá-los.

## Acceptance criteria

- Bloco de 4 operandos imprime sem `MEMORY_BLOCK_TOO_WIDE`
  (`test_a_block_of_four_operands_fits_and_round_trips`).
- Diff do golden de workbook revisado célula a célula: **só** relocação de coluna
  (QUANT. `F→I`, TOTAL `G→J`, subtotais `F→I`), zero mudança de valor.
- Round-trip do auditor continua fechando (suíte de `test_writer_roundtrip.py` verde).
- `make check` e `make test` verdes.

## Validation

```bash
uv run pytest tests/valuation/test_writer_roundtrip.py tests/valuation/test_estimate_workbook.py
uv run pytest tests/valuation/test_canonical_golden.py
make check && make test
```

## Report

**Placement decidido pela leitura do escritor.** A issue pedia "ampliar de 3 para 6" sem
dizer as letras. Como o subtotal é `PRODUCT(primeiro:último)` e não pode ser abarcado pelos
operandos, e como a leitura da memória é "fatores à esquerda, subtotal à direita", os
operandos ficaram em `C..H` e QUANT./TOTAL recuaram para `I`/`J`. Assim cada subtotal de
bloco continua sob a coluna de QUANT., agora logo à direita da área de operandos.

**Golden byte-a-byte:** os dois goldens de planilha (`valuation-demo.canonical.json` e
`valuation-demo-m4.canonical.json`) mudaram só nas abas MEMÓRIA, e cada linha alterada é uma
relocação `F→I` / `G→J` (inclusive as fórmulas `=TRUNC(I·*E·,2)` e `=SUM(I·:I·)`). Nenhuma
célula de `value` se moveu — a conta é a mesma, só a coluna mudou.
