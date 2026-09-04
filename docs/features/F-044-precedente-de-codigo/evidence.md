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
- **Desfazer um par `(item, código)` confirmado — não existe hoje, e é candidato a fatia
  própria.** As rotas de `code-assignments` são `GET`, `decisions` e `closures`; a decisão é
  do par e a rota recusa item já decidido. Enquanto isso não existir, o único conserto de um
  aceite errado é a rodada seguinte. Vale como fatia própria porque não é do precedente: é da
  etapa de códigos inteira, e a F-038 a deixou de fora pelo mesmo motivo. Registrado aqui
  porque foi a revisão 2 da F-044 que a expôs — o aceite em um clique aumenta o que se grava
  por ato, e portanto o custo de não poder desfazer.
- **Se o código minoritário deveria poder sair do pacote antes de confirmar.** A revisão 2
  decide marcar, não decide desmarcar — retirar um código do aceite mudaria a decisão 4 e
  precisa da evidência de que a marca sozinha não bastou.
- ~~**O aceite em lote não grava**~~ — achado da evidência de navegador de 2026-09-04, descrito
  na seção abaixo. **Reparado no mesmo dia**: a arbitragem foi pelo contrato da rota (a tela
  passou a citar `catalog_sha256`), e a re-verificação de navegador gravou os três pares numa
  revisão só. O critério 3 da T3b está cumprido por inteiro. Ver *"O desfecho: o reparo, e a
  re-verificação que ele exigiu"*.

## Evidência de navegador (T3b e T3c)

Classificação: `BROWSER_REQUIRED` — a F-044 é `INTERFACE_CHANGE`, e o
[pacote aprovado](mock/README.md) (revisão 1 e revisão 2, aprovadas por ato humano em
2026-08-28) é a especificação da superfície que a T3b e a T3c construíram.

Capturada em **2026-09-04** contra o stack local — PostgreSQL, floci e Keycloak reais, API em
`uvicorn` e a SPA em `vite` —, com sessão OIDC real (`orcamentista.f044`, tenant
`tenant-f044`) e navegação determinística em Chromium via Playwright (1440 px de largura,
`deviceScaleFactor` 2). Nenhuma tela é mock e nenhum passo dependeu de modelo.

O dado é **sintético e inteiro**: as quatro praças passadas, os rótulos, os códigos e os
preços foram inventados para esta bancada. Nenhum rótulo, código ou valor do documento real
do cliente entra aqui — o pacote de design já declarava que os seus também eram ilustrativos.
O índice nasceu de quatro praças semeadas por `POST /v1/precedents/seed` (fonte B da T2) sob a
fonte de preço da própria rodada, montadas para produzir os estados do pacote:

| Rótulo do elemento | Praças | Códigos | Estado que ele exercita |
| --- | --- | --- | --- |
| `PISO EM CONCRETO (SINTETICO)` | 4 | 2, ambos nas 4 | pacote **unânime** |
| `ALAMBRADO H=3,00M (SINTETICO)` | 4 | 3, um deles em 1 praça | pacote **não unânime** |
| `GUARDA CORPO METALICO (SINTETICO)` | 1 | 2 | precedente **fraco** |
| `BANCO DE MADEIRA PLASTICA (SINTETICO)` | — | — | **rótulo inédito** |

