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

### `GET /v1/me`

Exige só autenticação — nenhum papel específico. Devolve o principal que o JWT
carrega: `subject`, `tenant_id` e `roles` (lista ordenada), mais `journeys`. Nunca
devolve claims brutos nem o token; é a rota que a SPA usa para descobrir quem está
logado.

`journeys` é a lista das jornadas (`croqui`, `medicao`, `orcamento`) que este principal
pode abrir, **já resolvida no servidor** pelas três perguntas da F-034, nesta ordem:
o estado declarado da jornada neste ambiente, o entitlement do tenant (consultado
somente quando o estado é `pilot`) e o papel do JWT. A SPA renderiza a lista; ela não
recalcula papel nem decide disponibilidade. Lista vazia é resposta legítima: significa
que não há jornada para oferecer a este principal.

### Disponibilidade de jornada

Cada jornada tem um estado por ambiente — `enabled` (existe para todos os tenants),
`pilot` (existe só para tenants com entitlement ativo) ou `disabled` (não existe aqui).
O padrão de todas é `enabled`, então um ambiente que não declara nada se comporta como
antes desta regra existir.

As rotas de jornada são recusadas com `403 JOURNEY_UNAVAILABLE` quando a jornada não está
disponível — esconder a aba não protege a URL. A recusa é **a mesma** para jornada
`disabled` e para piloto sem entitlement (inclusive entitlement revogado): a diferença
entre as duas revelaria a existência de um piloto do qual o tenant não faz parte.

O portão antecede o portão de papel de cada rota e não o substitui: com a jornada
disponível, papel ausente continua recusando com o `403 FORBIDDEN` de sempre. Prefixos por
jornada: `/v1/jobs`, `/v1/uploads` e `/v1/projects` (croqui), `/v1/valuation-rounds`
(medição) e `/v1/estimate-rounds` (orçamento). Fora de jornada, explicitamente: `/v1/me`,
`/v1/meta`, `/v1/schemas` e `/v1/platform`.

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

### `GET /v1/platform/tenants`

Requer `platform_operator`. Leitura sem `Idempotency-Key` e sem auditoria (a
auditoria segue só no PUT). Lista todo `tenant_id` com pegada conhecida — união de
`tenant_ai_processing_entitlements`, `projects` e `uploads` (uploads é a pegada
mais precoce do ciclo de vida) — ordenado deterministicamente por `tenant_id`.
Cada item traz o estado do entitlement (`enabled`, `agreement_reference`,
`authorized_at`, `revoked_at`), com nulos para o tenant que nunca foi ativado.

### `GET /v1/platform/tenants/{tenant_id}/ai-processing-entitlement`

Requer `platform_operator`. Responde sempre `200`, mesmo para um `tenant_id` que
nunca teve entitlement criado (`enabled: false` e os demais campos nulos) — não há
tabela de tenants, então `404` seria arbitrário. Mesmo formato de item usado na
listagem, distinto da resposta do PUT (que só existe depois da primeira ativação).

## Disponibilidade de jornada por tenant

### `GET /v1/platform/journeys`

Requer `platform_operator`. Leitura sem `Idempotency-Key` e sem auditoria. Devolve duas
coisas numa resposta só, porque a tela responde uma pergunta só (quais jornadas existem
para cada cliente):

- `journeys`: o estado declarado de cada jornada neste ambiente (`enabled`, `pilot` ou
  `disabled`), na ordem estável `croqui`, `medicao`, `orcamento`. É **somente leitura** —
  mudar o estado é alterar configuração de ambiente e publicar, e por isso não existe rota
  que o escreva;
- `entitlements`: toda autorização já concedida, ordenada por `(tenant_id, journey)`, com
  `agreement_reference`, `authorized_by`, `authorized_at` e `revoked_at`. A autorização
  **revogada continua na lista**, com a data — sumir com ela apagaria a trilha.

Só entram os pares `(tenant, jornada)` que têm registro; ao contrário de
`GET /v1/platform/tenants`, esta rota não faz união com `projects` nem `uploads`.

### `PUT /v1/platform/tenants/{tenant_id}/journey-entitlements/{journey}`

Requer `platform_operator` e `Idempotency-Key`. O par `(tenant, jornada)` vem da rota; o
corpo carrega só o ato: `enabled` e, ao conceder, `agreement_reference` (3 a 128
caracteres). O tenant **alvo** é o da rota — o `tenant_id` do JWT de quem chama não decide
nada aqui, exatamente como no entitlement de IA. O ato é auditado no tenant alvo
(`JOURNEY_ENTITLEMENT_GRANTED` / `JOURNEY_ENTITLEMENT_REVOKED`).

