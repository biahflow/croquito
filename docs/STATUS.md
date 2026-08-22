# Estado do produto (vista derivada)

Status: Active  
Responsável: Product / Engineering  
Última revisão: 2026-08-19 (F-012 documentada — operação SaaS da autorização de IA, ADR-0036
`Proposed`, implementação completa; F-009 documentada — suite hospedada de providers sem AWS,
ADR-0035 `Proposed`, implementação completa; medição migrada para a API `/v1`, F-003; F-006
concluída após os atos humanos de homologação; F-007 e F-008 abertas, com os ADR-0032 e
ADR-0033 aceitos)

> Esta é uma vista derivada de estado, riscos, evidências e atos humanos pendentes. O
> trabalho planejado tem fonte canônica no [Roadmap](product/ROADMAP.md); a convenção de
> lifecycle e evidências está no [Project Context](engineering/PROJECT_CONTEXT.md).

## Marco atual

Quarto marco local concluído em código. O ambiente Docker com LocalStack, PostgreSQL e
Keycloak OIDC está de pé, e a sessão autenticada agora percorre o caminho inteiro: carga
explícita do pacote autorizado, decisão de leitura, solver, calibração, aceite de
proposta, aprovação técnica formal e exportação auditada do DXF pelo worker.

Não há serviços AWS reais, IA paga ou upload de documento de cliente para terceiros.

O que falta neste marco **não é código**: são os atos humanos e a autorização de gasto,
listados em "Próximo marco". Nenhum deles é fabricado por fixture ou agente.

Em paralelo, o contexto de medição de obra percorreu os marcos M1 a M5 em código,
descritos em "Quinto marco: medição de obra (M1 a M5 em código)".

## Entregue neste marco

- Monorepo Python/TypeScript com `make setup`, `make dev`, `make check`,
  `make test` e `make demo`.
- Scene graph Pydantic com precisão, proveniência, medidas, constraints e issues.
- JSON Schema canônico e tipos TypeScript gerados, com drift check em CI.
- Guardrails que bloqueiam cena não aprovada, `unresolved`, aproximação sem aceite,
  issue crítica e medida confirmada incompatível.
- DXF R2018 em metros com layers, cotas, XDATA, reabertura, auditoria, render e ZIP.
- Fixture sintética e preview inspecionado visualmente.
- API FastAPI mínima para health, metadata e schema; processamento fora do request.
- Shell React/TypeScript com revisão, precisão e auditoria visíveis.
- Fundação Terraform AWS: S3 privado SSE-KMS, filas/DLQ, KMS e logs.
- Ingestão PyMuPDF com hash, render a 200 DPI, métricas e contact sheet.
- Sete PDFs locais ingeridos: 16 páginas esperadas e zero páginas vazias sugeridas.
- Propostas OpenCV de linhas, círculos e contornos, sempre em pixels e `unresolved`.
- Limites de candidatos registrados explicitamente quando atingidos.
- Overlay conservador separado do JSON bruto, com aviso de não exportação.
- Contact sheet de propostas para cada dataset e regressão nas 16 páginas.
- Eval sintética: recall de linhas/círculo e precisão de círculo em 100%, sem liberar
  nenhuma proposta para exportação. Isso valida a fixture, não precisão nos PDFs reais.
- CI inicial e testes Python/TypeScript.
- `ReviewPacket` com recorte, digest, texto bruto, valor, unidade e estado.
- Confirmação/rejeição válida somente com `HumanDecision` profissional rastreável.
- Solver retangular determinístico com resíduos, constraints e conflicts críticos.
- Rascunho solucionado continua bloqueado até `SceneApproval` ligado ao UUID exato.
- Aprovação cria nova revisão e entra no ZIP como `aprovacao.json`.
- Eval sintética ponta a ponta de revisão, solver, aprovação e DXF auditado.
- Guaxindiba preparado com duas cotas globais propostas e círculo ambíguo; o solver
  registra três blockers e não gera DXF real antes da revisão do domínio.
- Toca preparado com largura proposta, altura e associação ainda ambíguas; o solver
  bloqueia a cena retangular até confirmação.
- Raul Campelo preparado com propostas de pérgola e patamar; contorno orgânico e
  semântica de círculo permanecem em revisão.
- `apply-review` cria nova versão do review packet a partir de decisões por leitura,
  preserva a proposta de origem e impede sobrescrita de decisão já registrada.
- Associação determinística proposta→cota em pixels para os três casos, com até
  três alternativas por leitura e sem autoassociação, confirmação ou exportação.
- Ambiente local em Docker com PostgreSQL, LocalStack e Keycloak OIDC iniciado e
  validado. O bootstrap cria bucket, filas, DLQ, secret e state machine locais.
- API persiste upload/job tenant-scoped com idempotência; worker local consome SQS
  e muda o job para `REVIEW_REQUIRED` sem executar IA ou exportação; a persistência
  do pacote de revisão é feita pelo estágio de evidências autorizado.
- Upload autenticado fecha o PUT direto ao storage com checksum assinado,
  verificação remota antes do job e validação local do PDF antes da revisão stub.
- Sessão autenticada de revisão persiste snapshots imutáveis de pacote, evidência,
  associações e referências privadas de preview por job/tenant. Decisões por
  leitura usam controle otimista, idempotência e identidade/papel derivados do
  JWT; nenhuma decisão ou URL assinada é registrada em logs.
- O shell web não contém mais casos ou decisões simuladas: abre somente uma
  revisão autenticada, mostra imagem/overlay sincronizados e mantém DXF bloqueado
  enquanto os blockers críticos estiverem presentes.
- Editor autenticado de propostas CV: profissional calibra pixels contra duas
  linhas métricas confirmadas e aceita linha, círculo ou contorno somente como
  entidade `approximate` rastreável; rejeições permanecem auditáveis e nada é
  promovido a `exact` ou exportado sem aprovação.
- O solver retangular exige associação explícita além da confirmação humana e
  propaga essa associação na provenance. Rascunhos parciais do Guaxindiba recebem
  blockers críticos de critérios ainda não cobertos e não são exportáveis.
- Contratos estruturados offline para OpenAI, Bedrock/Claude, Textract e todos os
  prompts MVP, com mocks determinísticos, fault injection e lineage por leitura.
  O worker só usa essas fixtures por injeção explícita em teste/demo; uploads
  normais não chamam providers nem recebem observações fabricadas.
- Adapters reais locais para OpenAI, Bedrock/Claude e Textract, com schemas
  estritos, retries transitórios, lineage, respostas brutas privadas e autorização
  contratual imutável por job. Permanecem desligados por padrão e não foram chamados neste
  repositório; o piloto limita explicitamente a análise à primeira página. O braço `ocr` da
  suite hospedada ganhou depois um segundo adapter real, Document AI, montável no lugar do
  Cloud Vision por `CROQUITO_DOCAI_PROCESSOR`
  ([ADR-0037](adr/0037-document-ai-como-braco-de-ocr.md), que revisa D3 do
  [ADR-0035](adr/0035-suite-hospedada-openai-anthropic-direto.md)); nenhum processador está
  provisionado até esta revisão, e a suite segue montando Cloud Vision por padrão.
- A tela autenticada lista projetos do tenant, abre revisões sem exigir UUID e não
  expõe aceite de IA por job. O entitlement contratual é administrado somente por
  `platform_operator`, registrado por tenant e revalidado pelo worker.
- `croquito-demo seed-review` liga um pacote de revisão autorizado a um job existente
  sem copiar o original para o Git e sem chamar provedor. Recusa fechada quando o job não
  é do tenant, quando o digest do documento ou da página diverge do upload, quando o
  pacote já traz decisão humana, quando uma leitura do solver não tem candidato de
  associação e quando já existe revisão para o job — nunca sobrescreve evidência.
- O worker deixou de inserir cena stub vazia. A primeira cena métrica nasce do solver, na
  sessão autenticada, a partir de leituras confirmadas com associação explícita.
- Entidades `approximate` aceitas por um profissional passaram a sobreviver às decisões
  de leitura seguintes. A calibração é revalidada contra a nova cena; se ela deixar de
  valer, a geometria aceita **não** é reprojetada nem descartada: a cena recebe a issue
  crítica `CALIBRATION_SUPERSEDED` e o export fica bloqueado até nova calibração.
- Aprovação técnica alinhada ao contrato `SceneApproval`: três verificações explícitas,
  declaração de 20 a 500 caracteres, identidade e horário derivados do servidor,
  idempotência real e `approval_json` persistido no mesmo formato do `aprovacao.json`.
- Declaração nominal por critério de escopo na aprovação, restrita aos códigos declarados
  no caso e com dois desfechos distintos: coberto pela cena (issue `resolved`) ou
  reconhecido como pendente (issue `accepted`). Os dois conjuntos viajam separados no
  `aprovacao.json`, o texto do critério acompanha o código desde a semeadura e a cena
  traçada materializa a issue igual à do solver retangular — sem declaração, o export
  continua bloqueado. Blockers de geometria continuam indispensáveis
  ([ADR-0017](adr/0017-per-criterion-coverage-declaration-and-trace-parity.md)).
- Export DXF pela sessão autenticada: a API só enfileira comando idempotente, o worker
  gera, reabre, audita, renderiza e só então publica o ZIP no storage privado. Falha de
  auditoria não publica nada; replay não republica; falha transitória volta para a fila.
- Registro `export_artifacts` tenant-scoped com chave do pacote, digest, auditoria e um
  artefato por revisão aprovada. Download apenas por URL assinada de curta duração.
- Tela de aprovação e exportação: verificações nunca pré-marcadas, motivos de bloqueio
  sempre visíveis, acompanhamento do export e download do pacote auditado.
- Correção declarada de decisão de leitura: um erro de transcrição deixou de custar o job
  inteiro. `POST /v1/jobs/{id}/review/rectifications` registra um ato humano NOVO — nova
  `HumanDecision` com `rectifies_decision_id` apontando a anterior, em revisão de leitura
  nova — sem editar nada: a decisão errada continua legível na revisão em que foi tomada,
  a leitura nunca volta a proposta e a associação é sempre redeclarada. A cascata é
  invalidar para frente: quando a cena mais recente ainda se apoia na decisão corrigida,
  nasce uma cena nova **não aprovada** com a geometria intacta e a issue crítica
  `READING_DECISION_SUPERSEDED`, que bloqueia o export até o traçado daquela parte ser
  refeito — aprovações e pacotes já publicados não são tocados. O comando de decisão passa
  a recusar redecisão com `READING_ALREADY_DECIDED`, apontando a correção. Motivado pelo
  custo real do Guaxindiba v1→v2 (13 leituras com o eixo trocado)
  ([ADR-0022](adr/0022-declared-rectification-of-review-decisions.md)).
