# F-046 — Plano de implementação

Gates cumpridos em 2026-08-28, ambos por ato humano (Daniel Campos):
[ADR-0057](../../adr/0057-multiplas-pranchas-por-praca-na-extracao-de-legenda.md) **aceito** e
[Design Approval Package](mock/README.md) revisão 1 **aprovado**, inclusive a decisão 9 — "a
parcela que fica" —, que nasceu ao desenhar o pacote.

## A ordem é ditada pelo total, não por camada

O risco central desta feature é **somar errado sem que ninguém veja**: uma folha a menos é meia
praça, e meia praça parece uma praça inteira. Por isso o domínio vem primeiro e sozinho —
enquanto o consolidado não souber recusar folha pendente e não souber colapsar uma fusão
declarada, nenhuma rota grava consolidado nenhum.

A extração de N folhas vem **depois** do consolidado, e não antes, porque extrair folha é gastar
dinheiro: sem o consolidado pronto, uma segunda folha extraída não teria onde ser somada, e o
gasto seria por conta de nada.

A tela vem por último, porque é a única parte refeita sem custo de dado.

## Tarefas

| # | Tarefa | Depende de | Esforço |
|---|---|---|---|
| T1 | [O consolidado da praça e o vínculo de identidade no domínio](tasks/T1-consolidado-e-vinculo-no-dominio.md) | — | M |
| T2 | [O boletim da praça: união dos conjuntos e a parcela fundida](tasks/T2-boletim-da-praca.md) | T1 | L |
| T2b | [O centavo da praça: a GERAL governa a deriva](tasks/T2b-centavo-da-praca.md) | T2 | S |
| T3 | [Persistência e rotas `/v1` da praça](tasks/T3-persistencia-e-rotas.md) | T2 | M |
| T4 | [Promover N folhas: seleção explícita, em lote](tasks/T4-promover-n-folhas.md) | T3 | M |
| T5 | [A tela da praça: folhas, consolidado e a declaração de identidade](tasks/T5-tela-da-praca.md) | T3, T4 | L |
| T6 | [Evidência de navegador](tasks/T6-evidencia-de-navegador.md) | T5 | S |

Ordem: `T1 → T2 → T2b → T3 → T4 → T5 → T6`. Não há paralelismo seguro entre T1–T3: as três tocam a
mesma cadeia de cálculo. T4 e T5 poderiam ir juntas se houvesse dois executores, mas T5 precisa
de N folhas reais para exercer a faixa de cartões.

## O que atravessa todas as tarefas

- **Praça de uma folha é o caso N=1** e responde byte a byte como hoje. Todo PR desta feature
  roda o teste de não-regressão de digest antes de qualquer coisa.
- **Nunca fundir por semelhança**: rótulo, unidade e proximidade não associam nada. O único
  caminho de fusão é a declaração humana.
- **Fail-closed erra para somar demais e visível**, nunca para esconder.
- Erros novos nascem com nome estável em `application/problem+json`. Os nomes propostos no
  pacote de design (`WORKSITE_TAKEOFF_PLATE_PENDING`, `WORKSITE_LINK_SAME_PLATE`,
  `WORKSITE_LINK_INCOMPLETE`) são propostas do mock, não domínio existente: a T1 os fixa.

## O centavo da praça

A T2 expôs um efeito de segunda ordem: com um boletim por folha, o mesmo código medido em duas
folhas faz `TRUNC(Σq×preço)` divergir de `Σ TRUNC(q_i×preço)`, e `_check_consolidated_total`
recusava a pasta inteira. Era proporcional enquanto o caso era de exceção (multi-obra); na praça
de várias folhas vira o caso normal. O [ADR-0062](../../adr/0062-a-deriva-de-centavo-entre-folhas-da-praca.md),
aceito por ato humano em 2026-08-29, resolve o caso que o ADR-0018 tinha deixado em aberto: a
GERAL governa, e a deriva passa a ser declarada em vez de fatal. A T2b implementa.

## O teto de gasto continua por chamada

A T4 expôs que o teto de gasto da extração é **por chamada**, não por rodada: com a praça de
várias folhas, promover 12 folhas autoriza 12 vezes o teto de uma prancha sem que ninguém tenha
declarado esse total. **Decisão humana de 2026-08-29** (Daniel Campos): manter por chamada. Os
freios declarados são a contagem de folhas que a resposta do lote informa antes de executar e o
`WORKSITE_PLATE_LIMIT` de 12 por praça. Um teto agregado por rodada seria mudança do modelo de
gasto, e fica registrado aqui como caminho conhecido, não como dívida esquecida.

## Decisões de mecanismo já tomadas

- **A praça não vira entidade persistente.** Ela continua sendo `worksite_key` na rodada
  (ADR-0028 D8); o consolidado é artefato gravado na revisão, como o pacote e os assignments.
  O `Unknown` do contrato sobre `worksite_key` vs. id próprio fica resolvido assim.
- **As folhas da rodada deixam de ser colunas escalares.** `plate_upload_id`,
  `plate_object_key`, `plate_source_sha256` e `plate_page_count`
  (`services/api/src/croquito_api/database.py:942-951`) passam a ter uma tabela filha por
  rodada; a migração preserva a folha existente como a primeira da praça.
- **`TakeoffPacket` e `CodeAssignmentSet` não ganham campo** (ADR-0057, decisão 8).

## Integração

Branch e PR próprios a partir da `main` — **não empilhado**, pela lição registrada nos planos da
F-039 e da F-040: com squash merge, PR empilhado entrega o trabalho na branch de baixo e some da
`main` em silêncio.

A F-047 **depende desta feature** (a identidade do item de takeoff passa a ser `(plate_id,
item_id)`), e só começa depois que a T2 estiver na `main`.

## Human gates

- ADR-0057 e Design Approval: **cumpridos** em 2026-08-28.
- Merge do PR e o aceite que fecha a [issue #101](https://github.com/biahflow/croquito/issues/101),
  numa praça real de mais de uma prancha: atos humanos.
- A extração paga de folhas adicionais numa praça real continua exigindo autorização de gasto
  por rodada.
