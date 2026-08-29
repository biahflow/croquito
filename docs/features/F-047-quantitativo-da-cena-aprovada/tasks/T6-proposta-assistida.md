# F-047 · T6 — A proposta assistida de agrupamento

Feature: [F-047](../feature.md) · Plano: [plan.md](../plan.md) · Estado: **Pendente**

## Objetivo

Baratear o ato humano de identidade: o sistema **propõe** que certos traços são um elemento; a
proposta nasce `unresolved` e não vira identidade sem a decisão registrada.

> Entra nesta feature por decisão humana de 2026-08-28, e não numa fatia seguinte.

## Escopo

- O produtor das propostas (camada, rótulo próximo, mesma `provenance`)
- A rota que as expõe na revisão
- `tests/` correspondentes

## Fora de escopo

- Proposta que vira identidade sozinha — recusado pelo ADR-0058, decisão 2
- Modelo pago: a proposta é determinística, sem chamada de provider

## Critérios de aceite

1. A proposta nasce `unresolved` e é rotulada como proposta na resposta — nunca como identidade.
2. Proposta **não** alimenta quantidade nenhuma enquanto não for confirmada. Teste que prova que
   um agrupamento proposto e não confirmado não produz `TakeoffItem` com `source = scene_graph`.
3. Pelo menos um caso de teste com proposta **errada de propósito** (dois elementos distintos
   agrupados por camada), provando que o humano pode recusá-la e que a recusa fica registrada.
4. Confirmar uma proposta é o mesmo ato da T2, com o mesmo registro de autor e instante.
5. Sem propostas, a revisão responde como hoje.

## Validação

`uv run pytest tests` verde; `make check` verde.
