# T2 — Fallback por tarefa com degradação transparente (Anthropic primário)

Task Contract no formato do [template global](../../../engineering-os/templates/task.md),
derivado do [plano válido](../plan.md). Autossuficiente: assuma o Core (pinado em
`docs/engineering-os/`), este contrato e o repositório — nada mais.

## Identity

```text
feature_id: F-009
task_id: T2
parent_plan: docs/features/F-009-suite-hospedada-sem-aws/plan.md
depends_on: [T1]
```

## Goal

`build_provider_review_snapshot` sobrevive à falha permanente de um braço LLM sem
derrubar o job e sem esconder nada: degrada para o braço restante com nota de
segurança explícita, e toda leitura extraída sem comparação dupla nasce `AMBIGUOUS`.
Decisão do usuário (2026-08-19): **Anthropic é o braço primário; OpenAI é o
fallback** e a contraparte da comparação.

## Scope

Somente `services/worker/src/croquito_worker/provider_review.py` e testes.

Comportamento por tarefa (a matriz é normativa):

| Tarefa | Primário | Fallback | Nota de segurança no pacote |
|---|---|---|---|
| PAGE_SURVEY | `suite.anthropic` | `suite.openai` | `PROVIDER_FALLBACK_PAGE_SURVEY_OPENAI` |
| MEASUREMENT_EXTRACTION | dupla comparada (âncora das readings = braço anthropic; openai = contraparte de divergência) | braço único sobrevivente | `PROVIDER_FALLBACK_SINGLE_EXTRACTOR_OPENAI` ou `PROVIDER_FALLBACK_SINGLE_EXTRACTOR_ANTHROPIC` (nomeia quem SOBREVIVEU) |
| GEOMETRY_EXTRACTION | `suite.anthropic` | `suite.openai` | `PROVIDER_FALLBACK_GEOMETRY_EXTRACTION_OPENAI` |

Regras:

- Fallback SÓ após falha permanente (o `RetryingProviderAdapter` já esgotou as
  transitórias — você recebe a `ProviderExecutionError` final).
- `ProviderFailureCode.BUDGET_EXCEEDED` NUNCA aciona fallback: re-levanta
  imediatamente (a segunda chamada consumiria o mesmo teto compartilhado; o
  tratamento definitivo já existe em `local_queue.py`).
- Os dois braços falhando numa tarefa obrigatória: a exceção propaga (semântica
  atual de reentrega).
- Implementar via helper único (sugestão do plano):
  `_execute_with_fallback(primary, secondary, request, notes, note_code) -> ProviderExecution`
  — na extração dupla, captura individual por braço em vez do helper, porque os dois
  são chamados de propósito.
- Inversão de âncora: hoje o survey roda em `suite.openai` e o laço de leituras
  (~203-261 no commit base; T1 pode ter deslocado) itera
  `openai_extraction.output.readings`. Passa a: survey primário `anthropic`; laço
  ancorado nas readings do braço `anthropic`, com `openai` como contraparte.
  No modo dual: `extractor="anthropic+openai"`, lineage `[anthropic, openai]`.
  No modo braço único: TODA leitura nasce `ReadingStatus.AMBIGUOUS` (sem comparação
  não existe `proposed`), lineage com UMA entrada honesta, `extractor` com um nome
  só, SEM nota `READING_n_PROVIDER_DISAGREEMENT` (a nota de fallback já declara a
  degradação).
- Notas `READING_n_*` e caminho `REGION_CLASSIFICATION_REQUIRED` preservados;
  geometria em fallback continua passando por `register_to_ink`/
  `corroborate_with_ink` normalmente.
- NENHUM template/prompt muda (hashes congelados de
  `tests/worker/test_providers.py` têm que continuar passando sem edição).

Testes novos em `tests/worker/test_providers.py` (use `FixtureProviderAdapter` com
`failures` e um wrapper contador de chamadas):

1. Survey do braço anthropic falha permanente → survey vem do openai + nota
   `PROVIDER_FALLBACK_PAGE_SURVEY_OPENAI`; extração segue dupla e leitura
   concordante segue `proposed`.
2. Braço openai falha na extração → leituras do anthropic, todas `AMBIGUOUS`,
   lineage 1 entrada, `extractor="anthropic"`, nota
   `PROVIDER_FALLBACK_SINGLE_EXTRACTOR_ANTHROPIC`.
3. Simétrico (anthropic falha → sobrevive openai) — cobre a troca de âncora.
4. Geometria anthropic falha → propostas do openai + nota
   `PROVIDER_FALLBACK_GEOMETRY_EXTRACTION_OPENAI`, todas `unresolved`.
5. `BUDGET_EXCEEDED` no primário → propaga SEM chamar o segundo braço (contador
   prova zero chamadas no reserva).
6. Os dois braços falham na extração → `ProviderExecutionError` propaga.
7. Invariante: nenhum caminho de fallback produz leitura `proposed` a partir de
   braço único nem pacote exportável.

Atualize também o teste de lineage dual existente (ordem nova `[anthropic, openai]`
e `extractor="anthropic+openai"`), se a T1 ainda não o fez.

## Out of Scope

- Braço `ocr` (T3). Docs (T4). `local_queue.py`, `providers.py` (salvo se um helper
  de teste pedir export mínimo — justifique no relatório). Prompts/templates.

## Acceptance Criteria

1. `make check` e `make test` verdes (checado pela execução).
2. Os 7 testes novos passam e falham se a lógica for revertida (rode-os contra o
   comportamento antigo mentalmente: cada um afirma algo que só o fallback novo
   produz).
3. Nenhum hash de prompt congelado editado.
4. `git diff --stat` restrito a provider_review.py + testes.

## Validation

```text
baseline: make check e make test verdes após o merge da T1 na branch
required: full: make check
          full: make test
```

## Required Capabilities

```text
READ:     o repositório
WRITE:    services/worker/src/croquito_worker/provider_review.py,
          tests/worker/test_providers.py
VALIDATE: make check; make test
COMMIT:   forbidden — a entrega é o diff na árvore mais o BUILD REPORT
```

## Context to Read First

1. `AGENTS.md` (raiz) e `CLAUDE.md`.
2. `provider_review.py` por inteiro NO ESTADO PÓS-T1 (o rename já aconteceu).
3. `providers.py`: `RetryingProviderAdapter`, `ProviderExecutionError`,
   `ProviderFailureCode`, `FixtureProviderAdapter`.
4. [Feature Contract](../feature.md), matriz D3 do plano.

## Known Risks

- A âncora do laço no modo braço único é o risco número 1 da feature: um deslize
  derruba silenciosamente a extração do sobrevivente.
- Ordem dos excepts: BUDGET_EXCEEDED tem que ser distinguido ANTES de qualquer
  tentativa de fallback.
- Não transformar falha transitória em fallback: quem esgota retries é o wrapper;
  aqui só se reage à exceção final.

## Human Gates

- Nenhum dentro do escopo.

## Reporting

Encerre com o `BUILD REPORT` completo do
[contrato do Builder](../../../engineering-os/agents/builder.md) e grave o mesmo
conteúdo em `docs/features/F-009-suite-hospedada-sem-aws/tasks/T2-build-report.md`.
