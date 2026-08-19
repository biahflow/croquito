# Contrato da API

Status: Accepted for MVP  
Responsável: Backend / Frontend  
Última revisão: 2026-08-18

Base path: `/v1`  
Autenticação: JWT bearer OIDC  
Content type: `application/json`, exceto upload direto ao S3.

## Metadados públicos

Estes endpoints não acessam conteúdo de cliente e podem ser usados por health
checks e geração de clientes:

- `GET /healthz`: liveness local, fora do base path versionado.
- `GET /v1/meta`: versão da API e do scene schema.
- `GET /v1/schemas/scene`: JSON Schema da cena canônica.

Os demais endpoints exigem JWT emitido por um provedor OIDC configurado. A API
valida assinatura por JWKS, `issuer` e `audience`, e deriva tenant, identidade e
papéis somente dos claims assinados.

Recusas de autenticação respondem `401` com código estável no corpo: `UNAUTHORIZED`
(sem credencial Bearer), `INVALID_TOKEN` (assinatura, issuer, audience ou forma dos
claims inválidos) e `TOKEN_WITHOUT_TENANT` (token válido de conta **sem o claim
`tenant_id`** — a conta autenticou, mas não está vinculada a nenhuma organização; o
cliente deve orientar a pessoa a procurar quem administra o tenant, e não repetir o
login, que produziria o mesmo resultado).

## Convenções

- IDs são UUIDv7.
- Timestamps são UTC ISO 8601.
- Valores geométricos retornados pela API usam metros e radianos.
- Toda resposta contém `request_id` por header.
- Erros usam `application/problem+json`.
- Comandos mutáveis aceitam `Idempotency-Key`.

## Uploads

### `POST /v1/uploads/presign`

Entrada: `filename`, `content_type`, `size_bytes`, `sha256`.  
Saída: `upload_id`, `object_key`, `url`, headers obrigatórios e `expires_at`.

`content_type` aceita dois tipos, e só eles: `application/pdf` (a prancha do croqui e a
da medição) e `application/json` (o catálogo de preços que a rodada de medição instala na
criação — [ADR-0028](../adr/0028-medicao-na-api-v1-autenticada.md) D6 tratou só da
prancha). A extensão de `filename` precisa casar com o tipo declarado: `.pdf` com tipo de
JSON, `.json` com tipo de PDF ou qualquer outra extensão devolvem
`422 INVALID_UPLOAD`. Quem consome o upload continua exigindo o que aceita —
`POST /v1/jobs` recusa upload que não seja PDF com o mesmo `422 INVALID_UPLOAD`.

Os headers incluem `Content-Type` com o tipo declarado e, quando o storage assina
checksum, `x-amz-checksum-sha256` (SHA-256 em base64). O cliente envia no PUT
exatamente os headers devolvidos, nem mais nem menos: no perfil de storage sem
checksum assinado (`CROQUITO_STORAGE_FLAVOR=gcs`, interoperabilidade XML do Cloud
Storage) o header não vem e enviá-lo faria o PUT falhar. Nesse perfil a criação do
job confere tamanho e tipo, registra o evento de auditoria
`UPLOAD_CHECKSUM_DEFERRED_TO_WORKER` e o digest continua verificado pelo worker,
que recalcula o SHA-256 dos bytes gravados antes de qualquer processamento.

O endpoint não aceita caminho S3 fornecido pelo cliente. A URL expira em até 15
minutos.

## Jobs

### `POST /v1/jobs`

Entrada: `upload_id`, `project_name`, `default_unit`.  
Saída: `job_id`, `project_id`, `status=UPLOADED`, `expires_at`.

O campo legado `external_ai_consent` permanece aceito temporariamente em `/v1`
para clientes já publicados, mas é ignorado e não deve ser enviado por novas
integrações.

Criar job valida ownership, tamanho, MIME, digest e conclusão do upload antes de
iniciar a state machine. Falha transitória de dispatch pode ser repetida com a
mesma `Idempotency-Key`.

Quando providers reais estiverem ativados no ambiente, o tenant precisa de uma
autorização contratual ativa. A API cria um snapshot imutável por job com a
referência lógica do contrato, operador que a ativou, OpenAI,
Bedrock/Anthropic, Textract, processamento global e retenção de sete dias; o
worker bloqueia chamadas externas sem esse snapshot ou após revogação do
entitlement.

## Autorização contratual de IA

### `PUT /v1/platform/tenants/{tenant_id}/ai-processing-entitlement`

Requer o papel OIDC `platform_operator`, não é exposto no front de revisão e
aceita `Idempotency-Key`. Entrada: `enabled` e, ao ativar,
`agreement_reference` (identificador lógico do contrato). A ativação ou revogação
é auditada no tenant alvo. Um `tenant_admin` não pode liberar processamento externo
por conta própria.

### `GET /v1/jobs/{job_id}`

Retorna status, etapa, `page_count`, timestamps e falha normalizada. A lista de
projetos inclui opcionalmente o último resumo de job para retomada após recarga.
Não retorna payloads de modelos.

### `DELETE /v1/jobs/{job_id}`

Revoga downloads e inicia exclusão idempotente. Retorna `202 DELETING`.

## Cena e revisão

### `GET /v1/jobs/{job_id}/scene`

Retorna a revisão corrente, entidades, medidas, constraints, issues e URLs
assinadas de preview.

### `POST /v1/jobs/{job_id}/revisions`

Entrada:

```json
{
  "base_version": 3,
  "operations": [
    {"op": "replace_measurement", "measurement_id": "...", "value": 31.95}
  ],
  "reason": "Confirmado no croqui"
}
```

