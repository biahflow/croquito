# FEATURE EXECUTION PLAN — F-006

feature_id: F-006
goal: Devolver a homologação em GCP ao ar e tornar o conserto repetível — a credencial do
banco passa a ser gerenciada por Terraform no repositório central de infraestrutura, a
imagem real volta a servir a API, e a fumaça da borda passa a verificar conteúdo, de modo que
o mesmo modo de falha não possa mais passar por verde.
assumptions: O [Feature Contract](feature.md) é autoritativo; o
[ADR-0031](../../adr/0031-segredo-de-homologacao-gerenciado-por-terraform.md) é a decisão
técnica e precisa de aceitação humana antes do apply; o repositório `biahflow/infra` é dono
da casca do ambiente e `biahflow/croquito` é dono da imagem e da revisão; `apply` e merge em
`main` são atos humanos.
risks: Um bloco `moved` ausente ou errado destrói os sete secrets e derruba o ambiente
inteiro — mitigado por plano revisado por humano, com zero destroy de secret como critério de
aceite, e por `moved` sem índice, que adota todas as instâncias do `for_each` de uma vez.
Escrever o HCL do Neon sem levantar a topologia real produziria um stack que segura
credenciais e não corresponde ao mundo — mitigado transformando o levantamento em tarefa
própria, bloqueante, em vez de adivinhar. Rotacionar a credencial sem redeployar não conserta
nada, porque o serviço só relê o secret ao subir — mitigado fixando a ordem (apply, depois
deploy) no contrato e na documentação de operação.

## Tasks

### F006-T01

- role: builder
- goal: Módulo `secret-manager` no repositório central de infraestrutura.
- scope: Criar `modules/secret-manager/` com `main.tf`, `variables.tf`, `outputs.tf`,
  `versions.tf` e `README.md`, na convenção de `modules/cloud-run-service`. Interface:
  `secrets` (nome → acessores) e `valores` (nome → valor, sensível, opcional). Versão nasce
  com `create_before_destroy` e `deletion_policy = "DISABLE"`.
- out_of_scope: Qualquer recurso de Cloud Run, bucket ou DNS; valor de segredo escrito no
  repositório.
- expected_areas: `modules/secret-manager/`
- acceptance_criteria: secret sem entrada em `valores` nasce como casca, sem versão; `for_each`
  não recebe valor sensível; o README declara que o valor gerenciado mora no state e por que
  `secret_data_wo` não muda esse fato para os valores deste stack.
- depends_on: []
- validation: `terraform fmt -check -recursive` e `terraform validate` do stack consumidor.
- risk: Marcar a variável inteira como sensível quebraria o `for_each`.
- relative_effort: S
- status: `DONE`

### F006-T02

- role: builder
- goal: Stack `envs/hml/croquito` consumindo o módulo, sem recriar secret nenhum.
- scope: Trocar o bloco inline de secrets por `module "secrets"`, com blocos `moved` para as
  cascas e para os bindings. Atualizar o cabeçalho do stack, que declarava a política antiga.
- out_of_scope: Mudar quem lê cada secret; mexer em serviço, bucket ou DNS.
- expected_areas: `envs/hml/croquito/main.tf`
- acceptance_criteria: as chaves do `for_each` são idênticas nos dois lados; o plano não
  destrói nem recria nenhum secret.
- depends_on: [F006-T01]
- validation: `terraform plan` revisado por humano.
- risk: `moved` com índice, ou faltando, produzindo destroy silencioso.
- relative_effort: S
- status: `DONE` (código), plano **não verificado** — ver F006-T07

### F006-T03

- role: builder
- goal: Chave HMAC do interop S3 nascendo no Terraform.
- scope: `google_storage_hmac_key` para a SA `croquito-hml-storage`, alimentando
  `croquito-hml-storage-hmac-id` e `-secret`. Registrar por que a chave anterior não é
  adotada nem desativada no mesmo passo.
- out_of_scope: Desativar a chave anterior.
- expected_areas: `envs/hml/croquito/main.tf`, `envs/hml/croquito/outputs.tf`
- acceptance_criteria: o `access_id` sai como output (metade pública); o segredo não aparece
  em output nenhum.
- depends_on: [F006-T01]
- validation: `terraform validate`.
- risk: Importar a chave existente traria o segredo vazio e o secret gravado seria mentira.
- relative_effort: S
- status: `DONE`

### F006-T04

- role: builder
- goal: Remover o modo hospedado do stack antes que um apply o ressuscite.
- scope: Remover `module "medicao"`, a runtime SA `croquito-medicao-hml`, o bucket
  `croquito-hml-rounds`, o binding correspondente e os outputs relacionados.
- out_of_scope: Esvaziar o bucket.
- expected_areas: `envs/hml/croquito/main.tf`, `envs/hml/croquito/outputs.tf`
- acceptance_criteria: nenhuma referência a `medicao` ou `rounds` sobra no stack; o comentário
  explica que serviço e bucket já não existiam e que o apply os teria recriado.
- depends_on: []
- validation: `grep` no stack e `terraform validate`.
- risk: Verificado em 2026-08-18 que serviço e bucket já não existem, então o único destroy
  real é a runtime SA. Se o bucket voltasse a existir com objeto dentro, o destroy pararia por
  falta de `force_destroy` — e esvaziar seria ato consciente, não algo que o stack faça.
