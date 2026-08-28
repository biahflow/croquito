# Design Approval Package — F-047, o quantitativo nasce da cena aprovada

Classification: INTERFACE_CHANGE  
Revision: 1  
Status: **Pendente de aprovação humana**  
Date: 2026-08-28  
Produced by: agente (Claude Code)

> Governado por [design-approval](../../../engineering-os/workflows/design-approval.md). Este
> artefato é evidência para um gate humano. Não é implementação e não deve ser copiado para
> código de aplicação. **Nenhum agente aprova design.**
>
> O outro gate desta feature — o aceite do
> [ADR-0058](../../../adr/0058-quantitativo-derivado-do-scene-graph-e-identidade-de-elemento.md) —
> **já foi satisfeito por ato humano em 2026-08-28** (Daniel Campos), com a emenda da decisão 4
> (só `exact` e `derived` alimentam a medição) e a tolerância da decisão 6 nomeada. Este pacote
> é o gate que falta antes do planejamento: enquanto ele estiver pendente, a F-047 não sai de
> `READY_FOR_PLANNING`.

## Registro de aprovação

| Campo | Valor |
| --- | --- |
| O que se aprova | a composição visual da revisão 1 e as doze decisões listadas em "Decisões que este pacote carrega" |
| Aprovado por | _aguardando ato humano_ |
| Data | _aguardando_ |
| Revisão | 1 |
| Explicitamente **não** coberto | a copy final; os números, nomes e datas das capturas, que são sintéticos; a forma e o escopo de unicidade do `element_ref`; o agrupamento do `quantitativos.csv` quando um elemento tem várias entidades; e as decisões do ADR-0058, que são gate próprio e já aceito |

Aprovar esta revisão não aprova a seguinte: pacote materialmente alterado é revisão nova e
precisa de registro próprio.

## Artefato

| Arquivo | O que é |
| --- | --- |
| [`quantitativo-da-cena-aprovada.html`](quantitativo-da-cena-aprovada.html) | A rendição autocontida. Abre no navegador sem build, sem rede e sem servidor. |
| [`00-pagina-inteira.png`](00-pagina-inteira.png) | Os nove estados numa imagem |
| [`01-revisao-sem-identidade.png`](01-revisao-sem-identidade.png) | A revisão do croqui hoje: entidades com geometria, precisão e proveniência — e sem identidade de elemento |
| [`02-proposta-do-sistema.png`](02-proposta-do-sistema.png) | O agrupamento proposto pelo sistema, nascendo `unresolved`, inclusive uma proposta errada |
| [`03-ato-de-declarar.png`](03-ato-de-declarar.png) | O ato humano de declarar a identidade, com autor e instante carimbados |
| [`04-aproximada-nao-alimenta.png`](04-aproximada-nao-alimenta.png) | Elemento `approximate` marcado como não alimenta, com o motivo escrito; a legenda segue como fonte |
| [`05-quantidade-da-cena.png`](05-quantidade-da-cena.png) | O item com `source = scene_graph`: origem visível, sem campo digitável, e a cadeia N:N |
| [`06-divergencia.png`](06-divergencia.png) | Os dois números lado a lado, a tolerância nomeada, a issue aberta e o item bloqueado |
| [`07-resolucao-humana.png`](07-resolucao-humana.png) | A resolução como decisão humana registrada, com o número preterido ainda gravado |
| [`08-sem-par.png`](08-sem-par.png) | Sem identidade dos dois lados: "nenhum par", incluindo o caso de número igual que não casa |
| [`09-controle.png`](09-controle.png) | O controle: croqui e medição sem identidade declarada, idênticos aos de hoje |

Capturas em 1280 px de largura, `deviceScaleFactor` 2, Chromium — a mesma proporção das do
pacote da F-040.

### Os números, e por que eles fecham

A obra é a **Praça do Cedro**, fixture **sintética inventada para este pacote**: nenhum nome,
número ou documento de cliente aparece aqui. Os números são aritmeticamente consistentes,
porque um pacote de design de produto de dinheiro que mostra conta errada ensina a conta errada:

| Elemento | Un | Cena | Legenda | Diferença | 1% | Tolerância | Resultado |
| --- | --- | --- | --- | --- | --- | --- | --- |
| EL-001 Piso em concreto | m² | 418,12 | 418,12 | 0,00 | 4,1812 | 4,1812 | casou |
| EL-002 Meio-fio | m | 242,40 | 240,00 | 2,40 | 2,4000 | 2,4000 | **borda exata de 1%** — não abre |
| EL-003 Alambrado | m | 401,55 | 385,00 | 16,55 | 3,8500 | 3,8500 | abre issue (4,30%) |
| EL-004 Grelha 0,90 × 0,90 | m² | 0,81 | 0,80 | 0,01 | 0,0080 | 0,0100 | **0,01 > 1%** — o piso segura |
| EL-005 Canteiro gramado | m² | 96,40 | 92,00 | — | — | — | cena `approximate`: não alimenta, não compara |

Outras contas da página: a proposta errada do estado 02 soma `401,55 + 160,35 = 561,90`; a
grelha do EL-004 é `0,90 × 0,90 = 0,81`; e o dinheiro do estado 05 é
`418,12 × 96,50 = 40.348,58`, `418,12 × 22,50 = 9.407,70`, soma `49.756,28`.

## Decisões que este pacote carrega

1. **A identidade de elemento é um terceiro campo, ao lado do `entity_id` e do texto livre —
   nunca no lugar de nenhum dos dois.** O estado 01 mostra por que: `entity_id` é identidade de
   linha e muda quando a aprovação cria revisão nova, `layer` é vocabulário de CAD, e o rótulo é
   uma entidade `TEXT` que o `quantitativos.csv` descarta. O estado 03 mostra o campo novo
   convivendo com os dois. É a **decisão 1 do ADR-0058**, e a mesma escolha que o ADR-0053 fez
   ao manter `label` ao lado de `source_item_id`.

2. **A proposta do sistema aparece como proposta, e se parece com uma.** Traço tracejado, selo
   `⚙ proposta · unresolved`, o motivo do agrupamento escrito na linha, e três botões que
   incluem "descartar". É a **decisão 2 do ADR-0058** tornada visível: o sistema propõe, o humano
   declara.

3. **Uma das três propostas do estado 02 está errada de propósito**, e ela agrupa dois
   alambrados distintos porque a camada é a mesma. Foi desenhada assim para que o pacote mostre
   o custo da alternativa rejeitada no ADR ("camada + rótulo como identidade automática") em vez
   de descrevê-lo: aceitá-la somaria 561,90 m onde há 401,55 m e 160,35 m.

4. **Autor e instante são carimbados pelo sistema; o rótulo é de quem declara.** O carimbo do
   estado 03 tem borda esquerda de 3 px e diz quem, quando e sobre qual revisão da cena. A
   declaração não se apaga — corrigir é retificar, o mesmo padrão que a decisão de leitura já
   tem na revisão. Deriva da **decisão 2 do ADR-0058** e do padrão de `HumanDecision` do
   produto.

5. **`approximate` não alimenta a medição, e o motivo está na tela.** O estado 04 escreve, no
   lugar onde a pessoa está: aproximação multiplicada por preço unitário vira uma linha de R$
   que ninguém lê como aproximada. É a **decisão 4 do ADR-0058 na redação emendada pelo aceite
   humano de 2026-08-28** — a proposta original admitia `approximate` sob aceite explícito, e o
   aceite recusou. Nesse caso a legenda segue sendo a fonte, com a cena visível e carimbada ao
   lado.

6. **Cena aproximada não abre divergência.** Se ela não pode ser fonte, comparar os dois números
   produziria uma issue sem decisão possível. É leitura das **decisões 4 e 6 combinadas**, e está
   escrita no estado 04 e na última linha da tabela do estado 06.