| Arquivo | Estado do pacote | O que a imagem prova |
| --- | --- | --- |
| [`evidencia/01-selos-na-lista.png`](evidencia/01-selos-na-lista.png) | selo por elemento (02 e 04 do pacote) | Os quatro elementos com o selo escrito: “precedente em 4 praças”, “precedente em 1 praça” e “rótulo inédito”. O selo de inédito **só existe ao lado de irmãos que têm precedente**, que é a decisão 7 aplicada à lista. |
| [`evidencia/02-precedente-unanime.png`](evidencia/02-precedente-unanime.png) | 02 — o precedente no topo | “Você já usou isto em 4 praças” por extenso, o bloco **acima** dos blocos por fonte, a fonte nomeada no cabeçalho (`SCO · data-base 2026-09`, `1ª fonte da cascata`), e **nenhum cartão repetindo a contagem** — o pacote é unânime (decisão 8). Abaixo, a cascata inteira, com os mesmos dois códigos aparecendo de novo: é a decisão 3, e a tela a escreve (“o código que já era candidato aparece duas vezes”). |
| [`evidencia/03-pacote-nao-unanime.png`](evidencia/03-pacote-nao-unanime.png) | 06 — a contagem por código | **Todos** os três cartões escrevem a fração (“em 4 das 4 praças”, “em 1 das 4 praças”), o minoritário leva o selo âmbar, e a linha âmbar antes do botão diz quantos são: *“1 dos 3 códigos deste pacote não veio em todas as praças do rótulo. Ele entra junto se você aceitar o pacote inteiro.”* A cor é redundância: a fração vai escrita nos três. |
| [`evidencia/04-precedente-fraco.png`](evidencia/04-precedente-fraco.png) | 04 — uma praça só | “Você usou isto em 1 praça” e o aviso âmbar por extenso: *“Decisão de uma praça só. Confira antes de aceitar: se aquela vez foi um engano, aceitar aqui repete o engano com cara de acerto.”* Nenhum cartão traz fração — com uma praça o pacote é unânime por construção, e é só o aviso da decisão 6 que aparece. |
| [`evidencia/05-sem-precedente.png`](evidencia/05-sem-precedente.png) | 04 — o rótulo inédito | O elemento sem precedente: o bloco **não existe** — nem vazio, nem desabilitado (`.bloco-precedente` conta **0** no DOM). A shortlist é exatamente a de hoje, começando no primeiro cartão da cascata. |
| [`evidencia/06-lista-de-confirmacao.png`](evidencia/06-lista-de-confirmacao.png) | 03 + 06 — antes de gravar | “Antes de confirmar, o que vai ser gravado”, com os três códigos à vista, **a marca do minoritário repetida** (“em 1 das 4 praças”) porque é ali que o clique grava, e a frase que diz no mesmo fôlego que *“o fechamento do pacote continua sendo ato separado”* (decisões 4 e 5). |
| [`evidencia/07-o-aceite-recusado.png`](evidencia/07-o-aceite-recusado.png) | 03 — o ato, **recusado** | O clique em “Confirmar os 3 códigos” manda **um** pedido com os três — e o servidor responde `422`. A tela diz “Falha na API (422).” e preserva a lista à vista. Ver o achado abaixo. |
| [`evidencia/08-o-estado-de-uma-revisao-so.png`](evidencia/08-o-estado-de-uma-revisao-so.png) | 03 — o estado que o aceite produz | Os três pares do mesmo elemento confirmados numa revisão só, e o elemento **continua** em “Itens sem decisão de código” com o selo de precedente: aceitar não fechou o pacote (decisão 5). **Esta gravação não foi feita pelo navegador** — foi feita pela rota, com o mesmo corpo mais `catalog_sha256` (ver abaixo). A imagem mostra como a jornada desenha o resultado; ela não prova que a tela chega nele. |

### O defeito que a captura achou: o aceite em lote nunca gravou

O navegador enviou exatamente um pedido, e ele foi recusado:

```
POST /v1/estimate-rounds/{id}/code-assignments/decisions
{"base_version":7,"item_id":"ti_0000000000f04402","action":"confirm",
 "codes":["ZA20200100(/)","ZA20200200(B)","ZA20200300(/)"]}

422  "confirmação de código exige a fonte de preço em `catalog_sha256`"
```

A causa foi isolada fora do navegador, numa rodada própria para não mexer no estado que as
capturas mostram: o **mesmo corpo** acrescido de `catalog_sha256` é aceito e produz
exatamente **uma** revisão nova (versão 7 → 8, uma revisão com `code_assignments_json`, os
três pares `confirmed` do mesmo item). A diferença entre gravar e não gravar é um campo.

As duas metades estavam certas isoladas, e é por isso que nenhuma suíte pegou:

- **a rota** (T3a) manteve a validação que já existia para o caminho singular —
  `action == "confirm"` sem `catalog_sha256` é recusa de fronteira — e nunca a afrouxou para
  `codes`. O teste dela, `tests/api/test_precedents.py::_decide_codes`, **manda**
  `catalog_sha256` junto do lote, e por isso passa;
- **a tela** (T3b) implementou o contrato como as duas tasks o fixaram, e ele **não tem** o
  campo: `codeDecisionBody` devolve `{base_version, item_id, action, codes}` e retorna antes
  de escrever `catalog_sha256` (`apps/web/src/orcamento/requests.ts`). O teste dela,
  `apps/web/src/orcamento/precedente.test.tsx`, afirma esse corpo — sem o campo — e por isso
  também passa.

