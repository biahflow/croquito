# Design Approval Package — F-042, o acervo de parcelas de canteiro

Classification: INTERFACE_CHANGE  
Revision: 1  
Status: **Approved (2026-08-28)**  
Date: 2026-08-28  
Produced by: agente (Claude Code)

> Governado por [design-approval](../../../engineering-os/workflows/design-approval.md). Este
> artefato é evidência para um gate humano. Não é implementação e não deve ser copiado para
> código de aplicação. **Nenhum agente aprova design.**
>
> Os outros gates desta feature são o [ADR-0060](../../../adr/0060-onde-vive-o-acervo-de-parcelas-de-canteiro.md)
> (onde o acervo vive — unknown 1 da feature) e a **autoria do primeiro acervo**, que é ato
> da orçamentista sobre uma praça já feita. O aceite do
> [ADR-0059](../../../adr/0059-item-contratado-fora-da-tabela-sco.md) já foi cumprido em
> 2026-08-28.

## Registro de aprovação

| Campo | Valor |
| --- | --- |
| O que se aprova | a composição visual da revisão 1 e as nove decisões listadas abaixo |
| Aprovado por | Daniel Campos |
| Data | 2026-08-28 |
| Revisão | 1 |
| Explicitamente **não** coberto | a copy final; os códigos, nomes de parâmetro e números das capturas, que são sintéticos; **quais** são as 24 parcelas do Campo do Toca, que dependem da autoria humana do primeiro acervo; e a decisão do ADR-0060, que é gate próprio |

Aprovar esta revisão não aprova a seguinte: pacote materialmente alterado é revisão nova e
precisa de registro próprio.

## Artefato

| Arquivo | O que é |
| --- | --- |
| [`acervo-de-parcelas-de-canteiro.html`](acervo-de-parcelas-de-canteiro.html) | A rendição autocontida. Abre no navegador sem build, sem rede e sem servidor. |
| [`00-pagina-inteira.png`](00-pagina-inteira.png) | Os nove estados numa imagem |
| [`01-onde-vive.png`](01-onde-vive.png) | Onde a superfície vive: a etapa Códigos, hoje sem apoio nenhum para o canteiro |
| [`02-escolher-acervo.png`](02-escolher-acervo.png) | Passo 1 — escolher o acervo, com a versão à vista |
| [`03-declarar-parametros.png`](03-declarar-parametros.png) | Passo 2 — declarar os parâmetros de obra que o acervo cita |
| [`04-recusa-parametro.png`](04-recusa-parametro.png) | A recusa do parâmetro faltante, nomeando todos os que faltam |
| [`05-previsualizacao.png`](05-previsualizacao.png) | Passo 3 — a pré-visualização obrigatória, com a conta à vista |
| [`06-remover-parcela.png`](06-remover-parcela.png) | Remover uma parcela que não se aplica |
| [`07-aplicado.png`](07-aplicado.png) | Aplicado: a parcela na matriz, com a proveniência e a reaplicação |
| [`08-recusa-codigo.png`](08-recusa-codigo.png) | A recusa do código ausente do catálogo da rodada |
| [`09-autoria.png`](09-autoria.png) | Guardar as parcelas da rodada como acervo novo ou versão nova |

Os números são sintéticos, mas **aritmeticamente consistentes**: `1 × 2 = 2,00`;
`23 × 12 = 276,00`; `2,00 × 1,40 = 2,80`; `132,21 × 3,00 = 396,63`. Um pacote de design de
produto de dinheiro que mostra conta errada ensina a conta errada.

As formas usadas são as cinco que a memória do documento real traz, citadas na feature:
banheiro químico, container, vigia, placa de obra e transporte de andaime.

## Superfícies e estados incluídos

