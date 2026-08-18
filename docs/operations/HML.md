# Ambiente de homologação (GCP)

Status: Accepted  
Responsável: Platform / Engineering  
Última revisão: 2026-08-18

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
| `https://croquito-hml.biahflow.ai/` | `croquito-web-hml` | público | nginx: serve as SPAs e faz proxy do resto |
| `/revisao/` | `croquito-web-hml` | público | SPA da sessão de cena (`apps/web`) |
| `/medicao/` | `croquito-web-hml` | público | jornada de medição, na mesma SPA (`apps/web`) |
| `/api/` | `croquito-scene-hml` | interno | API FastAPI (`croquito_api.main:app`), inclusive as rotas de medição |
| `/auth/` | `croquito-auth-hml` | interno | Keycloak, realm `croquito` |
| — | `croquito-jobs-hml` | interno e privado | worker; recebe push do Pub/Sub em `POST /pubsub` |

Recursos de apoio: bucket `croquito-hml-artifacts` (documentos, previews e pacotes
exportados); tópico `projects/biahflow-hml/topics/croquito-hml-processing`; segredos
`croquito-hml-*` no Secret Manager; PostgreSQL gerenciado (Neon) para a API e para o
Keycloak, em schemas separados.

Nada disso é criado por este repositório: a casca do ambiente — serviços, bucket, Pub/Sub,
DNS, segredos e a chave HMAC — é Terraform em `biahflow/infra`, stack `envs/hml/croquito`.
Aqui mora a imagem e a revisão. A fronteira está no
[ADR-0031](../adr/0031-segredo-de-homologacao-gerenciado-por-terraform.md), D6.

Cada serviço roda com a própria conta de serviço
(`<serviço>@biahflow-hml.iam.gserviceaccount.com`), atribuída pelo deploy.

## Estado verificado

**Última verificação: 2026-08-18, `make smoke-hml` — as duas SPAs respondem; API e Keycloak
não.** `/api/healthz` responde 404 e o discovery OIDC responde 503, ou seja, a sessão
autenticada de homologação não sobe. É o mesmo resultado da fumaça de 2026-08-17T20:40Z
registrada na [seção 11 do evidence de F-001](../features/F-001-roadmap-clarification/evidence.md).

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
credencial nenhuma. As quatro rotas (`/revisao/`, `/medicao/`, `/api/healthz` e o discovery
OIDC) passam pelo nginx, que é o único serviço público; se elas respondem **com o conteúdo
certo**, o proxy same-origin e as duas SPAs estão de pé.

O conteúdo importa e não é preciosismo: o health precisa ser o JSON da API, o discovery
precisa anunciar o issuer da borda pública e cada SPA precisa referenciar os próprios assets.
Um `200` sozinho não prova nada — o container de exemplo do Cloud Run responde `200` em quase
todo caminho, e foi ele que ficou no lugar da API por quatro dias
([ADR-0031](../adr/0031-segredo-de-homologacao-gerenciado-por-terraform.md), D5).

O `croquito-jobs-hml` não tem fumaça externa por construção — ele só aceita chamada
autenticada do Pub/Sub, e a prova de vida dele é o job andar.

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
