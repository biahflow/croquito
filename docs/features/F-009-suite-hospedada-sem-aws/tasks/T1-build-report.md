# T1 — BUILD REPORT

```text
BUILD REPORT

Status: BUILD_COMPLETE

Files changed:
  services/worker/src/croquito_worker/providers.py
    - ProviderSuite passa a ter os campos `openai` e `anthropic`; `bedrock_anthropic` e
      `textract` saem da suite (as CLASSES dos dois adapters permanecem, usadas por
      build_extraction_arm e por teste direto).
    - build_real_provider_suite: sai `import boto3`, saem os braços Bedrock e Textract,
      sai CROQUITO_AI_ESTIMATED_COST_PER_TEXTRACT_CALL_USD e sai CROQUITO_AWS_PROVIDER_REGION;
      entra AnthropicProviderAdapter com CROQUITO_ANTHROPIC_API_KEY obrigatória
      (ValueError na ausência, como a da OpenAI), CROQUITO_ANTHROPIC_MODEL default
      "claude-opus-5", mesmo CostBudget e mesmo custo estimado por chamada LLM do braço
      OpenAI, embrulhado em RetryingProviderAdapter(BudgetedProviderAdapter(...)).
    - build_synthetic_provider_suite: braço `anthropic` com FixtureProviderAdapter
      (provider=ProviderName.ANTHROPIC, mesmos shared_outputs, variante chat_answer); o
      braço textract e a fixture de OCR órfã saem.
    - _failure_from_http_status: 401/403 passam a mapear para REFUSED (fora de
      RetryingProviderAdapter.RETRYABLE); 429 segue RATE_LIMITED e o resto UNAVAILABLE.
  services/worker/src/croquito_worker/provider_review.py
    - Sai a chamada morta de OCR, o isinstance que a validava e o import órfão de OcrOutput.
    - suite.bedrock_anthropic -> suite.anthropic nos dois usos (extração e geometria); ordem
      primário/fallback e âncora do laço de leituras intocadas (T2).
    - Nota de segurança deixa de citar OCR, que não é mais executado.
  services/worker/src/croquito_worker/local_queue.py
    - dataset_id do snapshot passa a f"job-{job_id}" (identifica o documento do job, não a
      origem das respostas).
    - created_by passa a "offline-provider-contract-fixture" quando a suite foi injetada e
      "hosted-provider-extraction-v1" quando foi construída por build_real_provider_suite.
    - Braço de chat passa a suite.anthropic.
  services/api/src/croquito_api/main.py
    - providers_json do registro de autorização passa a ["openai", "anthropic"].
  tests/worker/test_providers.py
    - Suite sintética: asserção do braço anthropic e dos providers declarados; a linha do
      textract sai (o contrato de OCR segue coberto pelo teste direto do adapter).
    - Lineage esperado do snapshot passa a {"openai", "anthropic"}.
    - Testes novos (abaixo).
  tests/worker/test_local_queue.py
    - providers_json nas duas seeds; ProviderSuite literal com dois braços; asserções novas
      de dataset_id/created_by; teste novo do rótulo hospedado.
  tests/api/test_api.py
    - providers_json esperado da autorização contratual.
  tests/worker/test_chat_worker.py
    - provider gravado no turno de conversa passa de bedrock_anthropic para anthropic
      (consequência direta do rename do braço de chat; ver desvios).

Validation executed:
  BASELINE (commit base 39a0666, árvore como recebida):
    make check -> exit 0
    make test  -> exit 0  (1453 passed, 10 skipped)
  FINAL (com a mudança):
    make check -> exit 0
      ruff check . -> All checks passed!
      ruff format --check . -> 344 files already formatted
      mypy strict (packages/core, packages/valuation, services/api, services/worker, tests)
        -> Success, 186 source files
      scripts/check_docs.py, schema_export --check, contracts:check -> sem drift
      npm web:check (tsc -b && vite build) -> built
      terraform fmt -check -recursive infra -> ok
    make test  -> exit 0  (pytest: 1455 passed, 10 skipped; vitest: 29 files / 529 tests passed)
  Verificações do contrato:
    grep -rn "suite\.textract|suite\.bedrock_anthropic" services/ -> vazio
    grep -n "boto3" services/worker/src/croquito_worker/providers.py
      -> só linhas 1557 e 1580, ambas dentro de build_extraction_arm; nenhuma em
         build_real_provider_suite

Validation skipped: none

Unavailable capabilities: none

Assumptions:
  - "claude-opus-5" é id válido da Messages API da Anthropic (conferido na referência de
    modelos antes de escrever o default), então o default do contrato foi mantido literal.
  - O rótulo "hosted-provider-extraction-v1" distingue a origem da suite, não o modelo: a
    condição usada é `self.provider_suite is not None`, exatamente como o contrato pede.
  - A fixture de OCR removida não deixou o contrato descoberto porque
    `test_textract_adapter_maps_handwriting_without_raw_reference` já exercita
    TextractProviderAdapter diretamente com fixture própria; nada foi movido.

Remaining risks:
  - `dataset_id` gravado muda de "synthetic-provider-contract-v1" para "job-<id>" apenas para
    revisões NOVAS. Revisões já gravadas mantêm o rótulo antigo; nenhum caminho reescreve o
    passado, e nenhum código consulta esse valor como chave. O CLI (`cli.py:915`) continua
    gravando o rótulo sintético, o que ali é verdade (demo sintética) e está fora do escopo.
  - O braço `anthropic` da suite real nunca chamou a API de verdade neste repositório: o
    teste cobre montagem e lineage com http_post injetado, não a resposta real do fornecedor.
    A primeira chamada paga é ato humano do runbook (T5), fora deste contrato.
  - Timeout default do braço Anthropic ficou em 60s (o do adapter e o de
    build_extraction_arm) contra 30s do braço OpenAI; com CROQUITO_PROVIDER_TIMEOUT_SECONDS
    definida, os dois usam o mesmo valor. Ver desvios.

Human decisions required:
  - Nenhuma dentro deste contrato. Commit, merge e deploy seguem atos humanos.
  - FORA do escopo, mas encontrado na árvore: `.github/workflows/deploy-hml.yml` está
    modificado e NÃO foi tocado por este builder (é material de T5 — flag da API/worker,
    secrets das duas chaves, teto e allowlist). Preservado intacto; precisa de decisão de
    quem o escreveu sobre em qual entrega ele viaja.
```

