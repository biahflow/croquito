# ADR-0029: Runner de migrations revisadas com Alembic

Status: Accepted  
Data: 2026-08-17  
Responsável: Engineering

## Contexto

O [ADR-0025](0025-homologacao-em-gcp-cloud-run.md) descreve como o schema nasce em homologação e,
no mesmo parágrafo, declara a dívida: o bootstrap aditivo "é uma lacuna declarada, não uma
solução: um runner de migrations revisadas continua sendo requisito de produção, e o bootstrap
não sabe alterar nem remover nada". A seção de consequências repete: "qualquer mudança de coluna
que exija alteração ou remoção não tem caminho automatizado hoje".

Hoje não existe runner nenhum. O único mecanismo de evolução de schema no repositório é
`Database.create_schema()` (`services/api/src/croquito_api/database.py:459-540`): um
`Base.metadata.create_all` seguido de **cinco** blocos de `ALTER TABLE … ADD COLUMN` guardados por
`inspect`, mais dois `CREATE UNIQUE INDEX IF NOT EXISTS`. O comentário na linha 464 diz o que ele
é: *"The local scaffold predates a migration runner."* Esse método é chamado por
`croquito_api.bootstrap` — via `make db-init` no ambiente local e como Cloud Run job
`croquito-db-init-hml`, antes de cada revisão da API — e por 24 pontos da suíte de testes, sobre
SQLite em arquivo.

O arranjo funciona enquanto toda mudança for aditiva e ninguém precisar saber em que estado um
banco está. Ele falha em três situações que já estão no caminho:

- **Coluna que muda de tipo, de nome ou que sai.** Não há caminho automatizado, e o próprio
  ADR-0025 registra isso como dívida assumida.
- **Saber o que já foi aplicado.** O banco não guarda versão de schema; o estado é inferido por
  `inspect` a cada execução, e um banco defasado é indistinguível de um banco em dia.
- **Esquecer a evolução.** Nada liga o modelo SQLAlchemy à DDL: alguém acrescenta coluna ao
  modelo, o `create_all` cria em banco novo, e o banco que já existe simplesmente não a tem.

O gatilho é concreto. O [ADR-0028](0028-medicao-na-api-v1-autenticada.md) decidiu duas tabelas
novas (`valuation_rounds`, `valuation_round_revisions`), e o contrato de
[F-003](../features/F-003-medicao-v1-migration/feature.md) proíbe "introduzir esquema sem caminho
de migration revisada, exportando dívida para produção". A ausência de runner é hoje o portão que
separa planejar aquela migração de executá-la.

Duas regras externas delimitam a decisão antes de ela ser tomada. Os guardrails de banco da
Engineering OS proíbem introduzir tecnologia de banco sem ADR — é por isso que este documento
existe — e exigem migrations *forward-only* com consideração explícita de rollback. O
[AGENTS.md](../../AGENTS.md) da raiz exige aprovação humana explícita para "migração destrutiva ou
irreversível de banco", e `services/api/AGENTS.md` já declara que "migrations seguem
expand/contract quando houver rolling deploy".

## Decisão

### D1 — O runner é o Alembic, com as migrations dentro do pacote

`alembic` entra como dependência de runtime (`[project].dependencies`, não grupo de
desenvolvimento: a imagem é construída com `uv sync --no-dev`). As migrations vivem em
`services/api/src/croquito_api/migrations/`, dentro do pacote que já contém os modelos, com
`env.py` e `versions/`.

Ficar dentro do pacote não é preferência de organização: a imagem instala os pacotes com
`--no-editable` (`docker/python.Dockerfile`), então em runtime o código roda de uma cópia dentro
do venv, sem `alembic.ini` e sem diretório de trabalho confiável. Por isso o runtime **não** usa
o CLI do Alembic: monta a configuração em Python, resolvendo o caminho das migrations pelo
próprio pacote instalado. O `alembic.ini` da raiz existe apenas para o CLI de desenvolvimento
gerar revisão nova.

### D2 — As migrations são forward-only

Não existe caminho de `downgrade` em ambiente hospedado ou de produção. Reverter aplicação é
apontar para a revisão anterior da imagem, como o ADR-0025 já descreve, e o código antigo precisa
tolerar o schema novo — que é exatamente o que expand/contract garante. Coluna sai em um trabalho
posterior ao que parou de usá-la, nunca no mesmo, e remoção continua exigindo aprovação humana
explícita.

