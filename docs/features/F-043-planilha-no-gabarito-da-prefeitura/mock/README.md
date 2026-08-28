# Design Approval Package — F-043, a planilha no gabarito da prefeitura

Classification: INTERFACE_CHANGE  
Revision: **2**  
Status: **Awaiting approval** (a revisão 1 foi aprovada em 2026-08-28)  
Date: 2026-08-28  
Produced by: agente (Claude Code)

> Governado por [design-approval](../../../engineering-os/workflows/design-approval.md). Este
> artefato é evidência para um gate humano. Não é implementação e não deve ser copiado para
> código de aplicação. **Nenhum agente aprova design.**
>
> A superfície que muda aqui é, antes de tudo, **o arquivo que a rodada publica**. A tela só
> muda no ponto em que ela promete esse arquivo. O aceite do
> [ADR-0059](../../../adr/0059-item-contratado-fora-da-tabela-sco.md) já foi cumprido em
> 2026-08-28.

## Por que existe uma revisão 2

A revisão 1 foi desenhada **antes** de o documento real estar disponível, e dizia por escrito
que a estrutura das capturas era sintética e não era especificação. Com os três orçamentos
reais em mãos (2026-08-28), quatro pontos de **forma** do documento se mostraram diferentes do
que a rendição mostrava. A revisão 2 corrige a rendição para o que o documento realmente é.

| Revisão 1 | Documento real, agora na revisão 2 |
| --- | --- |
| linha de grupo com título (`01 — SERVIÇOS PRELIMINARES…`) | linha de grupo com **apenas o número** (`1`) |
| rodapé de três linhas: TOTAL SEM BDI, BDI, TOTAL GERAL | **duas** linhas: `TOTAL` (com BDI) e `TOTAL S/BDI`, nessa ordem, **sem linha de BDI** |
| coluna rotulada `V. UNIT C/ BDI` | rotulada **`VALOR UNIT (OUT/23)`** — o valor é o mesmo, com BDI embutido |
| BDI de 24,50% | **18%** |

**Nenhuma das sete decisões aprovadas na revisão 1 muda.** Ordem fixa do gabarito, linhas
zeradas impressas, numeração como texto, lacuna de grupo preservada, carimbo de revisão,
recusa de código ausente e memória só para código com quantidade continuam valendo palavra por
palavra. A revisão 2 é de fidelidade ao documento, não de desenho — mas é revisão nova e
precisa de registro próprio, porque o que se aprova é a rendição.

A verificação que produziu esta revisão está em [`../evidence.md`](../evidence.md), junto com
dois achados sobre os arquivos do cliente que **não** são escopo desta feature.

## Registro de aprovação

| Campo | Valor |
| --- | --- |
| O que se aprova | a forma do arquivo publicado na revisão 2 e as sete decisões da revisão 1, que ela preserva |
| Aprovado por | — |
| Data | — |
| Revisão | 2 |
| Explicitamente **não** coberto | a copy final; os códigos, descrições e preços das capturas, que continuam **sintéticos** (a *estrutura* deixou de ser); **qual das duas formas de rodapé vale** — a do cliente, desenhada aqui, ou a do ADR-0038 —, que é decisão de quem entrega; e o aceite do arquivo gerado contra o documento do cliente, que é gate próprio e posterior |

Aprovar esta revisão não aprova a seguinte: pacote materialmente alterado é revisão nova e
precisa de registro próprio.

## Decisão do dono já registrada

O gabarito entregável é a aba **`PLANILHA ORÇAMENTÁRIA` (433 códigos)**, não a
`PLANILHA PADRÃO ORDENADA` (518). Isso resolve o unknown 3 da feature e está refletido nas
capturas. Decidido por Daniel Campos em 2026-08-28.

## Artefato

| Arquivo | O que é |
| --- | --- |
| [`planilha-no-gabarito.html`](planilha-no-gabarito.html) | A rendição autocontida. Abre no navegador sem build, sem rede e sem servidor. |
| [`00-pagina-inteira.png`](00-pagina-inteira.png) | Os cinco estados numa imagem |
| [`01-hoje-e-amanha.png`](01-hoje-e-amanha.png) | O que a rodada publica hoje, e o que passa a publicar |
| [`02-escolher-gabarito.png`](02-escolher-gabarito.png) | Publicar: escolher o gabarito e ver a revisão dele |
| [`03-planilha-orcamentaria.png`](03-planilha-orcamentaria.png) | A aba PLANILHA ORÇAMENTÁRIA: ordem fixa, numeração `GG.N`, lacuna de grupo, linhas zeradas |
| [`04-memoria-de-calculo.png`](04-memoria-de-calculo.png) | A aba MEMÓRIA DE CÁLCULO: um bloco por código, parcelas nomeadas |
| [`05-recusas.png`](05-recusas.png) | As duas recusas: código fora do gabarito e auditoria divergente |

