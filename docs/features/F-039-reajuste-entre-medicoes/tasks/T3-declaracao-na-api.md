# F-039 · T3 — Declarar o reajuste na abertura da rodada

Feature: [F-039](../feature.md) · Plano: [plan.md](../plan.md) · Estado: **Entregue**

## Objetivo

`POST /v1/valuation-rounds` aceita a declaração do reajuste e a grava com o consolidado, que
continua imutável na rodada.

## Escopo

- `services/api/src/croquito_api/main.py` (contrato de entrada, aplicação ao consolidado,
  resposta), `tests/api/`, snapshot de OpenAPI, `docs/architecture/API_CONTRACT.md`.

## Fora de escopo

- Declarar reajuste em rodada **já aberta**: o consolidado é imutável nela (ADR-0048, D7).
- Rodada sem orçamento assinado de origem, que não tem consolidado a reajustar.

## Critérios de aceite

1. Reajuste por índice grava a declaração e o consolidado responde com o vigente.
2. Reajuste por versão de tabela resolve o preço por código a partir do catálogo citado e
   recusa quando falta código contratado.
3. Declaração inconferível recusa com código estável, na fronteira.
4. Abrir sem declarar não muda nada — nem resposta, nem consolidado.

## Validação

`uv run pytest tests/api` verde e snapshot regenerado.
