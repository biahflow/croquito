# ADR-0028: Medição de obra na API `/v1` autenticada

Status: Proposed  
Data: 2026-08-17  
Responsável: Product / Engineering

## Contexto

O [Status](../STATUS.md) declara a medição hospedada como **ponte, não destino**, e nomeia o
destino: "migração da medição para a API `/v1` autenticada (tabelas próprias, contratos TS
gerados, concorrência otimista real, papel `orcamentista` no realm)". O
[ADR-0026](0026-medicao-hospedada-sessao-autenticada-minima.md) escreve a mesma dívida do outro
lado, e com data: o modo hospedado "é código que existirá até a sessão autenticada completa e
depois será removido".

Nenhuma fonte versionada descreve **como** essa API deve ser. Um Planner que recebesse hoje
"migre a medição para `/v1`" precisaria tomar decisões que não lhe pertencem, porque as lacunas
são de contrato, não de execução:

- **Não há desenho de rota.** O vocabulário proibido do
  [ADR-0016](0016-valuation-bounded-context.md) exclui `Job`, o que impede pendurar a medição em
  `/v1/jobs/{job_id}/...`, o padrão da maioria das rotas de `services/api`. Há precedentes de
  raiz não-`Job` no mesmo arquivo — `/v1/projects` (`services/api/src/croquito_api/main.py:3232`),
  `/v1/platform/tenants/{tenant_id}/...` (linha 1542), `/v1/uploads/presign` (linha 1638) — mas
  nenhum foi decidido para a medição.
- **Não há esquema relacional.** O estado da rodada é hoje um diretório de artefatos JSON com
  nomes de arquivo fixos (`services/worker/src/croquito_worker/valuation/cli.py:202-245`), e o
  cliente nunca envia caminho — travessia de diretório é impossível por construção, não
  filtrada (`local_server.py:655-675`).
- **Não há semântica de `base_version`.** O ADR-0026 declara "sem `base_version` real" e atribui
  a lacuna a este marco. A guarda de hoje é digest de arquivo (`LOCAL_STATE_MOVED`,
  `local_server.py:331`), citado em três pontos distintos (`base_packet_sha256`,
  `base_suggestions_sha256`, `base_assignments_sha256`).
- **O pipeline de contratos é mono-modelo.** `croquito_core.schema_export` exporta apenas
  `SceneRevision` (`packages/core/src/croquito_core/schema_export.py:14`), e os tipos de
  `apps/medicao/src/api.ts` são escritos à mão, declarados no próprio arquivo como espelho
  manual do servidor local.
- **Não há decisão sobre onde as telas passam a viver.** O
  [ADR-0020](0020-local-homologation-server-for-valuation.md) rejeitou `apps/web` no M6 pelo
  estado daquele app naquele momento, não como regra permanente.

Este ADR decide o contrato. Ele **não** implementa nada: a execução é da feature de migração
([F-003](../features/F-003-medicao-v1-migration/feature.md)), que permanece bloqueada até este
rascunho ser aceito por ato humano.

## Decisão

### D1 — A entidade raiz é `ValuationRound`, sob `/v1/valuation-rounds`

A rodada de medição — uma prancha, um takeoff, uma confirmação de códigos, um boletim, um
dossiê — ganha nome próprio e vira a raiz das rotas: `/v1/valuation-rounds/{round_id}/...`.
`ValuationRound` não colide com `Job`, `Measurement*` nem `*Budget*` (ADR-0016) e nomeia o que o
servidor de medição já opera hoje sob o argumento `--root`. O
[Valuation Context](../architecture/VALUATION_CONTEXT.md) recebe a entrada de glossário
`rodada → ValuationRound`.

### D2 — Os artefatos da rodada são revisões imutáveis com colunas JSON