Operações são uma allowlist; cliente não substitui um scene graph inteiro. Se a
versão mudou, retorna `409 REVISION_CONFLICT` com a versão atual.

## Sessão de revisão de cotas

O worker persiste snapshots imutáveis de `ReviewPacket` por job: leituras e seus
textos brutos, regiões de evidência, digest da imagem, candidatos observacionais,
associações explicitamente selecionadas, referências privadas de preview e a
configuração determinística do solver. Conteúdo de evidência nunca vai para logs;
previews são retornados apenas como URLs assinadas curtas depois da checagem de
tenant.

### `GET /v1/jobs/{job_id}/review`

Retorna o snapshot de revisão atual do job pertencente ao tenant do JWT:
`review_id`, `version`, `packet`, candidatos de associação, associações
selecionadas, blockers, issues, cena rascunho quando existir e URLs de preview.
O endpoint retorna `409 JOB_NOT_READY` enquanto o worker ainda não persistiu o
pacote e `404 NOT_FOUND` para um job de outro tenant.

Quando disponíveis, a resposta também contém o `VisionProposalSet` do mesmo
digest/página, decisões imutáveis de propostas e a calibração corrente. Geometrias
de proposta permanecem em `source_image_pixels`; imagens e URLs privadas não são
incluídas nesse objeto.

`required_criteria` lista os critérios de escopo declarados para o caso quando a
evidência foi carregada, como pares `{code, text}`:

```json
{
  "required_criteria": [
    {
      "code": "ACC_GUA_001",
      "text": "Perímetro, linha central, círculo, áreas e gols são entidades CAD limpas."
    }
  ]
}
```

`text` é o critério escrito, para a tela mostrar a frase e não só o código. Revisão
semeada antes de o texto viajar responde com a frase padrão "Critério do caso ainda não
está coberto pela cena métrica."; nenhuma linha é migrada retroativamente
([ADR-0017](../adr/0017-per-criterion-coverage-declaration-and-trace-parity.md)).

Essa lista é a única fonte do que pode ser declarado na aprovação: o cliente não infere
política a partir de `blockers`, que já é uma lista achatada de pendências de origens
diferentes. Issue crítica com status `accepted` ou `resolved` não aparece em `blockers`.

### `POST /v1/jobs/{job_id}/review/decisions`

Entrada:

```json
{
  "base_version": 1,
  "decisions": [
    {
      "reading_id": "rd_...",
      "action": "confirm",
      "justification": "Conferido na evidência protegida.",
      "association_proposal_id": "vp_..."
    }
  ]
}
```

As ações permitidas são `confirm`, `correct` e `reject`. Confirmar ou corrigir
exige selecionar um candidato pertencente à mesma leitura; essa seleção é
evidência explícita, não uma promoção automática da proposta em pixels. A
exceção declarada é `"annotation": true` — a leitura é anotação da folha (uma
lembrança escrita, não a medida de um elemento): confirma **sem**
`association_proposal_id`, nunca entra no mapa de associações e segue como
leitura confirmada não aplicada (aviso, nunca restrição de geometria). Anotação
acompanhada de associação é contradição e recusa com 422. O
payload não aceita `tenant_id`, revisor, papel ou timestamp: todos são derivados
do JWT e do relógio do servidor. A operação requer `Idempotency-Key`, cria uma
nova revisão de leitura e retorna `409 REVISION_CONFLICT` se `base_version` não
for a atual. Uma leitura já decidida não pode ser sobrescrita **por este comando**
(`422 READING_ALREADY_DECIDED`); a correção é a retificação declarada descrita
abaixo.

Quando a configuração do job exigir a família retangular, somente leituras
confirmadas **e** associações explícitas chegam ao solver. A cena resultante é
uma `SceneRevision` nova, métrica e não aprovada; blockers críticos pendentes do
caso continuam nela e impedem aprovação, exportação e DXF.

### `POST /v1/jobs/{job_id}/review/rectifications`

Corrige decisões **já registradas**. É um ato humano novo, não uma edição: a decisão
anterior permanece na revisão em que foi tomada
([ADR-0022](../adr/0022-declared-rectification-of-review-decisions.md)).

```json
{
  "base_version": 3,
  "rectifications": [
    {
      "reading_id": "rd_...",
      "action": "confirm",
      "rectifies_decision_id": "hd_...",
      "justification": "O 12,00 é de outra cota; a largura do campo é 25,90.",
      "association_proposal_id": "vp_...",
      "raw_text": "25,90",
      "value_si": "25.90",
      "unit": "m",
      "kind": "width"
    }
  ]
}
```

As ações são `confirm` e `reject` — não existe `correct`: o que muda em relação ao
registro anterior viaja nos mesmos campos da decisão. `rectifies_decision_id` cita
nominalmente a decisão vigente da leitura e `justification` é obrigatória. Revisor,
papel e horário vêm do JWT e do relógio do servidor. Exige papel profissional elegível,
`Idempotency-Key` e de 1 a 50 correções (a tela envia uma por vez).

A **associação é sempre redeclarada**: valem as mesmas regras do comando de decisão —
confirmar exige `association_proposal_id` pertencente à leitura ou a declaração
`"annotation": true`, e rejeitar remove a leitura do mapa de associações. Nada é
herdado em silêncio da decisão corrigida.

O comando cria uma revisão de leitura nova (`version + 1`), copia o aceite de traçado
verbatim, revalida a calibração e, quando o job tem pedido de solver, re-resolve a cena
pelo mesmo caminho do comando de decisão. A leitura **nunca volta a `proposed`**.

