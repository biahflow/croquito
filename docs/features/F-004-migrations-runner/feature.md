# F-004 — Runner de migrations revisadas

## Status

`READY_FOR_HUMAN_REVIEW`

> Selecionada por decisão humana de 2026-08-17, na sequência da aceitação do
> [ADR-0028](../../adr/0028-medicao-na-api-v1-autenticada.md): o esquema da medição está
> decidido, e a ausência de runner é o portão que separa planejar
> [F-003](../F-003-medicao-v1-migration/feature.md) de executá-la.
>
> A decisão técnica é o [ADR-0029](../../adr/0029-runner-de-migrations-revisadas.md),
> **aceito por ato humano em 2026-08-17**. O guardrail global de banco, que proíbe introduzir
> tecnologia de banco sem ADR, está satisfeito, e a implementação está liberada.
>
> **A implementação foi entregue em `be82529`** (Alembic, adoção de banco preexistente por
> carimbo conferido e gate de drift com PostgreSQL no CI), com a validação determinística em
> [evidence.md](evidence.md). O estado ficou desatualizado neste contrato até 2026-08-17, quando
> a correção foi feita junto do fechamento de
> [F-005](../F-005-openapi-contract-test/feature.md). A transição para `DONE` depende da revisão
> humana, que ainda não ocorreu: a evidência registra revisão do modelo, e o risco residual
> declarado na seção 6 (FK ausente em banco adotado) continua aberto.

## Priority

`HIGH` — não por valor de produto, mas por ser pré-requisito declarado de F-003 e requisito de
produção registrado desde o [ADR-0025](../../adr/0025-homologacao-em-gcp-cloud-run.md).

## Problem

O ADR-0025 declara, sobre o schema em homologação: "Isso é uma lacuna declarada, não uma solução:
um runner de migrations revisadas continua sendo requisito de produção, e o bootstrap não sabe
alterar nem remover nada." A mesma dívida aparece em `docs/operations/HML.md`, na lista de
lacunas do ambiente, e em `services/api/src/croquito_api/bootstrap.py:3-6`.

O estado é verificável:

- Não existe runner. Sem Alembic (`pyproject.toml` não o declara), sem diretório de migrations,
  sem script versionado de DDL em nenhum lugar do repositório.
- O único mecanismo é `Database.create_schema()`
  (`services/api/src/croquito_api/database.py:459-540`): `Base.metadata.create_all` mais cinco
  blocos de `ALTER TABLE … ADD COLUMN` guardados por `inspect`, mais dois
  `CREATE UNIQUE INDEX IF NOT EXISTS`. O comentário da linha 464 declara: "The local scaffold
  predates a migration runner."
- O banco não guarda versão de schema. O estado é reinferido por `inspect` a cada execução, e um
  banco defasado é indistinguível de um banco em dia.
- Nada liga o modelo SQLAlchemy à DDL: coluna acrescentada ao modelo nasce em banco novo pelo
  `create_all` e simplesmente não existe no banco que já roda.

O gatilho é F-003. O ADR-0028 decidiu `valuation_rounds` e `valuation_round_revisions`, e o
contrato de F-003 proíbe "introduzir esquema sem caminho de migration revisada, exportando dívida
para produção" — além de listar, entre seus portões humanos, "decisão sobre o runner de
migrations antes de qualquer tabela".

## Desired Outcome

Um caminho automatizado, revisável e versionado para evoluir o schema em qualquer PostgreSQL do
projeto, com o banco declarando em que versão está; e um portão de CI que reprove modelo alterado
sem a migration correspondente. Ao fim, a lacuna do ADR-0025 deixa de existir e F-003 pode criar
tabela.

## Scope

- Adotar o Alembic como runner, com as migrations dentro de `croquito_api`, conforme o ADR-0029.
- Migration de baseline que descreve o schema atual por inteiro — o que hoje está espalhado entre
  `create_all` e os cinco blocos de DDL condicional.
- Reescrever `croquito_api.bootstrap` para aplicar migrations, mantendo o nome do módulo e o
  comando que a esteira já invoca. Ele passa a reconhecer banco com controle de versão, banco
  vazio e banco anterior ao runner — este último **adotado por carimbo**, com recusa explícita se
  as colunas mais recentes não estiverem presentes.
- Reduzir `Database.create_schema()` a `create_all`, para teste e banco novo.
- PostgreSQL como serviço no CI e teste que exige diferença **vazia** entre o schema das
  migrations e `Base.metadata`.
- Testes do caminho de adoção, da idempotência e da recusa fail-closed.
- Atualizar a esteira de homologação: mesmo passo, mesmo comando, comentário corrigido.
- Atualizar a documentação canônica que hoje descreve a lacuna como aberta.

## Out of Scope

- Qualquer migration de esquema **novo**: as tabelas da medição pertencem a F-003. Esta feature
  entrega o mecanismo, não o primeiro uso dele.
- Remover coluna hoje órfã, ou qualquer DDL destrutiva. Exige aprovação humana própria
  ([AGENTS.md](../../../AGENTS.md) da raiz).
- Migração de **dados** (transformar linha existente), distinta de migração de schema.
- O schema do Keycloak, que tem migração própria do produto.
- Decidir o banco de produção, que segue aberto no
  [ADR-0002](../../adr/0002-aws-managed-architecture.md).