- Conversa sobre a folha (fatia 1, 100% offline): sessão e turnos de chat na tela de
  revisão, respondidos pelo worker via tarefa `review-chat@1.0.0` (primeira tarefa
  imagem+texto) servida por fixture determinística — nenhuma chamada paga. A resposta é
  observação com rascunhos tipados dos atos existentes (decisão, associação, vão,
  manter-separados, nota, pendência); "ainda não sei" é saída de primeira classe; o
  botão da tela só pré-preenche o formulário de sempre e a submissão continua humana.
  Rascunho que cita id fora da revisão-base derruba o turno inteiro
  (`CHAT_ACT_UNKNOWN_REFERENCE`). Conteúdo da conversa vive no banco, nunca em log
  ([ADR-0023](adr/0023-review-chat-as-an-observational-agent.md)). A fatia 2 (provider
  real atrás de entitlement, com ok de gasto na hora e teto por sessão) é rodada futura.
- Teste fim a fim automatizado da cadeia inteira, do upload autenticado ao ZIP auditado,
  incluindo o envelope real publicado na fila — o único ponto que os testes por camada
  não cobriam.
- Dublês de storage e fila unificados: o storage guarda bytes por chave e deriva o
  checksum do que foi gravado, de modo que a verificação de upload não possa divergir
  entre API e worker dentro de uma fixture.
- SQLite passa a aplicar chaves estrangeiras nos testes (`PRAGMA foreign_keys=ON`).
  Isso expôs dois defeitos que só apareciam em PostgreSQL e agora estão corrigidos:
  a ordem de inserção de pai e filho no mesmo flush (job criado antes do projeto) e o
  uso de `authorization` como alias em SQL cru, que é palavra reservada.
- `make smoke-local`: smoke sintético contra o stack Docker real, cobrindo presign
  assinado, `head_object`, SQS, PostgreSQL e publicação do pacote no object store.
- Traçado em lote como estágio real do worker (`solve-trace`/`trace-export`): o grafo de
  junções, a regularização ortogonal e o solver de cotas resolvem a cena em metros com a
  cota confirmada mandando sobre o pixel; o eixo Y é espelhado de imagem para CAD e a
  precisão é declarada por entidade — `exact` somente quando toda distância interna vem
  de cota confirmada, o resto permanece `approximate` na layer `APROXIMADO` com aceite
  em lote identificado. O export ganhou cotas DIMENSION proporcionais à cena com texto
  sempre legível e empilhamento em faixas quando cotas do mesmo lado colidem, hachura
  declarada por aceite humano, carimbo com título, unidade, origem e hipóteses, e preview
  com folha e DPI proporcionais à extensão. Os nomes de elementos deixaram de cobrir o
  desenho: todo elemento rotulado vira balão numerado junto a ele, com legenda em coluna
  à direita da prancha e desvio de colisão que respeita texto de cota e carimbo (o nome
  inline dentro da região, tentado primeiro, foi aposentado em 2026-08-13 por
  inconsistência numa prancha real). Anotações confirmadas (alturas `h=…`, especificação de portão,
  traves, tela aérea) viram texto `exact` preso ao elemento, e cota de vão entre dois
  elementos (associação explícita a um par de propostas) entra no solver como restrição e
  é desenhada na posição da evidência — o 6,60 do Guaxindiba fecha com a cadeia
  19,75 + 8,60 − 21,75 e qualquer divergência viraria resíduo bloqueante. O revisor pode
  declarar que dois elementos desenhados coincidentes são distintos (`keep_apart` na
  topologia e nas faixas da regularização, registrado no aceite): foi o que resolveu o
  lado direito do Guaxindiba, onde
  a borda do patamar e a mureta estão uma sobre a outra na folha mas as cotas 4,80 e 3,30
  as separam — aplicadas sem a declaração, o solver acusou o conflito e bloqueou o export,
  como deve. A demonstração
  local do Guaxindiba reproduz as cotas da folha (campo 25,90 × 21,75; patamar 14,50;
  trechos 9,55/3,86/12,49; mureta 3,30 × 8,60) com orientação correta — os defeitos da
  iteração de 2026-08-10 (patamar 6,47, cena espelhada) viraram testes de regressão.
- O estágio de traçado ganhou documento canônico
  ([Trace Stage](architecture/TRACE_STAGE.md)) com os controles do revisor e as
  convenções de prancha, e foi validado num segundo caso dourado sem nenhuma mudança de
  código: a Toca saiu com campo 55,00 × 84,0 exato, cota e nota de portão, a partir de
  três decisões e quatro propostas OpenCV. O delta visual contra o Guaxindiba (traçado
  completo via extração) quantifica o valor da extração paga, que permanece desligada.

- Primeira eval paga comparativa executada com autorização explícita de gasto
  (2026-08-11): extração de geometria na Toca, Opus × Sonnet pela API direta da
  Anthropic, custo real ≈ US$ 0,45 contra teto autorizado de US$ 1,50. Opus corrobora
  0,96 após registro e vira o modelo de extração; Sonnet reprova (0,57) mesmo
  registrado. Resultado e rollback em [Model Routing](ai/MODEL_ROUTING.md).
- O lineage passou a distinguir a API direta da Anthropic (`anthropic`) do Bedrock
  (`bedrock_anthropic`); relatórios anteriores à distinção estão anotados no documento
  de roteamento. O parser de provider ganhou o repair estritamente estrutural previsto
  na política (envelope de chave única) e polyline aberta de 2 vértices normaliza para
  `line` — ambos com testes.
- O registro fino das propostas VLM contra a tinta virou comando idempotente
  (`register-extraction`): roda sobre os artefatos já pagos da eval, sem nova chamada
  externa, reescreve o relatório com o antes/depois auditável e grava
  `{arm}-registered.json`. O refino por elemento desse registro **nunca inverte a ordem
  traçada entre elementos**: os elementos são assentados por cobertura decrescente, cada um
  dentro de um corredor fechado pelas tangentes já assentadas, e tanto o empurrão quanto a
  escolha entre colocação bruta e pós-global passam por ele — era o conjunto misturado que
  fazia a aresta do campo pousar na tinta do muro vizinho e o muro na linha do campo, com
  cobertura alta e DXF espelhado ([Vision Proposals](ai/VISION_PROPOSALS.md)).
- O mesmo refino passou a corrigir **tamanho**, e não só assentamento: contorno fechado de
  quatro arestas quase-ortogonais ganha um deslocamento perpendicular por aresta, com
  nunca-piora por aresta, a lei da ordem aplicada aresta a aresta, cantos por interseção
  (direções preservadas), janela proporcional à extensão perpendicular com teto próprio de 5%
  da página e piso que impede achatar o elemento. O defeito que motivou: o VLM entregou o
  campo do Guaxindiba 1,28x mais alto que a tinta, e empurrão rígido só trocava qual aresta
  ficava errada — a base ficava 254 px longe do topo dos patamares e o encontro desenhado que
  amarra o traçado não existia. Medido na cópia dos artefatos pagos, sem nova chamada externa:
  encontro campo↔patamar de 254 px para no máximo 61 px (limite de fusão 67 px), cobertura do
  conjunto 0,873 → 0,936, `corroborated_rate` 0,95 → 1,00, nenhuma das 20 propostas abaixo da
  colocação bruta e nenhuma `order_unresolved`. Limitação declarada no documento: aresta que a
  folha não desenha adota a paralela mais próxima da janela, porque a lei da ordem só protege
  contra tinta de elemento já assentado ([Vision Proposals](ai/VISION_PROPOSALS.md)).
- A mesma lei chegou às **linhas**, pela extensão: depois do empurrão, cada ponta desliza ao
  longo da própria direção maximizando comprimento útil (tinta coberta menos comprimento sem
  tinta), com a cobertura e a ordem nunca piorando e o mesmo piso de extensão. Encolher tem
  parada natural — a tinta acaba; esticar só é permitido quando a tinta acaba dentro da
  janela, senão a ponta fica, porque um traço que continua não diz onde a linha termina. O
  defeito que motivou: a linha de meio de campo do Guaxindiba saiu 479 px mais comprida que o
  traço, com a ponta de cima pousada no toco da cota "6,60"; a ponta órfã impedia o encosto
  com as arestas do campo e o 21,75 flutuava no solve. Medido na cópia dos artefatos pagos:
  as duas pontas passaram a ficar a 34 px e 15 px das arestas do campo (limite de encosto
  67 px), cobertura do conjunto 0,936 → 0,943, `corroborated_rate` 1,00 mantida, nenhuma das
  20 propostas abaixo da bruta. A regra da assimetria é o que impede o portão de 3,10 m,
  desenhado sobre a linha do muro, de crescer 35% engolindo a tinta do muro
  ([Vision Proposals](ai/VISION_PROPOSALS.md)).
- O deslize de ponta passou a exigir **trecho contínuo próprio**: traço cruzante tem tinta e
  não é fim de linha. Com o halo, o risco do muro e a linha que ele cruza são uma mancha só, e
  a ponta parava na borda dela — no Guaxindiba, 44 px acima da própria tinta, mais perto da
  faixa do muro (2123,3) que da do campo (2130,1); o traçado amarrava o 21,75 na faixa errada e
  a cadeia estourava em três resíduos de 2,20 m. A parada agora exige duas tolerâncias de tinta
  ao longo da direção da linha, medidas numa máscara direcional, e a janela é estendida até a
  correção mínima quando nenhuma parada honesta cabe nela — o teto limita a procura, não a
  correção, como já valia para o corredor da ordem. Medido na cópia dos artefatos pagos, sem
  nova chamada externa: a ponta de cima foi de y=2096 (folha em branco) para y=2149 (o começo do
  traço), o traçado do caso real fechou **sem nenhum resíduo** — 21,75 em 21,749997 — contra
  três reprovações antes, `corroborated_rate` 1,00 e cobertura do conjunto 0,943 mantidas e
  nenhuma das 20 propostas abaixo da bruta. O preço declarado é um resíduo para dentro da linha,
  da ordem da tolerância ([Vision Proposals](ai/VISION_PROPOSALS.md)).
- Grupos de detalhe no traçado (`TraceAcceptance.detail_groups`): painéis e
  arquibancadas desenhados fora de escala ao lado da planta agora entram na prancha
  como detalhes independentes — modo `solve` com as cotas do grupo mandando em escala
  própria, ou `sketch` (isométricos) sem escala e fora dos quantitativos — com moldura,
  título, coluna própria entre planta e legenda e tipografia da planta preservada nos
  dois lados (traçado e export). Atende o ACC-TOC-002; controles e blockers no
  [Trace Stage](architecture/TRACE_STAGE.md).