- relative_effort: S
- status: `DONE`

### F006-T05

- role: builder
- goal: Fumaça da borda versionada, verificando conteúdo.
- scope: `scripts/smoke_hml.py` (só biblioteca padrão) e alvo `smoke-hml`; passo de fumaça da
  esteira usando o mesmo script; remover o bypass condicional.
- out_of_scope: Alerta ou monitoramento contínuo.
- expected_areas: `scripts/smoke_hml.py`, `Makefile`, `.github/workflows/deploy-hml.yml`
- acceptance_criteria: health precisa ser o JSON da API, discovery precisa anunciar o issuer
  da borda pública, cada SPA precisa referenciar os próprios assets; a fumaça falha fechada.
- depends_on: []
- validation: `uv run python scripts/smoke_hml.py`; `ruff`, `mypy`.
- risk: Verificar só o status deixaria o container de exemplo passar por verde.
- relative_effort: M
- status: `DONE`

### F006-T06

- role: builder
- goal: Provider Neon no stack, propagando a credencial corrente do banco.
- scope: Levantar a topologia real; usar `data "neon_project"` para ler host, database, usuário
  e senha correntes; compor o DSN psycopg da API e o JDBC do Keycloak, alimentando
  `croquito-hml-database-url`, `croquito-hml-kc-db-url`, `-user` e `-password`.
- out_of_scope: Criar, rotacionar ou apagar qualquer coisa no Neon; migrar de fornecedor.
- expected_areas: `envs/hml/croquito/`, `.github/workflows/*.yml` (credencial do provider)
- acceptance_criteria: nenhum valor de banco depende de ato manual; o DSN da API e o JDBC do
  Keycloak saem da mesma fonte, sem senha escrita à mão em lugar nenhum; o stack não tem poder
  de escrita sobre o banco.
- depends_on: [F006-T01]
- validation: `terraform validate` (feito); `terraform plan`; depois do apply, o job de banco
  executa com sucesso.
- risk: `neon_project_id` apontando para o projeto errado gravaria credencial de outro banco —
  por isso a variável não tem default.
- relative_effort: M
- status: `DONE` (código), **valores pendentes** — `NEON_API_KEY` e `NEON_PROJECT_ID`

### F006-T07

- role: builder
- goal: Plano do Terraform revisado, com zero destroy de secret.
- scope: `terraform plan` do stack e conferência item a item: sete secrets adotados, destroy
  apenas dos recursos do modo hospedado, criação apenas da HMAC e das versões novas.
- out_of_scope: `apply`, que é ato humano.
- expected_areas: —
- acceptance_criteria: o plano não destrói nem recria secret; todo destroy é nomeado e
  esperado.
- depends_on: [F006-T02, F006-T03, F006-T04, F006-T06]
- validation: `terraform plan` publicado no PR.
- risk: Aplicar sem ler o plano.
- relative_effort: S
- status: **PARCIAL** — a adoção está verificada (17 de 17 secrets movidos, zero recriação;
  destroy só da SA do modo hospedado), mas as versões novas de secret não entraram no plano
  porque ele para no provider Neon sem a chave. Falta o plano completo.

### F006-T08

- role: builder
- goal: Reconciliar a documentação com o que foi medido.
- scope: ADR-0031; `HML.md` (estado verificado, ordem de deploy, fumaça, lacunas);
  `deploy/nginx.conf` (comentário do "bug de GFE"); `STATUS.md`; `ROADMAP.md`; artefatos de
  F-006.
- out_of_scope: Editar o evidence de F-001, que é registro do que era verdade naquela data.
- expected_areas: `docs/`
- acceptance_criteria: nenhum documento afirma disponibilidade sem data e medição; `make
  check` verde, incluindo o validador de links.
- depends_on: [F006-T05]
- validation: `make check`.
- risk: Corrigir o ambiente e deixar o documento afirmando o que não é.
- relative_effort: M
- status: `DONE`

### F006-T09

- role: builder
- goal: Publicar F-003 em `main` e verificar o ambiente de pé.
- scope: Merge depois do apply da infraestrutura; acompanhar a esteira; rodar `make smoke-hml`;
  re-medir a anomalia do `/healthz` com a imagem real servindo.
- out_of_scope: Homologação real da orçamentista.
- expected_areas: —
- acceptance_criteria: quatro rotas verdes; job de banco com sucesso; `croquito-scene-hml`
  servindo `croquito-python:<sha>`.
- depends_on: [F006-T07]
- validation: `make smoke-hml`.
- risk: Se a fumaça falhar, a causa pode ser o conserto ou a F-003.
- relative_effort: S
- status: **BLOQUEADO** — depende do apply

## critical_path

F006-T01 → F006-T02 → F006-T06 → F006-T07 → F006-T09

## integration_strategy

Dois repositórios, duas rodadas. A infraestrutura vai primeiro, em PR próprio, porque o
serviço só relê o secret ao subir: rotacionar depois do deploy não conserta nada. O croquito
vai em seguida, e é o deploy que substitui o container de exemplo pela imagem real e exercita
o carimbo do Alembic contra o banco.

## human_gates

- Aceitação do ADR-0031.
- Revisão do plano e `terraform apply`.
- Merge da F-003 em `main`.
- Concessão do papel `orcamentista` no realm.
- Desativação da chave HMAC anterior, depois do deploy.