Os números são sintéticos, mas **aritmeticamente consistentes**, e as contas fecham na
rendição: `396,63 × 12,40 = 4.918,21` (truncado), `418,12 × 118,42 = 49.513,77`,
`418,12 × 24,90 = 10.411,18`, soma da coluna TOTAL `= 69.952,16` e
`TRUNC(69.952,16 ÷ 1,18; 2) = 59.281,49` — a mesma derivação que o documento real usa. Na
memória, `418,20 − 0,08 = 418,12`.

## Superfícies e estados incluídos

| Superfície | Estado | No pacote |
| --- | --- | --- |
| Publicar planilha | escolha do gabarito, com a revisão à vista | sim (02) |
| Publicar planilha | sem gabarito declarado — publica como hoje | sim (02, na própria lista) |
| Arquivo publicado | aba PLANILHA ORÇAMENTÁRIA, linhas preenchidas e zeradas | sim (03) |
| Arquivo publicado | aba MEMÓRIA DE CÁLCULO | sim (04) |
| Publicar planilha | recusa — código do orçamento ausente do gabarito | sim (05) |
| Publicar planilha | recusa — auditoria divergente | sim (05) |
| Publicar planilha | gerando / auditando (espera) | **não** — a geração é síncrona e curta no caminho de hoje; se virar assíncrona, é revisão nova |
| Publicar planilha | nenhum gabarito disponível | **não** — ver questões abertas |
| Publicar planilha | sem papel para publicar | **não** — a etapa de exportação já é gateada pelo papel da jornada, e este pacote não introduz permissão nova |

## Proveniência dos valores visuais

| Valor | Origem | Novo? |
| --- | --- | --- |
| `--bg`, `--surface`, `--surface-subtle`, `--ink`, `--ink-secondary`, `--muted`, `--line` | `apps/web/src/styles.css:24-42` | não |
| `--accent*` do botão primário e do selo de aprovado | `apps/web/src/styles.css:33-38` | não |
| Vermelho `#a33d32` da recusa e âmbar `#7c5210` do aviso | já em uso nas duas jornadas | não |
| Inter como família de texto da moldura | `apps/web/src/styles.css:47-48` | não |
| Grade cinza da planilha (bordas `#d8d8d3`, cabeçalho `#efefe9`, faixa de grupo `#e4e9ef`), família "Segoe UI" | **rendição do artefato do Excel**, não da SPA. Imita a grade da planilha de propósito, porque o que está sendo aprovado é a forma do arquivo. | **sim**, e é intencionalmente fora do design system da SPA |
| **NOVO** — terracota fria `#8a5a2b` e a família `--gabarito*` | introduzido por este pacote para o que fala do gabarito e da revisão dele. Escolhido por não colidir com verde = aprovado, âmbar = aviso, vermelho = recusa. | **sim** |

Design system referenciado: `apps/web/src/styles.css` (identidade "Grafite técnico") e
`apps/web/src/orcamento/styles.css`, lidos em 2026-08-28. Se este pacote e essa fonte
divergirem, a fonte vence e este pacote está velho.

**A grade da planilha é deliberadamente estranha ao design system**: ela representa o arquivo
`.xlsx` que a prefeitura abre no Excel, não uma tela do produto. Aprovar este pacote aprova
essa exceção.

## Entregue x reservado

| Elemento | Esta feature | Reservado para | Vira real quando |
| --- | --- | --- | --- |
| Aba no gabarito de ordem fixa, com linhas zeradas | entrega | — | — |
| Aba de memória de cálculo do orçamento | entrega | — | — |
| Escolha do gabarito e carimbo da revisão | entrega | — | — |
| As duas recusas | entrega | — | — |
| Aba `PLANILHA GERAL` (lista de preços do contrato) | **não desenha nada** | — | nunca por esta feature: é **entrada**, não saída |
| Inferir o gabarito de um `.xlsx` real | **não desenha nada** | feature própria | se algum dia valer o risco de adivinhar layout de arquivo de cliente |

