# F-051 · T6 — A tela da revisão

Feature: [F-051](../feature.md) · Plano: [plan.md](../plan.md) · Estado: **Entregue**  
`feature_id: F-051` · `task_id: T6` · `depends_on: T2, T3, T4`

## Objetivo

A etapa de decisões ganha o que o [DAP aprovado](../mock/README.md) desenha: o chip do hint,
o painel de sugestões, o ato de declarar/renomear/revogar sobre propostas, e as candidatas
por identidade **ao lado** das de proximidade no seletor que já existe. A composição aprovada
é vinculante; o mock não é fonte de código.

## Escopo

- `apps/web/src/CroquiApp.tsx` — etapa "decisions" (`:4668-5223`): chip
  `elemento (hint do modelo)` na leitura (tracejado; ver DAP estado 02) com o ato "corrigir
  hint" pela decisão existente; `<optgroup>` "Pela identidade — ◇ EL-NNN · rótulo" acima do
  grupo de proximidade no `<select>` de associação (`:4982-5020`), com `field-hint` no idioma
  de `:5004-5019`; **sem score e sem distância** (`api.ts:240-241` continua lei).
- Painel de sugestões/declaração da revisão — componente irmão de
  `apps/web/src/elementIdentityPanel.tsx`, reusando o idioma implementado: selo
  `⚙ proposta · unresolved` tracejado, recusa com motivo obrigatório, um único caminho de
  escrita (semear → declarar), carimbo por **papel** (`elementIdentity.ts:397-417`), textos
  distintos para "zero sugestões" × "falha de leitura" (`elementIdentityPanel.tsx:240-250`).
- Rótulos novos em `apps/web/src/labels.ts` (ex. a relação "pela identidade do elemento" em
  `RELATION_LABELS`, `:128-135`) — copy proposta, não aprovada (DAP: copy fica fora).
- `apps/web/src/api.ts` — consumir os tipos que T2/T3/T4 acrescentaram.
- Testes: vitest no molde dos existentes do painel de identidade
  (`npm --workspace @croquito/web run test`).

## Fora de escopo

- Qualquer decisão visual fora do DAP aprovado — divergência é revisão 2 do pacote, não
  improviso.
- O painel de identidade da **cena** (etapa de aprovação) — intocado.
- Mostrar score/distância de candidata — recusado pelo DAP (decisão 4).
- Evidência de navegador — é a T7.

## Critérios de aceite

1. Leitura com hint casando exibe o grupo "Pela identidade" com as propostas do elemento;
   sem casamento, **nenhum grupo vazio** aparece (DAP estados 05/07/09).
2. Declarar/renomear/revogar e recusar sugestão chamam as rotas da T2/T3 com
   `base_version`/`Idempotency-Key`; conflito usa o idioma "Recarregar revisão atual"
   (`CroquiApp.tsx:4518-4526`), sem tela nova.
3. Cor nunca é o único indicador: chip tracejado + texto, grupo rotulado por escrito,
   selo de proposta com palavra — verificável por inspeção dos elementos renderizados em
   teste.
4. Sem declaração e sem hint, a etapa de decisões renderiza como hoje (snapshot/teste de
   regressão).
5. `make check` verde (inclui build do web).

## Validação

```text
baseline: make check && make test verdes na main (registrar o resultado real antes de mudar)
required: npm --workspace @croquito/web run test
required: make check && make test
```

## Riscos conhecidos

- `CroquiApp.tsx` tem 7302 linhas e é vivo — integração ampla, muitos pontos de toque
  (o degrau de delegação certo é o de integração, não o de módulo novo).
- O `<select>` nativo limita a apresentação do grupo — o DAP já decidiu conviver com isso
  (grupo rotulado por escrito); não trocar o controle por listbox custom nesta tarefa.
