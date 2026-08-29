# ADR-0058: O quantitativo nasce da cena aprovada, e antes disso o elemento precisa de identidade declarada

Status: Accepted  
Data: 2026-08-27 (aceito por ato humano em 2026-08-28, Daniel Campos, com **uma emenda** na
decisão 4 e a tolerância da decisão 6 nomeada — ver "O que o aceite humano confirmou")  
Responsável: Product / Engineering

## Contexto

A [issue #102](https://github.com/biahflow/croquito/issues/102) pede o quantitativo
automático a partir do scene graph aprovado: a área que o solver já resolveu com precisão
declarada deveria alimentar a quantidade da legenda, em vez de ser redigitada por uma
pessoa. O [ROADMAP](../product/ROADMAP.md) reserva a porta (bullet "Quantitativo automático
derivado do scene graph aprovado", `docs/product/ROADMAP.md:663-665`): `TakeoffItem.source`
discriminado mais um `QuantitySource` lendo o `quantitativos.csv` do export DXF — e registra,
no próprio bullet, que a porta **depende de identidade estruturada de elemento nas entidades,
que hoje não existe**.

O mapeamento do código confirma que a dependência, e não a fiação, é o que dimensiona a
feature.

### O que já existe

- **A cena aprovada já produz quantidade auditada.** `_write_quantities`
  (`../../services/worker/src/croquito_worker/dxf.py:482-539`) escreve `quantitativos.csv`
  com `entity_id`, `layer`, `kind`, `precision`, `length_m`, `perimeter_m` e `area_m2`, uma
  linha por entidade exportável, computada da geometria métrica. Ele já sabe o que **não** é
  quantidade física: pula `TEXTOS` e `COTAS` (`dxf.py:503-506`) e os `summary_code` de moldura
  e sketch sem escala. A quantidade sai, e sai carimbada com a precisão da entidade.

- **A precisão é declarada, entidade a entidade.** `Precision`
  (`../../packages/core/src/croquito_core/models.py:31-35`) é `exact | derived | approximate |
  unresolved`, e cada linha do CSV carrega a sua. A quantidade da cena não é um número solto:
  ela já vem com o quanto se pode confiar nela.

- **O lado da medição já tem a porta discriminada.** `TakeoffItem.source`
  (`../../packages/valuation/src/croquito_valuation/takeoff.py:99`) é `Literal["legend_extraction",
  "manual"]`, e a docstring (`takeoff.py:88-90`) diz em tantas palavras que `source` é "a porta
  discriminada reservada no roadmap para quando o quantitativo puder nascer do scene graph
  aprovado em vez da extração de legenda".

- **A cardinalidade elemento↔serviço já foi resolvida.** O
  [ADR-0053](0053-cardinalidade-n-n-elemento-servico.md) decidiu que a relação é N:N, com
  parcela por par: um `PISO EM CONCRETO` de 418,12 m² alimenta seis serviços, e um serviço soma
  parcelas de vários elementos. O elo que a máquina confere é `CalcBlock.source_item_id`, **ao
  lado** do `label` humano, e a identidade da confirmação é o par `(item_id, code)`.

### O que não existe, e é o bloqueio que dimensiona a feature

**A entidade da cena não tem identidade de elemento.** `Entity`
(`../../packages/core/src/croquito_core/models.py:178-202`) carrega `id` (um UUIDv7 de linha,
que muda a cada revisão), `kind`, `layer`, `precision`, `geometry` e `provenance` — e nada que
diga *que elemento do croqui este traço é*. O nome do elemento existe apenas como texto livre:
uma `TextGeometry.text` (`models.py:131-136`) numa entidade `TEXT` sobre a camada `TEXTOS`,
que o `quantitativos.csv` inclusive **descarta** por ser anotação (`dxf.py:503-506`). `grep`
por `element_id`, `element_ref`, `name` ou `label` em `models.py` não devolve campo nenhum na
`Entity`.

**O `QuantitySource` não existe.** `grep -rn QuantitySource packages services` só encontra a
citação do ROADMAP; a porta nunca foi aberta, em nenhum pacote.

**Nada liga um lado ao outro.** O `quantitativos.csv` é indexado por `entity_id` e `layer`; o
`TakeoffItem` é indexado por `id` (`ti_…`) e descrito por um `label` de texto livre
(`takeoff.py:96`). Não há chave comum. Ligar a área de um polígono ao item de legenda que diz
"418,12 m²" hoje só seria possível por **proximidade** — casar o número da cena com o número da
legenda, ou o polígono com o balão mais perto. É exatamente a associação que o produto recusa
em toda parte: proximidade em pixels nunca é associação implícita. Sem identidade estruturada,
o quantitativo automático seria essa associação por proximidade com outro nome.

Por isso este ADR não decide a fiação `QuantitySource → TakeoffItem`. Ele decide **o que
falta para que essa fiação não seja um palpite**: como a entidade da cena declara identidade de
elemento, quem a atribui, e o que acontece quando a quantidade derivada **diverge** da lida na
legenda.

### As decisões de produto que precederam este ADR

Este ADR é `Proposed`. As perguntas de domínio abaixo não têm resposta registrada por ato
humano ainda; a seção final ("Decisões de produto que este ADR pede ao aceite humano") as
lista, e a redação da Decisão propõe a direção que o resto do produto já sugere.

## Decisão

1. **A `Entity` ganha uma identidade de elemento estruturada, `element_ref`, ao lado do que já
   tem — nunca no lugar do texto livre.** Não é o `Entity.id` (que é identidade de linha e muda
   a cada revisão) nem a `TextGeometry.text` (que é a redação que o humano lê na prancha, e
   apagá-la para virar chave repetiria o erro que o ADR-0053 recusou ao manter `label` ao lado
   de `source_item_id`). `element_ref` é o elo estável que diz "este polígono e aquele balão são
   o mesmo elemento", sobrevive à criação de nova revisão na aprovação, e é o que o
   `quantitativos.csv` passa a carregar como chave de quantidade — ao lado de `entity_id`, não
   no lugar dele.

2. **A identidade de elemento é ATO HUMANO explícito na revisão, não inferência.** Coerente com
   o resto do produto: nada vira geometria sem passar pelo scene graph, nenhuma leitura vira
   cena sem `HumanDecision`, nenhuma associação `reading_id → proposal_id` nasce de proximidade.
   Atribuir identidade de elemento é o mesmo tipo de ato — declarar que estes traços são um
   elemento, e qual. O sistema pode **propor** o agrupamento (por camada, por rótulo próximo,
   pelo mesmo `provenance`), como propõe candidatos de visão, mas a proposta nasce `unresolved`
   e não vira identidade sem a decisão registrada. Um agrupamento inferido e não confirmado
   nunca alimenta quantidade.

3. **A identidade de elemento é o que conversa com a cardinalidade N:N do ADR-0053.** O
   `source_item_id` do [ADR-0053](0053-cardinalidade-n-n-elemento-servico.md) liga o item de
   *legenda* ao serviço; o `element_ref` deste ADR liga o item de legenda ao *elemento
   geométrico da cena*. Fechada a identidade, o par vira uma cadeia conferível: elemento da cena
   → item da legenda → N serviços do catálogo, cada aresta um elo estruturado, nenhuma por
   proximidade. A quantidade derivada da cena entra por essa cadeia, e a `ContributionBasis`
   `DERIVED` do ADR-0053 finalmente tem de onde derivar de fato, em vez de nominalmente.

4. **Só `exact` e `derived` alimentam a medição; `approximate` não entra, nem sob aceite.**
   *(Emendado no aceite humano de 2026-08-28 — a proposta original admitia `approximate` sob o
   mesmo aceite explícito do croqui.)* Um `TakeoffItem` alimentado pela cena nasce com `source`
   de um terceiro valor — `scene_graph` — no `Literal`, e carrega a `Precision` da entidade de
   origem (`../../packages/core/src/croquito_core/models.py:31-35`), que só pode ser `exact` ou
   `derived`. Entidade `approximate` ou `unresolved` **não** produz quantidade de medição: a
   legenda continua sendo a fonte nesses casos, lida por decisão humana como hoje.

   O motivo da emenda é o destino do número, não a sua qualidade. O aceite de aproximação que o
   croqui já tem existe para **publicar um desenho** declarando o que é aproximado; a quantidade
   da medição vira **dinheiro** num boletim que a prefeitura paga, e aproximação com carimbo
   continua sendo aproximação depois de multiplicada por preço unitário. Um número aproximado
   que atravessa a fronteira para a medição deixa de ser visivelmente aproximado quando vira
   uma linha de R$ no gabarito. A promoção de precisão que o pipeline proíbe continua proibida
   aqui, e a fronteira entre as duas jornadas ganha uma trava a mais do que o croqui sozinho
   precisa.

5. **`QuantitySource` lê o `quantitativos.csv` do export e resolve a quantidade por
   `element_ref`, não por posição.** É o adaptador que o ROADMAP reserva. Ele casa a linha do CSV
   com o `TakeoffItem` pela identidade de elemento declarada na revisão — a mesma dos dois lados.
   Sem `element_ref` em ambos os lados, `QuantitySource` **não resolve** e diz isso; ele nunca
   cai para casamento por número ou por proximidade de balão. A ausência de par é um estado
   legível, não um palpite silencioso.

6. **Divergência entre a quantidade da cena e a lida na legenda é DIAGNÓSTICO, nunca
   sobrescrita.** Quando o mesmo elemento tem quantidade derivada da cena **e** quantidade lida
   na legenda, e elas não batem além da tolerância nomeada, o sistema **abre uma Issue** e
   não escolhe por conta própria. A tolerância, fixada no aceite humano de 2026-08-28, é **o
   maior entre 1% do valor da legenda e 0,01 na unidade do item** — a faixa que absorve o
   arredondamento de quem escreve `418,12` para uma área de `418,1183...`, sem deixar passar
   erro de digitação. Ela é constante nomeada no código, não número solto: quem a mudar muda
   uma declaração, não uma linha de comparação. Nenhum dos dois números apaga o outro: a cena não sobrescreve
   a legenda, a legenda não sobrescreve a cena. Quem revisa vê as duas, a origem de cada uma e a
   diferença, e decide — como já decide toda divergência no produto. É o mesmo princípio da
   `AMENDMENT_APPLICATION_MISMATCH` do ADR-0055/56 e do `LINE_PRICE_NOT_IN_CONTRACT`: a
   divergência recusa e explica, não concilia sozinha. Divergência é o *valor* da feature — é
   onde a redigitação escondia o erro —, então escondê-la de novo com uma sobrescrita anularia o
   motivo de existir.

7. **A quantidade automática só existe a partir da cena APROVADA, pelo portão de exportação que
   já existe.** A quantidade vem do `quantitativos.csv`, e o CSV só é escrito depois de
   `ensure_exportable` e da reabertura/auditoria do DXF
   (`../../services/worker/src/croquito_worker/dxf.py`). Cena não aprovada, entidade
   `unresolved`, `approximate` sem aceite ou issue crítica aberta continuam barrando o export — e,
   com ele, a quantidade. Nenhum caminho novo até o `TakeoffItem` contorna esse portão; o
   quantitativo automático herda o portão, não o duplica.

8. **Sem `element_ref` declarado, tudo responde como hoje.** `TakeoffItem` sem `source =
   scene_graph` segue sendo lido da legenda por decisão humana, `quantitativos.csv` sem a nova
   coluna de identidade continua saindo para o croqui puro, e `source` aceita o valor novo de
   forma aditiva. A feature é uma porta que se abre quando a identidade é declarada, não um
   comportamento que muda o que já funciona.

### O que o aceite humano confirmou

Em 2026-08-28, ponto a ponto (Daniel Campos):

1. **A identidade de elemento é ato humano na revisão** (Decisão 2). A alternativa "camada +
   rótulo estruturado como identidade automática" foi recusada; ela permanece válida apenas
   como **proposta** que o humano confirma.
2. **A forma da identidade é um `element_ref` novo na `Entity`** (Decisão 1), e não a extensão
   do par do ADR-0053 até a cena. Os dois contextos continuam com chaves próprias: a cena diz
   qual elemento é, a legenda diz qual item é, e o elo entre eles é declarado.
3. **Só `exact` e `derived` alimentam a medição** — emenda à Decisão 4, que admitia
   `approximate` sob aceite. Quantidade aproximada nunca vira quantidade de boletim; nesses
   casos a legenda segue sendo a fonte.
4. **A divergência é sempre Issue**, nenhuma origem sobrescreve a outra, e a tolerância nomeada
   é **o maior entre 1% do valor da legenda e 0,01 na unidade do item** (Decisão 6).
5. **`TakeoffItem.source` ganha o terceiro valor `scene_graph`**, de forma aditiva, com a subida
   de versão de contrato que isso implica no lado da medição (Decisão 5 e 8).

## Alternativas

- **Associação por proximidade (casar a quantidade da cena com a da legenda pelo número, ou o
  polígono com o balão mais perto)** — **rejeitada, e é a rejeição central deste ADR.** É
  precisamente o que o produto recusa em toda parte: proximidade em pixels nunca é associação
  implícita, e o solver exige associação explícita `reading_id → proposal_id` mesmo para
  leituras confirmadas. Casar 418,12 da cena com 418,12 da legenda parece seguro até o dia em
  que dois elementos têm a mesma área, ou a leitura tem um dígito trocado — e aí o palpite erra
  em silêncio, que é a classe de erro que este repositório recusa por princípio.
- **Camada + rótulo estruturado como identidade automática** — rejeitada, mas é a alternativa
  legítima que o aceite pode preferir. A `Entity` já tem `layer`
  (`../../packages/core/src/croquito_core/models.py:178-202`), e derivar identidade de camada +
  texto do balão evitaria um ato humano novo. Rejeitada como *automática* porque a camada é
  grossa demais (vários elementos de `MURO` numa cena) e o rótulo é o texto livre que este ADR
  não quer transformar em chave; ela erraria a agregação e alimentaria quantidade errada sem
  ninguém declarar nada. Vale como **proposta** que o humano confirma (Decisão 2), não como
  identidade em si.
- **Casar a quantidade pelo `Entity.id`** — rejeitada: `id` é identidade de linha e a aprovação
  cria nova revisão, então o `id` muda e o elo se perde entre a cena que gerou a quantidade e a
  que foi aprovada. Identidade de elemento tem de sobreviver à revisão; `id` não sobrevive.
- **Sobrescrever a legenda com a quantidade da cena quando divergirem** (ou o inverso) —
  rejeitada pela Decisão 6. A cena é auditada, mas "auditada" não é "sempre certa": um elemento
  mal traçado produz área errada com precisão declarada `exact`. Sobrescrever apagaria o sinal
  exatamente onde ele importa, e a redigitação que a feature quer eliminar voltaria como uma
  conciliação silenciosa — o mesmo erro com outra roupa.
- **Derivar quantidade de entidade `approximate` como se fosse `exact`** — rejeitada: repete a
  promoção de precisão que o pipeline proíbe ponta a ponta. `approximate` continua `approximate`
  até o DXF, e continua depois dele, na medição.
- **Deixar `approximate` alimentar a medição *como* `approximate`, sob aceite explícito** — era
  a proposta original da Decisão 4 e foi **rejeitada no aceite humano de 2026-08-28**. O carimbo
  de aproximação sobrevive à tela e morre na planilha: multiplicado por preço unitário, o número
  vira uma linha de R$ que ninguém lê como aproximada. Onde a cena só tem aproximação, a legenda
  continua sendo a fonte.
- **Abrir `QuantitySource` agora, antes da identidade de elemento** — rejeitada: sem `element_ref`
  nos dois lados, o adaptador só teria proximidade para trabalhar, que é a primeira alternativa
  rejeitada. A identidade é pré-requisito, não detalhe posterior.

## Consequências

### Positivas

- A ligação que fecha as duas jornadas passa a existir sem palpite: a área que o solver
  resolveu com precisão declarada alimenta a quantidade da legenda por um elo declarado, e a
  redigitação — onde o erro entrava — deixa de ser necessária.
- A divergência entre cena e legenda vira um diagnóstico visível em vez de um erro que só
  aparece na obra. É o valor da feature, e ele é preservado por desenho.
- A cadeia elemento → legenda → serviços do ADR-0053 fica conferível de ponta a ponta, e a
  base `DERIVED` ganha de fato de onde derivar.
- Sem identidade declarada, todo caminho existente responde como hoje: croqui puro, legenda lida
  à mão, `quantitativos.csv` do jeito que já sai.

### Negativas

- **A `Entity` ganha campo, e é contrato gerado.** Mudar `SceneRevision`/`Entity` exige `make
  contracts` e propaga ao `scene.schema.json` e ao TypeScript gerado; é aditivo, mas toca o
  contrato publicado da cena.
- **A revisão ganha um ato humano novo** — declarar identidade de elemento. É trabalho a mais na
  revisão, assumido em troca de a associação nunca ser palpite; a proposta assistida (Decisão 2)
  reduz o custo, não o elimina.
- **A tolerância da divergência é um número que alguém escolhe**, e escolhido apertado demais
  vira ruído, largo demais deixa passar erro real. Fica como decisão de produto nomeada, não
  como constante escondida.
- **`TakeoffItem.source` sobe de contrato** ao ganhar o terceiro valor, no lado da medição.

## Riscos e mitigação

| Risco | Mitigação |
|---|---|
| Quantidade automática nascer de associação por proximidade | Decisões 1-2 e 5: identidade de elemento declarada por ato humano; `QuantitySource` casa por `element_ref`, nunca por número ou posição |
| Divergência cena × legenda sobrescrita em silêncio | Decisão 6: divergência abre Issue e recusa; nenhuma origem apaga a outra |
| Precisão promovida ao entrar na medição | Decisões 4 e 7: entra com a precisão da cena; `approximate` continua `approximate`; `unresolved` não entra |
| Elo perdido entre a cena que gerou a quantidade e a aprovada | Decisão 1: `element_ref` estável, sobrevive à nova revisão da aprovação; não usa `Entity.id` |
| Quantidade derivada de cena não aprovada | Decisão 7: a quantidade vem do `quantitativos.csv`, que só existe após `ensure_exportable` e auditoria |
| Identidade automática por camada+rótulo agregar elementos errados | Rejeitada como automática; vale só como proposta que o humano confirma (Decisão 2) |
| Contrato da cena e da medição mudam | Aditivo: `element_ref` opcional e `source = scene_graph` novo; sem declaração, comportamento idêntico ao de hoje (Decisão 8) |

## Rastreabilidade

- Feature: [F-047](../features/F-047-quantitativo-da-cena-aprovada/feature.md)
- Issue: [#102](https://github.com/biahflow/croquito/issues/102)
- Relacionados: [ADR-0053](0053-cardinalidade-n-n-elemento-servico.md),
  [ADR-0005](0005-canonical-scene-graph.md),
  [ADR-0006](0006-human-review-and-provenance.md),
  [ADR-0007](0007-dxf-primary-output.md),
  [ADR-0013](0013-export-worker-and-artifact-registry.md),
  [ADR-0048](0048-consolidado-contratual-do-orcamento-assinado.md),
  [ADR-0050](0050-correcao-humana-de-forma-como-proposta-derivada.md)
- Supersedes: none
- Superseded by: none
