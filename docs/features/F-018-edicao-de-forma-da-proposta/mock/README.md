# Design Approval Package — F-018, corrigir a forma da proposta na tela

Classification: INTERFACE_CHANGE  
Revision: 1  
Status: **Approved (2026-08-27)**  
Date: 2026-08-27  
Produced by: agente (Claude Code)

> Governado por [design-approval](../../../engineering-os/workflows/design-approval.md). Este
> artefato é evidência para um gate humano. Não é implementação e não deve ser copiado para
> código de aplicação. **Nenhum agente aprova design.**
>
> **Aprovado por ato humano em 2026-08-27**, registrado abaixo. Com este gate e o
> [ADR-0050](../../../adr/0050-correcao-humana-de-forma-como-proposta-derivada.md) (aceito em
> 2026-08-23), a [F-018](../feature.md) sai de `BLOCKED`.

## Registro de aprovação

| Campo | Valor |
| --- | --- |
| O que foi aprovado | a composição visual da revisão 1 e as nove decisões listadas em "Decisões que este pacote carrega" |
| Aprovado por | Daniel Campos |
| Data | 2026-08-27 |
| Revisão aprovada | 1 |
| Explicitamente **não** coberto | a copy final; os nomes, números e horários das capturas; a paleta de estado de leitura, que não muda; as decisões do [ADR-0050](../../../adr/0050-correcao-humana-de-forma-como-proposta-derivada.md), que foram gate próprio e já exercido |

Aprovar esta revisão não aprova a seguinte: pacote materialmente alterado é revisão nova e
precisa de registro próprio.

## Artefato

| Arquivo | O que é |
| --- | --- |
| [`correcao-de-forma.html`](correcao-de-forma.html) | A rendição autocontida. Abre no navegador sem build, sem rede e sem servidor. |
| [`00-pagina-inteira.png`](00-pagina-inteira.png) | Os nove estados numa imagem |
| [`01-decisoes.png`](01-decisoes.png) | O ato "Corrigir forma" ao lado de aceitar e rejeitar |
| [`02-mover-vertice.png`](02-mover-vertice.png) | Arrasto de vértice, com a observação original em traço fantasma |
| [`03-inserir-remover.png`](03-inserir-remover.png) | Vértice inserido no segmento; remoção com piso de dois vértices |
| [`04-uniao-de-fragmentos.png`](04-uniao-de-fragmentos.png) | Duas `line` viram uma polilinha com o recuo — o caso Guaxindiba V3 |
| [`05-justificativa.png`](05-justificativa.png) | Justificativa obrigatória antes de gravar |
| [`06-gravada.png`](06-gravada.png) | A correção ao lado da observação, com os superados recolhidos |
| [`07-conflito.png`](07-conflito.png) | Recusa por versão, com o rascunho preservado |
| [`08-sem-derivacao.png`](08-sem-derivacao.png) | Recusa de correção que não cita forma de origem |
| [`09-nao-corrigivel.png`](09-nao-corrigivel.png) | Proposta já decidida e conta sem papel de revisão |

O caso desenhado é o real que originou a feature: o muro do Guaxindiba V3 com recuo
**4,80 → 3,30**, que a extração paga (`geometry-extraction@2.0.1`) entregou como duas `line`
retas com um vão entre elas.

## Decisões que este pacote carrega

1. **A correção vive na etapa `Decisões`, não numa etapa nova.** É o Unknown 4 do
   [Feature Contract](../feature.md). Corrigir forma não é decisão de leitura, mas é decisão
   **sobre proposta** — e proposta é decidida ali. Uma quinta etapa para um ato que acontece
   dentro de outro custaria navegação em troca de nada.
2. **O ato aparece como terceiro botão, ao lado de aceitar e rejeitar**, e não escondido em
   menu: hoje ele é o caminho que não existe, e um caminho que ninguém encontra continua não
   existindo.
3. **A observação original permanece desenhada, em traço fantasma pontilhado**, durante toda a
   correção. É a tradução visual da decisão 4 do ADR-0050 — o fragmento não é consumido.
