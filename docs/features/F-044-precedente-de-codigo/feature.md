# F-044 — A shortlist aprende com as decisões de código já tomadas

## Status

`IN_PROGRESS`

> Nasce em 2026-08-28, da mesma medição de ROI que originou a
> [F-042](../F-042-acervo-de-parcelas-de-canteiro/feature.md) e a
> [F-043](../F-043-planilha-no-gabarito-da-prefeitura/feature.md). O pedido original do dono
> do produto era este — *"o ideal seria não o orçamentista fazer na mão, já trazer ali uma
> sugestão do código do SCO para o que tem na legenda"* —, e ele continua válido; a medição
> só mostrou que ele é a **terceira** alavanca por retorno, não a primeira.
>
> Registrada com `MEDIUM` e por último de propósito: as outras duas são determinísticas e
> entregam mais, enquanto esta depende de uma hipótese que **ainda não está provada** (ver
> Unknowns).

## Classification

`INTERFACE_CHANGE` — muda o que a etapa de códigos mostra e o que o orçamentista pode
aceitar de uma vez.

## Priority

`HIGH` — **elevada em 2026-08-28** (Daniel Campos), depois da medição. A prioridade `MEDIUM`
original repousava em três razões, e duas caíram: a hipótese de repetição estava por provar
(hoje provada, 80% de repetição e 96,1% de pacote estável) e o ganho era estimado em "cerca de
12 linhas" (medido em **54 a 120 linhas de código por praça**, acima das 24 da
[F-042](../F-042-acervo-de-parcelas-de-canteiro/feature.md)).

A terceira razão — o ganho ser diferido, porque o índice nasce do que está gravado e só uma
rodada real existe no banco — foi resolvida por decisão do dono na mesma data: **a semeadura a
partir de orçamentos passados entra no escopo desta feature**. Com ela o índice nasce com as
praças já feitas em vez de vazio, e o ganho deixa de esperar cinco praças novas.

## Problem

A shortlist casa **texto** contra a descrição do catálogo e **recomeça do zero em toda
praça**. `services/worker/src/croquito_worker/valuation/suggestions.py` decide entre a via
léxica por cobertura ponderada e a híbrida, e nenhuma das duas consulta o que a orçamentista
já decidiu antes.

Mas o dado bom já está no banco. A [F-038](../F-038-pacote-de-servicos/feature.md) gravou os
pares `(item, código)` confirmados, e no documento real esses pares têm cara de regra
estável: "PISO EM CONCRETO" dispara **dois** códigos — `BP09100050(B)` (pavimento rígido) e
`ET39050109(/)` (tela de aço soldada) —, ambos com a mesma quantidade de 418,12 m². O
alambrado dispara outros dois, `PJ14150203(A)` e `PJ14100500(/)`, ambos com 783,86 m². Um
rótulo de legenda que reaparece numa praça nova reencontra o mesmo pacote de códigos.

Hoje nada disso é reaproveitado: o rótulo volta a ser casado por letra, contra um catálogo
de centenas de códigos, como se fosse a primeira vez.

## Desired Outcome

Um rótulo de legenda já decidido antes traz o pacote de códigos que ele disparou, no topo da
shortlist e com a contagem de quantas praças o usaram, para aceitação em um clique — sem
substituir a via léxica, que continua atendendo o rótulo inédito.

## Scope

1. **Índice de precedentes** por rótulo de legenda normalizado → conjunto de códigos
   confirmados, com contagem de praças. Construído do que já está gravado
   (`code_assignments_json`), sem chamada paga.

   **Duas fontes, um índice só** (decisão do dono, 2026-08-28):

   - **a rodada do próprio sistema**, quando o pacote de códigos de um item é fechado — o ato
     humano que diz "acabou" para aquele elemento;
   - **a semeadura a partir de orçamentos passados**, lendo o par (rótulo → códigos) das
     planilhas que a orçamentista já entregou. Sem ela o índice nasce vazio e só ganha valor
     depois de várias praças processadas pelo sistema; com ela, nasce com o que o escritório
     já fez.

   A planilha do cliente **não sobe**: a extração é local, no molde de
   `make valuation-parity`, e o que entra no sistema é o pacote de observações (rótulo,
   código, fonte de preço, praça) — os mesmos dados que as revisões já guardam.