Conceder exige que a jornada esteja em `pilot` neste ambiente. Fora disso a resposta é
`409 JOURNEY_NOT_IN_PILOT`, **sem gravar nada**, com `details` declarando `journey` e
`state` — autorizar um cliente numa jornada que já existe para todos, ou que não existe
aqui, não teria efeito, e o registro criado passaria a valer sozinho se o estado virasse
`pilot` depois.

Revogar (`enabled: false`) é aceito em **qualquer** estado, de propósito: é o que permite
encerrar uma autorização criada durante o piloto depois que a jornada foi liberada, em vez
de deixá-la ativa esperando o próximo piloto. Revogar não apaga o registro: carimba
`revoked_at` e o status. Revogar o que nunca foi concedido é `404 NOT_FOUND`.

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

A resposta traz ainda a conferência aritmética das cotas confirmadas umas contra as
outras, em dois campos que nunca entram em `blockers`:

- `suggested_chains`: somas que fecham dentro da tolerância, calculadas na leitura.
  São sugestões para uma pessoa olhar — a maioria pode ser coincidência aritmética —
  e nenhuma delas vira restrição de geometria sozinha.
- `declared_chains`: as cadeias que uma pessoa declarou, reconferidas contra o pacote
  corrente a cada leitura. Cada item traz `chain_id`, `declared_by`, `declared_at`,
  `chain`, `status` (`closes`, `mismatch` ou `stale`) e `issue`. `mismatch` carrega
  `DIMENSION_CHAIN_MISMATCH` (severidade `warning`) e `stale` carrega
  `CHAIN_READING_SUPERSEDED` com `chain` nulo: uma cota participante deixou de estar
  confirmada depois da declaração, e a cadeia avisa em vez de sumir.

A resposta traz também os campos de **confiança determinística** (F-029), todos
OBSERVACIONAIS: nenhum decide leitura, seleciona associação, entra em `blockers`, cria
issue ou toca a exportação. A associação que vale continua sendo a explícita em
`selected_associations`, e ela só nasce de ato humano.

- Cada candidato de `associations.candidates` carrega `association_confidence` (0–1,
  "sei a qual segmento esta cota pertence?") e `orientation_alignment` (`number | null`;
  `null` quando o candidato não tem direção própria — círculo, contorno).
- `reading_confidences`: `reading_confidence` (0–1, "li esta cota corretamente?") por
  leitura do pacote. As duas confianças nunca se fundem num número só: associar errado é
  o erro que nada a jusante percebe. Participar de cadeia que fecha corrobora a leitura;
  participar de uma cadeia **declarada** cujo total não bate (`mismatch`) a rebaixa — a
  declaração é ato humano afirmando a completude da soma, e a aritmética contradita é
  evidência contra uma das participantes. Cadeia `stale` não pesa: perdeu participante e
  deixou de ser verificável. Cadeia apenas **sugerida** que não fecha também não pesa:
  ali a soma incompleta pode ser só uma cota que o croqui não traz.
- `confidence_shadow`: o shadow log gravado na revisão — para cada ponto da grade fixa de
  thresholds (`reading_threshold` × `association_threshold`, cortes 0,5/0,6/0,7/0,8/0,9/0,95
  nos dois eixos), a lista `auto_choices` do que TERIA sido auto-decidido ali, com
  `reading_id`, `proposal_id` e as duas confianças. É registro para calibração, nunca
  decisão.
- `auto_association_rate` e `review_rate`: taxas observacionais da revisão corrente,
  medidas no ponto **mais conservador** da grade. `auto_association_rate` = leituras
  auto-decidíveis ÷ leituras com ao menos um candidato; `review_rate` = complemento sobre
  o total de leituras, que inclui as sem candidato — elas também são trabalho humano. Os
  números dependem da grade e não são recomendação de corte operacional: esse corte é
  escolhido por uma pessoa a partir do relatório de calibração.

Revisão gravada antes da coluna do shadow responde com as listas vazias e as duas taxas
`null`: ausência de registro, nunca zero medido. A revisão 1, escrita pelo worker, nasce
com o shadow computado desde a F-029/T4 — é a foto anterior ao primeiro toque humano, e
nenhuma revisão posterior conseguiria reconstituí-la.

Toda decisão exibida em `packet.readings[].decision` carrega `actor`
(`"human" | "system"`, default `"human"`;
[ADR-0041](../adr/0041-decisao-de-ator-maquina-atras-de-flag-local.md)). Decisão de
pessoa continua idêntica ao que sempre foi. Decisão de **sistema** — que só existe com o
modo automático local ligado, nasce no worker e nunca chega por request — tem
`reviewer_id` no formato `system:auto-association@<versão do score>`, `reviewer_role`
`null` (papel profissional é atributo de pessoa, derivado do JWT) e `action` sempre
`confirm`: o sistema nunca rejeita e nunca retifica. `reviewer_role` passa a ser opcional
no contrato por isso, e continua obrigatório para o ator humano.