A persistência segue o padrão já declarado de `ReviewRevisionRecord`
(`services/api/src/croquito_api/database.py:146-184`): duas tabelas,
`valuation_rounds` (identidade, tenant, obra, catálogo instalado, contador de versão) e
`valuation_round_revisions` (append-only, `UniqueConstraint(round_id, version)`), com uma coluna
JSON por artefato — `takeoff_packet_json`, `code_suggestions_json`, `code_assignments_json`,
`valuation_json`, `amendment_dossier_json`, `extraction_lineage_json`. Nenhuma coluna JSON é
atualizada no lugar: mutação cria linha nova.

Blobs continuam fora do banco: o PDF da prancha, o PNG promovido e o overlay ficam no object
store sob o prefixo do tenant, e a linha de revisão guarda digest e metadado — o mesmo arranjo
que a cena já usa.

### D3 — `base_version` é uma única linha de versão por rodada

Toda mutação envia `base_version` e recebe `409 REVISION_CONFLICT` quando a versão corrente
diverge, exatamente como `POST /v1/jobs/{job_id}/revisions` (`main.py:3323-3326`). A rodada tem
**um** contador, não um por artefato: o takeoff, a shortlist de códigos, as confirmações, o
boletim e o dossiê pertencem à mesma cadeia causal, e uma decisão de takeoff invalida a
shortlist derivada dela. Os três digests de arquivo de hoje deixam de existir como conceito de
contrato.

### D4 — Códigos de erro: reuso primeiro, código novo só para semântica nova

Erro de domínio continua sendo `422 DOMAIN_VALIDATION_FAILED` com o código de domínio em
`details`, no padrão do `domain_error_handler` (`main.py:1509-1524`). Isso vale para as famílias
inteiras `TAKEOFF_*`, `CALC_*`, `ASSIGNMENT_*`, `AMENDMENT_DOSSIER_*` e `CATALOG_*`, que são
invariantes de `packages/valuation` e **não** entram na lista de códigos obrigatórios do
[API Contract](../architecture/API_CONTRACT.md) — a API não republica o vocabulário do domínio.

Códigos locais reaproveitados por código já existente:

| Código local | Código `/v1` |
|---|---|
| `LOCAL_STATE_MOVED` | `REVISION_CONFLICT` |
| `LOCAL_UPLOAD_INVALID` | `INVALID_UPLOAD` |
| `LOCAL_ARTIFACT_MISSING` (recurso inexistente) | `NOT_FOUND` |
| `LOCAL_QUANTITY_INVALID`, `LOCAL_REQUEST_INVALID`, `MODEL_VALIDATION_FAILED`, `LOCAL_BASE_DIGEST_REQUIRED`, `LOCAL_BASE_DIGEST_UNEXPECTED` | `DOMAIN_VALIDATION_FAILED` |
| `LOCAL_EXTRACTION_UNAVAILABLE` | `PROVIDER_UNAVAILABLE` ou `AI_PROCESSING_NOT_AUTHORIZED` |
| `HOSTED_SESSION_REQUIRED`, `HOSTED_SESSION_INVALID`, `HOSTED_REVIEWER_INVALID` | `401` padrão da API |
| `HOSTED_ROLE_REQUIRED` | `FORBIDDEN` |

Códigos novos, um por precondição que hoje não tem equivalente em `/v1`:
`ROUND_STAGE_NOT_READY` (etapa anterior da cadeia ausente, sucessor de `LOCAL_ARTIFACT_MISSING`
quando a causa é ordem e não inexistência), `ROUND_PLATE_ALREADY_PRESENT`
(`LOCAL_ROUND_ALREADY_HAS_PLATE`), `EXTRACTION_IN_PROGRESS` (`LOCAL_EXTRACTION_BUSY`),
`SUGGESTIONS_ALREADY_REFINED` (`LOCAL_SUGGESTIONS_REFINED`), `TAKEOFF_REVIEW_INCOMPLETE`
(`LOCAL_TAKEOFF_REVIEW_INCOMPLETE`), `CATALOG_QUERY_EMPTY` (`LOCAL_SEARCH_QUERY_EMPTY`) e
`CATALOG_REQUIRED` (rodada sem catálogo instalado, precondição de configuração e não de cadeia).

