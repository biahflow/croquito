# Functional Design Document

Status: Accepted for MVP  
Responsável: Product / Design / Engineering  
Última revisão: 2026-08-23 (seções "O orçamento é assinado antes de sair" e "De onde vem a
tabela de preços" — aprovação nominal com segregação entre quem orça e quem assina, despacho
como ato próprio, e a escolha da tabela publicada pela plataforma, F-035 e F-037); antes:
2026-08-21 (seção "Revisão" — vista de exceções do modo automático local, F-029)

## Experiência principal

### 1. Autenticação e projetos

Usuários entram por convite do provedor OIDC. A tela inicial lista somente projetos do
tenant atual, com estado legível, data de expiração e ação para acompanhar ou abrir a
revisão mais recente. Identificadores internos de job não são exibidos nem digitados:
a interface seleciona o job do projeto internamente.

### 2. Upload

O usuário cria projeto, escolhe unidade padrão (`m` por default) e envia um PDF
por URL assinada diretamente ao storage privado. O PUT inclui checksum assinado;
a API confere objeto, tamanho, MIME e digest antes de criar o job. Antes do
processamento, a UI exibe somente os campos necessários para o projeto e o envio.

Quando providers reais estiverem habilitados, a API exige autorização contratual
ativa para o tenant. Um operador de plataforma (papel `platform_operator`) administra
essa autorização pela própria jornada "Plataforma" do produto — tela dedicada,
visível só a quem tem o papel, com lista de tenants e ativação/desativação
inline por `agreement_reference`; não há mais curl nem edição de allowlist por
documento. Um snapshot imutável dessa autorização é ligado ao job; sua revogação
bloqueia novas chamadas externas. O piloto atual analisa apenas a primeira página;
páginas restantes aparecem como limitação explícita, sem descarte silencioso.

A mesma tela de Plataforma administra a **disponibilidade de jornada por tenant**
(F-034). Cada jornada — Croqui, Medição e Orçamento — tem um estado declarado no
ambiente (`liberada`, `piloto` ou `indisponível`) que a tela **mostra e não edita**:
mudar o estado é alterar configuração e publicar, e a tela diz isso por escrito. Em
`piloto`, a jornada existe só para os clientes autorizados nominalmente ali, com
referência de contrato, quem autorizou e quando. Autorizar um cliente numa jornada que
não está em piloto é recusado pelo servidor, com a frase por extenso, e nada é gravado.
Revogar não apaga: a linha permanece na lista com a data da revogação.

A tela de Plataforma administra também o **índice de embeddings** de cada tabela do acervo
([F-041](../features/F-041-braco-semantico-hospedado/feature.md),
[ADR-0054](../adr/0054-indice-de-embeddings-publicado-e-braco-semantico-hospedado.md)) — é
ele que faz a shortlist sair híbrida no recálculo. O operador lista os índices publicados
(com a tabela indexada, a receita de texto, o provider, o modelo, as dimensões, a contagem
de códigos, quem publicou e quando, e o estado escrito por extenso), publica o
`catalog-embeddings.json` e retira um índice de circulação. O índice é **construído pelo
comando pago `index-catalog` do CLI, nunca pela tela**: o servidor lê e confere o
documento, e a tela diz isso por escrito para ninguém procurar um botão que não existe.
Retirar não apaga — o arquivo continua existindo, a shortlist já calculada continua citando
o digest do índice que a produziu, e a fonte volta a entrar só pelo braço léxico. As quatro
recusas da publicação (acima do teto de leitura, documento ilegível, índice de outro
catálogo e conteúdo já publicado) aparecem em português, nunca como código cru.

Erros de MIME, limite ou PDF corrompido são apresentados antes de iniciar o job.

### 3. Processamento

A UI mostra etapas reais, não uma porcentagem artificial:

```text
validating → rendering → extracting → reconciling → solving → previewing
```

O cliente consulta o estado por polling com backoff. Atualizar a página não perde
o job.

### 4. Seleção de página e papel

Quando uma página contiver múltiplos desenhos, o usuário confirma:

- Planta principal.
- Detalhe construtivo.
- Lista/material.
- Ignorar, com justificativa.

O sistema nunca descarta automaticamente uma página só por ter pouco conteúdo.

### 5. Revisão

A revisão é uma jornada passo a passo — decisões das leituras, traçado, aprovação
técnica e exportação — e não uma tela com tudo aberto ao mesmo tempo. Um trilho no alto
da coluna de painéis lista as quatro etapas com marca, título, resumo e estado escrito
(concluída, em aberto, bloqueada). A etapa em andamento aparece aberta; a concluída vira
resumo recolhido que reabre por clique; a que ainda não pode começar aparece bloqueada,
com o motivo em língua de obra — "aguarda 12 leituras pendentes", "o desenho ainda não
tem formas detectadas", "aguarda o traçado resolvido", "aguarda a aprovação técnica".
Estado nunca é indicado só por cor.

O trilho espelha a máquina de estados do servidor: ele organiza a tela e não substitui
nenhuma verificação da API. Nada é liberado porque a interface achou que sim.

- Decisões: concluída quando nenhuma leitura do pacote está proposta ou ambígua;
  rejeitar é decidir.
- Traçado: só abre com **todas** as leituras decididas e com formas detectadas no
  desenho; concluído quando existe cena métrica com geometria.
- Aprovação: só abre com cena métrica com geometria; concluída quando a cena está
  aprovada.
- Exportação: só abre depois da aprovação; concluída quando o pacote auditado está
  disponível. Exportação reprovada não vira bloqueio do trilho: a etapa continua em
  aberto e o código da falha e os erros de auditoria ficam visíveis na própria etapa.

Quando o servidor faz a jornada andar — o traçado fecha, a aprovação entra —, a etapa
seguinte abre sozinha; a etapa reaberta por clique deixa de valer nesse momento.

**Vista de exceções (modo automático local, F-029).** Quando o ambiente local está com
o modo automático ligado (dupla chave do ADR-0041; nenhum ambiente hospedado), leituras
com confiança calibrada acima do corte chegam à tela já confirmadas pelo sistema, e a
etapa de decisões ganha uma faixa de contadores — auto-associadas, precisam de revisão,
não resolvidas — e um filtro de dois estados ("só exceções"/"todas"). O filtro esconde
apenas linha decidida; pendência, linha citada por bloqueio e aviso crítico nunca somem.
A linha auto-decidida permanece na lista com marca textual ("associada pelo sistema",
com a versão do score e a confiança em vírgula decimal) e o mesmo caminho de correção
declarada das decisões humanas; máquina nunca é apresentada como pessoa. Sem o modo
ligado, a tela é a de sempre — sem faixa, contador ou filtro.

