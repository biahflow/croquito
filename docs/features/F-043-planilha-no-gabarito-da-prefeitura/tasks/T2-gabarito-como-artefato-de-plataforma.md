# F-043 T2 — Publicar o gabarito como artefato de plataforma

- **feature_id**: F-043
- **task_id**: T2
- **role**: builder
- **depends_on**: [T1]
- **required_capabilities**: READ, WRITE (`services/api/src/croquito_api`, `tests/api`), VALIDATE
- **risk**: MÉDIO — cria tabela e rotas novas, sem tocar caminho de publicação existente.
- **relative_effort**: M
- **validation**: `BROWSER_NOT_REQUIRED` (não há superfície nesta tarefa; a escolha na tela é a T3)

## A decisão que já está tomada

O dono decidiu, em 2026-08-28, que o gabarito **vive como artefato de plataforma**, no molde do
acervo de catálogos da [F-037](../../F-037-acervo-de-catalogos/feature.md) (plan.md, "Gates
cumpridos"). Esta tarefa não redecide isso: ela o constrói.

## O estado de hoje, e por que ele é o problema

A [T1](T1-gabarito-e-memoria.md) entregou o mecanismo inteiro: `EstimateTemplateLayout` em
`packages/valuation/src/croquito_valuation/template.py:591`, e
`plan_estimate_grid_workbook`/`write_estimate_grid_workbook`/`audit_estimate_grid_workbook` em
`estimate_workbook.py:894,989,1176`. As 433 linhas saíram na ordem do gabarito, com as 43
quantidades idênticas às do cliente, e as duas abas passaram pelo auditor sem um único finding.

Só que o gabarito **só existe como arquivo JSON lido por caminho no CLI do worker**
(`services/worker/src/croquito_worker/valuation/cli.py:595`,
`WorkbookTemplate.model_validate_json(path.read_text(...))`). A API **não conhece
`WorkbookTemplate`** — `grep -n "WorkbookTemplate" services/api/src/croquito_api/main.py` não
devolve nada. Enquanto isso for verdade, o gabarito da prefeitura é um arquivo que alguém
precisa ter na máquina, e a jornada web não tem como oferecê-lo.

## Goal

Fazer o gabarito ser **dado publicável e versionado pela plataforma**: um `platform_operator`
publica um `EstimateTemplateLayout`, ele fica listável e retirável de circulação, e a rodada
passa a ter de onde escolhê-lo — o que a T3 fará na tela.

## Scope

### 1. `EstimateTemplateRecord` em `services/api/src/croquito_api/database.py`

Molde: `SiteSetupKitRecord` (`:361-417`). Copie a **forma**, não o texto do docstring.

```
__tablename__ = "estimate_templates"
id                 String(36), primary key
tenant_id          String(128), nullable, index      # ver decisão abaixo
name               String(200)
template_version   String(120)                       # espelho de EstimateTemplateLayout.revision_label (max_length=120)
source_label       String(200)
document_json      JSON                              # o EstimateTemplateLayout serializado
document_sha256    String(64)
withdrawn_at       DateTime(timezone=True), nullable
created_by         String(128)
created_at         DateTime(timezone=True)
UniqueConstraint("tenant_id", "name", "template_version", name="uq_estimate_template_identity")
```

**Decisão sobre `tenant_id`, e ela é minha para tomar aqui**: a coluna existe e é **anulável**,
exatamente como em `site_setup_kits`, mas **esta tarefa só publica com `tenant_id IS NULL`** —
o gabarito é da prefeitura, e a decisão do dono o pôs no molde da F-037, que é global. A coluna
anulável existe porque o gabarito de uma segunda prefeitura, autorado por um tenant, é
extensão previsível e a alternativa (tabela global agora, coluna depois) custaria uma migração
com dado dentro. **Não construa** o caminho do tenant: nenhuma rota o escreve, e a leitura já
nasce com a cláusula correta.

**Nas rotas de plataforma o filtro é `tenant_id IS NULL`, e isso é intencional** — repare em
`list_site_setup_kits`: listar ali também o acervo autorado por tenants daria a um operador de
plataforma a lista dos acervos de todos os clientes. A cláusula `tenant_id IS NULL OR tenant_id
= :tenant` é a da leitura **pela rodada do tenant**, que não existe nesta tarefa e nasce na T3;
quando ela nascer, escrevê-la sem a segunda metade é defeito de isolamento
(`SiteSetupKitRecord:371-375`).

**O documento mora no banco, não no object store**, pela mesma razão do kit de canteiro
(`SiteSetupKitRecord:377-381`): não há bytes de arquivo de terceiro a preservar — o que entra é
um documento que a própria API validou —, e ele é lido inteiro toda vez que uma planilha é
publicada. As 433 linhas dão da ordem de 150 KB de JSON, que é pequeno para uma coluna `JSON` e
não justifica um round-trip de rede por leitura.

### 2. Migração `0029`

A última na `main` é `0028_valuation_round_scene_link.py`. Forward-only, no molde de
`0027`/`0028`. Índice em `tenant_id`, e a `UniqueConstraint` acima.

Se ao começar a `main` já tiver uma `0029`, **renumere para a seguinte livre e relinearize
`down_revision`** — não empilhe duas com o mesmo número.

### 3. Rotas em `services/api/src/croquito_api/main.py`

Molde: as três de `site-setup-kits` (`:7964`, `:8063`, `:8098`). Mesma ordem de recusas, mesmos
nomes de erro adaptados.

| Método | Rota | O que faz |
|---|---|---|
| `POST` | `/v1/platform/estimate-templates` | publica; `201`; exige `Idempotency-Key` |
| `GET` | `/v1/platform/estimate-templates` | lista os em circulação |
| `POST` | `/v1/platform/estimate-templates/{estimate_template_id}/withdraw` | carimba `withdrawn_at` |

Invariantes, todas com precedente no molde:

1. **`_require_platform_operator(principal)` é a primeira linha de toda rota**, antes de
   qualquer lookup — inclusive na leitura. Quem não tem o papel recebe `403` e não descobre,
   pela diferença entre `403` e `404`, o que existe no acervo.
2. **O documento é validado pelo domínio antes de virar linha**: o corpo traz o
   `EstimateTemplateLayout` cru, e `EstimateTemplateLayout.model_validate` o recusa com
   `422 DOMAIN_VALIDATION_FAILED` e o **código estável do domínio**
   (`TEMPLATE_ESTIMATE_GRID_CODE_INVALID`, `TEMPLATE_ESTIMATE_GRID_DUPLICATE_CODE`,
   `TEMPLATE_ESTIMATE_GRID_DUPLICATE_ITEM`), nunca como erro de esquema do FastAPI. Veja como
   `publish_site_setup_kit` faz isso e repita o padrão.
3. **Publicação é imutável**: mesma `(name, template_version)` já publicada recusa com
   `409 ESTIMATE_TEMPLATE_ALREADY_PUBLISHED`. A recusa é **conferida na rota**, não só pela
   constraint — `NULL` não colide com `NULL` em PostgreSQL nem em SQLite, e o acervo de
   plataforma tem `tenant_id` nulo. Este ponto está escrito em `SiteSetupKitRecord:387-392` e é
   a armadilha principal desta tarefa.
4. **`template_version` é lido de dentro do documento** (`EstimateTemplateLayout.revision_label`),
   nunca do corpo da requisição — é o mesmo rótulo que a planilha publicada citará, e deixá-lo
   entrar por fora abriria a porta para a linha dizer uma revisão e o documento dizer outra.
5. **Retirar não apaga**: carimba `withdrawn_at`. Uma rodada que publicou com o gabarito
   continua citando a revisão dele.
6. `document_sha256` é o digest canônico do documento gravado, no molde do kit.

### 4. Chave de idempotência

`operation = "platform.estimate-templates"`. **Confira o portão de operações**: o PR #124 criou
um portão que varre por AST todas as operações de idempotência e falha alto se encontrar uma
que não sabe medir. Rode-o e, se ele exigir registro da operação nova, registre — não contorne.

### 5. Contrato e snapshot

`docs/architecture/API_CONTRACT.md` ganha as três rotas. Regenere
`tests/api/openapi.snapshot.json` pelo alvo do Makefile (`make openapi-snapshot`); o diff deve
ser **aditivo**.

## Out of scope

- **A escolha do gabarito na jornada web** — é a T3, e é `INTERFACE_CHANGE`.
- **Ligar o gabarito publicado à publicação da planilha da rodada.** A T2 entrega o acervo; quem
  o consome é a T3. Não toque em `estimate_workbook.py` nem no CLI do worker.
- **O gabarito real do cliente.** Ele não está no repositório e não estará (T1, "Decisão do dono
  já tomada"). Fixture sintética, e ela entra pela mesma porta que o real entrará.
- **Gabarito autorado por tenant.** A coluna existe; o caminho, não.
- Qualquer mudança em `template.py` ou `EstimateTemplateLayout` — a T1 os fechou.

## Acceptance criteria

1. `platform_operator` publica um `EstimateTemplateLayout` sintético e recebe `201` com o
   `estimate_template_id`, o `template_version` lido do documento e o `document_sha256`.
2. Quem **não** é `platform_operator` recebe `403` nas três rotas, inclusive no `GET`, e o
   `403` vem **antes** de qualquer lookup (um id inexistente também dá `403`, não `404`).
3. Republicar a mesma `(name, template_version)` recusa com
   `409 ESTIMATE_TEMPLATE_ALREADY_PUBLISHED`, **e o teste roda com `tenant_id` nulo** — é o caso
   que a constraint do banco não pega.
4. Documento com código fora do formato, código duplicado ou item duplicado recusa com `422` e
   o código estável do domínio no corpo.
5. `template_version` divergente entre corpo e documento é impossível: o corpo não o aceita.
6. Retirar carimba `withdrawn_at`, some da listagem em circulação, e o registro continua no
   banco.
7. A mesma `Idempotency-Key` com o mesmo corpo devolve a mesma resposta sem publicar duas vezes.
8. A migração `0029` aplica **do zero** e o teste de migrações passa.
9. `make check` e `make test` verdes; snapshot OpenAPI aditivo.

## Verificação

```bash
uv run pytest tests/api/test_estimate_templates.py      # o arquivo novo desta tarefa
uv run pytest tests/api/test_migrations.py
uv run pytest tests/api/test_idempotency_operations.py  # o portão do #124
make openapi-snapshot && make check
make test
```

## Armadilhas

- **`NULL` não colide com `NULL`.** A `UniqueConstraint` não protege o acervo de plataforma. Se
  a recusa de republicação só existir no banco, o teste do critério 3 passa em nenhum lugar e o
  gabarito é republicável em silêncio. Esta é a armadilha que já mordeu o kit de canteiro, e
  está escrita no docstring dele.
- **Os testes rodam em SQLite e a produção é PostgreSQL.** Foi assim que o `500` da chave de
  idempotência passou por toda a suíte até a captura de navegador o encontrar (PR #124).
  Dimensione as colunas para o conteúdo real: `revision_label` cabe em `String(120)` — que é o `max_length` do modelo, e não menos — e `name` em
  `String(200)`? Se um nome de gabarito real for maior, o teste passa e a produção dá `500`.
- **433 linhas num `JSON`** é o maior documento que essa coluna vai guardar no schema. Confira
  que o `document_sha256` é calculado sobre a **forma canônica** do documento, não sobre o corpo
  cru da requisição — senão dois corpos equivalentes dão digests diferentes.
