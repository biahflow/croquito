# Design Approval Package — F-030, a evidência de campo na revisão do croqui

Classification: INTERFACE_CHANGE  
Revision: 2  
Status: **Pendente de aprovação**  
Date: 2026-08-23  
Produced by: agente (Claude Code)

> Governado por [design-approval](../../../engineering-os/workflows/design-approval.md). Este
> artefato é evidência para um gate humano. Não é implementação e não deve ser copiado para
> código de aplicação.
>
> **Produzir o pacote não é aprová-lo.** Nenhum agente aprova design, inclusive o que o
> produziu. Enquanto não houver registro de aprovação humana abaixo, a
> [F-030](../feature.md) permanece `BLOCKED`.

## O que mudou da revisão 1 para a 2

A revisão 1 cobria **só a foto**, e nunca chegou a ser aprovada. Uma decisão humana de
2026-08-23 ampliou a feature para incluir a **medida de campo como testemunha da cota** e o
caminho do **levantamento legado**, sem app. Isso é alteração material, e por isso é revisão
nova, e não uma correção da anterior.

Três estados entraram: testemunha ao lado da cota (5), testemunha discordando (6) e legado
com valor lido na foto a confirmar (7). Os sete estados da revisão 1 permanecem, renumerados.

## Registro de aprovação

| Campo | Valor |
| --- | --- |
| O que se pede aprovar | a composição visual da revisão 2 — os dez estados capturados e as nove decisões listadas em "Decisões que este pacote carrega" |
| Aprovado por | — |
| Data | — |
| Revisão | 2 |
| Explicitamente **não** coberto | a copy final; as amostras sintéticas no lugar das fotos; os números, nomes e datas das capturas; o nome do prompt e do modelo; e as decisões do [ADR-0049](../../../adr/0049-evidencia-de-campo-na-revisao-do-escritorio.md), que são gate próprio e ainda `Proposed` |

Aprovar esta revisão não aprova a seguinte: pacote materialmente alterado é revisão nova e
precisa de registro próprio.

## Artefato

| Arquivo | O que é |
| --- | --- |
| [`foto-na-revisao.html`](foto-na-revisao.html) | A rendição autocontida. Abre no navegador sem build, sem rede e sem servidor. |
| [`00-pagina-inteira.png`](00-pagina-inteira.png) | Todos os estados numa imagem |
| [`01-normal.png`](01-normal.png) | Levantamento vinculado: fotos com âncora, qualidade e leitura |
| [`02-vazio.png`](02-vazio.png) | Job sem levantamento vinculado, com o ato de vincular |
| [`03-carregando.png`](03-carregando.png) | Leitura em curso |
| [`04-sem-analise.png`](04-sem-analise.png) | Foto sem análise, e leitura paga pulada |
| [`05-testemunha.png`](05-testemunha.png) | A trena ao lado da cota, com a diferença mostrada e não classificada |
| [`06-testemunha-discorda.png`](06-testemunha-discorda.png) | Prancha e campo discordando — aviso, nunca veto |
| [`07-legado.png`](07-legado.png) | Legado sem app: valor lido no visor da trena, a confirmar |
| [`08-proposta-da-ia.png`](08-proposta-da-ia.png) | Classificação da fatia 3 como rascunho, com lineage |
| [`09-recusa.png`](09-recusa.png) | Recusa: processamento de IA não habilitado |
| [`10-sem-papel.png`](10-sem-papel.png) | Conta sem papel de revisão |

As imagens acompanham o HTML de propósito: a rendição depende de fonte, navegador e
plataforma, e a captura congelada é o que a aprovação de fato referencia.

**As fotos são amostras sintéticas** — um ladrilho listrado com a palavra "amostra sintética"
escrita dentro. O pacote não usa imagem de cliente, e não desenha uma foto plausível que
alguém pudesse tomar por evidência real.

## Decisões que este pacote carrega

1. **A foto mora onde a decisão acontece**, num painel próprio da revisão, e não em aba
   separada. Era o ponto da feature: a dúvida "o que é" aparece revisando a prancha.
2. **A âncora do campo é o rótulo da foto** — "Elemento: mureta oeste", "Ponto 7", "Nota:
   …". O escritório lê a ancoragem que o técnico registrou e não reancora por inferência.
3. **A fronteira "não mede" é escrita, não implícita.** A frase aparece no painel e de novo
   dentro da proposta da IA. Uma imagem ao lado de uma cota sugere confirmação que ela não
   dá, e o texto é a única defesa contra isso na tela.
4. **A proposta da IA usa a veste de rascunho, e a ação primária é "registrar como nota de
   revisão".** O ato humano é o que grava; o botão nomeia onde a conclusão vai parar.
5. **Estado sem análise é estado, não erro.** Cinza neutro e frase que diz o porquê —
   processamento pago desabilitado ou leitura pulada —, sem a cor de domínio do erro.
6. **A testemunha aparece como confronto de dois números, com a origem de cada um por
   extenso** — `COTA DA PRANCHA` e `TRENA EM CAMPO` —, e a diferença ao lado, separada por
   um filete. Sem os rótulos, os dois números pareceriam duas leituras da mesma coisa.