7. **No item alimentado pela cena não existe campo de quantidade.** A origem ocupa o lugar do
   `input`; "Editar quantidade" fica desabilitado e **visível**, com a razão ao lado, para que a
   ausência seja lida como decisão e não como falta. Decorre das **decisões 5 e 7 do ADR-0058**:
   a redigitação era onde o erro entrava, e o jeito de eliminá-la é não oferecer o teclado.

8. **A divergência mostra três blocos — cena, legenda, diferença — e a conta da tolerância por
   extenso.** Cada bloco carrega a origem escrita, a precisão e o número; a tolerância aparece
   como fórmula (`maior entre 1% da legenda e 0,01 na unidade`) e como resultado. É a **decisão 6
   do ADR-0058**, com a tolerância que o aceite humano nomeou.

9. **A borda da tolerância não abre issue.** O ADR diz que a issue abre quando a diferença
   *passa* da tolerância; este pacote lê "passa" como estritamente maior, e o EL-002 mostra o
   caso com 2,40 contra 2,40. **É uma leitura, não um fato** — está aqui separada das demais
   porque é exatamente o tipo de coisa que o gate humano existe para confirmar ou inverter.

10. **Sem par, a tela diz de que lado falta a identidade.** O estado 08 mostra três ausências e
    o caso em que os dois números são `418,12` e mesmo assim não casam. "Não encontrado" sem lado
    manda a pessoa procurar nos dois. É a **decisão 5 do ADR-0058** e a rejeição central do ADR
    (casamento por proximidade, por número ou por rótulo).

11. **Resolver a divergência não apaga nada, e "nenhuma das duas" fica indisponível.** O estado
    07 registra a escolha com motivo obrigatório, autor e instante, e mantém o número preterido
    gravado. A terceira opção aparece desabilitada com a razão escrita: digitar uma terceira
    quantidade ali seria a redigitação que a feature existe para eliminar. É a **decisão 6 do
    ADR-0058** — a divergência recusa e explica, não concilia sozinha.

12. **Sem identidade declarada, as duas telas são as de hoje.** O estado 09 é o controle: a lista
    de entidades sem etiqueta de elemento, o campo de quantidade digitado como está hoje, e o
    `quantitativos.csv` sem a coluna nova. É a **decisão 8 do ADR-0058**, e é o que torna os oito
    estados anteriores auditáveis.

## Fronteira entre entregue e reservado

**Entregue nesta feature:** os nove estados — a revisão sem identidade, a proposta do sistema, o
ato de declarar, a barreira da precisão, a quantidade chegando à medição sem digitação, a
divergência com a tolerância nomeada, a resolução humana, a ausência de par e o controle.

**Fatia em aberto, desenhada por inteiro** (marcada no estado 02): a **proposta assistida de
agrupamento**. Se ela entra nesta feature ou numa seguinte é decisão do plano — a F-047 registra
isso em *Unknowns*. Os estados 01 e 03 a 09 não dependem dela: sem proposta, o ato do estado 03
começa pela seleção manual das entidades. Ela torna o ato barato; não o torna correto.

**Reservado, desenhado para segurar lugar** (hachurado no estado 07): **retraçar o elemento sem
sair da medição** — o retorno à revisão do croqui a partir da divergência. Vira real quando
existir a ida e volta entre as duas jornadas dentro da mesma rodada; hoje o caminho é a jornada
do croqui, e o lugar do controle já está modelado para recebê-lo.

## O que a aprovação não cobre

- A **copy final** de rótulos, avisos e mensagens de recusa.
- Os **números, nomes e datas** das capturas, que são sintéticos (Praça do Cedro é fixture
  inventada; Ana Beatriz Rangel é nome de fixture).
- A **forma do `element_ref`** (string declarada, id opaco cunhado no ato) e o **escopo da sua
  unicidade** (cena, job ou praça). O pacote mostra `EL-001` por ser legível na tela; a
  composição não muda se ele for um UUID. É decisão do plano, e está declarada como tal no
  estado 03.
- Como o **`quantitativos.csv` agrupa** quando um elemento tem várias entidades — soma numa
  linha, ou uma linha por elemento com as parcelas. O pacote mostra uma linha por entidade com a
  coluna `element_ref` à frente, que é a forma aditiva mínima; a agregação é decisão do plano,
  junto com o [DXF_OUTPUT_SPEC](../../../architecture/DXF_OUTPUT_SPEC.md).
