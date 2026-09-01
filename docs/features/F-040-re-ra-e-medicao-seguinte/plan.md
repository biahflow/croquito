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
| T3 | [Declarar a RE-RA e abrir a medição seguinte na API](tasks/T3-declaracao-e-abertura-na-api.md) | **Entregue** |
| T4 | [A memória mostra contratado → vigente com a RE-RA](tasks/T4-memoria-com-a-re-ra.md) | **Entregue** |
| T5 | [A tela: declarar a RE-RA e abrir a medição seguinte](tasks/T5-tela-da-medicao.md) | **Entregue com desvio** |
| T6 | [A porta da medição seguinte: herança e prévia antes de gravar](tasks/T6-a-porta-da-medicao-seguinte.md) | **Entregue** (o desvio da prévia no cliente foi fechado pela T7) |
| T7 | [A prévia é do servidor, não do cliente](tasks/T7-previa-no-servidor.md) | **Entregue** |

> **T5**: a declaração da RE-RA na abertura a partir do orçamento assinado e a memória
> (contratado → vigente → saldo, com o selo "re-ratificada") estão entregues e testadas. A
> **evidência de navegador** (`BROWSER_REQUIRED`, AC 11), que exige subir o stack completo e é
> parte da disciplina de design-approval, foi capturada em 2026-08-28 e está em
> [evidence.md](evidence.md).
>
> **A T5 foi dada por entregue com desvio, e o desvio virou tarefa.** A captura de navegador
> mostrou que **três decisões do pacote de design aprovado** não estavam no código: a medição
> seguinte como uma das duas portas da abertura (decisão 1), a herança mostrada antes de
> qualquer declaração (decisão 4) e a prévia do efeito antes de gravar (decisão 6). O botão
> "Abrir a medição n+1" criava a rodada na hora, com o formulário vazio — e por não passar pela
> abertura, **não havia como declarar uma RE-RA na medição seguinte pela tela**, embora a API
> sempre tenha aceitado `previous_round_id` junto de `amendment`. Como re-ratificação é o que
> acontece *entre* medições, o caminho principal da feature estava inalcançável pela interface.
>
> **T6**: fecha os três desvios. Pacote aprovado é contrato da superfície: decisão aprovada e
> não construída é dívida, não escolha de quem implementa. A tarefa não muda o servidor — ele
> já aceitava a declaração nessa porta, e o read-model já traz o contratado por código; o que
> faltava era a tela.
>
> **A T6 saiu com um desvio, e o desvio era do handoff, não de quem implementou.** O spec dela
> mandou calcular a prévia **no cliente**, contra a regra da jornada de medição escrita no
> `apps/web/AGENTS.md` e citada pelo critério VAL-07: a tela nunca soma, multiplica ou
> arredonda dinheiro nem quantidade. Para cumprir o spec, a tela precisou rederivar duas
> identidades do domínio que nenhuma leitura expunha — o acumulado e o medido do período —, que
> é exatamente a duplicação que a regra existe para impedir.
>
> **T7**: leva a conta para o servidor, com a rota de prévia somente-leitura, mantendo a mesma
> tela que o pacote desenhou. A prévia e a criação passam a partir das **mesmas duas funções**,
> e um teste manda o mesmo corpo às duas rotas para provar que os números coincidem. Pende a
> **recaptura** dos estados novos (`BROWSER_REQUIRED`), que é tarefa própria.

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
- Merge do PR (feito: #109, #112 e #113) e o aceite de código que fecha a
  [issue #100](https://github.com/biahflow/croquito/issues/100): **ocorrido em 2026-08-28** —
  antes de a captura expor os três desvios do pacote, que a T6 fecha.
- **Recaptura** dos seis estados: **feita em 2026-09-01**, sobre a `main` de `482fa8e`, com a
  T6 e a T7 no código ([evidence.md](evidence.md)).
- Merge do PR da T6/T7: **feito** ([#129](https://github.com/biahflow/croquito/pull/129)).
- O aceite numa medição real com contrato re-ratificado permanece como dívida escrita na
  [feature](feature.md).
