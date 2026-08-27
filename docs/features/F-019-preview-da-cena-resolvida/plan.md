# F-019 — Plano de implementação

Gate cumprido: [Design Approval Package](mock/README.md) revisão 1, **aprovado por ato humano
em 2026-08-27**. Não há gate de arquitetura — a feature não cria rota, não muda modelo e não
toca o portão de exportação.

## A ordem é ditada pelo risco de eixo, não por conveniência

O risco central desta feature não é desenhar: é **desenhar invertido**. Uma cena espelhada no
eixo errado parece correta numa geometria simétrica e só aparece na obra. Por isso toda a
aritmética — inclusive o espelhamento — foi isolada num módulo puro **antes** de existir
qualquer SVG, e a fixture do teste é assimétrica de propósito.

A segunda decisão de ordem: a busca da cena entra **depois** do desenho existir. Buscar dado
que ninguém desenha ainda produziria uma chamada de rede sem consumidor, que é exatamente a
lacuna que a F-020 já cobrou uma vez.

## Tarefas

| # | Tarefa | Estado |
|---|---|---|
| T1 | [Aritmética do desenho: espelhamento, enquadramento, escala e vãos](tasks/T1-aritmetica-do-desenho.md) | **Entregue** |
| T2 | [O componente na etapa de aprovação, e a rota que a SPA não chamava](tasks/T2-componente-e-leitura-da-cena.md) | **Entregue** |

Duas tarefas, e não oito: o diff é inteiramente de cliente, sem migração, sem rota e sem
contrato novo. Fatiar mais produziria cerimônia, não segurança.

## O que a execução decidiu diferente do plano

**`contested_spans` não puderam ser posicionados.** O plano supunha que os vãos em disputa
seriam desenhados onde estão, como os aplicados. Ao ler o contrato, `ContestedSpanOut` declara
`axis`, `values_m` e `reading_ids` — e **não** declara posição. A execução desenhou a disputa
como faixa do eixo, com a limitação escrita na tela, em vez de inventar um ponto. Posicioná-la
de verdade é mudança de contrato da API, e portanto outra feature.

É `PLAN_DEVIATION` declarado: o critério 4 do contrato continua atendido (a disputa aparece
sobre a geometria e é distinguível de um vão aplicado), mas com precisão de eixo, não de ponto.

## Integração

Branch própria, PR próprio, sem dependência da F-018 — as duas tocam arquivos diferentes da
mesma tela, e nenhuma das duas depende do que a outra grava.

## Human gates

- Design Approval: **cumprido** em 2026-08-27.
- Merge do PR: ato humano, não executado pela harness.
- Aceite numa rodada real com cena de verdade.
