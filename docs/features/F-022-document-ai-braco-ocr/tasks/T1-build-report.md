# T1 — Build Report

Relatório do Builder para a task `F-022-T1`, no formato exigido pelo
[contrato do Builder](../../../engineering-os/agents/builder.md).

```text
BUILD REPORT

Status: BUILD_COMPLETE

Files changed:
  - services/worker/src/croquito_worker/providers.py
    (+340/-13) `ProviderName.GCP_DOCUMENT_AI`; constantes `DOCAI_PROCESSOR_ENV`,
    `DOCAI_PROCESSOR_PATTERN`, `GCP_DOCUMENT_AI_MODEL_ID`,
    `DOCAI_RAW_DOCUMENT_MIME_TYPE`, `OCR_LINE_TEXT_LIMIT`; helpers
    `_document_ai_endpoint`, `_document_ai_index`, `_document_ai_segment_text`,
    `_document_ai_bbox`, `_document_ai_lines`; adapter `GcpDocumentAiOcrAdapter`;
    `_ocr_failure` ganhou o parâmetro `provider` com default `GCP_VISION`;
    `build_real_provider_suite` escolhe o braço `ocr` por `CROQUITO_DOCAI_PROCESSOR`.
  - tests/worker/test_providers.py
    (+522/-0, puramente aditivo) bateria do Document AI (parse, recusas, log, HTTP,
    nome de processador) e bateria de montagem da suite por configuração;
    `_hosted_suite_env` passou a neutralizar `CROQUITO_DOCAI_PROCESSOR`.

Validation executed:
  - BASELINE (antes da mudança, com os diffs de F-021 T1+T2 na árvore):
      make check                  exit 0
      make test                   exit 0 — 1602 passed, 10 skipped (pytest); 581 passed (vitest)
      make provider-contract-demo exit 0 — status=human_review_required, readings=3
      make ocr-eval               exit 0 — passed=true, confirmation_recall=1.0,
                                  false_confirmed_count=0
  - FINAL (depois da mudança):
      make check                                     exit 0
      make test                                      exit 0 — 1641 passed, 10 skipped
                                                     (pytest); 581 passed (vitest)
      uv run pytest tests/worker/test_providers.py -x -q  exit 0 — 269 passed
      make provider-contract-demo                    exit 0 — saída idêntica ao baseline
      make ocr-eval                                  exit 0 — saída idêntica ao baseline
  - Nenhuma falha preexistente no baseline; nenhuma falha nova.

Validation skipped: none

Unavailable capabilities: none
  (READ, WRITE e VALIDATE exercidos; COMMIT não foi solicitado e o diff fica na árvore,
  como o contrato manda.)

Assumptions:
  - `startIndex`/`endIndex` de `textSegments` chegam como string no JSON do proto3
    (int64), e `startIndex` ausente é o zero que o proto3 omite. As duas formas são
    aceitas; ver `_document_ai_index`.
  - `normalizedVertices` já vem em 0-1 e é polígono; a bbox retangular é o min/max dos
    vértices, com clamp em 0-1 como no adapter do Vision.
  - O processador provisionado é de OCR e o pipeline só envia PNG (`ingest.py` rasteriza
    em PNG 200 DPI), por isso `mimeType` é constante e não parâmetro.
  - `cloud-platform` (GCP_VISION_SCOPES) autoriza os dois fornecedores; nenhuma constante
    de escopo nova foi criada porque o valor seria idêntico e duas constantes iguais
    convidariam a divergir.

Remaining risks:
  - A forma da resposta real do Document AI não foi exercida contra o serviço: a fixture
    dos testes é sintética, escrita a partir do contrato REST. Um campo que o serviço
    entregue diferente do assumido degrada para linha recusada (nunca para bbox
    inventada), mas reduz recall silenciosamente.
  - Coordenada ausente num vértice recusa a linha em vez de lê-la como o zero do proto3.
    É a escolha conservadora deliberada (ver desvio 2); uma linha exatamente na borda
    `x = 0`/`y = 0` seria perdida.
  - A granularidade de "linha" muda de parágrafo (Vision) para linha do layout (DocAI). O
    ADR-0037 já registra que só o eval comparativo pago contra a mesma prancha confirma o
    efeito na corroboração.
  - O default de `CROQUITO_AI_ESTIMATED_COST_PER_OCR_CALL_USD` (0.0015) foi mantido, mas
    o preço por página do Document AI é maior que o do Cloud Vision. O valor é dado de
    deploy e precisa ser revisto junto do provisionamento (consequência já escrita no
    ADR-0037).

Human decisions required:
  - Aceite do ADR-0037 (hoje `Proposed`).
  - Provisionamento do processador no GCP e definição de `CROQUITO_DOCAI_PROCESSOR` +
    revisão do custo estimado por chamada em HML — atos de infraestrutura/deploy, fora
    do código.
  - Eval comparativo pago (chamada paga em massa) antes de promover o braço.
```

## Desvios conscientes do contrato

1. **`os.getenv(...).strip()` em vez de `os.environ.get(...)` não-vazio.** Variável
   exportada com só espaços passa a contar como ausente. Precedente no módulo:
   `EMBEDDINGS_MODEL_ENV` e `_openai_arm_enabled` já normalizam antes de decidir. Coberto
   por `test_an_empty_processor_env_does_not_switch_the_ocr_arm`.
2. **Coordenada ausente num vértice recusa a linha.** O contrato diz "vértice ausente ou
   caixa de área não positiva → linha RECUSADA"; estendi a recusa para o vértice com
   coordenada faltando. Ler o `x` omitido como o zero do proto3 seria decodificação
   correta, mas infla a caixa até a borda da folha quando o vértice está truncado — e
   `provider_review._reading_confirmed_by_ocr` confirma leitura por texto igual MAIS
   interseção de bbox, então caixa inflada produz falso-confirmado, que é a falha cara.
   Perder uma linha é a falha barata. Documentado no docstring de `_document_ai_bbox` e
   coberto pelo caso `coordenada-omitida`.
3. **`endpoint` é `property`, não campo do dataclass** (no Vision é campo com default).
   O endpoint é derivado do `processor_name`, e um campo permitiria construir um adapter
   cujo endpoint contradiz o próprio processador. `__post_init__` valida o nome na
   construção, como o contrato pede.
4. **Método privado `_failure` no adapter** em vez de repetir
   `provider=ProviderName.GCP_DOCUMENT_AI` em cada uma das nove chamadas de
   `_ocr_failure`. Estrutura idêntica, uma linha de ruído a menos por chamada.
5. **Duas constantes além das nomeadas no contrato**: `DOCAI_RAW_DOCUMENT_MIME_TYPE` (o
   contrato pedia "constante comentada") e `OCR_LINE_TEXT_LIMIT`, com teste de drift
   contra o `max_length` de `OcrLineOutput`.

## Oportunidades vistas e NÃO implementadas (fora de escopo)

- `GCP_VISION_SCOPES` passou a autorizar dois fornecedores e o nome ficou estreito;
  renomear tocaria o braço antigo além do logger.
- `GcpVisionOcrAdapter` e `GcpDocumentAiOcrAdapter` compartilham `_access_token` quase
  literalmente; extrair um mixin/base mexeria no adapter existente sem necessidade agora.
- `ocr_eval.py` e as fixtures sintéticas seguem em `GCP_VISION` — um eixo de eval que
  compare os dois braços contra a mesma prancha é o que o ADR-0037 pede, e é trabalho de
  outra task.
- Documentação de vendor/operação (MODEL_ROUTING, HML, AI_VENDOR_RISK, STATUS) é a T2.