**Dois tiers, contados e marcados separado (ADR-0044).** A leitura sem papel de geometria
de planta — elevação (`h=…`) e recado da folha — entra por um tier próprio, com uma
testemunha só e **sem elemento associado**, exatamente como a anotação da folha que o
profissional declara: ela não mede a planta, não entra na geometria e o erro possível é
um texto a conferir, não uma cota errada dentro do desenho. Onde o texto fica continua
sendo declaração humana, no aceite do traçado; a justificativa registrada traz o elemento
provável como dica. Quando houver alguma, a faixa ganha o contador "anotações
automáticas" ao lado das auto-associadas, com a frase que explica por que a segunda
leitura não foi exigida, e a linha é marcada como "anotação automática" em vez de
"associada pelo sistema" — palavra diferente, não só tom diferente. Cota de planta nunca
entra por esse tier, com qualquer confiança. Sem anotação automática na revisão, o
contador não aparece zerado. As confianças e o shadow
são observação para calibração: nada na interface decide, pré-marca ou aprova por conta
deles.

Layout:

- Coluna da jornada: o trilho e o conteúdo da etapa aberta — leituras, evidência
  recortada e decisão; formas detectadas, decisão em lote e aceite de traçado; estado de
  publicação, bloqueios e aprovação técnica; exportação e download do pacote auditado.
- Palco do desenho, sempre visível e fora da jornada: imagem original com bounding
  boxes e cotas, geometria vetorial sobreposta, zoom, rotação e pan sincronizados.

Dentro da etapa de traçado, a calibração pixel→metro é o caminho de aproximação — só
necessária para aceitar forma sem cota escrita — e nasce recolhida, aberta sob demanda,
para não disputar espaço com o aceite em lote.

Controles do viewer. Eles são apresentação: nenhum deles altera evidência, manifesto,
pacote entregue ou payload de API.

- Zoom de 1× a 4×. Imagem e overlays são filhos do mesmo transform, então eles nunca
  saem de registro entre si.
- Pan por arrastar o desenho, além de rolagem e teclado. Ampliada, a folha inteira
  continua alcançável.
- Rotação em passos de 90°, por botão ou pela tecla `R` (`Shift+R` gira no sentido
  oposto), com o ângulo atual sempre visível em texto. A escolha é lembrada por job no
  próprio browser e volta na reabertura, porque o croqui costuma ser desenhado em
  paisagem numa página retrato.
- O recorte ampliado da leitura selecionada nasce na rotação atual do viewer e gira
  independente depois disso: as cotas de uma mesma folha estão escritas em orientações
  diferentes entre si.
- A caixa da leitura selecionada é desenhada mesmo quando a revisão não trouxe
  propostas de visão.
- Seleção por retângulo com `Shift`+arrasto, disponível enquanto as formas detectadas
  estão abertas e nenhuma cota está sendo amarrada. O retângulo aparece tracejado sobre
  o desenho e, ao soltar, **adiciona** à seleção toda forma ainda sem decisão que ele
  tocar — encostar basta, como no CAD. Arrasto sem `Shift` continua deslocando o
  desenho e o clique na forma continua marcando e desmarcando uma a uma; o retângulo
  nunca remove nada da seleção. A contagem de formas selecionadas é anunciada em texto
  vivo, porque o gesto acontece longe do painel que a mostra.

Cores de precisão:

- Verde: `exact`.
- Azul: `derived`.
- Laranja: `approximate`.
- Vermelho: `unresolved`.

Nomenclatura do painel de geometria. Quem revisa é profissional de obra, então
identificador interno não aparece em texto e enum não aparece em inglês. Cada forma
detectada recebe um balão numerado estável pela posição na lista (① a ⑳ e, daí em
diante, "nº 21"), seguido do rótulo que a extração escreveu quando ele existe e de uma
descrição geométrica quando não existe — "⑫ linha vertical · ≈ 34 m". A medida sai em
pixels enquanto não houver calibração e em metros aproximados depois dela, sempre com o
sinal de aproximação. Decisão da proposta, tipo de medida, relação de associação, modo
de calibração e precisão são escritos em português. A calibração é apresentada como a
régua da conversão pixel→metro e mostra o casamento que o servidor resolveu, uma linha
por âncora, ligando a forma detectada à aresta métrica correspondente. Os
identificadores de proposta, leitura e entidade continuam disponíveis para suporte e
auditoria em `title` e numa ação discreta de copiar, nunca em prosa. Quando a página
aguarda classificação, cada região candidata mostra o nome do papel em português —
planta principal, detalhe construtivo, lista de materiais, bloco de anotações ou papel
ainda não identificado — nunca o enum bruto, que fica só em `title` para auditoria.

Operações permitidas:

- Corrigir texto, valor ou unidade.
- Reassociar medida a segmento/entidade.
- Confirmar tipo geométrico e constraint.
- Excluir falso positivo.
- Selecionar ou rejeitar proposta geométrica; a seleção cria somente uma entidade
  `approximate` depois de calibração métrica confirmada.
- Criar medida faltante com região de evidência.
- Ajustar pontos somente de entidades aproximadas.
- Solicitar reanálise de uma região.

Alterações criam nova `SceneRevision`; nunca sobrescrevem uma revisão aprovada.

Toda decisão de leitura (confirmar, corrigir e confirmar ou rejeitar) e toda amarração
de cota a uma linha traçada exigem uma justificativa escrita pelo profissional, nas
próprias palavras, com a mesma régua de 3 a 500 caracteres da API. O campo nunca vem
pré-preenchido com frase pronta e é validado no envio, com a pendência explicada em
texto; a interface não desabilita o botão em silêncio. O texto gravado é auditado como
palavra do revisor, no mesmo padrão já usado pelo aceite em lote e pela decisão
individual de proposta geométrica.

Leitura que o pipeline reconhece como recado da folha — sinal `annotation_suggested`
do pacote ou o padrão `h=` no próprio texto — abre o formulário com "Anotação da
folha" pré-selecionada e uma frase dizendo de onde veio a sugestão (F-021). Sugerir
não é decidir: os candidatos continuam todos na lista, trocar a seleção à mão vale
mais que a sugestão, e a justificativa continua nascendo vazia.

