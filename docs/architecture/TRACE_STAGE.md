# Estágio de traçado: do croqui aceito à prancha cotada

Status: Accepted  
Responsável: Product / Engineering  
Última revisão: 2026-08-13 (nome inline aposentado; todo elemento rotulado vira balão)

Este documento é a referência canônica do estágio de traçado em lote
(`services/worker/src/croquito_worker/tracing.py`, comandos `solve-trace` e
`trace-export` do CLI `croquito-demo`). Ele existe por dois motivos: registrar de
forma durável o que foi aprendido nas iterações do Campo do Guaxindiba (2026-08-11), e
servir de especificação funcional para a tela de revisão e para o agente de conversa
([ADR-0023](../adr/0023-review-chat-as-an-observational-agent.md)) — **cada controle
listado aqui é uma pergunta que a UI fará ao profissional**. Os controles continuam
canônicos aqui; o agente é mais uma superfície deles, e os rascunhos que ele propõe são os
payloads destes mesmos controles, sempre assinados por um humano.

O estágio também é acionável pela sessão autenticada, com exatamente os mesmos controles:
`POST /v1/jobs/{id}/trace-solves` valida o aceite, enfileira e devolve `202`; o worker
resolve e o resultado é consultado por polling
([API Contract](API_CONTRACT.md), [ADR-0015](../adr/0015-trace-solve-worker-and-registry.md)).
Identidade do revisor, horário e `acceptance_id` vêm do servidor. Os comandos
`solve-trace` e `trace-export` da CLI continuam válidos e usam o mesmo motor.

Os controles 2, 4, 5 e 6 — associação (inclusive vão entre dois elementos e vão declarado
por âncoras), nota presa, texto de cota declarado e cota derivada — passaram a ter autoria
na própria sessão autenticada: o revisor os declara clicando no desenho, sem digitar
coordenada de pixel, com o recorte da evidência ao lado da pergunta
([FDD](../product/FDD.md)). Este documento continua sendo a especificação canônica do que
cada controle significa; a tela é uma superfície dele.

## Princípio

O croqui de mão é fora de escala por natureza; a cota escrita é a verdade métrica e o
desenho é a topologia. O traçado promove a extração aceita a cena métrica fazendo a cota
mandar:

1. `topology.build_topology` funde vértices coincidentes em junções (respeitando
   `keep_apart`).
2. `geometry_solver.regularise` agrupa junções em faixas ortogonais — remove anisotropia
   e esquadro torto sem alterar quem liga com quem. Além das arestas desenhadas, a junção
   que **encosta no meio** da aresta perpendicular de outro elemento entra na faixa dela,
   pela mesma tolerância com que a topologia funde vértices: a fusão só vê vértice contra
   vértice, e um endpoint apoiado no meio de um traço não tem vizinho nenhum. Era o que
   deixava a linha de meio de campo vazar 5,12 m pelo fundo do campo e as áreas saírem para
   fora da lateral no DXF de 2026-08-13. Recebe os mesmos `keep_apart`: nenhuma faixa reúne
   os dois lados de um par declarado distinto, nem por ponte de um terceiro, nem por
   encosto. Elemento `freeform` fica fora dos dois lados do encosto — nem gera nem recebe.
