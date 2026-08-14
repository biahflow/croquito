# Propostas de visão computacional

Status: Implemented for local observational stage  
Responsável: AI Engineering / Geometry  
Última revisão: 2026-08-13

## Objetivo

Localizar evidências geométricas candidatas em páginas renderizadas sem inferir
escala, unidade, identidade do objeto ou dimensão. Este estágio reduz o espaço de
busca para OCR, modelos multimodais e revisão humana; ele não produz CAD.

## Contrato

`VisionProposalSet` registra:

- digest e dimensões da imagem fonte;
- sistema de coordenadas `source_image_pixels`;
- versão do detector;
- limites configurados e quais limites foram atingidos;
- geometria candidata, algoritmo e `quality_score`;
- se a abertura angular de um arco foi observada ou fabricada (`arc_angles_observed`);
- notas de segurança do estágio.

Cada `VisionProposal` força:

```json
{
  "precision": "unresolved",
  "export": false
}
```

O `quality_score` mede suporte geométrico do algoritmo. Não é probabilidade
calibrada, não representa correção semântica e não autoriza confirmação automática.

## Algoritmos atuais

### Linhas

- Threshold adaptativo combinado com tinta colorida.
- `HoughLinesP` com parâmetros relativos ao tamanho da página.
- Merge de segmentos colineares por ângulo, distância perpendicular e gap.
- Limite bruto de 80 candidatos por página.

### Círculos

- `HoughCircles` sobre grayscale suavizado.
- Verificação de suporte ao longo da circunferência na máscara de tinta.
- Threshold conservador para evitar letras e anotações circulares.
- Contornos que duplicam círculo forte são suprimidos.

### Contornos

- Fechamento morfológico e contornos externos.
- Simplificação de visualização por `approxPolyDP`.
- Formas quase circulares ficam a cargo do detector de círculos.
- Contorno curvo continua polilinha em pixels, nunca spline exata.

## Registro contra a tinta

Proposta vinda de modelo acerta a estrutura e erra o assentamento. `register_to_ink`
corrige isso em dois estágios, ambos determinísticos e em grade fixa — nunca um
otimizador cujo resultado ninguém consiga auditar depois.

**Global.** Uma só transformação para o conjunto inteiro: quarto de volta exato
(0/90/180/270), rotação fina de até ±3,0° em torno do mesmo centroide (passo de 0,5° e
depois 0,1°), escala por eixo e translação. O quarto de volta cobre o croqui deitado na
folha; o ângulo fino cobre a folha que entrou torta no scanner, cujo erro cresce longe do
centroide e nenhum múltiplo de 90° corrige.

**Por elemento.** O ótimo agregado pode sacrificar um elemento que já estava certo, e foi
o que aconteceu com o muro perimetral do Guaxindiba. Cada proposta é então reassentada
sozinha, com o ajuste que o tipo dela autoriza:

| Tipo | Ajuste permitido | Nunca |
|---|---|---|
| Linha e contorno | Empurrão rígido dentro da janela | Re-forma |
| Linha | Depois do empurrão, cada ponta desliza ao longo da própria direção | Girar, ou adotar a extensão de um traço que continua |
| Contorno fechado quase-retangular | Deslocamento perpendicular por aresta, direções preservadas | Girar aresta ou achatar o contorno |
| Círculo | Centro na mesma janela e raio em ±15% | Virar outra forma |
| Polilinha de arco | Centro, raio e orientação — esta em ±15° quando observada —, preservando extensão angular e vértices | Fechar em círculo |

A janela do empurrão cresce com o elemento — 15% da diagonal da própria caixa envolvente —
com piso de 0,5% e **teto de 2% do lado maior da página**. Sem crescer, o contorno grande
fica preso; sem teto, ele desliza centenas de pixels e vai colher tinta que não é dele,
porque num croqui cheio de linhas longas e paralelas a cobertura premia qualquer tinta
alcançada. Empate de cobertura fica sempre com a **correção menor**.

### Erro de tamanho: cada aresta busca a própria tinta

Empurrão rígido corrige **assentamento**. O modelo também erra **tamanho**, e nenhum
deslocamento do elemento inteiro conserta isso: no Guaxindiba o contorno do campo saiu 1,28x
mais alto que a tinta, e ancorar o topo na tinta certa jogava a base 285 px para dentro do
patamar — o encontro desenhado campo↔patamar, que é o que amarra os dois elementos no
traçado, deixava de existir.

Contorno **fechado de quatro arestas quase-ortogonais** — mesma tolerância angular que a
regularização do traçado usa, para o refino não chamar de retângulo o que ela vai tratar como
diagonal — ganha então um deslocamento perpendicular por aresta, quatro escalares buscados na
mesma escada de grade. Contorno que não passa nesse teste segue no empurrão rígido.

