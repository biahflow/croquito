# F-031 — Contrato de eventos de domínio (v1)

Contrato de consumo para o portal do cliente (repositório próprio). O portal
lê do broker (Pub/Sub; ver [ADR-0042](../../adr/0042-eventos-de-dominio-outbox-pubsub.md)),
nunca da API do croquito. Este documento é a fonte que o repositório do portal
deve seguir sem ler código do croquito.

## Envelope

Toda mensagem publicada é um JSON com o envelope:

```json
{
  "event_id": "uuid7",
  "event_type": "croquito.<entidade>.<fato>.v1",
  "tenant_id": "string opaca",
  "occurred_at": "RFC 3339 UTC",
  "job_id": "uuid7 | null",
  "payload": {}
}
```

Regras invariantes (herdadas da política de logs do repositório):

- `payload` carrega **somente** IDs opacos, stage, durações (ms), status,
  códigos de erro estáveis, model ID, tokens, custo (string decimal em USD) e
  contagens. Nunca imagens, texto de cota, conteúdo de documento, tokens de
  autenticação ou URLs assinadas.
- Sufixo `.v1` é versionamento do payload: mudança incompatível cria `.v2`,
  nunca muta `.v1`.
- Entrega é **at-least-once**; consumidores deduplicam por `event_id`.
- Ordem não é garantida entre tipos; `occurred_at` ordena por entidade.

## Catálogo v1

| event_type | Quando | payload |
|---|---|---|
| `croquito.job.created.v1` | job criado na API | `{project_id, stage, status}` |
| `croquito.job.stage_changed.v1` | worker/API muda stage/status | `{from_stage, to_stage, from_status, to_status, stage_duration_ms?, failure_code?}` |
| `croquito.review.decisions_recorded.v1` | lote de decisões humanas | `{review_version, decisions_total, confirmed, corrected, rejected, interaction_ms?}` |
| `croquito.review.rectifications_recorded.v1` | retificações | `{review_version, rectifications_total, interaction_ms?}` |
| `croquito.review.proposals_decided.v1` | decisão sobre propostas CV | `{review_version, proposals_total, accepted, rejected}` |
| `croquito.review.calibration_set.v1` | calibração pixel→metro | `{review_version}` |
| `croquito.review.chains_declared.v1` | declaração/retração de cadeia | `{review_version, action, chains_total}` |
| `croquito.scene.approved.v1` | aprovação de cena | `{scene_revision_id, approved_by_role}` |
| `croquito.export.completed.v1` | ZIP publicado | `{export_id, duration_ms?}` |
| `croquito.export.failed.v1` | export falhou fechado | `{export_id, failure_code}` |
| `croquito.ai.call_executed.v1` | chamada de provider concluída | `{provider, model_id, prompt_version, latency_ms, input_tokens?, output_tokens?, estimated_cost_usd?, failure_code?}` |
| `croquito.valuation.action_recorded.v1` | ações auditadas da medição | `{action, round_id?, version?}` |
| `croquito.estimate.action_recorded.v1` | ações auditadas do orçamento | `{action, round_id?, version?}` |

Notas:

- `valuation.*`/`estimate.*` espelham 1:1 as ações já gravadas em
  `audit_events` (`VALUATION_ROUND_CREATED` … `BULLETIN_EXPORTED`); o campo
  `action` carrega o código estável existente. Granularizar em tipos próprios
  é evolução `.v2+`, guiada pelo consumo real do portal.
- Campos com `?` são opcionais; ausência significa "não medido", nunca zero.
- `interaction_ms` só existe após a T4 e é observacional (autorrelato da tela).

## Transporte

- **Outbox**: tabela `domain_events` gravada na mesma transação do fato.
- **Relay**: `croquito-demo publish-events` (idempotente; marca
  `published_at`) publica na porta `DomainEventPublisher`.
- **Adapters v1**: `file` (JSONL local, demo/testes) e `pubsub` (tópico
  `CROQUITO_DOMAIN_EVENTS_TOPIC`; exercitado só no hosted, fora desta rodada).

## Métricas derivadas (referência para o portal)

- Cycle time por etapa: deltas de `job.stage_changed` por `job_id`.
- Automation/review rate: virão da F-029 (`auto_association_rate`,
  `review_rate`) — expostos no read-model `/v1/metrics/*`, e como evento em
  fatia futura.
- Correction rate: `corrected / decisions_total` de `decisions_recorded`.
- Custo por transação: soma de `ai.call_executed.estimated_cost_usd` por job.
- Touch time: soma de `interaction_ms`; na ausência, proxy por deltas entre
  eventos de ato humano do mesmo job.
