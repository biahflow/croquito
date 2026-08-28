# Design Approval Package — F-044, o precedente de código na shortlist

Classification: INTERFACE_CHANGE  
Revision: 1  
Status: **Awaiting approval — e atrás de um gate anterior**  
Date: 2026-08-28  
Produced by: agente (Claude Code)

> Governado por [design-approval](../../../engineering-os/workflows/design-approval.md). Este
> artefato é evidência para um gate humano. Não é implementação e não deve ser copiado para
> código de aplicação. **Nenhum agente aprova design.**

## O gate que vem antes deste

O primeiro Human Gate da feature é **medir a hipótese de repetição de rótulo entre praças** e
decidir se a feature continua: *"Se a repetição for baixa, a feature perde a razão de existir
e deve ser cancelada em vez de construída"*.

Essa medição **ainda não foi feita** — o instrumento para fazê-la está sendo construído nesta
mesma rodada (`precedent-eval`), e o dado de uma segunda praça foi prometido pelo dono do
produto em 2026-08-28.

Aprovar este pacote decide **a forma, caso a feature siga**. Não decide que ela segue. Se a
medição derrubar a hipótese, este pacote é arquivado junto com a feature.

## Registro de aprovação

| Campo | Valor |
| --- | --- |
| O que se aprova | a composição visual da revisão 1 e as sete decisões listadas abaixo, condicionadas ao gate de medição |
| Aprovado por | — |
| Data | — |
| Revisão | 1 |
| Explicitamente **não** coberto | a copy final; os rótulos, códigos, preços e contagens de praça das capturas, que são sintéticos; **o limiar de quantas praças fazem um precedente confiável** (unknown 3 da feature); e a estratégia de normalização do rótulo (unknown 2), que sai da medição |

Aprovar esta revisão não aprova a seguinte: pacote materialmente alterado é revisão nova e
precisa de registro próprio.

## Artefato

| Arquivo | O que é |
| --- | --- |
| [`precedente-de-codigo.html`](precedente-de-codigo.html) | A rendição autocontida. Abre no navegador sem build, sem rede e sem servidor. |
| [`00-pagina-inteira.png`](00-pagina-inteira.png) | Os cinco estados numa imagem |
| [`01-shortlist-hoje.png`](01-shortlist-hoje.png) | A shortlist de hoje: blocos por fonte, sem memória nenhuma |
| [`02-precedente-no-topo.png`](02-precedente-no-topo.png) | O precedente no topo, com a contagem de praças |
| [`03-aceite-do-pacote.png`](03-aceite-do-pacote.png) | Aceitar o pacote inteiro de códigos em um clique |
| [`04-precedente-fraco.png`](04-precedente-fraco.png) | Precedente de uma praça só, e o rótulo inédito sem degradação |
| [`05-fonte-diferente.png`](05-fonte-diferente.png) | Precedente de outra fonte de preço não é oferecido |

## Superfícies e estados incluídos

| Superfície | Estado | No pacote |
| --- | --- | --- |
| Shortlist de códigos | sem precedente — rótulo inédito | sim (04) |
| Shortlist de códigos | com precedente forte (N praças) | sim (02) |
| Shortlist de códigos | com precedente fraco (1 praça) | sim (04) |
| Shortlist de códigos | precedente de outra fonte de preço | sim (05) — o bloco não aparece |
| Aceite de pacote | confirmação antes de gravar | sim (03) |
| Lista de elementos | selo de precedente por elemento | sim (02) |
| Aceite de pacote | recusa do servidor (conflito de versão, código fora do catálogo) | **não** — são as recusas que a etapa Códigos já tem hoje, e este pacote não as altera |
| Shortlist de códigos | carregando | **não** — o `GET` da shortlist já existe e não muda de natureza; o precedente não introduz espera nova |

## Proveniência dos valores visuais

| Valor | Origem | Novo? |
| --- | --- | --- |
| `--bg`, `--surface`, `--surface-subtle`, `--ink`, `--ink-secondary`, `--muted`, `--line` | `apps/web/src/styles.css:24-42` | não |
| `--accent*` do botão primário e do selo de confirmado | `apps/web/src/styles.css:33-38` | não |
| Âmbar `#7c5210` do aviso de precedente fraco | já em uso nas duas jornadas | não |
| Cartão de código, selo de fonte, bloco por fonte de preço | `apps/web/src/orcamento/styles.css` (etapa Códigos, `.codigos`, `.codigo-card`, selo de fonte) | não |
| Inter como família de texto | `apps/web/src/styles.css:47-48` | não |
| **NOVO** — índigo `#4a4a9c` e a família `--precedente*` | introduzido por este pacote para o que veio de decisão anterior. Escolhido por não colidir com verde = confirmado, âmbar = atenção, vermelho = recusa, cinza = observação da máquina. | **sim** |

