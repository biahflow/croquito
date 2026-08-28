# F-044 — Evidência

## Human Gate 1 — a hipótese de repetição, medida

**Data**: 2026-08-28  
**Resultado**: **hipótese confirmada**. A feature continua.

### O que foi medido

Três orçamentos reais, fornecidos pelo dono do produto em 2026-08-28, todos com revisão
SEAC do mesmo contrato:

| Praça | Aba de memória | Blocos | Com rótulo | Rótulos distintos |
|---|---|---|---|---|
| Campo do Toca | `PRAÇA CAMPO DO TOCA` | 129 | 125 | 76 |
| Dona Eli | `MEMÓRIA DE CÁLCULO` | 133 | 130 | 84 |
| Todos os Santos (Quadra do Condomínio) | `MEMÓRIA RESIDENCIAL MIRANTE` | 71 | 67 | 48 |

Os arquivos são dados de cliente: **não estão versionados**, e nenhum rótulo, código ou
valor deles entra em `tests/`. A leitura é local, no molde de
`make valuation-parity PREVIOUS=<caminho>`.

O par medido é (**rótulo do elemento na memória de cálculo** → **conjunto de códigos SCO que
ele dispara**). Cada bloco da memória traz item, código e, abaixo, o rótulo do elemento; um
mesmo rótulo aparece em vários blocos, que é exatamente o pacote N:N da
[F-038](../F-038-pacote-de-servicos/feature.md).

### Repetição entre praças

```
rótulos distintos no total       95
rótulos presentes em ≥2 praças   76   (80,0% de repetição)
```

Estabilidade do pacote de códigos, entre as praças em que o rótulo reaparece:

| Classe | Quantos | % dos repetidos |
|---|---|---|
| `identical` — mesmo conjunto de códigos | 65 | 85,5% |
| `subset` — **todos** os pares aninhados por inclusão | 8 | 10,5% |
| `overlapping` — algum par só se cruza, sem conter | 2 | 2,6% |
| `disjoint` — algum par sem código em comum | **1** | 1,3% |

**96,1% dos rótulos repetidos têm pacote idêntico ou contido.** O único caso `disjoint` em
76 é `PONTOS DE SOLDA`: `SC19050600(/)` no Campo do Toca contra `SC14050400(/)` na Dona Eli.

> **Correção de método.** A primeira apuração, feita por script de análise, classificava como
> `subset` qualquer rótulo com **algum** par aninhado, o que dava 10 `subset` e 0
> `overlapping` — e a leitura otimista de "98,7% idêntico ou contido". A ferramenta
> `precedent-eval` usa a regra **estrita**: `subset` só quando **todos** os pares são
> aninhados; um único par que apenas se cruza derruba o rótulo para `overlapping`. A regra
> estrita é a correta para o que se quer saber, porque um par incompatível dentro do grupo é
> exatamente o que não pode ficar escondido atrás de uma média.
>
> Os dois rótulos que mudam de classe são `ALAMBRADO` e `QUADRA POLIESPORTIVA`, ambos em três
> praças. Em `ALAMBRADO`, o Campo do Toca traz `ET04600200(/)` e `PJ14150203(A)` que as
> outras não têm, enquanto as outras trazem `AD14100200(/)` que ele não tem: não é contenção,
> é divergência real, e chamar isso de `subset` esconderia o fato.
>
> A conclusão do gate não muda — a hipótese continua confirmada, e por larga margem.

Os oito `subset` não são erro — são escopo menor. `CAMADA DE BRITA` dispara um código no
Campo do Toca e quatro em Todos os Santos, porque ali há drenagem; `GUARDA CORPO` perde o
código de instalação na praça que não o tem.

### Ganho prático, cada praça tratada como a nova

| Praça nova | Rótulos com precedente | Pacote exato | Linhas de código cobertas |
|---|---|---|---|
| Campo do Toca | 70/76 (92%) | 63/70 | 111/125 (89%) |
| Dona Eli | 76/84 (90%) | 71/76 | 120/130 (92%) |
| Todos os Santos | 43/48 (90%) | 36/43 | 54/67 (81%) |

### O que estes números mudam na feature

A F-044 foi registrada com prioridade `MEDIUM` e estimativa de **cerca de 12 linhas**
preenchidas sem decisão humana. A medição diz outra coisa: **54 a 120 linhas de código por
praça** têm precedente com pacote exato ou contido.

Isso a coloca acima da [F-042](../F-042-acervo-de-parcelas-de-canteiro/feature.md) (24
linhas) em volume, e a estimativa original está subdimensionada por um fator de cerca de
cinco. **A prioridade foi elevada para `HIGH` pelo dono em 2026-08-28**, e a semeadura de
orçamentos passados entrou no escopo da feature na mesma decisão — sem ela o índice nasceria
vazio, porque só uma rodada real existe no banco, e o ganho medido esperaria várias praças
novas.

### Unknown 2 — como normalizar o rótulo