A decisão de sistema carrega também `auto_tier` (`"cota" | "anotacao"`;
[ADR-0044](../adr/0044-triagem-por-testemunha-anotacao-automatica.md)), que diz por qual
regra a máquina decidiu. `cota` exigiu as duas confianças acima do corte e gravou a
associação explícita em `selected_associations`. `anotacao` não exigiu corte nenhum e
**não gravou associação**: a leitura entra confirmada e ausente de
`selected_associations`, que é a mesma forma da "anotação da folha" declarada por uma
pessoa (`annotation: true`, a única confirmação sem elemento associado). É essa ausência
que a mantém fora de qualquer restrição de geometria; o elemento provável viaja como
observação na `note` da decisão e na auditoria do export, nunca como vínculo.

Decisão humana traz `auto_tier` `null` — pessoa decide por julgamento, não por tier —, e
decisão de sistema gravada antes do campo é devolvida como `cota`, o único tier que
existia quando ela foi tomada. O corte continua sendo **um só**, e nenhum tier tem
threshold próprio.

Uma auto-decisão é imutável pelo mesmo caminho de todas: decidir de novo é
`READING_ALREADY_DECIDED`, e corrigi-la é a correção declarada de sempre
(`POST /v1/jobs/{job_id}/review/rectifications`), que a sucede por uma decisão humana com
`rectifies_decision_id`. Nenhuma rota muda de forma.

Cada leitura de `packet.readings` carrega `annotation_suggested`: `true` quando o
pipeline leu a linha como **anotação da folha** — um recado escrito, não a medida de um
elemento:

```json
{
  "packet": {
    "readings": [
      {
        "id": "rd_...",
        "raw_text": "muro Vizinho h=3,80",
        "kind": "length",
        "status": "proposed",
        "value_si": "3.80",
        "unit": "m",
        "annotation_suggested": true
      }
    ]
  }
}
```

É sugestão observada, nunca decisão: ela não confirma a leitura, não substitui
`"annotation": true` no comando de decisão e não dispensa a justificativa escrita. A
tela pode nascer com a opção de anotação pré-selecionada, e trocar a seleção à mão
continua valendo mais do que a sugestão. Pacote persistido antes do campo responde sem
ele, e o cliente trata a ausência como `false`.

Cada leitura também carrega `ocr_corroborated: boolean | null` (F-010, 2026-08-20):
registro de **nascimento** da corroboração determinística por OCR, nunca recalculado
numa retificação posterior da leitura. Tri-estado: `true` quando o braço de OCR leu o
mesmo texto na mesma região da leitura (match textual normalizado **e** interseção
espacial de bbox); `false` quando o OCR rodou e não encontrou correspondência; `null`
quando o braço estava ausente, falhou, ou o pacote foi persistido antes do campo
existir — os dois últimos casos têm o mesmo significado para o revisor: nenhuma segunda
testemunha foi conferida. A corroboração nunca rebaixa `status`: é aviso, não regra
determinística de aceite. Caso fundador: a V17 leu `24,75` onde a folha dizia `19,75`
e o pacote já sabia (`READING_{n}_OCR_EVIDENCE_MISSING` nas notas posicionais), mas o
sinal não chegava à tela — o campo o expõe à revisão sem exigir leitura de log.

`target_hint` de `packet.readings` é `string | null` (F-024, 2026-08-20): é dica de
leitura para o revisor, não amarração — quem liga a leitura à geometria é a associação
explícita por proximidade (`association.py`), que nunca lê o hint. Leitura com valor e
sem hint entra no pacote com `target_hint: null` e a nota
`READING_{n}_WITHOUT_TARGET_HINT` em vez de ser descartada; sem valor, o comportamento
de descarte (`READING_{n}_INCOMPLETE`, ou `READING_{n}_NOTE_WITHOUT_VALUE` quando
`kind="note"`) continua intacto.

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

### `POST /v1/jobs/{job_id}/review/chains`

Declara ou retrata uma cadeia de cotas: estas parcelas partilham este total. O motor
sugere; quem afirma é uma pessoa.

```json
{
  "base_version": 3,
  "action": "declare",
  "total_id": "rd_...",
  "part_ids": ["rd_...", "rd_..."]
}
```

`action` é `declare` ou `retract`. Declarar exige `total_id` e pelo menos duas
`part_ids`, todas de leituras **confirmadas**; retratar exige `chain_id` e funciona
também para cadeia `stale`. Revisor, papel e horário vêm do JWT e do relógio do
servidor, e o comando exige papel profissional elegível e `Idempotency-Key`.

Uma cadeia que **não fecha** é declarável de propósito: o desencontro entre a soma e o
total é justamente o achado, e ele viaja como `warning` em `declared_chains`, nunca em
`blockers`. O comando cria uma revisão de leitura nova (`version + 1`) carregando todo
o resto verbatim — pacote, associações, calibração, aceite de traçado e cena não são
tocados.

