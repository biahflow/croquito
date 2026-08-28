# Design Approval Package — F-046, A praça de várias pranchas

Classification: INTERFACE_CHANGE  
Revision: 1  
Status: **Approved (2026-08-28)**  
Date: 2026-08-28  
Produced by: agente (Claude Code)

> Governado por [design-approval](../../../engineering-os/workflows/design-approval.md). Este
> artefato é evidência para um gate humano. Não é implementação e não deve ser copiado para
> código de aplicação. **Nenhum agente aprova design.**
>
> O outro gate desta feature, o aceite do
> [ADR-0057](../../../adr/0057-multiplas-pranchas-por-praca-na-extracao-de-legenda.md), já
> **foi satisfeito em 2026-08-28** (Daniel Campos). Este pacote **foi aprovado por ato humano em
> 2026-08-28** (Daniel Campos), inclusive a decisão 9 — "a parcela que fica" —, que nasceu ao
> desenhar e não estava no ADR. Com os dois gates passados, a F-046 entra em planejamento.

## Registro de aprovação

| Campo | Valor |
| --- | --- |
| O que se aprova | a composição visual da revisão 1 e as treze decisões listadas em "Decisões que este pacote carrega" |
| Aprovado por | Daniel Campos |
| Data | 2026-08-28 |
| Revisão | 1 |
| Explicitamente **não** coberto | ver "O que a aprovação não cobre", abaixo |

Aprovar esta revisão não aprova a seguinte: pacote materialmente alterado é revisão nova e
precisa de registro próprio.

## Artefato

| Arquivo | O que é |
| --- | --- |
| [`praca-de-varias-pranchas.html`](praca-de-varias-pranchas.html) | A rendição autocontida. Abre no navegador sem build, sem rede e sem servidor. |
| [`00-pagina-inteira.png`](00-pagina-inteira.png) | Os nove estados numa imagem |
| [`01-a-praca-e-suas-folhas.png`](01-a-praca-e-suas-folhas.png) | A praça com suas folhas: quais são, qual está em foco, o estado de cada uma |
| [`02-acrescentar-uma-folha.png`](02-acrescentar-uma-folha.png) | O ato de acrescentar folha: seleção de páginas em lote, nada marcado por padrão |
| [`03-a-folha-em-revisao.png`](03-a-folha-em-revisao.png) | A folha em revisão, com overlay **por folha** e o cabeçalho "folha 2 de 3" |
| [`04-o-consolidado-da-praca.png`](04-o-consolidado-da-praca.png) | O consolidado: total por código, parcelas por folha na memória, boletim por folha |
| [`05-item-repetido-conta-duas-vezes.png`](05-item-repetido-conta-duas-vezes.png) | O item repetido entre folhas contando duas vezes, com o aviso e a colisão de `item_id` |
| [`06-declarar-a-identidade.png`](06-declarar-a-identidade.png) | A declaração par a par, com nota, e a prévia do efeito no total antes de gravar |
| [`07-depois-da-declaracao.png`](07-depois-da-declaracao.png) | A fusão na memória, carimbada com autor e instante |
| [`08-recusas.png`](08-recusas.png) | Três recusas e um aviso |
| [`09-praca-de-uma-folha.png`](09-praca-de-uma-folha.png) | O controle: praça de uma folha só, idêntica ao que existe hoje |

### A obra e os números

Obra **sintética**: Praça Nova Aurora (`PR-NOVA-AURORA`), três folhas — planta geral, detalhe do
playground, corte e muro de arrimo. Nenhum dado de cliente aparece no pacote.

Os números são sintéticos, mas **aritmeticamente consistentes**, e cada soma aparece escrita ao
lado do resultado que ela produz. Conferidas uma a uma:

- piso, `PJ05100100(/)`: `320,00 + 64,50 + 27,40 = 411,90` · `411,90 × 48,90 = 20.141,91`
- alambrado, `PJ14100500(/)`, antes da declaração: `186,00 + 186,00 = 372,00` ·
  `372,00 × 62,40 = 23.212,80`; depois: `186,00 × 62,40 = 11.606,40`
