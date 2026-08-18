# ADR-0031: Segredo de homologação gerenciado por Terraform

Status: Accepted
Data: 2026-08-18  
Responsável: Engineering

## Contexto

A homologação em GCP ficou fora do ar por quatro dias sem que nada no repositório soubesse
dizer isso. O diagnóstico executado em 2026-08-18, com consulta somente-leitura à borda
pública e ao projeto `biahflow-hml`, encontrou uma causa raiz única e uma secundária.

**O endereço do banco nos secrets aponta para um endpoint que não existe mais.** Os secrets
guardam o host `ep-still-firefly-audokk6w.c-10.us-east-1.aws.neon.tech`, que não pertence a
nenhum projeto da conta Neon; o endpoint corrente da homologação é outro. O proxy do Neon
roteia pelo hostname e responde a endpoint desconhecido com **falha de autenticação** — por
isso todos os consumidores relatam senha recusada, e por isso o diagnóstico inicial acusou uma
credencial vencida que estava, o tempo todo, correta:

- `croquito-auth-hml` sobe, falha em `Failed to obtain JDBC connection — password
  authentication failed for user 'neondb_owner'` e chama `exit(1)`. Cada requisição a `/auth/`
  dispara um cold start que morre, e o discovery OIDC responde **503**;
- o job `croquito-db-init-hml` falhou em 2026-08-17T14:12 com o mesmo erro. Como
  `.github/workflows/deploy-hml.yml` para no job de banco por desenho — "código novo contra
  schema velho é a forma mais barata de transformar deploy em incidente" —, **nenhuma revisão
  nova entra no ar desde 2026-08-14**. O portão funcionou; ninguém foi avisado;
- a API usa o mesmo banco (`croquito-hml-database-url`) e cairia igual.

A comparação que fechou o diagnóstico, feita por digest para não expor nenhuma das duas: a
senha gravada nos secrets é **idêntica** à senha corrente da role no Neon. O que diverge é o
host. Endereço de banco escrito à mão uma vez e nunca mais conferido é o defeito; a senha foi
só o sintoma que o proxy escolheu reportar.

**A API não estava publicada.** `croquito-scene-hml` serve, com 100% do tráfego, a revisão
`00003-kt9`, cuja imagem é `us-docker.pkg.dev/cloudrun/container/hello`. A revisão `00002-9kc`,
de cinco minutos antes, rodava a imagem real e subiu com sucesso. O container de exemplo foi
posto ali num teste manual de roteamento em 2026-08-14 e nunca revertido — e como a esteira
estava barrada pelo job de banco, nada o substituiu.

A política de segredo vigente até aqui está escrita no stack de infraestrutura
(`envs/hml/croquito/main.tf`, repositório `biahflow/infra`): as cascas dos secrets nascem no
Terraform, mas "versões entram por `gcloud secrets versions add`, nunca por Terraform nem por
CI do GitHub", e a chave HMAC do interop S3 é "criada fora do TF para o segredo não morar no
state". A intenção era proteger o state. O efeito medido foi outro: **coordenada de banco que
só um humano sabe atualizar é coordenada que ninguém atualiza** — o endpoint do Neon mudou, o
secret ficou apontando para o antigo, e o ambiente inteiro parou atrás disso. Não era um
segredo mal guardado; era um dado desatualizado que nenhum mecanismo reconciliava.

O [ADR-0025](0025-homologacao-em-gcp-cloud-run.md) declara que a casca dos serviços é criada
fora deste repositório. Isso continua verdade e não é o que muda aqui — o que muda é de que
lado da fronteira mora o **valor** da credencial, e como ele é trocado.

## Decisão

**D1. O valor dos segredos de homologação é Terraform.** Casca, IAM de leitura e versão
corrente saem do módulo `modules/secret-manager` do repositório `biahflow/infra`, consumido
pelo stack `envs/hml/croquito`. Propagar credencial passa a ser `terraform apply` revisado em
PR, e não um comando que alguém precisa lembrar de rodar.

**D1.1. O Terraform lê o banco, não manda nele.** O stack declara a **branch** do Neon por
nome (`staging`) e deriva dela o host do endpoint de escrita e a senha da role, compondo o DSN
da API e o JDBC do Keycloak. Nenhum hostname é escrito à mão — foi exatamente um hostname
escrito à mão que quebrou o ambiente. Ele **não cria, não rotaciona e não apaga** nada no
Neon: reconciliar é o que um `data` faz, e fazê-lo sem poder de escrita mantém o raio de ação
deste stack longe do banco. Se o endpoint mudar de novo, o conserto é um apply, não uma caçada.

