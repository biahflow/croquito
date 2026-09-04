# F-051 — Roteiro do gate 3: o aceite contra o croqui real

Feature: [A cota-balão encontra seu elemento](../feature.md) · Preparado pela
[T7](../tasks/T7-evidencia-e-o-caso-real.md) · Data: **2026-09-04**

Este é o passo a passo do **gate 3** da F-051: o aceite final, contra o job real do Campo da
Toca, do critério de aceite 1 do contrato — *a leitura `C=56m` com hint "B" ganha candidata
por identidade, é confirmável pelo portão de sempre e entra no solver como constraint*.

**Quem exerce é o dono.** A T7 preparou e validou este roteiro contra a fixture sintética
(cada passo abaixo foi executado no navegador, e a captura correspondente está em
[`README.md`](README.md)); ela **não** rodou nada contra o job real, e não tocou no banco
local que o guarda.

## Antes de começar

| Item | Como conferir |
| --- | --- |
| A `main` com a F-051 inteira | `git log --oneline -1` deve estar em `0aa07c0` ou depois (T6, PR #169) |
| O stack local de pé | `docker compose -f docker-compose.local.yml ps` — os três serviços saudáveis |
| As migrações `0031` e `0032` aplicadas | `make db-init` — idempotente e forward-only: aplica só as revisões que faltam e não apaga nada. Sem elas, as rotas da identidade da revisão respondem erro de coluna |
| API e SPA | `make dev` |
| O job | abra `http://localhost:5173/?job=01a068ef-…` (o id completo é o do croqui do Campo da Toca; a lista de projetos também o abre) |

Se `make check` estiver vermelho por causa da
[issue #171](https://github.com/biahflow/croquito/issues/171) (mypy em
`tests/core/test_scene.py:501`), ignore para este roteiro: é defeito de tipagem em teste, e
não afeta a API nem a tela.

## O roteiro

### 1 · Declarar o elemento "B" sobre as propostas do fecho

Na etapa **1. Decisões**, no painel **"Identidade de elemento na revisão"** (abaixo da lista
de leituras):

1. marque, em "DECLARAR ELEMENTO", **as propostas que desenham o elemento que o balão B
   nomeia** — o fecho da área. Marque todas as que forem o mesmo elemento;
2. escreva o rótulo **`B`** em "Rótulo (o que a pessoa lê)";
3. escreva a justificativa do agrupamento;
4. clique em **"Declarar elemento com N propostas"**.

O que precisa acontecer: um carimbo azul com `EL-NNN "B" declarado por <papel> em <instante>,
sobre a revisão vN`, e o elemento aparecendo em "ELEMENTOS DECLARADOS NESTA REVISÃO".
O `EL-NNN` é **cunhado pelo servidor** — se o campo aceitasse digitação, é defeito.

> Comparação: capturas [02](02-o-ato-de-declarar.png) e
> [03](03-o-elemento-declarado.png).

**Se recusar com `ELEMENT_LABEL_ALREADY_USED`**, já existe um "B" ativo neste job: use o que
existe em vez de declarar outro (o rótulo é único por job, e é a decisão 9 do DAP aprovado).

### 2 · Garantir que a leitura `C=56,00` carrega o hint estruturado "B"

Abra a leitura `C=56,00` na lista. Duas situações, e as duas são caminho previsto:

- **o chip tracejado `elemento (hint do modelo): B` aparece** → siga para o passo 3;
- **o chip não aparece** → é esperado, e não é defeito: **este pacote foi extraído antes da
  T1**, quando o rótulo do modelo ainda era achatado numa string informativa
  (`provider_review.py`), e o campo estruturado `target_entity_label` da leitura ficou vazio.
  O conserto é ato previsto, na própria decisão: escreva **`B`** no campo **"Elemento do
  balão — corrigir o hint do modelo (opcional)"**, no card da leitura. O texto de ajuda ao
  lado diz exatamente isso ("O modelo não leu rótulo de elemento nesta cota. Escrever a letra
  do balão aqui liga a cota ao elemento declarado com esse rótulo").

Corrigir o hint **recunha as candidatas da leitura** (F-051 T4), então o passo 3 vale para as
duas situações — na segunda, o grupo aparece depois que a decisão com o hint corrigido for
gravada.

### 3 · Ver a candidata por identidade

No seletor **"Associação explícita"** da leitura, deve existir um grupo escrito
**`Pela identidade — ◇ EL-NNN · B`**, acima do grupo de proximidade (se houver), com **uma
opção por proposta do elemento declarado**, e a relação "identidade declarada do elemento"
por extenso. Abaixo do seletor, o `field-hint` diz por que a candidata está ali.

O que **não** pode acontecer: grupo vazio, score, distância em pixels, ou a candidata por
identidade no lugar das de proximidade em vez de ao lado delas.

> Comparação: captura [04](04-candidata-por-identidade.png).

### 4 · Confirmar pelo portão de sempre

Escolha a proposta do elemento no seletor, escreva a justificativa e clique **"Confirmar"**.
Se a leitura já estiver decidida (o Campo da Toca foi revisado inteiro), o botão é
**"Corrigir decisão registrada"** — a retificação é o ato certo, e ela também recunha as
candidatas.

O que precisa acontecer: a decisão gravada com autor, instante e justificativa, e a
associação registrada. Nenhuma tela nova, nenhum caminho novo de escrita.

> Comparação: captura [05](05-confirmada-pelo-portao.png).

### 5 · Traçar em lote

Vá para **2. Traçado**. Na lista "Cotas confirmadas e suas amarrações", a `C=56,00` deve
aparecer como **"mede a forma …"**, e não mais como "anotação da folha — sem vão". Marque as
formas, e clique em **"Aceitar traçado (N formas)"**.

> Comparação: capturas [07](07-o-balao-amarrado-a-forma.png) e
> [08](08-a-orfa-sem-vao.png) (esta última é a fronteira honesta: balão que não casa continua
> sem vão).

### 6 · Conferir o solver e a cena — é aqui que o gate se decide

Duas leituras, nesta ordem:

1. **O resíduo**, no bloco de estado do traçado: "Traçado resolvido — N elementos exatos…"
   seguido de "**M cotas conferidas contra a geometria**; a pior diferença foi …". O `M`
   precisa **contar a `C=56,00`** — é isso que significa "entrou no solver como constraint".
   A lista abaixo mostra, cota a cota, quanto cada uma amarrou.
   > Comparação: captura [09](09-o-tracado-resolvido.png).
2. **A cena**, na etapa **3. Aprovação**, no painel "Identidade de elemento": as entidades
   criadas a partir das propostas declaradas precisam carregar **`◇ EL-NNN`**, o rótulo `B` e
   o selo "→ alimenta a medição". A letra do balão chegou à cena **sem ninguém redigitá-la**.
   > Comparação: captura [10](10-a-cena-com-a-identidade.png).

Se as duas leituras baterem, o critério de aceite 1 está satisfeito **contra o croqui real** e
o gate 3 pode ser dado como cumprido — registrando o desfecho no
[`evidence.md`](../evidence.md) da feature.

## O que pode dar errado, e o que cada coisa significa

| O que você vê | O que é | O que fazer |
| --- | --- | --- |
| A `C=56,00` aparece em **"Cotas não aplicadas ao traçado"** com um código `TRACE_SPAN_…` | O número do balão é o **fecho** (perímetro) do elemento, e o traçado amarra **vão**, não perímetro: uma leitura só não descreve os quatro lados. A F-051 entrega a identidade e a candidata; **transformar um fecho em quatro restrições é outra coisa** | Registre como achado (issue), não como falha do roteiro. A identidade e a candidata continuam válidas — o que faltou é o significado geométrico do número, que nenhuma parte desta feature promete |
| O resíduo estoura a tolerância | A cota confirmada está amarrada à forma errada, ou o `56,00` mede outra coisa que não aquele trecho | Retifique a decisão escolhendo outra proposta do grupo. O solver **nunca** deve ser "ajudado" mudando o número |
| Nenhum grupo "Pela identidade" mesmo depois do hint corrigido | O rótulo do elemento e o hint não casam. O casamento é declarado: igualdade ignorando caixa/espaços, **ou** o hint como palavra inteira do rótulo (`"B"` alcança `"B"`, `"grade B"` e `"B — fecho da área"`; **não** alcança `"fecho"`) | Renomeie o elemento para um rótulo que contenha a letra como palavra, ou corrija o hint. Nunca há parecença nem prefixo — e isso é decisão, não limitação a contornar |
| `409` de conflito ao declarar | Outra aba (ou o worker) criou revisão nova no meio | Use "Recarregar revisão atual" e repita o ato |
| As outras duas cotas-balão do Campo da Toca | A issue [#139](https://github.com/biahflow/croquito/issues/139) contou **três**; este roteiro cobre a `C=56,00`. As outras duas seguem o mesmo caminho, uma a uma | Se o referente de alguma delas **não tiver proposta** do CV, ela continua em `annotation=true`: é o fora de escopo declarado do contrato (caminho C do ADR-0063) |

## O que este roteiro NÃO faz

- Não aprova a cena, não exporta DXF e não roda a medição: o gate 3 é sobre a cota entrar no
  solver e a identidade chegar à cena.
- Não chama provider pago em ponto nenhum. Nenhum passo aqui reextrai leitura.
- Não altera nada fora do job em que você o executar.
