# Design Approval Package — F-040, RE-RA declarada e a medição seguinte

Classification: INTERFACE_CHANGE  
Revision: 1  
Status: **Approved (2026-08-27)**  
Date: 2026-08-27  
Produced by: agente (Claude Code)

> Governado por [design-approval](../../../engineering-os/workflows/design-approval.md). Este
> artefato é evidência para um gate humano. Não é implementação e não deve ser copiado para
> código de aplicação. **Nenhum agente aprova design.**
>
> O outro gate desta feature é o
> [ADR-0056](../../../adr/0056-re-ra-declarada-e-o-consolidado-da-medicao-seguinte.md).
> **Aprovado por ato humano em 2026-08-27** (Daniel Campos), junto com o aceite do ADR-0056
> na mesma data; com os dois gates humanos passados, a feature sai de `READY_FOR_PLANNING`
> para planejamento e construção.

## Registro de aprovação

| Campo | Valor |
| --- | --- |
| O que se aprova | a composição visual da revisão 1 e as nove decisões listadas em "Decisões que este pacote carrega" |
| Aprovado por | Daniel Campos |
| Data | 2026-08-27 |
| Revisão | 1 |
| Explicitamente **não** coberto | a copy final; os números, nomes e datas das capturas, que são sintéticos; o layout impresso do MAPÃO e do boletim, que seguem o modelo da prefeitura; e as decisões do ADR-0056, que são gate próprio |

Aprovar esta revisão não aprova a seguinte: pacote materialmente alterado é revisão nova e
precisa de registro próprio.

## Artefato

| Arquivo | O que é |
| --- | --- |
| [`re-ra-e-medicao-seguinte.html`](re-ra-e-medicao-seguinte.html) | A rendição autocontida. Abre no navegador sem build, sem rede e sem servidor. |
| [`00-pagina-inteira.png`](00-pagina-inteira.png) | Os oito estados numa imagem |
| [`01-duas-portas.png`](01-duas-portas.png) | Abertura: primeira medição ou medição seguinte, e a rodada anterior aprovada |
| [`02-heranca-da-anterior.png`](02-heranca-da-anterior.png) | O que vem da rodada anterior: períodos, acumulado, saldo |
| [`03-declarar-a-re-ra.png`](03-declarar-a-re-ra.png) | A declaração: identificação, citação da publicação, deltas e item novo |
| [`04-previa-antes-de-gravar.png`](04-previa-antes-de-gravar.png) | Contratado → RE-RA → vigente → saldo novo, antes de gravar |
| [`05-item-novo-e-o-fator.png`](05-item-novo-e-o-fator.png) | Item novo não recebe o fator do período em que não existia |
| [`06-memoria-com-a-declaracao.png`](06-memoria-com-a-declaracao.png) | A memória com a conta e a declaração carimbada |
| [`07-sem-re-ra.png`](07-sem-re-ra.png) | O controle: medição seguinte sem declaração |
| [`08-recusas.png`](08-recusas.png) | Cinco recusas e um aviso |

Os números são sintéticos, mas **aritmeticamente consistentes**: `240,00 × 62,40 = 14.976,00`,
`240,00 × 148,20 = 35.568,00`, soma `50.544,00`; `783,86 + 120,00 = 903,86` e
`903,86 − 240,00 = 663,86` de saldo; `62,40 × 1,0432 = 65,0956…` truncado em `65,09`. Um
pacote de design de produto de dinheiro que mostra conta errada ensina a conta errada.

A obra é o Campo do Toca, com os dois códigos do alambrado sobre a mesma área — o par que o
[ADR-0053](../../../adr/0053-cardinalidade-n-n-elemento-servico.md) documenta a partir do
arquivo real.

## Decisões que este pacote carrega

1. **A medição seguinte é uma das duas portas da abertura, não uma tela separada.** As duas
   aparecem juntas, como escolha única, porque a pergunta é a mesma — de onde vem o contratado
   desta medição. Esconder a segunda atrás de outro caminho faria a continuação da obra parecer
   exceção, e ela é o caso normal a partir do segundo mês.

2. **O período não é digitado.** Ele é calculado da rodada anterior e mostrado. Período que se
   escolhe à mão abre espaço para pular um ou repetir um, e o consolidado seria recusado depois
   por `PERIOD_NOT_SEQUENTIAL` — tarde, e sem dizer o que fazer.

3. **A rodada anterior aparece com o selo de aprovada, e a não aprovada não entra na lista.** É
   a tradução visual da decisão 5 do ADR-0056: o motivo de a rodada não estar disponível é dito
   no lugar onde ela seria escolhida, não depois da tentativa.

