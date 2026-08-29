# F-046 · T5 — A tela da praça: folhas, consolidado e a declaração de identidade

Feature: [F-046](../feature.md) · Plano: [plan.md](../plan.md) · Estado: **Pendente**

## Objetivo

Levar à tela a praça de várias folhas exatamente como o
[pacote de design aprovado](../mock/README.md) revisão 1 desenhou — sem redesenhar nada.

## Escopo

- `apps/web/src/medicao/` (`MedicaoApp.tsx`, `api.ts`, `requests.ts`, estilos)
- Testes `vitest` correspondentes

## Fora de escopo

- Overlay de praça (não existe; um overlay por folha)
- Qualquer decisão visual não coberta pelo pacote aprovado; copy final

## Critérios de aceite

1. As folhas da praça aparecem como **faixa de cartões**, com foco marcado e o estado de cada
   folha dito por texto **e** por forma — nunca só por cor.
2. Etapa `Praça` entre Códigos e Boletim, conforme o pacote.
3. Acrescentar folha é ato em lote com seleção explícita, nada marcado por padrão, e o custo
   aparece no botão.
4. A folha em revisão mostra o overlay **daquela** folha, com o cabeçalho dizendo qual folha de
   quantas.
5. O consolidado mostra o total por código e a memória com as parcelas por folha; item repetido
   aparece contando duas vezes, com o aviso de que são duas leituras.
6. A declaração de identidade é par a par, com nota obrigatória, escolha de "a parcela que
   fica" e **prévia** do efeito no total antes de gravar.
7. As três recusas aparecem na tela com o motivo: folha pendente (nomeando a folha), vínculo na
   mesma folha, vínculo incompleto.
8. Praça de uma folha fica idêntica à tela de hoje: sem faixa, sem etapa `Praça`.

## Validação

`npm --workspace @croquito/web run test` verde; `make check` verde (inclui build do web).