- **Cada aresta é medida na tinta dela**, nas amostras da própria aresta na colocação de
  base. Medir o elemento inteiro é o que impede a correção: três arestas certas afogam a
  quarta, e o que sobe a cobertura média é o deslocamento rígido, que não corrige tamanho.
- **Nunca-piora por aresta**: aresta sem tinta melhor na janela fica onde está. Vale também
  para o elemento inteiro, como no empurrão rígido.
- A **janela por aresta** é fração da extensão do elemento **perpendicular** àquela aresta,
  não da diagonal, com o mesmo piso e **teto próprio de 5% do lado maior da página**. O teto é
  maior porque a aresta oposta à que já pousou carrega o erro de escala inteiro; a extensão
  perpendicular é a medida certa porque o erro é proporcional à profundidade que a aresta
  atravessa. Pela diagonal os dois lados erram: no Guaxindiba a faixa de área vegetativa (221
  px de altura, 1.528 px de diagonal) ganharia janela para o topo descer 220 px até a linha de
  outro elemento, e os patamares, que precisavam de até 310 px, ganhariam só 272.
- **Cantos são a interseção das quatro retas deslocadas.** O contorno continua fechado, com
  quatro vértices, e as direções das arestas saem exatamente como entraram.
- **Piso de extensão**: o refino não pode reduzir o elemento a menos da metade de qualquer
  uma das extensões dele. Corrigir tamanho é o trabalho; anular o elemento não é — um par de
  paralelas fechando sobre a mesma tinta daria cobertura perfeita e um traço no lugar do
  contorno. Quando a correção que a **ordem** já exige não cabe nesse piso, o refino por
  aresta se declara inaplicável e o elemento volta para o empurrão rígido: ordem é defeito de
  posição, e mudar tamanho não conserta posição.
- **Correção mínima desempata**, aresta a aresta, o que minimiza a soma dos módulos. Cada
  passe varre o intervalo inteiro na resolução dele em vez de refinar em torno do vencedor do
  passe anterior: um passe grosso anda mais que a tolerância da tinta e pode pular a tinta do
  próprio elemento, enxergando só a de um vizinho distante — medido no Guaxindiba, o topo da
  pequena área direita andava 284 px até a linha de outro elemento em vez dos 25 px até a
  própria, com a mesma cobertura.

O relatório por proposta declara os quatro deslocamentos em `edge_shifts_px`, na ordem topo,
base, esquerda e direita — o papel da aresta, não o índice do vértice, porque é o papel que a
revisão confere contra a folha.

### Extensão de linha: as pontas deslizam sobre a própria reta

O empurrão acerta **onde** a linha está e não tem como acertar **até onde** ela vai — mover a
linha inteira para consertar uma ponta estraga a outra. Depois do empurrão, então, cada ponta
de `PixelLine` desliza ao longo da direção da própria linha, na mesma escada de grade. A
direção não gira e a outra ponta não é arrastada: uma ponta errada não custa a que estava
certa.

O que se maximiza é o **comprimento útil** — tinta coberta menos comprimento sem tinta,
contado em pixels. Cobertura sozinha encolheria a linha até um toco sobre o traço mais grosso;
comprimento sozinho a esticaria pela folha. A diferença entre os dois para exatamente onde a
tinta acaba, e é também o que decide um vão: a ponta só atravessa um trecho sem tinta quando o
traço do outro lado é mais longo que o vão. No Guaxindiba foi isso que manteve o toco da cota
"6,60" fora da linha de meio de campo — 69 px de tinta atrás de um vão de 275 px —, e a linha
saiu 479 px mais curta, do topo do campo até a base dele.

**Encolher e esticar não são simétricos.** Encolher tem parada natural: a tinta acaba. Esticar
só tem parada quando a tinta acaba dentro da janela; quando o traço segue além dela, a folha
não diz onde a linha termina, e escolher um fim seria inventar extensão — nesse caso a ponta
não estica, só pode encolher. Sem essa regra o portão do Guaxindiba, que é uma abertura de
3,10 m desenhada **sobre** a linha do muro, crescia 35% para cada lado engolindo a tinta do
muro e apagando o vão que ele existe para declarar.

A janela por ponta é a mesma fração do refino por aresta, aplicada ao comprimento da linha,
com o mesmo piso e teto de página; o piso de extensão também vale, então a linha não encolhe
até sumir. A cobertura nunca piora, a ordem nunca piora — mesmo corredor, mesmas barreiras,
medidos na linha reconstruída — e o relatório declara `tip_shifts_px`, quanto cada ponta
deslizou, positivo no sentido início→fim.

