# T3 — Braço OCR determinístico: Cloud Vision com corroboração real

Task Contract no formato do [template global](../../../engineering-os/templates/task.md),
derivado do [plano válido](../plan.md). Autossuficiente: assuma o Core (pinado em
`docs/engineering-os/`), este contrato e o repositório — nada mais.

## Identity

```text
feature_id: F-009
task_id: T3
parent_plan: docs/features/F-009-suite-hospedada-sem-aws/plan.md
depends_on: [T1]
```

## Goal

A suite ganha um braço opcional de OCR determinístico — Cloud Vision (document text
detection), autenticado pela service account do ambiente (ADC, sem chave nova) — e o
snapshot passa a CONSUMIR o OCR de verdade: cada leitura extraída pelos LLMs é
confirmada (ou não) contra o texto que o OCR encontrou na região, com a confirmação
registrada por leitura e a nota `OCR_EVIDENCE_MISSING` quando não confirmada.
Decisão do usuário (2026-08-19): "OCR de verdade, determinístico + LLM, não elas
sozinhas decidindo". Document AI fica registrado como escalada se o eval reprovar
(isso é da T4, não sua).

## Scope

Em `services/worker/src/croquito_worker/providers.py`:

- `GcpVisionOcrAdapter` novo implementando o Protocol `ProviderAdapter` para
  `PromptTask.OCR` → `OcrOutput` (schema existente: `lines` com `raw_text`, `bbox`
  normalizado 0-1, `text_type`). Chamada REST `images:annotate` com
  `DOCUMENT_TEXT_DETECTION` usando ADC (token via
  `google.auth.default()` + refresh — verifique o que o repo já tem de dependência
  Google antes de adicionar qualquer coisa ao pyproject; se precisar de dependência
  nova, adicione ao grupo certo e registre no relatório). Sem endpoint hardcoded de
  região; timeout do mesmo `CROQUITO_PROVIDER_TIMEOUT_SECONDS`. `ProviderExecution`
  com `provider` novo no enum (`ProviderName.GCP_VISION = "gcp_vision"`), model_id
  estável (ex. `"cloud-vision/document-text-detection"`), usage com custo estimado
  próprio (env `CROQUITO_AI_ESTIMATED_COST_PER_OCR_CALL_USD`, default `"0.0015"`),
  raw_response_ref via raw_store como os demais.
- `ProviderSuite`: campo `ocr: ProviderAdapter | None = None`.
- `build_real_provider_suite`: braço ocr SEMPRE presente (embrulhado em
  `RetryingProviderAdapter(BudgetedProviderAdapter(...))` no MESMO CostBudget).
- `build_synthetic_provider_suite`: braço ocr com `FixtureProviderAdapter`
  (`ProviderName.GCP_VISION`) reaproveitando a fixture de OcrOutput que a T1
  realocou; a fixture deve conter linhas que confirmam as leituras sintéticas
  existentes (para os testes atuais do snapshot continuarem representativos).
- Mapeamento HTTP→falha coerente com os outros adapters (429→RATE_LIMITED,
  5xx→UNAVAILABLE, 401/403→não-retryável, etc. — siga o padrão pós-T1).

Em `services/worker/src/croquito_worker/provider_review.py`:

- Após montar as leituras (pós-comparação dupla/fallback), corroboração:
  para cada leitura, procurar nas `lines` do OCR um match do `raw_text` normalizado
  (normalização mínima e nomeada: strip, colapso de espaços, vírgula↔ponto decimal)
  cuja `bbox` intersecte a bbox de evidência da leitura (interseção simples; se a
  leitura não tiver bbox, só o match textual conta e isso fica dito no código).
  - Confirmada: registrar por leitura (campo/nota estruturada — siga o formato que o
    `ReviewPacket` suporta hoje; se não houver campo natural, uma nota
    `READING_{n}_OCR_CONFIRMED` é aceitável; NÃO invente campo novo de contrato
    Pydantic→TS sem necessidade — se precisar mudar `ReviewPacket`, PARE e reporte,
    porque isso dispara `make contracts` e revisão de contrato).
  - Não confirmada: nota `READING_{n}_OCR_EVIDENCE_MISSING` + a leitura NUNCA fica
    melhor que `AMBIGUOUS`... CUIDADO: não rebaixe leitura `proposed` concordante
    dos dois LLMs por falha de OCR de rotação/normalização — o rebaixamento é
    exatamente o sinal, então registre a nota SEM mudar o status nesta entrega
    (calibração de status é a F-010; a nota é o dado).
  - OCR ausente (`suite.ocr is None`) ou falha permanente da chamada: nota única
    `OCR_UNAVAILABLE` no pacote, sem derrubar o job e sem fallback para LLM.
