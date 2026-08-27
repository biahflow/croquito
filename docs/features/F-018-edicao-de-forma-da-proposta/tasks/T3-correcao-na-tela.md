# F-018 · T3 — A correção na tela

Feature: [F-018](../feature.md) · Plano: [plan.md](../plan.md) · Estado: **Entregue**

## Objetivo

Implementar os nove estados aprovados no [Design Approval Package](../mock/README.md): o ato
ao lado de aceitar/rejeitar, arrasto de vértice, inserir/remover, união de fragmentos,
justificativa, gravação, os dois estados de recusa e o não-corrigível.

## Escopo

- `apps/web/src/shapeCorrection.ts` (+ testes), `apps/web/src/CroquiApp.tsx`,
  `apps/web/src/api.ts`, `apps/web/src/styles.css`.

## Fora de escopo

- Limiar de "vértice movido demais": o pacote de design registra explicitamente que não há
  número calibrado para isso.
- Corrigir círculo.

## Critérios de aceite

1. O rascunho vive só na tela e sobrevive à recusa do servidor.
2. A observação de origem continua desenhada, em traço fantasma.
3. Cor não é o único indicador: traço, selo escrito e rótulo dizem o mesmo.
4. "Superada" é derivado da derivação, nunca de um campo do fragmento.
5. Gravar sem origem ou sem justificativa é recusado **antes** da rede.

## Validação

`npm --workspace @croquito/web run test` (1236 testes) e `npm run build` verdes.

## Resultado

Entregue. A verificação renderizada do arrasto depende de uma revisão real com propostas e
está declarada como pendência de aceite em [evidence.md](../evidence.md).