A resposta é a mesma de `GET /v1/jobs/{job_id}/review`. Erros: `422 CHAIN_INVALID` (a
cadeia não pode ser montada — menos de duas parcelas, leitura repetida, total que é
parcela de si mesmo ou leitura ainda não confirmada), `404 CHAIN_NOT_FOUND` (retração
de cadeia inexistente), `409 REVISION_CONFLICT`, `403 FORBIDDEN`, `404 NOT_FOUND` e
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
`unapplied_reading_ids`, `unapplied_readings`, `contested_spans`, `applied_spans`,
`residual_summary`, `exact_entity_count`, `approximate_entity_count`, `note_count`,
`scale_m_per_px`, `detail_group_scales`, `result_scene_revision_id`,
`result_scene_version`, `result_review_version` e `failure_code`. Registro de outro tenant
retorna `404`.

Os três campos de diagnóstico são **aditivos** (F-025): `unapplied_reading_ids` continua
existindo, com o mesmo conteúdo e a mesma ordem, e `blockers`, `residual_summary` e
`solve_status` não mudam por causa deles. Diagnóstico não é portão — quem decide o
desfecho continua sendo o resíduo e os blockers de sempre. Registro anterior à mudança
responde com as três listas vazias.

- `unapplied_readings`: uma entrada por leitura confirmada que não virou vão, com
  `reading_id`, `cause` (código estável, mesmo formato de `Issue.code`) e
  `target_proposal_ids` (o que a associação apontava). Para todo índice `i`,
  `unapplied_reading_ids[i] == unapplied_readings[i].reading_id`.
- `contested_spans`: os vãos disputados por duas ou mais leituras confirmadas, com `axis`,
  `reading_ids` (ordenados), `values_m` (na mesma ordem de `reading_ids`) e
  `proposal_ids`. Só aparece quando a divergência entre os valores escritos excede a
  tolerância da cota mais grosseira do par.
- `applied_spans`: onde cada cota aplicada ancorou, com `reading_id`, `axis`, `value_m`,
  `start_m`/`end_m` (coordenada ao longo do eixo no frame CAD da prancha, com
  `start_m <= end_m`), `proposal_id`, `second_proposal_id` e `gap`.

Os códigos de causa, que o [Trace Stage](TRACE_STAGE.md) descreve no estágio:

| `cause` | O que aconteceu | O que costuma consertar |
|---|---|---|
| `TRACE_SPAN_VALUE_OR_DECISION_MISSING` | A leitura chegou sem valor em metros ou sem decisão humana completa | Rever a leitura na revisão de cotas |
| `TRACE_SPAN_AXIS_UNDECLARED` | O vão não declara eixo (`width`/`height`) | Declarar o eixo da cota |
| `TRACE_SPAN_EDGE_NOT_FOUND` | Nenhuma aresta perpendicular ao eixo foi encontrada para uma das âncoras | Reapontar a âncora do vão |
| `TRACE_SPAN_SAME_BAND` | As duas âncoras caíram na mesma faixa | Declarar `keep_apart_pairs` no eixo do problema |
| `TRACE_TARGET_AS_DRAWN` | O alvo está em `freeform_proposal_ids`, e cota de elemento único não amarra forma livre | Tirar o alvo de `freeform` ou declarar o vão por âncoras |
| `TRACE_SPAN_NOT_ORTHOGONAL` | O elemento não tem segmento ortogonal compatível com o eixo da cota | Associar a cota ao trecho ortogonal certo |
| `TRACE_NOTE_ZERO_LENGTH` | O segmento âncora da nota tem comprimento zero | Reapontar a nota |
| `TRACE_NOTE_UNSUPPORTED_GEOMETRY` | A geometria do alvo não suporta nota ancorada | Reapontar a nota para um elemento com aresta |

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

Se a rodada já tinha uma aprovação, ela é **levada adiante** — e preservar não é aprovar. A
aprovação carregada continua amarrada ao digest do conteúdo anterior, então a medição
recém-montada nasce com a **aprovação caduca**: `GET .../bulletin` devolve `stale: true` com
`approved_by`/`approved_at` preenchidos e os dois digests divergentes, e
`POST .../bulletin/export` recusa com `APPROVAL_CONTENT_MISMATCH` até um ato novo de
aprovação. Descartá-la apagaria em silêncio o fato de que alguém assinou.

### `GET /v1/valuation-rounds/{round_id}/bulletin`

Retorna o boletim com totais **recomputados** na leitura, nunca lidos como estavam gravados.
Boletim ainda não construído devolve `409 ROUND_STAGE_NOT_READY`.

Acompanha o bloco `approval` (`approved`, `approved_by`, `approved_at`, `approved_digest`,
`current_digest`, `stale`), o estado da planilha publicada (`workbook_present`,
`workbook_sha256`) e `workbook_url` — URL assinada de curta duração, montada na leitura e
nunca persistida. `stale: true` é a **aprovação caduca**: houve aprovação, mas o conteúdo
mudou depois dela, e a exportação vai recusar até um ato novo.

