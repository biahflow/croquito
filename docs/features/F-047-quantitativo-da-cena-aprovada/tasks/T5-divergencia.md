# F-047 · T5 — Divergência: tolerância nomeada, issue e bloqueio

Feature: [F-047](../feature.md) · Plano: [plan.md](../plan.md) · Estado: **Pendente**

## Objetivo

Quando o mesmo elemento tem quantidade da cena e quantidade lida na legenda, mostrar as duas e
recusar fechar — nunca escolher sozinho.

## Escopo

- `packages/valuation/src/croquito_valuation/` (a divergência e o bloqueio do item)
- `services/api/src/croquito_api/main.py` (a resolução como decisão humana registrada)
- `tests/valuation/`, `tests/api/`

## Fora de escopo

- Qualquer forma de sobrescrita automática
- Digitar uma terceira quantidade na resolução: seria a redigitação que a feature elimina

## Critérios de aceite

1. A tolerância é **constante nomeada**: `maior(1% do valor da legenda, 0,01 na unidade do
   item)`. Testada nas bordas — exatamente 1%, exatamente 0,01 e o caso em que 0,01 é maior que
   1%.
2. Diferença **igual** à tolerância **não** abre issue (`>`, nunca `>=`) — confirmado no aceite
   humano de 2026-08-28.
3. Fora da tolerância, abre issue com os dois números, as duas origens e a diferença; nenhum
   apaga o outro, e os dois continuam gravados.
4. O item **não fecha** enquanto a issue estiver aberta.
5. Resolver é decisão humana registrada, com autor e instante; o número preterido continua
   gravado e visível.
6. Elemento com cena `approximate` **não** gera divergência (não alimenta, então não compara).
7. Sem quantidade da cena, nada muda: o item da legenda segue como hoje.

## Validação

`uv run pytest tests/valuation tests/api` verde; `make check` verde.