| Superfície | Estado | No pacote |
| --- | --- | --- |
| Painel de parcelas de canteiro (etapa Códigos) | vazio — nenhuma parcela na rodada | sim (01) |
| Painel de parcelas de canteiro | com parcelas aplicadas | sim (07) |
| Aplicar acervo | passo 1 — escolha | sim (02) |
| Aplicar acervo | passo 2 — parâmetros | sim (03) |
| Aplicar acervo | passo 3 — pré-visualização | sim (05) |
| Aplicar acervo | pré-visualização com parcela removida | sim (06) |
| Aplicar acervo | recusa — parâmetro faltante | sim (04) |
| Aplicar acervo | recusa — código ausente do catálogo | sim (08) |
| Aplicar acervo | acervo vazio / nenhum acervo disponível | **não** — ver questões abertas |
| Aplicar acervo | carregando | **não** — o cálculo é local e determinístico; a etapa não tem espera de rede própria além da que a jornada já tem |
| Aplicar acervo | sem papel para aplicar | **não** — a etapa Códigos inteira já é gateada pelo papel da jornada, e este pacote não introduz permissão nova |
| Autoria do acervo | salvar como acervo novo / versão nova | sim (09) |
| Autoria do acervo | recusa de autoria (nome repetido, nada a salvar) | **não** — ver questões abertas |

## Proveniência dos valores visuais

| Valor | Origem | Novo? |
| --- | --- | --- |
| `--bg`, `--surface`, `--surface-subtle`, `--surface-sunken`, `--ink`, `--ink-secondary`, `--muted`, `--line` | `apps/web/src/styles.css:24-42` | não |
| `--accent`, `--accent-hover`, `--accent-ink`, `--accent-text`, `--accent-soft`, `--accent-line` | `apps/web/src/styles.css:33-38` | não |
| Vermelho `#a33d32` da recusa e âmbar `#7c5210` do aviso | já em uso nas duas jornadas | não |
| Inter como família de texto | `apps/web/src/styles.css:47-48` | não |
| Passos 1-2-3 no topo do fluxo | forma nova neste pacote, mas construída só com tokens existentes | forma nova, valores existentes |
| **NOVO** — azul-ardósia `#3a5f8f` e a família `--acervo*` para o que veio de um acervo | introduzido por este pacote. Escolhido por não colidir com nenhum significado já em uso no orçamento: verde = confirmado/contratado, roxo = reajuste, petróleo = RE-RA, âmbar = aviso, vermelho = recusa. | **sim** |

Design system referenciado: `apps/web/src/styles.css` (identidade "Grafite técnico") e
`apps/web/src/orcamento/styles.css`, lidos em 2026-08-28. Se este pacote e essa fonte
divergirem, a fonte vence e este pacote está velho.

Regra de acessibilidade da folha respeitada: `--accent` só em preenchimento; verde como texto
usa `--accent-text`; `--muted` não é usado como texto pequeno vivo. O azul-ardósia novo é
usado como texto (`#3a5f8f` sobre branco, 6,6:1) e como borda.

## Entregue x reservado

| Elemento | Esta feature | Reservado para | Vira real quando |
| --- | --- | --- | --- |
| Escolher acervo, declarar parâmetros, pré-visualizar, remover, aplicar | entrega | — | — |
| Selo de proveniência "do acervo vN" na matriz | entrega | — | — |
| Reaplicar / remover as do acervo | entrega | — | — |
| Autoria de acervo (estado 09) | entrega | — | — |
| Sugestão de valor de parâmetro a partir da prancha | **não desenha nada** | feature futura | quando estiver verificado que a "ÁREA DE INTERVENÇÃO" impressa alimenta alguma parcela |

Nenhum controle inerte é desenhado. O pacote não reserva espaço para o que não entrega:
sugestão de parâmetro simplesmente não existe na tela.

## Decisões que este pacote carrega

1. **O painel de canteiro é seção própria da etapa Códigos, irmã da lista de elementos — não
   uma aba nem uma tela separada.** Parcela de canteiro não tem elemento de origem
   (`STANDALONE` proíbe `source_item_id`), então ela não pode aparecer pendurada em nenhum
   item da legenda sem mentir sobre o modelo. E separá-la em outra tela esconderia 56% do
   preenchimento da praça de quem está preenchendo a praça.

2. **A aplicação tem três passos obrigatórios — acervo, parâmetros, prévia — e não existe
   caminho que pule a prévia.** É o controle do risco declarado na feature: "o ganho é
   justamente não digitar, e o risco é a orçamentista aplicar sem olhar". Um botão "aplicar
   tudo" ao lado da escolha do acervo destruiria o controle, e por isso ele não existe.

