# Fluxo do sistema: que processos existem e quem chama quem

Status: Accepted  
Responsável: Architecture / Engineering  
Última revisão: 2026-08-21

Este documento é **descritivo**: registra a topologia que existe hoje no código, não o
desenho que se pretende. Onde a realidade diverge de outro documento, ele diz qual é qual.

Ele responde três perguntas que estavam espalhadas: **quais processos rodam**, **quem
chama quem**, e **onde o sistema recusa em vez de prosseguir**. O detalhe profundo de cada
peça continua nos documentos de referência, linkados ao longo do texto.

## 1. O que o sistema é

Duas cadeias de trabalho sobre uma fonte geométrica única.

- **Cadeia do croqui** — levantamento de campo vira cena técnica auditável e sai em DXF.
- **Cadeia de medição e orçamento** — prancha quantificada vira boletim de medição ou
  planilha orçamentária.

As duas são **independentes no código**, e isso é verificável: nenhum arquivo de
`packages/valuation/` importa `SceneRevision`, `Entity` ou qualquer módulo do worker do
croqui — a única coisa que atravessa é o gerador de UUID. A cadeia do croqui termina no
pacote CAD; a de medição começa numa prancha que um projetista desenhou fora do produto,
e nunca lê o DXF que a outra produziu.

O acoplamento entre elas é só de **infraestrutura**: mesmo módulo de fila, mesma sessão na
web, mesmo gerador de identificador. Elas se encontram na operação, não em memória — a
costura humana está descrita na [Cadeia operacional](../product/CADEIA_OPERACIONAL.md).

O que atravessa a cadeia do croqui é o **scene graph**
(`packages/core/src/croquito_core/models.py`): modelos de IA e OpenCV produzem
*observações*, e nada vira geometria sem passar por ele. Toda entidade carrega `precision`
(`exact`, `derived`, `approximate`, `unresolved`) e `Provenance`.

## 2. Os processos que existem

Não há um contêiner por serviço: **uma imagem Python única**
(`docker/python.Dockerfile`) roda a API, o worker e o job de inicialização de banco — é o
mesmo código, com entry points diferentes. A SPA e o Keycloak têm imagens próprias.

<figure>
<div class="figbox">
<svg viewBox="0 0 740 320" role="img" aria-label="Topologia: navegador fala com a SPA, que chama a API; a API le e escreve no banco e no object storage, valida token no Keycloak e publica comandos na fila; o worker consome a fila e e o unico que chama provedores de IA.">
<defs>
<marker id="fx-a" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" class="f-ink"/></marker>
<marker id="fx-b" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" class="f-gap"/></marker>
</defs>

<rect x="16" y="16" width="120" height="46" fill="none" class="l-ink"/>
<text x="76" y="37" text-anchor="middle" class="mono" font-size="10.5">SPA (nginx)</text>
<text x="76" y="52" text-anchor="middle" font-size="11" class="quiet">React + Vite</text>

<rect x="212" y="16" width="140" height="46" fill="none" class="l-ink" stroke-width="2"/>
<text x="282" y="37" text-anchor="middle" class="mono" font-size="10.5">API</text>
<text x="282" y="52" text-anchor="middle" font-size="11" class="quiet">FastAPI · uvicorn</text>

<rect x="212" y="130" width="140" height="46" fill="none" class="l-ink"/>
<text x="282" y="151" text-anchor="middle" class="mono" font-size="10.5">FILA</text>
<text x="282" y="166" text-anchor="middle" font-size="11" class="quiet">Pub/Sub ou SQS</text>

<rect x="212" y="244" width="140" height="46" fill="none" class="l-ink" stroke-width="2"/>
<text x="282" y="265" text-anchor="middle" class="mono" font-size="10.5">WORKER</text>
<text x="282" y="280" text-anchor="middle" font-size="11" class="quiet">push server</text>