3. Cada leitura confirmada **com associação explícita** vira restrição de vão; onde há
   cota ela manda com precedência exata, onde não há o traçado responde por um prior
   minúsculo (com segunda passada que reposiciona o que não tem cota pela transformação
   ajustada — croqui fora de escala por região não arrasta elemento solto). **Cota manda
   na distância; o lado vem do traçado**: a restrição é assinada pela ordem traçada das
   duas faixas que ela liga (`segunda − primeira = +valor`), e a faixa é a incógnita do
   solver, não a junção que a associação apontou — um elemento desenhado torto tem a faixa
   na média das pontas, e a ponta perto do recorte da evidência pode cair do outro lado da
   faixa vizinha. Sem esse sinal a restrição valeria |distância| e a cena espelhada — o
   muro do outro lado do campo — fecharia com resíduo zero, porque o resíduo reportado é
   absoluto; com ele, o espelho erra por duas vezes a cota e aparece como resíduo
   estourado na cota que discorda (defeito medido no DXF real do Guaxindiba v2,
   2026-08-13). A exceção é o empate: par de faixas cujo gap traçado é menor que a
   tolerância de agrupamento — elementos desenhados coincidentes e declarados distintos
   por `keep_apart` — não tem ordem significativa, e aí a restrição volta a valer em
   módulo, com o lado decidido pelas cotas que têm lado (a mureta desenhada sobre a borda
   do campo cai 3,30 m fora dela porque a cadeia diz isso, nunca por meio pixel de ruído).
   Quando nem as outras cotas decidem, o lado fica com a ordem em que a restrição foi
   emitida — e essa ordem vem inteira do traçado (posição da aresta, posição da faixa, id
   da faixa), nunca da ordem em que o revisor clicou o par.
   Esse mesmo prior fraco pode, em croqui bastante fora de escala, inverter a ordem
   espacial de faixas adjacentes — inclusive faixas determinadas por cota confirmada. O
   solver detecta isso comparando a ordem traçada (pixel) com a ordem resolvida (metro) e
   bloqueia com `TRACE_BAND_ORDER_INVERTED` (erro cedo e nomeado, com o auditor de export
   como defesa em profundidade contra a polilinha fechada auto-intersectada que o defeito
   produziria). Violação é dispensada quando ao menos uma das duas faixas pertence só a
   junções de elementos declarados `freeform`: a posição desenhada é declaração do
   revisor, então a ordem dela contra o resto não é defeito do traçado (achado do
   Guaxindiba v2, 2026-08-13 — inversão entre faixas normais continua bloqueando). A
   violação também só vira blocker quando as duas faixas compartilham ao menos um dono: o
   check de ordem guarda o auto-cruzamento (faixas do mesmo elemento); relação cotada
   entre elementos tem o lado garantido pela restrição assinada; ordem entre elementos
   distintos sem cota é distorção do croqui e fica na camada aproximada (E6,
   2026-08-13).
4. O eixo Y é espelhado (imagem cresce para baixo; CAD, para cima) e a origem (0,0) vai
   para o canto inferior esquerdo. O espelho é a última etapa e vale para a solução
   inteira: dentro do solver o eixo Y continua crescendo para baixo, como na imagem, e é
   nessa orientação que se lê o sinal das restrições do princípio 3.
5. Precisão declarada por entidade: `exact` somente quando toda distância interna vem de
   cota confirmada; o resto permanece `approximate` na layer `APROXIMADO`, aceito em
   lote por pessoa identificada. Nada contorna `SceneRevision.ensure_exportable()`.

Divergência nunca passa calada: cota confirmada incompatível com o resto vira resíduo
acima da tolerância e **bloqueia o export** (`NUMERIC_RESIDUAL_EXCEEDS_TOLERANCE`). Foi
assim que o sistema acusou que a folha do Guaxindiba "não fechava" na direita — o
conflito de 1,50 m entre o 4,80 e a cadeia do recuo — até o usuário explicar o dente do
muro.

## O que o resultado diagnostica

O resultado do traçado não diz só *o que* falhou; diz *por quê*, *quem disputa com quem* e
*onde a cota que aplicou ancorou*. Os três campos são aditivos: `unapplied_reading_ids`,
`blockers`, `residual_summary` e `solve_status` continuam exatamente como eram, e nada
aqui cria blocker novo nem muda o portão de export — isto é o consultor, não o juiz.

- **Causa por leitura não aplicada** (`unapplied_readings`). O código nasce no ponto do
  descarte, onde a decisão é tomada, nunca reconstruído depois a partir do id: "não pôde
  virar vão ortogonal" cabe em situações com consertos diferentes. `TRACE_TARGET_AS_DRAWN`
  (o alvo está declarado `freeform` e cota de elemento único não amarra forma livre) e
  `TRACE_SPAN_SAME_BAND` (as duas âncoras caíram na mesma faixa, o caso que
  `keep_apart_pairs` resolve) são os dois que a rodada real mais produziu. A tabela
  completa dos códigos está no [API Contract](API_CONTRACT.md). A `Issue`
  `CONFIRMED_READING_NOT_APPLIED` da cena carrega a frase da causa; o código dela não
  mudou.