Cascata de invalidação para frente: se a cena mais recente ainda se apoia na decisão
corrigida — entidade ou medida cuja `provenance` cita o `decision_id` antigo e que não
foi recomputada neste request —, uma `SceneRevision` nova e **não aprovada** é criada
com a geometria intacta mais a issue crítica `READING_DECISION_SUPERSEDED`, listando as
entidades afetadas. O export fica bloqueado até o traçado daquela parte ser refeito.
Aprovações e pacotes já publicados não são tocados; a cena anterior deixa de ser a
corrente e aprová-la passa a responder `409 REVISION_CONFLICT`. Um request produz no
máximo uma cena nova, mesmo quando `CALIBRATION_SUPERSEDED` ocorre junto.

A resposta é a mesma de `GET /v1/jobs/{job_id}/review`; o impacto viaja em `issues` e
`blockers`. Erros: `422 READING_NOT_DECIDED` (leitura sem decisão — use o comando de
decisão), `409 RECTIFICATION_TARGET_STALE` (o alvo não é a decisão vigente),
`422 RECTIFICATION_ALREADY_APPLIED` (a correção não muda nada), `409 REVISION_CONFLICT`,
`422 DOMAIN_VALIDATION_FAILED`, `403 FORBIDDEN`, `404 NOT_FOUND` e
`409 JOB_NOT_READY`.

### Calibração e decisões de proposta

`POST /v1/jobs/{job_id}/review/calibration` exige `base_review_version`,
`base_scene_version` e exatamente dois anchors `{proposal_id, entity_id,
reversed}`. Cada anchor liga uma proposta `line` a uma entidade `line`
`exact`/`derived`; linhas paralelas, degeneradas, divergentes ou ausentes falham
com `422 CALIBRATION_INVALID`. A API calcula o transform de similaridade
pixel→metro, registra escala, rotação, translação e resíduo na nova revisão de
leitura. Somente papel profissional elegível pode executar o comando.

`POST /v1/jobs/{job_id}/review/proposals` recebe `base_review_version`,
`base_scene_version`, `proposal_id`, `action=accept|reject`, justificativa e,
para aceite, `calibration_id`. Aceitar requer a calibração corrente, cria nova
revisão de leitura e nova `SceneRevision`; linha, círculo e contorno tornam-se
`line`, `circle` e `polyline` fechada `approximate` no layer `APROXIMADO`.
Rejeitar cria somente a revisão/auditoria. Toda proposta recebe no máximo uma
decisão; `CALIBRATION_REQUIRED`, `CALIBRATION_STALE` e
`PROPOSAL_ALREADY_DECIDED` falham fechados. Ambos os comandos exigem
`Idempotency-Key` e retornam `409 REVISION_CONFLICT` quando qualquer versão-base
não for a atual.

### `POST /v1/jobs/{job_id}/review/proposals/batch`

Mesma decisão para muitas propostas: traçar um croqui inteiro proposta a proposta é
inviável. Entrada: `base_review_version`, `base_scene_version`, `proposal_ids` (1 a 500,
sem repetição), `action=accept|reject`, `justification` e, para aceite,
`calibration_id`. A justificativa é única por lote e vale para cada proposta nele.

O lote é atômico: uma revisão de leitura e, no aceite, uma única cena nova com todas as
entidades `approximate` no layer `APROXIMADO`. Qualquer proposta que falhe recusa o lote
inteiro — meia cena traçada seria pior do que nenhuma. Rejeição não aceita
`calibration_id`. A resposta é a mesma de `GET /v1/jobs/{job_id}/review`.

Erros: `409 PROPOSALS_NOT_READY` sem snapshot de propostas, `409 REVISION_CONFLICT` para
versão-base vencida, `422 DOMAIN_VALIDATION_FAILED` para proposta repetida, fora do
snapshot ou rejeição com calibração, `422 PROPOSAL_ALREADY_DECIDED`,
`422 CALIBRATION_REQUIRED`, `409 CALIBRATION_STALE` e `422 CALIBRATION_INVALID`.

## Traçado em lote

O traçado (`solve_trace`) resolve topologia, bandas ortogonais e restrições de cota; é
trabalho pesado e roda sempre no worker, por comando idempotente na mesma fila de
processamento ([ADR-0015](../adr/0015-trace-solve-worker-and-registry.md)). A API valida,
persiste a intenção, enfileira e devolve `202`; o cliente acompanha por polling. Os
comandos `solve-trace`/`trace-export` da CLI continuam válidos e usam o mesmo motor.

### `POST /v1/jobs/{job_id}/trace-solves`

Exige papel profissional e `Idempotency-Key`. O corpo é o aceite em lote descrito no
[Trace Stage](TRACE_STAGE.md), sem identidade e sem relógio: `reviewer_id`,
`reviewer_role`, `decided_at` e `acceptance_id` são derivados do JWT e do servidor e não
podem ser enviados nem escolhidos.

```json
{
  "base_review_version": 2,
  "base_scene_version": 1,
  "proposal_ids": ["vp_1111111111111111", "vp_2222222222222222"],
  "hatch_proposal_ids": [],
  "keep_apart_pairs": [
    ["vp_1111111111111111", "vp_2222222222222222"],
    {"first": "vp_1111111111111111", "second": "vp_2222222222222222", "axis": "x"}
  ],
  "unlabelled_proposal_ids": [],
  "freeform_proposal_ids": [],
  "detail_groups": [
    {"detail_id": "A", "title": "Painel de alambrado", "proposal_ids": [], "mode": "solve"}
  ],
  "associations": {
    "rd_1111111111111111": "vp_1111111111111111",
    "rd_2222222222222222": ["vp_1111111111111111", "vp_2222222222222222"],
    "rd_3333333333333333": {
      "proposal_id": "vp_2222222222222222",
      "spans_px": [[[10, 20], [10, 60]]]
    }
  },
  "note_associations": {"rd_4444444444444444": "legenda:vp_1111111111111111"},
  "derived_dimensions": [
    {"proposal_id": "vp_2222222222222222", "near_x_px": 40, "near_y_px": 10}
  ],
  "dimension_texts": {"rd_5555555555555555": "1,0 x 2,05"},
  "note": "Traçado conferido contra a evidência protegida.",
  "title": "CAMPO GUAXINDIBA",
  "feature_id": "tracado"
}
```

