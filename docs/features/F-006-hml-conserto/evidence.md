# F-006 — Evidência

Status: `IN PROGRESS`  
Última atualização: 2026-08-18

## 1. Diagnóstico executado (2026-08-18)

Consulta somente-leitura à borda pública e ao projeto `biahflow-hml`, com a conta
`daniel@biahflow.ai`. Nenhuma mutação foi feita no ambiente.

### 1.1 A borda, medida

| Rota | Resultado | Observação |
|---|---|---|
| `/revisao/` | 200 | SPA íntegra |
| `/medicao/` | 200 | SPA íntegra |
| `/api/healthz` | **404** | página de erro do Google, com `x-cloud-trace-context` |
| `/auth/realms/croquito/.well-known/openid-configuration` | **503** | corpo `Service Unavailable`, 19 bytes |

Reproduzido também contra `https://croquito-web-hml-…run.app`, sem a CDN: mesmo resultado,
então Cloudflare não participa da falha.

**Anomalia registrada, não explicada:** sob `/api/`, apenas o path exato `/healthz` responde
404. `/api/healthzz`, `/api/health`, `/api/healt`, `/api/v1/meta` e `/api/v1/projects`
respondem **200 com a página "Congratulations | Cloud Run"**. Isso é medição, não teoria;
re-medir com a imagem real servindo.

### 1.1.1 Correção do diagnóstico: não era a senha, era o endereço

A primeira leitura deste evidence atribuiu a falha a uma credencial vencida. **Estava errada**,
e o que a corrigiu foi o acesso à API do Neon, obtido depois. Registrado aqui em vez de
reescrito em silêncio, porque o erro tem valor: o sintoma reportado por todos os consumidores
era `password authentication failed`, e ele apontava para o lugar errado.

Comparação por digest, para não expor nenhuma das senhas (`sha256`, 12 primeiros dígitos):

| | digest | tamanho |
|---|---|---|
| senha corrente da role no Neon | `3fbefa0d6b0f` | 16 |
| senha no secret do Keycloak | `3fbefa0d6b0f` | 16 |
| senha embutida no DSN da API | `3fbefa0d6b0f` | 16 |

**As três são idênticas.** O que diverge é o host:

| | host |
|---|---|
| nos secrets | `ep-still-firefly-audokk6w.c-10.us-east-1.aws.neon.tech` |
| endpoints reais da conta | `ep-still-leaf-audsh9wg` (production), `ep-morning-resonance-auqvw4lf` (staging), e os de outros três projetos |

`ep-still-firefly-audokk6w` **não pertence a nenhum projeto da conta**. O proxy do Neon roteia
pelo hostname; endpoint desconhecido não vira erro de conexão, vira falha de autenticação — é
essa tradução que despistou o diagnóstico por uma rodada inteira.

Prova do conserto, obtida **antes** de qualquer apply: conectando com o host da branch
`staging` e a senha da role daquela branch, `SELECT` responde —
`PostgreSQL 16.14`, `user=neondb_owner`, `db=neondb`.

### 1.1.2 O banco está vazio nas duas branches

Medido na mesma conexão, e não previsto por ninguém:

| branch | tabelas fora de `pg_catalog`/`information_schema` | `alembic_version` |
|---|---|---|
| `production` | nenhuma | não existe |
| `staging` | nenhuma | não existe |

O schema criado pelo job de banco em 2026-08-14 vivia no endpoint que sumiu. Duas
consequências que não são de código:

1. **O ato pendente de [F-004](../F-004-migrations-runner/feature.md) não pode ser cumprido por
   este deploy.** O runner vai reconhecer banco vazio e aplicar desde a baseline — o caminho de
   **carimbo** de banco preexistente, que é o que faltava exercitar, continua sem prova.
2. **O realm do Keycloak nasce sem usuários.** O import traz o realm `croquito` e os papéis, não
   as pessoas: recriar o usuário da orçamentista e conceder `orcamentista` deixou de ser um item
   pendente e passou a ser pré-requisito de qualquer homologação.

### 1.2 Keycloak: por que 503

Log do cold start disparado pela própria fumaça, revisão `croquito-auth-hml-00016-z5g`:

```
2026-08-18T10:37:47Z WARN  [io.agroal.pool] Datasource '<default>': ERROR: password
                     authentication failed for user 'neondb_owner'
2026-08-18T10:37:49Z ERROR [org.keycloak…ExecutionExceptionHandler] Failed to start server
                     in (production) mode / Failed to obtain JDBC connection
2026-08-18T10:37:49Z       Container called exit(1).
```

