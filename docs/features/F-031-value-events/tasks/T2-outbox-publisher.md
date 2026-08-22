# T2 — Outbox `domain_events`, porta de publicação e relay idempotente

Task Contract derivado do [plano](../plan.md). Autossuficiente. Contrato de
consumo: [events-contract.md](../events-contract.md) (fonte da verdade dos
tipos e payloads — siga-o à risca). Decisão de arquitetura:
[ADR-0042](../../../adr/0042-eventos-de-dominio-outbox-pubsub.md) (Proposed).

## Identity

```text
feature_id: F-031
task_id: T2
parent_plan: docs/features/F-031-value-events/plan.md
depends_on: [T1]
```

## Goal

Todo fato relevante (atos humanos da API, transições de estágio do worker,
chamadas de IA) grava um evento versionado na outbox `domain_events` na mesma
transação da mudança de estado; um relay CLI idempotente publica na porta
`DomainEventPublisher` (adapters `file` e `pubsub`). Nada é publicado
diretamente do request path.

## Baseline

T1 integrada na branch `feat/f-031-value-events` (worktree
`/Users/danielcampos/workspace/daniel/croquito-f031`). Rode e registre:
`uv run pytest tests/api tests/worker -q`.

## Mapa verificado (leia antes de editar)

- Catálogo/envelope: `docs/features/F-031-value-events/events-contract.md`.
- Helper novo: `packages/core/src/croquito_core/events.py` — constantes de
  `event_type` + `build_domain_event(...) -> dict` (envelope; valida que
  `payload` só tem tipos escalares/None — nada de conteúdo). Sem I/O, sem DB.
- API: `_record_audit` em `services/api/src/croquito_api/main.py` l.1545-1565
  é o marcador dos atos humanos; grep `_record_audit(` (~40 sítios) e emita
  evento **apenas** nos que o catálogo v1 cobre, na MESMA sessão do request
  (mesmo `session.add`/commit do registro de negócio). Ações
  `VALUATION_*`/`ESTIMATE_*` viram `valuation.action_recorded.v1`/
  `estimate.action_recorded.v1` com o código estável no payload.
- Worker: os mesmos sítios de `UPDATE jobs SET` da T1 emitem
  `job.stage_changed.v1` na mesma `engine.begin()` (insert SQL cru, estilo do
  arquivo). Chamada de IA concluída emite `ai.call_executed.v1` — ponto de
  captura: onde `ProviderExecution` retorna no fluxo real
  (`provider_review.py`/`local_queue.py`); NÃO instrumente `providers.py`.
- Tabela: molde append-only `ReviewDecisionRecord`
  (`services/api/src/croquito_api/database.py` l.203-223). Migração
  `0009_domain_events.py`, `down_revision = "0008"`.
- Publicador: padrão de porta/adapter existente —
  `ProcessingQueue`/`PubSubProcessingQueue` (`main.py` l.1189-1272,
  `services/api/src/croquito_api/pubsub_queue.py` l.53) e seleção por settings
  (`main.py` l.2615-2619; `services/api/src/croquito_api/config.py` l.49-54,
  `pubsub_topic`/`queue_backend`). `google-cloud-pubsub` já é dependência do
  pyproject único da raiz.
- CLI: parsers e dispatch em `services/worker/src/croquito_worker/cli.py`
  (siga o padrão dos subcomandos existentes; help em português de domínio).
- Config: env com prefixo `CROQUITO_` (`config.py` l.71-86). Nova:
  `CROQUITO_DOMAIN_EVENTS_TOPIC` (adapter pubsub do relay).

## Scope (comportamento)

### 1. Tabela `domain_events` (outbox)

`DomainEventRecord`: `{id/event_id (str36, uuid7), tenant_id (indexado),
event_type (str, indexado), job_id: str | None (indexado), occurred_at
(tz-aware), payload_json (JSON), published_at: datetime | None (indexado),
created_at}`. Migração 0009 aditiva (forward-only; rollback = drop table).
Sem poda/retenção nesta fatia.

### 2. Emissão

- API: gravação ORM ao lado dos `_record_audit` cobertos pelo catálogo; a
  transação é a do request — evento e fato commitam juntos ou nenhum.
- Worker: insert SQL cru na mesma transação dos sítios da T1 +
  `ai.call_executed.v1` no ponto de retorno do provider real.
- Payloads exatamente como no contrato; contagens
  (`confirmed/corrected/rejected`) computadas do lote da própria request.
- `stage_duration_ms` de `job.stage_changed.v1`: delta contra o último
  `job_stage_events` do job quando disponível na mesma conexão; `None` caso
  contrário — não faça query cara para isso.

### 3. Porta e adapters

`services/worker/src/croquito_worker/domain_event_publisher.py`:
`DomainEventPublisher` (Protocol/ABC, método `publish(envelope: dict) -> None`),
`FileDomainEventPublisher` (JSONL append em caminho dado) e
`PubSubDomainEventPublisher` (topic de `CROQUITO_DOMAIN_EVENTS_TOPIC`; import
do SDK **dentro** do adapter, lazy — o resto do worker não pode passar a
depender do SDK em import time). Sem retry próprio na fatia 1: exceção do
adapter interrompe o relay sem marcar `published_at` (reentrega natural).

### 4. Relay `croquito-demo publish-events`

`croquito-demo publish-events --sink file --path out.jsonl [--limit N]`
(e `--sink pubsub`). Seleciona eventos com `published_at IS NULL` em ordem de
`created_at`, publica um a um e marca `published_at` **após** publicar cada
um (falha no meio não re-publica os já marcados; re-execução continua dos não
marcados). Saída stdout JSON `{"published": N, "remaining": M}`. Exit 0;
falha de sink → mensagem em stderr, exit 1.

## Out of Scope

Rotas de métricas (T3); `apps/web`; provisionamento de tópico/infra;
retenção/poda; retry/DLQ do relay; consumidores; mudanças em
`ProcessingQueue`/`PubSubProcessingQueue`. Não conserte falha preexistente
fora do escopo — pare e reporte.

## Acceptance Criteria

1. Decisões de review (rota existente) geram `review.decisions_recorded.v1`
   com contagens corretas, na mesma transação (teste com rollback injetado:
   sem fato, sem evento).
2. Transição de stage do worker gera `job.stage_changed.v1` coerente com a
   linha de `job_stage_events`.
3. Ação de valuation auditada gera `valuation.action_recorded.v1` com o
   código estável.
4. Envelope de todo evento valida contra o contrato (teste que percorre os
   eventos emitidos no e2e e verifica envelope + ausência de chaves proibidas
   — ex.: `raw_text`, `url`, base64).
5. `publish-events --sink file`: publica pendentes, marca `published_at`,
   re-execução publica 0; falha simulada do sink no meio do lote deixa os
   já publicados marcados e os demais pendentes.
6. Adapter pubsub é instanciável sem rede (teste de unidade com client
   injetado/fake); nenhum teste chama GCP real.
7. Migração 0009 verde em `tests/api/test_migrations.py`; `make check` e
   `make test` verdes.

## Validation

```bash
uv run pytest tests/api tests/worker tests/e2e -q
make check
make test
```

## Report

Termine com o `BUILD REPORT` completo do contrato do Builder (todos os
campos; `none` explícito onde vazio).
