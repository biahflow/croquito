# T1 — Adapter Document AI e montagem por configuração

Task Contract no formato do [template global](../../../engineering-os/templates/task.md),
derivado do [plano válido](../plan.md). Autossuficiente: assuma o Core (pinado em
`docs/engineering-os/`), este contrato e o repositório — nada mais.

## Identity

```text
feature_id: F-022
task_id: T1
parent_plan: docs/features/F-022-document-ai-braco-ocr/plan.md
depends_on: []
```

## Goal

`build_real_provider_suite` monta o braço `ocr` como Document AI quando
`CROQUITO_DOCAI_PROCESSOR` está definido (nome completo do processador:
`projects/<p>/locations/<l>/processors/<id>`), e como Cloud Vision quando não está —
comportamento atual intacto. O adapter novo espelha o desenho do atual: REST puro,
token ADC, schema estrito, mesmo contrato `OcrOutput`. Decisão registrada no
[ADR-0037](../../../adr/0037-document-ai-como-braco-de-ocr.md) (Proposed).

## Baseline

`make check`, `make test`, `make provider-contract-demo`, `make ocr-eval` verdes.
Há mudanças não commitadas em `apps/web/` e `docs/` na árvore — não são suas, não as
toque.

## Scope

Tudo em `services/worker/src/croquito_worker/providers.py` e
`tests/worker/test_providers.py`.

### Enum e constantes

- `ProviderName.GCP_DOCUMENT_AI = "gcp_document_ai"` (enum na linha ~40).
- `DOCAI_PROCESSOR_ENV: Final = "CROQUITO_DOCAI_PROCESSOR"`.
- Endpoint derivado do processador: a região está DENTRO do nome
  (`projects/p/locations/us/processors/x` →
  `https://us-documentai.googleapis.com/v1/{name}:process`). Valide o formato do
  nome com regex estrita e recuse na construção (erro de configuração, não de
  chamada).
- `GCP_DOCUMENT_AI_MODEL_ID: Final = "document-ai/ocr-processor"`.
- Escopo de auth: reuse `GCP_VISION_SCOPES` (cloud-platform serve para os dois) —
  se preferir constante própria com o mesmo valor, diga por quê no relatório.

### Adapter

`GcpDocumentAiOcrAdapter`, `@dataclass(frozen=True)`, espelho estrutural de
`GcpVisionOcrAdapter` (linhas 1945-2065 — leia inteiro antes):

- Campos: `credentials`, `processor_name: str`, `timeout_seconds: float = 30.0`,
  `raw_store`, `http_post`, `model_id: str = GCP_DOCUMENT_AI_MODEL_ID`.
- `_access_token`: mesmo mecanismo de refresh via `google-auth` transport local
  (`_UrllibAuthRequest`/`_AuthTransportResponse` já existem — reuse, não duplique).
- `execute`:
  - valida `request.task is PromptTask.OCR`, exige `image_bytes` e dimensões, como o
    atual (1977-1990).
  - body: `{"rawDocument": {"content": base64, "mimeType": "image/png"}}` — o
    pipeline só envia PNG (ingest gera PNG 200 DPI); deixe o mimeType como
    constante comentada, não parâmetro.
  - POST em `{endpoint}` com Bearer token; mapeamento de status HTTP IDÊNTICO aos
    demais adapters REST (use `_http_failure(provider=GCP_DOCUMENT_AI, ...)`).
  - resposta: `document.pages[].lines[]`, cada linha com
    `layout.textAnchor.textSegments` (índices em `document.text`) e
    `layout.boundingPoly.normalizedVertices`. Texto da linha = fatia de
    `document.text` pelos segments (concatenar múltiplos segments na ordem). Bbox =
    min/max dos `normalizedVertices` (já 0-1); vértice ausente ou caixa de área não
    positiva → linha RECUSADA (pule, não invente). `text_type`: Document AI OCR não
    declara manuscrito por linha de forma estável — use `"unknown"` sempre, com
    comentário.
  - truncamento: `raw_text` respeita o limite 1-200 de `OcrLineOutput` (trunque em
    200 como fizer o padrão do módulo; linha vazia após strip é recusada).
  - erro embutido em 200 (`response.get("error")`): mapeie para `UNAVAILABLE`, mesmo
    tratamento e mesmo comentário de motivo do Vision (2034-2040).
  - raw-store: `persist(provider=GCP_DOCUMENT_AI, input_digest=request.image_sha256,
    payload=...)` como o atual (2050-2056).

### Logger

`_ocr_failure` (937-971) fixa `ProviderName.GCP_VISION.value` nos logs. Parametrize o
provider (parâmetro com default `GCP_VISION` mantém os call-sites atuais idênticos) e
o adapter novo loga o próprio nome. Os testes de log existentes
(`test_ocr_token_failure_is_logged_without_the_credential` etc., 1107-1189) NÃO podem
mudar de asserção — se mudarem, você quebrou compatibilidade.

### Montagem

`build_real_provider_suite` (2502-2582): se `os.environ.get(DOCAI_PROCESSOR_ENV)`
não-vazio → braço `ocr` é
`RetryingProviderAdapter(BudgetedProviderAdapter(GcpDocumentAiOcrAdapter(...)))`, com
o MESMO `ocr_cost` (env `CROQUITO_AI_ESTIMATED_COST_PER_OCR_CALL_USD`) e o MESMO
`CostBudget`; senão, Cloud Vision exatamente como hoje. `build_synthetic_provider_suite`
NÃO muda (fixture continua `GCP_VISION`).

### Testes (espelho da bateria do Vision, 973-1229 e 2580-2660)

- parse: resposta real-shaped do DocAI (fixture JSON inline no teste) → linhas com
  texto correto e bbox min/max dos vértices; linha sem vértices é pulada; segment
  múltiplo concatena.
- erro-em-200 → `UNAVAILABLE`; status HTTP mapeados como os demais.
- token: falha de refresh logada sem credencial, com o nome `gcp_document_ai`.
- nome de processador malformado → recusa na construção.
- suite real com env definido monta DocAI; sem env, monta Vision (monkeypatch de
  `google.auth.default` como `_hosted_suite_env`, 2580-2593).
- `test_prompt_hashes_of_existing_tasks_are_frozen` (1967-1990) INTOCADO e verde.

## Out of scope

- `provider_review.py`, `ocr_eval.py`, `local_queue.py`, fixtures sintéticas.
- Docs (T2 desta feature).
- Dependência nova no pyproject (google-auth já cobre; se você concluir que precisa
  de algo, PARE e reporte).
- Remover ou alterar `GcpVisionOcrAdapter` além do logger parametrizado.

## Acceptance criteria

1. `make check`, `make test`, `make provider-contract-demo`, `make ocr-eval` verdes.
2. Bateria nova de testes do DocAI passa; bateria antiga do Vision passa sem mudança
   de asserção.
3. Nenhum log novo carrega imagem, texto integral, token ou URL assinada.
4. Sem env novo definido, o comportamento da suite é byte-idêntico ao atual.

## Validation

```bash
make check
make test
uv run pytest tests/worker/test_providers.py -x -q
make provider-contract-demo
make ocr-eval
```

## Required capabilities

READ, WRITE, VALIDATE. Sem COMMIT: deixe o diff na árvore.

## Report

`BUILD REPORT` completo do contrato do Builder, gravado em
docs/features/F-022-document-ai-braco-ocr/tasks/T1-build-report.md.