4. **A correção tem traço próprio: contínuo, azul, mais espesso.** Proposta de máquina é
   tracejada laranja (`.proposal-shape`, `styles.css:1738`) e continua sendo. Cor **não** é o
   único indicador: o traço (contínuo × tracejado × pontilhado), o selo escrito
   ("origem: correção humana") e o rótulo na lista dizem a mesma coisa sem cor nenhuma.
5. **A precisão é declarada em todo estado do rascunho**: "nasce não resolvida · não exporta".
   Uma forma desenhada à mão parece mais confiável que uma bruta, e é justamente o que ela não
   é — decisão 5 do ADR-0050.
6. **A união mostra a derivação como lista de formas citadas**, com o ato de tirar uma delas.
   Sem forma citada, a gravação é recusada (estado 08): é a fronteira entre corrigir e
   desenhar.
7. **O rascunho vive só na tela e não sobrevive ao conflito de versão** — mas também não é
   descartado por ele (estado 07). Nada é gravado pela metade, e ninguém reescreve quatro
   vértices por causa de uma versão.
8. **"Superada" é derivada da derivação, nunca um estado gravado** (decisão 4 do ADR-0050): a
   lista recolhe as formas citadas por alguma correção, e o ato "mostrar" as traz de volta.
9. **Proposta já decidida não é corrigível** (estado 09), com o motivo escrito. Decisão
   registrada é imutável — é a regra que a revisão já tem.

## Proveniência de cada valor visual

| Valor | De onde vem |
| --- | --- |
| `--bg`, `--surface`, `--ink`, `--line`, `--accent*`, `--muted` | `apps/web/src/styles.css` — identidade "Grafite técnico" |
| Laranja `#bd7a20` tracejado da proposta de máquina | `.proposal-shape` (`styles.css:1738`) |
| Azul `#166a83` da forma selecionada | `.proposal-shape.selected` (`styles.css:1748`) |
| Verde `--accent-text` da forma aceita | `.proposal-shape.accept` (`styles.css:2233`) |
| Vermelho `#a33d32` da recusa | `.proposal-shape.reject` (`styles.css:2238`) |
| Pílula de etapa, painel, botões, avisos | Padrões já usados na revisão (`CroquiApp.tsx`) |
| **NOVO** — azul `#1f5fa8` contínuo da correção humana, e a família `--correcao*` | Introduzido por este pacote. É o que está sendo aprovado. Escolhido por não colidir com nenhum dos cinco significados já em uso (proposta, selecionada, aceita, recusada, amarração `#7a3fa0`). |
| **NOVO** — alça de vértice (círculo branco com contorno azul; preenchido quando ativo) | Introduzido por este pacote |
| **NOVO** — traço pontilhado esmaecido da forma superada | Introduzido por este pacote, derivado do laranja existente |

## Fronteira entre entregue e reservado

**Entregue nesta feature:** os nove estados acima — mover vértice, inserir/remover vértice,
unir fragmentos, justificativa, gravação, os dois estados de recusa e o não-corrigível.

**Reservado, desenhado para segurar lugar** (aparece hachurado no estado 05): aceitar a
correção no mesmo ato de gravá-la. Hoje aceitar exige calibração confirmada e é fluxo próprio;
o atalho só vira real se uma decisão futura o pedir.

## O que a aprovação não cobre

- A **copy final** de rótulos, avisos e mensagens de recusa.
- Os **nomes, números e horários** das capturas, que são sintéticos.
- A **tolerância de "vértice movido demais"** (Unknown 3 do contrato): este pacote **não**
  propõe limite numérico. A posição é declarada em texto — "12 px do ponto observado" — e
  nenhum limiar é aplicado, porque não existe número calibrado para separar ajuste de forma
  nova. Se um limiar for desejado, ele é decisão nova.
- O comportamento em **toque** e o desempenho do arrasto em cena com muitas formas.
- Qualquer mudança no **portão de exportação**, que continua sendo `ensure_exportable()`.