`base_scene_version` é omitido (ou `null`) quando o job ainda não tem cena: o traçado
pode ser a primeira geometria métrica do job.

As associações efetivas são as `selected_associations` da revisão corrente
**sobrepostas** pelo campo `associations` do corpo: o corpo vence por `reading_id` e as
demais associações confirmadas continuam valendo. Os três formatos de alvo são os do
traçado — um elemento, um par de elementos (vão entre dois) ou
`{proposal_id, spans_px}` (vão declarado entre duas arestas do mesmo elemento).

`keep_apart_pairs` aceita as duas formas do traçado: o par `["vp_a", "vp_b"]` separa as
faixas nos dois eixos e `{"first", "second", "axis": "x"|"y"|null}` separa só no eixo
declarado ([Trace Stage](TRACE_STAGE.md), controle 3). As duas impedem igualmente a fusão
de vértices.

Validações do request path, todas baratas: as versões-base precisam ser as atuais
(`409 REVISION_CONFLICT`); toda proposta citada — no aceite, nas listas auxiliares, nos
grupos de detalhe, nas associações, nas notas e nas cotas derivadas — precisa existir no
snapshot de propostas da revisão (`422 TRACE_PROPOSAL_UNKNOWN`); e o aceite precisa ser
internamente consistente (`422 TRACE_ACCEPTANCE_INVALID`, com a mensagem de domínio do
contrato, nunca os valores recusados). Geometria não é resolvida aqui.

Resposta `202` com o registro recém-criado: `trace_solve_id`, `status="QUEUED"` e
`acceptance_id`. Repetir a mesma `Idempotency-Key` com o mesmo corpo devolve o mesmo
registro sem enfileirar de novo. Erros adicionais: `404 NOT_FOUND` para job de outro
tenant, `409 JOB_NOT_READY` sem pacote de revisão, `409 PROPOSALS_NOT_READY` sem snapshot
de propostas, `403 FORBIDDEN` sem papel profissional e `503 PROCESSING_UNAVAILABLE`
quando a fila recusa o comando — nesse caso o registro permanece `QUEUED` e uma nova
chamada reenfileira.

### `GET /v1/jobs/{job_id}/trace-solves/{trace_solve_id}`

Polling do ciclo `QUEUED → RUNNING → COMPLETED|FAILED`. Retorna `status`, `solve_status`
(`solved_unapproved`, `review_required` ou `conflict`), `blockers`,
`unapplied_reading_ids`, `residual_summary`, `exact_entity_count`,
`approximate_entity_count`, `note_count`, `scale_m_per_px`, `detail_group_scales`,
`result_scene_revision_id`, `result_scene_version`, `result_review_version` e
`failure_code`. Registro de outro tenant retorna `404`.

`blockers` são os códigos estáveis do traçado (por exemplo
`TRACE_HUMAN_CONFIRMATION_REQUIRED:<reading_id>`,
`TRACE_ASSOCIATION_CROSSES_DETAIL_GROUP:<reading_id>`,
`DETAIL_GROUP_WITHOUT_APPLIED_READING:<detail_id>`); saída bruta de solver nunca volta ao
cliente. `residual_summary` traz `count`, `failed_count` e o pior resíduo
(`worst_code`, `worst_absolute_error_m`, `worst_tolerance_m`) — a lista completa fica na
cena resolvida, não no registro.

Desfechos:

- `solved_unapproved` cria uma `SceneRevision` nova, métrica e **não aprovada**, mais uma
  revisão de leitura que registra o aceite. Os ids vêm em `result_scene_revision_id` e
  nas versões correspondentes; a cena passa a ser a corrente em
  `GET /v1/jobs/{job_id}/scene`.
  A cena traçada carrega os critérios de escopo da revisão de leitura como issues críticas
  abertas, exatamente como a cena do solver retangular: sem declaração na aprovação, o
  export continua bloqueado
  ([ADR-0017](../adr/0017-per-criterion-coverage-declaration-and-trace-parity.md)).
- `review_required` registra blockers e leituras não aplicadas sem criar revisão alguma.
- `conflict` com `failure_code="REVISION_MOVED"` significa que a revisão de leitura ou a
  cena avançaram entre o aceite e a execução: o resultado é consultável, não um erro de
  servidor, e o traçado precisa ser refeito sobre as versões novas.
- `FAILED` com `failure_code` registra falha determinística do estágio; a mensagem
  original nunca é exposta nem registrada.

## Sessão de conversa da revisão

O profissional pergunta sobre a folha em revisão e recebe uma resposta **observacional**
com rascunhos tipados dos atos que ele pode assinar
([ADR-0023](../adr/0023-review-chat-as-an-observational-agent.md)). O agente não submete
nada: cada rascunho é o corpo de um endpoint desta página, e só vale depois do comando
humano correspondente.

Chamar o modelo é trabalho de worker, como export e traçado: a API valida, persiste a
pergunta, enfileira e devolve `202`; o cliente acompanha por polling. Pergunta e resposta
ficam no banco e nunca em log ou auditoria — o registro de auditoria leva apenas ids.

### `POST /v1/jobs/{job_id}/chat-sessions`