2. **Precedente no topo da shortlist**, rotulado ("você usou isto em N praças"), **sem
   substituir** os blocos por fonte da cascata, que continuam na ordem instalada.
3. **Aceitar o pacote inteiro num clique** — o precedente é do rótulo e vale para todos os
   códigos que ele dispara, que é a forma como a decisão foi tomada originalmente.
4. **Escopo do índice**: chaveado por (rótulo normalizado, **fonte de preço**), nunca por
   rótulo sozinho. Precedente aprendido no contrato de uma praça não vale num programa com
   outra tabela — sugerir código que não existe naquela tabela é pior que não sugerir nada.
   É barato acertar agora e caro depois.

## Out of Scope

- **Aplicar precedente sem confirmação.** Precedente é observação, nunca decisão — a mesma
  regra que já vale para a shortlist.
- **Precedente de quantidade ou de receita de cálculo.** É o passo natural seguinte, e o
  mais valioso a longo prazo ("alambrado: metro linear × altura" reaproveita a fórmula, não
  o número), mas o precedente de código precisa provar valor antes.
- **Substituir o braço semântico da [F-041](../F-041-braco-semantico-hospedado/feature.md).**
  Ver a nota abaixo: são peças diferentes e complementares.

## Precedente não é o braço semântico

A distinção importa e não pode se perder na execução:

| | Braço semântico (F-041) | Precedente (esta feature) |
|---|---|---|
| Casa | texto do rótulo × descrição do catálogo | rótulo × decisão já tomada |
| Custo | pago (embeddings) | de graça, do banco |
| Desempenho | fixo | melhora a cada praça |
| Serve | o **primeiro** encontro com um rótulo | todos os seguintes |

São complementares e não se substituem: o semântico resolve a partida a frio, que é
exatamente o que o precedente não tem como resolver.

## Acceptance Criteria

1. Rótulo com precedente aparece no topo com a contagem de praças; rótulo inédito cai na via
   léxica **sem degradação** em relação a hoje.
2. O precedente nunca vira decisão sem clique.
3. Aceitar o precedente confirma o pacote inteiro de códigos daquele rótulo, numa revisão só.
4. Precedente de outra fonte de preço **não** é oferecido.
5. Nenhuma chamada paga: o índice sai do que já está no banco.
6. **Métrica**: as linhas preenchidas sem decisão humana no Campo do Toca sobem cerca de 12,
   e a medida é registrada em `evidence.md` a cada praça nova, porque o ganho é cumulativo.

## Constraints

- Shortlist é observação, nunca decisão (invariante da jornada).
- O `GET` da shortlist continua sem pagar nada e sem avançar a versão da rodada (ADR-0054
  D7); o precedente não pode introduzir custo nesse caminho.
- Rótulo de legenda é texto de cliente: o índice guarda o que já está gravado nas revisões,
  e não cria fronteira de retenção nova.

## Dependencies

- [F-038](../F-038-pacote-de-servicos/feature.md) — os pares `(item, código)` confirmados
  são a matéria-prima do índice.
- [ADR-0021](../../adr/0021-hybrid-sco-code-retrieval.md) — o matcher, cuja saída o
  precedente antecede sem substituir.
- [ADR-0059](../../adr/0059-item-contratado-fora-da-tabela-sco.md) — **`Accepted` em
  2026-08-28**, alternativa A: a chave do índice inclui a fonte de preço, que sob demanda
  contratada passa a se chamar `contract`.

## Unknowns

1. ~~**A hipótese de repetição entre praças não está provada.**~~ **Medida e confirmada em
   2026-08-28** sobre três orçamentos reais — ver [`evidence.md`](evidence.md). Fica a
   limitação declarada ali: o corpus é de um escritório só, então a repetição está provada
   **dentro de um escritório**, que é o caso de uso, e não entre projetistas diferentes.
   > **Registro de uma medição retirada:** tentei prová-la medindo a sobreposição de códigos
   > entre os "grupos" da aba `PLANILHA GERAL` e achei 98%. A medição **não vale**: aqueles
   > grupos são os três **lotes do contrato** (GRUPO 1 implantação, GRUPO 2 manutenção,
   > GRUPO 3 infraestrutura), não praças diferentes. A sobreposição alta apenas diz que os
   > lotes compartilham o universo de serviços do contrato.

   **A primeira tarefa da feature é medir a repetição sobre duas praças reais** — quantos
   rótulos de legenda reaparecem, e com que estabilidade de pacote de códigos. Se a
   repetição for baixa, a feature perde a razão de existir e deve ser cancelada em vez de
   construída.
