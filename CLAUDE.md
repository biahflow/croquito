# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Precedência de instruções

[AGENTS.md](AGENTS.md) na raiz é a instrução canônica para agentes e prevalece sobre
este arquivo. `AGENTS.md` em subdiretórios (`apps/web`, `services/api`,
`services/worker`, `infra`) acrescentam regras e nunca as enfraquecem — leia o mais
próximo do arquivo alvo antes de editar.

Antes de alterar código, leia [docs/INDEX.md](docs/INDEX.md) (roteador de contexto por
tipo de tarefa) e [docs/STATUS.md](docs/STATUS.md) (marco atual e o que já existe).
Leia por completo os poucos documentos canônicos relevantes; não carregue `docs/`
inteiro.

## Comandos

```bash
make setup      # uv sync --all-groups + npm install + geração de contratos
make check      # ruff check/format, mypy strict, check_docs, drift de contratos, build web, terraform fmt
make test       # uv run pytest + vitest
make dev        # API (uvicorn :8000) + web (vite :5173) em paralelo
```

Ambiente local completo (PostgreSQL, LocalStack, Keycloak):

```bash
cp .env.local.example .env.local
make dev-services   # docker compose -f docker-compose.local.yml up -d
make db-init        # cria schema + bucket/filas/state machine no LocalStack
make dev
make dev-worker     # consome uma mensagem SQS local (local-worker-once)
make down-services
```

Testes individuais:

```bash
uv run pytest tests/worker/test_dxf.py
uv run pytest tests/worker/test_rectangle_solver.py::test_nome -x
uv run pytest tests/e2e/test_full_flow.py      # cadeia completa, in-process
npm --workspace @croquitodxf/web run test -- src/App.test.tsx
```

`tests/` é um pacote: fixtures compartilhadas ficam em `tests/fakes.py` (storage e fila
com estado) e `tests/bundles.py` (pacote de revisão com digests amarrados). O `Database`
liga `PRAGMA foreign_keys=ON` no SQLite, então ordem de inserção errada falha no teste em
vez de só falhar em PostgreSQL.

Evals e demos determinísticas (todas gravam em `output/`, ignorado pelo Git):

```bash
make demo                     # vertical slice sintético → DXF + auditoria + ZIP
make provider-contract-demo   # adapters de provider offline, sem credenciais
make vision-eval              # gate de recall das propostas CV
make solver-eval              # revisão → solver → aprovação → DXF auditado
make valuation-demo           # MAPÃO anterior → medição multi-obra consolidada em xlsx auditado
make valuation-eval           # gate do takeoff sintético: extração fixture + revisão
make valuation-parity PREVIOUS=<caminho.xlsx>   # local, nunca CI: fórmula x valor em cache
```

Smoke contra o stack Docker real (fixture sintética, fora do CI):

```bash
make dev-services && make db-init && make dev-api
CROQUITODXF_ALLOW_TEST_TOKENS=true make smoke-local
```

Infra: `make infra-check` só roda `terraform fmt -check`. Validação real exige uma vez
`terraform -chdir=infra init -backend=false && terraform -chdir=infra validate`.
Nunca execute `terraform apply`.

## Arquitetura

Monorepo Python + TypeScript. `pyproject.toml` na raiz é único e declara três pacotes
Python via `packages/core/src`, `services/api/src`, `services/worker/src`; `package.json`
usa npm workspaces para `apps/web` e `packages/contracts`.

### O scene graph é a fonte geométrica

`packages/core/src/croquitodxf_core/models.py` define `SceneRevision` e é a única fonte
de verdade geométrica. Modelos de IA e OpenCV produzem *observações*; nada vira geometria
sem passar por aqui.

Toda `Entity` carrega `precision` (`exact` | `derived` | `approximate` | `unresolved`) e
`Provenance`. O portão de exportação é `SceneRevision.export_errors()` /
`ensure_exportable()`, que bloqueia cena não aprovada, entidade `unresolved`,
`approximate` sem aceite explícito, `exact` sem provenance, issue crítica aberta e
medida confirmada incompatível com a geometria. Qualquer caminho novo até DXF deve passar
por esse portão, não contorná-lo.

### Contratos gerados, nunca escritos à mão

Pydantic → JSON Schema → TypeScript:

```
croquitodxf_core.models  →  packages/contracts/scene.schema.json  →  packages/contracts/src/scene.generated.ts
```

Depois de mudar `SceneRevision`, rode `make contracts` e `make check`. `make check` falha
com drift (`schema_export --check` + `contracts:check`). Não edite `scene.schema.json` nem
`scene.generated.ts` manualmente.

### Fluxo real: evidência → revisão → associação → solver → aprovação → DXF

Implementado em `services/worker/src/croquitodxf_worker/`, cada etapa como comando
idempotente do CLI `croquitodxf-demo` (`cli.py`):