- portão, `PJ25400100(B)`: `12,60 + 6,30 = 18,90` · `18,90 × 96,00 = 1.814,40`
- bancos, `PJ11200300(A)`: `8 + 3 = 11` · `11 × 385,00 = 4.235,00`
- total da praça antes: `20.141,91 + 23.212,80 + 1.814,40 + 4.235,00 = 49.404,11`
- total da praça depois: `20.141,91 + 11.606,40 + 1.814,40 + 4.235,00 = 37.797,71`
- efeito da declaração: `49.404,11 − 11.606,40 = 37.797,71`
- pelas folhas, antes: `31.544,00 + 15.915,45 + 1.944,66 = 49.404,11`
- pelas folhas, depois: `31.544,00 + 4.309,05 + 1.944,66 = 37.797,71` — só a folha 2 muda,
  porque foi dela a parcela fundida

A soma por código e a soma por folha dão o mesmo total, nos dois momentos, e as duas ficam na
tela. Um pacote de design de produto de dinheiro que mostra conta errada ensina a conta errada.

### Uma advertência de leitura

Os estados **01**, **02**, **03** e **08** mostram a rodada **em andamento** — folha 2 pendente
de revisão, folha 3 em extração. Os estados **04** a **07** mostram a mesma praça **depois** de
as três folhas estarem revisadas, porque o consolidado não existe antes disso (decisão 7 do
ADR-0057). O estado **09** é outra rodada: a praça de uma folha só.

## Decisões que este pacote carrega

1. **A faixa de folhas é uma lista, não um explorador de arquivos**, e a etapa `Prancha` vira
   `Pranchas`. Cada folha é um cartão com nome, `plate_id`, estado por extenso e contagem de
   itens; a folha em foco traz a marca `▸ em foco` e a barra à esquerda. Uma árvore de arquivos
   convidaria a pensar em páginas de PDF, e a praça não é um arquivo — é o conjunto de folhas que
   a orçamentista declarou. *(ADR-0057, decisão 2.)*

2. **A praça ganha uma etapa própria, entre `Códigos` e `Boletim`.** É onde o total por código, a
   memória com as parcelas por folha e o ato de declarar identidade moram. O ADR-0057 registra
   como consequência negativa que "a revisão fica em dois níveis […] e a UI precisa tornar
   visível qual dos dois o orçamentista está fazendo": a separação por etapa é a resposta a essa
   consequência — confirmar código é na folha, fechar a praça é na praça. *(ADR-0057, decisões 2
   e 6.)*

3. **Promover páginas é ato em lote, com seleção explícita e nada marcado por padrão.** Resolve o
   terceiro `Unknown` do Feature Contract: a seleção é em lote (marcar as três páginas de uma
   vez), a confirmação é uma só, e o botão diz quantas folhas serão acrescentadas. Um ato por
   página faria a praça de seis folhas custar seis idas ao mesmo diálogo; promoção automática de
   todas as páginas encheria a praça de quadro de áreas e carimbo. *(Feature Contract, escopo 2.)*

