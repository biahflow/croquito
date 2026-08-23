# Design Approval Package — F-030, a foto do levantamento na revisão do croqui

Classification: INTERFACE_CHANGE  
Revision: 1  
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

## Registro de aprovação

| Campo | Valor |
| --- | --- |
| O que se pede aprovar | a composição visual da revisão 1 — os sete estados capturados e as seis decisões listadas em "Decisões que este pacote carrega" |
| Aprovado por | — |
| Data | — |
| Revisão | 1 |
| Explicitamente **não** coberto | a copy final; as amostras sintéticas no lugar das fotos; o nome do prompt e do modelo nas capturas; e as decisões do [ADR-0049](../../../adr/0049-foto-de-campo-na-revisao-do-escritorio.md), que são gate próprio e ainda `Proposed` |

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
| [`05-proposta-da-ia.png`](05-proposta-da-ia.png) | Classificação da fatia 3 como rascunho, com lineage |
| [`06-recusa.png`](06-recusa.png) | Recusa: processamento de IA não habilitado |
| [`07-sem-papel.png`](07-sem-papel.png) | Conta sem papel de revisão |

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
6. **Cor nunca é o único indicador.** `NITIDEZ BOA`, `CONTRALUZ`, `SEM ANÁLISE`,
   `LEITURA PULADA` e `RASCUNHO` são texto dentro da pastilha, e o bloco reservado é
   tracejado **e** rotulado.

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
- a **pastilha neutra** (`SEM ANÁLISE`, `SEM VÍNCULO`), sobre `--surface-sunken`. É irmã da
  `.neutro` que o pacote da F-034 introduziu na tela de Plataforma, pelo mesmo motivo: as
  duas pastilhas existentes são "positivo" e "atenção", e ausência não é nenhuma das duas.

## Fronteira entre entregue e reservado

**Entregue**: os estados 1 a 7 — ver as fotos ancoradas com qualidade e leitura, vincular um
levantamento, subir foto avulsa, a classificação por IA como rascunho, e os estados de vazio,
carregando, sem análise, recusa e sem papel.

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
