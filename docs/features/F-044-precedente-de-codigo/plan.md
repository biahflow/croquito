# F-044 — Plano de implementação

Gates cumpridos em 2026-08-28, por ato humano (Daniel Campos):
[ADR-0059](../../adr/0059-item-contratado-fora-da-tabela-sco.md) aceito,
[Design Approval Package](mock/README.md) revisão 1 **aprovado** (condicionado ao gate de
medição), e — o que importa — **o gate que podia cancelar a feature foi exercido**: o dono
forneceu três orçamentos reais, a hipótese de repetição foi medida e **se confirmou**. Ver
[`evidence.md`](evidence.md).

## Medir antes de construir não é cerimônia

A feature inteira repousa numa hipótese que ninguém tinha verificado, e uma medição anterior
**foi retirada** por medir a coisa errada — sobreposição entre os três lotes do contrato, não
entre praças. Por isso a primeira tarefa não constrói nada do produto: ela entrega o
instrumento, e só ele.

O índice de precedentes, a mudança na shortlist e a tela só começam depois do número. O número
existe agora, e é forte: 80% dos rótulos reaparecem entre praças, e 96,1% dos repetidos têm
pacote de códigos idêntico ou contido.

## Tarefas

| # | Tarefa | Estado |
|---|---|---|
| T1 | [Medir a repetição de rótulo entre praças](tasks/T1-medir-a-repeticao.md) | **Entregue** |
| T2 | Índice de precedentes a partir do que já está gravado | Não iniciada |
| T3 | Precedente no topo da shortlist e aceite de pacote em um clique | Não iniciada |

## O que a medição mudou no plano

A estimativa que justificou a prioridade `MEDIUM` era de **cerca de 12 linhas** preenchidas sem
decisão humana. O medido é de **54 a 120 linhas de código por praça** — cerca de cinco vezes
mais, e acima das 24 da [F-042](../F-042-acervo-de-parcelas-de-canteiro/feature.md). A
prioridade fica marcada para revisão do dono, e não foi alterada por conta própria.

A ferramenta também **corrigiu** o script de análise que fez a primeira leitura, na fronteira
entre `subset` e `overlapping` — sem ajustar nada para bater com ele.

## Integração

Branch `feat/f-044-precedente-medicao`, reunida em `feat/f-042-f-043-f-044-integracao`.
Nenhuma planilha real entrou em `tests/`: todas as fixtures são sintéticas, e a leitura dos
arquivos de cliente é local, no molde de `make valuation-parity`.

## Human Gates que continuam abertos

1. **A prioridade da feature**, à luz do volume medido.
2. **Unknown 3 — quantas praças fazem um precedente confiável.** A medição não decide limiar.
