# F-031 — Eventos de valor: telemetria de automação e emissão para o portal

## Status

`DONE`

> **Aceite humano em 2026-08-28**, sobre o pacote de revisão em [evidence.md](evidence.md).
> A fatia 1 já está integrada à `main` (migrações `0011_job_stage_events` e
> `0012_domain_events`, CLI `publish-events`). Dívida declarada, não exercida:
> provisionamento do tópico Pub/Sub e aplicação das migrações no ambiente hospedado.
>
> Especificada e executada em 2026-08-21 (decisão humana na mesma sessão:
> escopo, broker Pub/Sub e inclusão do logging estruturado). Fatia 1 completa —
> 5 tasks entregues, revisadas linha a linha e commitadas, portões finais verdes
> ([evidência](evidence.md)). A integração à `main` (rebase pós-F-029, renumeração das
> migrações) já ocorreu; o que resta são os atos de ambiente hospedado listados acima.

## Classification

Não é `INTERFACE_CHANGE`: não nasce superfície visual nova (a única mudança no
web é cronômetro invisível de interação). Sem Design Approval Package.

## Priority

`MEDIUM` — incremento de plataforma (metodologia de valor da Biahflow), não
bloqueia o MVP.

## Problem

A Biahflow está formalizando uma metodologia de valor (AS-IS → baseline →
TO-BE medido → valor realizado) cujo dashboard vive no portal do cliente
(outro repositório). O croquito precisa **provar o TO-BE com dados**: quanto
tempo o fluxo leva por etapa, quanto toque humano ainda existe, quanto foi
corrigido sobre o que a máquina propôs, quanto custou de IA por transação.

O diagnóstico no código (2026-08-21) mostrou que a matéria-prima existe mas
está incompleta e presa:

1. `jobs.stage/status` são sobrescritos por `UPDATE` cru
   (`local_queue.py:648,906,960`) — cycle time por etapa é irreconstruível.
2. O lineage do pipeline do croqui (`ProviderLineage`, `review.py:100-113`)
   descarta tokens/custo (`execution.usage`) ao persistir; só `chat_turns` e
   `extraction_lineage_json` da medição guardam custo.
3. Não existe nenhuma emissão de evento para fora: a fila SQS/Pub-Sub é
   comando interno API↔worker; zero webhooks/exportação.
4. Não existe read-model de métricas; `CostBudget.spent_usd` morre em memória.
5. Touch time real não existe (`decided_at` é carimbo do servidor; o web não
   envia telemetria de interação).
6. Não existe nenhuma configuração de logging no repositório (root logger sem
   handler; a API não tem `import logging`) — o que `OBSERVABILITY.md` e o
   ADR-0023 descrevem não está implementado.

## Desired Outcome

Fatia 1 (esta rodada, tudo local):

- **Fatos persistidos**: histórico de transição de estágio por job
  (`job_stage_events`) e tokens/custo no lineage do croqui.
- **Outbox transacional** `domain_events` com catálogo versionado
  (`croquito.job.stage_changed.v1`…, incluindo `valuation.*`/`estimate.*`) e
  relay idempotente `croquito-demo publish-events` atrás da porta
  `DomainEventPublisher` — broker decidido: **Pub/Sub** (adapter; RabbitMQ/
  Kafka ficam como alternativa futura atrás da mesma porta). O portal consome
  do broker, sem acoplamento com a API. Contrato documentado em
  [events-contract.md](events-contract.md).
- **Read-model de métricas**: `GET /v1/jobs/{job_id}/metrics` (aninhada no job,
  coerente com as vizinhas — o Task Contract T3 prevalece; caminho antigo
  `/v1/metrics/jobs/{id}` era erro de spec) e
  `GET /v1/metrics/summary` (tenant do JWT) + CLI `value-report` — cycle time
  por etapa, atos humanos, correction_rate, custo de IA por job; campos
  reservados para `auto_association_rate`/`review_rate` da F-029 (`null` até
  ela aterrissar).
- **Touch time real**: `interaction_ms` opcional medido pela tela de revisão.
- **Logging estruturado JSON** de API e worker (stdlib, sem dependência nova),
  alinhado a `docs/operations/OBSERVABILITY.md`.

Fora desta fatia: dashboard/ROI/baseline AS-IS (portal), integração ERP
(portal), OpenTelemetry/traces/alarmes, qualquer auto-decisão (F-029).

## Scope

Cinco tasks sequenciais (T1→T2→T3→T5→T4), contrato aditivo, detalhadas no
[plano](plan.md) e nos Task Contracts:
[T1](tasks/T1-stage-events.md), [T2](tasks/T2-outbox-publisher.md),
[T3](tasks/T3-metrics-readmodel.md), [T5](tasks/T5-structured-logging.md),
[T4](tasks/T4-touch-time-web.md).

## Out of Scope

- Merge na main, push, deploy, migração no hosted, provisionamento do tópico
  Pub/Sub — atos humanos posteriores.
- `docs/product/ROADMAP.md`, `docs/STATUS.md`, `docs/features/README.md`
  (sincronizados na integração; ver desvio no Status).
- Threshold/auto-decisão e shadow mode (F-029); `dimension_closure.py`.
- Qualquer mudança no portão `SceneRevision.export_errors()`.
- Payload de evento ou log com conteúdo (imagem, texto de cota, URL assinada,
  token) — regra do CLAUDE.md vale como critério de revisão.

## Acceptance Criteria

1. `make check` e `make test` verdes no worktree (baseline registrada antes).
2. Fluxo e2e local grava transições em `job_stage_events` (API na criação,
   worker nas mudanças) e eventos correspondentes em `domain_events`, na mesma
   transação da mudança de estado.
3. `croquito-demo publish-events` drena a outbox marcando `published_at`;
   re-execução não duplica publicação; adapter file/log funciona sem serviços.
4. `GET /v1/metrics/jobs/{id}` devolve cycle time por etapa, contagens de atos
   humanos, `correction_rate` e custo de IA quando existir; jobs de outro
   tenant são invisíveis.
5. `interaction_ms` viaja opcionalmente nas mutações de revisão e fica em
   `review_revisions`; ausência ou valor absurdo nunca invalida a decisão.
6. Logs da API e do worker saem como uma linha JSON por registro com campos de
   `extra` promovidos; teste garante rota-template (sem IDs no path) e ausência
   de conteúdo sensível.
7. Snapshot OpenAPI regenerado deliberadamente onde o contrato mudou;
   `docs/architecture/API_CONTRACT.md` atualizado.

## Human Gates

- ~~Aceite do [ADR-0042](../../adr/0042-eventos-de-dominio-outbox-pubsub.md)~~ —
  **satisfeito** (`Accepted`; broker Pub/Sub decidido pelo usuário em sessão de
  2026-08-21).
- ~~Integração da branch (rebase pós-F-029, renumeração de migrações, sync de
  ROADMAP/STATUS/README de features)~~ — **satisfeito**: integrada à `main`.
- Provisionamento do tópico Pub/Sub e aplicação de migrações no hosted.