- **Vão em disputa** (`contested_spans`). Duas ou mais leituras confirmadas que amarram o
  MESMO par de faixas no mesmo eixo disputam uma única incógnita, e o LSQ cede para algum
  lugar entre elas. O resíduo já acusava o estrago espalhado; o que faltava era o par
  nomeado — no Guaxindiba v2 foram cinco resíduos de 0,66 m sem nenhum deles dizer quais
  duas cotas discordavam. Só entra quando a divergência excede a tolerância da cota mais
  grosseira do par: repetir a mesma medida em cima e embaixo é legítimo.
- **Âncoras aplicadas** (`applied_spans`). Para cada cota que aplicou, de onde até onde ela
  amarrou em metros da prancha (frame CAD, origem no canto inferior esquerdo), com o eixo,
  o valor, os elementos envolvidos e se é vão entre dois. É o que permite conferir "esta
  cota amarra daqui até ali" sem reabrir o DXF.

## Os controles do revisor

Todos os insumos são declarações humanas registradas; o sistema nunca adivinha. Exemplo
completo em uso: `output/dxf-retificado/inputs/` (retenção local de 7 dias; o formato é
o contrato).

### 1. Decisões de leitura (`apply-review`)

`ReadingDecisionBatch`: confirma/rejeita cada leitura. O `kind` declarado na decisão
informa o **eixo** que a cota mede (`width` → horizontal, `height` → vertical) — é o que
desambigua o segmento quando a cota está escrita longe do trecho (o `3,30` do recuo
encosta na parede vertical). `raw_text` é preservado como está na folha; um lapso do
levantamento (`h = 10` que é 0,10) mantém o texto original e declara o valor na decisão,
com nota do revisor.

### 2. Associações (`--associations`)

Objeto JSON `reading_id → alvo`:

- `"vp_…"` — vão de um elemento: a cota mede o segmento da proposta mais próximo do
  recorte de evidência, filtrado pelo eixo do `kind`.
- `"vp_…"` **de um círculo, com `kind` confirmado de raio ou diâmetro** — a cota
  determina o círculo: o raio vem do número escrito (÷2 quando é diâmetro), a entidade
  sai `exact` com `Measurement` confirmada amarrada a ela, e uma cota diametral (⌀) é
  desenhada no ângulo da evidência ("a cota pousa onde o croqui a escreve"). É extensão
  da mesma pergunta de associação, não um controle novo. Círculo não tem junção e nunca
  entra no sistema de faixas — sem essa leitura ele permanece `approximate` na layer
  `APROXIMADO`, com o raio pela escala média dos eixos; o centro continua vindo do
  traçado nos dois casos (é a posição, não a medida, que o croqui distorce). Duas
  leituras que discordam do mesmo círculo além da precisão escrita bloqueiam com
  `TRACE_CIRCLE_READINGS_CONFLICT` (a geometria fica com a de menor `reading_id` e as
  duas medidas entram na cena, para o portão do core acusar a incompatível). Em detalhe
  `sketch` nada muda: a cota vira nota presa, como qualquer outra. Leitura de
  largura/altura/comprimento sobre círculo continua não aplicada — não se adivinha eixo
  de círculo.
- `["vp_a", "vp_b"]` — **vão entre dois elementos** (o `6,60` campo↔muro): restrição
  entre as faixas dos dois; a DIMENSION é desenhada na posição da evidência; exige eixo
  declarado; não gera `Measurement` (não é medida de uma entidade só). A **ordem do par
  não é declaração**: `[a, b]` e `[b, a]` resolvem a mesma cena. Quem vem antes na
  restrição sai da posição traçada da aresta eleita, depois da posição traçada da faixa e,
  em empate das duas, do id da faixa — nunca da ordem em que o revisor clicou as formas
  (defeito medido em 2026-08-13: dois elementos desenhados na mesma coordenada empatavam a
  eleição, o desempate caía na posição no array e os dois trocavam de lado, com todos os
  resíduos verdes). Vale igual para a ordem das âncoras de um vão declarado.
- `{"proposal_id": "vp_…", "spans_px": [[[x,y],[x,y]], …]}` — **vão declarado entre
  duas arestas do mesmo elemento** (o `2,3` do rebaixo central do painel A da Toca):
  a folha cota um trecho interno que nenhum segmento único carrega. Cada par de âncoras
  em pixel elege a aresta perpendicular mais próxima de cada ponta e a cota amarra as
  duas faixas; a DIMENSION pousa no ponto médio das âncoras. Mais de um par aplica o
  mesmo valor em mais de um trecho (as duas pontas cheias de `4,40`). Exige eixo do
  `kind`; formato inválido bloqueia (`TRACE_ASSOCIATION_INVALID`); âncora que não
  resolve deixa a leitura em `unapplied_reading_ids`.

