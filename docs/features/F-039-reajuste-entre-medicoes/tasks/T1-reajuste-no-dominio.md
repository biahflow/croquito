# F-039 · T1 — O reajuste no domínio

Feature: [F-039](../feature.md) · Plano: [plan.md](../plan.md) · Estado: **Entregue**

## Objetivo

Representar a declaração de reajuste e o preço vigente no consolidado, sem afrouxar invariante
nenhum e sem mover número já pago.

## Escopo

- `packages/valuation/src/croquito_valuation/contract.py`
- `tests/valuation/test_price_adjustment.py`

## Fora de escopo

- Rota, planilha e tela. Nenhuma escrita nova de dado nesta tarefa.
- Escopo por item (fórmula paramétrica), declarado como extensão no ADR.

## Critérios de aceite

1. `PriceAdjustment` discriminado por `kind`, com autor, instante, período e a citação que
   torna a declaração conferível.
2. `current_unit_price` **derivado**, com fatores compondo e truncamento uma vez, no fim.
3. Versão nova de tabela que não precifica todo código contratado recusa.
4. Consolidado `2.0.0` continua validando, sem reajuste.
5. Sem reajuste declarado, vigente é contratado — bit a bit.

## Validação

`uv run pytest tests/valuation` verde; `uv run mypy packages` limpo.

## Resultado

Entregue, com um **desvio material** que virou emenda do ADR: `ContractLine.validate_periods`
exigia que todo período batesse com o preço único da linha, então o modelo não conseguia
representar um contrato reajustado. `PeriodProgress` ganhou `unit_price` opcional — ausente
significa "medido pelo contratado". Ver a emenda da decisão 6 do ADR-0055.