<rect x="452" y="8" width="130" height="38" fill="none" class="l-ink"/>
<text x="517" y="32" text-anchor="middle" font-size="11.5">Keycloak (OIDC)</text>
<rect x="452" y="58" width="130" height="38" fill="none" class="l-ink"/>
<text x="517" y="82" text-anchor="middle" font-size="11.5">PostgreSQL</text>
<rect x="452" y="108" width="130" height="38" fill="none" class="l-ink"/>
<text x="517" y="132" text-anchor="middle" font-size="11.5">Object storage</text>
<rect x="452" y="246" width="130" height="42" fill="none" class="l-gap" stroke-width="2"/>
<text x="517" y="264" text-anchor="middle" font-size="11.5" class="t-gap">Provedores de IA</text>
<text x="517" y="280" text-anchor="middle" font-size="10.5" class="t-gap">pagos, atrás de flag</text>

<line x1="136" y1="39" x2="206" y2="39" class="l-ink" stroke-width="1.5" marker-end="url(#fx-a)"/>
<text x="171" y="31" text-anchor="middle" font-size="10" class="quiet">/v1</text>

<line x1="352" y1="30" x2="446" y2="27" class="l-ink" stroke-width="1.2" marker-end="url(#fx-a)"/>
<line x1="352" y1="45" x2="446" y2="77" class="l-ink" stroke-width="1.2" marker-end="url(#fx-a)"/>
<line x1="352" y1="55" x2="446" y2="127" class="l-ink" stroke-width="1.2" marker-end="url(#fx-a)"/>

<line x1="282" y1="62" x2="282" y2="124" class="l-ink" stroke-width="1.5" marker-end="url(#fx-a)"/>
<text x="292" y="98" font-size="10.5" class="quiet">publica (síncrono)</text>

<line x1="282" y1="176" x2="282" y2="238" class="l-ink" stroke-width="1.5" marker-end="url(#fx-a)"/>
<text x="292" y="212" font-size="10.5" class="quiet">push HTTP</text>

<line x1="352" y1="267" x2="446" y2="267" class="l-gap" stroke-width="1.8" marker-end="url(#fx-b)"/>
<line x1="368" y1="258" x2="368" y2="150" class="l-ink" stroke-width="1.2" stroke-dasharray="4 3" marker-end="url(#fx-a)"/>
<line x1="368" y1="150" x2="446" y2="132" class="l-ink" stroke-width="1.2" stroke-dasharray="4 3" marker-end="url(#fx-a)"/>
<text x="384" y="200" font-size="10" class="quiet">grava artefatos</text>

<text x="16" y="308" class="mono t-gap" font-size="10.5">A API nunca chama provedor de IA — só o worker chama, e nunca no caminho de um request.</text>
</svg>
</div>
<figcaption>Quatro processos e quatro dependências externas. A seta grossa em destaque é a única que gasta dinheiro por chamada, e ela sai do worker, nunca da API.</figcaption>
</figure>

| Processo | O que é | Como sobe |
|---|---|---|
| SPA | React 19 + Vite, build estático servido por nginx | serviço próprio, único com ingress público |
| API | FastAPI, `croquito_api.main:app` por uvicorn | serviço com ingress interno |
| Worker | `croquito-worker-push` → servidor HTTP que recebe push do Pub/Sub em `POST /pubsub` | serviço interno e privado; só aceita chamada autenticada da fila |
| Init de banco | `python -m croquito_api.bootstrap`, aplica as migrações | **job**, não serviço; roda antes dos demais no deploy |
| Keycloak | provedor OIDC, realm `croquito` | serviço com imagem própria |

Os CLIs `croquito-demo` e `croquito-valuation` percorrem as mesmas cadeias offline, por
comando idempotente. São ferramenta de demo, eval e operação local — não sobem em
ambiente hospedado.

## 3. Quem chama quem

A API autentica, autoriza e coordena ciclo de vida. Ela **não** renderiza PDF, **não**
chama modelo e **não** gera DXF no caminho do request.

