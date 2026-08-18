# F-006 — Conserto e verificação da homologação em GCP

## Status

`DONE`

> **2026-08-18, medido**: o ambiente subiu e a fumaça prova que subiu — quatro rotas verdes na
> esteira, com o discovery anunciando o issuer da borda pública, e os quatro serviços servindo
> `:3acbcc1`. Cinco dos seis critérios de aceite estão atendidos; o critério 4 (o **carimbo**
> do Alembic contra banco preexistente) não é atendível por este deploy, como `Unknowns` já
> declarava, e segue como ato aberto de [F-004](../F-004-migrations-runner/feature.md).
>
> Uma correção fora do escopo original entrou na mesma rodada, e a janela para fazê-la sem
> perda era exatamente esta: Keycloak e aplicação **compartilhavam o schema `public`**, ao
> contrário do que `HML.md` afirmava. Detalhe e medições na seção 3.4 do
> [evidence](evidence.md).
>
> O ADR-0031 foi aceito por ato humano em 2026-08-18, e as pendências operacionais da seção 5
> foram declaradas concluídas pelo responsável humano. F-006 está `DONE`. O critério 4 continua
> explicitamente não atendido e não atendível neste deploy, seguindo como follow-up de F-004;
> não é apresentado como critério verde.

> Selecionada por decisão humana de 2026-08-18, a partir do levantamento de features abertas:
> as cinco features anteriores estão `DONE`, e o que restava delas eram atos de produção que o
> ambiente no chão impedia de executar.
>
> A decisão técnica é o
> [ADR-0031](../../adr/0031-segredo-de-homologacao-gerenciado-por-terraform.md), `Accepted` por
> ato humano em 2026-08-18.
> Duas decisões humanas da mesma data moldam o escopo: o valor dos segredos passa a ser
> gerenciado por Terraform no repositório central de infraestrutura (sem `gcloud`, sem passo
> manual), e a [F-003](../F-003-medicao-v1-migration/feature.md) vai para `main` na mesma
> rodada do conserto.

## Priority

`HIGH` — não por valor de produto, mas porque é o portão de tudo que está pendente: os atos
de produção de F-003 (papel `orcamentista`, borda sem `/medicao/api/`), o ato de F-004
(primeiro deploy com o runner, que exercita o carimbo contra o banco real) e a homologação
real da orçamentista dependem de um ambiente que sobe.

## Problem

A homologação está fora do ar desde 2026-08-14 e o repositório não sabia dizer isso. A
fumaça de 2026-08-17T20:40Z, registrada na
[seção 11 do evidence de F-001](../F-001-roadmap-clarification/evidence.md), mediu
`GET /api/healthz` → 404 e o discovery OIDC → 503, e declarou o conserto como trabalho
próprio. `docs/operations/HML.md` seguia afirmando, no presente, que API e Keycloak estavam
em operação.

O diagnóstico de 2026-08-18 (somente leitura, borda pública + projeto `biahflow-hml`)
encontrou:

- **Causa raiz: o endereço do banco nos secrets aponta para um endpoint do Neon que não existe
  mais.** `neondb_owner` é recusado por senha em todos os consumidores, mas a senha gravada é
  idêntica à corrente (comparada por digest): o proxy do Neon roteia pelo hostname e responde a
  endpoint desconhecido com falha de autenticação. O Keycloak falha no boot com `Failed to
  obtain JDBC connection` e chama `exit(1)` — daí o 503. O job `croquito-db-init-hml` falhou em
  2026-08-17T14:12 pelo mesmo motivo e, como a esteira para no job de banco por desenho,
  **nenhuma revisão nova entra no ar desde 2026-08-14**.
- **Causa secundária: a API não está publicada.** `croquito-scene-hml` serve, com 100% do
  tráfego, uma revisão cuja imagem é `us-docker.pkg.dev/cloudrun/container/hello`. A revisão
  anterior rodava a imagem real e subiu com sucesso. O container de exemplo entrou num teste
  manual de roteamento em 2026-08-14 e nunca saiu — e a esteira, barrada, não o substituiu.
- **O "bug de GFE" não explica o 404 de hoje.** A causa conhecida de 404 naquele caminho tem
  conserto no stack de infraestrutura — sem a zona DNS privada `run.app` →
  `private.googleapis.com`, o egress VPC do proxy alcança os backends pelos IPs públicos e o
  ingress interno classifica a requisição como externa — e essa zona entrou no stack duas
  horas e meia **antes** do rename que o comentário de `deploy/nginx.conf` justifica.
- **O stack ainda declarava o modo hospedado.** `croquito-medicao-hml` e o bucket
  `croquito-hml-rounds` já não existem no projeto, mas o Terraform continuava sendo dono deles:
  o próximo apply os teria recriado, ressuscitando o que a F-003 removeu.

Por trás das duas causas há a mesma política: credencial que só um humano sabe trocar é
credencial que ninguém troca.

## Desired Outcome

A homologação sobe, a fumaça prova que subiu — e continuaria provando se cair de novo —, e a
troca de credencial deixa de depender de alguém lembrar de um comando.

## Scope

- **Repositório `biahflow/infra`**: módulo `modules/secret-manager` (casca, IAM e valor
  corrente); stack `envs/hml/croquito` consumindo o módulo com blocos `moved`; chave HMAC do
  interop S3 nascendo no Terraform; provider Neon **lendo** a credencial corrente do banco e
  alimentando os quatro secrets de banco; remoção do modo hospedado (serviço, SA e bucket
  `croquito-hml-rounds`); filtro do módulo novo no `plan.yml`/`apply.yml`.
