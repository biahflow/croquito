# F-039 · T2 — O portão de exportação sobre o preço vigente

Feature: [F-039](../feature.md) · Plano: [plan.md](../plan.md) · Estado: **Entregue**

## Objetivo

`LINE_PRICE_NOT_IN_CONTRACT` passa a comparar o boletim com o preço que o contrato paga hoje.

## Escopo

- `packages/valuation/src/croquito_valuation/models.py` (`Valuation.export_errors`)

## Fora de escopo

- Qualquer outro guardrail do portão; nenhum deles muda de significado.

## Critérios de aceite

1. Sem reajuste declarado, o comportamento é idêntico ao anterior à feature.
2. Com reajuste, boletim pelo preço antigo é recusado; pelo vigente, passa.

## Validação

`uv run pytest tests/valuation tests/api` verde.

## Resultado

Entregue. Uma linha de comparação e o comentário que explica por que ela mudou.
