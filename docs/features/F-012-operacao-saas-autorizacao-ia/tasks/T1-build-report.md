# T1 — Build Report

```text
BUILD REPORT

Status: BUILD_COMPLETE
Files changed:
  - services/worker/src/croquito_worker/local_queue.py — removido o campo
    LocalWorkerSettings.ai_extraction_allowed_digests (com o comentário), o parse de
    CROQUITO_AI_EXTRACTION_ALLOWED_DIGESTS em from_environment, e o bloco de checagem
    de allowlist em _handle_upload (com os dois comentários internos, que passariam a
    mentir). O early-return de reentrega, o gate de consent
    (AI_PROCESSING_NOT_AUTHORIZED) e a construção da suite real ficam intocados —
    confirmado por leitura do diff linha a linha.
  - tests/worker/test_local_queue.py — apagado
    test_extraction_refuses_a_document_outside_the_allowlist (cobria o comportamento
    removido); removido o kwarg ai_extraction_allowed_digests de
    test_hosted_suite_labels_the_revision_as_paid_extraction. Nenhum import ficou
    órfão: hashlib segue usado em três outros pontos do arquivo.
  - .github/workflows/deploy-hml.yml — removido
    CROQUITO_AI_EXTRACTION_ALLOWED_DIGESTS= do --set-env-vars do worker e o trecho do
    comentário que descrevia a allowlist; o comentário sobre kill switch
    (CROQUITO_REAL_PROVIDERS_ENABLED) e teto (CROQUITO_AI_MAX_ESTIMATED_COST_USD)
    permanece.
  - docs/adr/0036-autorizacao-de-ia-contratual-sem-allowlist-documental.md (novo,
    Proposed) — contexto, decisão (gate = entitlement + consent + teto + kill switch;
    allowlist por digest permanece só em extraction_eval.py), alternativas (rota de
    plataforma para a allowlist — rejeitada), consequências (supersede parcialmente o
    D6 do ADR-0035; ADR-0035 não é reescrito), riscos e rastreabilidade.
  - docs/adr/README.md — acrescentada a linha do índice para o ADR-0036 (Proposed).
    Não estava no mapa de arquivos do spec, mas é exigido por
    validate_adr_index_parity() em scripts/check_docs.py: todo arquivo em docs/adr/
    precisa de linha correspondente no índice, senão make check reprova. Sem essa
    linha, o critério de aceite "make check verde" não seria alcançável.

Validation executed:
  - grep -n "ai_extraction_allowed_digests\|AI_EXTRACTION_NOT_ALLOWLISTED"
    services/worker/src/croquito_worker/local_queue.py -> vazio (critério de aceite 1)
  - make check -> verde (ruff check, ruff format --check, mypy strict em 187 arquivos,
    check_docs.py, schema_export --check-dir, contracts:check, web:check/vite build,
    terraform fmt -check)
  - make test -> verde (uv run pytest: 1476 passed, 10 skipped, 47 warnings; npm
    web:test/vitest: 29 arquivos, 529 testes passando)
  - git diff --stat tests/worker/test_extraction_eval.py tests/worker/test_cli.py
    tests/worker/test_transcription.py tests/worker/test_valuation_extraction_cli.py
    tests/worker/test_valuation_local_server.py
    tests/worker/test_valuation_legend_extraction.py -> vazio (nenhuma edição); os
    seis arquivos rodados isoladamente também passam (uv run pytest
    tests/worker/test_extraction_eval.py tests/worker/test_cli.py
    tests/worker/test_transcription.py -q)
  - uv run pytest
    tests/worker/test_local_queue.py::test_real_providers_require_contractual_authorization_before_reading_upload
    -> passa (critério de aceite 3, o gate de consent que fica)
  - Verificação isolada dos checks de docs (validate_adr_index_parity,
    validate_file no ADR-0036, validate_feature_artifacts, validate_roadmap_feature_parity)
    -> 0 erros cada, via scripts/check_docs.py importado diretamente

Validation skipped: none

Unavailable capabilities: none

Assumptions:
  - "formato dos vizinhos" para o ADR-0036 inclui adicionar a linha correspondente no
    índice docs/adr/README.md, já que check_docs.py exige essa paridade — tratado
    como parte necessária do escopo do arquivo novo, não como escopo adicional.
  - O gap "F-012 sem linha no roadmap" que apareceu na primeira rodada de make check
    era pré-existente (commit b01af5a, anterior ao início desta task, sem tocar
    docs/product/ROADMAP.md) e foi fechado por trabalho concorrente na branch
    (commit 512e49d, "paridade de lifecycle — linha no roadmap e estado
    IN_PROGRESS") enquanto esta task estava em andamento — não é entrega desta task
    T1; make check foi re-executado depois e ficou verde.

Remaining risks: none identificado dentro do escopo desta task. A allowlist por
digest continua existindo em extraction_eval.py (fora de escopo, intocada) com a
mesma variável de ambiente por nome — o ADR-0036 registra essa ambiguidade de nome
explicitamente como risco mitigado por referência cruzada e pela atualização de
HML.md/RUNBOOK_VALUATION_TOCA_ACCEPTANCE.md na T4.

Human decisions required: aceite do ADR-0036 (Proposed -> Accepted/Rejected) é ato
humano posterior, como registrado no Human Gate do task contract.
```

## Desvios conscientes do spec

Nenhum desvio de comportamento. Único acréscimo ao mapa de arquivos do spec foi
`docs/adr/README.md` (linha de índice do ADR-0036), necessário para `make check`
passar (`validate_adr_index_parity`) — documentado acima em "Files changed" e
"Assumptions".

## Oportunidades vistas e não implementadas (fora de escopo)

- `docs/operations/HML.md` e `docs/operations/RUNBOOK_VALUATION_TOCA_ACCEPTANCE.md`
  ainda descrevem o ritual manual da allowlist hospedada (linhas 276/344 e
  90/117/226 respectivamente) — explicitamente atribuído à T4 pelo plano
  (`out_of_scope` desta task lista HML.md e o runbook).
- `docs/features/F-012-operacao-saas-autorizacao-ia/feature.md:31,72` cita a
  allowlist/`AI_EXTRACTION_NOT_ALLOWLISTED` como critério de aceite do texto do
  contrato de feature — não editado por não estar no mapa de arquivos da T1; a
  feature.md já foi escrita prevendo esta remoção.