Medido com duas estratégias, `exact` (texto como escrito) e `folded` (casefold, sem acento,
pontuação colapsada): **resultado idêntico nas duas**, nos três arquivos. Neste corpus os
rótulos já chegam padronizados, e normalização agressiva não é necessária.

Isso **não** encerra o unknown: o corpus é de um escritório só (ver limitações). A conclusão
sustentada é a mais fraca — normalização leve basta aqui, e não há evidência que justifique
uma agressiva.

## Limitações desta medição, declaradas

1. **Um escritório, um contrato.** Os três arquivos são revisão SEAC do mesmo contrato e
   compartilham a estrutura da planilha, a numeração `GG.N` e a lista de preços. A medição
   prova a repetição **dentro de um escritório**, que é o caso de uso real do produto, e
   **não** prova nada sobre praças de projetistas diferentes. O risco "rótulo instável entre
   projetistas", declarado na feature, continua aberto e não foi testado.

2. **O rótulo medido é o da memória de cálculo, não o da legenda da prancha.** É a melhor
   aproximação disponível — a memória é onde o rótulo do elemento encosta no código —, mas o
   índice que a feature vai construir se chaveia pelo rótulo da **legenda**, extraído da
   prancha. Se os dois divergirem sistematicamente, o recall medido aqui é otimista.

3. **A perda de recall já aparece no corpus.** O código `BP09100050(B)` é `PASSEIO` no Campo
   do Toca e `CALÇADA DE ACESSO` nas outras duas: o mesmo serviço com dois rótulos. Nenhuma
   normalização razoável funde os dois, e nenhuma deveria. É perda de recall, não erro — e é
   parte de por que a cobertura fica em 90% e não em 100%.

4. **A medição foi feita primeiro por script de análise**, fora do repositório, e depois
   reproduzida pela ferramenta `precedent-eval` (`--memoria <arquivo>:<aba>`, no molde local
   do `parity`). A ferramenta bateu todos os números — 129/133/71 blocos, 125/130/67
   rotulados, 95 rótulos, 76 repetidos, 65 `identical`, 1 `disjoint` — e **corrigiu** a
   fronteira `subset`/`overlapping` do script, como registrado acima. A ferramenta é o
   artefato reproduzível; o script foi só o instrumento da primeira leitura.

   Os blocos sem rótulo são contados e nomeados pela ferramenta, nunca descartados em
   silêncio: 4 no Campo do Toca, 3 na Dona Eli, 4 em Todos os Santos.

5. **Uma fonte de preço para toda a leitura `--memoria`.** A aba de memória não grava
   identificador de tabela de preços, então a ferramenta trata os três arquivos como a mesma
   fonte — o que é verdade aqui (um contrato só) e é o que torna a comparação possível.
   Derivar a fonte do nome do arquivo tornaria qualquer repetição entre praças indetectável
   por construção. A consequência declarada: hoje `--memoria` **não** separa praças de
   contratos diferentes numa mesma leitura, e usá-lo assim invalidaria a medição.

## Human Gate 2 — Design Approval Package

Revisão 1 **aprovada em 2026-08-28** (Daniel Campos), condicionada a este gate 1 — que agora
está cumprido. Ver [`mock/README.md`](mock/README.md).

**Revisão 2 aprovada em 2026-08-28** (Daniel Campos): a contagem de praças **por código**
(decisão 8, estado 6). As sete decisões da revisão 1 continuam válidas e nenhuma delas muda.

## Human Gate 3 — ADR-0059

Cumprido em 2026-08-28.

## T2 — o índice, com as duas fontes

**Data**: 2026-08-28. Executada.

O índice vive em `precedent_observations` (migração `0022`), uma linha por
`(praça, rótulo normalizado, fonte de preço, código)`, com `tenant_id` **NOT NULL** e toda
leitura filtrada por ele. A camada de aplicação é `croquito_api/precedents.py`; a normalização
e o contrato do pacote de semeadura são reusados da T1 (`croquito_valuation.precedent`).

Duas fontes, como o contrato da task pediu:

- **a rodada** — efeito do fechamento de pacote
  (`POST /v1/estimate-rounds/{id}/code-assignments/closures`), na mesma transação, só com
  código confirmado;
- **a semeadura** — `croquito-valuation precedent-extract` lê a memória de cálculo de uma
  praça passada na máquina de quem semeia e escreve um pacote; `POST /v1/precedents/seed`
  o ingere. A planilha do cliente não sobe.

A consulta é `precedents_for(session, tenant_id, labels, price_source)`, que a T3 consome.

### Decisões que ficaram registradas na execução

1. **A fonte de preço da semeadura é declarada** (`--price-source`, com o rótulo legível do
   contrato como padrão). Sem poder declará-la, todo precedente semeado nasceria sob uma fonte
   que jamais casaria com o `catalog_sha256` de uma rodada real, e a semeadura seria um índice
   paralelo que ninguém alcança. Inventar um hash seria pior.