### D3 — Um banco que já existe é adotado, não recriado

Neon em homologação e os volumes locais já têm tabelas criadas pelo bootstrap. O runner
reconhece três estados e trata cada um:

1. **Com controle de versão** — aplica o que falta.
2. **Sem controle de versão e vazio** — aplica desde a baseline.
3. **Sem controle de versão e com tabelas** — é um banco anterior ao runner: ele é **carimbado**
   na baseline e segue adiante, sem recriar nada.

O terceiro caminho é o perigoso, e por isso é fail-closed: antes de carimbar, o runner confere que
as colunas mais recentes — as que os blocos de `ALTER TABLE` de hoje acrescentavam — estão
presentes. Se faltar qualquer uma, ele **recusa** com erro explícito em vez de carimbar um banco
defasado como se estivesse em dia. Carimbo silencioso sobre banco incompleto seria a única forma
de este ADR piorar o que já existe.

### D4 — `create_schema()` deixa de evoluir banco

`Database.create_schema()` passa a ser `create_all` e nada mais. Ele continua servindo a suíte de
testes e a criação de banco novo; evoluir banco que já existe passa a ser exclusividade do runner.
Os cinco blocos de `ALTER TABLE` e os dois `CREATE UNIQUE INDEX` saem: o schema que eles produzem
é exatamente o que a migration de baseline descreve, e manter as duas descrições vivas criaria
duas verdades sobre a mesma tabela.

### D5 — Divergência entre modelo e migration é gate de CI

O CI ganha um PostgreSQL como serviço e um teste que aplica as migrations em banco limpo e exige
que a comparação entre o schema resultante e `Base.metadata` produza **nenhuma** operação. Modelo
alterado sem migration correspondente reprova o CI.

Isso é deliberadamente um portão automático e não uma regra de revisão: a falha que este ADR
existe para eliminar — modelo e banco divergirem em silêncio — é precisamente a que passa por
revisão humana sem ser vista. O teste é pulado quando não há PostgreSQL no ambiente, para que
`make test` continue rodando na máquina do desenvolvedor sem exigir serviço no ar.

### D6 — A esteira adota o runner no passo que já existe

O passo "Inicializa o schema" de `.github/workflows/deploy-hml.yml` continua sendo o mesmo Cloud
Run job, com o mesmo comando (`python -m croquito_api.bootstrap`), na mesma posição — antes da
revisão nova da API, falhando fechado. O que muda é o que o módulo faz. Nada é reordenado, porque
a ordem já está certa: "código novo contra schema velho é a forma mais barata de transformar
deploy em incidente".

### O que este ADR não decide

- **Qual banco a produção usa.** O [ADR-0002](0002-aws-managed-architecture.md) escolheu RDS num
  desenho que nunca foi aplicado, e a escolha de produção continua aberta. Este ADR decide como o
  schema evolui, em qualquer PostgreSQL.
- **O schema do Keycloak**, que tem migração própria do produto e não passa por aqui.
- **Se e quando remover coluna hoje órfã.** Remoção é trabalho próprio, com aprovação humana.
- **Migração de dados** (transformar linha existente), distinta de migração de schema. O primeiro
  caso que precisar dela decide seu padrão.
- **O destino das rodadas em bucket de homologação**, que segue como pendência do ADR-0028.

## Alternativas

- **Runner caseiro de SQL numerado** (tabela `schema_migrations` mais arquivos `NNN_nome.sql`
  aplicados em ordem). Rejeitado: a parte cara não é aplicar arquivo em ordem — são ~100 linhas —,
  é descobrir *o que* mudou entre o modelo e o banco. Escrever isso à mão é reimplementar a única
  parte do Alembic que evita erro humano, e sem ela o gate de drift da D5 não teria como existir.
- **Manter o bootstrap aditivo e proibir mudança não-aditiva.** Rejeitado: é o estado atual, e ele
  já está declarado como dívida em dois documentos. Também não resolve o problema de não saber em
  que estado um banco está, que aparece antes de qualquer mudança destrutiva.
- **Migrations na raiz do repositório**, no layout convencional do Alembic. Rejeitado: o runtime
  instala pacotes com `--no-editable` e não teria como resolver esse caminho; a alternativa seria
  copiar o diretório para dentro da imagem por fora do empacotamento, criando um segundo mecanismo
  de distribuição para o mesmo código.
