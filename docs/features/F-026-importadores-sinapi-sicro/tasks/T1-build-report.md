# T1 — BUILD REPORT

```text
feature_id: F-026
task_id: T1
harness: Claude Code (worktree /Users/danielcampos/workspace/daniel/croquito-specs,
         branch f-026-importadores)
```

## Baseline

Estabelecido antes de qualquer edição, na branch `f-026-importadores`, árvore limpa:

- `make setup` — `uv sync --all-groups` + `npm install` + `make contracts` (rodou como
  parte do setup); `git status --short` ficou vazio após o setup: nenhum drift de
  contratos pré-existente.
- `make check` — verde (ruff check, ruff format --check, mypy strict em 194 arquivos,
  check_docs, schema_export --check-dir, contracts:check, web:check tsc+vite build,
  infra-check terraform fmt).
- `make test` — verde: `1695 passed, 13 skipped` (pytest) + `693 passed` em 39 arquivos
  (vitest).

Nenhuma falha pré-existente registrada.

## BUILD REPORT

```text
Status: BUILD_COMPLETE

Files changed:
  - packages/valuation/src/croquito_valuation/models.py
    -> PriceOrigin ganha SINAPI="sinapi" e SICRO="sicro"; docstring da classe estendida
       citando ADR-0039/F-026 e o superset NON_SCO_CODE_PATTERN que as origens novas
       compartilham com EMOP/composição (linhas 95-118 aprox., NON_SCO_CODE_PATTERN
       intocado).
  - packages/valuation/src/croquito_valuation/assignment.py
    -> SUGGESTION_SCHEMA_VERSION "1.1.0" -> "1.2.0" (linha 62) e o Literal do campo
       schema_version de CodeSuggestionSet "1.1.0" -> "1.2.0" (linha 247), porque o
       schema publicado code-suggestions.schema.json embute PriceOrigin em
       CodeCandidate.catalog_origin (decisão 5 do ADR-0039).
  - packages/valuation/src/croquito_valuation/estimate.py
    -> ESTIMATE_SCHEMA_VERSION "2.0.0" -> "2.1.0" (linha 59) e o Literal do campo
       schema_version de Estimate "2.0.0" -> "2.1.0" (linha 170), pelo mesmo motivo
       (estimate.schema.json embute PriceOrigin em CatalogSource.origin/EstimateLine).
  - packages/contracts/schemas/code-suggestions.schema.json
    -> regenerado por `make contracts`: enum PriceOrigin ganha sinapi/sicro, $id e
       schema_version.const/default sobem para 1.2.0. Nunca editado à mão.
  - packages/contracts/schemas/estimate.schema.json
    -> regenerado por `make contracts`: mesmo padrão, versão 2.1.0. Nunca editado à mão.
  - packages/contracts/src/code-suggestions.generated.ts
    -> regenerado por `make contracts` a partir do schema acima. Nunca editado à mão.
  - packages/contracts/src/estimate.generated.ts
    -> regenerado por `make contracts` a partir do schema acima. Nunca editado à mão.
  - apps/web/src/orcamento/labels.ts
    -> PRICE_ORIGIN_LABELS ganha sinapi:"SINAPI" e sicro:"SICRO" (linhas 145-151).
       priceOriginSeloClass NÃO ganhou entrada nova — desvio de propósito, ver seção
       "Desvios conscientes" abaixo.
  - apps/web/src/orcamento/labels.test.ts (novo)
    -> cobre priceOriginLabel para sinapi/sicro e priceOriginSeloClass caindo no
       fallback selo-neutro para as duas origens novas; nenhum teste de label existia
       antes para este módulo.
  - tests/valuation/test_calc.py
    -> novo teste parametrizado
       test_bulletin_refuses_a_catalog_whose_origin_is_sinapi_or_sicro (origin in
       [PriceOrigin.SINAPI, PriceOrigin.SICRO]), espelho de
       test_bulletin_refuses_a_catalog_whose_origin_is_not_sco (linha 431/464): prova
       BULLETIN_PRICE_ORIGIN_FORBIDDEN para as duas origens novas.
  - tests/valuation/test_writer_roundtrip.py
    -> novo teste parametrizado
       test_the_writer_refuses_a_catalog_whose_origin_is_sinapi_or_sicro (origin in
       ["sinapi", "sicro"]), espelho de test_the_writer_refuses_a_catalog_whose_origin_is_not_sco
       (linha 206/219): segunda linha de defesa do guardrail, no escritor de planilha.
  - tests/valuation/test_assignment.py
    -> asserção hardcoded restored.schema_version == "1.1.0" (linha 1223) ajustada para
       "1.2.0", consequência direta do bump de SUGGESTION_SCHEMA_VERSION (ver "Desvios
       conscientes").
  - tests/valuation/golden/estimate-demo.canonical.json
    -> ÚNICA mudança: "schema_version": "2.0.0" -> "2.1.0" (linha 211), confirmado por
       `git diff` isolado a essa linha.
  - docs/features/F-026-importadores-sinapi-sicro/tasks/T1-build-report.md (novo, este
    arquivo)

Validation executed (todos em foreground, no worktree, na ordem do contrato):
  - make check -> verde. ruff check "All checks passed!"; ruff format --check "420
    files already formatted"; mypy strict "Success: no issues found in 194 source
    files"; check_docs "249 arquivos Markdown, paridade de lifecycle verificada" (248
    no baseline -> 249 porque este T1-build-report.md entrou); schema_export
    --check-dir sem drift; contracts:check sem drift; web:check (tsc -b + vite build)
    verde; infra-check (terraform fmt -check) verde.
  - make test -> verde. pytest: "1699 passed, 13 skipped, 48 warnings" (1695->1699: os
    4 testes novos parametrizados, 2 em test_calc.py + 2 em test_writer_roundtrip.py).
    vitest: "Test Files 40 passed (40)" / "Tests 697 passed (697)" (693->697: os 4
    testes novos de apps/web/src/orcamento/labels.test.ts).
  - uv run pytest tests/valuation/test_calc.py tests/valuation/test_writer_roundtrip.py
    tests/valuation/test_canonical_golden.py -x -q -> verde, "49 passed, 5 warnings".
  - make valuation-estimate-demo -> verde, status "ok", schema_version "2.1.0",
    total_amount "71516.83", lines_by_origin {"composition":1,"emop":2,"sco":2}.
    Determinismo verificado rodando duas vezes seguidas e comparando estimate.json
    (chaves ordenadas): campos lógicos (schema_version, preços, totais, cascade
    origins/labels, lines_by_origin) idênticos entre as duas execuções; só
    source_pdf_sha256 e o source_sha256 do catálogo SCO variam — não-determinismo já
    documentado no docstring de tests/valuation/test_canonical_golden.py (pymupdf/
    openpyxl gravam identificadores/timestamp novos a cada save), não uma regressão
    desta task.

Validation skipped: none

Unavailable capabilities: none

Assumptions:
  - Nenhuma além das já registradas no plano da F-026 (verificadas de novo nesta task:
    nenhum match exaustivo por PriceOrigin fora de composition.py/emop.py/
    estimate_fixture.py/cli.py, todos ligados à origem própria deles, não a um
    switch/match sobre o enum inteiro; NON_SCO_CODE_PATTERN permanece o superset
    estrutural correto para sinapi/sicro sem alteração).

Remaining risks:
  - O padrão estrutural REAL de código SINAPI/SICRO (formato de dado do importador,
    T2) ainda não existe; até lá, sinapi/sicro só têm o superset genérico
    NON_SCO_CODE_PATTERN como validação de forma, igual à EMOP antes do importador
    dela — risco já é do desenho aceito no ADR-0039, não desta task.
  - services/worker/src/croquito_worker/review.py:153 tem um Literal["1.0.0","1.1.0"]
    de outro schema (ReviewPacket), não tocado nesta task por ser owner de uma versão
    e um artefato completamente diferentes (nada a ver com PriceOrigin/
    SUGGESTION_SCHEMA_VERSION); registrado aqui só para deixar claro que foi
    verificado e descartado, não esquecido.

Human decisions required: none para esta task (T1 é escopo fechado e os portões
  fecham sozinhos; aceite/priorização de T2/T3 e produção seguem o processo normal
  da feature).
```

