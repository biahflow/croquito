# T1 — Suite hospedada com braços openai + anthropic, sem AWS

Task Contract no formato do [template global](../../../engineering-os/templates/task.md),
derivado do [plano válido](../plan.md). Autossuficiente: assuma o Core (pinado em
`docs/engineering-os/`), este contrato e o repositório — nada mais.

## Identity

```text
feature_id: F-009
task_id: T1
parent_plan: docs/features/F-009-suite-hospedada-sem-aws/plan.md
depends_on: none
```

## Goal

A suite hospedada de providers passa a ter dois braços com nomes honestos — `openai`
e `anthropic` (API direta) — sem nenhum cliente AWS no caminho; a chamada morta de
OCR sai do snapshot; os rótulos gravados (`dataset_id`, `created_by`,
`providers_json`) passam a dizer a verdade; 401/403 deixam de ser retryáveis.

## Scope

Em `services/worker/src/croquito_worker/providers.py`:

- `ProviderSuite` (linhas 1453-1457): campos passam a `openai: ProviderAdapter` e
  `anthropic: ProviderAdapter`. O campo `textract` sai. (Números de linha são do
  commit base deste contrato; confie no conteúdo, não no número exato.)
- `build_real_provider_suite` (1625-1690): remover `import boto3` local, os braços
  Bedrock e Textract, `CROQUITO_AI_ESTIMATED_COST_PER_TEXTRACT_CALL_USD` e
  `CROQUITO_AWS_PROVIDER_REGION`. Braço novo:
  `AnthropicProviderAdapter(api_key=env CROQUITO_ANTHROPIC_API_KEY — obrigatória,
  ausência levanta ValueError como a da OpenAI; model_id=os.getenv("CROQUITO_ANTHROPIC_MODEL",
  "claude-opus-5"); timeout do mesmo CROQUITO_PROVIDER_TIMEOUT_SECONDS; raw_store
  compartilhado)`, embrulhado em `RetryingProviderAdapter(BudgetedProviderAdapter(...))`
  usando o MESMO `CostBudget` e o mesmo custo estimado por chamada LLM do braço
  OpenAI. Leia a assinatura real de `AnthropicProviderAdapter` (960-1073) antes.
- `build_synthetic_provider_suite` (1706-1887): braço `anthropic` com
  `FixtureProviderAdapter(provider=ProviderName.ANTHROPIC, ...)` (mesmos
  `shared_outputs`, variante `chat_answer` como hoje o braço bedrock tem); o braço
  textract sai da suite. Se a fixture de OCR (1872-1886) ficar órfã, movê-la para o
  teste que exercita `TextractProviderAdapter` ou removê-la — não deixar código morto.
- `_failure_from_http_status` (procure a função): 401 e 403 passam a mapear para um
  código NÃO-retryável (fora de `RetryingProviderAdapter.RETRYABLE` — ex.
  `ProviderFailureCode.REFUSED` ou código próprio já existente que não seja
  TIMEOUT/RATE_LIMITED/UNAVAILABLE). Chave inválida não pode queimar 3 tentativas.
- As CLASSES `BedrockAnthropicProviderAdapter` e `TextractProviderAdapter`
  PERMANECEM (usadas por `build_extraction_arm` e testes) — sai só o fio da suite.

Em `services/worker/src/croquito_worker/provider_review.py`:

- Remover a chamada morta de OCR (linha 184) e o isinstance (189-190), e o import de
  `OcrOutput` se ficar órfão.
- Renomear os usos `suite.bedrock_anthropic` → `suite.anthropic` (186, 272). NÃO
  mudar a ordem primário/fallback nem a âncora do laço de leituras — isso é a T2.

Em `services/worker/src/croquito_worker/local_queue.py`:

- Linha 543: `dataset_id=f"job-{job_id}"` (incondicional — identifica o documento do
  job, não a origem das respostas).
- Linha 597: `created_by` = `"offline-provider-contract-fixture"` quando a suite foi
  injetada (`self.provider_suite is not None`), `"hosted-provider-extraction-v1"`
  quando construída por `build_real_provider_suite`.
- Linha 1292 (chat): `suite.anthropic`.

Em `services/api/src/croquito_api/main.py`:

- Linha 2484: `providers_json=["openai", "anthropic"]`.