Abre uma conversa. Exige papel profissional e `Idempotency-Key`; o corpo é `{}` — a
revisão-base é fixada pelo servidor na revisão de leitura corrente e **não** acompanha o
job depois disso: uma conversa que andasse com a revisão responderia sobre uma folha
diferente da que gerou a pergunta.

Resposta `201` com `chat_session_id`, `status="OPEN"`, `base_review_revision_id`,
`base_review_version`, `created_at` e `turns` (vazio). Erros: `403 FORBIDDEN` sem papel
profissional, `404 NOT_FOUND` para job de outro tenant e `409 JOB_NOT_READY` enquanto não
houver pacote de revisão. Quando o ambiente tem providers reais ativados, vale a mesma
autorização contratual do job (`403 AI_PROCESSING_NOT_AUTHORIZED`); com providers
desligados nenhuma autorização é exigida, porque nada sai da máquina.

### `POST /v1/jobs/{job_id}/chat-sessions/{session_id}/turns`

```json
{
  "question": "Essa cota mede a borda do patamar ou a mureta?",
  "anchors": {
    "reading_ids": ["rd_1111111111111111"],
    "proposal_ids": ["vp_1111111111111111"]
  }
}
```

`question` tem de 3 a 500 caracteres. `anchors` é o que o profissional apontou — nada é
inferido por proximidade — e cada id precisa existir no pacote ou no snapshot de propostas
da **revisão-base da conversa** (`422 CHAT_ANCHOR_UNKNOWN`). Exige papel profissional e
`Idempotency-Key`.

A sessão precisa estar aberta (`409 CHAT_SESSION_CLOSED`) e **um turno por vez** pode estar
em voo — `QUEUED` ou `RUNNING` — por sessão (`409 CHAT_TURN_PENDING`): duas respostas sem
ordem entre si não seriam uma conversa. O turno é persistido `QUEUED` com
`sequence = último + 1`, commitado, e só então o comando `answer_chat_turn` é publicado.

Resposta `202` com o turno. Erros adicionais: `404 NOT_FOUND` para conversa de outro tenant
ou de outro job e `503 PROCESSING_UNAVAILABLE` quando a fila recusa o comando — nesse caso
o turno permanece `QUEUED` e uma nova chamada reenfileira.

### `GET /v1/jobs/{job_id}/chat-sessions/{session_id}`

Polling da conversa: a sessão mais os turnos ordenados por `sequence`. Cada turno traz
`status` (`QUEUED → RUNNING → COMPLETED|FAILED`), `question`, `anchors`, `failure_code` e,
quando respondido, `answer`:

```json
{
  "answer_kind": "answer",
  "answer_text": "A cota está escrita ao lado do elemento que você apontou.",
  "evidence_notes": ["Leitura e elemento vieram do contexto enviado."],
  "open_question": null,
  "proposed_acts": [
    {
      "act": "reading_decision",
      "reading_id": "rd_1111111111111111",
      "action": "confirm",
      "association_proposal_id": "vp_1111111111111111",
      "annotation": false,
      "justification_draft": "Cota conferida contra o recorte da evidência."
    }
  ]
}
```

O schema completo, as cinco formas de rascunho e as regras estão em
[Prompt Contracts](../ai/PROMPT_CONTRACTS.md). `answer_kind="uncertain"` sempre vem com
`open_question` preenchida: "ainda não sei" é saída de contrato, não falha.

`failure_code` traz códigos estáveis do estágio, nunca a mensagem original:
`CHAT_ACT_UNKNOWN_REFERENCE` (algum id do rascunho não existe no snapshot da revisão-base —
o turno inteiro é recusado e nenhuma resposta é gravada), `CHAT_PROVIDER_UNAVAILABLE`
(nenhuma via de modelo disponível para o turno) e `CHAT_ANSWER_FAILED` (falha determinística
do estágio).

### `GET /v1/jobs/{job_id}/chat-sessions`

Lista magra das conversas do job: `chat_session_id`, `status`, `created_at` e `turn_count`.
Job de outro tenant retorna `404`.

### `POST /v1/jobs/{job_id}/regions/{region_id}/reanalyze`

Inicia workflow regional e retorna `202` com `analysis_id`. Limite e custo são
aplicados por tenant.

### `POST /v1/jobs/{job_id}/approve`

O corpo espelha o contrato `SceneApproval`: cada verificação é declarada, nunca
inferida. O JWT determina `tenant_id`, identidade e papel profissional do aprovador;
o cliente não envia nem pode escolher esses campos, e `decided_at` vem do relógio do
servidor. Exige `Idempotency-Key`; a repetição devolve a mesma revisão aprovada.

Exemplo de entrada:

```json
{
  "revision_id": "0198f0da-9d75-7000-8000-000000000001",
  "accepted_approximations": ["0198f0da-9d75-7000-8000-0000000000a1"],
  "covered_criteria": ["ACC_GUA_002"],
  "acknowledged_criteria": ["ACC_GUA_001"],
  "source_evidence_checked": true,
  "geometry_checked": true,
  "limitations_acknowledged": true,
  "statement": "Revisei evidências, geometria e limitações desta revisão."
}
```

Os três campos de verificação são `Literal[true]`: qualquer outro valor é `422`.
`statement` tem de 20 a 500 caracteres.

A declaração por critério de **escopo** tem dois atos distintos, conforme o
[ADR-0014](../adr/0014-scope-criteria-acknowledgement-at-approval.md) e o
[ADR-0017](../adr/0017-per-criterion-coverage-declaration-and-trace-parity.md):

| Campo | Significado | Status da issue |
|---|---|---|
| `covered_criteria` | A cena que está sendo aprovada cobre o critério | `resolved` |
| `acknowledged_criteria` | O critério segue pendente e o profissional assina assim mesmo | `accepted` |