- Raul Campelo extraído e traçado via VLM (`output/dxf-raul-vlm/`, demo local, arm
  único Opus autorizado, ≈ US$ 0,14): corroboração 0,28 → 0,78 após registro, contorno
  orgânico da praça preservado pela regularização, parquinho 19,90/10,0/14,35 e gazebo
  4,30 × 4,30 cotados. O achado de motor daquela rodada — o traçado não aplicava cota de
  **diâmetro** em círculo (9,60 e 5,04 ficaram como notas presas) — está fechado: leitura
  confirmada de raio ou diâmetro com associação simples a um círculo aceito determina o
  raio, o círculo sai `exact` com medida confirmada amarrada e a cota diametral (⌀) é
  desenhada no ângulo da evidência; sem leitura o círculo permanece `approximate`, e duas
  leituras que discordam bloqueiam com `TRACE_CIRCLE_READINGS_CONFLICT`
  ([Trace Stage](architecture/TRACE_STAGE.md)).
- O aceite em lote do traçado deixou de ser exclusivo da CLI: a sessão autenticada posta o
  aceite em `POST /v1/jobs/{id}/trace-solves` e acompanha o resultado por polling. A API
  valida versões-base, propostas citadas e a consistência do aceite, deriva revisor,
  horário e `acceptance_id` do servidor e enfileira; o worker resolve com claim atômico e,
  quando o traçado fecha, grava a cena métrica não aprovada mais a revisão de leitura que
  registra o ato. Revisão que andou entre o aceite e a execução vira `conflict`
  consultável com `REVISION_MOVED`, não erro de servidor, e replay não cria segunda cena
  ([ADR-0015](adr/0015-trace-solve-worker-and-registry.md)). A tela monta esse aceite
  sobre a seleção múltipla que já existia: hachura, dispensa de legenda, elemento como
  desenhado, grupos de detalhe com escala declarada e pares a manter separados, com
  pré-validação e pendências em língua de obra. Traçado resolvido recarrega revisão e
  cena e limpa a montagem; conflito recarrega e preserva a montagem para reenvio.
- Traçado completo da Toca via extração VLM (`output/dxf-toca-vlm/`, demo local):
  campo 55,00 × 84,0 exato, faixa de grama hachurada, vão de 0,48 com `keep_apart`,
  traves 7,30, notas nas posições da folha e carimbo com a síntese dos detalhes.
  Pendências declaradas ao projetista em vez de adivinhadas: 56,00 da base da faixa
  (trapézio abaixo da tolerância de banda), 12,00 da faixa esquerda e o trio
  1,55/4,2/1,65 do limite do lote ficaram como notas, não restrições.
- Série de aceitação real do braço de OCR e do funil (Guaxindiba, 2026-08-20, mesma
  folha em quatro uploads): V14 10 leituras/2 de chão; V15 6/0 (expôs o limite do
  Cloud Vision em manuscrito); V16 8/0 no pacote MAS 27/13 na extração — o raw-store
  revelou o funil descartando leitura sem `target_hint`
  ([F-024](features/F-024-leitura-sem-target-hint/feature.md)); V17, já com Document
  AI ([ADR-0037](adr/0037-document-ai-como-braco-de-ocr.md), processador em
  `biahflow/infra` PR #17) e o funil consertado, extraiu 29 leituras (13 de chão,
  2 `note` do modelo — o sinal da
  [F-021](features/F-021-nota-pre-classificada/feature.md) em produção). Lição de
  método: cada rodada expôs um gargalo diferente (eixo, OCR, funil) e nenhum era
  erro de leitura do modelo — insumo direto da F-023 (Survey Quality Score). O eval
  comparativo pago Vision×DocAI segue como gate declarado do ADR-0037.
- Fatia 1 da F-023 (Survey Quality Score) executada em 2026-08-20, na mesma
  sessão que a especificou: o motor de fechamento de cadeias de cotas
  (`dimension_closure.py`), completo e testado desde a criação mas órfão, ganhou
  chamadores — `suggested_chains` (somas que fecham, calculadas a cada leitura)
  e `declared_chains` (declaração humana persistida com autoria, reconferida
  contra o pacote corrente: `closes`/`mismatch`/`stale`) na resposta de review,
  rota `POST /v1/jobs/{id}/review/chains` (declare/retract), migração aditiva
  0006, CLI `check-chains` e a seção "Somas de cotas" na tela com o badge
  "Σ fecha". Desencontro de cadeia é WARNING e nunca blocker; nada toca o portão
  de export. Pendem migração no hosted, deploy e aceitação real
  ([F-023](features/F-023-survey-quality-score/feature.md)); o score agregado
  com recomendações de campo é a fatia 2, calibrada com V14–V17 — em
  2026-08-21 o score calibrado migrou por decisão humana para a
  [F-029](features/F-029-auto-associacao-confianca/feature.md)
  (auto-associação de cotas por confiança calibrada, experimento local), e as
  recomendações de campo seguem como fatia futura da F-023.
- F-029 executada por inteiro em 2026-08-21, na mesma sessão que a especificou
  (T1–T5, cada task revisada linha a linha, portões verdes): duas confianças
  determinísticas por cota (`reading_confidence` × `association_confidence`,
  pesos versionados — score `1.0.0`), shadow log persistido em toda revisão
  (migração 0007) com o que cada ponto de uma grade 6×6 de cortes TERIA
  auto-decidido, métricas observacionais na resposta de review, eval com gate
  (`make association-eval`) e relatório local de calibração
  (`make association-calibration`, verdade = decisão humana vigente medida
  contra o shadow PRÉ-decisão), e o modo automático do
  [ADR-0041](adr/0041-decisao-de-ator-maquina-atras-de-flag-local.md)
  (Accepted): atrás de dupla chave local (`CROQUITO_AUTO_ASSOCIATION_ENABLED`
  + threshold explícito sem default), decisão de ator-máquina que só
  confirma, nunca sobrescreve e é retificável pelo caminho declarado; toda
  cota automática sai nominalmente na auditoria do export, e a tela de
  revisão ganha a vista de exceções (contadores + filtro que nunca esconde
  pendência nem bloqueio). Flag desligada = comportamento idêntico ao
  anterior, coberto por teste. Pendem os atos humanos: rodada local com a
  flag ligada, calibração com os sete levantamentos reais e a escolha do
  threshold ([F-029](features/F-029-auto-associacao-confianca/feature.md)).
- Primeira revisão real em nuvem processada de ponta a ponta (Guaxindiba V3,
  2026-08-19) e primeiro ciclo completo de eval-promoção de prompt motivado por
  defeito real, não por rodada de rotina: o muro com recuo 4,80→3,30 veio fragmentado
  em duas `line` retas sob `geometry-extraction@2.0.1`; o candidato `2.0.2` instrui o
  degrau a virar vértices de uma única polyline, o gate de fidelidade do degrau
  (`assess_step_fidelity`) e a fixture dedicada nasceram no mesmo ciclo, e a rodada
  paga comparativa aprovou e promoveu o candidato — resultado e protocolo completos em
  [Model Routing](ai/MODEL_ROUTING.md). A investigação também expôs dois achados fora
  do escopo do prompt, registrados como candidatos a trabalho futuro em
  [Roadmap](product/ROADMAP.md) (F-018, F-019): a revisora não tem como corrigir
  vértice ou recuo direto na tela, e leitura confirmada não aplicada gera issue apenas
  `warning` — a cena permanece exportável com entidade `exact` contradita.

Os renders, manifests com hashes e documentos permanecem somente em `output/`,
que é ignorado pelo Git e deve respeitar retenção local de sete dias.

## Quinto marco: medição de obra (M1 a M5 em código)

O contexto delimitado `valuation` nasceu com o trecho final da cadeia de medição, sem IA,
sem PDF e sem consolidação multi-obra
([ADR-0016](adr/0016-valuation-bounded-context.md),
[Valuation Context](architecture/VALUATION_CONTEXT.md)).

- `packages/valuation` com modelos canônicos de medição (boletim, linha, memória de
  cálculo, bloco, catálogo de preços), template de planilha como dado, importador do
  catálogo SCO, escritor das abas BM e MEMÓRIA e auditoria de round-trip.
- Dinheiro trunca em duas casas em `Decimal` e `float` é recusado na fronteira dos
  modelos. O par 1,15 × 10,30 fecha em 11,84 no golden versionado — arredondar daria
  11,85.
- Toda pasta gerada é reaberta e recomputada por um avaliador de gramática fechada
  (quatro formas no M1, seis desde o M2); fórmula fora da gramática é recusada e
  divergência de centavo não publica.
- Total cujo produto em ponto flutuante divergiria do cálculo exato é gravado literal e
  declarado em `pinned_cells` — critério conservador, registrado no `audit.json`.
- O M1 entregou `make valuation-demo` gerando `medicao.xlsx`, `valuation.json` e
  `audit.json` de uma obra, a partir de um mini-MAPÃO sintético de 30 itens (variantes
  `(A)`/`(B)`, aba de preços oculta, unidades escritas de formas diferentes). O canônico
  é determinístico e continua versionado como golden em `tests/valuation/golden/`; o
  comando em si passou a percorrer a cadeia do M2, descrita abaixo.

### M2 em código: consolidado, saldo e portão de aprovação

O M2 fechou as duas pontas do trecho entregue no M1
([ADR-0018](adr/0018-valuation-consolidation-and-balance-semantics.md)).

- `import-workbook` lê catálogo **e** consolidado contratual do mesmo arquivo do cliente,
  sem escrever no original, e falha fechado: acumulado que não fecha com os períodos,
  saldo que não fecha com vigente menos acumulado, RE-RA que não explica a quantidade
  vigente e vigente divergindo entre a PLANILHA GERAL e a aba da prefeitura
  (`GENERAL_AMENDED_DIVERGENT`) recusam a importação sem deixar artefato pela metade.
- A pasta gerada passou a abrir pela PLANILHA GERAL consolidando todas as obras da
  medição, com os pares históricos copiados literais, o par corrente calculado, acumulado
  e saldo como fórmulas vivas — e a GERAL gerada é reimportável como consolidado da
  medição seguinte. A aba de RE-RA é carregada adiante; o v1 lê revisão, não a cria.
- `export-valuation` só publica atrás do portão de aprovação e saldo: sem aprovação
  nominal amarrada por digest, fora da sequência de períodos, com código fora do contrato
  ou com quantidade acima do saldo, nenhuma planilha é gravada. Auditoria divergente
  também não publica: a pasta é gravada com nome temporário e removida.
- A gramática fechada de fórmulas passou de quatro para seis formas, para o acumulado de
  células alternadas (`=SUM(<ref>,<ref>,...)`) e para o saldo (`=<ref>-<ref>`).