**D2. O segredo que o Terraform produz mora no state, e isso é declarado.** `secret_data` é
argumento comum e é persistido. A alternativa write-only do provider (`secret_data_wo`) não
muda o quadro para este caso: os valores em questão nascem de recursos do próprio Terraform —
`google_storage_hmac_key.secret` e a senha de uma role de banco são `computed` e `sensitive` —,
portanto já estariam no state pela origem. A consequência operacional é única e não tem
meio-termo: **quem lê o state de `hml` lê as credenciais de `hml`**. Os buckets de state são
privados e versionados, e o acesso a eles passa a ser tratado como acesso a credencial.

**D3. Segredo que o Terraform não produz nasce como casca, sem versão.**
`croquito-hml-kc-bootstrap-admin-password` é o caso: `KC_BOOTSTRAP_ADMIN_PASSWORD` só age na
criação do primeiro admin, então gerar um valor novo não mudaria a senha do admin que já existe
no realm — só faria o secret divergir do mundo. Um secret sem versão é um estado honesto; um
secret com valor que ninguém honra, não.

**D4. A chave HMAC do interop S3 nasce no Terraform.** O GCS só devolve o segredo na criação:
adotar por `import` uma chave criada fora traria o campo vazio, e o secret gravado seria
mentira. A chave anterior permanece válida até ser desativada, o que é ato posterior ao deploy
que passa a usar a nova — desativar antes derrubaria o upload de artefato da revisão em
execução.

**D5. A fumaça da borda verifica conteúdo, não status.** `scripts/smoke_hml.py` é a mesma
verificação no runner do deploy e na máquina do operador (`make smoke-hml`), e confere o corpo
de cada rota: health precisa ser o JSON da API, o discovery precisa anunciar o issuer da borda
pública, cada SPA precisa referenciar os próprios assets. O incidente é a justificativa direta:
o container de exemplo responde `200` em quase todo caminho, e uma fumaça de status teria dito
"verde" durante os quatro dias de indisponibilidade. Junto sai o bypass condicional que pulava
a fumaça — fumaça que se pula sozinha ensina a confiar no verde errado.

**D6. A fronteira entre os dois repositórios fica explícita.** `biahflow/infra` é dono da casca
dos serviços, dos buckets, do Pub/Sub, do DNS e agora do valor das credenciais.
`biahflow/croquito` é dono da imagem, da revisão e das variáveis de ambiente, por
`deploy-hml.yml`. Nenhum dos dois escreve no território do outro, e o Cloud Run é o ponto onde
as duas propriedades se encontram: o serviço monta o secret por `:latest` e só o relê no
próximo deploy.

## Consequências

- Rotação de credencial vira mudança revisável, com plano legível em PR e histórico em commit.
  O que hoje é "alguém precisa lembrar" passa a ter dono e rastro.
- O state ganha material sensível. Quem tem `roles/storage.objectViewer` no bucket de state tem,
  na prática, as credenciais do ambiente — e a lista de quem tem esse acesso passa a ser uma
  decisão de segurança, não de conveniência.
- Ordem de operação passa a importar e está declarada: aplicar a infraestrutura **antes** do
  deploy da aplicação, porque o serviço em execução segue com o valor antigo até a próxima
  revisão. Rotacionar sem redeployar não conserta nada.
- O ambiente ganha um sinal que não tinha: com a fumaça sem bypass, um deploy que suba e não
  funcione falha ruidosamente em vez de terminar verde.
- Produção AWS ([ADR-0002](0002-aws-managed-architecture.md)) não é tocada. Esta decisão vale
  para homologação em GCP; estendê-la exige decisão própria.

## Alternativas rejeitadas

**Manter `gcloud secrets versions add` como caminho do valor.** É o estado que produziu o
incidente. A proteção que ele oferecia — segredo fora do state — não sobrevive ao fato de que a
chave HMAC e a senha de role, quando geradas pelo Terraform, entram no state pela origem.

**Write-only (`secret_data_wo`) para todos os valores.** Protegeria o secret version, não a
origem. Fica registrado como o caminho correto para valor que venha de fora do Terraform, e o
módulo pode passar a expô-lo sem reescrita quando houver esse caso.

**Gerenciar a role do Neon pelo Terraform** (`neon_role`), rotacionando a senha a cada apply.
Daria controle total, mas põe o stack em posição de escrever no banco de homologação para
resolver um problema que é de propagação, não de rotação. Um `data` resolve com raio de ação
menor. Se algum dia a rotação programada for requisito, o recurso existe no mesmo provider e o
caminho fica aberto.

**Migrar de Neon para Cloud SQL**, com instância, banco, usuário e senha inteiramente no
Terraform. Elimina o provider externo e a chave de API, mas é troca de fornecedor de banco, com
custo e migração de dados próprios. Se vier, vem como decisão de arquitetura, não como efeito
colateral de um conserto de credencial.