- **Recriar o schema em homologação** em vez de adotá-lo. Rejeitado: descarta a rodada em
  homologação da orçamentista, que é dado real de trabalho em curso, para economizar um caminho
  de código executado uma única vez.
- **Rodar as migrations no start da aplicação**, em vez de job separado. Rejeitado: com mais de
  uma instância, duas subidas simultâneas disputariam a mesma DDL, e a falha de migration passaria
  a derrubar a aplicação em vez de parar o deploy antes dele acontecer.
- **Aplicar as migrations do CI contra o banco de homologação.** Rejeitado: não existe caminho de
  publicação a partir de máquina de desenvolvimento nem de fora da esteira (ADR-0025), e criar um
  seria abrir exatamente a porta que aquele ADR fechou.

## Consequências

### Positivas

- A dívida declarada no ADR-0025 deixa de existir: passa a haver caminho automatizado e revisado
  para alteração e remoção de coluna.
- O banco passa a saber em que versão está, e um banco defasado deixa de ser indistinguível de um
  banco em dia.
- F-003 perde o portão que a impedia de criar tabela, e o esquema decidido no ADR-0028 ganha
  caminho legítimo até o banco.
- Modelo e schema deixam de poder divergir em silêncio: a divergência vira falha de CI, com nome
  e linha.
- A migration de baseline documenta, num arquivo só e revisável, o schema que hoje está espalhado
  entre `create_all` e cinco blocos de DDL condicional.

### Negativas

- Uma dependência nova no runtime, num repositório que evita dependência por gosto.
- O CI fica mais lento e mais complexo: sobe um PostgreSQL que antes não existia.
- Acrescentar coluna passa a custar dois passos — modelo e migration — em vez de um. É o preço de
  o banco existente também receber a coluna.
- Volume local anterior a esta mudança deixa de ser consertado automaticamente pelos blocos de
  `ALTER`; o caminho passa a ser recriar o volume, aceitável porque local só tem dado sintético.
- O caminho de carimbo é código que roda uma vez por banco e depois nunca mais, e código assim é o
  menos exercitado que existe. Ele fica coberto por teste justamente por isso.

## Riscos e mitigação

| Risco | Mitigação |
|---|---|
| O banco de homologação divergir do que a baseline descreve, e o carimbo mentir | Conferência de coluna antes de carimbar, com recusa explícita; gate de drift provando que baseline e modelos coincidem; o job falha fechado antes de a revisão nova da API subir |
| Migration nova quebrar o deploy de homologação | O job roda antes da API e falha para o deploy, comportamento que já existe hoje; rollback é apontar para a revisão anterior da imagem (ADR-0025) |
| As migrations não entrarem na imagem por detalhe de empacotamento, e a falha só aparecer no deploy | O diretório de versões é pacote Python descoberto pelo empacotamento existente, e a construção da imagem entra na verificação da feature |
| Alguém usar `downgrade` em ambiente hospedado | Forward-only é decisão declarada aqui; reverter é apontar imagem, e remoção de coluna exige aprovação humana pelo AGENTS.md da raiz |
| O teste de drift ser pulado silenciosamente por falta de PostgreSQL e ninguém notar | O CI define o serviço e a variável; pular é comportamento de máquina de desenvolvedor, não do portão |
| Duas migrations criadas em paralelo em branches diferentes divergirem a linha de revisões | O Alembic detecta múltiplas cabeças e falha; resolver é ato explícito de quem integra |

## Rastreabilidade

- Requirements: fecha a lacuna declarada no
  [ADR-0025](0025-homologacao-em-gcp-cloud-run.md) ("um runner de migrations revisadas continua
  sendo requisito de produção"), que **não** é substituído — ele decide onde a homologação roda, e
  isso continua valendo. Desbloqueia a constraint de esquema de
  [F-003](../features/F-003-medicao-v1-migration/feature.md), cujo esquema foi decidido no
  [ADR-0028](0028-medicao-na-api-v1-autenticada.md). Preserva
  [ADR-0002](0002-aws-managed-architecture.md), que escolheu RDS para uma produção ainda não
  aplicada. Contrato de feature:
  [F-004](../features/F-004-migrations-runner/feature.md).
- Supersedes: none
- Superseded by: none