### `POST /v1/valuation-rounds/{round_id}/approve`

Entrada: **só** `base_version`. A identidade do aprovador **não viaja no corpo** — quem
aprova é o `sub` do JWT, e o instante é o relógio do servidor. Um corpo com `reviewer_id`
(ou qualquer outro campo) é recusado com `422`.

Aprova nominalmente a medição da cabeça e amarra o ato ao `content_digest()` da medição, que
exclui a própria aprovação do cálculo. Exige `Idempotency-Key` e `base_version`, com
`409 REVISION_CONFLICT` para versão divergente, e avança `version` — aprovar é ato humano
deliberado. Boletim ainda não construído devolve `409 ROUND_STAGE_NOT_READY`; boletim que não
revalida devolve `422`.

### `POST /v1/valuation-rounds/{round_id}/bulletin/export`

Entrada: **só** `base_version`. Não há o que escolher na exportação: a medição é a da cabeça
e o layout é o da prefeitura.

Publica o `.xlsx` do boletim atrás de dois portões, nesta ordem. Primeiro o portão do
**domínio** (`Valuation.ensure_exportable`): medição sem aprovação, com aprovação de recusa
ou com aprovação que não confere com o conteúdo atual devolve `422 DOMAIN_VALIDATION_FAILED`
com `details.code = VALUATION_EXPORT_BLOCKED` e a lista de violações em `details.errors`
(`VALUATION_NOT_APPROVED`, `VALUATION_APPROVAL_REJECTED`, `APPROVAL_CONTENT_MISMATCH`).
Depois o portão da **auditoria**: a planilha é escrita, reaberta e reconferida contra a
medição e o catálogo instalado, e um laudo divergente devolve `500
VALUATION_WORKBOOK_AUDIT_FAILED` — só com os códigos dos achados, nunca com valor medido — e
**não publica nada**.

O `.xlsx` é endereçado pelo digest da medição, de modo que uma exportação nova nunca
sobrescreve a planilha que uma revisão anterior ainda referencia. A exportação não altera a
medição: a revisão nova carrega o mesmo boletim e acrescenta só a referência e o digest do
arquivo. A resposta do `POST` **não** traz `workbook_url`; a URL assinada sai apenas no `GET`.

Limite declarado: a cadeia de `/v1` não importa consolidado contratual, então os códigos de
saldo e contrato do portão (`BALANCE_EXCEEDED`, `CODE_NOT_IN_CONTRACT`,
`LINE_PRICE_NOT_IN_CONTRACT` e afins) não têm fato que os alimente nesta rota — a conferência
de preço contra o catálogo instalado é feita pelo auditor (`CATALOG_PRICE_MISMATCH`), e a
aprovação continua valendo integralmente.

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

## Orçamento-base de obra

O orçamento-base é o outro lado da fronteira que o
[ADR-0027](../adr/0027-price-source-provenance-and-bid-boundary.md) fixou: em obra
**licitada** o contrato manda e item fora dele vira dossiê de aditivo; **antes** da
licitação vale a cascata SCO → EMOP → composição, e é dela que sai o orçamento-base
([ADR-0038](../adr/0038-bdi-como-conceito-de-pre-licitacao.md)). A raiz é a **rodada de
orçamento** (`EstimateRound`), que leva uma prancha do levantamento de quantitativos à
planilha `.xlsx` com proveniência por linha.

Regras que valem em toda a seção, idênticas às da medição:

- Papel exigido: `orcamentista`, em toda rota — inclusive de leitura. Papel ausente devolve
  `403 FORBIDDEN` antes de qualquer lookup, e por isso ninguém descobre pela diferença
  entre `403` e `404` o que existe no tenant vizinho.
- `tenant_id` vem do JWT. Rodada de outro tenant devolve `404 NOT_FOUND`.
- Toda mutação exige `Idempotency-Key` e `base_version`; versão divergente devolve
  `409 REVISION_CONFLICT`. A versão é **da rodada**, uma só para toda a cadeia.
- O carimbo de identidade é sempre do servidor: o corpo recusa `reviewer_id`,
  `reviewer_role`, `decided_at` e `decision_id`.
- Invariante de domínio de `packages/valuation` devolve `422 DOMAIN_VALIDATION_FAILED` com
  o código de domínio (`ESTIMATE_*`, `ASSIGNMENT_*`, `TAKEOFF_*`) em `details`.

O que **não** existe aqui, por construção: contrato, período, saldo e aprovação. Nenhum
deles existe antes da licitação, e o `Estimate` não passa pelo portão de exportação da
medição.

### `POST /v1/estimate-rounds`