Só é aceito um código presente em `required_criteria` da revisão de leitura corrente;
qualquer outro retorna `422 CRITERION_NOT_ACKNOWLEDGEABLE`. O mesmo código nos dois
conjuntos retorna `422 CRITERION_DECLARATION_CONFLICT`. Blockers de geometria — resíduo
numérico, cota incompatível, aproximação não aceita, calibração obsoleta — nunca são
declaráveis por nenhum dos dois atos. Critério exigido que não recebe declaração alguma
permanece `open` e a aprovação falha com `OPEN_CRITICAL_ISSUE:<code>`.

Os dois conjuntos são gravados ordenados e viajam **separados** no `aprovacao.json`
dentro do pacote CAD: quem recebe o desenho lê o que a cena cobre e o que ela deixou
pendente sem interpretar um campo só.

Retorna `422` se houver issue crítica aberta ou `unresolved` relevante,
`422 DOMAIN_VALIDATION_FAILED` se `accepted_approximations` citar entidade inexistente
ou não aproximada, `403 FORBIDDEN` quando o papel não puder aprovar tecnicamente e
`409 REVISION_CONFLICT` ao reaprovar uma revisão aprovada ou uma revisão superada.

A resposta retorna a nova revisão aprovada. A `SceneApproval` completa é persistida e
serializada no pacote CAD. Nunca retorna ou aceita o papel profissional no payload.

## Medição de obra

A medição de obra é um contexto delimitado próprio
([ADR-0016](../adr/0016-valuation-bounded-context.md)) e não pende de `job`: a raiz é a
**rodada** (`ValuationRound`), que leva uma prancha do levantamento de quantitativos ao
boletim e ao dossiê do aditivo.

Regras que valem em toda a seção:

- Papel exigido: `orcamentista`. Quem revisa takeoff e confirma código não é quem aprova
  cena; papel ausente devolve `403 FORBIDDEN`.
- `tenant_id` vem do JWT. Rodada de outro tenant devolve `404 NOT_FOUND`.
- Toda mutação exige `Idempotency-Key` e `base_version`; versão divergente devolve
  `409 REVISION_CONFLICT`. A versão é **da rodada**, uma só para toda a cadeia.
- O carimbo de identidade é sempre do servidor: o corpo recusa `reviewer_id`,
  `reviewer_role`, `decided_at` e `decision_id`.
- Invariante de domínio de `packages/valuation` devolve `422 DOMAIN_VALIDATION_FAILED` com o
  código de domínio (`TAKEOFF_*`, `CALC_*`, `ASSIGNMENT_*`, `AMENDMENT_DOSSIER_*`,
  `CATALOG_*`) em `details`. A API não republica o vocabulário do domínio.

### `POST /v1/valuation-rounds`

Entrada: `worksite_key`, `worksite_name`, `catalog_upload_id`, `reference_label`,
`period_number`, `address` (opcional), `contract_label` (opcional).  
Saída: `round_id`, `version=1`, `status`, `created_at`.

`worksite_key` segue `WORKSITE_KEY_PATTERN` (`^[a-z0-9][a-z0-9-]{2,63}$`), o mesmo padrão
que o domínio exige de `WorksiteBulletin`: a chave é imutável na rodada e aceitá-la livre
aqui faria uma rodada nascer válida e só quebrar em `POST .../calc`, dezenas de decisões
depois. `period_number`, `address` e `contract_label` são atributos da RODADA — nenhum
deles viaja em `POST .../calc`, que lê todos da rodada.

O catálogo de preços é instalado na criação e é imutável na rodada: trocar de catálogo é
abrir rodada nova. Erros: `422 DOMAIN_VALIDATION_FAILED` para catálogo ilegível ou inválido.

### `GET /v1/valuation-rounds`

Lista as rodadas do tenant, com cursor opaco. Devolve `round_id`, `worksite_key`,
`reference_label`, `version`, `status` e etapa corrente da cadeia.

### `GET /v1/valuation-rounds/{round_id}`

Estado da rodada: `version`, catálogo instalado, etapas (prancha, extração, takeoff, códigos,
boletim, dossiê) por presença e digest de artefato, e o estado da extração paga
(`idle`, `queued`, `running`, `done`, `failed`). É por aqui que o cliente acompanha o
comando assíncrono da extração.

### `POST /v1/valuation-rounds/{round_id}/plate`

Entrada: `upload_id`, `base_version`. O PDF sobe por `POST /v1/uploads/presign` e nunca em
JSON. Uma rodada tem no máximo uma prancha: segunda chamada devolve
`409 ROUND_PLATE_ALREADY_PRESENT`.

Erros: `422 INVALID_UPLOAD` quando o objeto não é PDF legível de prancha,
`409 REVISION_CONFLICT` por versão movida.

### `GET /v1/valuation-rounds/{round_id}/plate`

Retorna metadados da prancha e `image_url`: URL assinada de curta duração para o PNG
promovido, sob o prefixo do tenant, nunca registrada em log nem em auditoria. Prancha ainda
não ingerida devolve `409 ROUND_STAGE_NOT_READY`.

### `POST /v1/valuation-rounds/{round_id}/plate/extractions`

Enfileira a extração paga da legenda e retorna `202` com `extraction_id` e `status`. Exige
`Idempotency-Key` e `base_version`. Extração já em voo na rodada devolve
`409 EXTRACTION_IN_PROGRESS`.

A extração é chamada paga de provider: vale a autorização contratual por tenant
([ADR-0012](../adr/0012-contractual-ai-processing-entitlements.md)),
`403 AI_PROCESSING_NOT_AUTHORIZED` sem entitlement e `503 PROVIDER_UNAVAILABLE` quando o
ambiente não tem provider configurado. Fila indisponível devolve
`503 PROCESSING_UNAVAILABLE`, com o comando repetível. Resposta bruta de provider nunca
volta ao cliente; o lineage (modelo, tokens, custo) fica no estado da rodada.