## Desvios conscientes do contrato

1. **`tests/worker/test_chat_worker.py` alterado, embora não listado.** O contrato lista
   como "testes a adaptar (mínimo)" apenas `test_providers.py`, `test_local_queue.py` e
   `test_api.py`. O rename do braço de chat (`local_queue.py:1292`), que é escopo explícito,
   faz o turno gravar `provider = "anthropic"` no lugar de `"bedrock_anthropic"`, e as duas
   asserções de lineage do chat reprovaram. É consequência direta da mudança em escopo, não
   conserto de área alheia: só as duas linhas de asserção mudaram.

2. **Não havia teste prévio de `build_real_provider_suite`.** O contrato aponta "~560
   (build_real_provider_suite: ...)" como teste a adaptar; naquela linha vive
   `test_permanent_bedrock_errors_are_not_retried`, e `grep -rn build_real_provider_suite
   tests/` era vazio no commit base. A função nunca teve cobertura. Em vez de adaptar um
   teste inexistente, foram escritos três novos (ver abaixo).

3. **Default de timeout do braço Anthropic é 60s, não 30s.** O contrato diz "timeout do mesmo
   `CROQUITO_PROVIDER_TIMEOUT_SECONDS`", e a variável é a mesma nos dois braços. O que difere
   é o *default* quando ela não está definida: o braço OpenAI mantém "30" (comportamento
   inalterado) e o Anthropic usa "60", que é o default do próprio `AnthropicProviderAdapter`
   e o que `build_extraction_arm` já usa para o mesmo eixo. Unificar em 30s encurtaria em
   silêncio o teto de uma chamada de visão que hoje tem 60s em toda outra via do repositório.