### 3. Aceite em lote (`--acceptance`, `TraceAcceptance`)

Identidade do revisor + lista exata de propostas aceitas, e três listas auxiliares:

- `hatch_proposal_ids` — regiões que a folha marca hachuradas (área vegetativa).
- `keep_apart_pairs` — elementos desenhados coincidentes que são distintos na obra
  (borda do patamar sobre a mureta): os vértices nunca se fundem, nem por ponte de um
  terceiro elemento. A separação vale para os vértices **e** para as faixas da
  regularização (princípio 2): a faixa é a variável do solver, então dois elementos
  separados que caíssem na mesma faixa continuariam amarrados um ao outro (Guaxindiba v2,
  2026-08-13 — a cadeia dos patamares e o recuo declarado disputavam a mesma incógnita por
  uma ponte da faixa vegetativa). Sem isso, o sistema de cotas do Guaxindiba era insolúvel.
  O par tem duas formas: `["vp_a", "vp_b"]` separa as faixas nos dois eixos, e
  `{"first": "vp_a", "second": "vp_b", "axis": "x"}` separa **só no eixo declarado**. O
  eixo existe porque o problema costuma ser de um só: o dente do muro (3,30/4,80) é
  horizontal, mas a base da mureta encontra a base do campo de verdade — separar também em
  Y soltava o sistema do muro inteiro, que deslizou 14,5 m no DXF de 2026-08-13. A fusão
  de vértices continua impedida nas duas formas: vértice fundido é um ponto só e amarraria
  os dois eixos de uma vez.
- `unlabelled_proposal_ids` — geometria aceita que dispensa balão e legenda (marcações
  padrão de campo: áreas, meia-luas, traves, círculo, pênaltis).
- `freeform_proposal_ids` — elementos **intencionalmente não-ortogonais** (o limite do
  lote da Toca converge para a rua: 1,55 no topo, 4,2 na dobra, 1,65 na base). A
  regularização não agrupa as arestas deles em faixas: o contorno segue como desenhado
  e cada vão `["vp_lote", "vp_ref"]` ancora no **vértice** do elemento livre mais
  próximo da evidência — é o que permite três afastamentos distintos ao longo do mesmo
  limite, em vez de colapsá-los numa faixa só. Declaração de quem conhece o lugar,
  nunca inferência de ângulo. Pelo mesmo motivo, a faixa de um vértice `freeform` sai do
  check de ordem (`TRACE_BAND_ORDER_INVERTED`, princípio 3): a posição desenhada já é a
  declaração do revisor, não um defeito a acusar.

### 4. Notas (`--notes`)

Objeto `reading_id → alvo`, para anotações confirmadas (`h=…`, especificações, tela
aérea). Alvos:

- `"vp_…"` — nota presa ao elemento, pousando na **projeção da evidência** sobre o
  segmento (onde o croqui a escreveu), girada ao longo dele e nunca de cabeça para
  baixo. Sufixo `#v`/`#h` declara a orientação da aresta âncora. Nota curta (≤ 10
  caracteres) usa fonte menor, fica do lado de **dentro** do desenho e ganha um risco
  vermelho (layer COTAS, `NOTE_LEADER_TICK`) até o ponto da linha.
- `"legenda:vp_…"` — o texto vira sufixo da linha de legenda do elemento.
- `"carimbo"` — nota geral, acima do título da prancha.

### 5. Texto de cota declarado (`--dimension-texts`)

`reading_id → texto exibido` para vão cuja cota mostra a especificação em vez do valor
(portão: `1,0 x 2,05`). A medida real continua na geometria e no resíduo; o texto é
apresentação declarada.

### 6. Cota derivada (`--derived-dimensions`)

Lista de `{proposal_id, near_x_px, near_y_px, text?}`: cota um trecho desenhado com o
valor da geometria resolvida (o `1,50` do dente = 4,80 − 3,30), precisão `derived` —
o número vem do solver, nunca finge leitura da folha. `text` opcional para especificação
(`3,60 x 3,90` na boca da entrada).

### 7. Grupos de detalhe (`detail_groups` no aceite)

