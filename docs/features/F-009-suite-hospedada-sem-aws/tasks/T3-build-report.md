# T3 — Build Report

```text
BUILD REPORT

Status: BUILD_COMPLETE

Files changed:
  services/worker/src/croquito_worker/providers.py
    - ProviderName ganha GCP_VISION = "gcp_vision".
    - GcpVisionOcrAdapter novo: document text detection do Cloud Vision via REST puro
      (images:annotate, feature DOCUMENT_TEXT_DETECTION), autenticado por ADC
      (google.auth.default() + refresh via _UrllibAuthRequest, um transporte mínimo em
      cima de urllib.request — mesma escolha do resto do arquivo, sem puxar requests/
      urllib3). Sem endpoint regional fixo; timeout no mesmo CROQUITO_PROVIDER_TIMEOUT_
      SECONDS; ProviderExecution com model_id estável "cloud-vision/document-text-
      detection"; mapeamento HTTP igual aos demais adapters REST (_failure_from_http_
      status: 429->RATE_LIMITED, 401/403->REFUSED não-retryável, resto->UNAVAILABLE).
      Parsing de fullTextAnnotation.pages[].blocks[].paragraphs[] em _cloud_vision_lines/
      _cloud_vision_bbox/_cloud_vision_word_text (ver "Desvios conscientes" abaixo).
    - ProviderSuite ganha campo ocr: ProviderAdapter | None = None.
    - build_real_provider_suite: braço ocr SEMPRE presente, embrulhado em
      RetryingProviderAdapter(BudgetedProviderAdapter(GcpVisionOcrAdapter(...))) no MESMO
      CostBudget da rodada; custo estimado de CROQUITO_AI_ESTIMATED_COST_PER_OCR_CALL_USD
      (default "0.0015"); credenciais de google.auth.default(scopes=GCP_VISION_SCOPES).
    - build_synthetic_provider_suite: braço ocr com FixtureProviderAdapter
      (ProviderName.GCP_VISION), fixture OcrOutput nova com 3 linhas que confirmam as 3
      leituras sintéticas existentes (bbox igual à bbox de cada leitura; a cota do
      círculo central usa ponto na fixture de OCR contra vírgula na leitura, cobrindo a
      normalização decimal dentro do próprio contrato sintético).
  services/worker/src/croquito_worker/provider_review.py
    - _normalize_ocr_text, _normalized_boxes_intersect, _reading_confirmed_by_ocr novos:
      normalização nomeada (strip, colapso de espaço, vírgula->ponto) e interseção
      espacial "qualquer", nunca containment (tolerante a rotação).
    - build_provider_review_snapshot: depois de montar as leituras (âncora pós-fallback/
      comparação dupla), roda suite.ocr uma vez por documento — só quando há alguma
      leitura do LLM para conferir — e, por leitura, adiciona READING_{n}_OCR_CONFIRMED
      ou READING_{n}_OCR_EVIDENCE_MISSING às safety_notes, sem tocar em status.
      suite.ocr is None ou falha permanente do OCR -> nota única "OCR_UNAVAILABLE",
      pacote sai normal. BUDGET_EXCEEDED do OCR propaga como as demais chamadas do job.
  services/worker/src/croquito_worker/ocr_eval.py (novo)
    - run_ocr_corroboration_eval(output_dir): eval determinística e offline. Caso
      positivo (fixture padrão): afirma confirmation_recall == 1.0 (as 3 leituras
      confirmáveis confirmam). Caso negativo (_decoy_ocr_suite): remove a linha de OCR
      real da leitura 1 e insere uma decoy com o MESMO texto em bbox distante de
      qualquer leitura — afirma false_confirmed_count == 0 (nega o falso-confirmado por
      texto repetido, risco conhecido da task). Grava output/ocr-eval/ocr-eval.json via
      atomic_write_text, espelhando vision_eval.py/solver_eval.py.
  services/worker/src/croquito_worker/cli.py
    - Subcomando "ocr-eval" novo (--output), mesmo padrão de "vision-eval"/"solver-eval".
  Makefile
    - Target ocr-eval novo (uv run croquito-demo ocr-eval --output output/ocr-eval);
      adicionado ao .PHONY.
  pyproject.toml / uv.lock
    - google-auth>=2.56,<3 declarada como dependência direta (já era transitiva de
      google-cloud-pubsub; passa a ser direta porque há import direto de
      google.auth.default()). uv sync --all-groups resolveu sem conflito (86 pacotes).
  tests/worker/test_providers.py
    - _FakeGcpCredentials (ADC falso) e _hosted_suite_env monkeypatchando
      google.auth.default para os testes de build_real_provider_suite existentes
      continuarem passando sem rede/credencial real.
    - test_synthetic_provider_suite_covers_every_mvp_contract: comentário/asserção
      atualizados (a suite agora TEM braço ocr).
    - test_real_provider_suite_builds_two_direct_arms_without_aws: asserções novas de
      que o braço ocr é montado, autenticado pelas credenciais mockadas e reserva no
      MESMO CostBudget dos demais braços.
    - Testes novos (ver seção abaixo).

Testes novos (services/worker/src/croquito_worker/... via tests/worker/test_providers.py):
  test_gcp_vision_adapter_parses_full_text_annotation_into_normalized_lines
    - Requisito 1 do contrato: fixture de resposta Cloud Vision (fullTextAnnotation com
      um parágrafo de duas palavras) -> OcrOutput com bbox normalizada corretamente
      (vértices em pixel 10..90/20..40 sobre imagem 100x100 -> bbox 0.1/0.2/0.9/0.4) e
      raw_text reconstruído ("3,50 m").
  test_gcp_vision_adapter_maps_http_status_like_the_other_rest_adapters
    - 429 -> RATE_LIMITED, reaproveitando _failure_from_http_status como os demais REST.
  test_ocr_corroboration_confirms_matching_readings
    - Requisito 2: as 3 leituras sintéticas recebem READING_n_OCR_CONFIRMED; nenhuma
      EVIDENCE_MISSING; confirmação não muda o status já calculado (leitura 3 continua
      AMBIGUOUS por legibilidade, não por OCR).
  test_ocr_corroboration_flags_reading_without_spatial_evidence
    - Requisito 3: decoy com o mesmo texto da leitura 1 em bbox distante ->
      READING_1_OCR_EVIDENCE_MISSING (não CONFIRMED); status da leitura 1 permanece
      PROPOSED (OCR nunca rebaixa status nesta entrega).
  test_ocr_corroboration_missing_arm_adds_a_single_note
    - Requisito 4: suite.ocr=None -> exatamente uma nota OCR_UNAVAILABLE, nenhuma nota
      por leitura, pacote com leituras normais.
  test_ocr_corroboration_permanent_failure_adds_a_single_note
    - Requisito 5: falha UNAVAILABLE do braço ocr -> mesma nota única OCR_UNAVAILABLE,
      pacote normal.
  test_ocr_corroboration_budget_exceeded_propagates_without_a_note
    - BUDGET_EXCEEDED do OCR propaga como ProviderExecutionError, sem nota substituta.
  test_ocr_text_normalization_matches_decimal_comma_and_dot
    - Requisito 6: "3,50 m" normaliza igual a "3.50 m"; confirmação positiva com bbox
      coincidente, negativa sem linha e negativa com bbox distante (mesmo texto).
  test_ocr_corroboration_eval_passes
    - make ocr-eval fica coberto também como teste unitário (report.passed,
      confirmation_recall==1.0, false_confirmed_count==0, artefato gravado).

Validation executed:
  BASELINE (HEAD antes da mudança, T1+T2 já commitadas):
    make check -> exit 0 (herdado; não re-executado isolado porque a árvore já estava
      verde ao iniciar a task, confirmado no T2-build-report.md)
  CHANGE + FINAL (com a mudança completa):
    uv run ruff check .        -> All checks passed!
    uv run ruff format --check . -> 348 files already formatted
    uv run mypy --strict packages/core packages/valuation services/api services/worker tests
      -> Success: no issues found in 187 source files
    make check (ruff check/format, mypy strict, check_docs, schema_export --check-dir,
      contracts:check, web:check tsc+vite build, infra-check terraform fmt) -> exit 0,
      sem drift em scene.schema.json/scene.generated.ts
    make ocr-eval -> {"passed": true, "reading_count": 3, "confirmed_count": 3,
      "confirmation_recall": 1.0, "false_confirmed_count": 0}
    make test (uv run pytest + npm web:test)
      -> pytest: 1472 passed, 10 skipped, 47 warnings (126.43s)
      -> vitest: 29 arquivos, 529 testes passed
    uv sync --all-groups (após editar pyproject.toml) -> resolveu 86 pacotes, sem
      conflito; uv.lock atualizado (2 linhas).

Validation skipped: none

Unavailable capabilities: none

Assumptions:
  - "Linha" do OCR = um parágrafo de fullTextAnnotation.pages[].blocks[].paragraphs[],
    não a reconstrução exata por detectedBreak símbolo a símbolo (ver desvio abaixo).
  - Corroboração roda uma única chamada de OCR por documento, não por leitura — o braço
    ocr chama images:annotate uma vez com a imagem inteira, igual ao Textract legado.
  - "OCR ausente ou falha permanente" cobre também o caso em que não há nenhuma leitura
    do LLM para conferir: nesse caso o braço ocr simplesmente não é chamado (sem custo à
    toa) e nenhuma nota é adicionada (nem OCR_UNAVAILABLE nem por leitura), porque não há
    o que corroborar.
  - providers_json da entitlement de IA (services/api/src/croquito_api/main.py) NÃO
    ganhou "gcp_vision": o OCR é um suporte determinístico sempre ligado quando a suite
    real é construída, não um provedor de LLM que o tenant autoriza explicitamente —
    interpretação alinhada ao texto da task, que não menciona a rota de entitlement.

Remaining risks:
  - _cloud_vision_lines granula por parágrafo, não por linha reconstruída via
    detectedBreak. Para cotas de uma ou poucas palavras (o caso real deste produto) isso
    é equivalente; um parágrafo com várias linhas de texto real (não é o caso das cotas
    manuscritas/impressas curtas deste domínio) sairia como uma única OcrLineOutput
    "linha" com o texto de todas as linhas do parágrafo concatenado — sem fixture real do
    Cloud Vision contra prancha real para validar a reconstrução símbolo a símbolo, essa
    simplificação foi escolhida deliberadamente sobre inventar uma heurística de quebra
    não testável. Se o eval (T4/produção) revelar recall baixo por causa disso, é o
    primeiro lugar a revisar.
  - Erro por-imagem embutido no corpo 200 do Cloud Vision (responses[0].error) mapeia
    sempre para UNAVAILABLE (retryable), espelhando o tratamento pré-existente do
    TextractProviderAdapter para exceções do client; não há informação suficiente na
    resposta para diferenciar permanente de transitório sem uma tabela de error.code do
    Vision, que não foi construída nesta entrega.
  - O caminho real (build_real_provider_suite -> GcpVisionOcrAdapter com ADC de verdade)
    não foi exercitado contra o serviço Cloud Vision real nesta entrega — só via fixture/
    mock, como os demais adapters REST deste arquivo. A habilitação da API e o primeiro
    disparo real são da T5 + apply humano, conforme o próprio contrato desta task.

Human decisions required: none dentro do escopo desta task (a habilitação de
  vision.googleapis.com e o primeiro disparo real são da T5 + apply humano, como o
  contrato já registra).
```

