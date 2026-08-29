# F-047 · T7 — As duas telas: identidade na revisão, divergência na medição

Feature: [F-047](../feature.md) · Plano: [plan.md](../plan.md) · Estado: **Pendente**

## Objetivo

Levar à tela o que o [pacote de design aprovado](../mock/README.md) revisão 1 desenhou, nos dois
lados do produto — sem redesenhar nada.

## Escopo

- `apps/web/src/` (revisão do croqui) e `apps/web/src/medicao/` (a divergência)
- Testes `vitest` correspondentes

## Fora de escopo

- Copy final; retraçar o elemento sem sair da medição (reservado no pacote)
- Qualquer decisão visual fora do pacote aprovado

## Critérios de aceite

1. Na revisão: a proposta do sistema aparece como proposta, e o ato de declarar identidade
   carimba autor e instante.
2. Elemento `approximate` aparece marcado como **não alimenta a medição**, com o motivo escrito
   na tela, e a legenda seguindo como fonte.
3. Na medição: item com `source = scene_graph` mostra a origem e **não** tem campo digitável.
4. A divergência mostra os dois números, a conta da tolerância e o item bloqueado; a resolução é
   ato humano, e "nenhuma das duas" não é oferecida.
5. O caso sem par diz "nenhum par" — nunca um palpite.
6. Precisão e issue nunca são indicadas só por cor.
7. Sem identidade declarada, as duas telas ficam idênticas às de hoje.

## Validação

`npm --workspace @croquito/web run test` verde; `make check` verde.