Os dois códigos de digest-base (`LOCAL_BASE_DIGEST_REQUIRED`, `LOCAL_BASE_DIGEST_UNEXPECTED`)
deixam de ter equivalente próprio: com `base_version` obrigatório no corpo, ausência ou formato
errado é falha de contrato do request, e só a divergência de versão é `REVISION_CONFLICT`.

Não migram, porque nomeiam conceito de processo local que deixa de existir: `LOCAL_ROOT_MISSING`,
`LOCAL_REVIEWER_INVALID`, `SERVE_REVIEWER_REQUIRED`, `SERVE_REVIEWER_FORBIDDEN`,
`HOSTED_CONFIG_MISSING`, `LOCAL_EXTRACTION_ARM_INVALID`,
`LOCAL_EXTRACTION_ARM_FIXTURE_FORBIDDEN` e `LOCAL_CATALOG_INVALID`.

### D5 — Imagem binária sai por URL assinada, não pelo request path

`GET /v1/valuation-rounds/{round_id}/plate` e
`GET /v1/valuation-rounds/{round_id}/takeoff/overlay` devolvem JSON com URL assinada de curta
duração sob o prefixo do tenant, no padrão já escrito para o pacote CAD
(`API_CONTRACT.md`, `GET /v1/jobs/{job_id}/exports/{export_id}`): a URL nunca é registrada em log
nem em auditoria. A API não faz streaming de bytes de cliente.

### D6 — A prancha entra pelo presign existente

`POST /plates` multipart deixa de existir. O cliente chama `POST /v1/uploads/presign`
(`main.py:1638`, sem alteração), envia o PDF direto ao storage e depois associa o upload à
rodada com `POST /v1/valuation-rounds/{round_id}/plate`, corpo `{upload_id, base_version}`.
Vale aqui a regra já escrita no API Contract: a API nunca aceita PDF em JSON, e o cliente envia
no PUT exatamente os headers devolvidos pelo presign.

### D7 — A extração paga é comando de fila, não thread do processo

A extração de legenda sai da `threading.Thread` daemon de hoje (`local_server.py:1520-1525`) e
vira comando enfileirado pela `ProcessingQueue` (`main.py:550-626`), consumido pelo worker.
`POST /v1/valuation-rounds/{round_id}/plate/extractions` responde `202` e o acompanhamento é por
`GET /v1/valuation-rounds/{round_id}`, como em exports e trace-solves. A extração é chamada paga
de provider: o gate contratual por tenant do
[ADR-0012](0012-contractual-ai-processing-entitlements.md) se aplica, com
`AI_PROCESSING_NOT_AUTHORIZED`, e a fila indisponível devolve `503 PROCESSING_UNAVAILABLE` com
o comando repetível.

### D8 — A rodada é do tenant, e não pende de `projects`

`tenant_id` vem do JWT, é coluna indexada da rodada e filtra toda query, como em todas as
tabelas de `database.py`. A rodada **não** tem chave estrangeira para `ProjectRecord`: um
projeto é do contexto de croqui, e a fronteira do ADR-0016 vale também para o modelo relacional.
A obra permanece atributo da rodada (`worksite_key`, `worksite_name`), não entidade própria.

O papel exigido nas rotas de medição é `orcamentista`, o mesmo que o modo hospedado já exige
(`hosted_auth.py:39`), pelo mesmo validador compartilhado `croquito_core.oidc`. Quem revisa
takeoff e confirma código não é quem aprova cena.

### D9 — As telas de medição migram para `apps/web`

`apps/medicao` é removido junto do modo hospedado, e as telas de revisão de takeoff, confirmação
de código, boletim e dossiê passam a viver em `apps/web`, consumindo os tipos gerados de
`@croquito/contracts` no lugar dos tipos escritos à mão. Uma sessão OIDC, um build, um deploy.