## Decisões que este pacote carrega

1. **O arquivo publicado passa a ser o gabarito, e a aba de hoje não morre.** A rodada que não
   declara gabarito continua publicando exatamente o que publica agora. O gabarito é seção
   adicional, não substituição — o que também é o que o contrato da feature manda.

2. **As 390 linhas sem quantidade são impressas com zero, e não omitidas.** Elas fazem parte
   da entrega: o documento que a prefeitura recebe tem 433 linhas. Uma planilha com 43 linhas
   não é o mesmo documento.

3. **Linha zerada se distingue pelo número, não pela cor.** O cinza mais claro é conforto de
   leitura; o que diz que a linha está zerada é `0,00` impresso na quantidade e no total.

4. **Grupo, numeração `GG.N` e lacunas de grupo vêm do gabarito como texto, e nunca são
   recomputados.** `01.5` vem antes de `01.10` porque é numeração, não número; e os grupos 5,
   15 e 22 estão ausentes porque o documento do cliente os omite. Renumerar "para arrumar"
   produziria um arquivo que não é o documento.

5. **A revisão do gabarito é escolhida com a data à vista, e fica carimbada dentro do
   arquivo.** É o controle do risco de "gabarito envelhecido em silêncio": um arquivo gerado
   na revisão velha parece certo, e precisa dizer sozinho qual usou quando estiver fora do
   sistema.

6. **Código no orçamento e ausente do gabarito é recusa nomeando o código — jamais linha
   acrescentada ao fim do arquivo.** Uma linha inventada no fim é um item entregue à
   prefeitura fora do gabarito que ela aceita. As saídas são humanas, e a recusa as nomeia.

7. **Só os códigos com quantidade têm bloco de memória.** Imprimir 390 blocos vazios seria
   ruído, e a planilha já diz que a quantidade é zero.

## Questões abertas

Nada aqui é resolvido por um agente durante a implementação.

- ~~**De onde sai o preço impresso** (unknown 2 da feature)~~ — **resolvido em 2026-08-28**
  contra o arquivo real: a coluna `VALOR UNIT (OUT/23)` traz o preço **com BDI**, porque o
  rodapé deriva o total sem BDI dividindo o total por 1,18. É a mesma base que o escritor já
  usava para compor o total, e a revisão 2 imprime o rótulo real.

- **Qual forma de rodapé vale.** O documento do cliente imprime `TOTAL` e `TOTAL S/BDI` e
  **não** imprime linha de BDI; o [ADR-0038](../../../adr/0038-bdi-como-conceito-de-pre-licitacao.md)
  manda imprimir o BDI como diferença entre totais truncados. As duas dão o mesmo dinheiro. A
  revisão 2 desenha a forma do cliente, e a escolha é de quem entrega à prefeitura.
- **Preço das linhas sem quantidade.** O pacote imprime o preço declarado no gabarito quando
  há um, e deixa a célula vazia quando não há. Se o documento real imprime preço em todas as
  390, o gabarito precisa trazê-los — e isso é dado, não código.
- **Se o gabarito é por lote do contrato ou único para todas as praças** (unknown 1). O pacote
  não decide: o seletor mostra um gabarito nomeado, e se houver um por lote a rodada precisa
  declarar o lote.
- **Nenhum gabarito disponível** — estado não desenhado, porque depende de onde o gabarito
  vive.
- **A copy final** das duas recusas e do aviso de revisão antiga.

## Notas para quem implementar

- **Intencional e a preservar**: todas as linhas do gabarito impressas; o zero visível; a
  numeração e as lacunas como texto do gabarito; o carimbo de revisão dentro do arquivo; as
  duas recusas antes de publicar; o BDI como diferença entre totais truncados (ADR-0038).
- **Ilustrativo, e não é especificação**: os códigos, as descrições, os preços, os nomes de
  grupo, a quantidade de linhas mostrada e a estrutura `01/02/04`. O gabarito real tem 433
  linhas em 21 grupos e entra como **dado declarado**, não como código.
- **O que o artefato não mostra**: larguras de coluna reais, congelamento de painel, formatos
  de número do Excel, quebras de página e impressão. Nada disso é decidido aqui.
- A rendição da grade é uma aproximação em HTML de um arquivo `.xlsx`. Ela existe para
  decidir **a forma do documento**, não para ser copiada como estilo de tela.