- `BUDGET_EXCEEDED` do OCR: mesmo tratamento dos demais (propaga).

Eval (padrão vision-eval):

- Target novo `make ocr-eval` (ou extensão de eval existente se houver encaixe
  natural — justifique a escolha): roda a corroboração sobre a prancha sintética do
  repo com a fixture de OCR e afirma recall de confirmação 100% das leituras
  confirmáveis + zero falso-confirmada. Determinístico, offline, grava em `output/`.

Testes em `tests/worker/test_providers.py` (+ `test_local_queue.py` se necessário):

1. Adapter: resposta Cloud Vision fixture → OcrOutput com bbox normalizada.
2. Corroboração confirma leitura (nota/registro presente).
3. Corroboração não confirma → `READING_n_OCR_EVIDENCE_MISSING`, status intacto.
4. `suite.ocr=None` → `OCR_UNAVAILABLE`, pacote sai normal.
5. Falha permanente do OCR → `OCR_UNAVAILABLE`, pacote sai normal.
6. Normalização: `3,50` confirma `3.50`.

## Out of Scope

- Document AI. Mudança de status de leitura por OCR (F-010). Docs (T4).
- Mudanças em `SceneRevision`/contratos gerados — se parecer necessário, PARE e
  reporte.
- `local_queue.py` além do estritamente necessário para passar o braço ocr.

## Acceptance Criteria

1. `make check` e `make test` verdes; eval novo verde (checado pela execução).
2. Upload sintético via suite fixture continua gerando pacote com as MESMAS leituras
   de antes + registros de confirmação (regressão zero nos testes existentes, salvo
   asserções novas).
3. Nenhum arquivo de contrato gerado (`scene.schema.json`/`scene.generated.ts`)
   alterado.
4. Nenhuma credencial/chave nova: o adapter real usa ADC.

## Validation

```text
baseline: make check e make test verdes após T1 na branch
required: full: make check
          full: make test
          eval: make ocr-eval (ou o target escolhido, nomeado no relatório)
```

## Required Capabilities

```text
READ:     o repositório
WRITE:    services/worker/src/croquito_worker/{providers.py,provider_review.py},
          tests/worker/*, Makefile (target de eval), pyproject.toml (só se
          dependência nova for inevitável), tests/fixtures conforme necessário
VALIDATE: make check; make test; o eval novo
COMMIT:   forbidden — a entrega é o diff na árvore mais o BUILD REPORT
```

## Context to Read First

1. `AGENTS.md` (raiz) e `CLAUDE.md`.
2. `providers.py` pós-T1: adapters existentes (o TextractProviderAdapter preservado
   é o exemplo de OCR→OcrOutput com normalização de bbox), `OcrOutput`,
   `FixtureProviderAdapter`, wrappers de retry/budget.
3. `provider_review.py` pós-T1/T2 (se T2 já tiver entregue).
4. `Makefile` targets de eval existentes (`vision-eval`, `solver-eval`) e
   `tests/bundles.py`/fixtures sintéticas.
5. [Feature Contract](../feature.md).

## Known Risks

- Rotação de texto em prancha: document text detection devolve bbox de palavras
  rotacionadas — a interseção com a bbox de evidência precisa ser tolerante
  (interseção qualquer, não containment).
- Falso-confirmado por texto repetido na prancha (mesma cota em dois lugares): o
  match exige interseção espacial quando há bbox — não relaxe isso.
- Dependência nova do Google: prefira REST puro com a lib de auth que já exista no
  ambiente; adicionar SDK pesado do Vision é overkill.

## Human Gates

- Nenhum dentro do escopo (a habilitação da API `vision.googleapis.com` é da T5 +
  apply humano).

## Reporting

Encerre com o `BUILD REPORT` completo do
[contrato do Builder](../../../engineering-os/agents/builder.md) e grave o mesmo
conteúdo em `docs/features/F-009-suite-hospedada-sem-aws/tasks/T3-build-report.md`.
