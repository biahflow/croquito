# Design Approval Package — F-033, demanda sob contrato licitado

Classification: INTERFACE_CHANGE  
Revision: 2 (a revisão 1 permanece registrada abaixo, aprovada e implementada)  
Status: Revision 2 — Pending approval  
Date: 2026-08-22  
Produced by: agente (Claude Code)

---

# Revisão 2 — o regime na abertura, e o rótulo que não mente

Status: **Pending approval**  
Data: 2026-08-22  
Artefato: [`abertura-r2.html`](abertura-r2.html)

## Por que existe uma revisão 2

Levantada por Daniel Campos em 2026-08-22, olhando a tela construída: para orçar uma praça
que **já está sob contrato licitado**, ele precisa abrir a rodada, ler no cabeçalho que ela
é "pré-licitação", e só então declarar o regime — a rodada nasce dizendo o contrário do que
ela é.

Ao apurar, o defeito é maior do que a inconveniência descrita. Na tela de lista **não existe
rodada nenhuma**, e mesmo assim o cabeçalho afirma `ORÇAMENTO-BASE · PRÉ-LICITAÇÃO` e a
faixa âmbar fala de pré-licitação. São três telas com esse texto fixo
(`OrcamentoApp.tsx:1551`, `1568`, `1587`): sem sessão, sem acesso e nenhum orçamento aberto.
Nenhuma delas tem rodada. **A tela afirma um regime sobre nada.**

A revisão 1 decidiu (decisão 4) que declarar o regime é ato próprio e "não é caixa de marcar
escondida no formulário de abertura". Esta revisão **não contradiz** aquela decisão: o que
ela rejeitou foi a caixa **escondida**. O campo proposto aqui tem o mesmo peso do Teto da
verba — rótulo, dica e o aviso da mão única antes do clique — e o painel de declarar depois
**continua existindo**, para quem abriu sem declarar.

O servidor já aceita o que se propõe: `POST /v1/estimate-rounds` recebe `pricing_regime`
opcional desde a revisão 1 (`CreateEstimateRoundRequest`). Só a tela não oferecia.

## O que a revisão 2 muda

| # | Mudança | Custo |
| --- | --- | --- |
| 1 | **Rótulo neutro sem rodada.** As três telas sem rodada usam `ORÇAMENTO-BASE`, sem sufixo, e uma faixa âmbar que não afirma momento. O sufixo (`PRÉ-LICITAÇÃO` / `DEMANDA SOB CONTRATO`) só aparece com rodada aberta. | Só tela |
| 2 | **Campo Regime na abertura**, ao lado do Teto, com a mão única dita antes do clique. | Só tela — o servidor já aceita |
| 3 | **Selo do regime no card da lista**, para distinguir as rodadas antes de abrir. | Exige `pricing_regime` na resposta de `GET /v1/estimate-rounds` — acréscimo aditivo |
| 4 | **O painel de declarar depois permanece**, com a copy ajustada para dizer que a rodada foi aberta em pré-licitação. | Só tela |

## Decisões que esta revisão carrega

1. **A tela não afirma o que não sabe.** Sem rodada não há regime, e o rótulo cala sobre
   ele. É a mesma regra da revisão 1 — "ausência não é um valor, é a falta dele" — aplicada
   ao lugar onde ela tinha sido violada.
2. **Declarar na abertura não é esconder.** O campo é visível, rotulado e carrega a
   consequência. O que a revisão 1 recusou foi a caixa discreta; o que entra aqui é o
   oposto.
3. **Dois caminhos, não dois donos.** Abrir declarando e declarar depois são o mesmo ato em
   momentos diferentes; o segundo passa a ser o caminho de correção, não o caminho único.
4. **O card diz o regime, e o silêncio também diz.** Card sem selo é rodada em
   pré-licitação. Nenhuma pastilha nova é inventada: é o mesmo selo da revisão 1, num
   terceiro lugar.

## Efeito colateral desejado

Com a rodada nascendo declarada, a cascata **nunca** está suja no instante da declaração — a
recusa `ESTIMATE_REGIME_CASCADE_DIRTY` deixa de ser alcançável pelo caminho normal. Isso
resolve, de graça, um segundo achado da mesma conversa: na aba Cascata o painel "Instalar
catálogo" está **acima** da pergunta do regime (`OrcamentoApp.tsx:2096` vs `2104`), e a
leitura natural — instalar primeiro, declarar depois — leva justamente à recusa que a
feature existe para evitar. A recusa continua implementada e testada, porque a rodada aberta
sem regime ainda pode chegar nela.

## Artefato da revisão 2

