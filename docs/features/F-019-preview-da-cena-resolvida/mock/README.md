# Design Approval Package — F-019, ver a cena resolvida antes de exportar

Classification: INTERFACE_CHANGE  
Revision: 1  
Status: **Approved (2026-08-27)**  
Date: 2026-08-27  
Produced by: agente (Claude Code)

> Governado por [design-approval](../../../engineering-os/workflows/design-approval.md). Este
> artefato é evidência para um gate humano. Não é implementação e não deve ser copiado para
> código de aplicação. **Nenhum agente aprova design.**
>
> Este é o **único** gate da [F-019](../feature.md): ela não exige decisão de arquitetura —
> lê uma rota que já existe (`GET /v1/jobs/{job_id}/scene`) e desenha no cliente.
> **Aprovado por ato humano em 2026-08-27**, registrado abaixo; com isso a feature sai de
> `BLOCKED`.

## Registro de aprovação

| Campo | Valor |
| --- | --- |
| O que foi aprovado | a composição visual da revisão 1 e as dez decisões listadas em "Decisões que este pacote carrega" |
| Aprovado por | Daniel Campos |
| Data | 2026-08-27 |
| Revisão aprovada | 1 |
| Explicitamente **não** coberto | a copy final; os números, nomes e horários das capturas, que são sintéticos; a paleta das demais etapas, que não muda |

Aprovar esta revisão não aprova a seguinte: pacote materialmente alterado é revisão nova e
precisa de registro próprio.

## Artefato

| Arquivo | O que é |
| --- | --- |
| [`preview-da-cena.html`](preview-da-cena.html) | A rendição autocontida. Abre no navegador sem build, sem rede e sem servidor. |
| [`00-pagina-inteira.png`](00-pagina-inteira.png) | Os seis estados numa imagem |
| [`01-cena-resolvida.png`](01-cena-resolvida.png) | A cena com as quatro precisões, escala e orientação |
| [`02-vaos-sobre-a-geometria.png`](02-vaos-sobre-a-geometria.png) | `applied_spans` como cota desenhada; `contested_spans` como faixa do eixo |
| [`03-sem-tracado.png`](03-sem-tracado.png) | Job sem traçado: estado honesto, não erro |
| [`04-conflito.png`](04-conflito.png) | Cena com entidade não resolvida e trecho em disputa |
| [`05-cena-grande.png`](05-cena-grande.png) | Aproximar e enquadrar, com a escala acompanhando |
| [`06-entidade-escolhida.png`](06-entidade-escolhida.png) | Seleção cruzada entre desenho e lista |

## Decisões que este pacote carrega

1. **O preview vive na etapa `Aprovação`** (Unknown 2 do [Feature Contract](../feature.md)).
   É onde a decisão que ele informa acontece. Traçado é onde o resultado nasce, mas ver ali
   seria ver antes de a pergunta existir.
2. **A precisão é distinguida por traço, e o traço é o indicador primário**: exata = grosso
   contínuo, derivada = fino contínuo, aproximada = tracejado, não resolvida = pontilhado
   esmaecido. A legenda repete a mesma distinção **por escrito**, e cada entidade leva rótulo
   com o nome da precisão. Nenhuma das quatro depende de cor para ser lida — critério 3 do
   contrato.
3. **`applied_spans` viram cota desenhada onde ancoraram.** Eles declaram `start_m`/`end_m`,
   então há posição para respeitar.
4. **`contested_spans` aparecem como faixa do eixo, e o desenho declara por quê.** O contrato
   de `ContestedSpanOut` traz `axis`, `values_m` e `reading_ids` — **não traz posição**.
   Desenhar a disputa num ponto exato seria inventar o dado que falta. A faixa cobre o eixo e
   diz, em texto, "posição no eixo não é declarada pelo servidor". Se posição precisa for
   desejada, ela é mudança de contrato da API, e portanto outra feature.
5. **Escala é barra gráfica com marcas**, e ela acompanha o zoom. Sem barra, um desenho sem
   cota não diz se aquilo tem 3 ou 30 metros.
6. **A orientação é declarada com uma seta `Y+`**, e a cena é desenhada com Y para cima. O
   espelhamento é o mesmo que `tracing.py` já aplica.
7. **Cena grande usa a interação de zoom que a prancha já tem**: roda aproxima, arrasto move,
   um botão enquadra o todo. O `viewBox` move desenho e cotas juntos, por construção — o mesmo
   argumento que a prancha do orçamento registrou.
8. **O preview não imita a prancha**: fundo neutro, sem carimbo, sem moldura, com "somente
   leitura" escrito na barra. É a mitigação do risco de alguém aprovar o desenho em vez da
   cena.
9. **Sem traçado, o painel diz que não há o que desenhar** e não chama nada. Estado honesto,
   como o contrato pede.
10. **Ver não é corrigir**: nenhuma alça, nenhum arrasto de vértice. Corrigir forma é a
    [F-018](../../F-018-edicao-de-forma-da-proposta/feature.md), e a barra inferior do estado
    06 diz isso por extenso.

## Proveniência de cada valor visual

| Valor | De onde vem |
| --- | --- |
| `--bg`, `--surface`, `--ink`, `--line`, `--accent*`, `--muted` | `apps/web/src/styles.css` — identidade "Grafite técnico" |
| Azul `#166a83` dos vãos aplicados | `.proposal-shape.selected` (`styles.css:1748`) — o mesmo azul de "isto é o que você está olhando" |
| Vermelho `#a33d32` da disputa | `.proposal-shape.reject` (`styles.css:2238`) |
| Pílula de etapa, painel, avisos, botão primário | Padrões já usados na revisão (`CroquiApp.tsx`) |
| Controles de zoom (`+`, `−`, `⤢`) | Mesma forma dos controles de viewport da prancha |
| **NOVO** — a família de traços por precisão (grosso/fino/tracejado/pontilhado) | Introduzida por este pacote. É o núcleo do que está sendo aprovado. |
| **NOVO** — barra de escala com marca intermediária e seta `Y+` | Introduzida por este pacote |
| **NOVO** — faixa hachurada do eixo em disputa | Introduzida por este pacote |

## Fronteira entre entregue e reservado

**Entregue nesta feature:** os seis estados acima — cena resolvida, vãos sobre a geometria,
ausência de traçado, conflito, zoom/enquadramento e seleção cruzada com a lista.

**Reservado, desenhado para segurar lugar** (aparece hachurado no estado 05): a **prancha do
projetista sob o desenho**. O Feature Contract já a coloca fora de escopo; o pacote confirma e
nomeia a condição para ela virar real — registro entre pixels e metros com incerteza declarada
por entidade. Um overlay desalinhado é pior que nenhum.

## O que a aprovação não cobre

- A **copy final** de rótulos e avisos.
- Os **números, nomes e horários** das capturas, que são sintéticos.
- O **desempenho** com cena de muitas entidades: o pacote decide a interação (zoom, recorte),
  não um teto de entidades.
- Qualquer mudança no **portão de exportação** (`ensure_exportable()`), que continua sendo
  quem decide se a cena sai — o desenho é leitura, não laudo.
- O **render do DXF**, que continua sendo a prova do arquivo exportado.