Entrada: `worksite_key`, `worksite_name`, `reference_label`, `address` (opcional),
`target_amount`/`target_label` (opcionais, o teto de verba da demanda — ADR-0040).  
Saída: `round_id`, `version=1`, `status`, `created_at`.

`worksite_key` segue `WORKSITE_KEY_PATTERN`, como na medição: a chave é imutável na rodada.
A rodada nasce **sem** fonte de preço — as fontes entram uma a uma, em ordem declarada.
`target_amount` viaja como **texto**, `Decimal` exato; zero, negativo ou ilegível devolvem
`422 ESTIMATE_TARGET_INVALID`. Sem `target_amount`, a rodada nasce sem teto — o
comportamento de antes desta decisão, sem qualquer bloco derivado.

`pricing_regime` (opcional, ADR-0045) declara na abertura que a demanda corre sob contrato
já licitado. O único valor gravável é `contracted_demand`; `pre_bid` devolve
`409 ESTIMATE_REGIME_IRREVERSIBLE`, e omitir o campo é a pré-licitação de sempre — ausência
não é um valor, é a falta dele.

### `GET /v1/estimate-rounds`

Lista as rodadas do tenant, com cursor opaco. Devolve `round_id`, `worksite_key`,
`reference_label`, `version`, `status`, etapa corrente e `cascade_origins` na ordem da
cascata.

Com teto declarado (ADR-0040), cada item ganha `target_amount`/`target_label` — os dois
textos crus da raiz da rodada, sem `consumed`/`remaining`/`over`: a listagem não busca a
cabeça de cada rodada para derivar aquele bloco. Rodada sem teto devolve os dois `null`.

### `GET /v1/estimate-rounds/{round_id}`

Estado da rodada: `version`, cascata instalada (origem, digest, data-base e rótulo de cada
fonte, na ordem), etapas por presença e digest de artefato, estado da extração paga e o
estado do orçamento (`estimate_sha256`, `workbook_sha256`).

Com teto declarado (ADR-0040), a resposta ganha `target: {amount, label}`; com teto **e**
orçamento montado, ganha também `consumed` (o `total_amount` do documento, como está),
`remaining` (teto menos consumido, pode ser negativo) e `over` (`consumido > teto`,
**estrito** — o limite exato não é estouro). Nada aqui recomputa dinheiro: os dois lados da
comparação são lidos, nunca refeitos. Rodada sem teto não ganha nenhuma dessas chaves.

Com regime declarado (ADR-0045), a resposta ganha `regime: {value,
allowed_cascade_origins, amendment_candidates}`. `allowed_cascade_origins` é a lista que a
instalação aceitaria, servida pelo servidor para a tela não guardar cópia própria da regra.
`amendment_candidates` é o **mesmo** número de `codes.rejected`, lido sob o regime: item
cuja confirmação de código foi rejeitada é candidato a aditivo, e o sinal vem do julgamento
de quem revisou — nunca de uma conferência contra um contrato que o orçamento não modela.
Rodada sem regime não ganha a chave.

### `POST /v1/estimate-rounds/{round_id}/target`

Entrada: `base_version`, `target_amount` (texto, `Decimal` exato, **> 0**),
`target_label` (opcional). Declara o teto de verba da rodada quando ainda não existe, ou
edita o valor/rótulo de um já declarado — a mesma rota serve os dois atos. `target_amount`
zero, negativo ou ilegível devolve `422 ESTIMATE_TARGET_INVALID`; a mesma recusa vale na
criação da rodada.

O teto é dado da RODADA, não do `Estimate` (ADR-0040, decisão 1): esta rota só grava as
duas colunas de `estimate_rounds` e avança a versão da rodada, como o BDI — nenhuma
revisão append-only nasce deste ato. **Não existe rota de remoção**: o Design Approval
Package não desenha apagar um teto já declarado.

### `POST /v1/estimate-rounds/{round_id}/regime`

Entrada: `base_version`, `pricing_regime`. Declara que a rodada corre **sob contrato
licitado** (ADR-0045). Como o teto, o regime é dado da RODADA: grava uma coluna de
`estimate_rounds` e avança a versão da rodada, sem revisão append-only e sem campo novo no
`Estimate`.

Duas recusas, as duas **sem gravar nada**:

- `409 ESTIMATE_REGIME_IRREVERSIBLE` — `pricing_regime: "pre_bid"`. O regime é **mão
  única**: rodada declarada não volta atrás, e rodada sem regime não "declara
  pré-licitação", porque a ausência já é ela. Corrigir um engano é abrir outra rodada. A
  mesma recusa vale na criação da rodada.
- `409 ESTIMATE_REGIME_CASCADE_DIRTY` — há fonte de origem ≠ `sco` instalada. A saída é
  removê-la por `POST .../catalogs/remove`; nada é reescrito por uma declaração posterior.

### `POST /v1/estimate-rounds/{round_id}/catalogs`