O croqui desenha detalhes fora de escala ao lado da planta (painéis de alambrado em
elevação, arquibancadas em isométrico). Cada `TraceDetailGroup` — `detail_id`
(`A`, `C1`…), `title`, `proposal_ids` (subconjunto disjunto do aceite; a planta nunca
fica vazia) e `mode` — é resolvido **independente** da planta: topologia, bandas,
escala e origem próprias (a tolerância de fusão segue o bbox do grupo, não a folha).
Os grupos são empilhados numa coluna entre a planta e a legenda, cada um com moldura
(layer `DETALHES`, `DETAIL_FRAME`) e título `DETALHE X — <title>` — entidades normais,
com XDATA e contagem 1:1 na auditoria; o carimbo desce sozinho para baixo da coluna.

- `mode: "solve"` (elevações ortogonais): as cotas associadas ao grupo mandam dentro
  dele com escala verdadeira — `exact` onde determinado, quantitativos reais no CSV.
  Grupo `solve` que nenhuma cota alcança bloqueia
  (`DETAIL_GROUP_WITHOUT_APPLIED_READING`): confirme uma cota ou declare `sketch`.
- `mode: "sketch"` (isométricos, croquis livres): o desenho fica como está, projetado
  pela escala da planta, sempre `approximate` (`DETAIL_SKETCH_AS_DRAWN`), título com
  sufixo `(SEM ESCALA)`, fora dos quantitativos. Cota associada a sketch vira nota
  presa; cota derivada sobre sketch bloqueia (`DERIVED_DIMENSION_ON_SKETCH_DETAIL`).

Vão entre grupos (ou grupo↔planta) não existe — as topologias são independentes — e
bloqueia com `TRACE_ASSOCIATION_CROSSES_DETAIL_GROUP`. Resíduo estourado **dentro** de
um detalhe bloqueia a prancha inteira, como qualquer cota confirmada incompatível: o
detalhe é parte do desenho, não um anexo decorativo. A tipografia da prancha
(altura de cota, rótulos, legenda) segue a **planta**; `scale_m_per_px` do resultado é
a escala da planta e `detail_group_scales` registra a de cada grupo.

## Convenções de prancha (decididas com o usuário em 2026-08-11, nomes revisados em 2026-08-13)

- Cota pousa onde o croqui a escreve (evidência decide posição; o `21,75` desce pela
  linha de meio de campo).
- Especificação de vão vai no texto da cota; legenda fica só com o nome do elemento.
- Marcação curta (`h=…`) por dentro, pequena, com risco de chamada — como o engenheiro
  faz na folha.
- Todo elemento rotulado vira balão numerado junto a ele + linha na coluna de legenda —
  **o nome inline dentro da região está aposentado** (`element_labels.place_labels`).
  A convenção anterior ("nome completo só dentro de região onde cabe; o resto vira
  balão") colidiu na prancha real do Guaxindiba: o "Patamar de concreto esquerdo" saiu
  como nome inline enquanto todos os demais elementos saíram como balão, e o usuário
  arbitrou consistência keynote — um elemento rotulado, um jeito só de rotular.
  `unlabelled_proposal_ids` continua dispensando balão e legenda para geometria que não
  precisa de identidade (marcações padrão de campo).
- Elemento contêiner — região fechada (polilinha) que abrange outros elementos, como o
  Alambrado do Guaxindiba envolvendo o campo — recebe o balão junto à própria borda, não
  no centroide de área: o número nomeia o contorno, não o conteúdo
  (`element_labels.place_labels`).
- Legenda em coluna à direita, apenas para elementos com medida ou identidade útil;
  nota geral acima do título, com respiro.
- Colisões: caixas de texto levam folga de fonte de CAD (a fonte do AutoCAD é mais larga
  que a do preview); cotas do mesmo lado empilham em faixas; linhas de extensão de cota
  são obstáculo; balões desviam de tudo isso.

## Verificação

- `uv run pytest tests/worker/test_tracing.py` — cada defeito das iterações do
  Guaxindiba é um teste de regressão (anisotropia, espelhamento, patamar fora de escala,
  keep_apart, vãos, notas, colisões).
- Fluxo real reproduzível com os comandos de [CLAUDE.md](../../CLAUDE.md) e os insumos
  de exemplo; auditoria do DXF continua fail-closed
  ([DXF Output Spec](DXF_OUTPUT_SPEC.md)).