- Executar deploy, `terraform apply` ou qualquer comando contra o banco de homologação. A esteira
  é o único caminho e ela roda por ato humano de merge.
- Provisionar banco em Terraform: `infra/` não tem recurso de banco e não ganha um aqui.

## Acceptance Criteria

- `python -m croquito_api.bootstrap` aplica as migrations contra PostgreSQL limpo e o banco passa
  a declarar sua versão de schema.
- Rodar o mesmo comando duas vezes seguidas não falha e não produz DDL na segunda vez.
- Banco criado pelo `create_all` sem controle de versão é **carimbado** na baseline, com as
  tabelas e os dados preservados; nenhuma tabela é recriada.
- Banco com tabela mas sem as colunas mais recentes faz o runner **recusar** com erro explícito,
  em vez de carimbar.
- Existe teste que aplica as migrations em banco limpo e falha quando a comparação com
  `Base.metadata` produz qualquer operação; ele é pulado, e não falha, quando não há PostgreSQL
  no ambiente.
- O CI sobe PostgreSQL e roda esse teste sem pular.
- `Database.create_schema()` não contém nenhum `ALTER TABLE`.
- A imagem construída por `docker/python.Dockerfile` contém as migrations — verificado por build,
  não por inspeção do código.
- `uv.lock` está atualizado e commitado: `uv sync --locked` e o build com `--frozen` passam.
- `make check` e `make test` passam, com a contagem de testes registrada antes da mudança.
- `git diff .github/workflows/deploy-hml.yml` não altera comando, ordem ou nome de job.
- Nenhum arquivo sob `infra/` é tocado, e o ADR-0025 permanece byte-idêntico.

## Constraints

- O guardrail global de banco exige migrations **forward-only** com consideração de rollback
  registrada, e proíbe alterar migration já aplicada fora do ambiente local.
- Migração destrutiva ou irreversível exige aprovação humana explícita (AGENTS.md da raiz).
- `services/api/AGENTS.md:24`: "Migrations seguem expand/contract quando houver rolling deploy."
- A imagem instala os pacotes com `uv sync --no-dev --no-editable`: a dependência precisa estar
  fora do grupo de desenvolvimento, e as migrations precisam ser distribuídas pelo empacotamento,
  sem depender de diretório de trabalho.
- Deploy só pela esteira, com imagem por SHA e WIF; não existe caminho a partir de máquina de
  desenvolvimento (ADR-0025).
- O job de banco roda **antes** da revisão nova da API e falha fechado. Essa ordem não muda.
- A rodada da orçamentista em homologação é dado real de trabalho em curso: nada pode recriá-la.

## Dependencies

- [ADR-0029](../../adr/0029-runner-de-migrations-revisadas.md) — aceito em 2026-08-17; era a
  dependência bloqueante da implementação.
- [ADR-0025](../../adr/0025-homologacao-em-gcp-cloud-run.md) (esteira, Neon, job de banco),
  [ADR-0028](../../adr/0028-medicao-na-api-v1-autenticada.md) (esquema que vai usar o runner).
- `services/api/src/croquito_api/{bootstrap.py,database.py}`, `docker/python.Dockerfile`,
  `.github/workflows/{ci.yml,deploy-hml.yml}`, `pyproject.toml`, `uv.lock`, `Makefile`.

## Unknowns

- Se o banco de homologação corresponde exatamente ao que a baseline descreve. A conferência de
  coluna antes do carimbo é a resposta operacional, e o primeiro deploy é a verificação real.
- Se algum volume local em uso hoje está defasado a ponto de o runner recusar.
- Qual o custo de tempo do PostgreSQL no CI, hoje sem nenhum serviço.

## Risks

- Carimbar um banco defasado como se estivesse em dia, adiando a falha para a próxima migration.
- As migrations não entrarem na imagem por detalhe de empacotamento, com a falha aparecendo só no
  deploy.
- Baseline que não descreve fielmente o schema atual, fazendo banco novo e banco adotado
  divergirem.
- Confundir esta feature com F-003 e criar tabela de medição aqui.

## Human Gates

- Aceitação do [ADR-0029](../../adr/0029-runner-de-migrations-revisadas.md) antes de qualquer
  código. Um agente nunca move um ADR de `Proposed` para `Accepted`. **Cumprido em 2026-08-17.**
- Aprovação deste contrato e criação de sua entrada no roadmap canônico.
- Primeiro deploy de homologação com o runner: é ele que exercita o caminho de adoção contra o
  banco real.
- Qualquer DDL destrutiva, hoje fora de escopo.

## References

- [ADR-0025](../../adr/0025-homologacao-em-gcp-cloud-run.md),
  [ADR-0028](../../adr/0028-medicao-na-api-v1-autenticada.md),
  [ADR-0029](../../adr/0029-runner-de-migrations-revisadas.md)
- [HML](../../operations/HML.md) — lacuna "Migrations revisadas"
- [Deployment e Rollback](../../operations/DEPLOYMENT_AND_ROLLBACK.md)
- [Definition of Done](../../engineering/DEFINITION_OF_DONE.md) — "Migração, compatibilidade e
  rollback foram avaliados"
- [Testing Strategy](../../engineering/TESTING_STRATEGY.md),
  [Project Context](../../engineering/PROJECT_CONTEXT.md)