| Arquivo | O que é |
| --- | --- |
| [`abertura-r2.html`](abertura-r2.html) | A rendição autocontida da revisão 2 |
| [`r2-00-pagina-inteira.png`](r2-00-pagina-inteira.png) | Todos os estados numa imagem |
| [`r2-01-defeito-hoje.png`](r2-01-defeito-hoje.png) | O que está no ar: regime afirmado sobre nada |
| [`r2-02-rotulo-neutro.png`](r2-02-rotulo-neutro.png) | Proposto: rótulo neutro sem rodada |
| [`r2-03-abertura-com-regime.png`](r2-03-abertura-com-regime.png) | O campo Regime na abertura e o selo no card da lista |
| [`r2-04-dentro-da-rodada.png`](r2-04-dentro-da-rodada.png) | Dentro da rodada o sufixo volta — idêntico à revisão 1 |
| [`r2-05-declarar-depois.png`](r2-05-declarar-depois.png) | O painel de declarar depois, que permanece |

## O que esta aprovação NÃO cobre

- A copy final dos textos novos, que é proposta do agente.
- O nome do campo na resposta de `GET /v1/estimate-rounds` e a forma da paginação.
- Qualquer mudança de comportamento do regime: ele segue mão única, e isso é do ADR-0045.

---

# Revisão 1 — aprovada e implementada

> Governado por [design-approval](../../../engineering-os/workflows/design-approval.md). Este
> artefato é evidência para um gate humano. Não é implementação e não deve ser copiado para
> código de aplicação.
>
> O vocabulário desta tela é o que o
> [ADR-0045](../../../adr/0045-terceiro-estado-demanda-sob-contrato.md) fixou (`Accepted`,
> 2026-08-22): "demanda sob contrato" no domínio, "Sob contrato licitado" no selo.

## Registro de aprovação

| Campo | Valor |
| --- | --- |
| O que foi aprovado | a composição visual da revisão 1 — os oito estados capturados e as seis decisões listadas em "Decisões que este pacote carrega", incluindo o selo do regime como valor novo |
| Aprovado por | Daniel Campos |
| Data | 2026-08-22 |
| Revisão aprovada | 1 |
| Explicitamente **não** aprovado (na revisão 1) | o comportamento, que é do ADR-0045 e já foi aceito; a forma da recusa no servidor (código e status), que é do plano; os nomes das fontes de preço e o formato da data-base exibida. As duas questões em aberto ao final **seguem em aberto** |
| **Copy — aprovada em 2026-08-22, depois da implementação** | Daniel Campos aprovou a copy da tela construída, incluindo os três desvios registrados em "Divergências apuradas": a frase que prometia trocar de regime foi substituída, o aviso da mão única (autoral, sem contraparte no mock) entra, e a recusa fala em "fonte de outra origem" em vez de nomear EMOP. Aprovou também a mudança de veste do status da decisão na rodada **sem** regime, e a quebra de linha do cabeçalho real, que o mock não previa por não desenhar as ações de sessão |

Transcrito de decisão humana explícita de 2026-08-22, dada após a rendição e as capturas
serem entregues e abertas. Nenhum agente aprova design, inclusive o que produziu o pacote.
Aprovar esta revisão não aprova a seguinte: pacote materialmente alterado é revisão nova e
precisa de registro próprio.

## Artefato

| Arquivo | O que é |
| --- | --- |
| [`regime.html`](regime.html) | A rendição autocontida. Abre no navegador sem build, sem rede e sem servidor. |
| [`00-pagina-inteira.png`](00-pagina-inteira.png) | Todos os estados numa imagem |
| [`01-cabecalho-regime.png`](01-cabecalho-regime.png) | Cabeçalho da rodada sob o regime, com o selo |
| [`02-cascata-regime.png`](02-cascata-regime.png) | Aba Cascata sob o regime: uma fonte só |
| [`03-recusa-fonte.png`](03-recusa-fonte.png) | Recusa de fonte proibida, na instalação |
| [`04-recusa-declaracao.png`](04-recusa-declaracao.png) | Recusa de declarar o regime com cascata suja |
| [`05-candidato-aditivo.png`](05-candidato-aditivo.png) | Item rejeitado marcado como candidato a aditivo |
| [`06-sem-regime.png`](06-sem-regime.png) | Rodada sem regime — exatamente como hoje |
| [`07-declarar.png`](07-declarar.png) | O ato de declarar o regime |
| [`08-reservado.png`](08-reservado.png) | Bloco reservado, **não** entregue nesta fatia |

## Decisões que este pacote carrega

1. **O selo aparece em dois lugares, não em um.** No cabeçalho, porque o regime vale para a
   rodada inteira; e na aba Cascata, porque é ali que a regra age e ali que a recusa
   acontece. Um selo só no topo faria a recusa parecer arbitrária a quem está na aba.
2. **A recusa é frase de obra, não código.** Ela diz o que aconteceria se a fonte entrasse:
   um preço que a medição recusaria depois, sobre serviço já executado.
3. **Recusar não altera nada.** As duas telas de recusa mostram a cascata intacta e dizem
   por escrito que nada foi gravado.
4. **Declarar o regime é ato próprio**, com seletor e botão, no molde do teto da F-027 — não
   é caixa de marcar escondida no formulário de abertura.
5. **Ausência de regime não tem selo.** A tela 6 é a de hoje, sem nenhuma peça nova:
   ausência não é um valor, é a falta dele.