4. **A nota de segurança do pacote deixou de citar OCR.** Com a chamada morta removida,
   `"Leituras de OCR e dos dois providers são observações..."` passaria a afirmar uma
   evidência que não foi produzida. Virou `"Leituras dos dois providers são observações..."`.
   Nenhum teste dependia do texto anterior; o braço de OCR real é T3 e reescreverá a nota.

## Testes novos e o que cobrem

| Teste | Cobre |
|---|---|
| `test_credential_failures_are_not_retried_over_http` (401 e 403, parametrizado) | Chave inválida falha em **uma** tentativa (`attempts == 1`) com código `REFUSED`, atravessando `RetryingProviderAdapter` de verdade — não só o mapeamento. |
| `test_http_status_mapping_keeps_transport_failures_retryable` | O mapeamento novo não roubou a retentativa de falha transitória: 429 segue `RATE_LIMITED` e 5xx segue `UNAVAILABLE`, ambos em `RETRYABLE`. |
| `test_real_provider_suite_requires_both_api_keys` (parametrizado nas duas chaves) | Ausência de `CROQUITO_OPENAI_API_KEY` **ou** de `CROQUITO_ANTHROPIC_API_KEY` levanta `ValueError` nomeando a variável faltante. |
| `test_real_provider_suite_builds_two_direct_arms_without_aws` | Com as duas chaves a suite monta; `boto3.client` é monkeypatchado para falhar o teste se for chamado, mesmo com `AWS_ACCESS_KEY_ID/SECRET` presentes no ambiente (o cenário exato do HML); as chaves chegam ao adapter certo; o modelo default é `claude-opus-5`; e os dois braços compartilham o **mesmo** objeto `CostBudget`. |
| `test_real_provider_suite_arms_declare_their_own_lineage` | Executando cada braço com `http_post` injetado, o lineage gravado é `ProviderName.OPENAI` e `ProviderName.ANTHROPIC` — critério de aceite 3. |
| `test_hosted_suite_labels_the_revision_as_paid_extraction` (local_queue) | Caminho em que `provider_suite is None` e a suite vem de `build_real_provider_suite` (monkeypatchado para fixture, nada sai da máquina): `created_by == "hosted-provider-extraction-v1"` e `dataset_id == "job-<id>"`. |
| asserções novas em `test_explicit_provider_fixture_persists_non_exportable_review_snapshot` | Caminho da suite injetada: `created_by == "offline-provider-contract-fixture"` e `dataset_id == "job-<id>"` propagado a packet, associações e propostas. |

## Oportunidades vistas e NÃO implementadas (fora de escopo)

- `_failure_from_http_status` mapeia **404** para `UNAVAILABLE`, ou seja, retentável — para
  um endpoint fixo do adapter, 404 é tão permanente quanto 401. Não mexi: o contrato nomeia
  só 401 e 403.
- `cli.py:915` ainda grava `dataset_id="synthetic-provider-contract-v1"`. Ali é demo
  sintética de verdade, mas o rótulo passa a divergir do da fila; se T4 padronizar o
  vocabulário de dataset, vale reavaliar.
- `ProviderName.BEDROCK_ANTHROPIC` e `ProviderName.TEXTRACT` continuam no enum e são
  necessários (adapters preservados, lineage já gravado). Nenhuma limpeza cabe aqui.
- Fallback provider→provider, inversão de primário, braço `ocr`/Cloud Vision, docs e deploy
  seguem intocados por serem T2/T3/T4/T5.