#### Traço cruzante não é fim de linha

Cobertura e comprimento útil sabem que há tinta, não de quem ela é, e um risco perpendicular
tem tinta. Com o halo, o risco e a linha que ele cruza viram **uma mancha contínua**: a ponta
para na borda dessa mancha e nunca alcança a tinta própria. No Guaxindiba a ponta de cima da
linha de meio parou em y=2096, 44 px acima do próprio traço, dentro do halo do risco que cruza
a coluna em 2118..2153 — e ali ela ficava mais perto da faixa do muro (2123,3) que da do campo
(2130,1). O traçado amarrou o 21,75 na faixa errada e a cadeia estourou em três resíduos de
2,20 m (19,75, 8,60 e o próprio 21,75).

A parada, então, só vale onde a tinta testemunha um **trecho contínuo próprio**: pelo menos
duas tolerâncias de tinta ao longo da direção da linha. A evidência é medida numa máscara
direcional — a tinta erodida por um segmento naquela direção, o que apaga qualquer estrutura
que não se estenda por esse mínimo, com o halo devolvido apenas na **perpendicular**, que é
para o que ele serve aqui: alcançar o traço cujo centro a proposta não pegou em cheio.
Devolvê-lo também na direção reporia exatamente o que a erosão tirou — medido: a ponta voltava
a parar em y=2121, ainda dentro do risco, e a cadeia continuava estourada. Duas tolerâncias é o
limiar natural porque "mais perto que a tolerância os dois são o mesmo traço" é a definição que
este estágio já usa para ordem e corroboração: tinta que só se estende por uma tolerância na
direção é espessura de traço, não extensão.

O preço é declarado: a ponta pousa onde o trecho mínimo já está inteiro, então sobra um resíduo
**para dentro** da linha, da ordem da tolerância. É a mesma ordem de grandeza do resíduo do R1e,
que era para fora, e é o lado seguro — a ponta que para antes do risco continua dentro do vão do
próprio elemento, enquanto a que passa dele encosta na faixa do vizinho. Não se troca por menos:
num encontro em T a tinta do risco e a da linha se tocam, então "onde a tinta própria começa" é,
no pixel, o topo do risco, e parar ali é justamente o defeito.

Quando nenhuma parada honesta cabe na janela, a janela é **estendida até a correção mínima** que
põe a ponta sobre trecho próprio, pelo mesmo princípio do corredor da ordem: o teto limita quanto
a ponta procura tinta, não a correção que a lei exige. No Guaxindiba o trecho próprio começa
359 px adiante e o teto dá 336 — sem a extensão a regra ficaria pior que o defeito, deixando a
ponta onde o modelo a pôs, 344 px além da tinta, sobre o toco da cota "6,60". A extensão vale só
para **encolher** e no máximo até o piso de extensão: esticar até um trecho distante seria adotar
extensão que a folha não deu.

Uma ponta pousa na borda do **halo** da tinta, não no centro do último traço: "sobre tinta"
neste estágio é definido com a tolerância da tinta, a mesma que decide corroboração, ordem e
encosto. O resíduo é dessa ordem de grandeza e é declarado em vez de fingido de zero.

Polilinha aberta que não é arco continua só no empurrão rígido: ela tem vértices interiores, e
deslizar as pontas dela mudaria a forma, não a extensão.

**Limitação declarada.** Uma aresta que a folha não desenha não tem tinta própria para achar,
e dentro da janela ela adota a paralela mais próxima. A lei da ordem só protege contra a tinta
de elementos **já assentados**; contra a de um vizinho que ainda não se assentou, ou de um
traço que não virou proposta, não há corredor a fechar. O empurrão rígido não tinha essa
exposição porque as quatro arestas se seguravam. É o preço da correção de tamanho, e ele é
declarado em vez de escondido.

### O refino nunca inverte a ordem traçada

Cobertura sozinha não distingue a tinta do elemento da tinta do vizinho. No Guaxindiba isso
custou o desenho: a aresta superior do contorno do campo pousou na tinta do "muro vizinho
h=3,80" e a do contorno do terreno pousou na linha do campo. As duas ficaram com cobertura
alta, e o DXF saiu espelhado — o solver honra o lado do traçado, então dado trocado vira
geometria trocada.