6. **O produto não mente sobre o que sabe.** A tela do candidato a aditivo diz que a
   orçamentista não achou código na tabela contratual — nunca que o item não existe no
   contrato. E a tela de declarar diz, por escrito, que restringir a origem não confere o
   contrato.

## Procedência de cada valor visual

Citações do sistema existente, todas da jornada do orçamento aprovada na F-020:

| Elemento | De onde vem |
| --- | --- |
| Tokens de cor, tipografia e raio | `apps/web/src/styles.css`, bloco `:root` — verbatim |
| Topbar escura, `eyebrow`, `topbar-meta` | `apps/web/src/orcamento/styles.css` |
| Aviso permanente âmbar | `.aviso-fixo`, a mesma da jornada |
| Cartão de conteúdo | `.painel` |
| Lista numerada da cascata | `.cascata` + `.item-numero` |
| Selo de origem do preço | `.selo` |
| Faixa de erro | `.app-alert` |
| Pastilha âmbar do candidato a aditivo | `.blocked` da casca, mesmas cores |

**Único valor novo, e é o que está sendo decidido:** o selo do regime — contorno claro sobre
a topbar escura (`--dark-ink` sobre `--dark-line-strong`) e sua variante para superfície
clara na aba Cascata. Nenhuma cor nova entra no sistema; o que é novo é a **forma**: um selo
de contorno, distinto dos selos preenchidos que já indicam origem de preço, porque regime da
rodada e origem de uma linha são coisas diferentes e não podem ler igual.

## Fronteira entre entregue e reservado

**Entregue nesta fatia**: telas 1 a 7 — o selo nos dois lugares, a cascata restrita, as duas
recusas, o candidato a aditivo, a rodada sem regime e o ato de declarar.

**Reservado** (tela 8, tracejada e com opacidade reduzida): amarrar a rodada a um contrato
real e conferir data-base e desconto. É a lacuna que o ADR-0045 nomeia e deixa aberta.
Torna-se real quando o orçamento passar a modelar contrato como entidade. Não é construído
aqui, e o `Out of Scope` do contrato diz o mesmo.

## O que a aprovação desta revisão NÃO cobre

- **A copy final.** Os textos são proposta do agente. Aprovação visual não é aprovação de
  texto, e estas frases carregam regra de domínio — merecem sua leitura à parte.
- **O comportamento**, que é do ADR-0045 e já foi aceito: o que a tela mostra é
  consequência, não decisão desta aprovação.
- **A forma da recusa no servidor** (código de erro, status), que é do plano.
- **Os nomes das fontes de preço** e o formato da data-base exibida.

## Divergências apuradas na implementação (2026-08-22)

Registradas aqui para que a revisão 1 não seja lida como fiel ao que foi construído. As três
caem **dentro** do que a aprovação já excluía — "a copy final" e a composição de estados que
o pacote não desenhou —, e por isso **não** reabrem o gate. Uma revisão 2 deste pacote só é
necessária se a composição visual mudar.

1. **A dica da tela 2 promete um ato que o produto recusa.** Ela diz "Trocar de regime é ato
   próprio, com o orçamento ainda em aberto". O pacote foi aprovado **antes** da decisão de
   2026-08-22 que fixou o regime como **mão única**: declarado, não volta. O servidor recusa
   com `ESTIMATE_REGIME_IRREVERSIBLE`, e manter aquela frase na tela seria prometer o que a
   API nega. A implementação a substituiu e acrescentou um aviso da mão única no painel de
   declarar — texto autoral, portanto **não aprovado**.
2. **O cabeçalho real tem uma peça que o mock omitiu.** As telas 1 e 6 desenham identidade +
   selo + aviso; o cabeçalho de verdade carrega também as ações de sessão ("Trocar de
   orçamento", "Sessão", "Sair"). Com o selo, são quatro elementos disputando a largura, e o
   bloco de identidade quebra em mais linhas do que a captura sugere. É fidelidade do mock,
   não defeito do código — mas quem comparar as duas imagens precisa saber.
3. **O status da decisão de código mudou de veste também FORA do regime.** Ele era um
   parágrafo `.topbar-meta` dentro de um painel branco: `rgba(242,244,247,.72)` sobre
   `#ffffff`, contraste de ~1,05:1 — texto efetivamente **invisível**, defeito preexistente.
   Como é justamente esse texto que passa a dizer "candidato a aditivo", deixá-lo assim
   faria o sinal nascer invisível. Virou pastilha. O texto da rodada sem regime não mudou;
   a veste, sim.

## Questões em aberto

1. O seletor de regime deve permitir **voltar** para pré-licitação depois de declarado? O
   mock mostra o seletor com as duas opções, o que sugere que sim enquanto o orçamento está
   em aberto. O ADR não decidiu isso.
2. O candidato a aditivo deve aparecer também no cabeçalho, como contador ("2 candidatos a
   aditivo"), ou só na lista de códigos? O mock mostra só na lista.