2. **A recusa de colisão de praça fica do lado da semeadura**, e não do fechamento. Semear é
   importação deliberada, que pode esperar e ser refeita com outra chave; fechar o pacote é o
   ato central da jornada, e travá-lo pela contabilidade de um índice seria a ferramenta
   impedindo o trabalho. A consequência declarada: uma praça semeada ANTES de a rodada real
   existir continua semeada, e a rodada acrescenta observações sob a mesma chave — a contagem
   de praças não infla (ela conta chaves distintas), mas as duas origens convivem ali.
3. **A estratégia de normalização é gravada com cada observação** e filtrada na consulta.
   Reindexar sob outra estratégia deixa as linhas velhas de fora, em vez de misturar duas
   chaves para o mesmo rótulo.

### Limitação nova, medida na execução

`folded` — a estratégia que a medição escolheu — **não colapsa espaço interno repetido**
(`catalog._lexical_normalize` dobra caixa e acento, e só). "PISO EM CONCRETO" e
"Piso em Concretô" caem na mesma chave; "PISO  EM  CONCRETO" (com espaço duplo) não. É perda
de recall, não erro, e é da mesma família da que a medição já declarou (`PASSEIO` ×
`CALÇADA DE ACESSO`). Não foi corrigida aqui de propósito: a T2 reusa a normalização da T1, e
trocá-la exigiria refazer a medição que a sustenta.

## T3c — a contagem por código, à vista

**Data**: 2026-08-28. Executada.

A T3a devolvia `worksite_count` em dois níveis e a tela escrevia só o do rótulo — o contrato
dela registrou isso em uma linha (*"a tela mostra o do rótulo no cabeçalho"*). A consequência
não era cosmética: um código de **1** praça dentro de um pacote de **4** entrava no aceite de
um clique com a mesma autoridade dos outros, que é o risco de *propagar erro com autoridade*
que a feature declara temer, e para o qual a contagem é o controle mínimo.

Nenhum dado novo foi pedido: `codes[].worksite_count` já atravessava a fronteira desde a T3a.
A mudança é de tela — quatro funções puras, duas frases, um selo e um aviso.

A regra que ficou (decisão 8 do pacote, revisão 2):

- **pacote não unânime** — algum código veio de menos praças que o rótulo: **todos** os
  cartões escrevem a fração ("em 4 das 4 praças", "em 1 das 4 praças"), o minoritário leva
  selo âmbar, e uma linha âmbar antes do botão diz quantos são e que eles entram junto;
- **pacote unânime**: nenhum cartão repete a contagem — o cabeçalho já a disse;
- a marca **se repete na lista de confirmação**, porque é ali que o clique grava;
- o aceite continua sendo do pacote **inteiro**, num pedido só: nada foi desabilitado,
  removido nem reordenado.

Duas decisões de execução, ambas registradas no pacote:

1. **Tudo-ou-nada dentro do bloco.** Marcar só o cartão divergente deixaria os outros sem
   contagem, e ausência de rótulo é ambígua: o leitor não distingue "veio em todas" de "não
   veio o dado". O contraste entre as frações é o que informa.
2. **Nenhum limiar.** A marca é **relativa** ao rótulo (`código < rótulo`), e por isso não
   toca o unknown 3, que continua aberto. Um pacote de rótulo com uma praça só é unânime por
   construção, e ali só o aviso da revisão 1 aparece.

O pacote que a governa é a **revisão 2, aprovada em 2026-08-28**.

Um terceiro caso apareceu na revisão do próprio diff e não estava no pacote: a fração não
cabe quando sobra **um** código só ("1 dos 1 códigos" conta certo e lê errado), nem quando
**nenhum** código do que sobrou acompanhou o rótulo. Os dois nascem da mesma origem — a API
omite código fora do catálogo vigente sem recalcular a contagem do rótulo (T3a) —, e as duas
frases próprias foram escritas e testadas. A copy final continua sendo gate do dono.

Validação: `npm --workspace @croquito/web run test -- src/orcamento/precedente.test.tsx`
(29 testes, verdes; 7 novos), mais `make check` (exit 0) e `make test` (2821 pytest,
1450 web, 261 campo).

## O que continua aberto

- **Unknown 3 — quantas praças fazem um precedente confiável.** A medição não decide limiar.
  Com três praças, o caso de "uma praça só" é comum e é justamente o que o desenho marca com
  aviso. A T2 não decide limiar: ela devolve a contagem, e quem a usa é a T3.
- ~~**A prioridade da feature**~~ — **elevada para `HIGH` em 2026-08-28** (Daniel Campos),
  junto com a decisão de trazer a semeadura para o escopo. A divergência que a T2 registrou
  entre o contrato dela e o [`feature.md`](feature.md)/[roadmap](../../product/ROADMAP.md)
  existia porque a worktree da T2 saiu antes desse commit; os três estão alinhados agora.
- ~~**A mudança na shortlist e a tela**~~ — T3a, T3b e T3c entregues.
- **Se o código minoritário deveria poder sair do pacote antes de confirmar.** A revisão 2
  decide marcar, não decide desmarcar — retirar um código do aceite mudaria a decisão 4 e
  precisa da evidência de que a marca sozinha não bastou.