Isto é registrado como **tensão**, não como consenso silencioso: o ADR-0020 rejeitou `apps/web`
no M6. Aquela rejeição foi pelo estado daquele app naquele momento e o próprio ADR-0020 não a
declarou permanente; este ADR **não** o supersede, porque o servidor local segue válido para a
máquina do operador. Se, na execução, o estado de `apps/web` reprovar a decisão, o caminho é
novo ADR — não uma escolha de implementação.

### Inventário das rotas do servidor de medição

Todas as linhas citadas são de `services/worker/src/croquito_worker/valuation/local_server.py`.
O `router` é criado na linha 1960 e incluído no app na linha 2447. A contagem apurada é de
**16 rotas** no `router`, conferida contra o arquivo por
`grep -c "@router\." services/worker/src/croquito_worker/valuation/local_server.py`. Nenhuma
contagem é herdada de outro documento: o "~7 rotas" citado no ADR-0020 é anterior a M6, M7 e M8 e
não descreve o estado atual. `GET /healthz` está declarado fora do `router` (linha 2505, dentro
de `create_hosted_app`), é sonda de saúde e não rota de domínio.

| Linha | Rota local | Destino |
|---|---|---|
| 1994 | `GET /state` | `GET /v1/valuation-rounds/{round_id}` |
| 1998 | `GET /takeoff` | `GET /v1/valuation-rounds/{round_id}/takeoff` |
| 2009 | `GET /images/plate` | `GET /v1/valuation-rounds/{round_id}/plate` (URL assinada, D5) |
| 2027 | `GET /images/overlay` | `GET /v1/valuation-rounds/{round_id}/takeoff/overlay` (URL assinada, D5) |
| 2034 | `POST /plates` | `POST /v1/uploads/presign` + `POST /v1/valuation-rounds/{round_id}/plate` (D6) |
| 2059 | `POST /plates/extract` | `POST /v1/valuation-rounds/{round_id}/plate/extractions` (D7) |
| 2080 | `POST /takeoff/decisions` | `POST /v1/valuation-rounds/{round_id}/takeoff/decisions` |
| 2123 | `GET /suggestions` | `GET /v1/valuation-rounds/{round_id}/code-suggestions` |
| 2156 | `POST /suggestions/recompute` | `POST /v1/valuation-rounds/{round_id}/code-suggestions/recompute` |
| 2224 | `GET /catalog/search` | `GET /v1/valuation-rounds/{round_id}/catalog/search` |
| 2270 | `GET /codes` | `GET /v1/valuation-rounds/{round_id}/code-assignments` |
| 2291 | `POST /codes/decisions` | `POST /v1/valuation-rounds/{round_id}/code-assignments/decisions` |
| 2362 | `POST /calc/build` | `POST /v1/valuation-rounds/{round_id}/calc` |
| 2395 | `GET /bulletin` | `GET /v1/valuation-rounds/{round_id}/bulletin` |
| 2407 | `POST /dossier/build` | `POST /v1/valuation-rounds/{round_id}/amendment-dossier` |
| 2432 | `GET /dossier` | `GET /v1/valuation-rounds/{round_id}/amendment-dossier` |

Duas rotas `/v1` não têm origem local, porque hoje a rodada é o argumento `--root` do processo e
não um recurso: `POST /v1/valuation-rounds` (cria a rodada, instala catálogo e obra) e
`GET /v1/valuation-rounds` (lista as rodadas do tenant). `GET /healthz` do modo hospedado não
migra: a API já tem a sua (`main.py:1526`).

### Desenho do pipeline de contratos multi-modelo

Registrado como desenho, **não** implementado por este ADR nem pela feature que o produz.
`croquito_core.schema_export` deixa de exportar um modelo e passa a percorrer um registro
`{modelo → arquivo de schema}`, trocando o par `--output`/`--check` por `--output-dir`/`--check-dir`
sobre um manifesto versionado em `packages/contracts`. O gerador TS
(`packages/contracts/scripts/generate.mjs`) e o verificador de drift
(`packages/contracts/scripts/check-generated.mjs`) passam a iterar esse manifesto, e
`make contracts` / `make check` continuam sendo os dois portões, agora sobre N arquivos.