- A **chave `(plate_id, item_id)`** que a [F-046](../../F-046-praca-de-varias-pranchas/feature.md)
  introduz no item de takeoff. Este pacote desenha um item por praça de uma prancha só; a
  dependência já está declarada na F-047.
- O **ciclo de vida da issue de divergência** no resto do produto (onde ela aparece na lista de
  pendências, se notifica, se some do painel ao fechar).
- A **reconciliação retroativa** de croquis já exportados sem identidade, que a F-047 põe fora
  de escopo.
- O **layout impresso** do MAPÃO e do boletim, que seguem o modelo da prefeitura.

## Proveniência de cada valor visual

| Valor | De onde vem |
| --- | --- |
| `--bg`, `--surface`, `--surface-subtle`, `--surface-sunken`, `--ink`, `--ink-secondary`, `--muted`, `--line`, `--accent*` | `apps/web/src/styles.css` — identidade "Grafite técnico" |
| Vermelho `#a33d32` da recusa e âmbar `#7c5210` do aviso | Já em uso nas duas jornadas |
| Verde `--accent-soft`/`--accent-text`/`--accent-line` do selo de confirmado | Já em uso |
| Traço da precisão — cheio 3 px (exata), fino 1,5 px (derivada), tracejado 7 5 (aproximada), pontilhado 1 5 em `--muted` (não resolvida) | `apps/web/src/styles.css`, regras `.cena-forma.precisao-*` do preview da cena, reproduzidas sem alteração |
| Pílula do selo (`border-radius: 999px`), tabela com cabeçalho em versalete e números tabulares | Padrão já usado nas duas jornadas (`.selo`, `.tabela`, `.numero`) |
| `dl.procedencia` de pares rótulo/valor | Padrão `.procedencia` da medição — dado lido, nunca digitado |
| Carimbo com borda esquerda de 3 px | Introduzido pelo pacote da [F-040](../../F-040-re-ra-e-medicao-seguinte/mock/README.md), reaproveitado aqui sem alteração |
| Bloco hachurado do reservado | Introduzido pelo pacote da F-040, reaproveitado sem alteração |
| **NOVO** — família `--cena` (`#2b5ea8`, `-soft`, `-line`, `-ink`) para a origem "cena aprovada" | Introduzida por este pacote. A origem nova precisa de identidade visual estável nas duas jornadas, e nenhuma família existente significa "geometria aprovada": verde é contratado/confirmado, roxo é reajustado (F-039), petróleo é re-ratificado (F-040), âmbar é atenção, vermelho é recusa. A **legenda lida permanece neutra de propósito** — ela é o que já existe, e a cor nova marca o que a feature acrescenta. |
| **NOVO** — a etiqueta `.elemento` (monoespaçada, glifo `◇`, cantos de 4 px) | Introduzida por este pacote. `element_ref` não pode se confundir com o rótulo humano nem com o `entity_id`; a forma quadrada e monoespaçada a separa das pílulas de selo. A variante ausente é tracejada e diz "— sem identidade" por escrito. |
| **NOVO** — o bloco `.duplo` dos dois números lado a lado | Introduzido por este pacote. É composição, não cor: três colunas de peso igual — cena, legenda, diferença —, cada uma com a origem escrita, para que nenhuma pareça a principal. |
| **NOVO** — o bloco `.bloqueado` (borda esquerda âmbar de 3 px) do item que não fecha | Introduzido por este pacote, reusando o âmbar `--atencao` já em uso. O bloqueio é diagnóstico, não recusa: por isso âmbar e não vermelho. |

Nenhum valor visual deste pacote depende só de cor. Precisão é traço **e** palavra; divergência é
glifo `⚠`, borda esquerda **e** texto; proposta é traço tracejado **e** o selo escrito
`⚙ proposta · unresolved`; ausência de par é a palavra "não resolve" **e** a mensagem que diz de
que lado falta a identidade.
