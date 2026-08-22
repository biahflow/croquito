# T5 — Logging estruturado JSON da API e do worker

Task Contract derivado do [plano](../plan.md). Autossuficiente.

## Identity

```text
feature_id: F-031
task_id: T5
parent_plan: docs/features/F-031-value-events/plan.md
depends_on: [T3]
```

## Goal

Hoje NENHUM logging está configurado no repositório (root logger sem handler;
`services/api` não tem `import logging`; os `logger.warning` do worker se
perdem). Ligar logging estruturado: uma linha JSON por registro, campos de
`extra` promovidos a chaves, request log na API e log por comando no worker —
alinhado a `docs/operations/OBSERVABILITY.md` e à política do CLAUDE.md
(nunca conteúdo).

## Baseline

T1–T3 na branch. Rode e registre: `uv run pytest tests -q`.

## Mapa verificado (leia antes de editar)

- Loggers existentes (passam a ter saída — não os altere):
  `services/worker/src/croquito_worker/providers.py` l.26 (usos l.748-754,
  914, 966, 1321, 1333), `local_queue.py` l.97 (usos l.463-476, 562-575),
  `push_server.py` l.44, `provider_review.py`.
- API: middleware `request_correlation` em
  `services/api/src/croquito_api/main.py` l.2629-2635 (molde a estender);
  `create_app()` monta o app — a configuração de logging entra lá, idempotente
  (a suíte instancia vários apps no mesmo processo; configurar duas vezes não
  pode duplicar handlers).
- Worker: entradas são os subcomandos de
  `services/worker/src/croquito_worker/cli.py` e o consumo de
  `local_queue.py` (`dispatch` l.681 — comando, tenant; o job_id vem do body).
- Vários subcomandos do CLI imprimem JSON de resultado em **stdout** — logs
  devem ir para **stderr** para não corromper essas saídas.
- Campos-alvo (OBSERVABILITY.md l.20-21): `request_id`, `job_id`, `stage`,
  `attempt` quando existirem; nunca `tenant_id` cru em log — se precisar,
  hash (siga `tenant_id_hash` do doc).

## Scope (comportamento)

### 1. `croquito_core.logging_config` (novo)

`packages/core/src/croquito_core/logging_config.py`:

- `JsonLogFormatter(logging.Formatter)`: linha JSON com `timestamp` (UTC ISO),
  `level`, `logger`, `message`, e todo atributo de `record` fora do conjunto
  padrão do stdlib promovido a chave (o dict `extra`); `exc_info` vira
  `error.kind`/`error.message` (sem stack de valores de variáveis).
- `configure_logging(level: str = "INFO") -> None`: `dictConfig` com um
  handler para **stderr** e o formatter acima no root; idempotente
  (chamada repetida não duplica handler); respeita
  `CROQUITO_LOG_LEVEL` quando setado.
- Sem dependência nova (stdlib puro).

### 2. API

- `configure_logging()` em `create_app()`.
- Estender `request_correlation` (l.2629-2635): logar ao fim de cada request
  `{method, route (template via `request.scope["route"].path` — NUNCA o path
  cru com IDs), status_code, duration_ms, request_id}` em logger
  `croquito_api.request`, nível INFO (WARNING para 5xx). Sem body, sem query
  string, sem headers.

### 3. Worker

- `configure_logging()` na entrada do CLI (`main()`/dispatch de subcomandos)
  e do consumo de fila.
- Em `dispatch` (`local_queue.py` l.681): log INFO ao concluir cada comando
  `{command, job_id (quando houver), status: ok|error, duration_ms}`; erro
  loga `error_code` estável quando disponível e re-levanta (semântica de
  reentrega intocada).

## Out of Scope

OpenTelemetry/traces/métricas/alarmes; mudar mensagens/níveis dos logs
existentes; logar em request de terceiros (providers já têm seus pontos);
`apps/web`. Não conserte falha preexistente fora do escopo — pare e reporte.

## Acceptance Criteria

1. Teste de unidade do formatter: linha é JSON válido; `extra` promovido;
   registro com exceção carrega `error.kind` sem variáveis locais.
2. Teste da API (client de teste + captura de stderr/caplog): request logado
   com rota template (`/v1/jobs/{job_id}/...`, sem UUID no valor de `route`),
   status e `duration_ms` numérico; `request_id` igual ao header devolvido.
3. Teste do worker: comando despachado loga `command`/`status`/`duration_ms`;
   comando que falha loga `status: "error"` e a exceção continua propagando.
4. Subcomandos de CLI que imprimem JSON em stdout continuam com stdout
   parseável (teste existente de CLI segue verde sem ajuste de parsing).
5. Grep de segurança nos pontos novos: nenhum log com `raw_text`, path com
   ID inline na mensagem, URL assinada ou tenant_id cru.
6. `configure_logging` chamado duas vezes não duplica linhas (teste).
7. `make check` e `make test` verdes.

## Validation

```bash
uv run pytest tests -q
make check
make test
```

## Report

Termine com o `BUILD REPORT` completo (todos os campos; `none` explícito
onde vazio).
