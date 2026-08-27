# F-040 · T3 — Declarar a RE-RA e abrir a medição seguinte na API

Feature: [F-040](../feature.md) · Plano: [plan.md](../plan.md) · Estado: **Entregue**

## Objetivo

Dar caminho de entrada à RE-RA e à rodada seguinte na `/v1`, espelhando o campo
`price_adjustment` da abertura da rodada (F-039), aplicado ao consolidado **antes** de ele ser
gravado — é a imutabilidade na rodada que faz a declaração valer para o período inteiro.

## Escopo

- `services/api/src/croquito_api/main.py` — `POST /v1/valuation-rounds` (campo opcional
  `amendment`) e a abertura da rodada `n+1`.
- `services/api/src/croquito_api/valuation_rounds.py`.
- `tests/api/` — declaração na abertura e a rodada seguinte ponta a ponta.

## Fora de escopo

- Tela (T5). Máquina de estados do pedido de RE-RA: fora de escopo (ADR-0056, decisão 2).

## Critérios de aceite

1. `POST /v1/valuation-rounds` aceita `amendment` opcional (autor, instante com fuso, período
   de referência, linhas com delta e item novo), aplicado ao consolidado antes da gravação;
   `tenant_id` vem do JWT, nunca do body.
2. Declaração inválida recusa com `application/problem+json` e código estável; resposta bruta
   de nada vaza ao cliente.
3. Abrir a rodada `n+1` produz o consolidado da continuidade (T2); medir acima do vigente
   **novo** recusa com `BALANCE_EXCEEDED`, abaixo exporta (feature.md, AC 8).
4. Mutação aceita `Idempotency-Key`; a rodada permanece imutável depois de gravada (AC 6).
5. Nenhum digest assinado se move: o `Estimate` assinado não ganha campo (AC 9).

## Validação

`uv run pytest tests/api tests/e2e` verde; `uv run mypy services` limpo; drift de contratos
zerado (`make contracts` + `make check`).
