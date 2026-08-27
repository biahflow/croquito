# F-039 · T5 — A declaração e a conta na tela

Feature: [F-039](../feature.md) · Plano: [plan.md](../plan.md) · Estado: **Entregue**

## Objetivo

A tela da medição corresponde aos sete estados aprovados: declarar por índice ou por versão de
tabela, ver a prévia da conta, ler a memória com contratado/fator/vigente e as recusas.

## Escopo

- `apps/web/src/medicao/` e a folha de estilo.

## Fora de escopo

- A tabela de índices importada (reservada no pacote de design).

## Critérios de aceite

1. Os três caminhos da abertura aparecem como escolha única.
2. Fator, índice e período são exigidos juntos, antes da rede.
3. A linha reajustada tem selo escrito, não só cor.

## Validação

`npm --workspace @croquito/web run test` e `run build` verdes.
