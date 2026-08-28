# F-047 · T4 — `QuantitySource`: a quantidade atravessa a fronteira

Feature: [F-047](../feature.md) · Plano: [plan.md](../plan.md) · Estado: **Pendente**

## Objetivo

Abrir a porta que o roadmap reservava: ler o `quantitativos.csv` da cena aprovada e alimentar o
item de legenda pela identidade declarada — nunca por proximidade, nunca por número igual.

## Escopo

- `packages/valuation/src/croquito_valuation/` — `QuantitySource` (módulo novo) e `takeoff.py`
- `tests/valuation/`

## Fora de escopo

- Divergência (T5); tela (T7)
- Qualquer heurística de casamento

## Critérios de aceite

1. `QuantitySource` resolve a quantidade **por `element_ref` nos dois lados**. Faltando de um
   dos lados, ele **não resolve** e devolve o motivo: a ausência de par é estado legível.
2. Teste que oferece `418,12` dos dois lados **sem** identidade prova que ele **não** casa.
3. `TakeoffItem` ganha `element_ref` e o terceiro valor `scene_graph` em `source`, de forma
   aditiva, com a versão do contrato de takeoff subindo e aceitando as anteriores.
4. Só `exact` e `derived` alimentam: entidade `approximate` ou `unresolved` **nunca** vira
   quantidade de `TakeoffItem`, mesmo com aceite de aproximação registrado na cena.
5. Item alimentado pela cena carrega a precisão de origem, e a precisão nunca sobe.
6. A quantidade só existe a partir de cena aprovada, pelo portão de exportação que já existe —
   sem caminho novo que o contorne.
7. `TakeoffItem` sem `source = scene_graph` continua exatamente como hoje.

## Validação

`uv run pytest tests/valuation` verde; `make check` verde.