O serviço tem `minScale: 0`: cada requisição a `/auth/` acorda uma instância que morre no
boot, e o Cloud Run devolve 503. O padrão se repete idêntico em 2026-08-17T20:40Z — a hora
exata da fumaça registrada em F-001.

### 1.3 O job de banco: a esteira está barrada desde 2026-08-14

| Execução | Data | Resultado |
|---|---|---|
| `croquito-db-init-hml-7kr72` | 2026-08-17T14:12 | **falhou** |
| `croquito-db-init-hml-d4m96` | 2026-08-14T23:50 | sucesso |
| três anteriores | 2026-08-14 | sucesso |

Causa da falha, no log:

```
psycopg.OperationalError: connection failed: … ERROR: password authentication failed for
user 'neondb_owner'
host: 'ep-still-firefly-audokk6w.c-10.us-east-1.aws.neon.tech'
```

Como `deploy-hml.yml` executa o job de banco antes da API e falha o deploy inteiro se ele não
passar, **nenhuma revisão nova entrou no ar desde 2026-08-14**. O portão fez exatamente o que
foi desenhado para fazer. O que faltou foi alguém saber.

### 1.4 A API está servindo o container de exemplo

```
croquito-scene-hml-00003-kt9  2026-08-14T23:56  us-docker.pkg.dev/cloudrun/container/hello  (100% do tráfego)
croquito-scene-hml-00002-9kc  2026-08-14T23:51  …/croquito-python@sha256:54bf6d0a…
croquito-scene-hml-00001-9s4  2026-08-14T23:46  us-docker.pkg.dev/cloudrun/container/hello
```

A revisão `00002` — a imagem real — **subiu com sucesso**:

```
INFO: Application startup complete.
INFO: 169.254.169.126 - "GET /healthz HTTP/1.1" 200 OK
STARTUP HTTP probe succeeded after 3 attempts … port 8080 path "/healthz"
2026-08-14T23:56:26Z Shutting down user disabled instance
```

Cinco minutos depois ela foi substituída pelo `hello`, num teste manual de roteamento, e
nunca revertida. Com a esteira barrada pelo job de banco, nada a substituiu.

### 1.5 O "bug de GFE" não explica o 404 medido

`envs/hml/croquito/main.tf`, no repositório de infraestrutura, documenta e resolve a causa
conhecida de 404 naquele caminho: sem a zona DNS privada `run.app` →
`private.googleapis.com`, o egress VPC do proxy resolve os backends pelos IPs públicos do
Google Frontend e o ingress interno classifica a requisição como externa.

Cronologia, por `git log -S` no stack: a zona entrou em **2026-08-14 18:46**; o rename
`croquito-api-hml` → `croquito-scene-hml`, que o comentário de `deploy/nginx.conf` justifica
pelo "bug de plataforma", foi aplicado em **2026-08-14 21:16** — duas horas e meia depois.

O que **não** é afirmável com o que foi medido: que o rename tenha sido desnecessário. Não há
registro do estado do apply entre os dois commits. O que é afirmável: a explicação de bug de
plataforma não cobre o 404 de 2026-08-18, porque quem responde por trás do proxy é o container
de exemplo. O comentário foi corrigido para dizer isso, e não mais do que isso.

### 1.6 O stack ainda declarava o modo hospedado

`croquito-medicao-hml` **não existe** na listagem de serviços do projeto, e o bucket
`croquito-hml-rounds` responde **404** — os dois já removidos por ato humano. Mas o stack
ainda declarava serviço, runtime SA e bucket: o próximo apply os teria **recriado**,
desfazendo em silêncio a remoção que a
[F-003](../F-003-medicao-v1-migration/feature.md) fez de propósito.

O que ainda existe, verificado em 2026-08-18: a service account
`croquito-medicao-hml@biahflow-hml.iam.gserviceaccount.com`. Ela é o único destroy real desse
grupo — serviço e bucket saem do state por reconciliação, porque o mundo já não os tem.

### 1.7 Chaves HMAC ativas hoje

`gcloud storage hmac list` mostra uma chave `ACTIVE` para
`croquito-hml-storage@biahflow-hml.iam.gserviceaccount.com` (mais uma de outra SA, alheia a
este stack). Depois do apply serão duas, até a antiga ser desativada — o que só pode
acontecer depois do deploy que passa a ler o secret novo.

## 2. Autorização humana

| Decisão | Data |
|---|---|
| Selecionar o conserto da HML como trabalho próprio | 2026-08-18 |
| Segredo por Secret Manager gerenciado com Terraform, sem `gcloud`, nada manual | 2026-08-18 |
| Valor gerenciado nos sete secrets do stack | 2026-08-18 |
| Publicar F-003 em `main` na mesma rodada do conserto | 2026-08-18 |
| Remover o bucket `croquito-hml-rounds` junto com o modo hospedado, com perda do conteúdo | 2026-08-18 |