Entrada: `upload_id`, `base_version`. Instala uma fonte de preço no **fim** da cascata; o
JSON do catálogo sobe por `POST /v1/uploads/presign`, como o catálogo da medição.

A fonte é lida e validada antes de a entrada existir. Segunda fonte da mesma origem devolve
`409 ESTIMATE_CASCADE_ORIGIN_DUPLICATE` — o mesmo código do domínio —, porque a origem
deixaria de identificar de qual arquivo o preço de cada linha veio. Catálogo ilegível
devolve `422 DOMAIN_VALIDATION_FAILED`.

Na rodada **sob contrato licitado** (ADR-0045), origem fora da tabela contratual devolve
`409 ESTIMATE_CASCADE_ORIGIN_FORBIDDEN`, no mesmo instante e pelo mesmo motivo: a
alternativa é o preço atravessar orçamento e execução e só ser recusado na medição
(`BULLETIN_PRICE_ORIGIN_FORBIDDEN`), sobre serviço já feito. Sem regime declarado, a
cascata segue livre.

### `POST /v1/estimate-rounds/{round_id}/catalogs/order`

Entrada: `base_version` e `cascade`, a lista **completa** dos digests na ordem nova.
Reordenar é ato humano com consequência visível — a shortlist e a busca passam a devolver
primeiro o bloco da fonte promovida — e por isso avança a versão da rodada.

Nenhuma fonte entra nem sai por aqui: lista que não seja permutação da cascata instalada
devolve `422 ESTIMATE_CASCADE_ORDER_INVALID`.

Rodada que já tem decisão de código devolve `409 ESTIMATE_CASCADE_LOCKED`: o conjunto de
decisões é amarrado ao catálogo cabeça da cascata, e reordenar invalidaria as decisões já
registradas — que esta API não apaga. Reordene antes de decidir código.

### `POST /v1/estimate-rounds/{round_id}/catalogs/remove`

Entrada: `base_version` e `source_sha256`, o digest da fonte a remover. Remove uma fonte da
cascata instalada; a `version` da rodada avança.

Digest que não está instalado devolve `422 ESTIMATE_CASCADE_ORDER_INVALID` — o mesmo código
da reordenação, porque o corpo cita algo que a cascata não reconhece.

A trava é por FONTE, não pela cascata inteira: remover devolve `409 ESTIMATE_CASCADE_LOCKED`
só quando alguma decisão de código registrada citou justamente a fonte removida
(`CodeAssignment.catalog_sha256`). Remover uma fonte que nenhuma decisão citou é permitido
mesmo com outras decisões já registradas na rodada.

### `POST /v1/estimate-rounds/{round_id}/plate`

Entrada: `upload_id`, `base_version`. Mesmo regime da prancha da medição: uma rodada tem no
máximo uma prancha, e a segunda chamada devolve `409 ROUND_PLATE_ALREADY_PRESENT`.

### `GET /v1/estimate-rounds/{round_id}/plate`

Metadados da prancha e `image_url`: URL assinada de curta duração para o PNG promovido, sob
o prefixo do tenant, nunca registrada em log nem em auditoria.

### `POST /v1/estimate-rounds/{round_id}/plate/extractions`

Enfileira a extração paga da legenda e retorna `202` com `extraction_id` e `status`. Mesmo
portão da medição: autorização contratual por tenant
([ADR-0012](../adr/0012-contractual-ai-processing-entitlements.md)),
`403 AI_PROCESSING_NOT_AUTHORIZED` sem entitlement, `503 PROVIDER_UNAVAILABLE` sem provider
configurado no ambiente, `409 EXTRACTION_IN_PROGRESS` com extração em voo e
`503 PROCESSING_UNAVAILABLE` com a fila indisponível.

### `GET /v1/estimate-rounds/{round_id}/takeoff`

Retorna o `TakeoffPacket` da rodada, com a âncora de evidência por item e o digest do
pacote. Sem extração publicada devolve `409 ROUND_STAGE_NOT_READY`.

### `GET /v1/estimate-rounds/{round_id}/takeoff/overlay`

Retorna `image_url` assinada do overlay das âncoras, mais `stale` e o digest do pacote que
originou o desenho ([ADR-0030](../adr/0030-overlay-do-takeoff-reconstruido-na-fila.md)).
Overlay vencido devolve `200` com a marca, nunca erro.

### `POST /v1/estimate-rounds/{round_id}/takeoff/decisions`

Entrada: `base_version` e uma decisão sobre um item — `item_id`, `action`, `quantity`,
`unit`, `note`, `item_note`. `quantity` viaja como **texto**, porque quantidade é `Decimal`
exato neste contexto. Decisão é imutável: item já revisado devolve
`422 DOMAIN_VALIDATION_FAILED` com `TAKEOFF_ITEM_ALREADY_REVIEWED`.

### `GET /v1/estimate-rounds/{round_id}/code-suggestions`