A origem é anterior às duas: **o contrato escrito nas tasks** omite `catalog_sha256` no aceite
de lote, nas duas pontas ([T3a](tasks/T3a-precedente-na-shortlist-api.md), seção “O aceite do
pacote numa revisão só”, e [T3b](tasks/T3b-precedente-na-shortlist-tela.md), seção “Contrato
de API”). O servidor implementou a regra mais
estrita, o cliente implementou o contrato, e ninguém atravessou a fronteira até esta captura.

**Não foi consertado aqui**, e não é conserto de uma linha por acidente: qual das duas pontas
está certa é decisão de contrato. A fonte de preço do lote é conhecida e única — o bloco de
precedente é montado sobre o catálogo **cabeça** da cascata (`_estimate_precedents`), e cada
código já viaja com o seu `catalog_sha256` —, de modo que tanto “a tela cita a fonte” quanto
“a rota aceita o lote sem citação, derivando-a dos códigos” produzem o mesmo resultado. Quem
escolhe é quem manda no contrato da rota.

Consequência para os critérios de aceite da T3b: o 3 (*“confirmar o pacote manda um pedido com
os N códigos, e mostra a lista antes”*) está cumprido na metade da tela — o pedido é **um** e
a lista aparece antes — e reprovado na metade do servidor. Os critérios 1, 2, 4, 5, 6 e 7
estão exercidos pelas imagens acima.

Um segundo ponto, menor e da mesma cena: a recusa chega ao usuário como **“Falha na API
(422).”** — a mensagem genérica, sem o motivo nomeado que o servidor devolveu. A rota já
manda a razão em `problem+json`; quem lê a tela não a recebe.

### O desfecho: o reparo, e a re-verificação que ele exigiu

**Data**: 2026-09-04, depois da captura acima. O registro do defeito fica como está — é ele
que explica por que a suíte inteira passava sobre um ato que nunca gravou.