A lei que fecha esse buraco vale para o estágio por elemento inteiro, e no refino por aresta
ela é aplicada **por aresta**: cada uma responde pela tangente que governa, com o mesmo
corredor e as mesmas barreiras, e o candidato é julgado no contorno reconstruído — o canto é
interseção, então deslocar uma aresta arrasta o canto das vizinhas ao longo delas. A âncora
entra no corredor já descontada dessa folga, senão a primeira aresta que se move empurra o
canto de volta para cima do vizinho e a busca trava.

- **Referência de ordem é o conjunto pós-global**, que é a mesma ordem do bruto: o estágio
  global aplica giro, escalas positivas e translação ao conjunto todo, e transformação assim
  não troca vizinho de lado.
- Cada elemento declara onde está por **quatro tangentes** da caixa envolvente (topo, base,
  esquerda, direita); círculo e arco declaram pelo **centro**, porque girar a janela angular
  de um arco muda os quatro extremos sem que ele tenha atravessado ninguém.
- Duas features só declaram ordem quando a do vizinho **cobre ao menos um quinto** da do
  elemento e as duas estão separadas por mais que a tolerância da tinta. A fração é medida
  sobre a feature restringida: uma linha que cobre a aresta inteira de um elemento diz de que
  lado dela ele está; um portão de 150 px atravessando um muro de 3.800 px não diz nada sobre
  o muro — ele está dentro do muro, não de um lado dele. Mais perto que a tolerância os dois
  são o mesmo traço, e esse é o caso que o traçado resolve com `keep_apart`.
- Os elementos são assentados em **ordem de cobertura decrescente** (quem tem mais tinta
  manda; empate pelo id) e cada um recebe um corredor fechado pelas tangentes já assentadas.
  O corredor para uma tolerância de tinta **antes** da posição do vizinho, não sobre ela:
  encostar já é o defeito.
- **Candidato que cruzaria é recusado.** O elemento fica na base, com a regra nunca-piora
  intacta — mesma mecânica de recusa do teto de 2%.
- A **escolha da base** passa pelo mesmo corredor, porque ela também move um elemento
  sozinho: no Guaxindiba a colocação bruta e a pós-global estão a ~700 px uma da outra, e foi
  o conjunto misturado (muro no bruto, campo no pós-global) que trocou as duas linhas de
  tinta — o empurrão local, de 30 e 85 px, não teria como fazer isso. Quando a base preferida
  não tem nenhuma posição admissível, a outra colocação entra como alternativa.
- Quando a base cruza vizinho, mover deixa de ser opcional: a janela é **recentrada na
  correção mínima** que devolve o elemento ao corredor, e a colocação admissível vale mesmo
  com menos tinta. Ordem certa com menos tinta vence linha trocada. O teto de 2% continua
  limitando quanto o elemento procura tinta; ele não pode impedir a correção que a ordem
  exige, e dentro do corredor o elemento não alcança a tinta do vizinho por construção.
- Se nenhuma colocação preservar a ordem, o elemento fica na base preferida e o relatório
  declara `order_unresolved`. Proposta incompatível com as vizinhas vai para a revisão; não
  se escolhe um lado em silêncio.

O relatório por proposta declara `order_constrained` (o elemento foi movido por obrigação de
ordem, não por ganho de tinta) e `order_unresolved`, e o resumo do eixo traz
`ORDER_GUARD:relocated=n/N;unresolved=m`.

A ordem preservada é a das tangentes, que é o que diz qual elemento está por fora e qual
está por dentro. Duas arestas não paralelas ainda podem terminar coincidentes dentro da
tolerância da tinta — quando a própria proposta é internamente incompatível, como o contorno
do terreno do Guaxindiba, desenhado 316 px abaixo da linha dele. Coincidente é o caso que o
revisor resolve declarando `keep_apart`; trocado não tinha como resolver.

Uma polilinha aberta só é tratada como arco quando os vértices cabem num círculo com
resíduo relativo pequeno **e** existe flecha mensurável sobre a corda. Sem o teste da
flecha uma reta passaria — reta é o limite de um círculo de raio infinito —, e o estágio
inventaria curvatura que ninguém desenhou.

### Orientação do arco: observação se lapida, chute se reconquista

Até `geometry-extraction@1.0.0` a orientação **nunca foi observação do modelo**: o contrato
não tinha ângulo inicial nem final para `kind="arc"` e `proposals_from_geometry` fabricava
a abertura como 0..π fixo. No Guaxindiba isso pôs as duas meias-luas giradas um quarto de
volta em relação à tinta — com cobertura suficiente para passar no limiar e forma
visivelmente errada.