## Desvios conscientes do spec

1. **Granularidade de "linha" do OCR (parágrafo, não reconstrução por `detectedBreak`).**
   O contrato pede `OcrOutput.lines`, mas o Cloud Vision `fullTextAnnotation` não expõe
   "linha" como unidade de primeira classe — só blocos, parágrafos, palavras e símbolos,
   com quebra de linha marcada símbolo a símbolo (`property.detectedBreak.type`).
   Reconstruir por quebra de símbolo é o caminho fiel, mas exige uma heurística sem
   fixture real do Cloud Vision para validar contra (a task não forneceu uma resposta
   real do serviço). Optei por usar o parágrafo como "linha": para as cotas curtas que
   este produto lê (uma ou poucas palavras por anotação, nunca um parágrafo de texto
   corrido), o parágrafo e a linha coincidem na prática esmagadora dos casos. Registrado
   como risco remanescente acima, não escondido.
2. **Erro embutido (`responses[0].error`) sempre mapeado para `UNAVAILABLE`.** O spec
   pede mapeamento HTTP coerente com os outros adapters, mas o Cloud Vision pode devolver
   HTTP 200 com um erro por imagem dentro do corpo (ex.: payload ilegível). Sem uma
   tabela de `error.code` do Vision para diferenciar permanente de transitório, segui o
   mesmo tratamento já usado pelo `TextractProviderAdapter` para exceções do client:
   `UNAVAILABLE`. É uma simplificação deliberada, documentada no código.
