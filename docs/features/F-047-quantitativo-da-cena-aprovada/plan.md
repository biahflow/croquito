# F-047 — Plano de implementação

Gates cumpridos em 2026-08-28, ambos por ato humano (Daniel Campos):
[ADR-0058](../../adr/0058-quantitativo-derivado-do-scene-graph-e-identidade-de-elemento.md)
**aceito com emenda** (só `exact` e `derived` alimentam a medição) e
[Design Approval Package](mock/README.md) revisão 1 **aprovado**, com duas confirmações no mesmo
ato: a borda exata da tolerância **não** abre issue, e a **proposta assistida de agrupamento
entra nesta feature**.

## A ordem é ditada pela identidade

Nada nesta feature funciona sem `element_ref` nos dois lados. Por isso a identidade vem
primeiro, sozinha, e com o teste que mais importa: **cena sem identidade sai byte a byte igual à
de hoje**. Um croqui existente que mude de digest por causa desta feature é regressão, não
progresso.

O adaptador vem depois da identidade e antes da divergência, porque a divergência só existe
quando há dois números — e o segundo número é o que o adaptador traz.

A proposta assistida entra **depois** do ato manual estar de pé, e não antes: proposta que nasce
antes do ato que ela propõe não tem como ser confirmada, e a tentação de deixá-la valer sozinha
é exatamente o que o ADR recusa.

A tela vem por último; a evidência de navegador fecha.

## Tarefas

| # | Tarefa | Depende de | Esforço |
|---|---|---|---|
| T1 | [`element_ref` na entidade e o contrato gerado](tasks/T1-element-ref-na-entidade.md) | — | M |
| T2 | [O ato humano de identidade na revisão](tasks/T2-ato-de-identidade.md) | T1 | M |
| T3 | [`quantitativos.csv` com identidade e agrupamento por elemento](tasks/T3-csv-por-elemento.md) | T1 | S |
| T3b | [Polilinha aberta tem comprimento](tasks/T3b-polilinha-aberta.md) | T3 | S |
| T4 | [`QuantitySource`: a quantidade atravessa a fronteira](tasks/T4-quantity-source.md) | T2, T3 | L |
| T4b | [O elo entre a rodada de medição e o croqui aprovado](tasks/T4b-elo-rodada-croqui.md) | T5 | L |
| T5 | [Divergência: tolerância nomeada, issue e bloqueio](tasks/T5-divergencia.md) | T4 | M |
| T6 | [A proposta assistida de agrupamento](tasks/T6-proposta-assistida.md) | T2 | M |
| T7a | Tela da revisão: a identidade do elemento (metade croqui da T7) | T6 | L |
| T7b | Tela da medição: a divergência (metade medição da T7) | T7a, T5 | L |
| T8 | [Evidência de navegador](tasks/T8-evidencia-de-navegador.md) | T7 | S |

Ordem: `T1 → (T2, T3) → T3b → T4 → T5 → T4b → T6 → T7a → T7b → T8`. T2 e T3 são genuinamente paralelas: uma mexe na
revisão, a outra no export.

Duas tarefas nasceram **durante** a execução, e as duas de achados que só apareceram com o
código na mão: a **T3b**, porque polilinha aberta não produzia grandeza nenhuma e a feature
cobriria menos do que aparenta; e a **T4b**, porque a T5 expôs que nada na `/v1` confrontava a
cena com o takeoff — faltava o elo rodada ↔ croqui, sem o qual toda a feature só existia em
teste. A T7 foi partida em **T7a** (croqui) e **T7b** (medição) para as duas metades não
colidirem no mesmo `MedicaoApp.tsx`.

## O que atravessa todas as tarefas

- **Sem `element_ref` declarado, tudo responde como hoje** (decisão 8). É critério de aceite de
  cada tarefa, não só da primeira.
- **Nada casa por proximidade, por número igual ou por rótulo.** O teste que prova isso oferece
  418,12 dos dois lados e exige que **não** case.
- **`approximate` não atravessa a fronteira**, nem sob aceite. E, por não atravessar, também não
  gera divergência: comparar com um número que não pode ser fonte produziria issue sem decisão
  possível.
- **A tolerância é constante nomeada**: `maior(1% do valor da legenda, 0,01 na unidade do item)`,
  e a borda exata **não** abre issue (`>`, nunca `>=`).

## Dependência de feature

Esta feature **começa depois da T2 da [F-046](../F-046-praca-de-varias-pranchas/feature.md) estar
na `main`**: a identidade do item de takeoff passa a ser `(plate_id, item_id)`, e construir o elo
elemento↔item antes disso obrigaria a refazê-lo.

## Integração

Branch e PR próprios a partir da `main`, não empilhados sobre a F-046 — pela lição já registrada
nos planos da F-039 e da F-040. A T1 muda `SceneRevision`, então todo PR roda `make contracts` e
o drift check.

## Human gates

- ADR-0058 e Design Approval: **cumpridos** em 2026-08-28.
- Merge do PR e o aceite que fecha a [issue #102](https://github.com/biahflow/croquito/issues/102),
  num croqui real cuja quantidade chega à medição sem redigitação: atos humanos.