### `GET /v1/valuation-rounds/{round_id}/takeoff`

Retorna o `TakeoffPacket` da rodada, com a âncora de evidência por item e o digest do pacote.
Sem extração publicada devolve `409 ROUND_STAGE_NOT_READY`.

### `GET /v1/valuation-rounds/{round_id}/takeoff/overlay`

Retorna `image_url` assinada do overlay das âncoras sobre a prancha, no mesmo regime da
imagem da prancha, mais `stale` e o digest do pacote que originou o desenho
([ADR-0030](../adr/0030-overlay-do-takeoff-reconstruido-na-fila.md)).

Overlay vencido devolve `200` com a marca, nunca erro: o desenho anterior continua sendo a
única visão de onde cada número foi lido, e esconder a divergência é pior que declará-la.

### `POST /v1/valuation-rounds/{round_id}/takeoff/decisions`

Entrada: `base_version` e uma decisão do orçamentista sobre um item — `item_id`,
`action` (`confirm` ou `reject`), `quantity`, `unit`, `note`, `item_note`. `quantity` viaja
como **texto**, porque quantidade é `Decimal` exato neste contexto e um `float` de JSON já
teria perdido a escala escrita.

Decisão do orçamentista é imutável: item já confirmado ou rejeitado devolve
`422 DOMAIN_VALIDATION_FAILED` com `TAKEOFF_ITEM_ALREADY_REVIEWED` em `details`. Correção de
decisão é ato declarado, não sobrescrita.

A resposta traz a rodada em versão nova, com o pacote regravado. O overlay é reconstruído
**fora do request path**, por comando de fila
([ADR-0030](../adr/0030-overlay-do-takeoff-reconstruido-na-fila.md)), e até o worker
publicá-lo o overlay corrente fica marcado como vencido. Fila indisponível não derruba a
decisão já gravada: o comando é repetível e a resposta continua `200`.

### `GET /v1/valuation-rounds/{round_id}/code-suggestions`

Shortlist determinística de código SCO por item confirmado
([ADR-0021](../adr/0021-hybrid-sco-code-retrieval.md)) — observação, nunca decisão. Revisão de
takeoff incompleta devolve `409 TAKEOFF_REVIEW_INCOMPLETE`; rodada sem catálogo devolve
`409 CATALOG_REQUIRED`.

### `POST /v1/valuation-rounds/{round_id}/code-suggestions/recompute`

Recalcula a shortlist. Exige `Idempotency-Key` e `base_version`. Shortlist já refinada por
modelo pago não é recalculada por caminho determinístico:
`409 SUGGESTIONS_ALREADY_REFINED`.

### `GET /v1/valuation-rounds/{round_id}/catalog/search`

Busca no catálogo instalado. Parâmetros: `q`, `limit`, `arm`. Consulta sem termo utilizável
devolve `422 CATALOG_QUERY_EMPTY`; rodada sem catálogo, `409 CATALOG_REQUIRED`.

`arm=lexical` é o padrão. `arm=hybrid` é braço PAGO e passa pelo mesmo portão da extração:
sem autorização contratual do tenant, `403 AI_PROCESSING_NOT_AUTHORIZED`
([ADR-0012](../adr/0012-contractual-ai-processing-entitlements.md)). Com entitlement, a
resposta ainda é `503 PROVIDER_UNAVAILABLE` — o braço semântico depende de índice de
embeddings publicado na rodada e nenhuma rota de `/v1` publica esse índice hoje. Isso é
estado honesto, não falha: a busca nunca degrada em silêncio para o léxico fingindo ser
híbrida.

### `GET /v1/valuation-rounds/{round_id}/code-assignments`

Retorna o `CodeAssignmentSet` corrente e os itens confirmados ainda sem decisão de código.

### `POST /v1/valuation-rounds/{round_id}/code-assignments/decisions`

Entrada: `base_version`, `item_id`, `action` (`confirm` ou `reject`), `code` e `note`.
Confirmação exige `code`; rejeição exige justificativa e recusa `code`. Item não confirmado no
takeoff, código fora do catálogo instalado, item já decidido ou unidade incompatível sem nota
devolvem `422 DOMAIN_VALIDATION_FAILED` com o código `ASSIGNMENT_*` correspondente em
`details`.

### `POST /v1/valuation-rounds/{round_id}/calc`

Entrada: **só** `base_version`. `worksite_key`, `worksite_name`, `period_number`,
`reference_label`, `address` e `contract_label` são atributos da rodada, recebidos em
`POST /v1/valuation-rounds`, e não voltam a viajar aqui — quem os quiser mudar abre rodada
nova.

Constrói o boletim e a memória de cálculo a partir do takeoff confirmado e das confirmações
de código. Exige `Idempotency-Key` e `base_version`, com `409 REVISION_CONFLICT` para
versão divergente. Não aprova nada: aprovação nominal é ato próprio e não pertence a esta
rota. Confirmação de código pendente devolve `422 DOMAIN_VALIDATION_FAILED` com
`CALC_ASSIGNMENT_MISSING`.

### `GET /v1/valuation-rounds/{round_id}/bulletin`

Retorna o boletim com totais **recomputados** na leitura, nunca lidos como estavam gravados.
Boletim ainda não construído devolve `409 ROUND_STAGE_NOT_READY`.

### `POST /v1/valuation-rounds/{round_id}/amendment-dossier`

