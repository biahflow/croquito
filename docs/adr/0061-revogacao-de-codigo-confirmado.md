# ADR-0061: Desfazer um código confirmado é decisão nova, que reabre o pacote e compensa o índice

Status: Proposed  
Data: 2026-08-28  
Responsável: Product / Engineering

## Contexto

Desde o [ADR-0053](0053-cardinalidade-n-n-elemento-servico.md) a identidade da decisão de
código é o par `(item_id, code)`: um elemento de legenda recebe N códigos, e o que recusa
repetição é o par. A [F-038](../features/F-038-pacote-de-servicos/feature.md) acrescentou o
`ItemPackageClosure` — o ato humano que declara o pacote completo — e a
[F-044](../features/F-044-precedente-de-codigo/feature.md) pendurou nesse fechamento um
efeito novo: as confirmações do item viram observações no índice de precedentes, que a praça
seguinte reencontra.

O que nunca existiu é o inverso. A etapa tem `GET`, `decisions` e `closures`;
`_ensure_batch_decidable` recusa re-decidir um par com `ASSIGNMENT_ITEM_ALREADY_DECIDED`
(`packages/valuation/src/croquito_valuation/assignment.py:1364-1377`), e não há rollback de
revisão em lugar nenhum da `/v1`. Um código confirmado por engano só se conserta refazendo a
rodada — jogando fora takeoff revisado, calibração e todas as outras decisões da praça.

A revisão 2 do pacote de design da F-044 tornou isso mais caro sem criar o problema: o aceite
de precedente grava **N códigos num ato só**, então a mesma distração passou a poder gravar
um pacote inteiro. A [F-045](../features/F-045-desfazer-codigo-confirmado/feature.md) existe
para fechar a lacuna, e três perguntas precisam de resposta registrada antes de qualquer
código: **o que a revogação faz com o histórico, com o fechamento do pacote e com o índice.**

## Decisão

**D1 — Revogar é decisão nova, nunca edição do que já foi gravado.** A revogação produz uma
revisão nova, como confirmação e fechamento produzem. A revisão anterior continua existindo,
com o par ainda confirmado dentro dela: desfazer não reescreve o passado, acrescenta um ato
ao presente. Justificativa é **obrigatória**, como na rejeição.

**D2 — O par sai do conjunto corrente e fica registrado em `revocations`.** Não basta a prova
estar na revisão anterior: quem lê o conjunto corrente precisa distinguir "nunca foi
decidido" de "foi decidido e desfeito", sem diferenciar revisões. O registro carrega o par,
quem revogou, quando e por quê. É campo novo em `CodeAssignmentSet`, com default vazio —
conjunto gravado antes desta decisão relê exatamente como antes.

**D3 — Revogar reabre o pacote do elemento.** Se o item tinha `ItemPackageClosure`, ela cai
no mesmo ato. A completude foi afirmada sobre um pacote que mudou, e mantê-la seria deixar em
pé uma afirmação que ninguém refez. A alternativa — exigir uma reabertura explícita antes —
foi rejeitada: sem rota de reabertura, ela seria um beco sem saída, e com rota seria
cerimônia para o mesmo efeito.

**D4 — O índice de precedentes é compensado na mesma transação.** A observação
`(praça, rótulo normalizado, fonte de preço, código)` que o fechamento desta praça gravou é
removida. Só a de origem `round` e só a desta praça: observação **semeada** de orçamento
passado (fonte B da F-044) não é tocada por ato de rodada, porque ela registra o que outra
praça fez, e um erro daqui não desmente aquilo.

**D5 — Revogar não bane o código.** Depois de revogado, o mesmo par pode ser confirmado de
novo — a revogação limpa o par do conjunto corrente e ele volta a ser decidível. Bani-lo
transformaria um conserto em punição, e a orçamentista que revogou por engano ficaria sem
saída dentro da própria rodada.

**D6 — O regime `1.0.0` não aceita revogação.** Naquele regime um item tem um código só e a
confirmação *era* o fechamento; revogar ali significaria outra coisa, e reabrir esse
significado para rodadas antigas não serve a ninguém. Recusa nomeada.

**D7 — Enquanto o gate humano não decide, revogar depois da aprovação do orçamento é
RECUSADO.** A aprovação é nominal e amarrada por digest ao conteúdo do orçamento (ADR-0046),
mas revogar **não** remonta o orçamento: o digest continuaria conferindo enquanto o conjunto
de códigos por baixo dele mudou, e o portão de exportação — que leria a divergência como
`APPROVAL_CONTENT_MISMATCH` — não veria nada. A recusa
(`ASSIGNMENT_REVOCATION_AFTER_APPROVAL`) escolhe o lado seguro sem decidir o unknown: se o
dono decidir permitir, apaga-se a checagem; o caminho contrário — descobrir depois que uma
assinatura aponta para um conjunto que mudou — não tem volta.

## Consequências

- Existe, pela primeira vez, um ato que **retira** algo do conjunto corrente. Todo consumidor
  do `CodeAssignmentSet` passa a poder ver um item que já teve código e não tem mais — que é
  o mesmo estado de um item nunca decidido, com `revocations` explicando a diferença.
- **Reabrir o pacote tem efeito adiante**: o boletim e o portão de exportação recusam pacote
  aberto, então revogar um código de item fechado bloqueia a exportação até alguém fechar de
  novo. É o comportamento correto, e precisa estar escrito na resposta e na tela — reabrir em
  silêncio seria a pior versão disto.
- A contagem de praças do índice **cai** quando a última observação daquele código naquela
  praça é removida. Um precedente pode desaparecer da shortlist da praça seguinte por causa
  de uma revogação — e é o que se quer: ele deixou de ser verdade.
- A compensação abre a possibilidade de o índice divergir se a remoção falhar. Por isso a
  mesma transação do ato, e nunca um efeito posterior.

## Alternativas consideradas

- **Apagar o assignment sem registro** — rejeitada: perde a distinção entre "nunca decidido"
  e "desfeito", e é justamente essa distinção que uma auditoria procura.
- **Marcar o assignment como `revoked` mantendo-o em `assignments`** — rejeitada: obrigaria
  todo consumidor (boletim, exportação, precedente, contagens) a filtrar por status, e um
  consumidor esquecido imprimiria linha revogada. Sair da lista é falha fechada.
- **Rollback de revisão** — rejeitada para este problema: desfaz também tudo o que foi feito
  depois do engano, o que é mais destrutivo que o próprio engano. Continua fazendo sentido
  como feature própria, para outro problema.
- **Editar a confirmação, trocando o código** — rejeitada: esconde a decisão original, e o
  par revogado é exatamente o que alguém vai querer ver depois.
- **Não compensar o índice, deixando a observação viva** — rejeitada: o índice ensinaria à
  praça seguinte o código que esta praça desfez, com a autoridade de "você já fez assim".

## Gate humano

Esta decisão precisa de **aceite explícito** antes de a implementação da F-045 valer.

O **unknown 1 da F-045** — o que acontece com uma revogação depois de o orçamento ter sido
aprovado — continua sendo do dono. A implementação não o decidiu: aplicou a D7, que **recusa**
enquanto ninguém decide, exatamente porque o erro nessa direção é reversível com uma linha e
o erro na direção contrária não é.
