# Ambiente de homologação (GCP)

Status: Accepted  
Responsável: Platform / Engineering  
Última revisão: 2026-08-20 (braço OpenAI desligado por configuração na rodada atual,
`CROQUITO_OPENAI_ARM_ENABLED=false`)

Fonte única do ambiente hospedado. A decisão e as alternativas estão no
[ADR-0025](../adr/0025-homologacao-em-gcp-cloud-run.md); o desenho AWS de
[AWS Deployment](../architecture/AWS_DEPLOYMENT.md) é o alvo de **produção** e não
descreve o que está no ar.

## O que está publicado

Esta seção descreve o **desenho publicado**: o que a esteira cria e como as peças se ligam.
Ela não afirma disponibilidade — para isso existe "Estado verificado", logo abaixo, e a
fumaça que qualquer pessoa pode rodar.

Projeto `biahflow-hml`, região `us-east1`, registro
`us-east1-docker.pkg.dev/biahflow-hml/hml`.

| Rota pública | Serviço Cloud Run | Ingress | O que é |
|---|---|---|---|
| `/` | `croquito-web-hml` | público | `302 /login`, porta de entrada do produto |
| `/login` | `croquito-web-hml` | público | SPA de entrada; o build é servido em `/revisao/` |
| `/revisao/` | `croquito-web-hml` | público | SPA da sessão de cena (`apps/web`) |
| `/medicao/` | `croquito-web-hml` | público | jornada de medição, na mesma SPA (`apps/web`) |
| `/api/` | `croquito-scene-hml` | interno | API FastAPI (`croquito_api.main:app`), inclusive as rotas de medição |
| `/auth/` | `croquito-auth-hml` | interno | Keycloak, realm `croquito` |
| — | `croquito-jobs-hml` | interno e privado | worker; recebe push do Pub/Sub em `POST /pubsub` |

