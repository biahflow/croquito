# F-004 — Pacote de evidências

Status: `IN_PROGRESS`
Responsável: Engineering
Última revisão: 2026-08-17

Este documento registra a autorização humana, a baseline e a validação determinística de F-004.
Ele não é aprovação humana.

## 1. Contrato e decisão

| Artefato | Fonte |
| --- | --- |
| Feature Contract | [feature.md](feature.md) |
| Decisão técnica (`Accepted` em 2026-08-17) | [ADR-0029](../../adr/0029-runner-de-migrations-revisadas.md) |
| Lacuna que este trabalho fecha | [ADR-0025](../../adr/0025-homologacao-em-gcp-cloud-run.md), item 5 do bloco de decisão |
| Esquema que vai usar o runner | [ADR-0028](../../adr/0028-medicao-na-api-v1-autenticada.md) |
| Feature desbloqueada por este trabalho | [F-003](../F-003-medicao-v1-migration/feature.md) |

## 2. Autorização humana

**2026-08-17.** O responsável pelo produto selecionou o runner de migrations como trabalho
próprio, na sequência da aceitação do ADR-0028, e decidiu quatro pontos de desenho antes de
qualquer código:

| # | Questão | Decisão |
| --- | --- | --- |
| 1 | Escopo da rodada | **ADR + contrato + implementação**, com a aceitação do ADR como checkpoint no meio |
| 2 | Qual runner | **Alembic**, e não runner caseiro de SQL numerado |
| 3 | Gate de drift | **PostgreSQL no CI** e teste que exige diferença vazia entre migrations e `Base.metadata` |
| 4 | Esteira de homologação | **Muda nesta rodada**, com adoção do banco existente por carimbo |

Na mesma data, e depois de as três consequências de risco lhe serem apresentadas nominalmente —
o carimbo sobre banco que pode divergir, a exigência de empacotamento imposta pelo
`--no-editable`, e a perda do conserto automático de volume local antigo —, o responsável
**aceitou o ADR-0029**. Essa aceitação é a dependência bloqueante que o contrato registrava, e o
guardrail global que proíbe introduzir tecnologia de banco sem ADR passa a estar satisfeito.

A aceitação **não** autoriza deploy, `terraform apply` nem qualquer comando contra o banco de
homologação. A esteira continua sendo o único caminho, e ela roda por ato humano de merge.

## 3. Baseline

| Fato | Valor |
| --- | --- |
| Commit base da implementação | `dca7cf5` — `docs(adr): rascunho do runner de migrations revisadas (F-004)` |
| Branch de trabalho | `docs/f-002-medicao-v1-contract`, não publicada |
| Testes coletados por `uv run pytest --co` | **1277** |
| `make check` antes da mudança | exit 0 |
| Runner existente | Nenhum. Sem Alembic em `pyproject.toml`, sem diretório de migrations, sem DDL versionada |
| Mecanismo atual de schema | `Database.create_schema()` (`services/api/src/croquito_api/database.py:459-540`): `create_all` + 5 blocos de `ALTER TABLE ADD COLUMN` guardados por `inspect` + 2 `CREATE UNIQUE INDEX IF NOT EXISTS` |
| Call sites de `create_schema()` | 1 em produção (`bootstrap.py:16`) e 24 em testes |
| Falhas preexistentes conhecidas | Nenhuma registrada |

## 4. Validação determinística

A registrar ao fim da implementação: `make check`, `make test` com a contagem comparada à
baseline de 1277, o teste de drift contra PostgreSQL real, a execução do runner contra o
PostgreSQL local e a construção da imagem provando que as migrations entram nela.