| Etapa | Módulo | Saída |
|---|---|---|
| Ingestão de PDF (não copia o original) | `ingest.py` | PNGs 200 DPI + manifest com digest |
| Propostas OpenCV em pixels | `vision.py` | candidatos sempre `unresolved`, `export=false` |
| Pacote de revisão de cotas | `review.py` | `ReviewPacket` com recorte, digest e `raw_text` |
| Associação proposta↔cota | `association.py` | ranking observacional, nunca confirma |
| Calibração pixel→metro | `proposal_calibration.py` | promove só a `approximate` |
| Solver retangular | `rectangle_solver.py` | resíduos, constraints, blockers críticos |
| Traçado em lote (cota manda) | `tracing.py` | cena métrica via `topology`+`geometry_solver`, Y espelhado, precisão declarada |
| Export CAD | `dxf.py` | gera, reabre, audita, renderiza e empacota |

Invariantes que atravessam o pipeline:

- Uma leitura sem `HumanDecision` completo retorna `review_required` (exit code 2) e não
  cria cena métrica. Não “corrija” esse estado editando o status.
- O solver exige associação explícita `reading_id → proposal_id` mesmo para leituras
  confirmadas; proximidade em pixels nunca é associação implícita.
- Aprovação é `SceneApproval` ligada ao UUID exato da revisão, e cria nova revisão.
- O export falha fechado: erro do auditor não publica o ZIP.
- Dimensão exata nunca é derivada de pixels; `approximate` continua `approximate` até o DXF.

### Providers de IA

`providers.py` isola OpenAI, Bedrock/Claude e Textract atrás de adapters com schema
estrito, `RetryingProviderAdapter` (só falha transitória), `BudgetedProviderAdapter` e
lineage de prompt/modelo por leitura. Estão **desligados por padrão**
(`CROQUITODXF_REAL_PROVIDERS_ENABLED=false`) e exigem entitlement contratual por tenant,
administrado apenas por `platform_operator`. Uploads normais não chamam providers; as
fixtures offline (`provider_review.py`, `make provider-contract-demo`) só entram por
injeção explícita em teste/demo. Chamadas pagas em massa exigem aprovação humana.

### API

`services/api/src/croquitodxf_api/main.py` monta tudo em `create_app()` (rotas declaradas
como closures). Ela autentica, autoriza e coordena lifecycle — não renderiza PDF, não
chama modelos e não gera DXF no request path. Rotas em `/v1/`: `projects`, `uploads/presign`,
`jobs`, `jobs/{id}/review` (+ `decisions`, `proposals`, `calibration`), `jobs/{id}/revisions`,
`jobs/{id}/scene`, `jobs/{id}/approve`, `platform/.../ai-processing-entitlement`.

- `tenant_id` vem sempre do JWT (`auth.py`), nunca do body.
- Mutações externas aceitam `Idempotency-Key` (`IdempotencyRecord`); revisões usam
  concorrência otimista com `base_version`.
- Erros usam códigos estáveis em `application/problem+json`; respostas brutas de provider
  nunca voltam ao cliente.
- `database.py` concentra os modelos SQLAlchemy; blobs ficam no S3, banco guarda metadados
  e digests. `config.py` lê tudo de env com prefixo `CROQUITODXF_`.

### Web

`apps/web` é React 19 + TS strict + Vite, consumindo os tipos gerados de
`@croquitodxf/contracts` e OIDC via `oidc-client-ts`. Apresenta revisão e status; não
resolve geometria nem decide consenso. Edições são operations allowlisted com `base_version`.
Cor nunca é o único indicador de precisão/issue; warnings críticos não são escondidos.

## Convenções

- Código e identificadores em inglês; documentação e mensagens de domínio em português.
- Python 3.12, mypy `strict = true`, ruff com `line-length = 100`, `select = ["E","F","I","UP","B","SIM","RUF"]`.
- Metros e radianos internamente; UTC; UUIDv7 (`croquitodxf_core.ids.new_uuid7`).
- `Decimal` onde a precisão escrita da cota importa; float só no solver, com tolerâncias nomeadas.
- Erros de domínio estruturados (`croquitodxf_core.errors.DomainValidationError`); não faça
  parsing de string de exception.
- Logs permitem IDs opacos, stage, duração, status, error code, model ID, tokens, custo e
  contagens. Nunca imagens, texto integral, cotas, tokens ou URLs assinadas.

## Dados e limites

- Nunca versione PDFs de clientes, renders, DXFs reais ou respostas brutas de provider.
  Tudo em `output/` é temporário, ignorado pelo Git e sujeito a retenção local de 7 dias.
- Fixtures versionadas são sintéticas ou explicitamente licenciadas.
- Exigem aprovação explícita: deploy/mutação AWS, migração destrutiva, chamadas pagas em
  massa, envio de documento a serviço externo, mudança de retenção/fornecedor, exclusão de
  dados de usuário.

## Conclusão de mudança

`make check` roda `scripts/check_docs.py`, que valida blocos de código fechados e **todo
link relativo de Markdown do repositório** — inclusive deste arquivo. Um link quebrado
reprova o CI.

Além dos testes: mudança de comportamento atualiza FDD e critérios de aceite; mudança de
interface atualiza [API Contract](docs/architecture/API_CONTRACT.md) e testes de contrato;
mudança arquitetural cria ADR (ADR aceito é imutável — crie outro com `Supersedes`);
mudança de IA exige eval comparativa e plano de rollback; se o marco mudou, atualize
[docs/STATUS.md](docs/STATUS.md).