Recursos de apoio: bucket `croquito-hml-artifacts` (documentos, previews e pacotes
exportados); tópico `projects/biahflow-hml/topics/croquito-hml-processing`; segredos
`croquito-hml-*` no Secret Manager; PostgreSQL gerenciado (Neon) para a API e para o
Keycloak, cada um no seu schema — veja [Os dois schemas do banco](#os-dois-schemas-do-banco).

Nada disso é criado por este repositório: a casca do ambiente — serviços, bucket, Pub/Sub,
DNS, segredos e a chave HMAC — é Terraform em `biahflow/infra`, stack `envs/hml/croquito`.
Aqui mora a imagem e a revisão. A fronteira está no
[ADR-0031](../adr/0031-segredo-de-homologacao-gerenciado-por-terraform.md), D6.

Cada serviço roda com a própria conta de serviço
(`<serviço>@biahflow-hml.iam.gserviceaccount.com`), atribuída pelo deploy.

## Estado verificado

**Última verificação: 2026-08-18, `make smoke-hml` — as quatro rotas verdes.** A jornada
responde, o endereço herdado da medição redireciona, a API se identifica e o Keycloak anuncia
o issuer desta borda: a sessão autenticada de homologação **está de pé**, depois de quatro dias
fora do ar.

O que segue abaixo é o registro de como ela caiu, mantido porque a explicação errada custou
uma rodada inteira de diagnóstico.

A causa foi diagnosticada em 2026-08-18 e está no
[ADR-0031](../adr/0031-segredo-de-homologacao-gerenciado-por-terraform.md): o endereço do banco
nos secrets aponta para um endpoint do Neon que não existe mais — a senha estava certa, e o
proxy do Neon é que responde a endpoint desconhecido com falha de autenticação. Isso derruba o
Keycloak no boot e **barra a esteira no job de banco desde 2026-08-14**; com a esteira barrada,
o container de exemplo que alguém pôs em `croquito-scene-hml` num teste de roteamento nunca foi
substituído pela imagem real. O conserto é a
[F-006](../features/F-006-hml-conserto/feature.md).

O banco de homologação está **vazio** nas duas branches do projeto Neon: o schema que existia
vivia no endpoint que sumiu. Quem subir o ambiente encontra um realm sem usuários e um banco
sem tabelas — recriar o usuário da orçamentista e o papel `orcamentista` deixou de ser opcional.

Esta seção é atualizada por medição, não por intenção: se a data acima está velha, o estado
é desconhecido, não bom.

### A borda pública

`croquito-web-hml` é o único serviço com ingress público. A imagem
(`docker/web.Dockerfile`) constrói as duas SPAs e as serve por
[`deploy/nginx.conf`](../../deploy/nginx.conf), que faz o proxy same-origin do resto. Duas
consequências operacionais:

- **As URLs internas são literais na configuração do nginx.** Elas são determinísticas
  (`croquito-<serviço>-hml-209400815796.us-east1.run.app`) e não vêm de variável de
  ambiente: trocar de URL — outro projeto, outra região, outro serviço — exige reconstruir
  e republicar a imagem do nginx, não editar o serviço.
- **As `VITE_*` da SPA são de build** (base da API `/api`, `authority` do realm e
  `client_id` público). Elas entram no bundle como `ARG`/`ENV` do Dockerfile; mudar qualquer
  uma delas também é reconstruir a imagem.

O prefixo é removido no proxy da API (`/api/healthz` → `/healthz`) e **preservado** no do
Keycloak (`/auth/...`), que vive em subpath. O corpo aceito pela borda é de 1 MB e não há
exceção: desde a migração da medição para a `/v1`
([F-003](../features/F-003-medicao-v1-migration/feature.md)), tanto a prancha quanto o
catálogo de preços sobem presignados direto ao bucket, e nenhum arquivo de usuário atravessa
o nginx.

## Como deployar

Só existe um caminho: a esteira
[`deploy-hml.yml`](../../.github/workflows/deploy-hml.yml), autenticada por Workload
Identity Federation. Não há chave de conta de serviço, então publicar de uma máquina de
desenvolvimento não é possível — e não é para ser.

- **Automático**: push na `main` que toque `services/`, `packages/`, `apps/`, `docker/`,
  `keycloak/`, `deploy/`, `pyproject.toml`, `uv.lock`, `package*.json` ou o próprio
  workflow.
- **Manual**: `workflow_dispatch` (aba Actions → deploy-hml → Run workflow).

A ordem é sempre: construir e publicar as imagens com tag `$GITHUB_SHA` → **job de banco**
(`croquito-db-init-hml`, runner de migrations) → API → worker → Keycloak → nginx → fumaça.
Falha no job de banco para o deploy antes de qualquer revisão nova entrar no ar — e foi
exatamente o que aconteceu entre 2026-08-14 e 2026-08-18, com a credencial de banco vencida.
O portão fez o que devia; o que faltou foi alguém saber.

O passo de publicação do servidor de medição saiu da esteira com a
[F-003](../features/F-003-medicao-v1-migration/feature.md), junto do modo hospedado.

### O job de banco

`python -m croquito_api.bootstrap` é o runner de migrations revisadas decidido no
[ADR-0029](../adr/0029-runner-de-migrations-revisadas.md): ele aplica com Alembic as
revisões que faltam, e as revisões viajam dentro do pacote `croquito_api`, na mesma imagem
da API. Ele reconhece três estados de banco: com controle de versão (aplica o que falta),
vazio (aplica desde a baseline) e anterior ao runner (**carimba** na baseline, sem recriar
nada). O terceiro caminho é fail-closed — antes de carimbar, o runner confere que as
colunas que o bootstrap aditivo acrescentava estão presentes e **recusa** um banco
defasado em vez de carimbá-lo como se estivesse em dia.

O primeiro deploy com o runner é o que exercita o caminho de carimbo contra o banco real do
ambiente; a rodada da orçamentista não é recriada em nenhuma hipótese.

Imagem é sempre endereçada pelo SHA do commit; `latest` não é usado em lugar nenhum.

### Os dois schemas do banco

Um banco (`neondb`), dois schemas, e **nenhum dos dois é `public`**:

| Schema | Dono | Quem aponta para ele |
|---|---|---|
| `croquito` | API, worker e job de banco | `options=-csearch_path=croquito` no DSN de `croquito-hml-database-url` |
| `keycloak` | Keycloak | `KC_DB_SCHEMA=keycloak` no deploy **e** `currentSchema=keycloak` no JDBC |

Os dois DSNs são compostos pelo Terraform em `biahflow/infra`
([ADR-0031](../adr/0031-segredo-de-homologacao-gerenciado-por-terraform.md)); `KC_DB_SCHEMA`
mora no deploy porque é opção de runtime do container, não credencial.

**`KC_DB_SCHEMA` é o que move o DDL do Keycloak; `currentSchema` não.** O parâmetro do JDBC
muda o `search_path` da sessão, e o Liquibase do Keycloak cria tabela no schema padrão dele,
que é `public` até alguém dizer o contrário. Entre 2026-08-18 e o conserto deste documento o
DSN dizia `currentSchema=keycloak`, o schema `keycloak` não existia, e as ~88 tabelas do
Keycloak conviviam em `public` com as 19 da aplicação. Criar o schema sem mais nada teria
sido pior que deixar como estava: o Keycloak passaria a olhar para um schema vazio e perderia
realm e usuários.

**Os schemas são criados fora do código**, junto com a branch do Neon — o stack de infra lê o
banco e não manda nele (ADR-0031, D1.1). Ao nascer um ambiente, uma vez:

```sql
CREATE SCHEMA IF NOT EXISTS croquito;
CREATE SCHEMA IF NOT EXISTS keycloak;
```

Esquecer esse passo não corrompe nada: `search_path` com um schema só e sem `public` no fim
faz `current_schema()` virar NULL, o job de banco falha em `no schema has been selected to
create in` e o deploy para antes de publicar revisão nova. É a mesma escolha de falhar
fechado do runner de migrations — o que não se pode admitir é a queda silenciosa para
`public`.


## Como ver o que aconteceu

```bash
# log recente de um serviço (últimos 60 minutos por padrão do comando)
gcloud run services logs read croquito-scene-hml --region us-east1 --limit 100

# quem está servindo agora, e com qual imagem
gcloud run services describe croquito-scene-hml --region us-east1 \
  --format='value(status.url, status.latestReadyRevisionName, spec.template.spec.containers[0].image)'

# revisões, da mais nova para a mais antiga
gcloud run revisions list --service croquito-scene-hml --region us-east1
```

O que os logs podem conter é o que a política do repositório já define: id opaco, stage,
duração, status, código de erro, modelo, tokens, custo e contagens. Imagem, texto
integral, cota, token e URL assinada **nunca**.

## Rollback

Duas camadas, nesta ordem.

1. **Imediato, sem build** — aponta o tráfego para a revisão anterior:

   ```bash
   gcloud run revisions list --service croquito-scene-hml --region us-east1
   gcloud run services update-traffic croquito-scene-hml --region us-east1 \
     --to-revisions=croquito-scene-hml-00042-abc=100
   ```

   Vale para qualquer um dos quatro serviços. Toda revisão carrega a imagem do SHA que a
   gerou, então voltar é apontar — não é reconstruir.

   Ressalva de credencial: apontar para uma revisão anterior **não** volta o segredo. O
   serviço monta o secret por `:latest` e o relê ao subir, então a revisão antiga sobe com o
   valor corrente. Voltar um segredo é reabilitar a versão anterior no Secret Manager e
   publicar de novo.

2. **Definitivo** — `git revert` do commit e novo deploy pela esteira.

Ressalva de banco: as migrations são **forward-only** por decisão
([ADR-0029](../adr/0029-runner-de-migrations-revisadas.md), D2). Voltar a revisão anterior
da aplicação não desfaz DDL aplicada, e não existe `downgrade` em ambiente hospedado:
reverter é apontar a revisão anterior da imagem, e o código antigo precisa tolerar o schema
novo — que é o que expand/contract garante. Coluna sai em trabalho posterior ao que parou
de usá-la, nunca no mesmo, e remoção continua exigindo aprovação humana explícita.

## Fumaça

```bash
make smoke-hml                                   # borda pública
make smoke-hml BASE_URL=https://<serviço>.run.app  # direto no Cloud Run, sem a CDN
```

É o mesmo `scripts/smoke_hml.py` que o passo final da esteira roda, e ele não precisa de
credencial nenhuma. As quatro rotas (`/revisao/`, `/medicao/`, `/api/v1/meta` e o discovery
OIDC) passam pelo nginx, que é o único serviço público; se elas respondem **com o conteúdo
certo**, o proxy same-origin, a jornada e a sessão autenticada estão de pé. A porta nova
também deve ser conferida manualmente:

```bash
BASE_URL=https://croquito-hml.biahflow.ai
curl -sS --max-redirs 0 -D - -o /dev/null "$BASE_URL/" | grep -E '^HTTP/.* 302|^Location: /login'
curl -fsS "$BASE_URL/login" | grep -F '/revisao/assets/'
```

O primeiro comando confirma `302` relativo para `/login`; o segundo confirma que `/login`
entrega o HTML da SPA e mantém os assets sob `/revisao/`.

**O domínio público passa pelo Cloudflare** (proxy de DNS), e a proteção de bot dele
devolve `403` a clientes que não parecem navegador (ex.: `Python-urllib`). Serviço
falando com serviço NÃO usa o host público: a API busca o JWKS pela URL direta do
`croquito-web-hml` no Cloud Run (`CROQUITO_OIDC_JWKS_URL`) — foi o incidente de
2026-08-19: todo token virava `INVALID_TOKEN` porque a API não conseguia baixar as
chaves pela borda pública.

**Não use `/api/healthz` para verificar a API daqui de fora.** O Cloud Run reserva `/healthz`
na raiz de todo serviço, e como o proxy remove o prefixo, esse caminho nunca chega ao
container: o 404 vem do Google, não do FastAPI. O `/healthz` continua servindo ao startup
probe, que chama o container direto. Era este o "bug de roteamento no GFE" que motivou o
rename de serviço em 2026-08-14 — não era bug, e o rename não tinha como resolver.

O conteúdo importa e não é preciosismo: a API precisa se identificar como `croquito-api`, o
discovery precisa anunciar o issuer da borda pública, a SPA precisa referenciar os próprios
assets e `/medicao/` precisa **redirecionar** para a jornada nova (`/revisao/?rodada=`) — o
endereço herdado da SPA que a F-003 aposentou, e que continua em favoritos de quem homologou.
Um `200` sozinho não prova nada — o container de exemplo do Cloud Run responde `200` em quase
todo caminho, e foi ele que ficou no lugar da API por quatro dias
([ADR-0031](../adr/0031-segredo-de-homologacao-gerenciado-por-terraform.md), D5).

O `croquito-jobs-hml` não tem fumaça externa por construção — ele só aceita chamada
autenticada do Pub/Sub, e a prova de vida dele é o job andar.

## Providers de IA

Status real: descrito em [ADR-0035](../adr/0035-suite-hospedada-openai-anthropic-direto.md)
(`Proposed`) e implementado pela [F-009](../features/F-009-suite-hospedada-sem-aws/feature.md).
A suite hospedada é Anthropic (braço primário) + OpenAI (reserva/contraparte) + Cloud Vision
(braço `ocr`, sempre ligado quando a suite real é construída) — sem Bedrock nem Textract; o
caminho AWS nunca rodou neste ambiente. Roteamento, fallback e semântica de falha em
[Model Routing](../ai/MODEL_ROUTING.md). O gate de autorização por documento (D6 do ADR-0035)
foi revisto pela [F-012](../features/F-012-operacao-saas-autorizacao-ia/feature.md)
([ADR-0036](../adr/0036-autorizacao-de-ia-contratual-sem-allowlist-documental.md), `Proposed`):
a allowlist por digest saiu do caminho hospedado e o gate passou a ser só entitlement + consent
+ teto + kill switch, ativado pela jornada Plataforma em vez de curl.

### Envs e segredos

O deploy do worker (`deploy-hml.yml`) já declara, comprometido na esteira:

| Variável | Onde | O que é |
|---|---|---|
| `CROQUITO_REAL_PROVIDERS_ENABLED` | env var, API e worker | kill switch — `false` desliga toda chamada paga sem redeploy de código |
| `CROQUITO_AI_MAX_ESTIMATED_COST_USD` | env var, worker | teto **por invocação** do worker (`5.00`), não por dia nem por job |
| `CROQUITO_OPENAI_MODEL` / `CROQUITO_ANTHROPIC_MODEL` | env var, worker | `gpt-5.6-sol` (braço desligado na rodada atual) / `claude-fable-5` (teste de 2026-08-20; reverter = `claude-opus-5`) |
| `CROQUITO_OPENAI_ARM_ENABLED` | env var, worker | interruptor do braço OpenAI (`true` quando ausente); `false` na rodada atual — só `true`/`false`, valor estranho recusa a suite |
| `CROQUITO_OPENAI_API_KEY` / `CROQUITO_ANTHROPIC_API_KEY` | secret, worker (`croquito-hml-openai-api-key` / `croquito-hml-anthropic-api-key`) | as duas chaves de provider; casca e IAM em `biahflow/infra`, valor pela esteira (ver abaixo) |

O braço OpenAI está **desligado por decisão humana de 2026-08-20** (pós-V12): a rodada segue
só com Anthropic + OCR e o pareamento com o segundo braço fica pausado, porque no V12 o
pareamento espacial casou leituras de caixas de extensões diferentes. O efeito é declarado no
pacote — extração de medida em braço único, nota `PROVIDER_FALLBACK_SINGLE_EXTRACTOR_ANTHROPIC`
e toda leitura ambígua ([Model Routing](../ai/MODEL_ROUTING.md)). Religar é trocar a flag para
`true` no `deploy-hml.yml`: `CROQUITO_OPENAI_API_KEY` continua montada no serviço de propósito,
para que religar não passe por secret.

O braço `ocr` (Cloud Vision) não usa chave própria: autentica pela conta de serviço de runtime
do worker, que precisa da API `vision.googleapis.com` habilitada no projeto — é o que o PR de
infra descrito no runbook de ativação, abaixo, faz.

### Runbook de ativação

Desde a [F-012](../features/F-012-operacao-saas-autorizacao-ia/feature.md)
([ADR-0036](../adr/0036-autorizacao-de-ia-contratual-sem-allowlist-documental.md)), ativar um
tenant não exige mais digest de documento nem redeploy: o gate de envio a provider passa a ser
só entitlement contratual do tenant + consent automático por job + teto por invocação + kill
switch. O que resta manual é o passo humano de conceder o papel no Keycloak e o gesto de ativar
o tenant pela tela.

**Infra, concluída uma única vez em 2026-08-19 (não se repete por tenant nem por documento).**
Os dois GitHub Actions secrets (`CROQUITO_OPENAI_API_KEY`, `CROQUITO_ANTHROPIC_API_KEY`) foram
criados no repositório `biahflow/infra` e a branch `feat/croquito-hml-providers` os levou, junto
de `google_project_service.vision` e da `lifecycle_rule` de 7 dias no bucket de artefatos, por
PR revisado no `plan` do stack `envs/hml/croquito`. O PR
[biahflow/infra#14](https://github.com/biahflow/infra/pull/14) foi mesclado; o primeiro `apply`
falhou com `403 Permission denied to enable service` — a conta de deploy `infra-deploy` não
tinha `serviceusage.services.enable` — e o PR
[biahflow/infra#15](https://github.com/biahflow/infra/pull/15) concedeu
`roles/serviceusage.serviceUsageAdmin` a ela. Após o merge do #15 e a reexecução do apply do
stack `hml_croquito`, tudo verde e verificado no projeto: os dois secrets com versão 1
`enabled`, `vision.googleapis.com` habilitada e a regra de retenção aplicada. O episódio fica
registrado porque ensina a ordem: mudança que habilita API nova exige o papel na conta de
deploy ANTES, e o filtro de paths de um PR de `wif` não re-arrasta `croquito` — o apply
interrompido precisa de reexecução explícita.

Ativação por tenant, hoje:

1. **Keycloak: papel `platform_operator` e `tenant_id`.** Pelo procedimento de
   [HML_KEYCLOAK](HML_KEYCLOAK.md), atribua o papel `platform_operator` a quem vai autorizar o
   tenant, e confirme o `tenant_id` do tenant que vai processar.

2. **Ativar pela jornada Plataforma.** Entre no produto autenticado com o papel
   `platform_operator` e abra `?plataforma=` (o botão "Plataforma" só aparece para quem tem o
   papel). A lista mostra o estado do entitlement de todo tenant com pegada no banco
   (entitlement, project ou upload); tenant que só existe no Keycloak ainda não aparece nela —
   para esse, use o campo de texto livre "ativar tenant novo" com o identificador exato. A
   ativação pede `agreement_reference`
   (referência lógica do contrato). A mutação viaja com `Idempotency-Key` e o mesmo contrato do
   `PUT` de sempre (ver
   [API Contract](../architecture/API_CONTRACT.md#autorização-contratual-de-ia)); não há mais
   curl nem token pescado do DevTools.

3. **Subir o PDF pela SPA depois da ativação.** Um job criado antes da ativação nasceu sem
   consent válido — ele não "acorda" sozinho quando o entitlement é ligado depois. Faça um
   novo upload do mesmo documento pela tela normal do produto, já autenticado, depois da
   ativação.

4. **Rollback: a flag.** `CROQUITO_REAL_PROVIDERS_ENABLED=false` no worker (e na API, se
   necessário) desliga toda chamada paga no próximo deploy, sem tocar segredo nem
   infraestrutura.

### Aviso de custo

`CROQUITO_AI_MAX_ESTIMATED_COST_USD` é teto **por invocação do worker**, não por dia nem por
job. O Pub/Sub reentrega até a DLQ (5 tentativas); no pior caso, um único job que falha e é
reentregue pode consumir até **5× o teto configurado** antes de cair na DLQ. Não é defeito — é
o comportamento fail-closed pretendido — mas é o número a ter em mente antes de conceder
entitlement a um tenant: sem allowlist por documento, o teto e o kill switch são a única
segunda camada.

## Custo

Três dos quatro serviços escalam a zero e o banco suspende por ociosidade. O item de custo
fixo do ambiente é o **Keycloak**: ele sobe em dezenas de segundos mesmo com imagem
otimizada, então manter instância quente (`min-instances=1`) é o que evita que o primeiro
login do dia espere o servidor nascer. É uma escolha de operação, não uma exigência técnica
— com `min-instances=0` o ambiente fica mais barato e o primeiro login fica lento.

## Lacunas declaradas

- ~~**Recursos do modo hospedado ainda provisionados.**~~ **Fechada em 2026-08-18.** O serviço
  `croquito-medicao-hml` e o bucket `croquito-hml-rounds` já não existem no projeto
  (verificado), e o stack de infraestrutura — que ainda os declarava e portanto os teria
  recriado no próximo apply — deixou de declará-los, junto com a runtime SA, esta sim ainda
  existente e destruída pelo apply. A rodada que estivesse naquele bucket **não foi migrada
  por ninguém**, por decisão humana registrada: ela permanece reproduzível pelo CLI. Com a medição na `/v1`, os limites que o
  [ADR-0026](../adr/0026-medicao-hospedada-sessao-autenticada-minima.md) declarava (uma rodada
  por ambiente, uma instância só, ausência de `base_version` real e de multi-tenant) deixaram
  de valer.
- **Papel `orcamentista` no realm de homologação.** As rotas de medição o exigem; conceder é
  ato humano, pelo procedimento de [HML_KEYCLOAK](HML_KEYCLOAK.md).
- **Retenção de sete dias** precisa estar no ciclo de vida dos buckets, e não apenas na
  política escrita.
- **Duas chaves HMAC ativas.** A chave do interop S3 passou a nascer no Terraform
  ([ADR-0031](../adr/0031-segredo-de-homologacao-gerenciado-por-terraform.md), D4); a
  anterior, criada fora dele, continua válida até ser desativada. Desativar é ato posterior ao
  deploy que passa a ler o secret novo — antes disso, a revisão em execução ainda assina com a
  chave velha.
- **Nenhum alerta quando o ambiente cai.** A esteira barrou no job de banco por quatro dias
  sem que ninguém soubesse. A fumaça agora falha ruidosamente no deploy, mas ambiente que
  ninguém deploya continua caindo em silêncio; observabilidade de homologação é trabalho
  próprio, ainda não feito.

A lacuna "migrations revisadas", declarada no
[ADR-0025](../adr/0025-homologacao-em-gcp-cloud-run.md) e aberta desde então, foi **fechada**
pelo [ADR-0029](../adr/0029-runner-de-migrations-revisadas.md): o job de banco descrito
acima é o runner. O que continua exigindo ato humano é a DDL destrutiva.
