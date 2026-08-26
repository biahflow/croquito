# F-038 T6 — Os builders passam a iterar serviços, não itens

Issue: [#78](https://github.com/biahflow/croquito/issues/78) · Estado: **entregue**

## Goal

`build_worksite_bulletin` (`calc.py`) e `build_worksite_estimate` (`estimate.py`) deixavam de
suportar item com mais de um código (portão `*_PACKAGE_NOT_SUPPORTED`). Com a matriz da T4
pronta, eles passam a consumir `resolve_calc_matrix` e a produzir **uma linha por serviço**:
quantidade = soma das parcelas dos elementos, `CalcSheet` com um bloco por parcela — que é
literalmente o `SUM` do arquivo.

## Leia antes de editar

- [ADR-0053](../../../adr/0053-cardinalidade-n-n-elemento-servico.md), decisões 1 e 4.
- T4 (#76): `resolve_calc_matrix` / `ResolvedMatrix` — a costura que esta tarefa consome.
- T5 (#77): `(item_id, code)`, `confirmed_codes_by_item`, fechamento de pacote.

## Scope

- Ambos os builders ganham `calc_matrix: CalcMatrix | None = None` e, no fim, `service_numbers`
  em `CalcBuildResult`/`EstimateBuildResult` (código → linha, no regime da matriz).
- O portão `*_PACKAGE_NOT_SUPPORTED` vira **condicional**: só recusa pacote de vários códigos
  quando **não** há matriz (o regime legado não sabe fundir). Com matriz, é ela quem resolve.
- `calc.py` unifica os dois regimes via `resolve_calc_matrix` (catálogo único); a conferência
  `CALC_PLAN_QUANTITY_MISMATCH` do plano continua no builder, só no regime legado.
- `estimate.py` mantém o laço legado **verbatim** (byte-idêntico, com catálogo citado por
  item) e ganha um ramo de matriz à parte, porque a fonte de preço é por linha: nasce
  `_priced_catalog` (as três recusas de fonte) e `_cited_catalog_by_code`, que recusa com
  `ESTIMATE_PACKAGE_CATALOG_CONFLICT` quando o mesmo código é confirmado citando fontes
  diferentes.

## Out of scope

- Teto e nota de `PARTIAL` (`≤` quantidade do item): T3 direcionou a "builder (T4/T6)", mas
  o aceite do #78 não a exige e a dívida continua registrada — o resolver materializa a
  parcela `PARTIAL` sem conferir o teto. Fica para tarefa própria.
- Ligar a matriz ao CLI/rotas/migração (T8, #80) e à tela (T9, #81). Aqui os builders
  aceitam `calc_matrix`, mas o `valuation-demo`/`estimate-demo` seguem no regime legado.

## Acceptance

- Fusão N→1: três elementos alimentam o saibro e a linha fecha em **478,74** somando as
  parcelas (`test_matrix_regime_fuses_many_elements_into_one_service_line`).
- Fan-out 1→N: `PISO EM CONCRETO` dispara a pilha e gera **6 linhas**
  (`test_matrix_regime_expands_one_element_into_many_service_lines`).
- `valuation-demo` e `estimate-demo` **inalterados** (regime legado byte-idêntico — goldens de
  planilha e âncoras de `content_digest` imóveis).
- Pacote de vários códigos **sem** matriz continua recusando `*_PACKAGE_NOT_SUPPORTED`.
- `make check` e `make test` verdes.

## Validation

```bash
uv run pytest tests/valuation tests/e2e/test_valuation_full_chain.py
make check && make test
```

## Report

**Assimetria deliberada entre os dois builders.** `calc.py` (catálogo único) unifica os dois
regimes via `resolve_calc_matrix`; `estimate.py` (cascata, catálogo citado por item) mantém o
laço legado verbatim e ramifica só o regime da matriz. Unificar o estimate arriscaria a ordem
de erros e a fusão indevida de catálogos por código — o byte-idêntico venceu a simetria.

**`ESTIMATE_PACKAGE_CATALOG_CONFLICT` é novo.** Um serviço fundido de vários elementos precisa
de UMA fonte de preço; se dois elementos confirmam o mesmo código citando catálogos
diferentes, recusar é mais honesto do que deixar a fonte à sorte da ordem.

**Números reais.** O aceite cita `478,74` e as seis linhas do `PISO EM CONCRETO`; a base do
Campo do Toca é dado de cliente e não entra no Git, então os testes reproduzem a **estrutura**
(fusão e fan-out) com fixtures sintéticas — o `478,74` sai de `418,12 + 59,34 + 1,28`.
