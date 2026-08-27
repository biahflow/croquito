# F-039 — Plano de implementação

Gates cumpridos em 2026-08-27: [ADR-0055](../../adr/0055-reajuste-como-ato-declarado-sobre-o-consolidado.md)
**aceito** e [Design Approval Package](mock/README.md) revisão 1 **aprovado**, ambos por ato
humano.

## A ordem é ditada por dinheiro, não por camada

O risco central desta feature é **mover número já pago**. Por isso o domínio vem primeiro e
sozinho: enquanto o preço vigente não estiver derivado e testado contra o passado intocável,
nenhuma rota pode gravar declaração nenhuma. E o portão de exportação vem antes da API pelo
mesmo motivo — é ele que decide se um boletim reajustado pode sair.

A tela vem por último porque é a única parte que pode ser refeita sem custo de dado.

## Tarefas

| # | Tarefa | Estado |
|---|---|---|
| T1 | [O reajuste no domínio: declaração, preço vigente e composição](tasks/T1-reajuste-no-dominio.md) | **Entregue** |
| T2 | [O portão de exportação sobre o preço vigente](tasks/T2-portao-sobre-o-vigente.md) | **Entregue** |
| T3 | [Declarar o reajuste na abertura da rodada](tasks/T3-declaracao-na-api.md) | **Entregue** |
| T4 | [A memória e o boletim mostram a conta](tasks/T4-memoria-com-a-conta.md) | **Entregue** |
| T5 | [A declaração e a conta na tela da medição](tasks/T5-tela-da-medicao.md) | **Entregue** |

## O que a execução decidiu diferente do plano

2. **O fator não virou coluna da tabela da memória**, como a decisão 5 do pacote de design
   pedia: ele é um só para o contrato inteiro e aparece na linha da declaração. Desvio de
   decisão aprovada, registrado na evidência — a coluna volta se for desejada.

1. **O modelo não conseguia representar o passado que a decisão 6 do ADR prometia.**
   `ContractLine.validate_periods` exige que cada período bata com `quantidade × unit_price` da
   linha, e a linha tem UM preço: um contrato reajustado era recusado pelo próprio consolidado.
   `PeriodProgress` ganhou `unit_price` opcional, e o ADR-0055 foi **emendado** na decisão 6.
   É desvio material, e por isso está aqui e lá.

## Integração

Branch e PR próprios, a partir da `main` — **não empilhado**. É a lição da rodada da
F-018/F-019: com squash merge, PR empilhado mergeado na ordem natural entrega o trabalho na
branch de baixo e some da `main` em silêncio.

## Human gates

- ADR e Design Approval: **cumpridos**.
- Merge do PR e aceite numa medição real com contrato reajustado: atos humanos.