| Da API para | Módulo que chama | Síncrono no request? |
|---|---|---|
| Banco | `croquito_api.database` (SQLAlchemy) | sim, toda rota |
| Object storage | `croquito_api.storage.ArtifactStore` | sim, mas só para assinar URL e ler/escrever artefato pequeno — o PDF do cliente nunca passa pelo processo |
| Fila | `ProcessingQueue` (SQS) ou `PubSubProcessingQueue` | **sim, deliberadamente**: a rota só responde depois que o comando está durável na fila |
| Keycloak | `croquito_api.auth.OidcAuthenticator` (valida JWT por JWKS) | sim, em toda rota autenticada |
| Provedores de IA | — | **nunca**; vivem só em `croquito_worker.providers` |

O transporte da fila é escolhido por configuração e nunca há dois no mesmo deploy: com
`CROQUITO_PUBSUB_TOPIC` definido vale Pub/Sub, senão SQS. Os dois publicam **o mesmo corpo
JSON**, o que faz o worker não saber por qual transporte a mensagem chegou.

## 4. O que trafega na fila

Todo trabalho caro é comando na fila. O despachante é único
(`croquito_worker.local_queue.LocalQueueWorker.dispatch`), independente do transporte.

| Comando | Faz o quê |
|---|---|
| `process_upload` | ingestão do PDF, propostas de visão, pacote de revisão de cotas |
| `solve_trace_scene` | traçado em lote e solver, produzindo cena métrica |
| `export_scene_package` | gera o DXF, reabre, audita, renderiza e empacota |
| `answer_chat_turn` | turno da conversa sobre a folha |
| `extract_valuation_plate` | leitura paga da legenda da prancha, cadeia de medição |
| `extract_estimate_plate` | mesma leitura, cadeia de orçamento |
| `rerender_takeoff_overlay` | redesenha o overlay do takeoff (medição) |
| `rerender_estimate_takeoff_overlay` | idem, orçamento |

Comando desconhecido levanta `UnroutableMessageError`. Na entrega por push isso vira
descarte explícito em vez de reentrega infinita.

## 5. Cadeia do croqui, etapa por etapa

Quase toda etapa é comando idempotente do CLI `croquito-demo`
(`services/worker/src/croquito_worker/cli.py`) e, no ar, trabalho de fila.

| Etapa | Módulo | Produz |
|---|---|---|
| Ingestão do PDF (não copia o original) | `ingest.py` | PNGs 200 DPI + manifesto com digest |
| Propostas OpenCV em pixels | `vision.py` | candidatos sempre `unresolved`, `export=false` |
| Pacote de revisão de cotas | `review.py` | `ReviewPacket` com recorte, digest e `raw_text` |
| Associação proposta ↔ cota | `association.py` | ranking observacional; **nunca confirma** |
| Calibração pixel → metro | `proposal_calibration.py` | promove só a `approximate` |
| Solver retangular | `rectangle_solver.py` | resíduos, constraints, blockers críticos |
| Traçado em lote (a cota manda) | `tracing.py` | cena métrica, Y espelhado, precisão declarada |
| Export CAD | `dxf.py` | gera, reabre, audita, renderiza e empacota |

A calibração é a exceção: **não tem subcomando no CLI**. Ela só é alcançada pela rota
`POST /v1/jobs/{job_id}/review/calibration`, e uma calibração que não fecha volta como
`CALIBRATION_INVALID`.

## 6. Cadeia de medição e orçamento

Vive em `packages/valuation`, que não depende do worker nem do scene graph. A referência
profunda é o [Valuation Context](VALUATION_CONTEXT.md).

O caminho comum é: importar catálogo de preços → extrair a legenda da prancha (takeoff) →
revisar item a item → sugerir e confirmar **os** códigos do catálogo → **fechar o pacote de
serviços de cada elemento** → montar o documento.

O plural e o fechamento são do [ADR-0053](../adr/0053-cardinalidade-n-n-elemento-servico.md):
um elemento da prancha dispara N serviços (`PISO EM CONCRETO`, medido uma vez, alimenta
seis códigos). A identidade da confirmação é o par `(item_id, code)`, e como a presença de
um código deixou de responder "este item acabou?", quem responde é um ato humano próprio —
o `ItemPackageClosure`. Enquanto ele não vem, o item aparece como **pendente**.