7. **A discordância veste a faixa de erro do sistema (`.app-alert`), e a concordância não
   veste nada.** É deliberado: o caso que precisa de atenção é o que ninguém vê hoje. Mas o
   texto diz, dentro do próprio bloco, que é aviso e não veto — a veste chama, a frase
   delimita.
8. **No legado, confirmar o valor e associá-lo são dois botões em dois momentos.** O estado 7
   mostra só o primeiro. Um botão único faria um número lido por máquina virar testemunha sem
   ninguém olhar.
9. **Cor nunca é o único indicador.** `NITIDEZ BOA`, `CONTRALUZ`, `SEM ANÁLISE`,
   `LEITURA PULADA`, `RASCUNHO`, `LEGADO` e `TESTEMUNHA DISCORDA` são texto dentro da
   pastilha, e o bloco reservado é tracejado **e** rotulado.

## Procedência de cada valor visual

Tudo abaixo é **citação** do sistema existente, não valor novo:

| Elemento | De onde vem |
| --- | --- |
| Tokens de cor, tipografia e raio | `apps/web/src/styles.css`, bloco `:root` — copiados verbatim |
| Cartão e cabeçalho do painel | `.panel` e `.panel-heading` |
| Rótulo em caixa alta | `.eyebrow` |
| Texto auxiliar | `.field-hint` |
| Botões | `.button`, `.button-primary`, `.button-secondary` |
| Pastilha verde (`NITIDEZ BOA`, `VINCULADO`) | `.ready` |
| Pastilha âmbar (`CONTRALUZ`, `RASCUNHO`) | `.blocked` |
| Faixa de erro | `.app-alert` |
| Faixa de estado (não-erro) | `.app-status` |

**Valores novos, e é o que está sendo decidido**: três composições de layout, todas sobre
tokens existentes e sem cor nova —

- a **grade de fotos** (`.foto`), cartão com miniatura, âncora e pastilhas;
- o **bloco da proposta** (`.proposta`), que usa `--accent-soft` com borda `--accent-line`,
  ambos já no sistema, para distinguir rascunho de máquina do conteúdo confirmado;
- a **pastilha neutra** (`SEM ANÁLISE`, `SEM VÍNCULO`, `LEGADO`), sobre `--surface-sunken`. É
  irmã da `.neutro` que o pacote da F-034 introduziu na tela de Plataforma, pelo mesmo motivo:
  as duas pastilhas existentes são "positivo" e "atenção", e ausência não é nenhuma das duas;
- o **bloco de testemunha** (`.testemunha`), que é o `--surface-subtle` já usado em resumo,
  com os números em `font-variant-numeric: tabular-nums` para que 19,75 e 12,40 alinhem
  coluna a coluna. Na variante de discordância ele reusa os valores da `.app-alert`
  (`#fbeeec` e `#e0b4ad`), sem cor nova.

## Fronteira entre entregue e reservado

**Entregue**: os estados 1 a 10 — ver as fotos ancoradas com qualidade e leitura, vincular um
levantamento, subir foto avulsa, a testemunha de campo ao lado da cota (concordando e
discordando), o caminho do legado, a classificação por IA como rascunho, e os estados de
vazio, carregando, sem análise, recusa e sem papel.

**Reservado** (traço tracejado e opacidade reduzida, no estado 1): a **nota de voz do técnico
com sua transcrição** ao lado da foto. Áudio e transcrição já existem na F-032; trazê-los
para a revisão é feature própria e está declarado fora de escopo desta.

## O que a aprovação desta revisão NÃO cobre

- **A copy final.** Os textos são proposta do agente, não linguagem estabelecida do produto.
- **As fotos.** As amostras são sintéticas de propósito; como a foto real se apresenta em
  tamanho, corte e ampliação não está decidido aqui.
- **As decisões do ADR-0049** — vínculo pelo job da prancha, nada no scene graph, conclusão
  como nota de revisão, classificação sob demanda. São gate próprio, e o ADR está `Proposed`.
- **O nome do prompt, do modelo e o custo** que aparecem no lineage da captura: são
  ilustração da forma, não escolha de roteamento.
- **Qualquer regra de autorização**: a tela mostra e oferece; quem recusa é o servidor.

## Questões em aberto

1. A foto deve **ampliar** ao ser clicada, dentro da revisão, ou abrir em aba nova? O mock
   não decide — mostra a miniatura. Ampliar dentro mantém o contexto da decisão; abrir fora
   dá tela cheia sem construir visualizador.
2. As fotos devem ser **filtráveis pela âncora** (só as do elemento que estou revisando)?
   O mock lista todas do levantamento. Filtrar aproxima a evidência da decisão, mas esconde
   a foto cuja âncora o técnico errou — que é justamente a que o escritório precisa ver.
3. Uma leitura pode ter **mais de uma testemunha**? O mock mostra uma. Duas trenas do mesmo
   trecho é caso real, e a tela teria de escolher entre empilhá-las ou resumir a faixa.
