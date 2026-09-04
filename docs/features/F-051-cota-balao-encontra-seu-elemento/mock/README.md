# Design Approval Package — F-051, a cota-balão encontra seu elemento

Classification: INTERFACE_CHANGE  
Revision: 1  
Status: **Approved (2026-09-04)**  
Date: 2026-09-04  
Produced by: agente (Claude Code)

> Governado por [design-approval](../../../engineering-os/workflows/design-approval.md). Este
> artefato é evidência para um gate humano. Não é implementação e não deve ser copiado para
> código de aplicação. **Nenhum agente aprova design.**
>
> O outro gate desta feature — o aceite do
> [ADR-0063](../../../adr/0063-identidade-de-elemento-nasce-na-revisao.md) — **já foi
> satisfeito por ato humano em 2026-09-04** (Daniel Campos, pelo chat). Este pacote **foi
> aprovado por ato humano em 2026-09-04** (Daniel Campos, pelo chat, após o merge do PR
> #157), com as **duas leituras confirmadas no mesmo ato**: rótulo de elemento único por job
> na revisão (decisão 9) e revogação que não desfaz associação já confirmada (decisão 8).
> Com os dois gates passados, a F-051 entra em planejamento.

## Registro de aprovação

| Campo | Valor |
| --- | --- |
| O que se aprova | a composição visual da revisão 1 e as doze decisões listadas em "Decisões que este pacote carrega", incluindo a confirmação explícita das duas leituras (decisões 8 e 9) |
| Aprovado por | Daniel Campos |
| Data | 2026-09-04 |
| Revisão | 1 |
| Explicitamente **não** coberto | a copy final; os códigos `problem+json` das recusas; a normalização do casamento de rótulo (fatia 1, com o dado do job de referência); onde a declaração persiste no pacote versionado; os números/nomes sintéticos — a lista completa em "O que a aprovação não cobre" |

Aprovar esta revisão não aprova a seguinte: pacote materialmente alterado é revisão nova e
precisa de registro próprio.

## Artefato

| Arquivo | O que é |
| --- | --- |
| [`cota-balao-encontra-seu-elemento.html`](cota-balao-encontra-seu-elemento.html) | A rendição autocontida. Abre no navegador sem build, sem rede e sem servidor. |
| [`00-pagina-inteira.png`](00-pagina-inteira.png) | Os nove estados numa imagem |
| [`01-a-cota-balao-morre-como-anotacao.png`](01-a-cota-balao-morre-como-anotacao.png) | Hoje: a nota no alto, o referente do outro lado da folha, e o custo do caminho honesto |
| [`02-o-hint-deixa-de-ser-achatado.png`](02-o-hint-deixa-de-ser-achatado.png) | O hint do modelo vira campo da leitura, tracejado e corrigível |
| [`03-a-sugestao-assistida.png`](03-a-sugestao-assistida.png) | Os rótulos do modelo viram proposta de elemento — com uma errada de propósito |
| [`04-o-ato-de-declarar.png`](04-o-ato-de-declarar.png) | O ato humano: EL cunhado, carimbo com papel, namespace único, renomear/revogar |
| [`05-candidatas-por-identidade.png`](05-candidatas-por-identidade.png) | O seletor com o grupo "pela identidade" ao lado do de proximidade — e o h=4,40 que o humano mantém anotação |
| [`06-solver-e-transporte.png`](06-solver-e-transporte.png) | A confirmação entra no solver pelo caminho existente; a entidade nasce com ◇ EL-002 |
| [`07-fronteiras-honestas.png`](07-fronteiras-honestas.png) | Hint que não casa → tela de hoje; balão sem proposta → anotação continua |
| [`08-recusas.png`](08-recusas.png) | Três recusas novas e três coisas que não mudam |
| [`09-controle.png`](09-controle.png) | Sem declaração, a revisão é a de hoje |

Capturas em 1280 px de largura, `deviceScaleFactor` 2, Chromium — a mesma proporção das dos
pacotes F-040 e F-047.

### Os números, e por que eles fecham

A obra é a **Praça do Cedro**, a fixture **sintética** inventada para o pacote da F-047 —
nenhum dado de cliente. O caso espelha o padrão do corpus real (a nota de cota-balão ligada
por letra ao elemento do outro lado da folha), com números que fecham: a área de lazer mede
`16,00 × 12,00` e o fecho dela `2 × (16,00 + 12,00) = 56,00` — exatamente o `C = 56,00` da
nota `(B)`. No estado 06, a cadeia `16,00 + 12,00 + 16,00 + 12,00 = 56,00` dá resíduo `0,00`
contra a constraint.

## Decisões que este pacote carrega

1. **O hint do modelo vira campo visível da leitura — tracejado, nomeado "hint do modelo" e
   corrigível.** Hoje `target_hint` existe no contrato e é achatado para uma string que a tela
   nem exibe; o estado 02 mostra o campo estruturado no card da leitura, e "corrigir hint"
   como ato de decisão registrado — a **decisão 4 do ADR-0063** tornada visível. O chip é
   tracejado como toda sugestão do sistema: hint nunca se veste de identidade.

2. **A sugestão assistida de identidade usa o molde do painel que a cena já tem (F-047 T6),
   sem inventar outro.** Aviso fixo por escrito, selo `⚙ proposta · unresolved` tracejado,
   recusa com motivo obrigatório, e **um único caminho de escrita** — "declarar a partir da
   proposta" só semeia a seleção do ato, nunca grava. É a **decisão 1 do ADR-0063** no idioma
   já aprovado e implementado.

3. **Uma sugestão errada de propósito** (o modelo leu o balão do playground espelhado e
   rotulou «grade B») mostra o custo de declarar sem olhar: a cota `C = 56,00` ganharia
   candidata para uma grade que ela não mede. Quem declara ajusta a seleção antes do ato —
   e é por isso que rótulo de modelo não declara nada.

4. **As candidatas por identidade entram no `<select>` que já existe, num grupo rotulado por
   escrito, acima do grupo da proximidade — ao lado, nunca no lugar.** Sem score e sem
   distância na tela, porque o seletor real nunca mostra nem decide por eles; a distinção é
   texto (o rótulo do grupo e a relação "pela identidade do elemento"), não cor. A narrativa
   dos "≈ 2.100 px" fica neste pacote, não no produto.

5. **O porquê do casamento é dito num `field-hint` sob o seletor** — o mesmo idioma dos hints
   que a tela já tem — e **o recorte da folha continua na tela**: a mitigação do risco "rótulo
   errado do modelo guiando o revisor" é quem confirma olhar o desenho, não o hint.

6. **A identidade oferece; o humano decide o que constrange.** O `h = 4,40` da mesma nota
   também ganha candidatas pela identidade, e o revisor o mantém como anotação — altura não é
   geometria de planta. Nenhuma regra automática toma essa decisão (estado 05).

7. **O ato de declarar é o da F-047, uma etapa antes**: EL cunhado pelo sistema em campo
   somente-leitura, rótulo humano ao lado e nunca no lugar, carimbo com **papel profissional**
   (nunca usuário) e instante — o idioma implementado do painel da cena, mantido. O namespace
   é um só por job: o contador continua nos atos pós-solve.

8. **Renomear e revogar são atos declarados e registrados**, como a declaração; a identidade
   revogada não sai do histórico e o ref não é reaproveitado. **Leitura deste pacote, marcada
   como tal:** revogar a identidade não desfaz associação já confirmada por ela — corrigir
   associação é retificação de decisão, o ato que a revisão já tem. O gate humano confirma ou
   inverte.

9. **Rótulo de elemento único por job na revisão** (estado 08): declarar um segundo "B" é
   recusado apontando o existente. **Leitura deste pacote, marcada como tal:** o casamento por
   identidade precisa de referente inequívoco, e o corpus real mostra balões particionando, não
   repetindo. O gate humano confirma ou inverte.

10. **As fronteiras aparecem como texto, não como controle inerte** (estado 07): hint sem
    elemento declarado → a tela de hoje, sem candidata nova e com casamento exato, nunca fuzzy
    silencioso; balão cujo referente o CV não propôs → `annotation=true` continua, com o custo
    escrito. O segundo passe pós-traçado (caminho C do ADR-0063) fica **registrado como
    evolução futura e não segura lugar na tela**.

11. **Nenhuma tela nova de solver** (estado 06): a cota confirmada entra como toda associação
    confirmada entra, e o efeito visível é a entidade nascendo com ◇ EL e rótulo na cena — o
    elo croqui → cena → quantitativo fechado sem redigitar a letra.

12. **Sem declaração, a revisão é a de hoje** (estado 09): seletor com os grupos de sempre,
    nenhum grupo vazio de identidade, painel de sugestões que diz por escrito quando não tem o
    que sugerir, e os artefatos de saída idênticos. A F-051 é aditiva.

## Superfícies e estados

| Superfície | Estado | No pacote |
| --- | --- | --- |
| Etapa de decisões — seletor de associação | com identidade / sem casamento / controle | sim (05, 07, 09) |
| Etapa de decisões — card da leitura | hint estruturado / corrigir | sim (02) |
| Painel de sugestões de elemento (revisão) | propostas / vazia / falha de leitura | sim (03 — vazia e falha como texto, o padrão do painel da cena) |
| Ato de declarar / renomear / revogar | sucesso / recusas | sim (04, 08) |
| Efeito no solver e transporte | sucesso | sim (06) |
| Recusas (rótulo duplicado, sem proposta, papel) | erro | sim (08) |
| Conflito otimista (`base_version`) | erro | sim (08 — o idioma "Recarregar revisão atual" que a tela já tem, intocado) |
| Carregamento / erro de API / sessão perdida | — | **fora, com razão**: a jornada já tem esses estados (banner de alerta, status do job, porta de login) e esta feature não os altera |

## Fronteira entre entregue e reservado

**Entregue nesta feature:** os nove estados — o problema de hoje, o hint estruturado, a
sugestão assistida, o ato de declarar com renomear/revogar, as candidatas por identidade no
seletor, o efeito no solver com o transporte para a cena, as duas fronteiras honestas, as
recusas e o controle.

**Reservado, sem segurar lugar na tela:** o **segundo passe pós-traçado** (ligar anotação
confirmada a elemento da cena e re-resolver — caminho C do ADR-0063). Diferente dos pacotes
anteriores, aqui **nada é desenhado hachurado**: o estado 07 registra a evolução por escrito e
a composição não reserva espaço, porque quando vier é feature própria com gate próprio.

## O que a aprovação não cobre

- A **copy final** de rótulos, avisos, recusas e do rótulo da relação nova ("pela identidade
  do elemento" é proposta deste pacote).
- Os **códigos `problem+json`** exatos das recusas novas — contrato do planejamento, não do
  design.
- Os **números, nomes e datas** das capturas, que são sintéticos (Praça do Cedro é fixture
  inventada).
- A **normalização do casamento de rótulo** ("B" × "grade B" × "alambrado B") — a F-051 manda
  decidir na fatia 1 com o dado do job de referência; o pacote mostra casamento exato e o
  princípio "nunca fuzzy silencioso".
- **Onde a declaração persiste** no pacote de revisão versionado (Unknown 2 da F-051 —
  confirmar no planejamento contra `insert_review_revision_v1`).
- A **forma do seletor aberto nas capturas** (atributo `size`): artifício para a lista ser
  visível na imagem, não proposta de listbox permanente.
- As decisões do **ADR-0063**, que são gate próprio e já aceito.

## Proveniência de cada valor visual

| Valor | De onde vem |
| --- | --- |
| `--bg`, `--surface`, `--surface-subtle`, `--surface-sunken`, `--ink`, `--ink-secondary`, `--muted`, `--line`, `--accent*` | `apps/web/src/styles.css:24-51` — identidade "Grafite técnico" |
| Traço da precisão (cheio 3 px, fino 1,5 px, tracejado, pontilhado em `--muted`) + palavra por extenso | `apps/web/src/styles.css:3230-3282` (`.amostra-precisao`/`.cena-forma.precisao-*`), reproduzidos sem alteração |
| Selo tracejado `⚙ proposta · unresolved` | `.selo-proposta`, `apps/web/src/styles.css:3734-3763` — "proposta é tracejada em toda parte... porque ela não é identidade e não pode se parecer com uma" |
| Etiqueta `◇ EL-NNN` monoespaçada e a variante tracejada "— sem identidade" | `EtiquetaDeElemento`, `apps/web/src/elementIdentityPanel.tsx:48-55`, e o pacote da [F-047](../../F-047-quantitativo-da-cena-aprovada/mock/README.md) |
| Bolinha de status da leitura sempre com a palavra ao lado | `.status-dot`, `apps/web/src/styles.css:1344-1377` + `readingStatusLabel` |
| Anatomia da linha de leitura (bolinha + rótulo + selos) | `.review-row`, `apps/web/src/CroquiApp.tsx:4759-4843` |
| `<select>` de associação com "Anotação da folha — não mede um elemento" e os rótulos de relação "geometria mais próxima" / "dentro ou próximo do círculo" | `apps/web/src/CroquiApp.tsx:4982-5020` e `RELATION_LABELS`, `apps/web/src/labels.ts:128-135` |
| `field-hint` sob o seletor | idioma dos hints existentes (`suggestedAnnotationHint`/`ocrWitnessHint`, `apps/web/src/CroquiApp.tsx:5004-5019`) |
| Carimbo do ato com borda esquerda de 3 px, papel profissional e instante | introduzido pelo pacote da F-040, implementado em `carimboDoAto` (`apps/web/src/elementIdentity.ts:397-417` — papel, nunca usuário), reproduzido |
| Recusa em vermelho `#a33d32` / atenção em âmbar `#7c5210`, sempre com texto | já em uso nas duas jornadas (`.issue-panel`, `.decision-error`, `.ocr-warning`) |
| Família azul-aço `--cena*` para o que tem identidade declarada | introduzida pelo pacote da F-047, reaproveitada sem alteração |
| Bloco hachurado do reservado | introduzido pelo pacote da F-040, reaproveitado (aqui só no estado 07, para o caminho C) |
| **NOVO** — o chip do hint do modelo (`elemento (hint do modelo): B`, tracejado) | introduzido por este pacote. Tracejado como toda sugestão; nomeia a origem por escrito para nunca se confundir com a etiqueta ◇ de identidade declarada. |
| **NOVO** — o grupo "Pela identidade — ◇ EL-NNN · rótulo" no seletor, e a relação "pela identidade do elemento" | introduzidos por este pacote. Grupo rotulado por escrito acima do grupo "Pela proximidade"; distinção é texto, não cor, e não há score nem distância. |
| **NOVO** — a linha âmbar "≈ 2.100 px na folha" no desenho do estado 01 | anotação **deste pacote**, declarada como tal na própria tela — não existe na interface. |

Design system referenciado: `apps/web/src/styles.css` (e os componentes citados), lidos em
2026-09-04. Se este pacote e essa fonte divergirem, a fonte vence e o pacote está obsoleto.

Nenhum valor visual deste pacote depende só de cor. Precisão é traço **e** palavra; proposta é
tracejado **e** o selo escrito; identidade é o glifo ◇ **e** o ref monoespaçado; candidata por
identidade é grupo rotulado **e** relação por extenso; recusa é vermelho **e** a frase que diz
o que fazer.