## Desvios conscientes do spec

1. **`tests/valuation/test_assignment.py:1223`** — o contrato citava
   `test_canonical_golden.py`/`test_estimate.py` como os arquivos prováveis de
   asserção hardcoded de versão, mas `make check` (mypy) apontou uma terceira:
   `restored.schema_version == "1.1.0"` em `test_the_refined_set_survives_a_json_round_trip`
   (mypy: "Non-overlapping equality check" porque o campo virou
   `Literal["1.2.0"]`). Ajustado para `"1.2.0"` — é exatamente a categoria de desvio
   que o próprio contrato pré-autorizou ("Ajuste as asserções de versão hardcoded que
   existirem nos testes... desvio autorizado por consequência direta, escopo
   mínimo"), só que numa localização diferente da antecipada. `test_estimate.py` e
   `test_canonical_golden.py` (fora da linha do golden em si) não tinham nenhuma
   asserção hardcoded de `ESTIMATE_SCHEMA_VERSION`/`SUGGESTION_SCHEMA_VERSION` —
   verificado por grep, nada a ajustar neles.
2. **`priceOriginSeloClass` sem entrada nova** — seguido à risca como o contrato
   pediu: sinapi/sicro caem no fallback `selo-neutro`. Registrando aqui de novo,
   como o contrato exigiu: cor por origem nova é decisão de design que esta feature
   não tem; nenhuma cor foi inventada.
3. **Docstring de `PriceOrigin` estendida além do mínimo literal** — o contrato pedia
   "valores novos + docstring estendida"; a extensão inclui uma frase nova
   explicando que sinapi/sicro compartilham o superset `NON_SCO_CODE_PATTERN` com
   EMOP/composição. Julguei que documentar essa relação no próprio enum (não só no
   ADR) evita que um leitor futuro do código presuma que os códigos novos têm forma
   fechada própria aqui. Sem mudança de comportamento.

## Oportunidades vistas e NÃO implementadas (fora de escopo)

- Nenhum importador SINAPI/SICRO, fixture ou comando de CLI — é T2, dependente desta
  task e explicitamente fora de escopo aqui.
- Nenhuma cor/selo novo para SINAPI/SICRO na web — decisão de design não tomada nesta
  feature; documentado no código (`priceOriginSeloClass`) e neste relatório, não
  implementado.
- `services/worker/src/croquito_worker/review.py:153` tem seu próprio
  `SCHEMA_VERSION`/`Literal` de dois valores para `ReviewPacket` — não é o schema
  desta task (não embute `PriceOrigin`) e não foi tocado.
- Nenhum outro schema do manifesto (`scene`, `takeoff-packet`, `code-assignments`,
  `valuation`, `amendment-dossier`) embute `PriceOrigin` — confirmado de novo por
  inspeção do manifesto (`packages/contracts/contracts.manifest.json`) e do diff real
  de `make contracts` (só os dois schemas esperados mudaram); nenhum bump adicional
  aplicado.
