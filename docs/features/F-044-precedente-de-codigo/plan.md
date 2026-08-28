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
| T2 | O índice de precedentes, com as duas fontes (`tasks/T2-indice-e-semeadura.md`, chega com a T2) | Em execução |
| T3 | Precedente no topo da shortlist e aceite de pacote em um clique | Não iniciada |

## A semeadura entrou no escopo, e é ela que tira o ganho da espera

A medição provou a repetição, mas o índice sai do que está gravado — e só **uma** rodada real
existe no banco. Nascendo vazio, o precedente só teria valor depois de várias praças
processadas pelo sistema, enquanto a [F-042](../F-042-acervo-de-parcelas-de-canteiro/feature.md)
e a [F-043](../F-043-planilha-no-gabarito-da-prefeitura/feature.md) entregam na primeira.

O dono decidiu em 2026-08-28 que a **semeadura a partir de orçamentos passados** entra na
feature. A ferramenta da T1 já lê o par (rótulo → códigos) das planilhas — foi assim que a
medição foi feita —, então o índice pode nascer com as praças que o escritório já entregou. É
o que muda a F-044 de "valiosa daqui a cinco praças" para "valiosa na próxima", e é o que
sustentou a subida da prioridade para `HIGH`.

A planilha do cliente não sobe: a extração é local, e o que entra é o pacote de observações.

## O que a medição mudou no plano

A estimativa que justificou a prioridade `MEDIUM` era de **cerca de 12 linhas** preenchidas sem
decisão humana. O medido é de **54 a 120 linhas de código por praça** — cerca de cinco vezes
mais, e acima das 24 da [F-042](../F-042-acervo-de-parcelas-de-canteiro/feature.md). A
prioridade foi **elevada para `HIGH` pelo dono em 2026-08-28**, junto com a decisão da
semeadura.

A ferramenta também **corrigiu** o script de análise que fez a primeira leitura, na fronteira
entre `subset` e `overlapping` — sem ajustar nada para bater com ele.

## Integração

Branch `feat/f-044-precedente-medicao`, reunida em `feat/f-042-f-043-f-044-integracao`.
Nenhuma planilha real entrou em `tests/`: todas as fixtures são sintéticas, e a leitura dos
arquivos de cliente é local, no molde de `make valuation-parity`.

## Human Gates que continuam abertos

1. **A prioridade da feature**, à luz do volume medido.
2. **Unknown 3 — quantas praças fazem um precedente confiável.** A medição não decide limiar.
