# Observabilidade

Status: Accepted for MVP  
Responsável: Platform / Engineering  
Última revisão: 2026-08-10

## Objetivos

Responder sem acessar conteúdo do cliente:

- Onde o job está?
- Qual etapa falhou e é retryable?
- Qual provider/model/version foi usado?
- Quanto tempo e custo cada página consumiu?
- Quantas decisões humanas foram necessárias?
- Um deploy aumentou erro, custo ou divergência?

## Correlação

Campos obrigatórios: `request_id`, `tenant_id_hash`, `project_id`, `job_id`,
`page_id`, `execution_id`, `stage`, `attempt`, `pipeline_version`.

IDs de tenant são hash/alias operacional; nenhum nome de cliente aparece.

## Métricas

### Workflow

- `jobs_started/completed/failed`.
- `stage_duration_seconds`.
- `stage_retries` e `dlq_messages`.
- `jobs_in_state` e age.

### Providers

- calls, latency, status, timeout e rate limit.
- input/output tokens quando disponíveis.
- schema failure e disagreement rate.
- `estimated_cost_usd` por page/provider.

### Recompute da shortlist (braço de embeddings)

O recompute de código (`POST /v1/{valuation,estimate}-rounds/{id}/code-suggestions/recompute`)
declara o gasto da via paga de embeddings no evento de rodada (`*.action_recorded.v1`) e no
log estruturado `croquito_api.valuation` (`code_suggestions_recomputed`). Campos, só
grandezas: `semantic_arm_ran` (o braço rodou?), `model_id`, `input_tokens`,
`estimated_cost_usd` (texto), `sources_with_index` e `sources_total`. `semantic_arm_ran=false`
é registro POSITIVO — a rodada da API ainda não publica índice, então o braço não roda e o
log diz isso com `semantic_reason`, em vez de omitir. Nenhum rótulo ou descrição embutida
entra no evento ou no log.

### Geometria/CAD

- entities por precision/type.
- critical/warning issues.
- solver conflicts e unresolved count.
- export audit failures.
- DXF entity count e package size.

### Produto

- time to draft, time to approve.
- review operations e regional reanalysis count.
- approximation acceptance count.

## Logs

Estruturados em JSON, nível consistente e error code estável. Proibido registrar:
imagens, OCR text, cotas, prompts preenchidos, responses, JWTs, signed URLs,
segredos ou S3 keys completas.

## Traces

OpenTelemetry/X-Ray cobre API→Step Functions→Fargate/Lambda→serviços. Provider
spans incluem somente metadata e duração.

## Alarmes MVP

- Job failure rate acima do baseline.
- Export audit failure > 0.
- DLQ > 0.
- Job preso além do timeout operacional.
- Provider 429/5xx sustentado.
- Estimated daily cost acima do budget.
- Cleanup de retenção com órfãos.

## Dashboards

1. Saúde do produto.
2. Pipeline e providers.
3. Qualidade/revisão.
4. Custos.
5. Segurança/retenção sem payload.

