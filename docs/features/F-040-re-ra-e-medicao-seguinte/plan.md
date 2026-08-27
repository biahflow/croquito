# F-040 — Plano de implementação

Gates cumpridos em 2026-08-27, ambos por ato humano (Daniel Campos):
[ADR-0056](../../adr/0056-re-ra-declarada-e-o-consolidado-da-medicao-seguinte.md) **aceito** e
[Design Approval Package](mock/README.md) revisão 1 **aprovado**.

## A ordem é ditada por dinheiro, não por camada

O risco central é o mesmo da [F-039](../F-039-reajuste-entre-medicoes/feature.md): **mover
número já lançado**. Por isso o domínio vem primeiro e sozinho — enquanto a quantidade vigente
não estiver derivada e testada contra o passado intocável, nenhuma rota grava declaração
nenhuma. A medição seguinte vem logo depois, porque é ela que dá **onde** exercer a RE-RA: sem
a rodada `n+1`, a declaração só existiria na abertura do período 1, onde ainda não há o que
re-ratificar (ADR-0056, contexto). A API entra quando os dois já estão firmes, e a tela por
último, porque é a única parte refeita sem custo de dado.

`contract_diagnosis.py` recomputa as mesmas invariantes por fora, para diagnosticar o MAPÃO
histórico sem abortar na primeira violação; ele acompanha o vigente derivado na mesma tarefa
do domínio, sob pena de dois veredictos sobre a mesma planilha (feature.md, Risks).

## Tarefas

| # | Tarefa | Estado |
|---|---|---|
| T1 | [A RE-RA com procedência e o vigente derivado no domínio](tasks/T1-re-ra-e-vigente-no-dominio.md) | **Entregue** |
| T2 | [A medição seguinte: consolidado `n+1` a partir da rodada anterior](tasks/T2-medicao-seguinte.md) | **Entregue** |
| T3 | [Declarar a RE-RA e abrir a medição seguinte na API](tasks/T3-declaracao-e-abertura-na-api.md) | Planejado |
| T4 | [A memória mostra contratado → vigente com a RE-RA](tasks/T4-memoria-com-a-re-ra.md) | Planejado |
| T5 | [A tela: declarar a RE-RA e abrir a medição seguinte](tasks/T5-tela-da-medicao.md) | Planejado |

## Compatibilidade de schema

`ContractWorkbook.schema_version` sobe para `4.0.0` aceitando `2.0.0` e `3.0.0` (ADR-0056,
decisão 8). Consolidado gravado antes desta feature traz `amended_quantity` preenchido e
nenhuma RE-RA com procedência — o vigente derivado devolve exatamente o número que já estava
lá, e o teste sobre dado gravado real é critério de aceite (feature.md, AC 3).

## Integração

Branch e PR próprios, a partir da `main` — **não empilhado**, pela mesma lição da F-018/F-019
registrada no plano da F-039: com squash merge, PR empilhado entrega o trabalho na branch de
baixo e some da `main` em silêncio.

## Human gates

- ADR e Design Approval: **cumpridos**.
- Merge do PR e o aceite que fecha a [issue #100](https://github.com/biahflow/croquito/issues/100),
  numa medição real com contrato re-ratificado: atos humanos.