2. **Como normalizar o rótulo.** Parcialmente respondido em 2026-08-28: `exact` e `folded`
   deram resultado **idêntico** nos três arquivos reais, então normalização leve basta neste
   corpus. Não encerra o unknown, pelo mesmo motivo do item 1. "ALAMBRADO DO CAMPO EXISTENTE À SER RECUPERAR" e
   "ALAMBRADO PARQUE INFANTIL E CENTRO COMUNITÁRIO h=1.00m" são rótulos diferentes para o
   mesmo par de códigos. Normalização agressiva demais funde o que é distinto; tímida demais
   não reencontra nada.
3. **Quantas praças fazem um precedente confiável.** Uma decisão única pode ter sido um erro;
   exibi-la como precedente propaga o erro.

## Risks

- **Propagar erro com autoridade.** O precedente diz "você já fez assim", o que é um
  argumento forte. Um código escolhido errado uma vez volta com aparência de acerto. A
  contagem de praças ao lado é o controle mínimo; o limiar do unknown 3 é o outro.
- **Rótulo instável entre projetistas.** Praça de outro projetista escreve o mesmo item de
  outro jeito, e o precedente não reencontra. É perda de recall, não erro — mas derruba o
  ganho medido.
- **Vazamento entre fontes de preço.** Sugerir código que não existe na tabela vigente é o
  pior resultado possível, e é o que a decisão 4 do escopo existe para impedir.
- **O aceite do pacote é assimétrico, e o erro fácil é o que não tem volta.** Recusar o
  precedente custa alguns cliques — os códigos continuam alcançáveis um a um pelo bloco da
  fonte e pela busca da etapa, que casa por código (`catalog_search`), então quem desconfia
  não fica preso. Aceitar com um código errado dentro, não: a identidade da decisão é o par
  `(item, código)`, as rotas de `code-assignments` são `GET`, `decisions` e `closures`, e
  **nenhuma delas remove um par confirmado**. É por isso que a marca da decisão 8 fica antes
  do botão, e por isso um seletor por código dentro do pacote não é a resposta óbvia que
  parece: ele barateia a composição sem tocar na assimetria.

## Human Gates

1. ~~**Medir a hipótese de repetição** e decidir se a feature continua~~ — **cumprido em
   2026-08-28**: o dono forneceu três orçamentos reais e a medição **confirmou a
   hipótese**. 80% dos rótulos reaparecem entre praças e, dos repetidos, 98,7% têm pacote
   de códigos idêntico ou contido. Números, método e limitações em
   [`evidence.md`](evidence.md). **A feature continua.**
2. ~~**Design Approval Package**~~ — `INTERFACE_CHANGE`: como o precedente aparece na
   shortlist e como é o aceite de pacote em um clique. Revisão 1 **aprovada em 2026-08-28**
   (Daniel Campos), e **continua condicionada ao gate 1**: aprovar a forma não decide que a
   feature segue. [`mock/README.md`](mock/README.md).
3. ~~Aceite do [ADR-0059](../../adr/0059-item-contratado-fora-da-tabela-sco.md)~~ —
   **cumprido em 2026-08-28** (Daniel Campos), alternativa A.

## References

- `services/worker/src/croquito_worker/valuation/suggestions.py:1-17` — a decisão de qual
  shortlist computar, hoje sem memória nenhuma de decisão anterior.
- `packages/valuation/src/croquito_valuation/assignment.py:629-685` —
  `suggest_codes_over_cascade`, e a ordem por fonte que o precedente antecede sem quebrar.
- `services/api/src/croquito_api/estimate_rounds.py` — `code_assignments_json` na revisão, a
  matéria-prima do índice.