3. **Ramo "leitura sem bbox, só texto conta" não implementado.** O contrato da task
   previa esse caminho, mas `MeasurementReadingOutput.bbox` é campo obrigatório neste
   schema (nunca `None`) — o estado não é alcançável com o contrato atual. Implementar um
   `if` morto sem forma de testá-lo violaria a mesma disciplina que motivou não
   implementá-lo; documentado em `_reading_confirmed_by_ocr`.

## Oportunidades vistas e NÃO implementadas (fora de escopo)

- `docs/ai/MODEL_ROUTING.md`, `docs/operations/RUNBOOK_PROCESSING_FAILURES.md` e o bloco
  de comandos do `CLAUDE.md` raiz continuam descrevendo o fluxo Textract/`OCR_EVIDENCE_
  MISSING` antigo e não citam `make ocr-eval` — atualização é da T4 (Docs), explicitamente
  fora de escopo desta task.
- `providers_json` da entitlement de IA (`services/api/.../main.py`) não ganhou o braço
  `ocr` — ver "Assumptions" acima; se o produto decidir que Cloud Vision também deve
  entrar na allowlist por tenant, isso é uma decisão de produto/segurança fora do escopo
  desta task técnica.
- Reconstrução de linha por `detectedBreak` símbolo a símbolo (ver desvio 1) — mais fiel,
  mas não implementada por falta de fixture real para validar; primeiro candidato se o
  eval real (T4/produção) mostrar recall insuficiente.
- Document AI como escalada se o eval reprovar — explicitamente da T4/decisão de produto,
  não tocado.