Shortlist determinística de código sobre a **cascata**: um bloco por fonte, na ordem
instalada, nunca misturados por score — a ordem das fontes é decisão do orçamentista e não
pode ser desempatada por similaridade de texto. É observação, nunca decisão. Revisão de
takeoff incompleta devolve `409 TAKEOFF_REVIEW_INCOMPLETE`; rodada sem cascata devolve
`409 ROUND_STAGE_NOT_READY`.

### `POST /v1/estimate-rounds/{round_id}/code-suggestions/recompute`

Recalcula a shortlist sobre a cascata corrente; é o caminho declarado de reler o efeito de
uma reordenação. Exige `Idempotency-Key` e `base_version`. Shortlist já refinada por modelo
pago não é recalculada por caminho determinístico: `409 SUGGESTIONS_ALREADY_REFINED`.

### `GET /v1/estimate-rounds/{round_id}/catalog/search`

Busca léxica na cascata inteira. Parâmetros: `q`, `limit`. Cada resultado carrega
`price_origin`, `catalog_sha256` e `cascade_position`, além do `origin` que nomeia o braço
da busca. O corte de `limit` vale por fonte, para que uma tabela não seja espremida para
fora da página por outra que ficou na frente da cascata.

Não há parâmetro `arm`: o braço híbrido depende de índice de embeddings publicado na
rodada, e nenhuma rota de `/v1` publica esse índice. O motivo viaja em `semantic_notes` — a
busca nunca degrada em silêncio. Consulta sem termo utilizável devolve
`422 CATALOG_QUERY_EMPTY`.

### `GET /v1/estimate-rounds/{round_id}/code-assignments`

Retorna o `CodeAssignmentSet` corrente e os itens confirmados ainda sem decisão de código.

### `POST /v1/estimate-rounds/{round_id}/code-assignments/decisions`

Entrada: `base_version`, `item_id`, `action`, `code`, `catalog_sha256` e `note`. A
confirmação **cita a fonte**: com mais de uma tabela na rodada, resolver o código pela ordem
da cascata seria a máquina escolhendo quem precifica o item. Rejeição exige justificativa e
recusa tanto `code` quanto `catalog_sha256` — rejeitar é recusar todas as fontes.

Fonte fora da cascata, código fora do catálogo citado, item não confirmado no takeoff, item
já decidido ou unidade incompatível sem nota devolvem `422 DOMAIN_VALIDATION_FAILED` com o
código `ASSIGNMENT_*` correspondente.

### `POST /v1/estimate-rounds/{round_id}/estimate`

Entrada: `base_version` e `bdi_percent`, o percentual **único** do orçamento, como texto
(ADR-0038, decisão 2). A identidade da obra é atributo da rodada e não viaja aqui.

Monta o orçamento sobre o takeoff confirmado, as decisões de código e a cascata; grava a
planilha, reabre e reconfere centavo a centavo, e só então publica o `.xlsx` e grava a
revisão. Auditoria reprovada não publica nada e devolve `500
ESTIMATE_WORKBOOK_AUDIT_FAILED` com os códigos dos achados — nunca os valores divergentes.

Cascata vazia, takeoff ainda não revisado por inteiro e nenhuma decisão de código devolvem
`409 ROUND_STAGE_NOT_READY`. Confirmação sem fonte citada devolve
`422 DOMAIN_VALIDATION_FAILED` com `ESTIMATE_ASSIGNMENT_CATALOG_REQUIRED`; item confirmado
sem decisão de código, com `ESTIMATE_ASSIGNMENT_MISSING`. `bdi_percent` ilegível devolve
`422 ESTIMATE_BDI_INVALID`.

A resposta não carrega URL: ela é guardada no registro de idempotência, e URL assinada é
credencial de leitura.

Com teto declarado na rodada (ADR-0040), a resposta ganha `target`, `consumed`,
`remaining` e `over` — o mesmo bloco derivado do estado da rodada, comparando o
`total_amount` que acabou de ser montado contra o teto. Sem teto, nenhuma dessas chaves
aparece.

### `GET /v1/estimate-rounds/{round_id}/estimate`

Retorna o orçamento com BDI, totais e linhas **recomputados** na leitura, mais
`workbook_url`: URL assinada de curta duração da planilha publicada, montada na hora depois
de conferido o prefixo do tenant. Orçamento ainda não montado devolve
`409 ROUND_STAGE_NOT_READY`; orçamento que não revalida devolve `422`.

Com teto declarado, ganha também `target`/`consumed`/`remaining`/`over` (ADR-0040), a
mesma forma do estado da rodada.

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
`FORBIDDEN`, `NOT_FOUND`, `AI_PROCESSING_NOT_AUTHORIZED`, `JOURNEY_UNAVAILABLE`,
`JOURNEY_NOT_IN_PILOT`,
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
