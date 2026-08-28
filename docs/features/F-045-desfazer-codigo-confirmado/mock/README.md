# Design Approval Package — F-045, desfazer um código confirmado

Classification: INTERFACE_CHANGE  
Revision: 2  
Status: **Approved — revisões 1 e 2 (2026-08-28)**  
Date: 2026-08-28  
Produced by: agente (Claude Code)

> Governado por [design-approval](../../../engineering-os/workflows/design-approval.md). Este
> artefato é evidência para um gate humano. Não é implementação e não deve ser copiado para
> código de aplicação. **Nenhum agente aprova design.**

## O gate que vem antes deste

A **semântica** da revogação está no
[ADR-0061](../../../adr/0061-revogacao-de-codigo-confirmado.md), **aceito em 2026-08-28**:
revogar é
decisão nova, o par sai do conjunto corrente e fica em `revocations`, o pacote do elemento
**reabre** e a observação de precedente que aquele fechamento gravou é **removida** na mesma
transação.

Este pacote decide a **forma** dessas decisões na tela. Se o ADR mudar, o pacote muda com ele.

## Registro de aprovação

| Campo | Valor |
| --- | --- |
| O que se aprova | a composição dos cinco estados e as seis decisões abaixo |
| Aprovado por | Daniel Campos |
| Data | 2026-08-28 |
| Revisão | 1 |

### Revisão 2 — o mesmo ato na medição (2026-08-28)

| Campo | Valor |
| --- | --- |
| O que se aprova | o estado 6: a superfície de desfazer na jornada de **medição**, que a revisão 1 registrou como questão aberta |
| Por que | a rota irmã existe e é testada desde a revisão 1, e ficou sem tela. Uma rota sem superfície é uma capacidade que só o time sabe que existe |
| Aprovado por | Daniel Campos |
| Data | 2026-08-28 |
| Revisão | 2 |
| O que **não** muda | os estados 1 a 5 e as seis decisões da revisão 1; o ato, a copy e o fluxo são os mesmos — o que muda é onde eles ficam, porque ali o pacote era uma frase e vira lista |
| Explicitamente **não** coberto | a copy final; os rótulos, códigos e preços das capturas, que são sintéticos; **o que acontece quando o orçamento já foi aprovado** (unknown 1 da feature, decisão do dono); e o ato inverso, desfazer uma rejeição, que está fora de escopo |

## Artefato

| Arquivo | O que é |
| --- | --- |
| [`desfazer-codigo.html`](desfazer-codigo.html) | A rendição autocontida. Abre no navegador sem build, sem rede e sem servidor. |
| [`00-pagina-inteira.png`](00-pagina-inteira.png) | Os cinco estados numa imagem |
| [`01.png`](01.png) | Hoje: o pacote do elemento não tem saída |
| [`02.png`](02.png) | Desfazer, com o motivo escrito e o efeito à vista |
| [`03.png`](03.png) | Pacote fechado: desfazer reabre, e isso vai escrito antes do clique |
| [`04.png`](04.png) | Depois: o que foi desfeito continua à vista |
| [`05.png`](05.png) | As quatro recusas, em português |
| [`06-na-medicao.png`](06-na-medicao.png) | **Revisão 2** — o mesmo ato na jornada de medição |

## Superfícies e estados incluídos

| Superfície | Estado | No pacote |
| --- | --- | --- |
| Pacote do elemento | código confirmado, pacote aberto | sim (02) |
| Pacote do elemento | código confirmado, pacote **fechado** | sim (03) |
| Pacote do elemento | depois da revogação, com a lista de desfeitos | sim (04) |
| Caixa de desfazer | motivo em branco | sim (05) — recusa nomeada |
| Caixa de desfazer | conflito de versão e par já desfeito | sim (05) |
| Rodada no regime antigo (um código por elemento) | sim (05) — o ato não se aplica |
| Pacote do elemento na **medição** | a frase do pacote vira lista, com um ato por código | sim (06) |
| Pacote do elemento | carregando | **não** — a etapa já tem o seu, e a revogação não introduz espera nova |

## Proveniência dos valores visuais

