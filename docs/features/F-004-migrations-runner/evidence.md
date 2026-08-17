# F-004 — Pacote de evidências

Status: `DONE`
Responsável: Engineering
Última revisão: 2026-08-17

> Implementação entregue em `be82529`. A **revisão humana ocorreu em 2026-08-17** e encontrou um
> defeito latente no portão de adoção, corrigido antes do fechamento (seção 7). O risco residual
> da seção 6 permanece aberto por decisão explícita: fechá-lo depende de levantamento no banco
> real de homologação.

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

Executada em 2026-08-17, com PostgreSQL 17 descartável em porta própria — a 5432 estava ocupada
por outro projeto e nenhum contêiner alheio foi derrubado.

| Portão | Resultado |
| --- | --- |
| `make check` | exit 0 (ruff, ruff format, mypy strict em 171 arquivos, `check_docs` em 111 Markdown, drift de contratos, builds web e medição, `terraform fmt`) |
| `make test` sem PostgreSQL | exit 0 — os testes do runner **pulam**, como projetado |
| `make test` com `CROQUITO_TEST_POSTGRES_URL` | exit 0 — 1285 passed, 0 skipped; web 346, medição 127 |
| Testes coletados | 1277 na baseline → **1285** (+8) |
| Runner **dentro da imagem** contra PostgreSQL real | `schema migrado (estado inicial do banco: vazio)` e, na segunda execução, `versionado` |
| `docker build -f docker/python.Dockerfile` | sucesso; prova que as migrations viajam no pacote instalado |

Revalidação após a correção da revisão humana (seção 7), com PostgreSQL 17 descartável em porta
própria — nenhum contêiner alheio foi tocado:

| Portão | Resultado |
| --- | --- |
| `uv run pytest tests/api/test_migrations.py -v` com PostgreSQL | 10 passed (eram 8) |
| `uv run pytest` com `CROQUITO_TEST_POSTGRES_URL` | 1298 passed, 0 skipped |
| `make check` | exit 0 |
| `make test` sem PostgreSQL | exit 0 — os testes do runner voltam a pular, como projetado |
| Testes coletados | 1296 → **1298** (+2) |

## 5. Revisão: achado corrigido antes do commit

A revisão linha a linha encontrou um furo no caminho de adoção, reproduzido por script antes de
ser corrigido e coberto por teste depois.

**Sintoma.** Um banco anterior ao runner com **todas** as colunas legadas presentes, mas sem uma
tabela que nasceu depois, era carimbado na baseline em silêncio. Como a baseline descreve essa
tabela e passava a constar como aplicada, ela **nunca mais seria criada**. Reprodução: banco de
`create_schema()` com `chat_sessions` e `chat_turns` derrubadas devolvia
`estado reconhecido: adotado`, criava `alembic_version` e deixava as duas tabelas ausentes.

**Causa.** A conferência de adoção olhava apenas as colunas que os blocos de `ALTER TABLE`
acrescentavam. Tabela nova nunca teve bloco de `ALTER` — ela entrava pelo `create_all` do
bootstrap antigo —, então nenhuma coluna denunciava a defasagem. O ADR-0029 (D3) fala em
conferir "as colunas mais recentes"; a conferência de tabela é mais conservadora e não o
contraria.

**Correção.** O portão de adoção passa a exigir também que **toda** tabela de `Base.metadata`
exista antes de carimbar. A mesma reprodução agora recusa com
`Faltam: tabela chat_sessions, tabela chat_turns`. Coberto por
`test_tabela_nova_ausente_recusa_mesmo_com_colunas_legadas_em_dia`.

## 6. Risco residual declarado: FK ausente em banco adotado

Confirmado na revisão, **não** corrigido aqui, e registrado para não se perder.

O bloco antigo criava `ai_processing_consents.entitlement_id` por
`ALTER TABLE … ADD COLUMN entitlement_id VARCHAR(36)`, **sem** `REFERENCES`. O modelo declara
`ForeignKey("tenant_ai_processing_entitlements.id")` (`database.py:116-118`) e a baseline cria a
constraint (`0001_baseline.py:148-151`). Consequência: um banco **adotado** — o de homologação —
fica com a coluna e sem a constraint, enquanto um banco novo fica com as duas.

A conferência de adoção não detecta isso por construção: ela olha existência de tabela e de
coluna, não constraint. Exigir a constraint faria a homologação **recusar** a adoção e travar o
deploy, que seria pior remédio que doença.

O fechamento é uma migration forward-only que crie a constraint quando ausente. Ela não é
escrita aqui porque exige decisão humana sobre linha órfã: se houver `entitlement_id` apontando
para entitlement inexistente, a criação da FK falha e para o deploy. É trabalho próprio, com o
levantamento das linhas antes.

**Decisão da revisão humana de 2026-08-17: manter aberto.** Escrever a migration exige antes
levantar as linhas órfãs no banco real de homologação, o que é ato humano com acesso que nenhuma
sessão de agente tem. O risco continua registrado aqui, e não em nota de rodapé de commit.

## 7. Revisão humana: defeito no portão de adoção, corrigido antes do fechamento

**Sintoma.** `_adoption_gaps` conferia o banco anterior ao runner contra `Base.metadata`
**corrente**, exigindo dele toda tabela do modelo de hoje. Como a `0001` é a única revisão, as
duas listas coincidiam (16 tabelas de cada lado) e nenhum teste acusava.

**Consequência, com gatilho já agendado.** A docstring de `0001_baseline.py` declara que as
tabelas da medição ficaram de fora de propósito, para F-003. Quando a migration `0002` as criar,
`Base.metadata` passa a ter 18 tabelas e o banco de homologação — que nunca foi carimbado, porque
o primeiro deploy com o runner segue sendo ato humano pendente — continua com 16. O runner
recusaria com `Faltam: tabela valuation_rounds, …` e **pararia o deploy**, mandando "recriar o
banco ou tratar à mão", quando essas tabelas são exatamente o que o `upgrade` criaria logo depois
do carimbo. O portão reprovaria o banco que ele existe para adotar.

**Causa.** Confundir duas réguas diferentes. Carimbar afirma "este banco está no estado da
revisão `0001`" — logo a referência é a baseline, não o modelo. Medir contra o modelo torna o
portão mais estrito a cada migration nova, e essa estritização não descreve defasagem nenhuma.

**Correção.** `BASELINE_TABLES` declara as 16 tabelas da revisão `0001` e passa a ser a régua da
adoção; a detecção de banco vazio usa a união da baseline com o modelo, que é mais conservadora.
Isso é **mais fiel** ao ADR-0029 (D3 fala em conferir contra a baseline) e não contraria nenhuma
de suas decisões, então não exige ADR novo.

**Prova de que o teste morde.** `test_tabela_nascida_depois_da_baseline_nao_impede_adocao` foi
escrito antes da correção e reprovou no código antigo exatamente com o sintoma previsto —
`SchemaAdoptionError: … Faltam: tabela valuation_rounds_futura` — passando depois dela.
`test_baseline_tables_corresponde_a_revisao_0001` impede que a constante apodreça: ele aplica a
revisão `0001` num schema limpo e exige igualdade entre as tabelas criadas e a lista declarada.