Testes a adaptar (mínimo):

- `tests/worker/test_providers.py`: 79 (suite sintética — campos novos; a linha do
  textract vira teste direto do adapter com fixture ou sai), 176-179 (lineage
  esperado `{"openai", "anthropic"}`), ~560 (build_real_provider_suite: sem boto3,
  exige `CROQUITO_ANTHROPIC_API_KEY`, monta com as duas chaves). Teste NOVO para
  401/403 não-retryável (contador de tentativas = 1).
- `tests/worker/test_local_queue.py`: 182 (providers_json), 280+ (asserções novas de
  `dataset_id == f"job-{job_id}"` e `created_by`), 484 (construção literal de
  ProviderSuite).
- `tests/api/test_api.py`: 193 (lista nova).

## Out of Scope

- Fallback provider→provider e inversão de primário (T2).
- Braço `ocr`/Cloud Vision (T3). Docs (T4). Deploy/Terraform (T5).
- `build_extraction_arm`, `build_embeddings_adapter`, fluxos valuation, CLI de eval —
  INTOCADOS (os testes existentes deles têm que continuar passando sem edição).
- Prompts/templates: nenhum hash de prompt congelado
  (`tests/worker/test_providers.py:301`) pode mudar.

## Acceptance Criteria

1. `make check` e `make test` verdes (checado pela execução).
2. `grep -rn "suite\.textract\|suite\.bedrock_anthropic" services/` vazio; `grep -n
   "boto3" services/worker/src/croquito_worker/providers.py` só aparece nos adapters
   Bedrock/Textract preservados, nunca em `build_real_provider_suite` (checado).
3. `build_real_provider_suite` sem `CROQUITO_ANTHROPIC_API_KEY` levanta ValueError; com
   as duas chaves monta a suite com lineage `ProviderName.ANTHROPIC` no braço novo
   (coberto por teste).
4. 401/403: uma tentativa só, sem retry (coberto por teste).
5. Nenhum arquivo fora do escopo listado alterado; `git diff --stat` confere.

## Validation

```text
baseline: make check e make test verdes no commit base (branch
          feat/f-009-suite-hospedada-sem-aws, base 707832d)
required: full: make check
          full: make test
```

## Required Capabilities

```text
READ:     o repositório
WRITE:    services/worker/src/croquito_worker/{providers.py,provider_review.py,local_queue.py},
          services/api/src/croquito_api/main.py,
          tests/worker/{test_providers.py,test_local_queue.py}, tests/api/test_api.py
VALIDATE: make check; make test
COMMIT:   forbidden — a entrega é o diff na árvore mais o BUILD REPORT
```

## Context to Read First

1. `AGENTS.md` (raiz) e `CLAUDE.md` do repositório.
2. `services/worker/src/croquito_worker/providers.py`: 32-49 (enums), 693-778
   (protocolo e output models), 960-1073 (AnthropicProviderAdapter), 1453-1457,
   1532-1588 (build_extraction_arm — NÃO tocar), 1625-1690, 1706-1887.
3. `services/worker/src/croquito_worker/provider_review.py` por inteiro (317 linhas).
4. `services/worker/src/croquito_worker/local_queue.py`: 443-613, 1292.
5. [Feature Contract](../feature.md) e [docs/ai/MODEL_ROUTING.md](../../../ai/MODEL_ROUTING.md)
   (a seção de lineage direto × Bedrock explica por que o rename importa).

## Known Risks

- `mypy strict` é seu amigo no rename: rode cedo, ele aponta todo uso restante dos
  campos antigos.
- A fixture de OCR órfã: não deixar import/função morta (ruff acusa).
- `test_cli.py:100-124` monkeypatcha `build_extraction_arm` esperando
  `provider == "bedrock"` — se ele quebrar, você saiu do escopo.

## Human Gates

- Nenhum dentro do escopo. Commit, merge e deploy são atos humanos fora deste contrato.

## Reporting

Encerre com o `BUILD REPORT` completo do
[contrato do Builder](../../../engineering-os/agents/builder.md) — todos os campos,
`none` onde vazio — e grave o mesmo conteúdo em
`docs/features/F-009-suite-hospedada-sem-aws/tasks/T1-build-report.md`.