O contrato `@2.0.0` pede três pontos-âncora ao arco — onde a tinta começa, um ponto no meio
da curva e onde ela termina ([Prompt Contracts](PROMPT_CONTRACTS.md)) —, e com eles
orientação **e extensão** passam a ser observação. Os ângulos saem das âncoras de forma
determinística e **em pixels**, medidos contra o centro declarado; o `radius` do contrato
continua mandando no raio, e o `arc_mid` é o que resolve arco maior × arco menor sem
depender de convenção de sentido.

O re-fit se ajusta ao que a evidência autoriza, e a proposta declara qual dos dois casos é
o dela (`arc_angles_observed`):

| Origem da abertura | Busca de orientação |
|---|---|
| Observada nas três âncoras | Lapidação em **±15°**, mesmos passos 5°→1° |
| Fabricada (contrato v1, âncoras omitidas ou degeneradas) | Reconquista na **volta inteira** |

A janela existe porque orientação observada é evidência: o modelo erra o assentamento e
alguns graus de leitura são esperados, mas um quarto de volta com mais tinta por baixo — a
meia-lua vizinha, a curva do canteiro ao lado — apagaria em silêncio o que a folha mostrava
e o relatório declararia um giro que a própria observação contradiz. Quinze graus é o dobro
do passo grosso mais o passe fino: cabe erro de leitura, não cabe outra forma. Quando
observação e tinta discordam de verdade, a proposta fica onde foi observada, com pouca
tinta por baixo, e a conferência a rebaixa — a discordância é do revisor.

Centro e raio seguem no re-fit nos dois casos. O que continua preservado é a **extensão**
angular, quanto o arco varre, e a contagem de vértices; quando as âncoras foram observadas,
essa extensão também é observação. O giro aplicado é declarado por proposta no relatório.

Três garantias fecham o estágio:

- **Nenhuma proposta sai com menos tinta do que a melhor colocação admissível que tinha.** A
  base do refino é a melhor colocação disponível (bruta ou pós-global) e o resultado só é
  aceito quando a supera — salvo quando a própria base cruza vizinho, caso em que sair de
  cima dele é obrigação e não escolha.
- **Nenhuma proposta troca de lado com outra**, pela lei da ordem descrita acima.
- **Nenhuma ponta de linha para em traço cruzante**: parada exige trecho contínuo próprio.
- **Nenhum contorno é achatado nem nenhuma linha é apagada**: o refino por aresta e o
  deslizamento de pontas preservam ao menos metade da extensão do elemento, ou não se aplicam.
- **Nenhuma linha adota a extensão de um traço que continua além dela.**
- **Nenhuma orientação observada é substituída**: o arco com âncoras só é lapidado em ±15°,
  e o desacordo com a tinta vai para a revisão em vez de ser resolvido por conta própria.
- **O ID da proposta é preservado**, porque ele identifica a observação e não a posição.

O antes e o depois ficam auditáveis por elemento: cobertura bruta, pós-global e
pós-refino, qual colocação virou base, que ajuste foi aplicado, os deltas de centro,
raio e orientação, os quatro deslocamentos de aresta e os dois de ponta.

## JSON bruto e overlay

O JSON preserva os candidatos aceitos pelo detector até os limites configurados.
O overlay é mais conservador e mostra apenas scores suficientes para revisão
visual. Ocultar um candidato fraco no overlay não o remove silenciosamente do JSON.

Cores:

- Verde: linhas.
- Roxo: círculos.
- Laranja: contornos.

O banner do overlay declara `PIXELS ONLY` e `NOT EXPORTABLE`.

## Guardrails

- Nenhuma coordenada em pixel recebe unidade de engenharia.
- Nenhum candidato entra diretamente em `SceneRevision`.
- Limite atingido é registrado, não tratado como resultado completo.
- Detector não associa texto, cota, layer ou objeto.
- Proposta conflitante não é removida para obter uma resposta mais conveniente.
- Seleção humana registra o proposal ID e a calibração como provenance. Ela só
  cria entidade `approximate` depois de duas linhas CV serem explicitamente
  ancoradas em entidades `exact`/`derived` não paralelas; nenhum pixel vira
  geometria `exact`.

## Avaliação

`make vision-eval` usa somente uma fixture sintética. O relatório mede recall de
quatro bordas, recall/precisão do círculo e os rates de bloqueio. O gate falha se
qualquer proposta puder ser exportada.

Resultados sobre PDFs reais são observacionais. Eles provam que o estágio roda e
falha de forma segura, não que a geometria real foi reconstruída corretamente.

## Artefatos locais

Para cada página:

- `vision-proposals.json`;
- `vision-overlay.png`.

Para cada dataset:

- `vision/summary.json`;
- `vision/contact-sheet.png`.

Todos permanecem em `output/`, fora do Git e sujeitos à retenção de sete dias.