4. **O número de extrações pagas fica escrito no próprio botão** ("Acrescentar 3 folhas à
   praça"), e repetido no aviso ao lado. É a mitigação do risco "custo de extração multiplicar
   por folha sem o usuário perceber": o custo por folha não pode aparecer só na fatura.
   *(Feature Contract, tabela de riscos.)*

5. **O cabeçalho da revisão diz "folha 2 de 3", e o overlay é da folha.** O painel da prancha
   afirma por escrito que **não existe overlay da praça**: cada retângulo está em pixels da
   imagem daquela folha, conferida pelo digest dela. O consolidado endereça os overlays das suas
   folhas; ele não desenha nada. *(ADR-0057, decisão 3.)*

6. **Todo item mostra a chave inteira `(plate_id, item_id)`, não só o número da lista.** O número
   é da ordem na tela e muda; a chave é o que atravessa a praça. O estado 05 mostra o caso que
   torna isso obrigatório: o piso da folha 2 e os bancos da folha 1 cunharam o **mesmo**
   `ti_7e04ab13c65f9d28` em pacotes diferentes, e não são o mesmo item. *(ADR-0057, decisão 5.)*

7. **A dupla contagem aparece como duas parcelas nomeadas, não como um erro.** O total é
   `372,00` porque foram duas leituras, de duas folhas; o aviso âmbar explica isso e diz que só
   uma declaração humana funde. O sistema erra para o lado de somar demais, visivelmente — contar
   de menos é um erro que ninguém vê. *(ADR-0057, decisão 4.)*

8. **O par a declarar é escolhido explicitamente, um item de cada folha, e nenhuma sugestão é
   feita.** A lista só oferece itens de **outras** folhas, nada vem pré-selecionado, e não há
   ranking por rótulo, unidade ou posição. O estado 08 mostra a recusa de vínculo entre itens da
   mesma folha. A fusão automática por semelhança foi recusada nominalmente no aceite.
   *(ADR-0057, decisão 4, e a alternativa recusada.)*

9. **O vínculo escolhe qual leitura fica.** A declaração tem um campo "a parcela que fica": a
   leitura escolhida governa a quantidade e é a folha que a memória cita; a descartada continua
   escrita na memória, com sua quantidade, marcada como "fundida, não contribui". Sem essa
   escolha, uma parcela fundida ficaria sem folha de origem — e parcela sem evidência é
   exatamente o que este contexto recusa. Quando as duas leituras divergirem em quantidade, a
   escolhida governa o número e a diferença fica visível. **Esta decisão nasceu ao desenhar o
   pacote**: o ADR-0057 diz que a fusão "colapsa as duas leituras numa contribuição só", e o mock
   expôs que a memória precisa saber de qual folha essa contribuição veio.

10. **A nota é obrigatória; autor e instante são carimbados pelo sistema.** É o mesmo idioma do
    ato declarado do reajuste (F-039) e da RE-RA (F-040). Sem o motivo escrito, quem audita meses
    depois vê um número menor sem saber por quê. *(ADR-0057, decisão 4.)*

11. **A prévia mostra o total antes e depois, antes de gravar**, e diz que nenhum outro código se
    move. É a declaração que muda o total, então é antes de gravá-la que o total novo precisa ser
    visto. Mesma disciplina da prévia da F-040. *(ADR-0057, decisão 4.)*

12. **A recusa nomeia a folha.** O boletim bloqueado diz "folha 2 de 3 — Detalhe do playground
    (`nova-aurora-detalhe-playground`) tem 2 itens sem decisão" e "folha 3 de 3 […] ainda está em
    extração". Meia praça somada parece uma praça inteira; a recusa tem que dizer qual metade
    falta. *(ADR-0057, decisão 7; Feature Contract, AC 8.)*

13. **Com uma folha só, nada disso aparece.** Sem faixa de folhas, sem "folha 1 de 1", sem etapa
    `Praça`, sem coluna de parcelas, sem chave `(plate_id, item_id)` na lista e sem o ato de
    declarar identidade. A etapa continua se chamando `Prancha`, no singular. O plural e a faixa
    nascem no momento em que a segunda folha é acrescentada. *(ADR-0057, decisão 8; Feature
    Contract, AC 3.)*

## Proveniência de cada valor visual

| Valor | De onde vem |
| --- | --- |
| `--bg`, `--surface`, `--surface-subtle`, `--surface-sunken`, `--ink`, `--ink-secondary`, `--muted`, `--line`, `--accent*` | `apps/web/src/styles.css` — identidade "Grafite técnico" |
| Âmbar `#b47512` / `#fbe6c2` / `#6b3a06` do item **proposto** | `apps/web/src/medicao/styles.css` — já em uso na revisão do takeoff |
| Vermelho `#a02323` / `#f7d9d9` / `#7a1212` do item **ambíguo** | `apps/web/src/medicao/styles.css` — já em uso |
| Cinza `#5a625c` do item **rejeitado** | `apps/web/src/medicao/styles.css` — já em uso |
| Verde `--accent-soft` / `--accent-text` do item **confirmado** e do selo de folha revisada | Já em uso nas duas jornadas |
| Vermelho `#a33d32` da recusa e âmbar `#7c5210` do aviso | Já em uso nas duas jornadas |
| Faixa de etapas (`nav.etapas`, pílulas com estado por extenso) | `apps/web/src/medicao/MedicaoApp.tsx` — a navegação de hoje |
| Lista de itens com número, rótulo, estado por extenso e barra colorida à esquerda | `apps/web/src/medicao/styles.css` (`.itens`, `.item-*`) — a lista de hoje |
| Barra da prancha com "Mostrar/Ocultar marcações" e o zoom em `1,00×` | `apps/web/src/medicao/MedicaoApp.tsx` — os controles de hoje |
| Tabela, cabeçalho em versalete e números tabulares | Padrão já usado nas telas de medição e orçamento |
| Carimbo de declaração (borda esquerda de 3 px) e o hachurado do "reservado" | Introduzidos pelo pacote da [F-040](../../F-040-re-ra-e-medicao-seguinte/mock/README.md), reaproveitados aqui sem alteração |
| **NOVO** — índigo `#3b4a94` e a família `--praca*` (`--praca-soft` `#eef0fa`, `--praca-line` `#c3c8e8`, `--praca-ink` `#242c66`) | Introduzido por este pacote, para o consolidado da praça e para o vínculo de identidade que só existe nele. Escolhido por ser o matiz livre na medição: verde = contratado/confirmado, âmbar = proposto/aviso, vermelho = ambíguo/recusa, cinza = rejeitado, roxo `#6b4ba1` = reajustado (F-039), petróleo `#1f6f7a` = re-ratificado (F-040). Uma família só para as duas coisas, porque são o mesmo território novo. |
| **NOVO** — o cartão de folha (`.folha-chip`) com marca `▸ em foco` e barra esquerda de 4 px | Introduzido por este pacote |
| **NOVO** — os símbolos de estado da folha: `✓` extraída e revisada, `▲` pendente de revisão, `◐` em extração | Introduzidos por este pacote. Cada estado tem símbolo próprio **e** texto por extenso: a cor nunca é o único indicador. |
| **NOVO** — o sinal `≡` de identidade declarada e o par lado a lado da declaração | Introduzidos por este pacote |

Índigo e roxo são vizinhos no matiz. Neste pacote eles nunca aparecem juntos — roxo é do
reajuste e não há reajuste aqui —, e cada um vem sempre com o significado escrito ao lado. Se um
dia a mesma tela precisar mostrar reajuste e praça ao mesmo tempo, a distinção entre os dois
precisa ser reavaliada; é uma dívida declarada, não um descuido.

## Fronteira entre entregue e reservado

**Entregue nesta feature:** os nove estados — a praça e suas folhas, o ato de acrescentar folha,
a folha em revisão com overlay próprio, o consolidado com memória por folha, a dupla contagem
visível, a declaração de identidade com prévia, a fusão carimbada na memória, as recusas e o
controle de uma folha só.

**Reservado, desenhado para segurar lugar** (hachurado):

- **Reordenar e renomear as folhas** (estado 02). Vira real quando a praça passar de meia dúzia
  de folhas; até lá a ordem é a de acréscimo.
- **Desfazer um vínculo de identidade já declarado** (estado 06). Vira real quando o desfazer da
  F-045 for estendido ao consolidado da praça.

## O que a aprovação não cobre

- A **copy final** de rótulos, avisos e mensagens de recusa.
- Os **números, nomes e datas** das capturas, que são sintéticos.
- Os **nomes dos erros de domínio** citados no estado 08 (`WORKSITE_TAKEOFF_PLATE_PENDING`,
  `WORKSITE_LINK_SAME_PLATE`, `WORKSITE_LINK_INCOMPLETE`), que são **propostos** aqui e se
  confirmam no plano — nenhum deles existe hoje.
- Se a praça reaproveita `worksite_key` como chave ou se o consolidado precisa de id próprio —
  primeiro `Unknown` do Feature Contract, que o próprio contrato manda decidir **no plano**.
- O **nome final do artefato** (`WorksiteTakeoff`) e o do tipo do vínculo, que o ADR-0057 deixa
  provisórios.
- O **layout impresso** do boletim e da planilha da praça, que seguem o modelo da prefeitura —
  este pacote decide o que aparece na tela, não a diagramação do `.xlsx` exportado.
- O **alinhamento geométrico entre folhas**, que o Feature Contract já põe fora de escopo.
- **Multi-praça numa rodada só**, também fora de escopo.
- As decisões do **ADR-0057**, que são gate próprio e já foi satisfeito em 2026-08-28.