- `make valuation-parity PREVIOUS=<caminho.xlsx>` é diagnóstico local, nunca CI: confere
  fórmula contra valor em cache de uma pasta que o sistema não gerou, classifica `VLOOKUP`,
  `IF` e referência externa em vez de adivinhá-las, e não recusa nem publica nada.
- O golden do M1 continua intocado e um golden novo
  (`tests/valuation/golden/valuation-demo-m2.canonical.json`) fixa a pasta consolidada de
  três obras que `make valuation-demo` passou a gerar.

### M2.1 em código: o layout real como dado e o dossiê da divergência

A primeira leitura do MAPÃO real (2026-08-12) mapeou lacunas de layout e uma pergunta de
domínio. As lacunas foram fechadas como **dado**, sem exceção no código; a pergunta virou
artefato de conversa, não mecanismo de aceite.

- O template passou a declarar o que variava por cliente: hierarquia do catálogo em
  colunas próprias (família e nível intermediário), escala decimal da quantidade, ausência
  da coluna de vigente na GERAL — sem ela o vigente é derivado do contratual mais as RE-RA
  do código, e a derivação é declarada em cada achado —, a nota editorial intercalada entre
  os cabeçalhos do catálogo e o marcador de item sem cotação publicada (que fica fora do
  catálogo, sem virar preço zero).
- O número da medição é lido do rótulo (`11ª MEDIÇÃO - COMPLEMENTAR` é a 11ª) e o salto de
  numeração é dado, não erro; `period_numbers`, `period_gaps`, linhas separadoras puladas e
  células normalizadas pelo ruído de cache vão para o bloco `notes` do `import-report.json`.
- A chave do consolidado passou a ser o par grupo+código, porque o contrato real repete o
  mesmo código SCO em grupos diferentes; código ambíguo citado pela aba da prefeitura
  recusa em vez de escolher a linha.
- Recusa semântica deixou de ser a primeira violação e passou a ser o mapa inteiro:
  `CONTRACT_SEMANTICS_DIVERGENT` grava `import-diagnosis.json` com todas as divergências
  recomputadas do histórico já publicado, cada uma com o código estável do modelo, a célula
  exata e os dois números. Falha de layout continua recusando sem dossiê, e nenhuma recusa
  publica catálogo, consolidado ou relatório.
- O dossiê **não** aceita nada: continua não existindo mecanismo de aceite de divergência.
  Ele é o instrumento da conversa pendente com o orçamentista sobre qual número o erário
  reconhece ([ADR-0018](adr/0018-valuation-consolidation-and-balance-semantics.md)).
- **Fase D: código contratual extra como dado + linhas de seção da prefeitura.** As duas
  lacunas de domínio da rodada anterior fecharam como dado, sem exceção no código.
  `sco.py` ganhou o superset estrutural `CONTRACT_CODE_PATTERN` (código SCO completo ou a
  forma nua de dez caracteres, sem variante — `IE00040849`) e `is_contract_code`; o
  `WorkbookTemplate` declara `extra_code_patterns` por cliente e `matches_extra_code`, com
  validação própria (`TEMPLATE_EXTRA_CODE_PATTERN_INVALID` recusa regex inválida ou padrão
  frouxo demais). `BulletinLine.code`, `ContractLine.code` e `AmendmentLine.code` passaram
  a aceitar esse superset — o catálogo (`PriceCatalogEntry.code`) continua estrito SCO. O
  leitor da GERAL e da aba da prefeitura só aceita código nu quando o template o declara **e**
  revalida contra o superset estrutural de qualquer forma (cinto e suspensório); a linha e o
  código aceitos por padrão extra vão para `extra_code_rows`. A aba da prefeitura ganhou o
  segundo tratamento: linha cujo código não é aceito e cujos blocos de RE-RA não carregam
  nenhum valor é pulada como layout e contada em `amendment_section_rows`, com o subtotal
  de grupo ignorado quando havia um. Uma segunda rodada de aceite revelou que a linha que
  abre um grupo às vezes carrega esse subtotal na própria coluna de vigente — a mesma
  coluna que o resto da aba usa de verdade para reconciliar o vigente por código —, e o
  achado virou opt-in do template em vez de presunção do código:
  `AmendmentLayout.section_rows_carry_group_subtotal` (`False` por padrão) tira só essa
  coluna do cheque de "linha sem valor" quando ligada; os blocos de RE-RA continuam
  obrigatoriamente vazios em qualquer cenário, e o subtotal ignorado nunca desaparece em
  silêncio — vai para as notas com a linha e o valor.
- Terceira rodada de aceite local do MAPÃO real (2026-08-12, Fase D), com os dois códigos
  `IE00040849`/`IE00040850` e `section_rows_carry_group_subtotal: true` declarados no
  template: **zero falha de layout** pela primeira vez. Catálogo lido inteiro (4.965
  itens), GERAL com 878 linhas (15 medições com buraco na 14ª, 77 separadoras, 420 células
  normalizadas) e a aba da prefeitura inteira (4 linhas de seção — uma delas com o subtotal
  de grupo `171025043,0100` registrado e ignorado, as outras três sem nenhum valor) chegam
  ao portão semântico. A importação recusa `CONTRACT_SEMANTICS_DIVERGENT` com
  `import-diagnosis.json` gravado (1,3 MB, local, fora do Git): **3.086 achados em dez
  classes** — `CONTRACT_BALANCE_MISMATCH` 838, `CONTRACT_BALANCE_NEGATIVE` 548,
  `AMENDMENT_NEGATIVE_RESULT` 524, `CODE_AMBIGUOUS_IN_CONTRACT` 347,
  `CONTRACT_ACCUMULATED_MISMATCH` 379, `AMENDMENT_DUPLICATE_CODE` 312,
  `GENERAL_AMENDED_DIVERGENT` 102, `AMENDMENT_NEW_ITEM_INVALID` 28,
  `PERIOD_AMOUNT_MISMATCH` 7, `CONTRACT_DUPLICATE_ITEM` 1. É esse dossiê — agora completo,
  sem lacuna de layout escondendo achado — que instrui a conversa pendente com o
  orçamentista sobre qual número o erário reconhece
  ([ADR-0018](adr/0018-valuation-consolidation-and-balance-semantics.md)).

Atos humanos ainda pendentes neste contexto, não fabricáveis por agente:

- Aprovação nominal de orçamentista sobre uma medição real. **Pendente.**
- Confirmação, com o orçamentista responsável, da semântica de consolidação e saldo depois
  de RE-RA — em especial qual valor a prefeitura reconhece quando o mesmo código medido em
  mais de uma obra deriva um centavo entre `TRUNC(Σq × preço)` e `Σ TRUNC(qᵢ × preço)`. Até
  lá o escritor recusa (`GENERAL_CONSOLIDATION_MISMATCH`) em vez de escolher
  ([ADR-0018](adr/0018-valuation-consolidation-and-balance-semantics.md)). **Pendente.**
- Primeira importação do MAPÃO real: verificação local, fora do CI, com o arquivo do
  cliente fora do repositório. **Rodadas executadas em 2026-08-12.** Na primeira, o
  `import-workbook` recusou fechado com diagnóstico exato e mapeou as lacunas de layout;
  todas elas foram fechadas como dado na segunda rodada (hierarquia do catálogo em colunas
  próprias, rótulo de medição com sufixo, salto de numeração, quantidade com quatro casas,
  ruído de float no cache, linha separadora zerada, código repetido entre grupos, nota
  editorial do catálogo e item sem cotação). O catálogo real passou a ser lido inteiro
  (4.965 itens, 23 famílias, 640 subgrupos) e a GERAL também — 15 medições lançadas com
  buraco na 14ª, 77 linhas separadoras e 359 células de ruído absorvidas.
  **Duas classes bloquearam a importação nessa rodada e eram decisão de domínio, não de
  layout** — registradas aqui em vez de resolvidas em silêncio: (1) o contrato traz itens
  fora da tabela SCO (código `IE########`, sem variante, ausente do catálogo publicado),
  que o padrão de código do contexto ainda recusava; (2) a aba da prefeitura tem linhas de
  seção cujo nome ocupa a coluna de código. Rodando o diagnóstico sobre a GERAL com esses
  códigos aceitos — sonda local, fora do repositório —, o dossiê ficou em 403 achados:
  379 acumulados que não fecham, 12 saldos negativos (inclusive os dois já vistos na
  paridade), 7 valores de período fora de `TRUNC(q × preço)`, 4 saldos que não fecham e 1
  item repetido. As duas classes fecharam como dado na Fase D — mecanismo e o resultado da
  terceira rodada, com zero falha de layout e o dossiê completo (3.086 achados), estão no
  bloco "Fase D" acima. O `parity` varreu as 52 abas em segundos, verificou as fórmulas da
  gramática contra o cache e listou divergências reais de um centavo do arquivo do
  cliente — todas da classe `TRUNC` em ponto flutuante que a célula fixada do M1 existe
  para impedir. Relatórios locais em `output/`, fora do Git.
- Decisão de domínio sobre o item fora da tabela SCO (`IE########`): **fechada como dado na
  Fase D.** O contrato real o contrata e mede, o catálogo publicado não o precifica; o
  template agora declara `extra_code_patterns` por cliente e o leitor revalida cada código
  aceito contra o superset estrutural, nunca alargando a identidade do item em silêncio. O
  que continua fora de escopo — não implementado por esta fase — é o caminho de escrita: um
  boletim que meça um código nu num período futuro ainda depende de `PriceCatalogEntry`
  para preço/descrição na BM/MEMÓRIA (`workbook_writer.py`, intocado), e o catálogo publicado
  não tem entrada para código fora da tabela SCO por definição. Fica registrado como
  lacuna a fechar quando a medição de um item `IE########` for necessária de fato.
- Autorização de gasto para a sugestão de código SCO por modelo. **Autorizada e
  executada em 2026-08-13** na eval paga sintética do M5 (teto US$ 1,50 respeitado;
  Sonnet aprovado como braço das duas tarefas — ver
  [Model Routing](ai/MODEL_ROUTING.md)). A extração paga da prancha **real** da Toca
  segue como ato pendente do aceite, roteirizada em
  [RUNBOOK_VALUATION_TOCA_ACCEPTANCE](operations/RUNBOOK_VALUATION_TOCA_ACCEPTANCE.md).

### M3 em código: extração de legenda e revisão do takeoff (offline)

O começo da cadeia de medição — a legenda já quantificada da prancha do projetista —
ganhou mecanismo, inteiramente offline e sintético
([Valuation Context](architecture/VALUATION_CONTEXT.md)).