Design system referenciado: `apps/web/src/styles.css` e `apps/web/src/orcamento/styles.css`,
lidos em 2026-08-28. Se este pacote e essa fonte divergirem, a fonte vence e este pacote está
velho.

## Entregue x reservado

| Elemento | Esta feature | Reservado para | Vira real quando |
| --- | --- | --- | --- |
| Bloco de precedente no topo, com contagem de praças | entrega | — | — |
| Aceite do pacote inteiro em um clique | entrega | — | — |
| Selo de precedente na lista de elementos | entrega | — | — |
| Aviso de precedente de uma praça só | entrega | — | — |
| Precedente de **quantidade** ou de **receita de cálculo** | **não desenha nada** | feature futura | quando o precedente de código provar valor |
| Bloco do braço semântico (F-041) | **não altera nada** | — | são peças complementares: o semântico resolve a partida a frio, que é o que o precedente não tem como resolver |

Nenhum controle inerte é desenhado: quando não há precedente, o bloco **não existe** — não
aparece vazio nem desabilitado.

## Decisões que este pacote carrega

1. **O precedente é um bloco próprio acima dos blocos por fonte, e não reordena a cascata.** A
   ordem instalada por fonte de preço é contrato de outra decisão (ADR-0021 e a cascata da
   F-020); mexer nela seria mudar o que não está em escopo.

2. **A contagem de praças fica escrita ao lado, por extenso.** "Você já usou isto em 4 praças"
   é o controle mínimo do risco de propagar erro com autoridade: o precedente diz "você já fez
   assim", que é um argumento forte, e o leitor precisa saber quão forte.

3. **Um código pode aparecer duas vezes — no precedente e no bloco da fonte — e isso é
   intencional.** Esconder a repetição faria o bloco da cascata parecer incompleto e mudaria
   a ordem instalada.

4. **O aceite é do pacote inteiro do rótulo, em uma revisão só, com a lista à vista antes de
   confirmar.** O precedente é do rótulo, e o rótulo dispara um pacote de códigos — foi assim
   que a decisão original foi tomada. Confirmar sem mostrar o que vai ser gravado seria um
   clique cego.

5. **Aceitar o precedente não fecha o pacote.** O fechamento continua sendo ato separado, como
   a F-038 estabeleceu. Um atalho que fechasse o pacote junto tiraria da orçamentista a
   decisão de dizer "acabou".

6. **Precedente de uma praça só é exibido com aviso âmbar por extenso.** Uma decisão única
   pode ter sido um erro, e exibi-la como precedente propaga o erro. O limiar exato de quantas
   praças bastam continua em aberto (unknown 3) — o que este pacote decide é que o número
   sempre aparece e que o caso fraco é marcado.

7. **Precedente de outra fonte de preço não é oferecido, e nem aparece vazio.** Sugerir código
   que não existe na tabela vigente é o pior resultado possível — pior que não sugerir nada.
   Quando a fonte não bate, a shortlist é exatamente a de hoje.

## Questões abertas

Nada aqui é resolvido por um agente durante a implementação.

- **A hipótese de repetição** (unknown 1) — gate que precede tudo e pode cancelar a feature.
- **Como normalizar o rótulo** (unknown 2). Normalização agressiva demais funde o que é
  distinto; tímida demais não reencontra nada. A escolha sai da medição, não do desenho.
- **Quantas praças fazem um precedente confiável** (unknown 3). O pacote mostra o caso de 1
  praça com aviso, mas não decide se abaixo de um limiar o precedente deixa de ser oferecido.
- **O que fazer quando o precedente e a via léxica discordam frontalmente** — hoje convivem
  sem comentário. Se isso se mostrar confuso na prática, é revisão nova.
- **A copy final** de "Você já usou isto em N praças" e do aviso de precedente fraco.

## Notas para quem implementar

- **Intencional e a preservar**: o bloco acima sem reordenar a cascata; a contagem escrita; a
  lista de confirmação antes de gravar; o aviso do caso de uma praça; a ausência total do
  bloco quando a fonte não bate ou o rótulo é inédito.
- **Ilustrativo, e não é especificação**: os rótulos ("PISO EM CONCRETO", "ALAMBRADO
  h=3,00m"), os códigos, os preços e as contagens de praça. O par de códigos por rótulo é o
  que o documento real mostra, mas os valores exibidos são sintéticos.
- **O que o artefato não mostra**: ordem de foco, comportamento de teclado, leitura por leitor
  de tela e o texto de erro vindo da API.
- O `GET` da shortlist continua sem pagar nada e sem avançar a versão da rodada (ADR-0054
  D7). O precedente não pode introduzir custo nesse caminho, e o índice sai do que já está
  gravado no banco.