Desde a F-044, **fechar o pacote tem um efeito a mais**: as confirmações daquele elemento
viram observações no índice de precedentes (`precedent_observations`), chaveadas por (rótulo
normalizado, fonte de preço) e isoladas por tenant. É o que faz um rótulo já decidido
reencontrar o mesmo pacote de códigos na praça seguinte. O índice tem uma segunda fonte, a
**semeadura** de orçamentos passados (`croquito-valuation precedent-extract` local, e
`POST /v1/precedents/seed`), porque sem ela ele nasceria vazio. Precedente é observação: quem
o lê oferece, e o clique continua sendo da orçamentista.

O documento final é que difere, e é onde a fronteira licitada vale:

- **Medição** → boletim + memória de cálculo, só `PriceOrigin.sco`.
- **Orçamento-base** → planilha orçamentária com BDI, cascata de fontes declarada.

## 7. Onde o sistema recusa

Estes são os pontos em que o sistema para em vez de entregar coisa errada. São o desenho,
não defeito.

| Portão | Onde | Recusa quando |
|---|---|---|
| `ensure_exportable()` / `export_errors()` | `croquito_core.models.SceneRevision` | cena não aprovada, entidade `unresolved`, `approximate` sem aceite explícito, `exact` sem provenance, issue crítica aberta, ou medida confirmada incompatível com a geometria |
| Código de saída 2 do CLI | `rectangle_solver.py`, `tracing.py` | o solver terminou em `review_required` **ou** em `conflict` — nos dois casos não há cena métrica aprovável |
| Associação explícita obrigatória | solver | falta `reading_id → proposal_id`; proximidade em pixels nunca é associação implícita |
| Auditoria do DXF | `dxf.py` | o auditor reprova o arquivo gerado ao reabri-lo — o ZIP não é publicado |
| `CALIBRATION_INVALID` | `proposal_calibration.py` | âncoras degeneradas ou erro acima da tolerância |
| `BULLETIN_PRICE_ORIGIN_FORBIDDEN` | `valuation/calc.py`, reafirmado em `workbook_writer.py` | catálogo com origem diferente de `sco` na obra licitada — **duas linhas de defesa**, a segunda na hora de escrever a planilha |
| `CALC_PLAN_QUANTITY_MISMATCH` | `valuation/calc.py` | o plano de cálculo não fecha com a quantidade que o humano confirmou |
| `CALC_PACKAGE_NOT_CLOSED` / `ESTIMATE_PACKAGE_NOT_CLOSED` | `valuation/calc.py`, `valuation/estimate.py` | item confirmado com pacote de serviços em aberto — o boletim não é montado pela metade. Rejeição fecha o item sozinha |
| `CALC_PACKAGE_NOT_SUPPORTED` / `ESTIMATE_PACKAGE_NOT_SUPPORTED` | `valuation/calc.py`, `valuation/estimate.py` | item com mais de um código **sem `CalcMatrix`**: no regime legado o builder indexa um vínculo por item e descartaria os outros em silêncio, escolhendo uma linha ao acaso. É a **fronteira do regime legado**, não medida provisória — com matriz, é ela quem funde o pacote em serviços e o portão não se aplica |
| `CALC_CONTRIBUTION_*` | `valuation/models.py` | a base declarada da parcela não bate com o que ela implica: canteiro com elemento de origem, parcela derivada sem dizer de qual serviço vem, código de origem fora de parcela derivada, parcela de elemento sem nomear o elemento, ou código de origem sem forma de código de catálogo |
| `SITE_SETUP_PARAMETER_MISSING` / `SITE_SETUP_CODE_ABSENT` | `valuation/site_setup.py`, **só na aplicação** do acervo de canteiro | o acervo cita parâmetro de obra que a rodada não declarou (a recusa **nomeia todos**), ou código que o catálogo da cascata não tem (nomeia o código). Falha fechada: nenhuma parcela nasce parcialmente. A **pré-visualização não recusa** por nenhum dos dois desde 2026-08-28 (F-042 T4): ela devolve todas as parcelas e marca as bloqueadas (`missing_parameters`, `code_absent`, `blocked_parcel_ids`), porque recusar a lista de onde a saída mandava remover parcelas era beco sem saída. Prever não é aplicar: a leitura que marca não grava nada |
| `PRECEDENT_SEED_*` | `croquito_api/precedents.py`, na **semeadura** do índice de precedentes (F-044) | a praça semeada já é rodada real do tenant (`WORKSITE_CONFLICT` — misturar as duas origens sob a mesma chave juntaria o histórico importado de uma planilha com o que o sistema gravou dos atos da orçamentista), o pacote foi normalizado por outra estratégia (`STRATEGY_UNSUPPORTED` — duas chaves para o mesmo rótulo, e a metade errada nunca reencontraria nada) ou a normalização declarada não bate com a que o servidor calcula (`NORMALIZATION_MISMATCH`, nomeando as **posições**, nunca os rótulos). A recusa fica do lado da semeadura, e **não** do fechamento de pacote: semear é importação deliberada, que pode ser refeita; fechar o pacote é o ato central da jornada, e travá-lo pela contabilidade de um índice seria a ferramenta impedindo o trabalho |
| `VALUATION_EXPORT_BLOCKED` | `valuation/models.py` | medição não aprovada, aprovação que não casa com o conteúdo, período fora de sequência, código fora do contrato, preço/unidade divergentes do contrato ou saldo estourado |
| Auditoria da planilha | `valuation/canonical.py` | reabre o `.xlsx`, recanonicaliza e compara célula a célula; divergência não publica |
| Entitlement de IA | rotas de extração | tenant sem autorização contratual — recusa **antes** de enfileirar |
| `JOURNEY_UNAVAILABLE` | dependência única do router, por prefixo de rota (`croquito_api.journeys`) | a jornada está `disabled` neste ambiente, ou está `pilot` e o tenant não tem entitlement ativo — recusa **antes** do portão de papel de cada rota, que continua onde estava |