- Domínio espelho: `packages/valuation/src/croquito_valuation/takeoff.py`
  (`TakeoffPacket`/`TakeoffItem`) reproduz a forma e o ciclo `proposed`/`ambiguous` →
  `confirmed`/`rejected` do `ReviewPacket`/`DimensionReading` do worker sem importar dele
  (`ADR-0016`); recusa fechada de re-decisão (`TAKEOFF_ITEM_ALREADY_REVIEWED`) e de
  confirmação de item ambíguo sem quantidade informada (`TAKEOFF_ITEM_CONFIRMED_INCOMPLETE`).
- Prancha sintética como fonte única de desenho e gabarito: `plate.py`
  (`render_synthetic_plate`) desenha a prancha inventada a partir da mesma constante
  (`SYNTHETIC_LEGEND_ROWS`) que devolve o gabarito da legenda em pixels — nenhum número
  escrito duas vezes.
- Fixture amarrada por digest: `takeoff_fixture.py` só extrai o `PlateArtifacts` que ela
  mesma acabou de gerar; arquivo alterado entre gerar e extrair recusa
  (`TAKEOFF_FIXTURE_ARTIFACT_MISMATCH`) em vez de virar item de takeoff.
- Overlay com banner de aviso fixo ("legenda quantificada, revisão obrigatória, não gera
  medição") e três comandos offline no CLI `croquito-valuation`: `extract-legend`,
  `review-takeoff` e `takeoff-demo` (cadeia ponta a ponta com decisões sintéticas
  gravadas para reprodução).
- Eval com gate: `make valuation-eval` (`takeoff-eval`) mede o recall da legenda contra o
  gabarito e exercita de verdade os invariantes do fluxo de revisão — nenhum item nasce
  confirmado, a linha ilegível vira o único ambíguo, o pacote fica amarrado por digest à
  prancha, re-decisão é recusada, confirmar o ambíguo sem quantidade é recusado, revisar
  todos os pendentes zera `pending_items()` com decisão rastreável em cada item, e uma
  prancha adulterada depois de gerada é recusada. Recall 100% e todos os checks aprovados
  na fixture — **isso valida a fixture e o contrato do fluxo, não precisão de extração em
  prancha real de cliente**, que é marco futuro, pago e com gates próprios (mesma ressalva
  da eval de visão sintética).

### M4 em código: sugestão de código, confirmação e cadeia completa offline

O meio da cadeia de medição — ligar o quantitativo revisado ao contrato — ganhou
mecanismo, inteiramente offline e sintético
([Valuation Context](architecture/VALUATION_CONTEXT.md)).

- Matcher lexical determinístico (Dice de tokens + razão de sequência, stdlib) em
  `catalog.py`; `assignment.py` espelho deliberado de `association.py` do worker —
  shortlist que nunca confirma, com unidade compatível e presença no contrato dominando o
  ranking; itens sem candidato declarados em `unmatched_item_ids`. É o fallback
  permanente; o M5 só refina a shortlist.
- Confirmação de código fail-closed (`confirm-codes`): catálogo, contrato, ambiguidade de
  grupo, unidade sem nota e re-decisão recusam; decisão `vd_` determinística e conjunto
  imutável carregado adiante com `--previous`.
- `build-calc`: boletim e memória nascem do takeoff confirmado + códigos confirmados;
  plano de cálculo declara recipes (`PERIMETER_TIMES_HEIGHT` etc.), default quantidade
  direta; a quantidade confirmada pelo humano manda (`CALC_PLAN_QUANTITY_MISMATCH`);
  medição sai **sem aprovação** — aprovação e export continuam atos separados.
- `make valuation-demo` percorre a cadeia completa: a 4ª obra (`praca-sintetica-oeste`)
  nasce da prancha sintética — com rejeição de item na revisão (área de intervenção),
  rejeição de código (gramado sem cotação), conversão m→m² do alambrado registrada na
  decisão e impressa na memória — e entra na medição consolidada auditada (total
  38.859,46). Golden novo `valuation-demo-m4.canonical.json` substitui o M2 (dados
  sintéticos estendidos mudaram a GERAL; os comportamentos do M2 seguem fixados pelo
  golden novo; o M1 permanece).
- e2e in-process da cadeia inteira pelos comandos do CLI em
  `tests/e2e/test_valuation_full_chain.py`, incluindo as recusas no caminho.

Isso valida o mecanismo e o contrato da cadeia sobre fixture sintética — não precisão de
sugestão em catálogo real (o dossiê do M2.1 e o aceite real continuam pendentes).

### M5 em código: vias pagas, eval paga executada e comparador do aceite

As duas vias pagas da cadeia de medição ganharam mecanismo atrás dos gates existentes, a
primeira rodada paga foi executada com autorização explícita, e o comparador do aceite
existe ([Valuation Context](architecture/VALUATION_CONTEXT.md),
[Model Routing](ai/MODEL_ROUTING.md)).

- Duas tarefas novas de provider, aditivas em `providers.py`: `legend-extraction` (visão,
  transcrição literal da legenda quantificada — nenhum `Decimal` nasce no provider) e
  `sco-refinement` (a primeira tarefa de **texto puro** do repositório), com
  budget/retry/lineage/raw-store idênticos às tarefas existentes e contratos versionados
  em [Prompt Contracts](ai/PROMPT_CONTRACTS.md). O `sco-refinement` já está em `1.0.1`:
  o limite por flag nasceu de rodada paga real em que a resposta obediente ao schema
  estourava a composição da nota no domínio — o defeito era nosso e fechou por
  aritmética, não por truncamento.
- `extract-legend-real`: prancha real → pacote de takeoff com todo item `proposed` ou
  `ambiguous`, nunca confirmado; gate antes da rede (allowlist do documento por
  `authorize_page` + teto de gasto obrigatório); dúvida em rótulo, quantidade, unidade ou
  legibilidade produz item ambíguo sem quantidade, nunca número inventado.
- `suggest-codes --refine-arm`: refino pago como **permutação exata anotada** da
  shortlist lexical — código a mais, a menos ou novo recusa; lineage da chamada viaja no
  artefato (`suggester_version` + bloco `refinement`); a via lexical segue sendo o
  fallback permanente e o comando pago que falha recusa sem publicar artefato.
- `make valuation-extraction-eval`: gate dos dois estágios pagos, offline no CI (braço
  fixture embutido) com recall da legenda, acurácia de quantidade, top-1/top-3 do refino
  ao lado da baseline lexical e checks de gate exercitados de verdade (teto ausente
  recusa, imagem fora do manifest recusa, código fora da shortlist recusa, nenhum item
  nasce confirmado).
- Eval paga sintética executada em 2026-08-13 (teto autorizado US$ 1,50; custo real
  ≈ US$ 0,60–0,70): **Sonnet aprovou as duas tarefas** (recall 1,0; quantidade 1,0;
  top-1 do refino 0,8 → 1,0 sobre a baseline lexical) e é o braço da rodada real; o Opus
  reprovou — uma rodada invalidada por defeito nosso de contrato (corrigido) e uma
  reprovação real por violação de permutação (código duplicado na resposta), recusada
  pelo domínio como deve. A rodada também consertou o harness da eval: transcrição fiel
  ao rótulo **impresso** (nota colada ao elemento) passou a casar com o gabarito em vez
  de ser punida.
- `compare-bulletin` (`make valuation-compare`): o comparador do aceite, na família do
  `parity` — local, nunca CI, não escreve nos arquivos analisados. Casa o boletim gerado
  (`valuation.json`, fonte de verdade canônica) com a aba de BM real (valores em cache,
  layout declarado no template como dado), código a código e centavo a centavo, sem
  tolerância; `zero_cent` só é verdadeiro sem nenhum diff numérico e sem código ausente
  de um lado; código duplicado recusa nos dois lados.
- Runbook do aceite real:
  [RUNBOOK_VALUATION_TOCA_ACCEPTANCE](operations/RUNBOOK_VALUATION_TOCA_ACCEPTANCE.md),
  com comandos exatos, variáveis de ambiente (inclusive o `SSL_CERT_FILE` que o Python
  do `uv` exige neste macOS) e cada ato humano marcado como tal.

O que resta do M5 **não é código**: extração paga da prancha real da Toca, revisão e
confirmação reais do orçamentista e o `compare-bulletin` contra o BM real com zero
centavo. Risco conhecido do aceite, deliberadamente não antecipado: a leitura do BM real
recusa número com mais de duas casas (`canonical_number`); se o arquivo real trouxer
quantidade com quatro casas (padrão visto na GERAL do MAPÃO no M2.1), a recusa será
visível e a lacuna fechará como dado do template, nunca como tolerância silenciosa.

A primeira rodada real do M5 (prancha real do Campo do Toca, 2026-08-13, em andamento)
reformulou o aceite e apontou o marco seguinte: a obra é projeto novo de agosto/2026 e
**não tem BM real para comparar** — o produto da rodada é o boletim que o orçamentista
faria à mão, com o `compare-bulletin` pronto para a primeira medição real. A rodada
também produziu os achados de domínio registrados no
[Roadmap](product/ROADMAP.md) como marcos propostos — com a correção da orçamentista do
domínio: em obra **licitada**, item fora da lista SCO/contrato não pode vir da EMOP
(cadeia SCO → EMOP → composição vale só **pré-licitação**); o caminho é aditivo de
contrato (RE-RA), e o sistema deve produzir o dossiê do aditivo em vez de precificar por
fora — e dois achados de mecanismo: a shortlist lexical é fraca sobre catálogo real (rótulo de legenda
× descrição técnica SCO — busca por palavra-chave assistida cobriu o vão nesta rodada) e
o refino pago recusou `INVALID_SCHEMA` sobre payload real (provável estouro do limite de
rationale; candidato a dica de tamanho no template — a `1.0.2` foi consumida pelo patch
coletivo do rebranding, então essa mudança nasce em `sco-refinement@1.0.3`).

### M6 em código: UI local de homologação da medição

> **Registro do marco, não o estado de hoje.** O app `apps/medicao` e o modo hospedado
> descritos abaixo não existem mais: as telas migraram para `apps/web` e a cadeia passou a
> operar sobre a API `/v1` em 2026-08-18 — ver "A medição na API `/v1` autenticada". O que
> sobreviveu desta entrega é o servidor **local** do ADR-0020, e a guarda por digest citada aqui
> virou `base_version` na API.

A homologação da cadeia ganhou tela, priorizada pelo usuário para a orçamentista do
domínio homologar sem CLI ([ADR-0020](adr/0020-local-homologation-server-for-valuation.md)).

- `croquito-valuation serve` (`local_server.py`): servidor local fino sobre as mesmas
  funções de domínio fail-closed do CLI — recusa atravessa com código estável e nunca
  grava artefato. Identidade por flag (`--reviewer`) com `reviewer_id`/`decided_at`
  carimbados no servidor e recusados no corpo (`extra="forbid"`); guarda otimista por
  digest de arquivo (`LOCAL_STATE_MOVED`, 409) cobrindo localmente a lacuna declarada de
  `base_version`; imagens por nomes fixos com o digest mandando sobre o nome (prancha
  adulterada é tratada como ausente); busca por palavra-chave no catálogo como rota
  (mecanismo nascido da rodada real da Toca); CORS restrito à origem local; nenhum
  provider é chamado pelo servidor.
- `apps/medicao`: app React/TS strict novo, todo em português de obra, sem OIDC no
  caminho local (no modo hospedado do
  [ADR-0026](adr/0026-medicao-hospedada-sessao-autenticada-minima.md) a mesma tela exige
  sessão antes de ler a rodada) —
  quatro telas (rodada, revisão do takeoff sobre a prancha com bboxes SVG e decisão por
  item, confirmação de código com descrição completa + busca + distinção fornecimento ×
  execução declarada como dica de leitura, boletim e memória). A tela nunca calcula
  dinheiro (`format.ts` só troca pontuação, testado); nada nasce pré-marcado; item
  rejeitado por falta de código vira candidato a aditivo listado; `LOCAL_STATE_MOVED`
  preserva o formulário e oferece recarregar. Fluxo completo verificado ponta a ponta
  sobre a fixture sintética com o mesmo total do caminho in-process.
- Regras de agente do app em `apps/medicao/AGENTS.md`; a seção de medição do
  [FDD](product/FDD.md) passou a descrever a tela entregue; critério
  [VAL-07](product/ACCEPTANCE_CRITERIA.md) criado.
- A homologação real (orçamentista usando a rodada da Toca no mesmo dia) devolveu
  quatro correções absorvidas em horas: registro fino dos bboxes da legenda contra a
  tinta (`register-takeoff`/`legend_registration.py` — o defeito do VLM era **erro de
  escala** no eixo Y, ~1,28×, detectado porque o gate de confiança recusou o modelo de
  deslocamento fixo; solução: filtro de faixas pelo divisor da tabela + ajuste afim com
  casamento completo obrigatório; rodada real: 15/15 assentados); chips de inclusões
  **verbatim** da descrição SCO ("Inclui: …"/"Não inclui: …"/"somente fornecimento") em
  todo lugar que exibe código, mais a referência automática do catálogo no painel de
  decisão da revisão; prancha limpa por padrão (marcações só por opt-in); e upload da
  prancha do projetista pela tela (`POST /plates`) com **extração paga automática e
  assíncrona** — decisão explícita do usuário, freios registrados na emenda do
  [ADR-0020](adr/0020-local-homologation-server-for-valuation.md); fluxo real validado
  ponta a ponta (upload do PDF real → 15 itens, ≈ US$ 0,05). `serve --catalog` provê o
  catálogo à rodada nova na subida (nunca sobrescreve o de rodada existente) e o banner
  declara catálogo e disponibilidade da extração; na tela, catálogo ausente virou causa
  acionável em vez de "tente mais tarde". A segunda leva de feedback real endureceu
  mais três pontos: a busca do catálogo ganhou fronteira de palavra e ranking por
  similaridade ("gramado" não casa mais "programador"); o registro de âncoras ganhou o
  discriminador estrutural definitivo — linha de item tem régua vertical interna
  separando rótulo de valor, célula de nota mesclada não tem, e com isso a rodada real
  fechou bijeção 15×15 pelo método `rulings` (com `--restore-raw` para reprocessar do
  bruto sem nova chamada paga) — e o assentamento residual "na faixa mais próxima" foi
  removido: sem correspondência confiante, nenhum item é assentado, e a âncora de cada
  item viaja como `registered`/`raw` até a tela, que só desenha retângulo confirmado.
- `legend_registration.py` + `register-takeoff`: registro fino determinístico do bbox de
  cada item da legenda contra a tinta da prancha, espelho do `register-extraction` da
  geometria — motivado por feedback real da Toca (bboxes da legenda sistematicamente
  deslocados para baixo). Detecção de faixa de texto por projeção de tinta na coluna da
  legenda e casamento por programação dinâmica que preserva a ordem original e prioriza
  casar o máximo de itens antes de minimizar a distância entre centros; item sem faixa
  confiável fica intocado (`unmatched_item_ids`), nunca chuta. Fail-closed: pacote com
  algum item já decidido pelo orçamentista ou digest de imagem divergente recusa sem
  publicar nada. `run_legend_extraction` já devolve o pacote registrado;
  `register-takeoff` reprocessa um pacote já publicado, sem nova chamada paga.

### M7 em código: matcher híbrido de código SCO

O casamento item→código — apontado pelo usuário como o coração do produto ("não posso
correr o risco de o código ter no SCO e não fazer o match") — virou retrieval híbrido
com garantia medida ([ADR-0021](adr/0021-hybrid-sco-code-retrieval.md)).

- Léxico: radicais conservadores pt-BR + **sinônimos de domínio como dado** (seed
  versionado, curável pela orçamentista, expansão declarada no resultado) + cobertura
  da consulta ponderada por IDF; shortlist nunca mais vazia por corte — sempre top-N
  com score visível.
- Semântico: embeddings do catálogo (dado público SCO; índice local de 40 MB amarrado
  por digest e receita, ≈ US$ 0,007 por versão de catálogo; `index-catalog`), kNN em
  numpy, fusão RRF; candidatos com `origin` e scores declarados na busca.
- **A garantia virou gate**: golden set versionado (rótulos reais da Toca + gabarito
  sintético) com `recall@20 = 100%` — no catálogo real, **12/12** (léxico puro: 4/12),
  com oráculo por **família** nos casos em que o rótulo não discrimina a variante
  (altura do alambrado; refletor halógeno × projetor — a variante é decisão humana com
  a prancha, `human_choice` registrado). Ranks por braço fixados no golden; regressão
  acusa.
- Fallback permanente declarado: sem chave/teto/índice → léxico funcional com aviso;
  embeddings nunca confirmam nada; confirmar código segue ato humano.
- Medições descartadas registradas (índice sem prefixo de código: 8/12; pesos de RRF
  por caso: rejeitado) e oportunidade anotada como dado futuro (lista de ruído de
  legenda — "existente" pesou mais que "refletor" no IDF do caso real).

Rodada 2.2 (2026-08-13, [ADR-0021](adr/0021-hybrid-sco-code-retrieval.md) aceito):

- **Lista de ruído de legenda implementada e ativada** (`sco-legend-noise-v1.json`,
  amortecimento de peso — nunca remoção — das palavras de estado; suggester híbrido
  bumpado para `v2`, artefato `v1` segue relendo). O ganho não estava no rank do alvo
  (byte-idêntico, e a primeira calibração quase descartou o mecanismo por isso): estava
  na **composição do top-20** que a orçamentista varre — junk-share de "REFLETOR
  EXISTENTE" caiu de 10/20 para 0/20, agora gateado no golden (`hybrid_junk_max`).
- Pisos ratchet de top-1 (3/12) e top-3 (5/12) vigiados no golden; sobem quando
  melhorarem, nunca descem.
- **Sinal de abstenção "possível aditivo": medido e descartado** — cobertura, cosseno e
  evidência-não-coberta dos 3 aditivos reais se sobrepõem por completo às dos 12 com
  código (um aditivo cobre 100% dos radicais). Aditivo é condição contratual, não
  distância de retrieval; a decisão segue humana via `confirm-codes` fail-closed
  (`note_abstention_measurement` no golden).

O que resta do M6 **não é código**: a homologação real pela orçamentista do domínio
sobre a rodada da Toca (ato humano). A rodada real está estacionada no elo da
confirmação de código exatamente para esse ato; se ela preferir decidir a revisão do
zero, a re-extração paga custa ~US$ 0,05 dentro do teto já autorizado.

### M8 em código: a fronteira licitada × pré-licitação

A regra da orçamentista (2026-08-13) virou mecanismo em três fases
([ADR-0027](adr/0027-price-source-provenance-and-bid-boundary.md)), todas offline:

- **Dossiê do aditivo (obra licitada).** A lista de "candidatos a aditivo", antes só
  seção derivada na tela, virou artefato de domínio: `build_amendment_dossier` cruza as
  rejeições de código com os itens confirmados do takeoff (rejeição na revisão do
  takeoff nunca é aditivo), exige a nota da rejeição como justificativa, recusa rodada
  com decisão de código pendente (artefato de fechamento, complemento do boletim) e não
  tem campo de preço por construção — item de dossiê incoerente com a decisão recusa na
  releitura. CLI `build-amendment-dossier`, rotas locais `POST /dossier/build` +
  `GET /dossier` (espelhos do par do boletim) e a tela exibindo o dossiê do servidor,
  com a lista do cliente rebaixada a prévia declarada. RE-RA segue só leitura; o pedido
  à prefeitura segue ato humano (VAL-08).
- **Proveniência de fonte de preço + catálogo EMOP.** `PriceOrigin`
  (`sco`/`emop`/`composition`) em catálogo e entrada, com default `sco` que relê todo
  artefato M1–M7 sem migração; um catálogo é uma fonte só (`CATALOG_ORIGIN_MIXED`) e a
  forma do código é validada pela origem. O guardrail da licitada existe em dois pontos
  (`BULLETIN_PRICE_ORIGIN_FORBIDDEN` em `build_worksite_bulletin` e no escritor da
  planilha): preço de EMOP ou composição nunca chega à medição. `import-emop` lê o .DBF
  (dBASE III, leitor mínimo interno, stdlib) com o layout inteiro como dado
  (`EmopCatalogLayout`) e fixture sintética fonte-única; o catálogo digital real é pago
  (assinatura GRE, ato comercial pendente) e o formato real fecha como dado no layout.
- **Composição manual + orçamento-base.** `CostComposition` com preço unitário sempre
  recomputado (truncamento conservador por linha, documentado com o caso em que
  truncar-por-linha ≠ truncar-no-fim) compilada a catálogo `origin=composition` amarrado
  por digest à fonte (`import-compositions`). O orçamento-base (`build-estimate`) monta
  o `Estimate` sobre a cascata declarada nos `--catalog` (ordem é dado; origem duplicada
  recusa), com **proveniência por linha** (origem, digest, data-base — releitura recusa
  fonte fora da cascata), confirmação citando a fonte (`ASSIGNMENT_CATALOG_REQUIRED`),
  item sem preço declarado em `unpriced_item_ids` e a mesma memória de cálculo do
  boletim. Sem contrato, saldo ou aprovação de medição — e com as vias pagas recusando
  ou degradando declaradamente sobre cascata. Demo determinística
  `make valuation-estimate-demo` (5 linhas nas três origens, 1 item sem preço) com
  golden novo; `make valuation-demo` permaneceu byte-idêntico e o id de decisão
  histórico não mudou (VAL-09).

Portões do M8: `make check` e `make test` verdes ponta a ponta (pytest 1165 → 1277;
vitest web 346; medição 126 → 127), goldens M1/M4 e matcher intocados. O que resta do
M8 não é código: a importação do .DBF real da EMOP depende da assinatura GRE, e o
primeiro dossiê de aditivo real depende da rodada da Toca homologada.

## Decisões aceitas

- Produto AI First com revisão humana obrigatória antes do export.
- AWS gerenciada em `sa-east-1`.
- Processamento de IA global controlado.
- OpenAI e Anthropic como provedores independentes.
- OCR auxiliar: Cloud Vision por padrão; Document AI monta no lugar dele por
  `CROQUITO_DOCAI_PROCESSOR`, escalada nomeada em
  [ADR-0037](adr/0037-document-ai-como-braco-de-ocr.md), que revisa D3 do
  [ADR-0035](adr/0035-suite-hospedada-openai-anthropic-direto.md) (ambos `Proposed`).
- Step Functions e Fargate no lugar de Celery/Redis.
- Scene graph canônico entre extração e DXF.
- DXF R2018 em metros; DWG fora do MVP.
- Retenção de sete dias e exclusão manual imediata.
- Três casos dourados: Guaxindiba, Toca e Raul Campelo.

## Riscos ativos

| Risco | Impacto | Tratamento definido |
|---|---|---|
| Croqui fora de escala | Alto | Cotas e constraints têm precedência sobre pixels |
| Geometria subdeterminada | Alto | Bloquear ou exigir aproximação explícita |
| Erros correlacionados dos modelos | Alto | Regras determinísticas, evals e revisão humana |
| Escrita fraca ou ambígua | Médio | Recortes, dois provedores e correção regional |
| Curvas sem parâmetros | Alto | Spline aproximada e pontos de controle revisáveis |
| Custo de duas IAs | Médio | Roteamento, métricas por página e budgets |
| Dados processados globalmente | Alto | Minimização, entitlement contratual e contratos comerciais |
| Cloudflare fora do Terraform | Médio | O CDN/proxy do host público **não é declarado como código**: o único provider em `infra/` é AWS. Ele decide cache e roteamento de borda de tudo o que o usuário vê, e nada disso é revisável nem versionado — foi o que deixou o tema do login servindo uma cópia de 19/08 por quase quatro dias (2026-08-22). Contraria o guardrail de infraestrutura declarada. Mitigado por ora no que estava ao alcance: `deploy/nginx.conf` fixa o cache dos estáticos do Keycloak em 5 min. Importar a zona para Terraform é trabalho próprio, ainda sem dono |

## Próximo marco

Nenhum destes itens é implementável por um agente: todos dependem de decisão humana
registrada, de autorização de gasto ou de verificação fora do repositório.

- Registrar a primeira decisão de profissional do domínio na sessão autenticada do
  Guaxindiba autorizado, mantido em storage local protegido. **Concluído em
  2026-08-12/13: 29 decisões de leitura reais no job "Campo do Guaxindiba v2", pela
  sessão autenticada local.**
- Registrar a primeira aprovação técnica real, com reconhecimento nominal dos critérios
  de escopo não cobertos. **Concluído em 2026-08-13: aprovações técnicas reais com o
  ACC-GUA-001 declarado coberto pela cena métrica e declaração do profissional.**
- Primeiro DXF real de Guaxindiba exportado pela sessão autenticada e aberto no AutoCAD,
  com a evidência de abertura registrada fora do repositório. **Concluído em
  2026-08-13: pacote auditado exportado pela sessão autenticada (auditoria
  `approved`) e aberto no AutoCAD pelo profissional, com a prancha anotada —
  cotas da folha fechando em resíduos de micrômetros, vãos arbitrados, notas e
  legenda no padrão keynote. Evidência de abertura fora do repositório.**
- Executar a primeira eval paga autorizada com os golden cases fornecidos, budget,
  comparação de baseline e registro de rollback. **Executada em 2026-08-11 na Toca
  (Opus × Sonnet, budget respeitado, rollback documentado em
  [Model Routing](ai/MODEL_ROUTING.md)); a ativação do opt-in local e a extensão ao
  Raul Campelo seguem exigindo autorização explícita de gasto.**

O ciclo real completo — decisão profissional, arbitragem de vãos, aprovação
nominal e exportação auditada aberta no AutoCAD — foi percorrido de ponta a ponta
no Campo do Guaxindiba em 2026-08-13. O próximo passo de validação é o teste por
um segundo profissional e a repetição do ciclo nos demais golden cases.

### A medição na API `/v1` autenticada

Desde 2026-08-18 a cadeia de medição **opera sobre a API `/v1`**, com tabelas próprias,
concorrência otimista real e papel `orcamentista` exigido em cada rota. O desenho é o
[ADR-0028](adr/0028-medicao-na-api-v1-autenticada.md) (`Accepted` em 2026-08-17) e a execução
foi [F-003](features/F-003-medicao-v1-migration/feature.md), com evidência em
[evidence.md](features/F-003-medicao-v1-migration/evidence.md).

As dezoito rotas da seção "Medição de obra" do [API Contract](architecture/API_CONTRACT.md)
existem, estão no documento OpenAPI e são cobertas por um e2e que percorre a cadeia inteira por
HTTP (`tests/e2e/test_valuation_v1_chain.py`), com o worker consumindo os dois comandos de fila
da medição. A raiz é a **rodada** (`ValuationRound`): a tela lista, abre e cria rodada, e o
catálogo de preços entra pelo presign na criação.

Uma decisão de execução mudou o desenho do overlay do takeoff. O API Contract herdara do
servidor de medição a promessa de devolver "o overlay atualizado" junto da decisão, mas na API
isso exigiria ler o PNG promovido e gravar blob pela fronteira que declara não fazer nem uma
coisa nem outra, com render de imagem no request path. O
[ADR-0030](adr/0030-overlay-do-takeoff-reconstruido-na-fila.md) move o re-render para a fila: o
overlay declara a própria idade pelo digest do pacote que o originou, e **vencido é `200` com a
marca**, nunca erro nem silêncio.

**A ponte hospedada foi removida**, não desativada: `create_hosted_app`, `hosted_auth.py`, a
flag `--hosted`, a variável `CROQUITO_IO_DIRECT_WRITE`, o passo de esteira do serviço
`croquito-medicao-hml` e o proxy `/medicao/api/` saíram do repositório. O
[ADR-0026](adr/0026-medicao-hospedada-sessao-autenticada-minima.md) continua descrevendo a ponte
que existiu — ADR aceito é imutável.

O que **fica** é o servidor local do [ADR-0020](adr/0020-local-homologation-server-for-valuation.md)
(`croquito-valuation serve`, sem `--hosted`), com as mesmas dezesseis rotas e os mesmos 89 testes
de `tests/worker/test_valuation_local_server.py` passando sem uma linha alterada: ele é a
ferramenta da máquina do operador e não foi substituído.

Pendente e **humano**: a concessão do papel `orcamentista` no realm de homologação e a
homologação real da orçamentista sobre uma medição de verdade — que esta migração não
substitui. A remoção dos recursos hospedados foi verificada como feita em 2026-08-18: nem o
serviço `croquito-medicao-hml` nem o bucket `croquito-hml-rounds` existem mais no projeto. O
stack de infraestrutura, que ainda os declarava e os teria recriado no próximo apply, deixou
de declará-los junto com a runtime SA — a única peça do grupo que ainda existe.

### Runner de migrations revisadas

Desde 2026-08-17 o schema do banco evolui por migrations revisadas
([ADR-0029](adr/0029-runner-de-migrations-revisadas.md), execução em
[F-004](features/F-004-migrations-runner/feature.md)). O runner é o Alembic, com as revisões
dentro de `croquito_api.migrations` — distribuídas na mesma imagem da API — e aplicadas por
`python -m croquito_api.bootstrap`, que é o comando que o job de banco da esteira já
executava. A revisão `0001` é a baseline: descreve o schema que antes nascia de
`create_all` mais cinco blocos de `ALTER TABLE` condicional.

Com isso a lacuna declarada no [ADR-0025](adr/0025-homologacao-em-gcp-cloud-run.md) —
"um runner de migrations revisadas continua sendo requisito de produção" — deixa de existir,
e [F-003](features/F-003-medicao-v1-migration/feature.md) perde o portão que a impedia de
criar tabela. O que o runner traz junto:

- O banco declara em que versão está; banco defasado deixa de ser indistinguível de banco
  em dia.
- Banco anterior ao runner é **adotado por carimbo**, nunca recriado, e só depois de
  conferir que ele corresponde à baseline: todas as tabelas da revisão `0001` e todas as
  colunas mais recentes — se faltar qualquer uma, o comando recusa. A régua é a baseline, e
  não o modelo do dia: tabela que nasce em revisão posterior não existe no banco legado e é
  criada pelo `upgrade` logo depois do carimbo.
- Modelo alterado sem a migration correspondente reprova o CI: um PostgreSQL de serviço
  aplica as migrations em banco limpo e a diferença contra `Base.metadata` precisa ser vazia.
- `Database.create_schema()` voltou a ser só `create_all`, para teste e banco novo.
- Migrations são forward-only: não há `downgrade` em ambiente hospedado, e remover coluna
  segue exigindo aprovação humana explícita.

**Ato humano pendente**: o primeiro deploy de homologação com o runner, que é o que
exercita o caminho de carimbo contra o banco real do ambiente. Ele está bloqueado pelo
ambiente fora do ar, descrito a seguir.

### A homologação em GCP ficou fora do ar de 2026-08-14 a 2026-08-18

**Restabelecida em 2026-08-18**, com `make smoke-hml` verde nas quatro rotas: a jornada
responde, o endereço herdado da medição redireciona, a API se identifica e o Keycloak anuncia o
issuer da borda. O registro abaixo é de como ela caiu — mantido porque a explicação errada
custou uma rodada inteira de diagnóstico.

Durante a queda, medido em 2026-08-18: `/revisao/` e `/medicao/` respondiam 200; a API e o
discovery OIDC, não. É a confirmação da fumaça de 2026-08-17 registrada em F-001, com causa.

A causa raiz é uma só, e não é a que o erro sugere: **o endereço do banco nos secrets aponta
para um endpoint do Neon que não existe mais**. Todos os consumidores relatam
`password authentication failed for user 'neondb_owner'`, mas a senha gravada é idêntica à
corrente — comparada por digest, sem expor nenhuma das duas. O proxy do Neon roteia pelo
hostname e responde a endpoint desconhecido com falha de autenticação; o sintoma apontava para
a credencial, o defeito estava no endereço.

Com isso o Keycloak falha no boot (`Failed to obtain JDBC connection`) e chama `exit(1)`, e o
job `croquito-db-init-hml` falhou em 2026-08-17T14:12 pelo mesmo motivo. Como a esteira para no
job de banco por desenho, **nenhuma revisão nova entra no ar desde 2026-08-14** — o portão fez
o que devia, e ninguém soube. Com a esteira barrada, o container de exemplo do Cloud Run que
alguém pôs em `croquito-scene-hml` num teste de roteamento em 2026-08-14 nunca foi substituído
pela imagem real, que na revisão anterior havia subido com sucesso.

**O banco de homologação está vazio.** As duas branches do projeto Neon — `production` e
`staging` — não têm nenhuma tabela, e nenhuma tem `alembic_version`. O schema criado em
2026-08-14 vivia no endpoint que sumiu. Duas consequências que não são de código: o primeiro
deploy com o runner vai **criar o schema desde a baseline**, não carimbar banco preexistente
— então o ato pendente de [F-004](features/F-004-migrations-runner/feature.md) continua aberto
—, e o realm do Keycloak nasce sem usuário nenhum, o que torna obrigatória a recriação do
usuário da orçamentista e do papel `orcamentista`.

Dois registros do repositório caíram junto com o diagnóstico. O **"bug de plataforma no GFE"
não existe**: o Cloud Run reserva `/healthz` na raiz de todo serviço, e como o proxy remove o
prefixo, `/api/healthz` chega como o path reservado e nunca alcança o container — o 404 vem do
Google, não do FastAPI. A fumaça que verificava aquele caminho jamais poderia passar, e foi ela
que motivou o rename de serviço em 2026-08-14. A verificação externa passou a usar
`/api/v1/meta`. E o stack ainda declarava `croquito-medicao-hml`, que já não existe no projeto
— o próximo apply o teria recriado.

O conserto é a [F-006](features/F-006-hml-conserto/feature.md), com a decisão técnica no
[ADR-0031](adr/0031-segredo-de-homologacao-gerenciado-por-terraform.md): o valor das
credenciais de homologação passa a ser gerenciado por Terraform no repositório central de
infraestrutura, porque coordenada de banco que só um humano sabe atualizar é coordenada que
ninguém atualiza. O stack passou a declarar a **branch** do Neon por nome e derivar dela o host
e a senha — nenhum hostname escrito à mão, que foi o que quebrou.
A fumaça da borda (`make smoke-hml`) passou a verificar **conteúdo** e não só status — um
`200` do container de exemplo não é a API — e roda igual na esteira e na máquina do operador.

O ADR-0031 foi aceito por ato humano em 2026-08-18, e o responsável humano confirmou a
conclusão do role mapping, da desativação segura da HMAC antiga e do merge do PR #4. F-006 está
`DONE`. O carimbo do Alembic contra banco preexistente continua não atendível neste deploy e é
follow-up de F-004.

**O ambiente voltou em 2026-08-18**, e a fumaça da esteira das 14:06 prova as quatro rotas,
com o discovery anunciando o issuer da borda pública e os quatro serviços servindo a mesma
imagem por SHA. Ao verificar o estado interno do banco — que o diagnóstico anterior havia
declarado *não verificado* — apareceu o que a documentação negava: Keycloak e aplicação
**dividiam o schema `public`**, 107 tabelas no mesmo lugar. O DSN do Keycloak pedia
`currentSchema=keycloak` desde sempre, mas esse parâmetro só move a sessão; quem move o DDL do
Liquibase é `KC_DB_SCHEMA`, que ninguém setara. Consertar isso depois de o realm ter usuário
real custaria esse usuário, então foi feito antes: cada componente no seu schema, `public`
esvaziado, e o `search_path` da aplicação deliberadamente sem `public` no fim, para que schema
faltando vire falha barulhenta em vez de queda silenciosa. O terceiro achado da mesma rodada é
de esteira: `ci` e `deploy-hml` disparavam juntos no merge e corriam **em paralelo**, então a
imagem subia sem o portão ter passado naquele commit — o portão virou um workflow chamável e o
deploy passou a esperá-lo.

Com o ambiente de volta, duas features novas abriram na mesma data. A
[F-007](features/F-007-tela-de-login/feature.md) — a porta de entrada do produto — está
`READY_FOR_PLANNING` com prioridade `HIGH`: o
[ADR-0032](adr/0032-porta-de-entrada-e-estado-sem-sessao.md) foi aceito por ato humano e o visual
do mock foi aprovado; o texto da tela continua pendente. A
[F-008](features/F-008-ciclo-de-vida-de-conta/feature.md) — convite, recuperação de senha e login
com Google — nasce `BLOCKED`, e o que a bloqueia é decisão humana e não código: o provedor de
e-mail e o domínio remetente, sem os quais nenhum dos três fluxos existe; o
[ADR-0033](adr/0033-conta-por-convite-e-login-federado.md) também foi aceito. Do mesmo trabalho
nasceu o [Design System](engineering/DESIGN_SYSTEM.md), que tira a identidade do produto de dentro
de um comentário de folha de estilo e passa a ser a fonte que um Design Approval Package cita.

Em 2026-08-19, na primeira revisão da porta nova, abriu a
[F-009](features/F-009-suite-hospedada-sem-aws/feature.md): o upload real no HML terminava em
`REVIEW_REQUIRED` sem pacote de revisão porque a suite hospedada de providers dependia de
credencial AWS (Bedrock/Textract) que nunca existiu no ambiente GCP publicado — o caminho AWS
nunca rodou neste repositório, e a chamada de OCR do Textract no snapshot era código morto. A
suite passa a ter três braços diretos: `openai` e `anthropic` (Anthropic primário, OpenAI
reserva e contraparte da comparação dupla, com notas `PROVIDER_FALLBACK_*` sempre que degrada,
nunca silenciosamente) e `ocr` (Cloud Vision `document text detection`, corroborando cada
leitura com `READING_n_OCR_CONFIRMED`/`_OCR_EVIDENCE_MISSING`; `make ocr-eval` mede recall
100% e zero falso-confirmado na fixture sintética). A decisão técnica é o
[ADR-0035](adr/0035-suite-hospedada-openai-anthropic-direto.md), `Proposed` — aceitação segue
como ato humano. As tarefas de implementação (T1, T2, T3, T5) estão completas e o deploy do HML
(flag, segredos das duas chaves, teto de US$ 5 por rodada e allowlist por digest) está
preparado, sem nenhum `apply` executado por agente. A infraestrutura em `biahflow/infra` tem
dois PRs: #14 (mesclado, mas cujo primeiro `apply` falhou com 403 ao tentar habilitar
`vision.googleapis.com`) e #15 (concede a permissão que faltava à conta de deploy, aguardando
merge). O que resta não é código: aceite do ADR, merge/reexecução do apply em `biahflow/infra`,
valores dos dois segredos, papel `platform_operator` e entitlement do tenant, digest do PDF
autorizado na allowlist, e o merge/deploy em `biahflow/croquito`.