O ponto sensível fica escrito para quem implementar: hoje `packages/contracts` depende só de
`croquito_core`, e os modelos da medição vivem em `packages/valuation`. Exportar
`TakeoffPacket`, `CodeSuggestionSet`, `CodeAssignmentSet`, `Valuation` e `AmendmentDossier` exige
decidir se o registro importa dos dois pacotes ou se cada pacote publica o seu manifesto. Este
ADR não decide isso.

### Condição de remoção do modo hospedado

A dívida com data do ADR-0026 vence quando, cumulativamente: toda rota da tabela de inventário
existir em `/v1` com paridade verificada por teste; o papel `orcamentista` estiver também no
realm de desenvolvimento local, e não só em `keycloak/croquito-hml-realm.json`; e as rodadas hoje
no bucket de homologação tiverem destino decidido. Cumpridas as três, saem do repositório
`create_hosted_app`, `hosted_auth.py`, o serviço Cloud Run `croquito-medicao-hml`, a rota
`/medicao/api/` do host público, a variável `CROQUITO_IO_DIRECT_WRITE` e o app `apps/medicao`.
A remoção é execução de F-003, não deste ADR.

O servidor **local** do ADR-0020 (`serve` sem `--hosted`) continua existindo para a máquina do
operador e não é alcançado por esta condição.

### O que este ADR não decide

Cada item abaixo permanece decisão pendente, nomeada aqui para não ser tomada por conveniência
de implementação:

- **Migração das rodadas existentes** no bucket de homologação: importar para o banco,
  reprocessar do PDF, ou nenhuma migração de dados.
- **Destino do CLI `croquito-valuation`**, hoje o único caminho do refino pago de código e da
  cadeia offline completa.
- **Client e audience OIDC**: a decisão D9 implica reuso do client `croquito-web` por estar no
  mesmo app, mas audience própria para as rotas de medição continua em aberto.
- **Momento de entrada do papel `orcamentista` no realm local** — nesta feature ou em outra.
- **Hierarquia obra e período**: a rodada carrega `worksite_key` como atributo (D8); se obra e
  período viram recursos próprios em `/v1` é decisão de outro marco.
- **Paginação e listagem** de `GET /v1/valuation-rounds`, além da regra geral de cursor opaco já
  escrita no API Contract.
- **Aprovação da medição** (`ValuationApproval`) como rota `/v1`: a cadeia mapeada aqui vai até o
  boletim e o dossiê, que é onde as rotas locais param hoje.

## Alternativas

- **D1 — `/v1/valuations/{valuation_id}`.** Rejeitada por tensão de vocabulário: no glossário do
  contexto `Valuation` é o boletim consolidado, produzido no fim da cadeia (`valuation.json`,
  gravado só pelo `/calc/build`). A raiz existiria antes do seu próprio conteúdo, e a rota do
  boletim seria `/v1/valuations/{id}/bulletin`.
- **D1 — `/v1/worksites/{worksite_id}/rounds/{round_id}`.** Rejeitada por antecipar decisão: obra
  e período não existem como entidade hoje, e a hierarquia exigiria decidir agora o ciclo de vida
  de ambos, sem demanda que o justifique.
- **D2 — tabelas normalizadas por item** (item de takeoff, sugestão, confirmação, linha de
  boletim). Rejeitada porque o ADR-0016 declara o JSON canônico como fonte de verdade e a
  validação vive nos modelos Pydantic de `packages/valuation`; normalizar duplicaria invariante
  em DDL e criaria uma segunda verdade sobre o mesmo artefato.
- **D2 — manter o diretório de artefatos, agora em bucket por tenant.** Rejeitada: é o arranjo de
  hoje, e é justamente ele que impede lock, concorrência e multi-tenant (ADR-0026).
- **D3 — uma versão por artefato**, 1:1 com os três digests atuais. Rejeitada por multiplicar
  contadores sem invariante que os concilie: uma decisão de takeoff invalida a shortlist derivada
  dela, e três contadores independentes não expressam isso.