- **Repositório `biahflow/croquito`**: `scripts/smoke_hml.py` + `make smoke-hml`, verificando
  conteúdo e não só status; passo de fumaça da esteira usando o mesmo script, sem o bypass
  condicional; ADR-0031; reconciliação de `HML.md`, `STATUS.md`, `ROADMAP.md` e do comentário
  de `deploy/nginx.conf`; merge da F-003 em `main`.

## Out of Scope

- **Produção AWS.** O [ADR-0002](../../adr/0002-aws-managed-architecture.md) segue valendo e
  nada aqui o toca.
- **Migrar o banco para Cloud SQL.** Registrado como alternativa rejeitada no ADR-0031: se
  vier, vem como decisão própria.
- **Observabilidade de homologação.** O ambiente caiu por quatro dias em silêncio; a fumaça
  agora falha ruidosamente no deploy, mas ambiente que ninguém deploya continua caindo sem
  aviso. Alerta é trabalho próprio.
- **A homologação real da orçamentista.** Esta feature devolve o ambiente; não substitui o
  ato.

## Acceptance Criteria

1. `terraform plan` do stack `envs/hml/croquito` **não destrói nem recria nenhum secret** — os
   sete são adotados pelos blocos `moved`.
2. O plano mostra, como destroy intencional e nomeado, apenas a runtime SA
   `croquito-medicao-hml` — serviço e bucket já não existem no projeto e saem do state por
   reconciliação, não por destruição.
3. Depois do apply e do deploy: `make smoke-hml` verde nas quatro rotas, com health devolvendo
   o JSON da API e o discovery anunciando o issuer da borda pública.
4. O job `croquito-db-init-hml` executa com sucesso, exercitando o carimbo do Alembic contra o
   banco real — ato pendente de F-004.
5. `croquito-scene-hml` serve `croquito-python:<sha>`, não o `hello`.
6. `make check` e `make test` verdes.

## Constraints

- **Ordem obrigatória**: apply da infraestrutura antes do deploy da aplicação. O serviço monta
  o secret por `:latest` e só o relê ao subir; rotacionar sem redeployar não conserta nada.
- **Nada manual** (decisão humana de 2026-08-18): a credencial entra por Terraform, não por
  `gcloud secrets versions add`.
- **`apply` é ato humano aprovado**, no CI do repositório de infraestrutura, com plano
  revisado — como já vale para qualquer mudança de infraestrutura.
- Segredo não aparece em log, em plano publicado no resumo do job, nem em mensagem de commit.

## Dependencies

- [ADR-0031](../../adr/0031-segredo-de-homologacao-gerenciado-por-terraform.md) foi aceito por
  ato humano antes do apply.
- Credencial de aplicação do GCP (`gcloud auth application-default login`) para rodar o plano
  localmente, e `NEON_API_KEY` para o provider Neon.
- [F-003](../F-003-medicao-v1-migration/feature.md) e
  [F-004](../F-004-migrations-runner/feature.md): esta feature fecha os atos de produção que
  ficaram abertos nas duas.

## Unknowns

- ~~Se o projeto Neon tiver sido recriado, o banco está vazio~~ — **confirmado em 2026-08-18**:
  as duas branches (`production` e `staging`) não têm nenhuma tabela nem `alembic_version`. O
  Alembic vai criar o schema desde a baseline, **não** carimbar banco preexistente: o critério 4
  não pode ser cumprido por este deploy, e o ato pendente de F-004 continua aberto. O realm do
  Keycloak também nasce sem usuários.
- **A anomalia do `/healthz`.** Sob `/api/`, só o path exato `/healthz` responde 404; qualquer
  outro responde 200 com o `hello`. Vale na borda e direto no `run.app`, então não é a CDN.
  Re-medir com a imagem real no ar, sem prejulgar.

## Risks

- ~~**`moved` faltando ou errado destrói os sete secrets**~~ — **verificado em 2026-08-18**: o
  plano adota 17 de 17 recursos de secret, sem nenhuma recriação.
- **O apply restaura `min_instance_count = 1` no Keycloak**, que hoje está em zero no ambiente.
  É o que o stack sempre declarou e o que evita cold start no primeiro login, mas é custo fixo
  — e apareceu como drift, não como escolha desta feature.
- **O state passa a conter credenciais** (ADR-0031, D2). Quem lê o state de `hml` lê as
  credenciais de `hml`, e a lista de quem tem esse acesso vira decisão de segurança.
- **Duas chaves HMAC ativas** até a antiga ser desativada — o que só pode acontecer depois do
  deploy que passa a ler o secret novo.
- **Rodada única com muita coisa mudando**: se a fumaça falhar depois do merge, a causa pode
  ser o conserto ou a F-003. Mitigação: o job de banco roda antes de tudo e falha fechado, e
  cada serviço tem revisão anterior para rollback por imagem.

## Human Gates

- ~~Aceitação do ADR-0031~~ — aceita por ato humano em 2026-08-18.
- `terraform apply` do stack, com plano revisado.
- Merge da F-003 em `main`.
- ~~Concessão do papel `orcamentista` no realm~~ — concluída por ato humano em 2026-08-18.
- ~~Desativação da chave HMAC anterior, depois do deploy~~ — concluída por ato humano em
  2026-08-18.

## References

- [ADR-0031](../../adr/0031-segredo-de-homologacao-gerenciado-por-terraform.md)
- [ADR-0025](../../adr/0025-homologacao-em-gcp-cloud-run.md)
- [HML](../../operations/HML.md), [HML_KEYCLOAK](../../operations/HML_KEYCLOAK.md)
- [evidence de F-001, seção 11](../F-001-roadmap-clarification/evidence.md)