4. **A herança é mostrada antes de qualquer declaração** (estado 02). A pessoa vê o que vem da
   rodada anterior — contratado, vigente, medido, acumulado, saldo — antes de mexer em
   qualquer coisa. Sem RE-RA, contratado e vigente repetem o mesmo número **de propósito**, para
   que a diferença apareça quando existir.

5. **Autor e instante são carimbados, e a citação é digitada.** Quem declarou e quando são do
   sistema; o diário oficial e o processo são de quem declara. É a mesma mitigação da F-039 para
   o número digitado: o sistema não confere o teor da publicação — não tem como —, mas exige que
   a declaração **aponte** para ela.

6. **A prévia mostra o efeito código a código antes de gravar** (estado 04), e o vigente
   aparece como resultado de uma conta visível. **Não existe campo onde escrever `903,86`** —
   existe o `+120,00` que o produz. É a decisão 3 do ADR-0056 tornada impossível de contornar
   pela interface.

7. **O item novo declara de onde vieram descrição, unidade e preço.** Ele não estava no
   contrato, então é resolvido no catálogo contratual instalado e materializado na declaração.
   Esta decisão **nasceu ao desenhar este pacote**: o mock expôs que `AMENDMENT_NEW_ITEM_INVALID`
   exige uma linha zerada preexistente, que a planilha da prefeitura fornece e um consolidado
   vindo do orçamento assinado não tem. Virou a decisão 7 do ADR-0056.

8. **O item novo mostra que não recebe o fator do período em que não existia** (estado 05). É a
   decisão 9 do ADR-0055, que era regra escrita e agora é coisa que se vê: duas linhas
   reajustadas com o fator ao lado, e a terceira com um travessão e a origem da base declarada.

9. **O selo diz "re-ratificada" por escrito, em petróleo**, e a cor nunca é o único indicador —
   a linha continua legível em preto e branco. O petróleo foi escolhido por não colidir com
   nenhum significado já em uso na medição: verde é contratado, roxo é reajustado, âmbar é
   aviso, vermelho é recusa.

## Proveniência de cada valor visual

| Valor | De onde vem |
| --- | --- |
| `--bg`, `--surface`, `--ink`, `--line`, `--accent*`, `--muted` | `apps/web/src/styles.css` — identidade "Grafite técnico" |
| Tabela, cabeçalho em versalete e números tabulares | Padrão já usado nas telas de medição e orçamento |
| Vermelho `#a33d32` da recusa e âmbar `#7c5210` do aviso | Já em uso nas duas jornadas |
| Verde `--accent-soft`/`--accent-text` do selo de contratado e de aprovada | Já em uso |
| Roxo `--reajuste*` e o selo "reajustada" | Introduzidos pelo pacote da [F-039](../../F-039-reajuste-entre-medicoes/mock/README.md), reaproveitados aqui sem alteração |
| **NOVO** — petróleo `#1f6f7a` e a família `--rera*` para o que foi re-ratificado | Introduzido por este pacote. Escolhido por não colidir com contratado, reajustado, aviso nem recusa. |
| **NOVO** — o carimbo da declaração (borda esquerda de 3 px) e a linha de delta com sinal | Introduzidos por este pacote |

## Fronteira entre entregue e reservado

**Entregue nesta feature:** os oito estados — as duas portas da abertura, a herança da rodada
anterior, a declaração da RE-RA com citação, a prévia antes de gravar, o item novo e sua base
de preço, a memória com a declaração carimbada, o controle sem RE-RA e as recusas.

**Reservado, desenhado para segurar lugar** (hachurado no estado 03): **anexar o PDF da
publicação** à declaração. Vira real quando existir o acervo de documentos do contrato; o
campo já é modelado para recebê-lo sem quebrar contrato publicado.

## O que a aprovação não cobre

- A **copy final** de rótulos, avisos e mensagens de recusa.
- Os **números, nomes e datas** das capturas, que são sintéticos.
- O **layout impresso** do MAPÃO e do boletim, que seguem o modelo da prefeitura — este pacote
  decide o que aparece, não a diagramação da planilha exportada.
- O **ciclo de vida do pedido** de aditivo (protocolo, deferimento, negativa), que a decisão 2
  do ADR-0056 põe fora do sistema.
- **RE-RA retroativa** que reescreva período já lançado, que o ADR-0055 decisão 6 já recusou.
- A **jornada do dossiê do aditivo**, que já existe e não é tocada aqui.
