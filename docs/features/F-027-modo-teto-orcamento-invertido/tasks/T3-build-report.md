# T3 — BUILD REPORT

## Identity

```text
feature_id: F-027
task_id: T3
harness: Claude Code (subagent implementador)
```

## Status

BUILD_COMPLETE

## Files changed

- `tests/e2e/test_estimate_rounds_v1.py` — único arquivo tocado (escopo do Task
  Contract). Diff aditivo: 260 linhas inseridas, 0 removidas.
  - No teste EXISTENTE (`test_estimate_round_full_chain_through_v1_api`): duas
    asserções novas de retrocompatibilidade — após `built_body["workbook_present"]`
    (bloco derivado ausente em `built_body`) e após o `GET .../estimate` final
    (bloco derivado ausente em `read`). Nenhuma linha pré-existente foi alterada ou
    removida.
  - Teste novo `test_estimate_round_target_over_and_exact_limit_through_v1_api`:
    cadeia completa e2e com teto declarado na criação, cobrindo os critérios 2–4 da
    feature pela API `/v1` real.

## New tests and what they cover

`test_estimate_round_target_over_and_exact_limit_through_v1_api`
(`tests/e2e/test_estimate_rounds_v1.py`):

1. `POST /v1/estimate-rounds` com `target_amount="70000.00"` e `target_label`
   declarados na criação (critério 2 da feature).
2. Bloco derivado sobrevive intacto à extração da prancha (só `target`, sem
   `consumed`/`remaining`/`over` — orçamento ainda não montado).
3. `POST .../estimate` monta o orçamento real (cascata de 3 fontes + takeoff +
   code-assignments pela cadeia completa); teto (`70000.00`) menor que o total
   conhecido do cenário (`71516.83` com BDI 25%) → `over: true`,
   `consumed == total_amount` (string exata), `remaining == "-1516.83"` (critério 3).
   Mesma verificação repetida no `GET .../estimate`.
4. `POST .../target` editando o teto para EXATAMENTE o `total_amount` publicado →
   `over: false`, `remaining == "0.00"` — limite exato não é estouro (critério 4).
   Também prova que editar sem repetir `target_label` limpa o rótulo (a rota não faz
   merge parcial — comportamento já coberto por T1 em
   `test_declarar_teto_depois_da_criacao`, aqui reconfirmado pela cadeia real).
5. `base_version` velho na edição do teto → `409 REVISION_CONFLICT`, sem gravar nada
   (`GET` posterior confirma versão e teto inalterados).
6. `target_amount="0.00"` → `422 ESTIMATE_TARGET_INVALID`, sem avançar versão nem
   tocar o teto gravado.

Asserções em `test_estimate_round_full_chain_through_v1_api` (retrocompatibilidade,
critério 5 do escopo): rodada SEM teto — bloco derivado (`target`, `consumed`,
`remaining`, `over`) ausente tanto na resposta de `POST .../estimate` quanto no
`GET .../estimate` final.

## Validation executed

Todos em foreground, na árvore `/Users/danielcampos/workspace/daniel/croquito-specs`:

- `uv run pytest tests/e2e/test_estimate_rounds_v1.py -q` → `2 passed` (isolado, antes
  e depois do `ruff format`).
- `make check` → `ruff check` OK, `ruff format --check` OK (após autoformat de uma
  linha longa introduzida por mim), `mypy strict` OK (195 arquivos), `check_docs.py`
  OK, `schema_export --check` OK, `contracts:check` OK, `web:check` (tsc + vite
  build) OK, `terraform fmt -check` OK.
- `make test` → `uv run pytest`: `1705 passed, 13 skipped` (147.32s); `npm run
  web:test` (vitest): `693 passed` em 39 arquivos, incluindo os testes de
  `apps/web/src/orcamento/` da T2 paralela — nenhum sinal de interferência.
- `uv run pytest tests/e2e -q` (comando explícito do contrato) → `17 passed`.

## Validation skipped

Nenhuma.

## Unavailable capabilities

Nenhuma.

## Assumptions

- O contrato menciona "o cenário determinístico existente produz `total_amount ==
  '1125.00'` com BDI 25.00" como contexto do que T1 entregou. Verifiquei que esse
  valor pertence à fixture MENOR e mais simples usada pelos testes de rota de T1 em
  `tests/api/test_estimate_round_routes.py` (`_round_ready_for_estimate`: 2 fontes, 2
  itens). O cenário e2e deste arquivo (`legend_fixture_adapter` + prancha sintética +
  cascata de 3 fontes + `build_demo_estimate_assignments`) é um cenário DIFERENTE e
  mais rico, já usado pelo teste existente do arquivo. Medi o total real desse cenário
  rodando a cadeia (`total_amount == "71516.83"` com BDI 25%, determinístico —
  confirmado por reexecução) e usei esse valor exato nas asserções, em vez do
  `1125.00` citado no contrato, que não se aplica a este arquivo. Documentado no
  docstring do teste novo.
- Assumi que "critério 2 da feature" (teto declarado na criação) devia ser exercido
  pela ROTA `POST /v1/estimate-rounds` com `target_amount`/`target_label` no corpo
  (conforme o diff de T1 em `services/api/src/croquito_api/main.py`,
  `CreateEstimateRoundRequest`), e não por uma chamada separada a `.../target` logo
  após a criação.

## Remaining risks

- O teste novo duplica boa parte do setup do teste existente (prancha sintética,
  cascata de 3 fontes, worker local) em vez de extrair um helper compartilhado — feito
  deliberadamente para manter o diff do teste EXISTENTE mínimo (só a asserção de
  ausência, como o critério de aceite 2 exige) e não introduzir uma refatoração fora
  do escopo desta task.
- O valor `71516.83` é sensível a qualquer mudança futura nas fixtures sintéticas de
  valuation (`estimate_fixture.py`, `legend_fixtures.py`, catálogos EMOP/composição).
  Se essas fixtures mudarem, este teste vai quebrar por um valor hardcoded — o mesmo
  padrão de risco que já existe em `test_o_caminho_feliz_publica_orcamento_e_planilha_
  auditada` (T1, hardcoda `"1125.00"`) e nos demais testes deste arquivo que citam
  `LUMINARIA DUPLA SINTETICA`/`SYNTHETIC_LEGEND_ROWS`. Não é um risco introduzido por
  esta task, é o padrão já estabelecido no arquivo.

## Human decisions required

Nenhuma decisão humana nova é necessária para esta task especificamente. As pendências
já registradas por T1 (aceite de ADR-0040, se aplicável) permanecem fora do escopo
deste Builder.
