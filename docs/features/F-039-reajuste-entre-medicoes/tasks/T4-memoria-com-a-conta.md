# F-039 · T4 — A memória e o boletim mostram a conta

Feature: [F-039](../feature.md) · Plano: [plan.md](../plan.md) · Estado: **Entregue**

## Objetivo

Preço contratado, fator e preço vigente visíveis onde a prefeitura audita.

## Escopo

- A leitura da rodada (o que a tela consome) e a memória de cálculo.

## Fora de escopo

- A diagramação da planilha exportada, que segue o modelo da prefeitura e não foi decidida
  no pacote de design.

## Critérios de aceite

1. A resposta da rodada declara os reajustes e o preço vigente por linha.
2. Sem reajuste, nenhum campo novo aparece com valor — ausência é ausência.

## Validação

`uv run pytest tests/api` verde.
