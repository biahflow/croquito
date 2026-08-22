# Design Approval Package — F-034 fatia 2, disponibilidade de jornada por tenant

Classification: INTERFACE_CHANGE  
Revision: 1  
Status: Approved (2026-08-22)  
Date: 2026-08-22  
Produced by: agente (Claude Code)

> Governado por [design-approval](../../../engineering-os/workflows/design-approval.md). Este
> artefato é evidência para um gate humano. Não é implementação e não deve ser copiado para
> código de aplicação.

## Registro de aprovação

| Campo | Valor |
| --- | --- |
| O que foi aprovado | a composição visual da revisão 1 — os seis estados capturados e as seis decisões listadas em "Decisões que este pacote carrega", incluindo a pastilha `.neutro` como valor novo |
| Aprovado por | Daniel Campos |
| Data | 2026-08-22 |
| Revisão aprovada | 1 |
| Explicitamente **não** aprovado | a copy final; o estado padrão de uma jornada quando o ambiente não declara nada; a fatia 1 (sem superfície); o nome das jornadas na tela; qualquer regra de autorização. As duas questões em aberto ao final deste documento **seguem em aberto** — a aprovação não as decidiu |

Transcrito de decisão humana explícita de 2026-08-22, dada após a rendição e as capturas
serem entregues e abertas. Nenhum agente aprova design, inclusive o que produziu o pacote.
Aprovar esta revisão não aprova a seguinte: pacote materialmente alterado é revisão nova e
precisa de registro próprio.

## Artefato

| Arquivo | O que é |
| --- | --- |
| [`disponibilidade.html`](disponibilidade.html) | A rendição autocontida. Abre no navegador sem build, sem rede e sem servidor. |
| [`00-pagina-inteira.png`](00-pagina-inteira.png) | Todos os estados numa imagem |
| [`01-normal.png`](01-normal.png) | Estado normal — três jornadas com seu estado de ambiente, formulário de autorização e lista com um cliente autorizado e um revogado |
| [`02-vazio.png`](02-vazio.png) | Nenhum cliente autorizado ainda |
| [`03-carregando.png`](03-carregando.png) | Leitura em curso |
| [`04-recusa.png`](04-recusa.png) | Recusa do servidor: jornada que não está em piloto |
| [`05-sem-papel.png`](05-sem-papel.png) | Conta sem `platform_operator` |
| [`06-reservado.png`](06-reservado.png) | Bloco reservado, desenhado para segurar espaço e **não** entregue nesta fatia |

As imagens acompanham o HTML de propósito: a rendição depende de fonte, navegador e
plataforma, e a captura congelada é o que a aprovação de fato referencia.

## Decisões que este pacote carrega

1. **A seção mora na tela de Plataforma, abaixo da autorização de IA** — não em tela nova.
   As duas respondem à mesma pergunta ("o que este cliente pode usar") e são administradas
   pelo mesmo papel.
2. **O estado do ambiente é mostrado, mas não é editável aqui.** Ligar ou desligar uma
   jornada é alterar configuração e publicar. A tela diz isso por escrito, para ninguém
   procurar um interruptor que não existe.
3. **A tela age só onde tem efeito: no piloto.** Autorizar um cliente numa jornada
   `liberada` ou `indisponível` é recusado pelo servidor, com a frase por extenso.
4. **A autorização é nominal e reversível, no molde da autorização de IA**: referência de
   contrato obrigatória, quem autorizou, quando, e revogação que não apaga o registro.
5. **Revogado continua na lista**, com a data da revogação — sumir apagaria a trilha.
6. **Cor nunca é o único indicador**: cada pastilha tem o texto do estado ao lado.

## Procedência de cada valor visual

Tudo abaixo é **citação** do sistema existente, não valor novo:

| Elemento | De onde vem |
| --- | --- |
| Tokens de cor, tipografia e raio | `apps/web/src/styles.css`, bloco `:root` — copiados verbatim |
| Cartão de duas colunas | `.authenticated-workspace`, a mesma da autorização de IA |
| Rótulo em caixa alta | `.eyebrow` |
| Texto auxiliar | `.field-hint` |
| Botões | `.button` e `.button.project-action` |
| Formulário | `.upload-form` |
| Lista de clientes | `.project-list` |
| Pastilha verde (`LIBERADA`) | `.ready` |
| Pastilha âmbar (`PILOTO`) | `.blocked` |
| Faixa de erro | `.app-alert` |

**Único valor novo, e é o que está sendo decidido:** a terceira pastilha, `.neutro`, para o
estado `INDISPONÍVEL`. Ela não introduz cor nova — usa `--ink-secondary` sobre
`--surface-sunken`, ambos já no sistema. Existe porque as duas pastilhas atuais são
"positivo" e "atenção", e um módulo que não existe neste ambiente não é nenhum dos dois.

## Fronteira entre entregue e reservado

**Entregue nesta fatia**: os estados 1 a 5 — ler o estado das jornadas, autorizar um cliente
numa jornada em piloto, revogar, e os estados de vazio, carregando, recusa e sem papel.

**Reservado** (estado 6, desenhado com traço tracejado e opacidade reduzida): o histórico
completo de autorizações por tenant e jornada. Torna-se real quando a auditoria do
entitlement virar tela, que é a F-017 do roadmap. Não é construído aqui.

## O que a aprovação desta revisão NÃO cobre

- **A copy final.** Os textos são proposta do agente, não linguagem estabelecida do produto.
  Aprovação visual não é aprovação de texto.
- **O estado padrão de uma jornada** quando o ambiente não declara nada. É decisão de
  comportamento, registrada como premissa no [plano](../plan.md), não decisão de tela.
- **A fatia 1** (backend), que não tem superfície nova e não passa por este gate.
- **O nome das jornadas na tela** ("Croqui", "Medição", "Orçamento") — vêm do seletor que já
  existe e não são decididos aqui.
- **Qualquer regra de autorização**: a tela mostra e administra; quem autoriza é o servidor.

## Questões em aberto

1. A lista deve mostrar **todos** os tenants conhecidos, ou só os que têm autorização em
   alguma jornada? O mock mostra só os que têm. Mostrar todos facilita achar um cliente
   novo, mas alonga a lista sem informação.
2. Revogar deve pedir confirmação? O mock não pede — revogar é reversível pelo botão ao
   lado, e a trilha registra as duas coisas.