Duas simetrias que valem notar: cada cadeia tem o **seu** portão de exportação
(`SceneRevision` de um lado, `Valuation` do outro), e cada uma **reabre e audita o que
gerou** antes de publicar — `audit_dxf` na cadeia do croqui, `audit_workbook` na de
medição. Nenhuma confia no que acabou de escrever.

A regra que amarra a cadeia do croqui: **dimensão exata nunca é derivada de pixels**, e
`approximate` continua `approximate` até o DXF.

## 8. Onde roda hoje

**GCP / Cloud Run**, com bucket GCS por interoperabilidade S3, Pub/Sub como fila e
PostgreSQL gerenciado.

**A infraestrutura mora em outro repositório: `biahflow/infra`.** É o Terraform de lá que
provisiona serviços, bucket, Pub/Sub, DNS e segredos do ambiente. O diretório `infra/`
deste repositório declara apenas recursos AWS, do desenho-alvo de produção que
[nunca foi aplicado](AWS_DEPLOYMENT.md) — ele **não** sobe nada do que está no ar. Quem
procura "onde muda a infraestrutura" tem que sair deste repositório.

Aposentar formalmente o alvo AWS em favor do GCP é decisão de arquitetura por ADR, não
edição de documento; até lá o ADR-0002 continua registrado como a decisão de produção.

Um segundo ponto que confundia quem lia o repositório pela primeira vez: as duas *state
machines* de [Processing Workflows](PROCESSING_WORKFLOWS.md) **não existem** — não há Step
Functions, Fargate nem EventBridge. O que existe é o despachante único da fila descrito na
§4. Aquele documento passou a declarar isso no topo; a separação conceitual que ele defende
(extração e exportação como etapas distintas, com revisão humana no meio) vale e está
implementada, só que por comandos de fila.

## Documentos de referência

- [Cadeia operacional](../product/CADEIA_OPERACIONAL.md) — o fluxo de trabalho humano.
- [Domain Model](DOMAIN_MODEL.md) — agregados e invariantes.
- [API Contract](API_CONTRACT.md) — a superfície `/v1` completa.
- [Valuation Context](VALUATION_CONTEXT.md) — a cadeia de medição em profundidade.
- [Trace Stage](TRACE_STAGE.md) — o estágio de traçado.
- [HML](../operations/HML.md) — o ambiente que está no ar.
