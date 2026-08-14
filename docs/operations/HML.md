# Ambiente de homologação (GCP)

Status: Accepted  
Responsável: Platform / Engineering  
Última revisão: 2026-08-14

Fonte única do ambiente hospedado. A decisão e as alternativas estão no
[ADR-0025](../adr/0025-homologacao-em-gcp-cloud-run.md); o desenho AWS de
[AWS Deployment](../architecture/AWS_DEPLOYMENT.md) é o alvo de **produção** e não
descreve o que está no ar.

## O que está no ar

Projeto `biahflow-hml`, região `us-east1`, registro
`us-east1-docker.pkg.dev/biahflow-hml/hml`.

| Rota pública | Serviço Cloud Run | Ingress | O que é |
|---|---|---|---|
| `https://croquito-hml.biahflow.ai/` | `croquito-web-hml` | público | nginx: serve as SPAs e faz proxy do resto |
| `/revisao/` | `croquito-web-hml` | público | SPA da sessão de cena (`apps/web`) |
| `/medicao/` | `croquito-web-hml` | público | SPA da medição (`apps/medicao`) |
| `/api/` | `croquito-api-hml` | interno | API FastAPI (`croquito_api.main:app`) |
| `/auth/` | `croquito-auth-hml` | interno | Keycloak, realm `croquito` |
| `/medicao/api/` | `croquito-medicao-hml` | interno | servidor de medição (`serve --hosted`) |
| — | `croquito-worker-hml` | interno e privado | worker; recebe push do Pub/Sub em `POST /pubsub` |

Recursos de apoio: buckets `croquito-hml-artifacts` (documentos, previews e pacotes
exportados) e `croquito-hml-rounds` (rodada da medição, montada por FUSE em
`/mnt/rounds`); tópico `projects/biahflow-hml/topics/croquito-hml-processing`; segredos
`croquito-hml-*` no Secret Manager; PostgreSQL gerenciado (Neon) para a API e para o
Keycloak, em schemas separados.

Cada serviço roda com a própria conta de serviço
(`<serviço>@biahflow-hml.iam.gserviceaccount.com`), atribuída pelo deploy.

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
(`croquito-db-init-hml`, bootstrap aditivo) → API → worker → Keycloak → medição → nginx →
fumaça. Falha no job de banco para o deploy antes de qualquer revisão nova entrar no ar.

Imagem é sempre endereçada pelo SHA do commit; `latest` não é usado em lugar nenhum.

## Como ver o que aconteceu

```bash
# log recente de um serviço (últimos 60 minutos por padrão do comando)
gcloud run services logs read croquito-api-hml --region us-east1 --limit 100

# quem está servindo agora, e com qual imagem
gcloud run services describe croquito-api-hml --region us-east1 \
  --format='value(status.url, status.latestReadyRevisionName, spec.template.spec.containers[0].image)'

# revisões, da mais nova para a mais antiga
gcloud run revisions list --service croquito-api-hml --region us-east1
```

O que os logs podem conter é o que a política do repositório já define: id opaco, stage,
duração, status, código de erro, modelo, tokens, custo e contagens. Imagem, texto
integral, cota, token e URL assinada **nunca**.

## Rollback

Duas camadas, nesta ordem.

1. **Imediato, sem build** — aponta o tráfego para a revisão anterior:

   ```bash
   gcloud run revisions list --service croquito-api-hml --region us-east1
   gcloud run services update-traffic croquito-api-hml --region us-east1 \
     --to-revisions=croquito-api-hml-00042-abc=100
   ```

   Vale para qualquer um dos cinco serviços. Toda revisão carrega a imagem do SHA que a
   gerou, então voltar é apontar — não é reconstruir.

2. **Definitivo** — `git revert` do commit e novo deploy pela esteira.

Ressalva de banco: o bootstrap é **aditivo**, então voltar a revisão anterior da aplicação
não desfaz coluna criada. Coluna nova é ignorada por código antigo; o que não existe hoje é
caminho automatizado para alteração ou remoção (lacuna declarada no
[ADR-0025](../adr/0025-homologacao-em-gcp-cloud-run.md)).

## Fumaça manual

```bash
curl -sf https://croquito-hml.biahflow.ai/api/healthz
curl -sf https://croquito-hml.biahflow.ai/auth/realms/croquito/.well-known/openid-configuration
```

As duas rotas passam pelo nginx, que é o único serviço público; se elas respondem, o proxy
same-origin está de pé. O `croquito-worker-hml` não tem fumaça externa por construção — ele
só aceita chamada autenticada do Pub/Sub, e a prova de vida dele é o job andar.

## Custo

Quatro dos cinco serviços escalam a zero e o banco suspende por ociosidade. O item de custo
fixo do ambiente é o **Keycloak**: ele sobe em dezenas de segundos mesmo com imagem
otimizada, então manter instância quente (`min-instances=1`) é o que evita que o primeiro
login do dia espere o servidor nascer. É uma escolha de operação, não uma exigência técnica
— com `min-instances=0` o ambiente fica mais barato e o primeiro login fica lento.

## Lacunas declaradas

- **`redirect_uri` da SPA de cena.** `apps/web` monta `redirect_uri` como
  `${window.location.origin}/`, e o realm de homologação autoriza
  `/revisao/*` e `/medicao/*`. Servir a SPA em subpath exige que o app passe a compor o
  `redirect_uri` com o base path (ou que o realm autorize a raiz). Fica com a entrega do
  nginx/SPA, e sem isso o login não fecha.
- **`serve --hosted`** (Bearer JWT, papel `orcamentista`, CORS do host público) está
  decidido no [ADR-0026](../adr/0026-medicao-hospedada-sessao-autenticada-minima.md) e
  ainda não implementado: até lá o serviço `croquito-medicao-hml` recusa subir por falta da
  flag, o que é o desfecho correto — servidor sem autenticação não deve nascer em host
  público.
- **Retenção de sete dias** precisa estar no ciclo de vida dos buckets, e não apenas na
  política escrita.
- **Migrations revisadas**: o ambiente usa bootstrap aditivo, descrito acima.