- **D3 — manter a guarda por digest de conteúdo.** Rejeitada: o digest resolve corrida entre abas
  do mesmo usuário, não entre sessões, e o ADR-0026 já a registrou como substituto declarado.
- **D4 — republicar os códigos de domínio na lista de códigos obrigatórios.** Rejeitada: são
  dezenas de códigos de `packages/valuation`, e promovê-los a contrato de API congelaria
  vocabulário interno do domínio em `/v1`.
- **D4 — traduzir tudo para os códigos genéricos existentes**, sem código novo. Rejeitada:
  perderia precondição que a tela precisa distinguir (extração em curso × prancha já presente ×
  etapa anterior pendente), reduzindo tudo a `409`.
- **D5 — proxy binário autenticado**, com `blob:` no cliente, que é o que `apps/medicao` faz hoje.
  Rejeitada: põe bytes de cliente no request path da API, contra a regra de que a API não
  renderiza nem serve conteúdo, e desperdiça o padrão de URL assinada já existente.
- **D6 — manter multipart em `/v1`.** Rejeitada: contraria a seção de uploads do API Contract e
  criaria um segundo caminho de ingestão de PDF, com um segundo lugar para verificar digest,
  tamanho e tipo.
- **D7 — `BackgroundTasks` do FastAPI.** Rejeitada: reproduz em `/v1` a limitação de instância
  única do ADR-0026 — trabalho pago preso ao processo que atendeu o request, perdido em restart.
- **D7 — extração síncrona no request.** Rejeitada: chamada paga de provider no request path
  amarra o timeout do cliente ao do provider e contraria o ADR-0013 e o ADR-0015, que já tiraram
  export e traçado do request path.
- **D8 — pendurar a rodada em `/v1/projects/{project_id}`.** Rejeitada: reusaria navegação pronta
  ao custo de acoplar os dois contextos delimitados por chave estrangeira, exatamente o que o
  ADR-0016 separou.
- **D8 — isolamento adicional por obra dentro do tenant.** Rejeitada por ora: exigiria decidir
  agora como a obra é cadastrada e autorizada, e não há demanda de separar orçamentistas por obra
  dentro da mesma organização.
- **D9 — manter `apps/medicao` apontando para `/v1`.** Rejeitada como destino: seria o menor diff,
  mas conservaria dois apps, dois deploys e dois caminhos de sessão para a mesma organização, e o
  ADR-0020 e o ADR-0026 declaram esse client descartável por construção.
- **D9 — terceiro app novo.** Rejeitada: paga scaffolding e um terceiro build para resolver um
  problema de navegação que a decisão de fronteira entre jornadas resolve dentro de `apps/web`.

## Consequências

### Positivas

- O Planner passa a ter fronteira: cada rota do inventário tem destino declarado, e o Builder
  implementa sem escolher desenho.
- A concorrência otimista da medição passa a ser a mesma da cena — um `base_version`, um
  `REVISION_CONFLICT` — e para de ser um mecanismo paralelo que só a medição entende.
- Os tipos de `apps/medicao/src/api.ts`, hoje espelho manual, deixam de existir como categoria de
  trabalho: o drift passa a ser detectado por `make check`, e não por revisão humana.
- A extração paga entra no mesmo regime de fila, entitlement e auditoria que o resto do
  processamento pago, em vez de uma thread sem registro de fila.
- A dívida com data do ADR-0026 ganha condição de vencimento verificável, escrita antes da
  implementação começar.
- A rodada passa a ter nome próprio no glossário (D1) e escopo de tenant igual ao do resto do
  banco (D8): a medição deixa de ser o único contexto sem partição de dados, e o segundo tenant
  passa a ser configuração e não marco.
- Revisão imutável com coluna JSON (D2) preserva a auditoria que o diretório de artefatos já
  dava — cada estado anterior continua legível —, agora com transação e sem depender de escrita
  atômica em volume montado.
