# Design Approval Package — F-036, abertura da medição a partir do orçamento assinado

Classification: INTERFACE_CHANGE  
Revision: 1  
Status: **Approved (2026-08-23)**  
Date: 2026-08-23  
Produced by: agente (Claude Code)

> Governado por [design-approval](../../../engineering-os/workflows/design-approval.md). Este
> artefato é evidência para um gate humano. Não é implementação e não deve ser copiado para
> código de aplicação.
>
> **Aprovado por ato humano em 2026-08-23**, registrado abaixo. Nenhum agente aprova design,
> inclusive o que o produziu; o que segue é a transcrição da decisão humana. Com este gate e o
> [ADR-0048](../../../adr/0048-consolidado-contratual-do-orcamento-assinado.md) aceito, a
> [F-036](../feature.md) sai de `BLOCKED`.

## Registro de aprovação

| Campo | Valor |
| --- | --- |
| O que foi aprovado | a composição visual da revisão 1 — os sete estados capturados e as seis decisões listadas em "Decisões que este pacote carrega" |
| Aprovado por | Daniel Campos |
| Data | 2026-08-23 |
| Revisão aprovada | 1 |
| Explicitamente **não** coberto | a copy final; os números fictícios das capturas; qualquer regra de autorização; e as decisões do [ADR-0048](../../../adr/0048-consolidado-contratual-do-orcamento-assinado.md), que foram gate próprio, exercido em separado na mesma data |

Aprovar esta revisão não aprova a seguinte: pacote materialmente alterado é revisão nova e
precisa de registro próprio.

## Artefato

| Arquivo | O que é |
| --- | --- |
| [`abertura-da-medicao.html`](abertura-da-medicao.html) | A rendição autocontida. Abre no navegador sem build, sem rede e sem servidor. |
| [`00-pagina-inteira.png`](00-pagina-inteira.png) | Todos os estados numa imagem |
| [`01-normal.png`](01-normal.png) | Há orçamento assinado sob demanda contratada; o revisor escolhe a origem |
| [`02-vazio.png`](02-vazio.png) | Nenhum orçamento assinado disponível; a alternativa fica escrita |
| [`03-carregando.png`](03-carregando.png) | Leitura em curso, sem afirmar nada |
| [`04-recusa.png`](04-recusa.png) | Recusa do servidor: assinatura caduca por remontagem |
| [`05-sem-papel.png`](05-sem-papel.png) | Conta sem `orcamentista` |
| [`06-rodada-com-vinculo.png`](06-rodada-com-vinculo.png) | A rodada aberta declarando contra o que confere |
| [`07-rodada-sem-vinculo.png`](07-rodada-sem-vinculo.png) | A mesma rodada sem vínculo, dizendo a verdade oposta |

As imagens acompanham o HTML de propósito: a rendição depende de fonte, navegador e
plataforma, e a captura congelada é o que a aprovação de fato referencia.

## Decisões que este pacote carrega

1. **A origem é uma escolha explícita, não um caminho escondido.** O revisor decide entre "de
   um orçamento assinado" e "do zero, com catálogo por upload". Sem a escolha visível, a
   medição vinculada seria um atalho que só quem já sabe encontra.
2. **O que vem do orçamento não é digitado.** Obra, catálogo, contratado e saldo inicial
   aparecem como procedência lida, não como campo. É a tradução visual da regra do contrato:
   nenhum número do consolidado é informado por humano.
3. **O digest do conteúdo assinado é mostrado, abreviado.** É o que responde "medi contra o
   quê", e mostrá-lo por extenso ocuparia a linha inteira sem ajudar a ler.
4. **A rodada declara o regime de conferência, e as duas variantes usam o mesmo painel.**
   Estados 6 e 7 são a mesma composição dizendo coisas opostas. É a exigência da decisão 9 do
   ADR-0048 traduzida em tela: as duas não podem parecer iguais.
5. **A recusa nomeia a causa e o próximo ato.** "Assinatura caduca" vem com o que fazer —
   assinar a versão atual —, e com a afirmação de que nada foi gravado.
6. **Cor nunca é o único indicador.** Todo selo tem o texto do estado dentro dele
   (`Assinado`, `Assinatura caduca`, `Sem contratado de origem`), e o bloco reservado é
   tracejado **e** rotulado.

## Procedência de cada valor visual

Tudo abaixo é **citação** do sistema existente, não valor novo:

| Elemento | De onde vem |
| --- | --- |
| Tokens de cor, tipografia e raio | `apps/web/src/styles.css`, bloco `:root` — copiados verbatim |
| Cartão da seção | `.painel` e `.painel-cabecalho` (`apps/web/src/medicao/styles.css`) |
| Formulário e campos | `.formulario`, `.campo`, `.campo-dica`, `.campo-erro` |
| Grupo de opções | `.acoes` (o mesmo do par de rádios já usado na medição) |
| Botões | `.botao-primario`, `.botao-secundario`, `.acoes-linha` |
| Faixa de aviso | `.aviso-fixo` + `.aviso-inline` |
| Selos | `.selo`, `.selo-ok`, `.selo-atencao`, `.selo-neutro` |
| Bloco de resumo cinza | `.decisao-registrada` (fundo `--surface-subtle`) |

**Valores novos, e é o que está sendo decidido**: três composições de layout, todas montadas
sobre tokens existentes e sem cor nova —

- a **lista de origem** (`.origem-item`), que é um cartão com rádio; o estado escolhido usa
  `--accent-soft` com borda `--accent-text`, ambos já no sistema;
- a **faixa de procedência** (`.procedencia`), rótulo em caixa alta sobre `--surface-sunken`,
  no molde do `.eyebrow` que a folha já tem;
- o **digest em monoespaçada**, que é a primeira vez que a jornada de medição imprime um
  digest na tela.

## Fronteira entre entregue e reservado

**Entregue**: os estados 1 a 7 — escolher a origem, ver a procedência, abrir a rodada, as
recusas, e o painel da rodada declarando o regime de conferência nos dois casos.

**Reservado** (traço tracejado e opacidade reduzida, no estado 1): o bloco **Contrato** —
número, data-base e desconto do contrato guarda-chuva. Torna-se real quando o orçamento
modelar contrato como entidade, que é a lacuna 4 do
[ADR-0045](../../../adr/0045-terceiro-estado-demanda-sob-contrato.md) e feature própria. Não é
construído aqui.

## O que a aprovação desta revisão NÃO cobre

- **A copy final.** Os textos são proposta do agente, não linguagem estabelecida do produto.
- **Os números.** Praças, valores, nomes e digests são fictícios e servem para dar forma.
- **As decisões do ADR-0048** — preço sem BDI, agregação por código, grupo único, período.
  Foram gate próprio, aceito por ato humano separado na mesma data.
- **Qualquer regra de autorização**: a tela mostra e oferece; quem recusa é o servidor.

## Questões em aberto

1. A lista deve mostrar **todos** os orçamentos assinados do cliente, ou só os que ainda não
   têm medição aberta? O mock mostra todos. Esconder os já medidos encurta a lista, mas
   esconde também o caso legítimo da segunda medição.
2. O painel da rodada vinculada deve mostrar **saldo por código** já na abertura, ou só o
   total? O mock mostra só o total — a tabela por código existe na etapa do boletim, e
   repeti-la aqui duplicaria a leitura antes de haver o que comparar.

## Divergências entre a revisão aprovada e o que foi construído

Conferidas estado a estado na T3 (2026-08-23), com as capturas ao lado da tela. Três, e as
duas primeiras têm a mesma raiz — **o mock desenhou dado que nenhuma rota devolve**:

1. **A procedência não nomeia o catálogo.** O estado 1 desenha "SCO 2026-06 (do orçamento)";
   a tela mostra "o mesmo do orçamento". `GET /v1/valuation-origins` devolve o que identifica
   o orçamento (obra, referência, assinatura, códigos, total), não a data-base do catálogo
   dele. Trazer o rótulo exigiria abrir cada orçamento na listagem, e a tela preferiu dizer
   a verdade curta a inventar a longa.

2. **A recusa de assinatura caduca aparece NO ITEM, não numa faixa no topo.** O estado 4
   desenha a faixa `.aviso-fixo` acima da lista. O construído põe o motivo dentro do próprio
   item, com o rádio desabilitado, e reserva a faixa do topo para a recusa que vem do
   servidor. A razão é de leitura: a faixa no topo fala de "este orçamento" sem dizer qual,
   e com mais de um item na lista ela deixa de identificar o seu alvo.

3. **O padrão da escolha segue o dado, não a captura.** O estado 1 mostra "De um orçamento
   assinado" marcado. A tela nasce em "do zero" e só troca quando existe ao menos um
   orçamento **assinado** — que é exatamente o que o estado 2 do próprio pacote desenha, com
   a opção desabilitada. As duas capturas juntas descrevem um comportamento condicional que
   nenhuma delas mostra sozinha.

Nenhuma delas muda a composição visual aprovada: são o mesmo layout, os mesmos selos e os
mesmos tokens. Se alguma for contestada, é revisão nova do pacote, com registro próprio.

## Transcrição do ato

Aprovação dada por Daniel Campos em 2026-08-23, depois de o pacote e as capturas serem
entregues. Aprovar esta revisão não aprova a seguinte, e não decide as duas questões em
aberto acima — elas seguem em aberto.