**A arbitragem**: o contrato da **rota** é o que vale. Ela sempre disse que *"todos os
códigos citam a MESMA fonte, que é a que `catalog_sha256` declara"*, e o
[API Contract](../../architecture/API_CONTRACT.md) já a acompanhava (*"Entrada: `base_version`,
`item_id`, `action`, `code` **ou** `codes`, `catalog_sha256` e `note`"*). Quem divergia eram o
contrato escrito nas tasks T3a/T3b e a tela que o implementou fielmente. **A rota não mudou.**

O reparo é de tela, e são duas metades:

1. **O corpo do lote cita a fonte.** `catalog_sha256` entra no corpo do aceite em lote pelo
   mesmo caminho do singular — a exigência é da CONFIRMAÇÃO, não do formato do corpo. A fonte
   é a que `fonteDoPrecedente` já calculava para o cabeçalho do bloco, e ela agora **viaja na
   confirmação** (`ConfirmacaoDoPrecedente.catalogSha256`): uma leitura, dois usos, para que a
   tabela mostrada e a tabela gravada não possam divergir.

   A consequência de tipo é a tranca: `abrirConfirmacao` passou a receber a fonte e a devolver
   `null` sem ela, então **não existe confirmação sem citação**. E o bloco de precedente cujo
   pacote atravessa duas tabelas perde o botão de aceitar — **ausente, não desabilitado** —
   com a saída escrita (*"Confirme-os um a um pelos blocos da cascata, abaixo"*). Oferecer um
   ato que o servidor recusaria sempre era o defeito com outra causa.

   Esse caso **não tem imagem**, e a razão é a boa: ele é defensivo e o servidor não o produz —
   a API monta o precedente sobre o catálogo **cabeça** da cascata e carimba o mesmo digest em
   todo código (`shortlist_precedents`), de modo que a convergência é garantida do outro lado
   da fronteira. Quem o cobre é o teste do bloco desenhado, e o que ele afirma é o que a
   evidência não pôde: o bloco fica, o botão sai e o motivo vai escrito.

2. **A recusa nomeia o motivo.** O segundo achado tinha uma causa que a leitura de então não
   nomeou: a API responde em **dois envelopes**. As invariantes de domínio saem em
   `application/problem+json` com código estável, e a tela já as traduzia por tabela; a
   validação de **esquema** do Pydantic sai no envelope nativo do FastAPI, com `detail` como
   LISTA e sem código nenhum — e era dela que sobrava só "Falha na API (422).". O transporte
   passa a preservar os `msg` daquela lista (`CONTRACT_ERRORS_KEY`, em `apps/web/src/api.ts`),
   e a decisão de código passa a nomeá-los (`recusaDaDecisaoDeCodigo`). O `input` do envelope
   — que é o corpo do cliente — **não** volta para a tela, e a `message` do transporte não
   mudou: nenhuma outra jornada teve a copy alterada por este reparo.

#### A re-verificação, no mesmo banco e na mesma bancada

Mesma bancada, mesmo tenant sintético, e a **API servida da worktree do reparo** (8011) com a
SPA dela (5174) — o reparo é só de tela, mas nada foi servido do checkout principal.

A rodada das capturas de manhã continuou intacta (o `422` não gravou nada), e a primeira
re-verificação foi feita contra ela mesma. Rodadas novas foram semeadas em seguida pelo mesmo
`semear.py`, por duas razões declaradas: o aviso de sucesso é banner de **5 s** no topo e a
captura precisava subir até ele dentro da janela; e as imagens finais foram refeitas contra a
revisão **exatamente como commitada**, depois de a classe do bloco sem fonte única ganhar nome
próprio na folha. Todas as rodadas deram o mesmo resultado, e o ambiente foi desfeito ao fim —
o usuário sintético removido, o cliente do Keycloak devolvido às duas URIs do realm e o *user
profile* ao padrão, como na captura de manhã.

| Arquivo | O que a imagem prova |
| --- | --- |
| [`evidencia/07b-o-aceite-gravando.png`](evidencia/07b-o-aceite-gravando.png) | O mesmo clique da 07, agora **gravando**: o banner verde *"3 códigos confirmados pelo precedente, numa revisão só"*, os três pares `ti_…f04402 × ZA20200100(/) / ZA20200200(B) / ZA20200300(/)` com o selo "código confirmado" e a fonte nomeada, a rodada na **versão 8** e o `ALAMBRADO` **continuando** em "Itens sem decisão de código" com o selo de precedente — aceitar não fechou o pacote (decisão 5). É a 08 outra vez, e desta vez **feita pelo navegador**. |
| [`evidencia/07c-a-recusa-com-o-motivo.png`](evidencia/07c-a-recusa-com-o-motivo.png) | A segunda metade, exercida contra o servidor real: *"A decisão não foi gravada: o servidor recusou o formato do pedido. Motivo: Value error, confirmação de código exige a fonte de preço em `catalog_sha256`."* — onde antes se lia "Falha na API (422).". A lista de confirmação continua à vista e nada foi gravado. |

Como a 07c foi produzida, declarado: o aceite em lote **não produz mais** essa recusa sozinho
— é o que a primeira metade consertou. A cena remove `catalog_sha256` do corpo **no fio**
(`page.route`), de modo que o que chega à API é byte a byte o corpo que a tela mandava até
esta data. A adulteração é do transporte da bancada, não da tela nem da rota, e o JSON da cena
guarda os dois corpos, o original e o do fio.

O que o navegador mandou e o que o servidor respondeu:

```
POST /v1/estimate-rounds/{id}/code-assignments/decisions
{"base_version":7,"item_id":"ti_0000000000f04402","action":"confirm",
 "codes":["ZA20200100(/)","ZA20200200(B)","ZA20200300(/)"],
 "catalog_sha256":"e2710eff…0503"}

200
```

E o que o **banco** diz, que é o que decide — lido fora da tela, direto em
`estimate_round_revisions`:

```
pedidos do navegador  : 1
versão da rodada      : 7 → 8          (um passo)
revisões novas        : 1              (uma só, e é a que carrega code_assignments_json)
pares gravados        : ZA20200100(/) confirmed
                        ZA20200200(B) confirmed
                        ZA20200300(/) confirmed   — todos do mesmo item, mesma fonte
avisos na tela        : nenhum
```

**Consequência para o critério 3 da T3b**: cumprido por inteiro. O pedido é **um**, a lista
aparece antes, e o servidor grava — as três metades. Os critérios 1, 2, 4, 5, 6 e 7 continuam
exercidos pelas imagens 01–06, que o reparo não tocou.

#### O que o reparo deixou declarado, e não resolveu

1. **A frase da recusa carrega o prefixo do Pydantic** — "Value error, " antes do texto que o
   repositório escreveu. Ele é ruído do framework, não conteúdo, e apará-lo seria a tela
   editando a mensagem do servidor por uma regra sobre o formato de um framework de terceiro.
   Ficou como está, à vista: a copy desta jornada já é gate do dono do produto, e esta é uma
   decisão de texto como as outras.
2. **A confirmação de um código só (o ato singular) divide o mesmo envelope de recusa**, e
   ganhou o motivo nomeado junto — é a mesma rota, o mesmo painel e a mesma classe de recusa,
   e deixar um dos dois botões mudo seria incoerência de tela. Nenhum outro ato da jornada foi
   tocado.
3. **O clique de verdade continua sendo provado só aqui.** A suíte testa componente por SSR
   estático, sem harness de eventos (é a convenção do repositório, e trocá-la seria
   dependência nova): o teste novo exercita a composição exata da tela — payload da API →
   `blocosDaShortlist` → `fonteDoPrecedente` → `abrirConfirmacao` → `pedidoDeConfirmacao` →
   pedido assertado —, e quem prova a ligação com o evento do navegador é esta evidência.

### Divergências entre a tela e o pacote aprovado

Todas de composição, e nenhuma delas toca as oito decisões — registradas porque foram vistas,
não porque pedem conserto:

| No pacote | Na tela |
| --- | --- |
| cabeçalho do bloco com **um** selo de fonte (`SCO-RIO`) | três selos: `Precedente`, `SCO · data-base 2026-09` e `1ª fonte da cascata` — mais informação, não menos |
| “observação, não decisão” **ao lado** do botão de aceitar | na linha **abaixo** do botão |
| a nota “o código aparece duas vezes” como faixa **abaixo do painel inteiro** | **dentro** do bloco de precedente, no rodapé dele |
| bloco da cascata com cabeçalho próprio (`SCO-Rio · Out/2023 · 1ª da cascata`) | selo de fonte **por cartão**, que é como a etapa Códigos já desenhava antes desta feature (F-020) — a rendição do pacote é que estilizou uma superfície que a F-044 não altera |

### Método

O ambiente foi semeado pelas **funções do próprio teste**
(`tests/api/test_estimate_round_routes`), apontadas para o servidor real em vez do
`TestClient` — o mesmo método da [evidência da F-043](../F-043-planilha-no-gabarito-da-prefeitura/evidence.md),
com as três substituições que ela documenta (object store no floci **com `ChecksumSHA256`**,
`Database` real, e a reescrita de `_headers` porque o tenant default é avaliado na importação
do módulo). A segunda metade é nova: as quatro praças passadas entram por
`POST /v1/precedents/seed`, com `price_source` igual ao `source_sha256` do catálogo da rodada
— o índice é chaveado por (rótulo, fonte), e semear sob outra fonte produziria um precedente
que a shortlist jamais ofereceria (decisão 7).

Três ajustes de ambiente, todos porque **outra sessão ocupava a 5173 e a 8010 ao mesmo tempo**,
e nenhum deles tocou arquivo do repositório:

1. API em `127.0.0.1:8011` e SPA em `localhost:5174`, com `CROQUITO_WEB_ORIGIN` e
   `VITE_API_BASE_URL` passados **inline** no comando;
2. no Keycloak local, o cliente `croquito-web` ganhou a 5174 nos `redirectUris`/`webOrigins`
   (aditivo — a 5173 continuou valendo o tempo todo);
3. um usuário `orcamentista.f044` com `tenant_id = tenant-f044`, para que a sessão real
   ficasse num tenant próprio. Criá-lo pela API de administração exigiu ligar
   `unmanagedAttributePolicy` no *user profile* do realm: o Keycloak 26 descarta atributo não
   declarado **em silêncio**, e sem o claim a API responde `401` — o realm importado guarda o
   atributo dos três usuários locais porque o import não passa por essa validação.

Os três foram desfeitos ao fim da rodada: o cliente voltou às duas URIs do realm, o usuário
sintético foi removido e o *user profile* voltou ao padrão. O `.env.local` da raiz, o
`apps/web/.env.local` e `keycloak/croquito-realm.json` não foram editados.