Entrada: **só** `base_version`, espelho de `POST .../calc`: o dossiê nasce dos mesmos dois
artefatos-base do boletim e não recebe rótulo próprio.

Constrói o dossiê do aditivo com os itens confirmados cujo código foi rejeitado, com a
justificativa humana ([ADR-0027](../adr/0027-price-source-provenance-and-bid-boundary.md)). O
dossiê não carrega campo de preço por construção. Exige `Idempotency-Key` e `base_version`,
com `409 REVISION_CONFLICT` para versão divergente. Decisão de código pendente devolve
`422 DOMAIN_VALIDATION_FAILED` com `AMENDMENT_DOSSIER_ASSIGNMENTS_INCOMPLETE`.

### `GET /v1/valuation-rounds/{round_id}/amendment-dossier`

Retorna o dossiê revalidado. Dossiê não construído devolve `409 ROUND_STAGE_NOT_READY`.

## Exports

O pacote CAD é sempre construído fora do request path, por comando idempotente no
worker ([ADR-0013](../adr/0013-export-worker-and-artifact-registry.md)).

### `POST /v1/jobs/{job_id}/exports`

Entrada: `revision_id`, `format="dxf"`. Exige papel profissional e `Idempotency-Key`.
A revisão precisa estar aprovada e ter `ApprovalRecord`; o servidor revalida
`export_errors()` antes de enfileirar. Retorna `202` com `export_id` e `status`.

Uma revisão aprovada tem no máximo um artefato por formato: chamadas repetidas, mesmo
com `Idempotency-Key` diferente, devolvem o mesmo `export_id`. Um artefato `COMPLETED`
não é reenfileirado; `QUEUED` ou `FAILED` são reenfileirados.

Erros: `404 NOT_FOUND` para job ou revisão de outro tenant,
`422 SCENE_NOT_APPROVED` para cena não aprovada, `422 DOMAIN_VALIDATION_FAILED` quando
a cena deixou de ser exportável e `503 PROCESSING_UNAVAILABLE` quando a fila recusa o
comando — nesse caso o artefato permanece `QUEUED` e uma nova chamada reenfileira.

### `GET /v1/jobs/{job_id}/exports/{export_id}`

Retorna `status`, `audit_status`, `dxf_sha256`, `failure_code` e `audit_errors`.
`package_url` é uma URL assinada de curta duração devolvida **somente** quando o status
é `COMPLETED` e a chave está sob o prefixo do tenant. A URL nunca é registrada em log
nem em auditoria. Artefato de outro tenant retorna `404`.

## Problem details

```json
{
  "type": "https://croquito/errors/revision-conflict",
  "title": "Revision conflict",
  "status": 409,
  "code": "REVISION_CONFLICT",
  "detail": "A newer revision exists.",
  "request_id": "...",
  "retryable": false
}
```

## Códigos obrigatórios

`INVALID_UPLOAD`, `PDF_UNREADABLE`, `LIMIT_EXCEEDED`, `PROCESSING_UNAVAILABLE`, `JOB_NOT_READY`,
`REVISION_CONFLICT`, `UNRESOLVED_GEOMETRY`, `PROVIDER_UNAVAILABLE`,
`EXPORT_AUDIT_FAILED`, `CALIBRATION_INVALID`, `CALIBRATION_REQUIRED`,
`CALIBRATION_STALE`, `PROPOSAL_ALREADY_DECIDED`, `PROPOSALS_NOT_READY`,
`FORBIDDEN`, `NOT_FOUND`, `AI_PROCESSING_NOT_AUTHORIZED`,
`AGREEMENT_REFERENCE_REQUIRED`, `SCENE_NOT_APPROVED`,
`CRITERION_NOT_ACKNOWLEDGEABLE`, `CRITERION_DECLARATION_CONFLICT`,
`DOMAIN_VALIDATION_FAILED`,
`TRACE_PROPOSAL_UNKNOWN`, `TRACE_ACCEPTANCE_INVALID`,
`READING_ALREADY_DECIDED`, `READING_NOT_DECIDED`,
`RECTIFICATION_TARGET_STALE`, `RECTIFICATION_ALREADY_APPLIED`,
`CHAT_SESSION_CLOSED`, `CHAT_TURN_PENDING`, `CHAT_ANCHOR_UNKNOWN`,
`IDEMPOTENCY_KEY_REUSED`,
`ROUND_STAGE_NOT_READY`, `ROUND_PLATE_ALREADY_PRESENT`, `EXTRACTION_IN_PROGRESS`,
`SUGGESTIONS_ALREADY_REFINED`, `TAKEOFF_REVIEW_INCOMPLETE`, `CATALOG_QUERY_EMPTY`,
`CATALOG_REQUIRED`.

Os códigos de invariante de `packages/valuation` (`TAKEOFF_*`, `CALC_*`, `ASSIGNMENT_*`,
`AMENDMENT_DOSSIER_*`, `CATALOG_*`) não são códigos de API: viajam em `details` do
`DOMAIN_VALIDATION_FAILED`.

## Paginação e limites

- Listas usam cursor opaco.
- Limites exatos são configuração operacional e retornados no erro.
- A API nunca aceita PDF base64 em JSON.

## Compatibilidade

- Campos aditivos não quebram `/v1`.
- Remoção ou mudança semântica exige `/v2` ou período de migração.
- OpenAPI gerado deve ser comparado em CI para detectar breaking changes. O snapshot
  versionado vive em `tests/api/openapi.snapshot.json`, comparado contra o documento gerado
  por `tests/api/test_openapi_contract.py`. O mesmo teste compara a superfície `/v1`
  exposta com esta página. Mudança intencional na superfície da API se atualiza com
  `make openapi-snapshot`, cujo diff deve ser revisado antes de commitar.
