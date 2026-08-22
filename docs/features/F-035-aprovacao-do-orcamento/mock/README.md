# Design Approval Package — F-035, aprovação nominal do orçamento

Classification: INTERFACE_CHANGE  
Revision: 1  
Status: Pending approval  
Date: 2026-08-22  
Produced by: agente (Claude Code)

> Governado por [design-approval](../../../engineering-os/workflows/design-approval.md). Este
> artefato é evidência para um gate humano. Não é implementação e não deve ser copiado para
> código de aplicação.
>
> O comportamento que estas telas mostram é do
> [ADR-0046](../../../adr/0046-aprovacao-do-orcamento-base.md), ainda `Proposed`. **Os dois
> gates são independentes**: aprovar este desenho não aceita o ADR, e aceitar o ADR não
> aprova este desenho.

## Registro de aprovação

| Campo | Valor |
| --- | --- |
| O que se pede aprovar | a composição visual da revisão 1 — os dez estados capturados e as sete decisões listadas em "Decisões que este pacote carrega" |
| Aprovado por | _pendente_ |
| Data | _pendente_ |
| Revisão | 1 |
| Explicitamente **não** coberto | a copy final (os textos são proposta do agente e carregam regra de domínio); o comportamento, que é do ADR-0046; os códigos de erro e status, que são do plano; o formato da data e do digest curto |

Nenhum agente aprova design, inclusive o que produziu o pacote. Aprovar esta revisão não
aprova a seguinte: pacote materialmente alterado é revisão nova e precisa de registro
próprio.

## Artefato

| Arquivo | O que é |
| --- | --- |
| [`aprovacao.html`](aprovacao.html) | A rendição autocontida. Abre no navegador sem build, sem rede e sem servidor. |
| [`00-pagina-inteira.png`](00-pagina-inteira.png) | Todos os estados numa imagem |
| [`01-montado-nao-assinado.png`](01-montado-nao-assinado.png) | O estado que hoje não existe: pronto e não despachável |
| [`02-ato-primeiro-passo.png`](02-ato-primeiro-passo.png) | O ato de aprovar, com as consequências ditas antes |
| [`03-ato-confirmar.png`](03-ato-confirmar.png) | Segundo passo: a confirmação, com a consequência repetida |
| [`04-aprovado-nao-despachado.png`](04-aprovado-nao-despachado.png) | Assinado, e ainda não enviado |
| [`05-aprovacao-caduca.png`](05-aprovacao-caduca.png) | O orçamento mudou sob a assinatura; os dois digests lado a lado |
| [`06-auto-aprovacao-recusada.png`](06-auto-aprovacao-recusada.png) | Quem montou não assina |
| [`07-sem-papel-aprovador.png`](07-sem-papel-aprovador.png) | Lê o estado, não opera o ato |
| [`08-despacho-e-auditoria.png`](08-despacho-e-auditoria.png) | Os quatro passos do despacho e a auditoria que reprova |
| [`09-despachado.png`](09-despachado.png) | Publicado — só aqui o link existe |
| [`10-reservado.png`](10-reservado.png) | Envio por e-mail/Drive, **não** entregue nesta feature |

## Decisões que este pacote carrega

1. **O ato é o mesmo da medição, deliberadamente.** `.ato`, `.ato-identidade`,
   `.ato-confirmacao`, `.registro` e `.digest-par` vêm verbatim do pacote aprovado da
   [F-028](../../F-028-boletim-medicao-web/mock/README.md). Duas assinaturas no mesmo
   produto têm de **ler como assinatura**; inventar uma forma nova aqui faria a mesma
   responsabilidade parecer duas coisas diferentes.

2. **Aprovar e despachar são atos separados, e a tela mostra isso.** A tela 4 é o estado
   entre os dois — assinado e não enviado. Fundir os botões economizaria um clique e
   apagaria a distinção que a feature existe para criar.

3. **A identidade é mostrada, nunca digitável.** Não há campo de nome. O texto diz por quê:
   o servidor lê a identidade do token e recusa qualquer nome que venha do cliente.

4. **A recusa de auto-aprovação explica a regra, não só nega.** A tela 6 nomeia quem montou
   e diz que acumular papéis não contorna — porque a primeira reação de quem é recusado é
   procurar o papel que falta.

5. **A caducidade mostra os dois digests, e a palavra vem antes da cor.** A etiqueta escrita
   ("Aprovação caduca") é a marca; o tracejado âmbar é redundância dela. Quem não distingue
   a cor lê a palavra.

6. **O despacho é passo a passo escrito, não barra de progresso.** Três dos quatro passos
   acontecem **antes** de existir arquivo publicado, e uma barra esconderia justamente isso.
   A faixa de auditoria reprovada afirma por extenso que nada foi publicado e que a
   aprovação continua válida.

7. **O link da planilha só existe depois do despacho.** Hoje ele aparece assim que a
   planilha existe; aqui ele passa a ser consequência do ato, e o digest fica ao lado dele.

## Procedência de cada valor visual

| Elemento | De onde vem |
| --- | --- |
| Tokens de cor, tipografia e raio | `apps/web/src/styles.css`, bloco `:root` — verbatim |
| Topbar, `eyebrow`, `.painel`, `.hint`, barra de etapas | `apps/web/src/orcamento/styles.css` (F-020) |
| `.ato`, `.ato-etiqueta`, `.ato-identidade`, `.ato-confirmacao` | `apps/web/src/medicao/styles.css` (F-028) — verbatim |
| `.registro`, `.registro-caduca`, `.registro-etiqueta`, `.digest-par` | idem, F-028 — verbatim |
| `.progresso`, `.passo-estado` | idem, F-028 — verbatim |
| Faixa de erro `.app-alert` | a mesma da jornada |

**Único valor novo:** o selo do estado do despacho (`NÃO DESPACHADO` / `DESPACHADO EM …`).
Nenhuma cor nova entra no sistema — reusa `--surface-sunken` e `--ink-secondary`. É um selo
de estado da rodada, e por isso lê como o selo do regime da F-033, não como os selos
preenchidos que indicam origem de preço.

## Fronteira entre entregue e reservado

**Entregue nesta feature**: telas 1 a 9 — o estado montado-e-não-assinado, o ato em dois
passos, o registro, a caducidade, as duas recusas, o despacho com auditoria e o estado
despachado.

**Reservado** (tela 10, tracejada e com opacidade reduzida): enviar a planilha aprovada a um
destinatário por e-mail ou Drive. Fora de escopo por decisão humana de 2026-08-22 — não há
provedor de e-mail no projeto, o mesmo motivo pelo qual a F-008 está `BLOCKED`. Não é
construído aqui, e o `Out of Scope` do contrato diz o mesmo.

## Questões abertas

1. **Onde a etapa entra na jornada.** O pacote propõe etapa nova, "Aprovação e despacho",
   depois de "BDI e montagem" — e a etapa "Planilha" de hoje é absorvida por ela, já que a
   planilha deixa de existir antes do despacho. A alternativa seria manter "Planilha" e dar
   a ela dois atos. Decide no gate.
2. **O rótulo do estado.** "Despachado" é proposta; "Publicado" e "Enviado" foram
   considerados. "Enviado" foi descartado por prometer envio, que é justamente o que está
   reservado.