Folha cheia de recado ("h=" em cada muro) faz o revisor repetir dezenas de vezes o mesmo
ato, então essas leituras — e **somente** elas — chegam pré-marcadas num lote, com uma
caixa ao lado de cada linha da lista. O lote não decide nada sozinho: o revisor escreve
**uma** justificativa, na mesma régua de 3 a 500 caracteres, e o envio grava N decisões
individuais, uma por leitura, cada uma com o seu autor e o mesmo motivo — é o mesmo
espelho que o aceite em lote de propostas já faz. Desmarcar vale mais que a sugestão e
não é desfeito enquanto a revisão for a mesma; a revisão seguinte volta a marcar o que
ainda restou sugerido. Cota de chão nunca entra no lote: ela declara associação e eixo,
uma a uma.

Quando o braço de OCR rodou e não encontrou o texto de uma leitura na mesma região da
folha, a linha da lista mostra "⚠ sem 2ª testemunha" e o painel de decisão mostra a
frase completa (F-010) — a corroboração nunca bloqueia nem rebaixa status, só informa;
confirmação e ausência do braço de OCR seguem silenciosas para não virar ruído.

#### Corrigir uma decisão já registrada

Leitura decidida deixa de mostrar os botões de decisão e passa a mostrar o registro:
quem decidiu, quando, e a justificativa escrita na hora. Ao lado dele há um botão único,
"Corrigir decisão registrada", que reabre o mesmo formulário da decisão com os valores
vigentes já preenchidos — texto, valor, unidade, tipo e a associação atual — e a
justificativa **vazia**: corrigir é um ato novo e pede palavra nova. A associação
pré-selecionada é enviada explicitamente, nunca herdada em silêncio. O envio se chama
"Registrar correção", e a tela diz o que acontece com o passado: "a decisão anterior
fica guardada no histórico da obra — nada se apaga".

Se o desenho já usava a medida corrigida, ele não é apagado nem movido: a cena passa a
carregar o bloqueio "medida corrigida depois do desenho — refaça o traçado antes de
exportar", visível na lista de bloqueios como qualquer outro
([ADR-0022](../adr/0022-declared-rectification-of-review-decisions.md)).

#### Aceite de traçado em lote

Traçar um croqui forma a forma é inviável, então o profissional monta um aceite em
lote a partir da mesma seleção múltipla que já usa para geometria aproximada: clicar
nas formas do desenho marca e desmarca, e a seção de traçado lista o que está marcado
pelo nome de obra de cada forma. Sobre cada forma aceita ele declara, por botão com
estado escrito, se ela é hachura, se dispensa legenda na prancha e se entra como
desenhada — elemento intencionalmente fora do esquadro, que a regularização não força
em faixa. Nenhuma dessas marcas é inferida do desenho.

Detalhes desenhados ao lado da planta — painel, arquibancada, isométrico — viram
grupos com código, título e escala declarada: escala verdadeira, quando as cotas do
grupo mandam nele, ou sem escala, quando o desenho entra como está e as cotas do grupo
viram notas. Dois elementos desenhados um sobre o outro que o profissional reconhece
como distintos são declarados como um par a manter separado. Grupos e pares ficam
listados com ação de desfazer, e a planta principal nunca pode ficar vazia.

Nem toda cota confirmada mede um elemento sozinho. A folha traz vão entre duas formas
(o 6,60 do campo até o muro), trecho interno do mesmo elemento (o rebaixo do painel),
anotação presa a um elemento e cota que só existe na geometria já resolvida (o dente do
muro, que é 4,80 − 3,30). Essas amarrações são declaradas dentro da própria etapa de
traçado, uma leitura por vez, numa lista das cotas confirmadas que escreve o que cada
uma mede hoje — “mede a forma ①”, “vão entre ① e ④”, “anotação da folha — sem vão”.

A pergunta ancora na evidência: abrir a linha da cota mostra o mesmo recorte ampliado da
folha usado na decisão, e a resposta é dada **clicando no desenho** — a primeira e a
segunda forma do vão, as duas pontas de cada trecho, o ponto onde a cota derivada pousa.
Coordenada de pixel nunca é digitada. Enquanto o gesto está de pé, uma faixa viva diz o
próximo passo em língua de obra e quantos trechos já fecharam; `Esc` conclui o que já
está marcado e descarta a ponta solta. O clique vale também sobre forma aceita em lote
anterior, porque um vão pode amarrar um elemento já decidido, e o rascunho aparece sobre
a folha — âncoras e a linha do vão — sempre repetido por escrito na lista, nunca só em
cor ou desenho.

“Ainda não sei” é resposta legítima: a leitura sem amarração continua valendo como foi
decidida, e a cota que não alcança o traçado volta declarada como não aplicada em vez de
ser adivinhada. Texto declarado da cota (o portão `1,0 x 2,05`), orientação da nota, nota
na legenda do elemento e nota no carimbo são escolhas escritas, com ação de desfazer.
A montagem inteira — formas marcadas, declarações e amarrações — sobrevive a uma recarga
da página enquanto a aba estiver aberta; traçado resolvido a limpa, conflito a preserva.

O aceite é enviado com as versões-base da revisão e da cena e acompanhado por uma
região viva de status, como a exportação. São três desfechos possíveis:

- Traçado resolvido: a cena métrica **não aprovada** da revisão é substituída pela
  cena traçada, a tela recarrega revisão e cena e a montagem é limpa.
- Traçado precisa de revisão: cada pendência aparece em texto, citando a cota ou a
  forma que falta, junto das cotas que não foram aplicadas. Nenhuma revisão é criada.
- Outra decisão entrou antes: a revisão avançou entre o aceite e a execução. A tela
  recarrega, explica o ocorrido e **preserva a montagem** para reenvio; não é erro.

Quando o traçado fecha, a mesma região de status resume em linguagem de obra a
conferência das cotas confirmadas contra a geometria traçada — quantas fecharam, a
pior diferença encontrada e onde ela ocorreu — sem duplicar o alarme de um bloqueio já
listado na mesma tela.

A mesma região diz **por que** cada cota confirmada não virou vão, em língua de obra e
com o código cru ao lado — alvo aceito como desenhado, eixo não declarado, âncora sem
aresta perpendicular, as duas âncoras na mesma faixa, nota sem geometria que a sustente.
Onde o conserto é mecânico ele cabe num clique: tratar a forma como retangular, amarrar
a cota a uma das alternativas que a revisão já ranqueou, declarar o par como mantido
separado, abrir a correção da leitura com os valores vigentes. Nenhum desses cliques
envia coisa alguma — eles mexem no rascunho do aceite ou abrem o formulário onde a
declaração se faz, e o envio continua sendo o clique em "Aceitar traçado". Duas cotas
confirmadas que prometem distâncias diferentes para o mesmo vão são nomeadas par a par
pelos textos que a folha escreve, e cada cota aplicada mostra onde ancorou na prancha,
em metros: o revisor confere o traçado contra a folha sem abrir o CAD.