## 3. Entregue

### No repositório `biahflow/infra` (branch `feat/secret-manager-modulo`)

- `modules/secret-manager/` — casca, IAM por leitor e versão corrente, com
  `create_before_destroy` e `deletion_policy = "DISABLE"` para que rotação não abra janela sem
  `latest` e a versão anterior continue existindo para rollback. README declara a fronteira e
  a consequência de o valor morar no state.
- `envs/hml/croquito` consumindo o módulo, com dois blocos `moved` (sem índice, adotando todas
  as instâncias do `for_each`) para os sete secrets e todos os bindings.
- `google_storage_hmac_key` para a SA `croquito-hml-storage`, alimentando
  `croquito-hml-storage-hmac-id` e `-secret`.
- Modo hospedado removido: `module "medicao"`, a runtime SA, o bucket `croquito-hml-rounds` e
  o binding correspondente.
- Branch do Neon declarada por nome (`staging`), com host e senha derivados dela, compondo o DSN
  da API e o JDBC do Keycloak e alimentando os quatro secrets de banco — leitura apenas, sem
  escrita no Neon.
- `plan.yml` e `apply.yml` com o filtro do módulo novo, `NEON_API_KEY` e
  `TF_VAR_neon_project_id`; a função de detecção passou a aceitar mais de um módulo por stack.
- `terraform fmt -check -recursive` e `terraform validate` verdes.

### No repositório `biahflow/croquito` (branch `feat/f-003-medicao-v1`)

- `scripts/smoke_hml.py` + `make smoke-hml` — só biblioteca padrão, sem credencial, verificando
  **conteúdo**: health precisa ser o JSON da API, discovery precisa anunciar o issuer da borda
  pública, cada SPA precisa referenciar os próprios assets. Rodado contra a HML: reproduz o
  diagnóstico e sai com código 1.
- Passo de fumaça da esteira trocado pelo mesmo script, **sem o bypass condicional**.
- [ADR-0031](../../adr/0031-segredo-de-homologacao-gerenciado-por-terraform.md) (`Proposed`).
- Reconciliação: `HML.md` ganhou "Estado verificado" com data e medição, perdeu o passo
  "medição" da ordem de deploy e a lacuna do modo hospedado; `deploy/nginx.conf` teve o
  comentário do "bug de GFE" corrigido.

### Neon: topologia levantada e desenho escolhido

Com o `gcloud` reautenticado, a forma dos DSNs em uso foi lida dos próprios secrets (campos
não sensíveis; a senha nunca saiu do processo):

| | API/worker | Keycloak |
|---|---|---|
| driver | `postgresql+psycopg` | `jdbc:postgresql` |
| host | `ep-still-firefly-audokk6w.c-10.us-east-1.aws.neon.tech` | idem |
| database | `neondb` | `neondb` |
| usuário | `neondb_owner`, embutido no DSN | `neondb_owner`, em secret próprio |
| parâmetros | `sslmode=require`, `channel_binding=require` | `sslmode=require`, `currentSchema=keycloak` |

Ou seja: **um banco, um usuário, dois schemas**.

O projeto é `empty-glitter-27235439`, com duas branches: `production` (default) e `staging`
(filha), cada uma com endpoint de escrita próprio e senha própria para a role. **Por decisão do
usuário em 2026-08-18, a homologação passa a usar `staging`.**

O provider `kislerdm/neon` (0.15.0, schema inspecionado, não presumido) fornece o caminho
completo por leitura: `neon_branches` → a branch pelo **nome**, `neon_branch_endpoints` → o host
do endpoint `read_write`, `neon_branch_role_password` → a senha da role naquela branch. O stack
usa os três e compõe os DSNs — **sem criar, rotacionar ou apagar nada no Neon**, e sem nenhum
hostname escrito à mão, que foi precisamente o defeito. Se o endpoint mudar de novo, o conserto
é um apply.

## 3.1 Plano do Terraform: completo e verificado (2026-08-18)

Executado com ADC e `NEON_API_KEY`, apontando para a branch `staging`:

```
Plan: 7 to add, 1 to change, 2 to destroy.
```

As sete criações são a chave HMAC e as **seis versões de secret** (as duas de HMAC e as quatro
de banco). `croquito-hml-kc-bootstrap-admin-password` segue sem versão, como declarado.

- **17 de 17 recursos de secret adotados** por `moved`, sem uma única recriação. A conferência
  foi por conjunto, não por leitura: `terraform state list` filtrado por `secret` (7 cascas +
  10 bindings) menos os endereços com `has moved to` resulta em **conjunto vazio**.