| Valor | Origem | Novo? |
| --- | --- | --- |
| Tokens de superfície, tinta e linha | `apps/web/src/styles.css` | não |
| `.botao-secundario`, `.selo`, `.codigo-card`, `.campo`/`textarea` | `apps/web/src/orcamento/styles.css` (etapa Códigos) | não |
| Âmbar `#7c5210` do aviso de efeito | o mesmo do aviso de precedente fraco (F-044) | não |
| **Cor nova** | — | **nenhuma** |

Nenhuma cor nova é introduzida por este pacote, e isso é decisão (nº 2 abaixo), não acaso.

## Decisões que este pacote carrega

1. **O ato mora no cartão do código, dentro do pacote do elemento.** É onde a pessoa está
   olhando quando descobre o engano, e é o único lugar onde o par `(elemento, código)` —
   que é a identidade da decisão — está inteiro à vista.

2. **Desfazer não ganha cor própria.** A folha não tem afordância de destrutivo, e a
   rejeição de código, que já é recusa, usa o botão neutro ("Rejeitar com nota"). Inventar um
   vermelho aqui criaria vocabulário que o resto da tela não fala. O que distingue o ato é a
   **palavra** e o aviso do efeito.

3. **O motivo é obrigatório e é campo, não caixa de confirmação.** Desfazer é ato que alguém
   vai auditar; um "tem certeza?" não deixa rastro nenhum. A obrigatoriedade é a mesma da
   rejeição de código, e é ela que mantém a confirmação séria — desfazer barato demais
   convidaria a decidir sem olhar.

4. **O efeito vai escrito antes do clique, em três linhas.** O que sai, o que fica
   registrado, e que o precedente daquele código desaparece para as próximas praças. A
   terceira linha é a que ninguém adivinharia sozinho.

5. **Pacote fechado avisa que reabre, com o botão dizendo isso.** "Desfazer e reabrir o
   pacote" no lugar de "Desfazer o código". Reabrir em silêncio é a pior versão disto: a
   exportação passa a recusar aquele elemento, e a pessoa descobriria três telas depois.

6. **O desfeito continua à vista, numa lista própria do elemento.** "Nunca decidido" e
   "decidido e desfeito" não podem parecer a mesma coisa. A lista mostra o código riscado, o
   motivo, quem e quando — do conjunto corrente, sem obrigar ninguém a comparar revisões.

7. **Na medição, a frase do pacote vira lista** *(revisão 2)*. Ali o pacote era uma linha de
   texto com os códigos entre parênteses, e não havia onde pendurar um ato por código. Vira
   lista, e cada código recebe o mesmo ato do orçamento — mesma caixa, mesma copy, mesmo
   aviso de reabertura. Duas coisas **não** atravessam, e as duas são do domínio: a linha
   "apaga o precedente…", porque o índice é do orçamento-base e seria falsa ali, e a recusa
   depois da aprovação, porque a aprovação nominal é do orçamento. Fora isso, forma única de
   propósito: duas formas para o mesmo ato criariam dois vocabulários para a mesma coisa.

## Questões abertas

- **A copy final** de todos os textos, inclusive as quatro recusas.
- **O que fazer depois da aprovação do orçamento** (unknown 1 da feature): a aprovação cita a
  revisão, e revogar depois dela deixaria a citação apontando para um conjunto que não existe
  mais. A proposta do ADR é recusar; a decisão é do dono.
- **Se a lista de desfeitos deve aparecer quando está vazia** — o pacote a desenha só quando
  há o que mostrar, pela mesma regra de "nenhum controle inerte" que a F-044 seguiu.
- ~~**Se o mesmo ato deve existir na jornada de medição com a mesma forma.**~~ — resolvido
  pela **revisão 2**: existe, com a mesma forma, menos as duas linhas que só valem no
  orçamento-base.

## Notas para quem implementar

- **Intencional e a preservar**: o motivo obrigatório; as três linhas de efeito; o botão que
  muda de texto quando o pacote está fechado; a lista de desfeitos; a ausência de cor nova.
- **Ilustrativo, e não é especificação**: rótulos, códigos, preços, o instante e o nome de
  quem desfez.
- **O que o artefato não mostra**: ordem de foco, comportamento de teclado, leitura por
  leitor de tela e o texto de erro vindo da API.
- A revogação é `POST` com `base_version` e `Idempotency-Key`, como as demais mutações da
  etapa; a resposta traz o conjunto novo, e a tela redesenha a partir dele — não remove a
  linha por conta própria.
