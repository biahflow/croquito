# F-040 · T2 — A medição seguinte: consolidado `n+1` a partir da rodada anterior

Feature: [F-040](../feature.md) · Plano: [plan.md](../plan.md) · Estado: **Entregue**

## Objetivo

Construir o consolidado da rodada `n+1` a partir do consolidado da rodada `n` mais os
períodos aprovados nela — exercendo, enfim, a decisão 8 do
[ADR-0048](../../../adr/0048-consolidado-contratual-do-orcamento-assinado.md), que estava escrita
e nunca fora rodada.

## Escopo

- `packages/valuation/src/croquito_valuation/contract_from_estimate.py` (ou builder próprio da
  continuidade) — a função que hoje serve só à primeira medição.
- `tests/valuation/test_contract_from_estimate.py` + novo oráculo da rodada seguinte.

## Fora de escopo

- A rota que dispara a abertura (T3).
- Reconstruir do orçamento assinado: rejeitado (ADR-0056, decisão 4) — cita a rodada anterior.

## Critérios de aceite

1. O consolidado de `n+1` nasce da rodada anterior: `period_numbers` recebe os períodos já
   lançados, cada `PeriodProgress` com o `unit_price` daquele período (quando reajustado), o
   acumulado somado e o saldo `vigente − acumulado` por código (feature.md, AC 7).
2. As RE-RA e os reajustes declarados na rodada anterior são **preservados**, não reaplicados
   a partir do orçamento (decisão 4).
3. Item novo criado por RE-RA na rodada `n` aparece como linha do consolidado `n+1`.
4. A rodada seguinte exige a anterior **aprovada** (decisão 5) — a validação de pré-condição
   mora aqui ou em T3, e é levada ao gate se a política precisar mudar.

## Validação

`uv run pytest tests/valuation` verde; `uv run mypy packages` limpo.