- Prancha e overlay passam pelo mesmo caminho de upload e de URL assinada que o resto do produto
  (D5, D6): um lugar só para verificar digest, tamanho e tipo, e nenhum byte de cliente no
  request path.

### Negativas

- O marco é grande e mexe em quatro camadas ao mesmo tempo (banco, API, contratos, telas); nada
  dele entrega valor ao usuário até que a cadeia inteira funcione.
- Migrar as telas para `apps/web` é diff maior que apontar `apps/medicao` para `/v1`, e mistura
  duas jornadas profissionais na mesma navegação — o custo é de UX, e é aceito aqui.
- Enquanto a migração não termina, o repositório mantém duas superfícies de contrato para a mesma
  cadeia, uma delas exposta na internet.
- O contador único de `base_version` por rodada torna qualquer mutação um conflito potencial para
  as demais, mesmo em etapas distintas da cadeia: é o preço de ter uma cadeia causal só.
- Guardar artefato como coluna JSON (D2) mantém o banco sem poder consultar item, código ou linha
  de boletim por SQL: relatório entre rodadas continua sendo trabalho de aplicação, e a decisão
  de normalizar fica adiada, não eliminada.
- O upload em duas etapas (D6) troca uma chamada por três — presign, PUT, associação — e a tela
  passa a ter estado intermediário que o multipart não tinha.
- A rodada sem vínculo com `projects` (D8) significa que a mesma obra pode existir dos dois lados
  sem que o sistema saiba: a ligação entre croqui e medição, se um dia for pedida, terá de ser
  desenhada como decisão própria.

## Riscos e mitigação

| Risco | Mitigação |
|---|---|
| O nome da entidade raiz ser escolhido por conveniência de implementação | `ValuationRound` entra no glossário do Valuation Context junto com este ADR, e o vocabulário proibido do ADR-0016 é critério verificável de revisão |
| O ADR descrever implementação e tirar do Builder liberdade legítima | Colunas, tabelas e paths são forma decidida; algoritmo, módulo e ordem de execução seguem fora deste documento |
| Contagem de rota herdada de documento antigo virar fato | A contagem é apurada por `grep` sobre o arquivo e declarada com o comando; o "~7 rotas" do ADR-0020 fica registrado como número que **não** descreve o estado atual |
| A migração parar no meio e deixar as duas superfícies vivas indefinidamente | A condição de remoção do modo hospedado é cumulativa e verificável, e a paridade de rota é teste, não inspeção |
| Perder o refino pago de código, hoje só no CLI | Registrado explicitamente como decisão pendente, e não como detalhe de execução |
| `apps/web` não suportar a jornada da orçamentista quando a migração chegar | A tensão com o ADR-0020 está escrita; reverter D9 exige ADR novo, não escolha de implementação |

## Rastreabilidade

- Requirements: destino declarado em [Status](../STATUS.md) ("Contexto de transição da medição
  hospedada") e no [ADR-0026](0026-medicao-hospedada-sessao-autenticada-minima.md); contrato de
  feature [F-002](../features/F-002-medicao-v1-contract/feature.md); execução em
  [F-003](../features/F-003-medicao-v1-migration/feature.md). Decisões preservadas:
  [ADR-0011](0011-oidc-portable-identity.md) (identidade OIDC portável),
  [ADR-0012](0012-contractual-ai-processing-entitlements.md) (entitlement de IA por tenant),
  [ADR-0016](0016-valuation-bounded-context.md) (contexto delimitado e vocabulário proibido),
  [ADR-0020](0020-local-homologation-server-for-valuation.md) (servidor local, que segue válido
  para a máquina do operador) e [ADR-0025](0025-homologacao-em-gcp-cloud-run.md) (ambiente que
  hospeda a ponte). A entrada na
  [matriz de rastreabilidade](../engineering/TRACEABILITY.md) é criada junto da implementação,
  quando existir verificação a citar.
- Supersedes: none
- Superseded by: none