**Atualização (F-012, 2026-08-19):** a allowlist por digest citada acima como pendência foi
removida do caminho hospedado — o parágrafo seguinte registra a decisão e o que resta é só o
entitlement por tenant, agora ativável pela jornada "Plataforma" em vez de curl.

Na primeira revisão da porta de entrada com a F-009 pronta, o usuário vetou os dois rituais
manuais que a ativação da suite hospedada deixava: entitlement por curl com token pescado do
DevTools, e allowlist de digest por env var exigindo um redeploy por documento — diretriz
literal "isso já nasce com a visão de SaaS, não posso ter esses gargalos/travas". Nasceu a
[F-012](features/F-012-operacao-saas-autorizacao-ia/feature.md), prioridade `HIGH`. A decisão
técnica é o [ADR-0036](adr/0036-autorizacao-de-ia-contratual-sem-allowlist-documental.md),
`Proposed`: o gate de envio de documento a provider pago no caminho hospedado passa a ser
integralmente entitlement contratual ativo do tenant + consent por job + teto de custo por
invocação + kill switch — sem segunda barreira por documento. A allowlist por digest
(`LocalWorkerSettings.ai_extraction_allowed_digests`, o parse de
`CROQUITO_AI_EXTRACTION_ALLOWED_DIGESTS` e a checagem em `_handle_upload`) saiu de
`services/worker/src/croquito_worker/local_queue.py` e do deploy do worker
(`.github/workflows/deploy-hml.yml`); ela permanece intocada no caminho offline de eval
(`extraction_eval.py`), onde não existe tenant nem entitlement e o operador que roda o comando
é quem autoriza o documento. A API ganhou `GET /v1/me` (subject, tenant_id, roles — como a SPA
decide mostrar a jornada) e dois GETs de plataforma: `GET /v1/platform/tenants` (união de
entitlements, projects e uploads, com o estado do entitlement de cada tenant) e
`GET /v1/platform/tenants/{id}/ai-processing-entitlement` (200 sempre, disabled/nulos quando
nunca ativado); nenhum dos dois muda o `PUT` existente. A SPA ganhou a jornada "Plataforma"
(`?plataforma=`, kind próprio em `route.ts`): o botão só aparece com o papel
`platform_operator`, a lista de tenants ativa/desativa entitlement inline com
`agreement_reference` e `Idempotency-Key`, e um formulário cobre o tenant que só existe no
Keycloak (sem pegada no banco). O runbook de ativação do HML perdeu os passos de digest e
redeploy por documento; o que fica é Keycloak (papel e tenant), ativação pela tela, upload pela
SPA e o kill switch como rollback. O que resta não é código: aceite do ADR-0036 e o merge, que
é deploy. A F-012 também abriu um inventário de gargalos SaaS ainda sem contrato — UI de
membros do tenant (F-013, depende do convite da F-008), entidade tenant e onboarding
self-service (F-014), recriar o job de upload existente (F-015), rotação de chaves de provider
(F-016) e custo agregado por tenant com trilha de auditoria na tela (F-017) — registrado no
[Roadmap](product/ROADMAP.md).

## Condição para avançar ao processamento real

- PDFs mantidos fora do Git. **Atendido localmente.**
- Entitlement contratual ativo para chamadas pagas e externas.
- Autorização controlada do gabarito inicial para revisão autenticada. **Atendido.**
- Decisão profissional do domínio registrada na sessão autenticada. **Atendido em
  2026-08-12/13 (Campo do Guaxindiba v2); nunca fabricada por fixtures ou agentes.**
- Evals básicas executáveis. **Atendido para visão e solver sintéticos.**
- Segredos configurados fora do repositório.