3. **A pré-visualização mostra a conta, não só o número.** A coluna "Conta" traz os operandos
   nomeados — `23 dias × 12 h` —, que é exatamente o que vai sair impresso na memória de
   cálculo. Mostrar só `276,00 h` obrigaria a abrir a planilha para conferir o que a máquina
   fez.

4. **Parâmetro nasce vazio e nunca é inferido nem pré-preenchido.** O campo diz a unidade e
   quantas parcelas o citam, para a orçamentista saber o peso do que está declarando. A tela
   diz por extenso que a área impressa na prancha não é usada enquanto não estiver verificada.

5. **A recusa por parâmetro faltante nomeia todos os faltantes e não materializa nada** — nem
   as parcelas que estariam completas. Aplicar "o que dá" produziria uma planilha parcial com
   aparência de completa, que é o modo de falha mais caro desta feature.

6. **A remoção é por parcela, na prévia, e a parcela removida continua visível, riscada.** Ela
   sai da conta, não da tela: sumir por completo deixaria a lista curta sem dizer o que saiu.
   Remover é reversível até aplicar.

7. **Parcela nascida de acervo carrega selo de proveniência com a versão, e continua editável
   como qualquer outra contribuição.** O selo distingue por **texto** ("do acervo v1" x
   "autorada à mão"), não por cor — a regra de nunca usar cor como único indicador vale aqui
   como vale na revisão do croqui.

8. **Reaplicar o mesmo acervo substitui as parcelas dele e nunca toca as autoradas à mão.** É
   a leitura visual da idempotência que a feature exige. O carimbo mostra os parâmetros da
   última aplicação, para que "reaplicar" não seja um salto no escuro.

9. **Código do acervo ausente do catálogo é recusa por extenso, nomeando o código — nunca
   parcela pulada em silêncio.** É o risco de "acervo silenciosamente desatualizado" da
   feature: um orçamento com uma linha a menos e nenhum sinal.

## Questões abertas

Nada aqui é resolvido por um agente durante a implementação.

- **Acervo vazio / nenhum acervo disponível ao tenant.** O estado não está no pacote porque
  depende do ADR-0060: se o acervo for artefato de plataforma, a lista vazia é uma frase de
  plataforma; se for do tenant, é um convite a autorar o primeiro. A frase muda conforme a
  decisão.
- **Recusa de autoria** (nome repetido, nada de `STANDALONE` para salvar) — mesma dependência.
- **Se os parâmetros são por rodada ou por praça** (unknown 2 da feature). O pacote desenha
  por rodada, que é onde a aplicação acontece; se o conjunto se partir em dois, a tela do
  passo 2 muda e isso é revisão nova.
- **Se o acervo é por lote do contrato** (unknown 3). O cartão do acervo tem espaço para dizer
  o lote, mas o pacote não decide que ele existe.
- **A copy final** de todas as frases, inclusive as duas recusas.

## Notas para quem implementar

- **Intencional e a preservar**: os três passos com a prévia obrigatória; a coluna "Conta" com
  operandos nomeados; a recusa que nomeia todos os faltantes; a parcela removida visível e
  riscada; o selo de origem distinguindo por texto; o carimbo com os parâmetros da aplicação.
- **Ilustrativo, e não é especificação**: todos os códigos (`AC01100010(/)` etc.), os nomes
  dos acervos, os nomes dos parâmetros, as datas e as quantidades. **Quais** são as 24
  parcelas do Campo do Toca é ato humano de autoria, não dedução a partir deste pacote.
- **O que o artefato não mostra**: ordem de foco, comportamento de teclado, leitura por
  leitor de tela, mensagens de carregamento e o texto de erro vindo da API. A recusa
  renderizada aqui é a forma; o texto real vem do código de erro estável do domínio.
- A prévia lista 5 das 24 parcelas por espaço. Na tela real a lista é inteira e rolável — o
  contador do rodapé ("24 parcelas", "23 serão aplicadas · 1 removida") é parte do desenho.
