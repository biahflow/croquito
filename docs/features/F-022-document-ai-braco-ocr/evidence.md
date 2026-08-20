# F-022 — Evidência de execução

Pacote de evidência no formato do processo (`BASELINE → CHANGE → FINAL`). Fontes
primárias: BUILD REPORTs por task, preservados com atribuição.

## Baseline

Árvore de 2026-08-20 sobre `main` (6aaf632) com os diffs aceitos de F-021 (T1+T2)
presentes e não commitados. `make check` exit 0; pytest 1602 passed;
`make provider-contract-demo` com `readings=3`; `make ocr-eval` com `recall=1.0`,
`false_confirmed=0`.

## Execução

| Task | Builder (harness/modelo) | Report (PRIMARY_EXECUTION_EVIDENCE) | Status |
|---|---|---|---|
| T1 adapter | Claude Code / implementador-opus | [T1-build-report.md](tasks/T1-build-report.md) | BUILD_COMPLETE |
| T2 docs | Claude Code / implementador-sonnet | [T2-build-report.md](tasks/T2-build-report.md) | BUILD_COMPLETE |

Desvios conscientes aceitos na revisão (T1): `os.getenv(...).strip()` para env só de
espaços (precedente `_openai_arm_enabled`); coordenada ausente de vértice recusa a
linha em vez de valer o zero do proto3 (caixa inflada viraria falso-confirmado na
corroboração por interseção — perder linha é a falha barata); `endpoint` como property
derivada do `processor_name` (campo permitiria contradição); reuso de
`GCP_VISION_SCOPES` (valor idêntico para os dois fornecedores).

## Revisão (orquestrador da sessão, linha a linha)

Diff de `providers.py` (+340/−13) conferido: parse de `textAnchor`/`textSegments`
(string do proto3, multi-segmento na ordem), bbox min/max de `normalizedVertices` com
recusa de degenerado, erro-em-200 → `UNAVAILABLE`, raw-store sob `gcp_document_ai`
amarrado ao digest, `_ocr_failure` parametrizado com default preservando o Vision,
montagem por `CROQUITO_DOCAI_PROCESSOR` com fallback byte-idêntico. Zero linhas
removidas em `tests/worker/test_providers.py`; teste dedicado prova que o braço antigo
segue logando sob o próprio nome; hash congelado do prompt `ocr` intocado.

## Validação integrada (FINAL, re-executada pelo orquestrador)

- `uv run pytest tests/` → 1641 passed, 10 skipped (39 novos da T1)
- `uv run pytest tests/worker/test_providers.py` → 269 passed
- `make check` → exit 0 (inclui check_docs com os docs da T2)
- `make provider-contract-demo` e `make ocr-eval` → verdes, saída idêntica à baseline

## Riscos remanescentes

- Nenhum processador Document AI provisionado; o braço novo nunca rodou contra o
  serviço real — toda menção documental é condicional.
- Granularidade de linha (parágrafo→linha de layout) só será medida no eval
  comparativo pago (gate do ADR-0037).
- Default de `CROQUITO_AI_ESTIMATED_COST_PER_OCR_CALL_USD` (0.0015) é preço de
  Vision; revisar junto do provisionamento.

## Decisões humanas pendentes

- Aceite do [ADR-0037](../../adr/0037-document-ai-como-braco-de-ocr.md) (Proposed).
- Commit dos diffs da árvore.
- Habilitar `documentai.googleapis.com` + provisionar o processador
  (`biahflow/infra`) e definir `CROQUITO_DOCAI_PROCESSOR` em HML.
- Eval comparativo pago Cloud Vision × Document AI antes de promover o braço.