- **Os dois destroys são os esperados e nomeados**: `google_service_account.medicao` e
  `google_service_account_iam_member.infra_deploy_actas["medicao"]`.
- **A única criação é a chave HMAC.**

**Achado não previsto — drift no Keycloak.** O plano acusa
`module.auth.google_cloud_run_v2_service.this` com `min_instance_count = 0 -> 1`: o stack
declara instância sempre quente para o Keycloak (`KC_CACHE=local` não forma cluster, e cold
start de 20-40s derrubaria o primeiro login), mas o serviço real está em zero — o que também
explica por que cada requisição a `/auth/` durante a falha acordava uma instância nova só para
vê-la morrer. O apply restaura o declarado. **É mudança de custo**, e o
[HML](../../operations/HML.md) já a descreve como escolha de operação: o Keycloak é o item de
custo fixo do ambiente.

O plano está completo: não sobra nada por planejar.

## 3.2 O primeiro apply falhou, e o que ele ensinou (2026-08-18)

O plano estava certo e ainda assim o apply parou em dois pontos. Nenhum dos dois é visível em
plano: um é permissão que só aparece na chamada, o outro é uma corrida que só existe no apply.

**`roles/storage.admin` não cobre chave HMAC.** `Error 403: … does not have
storage.hmacKeys.create access`. A permissão vive em `roles/storage.hmacKeyAdmin`, que a SA
`infra-deploy` não tinha.

**O serviço subiu antes do secret.** `Error waiting for Updating Service: … container failed
the configured startup probe checks`. Mexer no template cria revisão nova, revisão nova lê
`:latest` **ao subir**, e `min_instances = 1` exige que ela fique saudável para o apply
terminar. Sem ordem declarada, o Terraform atualizou o Keycloak em paralelo com a criação das
versões de secret: a revisão `00017` nasceu contra o host morto e morreu no probe. Os três
serviços que leem secret passaram a declarar `depends_on = [module.secrets]`.

Estado depois do apply parcial, apurado com `gcloud`:

| | estado |
|---|---|
| versões de secret | nenhuma criada — todas ainda na versão 1 de 14/08 |
| chave HMAC | não criada (403) |
| `croquito-auth-hml` | `min_instances` em 1; revisão `00017` criada e não saudável; tráfego na `00016` |
| SA `croquito-medicao-hml` | destruída, como planejado |

Nada ficou pior do que estava — o ambiente já não subia. O conserto é
[biahflow/infra#12](https://github.com/biahflow/infra/pull/12), com os dois planos limpos
(1 add em `wif`, 7 add e nenhum destroy em `croquito`).

**Ordem que decorre disso, e que vale registrar:** o apply grava os secrets certos, mas **não
levanta o Keycloak sozinho**. Com `min_instances` já em 1, o Terraform não terá motivo para
criar revisão nova, e revisão em execução não relê segredo. Quem levanta é o deploy da
aplicação, que publica todos os serviços com a imagem do SHA.

## 4. Não entregue (e por quê)

- **O apply**, que é ato humano com plano revisado.
- **`NEON_API_KEY` no CI.** O plano local usou a chave fornecida pelo usuário; para o
  `plan.yml`/`apply.yml` rodarem, ela precisa existir como secret do repositório de
  infraestrutura. `neon_project_id`, `neon_branch`, `neon_role` e `neon_database` têm default no
  stack e não exigem configuração.
- **`croquito-hml-kc-bootstrap-admin-password` continua sem valor gerenciado**, contra a
  decisão de "todos os sete", por razão técnica: `KC_BOOTSTRAP_ADMIN_PASSWORD` só age na
  criação do primeiro admin. Gerar valor novo não mudaria a senha do admin que já existe no
  realm — só faria o secret divergir do mundo. Fica como casca, declarado no código.

## 5. Pendências humanas

- Aceitar o ADR-0031.
- Configurar `NEON_API_KEY` como secret do repositório de infraestrutura.
- **Rotacionar a chave de API do Neon e a senha da role de `staging`**: as duas foram
  transmitidas em texto durante o trabalho de 2026-08-18 e devem ser consideradas expostas.
  Depois da rotação, um novo apply propaga a senha nova sozinho — que é exatamente o
  comportamento que esta feature entrega.
- Recriar o usuário da orçamentista no realm e conceder `orcamentista` (o realm nasce vazio).
- Revisar o plano do Terraform e aplicar.
- Publicar F-003 em `main`.
- Conceder o papel `orcamentista` no realm.
- Desativar a chave HMAC anterior, **depois** do deploy que passa a ler o secret novo.