O ponto de partida de "como desenhado" é recalculado a cada revisão nova, e só para as
formas que o revisor nunca tocou à mão — confirmar a cota do muro depois de tê-lo marcado
passa a valer sobre ele, em vez de envelhecer calado até o traçado resolvido. Forma cujo
estado o revisor mexeu, pelo chip da lista ou por um conserto do consultor, nunca é
re-semeada: semente não escreve sobre ato humano.

O princípio é o mesmo do resto da revisão: a interface declara o que o profissional
aceitou, o solver decide a geometria no worker, e revisor, papel e horário do aceite
vêm da sessão autenticada — a tela nunca os envia nem os escolhe.

#### Conversa sobre a folha

Nas etapas de decisões e de traçado, um painel auxiliar recolhido — nunca uma etapa da
jornada — deixa o profissional perguntar sobre a folha em revisão e receber uma resposta
**observacional** ([ADR-0023](../adr/0023-review-chat-as-an-observational-agent.md)). A
pergunta aponta o que ele já tem em mãos: a leitura aberta e as formas marcadas no
desenho viajam como âncoras, exibidas como etiquetas que saem por clique antes do envio.
Nada é inferido por proximidade.

A resposta chega por acompanhamento, como o traçado e a exportação: o estado do turno é
escrito ao lado da pergunta — na fila, lendo a folha, respondeu, ou falhou com o motivo
em língua de obra ("a resposta citou algo que não está na folha; foi descartada por
segurança"). Uma pergunta por vez: enquanto a anterior não fecha, a tela não oferece a
próxima. "Ainda não sei" é resposta legítima e aparece como pergunta em aberto.

Cada sugestão da resposta vira um cartão ancorado na evidência: o mesmo recorte ampliado
da leitura citada, o nome de obra das formas citadas com atalho que as destaca no
desenho, e a frase do ato com o **valor como está escrito na folha** — que vem sempre do
pacote de revisão, nunca do texto do agente. O botão "Usar este rascunho" **só
pré-preenche**: decisão de leitura abre o formulário de sempre com a associação
sugerida e a justificativa sugerida, editável, e o envio continua sendo o ato humano;
sugestão de traçado entra na montagem do aceite, que o profissional revisa antes de
enviar. Rascunho sobre leitura já decidida não é oferecido — corrigir decisão registrada
é ato próprio, com palavra nova.

O painel repete, fixo no rodapé, o que a garantia significa: nada ali entra no desenho
sem a confirmação do profissional. O conteúdo da conversa não é gravado em storage do
navegador nem em telemetria.

### 6. Aprovação

O botão Aprovar permanece bloqueado quando existe issue `critical` ou entidade
`unresolved` relevante. Para entidades aproximadas, o usuário deve aceitar a
hipótese explicitamente.

A confirmação mostra:

- Número de entidades por precisão.
- Medidas alteradas.
- Hipóteses aceitas.
- Elementos omitidos do export.

A decisão registra o UUID exato da revisão, revisor e papel profissional,
timestamp e aceite explícito de que evidência, geometria e limitações foram
verificadas. As três verificações são declaradas uma a uma, nunca pré-marcadas, e
acompanham uma declaração técnica de 20 a 500 caracteres. A aprovação cria outra
revisão; não altera o rascunho.

Cada critério de escopo declarado no caso aparece na tela com o **texto** do critério, não
com o código cru, e o profissional declara um dos dois desfechos por critério:

- **Coberto pela cena** — a geometria que está sendo aprovada atende ao critério; a
  pendência fecha como resolvida.
- **Reconheço como pendente** — o critério continua fora da cena e o profissional assina
  assim mesmo; a pendência fica registrada como aceita.

Os dois são atos distintos, nunca o mesmo botão, e viajam separados no pacote entregue.
Critério que não recebe nenhuma das duas declarações continua bloqueando a aprovação.
Nenhum dos dois dispensa pendência de geometria: resíduo numérico, cota incompatível com
a geometria, aproximação não aceita e calibração obsoleta continuam bloqueando. Vale para
a cena do solver retangular e para a cena traçada, sem diferença. Ver
[ADR-0014](../adr/0014-scope-criteria-acknowledgement-at-approval.md) e
[ADR-0017](../adr/0017-per-criterion-coverage-declaration-and-trace-parity.md).

Quando o botão está desabilitado, a interface lista os motivos em texto; nenhum
bloqueio é escondido para "limpar" a tela.

Sem sessão autenticada, a interface não exibe evidências nem permite decisões. A
interface habilita a revisão somente para a pessoa autenticada com o papel
profissional elegível; a API deriva identidade e papel do JWT e revalida as
mesmas condições antes de persistir a aprovação. A interface nunca envia ou
escolhe o papel profissional por conta própria.

A área de revisão autenticada não contém casos, cotas ou botões de simulação
embutidos no bundle. Ela abre a revisão mais recente de um projeto selecionado,
carrega o snapshot atual de evidências e candidatos, mostra imagem e overlay sob o
mesmo transform de zoom, rotação e pan, e envia uma decisão por leitura com
`base_version`. Confirmar/corrigir exige uma
associação explícita; rejeitar preserva a proposta no histórico. Loading, erro,
conflito recuperável e uma alternativa textual para blockers/estado da leitura
são obrigatórios. URLs de preview são efêmeras e não entram em telemetria do
browser.

Propostas de visão continuam em pixels até que o profissional confirme uma
calibração com duas linhas CV e duas entidades `exact`/`derived` não paralelas da
cena solucionada. A API calcula e versiona o transform pixel→metro; o browser
nunca envia coordenadas métricas derivadas. Linha, círculo e contorno selecionados
viram respectivamente `line`, `circle` e `polyline` fechada em layer
`APROXIMADO`, com precisão `approximate` e provenance da proposta/calibração.
Rejeitar preserva a proposta no histórico. A seleção não aceita aproximação, não
marca entidade como `exact` e não libera exportação.

#### Identidade de elemento na revisão

Ao lado do preview da cena, a etapa de aprovação apresenta a **identidade de elemento**
([ADR-0058](../adr/0058-quantitativo-derivado-do-scene-graph-e-identidade-de-elemento.md)).
A tela distingue por texto e por forma as entidades **sem** identidade — etiqueta tracejada
que diz "sem identidade" por escrito — das entidades **com** identidade, etiquetadas com o
`element_ref`.

O agrupamento proposto pelo sistema aparece **rotulado como proposta** (`proposta ·
unresolved`, traço tracejado) e nunca como identidade, e diz por qual sinal foi gerado —
mesma procedência de detecção, ou o mesmo rótulo mais próximo. Confirmar uma proposta é o
**mesmo ato** da declaração manual: a proposta apenas semeia a seleção, e a escrita passa
por `POST /v1/jobs/{job_id}/elements`, sem segundo caminho de identidade. Recusar registra
a recusa com motivo, e a proposta recusada não volta a ser oferecida. Declarar sem proposta
alguma, pela seleção manual das entidades, existe e usa a mesma rota.

O `element_ref` é cunhado pelo servidor no ato: a tela não oferece campo para o nome do
elemento, e declara por escrito de quem é a cunhagem. Depois do ato, a tela mostra o ref
cunhado com o papel profissional de quem declarou e o instante, sobre qual revisão da cena.
Como o ato cria revisão nova, a revisão em tela é recarregada, para que a aprovação assine
a revisão em que o elemento existe.

Ao lado do ref cunhado, o elemento carrega um **rótulo legível** — o nome que a pessoa lê
("Alambrado da quadra"), escrito no mesmo ato da declaração e apresentado ao lado do
`EL-00N`. O rótulo é **opcional**: cena sem rótulo nenhum é válida, e um elemento sem nome é
apresentado como "sem rótulo", nunca com um traço mudo. Ele **não é identidade**: o
casamento cena↔legenda continua sendo só pelo `element_ref`, e dois elementos com o mesmo
rótulo continuam sendo dois elementos. Ele também não substitui o texto escrito na prancha,
que continua sendo a redação que o humano lê no desenho. Renomear é ato declarado, com
autor, instante e motivo, criando revisão nova — nunca edição silenciosa; revogar a
identidade leva o rótulo junto, porque sem elemento o nome não nomeia nada.

Um elemento cuja precisão é `approximate` ou `unresolved` é marcado como **não alimenta a
medição**, com o motivo escrito na tela — a aproximação multiplicada por preço unitário
vira uma linha de R$ que ninguém lê como aproximada. A precisão do elemento é a mais fraca
entre as entidades **físicas** dele; anotação (`text`, `dimension`, `diameter_dimension`)
documenta o elemento e não decide a precisão dele. Camadas diferentes no mesmo grupo são
recusadas pelo servidor, e a tela apresenta a recusa legível, nomeando as camadas
misturadas — nunca como erro genérico.

Sem nenhuma identidade declarada, a revisão não ganha etiqueta, selo nem contagem de
elemento em lugar nenhum: ela fica idêntica à de hoje. A tela não soma, não multiplica e
não arredonda quantidade — ela não exibe quantidade nenhuma.

### 7. Exportação

Após aprovação, a exportação é assíncrona: a interface solicita o pacote e acompanha
os estados `QUEUED`, `RUNNING`, `COMPLETED` e `FAILED` com região viva de status. O
sistema congela a revisão, gera o DXF, reabre, audita e renderiza o próprio arquivo
fora do request path.

O ZIP é publicado somente se a auditoria aprovar, e inclui DXF, PNG,
`auditoria.json`, `quantitativos.csv`, hipóteses e o registro de aprovação com as
ressalvas reconhecidas. O download usa URL assinada de curta duração, exibida ao lado
do resultado da auditoria e do SHA-256 do DXF.

Uma exportação reprovada não disponibiliza link algum: a interface mostra o código da
falha e os erros de auditoria. Uma revisão aprovada tem no máximo um pacote por
formato; pedir de novo devolve o mesmo artefato.

## Medição de obra (planilha MAPÃO)

Fluxo do orçamentista, paralelo ao de croqui → DXF e com vocabulário próprio
([Valuation Context](../architecture/VALUATION_CONTEXT.md)). O profissional levanta
quantitativos, confirma os códigos de catálogo de cada item — a relação elemento ×
serviço é N:N, então um item pode receber vários códigos e o pacote é fechado por ato
próprio ([ADR-0053](../adr/0053-cardinalidade-n-n-elemento-servico.md)) —, monta a
memória de cálculo e recebe o boletim de medição da obra em planilha, com fórmulas
conferíveis célula a célula.

No M1 nada disso está na sessão autenticada: existe apenas a demonstração determinística
`make valuation-demo`, que parte de um catálogo sintético e produz `medicao.xlsx` (abas
BM e MEMÓRIA), `valuation.json` e `audit.json`. A planilha é render, não fonte: ela é
reaberta, tem as fórmulas recomputadas e é conferida centavo a centavo contra o JSON
canônico; divergência não publica arquivo nenhum.

Importar o MAPÃO do cliente devolve duas coisas ao orçamentista. Quando a planilha passa,
o relatório da importação diz o que a leitura observou sem recusar: quais medições estão
lançadas, qual número falta na sequência, quantas linhas separadoras foram puladas e quais
células chegaram com ruído de ponto flutuante no cache da fórmula. Quando o histórico já
publicado não fecha, a importação recusa fechada — nenhum artefato é gravado — e entrega o
dossiê da recusa: **todas** as divergências de uma vez, cada uma com a célula e os dois
números que não batem, em vez da primeira que apareceu. O dossiê é insumo de conversa com
a prefeitura; ele não aceita divergência nem destrava a importação.

O começo da cadeia — a legenda já quantificada da prancha do projetista — também tem
mecanismo, ainda fora da sessão autenticada: `extract-legend` gera uma prancha sintética e
extrai a legenda dela por fixture, e `extract-legend-real` lê a prancha real de cliente
com provider pago, atrás de teto de gasto e allowlist do documento (M5); `review-takeoff`
aplica as decisões do orçamentista item a item, com a mesma recusa de re-decisão da
revisão de cotas do croqui. Um item nunca nasce confirmado; a linha ilegível vira item
ambíguo, que só fecha quando o orçamentista informa a quantidade que a extração não
conseguiu ler.

Regras da interface de medição (escritas antes da primeira tela e vinculantes para
qualquer uma):

- Dinheiro trunca em duas casas; quantidade arredonda. A tela nunca mostra um total que
  o sistema não recomputou.
- Célula cujo valor não pode ser reproduzido com segurança por fórmula viva aparece com
  valor fixado e é declarada ao usuário, não escondida.
- Código de catálogo sugerido por modelo é proposta: entra como pendência de
  confirmação, nunca como associação feita.
- Sem aprovação nominal do orçamentista não há medição exportada.

A primeira implementação dessas regras é a **UI local de homologação** (M6,
[ADR-0020](../adr/0020-local-homologation-server-for-valuation.md)): o app
`apps/medicao` sobre o servidor `croquito-valuation serve`. A orçamentista revisa o
takeoff item a item sobre a prancha (bbox por estado, decisão nunca em lote, nada
pré-marcado), confirma ou rejeita os códigos de cada item com a descrição completa do
catálogo, busca por palavra-chave sempre à mão e o pacote de serviços do elemento —
vários códigos sobre a mesma medida, fechado por ato próprio ([ADR-0053](../adr/0053-cardinalidade-n-n-elemento-servico.md)) —
sinalizado como dica de leitura declarada; item rejeitado por falta de código no
SCO/contrato entra na lista visível de candidatos a aditivo (regra da obra licitada).
Essa lista é prévia calculada na tela — o **dossiê do aditivo** oficial nasce no
servidor, pelo mesmo gesto de fechamento do boletim: com toda decisão de código
registrada, "Gerar dossiê do aditivo" grava o artefato com a justificativa de cada
rejeição (a nota do orçamentista) e a tela passa a exibir a lista do servidor, sem
preço em nenhum campo — o pedido de RE-RA à prefeitura continua sendo ato humano
([ADR-0027](../adr/0027-price-source-provenance-and-bid-boundary.md)).
O boletim e a memória exibem exclusivamente números recomputados pelo servidor, com o
aviso permanente de que medição sem aprovação não exporta. Identidade e horário da
decisão são do servidor local; a tela não os envia. Ferramenta local declarada — a
sessão autenticada da medição é marco futuro e reaproveita estas telas.

A rodada nasce na própria tela: a orçamentista envia o PDF da prancha do projetista e a
leitura da legenda acontece automaticamente (ingestão local + extração por IA,
assíncrona, com transparência de custo/modelo no estado da rodada e falha visível com
nova tentativa explícita — nunca silêncio). A prancha exibida é só a prancha: nenhuma
marcação sobre o desenho por padrão; o item selecionado destaca apenas o próprio
recorte, e as marcações completas são opt-in. Durante a revisão de cada item, a tela
mostra automaticamente a referência do catálogo para o rótulo (códigos candidatos com a
descrição oficial completa e os trechos literais de inclusão/exclusão — "inclusive…",
"exclusive…", "Fornecimento e colocação") deixando à vista se mão de obra e materiais
já estão no preço composto; a confirmação do código continua sendo ato da etapa
seguinte. E âncora sem garantia não vira retângulo: a posição de um item sobre a
prancha só é desenhada quando o registro contra a tinta a confirmou
(`anchor: registered`); sem confirmação, a tela declara "localização não confirmada —
decida pela lista" em vez de apontar um lugar possivelmente errado.

Uma praça grande não cabe numa folha, e a tela passa a dizer isso
([ADR-0057](../adr/0057-multiplas-pranchas-por-praca-na-extracao-de-legenda.md)). A partir
da **segunda** folha a jornada ganha uma faixa de cartões — uma folha por cartão, com nome,
identidade da prancha, contagem de itens e o estado dito por extenso **e** por símbolo
próprio (`✓` extraída e revisada, `▲` pendente de revisão, `◐` em extração) —, a etapa
`Prancha` passa a se chamar `Pranchas` e nasce a etapa `Praça`, entre `Códigos` e
`Boletim`. Com uma folha só nada disso aparece: a rodada de uma prancha continua sendo a
tela de sempre. Acrescentar folha é ato humano em lote: a orçamentista marca quais páginas
do documento viram prancha, **nada vem marcado por padrão**, e o número de folhas que o ato
acrescenta — e o de leituras pagas que o lote seguinte dispara — fica escrito no próprio
botão, antes do clique. A praça não fecha com folha pendente, e a recusa **nomeia a folha**
("folha 2 de 3 …"), porque meia praça somada parece uma praça inteira.

A folha em foco atravessa a jornada inteira: imagem, overlay, itens, decisões de item,
shortlist, códigos, fechamento e revogação falam sempre **daquela** prancha, e trocar de
folha na faixa relê tudo com ela. A etapa de códigos é por folha — o conjunto de códigos é
de cada prancha e o boletim da praça é a união deles —, então ao lado da folha aberta a
tela lista **o que falta em cada uma**, com as contagens que o servidor deu de cada folha:
nada pendente na folha aberta não significa praça fechada. A etapa `Praça` mostra as folhas
do consolidado por digest, os vínculos declarados e, quando o boletim está montado, os
**números**: o total da praça, o total por código de cada folha e a memória com as parcelas
na folha onde cada leitura foi feita — todos como o servidor os calculou. A soma do mesmo
código **entre** folhas, e a deriva de centavo que o truncamento por linha pode produzir
(ADR-0062), são escritas pela PLANILHA GERAL na exportação e declaradas na auditoria dela:
esta tela não as calcula nem as estima, e diz isso por escrito — ela nunca soma, multiplica
ou arredonda dinheiro ou quantidade.

A pasta entregue à prefeitura ganha um par de abas por folha, e nome de aba tem teto de 31
caracteres — limite do formato da planilha. Nome de praça real não cabe nele ("Campo do
Morro da Bandeira" já estoura na primeira folha), então a aba passa a usar a forma curta do
nome **apenas quando o nome inteiro não couber**: caem primeiro as partículas de ligação
("Campo Morro Bandeira") e, se ainda faltar espaço, as palavras do meio são abreviadas,
preservando sempre a primeira palavra e a folha. O nome inteiro da praça e da folha
continua impresso **dentro** da aba, na identificação do BM e no cabeçalho da memória.
Praça cujo nome já cabia não muda de aba nenhuma — a pasta que a prefeitura já recebe
continua a mesma. Nome que não cabe nem encurtado é recusado quando o boletim é montado,
dizendo o teto e pedindo o nome mais curto, e não na hora de publicar o arquivo, quando já
não haveria o que fazer.

Declarar que duas leituras de folhas diferentes são o mesmo elemento é ato humano oferecido
**com a prévia do efeito no total**, calculada pelo servidor: as duas parcelas, o total sem
o vínculo e o total depois dele aparecem antes de gravar, e sem essa prévia a declaração
não é oferecida. Nada nasce escolhido, trocar uma das leituras apaga a prévia — um número
conferido de outro par é pior que número nenhum — e o motivo é obrigatório. Unidade
divergente não vira soma: os dois totais saem vazios com a divergência dita em palavra.

Duas ausências continuam declaradas em vez de disfarçadas: a folha que ainda não virou
pacote não desenha nada (um desenho de outra folha sob o cabeçalho desta engana com a
autoridade de um desenho, e não existe overlay da praça — cada retângulo está em pixels da
imagem da sua folha), e o desenho das âncoras da folha 2 em diante **não é refeito** depois
de uma decisão, porque o re-render em fila ainda é o da primeira folha; a tela o declara
vencido em palavra, e o recálculo pago da shortlist não é oferecido ali pelo mesmo motivo —
ele regravaria a shortlist da primeira folha. Pela mesma razão, na praça de várias folhas o
disparo **singular** da leitura não é oferecido: ele relê sempre a primeira folha, e seria
uma chamada paga na prancha errada. A releitura ali é o lote, que nomeia as folhas e
escreve no botão quantas chamadas pagas o ato dispara.

Conferir quantidade contra desenho pede área e pede ritmo. Na revisão do takeoff a prancha
ocupa a coluna larga e abre em tela cheia por gesto ("Ampliar", e `Esc` reduz), **sem
perder a aproximação corrente**: quem chegou até um item continua nele, maior. Cada âncora
leva o mesmo emblema numerado da lista ao lado, desenhado sempre **fora** do próprio
recorte para não cobrir a linha da legenda que ele marca, e o retângulo tracejado continua
distinguindo a âncora bruta da registrada. A decisão ganhou um caminho de lote sem virar
"confirmar tudo": a orçamentista marca, item a item, as linhas que conferiu certas e anota
as marcadas como confirmadas de uma vez, **sem tocar em quantidade nem unidade** — o que
ela afirma é que a legenda leu certo. Nada nasce marcado; item já decidido e item de
quantidade ambígua ficam fora da marcação em massa, com o motivo escrito ao lado da caixa,
nunca só no cinza de um controle desabilitado. Marcar não é anotar e anotar não é gravar: o
painel do lote está sempre visível, inclusive vazio, e a rodada só muda de versão quando o
lote inteiro é gravado — uma revisão para todas as decisões, ou nenhuma.

A busca de código tem dois gestos com custos diferentes, e a tela diz qual é qual. Ao
digitar (a partir de três caracteres, com espera curta entre teclas), a consulta sai pelo
**braço lexical fixado**: nenhuma chamada paga de embedding, nenhum cache de consulta
escrito, e a resposta que chega depois de outra tecla é descartada em vez de trocar a
lista sozinha; falha nessa via aparece ao lado do campo, nunca como banner de recusa da
rodada. A busca **completa** — semântica junto, quando a rodada tem índice, teto de gasto
e credencial — continua atrás do Enter ou do botão "Buscar", que é o gesto explícito. A
frase que resume o resultado declara a diferença entre o que casou por palavra e o que a
lista mostra (o braço semântico acrescenta vizinhos sem palavra em comum), e a degradação
declarada pelo servidor fica visível em vez de sumir.

A shortlist de código, uma vez gravada na rodada, pode ser **recalculada pelo gesto do
orçamentista**: o botão declara que sobrescreve `code-suggestions.json` com o algoritmo
atual do servidor e que as decisões de código já registradas não mudam; o custo do clique
é o do braço semântico daquela rodada, escrito ao lado do botão. O recompute cita o
digest-base lido — rodada que andou vira o conflito de sempre, com recarregar e decidir de
novo — e nunca descarta refino pago: shortlist com lineage de chamada paga é recusada pelo
servidor em vez de sobrescrita. É o caminho de cura para a shortlist gravada por uma
versão anterior do matcher, que antes obrigava a apagar o arquivo pela mão.

**A primeira leitura grava a shortlist léxica; a híbrida exige o recálculo**
([F-041](../features/F-041-braco-semantico-hospedado/feature.md),
[ADR-0054](../adr/0054-indice-de-embeddings-publicado-e-braco-semantico-hospedado.md)). O
índice de embeddings passou a ser artefato publicado pela plataforma, e ler a shortlist
continua não custando nada — é o recálculo, que é gesto explícito, que embute os rótulos e
traz a vizinhança semântica. No orçamento-base isso vale **por tabela**: cada fonte da
cascata é fundida com o índice dela, os blocos continuam saindo na ordem que a orçamentista
instalou, e a tabela sem índice entra só pelo braço léxico — com a nota dizendo **qual**
ficou de fora, em vez de uma frase única sobre o braço estar indisponível.

Nada disso recusa o recálculo. Contrato de IA inativo, ambiente sem provider, índice
ausente ou índice recusado: em todos, a shortlist sai léxica com o motivo escrito e o ato se
completa. Tirar o recálculo inteiro por falta de um braço que é acréscimo levaria junto o
léxico, que não custa nada e é o que a orçamentista usa todo dia.

### A quantidade que vem da cena aprovada

A rodada declara — por ato humano, nunca por inferência — **qual croqui aprovado a
alimenta**
([ADR-0058](../adr/0058-quantitativo-derivado-do-scene-graph-e-identidade-de-elemento.md)).
O elo nunca é adivinhado por obra de mesmo nome, data próxima ou rótulo parecido, e a tela
mostra os três identificadores que ele cita — o croqui, a revisão da cena e o pacote
publicado — mais o digest do DXF auditado, para que a auditoria saiba **qual** desenho
alimentou a medição. A ausência de elo é DECLARADA: sem croqui declarado a jornada segue
exatamente como antes, com a quantidade vindo da legenda lida.

O confronto com o `quantitativos.csv` do pacote declarado é gesto explícito, com o efeito
escrito antes do clique: ele alimenta o item que está sem quantidade, grava divergência
onde os dois números discordam além da tolerância e deixa o resto intacto. O relatório volta
**item a item, para todos os itens** — inclusive os que não mudaram, com o motivo nomeado:
identidade ausente de um dos lados, cena `approximate` (que não alimenta a medição e por
isso também não compara), unidade que a cena não produz, grandeza ausente, divergência já
gravada ou concordância dentro da tolerância. Ausência na lista nunca responde por "a cena
não tinha esse número".

Quando não há par, a tela diz **de que lado** falta a identidade e qual é o próximo ato.
Ela nunca casa por número igual, por proximidade do balão, pela ordem das linhas nem por
rótulo parecido: dois `418,12` continuam sendo ausência de par, porque número igual não é
identidade — identidade é declarada.

No item alimentado pela cena **não existe campo de quantidade**. A origem ocupa o lugar do
`input` e mostra a identidade, a revisão da cena e a precisão declarada; "Editar quantidade"
fica desabilitado e **visível**, com a razão ao lado, para que a ausência seja lida como
decisão e não como falta. A redigitação era onde o erro entrava, e o jeito de eliminá-la é
não oferecer o teclado.

A **divergência** apresenta três blocos de peso igual — cena, legenda, diferença —, cada um
com a sua origem escrita, e a conta da tolerância por extenso (`maior entre 1% da quantidade
da legenda e 0,01 na unidade do item`). A diferença e a tolerância exibidas são as que o
servidor gravou e confere a cada leitura; a tela não refaz nenhuma conta. Enquanto a
divergência estiver aberta o item aparece **bloqueado** — por palavra e por forma, nunca só
por cor — e o formulário de decisão não é oferecido.

Resolver é escolher entre **duas** origens, cena ou legenda, com motivo obrigatório na tela.
"Nenhuma das duas" aparece indisponível, com a razão escrita: digitar uma terceira
quantidade ali seria a redigitação que a feature existe para eliminar; se as duas estão
erradas, o caminho é corrigir o croqui ou a leitura, cada um na sua jornada. A decisão fica
carimbada com autor e instante, e **o número preterido continua gravado** — resolver não é
sobrescrever, e quem abrir a memória de cálculo meses depois vê os dois números, a
diferença, a tolerância vigente e quem decidiu.

## O orçamento é assinado antes de sair

A planilha do orçamento deixou de nascer publicada. Montar e despachar são **atos
separados**, e entre os dois existe a assinatura
([F-035](../features/F-035-aprovacao-do-orcamento/feature.md),
[ADR-0046](../adr/0046-aprovacao-do-orcamento-base.md)).

**Quem orça não assina.** A assinatura é de um papel próprio — `aprovador` —, e o produto
recusa quando quem tenta assinar é quem montou, mesmo que a pessoa acumule os dois papéis:
a comparação é de identidade, não de papel. Sem isso o papel novo seria cerimônia. Despachar
a planilha já assinada, esse sim, é do orçamentista: assinar é assumir o conteúdo, despachar
é operar o envio.

**A assinatura vale para um conteúdo exato.** Ela é amarrada por digest ao orçamento como
ele estava no ato, e o digest é calculado **sem** a própria assinatura — assinar não muda o
que foi assinado. Remontar depois não apaga o que aconteceu: a assinatura fica **caduca**,
visível, com os dois digests lado a lado, e o despacho recusa até um ato novo. Descartá-la
apagaria em silêncio o fato de que alguém assinou.

**A tela mostra o ato com peso de ato**: dois passos explícitos, a identidade da sessão à
vista e nunca digitável — não existe campo de nome, porque quem aprova é quem entrou —, e a
consequência escrita antes do clique. O link da planilha só existe depois do despacho, e não
porque um arquivo passou a existir.

## De onde vem a tabela de preços

A cascata de fontes do orçamento é alimentada por **escolha**, não por arquivo
([F-037](../features/F-037-acervo-de-catalogos/feature.md),
[ADR-0047](../adr/0047-acervo-de-catalogos-da-plataforma.md)). A plataforma publica as
tabelas públicas de referência uma vez para todos os tenants, e a orçamentista escolhe de
uma lista que traz nome, origem, data-base e tamanho — é o que distingue duas linhas que,
sem isso, seriam ambas "SCO". Ela não precisa saber o que é um catálogo em JSON, nem obter
o arquivo, nem escolher a data-base certa entre versões que ninguém nomeou.

O **arquivo próprio continua existindo**, declarado como alternativa e dito para quem
serve: quem tem a EMOP licenciada — que é tabela paga e por isso a plataforma não distribui
— ou o catálogo específico de um contrato envia o arquivo pelo caminho de sempre. O que
mudou é que ele deixou de ser a primeira coisa que aparece.

A cascata **declara de onde cada fonte veio**: `DO ACERVO` ou `TABELA PRÓPRIA`, ao lado da
origem do preço. São coisas diferentes — origem é de onde o preço vem, procedência é quem
publicou o arquivo —, e uma proveniência que não as distinguisse mentiria sobre a primeira.
Quem publicou o arquivo **não muda o que o arquivo diz**: o orçamento montado sobre uma
tabela do acervo é linha a linha idêntico ao montado sobre o mesmo arquivo enviado pelo
cliente.

Sob regime de contrato licitado, a lista **já chega filtrada do servidor** pelo que o regime
aceita: oferecer uma tabela que a instalação vai recusar é oferecer uma recusa. A tela não
guarda cópia da regra — ela mostra o que recebeu.

Publicar é ato de plataforma, e cada publicação é imutável: data-base nova é **entrada
nova**, nunca substituição, porque sobrescrever mudaria preço para todos os tenants ao mesmo
tempo — inclusive em rodadas já montadas. Retirar uma tabela de circulação a tira das
escolhas novas e **não** apaga nada: a rodada que já a citou continua funcionando.

## Estados e ações

| Estado | Ação do usuário | Próximo estado |
|---|---|---|
| `UPLOADED` | Iniciar | `VALIDATING` |
| `PROCESSING` | Aguardar ou excluir | `REVIEW_REQUIRED`/`FAILED` |
| `REVIEW_REQUIRED` | Revisar, reanalisar, aprovar | `APPROVED` |
| `APPROVED` | Exportar | `EXPORTING` |
| `EXPORTING` | Aguardar | `COMPLETED`/`FAILED` |
| `COMPLETED` | Baixar ou excluir | `DELETING` opcional |
| `FAILED` | Ver causa, repetir etapa segura ou excluir | conforme etapa |

## Falhas UX

- Falha de Textract: continuar e informar redução de evidência OCR.
- Falha de um LLM: continuar sem confirmação automática.
- Falha dos dois LLMs: job falha com retry disponível.
- Geometria impossível: abrir revisão com constraints conflitantes.
- Export inválido: não disponibilizar arquivo; preservar revisão e diagnóstico.
- Expiração próxima: mostrar aviso e permitir export ou exclusão, não extensão no
  MVP.

## Acessibilidade

- Cor nunca é o único indicador; usar ícone e texto.
- Navegação por teclado nas listas e propriedades.
- Zoom não altera tamanho dos controles.
- Mensagens indicam problema, impacto e ação recuperável.

## Referências

- [PRD](PRD.md)
- [API Contract](../architecture/API_CONTRACT.md)
- [Human in the Loop](../ai/HUMAN_IN_THE_LOOP.md)
